# Printer Temperature Display Cards

## Overview

These cards display the current and target temperatures for your Bambu Lab 3D printer's nozzle (extruder) and bed in a visually appealing, color-coded format.

## Features

- **Visual Temperature Display**: Shows both current (large, prominent) and target (small, next to icon) temperatures
- **Color-Coded States** (only when actively printing):
  - 🔴 **Red**: Heating up (target temperature is higher than current)
  - 🔵 **Blue**: Cooling down (target temperature is lower than current)
  - ⚪ **Grey**: At target (temperatures match within 2°C tolerance) or printer is idle
- **Fixed Icons**: Clear, consistent iconography
  - `mdi:printer-3d-nozzle-heat` for nozzle temperature (3D printer nozzle heater icon)
  - `mdi:radiator` for bed temperature (always)
- **Smart Heating Indicator**: Target temp styling changes based on heating state
  - **Bold & prominent** (font-weight: 700, opacity: 0.9) when target > 0°C (heater is on)
  - **Normal & subtle** (font-weight: 500, opacity: 0.7) when target = 0°C (heater is off)
- **Intelligent State Detection**: Color indicators active when printer status is not `idle`
- **Horizontal Layout**: Compact design that works well on mobile and desktop
- **Interactive**: Click any card to see detailed entity information

## Screenshot Reference

Based on the built-in HA Bambu Lab status card design:

```
┌─────────────────┐
│ 🌡️  0°C         │  ← Icon + Target Temp (small)
│                 │
│     25°C        │  ← Current Temp (large, prominent)
└─────────────────┘
```

**Note**: Icons are now fixed (thermometer for nozzle, radiator for bed) rather than changing based on state. Color coding indicates heating/cooling when printer is active.

## Installation

### Prerequisites

1. **Custom Cards** (install via HACS):
   - [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom) (required)
   - [card-mod](https://github.com/thomasloven/lovelace-card-mod) (required for styling)

2. **Bambu Lab Integration** with temperature sensors:
   - `sensor.YOUR_PRINTER_NAME_nozzle_temperature`
  - `sensor.YOUR_PRINTER_NAME_nozzle_target_temperature`
   - `sensor.YOUR_PRINTER_NAME_bed_temperature`
  - `sensor.YOUR_PRINTER_NAME_bed_target_temperature`
   - `sensor.YOUR_PRINTER_NAME_print_status` (required for idle state detection)

### Setup Steps

1. **Find Your Printer Entity Name**:
   - Go to Home Assistant → Developer Tools → States
   - Search for "temperature" to find your printer's temperature sensors
   - Note the prefix (e.g., `ntk_ryansoffice_3dprinter`)

2. **Copy Card Configuration**:
  - Open [homeassistant/packages/3d_printing/printer_temps/dashboard_cards/printer-temps.yaml](../../../../homeassistant/packages/3d_printing/printer_temps/dashboard_cards/printer-temps.yaml)
  - Copy the full card configuration (single canonical horizontal stack)

3. **Customize Entity Names**:
  - Replace the default entity prefix `ntk_ryansoffice_3dprinter` with your printer prefix
  - Example: replace `sensor.ntk_ryansoffice_3dprinter_nozzle_temperature` with `sensor.bambulab_x1c_nozzle_temperature`

4. **Add to Dashboard**:
   - Go to your Home Assistant dashboard
   - Click Edit Dashboard → Add Card → Manual Card
   - Paste the customized YAML configuration
   - Save

## Usage Examples

### Example 1: Side-by-Side Display (Recommended)

Perfect for showing both temperatures in a compact row:

```yaml
type: horizontal-stack
cards:
  - type: custom:mushroom-template-card
    entity: sensor.bambulab_x1c_nozzle_temperature
    # ... (see full config in printer-temps.yaml)
  - type: custom:mushroom-template-card
    entity: sensor.bambulab_x1c_bed_temperature
    # ... (see full config in printer-temps.yaml)
```

**Result**: `[🔴 220°C | 25°C] [🔵 80°C | 22°C]`

### Example 2: Vertical Stack

If you prefer temperatures stacked vertically:

```yaml
type: vertical-stack
cards:
  - type: custom:mushroom-template-card
    entity: sensor.bambulab_x1c_nozzle_temperature
    # ... (nozzle card config)
  - type: custom:mushroom-template-card
    entity: sensor.bambulab_x1c_bed_temperature
    # ... (bed card config)
```

### Example 3: In a Grid with Other Cards

Combine with other printer status cards:

```yaml
type: grid
columns: 2
cards:
  - type: horizontal-stack
    cards:
      - # Nozzle temp card
      - # Bed temp card
  - type: custom:bubble-card
    entity: sensor.bambulab_x1c_print_status
    # ... other status cards
```

## Customization

### Adjust Temperature Tolerance

The default tolerance is ±2°C. To change it, modify the comparison values:

```yaml
# Change from:
{% if target > current + 2 %}

# To (for 5°C tolerance):
{% if target > current + 5 %}
```

### Change Colors

Modify the RGB values in the `card_mod` section:

```yaml
# Heating (currently red):
background: rgba(244, 67, 54, 0.08);    # Red
border-left: 3px solid rgba(244, 67, 54, 0.8);

# Cooling (currently blue):
background: rgba(33, 150, 243, 0.08);   # Blue
border-left: 3px solid rgba(33, 150, 243, 0.8);

# At target (currently grey):
background: rgba(158, 158, 158, 0.05);  # Grey
```

### Adjust Font Sizes

Modify the `card_mod` style section:

```yaml
.primary {
  font-size: 14px !important;    # Target temp size
}
.secondary {
  font-size: 28px !important;    # Current temp size
}
```

### Different Icons

Change the icons for different states:

```yaml
icon: >-
  {% if target > current + 2 %}
    mdi:fire           # Instead of mdi:arrow-up
  {% elif target < current - 2 %}
    mdi:snowflake      # Instead of mdi:arrow-down
  {% else %}
    mdi:check-circle   # Instead of mdi:thermometer
  {% endif %}
```

## Troubleshooting

### Card Shows "Unknown" or "Unavailable"

**Cause**: Entity names don't match or sensors aren't available

**Solution**:
1. Verify entity names in Developer Tools → States
2. Ensure Bambu Lab integration is configured for LAN mode (required for temperature sensors)
3. Check that your printer model supports temperature sensors

### Colors Not Showing

**Cause**: card-mod not installed

**Solution**:
1. Install card-mod from HACS
2. Restart Home Assistant
3. Clear browser cache (Ctrl+Shift+R)

### Layout Broken on Mobile

**Cause**: Too many cards in horizontal stack

**Solution**:
- Use only 2 cards maximum in a horizontal stack for mobile
- Consider a conditional card that shows vertical stack on mobile:

```yaml
type: conditional
conditions:
  - condition: screen
    media_query: "(max-width: 600px)"
card:
  type: vertical-stack
  # ... vertical layout
```

### Temperatures Not Updating

**Cause**: Bambu Lab integration connectivity issue

**Solution**:
1. Check printer is online and connected to network
2. Verify Bambu Lab integration status in Settings → Devices & Services
3. Ensure LAN mode is enabled (required for real-time updates)

## Technical Details

### Entity Types

- **Sensors** (`sensor.*_temperature`): Read-only current temperature values
- **Numbers** (`number.*_target_temperature`): Read/write target temperature settings

### Update Frequency

Temperature sensors typically update every 1-5 seconds when printer is active, depending on your Bambu Lab integration settings.

### Temperature Comparison Logic

The cards use a ±2°C tolerance to determine heating/cooling state:

- **Heating**: `target > current + 2°C`
- **Cooling**: `target < current - 2°C`  
- **At Target**: Everything else

This prevents constant state changes when temperature fluctuates around the target.

## Related Documentation

- [Bambu Lab Integration Documentation](https://github.com/greghesp/ha-bambulab)
- [Mushroom Cards Documentation](https://github.com/piitaya/lovelace-mushroom)
- [card-mod Documentation](https://github.com/thomasloven/lovelace-card-mod)

## Support

If you encounter issues:

1. Check the [Bambu Lab Integration Issues](https://github.com/greghesp/ha-bambulab/issues)
2. Verify all prerequisites are installed
3. Review Home Assistant logs for errors
4. Test entity availability in Developer Tools → States

## Contributing

Found a bug or have an enhancement idea? Please open an issue in the repository!

---

**Last Updated**: 2024
**Tested With**: 
- Home Assistant 2024.x
- Bambu Lab Integration 2.x
- Mushroom Cards 3.x
- card-mod 3.x




