# Fan Controls Visual Guide

This document provides visual examples of how the fan control cards appear in different states.

<!-- SCREENSHOT: id=fan-controls-printing | format=png | version=1.0 | package=printer_controls | added=2026-03-15 | captured=2026-03-15 -->

![Fan controls — all fans active during print](\docs\screenshots\images\fan-controls-printing.png)

<!-- SCREENSHOT: id=fan-controls-idle | format=png | version=1.0 | package=printer_controls | added=2026-03-15 -->
<!-- Capture: All 4 fan cards when idle — grey icons, 0%/Off values -->
> **📸 Screenshot needed:** Fan controls — idle state (all fans off) *(png)*

## Desktop Layout (Horizontal)

The cards are arranged in a single horizontal row, taking up 1 section width:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FAN CONTROLS SECTION                                │
├──────────────────┬──────────────────┬──────────────────┬──────────────────┤
│    🌀 Aux Fan    │  🌀 Chamber      │  ❄️ Cooling      │  🌀 Bento Box    │
│       45%        │      30%         │      85%         │      Off         │
│                  │                  │                  │                  │
│   (Blue bg)      │  (Purple bg)     │  (Cyan bg)       │  (Green bg)      │
└──────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

## Mobile Layout (Stacked/Grid)

On narrow screens, the horizontal-stack automatically adjusts:

```
┌─────────────────────────┐
│    🌀 Aux Fan           │
│         45%             │
└─────────────────────────┘
┌─────────────────────────┐
│    🌀 Chamber           │
│         30%             │
└─────────────────────────┘
┌─────────────────────────┐
│    ❄️ Cooling           │
│         85%             │
└─────────────────────────┘
┌─────────────────────────┐
│    🌀 Bento Box         │
│         Off             │
└─────────────────────────┘
```

## Alternative Grid Layout (2 Columns)

For better mobile experience, use grid layout with 2 columns:

```
┌─────────────────────────────────────────┐
│   FAN CONTROLS - 2 COLUMN GRID         │
├──────────────────┬──────────────────────┤
│  🌀 Aux Fan      │  🌀 Chamber          │
│      45%         │      30%             │
├──────────────────┼──────────────────────┤
│  ❄️ Cooling      │  🌀 Bento Box        │
│      85%         │      Off             │
└──────────────────┴──────────────────────┘
```

## Color States

### Icon Colors Based on Fan Speed

Each fan icon changes color based on its speed:

#### Fan OFF (0%)
```
┌────────────────┐
│   ⚫ Fan Name   │  ← Grey icon
│      0%        │
└────────────────┘
```

#### Low Speed (< 30%)
```
┌────────────────┐
│   🔵 Fan Name   │  ← Blue/Green icon
│     25%        │
└────────────────┘
```

#### Medium Speed (30-70%)
```
┌────────────────┐
│   🟡 Fan Name   │  ← Amber/Cyan icon
│     50%        │
└────────────────┘
```

#### High Speed (> 70%)
```
┌────────────────┐
│   🔴 Fan Name   │  ← Red/Orange icon
│     85%        │
└────────────────┘
```

## Card States Examples

### Example 1: Printing (All Fans Active)
```
┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐
│  🟡 Aux Fan      │  🔵 Chamber      │  🔴 Cooling      │  🟢 Bento Box    │
│      55%         │      25%         │      90%         │      40%         │
└──────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

### Example 2: Idle (Fans Off)
```
┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐
│  ⚫ Aux Fan      │  ⚫ Chamber      │  ⚫ Cooling      │  ⚫ Bento Box    │
│       0%         │       0%         │       0%         │      Off         │
└──────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

### Example 3: Cooling Down (Partial Activity)
```
┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐
│  🔵 Aux Fan      │  🟡 Chamber      │  🔵 Cooling      │  ⚫ Bento Box    │
│      20%         │      45%         │      15%         │      Off         │
└──────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

## Interactive Features

### Hover Effect

When hovering over a card (desktop), the background becomes slightly more opaque:

```
NORMAL STATE:          HOVER STATE:
┌────────────────┐    ┌────────────────┐
│  🌀 Fan Name   │    │  🌀 Fan Name   │  ← Brighter background
│      45%       │ →  │      45%       │
└────────────────┘    └────────────────┘
  rgba(..., 0.05)       rgba(..., 0.1)
```

### Tap/Click Actions

#### Bambu Lab Fans (Sensors)
```
┌────────────────┐
│  🌀 Aux Fan    │  ← Tap/Click
│      45%       │
└────────────────┘
        ↓
┌─────────────────────────────────┐
│  More Info Dialog               │
│  ┌───────────────────────────┐ │
│  │ Aux Fan Speed             │ │
│  │ Current: 45%              │ │
│  │                           │ │
│  │ [History Graph]           │ │
│  │                           │ │
│  └───────────────────────────┘ │
└─────────────────────────────────┘
```

#### Bento Box Fan (Fan Entity)
```
┌────────────────┐
│  🌀 Bento Box  │  ← Single Tap: Toggle
│      On        │
└────────────────┘
        ↓
┌────────────────┐
│  🌀 Bento Box  │
│      Off       │  ← Fan toggled off
└────────────────┘

OR

┌────────────────┐
│  🌀 Bento Box  │  ← Hold/Long Press
│      40%       │
└────────────────┘
        ↓
┌─────────────────────────────────┐
│  More Info Dialog               │
│  ┌───────────────────────────┐ │
│  │ Bento Box Fan             │ │
│  │ [Toggle] [Speed Slider]   │ │
│  │                           │ │
│  │ Percentage: 40%           │ │
│  │ ═══════════○─────  [40%]  │ │
│  │                           │ │
│  └───────────────────────────┘ │
└─────────────────────────────────┘
```

## Background Colors

Each fan card has a subtle tinted background for visual distinction:

```
Aux Fan (Blue):      Chamber (Purple):   Cooling (Cyan):     Bento Box (Green):
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│              │    │              │    │              │    │              │
│  Blue tint   │    │ Purple tint  │    │  Cyan tint   │    │ Green tint   │
│              │    │              │    │              │    │              │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
rgba(33,150,243)    rgba(156,39,176)    rgba(0,188,212)     rgba(76,175,80)
   alpha: 0.05         alpha: 0.05         alpha: 0.05         alpha: 0.05
```

## Integration with Dashboard

### Placement in Dashboard

The fan controls are designed to be compact and informational. Recommended placement:

```
┌───────────────────────────────────────────────────────────┐
│  DASHBOARD HEADER                                         │
├───────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐ │
│  │ Print Status, Camera, etc.                          │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ AMS Trays                                           │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ FAN CONTROLS (smaller, informational)               │ │
│  │ ┌──────┬──────┬──────┬──────┐                      │ │
│  │ │ Aux  │Chamber│Cool │Bento │                      │ │
│  │ └──────┴──────┴──────┴──────┘                      │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ Other Dashboard Content                             │ │
│  └─────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘
```

## Screen Size Adaptations

### Wide Desktop (> 1200px)
All 4 cards in a single row, evenly spaced

### Medium Desktop/Tablet (768px - 1200px)
All 4 cards in a row, cards may be slightly narrower

### Mobile Portrait (< 768px)
Cards stack vertically OR use 2-column grid layout

## Usage Tips

1. **For Status Monitoring**: Use horizontal-stack for compact display
2. **For Mobile-First**: Use grid layout with `columns: 2`
3. **For Control Focus**: Make cards larger in grid layout with `square: true`
4. **For Compact Dashboard**: Keep as horizontal-stack at bottom of dashboard

## Real-World Usage Scenarios

### Scenario 1: Quick Status Check
```
User glances at dashboard
  ↓
Sees all 4 fan speeds at once
  ↓
Color-coded icons show status immediately
  ↓
No action needed if all normal
```

### Scenario 2: Detailed Investigation
```
User notices high cooling fan speed (red icon)
  ↓
Clicks cooling fan card
  ↓
Views historical data in more-info dialog
  ↓
Sees if speed is normal for current print
```

### Scenario 3: Manual Control
```
User wants to turn on bento box fan
  ↓
Taps bento box fan card
  ↓
Fan toggles on
  ↓
Icon changes from grey to green
```

## Customization Examples

See [fan-controls.md](\docs\features\printer_controls\reference\fan-controls.md) for detailed customization instructions including:
- Changing color thresholds
- Modifying background colors
- Using different icons
- Adding automation triggers
- Creating custom fan control services
