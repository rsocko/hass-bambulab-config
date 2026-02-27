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

1. **ESP32 Device (openHASP side)** — The `.jsonl` page layout and device configuration files run directly on the ESP32. They define what UI objects (arcs, labels, rectangles, images) appear on screen. See the [openhasp/](openhasp/) folder.

2. **Home Assistant side** — A plate configuration YAML binds those UI objects to HA entities (sensors, images). Automations push camera/model images to the display. See the [hass-config/](hass-config/) folder.

### Smart Status Source

The status text shown on the ESP32 is now sourced from the Home Assistant template sensor defined in [../../dashboards/templates.yaml](../../dashboards/templates.yaml):

- **Primary status (State):** `sensor.ntk_ryansoffice_3dprinter_smart_status`
- **Secondary status (Detail):** `sensor.ntk_ryansoffice_3dprinter_smart_status` attribute `detail`

These values are bound in [hass-config/officetouch5.yaml](hass-config/officetouch5.yaml) and rendered by label objects in [openhasp/printer2.jsonl](openhasp/printer2.jsonl).

```
┌──────────────────────┐         MQTT          ┌──────────────────────┐
│   Home Assistant      │◄─────────────────────►│   ESP32-S3 Display   │
│                       │                       │                       │
│  openhasp/            │   entity state →      │  printer2.jsonl       │
│   officetouch5.yaml   │   → object property   │  (page layout)        │
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
- **Estimated completion time**
- **AMS spool color indicators** — 8 rectangles (AMS 1: A1–A4, AMS 2: B1–B4) + external spool
- **Printer state** and **detail** labels (from smart status template sensor)
- **Status LED** indicator

## Directory Structure

```
esp32s3-5inch/
├── readme.md                  ← You are here
├── hass-config/               ← Home Assistant configuration files
│   ├── readme.md              ← Detailed docs for HA-side config
│   ├── officetouch5.yaml      ← OpenHASP plate object bindings
│   ├── template_sensors.yaml  ← Helper template sensor definitions
│   ├── push_printer_image_to_screen.yaml
│   └── save_camera_snapshot_from_3d_printer.yaml
└── openhasp/                  ← Files deployed to the ESP32 device
    ├── readme.md              ← Detailed docs for device-side files
    ├── config.json            ← Device configuration (Wi-Fi, MQTT, GUI)
    ├── printer2.jsonl         ← Page layout (UI objects)
    ├── online.cmd             ← Command executed when MQTT connects
    └── offline.cmd            ← Command executed when MQTT disconnects
```

## Quick Links

- **Home Assistant config details** → [hass-config/readme.md](hass-config/readme.md)
- **ESP32 device file details** → [openhasp/readme.md](openhasp/readme.md)
- **openHASP documentation** → [openhasp.com](https://www.openhasp.com/)
- **openHASP HA integration** → [How-To](https://www.openhasp.com/0.7.0/integrations/home-assistant/howto/)
- **Guition hardware page** → [ESP32-S3 JC8048W550](https://www.openhasp.com/0.7.0/hardware/guition/jc8048w550/)