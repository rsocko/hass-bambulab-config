# Printer Dashboards

How the main 3D printing dashboard is composed, laid out, and deployed. This section covers the **views and UI components** — for individual features, see the linked feature docs below.

## Dashboard Architecture

The dashboard is defined in [`homeassistant/packages/3d_printing/common/`](../../../homeassistant/packages/3d_printing/common/):

| File | Purpose |
|------|---------|
| `dashboards/_dashboards.yaml` | Lovelace dashboard registration |
| `dashboard_views/lovelace.3d_printing` | Root config with `button_card_templates:` and view includes |
| `dashboard_views/view_main.yaml` | Primary view assembling `!include` cards from all feature packages |

Each feature package contributes cards via its `dashboard_cards/` directory, which are `!include`d into `view_main.yaml`.

## Dashboard Layout

<!-- SCREENSHOT: id=dashboard-full-desktop | format=png | version=1.0 | package=printer_dashboards | added=2026-03-15 | captured=2026-03-15 -->

![Full dashboard — desktop overview](/docs/screenshots/images/dashboard-full-desktop.png)

<!-- SCREENSHOT: id=dashboard-full-mobile | format=png | version=1.0 | package=printer_dashboards | added=2026-03-15 | captured=2026-03-15 -->

![Full dashboard — mobile overview](/docs/screenshots/images/dashboard-full-mobile.png)

### Top Bar
Prominent status bar optimized for desktop and mobile. See [top-bar-layout.md](/docs/features/printer_dashboards/design/top-bar-layout.md) for layout design.

- Real-time print status and progress
- Time remaining and estimated completion
- Live camera feeds
- HMS error status badge

### Main Content Area
- Bambu Lab print status card with controls
- Advanced camera card with multiple views
- AMS status with interactive tray popups
- Spool information and tracking

### AMS Tray Popup
Interactive popup dialogs for detailed spool information. See [ams-tray-popup.md](/docs/features/printer_dashboards/reference/ams-tray-popup.md) and [ams-tray-popup-visual.md](/docs/features/printer_dashboards/design/ams-tray-popup-visual.md).

<!-- SCREENSHOT: id=ams-tray-popup-matched | format=png | version=1.0 | package=printer_dashboards | added=2026-03-15 | captured=2026-03-15 -->

![AMS tray popup — matched spool with full details](/docs/screenshots/images/ams-tray-popup-matched.png)

<!-- SCREENSHOT: id=ams-tray-popup-interaction | format=gif | version=1.0 | package=printer_dashboards | added=2026-03-15 -->
<!-- Capture: Record tap on AMS tray card → popup opens → scroll through details → close. ~5-8s loop (use ScreenToGif or ShareX GIF mode) -->
> **🎬 Animation needed:** AMS tray popup — tap-to-open interaction *(gif)*

### AMS Header Cards
Reusable `ams_header` button-card template placed above each AMS unit. See [card-templates-README.md](/docs/features/printer_dashboards/reference/card-templates-README.md).

### Feature Cards
Each feature contributes dashboard cards — see feature-specific docs:

| Dashboard Section | Feature Docs |
|-------------------|-------------|
| Error Alert Banner | [Error Alerts](/docs/features/error_alerts/README.md) |
| Temperature Cards | [Printer Temps](/docs/features/printer_temps/README.md) |
| Print Progress KPIs | [Print Progress](/docs/features/print_progress/README.md) |
| Weight & Cost | [Print Weight & Cost](/docs/features/print_weight_and_cost/README.md) |
| Fan Controls | [Printer Controls](/docs/features/printer_controls/README.md) |
| LED Controls | [Printer LED](/docs/features/printer_led/README.md) |
| Spool Tracking | [Spoolman Sync](/docs/features/spoolman_sync/README.md) |

## Dashboard-Specific Documentation

| File | Description |
|------|-------------|
| [top-bar-layout.md](/docs/features/printer_dashboards/design/top-bar-layout.md) | Top bar card layout and responsive grid |
| [ams-tray-popup.md](/docs/features/printer_dashboards/reference/ams-tray-popup.md) | AMS tray popup implementation and data sources |
| [ams-tray-popup-visual.md](/docs/features/printer_dashboards/design/ams-tray-popup-visual.md) | Visual mockup and layout guide |
| [active-spool-border.md](/docs/features/printer_dashboards/reference/active-spool-border.md) | Active spool cyan border indicator |
| [card-templates-README.md](/docs/features/printer_dashboards/reference/card-templates-README.md) | Reusable button-card templates (AMS header, tray label, tray detail, tray popup) |
| [animation-design-notes.md](/docs/features/printer_dashboards/design/animation-design-notes.md) | CSS animation design notes and patterns |
| [multicolor-spool-testing.md](/docs/features/printer_dashboards/reference/multicolor-spool-testing.md) | Testing guide for multi-color spool display |
| [yaml-conversion-status.md](/docs/features/printer_dashboards/planning/yaml-conversion-status.md) | YAML conversion status and known issues |

## Custom Cards Required (HACS)

1. **ha-bambulab-print_status-card** — Bambu Lab print status
2. **ha-bambulab-ams-card** — AMS tray monitoring
3. **ha-bambulab-spool-card** — Filament spool information
4. **bubble-card** — Modern card design
5. **mushroom** — Minimalist sensor cards
6. **advanced-camera-card** — Enhanced camera viewing
7. **config-template-card** — Dynamic card templates
8. **button-card** — Customizable buttons (AMS tray templates, popup actions)
9. **auto-entities** — Dynamic entity lists
10. **vertical-layout** / **grid-layout** — Layout control
11. **card-mod** (optional) — Custom styling
12. **browser-mod** — AMS tray popup dialogs

## Installation

1. Install all required custom cards via HACS
2. **Edit dashboard** → three-dot menu → **Raw configuration editor**
3. Paste contents of `lovelace.3d_printing`
4. Update entity names to match your printer
5. **Save** and reload

> The AMS tray card templates are defined in the `button_card_templates:` block at the top of `lovelace.3d_printing` — no `configuration.yaml` changes needed.

## Dependencies & Requirements

> **Foundation:** This feature requires the [Core](/docs/features/core/README.md) and [Common](/docs/features/common/README.md) packages and the [ha-bambulab](https://github.com/greghesp/ha-bambulab) integration — see [Foundation Packages](/docs/README.md#foundation-packages).

Printer Dashboards is the **aggregation layer** — it assembles cards contributed by all other features. Every feature with a `dashboard_cards/` directory is an implicit dependency.

### Feature Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| All features with `dashboard_cards/` | No (individually) | Each feature contributes cards via `!include` into `view_main.yaml`. Remove an `!include` line to remove that feature's cards from the dashboard. |

### Custom Frontend Cards (HACS)

See the [Custom Cards Required](#custom-cards-required-hacs) section above for the full list of 12 HACS cards. All are required for the full dashboard experience; `card-mod` is the only optional one (cosmetic styling).

### Related Features

| Feature | Relationship |
|---|---|
| [Core — Smart Status](/docs/features/core/README.md) | Status mapping used throughout the dashboard |

**Why `button_card_templates` is dashboard-level (not `configuration.yaml`):**
button-card reads `button_card_templates` from the Lovelace dashboard config object itself
(`ll.config`). It is not an HA integration key, so adding it to `configuration.yaml` will
cause the HA config checker to reject it. The templates must live in the dashboard YAML.

The source definitions are maintained directly in [homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing](../../../homeassistant/packages/3d_printing/common/dashboards/3d_printing.yaml):

| File | Template Name | Purpose |
|------|--------------|---------|
| `button_card_templates` in `lovelace.3d_printing` | `ams_header` | AMS unit header with humidity/temp indicators |
| `button_card_templates` in `lovelace.3d_printing` | `ams_tray_label` | Slot label card (A1, A2, B1, etc.) |
| `button_card_templates` in `lovelace.3d_printing` | `ams_tray_detail` | Full tray info card — appearance and data display |
| `button_card_templates` in `lovelace.3d_printing` | `ams_tray_popup` | Popup dialog — tap action with spool details |

Each AMS section in the dashboard uses:
```yaml
- type: vertical-stack
  card_mod:
    style: ':host { height: 100%; } #root { height: 100%; } #root > :last-child { flex: 1; }'
  cards:
    - type: custom:button-card
      template: ams_tray_label
      variables:
        trayName: A1
        trayEntityId: sensor.YOUR_PRINTER_ams_1_tray_1
    - type: custom:button-card
      template: ams_tray_detail
      variables:
        tray: ams_1_tray_1
        trayLabel: AMS 1 · Slot 1
        trayEntityId: sensor.YOUR_PRINTER_ams_1_tray_1
        printWeightKey: AMS 1 Tray 1
```

**Cross-dashboard reuse:** Copy the entire `button_card_templates:` block (from
`button_card_templates:` down to but not including `views:`) to the top of any other
dashboard YAML.

See the `button_card_templates:` section in [homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing](../../../homeassistant/packages/3d_printing/common/dashboards/3d_printing.yaml) for the full variable reference.

## Configuration

### Entity Naming
The dashboard expects entities with the following naming pattern:
- `sensor.ntk_ryansoffice_3dprinter_*` - Various printer sensors
- `camera.ntk_ryansoffice_3dprinter_camera` - Built-in printer camera
- `camera.3dprinter_front_camera_hd_stream` - Front camera view used by the advanced camera card
- `camera.3d_printer_top_tapo_c110_hd_stream` - Top camera view used by the advanced camera card
- `binary_sensor.ntk_ryansoffice_3dprinter_hms_errors` - HMS errors

Update these to match your actual entity names.

### Printer ID
Update the printer ID in the Bambu Lab card configuration:
```json
"printer": "YOUR_PRINTER_ID_HERE"
```

### Power Switch
If you have a smart switch controlling printer power, update:
```json
"custom_power": "switch.YOUR_POWER_SWITCH"
```

## Customization

### Top Bar Layout
See [top-bar-layout.md](/docs/features/printer_dashboards/design/top-bar-layout.md) for details on customizing the top bar, including:
- Changing grid columns
- Adjusting font sizes
- Adding new cards
- Modifying colors and icons

### Themes
The dashboard automatically adapts to your Home Assistant theme. For best results, use a theme with good contrast.

## Troubleshooting

### "Button-card template 'ams_tray_label' is missing!"

The `button_card_templates:` block at the top of the dashboard YAML is missing or was
accidentally deleted. Confirm the pasted YAML starts with `button_card_templates:` (before
`views:`). Copy it back from the `lovelace.3d_printing` file in this repository if needed.

### Cards Not Appearing
1. Verify all custom cards are installed (**button-card**, **browser-mod** via HACS)
2. Check browser console for errors
3. Verify entity names match your configuration
4. Clear browser cache and hard reload

### Mobile Layout Issues
1. Ensure you're using the latest Home Assistant mobile app
2. Try rotating device to force layout recalculation
3. Check that `columns` setting is appropriate for screen size

### Styling Not Applied
1. Verify card-mod is installed if using custom styles
2. Check for CSS syntax errors in style sections
3. Clear browser cache after making changes

## Contributing

When making changes to the dashboard:
1. Test on both desktop and mobile views
2. Verify JSON syntax is valid
3. Document any new custom cards required
4. Update this README if adding new features

## Related Resources

- [Home Assistant Lovelace Documentation](https://www.home-assistant.io/lovelace/)
- [Bambu Lab Integration](https://github.com/greghesp/ha-bambulab)
- [HACS - Custom Card Installation](https://hacs.xyz/)




