# AMS Tray Custom Popup - 3D v4 Dashboard

## Overview

The 3D v4 dashboard now features custom popup dialogs for all AMS tray filament cards and the external spool card. When you click on any tray card, instead of the standard entity info dialog, you'll see a comprehensive custom popup with detailed spool information and controls.

## What's New in v4

The v4 dashboard has been enhanced with the same rich popup functionality available in the 3D printing dashboard:

- **All 9 locations** now have custom popups:
  - AMS 1: Trays 1-4
  - AMS 2: Trays 1-4
  - External Spool
  
- **JSON Format Compatibility**: All popup code is properly formatted as JSON-compatible JavaScript template strings, making it safe to copy directly into the raw config editor.

## Features

### 1. Spool Information Header
- Displays spool name or "No Spool Matched" if no match found
- Shows Spool ID or tray location identifier
- Color-tinted background based on filament color
- Icon color changes based on tray status (empty = disabled, else primary)

### 2. Material & Vendor Information
- **Material Type**: Displays filament material (PLA, PETG, TPU, etc.)
  - Icon: 🧱 mdi:texture-box (orange)
  - Shows "Unknown" if not available
- **Vendor/Manufacturer**: Shows brand name (Bambu Lab, eSun, etc.)
  - Icon: 🏭 mdi:factory (purple)
  - Shows "Unknown" if not available
- Displayed in horizontal layout for compact presentation

### 3. Color Display & Weight
- Large color swatch showing actual filament color
- Dynamically adjusts text color (black/white) based on background brightness
- Remaining weight display with icon
- Shows as "N/A" if weight data unavailable

### 4. Desiccant Status & Management
- Shows current desiccant status with color-coded icon:
  - 🟢 Green: < 30 days (auto-hidden)
  - 🟡 Yellow: 30-45 days
  - 🟠 Orange: 45-60 days
  - 🔴 Red: > 60 days
- Displays last filled date in localized format
- **"Reset Desiccant Date" button** with confirmation dialog
  - Calls `spoolman.patch_spool` service
  - Updates `desiccant_filled` timestamp to current time
  - Requires confirmation to prevent accidental resets

### 5. Spoolman Integration
- **"Open in Spoolman" button**: Opens Spoolman web UI for the spool
- Default URL: `http://homeassistant.local:7912/spools/{id}`
- Opens in new tab/window
- Provides quick access for detailed editing

### 6. Dynamic Weight History Chart
- **Automatically adjusts duration based on spool age**
- Uses `first_used` attribute to calculate days since spool was opened
- Shows complete usage history from opening to present
- Title dynamically displays: "Weight History (X days)"
- Falls back to 7 days if `first_used` date not available
- Shows remaining weight trend over time using built-in `history-graph` card
- Tracks weight consumption patterns

### 7. Fallback for Unmatched Trays
- When no spool is matched in Spoolman, shows raw AMS tray/external spool entity details
- Displays entities card with tray entity information
- Allows viewing what the printer detects (color, UUID, type, etc.)
- Useful for troubleshooting matching issues

### 8. More Details Button
- Quick access to full entity info dialog
- Shows all Spoolman attributes
- Standard Home Assistant entity details view

## How It Works

### Popup Trigger

Each tray card uses a `tap_action` with `fire-dom-event` to trigger a `browser_mod.popup`:

```javascript
tap_action: [[[
  const tray = 'ams_1_tray_1';
  const trayEntity = 'sensor.p1s_01p00c460102350_ams_1_tray_1';
  const map = states['sensor.spoolman_tray_map']?.attributes?.tray_map;
  const spoolId = map?.[tray]?.spool_id;
  const trayData = map?.[tray];

  return {
    action: 'fire-dom-event',
    browser_mod: {
      service: 'browser_mod.popup',
      data: {
        title: trayData?.name || 'AMS Tray Details',
        content: {
          // ... popup content cards ...
        }
      }
    }
  };
]]]
```

### Data Sources

- **Tray Mapping**: `sensor.spoolman_tray_map` (template sensor in templates.yaml)
  - Provides: `spool_id`, `name`, `desiccant`, `filled`, `status`, `color`, `reason`
  
- **Spool Entities**: `sensor.spoolman_spool_{id}`
  - Provides: `remaining_weight`, `filament_material`, `filament_vendor_name`, `first_used`, `location`, etc.
  
- **Tray Entities**: 
  - AMS: `sensor.p1s_01p00c460102350_ams_{n}_tray_{n}`
  - External: `sensor.ntk_ryansoffice_3dprinter_external_spool`
  - Provides: Raw tray data (color, UUID, type)

### Card Types Used

1. `custom:mushroom-template-card` - Header, status, material, and vendor displays
2. `custom:button-card` - Color swatch and action buttons
3. `history-graph` - Dynamic weight tracking over time
4. `entities` - Fallback tray information display
5. `vertical-stack` & `horizontal-stack` - Layout organization

## Testing the Popup

### Using the Standalone Test Card

A standalone test card is provided in `dashboards/ams-tray-popup-standalone.yaml` that you can use to test the popup functionality independently:

1. Open your Home Assistant dashboard in edit mode
2. Click "Add Card"
3. Choose "Manual" card type
4. Copy the entire contents of `ams-tray-popup-standalone.yaml`
5. Paste into the raw config editor
6. Click "Save"
7. Test the popup by clicking the card

The standalone card is configured for AMS 1 Tray 1 by default. You can modify the `tray` and `trayEntity` constants at the top of each JavaScript template section to test other trays.

## Customization

### Changing Spoolman URL

Update the Spoolman URL in the popup configuration to match your setup. Look for this section in the tap_action:

```javascript
url_path: `http://homeassistant.local:7912/spools/${spoolId}`
```

Common alternatives:
- **Local with hostname**: `http://homeassistant.local:7912/spools/${spoolId}`
- **Local with IP**: `http://192.168.1.100:7912/spools/${spoolId}`
- **External domain**: `https://spoolman.yourdomain.com/spools/${spoolId}`

### Adjusting History Duration

The history chart automatically adjusts based on spool age, but you can modify the logic:

```javascript
// Current: Shows full history since first_used
historyHours = daysSinceOpened * 24 || 24;

// Alternative: Cap at 30 days maximum
historyHours = Math.min(daysSinceOpened * 24, 720) || 24;

// Alternative: Fixed 14 days
historyHours = 336;
```

### Custom Color Brightness Threshold

The color contrast calculation uses an average brightness threshold of 128. To adjust text color on the color swatch:

```javascript
// Current: threshold of 128
(parseInt(color.substring(0,2), 16) + 
 parseInt(color.substring(2,4), 16) + 
 parseInt(color.substring(4,6), 16)) / 3 > 128 ? '#000' : '#fff'

// More black text: increase threshold
> 150 ? '#000' : '#fff'

// More white text: decrease threshold  
> 100 ? '#000' : '#fff'
```

## Troubleshooting

### Popup Doesn't Appear

1. **Check browser_mod is installed**
   - Install via HACS: https://github.com/thomasloven/hass-browser_mod
   - Restart Home Assistant after installation
   - Verify browser_mod appears in Settings → Devices & Services

2. **Clear browser cache**
   - Force refresh: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)
   - Clear all Home Assistant cached data

3. **Verify JavaScript Console**
   - Open browser developer tools (F12)
   - Check Console tab for errors
   - Look for errors mentioning "browser_mod" or "fire-dom-event"

### Missing Desiccant Section

- Desiccant section only appears if the spool has `extra_desiccant_in_spool` = true
- Set this attribute in Spoolman for spools with desiccant
- The section will be hidden (null-filtered) if desiccant is false

### History Graph Shows "No Data"

- Ensure Home Assistant is recording the spoolman sensor
- Check `recorder` configuration includes spoolman sensors
- Data accumulates over time - new spools won't have history initially
- Verify the spool entity exists: `sensor.spoolman_spool_{id}`

### Color Swatch Shows Gray

- Indicates no color data available
- Check that tray has filament loaded
- Verify `spoolman_tray_map` sensor has `color` attribute for the tray
- Check raw tray entity has color data

### Button Actions Don't Work

1. **Reset Desiccant button does nothing**
   - Verify `spoolman` integration is installed
   - Check that `spoolman.patch_spool` service exists
   - Ensure spool_id is valid

2. **Open in Spoolman doesn't work**
   - Verify Spoolman is running and accessible
   - Check the URL in tap_action matches your setup
   - Test the URL manually in a browser

## Features Not Yet Implemented

The following features from the original issue are planned but not yet implemented:

### ⏳ Pending Features

1. **Location Change Dropdown**
   - Would allow changing spool location directly from popup
   - Requires: Spoolman API integration to fetch available locations
   - Implementation: Use `input_select` or dropdown calling `spoolman.patch_spool` service

2. **Total Amount Across Other Spools**
   - Show total weight of all spools with same material
   - Show count of other spools with same color
   - Requires: Querying all `sensor.spoolman_spool_*` entities

3. **Related Spools Display**
   - Show other spools with same color/material
   - Display locations of related spools for quick reference
   - "Quick swap" recommendations

4. **Current Print Usage Amount**
   - Show amount of filament to be used in current print
   - Display per-tray estimated usage
   - Requires: Integration with print job data
   - Already partially available via print_weight sensor (shown on main card)

5. **Base Color Information**
   - Show base color category (Red, Blue, etc.) distinct from hex value
   - Group spools by base color for easier organization

## Requirements

- **Home Assistant**: 2023.4 or newer
- **Custom Components**:
  - `browser-mod` (HACS) - **Required** for popups
  - `button-card` (HACS) - **Required** for custom cards
  - `mushroom` (HACS) - **Required** for mushroom cards
- **Integrations**:
  - Spoolman integration configured
  - Bambu Lab printer integration configured

## Related Files

- `/dashboards/lovelace.3d_v4` - Main v4 dashboard configuration with popups
- `/dashboards/ams-tray-popup-standalone.yaml` - Standalone test card
- `/dashboards/templates.yaml` - `spoolman_tray_map` sensor definition
- `/dashboards/docs/ams-tray-popup.md` - Original popup documentation
- `/spoolman-sync/` - Spoolman synchronization automations

## Support

For issues or feature requests:
1. Check this documentation for troubleshooting steps
2. Verify all requirements are met
3. Check browser console for JavaScript errors
4. Report issues in the repository issue tracker

## Credits

This popup implementation is based on the original popup design in the `lovelace.3d_printing` dashboard, adapted and enhanced for the v4 dashboard with JSON-compatible formatting.
