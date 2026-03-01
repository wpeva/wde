#!/bin/bash
###############################################################################
# WDE Antidetect Browser — ONE COMMAND TO RULE THEM ALL
#
# Usage:
#   ./run.sh                          # Build + Run (first time)
#   ./run.sh --profile trader1        # Run with named profile
#   ./run.sh --skip-build             # Run without rebuild
#   ./run.sh --docker                 # Build & run via Docker
#
# Requirements:
#   Bare metal: Ubuntu 22.04, 250+ GB disk, 16+ GB RAM, 4+ CPU cores
#   Docker:     Docker installed, 300+ GB disk
#
# What it does:
#   1. Installs deps + depot_tools
#   2. Downloads Chromium (~25 GB)
#   3. Applies antidetect patches (autopatcher)
#   4. Builds Chromium (~2-6 hours)
#   5. Launches the browser with antidetect flags
###############################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${WORK_DIR:-/home/$(whoami)/chromium-build}"
PROFILE="default"
SKIP_BUILD=0
USE_DOCKER=0
EXTRA_CHROME_ARGS=()

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[WDE]${NC} $*"; }
warn() { echo -e "${YELLOW}[WDE]${NC} $*"; }
err()  { echo -e "${RED}[WDE]${NC} $*" >&2; }
info() { echo -e "${CYAN}[WDE]${NC} $*"; }

# --- Parse args ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --profile)     PROFILE="$2"; shift 2 ;;
        --skip-build)  SKIP_BUILD=1; shift ;;
        --docker)      USE_DOCKER=1; shift ;;
        --help|-h)
            echo "Usage: ./run.sh [--profile NAME] [--skip-build] [--docker] [-- extra-chrome-flags]"
            echo ""
            echo "Options:"
            echo "  --profile NAME    Browser profile name (default: 'default')"
            echo "  --skip-build      Skip build, use existing binary"
            echo "  --docker          Build and run in Docker"
            echo "  -- <flags>        Extra flags passed to Chrome"
            exit 0
            ;;
        --)            shift; EXTRA_CHROME_ARGS=("$@"); break ;;
        *)             EXTRA_CHROME_ARGS+=("$1"); shift ;;
    esac
done

# ============================================================================
# PATH: Docker
# ============================================================================
run_docker() {
    log "=== Docker Mode ==="

    if ! command -v docker &>/dev/null; then
        err "Docker not installed. Install it first:"
        err "  curl -fsSL https://get.docker.com | sh"
        exit 1
    fi

    IMAGE_NAME="wde-antidetect"

    # Build image if needed
    if ! docker image inspect "$IMAGE_NAME" &>/dev/null || [ "$SKIP_BUILD" = "0" ]; then
        log "Building Docker image (this takes 3-6 hours first time)..."
        docker build -t "$IMAGE_NAME" "$SCRIPT_DIR"
    fi

    # Run
    log "Launching antidetect browser (profile: $PROFILE)..."
    docker run -it --rm \
        --name "wde-$PROFILE" \
        -e DISPLAY="${DISPLAY:-:0}" \
        -v /tmp/.X11-unix:/tmp/.X11-unix \
        -v "$HOME/.wde-profiles/$PROFILE:/tmp/antidetect-profiles/$PROFILE" \
        --shm-size=2g \
        "$IMAGE_NAME" \
        --profile "$PROFILE" \
        "${EXTRA_CHROME_ARGS[@]+"${EXTRA_CHROME_ARGS[@]}"}"
}

# ============================================================================
# PATH: Bare metal
# ============================================================================
find_chrome_binary() {
    # Check common locations
    local locations=(
        "$WORK_DIR/chromium/src/out/Antidetect/chrome"
        "$WORK_DIR/antidetect-browser/chrome"
        "$SCRIPT_DIR/out/Antidetect/chrome"
        "$SCRIPT_DIR/chrome"
    )
    for loc in "${locations[@]}"; do
        if [ -x "$loc" ]; then
            echo "$loc"
            return 0
        fi
    done
    return 1
}

run_bare_metal() {
    # Check if binary already exists
    CHROME_BIN=""
    if CHROME_BIN=$(find_chrome_binary); then
        if [ "$SKIP_BUILD" = "1" ]; then
            log "Using existing binary: $CHROME_BIN"
        else
            info "Found existing binary: $CHROME_BIN"
            info "Use --skip-build to skip rebuild."
        fi
    fi

    # Build if needed
    if [ -z "$CHROME_BIN" ] || [ "$SKIP_BUILD" = "0" ]; then
        if [ -z "$CHROME_BIN" ]; then
            log "No browser binary found. Starting full build..."
        fi

        # Run the build script
        export WORK_DIR
        export SKIP_DOWNLOAD="${SKIP_DOWNLOAD:-0}"
        bash "$SCRIPT_DIR/scripts/build_server.sh"

        # Find the built binary
        if ! CHROME_BIN=$(find_chrome_binary); then
            err "Build completed but chrome binary not found!"
            err "Check build output for errors."
            exit 1
        fi
    fi

    # Launch
    log ""
    log "============================================="
    log "  Launching Antidetect Browser"
    log "  Profile: $PROFILE"
    log "  Binary:  $CHROME_BIN"
    log "============================================="
    log ""

    exec bash "$SCRIPT_DIR/scripts/launch_antidetect.sh" \
        --profile "$PROFILE" \
        "$CHROME_BIN" \
        "${EXTRA_CHROME_ARGS[@]+"${EXTRA_CHROME_ARGS[@]}"}"
}

# ============================================================================
# Main
# ============================================================================
echo ""
echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   WDE Antidetect Browser             ║${NC}"
echo -e "${CYAN}║   Profile: $(printf '%-25s' "$PROFILE")║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

if [ "$USE_DOCKER" = "1" ]; then
    run_docker
else
    run_bare_metal
fi
