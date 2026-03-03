# Spoolman Sync - Home Assistant Automations

## Description: 
This is a collection of Home Assistant automations & scripts I have configured to automatically keep Spoolman updated based on actual print jobs and filament usage in my Bambu Lab P1S printer. It uses the Bambu Lab Home Assistant integration to react to various printer events and then reads and writes information on Spoolman as needed.

## Scenarios / Use Cases:
### 1. Update filament usage in Spoolman
Upon completing a print, the filament used will be updated in Spoolman. 

[Automation Details](docs/print_complete_update_filament_usage.md) | [Source .YAML](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/print_complete-update_filament_usage.yaml)

### 2. Update first & last used datetime in Spoolman
Any time a spool is active in Bambu Lab integration (while printing), it will update the last used datetime in Spoolman for the associated spool. If the spool has never been used it will also update the first used datetime.

[Automation Details](docs/active_tray_changed_update_spoolman.md) | [Source .YAML](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/active_tray_changed_update_spoolman.yaml)

### 3. Refresh Spoolman integration daily
I noticed when first starting to use the Spoolman integration that it got out of sync and the Home Assistant entities were sometimes inaccurate (specifically the location was wrong and/or orphaned entities existed). 

This script simply forced a reload of the integration on a nightly basis.

[Automation Details](docs/reload_spoolman_integration_nightly.md) | [Source .YAML](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/reload_spoolman_integration_nightly.yaml)

### 4. Persistent error logging and manual recovery
When the spoolman sync automation fails (e.g., spool not found), the system stores all necessary information for manual recovery. This includes print job details, AMS tray configuration, and comprehensive error information.

**📚 Documentation:**
- [Installation Guide](docs/error-logging/installation_guide.md) - Step-by-step setup instructions
- [Quick Reference](docs/error-logging/quick_reference.md) - At-a-glance command reference
- [Full Documentation](docs/error-logging/persistent_error_logging.md) - Complete system details
- [Error Flow Diagram](docs/error-logging/error_logging_flow.md) - Visual flow and scenarios

**📄 Files:**
- [Input Helpers Configuration](../../../homeassistant/packages/3d_printing/spoolman_sync/helpers/print_job_tracking_helpers.yaml)
- [Print Started Automation](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/print_started-capture_print_data.yaml)
- [Manual Recovery Script](../../../homeassistant/packages/3d_printing/spoolman_sync/scripts/manual_spoolman_recovery-script.yaml)
- [Updated Print Complete Automation](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/print_complete-update_filament_usage.yaml)
- [Updated Active Tray Changed Automation](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/active_tray_changed_update_spoolman.yaml)

### 5. Print-weight persistence troubleshooting self-test
Run a manual diagnostic script to validate that restart-safe backup helpers are
healthy and usable by the print completion automation.

**What it checks:**
- `input_text.print_weight_backup` exists, looks like JSON, and is within 255 chars
- `input_text.print_metadata_backup` is present, has `task|time|weight` format, and is within 255 chars
- AMS/External key count in backup payload for quick sanity check

[Source .YAML](../../../homeassistant/packages/3d_printing/spoolman_sync/scripts/print_weight_persistence_self_test-script.yaml)

### 6. Optional automatic self-test at print start/finish
If you want proactive protection, enable an optional automation that runs the
self-test script at both print start and print finish.

**Behavior:**
- Calls the self-test script with phase `start` on print start
- Calls the self-test script with phase `finish` on print completion
- Uses separate persistent notification IDs:
  - `print_weight_persistence_self_test_start`
  - `print_weight_persistence_self_test_finish`

[Source .YAML](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/print_weight_persistence_auto_self_test.yaml)

## Prequisites:
- [Bambu Lab integration](https://github.com/greghesp/ha-bambulab) installed and configured
- [Spoolman](https://github.com/Donkie/Spoolman) installed and accessible from Home Assistant
- Custom Fields added to Spoolman as follows: ([detailed instructions](docs/spoolman_custom_fields.md))
- One location in Spoolman called 'AMS' (since the 'find spool' logic checks for Spools in that location as an indicator that they are the active spool).
- [Spoolman integration](https://github.com/Disane87/spoolman-homeassistant) installed (for updating spoolman)
- [REST integration](https://www.home-assistant.io/integrations/rest/) in Home Assistant installed
- REST endpoint sensor for Spoolman configured (for retrieving all spools from Spoolman API) ([detailed instructions](docs/sensor_rest_spoolman_api_get_spools.md))
- Input helpers configured for error logging ([configuration file](../../../homeassistant/packages/3d_printing/spoolman_sync/helpers/print_job_tracking_helpers.yaml)) - Add this to your Home Assistant configuration

## Helper YAML Files & Configuration

Several features of this automation set require **input helpers** (input_text,
input_boolean, input_datetime, input_number) and **template sensors** to be
registered in Home Assistant. These are defined in three YAML files that ship
with this repository:

| File | Purpose |
|------|---------|
| `print_cost_helpers.yaml` | `input_number` helper for default filament cost per kg |
| `print_weight_persistence.yaml` | `input_text` helpers + `template` sensor for backup/restore of print-weight attributes across HA restarts |
| `print_job_tracking_helpers.yaml` | `input_text`, `input_boolean`, and `input_datetime` helpers for persistent error tracking and manual recovery |

### Recommended Folder Structure

Copy the three helper files into a logical location inside your Home Assistant
`/config` directory. A `packages/bambulab/` sub-folder keeps all Bambu Lab
related helpers together while leaving room for other groups (e.g. air quality,
notifications) to be organised in parallel sub-folders:

```
/config/
├── configuration.yaml
└── packages/
    ├── bambulab/                              ← Bambu Lab / 3D printer group
    │   ├── print_cost_helpers.yaml
    │   ├── print_job_tracking_helpers.yaml
    │   └── print_weight_persistence.yaml
    └── <other_group>/                         ← e.g. air_quality/, homeassistant/packages/3d_printing/notifications/
        └── ...
```

### configuration.yaml Entry

Add the following block to `configuration.yaml`. If you already have a
`homeassistant:` key, add the `packages:` section inside it; if you already
have a `packages:` section, add the three lines to it:

```yaml
homeassistant:
  packages:
    bambulab_print_cost:         !include packages/bambulab/print_cost_helpers.yaml
    bambulab_print_weight:       !include packages/bambulab/print_weight_persistence.yaml
    bambulab_print_job_tracking: !include packages/bambulab/print_job_tracking_helpers.yaml
```

Restart Home Assistant (or use **Developer Tools → YAML → Restart**) after
saving the file.

> **Why packages instead of `input_text: !include ...`?**  Each helper file
> defines more than one top-level section. For example
> `print_weight_persistence.yaml` contains both `input_text:` **and**
> `template:`. Using `input_text: !include ...` would try to nest the file's
> own section headers inside `input_text:`, producing invalid configuration.
> The `homeassistant.packages` mechanism is the correct Home Assistant pattern
> for loading a file that spans multiple integration domains.

> **Have other helpers already in configuration.yaml?**  No changes are
> needed to existing sections. Packages merge their keys into the overall
> configuration automatically — if you already have standalone `input_text:`
> or `input_number:` entries for unrelated helpers, those continue to work
> unchanged alongside the package-loaded entities.

## Notes:
- There are several known bugs that I will be cataloging and tracking in GitHub issues in this Repo.
- I have only tested this on my own setup - which is a Bambu Lab P1S with a single AMS attached. I have not, for example used these automations with an AMS Lite, and AMS 2 nor with multiple AMSs.
- Make sure to review the YAML code examples and update the Entity and Sensor names to match your Home Assistant setup

## Version Information
2025-05-23 - v1.0.0 - Initial public release
