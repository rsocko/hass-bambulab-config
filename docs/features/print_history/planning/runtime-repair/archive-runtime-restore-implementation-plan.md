# Archive Restore Implementation Plan

> Companion to [archive-runtime-restore-ha-ux-design.md](../../design/runtime-repair/archive-runtime-restore-ha-ux-design.md) and [archive-runtime-sidecar-api-and-compose.md](../../reference/runtime-repair/archive-runtime-sidecar-api-and-compose.md).

## Purpose

Turn the restore UX design into a concrete implementation sequence for the active Variant 3 print-history stack.

This plan assumes:

- the active backend is `homeassistant/custom_components/bambuddy/`
- popup launch continues to start in `print-history-browser-card.js`
- heavyweight restore state stays integration-owned rather than being serialized into helper entities
- browser file upload for a replacement `.gcode.3mf` enters Home Assistant first, not Bambuddy directly

## Implementation Goal

Support this operator flow from the existing archive popup:

1. open archive popup for the source archive
2. launch advanced restore
3. upload a replacement sliced `.gcode.3mf` from the browser to Home Assistant
4. create a replacement Bambuddy archive from that staged upload
5. run restore dry-run, apply, verify, and finish steps
6. keep cleanup gated until enrichment and verification are acceptable

## Existing Surfaces To Reuse

### Backend

- `homeassistant/custom_components/bambuddy/__init__.py`
- `homeassistant/custom_components/bambuddy/api.py`
- `homeassistant/custom_components/bambuddy/manager.py`
- `homeassistant/custom_components/bambuddy/services.yaml`
- `homeassistant/custom_components/bambuddy/const.py`

### Popup and frontend

- `homeassistant/www/3d_printing/print_history/print-history-browser-card.js`
- `homeassistant/www/3d_printing/print_history/print-history-photo-gallery-card.js`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/print_history_archive_popup.yaml`
- `homeassistant/packages/3d_printing/print_history/template_sensors/print_history_popup_archive_detail.yaml`
- `homeassistant/packages/3d_printing/print_history/helpers/`

### Existing patterns worth following

- popup-scoped `input_text.print_history_popup_archive_id`
- integration-owned local SQLite state for review and lineage metadata
- service-return-driven popup detail hydration
- `browser_mod.sequence` to set popup helper state before rendering UI

## Recommended Architecture

## 1. Separate the restore workflow into three layers

### Layer A: Browser upload session

Owns:

- accepting the replacement file from the browser
- validating filename and size
- staging the upload temporarily under HA control

Important for large `.gcode.3mf` files:

- the upload path must assume files may be materially larger than normal popup photo uploads
- the upload path should stream or spool to disk rather than buffering the entire file in memory
- the staged file should be passed forward by path/handle under HA control, not re-encoded into helper state or websocket payloads

Does not own:

- sidecar restore logic
- Bambuddy merge policy
- cleanup decisions

### Layer B: Integration-owned restore workflow state

Owns:

- source archive ID
- target archive ID
- upload session ID
- plan/apply/verify summaries
- current workflow state for the selected pair

Does not own:

- canonical merge policy
- direct DB writes in Bambuddy

### Layer C: Sidecar-backed restore actions

Owns:

- restore merge planning
- restore apply
- verification
- guarded removal checks

Does not own:

- browser upload intake
- popup rendering

## 2. Keep large restore payloads out of helpers

Allowed in helpers:

- source archive ID
- target archive ID
- upload session ID

Not allowed in helpers:

- raw `field_actions`
- full verify payloads
- binary upload metadata beyond a short session token

## 3. Prefer a dedicated restore popup/card over bloating the main archive popup

Recommended UI split:

- main archive popup keeps summary, media, edit, and lightweight actions
- `Repair` opens a dedicated restore popup or child popup
- the restore popup owns upload, plan/apply/verify/finalize controls

Why:

- keeps the normal popup readable
- isolates a high-risk admin workflow
- makes file upload UI easier to reason about

## Proposed New Runtime Pieces

## Backend

### New module: restore workflow manager

Recommended file:

- `homeassistant/custom_components/bambuddy/restore_workflow.py`

Responsibilities:

- hold transient workflow state keyed by `restore:{source_id}:{target_id}`
- track upload-session linkage to the active source archive
- summarize sidecar responses for UI consumption
- expose clear/get/update helpers used by service handlers

Storage recommendation:

- in-memory first
- optional later persistence only if resume-after-restart becomes necessary

### New module: replacement upload session manager

Recommended file:

- `homeassistant/custom_components/bambuddy/restore_uploads.py`

Responsibilities:

- create short-lived upload sessions
- validate extension and size
- hold staged files until replacement archive creation succeeds or the session expires
- clean up expired sessions

Large-file requirements:

- use disk-backed staging in a temp directory, not in-memory byte storage
- keep only compact metadata in workflow state: session ID, filename, size, and validation summary
- make max upload size configurable rather than hardcoding a tiny photo-scale limit
- fail early with a clear operator error if the upload exceeds the configured limit

### API extension

Likely file to touch:

- `homeassistant/custom_components/bambuddy/api.py`

Needed client support:

- multipart upload to Bambuddy `POST /api/v1/archives/upload`
- existing runtime-repair sidecar calls remain separate

Large-file expectation:

- HA should forward the staged file to Bambuddy as multipart from disk/path-backed content where practical
- do not base64-wrap the replacement file or embed it into JSON service payloads at any point

## Frontend

### New restore card

Recommended file:

- `homeassistant/www/3d_printing/print_history/print-history-archive-restore-card.js`

Responsibilities:

- render workflow summary for the active source-target pair
- expose upload button and hidden file input
- call HA upload endpoint for replacement-file staging
- call HA services for create/plan/apply/verify/finish/clear
- render warnings, counts, and next legal actions

Why a separate card instead of overloading the gallery card:

- upload semantics are different from photo upload
- restore state is pair-based, not photo-based
- action gating is materially more complex than media review

## Helpers and sensors

### New helpers

Recommended helpers:

- `input_text.print_history_restore_source_archive_id`
- `input_text.print_history_restore_target_archive_id`
- `input_text.print_history_restore_upload_session_id`

These are scalar selection helpers only.

### New popup summary sensor

Recommended file:

- `homeassistant/packages/3d_printing/print_history/template_sensors/print_history_popup_restore_workflow.yaml`

Recommended source:

- trigger-based template sensor that calls `bambuddy.get_print_history_archive_restore_workflow`

Why use a popup summary sensor:

- matches the existing `sensor.print_history_popup_archive_detail` pattern
- lets the restore card and popup templates read a stable entity
- avoids stuffing raw workflow JSON into frontend local state alone

## Phase Breakdown

## Phase 1: Backend Upload And Workflow Skeleton

### Outcome

Home Assistant can accept a staged replacement upload and maintain transient restore workflow state, but no popup wiring ships yet.

### Backend work

- add upload-session manager
- add restore-workflow manager
- add upload HTTP endpoint
- add workflow query service
- add create replacement service shell without popup wiring

### Acceptance criteria

- HA can stage a replacement `.gcode.3mf`
- HA can create a replacement archive from a staged session
- workflow state is queryable by source/target pair
- staging and forward-upload work without requiring the full file to live in helper state or a long-lived in-memory cache

## Phase 2: Restore Popup Entry And Pair Seeding

### Outcome

Operator can open advanced restore from an archive popup and see source/pair state for the selected archive.

### Frontend work

- add `Repair` button to popup action row
- add restore popup/card resource
- seed `input_text.print_history_restore_source_archive_id` from `input_text.print_history_popup_archive_id`
- clear target/upload helper state when starting a new repair flow

### Acceptance criteria

- restore popup opens from the archive popup
- the current popup archive becomes the default source archive
- prior stale restore state does not leak into a new session

## Phase 3: Browser Upload And Replacement Archive Creation

### Outcome

Operator can upload a replacement file from the restore popup and create the replacement Bambuddy archive.

### Backend work

- implement `create_print_history_archive_replacement_from_upload`
- refresh local Bambuddy store after replacement archive creation
- write initial repair-lineage row after target creation if appropriate

### Frontend work

- file chooser in restore card
- show staged upload summary and errors
- show returned target archive ID after creation

### Acceptance criteria

- replacement archive is created through HA from a browser upload
- target archive ID is captured automatically
- restore pair is ready without manual archive-ID entry

## Phase 4: Dry-Run, Apply, And Verify

### Outcome

Operator can plan, apply, and verify the restore workflow from HA.

### Backend work

- implement plan/apply/verify service handlers
- summarize sidecar `field_actions` into counts and high-signal rows
- store latest plan/apply/verify timestamps and summaries in the workflow manager

### Frontend work

- render plan summary
- render verify summary
- gate `Apply` behind an existing dry-run result for the same pair

### Acceptance criteria

- plan/apply/verify all run from the restore popup
- popup summary state updates after each action
- operator can see whether cleanup is blocked

## Phase 5: Finish-Repair And Cleanup Gate

### Outcome

Operator can finish repair safely even when automatic re-enrich is unavailable.

### Backend work

- implement `finish_print_history_archive_restore`
- integrate with existing `script.reenrich_print_history_archive` by service call when requested
- read current target enrichment status from refreshed archive detail
- keep `remove original` as a separate explicit destructive call

### Policy

Default `finish` behavior:

1. refresh target detail
2. if enrichment is incomplete and re-enrich was not successfully triggered, stop in `finalize_pending_reenrich`
3. if enrichment is acceptable, run verify
4. if verify is clean, either:
   - mark workflow complete with original retained, or
   - allow explicit remove-original action

### Acceptance criteria

- no implicit deletion after apply
- missing sidecar HA callback configuration does not strand the operator
- safe default outcome is completion with original retained

## Phase 6: Optional Remove-Original And Workflow Cleanup

### Outcome

Operator can explicitly remove the original source archive after clean verify.

### Backend work

- implement `remove_print_history_restored_source_archive`
- remove transient recovery tags from the surviving target where appropriate
- archive or clear transient workflow state after success

### Acceptance criteria

- remove-original is unavailable until verify is clean
- successful removal refreshes the browser cache and popup detail
- workflow state is cleared or archived after completion

## Exact Files Likely To Change

## Custom integration

- `homeassistant/custom_components/bambuddy/__init__.py`
- `homeassistant/custom_components/bambuddy/api.py`
- `homeassistant/custom_components/bambuddy/const.py`
- `homeassistant/custom_components/bambuddy/services.yaml`
- `homeassistant/custom_components/bambuddy/manager.py`
- `homeassistant/custom_components/bambuddy/restore_workflow.py` (new)
- `homeassistant/custom_components/bambuddy/restore_uploads.py` (new)

## Package YAML

- `homeassistant/packages/3d_printing/print_history/helpers/input_text/` (new helpers)
- `homeassistant/packages/3d_printing/print_history/template_sensors/print_history_popup_restore_workflow.yaml` (new)

## Frontend

- `homeassistant/www/3d_printing/print_history/print-history-browser-card.js`
- `homeassistant/www/3d_printing/print_history/print-history-archive-restore-card.js` (new)
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/print_history_archive_popup.yaml`
- `homeassistant/packages/3d_printing/common/dashboards/_resources.yaml`

## Suggested Delivery Order

1. backend upload session and workflow manager
2. service/query contract
3. popup summary sensor and helpers
4. restore popup/card resource
5. replacement upload and create flow
6. plan/apply/verify UI
7. finish-repair gate
8. explicit remove-original path

## Explicit Deferrals

- restart-persistent restore workflow state
- automatic candidate-pair discovery beyond source-prefill from the current popup archive
- embedding full sidecar diff tables directly in helper-backed YAML cards
- automatic removal of the original archive after apply
- blending the restore state machine into the photo gallery card

## Large-File Guardrails

The first implementation should explicitly assume that replacement `.gcode.3mf` files may be large enough to stress normal Lovelace popup upload patterns.

Required guardrails:

1. use HTTP multipart upload to HA, not websocket/base64 transport
2. spool incoming uploads to disk or temp-file storage as early as possible
3. keep only session metadata in workflow state and helpers
4. expose a configurable maximum upload size with a clear operator-facing error message
5. clean up staged files promptly after replacement archive creation succeeds or the session expires

Recommended later enhancement:

- add progress reporting for upload and Bambuddy forward-transfer so operators can tell the difference between `uploading to HA` and `creating replacement archive in Bambuddy`