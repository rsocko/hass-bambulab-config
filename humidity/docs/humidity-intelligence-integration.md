# Integration with Humidity Intelligence Package

This guide shows how to integrate the basic humidity card with the [humidity-intelligence](https://github.com/senyo888/humidity-intelligence) package for advanced analysis.

## Prerequisites

1. Basic humidity card installed (from this repository)
2. humidity-intelligence package installed via HACS
3. Bambu Lab integration configured with AMS sensors

## Installation Steps

### 1. Install Humidity-Intelligence via HACS

1. Open **HACS** in Home Assistant
2. Go to **Integrations**
3. Click **⋮ → Custom repositories**
4. Add repository:
   - **URL:** `https://github.com/senyo888/humidity-intelligence`
   - **Category:** Template
5. Click **Install**
6. Restart Home Assistant

### 2. Enable Packages in configuration.yaml

Add to your `configuration.yaml` (if not already present):

```yaml
homeassistant:
  packages: !include_dir_named packages
```

### 3. Create Package Configuration

Create file: `/config/packages/humidity_intelligence.yaml`

Include the humidity-intelligence package:

```yaml
# Option B: Include (recommended - gets updates automatically)
packages:
  humidity_intelligence: !include jinja/humidity_intelligence.jinja
```

Or copy the content manually (Option A - full control).

### 4. Configure Your Sensors

Edit `/config/packages/humidity_intelligence.yaml` to map your sensors:

```yaml
# In the humidity-intelligence config section, update the room map:

# Room map for humidity sensors
template:
  - sensor:
      - name: "Humidity Intelligence Config"
        state: "configured"
        attributes:
          room_map:
            'Printer Room': 'sensor.room_humidity'  # Your room sensor (optional)
            'AMS 1': 'sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_humidity'
            'AMS 2': 'sensor.3d_printer_ams_2_humidity_and_temp_humidity'
```

### 5. Configure Temperature Sensors for Dew Point Calculation

For advanced features like dew point and condensation risk:

```yaml
# Map temperature sensors for each room/AMS
template:
  - sensor:
      # AMS 1 Dew Point
      - name: "AMS 1 Dew Point"
        unit_of_measurement: "°C"
        state: >
          {% set T = states('sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_temperature') | float %}
          {% set RH = states('sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_humidity') | float %}
          {% if T and RH %}
            {{ ((T - ((100 - RH) / 5)) | round(1)) }}
          {% else %}
            unavailable
          {% endif %}
      
      # AMS 2 Dew Point
      - name: "AMS 2 Dew Point"
        unit_of_measurement: "°C"
        state: >
          {% set T = states('sensor.3d_printer_ams_2_humidity_and_temp_temperature') | float %}
          {% set RH = states('sensor.3d_printer_ams_2_humidity_and_temp_humidity') | float %}
          {% if T and RH %}
            {{ ((T - ((100 - RH) / 5)) | round(1)) }}
          {% else %}
            unavailable
          {% endif %}
```

### 6. Restart Home Assistant

After configuration, restart Home Assistant to load the new sensors.

## Available Sensors After Integration

Once configured, you'll have access to these sensors:

### House-Level Sensors
- `sensor.house_average_humidity` - Average humidity across all mapped rooms
- `sensor.house_humidity_mean_7d` - 7-day historical mean
- `sensor.house_humidity_drift_7d` - Drift from 7-day average

### Risk Assessment Sensors
- `sensor.worst_room_condensation` - Room with highest condensation risk
- `sensor.worst_room_condensation_risk` - Risk level (OK/Watch/Risk/Danger)
- `sensor.worst_room_mould` - Room with highest mould risk
- `sensor.worst_room_mould_risk` - Mould risk level

### Binary Alert Sensors (for Automations)
- `binary_sensor.humidity_danger` - Overall humidity danger flag
- `binary_sensor.condensation_danger` - Condensation risk flag
- `binary_sensor.mould_danger` - Mould risk flag

### Constellation Chart Data
- `sensor.humidity_constellation_series` - ApexCharts-ready data for visualization

## Enhanced Dashboard Cards

### Add House Average Humidity Card

```yaml
type: custom:mushroom-template-card
primary: House Average
secondary: "{{ states('sensor.house_average_humidity') | round(1) }}%"
icon: mdi:home-analytics
icon_color: |-
  {% set h = states('sensor.house_average_humidity') | float(0) %}
  {% if h < 30 %}red
  {% elif h < 40 %}orange
  {% elif h < 60 %}green
  {% elif h < 70 %}amber
  {% else %}red
  {% endif %}
tap_action:
  action: more-info
  entity: sensor.house_average_humidity
```

### Add Risk Alert Cards

```yaml
type: horizontal-stack
cards:
  # Condensation Risk
  - type: custom:mushroom-template-card
    primary: Condensation
    secondary: "{{ states('sensor.worst_room_condensation_risk') }}"
    icon: mdi:water-alert
    icon_color: |-
      {% set risk = states('sensor.worst_room_condensation_risk') %}
      {% if risk == 'OK' %}green
      {% elif risk == 'Watch' %}amber
      {% elif risk == 'Risk' %}orange
      {% else %}red
      {% endif %}
    tap_action:
      action: more-info
      entity: binary_sensor.condensation_danger
  
  # Mould Risk
  - type: custom:mushroom-template-card
    primary: Mould
    secondary: "{{ states('sensor.worst_room_mould_risk') }}"
    icon: mdi:biohazard
    icon_color: |-
      {% set risk = states('sensor.worst_room_mould_risk') %}
      {% if risk == 'OK' %}green
      {% elif risk == 'Watch' %}amber
      {% elif risk == 'Risk' %}orange
      {% else %}red
      {% endif %}
    tap_action:
      action: more-info
      entity: binary_sensor.mould_danger
```

### Add 7-Day Drift Card

```yaml
type: custom:mushroom-template-card
primary: Humidity Drift (7d)
secondary: |-
  {% set drift = states('sensor.house_humidity_drift_7d') | float(0) %}
  {% if drift > 0 %}+{% endif %}{{ drift | round(1) }}%
icon: mdi:chart-line-variant
icon_color: |-
  {% set drift = states('sensor.house_humidity_drift_7d') | float(0) | abs %}
  {% if drift < 5 %}green
  {% elif drift < 10 %}amber
  {% else %}red
  {% endif %}
tap_action:
  action: more-info
  entity: sensor.house_humidity_drift_7d
```

### Add Humidity Constellation Chart

Requires: `apexcharts-card` via HACS

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: "Humidity Constellation (24h)"
series:
  - entity: sensor.humidity_constellation_series
    type: line
    stroke_width: 2
    data_generator: |
      return JSON.parse(entity.state).map(point => {
        return [new Date(point.time).getTime(), point.humidity];
      });
apex_config:
  chart:
    height: 250
  xaxis:
    type: datetime
  yaxis:
    min: 0
    max: 100
    title:
      text: "Humidity %"
```

## Automation Examples

### Alert on Any Humidity Danger

```yaml
automation:
  - alias: "Humidity Danger Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.humidity_danger
        to: 'on'
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ Humidity Danger"
          message: >
            House average: {{ states('sensor.house_average_humidity') }}%
            Worst room: {{ states('sensor.worst_room_condensation') }}
          data:
            actions:
              - action: "VIEW_HUMIDITY"
                title: "View Details"
```

### Alert on Condensation Risk

```yaml
automation:
  - alias: "Condensation Risk Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.condensation_danger
        to: 'on'
    action:
      - service: notify.persistent_notification
        data:
          title: "Condensation Risk Detected"
          message: >
            {{ states('sensor.worst_room_condensation') }} is at {{ states('sensor.worst_room_condensation_risk') }} risk.
            Consider increasing ventilation or using a dehumidifier.
```

### Track AMS Humidity Trends

```yaml
automation:
  - alias: "AMS Humidity Rising Alert"
    trigger:
      - platform: template
        value_template: >
          {{ 
            (states('sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_humidity') | float(0)) -
            (state_attr('sensor.ams_1_humidity_mean_7d', 'mean') | float(0)) > 10
          }}
    action:
      - service: notify.mobile_app
        data:
          title: "AMS 1 Humidity Rising"
          message: >
            Current: {{ states('sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_humidity') }}%
            7-day avg: {{ state_attr('sensor.ams_1_humidity_mean_7d', 'mean') | round(1) }}%
            Consider checking or replacing desiccant pack.
```

### Auto-Enable Dehumidifier

```yaml
automation:
  - alias: "Auto Enable Dehumidifier"
    trigger:
      - platform: numeric_state
        entity_id: sensor.house_average_humidity
        above: 60
        for:
          minutes: 30
    condition:
      - condition: state
        entity_id: binary_sensor.humidity_danger
        state: 'on'
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.dehumidifier
      - service: notify.mobile_app
        data:
          title: "Dehumidifier Activated"
          message: "House humidity is {{ states('sensor.house_average_humidity') }}% - dehumidifier started"
```

## Complete Dashboard Example

Combining basic humidity card with advanced features:

```yaml
type: vertical-stack
cards:
  # Basic AMS Humidity Cards (from this repo)
  - type: horizontal-stack
    cards:
      - type: custom:mushroom-template-card
        primary: AMS 1
        secondary: "{{ states('sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_humidity') }}% · {{ states('sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_temperature') }}°C"
        icon: mdi:package-variant
        icon_color: >-
          {% set h = states('sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_humidity')|float(0) %}
          {% if h < 20 %}green{% elif h < 40 %}light-green{% elif h < 60 %}amber{% elif h < 70 %}orange{% else %}red{% endif %}
        tap_action:
          action: more-info
          entity: sensor.ntk_ryansoffice_3dprinterams1_humidity_temperature_humidity
      
      - type: custom:mushroom-template-card
        primary: AMS 2
        secondary: "{{ states('sensor.3d_printer_ams_2_humidity_and_temp_humidity') }}% · {{ states('sensor.3d_printer_ams_2_humidity_and_temp_temperature') }}°C"
        icon: mdi:package-variant-closed
        icon_color: >-
          {% set h = states('sensor.3d_printer_ams_2_humidity_and_temp_humidity')|float(0) %}
          {% if h < 20 %}green{% elif h < 40 %}light-green{% elif h < 60 %}amber{% elif h < 70 %}orange{% else %}red{% endif %}
        tap_action:
          action: more-info
          entity: sensor.3d_printer_ams_2_humidity_and_temp_humidity
  
  # House Average (from humidity-intelligence)
  - type: custom:mushroom-template-card
    primary: House Average
    secondary: "{{ states('sensor.house_average_humidity') | round(1) }}% (7d drift: {{ states('sensor.house_humidity_drift_7d') }}%)"
    icon: mdi:home-analytics
    icon_color: >-
      {% set h = states('sensor.house_average_humidity')|float(0) %}
      {% if h < 30 %}red{% elif h < 40 %}orange{% elif h < 60 %}green{% elif h < 70 %}amber{% else %}red{% endif %}
    tap_action:
      action: more-info
      entity: sensor.house_average_humidity
  
  # Risk Indicators (from humidity-intelligence)
  - type: horizontal-stack
    cards:
      - type: custom:mushroom-template-card
        primary: Condensation
        secondary: "{{ states('sensor.worst_room_condensation_risk') }}"
        icon: mdi:water-alert
        icon_color: >-
          {% set risk = states('sensor.worst_room_condensation_risk') %}
          {% if risk == 'OK' %}green{% elif risk == 'Watch' %}amber{% elif risk == 'Risk' %}orange{% else %}red{% endif %}
        tap_action:
          action: more-info
          entity: binary_sensor.condensation_danger
      
      - type: custom:mushroom-template-card
        primary: Mould
        secondary: "{{ states('sensor.worst_room_mould_risk') }}"
        icon: mdi:biohazard
        icon_color: >-
          {% set risk = states('sensor.worst_room_mould_risk') %}
          {% if risk == 'OK' %}green{% elif risk == 'Watch' %}amber{% elif risk == 'Risk' %}orange{% else %}red{% endif %}
        tap_action:
          action: more-info
          entity: binary_sensor.mould_danger
  
  # Optional: Humidity Constellation Chart
  # Requires apexcharts-card via HACS
  # - type: custom:apexcharts-card
  #   header:
  #     show: true
  #     title: "24h Humidity Trends"
  #   series:
  #     - entity: sensor.humidity_constellation_series
  #       # ... chart config
```

## Troubleshooting Integration

### Sensors Not Appearing

1. Verify humidity-intelligence package is loaded:
   ```bash
   grep -r "humidity_intelligence" /config/packages/
   ```

2. Check for errors in Home Assistant logs:
   ```
   Settings → System → Logs
   Search for: "humidity_intelligence"
   ```

3. Verify sensor mapping in configuration:
   ```yaml
   # Check Developer Tools → Template
   {{ states.sensor.humidity_intelligence_config.attributes.room_map }}
   ```

### Incorrect Values

1. Verify sensor entity IDs are correct
2. Check sensor states in Developer Tools → States
3. Ensure sensors are providing numeric values (not "unavailable" or "unknown")

### Package Updates Overwriting Changes

If using Option B (Include), changes may be reset on HACS updates. Either:
- Switch to Option A (Copy) for full control
- Store custom configuration separately and reference it

## Additional Resources

- [Humidity-Intelligence Documentation](https://github.com/senyo888/humidity-intelligence)
- [ApexCharts Card](https://github.com/RomRider/apexcharts-card)
- [Home Assistant Packages](https://www.home-assistant.io/docs/configuration/packages/)
- [Template Sensors](https://www.home-assistant.io/integrations/template/)

## Support

For issues specific to:
- **Basic humidity card**: Open an issue in [hass-bambulab-config](https://github.com/rsocko/hass-bambulab-config)
- **Humidity-intelligence package**: Open an issue in [humidity-intelligence](https://github.com/senyo888/humidity-intelligence)
