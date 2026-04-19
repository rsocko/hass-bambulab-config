# Archive Enrichment Metadata Services

This document defines the Home Assistant service contract for inspecting and editing the system-managed enrichment metadata stored on Bambuddy archives.

These services are intentionally narrower than the general popup edit flow. They are for operator or UI workflows that need to read and replace only the managed enrichment subset:

- system tags such as `f:<id>` and `s:<id>`
- the hidden `+>` note payload
- per-slot manual override rows for known tray, spool, or filament identity
- the optional recovery audit note block that manual re-enrich may preserve ahead of the hidden payload

They do not edit operator-managed tags or freeform user notes directly.

## Goals

- expose the managed enrichment subset in a structured form that can be shown to the user
- let operator tooling replace that managed subset without guessing how to preserve user tags or user notes
- keep the write contract conservative by treating each supplied managed subset as a full replacement, not a partial patch

## Service Names

- `bambuddy.get_print_history_archive_enrichment_metadata`
- `bambuddy.update_print_history_archive_enrichment_metadata`

## Read Service

### `bambuddy.get_print_history_archive_enrichment_metadata`

Required input:

- `archive_id`

Optional input:

- `entry_id`
- `mode`

Supported `mode` values:

- `ALL` — return all hidden payload rows
- `ANY_MISSING_DATA` — return only rows with any missing tray, spool, or filament identity
- `MISSING_SPOOL` — return only rows missing `s`
- `MISSING_FILAMENT` — return only rows missing `f`

The service returns:

- basic archive detail needed for review
- `tag_metadata`
  - `raw_tags`
  - `system_tags`
  - `user_tags`
- `note_metadata`
  - `marker`
  - `recovery_marker`
  - `system_notes`
  - `user_notes`
  - `recovery_block`
  - `payload`
  - `payload_raw`
  - `payload_rows`
  - `filtered_payload_rows`
  - counts and filtered row indices

Important behavior:

- the service always returns the full managed payload object
- `mode` only filters the returned row view for operator review
- `mode` does not trim the canonical payload returned in `note_metadata.payload`

That split exists so a UI can focus on unresolved rows while still holding the full managed dataset needed for a safe write-back.

## Write Service

### `bambuddy.update_print_history_archive_enrichment_metadata`

Required input:

- `archive_id`

Optional input:

- `entry_id`
- `tag_metadata`
- `note_metadata`
- `slot_overrides`

At least one of `tag_metadata`, `note_metadata`, or `slot_overrides` must be provided.

### `tag_metadata`

`tag_metadata` is a full replacement for the managed tag subset.

Required fields:

- `system_tags`

Rules:

- only system-managed tags are accepted here
- user tags are preserved from the current archive automatically
- missing tags in `system_tags` are treated as intentional removal from the managed subset

### `note_metadata`

`note_metadata` is a full replacement for the managed note subset.

Required fields:

- `payload`

Optional fields:

- `recovery_block`
- `slot_overrides`

Rules:

- the service preserves the current archive's user-authored notes automatically
- the supplied `payload` replaces the hidden `+>` payload as a whole
- the supplied `recovery_block` replaces the recovery audit block as a whole
- the supplied `slot_overrides` replace the managed slot override subset as a whole
- omitted row entries inside `payload.F` are treated as intentional removal because `payload` is authoritative

### `slot_overrides`

`slot_overrides` is the operator-friendly form of the managed per-slot override subset.

Each row must include:

- `slot_id`

Each row must also include at least one of:

- `tray`
- `spool_id`
- `filament_id`

Example:

```json
[
  {"slot_id": "0", "tray": "A2", "spool_id": 252, "filament_id": 25},
  {"slot_id": "1", "tray": "B1", "filament_id": 31}
]
```

Rules:

- `slot_overrides` can be sent either as a top-level service field or inside `note_metadata`
- the override list is stored inside the managed hidden payload so review UIs only need one canonical note object
- an empty list removes the managed slot override subset

## Why Full Replacement

Partial row updates look attractive but create ambiguity fast:

- removing one `s:<id>` tag does not say whether the caller intended to keep or recompute the other system tags
- updating one row in `payload.F` without the full payload makes it unclear whether untouched rows should remain, be dropped, or be reindexed
- patching one slot override without the full override list makes it unclear whether other known overrides should remain active
- filtered review modes such as `MISSING_SPOOL` are a view concern, not a persistence contract

For that reason the write service uses a strict rule:

- each supplied managed subset must be complete for that subset

This keeps the merge logic simple and safe:

- preserve user tags
- preserve user notes
- replace only the managed subset the caller explicitly supplied
- manual slot overrides are treated as their own managed subset with full-replacement semantics

## Persistence Rules

When writing:

- managed tags are rebuilt as `user_tags + system_tags`
- managed notes are rebuilt as `user_notes + recovery_block + +>payload`
- managed slot overrides are stored inside `payload.slot_overrides`
- empty payload dict means the hidden enrichment payload is removed
- empty `system_tags` list means the managed tag subset is removed
- empty `slot_overrides` list means the managed slot override subset is removed

The service then refreshes the targeted archive through the Bambuddy custom integration so the Variant 3 store, popup, and browser stay in sync.

## UI Guidance

Recommended UI behavior:

- call the read service with `mode = ALL` to obtain the canonical editable object
- optionally use `filtered_payload_rows` from a second read or from the same response for focused review
- when saving, send the full `tag_metadata` or full `note_metadata` object back
- when saving slot overrides, send the full `slot_overrides` array back
- do not send only filtered rows from `MISSING_SPOOL` or `MISSING_FILAMENT` mode

## Relationship To Manual Re-Enrich

These services do not replace `script.reenrich_print_history_archive`.

Manual re-enrich remains the heuristic recovery path that tries to reconstruct spool lineage from archive detail and current Spoolman data.

The new services are the explicit operator override path for cases where the operator already knows the correct managed metadata and wants to inspect or replace it directly.

Manual re-enrich now consumes `slot_overrides` first. Overrides supply explicit tray, spool, or filament identity for a given archived slot row, and the heuristic matcher only fills in any remaining gaps.