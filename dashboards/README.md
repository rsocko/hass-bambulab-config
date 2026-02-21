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
8. **button-card** - Customizable button cards (also provides the global `button_card_templates` configuration key)
9. **declutter-card** - Reusable card structure templates (used for the `ams_tray_slot` template that wraps AMS tray cards)
10. **auto-entities** - Dynamic entity lists
11. **vertical-layout** - Layout control
12. **grid-layout** - Grid layout control
13. **card-mod** (optional) - Custom styling
14. **browser-mod** - Required for AMS tray popup dialogs

## Installation

1. Install all required custom cards via HACS
2. Copy the `dashboards/card-templates/` directory from this repository into your HA config
   directory so the layout looks like this:
   ```
   /config/                          ← HA config root (where configuration.yaml lives)
   ├── configuration.yaml
   └── dashboards/
       └── card-templates/
           ├── ams_tray_label.yaml
           ├── ams_tray_detail.yaml
           ├── ams_tray_popup.yaml
           └── ams_tray_slot.yaml
   ```
3. Add the following to your `configuration.yaml` **at the root level** (not nested under
   another key):
   ```yaml
   button_card_templates: !include_dir_merge_named dashboards/card-templates/
   ```
   > **Note:** There is no reload service for `button_card_templates`. Any future edits to
   > files in `dashboards/card-templates/` require another Home Assistant restart for the
   > changes to appear in Lovelace.
4. **Before restarting,** go to **Developer Tools → YAML → Check Configuration** and confirm
   no errors are reported. A YAML or schema error in any template file will cause HA to
   silently skip loading `button_card_templates`.
5. **Restart Home Assistant.**
6. After restart, go to **Settings → System → Logs** and search for `button_card_templates`
   or `card-templates` to confirm the templates loaded without errors.
7. Open your dashboard in Home Assistant → **Edit dashboard** → three-dot menu → **Raw configuration editor**
8. Paste the contents of **`lovelace.3d_printing`** into the editor
9. Update entity names to match your Bambu Lab printer configuration (see [Configuration](#configuration) below)
10. Click **Save** and reload the dashboard

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

### Declutter-Card Template

The `ams_tray_slot` declutter-card template (documented in
[`card-templates/ams_tray_slot.yaml`](card-templates/ams_tray_slot.yaml)) wraps the two
`custom:button-card` calls into a single, concise card reference. It is defined once at the
top of each dashboard YAML (in a `decluttercard:` block before `views:`) and then referenced
with `type: custom:declutter-card` wherever an AMS slot card is needed.

**Why both layers?**

- **`button_card_templates`** (global, `configuration.yaml`) — single source of truth for all
  card logic, styling, and popup behaviour. Defined once; available to every dashboard without
  any per-dashboard YAML.
- **`decluttercard`** (per-dashboard `decluttercard:` block) — defines the card *structure*
  (the `vertical-stack` that wraps label + detail) once per dashboard. Because it only
  references button-card template *names* (which are already global), the block is small and
  easy to copy into any new dashboard.

See [card-templates/README.md](card-templates/README.md) for the full template definition,
variable reference, and cross-dashboard usage instructions.

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

### "Integration error: button_card_templates - Integration 'button_card_templates' not found"

This error appears in **Developer Tools → YAML → Check Configuration** when Home Assistant
does not recognise `button_card_templates` as a valid configuration key. The key is registered
by the `button-card` custom component — if that component is not installed, HA reports it as
an unknown integration.

**Cause:** `button-card` was not installed via HACS, or was installed only as a manual
frontend resource (a `.js` file copied to `www/`) without the accompanying custom component.
Installing via HACS is required because the HACS package includes both the frontend resource
*and* a backend custom component that registers `button_card_templates` as a valid
configuration key.

**Fix:**
1. Open **HACS → Frontend** and install **button-card** (search for "button-card").
2. **Restart Home Assistant** so the custom component is loaded.
3. Re-run **Developer Tools → YAML → Check Configuration** — the error should be gone.
4. Continue with the normal [installation](#installation) steps.

---

### "Button-card template '…' is missing!" Error

This error appears when Home Assistant has not loaded `button_card_templates` from
`configuration.yaml`. Work through these steps in order:

1. Confirm your files are laid out correctly (see [Installation](#installation) directory tree above).
2. Confirm `configuration.yaml` contains the following **at the root level** (not indented
   under any other key):
   ```yaml
   button_card_templates: !include_dir_merge_named dashboards/card-templates/
   ```
   Both the relative path above and `/config/dashboards/card-templates/` work.
3. **Before restarting,** go to **Developer Tools → YAML → Check Configuration**. A YAML or
   schema error in any template file will cause HA to silently skip loading
   `button_card_templates` with no warning on the dashboard.
4. **Restart Home Assistant** — a configuration reload or dashboard reload is not sufficient.
   `button_card_templates` are only read at startup.
5. After restart, go to **Settings → System → Logs** and search for `button_card_templates`
   or `card-templates`. Any error logged here explains why the templates did not load.
6. After HA has fully restarted, hard-reload your browser (`Ctrl+Shift+R` / `Cmd+Shift+R`)
   to clear any cached dashboard state.

### Cards Not Appearing
1. Verify all custom cards are installed (including **declutter-card** via HACS)
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
