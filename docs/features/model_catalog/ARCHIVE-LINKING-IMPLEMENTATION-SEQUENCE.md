# Model Catalog: Archive Linking — Sequenced Implementation Plan

> Generated from the 26 open issues carrying the `Model Catalog: Archive Linking` label.
> Date: 2026-06-01

---

## Summary

The Archive Linking workstream connects **print history archives** (Bambuddy canonical records) to **model catalog entries** (local-authority models/Working Files). It spans discovery, matching, search, metadata sync, slicer-based archive creation, and historical backfill.

This plan sequences all open issues into implementation tiers based on:

1. Logical dependency ordering
2. Explicit `blocked-by` relationships already declared on issues
3. Shared infrastructure requirements
4. Stated milestone/phase assignments

---

## Tier 0 — Foundational Design Decisions

These are design-level issues that must be resolved first because they determine the shape of the linkage data model. They have no code dependencies but every downstream issue implicitly depends on their conclusions.

| # | Issue | Status | Description |
|---|-------|--------|-------------|
| 1 | [#1314](https://github.com/rsocko/hass-bambulab-config/issues/1314) | Todo | **Linking Model ↔ Archive: link to the ACTUAL .3mf file, not just the 'model' record** — Decide whether linkage targets the model record, the specific .3mf file, or both. |
| 2 | [#1375](https://github.com/rsocko/hass-bambulab-config/issues/1375) | Todo | **Maintain Archive ↔ Model linkage across Working Files → Catalog graduation** — Define linkage identity scheme that survives model lifecycle transitions. |

### Deliverables
- ADR or design note specifying the linkage target (model-level vs. file-level vs. dual)
- Schema guarantee for stable linkage IDs across graduation/demotion
- Update `archive_model_link` table schema if needed

### Rationale for ordering
Every matching engine, search endpoint, and UI component assumes a specific shape for linkage records. If linkage can target a file within a model (not just the model), candidate discovery logic, search indexing, and popup display all change.

---

## Tier 1 — Core Discovery & Matching Engine

Build on the existing `archive_linking.py` (Phase 3.3 Tasks 1–2 complete). Broaden and harden the candidate matching engine against the local model authority.

| # | Issue | Status | Phase | Description |
|---|-------|--------|-------|-------------|
| 3 | [#1114](https://github.com/rsocko/hass-bambulab-config/issues/1114) | **In Progress** | 6 | **Broaden model-catalog candidate discovery beyond name overlap** — Add richer signals (filename, source hash, time proximity) and persist rationale. |
| 4 | [#1118](https://github.com/rsocko/hass-bambulab-config/issues/1118) | **In Progress** | 6 | **Broaden archive candidate discovery and rationale** — Extend scoring with normalized filename overlap, identity hints, time-proximity boosts; keep heuristics review-only. |
| 5 | [#1142](https://github.com/rsocko/hass-bambulab-config/issues/1142) | Partial | 6 | **Archive-model search, related models, and navigation** — Finish Phase 3.3 Task 3 (Recommendation Engine), wire navigation services. Tasks 1–2 (linking engine + related-models algorithm) already complete. |

### Dependencies
- **Tier 0** conclusions feed the target shape of new linkage records
- Existing `ArchiveLinkingEngine` + `get_related_models()` in `archive_linking.py`
- Local model authority (Phase 3 cut-over #1160 — completed ✅)

### Implementation order within tier
1. #1114 → #1118 (nearly identical scope; #1114 is model-scoped, #1118 is archive-scoped; share scoring infrastructure)
2. #1142 Task 3 (builds on completed Task 1–2 and scoring from #1114/#1118)

---

## Tier 2 — Search & Similarity Infrastructure

Define the query model and implement the similarity/related-items endpoint that feeds both UI and API consumers.

| # | Issue | Status | Phase | Blocked By | Description |
|---|-------|--------|-------|------------|-------------|
| 6 | [#1094](https://github.com/rsocko/hass-bambulab-config/issues/1094) | Todo | 6 | #1093 | **Define search facets and query model** — Document searchable entities, facets, sorts across curated/working/archive-linked items. |
| 7 | [#1096](https://github.com/rsocko/hass-bambulab-config/issues/1096) | Todo | 6 | #1093 | **Similarity signals and related-items endpoint** — Implement shared-tag/collection/name-token/print-history similarity helpers. |
| 8 | [#1131](https://github.com/rsocko/hass-bambulab-config/issues/1131) | Todo | 6 | — | **Bulk Metadata Enrichment** — Batch 3MF parsing, color extraction, tag suggestion, review-first approval. Feeds better signals into discovery. Sub-issues: #1135, #1136. |

### Dependencies
- Tier 1 matching engine provides the scoring primitives reused by similarity
- #1093 (Search, Similarity, and Better Discovery umbrella) must unblock #1094 and #1096
- Bulk enrichment (#1131) can start in parallel with #1094/#1096 since it feeds data quality rather than depending on search

### Implementation order within tier
1. #1094 (design doc — unblocks endpoint contracts)
2. #1096 (implement endpoint per the #1094 design)
3. #1131 (parallel — improves data richness fed into #1096)

---

## Tier 3 — UI for Search & Discovery

Surface the discovery infrastructure in HA dashboards.

| # | Issue | Status | Phase | Blocked By | Description |
|---|-------|--------|-------|------------|-------------|
| 9 | [#1115](https://github.com/rsocko/hass-bambulab-config/issues/1115) | Todo | 6 | — | **Archive-initiated model picker and curated catalog search** — Searchable endpoint + archive popup action to find and link a model. |
| 10 | [#1097](https://github.com/rsocko/hass-bambulab-config/issues/1097) | Todo | 6 | #1093 | **HA UI — search and related panels** — Search view with facets/sorts, mixed results, related-items toggle panel. |

### Dependencies
- #1094 (facets/query model design) informs #1097 and #1115 UI contracts
- #1096 (similarity endpoint) feeds the "related" panel in #1097
- Archive-initiated picker (#1115) is an earlier, simpler UI than the full search (#1097)

### Implementation order within tier
1. #1115 (narrower scope — just model picker from archive popup)
2. #1097 (full search view — requires #1094 + #1096 endpoints live)

---

## Tier 4 — Cross-System Metadata Sync

Lightweight enhancements that leverage existing linkage records to sync display metadata.

| # | Issue | Status | Description |
|---|-------|--------|-------------|
| 11 | [#1473](https://github.com/rsocko/hass-bambulab-config/issues/1473) | Todo | **Sync Tags between Archive → Catalog** — One-way (or optional bidirectional) tag propagation for linked records. |
| 12 | [#1474](https://github.com/rsocko/hass-bambulab-config/issues/1474) | Todo | **Allow showing Archive Image as Preview image on Model** — Pull archive print photo into model card when no dedicated preview exists. |

### Dependencies
- Working linkage records (Tier 1 output) must exist
- Tag schema parity between Archive and Catalog tagging systems
- Photo/image proxy for archive images accessible from model detail view

### Implementation order within tier
1. #1474 (simpler — read-only image fallback)
2. #1473 (requires merge/sync strategy design; more impactful)

---

## Tier 5 — Slicer Integration: Push Model → Archive

A complete vertical slice enabling operators to take a source `.3mf` from the catalog and create a canonical Bambuddy archive via local slicing.

| # | Issue | Status | Parent | Description |
|---|-------|--------|--------|-------------|
| 13 | [#1342](https://github.com/rsocko/hass-bambulab-config/issues/1342) | Todo | — | **Push Model → Archive (recreating gcode)** — Parent/epic (0/5 sub-issues complete). |
| 14 | [#1182](https://github.com/rsocko/hass-bambulab-config/issues/1182) | Todo | #1342 | **Deploy local slicer worker + health/capability contract** — Config, diagnostics, `GET /api/slicer/providers`. |
| 15 | [#1183](https://github.com/rsocko/hass-bambulab-config/issues/1183) | Todo | #1342 | **Add slice-job persistence and sidecar API** — SQLite state machine, CRUD routes for slice jobs. |
| 16 | [#1184](https://github.com/rsocko/hass-bambulab-config/issues/1184) | Todo | #1342 | **Build validation layer + deterministic filament substitution** — Warnings, filament candidate lists from Filament Catalog/Spoolman. |
| 17 | [#1185](https://github.com/rsocko/hass-bambulab-config/issues/1185) | Todo | #1342 | **Commit sliced output to Bambuddy canonical archive with provenance** — Upload `.gcode.3mf`, attach source, persist linkage, idempotent retry. |
| 18 | [#1186](https://github.com/rsocko/hass-bambulab-config/issues/1186) | Todo | #1342 | **Model Catalog + HA UX flow for source 3MF archive creation** — End-to-end operator UX. |
| 19 | [#1454](https://github.com/rsocko/hass-bambulab-config/issues/1454) | Todo | #1449 | **[Slicer Sidecar] Sub 5 — Bambuddy archive commit + provenance + historical timestamp pass-through** — Post-slice commit flow with operator-provided timestamps. |

### Dependencies
- Tier 0 (#1314) — linkage target design needed for the archive commit linkage record
- Tier 1 matching engine — used for auto-discovery of newly created archives
- `orca-slicer-api` upstream worker (#1449 epic) — #1454 depends on
- `print-history-slicer-integration-design.md` and `print-history-slicer-implementation-plan.md` design docs (already committed)

### Implementation order within tier (strictly sequential)
1. **#1182** — Worker deployment + health contract (nothing else works without the worker)
2. **#1183** — Slice-job persistence + API (state machine drives all downstream flows)
3. **#1184** — Validation layer (validates before execution)
4. **#1454** — Bambuddy archive commit + provenance + historical timestamp pass-through _(absorbs #1185 — close #1185 as superseded)_
5. **#1186** — Full UX flow (ties it all together for the operator)

> **Decision:** #1454 and #1185 are merged into a single implementation item (#1454). The orca-slicer-api Sub 5 scope is the superset — it includes the basic commit flow from #1185 plus historical timestamp pass-through. Close #1185 with a superseding reference.

---

## Tier 6 — Reverse Flows & Historical Backfill

Enable working backward from models to find/create archive records, including historical recovery.

| # | Issue | Status | Phase | Description |
|---|-------|--------|-------|-------------|
| 20 | [#1116](https://github.com/rsocko/hass-bambulab-config/issues/1116) | Todo | 8 | **Add reverse model-to-archive candidate review and backfill flow** — Start from model, surface candidate archives, link/create/defer. |
| 21 | [#1483](https://github.com/rsocko/hass-bambulab-config/issues/1483) | Todo | — | **US-4: Add Historical Print Wizard** — Operator-driven "Add Historical Print" wizard from Catalog popup. Scan candidates, confirm timestamps, commit backfill. |
| 22 | [#1043](https://github.com/rsocko/hass-bambulab-config/issues/1043) | Todo | — | **Allow 'backfill' of print history via the Model Catalog UI** — Original ask; now largely superseded/refined by #1483. |

### Dependencies
- Tier 1 matching engine (reverse discovery needs the same scoring)
- Tier 5 archive commit (#1185) — backfill creates archives
- Tier 0 linkage design — backfilled records must use the stable scheme
- #1483 has a commit implementing the wizard (46ea57a) — may partially exist

### Implementation order within tier
1. #1116 (server-side candidate surfacing — review-heavy)
2. #1483 (full UX wizard building on #1116's backend)
3. #1043 (close as superseded by #1483 or merge remaining scope)

---

## Tier 7 — UI Polish

Final cross-cutting polish pass once all functional flows are in place.

| # | Issue | Status | Phase | Blocked By | Description |
|---|-------|--------|-------|------------|-------------|
| 23 | [#1111](https://github.com/rsocko/hass-bambulab-config/issues/1111) | Todo | 8 | #1108 | **UI polish pass (browse/queue/linkage)** — Consistent terminology, icons, empty/loading states, confirmation prompts, basic accessibility. |

### Dependencies
- All functional surfaces from Tiers 1–6 must be feature-complete
- Phase 8 umbrella (#1108) must unblock

---

## Dependency Graph (Simplified)

```
Tier 0: Design Decisions
  #1314 (linkage target) ──┐
  #1375 (graduation)    ──┤
                           ▼
Tier 1: Discovery Engine ──────────────────────────────┐
  #1114 ──► #1118 ──► #1142 Task 3                     │
                           │                            │
                           ▼                            │
Tier 2: Search/Similarity Infra                         │
  #1094 ──► #1096                                       │
  #1131 (parallel)                                      │
           │                                            │
           ▼                                            │
Tier 3: UI for Discovery                                │
  #1115 ──► #1097                                       │
                                                        │
Tier 4: Metadata Sync                                   │
  #1474 ──► #1473                                       │
                                                        │
Tier 5: Slicer (Push Model → Archive) ◄────────────────┘
  #1182 ──► #1183 ──► #1184 ──► #1185 ──► #1186
                                    │
                                    ▼
                                  #1454 (orca-slicer-api)
                                    │
                                    ▼
Tier 6: Reverse Flows / Backfill
  #1116 ──► #1483 ──► #1043 (close)
                           │
                           ▼
Tier 7: Polish
  #1111
```

---

## Parallel Work Opportunities

| Stream A (Discovery) | Stream B (Slicer) | Stream C (Metadata) |
|----------------------|-------------------|---------------------|
| Tier 0 (shared) | Tier 0 (shared) | — |
| Tier 1: #1114, #1118 | Tier 5: #1182, #1183 | Tier 4: #1474, #1473 |
| Tier 2: #1094, #1096, #1131 | Tier 5: #1184, #1185, #1186 | — |
| Tier 3: #1115, #1097 | Tier 5: #1454 | — |
| Tier 6: #1116, #1483 | — | — |
| Tier 7: #1111 | — | — |

## Execution Order (Discovery First)

> Per decision: complete Discovery (Tiers 1–3) before starting Slicer (Tier 5). Metadata Sync (Tier 4) proceeds opportunistically once linkage records exist.

| Phase | Tiers | Issues |
|-------|-------|--------|
| **Phase A** | Tier 0 | #1314, #1375 (ADR) |
| **Phase B** | Tiers 1–3 | #1114, #1118, #1142, #1094, #1096, #1131, #1115, #1097 |
| **Phase B′** (parallel) | Tier 4 | #1474, #1473 |
| **Phase C** | Tier 5 | #1182, #1183, #1184, #1454, #1186 |
| **Phase D** | Tier 6 | #1116, #1483 |
| **Phase E** | Tier 7 | #1111 |

**Key insight:** After Tier 0 design decisions are locked, Discovery is the critical path. Metadata Sync (Tier 4) can overlap with Phase B since it only needs linkage records, not search infrastructure. Slicer work (Tier 5) starts once Tiers 1–3 ship.

---

## Overlap / Deduplication Notes

| Issues        | Relationship                                                                      | Action                                                                      |
| ------------- | --------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| #1185 ↔ #1454 | #1454 is the refined/scoped version under the orca-slicer-api epic.               | **Close #1185** — implement under #1454.                                    |
| #1043 ↔ #1483 | #1483 is the redesigned version of #1043.                                         | **Close #1043** — superseded by #1483.                                      |
| #1114 ↔ #1118 | Heavily overlapping scope (model-scoped vs. archive-scoped candidate broadening). | Implement as single PR with two facets; keep both issues open for tracking. |

---

## Current Status Snapshot

| State | Issues |
|-------|--------|
| **In Progress** | #1114, #1118 |
| **Partially Done** | #1142 (Tasks 1–2 complete, Task 3 pending) |
| **Todo** | All others (21 issues) |
| **Blocked** | #1094, #1096, #1097 (by #1093); #1111 (by #1108) |

---

## Decisions (Resolved 2026-06-01)

| Decision | Resolution |
|----------|-----------|
| **Tier 0 format** | Draft a proposed ADR with trade-offs for user approval (not a full RFC). |
| **#1185 vs #1454** | **Merge**: implement once under #1454, close #1185 as superseded. The Tier 5 sequence becomes #1182 → #1183 → #1184 → #1454 → #1186. |
| **Parallel streams** | **Discovery first** — complete Tiers 1–3 before starting the slicer stream (Tier 5). Metadata sync (Tier 4) can proceed as soon as linkage records exist. |
| **#1043 disposition** | **Close as superseded** by #1483. No remaining unique scope. |

---

## Recommended Next Actions

1. **Draft ADR for Tier 0** (#1314, #1375) — short decision doc covering linkage-target shape and graduation-stable identity scheme.
2. **Complete #1114 and #1118** (already in progress) — finish the broadened discovery engine.
3. **Finish #1142 Task 3** — wire the recommendation engine now that Tasks 1–2 are proven.
4. **Close #1043** — superseded by #1483; add a closing comment referencing the wizard issue.
5. **After Tiers 1–3 ship** — begin Tier 5 slicer work starting with #1182 (worker deployment).
