# Print History Issue Update Drafts (2026-04)

## Purpose

This document converts the recent print-history design review and metadata roadmap into issue-ready text.

Use it to update existing issues or create new ones without creating a second planning track outside GitHub.

The intent is:

- keep tracking anchored to the current Variant 3 architecture
- keep Variant 4 as a future execution-boundary option, not a separate metadata plan
- connect the external-services review back to existing issues
- only introduce new issues where the current set does not provide a clean implementation anchor

## Recommended Tracker Strategy

### Keep These As Existing Anchors

- `#197` and `#198` remain the main metadata-definition anchors
- `#235` remains the Node-RED reference issue for event-ledger and artifact-capture ideas
- `#248` remains the spool/provenance reference issue
- `#793` remains the mismatch/repair pressure-test issue for provenance and event history
- `#426`, `#649`, and `#650` remain the power and cost integration anchors
- `#110`, `#111`, `#112`, `#113`, and `#116` remain the main analytics/UI surfacing anchors

### Add New Issues Only For Missing Implementation Units

Recommended new issues:

1. Variant 3 metadata schema hardening
2. Per-archive event timeline capture
3. Print-start artifact metadata extraction
4. Structured spool snapshot provenance

These are implementation anchors that do not map cleanly to a single existing issue today.

## Existing Issue Update Drafts

The text below is written to be copied into GitHub comments or issue-description updates.

### Update Draft For `#197` / `#198`

Suggested use:

- post this on both issues, or
- merge the wording into whichever one you want to keep as the primary metadata-definition tracker

Draft:

```md
Design update after the 2026-04 print-history review:

We now have a clearer direction for print-history metadata, and it stays aligned to the active Variant 3 architecture rather than introducing a parallel model.

Key decisions:

- Bambuddy remains the authoritative source for archive-core fields.
- Variant 3 remains the place where we extend the integration-owned local materialized store.
- Variant 4 is still deferred; if we ever promote it, it should reuse the same metadata model behind a sidecar boundary rather than redefining the schema.
- New metadata work should NOT widen Layer 1 with UI-only labels or card-specific wording.

Planned metadata additions:

- explicit derived metric storage for estimated vs actual weight, duration, filament cost, and energy cost
- per-archive event timeline rows
- structured spool snapshot provenance
- print-start artifact metadata extracted from `.3mf` or related artifacts when available
- broader lineage rows for duplicate / reprint / compare / mismatch relationships

Reference docs:

- `docs/features/print_history/external-services-design-review-2026-04.md`
- `docs/features/print_history/variant3-metadata-schema-and-variant4-carry-forward.md`
- `docs/features/print_history/metadata-implementation-roadmap.md`

Recommended next step from this issue:

- use `#197` / `#198` as the main metadata-definition anchor
- track implementation in child issues for schema hardening, event timeline capture, artifact extraction, and spool provenance
```

### Update Draft For `#235`

Draft:

```md
Design review follow-up:

The Node-RED + Postgres flow reviewed here is useful as a source of implementation ideas, but not as a platform we should adopt for print history.

Current conclusion:

- We should NOT add Node-RED as a required dependency.
- We SHOULD adopt several of its strongest patterns inside the current Variant 3 integration/store path.

Most valuable ideas from this issue:

- a per-print event ledger (`started`, `paused`, `resumed`, `failed`, `stopped`, `finished`)
- print-start artifact extraction from `.3mf` for preview image, estimated weight, and file-derived material/profile metadata
- explicit `estimated_*` vs `actual_*` metric fields
- per-print energy-cost joins where power-monitoring data exists
- preservation of derivation provenance when a value is progress-adjusted or estimated

Architecture note:

- This work should land in the existing Variant 3 local materialized store.
- If Variant 4 ever happens later, it should carry the same metadata model forward behind a sidecar boundary.

Reference docs:

- `docs/features/print_history/external-services-design-review-2026-04.md`
- `docs/features/print_history/variant3-metadata-schema-and-variant4-carry-forward.md`
- `docs/features/print_history/metadata-implementation-roadmap.md`
```

### Update Draft For `#248`

Draft:

```md
Design review follow-up:

OpenSpoolman remains useful as a reference for spool-state modeling, but not as a replacement for Bambuddy-backed print history.

Current conclusion:

- Keep Bambuddy as the archive authority.
- Use the current Variant 3 local store for print-history query/provenance work.
- Borrow spool-linkage ideas rather than adopting OpenSpoolman as the history backend.

Most relevant takeaways from this issue:

- preserve per-print spool snapshots at print start and terminal state
- record spool attribution as structured rows instead of burying it only in hidden note payloads
- store the matching method used (`archive_uuid`, `tray_map_snapshot`, `color_fallback`, `manual_override`)
- keep spool-derived cost and material provenance distinct from Bambuddy-owned archive truth

This issue now aligns most closely to the planned `archive_spool_snapshots` work in the Variant 3 schema extension.

Reference docs:

- `docs/features/print_history/external-services-design-review-2026-04.md`
- `docs/features/print_history/variant3-metadata-schema-and-variant4-carry-forward.md`
- `docs/features/print_history/metadata-implementation-roadmap.md`
```

### Update Draft For `#793`

Draft:

```md
Design follow-up after the broader print-history review:

Issue `#793` is now a key justification for two metadata additions in Variant 3:

1. a durable per-archive event timeline
2. broader lineage/provenance rows beyond repair-only lineage

Why:

- mismatch review and repair workflows are much easier if we can inspect lifecycle events and relationship evidence directly
- content-hash grouping alone is not enough when the archived payload itself may be wrong
- review operators need structured evidence, not only final archive status and repaired notes

Current architecture decision:

- keep this inside the existing Variant 3 integration-owned store
- keep Bambuddy authoritative for archive-core mirrored fields
- add local-only lineage, timeline, and review metadata without turning the integration into a second archive authority

Reference docs:

- `docs/features/print_history/archive-mismatch-repair-design.md`
- `docs/features/print_history/variant3-metadata-schema-and-variant4-carry-forward.md`
- `docs/features/print_history/metadata-implementation-roadmap.md`
```

### Update Draft For `#426`, `#649`, And `#650`

Suggested use:

- post the same comment with minor wording changes, or
- use this as a body update in the most implementation-focused issue among them

Draft:

```md
Print-history design update:

Per-print power and energy cost are now explicitly part of the Variant 3 metadata plan, but they will be modeled as derived fields rather than archive-core truth.

Current decision:

- keep Bambuddy authoritative for archive-core data
- compute per-print energy and cost in the local Variant 3 store
- preserve derivation basis and confidence instead of treating estimated and actual values as interchangeable

Planned shape:

- `actual_energy_cost` and `actual_power_wh` when power monitoring data is available
- `estimated_energy_cost` and `estimated_power_wh` only as fallback-derived values
- detail hydration should expose basis / confidence for the computed values
- page rows may surface compact summaries only when the derived values are stable enough for filtering or display

This keeps power analytics aligned with the print-history roadmap without widening Layer 1 or overloading the archive row.

Reference docs:

- `docs/features/print_history/variant3-metadata-schema-and-variant4-carry-forward.md`
- `docs/features/print_history/metadata-implementation-roadmap.md`
- `docs/features/print_history/external-services-design-review-2026-04.md`
```

### Update Draft For `#110`, `#111`, `#112`, `#113`, And `#116`

Draft:

```md
Print-history analytics update:

The recent design review clarified that these analytics issues should be built on top of the existing Variant 3 integration/store path, not a separate reporting backend.

Important boundary decisions:

- new analytics should consume structured query outputs from the Variant 3 store
- we should not add UI-only or chart-only fields into Layer 1 just to simplify rendering
- estimated vs actual metrics must be distinguishable where relevant

This is especially important for:

- filament cost per print (`#116`)
- activity heatmap semantics (`#110`)
- hours per week / month (`#111`, `#112`)
- utilization rate (`#113`)

Planned support from the metadata roadmap:

- `archive_metric_summary` for derived cost / duration / weight values
- `archive_event_timeline` for lifecycle-aware analytics
- `archive_spool_snapshots` for explainable spool-derived cost and material attribution

Reference docs:

- `docs/features/print_history/metadata-implementation-roadmap.md`
- `docs/features/print_history/variant3-metadata-schema-and-variant4-carry-forward.md`
```

## Proposed New Issue Bodies

These are the new issue candidates that appear to be missing today.

### New Issue 1: Variant 3 Print History Metadata Schema Hardening

Suggested title:

`Print History: Variant 3 metadata schema hardening for derived metrics, provenance, and lineage`

Suggested body:

```md
## Summary

Extend the active Variant 3 `bambuddy` integration store with focused local-only tables for derived metrics, event history, spool provenance, artifact metadata, and broader lineage.

This is a schema-hardening issue, not a UI-first issue.

## Why

The current Variant 3 store already has the correct foundation (`archives`, filament rows, tags, photos, note payload rows, repair lineage, review state), but several roadmap items still depend on hidden payload blobs or ad hoc parsing.

The recent design review concluded that we should:

- keep Bambuddy as the archive authority
- keep Variant 3 as the current implementation target
- design Variant 4, if it ever happens, as a hosting-boundary promotion of the same metadata model rather than a different model

## Proposed additions

- `archive_metric_summary`
- `archive_event_timeline`
- `archive_spool_snapshots`
- `archive_artifact_metadata`
- `archive_lineage`

## Constraints

- do not widen Layer 1 with UI-only labels or card-specific wording
- do not turn the integration store into a second archive authority
- Bambuddy-owned fields remain mirrored and overwritten from Bambuddy on sync
- local-only and derived tables remain integration-owned

## Related issues

- `#197`
- `#198`
- `#235`
- `#248`
- `#793`

## Reference docs

- `docs/features/print_history/variant3-metadata-schema-and-variant4-carry-forward.md`
- `docs/features/print_history/metadata-implementation-roadmap.md`
- `docs/features/print_history/external-services-design-review-2026-04.md`
```

### New Issue 2: Print History Per-Archive Event Timeline

Suggested title:

`Print History: persist per-archive event timeline in Variant 3 store`

Suggested body:

```md
## Summary

Add a durable per-archive event timeline to the active Variant 3 print-history store.

## Goal

Capture lifecycle and local workflow events as first-class rows instead of inferring everything from the final archive state.

## Initial event types

- `print_started`
- `print_paused`
- `print_resumed`
- `print_finished`
- `print_failed`
- `print_stopped`
- `photo_captured`
- `enrichment_applied`
- `repair_applied`

## Why

- inspired by the Node-RED `#235` review
- useful for diagnostics and mismatch review (`#793`)
- enables future detail-popup timeline views without log scraping

## Constraints

- implement in the current Variant 3 integration/store path
- do not require Node-RED
- preserve source information for each event (`bambuddy_webhook`, `bambu_lab`, `ha_script`, etc.)

## Related issues

- `#235`
- `#793`

## Reference docs

- `docs/features/print_history/variant3-metadata-schema-and-variant4-carry-forward.md`
- `docs/features/print_history/metadata-implementation-roadmap.md`
```

### New Issue 3: Print-Start Artifact Metadata Extraction

Suggested title:

`Print History: capture print-start artifact metadata from 3MF when available`

Suggested body:

```md
## Summary

Capture file-derived print metadata at print start when `.3mf` or related artifacts are accessible.

## Goal

Persist a structured artifact metadata row that can hold:

- preview image reference
- estimated filament weight
- estimated cost if available
- material/profile names
- plate index / plate name
- project/model identifiers when recoverable

## Why

- strongest carry-forward idea from Node-RED issue `#235`
- improves resilience when runtime data is incomplete or delayed
- complements archive recovery and backfill flows

## Constraints

- values extracted from artifacts must be labeled as derived / estimated where appropriate
- do not overwrite Bambuddy-owned archive truth fields directly
- keep this inside the active Variant 3 integration/store model

## Related issues

- `#235`
- archive recovery/backfill work under `docs/features/print_history/`

## Reference docs

- `docs/features/print_history/variant3-metadata-schema-and-variant4-carry-forward.md`
- `docs/features/print_history/metadata-implementation-roadmap.md`
```

### New Issue 4: Structured Spool Snapshot Provenance

Suggested title:

`Print History: persist structured spool snapshots for per-print provenance`

Suggested body:

```md
## Summary

Persist structured per-print spool snapshots in the Variant 3 store.

## Goal

Record explainable spool attribution rows rather than relying only on hidden enrichment payloads.

## Initial fields

- snapshot phase (`start`, `terminal`, `recovered`, `manual_review`)
- tray key / AMS slot
- tray UUID / RFID UUID when present
- spool id / filament id when matched
- vendor / material / profile / color snapshot
- matching method (`archive_uuid`, `tray_map_snapshot`, `color_fallback`, `manual_override`)
- ambiguity code and attributable used weight when available

## Why

- incorporates the best lessons from `#248` and the broader OpenSpoolman / SpoolSync review
- makes cost attribution and provenance inspectable
- supports future compare/reprint/analytics work

## Constraints

- keep Bambuddy as archive authority
- keep implementation inside Variant 3 store first
- do not widen Layer 1 with spool-display-only strings

## Related issues

- `#248`
- Phase 2.8 in `advanced-features-design.md`

## Reference docs

- `docs/features/print_history/variant3-metadata-schema-and-variant4-carry-forward.md`
- `docs/features/print_history/metadata-implementation-roadmap.md`
```

## Recommended Order For Tracker Updates

1. Update `#197` / `#198` first so the metadata contract is the clear parent decision.
2. Update `#235`, `#248`, and `#793` next so the evidence issues point back to the chosen architecture.
3. Update `#426`, `#649`, `#650`, `#110`, `#111`, `#112`, `#113`, and `#116` so analytics issues reference the new Variant 3 data path.
4. Create the new implementation issues only after the metadata parent issues are updated.

## Final Note

If these updates are applied, the repo should have one coherent story:

- existing issues explain why the metadata direction changed
- new issues define the missing implementation slices
- Variant 3 remains the active execution target
- Variant 4 stays available as a future promotion path for the same model
```