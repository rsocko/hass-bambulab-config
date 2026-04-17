# Printer LED Package

## Overview

The `printer_led` package provides unified control over all LED lighting associated with the Bambu Lab 3D printer, including:

- **MagWLED** — Interior top LED strip (WLED RGBIC)
- **Chamber Light** — Built-in Bambu Lab chamber LED
- **DigQuad AMS Tray Lights** — AMS 1 & 2 tray illumination (WLED RGBIC)
- **DigQuad AMS Tag LEDs** — Individual filament tag LEDs (WLED RGBIC)
- **DigQuad Front LED** — Print progress bar and status indicators (WLED RGBIC)

## Package Contents

### Deployed Configuration

| Component | File | Description |
|---|---|---|
| Loader | `printer_led_loader.yaml` | Registers helpers and scripts with HA |
| Script | `scripts/reset_interior_light_to_white-script.yaml` | Resets MagWLED to 100% bright white |
| Script | `scripts/printer_led_magwled_photo_lighting-script.yaml` | Snapshots MagWLED into a temporary scene, applies solid cool white for photos, then restores it |
| Helper | `helpers/input_boolean_show_printer_controls.yaml` | Toggle to show/hide printer controls panel |
| Automations | `automations/printer_led_automations.yaml` | 3 optional auto-reset automations (disabled by default) |

### Dashboard Cards

| Card | File | Description |
|---|---|---|
| Compact row | `dashboard_cards/printer-led-controls.yaml` | 6-button icon row for dashboard header (chamber, MagWLED, reset, DigQuad×2, controls toggle) |
| Expanded grid | `dashboard_cards/led-controls-expanded.yaml` | Full 7-light control grid with effects, palettes, all-on/off, status overview |

## Quick Start

1. Ensure the package loader is included via `_feature_loaders.yaml` or `configuration.yaml`:

   ```yaml
   homeassistant:
     packages:
       printer_led: !include packages/3d_printing/printer_led/printer_led_loader.yaml
   ```

2. Add a dashboard card — copy either compact or expanded card YAML into your dashboard via Edit Dashboard → Add Card → Manual.

3. (Optional) Enable automations — see [AUTOMATIONS.md](AUTOMATIONS.md).

## Screenshots

<!-- SCREENSHOT: id=led-controls-compact | format=png | version=1.0 | package=printer_led | added=2026-03-15 | captured=2026-03-15 -->

![LED controls — compact icon row](../../screenshots/images/led-controls-compact.png)

<!-- SCREENSHOT: id=led-controls-expanded-grid | format=png | version=1.0 | package=printer_led | added=2026-03-15 -->
<!-- Capture: Full 7-light control grid showing all LED entities with brightness sliders and status -->
> **📸 Screenshot needed:** LED controls — expanded grid with all 7 lights *(png)*

<!-- SCREENSHOT: id=led-wled-popup | format=gif | version=1.0 | package=printer_led | added=2026-03-15 -->
<!-- Capture: Double-tap a WLED light → popup opens with effect/palette/speed controls → change effect → close. ~8s (use ScreenToGif) -->
> **🎬 Animation needed:** WLED advanced popup — effect selection interaction *(gif)*

<!-- SCREENSHOT: id=led-physical-strips | format=gif | version=1.0 | package=printer_led | added=2026-03-15 -->
<!-- Capture: Film physical LED strips on printer — show state transition (idle blue → printing green). Phone camera → convert to GIF -->
> **🎬 Animation needed:** Physical LED strips — state transition on hardware *(gif)*

## Additional Guides

| Guide | Description |
|---|---|
| [AUTOMATIONS.md](AUTOMATIONS.md) | How to enable/customize the interior light auto-reset automations |
| [customization-examples.md](customization-examples.md) | Light presets, advanced automations, input helpers, Node-RED, webhooks |
| [esp32-integration.md](esp32-integration.md) | ESPHome touchscreen button integration |
| [physical-button-integration.md](physical-button-integration.md) | Zigbee, Z-Wave, WiFi, and wired button setups |
| [visual-examples.md](visual-examples.md) | ASCII mockups and dashboard layout ideas |
| [dashboard-button-variants.yaml](dashboard-button-variants.yaml) | 5 alternative reset-button styles (Mushroom, standard, entity, Bubble, horizontal stack) |
| [led-controls-readme.md](led-controls-readme.md) | Quick start guide for expanded LED controls grid |
| [led-controls-implementation-summary.md](led-controls-implementation-summary.md) | Full implementation summary |
| [led-controls.md](led-controls.md) | Comprehensive LED controls documentation (7 lights, WLED config, troubleshooting) |
| [led-controls-visual.md](led-controls-visual.md) | Visual reference guide with ASCII layouts and state visualizations |
| [led-controls-integration-examples.md](led-controls-integration-examples.md) | 9 integration methods with code examples |

## Key Entities

| Entity | Type | Purpose |
|---|---|---|
| `light.magwled` | Light | MagWLED interior top strip |
| `light.ntk_ryansoffice_3dprinter_chamber_light` | Light | Built-in chamber light |
| `light.dig_quad_v3` | Light | DigQuad front progress LED |
| `light.dig_quad_v3_segment_1` | Light | DigQuad front status segment |
| `script.reset_interior_light_to_white` | Script | Reset MagWLED to white |
| `script.printer_led_magwled_photo_lighting` | Script | Snapshot, apply, and restore MagWLED photo lighting |
| `input_boolean.show_printer_controls` | Helper | Toggle controls panel visibility |

## Dependencies & Requirements

> **Foundation:** This feature requires the [Core](../core/README.md) and [Common](../common/README.md) packages and the [ha-bambulab](https://github.com/greghesp/ha-bambulab) integration — see [Foundation Packages](../../README.md#foundation-packages).

### Feature Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [WLED](../wled/README.md) | **Yes** | WLED controller configuration, presets, and state machine that drives the LED strips |

### External Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| WLED controllers (DigQuad + MagWLED) | **Yes** | Physical LED controllers running WLED firmware |
| [WLED HA integration](https://www.home-assistant.io/integrations/wled/) | **Yes** | Built-in HA integration for WLED device control |

### Custom Frontend Cards (HACS)

| Card | Required | Purpose |
|---|---|---|
| [mushroom](https://github.com/piitaya/lovelace-mushroom) | **Yes** | `mushroom-light-card` for light controls |
| [button-card](https://github.com/custom-cards/button-card) | **Yes** | Customizable LED toggle buttons |
| [browser-mod](https://github.com/thomasloven/hass-browser_mod) | **Yes** | Popup dialogs for expanded LED controls |

### Related Features

| Feature | Relationship |
|---|---|
| [WLED](../wled/README.md) | Full WLED state machine, presets, and segment configuration |
| [Printer Dashboards](../printer_dashboards/README.md) | Dashboard layout and placement |

