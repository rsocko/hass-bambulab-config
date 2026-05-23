# Error Alerts

Unified error detection, display, and alerting for Bambu Lab printers. Aggregates HMS hardware errors and print errors into a single dashboard section with severity-adaptive colors, type badges, and contextual action buttons.

## Implementation

**Package**: [`homeassistant/packages/3d_printing/error_alerts/`](../../../homeassistant/packages/3d_printing/error_alerts/)

### Structure

| Directory | Purpose |
|-----------|---------|
| `automations/` | Error logging, clear-on-resolve, and alert automation |
| `dashboard_cards/` | Unified error alert banner card (HMS + print errors) |
| `helpers/` | Input booleans and selects for preview/test mode |
| `template_sensors/` | Unified display wrapper (aggregates HMS + print errors) |

### Key Entities

- `binary_sensor.error_alert_display_wrapper` — `on` when any error present; `errors` attribute contains all active errors with type, severity, code, message, and wiki
- `input_boolean.error_alert_test_mode` — Enable preview/test scenarios
- `input_select.error_alert_test_scenario` — Select from 11 test scenarios

## Screenshots

<!-- SCREENSHOT: id=hms-alert-single-error | format=png | version=1.0 | package=error_alerts | added=2026-03-15 -->
<!-- Capture: Single error expanded — show red banner with error description, code, and wiki link -->
> **📸 Screenshot needed:** Error alert banner — single error expanded *(png)*

<!-- SCREENSHOT: id=hms-alert-multiple-errors | format=png | version=1.0 | package=error_alerts | added=2026-03-15 -->
<!-- Capture: Multiple errors (2-3) showing severity-colored cards (red/orange/yellow) in flex-wrap layout -->
> **📸 Screenshot needed:** Error alert banner — multiple errors with severity colors *(png)*

<!-- SCREENSHOT: id=hms-alert-collapse-toggle | format=gif | version=1.0 | package=error_alerts | added=2026-03-15 -->
<!-- Capture: Record expand/collapse toggle — tap chevron to collapse, tap again to expand. ~3-4s loop (use ScreenToGif) -->
> **🎬 Animation needed:** Error alert banner — expand/collapse interaction *(gif)*

<!-- SCREENSHOT: id=hms-alert-no-errors | format=png | version=1.0 | package=error_alerts | added=2026-03-15 -->
<!-- Capture: Dashboard with no errors present — show that error alert section is completely hidden (clean dashboard) -->
> **📸 Screenshot needed:** Dashboard with no errors — banner hidden *(png)*

## Documentation

| File | Description |
|------|-------------|
| [error-alerts-unified-design.md](design/error-alerts-unified-design.md) | **Unified design:** Consolidates HMS + print errors into one "Error Alerts" system — phased implementation plan |
| [hms-error-alert-implementation.md](reference/hms-error-alert-implementation.md) | Technical implementation: architecture, card structure, template syntax, styling |
| [hms-error-ui-mockup.md](design/hms-error-ui-mockup.md) | Visual mockup: layout diagrams, color scheme, responsive behavior |
| [hms-error-testing-guide.md](reference/hms-error-testing-guide.md) | Testing guide: prerequisites, test scenarios, troubleshooting |

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
