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

## Phase B: Event Timeline Capture

### Objective

Persist lifecycle rows for each archive rather than relying only on final archive status.

### Event types to capture first

- `print_started`
- `print_paused`
- `print_resumed`
- `print_finished`
- `print_failed`
- `print_stopped`
- `enrichment_applied`
- `repair_applied`

### Data sources

- Bambuddy webhook events where they remain authoritative
- native `bambu_lab` triggers where equivalent semantics are verified
- integration services for enrichment and repair state

### Issue alignment

- `#235` for the event-ledger pattern
- `#793` because mismatch and repair review benefit from a durable event trail

### Exit criteria

- archive detail hydration can include timeline rows
- review flows can see the sequence of archive lifecycle events without re-parsing logs or notes

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
- `archive-enrichment.md`

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

The recommended order is:

1. Phase A: metadata tables and migrations
2. Phase B: event timeline capture
3. Phase D: spool snapshot provenance
4. Phase C: artifact extraction
5. Phase E: cost and energy joins
6. Phase G: lineage support
7. Phase F: expanded analytics and UI surfacing

This order keeps the repo from building UI-first features on top of temporary blobs.

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