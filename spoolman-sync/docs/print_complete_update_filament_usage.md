# Print Complete - Update Filament Usage in Spoolman - Home Assistant Automation

## Description
This Home Assistant automation triggers upon a successful completion of a print job on your Bambu Lab printer (as reported by the Bambu Lab integration). It updates Spoolman with the filament usage for each tray that contributed to the print.

## Key Features
- **Backup/restore support**: If Home Assistant restarts during a print, the automation falls back to a backed-up snapshot of print weight attributes (captured at print start) so Spoolman is still updated correctly. See [Print Weight Persistence](print_weight_persistence.md) for details.
- **External Spool support**: Handles filament usage for both AMS trays and the External Spool.
- **Zero-weight skip**: Trays that contributed 0 grams are silently skipped.
- **No-data warning**: If neither the live sensor nor the backup has per-tray data, a persistent notification is created and Spoolman is not modified, so the user can manually recover.
- **Persistent error logging**: When a spool cannot be found in Spoolman, the error is recorded in `input_text.spoolman_sync_error_log` (rolling 10-entry log), `input_text.spoolman_sync_last_error`, `input_datetime.spoolman_sync_last_error_time`, and `input_boolean.spoolman_sync_error_active`, enabling manual recovery via the [Manual Spoolman Recovery script](../manual_spoolman_recovery-script.yaml).

## Logic
1. Check whether the live `print_weight` sensor has AMS/External Spool attributes.
2. If not, fall back to the backup stored in `input_text.print_weight_backup`.
3. If neither source has per-tray data, notify the user and stop.
4. For each tray with non-zero usage, call the **Find Matching Spool** script to locate the correct spool in Spoolman and update its filament usage via `spoolman.use_spool_filament`.
5. On success: log to system log, logbook, and create a persistent notification.
6. On failure (spool not found): write to the persistent error log helpers and create an actionable notification with tray details for manual recovery.
7. Clear the print weight backup after processing.

## Source Code
[Print Complete - Update Filament Usage - YAML](../print_complete-update_filament_usage.yaml)

## Prerequisites
- [Find Matching Spool Home Assistant script](find_matching_spools.md) setup and working
- [Print Started - Backup Print Weight automation](../print_started-backup_print_weight.yaml) enabled (for backup/restore support)
- Input helpers from [print_weight_persistence.yaml](../print_weight_persistence.yaml) and [print_job_tracking_helpers.yaml](../print_job_tracking_helpers.yaml) registered in Home Assistant
- All other prerequisites as specified in [README](../README.md)

## Notes
- I have only tested this on my own setup — a Bambu Lab P1S with a single AMS attached. I have not tested with an AMS Lite, AMS 2, or multiple AMSs.

## Flow of the Logic

![Flow Chart describing the Print Complete automation](../Bambu%20Printer%20Automations-Print%20Complete.png)