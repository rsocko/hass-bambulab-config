# Model Catalog Implementation Roadmap — Revised With Bulk Ingestion

> **Status**: Updated roadmap incorporating bulk-ingestion and projects assessment.
> **Created**: 2026-04-24
> **Basis**: [bulk-ingestion-and-projects-assessment.md](bulk-ingestion-and-projects-assessment.md), [projects-design.md](projects-design.md)

---

## Summary of Changes to Original Plan

The original [implementation-plan.md](implementation-plan.md) assumed single-file workflows and did not account for:
- Bulk file discovery and import from large existing collections
- Project as a first-class concept linking working groups, curated models, and archives
- Bulk metadata enrichment (color extraction, tag assignment)

**Revised plan** adds three new sub-phases:
- **Phase 1.5**: Bulk discovery & import
- **Phase 3.5**: Bulk metadata enrichment
- **Phase 4-5 (Enhanced)**: Project model and working group/curated model linkage

---

## Revised Phase Plan

### Phase 0: Delivery Baseline And Contracts (Unchanged)

**Status**: ✅ Already approved

Outcomes:
- Architecture baseline frozen
- Manyfold capability matrix confirmed
- External-storage truth table published
- Working-group model defined

**Changes**: None. Phase 0 remains as-is.

---

### Phase 1: Sidecar Scaffold And Manyfold Read Baseline (Unchanged)

**Status**: Ready for implementation

Outcomes:
- Catalog sidecar exists as runnable service
- Sidecar can read Manyfold and expose normalized summaries

Work items:
- Scaffold FastAPI sidecar service
- Add health, configuration, diagnostics endpoints
- Bootstrap SQLite schema for:
  - Archive/model links
  - Custom fields
  - Manyfold model summary cache
  - **Working groups and Working items** (planned in original)
  - **Bulk ingestion metadata** (NEW: discovery_metadata, file_hashes, enrichment tracking)
  - **Projects** (NEW: project CRUD tables, junction tables)
  - Review/audit events
- Define archive-facing dependency contract
- Add Manyfold REST client
- Expose sidecar read endpoints

**Additions to original Phase 1**:
- Add Working-group discovery-metadata schema (preparation for Phase 1.5)
- Add Project CRUD schema (preparation for Phase 4-5)
- Document field-hash deduplication approach

Deliverables:
- Sidecar runs in Docker with enhanced schema

---

### Phase 1.5: Bulk Discovery & Import (NEW)

**Status**: Recommended before Phase 2

Outcomes:
- Working groups can be populated from filesystem scan
- Folder-to-group mapping can be configured or inferred
- Bulk grouping workflow exists in HA and sidecar
- File deduplication and conflict detection prevent orphaned duplicates

Work items:

1. **Sidecar bulk-discover endpoint**
   - `POST /working-groups/bulk-discover`
   - Input: folder path, grouping strategy ("by-folder", "by-root", "flat")
   - Output: list of proposed working groups with file lists, no commits yet
   - Deduplication: warn if file hash matches existing working group
   - Validation: check for obvious issues (no files, too many, naming conflicts)

2. **Sidecar bulk-import endpoint**
   - `POST /working-groups/bulk-import`
   - Input: list of reviewed groups (name, files, folder_hint, optional stage)
   - Create all Working groups in batch
   - Deduplicate by file hash before creating
   - Track: import timestamp, source folder, strategy used
   - Output: created group IDs, errors, summary

3. **HA automation/script**
   - Expose service `model_catalog.bulk_discover_working_groups`
   - Expose service `model_catalog.bulk_import_working_groups`
   - Store review state in HA helpers for persistence across sessions

4. **HA bulk-import card**
   - Show proposed groups with file lists
   - Allow rename, merge groups, or skip
   - Show deduplication warnings
   - Review and approve before import
   - Show progress and results

5. **Documentation**
   - Folder-scanning best practices for your use case
   - Disambiguation: "by-folder" vs "by-root" strategies
   - Bulk-import error recovery and rollback
   - Example: scanning ~/3D Printing/ with 500+ files

**Design references**:
- See [bulk-ingestion-and-projects-assessment.md](bulk-ingestion-and-projects-assessment.md) "Phase 1.5" section for full specification

Deliverables:
- Bulk-discover and bulk-import endpoints
- HA bulk-import workflow card
- Successful test with 500+ file scenario

---

### Phase 2: Archive Linkage And Popup Integration (Unchanged)

**Status**: As planned

Outcomes:
- Archive popup becomes first operator surface for model linkage

Work items:
- Implement archive-link CRUD and candidate-review endpoints
- Expose HA services for link management
- Show Manyfold model summary in popup
- Allow queue/backlog state updates from confirmed linkage

**Enhancements from revised plan**:
- Optional: Show related projects if archive is linked to model in a project
- Optional: Show related working groups from same project

Deliverables:
- End-to-end archive-to-model linking from HA

---

### Phase 3: Queue, Ranking, And Curated Browse (Unchanged Core, Enhanced with 3.5)

**Status**: As planned

Outcomes:
- Curated catalog becomes useful for day-to-day rediscovery and quick reprint

Work items (Phase 3):
- Add sidecar-owned queue/backlog fields
- Add sidecar-owned model taxonomy/browse fields
- Derive archive-backed ranking fields
- Add HA browse card for curated catalog
- Add filtered backlog/queue view
- Add curated browse filtering

**No changes to Phase 3 core** (Phase 3.5 is separate sub-phase)

Deliverables:
- Curated catalog card optimized for quick rediscovery
- Simple backlog/queue view

---

### Phase 3.5: Bulk Metadata Enrichment (NEW)

**Status**: Recommended after Phase 3 core

Outcomes:
- Bulk color extraction from 3MF files
- Bulk tag assignment from folder structure or file naming
- Bulk provenance capture
- Preview before commit

Work items:

1. **3MF parser integration**
   - Add Python/Rust parser to sidecar (or subprocess call to tool)
   - Extract model dimensions, material slots, color information
   - Cache results in SQLite with file hash as key
   - Support background/async processing for large batches

2. **Sidecar bulk-analyze endpoint**
   - `POST /working-groups/bulk-analyze`
   - Input: list of working group IDs
   - Process: Extract colors, dimensions, material info per file
   - Propose: Tags from folder structure or naming patterns
   - Output: list of proposed enrichments with confidence scores

3. **Sidecar bulk-enrich endpoint**
   - `POST /working-groups/bulk-enrich`
   - Input: list of enrichments (with operator approval)
   - Apply: Colors, tags, and metadata in batch
   - Track: Enrichment source for later audit
   - Output: Applied enrichments and summary

4. **HA enrichment review card**
   - Show proposed colors for each group with swatches
   - Show proposed tags with confidence scores
   - Allow operator override or skip per item
   - Batch apply after review
   - Show audit trail (which enrichments were applied, which were skipped)

5. **Documentation**
   - Tag-assignment heuristics
   - Color extraction confidence levels
   - Bulk-enrich error recovery
   - Example workflows

**Design references**:
- See [bulk-ingestion-and-projects-assessment.md](bulk-ingestion-and-projects-assessment.md) "Phase 3.5" section for full specification

Deliverables:
- 3MF analysis service
- Bulk-enrich endpoints and error handling
- HA enrichment review card
- Successful batch enrichment of 500+ files

---

### Phase 4: Working Groups And Working Veneer (Enhanced)

**Status**: As planned, with project linkage

Outcomes:
- Working files gain first-class operator surface without forcing them into Manyfold
- Working groups can optionally belong to projects

Work items (Phase 4 — Original):
- Implement Working-group data model
- Support logical grouping
- Add Working-side duplicate detection
- Expose sidecar endpoints for CRUD
- Add custom/remix provenance fields
- Add HA Working-group board
- Support quick-open actions

**Additions for Phase 4 (Projects)**:
- Add `project_id` field to working groups (optional, nullable)
- Support assigning working groups to projects
- Update HA working board to optionally show/filter by project
- Update working-group detail to show related project and cross-linked items

Deliverables:
- Working files become visible and manageable from HA
- Working groups can optionally be organized by project

---

### Phase 5: Publish Workflow And Revision Lineage (Enhanced)

**Status**: As planned, with project linkage

Outcomes:
- Boundary between Working and curated catalog becomes explicit
- Curated models can belong to projects

Work items (Phase 5 — Original):
- Implement publish flow from Working group to curated catalog
- Define lineage semantics
- Add reconciliation checks before publish
- Support deliberate publish-time choices
- Define recovery behavior for external paths

**Additions for Phase 5 (Projects)**:
- Support creating or adding curated model to a project during publish
- Store published_from_group_id in project metadata
- Show project context in publish workflow
- Allow operator to add model to existing project or create new one
- Track lineage: "This curated model came from working group X in project Y"

Deliverables:
- Clear Working-to-curated publish action with optional project assignment

---

### Phase 6: Photo Upload And 3MF Enrichment (Unchanged)

**Status**: As planned

Outcomes:
- Curated records become richer without manual re-entry

Work items:
- Add photo-upload proxy to Manyfold
- Implement sidecar-driven 3MF parsing and asset upload
- Allow preview selection assistance
- Expose enrichment actions in archive popup and curated browse
- Add filament ID inference for model color taxonomy

**Note**: Phase 6 3MF enrichment is different from Phase 3.5 bulk enrichment.
- Phase 3.5: Bulk metadata extraction for taxonomy (colors, tags)
- Phase 6: Individual photo/asset upload and enrichment for detailed curation

Deliverables:
- Curated records can be enriched from HA

---

### Phase 7: Provenance Capture And Online Ingestion (Unchanged)

**Status**: As planned

Outcomes:
- Online-source provenance is captured early

Work items:
- Add source recording for Printables/Makerworld URLs
- Surface pending source records in HA
- Preserve source identity for duplicate review
- Add metadata-scrape draft flow later

Deliverables:
- Provenance capture works before or after cataloging

---

### Phase 8: Historical Print-History Backfill From Model Catalog (Unchanged)

**Status**: As planned

Outcomes:
- Model-catalog UI can assist operator-driven backfill of older print-history records

Work items:
- Add catalog-driven review flow for backfill candidates
- Surface nearby or candidate archive matches
- Support operator choices (link, create, attach, defer)
- Reuse existing runner and manifest concepts

Deliverables:
- Model-catalog-driven backfill workflow exists

---

### Phase 9: Storage Monitoring, Preview Quality, And Recovery (Unchanged)

**Status**: As planned

Deliverables:
- Storage sensors and maintenance actions

---

### Phase 10: Upstream Improvement Track + Projects Integration (Enhanced)

**Status**: New phase, now includes project integration

Outcomes:
- Sidecar boundary remains stable
- Projects become fully cross-linked
- Optional Bambuddy project linkage available

Work items (New in Phase 10):

1. **Project CRUD endpoints** (sidecar)
   - Create, read, update, delete projects
   - Manage project composition (add/remove groups and models)

2. **HA project views**
   - Projects browser/grid
   - Project detail view with cross-links
   - Related archives aggregation
   - Cross-link from archive detail to project

3. **HA services for project management**
   - Create project
   - Add/remove working groups
   - Add/remove curated models
   - Set Bambuddy project reference

4. **Cross-feature contracts**
   - Document archive → model → project navigation
   - Document working group ↔ project linkage
   - Document curated model ↔ project linkage
   - Optional Bambuddy project integration

5. **Upstream enhancement list**
   - Continue to maintain list of Manyfold gaps
   - Evaluate upstream PRs
   - Keep fork boundary clear

Deliverables:
- Projects become first-class in HA
- Cross-system navigation works
- Clear distinction between sidecar and upstream work

---

## Validation Spikes (Updated)

Before implementation, validate:

1. ✅ Manyfold REST upload and file operations (Phase 1)
2. ✅ Manyfold file/model PATCH for safe write-back (Phase 1)
3. Filesystem scan performance with 500+ files (Phase 1.5)
4. File-hash deduplication accuracy and speed (Phase 1.5)
5. 3MF parser performance on 500+ files, async processing (Phase 3.5)
6. Color extraction accuracy and edge cases (Phase 3.5)
7. Tag inference quality from folder names (Phase 3.5)
8. Rescan behavior for curated external library changes (Phase 5)
9. Recovery after restoring missing external files (Phase 5)
10. Archive linkage scale with projects (Phase 2 / Phase 10)
11. Project navigation performance with large archives (Phase 10)
12. Same-stack sidecar deployment and project DB scale (Phase 10)

---

## Timeline Estimates (Rough)

Assuming single developer, ~40h/week committed:

| Phase | Effort | Weeks | Cumulative |
|-------|--------|-------|-----------|
| 0 | Design | 2-3 | 2-3 |
| 1 | Scaffold | 3-4 | 5-7 |
| **1.5** | **Bulk ingest** | **2-3** | **7-10** |
| 2 | Archive linkage | 3-4 | 10-14 |
| 3 | Browse & ranking | 4-5 | 14-19 |
| **3.5** | **Bulk enrichment** | **2-3** | **16-22** |
| 4 | Working groups | 3-4 | 19-26 |
| 5 | Publish workflow | 2-3 | 21-29 |
| 6 | Photo upload | 2-3 | 23-32 |
| 7 | Provenance | 1-2 | 24-34 |
| 8 | Backfill | 2-3 | 26-37 |
| 9 | Storage monitoring | 1-2 | 27-39 |
| **10** | **Projects + integration** | **3-4** | **30-43** |

**Total: 30-43 weeks (7-10 months)** to full delivery of all phases including projects.

**Expedited baseline** (Phase 0-3, skip 1.5/3.5): **14-19 weeks (3.5-5 months)**

**With bulk ingest only** (Phase 0-3 + 1.5): **16-22 weeks (4-5 months)**

---

## Recommended Delivery Sequencing

### Option A: Bulk-First (Recommended For Your Use Case)

1. Phase 0 (design)
2. Phase 1 (scaffold)
3. **Phase 1.5 (bulk ingest)** ← Priority for your 500+ files
4. Phase 2 (archive linkage)
5. Phase 3 (browse)
6. **Phase 3.5 (bulk enrichment)** ← Productivity for your use case
7. Phase 4 (working groups)
8. Phase 5 (publish)
9. Phase 6-9 (later)
10. **Phase 10 (projects)** ← Full integration for your use case

**Rationale**: Bulk ingest and enrichment directly address your ingestion scenario. Projects complete the design for your project-based organization.

### Option B: Browse-First (Faster Time To Working System)

1. Phase 0 (design)
2. Phase 1 (scaffold)
3. Phase 2 (archive linkage)
4. Phase 3 (browse)
5. Phase 4 (working groups)
6. Phase 1.5 (bulk ingest) ← Add after basic system works
7. Phase 5 (publish)
8. Phase 3.5 (bulk enrichment) ← After core curation
9. Phase 6-9
10. Phase 10 (projects)

**Rationale**: Get a working system faster, then add bulk workflows.

**Recommendation**: **Option A is better for your stated use case.** You have 500+ files waiting to be organized; bulk import and enrichment should be early so you can start using the system immediately.

---

## Dependencies and Blockers

| Phase | Depends On | Blocker? | Notes |
|-------|-----------|----------|-------|
| 1 | Phase 0 | No | |
| **1.5** | Phase 1 | No | But Phase 1 schema needs working-group prep |
| 2 | Phase 1 | No | |
| 3 | Phase 2 | No | Improves with archive linkage |
| **3.5** | Phase 1, 3 | No | 3MF parser is optional dependency |
| 4 | Phase 1 | No | Improves with projects (Phase 10) |
| 5 | Phase 4 | No | Improves with projects |
| 6 | Phase 5 | No | |
| 7 | Phase 1, 2 | No | |
| 8 | Phase 5 | No | Uses existing print-history tooling |
| 9 | Any | No | Utility, not blocking |
| **10** | Phase 1, 4, 5 | No | But needed for full bulk-ingest scenario |

**Critical path for bulk ingest**: Phase 0 → 1 → 1.5 → (optionally 3.5) → 4 → 5 → 10

**No hard blockers.** Can deliver Phase 1.5 as soon as Phase 1 is complete.

---

## Design Artifacts to Create

Before implementation starts:

1. ✅ **Bulk Ingestion & Projects Assessment** — [bulk-ingestion-and-projects-assessment.md](bulk-ingestion-and-projects-assessment.md)
2. ✅ **Projects Design** — [projects-design.md](projects-design.md)
3. 🔲 **Working Groups Phase 1.5 Specification** — (sub-section of above, ready to extract)
4. 🔲 **Bulk Enrichment Phase 3.5 Specification** — (sub-section of above, ready to extract)
5. 🔲 **Cross-Feature Project Linkage Contract** — (new document for Phase 10)
6. 🔲 **HA Project Board / Navigation Design** — (UX mockup or detailed wireframe)

---

## Success Criteria

### Phase 1.5 Success
- [ ] Discover 500+ files from ~/3D Printing/ in < 5 seconds
- [ ] Auto-group by subfolder (or by-root) strategy
- [ ] Propose ~20-30 working groups
- [ ] Preview before commit
- [ ] Import all groups in < 10 seconds
- [ ] File-hash deduplication catches duplicates

### Phase 3.5 Success
- [ ] Analyze 500+ files for colors in < 30 seconds (async)
- [ ] Extract colors with > 80% accuracy
- [ ] Propose tags from folder structure
- [ ] Batch approve and apply in < 5 seconds
- [ ] Result: All working groups have colors and tags applied

### Phase 10 Success
- [ ] Navigate: Archive → Project → Related Groups → Related Models
- [ ] Create project from bulk-import or publish workflow
- [ ] List all items in project (groups + models + archives)
- [ ] Optional Bambuddy project linkage works
- [ ] HA project views are responsive and informative

---

## Out Of Scope For Baseline (Unchanged)

- Managing `Downloads/` as a first-class system
- Turning HA into a full Manyfold admin replacement
- Forcing Working into Manyfold
- Direct Manyfold DB writes (API only)
- Manyfold library admin via API (upstream gap)
- Full project admin with user roles, sharing, etc. (single-user baseline)

---

## Open Questions For Planning

1. **Bulk discovery strategy**: Does "by-folder" match your folder organization well? If not, what variations are needed?
2. **3MF parser**: Should we call an external tool (e.g., OpenSCAD, 3MF SDK) or write our own? Performance requirement?
3. **Color accuracy**: Is >80% enough, or do you need > 95%? What's the human time cost to fix auto-extracted colors?
4. **Tag inference**: Folder names as tags? Filename patterns? Both? Custom rules?
5. **Project model**: Confirm sidecar ownership before implementation starts.
6. **Bambuddy integration**: Optional or required? Tight coupling OK or should it remain loose?
7. **Timeline**: Is 4-5 months acceptable, or do you want to prioritize a subset of phases?

