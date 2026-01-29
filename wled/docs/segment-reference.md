# Segment Allocation Reference Card

Quick reference for WLED segment IDs and their purposes.

**Total System LEDs: 711**

For complete LED specifications, see [digquad-led-segments.md](../digquad-led-segments.md).
For function details, see [led-functions.md](../led-functions.md).
For scenario behaviors, see [light-scenarios.md](../light-scenarios.md).

## Digquad Controller - GPIO Pin Mapping

| GPIO Pin | Connected To | LED Type | LED Count | LED Range | Purpose |
|----------|--------------|----------|-----------|-----------|---------|
| 15 | Printer Front Door | COB 160 LED/m | 158 | 0-157 | Progress bar + status indicators |
| 1 | AMS 1 Lid/Spools | COB 160 LED/m | 140 | 158-297 | Spool illumination |
| 3 | AMS 2 Lid/Spools | COB 160 LED/m | 139 | 298-436 | Spool illumination |
| 16 | AMS 1 Tags + Hygro | Mini 2.7mm 160 LED/m | 136 | 437-572 | Tag/hygrometer indication |
| 4 | AMS 2 Tags + Hygro | Mini 2.7mm 160 LED/m | 138 | 573-710 | Tag/hygrometer indication |

**Total: 711 LEDs**

## Functional Zone Breakdown

### GPIO 15: Printer Front Door (158 LEDs)

| Zone | LED Range | Count | Primary Function |
|------|-----------|-------|------------------|
| Bottom | 0-49 | 50 | Print progress bar, animated progress |
| Left | 50-114 | 65 | Status indicator (pulsing green/flashing red) |
| Top | 115-157 | 43 | Status indicator (same as left) |

**Functions** (see [led-functions.md](../led-functions.md)):
- Bottom: Display print progress %, pause animation, completion flash
- Left/Top: Print status (pulsing soft green when printing, flashing red on error)

### GPIO 1: AMS 1 Lid/Spools (140 LEDs, Range: 158-297)

Detailed breakdown in [digquad-led-segments.md](../digquad-led-segments.md).

**Key Segments**:
- Top sections by tray (17, 12, 13, 13 LEDs)
- Side wall (25 LEDs)
- Bottom sections by tray (14, 13, 13, 14 LEDs)

**Functions**:
- Lighting of all spools (white)
- Indicator of current spool in use
- Error indication (spool load issue)
- Animation for loading/unloading spool

### GPIO 3: AMS 2 Lid/Spools (139 LEDs, Range: 298-436)

Similar to AMS 1, with additional heating animation support (AMS2 only).

### GPIO 16: AMS 1 Tags + Hygrometer (136 LEDs, Range: 437-572)

Complex layout including tags and hygrometer.

**Functions**:
- **Tag Top**: Color-match filament, highlight current use
- **Tag Bottom**: % filament left, desiccant warning (>X months), spool errors
- **Hygrometer**: Make visible, humidity warning (>X%)

### GPIO 4: AMS 2 Tags + Hygrometer (138 LEDs, Range: 573-710)

Similar to AMS 1 tags.

## Preset to Scenario Mapping

For complete scenario catalog, see [light-scenarios.md](../light-scenarios.md).

### Power & Connectivity States

| Preset | Name | Description | Key LEDs |
|--------|------|-------------|----------|
| 1 | Printer Offline | Dim amber | Door |
| 2 | Printer Idle | Soft blue breathing | All |
| 3 | Printer Busy | Medium white | All |

### Print Lifecycle States

| Preset | Name | Description | Key LEDs |
|--------|------|-------------|----------|
| 4 | Heating Bed | Orange pulse | Door |
| 5 | Heating Nozzle | Yellow pulse | Door |
| 6 | Bed Leveling | Blue pulse/chase | Door + Lid |
| 7 | Purge Line | Cyan pulse | Door |
| 8 | Printing | Green status + progress | Door bottom (progress), Door left/top (green), Tags (filament color) |
| 9 | Paused (User) | Yellow blink | All |
| 10 | Paused (Error) | Red strobe | Door, affected tray |
| 11 | Print Finished | Green pulse | All |

### Error & Warning States

| Preset | Name | Description | Key LEDs |
|--------|------|-------------|----------|
| 12 | Filament Runout | Red blink | Door, affected tag |
| 13 | Filament Jam | Orange strobe | AMS, tags |
| 14 | AMS Comm Error | Purple pulse | AMS |
| 15 | Temperature Error | Red strobe | All |
| 16 | Door Open | Bright white | Door, lid |

### AMS-Specific Scenarios

| Preset | Name | Description | Key LEDs |
|--------|------|-------------|----------|
| 17 | Filament Loading | Blue chase | AMS, active tag |
| 18 | Filament Unloading | Teal chase | AMS, tags |
| 19 | AMS Drying | Warm amber | AMS, hygrometer white |
| 20 | Humidity High | Red warning | Hygrometer |
| 21 | Humidity Normal | White | Hygrometer, AMS |
| 22 | Tray Selected | Filament color | Selected tag |
| 23 | Tray Feeding | Bright filament color | Active tag, tray |

## Color Codes

| Color | RGB Value | Hex | Usage |
|-------|-----------|-----|-------|
| White (Bright) | 255,255,255 | #FFFFFF | Active spools, maintenance |
| Warm White | 255,220,180 | #FFDCB4 | Inactive spools, idle |
| Green | 0,255,0 | #00FF00 | Normal status, success |
| Red | 255,0,0 | #FF0000 | Error, alert |
| Orange | 255,100,0 | #FF6400 | Active tag highlight |
| Yellow | 150,150,0 | #969600 | Upcoming tag |
| Blue | 100,150,255 | #6496FF | Idle breathing |
| Gray | 100,100,100 | #646464 | Inactive tags |

## Effect IDs (Common WLED Effects)

| Effect ID | Name | Usage in Presets |
|-----------|------|------------------|
| 0 | Solid | Most static segments |
| 1 | Breathing | Idle mode breathing |
| 2 | Blink | Error alerts |
| 3 | Wipe | Loading animations |
| 28 | Chase | Progress animations |

## AMS Tray to Segment Mapping

| AMS Unit | Tray # | Slot ID | Spool Segment (Digquad) | Tag Segment (Digquad) | Tag Segment (MagWLED) | Notes |
|----------|--------|---------|-------------------------|----------------------|----------------------|-------|
| AMS 1 | 1 | A1 | 4 | 8 | - | First unit, first slot |
| AMS 1 | 2 | A2 | 5 | 9 | - | First unit, second slot |
| AMS 1 | 3 | A3 | 6 | 10 | - | First unit, third slot |
| AMS 1 | 4 | A4 | 7 | 11 | - | First unit, fourth slot |
| AMS 2 | 5 | B1 | 12 | - | 0,4 | Second unit, first slot |
| AMS 2 | 6 | B2 | 13 | - | 1,5 | Second unit, second slot |
| AMS 2 | 7 | B3 | 14 | - | 2,6 | Second unit, third slot |
| AMS 2 | 8 | B4 | 15 | - | 3,7 | Second unit, fourth slot |

## Home Assistant Sensor Mapping

| Bambu Lab Sensor | WLED Action | Example Value | Preset |
|------------------|-------------|---------------|--------|
| `sensor.bambu_lab_x1c_current_stage` | Trigger lifecycle preset | "printing", "idle", "complete" | 2-11 |
| `sensor.bambu_lab_x1c_print_progress` | Update progress bar | 0-100 (percentage) | Dynamic |
| `sensor.bambu_lab_x1c_active_tray` | Highlight active tray/tag | 1-8 (tray number) | 22-23 |
| `sensor.bambu_lab_x1c_hms_errors` | Trigger error preset | Error list or count | 10, 12-15 |
| `sensor.bambu_lab_x1c_chamber_temperature` | Temperature warnings | Temperature value | 28-29 |
| AMS humidity sensors | Hygrometer warnings | Humidity percentage | 20-21 |

## GPIO Output Reference

| GPIO Pin | Purpose | LED Count | Typical Brightness | Notes |
|----------|---------|-----------|-------------------|-------|
| 15 | Printer Door | 158 | 30-50% | Progress + status |
| 1 | AMS 1 Lid | 140 | 30-40% | Spool illumination |
| 3 | AMS 2 Lid | 139 | 30-40% | Spool illumination |
| 16 | AMS 1 Tags | 136 | 40-60% | Tag highlighting |
| 4 | AMS 2 Tags | 138 | 40-60% | Tag highlighting |

**Power Management:**
- Typical usage: 30-50% brightness with mixed colors
- Estimated current: 12-21A @ 5V
- Power injection recommended for each GPIO
- Monitor actual draw during operation

## Quick Command Reference

### WLED HTTP API Examples

**Set Preset:**
```bash
curl -X POST http://digquad.local/win&PL=1
```

**Set Segment Color:**
```bash
curl -X POST http://digquad.local/json/state -H "Content-Type: application/json" -d '{"seg":[{"id":4,"col":[[255,255,255]]}]}'
```

**Turn On/Off:**
```bash
curl -X POST http://digquad.local/win&T=1  # Toggle
curl -X POST http://digquad.local/win&T=0  # Off
```

**Set Brightness:**
```bash
curl -X POST http://digquad.local/win&A=128  # 0-255
```

### Home Assistant Service Calls

**Apply Preset:**
```yaml
service: light.turn_on
target:
  entity_id: light.digquad
data:
  preset: 1
```

**Set Segment Color:**
```yaml
service: wled.effect
target:
  entity_id: light.digquad
data:
  segment_id: 4
  color_primary: [255, 255, 255]
```

## Troubleshooting Quick Reference

| Problem | Check | Solution |
|---------|-------|----------|
| No lights | Power supply | Verify 5V and ground, check connections |
| Wrong colors | LED type | Change to GRB or BGR in WLED config |
| Partial lighting | LED counts | Verify total count matches actual (711) |
| Flickering | Power | Add power injection at each GPIO |
| Preset not working | Preset ID | Check preset exists and is configured |
| Automation not triggering | Entity ID | Verify correct entity names in HA |
| Progress bar not updating | LED range | Verify bottom segment is 0-50 |
| Tags wrong color | Filament data | Check Spoolman integration |
| Hygrometer not showing | LED range | Verify hygrometer LEDs in tag ranges |

## Notes

- **LED ranges are ACTUAL** - 711 total LEDs documented in digquad-led-segments.md
- **GPIO pins are SPECIFIED** - Use pins 15, 1, 3, 16, 4
- **Functions are DEFINED** - See led-functions.md for zone purposes
- **Scenarios are CATALOGED** - See light-scenarios.md for all 33+ behaviors
- **Always backup** configurations before making changes
- **Test incrementally** - One GPIO at a time
- **Start simple** and add complexity gradually

## Print This Page

This reference card is designed to be printed and kept near your printer for quick reference during setup and troubleshooting.

---

**Version:** 1.1 (Updated with actual specifications)  
**Total LEDs:** 711  
**Last Updated:** 2024  
**Repository:** https://github.com/rsocko/hass-bambulab-config
