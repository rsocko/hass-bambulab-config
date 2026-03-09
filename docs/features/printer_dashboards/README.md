# Dashboard Documentation

This directory contains the Home Assistant dashboards for the 3D Printer monitoring system.

## Files

- **lovelace.3d_printing** - Main 3D printer dashboard configuration (YAML format, paste directly into the Raw Dashboard Editor)
- **homeassistant/packages/3d_printing/** - Reusable Home Assistant package files (organized by feature and domain)
- **printer-temps.yaml** - Canonical temperature cards extracted from `view_main.yaml` and included via `!include`
- **print-progress-kpi-option-*.yaml** - Standalone print progress KPI option cards under `homeassistant/packages/3d_printing/print_progress/dashboard_cards/`
- **card templates** - Individual `button-card` templates are maintained in the `button_card_templates:` block in [homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing](../../../homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing)
- **docs/** - Documentation for dashboard features and customization

## Dashboard Features

### Top Bar
The dashboard features a prominent top bar with status information optimized for readability on both desktop and mobile devices. See [docs/top-bar-layout.md](docs/top-bar-layout.md) for detailed information.

Key features:
- Real-time print status and progress
- Time remaining and estimated completion time
- Live camera feeds
- Health monitoring system (HMS) error status

### Main Content Area
- Bambu Lab print status card with controls
- Advanced camera card with multiple views
- AMS (Automatic Material System) status
- Spool information and tracking

### AMS Tray Popup
Interactive popup dialogs for detailed spool information. See [docs/ams-tray-popup.md](docs/ams-tray-popup.md) for detailed information.

Key features:
- Click any AMS tray to open detailed spool information
- Color-coded filament display with brightness-adjusted text
- 7-day weight history chart
- Desiccant status tracking with age-based color indicators
- One-click desiccant reset button
- Direct link to Spoolman web interface
- Fallback display for unmatched or empty trays

### AMS Header Cards
Custom bubble-card separator headers placed above each AMS unit, replacing the built-in
`ha-bambulab-ams-card` header and info bar. See [card-templates-README.md](card-templates-README.md) for template variables.

Key features:
- Reusable `ams_header` button-card template with configurable variables
- Humidity sub-button with dynamic icon and color based on Bambu Lab's 1–5 rating (mapped to percentage thresholds)
- Temperature sub-button with color-coded background (blue → green → amber → orange → red)
- Replaces `subtitle` and `show_info_bar` on the AMS card for a cleaner, more informative display

### Print Details
The Print Details section includes an enhanced print weight visualization. See [docs/print-weight-bar-chart.md](docs/print-weight-bar-chart.md) for detailed information.

Key features:
- Horizontal stacked bar chart showing filament usage breakdown
- Each segment colored with actual filament color
- Percentage display for each filament (when segment is large enough)
- Total weight display
- Dark and light mode compatible with proper borders and contrast

### Temperature Monitoring
Standalone temperature display cards for nozzle and bed temperatures. See [docs/printer-temps-cards.md](docs/printer-temps-cards.md) or [docs/printer-temps-quick-start.md](docs/printer-temps-quick-start.md) for detailed information.

Key features:
- Real-time current and target temperature display
- Color-coded heating/cooling indicators (red = heating, blue = cooling, grey = at target)
- Fixed semantic icons with color-coded temperature state
- Horizontal compact layout for mobile and desktop
- Easy to paste into any dashboard view

### Print Progress Cards
Animated progress cards for monitoring active prints. Available as standalone KPI option files in `homeassistant/packages/3d_printing/print_progress/dashboard_cards/`.
See [docs/print-progress-options-guide.md](docs/print-progress-options-guide.md) for all thirteen issue #516 progress design variants.
See [docs/print-progress-dependencies.md](docs/print-progress-dependencies.md) for include wiring, required entities, and deployment caveats.

Key features:
- **Layer Progress** — layers icon bounces upward while printing, simulating layers piling up
- **Print Progress** — icon spins continuously while printing
- **Time Remaining** — clock icon rotates like spinning clock hands while printing
- **Est. Completion** — flag waves gently while printing; turns green when finished; smart human-readable time format:
  - Same day: `4:32 PM`
  - Next day: `4:32 PM tomorrow`
  - Within a week: `4:32 PM on Wednesday`
  - Farther away: `4:32 PM on 4/12/26`
- All animations stop automatically when the print is paused, stopped, or complete
- Finished-state visuals for KPI options now retain semantic colors (instead of gray) for configured icons/progress/fill elements
- 2×2 grid layout: Layer Progress + Print Progress (row 1), Time Remaining + Est. Completion (row 2)

## Custom Cards Required

The dashboard uses several custom cards that must be installed via HACS:

1. **ha-bambulab-print_status-card** - Bambu Lab specific print status
2. **ha-bambulab-ams-card** - AMS tray monitoring
3. **ha-bambulab-spool-card** - Filament spool information
4. **bubble-card** - Modern card design for status info
5. **mushroom** - Minimalist cards for sensors
6. **advanced-camera-card** - Enhanced camera viewing
7. **config-template-card** - Dynamic card templates
8. **button-card** - Customizable button cards (AMS tray templates and popup action buttons)
9. **auto-entities** - Dynamic entity lists
10. **vertical-layout** - Layout control
11. **grid-layout** - Grid layout control
12. **card-mod** (optional) - Custom styling
13. **browser-mod** - Required for AMS tray popup dialogs

## Installation

1. Install all required custom cards via HACS
2. Open your dashboard in Home Assistant → **Edit dashboard** → three-dot menu → **Raw configuration editor**
3. Paste the contents of **`lovelace.3d_printing`** into the editor
4. Update entity names to match your Bambu Lab printer configuration (see [Configuration](#configuration) below)
5. Click **Save** and reload the dashboard

> **No `configuration.yaml` changes are required.** The AMS tray card templates are defined
> in the `button_card_templates:` block at the top of `lovelace.3d_printing` and are immediately
> usable after pasting.

If you want to load the template sensors from `configuration.yaml`, use one of these patterns:

```yaml
sensor: !include_dir_merge_list template_sensors/
```

or point `sensor` directly to this feature folder:

```yaml
sensor: !include_dir_merge_list homeassistant/packages/3d_printing/
```

`!include_dir_merge_list` is not recursive, so files in nested folders are not auto-loaded when `sensor` points at `sensors/`.

### AMS Tray Templates

The AMS tray cards use three `button-card` templates (`ams_tray_label`, `ams_tray_detail`,
`ams_tray_popup`) and the `ams_header` template defined in the `button_card_templates:` block at the top of
`lovelace.3d_printing`. No external files or `configuration.yaml` entry are needed.

**Why `button_card_templates` is dashboard-level (not `configuration.yaml`):**
button-card reads `button_card_templates` from the Lovelace dashboard config object itself
(`ll.config`). It is not an HA integration key, so adding it to `configuration.yaml` will
cause the HA config checker to reject it. The templates must live in the dashboard YAML.

The source definitions are maintained directly in [homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing](../../../homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing):

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

See the `button_card_templates:` section in [homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing](../../../homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing) for the full variable reference.

## Configuration

### Entity Naming
The dashboard expects entities with the following naming pattern:
- `sensor.ntk_ryansoffice_3dprinter_*` - Various printer sensors
- `camera.ntk_ryansoffice_3dprinter_camera` - Printer camera
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
See [docs/top-bar-layout.md](docs/top-bar-layout.md) for details on customizing the top bar, including:
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


