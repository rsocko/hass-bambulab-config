# Active Spool Border Feature

## Overview

This feature adds a visual indicator to the AMS tray spool cards displayed below the AMS card in the 3D printing dashboard. When a tray is actively being used by the printer, its corresponding spool card will display a colored border matching the filament color, similar to how the AMS card itself indicates the active tray.

## Implementation

### How it Works

1. **Active Tray Detection**: The feature uses the `sensor.ntk_ryansoffice_3dprinter_active_tray` sensor which provides a `tray_uuid` attribute indicating which tray is currently active.

2. **UUID Matching**: Each tray entity (e.g., `sensor.p1s_01p00c460102350_ams_1_tray_1`) also has a `tray_uuid` attribute. The code compares these UUIDs to determine if a specific tray is the active one.

3. **Dynamic Border Styling**: When a tray is active, the button-card applies:
   - A 3px solid border using the filament color from `sensor.spoolman_tray_map`
   - An 8px border-radius for a rounded appearance
   - Falls back to `var(--primary-color)` if no color is available

### Code Structure

The implementation uses JavaScript template syntax in the `styles` field of each button-card:

```javascript
"styles": "[[[\n  const tray = 'ams_1_tray_1';\n  const trayEntity = 'sensor.p1s_01p00c460102350_ams_1_tray_1';\n  const activeTray = states['sensor.ntk_ryansoffice_3dprinter_active_tray'];\n  const activeTrayUuid = activeTray?.attributes?.tray_uuid;\n  const thisTrayUuid = states[trayEntity]?.attributes?.tray_uuid;\n  const isActive = activeTrayUuid && thisTrayUuid && activeTrayUuid === thisTrayUuid;\n  \n  // Get tray color for border\n  const map = states['sensor.spoolman_tray_map']?.attributes?.tray_map;\n  const trayColor = map?.[tray]?.color;\n  const borderColor = trayColor ? '#' + trayColor : 'var(--primary-color)';\n  \n  return {\n    card: [\n      { 'padding': '6px' },\n      { 'background': 'none' },\n      { 'box-shadow': 'none' },\n      ...(isActive ? [{ 'border': `3px solid ${borderColor}` }, { 'border-radius': '8px' }] : [])\n    ],\n    // ... rest of styles\n  };\n]]]\n"
```

### Coverage

The feature is implemented for all 8 AMS trays:
- ✅ AMS 1 - Tray 1 (ams_1_tray_1)
- ✅ AMS 1 - Tray 2 (ams_1_tray_2)
- ✅ AMS 1 - Tray 3 (ams_1_tray_3)
- ✅ AMS 1 - Tray 4 (ams_1_tray_4)
- ✅ AMS 2 - Tray 1 (ams_2_tray_1)
- ✅ AMS 2 - Tray 2 (ams_2_tray_2)
- ✅ AMS 2 - Tray 3 (ams_2_tray_3)
- ✅ AMS 2 - Tray 4 (ams_2_tray_4)

## Visual Behavior

### When Active
- The spool card displays a **3px solid border**
- Border color matches the **filament color** from the spool
- Border has an **8px radius** for smooth corners
- All existing card styling (padding, background, etc.) is preserved

### When Inactive
- No border is shown (box-shadow: none)
- Card appears with default transparent background
- No visual difference from the previous implementation

## Dependencies

### Sensors Required
1. **sensor.ntk_ryansoffice_3dprinter_active_tray**
   - Provides: `tray_uuid` attribute
   - Updated by printer when active tray changes

2. **sensor.spoolman_tray_map**
   - Provides: Color information for each tray
   - Located in: `dashboards/templates.yaml`

3. **Tray Entity Sensors**
   - Format: `sensor.p1s_01p00c460102350_ams_[1-2]_tray_[1-4]`
   - Provides: `tray_uuid` attribute for matching

### Custom Cards
- **custom:button-card** - Used for spool display cards

## Customization

### Changing Border Width

To modify the border thickness, update the border property:

```javascript
// From:
{ 'border': `3px solid ${borderColor}` }

// To (example: 5px):
{ 'border': `5px solid ${borderColor}` }
```

### Changing Border Radius

To adjust the corner rounding:

```javascript
// From:
{ 'border-radius': '8px' }

// To (example: sharper corners):
{ 'border-radius': '4px' }

// Or (example: pill-shaped):
{ 'border-radius': '12px' }
```

### Using a Different Color

To use a fixed color instead of the filament color:

```javascript
// Replace:
const borderColor = trayColor ? '#' + trayColor : 'var(--primary-color)';

// With (example: always use blue):
const borderColor = '#0066cc';
```

### Adding a Glow Effect

To add a subtle glow/shadow to the border:

```javascript
...(isActive ? [
  { 'border': `3px solid ${borderColor}` }, 
  { 'border-radius': '8px' },
  { 'box-shadow': `0 0 10px ${borderColor}40` }  // Add 40 for 25% opacity
] : [])
```

## Troubleshooting

### Border Not Showing

**Problem**: Active tray doesn't show a border

**Possible Causes & Solutions**:

1. **Active tray sensor unavailable**
   - Check if `sensor.ntk_ryansoffice_3dprinter_active_tray` exists
   - Verify the sensor has a valid `tray_uuid` attribute

2. **UUID mismatch**
   - Ensure tray entities have `tray_uuid` attributes
   - Verify UUIDs match between active_tray sensor and tray entities

3. **Spoolman integration issue**
   - Check `sensor.spoolman_tray_map` is available
   - Verify tray_map contains color data for the tray

### Wrong Tray Highlighted

**Problem**: Border appears on the wrong tray

**Cause**: The tray entity name or tray key doesn't match

**Solution**: Verify the `tray` variable and `trayEntity` variable match your actual entity names in the JavaScript template.

### Border Always Shows

**Problem**: Border appears even when tray is not active

**Cause**: Logic error in isActive calculation

**Solution**: Check browser console for JavaScript errors in the button-card template.

## Related Features

- [AMS Tray Popup](./ams-tray-popup.md) - Detailed popup when clicking a spool card
- [Print Weight Bar Chart](./print-weight-bar-chart.md) - Visual weight breakdown by filament

## Files Modified

- `dashboards/lovelace.3d_printing` - Main dashboard configuration containing all 8 AMS tray button-cards

## Future Enhancements

Potential improvements:

1. **Animation** - Add a subtle pulse or fade effect when tray becomes active
2. **Additional Visual Indicators** - Include an icon or badge showing "ACTIVE" text
3. **Configurable Colors** - Allow user to choose border color scheme in UI
4. **External Spool Support** - Extend feature to external spool card
5. **Multi-Color Border** - For multi-material prints, show gradient border with all active colors

## Support

For issues or questions about this feature:
- Check the [main README](../../README.md)
- Review the [AMS card documentation](https://github.com/AdrianGarside/ha-bambulab) for ha_bambulab integration
- Reference the [button-card documentation](https://github.com/custom-cards/button-card) for styling options
