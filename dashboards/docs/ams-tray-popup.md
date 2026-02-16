# AMS Tray Custom Popup

## Overview

This document describes the custom popup dialog that appears when clicking on an AMS tray filament card in the 3D printing dashboard.

## Features Implemented

### ✅ Core Features

1. **Spool Information Header**
   - Displays spool name or "No Spool Matched" if no match found
   - Shows Spool ID or Tray location
   - Color-tinted background based on filament color
   - Icon color changes based on tray status (empty = disabled, else primary)

2. **Color Display & Weight**
   - Large color swatch showing actual filament color
   - Dynamically adjusts text color (black/white) based on background brightness
   - Remaining weight display with icon

3. **Desiccant Status & Management**
   - Shows current desiccant status with color-coded icon:
     - 🟢 Green: < 30 days (auto-hidden)
     - 🟡 Yellow: 30-45 days
     - 🟠 Orange: 45-60 days
     - 🔴 Red: > 60 days
   - Displays last filled date
   - "Reset Desiccant Date" button with confirmation dialog
   - Calls `spoolman.patch_spool` service to update desiccant_filled timestamp

4. **Spoolman Integration**
   - "Open in Spoolman" button - opens Spoolman web UI for the spool
   - Default URL: `http://homeassistant.local:7912/spools/{id}`
   - Can be customized based on your Spoolman instance location

5. **Weight History Chart**
   - 7-day (168 hours) history graph
   - Shows remaining weight trend over time
   - Uses built-in `history-graph` card

6. **Fallback for Unmatched Trays**
   - When no spool is matched in Spoolman, shows AMS tray entity details
   - Allows viewing raw tray data (color, UUID, type, etc.)
   - User can still see what the printer detects

7. **More Details Button**
   - Quick access to full entity info dialog
   - Shows all Spoolman attributes

## Implementation Details

### Popup Trigger

Each of the 8 AMS tray cards uses a `tap_action` with `fire-dom-event` to trigger a `browser_mod.popup`:

```javascript
tap_action: {
  action: 'fire-dom-event',
  browser_mod: {
    service: 'browser_mod.popup',
    data: {
      title: 'Spool Name or Tray ID',
      content: { /* card configuration */ }
    }
  }
}
```

### Data Sources

- **Tray Mapping**: `sensor.spoolman_tray_map` (template sensor in templates.yaml)
  - Provides: spool_id, name, desiccant, filled, status, color, reason
- **Spool Entities**: `sensor.spoolman_spool_{id}`
  - Provides: remaining_weight, filament attributes, location, etc.
- **Tray Entities**: `sensor.p1s_01p00c460102350_ams_{n}_tray_{n}`
  - Provides: Raw tray data (color, UUID, type)

### Card Types Used

1. `custom:mushroom-template-card` - Header and status displays
2. `custom:button-card` - Color swatch and action buttons
3. `history-graph` - Weight tracking over time
4. `entities` - Fallback tray information
5. `vertical-stack` & `horizontal-stack` - Layout organization

## Features Not Yet Implemented

The following features from the original requirement are not yet implemented:

### ⏳ Pending Features

1. **Location Change Dropdown**
   - Requires: Spoolman integration to support location changes
   - Implementation: Would use `input_select` or dropdown calling `spoolman.patch_spool` service
   - Challenge: Need to know available locations from Spoolman

2. **Additional Spool Information**
   - Material type (PLA, PETG, TPU, etc.)
   - Vendor/manufacturer name
   - Total weight (initial spool weight)
   - Could be added as an entities card or additional mushroom cards

3. **Related Spools Display**
   - Show other spools with same color
   - Show other spools with same material
   - Location of other spools for quick reference
   - Implementation: Would require querying all `sensor.spoolman_spool_*` entities

4. **Current Print Usage**
   - Amount of filament to be used in current print
   - Requires: Integration with print job data
   - Would show estimated usage per color from current print

## Customization

### Changing Spoolman URL

Update the Spoolman URL in the popup configuration:

```javascript
url_path: `http://YOUR_SPOOLMAN_HOST:7912/spools/${spoolId}`
```

Common alternatives:
- Local: `http://homeassistant.local:7912/spools/${spoolId}`
- IP Address: `http://192.168.1.100:7912/spools/${spoolId}`
- External: `https://spoolman.yourdomain.com/spools/${spoolId}`

### Adjusting History Duration

Change the `hours_to_show` parameter in the history-graph card:

```javascript
hours_to_show: 168  // Default: 7 days
hours_to_show: 336  // 14 days
hours_to_show: 720  // 30 days
```

### Custom Color Brightness Threshold

The color contrast calculation uses an average brightness threshold of 128. To adjust:

```javascript
// Current calculation
(parseInt(color.substring(0,2), 16) + 
 parseInt(color.substring(2,4), 16) + 
 parseInt(color.substring(4,6), 16)) / 3 > 128 ? '#000' : '#fff'

// Make threshold higher for more black text
> 150 ? '#000' : '#fff'

// Make threshold lower for more white text  
> 100 ? '#000' : '#fff'
```

## Troubleshooting

### Popup Doesn't Appear

1. **Check browser_mod is installed**
   - Install via HACS if missing
   - Restart Home Assistant

2. **Verify JavaScript Console**
   - Open browser developer tools (F12)
   - Check for errors in console

### Missing Desiccant Button

- Button only appears if spool has `extra_desiccant_in_spool` = true
- Set this in Spoolman for spools with desiccant

### History Graph Shows "No Data"

- Ensure Home Assistant is recording the sensor
- Check `recorder` configuration includes spoolman sensors
- Data takes time to accumulate

### Color Swatch Shows Gray

- Indicates no color data available
- Check that tray has filament loaded
- Verify spoolman_tray_map sensor has color attribute

## Future Enhancements

Potential improvements for future versions:

1. **Dynamic Location Selector**
   - Query Spoolman API for available locations
   - Use `input_select` or custom dropdown
   - Update spool location via service call

2. **Multi-Spool Comparison**
   - Side-by-side comparison of spools with same material
   - Show which has most weight remaining
   - Quick-swap recommendations

3. **Print Estimation Integration**
   - Pull data from current print job
   - Show estimated consumption by color
   - Warn if spool weight is insufficient

4. **Filament Age Tracking**
   - Show when spool was first used
   - Display total days since opening
   - Age-based quality warnings

5. **Custom Notes Field**
   - Add notes about filament quality
   - Print success rate tracking
   - Personal ratings/reviews

## Related Files

- `/dashboards/lovelace.3d_printing` - Main dashboard configuration
- `/dashboards/templates.yaml` - spoolman_tray_map sensor definition
- `/spoolman-sync/` - Spoolman synchronization automations

## Support

For issues or feature requests, please refer to the repository's issue tracker.
