# Fan Controls Dashboard Card

This document explains the fan control cards for monitoring and controlling printer fans and the ESP32 bento box fan.

## Overview

The fan controls provide a compact, informational dashboard for monitoring:
- **3 Bambu Lab printer fans**: Auxiliary, Chamber, and Cooling fans
- **1 ESP32 Bento Box fan**: External enclosure/storage fan

These cards are designed to:
- Take up 1 section width when arranged horizontally
- Look good on both desktop and mobile devices
- Use color-coded icons for quick status recognition
- Provide click/tap actions for more details or control

## Features

### Visual Design
- **Compact Layout**: Horizontal stack of 4 fan cards
- **Color Coding**: Icons change color based on fan speed
  - Grey: Fan off (0%)
  - Blue/Green: Low speed (< 30%)
  - Amber/Cyan: Medium speed (30-70%)
  - Red/Orange: High speed (> 70%)
- **Hover Effects**: Subtle background color change on hover
- **Mobile Responsive**: Cards automatically adapt to screen size

### Fan Information Display

#### Auxiliary Fan
- **Purpose**: High-power cooling for better print quality and faster cooling
- **Icon**: `mdi:fan`
- **Entity**: `sensor.ntk_ryansoffice_3dprinter_aux_fan_speed`
- **Background Color**: Blue tint (rgba(33, 150, 243, 0.05))

#### Chamber Fan
- **Purpose**: Circulates air within printer chamber for temperature control
- **Icon**: `mdi:fan-chevron-up`
- **Entity**: `sensor.ntk_ryansoffice_3dprinter_chamber_fan_speed`
- **Background Color**: Purple tint (rgba(156, 39, 176, 0.05))

#### Cooling Fan
- **Purpose**: Main part cooling fan for layer cooling during printing
- **Icon**: `mdi:snowflake`
- **Entity**: `sensor.ntk_ryansoffice_3dprinter_cooling_fan_speed`
- **Background Color**: Cyan tint (rgba(0, 188, 212, 0.05))

#### Bento Box Fan (ESP32)
- **Purpose**: External enclosure/storage fan for filament storage area
- **Icon**: `mdi:fan-auto`
- **Entity**: `fan.bento_box_fan`
- **Background Color**: Green tint (rgba(76, 175, 80, 0.05))
- **Special Feature**: Tap to toggle on/off (unlike read-only sensor entities)

## Installation

### Prerequisites

Install these custom cards via HACS:
1. **mushroom** - For the template cards
2. **card-mod** - For custom styling

### Setup Steps

1. **Update Entity Names**
   
   Replace the placeholder entity names with your actual entities:
   
   **For Bambu Lab Printer:**
   ```yaml
   # Replace 'ntk_ryansoffice_3dprinter' with your printer name
   sensor.YOUR_PRINTER_NAME_aux_fan_speed
   sensor.YOUR_PRINTER_NAME_chamber_fan_speed
   sensor.YOUR_PRINTER_NAME_cooling_fan_speed
   ```
   
   **For ESP32 Bento Box:**
   ```yaml
   # Replace 'bento_box_fan' with your actual fan entity
   fan.your_esp32_fan_entity_name
   ```

2. **Use Canonical Configuration**
   
  Canonical card file:
  `/homeassistant/packages/3d_printing/printer_controls/dashboard_cards/fan_controls_v2.yaml`

  Packaged dashboard include (already wired in `view_main.yaml`):
  `!include ../../printer_controls/dashboard_cards/fan_controls_v2.yaml`

3. **Add to Dashboard**
   
   - Open your Home Assistant dashboard in edit mode
   - Add a new card
   - Choose "Manual" or "Show Code Editor"
   - Paste the copied configuration
   - Save the dashboard

## Usage

### Desktop View
- All 4 fans display in a single horizontal row
- Hover over cards for subtle highlight effect
- Click any card to view more details

### Mobile View
- Cards automatically stack or adjust based on screen width
- Tap cards for more information
- Tap Bento Box fan card to toggle on/off

### Tap Actions

**Bambu Lab Fans (Sensor Entities):**
- **Single Tap**: Opens more-info dialog with historical data
- **Hold/Long Press**: Opens more-info dialog

**Bento Box Fan (Fan Entity):**
- **Single Tap**: Toggles fan on/off
- **Hold/Long Press**: Opens more-info dialog with speed controls

## Alternative Layouts

If the horizontal layout is too compact for your needs, you can use a grid layout instead:

```yaml
type: grid
columns: 2  # Use 2 columns for mobile-friendly layout
square: false
cards:
  - [Aux Fan card configuration]
  - [Chamber Fan card configuration]
  - [Cooling Fan card configuration]
  - [Bento Box Fan card configuration]
```

This creates a 2x2 grid that works better on mobile devices.

2. **Use Canonical Configuration**
   
  Use `/homeassistant/packages/3d_printing/printer_controls/dashboard_cards/fan_controls_v2.yaml` as the canonical fan controls card.

  If you are using the packaged dashboard view, this card is already included from:
  `/homeassistant/packages/3d_printing/common/dashboard_views/view_main.yaml`
  via:
  `!include ../../printer_controls/dashboard_cards/fan_controls_v2.yaml`

### Changing Colors

Modify the `icon_color` section to adjust when colors change:

```yaml
icon_color: |-
  {% set speed = states('sensor.YOUR_ENTITY') | int(0) %}
  {% if speed == 0 %}
    grey        # Off
  {% elif speed < 30 %}
    blue        # Low
  {% elif speed < 70 %}
    amber       # Medium
  {% else %}
    red         # High
  {% endif %}
```

### Changing Background Colors

Adjust the `card_mod` style section:

```yaml
card_mod:
  style: |
    ha-card {
      background: rgba(33, 150, 243, 0.05);  # Normal state
    }
    ha-card:hover {
      background: rgba(33, 150, 243, 0.1);   # Hover state
    }
```

### Changing Icons

Available fan-related icons:
- `mdi:fan` - Standard fan
- `mdi:fan-alert` - Fan with alert
- `mdi:fan-auto` - Auto/smart fan
- `mdi:fan-chevron-down` - Downward flow
- `mdi:fan-chevron-up` - Upward flow
- `mdi:fan-off` - Fan off indicator
- `mdi:fan-plus` - Fan with plus
- `mdi:fan-remove` - Fan with minus
- `mdi:fan-speed-1` / `2` / `3` - Speed indicators
- `mdi:snowflake` - Cooling/cold
- `mdi:air-filter` - Air filtration

See [Material Design Icons](https://pictogrammers.com/library/mdi/) for the complete list.

### Adding Fan Control Actions

If you have fan control entities (not just sensors), you can add control actions:

```yaml
tap_action:
  action: call-service
  service: fan.set_percentage
  service_data:
    entity_id: fan.YOUR_FAN_ENTITY
    percentage: 50
```

Or use a more-info popup with controls:

```yaml
tap_action:
  action: more-info
  entity: fan.YOUR_FAN_ENTITY  # Fan entity (not sensor)
```

## Troubleshooting

### Cards Not Appearing
1. Verify mushroom and card-mod are installed via HACS
2. Clear browser cache and hard reload (Ctrl+Shift+R)
3. Check browser console for errors

### Entity Not Found
1. Verify entity names match your actual entities
2. Check Developer Tools > States to find correct entity names
3. Update entity names in the configuration

### Fan Speed Shows "unknown" or "unavailable"
1. Check that your Bambu Lab integration is connected
2. Verify printer is powered on and connected to network
3. For ESP32 fan, check ESPHome device is online

### Colors Not Showing
1. Verify card-mod is installed
2. Check that the style section is properly indented
3. Try clearing browser cache

### Mobile Layout Issues
1. Consider using grid layout with `columns: 2` instead of horizontal-stack
2. Adjust card sizing in the grid configuration
3. Test on actual mobile device, not just browser resize

## Technical Details

### Entity Types

**Bambu Lab Fans (Sensors)**
- Type: `sensor.*`
- State: Percentage (0-100)
- Attributes: Various depending on integration version
- Read-only: Display only, control via printer interface

**ESP32 Fan (Fan Entity)**
- Type: `fan.*`
- State: `on` / `off`
- Attributes: `percentage` (speed), `preset_mode`, etc.
- Controllable: Can toggle and set speed

### Card Dependencies

The cards use:
- `custom:mushroom-template-card` - Base card type
- Jinja2 templates - For dynamic content
- CSS via card_mod - For styling

## Related Documentation

- [Dashboard README](../README.md) - Main dashboard documentation
- [Top Bar Layout](top-bar-layout.md) - Top bar customization
- [Bambu Lab Integration](https://github.com/greghesp/ha-bambulab) - Integration documentation
- [ESPHome Fan Component](https://esphome.io/components/fan/) - ESP32 fan setup

## Contributing

When making changes to the fan controls:
1. Test on both desktop and mobile
2. Verify all entity names are placeholders or documented
3. Update this documentation if adding features
4. Maintain consistent styling with other dashboard cards

