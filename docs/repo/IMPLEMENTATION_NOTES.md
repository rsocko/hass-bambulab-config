# AMS Tray Custom Popup - Implementation Summary

## Overview
This implementation adds custom popup dialogs for each AMS (Automatic Material System) tray filament card in the Bambu Lab 3D printing dashboard. When users click on any of the 8 AMS tray cards, they now see a detailed popup with comprehensive spool information instead of the default entity info dialog.

## Changes Made

### 1. Dashboard Configuration ([homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing](../../homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing))
- Modified `tap_action` for all 8 AMS tray cards (ams_1_tray_1 through ams_2_tray_4)
- Changed from `more-info` or `none` actions to custom `fire-dom-event` with `browser_mod.popup`
- Each popup dynamically generates content based on:
  - Matched spool data from `sensor.spoolman_tray_map`
  - Spool entity attributes from `sensor.spoolman_spool_{id}`
  - Raw tray data from AMS sensors when no match exists

### 2. Documentation ([docs/features/printer_dashboards/docs/ams-tray-popup.md](../features/printer_dashboards/docs/ams-tray-popup.md))
Created comprehensive documentation covering:
- All implemented features
- Data sources and structure
- Card types used
- Customization options
- Troubleshooting guide
- Future enhancement ideas
- Related files and support information

### 3. README Updates ([docs/features/printer_dashboards/README.md](../features/printer_dashboards/README.md))
- Added new "AMS Tray Popup" section under Main Content Area
- Listed key features of the popup
- Added `browser-mod` to the required custom cards list

## Features Implemented

### ✅ Core Functionality
1. **Interactive Popup Dialog**
   - Triggered by clicking any AMS tray card
   - Uses browser_mod for popup display
   - Dynamic title based on spool name or tray ID

2. **Spool Information Display**
   - Header card with spool name and ID
   - Color-tinted background matching filament color
   - Status-based icon color (empty = disabled, active = primary)

3. **Visual Color Display**
   - Large color swatch showing actual filament color
   - Smart text color (black/white) based on background brightness
   - Palette icon overlaid on color swatch

4. **Weight Information**
   - Current remaining weight display
   - 7-day weight history chart
   - Historical trend visualization

5. **Desiccant Management**
   - Color-coded status indicator (green/yellow/orange/red)
   - Shows last filled date
   - One-click reset button with confirmation
   - Calls spoolman.patch_spool service

6. **Spoolman Integration**
   - Direct link to Spoolman web interface
   - Opens specific spool detail page
   - Configurable URL (default: http://homeassistant.local:7912)

7. **Fallback Handling**
   - Shows AMS tray entity details when no spool matched
   - Displays raw tray data (color, UUID, type)
   - Allows viewing printer-detected information

8. **Quick Access**
   - "More Details" button to full entity info
   - Access to all Spoolman attributes
   - Additional spool metadata

## Technical Implementation

### Data Flow
```
User Click → tap_action → fire-dom-event → browser_mod.popup
                                              ↓
                            Read sensor.spoolman_tray_map
                                              ↓
                            Generate popup content
                                              ↓
                            Display vertical-stack of cards
```

### Card Structure
```
vertical-stack
├── mushroom-template-card (header)
├── horizontal-stack (color + weight)
│   ├── button-card (color swatch)
│   └── mushroom-template-card (weight)
├── vertical-stack (desiccant) [conditional]
│   ├── mushroom-template-card (status)
│   └── button-card (reset button)
├── button-card (Spoolman link)
├── history-graph (weight chart)
├── entities (tray fallback) [conditional]
└── button-card (more details)
```

### JavaScript Templates
Each popup uses JavaScript templates (`[[[...]]]]`) for:
- Dynamic data extraction from sensor states
- Conditional card display
- Color calculations
- Entity ID construction

## Requirements Met

Based on the original issue requirements:

✅ Show history of weight remaining - **Implemented** (7-day chart)
✅ Allow location change - **Implemented** (native spoolman spool location select entity from v1.1)
✅ Button to reset Desiccant filled date - **Implemented** (with confirmation)
✅ Show icon/color - **Implemented** (large color swatch with smart text color)
❌ Show other fields - **Partially implemented** (access via More Details button)
❌ Show other spool locations - **Not implemented** (documented as future enhancement)
✅ Open URL to spoolman UX - **Implemented** (configurable URL)
❌ Amount to be used in current print - **Not implemented** (documented as future enhancement)
✅ Show AMS details when no spool found - **Implemented** (entities card with tray data)

## Dependencies

### Required Custom Cards
- **browser-mod** (NEW) - For popup functionality
- **mushroom** - Template cards in popup
- **button-card** - Color swatch and action buttons
- History-graph (built-in) - Weight chart

### Required Integrations
- Spoolman integration with sensor entities
- Bambu Lab integration with AMS tray sensors
- Template sensor: `sensor.spoolman_tray_map`

## Testing Recommendations

The implementation should be tested in the following scenarios:

1. **Matched Spool (Normal Case)**
   - Click tray with matched spoolman spool
   - Verify all information displays correctly
   - Test desiccant reset button
   - Test Spoolman link opens correctly

2. **Unmatched Tray**
   - Click tray with no matching spool
   - Verify fallback entities card appears
   - Confirm tray data is visible

3. **Empty Tray**
   - Click empty tray slot
   - Verify appropriate message/status
   - Ensure no errors in browser console

4. **Desiccant Status**
   - Test with spools of different desiccant ages
   - Verify correct color coding (green/yellow/orange/red)
   - Test reset functionality

5. **Browser Compatibility**
   - Test on desktop browsers (Chrome, Firefox, Safari)
   - Test on mobile devices (iOS, Android)
   - Verify layout responsiveness

## Future Enhancements

The following features are documented but not yet implemented:

1. **Extended Spool Information**
   - Material type display (PLA, PETG, etc.)
   - Vendor/manufacturer name
   - Total spool weight
   - Date opened/first used

2. **Related Spools**
   - Show other spools with same color
   - Show other spools with same material
   - Quick location finder

3. **Print Integration**
   - Estimated consumption for current print
   - Weight needed per color
   - Sufficiency warning

4. **Advanced Features**
   - Filament age tracking
   - Custom notes/ratings
   - Print success rate
   - Quality warnings

## Files Modified

1. `/homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing` - Main dashboard (8 tap_action updates)
2. `/docs/features/printer_dashboards/README.md` - Feature documentation and requirements
3. `/docs/features/printer_dashboards/docs/ams-tray-popup.md` - Detailed popup documentation (NEW)

## Validation

- ✅ JSON syntax validated
- ✅ No build errors
- ✅ Documentation complete
- ⏳ UI testing pending (requires Home Assistant instance)

## Notes for Deployment

1. **Ensure browser-mod is installed**
   - Install via HACS
   - Restart Home Assistant
   - Clear browser cache

2. **Customize Spoolman URL if needed**
   - Update in each tap_action
   - Match your Spoolman instance location

3. **Review desiccant service call**
   - Ensure spoolman.patch_spool service exists
   - Verify extra.desiccant_filled field is supported

4. **Check history recording**
   - Ensure spoolman sensors are recorded
   - May need recorder configuration update

## Support and Issues

For issues with this implementation:
1. Check browser console for JavaScript errors
2. Verify browser-mod is properly installed
3. Ensure all sensor entities exist
4. Review documentation in `/docs/features/printer_dashboards/docs/ams-tray-popup.md`

---

**Implementation Date**: 2026-02-16
**Author**: GitHub Copilot
**Issue**: Custom popup for each spool to show more details / controls



