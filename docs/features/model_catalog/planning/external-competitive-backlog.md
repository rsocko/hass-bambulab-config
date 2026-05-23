# Prioritized Implementation Backlog From Competitive Reviews

Date: 2026-05-08

Inputs consolidated:
- [docs/features/model_catalog/external-competitive-review-mmp-orynt-2026-05-08.md](../docs/features/model_catalog/external-competitive-review-mmp-orynt-2026-05-08.md)
- [docs/features/model_catalog/external-competitive-review-orynt-alternatives-2026-05-08.md](../docs/features/model_catalog/external-competitive-review-orynt-alternatives-2026-05-08.md)

Alignment anchors used:
- [docs/features/model_catalog/phase-6-search-ranking-and-discovery-design.md](../docs/features/model_catalog/phase-6-search-ranking-and-discovery-design.md)
- [docs/features/model_catalog/PHASE-5-EXECUTION-SEQUENCE.md](../docs/features/model_catalog/PHASE-5-EXECUTION-SEQUENCE.md)
- [docs/features/model_catalog/phase-5-end-state-ui-and-handoff-design.md](../docs/features/model_catalog/phase-5-end-state-ui-and-handoff-design.md)
- [docs/features/model_catalog/phase-3.1-3.3-roadmap.md](../docs/features/model_catalog/phase-3.1-3.3-roadmap.md)

---

## Goal
Turn competitive-analysis insights into a delivery-ready backlog mapped to current model-catalog phases, with clear dependencies and acceptance criteria.

## Scoring
- Value: 1-5
- Complexity: 1-5
- Confidence: High / Medium / Low

---

## Priority Queue (Cross-Phase)

| Priority | Initiative | Value | Complexity | Confidence | Primary Phase Mapping | Source |
|---|---|---:|---:|---|---|---|
| P0 | Source-rule ingestion profiles + explainability | 5 | 3 | High | Phase 5 + Phase 9 intake/project integrations | Orynt, MMP, external-services review |
| P0 | Typed query language + saved searches | 5 | 3 | High | Phase 6 search/discovery | Orynt, Printables patterns |
| P0 | Taxonomy lineage visibility (system/inherited/user) | 4 | 2 | High | Phase 6 + existing detail/browse UI | Orynt, external-services review |
| P0 | Archive-derived ranking signals (popularity, success-rate, recency) | 5 | 2 | High | Phase 6 ranking/discovery | Printables, Thangs, Manyfold insights |
| P1 | Model relationship primitives (variant/remix/multipart/supersedes) | 4 | 3 | High | Phase 6, prepares later project-aware flows | Printables, Thingiverse, online services |
| P1 | Creator/team attribution in taxonomy with provenance | 4 | 2 | High | Phase 5 intake + Phase 6 catalog | Printables, Makerworld, online services |
| P1 | Discovery diagnostics panel (parse/fallback/rationale) | 4 | 2 | High | Phase 6 + Phase 3 viewer/detail surfaces | MMP review, Papa's Best patterns |
| P1 | Duplicate + inefficiency detection dashboard | 4 | 3 | High | Phase 6 troubleshoot/discovery | Manyfold, Printventory patterns |
| P2 | Creator-bundled metadata and print-profile import | 3 | 3 | Medium-High | Phase 5 intake workflow | Online services integration patterns |
| P2 | Multi-model compare/assembly viewer mode | 4 | 4 | Medium | Phase 3 viewer enhancements + Phase 6 related/discovery | MMP UI patterns |
| P2 | Plugin-style extension points (viewer/enrichment adapters) | 4 | 5 | Medium | Post-Phase 6 architecture hardening | Manyfold roadmap |
| P3 | Faceted browse with time/difficulty/success facets | 3 | 2 | Medium | Phase 6 browse UI | Printables, Thangs |
| P3 | Model versioning and supersedes-chain UI | 3 | 4 | Medium | Phase 6+ relationship features | Printables versioning model |

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
- Support MVP tokens: tag, collection, source/path, filename, note, name, creator.
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

### EPIC B.1: Archive-Derived Ranking Signals (P0)

Why now
- Online services show that popularity and success-rate ranking drives discovery.
- Printables/Thangs patterns prove this is high-value UX multiplier.
- Sidecar already has archive linkage; signals are within reach.

Mapped workstreams
- Phase 6 ranking layer + Phase 5 archive-to-catalog link refinement.

Stories
1. Archive-signal projection model
- For each curated model: extract linked_archive_count, print_count, success_rate, last_printed_at.
- Acceptance: all linked archives contribute proportionally; nulls handled gracefully.

2. Ranking boost and sort modes
- Recent, frequent, common, favorite, rating, success-rate sort modes.
- Recency-weighted frequency for "common" scoring (everyday rediscovery).
- Acceptance: stable tie-break rules; no silent opaque changes.

3. Browse UI ranking integration
- Default sorts for browse view: recent (default), frequent, success-rate.
- Facet by success-rate bucket and print-count bucket.
- Acceptance: sort choices persist across sessions; facets update as archive grows.

4. Related-model ranking and discovery
- Use success-rate and print-frequency to score related models.
- Acceptance: related items return rationale metadata explaining why they matched.

Dependencies
- Archive linkage from Phase 5.
- Phase 6 ranking primitives (already designed).

---

### EPIC C: Taxonomy Provenance + Creator Attribution + Discovery Diagnostics (P0/P1)

Why now
- Improves trust, reduces debugging friction, and supports future automation.
- Online services (Printables, Makerworld) show creator attribution is high-value discovery signal.
- Archive linkage provides origin context; make it explicit in catalog.

Mapped workstreams
- Phase 6 result projection, model detail, and popup UI surfaces.
- Phase 5 intake to capture source/creator metadata.

Stories
1. Add taxonomy provenance fields to response contracts
- For tags/attributes: source_type (system/inherited/user), source_id, inherited_from, user_override.
- For creators: creator_name, creator_profile_url, team_id, attribution_required.
- Acceptance: all displayed taxonomy entries carry provenance metadata.

2. Creator/team profiles in catalog metadata
- Store creator name, team affiliation, external source/URL, attribution preference.
- Support team bulk operations (e.g., "flag all models from this creator for review").
- Acceptance: creator profile queryable and filterable in Phase 6 search.

3. UI badges and filters by provenance
- Filters: system vs inherited vs user; verified vs unverified source.
- Creator/team profile badges in result lists.
- Acceptance: operators can isolate user edits from inherited taxonomy and see source attribution.

4. Add parse/preview diagnostics panel
- Show parse mode (server/fallback), selected plate, LOD, triangle counts, fallback reason.
- Link geometry diagnostics to creator when parse failures occur (helps identify bad source files).
- Acceptance: each 3D-preview session emits a concise diagnostics snapshot.

Dependencies
- Existing geometry/LOD contracts in sidecar and viewer.
- Phase 5 intake to capture source provenance.

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
- EPIC B.1 (stories 1-2, archive-signal extraction and basic ranking)
- EPIC C (story 1, provenance fields)

Exit criteria
- Intake explainability live.
- Query parser + execution working for MVP tokens.
- Taxonomy provenance available in API payloads.
- Archive-derived ranking signals available for sort/browse.

### Release R2 (2-3 sprints)
- EPIC B (stories 3-4, saved searches)
- EPIC B.1 (stories 3-4, browse UI ranking integration and related-model discovery)
- EPIC C (stories 2-4, creator attribution, diagnostics panel)
- EPIC D (stories 1-2, relationship primitives and ranking boosts)

Exit criteria
- Saved searches live in HA UI.
- Diagnostics panel visible in model detail/viewer.
- Relationship primitives persisted and queryable.
- Creator attribution visible in results and searchable.

### Release R3 (2-3 sprints)
- EPIC D (story 3, duplicate detection)
- EPIC E (Multi-model compare) or P2 Creator-bundled metadata import

Exit criteria
- Discovery troubleshoot dashboard live.
- Multi-model compare mode production-ready with guardrails (or) creator metadata bundling working.

### Release R4 (optional, strategic)
- EPIC F (Extension architecture)
- Remaining P3 items (faceted browse, versioning UI) if prioritized

---

## Not Recommended (From Competitive Findings)

1. Do not replace server-side 3MF parsing authority with browser-only parsing.
- Keep current sidecar geometry contracts as source of truth.

2. Do not copy parser implementations with known correctness defects.
- Borrow product ideas, not brittle internals.

3. Do not front-load plugin architecture ahead of ingestion/search trust work.
- Extension points are valuable but should follow core reliability milestones.

4. Do not treat Bambuddy as a library authority if rich model curation is important.
- Use Bambuddy for archive/file-manager; sidecar for model-catalog authority.

5. Do not regress from server-side 3MF extraction depth.
- Competing tools show variability in parsing quality; maintain robust server-side baseline.

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

---

## Design Ideas Sourcing (Cross-Reference)

This backlog synthesizes ideas from multiple competitive and user-experience sources:

### From Orynt3D
- Source-rule ingestion profiles with inheritance and explainability
- Taxonomy system distinguishing inherited vs user-added taxonomy
- Search language with typed tokens and boolean operators
- Local-first positioning and privacy respect

### From Printables, Makerworld, Thangs (Online Services)
- Faceted search with popularity/success/time signals
- Creator/team attribution and profile pages
- Explicit model relationships (variant, remix, multipart, supersedes)
- Saved searches and user-defined discovery queues
- Archive-linked popularity and engagement metrics for ranking

### From Manyfold (Local Catalog)
- Metadata richness and structured taxonomy
- Library-oriented UI and curation workflows
- Plugin/extension system architecture direction
- Clear capability matrix and format support transparency

### From Bambuddy (Archive Authority)
- Archive-to-file-manager linkage pattern
- External-folder indexing and allowlist safety model
- File upload queue state machine
- Bambu-specific metadata enrichment

### From Printventory (Desktop Workflows)
- Worker-based parsing to avoid UI blocking
- Local-first and server-mode dual architecture
- Duplicate-detection UX and bulk metadata editing
- Auto-scan and periodic reindexing ergonomics

### From MMP (Caution: Code Review)
- Multi-model side-by-side viewer concept (architecture only, not parsing)
- Project/asset workflow concepts (not implementation)
- **What NOT to copy**: Parsing/enrichment internals with known defects

### From External Services Design Review (Repo Archive)
- O.D.I.N. separation principle: archives ≠ print_files ≠ models ≠ jobs
- Value of explicit link layers between related domains
- Archive-signal extraction for discovery ranking
- Distinction between additive tools and replacement-scale platforms

---

## Summary: High-Level Integration Strategy

1. **Intake Phase (5)**: Source-rule profiles with explainability, creator metadata bundling
2. **Discovery Phase (6)**: Query language, saved searches, archive-derived ranking, relationship primitives
3. **Display Phase (3+6)**: Diagnostics panel, creator attribution UI, relationship visualization
4. **Optional Future (9+)**: Multi-model compare, plugin architecture, versioning UI

All changes preserve the current robust server-side 3MF pipeline and respect the sidecar-owned catalog authority model selected in the post-Manyfold transition.
