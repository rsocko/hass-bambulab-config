# GitHub Posting Batch 1 (2026-04)

## Purpose

This file is the smallest ready-to-post batch for the first wave of GitHub updates.

It keeps the detailed rationale in the other docs, but gives you exact text for:

- the first three existing-issue comments to post
- the first two new issues to create

Supporting detail remains in:

- [external-services-design-review-2026-04.md](external-services-design-review-2026-04.md)
- [variant3-metadata-schema-and-variant4-carry-forward.md](variant3-metadata-schema-and-variant4-carry-forward.md)
- [metadata-implementation-roadmap.md](metadata-implementation-roadmap.md)
- [issue-update-drafts-2026-04.md](issue-update-drafts-2026-04.md)
- [issue-posting-plan-2026-04.md](issue-posting-plan-2026-04.md)

## Post These Comments First

### Comment For `#197` / `#198`

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

### Comment For `#235`

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

### Comment For `#248`

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

## Create These Two Issues First

### New Issue 1

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

### New Issue 2

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

## Recommended Order

1. Post the `#197/#198` comment.
2. Post the `#235` comment.
3. Post the `#248` comment.
4. Create `Variant 3 metadata schema hardening`.
5. Create `Per-archive event timeline`.

That is the smallest batch that preserves the architecture decision, the Node-RED carry-forward ideas, the spool provenance direction, and the first two implementation anchors.