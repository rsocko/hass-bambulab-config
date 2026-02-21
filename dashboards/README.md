# Dashboard Documentation

This directory contains the Home Assistant dashboards for the 3D Printer monitoring system.

## Files

- **lovelace.3d_printing** - Main 3D printer dashboard configuration (YAML format, paste directly into the Raw Dashboard Editor)
- **templates.yaml** - Reusable Home Assistant template sensors (spoolman tray map, filament totals)
- **printer-temps.yaml** - Temperature display cards for nozzle and bed (separate, paste-able YAML)
- **printer-temps-example.yaml** - Ready-to-use temperature cards with repository entity names
- **card-templates/** - Individual `button-card` template files (one per template); see [card-templates/README.md](card-templates/README.md)
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
- Dynamic icons showing temperature state
- Horizontal compact layout for mobile and desktop
- Easy to paste into any dashboard view

## Custom Cards Required

The dashboard uses several custom cards that must be installed via HACS:

1. **ha-bambulab-print_status-card** - Bambu Lab specific print status
2. **ha-bambulab-ams-card** - AMS tray monitoring
3. **ha-bambulab-spool-card** - Filament spool information
4. **bubble-card** - Modern card design for status info
5. **mushroom** - Minimalist cards for sensors
6. **advanced-camera-card** - Enhanced camera viewing
7. **config-template-card** - Dynamic card templates
8. **button-card** - Customizable button cards
9. **auto-entities** - Dynamic entity lists
10. **vertical-layout** - Layout control
11. **grid-layout** - Grid layout control
12. **card-mod** (optional) - Custom styling
13. **browser-mod** - Required for AMS tray popup dialogs

## Installation

1. Install all required custom cards via HACS
2. Add the following to your `configuration.yaml` and **restart Home Assistant**:
   ```yaml
   button_card_templates: !include_dir_merge_named /config/dashboards/card-templates/
   ```
3. Open your dashboard in Home Assistant → **Edit dashboard** → three-dot menu → **Raw configuration editor**
4. Paste the contents of **`lovelace.3d_printing`** into the editor
5. Update entity names to match your Bambu Lab printer configuration (see [Configuration](#configuration) below)
6. Click **Save** and reload the dashboard

### Button-Card Templates

The AMS tray cards use three `custom:button-card` templates defined in
[`card-templates/`](card-templates/). They are loaded globally via `configuration.yaml`,
making them available to **all** dashboards including UI-managed ones.

| Template File | Template Name | Purpose |
|---|---|---|
| `card-templates/ams_tray_label.yaml` | `ams_tray_label` | Slot label card (A1, A2, B1, etc.) |
| `card-templates/ams_tray_detail.yaml` | `ams_tray_detail` | Full tray info card — card appearance and data display |
| `card-templates/ams_tray_popup.yaml` | `ams_tray_popup` | Popup dialog — tap action that opens the spool details popup |

`ams_tray_detail` inherits its `tap_action` from `ams_tray_popup` via template inheritance. To modify the popup appearance or behavior, edit only `ams_tray_popup.yaml`. To modify the card appearance, edit `ams_tray_detail.yaml`.

See [card-templates/README.md](card-templates/README.md) for full variable reference and instructions for reusing these templates in other dashboards.

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

### Cards Not Appearing
1. Verify all custom cards are installed
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
