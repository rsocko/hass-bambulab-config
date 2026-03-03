# Humidity Card Quick Start

Copy and paste this minimal configuration into your Home Assistant dashboard.

## Minimal Configuration (Copy & Paste)

```yaml
type: horizontal-stack
cards:
  - type: custom:mushroom-template-card
    primary: AMS 1
    secondary: |-
      {% set humidity = states('sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_humidity') | float(-1) %}
      {% set temp = states('sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_temperature') | float(-1) %}
      {% if humidity >= 0 %}
        {{ humidity | round(1) }}% · {{ temp | round(1) }}°C
      {% else %}
        N/A
      {% endif %}
    icon: mdi:package-variant
    icon_color: |-
      {% set humidity = states('sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_humidity') | float(-1) %}
      {% if humidity < 0 %}
        grey
      {% elif humidity < 20 %}
        green
      {% elif humidity < 40 %}
        light-green
      {% elif humidity < 60 %}
        amber
      {% elif humidity < 70 %}
        orange
      {% else %}
        red
      {% endif %}
    tap_action:
      action: more-info
      entity: sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_humidity

  - type: custom:mushroom-template-card
    primary: AMS 2
    secondary: |-
      {% set humidity = states('sensor.3d_printer_ams_2_humidity_and_temp_humidity') | float(-1) %}
      {% set temp = states('sensor.3d_printer_ams_2_humidity_and_temp_temperature') | float(-1) %}
      {% if humidity >= 0 %}
        {{ humidity | round(1) }}% · {{ temp | round(1) }}°C
      {% else %}
        N/A
      {% endif %}
    icon: mdi:package-variant-closed
    icon_color: |-
      {% set humidity = states('sensor.3d_printer_ams_2_humidity_and_temp_humidity') | float(-1) %}
      {% if humidity < 0 %}
        grey
      {% elif humidity < 20 %}
        green
      {% elif humidity < 40 %}
        light-green
      {% elif humidity < 60 %}
        amber
      {% elif humidity < 70 %}
        orange
      {% else %}
        red
      {% endif %}
    tap_action:
      action: more-info
      entity: sensor.3d_printer_ams_2_humidity_and_temp_humidity
```

## What You Need

1. **Custom Cards** (via HACS):
   - mushroom
   - card-mod (optional, for styling)

2. **Sensors** (from Bambu Lab integration):
   - `sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_humidity`
   - `sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_temperature`
   - `sensor.3d_printer_ams_2_humidity_and_temp_humidity`
   - `sensor.3d_printer_ams_2_humidity_and_temp_temperature`

## Installation

1. Install **mushroom** via HACS
2. Copy the YAML above
3. Edit your dashboard
4. Add card → Manual
5. Paste the YAML
6. Update entity names if different
7. Save

## Color Guide

- **Green** (< 20%): Optimal for all filaments
- **Light Green** (20-40%): Good for most filaments
- **Amber** (40-60%): Monitor hygroscopic filaments
- **Orange** (60-70%): Replace desiccant soon
- **Red** (> 70%): Critical - replace desiccant now

## Customization

### Add Your Entity Names

Replace `ntk_ryansoffice_3dprinter` with your printer name.

### Change to Fahrenheit

Replace `{{ temp | round(1) }}°C` with:
```yaml
{{ ((temp * 9/5) + 32) | round(1) }}°F
```

### Add Room Sensor

Add before the AMS cards:
```yaml
- type: custom:mushroom-template-card
  primary: Room
  secondary: "{{ states('sensor.room_humidity') | round(1) }}%"
  icon: mdi:home-thermometer-outline
  icon_color: |-
    {% set h = states('sensor.room_humidity') | float(-1) %}
    {% if h < 30 %}red
    {% elif h < 40 %}orange
    {% elif h < 60 %}green
    {% elif h < 70 %}amber
    {% else %}red
    {% endif %}
  tap_action:
    action: more-info
    entity: sensor.room_humidity
```

## Need More?

See [README.md](README.md) for:
- Complete documentation
- Advanced features
- Automation examples
- Troubleshooting guide

## Quick Links

- [Full Card Configuration](../../../homeassistant/packages/3d_printing/humidity/dashboard_cards/humidity-card.yaml)
- [Visual Guide](docs/visual-guide.md)
- [Bambu Lab Integration](https://github.com/greghesp/ha-bambulab)
