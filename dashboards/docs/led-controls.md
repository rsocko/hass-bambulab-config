# LED Controls Dashboard Card

## Overview

This document describes the LED Controls dashboard card that provides a centralized interface for controlling and monitoring all LED lights associated with the Bambu Lab 3D printer setup, including WLED-controlled RGBIC strips and the built-in chamber light.

## Features

### 💡 LED Control Grid

A 2-column grid layout displaying all 7 LED light entities:

1. **Interior Top Light (MagWLED)** - WLED RGBIC
   - Full color control with effects and palettes
   - Preset quick-access buttons
   - Effect speed and intensity controls

2. **Chamber Light** - Built-in printer light
   - Simple on/off and brightness control
   - Visual indicator when on (warm amber glow)

3. **AMS 1 Tray Light (DigQuad)** - WLED RGBIC
   - Illuminates spools in AMS 1
   - Full WLED effect control
   - Color matching for active spool indication

4. **AMS 1 Tag LEDs (DigQuad)** - WLED RGBIC
   - Filament tag illumination
   - Individual segment control capability
   - Desiccant warning and status indication

5. **AMS 2 Tray Light (DigQuad)** - WLED RGBIC
   - Illuminates spools in AMS 2
   - Full WLED effect control
   - Active spool indication

6. **AMS 2 Tag LEDs (DigQuad)** - WLED RGBIC
   - Filament tag illumination
   - Individual segment control capability
   - Humidity and status indicators

7. **Front Display LED (DigQuad)** - WLED RGBIC
   - C-shaped door LED strip
   - Print progress bar (bottom segment)
   - Status indicators (left/top segments)

### 🎮 Interactive Controls

Each LED card features:

- **Tap Action**: Toggle light on/off
- **Hold Action**: Open standard more-info dialog
- **Double-Tap Action**: Open custom popup with advanced controls (WLED lights only)

### 🔧 Advanced WLED Popups

For WLED-controlled lights, double-tap opens a detailed popup with:

- **Power Control**: Turn light on/off
- **Effect Selection**: Choose from WLED effects
- **Color Palette**: Select preset color palettes
- **Speed Control**: Adjust animation speed
- **Intensity Control**: Adjust effect intensity
- **Color & Brightness**: Standard light controls
- **Preset Quick Access**: Quick buttons for presets (MagWLED only)

### ⚡ Quick Actions

Two quick-action buttons at the bottom:

1. **All On** - Turns on all 7 lights simultaneously
   - Warm amber background indicator
   - Icon: `mdi:lightbulb-group`

2. **All Off** - Turns off all 7 lights simultaneously
   - Gray background indicator
   - Icon: `mdi:lightbulb-group-off`

### 📊 Status Overview

Real-time status card showing:

- **Primary**: Count of lights currently on (e.g., "3 of 7 lights on")
- **Secondary**: List of which lights are on (e.g., "Interior, AMS1 Tray, Front")
- **Icon Color**: Visual indicator
  - 🔴 Disabled: All lights off
  - 🔵 Blue: 1-3 lights on
  - 🟠 Amber: 4-6 lights on
  - 🟢 Green: All 7 lights on

## Setup Instructions

### 1. Prerequisites

- Home Assistant with the following integrations:
  - **WLED Integration** - For DigQuad and MagWLED controllers
  - **Bambu Lab Integration** - For chamber light control
  - **Custom Cards** (via HACS):
    - `mushroom-cards` - Modern UI cards
    - `button-card` - Advanced button functionality
    - `browser-mod` - Popup dialogs
    - `card-mod` - Custom styling

### 2. Entity ID Mapping

Replace the placeholder entity IDs in `led-controls.yaml` with your actual entity IDs:

| Placeholder | Description | Example Actual Entity |
|-------------|-------------|----------------------|
| `light.magwled_internal_top_light` | MagWLED interior light | `light.wled_magwled` |
| `light.bambu_chamber_light` | Built-in chamber light | `light.p1s_01p00c460102350_chamber_light` |
| `light.digquad_ams1_tray_light` | AMS 1 tray lighting | `light.wled_digquad_segment_3` |
| `light.digquad_ams1_tag_light` | AMS 1 tag LEDs | `light.wled_digquad_segment_11` |
| `light.digquad_ams2_tray_light` | AMS 2 tray lighting | `light.wled_digquad_segment_7` |
| `light.digquad_ams2_tag_light` | AMS 2 tag LEDs | `light.wled_digquad_segment_15` |
| `light.digquad_front_led` | Front door LED strip | `light.wled_digquad_segment_1` |

### 3. WLED Entity Types

For each WLED light, you'll also need to update the related entities:

- **Effect**: `select.{light_name}_effect`
- **Palette**: `select.{light_name}_palette`
- **Speed**: `number.{light_name}_speed`
- **Intensity**: `number.{light_name}_intensity`
- **Preset**: `select.{light_name}_preset`

**Example:**
If your interior light entity is `light.wled_magwled`, the related entities would be:
- `select.wled_magwled_effect`
- `select.wled_magwled_palette`
- `number.wled_magwled_speed`
- `number.wled_magwled_intensity`
- `select.wled_magwled_preset`

### 4. Installation Steps

1. **Copy the configuration file:**
   ```bash
   cp dashboards/led-controls.yaml /config/dashboards/
   ```

2. **Edit entity IDs:**
   - Open `led-controls.yaml` in your text editor
   - Find and replace all placeholder entity IDs with your actual entity IDs
   - Update WLED-related entities (effects, palettes, etc.)

3. **Add to your dashboard:**
   - Open your Home Assistant dashboard in edit mode
   - Add a new card
   - Select "Manual" card type
   - Copy the entire contents of `led-controls.yaml`
   - Paste into the card YAML editor
   - Save

4. **Test functionality:**
   - Test each light's toggle function
   - Verify double-tap popups work for WLED lights
   - Test quick-action buttons (All On/All Off)
   - Verify status overview updates correctly

## Customization

### Changing Grid Layout

To change from 2 columns to 3 columns:

```yaml
- type: grid
  columns: 3  # Change from 2 to 3
  square: false
  cards:
```

### Adding Custom Presets

To add more preset buttons in the MagWLED popup:

```yaml
- type: custom:mushroom-template-card
  primary: "Preset 4"
  icon: mdi:numeric-4-circle
  tap_action:
    action: call-service
    service: select.select_option
    service_data:
      option: "4"
    target:
      entity_id: select.magwled_internal_top_light_preset
```

### Modifying Colors

To change the card background colors, edit the `card_mod` sections:

```yaml
card_mod:
  style: |
    ha-card {
      background: rgba(255, 183, 77, 0.1);  # Adjust RGBA values
    }
```

### Removing Lights

If you don't have all 7 lights:

1. Remove the corresponding card from the grid
2. Remove the entity from the "All On" and "All Off" quick actions
3. Update the status overview to reflect the correct number of lights

## WLED Configuration Reference

### Segment Mapping

Based on the WLED configuration documented in `/wled/README.md`:

| LED Zone | GPIO Pin | LED Range | Segments |
|----------|----------|-----------|----------|
| Front Door | 15 | 0-157 | Bottom (0-49), Left (50-114), Top (115-157) |
| AMS 1 Tray | 1 | 158-297 | 4 tray segments or top/bottom split |
| AMS 2 Tray | 3 | 298-436 | 4 tray segments or top/bottom split |
| AMS 1 Tags | 16 | 437-572 | Individual tag segments + hygrometer |
| AMS 2 Tags | 4 | 573-710 | Individual tag segments + hygrometer |

### Recommended Effects

For different use cases:

**During Printing:**
- Front Door: Progress bar + status pulse
- Active Tray: Filament color solid
- Active Tag: Filament color bright

**Idle Mode:**
- All: Soft white breathing
- Brightness: 20-30%

**Show Mode:**
- All: Rainbow or colorful effects
- Tags: Color matching filament

**Error State:**
- Affected zones: Red strobe/pulse
- Other zones: Dim or off

## Troubleshooting

### Lights Not Responding

1. **Check entity availability:**
   - Go to Developer Tools → States
   - Search for your light entities
   - Verify they show "on" or "off" (not "unavailable")

2. **Verify WLED integration:**
   - Settings → Devices & Services → WLED
   - Ensure WLED devices are connected
   - Check IP addresses are correct

3. **Test manually:**
   - Go to Developer Tools → Services
   - Call `light.turn_on` with your entity ID
   - If this fails, the issue is with the integration, not the card

### Popups Not Working

1. **Verify browser-mod is installed:**
   - HACS → Frontend → Search "browser-mod"
   - Install if missing

2. **Check browser-mod service:**
   - Developer Tools → Services
   - Search for `browser_mod.popup`
   - Should appear in the list

3. **Clear browser cache:**
   - Hard refresh: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)

### WLED Effects Not Showing

1. **Update entity IDs:**
   - Verify `select.{light_name}_effect` entities exist
   - Check in Developer Tools → States

2. **WLED integration version:**
   - Ensure you have the latest WLED integration
   - Some older versions don't expose all entities

## Advanced Features

### Automation Integration

You can trigger these lights based on printer state:

```yaml
automation:
  - alias: "Printer Started - Set Lights"
    trigger:
      - platform: state
        entity_id: sensor.p1s_print_status
        to: "printing"
    action:
      - service: light.turn_on
        target:
          entity_id: light.digquad_front_led
        data:
          effect: "Progress Bar"
```

### Conditional Display

Show/hide lights based on conditions:

```yaml
type: conditional
conditions:
  - entity: sensor.p1s_print_status
    state: "printing"
card:
  # Your LED control card here
```

### Voice Control

These lights will automatically appear in voice assistants:

- "Hey Google, turn on the chamber light"
- "Alexa, set AMS 1 tray light to blue"
- "Hey Google, turn off all printer lights"

## Related Documentation

- **WLED Setup**: `/wled/README.md` - Complete WLED configuration guide
- **LED Segments**: `/wled/digquad-led-segments.md` - Detailed segment specifications
- **Light Scenarios**: `/wled/light-scenarios.md` - 33+ lighting scenario catalog
- **Automations**: `/wled/docs/home-assistant-automations.md` - Example automations

## Support

For issues or questions:

- **Repository**: https://github.com/rsocko/hass-bambulab-config/issues
- **WLED Documentation**: https://kno.wled.ge/
- **Home Assistant WLED**: https://www.home-assistant.io/integrations/wled/
- **Mushroom Cards**: https://github.com/piitaya/lovelace-mushroom

## Version History

### v1.0.0 (Initial Release)
- 7 LED light controls with grid layout
- WLED advanced popups with effect/palette controls
- Quick action buttons (All On/All Off)
- Status overview with dynamic counting
- Comprehensive documentation

## License

This configuration is part of the hass-bambulab-config repository and follows the same license terms.
