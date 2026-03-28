# Documentation Index

This folder contains all repository documentation organized by topic.

## Sections

- `repo/` — Repository-level migration notes, implementation summaries, and quick-start docs.
- `features/` — Feature-level documentation, one folder per implementation package.
- `infrastructure/` — Non-Home Assistant operational/infrastructure docs.

## Foundation Packages

Nearly every feature in this repository depends on two **foundation packages** and one **external integration**. If a feature's Dependencies section mentions "Foundation," it means these three:

| Dependency | What It Provides |
|---|---|
| **[Core](features/core/README.md)** | Smart status sensor (`sensor.*_smart_status`), spoolman tray map, base template sensors. Wraps raw printer data into reusable entities consumed by almost every other feature. |
| **[Common](features/common/README.md)** | Shared dashboard infrastructure — Lovelace registration, `view_main.yaml`, reusable `button_card_templates`. Any feature that contributes dashboard cards depends on Common. |
| **[ha-bambulab](https://github.com/greghesp/ha-bambulab)** | The Bambu Lab Home Assistant integration. Provides all raw printer sensors, camera entity, device triggers, and AMS data that Core and other features build on. Must be installed and configured with your printer before any feature will work. |

> **Tip:** Features that are purely dashboard-card packages (e.g., humidity, printer_temps, print_progress) depend on Core and Common but don't have their own feature loader — they are included via `!include` in `view_main.yaml`.

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
| [error_alerts](features/error_alerts/README.md) | Unified error alerts (HMS + print errors), severity mapping, action buttons |

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

- `repo/deployment-structure.md` — Deployment profiles, package scope, and workflow safety guards.
- `repo/dashboard-deployment-behavior.md` — Dashboard/reload behavior and JS cache-bust procedure.
- `repo/repo-layout.md` — Repository file layout.
- `repo/quick-start.md` — Quick start guide.
- `repo/implementation-summary.md` — Implementation overview.
- `repo/implementation-notes.md` — AMS tray popup implementation details.
- `repo/third-party-attribution.md` — Third-party inspiration and attribution.
- `repo/screenshot-guide.md` — Screenshot & animation capture guide, versioning, and embedding conventions.

## Screenshots

Visual assets are tracked in [`screenshots/README.md`](screenshots/README.md) — a checklist of all 65 planned screenshots and animations across the documentation. See [`repo/screenshot-guide.md`](repo/screenshot-guide.md) for capture tools, format recommendations, and versioning conventions.

## Dependency Overview

Every feature's README has a **Dependencies & Requirements** section in a consistent format. The table below gives a quick-reference summary. See each feature's README for full details including optional dependencies and how to disable them.

| Feature | Core | Common | ha-bambulab | Other Feature Dependencies | Key External Dependencies |
|---|:---:|:---:|:---:|---|---|
| **core** | — | — | **Yes** | *(none — this is the foundation)* | — |
| **common** | **Yes** | — | **Yes** | *(none — this is the foundation)* | button-card, browser-mod |
| **air_quality** | **Yes** | **Yes** | **Yes** | printer_controls *(optional)* | AirGradient, Govee (gv2mqtt), Bento Box fan |
| **bambuddy_integration** | **Yes** | — | **Yes** | notifications *(optional)* | Bambuddy service |
| **filament_tag** | **Yes** | **Yes** | **Yes** | spoolman_sync | NFC reader, Spoolman |
| **error_alerts** | **Yes** | **Yes** | **Yes** | *(none)* | mushroom, button-card, card-mod |
| **humidity** | **Yes** | **Yes** | **Yes** | *(none)* | mushroom, card-mod |
| **logging** | — | — | — | *(none — standalone)* | Loki/Grafana *(optional)* |
| **notifications** | **Yes** | — | **Yes** | *(none)* | Mobile app, light *(opt)*, TTS *(opt)* |
| **openhasp_display** | **Yes** | — | **Yes** | printer_controls | OpenHASP hardware + integration |
| **printer_controls** | **Yes** | **Yes** | **Yes** | *(none)* | mushroom, button-card |
| **printer_dashboards** | **Yes** | **Yes** | **Yes** | All features with `dashboard_cards/` | 12 HACS cards (see feature README) |
| **printer_led** | **Yes** | **Yes** | **Yes** | wled | WLED controllers, mushroom, button-card |
| **printer_temps** | **Yes** | **Yes** | **Yes** | *(none)* | mushroom |
| **print_progress** | **Yes** | **Yes** | **Yes** | *(none)* | button-card |
| **print_weight_and_cost** | **Yes** | **Yes** | **Yes** | spoolman_sync | — |
| **spoolman_sync** | **Yes** | — | **Yes** | *(none)* | Spoolman, Spoolman HA integration, REST |
| **wled** | **Yes** | — | **Yes** | *(none)* | WLED hardware + firmware |
