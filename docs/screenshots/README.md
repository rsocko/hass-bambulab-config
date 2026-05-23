# Screenshot Capture Task Tracker

> **Guide:** See [screenshot-guide.md](/docs/repo/reference/screenshot-guide.md) for format recommendations, capture tools, versioning, and embedding syntax.

## Status Legend

| Symbol | Meaning |
|--------|---------|
| ⬜ | Not yet captured |
| ✅ | Captured and embedded |
| 🔄 | Needs refresh (feature changed since last capture) |

---

## Printer Dashboards

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ✅ | `dashboard-full-desktop` | png | Full dashboard — desktop overview | [README](/docs/features/printer_dashboards/README.md) |
| ✅ | `dashboard-full-mobile` | png | Full dashboard — mobile overview | [README](/docs/features/printer_dashboards/README.md) |
| ✅ | `ams-tray-popup-matched` | png | AMS tray popup — matched spool with full details | [README](/docs/features/printer_dashboards/README.md) |
| ⬜ | `ams-tray-popup-interaction` | gif | AMS tray popup — tap-to-open interaction | [README](/docs/features/printer_dashboards/README.md) |
| ✅ | `top-bar-desktop` | png | Top bar — desktop 2-column grid during active print | [top-bar-layout.md](/docs/features/printer_dashboards/design/top-bar-layout.md) |
| ✅ | `top-bar-mobile` | png | Top bar — mobile single-column layout | [top-bar-layout.md](/docs/features/printer_dashboards/design/top-bar-layout.md) |
| ✅ | `ams-popup-full-matched` | png | AMS popup — full matched spool view | [ams-tray-popup-visual.md](/docs/features/printer_dashboards/design/ams-tray-popup-visual.md) |
| ✅ | `ams-popup-no-spool` | png | AMS popup — fallback/no spool matched | [ams-tray-popup-visual.md](/docs/features/printer_dashboards/design/ams-tray-popup-visual.md) |
| ✅ | `ams-popup-weight-warning` | png | AMS popup — insufficient filament warning | [ams-tray-popup-visual.md](/docs/features/printer_dashboards/design/ams-tray-popup-visual.md) |
| ⬜ | `ams-popup-desiccant-states` | png | AMS popup — desiccant status color states | [ams-tray-popup-visual.md](/docs/features/printer_dashboards/design/ams-tray-popup-visual.md) |

## Common (AMS Card Templates)

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ✅ | `common-ams-header-card` | png | AMS header card with humidity/temp indicators | [README](/docs/features/common/README.md) |
| ✅ | `common-ams-tray-cards` | png | AMS section — header + 4 tray cards with filament colors | [README](/docs/features/common/README.md) |

## Printer Controls (Fan Controls)

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ✅ | `fan-controls-desktop` | png | Fan controls — desktop layout during active print | [README](/docs/features/printer_controls/README.md) |
| ⬜ | `fan-controls-speed-states` | gif | Fan control icon color transitions at different speeds | [README](/docs/features/printer_controls/README.md) |
| ✅ | `fan-controls-printing` | png | All fans active during print (varying speeds, colored icons) | [fan-controls-visual.md](/docs/features/printer_controls/design/fan-controls-visual.md) |
| ⬜ | `fan-controls-idle` | png | All fans idle (grey icons, 0%/Off) | [fan-controls-visual.md](/docs/features/printer_controls/design/fan-controls-visual.md) |

## Printer Temps

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ✅ | `temp-cards-heating` | png | Temp cards — heating state (red indicators) | [README](/docs/features/printer_temps/README.md) |
| ⬜ | `temp-cards-cooling` | png | Temp cards — cooling state (blue indicators) | [README](/docs/features/printer_temps/README.md) |
| ⬜ | `temp-cards-idle` | png | Temp cards — idle state (grey) | [README](/docs/features/printer_temps/README.md) |
| ⬜ | `temp-cards-transition` | gif | Temp cards — heating cycle color transition | [README](/docs/features/printer_temps/README.md) |
| ✅ | `temp-visual-heating` | png | Visual ref — heating state (red tint, borders) | [printer-temps-visual-reference.md](/docs/features/printer_temps/design/printer-temps-visual-reference.md) |
| ⬜ | `temp-visual-cooling` | png | Visual ref — cooling state (blue tint, borders) | [printer-temps-visual-reference.md](/docs/features/printer_temps/design/printer-temps-visual-reference.md) |
| ⬜ | `temp-visual-idle` | png | Visual ref — idle state (no color indicators) | [printer-temps-visual-reference.md](/docs/features/printer_temps/design/printer-temps-visual-reference.md) |

## Printer LED

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ✅ | `led-controls-compact` | png | LED compact 6-button icon row | [README](/docs/features/printer_led/README.md) |
| ⬜ | `led-controls-expanded-grid` | png | LED expanded grid with all 7 lights | [README](/docs/features/printer_led/README.md) |
| ⬜ | `led-wled-popup` | gif | WLED advanced popup — effect selection | [README](/docs/features/printer_led/README.md) |
| ⬜ | `led-physical-strips` | gif | Physical LED strips — state transition on hardware | [README](/docs/features/printer_led/README.md) |
| ✅ | `led-visual-full-grid` | png | Visual ref — full 7-light grid | [led-controls-visual.md](/docs/features/printer_led/reference/led-controls/visual-reference.md) |
| ⬜ | `led-visual-wled-popup` | png | Visual ref — WLED popup control panel | [led-controls-visual.md](/docs/features/printer_led/reference/led-controls/visual-reference.md) |

## Print Progress

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ✅ | `print-progress-kpi-active` | png | KPI cards — active print with real values | [README](/docs/features/print_progress/README.md) |
| ⬜ | `print-progress-kpi-animation` | gif | KPI cards — CSS animations (spin/bounce) | [README](/docs/features/print_progress/README.md) |
| ⬜ | `print-progress-kpi-idle` | png | KPI cards — idle state | [README](/docs/features/print_progress/README.md) |

## Print Weight & Cost

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ✅ | `weight-bar-chart-multicolor` | png | Stacked bar chart — multi-color print | [README](/docs/features/print_weight_and_cost/README.md) |
| ⬜ | `weight-per-tray-warnings` | png | Per-tray weight cards with warnings | [README](/docs/features/print_weight_and_cost/README.md) |

## Error Alerts

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ⬜ | `hms-alert-single-error` | png | Single error expanded (red banner) | [README](/docs/features/error_alerts/README.md) |
| ⬜ | `hms-alert-multiple-errors` | png | Multiple errors with severity colors | [README](/docs/features/error_alerts/README.md) |
| ⬜ | `hms-alert-collapse-toggle` | gif | Expand/collapse interaction | [README](/docs/features/error_alerts/README.md) |
| ⬜ | `hms-alert-no-errors` | png | Dashboard with banner hidden (no errors) | [README](/docs/features/error_alerts/README.md) |
| ⬜ | `hms-ui-single-expanded` | png | UI mockup — single error expanded | [hms-error-ui-mockup.md](/docs/features/error_alerts/design/hms-error-ui-mockup.md) |
| ⬜ | `hms-ui-multiple-errors` | png | UI mockup — multiple errors | [hms-error-ui-mockup.md](/docs/features/error_alerts/design/hms-error-ui-mockup.md) |
| ⬜ | `hms-ui-collapsed` | png | UI mockup — collapsed state | [hms-error-ui-mockup.md](/docs/features/error_alerts/design/hms-error-ui-mockup.md) |

## Air Quality

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ✅ | `air-quality-sensors-good` | png | Sensor cards — good state (all green) | [README](/docs/features/air_quality/README.md) |
| ⬜ | `air-quality-sensors-poor` | png | Sensor cards — poor state (high-VOC print) | [README](/docs/features/air_quality/README.md) |
| ✅ | `air-quality-purifier-controls` | png | Govee purifier control card | [README](/docs/features/air_quality/README.md) |
| ✅ | `air-quality-visual-good` | png | Visual preview — good (all green) | [visual-preview.md](/docs/features/air_quality/reference/visual-preview.md) |
| ⬜ | `air-quality-visual-moderate` | png | Visual preview — moderate (yellow) | [visual-preview.md](/docs/features/air_quality/reference/visual-preview.md) |
| ⬜ | `air-quality-visual-poor` | png | Visual preview — poor (orange) | [visual-preview.md](/docs/features/air_quality/reference/visual-preview.md) |
| ✅ | `air-quality-visual-purifier` | png | Visual preview — purifier controls ON | [visual-preview.md](/docs/features/air_quality/reference/visual-preview.md) |

## Humidity

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ✅ | `humidity-cards-desktop` | png | Humidity cards — desktop, optimal conditions | [README](/docs/features/humidity/README.md) |
| ⬜ | `humidity-cards-warning` | png | Humidity cards — mixed warning states | [README](/docs/features/humidity/README.md) |

## WLED

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ⬜ | `wled-state-machine-printing` | gif | Physical LEDs — idle → printing transition | [README](/docs/features/wled/README.md) |
| ⬜ | `wled-front-display-progress` | gif | Front C-shape LED — progress bar filling | [README](/docs/features/wled/README.md) |
| ⬜ | `wled-ams-tray-lighting` | png | AMS lid LEDs — spool illumination | [README](/docs/features/wled/README.md) |
| ⬜ | `wled-error-state` | gif | Error state S6 — flashing red LEDs | [README](/docs/features/wled/README.md) |

## OpenHASP Display

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ⬜ | `openhasp-esp32s3-5inch-home` | png | ESP32-S3 5" — home screen | [README](/docs/features/openhasp_display/README.md) |
| ⬜ | `openhasp-esp32s3-5inch-controls` | gif | ESP32-S3 5" — screen navigation | [README](/docs/features/openhasp_display/README.md) |
| ⬜ | `openhasp-xtouch-2.8-home` | png | xTouch 2.8" — home screen | [README](/docs/features/openhasp_display/README.md) |

## Spoolman Sync

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ⬜ | `spoolman-persistent-notification` | png | Sync error persistent notification | [README](/docs/features/spoolman_sync/README.md) |
| ⬜ | `spoolman-self-test-pass` | png | Self-test passing result | [README](/docs/features/spoolman_sync/README.md) |

## Notifications

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ⬜ | `notification-print-complete` | png | Print completion notification with snapshot | [README](/docs/features/notifications/README.md) |
| ⬜ | `notification-print-error` | png | Print error critical notification | [README](/docs/features/notifications/README.md) |

## Filament Tag

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ⬜ | `filament-tag-scan-result` | png | NFC tag scan — matched spool result | [README](/docs/features/filament_tag/README.md) |

## Bambuddy Integration

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ⬜ | `bambuddy-integration-entities` | png | HA sensor entities | [docs README](/docs/features/bambuddy_integration/README.md) |

## Bambuddy Dashboards

| Status | ID | Format | Description | Doc Location |
|--------|-----|--------|-------------|-------------|
| ⬜ | `bambuddy-print-history-card` | png | Legacy prototype print history card | [docs/repo/planning/bambuddy-reorganization-plan.md](/docs/repo/planning/bambuddy-reorganization-plan.md) |
| ⬜ | `bambuddy-queue-card` | png | Legacy prototype queue card | [docs/repo/planning/bambuddy-reorganization-plan.md](/docs/repo/planning/bambuddy-reorganization-plan.md) |
| ⬜ | `bambuddy-statistics-card` | png | Legacy prototype statistics card | [docs/repo/planning/bambuddy-reorganization-plan.md](/docs/repo/planning/bambuddy-reorganization-plan.md) |
| ⬜ | `bambuddy-maintenance-card` | png | Legacy prototype maintenance card | [docs/repo/planning/bambuddy-reorganization-plan.md](/docs/repo/planning/bambuddy-reorganization-plan.md) |

---

## Summary

| Category | PNG | GIF | Total |
|----------|-----|-----|-------|
| Printer Dashboards | 8 | 1 | 9 |
| Common | 2 | 0 | 2 |
| Printer Controls | 3 | 1 | 4 |
| Printer Temps | 6 | 1 | 7 |
| Printer LED | 4 | 2 | 6 |
| Print Progress | 2 | 1 | 3 |
| Print Weight & Cost | 2 | 0 | 2 |
| HMS Alert | 6 | 1 | 7 |
| Air Quality | 6 | 0 | 6 |
| Humidity | 2 | 0 | 2 |
| WLED | 1 | 3 | 4 |
| OpenHASP Display | 2 | 1 | 3 |
| Spoolman Sync | 2 | 0 | 2 |
| Notifications | 2 | 0 | 2 |
| Filament Tag | 1 | 0 | 1 |
| Bambuddy | 5 | 0 | 5 |
| **Total** | **54** | **11** | **65** |
