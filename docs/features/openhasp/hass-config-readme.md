# Home Assistant Configuration for OpenHASP Touchscreen

Configuration files that define the bridge between Home Assistant and the OpenHASP-powered ESP32-S3 5" touchscreen display. These files live in Home Assistant's `/config/` directory and manage data binding, image pushing, and camera snapshot capture for the 3D printer dashboard.

## Architecture Overview

```
Home Assistant
├── /config/openhasp/
│   └── officetouch5.yaml          ← Object-to-entity data bindings (MQTT)
├── /config/automations.yaml       ← Contains the automations below
│   ├── Push Printer Image to Screen
│   ├── OpenHASP Printer Controls (Stop/Pause/Start)
│   └── Save Camera Snapshot from 3D Printer
├── Template Helpers (UI or YAML)
│   ├── Print Time Remaining (Formatted)   ← "Xh Ym" display string
│   ├── Total Estimated Print Time         ← Arc max value (minutes)
│   └── Print End Time Friendly            ← User-friendly estimated completion text
└── /config/www/
    ├── 3dprinter_coverimage.png   ← Saved cover image (optional)
    └── printer_snapshot.jpg       ← Periodic camera snapshot
```

## Files in This Directory

For a grouped object ID summary, see the top-level quick reference in [esp32s3-5inch-readme.md](esp32s3-5inch-readme.md#object-id-quick-reference).

### OpenHASP Plate Configuration

| File | HA Path | Description |
|------|---------|-------------|
| [officetouch5.yaml](../../../homeassistant/packages/3d_printing/openhasp_display/openhasp/officetouch5.yaml) | `/config/openhasp/officetouch5.yaml` | Defines the object-to-entity mappings for the `officetouch5` plate. Maps JSONL UI objects on the ESP32 to Home Assistant sensor values via the OpenHASP custom component. |

**Key bindings in `officetouch5.yaml`:**

| Object | Type | Bound Entity / Data |
|--------|------|---------------------|
| `p1b2` | Arc | Print progress % (`sensor.ntk_ryansoffice_3dprinter_print_progress`) |
| `p1b3` | Arc | Current layer / total layers |
| `p1b4` | Arc | Remaining time / total estimated time |
| `p1b5` | Label | Print progress % text |
| `p1b7` | Label | Layer count (current/total) |
| `p1b14` | Label | Time remaining (formatted) |
| `p1b29` | Label | Estimated end time (`sensor.print_end_time_friendly`) |
| `p1b53`, `p1b54` | Label | Weight/cost tab totals (`print_weight`, `print_cost`) |
| `p1b10`–`p1b13` | Obj | AMS 1 tray 1–4 spool colors |
| `p1b17`–`p1b20` | Obj | AMS 2 tray 1–4 spool colors |
| `p1b39` | Obj | External spool color/active highlight |
| `p1b73`–`p1b81` | Obj | Weight tab stacked segments (x/w/bg_color) |
| `p1b60`–`p1b68` | Obj | Cost tab stacked segments (x/w/bg_color) |
| `p1b31` | Label | Smart status detail (`state_attr('sensor.ntk_ryansoffice_3dprinter_smart_status', 'detail')`) |
| `p1b32` | Label | Smart status state (`sensor.ntk_ryansoffice_3dprinter_smart_status`) |
| `p1b84`, `p1b86`, `p1b88` | Obj | Top-right control button colors (`stop`, `pause`, `start`) |
| `p1b85`, `p1b87`, `p1b89` | Label | Top-right control icon colors (enabled/disabled state) |

> **Smart status dependency:** The entity `sensor.ntk_ryansoffice_3dprinter_smart_status` is defined in [homeassistant/packages/3d_printing/core/template_sensors/smart_status.yaml](../../../homeassistant/packages/3d_printing/core/template_sensors/smart_status.yaml) and must exist in Home Assistant for these two labels to render correctly.

### Automations

Each automation is stored as a separate YAML file for easy version control and deployment.

| File | HA Automation | Status | Description |
|------|---------------|--------|-------------|
| [push_printer_image_to_screen.yaml](../../../homeassistant/packages/3d_printing/openhasp_display/automations/push_printer_image_to_screen.yaml) | `Push Printer Image to Screen` | **Active** | Pushes the 3D printer's model/cover image to the OpenHASP display whenever the image entity updates. Uses `openhasp.push_image` to render the image on object `p1b1`. |
| [save_camera_snapshot_from_3d_printer.yaml](../../../homeassistant/packages/3d_printing/openhasp_display/automations/save_camera_snapshot_from_3d_printer.yaml) | `Save Camera Snapshot from 3D Printer` | **Disabled** | Captures a camera snapshot every 2 minutes (when printer is on) and saves to `/config/www/printer_snapshot.jpg`. Useful for serving static images to dashboards or external tools. |
| [auto_manage_screen_visibility.yaml](../../../homeassistant/packages/3d_printing/openhasp_display/automations/auto_manage_screen_visibility.yaml) | `Auto Manage ESP32 Screen Visibility` | **Active** | Implements issue #46 behavior: keeps screen visibility in sync with print activity, errors, and optional office-presence signals. Uses `openhasp.wakeup` and `openhasp.command` to drive full brightness, low visibility, and delayed full off states. |
| [printer_control_buttons.yaml](../../../homeassistant/packages/3d_printing/openhasp_display/automations/printer_control_buttons.yaml) | `OpenHASP Printer Controls (Stop/Pause/Start)` | **Active** | Listens for touch events from control IDs `p1b84`–`p1b89` and conditionally invokes printer stop/pause/resume button entities. |

**Visibility automation customization:**

- Targets `openhasp.officetouch5` by default.
- Optional office-presence entities (replace to match your setup):
    - `binary_sensor.office_pc_active`
    - `binary_sensor.office_occupied`
- If neither presence sensor exists, presence gating is skipped (treated as present).
- Default brightness profile:
    - Full visibility: `255`
    - Low visibility: `45`
    - Pre-off dim level: `15`
    - Off delay from low visibility: `10 minutes`

### Template Sensors (Helpers)

Custom template sensors that transform raw Bambu Lab printer data into display-friendly values for the touchscreen.

| File | HA Entity | Used By | Description |
|------|-----------|---------|-------------|
| [template_sensors.yaml](../../../homeassistant/packages/3d_printing/openhasp_display/sensors/template_sensors.yaml) | `sensor.print_time_remaining_formatted` | `p1b14` label | Converts the raw remaining-time sensor (integer minutes) into a human-readable `Xh Ym` or `Ym` string. Source: `sensor.ntk_ryansoffice_3dprinter_remaining_time`. |
| [template_sensors.yaml](../../../homeassistant/packages/3d_printing/openhasp_display/sensors/template_sensors.yaml) | `sensor.total_estimated_print_time` | `p1b4` arc max | Calculates total estimated print duration in minutes from the printer's start/end times. Used as the arc maximum so the remaining-time arc scales correctly. Source: `start_time` and `end_time` sensors. |
| [template_sensors.yaml](../../../homeassistant/packages/3d_printing/openhasp_display/sensors/template_sensors.yaml) | `sensor.print_end_time_friendly` | `p1b29` label | Formats estimated completion time for readability: same-day time, `tomorrow`, `on {Day}` within a week, and `on MM/DD/YYYY` beyond one week. Source: `sensor.ntk_ryansoffice_3dprinter_end_time`. |

> **Note:** These sensors can be created via the HA UI (Settings → Helpers → Template) or added to `configuration.yaml` under the `template:` key. See [template_sensors.yaml](../../../homeassistant/packages/3d_printing/openhasp_display/sensors/template_sensors.yaml) for both approaches.

## How It Works

1. **OpenHASP Custom Component** — The [openHASP integration](https://www.openhasp.com/0.7.0/integrations/home-assistant/howto/) in Home Assistant communicates with the ESP32 plate over MQTT. The plate configuration YAML (`officetouch5.yaml`) defines which UI objects on the display are bound to which Home Assistant entities.

2. **Data Flow**: When a sensor value changes in Home Assistant (e.g., print progress), the OpenHASP component automatically publishes the new value via MQTT to the plate, which updates the corresponding UI element (arc, label, colored rectangle, stacked segment geometry, etc.).

3. **Image Pushing**: The `Push Printer Image to Screen` automation watches for changes to the printer's cover image entity and pushes the updated image directly to the display using the `openhasp.push_image` service.

## Deployment

To deploy changes from this repo to Home Assistant:

1. **Plate config** — Copy `officetouch5.yaml` to your Home Assistant's `/config/openhasp/` directory.
2. **Automations** — Add the contents of each automation YAML file into your Home Assistant `automations.yaml` (as a list item with leading `- `), or use the HA UI to import them.
3. **Template sensors** — Create the helper sensors from `template_sensors.yaml`. Either:
   - **UI:** Settings → Devices & Services → Helpers → Create Helper → Template → Template a sensor — copy the name, template, and unit from the file.
   - **YAML:** Add the sensor definitions under the `template:` key in `configuration.yaml`.
4. **Reload** — In Home Assistant, go to **Developer Tools → YAML** and reload **OpenHASP**, **Automations**, and **Template Entities**.

## Dependencies

- [OpenHASP Custom Component](https://github.com/HASwitchPlate/openHASP-custom-component) installed in Home Assistant
- [Bambu Lab integration](https://github.com/greghesp/ha-bambulab) for printer sensor entities
- MQTT broker (e.g., Mosquitto) for HA ↔ ESP32 communication
- Template helper sensors defined in [template_sensors.yaml](../../../homeassistant/packages/3d_printing/openhasp_display/sensors/template_sensors.yaml) — must be created in HA before the plate config will work correctly


