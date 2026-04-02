# Archive Mismatch Repair Design

> Analysis based on live Bambuddy API behavior observed on 2026-04-02 for issue `#793` in this repository and source review of `maziggy/bambuddy`.

## Goal

Define a Home Assistant-side detection and repair design for Bambuddy archives whose main archived `.3mf` payload is wrong for the print record, even though the archive itself is otherwise complete.

This is a different failure mode from fallback `no_3mf_available` archives:

- the archive row exists
- the archive has a real `file_path`
- thumbnail, G-code, and preview endpoints work
- but they work against the wrong archived file

## Why This Exists

Issue `#793` exposed a concrete case where a later archive record was renamed to the intended print name, but Bambuddy had already archived the wrong `.3mf` payload.

Observed evidence from the live API:

- archive `51` and archive `190` returned the same `content_hash`
- `GET /archives/190/duplicates` reported archive `51` as an exact duplicate
- `GET /archives?limit=250` reported archive `190` with `duplicate_sequence = 1` and `original_archive_id = 51`
- downloading both `GET /archives/{id}/download` payloads and hashing them produced the same SHA-256

That means Bambuddy did not merely mis-render the UI. It stored the same 3MF bytes for both records.

## Scope

### In scope

- detection of suspicious archive/file mismatches from Bambuddy API data
- manual review UX inside `print_history`
- repair workflow design that creates a replacement archive when the stored file is wrong
- tag and note conventions for preserving lineage between the bad archive and the replacement archive
- optional operator tooling for confirming whether a mismatch is metadata-only or file-level

### Out of scope

- direct mutation of Bambuddy database rows
- undocumented in-place replacement of archive file payloads
- automatic background deletion of bad archives

## Confirmed Bambuddy Behavior

### Duplicate detection is computed, not manually stored

Bambuddy persists `content_hash` on the archive row. `duplicate_count`, `duplicate_sequence`, and `original_archive_id` are computed at API response time from the current archive table.

Important consequence:

- there is no supported API to manually mark an archive as `not duplicate`
- there is no supported API to repoint an archive to a different duplicate parent

### Archive metadata can diverge from the archived file

`PATCH /archives/{id}` can change `print_name`, tags, notes, status, and similar metadata, but it cannot change:

- `content_hash`
- `file_path`
- `thumbnail_path`
- duplicate-parent linkage

Important consequence:

- if the wrong `.3mf` was archived and the user later renames the archive, the record can become internally inconsistent
- UI search and labels may look correct while preview, G-code, and duplicate grouping still reflect the wrong archived file

### Current Bambuddy repair APIs are insufficient for this failure mode

- `POST /archives/{id}/rescan` reparses the current archived file, so it preserves the wrong file problem
- `POST /archives/upload-source` attaches source provenance only and does not replace the main archived payload
- `POST /archives/upload` creates a new archive rather than repairing the old one in place

## Problem Definition

The system needs to distinguish between two classes of archive problems:

1. **Metadata-only mismatch**
   The archived `.3mf` is correct, but `print_name` or notes are wrong.

2. **File-level mismatch**
   The archive row refers to the wrong `.3mf` payload. Thumbnail, G-code, duplicate grouping, and previews are therefore all wrong.

Issue `#793` is class 2.

## Requirements

### Functional requirements

1. Surface suspicious same-hash, different-name relationships for operator review
2. Let the operator inspect duplicate chain members from Home Assistant
3. Provide a repair path that preserves history explainability
4. Avoid pretending there is an in-place repair when Bambuddy does not support one
5. Preserve enough lineage that the operator can see which archive was replaced and why

### Non-functional requirements

1. Prefer stable Bambuddy APIs over DB surgery
2. Keep browser cache lean and use on-demand detail for heavier diagnostics where practical
3. Minimize accidental destructive operations
4. Keep operator decisions explicit for suspicious duplicates

## Detection Model

This feature should not assume every same-hash, different-name pair is wrong. Some users may intentionally reuse the same file and rename the print record later.

Instead, detection should classify **suspected mismatches**.

### Signal 1: Same hash, materially different print names

Mark as suspicious when:

- two archives share `content_hash`
- `print_name` values normalize to different strings

This is the primary lightweight signal.

### Signal 2: Later archive points to an older original with different print name

Escalate suspicion when:

- `duplicate_sequence > 0`
- `original_archive_id` points to an older archive
- normalized names between current and original differ materially

This fits the exact `#793` pattern.

### Signal 3: Filename looks generic and does not resemble the current print name

Treat as a weak supporting signal when:

- `filename` is generic or repeated across unrelated prints
- normalized `filename` does not resemble normalized `print_name`

This should not stand alone because Bambu file naming can already be generic.

### Signal 4: Byte-identity confirmation

For manual diagnostics, offer a strong confirmation path:

1. fetch the current archive detail
2. fetch duplicate chain members
3. optionally download one or more 3MF payloads externally
4. compare hashes or byte identity

This is best treated as an operator or `n8n` validation step, not a routine dashboard action.

## Data Contract Additions

The current Layer 1 field projection intentionally drops `content_hash`, `file_path`, duplicate metadata, and detailed archive internals.

That is appropriate for the normal browser, but mismatch detection needs a slightly richer contract.

### Recommended browser-cache additions

Add these fields to the projected archive payload:

- `filename`
- `content_hash`
- `duplicate_count`
- `duplicate_sequence`
- `original_archive_id`

### Keep out of the general browser cache

Do not add `file_path` to the general list cache unless a concrete feature needs it in the browser layer.

Reason:

- it adds operator-noise more than user-facing value
- most mismatch review can start from hash, filename, and duplicate metadata
- deeper diagnostics can use `GET /archives/{id}` on demand from popup flows

## UX Design

### Level 1: Suspicion marker in history views

When an archive is suspected of mismatch, show a small warning affordance distinct from the normal duplicate indicator.

Suggested semantics:

- duplicate badge continues to mean `same archived file`
- mismatch badge means `same archived file but suspiciously different print name`

### Level 2: Popup diagnostic block

Archive detail popup should show:

- current archive `print_name`
- archived `filename`
- hash prefix
- duplicate sequence/original archive ID
- duplicate chain members with names and timestamps
- a short explanation when the duplicate chain names diverge

### Level 3: Review actions

Provide manual actions:

1. `Mark reviewed, legitimate duplicate`
2. `Rename metadata only`
3. `Create replacement archive from correct 3MF`
4. `Open lineage notes/tags`

Deletion should remain a deliberate secondary admin action, not the first suggested action.

## Repair Model

## Chosen direction

Treat file-level mismatch repair as **replacement**, not in-place editing.

### Repair path A: Metadata-only correction

Use when the operator confirms the archived file is correct and only the record label is wrong.

Action:

- `PATCH /archives/{id}` for `print_name`, tags, notes, status, etc.

### Repair path B: Replacement archive creation

Use when the archived file is wrong.

Workflow:

1. obtain the correct `.3mf` from operator upload, printer-side recovery, or another trusted source
2. create a new archive with `POST /archives/upload`
3. PATCH old and new archives with lineage tags/notes
4. optionally mark the old archive as superseded in the dashboard
5. optionally let the operator delete the old archive after verification

### Why replacement is the correct model

- it uses supported Bambuddy APIs
- it creates a fresh `content_hash`, thumbnail, preview, and G-code path
- it does not rely on undocumented file replacement behavior

## Recommended Tagging Convention

For the bad archive:

- `exception:wrong_archive_file`
- `repair:superseded`
- `replacement_archive:{new_id}`

For the replacement archive:

- `repair:replacement`
- `replaces_archive:{old_id}`

Optional note on the old archive:

```text
Archive retained for audit only. The archived 3MF did not match the intended print record.
Replacement archive: #<new_id>
```

Optional note on the new archive:

```text
Created as the canonical replacement for archive #<old_id> after wrong-file archive detection.
```

## HA / `n8n` Workflow Shape

### Manual mode first

Recommended first implementation:

1. operator opens archive popup
2. HA shows mismatch evidence from Bambuddy data
3. operator triggers a repair script or webhook
4. external worker uploads the correct 3MF to Bambuddy
5. HA patches lineage notes/tags on both archive records
6. HA refreshes the print history cache

### Future automation modes

Possible later modes:

- detect and queue suspicious mismatches automatically for review
- recover the correct file from printer/cache when recent enough
- auto-create replacement archive only after a human approval gate

## Upstream Improvement Wishlist

If Bambuddy adds stronger repair primitives later, the preferred API improvements would be:

1. `POST /archives/{id}/replace-file` to rebuild the archive in place from a provided 3MF
2. duplicate override metadata for legitimate same-hash-but-distinct-history cases
3. archive audit history for `print_name` and file replacement changes

Until then, replacement archive creation is the safest supported path.

## Recommended Phase Plan

### Phase 1: Detection only

- enrich Layer 1 payload with hash and duplicate fields
- add suspicion marker and popup diagnostics
- add issue-review documentation

### Phase 2: Manual replacement workflow

- add HA action to launch operator-approved replacement flow
- define `n8n` request/response contract for replacement uploads
- PATCH lineage notes/tags after replacement

### Phase 3: Review queue and operator tooling

- add mismatch exception card or filtered collection
- add reviewed/legitimate state handling
- optionally support old-archive deletion after operator verification