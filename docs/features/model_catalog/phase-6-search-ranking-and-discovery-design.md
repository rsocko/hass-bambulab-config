# Phase 6 Search, Ranking, and Discovery Design

> **Status**: Authoritative Phase 6 design.
> **Last updated**: 2026-05-03
> **Scope**: Unified search, ranking, archive-initiated curated search, related-item discovery, and Home Assistant operator surfaces for the post-Manyfold sidecar-owned catalog.

## Purpose

Define the current Phase 6 design baseline for search, ranking, and discovery after the authority pivot to a sidecar-owned catalog.

This document is the implementation-facing source of truth for:

- unified search/query behavior across sidecar-owned catalog surfaces
- ranking and facet semantics used by browse and backlog views
- archive-initiated picker/search from print-history popup flows
- related-model and related-item scoring behavior
- Phase 6 HA UI search and related-panel expectations

This document consolidates the still-valid Phase 6 intent from issues `#1060`, `#1062`, `#1093`, `#1094`, `#1095`, `#1096`, `#1097`, `#1115`, `#1118`, `#1114`, and `#1142`.

## Phase 6 Scope

Phase 6 owns the discovery layer that sits on top of the current local authority and archive-linkage baseline.

In scope:

- searchable curated-model records in the sidecar-owned catalog
- archive-linked navigation from print-history surfaces into catalog detail/search
- archive-scoped candidate broadening and rationale persistence
- archive-derived ranking signals used for browse, backlog, and relevance
- related-model and related-item suggestions derived from local authority data
- HA search view and optional related panels using sidecar APIs

Out of scope:

- project-aware navigation or archive -> model -> project contracts
- project CRUD or broader project browse surfaces
- replacing the intake queue, Working board, or publish workflow designs
- full-text search over arbitrary file contents or raw 3MF internals in the first Phase 6 slice
- external-source ingestion connectors beyond what is needed for stored provenance fields

Project-aware navigation is deferred to the current Phase 9 track.

## Baseline Decisions

1. Search and ranking operate against sidecar-owned authority, not Manyfold-backed runtime assumptions.
2. Archive popup candidate refresh remains archive-scoped and review-first.
3. Explicit operator search and picker flows are separate from background candidate discovery.
4. Deterministic candidate matches may rank above heuristic matches, but heuristic matches remain review-only unless a later design says otherwise.
5. Ranking signals from archives are valid inputs for browse and backlog ordering, but they do not override explicit operator fields such as queue priority.
6. Related-item behavior must stay explainable. Responses should include a concise rationale summary rather than opaque similarity scores alone.

## Entity Surfaces

Phase 6 search spans these sidecar-owned surfaces:

### Curated Models

Primary searchable surface.

Searchable fields:

- title and normalized title tokens
- description summary tokens
- creator names
- collection names
- tags
- taxonomy fields
- sidecar custom fields used for ranking, queue, favorites, and ratings
- archive-link summary signals such as linked archive count and last printed timestamp

### Archive-Linked Model Results

This is not a separate authority. It is a curated-model result projection enriched with archive facts.

Available enrichments:

- linked archive count
- last printed timestamp
- recent, frequent, and common ranking projections
- success-rate summary when available
- accepted link state

### Working Groups

Working groups are eligible for later unified discovery, but they are not required for the first shipped Phase 6 archive-initiated picker/search slice.

Rule:

- archive popup picker/search should default to curated models only
- broader unified search may add Working-group results when the UI clearly distinguishes result types

### Explicit Exclusions For Initial Phase 6

- project entities
- raw archive records as primary search results
- printer queue items as search entities
- raw assets/files as first-class search results

## Query Model

Phase 6 uses one normalized query model for browse, search, archive picker, and related-panel fetches.

### Common Query Inputs

```yaml
query: string?
entity_types: [curated_model, working_group]?
offset: int = 0
limit: int = 25
sort: relevance | recent | frequent | common | favorites | rating | linked_archive_count | last_printed_at | queue_priority
direction: desc | asc
include_facets: bool = false
include_related_preview: bool = false
context: browse | archive_picker | related_panel | backlog | popup_search
```

### Facets

Initial Phase 6 facets:

- `tags`
- `collections`
- `creators`
- `taxonomy_origin_class`
- `taxonomy_change_axes`
- `colors_used`
- `model_favorite`
- `model_rating`
- `to_print_status`
- `has_linked_archives`
- `linked_archive_count_bucket`
- `recent_print_window`

Optional later facets:

- success-rate bucket
- working stage
- file type / asset role

### Sort Modes

Required sort modes:

- `relevance`
- `recent`
- `frequent`
- `common`
- `favorites`
- `rating`
- `linked_archive_count`
- `last_printed_at`
- `queue_priority`

Interpretation:

- `relevance` is context-aware and may combine text match with ranking boosts
- `recent`, `frequent`, and `common` use archive-derived ranking signals
- `favorites` and `rating` are operator-controlled catalog signals
- `queue_priority` sorts by explicit backlog priority first and falls back to rank only when priorities tie

## Ranking Signals

Phase 6 promotes the validated archive-derived ranking baseline into the active design contract.

### Required Stored Or Computed Signals

- `last_printed_at`
- `print_count`
- `failed_count`
- `success_rate`
- `linked_archive_count`
- `recent_score`
- `frequent_score`
- `common_score`

### Signal Semantics

- `recent_score`: how recently the model was printed within the configured lookback window
- `frequent_score`: total successful-print count for the linked model
- `common_score`: recency-weighted frequency score for everyday rediscovery
- `success_rate`: quality indicator, not the primary browse rank
- `linked_archive_count`: coarse popularity and confidence signal

### Queue And Browse Interaction

Queue/backlog state remains a separate operator signal.

- `to_print_status` and `to_print_priority` stay sidecar custom fields
- archive-derived ranking can influence backlog sort defaults
- explicit queue priority wins when a backlog view is explicitly sorted by queue semantics

## Archive Candidate Discovery

Archive candidate discovery stays distinct from explicit search.

### Candidate Refresh Inputs

Archive-scoped candidate broadening may use:

- `archive_name`
- `archive_completed_at`
- `archive_started_at`
- `source_file_name`
- `source_hash`
- deterministic identity hints already persisted in sidecar linkage metadata

### Candidate Signal Tiers

#### Deterministic

- content-hash exact
- file-hash exact
- explicit cross-system identity
- exact persisted path identity where supported

#### Heuristic

- normalized filename overlap
- archive-name token overlap
- time-proximity boost when another identity hint overlaps
- linked-plate or repeated-source neighbor signals

### Candidate Rationale

Candidate rows must persist rationale in a form suitable for popup display.

Minimum rationale payload:

```json
{
  "summary": "normalized filename overlap + upload within 3 days of print",
  "signals": [
    {"type": "normalized_filename_overlap", "strength": "strong"},
    {"type": "time_proximity", "days": 3}
  ]
}
```

### Candidate Guardrails

- heuristic matches remain review-only
- time proximity is a boost, not a standalone match
- deterministic matches sort above heuristic matches
- candidate refresh should not degrade into a full catalog browser

## Archive-Initiated Picker And Curated Search

This is the operator escape hatch when candidate refresh is not sufficient.

### Entry Points

- archive popup action: `Search catalog`
- archive popup fallback after empty or weak candidate refresh
- archive detail shortcut to open curated picker with archive context preloaded

### Behavior

- default result type: curated models only
- search can use archive context as a ranking boost, not as a hidden filter
- selecting a result creates a reviewed archive-to-model link through the same linkage workflow used by manual accept/create actions
- manual URL linking remains available as fallback

### Archive Context Boosts

Allowed boosts:

- archive-name token overlap
- filename overlap
- recent accepted-link neighbors
- archive-derived popularity or recency signals

Not allowed:

- silently restricting the search space to current candidate rows only
- auto-accepting a selected result without the normal reviewed link contract

## Related Models And Related Items

Phase 6 related-item behavior is local-authority and explainable.

### Minimum Related-Model Signals

- shared collections
- shared creators
- shared tags
- normalized name-token overlap
- archive-derived co-interest or related rediscovery signals when available

### Optional Later Signals

- shared colors_used taxonomy
- shared queue/backlog affinity
- shared external provenance source

### Related Response Shape

```json
{
  "base_entity": {"entity_type": "curated_model", "model_ref": "gridfinity-bin"},
  "related": [
    {
      "entity_type": "curated_model",
      "model_ref": "gridfinity-drawer",
      "score": 0.72,
      "reasons": ["same collection", "2 shared tags", "recently printed"],
      "preview_url": "/api/models/.../preview"
    }
  ]
}
```

Rules:

- exclude the base entity
- sort by score descending
- return explanation strings or structured reasons
- allow per-context limits and minimum-score thresholds

## API Contracts

### Unified Search

Recommended endpoint:

- `GET /api/search`

Required behavior:

- accepts entity-type filters
- supports facets, pagination, and sort modes
- returns typed results with enough fields for HA list cards and popup pickers
- returns facet summaries when requested

### Curated Model Search Alias

Archive picker/search may use either:

- `GET /api/search?entity_types=curated_model`

or a narrower alias:

- `GET /api/models/search`

Rule:

- both contracts must reflect the same query model if both are kept
- the narrow model-search alias may be used for simpler HA integrations, but the broader query model is authoritative

### Related Items

Recommended endpoint:

- `GET /api/models/{model_ref}/related`

Possible later expansion:

- `GET /api/related?entity_type=curated_model&id=...`

### Archive Navigation

Required support:

- archive -> model lookup for accepted links
- archive popup open action for picker/search
- consistent reviewed-link creation after result selection

## Home Assistant UI Expectations

### Search View

The Phase 6 HA search surface should support:

- free-text search
- visible facets and sort controls
- typed results when more than one entity surface is enabled
- result cards that surface preview, title, creator/collection summary, ranking context, and queue/backlog context when relevant

### Related Panels

Optional but supported:

- model detail related-models panel
- archive popup related or suggested-models panel
- browse-card sidebar or inline related strip

### Archive Picker Popup

Required behaviors:

- show current accepted link if present
- show candidate refresh results and rationale separately from explicit search results
- allow switching into curated search without losing archive context
- show whether selection will create a reviewed manual link or accept a candidate

## Caching And Invalidation

Phase 6 search and related endpoints participate in the existing list/search/detail cache plan.

Invalidate search or related caches on:

- curated model metadata writes affecting list/search facets
- ranking refresh completion
- queue/backlog field changes
- archive-link accept/reject/deactivate actions that change archive-linked projections
- preview or asset changes that alter result-card projections

## Validation Gates

Phase 6 search/discovery design is implementation-ready when all of the following are true:

1. The query model is stable enough for both `GET /api/search` and archive picker/search reuse.
2. Candidate broadening and explicit search are documented as separate operator flows.
3. Archive-derived ranking semantics are explicit enough to avoid reopening issue `#1060` during implementation.
4. Related-item scoring and response rationale are concrete enough for endpoint and UI tests.
5. Project-aware navigation remains explicitly excluded from this phase.

## Issue Mapping

### Search And Ranking Umbrella

- `#1093` — umbrella for Phase 6 search, similarity, and better discovery
- `#1094` — query model, facets, and sort definitions
- `#1095` — unified search endpoint contract
- `#1096` — similarity signals and related-items endpoint
- `#1097` — HA search view and related panels

### Archive Discovery And Navigation

- `#1114` — broaden model-catalog candidate discovery beyond name overlap
- `#1115` — archive-initiated model picker and catalog search
- `#1118` — archive candidate discovery and rationale
- `#1142` — archive-model search, related models, and navigation

### Ranking Validation And Browse Context

- `#1060` — validate archive-derived ranking signals availability
- `#1062` — queue, ranking, and curated browse context consumed by this query model

## Related Documents

- [post-manyfold-transition-plan-2026-04.md](post-manyfold-transition-plan-2026-04.md)
- [phase-delivery-and-validation.md](phase-delivery-and-validation.md)
- [candidate-discovery-strategy.md](candidate-discovery-strategy.md)
- [integration/archive-model-link-ha-service-and-popup-contract.md](integration/archive-model-link-ha-service-and-popup-contract.md)
- [print-queue-assessment.md](print-queue-assessment.md)
- [integration/spike-1060-archive-ranking-signals-validation.md](integration/spike-1060-archive-ranking-signals-validation.md)