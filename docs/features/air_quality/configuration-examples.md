# Air Quality Integration - Configuration Examples

This document provides complete, working examples of how to configure the air quality integration with common setups.

## Example 1: Basic Setup with AirGradient and Govee

### Your Devices
- **Air Gradient ONE** sensor
- **Govee GoveeLife Smart Air Purifier Lite**
- **Bambu Lab X1 Carbon**

### Step-by-Step Configuration

#### 1. Identify Your Entity Names

After integrating your devices, find entity IDs in **Developer Tools > States**:

```
Air Gradient Sensor:
  sensor.airgradient_one_pm25
  sensor.airgradient_one_co2
  sensor.airgradient_one_tvoc
  sensor.airgradient_one_temperature
  sensor.airgradient_one_humidity

Govee Purifier:
  fan.govee_h7121_air_purifier

Bambu Lab Printer:
  Device ID: abc123def456
  sensor.x1_carbon_print_status
  sensor.x1_carbon_task_name
```

#### 2. Dashboard Card Configuration

Open [homeassistant/packages/3d_printing/air_quality/dashboard_cards/air-quality-cards.yaml](../../../../homeassistant/packages/3d_printing/air_quality/dashboard_cards/air-quality-cards.yaml) and update:

**Before:**
```yaml
secondary: |-
  {% set pm25 = states('sensor.airgradient_pm25') | float(0) %}
  {{ pm25 | round(1) }} µg/m³
```

**After:**
```yaml
secondary: |-
  {% set pm25 = states('sensor.airgradient_one_pm25') | float(0) %}
  {{ pm25 | round(1) }} µg/m³
```

**Complete Find & Replace:**
```
Find: sensor.airgradient_pm25
Replace: sensor.airgradient_one_pm25

Find: sensor.airgradient_co2
Replace: sensor.airgradient_one_co2

Find: sensor.airgradient_tvoc
Replace: sensor.airgradient_one_tvoc

Find: sensor.airgradient_temperature
Replace: sensor.airgradient_one_temperature

Find: sensor.airgradient_humidity
Replace: sensor.airgradient_one_humidity

Find: fan.govee_air_purifier
Replace: fan.govee_h7121_air_purifier
```

#### 3. Automation Configuration

For `print_started_auto_purifier.yaml`:

**Before:**
```yaml
triggers:
  - device_id: YOUR_PRINTER_DEVICE_ID_HERE
    domain: bambu_lab
    type: event_print_started
    trigger: device
```

**After:**
```yaml
triggers:
  - device_id: abc123def456
    domain: bambu_lab
    type: event_print_started
    trigger: device
```

**Complete Find & Replace in all automation files:**
```
Find: YOUR_PRINTER_DEVICE_ID_HERE
Replace: abc123def456

Find: sensor.ntk_ryansoffice_3dprinter_task_name
Replace: sensor.x1_carbon_task_name

Find: sensor.ntk_ryansoffice_3dprinter_print_status
Replace: sensor.x1_carbon_print_status

Find: sensor.ntk_ryansoffice_3dprinter_smart_status
Replace: sensor.x1_carbon_smart_status

Find: sensor.airgradient_pm25
Replace: sensor.airgradient_one_pm25

Find: sensor.airgradient_co2
Replace: sensor.airgradient_one_co2

Find: sensor.airgradient_tvoc
Replace: sensor.airgradient_one_tvoc

Find: fan.govee_air_purifier
Replace: fan.govee_h7121_air_purifier
```

> For new dashboard/notification-style logic, prefer `*_smart_status` entities; keep `*_print_status` only where you explicitly need raw Bambu integration state values.

#### 4. Remove Bento Box Fan (If Not Used)

If you don't have a Bento Box fan, remove these sections from automations:

```yaml
# DELETE OR COMMENT OUT:
- action: fan.turn_on
  target:
    entity_id: fan.bento_box_fan
  data:
    percentage: 66
  continue_on_error: true
```

## Example 2: ESPHome Air Quality Sensor

### Your Devices
- **ESPHome DIY Air Quality Sensor** (PM2.5, CO2, VOC)
- **Smart plug controlling a regular air purifier**
- **Bambu Lab P1S**

### Entity Names
```
ESPHome Sensor:
  sensor.office_air_pm25
  sensor.office_air_co2
  sensor.office_air_tvoc
  sensor.office_air_temperature
  sensor.office_air_humidity

Smart Plug (as purifier):
  switch.air_purifier_plug

Printer:
  Device ID: xyz789abc123
  sensor.p1s_print_status
  sensor.p1s_task_name
```

### Configuration Changes

Since you're using a switch instead of a fan entity, modify automations:

**Original (Fan Entity):**
```yaml
- action: fan.turn_on
  target:
    entity_id: fan.govee_air_purifier
  data:
    percentage: 66
```

**Modified (Switch Entity):**
```yaml
- action: switch.turn_on
  target:
    entity_id: switch.air_purifier_plug
```

**For Dashboard Card:**
Replace the Govee purifier card with a simple switch card:

```yaml
- type: custom:mushroom-template-card
  primary: Air Purifier
  secondary: |-
    {% if is_state('switch.air_purifier_plug', 'on') %}
      On
    {% elif is_state('switch.air_purifier_plug', 'off') %}
      Off
    {% else %}
      Unavailable
    {% endif %}
  icon: mdi:air-purifier
  icon_color: |-
    {% if is_state('switch.air_purifier_plug', 'on') %}
      green
    {% else %}
      grey
    {% endif %}
  tap_action:
    action: toggle
  hold_action:
    action: more-info
```

Remove speed control buttons since switches are on/off only.

## Example 3: Multiple Printers with Shared Air Quality System

### Your Devices
- **Two Bambu Lab printers** (X1C and P1S)
- **Single AirGradient sensor** (centrally located)
- **Govee air purifier**

### Configuration Strategy

Create separate automations for each printer but use the same air quality sensors.

**Automation 1: X1C Print Started**
```yaml
alias: Print Started - Auto Purifier (X1C)
triggers:
  - device_id: x1c_device_id_here
    domain: bambu_lab
    type: event_print_started
    trigger: device
# ... rest of automation
```

**Automation 2: P1S Print Started**
```yaml
alias: Print Started - Auto Purifier (P1S)
triggers:
  - device_id: p1s_device_id_here
    domain: bambu_lab
    type: event_print_started
    trigger: device
# ... rest of automation
```

Both automations control the same purifier and monitor the same air quality sensors.

**Modify Print Complete automation** to check if ANY printer is still printing:

```yaml
conditions:
  - condition: or
    conditions:
      # X1C is currently printing
      - condition: state
        entity_id: sensor.x1c_print_status
        state: "printing"
      
      # P1S is currently printing
      - condition: state
        entity_id: sensor.p1s_print_status
        state: "printing"
```

## Example 4: Advanced Setup with Multiple Sensors

### Your Devices
- **AirGradient sensor near printer**
- **Additional temperature/humidity sensor**
- **Govee air purifier**
- **Smart exhaust fan**
- **Bambu Lab printer**

### Configuration

Add additional sensor cards to dashboard:

```yaml
# Additional Temperature Sensor
- type: custom:mushroom-template-card
  primary: Printer Temp
  secondary: |-
    {% set temp = states('sensor.printer_enclosure_temperature') | float(0) %}
    {{ temp | round(1) }}°C
  icon: mdi:thermometer
  icon_color: |-
    {% set temp = states('sensor.printer_enclosure_temperature') | float(0) %}
    {% if temp < 25 %}
      green
    {% elif temp < 35 %}
      amber
    {% else %}
      red
    {% endif %}
```

Add exhaust fan control to automations:

```yaml
# Turn on exhaust fan when VOC is high
- action: fan.turn_on
  target:
    entity_id: fan.exhaust_fan
  data:
    percentage: 100
  condition:
    - condition: numeric_state
      entity_id: sensor.airgradient_tvoc
      above: 200
```

## Example 5: Using Preset Modes (Some Govee Models)

Some Govee purifiers use `preset_mode` instead of `percentage`.

### Check Your Purifier

In **Developer Tools > States**, look at `fan.govee_air_purifier`:

**If you see:**
```yaml
preset_modes:
  - low
  - medium
  - high
  - auto
```

Then your purifier uses preset modes.

### Modify Automations

**Original:**
```yaml
- action: fan.set_percentage
  target:
    entity_id: fan.govee_air_purifier
  data:
    percentage: 66
```

**Modified:**
```yaml
- action: fan.set_preset_mode
  target:
    entity_id: fan.govee_air_purifier
  data:
    preset_mode: medium
```

**Preset mode mapping:**
```
Low:    preset_mode: low
Medium: preset_mode: medium
High:   preset_mode: high
Auto:   preset_mode: auto
```

### Modify Dashboard Speed Buttons

```yaml
# Low Speed Button
- type: custom:mushroom-template-card
  primary: Low
  icon: mdi:fan-speed-1
  icon_color: |-
    {% if state_attr('fan.govee_air_purifier', 'preset_mode') == 'low' %}
      green
    {% else %}
      grey
    {% endif %}
  tap_action:
    action: call-service
    service: fan.set_preset_mode
    target:
      entity_id: fan.govee_air_purifier
    data:
      preset_mode: low
```

## Common Modifications

### Change Alert Thresholds

To make alerts less sensitive (fewer notifications):

**Original:**
```yaml
- trigger: numeric_state
  entity_id: sensor.airgradient_pm25
  above: 35
  for:
    minutes: 2
```

**Less Sensitive:**
```yaml
- trigger: numeric_state
  entity_id: sensor.airgradient_pm25
  above: 55  # Higher threshold
  for:
    minutes: 5  # Longer delay
```

### Adjust Purifier Speeds

To run purifier at higher speeds:

**Original:**
```yaml
{# Good air quality #}
{% else %}
  33  # Low speed
{% endif %}
```

**Higher Speed:**
```yaml
{# Good air quality #}
{% else %}
  50  # Medium-low speed instead
{% endif %}
```

### Change Post-Print Duration

To keep purifier running longer after prints:

**Original:**
```yaml
# Wait 30 minutes
- delay:
    minutes: 30
```

**Longer Duration:**
```yaml
# Wait 60 minutes
- delay:
    minutes: 60
```

### Disable Notifications

To disable notifications but keep automation functionality:

**Comment out notification actions:**
```yaml
# - action: notify.notify
#   data:
#     title: "Alert Title"
#     message: "Alert message"
```

Keep the logbook entries for troubleshooting:
```yaml
- action: logbook.log  # Keep this
  data:
    name: Air Purification Started
    message: Purifier turned on
```

## Testing Your Configuration

### 1. Test Dashboard Cards

```
1. Open your dashboard
2. Verify all sensor values are displaying
3. Tap PM2.5 card → Should show history graph
4. Tap purifier card → Should toggle on/off
5. Tap speed buttons → Should change purifier speed
6. Check colors match sensor values
```

### 2. Test Individual Automation

```
1. Settings > Automations & Scenes
2. Find your automation
3. Click ⋮ menu > Run
4. Check that it executes without errors
5. Verify in Logbook that actions completed
```

### 3. Test End-to-End

```
1. Start a test print
2. Watch for:
   - Purifier turns on (within 5 seconds)
   - Notification sent (if enabled)
   - Logbook entry created
3. Monitor air quality readings
4. Verify purifier speed adjusts if enabled
5. After print completes:
   - Purifier continues running
   - After 30 min, check if turned off/reduced
```

### 4. Check Logs

```
Settings > System > Logs

Look for:
  - "Air Purification Started"
  - "Air Purifier Speed Increased/Decreased"
  - "Air Purification Complete"
  
No errors should appear related to your entities
```

## Troubleshooting Your Configuration

### Entity Not Found

**Error:** `Entity sensor.airgradient_pm25 not found`

**Solution:**
1. Go to Developer Tools > States
2. Search for "pm25" or "pm2.5"
3. Copy exact entity ID
4. Update in your configuration
5. Entity names are case-sensitive!

### Purifier Not Responding

**Issue:** Automation runs but purifier doesn't turn on

**Check:**
1. Test manual control in Home Assistant UI
2. Verify entity ID is correct
3. Check if device uses `percentage` or `preset_mode`
4. Look at automation trace for errors
5. Check if service call is correct format

### Automation Not Triggering

**Issue:** Print starts but automation doesn't run

**Check:**
1. Verify automation is enabled (toggle on)
2. Confirm printer device ID is correct
3. Look at automation trace (shows why it didn't trigger)
4. Check if conditions are being met
5. Review printer integration status

### Colors Not Showing on Cards

**Issue:** Cards display but colors are grey

**Check:**
1. Verify card-mod is installed via HACS
2. Clear browser cache (Ctrl+Shift+R)
3. Check browser console for errors (F12)
4. Try different browser
5. Verify template syntax is correct

## Migration from Other Systems

### From Separate Air Quality Dashboard

If you already have air quality cards elsewhere:

1. Copy sensor entity IDs from existing cards
2. Use them in the new configuration
3. Test new cards alongside old ones
4. Once verified, remove old cards
5. Update any automations referencing old cards

### From Manual Purifier Control

If you currently control purifier manually:

1. Install automations but keep them disabled initially
2. Test each automation individually
3. Monitor for a few days
4. Enable automations one at a time
5. Adjust thresholds based on your patterns

### From Different Integration

If switching from different air quality sensor:

1. Keep old integration installed initially
2. Add new sensor integration
3. Update dashboard with new entity IDs
4. Compare readings for a day
5. Remove old integration once verified

## Support and Resources

**Need Help?**
- Check README.md for detailed explanations
- Review QUICK_SETUP.md for step-by-step guide
- Check Home Assistant logs for errors
- Review automation traces for troubleshooting

**Community Resources:**
- [Home Assistant Community Forums](https://community.home-assistant.io/)
- [AirGradient Documentation](https://www.airgradient.com/documentation/)
- [Govee Integration GitHub](https://github.com/LaggAt/hacs-govee)

**Example Configurations:**
All examples in this document are tested and working. Adjust entity names to match your setup and you should have a functional system within minutes!



