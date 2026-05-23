# Humidity Card Visual Guide

This document provides visual examples and configuration variations for the humidity monitoring card.

## Basic Card Layout

The humidity card displays in a horizontal layout with individual cards for each sensor:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Humidity Monitoring                         │
├──────────────────┬──────────────────┬──────────────────────────┤
│   📦 AMS 1      │   📦 AMS 2       │   🏠 Room (Optional)     │
│   15.2% · 22°C  │   18.7% · 22°C   │   45%                    │
│   [Green Icon]  │   [Green Icon]   │   [Amber Icon]           │
└──────────────────┴──────────────────┴──────────────────────────┘
```

## Color-Coded Status Examples

### Optimal Conditions (Green)
```
┌──────────────────┐
│   📦 AMS 1      │
│   15.2% · 22°C  │  ← Green icon
│   Optimal ✓     │
└──────────────────┘
```
**Status:** Humidity < 20% - Perfect for all filament types including Nylon and TPU

### Good Conditions (Light Green)
```
┌──────────────────┐
│   📦 AMS 1      │
│   28.5% · 21°C  │  ← Light green icon
│   Good          │
└──────────────────┘
```
**Status:** Humidity 20-40% - Acceptable for most filaments

### Monitor Required (Amber)
```
┌──────────────────┐
│   📦 AMS 1      │
│   52.3% · 23°C  │  ← Amber icon
│   Monitor       │
└──────────────────┘
```
**Status:** Humidity 40-60% - PLA/PETG okay, watch Nylon/TPU

### Concern (Orange)
```
┌──────────────────┐
│   📦 AMS 1      │
│   65.8% · 24°C  │  ← Orange icon
│   Concern!      │
└──────────────────┘
```
**Status:** Humidity 60-70% - Filament quality may degrade, replace desiccant

### Critical (Red)
```
┌──────────────────┐
│   📦 AMS 1      │
│   78.4% · 25°C  │  ← Red icon
│   CRITICAL!     │
└──────────────────┘
```
**Status:** Humidity > 70% - Immediate action needed, moisture absorption risk

### Unavailable (Grey)
```
┌──────────────────┐
│   📦 AMS 1      │
│   N/A           │  ← Grey icon
│   Unavailable   │
└──────────────────┘
```
**Status:** Sensor not responding or disconnected

## Layout Variations

### Standard Horizontal Stack (Desktop)
```yaml
type: horizontal-stack
cards:
  - [AMS 1 Card]
  - [AMS 2 Card]
  - [Room Card]
```

**Result:**
```
┌──────────────┬──────────────┬──────────────┐
│   AMS 1      │   AMS 2      │   Room       │
└──────────────┴──────────────┴──────────────┘
```

### Vertical Stack (Mobile/Narrow)
```yaml
type: vertical-stack
cards:
  - [AMS 1 Card]
  - [AMS 2 Card]
  - [Room Card]
```

**Result:**
```
┌──────────────┐
│   AMS 1      │
├──────────────┤
│   AMS 2      │
├──────────────┤
│   Room       │
└──────────────┘
```

### Grid Layout (2 Columns)
```yaml
type: grid
columns: 2
square: false
cards:
  - [AMS 1 Card]
  - [AMS 2 Card]
  - [Room Card]
```

**Result:**
```
┌──────────────┬──────────────┐
│   AMS 1      │   AMS 2      │
├──────────────┴──────────────┤
│   Room                      │
└─────────────────────────────┘
```

### Grid Layout (3 Columns)
```yaml
type: grid
columns: 3
square: false
cards:
  - [AMS 1 Card]
  - [AMS 2 Card]
  - [AMS 3 Card]
  - [AMS 4 Card]
  - [Room Card]
```

**Result:**
```
┌──────────┬──────────┬──────────┐
│  AMS 1   │  AMS 2   │  AMS 3   │
├──────────┼──────────┼──────────┤
│  AMS 4   │  Room    │          │
└──────────┴──────────┴──────────┘
```

## Customization Examples

### Example 1: Temperature in Fahrenheit

**Configuration:**
```yaml
secondary: |-
  {% set humidity = states('sensor.ams_1_humidity') | float(-1) %}
  {% set temp = states('sensor.ams_1_temperature') | float(-1) %}
  {% if humidity >= 0 %}
    {{ humidity | round(1) }}% · {{ ((temp * 9/5) + 32) | round(1) }}°F
  {% else %}
    N/A
  {% endif %}
```

**Display:**
```
┌──────────────────┐
│   📦 AMS 1      │
│   15.2% · 71°F  │  ← Temperature in Fahrenheit
└──────────────────┘
```

### Example 2: Humidity Only (No Temperature)

**Configuration:**
```yaml
secondary: |-
  {% set humidity = states('sensor.ams_1_humidity') | float(-1) %}
  {% if humidity >= 0 %}
    {{ humidity | round(1) }}%
  {% else %}
    N/A
  {% endif %}
```

**Display:**
```
┌──────────────────┐
│   📦 AMS 1      │
│   15.2%         │  ← Humidity only
└──────────────────┘
```

### Example 3: Custom Icon Based on AMS Type

**Configuration:**
```yaml
icon: |-
  {% set humidity = states('sensor.ams_1_humidity') | float(-1) %}
  {% if humidity < 30 %}
    mdi:package-variant-closed-check
  {% elif humidity < 60 %}
    mdi:package-variant
  {% else %}
    mdi:package-variant-closed-remove
  {% endif %}
```

**Display:**
```
┌──────────────────┐
│   ✓📦 AMS 1     │  ← Check icon for good humidity
│   15.2% · 22°C  │
└──────────────────┘
```

### Example 4: Status Text in Secondary Line

**Configuration:**
```yaml
secondary: |-
  {% set humidity = states('sensor.ams_1_humidity') | float(-1) %}
  {% set temp = states('sensor.ams_1_temperature') | float(-1) %}
  {% if humidity >= 0 %}
    {% if humidity < 20 %}
      {{ humidity }}% · {{ temp }}°C · Optimal
    {% elif humidity < 40 %}
      {{ humidity }}% · {{ temp }}°C · Good
    {% elif humidity < 60 %}
      {{ humidity }}% · {{ temp }}°C · Monitor
    {% elif humidity < 70 %}
      {{ humidity }}% · {{ temp }}°C · Concern
    {% else %}
      {{ humidity }}% · {{ temp }}°C · CRITICAL
    {% endif %}
  {% else %}
    N/A
  {% endif %}
```

**Display:**
```
┌──────────────────────────────┐
│   📦 AMS 1                  │
│   15.2% · 22°C · Optimal    │  ← Status text included
└──────────────────────────────┘
```

## Mobile Responsive Behavior

### On Desktop (Wide Screen)
Cards display side-by-side in a horizontal layout:
```
┌─────────────────────────────────────────────────┐
│  [📦 AMS 1]  [📦 AMS 2]  [🏠 Room]            │
└─────────────────────────────────────────────────┘
```

### On Tablet (Medium Screen)
Cards may wrap to multiple rows:
```
┌──────────────────────────┐
│  [📦 AMS 1]  [📦 AMS 2] │
│  [🏠 Room]               │
└──────────────────────────┘
```

### On Mobile (Narrow Screen)
Cards automatically stack vertically:
```
┌──────────────┐
│  📦 AMS 1   │
├──────────────┤
│  📦 AMS 2   │
├──────────────┤
│  🏠 Room    │
└──────────────┘
```

## Integration with Dashboard Sections

### In a Section Card
```yaml
type: sections
sections:
  - type: grid
    title: "3D Printing Environment"
    cards:
      - type: horizontal-stack
        cards:
          - [AMS 1 Card]
          - [AMS 2 Card]
          - [Room Card]
```

### In a Collapsible Section
```yaml
type: custom:fold-entity-row
head:
  type: section
  label: "Humidity Monitoring"
cards:
  - type: horizontal-stack
    cards:
      - [AMS 1 Card]
      - [AMS 2 Card]
      - [Room Card]
```

### Alongside Other Printer Cards
```yaml
type: vertical-stack
cards:
  - type: custom:ha-bambulab-print_status-card
    # ... printer status config
  
  - type: horizontal-stack
    cards:
      - [AMS 1 Humidity Card]
      - [AMS 2 Humidity Card]
  
  - type: custom:ha-bambulab-ams-card
    # ... AMS trays config
```

## Tap Action Customization

### Open More Info Dialog (Default)
```yaml
tap_action:
  action: more-info
  entity: sensor.ams_1_humidity
```

### Open URL (External Dashboard)
```yaml
tap_action:
  action: url
  url_path: "/lovelace/humidity-details"
```

### Call Service (Toggle Dehumidifier)
```yaml
tap_action:
  action: call-service
  service: switch.toggle
  service_data:
    entity_id: switch.dehumidifier
```

### Show Navigation Path
```yaml
tap_action:
  action: navigate
  navigation_path: "/lovelace/environment"
```

### Open Browser Mod Popup
```yaml
tap_action:
  action: fire-dom-event
  browser_mod:
    service: browser_mod.popup
    data:
      title: "AMS 1 Humidity Details"
      content:
        type: history-graph
        entities:
          - sensor.ams_1_humidity
          - sensor.ams_1_temperature
```

## Advanced Styling Examples

### Larger Card with Bold Text
```yaml
card_mod:
  style: |
    ha-card {
      background: rgba(33, 150, 243, 0.1);
      padding: 16px;
    }
    .primary {
      font-size: 18px;
      font-weight: bold;
    }
    .secondary {
      font-size: 14px;
    }
```

### Animated Warning for High Humidity
```yaml
card_mod:
  style: |-
    ha-card {
      {% set humidity = states('sensor.ams_1_humidity') | float(0) %}
      {% if humidity > 70 %}
        background: rgba(244, 67, 54, 0.2);
        animation: pulse 2s infinite;
      {% elif humidity > 60 %}
        background: rgba(255, 152, 0, 0.1);
      {% else %}
        background: rgba(33, 150, 243, 0.05);
      {% endif %}
    }
    @keyframes pulse {
      0% { opacity: 1; }
      50% { opacity: 0.7; }
      100% { opacity: 1; }
    }
```

### Border Color Based on Status
```yaml
card_mod:
  style: |-
    ha-card {
      {% set humidity = states('sensor.ams_1_humidity') | float(0) %}
      {% if humidity > 70 %}
        border: 3px solid var(--error-color);
      {% elif humidity > 60 %}
        border: 3px solid var(--warning-color);
      {% elif humidity < 20 %}
        border: 3px solid var(--success-color);
      {% else %}
        border: 1px solid var(--divider-color);
      {% endif %}
    }
```

## Tips for Best Visual Results

1. **Consistent Sensor Updates** - Ensure sensors update regularly for smooth UI
2. **Theme Compatibility** - Test with both light and dark themes
3. **Icon Selection** - Choose icons that are clear at small sizes
4. **Color Accessibility** - Use colors with good contrast for visibility
5. **Mobile Testing** - Always test on actual mobile devices
6. **Loading States** - Handle unavailable sensors gracefully with "N/A"
7. **Performance** - Keep templates simple for fast rendering

## Further Reading

- [Mushroom Card Documentation](https://github.com/piitaya/lovelace-mushroom)
- [Card-mod Examples](https://github.com/thomasloven/lovelace-card-mod)
- [Home Assistant Themes](https://www.home-assistant.io/integrations/frontend/#themes)
- [Material Design Icons](https://pictogrammers.com/library/mdi/)
