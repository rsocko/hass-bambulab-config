# Intake Source Routing Contract

> Status: Draft API and schema contract for generalized mixed-source intake
> Last updated: 2026-05-29
> Scope: Queue-backed routing for externally sourced intake items that may resolve to Model, Working Files, Idea, Project, Collection, or Link Only outcomes.

## Purpose

Define the API-facing and storage-facing contract that turns generalized source capture into one shared intake model.

This document exists to support the design direction in:

- `design/external-source-intake.md`
- `design/intake-inbox.md`
- `planning/issue-1496-various-sources-plan.md`

It is intentionally narrower than those design docs. This file answers:

- which normalized routing fields belong on intake records
- which values are allowed for source profiles, trigger classes, and target types
- which API payloads need to exist to capture, route, and commit these items
- which validation and state rules should govern mixed-source review

## Design Position

Generalized source intake should reuse the existing queue and Job History model rather than introducing a source-specific workflow per adapter.

The routing contract therefore separates five concerns that must not be collapsed into one field:

1. capture channel
2. source profile
3. trigger class
4. target selection
5. queue / terminal state

## Normalized Enums

### `capture_channel`

How the sidecar received the item.

Allowed values:

- `url_paste`
- `browser_extension`
- `streamdeck`
- `karakeep_sync`
- `mstodo_sync`
- `webhook`
- `manual_form`
- `batch_materialization`

### `source_profile`

What kind of source the item represents.

Allowed values:

- `provider_model_page`
- `task_item`
- `social_saved_link`
- `collection_container`
- `manual_generic_url`
- `uploaded_file_batch`
- `server_folder_batch`

Notes:

- `uploaded_file_batch` and `server_folder_batch` are included so the queue contract can stay uniform even when the source was not external.
- #1496 work mainly adds the first five values.

### `trigger_class`

Who or what initiated the intake event.

Allowed values:

- `user_direct`
- `user_quick_action`
- `service_push`
- `background_sync`
- `batch_materialization`

### `selected_target_type`

The destination entity class chosen during review or fast-path commit.

Allowed values:

- `model`
- `working_file_group`
- `idea`
- `project`
- `collection`
- `link_only`

### `review_reason_code`

Why the item must remain in review before commit.

Allowed values:

- `review_external_source_default`
- `review_background_sync`
- `review_service_push`
- `review_low_confidence`
- `review_medium_confidence`
- `review_social_source`
- `review_task_source`
- `review_collection_source`
- `review_target_not_confirmed`
- `review_duplicate_warning`
- `review_missing_file_evidence`
- `review_auth_incomplete`
- `review_batch_expansion_required`

## Storage Contract

## Table: `source_intake_records`

Existing fields remain in place. The following additions are required for generalized routing.

| Field | Type | Required | Purpose |
|---|---|---|---|
| `source_profile` | string | yes | normalized source kind |
| `trigger_class` | string | yes | initiation category |
| `review_required` | boolean | yes | whether queue review is required before commit |
| `review_reason_codes` | json array | yes | explicit reasons why review is required |
| `suggested_targets_json` | json | yes | ordered list of suggested target types plus confidence/reasoning |
| `selected_target_type` | string nullable | no | final or in-progress target selection |
| `selected_target_id` | string nullable | no | selected existing entity when applicable |
| `capture_batch_id` | uuid nullable | no | parent batch or sync run identifier |
| `origin_service` | string nullable | no | upstream orchestrator or sync source, e.g. `n8n`, `karakeep`, `mstodo` |
| `origin_external_id` | string nullable | no | stable upstream record identifier |
| `target_context_json` | json nullable | no | target-specific options such as project seed mode, collection expansion mode, or working path preference |
| `review_completed_at` | timestamp nullable | no | timestamp when review reached an explicit decision |
| `review_completed_by` | string nullable | no | user/service identity that completed review |

### `suggested_targets_json` shape

```json
[
  {
    "target_type": "idea",
    "score": 0.91,
    "reason_codes": ["social_source", "low_printable_confidence"],
    "default": true
  },
  {
    "target_type": "project",
    "score": 0.58,
    "reason_codes": ["task_or_brief_like"],
    "default": false
  },
  {
    "target_type": "link_only",
    "score": 0.41,
    "reason_codes": ["fallback_safe_option"],
    "default": false
  }
]
```

### `target_context_json` examples

```json
{
  "project_mode": "attach_existing",
  "project_id": "proj_123",
  "idea_visibility": "active",
  "working_path_policy": null,
  "collection_materialization_mode": null
}
```

```json
{
  "project_mode": "create_seed",
  "project_title": "Bathroom organizer refresh",
  "idea_visibility": null,
  "working_path_policy": null,
  "collection_materialization_mode": null
}
```

## State Model Addendum

The queue states in `intake-state-machine.md` remain authoritative.

This routing contract adds interpretation rules, not a second state machine:

- `submitted` means the item exists with captured source context but may not yet have a confirmed target
- `validated_ready` means validation passed and the currently selected target is actionable
- `validated_warning` means validation passed with warnings or review remains required
- terminal states should record the final `selected_target_type` and resulting entity identifier where applicable

Additional expectations:

- an item may remain `submitted` even when metadata capture succeeded if no target has been selected yet
- `selected_target_type` changes do not create a new queue item; they mutate review context for the same item
- `review_required = true` does not force a separate queue state; it governs allowed actions and visible reasons

## API Contract

## `POST /api/intake/source/capture`

Creates or refreshes a queued intake record from a direct or service-triggered source.

### Request body

```json
{
  "source_url": "https://makerworld.com/en/models/1295917-big-brick-man",
  "capture_channel": "url_paste",
  "trigger_class": "user_direct",
  "origin_service": null,
  "origin_external_id": null,
  "target_hint": "model",
  "project_hint": null,
  "capture_mode": "metadata_only"
}
```

### Response body

```json
{
  "item_id": "intake_01jwn3q8z2g2s9w0yya3j7m4rf",
  "queue_state": "submitted",
  "source_profile": "provider_model_page",
  "review_required": true,
  "review_reason_codes": [
    "review_external_source_default",
    "review_target_not_confirmed"
  ],
  "suggested_targets": [
    {"target_type": "model", "default": true},
    {"target_type": "working_file_group", "default": false},
    {"target_type": "link_only", "default": false}
  ]
}
```

## `POST /api/intake/source/{id}/route`

Changes target selection and review context without committing the item.

### Request body

```json
{
  "selected_target_type": "project",
  "selected_target_id": null,
  "target_context": {
    "project_mode": "create_seed",
    "project_title": "Bathroom organizer refresh"
  }
}
```

### Behavior

- recompute `review_required` and `review_reason_codes` if target selection changes risk level
- preserve capture metadata and queue identity
- do not create output entities

## `POST /api/intake/source/{id}/validate`

Runs target-aware validation for the current route.

Expected checks include:

- duplicate or collision checks for `model`
- path/readability and policy checks for `working_file_group`
- minimum metadata checks for `idea`
- project existence or seed-title checks for `project`
- expansion/preflight checks for `collection`
- provenance-only safety checks for `link_only`

## `POST /api/intake/source/{id}/commit`

Commits the reviewed item to the chosen target type.

### Request body

```json
{
  "selected_target_type": "idea",
  "selected_target_id": null,
  "target_context": {
    "idea_visibility": "active"
  },
  "override_warnings": false
}
```

### Response body

```json
{
  "item_id": "intake_01jwn3q8z2g2s9w0yya3j7m4rf",
  "terminal_state": "rejected",
  "result": {
    "target_type": "idea",
    "entity_id": "idea_01jwn42hm5f8njx8qz2p7g0m1e"
  },
  "job_history_id": "job_01jwn438b0er8ay9kt5fp4c5za"
}
```

Implementation note:

- the terminal state names in the existing state machine may need additive expansion in implementation if `idea`, `project`, or `collection` outcomes should be distinguishable in Job History without overloading `grouped_*` or `published_to_catalog`
- if the existing terminal-state vocabulary is preserved, `terminal_action` should still record the exact target type separately

## `POST /api/intake/source/{id}/materialize_children`

Expands a `collection_container` item into child intake items.

### Request body

```json
{
  "mode": "chunked",
  "chunk_size": 50,
  "default_child_target_type": null,
  "auto_approve_high_confidence": false
}
```

## Validation Rules

### Review required by default when

- `trigger_class` is `background_sync` or `service_push`
- `source_profile` is `social_saved_link`, `task_item`, or `collection_container`
- `selected_target_type` is `idea`, `project`, or `collection`
- source confidence is below `high`
- duplicate warnings or auth/file-evidence gaps exist

### Fast-path bypass allowed only when

- `trigger_class` is `user_direct` or explicit `user_quick_action`
- `source_profile` is `provider_model_page`
- confidence is `high`
- `selected_target_type` is `model` or `working_file_group`
- no warnings requiring operator override exist

## UI Mapping Requirements

`Queue Review` should render these routing fields directly:

- `source_profile`
- `trigger_class`
- `suggested_targets_json`
- `selected_target_type`
- `review_required`
- `review_reason_codes`
- `origin_service`

`Intake Home` should render summarized routing signals:

- recent capture source mix
- recent suggested target mix
- background-sync health by `origin_service`

`Job History` should render the final routing outcome:

- final `selected_target_type`
- resulting entity id or target label
- original source profile and origin service where helpful

## Open Contract Questions

- Should `idea`, `project`, and `collection` outcomes each gain first-class terminal states, or should they remain differentiated by `terminal_action` metadata only?
- Should `selected_target_id` be nullable for `project` when the operator intends to create a seed project during commit?
- Should `link_only` create a durable local record in the same table family as ideas, or remain only a terminalized intake record plus provenance snapshot?