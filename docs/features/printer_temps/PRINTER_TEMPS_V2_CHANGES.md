# Printer Temperature Cards v2 - Change Summary

## What Changed

This update addresses user feedback to improve the printer temperature cards with fixed icons and intelligent idle state detection.

## Visual Changes

### Before (v1)

**Heating State:**
```
┌──────────────────────┐
│ ⬆️  220°C           │  ← Red arrow up
│                      │
│      25°C            │  ← Current temp (RED)
└──────────────────────┘
```

**Cooling State:**
```
┌──────────────────────┐
│ ⬇️  0°C             │  ← Blue arrow down
│                      │
│      25°C            │  ← Current temp (BLUE) - misleading when idle!
└──────────────────────┘
```

**At Target:**
```
┌──────────────────────┐
│ 🌡️  220°C           │  ← Thermometer (nozzle only)
│                      │
│     220°C            │  ← Current temp (GREY)
└──────────────────────┘
```

### After (v2)

**Heating State (when actively printing):**
```
┌──────────────────────┐
│ 🌡️  220°C           │  ← Red thermometer (always thermometer for nozzle)
│                      │
│      25°C            │  ← Current temp (RED)
└──────────────────────┘
```

**Idle State (printer not printing):**
```
┌──────────────────────┐
│ 🌡️  0°C             │  ← Grey thermometer (no misleading blue!)
│                      │
│      23°C            │  ← Current temp (GREY) - shows ambient
└──────────────────────┘
```

**At Target (when actively printing):**
```
┌──────────────────────┐
│ 🌡️  220°C           │  ← Grey thermometer
│                      │
│     220°C            │  ← Current temp (GREY)
└──────────────────────┘
```

## Key Improvements

### 1. Fixed Icons - No More Arrows

**Before:** Icons changed dynamically between arrows (⬆️⬇️) and base icon (🌡️/🔥)
**After:** Always show the same icon per component:
- Nozzle: `mdi:thermometer` 🌡️
- Bed: `mdi:radiator` 🔥

**Why?** 
- Cleaner, less busy interface
- Color coding is sufficient to indicate state
- More consistent with user's preferences

### 2. Intelligent Idle State Detection

**Before:** Color indicators always active based on temp difference
- Problem: When printer idle with target=0°C and current=23°C (ambient), showed misleading blue "cooling" indicator

**After:** Color indicators only active when printer is printing or preparing
- Checks `sensor.[printer]_print_status` for 'printing' or 'prepare' state
- When idle: Always grey, regardless of temperature difference
- When active: Red (heating), Blue (cooling), or Grey (at target)

**Why?**
- More accurate representation of printer state
- No false heating/cooling indicators when printer is at rest
- Users can quickly see if printer is actively managing temperature

### 3. Compact Layout (Unchanged)

- Horizontal layout maintained
- Works well next to other compact cards (e.g., fan controls)
- Mobile responsive

## Technical Details

### New Logic Flow

```
IF printer_status in ['printing', 'prepare']:
    IF target > current + 2°C:
        → RED (heating)
    ELIF target < current - 2°C:
        → BLUE (cooling)
    ELSE:
        → GREY (at target)
ELSE:
    → GREY (idle)
```

### Required Sensors

The following sensors are now **required** for proper functionality:
- `sensor.[printer]_nozzle_temperature`
- `number.[printer]_nozzle_target_temperature`
- `sensor.[printer]_bed_temperature`
- `number.[printer]_bed_target_temperature`
- `sensor.[printer]_print_status` ⚠️ **Now required** (was optional)

### Compatibility

✅ Works with existing Bambu Lab integration
✅ No breaking changes to card structure
✅ Same dependencies (Mushroom Cards, card-mod)
✅ Backward compatible with v1 (just better logic)

## User Feedback Addressed

From the issue comments:

✅ "I want to always have the icons be the nozzle for the extruder temp and a radiator or something like it for the bed temp. I don't want arrows."
- **Fixed:** Icons are now fixed per component

✅ "Could we consider any additional logic that might eliminate the color coding when the printer is idle?"
- **Fixed:** Added printer status checking

✅ "even though my target might be 0 (eg no heat) it is reporting 23 degrees - which is just the ambient temp"
- **Fixed:** No color coding when idle, so no misleading indicators

✅ "make sure the layout is compact enough that if I put another card next to it (such as a fan control) it will shrink horizontally but still show the relevant info"
- **Already working:** Horizontal layout is compact and flexible

## Files Updated

1. [homeassistant/packages/3d_printing/printer_temps/dashboard_cards/printer-temps.yaml](../../homeassistant/packages/3d_printing/printer_temps/dashboard_cards/printer-temps.yaml) - Canonical include-based card file
2. `PRINTER_TEMPS_IMPLEMENTATION.md` - Implementation summary
3. [printer-temps-cards.md](printer-temps-cards.md) - Main documentation
4. [printer-temps-visual-reference.md](printer-temps-visual-reference.md) - Visual examples

## Migration Guide

No migration needed! The changes are enhancements to existing cards:

1. If using v1 cards, simply replace the YAML with v2 YAML
2. Ensure `sensor.[printer]_print_status` is available
3. That's it! Everything else works the same

## Summary

This update makes the temperature cards smarter and cleaner:
- **Smarter:** Only shows color indicators when they're meaningful (printer actively printing)
- **Cleaner:** Fixed icons instead of changing arrows
- **More Accurate:** No misleading indicators when printer is idle
- **User-Requested:** Directly addresses all feedback from the issue

Version 2 is a refinement that makes the cards more intuitive and accurate without any breaking changes.



