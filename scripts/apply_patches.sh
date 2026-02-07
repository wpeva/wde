#!/bin/bash
# Apply antidetect patches to Chromium source tree
#
# Usage:
#   ./scripts/apply_patches.sh /path/to/chromium/src
#
# Prerequisites:
#   - Chromium source tree checked out (see README.md)
#   - git initialized in the chromium/src directory

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_DIR="$SCRIPT_DIR/../patches"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <chromium_src_dir>"
    echo ""
    echo "Example:"
    echo "  $0 ~/chromium/src"
    exit 1
fi

CHROMIUM_SRC="$1"

if [ ! -d "$CHROMIUM_SRC" ]; then
    echo "Error: Directory '$CHROMIUM_SRC' does not exist."
    exit 1
fi

if [ ! -f "$CHROMIUM_SRC/BUILD.gn" ]; then
    echo "Error: '$CHROMIUM_SRC' does not appear to be a Chromium source directory."
    echo "       Expected to find BUILD.gn in the root."
    exit 1
fi

echo "=== Chromium Antidetect Patcher ==="
echo "Source dir: $CHROMIUM_SRC"
echo "Patch dir:  $PATCH_DIR"
echo ""

# Create the antidetect utils directory first (needed by all patches)
ANTIDETECT_DIR="$CHROMIUM_SRC/third_party/blink/renderer/core/antidetect"
if [ ! -d "$ANTIDETECT_DIR" ]; then
    echo "[*] Creating antidetect utils directory..."
    mkdir -p "$ANTIDETECT_DIR"
fi

FAILED=0
APPLIED=0

for patch_file in "$PATCH_DIR"/*.patch; do
    patch_name="$(basename "$patch_file")"
    echo -n "[*] Applying $patch_name... "

    if git -C "$CHROMIUM_SRC" apply --check "$patch_file" 2>/dev/null; then
        git -C "$CHROMIUM_SRC" apply "$patch_file"
        echo "OK"
        ((APPLIED++))
    else
        echo "SKIPPED (may already be applied or needs manual resolution)"
        ((FAILED++))
    fi
done

echo ""
echo "=== Results ==="
echo "Applied: $APPLIED"
echo "Skipped: $FAILED"
echo ""

if [ $FAILED -gt 0 ]; then
    echo "Some patches were skipped. You may need to apply them manually."
    echo "Try: git apply --3way patches/<name>.patch"
fi

echo ""
echo "Next steps:"
echo "  1. cd $CHROMIUM_SRC"
echo "  2. gn gen out/Antidetect --args='$(cat $SCRIPT_DIR/gn_args.txt 2>/dev/null || echo "is_debug=false")'"
echo "  3. autoninja -C out/Antidetect chrome"
echo ""
echo "Done."
