# Printer Status Card Features: Research & Replication Guide

This document explains the two main interactive features of the
[ha-bambulab-cards](https://github.com/greghesp/ha-bambulab-cards) Print Status
card and details what can (and cannot) be replicated using standalone Home
Assistant YAML dashboard cards.

---

## Feature 1 – Print History & Timelapse Videos Popup

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
provided by the **ha-bambulab** integration (not a standard HA API).

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
