# Printer Temperature Cards v3 - Change Summary

## What Changed in v3

This update addresses user feedback to use a more accurate nozzle icon and add visual distinction for when the heating element is actively commanded to be on.

## Visual Changes

### 1. Nozzle Icon - More Accurate

**Before (v2):**
```
┌──────────────────────┐
│ 🌡️  220°C           │  ← Generic thermometer icon
│                      │
│      25°C            │
└──────────────────────┘
```

**After (v3):**
```
┌──────────────────────┐
│ 🔥  220°C           │  ← 3D printer nozzle heater icon
│                      │
│      25°C            │
└──────────────────────┘
```

**Icon Change:**
- From: `mdi:thermometer` (generic temperature icon)
- To: `mdi:printer-3d-nozzle-heat` (specific 3D printer nozzle heater icon)
- Why: More semantically correct and visually representative

### 2. Bold Target Temp When Heating Is On

This is the key new feature for v3!

**Heating Element OFF (target = 0°C):**
```
┌──────────────────────┐
│ 🔥  0°C             │  ← Normal weight, subtle (opacity 0.7)
│                      │
│      23°C            │  ← Ambient temperature
└──────────────────────┘
```

**Heating Element ON (target > 0°C):**
```
┌──────────────────────┐
│ 🔥 **220°C**        │  ← BOLD weight, prominent (opacity 0.9)
│                      │
│      25°C            │
└──────────────────────┘
```

**Styling Details:**
- **Target = 0°C**: font-weight: 500, opacity: 0.7 (normal, subtle)
- **Target > 0°C**: font-weight: 700, opacity: 0.9 (bold, prominent)

## Why These Changes Matter

### Problem 1: Generic Icon
The thermometer icon was generic and didn't clearly represent a 3D printer nozzle heater. The new icon is more specific and immediately recognizable.

### Problem 2: Hard to Tell If Heating Is On
**Scenario**: You look at your dashboard and see:
- Target: 0°C (grey, cooling indicator)
- Current: 23°C

**Question**: Is the heater on or off?
- In v2: Not immediately obvious - you have to think about it
- In v3: **Instantly clear** - target temp is subtle/normal weight, so heater is OFF

**Scenario 2**: You look at your dashboard and see:
- Target: 220°C (grey, at target indicator)
- Current: 220°C

**Question**: Is the heater actively maintaining this temperature?
- In v2: Target looks the same as when it's 0°C
- In v3: **Target is BOLD** - heater is commanding heat to maintain temp

## Key Distinction from Color Coding

The card already had color coding (red/blue/grey) that shows:
- **Red**: Currently heating up (target > current)
- **Blue**: Currently cooling down (target < current)
- **Grey**: At target or idle

The NEW bold styling is different - it shows:
- **Bold**: Heating element is COMMANDED to be on (target > 0)
- **Normal**: Heating element is commanded to be off (target = 0)

### Example: Why Both Are Useful

**Scenario: Print finishing, nozzle at 220°C, target set to 220°C**
- Color: **Grey** (at target temp, no active heating/cooling)
- Bold: **Yes** (heater is still commanding 220°C to maintain it)
- Interpretation: Heater is on and maintaining temperature

**Scenario: Print complete, nozzle cooling from 220°C to ambient**
- Target: 0°C, Current: 180°C (still hot but cooling)
- Color: **Grey** (idle state, no active temp management)
- Bold: **No** (target is 0, so subtle styling)
- Interpretation: Heater is off, passively cooling

## Summary of All States (v3)

| Target | Current | Printing? | Color | Bold? | Interpretation |
|--------|---------|-----------|-------|-------|----------------|
| 220°C | 25°C | Yes | Red | Yes | Heating up to target |
| 220°C | 220°C | Yes | Grey | Yes | At target, maintaining |
| 220°C | 220°C | No | Grey | Yes | Idle but heater still on |
| 0°C | 218°C | No | Grey | No | Cooling down, heater off |
| 0°C | 23°C | No | Grey | No | Cold, heater off |

## Technical Implementation

```yaml
.primary {
  font-size: 14px !important;
  {% set target = states('number.YOUR_PRINTER_NAME_nozzle_target_temperature') | float(0) %}
  {% if target > 0 %}
    font-weight: 700;
    opacity: 0.9;
  {% else %}
    font-weight: 500;
    opacity: 0.7;
  {% endif %}
}
```

This is simple, efficient, and provides instant visual feedback.

## Files Updated

1. [homeassistant/packages/3d_printing/printer_temps/dashboard_cards/printer-temps.yaml](../../../../homeassistant/packages/3d_printing/printer_temps/dashboard_cards/printer-temps.yaml) - Canonical include-based card file
2. `printer-temps-implementation.md` - Implementation notes
3. [printer-temps-cards.md](../reference/printer-temps-cards.md) - Feature documentation
4. [printer-temps-visual-reference.md](../design/printer-temps-visual-reference.md) - Visual examples

## Migration

No migration needed! Just update your YAML files with the new versions. The changes are backward compatible and enhance the existing functionality.

## User Feedback Addressed

From the problem statement:

✅ **"Use printer-3d-nozzle-heat icon for the nozzle heater. Not thermometer."**
- Fixed: Now uses `mdi:printer-3d-nozzle-heat`

✅ **"Do you think there is a smart way to distinguish the format (color or bold or something) when the device is at a target temp that is non-zero (meaning the heating is in fact on) vs. when printer is idle"**
- Fixed: Bold target temp when target > 0, normal when target = 0
- Provides instant visual distinction independent of current temp or print state

## Version History

- **v1**: Initial implementation with arrow icons
- **v2**: Fixed icons per component, idle state detection
- **v3**: Accurate nozzle icon, bold styling for heating-on state

Each version builds on the previous, making the cards progressively smarter and more intuitive!




