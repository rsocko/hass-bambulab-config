# Bento Box Fan Enhancement - Implementation Summary

## Problem Statement

> "Make sure the bento fan is run regardless of the chamber fan. Base it off of the air quality and potentially the filament type being used like ABS or ASA or other toxic filaments"

## Solution Overview

Created a **dedicated, intelligent automation** for Bento Box fan control that:

1. ✅ **Runs independently** - Not tied to chamber fan or Govee purifier
2. ✅ **Filament-aware** - Detects high-VOC materials (ABS, ASA, PC, Nylon, HIPS)
3. ✅ **Air quality responsive** - Adjusts based on PM2.5 and VOC readings
4. ✅ **Safety-focused** - Alerts users when printing toxic materials

## What Changed

### Before
```
Print Start:
  → Govee Purifier: ON (based on air quality)
  → Bento Box Fan: 66% (hard-coded)
  → Both controlled by same automation

Print Complete:
  → Both run for 30 minutes
  → Both turn off together
  → No filament type awareness
```

### After
```
Print Start:
  → Govee Purifier: ON (based on air quality) [separate automation]
  → Bento Box Fan: 30-80% (based on filament + air quality) [dedicated automation]
  
Print Complete:
  → Purifier: 30 minutes (air quality based)
  → Bento Box: 45 minutes (filament + air quality based)
  → Independent operation
  → Filament-aware speeds
```

## Implementation Details

### New File: `bento_box_fan_auto_control.yaml`

**Size**: 6.2KB (175 lines)

**Triggers:**
- Print starts (event_print_started)
- Every 5 minutes during printing (time_pattern)
- Print completes (event_print_finished)

**Conditions:**
- Only runs during printing OR within 45 minutes after print

**Key Logic:**

```yaml
1. Get filament type from active_tray sensor
2. Get air quality readings (PM2.5, VOC, CO2)
3. Classify filament as high-VOC or low-VOC
4. Calculate target speed based on:
   - Very poor air quality → 100%
   - Poor air quality OR high-VOC printing → 80%
   - Moderate air quality OR high-VOC post-print → 60%
   - Printing low-VOC with slight elevation → 40%
   - Good air quality, not printing → OFF
   - Default → 30%
5. Control fan (turn on/off/adjust)
6. Log action
7. Send notification if high-VOC material detected
```

**High-VOC Materials Detected:**
- ABS (Acrylonitrile Butadiene Styrene)
- ASA (Acrylonitrile Styrene Acrylate)
- PC (Polycarbonate)
- Nylon (Polyamide)
- HIPS (High Impact Polystyrene)

### Modified Files

**1. `print_started_auto_purifier.yaml`**
- Removed: Hard-coded Bento Box fan control (lines 47-53)
- Added: Comment noting dedicated automation now controls Bento Box fan
- Updated: Notification and log messages

**2. `print_complete_continue_purifier.yaml`**
- Removed: Bento Box fan on/off control (multiple locations)
- Added: Comments noting dedicated automation
- Updated: Log messages to indicate separation

**3. `README.md`**
- Added: Bento Box fan feature description in overview
- Added: New automation documentation
- Updated: Automation list with filament-aware control note

### New Documentation

**1. [bento-box-fan-filament-control.md](../reference/bento-box-fan-filament-control.md)** (11KB)
- Complete guide with theory and examples
- Speed logic explanation
- Configuration instructions
- Customization options
- Troubleshooting guide
- Safety notes

**2. [bento-box-fan-quick-config.md](../reference/bento-box-fan-quick-config.md)** (7KB)
- Quick 5-minute setup guide
- Step-by-step instructions
- Example scenarios
- Common customizations
- Testing procedures

## Key Features

### 1. Filament Type Detection

Uses Bambu Lab integration's active tray sensor:
```yaml
filament_type: {{ state_attr('sensor.ntk_ryansoffice_3dprinter_active_tray', 'type') | upper }}
```

Returns values like: PLA, ABS, ASA, PETG, PC, NYLON, etc.

### 2. Intelligent Speed Control

Multi-factor decision making:
1. **Air quality severity** (PM2.5, VOC thresholds)
2. **Filament toxicity** (high-VOC vs low-VOC)
3. **Print status** (active vs recent vs inactive)

### 3. Extended Post-Print Duration

- **Purifier**: 30 minutes post-print
- **Bento Box**: 45 minutes post-print (especially for high-VOC)

Rationale: Enclosure needs more time to vent fumes than room needs to filter

### 4. Safety Notifications

When printing with high-VOC materials:
```
⚠️ High-VOC Filament Detected

Print started with ABS filament.

Bento Box fan set to 80% for enhanced ventilation.

Current Air Quality:
PM2.5: 8.0 µg/m³
VOC: 45 ppb
CO2: 650 ppm
```

### 5. Independent Operation

| Feature | Bento Box Fan | Govee Purifier | Chamber Fan |
|---------|--------------|----------------|-------------|
| **Control** | Air quality + filament | Air quality only | Printer firmware |
| **Purpose** | Fume extraction | Air filtration | Part cooling |
| **Duration** | 45 min post-print | 30 min post-print | Per G-code |
| **Awareness** | Filament-aware | Generic | Print-specific |
| **Speed Range** | 0-100% dynamic | 33-100% | 0-100% |

## Examples

### Scenario 1: PLA Print (Low-VOC)

```
T+0s  Print starts with PLA
      → Bento Box: 30% (low circulation)
      
T+5m  PM2.5: 11 µg/m³, VOC: 85 ppb
      → Bento Box: 40% (slight elevation)
      
T+2h  Print completes
      → Bento Box: 40% (continues)
      
T+2h45m Air quality good
        → Bento Box: OFF
```

### Scenario 2: ABS Print (High-VOC)

```
T+0s  Print starts with ABS
      → Bento Box: 80% (high-VOC detected)
      → Notification sent
      
T+15m PM2.5: 42 µg/m³, VOC: 285 ppb
      → Bento Box: 100% (poor air quality)
      
T+3h  Print completes
      → Bento Box: 80% (continues high ventilation)
      
T+3h45m Still elevated (PM2.5: 15, VOC: 110)
        → Bento Box: 60% (continues)
        
T+5h  Air quality recovered
      → Bento Box: OFF
```

## Benefits

### Health & Safety
- ✅ Reduced exposure to toxic fumes
- ✅ Automatic detection of hazardous materials
- ✅ Enhanced ventilation when needed most
- ✅ Proactive user notifications

### Air Quality
- ✅ Faster recovery after printing
- ✅ Lower cumulative exposure
- ✅ Extended filtering for problematic materials
- ✅ Real-time responsiveness

### Convenience
- ✅ Zero manual intervention required
- ✅ Set once, works forever
- ✅ Adapts to any filament automatically
- ✅ Independent of other systems

### Flexibility
- ✅ Easy to customize
- ✅ Add new filament types
- ✅ Adjust thresholds
- ✅ Configure durations

## Configuration Required

Users need to update 4 entity references:

1. **Printer Device ID** (2 places)
   - Get from Settings > Devices > Bambu Lab
   
2. **Bento Box Fan Entity** (2 places)
   - Usually: `fan.bento_box_fan`
   
3. **Printer Sensors** (3 places)
   - `sensor.XXX_active_tray`
   - `sensor.XXX_print_status`
   - `sensor.XXX_end_time`
   
4. **Air Quality Sensors** (3 places)
   - `sensor.XXX_pm25`
   - `sensor.XXX_tvoc`
   - `sensor.XXX_co2`

## Testing Performed

- ✅ YAML syntax validation (all files pass)
- ✅ Template logic verification
- ✅ Entity reference patterns checked
- ✅ Documentation completeness reviewed

## Compatibility

- **Home Assistant**: 2023.3+ (for template features)
- **Bambu Lab Integration**: Latest version with active_tray sensor
- **Air Quality Sensors**: Any compatible sensor
- **Bento Box Fan**: Any fan entity controllable by HA

## Migration Path

### For New Users
1. Import the new automation
2. Configure entity IDs
3. Done!

### For Existing Users
1. Import the new automation
2. Update entity IDs
3. Optional: Update existing automations to remove duplicate controls
4. Both versions will work (new overrides old)

## Future Enhancements

Potential additions:
- Temperature-based speed adjustment
- Seasonal/outdoor air quality consideration
- Multi-printer coordination
- Historical trend analysis
- Voice announcements
- WLED visual indicators

## Statistics

- **Files Added**: 3 (automation + 2 docs)
- **Files Modified**: 3 (2 automations + README)
- **Total Lines Added**: ~600
- **Documentation**: 18KB
- **Code**: 6.2KB
- **Setup Time**: 5 minutes

## Conclusion

This implementation delivers exactly what was requested:

✅ **"Make sure the bento fan is run regardless of the chamber fan"**
   - Dedicated automation, completely independent
   
✅ **"Base it off of the air quality"**
   - Real-time PM2.5 and VOC monitoring
   - Dynamic speed adjustment
   
✅ **"and potentially the filament type being used like ABS or ASA or other toxic filaments"**
   - Detects ABS, ASA, PC, Nylon, HIPS
   - Automatically increases ventilation
   - Alerts users to high-VOC materials

The solution is production-ready, well-documented, and provides significant safety and convenience improvements for 3D printing operations.

**Ready to merge and use! 🖨️💨✨**


