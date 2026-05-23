# WLED Wiring Diagram and Configuration Guide

- Status: Active
- Last Reviewed: 2026-05-23
- Functional Owner: wled
- Replaces: docs/features/wled/wiring-diagram.md
- Replaced By: n/a


## Physical Layout Overview

This document provides detailed wiring instructions for connecting LED strips to your Digquad controller for Bambu Lab printer lighting.

**System Specifications:**
- **Total LEDs**: 711
- **Controller**: Digquad (5 GPIO outputs)
- **LED Types**: COB 160 LED/m and Mini 2.7mm 160 LED/m

For complete LED specifications, see [digquad-led-segments.md](digquad-led-segments.md).
For function details, see [LED Function Map](../design/light-scenarios.md#2-led-function-map-consolidated).
For scenario behaviors, see [light-scenarios.md](../design/light-scenarios.md).

## Controller Specifications

### Digquad Controller
- **GPIO Outputs**: 5 (GPIO 15, 1, 3, 16, 4)
- **Total LEDs**: 711
- **Max LEDs per port**: Varies by LED type and power supply
- **Power**: Requires adequate 5V power supply (15-20A recommended)

## Wiring Diagram

```
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
                            DIGQUAD LED CONTROLLER
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                                                                               â”‚
â”‚  [DIGQUAD]                                                                    â”‚
â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”                   â”‚
â”‚  â”‚  Power:  5V â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ [Power Supply]   â”‚                   â”‚
â”‚  â”‚  Ground: GND â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€[Power Supply]   â”‚                   â”‚
â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜                   â”‚
â”‚                                                                               â”‚
â”‚  OUTPUT PORTS:                                                                â”‚
â”‚                                                                               â”‚
â”‚  Port 1 (GPIO 1):  â”€â”€â”€â”€â”€â”€â”€â–º Strip 1: Printer Interior                        â”‚
â”‚                              â””â”€ 30 LEDs (example)                             â”‚
â”‚                              â””â”€ Segment 0: Full strip                         â”‚
â”‚                                                                               â”‚
â”‚  Port 2 (GPIO 2):  â”€â”€â”€â”€â”€â”€â”€â–º Strip 2: Printer Front (C-shape)                 â”‚
â”‚                              â””â”€ 90 LEDs total (example)                       â”‚
â”‚                              â”œâ”€ Segment 1: Bottom (30 LEDs) - Progress bar   â”‚
â”‚                              â”œâ”€ Segment 2: Left (30 LEDs) - Status           â”‚
â”‚                              â””â”€ Segment 3: Top (30 LEDs) - Status            â”‚
â”‚                                                                               â”‚
â”‚  Port 3 (GPIO 3):  â”€â”€â”€â”€â”€â”€â”€â–º Strip 3: AMS 1 Lid Spool Lighting                â”‚
â”‚                              â””â”€ 60 LEDs total (example)                       â”‚
â”‚                              â”œâ”€ Segment 4: Spool A1 (15 LEDs)                â”‚
â”‚                              â”œâ”€ Segment 5: Spool A2 (15 LEDs)                â”‚
â”‚                              â”œâ”€ Segment 6: Spool A3 (15 LEDs)                â”‚
â”‚                              â””â”€ Segment 7: Spool A4 (15 LEDs)                â”‚
â”‚                                                                               â”‚
â”‚  Port 4 (GPIO 4):  â”€â”€â”€â”€â”€â”€â”€â–º Strip 4: AMS 1 Tag Lighting                      â”‚
â”‚                              â””â”€ 40 LEDs total (example)                       â”‚
â”‚                              â”œâ”€ Segment 8: Tag A1 (10 LEDs)                  â”‚
â”‚                              â”œâ”€ Segment 9: Tag A2 (10 LEDs)                  â”‚
â”‚                              â”œâ”€ Segment 10: Tag A3 (10 LEDs)                 â”‚
â”‚                              â””â”€ Segment 11: Tag A4 (10 LEDs)                 â”‚
â”‚                                                                               â”‚
â”‚  Port 5 (GPIO 5):  â”€â”€â”€â”€â”€â”€â”€â–º Strip 5: AMS 2 Lid Spool Lighting                â”‚
â”‚                              â””â”€ 60 LEDs total (example)                       â”‚
â”‚                              â”œâ”€ Segment 12: Spool B1 (15 LEDs)               â”‚
â”‚                              â”œâ”€ Segment 13: Spool B2 (15 LEDs)               â”‚
â”‚                              â”œâ”€ Segment 14: Spool B3 (15 LEDs)               â”‚
â”‚                              â””â”€ Segment 15: Spool B4 (15 LEDs)               â”‚
â”‚                                                                               â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜

Total LED Count: ~280 LEDs (example - adjust based on your actual strips)
Total Segments: 16/16 (all segments used, at maximum capacity)


â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
                            MAGWLED CONTROLLER
â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                                                                               â”‚
â”‚  [MAGWLED]                                                                    â”‚
â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”                   â”‚
â”‚  â”‚  Power:  5V â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ [USB-C or Power] â”‚                   â”‚
â”‚  â”‚  Ground: GND â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€[Power Supply]   â”‚                   â”‚
â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜                   â”‚
â”‚                                                                               â”‚
â”‚  OUTPUT PORT:                                                                 â”‚
â”‚                                                                               â”‚
â”‚  Port 1 (GPIO 2): â”€â”€â”€â”€â”€â”€â”€â”€â–º Strip 6: AMS 2 Tag Lighting                      â”‚
â”‚                              â””â”€ 80 LEDs total (example)                       â”‚
â”‚                              â”œâ”€ Segment 0: Tag B1 Top (10 LEDs)              â”‚
â”‚                              â”œâ”€ Segment 1: Tag B2 Top (10 LEDs)              â”‚
â”‚                              â”œâ”€ Segment 2: Tag B3 Top (10 LEDs)              â”‚
â”‚                              â”œâ”€ Segment 3: Tag B4 Top (10 LEDs)              â”‚
â”‚                              â”œâ”€ Segment 4: Tag B1 Bottom (10 LEDs)           â”‚
â”‚                              â”œâ”€ Segment 5: Tag B2 Bottom (10 LEDs)           â”‚
â”‚                              â”œâ”€ Segment 6: Tag B3 Bottom (10 LEDs)           â”‚
â”‚                              â””â”€ Segment 7: Tag B4 Bottom (10 LEDs)           â”‚
â”‚                                                                               â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜

Total LED Count: ~80 LEDs (example - adjust based on your actual strip)
Total Segments: 8/16 (8 segments remaining for future use)
```

## Physical Strip Layout

**IMPORTANT**: The specifications below are updated with actual LED counts (711 total).
For complete specifications, see [digquad-led-segments.md](digquad-led-segments.md).

### Printer Front Door (GPIO 15, 158 LEDs, Range: 0-157)
```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚         PRINTER LID (INSIDE)         â”‚
â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”‚
â”‚  â”‚ â—„â”€â”€â”€â”€â”€ LED Strip 1 â”€â”€â”€â”€â”€â”€â”€â”€â”€â–º â”‚  â”‚
â”‚  â”‚  [============================] â”‚  â”‚
â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

### Strip 2: Printer Front (C-Shape)
```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚      PRINTER FRONT VIEW (C-SHAPE)    â”‚
â”‚                                       â”‚
â”‚  [====== TOP (Segment 3) ======]     â”‚ Status: Green/Red
â”‚  â•‘                            â•‘      â”‚
â”‚  â•‘    LEFT (Segment 2)        â•‘      â”‚ Status: Green/Red
â”‚  â•‘                            â•‘      â”‚
â”‚  [====== BOTTOM (Seg 1) ======]      â”‚ Progress Bar
â”‚                                       â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

### Strip 3 & 5: AMS Lid Spool Lighting (Reverse C-Shape)
```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚       AMS LID (TOP VIEW)              â”‚
â”‚                                       â”‚
â”‚  â”Œâ”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”           â”‚
â”‚  â”‚  A1 â”‚  A2 â”‚  A3 â”‚  A4 â”‚           â”‚
â”‚  â”‚ [=] â”‚ [=] â”‚ [=] â”‚ [=] â”‚           â”‚  LED strip wraps
â”‚  â”‚  â”‚  â”‚  â”‚  â”‚  â”‚  â”‚  â”‚  â”‚           â”‚  around each spool
â”‚  â”‚  â””â”€â”€â”´â”€â”€â”´â”€â”€â”´â”€â”€â”´â”€â”€â”˜     â”‚           â”‚
â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜           â”‚
â”‚    Segment: 4    5    6    7          â”‚
â”‚    (or 12-15 for AMS 2)               â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

### Strip 4 & 6: AMS Tag Lighting (Complex Path)
```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚       AMS FRONT (TAG VIEW)            â”‚
â”‚                                       â”‚
â”‚  â”Œâ”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”   â”‚
â”‚  â”‚ [=] â”‚ [=] â”‚       â”‚ [=] â”‚ [=] â”‚   â”‚ TOP path: Segments 8-11
â”‚  â”‚ Tag â”‚ Tag â”‚ Hygro â”‚ Tag â”‚ Tag â”‚   â”‚           (or 0-3 for AMS2)
â”‚  â”‚ A1  â”‚ A2  â”‚ meter â”‚ A3  â”‚ A4  â”‚   â”‚
â”‚  â”‚ [=] â”‚ [=] â”‚       â”‚ [=] â”‚ [=] â”‚   â”‚ BOTTOM path: Add 4 to seg ID
â”‚  â””â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”˜   â”‚
â”‚                                       â”‚
â”‚  Note: For Digquad Strip 4, only     â”‚
â”‚  TOP segments (8-11) are used.       â”‚
â”‚  For MagWLED Strip 6, both TOP       â”‚
â”‚  (0-3) and BOTTOM (4-7) are used.    â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

## Step-by-Step Installation Instructions

### Step 1: Pre-Installation Planning
1. **Measure LED Counts**: Count exact number of LEDs in each strip section
2. **Test Strips**: Connect each strip individually to verify all LEDs work
3. **Plan Power**: Calculate total power needs (60mA per LED at full white)
4. **Prepare Workspace**: Clear area around printer and AMS units

### Step 2: Strip Installation

#### Printer Interior (Strip 1)
1. Clean the inside of printer lid with isopropyl alcohol
2. Apply LED strip along the center or edge of lid
3. Connect to Digquad Port 1
4. Test: All LEDs should light up

#### Printer Front C-Shape (Strip 2)
1. Clean printer front, left side, and top edge
2. Carefully measure and mark the following sections:
   - Bottom: Width of printer base
   - Left: Height of printer side
   - Top: Width of printer top
3. Apply strip in continuous C-shape
4. Note the LED numbers where each section begins/ends
5. Connect to Digquad Port 2
6. Test: Verify all three sections light properly

#### AMS 1 Lid (Strip 3)
1. Clean AMS 1 lid top surface
2. Apply strip in reverse C pattern:
   - Start at spool A1 position
   - Wrap around each spool area (A1, A2, A3, A4)
   - End at left side wrap-around
3. Mark LED positions for each spool segment
4. Connect to Digquad Port 3
5. Test: Each spool should be illuminated

#### AMS 1 Tags (Strip 4)
1. Apply strip across the top of filament tag holders
2. Route through/around hygrometer space
3. For simplified version: Just use top path
4. For complex version: Also route bottom path
5. Connect to Digquad Port 4
6. Test: Each tag area should light up

#### AMS 2 Lid (Strip 5)
1. Repeat same process as Strip 3
2. Connect to Digquad Port 5

#### AMS 2 Tags (Strip 6)
1. Apply strip with both top and bottom paths
2. This is more complex than Strip 4
3. Connect to MagWLED Port 1
4. Test: All 8 segments should be controllable

### Step 3: LED Count Documentation
After installation, record actual LED positions:

**Create a file named: `led_counts.txt`**
```
Strip 1 (Interior): 0-29 (30 LEDs)
Strip 2 (Printer Front):
  - Bottom: 30-59 (30 LEDs)
  - Left: 60-89 (30 LEDs)
  - Top: 90-119 (30 LEDs)
Strip 3 (AMS1 Lid):
  - A1: 120-134 (15 LEDs)
  - A2: 135-149 (15 LEDs)
  - A3: 150-164 (15 LEDs)
  - A4: 165-179 (15 LEDs)
[... continue for all strips ...]
```

### Step 4: WLED Configuration

#### Configure Digquad:
1. Connect to Digquad's web interface (usually http://digquad.local or IP address)
2. Go to Config > LED Preferences
3. Set total LED count based on your measurements
4. Configure each strip's GPIO pin and LED count
5. Go to Segments
6. Create 15 segments based on your LED counts
7. Name each segment appropriately
8. Save configuration

#### Configure MagWLED:
1. Connect to MagWLED's web interface (usually http://wled-a972b4.local)
2. Update LED count to match Strip 6
3. Create 8 segments for AMS 2 tags
4. Save configuration

### Step 5: Import Presets
1. Download preset JSON files from this repository
2. In WLED web interface, go to Config > Presets
3. Use import function or manually create presets
4. Test each preset to verify functionality

### Step 6: Home Assistant Integration
1. Add both WLED devices in Home Assistant
2. Configuration > Integrations > Add Integration > WLED
3. Enter IP addresses or mDNS names
4. Create automations to trigger presets based on printer state

## Power Supply Recommendations

### Power Calculation
- Total LEDs: 711
- Each LED draws approximately 60mA at full white brightness
- Maximum theoretical: 711 Ã— 0.06A = 42.66A at full white
- Typical usage: 30-50% brightness with mixed colors = 12-21A
- **Recommended**: 15-20A @ 5V power supply with adequate headroom

### Power Injection
For optimal performance:
- Inject power at each GPIO output
- Use adequate wire gauge (18-22 AWG)
- Keep voltage drop below 0.5V
- Full white at 100% is rarely needed in practice

### Separate Power Considerations
- Digquad can handle 5 strips but may need external power injection
- Each strip should have its own power connection for strips > 100 LEDs
- Ground all power supplies together
- Use a common ground between controller and strips

## Troubleshooting Guide

### LEDs Not Lighting
- Check power supply voltage (should be 5V Â±0.5V)
- Verify ground connections
- Check GPIO pin configuration in WLED
- Test with single color (red) at low brightness

### Wrong Colors
- Check LED type in WLED config (WS2812B, SK6812, etc.)
- Verify RGB order (RGB, GRB, BGR, etc.)
- Try different order settings until colors are correct

### Segments Not Working
- Verify start/stop LED numbers
- Check that segments don't overlap
- Ensure segment IDs are sequential
- Verify GPIO pin for each strip

### Effects Not Smooth
- Reduce FPS in WLED settings
- Simplify effects
- Check power supply stability
- Reduce number of active segments

### Flickering
- Usually a power issue
- Add power injection points
- Use shorter wire runs
- Check for loose connections

## Advanced Configuration

### Custom Effects
WLED supports custom effects through:
- JSON API for dynamic control
- Home Assistant automations
- Custom palettes
- User-defined patterns

### Synchronization
Both controllers can be synchronized:
- Use WLED sync feature
- Configure UDP sync ports
- Set same group number
- Enable in Config > Sync Interfaces

### Progress Bar Implementation
For printer progress (Segment 1 - Printer Bottom):
1. Use Home Assistant automation
2. Read `sensor.bambu_lab_x1c_print_progress`
3. Calculate LED count: `(Progress% / 100) Ã— LEDs_in_segment`
4. Use WLED API to set individual LED colors
5. Update every 1-5 seconds

Example API call:
```json
{
  "seg": [{
    "id": 1,
    "i": [0, 15, "FF5500", 16, 30, "000000"]
  }]
}
```
This lights LEDs 0-15 orange (progress) and 16-30 black (remaining)

## Maintenance

### Regular Checks
- Monthly: Verify all segments working
- Quarterly: Clean LED strips with compressed air
- Annually: Check wire connections and solder joints

### Software Updates
- Keep WLED firmware updated
- Backup configurations before updates
- Test all presets after updates

## Future Enhancements

### Possible Additions
1. **Temperature indicators**: Color-code based on hotend/bed temp
2. **Filament color matching**: Match AMS LEDs to actual filament colors
3. **Time remaining indicators**: Visual countdown
4. **Error codes**: Display specific HMS error patterns
5. **Humidity alerts**: Flash when humidity is high
6. **Maintenance reminders**: Special patterns for maintenance schedule

### Available Segments
- Digquad: 0 unused segments (all 16 used)
- MagWLED: 8 unused segments
- Can expand MagWLED or add more indicators on future devices

## Safety Warnings

âš ï¸ **IMPORTANT SAFETY INFORMATION** âš ï¸

1. **Electrical Safety**
   - Never exceed the rated current of your power supply
   - Always use proper wire gauge for the current
   - Keep power supplies away from water/moisture
   - Use fuses or circuit breakers

2. **Fire Safety**
   - LED strips can get hot at full brightness
   - Ensure adequate ventilation
   - Don't cover strips with flammable materials
   - Monitor temperature during initial testing

3. **Printer Safety**
   - Don't interfere with printer mechanics
   - Keep wires away from moving parts
   - Don't block ventilation
   - Test thoroughly before long prints

4. **Controller Safety**
   - Don't exceed voltage ratings
   - Protect controllers from physical damage
   - Keep away from high temperatures
   - Ensure proper grounding

## Support and Resources

- **WLED Documentation**: https://kno.wled.ge/
- **WLED GitHub**: https://github.com/Aircoookie/WLED
- **Home Assistant WLED**: https://www.home-assistant.io/integrations/wled/
- **Bambu Lab Integration**: https://github.com/greghesp/ha-bambulab

## Revision History

- v1.0 (2024): Initial configuration for dual AMS setup
- LED counts are examples - must be customized for your installation




