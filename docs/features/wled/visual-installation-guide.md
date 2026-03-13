# Visual Installation Guide - LED Strip Layout

This document provides visual diagrams to help you understand the physical layout of LED strips on your Bambu Lab printer and AMS units.

## Overview Diagram

```
                    ┌──────────────────────────────────────┐
                    │     BAMBU LAB PRINTER SETUP          │
                    └──────────────────────────────────────┘
                                    
        ╔═══════════════════════════════════════════════════════╗
        ║                    PRINTER                            ║
        ║   ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓   ║
        ║   ┃ Interior: Strip 1 (Seg 0) - 30 LEDs       ┃   ║
        ║   ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛   ║
        ║                                                       ║
        ║   ┌─────────────────────────────────────────────┐   ║
        ║   │ Front C-Shape: Strip 2 (Seg 1-3)            │   ║
        ║   │ [========= TOP (Seg 3) =========]           │   ║
        ║   │ ║                                ║           │   ║
        ║   │ ║  LEFT (Seg 2)                  ║           │   ║
        ║   │ ║                                ║           │   ║
        ║   │ [======= BOTTOM (Seg 1) ========]           │   ║
        ║   └─────────────────────────────────────────────┘   ║
        ╚═══════════════════════════════════════════════════════╝
                                    
    ╔════════════════════╗          ╔════════════════════╗
    ║     AMS 1          ║          ║     AMS 2          ║
    ║                    ║          ║                    ║
    ║ Strip 3 (Seg 4-7)  ║          ║ Strip 5 (Seg 12-15)║
    ║ Strip 4 (Seg 8-11) ║          ║ Strip 6 (Seg 0-7)  ║
    ╚════════════════════╝          ╚════════════════════╝
          Digquad                        Digquad + MagWLED
```

## Strip 1: Printer Interior Lighting

```
                    TOP VIEW OF PRINTER LID (OPEN)
    ┌───────────────────────────────────────────────────────┐
    │                                                         │
    │   ┌─────────────────────────────────────────────┐     │
    │   │  ◄──────── LED Strip 1 ────────────►        │     │
    │   │  ╔═══════════════════════════════════╗      │     │
    │   │  ║ 0    5    10   15   20   25   29 ║      │     │
    │   │  ║●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●║      │     │
    │   │  ╚═══════════════════════════════════╝      │     │
    │   │                                             │     │
    │   │         Segment 0: Full Strip              │     │
    │   │         Purpose: Interior Illumination     │     │
    │   └─────────────────────────────────────────────┘     │
    │                                                         │
    └───────────────────────────────────────────────────────┘
    
    Installation Tips:
    - Mount along center of lid for even lighting
    - Can also mount along edge/perimeter
    - Ensure strip doesn't interfere with lid closing
    - Clean surface before mounting
```

## Strip 2: Printer Front C-Shape

```
                    FRONT VIEW OF PRINTER
    
    ┌─────────────────────────────────────────────────┐
    │                  TOP EDGE                       │
    │   ╔═══════════════════════════════════╗         │
    │   ║  90    95    100   105   110  119 ║         │  Segment 3
    │   ║  ●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●║         │  "Top Status"
    │   ╚═══════════════════════════════════╝         │  30 LEDs
    │   ║                                   ║         │  Green/Red
    │   ║                                   ║         │
    │   ║   60                           89 ║         │  Segment 2
    │   ║   ●                             ● ║         │  "Left Status"
    │   ║   ●                             ● ║         │  30 LEDs
    │   ║   ●      PRINTER FRONT          ● ║         │  Green/Red
    │   ║   ●                             ● ║         │
    │   ║   ●                             ● ║         │
    │   ║   ●                             ● ║         │
    │   ╚═══════════════════════════════════╝         │
    │   ╔═══════════════════════════════════╗         │
    │   ║  30    35    40    45    50    59 ║         │  Segment 1
    │   ║  ●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●║         │  "Bottom Progress"
    │   ╚═══════════════════════════════════╝         │  30 LEDs
    │                 BOTTOM EDGE                     │  Progress Bar
    └─────────────────────────────────────────────────┘
    
    Installation Path:
    1. Start at LED 30 (bottom left corner)
    2. Run along bottom edge → LED 59 (bottom right)
    3. Turn up and run along left side → LED 89 (top left)
    4. Run along top edge → LED 119 (top right)
    
    Key Points:
    - Single continuous strip in C-shape
    - No breaks between segments
    - Bottom segment shows print progress
    - Left and top segments show status (green/red)
```

## Strip 3 & 5: AMS Lid Spool Lighting (Reverse C)

```
                AMS 1 LID - TOP VIEW (STRIP 3)
                Segments 4-7 (Digquad)
    
    ┌──────────────────────────────────────────────────┐
    │          AMS 1 - FILAMENT SPOOL AREA             │
    │                                                   │
    │     START HERE (LED 120)                         │
    │           ↓                                       │
    │      ┌────────┬────────┬────────┬────────┐       │
    │      │  ●●●   │  ●●●   │  ●●●   │  ●●●   │       │
    │      │  ●●●   │  ●●●   │  ●●●   │  ●●●   │       │
    │      │  ●●●   │  ●●●   │  ●●●   │  ●●●   │       │
    │      │  ●●●   │  ●●●   │  ●●●   │  ●●●   │       │
    │      │  ●●●   │  ●●●   │  ●●●   │  ●●●   │       │
    │      │        │        │        │        │       │
    │      │ Spool  │ Spool  │ Spool  │ Spool  │       │
    │      │   A1   │   A2   │   A3   │   A4   │       │
    │      │        │        │        │        │       │
    │      │  Seg4  │  Seg5  │  Seg6  │  Seg7  │       │
    │      │120-134 │135-149 │150-164 │165-179 │       │
    │      └────────┴────────┴────────┴────────┘       │
    │           ↑                                       │
    │      LEDs wrap around left side                  │
    │                                                   │
    └──────────────────────────────────────────────────┘
    
    Installation Path:
    1. Start at LED 120 (Spool A1 area)
    2. Wrap around Spool A1 → LED 134
    3. Continue to Spool A2 → LED 149
    4. Continue to Spool A3 → LED 164
    5. Continue to Spool A4 → LED 179
    6. May wrap back on left side
    
    Strip 5 (AMS 2) follows same pattern:
    - Segments 12-15 (Digquad)
    - LEDs 220-279
    - Spools B1, B2, B3, B4
```

## Strip 4: AMS 1 Tag Lighting (Simplified)

```
            AMS 1 FRONT - FILAMENT TAGS VIEW
                Segments 8-11 (Digquad)
    
    ┌──────────────────────────────────────────────────┐
    │          FILAMENT TAG HOLDERS                    │
    │                                                   │
    │    ┌────────┬────────┬────────┬────────┬─────┐   │
    │    │ [LED]  │ [LED]  │        │ [LED]  │[LED]│   │  TOP PATH
    │    │ Tag A1 │ Tag A2 │  Hygro │ Tag A3 │Tag4 │   │
    │    │  Seg8  │  Seg9  │        │  Seg10 │Seg11│   │
    │    │180-189 │190-199 │        │200-209 │210-2│   │
    │    └────────┴────────┴────────┴────────┴─────┘   │
    │                                                   │
    │    [●●●●●●●] [●●●●●●●]        [●●●●●●●] [●●●●]   │
    │                                                   │
    └──────────────────────────────────────────────────┘
    
    Installation Path (TOP PATH ONLY):
    1. Start at LED 180 (Tag A1)
    2. Run across Tag A1 holder → LED 189
    3. Continue to Tag A2 holder → LED 199
    4. Skip hygrometer area
    5. Continue to Tag A3 holder → LED 209
    6. Continue to Tag A4 holder → LED 219
    
    Purpose:
    - Highlight which filament tag is active
    - Shows which spool is currently in use
    - Can also show which spools will be used in print
```

## Strip 6: AMS 2 Tag Lighting (Complex with Top & Bottom)

```
            AMS 2 FRONT - FILAMENT TAGS VIEW
            Segments 0-7 (MagWLED)
    
    ┌──────────────────────────────────────────────────┐
    │          FILAMENT TAG HOLDERS - AMS 2            │
    │                                                   │
    │    ┌────────┬────────┬────────┬────────┬─────┐   │
    │    │ [LED]  │ [LED]  │        │ [LED]  │[LED]│   │  TOP PATH
    │    │ Seg 0  │ Seg 1  │  Hygro │ Seg 2  │Seg3 │   │  (0-39)
    │    │  0-9   │ 10-19  │        │ 20-29  │30-39│   │
    │    │        │        │        │        │     │   │
    │    │ Tag B1 │ Tag B2 │        │ Tag B3 │Tag4 │   │
    │    │        │        │        │        │     │   │
    │    │ Seg 4  │ Seg 5  │        │ Seg 6  │Seg7 │   │  BOTTOM PATH
    │    │ [LED]  │ [LED]  │        │ [LED]  │[LED]│   │  (40-79)
    │    │ 40-49  │ 50-59  │        │ 60-69  │70-79│   │
    │    └────────┴────────┴────────┴────────┴─────┘   │
    │                                                   │
    │    [●●●●●●●●●●] [●●●●●●●●●●]  [●●●●●●●●] [●●●●]  │  Top LEDs
    │         │            │              │        │    │
    │    [●●●●●●●●●●] [●●●●●●●●●●]  [●●●●●●●●] [●●●●]  │  Bottom LEDs
    │                                                   │
    └──────────────────────────────────────────────────┘
    
    Installation Path (BOTH TOP & BOTTOM):
    1. Start at LED 0 (Tag B1 top)
    2. Run across top of tags → LED 39
    3. Wrap around to bottom path
    4. Run back along bottom of tags → LED 79
    
    This gives more control:
    - Can create framing effect
    - Can animate both paths separately
    - More LEDs per tag = better visibility
    
    Alternative Simplified Layout:
    - Use only 4 segments (combine top+bottom)
    - Seg 0: B1 complete (0-19)
    - Seg 1: B2 complete (20-39)
    - Seg 2: B3 complete (40-59)
    - Seg 3: B4 complete (60-79)
```

## Controller Wiring Diagram

```
                PHYSICAL WIRING LAYOUT
    
    ┌─────────────────────────────────────────────────┐
    │          DIGQUAD LED CONTROLLER                 │
    │  ┌──────────────────────────────────────────┐   │
    │  │  5V Power Input  [+]  GND [-]            │   │
    │  └──────────────────────────────────────────┘   │
    │                                                  │
    │  GPIO 1 ───────► Strip 1 (Interior)             │
    │  GPIO 2 ───────► Strip 2 (Front C)              │
    │  GPIO 3 ───────► Strip 3 (AMS1 Lid)             │
    │  GPIO 4 ───────► Strip 4 (AMS1 Tags)            │
    │  GPIO 5 ───────► Strip 5 (AMS2 Lid)             │
    └─────────────────────────────────────────────────┘
                          │
                          │ Power & Ground
                          ↓
                ┌──────────────────┐
                │  POWER SUPPLY    │
                │   5V / 10-15A    │
                └──────────────────┘
                          │
                          │ Power & Ground
                          ↓
    ┌─────────────────────────────────────────────────┐
    │          MAGWLED CONTROLLER                     │
    │  ┌──────────────────────────────────────────┐   │
    │  │  5V Power Input  [+]  GND [-]            │   │
    │  └──────────────────────────────────────────┘   │
    │                                                  │
    │  GPIO 2 ───────► Strip 6 (AMS2 Tags)            │
    └─────────────────────────────────────────────────┘
    
    Power Distribution Notes:
    - Common ground between controllers
    - Power injection for long strips (>100 LEDs)
    - Adequate wire gauge (18-22 AWG)
    - Fuses recommended for safety
```

## Segment ID Visual Reference

```
    SEGMENT ID LEGEND
    
    Digquad Controller:
    ┌─────┬─────┬─────┬─────┐
    │  0  │  1  │  2  │  3  │  Printer: Interior, Bottom, Left, Top
    ├─────┼─────┼─────┼─────┤
    │  4  │  5  │  6  │  7  │  AMS1 Spools: A1, A2, A3, A4
    ├─────┼─────┼─────┼─────┤
    │  8  │  9  │ 10  │ 11  │  AMS1 Tags: A1, A2, A3, A4
    ├─────┼─────┼─────┼─────┤
    │ 12  │ 13  │ 14  │ 15  │  AMS2 Spools: B1, B2, B3, B4
    └─────┴─────┴─────┴─────┘
    
    MagWLED Controller:
    ┌─────┬─────┬─────┬─────┐
    │  0  │  1  │  2  │  3  │  AMS2 Tags Top: B1, B2, B3, B4
    ├─────┼─────┼─────┼─────┤
    │  4  │  5  │  6  │  7  │  AMS2 Tags Bottom: B1, B2, B3, B4
    └─────┴─────┴─────┴─────┘
```

## Color Legend for Status Indicators

```
    PRINTER STATUS COLORS
    
    ┌──────────────────────────────────────────────────┐
    │ GREEN    ████████  Print Running Normally        │
    │ RED      ████████  Error / HMS Alert             │
    │ ORANGE   ████████  Progress Indicator            │
    │ BLUE     ████████  Idle / Standby                │
    │ YELLOW   ████████  Upcoming Spool                │
    │ WHITE    ████████  Active Spool                  │
    │ GRAY     ████████  Inactive Tag                  │
    └──────────────────────────────────────────────────┘
```

## Installation Sequence

```
    RECOMMENDED INSTALLATION ORDER
    
    Day 1: Planning & Prep
    ┌────────────────────────────────┐
    │ 1. Read all documentation      │
    │ 2. Measure LED strips          │
    │ 3. Test each strip             │
    │ 4. Calculate power needs       │
    │ 5. Prepare installation area   │
    └────────────────────────────────┘
    
    Day 2: Physical Installation
    ┌────────────────────────────────┐
    │ 1. Install Strip 1 (Interior)  │
    │ 2. Install Strip 2 (Front C)   │
    │ 3. Install Strip 3 (AMS1 Lid)  │
    │ 4. Install Strip 4 (AMS1 Tags) │
    │ 5. Install Strip 5 (AMS2 Lid)  │
    │ 6. Install Strip 6 (AMS2 Tags) │
    │ 7. Connect to controllers      │
    │ 8. Connect power supply        │
    └────────────────────────────────┘
    
    Day 3: Configuration
    ┌────────────────────────────────┐
    │ 1. Configure Digquad           │
    │ 2. Configure MagWLED           │
    │ 3. Create segments             │
    │ 4. Import presets              │
    │ 5. Test all segments           │
    │ 6. Adjust colors/effects       │
    └────────────────────────────────┘
    
    Day 4: Integration
    ┌────────────────────────────────┐
    │ 1. Add to Home Assistant       │
    │ 2. Create automations          │
    │ 3. Test automations            │
    │ 4. Fine-tune settings          │
    │ 5. Document final config       │
    └────────────────────────────────┘
```

## Tips for Physical Installation

### DO:

### DON'T:

## Measurement Template

Print and use this to record your actual measurements:

```
MY LED STRIP MEASUREMENTS
Date: __________

Strip 1 (Interior):
┌──────────────────────────────────────┐
│ Total LEDs: ______                   │
│ Start LED: 0                         │
│ End LED: ______                      │
│ GPIO Pin: ______                     │
└──────────────────────────────────────┘

Strip 2 (Front C):
┌──────────────────────────────────────┐
│ Bottom Segment LEDs: ______          │
│   Start: ______ End: ______          │
│ Left Segment LEDs: ______            │
│   Start: ______ End: ______          │
│ Top Segment LEDs: ______             │
│   Start: ______ End: ______          │
│ Total LEDs: ______                   │
│ GPIO Pin: ______                     │
└──────────────────────────────────────┘

[Continue for Strips 3-6...]

Power Supply:
┌──────────────────────────────────────┐
│ Voltage: 5V                          │
│ Max Current: ______ A                │
│ Total LED Count: ______              │
│ Calculated Max Draw: ______ A        │
│ Headroom: ______ A                   │
└──────────────────────────────────────┘
```

---
- `README.md` - Overview and design
- `quick-start.md` - Step-by-step guide
- [wiring-diagram.md](wiring-diagram.md) - Detailed wiring instructions

