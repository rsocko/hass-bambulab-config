# Segment Allocation Reference Card

Quick reference for WLED segment IDs and their purposes.

## Digquad Controller - Segment Map

| Segment ID | Name | Strip | Purpose | LED Range (Example) | Notes |
|------------|------|-------|---------|---------------------|-------|
| 0 | Interior Light | 1 | General interior illumination | 0-29 | Always on during printing |
| 1 | Printer Bottom | 2 | Print progress bar | 30-59 | Dynamic progress indicator |
| 2 | Printer Left | 2 | Status indicator | 60-89 | Green=good, Red=error |
| 3 | Printer Top | 2 | Status indicator | 90-119 | Green=good, Red=error |
| 4 | AMS1 Spool A1 | 3 | Illuminate spool slot A1 | 120-134 | Bright when active |
| 5 | AMS1 Spool A2 | 3 | Illuminate spool slot A2 | 135-149 | Bright when active |
| 6 | AMS1 Spool A3 | 3 | Illuminate spool slot A3 | 150-164 | Bright when active |
| 7 | AMS1 Spool A4 | 3 | Illuminate spool slot A4 | 165-179 | Bright when active |
| 8 | AMS1 Tag A1 | 4 | Highlight tag for spool A1 | 180-189 | Orange when active |
| 9 | AMS1 Tag A2 | 4 | Highlight tag for spool A2 | 190-199 | Orange when active |
| 10 | AMS1 Tag A3 | 4 | Highlight tag for spool A3 | 200-209 | Orange when active |
| 11 | AMS1 Tag A4 | 4 | Highlight tag for spool A4 | 210-219 | Orange when active |
| 12 | AMS2 Spool B1 | 5 | Illuminate spool slot B1 | 220-234 | Bright when active |
| 13 | AMS2 Spool B2 | 5 | Illuminate spool slot B2 | 235-249 | Bright when active |
| 14 | AMS2 Spool B3 | 5 | Illuminate spool slot B3 | 250-264 | Bright when active |
| 15 | AMS2 Spool B4 | 5 | Illuminate spool slot B4 | 265-279 | Bright when active |

**Total Segments Used: 16 segments (IDs 0-15, using all available slots)**
**Total LEDs (Example): ~280**

## MagWLED Controller - Segment Map

### Full Layout (8 Segments)

| Segment ID | Name | Strip | Purpose | LED Range (Example) | Notes |
|------------|------|-------|---------|---------------------|-------|
| 0 | AMS2 Tag B1 Top | 6 | Top path for tag B1 | 0-9 | Orange when active |
| 1 | AMS2 Tag B2 Top | 6 | Top path for tag B2 | 10-19 | Orange when active |
| 2 | AMS2 Tag B3 Top | 6 | Top path for tag B3 | 20-29 | Orange when active |
| 3 | AMS2 Tag B4 Top | 6 | Top path for tag B4 | 30-39 | Orange when active |
| 4 | AMS2 Tag B1 Bottom | 6 | Bottom path for tag B1 | 40-49 | Orange when active |
| 5 | AMS2 Tag B2 Bottom | 6 | Bottom path for tag B2 | 50-59 | Orange when active |
| 6 | AMS2 Tag B3 Bottom | 6 | Bottom path for tag B3 | 60-69 | Orange when active |
| 7 | AMS2 Tag B4 Bottom | 6 | Bottom path for tag B4 | 70-79 | Orange when active |

**Total Segments Used: 8/16**
**Total LEDs (Example): ~80**

### Simplified Layout (4 Segments) - Alternative

| Segment ID | Name | Strip | Purpose | LED Range (Example) | Notes |
|------------|------|-------|---------|---------------------|-------|
| 0 | AMS2 Tag B1 | 6 | Complete tag B1 (top+bottom) | 0-19 | Simpler control |
| 1 | AMS2 Tag B2 | 6 | Complete tag B2 (top+bottom) | 20-39 | Simpler control |
| 2 | AMS2 Tag B3 | 6 | Complete tag B3 (top+bottom) | 40-59 | Simpler control |
| 3 | AMS2 Tag B4 | 6 | Complete tag B4 (top+bottom) | 60-79 | Simpler control |

**Total Segments Used: 4/16** (more room for expansion)

## Preset to Segment Mapping

### Digquad Presets

| Preset | Name | Active Segments | Description |
|--------|------|-----------------|-------------|
| 1 | Normal Printing | All (0-15) | Progress bar + green status + dim spools |
| 2 | Print Error | 0-3 | Interior + printer frame flash red |
| 3 | Print Complete | 0-3 | Interior green + frame celebration |
| 4 | Idle/Standby | All | Dim warm white + blue breathing |
| 5 | Maintenance | All | Bright white everywhere |
| 6 | AMS Loading | 0-7 | Dim printer + loading animation on AMS |
| 7 | Active Spool A1 | 4, 8 | Highlight spool A1 + tag A1 |
| 8 | Active Spool A2 | 5, 9 | Highlight spool A2 + tag A2 |
| 9 | Active Spool A3 | 6, 10 | Highlight spool A3 + tag A3 |
| 10 | Active Spool A4 | 7, 11 | Highlight spool A4 + tag A4 |
| 11 | Active Spool B1 | 12 | Highlight spool B1 |
| 12 | Active Spool B2 | 13 | Highlight spool B2 |
| 13 | Active Spool B3 | 14 | Highlight spool B3 |
| 14 | Active Spool B4 | 15 | Highlight spool B4 |

### MagWLED Presets

| Preset | Name | Active Segments | Description |
|--------|------|-----------------|-------------|
| 1 | Normal Printing | All (0-7) | Dim gray on all tags |
| 2 | Idle/Standby | None | All tags off |
| 3 | Maintenance | All (0-7) | Bright white on all tags |
| 4 | Active Tag B1 | 0, 4 | Orange on B1 top+bottom |
| 5 | Active Tag B2 | 1, 5 | Orange on B2 top+bottom |
| 6 | Active Tag B3 | 2, 6 | Orange on B3 top+bottom |
| 7 | Active Tag B4 | 3, 7 | Orange on B4 top+bottom |
| 8 | Upcoming Tag B1 | 0, 4 | Yellow on B1 (dimmer) |
| 9 | Upcoming Tag B2 | 1, 5 | Yellow on B2 (dimmer) |
| 10 | Upcoming Tag B3 | 2, 6 | Yellow on B3 (dimmer) |
| 11 | Upcoming Tag B4 | 3, 7 | Yellow on B4 (dimmer) |

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

| Bambu Lab Sensor | WLED Action | Example Value |
|------------------|-------------|---------------|
| `sensor.bambu_lab_x1c_current_stage` | Trigger preset change | "printing", "idle", "complete" |
| `sensor.bambu_lab_x1c_print_progress` | Update progress bar | 0-100 (percentage) |
| `sensor.bambu_lab_x1c_active_tray` | Highlight active spool | 1-8 (tray number) |
| `sensor.bambu_lab_x1c_hms_errors` | Trigger error preset | Empty or list of errors |

## GPIO Pin Mapping

### Digquad Controller

| GPIO Pin | Strip # | Description | LED Count (Example) |
|----------|---------|-------------|---------------------|
| 1 | Strip 1 | Printer Interior | 30 |
| 2 | Strip 2 | Printer Front C-shape | 90 |
| 3 | Strip 3 | AMS 1 Lid | 60 |
| 4 | Strip 4 | AMS 1 Tags | 40 |
| 5 | Strip 5 | AMS 2 Lid | 60 |

### MagWLED Controller

| GPIO Pin | Strip # | Description | LED Count (Example) |
|----------|---------|-------------|---------------------|
| 2 | Strip 6 | AMS 2 Tags | 80 |

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
| No lights | Power supply | Verify 5V and ground |
| Wrong colors | LED type | Change to GRB or BGR |
| Segment gaps | LED counts | Verify start/stop numbers |
| Flickering | Power | Add power injection |
| Preset not working | Preset ID | Check preset exists |
| Automation not triggering | Entity ID | Verify correct entity names |

## Notes

- **LED ranges are EXAMPLES** - You must measure your actual strips
- **GPIO pins may vary** - Adjust based on your Digquad wiring
- **Always backup** configurations before making changes
- **Test presets manually** before creating automations
- **Start simple** and add complexity gradually

## Print This Page

This reference card is designed to be printed and kept near your printer for quick reference during setup and troubleshooting.

---

**Version:** 1.0  
**Last Updated:** 2024  
**Repository:** https://github.com/rsocko/hass-bambulab-config
