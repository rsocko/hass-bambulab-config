# HMS Alert

Bambu Lab Health Management System (HMS) error detection, display, and alerting.

## Implementation

**Package**: [`homeassistant/packages/3d_printing/hms_alert/`](../../../homeassistant/packages/3d_printing/hms_alert/)

### Structure

| Directory | Purpose |
|-----------|---------|
| `automations/` | HMS error handling automations |
| `dashboard_cards/` | Unified responsive HMS alert banner card |
| `helpers/` | Input booleans and selects for preview/testing |
| `template_sensors/` | Binary sensors for HMS error state |

### Key Entities

- `binary_sensor.*_hms_errors` — `on` when errors present; attributes include `count` and `errors` array
- HMS alert banner card — Conditional card that appears only when errors exist

## Screenshots

<!-- SCREENSHOT: id=hms-alert-single-error | format=png | version=1.0 | package=hms_alert | added=2026-03-15 -->
<!-- Capture: Single HMS error expanded — show red banner with error description, code, and wiki link -->
> **📸 Screenshot needed:** HMS alert banner — single error expanded *(png)*

<!-- SCREENSHOT: id=hms-alert-multiple-errors | format=png | version=1.0 | package=hms_alert | added=2026-03-15 -->
<!-- Capture: Multiple HMS errors (2-3) showing severity-colored cards (red/orange/yellow) in flex-wrap layout -->
> **📸 Screenshot needed:** HMS alert banner — multiple errors with severity colors *(png)*

<!-- SCREENSHOT: id=hms-alert-collapse-toggle | format=gif | version=1.0 | package=hms_alert | added=2026-03-15 -->
<!-- Capture: Record expand/collapse toggle — tap chevron to collapse, tap again to expand. ~3-4s loop (use ScreenToGif) -->
> **🎬 Animation needed:** HMS alert banner — expand/collapse interaction *(gif)*

<!-- SCREENSHOT: id=hms-alert-no-errors | format=png | version=1.0 | package=hms_alert | added=2026-03-15 -->
<!-- Capture: Dashboard with no errors present — show that HMS section is completely hidden (clean dashboard) -->
> **📸 Screenshot needed:** Dashboard with no HMS errors — banner hidden *(png)*

## Documentation

| File | Description |
|------|-------------|
| [error-alerts-unified-design.md](error-alerts-unified-design.md) | **Unified design:** Consolidates HMS + print errors into one "Error Alerts" system — phased implementation plan |
| [hms-error-alert-implementation.md](hms-error-alert-implementation.md) | Technical implementation: architecture, card structure, template syntax, styling |
| [hms-error-ui-mockup.md](hms-error-ui-mockup.md) | Visual mockup: layout diagrams, color scheme, responsive behavior |
| [hms-error-testing-guide.md](hms-error-testing-guide.md) | Testing guide: prerequisites, test scenarios, troubleshooting |

## Dependencies & Requirements

> **Foundation:** This feature requires the [Core](../core/README.md) and [Common](../common/README.md) packages and the [ha-bambulab](https://github.com/greghesp/ha-bambulab) integration — see [Foundation Packages](../../README.md#foundation-packages).

### Custom Frontend Cards (HACS)

| Card | Required | Purpose |
|---|---|---|
| [mushroom](https://github.com/piitaya/lovelace-mushroom) | **Yes** | `mushroom-template-card` for the alert banner |
| [card-mod](https://github.com/thomasloven/lovelace-card-mod) | No | Enhanced red styling on the banner — cosmetic only |

### Related Features

| Feature | Relationship |
|---|---|
| [Notifications](../notifications/README.md) | Can trigger mobile alerts based on HMS errors |
| [Printer Dashboards](../printer_dashboards/README.md) | HMS banner placement in the main dashboard view |
