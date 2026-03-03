# Temperature Cards - Visual Mockup

This is a text-based representation of what the temperature cards look like in Home Assistant.

## Desktop View - Side by Side

```
╔═══════════════════════════════════════════════════════════════════════════════════╗
║                          HOME ASSISTANT DASHBOARD                                 ║
╠═══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                   ║
║  ┌───────────────────────────────────────┬───────────────────────────────────┐   ║
║  │                                       │                                   │   ║
║  │  ┌──────────────────────────────┐    │   ┌──────────────────────────┐    │   ║
║  ▌  │        NOZZLE TEMP           │    │   │       BED TEMP           │    │   ║
║  ▌  │                              │    │   │                          │    │   ║
║  ▌  │   🔺  220°C                  │    │   │   🔺  80°C               │    │   ║
║  ▌  │                              │    │   │                          │    │   ║
║  ▌  │       218°C                  │    │   │       78°C               │    │   ║
║  ▌  │                              │    │   │                          │    │   ║
║  ▌  └──────────────────────────────┘    │   └──────────────────────────┘    │   ║
║  │  Red background tint                 │   Red background tint             │   ║
║  │  Red left border                     │   Red left border                 │   ║
║  └───────────────────────────────────────┴───────────────────────────────────┘   ║
║                                                                                   ║
║  ↑ When HEATING: Red arrows, red borders, red current temp                       ║
║                                                                                   ║
╠═══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                   ║
║  ┌───────────────────────────────────────┬───────────────────────────────────┐   ║
║  │                                       │                                   │   ║
║  │  ┌──────────────────────────────┐    │   ┌──────────────────────────┐    │   ║
║  ▌  │        NOZZLE TEMP           │    │   │       BED TEMP           │    │   ║
║  ▌  │                              │    │   │                          │    │   ║
║  ▌  │   🔻  0°C                    │    │   │   🔻  0°C                │    │   ║
║  ▌  │                              │    │   │                          │    │   ║
║  ▌  │       218°C                  │    │   │       85°C               │    │   ║
║  ▌  │                              │    │   │                          │    │   ║
║  ▌  └──────────────────────────────┘    │   └──────────────────────────┘    │   ║
║  │  Blue background tint                │   Blue background tint            │   ║
║  │  Blue left border                    │   Blue left border                │   ║
║  └───────────────────────────────────────┴───────────────────────────────────┘   ║
║                                                                                   ║
║  ↑ When COOLING: Blue arrows, blue borders, blue current temp                    ║
║                                                                                   ║
╠═══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                   ║
║  ┌───────────────────────────────────────┬───────────────────────────────────┐   ║
║  │                                       │                                   │   ║
║  │  ┌──────────────────────────────┐    │   ┌──────────────────────────┐    │   ║
║  │  │        NOZZLE TEMP           │    │   │       BED TEMP           │    │   ║
║  │  │                              │    │   │                          │    │   ║
║  │  │   🌡  220°C                  │    │   │   🏠  80°C               │    │   ║
║  │  │                              │    │   │                          │    │   ║
║  │  │       220°C                  │    │   │       80°C               │    │   ║
║  │  │                              │    │   │                          │    │   ║
║  │  └──────────────────────────────┘    │   └──────────────────────────┘    │   ║
║  │  Grey neutral background             │   Grey neutral background         │   ║
║  └───────────────────────────────────────┴───────────────────────────────────┘   ║
║                                                                                   ║
║  ↑ When AT TARGET: Grey icons, neutral colors, no border                         ║
║                                                                                   ║
╚═══════════════════════════════════════════════════════════════════════════════════╝
```

## Mobile View - Stacked

```
╔═══════════════════════════════════╗
║     HOME ASSISTANT MOBILE         ║
╠═══════════════════════════════════╣
║                                   ║
║  ┌───────────────────────────┐   ║
║  │                           │   ║
║  │  ┌───────────────────┐    │   ║
║  ▌  │   NOZZLE TEMP     │    │   ║
║  ▌  │                   │    │   ║
║  ▌  │  🔺  220°C        │    │   ║
║  ▌  │                   │    │   ║
║  ▌  │     218°C         │    │   ║
║  ▌  │                   │    │   ║
║  ▌  └───────────────────┘    │   ║
║  │  Red background/border    │   ║
║  └───────────────────────────┘   ║
║                                   ║
║  ┌───────────────────────────┐   ║
║  │                           │   ║
║  │  ┌───────────────────┐    │   ║
║  ▌  │    BED TEMP       │    │   ║
║  ▌  │                   │    │   ║
║  ▌  │  🔺  80°C         │    │   ║
║  ▌  │                   │    │   ║
║  ▌  │     78°C          │    │   ║
║  ▌  │                   │    │   ║
║  ▌  └───────────────────┘    │   ║
║  │  Red background/border    │   ║
║  └───────────────────────────┘   ║
║                                   ║
╚═══════════════════════════════════╝
```

## Actual Card Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Mushroom Template Card (Horizontal Layout)                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [ICON]  Target°C               Current°C                  │
│   ^         ^                       ^                       │
│   |         |                       |                       │
│   |         |                       |                       │
│   |         Primary Text            Secondary Text          │
│   |         (14px, opacity 0.7)     (28px, bold)            │
│   |                                                          │
│   Icon Color: red/blue/grey based on state                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Size Comparison

```
Target Temp (Primary):    220°C     ← Small (14px)
Current Temp (Secondary):  220°C    ← Large (28px, 2x size)
```

## State Transitions

```
HEATING UP:
  Target: 220°C  →  Icon: 🔺 (red)  →  Background: Red tint
  Current: 25°C  →  Color: RED      →  Border: Red left

↓ Temperature rising...

AT TARGET:
  Target: 220°C  →  Icon: 🌡 (grey) →  Background: Neutral
  Current: 220°C →  Color: GREY     →  Border: None

↓ Print complete, cooling...

COOLING DOWN:
  Target: 0°C    →  Icon: 🔻 (blue) →  Background: Blue tint
  Current: 218°C →  Color: BLUE     →  Border: Blue left
```

## Tolerance Visualization

```
Temperature Range:      |-------|-------|-------|
                       217°    220°    223°
                              ^target

Current: 217°C  →  COOLING (blue)   ← More than 2° below target
Current: 219°C  →  AT TARGET (grey) ← Within ±2° of target
Current: 220°C  →  AT TARGET (grey) ← Within ±2° of target
Current: 221°C  →  AT TARGET (grey) ← Within ±2° of target
Current: 223°C  →  HEATING (red)    ← More than 2° above target
```

## Click Interaction

```
┌─────────────────────────┐
│                         │
│  🔺  220°C              │  ← Click anywhere
│                         │
│     218°C               │  ← Opens more-info dialog
│                         │
└─────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│  Sensor Details                     │
├─────────────────────────────────────┤
│  Entity: sensor.xxx_nozzle_temp     │
│  State: 218°C                       │
│  Attributes:                        │
│    - unit_of_measurement: °C        │
│    - friendly_name: Nozzle Temp     │
│  History:                           │
│  [Temperature graph]                │
└─────────────────────────────────────┘
```

## Integration Example

```
╔═══════════════════════════════════════════════════════════╗
║              3D PRINTER DASHBOARD                         ║
╠═══════════════════════════════════════════════════════════╣
║                                                           ║
║  ┌─────────────────────┬─────────────────┬──────────┐    ║
║  │  🔺  220°C          │  🔺  80°C       │  Status  │    ║
║  │     218°C           │     78°C        │ Printing │    ║
║  └─────────────────────┴─────────────────┴──────────┘    ║
║                                                           ║
║  ┌────────────────────────────────────────────────────┐  ║
║  │         Print Progress: 45%                        │  ║
║  └────────────────────────────────────────────────────┘  ║
║                                                           ║
║  ┌────────────────────────────────────────────────────┐  ║
║  │         Time Remaining: 2h 34m                     │  ║
║  └────────────────────────────────────────────────────┘  ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
```

---

**Note**: This is a text-based mockup. Actual appearance will follow Home Assistant's theme and styling, with smooth fonts, icons, and colors.

The cards will automatically adapt to your Home Assistant theme (dark/light mode) and display real-time temperature data from your Bambu Lab printer.
