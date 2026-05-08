# Candidate Discovery Strategy

> Status: Revised Phase 6 design update with shipped Phase 2 baseline noted.
> Scope: Archive-to-model candidate discovery, operator review, archive-initiated picker/search, and curated discovery guardrails.

## Purpose

Document how archive popup candidate discovery should broaden beyond the current
name-overlap fallback while preserving a review-first operator workflow.

This document separates three concerns:

- deterministic auto-linking signals that may justify high-confidence candidates
- heuristic ranking signals that should remain review-only
- later browse/search flows that should not be forced into the Phase 2 popup-only matcher

## Current Implementation Snapshot

Current shipped candidate refresh behavior is intentionally narrow:

- input is the archive `print_name`
- both archive name and local curated model titles are tokenized to lowercase alphanumeric words
- score is token overlap divided by the larger token set
- candidates below the minimum score threshold are discarded
- the caller may request a forced local summary refresh before scoring
- surviving candidates are stored as review rows with `match_method=name_similarity`

Current limitations:

- does not inspect uploaded source 3MF or any source-file hash
- does not use archive completion time or recent local catalog activity time
- does not yet use refreshed local summary data for anything beyond the current name-overlap baseline
- does not expose a picker/search UI when heuristic discovery misses

## Design Principles

1. Keep automatic acceptance limited to deterministic evidence.
2. Allow heuristic signals to improve ranking, but keep them review-only.
3. Preserve explainability by storing why a candidate was suggested.
4. Keep popup candidate refresh archive-scoped; do not overload it into a full catalog browser.
5. Add richer picker/search as a later operator tool rather than hiding it behind background heuristics.

## Candidate Signal Tiers

### Tier 1: Deterministic Signals

These may justify high-confidence candidates and, when unique, may eventually justify auto-accept.

- exact source hash or content hash match
- exact catalog-side file hash match when available
- exact persisted source-path identity when the same working/source artifact is known on both sides
- explicit upstream cross-system ID already stored in local linkage metadata

Recommended `match_method` values:

- `content_hash_exact`
- `file_hash_exact`
- `path_exact`
- `explicit_cross_id`

### Tier 2: Strong Heuristic Signals

These should improve ranking but remain operator-reviewed.

- normalized filename overlap between archive source artifact and catalog file/model name
- archive print name overlap with curated model title
- recent catalog upload or file-attach time near archive completion time
- existing accepted links between nearby plates or repeated prints of the same normalized source name
- optional creator/collection/tag overlap when archive-side provenance later becomes available

Recommended `match_method` values:

- `normalized_filename_overlap`
- `name_similarity`
- `time_proximity_plus_name`
- `linked_plate_family_neighbor`

### Tier 3: Operator Search / Browse Flows

These should not be treated as candidate discovery at all. They are explicit operator tools.

- manual URL paste
- archive popup search/picker against the catalog
- catalog browse view with filters and ranking
- model-to-archive review flow for backfill and reconciliation

## Proposed Phase Mapping

### Phase 2: Popup Linkage Baseline

Phase 2 is now the shipped popup-first linkage baseline.

Implemented baseline:

- pass `archive_name` explicitly as the current matching signal
- support `force_refresh_model_cache` so candidate refresh can pull newly created local catalog summaries into the cache before scoring
- keep candidate refresh review-only
- enrich popup rows with cached local catalog summary fields such as model name
- support manual link create, candidate accept/reject, and deactivate flows from the popup

This gives the archive popup a stable linking surface without yet expanding candidate heuristics beyond name overlap.

### Phase 6: Candidate Broadening, Archive Search, And Curated Browse

Current Phase 6 should introduce both richer candidate scoring and explicit search/picker surfaces instead of relying only on the current background matcher.

Recommended additions:

- optionally pass `archive_completed_at`, `archive_started_at`, and source-file hints when available
- add a recent-upload boost for models or files created near the archive completion time
- add normalized filename overlap when archive-side source file names are available
- store candidate rationale in `review_note` or structured annotations so the popup can show why a row appeared
- add later preview thumbnail support when the compact review layout can accommodate it safely
- archive popup action to search/browse the catalog
- sidecar endpoint for searchable model-library queries with pagination and filter support
- result ranking that can incorporate recent uploads, recent prints, and accepted-link history
- picker flow to create a reviewed manual link from a selected result
- taxonomy facet filters for `taxonomy_origin_class` and `taxonomy_change_axes`
- `colors_used` facet filters that start hex-first in the Phase 6 baseline

This phase is the right place for a true "find a model" operator experience.

Issue `#187` alignment for the current search/ranking slice:

- `reprint` and `custom_unique` are first-class model-catalog taxonomy facets
- `remix_or_tweak` is paired with explicit change-axis filtering (`color`, `model`, `other`)
- `favorite` and optional `rating` are model-level ranking/filter signals
- `Colors used` should be queryable through model-catalog metadata as hex in the Phase 6 baseline
- later phase: optional `filament_id` picker + parsed `.3mf` inference to link colors back to Spoolman filament records

### Phase 8: Reverse Model-To-Archive Matching

Phase 8 should add the opposite direction:

- start from a curated or Working model
- look for nearby or candidate print-history archives
- support linking an existing archive or creating a missing one

This is the right place for "go the other way" workflows.

## Recommended Request Inputs For Candidate Refresh

Archive candidate refresh should support a richer but still archive-scoped payload:

```yaml
entry_id: string?
archive_id: int
archive_name: string
archive_completed_at: datetime?
archive_started_at: datetime?
source_file_name: string?
source_hash: string?
allow_filename_fallback: bool = true
allow_time_proximity: bool = true
prefer_recent_uploads: bool = true
recent_upload_window_days: int = 14
force_refresh_model_cache: bool = false
max_candidates: int = 10
```

Not every field needs to exist in the shipped Phase 2 baseline, but the contract should leave room for them when current Phase 6 broadening begins.

## Ranking Guidance

Candidate ranking should be additive and explainable.

Recommended approach:

- deterministic matches sort above heuristic matches
- filename overlap and name overlap contribute separately
- recent-upload proximity acts as a boost, not as a standalone match signal
- no candidate should be suggested solely because it is recent unless another identity hint also overlaps

Example reasoning strings:

- `exact source hash match`
- `normalized filename overlap + upload within 3 days of print`
- `name overlap + recent upload + same creator`

## Non-Goals For The Shipped Phase 2 Baseline

- full-text catalog search in the popup
- large browse/filter UI inside the candidate refresh action
- automatic acceptance of time-based or name-based heuristic matches
- direct storage-layer joins outside the sidecar-owned authority

## Suggested Follow-On Work Items

- Phase 6 feature: broaden candidate discovery with filename overlap, deterministic identity signals, and time-proximity scoring
- Phase 6 feature: archive popup model picker/search backed by a searchable curated-catalog endpoint
- Phase 8 feature: reverse model-to-archive candidate review and backfill flow

## Related Documents

- [phase-6-search-ranking-and-discovery-design.md](phase-6-search-ranking-and-discovery-design.md)
- [integration/archive-model-link-ha-service-and-popup-contract.md](integration/archive-model-link-ha-service-and-popup-contract.md)