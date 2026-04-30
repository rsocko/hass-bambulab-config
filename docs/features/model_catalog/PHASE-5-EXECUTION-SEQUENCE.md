# Phase 5: Intake, Bulk Discovery, and Working/Curated Unification — Execution Sequence

> **Status**: Execution sequencing document
> **Created**: 2026-04-30
> **Scope**: Post-Manyfold model-catalog Phase 5 — 20 GitHub issues organized by dependency and delivery order
> **Authority**: [Post-Manyfold Transition Plan](post-manyfold-transition-plan-2026-04.md) + [Phase Delivery And Validation](phase-delivery-and-validation.md)

## Phase 5 Purpose

Activate inbox and bulk intake as first-class workflows. Unify draft-to-curated lifecycle in sidecar. Keep dedup and validation states operator-reviewable.

**Output**: Files can be ingested via bulk discovery, drag-drop, or server-browse into a reviewable Intake Inbox. Intake items can be converted into Working Groups without requiring publish workflows. Working groups have a minimal but complete data model with deduplication and conflict detection.

---

## Issue Mapping Summary

| Area | Issues | Status |
|------|--------|--------|
| **Design & Validation** | #1059, #1074, #1079 | Foundation |
| **Sidecar Backend** | #1075, #1076, #1144, #1147, #1080 | Core infra |
| **Intake & Discovery** | #1130, #1042 | Main workflow |
| **HA Integration** | #1077, #1082, #1145 | UI/UX |
| **Publish Handoff** | #1163, #1137, #1132, #1133 | Later phases |
| **Operations** | #1149, #1146, #213 | Supporting |

---

## Recommended Execution Order

### **WAVE 1: Foundation & Specification (Days 1–3)**

These must complete before any implementation begins. They freeze the data model and validation rules.

#### 1️⃣ #1059: Validate working-file indexing and logical grouping feasibility
- **Effort**: 1 day (research/validation)
- **Blocker for**: Everything
- **What it delivers**:
  - Proof that filesystem indexing (filesystem walk + hash-based dedupe) can scale to 500+ models
  - Feasibility of incremental indexing (timestamp + hash strategy)
  - Answers on performance expectations and caching strategy
- **Acceptance criteria**:
  - Test scan on a real ~500 file directory
  - Document incremental update strategy
  - Confirm hash-based dedupe is effective
- **Owner**: Research/validation phase
- **GitHub**: [#1059](https://github.com/rsocko/hass-bambulab-config/issues/1059)

#### 2️⃣ #1074: Define working-file inventory and normalization rules
- **Effort**: 1 day (spec writing)
- **Blocker for**: #1075, #1076, #1130, #1042
- **What it delivers**:
  - Document of supported file types (3MF, STL, STEP, slicer projects, zips)
  - Normalization rules for paths, names, case, separators, suffixes like "(1)"
  - Dedupe strategy and identity rules (SHA-256 hash primary; size/name fallback)
  - Example: "Football_Holder.3mf" vs "football holder-3MF" vs "Football_Holder (1).3mf" — all same identity
- **Acceptance criteria**:
  - Doc is complete and referenced in #1075, #1076
  - Normalization rules passed team review
  - Identity strategy locked in
- **Owner**: Design/spec
- **GitHub**: [#1074](https://github.com/rsocko/hass-bambulab-config/issues/1074)
- **Deliverable**: `docs/features/model_catalog/working-file-spec.md`

#### 3️⃣ #1079: Define intake flow states + transitions
- **Effort**: 1.5 days (spec writing)
- **Blocker for**: #1130, #1080, #1077, #1082
- **What it delivers**:
  - State machine diagram: `discovered → grouped → ready-to-curate → grouped-to-working → curated-publish`
  - Per-state metadata requirements and what sidecar/HA actions occur
  - Transition logic: when can an item move between states, who triggers it
  - Validation rules per state
- **Acceptance criteria**:
  - State diagram is complete and unambiguous
  - Metadata requirements per state are locked
  - Transition logic passes team review
- **Owner**: Design/spec
- **GitHub**: [#1079](https://github.com/rsocko/hass-bambulab-config/issues/1079)
- **Deliverable**: `docs/features/model_catalog/intake-state-machine.md`

---

### **WAVE 2: Sidecar Backend Foundation (Days 4–10)**

Implement the core sidecar data model, indexing, and API endpoints. These are the engine for all later HA UI work.

#### 4️⃣ #1075: Sidecar indexing job for working files
- **Effort**: 2–3 days (implementation)
- **Dependency**: #1059, #1074 (specs locked)
- **Blocker for**: #1076, #1130
- **What it delivers**:
  - Sidecar job that scans configured roots (`/assets/model inbox`, `/assets/working`, etc.)
  - Incremental indexing via timestamp + hash (rescan only if mtime or size changed)
  - SQLite schema for `working_files` inventory
  - Endpoints to query by name, path, type, hash
  - No UI wiring yet — just backend index
- **Acceptance criteria**:
  - Can scan a ~500 file directory
  - Incremental updates work correctly
  - Hash collisions are detected
  - `GET /api/working-files?name=football` returns results
- **Tests**: Unit tests for hash logic, incremental update, query endpoints
- **GitHub**: [#1075](https://github.com/rsocko/hass-bambulab-config/issues/1075)
- **Deliverable**:
  - `sidecars/model_catalog/app/models/working_file.py` (schema)
  - `sidecars/model_catalog/app/jobs/index_working_files.py` (job)
  - `sidecars/model_catalog/app/routers/working_files.py` (endpoints)

#### 5️⃣ #1076: Working groups and veneer mapping schema/API
- **Effort**: 2–3 days (implementation)
- **Dependency**: #1074 (specs locked), #1075 (working_files index complete)
- **Blocker for**: #1130, #1080, #1077
- **What it delivers**:
  - SQLite schema for `working_groups`, `working_group_items` (files attached to groups)
  - Schema for `working_group_to_model_links` (veneer mapping to curated models)
  - CRUD endpoints:
    - `POST /api/working-groups` (create group)
    - `GET /api/working-groups` (list)
    - `GET /api/working-groups/{group_id}` (detail)
    - `PATCH /api/working-groups/{group_id}` (update metadata)
    - `DELETE /api/working-groups/{group_id}` (delete)
    - `POST /api/working-groups/{group_id}/items` (attach file)
    - `DELETE /api/working-groups/{group_id}/items/{file_id}` (detach file)
  - Link endpoints:
    - `POST /api/working-groups/{group_id}/links` (link to curated model)
    - `GET /api/working-groups/{group_id}/links`
    - `DELETE /api/working-groups/{group_id}/links/{link_id}` (unlink)
- **Acceptance criteria**:
  - Can create, read, update, list working groups
  - Can attach/detach files
  - Can create and manage links to curated models
  - Deduplication warnings are attached to attachment attempts
- **Tests**: Unit tests for CRUD logic, link creation, dedupe detection
- **GitHub**: [#1076](https://github.com/rsocko/hass-bambulab-config/issues/1076)
- **Deliverable**:
  - `sidecars/model_catalog/app/models/working_group.py` (schema + models)
  - `sidecars/model_catalog/app/routers/working_groups.py` (endpoints)

#### 6️⃣ #1144: Implement sidecar upload queue API and persistence state machine
- **Effort**: 2–3 days (implementation)
- **Dependency**: #1074 (specs locked)
- **Blocker for**: #1130, #1080
- **What it delivers**:
  - SQLite schema for `upload_queue` with state machine: `queued → uploading → uploaded_unverified → verified → cleanup_pending → cleanup_done`
  - Queue entry endpoints:
    - `POST /api/upload-queue/submit` (add item to queue)
    - `GET /api/upload-queue` (list queue items)
    - `GET /api/upload-queue/{item_id}` (get queue item detail)
  - State transitions:
    - Verify uploaded file via hash
    - Mark verification complete
    - Schedule cleanup if policy is enabled
  - Multipart upload support for browser-based file ingestion
- **Acceptance criteria**:
  - Can submit files to queue from browser
  - Queue state transitions correctly
  - Hash verification works
  - Cleanup can be deferred or executed
- **Tests**: Unit tests for queue state machine, upload/verify flow
- **GitHub**: [#1144](https://github.com/rsocko/hass-bambulab-config/issues/1144)
- **Deliverable**:
  - `sidecars/model_catalog/app/models/upload_queue.py` (schema + state machine)
  - `sidecars/model_catalog/app/routers/upload_queue.py` (endpoints)

#### 7️⃣ #1147: Implement sidecar server-filesystem browse/select with allowlisted roots
- **Effort**: 2 days (implementation)
- **Dependency**: #1074, #1075 (specs and indexing complete)
- **Blocker for**: #1130, #1080
- **What it delivers**:
  - Browse endpoints for navigating allowlisted filesystem roots
  - `GET /api/filesystem/roots` — list configured roots
  - `GET /api/filesystem/browse?root=model-inbox&path=subfolder` — browse children of path
  - `POST /api/filesystem/select` — submit selected path(s) to intake queue
  - Security: only expose configured allowlisted roots; no path traversal escape
- **Acceptance criteria**:
  - Can browse `/assets/model inbox` and subdirectories
  - Can select files/folders and submit them to intake queue
  - Path traversal attempts are blocked
- **Tests**: Unit tests for path validation, security checks
- **GitHub**: [#1147](https://github.com/rsocko/hass-bambulab-config/issues/1147)
- **Deliverable**:
  - `sidecars/model_catalog/app/routers/filesystem.py` (endpoints)

#### 8️⃣ #1080: Sidecar workflow endpoints for intake + batch actions
- **Effort**: 2–3 days (implementation)
- **Dependency**: #1075, #1076, #1144 (backend models complete)
- **Blocker for**: #1130, #1082
- **What it delivers**:
  - `POST /api/intake/submit` — submit files/folders to intake queue
  - `GET /api/intake/items` — list intake queue items
  - `POST /api/intake/items/{item_id}/validate` — validate single item (dedup check, type check)
  - `POST /api/intake/items/{item_id}/group` — convert intake item to working group
  - `POST /api/intake/bulk-discover` — scan folder and propose groups
  - `POST /api/intake/bulk-import` — import reviewed proposals as working groups
  - Batch endpoints for multi-item operations
- **Acceptance criteria**:
  - Can submit one file to intake
  - Validation detects duplicates
  - Can create working group from intake item
  - Can bulk discover a folder with 50+ files
- **Tests**: Integration tests for full intake workflow
- **GitHub**: [#1080](https://github.com/rsocko/hass-bambulab-config/issues/1080)
- **Deliverable**:
  - `sidecars/model_catalog/app/routers/intake.py` (endpoints)
  - `sidecars/model_catalog/app/services/intake_service.py` (business logic)

---

### **WAVE 3: Intake & Discovery (Days 11–15)**

Implement the core workflow endpoints that tie together indexing, queue, and working groups.

#### 9️⃣ #1042: Deduplicate re-downloads and imported model collisions
- **Effort**: 1–2 days (implementation)
- **Dependency**: #1074, #1075, #1076 (specs and backend)
- **What it delivers**:
  - Dedupe logic integrated into #1080 intake workflow
  - Detects file hash collisions against:
    - Existing working files index
    - Already-grouped files
    - Queue items
  - Returns warnings to operator before commit
  - Offers choices: create anyway, merge into existing group, skip
- **Acceptance criteria**:
  - Can detect when same file is re-downloaded with different name
  - Collision warnings are surfaced to operator
  - Operator can choose merge or skip
- **Tests**: Dedupe logic tests with fixture files
- **GitHub**: [#1042](https://github.com/rsocko/hass-bambulab-config/issues/1042)
- **Deliverable**:
  - Integrated into `app/services/intake_service.py`

#### 🔟 #1130: Bulk Discovery and Import
- **Effort**: 2–3 days (implementation + HA wiring)
- **Dependency**: #1080, #1042 (intake endpoints complete)
- **What it delivers**:
  - `POST /api/working-groups/bulk-discover` endpoint (core logic)
  - `POST /api/working-groups/bulk-import` endpoint (batch create)
  - HA services for bulk discover/import
  - Basic HA card for reviewing proposed groups before import
  - Operator can rename, merge, or skip groups
  - End-to-end test with ~50 file scenario
- **Acceptance criteria**:
  - Can discover folder with 50+ files
  - Proposals appear in HA card
  - Can import reviewed proposals without duplicates
  - Bulk import handles 500+ file scenario correctly
- **Tests**: Integration tests with fixture file set
- **GitHub**: [#1130](https://github.com/rsocko/hass-bambulab-config/issues/1130)
- **Deliverable**:
  - Sidecar endpoints (core logic via #1080)
  - HA services: `model_catalog.bulk_discover_working_groups`, `model_catalog.bulk_import_working_groups`
  - HA card: `homeassistant/packages/model_catalog/cards/bulk_import_review.yaml`

---

### **WAVE 4: HA Integration — Working Groups & UI (Days 16–20)**

Build the HA UI surfaces that operators use to interact with working groups and intake.

#### 1️⃣1️⃣ #1077 (HA component): HA UI - working groups and link management
- **Effort**: 2–3 days (HA UI)
- **Dependency**: #1080 (sidecar endpoints complete)
- **Blocker for**: #1082
- **What it delivers**:
  - HA service `model_catalog.create_working_group` (simple wrapper)
  - HA service `model_catalog.update_working_group` (metadata updates)
  - HA service `model_catalog.attach_file_to_group` (file attach)
  - HA UI card showing working groups list
  - Detail popup for each working group (files, links, metadata)
  - Link management UI (add/remove curated model links)
  - Quick-open actions (open folder, open primary file)
- **Acceptance criteria**:
  - Can see all working groups in card
  - Can view group detail (files, links)
  - Can attach/detach files via UI
  - Can create/delete links via UI
- **GitHub**: [#1077](https://github.com/rsocko/hass-bambulab-config/issues/1077)
- **Deliverable**:
  - HA custom component services
  - HA cards: `homeassistant/packages/model_catalog/cards/working_groups_board.yaml`, `working_group_detail.yaml`

#### 1️⃣2️⃣ #1082: HA UI actions for curation workflows
- **Effort**: 2 days (HA UI)
- **Dependency**: #1076 (HA working groups UI complete)
- **What it delivers**:
  - HA UI buttons/actions for batch operations
  - Intake entry points from working group views
  - Batch selection (multi-select working groups)
  - Batch actions (convert to curated, mark for publish, etc.)
  - Clear feedback for success/failure
  - Progress indicators for long-running operations
- **Acceptance criteria**:
  - Can batch-select working groups
  - Can trigger batch actions
  - Feedback is clear (success/fail/partial)
- **GitHub**: [#1082](https://github.com/rsocko/hass-bambulab-config/issues/1082)
- **Deliverable**:
  - HA cards with batch UI: `homeassistant/packages/model_catalog/cards/batch_actions.yaml`

#### 1️⃣3️⃣ #1145: Update HA Model Catalog UI/services for source mode, queue, and cleanup policy
- **Effort**: 1–2 days (HA config)
- **Dependency**: #1144, #1147 (queue and browser complete)
- **What it delivers**:
  - HA service `model_catalog.set_upload_source` (drag-drop, file-picker, server-browse, stream-deck)
  - HA service `model_catalog.set_cleanup_policy` (keep, delete_on_verified, replace_with_stub)
  - HA input helpers for configuration:
    - `input_select.model_catalog_upload_source_mode`
    - `input_select.model_catalog_cleanup_policy`
  - HA dashboard card for intake configuration
- **Acceptance criteria**:
  - Can set upload source mode
  - Can set cleanup policy
  - Settings persist
- **GitHub**: [#1145](https://github.com/rsocko/hass-bambulab-config/issues/1145)
- **Deliverable**:
  - HA services and helpers
  - HA configuration card: `homeassistant/packages/model_catalog/cards/intake_config.yaml`

---

### **WAVE 5: Publish Workflow Prep & Supporting Docs (Days 21–25)**

Lay groundwork for Phase 6 publish workflow. Document operations and deployment.

#### 1️⃣4️⃣ #1163 + #1137: Phase 5 3MF Publish Workflow — Preview Promotion & Supporting-Asset Import
- **Effort**: 1 day (spec only; implementation in Phase 6)
- **Dependency**: None (can be parallel)
- **What it delivers**:
  - Design doc for publish workflow behavior
  - How to promote extracted 3MF preview as curated preview
  - Which supporting assets (PDFs, STLs, images) to attach on publish
  - Publish-time conflict resolution (new revision vs add file vs keep separate)
- **Acceptance criteria**:
  - Design is documented and approved
  - Ready for Phase 6 implementation
- **GitHub**: [#1163](https://github.com/rsocko/hass-bambulab-config/issues/1163), [#1137](https://github.com/rsocko/hass-bambulab-config/issues/1137)
- **Deliverable**: `docs/features/model_catalog/publish-workflow-3mf.md`

#### 1️⃣5️⃣ #1132 + #1133: Working Groups And Working Veneer (Enhanced) + Publish Workflow And Revision Lineage
- **Effort**: 1 day (spec only; implementation deferred)
- **Dependency**: #1076 (working groups exist)
- **What it delivers**:
  - Enhanced working group data model (provisional; deferred to Phase 6)
  - Publish workflow state machine (to be implemented in Phase 6)
  - Revision lineage design (deferred to Phase 6)
- **Acceptance criteria**:
  - Design is documented
  - Ready as Phase 6 baseline
- **GitHub**: [#1132](https://github.com/rsocko/hass-bambulab-config/issues/1132), [#1133](https://github.com/rsocko/hass-bambulab-config/issues/1133)
- **Deliverable**: `docs/features/model_catalog/working-groups-enhanced.md`

#### 1️⃣6️⃣ #1149: Add deployment docs and validation plan for queue volume + remote-client intake flows
- **Effort**: 1–2 days (ops docs)
- **Dependency**: #1080, #1144, #1147 (features complete)
- **What it delivers**:
  - Deployment guide for queue volume sizing
  - Remote-client intake flow documentation (Streamdeck, network paths, etc.)
  - Testing validation checklist for 500+ file scenarios
  - Performance expectations and tuning guidance
- **Acceptance criteria**:
  - Deployment docs are complete
  - Can scale to 500+ files without issues
  - Remote-client flows are documented
- **GitHub**: [#1149](https://github.com/rsocko/hass-bambulab-config/issues/1149)
- **Deliverable**: `docs/features/model_catalog/DEPLOYMENT-INTAKE-GUIDE.md`

#### 1️⃣7️⃣ #1146: Add optional post-upload source cleanup policy with safety guardrails
- **Effort**: 1 day (spec + implementation)
- **Dependency**: #1144 (queue state machine)
- **What it delivers**:
  - Cleanup policy options: `keep` (default), `delete_on_verified`, `replace_with_stub`
  - Safety guardrails: only for allowlisted roots, requires verification before cleanup
  - Audit trail for cleanup actions
  - HA UI for policy selection
- **Acceptance criteria**:
  - Policy can be set and persisted
  - Cleanup only happens after verification
  - Audit log exists
- **GitHub**: [#1146](https://github.com/rsocko/hass-bambulab-config/issues/1146)
- **Deliverable**: 
  - Integrated into #1144
  - HA service: `model_catalog.set_source_cleanup_policy`

#### 1️⃣8️⃣ #213: Import existing local model library from OneDrive
- **Effort**: 0.5–1 day (proof-of-concept)
- **Dependency**: #1130, #1147 (bulk import complete)
- **What it delivers**:
  - Proof-of-concept integration with OneDrive API (or local sync folder)
  - One-time bulk import of existing library
  - Documents the workflow for operators
- **Acceptance criteria**:
  - Can import 100+ files from OneDrive successfully
  - All files end up as working groups
  - Duplicate detection works correctly
- **GitHub**: [#213](https://github.com/rsocko/hass-bambulab-config/issues/213)
- **Deliverable**: `docs/features/model_catalog/ONEDRIVE-IMPORT-GUIDE.md`

---

## Validation Gates by Wave

### Wave 1 Completion Gate
- [x] All three spec documents are complete and reviewed
- [x] Team agrees on state machine, file normalization, and indexing strategy
- [x] No blocking unknowns remain for Wave 2

### Wave 2 Completion Gate
- [ ] All sidecar endpoints exist and are tested
- [ ] Indexing scales to 500+ files
- [ ] Working group CRUD works
- [ ] Upload queue state machine is validated
- [ ] No integration issues identified

### Wave 3 Completion Gate
- [ ] Dedupe logic catches collision scenarios
- [ ] Bulk discovery works with 50+ file set
- [ ] Bulk import creates all groups without orphans
- [ ] No file-loss or corruption issues

### Wave 4 Completion Gate
- [ ] HA can see all working groups
- [ ] Operators can perform all basic actions (create, attach, link)
- [ ] Batch operations work correctly
- [ ] UI feedback is clear

### Wave 5 Completion Gate
- [ ] Publish workflow is spec'd and ready for Phase 6
- [ ] Deployment guide is complete
- [ ] OneDrive import works (PoC)
- [ ] All 20 issues are closure-ready or deferred with clear rationale

---

## Risk Mitigation

### High-Risk Items

1. **File-loss during bulk import** → Mitigate with extensive fixture testing and hash verification before any destructive operations
2. **Deduplication false positives** → Extensive collision detection tests; operator always shown warnings before commit
3. **Performance degradation at 500+ files** → Validate indexing early (Wave 1); optimize queries if needed
4. **State machine complexity** → Lock state machine design early (Wave 1); keep transitions well-documented

### Recommended Checkpoints

- **Day 10 (end of Wave 2)**: Code review of all sidecar endpoints; integration smoke test
- **Day 15 (end of Wave 3)**: 500-file scenario test; dedupe validation with real files
- **Day 20 (end of Wave 4)**: Full end-to-end workflow test (file upload → intake review → group creation → HA view)

---

## Success Criteria for Phase 5

- [ ] Files can be discovered from filesystem and proposed as groups
- [ ] Files can be uploaded via browser or server-browse
- [ ] Duplicates are detected and operator is warned before commit
- [ ] Intake items can be converted to working groups without errors
- [ ] Working groups visible and manageable in HA
- [ ] Batch operations work correctly at 100+ item scale
- [ ] 500+ file scenario completed without orphan duplicates
- [ ] Documentation is complete and tested with real scenario
- [ ] All 20 issues are closed or deferred with clear Phase 6 mapping

---

## Relationship to Other Phases

- **Phase 1–4**: Already complete (sidecar scaffold, archive linking, UI foundational work)
- **Phase 5 INPUT**: Sidecar running, archive endpoints working, HA integration points available
- **Phase 5 OUTPUT**: Working groups exist; intake workflow functional; ready for publish workflow (Phase 6)
- **Phase 6 INPUT**: Working groups from Phase 5; ready to build publish-to-curated flow
- **Phase 6 OUTPUT**: Publish workflow; curated catalog enrichment; ranking

---

## Issue Closure Mapping

| Issue | Closure Status | Phase 6 Dependency |
|-------|---|---|
| #1059 | ✅ Closed | N/A |
| #1074 | ✅ Closed | N/A |
| #1079 | ✅ Closed | N/A |
| #1075 | ✅ Closed | N/A |
| #1076 | ✅ Closed | N/A |
| #1080 | ✅ Closed | N/A |
| #1144 | ✅ Closed | N/A |
| #1147 | ✅ Closed | N/A |
| #1042 | ✅ Closed | N/A |
| #1130 | ✅ Closed | N/A |
| #1077 | ✅ Closed | N/A |
| #1082 | ✅ Closed | N/A |
| #1145 | ✅ Closed | N/A |
| #1163 | 🔄 Deferred | Phase 6 |
| #1137 | 🔄 Deferred | Phase 6 |
| #1132 | 🔄 Deferred | Phase 6 |
| #1133 | 🔄 Deferred | Phase 6 |
| #1149 | ✅ Closed | N/A |
| #1146 | ✅ Closed | N/A |
| #213 | ✅ Closed (PoC) | Optional Phase 6 follow-on |

