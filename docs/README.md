# Documentation Index

This folder contains all repository documentation organized by topic.

## Sections

- `repo/` — Repository-level migration notes, implementation summaries, and quick-start docs.
- `features/` — Feature-level documentation, one folder per implementation package.
- `infrastructure/` — Non-Home Assistant operational/infrastructure docs.

## Feature Docs

Each feature folder maps 1:1 to a package under `homeassistant/packages/3d_printing/`.

### Foundation

| Feature | Description |
|---------|-------------|
| [core](features/core/README.md) | Smart status sensor, base template sensors, unmapped state alerts |
| [common](features/common/README.md) | Shared dashboard layouts, views, card templates |

### Printer Features

| Feature | Description |
|---------|-------------|
| [printer_controls](features/printer_controls/README.md) | Fan controls, skip objects, printer status card |
| [printer_temps](features/printer_temps/README.md) | Nozzle and bed temperature monitoring cards |
| [printer_led](features/printer_led/README.md) | LED lighting control (MagWLED, chamber, AMS, front display) |
| [printer_dashboards](features/printer_dashboards/README.md) | Dashboard composition, layout, views, AMS tray UI |
| [hms_alert](features/hms_alert/README.md) | HMS error detection, alert banner, testing |

### Print Tracking

| Feature | Description |
|---------|-------------|
| [print_progress](features/print_progress/README.md) | Animated KPI cards (layer, progress, time, ETA) |
| [print_weight_and_cost](features/print_weight_and_cost/README.md) | Filament weight visualization and cost tracking |
| [spoolman_sync](features/spoolman_sync/README.md) | Spoolman integration, spool usage, print weight persistence |
| [filament_tag](features/filament_tag/README.md) | NFC filament tag scanning and Spoolman association |

### Environment & Monitoring

| Feature | Description |
|---------|-------------|
| [air_quality](features/air_quality/README.md) | PM2.5, CO2, VOC monitoring; air purifier automation |
| [humidity](features/humidity/README.md) | Humidity/temperature tracking for filament storage |
| [logging](features/logging/README.md) | Structured logging, error tracking, Loki/Grafana/Prometheus |
| [notifications](features/notifications/README.md) | Print completion alerts, camera snapshots, TTS |

### External Hardware

| Feature | Description |
|---------|-------------|
| [wled](features/wled/README.md) | WLED controllers, state machine, presets, segment configuration |
| [openhasp_display](features/openhasp_display/README.md) | OpenHASP touchscreen displays (xTouch, ESP32-S3) |
| [bambuddy_integration](features/bambuddy_integration/README.md) | Bambuddy cloud integration for print history and queue |

## Repo Docs

- `repo/DEPLOYMENT_STRUCTURE.md` — Deployment profiles, package scope, and workflow safety guards.
- `repo/DASHBOARD_DEPLOYMENT_BEHAVIOR.md` — Dashboard/reload behavior and JS cache-bust procedure.
- `repo/REPO_LAYOUT.md` — Repository file layout.
- `repo/QUICK_START.md` — Quick start guide.
- `repo/IMPLEMENTATION_SUMMARY.md` — Implementation overview.
- `repo/IMPLEMENTATION_NOTES.md` — AMS tray popup implementation details.
- `repo/THIRD_PARTY_ATTRIBUTION.md` — Third-party inspiration and attribution.
