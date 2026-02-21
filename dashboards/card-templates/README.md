# Card Templates

This directory contains the card component definitions for the AMS tray slot cards.
These files document the individual card logic that is **embedded inline** in the
`decluttercard:` template block in each dashboard. No `configuration.yaml` entry is needed.

## Files

| File | Purpose |
|------|---------|
| `ams_tray_label.yaml` | Label card definition — slot name (A1, A2, B1, etc.) + active-spool highlight |
| `ams_tray_detail.yaml` | Detail card definition — filament name, desiccant status, remaining weight, print weight |
| `ams_tray_popup.yaml` | Popup tap-action definition — merged into the detail card (no separate template needed) |
| `ams_tray_slot.yaml` | Usage guide — documents the `ams_tray_slot` declutter template and cross-dashboard setup |

## How the Pieces Fit Together

The `decluttercard:` block in each dashboard YAML embeds the complete card definitions from
`ams_tray_label.yaml`, `ams_tray_detail.yaml`, and `ams_tray_popup.yaml` inline — merged into
two `custom:button-card` entries. declutter-card substitutes the per-slot variable values;
button-card renders each card with the correct data.

```
decluttercard: ams_tray_slot
├── custom:button-card  ← ams_tray_label.yaml content (label + active highlight)
└── custom:button-card  ← ams_tray_detail.yaml + ams_tray_popup.yaml merged (detail + popup)
```

## Usage

**No `configuration.yaml` changes required.** The template block is pasted directly into the
dashboard YAML.

**Step 1.** Install the required custom cards via HACS → Frontend:
- **declutter-card** — provides `custom:declutter-card`
- **button-card** — provides `custom:button-card` (used inside the template)
- **browser-mod** — required for the spool info popup

**Step 2.** Copy the entire `decluttercard:` block from `lovelace.3d_printing` (everything
from line `decluttercard:` down to but not including `views:`) and paste it at the **top** of
your dashboard YAML, before the `views:` key.

**Step 3.** Use `custom:declutter-card` wherever you want an AMS tray slot:

```yaml
- type: custom:declutter-card
  template: ams_tray_slot
  variables:
    - trayName: A1
    - trayEntityId: sensor.YOUR_PRINTER_ams_1_tray_1
    - tray: ams_1_tray_1
    - trayLabel: AMS 1 · Slot 1
    - printWeightKey: AMS 1 Tray 1
```

A full four-slot AMS row:

```yaml
- type: horizontal-stack
  cards:
    - type: custom:declutter-card
      template: ams_tray_slot
      variables:
        - trayName: A1
        - trayEntityId: sensor.YOUR_PRINTER_ams_1_tray_1
        - tray: ams_1_tray_1
        - trayLabel: AMS 1 · Slot 1
        - printWeightKey: AMS 1 Tray 1
    - type: custom:declutter-card
      template: ams_tray_slot
      variables:
        - trayName: A2
        - trayEntityId: sensor.YOUR_PRINTER_ams_1_tray_2
        - tray: ams_1_tray_2
        - trayLabel: AMS 1 · Slot 2
        - printWeightKey: AMS 1 Tray 2
    - type: custom:declutter-card
      template: ams_tray_slot
      variables:
        - trayName: A3
        - trayEntityId: sensor.YOUR_PRINTER_ams_1_tray_3
        - tray: ams_1_tray_3
        - trayLabel: AMS 1 · Slot 3
        - printWeightKey: AMS 1 Tray 3
    - type: custom:declutter-card
      template: ams_tray_slot
      variables:
        - trayName: A4
        - trayEntityId: sensor.YOUR_PRINTER_ams_1_tray_4
        - tray: ams_1_tray_4
        - trayLabel: AMS 1 · Slot 4
        - printWeightKey: AMS 1 Tray 4
```

## Cross-Dashboard Reuse

Because the `decluttercard:` block is self-contained, adding AMS tray cards to a second
dashboard requires only:

1. Copy the `decluttercard:` block to the top of the new dashboard YAML.
2. Use `custom:declutter-card` with your variables — all card logic is already embedded.

No `configuration.yaml` changes, no HA restart, no file copies needed.

## Template Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `trayName` | Yes | Display label for the slot (e.g. `A1`, `B3`, `External`) |
| `trayEntityId` | Yes | Entity ID of the AMS tray sensor (active-spool highlight + popup fallback) |
| `tray` | Yes | Tray key in the `spoolman_tray_map` (e.g. `ams_1_tray_1`, `external_spool`) |
| `trayLabel` | Yes | Human-readable label shown in the popup header (e.g. `AMS 1 · Slot 1`) |
| `printWeightKey` | Yes | Attribute key in `sensor.ntk_ryansoffice_3dprinter_print_weight` (e.g. `AMS 1 Tray 1`) |

## Sensor References

The inline card definitions reference these sensors — update them to match your setup by
editing the `decluttercard:` block in the dashboard YAML:

| Reference | Description |
|-----------|-------------|
| `sensor.spoolman_tray_map` | Spoolman tray-to-spool mapping sensor (defined in `templates.yaml`) |
| `sensor.spoolman_filament_totals` | Filament weight totals sensor (defined in `templates.yaml`) |
| `sensor.ntk_ryansoffice_3dprinter_print_weight` | Active print weight sensor |
| `SPOOLMAN_BASE_URL` in tap_action JS | Base URL for Spoolman web UI |

## Modifying the Card Definitions

To change card appearance or behaviour, edit the `decluttercard:` block in your dashboard
YAML directly. The component files in this directory (`ams_tray_label.yaml`,
`ams_tray_detail.yaml`, `ams_tray_popup.yaml`) are reference documentation — update them
to keep them in sync if you make changes to your dashboard.

## Troubleshooting

### "custom:declutter-card is not a valid card"

Install **declutter-card** via HACS → Frontend. Search for "declutter-card" and install it,
then hard-reload your browser (`Ctrl+Shift+R` / `Cmd+Shift+R`).

### Cards show but variables are not substituted (`[[trayName]]` appears literally)

The `decluttercard:` block is missing or malformed. Confirm the YAML anchor matches the
template name: `- &ams_tray_slot` in the `decluttercard:` list and `template: ams_tray_slot`
in each `custom:declutter-card` card.

### "custom:button-card is not a valid card"

Install **button-card** via HACS → Frontend (search for "button-card"), then hard-reload.

### Popup does not open when tapping a tray card

Install **browser-mod** via HACS → Frontend and confirm it is configured. The popup uses
`browser_mod.popup` which requires browser-mod to be active.
