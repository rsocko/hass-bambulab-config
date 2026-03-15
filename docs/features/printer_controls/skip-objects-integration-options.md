# Skip Objects Integration Options

This note reverse-engineers how `ha-bambulab-cards` and `ha-bambulab` implement Skip Objects, then outlines practical implementation options for this repo.

## What Upstream Actually Does

From `greghesp/ha-bambulab-cards`:
- `print_control-card` opens a Skip Objects workflow and calls `bambu_lab.skip_objects`.
- Shared component `skip-objects` builds a list from:
  - `..._printable_objects` entity attribute `objects` (map of ID -> name)
  - `..._skipped_objects` entity attribute `objects` (list of skipped IDs)
- Final call is:
  - domain: `bambu_lab`
  - service: `skip_objects`
  - data: `{ device_id, objects: "id1,id2,id3" }`

From `greghesp/ha-bambulab`:
- Service `skip_objects` is registered in the integration service map.
- Coordinator normalizes and validates `objects` into `obj_list` integers.
- Integration publishes command:
  - `print.command = "skip_objects"`
  - `print.obj_list = [int, int, ...]`

## Key Constraints

- Skip list is effectively replaced on each call, not incrementally appended.
- Best practice is to send cumulative IDs when adding one object to skip.
- UI should guard on availability:
  - printing context active
  - printable object count in a sane range
  - MQTT encryption/hybrid-blocking can disable controls

## Options

### 1. Reuse Existing Upstream UI (recommended fastest)

Use `custom:ha-bambulab-print_control-card` directly, either inline or in popup.

Pros:
- Minimal maintenance.
- You keep canvas/image object picking and tested behavior.

Cons:
- Tied to upstream card UX.

Scaffold in this repo:
- `homeassistant/packages/3d_printing/printer_controls/dashboard_cards/skip-objects-launcher.yaml`
  - compact button that opens the skip objects popup (`custom:skip-objects-card`)
- `homeassistant/www/3d_printing/printer_controls/skip-objects-card.js`
  - interactive custom card that reads printable/skipped entities and calls `bambu_lab.skip_objects`

Dashboard resource registration required (via HA UI or API, **not** YAML):
- URL: `/local/3d_printing/printer_controls/skip-objects-card.js`
- Type: **JavaScript Module**

Register in HA: **Settings → Dashboards → Resources → Add Resource**

> **Note:** HA uses storage mode for resource management. Resources defined in YAML
> packages are silently ignored. See [Dashboard Deploy Behavior](../../repo/dashboard-deployment-behavior.md)
> section 3 for details.

The file `common/dashboards/_resources.yaml` is kept as a reference manifest of resource
URLs this repo provides; it is not loaded by HA at runtime.

Git-based deployment notes:
- Keep the JS file under `homeassistant/www/3d_printing/printer_controls/`.
- Use deploy allowlist profile `packages_www` so both package YAML and `www/` assets deploy together.
- Result on Home Assistant host:
  - `homeassistant/www/3d_printing/printer_controls/skip-objects-card.js` → `/config/www/3d_printing/printer_controls/skip-objects-card.js`
  - After deploy, register the `/local/...` URL as a Lovelace resource in HA UI/API (one-time step per new JS file).

### 2. Keep Native YAML UI + Service Wrapper (recommended flexible)

Use a custom dashboard section and call local scripts:
- `script.skip_print_object`
- `script.skip_print_objects_list`

Pros:
- No custom JS build/deploy needed.
- Easier to customize to your dashboard style.

Cons:
- No 2D pick-image click UX unless you embed upstream card.

Existing base in repo:
- `homeassistant/packages/3d_printing/printer_controls/scripts/skip_objects_script.yaml`
- `homeassistant/packages/3d_printing/printer_controls/dashboard_cards/skip-objects-card.yaml`

### 3. Build a New Custom Card (longer-term)

Create your own Lovelace custom card under `homeassistant/www/`.

Suggested architecture:
- Card reads printable + skipped object attributes.
- Card renders list/grid/canvas per your UX.
- Card calls `hass.callService("bambu_lab", "skip_objects", {...})`.
- Keep service call logic tiny and delegate merge behavior to existing scripts when possible.

Pros:
- Full control.

Cons:
- You own lifecycle, compatibility, and testing.

Scaffold now added in this repo:
- `homeassistant/www/3d_printing/printer_controls/skip-objects-card.js`
- `homeassistant/packages/3d_printing/printer_controls/dashboard_cards/skip-objects-card.yaml`

Resource registration required (one-time, via HA UI/API):
- URL: `/local/3d_printing/printer_controls/skip-objects-card.js`
- Type: JavaScript Module

## Suggested Path

1. Start with Option 1 popup launcher to unblock daily use immediately.
2. Keep Option 2 scripts as your stable API layer for automations and one-click actions.
3. Only build Option 3 if you need UX not achievable with popup + YAML composition.

