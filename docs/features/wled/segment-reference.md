# Segment Allocation Reference Card

Quick reference for WLED segment IDs and their purposes.

**Total System LEDs: 711**

For complete LED specifications, see [digquad-led-segments.md](digquad-led-segments.md).
For function details, see [LED Function Map](light-scenarios.md#2-led-function-map-consolidated).
For scenario behaviors, see [light-scenarios.md](light-scenarios.md).

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

**Functions** (see [LED Function Map](light-scenarios.md#2-led-function-map-consolidated)):
- Bottom: Display print progress %, pause animation, completion flash
- Left/Top: Print status (pulsing soft green when printing, flashing red on error)

### GPIO 1: AMS 1 Lid/Spools (140 LEDs, Range: 158-297)

Detailed breakdown in [digquad-led-segments.md](digquad-led-segments.md).

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

For complete scenario catalog, see [light-scenarios.md](light-scenarios.md).

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

| Color          | RGB Value   | Hex     | Usage                      |
| -------------- | ----------- | ------- | -------------------------- |
| White (Bright) | 255,255,255 | #FFFFFF | Active spools, maintenance |
| Warm White     | 255,220,180 | #FFDCB4 | Inactive spools, idle      |
| Green          | 0,255,0     | #00FF00 | Normal status, success     |
| Red            | 255,0,0     | #FF0000 | Error, alert               |
| Orange         | 255,100,0   | #FF6400 | Active tag highlight       |
| Yellow         | 150,150,0   | #969600 | Upcoming tag               |
| Blue           | 100,150,255 | #6496FF | Idle breathing             |
| Gray           | 100,100,100 | #646464 | Inactive tags              |

## Effect IDs Reference

> **How to retrieve**: Query `http://<wled-ip>/json/effects` — returns an array where the index is the effect ID.  
> PowerShell: `(Invoke-RestMethod "http://192.168.50.103/json/effects") | ForEach-Object -Begin {$i=0} -Process { "$i`t$_"; $i++ }`  
> **Note**: Effect IDs can vary between WLED firmware versions. Always verify against your device.

### Effects Used in State Machine Presets

| Effect ID | Name | Used In | Purpose |
|-----------|------|---------|---------|
| 0 | Solid | Most segments across all presets | Static color fill |
| 1 | Blink | S8 Show (tags) | Slow blinking aesthetic |
| 2 | Breathe | S1 Idle (seg 2), S3 Printing (seg 2), S4 Paused (seg 2), S5 Error (seg 2) | Slow pulsing glow |
| 3 | Wipe | S6 Finishing (seg 2) | Sweep animation |
| 6 | Sweep | S2 Prep (seg 2) | Back-and-forth sweep |
| 10 | Scan | S1 Idle (seg 2) | Scanning light |
| 17 | Twinkle | S7 Maintenance (seg 2) | Sparse twinkling |
| 68 | Bpm | S8 Show (seg 2) | Palette-based beat |
| 98 | Percent | S3 Printing (seg 0, 1), S4 Paused (seg 0, 1), S5 Error (seg 0, 1) | Progress bar fill — `ix` controls fill % (0–100 direct percentage) |

### Full Effects List (DigQuad at 192.168.50.103, retrieved 2026-03-13)

<details>
<summary>Click to expand full list (187 effects)</summary>

| ID | Name | ID | Name | ID | Name |
|----|------|----|------|----|------|
| 0 | Solid | 1 | Blink | 2 | Breathe |
| 3 | Wipe | 4 | Wipe Random | 5 | Random Colors |
| 6 | Sweep | 7 | Dynamic | 8 | Colorloop |
| 9 | Rainbow | 10 | Scan | 11 | Scan Dual |
| 12 | Fade | 13 | Theater | 14 | Theater Rainbow |
| 15 | Running | 16 | Saw | 17 | Twinkle |
| 18 | Dissolve | 19 | Dissolve Rnd | 20 | Sparkle |
| 21 | Sparkle Dark | 22 | Sparkle+ | 23 | Strobe |
| 24 | Strobe Rainbow | 25 | Strobe Mega | 26 | Blink Rainbow |
| 27 | Android | 28 | Chase | 29 | Chase Random |
| 30 | Chase Rainbow | 31 | Chase Flash | 32 | Chase Flash Rnd |
| 33 | Rainbow Runner | 34 | Colorful | 35 | Traffic Light |
| 36 | Sweep Random | 37 | Chase 2 | 38 | Aurora |
| 39 | Stream | 40 | Scanner | 41 | Lighthouse |
| 42 | Fireworks | 43 | Rain | 44 | Tetrix |
| 45 | Fire Flicker | 46 | Gradient | 47 | Loading |
| 48 | Rolling Balls | 49 | Fairy | 50 | Two Dots |
| 51 | Fairytwinkle | 52 | Running Dual | 53 | RSVD |
| 54 | Chase 3 | 55 | Tri Wipe | 56 | Tri Fade |
| 57 | Lightning | 58 | ICU | 59 | Multi Comet |
| 60 | Scanner Dual | 61 | Stream 2 | 62 | Oscillate |
| 63 | Pride 2015 | 64 | Juggle | 65 | Palette |
| 66 | Fire 2012 | 67 | Colorwaves | 68 | Bpm |
| 69 | Fill Noise | 70 | Noise 1 | 71 | Noise 2 |
| 72 | Noise 3 | 73 | Noise 4 | 74 | Colortwinkles |
| 75 | Lake | 76 | Meteor | 77 | Meteor Smooth |
| 78 | Railway | 79 | Ripple | 80 | Twinklefox |
| 81 | Twinklecat | 82 | Halloween Eyes | 83 | Solid Pattern |
| 84 | Solid Pattern Tri | 85 | Spots | 86 | Spots Fade |
| 87 | Glitter | 88 | Candle | 89 | Fireworks Starburst |
| 90 | Fireworks 1D | 91 | Bouncing Balls | 92 | Sinelon |
| 93 | Sinelon Dual | 94 | Sinelon Rainbow | 95 | Popcorn |
| 96 | Drip | 97 | Plasma | 98 | Percent |
| 99 | Ripple Rainbow | 100 | Heartbeat | 101 | Pacifica |
| 102 | Candle Multi | 103 | Solid Glitter | 104 | Sunrise |
| 105 | Phased | 106 | Twinkleup | 107 | Noise Pal |
| 108 | Sine | 109 | Phased Noise | 110 | Flow |
| 111 | Chunchun | 112 | Dancing Shadows | 113 | Washing Machine |
| 114 | Rotozoomer | 115 | Blends | 116 | TV Simulator |
| 117 | Dynamic Smooth | 118 | Spaceships | 119 | Crazy Bees |
| 120 | Ghost Rider | 121 | Blobs | 122 | Scrolling Text |
| 123 | Drift Rose | 124 | Distortion Waves | 125 | Soap |
| 126 | Octopus | 127 | Waving Cell | 128 | Pixels |
| 129 | Pixelwave | 130 | Juggles | 131 | Matripix |
| 132 | Gravimeter | 133 | Plasmoid | 134 | Puddles |
| 135 | Midnoise | 136 | Noisemeter | 137 | Freqwave |
| 138 | Freqmatrix | 139 | GEQ | 140 | Waterfall |
| 141 | Freqpixels | 142 | RSVD | 143 | Noisefire |
| 144 | Puddlepeak | 145 | Noisemove | 146 | Noise2D |
| 147 | Perlin Move | 148 | Ripple Peak | 149 | Firenoise |
| 150 | Squared Swirl | 151 | RSVD | 152 | DNA |
| 153 | Matrix | 154 | Metaballs | 155 | Freqmap |
| 156 | Gravcenter | 157 | Gravcentric | 158 | Gravfreq |
| 159 | DJ Light | 160 | Funky Plank | 161 | RSVD |
| 162 | Pulser | 163 | Blurz | 164 | Drift |
| 165 | Waverly | 166 | Sun Radiation | 167 | Colored Bursts |
| 168 | Julia | 169 | RSVD | 170 | RSVD |
| 171 | RSVD | 172 | Game Of Life | 173 | Tartan |
| 174 | Polar Lights | 175 | Swirl | 176 | Lissajous |
| 177 | Frizzles | 178 | Plasma Ball | 179 | Flow Stripe |
| 180 | Hiphotic | 181 | Sindots | 182 | DNA Spiral |
| 183 | Black Hole | 184 | Wavesins | 185 | Rocktaves |
| 186 | Akemi | | | | |

</details>

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
- **Functions are DEFINED** - See light-scenarios.md Section 2 (LED Function Map) for zone purposes
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
