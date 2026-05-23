# OpenHASP Device Files — ESP32-S3 5" Touchscreen

These files are deployed directly to the ESP32 device's flash storage. They are accessible and editable via the openHASP web interface at `http://<device-ip>/` (default port 80).

> **These files do not live in Home Assistant.** They are stored on the ESP32 itself. Edit them via the openHASP web UI file editor, Telnet, or by uploading through the HTTP interface.

For a grouped object ID summary, see the top-level quick reference in [esp32s3-5inch-readme.md](esp32s3-5inch-readme.md#object-id-quick-reference).

## Files

### `config.json` — Device Configuration

The main openHASP [configuration file](https://www.openhasp.com/0.7.0/firmware/configuration/hasp/) that controls all device settings. Key sections:

| Section | Purpose |
|---------|---------|
| `wifi` | Wi-Fi SSID and password (connects to `IoT` network) |
| `mqtt` | MQTT broker connection — host `192.168.1.5`, port `1883`, node name `officetouch5`. Topic pattern: `hasp/officetouch5/<topic>` |
| `http` | Web interface on port 80 (for file editing, firmware updates, configuration) |
| `telnet` | Telnet access on port 23 (for sending commands, debugging) |
| `gui` | Display settings — idle timeouts (60s dim, 120s off), backlight level, rotation |
| `hasp` | UI settings — start page `1`, theme `2` (Material Dark), primary color `#00b6ff`, secondary `#ff9962`, pages file `/printer2.jsonl` |
| `debug` | Serial baud rate 115200, telemetry period 300s |
| `gpio` | GPIO pin configuration (all default/unused) |
| `mdns` | mDNS enabled for local network discovery |

**MQTT topic structure:**
```
hasp/officetouch5/state/p1b5    → {"text":"42%"}     (object states OUT)
hasp/officetouch5/command/p1b5  → {"text":"55%"}     (commands IN)
homeassistant/status            → online/offline      (HA birth/will)
```

### `printer2.jsonl` + `pages/*.jsonl` — Page Layout (UI Design)

The [JSONL pages file](https://www.openhasp.com/0.7.0/design/pages/) defines all visual objects on the touchscreen. Each line is a JSON object that creates or configures one UI element. The file is loaded at boot via the `hasp.pages` setting in `config.json`.

- `printer2.jsonl` is the deployable combined file loaded by openHASP.
- `pages/3dprinter.page0.nav.jsonl`, `pages/3dprinter.page1.home.jsonl`, `pages/3dprinter.page2.controls.jsonl`, and `pages/3dprinter.page3.filament.jsonl` are per-page source files for easier editing.

**Page structure:**
- **Page 0** — Shared left-side navigation (Home, Controls, Filament icons)
- **Page 1** — 3D Printer Dashboard (main and only page)
- **Page 2** — Printer motion + filament controls
- **Page 3** — Filament weight/cost breakdown (side-by-side panels)

**Object map for Page 1:**

| ID | Object Type | Position | Description |
|----|------------|----------|-------------|
| `p1b1` | `img` | 40,140 200×200 | 3D model preview image (pushed from HA) |
| `p1b28` | `obj` | 40,140 200×200 | Border frame around the model image |
| `p1b2` | `arc` | 270,10 120×120 | Print progress arc (0–100%) |
| `p1b3` | `arc` | 10,10 120×120 | Layer progress arc (current/total) |
| `p1b5` | `label` | 300,50 | Progress percentage text |
| `p1b7` | `label` | 30,50 | Layer count text (current/total) |
| `p1b82` | `img` | 54,82 32×32 | Layer icon centered under layer count (`L:/layers.png`) |
| `p1b83` | `img` | 314,82 32×32 | Progress icon centered under percentage (`L:/progress.png`) |
| `p1b9` | `label` | 40,110 | "Layers" static label |
| `p1b16` | `label` | 300,110 | "Progress" static label |
| `p1b84` | `btn` | 692,20 52×52 | **Stop** button — always visible, color indicates enabled (red) or disabled (dark gray) |
| `p1b85` | `img` | 702,30 32×32 | Stop icon (`L:/stop.png`, `click:false` — touches pass to btn below) |
| `p1b86` | `btn` | 748,20 52×52 | **Pause** button — visible only when actively printing (hidden when paused/idle) |
| `p1b87` | `img` | 758,30 32×32 | Pause icon (`L:/pause.png`, shown/hidden with Pause btn) |
| `p1b88` | `btn` | 748,20 52×52 | **Resume** button — same position as Pause, visible only when paused |
| `p1b89` | `img` | 758,30 32×32 | Resume/play icon (`L:/play.png`, shown/hidden with Resume btn) |
| `p0b2` | `btn` | 6,20 44×44 | Shared nav: opens dashboard page (page 1) |
| `p0b3` | `btn` | 6,80 44×44 | Shared nav: opens controls page (page 2) |
| `p0b4` | `btn` | 6,140 44×44 | Shared nav: opens filament analytics page (page 3) |
| `p1b14` | `label` | 140,25 | Time remaining value |
| `p1b15` | `label` | 130,55 | "Time Remaining" static label |
| `p1b30` | `label` | 110,84 | "Est" static label |
| `p1b29` | `label` | 145,80 (145×35, font 16) | Estimated completion time value (friendly formatted text) |
| `p1b10`–`p1b13`, `p1b17`–`p1b20`, `p1b39` | `obj` | main page | AMS spool indicators (A1–A4, B1–B4, Ext) |
| `p1b41`, `p1b42`, `p1b33`–`p1b38`, `p1b40` | `label` | main page | Static spool slot labels |
| `p1b27` | `led` | 45,375 | Status LED indicator |
| `p1b31` | `label` | 100,390 | Smart status detail value (`detail` attribute) |
| `p1b32` | `label` | 100,355 | Smart status state value |

**Object map for Page 2 (controls):**

| ID | Object Type | Position | Description |
|----|------------|----------|-------------|
| `p2b5`–`p2b8` | `btn` | XY center ring | XY jog by 1 step (icon buttons) |
| `p2b9`–`p2b12` | `btn` | XY outer ring | XY jog by 10 steps (stacked-arrow icons) |
| `p2b13` | `btn` | XY center | Home action (home icon overlay) |
| `p2b20`–`p2b23` | `btn` | Right column | Z jog (up/down arrow icons for 1 and 10) |
| `p2b30` | `btn` | Far-right column | Retract filament (up-arrow icon button) |
| `p2b31` | `btn` | Far-right column | Extrude filament (down-arrow icon button) |
| `p2b42`–`p2b55` | `img` | Page 2 overlays | Directional icon overlays for XY/Z + extruder controls |
| `p2b41` | `label` | Top-right area | Safety hint placeholder (hidden) |

**Object map for Page 3 (filament analytics):**

| ID | Object Type | Position | Description |
|----|------------|----------|-------------|
| `p3b53`, `p3b54` | `label` | top of each panel | Total weight and total cost labels |
| `p3b73`–`p3b81` | `obj` | left panel | Weight stacked bar segments (A1–A4, B1–B4, Ext) |
| `p3b60`–`p3b68` | `obj` | right panel | Cost stacked bar segments (A1–A4, B1–B4, Ext) |
| `p3b69`, `p3b70` | `obj` | panel bar areas | Weight/cost bar border frames |
| `p3b71`, `p3b72` | `label` | panel detail areas | Multiline legend/detail text with per-slot values and percentages |

> **Note:** Static visual-only IDs (for labels/icons) do not require Home Assistant bindings. On page 2 this includes icon overlays such as `p2b15`, `p2b25`, `p2b33`, and `p2b42`–`p2b55`.

The values for `p1b31` and `p1b32` are populated by Home Assistant via [officetouch5.yaml](../../../../homeassistant/packages/3d_printing/openhasp_display/openhasp/officetouch5.yaml), using `sensor.ntk_ryansoffice_3dprinter_smart_status` and its `detail` attribute.

Page-2 touch events are consumed by [printer_motion_controls.yaml](../../../../homeassistant/packages/3d_printing/openhasp_display/automations/printer_motion_controls.yaml), which calls:

- `bambu_lab.move_axis` for X/Y/Z/home actions
- `bambu_lab.extrude_retract` for filament retract/extrude

**Object types used** (see [openHASP Objects reference](https://www.openhasp.com/0.7.0/design/objects/)):

| Type | Description |
|------|-------------|
| [`arc`](https://www.openhasp.com/0.7.0/design/objects/arc/) | Circular progress indicator with configurable start/end angles. Used for print %, layer count, and time remaining. |
| [`btn`](https://www.openhasp.com/0.7.0/design/objects/btn/) | Clickable button with built-in touch events. Used for printer control buttons (Stop, Pause, Resume). |
| [`label`](https://www.openhasp.com/0.7.0/design/objects/label/) | Text display. Used for all text values and static labels. |
| [`obj`](https://www.openhasp.com/0.7.0/design/objects/obj/) | Base rectangle object. Used as stacked bar segments and bar frames (colors and widths set dynamically from HA). |
| [`img`](https://www.openhasp.com/0.7.0/design/objects/img/) | Image display. Shows the 3D model preview pushed from Home Assistant. Requires PSRam. |
| [`led`](https://www.openhasp.com/0.7.0/design/objects/led/) | LED indicator with adjustable brightness and color. Used as a status indicator. |

### `online.cmd` — Online Command Script

A [batch command](https://www.openhasp.com/0.7.0/commands/scripts/) executed automatically when the device connects to MQTT (i.e., when Home Assistant comes online). Displays a popup message box showing the device's IP address, auto-closing after 20 seconds.

```
jsonl {"page":0,"id":239,"obj":"msgbox","text":"%ip%","auto_close":20000}
```

### `offline.cmd` — Offline Command Script

A [batch command](https://www.openhasp.com/0.7.0/commands/scripts/) executed automatically when the MQTT connection is lost (i.e., when Home Assistant goes offline). Displays a popup message box reading "offline", auto-closing after 20 seconds.

```
jsonl {"page":0,"id":239,"obj":"msgbox","text":"offline","auto_close":20000}
```

## Editing These Files

1. **Web UI** — Navigate to `http://<device-ip>/` → click the file editor icon to upload or edit files directly.
2. **Telnet** — Connect to the device on port 23 to send [commands](https://www.openhasp.com/0.7.0/commands/global/) in real-time (useful for testing object changes with `jsonl` commands before saving to the `.jsonl` file).
3. **Upload** — Use the HTTP upload endpoint or the web UI to push updated files.

After editing `printer2.jsonl`, reboot the device or send the `reboot` command via Telnet for changes to take effect.

## Useful References

- [openHASP Objects](https://www.openhasp.com/0.7.0/design/objects/) — All available object types and properties
- [openHASP Pages](https://www.openhasp.com/0.7.0/design/pages/) — JSONL page file format
- [openHASP Styling](https://www.openhasp.com/0.7.0/design/styling/) — Colors, borders, padding properties
- [openHASP Commands](https://www.openhasp.com/0.7.0/commands/global/) — Runtime commands (jsonl, page, reboot, etc.)
- [openHASP Batch Scripts](https://www.openhasp.com/0.7.0/commands/scripts/) — `.cmd` file format (online.cmd, offline.cmd)
- [HA Integration How-To](https://www.openhasp.com/0.7.0/integrations/home-assistant/howto/) — Setting up the HA custom component
- [HA Example Configs](https://www.openhasp.com/0.7.0/integrations/home-assistant/sampl_conf/) — Sample plate configurations
- [Guition ESP32-S3 JC8048W550](https://www.openhasp.com/0.7.0/hardware/guition/jc8048w550/) — Hardware-specific info for this board