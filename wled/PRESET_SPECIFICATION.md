# WLED Preset Specification

## Overview

This document provides a comprehensive specification of all WLED presets for the Bambu Lab printer LED system. Each preset defines which segments are active and what colors/effects they display for specific printer scenarios.

**IMPORTANT: Two-Controller Setup**
- **DigQuad Controller**: Controls 5 LED strips (711 LEDs) with 15 segments (0-14), 1 spare
- **MagWLED Controller**: Controls 1 LED strip (~30 LEDs) with 1 segment (0), 15 spare

Presets must coordinate actions across BOTH controllers when needed. In Home Assistant, you'll typically need to call services for both `light.digquad` and `light.magwled` entities.

## Segment Reference

### Complete Segment Allocation (15 segments on DigQuad + 1 on MagWLED)

#### DigQuad Controller (15 segments used, 1 spare)

| Segment ID | Name | GPIO | LED Range | Count | Purpose |
|------------|------|------|-----------|-------|---------|
| 0 | Front Door Bottom | 15 | 0-49 | 50 | Progress bar |
| 1 | Front Door Left+Top | 15 | 50-157 | 108 | Status indicator (merged) |
| 2 | AMS 1 Tray Top | 1 | 158-215 | 58 | Combined tray lighting |
| 3 | AMS 1 Tray Bottom | 1 | 241-297 | 57 | Neutral background |
| 4 | AMS 2 Tray Top | 3 | 298-357 | 60 | Combined tray lighting |
| 5 | AMS 2 Tray Bottom | 3 | 382-436 | 55 | Neutral background |
| 6 | AMS 1 Tag A1 Top | 16 | 442-453 | 12 | Tag for tray A1 |
| 7 | AMS 1 Tag A2 Top | 16 | 454-465 | 12 | Tag for tray A2 |
| 8 | AMS 1 Tag A3 Top | 16 | 466-477 | 12 | Tag for tray A3 |
| 9 | AMS 1 Tag A4 Top | 16 | 490-501 | 12 | Tag for tray A4 |
| 10 | AMS 2 Tag B1 Top | 4 | 579-591 | 13 | Tag for tray B1 |
| 11 | AMS 2 Tag B2 Top | 4 | 592-605 | 14 | Tag for tray B2 |
| 12 | AMS 2 Tag B3 Top | 4 | 606-619 | 14 | Tag for tray B3 |
| 13 | AMS 2 Tag B4 Top | 4 | 632-643 | 12 | Tag for tray B4 |
| 14 | Neutral Backgrounds | 16, 4 | Various | ~125 | Hygrometers + tag bottoms (neutral) |

**Total: 15 segments on DigQuad, 1 segment spare**

#### MagWLED Controller (1 segment used, 15 spare)

| Segment ID | Name | GPIO | LED Range | Count | Purpose |
|------------|------|------|-----------|-------|---------|
| 0 | Interior Lid Light | 2 | 0-~30 | ~30 | Simple interior lighting |

**Total: 1 segment on MagWLED, 15 segments available for future use**

**System Total**: 16 active segments (15 on DigQuad + 1 on MagWLED)

## Color Palette

| Color Name | RGB | Hex | Usage |
|------------|-----|-----|-------|
| Soft White | 255, 220, 180 | #FFDCB4 | Neutral backgrounds, idle |
| Bright White | 255, 255, 255 | #FFFFFF | Active lighting, visibility |
| Green | 0, 255, 0 | #00FF00 | Printing status, success |
| Soft Green | 100, 255, 100 | #64FF64 | Idle breathing |
| Blue | 100, 150, 255 | #6496FF | Cooling, leveling |
| Cyan | 0, 255, 255 | #00FFFF | Purge line |
| Yellow | 255, 255, 0 | #FFFF00 | Paused (user) |
| Orange | 255, 100, 0 | #FF6400 | Warnings, heating |
| Red | 255, 0, 0 | #FF0000 | Errors, critical alerts |
| Purple | 200, 0, 255 | #C800FF | AMS comm error |
| Amber | 255, 180, 0 | #FFB400 | Offline, drying |
| Teal | 0, 200, 200 | #00C8C8 | Unloading |

## Effect Reference

| Effect ID | Effect Name | Usage |
|-----------|-------------|-------|
| 0 | Solid | Static colors, stable states |
| 1 | Breathe | Idle breathing, soft pulse |
| 2 | Blink | Warnings, errors |
| 3 | Wipe | Loading animations |
| 12 | Chase | Progress animation |
| 28 | Scanner | Active scanning/loading |

---

## Preset Definitions

### Category 1: Power & Connectivity States

#### Preset 1: Printer Offline
**Scenario**: Printer is powered off or unreachable by Home Assistant  
**Active Segments**: DigQuad Segment 1 (Front Door Left+Top), MagWLED Segment 0 (Lid) off  
**Trigger**: `sensor.printer_status == "offline"`

**DigQuad Segments:**
| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Off | - | 0% | Progress bar off |
| 1 | Amber | Solid | 30% | Dim amber indicator |
| 2-14 | Off | - | 0% | All AMS off |

**MagWLED Segments:**
| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Off | - | 0% | Interior lid off |

#### Preset 2: Printer Idle
**Scenario**: Printer is powered on but not printing  
**Active Segments**: All  
**Trigger**: `sensor.printer_stage == "idle"`

**DigQuad Segments:**
| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Off | - | 0% | No progress |
| 1 | Soft Green | Breathe | 30% | Gentle breathing |
| 2 | Soft White | Solid | 30% | AMS 1 top dim |
| 3 | Soft White | Solid | 25% | AMS 1 bottom neutral |
| 4 | Soft White | Solid | 30% | AMS 2 top dim |
| 5 | Soft White | Solid | 25% | AMS 2 bottom neutral |
| 6-13 | Soft White | Solid | 25% | All tags dim |
| 14 | Soft White | Solid | 25% | Backgrounds neutral |

**MagWLED Segments:**
| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Soft White | Solid | 40% | Interior lid on |

---

### Category 2: Print Lifecycle States

#### Preset 3: Heating Bed
**Scenario**: Bed warming before print  
**Active Segments**: 0, 2  
**Trigger**: `sensor.printer_stage == "heating_bed"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Orange | Solid | 50% | Lid orange |
| 1 | Off | - | 0% | No progress yet |
| 2 | Orange | Breathe | 60% | Pulsing orange |
| 3-15 | Off | - | 0% | AMS off during heat |

#### Preset 4: Heating Nozzle  
**Scenario**: Nozzle warming before print  
**Active Segments**: 0, 2  
**Trigger**: `sensor.printer_stage == "heating_nozzle"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Yellow | Solid | 50% | Lid yellow |
| 1 | Off | - | 0% | No progress yet |
| 2 | Yellow | Breathe | 60% | Pulsing yellow |
| 3-15 | Off | - | 0% | AMS off during heat |

#### Preset 5: Bed Leveling
**Scenario**: Printer probing or scanning bed  
**Active Segments**: 0, 2, 3, 5  
**Trigger**: `sensor.printer_stage == "leveling"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Blue | Breathe | 50% | Lid pulsing blue |
| 1 | Off | - | 0% | No progress yet |
| 2 | Blue | Chase | 60% | Chase effect on door |
| 3 | Blue | Solid | 40% | AMS 1 blue |
| 4 | Soft White | Solid | 20% | Neutral |
| 5 | Blue | Solid | 40% | AMS 2 blue |
| 6 | Soft White | Solid | 20% | Neutral |
| 7-15 | Off | - | 0% | Tags off |

#### Preset 6: Purge Line
**Scenario**: Printer purging or wiping nozzle  
**Active Segments**: 0, 2  
**Trigger**: `sensor.printer_stage == "purging"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Cyan | Solid | 50% | Lid cyan |
| 1 | Cyan | Wipe | 50% | Wiping effect |
| 2 | Cyan | Breathe | 50% | Pulsing cyan |
| 3-15 | Off | - | 0% | AMS off |

#### Preset 7: Printing (Base - No Active Tray)
**Scenario**: Actively printing (no filament indicator yet)  
**Active Segments**: All  
**Trigger**: `sensor.printer_stage == "printing"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Bright White | Solid | 80% | Lid bright |
| 1 | Green | Solid | Dynamic | Progress bar (% based) |
| 2 | Green | Solid | 60% | Status green |
| 3 | Soft White | Solid | 40% | AMS 1 top lit |
| 4 | Soft White | Solid | 25% | Neutral |
| 5 | Soft White | Solid | 40% | AMS 2 top lit |
| 6 | Soft White | Solid | 25% | Neutral |
| 7-14 | Soft White | Solid | 30% | All tags dim |
| 15 | Soft White | Solid | 25% | Neutral backgrounds |

**Note**: This is the base printing preset. Specific active tray presets follow (Presets 8-15).

#### Presets 8-15: Printing with Active Tray (A1, A2, A3, A4, B1, B2, B3, B4)

Each preset represents printing with a specific active tray. The preset is identical to Preset 7 except for the highlighted active tag.

##### Preset 8: Printing - Active Tray A1
**Active Tray**: AMS 1, Tray 1 (A1)  
**Trigger**: `sensor.printer_stage == "printing" AND sensor.active_tray == "1"`

Inherits Preset 7, with these changes:
| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 7 | Filament Color | Solid | 80% | ⭐ A1 tag highlighted |
| 8-10 | Soft White | Solid | 30% | Other AMS 1 tags dim |

##### Preset 9: Printing - Active Tray A2
**Active Tray**: AMS 1, Tray 2 (A2)  
**Trigger**: `sensor.active_tray == "2"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 7 | Soft White | Solid | 30% | A1 dim |
| 8 | Filament Color | Solid | 80% | ⭐ A2 tag highlighted |
| 9-10 | Soft White | Solid | 30% | Other AMS 1 tags dim |

##### Preset 10: Printing - Active Tray A3
**Active Tray**: AMS 1, Tray 3 (A3)  
**Trigger**: `sensor.active_tray == "3"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 7-8 | Soft White | Solid | 30% | A1-A2 dim |
| 9 | Filament Color | Solid | 80% | ⭐ A3 tag highlighted |
| 10 | Soft White | Solid | 30% | A4 dim |

##### Preset 11: Printing - Active Tray A4
**Active Tray**: AMS 1, Tray 4 (A4)  
**Trigger**: `sensor.active_tray == "4"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 7-9 | Soft White | Solid | 30% | A1-A3 dim |
| 10 | Filament Color | Solid | 80% | ⭐ A4 tag highlighted |

##### Preset 12: Printing - Active Tray B1
**Active Tray**: AMS 2, Tray 1 (B1)  
**Trigger**: `sensor.active_tray == "5"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 11 | Filament Color | Solid | 80% | ⭐ B1 tag highlighted |
| 12-14 | Soft White | Solid | 30% | Other AMS 2 tags dim |

##### Preset 13: Printing - Active Tray B2
**Active Tray**: AMS 2, Tray 2 (B2)  
**Trigger**: `sensor.active_tray == "6"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 11 | Soft White | Solid | 30% | B1 dim |
| 12 | Filament Color | Solid | 80% | ⭐ B2 tag highlighted |
| 13-14 | Soft White | Solid | 30% | Other AMS 2 tags dim |

##### Preset 14: Printing - Active Tray B3
**Active Tray**: AMS 2, Tray 3 (B3)  
**Trigger**: `sensor.active_tray == "7"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 11-12 | Soft White | Solid | 30% | B1-B2 dim |
| 13 | Filament Color | Solid | 80% | ⭐ B3 tag highlighted |
| 14 | Soft White | Solid | 30% | B4 dim |

##### Preset 15: Printing - Active Tray B4
**Active Tray**: AMS 2, Tray 4 (B4)  
**Trigger**: `sensor.active_tray == "8"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 11-13 | Soft White | Solid | 30% | B1-B3 dim |
| 14 | Filament Color | Solid | 80% | ⭐ B4 tag highlighted |

#### Preset 16: Print Paused (User)
**Scenario**: User manually paused print  
**Trigger**: `sensor.printer_stage == "paused"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Yellow | Solid | 60% | Lid yellow |
| 1 | Yellow | Solid | Dynamic | Paused progress bar |
| 2 | Yellow | Blink | 60% | Blinking yellow |
| 3-15 | Yellow | Solid | 40% | All yellow |

#### Preset 17: Print Paused (Error)
**Scenario**: Print paused due to error  
**Trigger**: `sensor.hms_errors.count > 0 AND sensor.printer_stage == "paused"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Red | Solid | 80% | Lid red |
| 1 | Red | Blink | 80% | Error on progress bar |
| 2 | Red | Blink | 80% | Fast blink |
| 3-15 | Red | Solid | 60% | All red alert |

**Note**: If error is tray-specific, affected tag can be made brighter or strobe faster.

#### Preset 18: Print Finished
**Scenario**: Print completed successfully  
**Trigger**: `sensor.printer_stage == "finish"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Green | Breathe | 80% | Celebration effect |
| 1 | Green | Solid | 100% | Full progress bar |
| 2 | Green | Breathe | 80% | Pulsing green |
| 3-15 | Green | Solid | 50% | Success all around |

---

### Category 3: Error & Warning States

#### Preset 19: Filament Runout
**Scenario**: AMS tray reports runout  
**Trigger**: `sensor.ams_tray_X_state == "runout"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Red | Solid | 80% | Lid red |
| 1 | Red | Solid | Dynamic | Progress frozen |
| 2 | Red | Blink | 80% | Fast red blink |
| 3-6 | Red | Solid | 60% | AMS red |
| 7-14 | Red | Solid | 80% | **Affected tag BRIGHT** |
| 15 | Red | Solid | 40% | All red |

**Dynamic Behavior**: The specific tag segment (7-14) for the empty tray should be set to maximum brightness (100%) and potentially strobe effect.

#### Preset 20: Filament Tangle/Jam
**Scenario**: AMS detects abnormal resistance  
**Trigger**: `sensor.ams_error_type == "tangle"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Orange | Solid | 70% | Lid orange |
| 1 | Orange | Solid | Dynamic | Progress frozen |
| 2 | Orange | Blink | 70% | Orange blink |
| 3-6 | Orange | Blink | 60% | AMS strobe |
| 7-14 | Orange | Solid | 70% | Tags orange |
| 15 | Orange | Solid | 40% | Backgrounds |

#### Preset 21: AMS Communication Error
**Scenario**: AMS offline or not responding  
**Trigger**: `sensor.ams_status == "offline"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Purple | Solid | 60% | Lid purple |
| 1 | Off | - | 0% | No progress |
| 2 | Purple | Breathe | 60% | Pulsing purple |
| 3-6 | Purple | Breathe | 60% | AMS pulsing |
| 7-14 | Off | - | 0% | Tags off (no comm) |
| 15 | Off | - | 0% | Backgrounds off |

#### Preset 22: Temperature Error
**Scenario**: Nozzle or bed temperature fault  
**Trigger**: `sensor.temperature_error == true`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Red | Blink | 100% | Lid strobe |
| 1 | Red | Blink | 100% | All red strobe |
| 2 | Red | Blink | 100% | Critical alert |
| 3-15 | Red | Blink | 80% | All red strobe |

#### Preset 23: Door Open During Print
**Scenario**: Door opened while printing  
**Trigger**: `sensor.door_state == "open" AND sensor.printer_stage == "printing"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Bright White | Solid | 100% | Max brightness |
| 1 | Bright White | Solid | Dynamic | Progress frozen |
| 2 | Bright White | Solid | 100% | Door area bright |
| 3-15 | Off | - | 0% | AMS off |

---

### Category 4: AMS-Specific Scenarios

#### Preset 24: Filament Loading
**Scenario**: AMS loading filament into printer  
**Trigger**: `sensor.ams_action == "loading"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Blue | Solid | 50% | Lid blue |
| 1 | Blue | Wipe | 50% | Loading animation |
| 2 | Blue | Solid | 50% | Door blue |
| 3 or 5 | Blue | Chase | 60% | Active AMS chase |
| 4 or 6 | Blue | Solid | 40% | Bottom blue |
| Active Tag | Blue | Solid | 80% | **Active tag bright** |
| Other Tags | Soft White | Solid | 30% | Dim |
| 15 | Blue | Solid | 30% | Backgrounds |

**Dynamic Behavior**: Only the AMS unit performing the load (3 or 5) and its active tag (7-14) are highlighted.

#### Preset 25: Filament Unloading
**Scenario**: AMS retracting filament  
**Trigger**: `sensor.ams_action == "unloading"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Teal | Solid | 50% | Lid teal |
| 1 | Teal | Wipe | 50% | Unloading animation |
| 2 | Teal | Solid | 50% | Door teal |
| 3 or 5 | Teal | Chase | 60% | Active AMS reverse chase |
| 4 or 6 | Teal | Solid | 40% | Bottom teal |
| Active Tag | Teal | Solid | 80% | **Active tag bright** |
| Other Tags | Soft White | Solid | 30% | Dim |
| 15 | Teal | Solid | 30% | Backgrounds |

#### Preset 26: AMS Drying Mode (AMS 2 Only)
**Scenario**: AMS heater active (AMS 2 Pro)  
**Trigger**: `sensor.ams2_heater == "on"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Amber | Solid | 40% | Lid warm |
| 1 | Off | - | 0% | No print |
| 2 | Amber | Solid | 30% | Door warm |
| 3-4 | Soft White | Solid | 30% | AMS 1 normal |
| 5 | Amber | Solid | 60% | **AMS 2 warm amber** |
| 6 | Amber | Solid | 50% | AMS 2 bottom |
| 7-10 | Soft White | Solid | 30% | AMS 1 tags normal |
| 11-14 | Amber | Solid | 40% | AMS 2 tags amber |
| 15 | Bright White | Solid | 60% | **Hygrometer bright** |

#### Preset 27: Humidity High (⚠️ Degraded)
**Scenario**: Hygrometer reading above threshold  
**Trigger**: `sensor.ams_humidity > 60`

**⚠️ LIMITATION**: Cannot individually control each AMS hygrometer since they share segment 15.

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Soft White | Solid | 40% | Lid normal |
| 1 | Off | - | 0% | No print |
| 2 | Soft White | Solid | 30% | Door normal |
| 3 or 5 | Red | Breathe | 60% | **Affected AMS pulse** |
| 4 or 6 | Soft White | Solid | 30% | Other areas normal |
| 7-14 | Soft White | Solid | 30% | Tags normal |
| 15 | Red | Blink | 80% | **Hygrometer warning** |

**Workaround**: Use affected AMS tray top (segment 3 or 5) to pulse red to indicate WHICH AMS has high humidity.

#### Preset 28: Humidity Normal
**Scenario**: Hygrometer reading normal  
**Trigger**: `sensor.ams_humidity < 60`

This is essentially the same as Preset 2 (Idle).

---

### Category 5: Maintenance & Utility States

#### Preset 29: Cooling Down
**Scenario**: Printer cooling after print  
**Trigger**: `sensor.printer_stage == "cooling"`

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Blue | Breathe | 50% | Cooling indicator |
| 1 | Green | Solid | 100% | Completed progress |
| 2 | Blue | Breathe | 50% | Cooling pulse |
| 3-15 | Blue | Solid | 30% | All cooling |

#### Preset 30: Chamber Light (Manual)
**Scenario**: User toggles chamber light  
**Trigger**: Manual button press

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0 | Bright White | Solid | 100% | Max visibility |
| 1 | Off | - | 0% | No progress |
| 2 | Bright White | Solid | 80% | Door lit |
| 3-15 | Bright White | Solid | 80% | All lit for visibility |

#### Preset 31: Night Mode
**Scenario**: Quiet hours  
**Trigger**: Time-based or manual

| Segment | Color | Effect | Brightness | Notes |
|---------|-------|--------|------------|-------|
| 0-15 | Off | - | 0% | All off OR very dim warm white (10%) |

---

## Preset Summary Table

| Preset # | Name | Active Segments | Key Trigger | Segment Complexity |
|----------|------|----------------|-------------|-------------------|
| 1 | Printer Offline | 2 | Status offline | Low |
| 2 | Printer Idle | All | Status idle | Low |
| 3 | Heating Bed | 0, 2 | Stage heating_bed | Low |
| 4 | Heating Nozzle | 0, 2 | Stage heating_nozzle | Low |
| 5 | Bed Leveling | 0, 2, 3, 5 | Stage leveling | Medium |
| 6 | Purge Line | 0, 1, 2 | Stage purging | Low |
| 7 | Printing (Base) | All | Stage printing | Medium |
| 8-15 | Printing + Active Tray | All | Active tray 1-8 | **Complex** |
| 16 | Print Paused (User) | All | Stage paused | Low |
| 17 | Print Paused (Error) | All | Errors + paused | Low |
| 18 | Print Finished | All | Stage finish | Low |
| 19 | Filament Runout | All | Tray runout | **Dynamic** |
| 20 | Filament Jam | All | AMS error tangle | Medium |
| 21 | AMS Comm Error | 0-6 | AMS offline | Low |
| 22 | Temperature Error | All | Temp error | Low |
| 23 | Door Open | 0-2 | Door open | Low |
| 24 | Filament Loading | Dynamic | AMS loading | **Complex** |
| 25 | Filament Unloading | Dynamic | AMS unloading | **Complex** |
| 26 | AMS Drying | 5, 6, 11-15 | AMS2 heater on | Medium |
| 27 | Humidity High | Dynamic | Humidity > 60 | Medium (⚠️) |
| 28 | Humidity Normal | All | Humidity < 60 | Low |
| 29 | Cooling Down | All | Stage cooling | Low |
| 30 | Chamber Light | All | Manual | Low |
| 31 | Night Mode | None | Manual/Time | Low |

**Total Presets: 31+**

---

## Active Tray Scenario Matrix

### All Possible Active Tray Scenarios

Since only ONE tray can be active at a time, we have 8 distinct scenarios:

| Scenario # | AMS | Tray | Slot ID | Segment to Highlight | Preset # |
|------------|-----|------|---------|---------------------|----------|
| 1 | AMS 1 | 1 | A1 | Segment 7 | 8 |
| 2 | AMS 1 | 2 | A2 | Segment 8 | 9 |
| 3 | AMS 1 | 3 | A3 | Segment 9 | 10 |
| 4 | AMS 1 | 4 | A4 | Segment 10 | 11 |
| 5 | AMS 2 | 1 | B1 | Segment 11 | 12 |
| 6 | AMS 2 | 2 | B2 | Segment 12 | 13 |
| 7 | AMS 2 | 3 | B3 | Segment 13 | 14 |
| 8 | AMS 2 | 4 | B4 | Segment 14 | 15 |

**Implementation Note**: In Home Assistant automation, you can use a single template automation that:
1. Detects `sensor.active_tray` value (1-8)
2. Calls the appropriate preset (8-15)
3. Passes the filament color from Spoolman integration

---

## Implementation Notes

### Filament Color Dynamic Insertion

For presets 8-15 (Printing with Active Tray), the "Filament Color" should be dynamically retrieved from:
- **Spoolman Integration**: `sensor.spoolman_spool_X_color_hex`
- **Bambu Lab Integration**: `sensor.bambu_tray_X_color` (if available)

Example Home Assistant automation:
```yaml
- service: wled.preset
  data:
    preset: 8
    segment_id: 7
    color_primary: "{{ state_attr('sensor.spoolman_spool_1', 'color_hex') }}"
```

### Progress Bar Dynamic Update

Segment 1 (Progress Bar) should be updated in real-time based on print progress:
```yaml
- service: wled.effect
  data:
    segment_id: 1
    color_primary: [0, 255, 0]
    length: "{{ (states('sensor.print_progress') | int * 50 / 100) | int }}"
```

### Segment Limitation Workarounds

#### Workaround 1: Humidity Warning
Since both hygrometers share segment 15, use the affected AMS tray top (segment 3 or 5) to pulse red to indicate which AMS has the humidity issue.

#### Workaround 2: Filament Remaining
Cannot show on tag bottoms (segment 15 is combined). Alternative: Use tag top brightness/intensity to indicate level:
- 100% = Full spool
- 75% = 3/4 full
- 50% = Half full
- 25% = Low (< 25%)
- Blinking = Critical (< 10%)

#### Workaround 3: Desiccant Warning
Cannot show individually on tag bottoms. Alternative: Flash the tag top orange periodically when desiccant is old:
- Normal color for 5 seconds
- Flash orange for 1 second
- Repeat cycle

---

## Preset Testing Checklist

Use this checklist when implementing and testing presets:

### Basic Presets
- [ ] Preset 1: Printer Offline
- [ ] Preset 2: Printer Idle
- [ ] Preset 3: Heating Bed
- [ ] Preset 4: Heating Nozzle
- [ ] Preset 5: Bed Leveling
- [ ] Preset 6: Purge Line

### Printing Presets (Active Tray)
- [ ] Preset 7: Printing (Base)
- [ ] Preset 8: Printing - A1
- [ ] Preset 9: Printing - A2
- [ ] Preset 10: Printing - A3
- [ ] Preset 11: Printing - A4
- [ ] Preset 12: Printing - B1
- [ ] Preset 13: Printing - B2
- [ ] Preset 14: Printing - B3
- [ ] Preset 15: Printing - B4

### Pause/Finish Presets
- [ ] Preset 16: Paused (User)
- [ ] Preset 17: Paused (Error)
- [ ] Preset 18: Print Finished

### Error Presets
- [ ] Preset 19: Filament Runout
- [ ] Preset 20: Filament Jam
- [ ] Preset 21: AMS Comm Error
- [ ] Preset 22: Temperature Error
- [ ] Preset 23: Door Open

### AMS Presets
- [ ] Preset 24: Filament Loading
- [ ] Preset 25: Filament Unloading
- [ ] Preset 26: AMS Drying
- [ ] Preset 27: Humidity High
- [ ] Preset 28: Humidity Normal

### Utility Presets
- [ ] Preset 29: Cooling Down
- [ ] Preset 30: Chamber Light
- [ ] Preset 31: Night Mode

---

## Conclusion

This specification defines 31+ presets that cover all major printer scenarios while staying within the 16-segment limitation. The key design decisions are:

1. **Merged front door left+top** reduces from 3 to 2 segments
2. **Individual tag control** for all 8 trays (segments 7-14)
3. **Combined background lighting** (segment 15) for neutrality
4. **Dynamic preset switching** based on active tray (presets 8-15)
5. **Workarounds** for scenarios blocked by segment limits

Each preset can be tested incrementally and refined based on actual behavior and user preferences.
