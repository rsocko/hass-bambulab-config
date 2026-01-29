# Preset-Based Segment Configuration - Visual Guide

This document provides visual representations to help understand how preset-based segment configurations work.

## Traditional vs Preset-Based Approach

### Traditional Approach (Single Static Segment Layout)

```
┌─────────────────────────────────────────────────────────────┐
│                     DIGQUAD CONTROLLER                      │
│                   Fixed Segment Layout                       │
│                     (Always the Same)                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Segment 0: Progress Bar                                    │
│  Segment 1: Front Door Status                               │
│  Segment 2-5: AMS Tray Lighting                            │
│                                                              │
│  ┌────────────── Tag Control ──────────────┐               │
│  │                                          │               │
│  │  Segment 6:  A1 Tag TOP  ✓ Individual   │               │
│  │  Segment 7:  A2 Tag TOP  ✓ Individual   │               │
│  │  Segment 8:  A3 Tag TOP  ✓ Individual   │               │
│  │  Segment 9:  A4 Tag TOP  ✓ Individual   │               │
│  │  Segment 10: B1 Tag TOP  ✓ Individual   │               │
│  │  Segment 11: B2 Tag TOP  ✓ Individual   │               │
│  │  Segment 12: B3 Tag TOP  ✓ Individual   │               │
│  │  Segment 13: B4 Tag TOP  ✓ Individual   │               │
│  │                                          │               │
│  │  Segment 14: ALL Tag Bottoms ❌ Combined │               │
│  │              (A1+A2+A3+A4+B1+B2+B3+B4)  │               │
│  │              + Hygrometers               │               │
│  │                                          │               │
│  └──────────────────────────────────────────┘               │
│                                                              │
│  Result: ❌ Cannot highlight BOTH top AND bottom            │
│          of a specific tag                                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Preset-Based Approach (Dynamic Segment Layouts)

```
                     MULTIPLE PRESET CONFIGURATIONS
                   (Switch between them dynamically)

┌─────────────────────────────────────────────────────────────┐
│                   PRESET 50: A1 ACTIVE                      │
│              (Optimized for Tray A1 Full Control)           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Segment 0: Progress Bar                                    │
│  Segment 1: Front Door Status                               │
│  Segment 2-5: AMS Tray Lighting                            │
│                                                              │
│  ┌────────────── Tag Control ──────────────┐               │
│  │                                          │               │
│  │  Segment 6:  A1 Tag TOP  ✓ ACTIVE      │  ← Filament   │
│  │  Segment 7:  A1 Tag BOTTOM ✓ ACTIVE    │  ← Color      │
│  │                                          │               │
│  │  Segment 8:  A2-A4 Tags TOP (Combined)  │               │
│  │  Segment 9:  B1-B4 Tags TOP (Combined)  │               │
│  │  Segment 10: A2-A4 Tags BOTTOM (Comb.)  │               │
│  │  Segment 11: B1-B4 Tags BOTTOM (Comb.)  │               │
│  │  Segment 12-13: Hygrometers             │               │
│  │                                          │               │
│  └──────────────────────────────────────────┘               │
│                                                              │
│  Result: ✓ Full control of A1 top AND bottom!              │
│                                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   PRESET 51: A2 ACTIVE                      │
│              (Optimized for Tray A2 Full Control)           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Segment 0-5: Same (Progress, Status, AMS)                 │
│                                                              │
│  ┌────────────── Tag Control ──────────────┐               │
│  │                                          │               │
│  │  Segment 6:  A2 Tag TOP  ✓ ACTIVE      │  ← Filament   │
│  │  Segment 7:  A2 Tag BOTTOM ✓ ACTIVE    │  ← Color      │
│  │                                          │               │
│  │  Segment 8:  A1,A3-A4 Tags TOP (Comb.)  │               │
│  │  Segment 9:  B1-B4 Tags TOP (Combined)  │               │
│  │  Segment 10: A1,A3-A4 Tags BOTTOM       │               │
│  │  Segment 11: B1-B4 Tags BOTTOM          │               │
│  │  Segment 12-13: Hygrometers             │               │
│  │                                          │               │
│  └──────────────────────────────────────────┘               │
│                                                              │
│  Result: ✓ Full control of A2 top AND bottom!              │
│                                                              │
└─────────────────────────────────────────────────────────────┘

... and so on for Presets 52-57 (A3, A4, B1, B2, B3, B4)
```

## How Preset Switching Works

```
PRINTING WORKFLOW WITH PRESET-BASED SEGMENTS

Step 1: Print Starts
┌─────────────────────────────────┐
│ Bambu Lab Printer               │
│ Active Tray: A1 (Tray 1)       │
└────────────┬────────────────────┘
             │
             │ sensor.bambu_active_tray = "1"
             ▼
┌─────────────────────────────────────────────────┐
│ Home Assistant Automation                       │
│ "WLED - Active Tray Preset Switcher"          │
├─────────────────────────────────────────────────┤
│                                                 │
│ 1. Detect active tray changed to 1             │
│ 2. Calculate preset: 49 + 1 = 50               │
│ 3. Get filament color from Spoolman            │
│                                                 │
└────────────┬────────────────────────────────────┘
             │
             │ service: light.turn_on preset: 50
             ▼
┌─────────────────────────────────────────────────┐
│ WLED Controller (DigQuad)                      │
├─────────────────────────────────────────────────┤
│                                                 │
│ 1. Load Preset 50 configuration                │
│ 2. RECONFIGURE SEGMENTS (takes ~500ms)         │
│    - Segment 6 → A1 Top (442-453)              │
│    - Segment 7 → A1 Bottom (502-513)           │
│    - Segment 8 → A2-A4 tops combined           │
│    - etc.                                       │
│                                                 │
└────────────┬────────────────────────────────────┘
             │
             │ Wait 500ms for reconfiguration
             ▼
┌─────────────────────────────────────────────────┐
│ Set Colors                                      │
├─────────────────────────────────────────────────┤
│                                                 │
│ Segment 6 (A1 Top):    #FF5733 (filament)     │
│ Segment 7 (A1 Bottom): #FF5733 (filament)     │
│ Segment 8-11:          #FFDCB4 (neutral)      │
│                                                 │
└─────────────────────────────────────────────────┘

Result:
         A1 TAG
    ┌──────────────┐
    │   #FF5733    │  ← TOP (bright)
    │   ▓▓▓▓▓▓▓▓  │
    │   ▓▓▓▓▓▓▓▓  │
    │   #FF5733    │  ← BOTTOM (bright)
    └──────────────┘
    
    A2 TAG        A3 TAG        A4 TAG
┌────────┐    ┌────────┐    ┌────────┐
│ neutral│    │ neutral│    │ neutral│  ← Dim
│ ░░░░░░ │    │ ░░░░░░ │    │ ░░░░░░ │
│ ░░░░░░ │    │ ░░░░░░ │    │ ░░░░░░ │
│ neutral│    │ neutral│    │ neutral│  ← Dim
└────────┘    └────────┘    └────────┘
```

## Segment Count Comparison

### Traditional Layout
```
Segments Used: 15/16 on DigQuad
┌─────────────────────────────────────┐
│ Seg 0: Progress (1)                 │
│ Seg 1: Status (1)                   │
│ Seg 2-5: AMS Tray (4)              │
│ Seg 6-13: Tag Tops Individual (8)   │ ✓ Individual
│ Seg 14: Tag Bottoms + Hygro (1)    │ ❌ All combined
│ Seg 15: Spare                       │
└─────────────────────────────────────┘
Total: 15 segments
Limitation: Cannot split tag bottoms
```

### Preset-Based Layout (Example: Preset 50)
```
Segments Used: 14/16 on DigQuad
┌─────────────────────────────────────┐
│ Seg 0: Progress (1)                 │
│ Seg 1: Status (1)                   │
│ Seg 2-5: AMS Tray (4)              │
│ Seg 6: A1 Tag TOP (1)              │ ✓ Active tag
│ Seg 7: A1 Tag BOTTOM (1)           │ ✓ Active tag
│ Seg 8: A2-A4 Tops Combined (1)     │ ⚠ Inactive combined
│ Seg 9: B1-B4 Tops Combined (1)     │ ⚠ Inactive combined
│ Seg 10: A2-A4 Bottoms Combined (1) │ ⚠ Inactive combined
│ Seg 11: B1-B4 Bottoms Combined (1) │ ⚠ Inactive combined
│ Seg 12-13: Hygrometers (2)         │
│ Seg 14-15: Spare                    │
└─────────────────────────────────────┘
Total: 14 segments
Benefit: Active tag has BOTH top and bottom!
Trade-off: Inactive tags combined (acceptable)
```

## The "Magic" of Preset-Based Segments

```
┌───────────────────────────────────────────────────────────┐
│                                                           │
│  WLED Presets Can Save Two Things:                       │
│                                                           │
│  1. COLORS/EFFECTS (Traditional use)                     │
│     ├─ Preset 1: All red                                 │
│     ├─ Preset 2: All blue breathing                      │
│     └─ Preset 3: Rainbow chase                           │
│                                                           │
│  2. SEGMENT DEFINITIONS (Advanced use) ⭐                 │
│     ├─ Which LEDs belong to which segment                │
│     ├─ How many segments exist                           │
│     └─ The arrangement of segments                       │
│                                                           │
│  By enabling "Save segment bounds" when saving a preset, │
│  you store the LAYOUT itself, not just appearance!       │
│                                                           │
└───────────────────────────────────────────────────────────┘

This means you can have:

  Preset 2:  Base layout     (8 tag tops individual)
  Preset 50: A1 optimized    (A1 top+bottom split)
  Preset 51: A2 optimized    (A2 top+bottom split)
  Preset 52: A3 optimized    (A3 top+bottom split)
  ...

Each preset has a DIFFERENT 16-segment layout!
Switch between them to adapt to the scenario!
```

## LED Strip Physical Layout

```
AMS 1 TAG STRIP (Physical LED Strip)
═══════════════════════════════════════════════════════════

LED 442 →──────────┬──────────┬──────────┬──────────→ LED 501
           A1 Top    A2 Top    A3 Top     A4 Top
          (442-453) (454-465) (466-477)  (490-501)
              ↓         ↓         ↓          ↓
           12 LEDs   12 LEDs   12 LEDs   12 LEDs

LED 501 ←──────────┬──────────┬──────────┬──────────← LED 562
         A4 Bottom  A3 Bottom  A2 Bottom  A1 Bottom
         (551-562)  (526-538)  (514-525)  (502-513)
             ↓          ↓          ↓          ↓
          12 LEDs    13 LEDs    12 LEDs    12 LEDs


TRADITIONAL LAYOUT (Base Preset 2):
┌──────────────────────────────────────────────────────────┐
│ Segment 6: A1 Top (442-453)     ✓ Individual            │
│ Segment 7: A2 Top (454-465)     ✓ Individual            │
│ Segment 8: A3 Top (466-477)     ✓ Individual            │
│ Segment 9: A4 Top (490-501)     ✓ Individual            │
│ Segment 14: ALL Bottoms (502-562) ❌ All combined       │
└──────────────────────────────────────────────────────────┘


PRESET 50 LAYOUT (A1 Active):
┌──────────────────────────────────────────────────────────┐
│ Segment 6: A1 Top (442-453)        ✓ ACTIVE             │
│ Segment 7: A1 Bottom (502-513)     ✓ ACTIVE             │
│ Segment 8: A2-A4 Tops (454-501)    ⚠ Combined           │
│ Segment 10: A2-A4 Bottoms (514-562) ⚠ Combined          │
└──────────────────────────────────────────────────────────┘
```

## Automation Flow Diagram

```
                        START
                          │
                          ▼
              ┌───────────────────────┐
              │ Active Tray Changed?  │
              └───────────┬───────────┘
                          │ YES
                          ▼
              ┌───────────────────────┐
              │ Printing?             │
              └───────────┬───────────┘
                          │ YES
                          ▼
              ┌───────────────────────────────┐
              │ Map Tray → Preset ID          │
              │ Tray 1 → Preset 50            │
              │ Tray 2 → Preset 51            │
              │ ... etc                       │
              └───────────┬───────────────────┘
                          ▼
              ┌───────────────────────────────┐
              │ Get Filament Color            │
              │ from Spoolman                 │
              └───────────┬───────────────────┘
                          ▼
              ┌───────────────────────────────┐
              │ Load Preset Configuration     │
              │ (Segments reconfigure)        │
              └───────────┬───────────────────┘
                          ▼
              ┌───────────────────────────────┐
              │ Wait 500ms                    │
              │ (Let segments reconfigure)    │
              └───────────┬───────────────────┘
                          ▼
              ┌───────────────────────────────┐
              │ Set Segment 6 (Top)           │
              │ to Filament Color             │
              └───────────┬───────────────────┘
                          ▼
              ┌───────────────────────────────┐
              │ Set Segment 7 (Bottom)        │
              │ to Filament Color             │
              └───────────┬───────────────────┘
                          ▼
              ┌───────────────────────────────┐
              │ Set Segments 8-11 (Inactive)  │
              │ to Neutral Color              │
              └───────────┬───────────────────┘
                          ▼
                        DONE
          
          Both top and bottom of active tag
          are now highlighted with filament color!
```

## Key Insight Visualization

```
┌───────────────────────────────────────────────────────────┐
│                                                           │
│              THE KEY INSIGHT                              │
│                                                           │
│  You're NOT limited to 16 segments TOTAL                 │
│                                                           │
│  You're limited to 16 segments AT ONE TIME               │
│                                                           │
│  By switching preset configurations, you can have        │
│  different sets of 16 segments for different scenarios!  │
│                                                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │ Preset 50   │  │ Preset 51   │  │ Preset 52   │     │
│  │ (16 segs)   │  │ (16 segs)   │  │ (16 segs)   │     │
│  │             │  │             │  │             │     │
│  │ A1 top+btm  │  │ A2 top+btm  │  │ A3 top+btm  │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
│                                                           │
│  Switch between them based on active tray!               │
│                                                           │
│  Result: Effectively MORE than 16 segments by using      │
│          context-aware layouts!                          │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

## Summary

```
┌─────────────────────────────────────────────────────────┐
│                   TRADITIONAL                            │
│                                                          │
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐                           │
│  │ A1 │ │ A2 │ │ A3 │ │ A4 │  ← Top only (individual) │
│  │ ✓  │ │ ✓  │ │ ✓  │ │ ✓  │                          │
│  └────┘ └────┘ └────┘ └────┘                           │
│  └──────────────────────────┘                           │
│         ALL BOTTOMS ❌ (combined)                        │
│                                                          │
│  Limitation: Can't highlight both top and bottom        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                 PRESET-BASED                             │
│                                                          │
│  When A1 Active (Preset 50):                           │
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐                           │
│  │ A1 │ │ A2 │ │ A3 │ │ A4 │  ← Tops                  │
│  │ ✓✓ │ │ ⚠  │ │ ⚠  │ │ ⚠  │  (A1 split, others comb)│
│  │ ✓✓ │ │ ⚠  │ │ ⚠  │ │ ⚠  │  ← Bottoms              │
│  └────┘ └────┘ └────┘ └────┘  (A1 split, others comb) │
│                                                          │
│  Benefit: Full control of A1 top AND bottom! ✓         │
│  Trade-off: Other tags combined (but they're dim)      │
└─────────────────────────────────────────────────────────┘
```

---

**Visual Summary**: Preset-based segment configuration is like having multiple WLED configurations that you can switch between on demand, each optimized for a different scenario!
