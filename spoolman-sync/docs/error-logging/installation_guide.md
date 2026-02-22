# Installation Guide: Persistent Error Logging System

This guide walks you through installing the persistent error logging system for Spoolman sync failures.

## Prerequisites

Before installing, ensure you have:
- Home Assistant configured and running
- Bambu Lab integration installed and configured
- Spoolman integration installed and configured
- Existing Spoolman sync automations working (from this repository)

## Step 1: Add Input Helpers

The input helpers provide persistent storage for error data.

### Option A: Via Home Assistant UI (Recommended)

1. Go to **Settings** → **Devices & Services** → **Helpers**
2. Click **"+ CREATE HELPER"**
3. Create each helper manually using the table below:

| Type | Name | Entity ID | Max Length | Icon |
|------|------|-----------|------------|------|
| Text | Current Print Job Info | `input_text.print_job_current` | 255 | mdi:printer-3d |
| Text | Print Job AMS Tray Data | `input_text.print_job_ams_trays` | 1000 | mdi:file-cabinet |
| Text | Last Spoolman Sync Error | `input_text.spoolman_sync_last_error` | 500 | mdi:alert-circle |
| Text | Spoolman Sync Error Log | `input_text.spoolman_sync_error_log` | 2000 | mdi:text-box-multiple |
| Toggle | Spoolman Sync Error Active | `input_boolean.spoolman_sync_error_active` | - | mdi:alert |
| Date/Time | Last Sync Error Time | `input_datetime.spoolman_sync_last_error_time` | - | mdi:clock-alert |

### Option B: Via Configuration File

If you manage Home Assistant configuration via YAML files, use the **packages**
mechanism.  This is the only correct approach because `print_job_tracking_helpers.yaml`
defines multiple top-level sections (`input_text:`, `input_boolean:`,
`input_datetime:`), and loading it under a single key such as
`input_text: !include ...` would produce incorrect nested YAML.

**Recommended folder structure:**

```
/config/
├── configuration.yaml
└── packages/
    └── bambulab/
        ├── print_cost_helpers.yaml          ← spoolman-sync/print_cost_helpers.yaml
        ├── print_job_tracking_helpers.yaml  ← spoolman-sync/print_job_tracking_helpers.yaml
        └── print_weight_persistence.yaml    ← spoolman-sync/print_weight_persistence.yaml
```

1. Copy `print_job_tracking_helpers.yaml` (and the other helper files) into
   `/config/packages/bambulab/`.

2. Add the following to `configuration.yaml` (merge with an existing
   `homeassistant.packages` block if you already have one):

   ```yaml
   homeassistant:
     packages:
       bambulab_print_cost:         !include packages/bambulab/print_cost_helpers.yaml
       bambulab_print_weight:       !include packages/bambulab/print_weight_persistence.yaml
       bambulab_print_job_tracking: !include packages/bambulab/print_job_tracking_helpers.yaml
   ```

   > **Have other helpers defined elsewhere?**  Packages merge cleanly with any
   > existing `input_text:` or other sections in `configuration.yaml` — no
   > changes to those sections are needed.  Each package key (e.g.
   > `bambulab_print_job_tracking`) simply contributes its sections to the
   > merged configuration.

3. Restart Home Assistant or reload the configuration.

## Step 2: Add Print Started Automation

This automation captures AMS tray data when a print starts.

1. Go to **Settings** → **Automations & Scenes** → **Automations**
2. Click **"+ CREATE AUTOMATION"**
3. Choose **"Create new automation"** → **"Start with an empty automation"**
4. Click the **⋮** menu (top right) → **"Edit in YAML"**
5. Copy the entire contents of `print_started-capture_print_data.yaml`
6. Paste into the YAML editor
7. **Important**: Update the `device_id` on line 6 to match your printer:
   - Click on the trigger section
   - Change device to your Bambu Lab printer
   - The correct device_id will be populated
8. Save the automation with name: **"Print Started - Capture Print Data"**

## Step 3: Update Print Complete Automation

This updates the existing automation to add error logging.

**⚠️ Backup First**: Before modifying, export your current automation as backup.

1. Go to **Settings** → **Automations & Scenes** → **Automations**
2. Find your **"Print Complete - Update Filament Usage"** automation
3. Click **Edit**
4. Click the **⋮** menu (top right) → **"Edit in YAML"**
5. Replace the entire content with `print_complete-update_filament_usage.yaml`
6. **Important**: Update entity IDs to match your setup:
   - Line 16: `sensor.ntk_ryansoffice_3dprinter_print_weight` → your print weight sensor
   - Line 71: `sensor.p1s_01p00c460102350_ams_1_tray_` → your AMS tray sensors
   - Line 123: `sensor.ntk_ryansoffice_3dprinter_task_name` → your task name sensor
7. Save the automation

## Step 4: Update Active Tray Changed Automation

This updates the existing automation for consistent error messaging.

**⚠️ Backup First**: Export your current automation as backup.

1. Go to **Settings** → **Automations & Scenes** → **Automations**
2. Find your **"3D Printer - Active Tray Changed: Update Spoolman Last Used"** automation
3. Click **Edit**
4. Click the **⋮** menu (top right) → **"Edit in YAML"**
5. Replace the entire content with `active_tray_changed_update_spoolman.yaml`
6. **Important**: Update entity IDs to match your setup (same entities as your original automation)
7. Save the automation

## Step 5: Add Manual Recovery Script

This script allows manual application of stored error data.

1. Go to **Settings** → **Automations & Scenes** → **Scripts**
2. Click **"+ ADD SCRIPT"**
3. Click **"Create new script"**
4. Click the **⋮** menu (top right) → **"Edit in YAML"**
5. Copy the entire contents of `manual_spoolman_recovery-script.yaml`
6. Paste into the YAML editor
7. Save the script with name: **"Manual Spoolman Recovery"**

## Step 6: Verify Installation

After installing all components:

1. **Check Helpers**: Go to **Settings** → **Devices & Services** → **Helpers**
   - Verify all 6 new helpers appear in the list
   - Check they are in the correct state (empty/false initially)

2. **Check Automations**: Go to **Settings** → **Automations & Scenes** → **Automations**
   - Verify "Print Started - Capture Print Data" appears
   - Verify "Print Complete - Update Filament Usage" shows updated
   - Verify "3D Printer - Active Tray Changed" shows updated

3. **Check Script**: Go to **Settings** → **Automations & Scenes** → **Scripts**
   - Verify "Manual Spoolman Recovery" appears

4. **Test Print Start Capture**:
   - Start a print job
   - After print starts, check:
     - `input_text.print_job_current` should contain print name and timestamp
     - `input_text.print_job_ams_trays` should contain JSON with tray data
   - You can view these in **Developer Tools** → **States**

## Step 7: Optional Dashboard Card

Add a card to your dashboard to show error status:

```yaml
type: conditional
conditions:
  - entity: input_boolean.spoolman_sync_error_active
    state: "on"
card:
  type: entities
  title: ⚠️ Spoolman Sync Error
  entities:
    - entity: input_datetime.spoolman_sync_last_error_time
      name: Error Time
    - entity: input_text.spoolman_sync_last_error
      name: Error Details
  state_color: true
```

Or a more detailed markdown card:

```yaml
type: conditional
conditions:
  - entity: input_boolean.spoolman_sync_error_active
    state: "on"
card:
  type: markdown
  title: ⚠️ Spoolman Sync Error - Action Required
  content: |
    **Last Error:** {{ states('input_datetime.spoolman_sync_last_error_time') | as_timestamp | timestamp_custom('%b %d, %Y at %I:%M %p') }}

    {% set error = states('input_text.spoolman_sync_last_error').split('|') %}
    {% if error | length >= 7 %}
    **Tray:** {{ error[1] }}
    **Error:** {{ error[2] }}
    **Weight:** {{ error[3] }}g

    **Tray Details:**
    - UUID: `{{ error[4] }}`
    - Color: `{{ error[5] }}`
    - Type: `{{ error[6] }}`

    [View Notifications](/config/notifications) | [Run Recovery Script](/config/script)
    {% endif %}
```

## Troubleshooting Installation

### Helpers don't appear
- Restart Home Assistant after adding via configuration.yaml
- Check logs for syntax errors
- Verify file permissions

### Automations fail to save
- Check entity IDs match your setup
- Verify device_id is correct for your printer
- Check for YAML syntax errors (use YAML validator)

### Print data not captured
- Verify "Print Started - Capture Print Data" automation is enabled
- Check automation is triggered when print starts (check logbook)
- Verify entity IDs for tray sensors are correct

### Script doesn't work
- Verify Spoolman integration is installed
- Check spool ID is valid in Spoolman
- Review Home Assistant logs for specific errors

## Next Steps

After installation:

1. Read the [Persistent Error Logging Documentation](persistent_error_logging.md)
2. Review the [Error Logging Flow Diagram](error_logging_flow.md)
3. Test the system by simulating an error (temporarily rename a spool in Spoolman)
4. Familiarize yourself with the [Manual Recovery Process](persistent_error_logging.md#manual-recovery-process)

## Support

If you encounter issues:

1. Check Home Assistant logs: **Settings** → **System** → **Logs**
2. Review automation traces: Go to automation → Click **⋮** → **Traces**
3. Verify entity IDs match your setup
4. Open an issue in the GitHub repository with details

## Updating Entity IDs

You need to update entity IDs in multiple places. Here's a quick reference:

**In print_started-capture_print_data.yaml:**
- Line 6: `device_id` for your printer
- Line 15: `sensor.[your_printer]_task_name`
- Line 28: `sensor.p1s_[your_serial]_ams_1_tray_`

**In print_complete-update_filament_usage.yaml:**
- Line 4: `device_id` for your printer
- Line 16: `sensor.[your_printer]_print_weight`
- Line 20: `sensor.[your_printer]_print_weight`
- Line 40: `sensor.[your_printer]_print_weight`
- Line 71: `sensor.p1s_[your_serial]_ams_1_tray_`
- Line 123: `sensor.[your_printer]_task_name`

**In active_tray_changed_update_spoolman.yaml:**
- Line 8-9: `sensor.[your_printer]_active_tray`
- Line 12, 18, 23, 30: `sensor.[your_printer]_current_stage`

To find your entity IDs:
1. Go to **Developer Tools** → **States**
2. Search for entities containing your printer name
3. Copy the exact entity ID (e.g., `sensor.p1s_01p00c460102350_ams_1_tray_1`)
