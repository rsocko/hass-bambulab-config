# Card Templates

This directory contains the source definitions for the three AMS tray `button-card` templates
used in the 3D printer dashboards. These files are the single source of truth — when you edit
a template, update the corresponding file here so the repo stays current.

## Files

| File | Template Name | Purpose |
|------|--------------|---------|
| `ams_tray_label.yaml` | `ams_tray_label` | Slot label card (A1, A2, B1, etc.) — shows tray name + active-spool highlight |
| `ams_tray_detail.yaml` | `ams_tray_detail` | Full tray info card — filament name, desiccant status, remaining weight, print weight |
| `ams_tray_popup.yaml` | `ams_tray_popup` | Tap-action popup — spool info dialog (inherited by `ams_tray_detail`) |

### Template Inheritance

`ams_tray_detail` inherits its `tap_action` from `ams_tray_popup` via button-card's template
inheritance (`template: - ams_tray_popup`). Both must be defined in the same
`button_card_templates:` block. To modify the popup, edit `ams_tray_popup.yaml`. To modify
the card appearance, edit `ams_tray_detail.yaml`.

## How Templates are Loaded

`button_card_templates` is a **Lovelace dashboard-level** key. button-card reads it from the
dashboard config object (`ll.config`), not from `configuration.yaml`. This is why adding
`button_card_templates:` to `configuration.yaml` fails the HA config check — HA's config
validator doesn't know about it because it's not a Home Assistant integration key.

The templates must be defined in the **dashboard YAML** itself, in a `button_card_templates:`
block before `views:`. They are then available to all cards in that dashboard using
`template: ams_tray_label` etc.

**The `lovelace.3d_printing` file includes the full `button_card_templates:` block** — paste
the entire file into the Raw Configuration Editor and the templates are immediately usable.

## Usage — In a Dashboard

The `button_card_templates:` block at the top of `lovelace.3d_printing` contains all three
templates. Each AMS slot card is a `vertical-stack` with two `custom:button-card` entries:

```yaml
- type: vertical-stack
  card_mod:
    style: ':host { height: 100%; } #root { height: 100%; } #root > :last-child { flex: 1; }'
  cards:
    - type: custom:button-card
      template: ams_tray_label
      variables:
        trayName: A1
        trayEntityId: sensor.YOUR_PRINTER_ams_1_tray_1
    - type: custom:button-card
      template: ams_tray_detail
      variables:
        tray: ams_1_tray_1
        trayLabel: AMS 1 · Slot 1
        trayEntityId: sensor.YOUR_PRINTER_ams_1_tray_1
        printWeightKey: AMS 1 Tray 1
```

## Cross-Dashboard Reuse

To reuse these templates in another dashboard:

1. Copy the entire `button_card_templates:` block from `lovelace.3d_printing` (everything
   from `button_card_templates:` down to but not including `views:`) and paste it at the top
   of the target dashboard YAML, before `views:`.
2. Use the cards as shown above — the templates are now available in that dashboard too.

There is no global/configuration.yaml mechanism for button-card templates in a standard HA
installation. Each dashboard that uses them must include the `button_card_templates:` block.

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

## Sensor References

Update these references inside the template files (and the corresponding `button_card_templates:`
block in your dashboard) to match your setup:

| Reference | Description |
|-----------|-------------|
| `sensor.spoolman_tray_map` | Spoolman tray-to-spool mapping sensor (defined in `templates.yaml`) |
| `sensor.spoolman_filament_totals` | Filament weight totals sensor (defined in `templates.yaml`) |
| `sensor.ntk_ryansoffice_3dprinter_print_weight` | Active print weight sensor |
| `SPOOLMAN_BASE_URL` in tap_action JS | Base URL for Spoolman web UI |

## Updating a Template

1. Edit the appropriate `.yaml` file here.
2. Copy the updated content into the `button_card_templates:` block in your dashboard YAML
   (under the matching template name key).
3. Save the dashboard — the card will update immediately (no HA restart needed).

## Troubleshooting

### "Button-card template 'ams_tray_label' is missing!"

The `button_card_templates:` block is missing from the dashboard. Confirm the pasted YAML
starts with `button_card_templates:` (before `views:`). If you accidentally deleted it,
copy it back from the `lovelace.3d_printing` file in this repository.

### "custom:button-card is not a valid card"

Install **button-card** via HACS → Frontend (search for "button-card"), then hard-reload
your browser (`Ctrl+Shift+R` / `Cmd+Shift+R`).

### Popup does not open when tapping a tray card

Install **browser-mod** via HACS → Frontend and confirm it is configured. The popup uses
`browser_mod.popup` which requires browser-mod to be active.
