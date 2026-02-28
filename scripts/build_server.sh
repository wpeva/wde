#!/bin/bash
###############################################################################
# WDE Chromium Antidetect — Full Automated Build Script
#
# Run on a clean Ubuntu 22.04 server with 250+ GB disk, 16+ GB RAM
#
# Usage:
#   curl -sSL <raw_url_to_this_script> | bash
#   # or:
#   chmod +x build_server.sh && ./build_server.sh
#
# The script will:
#   1. Install all dependencies
#   2. Download depot_tools + Chromium source (shallow, ~25 GB)
#   3. Apply antidetect patches
#   4. Build Chromium (~2-6 hours depending on CPU)
#   5. Package the result into a portable .tar.gz (~1.5 GB)
#
# Environment variables (optional):
#   WDE_REPO_URL    - URL to this repo (default: from git remote)
#   WDE_BRANCH      - Branch with patches (default: master)
#   CHROMIUM_TAG    - Specific Chromium version tag (default: latest stable)
#   BUILD_JOBS      - Number of parallel build jobs (default: nproc)
#   SKIP_DOWNLOAD   - Set to 1 to skip Chromium download (if already present)
#   SKIP_BUILD      - Set to 1 to skip the build step
###############################################################################

set -euo pipefail

# --- Config ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${WORK_DIR:-/home/user/chromium-build}"
WDE_DIR="${WDE_DIR:-$SCRIPT_DIR/..}"
BUILD_JOBS="${BUILD_JOBS:-$(nproc)}"
CHROMIUM_TAG="${CHROMIUM_TAG:-}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[WDE]${NC} $*"; }
warn() { echo -e "${YELLOW}[WDE WARN]${NC} $*"; }
err()  { echo -e "${RED}[WDE ERROR]${NC} $*" >&2; }

# --- Step 0: Preflight checks ---
preflight() {
    log "=== Preflight Checks ==="

    # Check disk space (need at least 100 GB free)
    AVAIL_GB=$(df --output=avail -BG "$WORK_DIR" 2>/dev/null | tail -1 | tr -d 'G ')
    if [ -z "$AVAIL_GB" ]; then
        AVAIL_GB=$(df -BG "$WORK_DIR" | tail -1 | awk '{print $4}' | tr -d 'G')
    fi
    log "Available disk: ${AVAIL_GB} GB"
    if [ "$AVAIL_GB" -lt 80 ]; then
        err "Need at least 80 GB free disk space, have ${AVAIL_GB} GB"
        err "For full build with source, 200+ GB recommended"
        exit 1
    fi

    # Check RAM
    TOTAL_RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
    log "Total RAM: ${TOTAL_RAM_MB} MB"
    if [ "$TOTAL_RAM_MB" -lt 8000 ]; then
        warn "Low RAM (${TOTAL_RAM_MB} MB). Build may fail or be very slow."
        warn "Recommended: 16+ GB. Will reduce parallelism."
        BUILD_JOBS=$(( BUILD_JOBS > 4 ? 4 : BUILD_JOBS ))
    fi

    log "Build jobs: $BUILD_JOBS"
    log "Work dir: $WORK_DIR"
    log "WDE patches dir: $WDE_DIR/patches"
}

# --- Step 1: Install system dependencies ---
install_deps() {
    log "=== Step 1/5: Installing System Dependencies ==="

    export DEBIAN_FRONTEND=noninteractive

    sudo apt-get update -qq

    sudo apt-get install -y -qq \
        git curl wget python3 python3-pip lsb-release sudo \
        build-essential clang lld \
        pkg-config libglib2.0-dev libdbus-1-dev libnss3-dev \
        libatk1.0-dev libatk-bridge2.0-dev libcups2-dev \
        libdrm-dev libxkbcommon-dev libxcomposite-dev \
        libxdamage-dev libxrandr-dev libgbm-dev libpango1.0-dev \
        libcairo2-dev libasound2-dev libpulse-dev libxtst-dev \
        gperf bison flex nodejs npm zip unzip \
        xvfb xdg-utils

    log "System dependencies installed."
}

# --- Step 2: Setup depot_tools ---
setup_depot_tools() {
    log "=== Step 2/5: Setting up depot_tools ==="

    if [ -d "$WORK_DIR/depot_tools" ]; then
        log "depot_tools already exists, updating..."
        cd "$WORK_DIR/depot_tools"
        git pull -q
    else
        mkdir -p "$WORK_DIR"
        git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git \
            "$WORK_DIR/depot_tools"
    fi

    export PATH="$WORK_DIR/depot_tools:$PATH"
    log "depot_tools ready. fetch=$(which fetch), gclient=$(which gclient)"
}

# --- Step 3: Fetch Chromium source ---
fetch_chromium() {
    if [ "${SKIP_DOWNLOAD:-0}" = "1" ]; then
        log "Skipping Chromium download (SKIP_DOWNLOAD=1)"
        return
    fi

    log "=== Step 3/5: Fetching Chromium Source (shallow) ==="
    log "This will download ~25 GB. Be patient..."

    mkdir -p "$WORK_DIR/chromium"
    cd "$WORK_DIR/chromium"

    if [ ! -f ".gclient" ]; then
        fetch --nohooks --no-history chromium
    else
        log ".gclient already exists, skipping fetch"
    fi

    cd "$WORK_DIR/chromium/src"

    # If a specific tag is requested, checkout to it
    if [ -n "$CHROMIUM_TAG" ]; then
        log "Checking out tag: $CHROMIUM_TAG"
        git fetch --depth=1 origin "refs/tags/$CHROMIUM_TAG:refs/tags/$CHROMIUM_TAG"
        git checkout "$CHROMIUM_TAG"
    fi

    # Install build dependencies (Chromium's own script)
    log "Running Chromium install-build-deps..."
    sudo ./build/install-build-deps.sh --no-prompt --no-arm --no-chromeos-fonts || true

    # Run hooks
    log "Running gclient hooks..."
    gclient runhooks

    log "Chromium source ready."
}

# --- Step 4: Apply antidetect patches ---
apply_patches() {
    log "=== Step 4/5: Applying Antidetect Patches ==="

    CHROMIUM_SRC="$WORK_DIR/chromium/src"
    PATCH_DIR="$WDE_DIR/patches"

    if [ ! -d "$PATCH_DIR" ]; then
        err "Patch directory not found: $PATCH_DIR"
        err "Make sure the WDE repo is cloned properly"
        exit 1
    fi

    # Create the antidetect utils directory
    mkdir -p "$CHROMIUM_SRC/third_party/blink/renderer/core/antidetect"

    # First, extract and apply the new-file patches (antidetect_utils.h, BUILD.gn)
    # These are embedded in patch 01
    log "Extracting antidetect_utils.h from patch 01..."

    APPLIED=0
    FAILED=0
    NEEDS_MANUAL=()

    for patch_file in "$PATCH_DIR"/*.patch; do
        patch_name="$(basename "$patch_file")"
        echo -n "  [*] $patch_name... "

        # Try strict apply first
        if git -C "$CHROMIUM_SRC" apply --check "$patch_file" 2>/dev/null; then
            git -C "$CHROMIUM_SRC" apply "$patch_file"
            echo "OK"
            ((APPLIED++))
        # Try with fuzz
        elif git -C "$CHROMIUM_SRC" apply --check -C0 "$patch_file" 2>/dev/null; then
            git -C "$CHROMIUM_SRC" apply -C0 "$patch_file"
            echo "OK (fuzzy)"
            ((APPLIED++))
        # Try 3-way merge
        elif git -C "$CHROMIUM_SRC" apply --check --3way "$patch_file" 2>/dev/null; then
            git -C "$CHROMIUM_SRC" apply --3way "$patch_file"
            echo "OK (3-way)"
            ((APPLIED++))
        else
            echo "NEEDS MANUAL ADAPTATION"
            ((FAILED++))
            NEEDS_MANUAL+=("$patch_name")
        fi
    done

    echo ""
    log "Patches applied: $APPLIED"
    if [ $FAILED -gt 0 ]; then
        warn "Patches needing manual adaptation: $FAILED"
        for p in "${NEEDS_MANUAL[@]}"; do
            warn "  - $p"
        done
        warn ""
        warn "These patches reference specific line numbers that may have shifted"
        warn "in your Chromium version. You need to manually apply the changes."
        warn ""
        warn "The patches are well-commented, showing exactly which files and"
        warn "functions to modify. See README.md for details."
        warn ""
        read -p "Continue with build anyway? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            err "Aborted. Fix patches and re-run with SKIP_DOWNLOAD=1"
            exit 1
        fi
    fi

    # Register antidetect module in parent BUILD.gn
    CORE_BUILD_GN="$CHROMIUM_SRC/third_party/blink/renderer/core/BUILD.gn"
    if [ -f "$CORE_BUILD_GN" ]; then
        if ! grep -q "antidetect" "$CORE_BUILD_GN"; then
            log "Registering antidetect module in core/BUILD.gn..."
            # Add to the deps list
            sed -i '/group("core") {/,/deps = \[/ {
                /deps = \[/a\    "//third_party/blink/renderer/core/antidetect",
            }' "$CORE_BUILD_GN" 2>/dev/null || \
            warn "Could not auto-register antidetect in BUILD.gn — do it manually"
        fi
    fi

    log "Patches applied."
}

# --- Step 5: Build ---
build_chromium() {
    if [ "${SKIP_BUILD:-0}" = "1" ]; then
        log "Skipping build (SKIP_BUILD=1)"
        return
    fi

    log "=== Step 5/5: Building Chromium ==="

    CHROMIUM_SRC="$WORK_DIR/chromium/src"
    cd "$CHROMIUM_SRC"

    # Generate build config
    GN_ARGS='
is_debug = false
is_official_build = false
is_component_build = false
symbol_level = 0
blink_symbol_level = 0
v8_symbol_level = 0
enable_nacl = false
treat_warnings_as_errors = false
proprietary_codecs = true
ffmpeg_branding = "Chrome"
is_clang = true
use_sysroot = true
chrome_pgo_phase = 0
'

    log "Generating build files with GN..."
    gn gen out/Antidetect --args="$GN_ARGS"

    log "Starting build with $BUILD_JOBS jobs..."
    log "This will take 2-6 hours depending on your hardware."
    log "You can monitor progress: tail -f /tmp/chromium-build.log"

    # Build with autoninja (or ninja directly)
    if command -v autoninja &>/dev/null; then
        autoninja -C out/Antidetect chrome 2>&1 | tee /tmp/chromium-build.log
    else
        ninja -j"$BUILD_JOBS" -C out/Antidetect chrome 2>&1 | tee /tmp/chromium-build.log
    fi

    log "Build complete!"
}

# --- Step 6: Package ---
package_build() {
    log "=== Packaging Build ==="

    CHROMIUM_SRC="$WORK_DIR/chromium/src"
    OUT_DIR="$CHROMIUM_SRC/out/Antidetect"
    PACKAGE_DIR="$WORK_DIR/antidetect-browser"
    ARCHIVE="$WORK_DIR/antidetect-browser-$(date +%Y%m%d).tar.gz"

    mkdir -p "$PACKAGE_DIR"

    # Copy essential files
    log "Collecting browser files..."

    # Main binary
    cp "$OUT_DIR/chrome" "$PACKAGE_DIR/"

    # Required shared libraries and resources
    for f in \
        chrome_100_percent.pak \
        chrome_200_percent.pak \
        resources.pak \
        icudtl.dat \
        v8_context_snapshot.bin \
        snapshot_blob.bin \
        chrome_crashpad_handler \
        libEGL.so \
        libGLESv2.so \
        libvk_swiftshader.so \
        libvulkan.so.1 \
        vk_swiftshader_icd.json \
        ; do
        [ -f "$OUT_DIR/$f" ] && cp "$OUT_DIR/$f" "$PACKAGE_DIR/" || true
    done

    # Locales
    mkdir -p "$PACKAGE_DIR/locales"
    cp "$OUT_DIR/locales/"*.pak "$PACKAGE_DIR/locales/" 2>/dev/null || true

    # MEI resources (for Widevine etc.)
    [ -d "$OUT_DIR/MEIPreload" ] && cp -r "$OUT_DIR/MEIPreload" "$PACKAGE_DIR/" || true

    # Copy launch script from WDE
    cp "$WDE_DIR/scripts/launch_antidetect.sh" "$PACKAGE_DIR/"
    chmod +x "$PACKAGE_DIR/launch_antidetect.sh"

    # Fix the launch script to use local binary
    sed -i 's|./out/Antidetect/chrome|./chrome|g' "$PACKAGE_DIR/launch_antidetect.sh"

    # Create the archive
    log "Creating archive: $ARCHIVE"
    cd "$WORK_DIR"
    tar -czf "$ARCHIVE" -C "$WORK_DIR" antidetect-browser/

    ARCHIVE_SIZE=$(du -h "$ARCHIVE" | cut -f1)
    log "Package ready: $ARCHIVE ($ARCHIVE_SIZE)"
    log ""
    log "=== DONE ==="
    log ""
    log "To use on another machine:"
    log "  1. scp $ARCHIVE user@target:~/"
    log "  2. tar xzf antidetect-browser-*.tar.gz"
    log "  3. cd antidetect-browser"
    log "  4. ./launch_antidetect.sh --profile my_profile"
    log ""
}

# --- Main ---
main() {
    log "============================================="
    log "  WDE Chromium Antidetect Build System"
    log "============================================="
    log ""

    mkdir -p "$WORK_DIR"
    preflight
    install_deps
    setup_depot_tools
    fetch_chromium
    apply_patches
    build_chromium
    package_build
}

main "$@"
