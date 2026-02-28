#!/bin/bash
###############################################################################
# Quick setup script for Hetzner / any Ubuntu 22.04 VPS
#
# Run this on a fresh server:
#   ssh root@YOUR_SERVER
#   curl -sSL <raw_url> | bash
#
# Or manually:
#   git clone <wde-repo> ~/wde
#   bash ~/wde/scripts/setup_hetzner.sh
#
# After the build completes (~2-6 hours), download the archive:
#   scp root@YOUR_SERVER:/home/user/chromium-build/antidetect-browser-*.tar.gz .
###############################################################################

set -euo pipefail

echo "=== WDE Quick Server Setup ==="
echo ""

# Create a non-root user if needed
if [ "$(id -u)" = "0" ]; then
    echo "[*] Running as root, setting up build user..."
    useradd -m -s /bin/bash builder 2>/dev/null || true
    echo "builder ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/builder

    # Increase swap for low-RAM servers
    TOTAL_RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
    if [ "$TOTAL_RAM_MB" -lt 32000 ]; then
        echo "[*] Adding 16 GB swap..."
        if [ ! -f /swapfile ]; then
            fallocate -l 16G /swapfile
            chmod 600 /swapfile
            mkswap /swapfile
            swapon /swapfile
            echo '/swapfile none swap sw 0 0' >> /etc/fstab
        fi
    fi

    # Optimize for build
    echo "[*] Tuning system for build..."
    sysctl -w vm.swappiness=10 2>/dev/null || true
    sysctl -w fs.file-max=500000 2>/dev/null || true
    ulimit -n 500000 2>/dev/null || true
fi

# Clone or update WDE repo
WDE_DIR="/home/builder/wde"
if [ -d "$WDE_DIR" ]; then
    echo "[*] WDE repo exists, pulling updates..."
    cd "$WDE_DIR" && git pull || true
else
    echo "[*] Clone the WDE repo to $WDE_DIR"
    echo "    git clone <your-wde-repo-url> $WDE_DIR"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Now run the build:"
echo "  su - builder"
echo "  cd ~/wde"
echo "  ./scripts/build_server.sh 2>&1 | tee ~/build.log"
echo ""
echo "Or run in background (recommended for long builds):"
echo "  nohup ./scripts/build_server.sh > ~/build.log 2>&1 &"
echo "  tail -f ~/build.log"
echo ""
echo "Expected build time:"
echo "  - Hetzner AX41 (Ryzen 5 3600, 64 GB): ~2-3 hours"
echo "  - Hetzner CPX41 (8 vCPU, 16 GB):      ~4-5 hours"
echo "  - Any 4-core VPS:                       ~6-8 hours"
echo ""
