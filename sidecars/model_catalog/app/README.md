# Model Catalog App Module

**Status**: Phase 2 Refactoring Complete  
**Last Updated**: 2026-05-02

The `app/` module contains all FastAPI application logic, organized by domain and architectural layer.

## Directory Structure

```
app/
├── main.py                      (FastAPI app factory and lifecycle)
├── settings.py                  (Pydantic settings)
├── state.py                     (AppState dataclass)
├── models.py                    (Data models)
│
├── routers/                     (HTTP endpoint handlers)
│   ├── __init__.py
│   ├── system.py               (Health, config, diagnostics)
│   ├── source_filesystems.py    (Filesystem browsing)
│   ├── archive_links.py         (Archive↔model linking)
│   ├── intake.py               (Publishing & adapters)
│   ├── intake_queue.py         (Queue CRUD, status transitions)
│   ├── intake_verification.py   (Validation & verification)
│   ├── intake_cleanup.py        (Source cleanup & lifecycle)
│   ├── models.py               (Local model authority)
│   ├── models_search.py        (Search & filtering)
│   ├── models_detail.py        (Detail enrichment)
│   ├── models_media.py         (Photos, geometry, downloads)
│   └── working.py              (Working groups & projects)
│
├── services/                    (Business logic & workflows)
│   ├── __init__.py
│   ├── shared_helpers.py       (Shared utilities)
│   ├── intake_service.py       (Dedup detection, hash collection)
│   ├── model_detail_service.py (Detail enrichment logic)
│   └── [phase-2-services]      (Planned: extracted from routers)
│
├── db.py                        (Connection factory & utilities)
├── db_common.py                 (Common schema/queries)
├── db_intake.py                 (Intake context schema)
├── db_models.py                 (Models context schema)
├── db_working.py                (Working context schema)
├── db_archive_links.py          (Archive links context schema)
├── db_migrations.py             (Schema initialization & versioning)
│
├── domain/                      (Specialized domain logic)
│   ├── manyfold.py             (ARCHIVED — was Manyfold API client)
│   ├── local_models.py         (Local model CRUD)
│   ├── geometry_3mf.py         (3MF geometry extraction)
│   ├── model_statistics.py     (Ranking & aggregation)
│   ├── archive_linking.py      (Archive matching & scoring)
│   ├── build_volume_helper.py  (Build volume detection)
│   ├── model_export.py         (Export & serialization)
│   └── _helpers.py             (Shared path & validation utilities)
│
└── __init__.py
```

## Module Responsibilities

### Routers (`routers/`)

HTTP endpoint handlers organized by domain. Each router:
- Validates incoming requests (Pydantic models)
- Delegates business logic to services
- Catches domain exceptions and maps to HTTP status codes
- Returns JSON responses

**Constraints**:
- Maximum ~40 lines per endpoint
- No direct database access (use services)
- All state via `request.app.state`

### Services (`services/`)

Business logic, workflows, and orchestration. Each service:
- Encapsulates domain workflows (multi-step operations)
- Handles validation and error cases
- Coordinates cross-domain operations
- Abstracts database layer

**Current Services**:
- `intake_service.py` — File deduplication, hash collection
- `model_detail_service.py` — Detail enrichment logic

**Planned Services** (Phase 2.1-2.4):
- `intake_queue_service.py` — Queue CRUD and status machine
- `intake_verification_service.py` — Validation workflows
- `intake_cleanup_service.py` — Source cleanup policies
- `model_search_service.py` — Search/filter/ranking logic
- `model_media_service.py` — Photo and media management
- `working_groups_service.py` — Group operations and linking
- `working_discovery_service.py` — Folder discovery patterns

### Database Layer (`db_*.py`)

SQLite schema, migrations, and CRUD operations organized by **bounded context**:

- `db_migrations.py` — Schema initialization and versioning
- `db_intake.py` — Upload queue, validation state
- `db_models.py` — Model catalog, assets, custom fields
- `db_working.py` — Working groups, projects, inventory
- `db_archive_links.py` — Archive↔model relationships
- `db_common.py` — Shared schema patterns
- `db.py` — Connection factory and common utilities

**Design Principles**:
- One module per bounded context
- Minimal cross-context queries (mostly reads for enrichment)
- Explicit foreign keys and relationship management
- Immutable IDs (no rename/move for local models)

### Domain Modules (`*/`)

Specialized logic for integration points and complex operations:

- `manyfold.py` — ARCHIVED (was Manyfold API client; see `archive/model_catalog/`)
- `local_models.py` — Local model CRUD, filesystem, SQLite
- `geometry_3mf.py` — 3MF file parsing, geometry extraction
- `model_statistics.py` — Ranking aggregation, print statistics
- `archive_linking.py` — Archive candidate matching, confidence scoring
- `build_volume_helper.py` — Build volume detection, plate layout
- `model_export.py` — Data export, serialization formats

## Data Flow

### Request Handling

```
HTTP Request
    ↓
Router (request validation)
    ↓
Service (business logic)
    ├─ db_*.py (data persistence)
    ├─ domain/*.py (specialized logic)
    └─ local_models.py (local authority)
    ↓
HTTP Response
```

### Bounded Context Dependencies

```
    intake ──┐
             ├──> models (for enrichment)
    archive_links ──┘

    working ──> models (for link validation)
```

**Invariant**: No circular dependencies; models is the only hub.

## Testing

### Test Organization

```
tests/
├── phase3/
│   ├── test_intake_workflow.py
│   ├── test_model_detail_endpoint.py
│   ├── test_model_search_endpoint.py
│   └── ...
├── sidecars/
│   └── model_catalog/
│       ├── test_local_models.py
│       ├── test_intake_service.py
│       ├── test_model_detail_service.py
│       └── ...
└── ...
```

### Coverage Targets

- **Routers**: Happy path + error cases (70%+)
- **Services**: Comprehensive workflows, edge cases (85%+)
- **Domain modules**: Critical paths (80%+)
- **Database**: Schema integrity, migrations (75%+)

## Configuration

### Environment Variables

See `settings.py` for the authoritative list:

- `DATABASE_PATH` — SQLite database location
- `ASSETS_ROOT_HOST` — Bind-mount path for file storage

### Authority Mode

**Local Authority** (only supported mode):
- All model queries hit local SQLite
- Identity scheme: `local://model/{local_model_id}`
- No external service dependencies

## Phase 2 Implementation Status

### Phase 2.1: Intake Router Decomposition ✅ COMPLETE
- ✓ Created `intake_queue.py` (queue CRUD, status transitions)
- ✓ Created `intake_verification.py` (validation, verification workflows)
- ✓ Created `intake_cleanup.py` (source cleanup, lifecycle)
- ✓ Updated `intake.py` (publishing & adapters only)
- ✓ Tests passing for all new routers

### Phase 2.2: Models Router Decomposition ✅ COMPLETE
- ✓ Created `models_search.py` (search, filtering, ranking)
- ✓ Created `models_detail.py` (detail enrichment, fields)
- ✓ Created `models_media.py` (photos, geometry, downloads)
- ✓ Updated `models.py` (local authority CRUD only)
- ✓ Tests passing for all new routers

### Phase 2.3: Database Context Split ✅ COMPLETE
- ✓ Split `db.py` into context-specific modules
- ✓ Created `db_migrations.py` for schema management
- ✓ Rewrote `db.py` as connection factory + utilities
- ✓ Updated all imports across codebase

### Phase 2.4: Working Router Optimization 🔄 IN PROGRESS
- ⏳ Extract `working_groups_service.py`
- ⏳ Extract `working_discovery_service.py`
- ⏳ Update `working.py` to delegate to services
- ⏳ Refactor serialization helpers

## API Endpoints Summary

### System (`system.py`)
- `GET /healthz` — Health check
- `GET /api/config` — Configuration summary
- `GET /openapi.json` — OpenAPI schema

### Models (`models*.py`)
- `GET /api/models` — List local models
- `GET /api/models/search` — Search with filtering
- `GET /api/models/{model_ref}/detail` — Fetch model detail
- `GET /api/models/{model_ref}/related` — Related models
- `POST /api/local/models` — Create local model
- `PUT /api/local/models/{local_model_id}` — Update local model
- `DELETE /api/local/models/{local_model_id}` — Delete local model
- `POST /api/models/{model_ref}/photos` — Upload photo
- `GET /api/models/{model_ref}/geometry/{file_id}` — Proxy 3MF geometry

### Intake (`intake*.py`)
- `POST /api/intake/browser` — Browser file upload
- `POST /api/intake/uploads/{upload_id}/status` — Update upload status
- `POST /api/intake/items/{item_id}/validate` — Validate intake item
- `POST /api/intake/submit` — Submit intake items
- `POST /api/intake/uploads/{upload_id}/publish-to-local` — Publish to local authority
- `POST /api/intake/uploads/{upload_id}/cleanup` — Run source cleanup

### Working (`working.py`)
- `GET /api/working/groups` — List working groups
- `POST /api/working/groups` — Create working group
- `GET /api/working/groups/{group_id}` — Fetch group detail
- `POST /api/working/groups/{group_id}/items` — Add working item
- `DELETE /api/working/groups/{group_id}/items/{item_id}` — Remove working item

See [MODEL_CATALOG_ARCHITECTURE.md](../../docs/MODEL_CATALOG_ARCHITECTURE.md) for complete API contracts.

## Migration Guides

### From Monolithic to Modular Routers

**For External Clients**: No breaking changes. All endpoint contracts are preserved.

**For Internal Developers**:
- Shared helpers moved from `_helpers.py` to `services/shared_helpers.py`
- Database layer split by context; update imports accordingly
- New service layer for business logic (optional, but recommended)

See [MIGRATION_GUIDE.md](#migration-guide) for detailed examples.

## References

- [Model Catalog Architecture](../../docs/MODEL_CATALOG_ARCHITECTURE.md)
- [Phase 2 Refactoring Design](../../docs/MODEL_CATALOG_PHASE_2_DESIGN.md)
- [Local Model Storage & Naming](../../docs/LOCAL-MODEL-STORAGE-AND-NAMING-DESIGN.md)
- [OpenAPI Schema](http://localhost:8314/openapi.json)

