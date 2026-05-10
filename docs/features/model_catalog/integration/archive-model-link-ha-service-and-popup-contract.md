# Archive Model Link HA Service And Popup Contract

> **Status**: Proposed contract with Phase 6 search/picker extensions.

## Purpose

Define the Home Assistant-facing service contract and archive-popup UX contract for archive-to-curated-model linkage.

This document is intentionally narrower than the broader integration strategy.

It answers:

- which HA services should exist first
- what payloads those services should accept
- what success and error responses should look like
- how the `print_history` archive popup should surface link state, candidate review, and open actions

## Scope

This contract covers the archive-centric linkage surface and its Phase 6 picker/search extensions:

- link a Bambuddy archive to one source-model identity
- optionally associate that identity with a sidecar-owned curated model
- surface link state in the archive popup
- support manual review and low-risk operator actions from HA
- support explicit curated search/picker fallback when candidate refresh is insufficient

This contract still does not cover:

- broad model-edit parity beyond archive-linked actions
- full library browsing UI inside HA
- graph lineage UIs
- bidirectional metadata sync beyond explicit operator actions

## Service Naming Direction

The first implementation should extend the existing `bambuddy` domain.

Recommended initial services:

- `bambuddy.get_archive_model_link`
- `bambuddy.refresh_archive_model_link_candidates`
- `bambuddy.create_archive_model_link`
- `bambuddy.accept_archive_model_link`
- `bambuddy.reject_archive_model_link`
- `bambuddy.deactivate_archive_model_link`
- `bambuddy.open_linked_model_target`

Recommended later services:

- `bambuddy.search_curated_models`
- `bambuddy.open_archive_model_picker`

## Common Service Conventions

### Shared Inputs

Every service should accept:

- optional `entry_id`
- `archive_id` when the operation is archive-scoped

### Shared Response Shape

Recommended success envelope:

```json
{
  "success": true,
  "entry_id": "abcd1234",
  "archive_id": 4812,
  "link": {
    "id": 17,
    "source_sha256": "2a5c...",
    "source_canonical_path": "D:/3D Printing/Library/Gridfinity/box.3mf",
    "source_kind": "source_3mf",
    "model_ref": "gridfinity-box",
    "relationship_type": "source_for",
    "match_method": "manual",
    "match_confidence": "high",
    "review_state": "accepted",
    "is_active": true,
    "updated_at": "2026-04-21T20:15:05Z"
  },
  "meta": {
    "candidate_count": 0,
    "catalog_authority": "sidecar_local"
  }
}
```

Recommended error envelope:

```json
{
  "success": false,
  "error": "link_not_found",
  "message": "No active archive model link exists for archive 4812.",
  "entry_id": "abcd1234",
  "archive_id": 4812
}
```

### Shared Error Codes

Recommended initial error codes:

- `invalid_payload`
- `resolve_failed`
- `archive_not_found`
- `link_not_found`
- `candidate_not_found`
- `ambiguous_match`
- `catalog_unavailable`
- `open_target_unavailable`
- `storage_unavailable`

## 1. `get_archive_model_link`

Purpose:

- fetch the current active link and any lightweight candidate summary for one archive

Inputs:

- optional `entry_id`
- required `archive_id`
- optional `include_candidates` with default `true`

Suggested payload schema:
- optional `model_ref`
archive_id: int
include_candidates: bool = true
```

Success response additions:

- `link`: active accepted or unreviewed link, or `null`
- `candidates`: optional compact candidate list
- `popup_summary`: compact projection intended for popup rendering

Recommended compact candidate shape:

```json
{
  "id": 33,
  "source_sha256": "2a5c...",
  "source_label": "Gridfinity Box",
  "source_canonical_path": "D:/3D Printing/Library/Gridfinity/box.3mf",
  "model_ref": "gridfinity-box",
  "model_name": "Gridfinity Box",
  "match_method": "sha256_exact",
  "match_confidence": "high",
  "review_state": "unreviewed"
}
```

## 2. `refresh_archive_model_link_candidates`

Purpose:

- re-run candidate discovery for one archive without automatically accepting ambiguous results

Inputs:

- optional `entry_id`
- required `archive_id`
- required `archive_name`
- optional `force_refresh_model_cache` default `false`

Current shipped baseline:

- `archive_name`
- optional `min_score`
- optional `max_candidates`
- optional `force_refresh_model_cache`

Deferred candidate-broadening inputs for a later phase:

- optional `archive_completed_at`
- optional `source_file_name`
- optional `source_hash`
- optional `allow_filename_fallback` default `true`
- optional `allow_time_proximity` default `true`
- optional `prefer_recent_uploads` default `true`
- optional `recent_upload_window_days` default `14`

Suggested payload schema:

```yaml
entry_id: string?
archive_id: int
archive_name: string
archive_completed_at: datetime?
source_file_name: string?
source_hash: string?
allow_filename_fallback: bool = true
allow_time_proximity: bool = true
prefer_recent_uploads: bool = true
recent_upload_window_days: int = 14
force_refresh_model_cache: bool = false
```

Success response additions:

- `created_or_updated_count`
- `active_link_changed`
- `candidates`

Behavior:

- exact hash matches may be auto-created as `accepted` only when the result is unique and deterministic
- recent-upload or time-proximity boosts should only affect ranking when another identity hint overlaps
- filename/name/time fallback matches should remain `needs_operator_review` or `unreviewed`
- candidate rows should include enough explanation for the popup to show why the candidate was suggested

Status note:

- the shipped Phase 2 popup linkage baseline only implements review-first candidate refresh using archive-name overlap plus optional cache refresh
- heuristic broadening, richer candidate rationale, and explicit curated picker/search behavior are defined by the current Phase 6 search/discovery design

## 2a. `search_curated_models`

Purpose:

- let the archive popup open an explicit curated-model picker/search flow when candidate refresh is empty, weak, or operator-bypassed

Inputs:

- optional `entry_id`
- required `archive_id`
- optional `query`
- optional `offset`
- optional `limit`
- optional `sort`
- optional `include_facets`

Suggested payload schema:

```yaml
entry_id: string?
archive_id: int
query: string?
offset: int = 0
limit: int = 25
sort: relevance | recent | frequent | common | favorites | queue_rank = relevance
include_facets: bool = false
```

Behavior:

- default to curated-model results only
- use archive context as a ranking boost, not a hidden hard filter
- keep explicit search results visually distinct from candidate-refresh rows in the popup
- selecting a result should flow through normal reviewed link creation or acceptance behavior

## 3. `create_archive_model_link`

Purpose:

- create or upsert an explicit archive-to-model link from operator input

Inputs:

- optional `entry_id`
- required `archive_id`
- optional `source_sha256`
- optional `source_path`
- required `source_kind`
- optional `model_ref`
- optional `relationship_type` default `source_for`
- optional `match_method` default `manual`
- optional `review_note`
- optional `linked_by`

Suggested payload schema:

```yaml
entry_id: string?
archive_id: int
source_sha256: string?
source_path: string?
source_kind: source_3mf | sliced_3mf | gcode_3mf | other_supporting_asset
model_ref: string?
relationship_type: source_for | derived_from | printed_from | family_anchor = source_for
match_method: manual | sha256_exact | path_exact | filename_and_time_window = manual
review_note: string?
linked_by: string?
```

Validation rules:

- reject when both `source_sha256` and `source_path` are absent
- reject when `relationship_type` is not in the supported set
- reject when `model_ref` cannot be resolved to a current sidecar-owned curated model

Behavior:

- created links should default to `review_state=accepted` when `match_method=manual`
- if an active link already exists for the same archive and same source identity, update in place rather than duplicating

## 4. `accept_archive_model_link`

Purpose:

- mark a candidate or unreviewed link as the accepted active link for the archive

Inputs:

- optional `entry_id`
- required `archive_id`
- required `link_id`
- optional `review_note`
- optional `linked_by`

Suggested payload schema:

```yaml
entry_id: string?
archive_id: int
link_id: int
review_note: string?
linked_by: string?
```

Behavior:

- set selected link to `review_state=accepted`
- set selected link `is_active=true`
- deactivate competing active links for the same archive if they exist
- preserve prior records rather than deleting them

## 5. `reject_archive_model_link`

Purpose:

- mark a candidate as reviewed and rejected without deleting provenance

Inputs:

- optional `entry_id`
- required `archive_id`
- required `link_id`
- optional `review_note`
- optional `linked_by`

Suggested payload schema:

```yaml
entry_id: string?
archive_id: int
link_id: int
review_note: string?
linked_by: string?
```

Behavior:

- set `review_state=rejected`
- prefer `is_active=false`
- do not remove audit history

## 6. `deactivate_archive_model_link`

Purpose:

- remove an active link from day-to-day use without destroying its historical record

Inputs:

- optional `entry_id`
- required `archive_id`
- required `link_id`
- optional `reason`

Suggested payload schema:

```yaml
entry_id: string?
archive_id: int
link_id: int
reason: string?
```

Behavior:

- set `is_active=false`
- keep current review state unchanged unless explicitly overridden later

## 7. `open_linked_model_target`

Purpose:

- return or launch the correct destination for the linked model from an archive popup

Inputs:

- optional `entry_id`
- required `archive_id`
- optional `target` default `ha_panel`

Supported targets:

- `ha_panel`
- `catalog_browser`
- `bambuddy`

Suggested payload schema:

```yaml
entry_id: string?
archive_id: int
target: ha_panel | catalog_browser | bambuddy = ha_panel
```

Success response additions:

- `target`
- `url`
- `link`

Recommended behavior:

- if `target=catalog_browser`, require an accepted link with `model_ref`
- if `target=bambuddy`, allow future support for archive-local source file or Bambuddy library file destinations
- if `target=ha_panel`, open the HA-native panel only when that panel exists

## Popup Wiring Contract

## Entry Point In The Current Popup

Recommended files:

- `homeassistant/www/3d_printing/print_history/print-history-browser-card.js`
- `homeassistant/www/3d_printing/print_history/print-history-archive-actions-card.js`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/print_history_archive_popup_content.yaml`

The first model-library slice should extend the existing archive popup, not open a separate unrelated modal first.

## Popup Summary Contract

The popup should receive a compact model-library summary from a detail entity or service-backed fetch.

Recommended compact projection:

```json
{
  "has_link": true,
  "review_state": "accepted",
  "candidate_count": 2,
  "active_link": {
    "id": 17,
    "source_label": "Gridfinity Box",
    "source_kind": "source_3mf",
    "source_canonical_path": "D:/3D Printing/Library/Gridfinity/box.3mf",
    "model_ref": "gridfinity-box",
    "model_name": "Gridfinity Box",
    "relationship_type": "source_for",
    "match_method": "manual",
    "match_confidence": "high"
  }
}
```

This summary should be added to archive detail state, not dumped into the page-browse payload.

## Popup Sections

### Section 1: Linked Model Summary

Show:

- linked state badge: `Linked`, `Needs Review`, or `Unlinked`
- source label
- curated model name when present
- match method and confidence
- compact source path or source hash hint

### Section 2: Actions

Recommended first actions:

- `Open Model`
- `Find Link Candidates`
- `Accept Link`
- `Reject Link`
- `Unlink`

Action behavior:

- `Open Model` should prefer the configured default open target
- `Find Link Candidates` should call `bambuddy.refresh_archive_model_link_candidates`
- `Accept Link` and `Reject Link` should only appear when a candidate or pending review exists
- `Unlink` should call `bambuddy.deactivate_archive_model_link`

### Section 3: Candidate Review

When candidate rows exist, render a compact review list with:

- source label
- curated model label if present
- match method
- match confidence
- primary action button per row

Recommended primary actions:

- `Accept`
- `Reject`

## Popup UX States

### Accepted Link

Show:

- green or positive link badge
- `Open Model`
- `Unlink`
- optional `Refresh Candidates`

### Needs Review

Show:

- warning badge
- top candidate list
- `Accept` or `Reject` actions
- `Open Model` only when the candidate has an eligible target

### Unlinked

Show:

- neutral badge
- `Find Link Candidates`
- optional `Create Link` action later

## Suggested Browser Mod Sequence

For popup review actions, prefer the same pattern already used elsewhere in `print_history`:

1. call the relevant `bambuddy.*archive_model_link*` service
2. refresh popup detail state if needed
3. keep the popup open when the action succeeds
4. show inline success or error status inside the popup action area

Do not close and reopen the popup for normal accept or reject flows.

## Initial Custom Card Contract

The first UI slice does not need a large dedicated library browser card.

It may need one small focused card if the existing popup template becomes too dense.

Recommended config shape if a dedicated popup review card is introduced:

```yaml
type: custom:print-history-archive-model-link-card
archive_json: "{}"
detail_entity: sensor.print_history_popup_archive_detail
status_entity: sensor.bambuddy_model_library_status
api_base_entity: input_text.bambuddy_api_base_url
```

Responsibilities:

- render compact link summary
- render candidate review buttons
- call HA services, not direct upstream APIs

## Suggested Implementation Order

1. add service schemas to `homeassistant/custom_components/bambuddy/__init__.py`
2. add lightweight persistence and query helpers behind those services
3. extend popup detail payload with compact `model_library_summary`
4. add popup summary rendering and review actions
5. defer broader library search and panel browsing until the archive-centric flow is proven