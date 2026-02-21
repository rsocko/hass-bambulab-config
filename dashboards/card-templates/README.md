# Button Card Templates

This directory contains reusable `button-card` templates for the 3D printer dashboards.
Each file defines a single named template that can be used with `custom:button-card` in any
Home Assistant Lovelace dashboard.

## Templates

| File | Template Name | Purpose |
|------|--------------|---------|
| `ams_tray_label.yaml` | `ams_tray_label` | Slot label card (A1, A2, B1, etc.) — shows the tray name with active-spool highlight |
| `ams_tray_detail.yaml` | `ams_tray_detail` | Full tray info card — displays filament name, desiccant status, remaining weight, and print weight |
| `ams_tray_popup.yaml` | `ams_tray_popup` | Tap-action popup — opens a detailed spool info dialog (inherited by `ams_tray_detail`) |

### Template Inheritance

`ams_tray_detail` inherits its `tap_action` from `ams_tray_popup` via button-card template
inheritance. To modify the popup content, edit `ams_tray_popup.yaml`. To modify the tray
card appearance, edit `ams_tray_detail.yaml`.

## Usage

There are two ways to make these templates available to your dashboards. Choose the one
that fits your workflow.

---

### Option A — Global templates via `configuration.yaml` (Recommended for UI-editor users)

Adding templates to `configuration.yaml` loads them globally so they are available to
**all** dashboards, including dashboards managed through the Home Assistant UI/raw editor.
The `button_card_templates:` block does **not** need to be present inside the dashboard YAML
at all — you can paste a much smaller dashboard file into the raw editor.

**Step 1.** Add the following to your `configuration.yaml`:

```yaml
button_card_templates: !include_dir_merge_named /config/dashboards/card-templates/
```

> **Note:** Use the absolute path from your Home Assistant config root (usually `/config/`).

**Step 2.** Restart Home Assistant so the templates are loaded.

**Step 3.** (Optional) When pasting `lovelace.3d_printing` into the Raw Configuration Editor,
you can remove the entire `button_card_templates:` block at the bottom of the file — the
globally-loaded templates will be used instead.

---

### Option B — Inline templates (standalone, no `configuration.yaml` changes)

The `lovelace.3d_printing` file already includes the full inline templates at the bottom
under `button_card_templates:`. Simply paste the entire file as-is into the Raw
Configuration Editor — no `configuration.yaml` changes required.

---

### In Another Dashboard

To reuse these templates in a different dashboard file (not the raw editor), add the
following to that dashboard's YAML configuration:

```yaml
button_card_templates: !include_dir_merge_named /config/dashboards/card-templates/
```

> **Note:** Use the absolute path from the Home Assistant config root (usually `/config/`).
> The relative path `card-templates/` only works when the dashboard YAML file is in the
> same directory as `card-templates/`.

## Template Variables

### `ams_tray_label`

| Variable | Required | Description |
|----------|----------|-------------|
| `trayName` | Yes | Display label for the slot (e.g. `A1`, `B3`, `External`) |
| `trayEntityId` | Yes | Entity ID of the AMS tray sensor (used to detect active spool) |

### `ams_tray_detail` and `ams_tray_popup`

| Variable | Required | Description |
|----------|----------|-------------|
| `tray` | Yes | Tray key in the `spoolman_tray_map` (e.g. `ams_1_tray_1`, `external_spool`) |
| `trayLabel` | Yes | Human-readable label shown in the popup header (e.g. `AMS 1 · Slot 1`) |
| `trayEntityId` | Yes | Entity ID of the AMS tray sensor |
| `printWeightKey` | Yes | Attribute key in `sensor.ntk_ryansoffice_3dprinter_print_weight` (e.g. `AMS 1 Tray 1`) |

## Configuration

The templates read from several sensor entities. Update the following references inside
the template files to match your setup:

| Reference | File | Description |
|-----------|------|-------------|
| `sensor.spoolman_tray_map` | `ams_tray_detail.yaml`, `ams_tray_popup.yaml` | Spoolman tray-to-spool mapping sensor (defined in `templates.yaml`) |
| `sensor.spoolman_filament_totals` | `ams_tray_popup.yaml` | Filament weight totals sensor (defined in `templates.yaml`) |
| `sensor.ntk_ryansoffice_3dprinter_print_weight` | `ams_tray_detail.yaml`, `ams_tray_popup.yaml` | Active print weight sensor |
| `SPOOLMAN_BASE_URL` | `ams_tray_popup.yaml` | Base URL for Spoolman web UI (line near top of `tap_action`) |

## Adding New Templates

To add a new template:

1. Create a new YAML file in this directory, e.g. `my_template.yaml`
2. Define the template with its name as the top-level key:

   ```yaml
   my_template:
     type: custom:button-card
     name: My Template
     # ... template definition
   ```

3. The template is automatically available in any dashboard using
   `!include_dir_merge_named card-templates/` — no other changes needed.
