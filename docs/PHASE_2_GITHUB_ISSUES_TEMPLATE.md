# GitHub Issues for Phase 2 Model Catalog Refactoring

This file contains issue templates that should be created in GitHub for Phase 2 work.

---

## Epic: Phase 2.1 - Intake Router Decomposition

**Title**: Phase 2.1: Split intake.py by workflow - Queue, Verification, Cleanup

**Labels**: `refactoring`, `technical-debt`, `model_catalog`, `phase-2`

**Description**:

Split the monolithic `intake.py` router (3161 lines) into focused workflow modules:

### Acceptance Criteria
- [ ] Create `routers/intake_queue.py` for queue state machine (~600 lines)
  - POST /api/intake/uploads - create
  - GET /api/intake/uploads/{upload_id} - read
  - PUT /api/intake/uploads/{upload_id}/status - transition
  - DELETE /api/intake/uploads/{upload_id} - delete
- [ ] Create `routers/intake_verification.py` for verification workflow (~700 lines)
  - POST /api/intake/items/{item_id}/validate
  - POST /api/intake/items/{item_id}/defer
  - POST /api/intake/items/{item_id}/reject
  - POST /api/intake/items/{item_id}/group
- [ ] Create `routers/intake_cleanup.py` for cleanup operations (~400 lines)
  - POST /api/intake/uploads/{upload_id}/cleanup
- [ ] Extract services: `intake_queue_service.py`, `intake_verification_service.py`, `intake_cleanup_service.py`
- [ ] Update main router registration to include new routers
- [ ] Run full test suite - all intake tests pass
- [ ] Update documentation for new structure
- [ ] Zero regression failures on existing intake endpoints

### Related Files
- `sidecars/model_catalog/app/routers/intake.py` (3161 lines → split)
- `sidecars/model_catalog/app/services/intake_queue_service.py` (NEW)
- `sidecars/model_catalog/app/services/intake_verification_service.py` (NEW)
- `sidecars/model_catalog/app/services/intake_cleanup_service.py` (NEW)

### Dependency
- Depends on: Phase 1 bug fixes (cleanup endpoint, status machine, validation consolidation)

---

## Epic: Phase 2.2 - Models Router Decomposition

**Title**: Phase 2.2: Split models.py by domain - Search, Detail, Media

**Labels**: `refactoring`, `technical-debt`, `model_catalog`, `phase-2`

**Description**:

Split the monolithic `models.py` router (3242 lines) into domain-focused modules:

### Acceptance Criteria
- [ ] Create `routers/models_search.py` for listing and search (~800 lines)
  - GET /api/models - list all
  - GET /api/models/search - search
  - GET /api/models/{model_ref}/related - related models
  - GET /api/models/{model_ref}/ranking - ranking data
- [ ] Create `routers/models_detail.py` for detail and enrichment (~700 lines)
  - GET /api/models/{model_ref}/detail
  - GET /api/models/{model_ref}/fields
  - PUT /api/models/{model_ref}/fields/{field_key}
  - DELETE /api/models/{model_ref}/fields/{field_key}
- [ ] Create `routers/models_media.py` for media and geometry (~600 lines)
  - POST /api/models/{model_ref}/photos
  - GET /api/models/{model_ref}/photos/{photo_id}/content
  - DELETE /api/models/{model_ref}/photos/{photo_id}
  - GET /api/models/{model_ref}/geometry/{file_id}
  - GET /api/models/{model_ref}/files/{file_id}/download
- [ ] Extract services: `model_search_service.py`, `model_detail_service.py`, `model_media_service.py`
- [ ] Keep local model CRUD in `models.py`
- [ ] Update main router registration
- [ ] Run full test suite - all model tests pass
- [ ] Zero regression failures on existing model endpoints

### Related Files
- `sidecars/model_catalog/app/routers/models.py` (3242 lines → split)
- `sidecars/model_catalog/app/services/model_search_service.py` (NEW)
- `sidecars/model_catalog/app/services/model_detail_service.py` (NEW)
- `sidecars/model_catalog/app/services/model_media_service.py` (NEW)

---

## Epic: Phase 2.3 - Database Layer Reorganization

**Title**: Phase 2.3: Split db.py by bounded context - Intake, Models, Working, Links

**Labels**: `refactoring`, `technical-debt`, `model_catalog`, `phase-2`

**Description**:

Reorganize `db.py` (1528 lines) into context-specific modules:

### Acceptance Criteria
- [ ] Create `db_intake.py` for intake queue schema (~300 lines)
  - Tables: intake_queue_uploads, intake_items
  - No cross-context imports
- [ ] Create `db_models.py` for model catalog schema (~400 lines)
  - Tables: model_catalog_entries, model_catalog_assets, model_catalog_fields
  - No cross-context imports
- [ ] Create `db_working.py` for working groups schema (~350 lines)
  - Tables: working_groups, working_items, working_group_model_links
- [ ] Create `db_archive_links.py` for archive linking schema (~250 lines)
  - Tables: archive_model_links
- [ ] Create `db_migrations.py` for centralized schema management (~400 lines)
  - All CREATE TABLE, ALTER TABLE, version migrations
  - Single source of truth for schema evolution
- [ ] Rewrite `db.py` as connection factory (~200 lines)
  - Provides connect() factory
  - Common utilities (row_factory, transaction helpers)
- [ ] Update all routers to import from new db context modules
- [ ] Run full test suite - all database tests pass
- [ ] Verify schema migrations still work

### Related Files
- `sidecars/model_catalog/app/db.py` (1528 lines → rewritten ~200 lines)
- `sidecars/model_catalog/app/db_intake.py` (NEW)
- `sidecars/model_catalog/app/db_models.py` (NEW)
- `sidecars/model_catalog/app/db_working.py` (NEW)
- `sidecars/model_catalog/app/db_archive_links.py` (NEW)
- `sidecars/model_catalog/app/db_migrations.py` (NEW)

### Risk
- HIGH: Widespread refactoring; requires careful verification
- Mitigation: Comprehensive test suite, staged deployment

---

## Task: Consolidate Shared Helper Functions

**Title**: Phase 2: Import shared helpers from services.shared_helpers

**Labels**: `refactoring`, `technical-debt`, `model_catalog`, `phase-2`, `priority-high`

**Description**:

Update `models.py`, `intake.py`, and `working.py` to import canonical helper implementations from `services/shared_helpers.py` instead of maintaining duplicate definitions.

### Acceptance Criteria
- [ ] `models.py`: Remove local definitions, import from shared_helpers:
  - `_resolve_local_asset_storage_path`
  - `_slugify_title`
  - `_sha256_file`
  - `_serialize_working_group`
  - `_serialize_project_row`
- [ ] `working.py`: Remove local definitions, import from shared_helpers (same 5 functions)
- [ ] `intake.py`: Verify it already uses or can use shared implementations
- [ ] Add import statement at top of each file
- [ ] Run full test suite - all tests pass
- [ ] Verify no behavioral changes in serialization or utility functions
- [ ] Document that shared_helpers is canonical source for these functions

### Related Files
- `sidecars/model_catalog/app/services/shared_helpers.py` (EXISTING - created in Phase 1 fixes)
- `sidecars/model_catalog/app/routers/models.py` (UPDATE)
- `sidecars/model_catalog/app/routers/working.py` (UPDATE)
- `sidecars/model_catalog/app/routers/intake.py` (VERIFY)

### Effort
- Estimated: 2-3 hours
- Risk: Low (import-only changes, existing implementations copy-pasted)

---

## Task: Extract Model Detail Endpoint Logic to Service

**Title**: Phase 2: Extract get_model_detail_endpoint logic to service layer

**Labels**: `refactoring`, `technical-debt`, `model_catalog`, `phase-2`, `priority-high`

**Description**:

Extract the logic from `models.py` endpoint `get_model_detail_endpoint` into a reusable service function to enable:
1. Direct testing without HTTP layer
2. Reuse from other endpoints (currently using TestClient anti-pattern)
3. Improved performance and observability

### Acceptance Criteria
- [ ] Create `services/model_detail_service.py` with function: `build_model_detail_response(state, client, model_ref, include_debug)`
- [ ] Function returns dict with: success, model_ref, authority, model, enrichment, photos, ranking, etc.
- [ ] Function has comprehensive error handling
- [ ] Update `models.py` endpoint to use service function
- [ ] Update TestClient workaround in `intake.py` to call service directly
- [ ] Add unit tests for service function with mock data
- [ ] Run full test suite - all detail-related tests pass
- [ ] Performance: response time unchanged or improved

### Related Files
- `sidecars/model_catalog/app/routers/models.py` (UPDATE endpoint to use service)
- `sidecars/model_catalog/app/routers/intake.py` (UPDATE publish endpoint to use service)
- `sidecars/model_catalog/app/services/model_detail_service.py` (NEW)
- `tests/sidecars/test_model_detail_service.py` (NEW tests)

### Effort
- Estimated: 4-6 hours
- Risk: Medium (careful extraction required to maintain behavior)

---

## Epic: Phase 2.4 - Working Router Enhancement

**Title**: Phase 2.4: Update working.py with services and helper consolidation

**Labels**: `refactoring`, `technical-debt`, `model_catalog`, `phase-2`

**Description**:

After earlier Phase 2 tasks, update `working.py` to use new services and consolidated helpers:

### Acceptance Criteria
- [ ] Update imports to use `services/shared_helpers.py` functions
- [ ] Extract `services/working_groups_service.py` for complex grouping logic
- [ ] Extract `services/working_discovery_service.py` for folder discovery
- [ ] Update endpoints to delegate business logic to services
- [ ] Reduce `working.py` from 2572 to ~1500 lines
- [ ] Run full test suite - all working group tests pass
- [ ] Performance: list/search operations unchanged or improved

### Related Files
- `sidecars/model_catalog/app/routers/working.py` (UPDATE - reduced 2572 → ~1500 lines)
- `sidecars/model_catalog/app/services/working_groups_service.py` (NEW)
- `sidecars/model_catalog/app/services/working_discovery_service.py` (NEW)

---

## Epic: Phase 2 - Full Test Suite Validation

**Title**: Phase 2: Full sidecar test suite validation and performance benchmarking

**Labels**: `testing`, `qa`, `model_catalog`, `phase-2`

**Description**:

After all Phase 2 refactoring is complete, run comprehensive test suite and performance benchmarks:

### Acceptance Criteria
- [ ] Run `pytest tests/sidecars/test_model_catalog_sidecar.py -v` - 100% pass rate
- [ ] Legacy Manyfold adapter tests are archived at `archive/model_catalog/legacy_tests/test_manyfold_upload_adapter.py` and excluded from default suite
- [ ] Code coverage >= 80% for all routers and services
- [ ] No performance regression on key operations:
  - Model list (< 500ms for 1000 models)
  - Model search (< 1s for complex filter)
  - Model detail enrichment (< 300ms)
  - Intake workflow (submit → publish < 5s)
- [ ] All status machine transitions validated
- [ ] No memory leaks in long-running test scenarios
- [ ] Document any performance improvements

### Deliverables
- [ ] Coverage report (coverage.xml)
- [ ] Performance benchmark results
- [ ] Regression test results
- [ ] Performance improvement summary

---

## Documentation Update

**Title**: Phase 2: Update documentation for refactored model_catalog structure

**Labels**: `documentation`, `model_catalog`, `phase-2`

**Description**:

Update documentation to reflect Phase 2 refactoring:

### Acceptance Criteria
- [ ] Update [MODEL_CATALOG_PHASE_2_DESIGN.md](../docs/MODEL_CATALOG_PHASE_2_DESIGN.md) as work progresses
- [ ] Create [MODEL_CATALOG_ARCHITECTURE.md](../docs/MODEL_CATALOG_ARCHITECTURE.md) with:
  - Router organization and responsibilities
  - Service layer design
  - Database schema by context
  - Data flow diagrams
- [ ] Update README files in affected directories
- [ ] Document breaking changes (if any)
- [ ] Create migration guide for external clients (if API changes)

### Related Files
- `docs/MODEL_CATALOG_PHASE_2_DESIGN.md` (UPDATE)
- `docs/MODEL_CATALOG_ARCHITECTURE.md` (NEW)
- `sidecars/model_catalog/app/README.md` (UPDATE)
- `sidecars/model_catalog/README.md` (UPDATE)

---

## Summary

**Total Issues to Create**: 8

**Estimated Total Effort**: 30-40 hours

**Priority**: Phase 2.1 (Intake) and shared helpers consolidation first, then Phase 2.2/2.3 in parallel

**Rollout Plan**:
1. Week 1: Shared helpers consolidation + detail service extraction (P1)
2. Week 2-3: Phase 2.1 (Intake decomposition) + Phase 2.3 (DB reorganization) (P2)
3. Week 4+: Phase 2.2 (Models decomposition) + Phase 2.4 (Working enhancements) (P3)
