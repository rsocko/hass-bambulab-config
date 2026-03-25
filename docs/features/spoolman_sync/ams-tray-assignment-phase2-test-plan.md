# AMS Tray Assignment Phase 2 - Validation Plan

## Scope

Validate Phase 2 behavior for:

- Automatic trigger from Spoolman location changes
- Tray inference for AMS/AMS 2
- External spool assignment path
- AMS non-interference guardrails
- Filament-tag quick actions (`AMS`, `AMS 2`, `Ext. Spool`, `Remove`)

## Pre-Flight

1. Deploy/reload package changes.
2. Confirm entities exist:
   - `automation.spoolman_location_change_assign_tray`
   - `script.assign_spool_to_printer_tray`
   - `sensor.last_tray_assignment_result`
   - `input_text.pending_tray_assignment_spool_id`
3. Confirm Bambu services are available:
   - `bambu_lab.set_filament`
   - `bambu_lab.get_filament_data`
4. Pick at least 3 test spools:
   - Non-Bambu spool with complete data
   - Bambu spool with `extra_spool_uuid`
   - Spool with incomplete color or material (negative test)

## Test Cases

### T1 - AMS auto-assign with exactly one empty tray

1. Ensure target AMS has exactly one `type=Empty` tray.
2. Set spool location entity `select.spoolman_spool_<id>_location` to `AMS`.
3. Verify expected result:
   - `script.assign_spool_to_printer_tray` runs automatically
   - `sensor.last_tray_assignment_result` state becomes `success`
   - Result attributes include inferred `tray_entity_id` and non-empty `tray_info_idx`

### T2 - AMS inference ambiguity (multiple or zero empty trays)

1. Make AMS state either:
   - two or more empty trays, or
   - zero empty trays
2. Set spool location to `AMS`.
3. Verify expected result:
   - `input_text.pending_tray_assignment_spool_id` becomes spool ID
   - `sensor.last_tray_assignment_result` state becomes `needs_tray_selection`
   - Persistent notification `tray_assignment_needs_selection_<id>` is created

### T3 - External spool auto-assign

1. Set location `select.spoolman_spool_<id>_location` to `External Spool Holder`.
2. Verify expected result:
   - Assignment runs without tray inference
   - Target tray is `sensor.ntk_ryansoffice_3dprinter_external_spool`
   - `sensor.last_tray_assignment_result` becomes `success`

### T4 - RFID Bambu spool in AMS is skipped

1. Use a Bambu spool with populated `extra_spool_uuid`.
2. Trigger AMS assignment (location `AMS` with inferable tray).
3. Verify expected result:
   - Assignment result is `skipped`
   - Message indicates RFID-managed AMS spool skip
   - No overwrite of AMS metadata

### T5 - Printer busy defers assignment

1. Put printer into active print state (`print_status=running` or smart status printing).
2. Trigger assignment.
3. Verify expected result:
   - Result state `deferred`
   - Persistent notification `tray_assignment_deferred_<id>`

### T6 - Already-correct AMS tray metadata is skipped

1. Ensure an AMS tray already matches target `type`, `color`, and profile `name`.
2. Run `script.assign_spool_to_printer_tray` for that spool/tray.
3. Verify expected result:
   - Result state `skipped`
   - Message says tray already configured

### T7 - AMS non-interference overwrite guard

1. Ensure AMS tray is non-empty and differs from computed mapping.
2. Run `script.assign_spool_to_printer_tray` with default `force_write=false`.
3. Verify expected result:
   - Result state `overwrite_required`
   - Persistent notification `tray_assignment_overwrite_required_<id>`
4. Re-run with `force_write=true`.
5. Verify expected result:
   - Result state `success`

### T8 - Incomplete spool data blocks assignment

1. Use spool missing usable color or material.
2. Trigger assignment.
3. Verify expected result:
   - Result state `failed` or `needs_tray_selection` depending on missing tray
   - Error message identifies missing field(s)

### T9 - Filament-tag quick action buttons

1. Open filament tag view.
2. Confirm `AMS`, `AMS 2`, and `Ext. Spool` buttons appear when a spool is selected.
3. Tap `Ext. Spool` and verify location updates to "External Spool Holder".
4. Tap `AMS` and verify location updates to "AMS" and tray assignment automation fires.

## Pass Criteria

Phase 2 is validated when T1-T9 all pass with expected statuses/messages and no unexpected YAML/automation errors in Home Assistant logs.

## Suggested Troubleshooting Checks

- Verify spool entity naming pattern: `sensor.spoolman_spool_<id>`
- Verify location entity naming pattern: `select.spoolman_spool_<id>_location`
- Verify tray sensor attributes include `type`, `name`, `color`
- If assignment fails at mapping, inspect `filament_material`, `filament_color_hex` / `filament_multi_color_hexes`, and `filament_extra_profile_name`
