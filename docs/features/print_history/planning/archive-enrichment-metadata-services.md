# Archive Enrichment Metadata Services

This document defines the Home Assistant service contract for inspecting and editing the system-managed enrichment metadata stored on Bambuddy archives.

These services are intentionally narrower than the general popup edit flow. They are for operator or UI workflows that need to read and replace only the managed enrichment subset:

- system tags such as `f:<id>` and `s:<id>`
- the hidden `+>` note payload
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

At least one of `tag_metadata` or `note_metadata` must be provided.

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

Rules:

- the service preserves the current archive's user-authored notes automatically
- the supplied `payload` replaces the hidden `+>` payload as a whole
- the supplied `recovery_block` replaces the recovery audit block as a whole
- omitted row entries inside `payload.F` are treated as intentional removal because `payload` is authoritative

## Why Full Replacement

Partial row updates look attractive but create ambiguity fast:

- removing one `s:<id>` tag does not say whether the caller intended to keep or recompute the other system tags
- updating one row in `payload.F` without the full payload makes it unclear whether untouched rows should remain, be dropped, or be reindexed
- filtered review modes such as `MISSING_SPOOL` are a view concern, not a persistence contract

For that reason the write service uses a strict rule:

- each supplied managed subset must be complete for that subset

This keeps the merge logic simple and safe:

- preserve user tags
- preserve user notes
- replace only the managed subset the caller explicitly supplied

## Persistence Rules

When writing:

- managed tags are rebuilt as `user_tags + system_tags`
- managed notes are rebuilt as `user_notes + recovery_block + +>payload`
- empty payload dict means the hidden enrichment payload is removed
- empty `system_tags` list means the managed tag subset is removed

The service then refreshes the targeted archive through the Bambuddy custom integration so the Variant 3 store, popup, and browser stay in sync.

## UI Guidance

Recommended UI behavior:

- call the read service with `mode = ALL` to obtain the canonical editable object
- optionally use `filtered_payload_rows` from a second read or from the same response for focused review
- when saving, send the full `tag_metadata` or full `note_metadata` object back
- do not send only filtered rows from `MISSING_SPOOL` or `MISSING_FILAMENT` mode

## Relationship To Manual Re-Enrich

These services do not replace `script.reenrich_print_history_archive`.

Manual re-enrich remains the heuristic recovery path that tries to reconstruct spool lineage from archive detail and current Spoolman data.

The new services are the explicit operator override path for cases where the operator already knows the correct managed metadata and wants to inspect or replace it directly.