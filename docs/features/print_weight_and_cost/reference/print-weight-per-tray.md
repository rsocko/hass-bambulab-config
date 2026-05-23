# Print Weight Display Per Tray

## Overview

Each AMS tray and external spool now displays the amount of filament that will be consumed during the current print job directly below the remaining weight indicator.

## Features

### Display Format
- Shows as: `(−XX.Xg)` 
- Negative value with parentheses to indicate consumption
- Positioned below the remaining weight on each tray card
- Small font (10px) to maintain clean layout

### Color-Coded Warnings

The print weight value is color-coded to alert users when filament may run out:

| Color | Threshold | Meaning |
|-------|-----------|---------|
| **Red** (#cc0000) | Remaining < Print Weight | **Will run out** - Not enough filament to complete print |
| **Orange** (#ff9900) | Remaining < Print Weight × 1.1 | **Close** - Less than 10% buffer remaining |
| **Yellow** (#ffcc00) | Remaining < Print Weight × 1.2 | **Approaching** - Less than 20% buffer remaining |
| Gray (#888) | Remaining ≥ Print Weight × 1.2 | **Sufficient** - Adequate filament available |

Warning colors also use bold font weight (600) for increased visibility.

### Data Source

Print weight data is retrieved from the Bambu Lab printer integration:
- **Sensor**: `sensor.ntk_ryansoffice_3dprinter_print_weight`
- **Attributes**: 
  - `AMS 1 Tray 1` through `AMS 1 Tray 4`
  - `AMS 2 Tray 1` through `AMS 2 Tray 4`
  - `External` for external spool

### Display Logic

The print weight is only shown when:
1. The tray has a spool mapped in Spoolman
2. The print weight value exists and is greater than 0
3. A print job is active that uses that specific tray

## Implementation

### Grid Layout Structure

Each tray card uses a 4-row grid:
```
Row 1: Name (spans all 3 columns)
Row 2: Label/reason (spans all 3 columns)
Row 3: Desiccant icon | (spacer) | Remaining weight
Row 4: (empty) | (empty) | Print weight
```

Grid template: `"n n n" "l l l" "desiccant_icon . remaining_weight" ". . print_weight"`

### Custom Fields

Three custom fields are used for each tray:
1. **desiccant_icon** - Shows desiccant status indicator
2. **remaining_weight** - Current weight left on spool (from Spoolman)
3. **print_weight** - Weight to be consumed (from print job, NEW)

### JavaScript Logic

```javascript
// Get mapped spool ID
const map = states['sensor.spoolman_tray_map']?.attributes?.tray_map;
const spoolId = map?.[tray]?.spool_id;

// Get print weight from sensor
const printWeightEntity = states['sensor.ntk_ryansoffice_3dprinter_print_weight'];
const printWeight = printWeightEntity?.attributes?.['AMS X Tray Y'];

// Get remaining weight for comparison
const spoolentity = states[`sensor.spoolman_spool_${spoolId}`];
const remainingWeight = spoolentity?.attributes?.remaining_weight;

// Calculate warning color
if (remainingWeight < printWeight) {
  color = '#cc0000'; // red
} else if (remainingWeight < printWeight * 1.1) {
  color = '#ff9900'; // orange  
} else if (remainingWeight < printWeight * 1.2) {
  color = '#ffcc00'; // yellow
}
```

## Example Scenarios

### Scenario 1: Sufficient Filament
- **Remaining**: 150g
- **Print Weight**: 45g
- **Display**: `(−45.0g)` in gray
- **Status**: ✅ Safe to print

### Scenario 2: Low Buffer (Yellow)
- **Remaining**: 50g
- **Print Weight**: 45g  
- **Display**: `(−45.0g)` in yellow (bold)
- **Status**: ⚠️ Approaching limit (11% buffer)

### Scenario 3: Very Low (Orange)
- **Remaining**: 48g
- **Print Weight**: 45g
- **Display**: `(−45.0g)` in orange (bold)
- **Status**: ⚠️ Close to limit (6.7% buffer)

### Scenario 4: Will Run Out (Red)
- **Remaining**: 40g
- **Print Weight**: 45g
- **Display**: `(−45.0g)` in red (bold)
- **Status**: ❌ Insufficient filament

## User Benefit

This feature provides at-a-glance visibility into:
1. **Which trays** are being used in the current print
2. **How much filament** will be consumed from each tray
3. **Whether there's enough** filament to complete the print
4. **How close** each tray is to running out

Users can proactively:
- Replace spools before starting a print
- Swap to fuller spools if available
- Prepare backup spools for multi-color prints
- Avoid failed prints due to filament runout
