# xTouch 2.8" TFT Screen — Complete Visual Specification

> **Source**: [github.com/xperiments-in/xtouch](https://github.com/xperiments-in/xtouch) `src/ui/`  
> **Purpose**: Exact visual spec for creating graphical renderings of every screen  
> **Display**: 2.8" TFT, **320 × 240 pixels**, ESP32-based (Arduino + LVGL 8.x)

---

## Table of Contents
1. [Global Design System](#1-global-design-system)
2. [Icon Font Reference](#2-icon-font-reference)
3. [Screen 0 — Intro / Splash](#3-screen-0--intro--splash)
4. [Screen Architecture (Screens 1–5)](#4-screen-architecture-screens-15)
5. [Sidebar Component](#5-sidebar-component)
6. [Screen 1 — Home](#6-screen-1--home)
7. [Screen 2 — Temperature](#7-screen-2--temperature)
8. [Screen 3 — Control (Movement)](#8-screen-3--control-movement)
9. [Screen 4 — Filament](#9-screen-4--filament)
10. [Screen 5 — Settings](#10-screen-5--settings)
11. [Overlay — Confirm Panel](#11-overlay--confirm-panel)
12. [Overlay — HMS Panel (Error Alerts)](#12-overlay--hms-panel-error-alerts)
13. [Sub-component — Main Screen Status](#13-sub-component--main-screen-status)
14. [State Variations Cheat Sheet](#14-state-variations-cheat-sheet)

---

## 1. Global Design System

### Display
| Property | Value |
|---|---|
| Resolution | 320 × 240 px |
| Orientation | Landscape |
| Color Depth | 16-bit (RGB565) |

### Color Palette

| Name | Hex | Usage |
|---|---|---|
| **Black** | `#000000` | Intro background, overlay dimming |
| **Dark 1** | `#222222` | Sidebar bg, settings row bg |
| **Dark 2** | `#333333` | Section headers, numpad pressed state, slider track |
| **Dark 3** | `#444444` | Main content bg, dummy spacers, disabled button bg |
| **Medium** | `#555555` | Sub-panels, temp boxes, status bar, HMS container |
| **Medium-Light** | `#777777` | Pressed state on controls, filament icon bg, disabled text |
| **Light Gray** | `#888888` | Muted text |
| **Accent Green** | `#2AFF00` | Checked text, switch ON indicator, scrollbar, progress highlight |
| **Button Green** | `#2AAA00` | YES/Confirm/Done/Retry button bg |
| **Button Green Pressed** | `#2A5500` | YES/Confirm/Done/Retry pressed |
| **Sidebar Pressed** | `#008800` | Sidebar button pressed bg |
| **Slider Green** | `#00FF00` | Slider indicator fill |
| **Accent Orange** | `#FF682A` | Settings title bg, hot temp target, reboot bg |
| **Button Red** | `#AA2A00` | NO / Cancel button bg |
| **Button Red Pressed** | `#552A00` | NO / Cancel pressed |
| **Nozzle Cold (Blue)** | `#39A1FD` | Nozzle temp < 170°C |
| **Nozzle Hot (Orange)** | `#FAA61E` | Nozzle temp ≥ 170°C |
| **White** | `#FFFFFF` | Default text, slider knob |
| **Near White** | `#DDDDDD` | Sidebar default icon color |
| **Light Gray Icons** | `#CCCCCC` | Icon tint in temp/control screens |
| **Muted Gray** | `#AAAAAA` | Logo text color |
| **Dim Gray** | `#999999` | Intro icon tint, very muted text |

### Typography

| Font | Size/Weight | Usage |
|---|---|---|
| `ui_font_xperiments` | Custom icon | xTouch logo — glyph "4" |
| `ui_font_xlcd` | Custom icon (large) | Sidebar icons, content area icons |
| `ui_font_xlcdmin` | Custom icon (small) | Button row icons, dialog button icons |
| `lv_font_montserrat_14` | 14px | Labels, captions, button text |
| `lv_font_montserrat_28` | 28px | Temperature values, numpad keys |

### Common Widget Styling
- **Border radius**: 0 (panels) or 6 (buttons, clickable items)
- **Border**: 0 everywhere except checked states (2px `#2AFF00`)
- **Scrollbar**: Off everywhere except Settings (green `#2AFF00`)
- **Padding standard**: 4px (content), 8px (panels/buttons), 16px (settings rows)

---

## 2. Icon Font Reference

### `ui_font_xlcd` / `ui_font_xlcdmin` Glyph Map

| Char | Icon | Used In |
|---|---|---|
| `"a"` | Home | Sidebar, Control (home button) |
| `"b"` | Thermometer | Sidebar (temperature nav) |
| `"c"` | Control/Joystick | Sidebar (control nav) |
| `"d"` | Settings/Gear | Sidebar (settings nav) |
| `"e"` | Bed (heated bed) | Home temp, Temperature screen |
| `"f"` | Nozzle (hotend) | Home temp, Temperature screen |
| `"g"` | Chamber | Home temp |
| `"h"` | Speed | Home (speed section) |
| `"i"` | Fan | Temperature (fan speed section) |
| `"k"` | Range | Control (step size toggle) |
| `"l"` | XY-Axis crosshair | Control (axis mode XY) |
| `"m"` | Z-Axis vertical | Control (axis mode Z) |
| `"n"` | Filament spool | Sidebar, Filament screen |
| `"p"` | Nozzle icon (alt) | Filament screen nozzle button |
| `"q"` | Checkmark / Confirm | Dialog buttons (HMS, Confirm) |
| `"r"` | Close / X | Dialog NO button |
| `"s"` | Up arrow ▲ | Control, Filament (up buttons) |
| `"t"` | Down arrow ▼ | Control, Filament (down buttons) |
| `"u"` | Left arrow ◄ | Control (left button) |
| `"v"` | Right arrow ► | Control (right button) |
| `"w"` | Light bulb | Home (toggle light button) |
| `"x"` | WiFi | Home status bar |
| `"y"` | Camera | Home status bar |
| `"z"` | Play ▶ | Home (player control) |
| `"0"` | Pause ⏸ | Home (player control) |
| `"1"` | Stop ■ | Home (player control) |
| `"2"` | Clock/Time | Home (remaining time) |
| `"3"` | Layers | Home (layer count) |

### `ui_font_xperiments` Glyph Map

| Char | Icon | Used In |
|---|---|---|
| `"4"` | xTouch logo | Intro screen, Main screen status |

### LVGL Built-in Symbols

| Symbol | Glyph | Used In |
|---|---|---|
| `LV_SYMBOL_SD_CARD` | 📁 | Intro caption |
| `LV_SYMBOL_SETTINGS` | ⚙ | Settings title |
| `LV_SYMBOL_IMAGE` | 🖼 | LCD section header, Invert Colors |
| `LV_SYMBOL_CHARGE` | ⚡ | Backlight label |
| `LV_SYMBOL_POWER` | ⏻ | Sleep min marker, Reboot |
| `LV_SYMBOL_EYE_OPEN` | 👁 | Wake on Print |
| `LV_SYMBOL_SHUFFLE` | 🔀 | Flip Screen |
| `LV_SYMBOL_LIST` | 📋 | Device section |
| `LV_SYMBOL_CLOSE` | ✕ | Numpad back key (when empty) |
| `LV_SYMBOL_BACKSPACE` | ⌫ | Numpad back key (when has input) |
| `LV_SYMBOL_NEW_LINE` | ↵ | Numpad OK key |

---

## 3. Screen 0 — Intro / Splash

```
┌─────────────────────────────────────────────────────┐
│                     #000000                         │
│                                                     │
│                                                     │
│           ┌─────────────────────┐                   │
│           │    "4"              │ xtouch logo       │
│           │  #999999 base       │ ui_font_xperiments│
│           │  #2AFF00 17px       │ overlay accent    │
│           │  overlay            │                   │
│           └─────────────────────┘                   │
│                                                     │
│              📁 caption text                        │
│              #555555                                │
│              montserrat_14                           │
│                                                     │
│                                                     │
└─────────────────────────────────────────────────────┘
320 × 240
```

### Detailed Properties

| Element | Property | Value |
|---|---|---|
| **Screen** | Background | `#000000` |
| | Layout | Flex COLUMN, center all |
| | Padding | 8px left, 8px right |
| **Logo Icon** | Text | `"4"` |
| | Font | `ui_font_xperiments` |
| | Color | `#999999` |
| | Padding | 68px top, 68px bottom (creates vertical centering) |
| | Overlay | 17px wide green bar, `#2AFF00` (achieved via partial-width overlay widget) |
| **Caption** | Content | `LV_SYMBOL_SD_CARD` + status text |
| | Font | `lv_font_montserrat_14` |
| | Color | `#555555` |

---

## 4. Screen Architecture (Screens 1–5)

All main screens share the same root structure:

```
┌──────────┬──────────────────────────────────────────┐
│          │                                          │
│ Sidebar  │         Content Component                │
│  48px    │         flex-grow: 1 (~272px)            │
│          │                                          │
│ #222222  │         #444444                           │
│          │                                          │
│          │                                          │
│          │                                          │
│          │                                          │
│          │                                          │
└──────────┴──────────────────────────────────────────┘
   48px                    272px                 = 320px total
```

| Property | Value |
|---|---|
| Layout | `LV_FLEX_FLOW_ROW` |
| Padding | 0 all sides |
| Size | 320 × 240 |
| Children | [Sidebar, ContentComponent] |

---

## 5. Sidebar Component

**11 child widgets** (including sub-labels)

```
 48px wide
┌──────────┐ ─ top
│          │
│  🏠 "a"  │  Home button
│          │
├──────────┤
│          │
│  🌡 "b"  │  Temp button
│          │
├──────────┤
│          │
│  🕹 "c"  │  Control button
│          │
├──────────┤
│          │
│  🧵 "n"  │  Filament button
│          │
├──────────┤
│          │
│  ⚙ "d"  │  Settings button
│          │
└──────────┘ ─ bottom
```

### Properties Detail

| Element | Property | Value |
|---|---|---|
| **Root Panel** | Width | 48px |
| | Height | 100% (240px) |
| | Background | `#222222` |
| | Layout | Flex COLUMN, SPACE_AROUND |
| | Padding | 2px all sides |
| **Each Button** | Width | 100% (fills 48px) |
| | Height | flex-grow: 1 (≈46px each with 5 buttons) |
| | Radius | 4 |
| | Background | Transparent (default) |
| | Icon Font | `ui_font_xlcd` |
| | Icon Alignment | Center |

### Button States

| State | Text Color | Background |
|---|---|---|
| Default | `#FFFFFF` → `#DDDDDD` | Transparent |
| Checked (active screen) | `#2AFF00` | Transparent |
| Pressed | Inherit | `#008800` |

---

## 6. Screen 1 — Home

**39 child widgets**. Most complex screen.

```
┌──────┬────────────────────────────────┬────────────┐
│      │ WiFi "x" │ Cam "y" │ AMS ████ │ Light "w"  │ 28px status bar
│      ├────────────────────────────────┼────────────┤
│  S   │                               │            │
│  I   │    Main Status / Player       │   Noz "f"  │
│  D   │  ▶ ⏸ ■   ═══════════ 35%     │   35°      │
│  E   │          12:34  L: 5/100      │            │
│  B   │                               ├────────────┤
│  A   │    ┌─────────────────────┐    │   Bed "e"  │
│  R   │    │  Speed "h"  ▼ 100% │    │   60°      │
│      │    └─────────────────────┘    │            │
│  48  │                               ├────────────┤
│  px  │                               │  Chmbr "g" │
│      │                               │   25°      │
└──────┴────────────────────────────────┴────────────┘
```

### Layout Tree

```
homeScreen (ROW)
├── sidebarComponent (48px) [see Section 5]
└── homeComponent (flex-grow:1, ~272px)
    ├── leftPanel (200px, COLUMN)
    │   ├── statusBar (28px, ROW)
    │   │   ├── WiFi icon "x" (ui_font_xlcdmin, #888888)
    │   │   ├── Camera icon "y" (ui_font_xlcdmin, #888888)
    │   │   ├── AMS Color Strip 1 (8×10px, border 1px #444444)
    │   │   ├── AMS Color Strip 2 (8×10px)
    │   │   ├── AMS Color Strip 3 (8×10px)
    │   │   └── AMS Color Strip 4 (8×10px)
    │   ├── mainScreenStatus (flex-grow:3) [see Section 13]
    │   │   [OR when printing: playerSection]
    │   ├── playerRow (32px, ROW)
    │   │   ├── Play "z" (flex-grow:1, checked: #2AFF00)
    │   │   ├── Pause "0" (flex-grow:1)
    │   │   └── Stop "1" (flex-grow:1)
    │   ├── progressSlider (146×14px)
    │   ├── infoRow (ROW)
    │   │   ├── Time icon "2" + time label
    │   │   └── Layer icon "3" + layer label
    │   └── speedSection (ROW)
    │       ├── Speed icon "h" (ui_font_xlcdmin, #CCCCCC)
    │       └── Speed dropdown (montserrat_14)
    └── rightPanel (72px, COLUMN)
        ├── lightButton "w" (flex-grow:1)
        │   [checked: border 2px #2AFF00]
        ├── nozzleTemp (flex-grow:1)
        │   ├── Icon "f" (ui_font_xlcdmin, #CCCCCC)
        │   └── Value "35" (montserrat_28)
        ├── bedTemp (flex-grow:1)
        │   ├── Icon "e" (ui_font_xlcdmin, #CCCCCC)
        │   └── Value "60" (montserrat_28)
        └── chamberTemp (flex-grow:1)
            ├── Icon "g" (ui_font_xlcdmin, #CCCCCC)
            └── Value "25" (montserrat_28)
```

### Key Measurements

| Element | Size | Background | Details |
|---|---|---|---|
| homeComponent root | 272×240 | `#444444` | Flex ROW, pad 4px |
| Left Panel | 200px wide | Transparent | Flex COLUMN |
| Status Bar | 200×28px | `#555555` | Flex ROW, pad 4px, radius 0 |
| WiFi/Camera icons | Auto | — | `ui_font_xlcdmin`, `#888888` |
| AMS Color Strips | 8×10px each | Dynamic color | border 1px `#444444`, radius 2 |
| Player Buttons | flex-grow:1, 32px tall | `#555555` | `ui_font_xlcdmin`, pressed: `#777777` |
| Progress Slider | 146×14px | Track `#333333` | Indicator: `#00FF00`, Knob: `#FFFFFF` |
| Speed Dropdown | auto | `#555555` | `montserrat_14` |
| Right Panel | 72px wide | Transparent | Flex COLUMN, gap 4px |
| Light Button | 72px, flex-grow:1 | `#555555` | Icon `"w"`, radius 6 |
| Temp Boxes | 72px, flex-grow:1 | `#555555` | Icon + value stacked, pad 4px |
| Temp Values | auto | — | `montserrat_28`, `#FFFFFF` |

---

## 7. Screen 2 — Temperature

**40 child widgets**. Three-panel layout with numpad.

### Default View (Temps Panel visible, Numpad hidden)

```
┌──────┬────────────────────────────────────────────┐
│      │                                            │
│  S   │  ┌─────────────────────────────────────┐   │
│  I   │  │  🔥 "f"  Nozzle                     │   │
│  D   │  │         35°     [___]                │   │
│  E   │  │  bg #555555           montserrat_28  │   │
│  B   │  └─────────────────────────────────────┘   │
│  A   │                                            │
│  R   │  ┌─────────────────────────────────────┐   │
│      │  │  🛏 "e"  Bed                        │   │
│      │  │         60°     [___]                │   │
│      │  │  bg #555555           montserrat_28  │   │
│      │  └─────────────────────────────────────┘   │
│      │                                            │
└──────┴────────────────────────────────────────────┘
```

### Numpad Active View (sidebar hidden, temps compressed)

```
┌────────────────────┬──────────────────────────────┐
│                    │                              │
│  🔥 "f"  35° [___] │   1   2   3                 │
│  #555555           │   4   5   6                 │
│                    │   7   8   9                 │
│  🛏 "e"  60° [___] │   0   ✕   ↵                 │
│  #555555           │                              │
│                    │  bg #444444                  │
│                    │  keys: #555555, radius 6     │
└────────────────────┴──────────────────────────────┘
```

### Fan Edit View (sidebar hidden, fans + numpad)

```
┌────────────────────┬──────────────────────────────┐
│                    │                              │
│ 💨"i" PART   [___] │   1   2   3                  │
│ #555555            │   4   5   6                  │
│ 💨"i" AUX    [___] │   7   8   9                  │
│ #555555            │   0   ✕   ↵                  │
│ 💨"i" CHAMBER[___] │                              │
│ #555555            │                              │
│                    │                              │
└────────────────────┴──────────────────────────────┘
```

### Layout Tree

```
temperatureScreen (ROW)
├── sidebarComponent (48px)
└── temperatureComponent (flex-grow:1)
    ├── tempsPanel (flex-grow:3, COLUMN)
    │   ├── nozzleSection (flex-grow:2, ROW SPACE_BETWEEN)
    │   │   ├── Nozzle icon "f" (ui_font_xlcd, #CCCCCC)
    │   │   ├── Nozzle value "35" (montserrat_28)
    │   │   └── Nozzle textarea (max 3 chars, montserrat_28)
    │   └── bedSection (flex-grow:2, ROW SPACE_BETWEEN)
    │       ├── Bed icon "e" (ui_font_xlcd, #CCCCCC)
    │       ├── Bed value "60" (montserrat_28)
    │       └── Bed textarea (max 3 chars, montserrat_28)
    ├── fansPanel (flex-grow:3, COLUMN) [HIDDEN by default]
    │   ├── partFanRow (flex-grow:1, ROW SPACE_BETWEEN)
    │   │   ├── Fan icon "i" (ui_font_xlcd, #CCCCCC)
    │   │   ├── Label "PART" (montserrat_14, right-align)
    │   │   ├── Value "%" (montserrat_14)
    │   │   └── Textarea (50px, max 3 chars)
    │   ├── auxFanRow (identical)
    │   └── chamberFanRow (identical, hidden on P1P w/o chamber)
    └── keyboardPanel (flex-grow:7, ROW_WRAP) [HIDDEN by default]
        ├── Hidden textarea (150px, max 3 chars)
        ├── Keys: 1, 2, 3 [row 1]
        ├── Keys: 4, 5, 6 [row 2 — "4" has FLEX_IN_NEW_TRACK]
        ├── Keys: 7, 8, 9 [row 3 — "7" has FLEX_IN_NEW_TRACK]
        └── Keys: 0, Back, OK [row 4 — "0" has FLEX_IN_NEW_TRACK]
```

### Key Measurements

| Element | Size | Background | Details |
|---|---|---|---|
| temperatureComponent | flex-grow:1, 100% h | `#444444` | Flex ROW centered, pad 4px |
| tempsPanel | flex-grow:3 | Transparent | Flex COLUMN |
| Nozzle/Bed sections | flex-grow:2 | `#555555` | ROW SPACE_BETWEEN, pad 8px, radius 0 |
| Icons ("f", "e") | auto | — | `ui_font_xlcd`, `#CCCCCC` |
| Values | auto | — | `montserrat_28`, `#FFFFFF` |
| Textarea input | auto | Transparent | `montserrat_28`, centered, max 3 chars |
| fansPanel | flex-grow:3 | Transparent | COLUMN, 4px row gap |
| Fan rows | flex-grow:1 | `#555555` | ROW SPACE_BETWEEN, pad 8px |
| Fan labels | auto, right-align | — | `montserrat_14` |
| Fan textareas | 50px wide | — | `montserrat_14`, max 3 chars |
| keyboardPanel | flex-grow:7 | `#444444` | ROW_WRAP, pad 4px L/R |
| Numpad keys | flex-grow:1 | `#555555` | `montserrat_28`, radius 6, pad 12px |
| Numpad keys pressed | — | `#333333` | — |
| Back key (empty) | flex-grow:1 | `#555555` | `LV_SYMBOL_CLOSE` |
| Back key (has input) | flex-grow:1 | `#555555` | `LV_SYMBOL_BACKSPACE` |
| OK key | flex-grow:1 | `#555555` | `LV_SYMBOL_NEW_LINE` |

### Interactive States

| State | Visual Change |
|---|---|
| Nozzle/Bed selected (checked) | 2px border `#2AFF00` |
| Nozzle/Bed pressed | Background → `#2AFF00` |
| Target temp > 0 | Icon + placeholder turn orange `#FF682A` |
| Numpad key pressed | Background → `#333333` |
| Fan row selected (checked) | 2px border `#2AFF00` |
| Fan row pressed | Background → `#2AFF00` |

---

## 8. Screen 3 — Control (Movement)

**21 child widgets**. 3-column directional pad.

```
┌──────┬────────────┬────────────┬────────────┐
│      │            │            │            │
│  S   │  Range "k" │   Up "s"   │ Axis "l"  │
│  I   │  1 / 10    │  #555555   │  XY / Z   │
│  D   │  #444444   │            │  #444444   │
│  E   ├────────────┼────────────┼────────────┤
│  B   │            │            │            │
│  A   │ Left "u"   │  Home "a"  │ Right "v"  │
│  R   │  #555555   │  #555555   │  #555555   │
│      │            │            │            │
│      ├────────────┼────────────┼────────────┤
│      │            │            │            │
│      │  (spacer)  │  Down "t"  │  (spacer)  │
│      │  #444444   │  #555555   │  #444444   │
│      │            │            │            │
└──────┴────────────┴────────────┴────────────┘
```

### Layout Tree

```
controlScreen (ROW)
├── sidebarComponent (48px)
└── controlComponent (flex-grow:1)
    ├── columnA (flex-grow:1, COLUMN)
    │   ├── rangeButton (flex-grow:2, ROW SPACE_BETWEEN)
    │   │   ├── Range icon "k" (ui_font_xlcd)
    │   │   └── Value "-" → "1" / "10" (montserrat_28)
    │   ├── leftButton (flex-grow:2, ROW SPACE_BETWEEN)
    │   │   └── Left arrow "u" (ui_font_xlcd)
    │   └── dummySpacer (flex-grow:2)
    ├── columnB (flex-grow:1, COLUMN)
    │   ├── upButton (flex-grow:2)
    │   │   └── Up arrow "s" (ui_font_xlcd)
    │   ├── homeButton (flex-grow:2)
    │   │   └── Home icon "a" (ui_font_xlcd)
    │   └── downButton (flex-grow:2)
    │       └── Down arrow "t" (ui_font_xlcd)
    └── columnC (flex-grow:1, COLUMN)
        ├── axisToggle (flex-grow:2)
        │   └── "l" (XY mode) / "m" (Z mode) (ui_font_xlcd)
        ├── rightButton (flex-grow:2)
        │   └── Right arrow "v" (ui_font_xlcd)
        └── dummySpacer (flex-grow:2)
```

### Key Measurements

| Element | Size | Background | Details |
|---|---|---|---|
| controlComponent | flex-grow:1, 100% h | `#444444` | Flex ROW centered, pad 4px |
| Each column | flex-grow:1 (≈90px) | Transparent | Flex COLUMN |
| Action buttons | flex-grow:2 (≈80px tall) | `#555555` | Center aligned, pad 8px |
| Range button | flex-grow:2 | `#444444` | ROW SPACE_BETWEEN |
| Axis toggle | flex-grow:2 | `#444444` | Center aligned |
| Dummy spacers | flex-grow:2 | `#444444` | Non-clickable |
| All icons | auto | — | `ui_font_xlcd`, `#FFFFFF` |

### Interactive States

| State | Visual Change |
|---|---|
| Button pressed | Background → `#777777` |
| Z-axis mode active | Axis icon changes `"l"` → `"m"` |
| Z-axis mode | Left + Right buttons DISABLED |
| Disabled button | Background → transparent, text → `#444444` |
| Home button pressed | Opens Confirm Panel: "Start Homing Process?" |
| Range toggle | Cycles: "-" → "1" → "10" → "1" (step size in mm) |

---

## 9. Screen 4 — Filament

**10 child widgets**. Two-column layout.

```
┌──────┬──────────────────────┬──────────────────────┐
│      │                      │                      │
│  S   │    Up "s"            │    UN                 │
│  I   │    ▲                 │    LOAD               │
│  D   │    #555555           │    #555555            │
│  E   ├──────────────────────┼──────────────────────┤
│  B   │                      │                      │
│  A   │  Nozzle "p"  35°    │  Filament "n"        │
│  R   │  #777777             │  #777777             │
│      │  temp: blue/orange   │                      │
│      ├──────────────────────┼──────────────────────┤
│      │                      │                      │
│      │    Down "t"          │    LOAD               │
│      │    ▼                 │    #555555            │
│      │    #555555           │                      │
│      │                      │                      │
└──────┴──────────────────────┴──────────────────────┘
```

### Layout Tree

```
filamentScreen (ROW)
├── sidebarComponent (48px)
└── filamentComponent (flex-grow:1)
    ├── nozzleColumn (flex-grow:2, COLUMN)
    │   ├── nozzleUpButton (flex-grow:2)
    │   │   └── Up arrow "s" (ui_font_xlcd)
    │   ├── nozzleIconTemp (flex-grow:1, ROW, flex-end align)
    │   │   ├── Nozzle icon "p" (ui_font_xlcd)
    │   │   └── Temp value (montserrat_28, color-coded)
    │   └── nozzleDownButton (flex-grow:2)
    │       └── Down arrow "t" (ui_font_xlcd)
    └── filamentColumn (flex-grow:2, COLUMN)
        ├── unloadButton (flex-grow:2)
        │   └── "UN\nLOAD" (montserrat_14, centered)
        ├── filamentIcon (flex-grow:1)
        │   └── Spool icon "n" (ui_font_xlcd)
        └── loadButton (flex-grow:2)
            └── "LOAD" (montserrat_14, centered)
```

### Key Measurements

| Element | Size | Background | Details |
|---|---|---|---|
| filamentComponent | flex-grow:1, 100% h | `#444444` | Flex ROW centered, pad 4px |
| Nozzle column | flex-grow:2 | Transparent | Flex COLUMN |
| Filament column | flex-grow:2 | Transparent | Flex COLUMN |
| Up/Down buttons | flex-grow:2 | `#555555` | Radius 6, pad-top 28px |
| Nozzle icon area | flex-grow:1 | `#777777` | ROW flex-end, radius 6, pad 8px, clickable |
| Filament icon area | flex-grow:1 | `#777777` | Radius 6 |
| Load button | flex-grow:2 | `#555555` | Radius 6, pad-top 36px |
| Unload button | flex-grow:2 | `#555555` | Radius 6, pad-top 28px |
| Nozzle temp value | auto | — | `montserrat_28` |

### Interactive States / Color Coding

| State | Visual Change |
|---|---|
| Any button pressed | Background → `#777777` |
| AMS not idle | Load/Unload DISABLED: text `#777777`, bg `#444444` |
| Nozzle temp < 170°C | Temp text color: `#39A1FD` (blue) |
| Nozzle temp ≥ 170°C | Temp text color: `#FAA61E` (orange) |
| Nozzle icon clicked | Opens temperature keypad for nozzle target |

---

## 10. Screen 5 — Settings

**32 child widgets**. Scrollable vertical list.

```
┌──────┬─────────────────────────────────────────────┐
│      │ ⚙ SETTINGS                                  │ #FF682A bg, #000 text
│      ├─────────────────────────────────────────────┤
│  S   │ 🖼 LCD                                      │ #333333 bg
│  I   ├─────────────────────────────────────────────┤
│  D   │ Back ⚡     ═══════════════════════          │ #222222 bg, 70px
│  E   ├─────────────────────────────────────────────┤
│  B   │ Sleep       ═══════════════════════  12m     │ #222222 bg, 70px
│  A   ├─────────────────────────────────────────────┤
│  R   │ 👁 Wake on Print              [====]         │ #222222 bg, switch
│      ├─────────────────────────────────────────────┤
│      │ 🖼 Invert Colors              [====]         │ #222222 bg, switch
│      ├─────────────────────────────────────────────┤
│      │ 🔀 Flip Screen                [====]         │ #222222 bg, switch
│      ├─────────────────────────────────────────────┤
│      │ 📋 XTOUCH v{version}                        │ #333333 bg
│      ├─────────────────────────────────────────────┤
│      │ AUX FAN                       [====]         │ conditional
│      │ CHAMBER FAN                   [====]         │ conditional
│      │ CHAMBER TEMP                  [====]         │ conditional
│      │ OTA Update                    [====]         │ #222222 bg
│      ├─────────────────────────────────────────────┤
│      │ ⏻ Reboot Device                             │ #FF682A bg, #000 text
└──────┴─────────────────────────────────────────────┘
```

### Layout Tree

```
settingsScreen (ROW)
├── sidebarComponent (48px)
└── settingsComponent (flex-grow:1, COLUMN, SCROLLABLE)
    ├── settingsTitle: "⚙ SETTINGS"
    ├── lcdHeader: "🖼 LCD"
    ├── backlightPanel (70px, ROW)
    │   ├── Label: "Back ⚡"
    │   └── Slider (range 10–255)
    ├── sleepPanel (70px, ROW)
    │   ├── Label: "Sleep"
    │   ├── Slider (range 4–60)
    │   └── Value label: "{val}m" or ⏻
    ├── wakeOnPrintRow (ROW SPACE_BETWEEN)
    │   ├── Label: "👁 Wake on Print"
    │   └── Switch (50×25)
    ├── invertColorsRow
    │   ├── Label: "🖼 Invert Colors"
    │   └── Switch
    ├── flipScreenRow
    │   ├── Label: "🔀 Flip Screen"
    │   └── Switch
    ├── deviceHeader: "📋 XTOUCH v{version}"
    ├── auxFanRow (hidden on non-P1P/X1)
    │   ├── Label: "AUX FAN"
    │   └── Switch
    ├── chamberFanRow (hidden on non-P1P)
    │   ├── Label: "CHAMBER FAN"
    │   └── Switch
    ├── chamberTempRow (hidden on non-P1)
    │   ├── Label: "CHAMBER TEMP"
    │   └── Switch
    ├── otaRow
    │   ├── Label: "OTA Update"
    │   └── Switch
    └── rebootButton: "⏻ Reboot Device"
```

### Key Measurements

| Element | Size | Background | Details |
|---|---|---|---|
| settingsComponent | flex-grow:1, 100% h | `#444444` | COLUMN, pad 8L/16R/8T/8B, row gap 8px |
| Settings title | auto | `#FF682A` | `montserrat_14`, text `#000000`, radius 6, pad 16L/12T/12B |
| Section headers | auto | `#333333` | `montserrat_14`, text `#FFFFFF`, radius 6, pad 16L/12T/12B |
| Slider panels | 70px height | `#222222` | ROW, radius 6, pad 16L/16R |
| Toggle rows | auto | `#222222` | ROW SPACE_BETWEEN, pad 16px all |
| Reboot button | auto | `#FF682A` | `montserrat_14`, text `#000000`, radius 6, clickable |

### Slider Styling

| Part | Color |
|---|---|
| Track | `#333333` |
| Indicator (filled) | `#00FF00` |
| Knob | `#FFFFFF` |
| Height | 10px |
| Width | flex-grow:1 (fills remaining space) |

### Switch Styling (All Switches)

| Part | State | Color |
|---|---|---|
| Size | — | 50×25 px |
| Indicator | Unchecked | Default gray |
| Indicator | Checked | `#2AFF00` |
| Knob | Default | `#2AFF00` |
| Knob | Checked | `#000000` |

### Scrollbar

| Property | Value |
|---|---|
| Mode | Active (appears on scroll) |
| Color | `#2AFF00` |

---

## 11. Overlay — Confirm Panel

**7 child widgets**. Modal dialog for confirmations (e.g., "Start Homing Process?").

```
┌─────────────────────────────────────────────────────┐
│                  #000000 @ 78% opacity               │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │  "Start Homing Process?"                     │    │
│  │  montserrat_14, white text, pad 8 T/B        │    │
│  │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │    │
│  │                                              │    │
│  │  ┌─── NO ───┐         ┌─── YES ───┐         │    │
│  │  │ "r" #AA2A00│        │ "q" #2AAA00│        │    │
│  │  │ montserrat │        │ montserrat │        │    │
│  │  └───────────┘         └───────────┘         │    │
│  │  bg #555555                                  │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### Layout

| Element | Property | Value |
|---|---|---|
| **Overlay root** | Size | 100% × 100% (fills entire screen) |
| | Position | FLOATING (on top of everything) |
| | Layout | Flex ROW, center all |
| | Background | `#000000`, opacity 200/255 (≈78%) |
| | Border | 0 |
| | Default state | HIDDEN |
| **Container** | Width | 100% |
| | Height | SIZE_CONTENT (auto) |
| | Layout | Flex ROW (with wrapping via FLEX_IN_NEW_TRACK) |
| | Background | `#555555` |
| | Border | 0 |
| **Caption** | Width | 100% |
| | Font | Default (montserrat_14) |
| | Padding | 0 L/R, 8 T/B |
| | Text | Dynamic (e.g., "Start Homing Process?") |
| **NO Button** | Background | `#AA2A00` (red-orange) |
| | Pressed bg | `#552A00` |
| | Icon | `"r"` (✕) in `ui_font_xlcdmin` |
| | Label | "NO" in `montserrat_14` |
| | Layout | FLEX_IN_NEW_TRACK (wraps below caption) |
| | Radius | 6, pad 8 all |
| | flex-grow | 1 |
| **YES Button** | Background | `#2AAA00` (green) |
| | Pressed bg | `#2A5500` |
| | Icon | `"q"` (✓) in `ui_font_xlcdmin` |
| | Label | "YES" in `montserrat_14` |
| | Radius | 6, pad 8 all |
| | flex-grow | 1 |

---

## 12. Overlay — HMS Panel (Error Alerts)

**9 child widgets**. Health Management System error notification overlay.

```
┌─────────────────────────────────────────────────────┐
│                  #000000 @ 78% opacity               │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │  "Filament runout detected. Please           │    │
│  │   check the spool."                          │    │
│  │  montserrat_14, white, wrapping, pad 8 T/B   │    │
│  │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │    │
│  │                                              │    │
│  │  ┌ Retry ┐  ┌ Done ┐  ┌ Confirm ┐           │    │
│  │  │#2AAA00│  │#2AAA00│  │#2AAA00  │           │    │
│  │  └───────┘  └──────┘  └─────────┘           │    │
│  │  bg #555555                                  │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### Button Visibility by Style

| Style Enum | Retry | Done | Confirm |
|---|---|---|---|
| `ONLY_CONFIRM` | Hidden | Hidden | Visible |
| `CONFIRM_AND_CANCEL` | Hidden | Hidden | Visible |
| `CONFIRM_AND_DONE` | Hidden | Visible | Visible |
| `CONFIRM_AND_RETRY` | Visible | Hidden | Visible |
| `DONE_AND_RETRY` | Visible | Visible | Hidden* |

*Note: Code shows Confirm is cleared initially then buttons are conditionally shown.

### Layout

| Element | Property | Value |
|---|---|---|
| **Overlay root** | Size | 100% × 100% |
| | Position | FLOATING |
| | Background | `#000000`, opacity 200/255 |
| | Default state | HIDDEN |
| **Container** | Width | 100% |
| | Height | SIZE_CONTENT |
| | Layout | Flex ROW (wrapping) |
| | Background | `#555555` |
| **Caption** | flex-grow | 1 |
| | Text | Dynamic HMS error message |
| | Long mode | LV_LABEL_LONG_WRAP (word-wrapping) |
| | Padding | 0 L/R, 8 T/B |
| **Retry Button** | Icon | `"q"` in `ui_font_xlcdmin` |
| | Label | "Retry" in `montserrat_14` |
| | Background | `#2AAA00`, pressed: `#2A5500` |
| | Radius | 6, pad 8 all |
| | flex-grow | 1, FLEX_IN_NEW_TRACK |
| **Done Button** | Icon | `"q"` in `ui_font_xlcdmin` |
| | Label | "Done" in `montserrat_14` |
| | Background | `#2AAA00`, pressed: `#2A5500` |
| | Radius | 6, pad 8 all |
| | flex-grow | 1, FLEX_IN_NEW_TRACK |
| **Confirm Button** | Icon | `"q"` in `ui_font_xlcdmin` |
| | Label | "Confirm" in `montserrat_14` |
| | Background | `#2AAA00`, pressed: `#2A5500` |
| | Radius | 6, pad 8 all |
| | flex-grow | 1, FLEX_IN_NEW_TRACK |

---

## 13. Sub-component — Main Screen Status

**3 child widgets**. Shows on Home screen when printer is idle.

```
┌────────────────────────────┐
│                            │
│       "4"                  │  xtouch logo
│   ui_font_xperiments       │  #AAAAAA
│                            │
│       "N/A"                │  Status caption
│   montserrat_14             │  #FFFFFF
│                            │
│   bg: #555555              │
└────────────────────────────┘
```

### Properties

| Element | Property | Value |
|---|---|---|
| **Root** | Width | 100% |
| | Height | flex-grow: 3 |
| | Layout | Flex COLUMN, SPACE_EVENLY, center |
| | Background | `#555555` |
| | Padding | 8 L/R, 0 T/B |
| | Row gap | 0 |
| | Column gap | 4 |
| | Text color | `#FFFFFF` |
| **Logo** | Text | `"4"` |
| | Font | `ui_font_xperiments` |
| | Color | `#AAAAAA` |
| **Caption** | Text | "N/A" (default, updated to printer model/status) |
| | Font | `lv_font_montserrat_14` |

---

## 14. State Variations Cheat Sheet

### Universal Pattern

| State | Typical Change |
|---|---|
| **Default** | Base bg color, `#FFFFFF` text |
| **Pressed** | Lighter bg (`#555555` → `#777777`, `#444444` → `#777777`) |
| **Checked** (active nav) | Text → `#2AFF00`, sometimes border 2px `#2AFF00` |
| **Disabled** | Text → `#777777`/`#444444`, bg → transparent or `#444444` |

### Screen-Specific Variations

| Screen | Variation | Trigger |
|---|---|---|
| Home | Play button text turns `#2AFF00` | Currently playing |
| Home | Light button gets 2px `#2AFF00` border | Light is ON |
| Temperature | Nozzle/Bed icon+placeholder turn `#FF682A` | Target temp > 0 |
| Temperature | Sidebar hides, numpad appears | Tap any temp/fan field |
| Temperature | Numpad back key toggles `✕` / `⌫` | Input empty / has chars |
| Control | Axis icon changes `"l"` ↔ `"m"` | XY / Z toggle |
| Control | Left+Right buttons disabled | Z-axis mode |
| Control | Home triggers confirm dialog | Tap home button |
| Filament | Nozzle temp blue `#39A1FD` / orange `#FAA61E` | < 170° / ≥ 170°C |
| Filament | Load/Unload disabled | AMS not idle |
| Settings | AUX FAN / CHAMBER FAN / CHAMBER TEMP rows | Model-dependent visibility |
| Settings | Sleep value shows `⏻` symbol | Below minimum sleep time |

---

## Appendix: Complete Widget Count Summary

| Component | # Children | Purpose |
|---|---|---|
| Sidebar | 11 | Navigation (5 buttons × 2 + root) |
| Home | 39 | Status + player + temperatures |
| Temperature | 40 | Temp input + fan input + numpad |
| Control | 21 | 3×3 directional pad |
| Filament | 10 | Nozzle control + load/unload |
| Settings | 32 | Scrollable preferences list |
| Confirm Panel | 7 | YES/NO modal dialog |
| HMS Panel | 9 | Error notification with Retry/Done/Confirm |
| Main Screen Status | 3 | Idle status display (logo + caption) |
| **Total** | **172** | |

---

*Document generated from raw LVGL C source code analysis of the xTouch firmware.*
