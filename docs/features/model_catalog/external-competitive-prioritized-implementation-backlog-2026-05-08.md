# Prioritized Implementation Backlog From Competitive Reviews

Date: 2026-05-08

Inputs consolidated:
- [docs/features/model_catalog/external-competitive-review-mmp-orynt-2026-05-08.md](docs/features/model_catalog/external-competitive-review-mmp-orynt-2026-05-08.md)
- [docs/features/model_catalog/external-competitive-review-orynt-alternatives-2026-05-08.md](docs/features/model_catalog/external-competitive-review-orynt-alternatives-2026-05-08.md)

Alignment anchors used:
- [docs/features/model_catalog/phase-6-search-ranking-and-discovery-design.md](docs/features/model_catalog/phase-6-search-ranking-and-discovery-design.md)
- [docs/features/model_catalog/PHASE-5-EXECUTION-SEQUENCE.md](docs/features/model_catalog/PHASE-5-EXECUTION-SEQUENCE.md)
- [docs/features/model_catalog/phase-5-end-state-ui-and-handoff-design.md](docs/features/model_catalog/phase-5-end-state-ui-and-handoff-design.md)
- [docs/features/model_catalog/phase-3.1-3.3-roadmap.md](docs/features/model_catalog/phase-3.1-3.3-roadmap.md)

---

## Goal
Turn competitive-analysis insights into a delivery-ready backlog mapped to current model-catalog phases, with clear dependencies and acceptance criteria.

## Scoring
- Value: 1-5
- Complexity: 1-5
- Confidence: High / Medium / Low

---

## Priority Queue (Cross-Phase)

| Priority | Initiative | Value | Complexity | Confidence | Primary Phase Mapping |
|---|---|---:|---:|---|---|
| P0 | Source-rule ingestion profiles + explainability | 5 | 3 | High | Phase 5 + Phase 9 intake/project integrations |
| P0 | Typed query language + saved searches | 5 | 3 | High | Phase 6 search/discovery |
| P0 | Taxonomy lineage visibility (system/inherited/user) | 4 | 2 | High | Phase 6 + existing detail/browse UI |
| P1 | Discovery diagnostics panel (parse/fallback/rationale) | 4 | 2 | High | Phase 6 + Phase 3 viewer/detail surfaces |
| P1 | Model relationship primitives (multipart/remix/variant/group) | 4 | 3 | High | Phase 6, prepares later project-aware flows |
| P1 | Duplicate + inefficiency detection dashboard | 4 | 3 | High | Phase 6 troubleshoot/discovery |
| P2 | Multi-model compare/assembly viewer mode | 4 | 4 | Medium | Phase 3 viewer enhancements + Phase 6 related/discovery |
| P2 | Plugin-style extension points (viewer/enrichment adapters) | 4 | 5 | Medium | Post-Phase 6 architecture hardening |
| P3 | Creator package import profile | 3 | 4 | Low-Medium | Later Phase 9+ ingestion expansion |

---

## Execution Plan (Sprint-Ready)

### EPIC A: Source Intelligence In Intake (P0)

Why now
- Highest direct impact on catalog quality and operator time.
- Strong alignment with existing Phase 5 intake investments.

Mapped workstreams
- Extend Phase 5 intake workflows and sidecar validation with explicit source semantics.

Stories
1. Add source profile schema in sidecar
- Fields: model_creation_mode, file_collection_mode, inheritance_mode, include/exclude rules, support-config hints.
- Acceptance: profiles persisted, versioned, and retrievable via API.

2. Add folder-level rules evaluation endpoint
- API returns include/exclude decisions plus rationale per file/folder.
- Acceptance: deterministic output for same source snapshot and profile.

3. Add operator explainability panel in intake UI
- Show why each item was included/excluded, with profile/rule trace.
- Acceptance: zero silent exclusions; every exclusion has rationale.

4. Add reusable presets and propagation actions
- Apply to descendants/siblings, per-folder override with inheritance fallback.
- Acceptance: batch apply is reversible and audit-logged.

Dependencies
- Existing Phase 5 intake APIs and state machine remain authority.

---

### EPIC B: Query Language + Saved Searches (P0)

Why now
- Highest discovery ROI after ingestion quality.
- Explicitly aligned to Phase 6 scope.

Mapped workstreams
- Implement inside Phase 6 unified query model and facets.

Stories
1. Query parser service
- Support MVP tokens: tag, collection, source/path, filename, note, name.
- Operators: and/or/not with precedence and parentheses.
- Acceptance: parser returns normalized AST + user-friendly parse errors.

2. Search execution adapter
- Map AST into sidecar query plan and facet filters.
- Acceptance: deterministic result ordering with stable tie-break rules.

3. Saved search model + CRUD
- Save, rename, pin, share-scope (user/local), delete.
- Acceptance: saved searches survive restart and integrate in HA browse UI.

4. Search observability
- Latency, result count, cache-hit metrics and failure reasons.
- Acceptance: status entities expose key diagnostics for support.

Dependencies
- Phase 6 ranking/sorting primitives already defined.

---

### EPIC C: Taxonomy Provenance + Discovery Diagnostics (P0/P1)

Why now
- Improves trust, reduces debugging friction, and supports future automation.

Mapped workstreams
- Phase 6 result projection, model detail, and popup UI surfaces.

Stories
1. Add taxonomy provenance fields to response contracts
- For tags/attributes: source_type, source_id, inherited_from, user_override.
- Acceptance: all displayed taxonomy entries carry provenance metadata.

2. UI badges and filters by provenance
- Filters: system vs inherited vs user.
- Acceptance: operators can isolate user edits from inherited taxonomy.

3. Add parse/preview diagnostics panel
- Show parse mode (server/fallback), selected plate, LOD, triangle counts, fallback reason.
- Acceptance: each 3D-preview session emits a concise diagnostics snapshot.

Dependencies
- Existing geometry/LOD contracts in sidecar and viewer.

---

### EPIC D: Relationships + Troubleshooting Intelligence (P1)

Why now
- Enables high-quality recommendations and de-dup governance.

Mapped workstreams
- Phase 6 related/discovery logic and ranking signals.

Stories
1. Relationship primitives in data model
- relation_type: variant, remix, multipart_group, supersedes, equivalent.
- Acceptance: links are directional where needed and reason-coded.

2. Relationship-aware ranking boosts
- Relatedness and confidence influence relevant sorts where applicable.
- Acceptance: boosts are explainable and bounded.

3. Duplicate + inefficiency insights
- Detect duplicates, oversized/inefficient mesh formats, missing metadata hotspots.
- Acceptance: dashboard with actionable buckets and drill-through.

Dependencies
- Search/ranking layer and candidate enrichment infrastructure.

---

### EPIC E: Multi-Model Compare Viewer (P2)

Why now
- Differentiator after core ingestion/search trust is in place.

Mapped workstreams
- Phase 3 viewer enhancement path with Phase 6 discovery integration.

Stories
1. Selection-to-scene workflow
- Launch compare mode from related results and manual selection.
- Acceptance: load/unload multiple models with stable camera controls.

2. Per-model transforms and visibility
- Toggle visibility, align on bed, per-model bounding boxes.
- Acceptance: no UI lockups on common multi-model scenes.

3. Diagnostics and limits
- Guardrails for max models, triangle budgets, memory pressure warnings.
- Acceptance: graceful degradation path with clear user messaging.

Dependencies
- Existing viewer diagnostics and LOD controls.

---

### EPIC F: Extension Architecture (P2)

Why now
- Strategic enabler for future integrations, but large design surface.

Mapped workstreams
- Post-Phase 6 architecture hardening.

Stories
1. Define extension contract
- Viewer adapters, metadata enrichers, import profile providers.
- Acceptance: contract versioning and compatibility policy documented.

2. Internal plugin loader
- Allowlisted modules with startup validation and health reporting.
- Acceptance: one internal sample adapter in production path.

3. Security and resource governance
- Timeouts, memory bounds, permission boundaries.
- Acceptance: failing plugin cannot crash core browsing flow.

---

## Release Sequencing

### Release R1 (2 sprints)
- EPIC A (core stories 1-3)
- EPIC B (stories 1-2)
- EPIC C (story 1)

Exit criteria
- Intake explainability live.
- Query parser + execution working for MVP tokens.
- Taxonomy provenance available in API payloads.

### Release R2 (2 sprints)
- EPIC B (stories 3-4)
- EPIC C (stories 2-3)
- EPIC D (story 1)

Exit criteria
- Saved searches live in HA UI.
- Diagnostics panel visible in model detail/viewer.
- Relationship primitives persisted and queryable.

### Release R3 (2-3 sprints)
- EPIC D (stories 2-3)
- EPIC E (all stories)

Exit criteria
- Discovery troubleshoot dashboard live.
- Multi-model compare mode production-ready with guardrails.

### Release R4 (optional, strategic)
- EPIC F
- EPIC Creator-profile item (P3) if prioritized

---

## Not Recommended (From Competitive Findings)

1. Do not replace server-side 3MF parsing authority with browser-only parsing.
- Keep current sidecar geometry contracts as source of truth.

2. Do not copy parser implementations with known correctness defects.
- Borrow product ideas, not brittle internals.

3. Do not front-load plugin architecture ahead of ingestion/search trust work.
- Extension points are valuable but should follow core reliability milestones.

---

## Tracking Template (Use Per Issue)

```yaml
initiative: "EPIC A - Source Intelligence In Intake"
story: "Add folder-level rules evaluation endpoint"
phase_mapping: "Phase 5"
value: 5
complexity: 3
confidence: High
dependencies:
  - "existing intake API contracts"
acceptance_criteria:
  - "deterministic include/exclude decisions"
  - "rationale returned per item"
  - "covered by integration tests"
telemetry:
  - "decision_count"
  - "exclusion_reason_distribution"
  - "endpoint_latency_p95"
```

---

## Definition Of Done (Portfolio)

A backlog item is done only when:
1. API/data contracts are documented and version-safe.
2. UI behavior is test-covered and operator-visible diagnostics are present.
3. Performance guardrails are measured on realistic catalogs.
4. Behavior is explainable, not opaque, in both normal and fallback paths.
