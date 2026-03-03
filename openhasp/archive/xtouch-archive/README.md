# xtouch Screen Design Archive

> **Archived on**: 2026-02-26
> **Source Project**: [xperiments-in/xtouch](https://github.com/xperiments-in/xtouch) (GitHub)
> **Original Website**: https://xtouch.pro/ (archived via [Wayback Machine](https://web.archive.org/web/2025*/https://xtouch.pro/))
> **Author**: Pedro Casaubon (xperiments)
> **License**: GPL-3.0 (2.8" open source version)
> **Note**: The xtouch project appears to no longer be actively maintained. The xtouch.pro website is no longer functional. This archive preserves the screen designs for reference.

---

## Project Overview

The **xtouch** project was an aftermarket touch screen interface for BambuLab 3D printers (P1P, P1S, X1C, etc.). It came in two versions:

1. **xtouch 2.8"** - Open source, based on the ESP32-2432S028R board with a 2.8" ILI9341 TFT display (320x240 resolution)
2. **xtouch Pro 5"** - Closed source commercial product, 5" capacitive touch display (800x480 resolution)

---

## Directory Structure

```
xtouch-archive/
├── README.md                    # This file
├── XTOUCH_UI_VISUAL_SPEC.md    # Complete LVGL visual specification
├── xtouch-logo.png              # xtouch project logo/icon
├── 2.8-inch/                    # 2.8" open-source version
│   ├── screen-2-8-front.png     # Hardware - front view with screen
│   ├── screen-2-8-back.png      # Hardware - back view showing ESP32
│   ├── power-pinout.png         # JST 1.25 4-pin power connector pinout
│   ├── DS18B20_pinout.png       # DS18B20 temperature sensor pinout
│   └── ui-screens/              # SVG UI reconstructions derived from LVGL source code
│       ├── home-printing.svg        # Home screen during active print job
│       ├── home-idle.svg            # Home screen when printer is idle
│       ├── temperature.svg          # Temperature & fan controls (normal view)
│       ├── temperature-numpad.svg   # Temperature numpad editing mode
│       ├── control.svg              # XY/Z axis control D-pad
│       ├── filament.svg             # Filament load/unload screen
│       └── settings.svg             # Settings (scrollable list)
├── openhasp-conversion/         # OpenHASP conversion of the 2.8" LVGL UI
│   ├── README.md                    # Setup guide, entity mapping, customization
│   ├── pages.jsonl                  # Complete UI definition (6 pages + numpad)
│   ├── boot.cmd                     # Boot-time plate configuration
│   └── ha_automations.yaml          # HA automations for display ↔ printer bridge
└── 5-inch-pro/                  # 5" Pro commercial version
    ├── xtouch_5_promo.png       # Promotional image of 5" screen
    ├── intro-screens/           # Intro/landing page screen mockups
    │   ├── manage.png           # Multi-printer management screen
    │   ├── control.png          # Head/axis control screen
    │   ├── filament.png         # Filament/AMS management screen
    │   ├── skip.png             # Skip objects screen
    │   └── temperature.png      # Temperature & fan control screen
    └── feature-screens/         # Feature showcase screenshots
        ├── xtouch-manage-0-multi-printer.png   # Multi-printer support (up to 10 BBL + 10 Klipper)
        ├── xtouch-manage-1-printer-mgmt.png    # Printer management interface
        ├── xtouch-ams-material-mgmt.png        # AMS/advanced material management
        ├── xtouch-keypad-temp-profiles.png     # Temperature/fan profile keypad
        └── xtouch-skip-objects.png             # Skip objects with precision
```

---

## 2.8" Version - Screen Descriptions

The 2.8" version used [LVGL](https://lvgl.io/) (Light and Versatile Graphics Library) for its UI, running on an ESP32 with a 320x240 ILI9341 display. The UI was defined programmatically in C code (see `src/ui/` in the GitHub repo).

### Screens (from source code analysis)

| Screen | Source File | Description |
|--------|------------|-------------|
| **Intro Screen** | `ui_introScreen` | Boot/splash screen with xtouch logo and calibration prompt |
| **Home Screen** | `ui_homeScreen` | Main dashboard - WiFi/camera/timelapse/AMS status bar, light toggle, nozzle/bed/chamber temps, print progress with pause/stop, layer info, speed selector |
| **Temperature/Fan Screen** | `ui_temperatureScreen` | 4 buttons for nozzle temp, bed temp, chamber temp, and fan speed. Tapping opens numeric keypad for adjustment |
| **Control Screen** | `ui_controlScreen` | XYZ position control with homing button, 1mm/10mm step size toggle |
| **Filament Screen** | `ui_filamentScreen` | Load/unload/extrude/retract filament controls (non-AMS printers) |
| **Settings Screen** | `ui_settingsScreen` | LCD settings (backlight, sleep timer, invert colors, flip screen), xtouch settings (AUX fan, chamber temp, OTA update) |
| **Access Code Screen** | `ui_accessCodeScreen` | Keyboard input for printer access code |
| **Printer Pair Screen** | `ui_printerPairScreen` | Roller/list for selecting printer to pair with |

### Key UI Elements (Home Screen)
- **Top Status Bar**: WiFi icon, camera status, timelapse indicator, AMS status
- **Light Button**: Toggle printer work light on/off
- **Temperature Display**: Nozzle, bed, and chamber temperatures in real-time (using custom `ui_font_xlcd` font)
- **Print Status Area**:
  - Idle: "Ready" message with logo
  - Printing: Pause/stop buttons, progress bar, layer count, print speed selector

### Hardware Images
- **screen-2-8-front.png**: Front view of the ESP32-2432S028R board showing the 2.8" TFT display
- **screen-2-8-back.png**: Back view showing the ESP32 module, SD card slot, and connectors
- **power-pinout.png**: JST 1.25 4-pin connector wiring diagram for external power
- **DS18B20_pinout.png**: Pinout for connecting an external DS18B20 chamber temperature sensor

### SVG UI Reconstructions (`ui-screens/`)

Since the 2.8" version never had official UI screenshots (only hardware photos), these SVG renderings were **reconstructed directly from the LVGL C source code** in the GitHub repository. Each SVG faithfully recreates the widget hierarchy, layout, colors, and dimensions defined in the source files under `src/ui/components/`.

**Rendering details:**
- **Native resolution**: 320×240 pixels (ILI9341 TFT, landscape orientation)
- **SVG scale**: 2× (rendered at 640×480px for clarity)
- **Layout**: 48px sidebar (left, navigation) + 272px content area (right)
- **Font substitution**: The original `ui_font_xlcd` custom icon font glyphs are represented using Unicode symbols/emoji equivalents

| SVG File | Source Component | Description |
|----------|-----------------|-------------|
| **home-printing.svg** | `ui_comp_homecomponent.c` | Home screen during an active print — WiFi/camera/AMS status bar, play/pause/stop controls, progress bar at 60%, layer count, speed selector, nozzle/bed/chamber temperatures |
| **home-idle.svg** | `ui_comp_homecomponent.c` | Home screen when idle — "✓ Ready" status, greyed controls, temperature dashes |
| **temperature.svg** | `ui_comp_temperaturecomponent.c` | Normal view with Nozzle/Bed temperature panels (left) and Part/Aux/Chamber fan controls (right), each with current values and editable targets |
| **temperature-numpad.svg** | `ui_comp_temperaturecomponent.c` | Numpad editing mode — sidebar hidden, selected temp panel highlighted with green border, 4×3 numeric keypad (1-9, 0, Back, OK) |
| **control.svg** | `ui_comp_controlcomponent.c` | 3-column D-pad layout — range toggle (1mm/10mm), directional arrows (↑↓←→), home button, XY/Z axis toggle |
| **filament.svg** | `ui_comp_filamentcomponent.c` | Left: nozzle temperature adjust (up/down arrows, temp display in blue when cold <170°C or orange when hot ≥170°C). Right: filament load/unload buttons |
| **settings.svg** | `ui_comp_settingscomponent.c` | Scrollable settings list — LCD section (backlight slider, sleep timer, wake on print, invert colors, flip screen), device section (AUX fan, chamber fan, OTA, reboot button) |

**Color palette used:**

| Color | Hex | Usage |
|-------|-----|-------|
| Background | `#000000` | Screen background |
| Sidebar | `#222222` | Navigation sidebar, settings panels |
| Content BG | `#444444` | Main content area background |
| Panels | `#555555` | Buttons, numpad keys, status bar |
| Section headers | `#333333` | Settings section dividers, pressed states |
| Icon BG | `#777777` | Filament icon backgrounds |
| Borders/dim | `#888888` | Borders, dimmed text |
| Accent green | `#2AFF00` | Active nav item, checked borders, scrollbar |
| Slider fill | `#00FF00` | Slider indicators |
| Orange accent | `#FF682A` | Settings title, reboot button, active targets |
| Cold nozzle | `#39A1FD` | Nozzle temperature below 170°C |
| Hot nozzle | `#FAA61E` | Nozzle temperature at/above 170°C |
| Primary text | `#FFFFFF` | Main labels and values |
| Secondary text | `#CCCCCC` | Icons, secondary labels |

---

## 5" Pro Version - Screen Descriptions

The 5" Pro version was a closed-source commercial product. The source code was never published on GitHub. These images were recovered from the [Wayback Machine archive of xtouch.pro](https://web.archive.org/web/20250913181036/https://xtouch.pro/).

### Intro Screens (from xtouch.pro/intro/)
These were animated showcase images from the product landing page:

| Image | Screen | Description |
|-------|--------|-------------|
| `manage.png` | Multi-Printer Management | Dashboard for controlling multiple printers simultaneously |
| `control.png` | Head Control | XYZ axis movement and homing controls |
| `filament.png` | Filament Manager | AMS and filament management interface |
| `skip.png` | Skip Objects | Interface for skipping failed print objects |
| `temperature.png` | Temperature & Fan | Temperature and fan speed control with profiles |

### Feature Screens (from xtouch.pro marketing page)

| Image | Feature | Description |
|-------|---------|-------------|
| `xtouch-manage-0-multi-printer.png` | Multi-Printer Support | Control up to 10 BambuLab Local and 10 Klipper printers. PRUSA support was in development. |
| `xtouch-manage-1-printer-mgmt.png` | Printer Management | Effortlessly manage local 3D printers |
| `xtouch-ams-material-mgmt.png` | Advanced Material Management | BambuLab AMS support, Creality CFS MMU was in development |
| `xtouch-keypad-temp-profiles.png` | Temp/Fan Profiles | Custom temperature and fan profiles stored on screen |
| `xtouch-skip-objects.png` | Skip Objects | Stop printing failed objects while completing the rest |

### Pro Features (from xtouch.pro pricing page)
- xtouch-hub (local-cloud) server
- Up to 20 printers (BBL Local + Klipper)
- OTA Updates
- Preview Images
- Custom Presets (Temp/Fan)
- Custom AMS Material Presets
- Skip Objects
- Chamber Temperature (with additional hardware)
- RFID/NFC via xspool
- Priority Support

---

## Source URLs

### GitHub Repository Images
| File | Original URL |
|------|-------------|
| xtouch-logo.png | https://raw.githubusercontent.com/xperiments-in/xtouch/main/readme-assets/xtouch.png |
| screen-2-8-front.png | https://raw.githubusercontent.com/xperiments-in/xtouch/main/readme-assets/screen-2-8.png |
| screen-2-8-back.png | https://raw.githubusercontent.com/xperiments-in/xtouch/main/readme-assets/screen-2-8-back.png |
| power-pinout.png | https://raw.githubusercontent.com/xperiments-in/xtouch/main/readme-assets/power-pinout.png |
| DS18B20_pinout.png | https://raw.githubusercontent.com/xperiments-in/xtouch/main/readme-assets/DS18B20_pinout.png |
| xtouch_5_promo.png | https://raw.githubusercontent.com/xperiments-in/xtouch/main/readme-assets/xtouch_5.png |

### Wayback Machine Archived Images (xtouch.pro)
| File | Wayback URL |
|------|------------|
| manage.png | https://web.archive.org/web/20250909191807im_/https://xtouch.pro/intro/img/manage.png |
| control.png | https://web.archive.org/web/20250909191807im_/https://xtouch.pro/intro/img/control.png |
| filament.png | https://web.archive.org/web/20250909191807im_/https://xtouch.pro/intro/img/filament.png |
| skip.png | https://web.archive.org/web/20250909191807im_/https://xtouch.pro/intro/img/skip.png |
| temperature.png | https://web.archive.org/web/20250909191807im_/https://xtouch.pro/intro/img/temperature.png |
| xtouch-manage-0-multi-printer.png | https://web.archive.org/web/20250909191807im_/https://xtouch.pro/assets/images/xtouch-manage-0-6bba18fb8b78869876c724e120fb1c3d.png |
| xtouch-manage-1-printer-mgmt.png | https://web.archive.org/web/20250909191807im_/https://xtouch.pro/assets/images/xtouch-manage-1-ccfcde73150bd95e1dd5454c79b4c890.png |
| xtouch-ams-material-mgmt.png | https://web.archive.org/web/20250909191807im_/https://xtouch.pro/assets/images/xtouch-ams-8a7c26dd9cb5180c02be5b8a35e4c227.png |
| xtouch-keypad-temp-profiles.png | https://web.archive.org/web/20250909191807im_/https://xtouch.pro/assets/images/xtouch-keypad-cee0840b184ba770e2b04d0c81b4bc73.png |
| xtouch-skip-objects.png | https://web.archive.org/web/20250909191807im_/https://xtouch.pro/assets/images/xtouch-skip-71943e6d4bba55204e262be8cb4ac3ff.png |

### Additional Wayback Machine Pages
- **Full site snapshot (Sep 2025)**: https://web.archive.org/web/20250913181036/https://xtouch.pro/
- **Intro page**: https://web.archive.org/web/20250909191807/https://xtouch.pro/intro/index.html
- **All captures**: https://web.archive.org/web/*/https://xtouch.pro/ (7 captures, Jan 2022 - Sep 2025)

---

## Related Links
- **GitHub Repository**: https://github.com/xperiments-in/xtouch (GPL-3.0, open source 2.8" version)
- **Discord Server**: https://discord.gg/RytEDEgfR3
- **Ko-fi**: https://ko-fi.com/xperiments
- **Author Twitter/X**: https://x.com/xps3riments
