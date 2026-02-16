# Active Spool Border Feature

## Overview

This feature adds a visual indicator to the AMS tray spool cards and external spool card displayed below the AMS card in the 3D printing dashboard. When a tray is actively being used by the printer, its corresponding spool card will display a cyan border matching the style used by the Bambu Lab AMS card itself.

## Implementation

### How it Works

1. **Active Tray Detection**: The feature uses the `sensor.ntk_ryansoffice_3dprinter_active_tray` sensor which provides a state value indicating which tray is currently active:
   - States `'1'` through `'8'`: AMS trays (1-4 for AMS 1, 5-8 for AMS 2)
   - State `'254'`: External spool  
   - State `'255'`: No active tray

2. **Tray Number Matching**: The code compares the active_tray sensor state directly with the tray number to determine if a specific tray is active. This approach works for both Bambu and non-Bambu spools since it doesn't require UUID matching.

3. **Consistent Border Styling**: When a tray is active, the button-card applies:
   - A 3px solid border in **cyan** (#2196F3) - the same color used by the Bambu AMS card
   - An 8px border-radius for a rounded appearance
   - Works consistently on both light and dark backgrounds

### Code Structure

The implementation uses JavaScript template syntax in the `styles` field of each button-card:

```javascript
"styles": "[[[\n  const tray = 'ams_1_tray_1';\n  const activeTrayState = states['sensor.ntk_ryansoffice_3dprinter_active_tray']?.state;\n  const isActive = activeTrayState === '1';\n  \n  // Use cyan border color (matching Bambu AMS card)\n  const borderColor = '#2196F3';\n  \n  return {\n    card: [\n      { 'padding': '6px' },\n      { 'background': 'none' },\n      { 'box-shadow': 'none' },\n      ...(isActive ? [{ 'border': \`3px solid \${borderColor}\` }, { 'border-radius': '8px' }] : [])\n    ],\n    // ... rest of styles\n  };\n]]]\n"
```

### Tray Number Mapping

| Tray Name | Active State Value | Description |
|-----------|-------------------|-------------|
| ams_1_tray_1 | `'1'` | AMS 1, Slot 1 |
| ams_1_tray_2 | `'2'` | AMS 1, Slot 2 |
| ams_1_tray_3 | `'3'` | AMS 1, Slot 3 |
| ams_1_tray_4 | `'4'` | AMS 1, Slot 4 |
| ams_2_tray_1 | `'5'` | AMS 2, Slot 1 |
| ams_2_tray_2 | `'6'` | AMS 2, Slot 2 |
| ams_2_tray_3 | `'7'` | AMS 2, Slot 3 |
| ams_2_tray_4 | `'8'` | AMS 2, Slot 4 |
| external_spool | `'254'` | External spool holder |

### Coverage

The feature is implemented for all 9 filament sources:
- ✅ AMS 1 - Tray 1 (ams_1_tray_1)
- ✅ AMS 1 - Tray 2 (ams_1_tray_2)
- ✅ AMS 1 - Tray 3 (ams_1_tray_3)
- ✅ AMS 1 - Tray 4 (ams_1_tray_4)
- ✅ AMS 2 - Tray 1 (ams_2_tray_1)
- ✅ AMS 2 - Tray 2 (ams_2_tray_2)
- ✅ AMS 2 - Tray 3 (ams_2_tray_3)
- ✅ AMS 2 - Tray 4 (ams_2_tray_4)
- ✅ External Spool (external_spool)

## Visual Behavior

### When Active
- The spool card displays a **3px solid border**
- Border color is **#2196F3** (Material Blue/cyan)
- Border has an **8px radius** for smooth corners
- Color provides excellent contrast on both light and dark Home Assistant themes
- All existing card styling (padding, background, etc.) is preserved

### When Inactive
- No border is shown (box-shadow: none)
- Card appears with default transparent background
- Same visual appearance as before the feature was added

### Advantages Over Previous Implementation

The new implementation has several improvements over the UUID-based approach:

1. **Works with all spools**: Non-Bambu spools don't have UUIDs but will still show the active border
2. **Simpler logic**: Direct state comparison is faster and more reliable than UUID matching
3. **Consistent color**: Cyan border is easily visible regardless of filament color
4. **Better UX**: Matches the visual style of the official Bambu AMS card
5. **Dark/light theme support**: #2196F3 provides good contrast in all themes

## Dependencies

### Sensors Required
1. **sensor.ntk_ryansoffice_3dprinter_active_tray**
   - Provides: State value (`'1'`-`'8'` for AMS, `'254'` for external, `'255'` for none)
   - Updated by printer when active tray changes

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

To use a different highlight color:

```javascript
// Replace:
const borderColor = '#2196F3';

// With (example: green):
const borderColor = '#4CAF50';

// Or (example: orange):
const borderColor = '#FF9800';
```

Some alternative colors that work well on both light and dark backgrounds:
- `#2196F3` - Material Blue (current/default)
- `#00BCD4` - Cyan
- `#03A9F4` - Light Blue
- `#4CAF50` - Green
- `#FF9800` - Orange
- `#F44336` - Red

### Adding a Glow Effect

To add a subtle glow/shadow to the border:

```javascript
...(isActive ? [
  { 'border': `3px solid ${borderColor}` }, 
  { 'border-radius': '8px' },
  { 'box-shadow': `0 0 10px ${borderColor}60` }  // Add 60 for 38% opacity
] : [])
```

## Troubleshooting

### Border Not Showing

**Problem**: Active tray doesn't show a border

**Possible Causes & Solutions**:

1. **Active tray sensor unavailable**
   - Check if `sensor.ntk_ryansoffice_3dprinter_active_tray` exists
   - Verify the sensor has a valid state value ('1'-'8' or '254')

2. **Sensor in wrong state**
   - Check if sensor state is '255' (no active tray)
   - Verify a print is actually running

3. **JavaScript template error**
   - Open browser console (F12) and check for errors
   - Verify button-card is properly installed

### Wrong Tray Highlighted

**Problem**: Border appears on the wrong tray

**Cause**: Incorrect tray number mapping

**Solution**: Verify the tray number in the JavaScript template matches the expected value:
- AMS 1 trays should use '1'-'4'
- AMS 2 trays should use '5'-'8'
- External spool should use '254'

### Border Always Shows

**Problem**: Border appears even when tray is not active

**Cause**: Logic error or incorrect state value

**Solution**: 
- Check the active_tray sensor state in Home Assistant developer tools
- Verify the comparison is using strict equality (`===`)
- Ensure quotes around the number (`'1'` not `1`)

### External Spool Not Highlighting

**Problem**: External spool doesn't show border when active

**Cause**: Incorrect state value comparison

**Solution**: Verify the external spool uses state value '254' (not '255' which means no active tray)

## Related Features

- [AMS Tray Popup](./ams-tray-popup.md) - Detailed popup when clicking a spool card
- [Print Weight Bar Chart](./print-weight-bar-chart.md) - Visual weight breakdown by filament

## Files Modified

- `dashboards/lovelace.3d_printing` - Main dashboard configuration containing all 9 spool button-cards
- `dashboards/docs/active-spool-border.md` - This documentation file

## Technical Notes

### Why Tray Number Instead of UUID?

The previous implementation used UUID matching which had limitations:
- **Non-Bambu spools**: Third-party filaments may not have UUIDs in the system
- **Complexity**: Required matching UUIDs between two different sensors
- **Reliability**: UUID matching could fail if attributes weren't available

The tray number approach:
- **Universal**: Works with any spool (Bambu or third-party)
- **Simple**: Direct state comparison
- **Reliable**: The active_tray sensor always provides a valid state
- **Efficient**: No need to access multiple sensor attributes

### Why Cyan Color Instead of Filament Color?

Using the filament color for the border had issues:
- **Low contrast**: Dark filaments (black, gray) were hard to see
- **Similar colors**: Multiple similar-colored spools were difficult to distinguish
- **Theme issues**: Some colors didn't work well on both light and dark themes

The cyan border (#2196F3):
- **High visibility**: Stands out on any background
- **Consistent**: Same visual treatment as the official Bambu AMS card
- **Theme-agnostic**: Works equally well in light and dark modes
- **Distinctive**: Clearly different from the gray default border

## Support

For issues or questions about this feature:
- Check the [main README](../../README.md)
- Review the [ha-bambulab integration](https://github.com/greghesp/ha-bambulab) documentation
- Reference the [button-card documentation](https://github.com/custom-cards/button-card) for styling options
