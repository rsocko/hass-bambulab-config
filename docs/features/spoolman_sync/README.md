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
- [Input Helpers Configuration](../../../homeassistant/packages/3d_printing/spoolman_sync/spoolman_sync_loader.yaml)
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
- Calls the self-test script with phase `start` when print status reaches `running` (5s stable)
- Calls the self-test script with phase `finish` on print completion
- Uses separate persistent notification IDs:
  - `print_weight_persistence_self_test_start`
  - `print_weight_persistence_self_test_finish`

The backup/capture automations also use this same timing model so per-tray MQTT
attributes have time to populate before persistence data is stored.

[Source .YAML](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/print_weight_persistence_auto_self_test.yaml)

## Dependencies & Requirements

> **Foundation:** This feature requires the [Core](../core/README.md) package and the [ha-bambulab](https://github.com/greghesp/ha-bambulab) integration — see [Foundation Packages](../../README.md#foundation-packages). This feature does **not** depend on [Common](../common/README.md) — it has no dashboard cards of its own (UI is provided via Core template sensors and other features that consume its data).

### External Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [ha-bambulab](https://github.com/greghesp/ha-bambulab) | **Yes** | Printer sensors, device triggers, AMS tray data |
| [Spoolman](https://github.com/Donkie/Spoolman) | **Yes** | Spool and filament database — must be installed and accessible from HA |
| [Spoolman HA integration](https://github.com/Disane87/spoolman-homeassistant) | **Yes** | Home Assistant integration for updating Spoolman |
| [REST integration](https://www.home-assistant.io/integrations/rest/) | **Yes** | REST endpoint sensor for Spoolman API spool retrieval |

### Spoolman Configuration Required

- Custom Fields added to Spoolman — see [detailed instructions](docs/spoolman_custom_fields.md)
- One location in Spoolman called `AMS` (the "find spool" logic checks for spools in that location as an indicator they are active)
- REST endpoint sensor configured for Spoolman API — see [detailed instructions](docs/sensor_rest_spoolman_api_get_spools.md)

### Prequisites:
- [Bambu Lab integration](https://github.com/greghesp/ha-bambulab) installed and configured
- [Spoolman](https://github.com/Donkie/Spoolman) installed and accessible from Home Assistant
- Custom Fields added to Spoolman as follows: ([detailed instructions](docs/spoolman_custom_fields.md))
- One location in Spoolman called 'AMS' (since the 'find spool' logic checks for Spools in that location as an indicator that they are the active spool).
- [Spoolman integration](https://github.com/Disane87/spoolman-homeassistant) installed (for updating spoolman)
- [REST integration](https://www.home-assistant.io/integrations/rest/) in Home Assistant installed
- REST endpoint sensor for Spoolman configured (for retrieving all spools from Spoolman API) ([detailed instructions](docs/sensor_rest_spoolman_api_get_spools.md))
- Input helpers configured for error logging ([configuration file](../../../homeassistant/packages/3d_printing/spoolman_sync/spoolman_sync_loader.yaml)) - Add this to your Home Assistant configuration

## Helper YAML Files & Configuration

Several features of this automation set require **input helpers** (input_text,
input_boolean, input_datetime, input_number) and **template sensors** to be
registered in Home Assistant. These are now loaded through one package loader
file in this repository:

| File | Purpose |
|------|---------|
| `spoolman_sync_loader.yaml` | Loads all spoolman sync domains (`automation`, `script`, `input_*`, and `template`) via directory-merge includes |

### Recommended Folder Structure

Copy the `spoolman_sync` package folder into your Home Assistant `/config`
packages path so the loader and all referenced files are present.

```
/config/
├── configuration.yaml
└── packages/
    └── 3d_printing/
        ├── _feature_loaders.yaml
        └── spoolman_sync/
            ├── spoolman_sync_loader.yaml
            ├── automations/
            ├── scripts/
            ├── helpers/
            └── template_sensors/
```

### configuration.yaml Entry

Add the following block to `configuration.yaml` (or confirm it already exists):

```yaml
homeassistant:
  packages: !include packages/3d_printing/_feature_loaders.yaml
```

Restart Home Assistant (or use **Developer Tools → YAML → Restart**) after
saving the file.

> **Why packages?** `spoolman_sync_loader.yaml` spans multiple integration
> domains and delegates to domain-specific files. Using
> `homeassistant.packages` is the correct merge mechanism for this structure.

> **Have other helpers already in configuration.yaml?**  No changes are
> needed to existing sections. Packages merge their keys into the overall
> configuration automatically — if you already have standalone `input_text:`
> or `input_number:` entries for unrelated helpers, those continue to work
> unchanged alongside the package-loaded entities.

### Critical Input Helper Setting for Restart Persistence

For restart-safe print-weight persistence, do **not** set `initial` on backup
helpers that should survive a Home Assistant restart:

- `input_text.print_weight_backup`
- `input_text.print_metadata_backup`

If `initial` is set (for example `initial: ""`), Home Assistant initializes the
helper to that value at startup, which prevents restoring the previously stored
state from recorder. This can make backups appear to be "cleared" immediately
after restart even when capture worked during print.

### Temporary Startup Diagnostic Automation

To confirm restart behavior while troubleshooting, an intentionally temporary
automation is included:

- `automations/temporary_startup_diagnostic_print_weight_persistence.yaml`

It logs startup values for both backup helpers to logbook/system log and creates
a persistent notification. Remove or disable it after validation so it does not
create long-term notification noise.

## Notes:
- There are several known bugs that I will be cataloging and tracking in GitHub issues in this Repo.
- I have only tested this on my own setup - which is a Bambu Lab P1S with a single AMS attached. I have not, for example used these automations with an AMS Lite, and AMS 2 nor with multiple AMSs.
- Make sure to review the YAML code examples and update the Entity and Sensor names to match your Home Assistant setup

## Cross-Package Dependencies

`spoolman_sync` owns the restart-safe backup helpers used by other packages.

### Produced in `spoolman_sync`

1. `input_text.print_weight_backup`
2. `input_text.print_metadata_backup`

### Consumed outside `spoolman_sync`

1. `core/template_sensors/print_weight_effective.yaml`
2. `core/template_sensors/print_cost.yaml`
3. `openhasp_display/openhasp/officetouch5.yaml` (via core sensors)
4. `common` dashboard card templates and `print_weight_and_cost` cards (via core sensors or fallback logic)

This separation is intentional: persistence belongs in `spoolman_sync`, while
shared read models for UI belong in `core`.

## Version Information
2025-05-23 - v1.0.0 - Initial public release
