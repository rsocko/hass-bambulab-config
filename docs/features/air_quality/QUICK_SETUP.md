# Air Quality Integration - Quick Setup Guide

Get your air quality monitoring and automated purification running in 15 minutes!

## Prerequisites

✅ Home Assistant installed and running  
✅ Bambu Lab 3D printer integrated  
✅ Air Gradient sensor (or ESPHome air quality sensor)  
✅ Govee air purifier (or compatible smart fan/purifier)  

## Step 1: Install Custom Cards (5 minutes)

1. Open HACS in Home Assistant
2. Go to **Frontend**
3. Click **"+ Explore & Download Repositories"**
4. Search for and install:
   - **Mushroom** - Required for card design
   - **card-mod** - Required for styling

5. Restart Home Assistant frontend (clear cache)

## Step 2: Integrate Your Devices (5 minutes)

### Air Gradient Sensor

**Option A: Official Integration**
1. Settings > Devices & Services
2. Click **"+ Add Integration"**
3. Search for **"AirGradient"**
4. Enter your device IP address
5. Complete setup

**Option B: Already using ESPHome?**
- Your air quality sensors are already integrated!
- Note your sensor entity IDs (e.g., `sensor.esphome_airgradient_pm25`)

### Govee Air Purifier

1. In HACS, go to **Integrations**
2. Search for **"Govee"** and install
3. Settings > Devices & Services
4. Click **"+ Add Integration"**
5. Search for **"Govee"**
6. Log in with your Govee account
7. Select your air purifier

## Step 3: Find Your Entity IDs (2 minutes)

1. Go to **Developer Tools > States**
2. Find and note these entities:

**Air Quality Sensors:**
```
sensor.airgradient_pm25         (or sensor.YOUR_SENSOR_pm25)
sensor.airgradient_co2          (or sensor.YOUR_SENSOR_co2)
sensor.airgradient_tvoc         (or sensor.YOUR_SENSOR_tvoc)
sensor.airgradient_temperature  (or sensor.YOUR_SENSOR_temperature)
sensor.airgradient_humidity     (or sensor.YOUR_SENSOR_humidity)
```

**Air Purifier:**
```
fan.govee_air_purifier          (or fan.YOUR_PURIFIER)
```

**Optional - Bento Box Fan:**
```
fan.bento_box_fan               (or fan.YOUR_FAN)
```

**Printer:**
```
sensor.YOUR_PRINTER_print_status
sensor.YOUR_PRINTER_task_name
```

## Step 4: Add Dashboard Cards (3 minutes)

1. Open the file: **[homeassistant/packages/3d_printing/air_quality/dashboard_cards/air-quality-cards.yaml](../../../homeassistant/packages/3d_printing/air_quality/dashboard_cards/air-quality-cards.yaml)**

2. **Find and replace** these entity names with yours:
   ```
   airgradient_pm25           → YOUR_SENSOR_pm25
   airgradient_co2            → YOUR_SENSOR_co2
   airgradient_tvoc           → YOUR_SENSOR_tvoc
   airgradient_temperature    → YOUR_SENSOR_temperature
   airgradient_humidity       → YOUR_SENSOR_humidity
   govee_air_purifier         → YOUR_PURIFIER_entity
   ```

3. Copy the card section you want:
   - **Lines 33-175**: Horizontal air quality sensors
   - **Lines 177-357**: Govee purifier control cards

4. Paste into your Home Assistant dashboard:
   - Click **Edit Dashboard**
   - Click **"+ Add Card"**
   - Choose **"Manual"** (bottom right)
   - Paste the YAML
   - Click **Save**

5. Verify cards display correctly with your live data

## Step 5: Configure Automations (Optional, 5 minutes each)

### Get Your Printer Device ID

1. Settings > Devices & Services
2. Find **Bambu Lab** integration
3. Click on your printer
4. Copy the **Device ID** from the URL (after `/config/devices/device/`)

### Add Automations

For each automation you want:

1. Open automation file from [homeassistant/packages/3d_printing/air_quality/](../../../homeassistant/packages/3d_printing/air_quality/) directory
2. Update these values:
   - `YOUR_PRINTER_DEVICE_ID_HERE` → Your printer's device ID
   - `ntk_ryansoffice_3dprinter` → Your printer entity prefix
   - `airgradient_*` → Your air sensor entity names
   - `govee_air_purifier` → Your purifier entity

3. Go to **Settings > Automations & Scenes**
4. Click **"+ Create Automation"**
5. Click **⋮ (menu)** > **"Edit in YAML"**
6. Paste the automation YAML
7. Click **Save**

**Recommended Automations:**
- ✅ **`print_started_auto_purifier.yaml`** - Auto-enable purifier when printing
- ✅ **`print_complete_continue_purifier.yaml`** - Continue filtering after print
- ⚠️ **`air_quality_alert.yaml`** - Alert on poor air quality (optional)
- ⚠️ **`auto_adjust_purifier_speed.yaml`** - Dynamic speed adjustment (optional)

## Step 6: Test Everything (5 minutes)

### Test Dashboard Cards
1. Check all sensor readings are displaying
2. Tap PM2.5 card - should show history graph
3. Tap purifier card - should toggle on/off
4. Tap speed buttons - should change purifier speed

### Test Automations
1. Go to **Settings > Automations & Scenes**
2. Find your air quality automation
3. Click **⋮ (menu)** > **"Run"**
4. Check that it executes correctly
5. View **Logbook** for confirmation

### Test End-to-End
1. Start a 3D print
2. Verify purifier turns on automatically (if automation enabled)
3. Monitor air quality readings during print
4. Check notifications (if alerts enabled)

## Troubleshooting

### "Entity not found" Error
- Double-check entity IDs in Developer Tools > States
- Entity names are case-sensitive
- Make sure devices are online and integrated

### Cards Not Showing Colors
- Verify `card-mod` is installed
- Clear browser cache (Ctrl+Shift+R)
- Check browser console for errors

### Purifier Not Responding
- Test manual control in Home Assistant UI first
- Some Govee models use `preset_mode` instead of `percentage`
- Check if device supports percentage-based speed control

### Automations Not Triggering
- Verify printer device ID is correct
- Check automation is **enabled** (toggle on)
- Review automation **traces** for errors
- Check **Logbook** for trigger events

## Quick Reference

### Entity ID Patterns

**AirGradient Official:**
```
sensor.airgradient_pm25
sensor.airgradient_co2
sensor.airgradient_tvoc
```

**ESPHome:**
```
sensor.esphome_airgradient_pm25
sensor.esphome_office_co2
sensor.esp32_air_tvoc
```

**Govee:**
```
fan.govee_air_purifier
fan.goveelife_air_purifier_lite
fan.govee_h7121_air_purifier
```

**Bambu Lab:**
```
sensor.[printer_name]_print_status
sensor.[printer_name]_task_name
Device ID: Settings > Devices > Bambu Lab > [Printer] > URL
```

## Next Steps

✅ **You're done!** You now have:
- Real-time air quality monitoring
- Smart purifier control
- Automated air management during printing

### Optional Enhancements

**Add Historical Tracking:**
- Install InfluxDB + Grafana for long-term data
- Create custom graphs in Home Assistant

**Integrate with Other Automation:**
- Link to smart window/vent controls
- Add voice announcements for alerts
- Connect to WLED for visual indicators

**Expand Monitoring:**
- Add PM1.0 and PM10 sensors
- Include outdoor air quality comparison
- Add air exchange rate calculations

## Support

Need help? Check:
1. **README.md** - Detailed configuration guide
2. **air-quality-cards-visual-reference.md** - Card design details
3. Home Assistant logs - Settings > System > Logs
4. Community forums - https://community.home-assistant.io/

## Summary

You should now have:
- ✅ Air quality sensors displaying on dashboard
- ✅ Govee purifier control cards working
- ✅ Automations managing air quality during prints
- ✅ Alerts for poor air quality (if enabled)

**Total setup time: ~15-20 minutes**

Enjoy cleaner air and safer 3D printing! 🖨️💨✨



