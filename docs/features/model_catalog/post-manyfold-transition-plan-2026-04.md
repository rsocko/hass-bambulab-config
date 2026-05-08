# Post-Manyfold Transition Plan (2026-04)

> Status: Approved implementation direction
> Last updated: 2026-04-28
> Decision: Retire Manyfold from the active model-catalog operational path and move to sidecar-owned catalog authority

## Purpose

Define the definitive migration plan from Manyfold-backed catalog authority to a custom sidecar-owned model catalog while preserving in-flight implementation work and minimizing disruption.

## Final Decisions

- Authority model: sidecar-owned custom catalog is authoritative for model metadata and model assets.
- Manyfold role: retired from active operational path; optional read-only adapter only in future phases.
- Phase handling: full sequential renumbering (new phase sequence below).
- Issue migration: hybrid strategy (close deprecated Manyfold-blocked issues, retarget still-valid issues, split mixed issues).
- **Persistence baseline**: Stay with SQLite for Phase 1-5. Plan SQLAlchemy ORM migration for Phase 6+ if multi-sidecar deployment emerges. See [Persistence Strategy and Database Graduation Path](persistence-strategy-and-graduation.md) for detailed rationale, trigger criteria, and migration playbook.

## Scope

### In scope

- Full metadata parity previously dependent on Manyfold (title, description, tags, collections, creators, links, license, favorites, ratings, notes, queue fields).
- Multi-file model records with typed assets (images, 3mf, stl/obj/step, PDF/docs/supporting files).
- Local API/storage cutover and compatibility for current HA surfaces.
- Continuation of in-flight Phase 3 UI work against local model APIs.
- Documentation and issue tracking realignment.

### Out of scope for this transition wave

- Active bidirectional sync with Manyfold.
- Requiring Manyfold for uploads, scans, or curated metadata writes.
- Full social/publishing workflows beyond current repo scope.

## Sequential Post-Manyfold Phases

### Phase 1: Authority Pivot Foundation

- Set sidecar as sole catalog authority.
- Freeze and deprecate Manyfold-dependent runtime paths.
- Establish migration-safe baseline schema direction.

### Phase 2: Canonical Data Model Expansion

- Implement canonical model record and metadata fields.
- Implement model asset graph with multiple assets per model.
- Add revision/provenance fields compatible with archive linkage.

### Phase 3: API and Storage Cutover

- Replace Manyfold-backed CRUD/search/filter with local APIs.
- Implement sidecar-owned upload and filesystem intake paths.
- Preserve DTO compatibility for existing HA cards/services where practical.

### Phase 4: UI Continuity and In-Flight Preservation

- Complete in-flight model popup/browser work against local APIs.
- Complete edit mode + gallery/file management with local data authority.
- Revalidate 3D viewer and linked-print flows with new schema.

### Phase 5: Intake, Bulk Discovery, and Working/Curated Unification

- Activate inbox and bulk intake as first-class workflows.
- Unify draft-to-curated lifecycle in sidecar.
- Keep dedupe and validation states operator-reviewable.

### Phase 6: Search, Ranking, and Enrichment Parity

- Rebuild search/filter/sort/ranking without Manyfold assumptions.
- Preserve and extend archive-link candidate/review workflows.

### Phase 7: Data Migration and Compatibility Layer

- Migrate existing sidecar cache/custom/linkage data to canonical schema.
- Keep temporary compatibility aliases for HA integrations.
- Remove Manyfold runtime settings and dead code post-validation.

### Phase 8: Docs and Issue Realignment

- Update architecture/strategy/phase docs for new sequence.
- Add legacy-to-new phase crosswalk.
- Apply hybrid issue migration policy.

### Phase 9: Future Integrations and Advanced Work

- Reframe Thingiverse/Printables/Makerworld ingestion as direct sidecar connectors.
- Re-scope advanced provenance and 3MF analysis phases to be Manyfold-independent.
- Optional Manyfold read-only adapter remains non-critical and deferred.

## Manyfold Feature Migration Priority Matrix

### Priority 0 (cutover-critical)

- Core metadata: title, description, tags, creators, collections, links, license.
- Multi-file model asset management with roles and ordering.
- Search/filter/pagination and archive-link continuity.

### Priority 1 (early post-cutover)

- Edit conflict detection.
- Bulk intake/discovery and dedupe workflows.
- Photo/gallery management and preview selection.
- Favorites/ratings and queue metadata.

### Priority 2 (advanced)

- 3MF deep analysis cache and enrichment suggestion automation.
- Provenance automation and external-source metadata enrichment.

### Priority 3 (optional)

- Optional read-only Manyfold adapter.
- Non-critical export/sync tooling.

## Legacy-To-New Phase Crosswalk

| Legacy phase | New phase | Notes |
|---|---|---|
| Phase 0 | Phase 1 input | Baseline docs remain historical context |
| Phase 1A | Phase 1-3 | Scaffold + read contracts inform cutover groundwork |
| Phase 1.25 | Phase 7-8 | Persistence/backup remains required before hard cutover |
| Phase 1.5 | Phase 5 | Intake/inbox promoted to core path |
| Phase 2 | Phase 6-7 | Archive-linkage preserved and migrated |
| Phase 3.0 | Phase 4 | Popup read surface preserved |
| Phase 3.1 | Phase 4 | Edit/gallery completion against local authority |
| Phase 3.2 | Phase 4 | 3D viewer completion against local authority |
| Phase 3.3 | Phase 4/6 | Cross-system navigation + related-model flows |
| Phase 3.5 | Phase 6/9 | Enrichment and parser-heavy work re-scoped |
| Phase 4-10 | Phase 5-9 | Re-indexed for post-Manyfold sequence |

## GitHub Issue Migration Policy (Hybrid)

1. Create one migration umbrella issue for the post-Manyfold transition.
2. Create child tracks for:
   - schema/API cutover
   - data migration
   - UI adaptation
   - docs migration
   - verification and rollout
3. Close issues that are Manyfold-blocked or Manyfold-only.
4. Retarget still-valid in-flight issues to the new sequential phases.
5. Split mixed issues that combine deprecated scope and still-valid scope.
6. Label all migrated issues with a common migration marker and new phase labels.

## Verification Gates

1. Schema gate: metadata and multi-file asset coverage complete.
2. API gate: current UI-critical paths available and stable.
3. Workflow gate: create/edit model, attach multiple files, archive-link, search/filter, and preview flow pass.
4. Migration gate: cache/custom/linkage data migrated without archival linkage loss.
5. Regression gate: model_catalog tests and relevant HA integration tests pass.
6. Docs and tracking gate: docs and issues reflect new phase sequence and policy.

## Related Documents

- architecture-overview.md
- phase-delivery-and-validation.md
- phase-6-search-ranking-and-discovery-design.md
- phase-6-bulk-metadata-enrichment-design.md
- implementation-strategy-options.md
- external-services-design-review-2026-04.md
- README.md
