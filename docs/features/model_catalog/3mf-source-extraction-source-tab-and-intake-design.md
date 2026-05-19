# 3MF Source Extraction - Source Tab Trigger + Intake Reuse Design

> **Status**: Proposed
> **Last updated**: 2026-05-19
> **Scope**: Add operator-triggered source metadata extraction from attached 3MF files, with shared backend logic that can also run during intake publish.

## Problem Statement

The model detail popup already allows manual editing of source metadata (`publication_source`, `source_urls`, `source_download_url`, and related labels), but there is no built-in action to derive those fields from embedded metadata in attached 3MF files.

This causes:

- repeated manual effort when imported models already contain source hints
- inconsistent source metadata quality across catalog entries
- no shared extraction path that intake publish can reuse

This work is intentionally separate from 3MF cleaning-for-publication workflows. The goal is provenance/source extraction, not output sanitization.

## Goals

- Add a Source-tab action to scan attached 3MF files and propose source metadata updates.
- Support dry-run preview before applying changes.
- Handle mixed-source models safely and predictably.
- Reuse the same extraction service in intake publish.
- Preserve operator authority by default (fill blanks unless overwrite is explicitly requested).

## Non-Goals

- No 3MF geometry transformations or metadata cleaning/repacking.
- No automatic publication workflow execution.
- No hard dependency on remote APIs for extraction.

## UX Placement and Operator Flow

## Source Tab Placement

Add an action button in the existing Source section of the popup:

- Label: `Extract from attached 3MF`
- Placement: Source block header, near Source URLs controls

## Interaction Flow

1. Operator clicks `Extract from attached 3MF`.
2. Frontend calls a dry-run endpoint and receives extraction results plus a proposed patch.
3. Popup shows a review panel containing:
   - scanned files and per-file evidence
   - detected platform(s)
   - detected source URLs
   - conflict summary (single source vs mixed)
   - exactly which fields would change
4. Operator chooses:
   - `Apply suggested changes`
   - `Apply only to empty fields`
   - `Cancel`

## Backend Contract

## New Shared Service

Create a service module dedicated to source extraction so both UI-triggered flow and intake flow use one implementation.

Suggested module:

- `sidecars/model_catalog/app/services/source_metadata_extractor.py`

Suggested service function shape:

- `extract_source_metadata_from_model_3mfs(db_path, model_ref, file_ids=None) -> SourceExtractionResult`

Where `SourceExtractionResult` includes:

- list of scanned 3MF files
- per-file findings (urls, detected platform, candidate IDs, confidence)
- deduped URL set
- recommended `publication_source`
- recommended `source_download_url`
- optional `source_platform_label` for mixed/custom cases
- proposed field updates and conflict flags

## New API Endpoint

Add endpoint on models router:

- `POST /api/models/{model_ref}/source/extract`

Payload:

```json
{
  "file_ids": ["optional", "subset"],
  "apply": false,
  "overwrite_existing": false,
  "mode": "fill_missing"
}
```

Response:

```json
{
  "success": true,
  "model_ref": "...",
  "summary": {
    "files_scanned": 3,
    "sources_detected": ["makerworld", "printables"],
    "has_conflict": true
  },
  "evidence": [...],
  "proposed_updates": {
    "publication_source": "other",
    "source_platform_label": "Mixed (auto-detected)",
    "source_urls": ["https://...", "https://..."],
    "source_download_url": "https://..."
  },
  "applied": false
}
```

If `apply=true`, backend persists updates and returns both proposed and applied values.

## Extraction Rules and Conflict Policy

## Platform Detection

Detect platform from known URL/domain signals and known metadata keys within 3MF package internals.

Initial platform set:

- makerworld
- printables
- thingiverse
- cults3d
- thangs
- myminifactory
- other

## Field Mapping

- `source_urls`: union of all valid extracted URLs, deduped, stable order
- `source_download_url`: selected canonical URL (if a clear best candidate exists)
- `publication_source`: selected using rules below
- `source_platform_label`: set when needed for `other` or mixed-source explanation

## Single-Source Model Rule

If all reliable findings map to one platform:

- set `publication_source` to that platform
- set `source_urls` to deduped list
- set `source_download_url` to canonical URL if determinable

## Mixed-Source Model Rule

If findings indicate 2+ distinct platforms:

- set `publication_source` to `other`
- set `source_platform_label` to `Mixed (auto-detected)`
- set `source_urls` to all deduped URLs
- only set `source_download_url` when exactly one high-confidence canonical URL exists

## No-Reliable-Data Rule

If no reliable source metadata is found:

- do not modify source fields
- return `success=true` with empty proposed patch and diagnostic notes

## Write Safety

Default mode should be `fill_missing`.

- Existing non-empty fields remain unchanged unless `overwrite_existing=true`.
- Manual operator values are authoritative.

## Intake Reuse

During intake publish, call the same extraction service after files are imported and model assets exist.

Default intake behavior:

- run extraction
- apply only missing source fields
- store extraction summary in intake metadata/history for auditability

Optional intake flag for bulk repair workflows:

- `source_extraction_overwrite=true` (explicit opt-in)

## Data Contract and Auditability

Existing fields to use:

- `publication_source`
- `source_platform_label`
- `source_urls`
- `source_download_url`

Optional new internal fields (if needed for diagnostics):

- `source_extraction_last_run_at`
- `source_extraction_last_mode`
- `source_extraction_last_summary`

These are optional and should remain internal, not required by UI.

## Testing Strategy

## Backend Tests

- unit tests for extractor parsing and platform detection
- unit tests for conflict resolution policy
- endpoint tests for dry-run and apply modes
- intake integration tests confirming shared service behavior

## Frontend Tests

- Source tab action visibility and button behavior
- review panel rendering with single-source and mixed-source payloads
- apply/cancel flows

## Edge Cases

- model has no 3MF assets
- malformed ZIP or missing expected entries
- duplicate URLs across files
- mixed sources with one malformed URL set
- existing manual fields with `fill_missing` mode

## Delivery Plan

## Phase 1 - Core Extraction and Operator Trigger

- shared backend extractor service
- new `/source/extract` endpoint with dry-run/apply
- Source tab button + review/apply UX
- conflict handling (`other` + mixed label + URL list)
- intake hook in `fill_missing` mode

## Phase 2 - Richer Enrichment and Smarter Canonicalization

- richer per-platform candidate parsing (creator handles, platform IDs)
- improved canonical URL ranking with confidence scoring
- optional secondary auto-fill fields behind explicit operator acceptance
- scheduled or batch re-extract utility for historical catalog repair

## Open Questions

- Should mixed-source always force `publication_source=other`, or should frontend offer a user override before apply?
- Should Phase 1 write optional internal extraction diagnostics fields, or defer to keep schema unchanged?
- Should intake run extraction synchronously in publish request or asynchronously as a follow-up job?

## Recommended Default Decisions

- Phase 1 keeps extraction synchronous for predictable operator feedback.
- Mixed-source defaults to `other` with explicit URL list preserved.
- Intake applies only missing fields by default.
