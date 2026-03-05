# Spoolman Sync YAML Migration Runbook

This runbook migrates `spoolman_sync` from UI-created objects to repo/YAML-managed package loading.

## Scope

Repo package paths:
- `homeassistant/packages/3d_printing/spoolman_sync/spoolman_sync_loader.yaml`
- `homeassistant/packages/3d_printing/spoolman_sync/automations/*.yaml`
- `homeassistant/packages/3d_printing/spoolman_sync/scripts/*.yaml`
- `homeassistant/packages/3d_printing/spoolman_sync/helpers/input_number/*.yaml`
- `homeassistant/packages/3d_printing/spoolman_sync/helpers/input_text/*.yaml`
- `homeassistant/packages/3d_printing/spoolman_sync/helpers/input_boolean/*.yaml`
- `homeassistant/packages/3d_printing/spoolman_sync/helpers/input_datetime/*.yaml`
- `homeassistant/packages/3d_printing/spoolman_sync/template_sensors/*.yaml`

Feature enablement wiring:
- `homeassistant/packages/3d_printing/_feature_loaders.yaml`

## Pre-Migration Safety

1. Ensure the repo files are deployed to Home Assistant `/config/packages/3d_printing/...`.
2. Take a Home Assistant backup.
3. Confirm Spoolman integration is healthy and entities are available.
4. Run config validation before restart (`ha_check_config`).

## Remove UI Objects First

These should be removed before relying on YAML loading, otherwise duplicate/conflicting automations/scripts/helpers may occur.

### Automations (remove)

- `automation.update_spool_lastused`
- `automation.print_complete_update_filament_usage`
- `automation.print_started_backup_print_weight_attributes`
- `automation.print_started_capture_print_data`
- `automation.print_weight_persistence_auto_self_test_optional`
- `automation.reload_spoolman_integration_daily_11pm`

MCP tool: `ha_config_remove_automation(identifier=...)`

### Scripts (remove)

- `script.find_matching_spool_in_spoolman`
- `script.manual_spoolman_recovery`
- `script.mark_spool_as_dried_in_spoolman`
- `script.print_weight_persistence_self_test`
- `script.update_spool_last_and_first_used`

MCP tool: `ha_config_remove_script(script_id=...)`

### Helpers (remove if UI-created)

- `input_text.print_weight_backup`
- `input_text.print_metadata_backup`
- `input_text.print_job_current`
- `input_text.print_job_external_spool`
- `input_text.spoolman_sync_last_error`
- `input_boolean.spoolman_sync_error_active`
- `input_datetime.spoolman_sync_last_error_time`
- `input_number.print_cost_default_per_kg`

MCP tool: `ha_config_remove_helper(helper_type=..., helper_id=...)`

Template helpers/sensors that come from helper-template definitions:
- `sensor.print_job_ams_tray_storage`
- `sensor.spoolman_sync_error_log_storage`
- `sensor.print_weight_data_status`

Note: these are usually recreated by YAML/template reload; remove only if duplicates persist.

## Spool Location Sync Automation

`automation.spoolman_location_sync` is now defined in the package at:
- `homeassistant/packages/3d_printing/spoolman_sync/automations/spoolman_location_sync.yaml`

During migration, remove the UI-created version so the YAML-managed copy can be
loaded cleanly.

## Activation Sequence

1. Confirm `_feature_loaders.yaml` includes:
   - `spoolman_sync_loader`
2. Validate config (`ha_check_config`).
3. Restart Home Assistant if required for package re-merge.
4. Verify entities were recreated from YAML.

## Post-Migration Verification Checklist

Automations expected:
- `3D Printer - Active Tray Changed: Update Spoolman Last Used`
- `Print Complete - Update Filament Usage`
- `Print Started - Backup Print Weight Attributes`
- `Print Started - Capture Print Data`
- `Print Weight Persistence - Auto Self-Test (Optional)`
- `Reload Spoolman Integration - Daily @11pm`
- `spoolman location sync`

Scripts expected:
- `script.find_matching_spool_in_spoolman`
- `script.manual_spoolman_recovery`
- `script.mark_spool_as_dried_in_spoolman`
- `script.print_weight_persistence_self_test`
- `script.update_spool_last_and_first_used`

Helpers expected:
- `input_text.print_weight_backup`
- `input_text.print_metadata_backup`
- `input_text.print_job_current`
- `input_text.print_job_external_spool`
- `input_text.spoolman_sync_last_error`
- `input_boolean.spoolman_sync_error_active`
- `input_datetime.spoolman_sync_last_error_time`
- `input_number.print_cost_default_per_kg`
- `sensor.print_job_ams_tray_storage`
- `sensor.spoolman_sync_error_log_storage`
- `sensor.print_weight_data_status`

## Notes

- `reload_spoolman_integration_nightly.yaml` currently uses a specific `entry_id`; verify this is correct in the target HA instance.
- Several automations/scripts include printer-specific entity IDs and `device_id` values; validate these against the target environment.
