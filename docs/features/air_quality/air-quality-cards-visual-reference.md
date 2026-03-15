# Air Quality Cards - Visual Reference

This document provides a visual reference and detailed explanation of the air quality monitoring and control cards.

## Card Layout

The layout uses a consolidated header card followed by two rows of three cards each for improved text visibility:

```
┌──────────────────────────────────────────────────────────┐
│  🌬️ Air Quality                                         │
│  Good / Moderate / Poor / Very Poor  (color-coded)       │
└──────────────────────────────────────────────────────────┘
┌──────────────┬──────────────┬──────────────┐
│   PM2.5      │     CO2      │     VOC      │
│  12.3 µg/m³  │   650 ppm    │   85 ppb     │
│   [Green]    │   [Green]    │   [Green]    │
└──────────────┴──────────────┴──────────────┘
┌──────────────┬──────────────┬──────────────┐
│    Temp      │  Humidity    │  Purifier    │
│   22.5°C     │     45%      │  On · Gear 2 │
│   [Green]    │   [Green]    │   [Amber]    │
└──────────────┴──────────────┴──────────────┘
```

Each sensor card shows:
- Sensor name (top)
- Current reading with unit (middle)
- Color-coded icon indicating status

The Purifier card opens a **browser_mod popup** on tap with on/off toggle and Low / Medium / High speed controls.

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

## Govee Air Purifier Control

### Purifier Card (Main Dashboard)

The purifier is shown inline in the second sensor row. Color-coded icon indicates status:
- **Grey**: Off or unavailable
- **Green**: On, Gear 1 (low)
- **Amber**: On, Gear 2 (medium)
- **Red**: On, Gear 3 (high)

### Speed Control Popup

Tapping the Purifier card opens a **browser_mod popup** with:
- Power toggle (tap the status card to turn on/off)
- Three speed buttons: **Low** (Gear 1) · **Medium** (Gear 2) · **High** (Gear 3)
- Active gear is highlighted with its respective color

## Real-World Examples

### During Normal Operation
```
Header: Air Quality — Good (Green)
PM2.5: 8.2 µg/m³ (Green) | CO2: 580 ppm (Green) | VOC: 65 ppb (Green)
Temp: 22.5°C (Green) | Humidity: 45% (Green) | Purifier: Off (Grey)
```

### During 3D Printing (PLA)
```
Header: Air Quality — Moderate (Yellow)
PM2.5: 18.5 µg/m³ (Yellow) | CO2: 920 ppm (Yellow) | VOC: 125 ppb (Yellow)
Temp: 24.1°C (Green) | Humidity: 42% (Green) | Purifier: On · Gear 2 (Amber)
```

### During 3D Printing (ABS - High VOC)
```
Header: Air Quality — Poor — Consider Purifier (Orange)
PM2.5: 42.3 µg/m³ (Orange) | CO2: 1050 ppm (Yellow) | VOC: 285 ppb (Orange)
Temp: 26.3°C (Green) | Humidity: 38% (Amber) | Purifier: On · Gear 3 (Red)
```

## Bento Box Filter Card

The Bento Box filter status is displayed as a single compact card:

```
┌──────────────────────────────────────────────────────────┐
│  ✅ Bento Box                                            │
│  Good · HEPA 42% · Carbon 31%                            │
└──────────────────────────────────────────────────────────┘
```

Tapping opens a **browser_mod popup** with:
- Overall filter status header (Good / Monitor / Replace Soon / Replace Now)
- HEPA filter detail: usage %, runtime hours, remaining hours, days since replacement
- Carbon filter detail: same breakdown
- Bento Box fan speed control
- Compact Reset HEPA / Reset Carbon buttons

## Tips for Best Display

### Desktop Dashboards
- Two rows of 3 sensor cards each provide good readability
- Purifier and Bento Box popups keep the main view uncluttered
- Group with other printer controls

### Mobile Dashboards
- 3-card rows adapt well to smaller screens
- Tap-to-popup interaction is mobile-friendly

### Integration with Other Cards
```
[Printer Status] [Camera]
[Air Quality Header]
[PM2.5 | CO2 | VOC]
[Temp | Humidity | Purifier]
[Bento Box] (compact)
[AMS Status]
```
