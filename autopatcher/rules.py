"""
WDE Antidetect Injection Rules

Each rule is a semantic description of WHERE and WHAT to inject.
Rules are version-agnostic — they find insertion points by function
signatures, not line numbers.

Guard strings prevent double-application.
"""

from engine import Injection

# ===========================================================================
# Shared: antidetect_utils.h (new file, always created)
# ===========================================================================

ANTIDETECT_UTILS_H = r'''// Copyright 2024 AntiBrowser Authors. All rights reserved.
// Antidetect utilities for browser fingerprint masking

#ifndef THIRD_PARTY_BLINK_RENDERER_CORE_ANTIDETECT_ANTIDETECT_UTILS_H_
#define THIRD_PARTY_BLINK_RENDERER_CORE_ANTIDETECT_ANTIDETECT_UTILS_H_

#include <cstdint>
#include <cstring>
#include <string>

#include "base/command_line.h"
#include "base/rand_util.h"
#include "base/strings/string_number_conversions.h"

namespace antidetect {

// Command-line switches
constexpr char kCanvasNoise[] = "antidetect-canvas-noise";
constexpr char kCanvasNoiseSeed[] = "antidetect-canvas-noise-seed";
constexpr char kWebglVendor[] = "antidetect-webgl-vendor";
constexpr char kWebglRenderer[] = "antidetect-webgl-renderer";
constexpr char kWebglNoise[] = "antidetect-webgl-noise";
constexpr char kAudioNoise[] = "antidetect-audio-noise";
constexpr char kAudioNoiseSeed[] = "antidetect-audio-noise-seed";
constexpr char kClientRectsNoise[] = "antidetect-client-rects-noise";
constexpr char kClientRectsNoiseSeed[] = "antidetect-client-rects-noise-seed";
constexpr char kUserAgent[] = "antidetect-user-agent";
constexpr char kPlatform[] = "antidetect-platform";
constexpr char kHardwareConcurrency[] = "antidetect-hardware-concurrency";
constexpr char kDeviceMemory[] = "antidetect-device-memory";
constexpr char kLanguages[] = "antidetect-languages";
constexpr char kScreenWidth[] = "antidetect-screen-width";
constexpr char kScreenHeight[] = "antidetect-screen-height";
constexpr char kScreenColorDepth[] = "antidetect-screen-color-depth";
constexpr char kPixelRatio[] = "antidetect-pixel-ratio";
constexpr char kTimezoneOffset[] = "antidetect-timezone-offset";
constexpr char kTimezoneId[] = "antidetect-timezone-id";
constexpr char kWebrtcPolicy[] = "antidetect-webrtc-policy";
constexpr char kFontList[] = "antidetect-font-list";
constexpr char kPluginList[] = "antidetect-plugin-list";
constexpr char kNoWebdriver[] = "antidetect-no-webdriver";
constexpr char kDoNotTrack[] = "antidetect-do-not-track";

inline bool HasSwitch(const char* name) {
  return base::CommandLine::ForCurrentProcess()->HasSwitch(name);
}

inline std::string GetSwitch(const char* name) {
  return base::CommandLine::ForCurrentProcess()->GetSwitchValueASCII(name);
}

inline uint64_t GetSeedSwitch(const char* name) {
  uint64_t seed = 0;
  if (HasSwitch(name)) {
    base::StringToUint64(GetSwitch(name), &seed);
  }
  if (seed == 0) {
    static uint64_t session_seed = base::RandUint64();
    seed = session_seed;
  }
  return seed;
}

// xorshift64* deterministic PRNG
inline uint64_t Xorshift64(uint64_t& state) {
  state ^= state >> 12;
  state ^= state << 25;
  state ^= state >> 27;
  return state * 0x2545F4914F6CDD1DULL;
}

// ---- Canvas ----
inline bool IsCanvasNoiseEnabled() { return HasSwitch(kCanvasNoise); }
inline uint64_t GetCanvasNoiseSeed() { return GetSeedSwitch(kCanvasNoiseSeed); }

inline void AddCanvasNoise(uint8_t* data, size_t len, uint64_t seed) {
  if (!data || len == 0) return;
  uint64_t state = seed ? seed : 0xdeadbeefcafe1234ULL;
  for (size_t i = 0; i < len; i += 4) {
    uint64_t rng = Xorshift64(state);
    if ((rng & 0xF) < 2) {
      uint8_t ch = (rng >> 4) % 3;
      if (i + ch < len) data[i + ch] ^= 1;
    }
  }
}

// ---- Audio ----
inline bool IsAudioNoiseEnabled() { return HasSwitch(kAudioNoise); }
inline uint64_t GetAudioNoiseSeed() { return GetSeedSwitch(kAudioNoiseSeed); }

inline void AddAudioNoise(float* data, size_t len, uint64_t seed) {
  if (!data || len == 0) return;
  uint64_t state = seed ? seed : 0xcafebeef12345678ULL;
  for (size_t i = 0; i < len; ++i) {
    uint64_t rng = Xorshift64(state);
    if ((rng & 0x7) == 0) {
      double noise = (static_cast<double>(rng >> 32) / 0xFFFFFFFF - 0.5) * 2e-7;
      data[i] += static_cast<float>(noise);
    }
  }
}

// ---- ClientRects ----
inline bool IsClientRectsNoiseEnabled() { return HasSwitch(kClientRectsNoise); }
inline uint64_t GetClientRectsNoiseSeed() { return GetSeedSwitch(kClientRectsNoiseSeed); }

inline double ClientRectsNoise(double val, uint64_t seed) {
  uint64_t state = seed ^ static_cast<uint64_t>(val * 1000000.0);
  uint64_t rng = Xorshift64(state);
  return (static_cast<double>(rng & 0xFFFFF) / 0xFFFFF - 0.5) * 0.002;
}

}  // namespace antidetect
#endif
'''

ANTIDETECT_BUILD_GN = '''import("//third_party/blink/renderer/core/core.gni")
blink_core_sources("antidetect") {
  sources = [ "antidetect_utils.h" ]
  deps = [ "//base", "//third_party/blink/renderer/platform" ]
}
'''

# ===========================================================================
# The includes we add everywhere
# ===========================================================================
INC_UTILS = '#include "third_party/blink/renderer/core/antidetect/antidetect_utils.h"'
INC_CMD = '#include "base/command_line.h"'
INC_RAND = '#include "base/rand_util.h"'
INC_STRNUM = '#include "base/strings/string_number_conversions.h"'
INC_STRSPLIT = '#include "base/strings/string_split.h"'

# ===========================================================================
# All injection rules
# ===========================================================================

RULES: list[Injection] = [

    # ===== 01: CANVAS NOISE =====
    Injection(
        id="canvas-noise-toDataURL",
        description="Add noise to canvas toDataURL output",
        file="third_party/blink/renderer/core/html/canvas/html_canvas_element.cc",
        anchor=r'String HTMLCanvasElement::ToDataURLInternal\b',
        position="before_return",
        guard="// Antidetect: canvas noise",
        includes=[INC_UTILS, INC_CMD, INC_RAND],
        code="""
  // Antidetect: canvas noise
  if (antidetect::IsCanvasNoiseEnabled()) {
    antidetect::AddCanvasNoise(
        const_cast<uint8_t*>(encoded_image.data()),
        encoded_image.size(),
        antidetect::GetCanvasNoiseSeed());
  }
""",
    ),

    # ===== 02: WEBGL VENDOR/RENDERER SPOOFING =====
    Injection(
        id="webgl-getParameter-vendor",
        description="Spoof GL_VENDOR in WebGL getParameter",
        file="third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc",
        anchor=r'ScriptValue WebGLRenderingContextBase::getParameter\b',
        position="start_of_function",
        guard="// Antidetect: webgl vendor/renderer",
        includes=[INC_UTILS, INC_CMD],
        code="""
  // Antidetect: webgl vendor/renderer
  if (pname == GL_RENDERER && antidetect::HasSwitch(antidetect::kWebglRenderer)) {
    return WebGLAny(script_state,
        String::FromUTF8(antidetect::GetSwitch(antidetect::kWebglRenderer)));
  }
  if (pname == GL_VENDOR && antidetect::HasSwitch(antidetect::kWebglVendor)) {
    return WebGLAny(script_state,
        String::FromUTF8(antidetect::GetSwitch(antidetect::kWebglVendor)));
  }
""",
    ),

    Injection(
        id="webgl-unmasked-vendor",
        description="Spoof UNMASKED_VENDOR_WEBGL",
        file="third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc",
        anchor=r'UNMASKED_VENDOR_WEBGL',
        anchor_context=r'getParameter|GetParameter',
        position="before_line",
        guard="// Antidetect: unmasked vendor",
        includes=[INC_UTILS],
        code="""
    // Antidetect: unmasked vendor
    if (antidetect::HasSwitch(antidetect::kWebglVendor)) {
      return WebGLAny(script_state,
          String::FromUTF8(antidetect::GetSwitch(antidetect::kWebglVendor)));
    }
""",
    ),

    Injection(
        id="webgl-unmasked-renderer",
        description="Spoof UNMASKED_RENDERER_WEBGL",
        file="third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc",
        anchor=r'UNMASKED_RENDERER_WEBGL',
        anchor_context=r'getParameter|GetParameter',
        position="before_line",
        guard="// Antidetect: unmasked renderer",
        includes=[INC_UTILS],
        code="""
    // Antidetect: unmasked renderer
    if (antidetect::HasSwitch(antidetect::kWebglRenderer)) {
      return WebGLAny(script_state,
          String::FromUTF8(antidetect::GetSwitch(antidetect::kWebglRenderer)));
    }
""",
    ),

    # ===== 03: AUDIO NOISE =====
    Injection(
        id="audio-getChannelData-noise",
        description="Add noise to AudioBuffer::getChannelData",
        file="third_party/blink/renderer/modules/webaudio/audio_buffer.cc",
        anchor=r'DOMFloat32Array.*AudioBuffer::getChannelData\b',
        position="before_return",
        guard="// Antidetect: audio noise",
        includes=[INC_UTILS, INC_CMD, INC_RAND],
        code="""
  // Antidetect: audio noise
  if (antidetect::IsAudioNoiseEnabled()) {
    antidetect::AddAudioNoise(
        static_cast<float*>(channel_data->Data()),
        channel_data->length(),
        antidetect::GetAudioNoiseSeed());
  }
""",
    ),

    Injection(
        id="audio-offline-noise",
        description="Add noise to OfflineAudioContext rendered buffer",
        file="third_party/blink/renderer/modules/webaudio/offline_audio_context.cc",
        anchor=r'void OfflineAudioContext::FireCompletionEvent\b',
        position="start_of_function",
        guard="// Antidetect: offline audio noise",
        includes=[INC_UTILS, INC_CMD, INC_RAND],
        code="""
  // Antidetect: offline audio noise
  if (antidetect::IsAudioNoiseEnabled() && rendered_buffer) {
    for (unsigned ch = 0; ch < rendered_buffer->numberOfChannels(); ++ch) {
      auto* cdata = rendered_buffer->getChannelData(ch);
      antidetect::AddAudioNoise(
          static_cast<float*>(cdata->Data()), cdata->length(),
          antidetect::GetAudioNoiseSeed() ^ ch);
    }
  }
""",
    ),

    # ===== 04: NAVIGATOR SPOOFING =====
    Injection(
        id="navigator-useragent",
        description="Override navigator.userAgent",
        file="third_party/blink/renderer/core/frame/navigator.cc",
        anchor=r'String Navigator::userAgent\(\) const',
        position="start_of_function",
        guard="// Antidetect: user agent",
        includes=[INC_UTILS, INC_CMD],
        code="""
  // Antidetect: user agent
  if (antidetect::HasSwitch(antidetect::kUserAgent))
    return String::FromUTF8(antidetect::GetSwitch(antidetect::kUserAgent));
""",
    ),

    Injection(
        id="navigator-platform",
        description="Override navigator.platform",
        file="third_party/blink/renderer/core/frame/navigator.cc",
        anchor=r'String Navigator::platform\(\) const',
        position="start_of_function",
        guard="// Antidetect: platform",
        includes=[INC_UTILS, INC_CMD],
        code="""
  // Antidetect: platform
  if (antidetect::HasSwitch(antidetect::kPlatform))
    return String::FromUTF8(antidetect::GetSwitch(antidetect::kPlatform));
""",
    ),

    Injection(
        id="navigator-hardwareConcurrency",
        description="Override navigator.hardwareConcurrency",
        file="third_party/blink/renderer/core/frame/navigator_concurrent_hardware.cc",
        anchor=r'unsigned NavigatorConcurrentHardware::hardwareConcurrency\b',
        position="start_of_function",
        guard="// Antidetect: hardwareConcurrency",
        includes=[INC_UTILS, INC_CMD, INC_STRNUM],
        code="""
  // Antidetect: hardwareConcurrency
  if (antidetect::HasSwitch(antidetect::kHardwareConcurrency)) {
    unsigned v = 0;
    if (base::StringToUint(antidetect::GetSwitch(antidetect::kHardwareConcurrency), &v) && v > 0)
      return v;
  }
""",
    ),

    Injection(
        id="navigator-deviceMemory",
        description="Override navigator.deviceMemory",
        file="third_party/blink/renderer/core/frame/navigator_device_memory.cc",
        anchor=r'float NavigatorDeviceMemory::deviceMemory\b',
        position="start_of_function",
        guard="// Antidetect: deviceMemory",
        includes=[INC_UTILS, INC_CMD, INC_STRNUM],
        code="""
  // Antidetect: deviceMemory
  if (antidetect::HasSwitch(antidetect::kDeviceMemory)) {
    double v = 0;
    if (base::StringToDouble(antidetect::GetSwitch(antidetect::kDeviceMemory), &v) && v > 0)
      return static_cast<float>(v);
  }
""",
    ),

    Injection(
        id="navigator-languages",
        description="Override navigator.languages",
        file="third_party/blink/renderer/core/frame/navigator_language.cc",
        anchor=r'Vector<String>.*NavigatorLanguage::languages\b',
        position="start_of_function",
        guard="// Antidetect: languages",
        includes=[INC_UTILS, INC_CMD, INC_STRSPLIT],
        code="""
  // Antidetect: languages
  if (antidetect::HasSwitch(antidetect::kLanguages)) {
    Vector<String> result;
    for (const auto& p : base::SplitString(
             antidetect::GetSwitch(antidetect::kLanguages),
             ",", base::TRIM_WHITESPACE, base::SPLIT_WANT_NONEMPTY))
      result.push_back(String::FromUTF8(p));
    if (!result.empty()) return result;
  }
""",
    ),

    # ===== 04b: SCREEN SPOOFING =====
    Injection(
        id="screen-width",
        description="Override screen.width",
        file="third_party/blink/renderer/core/frame/screen.cc",
        anchor=r'int Screen::width\(\) const',
        position="start_of_function",
        guard="// Antidetect: screen width",
        includes=[INC_UTILS, INC_CMD, INC_STRNUM],
        code="""
  // Antidetect: screen width
  if (antidetect::HasSwitch(antidetect::kScreenWidth)) {
    int v = 0;
    if (base::StringToInt(antidetect::GetSwitch(antidetect::kScreenWidth), &v))
      return v;
  }
""",
    ),

    Injection(
        id="screen-height",
        description="Override screen.height",
        file="third_party/blink/renderer/core/frame/screen.cc",
        anchor=r'int Screen::height\(\) const',
        position="start_of_function",
        guard="// Antidetect: screen height",
        includes=[INC_UTILS, INC_CMD, INC_STRNUM],
        code="""
  // Antidetect: screen height
  if (antidetect::HasSwitch(antidetect::kScreenHeight)) {
    int v = 0;
    if (base::StringToInt(antidetect::GetSwitch(antidetect::kScreenHeight), &v))
      return v;
  }
""",
    ),

    Injection(
        id="screen-colorDepth",
        description="Override screen.colorDepth",
        file="third_party/blink/renderer/core/frame/screen.cc",
        anchor=r'unsigned Screen::colorDepth\(\) const',
        position="start_of_function",
        guard="// Antidetect: colorDepth",
        includes=[INC_UTILS, INC_CMD, INC_STRNUM],
        code="""
  // Antidetect: colorDepth
  if (antidetect::HasSwitch(antidetect::kScreenColorDepth)) {
    unsigned v = 0;
    if (base::StringToUint(antidetect::GetSwitch(antidetect::kScreenColorDepth), &v))
      return v;
  }
""",
    ),

    Injection(
        id="screen-pixelRatio",
        description="Override window.devicePixelRatio",
        file="third_party/blink/renderer/core/css/media_values.cc",
        anchor=r'double MediaValues::CalculateDevicePixelRatio\b',
        position="start_of_function",
        guard="// Antidetect: pixelRatio",
        includes=[INC_UTILS, INC_CMD, INC_STRNUM],
        code="""
  // Antidetect: pixelRatio
  if (antidetect::HasSwitch(antidetect::kPixelRatio)) {
    double v = 0;
    if (base::StringToDouble(antidetect::GetSwitch(antidetect::kPixelRatio), &v) && v > 0)
      return v;
  }
""",
    ),

    # ===== 05: WEBRTC =====
    Injection(
        id="webrtc-policy",
        description="WebRTC IP leak prevention",
        file="third_party/blink/renderer/modules/peerconnection/rtc_peer_connection.cc",
        anchor=r'RTCPeerConnection\* RTCPeerConnection::Create\b',
        position="start_of_function",
        guard="// Antidetect: webrtc policy",
        includes=[INC_UTILS, INC_CMD],
        code="""
  // Antidetect: webrtc policy
  if (antidetect::HasSwitch(antidetect::kWebrtcPolicy)) {
    std::string policy = antidetect::GetSwitch(antidetect::kWebrtcPolicy);
    if (policy == "disable") {
      exception_state.ThrowDOMException(
          DOMExceptionCode::kNotSupportedError, "WebRTC disabled.");
      return nullptr;
    }
  }
""",
    ),

    # ===== 06: CLIENT RECTS NOISE =====
    Injection(
        id="element-getClientRects-noise",
        description="Add noise to Element::getClientRects",
        file="third_party/blink/renderer/core/dom/element.cc",
        anchor=r'DOMRectList\* Element::getClientRects\b',
        position="before_return",
        guard="// Antidetect: clientRects noise",
        includes=[INC_UTILS, INC_CMD, INC_RAND],
        code="""
  // Antidetect: clientRects noise
  if (antidetect::IsClientRectsNoiseEnabled()) {
    uint64_t seed = antidetect::GetClientRectsNoiseSeed();
    DOMRectList* noisy = MakeGarbageCollected<DOMRectList>();
    for (unsigned i = 0; i < rects->length(); ++i) {
      DOMRect* r = rects->item(i);
      noisy->Append(DOMRect::Create(
          r->x() + antidetect::ClientRectsNoise(r->x(), seed),
          r->y() + antidetect::ClientRectsNoise(r->y(), seed ^ 1),
          r->width() + antidetect::ClientRectsNoise(r->width(), seed ^ 2),
          r->height() + antidetect::ClientRectsNoise(r->height(), seed ^ 3)));
    }
    return noisy;
  }
""",
    ),

    Injection(
        id="element-getBoundingClientRect-noise",
        description="Add noise to Element::getBoundingClientRect",
        file="third_party/blink/renderer/core/dom/element.cc",
        anchor=r'DOMRect\* Element::getBoundingClientRect\b',
        position="before_return",
        guard="// Antidetect: boundingRect noise",
        includes=[INC_UTILS],
        code="""
  // Antidetect: boundingRect noise
  if (antidetect::IsClientRectsNoiseEnabled()) {
    uint64_t seed = antidetect::GetClientRectsNoiseSeed();
    return DOMRect::Create(
        rect->x() + antidetect::ClientRectsNoise(rect->x(), seed),
        rect->y() + antidetect::ClientRectsNoise(rect->y(), seed ^ 1),
        rect->width() + antidetect::ClientRectsNoise(rect->width(), seed ^ 2),
        rect->height() + antidetect::ClientRectsNoise(rect->height(), seed ^ 3));
  }
""",
    ),

    # ===== 07: FONT WHITELIST =====
    Injection(
        id="font-whitelist",
        description="Filter fonts through whitelist",
        file="third_party/blink/renderer/platform/fonts/font_cache.cc",
        anchor=r'SimpleFontData\* FontCache::GetFontData\b',
        position="start_of_function",
        guard="// Antidetect: font whitelist",
        includes=[INC_UTILS, INC_CMD, INC_STRSPLIT],
        code="""
  // Antidetect: font whitelist
  if (antidetect::HasSwitch(antidetect::kFontList)) {
    static bool init = false;
    static HashSet<String> allowed;
    if (!init) {
      for (const auto& f : base::SplitString(
               antidetect::GetSwitch(antidetect::kFontList),
               ",", base::TRIM_WHITESPACE, base::SPLIT_WANT_NONEMPTY))
        allowed.insert(String::FromUTF8(f).LowerASCII());
      for (const char* g : {"serif","sans-serif","monospace","cursive","fantasy","system-ui"})
        allowed.insert(String(g));
      init = true;
    }
    if (!allowed.Contains(family_name.LowerASCII()))
      return nullptr;
  }
""",
    ),

    # ===== 08: TIMEZONE =====
    Injection(
        id="timezone-offset",
        description="Override Date.getTimezoneOffset()",
        file="v8/src/builtins/builtins-date.cc",
        anchor=r'BUILTIN\(DatePrototypeGetTimezoneOffset\)',
        position="before_return",
        guard="// Antidetect: timezone offset",
        includes=[INC_CMD, INC_STRNUM],
        code="""
  // Antidetect: timezone offset
  {
    const auto* cmd = base::CommandLine::ForCurrentProcess();
    if (cmd->HasSwitch("antidetect-timezone-offset")) {
      int offset = 0;
      if (base::StringToInt(cmd->GetSwitchValueASCII("antidetect-timezone-offset"), &offset))
        return *isolate->factory()->NewNumber(-offset);
    }
  }
""",
    ),

    Injection(
        id="timezone-icu-id",
        description="Override ICU timezone ID",
        file="third_party/icu/source/i18n/timezone.cpp",
        anchor=r'TimeZone::detectHostTimeZone\b',
        position="start_of_function",
        guard="// Antidetect: timezone ID",
        includes=[INC_CMD],
        code="""
    // Antidetect: timezone ID
    {
      const auto* cmd = base::CommandLine::ForCurrentProcess();
      if (cmd->HasSwitch("antidetect-timezone-id")) {
        std::string tz = cmd->GetSwitchValueASCII("antidetect-timezone-id");
        if (!tz.empty()) {
          UnicodeString id = UnicodeString::fromUTF8(StringPiece(tz.data(), tz.size()));
          return TimeZone::createTimeZone(id);
        }
      }
    }
""",
    ),

    # ===== 10: WEBDRIVER =====
    Injection(
        id="webdriver-hide",
        description="Always return false for navigator.webdriver",
        file="third_party/blink/renderer/core/frame/navigator_automation_information.cc",
        anchor=r'bool NavigatorAutomationInformation::webdriver\b',
        position="start_of_function",
        guard="// Antidetect: hide webdriver",
        includes=[INC_UTILS, INC_CMD],
        code="""
  // Antidetect: hide webdriver
  if (antidetect::HasSwitch(antidetect::kNoWebdriver))
    return false;
""",
    ),

    Injection(
        id="cdc-rename",
        description="Rename $cdc_ ChromeDriver detection variable",
        file="chrome/test/chromedriver/js/call_function.js",
        anchor=r"var ELEMENT_KEY\s*=\s*'cdc_'",
        position="replace_line",
        guard="a]elements_",
        code="var ELEMENT_KEY = 'a]elements_';",
    ),
]
