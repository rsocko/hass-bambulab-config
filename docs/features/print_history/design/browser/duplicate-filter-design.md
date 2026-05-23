# Print History Duplicate Filter Design

## Purpose

Define the first implementation slice for issue `#737`: duplicate-aware browsing in the Bambuddy-backed print-history browser without widening Layer 1 into a full duplicate-members cache.

## Scope

This document covers:

- duplicate metadata fields that may be persisted in the Variant 3 archive projection
- duplicate filter semantics for the browser
- card and popup rendering rules for duplicate summaries
- the phased split between browser visibility now and related-item workflows later

This document does not cover:

- compare APIs or compare popups
- suspicious same-hash repair review
- enrichment-time duplicate tags or notifications
- manual repair-lineage UX

## Source Of Truth

Use Bambuddy archive payload duplicate metadata as the source of truth for this phase:

- `duplicate_count`
- `duplicate_sequence`
- `original_archive_id`

Do not use manual `archive_repair_lineage` rows as the primary duplicate source for issue `#737`. Those rows remain a separate operator-managed provenance surface.

## Layer Ownership

### Layer 1

Allowed fields:

- `duplicate_count`
- `duplicate_sequence`
- `original_archive_id`

Not allowed in Layer 1 for this feature:

- Bambuddy `duplicates` arrays
- related-item labels
- tooltip wording
- popup/card-specific summaries

### Layer 2

Layer 2 owns duplicate filter semantics and classification.

Supported filter values:

- `All`
- `Originals Only`
- `Duplicates Only`

Classification rules:

- duplicate child: `original_archive_id` is present or `duplicate_sequence > 0`
- duplicate original/root: `duplicate_count > 0` and the archive is not a duplicate child

### Layer 3

Layer 3 owns final UI wording.

Current rendering rules:

- original rows in duplicate sets show a compact original chip with total set size
- duplicate rows show a compact duplicate chip with sequence and original reference when available
- non-duplicate rows show no duplicate chip
- the popup shows the same role as a read-only summary plus supporting duplicate facts

## Popup Rules

- render duplicate context from the existing page payload
- do not require a second detail fetch just for duplicate summary
- do not add matching-item navigation or compare actions in this phase

## Phased Rollout

### Phase 1

- project compact duplicate fields
- store them in Variant 3
- add browser filter support
- render duplicate chips on `Compact`, `Media`, and `List`
- render a popup read-only duplicate summary

### Phase 2

- add popup navigation to matching archives if the browser contract needs it
- add a dedicated duplicate-members query path rather than bloating Layer 1

### Phase 3

- integrate compare flows and suspicious same-hash review with the archive mismatch design work

## Guardrails

- keep duplicate classification logic centralized in the query layer when possible
- do not duplicate full duplicate-member payloads into every page row
- do not let popup wording force Layer 1 schema expansion
- preserve the current three-layer print-history contract documented elsewhere in this folder