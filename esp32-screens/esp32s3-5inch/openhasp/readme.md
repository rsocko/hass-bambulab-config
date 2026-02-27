# OpenHASP Device Files — ESP32-S3 5" Touchscreen

These files are deployed directly to the ESP32 device's flash storage. They are accessible and editable via the openHASP web interface at `http://<device-ip>/` (default port 80).

> **These files do not live in Home Assistant.** They are stored on the ESP32 itself. Edit them via the openHASP web UI file editor, Telnet, or by uploading through the HTTP interface.

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

### `printer2.jsonl` — Page Layout (UI Design)

The [JSONL pages file](https://www.openhasp.com/0.7.0/design/pages/) defines all visual objects on the touchscreen. Each line is a JSON object that creates or configures one UI element. The file is loaded at boot via the `hasp.pages` setting in `config.json`.

**Page structure:**
- **Page 0** — Common objects (visible on all pages) — currently empty
- **Page 1** — 3D Printer Dashboard (main and only page)

**Object map for Page 1:**

| ID | Object Type | Position | Description |
|----|------------|----------|-------------|
| `p1b1` | `img` | 40,140 200×200 | 3D model preview image (pushed from HA) |
| `p1b28` | `obj` | 40,140 200×200 | Border frame around the model image |
| `p1b2` | `arc` | 270,10 120×120 | Print progress arc (0–100%) |
| `p1b3` | `arc` | 10,10 120×120 | Layer progress arc (current/total) |
| `p1b5` | `label` | 300,50 | Progress percentage text |
| `p1b7` | `label` | 30,50 | Layer count text (current/total) |
| `p1b9` | `label` | 40,110 | "Layers" static label |
| `p1b16` | `label` | 300,110 | "Progress" static label |
| `p1b14` | `label` | 140,25 | Time remaining value |
| `p1b15` | `label` | 130,55 | "Time Remaining" static label |
| `p1b30` | `label` | 130,110 | "Est. Complete" static label |
| `p1b29` | `label` | 140,80 | Estimated completion time value |
| `p1b10`–`p1b13` | `obj` | 310–490,140 | AMS 1 spool color indicators (A1–A4) |
| `p1b17`–`p1b20` | `obj` | 310–490,300 | AMS 2 spool color indicators (B1–B4) |
| `p1b39` | `obj` | 550,215 | External spool color indicator |
| `p1b41`, `p1b42` | `label` | 315,215 / 375,215 | AMS 1 slot labels (A1, A2) |
| `p1b33`, `p1b34` | `label` | 435,215 / 495,215 | AMS 1 slot labels (A3, A4) |
| `p1b35`–`p1b38` | `label` | 315–495,375 | AMS 2 slot labels (B1–B4) |
| `p1b40` | `label` | 555,290 | "Ext" label |
| `p1b26` | `label` | 100,355 | "State:" static label |
| `p1b27` | `led` | 45,375 | Status LED indicator |
| `p1b43` | `label` | 100,390 | "Detail:" static label |
| `p1b31` | `label` | 180,390 | Smart status detail value (`detail` attribute) |
| `p1b32` | `label` | 180,355 | Smart status state value |

> **Note:** Object IDs in the range 41–43 are used for static slot/state/detail labels that do not need to be controlled by Home Assistant. All object IDs are unique.

The values for `p1b31` and `p1b32` are populated by Home Assistant via [../hass-config/officetouch5.yaml](../hass-config/officetouch5.yaml), using `sensor.ntk_ryansoffice_3dprinter_smart_status` and its `detail` attribute.

**Object types used** (see [openHASP Objects reference](https://www.openhasp.com/0.7.0/design/objects/)):

| Type | Description |
|------|-------------|
| [`arc`](https://www.openhasp.com/0.7.0/design/objects/arc/) | Circular progress indicator with configurable start/end angles. Used for print %, layer count, and time remaining. |
| [`label`](https://www.openhasp.com/0.7.0/design/objects/label/) | Text display. Used for all text values and static labels. |
| [`obj`](https://www.openhasp.com/0.7.0/design/objects/obj/) | Base rectangle object. Used as colored spool indicators (background color set dynamically from HA). |
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