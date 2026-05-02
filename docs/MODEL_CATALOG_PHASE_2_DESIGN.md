# Model Catalog Sidecar: Phase 2 Refactoring Design

**Status**: Planning  
**Last Updated**: 2026-05-02  
**Related Issues**: #1190-#1197 (Phase 1 Refactor)

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

### 4.1 Split `intake.py` by Workflow (Phase 2.1)

**Current**: Single 3161-line router with mixed concerns

**Target**: Three focused routers/modules:

#### 4.1.1 Queue State Machine (NEW: `intake_queue.py`)
- Responsibilities:
  - Intake queue CRUD (create, read, update, delete uploads)
  - Status transitions with validation
  - Audit logging
- Endpoints:
  - `POST /api/intake/uploads` - Create upload queue entry
  - `GET /api/intake/uploads/{upload_id}` - Fetch upload status
  - `PUT /api/intake/uploads/{upload_id}/status` - Transition status
  - `DELETE /api/intake/uploads/{upload_id}` - Delete upload
- Service: Extract to `services/intake_queue_service.py`

#### 4.1.2 Verification & Validation (NEW: `intake_verification.py`)
- Responsibilities:
  - Entry validation
  - Source file verification
  - Duplicate detection
  - Verification workflow
- Endpoints:
  - `POST /api/intake/items/{item_id}/validate`
  - `POST /api/intake/items/{item_id}/defer`
  - `POST /api/intake/items/{item_id}/reject`
  - `POST /api/intake/items/{item_id}/group`
- Service: Extract to `services/intake_verification_service.py`

#### 4.1.3 Staging & Cleanup (NEW: `intake_cleanup.py`)
- Responsibilities:
  - Post-upload source cleanup
  - Staging directory management
  - File lifecycle policy enforcement
- Endpoints:
  - `POST /api/intake/uploads/{upload_id}/cleanup` - Run cleanup
- Service: Extract `_run_source_cleanup` to `services/intake_cleanup_service.py`

#### 4.1.4 Publishing & Adapters (KEEP in `intake.py`)
- Responsibilities:
  - Publish intake to local authority catalog
  - Manyfold adapter integration
  - Browser upload staging
- Endpoints:
  - `POST /api/intake/uploads/browser` - Browser upload
  - `POST /api/intake/submit` - Submit intake items
  - `POST /api/intake/uploads/{upload_id}/publish-to-local`
  - `POST /api/intake/uploads/{upload_id}/upload-to-manyfold`

**Estimated Impact**: ~800 lines per new module, clearer responsibilities

### 4.2 Split `models.py` by Domain (Phase 2.2)

**Current**: Single 3242-line router with multiple concerns

**Target**: Three focused routers/modules:

#### 4.2.1 Model Listing & Search (NEW: `models_search.py`)
- Responsibilities:
  - Model inventory listing (local + Manyfold catalog)
  - Search/filtering
  - Ranking aggregation
  - Related models
- Endpoints:
  - `GET /api/models` - List all models
  - `GET /api/models/search` - Search models
  - `GET /api/models/{model_ref}/related` - Related models
  - `GET /api/models/{model_ref}/ranking` - Get ranking
- Service: Extract to `services/model_search_service.py`

#### 4.2.2 Model Detail & Enrichment (NEW: `models_detail.py`)
- Responsibilities:
  - Model detail retrieval
  - Enrichment (custom fields, photos, metadata)
  - Field management
  - Asset listing
- Endpoints:
  - `GET /api/models/{model_ref}/detail` - Fetch model detail
  - `GET /api/models/{model_ref}/fields` - Get custom fields
  - `PUT /api/models/{model_ref}/fields/{field_key}` - Set custom field
  - `DELETE /api/models/{model_ref}/fields/{field_key}` - Delete field
- Service: Extract to `services/model_detail_service.py`

#### 4.2.3 Model Media & Geometry (NEW: `models_media.py`)
- Responsibilities:
  - Photo upload & management
  - Geometry proxy
  - File downloads
  - Preview generation
- Endpoints:
  - `POST /api/models/{model_ref}/photos` - Upload photo
  - `GET /api/models/{model_ref}/photos/{photo_id}/content` - Get photo
  - `DELETE /api/models/{model_ref}/photos/{photo_id}` - Delete photo
  - `GET /api/models/{model_ref}/geometry/{file_id}` - Proxy geometry
  - `GET /api/models/{model_ref}/files/{file_id}/download` - Download file
- Service: Extract to `services/model_media_service.py`

#### 4.2.4 Local Model Authority (KEEP in `models.py`)
- Responsibilities:
  - Local model CRUD (create, read, update, delete)
  - Local model lifecycle
- Endpoints:
  - `GET /api/local/models` - List local models
  - `GET /api/local/models/{local_model_id}` - Get local model
  - `GET /api/local/models/{local_model_id}/assets` - Get local assets

**Estimated Impact**: ~800-1000 lines per new module, clearer boundaries

### 4.3 Split `db.py` by Bounded Context (Phase 2.3)

**Current**: 1528-line ORM layer with domain-specific schema and logic mixed

**Target**: Service-oriented layer with bounded contexts:

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

---

## 5. Implementation Priorities

### P1 (Immediate)
1. **Shared helpers consolidation**: Update models.py, working.py to import from `shared_helpers.py`
   - Effort: 2-3 hours
   - Risk: Low (import-only changes)
   - Value: High (reduce maintenance burden)

2. **Detail endpoint refactoring**: Extract `get_model_detail_endpoint` logic to service
   - Effort: 4-6 hours
   - Risk: Medium (requires careful extraction)
   - Value: High (unblocks TestClient fix, improves testability)

### P2 (Next)
3. **Intake verification service**: Extract validation & verification logic
   - Effort: 6-8 hours
   - Risk: Medium (logic is complex)
   - Value: High (improves testability)

4. **db.py split by context**: Organize schema by bounded context
   - Effort: 8-10 hours
   - Risk: High (widespread refactoring)
   - Value: High (improves clarity)

### P3 (Later)
5. **Router splits**: Apply modularization to intake.py, models.py, working.py
   - Effort: 16-20 hours total
   - Risk: Medium (many endpoints, existing tests)
   - Value: Medium-High (improves maintainability)

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
