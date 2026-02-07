#!/bin/bash
# Launch Chromium with antidetect profile settings
#
# Usage:
#   ./scripts/launch_antidetect.sh [--profile <name>] [chromium_binary]
#
# Example:
#   ./scripts/launch_antidetect.sh --profile profile1 ./out/Antidetect/chrome
#   ./scripts/launch_antidetect.sh  # uses defaults

set -euo pipefail

PROFILE_NAME="default"
CHROME_BINARY=""
USER_DATA_DIR=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --profile)
            PROFILE_NAME="$2"
            shift 2
            ;;
        --user-data-dir)
            USER_DATA_DIR="$2"
            shift 2
            ;;
        *)
            CHROME_BINARY="$1"
            shift
            ;;
    esac
done

if [ -z "$CHROME_BINARY" ]; then
    CHROME_BINARY="./out/Antidetect/chrome"
fi

if [ -z "$USER_DATA_DIR" ]; then
    USER_DATA_DIR="/tmp/antidetect-profiles/$PROFILE_NAME"
fi

# Generate deterministic seed from profile name
SEED=$(echo -n "$PROFILE_NAME" | md5sum | head -c 16)
SEED_DEC=$((16#${SEED}))

echo "=== Antidetect Browser Launcher ==="
echo "Profile:  $PROFILE_NAME"
echo "Binary:   $CHROME_BINARY"
echo "Data dir: $USER_DATA_DIR"
echo "Seed:     $SEED_DEC"
echo ""

exec "$CHROME_BINARY" \
    --user-data-dir="$USER_DATA_DIR" \
    --antidetect-canvas-noise \
    --antidetect-canvas-noise-seed="$SEED_DEC" \
    --antidetect-webgl-noise \
    --antidetect-audio-noise \
    --antidetect-audio-noise-seed="$SEED_DEC" \
    --antidetect-client-rects-noise \
    --antidetect-client-rects-noise-seed="$SEED_DEC" \
    --antidetect-no-webdriver \
    --antidetect-webrtc-policy=disable_non_proxied_udp \
    --disable-background-networking \
    --disable-breakpad \
    --disable-component-update \
    --disable-default-apps \
    --disable-domain-reliability \
    --disable-features=AutofillServerCommunication \
    --no-default-browser-check \
    --no-first-run \
    "$@"
