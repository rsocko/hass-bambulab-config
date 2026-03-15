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

## Additional Guides

| Guide | Description |
|---|---|
| [AUTOMATIONS.md](AUTOMATIONS.md) | How to enable/customize the interior light auto-reset automations |
| [CUSTOMIZATION_EXAMPLES.md](CUSTOMIZATION_EXAMPLES.md) | Light presets, advanced automations, input helpers, Node-RED, webhooks |
| [ESP32_INTEGRATION.md](ESP32_INTEGRATION.md) | ESPHome touchscreen button integration |
| [PHYSICAL_BUTTON_INTEGRATION.md](PHYSICAL_BUTTON_INTEGRATION.md) | Zigbee, Z-Wave, WiFi, and wired button setups |
| [VISUAL_EXAMPLES.md](VISUAL_EXAMPLES.md) | ASCII mockups and dashboard layout ideas |
| [dashboard-button-variants.yaml](dashboard-button-variants.yaml) | 5 alternative reset-button styles (Mushroom, standard, entity, Bubble, horizontal stack) |
| [LED_CONTROLS_README.md](LED_CONTROLS_README.md) | Quick start guide for expanded LED controls grid |
| [LED_CONTROLS_IMPLEMENTATION_SUMMARY.md](LED_CONTROLS_IMPLEMENTATION_SUMMARY.md) | Full implementation summary |
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
| `input_boolean.show_printer_controls` | Helper | Toggle controls panel visibility |

## Dependencies

- [Core](../core/README.md) — Smart status sensor
- [WLED](../wled/README.md) — WLED controller configuration and preset definitions
- [Common](../common/README.md) — Dashboard view includes
- `custom:mushroom-light-card`, `custom:button-card`, `browser-mod` (HACS)

## See Also

- [WLED](../wled/README.md) — Full WLED state machine, presets, and segment configuration
- [Printer Dashboards](../printer_dashboards/README.md) — Dashboard layout and placement
