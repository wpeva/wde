###############################################################################
# WDE Chromium Antidetect — Build Container
#
# Multi-stage build:
#   Stage 1: Full Chromium build environment (~250 GB during build)
#   Stage 2: Minimal runtime with only the browser binary (~2 GB)
#
# Usage:
#   # Build (takes 3-6 hours first time, ~30 min for incremental):
#   docker build --build-arg CHROMIUM_VERSION=131.0.6778.69 -t wde-browser .
#
#   # Run:
#   docker run -it --rm \
#     -e DISPLAY=$DISPLAY \
#     -v /tmp/.X11-unix:/tmp/.X11-unix \
#     wde-browser --profile my_profile
#
#   # Extract binary from container:
#   docker create --name tmp wde-browser
#   docker cp tmp:/browser/. ./antidetect-browser/
#   docker rm tmp
###############################################################################

# ============================================================================
# Stage 1: Build
# ============================================================================
FROM ubuntu:22.04 AS builder

ARG CHROMIUM_VERSION=""
ARG BUILD_JOBS=""
ARG DEBIAN_FRONTEND=noninteractive

# System deps
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    git curl wget python3 python3-pip ca-certificates \
    build-essential clang lld \
    pkg-config libglib2.0-dev libdbus-1-dev libnss3-dev \
    libatk1.0-dev libatk-bridge2.0-dev libcups2-dev \
    libdrm-dev libxkbcommon-dev libxcomposite-dev \
    libxdamage-dev libxrandr-dev libgbm-dev libpango1.0-dev \
    libcairo2-dev libasound2-dev libpulse-dev libxtst-dev \
    gperf bison flex zip unzip lsb-release sudo \
    && rm -rf /var/lib/apt/lists/*

# depot_tools
RUN git clone --depth=1 https://chromium.googlesource.com/chromium/tools/depot_tools.git /depot_tools
ENV PATH="/depot_tools:${PATH}"

WORKDIR /build

# Fetch Chromium (shallow — no git history)
RUN mkdir chromium && cd chromium && \
    fetch --nohooks --no-history chromium

# Checkout specific version if requested
RUN if [ -n "$CHROMIUM_VERSION" ]; then \
        cd /build/chromium/src && \
        git fetch --depth=1 origin "refs/tags/$CHROMIUM_VERSION:refs/tags/$CHROMIUM_VERSION" && \
        git checkout "$CHROMIUM_VERSION"; \
    fi

# Install Chromium's own build deps & run hooks
RUN cd /build/chromium/src && \
    ./build/install-build-deps.sh --no-prompt --no-arm --no-chromeos-fonts || true
RUN cd /build/chromium/src && \
    gclient runhooks

# Copy patches
COPY patches/ /wde/patches/
COPY scripts/ /wde/scripts/

# Apply patches
RUN cd /build/chromium/src && \
    mkdir -p third_party/blink/renderer/core/antidetect && \
    for patch in /wde/patches/*.patch; do \
        echo "Applying $(basename $patch)..." && \
        git apply --check "$patch" 2>/dev/null && git apply "$patch" && echo "  OK" || \
        (git apply --check -C0 "$patch" 2>/dev/null && git apply -C0 "$patch" && echo "  OK (fuzzy)") || \
        echo "  SKIP (needs manual fix)"; \
    done

# Generate build config
RUN cd /build/chromium/src && \
    gn gen out/Antidetect --args=' \
        is_debug = false \
        is_official_build = false \
        is_component_build = false \
        symbol_level = 0 \
        blink_symbol_level = 0 \
        v8_symbol_level = 0 \
        enable_nacl = false \
        treat_warnings_as_errors = false \
        proprietary_codecs = true \
        ffmpeg_branding = "Chrome" \
        is_clang = true \
        use_sysroot = true \
        chrome_pgo_phase = 0 \
    '

# Build
RUN cd /build/chromium/src && \
    JOBS=${BUILD_JOBS:-$(nproc)} && \
    ninja -j"$JOBS" -C out/Antidetect chrome

# ============================================================================
# Stage 2: Minimal runtime image
# ============================================================================
FROM ubuntu:22.04 AS runtime

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libpulse0 libxtst6 \
    libdbus-1-3 libx11-6 libxext6 libxfixes3 \
    libxcb1 libxshmfence1 fonts-liberation xdg-utils \
    ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /browser

# Copy built browser from builder stage
COPY --from=builder /build/chromium/src/out/Antidetect/chrome ./chrome
COPY --from=builder /build/chromium/src/out/Antidetect/*.pak ./
COPY --from=builder /build/chromium/src/out/Antidetect/icudtl.dat ./
COPY --from=builder /build/chromium/src/out/Antidetect/v8_context_snapshot.bin ./
COPY --from=builder /build/chromium/src/out/Antidetect/snapshot_blob.bin ./
COPY --from=builder /build/chromium/src/out/Antidetect/chrome_crashpad_handler ./
COPY --from=builder /build/chromium/src/out/Antidetect/libEGL.so ./
COPY --from=builder /build/chromium/src/out/Antidetect/libGLESv2.so ./
COPY --from=builder /build/chromium/src/out/Antidetect/locales/ ./locales/

# Copy launch script
COPY scripts/launch_antidetect.sh ./launch_antidetect.sh
RUN chmod +x ./launch_antidetect.sh && \
    sed -i 's|./out/Antidetect/chrome|/browser/chrome|g' ./launch_antidetect.sh

# Non-root user for security
RUN useradd -m -s /bin/bash browser
USER browser

ENTRYPOINT ["/browser/launch_antidetect.sh"]
CMD ["--profile", "default"]
