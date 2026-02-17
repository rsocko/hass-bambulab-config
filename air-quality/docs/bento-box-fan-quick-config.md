# Bento Box Fan - Quick Configuration Guide

## What Changed?

The Bento Box fan is now controlled by a **dedicated automation** that's smarter and independent:

- ✅ **Before**: Hard-coded 66% speed when print starts, turns off after 30 minutes
- ✅ **Now**: Dynamic 0-100% speed based on filament type + air quality, runs 45 minutes

## Quick Setup (5 Minutes)

### Step 1: Get Your Entity IDs

Find these in **Developer Tools > States**:

```
Printer Device ID: [From Settings > Devices > Bambu Lab > Your Printer]
Bento Box Fan: fan.bento_box_fan
Active Tray: sensor.ntk_ryansoffice_3dprinter_active_tray
Air Quality: sensor.airgradient_pm25, sensor.airgradient_tvoc
```

### Step 2: Update the Automation

Edit `bento_box_fan_auto_control.yaml`:

```yaml
# Line 14 & 23: Replace with your printer device ID
device_id: YOUR_PRINTER_DEVICE_ID_HERE

# Line 50, 107: Replace with your Bento Box fan entity
entity_id: fan.bento_box_fan

# Lines 30-34, 62: Replace with your printer sensor prefix
sensor.ntk_ryansoffice_3dprinter_active_tray
sensor.ntk_ryansoffice_3dprinter_print_status
sensor.ntk_ryansoffice_3dprinter_end_time

# Lines 32, 65: Replace with your air quality sensors
sensor.airgradient_pm25
sensor.airgradient_tvoc
sensor.airgradient_co2
```

### Step 3: Import Automation

1. Settings > Automations & Scenes
2. Click "+" > "⋮" menu > "Edit in YAML"
3. Paste entire contents of `bento_box_fan_auto_control.yaml`
4. Save

### Step 4: Update Existing Automations (Optional but Recommended)

If you're using the existing air quality automations, update them to remove duplicate Bento Box fan control:

**Option A: Update existing files**
- Use the updated versions of `print_started_auto_purifier.yaml` and `print_complete_continue_purifier.yaml` 
- These have Bento Box fan control removed

**Option B: Keep old versions**
- The new automation will override the old controls
- May cause brief conflicts but won't break anything

## How It Works

### Example 1: Printing PLA (Low-VOC)

```
Print Starts:
→ Filament: PLA
→ PM2.5: 8 µg/m³, VOC: 45 ppb (good)
→ Bento Box Fan: 30% (low circulation)

During Print (air quality increases slightly):
→ PM2.5: 11 µg/m³, VOC: 85 ppb
→ Bento Box Fan: 40% (adjusted for slight elevation)

Print Completes:
→ Fan continues at 40% for 45 minutes
→ Then turns OFF when air quality is good
```

### Example 2: Printing ABS (High-VOC)

```
Print Starts:
→ Filament: ABS (HIGH-VOC DETECTED!)
→ PM2.5: 8 µg/m³, VOC: 45 ppb (good)
→ Bento Box Fan: 80% (high ventilation for toxic material)
→ Notification: "⚠️ High-VOC Filament Detected"

During Print (air quality degrades):
→ PM2.5: 42 µg/m³, VOC: 285 ppb (poor)
→ Bento Box Fan: 100% (maximum ventilation)

Print Completes:
→ Fan continues at 80-100% for 45+ minutes
→ Only reduces/turns off when air quality recovers
```

## Filament Classifications

### High-VOC (80-100% Fan Speed)
- ABS - Most common engineering plastic
- ASA - Weather-resistant ABS alternative
- PC - Polycarbonate (very high strength)
- Nylon - Engineering plastic
- HIPS - Support material

### Low-VOC (30-40% Fan Speed)
- PLA - Standard 3D printing plastic
- PETG - Engineering plastic
- TPU - Flexible material

## Customization

### Add More High-VOC Filaments

```yaml
# Line 67 in the automation:
{% set high_voc_materials = ['ABS', 'ASA', 'PC', 'NYLON', 'HIPS', 'POLYCARBONATE'] %}

# Add your materials:
{% set high_voc_materials = ['ABS', 'ASA', 'PC', 'NYLON', 'HIPS', 'POLYCARBONATE', 'PVA', 'CARBON_FIBER_ABS'] %}
```

### Adjust Fan Speeds

```yaml
# Line 76: Change from 80% to 100% for high-VOC materials
{% elif (pm25 >= 35 or voc >= 200) or (is_high_voc and is_printing) %}
  100  # Changed from 80

# Line 80: Change from 60% to 70% for moderate conditions
{% elif (pm25 >= 12 or voc >= 100) or is_high_voc %}
  70  # Changed from 60
```

### Change Post-Print Duration

```yaml
# Line 37: Change from 45 minutes (2700 seconds) to 60 minutes
{{ (as_timestamp(now()) - as_timestamp(print_end)) < 3600 }}
```

### Disable High-VOC Notifications

```yaml
# Lines 116-135: Comment out the entire notification section
# - if:
#     - condition: trigger
#       id: print_started
#     ...
```

## Testing

### Test 1: Manual Trigger
1. Go to the automation
2. Click "Run"
3. Check fan responds (if printing)

### Test 2: Print Start
1. Start a print with PLA
2. Fan should turn on at 30-40%
3. Check logbook for "Bento Box Fan Adjusted"

### Test 3: Print Start with ABS
1. Start a print with ABS
2. Fan should turn on at 80%
3. Check for high-VOC notification

### Test 4: Air Quality Response
1. During print, monitor air quality
2. If PM2.5 or VOC increases, fan should speed up
3. Check logbook entries every 5 minutes

## Troubleshooting

### Fan Not Responding

**Check:**
1. Entity ID is correct: `fan.bento_box_fan`
2. Fan works manually in HA UI
3. Automation is enabled
4. Review automation trace for errors

### Wrong Filament Detected

**Check:**
1. Active tray sensor shows correct filament type
2. Filament type name matches expected (PLA, ABS, etc.)
3. Case doesn't matter (automation converts to uppercase)

### Fan Runs Too Long/Short

**Adjust:**
1. Post-print duration (line 37)
2. Air quality thresholds (lines 75-87)
3. Speed percentages (lines 75-87)

## Benefits

### For Health
- ✅ Better fume extraction with high-VOC materials
- ✅ Reduced exposure to toxic vapors
- ✅ Automatic detection (no manual control needed)

### For Air Quality
- ✅ Faster recovery after printing
- ✅ Lower PM2.5 and VOC levels
- ✅ Extended filtering for problematic materials

### For Convenience
- ✅ Set it and forget it
- ✅ Automatically adjusts to filament type
- ✅ Smart notifications for toxic materials
- ✅ Works independently (won't interfere with other fans)

## Integration with Other Automations

The Bento Box fan automation works **alongside** (not instead of):

- **Govee Purifier** - Filters room air (separate from enclosure)
- **Chamber Fan** - Controlled by printer firmware for print quality
- **Air Quality Alerts** - Still get notifications for poor air quality

All work together for comprehensive air management!

## Next Steps

1. ✅ Import the automation
2. ✅ Update entity IDs
3. ✅ Test with a PLA print
4. ✅ Test with an ABS print (if available)
5. ✅ Monitor and adjust thresholds as needed
6. ✅ Read full documentation: `docs/bento-box-fan-filament-control.md`

## Support

Questions? Check:
- Full documentation: `docs/bento-box-fan-filament-control.md`
- Main README: `air-quality/README.md`
- Automation traces in Home Assistant
- Logbook entries for "Bento Box Fan"

**You're all set! The Bento Box fan will now intelligently manage ventilation based on what you're printing! 🖨️💨**
