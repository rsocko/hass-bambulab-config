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

## Deployment

This feature uses the standard loader deployment structure. It is loaded automatically when registered in `_feature_loaders.yaml`.

### Loader Registration

The air quality loader is registered in [`homeassistant/packages/3d_printing/_feature_loaders.yaml`](../../../homeassistant/packages/3d_printing/_feature_loaders.yaml):

```yaml
air_quality_loader: !include air_quality/air_quality_loader.yaml
```

The loader file [`air_quality_loader.yaml`](../../../homeassistant/packages/3d_printing/air_quality/air_quality_loader.yaml) includes:
- `automation:` → all automations via `!include_dir_merge_list automations`
- `input_number:` → filter tracking thresholds via `!include_dir_merge_named helpers/input_number`
- `input_datetime:` → filter replacement dates via `!include_dir_merge_named helpers/input_datetime`
- `input_boolean:` → filter tracking toggle via `!include_dir_merge_named helpers/input_boolean`
- `template: sensor:` → filter usage sensors via `!include_dir_merge_list template_sensors`

Deploy using the GitHub Actions workflow with `selected_packages` including `air_quality`, or use `packages_only` / `packages_www` profiles for full deploys.

### Prerequisites

#### Required Custom Cards (HACS)
- `mushroom` - Minimalist card designs
- `card-mod` - Custom styling
- `browser-mod` - Popup dialogs for purifier controls and Bento Box filter details

#### Required Integrations
- **AirGradient** - Official integration (device name: I-9PSL)
- **Govee** - Via [gv2mqtt](https://github.com/wez/govee2mqtt) MQTT bridge for purifier control

### Entity Reference

The following entity IDs are used throughout this feature (verified against live HA instance):

```yaml
# AirGradient I-9PSL Air Quality Sensor
sensor.i_9psl_pm2_5              # PM2.5 (µg/m³)
sensor.i_9psl_carbon_dioxide      # CO2 (ppm)
sensor.i_9psl_voc_index           # VOC index
sensor.i_9psl_temperature         # Temperature
sensor.i_9psl_humidity            # Humidity (%)

# Govee Air Purifier (via gv2mqtt)
switch.ryans_office_air_power_switch    # Power on/off
select.ryans_office_air_mode            # Mode: Auto, Custom, gearMode
number.ryans_office_air_gearmode        # Speed: 1 (Low), 2 (Medium), 3 (High)

# Bento Box Fan (ESPHome)
fan.3dprinter_controller_box_bento_box_fan  # Bento Box enclosure fan

# Printer (update device triggers with your device ID)
YOUR_PRINTER_DEVICE_ID_HERE      -> Your Bambu Lab device ID
sensor.ntk_ryansoffice_3dprinter_* -> Your printer sensor entities
```

Get your printer device ID from: Settings > Devices & Services > Bambu Lab > [Your Printer] > Copy Device ID

> **Note:** The Govee purifier uses gear modes (1-3), not percentage-based speed. The automations
> set `select.ryans_office_air_mode` to `gearMode` then adjust `number.ryans_office_air_gearmode`.

### Dashboard Integration

Add the air quality cards to `view_main.yaml` by including them in the fan controls section:

```yaml
# In view_main.yaml, after the fan_controls_v2 include:
- !include ../../air_quality/dashboard_cards/air-quality-cards.yaml
- !include ../../air_quality/dashboard_cards/bento-box-filter-cards.yaml
```

See [Deployment Recommendations](#deployment-recommendations) below for placement guidance.

## File Structure

```text
air_quality/
├── air_quality_loader.yaml              # Feature loader (registered in _feature_loaders.yaml)
├── automations/
│   ├── air_quality_alert.yaml           # PM2.5/CO2/VOC threshold alerts
│   ├── auto_adjust_purifier_speed.yaml  # Dynamic purifier speed during printing
│   ├── bento_box_fan_auto_control.yaml  # Filament-aware enclosure ventilation
│   ├── bento_box_filter_alerts.yaml     # Filter replacement notifications
│   ├── bento_box_filter_runtime_tracking.yaml  # Fan runtime accumulation
│   ├── print_complete_continue_purifier.yaml   # 30-min post-print filtering
│   └── print_started_auto_purifier.yaml        # Auto-enable on print start
├── helpers/
│   ├── input_boolean/
│   │   └── input_boolean_bento_box_filter_tracking_enabled.yaml
│   ├── input_datetime/
│   │   ├── input_datetime_bento_box_carbon_last_replaced.yaml
│   │   └── input_datetime_bento_box_hepa_last_replaced.yaml
│   └── input_number/
│       ├── input_number_bento_box_carbon_max_hours.yaml
│       ├── input_number_bento_box_carbon_runtime_hours.yaml
│       ├── input_number_bento_box_hepa_max_hours.yaml
│       └── input_number_bento_box_hepa_runtime_hours.yaml
├── template_sensors/
│   ├── bento_box_carbon_filter_usage.yaml
│   ├── bento_box_filter_status.yaml
│   └── bento_box_hepa_filter_usage.yaml
└── dashboard_cards/
    ├── air-quality-cards.yaml            # Consolidated AQ header + 2×3 sensor grid + purifier popup
    └── bento-box-filter-cards.yaml       # Compact Bento Box status card with detail popup
```

### Automations

| File | Purpose |
|---|---|
| `air_quality_alert.yaml` | Sends notifications when PM2.5 >35, CO2 >1200, or VOC >200 |
| `auto_adjust_purifier_speed.yaml` | Adjusts purifier speed every 5 min based on readings (only during/after prints) |
| `bento_box_fan_auto_control.yaml` | Filament-aware Bento Box fan control (detects ABS/ASA/PC/Nylon/HIPS) |
| `bento_box_filter_alerts.yaml` | Alerts at 75%/90%/100% filter usage thresholds |
| `bento_box_filter_runtime_tracking.yaml` | Accumulates fan runtime every minute when fan is on |
| `print_complete_continue_purifier.yaml` | Keeps purifier running 30 min post-print, then adjusts/stops |
| `print_started_auto_purifier.yaml` | Turns on purifier at appropriate speed when print starts |

### Helpers

| Entity | Type | Purpose |
|---|---|---|
| `input_number.bento_box_hepa_runtime_hours` | input_number | HEPA filter accumulated runtime |
| `input_number.bento_box_carbon_runtime_hours` | input_number | Carbon filter accumulated runtime |
| `input_number.bento_box_hepa_max_hours` | input_number | HEPA replacement threshold (default: 2000h) |
| `input_number.bento_box_carbon_max_hours` | input_number | Carbon replacement threshold (default: 1000h) |
| `input_datetime.bento_box_hepa_last_replaced` | input_datetime | Date of last HEPA replacement |
| `input_datetime.bento_box_carbon_last_replaced` | input_datetime | Date of last carbon replacement |
| `input_boolean.bento_box_filter_tracking_enabled` | input_boolean | Enable/disable filter tracking |

### Template Sensors

| Entity | Purpose |
|---|---|
| `sensor.bento_box_hepa_filter_usage` | HEPA filter usage % with status attributes |
| `sensor.bento_box_carbon_filter_usage` | Carbon filter usage % with status attributes |
| `sensor.bento_box_filter_status` | Combined filter status (Good/Monitor/Replace Soon/Replace Now) |

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
- Monitor air quality in real-time via the consolidated status header and sensor rows
- Tap the Purifier card to open a popup with power toggle and speed controls (Low/Medium/High)
- Tap the Bento Box card to see filter health, runtime, fan speed, and reset buttons
- View overall air quality status (Good/Moderate/Poor/Very Poor)

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

## Deployment Recommendations

### Dashboard Placement

The air quality cards fit naturally **below the fan controls** in the main dashboard view. This groups all ventilation/air-quality-related information together:

```
view_main.yaml section order (grid #2):
  printer-led-controls
  printer_controls (conditional)
  camera
  printer-temps
  fan_controls_v2           <-- existing fan controls
  air-quality-cards          <-- ADD HERE
  bento-box-filter-cards     <-- ADD HERE
```

Add these two lines to [view_main.yaml](../../../homeassistant/packages/3d_printing/common/dashboard_views/view_main.yaml) right after the `fan_controls_v2` include:

```yaml
    - !include ../../air_quality/dashboard_cards/air-quality-cards.yaml
    - !include ../../air_quality/dashboard_cards/bento-box-filter-cards.yaml
```

### Bento Box Fan Control Interaction

The `printer_controls` feature displays the Bento Box fan as a manual control card, while `air_quality` automatically adjusts the same fan based on air quality and filament type. This is by design:

- **Automatic mode** (air_quality) runs during and after prints
- **Manual override** (printer_controls card) lets you tap the card to open the more-info dialog and override speed
- The automatic control uses `mode: restart`, so it will resume automatic adjustments on the next scheduled check (every 5 minutes)

If you want fully manual control, disable the `bento_box_fan_auto_control` automation from the HA UI.

### Optional Sub-Features

You can deploy subsets of this feature by removing automations you don't need:

| If you don't have... | Remove these automations |
|---|---|
| Govee Air Purifier | `print_started_auto_purifier`, `auto_adjust_purifier_speed`, `print_complete_continue_purifier` |
| Bento Box Fan | `bento_box_fan_auto_control`, `bento_box_filter_runtime_tracking`, `bento_box_filter_alerts` |
| AirGradient Sensor | `air_quality_alert`, `auto_adjust_purifier_speed` (sensor-dependent portions) |

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



