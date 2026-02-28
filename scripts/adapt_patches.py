#!/usr/bin/env python3
"""
WDE Patch Adaptation Helper

When patches fail to apply because Chromium code shifted,
this script helps find the correct insertion points.

Usage:
    python3 scripts/adapt_patches.py /path/to/chromium/src

It will:
1. Try to apply each patch
2. For failing patches, search for the context (function signatures, includes)
3. Report exactly where to insert the antidetect code
4. Optionally auto-fix line offsets when the change is trivial
"""

import os
import re
import subprocess
import sys
from pathlib import Path

# Functions/patterns we hook into — used to locate insertion points
# even if line numbers shifted
HOOK_SIGNATURES = {
    "01-canvas-fingerprint-noise.patch": [
        {
            "file": "third_party/blink/renderer/core/html/canvas/html_canvas_element.cc",
            "find": r"String HTMLCanvasElement::ToDataURLInternal\(",
            "context": "Insert canvas noise BEFORE the base64 encoding return statement",
            "search_near": r'return String\("data:"',
        },
    ],
    "02-webgl-fingerprint-spoofing.patch": [
        {
            "file": "third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc",
            "find": r"ScriptValue WebGLRenderingContextBase::getParameter\(",
            "context": "Add getParameterAntidetect() method after getParameter()",
        },
        {
            "file": "gpu/config/gpu_info.cc",
            "find": r"void GPUInfo::EnumerateFields\(",
            "context": "Add ApplyAntidetectOverrides() method after EnumerateFields()",
        },
    ],
    "03-audio-fingerprint-noise.patch": [
        {
            "file": "third_party/blink/renderer/modules/webaudio/audio_buffer.cc",
            "find": r"NotShared<DOMFloat32Array> AudioBuffer::getChannelData\(",
            "context": "Add ApplyAudioNoise() call before returning channel data",
        },
        {
            "file": "third_party/blink/renderer/modules/webaudio/offline_audio_context.cc",
            "find": r"void OfflineAudioContext::FireCompletionEvent\(",
            "context": "Add noise to rendered buffer before firing completion",
        },
    ],
    "04-navigator-screen-spoofing.patch": [
        {
            "file": "third_party/blink/renderer/core/frame/navigator.cc",
            "find": r"String Navigator::userAgent\(\) const",
            "context": "Add command-line override at the start of userAgent()",
        },
        {
            "file": "third_party/blink/renderer/core/frame/navigator.cc",
            "find": r"String Navigator::platform\(\) const",
            "context": "Add command-line override at the start of platform()",
        },
        {
            "file": "third_party/blink/renderer/core/frame/navigator_concurrent_hardware.cc",
            "find": r"unsigned NavigatorConcurrentHardware::hardwareConcurrency\(\) const",
            "context": "Add override before NumberOfProcessors() call",
        },
        {
            "file": "third_party/blink/renderer/core/frame/screen.cc",
            "find": r"unsigned Screen::colorDepth\(\) const",
            "context": "Add override at start of colorDepth()",
        },
        {
            "file": "third_party/blink/renderer/core/frame/screen.cc",
            "find": r"int Screen::width\(\) const",
            "context": "Add override at start of width()",
        },
        {
            "file": "third_party/blink/renderer/core/frame/screen.cc",
            "find": r"int Screen::height\(\) const",
            "context": "Add override at start of height()",
        },
    ],
    "05-webrtc-ip-leak-prevention.patch": [
        {
            "file": "third_party/blink/renderer/modules/peerconnection/rtc_peer_connection.cc",
            "find": r"RTCPeerConnection\* RTCPeerConnection::Create\(",
            "context": "Add WebRTC policy override in Create()",
        },
    ],
    "06-client-rects-noise.patch": [
        {
            "file": "third_party/blink/renderer/core/dom/element.cc",
            "find": r"DOMRectList\* Element::getClientRects\(\)",
            "context": "Add noise to client rects before returning",
        },
        {
            "file": "third_party/blink/renderer/core/dom/element.cc",
            "find": r"DOMRect\* Element::getBoundingClientRect\(\)",
            "context": "Add noise to bounding rect before returning",
        },
    ],
    "07-font-enumeration-spoofing.patch": [
        {
            "file": "third_party/blink/renderer/platform/fonts/font_cache.cc",
            "find": r"const SimpleFontData\* FontCache::GetFontData\(",
            "context": "Add font whitelist check before font lookup",
        },
    ],
    "08-timezone-spoofing.patch": [
        {
            "file": "third_party/icu/source/i18n/timezone.cpp",
            "find": r"TimeZone::detectHostTimeZone\(\)",
            "context": "Add timezone ID override at start of detectHostTimeZone()",
        },
    ],
    "10-webdriver-detection-prevention.patch": [
        {
            "file": "third_party/blink/renderer/core/frame/navigator_automation_information.cc",
            "find": r"bool NavigatorAutomationInformation::webdriver\(",
            "context": "Add early return false when --antidetect-no-webdriver is set",
        },
    ],
}


def run(cmd, cwd=None):
    """Run a command and return (returncode, stdout)."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd
    )
    return result.returncode, result.stdout, result.stderr


def find_line(filepath, pattern):
    """Find line number matching regex pattern in file."""
    try:
        with open(filepath, "r", errors="replace") as f:
            for i, line in enumerate(f, 1):
                if re.search(pattern, line):
                    return i
    except FileNotFoundError:
        return None
    return None


def check_patch(chromium_src, patch_path):
    """Try to apply a patch and return success status."""
    rc, _, stderr = run(f"git apply --check '{patch_path}'", cwd=chromium_src)
    if rc == 0:
        return True, ""

    # Try fuzzy
    rc, _, stderr = run(f"git apply --check -C0 '{patch_path}'", cwd=chromium_src)
    if rc == 0:
        return True, "(fuzzy match)"

    return False, stderr


def analyze_patch(chromium_src, patch_name):
    """For a failing patch, find where the hooks should go."""
    hooks = HOOK_SIGNATURES.get(patch_name, [])
    results = []

    for hook in hooks:
        filepath = os.path.join(chromium_src, hook["file"])
        line = find_line(filepath, hook["find"])

        if line:
            results.append({
                "file": hook["file"],
                "pattern": hook["find"],
                "found_at_line": line,
                "context": hook["context"],
                "status": "FOUND",
            })
        else:
            # Try broader search
            if os.path.exists(filepath):
                results.append({
                    "file": hook["file"],
                    "pattern": hook["find"],
                    "found_at_line": None,
                    "context": hook["context"],
                    "status": "PATTERN_NOT_FOUND (file exists, function may be renamed)",
                })
            else:
                results.append({
                    "file": hook["file"],
                    "pattern": hook["find"],
                    "found_at_line": None,
                    "context": hook["context"],
                    "status": "FILE_NOT_FOUND",
                })

    return results


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <chromium_src_dir>")
        sys.exit(1)

    chromium_src = os.path.abspath(sys.argv[1])
    script_dir = os.path.dirname(os.path.abspath(__file__))
    patch_dir = os.path.join(script_dir, "..", "patches")

    if not os.path.isdir(chromium_src):
        print(f"Error: {chromium_src} is not a directory")
        sys.exit(1)

    print("=" * 70)
    print("WDE Patch Adaptation Helper")
    print(f"Chromium src: {chromium_src}")
    print(f"Patches dir:  {patch_dir}")
    print("=" * 70)
    print()

    patches = sorted(
        [f for f in os.listdir(patch_dir) if f.endswith(".patch")]
    )

    ok_count = 0
    fail_count = 0
    all_analysis = []

    for patch_name in patches:
        patch_path = os.path.join(patch_dir, patch_name)
        success, note = check_patch(chromium_src, patch_path)

        if success:
            print(f"  OK   {patch_name} {note}")
            ok_count += 1
        else:
            print(f"  FAIL {patch_name}")
            fail_count += 1
            analysis = analyze_patch(chromium_src, patch_name)
            all_analysis.append((patch_name, analysis))

    print()
    print(f"Results: {ok_count} OK, {fail_count} FAILED")
    print()

    if all_analysis:
        print("=" * 70)
        print("ADAPTATION GUIDE FOR FAILED PATCHES")
        print("=" * 70)
        for patch_name, hooks in all_analysis:
            print(f"\n--- {patch_name} ---")
            for h in hooks:
                print(f"  File:    {h['file']}")
                print(f"  Pattern: {h['pattern']}")
                if h["found_at_line"]:
                    print(f"  Line:    {h['found_at_line']} <-- INSERT HERE")
                else:
                    print(f"  Line:    NOT FOUND")
                print(f"  Status:  {h['status']}")
                print(f"  Action:  {h['context']}")
                print()

        print("=" * 70)
        print("To fix: update the @@ line offsets in each .patch file,")
        print("or manually insert the code at the locations shown above.")
        print("The antidetect code blocks in each patch are clearly marked")
        print("with '// Antidetect:' comments.")
        print("=" * 70)


if __name__ == "__main__":
    main()
