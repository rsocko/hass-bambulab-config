# ESP32-S3 5" Touchscreen – 3D Printer Dashboard

A physical touchscreen display mounted near the 3D printer that shows real-time printer state/detail, progress arcs, AMS spool colors, camera images, and more — all driven by [openHASP](https://www.openhasp.com/) and Home Assistant.

## Hardware

| Item | Details |
|------|---------|
| **Display** | [Guition ESP32-S3 5" 800×480 Touch LCD](https://www.aliexpress.us/item/3256806529479550.html?spm=a2g0o.order_list.order_list_main.5.522b1802WVIMK4&gatewayAdapt=glo2usa) (purchased from AliExpress) |
| **Firmware** | [openHASP](https://www.openhasp.com/) — MQTT-driven touchscreen UI firmware for ESP32 |
| **Resolution** | 800 × 480 pixels, capacitive touch |
| **Connectivity** | Wi-Fi + MQTT to Home Assistant |

## How It Works

The system is split into two halves:

1. **ESP32 Device (openHASP side)** — The `.jsonl` page layout and device configuration files run directly on the ESP32. They define what UI objects (arcs, labels, rectangles, images) appear on screen. See the [openhasp/](../../../../openhasp/) folder.

2. **Home Assistant side** — A plate configuration YAML binds those UI objects to HA entities (sensors, images). Automations push camera/model images to the display. See [hass-config-readme.md](./hass-config-readme.md).

### Smart Status Source

The status text shown on the ESP32 is now sourced from the Home Assistant template sensor defined in [../../../../homeassistant/packages/3d_printing/core/template_sensors/smart_status.yaml](../../../../homeassistant/packages/3d_printing/core/template_sensors/smart_status.yaml):

- **Primary status (State):** `sensor.ntk_ryansoffice_3dprinter_smart_status`
- **Secondary status (Detail):** `sensor.ntk_ryansoffice_3dprinter_smart_status` attribute `detail`

These values are bound in [../../../../homeassistant/packages/3d_printing/openhasp_display/openhasp/officetouch5.yaml](../../../../homeassistant/packages/3d_printing/openhasp_display/openhasp/officetouch5.yaml) and rendered by label objects in [../../../../openhasp/esp32s3-5inch/device/printer2.jsonl](../../../../openhasp/esp32s3-5inch/device/printer2.jsonl).

```
┌──────────────────────┐         MQTT          ┌──────────────────────┐
│   Home Assistant      │◄─────────────────────►│   ESP32-S3 Display   │
│                       │                       │                       │
│  packages/3d_printing │   entity state →      │  printer2.jsonl       │
│   /openhasp_display/  │   → object property   │  (page layout)        │
│                       │                       │                       │
│  automations:         │   push_image →        │  UI renders arcs,     │
│   push image to screen│   → display bitmap    │  labels, spool colors │
└──────────────────────┘                       └──────────────────────┘
```

## Display Layout (Page 1)

The printer dashboard shows:

- **Model preview image** (200×200, pushed from HA via automation)
- **Progress arc** with percentage label
- **Layer arc** showing current/total layers
- **Time remaining** arc and formatted label
- **Top-right printer controls** (`Stop`, `Pause`, `Start`) with icon-only buttons and state-driven availability colors
- **Controls page shortcut** (`CTL`) that opens a dedicated motion/filament page
- **Estimated completion time** (friendly format: same day time, `tomorrow`, weekday, or date)
- **Filament analytics shortcut** (`FIL`) opening a dedicated page with side-by-side `Print Weight` and `Print Cost` panels
- **Printer state** and **detail** labels (from smart status template sensor)
- **Status LED** indicator

### Display Layout (Page 2)

The controls page provides direct machine movement actions inspired by the ha-bambulab controls popup:

- **XY directional control cluster** with icon-based 1-step and stacked-arrow 10-step moves plus a centered home icon action
- **Z axis controls** that reuse the same up/down single and stacked arrow icons as XY, plus a center bed icon
- **Filament controls** using up/down arrow icon buttons for retract/extrude
- **Close button** (`X`) to return to the main dashboard page
- Safety hint text is hidden to reduce visual clutter on this page

## Object ID Quick Reference

Use this as a fast map of the major object groups. For full object-by-object details (types, coordinates, and static labels), use [openhasp/README.md](../../../../openhasp/README.md).

| Object IDs | Role |
|------------|------|
| `p1b1` | Model/cover image target |
| `p1b2`–`p1b8` | Progress, layer, time arcs and primary metric labels |
| `p1b14`, `p1b15`, `p1b16`, `p1b29` | Formatted time/estimate labels |
| `p1b10`–`p1b13`, `p1b17`–`p1b20`, `p1b39` | AMS + external spool indicators |
| `p1b27` | Smart status LED color indicator |
| `p1b31`, `p1b32` | Smart status text labels (detail/state) |
| `p0b2`–`p0b4` | Shared left-nav launchers (home, controls, filament) |
| `p1b84`–`p1b89` | Printer control buttons + icons (`Stop`, `Pause`, `Start`) |
| `p2b5`–`p2b13` | XY controls (icon-based 1-step, stacked-arrow 10-step, home) |
| `p2b20`–`p2b23` | Z-axis controls (up/down icon-based 1-step and 10-step) |
| `p2b30`, `p2b31` | Filament retract/extrude |
| `p2b41` | Safety hint placeholder (hidden) |
| `p3b53`, `p3b54` | Weight/cost panel totals |
| `p3b60`–`p3b68` | Cost panel stacked bar segments |
| `p3b73`–`p3b81` | Weight panel stacked bar segments |
| `p3b71`, `p3b72` | Multiline legend/detail labels (per-slot values and percentages) |

Maintenance note: keep this section as a grouped summary only; update exact object metadata in [openhasp/README.md](../../../../openhasp/README.md) to maintain a single detailed source of truth.

## Directory Structure

```
homeassistant/packages/3d_printing/openhasp_display/
├── openhasp_display_loader.yaml      ← Feature loader referenced by _feature_loaders.yaml
├── openhasp/
│   └── officetouch5.yaml             ← OpenHASP plate object bindings
└── automations/
    ├── auto_manage_screen_visibility.yaml
    ├── printer_motion_controls.yaml
    ├── printer_control_buttons.yaml
    ├── push_printer_image_to_screen.yaml
    └── save_camera_snapshot_from_3d_printer.yaml

openhasp/esp32s3-5inch/device/
├── config.json                       ← Device configuration (Wi-Fi, MQTT, GUI)
├── pages/                            ← Per-page source JSONL files (page0..page3)
├── printer2.jsonl                    ← Combined deploy file loaded by openHASP
├── online.cmd                        ← Command executed when MQTT connects
└── offline.cmd                       ← Command executed when MQTT disconnects
```

## Quick Links

- **Home Assistant config details** → [hass-config-readme.md](./hass-config-readme.md)
- **ESP32 device file details** → [openhasp/README.md](../../../../openhasp/README.md)
- **openHASP documentation** → [openhasp.com](https://www.openhasp.com/)
- **openHASP HA integration** → [How-To](https://www.openhasp.com/0.7.0/integrations/home-assistant/howto/)
- **Guition hardware page** → [ESP32-S3 JC8048W550](https://www.openhasp.com/0.7.0/hardware/guition/jc8048w550/)


