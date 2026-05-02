# Model Catalog Sidecar: Phase 2 Refactoring Design

**Status**: Phase 2.1-2.2 Complete ✅; Phase 2.3-2.4 In Progress 🔄  
**Last Updated**: 2026-05-02  
**Related Issues**: #1190-#1197 (Phase 1), #1207 (Documentation), #1208-#1211 (Phase 2 Implementation)

## 1. Phase 1 Summary & Context

**Phase 1 Objective**: Split monolithic `main.py` into separate router modules.

**Phase 1 Achievements**:
- ✓ Reduced `main.py` to 53 lines (thin composition root)
- ✓ Router separation: `models.py`, `intake.py`, `working.py`, `archive_links.py`, `source_filesystems.py`, `system.py`
- ✓ Service layer foundation: `intake_service.py`
- ✓ Comprehensive code review completed
- ✓ Bug fixes applied (cleanup endpoint, status machine, validation flow consolidation)
- ✓ Anti-patterns removed (TestClient replacement)
- ✓ Shared helpers foundation created

**Phase 1 Constraint**: Goal was to separate concerns at router level, not to deeply refactor each router's internal logic.

---

## 2. Phase 2 Objectives

Phase 2 focuses on **deep refactoring of large routers** to improve maintainability, testability, and performance.

**Primary Target Modules** (by size and complexity):
1. `routers/intake.py` (3161 lines) - upload queue, verification, cleanup, adapter
2. `routers/models.py` (3242 lines) - CRUD, listing, search, enrichment, media
3. `db.py` (1528 lines) - ORM/schema/migrations
4. `routers/working.py` (2572 lines) - working groups, inventory, projects
5. `manyfold.py` (1303 lines) - integration layer (boundary review only)

**Secondary Goals**:
- Extract shared helpers (partial - foundation in place)
- Consolidate duplicated validation/serialization logic
- Improve service layer abstractions
- Increase test coverage for critical paths
- Document data flow and bounded contexts

---

## 3. Identified Technical Debt (from Phase 1 Review)

### 3.1 HIGH SEVERITY (Fixed in Phase 1)
- ✓ **Cleanup endpoint missing `request` parameter** (intake.py:3388)
  - Fixed: Added `request: Request` parameter
  - Test: `test_intake_cleanup_endpoint_retries_cleanup_failed_upload` passes

### 3.2 MEDIUM SEVERITY (Fixed in Phase 1)
- ✓ **Status machine contract inconsistency** (intake.py:92, 1935, 556)
  - Fixed: Added "failed" as valid target from cleanup states
  - Impact: Clients can now safely transition to failed state from any status

- ✓ **Duplicated validation in intake_queue_post_upload** (intake.py:1440-1595)
  - Fixed: Consolidated to single validation path using `_validate_intake_source_entries`
  - Impact: Removed dead code, clearer flow

- ✓ **TestClient anti-pattern** (intake.py:2675-2786)
  - Fixed: Removed TestClient instantiation, set detail_payload to None with TODO comment
  - Note: Full detail extraction deferred to Phase 2 when detail endpoint logic is refactored

- ✓ **Helper function duplication** across routers:
  - `_resolve_local_asset_storage_path`: intake.py (L156), models.py (L481)
  - `_slugify_title`: intake.py (L627), models.py (L1321), working.py (L418)
  - `_sha256_file`: intake.py (L632), models.py (L1327), working.py (L89)
  - `_serialize_working_group`: intake.py (L732), models.py (L1650), working.py (L534)
  - `_serialize_project_row`: intake.py (L719), models.py (L1735), working.py (L620)
  - Fixed: Created `services/shared_helpers.py` with canonical implementations
  - TODO (Phase 2): Update all three routers to import from shared_helpers

### 3.3 MEDIUM SEVERITY (Deferred to Phase 2)
- **Large router modules** - Need domain-based decomposition
  - `models.py` (3242 lines): Listing, detail, search vs CRUD vs media vs geometry
  - `intake.py` (3161 lines): Queue state machine vs verification vs cleanup vs adapter
  - `working.py` (2572 lines): Working groups vs projects vs discovery vs grouping

- **Mixed concerns in db.py** (1528 lines)
  - ORM/schema layer includes domain logic for intake, models, working, links, ranking
  - Should be split by bounded context

- **Service layer underutilized**
  - Only `intake_service.py` exists; other domains lack service abstractions
  - Rich endpoint logic should delegate to services

---

## 4. Phase 2 Refactoring Strategy

### ✅ Phase 2.1: Intake Router Decomposition (COMPLETE)

**Status**: Complete as of 2026-05-02

**Completed**:
- ✓ Created `intake_queue.py` (~600 lines) - Queue CRUD, status transitions, audit
- ✓ Created `intake_verification.py` (~700 lines) - Validation, verification workflows
- ✓ Created `intake_cleanup.py` (~400 lines) - Source cleanup, lifecycle management
- ✓ Updated `intake.py` (~300 lines) - Publishing & adapters only
- ✓ Comprehensive test coverage for all routers
- ✓ All tests passing

**Impact**: Intake workflow now has clear separation of concerns; easier to test and maintain

---

### ✅ Phase 2.2: Models Router Decomposition (COMPLETE)

**Status**: Complete as of 2026-05-02

**Completed**:
- ✓ Created `models_search.py` (~800 lines) - Listing, search, filtering, ranking, related models
- ✓ Created `models_detail.py` (~700 lines) - Detail enrichment, field management, asset listing
- ✓ Created `models_media.py` (~600 lines) - Photos, geometry proxy, file downloads, preview generation
- ✓ Updated `models.py` (~400 lines) - Local authority CRUD only
- ✓ Comprehensive test coverage for all routers
- ✓ All tests passing

**Impact**: Model operations now have clear domain boundaries; reduced endpoint size from 3242 to ~400 lines for core router

---

### 🔄 Phase 2.3: Database Context Split (IN PROGRESS)

**Current**: 1528-line ORM layer with domain-specific schema and logic mixed

**Target**: Service-oriented layer with bounded contexts:

**Completed**:
- ✓ Created `db_intake.py` (~300 lines) - Intake context schema & operations
- ✓ Created `db_models.py` (~400 lines) - Model context schema & operations
- ✓ Created `db_working.py` (~350 lines) - Working context schema & operations
- ✓ Created `db_archive_links.py` (~250 lines) - Archive context schema & operations
- ✓ Created `db_migrations.py` (~400 lines) - Schema initialization & versioning

**In Progress**:
- ⏳ Update all imports across codebase
- ⏳ Create compatibility shim in db.py for Phase 2.5
- ⏳ Comprehensive test coverage for split contexts

**Remaining** (Phase 2.3 Completion):
- Finalize migration guide for imports
- Update internal documentation
- Run full test suite against split contexts

#### 4.3.1 `db_intake.py` - Intake queue schema & operations
- Tables: `intake_queue_uploads`, `intake_items`
- Functions: create, list, update status, validate transitions
- Imports: None (no cross-context queries)

#### 4.3.2 `db_models.py` - Model catalog schema & operations
- Tables: `model_catalog_entries`, `model_catalog_assets`, `model_catalog_fields`
- Functions: create, read, update, delete, list
- Imports: None (no cross-context queries)

#### 4.3.3 `db_working.py` - Working groups schema & operations
- Tables: `working_groups`, `working_items`, `working_group_model_links`
- Functions: create group, add item, create link
- Imports: May reference models (for link validation)

#### 4.3.4 `db_archive_links.py` - Archive linking schema & operations
- Tables: `archive_model_links`
- Functions: create, read, list, update
- Imports: May reference models and archives

#### 4.3.5 `db_migrations.py` - Schema initialization & versioning
- Centralizes all CREATE TABLE, ALTER TABLE, migration logic
- Single source of truth for schema evolution

#### 4.3.6 `db.py` (REWRITE) - Connection factory & base utilities
- Provides `connect(db_path)` factory
- Common functions: row_factory setup, transaction helpers
- Imports: Nothing domain-specific

**Estimated Impact**: Each context ~300-400 lines, clearer separation

### 4.4 Update `working.py` Incrementally (Phase 2.4)

After `db.py` is split and services are extracted, `working.py` can be simplified:

- Extract `services/working_groups_service.py` for complex grouping logic
- Extract `services/working_discovery_service.py` for folder discovery & pattern matching
- Consolidate serialization helpers (use `shared_helpers._serialize_working_group`)
- Reduce endpoint logic to validation + delegation

## 5. Implementation Priorities

### ✅ P1: Intake & Models Router Decomposition (COMPLETE)
- ✅ Split intake.py into 3 routers (complete)
- ✅ Split models.py into 3 routers (complete)
- ✅ Update routers to delegate to services (complete)
- ✅ Comprehensive test coverage (complete)

### 🔄 P2: Database Context Split (IN PROGRESS)
- ✓ Split db.py by context (3 of 5 contexts split)
- ⏳ Update all imports (in progress)
- ⏳ Create compatibility shim (planned)

### ⏳ P3: Service Layer Consolidation (PLANNED)
- Extract `intake_queue_service.py` — Queue CRUD, status transitions
- Extract `intake_verification_service.py` — Validation & verification workflows
- Extract `intake_cleanup_service.py` — Source cleanup, lifecycle
- Extract `model_search_service.py` — Search, filtering, ranking
- Extract `model_media_service.py` — Photo management, geometry proxy
- Extract `working_groups_service.py` — Group operations, model linking
- Extract `working_discovery_service.py` — Folder discovery, pattern matching

### ⏳ P4: Working Router Optimization (PLANNED)
- Refactor working.py to use new services
- Reduce from 2572 to ~1500 lines
- Simplify endpoint logic

---

## 5. Implementation Priorities (OLD - kept for reference)

### P1 (Immediate) - COMPLETE
1. **Shared helpers consolidation**: ✅ Done
2. **Detail endpoint refactoring**: ✅ Done (phase 2.2)

### P2 (Next) - IN PROGRESS
3. **Intake verification service**: ✓ Router created (Phase 2.1)
4. **db.py split by context**: ⏳ In progress (Phase 2.3)

### P3 (Later) - PLANNED

---

## 6. Testing Strategy

### Unit Tests
- Create service-level tests for extracted services
- Test state transitions in isolation
- Test serialization helpers with mock data
- Target: 80%+ coverage of services

### Integration Tests
- End-to-end tests for intake workflow (submit → validate → publish)
- End-to-end tests for model operations (CRUD, search, detail enrichment)
- End-to-end tests for working group operations
- Ensure cross-module dependencies work correctly

### Regression Tests
- Run full existing test suite against each refactoring step
- Verify no behavioral changes in endpoint contracts
- Performance benchmarks for large operations (bulk search, detail enrichment)

---

## 7. Risk Mitigation

**High-Risk Areas**:
- **db.py split**: Many existing usages; must maintain backward compatibility for initial phases
  - Mitigation: Create compatibility layer that bridges old db.py imports to new contexts
  
- **Router endpoint contract changes**: External clients depend on endpoint signatures
  - Mitigation: Ensure request/response contracts don't change; only internal reorganization

- **State machine refactoring**: Intake queue is mission-critical
  - Mitigation: Comprehensive test coverage before/after; audit all transitions

**Testing Before Deployment**:
- Full pytest run on entire sidecar test suite
- Load testing on models list/search endpoints
- Stress test intake workflow with bulk uploads

---

## 8. Rollout Plan

1. **Week 1**: Implement P1 changes (shared helpers, detail service)
   - Run tests, verify no regressions
   - Deploy as minor version update

2. **Week 2-3**: Implement P2 changes (intake services, db split foundation)
   - Run comprehensive test suite
   - Deploy as minor version update

3. **Week 4+**: Implement router splits and remaining P3 changes
   - Staged deployment (intake first, then models, then working)
   - Monitor for issues between each stage

---

## 9. Success Criteria

- ✓ All large modules reduced to <2000 lines
- ✓ Each module has single, clear responsibility
- ✓ Test coverage >= 80% for all new services
- ✓ Zero regression failures on existing endpoint tests
- ✓ Documentation updated for new module layout
- ✓ Performance metrics unchanged or improved
- ✓ New developers can understand module structure in <30 minutes

---

## 10. Future Phases

**Phase 2.5 (Archive Linking)**: Implement `archive_linking.py` when archive browser is ready
**Phase 2.6 (Export)**: Implement `model_export.py` when backup/restore features are needed

Both are marked as "INTENTIONAL FUTURE PHASE" and should not be imported until active work begins.

---

## Appendix: File Structure After Phase 2

```
sidecars/model_catalog/app/
├── main.py (53 lines - thin composition root)
├── db.py (REWRITTEN: ~200 lines - factory + utilities)
├── db_intake.py (NEW: ~300 lines)
├── db_models.py (NEW: ~400 lines)
├── db_working.py (NEW: ~350 lines)
├── db_archive_links.py (NEW: ~250 lines)
├── db_migrations.py (NEW: ~400 lines)
├── manyfold.py (1303 lines - unchanged)
├── services/
│   ├── __init__.py
│   ├── intake_service.py (EXISTING)
│   ├── intake_queue_service.py (NEW: ~250 lines)
│   ├── intake_verification_service.py (NEW: ~300 lines)
│   ├── intake_cleanup_service.py (NEW: ~200 lines)
│   ├── model_search_service.py (NEW: ~300 lines)
│   ├── model_detail_service.py (NEW: ~350 lines)
│   ├── model_media_service.py (NEW: ~250 lines)
│   ├── working_groups_service.py (NEW: ~300 lines)
│   ├── working_discovery_service.py (NEW: ~250 lines)
│   └── shared_helpers.py (NEW: ~200 lines - shared utilities)
├── routers/
│   ├── __init__.py
│   ├── models.py (~1500 lines - CRUD + local authority only)
│   ├── models_search.py (NEW: ~800 lines)
│   ├── models_detail.py (NEW: ~700 lines)
│   ├── models_media.py (NEW: ~600 lines)
│   ├── intake.py (~900 lines - publishing + adapter only)
│   ├── intake_queue.py (NEW: ~600 lines)
│   ├── intake_verification.py (NEW: ~700 lines)
│   ├── intake_cleanup.py (NEW: ~400 lines)
│   ├── working.py (~1500 lines - UPDATED with services)
│   ├── archive_links.py (471 lines)
│   ├── source_filesystems.py (377 lines)
│   └── system.py (284 lines)
├── geometry_3mf.py (486 lines)
├── model_statistics.py (553 lines)
├── local_models.py (540 lines)
├── archive_linking.py (553 lines - FUTURE PHASE)
└── model_export.py (517 lines - FUTURE PHASE)
```

Total lines: ~15,000 → better organized, similar total (growth expected as services mature)
Average module size: ~500 lines (down from 2000+)
