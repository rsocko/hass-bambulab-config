# Phase 1.5 — Intake Inbox Implementation Breakdown

> **Status**: Proposed implementation breakdown.
> **Created**: 2026-04-25
> **Scope**: Concrete delivery slices for Phase 1.5 intake, review, and Working-group creation.

## Post-Manyfold Mapping Note

This is a legacy phase-numbered design document.

- Legacy `Phase 1.5` now maps to **Phase 5: Intake, Bulk Discovery, and Working/Curated Unification**.
- References below to Manyfold as the curated authority reflect the pre-pivot baseline, not the current active operational model.
- The intake/review/Working-group boundary definitions remain useful, but the authoritative destination model is now the sidecar-owned post-Manyfold path.

## Purpose

Turn the Phase 1.5 design into an implementation-ready breakdown for:

- sidecar schema and endpoints
- HA-facing service contracts
- the first Intake Inbox review card
- validation gates that keep the slice incremental

This document assumes the current approved baseline remains unchanged:

- Manyfold is still the curated authority
- Working groups remain the normal pre-curated operating model
- the sidecar owns intake review state and dedupe metadata
- Home Assistant remains the first operator surface

## Scope Boundary

Phase 1.5 should deliver **intake and triage**, not the full publish workflow.

In scope:

- submit one file or small batches into an Intake Inbox
- bulk-discover from a folder tree into the same review flow
- validate and dedupe against Inbox and Working groups
- create new Working groups or attach to existing ones
- reject or defer items

Out of scope for this phase:

- broad Manyfold write-back parity
- publish-to-curated workflow depth from Phase 5
- full drag-drop implementation details for every client surface
- rich metadata extraction beyond cheap validation hints
- full Working-board behavior from Phase 4
- curated-model custom fields and provenance editing from Phases 4 and 7

## Later-Phase Boundary Check

Several items in this breakdown intentionally touch the front edge of later phases, but only as a narrow handoff.

### Relationship To Phase 4: Working Groups And Working Veneer

Phase 1.5 may do only this narrow subset:

- create a new Working group from an Inbox item
- attach an Inbox item to an existing Working group
- set only the minimum creation-time fields needed for intake conversion, such as `title`, `stage`, `folder_hint`, and the resulting `working_group_id` backlink

Phase 1.5 does **not** own the broader Phase 4 surface:

- Working-group board and detail UX
- general Working-group CRUD beyond intake conversion
- attach/detach arbitrary supporting assets after intake
- mark primary file as an independent workflow
- broad stage/status editing outside intake conversion
- quick-open actions for folders/files
- repeated reacquisition policy beyond simple duplicate warnings at intake time

### Relationship To Phase 5: Publish Workflow And Revision Lineage

Phase 1.5 stops once an item is staged or converted into the Working layer.

Phase 1.5 does **not** include:

- publish-to-curated actions
- lineage decisions such as supersession or revision choice
- curated duplicate reconciliation against Manyfold records as a publish-time flow
- preview promotion or publish-time asset selection

### Relationship To Phase 6: 3MF Enrichment

Phase 1.5 may surface cheap validation hints only.

Phase 1.5 does **not** include:

- reusable `.3mf` analysis cache ownership
- preview/resource extraction workflows
- enrichment upload actions
- rich parsed metadata review beyond lightweight sampling for operator context

### Relationship To Phase 7: Provenance Capture And Online Ingestion

Phase 1.5 may retain `source_type` and a local source path, but it does **not** own:

- source-platform attribution
- source-download URL capture
- fetched public metadata from Makerworld, Printables, or similar sources
- embedded provenance extraction as a durable catalog feature

## Minimal Working-Group Contract For Phase 1.5

To avoid scope bleed into Phase 4, treat the Working-group interaction here as a bootstrap contract only.

Allowed create-time fields in this phase:

- `title`
- `stage`
- `folder_hint`
- `notes` limited to intake-handoff context
- initial attached file list derived from the Inbox item or discovery proposal

Deferred to Phase 4:

- general metadata editing after creation
- arbitrary file attach/detach management
- supporting-asset organization
- primary-file workflow refinement
- Working-group browse and maintenance surfaces

## Naming Normalization

The roadmap used shorthand endpoint labels. For implementation, prefer the existing sidecar API convention:

- service root uses `GET /healthz`, `GET /config`, `GET /diagnostics`
- domain endpoints live under `/api/...`

Recommended Phase 1.5 endpoint family:

- `/api/intake/...`
- `/api/working-groups/...`

Recommended HA domain for this slice:

- `model_catalog.*`

Reason:

- archive-linkage was initially `bambuddy`-centric because the popup lived there
- Intake Inbox is broader model-catalog behavior and should not be named as archive-only behavior

## Delivery Order

Implement this phase in four narrow slices.

### Slice 1: Intake Persistence And Read Path

Goal:

- accept intake submissions
- persist them
- read them back in a stable review shape

Required sidecar schema additions:

- `intake_inbox_items`
- `intake_validation_results`
- optional `intake_events` if audit/event rows should stay separate from the existing generic event log

Recommended minimum `intake_inbox_items` fields:

- `id` UUID/TEXT primary key
- `source_type`
- `source_path`
- `source_path_normalized`
- `file_name`
- `file_extension`
- `file_size_bytes`
- `file_hash_sha256` nullable during initial receive, filled after validation
- `status`
- `inbox_state`
- `proposed_title`
- `proposed_project_hint`
- `notes`
- `created_at`
- `updated_at`
- `validated_at` nullable
- `grouped_at` nullable
- `working_group_id` nullable

Recommended minimum `intake_validation_results` fields:

- `intake_item_id`
- `validation_state` (`ready`, `duplicate_candidate`, `unsupported_type`, `missing_source`, `needs_manual_grouping`)
- `file_exists`
- `is_supported_type`
- `hash_computed`
- `duplicate_in_inbox_count`
- `duplicate_working_group_count`
- `sample_metadata_json`
- `warnings_json`
- `computed_at`

Required endpoints:

- `POST /api/intake/submit`
- `GET /api/intake/items`
- `GET /api/intake/items/{item_id}`

Recommended request for `POST /api/intake/submit`:

```json
{
  "items": [
    {
      "source_path": "D:/3D Printing/Downloads/gridfinity-box.3mf",
      "source_type": "filesystem_action"
    }
  ],
  "auto_validate": true
}
```

Recommended response shape:

```json
{
  "success": true,
  "created_count": 1,
  "items": [
    {
      "id": "inbox_01",
      "source_path": "D:/3D Printing/Downloads/gridfinity-box.3mf",
      "status": "validated",
      "inbox_state": "inbox",
      "proposed_title": "gridfinity box",
      "validation": {
        "validation_state": "ready",
        "duplicate_working_group_count": 0,
        "warnings": []
      }
    }
  ]
}
```

Validation gate for Slice 1:

- unit tests for schema bootstrap and path normalization
- focused API tests for submit/list/detail
- duplicate-free single-file submit returns stable item state

### Slice 2: Validation And Dedupe Refresh

Goal:

- rerun validation cheaply
- detect duplicate candidates before grouping

Required endpoints:

- `POST /api/intake/items/{item_id}/validate`
- `POST /api/intake/validate-batch`

Behavior:

- check filesystem existence/readability
- restrict to supported file types for this slice (`.3mf`, `.stl`, `.step` if desired; otherwise start with `.3mf` and `.stl`)
- compute or refresh SHA-256
- compare against existing Inbox items
- compare against Working-group file hashes when present
- produce a compact reason list, not only a boolean

Recommended validation detail payload:

```json
{
  "validation_state": "duplicate_candidate",
  "warnings": [
    {
      "code": "working_group_hash_match",
      "message": "Hash matched an existing Working-group file.",
      "related_ids": ["wg_17"]
    }
  ]
}
```

Validation gate for Slice 2:

- duplicate hash detection works for Inbox-to-Inbox and Inbox-to-Working comparisons
- missing-file and unsupported-type states are preserved predictably
- rerun validation updates the item without creating a duplicate row

### Slice 3: Review Actions And Working-Group Conversion

Goal:

- move reviewed Inbox items into the Working layer
- allow reject/defer decisions without deleting history

Required endpoints:

- `POST /api/intake/items/{item_id}/defer`
- `POST /api/intake/items/{item_id}/reject`
- `POST /api/intake/items/{item_id}/group`
- `POST /api/intake/group-batch`

Recommended `group` request shape:

```json
{
  "action": "create_working_group",
  "title": "Gridfinity Storage",
  "stage": "draft",
  "folder_hint": "D:/3D Printing/Downloads",
  "notes": "Imported from Intake Inbox"
}
```

Recommended alternate attach shape:

```json
{
  "action": "attach_existing_working_group",
  "working_group_id": "wg_17",
  "mark_as_primary": false
}
```

Behavior:

- `defer` keeps the item in Inbox with updated notes/state
- `reject` marks the item rejected but preserves auditability
- `group` creates a Working group or attaches to an existing one using only the minimal bootstrap fields above
- grouped items should retain a backlink to the resulting Working group

Validation gate for Slice 3:

- create-new-group path works from one Inbox item
- attach-existing-group path works without duplicating the item row
- reject/defer do not remove the validation history needed for operator review

### Slice 4: Bulk Discover Feeding Intake

Goal:

- reuse the Intake Inbox for folder-tree discovery instead of inventing a separate review queue

Required endpoints:

- `POST /api/intake/discover`
- optional `GET /api/intake/discover/{job_id}` if discovery becomes asynchronous

Recommended request:

```json
{
  "root_path": "D:/3D Printing",
  "grouping_strategy": "by-folder",
  "max_depth": 3,
  "auto_stage_to_inbox": true
}
```

Behavior:

- scan candidate files
- propose logical groupings
- materialize proposed group rows into Intake review state when `auto_stage_to_inbox=true`
- keep discovery metadata so the card can explain why the grouping was proposed

Validation gate for Slice 4:

- by-folder discovery produces stable proposals
- grouped proposals can be accepted into Working groups without re-entering filenames manually
- a 500-file fixture run is bounded and reviewable

## HA Service Contract

HA should treat the sidecar as the write authority for this phase and expose thin operator services.

Recommended initial HA services:

- `model_catalog.submit_to_inbox`
- `model_catalog.get_intake_items`
- `model_catalog.get_intake_item`
- `model_catalog.validate_intake_item`
- `model_catalog.defer_intake_item`
- `model_catalog.reject_intake_item`
- `model_catalog.group_intake_item`
- `model_catalog.discover_intake_groups`

Explicitly deferred to later phases:

- generic `model_catalog.create_working_group`
- generic `model_catalog.update_working_group`
- generic `model_catalog.attach_working_group_file`
- `model_catalog.publish_working_group`
- curated provenance-editing services

Recommended common service conventions:

- optional `entry_id` when the integration supports multiple sidecar instances later
- thin pass-through to sidecar with HA-friendly error envelopes
- do not copy Intake state into HA helpers except for UI convenience that cannot be rendered directly from service-backed entities

Recommended service examples:

`model_catalog.submit_to_inbox`

```yaml
source_paths:
  - D:/3D Printing/Downloads/gridfinity-box.3mf
source_type: filesystem_action
auto_validate: true
```

`model_catalog.group_intake_item`

```yaml
item_id: inbox_01
action: create_working_group
title: Gridfinity Storage
stage: draft
folder_hint: D:/3D Printing/Downloads
```

Recommended HA response envelope:

```json
{
  "success": true,
  "item_id": "inbox_01",
  "working_group_id": "wg_17",
  "message": "Inbox item grouped successfully."
}
```

## Intake Review Card

The first card should stay narrow and operational.

### Card Goals

- show what just arrived
- make validation warnings obvious
- allow the shortest path to Working-group creation

### Required Top-Level Sections

1. Summary bar
   - Inbox count
   - ready count
   - duplicate-warning count
   - rejected/deferred count optional or tucked into overflow

2. Inbox list
   - file/title
   - source type
   - validation status chip
   - duplicate warning indicator
   - proposed project hint when present

3. Detail panel or popup
   - normalized path
   - validation reason list
   - notes field
   - actions

### Required Actions Per Item

- `Validate`
- `Create Working Group`
- `Attach To Existing`
- `Keep In Inbox`
- `Reject`

### Suggested View Model Per Item

```json
{
  "id": "inbox_01",
  "title": "gridfinity box",
  "path_label": "D:/3D Printing/Downloads/gridfinity-box.3mf",
  "status_chip": "ready",
  "warning_count": 0,
  "duplicate_hint": null,
  "project_hint": null,
  "actions": [
    "validate",
    "create_working_group",
    "attach_existing",
    "defer",
    "reject"
  ]
}
```

### Deliberate Non-Goals For V1 Card

- full drag/drop browser implementation details
- editable bulk metadata matrix
- deep Manyfold publish actions
- rich preview/media extraction
- full Working-group board/detail parity
- post-intake Working-group maintenance flows

## Error Handling Direction

Recommended error codes for this phase:

- `invalid_payload`
- `item_not_found`
- `source_missing`
- `unsupported_type`
- `duplicate_candidate`
- `working_group_not_found`
- `validation_failed`
- `storage_unavailable`

The card should distinguish between:

- blocking errors that prevent grouping
- review warnings that still allow operator override

## Recommended Test Strategy

Focused automated checks first:

1. schema/bootstrap tests for intake tables
2. API tests for submit/list/detail/validate/group/reject/defer
3. dedupe tests using same-hash and same-path fixtures
4. grouping tests for create-new and attach-existing flows
5. bulk-discovery fixture test with bounded sample tree

Manual or environment checks later:

1. HA service invocation against a live sidecar
2. first review card rendering with mixed states
3. filesystem-path handling on the actual host layout you plan to use

## Recommended Exit Criteria

Phase 1.5 is implementation-ready when all of the following are true:

- one-file submit to Inbox works end to end
- validation and dedupe warnings render in a stable operator shape
- an Inbox item can create a new Working group
- an Inbox item can attach to an existing Working group
- bulk discovery can feed the same review flow without inventing a second queue model
- the implementation does not require Phase 4 Working-board CRUD or Phase 5 publish workflows to be present

## Related Docs

- [Intake Inbox Design](intake-inbox-design.md)
- [ROADMAP-REVISED-WITH-BULK](ROADMAP-REVISED-WITH-BULK.md)
- [Workflow And Ingestion Guide](workflow-and-ingestion-guide.md)
- [Phase Delivery And Validation Tracker](phase-delivery-and-validation.md)
- [integration/HA Model Library Integration](integration/ha-model-library-integration.md)