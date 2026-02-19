# Visual Reference - Temperature Card States

This document shows visual examples of how the temperature cards appear in different states.

**Note**: As of v2, icons are fixed (thermometer for nozzle, radiator for bed) and color indicators only appear when the printer is actively printing or preparing to print.

## Layout Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    HORIZONTAL STACK                         │
├─────────────────────────────┬───────────────────────────────┤
│     NOZZLE TEMPERATURE      │      BED TEMPERATURE          │
│  ┌─────────────────────┐    │   ┌─────────────────────┐     │
│  │  🌡️ Target°C        │    │   │  🔥 Target°C         │     │
│  │                     │    │   │                     │     │
│  │    Current°C        │    │   │    Current°C        │     │
│  └─────────────────────┘    │   └─────────────────────┘     │
└─────────────────────────────┴───────────────────────────────┘
```

## State Examples

### 🔴 HEATING STATE (Target > Current)

**When**: Printer is actively printing/preparing and warming up

**Nozzle Example**:
```
┌──────────────────────┐
│ 🌡️  220°C           │  ← Red thermometer, target temp (small)
│                      │
│      25°C            │  ← Current temp (large, RED)
└──────────────────────┘
   ▌                      ← Red left border
   Red tinted background
```

**Bed Example**:
```
┌──────────────────────┐
│ 🔥  80°C            │  ← Red radiator, target temp (small)
│                      │
│      22°C            │  ← Current temp (large, RED)
└──────────────────────┘
   ▌                      ← Red left border
   Red tinted background
```

**Visual Details**:
- Icon: `mdi:thermometer` (🌡️) for nozzle or `mdi:radiator` (🔥) for bed - in red
- Background: Light red tint `rgba(244, 67, 54, 0.08)`
- Left border: Solid red `3px solid rgba(244, 67, 54, 0.8)`
- Current temp color: Red `rgb(244, 67, 54)`
- Target temp: Small, 14px, opacity 0.7
- Current temp: Large, 28px, bold

---

### 🔵 COOLING STATE (Target < Current)

**When**: Printer is actively printing and cooling down

**Nozzle Example**:
```
┌──────────────────────┐
│ 🌡️  0°C             │  ← Blue thermometer, target temp (small)
│                      │
│     218°C            │  ← Current temp (large, BLUE)
└──────────────────────┘
   ▌                      ← Blue left border
   Blue tinted background
```

**Bed Example**:
```
┌──────────────────────┐
│ 🔥  0°C             │  ← Blue radiator, target temp (small)
│                      │
│      85°C            │  ← Current temp (large, BLUE)
└──────────────────────┘
   ▌                      ← Blue left border
   Blue tinted background
```

**Visual Details**:
- Icon: `mdi:thermometer` (🌡️) for nozzle or `mdi:radiator` (🔥) for bed - in blue
- Background: Light blue tint `rgba(33, 150, 243, 0.08)`
- Left border: Solid blue `3px solid rgba(33, 150, 243, 0.8)`
- Current temp color: Blue `rgb(33, 150, 243)`
- Target temp: Small, 14px, opacity 0.7
- Current temp: Large, 28px, bold

---

### ⚪ IDLE/AT TARGET (Printer Not Printing)

**When**: Temperature is at target OR printer is idle (not printing/preparing)

**Note**: This state now handles both stable temperature AND idle printer state, eliminating misleading color indicators when the printer is off but showing ambient temperature.

**Nozzle Example (Idle)**:
```
┌──────────────────────┐
│ 🌡️  0°C             │  ← Grey thermometer, target temp (small)
│                      │
│      23°C            │  ← Current temp (large, GREY) - ambient
└──────────────────────┘
   Neutral grey background
```

**Bed Example (At Target)**:
```
┌──────────────────────┐
│ 🔥  80°C            │  ← Grey radiator, target temp (small)
│                      │
│      80°C            │  ← Current temp (large, GREY)
└──────────────────────┘
   Neutral grey background
```

**Visual Details**:
- Nozzle icon: `mdi:thermometer` (🌡️) in grey
- Bed icon: `mdi:radiator` (🔥) in grey
- Background: Very subtle grey `rgba(158, 158, 158, 0.05)`
- No left border
- Current temp color: Grey `rgb(158, 158, 158)`
- Target temp: Small, 14px, opacity 0.7
- Current temp: Large, 28px, bold

---

## Side-by-Side Examples

### Scenario 1: Print Starting (Both Heating)

```
┌─────────────────────────────┬─────────────────────────────┐
│     NOZZLE (HEATING)        │      BED (HEATING)          │
│  ┌─────────────────────┐    │   ┌─────────────────────┐   │
│  │  🌡️ 220°C  [RED]    │    │   │  🔥 80°C   [RED]    │   │
│  │       25°C          │    │   │      22°C           │   │
│  └─────────────────────┘    │   └─────────────────────┘   │
└─────────────────────────────┴─────────────────────────────┘
```

### Scenario 2: Print Active (Both At Target)

```
┌─────────────────────────────┬─────────────────────────────┐
│   NOZZLE (AT TARGET)        │    BED (AT TARGET)          │
│  ┌─────────────────────┐    │   ┌─────────────────────┐   │
│  │  🌡️ 220°C  [GREY]   │    │   │  🔥 80°C   [GREY]   │   │
│  │      220°C          │    │   │      80°C           │   │
│  └─────────────────────┘    │   └─────────────────────┘   │
└─────────────────────────────┴─────────────────────────────┘
```

### Scenario 3: Printer Idle (Both Grey)

**Note**: When printer is idle, color indicators are disabled regardless of temp difference

```
┌─────────────────────────────┬─────────────────────────────┐
│      NOZZLE (IDLE)          │       BED (IDLE)            │
│  ┌─────────────────────┐    │   ┌─────────────────────┐   │
│  │  🌡️ 0°C    [GREY]   │    │   │  🔥 0°C    [GREY]   │   │
│  │       23°C          │    │   │      22°C           │   │
│  └─────────────────────┘    │   └─────────────────────┘   │
└─────────────────────────────┴─────────────────────────────┘
```

### Scenario 4: Mixed States (During Active Print)

```
┌─────────────────────────────┬─────────────────────────────┐
│   NOZZLE (AT TARGET)        │     BED (COOLING)           │
│  ┌─────────────────────┐    │   ┌─────────────────────┐   │
│  │  🌡️ 220°C  [GREY]   │    │   │  🔥 50°C   [BLUE]   │   │
│  │      220°C          │    │   │      78°C           │   │
│  └─────────────────────┘    │   └─────────────────────┘   │
└─────────────────────────────┴─────────────────────────────┘
```

---

## Mobile View

On mobile devices (width < 600px), both cards stack vertically but maintain the same horizontal layout within each card:

```
┌─────────────────────────────┐
│     NOZZLE TEMPERATURE      │
│  ┌─────────────────────┐    │
│  │  🌡️ 220°C  [RED]    │    │
│  │       25°C          │    │
│  └─────────────────────┘    │
└─────────────────────────────┘

┌─────────────────────────────┐
│      BED TEMPERATURE        │
│  ┌─────────────────────┐    │
│  │  🔥 80°C   [RED]    │    │
│  │      22°C           │    │
│  └─────────────────────┘    │
└─────────────────────────────┘
```

---

## Color Palette Reference

### Red (Heating - Only When Printing)
- Background: `rgba(244, 67, 54, 0.08)` - 8% opacity red
- Border: `rgba(244, 67, 54, 0.8)` - 80% opacity red
- Text: `rgb(244, 67, 54)` - Full red
- Icon: `red` (Home Assistant color)

### Blue (Cooling - Only When Printing)
- Background: `rgba(33, 150, 243, 0.08)` - 8% opacity blue
- Border: `rgba(33, 150, 243, 0.8)` - 80% opacity blue
- Text: `rgb(33, 150, 243)` - Full blue
- Icon: `blue` (Home Assistant color)

### Grey (At Target or Idle)
- Background: `rgba(158, 158, 158, 0.05)` - 5% opacity grey
- Border: None
- Text: `rgb(158, 158, 158)` - Full grey
- Icon: `grey` (Home Assistant color)

---

## Icon Reference

| Component | Icon | MDI Code | Color States |
|-----------|------|----------|--------------|
| Nozzle | 🌡️ Thermometer | `mdi:thermometer` | Red/Blue/Grey based on print status |
| Bed | 🔥 Radiator | `mdi:radiator` | Red/Blue/Grey based on print status |

**Note**: Icons are now fixed per component (no more directional arrows). Color indicates heating/cooling state when printer is actively printing.

---

## Comparison with Reference Screenshot

The design matches the Home Assistant Bambu Lab status card shown in the issue:

**Reference Layout**:
```
[Icon] Target°C (small, muted)
  Current°C (large, prominent)
```

**Our Implementation**:
- ✅ Icon positioned to the left
- ✅ Target temperature small and next to icon
- ✅ Current temperature large and prominent
- ✅ Color-coded based on heating/cooling state
- ✅ Colored icon matching state
- ✅ Horizontal layout
- ✅ Mobile responsive
- ✅ Compact size (informational)

---

**Note**: All temperature values shown are examples. Actual values will reflect your printer's real-time data.
