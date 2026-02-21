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

Templates are loaded globally via `configuration.yaml`, making them available to all dashboards
including UI-managed ones.

**Step 1.** Copy the `dashboards/card-templates/` directory from this repository into your
Home Assistant config directory so the layout looks like this:

```
/config/                          ← HA config root (where configuration.yaml lives)
├── configuration.yaml
└── dashboards/
    └── card-templates/
        ├── ams_tray_label.yaml
        ├── ams_tray_detail.yaml
        └── ams_tray_popup.yaml
```

**Step 2.** Add the following to your `configuration.yaml`:

```yaml
button_card_templates: !include_dir_merge_named dashboards/card-templates/
```

> **Note:** The path is relative to your config root (`/config/`). If you prefer an absolute
> path, use `/config/dashboards/card-templates/`. Both forms work.

**Step 3.** Before restarting, validate your configuration: in Home Assistant go to
**Developer Tools → YAML → Check Configuration**. Fix any errors it reports, then restart.

**Step 4.** Restart Home Assistant so the templates are loaded.

> **Important:** There is no reload service for `button_card_templates`. Any future changes
> to files in `dashboards/card-templates/` require another Home Assistant restart before the
> updated templates appear in Lovelace.

**Step 5.** Confirm the templates loaded: go to **Settings → System → Logs** immediately
after restart and search for `button_card_templates` or `card-templates`. Any path or YAML
error here will prevent the templates from loading.

**Step 6.** Paste `lovelace.3d_printing` into the Raw Configuration Editor — no
`button_card_templates:` block required in the dashboard YAML.

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

3. The template will be available in any dashboard using
   `!include_dir_merge_named card-templates/` after the next Home Assistant restart.

## Troubleshooting

### "Integration error: button_card_templates - Integration 'button_card_templates' not found"

This error appears in **Developer Tools → YAML → Check Configuration** when Home Assistant
does not recognise `button_card_templates` as a valid configuration key. The key is registered
by the `button-card` custom component — if that component is not installed, HA reports it as
an unknown integration.

**Cause:** `button-card` was not installed via HACS, or was installed only as a manual
frontend resource (a `.js` file copied to `www/`) without the accompanying custom component.
Installing via HACS is required because the HACS package includes both the frontend resource
*and* a backend custom component that registers `button_card_templates` as a valid
configuration key.

**Fix:**
1. Open **HACS → Frontend** and install **button-card** (search for "button-card").
2. **Restart Home Assistant** so the custom component is loaded.
3. Re-run **Developer Tools → YAML → Check Configuration** — the error should be gone.
4. Continue with the normal setup steps above.

---

### "Button-card template '…' is missing!" Error

This error means Home Assistant has not yet loaded the templates from `configuration.yaml`.
Work through these steps in order:

1. Confirm your files are laid out correctly under the HA config root:

   ```
   /config/                          ← HA config root (where configuration.yaml lives)
   ├── configuration.yaml
   └── dashboards/
       └── card-templates/
           ├── ams_tray_label.yaml
           ├── ams_tray_detail.yaml
           └── ams_tray_popup.yaml
   ```

2. Confirm `configuration.yaml` contains (at the root level, not nested):
   ```yaml
   button_card_templates: !include_dir_merge_named dashboards/card-templates/
   ```
   Both the relative path above and the absolute path
   `/config/dashboards/card-templates/` work. The line must not be
   indented under any other key.

3. **Before restarting,** go to **Developer Tools → YAML → Check Configuration**.
   If it reports any errors, fix them first. A YAML or schema error anywhere in the
   included files will cause HA to silently skip loading `button_card_templates`.

4. **Restart Home Assistant** — a configuration reload or dashboard reload is not
   sufficient. `button_card_templates` are only read at startup.

5. After restart, go to **Settings → System → Logs** and search for
   `button_card_templates` or `card-templates`. Any error logged here explains why
   the templates did not load.

6. After HA has fully restarted, hard-reload your browser
   (`Ctrl+Shift+R` / `Cmd+Shift+R`) to clear any cached dashboard state.
