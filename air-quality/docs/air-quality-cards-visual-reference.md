# Air Quality Cards - Visual Reference

This document provides a visual reference and detailed explanation of the air quality monitoring and control cards.

## Card Layouts

### Horizontal Layout (Desktop Optimized)

The primary layout arranges all air quality sensors in a horizontal row, perfect for wide screens:

```
┌─────────────┬─────────────┬─────────────┬─────────────┬─────────────┐
│   PM2.5     │     CO2     │     VOC     │    Temp     │  Humidity   │
│  [Filter]   │ [Molecule]  │  [Chemical] │[Thermometer]│   [Water]   │
│  12.3 µg/m³ │   650 ppm   │   85 ppb    │   22.5°C    │     45%     │
│   [Green]   │   [Green]   │   [Green]   │   [Green]   │   [Green]   │
└─────────────┴─────────────┴─────────────┴─────────────┴─────────────┘
```

Each card shows:
- Sensor name (top)
- Current reading with unit (middle)
- Color-coded icon (bottom) indicating status

### Grid Layout (Mobile Optimized)

Alternative 2-column grid layout for smaller screens:

```
┌─────────────┬─────────────┐
│   PM2.5     │     CO2     │
│  12.3 µg/m³ │   650 ppm   │
├─────────────┼─────────────┤
│     VOC     │  Purifier   │
│   85 ppb    │   On - 66%  │
└─────────────┴─────────────┘
```

## Color Coding System

### PM2.5 (Particulate Matter)
Visual indicators based on air quality:

```
🟢 Green (Good)           : 0-12 µg/m³    - Excellent air quality
🟡 Yellow (Moderate)      : 12-35 µg/m³   - Acceptable for most people
🟠 Orange (Unhealthy)     : 35-55 µg/m³   - Sensitive groups may be affected
🔴 Red (Very Unhealthy)   : 55+ µg/m³     - Everyone may be affected
```

### CO2 (Carbon Dioxide)
Indicates ventilation and air circulation quality:

```
🟢 Green (Good)        : <800 ppm        - Excellent ventilation
🟡 Yellow (Moderate)   : 800-1200 ppm    - Acceptable ventilation
🟠 Orange (Poor)       : 1200-2000 ppm   - Poor ventilation, open windows
🔴 Red (Very Poor)     : 2000+ ppm       - Very poor ventilation, immediate action
```

### VOC (Volatile Organic Compounds)
Measures off-gassing from printing materials:

```
🟢 Green (Good)        : <100 ppb        - No significant VOCs
🟡 Yellow (Moderate)   : 100-200 ppb     - Mild VOC levels
🟠 Orange (Poor)       : 200-300 ppb     - Elevated VOCs, increase filtration
🔴 Red (Very Poor)     : 300+ ppb        - High VOCs, maximum filtration needed
```

## Govee Air Purifier Control Card

### Main Status Card

Shows current purifier status with color-coded icon:
- **Grey**: Off or unavailable
- **Green**: On, low speed (<30%)
- **Amber**: On, medium speed (30-70%)
- **Red**: On, high speed (>70%)

### Speed Control Buttons

Three-button layout for quick speed adjustment:
- **Low (33%)**: Quiet operation, good air quality
- **Medium (66%)**: Balanced purification
- **High (100%)**: Maximum filtration

## Real-World Examples

### During Normal Operation
```
PM2.5: 8.2 µg/m³ (Green)
CO2: 580 ppm (Green)
VOC: 65 ppb (Green)
Status: Good - Air Quality Excellent
Purifier: Off
```

### During 3D Printing (PLA)
```
PM2.5: 18.5 µg/m³ (Yellow)
CO2: 920 ppm (Yellow)
VOC: 125 ppb (Yellow)
Status: Moderate - Monitor
Purifier: On - 66% (Auto-enabled)
```

### During 3D Printing (ABS - High VOC)
```
PM2.5: 42.3 µg/m³ (Orange)
CO2: 1050 ppm (Yellow)
VOC: 285 ppb (Orange)
Status: Poor - Purifier Recommended
Purifier: On - 100% (Auto-adjusted to high)
```

## Tips for Best Display

### Desktop Dashboards
- Use horizontal-stack for all sensors
- Full width section for visibility
- Group with other printer controls

### Mobile Dashboards
- Use grid layout (2 columns)
- Prioritize most important sensors
- Make purifier control easily accessible

### Integration with Other Cards
```
[Printer Status] [Camera]
[Air Quality Sensors Row]
[Purifier Controls]
[AMS Status]
```
