# xTouch 2.8" → OpenHASP Conversion

> **Source**: Converted from [xtouch LVGL source code](https://github.com/xperiments-in/xtouch) to [OpenHASP](https://www.openhasp.com/) JSONL format  
> **Hardware**: ESP32-2432S028R ("Cheap Yellow Display") — 320×240 ILI9341 TFT  
> **Integration**: Home Assistant via MQTT (OpenHASP custom component)

This directory contains a complete OpenHASP UI conversion of the xtouch 2.8" firmware's LVGL-based interface, designed to run on the **same ESP32-2432S028R hardware** that xtouch originally targeted.

---

## Why OpenHASP?

The original xtouch firmware was a standalone C/Arduino project with a tightly-coupled LVGL UI. OpenHASP provides:

- **JSON-based UI** — No C compilation needed; edit `pages.jsonl` and upload
- **Home Assistant native integration** — Real-time entity updates via MQTT
- **Web-based editor** — Modify UI from any browser on your network
- **OTA updates** — Wireless firmware updates
- **Same hardware** — Runs directly on the ESP32-2432S028R board

---

## Directory Structure

```
openhasp-conversion/
├── README.md              # This file
├── pages.jsonl            # Complete UI definition (6 pages + numpad)
├── boot.cmd               # Boot-time configuration commands
└── ha_automations.yaml    # Home Assistant automations for display updates
```

---

## Pages Overview

| Page | Name | Description | Object IDs |
|------|------|-------------|------------|
| **0** | Sidebar | Navigation bar (always visible, 48px wide) | `p0b1`–`p0b6` |
| **1** | Home | Dashboard: status bar, player controls, temps | `p1b1`–`p1b49` |
| **2** | Temperature | Nozzle/bed temps + part/aux/chamber fan controls | `p2b1`–`p2b54` |
| **3** | Control | XY/Z axis movement D-pad (3×3 grid) | `p3b1`–`p3b18` |
| **4** | Filament | Nozzle temp adjust + filament load/unload | `p4b1`–`p4b23` |
| **5** | Settings | Backlight, sleep timer, toggles, reboot | `p5b1`–`p5b30` |
| **6** | Numpad | Full-screen numeric keypad (for temp input) | `p6b1`–`p6b10` |

### Visual Layout

```
┌──────────┬──────────────────────────────────────────┐
│          │                                          │
│ Sidebar  │         Active Page Content              │
│  48px    │         272 × 240 px                     │
│          │                                          │
│ Page 0   │         Pages 1–6                        │
│          │                                          │
│  [Home]  │                                          │
│  [Temp]  │                                          │
│  [Ctrl]  │                                          │
│  [Fil ]  │                                          │
│  [Set ]  │                                          │
│          │                                          │
└──────────┴──────────────────────────────────────────┘
   48px                    272px                = 320px
```

---

## Setup Instructions

### 1. Flash OpenHASP Firmware

1. Download the OpenHASP firmware for **ESP32-2432S028R** from [openhasp.com](https://www.openhasp.com/latest/firmware/esp32/)
2. Flash using the [web installer](https://nightly.openhasp.com/) or `esptool.py`:
   ```
   esptool.py --port COM3 write_flash 0x0 openhasp_esp32-2432s028r_v0.7.x.bin
   ```
3. Connect to the `openhasp-xxxxxx` WiFi AP and configure your network

### 2. Upload UI Files

1. Open the plate's web interface (http://\<plate-ip\>/)
2. Go to **Files** tab
3. Upload `pages.jsonl` and `boot.cmd`
4. Reboot the plate

### 3. Configure MQTT

1. In the plate's web interface, go to **MQTT** settings
2. Set your MQTT broker address, username, and password
3. Set the **node name** to `xtouch` (or change all references in `ha_automations.yaml`)
4. Save and reboot

### 4. Install Home Assistant Integration

1. Install the [OpenHASP custom component](https://github.com/HASwitchPlate/openHASP-custom-component) via HACS
2. Add the plate in HA: **Settings → Devices → Add Integration → OpenHASP**
3. Copy `ha_automations.yaml` content into your HA automations (or include as a package)

### 5. Configure Entity Names

The automations reference Bambu Lab entities with the prefix `x1c_`. Update these to match your printer:

| Automation Entity | Replace With |
|-------------------|-------------|
| `sensor.x1c_nozzle_temperature` | `sensor.YOUR_PRINTER_nozzle_temperature` |
| `sensor.x1c_bed_temperature` | `sensor.YOUR_PRINTER_bed_temperature` |
| `sensor.x1c_chamber_temperature` | `sensor.YOUR_PRINTER_chamber_temperature` |
| `sensor.x1c_target_nozzle_temperature` | `sensor.YOUR_PRINTER_target_nozzle_temperature` |
| `sensor.x1c_target_bed_temperature` | `sensor.YOUR_PRINTER_target_bed_temperature` |
| `sensor.x1c_print_percentage` | `sensor.YOUR_PRINTER_print_percentage` |
| `sensor.x1c_remaining_time` | `sensor.YOUR_PRINTER_remaining_time` |
| `sensor.x1c_current_layer` | `sensor.YOUR_PRINTER_current_layer` |
| `sensor.x1c_total_layers` | `sensor.YOUR_PRINTER_total_layers` |
| `sensor.x1c_current_stage` | `sensor.YOUR_PRINTER_current_stage` |
| `light.x1c_chamber_light` | `light.YOUR_PRINTER_chamber_light` |
| `fan.x1c_part_fan` | `fan.YOUR_PRINTER_part_fan` |
| `fan.x1c_aux_fan` | `fan.YOUR_PRINTER_aux_fan` |
| `fan.x1c_chamber_fan` | `fan.YOUR_PRINTER_chamber_fan` |
| `button.x1c_pause` | `button.YOUR_PRINTER_pause` |
| `button.x1c_resume` | `button.YOUR_PRINTER_resume` |
| `button.x1c_stop` | `button.YOUR_PRINTER_stop` |
| `sensor.x1c_ams_tray_1_color` | `sensor.YOUR_PRINTER_ams_tray_1_color` |

> **Tip**: Use find-and-replace to change `x1c` to your printer's entity prefix.

---

## Color Palette

Preserved from the original xtouch LVGL design:

| Name | Hex | OpenHASP Usage |
|------|-----|---------------|
| Sidebar BG | `#222222` | Sidebar panel, settings rows |
| Content BG | `#444444` | Page backgrounds, spacers |
| Panels | `#555555` | Buttons, status bar, temp boxes |
| Section Headers | `#333333` | Settings dividers, slider tracks |
| Icon BG | `#777777` | Filament icon panels, pressed states |
| Dim Text | `#888888` | WiFi/camera icons, muted labels |
| Accent Green | `#2AFF00` | Active nav, checked states, progress |
| Orange Accent | `#FF682A` | Settings title, reboot, hot targets |
| Cold Nozzle | `#39A1FD` | Nozzle temp below 170°C |
| Hot Nozzle | `#FAA61E` | Nozzle temp at/above 170°C |
| Primary Text | `#FFFFFF` | Main labels and values |
| Secondary Text | `#CCCCCC` | Icons, secondary labels |
| Sidebar Icons | `#DDDDDD` | Default sidebar button text |

---

## Object Reference

### Page 0 — Sidebar

| Object | ID | Type | Description |
|--------|----|------|-------------|
| Sidebar BG | `p0b1` | obj | Background panel (48×240) |
| Home | `p0b2` | btn | Navigate to Page 1 |
| Temperature | `p0b3` | btn | Navigate to Page 2 |
| Control | `p0b4` | btn | Navigate to Page 3 |
| Filament | `p0b5` | btn | Navigate to Page 4 |
| Settings | `p0b6` | btn | Navigate to Page 5 |

All sidebar buttons use `groupid:1` (radio-button behavior) and `toggle:true`.

### Page 1 — Home

| Object | ID | Type | Description |
|--------|----|------|-------------|
| WiFi icon | `p1b11` | label | WiFi status indicator |
| Camera icon | `p1b12` | label | Camera status indicator |
| AMS Slot 1–4 | `p1b13`–`p1b16` | obj | AMS tray color indicators |
| Play | `p1b20` | btn | Resume print (hidden when idle) |
| Pause | `p1b21` | btn | Pause print (hidden when idle) |
| Stop | `p1b22` | btn | Stop print (hidden when idle) |
| Progress bar | `p1b23` | bar | Print progress (0–100) |
| Progress % | `p1b24` | label | "60%" text |
| Time remaining | `p1b25` | label | "1h 23m" text |
| Layer count | `p1b26` | label | "5/100" text |
| Speed label | `p1b27` | label | Speed indicator |
| Speed dropdown | `p1b28` | dropdown | Silent/Standard/Sport/Ludicrous |
| Idle panel | `p1b30` | obj | "Ready" status (hidden when printing) |
| Ready label | `p1b31` | label | "Ready" text |
| Light toggle | `p1b40` | btn | Toggle chamber light |
| Nozzle temp | `p1b43` | label | Nozzle temperature value |
| Bed temp | `p1b46` | label | Bed temperature value |
| Chamber temp | `p1b49` | label | Chamber temperature value |

### Page 2 — Temperature

| Object | ID | Type | Description |
|--------|----|------|-------------|
| Nozzle current | `p2b12` | label | Current nozzle temperature |
| Nozzle target | `p2b14` | label | Target nozzle temperature |
| Set nozzle target | `p2b15` | btn | Open numpad for nozzle temp |
| Bed current | `p2b22` | label | Current bed temperature |
| Bed target | `p2b24` | label | Target bed temperature |
| Set bed target | `p2b25` | btn | Open numpad for bed temp |
| Part fan % | `p2b33` | label | Part fan percentage |
| Part fan slider | `p2b34` | slider | Part fan speed control |
| Aux fan % | `p2b43` | label | Aux fan percentage |
| Aux fan slider | `p2b44` | slider | Aux fan speed control |
| Chamber fan % | `p2b53` | label | Chamber fan percentage |
| Chamber fan slider | `p2b54` | slider | Chamber fan speed control |

### Page 3 — Control

| Object | ID | Type | Description |
|--------|----|------|-------------|
| Range toggle | `p3b10` | btn | Step size: 1mm / 10mm |
| Up | `p3b11` | btn | Move Y+ (or Z+ in Z mode) |
| Axis toggle | `p3b12` | btn | XY mode / Z mode |
| Left | `p3b13` | btn | Move X- (disabled in Z mode) |
| Home | `p3b14` | btn | Home axes |
| Right | `p3b15` | btn | Move X+ (disabled in Z mode) |
| Down | `p3b17` | btn | Move Y- (or Z- in Z mode) |

### Page 4 — Filament

| Object | ID | Type | Description |
|--------|----|------|-------------|
| Nozzle Up | `p4b10` | btn | Increase nozzle target temp |
| Nozzle Temp | `p4b13` | label | Current temp (color-coded) |
| Nozzle Down | `p4b14` | btn | Decrease nozzle target temp |
| Unload | `p4b20` | btn | Unload filament |
| Load | `p4b23` | btn | Load filament |

### Page 5 — Settings

| Object | ID | Type | Description |
|--------|----|------|-------------|
| Backlight slider | `p5b12` | slider | LCD brightness (10–255) |
| Sleep slider | `p5b15` | slider | Idle timeout (1–60 min) |
| Sleep value | `p5b16` | label | Current timeout value |
| Wake on Print | `p5b22` | switch | Auto-wake when print starts |
| Invert Colors | `p5b25` | switch | Invert display colors |
| AUX Fan toggle | `p5b28` | switch | AUX fan enable (P1P/X1 only) |
| Reboot | `p5b30` | btn | Reboot the plate |

### Page 6 — Numpad

| Object | ID | Type | Description |
|--------|----|------|-------------|
| Title | `p6b2` | label | "Set Nozzle Target:" context label |
| Input display | `p6b3` | label | Current input value |
| Numpad matrix | `p6b10` | btnmatrix | 4×3 grid: 1-9, 0, Back, OK |

---

## LVGL Symbol to OpenHASP Icon Mapping

The original xtouch used a custom icon font (`ui_font_xlcd`). OpenHASP uses LVGL's built-in symbol font:

| Original Glyph | Function | OpenHASP (LVGL Symbol) | Codepoint |
|----------------|----------|----------------------|-----------|
| `"a"` Home | Sidebar, Control | `\uF015` (HOME) | U+F015 |
| `"d"` Settings | Sidebar | `\uF013` (SETTINGS) | U+F013 |
| `"s"` Up Arrow | Control, Filament | `\uF077` (UP) | U+F077 |
| `"t"` Down Arrow | Control, Filament | `\uF078` (DOWN) | U+F078 |
| `"u"` Left Arrow | Control | `\uF053` (LEFT) | U+F053 |
| `"v"` Right Arrow | Control | `\uF054` (RIGHT) | U+F054 |
| `"w"` Light | Home | `\uF043` (TINT) | U+F043 |
| `"x"` WiFi | Home status | `\uF1EB` (WIFI) | U+F1EB |
| `"y"` Camera | Home status | `\uF008` (VIDEO) | U+F008 |
| `"z"` Play | Home player | `\uF04B` (PLAY) | U+F04B |
| `"0"` Pause | Home player | `\uF04C` (PAUSE) | U+F04C |
| `"1"` Stop | Home player | `\uF04D` (STOP) | U+F04D |
| `"b"` Thermometer | Sidebar (temp) | `\uF043` (TINT) | U+F043 |
| `"c"` Control | Sidebar (control) | `\uF074` (SHUFFLE) | U+F074 |
| `"n"` Filament | Sidebar (filament) | Text: "FIL" | — |

Icons without direct LVGL equivalents (`"e"` Bed, `"f"` Nozzle, `"g"` Chamber, `"h"` Speed, `"i"` Fan) use text labels instead. To use Material Design Icons, compile OpenHASP with an MDI font and substitute the codepoints.

---

## Customization

### Using Material Design Icons

If your OpenHASP build includes MDI fonts, you can replace text labels with proper icons:

```jsonl
// Example: Replace "Noz" text with MDI printer-3d-nozzle icon
// Check your font file for the exact codepoint
{"page":1,"id":42,"text":"\uF0FD6","text_font":"materialdesign-webfont-24"}
```

### Changing Display Size

The layout is designed for 320×240 (ILI9341). To adapt to other resolutions:
1. Scale all `x`, `y`, `w`, `h` values proportionally
2. Adjust `text_font` sizes accordingly
3. The sidebar width (48px) can be increased for larger displays

### Adding More AMS Slots

The home screen has 4 AMS color slots. For multi-AMS setups, add more slots:

```jsonl
{"page":1,"id":17,"obj":"obj","x":102,"y":5,"w":10,"h":14,"parentid":10,"bg_color":"#444444","radius":2}
```

### Printer Model Visibility

Some settings are model-specific. The `ha_automations.yaml` can show/hide these:

```yaml
# Show AUX FAN toggle only for P1P/X1 series
- service: mqtt.publish
  data:
    topic: "hasp/xtouch/command/p5b26.hidden"
    payload: "{{ 'false' if 'P1P' in states('sensor.x1c_printer_model') else 'true' }}"
```

---

## Differences from Original xtouch

| Feature | Original xtouch | OpenHASP Conversion |
|---------|----------------|-------------------|
| UI Engine | LVGL C code (compiled) | JSONL (editable text) |
| Communication | Direct MQTT to Bambu Cloud | HA → MQTT → Plate |
| Custom Icons | `ui_font_xlcd` custom font | LVGL built-in symbols + text |
| Numpad | Inline in temperature page | Separate page (Page 6) |
| Scrollable Settings | Native LVGL scroll | Fixed layout (fits on screen) |
| Fan Control | Read-only display | Interactive sliders |
| Temperature Set | Built-in numpad overlay | Button → HA service call |
| Firmware Updates | OTA via xtouch server | OpenHASP OTA or web upload |
| Printer Pairing | Built-in discovery | Via HA Bambu Lab integration |

---

## Troubleshooting

### Icons display as boxes or question marks
The LVGL symbol font may not be included in your firmware build. Check [OpenHASP firmware builds](https://www.openhasp.com/latest/firmware/) for your board, or compile custom firmware with the required fonts.

### Settings switches don't work
The switches on Page 5 are display-only toggles. Connect them to HA automations to make them functional. The `ha_automations.yaml` includes handlers for backlight, sleep, and reboot.

### Page doesn't change when pressing sidebar
Ensure the MQTT automations in `ha_automations.yaml` are active. The sidebar buttons publish events that HA must relay back as page change commands.

### Temperature values show "--"
Check that:
1. The Bambu Lab integration is running in HA
2. Entity names match (default uses `x1c_` prefix)
3. MQTT is connected between HA and the plate

---

## Related Resources

- [OpenHASP Documentation](https://www.openhasp.com/)
- [OpenHASP Custom Component for HA](https://github.com/HASwitchPlate/openHASP-custom-component)
- [ESP32-2432S028R Board Info](https://github.com/witnessmenow/ESP32-Cheap-Yellow-Display)
- [Original xtouch Source](https://github.com/xperiments-in/xtouch)
- [Bambu Lab HA Integration](https://github.com/greghesp/ha-bambulab)
