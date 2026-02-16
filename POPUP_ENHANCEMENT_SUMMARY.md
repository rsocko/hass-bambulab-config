# Popup Enhancement Summary

## What Was Requested

1. ✅ Same popup functionality on the external spool
2. ✅ Dynamic weight history based on date opened field (days, months, or longer)
3. ✅ Include additional details like vendor and type (material)

## What Was Implemented

### 1. External Spool Popup ✅
- Added complete custom popup to the external spool card
- Uses same `browser_mod.popup` pattern as AMS trays
- All features available for external spool:
  - Material & vendor display
  - Dynamic history based on spool age
  - Color swatch with smart text contrast
  - Desiccant status and reset
  - Link to Spoolman web UI
  - Fallback for unmatched spools

### 2. Dynamic Weight History ✅
Implemented intelligent history duration that adapts to how long a spool has been in use:

**Logic:**
- Checks `first_used` attribute on the spoolman entity
- Calculates days since spool was opened
- Sets `hours_to_show` to show FULL history from opening to present
- Minimum: 24 hours (1 day)
- Maximum: Unlimited (shows entire history)
- Falls back to 7 days (168 hours) if no `first_used` date available

**Visual Feedback:**
- Title dynamically updates: "Weight History (X days)"
- Users can see exactly how long the spool has been tracked

**Examples:**
- Spool opened 3 days ago → Shows 3 days of history
- Spool opened 2 weeks ago → Shows 14 days of history
- Spool opened 2 months ago → Shows ~60 days of history
- Spool opened 6 months ago → Shows ~180 days of history
- No date available → Shows default 7 days

### 3. Additional Details - Vendor & Material ✅
Added new horizontal-stack section showing:

**Material Type:**
- Icon: 🧱 mdi:texture-box (orange color)
- Attribute: `filament_material`
- Examples: PLA, PETG, TPU, ABS, etc.
- Displays "Unknown" if not available

**Vendor/Manufacturer:**
- Icon: 🏭 mdi:factory (purple color)
- Attribute: `filament_vendor_name`
- Examples: Bambu Lab, eSun, Polymaker, etc.
- Displays "Unknown" if not available

**Layout:**
Both displayed side-by-side for compact presentation, positioned between the header and color sections.

## Coverage

### All 9 Spools Enhanced:
1. ✅ AMS 1 - Tray 1
2. ✅ AMS 1 - Tray 2
3. ✅ AMS 1 - Tray 3
4. ✅ AMS 1 - Tray 4
5. ✅ AMS 2 - Tray 1
6. ✅ AMS 2 - Tray 2
7. ✅ AMS 2 - Tray 3
8. ✅ AMS 2 - Tray 4
9. ✅ External Spool

## Technical Implementation

### Code Structure
Each popup now includes these sections (in order):
1. **Header** - Spool name, ID, color-tinted background
2. **Material & Vendor** ⭐ NEW - Side-by-side cards with icons
3. **Color & Weight** - Color swatch + remaining weight
4. **Desiccant** - Status indicator + reset button
5. **Spoolman Link** - Button to open web UI
6. **Dynamic History** ⭐ ENHANCED - Adaptive duration chart
7. **Fallback** - Entity details when no match
8. **More Details** - Link to full entity info

### JavaScript Highlights

**Dynamic History Calculation:**
```javascript
const spoolEntity = states['sensor.spoolman_spool_' + spoolId];
const firstUsed = spoolEntity?.attributes?.first_used;
let historyHours = 168; // Default 7 days

if (firstUsed) {
  const firstUsedDate = new Date(firstUsed);
  const now = new Date();
  const daysSinceOpened = Math.floor((now - firstUsedDate) / (1000 * 60 * 60 * 24));
  historyHours = daysSinceOpened * 24 || 24; // Full history, min 1 day
}
```

**Material & Vendor Display:**
```javascript
{
  type: 'horizontal-stack',
  cards: [
    {
      primary: states['sensor.spoolman_spool_' + spoolId]?.attributes?.filament_material || 'Unknown',
      secondary: 'Material',
      icon: 'mdi:texture-box',
      icon_color: 'orange'
    },
    {
      primary: states['sensor.spoolman_spool_' + spoolId]?.attributes?.filament_vendor_name || 'Unknown',
      secondary: 'Vendor',
      icon: 'mdi:factory',
      icon_color: 'purple'
    }
  ]
}
```

## Benefits

### For Users:
1. **Better Visibility** - See material type and vendor at a glance
2. **Historical Context** - Full usage history since spool was opened
3. **Consistency** - External spool has same rich popup as AMS trays
4. **Data-Driven** - History adapts to actual spool lifecycle

### For Troubleshooting:
1. Know exactly when a spool was first used
2. See complete weight reduction trend
3. Identify vendor-specific patterns
4. Track material performance over time

## Files Modified

1. **dashboards/lovelace.3d_printing**
   - Updated all 9 tap_action configurations
   - Added Material/Vendor sections
   - Implemented dynamic history logic
   - Valid JSON syntax ✅

2. **dashboards/docs/ams-tray-popup.md**
   - Updated title to include External Spool
   - Documented Material & Vendor feature
   - Documented Dynamic History feature
   - Added code examples
   - Updated popup coverage list

## Testing Checklist

### Functional Testing:
- [ ] Click AMS tray 1-4 to verify popup opens
- [ ] Click AMS tray 2-1 through 2-4 to verify popups
- [ ] Click External Spool to verify popup
- [ ] Verify Material displays correctly
- [ ] Verify Vendor displays correctly
- [ ] Check history title shows "(X days)"
- [ ] Verify history chart shows appropriate duration
- [ ] Test with spools of different ages
- [ ] Test with spools without first_used date
- [ ] Verify desiccant reset still works
- [ ] Verify Spoolman link opens correctly

### Visual Testing:
- [ ] Icons display correctly (texture-box, factory)
- [ ] Colors are appropriate (orange, purple)
- [ ] Layout is clean and readable
- [ ] Text contrast works on various themes
- [ ] Popup is responsive on mobile

## Notes

- All popups use existing Spoolman entity attributes (no new integrations needed)
- Dynamic history automatically scales to spool lifecycle
- Falls back gracefully when data not available
- Compatible with existing spoolman_tray_map template sensor
- No breaking changes to existing functionality

## Future Enhancements

While not implemented in this iteration, future enhancements could include:
- Location dropdown for changing spool storage
- List of other spools with same material/color
- Print usage estimates for current job
- Age-based quality warnings
- Custom notes/ratings per spool
