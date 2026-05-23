# Model Catalog Implementation Roadmap — Revised With Bulk Ingestion

> **Status**: Updated roadmap incorporating bulk-ingestion and projects assessment.
> **Created**: 2026-04-24
> **Basis**: [bulk-ingestion-and-projects-assessment.md](../bulk-ingestion-and-projects-assessment.md), [projects-design.md](../projects-design.md)

## Post-Manyfold Status Note

This roadmap is a legacy pre-transition sequencing document.

- Legacy `Phase 1.25` now maps to current **Phase 7**.
- Legacy `Phase 1.5` now maps to current **Phase 5**.
- Legacy `Phase 3.5` now maps primarily to current **Phase 6**, with parser/provenance-heavy follow-on work deferred into current **Phase 9**.
- Legacy project/navigation work previously described under `Phase 10` now maps to current **Phase 9**.
- Use [post-manyfold-transition-plan-2026-04.md](../post-manyfold-transition-plan-2026-04.md) and [phase-delivery-and-validation.md](../phase-delivery-and-validation.md) as the authoritative current sequencing documents.

---

## Execution Snapshot

Already complete or materially implemented:

- **Phase 0**: Design baseline and contracts are closed in docs
- **Phase 1**: Sidecar scaffold and Manyfold read baseline are implemented
- **Phase 2**: Archive-linkage slice is implemented and validated end to end

Open planning or implementation work:

- **Phase 1.25**: Backup automation and restore drill are planned, not yet executed
- **Phase 1.5**: Intake Inbox and bulk discovery/import are designed, not yet implemented
- **Phase 3+**: Browse, Working, publish, enrichment, provenance, backfill, and project integration remain open

Current-sequence reading:

- legacy `Phase 1.25` -> current `Phase 7`
- legacy `Phase 1.5` -> current `Phase 5`
- legacy `Phase 3.5` -> current `Phase 6` / `Phase 9` split

Use this roadmap for sequencing and scope boundaries. Use [phase-delivery-and-validation.md](../phase-delivery-and-validation.md) for the stricter current execution state.

Issue tracking note:

- GitHub phase titles have now been realigned to the post-Manyfold sequence.
- Keep this document as historical sequencing context only.
- Revised `.3mf` extraction follow-up from issue `#173` now maps to current `Phase 5` and current `Phase 9` rather than legacy `Phase 3.5` / `Phase 7` labels in active issue titles.

---

## Summary of Changes to Original Plan

The original [implementation-plan.md](../implementation-plan.md) assumed single-file workflows and did not account for:
- Bulk file discovery and import from large existing collections
- Project as a first-class concept linking working groups, curated models, and archives
- Bulk metadata enrichment (color extraction, tag assignment)

**Legacy revised plan** adds three pre-transition sub-phases:
- **Phase 1.25**: Sidecar persistence & backup automation
- **Phase 1.5**: Intake Inbox, bulk discovery & import
- **Phase 3.5**: Bulk metadata enrichment
- **Phase 4-5 (Enhanced)**: Project model and working group/curated model linkage

In the current post-Manyfold sequence, read those as:
- current **Phase 7**: persistence / backup / compatibility boundary
- current **Phase 5**: intake inbox, bulk discovery & import
- current **Phase 6**: bulk metadata enrichment baseline
- current **Phase 9**: project integration and advanced follow-on work

---

## Revised Phase Plan

### Phase 0: Delivery Baseline And Contracts (Unchanged)

**Status**: Complete

Outcomes:
- Architecture baseline frozen
- Manyfold capability matrix confirmed
- External-storage truth table published
- Working-group model defined

**Changes**: None. Phase 0 remains as-is.

---

### Phase 1: Sidecar Scaffold And Manyfold Read Baseline (Unchanged)

**Status**: Implemented for the current scaffold/read slice

Outcomes:
- Catalog sidecar exists as runnable service
- Sidecar can read Manyfold and expose normalized summaries

Delivered in the current slice:
- Scaffold FastAPI sidecar service
- Add health, configuration, diagnostics endpoints
- Bootstrap SQLite schema for:
  - Archive/model links
  - Custom fields
  - Manyfold model summary cache
  - **Working groups and Working items** (planned in original)
   - **Intake inbox queue** (schema preparation for later phases)
  - **Bulk ingestion metadata** (NEW: discovery_metadata, file_hashes, enrichment tracking)
  - **Projects** (NEW: project CRUD tables, junction tables)
  - Review/audit events
- Define archive-facing dependency contract
- Add Manyfold REST client
- Expose sidecar read endpoints

Remaining or follow-on prep captured in this phase:
- Add Working-group discovery-metadata schema (preparation for Phase 1.5)
- Add Project CRUD schema (preparation for Phase 4-5)
- Document field-hash deduplication approach

Deliverables:
- Sidecar runs in Docker with enhanced schema

---

### Phase 1.25: Sidecar Persistence And Backup Automation (NEW, Issue #1121)

**Status**: Planned next; docs complete, execution still open

Outcomes:
- Sidecar durable state has a clear backup boundary and restore playbook
- Backup automation exists before Working-group bulk import and broader operator use
- HA can surface backup status or a manual trigger later without becoming the storage owner

Work items:

1. **Freeze the persistence contract**
   - Treat `/data` as the only durable sidecar-state root
   - Keep the SQLite DB at `MODEL_CATALOG_DB_PATH=/data/model_catalog.db`
   - Require future durable sidecar artifacts (ingestion manifests, parser cache, export bundles) to live under `/data` unless explicitly documented otherwise
   - Document schema-version expectations and restore compatibility assumptions

2. **Choose and document the default storage mode**
   - **Default recommendation: dedicated Docker named volume** for `/data`
   - Reasoning: best isolation, simplest same-stack deployment, avoids accidental Windows/WSL path-coupling, and matches the current compose examples
   - Optional mode: Linux-side bind mount when host-visible inspection or host-native backup tooling is materially valuable
   - Non-recommended default: direct Windows-host bind mount for the live SQLite file

3. **Implement backup/restore workflow at the Docker-host layer**
   - Add a documented backup job that captures `/data` on a schedule
   - Prefer a consistent SQLite snapshot/export step rather than copying an actively-written DB blindly
   - Store backup metadata with timestamp, sidecar image version, and schema version
   - Define restore flow: stop sidecar, restore snapshot, restart sidecar, validate `/healthz` and schema

4. **Add HA-facing operational hooks without making HA the backup engine**
   - HA should not be the first-class owner of filesystem-level backup execution because the volume lives with Docker, not with HA's runtime boundary
   - If useful, add a later HA manual action for "backup now" that calls a sidecar/admin endpoint or host automation
   - If useful, expose read-only backup status in HA (last backup time, last restore-tested time, last backup result)
   - Keep backup execution decoupled from the existing `bambuddy`/print_history local SQLite patterns

5. **Define third-party / fallback backup options**
   - Preferred class: existing homelab backup tooling already trusted for Docker volumes or bind mounts
   - Strong candidates: `restic` or `kopia` around exported snapshots or the `/data` mount
   - Operational fallback: a small scheduled Docker job that writes timestamped backup files to a second protected location
   - Lowest-friction emergency fallback: manual export/copy of `/data/model_catalog.db` before risky schema or deployment changes

6. **Document deployment-mode tradeoffs**
   - **Docker named volume**
     - Pros: strongest isolation, simplest compose, least accidental path drift, good fit for same-stack sidecar
     - Cons: less transparent to browse from Windows Explorer, requires Docker-aware backup tooling or an export step
   - **Linux/WSL bind mount**
     - Pros: host-visible files, easy inspection, easier integration with filesystem backup jobs, simpler manual restore drills
     - Cons: more operator responsibility for path stability, permissions, and accidental edits
   - **Windows bind mount exposed into Linux containers**
     - Pros: easiest direct visibility from Windows tools
     - Cons: weakest recommendation for a live SQLite workload due to performance, permissions, newline/metadata differences, and cross-boundary path fragility

**Design decision for issue #1121**:
- Keep the shipped default as a dedicated Docker named volume for `/data`
- Support Linux/WSL bind mount as an explicit opt-in mode when direct filesystem visibility or host-native backup software is important
- Do not make a Windows-host bind mount the recommended default for the live sidecar DB
- Keep backup automation close to Docker/host operations first; treat HA as a status and optional trigger surface, not the primary backup executor

Deliverables:
- Backup boundary documented for all durable sidecar state
- Default volume strategy and optional bind-mount mode documented
- Backup and restore runbook published and restore-tested
- Optional HA-visible backup status contract defined

---

### Phase 1.5: Intake Inbox, Bulk Discovery, API Upload & Import (NEW)

**Status**: Designed; implementation still open

Outcomes:
- Ad hoc model intake can land in a reviewable Inbox before curation
- Working groups can be populated from filesystem scan
- Small-batch or single-file uploads share the same intake contract as bulk discovery
- Browser local-file uploads and server-side filesystem selections feed a common sidecar queue
- Intake supports explicit file selection, folder selection, or mixed source batches
- Folder sources support recursion control (`recurse` true/false)
- Queue processing uploads selected files into Manyfold using API-managed storage (not sidecar-managed final file storage)
- Folder-to-group mapping can be configured or inferred
- Bulk grouping workflow exists in HA and sidecar
- File deduplication and conflict detection prevent orphaned duplicates
- Optional post-upload source cleanup can delete or replace source files only after verified Manyfold ingestion

Work items:

1. **Sidecar intake endpoint and inbox model**
   - `POST /intake/submit`
   - Input: one or more filesystem paths plus source hint (`drag_drop`, `file_picker`, `streamdeck`, `filesystem_action`, `server_browse`)
   - Output: staged inbox items with validation results, duplicate hints, and proposed titles
   - Store Intake Inbox state until the operator groups, rejects, or publishes deliberately

2. **Browser upload queue and server browse queue adapters**
   - Add queue entry endpoint for browser-selected local files (multipart upload)
   - Add server-root browse endpoints so operators can choose files from sidecar-mounted roots
   - Support both explicit file picks and folder picks in a single normalized source contract
   - Add folder traversal control (`recurse`) per folder source
   - Normalize both paths into one queue contract used by review/import
   - Track queue states (`queued`, `uploading`, `uploaded_unverified`, `verified`, `cleanup_pending`, `cleanup_done`, `cleanup_failed`, `failed`)

3. **Sidecar bulk-discover endpoint**
   - `POST /working-groups/bulk-discover`
   - Input: folder path, grouping strategy ("by-folder", "by-root", "flat")
   - Output: list of proposed working groups with file lists, no commits yet
   - Proposed groups can optionally be materialized into the same Intake Inbox for operator review
   - Deduplication: warn if file hash matches existing working group
   - Validation: check for obvious issues (no files, too many, naming conflicts)

4. **Sidecar bulk-import endpoint**
   - `POST /working-groups/bulk-import`
   - Input: list of reviewed groups or inbox items (name, files, folder_hint, optional stage)
   - Create all Working groups in batch
   - Deduplicate by file hash before creating
   - Upload selected files to Manyfold via API before marking item import complete
   - Track: import timestamp, source folder, strategy used, queue provenance, and Manyfold references
   - Output: created group IDs, errors, summary

5. **Verified post-upload source action policy (optional)**
   - Policy values: `keep` (default), `delete_on_verified`, `replace_with_stub`
   - Execute only after Manyfold upload success and verification checks (hash preferred; size fallback)
   - Restrict destructive actions to approved sidecar-mounted roots
   - Write audit events for each cleanup action and result

Boundary note:
- This phase may only create or attach to Working groups as an intake handoff
- Full Working-group CRUD, Working board/detail UX, and broader file-management workflows remain Phase 4

6. **HA automation/script**
   - Expose service `model_catalog.submit_to_inbox`
   - Expose service `model_catalog.bulk_discover_working_groups`
   - Expose service `model_catalog.bulk_import_working_groups`
   - Store review state in HA helpers for persistence across sessions

7. **HA intake and bulk-import card**
   - Show Inbox items and proposed groups with file lists
   - Show validation status and duplicate warnings
   - Allow rename, merge groups, or skip
   - Allow create Working group, attach to existing group, or keep in Inbox
   - Show deduplication warnings
   - Review and approve before import
   - Show progress and results

8. **Quick-entry adapters**
   - Support drag/drop and file-picker style intake in the operator surface
   - Support path-based shortcuts such as right-click helper or Stream Deck action that submits into the same Intake Inbox contract

9. **Documentation**
   - Intake Inbox semantics and triage rules
   - Folder-scanning best practices for your use case
   - Disambiguation: "by-folder" vs "by-root" strategies
   - Manyfold API upload contract and queue verification semantics
   - Optional post-upload source cleanup safeguards and allowed-root policy
   - Bulk-import error recovery and rollback
   - Example: scanning ~/3D Printing/ with 500+ files

**Design references**:
- See [bulk-ingestion-and-projects-assessment.md](../bulk-ingestion-and-projects-assessment.md) "Phase 1.5" section for full specification
- See [intake-inbox-design.md](../intake-inbox-design.md) for the operator intake model

Deliverables:
- Intake Inbox endpoints and review state
- Upload queue and server-browse adapters feeding one intake pipeline
- Bulk-discover and bulk-import endpoints
- HA intake/bulk-import workflow card
- Manyfold API upload integration with verified completion state
- Optional post-upload cleanup policy with audit trail
- Successful test with 500+ file scenario

---

### Phase 2: Archive Linkage And Popup Integration (Unchanged)

**Status**: Implemented for the first archive-linkage slice; follow-on enhancements remain open

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

**Status**: Open

Outcomes:
- Catalog becomes useful for day-to-day rediscovery and quick reprint

Work items (Phase 3):
- Add sidecar-owned queue/backlog fields
- Add sidecar-owned model taxonomy/browse fields
- Derive archive-backed ranking fields
- Add HA browse card for catalog
- Add filtered backlog/queue view
- Add curated browse filtering

**No changes to Phase 3 core** (Phase 3.5 is separate sub-phase)

Deliverables:
- Catalog card optimized for quick rediscovery
- Simple backlog/queue view

---

### Phase 3.5: Bulk Metadata Enrichment (NEW)

**Status**: Open; depends on Phase 3 core and parser foundation

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

Boundary note:
- Phase 3.5 owns bulk analyze/enrich workflows only
- Publish-time asset selection and individual curated enrichment remain later phases

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
- See [bulk-ingestion-and-projects-assessment.md](../bulk-ingestion-and-projects-assessment.md) "Phase 3.5" section for full specification
- See [planning/3mf-cache-draft.md](../planning/3mf-cache-draft.md) for the concrete sidecar schema and `/api/3mf-analysis/...` draft

Deliverables:
- 3MF analysis service
- Bulk-enrich endpoints and error handling
- HA enrichment review card
- Successful batch enrichment of 500+ files

---

### Phase 4: Working Groups And Working Veneer (Enhanced)

**Status**: Open; broader Working experience not yet implemented

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

Boundary note:
- Phase 4 owns the Working board, general Working-group CRUD, supporting-asset management, and broader reacquisition handling
- It should not be assumed complete just because Phase 1.5 can create or attach a Working group during intake

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

**Status**: Open

Outcomes:
- Boundary between Working and catalog becomes explicit
- Curated models can belong to projects

Work items (Phase 5 — Original):
- Implement publish flow from Working group to catalog
- Define lineage semantics
- Add reconciliation checks before publish
- Support deliberate publish-time choices
- Define recovery behavior for external paths

Boundary note:
- Publish, lineage, curated duplicate reconciliation, and project-aware publish decisions all remain Phase 5
- Phase 1.5 and Phase 4 should hand off to this phase rather than partially reimplement it

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

**Status**: Open

Outcomes:
- Curated records become richer without manual re-entry

Work items:
- Add photo-upload proxy to Manyfold
- Reuse the Phase 3.5 file-hash-keyed analysis cache for individual curated enrichment
- Inventory preview candidates, allowlisted companion resources, and embedded provenance hints without treating raw model payload members as user-facing support files
- Allow preview selection assistance and explicit publish-time promotion
- Expose enrichment actions in archive popup and curated browse
- Add filament ID inference for model color taxonomy

**Note**: Phase 6 3MF enrichment is different from Phase 3.5 bulk enrichment.
- Phase 3.5: Bulk metadata extraction for taxonomy (colors, tags)
- Phase 6: Individual preview/supporting-asset promotion and enrichment for detailed curation

Boundary note:
- Phase 6 is still the late-sequence curated enrichment phase in this roadmap.
- The parser/cache foundation for issue `#173` is tracked earlier under Phase 3.5 and its concrete schema draft lives in [planning/3mf-cache-draft.md](../planning/3mf-cache-draft.md).

Deliverables:
- Curated records can be enriched from HA

---

### Phase 7: Provenance Capture And Online Ingestion (Unchanged)

**Status**: Open

Outcomes:
- Online-source provenance is captured early

Work items:
- Add source recording for Printables/Makerworld URLs
- Keep embedded `.3mf` provenance hints separate from fetched public-source metadata
- Add opt-in source resolution for MakerWorld and other public URLs using sidecar-owned source records
- Surface pending source records in HA
- Preserve source identity for duplicate review
- Add metadata-scrape draft flow later

Deliverables:
- Provenance capture works before or after cataloging

---

### Phase 8: Historical Print-History Backfill From Model Catalog (Unchanged)

**Status**: Open

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

### Phase 9: Storage Monitoring, Preview Quality, And Recovery (Enhanced)

**Status**: Open

Tracking:
- Issue [#222](https://github.com/rsocko/hass-bambulab-config/issues/222)

Outcomes:
- Operators can monitor storage growth and preview quality drift without manual filesystem forensics
- Preview cleanup can be run safely with dry-run visibility before destructive actions

Work items:
- Add storage sensors and maintenance actions with trend-aware thresholds
- Add stale-preview detection and quality guardrails for canonical preview coverage
- Add preview trim workflow with dry-run/apply modes and clear audit output
- Add recovery/runbook guidance for rescan vs recreate/relink paths

Deliverables:
- Storage monitoring and preview-maintenance controls are available in Phase 9 workflows

---

### Phase 10: Upstream Improvement Track + Projects Integration (Enhanced)

**Status**: Open

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
3. SQLite backup/export consistency while the sidecar is running (Phase 1.25)
4. Restore drill from backup into a fresh sidecar instance (Phase 1.25)
5. Named-volume versus Linux bind-mount operational fit in your Docker/WSL setup (Phase 1.25)
6. Filesystem scan performance with 500+ files (Phase 1.5)
7. File-hash deduplication accuracy and speed (Phase 1.5)
8. 3MF parser performance on 500+ files, async processing (Phase 3.5)
9. Color extraction accuracy and edge cases (Phase 3.5)
10. Tag inference quality from folder names (Phase 3.5)
11. Rescan behavior for curated external library changes (Phase 5)
12. Recovery after restoring missing external files (Phase 5)
13. Archive linkage scale with projects (Phase 2 / Phase 10)
14. Project navigation performance with large archives (Phase 10)
15. Same-stack sidecar deployment and project DB scale (Phase 10)

---

## Timeline Estimates (Rough)

Assuming single developer, ~40h/week committed:

| Phase | Effort | Weeks | Cumulative |
|-------|--------|-------|-----------|
| 0 | Design | 2-3 | 2-3 |
| 1 | Scaffold | 3-4 | 5-7 |
| **1.25** | **Persistence + backup** | **1-2** | **6-9** |
| **1.5** | **Bulk ingest** | **2-3** | **8-12** |
| 2 | Archive linkage | 3-4 | 11-16 |
| 3 | Browse & ranking | 4-5 | 15-21 |
| **3.5** | **Bulk enrichment** | **2-3** | **17-24** |
| 4 | Working groups | 3-4 | 20-28 |
| 5 | Publish workflow | 2-3 | 22-31 |
| 6 | Photo upload | 2-3 | 24-34 |
| 7 | Provenance | 1-2 | 25-36 |
| 8 | Backfill | 2-3 | 27-39 |
| 9 | Storage monitoring | 1-2 | 28-41 |
| **10** | **Projects + integration** | **3-4** | **31-45** |

**Total: 31-45 weeks (7-11 months)** to full delivery of all phases including projects and backup automation.

**Expedited baseline** (Phase 0-3, skip 1.5/3.5): **15-21 weeks (4-5 months)**

**With bulk ingest only** (Phase 0-3 + 1.25 + 1.5): **18-24 weeks (4.5-6 months)**

---

## Recommended Delivery Sequencing

### Option A: Bulk-First (Recommended For Your Use Case)

1. Phase 0 (design)
2. Phase 1 (scaffold)
3. **Phase 1.25 (persistence + backup)** ← Protect sidecar state before it becomes valuable
4. **Phase 1.5 (bulk ingest)** ← Priority for your 500+ files
5. Phase 2 (archive linkage)
6. Phase 3 (browse)
7. **Phase 3.5 (bulk enrichment)** ← Productivity for your use case
8. Phase 4 (working groups)
9. Phase 5 (publish)
10. Phase 6-9 (later)
11. **Phase 10 (projects)** ← Full integration for your use case

**Rationale**: Bulk ingest and enrichment directly address your ingestion scenario, but issue #1121 means the sidecar needs a backup story before those phases create harder-to-reconstruct state. Projects complete the design for your project-based organization.

### Option B: Browse-First (Faster Time To Working System)

1. Phase 0 (design)
2. Phase 1 (scaffold)
3. Phase 1.25 (persistence + backup)
4. Phase 2 (archive linkage)
5. Phase 3 (browse)
6. Phase 4 (working groups)
7. Phase 1.5 (bulk ingest) ← Add after basic system works
8. Phase 5 (publish)
9. Phase 3.5 (bulk enrichment) ← After core curation
10. Phase 6-9
11. Phase 10 (projects)

**Rationale**: Get a working system faster, then add bulk workflows.

**Recommendation**: **Option A is better for your stated use case.** You have 500+ files waiting to be organized; bulk import and enrichment should be early so you can start using the system immediately.

---

## Dependencies and Blockers

| Phase | Depends On | Blocker? | Notes |
|-------|-----------|----------|-------|
| 1 | Phase 0 | No | |
| **1.25** | Phase 1 | No | Should land before broader operator data accumulation |
| **1.5** | Phase 1, 1.25 | No | But Phase 1 schema needs working-group prep |
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

**Critical path for bulk ingest**: Phase 0 → 1 → 1.25 → 1.5 → (optionally 3.5) → 4 → 5 → 10

**No hard blockers.** Can deliver Phase 1.5 as soon as Phase 1 is complete.

---

## Design Artifacts to Create

Still useful to extract or add before those later phases start:

1. ✅ **Bulk Ingestion & Projects Assessment** — [bulk-ingestion-and-projects-assessment.md](../bulk-ingestion-and-projects-assessment.md)
2. ✅ **Projects Design** — [projects-design.md](../projects-design.md)
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

## Open Questions For Remaining Planning

1. **Bulk discovery strategy**: Does "by-folder" match your folder organization well? If not, what variations are needed?
2. **3MF parser**: Should we call an external tool (e.g., OpenSCAD, 3MF SDK) or write our own? Performance requirement?
3. **Color accuracy**: Is >80% enough, or do you need > 95%? What's the human time cost to fix auto-extracted colors?
4. **Tag inference**: Folder names as tags? Filename patterns? Both? Custom rules?
5. **Project model**: Confirm sidecar ownership before implementation starts.
6. **Bambuddy integration**: Optional or required? Tight coupling OK or should it remain loose?
7. **Timeline**: Is 4-5 months acceptable, or do you want to prioritize a subset of phases?

