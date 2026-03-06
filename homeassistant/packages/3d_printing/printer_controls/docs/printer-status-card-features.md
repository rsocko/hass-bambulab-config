# Printer Status Card Features: Research & Replication Guide

This document explains the two main interactive features of the
[ha-bambulab-cards](https://github.com/greghesp/ha-bambulab-cards) Print Status
card and details what can (and cannot) be replicated using standalone Home
Assistant YAML dashboard cards.

---

## Feature 1 – Print History & Timelapse Videos Popup

### Where does the API come from?

The API is **not** built into the Bambu Lab printer itself. It is provided
entirely by the **ha-bambulab Home Assistant integration**
([greghesp/ha-bambulab](https://github.com/greghesp/ha-bambulab)).

When the integration is installed it registers two custom HTTP views inside
Home Assistant's own web server (`custom_components/bambu_lab/__init__.py`):

```python
class PrintHistoryAPIView(HomeAssistantView):
    url = "/api/bambu_lab/print_history"
    requires_auth = True          # ← HA long-lived access token required

class VideoAPIView(HomeAssistantView):
    url = "/api/bambu_lab/videos"
    requires_auth = True
```

Both views:
1. Iterate over every configured Bambu Lab printer in `hass.data["bambu_lab"]`.
2. Call `coordinator.get_cached_files(file_type='prints'|'timelapse')` — this
   reads files that the integration has **already downloaded and cached to disk**
   from the printer over the local network (MQTT + FTP).
3. Return a JSON response sorted newest-first.

The **files are cached by the integration**, not fetched live from the printer on
each API request. The integration must have the *file cache* feature enabled in its
configuration settings for print history and timelapse files to appear.

### How it works in ha-bambulab-cards

The **Print History** button (list icon) in the status card opens a popup implemented
by the `<print-history-popup>` LitElement web component
(`src/cards/shared-components/print-history-popup/print-history-popup.ts`).

The popup has two tabs:

| Tab | Data source | Format |
|-----|-------------|--------|
| Print History | `GET /api/bambu_lab/print_history` | JSON — `{ files: [...], total_size_bytes }` |
| Timelapse Videos | `GET /api/bambu_lab/videos` | JSON — `{ videos: [...], total_size_bytes }` |

Both endpoints require an `Authorization: Bearer <access_token>` header and are
provided by the **ha-bambulab** integration (not a standard HA API and not by the
printer).

Each call is authenticated using `this._hass.auth.data.access_token` — a token that
is only available inside a Lit-based custom card running in the HA frontend context.
This means the authentication cannot be replicated in plain YAML templates, which
have no access to the bearer token.

#### File thumbnails
Thumbnails for each print file are loaded from:
```
GET /api/bambu_lab/file_cache/<thumbnail_path>
```
They are fetched with the same bearer token and converted to object-URLs for display.

#### Timelapse video playback & download
Timelapse video files are stored locally at:
```
/local/media/ha-bambulab/<relative_path>
```
That path corresponds to `<config>/www/media/ha-bambulab/` on the HA host, which HA
serves as static files under `/local/`.

#### Print Again button
The **Print Again** button is enabled only when the printer is reachable via
unencrypted MQTT (the `controlBlocked` prop is `false`).  It opens a
`<print-settings-popup>` that calls `bambu_lab.print_project_file` with the
selected file path and print settings.

---

### What can be replicated in YAML

| Feature | Replicable in YAML? | Notes |
|---------|--------------------|----|
| Timelapse video browsing | ✅ Yes | Use the built-in **Media Browser** card pointing at `media-source://media_source/local/ha-bambulab/` |
| Print history file list | ❌ No | Requires authenticated REST API call not available to YAML templates |
| Print file thumbnails | ❌ No | Same REST API restriction |
| Print Again | ❌ No | Requires MQTT control + authenticated API |

#### Recommended alternative for Timelapse Videos

Add a **Media Player / Browser** card to your dashboard:

```yaml
type: media-control
entity: media_player.your_media_player   # optional, for cast target
```

Or use the **Picture Glance** card to show the most recent timelapse thumbnail if
you expose it as an image entity via a template sensor.

For full timelapse browsing, the best in-dashboard option remains using the
ha-bambulab-cards Print Status card (the popup component is only available
inside that card) or navigating to **Media → Local Media → ha-bambulab** in the
HA sidebar.

---

## Feature 2 – Show Controls (Axis Movement + Extruder)

### How it works in ha-bambulab-cards

When the user taps the **camera-control** icon in the extra-controls row of the
a1-screen-card (`src/cards/print-status-card/a1-screen/a1-screen-card.ts`), the
card switches to `Page.Controls` which renders `#renderControlsPage()`.

The controls page contains three sub-panels:

#### XY Joypad (`#renderMoveAxis`)
An inline SVG renders a circular joystick with eight clickable arc segments:

| Segment | Axis | Distance |
|---------|------|----------|
| Inner left | X | −1 mm |
| Outer left | X | −10 mm |
| Inner right | X | +1 mm |
| Outer right | X | +10 mm |
| Inner top | Y | +1 mm |
| Outer top | Y | +10 mm |
| Inner bottom | Y | −1 mm |
| Outer bottom | Y | −10 mm |
| Centre circle | — | HOME |

Each click calls:
```typescript
this._hass.callService("bambu_lab", "move_axis", {
  device_id: this._device_id,
  axis: "X" | "Y" | "Z" | "HOME",
  distance: number
});
```

Tapping the **Home** centre circle shows a confirmation dialog before issuing the
call because homing drives the bed toward the nozzle and can damage a model.

#### Bed (Z) Controls (`#renderBedMoveControls`)
Five vertical buttons: ±10 mm, ±1 mm, and a decorative flatbed icon.
Uses the same `bambu_lab.move_axis` service with `axis: "Z"`.

> **Z-axis sign convention** – In the source code, `Z: -1` moves the bed *up*
> (nozzle closer to bed) and `Z: +1` moves it *down*.  The bed is on the Z axis
> and the nozzle is stationary.

#### Extruder Controls (`#renderExtruderControls`)
Up (retract) / Down (extrude) buttons calling:
```typescript
this._hass.callService("bambu_lab", "extrude_retract", {
  device_id: this._device_id,
  type: "retract" | "extrude"
});
```

The button is blocked when `isMqttEncryptionEnabled()` returns `true` (cloud-only
connection) — the service itself will fail if the printer is not reachable via
local MQTT.

---

### Standalone YAML replication

The `printer-movement-controls.yaml` card in this directory is a standalone
button-card implementation of the entire controls page.

**Controls provided:**

| Button | Service | Parameters |
|--------|---------|------------|
| ←← / →→ (XY) | `bambu_lab.move_axis` | axis: X, distance: ∓10 |
| ← / → (XY) | `bambu_lab.move_axis` | axis: X, distance: ∓1 |
| ↑↑ / ↓↓ (XY) | `bambu_lab.move_axis` | axis: Y, distance: ±10 |
| ↑ / ↓ (XY) | `bambu_lab.move_axis` | axis: Y, distance: ±1 |
| 🏠 Home | `bambu_lab.move_axis` | axis: HOME (with confirmation) |
| ↑↑ / ↓↓ (Z) | `bambu_lab.move_axis` | axis: Z, distance: ∓10 |
| ↑ / ↓ (Z) | `bambu_lab.move_axis` | axis: Z, distance: ∓1 |
| ↑ Retract | `bambu_lab.extrude_retract` | type: retract |
| ↓ Extrude | `bambu_lab.extrude_retract` | type: extrude |

**Prerequisites:**
- ha-bambulab integration installed and a printer configured
- `custom:button-card` installed (HACS)
- The `device_id` in the YAML must match your printer's device ID
  (currently `210dfdfa64085e8cf073e50eae757d90`)

**Adding to your dashboard:**

Option A — always visible:
```yaml
- !include ../../printer_controls/dashboard_cards/printer-movement-controls.yaml
```

Option B — toggle-visible (via `input_boolean.show_movement_controls`):
```yaml
- type: custom:button-card
  entity: input_boolean.show_movement_controls
  name: Movement Controls
  icon: mdi:camera-control
  tap_action:
    action: toggle

- type: conditional
  conditions:
    - condition: state
      entity: input_boolean.show_movement_controls
      state: "on"
  card: !include ../../printer_controls/dashboard_cards/printer-movement-controls.yaml
```

**Limitations vs the original card:**
- The original uses an elegant circular SVG joypad; the YAML version uses a
  button grid — functionally identical but visually different.
- No automatic "controls blocked" detection when MQTT encryption is enabled.
  The service call will simply fail silently.  Add a conditional card if you
  want to hide the controls when `binary_sensor.*_mqtt_encryption` is `on`.

---

## Feature 3 – Safety Controls & Guards

### Is movement blocked during an active print?

**Short answer: the ha-bambulab-cards card does NOT check print status — the
only software guard it enforces is the MQTT encryption check.  The Bambu
printer firmware is the real safety net.**

### What ha-bambulab-cards checks

#### Controls page access (`#isControlsPageDisabled`)

```typescript
#isControlsPageDisabled() {
  return this.#isMqttEncryptionEnabled();
}
```

The camera-control button that opens the Controls page is disabled **only**
when MQTT encryption is active (i.e. the printer is on a cloud-only
connection).  There is **no check for active printing state** — the user can
open the Controls page and send axis movement commands even while a print is
running.

#### Home confirmation dialog

The *only* mid-operation safety UX in the Controls page is a confirmation
dialog shown before issuing the HOME command:

> "This will bring the heat bed to the nozzle.  If there is a model on the
> heat bed it will collide, possibly resulting in damage to the model or the
> printer."

All other axis movements (X/Y/Z) are issued immediately with no
confirmation.

#### Extruder error display

Extruder calls use `returnResponse: true` so the result is awaited.  If the
printer firmware returns an `Error` field the card shows it in a dialog.
There is no pre-flight state check in the card itself.

#### Print Again (`controlBlocked` prop)

In the `<print-history-popup>`, the **Print Again** button is blocked when:

```typescript
controlBlocked = this.#isMqttEncryptionEnabled() || this.#isHybridMqttConnection()
```

This means Print Again is disabled when:
1. MQTT encryption is on (cloud-only connection — no local MQTT write access)
2. Hybrid mode is active (MQTT + cloud — partial control only)

There is also **no active-print check** on Print Again.  The Bambu printer
firmware will reject a new print job if one is already running; the card
itself does not prevent the attempt.

---

### What the ha-bambulab integration checks

In `coordinator.py`, `_handle_service_call_event` runs this check before
executing **any write action** (move, extrude, skip, print, etc.):

```python
if self.get_model().print_fun.mqtt_signature_required:
    LOGGER.error("Printer firmware requires mqtt encryption.  All control actions are blocked.")
    return False
```

Beyond that gate, individual service handlers do minimal validation:

| Service | Integration-level guard |
|---------|------------------------|
| `move_axis` | Validates `axis` is X/Y/Z/HOME and `abs(distance) ≤ 100` |
| `extrude_retract` | Has an optional `force` parameter; if `force=False` (default) the printer firmware rejects below 170 °C |
| `print_project_file` | No active-print check; firmware rejects if already printing |
| All others | No print-state guard |

**There is no integration-level guard that prevents movement or extrusion
while a print is in progress.**

---

### Does the Bambu printer firmware enforce the guard?

Yes, to a limited degree.  The `move_axis` service sends raw GCode via the
`gcode_line` MQTT command:

```python
MOVE_AXIS_GCODE = (
    "M211 S\n"          # save current endstop state
    "M211 X1 Y1 Z1\n"   # enable software endstops
    "M1002 push_ref_mode\n"
    "G91 \n"             # relative positioning
    "G1 {axis}{distance}.0 F{speed}\n"
    "M1002 pop_ref_mode\n"
    "M211 R\n"           # restore endstop state
)
```

The `M1002 push_ref_mode` / `pop_ref_mode` pair is Bambu-specific GCode.  In
practice:

- **During an active print**, the Bambu firmware *may* queue the GCode behind
  the print buffer rather than executing it immediately, which means the
  move will be delayed until the current print command finishes — potentially
  interrupting the layer.  Community testing indicates behaviour varies by
  printer model and firmware version.
- **Extrusion** is blocked by the firmware below 170 °C unless `force: true`
  is passed.  This is a firmware-enforced temperature floor, not an
  integration or card check.
- **Homing (G28)** during a print will almost certainly crash the nozzle into
  the model.  There is no firmware guard preventing this — the confirmation
  dialog in the card is the only warning.

**In summary: do not use the movement controls while printing.  The
responsibility for safe operation is entirely on the user; neither the card
nor the integration will prevent you from issuing a potentially damaging
command.**

---

### How the standalone YAML card compares

| Safety check | ha-bambulab-cards | YAML `printer-movement-controls.yaml` |
|---|---|---|
| MQTT encryption → disable all | ✅ Disables Controls page button | ⚠️ Warning banner only |
| Active print → disable movement | ❌ Not checked | ⚠️ Warning banner only |
| Home → confirmation dialog | ✅ Yes | ✅ Yes (button-card `confirmation:`) |
| Extruder temperature floor | ✅ Firmware + error dialog | ✅ Firmware enforced |
| Print Again blocked during print | ❌ Not checked | N/A (Print Again not replicable in YAML) |

To make the YAML controls page more conservative, you can wrap it in a
`conditional` card that hides it while printing:

```yaml
- type: conditional
  conditions:
    - condition: state
      entity: sensor.YOUR_PRINTER_current_stage
      state_not: printing
  card: !include ../../printer_controls/dashboard_cards/printer-movement-controls.yaml
```
