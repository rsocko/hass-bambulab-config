# Bento Box Fan - Filament-Aware Air Quality Control

## Overview

The Bento Box fan is now controlled by a dedicated automation (`bento_box_fan_auto_control.yaml`) that intelligently adjusts fan speed based on:

1. **Filament type** - High-VOC materials trigger higher ventilation
2. **Air quality readings** - PM2.5 and VOC levels primarily
3. **Print status** - Active printing vs. post-print filtering

This automation runs **independently** of the chamber fan and Govee air purifier, providing dedicated enclosure ventilation.

## High-VOC Filaments

The following filament types are classified as high-VOC and trigger enhanced ventilation:

### High-VOC Materials (Require More Ventilation)
- **ABS** (Acrylonitrile Butadiene Styrene) - Common engineering plastic with styrene emissions
- **ASA** (Acrylonitrile Styrene Acrylate) - Weather-resistant ABS alternative
- **PC** (Polycarbonate) - High-strength engineering plastic
- **Nylon** (Polyamide) - Engineering plastic with caprolactam emissions
- **HIPS** (High Impact Polystyrene) - Support material with styrene emissions

### Low-VOC Materials (Require Less Ventilation)
- **PLA** (Polylactic Acid) - Minimal VOC emissions
- **PETG** (Polyethylene Terephthalate Glycol) - Low VOC emissions
- **TPU** (Thermoplastic Polyurethane) - Flexible material with minimal emissions

## Fan Speed Logic

The automation uses a sophisticated algorithm that considers multiple factors:

### Speed Determination

```yaml
Very Poor Air Quality (PM2.5 ≥55 or VOC ≥300):
  → 100% (maximum ventilation regardless of filament)

Poor Air Quality OR High-VOC Printing (PM2.5 ≥35 or VOC ≥200 or printing ABS/ASA/etc):
  → 80% (high ventilation)

Moderate Air Quality OR High-VOC Post-Print (PM2.5 ≥12 or VOC ≥100 or high-VOC within 45min):
  → 60% (medium-high ventilation)

Printing Low-VOC with Slight Elevation (printing PLA/PETG with PM2.5 ≥8 or VOC ≥50):
  → 40% (medium ventilation)

Good Air Quality, Not Printing (PM2.5 <12 and VOC <100):
  → OFF (no ventilation needed)

Default:
  → 30% (low circulation)
```

### Key Features

1. **Filament-Aware**: Automatically detects high-VOC materials and increases ventilation
2. **Air Quality Response**: Adjusts speed based on real-time PM2.5 and VOC readings
3. **Extended Post-Print**: Continues ventilation for 45 minutes after print completion (longer than purifier)
4. **Independent Operation**: Not tied to chamber fan or purifier status
5. **Smart Notifications**: Alerts when printing with high-VOC filaments

## Comparison with Other Fans

### Bento Box Fan (Enclosure Ventilation)
- **Purpose**: Extract fumes from printer enclosure
- **Control**: Air quality + filament type
- **Duration**: 45 minutes post-print
- **Speed Range**: 0-100% based on need
- **Priority**: Ventilation and fume extraction

### Govee Air Purifier (Room Air Filtration)
- **Purpose**: Filter room air (particles and VOCs)
- **Control**: Air quality only
- **Duration**: 30 minutes post-print
- **Speed Range**: 33-100% based on air quality
- **Priority**: Air cleaning and filtration

### Chamber Fan (Printer Built-in)
- **Purpose**: Part cooling and temperature control
- **Control**: Printer firmware based on print settings
- **Duration**: Controlled by print file
- **Speed Range**: 0-100% per G-code
- **Priority**: Print quality

## Installation

### 1. Update Entity Names

Edit `bento_box_fan_auto_control.yaml`:

```yaml
# Replace these with your actual entity names:
device_id: YOUR_PRINTER_DEVICE_ID_HERE  # Your Bambu Lab printer device ID
entity_id: fan.bento_box_fan            # Your Bento Box fan entity
sensor.ntk_ryansoffice_3dprinter_*      # Your printer sensor prefix
sensor.airgradient_*                    # Your air quality sensor prefix
```

### 2. Import Automation

1. Go to Settings > Automations & Scenes
2. Click "+" to add automation
3. Click "⋮" menu > "Edit in YAML"
4. Copy contents from `bento_box_fan_auto_control.yaml`
5. Paste and save
6. Enable the automation

### 3. Update Existing Automations (Optional)

The print start and print complete automations have been updated to remove Bento Box fan control, as it's now handled by the dedicated automation. If you're using the old versions, update them to avoid conflicts.

## Configuration Examples

### Example 1: Printing PLA (Low-VOC)

**Scenario**: Printing PLA, good initial air quality

```
Print starts:
  Filament: PLA (low-VOC)
  PM2.5: 8.0 µg/m³
  VOC: 45 ppb
  → Bento Box Fan: 30% (low circulation)

During print (5 min later):
  PM2.5: 10.5 µg/m³
  VOC: 75 ppb
  → Bento Box Fan: 40% (slight elevation detected)

Print completes:
  PM2.5: 11.2 µg/m³
  VOC: 82 ppb
  → Bento Box Fan: 40% (continues for 45 min)

45 minutes later:
  PM2.5: 7.5 µg/m³
  VOC: 38 ppb
  → Bento Box Fan: OFF (air quality good)
```

### Example 2: Printing ABS (High-VOC)

**Scenario**: Printing ABS, good initial air quality

```
Print starts:
  Filament: ABS (high-VOC)
  PM2.5: 8.0 µg/m³
  VOC: 45 ppb
  → Bento Box Fan: 80% (high-VOC material detected)
  → Notification: "⚠️ High-VOC Filament Detected"

During print (5 min later):
  PM2.5: 28.3 µg/m³
  VOC: 185 ppb
  → Bento Box Fan: 80% (maintains high ventilation)

During print (15 min later):
  PM2.5: 42.1 µg/m³
  VOC: 285 ppb
  → Bento Box Fan: 100% (air quality degraded further)

Print completes:
  PM2.5: 38.5 µg/m³
  VOC: 265 ppb
  → Bento Box Fan: 80% (continues high ventilation)

45 minutes later:
  PM2.5: 15.2 µg/m³
  VOC: 110 ppb
  → Bento Box Fan: 60% (still moderate, continues)

90 minutes after print:
  PM2.5: 9.8 µg/m³
  VOC: 75 ppb
  → Bento Box Fan: OFF (air quality recovered)
```

### Example 3: Poor Initial Air Quality

**Scenario**: Starting print with already elevated air quality

```
Print starts:
  Filament: PETG (low-VOC)
  PM2.5: 42.0 µg/m³ (poor)
  VOC: 210 ppb (poor)
  → Bento Box Fan: 80% (poor air quality override)

After 10 minutes:
  PM2.5: 38.5 µg/m³
  VOC: 195 ppb
  → Bento Box Fan: 80% (still poor)

After 20 minutes:
  PM2.5: 28.2 µg/m³
  VOC: 145 ppb
  → Bento Box Fan: 60% (improving to moderate)
```

## Customization

### Adjust Filament Classifications

To add or modify filament types:

```yaml
# In the automation, modify this list:
{% set high_voc_materials = ['ABS', 'ASA', 'PC', 'NYLON', 'HIPS', 'POLYCARBONATE'] %}

# Add new materials:
{% set high_voc_materials = ['ABS', 'ASA', 'PC', 'NYLON', 'HIPS', 'POLYCARBONATE', 'PVA', 'CARBON_FIBER'] %}
```

### Adjust Speed Thresholds

To change fan speeds:

```yaml
# Example: More aggressive ventilation for high-VOC materials
{% elif (pm25 >= 35 or voc >= 200) or (is_high_voc and is_printing) %}
  100  # Changed from 80 to 100
```

### Change Post-Print Duration

To keep fan running longer after prints:

```yaml
# In conditions section, change from 45 minutes (2700 seconds) to 60 minutes:
{{ (as_timestamp(now()) - as_timestamp(print_end)) < 3600 }}
```

### Disable Notifications

To disable high-VOC filament alerts:

```yaml
# Comment out or remove this section:
# - if:
#     - condition: trigger
#       id: print_started
#     - condition: template
#       value_template: "{{ is_high_voc_filament }}"
#   then:
#     - action: notify.notify
#       ...
```

## Monitoring

### Logbook Entries

The automation creates logbook entries:
- "Bento Box Fan Adjusted" - When speed changes
- "Bento Box Fan Off" - When fan is turned off

### Notifications

- **High-VOC Filament Alert** - Sent when print starts with ABS/ASA/PC/etc.
- Includes current air quality readings
- Priority: High

### Entity States

Monitor the automation in Home Assistant:
- Check `fan.bento_box_fan` entity state
- View percentage attribute for current speed
- Review automation traces for debugging

## Troubleshooting

### Fan Not Responding

**Issue**: Automation triggers but fan doesn't change

**Solutions**:
1. Verify `fan.bento_box_fan` entity exists
2. Test manual control in Home Assistant UI
3. Check automation trace for errors
4. Ensure `continue_on_error: true` allows graceful failure

### Wrong Filament Type Detected

**Issue**: Automation treats PLA as high-VOC or vice versa

**Solutions**:
1. Check filament type in Bambu Studio/Handy app
2. Verify `sensor.ntk_ryansoffice_3dprinter_active_tray` shows correct type
3. Ensure filament type names match expected values (case-insensitive)
4. Add custom mappings if needed

### Fan Runs Too Long

**Issue**: Fan continues running after air quality is good

**Solutions**:
1. Reduce post-print duration (currently 45 minutes)
2. Lower thresholds for "good" air quality
3. Check air quality sensors are reporting correctly

### Fan Doesn't Run Long Enough

**Issue**: Fan turns off too soon after high-VOC prints

**Solutions**:
1. Increase post-print duration
2. Add to high-VOC materials list if needed
3. Lower speed thresholds for moderate air quality

## Best Practices

### Sensor Placement
- Place air quality sensor near printer but not inside enclosure
- Ensure sensor is downstream of enclosure exhaust
- Avoid direct airflow from Bento Box fan to sensor

### Enclosure Setup
- Ensure Bento Box has proper intake airflow
- Use activated carbon filter for VOC removal
- Consider HEPA filter for particle filtration
- Maintain filter cleanliness for optimal performance

### Filament Storage
- Store high-VOC filaments in well-ventilated area
- Keep desiccant in filament containers
- Label filaments clearly with material type

### Room Ventilation
- Open window or door when printing high-VOC materials
- Use Govee purifier in conjunction with Bento Box fan
- Consider whole-room air exchange for long ABS prints

## Safety Notes

⚠️ **Important Safety Information**:

1. **Ventilation is Critical**: High-VOC filaments release potentially harmful fumes
2. **Multiple Layers of Protection**: Use Bento Box fan + Govee purifier + room ventilation
3. **Monitor Air Quality**: Watch for elevated PM2.5 and VOC readings
4. **Health Considerations**: Avoid prolonged exposure to ABS/ASA fumes
5. **Printer Enclosure**: Ensure enclosure seals properly for effective fume extraction

## Related Automations

This Bento Box fan automation works alongside:

- **print_started_auto_purifier.yaml** - Controls Govee air purifier
- **auto_adjust_purifier_speed.yaml** - Adjusts purifier speed during printing
- **print_complete_continue_purifier.yaml** - Post-print purifier control
- **air_quality_alert.yaml** - Sends alerts for poor air quality

All automations work independently but complement each other for comprehensive air quality management.

## Support

For issues or questions:
1. Check automation traces in Home Assistant
2. Review logbook for fan control events
3. Verify air quality sensor readings
4. Consult main docs/features/air_quality/README.md
5. Check filament type attribute in Developer Tools > States

## Summary

The Bento Box fan automation provides intelligent, filament-aware ventilation control that:

✅ **Detects high-VOC materials** and increases ventilation automatically  
✅ **Responds to air quality** in real-time  
✅ **Runs independently** of other fans and purifiers  
✅ **Continues post-print** for extended fume extraction  
✅ **Alerts users** when printing with toxic materials  
✅ **Saves energy** by turning off when not needed  

This provides an essential layer of safety and air quality management for 3D printing, especially when working with engineering-grade materials.

