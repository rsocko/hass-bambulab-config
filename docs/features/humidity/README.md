# Humidity Intelligence for Bambu Lab AMS

Monitor humidity levels across your room and AMS units with an easy-to-use Home Assistant dashboard card.

## Screenshots

<!-- SCREENSHOT: id=humidity-cards-desktop | format=png | version=1.0 | package=humidity | added=2026-03-15 -->
<!-- Capture: Desktop view of all 3 humidity cards (AMS1, AMS2, Room) in optimal green state -->
> **📸 Screenshot needed:** Humidity cards — desktop layout, optimal conditions *(png)*

<!-- SCREENSHOT: id=humidity-cards-warning | format=png | version=1.0 | package=humidity | added=2026-03-15 -->
<!-- Capture: Cards showing mixed states — one green (optimal), one amber (monitoring), one red (attention needed) -->
> **📸 Screenshot needed:** Humidity cards — mixed warning states *(png)*

## Overview

This humidity monitoring solution provides real-time humidity and temperature data for your 3D printing environment:

- **Room Humidity** (optional) - Monitor the ambient humidity in your printer room
- **AMS 1 Humidity** - Track humidity and temperature inside AMS Unit 1
- **AMS 2 Humidity** - Track humidity and temperature inside AMS Unit 2

The card uses color-coded indicators to quickly identify when humidity levels are optimal (green), need monitoring (amber/orange), or require immediate attention (red).

## Dependencies & Requirements

> **Foundation:** This feature requires the [Core](../core/README.md) and [Common](../common/README.md) packages and the [ha-bambulab](https://github.com/greghesp/ha-bambulab) integration — see [Foundation Packages](../../README.md#foundation-packages).

This is a dashboard-card-only feature — it has no loader in `_feature_loaders.yaml` and is included via `!include` in `view_main.yaml`.

### External Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [ha-bambulab](https://github.com/greghesp/ha-bambulab) with AMS | **Yes** | Provides AMS humidity and temperature sensor entities |
| Room humidity sensor (e.g., Aqara, ESPHome) | No | Optional ambient room humidity monitoring — simply omit the room card section if not available |

### Custom Frontend Cards (HACS)

| Card | Required | Purpose |
|---|---|---|
| [mushroom](https://github.com/piitaya/lovelace-mushroom) | **Yes** | Minimalist card designs |
| [card-mod](https://github.com/thomasloven/lovelace-card-mod) | **Yes** | Color-coded humidity threshold styling |

## Features

- **Real-time Monitoring** - Live humidity and temperature readings
- **Color-Coded Status** - Visual indicators based on filament storage best practices
- **Click for Details** - Tap any card to view detailed sensor information and history
- **Responsive Design** - Automatically adapts to desktop and mobile layouts
- **Customizable** - Easy to modify colors, thresholds, and sensor entities

## Screenshots

The card displays as a horizontal stack with individual cards for each sensor:

```
┌─────────────┬─────────────┬─────────────┐
│   AMS 1     │   AMS 2     │    Room     │
│   15.2%     │   18.7%     │    45%      │
│   22.1°C    │   21.9°C    │    22°C     │
└─────────────┴─────────────┴─────────────┘
```

## Requirements

### Custom Cards (via HACS)

1. **[mushroom](https://github.com/piitaya/lovelace-mushroom)** - Minimalist cards
2. **[card-mod](https://github.com/thomasloven/lovelace-card-mod)** - Custom styling

### Sensors

The following sensors should be available in your Home Assistant instance:

- `sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_humidity` - AMS 1 humidity
- `sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_temperature` - AMS 1 temperature
- `sensor.3d_printer_ams_2_humidity_and_temp_humidity` - AMS 2 humidity
- `sensor.3d_printer_ams_2_humidity_and_temp_temperature` - AMS 2 temperature
- `sensor.room_humidity` (optional) - Room/office humidity sensor

These sensors are typically provided by the [Bambu Lab Home Assistant Integration](https://github.com/greghesp/ha-bambulab).

## Installation

### Step 1: Install Required Custom Cards

1. Open **HACS** in Home Assistant
2. Go to **Frontend**
3. Search for and install:
   - **Mushroom**
   - **card-mod**
4. Restart Home Assistant

### Step 2: Copy the Card Configuration

1. Open the [humidity-card.yaml](../../../homeassistant/packages/3d_printing/humidity/dashboard_cards/humidity-card.yaml) file
2. Copy the entire YAML configuration
3. Navigate to your Home Assistant dashboard
4. Click **Edit Dashboard** (top right)
5. Click **Add Card** (bottom right)
6. Select **Manual** at the bottom
7. Paste the YAML configuration
8. Click **Save**

### Step 3: Update Entity Names (if needed)

If your sensor entity names differ from the default:

1. Edit the card in your dashboard
2. Replace entity names with your actual sensor IDs
3. Common patterns:
   - `sensor.YOUR_PRINTER_NAME_ams1_humidity_temperature_humidity`
   - `sensor.YOUR_PRINTER_NAME_ams2_humidity_temperature_humidity`

### Step 4: Enable Room Sensor (optional)

If you have a room humidity sensor:

1. Edit the card configuration
2. Uncomment the "ROOM HUMIDITY" section (remove the `#` symbols)
3. Update the entity name to match your room sensor
4. Save the card

## Humidity Thresholds

### For 3D Printing Filament Storage

| Range | Humidity | Color | Status | Notes |
|-------|----------|-------|--------|-------|
| **Optimal** | < 20% | Green | Excellent | Ideal for hygroscopic materials like Nylon, TPU |
| **Good** | 20-40% | Light Green | Good | Acceptable for most filaments including PLA, PETG |
| **Monitor** | 40-60% | Amber | Watch | PLA/PETG still okay, monitor Nylon/TPU closely |
| **Concern** | 60-70% | Orange | Concern | Filament quality may degrade, consider desiccant |
| **Critical** | > 70% | Red | Action Needed | High risk of moisture absorption, replace desiccant |

### For General Room Comfort

| Range | Humidity | Status |
|-------|----------|--------|
| **Too Dry** | < 30% | May cause static, respiratory issues |
| **Optimal** | 40-60% | Comfortable for humans |
| **Too Humid** | > 70% | Risk of condensation, mold |

## Customization

### Change Temperature Units

To display temperatures in Fahrenheit instead of Celsius:

1. Edit the card configuration
2. Find the temperature display line:
   ```yaml
   {{ temp | round(1) }}°C
   ```
3. Replace with:
   ```yaml
   {{ ((temp * 9/5) + 32) | round(1) }}°F
   ```

### Adjust Color Thresholds

To modify when colors change, edit the `icon_color` section:

```yaml
icon_color: |-
  {% set humidity = states('sensor.YOUR_SENSOR') | float(-1) %}
  {% if humidity < 0 %}
    grey           # Sensor unavailable
  {% elif humidity < 20 %}
    green          # Change this threshold
  {% elif humidity < 40 %}
    light-green    # Change this threshold
  {% elif humidity < 60 %}
    amber          # Change this threshold
  {% elif humidity < 70 %}
    orange         # Change this threshold
  {% else %}
    red            # Above threshold
  {% endif %}
```

### Change Card Layout

**Vertical Stack** (for narrow spaces):
```yaml
type: vertical-stack
cards:
  # ... rest of cards
```

**Grid Layout** (for multiple sensors):
```yaml
type: grid
columns: 2
square: false
cards:
  # ... rest of cards
```

### Add More AMS Units

To add AMS 3, AMS 4, etc.:

1. Copy one of the AMS card blocks
2. Update the entity names:
   - `sensor.3d_printer_ams_3_humidity_and_temp_humidity`
   - `sensor.3d_printer_ams_3_humidity_and_temp_temperature`
3. Change the `primary` label to "AMS 3"
4. Optionally adjust the background color in `card_mod` section

### Custom Icons

Available icons (see [Material Design Icons](https://pictogrammers.com/library/mdi/) for more):

- `mdi:home-thermometer-outline` - Room sensor
- `mdi:package-variant` - AMS unit
- `mdi:package-variant-closed` - AMS unit (alternative)
- `mdi:water-percent` - Humidity specific
- `mdi:thermometer` - Temperature specific
- `mdi:air-humidifier` - Humidifier/dehumidifier

## Troubleshooting

### Cards Not Appearing

1. Verify custom cards are installed via HACS
2. Clear browser cache and hard reload (Ctrl+Shift+R)
3. Check browser console for errors (F12)
4. Verify entity names match your sensors

### Sensors Show "N/A"

1. Check that the Bambu Lab integration is working
2. Verify sensor entity IDs in Developer Tools → States
3. Ensure AMS units are powered on and connected
4. Wait a few minutes for sensors to initialize

### Wrong Colors or Values

1. Verify humidity values are reasonable (0-100%)
2. Check temperature sensor units (°C vs °F)
3. Review threshold values in `icon_color` section
4. Test with known good sensor values

### Mobile Layout Issues

1. Use horizontal-stack for desktop (auto-stacks on mobile)
2. Consider grid layout with `columns: 2` for better mobile UX
3. Test in Home Assistant mobile app
4. Check card widths don't exceed screen width

## Automation Ideas

### Alert on High Humidity

```yaml
automation:
  - alias: "AMS High Humidity Alert"
    trigger:
      - platform: numeric_state
        entity_id: 
          - sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_humidity
          - sensor.3d_printer_ams_2_humidity_and_temp_humidity
        above: 60
        for:
          minutes: 15
    action:
      - service: notify.mobile_app
        data:
          title: "AMS Humidity Warning"
          message: "AMS humidity is {{ states(trigger.entity_id) }}% - consider replacing desiccant"
```

### Track Humidity History

Create a sensor to track daily averages:

```yaml
sensor:
  - platform: statistics
    name: "AMS 1 Daily Average Humidity"
    entity_id: sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_humidity
    state_characteristic: mean
    max_age:
      hours: 24
```

### Desiccant Replacement Reminder

```yaml
automation:
  - alias: "Desiccant Replacement Reminder"
    trigger:
      - platform: numeric_state
        entity_id: sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_humidity
        above: 40
        for:
          days: 7
    action:
      - service: notify.persistent_notification
        data:
          title: "AMS 1 Desiccant Replacement"
          message: "Humidity has been above 40% for 7 days. Consider replacing AMS 1 desiccant pack."
```

## Related Resources

- [AMS Header Cards](../printer_dashboards/card-templates-README.md) - Inline humidity/temperature indicators on each AMS header (uses the same threshold mappings)
- [Bambu Lab Home Assistant Integration](https://github.com/greghesp/ha-bambulab)
- [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom)
- [Card-mod Documentation](https://github.com/thomasloven/lovelace-card-mod)
- [Home Assistant Lovelace Documentation](https://www.home-assistant.io/lovelace/)

## Contributing

Found a bug or have a suggestion? Please open an issue in the main repository.

## License

This configuration is part of the [hass-bambulab-config](https://github.com/rsocko/hass-bambulab-config) repository and follows the same license.

## Version History

- **v1.0.0** (2026-02-17) - Initial release
  - Support for 2 AMS units
  - Optional room sensor
  - Color-coded status indicators
