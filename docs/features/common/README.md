# Common

Shared dashboard infrastructure — layouts, views, reusable card templates, and the main Lovelace dashboard definition.

## Screenshots

<!-- SCREENSHOT: id=common-ams-header-card | format=png | version=1.0 | package=common | added=2026-03-15 -->
<!-- Capture: AMS header card showing humidity/temperature indicators for one AMS unit -->
> **📸 Screenshot needed:** AMS header card with humidity/temp indicators *(png)*

<!-- SCREENSHOT: id=common-ams-tray-cards | format=png | version=1.0 | package=common | added=2026-03-15 -->
<!-- Capture: Full AMS section showing header + 4 tray label/detail cards with filament colors and active spool border -->
> **📸 Screenshot needed:** AMS section — header + 4 tray cards with filament colors *(png)*

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

## Dependencies & Requirements

### Feature Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [Core](../core/README.md) | **Yes** | Smart status sensor, base template sensors — used in card templates and conditional cards |

### External Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [ha-bambulab](https://github.com/greghesp/ha-bambulab) | **Yes** | Printer entities referenced by dashboard cards and button-card templates |

### Custom Frontend Cards (HACS)

The cards defined in Common's templates require these custom cards to be installed:

| Card | Required | Purpose |
|---|---|---|
| [button-card](https://github.com/custom-cards/button-card) | **Yes** | AMS header, tray label, tray detail, and tray popup templates |
| [browser-mod](https://github.com/thomasloven/hass-browser_mod) | **Yes** | Popup dialog support for AMS tray interactions |

> **Common is consumed by every feature that contributes dashboard cards.** All feature `dashboard_cards/` directories are assembled into `view_main.yaml` via `!include`. If you add a new feature with UI cards, it depends on Common.

## See Also

- [Printer Dashboards](../printer_dashboards/README.md) — Documentation focused on dashboard composition and UI behavior
- [card-templates-README.md](../printer_dashboards/card-templates-README.md) — Reusable button-card template reference
