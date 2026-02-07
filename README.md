# WDE — Chromium Antidetect Patch Set

Набор патчей для исходного кода Chromium, позволяющий создать антидетект-браузер с управлением фингерпринтами через командную строку.

## Покрытые вектора фингерпринтинга

| # | Патч | Вектор | Метод защиты |
|---|------|--------|-------------|
| 01 | `canvas-fingerprint-noise` | Canvas 2D fingerprint | Добавление шума в LSB пикселей при вызове `toDataURL()` / `toBlob()` |
| 02 | `webgl-fingerprint-spoofing` | WebGL renderer/vendor | Подмена `GL_RENDERER`, `GL_VENDOR`, `UNMASKED_*` строк |
| 03 | `audio-fingerprint-noise` | AudioContext fingerprint | Шум ~1e-7 в `getChannelData()` и `OfflineAudioContext` |
| 04 | `navigator-screen-spoofing` | Navigator & Screen API | Подмена UA, platform, hardwareConcurrency, deviceMemory, languages, screen size, colorDepth, pixelRatio |
| 05 | `webrtc-ip-leak-prevention` | WebRTC IP leak | Фильтрация ICE кандидатов, блокировка host/UDP кандидатов |
| 06 | `client-rects-noise` | ClientRects fingerprint | Шум ±0.001px в `getClientRects()` и `getBoundingClientRect()` |
| 07 | `font-enumeration-spoofing` | Font fingerprint | Белый список шрифтов, блокировка нелистованных |
| 08 | `timezone-spoofing` | Timezone fingerprint | Подмена `getTimezoneOffset()`, ICU timezone ID |
| 09 | `plugin-mimetype-spoofing` | Plugin enumeration | Контроль `navigator.plugins` и `navigator.mimeTypes` |
| 10 | `webdriver-detection-prevention` | Automation detection | Скрытие `navigator.webdriver`, удаление `$cdc_` переменных, блокировка DevTools discovery |

## Быстрый старт

### 1. Получить исходники Chromium

```bash
git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git
export PATH="$PATH:$(pwd)/depot_tools"
mkdir chromium && cd chromium
fetch --nohooks chromium
cd src
gclient runhooks
```

### 2. Применить патчи

```bash
git clone <this-repo> /path/to/wde
cd /path/to/chromium/src
/path/to/wde/scripts/apply_patches.sh .
```

### 3. Собрать

```bash
gn gen out/Antidetect --args="$(cat /path/to/wde/scripts/gn_args.txt)"
autoninja -C out/Antidetect chrome
```

### 4. Запустить

```bash
/path/to/wde/scripts/launch_antidetect.sh --profile my_profile ./out/Antidetect/chrome
```

## Все флаги командной строки

### Canvas

| Флаг | Описание | Пример |
|------|----------|--------|
| `--antidetect-canvas-noise` | Включить canvas noise | (без значения) |
| `--antidetect-canvas-noise-seed=N` | Seed для canvas noise (uint64) | `12345678` |

### WebGL

| Флаг | Описание | Пример |
|------|----------|--------|
| `--antidetect-webgl-vendor=STR` | Подменить GL_VENDOR | `Google Inc. (NVIDIA)` |
| `--antidetect-webgl-renderer=STR` | Подменить GL_RENDERER | `ANGLE (NVIDIA GeForce GTX 1080)` |
| `--antidetect-webgl-noise` | Включить WebGL readPixels noise | (без значения) |

### Audio

| Флаг | Описание | Пример |
|------|----------|--------|
| `--antidetect-audio-noise` | Включить audio noise | (без значения) |
| `--antidetect-audio-noise-seed=N` | Seed для audio noise (uint64) | `87654321` |

### Navigator / Screen

| Флаг | Описание | Пример |
|------|----------|--------|
| `--antidetect-user-agent=STR` | Подменить User-Agent | `Mozilla/5.0 ...` |
| `--antidetect-platform=STR` | Подменить navigator.platform | `Win32` |
| `--antidetect-hardware-concurrency=N` | Подменить кол-во ядер | `8` |
| `--antidetect-device-memory=N` | Подменить память (ГБ) | `8` |
| `--antidetect-languages=LIST` | Подменить языки (через запятую) | `en-US,en` |
| `--antidetect-screen-width=N` | Подменить ширину экрана | `1920` |
| `--antidetect-screen-height=N` | Подменить высоту экрана | `1080` |
| `--antidetect-screen-color-depth=N` | Подменить глубину цвета | `24` |
| `--antidetect-pixel-ratio=N` | Подменить device pixel ratio | `1.0` |

### WebRTC

| Флаг | Описание | Пример |
|------|----------|--------|
| `--antidetect-webrtc-policy=POLICY` | Политика WebRTC | `disable`, `disable_non_proxied_udp`, `default_public_interface_only` |

### ClientRects

| Флаг | Описание | Пример |
|------|----------|--------|
| `--antidetect-client-rects-noise` | Включить noise | (без значения) |
| `--antidetect-client-rects-noise-seed=N` | Seed | `11111111` |

### Timezone

| Флаг | Описание | Пример |
|------|----------|--------|
| `--antidetect-timezone-offset=N` | Смещение UTC в минутах | `180` (= UTC+3) |
| `--antidetect-timezone-id=STR` | IANA timezone ID | `America/New_York` |

### Шрифты

| Флаг | Описание | Пример |
|------|----------|--------|
| `--antidetect-font-list=LIST` | Белый список шрифтов | `Arial,Times New Roman,Courier New` |

### Плагины

| Флаг | Описание | Пример |
|------|----------|--------|
| `--antidetect-plugin-list=LIST` | Список плагинов (`;`-разделитель) | `Chrome PDF Viewer` или `none` |

### Автоматизация

| Флаг | Описание | Пример |
|------|----------|--------|
| `--antidetect-no-webdriver` | Скрыть navigator.webdriver | (без значения) |
| `--antidetect-do-not-track=N` | Установить DNT заголовок | `1` |

## Архитектура

```
patches/
├── 01-canvas-fingerprint-noise.patch      # Canvas 2D noise
├── 02-webgl-fingerprint-spoofing.patch    # WebGL vendor/renderer spoof
├── 03-audio-fingerprint-noise.patch       # AudioContext noise
├── 04-navigator-screen-spoofing.patch     # Navigator & Screen API
├── 05-webrtc-ip-leak-prevention.patch     # WebRTC IP leak prevention
├── 06-client-rects-noise.patch            # ClientRects/BoundingRect noise
├── 07-font-enumeration-spoofing.patch     # Font whitelist
├── 08-timezone-spoofing.patch             # Timezone offset & ID
├── 09-plugin-mimetype-spoofing.patch      # Plugin/MimeType control
├── 10-webdriver-detection-prevention.patch # Automation hiding
scripts/
├── apply_patches.sh                       # Скрипт применения патчей
├── launch_antidetect.sh                   # Скрипт запуска с профилем
└── gn_args.txt                            # Аргументы сборки GN
```

### Центральный модуль: `antidetect_utils.h`

Все патчи используют общий заголовочный файл `third_party/blink/renderer/core/antidetect/antidetect_utils.h`, который:

- Определяет все `constexpr char k*[]` имена command-line флагов
- Содержит inline-функции проверки включённости фич
- Реализует детерминистический PRNG (xorshift64*) для генерации noise
- Обеспечивает воспроизводимость fingerprint для одного seed (= один профиль)

### Принцип работы noise

Noise-функции (canvas, audio, clientRects) используют **детерминистический** PRNG с seed, привязанным к профилю:
- Один и тот же seed → один и тот же fingerprint (стабильность профиля)
- Разные seed → разные fingerprints (уникальность между профилями)
- Noise минимален (LSB для canvas, 1e-7 для audio, 0.001px для rects) — визуально незаметен

## Пример использования с профилями

```bash
# Профиль 1: Windows + NVIDIA
./out/Antidetect/chrome \
    --user-data-dir=/profiles/win-nvidia \
    --antidetect-canvas-noise \
    --antidetect-canvas-noise-seed=111 \
    --antidetect-audio-noise \
    --antidetect-audio-noise-seed=111 \
    --antidetect-client-rects-noise \
    --antidetect-client-rects-noise-seed=111 \
    --antidetect-user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
    --antidetect-platform="Win32" \
    --antidetect-hardware-concurrency=8 \
    --antidetect-device-memory=16 \
    --antidetect-languages="en-US,en" \
    --antidetect-screen-width=1920 \
    --antidetect-screen-height=1080 \
    --antidetect-webgl-vendor="Google Inc. (NVIDIA)" \
    --antidetect-webgl-renderer="ANGLE (NVIDIA, NVIDIA GeForce GTX 1080 Direct3D11 vs_5_0 ps_5_0)" \
    --antidetect-timezone-offset=-300 \
    --antidetect-timezone-id="America/New_York" \
    --antidetect-webrtc-policy=disable_non_proxied_udp \
    --antidetect-no-webdriver

# Профиль 2: macOS + Apple M1
./out/Antidetect/chrome \
    --user-data-dir=/profiles/mac-m1 \
    --antidetect-canvas-noise \
    --antidetect-canvas-noise-seed=222 \
    --antidetect-audio-noise \
    --antidetect-audio-noise-seed=222 \
    --antidetect-client-rects-noise \
    --antidetect-client-rects-noise-seed=222 \
    --antidetect-user-agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
    --antidetect-platform="MacIntel" \
    --antidetect-hardware-concurrency=10 \
    --antidetect-device-memory=8 \
    --antidetect-languages="en-GB,en" \
    --antidetect-screen-width=2560 \
    --antidetect-screen-height=1600 \
    --antidetect-pixel-ratio=2.0 \
    --antidetect-webgl-vendor="Google Inc. (Apple)" \
    --antidetect-webgl-renderer="ANGLE (Apple, Apple M1 Pro, OpenGL 4.1)" \
    --antidetect-timezone-offset=0 \
    --antidetect-timezone-id="Europe/London" \
    --antidetect-webrtc-policy=disable_non_proxied_udp \
    --antidetect-no-webdriver
```

## Совместимость

Патчи разработаны для Chromium **120+** (stable). При применении к другим версиям могут потребоваться ручные правки из-за изменений в upstream API.

## Лицензия

Патчи распространяются под той же лицензией, что и Chromium (BSD 3-Clause).
