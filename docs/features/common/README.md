# Common

Shared dashboard infrastructure — layouts, views, reusable card templates, and the main Lovelace dashboard definition.

## Implementation

**Package**: [`homeassistant/packages/3d_printing/common/`](../../../homeassistant/packages/3d_printing/common/)

### Structure

| Directory | Purpose |
|-----------|---------|
| `dashboards/` | Lovelace dashboard registration (`_dashboards.yaml`) |
| `dashboard_views/` | Main view files (`view_main.yaml`, `lovelace.3d_printing`) |
| `dashboard_cards/` | Shared card fragments used across multiple views |

### Key Files

- **`lovelace.3d_printing`** — Root dashboard configuration containing `button_card_templates:` (AMS header, tray label, tray detail, tray popup) and view includes.
- **`view_main.yaml`** — Primary view assembling cards from all feature packages via `!include`.

## Dependencies

- [Core](../core/README.md) — Smart status sensor, base template sensors
- All feature packages contribute `dashboard_cards/` that get included into `view_main.yaml`

## See Also

- [Printer Dashboards](../printer_dashboards/README.md) — Documentation focused on dashboard composition and UI behavior
- [card-templates-README.md](../printer_dashboards/card-templates-README.md) — Reusable button-card template reference
