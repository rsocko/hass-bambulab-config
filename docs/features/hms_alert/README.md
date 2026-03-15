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

## Documentation

| File | Description |
|------|-------------|
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
