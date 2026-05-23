# Archive Restore HA Service And Popup Contract

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: print_history
Replaces: docs/features/print_history/runtime-repair/archive-runtime-restore-ha-service-and-popup-contract.md
Replaced By: none

> Concrete companion to [archive-runtime-restore-ha-ux-design.md](../runtime-repair/archive-runtime-restore-ha-ux-design.md) and [archive-runtime-restore-implementation-plan.md](../runtime-repair/archive-runtime-restore-implementation-plan.md).

## Purpose

Define the first concrete Home Assistant contract for the sidecar-backed archive restore workflow.

This document is intentionally implementation-shaped:

- exact proposed service names
- exact popup state helpers
- exact upload endpoint shape
- proposed popup wiring points in the current print-history frontend

## Contract Principles

1. browser uploads the replacement file to HA, not directly to Bambuddy
2. HA integration owns transient workflow state for the active pair
3. Bambuddy sidecar remains the merge-policy and verification boundary
4. popup UI reads summary state from HA entities/services, not by reconstructing workflow state in JavaScript alone
5. cleanup remains explicit and gated

## Proposed HA Helpers

Recommended helper entities:

- `input_text.print_history_restore_source_archive_id`
- `input_text.print_history_restore_target_archive_id`
- `input_text.print_history_restore_upload_session_id`

Rules:

- `source_archive_id` is seeded from the main popup archive ID when the operator launches restore
- `target_archive_id` is blank until a replacement archive is created or explicitly selected
- `upload_session_id` is blank until a browser upload successfully stages a replacement file

These helpers carry selection state only. They do not carry plan or verify payloads.

## Proposed HA Entity Surface

## Summary entity

Recommended entity:

- `sensor.print_history_popup_restore_workflow`

Recommended fields:

- state: workflow state string such as `idle`, `plan_ready`, or `finalize_pending_reenrich`
- attributes:
  - `source_archive_id`
  - `target_archive_id`
  - `upload_session_id`
  - `pair_key`
  - `plan_warning_count`
  - `plan_updated_field_count`
  - `verify_remaining_difference_count`
  - `verify_blocking_difference_count`
  - `verified`
  - `removable`
  - `enrichment_status`
  - `last_operation`
  - `last_operation_at`
  - `last_error`
  - `summary_json`

Recommended hydration pattern:

- trigger-based template sensor
- calls `bambuddy.get_print_history_archive_restore_workflow`
- updates whenever any restore helper changes or when the Bambuddy browser revision changes

## Proposed Upload Endpoint

## `POST /api/bambuddy/print-history/archive-repair/replacement/discover`

Purpose:

- accept a browser-uploaded replacement file
- validate it
- create a short-lived upload session

Transport expectation:

- this endpoint exists specifically because the replacement file may be quite large
- the browser should send multipart HTTP directly to HA
- HA should spool the upload to temp storage rather than assuming it fits comfortably in popup-scale in-memory handling

Multipart fields:

- `entry_id`
- `source_archive_id`
- `printer_id`
- `file`

Response shape:

```json
{
  "upload_session_id": "rs_01HV...",
  "source_archive_id": 191,
  "printer_id": 1,
  "filename": "Deadpool___Wolverine_Deadpool.gcode.3mf",
  "size_bytes": 4812293,
  "file_kind": "sliced_3mf",
  "warnings": [],
  "ready_to_create_replacement": true
}
```

Validation rules for the first version:

- require `.3mf` suffix
- cap file size with a configurable limit sized for realistic sliced `.gcode.3mf` uploads rather than photo uploads
- reject malformed ZIPs
- detect obvious source-project versus sliced-file signals only for warning text, not hard rejection

Operational rules for large files:

- do not relay the file through websocket or base64 transport
- do not return any binary payload in the response; only return session metadata
- do not store file bytes in helpers or the restore workflow summary entity
- expire abandoned staged files automatically

## Proposed HA Services

All services are under the `bambuddy` domain.

## 1. `get_print_history_archive_restore_workflow`

Purpose:

- return the summarized workflow state for the current or specified pair

Inputs:

- optional `source_archive_id`
- optional `target_archive_id`

Response:

```json
{
  "workflow_state": "plan_ready",
  "source_archive_id": 191,
  "target_archive_id": 200,
  "upload_session_id": "rs_01HV...",
  "pair_key": "restore:191:200",
  "plan_warning_count": 1,
  "plan_updated_field_count": 7,
  "verify_remaining_difference_count": 0,
  "verify_blocking_difference_count": 0,
  "verified": false,
  "removable": false,
  "enrichment_status": "missing",
  "last_operation": "plan",
  "last_operation_at": "2026-04-16T22:14:00Z",
  "last_error": "",
  "summary": {}
}
```

## 2. `create_print_history_archive_replacement_from_upload`

Purpose:

- create a replacement Bambuddy archive from a staged upload session
- set the target archive ID into workflow state

Large-file handling requirement:

- this service should consume the staged file from HA-controlled temp storage and stream or forward it to Bambuddy's multipart upload path
- it should not require the browser to resend the file after the discovery/upload-session step

Inputs:

- `source_archive_id`
- `upload_session_id`
- `printer_id`
- optional `recovery_source`

Response:

```json
{
  "created": true,
  "source_archive_id": 191,
  "target_archive_id": 232,
  "workflow_state": "replacement_created",
  "upload_session_id": "rs_01HV...",
  "replacement_archive": {}
}
```

## 3. `plan_print_history_archive_restore`

Purpose:

- call sidecar `POST /admin/archive-restore-from` with `dry_run: true`

Inputs:

- `source_archive_id`
- `target_archive_id`
- optional `field_groups`
- optional `exclude_tags`
- optional `include_tags`
- optional `overrides`
- optional `run_reenrich`

Response:

- summarized workflow payload plus raw plan payload stored integration-side

## 4. `apply_print_history_archive_restore`

Purpose:

- call sidecar `POST /admin/archive-restore-from` with `dry_run: false`

Inputs:

- same as plan
- optional `audit_note`

Response:

- summarized workflow payload with `workflow_state = applied_pending_verify`

## 5. `verify_print_history_archive_restore`

Purpose:

- call sidecar `POST /admin/archive-restore-verify` with `remove_original: false`

Inputs:

- `source_archive_id`
- `target_archive_id`
- optional `field_groups`
- optional `exclude_tags`
- optional `include_tags`

Response:

- summarized verification payload

## 6. `finish_print_history_archive_restore`

Purpose:

- provide the HA-side orchestration step that closes the workflow safely

This is not a second merge action.

Inputs:

- `source_archive_id`
- `target_archive_id`
- optional `attempt_reenrich`
- optional `retain_original`

Default behavior:

1. refresh target detail
2. if enrichment is incomplete and `attempt_reenrich = true`, call existing `script.reenrich_print_history_archive`
3. refresh target detail again
4. if enrichment is still incomplete, return `workflow_state = finalize_pending_reenrich`
5. if enrichment is acceptable, run verify
6. if verify is clean and `retain_original = true`, return `workflow_state = completed_original_retained`
7. if verify is clean and `retain_original = false`, leave the workflow in `remove_ready`

Response:

```json
{
  "workflow_state": "finalize_pending_reenrich",
  "source_archive_id": 191,
  "target_archive_id": 232,
  "enrichment_status": "missing",
  "verified": false,
  "removable": false,
  "message": "Target archive enrichment is not complete. Run re-enrich before cleanup or keep the original archive."
}
```

## 7. `remove_print_history_restored_source_archive`

Purpose:

- perform the destructive original-removal step only after verify is clean

Inputs:

- `source_archive_id`
- `target_archive_id`

Behavior:

- reject unless the current workflow state for the pair is `remove_ready`
- call sidecar `POST /admin/archive-restore-verify` with `remove_original: true` and `dry_run: false`
- clear or archive workflow state after success

## 8. `clear_print_history_archive_restore`

Purpose:

- discard transient workflow state for the pair

Inputs:

- optional `source_archive_id`
- optional `target_archive_id`

## Popup Wiring Contract

## Entry point in the current popup

Recommended files:

- `homeassistant/www/3d_printing/print_history/print-history-browser-card.js`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/print_history_archive_popup.yaml`

Add an admin-only popup action button:

- label: `Repair`
- icon: `mdi:wrench-cog`

Do not place upload controls directly on the normal popup action row.

Instead, the action should open a dedicated restore popup.

## Launch sequence

Recommended `browser_mod.sequence` steps:

1. set `input_text.print_history_restore_source_archive_id` to the current popup archive ID
2. clear `input_text.print_history_restore_target_archive_id`
3. clear `input_text.print_history_restore_upload_session_id`
4. call `bambuddy.clear_print_history_archive_restore`
5. open a child popup containing `custom:print-history-archive-restore-card`

## Dedicated restore popup card

Recommended config shape:

```yaml
type: custom:print-history-archive-restore-card
workflow_entity: sensor.print_history_popup_restore_workflow
detail_entity: sensor.print_history_popup_archive_detail
source_archive_helper: input_text.print_history_restore_source_archive_id
target_archive_helper: input_text.print_history_restore_target_archive_id
upload_session_helper: input_text.print_history_restore_upload_session_id
```

## Restore popup sections

### Section 1: Source and target summary

- source archive name and ID
- target archive name and ID when present
- workflow state chip

### Section 2: Replacement upload

- `Upload Replacement 3MF` button
- hidden file input
- staged upload summary and warnings
- `Create Replacement Archive` button

### Section 3: Restore workflow summary

- plan warning count
- updated field count
- verify remaining/blocking counts
- enrichment status
- last operation message

### Section 4: Actions

- `Plan Restore`
- `Apply Restore`
- `Verify`
- `Finish Repair`
- `Remove Original`
- `Clear`

## Action gating rules

### `Create Replacement Archive`

Visible when:

- `upload_session_id` is present
- `target_archive_id` is blank

### `Plan Restore`

Visible when:

- both source and target IDs are present

### `Apply Restore`

Visible when:

- workflow state is `plan_ready`

### `Verify`

Visible when:

- workflow state is `applied_pending_verify`
  or `finalize_pending_reenrich`
  or `verified_blocked`

### `Finish Repair`

Visible when:

- workflow state is `applied_pending_verify`
  or `finalize_pending_reenrich`
  or `verified_clean`

### `Remove Original`

Visible when:

- workflow state is `remove_ready`

## Relationship To Existing Popup Detail Flow

Keep using:

- `input_text.print_history_popup_archive_id`
- `sensor.print_history_popup_archive_detail`

Reason:

- the normal archive popup remains the source-archive detail surface
- the restore popup only needs the current source archive detail plus workflow summary
- target detail can be fetched on demand through workflow actions or a future target detail helper if needed

## Recommended First Build Slice

Build this contract in the following order:

1. upload endpoint
2. create replacement service
3. workflow query service and summary sensor
4. restore popup card with upload and create flow only
5. plan/apply/verify services
6. finish and remove-original services

## Large-File Design Answer

Yes, the intended architecture is to account for large replacement `.gcode.3mf` files, but the key requirement is architectural rather than cosmetic:

- file transport must be multipart HTTP
- staging must be temp-file or disk backed
- workflow state must carry only metadata and session IDs
- forward upload to Bambuddy must reuse the staged file rather than round-tripping the file through the popup again

If an implementation instead tries to hold the full upload in helper state, websocket payloads, or long-lived in-memory structures, it would violate this design.

## Explicit Non-Goals For The First Slice

- manually entering a target archive ID in the UI before upload/create exists
- making the main popup itself host the full restore state machine inline
- persisting restore workflow state across HA restart
- combining source-3MF image import and replacement-file repair into one UI card