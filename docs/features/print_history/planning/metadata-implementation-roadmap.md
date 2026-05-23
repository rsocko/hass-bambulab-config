# Print History Metadata Implementation Roadmap

## Purpose

This roadmap converts the external-services review and the Variant 3 schema plan into a concrete implementation order tied to the existing print-history direction.

The intent is:

- keep work inside the active Variant 3 architecture
- preserve portability to a future Variant 4 if that boundary is ever needed
- tie new work to existing issues and existing phase docs where possible
- avoid creating a second roadmap that competes with `advanced-features-design.md`

## Guiding Rules

- implement new metadata in the existing Variant 3 store first
- do not widen Layer 1 for UI-only labels or one-off dashboard conveniences
- prefer integration services and detail hydration over card-local parsing for new provenance features
- treat Variant 4 as a later execution boundary, not a reason to delay Variant 3 schema work

## Current Status Snapshot

This roadmap is no longer entirely prospective.

Already shipped in the active Variant 3 store and service layer:

- `archive_event_timeline`
- `archive_review_state`
- `archive_media_review_state`
- `archive_repair_lineage`
- integration service paths that mutate local review, media-review, repair-lineage, and event-timeline state

Already shipped as adjacent local-store inputs that partially reduce later schema pressure:

- `archive_enrichment_provenance_rows` for structured enrichment evidence and spool/filament matching provenance
- `archive_storage_metrics` for archive-scoped file inventory, cached size breakdowns, and artifact presence diagnostics
- compact duplicate metadata in the base archive projection: `duplicate_count`, `duplicate_sequence`, and `original_archive_id`

Still pending from the broader roadmap:

- `archive_metric_summary`
- `archive_spool_snapshots`
- `archive_artifact_metadata`
- a broader `archive_lineage` model beyond the currently shipped repair-lineage and compact duplicate slice

Important boundary:

- `archive_storage_metrics` is not a replacement for semantic `archive_artifact_metadata`; it covers file inventory and size diagnostics, not parsed `.3mf`-derived project, plate, or estimate fields
- compact duplicate metadata and `archive_repair_lineage` reduce immediate pressure for a generalized `archive_lineage`, but they do not eliminate the need if compare, reprint, or mismatch workflows later need first-class broader relationships

## Issue #867 Mapping

Issue `#867` should now be read as a narrowed metadata-hardening tracker rather than a request to build every listed table from scratch.

| Proposed item from `#867` | Current repo state | Recommended disposition | Notes |
|---|---|---|---|
| `archive_event_timeline` | Shipped | Keep issue linkage, but do not reopen as missing schema work | Remaining work is event coverage and popup/UI completion, not base-table creation |
| `archive_metric_summary` | Not shipped | Keep active | Build only with explicit consumers for estimated-vs-actual or energy-cost workflows |
| `archive_spool_snapshots` | Not shipped, but partially covered by hidden enrichment payload and `archive_enrichment_provenance_rows` | Keep active | Best next metadata addition when spool provenance needs to become queryable rather than popup-only |
| `archive_artifact_metadata` | Not shipped, but partially adjacent to `archive_storage_metrics` | Keep active | Must stay focused on parsed semantic artifact fields rather than duplicating file inventory |
| `archive_lineage` | Not shipped | Defer until compare/reprint/mismatch workflows need it | Compact duplicate metadata plus `archive_repair_lineage` are sufficient for the currently shipped browser and repair slices |

For issue maintenance, the main remaining scope is therefore:

- `archive_metric_summary`
- `archive_spool_snapshots`
- semantic `archive_artifact_metadata`
- generalized `archive_lineage`

## Workstream Summary

| Workstream | Goal | Primary motivation | Existing issue alignment |
|---|---|---|---|
| A. Metadata contract hardening | make derived and provenance fields first-class | issues `#197`, `#198`, review follow-up | `#197`, `#198`, `#235` |
| B. Event timeline capture | preserve lifecycle history per archive | Node-RED review, repair diagnostics | `#235`, `#793` |
| C. Artifact extraction | capture `.3mf`-derived estimates and preview metadata | Node-RED review, recovery resilience | `#235`, recovery docs |
| D. Spool snapshot provenance | make spool attribution explainable and queryable | OpenSpoolman, SpoolSync, existing enrichment | Phase 2.8, `#248` |
| E. Cost and energy joins | separate filament and energy cost truthfully | Node-RED, power-monitoring roadmap | Phase 2.6, `#426`, `#649`, `#650` |
| F. Analytics and UI surfacing | expose new metadata without Layer 1 bloat | 3D Print Log and existing heatmap/chart issues | `#110`, `#111`, `#112`, `#113`, `#116` |
| G. Compare and lineage readiness | support duplicate/reprint/repair workflows | O.D.I.N., Bambuddy compare APIs | Phase 2.2, 2.3, `#793` |

Issue `#737` is the first active slice inside Workstream G: compact duplicate metadata now rides with the Variant 3 archive projection so the browser can filter and label duplicate sets without storing the full related-members payload in Layer 1.

## Phase A: Metadata Contract Hardening

### Objective

Create the base tables and migration path described in [variant3-metadata-schema-and-variant4-carry-forward.md](variant3-metadata-schema-and-variant4-carry-forward.md).

### Why first

Without this step, later features will continue to hide important state in:

- note payload blobs
- card-local parsing
- ad hoc helper logic

### Deliverables

- add `archive_metric_summary`
- add `archive_event_timeline`
- add `archive_spool_snapshots`
- add `archive_artifact_metadata`
- add `archive_lineage`
- add migration and backfill logic in the current Variant 3 store

### Current implementation status

- `archive_event_timeline` is already shipped
- `archive_review_state`, `archive_media_review_state`, and `archive_repair_lineage` are already shipped as adjacent local-store primitives
- `archive_enrichment_provenance_rows` already carry structured spool/filament evidence that can seed a future `archive_spool_snapshots` table
- `archive_storage_metrics` already carry archive-scoped artifact inventory and size diagnostics, but not the semantic `.3mf` extraction fields proposed for `archive_artifact_metadata`
- the remaining work in Phase A is the broader metric, artifact, spool-snapshot, and generalized-lineage schema rather than the initial migration foundation itself

### Repo touchpoints

- `homeassistant/custom_components/bambuddy/print_history/store.py`
- `homeassistant/custom_components/bambuddy/print_history/query.py`
- `homeassistant/custom_components/bambuddy/manager.py`

### Issue alignment

- `#197` and `#198` should remain the main metadata-definition anchors
- `#235` should be referenced as the event-ledger and derived-metrics source of ideas, not as a platform dependency

### Exit criteria

- new tables exist behind migrations
- existing browser behavior still runs from the current page/detail contracts
- no new Layer 1 UI-only fields were introduced

For current planning, treat the remaining Phase A exit criteria as centered on `archive_metric_summary`, `archive_spool_snapshots`, `archive_artifact_metadata`, and a broader `archive_lineage` table.

## Phase B: Event Timeline Capture

### Objective

Persist intermediate event rows for each archive while leaving start and terminal timestamps sourced from the archive record itself.

### Event types to capture first

- `print_paused`
- `print_resumed`
- `photo_captured`
- `enrichment_applied`
- `repair_applied`

### Data sources

- native `bambu_lab` signals where equivalent semantics are verified
- integration services for photo capture, enrichment, and repair state

### Issue alignment

- `#235` for the event-ledger pattern
- `#793` because mismatch and repair review benefit from a durable event trail
- `#868` because the archive popup timeline should render durable intermediate events from detail hydration rather than a widened page payload

### Implementation notes for the active slice

- add an integration-owned local append path for HA workflow events such as `photo_captured`, `enrichment_applied`, and `repair_applied`
- treat archive `started_at`, `completed_at`, and final archive status as the canonical timeline anchors instead of duplicating them into the local ledger
- keep timeline rows local to Variant 3 for now instead of persisting them back to Bambuddy through archive-core fields
- expose a compact normalized `event_timeline` DTO through archive detail hydration only

### Exit criteria

- archive detail hydration can include timeline rows
- review flows can see the sequence of archive lifecycle events without re-parsing logs or notes
- popup timeline UI can render intermediate event dots from persisted rows without expanding the Layer 1 browser payload

### Current implementation status

The core storage and mutation slice for Phase B is already present:

- `archive_event_timeline` exists in the Variant 3 store
- local append paths are exposed through the integration service layer
- popup detail hydration already has the structural path needed to consume durable timeline rows

The remaining work is to expand event capture coverage and complete the final popup timeline presentation against the persisted rows.

For issue `#867`, treat Phase B as substantially implemented infrastructure rather than as one of the major remaining schema gaps.

## Phase C: Artifact Extraction At Print Start

### Objective

Capture file-derived metadata at print start when a `.3mf` or related artifact is accessible.

### Fields to extract first

- preview image reference
- estimated filament weight
- estimated cost if available
- material/profile names
- plate index or plate label
- project or model identifiers when recoverable

### Why this matters

- it directly adopts the highest-value part of the Node-RED flow from `#235`
- it reduces dependence on late or partial runtime data
- it improves repair and backfill resilience

### Existing doc alignment

- archive recovery and historical backfill docs under `docs/features/print_history/`
- `../reference/archive-enrichment-current.md`

### Current implementation status

- the repo already stores archive-scoped file inventory and artifact presence diagnostics in `archive_storage_metrics`
- that local table is useful for storage analytics and popup diagnostics, but it does not yet hold parsed `plate_name`, `estimated_weight_g`, `material_names_json`, `project_name`, or `designer_name`

That means Phase C remains genuinely open, but only for semantic artifact extraction rather than generic artifact presence caching.

### Exit criteria

- extracted values land in `archive_artifact_metadata`
- estimated values are labeled as estimated, not merged into Bambuddy-owned truth fields

## Phase D: Spool Snapshot Provenance

### Objective

Make spool attribution a first-class searchable model rather than a hidden enrichment side effect.

### First implementation slice

- write a `start` snapshot using archive UUIDs and tray-map data
- write a `terminal` snapshot if final attribution differs or becomes more certain
- record `matching_method` and ambiguity state explicitly

### Why this matters

- aligns to the strengths observed in OpenSpoolman and SpoolSync
- supports future compare, cost, and analytics features
- reduces repeated note-payload parsing for spool questions

### Existing roadmap alignment

- Phase 2.8 spool usage provenance in `advanced-features-design.md`
- issue `#248`

### Current implementation status

- hidden `+>` enrichment payload rows already preserve compact per-print spool and filament attribution
- `archive_enrichment_provenance_rows` already preserve structured evidence and matching-method hints for current enrichment results

That existing substrate should be treated as the migration/backfill source for any future `archive_spool_snapshots` table rather than discarded or re-derived from scratch.

### Exit criteria

- archive detail can display structured spool provenance
- cost and usage features can consume spool attribution rows directly

## Phase E: Cost And Energy Joins

### Objective

Separate filament-cost and energy-cost computation into explicit derived fields.

### First implementation slice

- compute `actual_filament_cost` from spool snapshot plus measured/recorded usage
- compute `actual_energy_cost` when power-monitoring data exists
- preserve basis and confidence for every computed value

### Existing issue alignment

- Phase 2.6 in `advanced-features-design.md`
- `#426` from power-monitoring future enhancements
- `#649` and `#650` from the analytics planning notes already referenced elsewhere in the repo

### Important boundary

- these values belong in `archive_metric_summary`
- they should not overwrite Bambuddy-owned `cost` blindly
- page rows may show compact summaries, but the calculation basis should remain inspectable in detail hydration

### Current implementation status

- the repo already PATCHes Bambuddy native `cost` during enrichment when it can justify a total from real filament usage rows
- explicit metric provenance, estimated-versus-actual semantics, and energy-specific truth are not yet modeled as first-class local fields

That means Phase E should create a narrow derived summary contract instead of reworking the existing enrichment write path wholesale.

### Exit criteria

- the system can distinguish archive-native cost from repo-derived cost
- per-print power and cost views can be built without scraping unrelated dashboards

## Phase F: Analytics And UI Surfacing

### Objective

Expose the new metadata in the existing browser, popup, and activity surfaces without creating Layer 1 bloat.

### First implementation slice

- show estimated vs actual badges or facts in detail popup
- add event timeline section to archive detail
- add spool provenance summary chips or facts to detail view
- extend activity or summary analytics only from integration query surfaces, not card-local raw parsing

### Existing issue alignment

- `#110` activity heatmap
- `#111` hours per week
- `#112` hours per month
- `#113` utilization rate
- `#116` filament cost per print

### Design constraint

- if a field is only useful for one card, keep it in detail hydration or a dedicated query path
- do not add display-only helper strings to mirrored archive storage just to simplify frontend rendering

### Exit criteria

## Phase G: Compare And Lineage Readiness

### Objective

Support duplicate, reprint, and repair workflows without forcing those heavier relationships into the base Layer 1 archive cache.

### Current shipped slice

- duplicate browser filtering and compact duplicate chips/summary are now shipped for issue `#737`
- Layer 1 stores only `duplicate_count`, `duplicate_sequence`, and `original_archive_id`
- Layer 2 owns duplicate filter semantics and role classification
- Layer 3 owns card and popup wording

Important implication for `#867`:

- do not build `archive_lineage` just to support the already shipped duplicate browser slice
- generalized lineage should wait until compare, reprint, or mismatch workflows need relationships broader than the compact duplicate projection and `archive_repair_lineage`

### Deferred follow-on slice

- related duplicate member lookup
- compare/deep-link actions from the popup
- suspicious same-hash review flows
- richer lineage tables when repair and compare workflows need more than the compact duplicate summary

- analytics consume structured query outputs
- no new giant payload blobs are introduced into entity state

## Phase G: Compare, Reprint, And Lineage Readiness

### Objective

Prepare the local store for compare-on-failure, duplicate intelligence, reprint lineage, and mismatch review.

### First implementation slice

- populate `archive_lineage` using content-hash and project evidence where reliable
- support links such as `duplicate_of`, `reprint_of`, `compare_candidate`, and `mismatch_target`
- keep `archive_repair_lineage` focused on repair provenance, not all relationships

### Existing roadmap alignment

- Phase 2.2 compare on failure
- Phase 2.3 duplicate and reprint intelligence
- Phase 2.10 repair diagnostics
- Phase 2.12 mismatch detection and replacement
- `#793`

### Exit criteria

- archive detail can expose related archives cleanly
- compare and reprint features have structured lineage rows to consume

## Preferred Delivery Order

For the still-missing parts of issue `#867`, the recommended order is:

1. Phase D: spool snapshot provenance
2. Phase C: semantic artifact extraction
3. Phase E: metric summary and energy joins
4. Phase G: broader lineage support
5. Phase F: expanded analytics and UI surfacing

This order keeps the repo from building UI-first features on top of temporary blobs while acknowledging that the event-timeline and review/repair primitives already landed.

## Variant 3 Versus Variant 4 Delivery Guidance

### What should happen now in Variant 3

- schema changes
- migration logic
- capture logic
- detail hydration expansion
- small summary fields for page rows where broadly useful

### What should wait unless Variant 4 is actually chosen

- a new standalone browser API unrelated to the integration contract
- separate data semantics for sidecar-only queries
- duplicate implementations of the same provenance model in HA and a sidecar

### Carry-forward rule

If Variant 4 happens later, it should adopt this roadmap by moving the same workstreams behind a sidecar boundary. It should not restart them with a different schema vocabulary.

## Decision Summary

The implementation plan should stay on the current rails:

- Variant 3 remains the place to build the next metadata layer
- Variant 4 remains a future hosting option for the same model
- `advanced-features-design.md` remains the feature roadmap
- this document adds the storage and rollout order needed to implement those features cleanly

That gives the repo one print-history architecture, one metadata model, and one migration path.