# Air Quality Monitoring and Control

This directory contains Home Assistant configurations for monitoring air quality and automatically controlling air purification during 3D printing operations.

## Overview

The air quality integration provides:

1. **Dashboard Cards** - Visual display of air quality sensors and purifier controls
2. **Automations** - Intelligent air quality management during and after printing
3. **Alerts** - Notifications when air quality degrades

## Features

### 📊 Air Quality Monitoring
- **PM2.5** - Particulate matter (fine particles from printing)
- **CO2** - Carbon dioxide levels (ventilation indicator)
- **VOC** - Volatile organic compounds (from filament off-gassing)
- **Temperature** - Room temperature
- **Humidity** - Relative humidity

### 🌬️ Air Purification Control
- **Govee Air Purifier** - Smart control with speed adjustment based on air quality
- **Bento Box Fan** - Independent enclosure ventilation based on air quality AND filament type
  - Automatically detects high-VOC materials (ABS, ASA, PC, Nylon, HIPS)
  - Adjusts ventilation speed based on filament toxicity
  - Runs independently of chamber fan and purifier
- **Color-coded status** - Visual feedback on air quality levels

### 🤖 Smart Automations
1. **Print Started** - Auto-enable purifier at appropriate speed
2. **Dynamic Speed Adjustment** - Adjust purifier based on real-time air quality
3. **Post-Print Filtering** - Continue purification for 30 minutes after print
4. **Air Quality Alerts** - Notifications when air quality degrades
5. **Bento Box Fan Control** - Filament-aware enclosure ventilation
   - Detects high-VOC filaments and increases ventilation
   - Responds to PM2.5 and VOC levels in real-time
   - Extended 45-minute post-print filtering for toxic materials
6. **Filter Tracking** - Monitor HEPA and carbon filter usage (NEW!)
   - Tracks fan runtime hours automatically
   - Usage percentage and replacement alerts
   - Know exactly when to replace filters

## Required Hardware

### Air Quality Sensor
- **AirGradient** sensor (recommended)
  - Measures PM2.5, CO2, VOC, Temperature, Humidity
  - Available as DIY kit or pre-built unit
  - [AirGradient Website](https://www.airgradient.com/)

- **Alternative:** ESPHome-based air quality sensor
  - Compatible with various PM, CO2, and VOC sensors
  - More customizable but requires assembly

### Air Purifier
- **Govee GoveeLife Smart Air Purifier Lite**
  - Smart control via Home Assistant
  - Available through Govee integration (HACS)
  
- **Alternative:** Any smart fan/purifier with Home Assistant integration

### Optional
- **Bento Box Fan** - ESP32-controlled enclosure fan
- **Smart Switches** - For controlling dumb purifiers

## Installation

### 1. Install Required Custom Cards

Install via HACS:
- `mushroom` - Minimalist card designs
- `card-mod` - Custom styling

### 2. Install Required Integrations

#### AirGradient Integration
**Option A: Official AirGradient Integration**
1. Add integration via Settings > Devices & Services
2. Search for "AirGradient"
3. Enter your device's IP address
4. Device entities will be created automatically

**Option B: ESPHome (DIY)**
1. Flash ESPHome firmware to your AirGradient device
2. Add ESPHome integration
3. Configure sensor entities in ESPHome YAML

#### Govee Integration
1. Install "Govee" integration via HACS
2. Add integration via Settings > Devices & Services
3. Log in with your Govee account
4. Select your air purifier device

### 3. Add Dashboard Cards

1. Open the dashboard file: [homeassistant/packages/3d_printing/air_quality/dashboard_cards/air-quality-cards.yaml](../../../homeassistant/packages/3d_printing/air_quality/dashboard_cards/air-quality-cards.yaml)
2. **Update entity names** to match your devices:
   ```yaml
   # Update these entity names throughout the file:
   sensor.airgradient_pm25          -> sensor.YOUR_SENSOR_pm25
   sensor.airgradient_co2           -> sensor.YOUR_SENSOR_co2
   sensor.airgradient_tvoc          -> sensor.YOUR_SENSOR_tvoc
   sensor.airgradient_temperature   -> sensor.YOUR_SENSOR_temperature
   sensor.airgradient_humidity      -> sensor.YOUR_SENSOR_humidity
   fan.govee_air_purifier           -> fan.YOUR_PURIFIER
   fan.bento_box_fan                -> fan.YOUR_FAN (if applicable)
   ```
3. Copy the desired card section(s) from the file
4. Paste into your Home Assistant dashboard
5. Save and refresh

### 4. Configure Automations

#### Step 1: Update Entity Names
For each automation file in the [homeassistant/packages/3d_printing/air_quality/](../../../homeassistant/packages/3d_printing/air_quality/) directory:

1. **Get your printer device ID:**
   ```
   Settings > Devices & Services > Bambu Lab > [Your Printer] > Copy Device ID
   ```

2. **Update automation entity names:**
   - `YOUR_PRINTER_DEVICE_ID_HERE` → Your printer's device ID
   - `sensor.ntk_ryansoffice_3dprinter_*` → Your printer sensor entities
   - `sensor.airgradient_*` → Your air quality sensor entities
   - `fan.govee_air_purifier` → Your purifier entity
   - `fan.bento_box_fan` → Your fan entity (or remove if not used)

#### Step 2: Import Automations
1. Go to Settings > Automations & Scenes
2. Click "+" to add automation
3. Click "⋮" menu > "Edit in YAML"
4. Copy contents from automation file
5. Paste and save
6. Repeat for each automation file

#### Step 3: Test Automations
1. Manually trigger by clicking "Run" in automation editor
2. Check that entities are correctly referenced
3. Verify notifications are received
4. Monitor logbook for automation activity

## Files

### Dashboard Cards
- **[homeassistant/packages/3d_printing/air_quality/dashboard_cards/air-quality-cards.yaml](../../../homeassistant/packages/3d_printing/air_quality/dashboard_cards/air-quality-cards.yaml)** - Complete dashboard card configurations
  - Air quality sensor cards (horizontal layout)
  - Govee purifier control card with speed buttons
  - Overall air quality status indicator
  - Alternative grid layout for mobile

### Automations
- **`air_quality_alert.yaml`** - Alerts when air quality degrades
  - Monitors PM2.5, CO2, VOC thresholds
  - Sends notifications and persistent alerts
  - Configurable thresholds for each pollutant

- **`print_started_auto_purifier.yaml`** - Auto-enable purifier when print starts
  - Turns on purifier at speed based on current air quality
  - Sends notification with air quality readings
  - Note: Bento Box fan now controlled by separate automation

- **`auto_adjust_purifier_speed.yaml`** - Dynamic speed adjustment during printing
  - Checks air quality every 5 minutes
  - Adjusts purifier speed based on readings
  - Only runs during or within 30 min after printing

- **`print_complete_continue_purifier.yaml`** - Post-print air filtering
  - Keeps purifier running for 30 minutes
  - Turns off if air quality is good
  - Reduces to low speed if moderate
  - Continues if air quality is still poor
  - Note: Bento Box fan now controlled by separate automation

- **`bento_box_fan_auto_control.yaml`** - Filament-aware Bento Box fan control
  - **Detects high-VOC filaments** (ABS, ASA, PC, Nylon, HIPS)
  - **Adjusts speed** based on filament type + air quality
  - **Independent operation** - not tied to chamber fan or purifier
  - **Extended filtering** - runs 45 minutes post-print for toxic materials
  - **Smart notifications** - alerts when printing with high-VOC materials
  - See [Bento Box Fan Documentation](docs/bento-box-fan-filament-control.md) for details

- **`bento_box_filter_helpers.yaml`** - Filter tracking input helpers (NEW!)
  - **Runtime tracking** for HEPA and carbon filters
  - **Usage percentage** calculations
  - **Replacement date** tracking
  - **Configurable thresholds** for filter lifespan

- **`bento_box_filter_runtime_tracking.yaml`** - Automatic runtime accumulation (NEW!)
  - **Tracks fan runtime** every minute when fan is on
  - **Updates both filters** simultaneously
  - **Can be disabled** via toggle if needed

- **`bento_box_filter_alerts.yaml`** - Filter replacement notifications (NEW!)
  - **Alerts at 75%** - Monitor filters
  - **Alerts at 90%** - Order replacements
  - **Alerts at 100%** - Replace immediately
  - **Persistent notifications** for overdue filters
  - See [Filter Tracking Documentation](docs/bento-box-filter-tracking.md) for details

## Configuration

### Air Quality Thresholds

The automations use the following thresholds (adjust in YAML if needed):

#### PM2.5 (Particulate Matter 2.5µm)
- **Good:** 0-12 µg/m³
- **Moderate:** 12-35 µg/m³
- **Unhealthy:** 35-55 µg/m³
- **Very Unhealthy:** 55+ µg/m³

#### CO2 (Carbon Dioxide)
- **Good:** <800 ppm
- **Moderate:** 800-1200 ppm
- **Poor:** 1200-2000 ppm
- **Very Poor:** 2000+ ppm

#### VOC (Volatile Organic Compounds)
- **Good:** <100 ppb
- **Moderate:** 100-200 ppb
- **Poor:** 200-300 ppb
- **Very Poor:** 300+ ppb

### Purifier Speed Mapping

The automations use these speed settings:

- **33%** - Low speed (good air quality, quiet operation)
- **50%** - Medium-low (moderate air quality)
- **66%** - Medium (printing, moderate air quality)
- **80%** - High (poor air quality)
- **100%** - Maximum (very poor air quality)

Adjust these percentages in the automation YAML files if your purifier uses different speed ranges.

## Usage

### Manual Control
Use the dashboard cards to:
- Monitor air quality in real-time
- Toggle purifier on/off
- Set purifier speed (Low/Medium/High)
- View overall air quality status

### Automatic Operation
Once configured, the automations will:
1. Turn on purifier when print starts
2. Adjust speed based on air quality during printing
3. Continue filtering for 30 minutes after print completes
4. Send alerts if air quality degrades significantly

### Notifications
You'll receive notifications for:
- High PM2.5 levels (>35 µg/m³)
- High CO2 levels (>1200 ppm)
- High VOC levels (>200 ppb)
- Purifier speed increases during printing
- Purifier status after print completion

## Customization

### Adjusting Thresholds
Edit the automation YAML files to change when alerts trigger or purifier speeds change:

```yaml
# Example: Change PM2.5 alert threshold
- trigger: numeric_state
  entity_id: sensor.airgradient_pm25
  above: 35  # Change this value
  for:
    minutes: 2  # Change alert delay
```

### Changing Purifier Speeds
Modify the percentage values in automations:

```yaml
# Example: Change purifier speed for good air quality
{% else %}
  33  # Change from 33% to desired speed
{% endif %}
```

### Disabling Bento Box Fan
If you don't have a Bento Box fan, remove or comment out these sections:

```yaml
- action: fan.turn_on
  target:
    entity_id: fan.bento_box_fan
  data:
    percentage: 66
  continue_on_error: true  # This prevents errors if entity doesn't exist
```

### Adding Custom Actions
You can add additional actions to automations, such as:
- Turning on exhaust fans
- Sending alerts to specific devices
- Triggering smart home scenes
- Logging to external systems

## Troubleshooting

### Sensors Not Showing Data
1. Check integration is installed and configured
2. Verify sensor entities exist in Developer Tools > States
3. Check entity IDs match exactly in YAML files
4. Ensure sensor device is powered and connected

### Purifier Not Responding
1. Verify Govee integration is working
2. Check entity ID is correct
3. Test manual control in Home Assistant UI
4. Check if device supports percentage-based speed control
5. Some Govee models use `preset_mode` instead of `percentage`

### Automations Not Triggering
1. Check automation is enabled
2. Verify device_id is correct for your printer
3. Check conditions are met (e.g., purifier is on for auto-adjust)
4. Review automation traces in Home Assistant
5. Check logbook for error messages

### Entity ID Mismatches
Common entity naming patterns:
- **AirGradient Official:** `sensor.airgradient_[metric]`
- **ESPHome:** `sensor.esphome_airgradient_[metric]`
- **Govee:** `fan.govee_air_purifier_[room]`
- **Bambu Lab:** `sensor.[printer_name]_[metric]`

Use Developer Tools > States to find exact entity IDs.

### Colors Not Showing
1. Ensure `card-mod` is installed via HACS
2. Clear browser cache
3. Verify card-mod is loading (check browser console)
4. Try refreshing the dashboard

## Best Practices

### Sensor Placement
- Place Air Gradient sensor near the printer but not inside enclosure
- Ensure good air circulation around sensor
- Keep sensor away from direct airflow or vents
- Mount at breathing height (3-5 feet) for accurate readings

### Purifier Placement
- Position purifier within 5-10 feet of printer
- Ensure intake has clearance (no obstructions)
- Point output toward general room area
- Don't place directly in front of printer enclosure exhaust

### Filament Considerations
Different filaments produce different amounts of particles and VOCs:
- **Low VOC:** PLA, PETG
- **Medium VOC:** TPU, Nylon
- **High VOC:** ABS, ASA
- **Very High VOC:** Polycarbonate, some specialty filaments

Consider adjusting purifier speeds or thresholds based on filament type.

### Maintenance
- **Air Gradient:** Clean sensor every 3-6 months
- **Govee Purifier:** Replace filter per manufacturer schedule
- **Bento Box Fan:** Clean filter monthly

## Additional Resources

### AirGradient
- [Official Documentation](https://www.airgradient.com/documentation/)
- [DIY Assembly Guide](https://www.airgradient.com/open-airgradient/instructions/)
- [Home Assistant Integration](https://www.home-assistant.io/integrations/airgradient/)

### Govee
- [Govee Home Assistant Integration (HACS)](https://github.com/LaggAt/hacs-govee)
- [Govee Official App](https://www.govee.com/apps)

### Air Quality Information
- [EPA Air Quality Index](https://www.airnow.gov/aqi/aqi-basics/)
- [Indoor Air Quality Guide](https://www.epa.gov/indoor-air-quality-iaq)
- [3D Printing Air Quality Study](https://www.sciencedirect.com/science/article/pii/S1352231013004470)

## Contributing

When making improvements:
1. Test changes with your specific hardware
2. Update entity names in examples
3. Document any new thresholds or settings
4. Update this README with new features

## Related Integrations

Consider adding:
- **WLED** - Visual air quality indicators with LED strips
- **Smart Switches** - Control exhaust fans or windows
- **TTS/Speakers** - Voice announcements for alerts
- **Grafana/InfluxDB** - Historical air quality tracking
- **Node-RED** - Advanced automation flows

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review Home Assistant logs
3. Check automation traces
4. Open an issue in the repository
5. Consult Home Assistant community forums

## License

This configuration is provided as-is for use with Home Assistant and compatible hardware.



