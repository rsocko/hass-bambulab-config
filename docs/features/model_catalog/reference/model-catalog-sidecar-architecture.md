# Model Catalog Sidecar: Architecture Documentation

**Version**: 1.0 (Phase 2 Design Foundation)  
**Last Updated**: 2026-05-02  
**Status**: Active  
**Related Issues**: #1207 (Documentation), #1190-#1197 (Phase 1 Refactor), Phase 2 Planning

---

## Table of Contents

1. [Overview](#overview)
2. [High-Level Architecture](#high-level-architecture)
3. [Router Organization](#router-organization)
4. [Service Layer Design](#service-layer-design)
5. [Database Schema by Context](#database-schema-by-context)
6. [Data Flow](#data-flow)
7. [Bounded Contexts](#bounded-contexts)
8. [Key Abstractions](#key-abstractions)
9. [External Integration Points](#external-integration-points)
10. [API Contracts](#api-contracts)

---

## Overview

The Model Catalog Sidecar is a FastAPI microservice that manages 3D printing model metadata, intake workflows, working file organization, and enrichment with print history archives. It provides a unified API for:

- **Local Model Authority**: Independent SQLite-backed catalog with full CRUD
- **Manyfold Integration**: Optional cache/hybrid mode for compatibility
- **Intake Workflow**: Upload queue, validation, verification, publishing
- **Working Groups**: Organization of active projects and printing inventory
- **Archive Linking**: Bidirectional model↔archive relationship tracking
- **Media & Enrichment**: Photos, custom fields, geometry extraction, ranking

**Design Principle**: Event-driven, service-oriented architecture with clear bounded contexts and minimal cross-context dependencies.

---

## High-Level Architecture

### Layered Architecture

```
┌─────────────────────────────────────────────────────────┐
│              EXTERNAL CLIENTS (HA, CLI, UI)             │
└────────────────────────────┬────────────────────────────┘
                             │ HTTP/WebSocket
┌────────────────────────────▼────────────────────────────┐
│                    ROUTER LAYER                         │
│  (HTTP request handlers, validation, delegation)        │
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│                    SERVICE LAYER                        │
│  (Business logic, workflows, coordination)              │
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│                   DOMAIN MODULES                        │
│  (Specialized logic: geometry, enrichment, export)      │
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│               PERSISTENCE LAYER (db_*.py)              │
│  (SQLite schema, queries, migrations)                   │
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│                    EXTERNAL SERVICES                    │
│  (Manyfold API, filesystem, external storage)           │
└─────────────────────────────────────────────────────────┘
```

### App Factory (`main.py`)

**Responsibility**: FastAPI application composition and lifecycle management.

- Creates FastAPI app with CORS middleware
- Initializes AppState (local SQLite, file system roots)
- Manages ManyfoldClient lifecycle (init on startup, cleanup on shutdown)
- Registers all routers in dependency order
- Serves OpenAPI schema at `/openapi.json`

**Key Design**: Zero endpoint handlers in `main.py`—all logic delegated to routers and services.

---

## Router Organization

### Router Responsibilities Matrix

| Router | Domain | Endpoints | Purpose |
|--------|--------|-----------|---------|
| `system.py` | System | 8 | Health, config, diagnostics, OpenAPI export |
| `source_filesystems.py` | Infrastructure | 3 | Server-side filesystem browsing for intake/working |
| `archive_links.py` | Archive Integration | 8 | Archive↔model linking, candidate discovery |
| `intake.py` | Intake/Publishing | 4 | Publishing, adapter integration (core intake split to Phase 2.1) |
| `models.py` | Model Authority | 4 | Local model CRUD (core search/detail split to Phase 2.2) |
| `working.py` | Working Groups | 26 | Project organization, working inventory, discovery |

### Router Request/Response Flow

All routers follow this pattern:

```
HTTP Request
    ↓
Router Handler
    ├── Validate input (Pydantic models)
    ├── Check authorization (if applicable)
    ├── Delegate to Service or Domain module
    └── Return Response (JSON or stream)
```

**Router Constraints**:
- Maximum ~40 lines per endpoint handler
- Input validation via Pydantic models (defined in `models.py`)
- Delegation to services for business logic
- Error handling: convert domain exceptions to HTTP status codes
- All state accessed via `request.app.state` (AppState)

---

## Service Layer Design

### Service Organization

**Current** (Phase 1):
- `intake_service.py` — Dedup detection, hash collection from inventory (working items, catalog assets, in-flight intake queue)

**Planned** (Phase 2):
- `intake_queue_service.py` — Queue CRUD, status transitions, audit
- `intake_verification_service.py` — Validation, verification workflows
- `intake_cleanup_service.py` — Source cleanup, lifecycle management
- `model_search_service.py` — Listing, search, filtering, ranking
- `model_detail_service.py` — Detail enrichment, field management
- `model_media_service.py` — Photo management, geometry proxy, downloads
- `working_groups_service.py` — Group operations, model linking
- `working_discovery_service.py` — Folder discovery, pattern matching
- `shared_helpers.py` — Shared utilities (slugify, hash, serialize)

### Service Conventions

**Responsibilities**:
- Implement domain workflows (composed of multiple db calls)
- Handle business logic errors (validation, constraints)
- Coordinate cross-context operations (e.g., enrichment)
- Abstract database details from routers

**API Pattern**:
```python
class MyService:
    def __init__(self, db_module: ModuleType):
        self.db = db_module

    def do_something(self, input: Dict) -> Result:
        # Validate input
        # Perform business logic
        # Persist changes
        # Return result
        pass
```

**Error Handling**:
- Raise domain exceptions (ValueError, NotFound, ValidationError)
- Routers catch and convert to HTTP status codes
- Never let database exceptions escape service layer

---

## Database Schema by Context

### Context Overview

The database is organized by **bounded context**, with explicit, minimal dependencies:

```
┌─────────────────────────────────────────────────────────┐
│                   INTAKE CONTEXT                        │
│  (Intake Queue Uploads, Items, Verification State)      │
├─────────────────────────────────────────────────────────┤
│  Tables:                                                │
│  • intake_queue_uploads (upload session metadata)       │
│  • intake_items (individual files in upload)            │
│  • intake_verification (validation state, holds)        │
│                                                         │
│  External Deps: models (for archiving)                  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                   MODELS CONTEXT                        │
│  (Model Catalog, Custom Fields, Assets)                 │
├─────────────────────────────────────────────────────────┤
│  Tables:                                                │
│  • model_catalog_entries (local model metadata)         │
│  • model_catalog_assets (3MF files, photos, renders)    │
│  • model_catalog_fields (custom field storage)          │
│                                                         │
│  External Deps: archive_links (for enrichment)          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                  WORKING CONTEXT                        │
│  (Working Groups, Projects, Inventory)                  │
├─────────────────────────────────────────────────────────┤
│  Tables:                                                │
│  • working_groups (project containers)                  │
│  • working_items (individual project items)             │
│  • working_group_model_links (ref to model context)     │
│                                                         │
│  External Deps: models (for link validation)            │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│              ARCHIVE_LINKS CONTEXT                      │
│  (Model↔Archive Relationships)                          │
├─────────────────────────────────────────────────────────┤
│  Tables:                                                │
│  • archive_model_links (bidirectional relationships)    │
│                                                         │
│  External Deps: models (for link targets)               │
└─────────────────────────────────────────────────────────┘
```

### Schema Details

#### Intake Context (`db_intake.py`)

```sql
CREATE TABLE intake_queue_uploads (
  upload_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,           -- 'browser', 'server', 'async'
  created_at TEXT NOT NULL,       -- ISO 8601
  uploaded_by TEXT,               -- User identifier
  status TEXT NOT NULL DEFAULT 'pending',  -- pending, processing, published, failed
  error_message TEXT,
  total_items INTEGER DEFAULT 0,
  successful_items INTEGER DEFAULT 0,
  failed_items INTEGER DEFAULT 0,
  metadata JSONB                  -- Additional context
);

CREATE TABLE intake_items (
  item_id TEXT PRIMARY KEY,
  upload_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  source_path TEXT NOT NULL,
  size_bytes INTEGER,
  file_hash TEXT,                 -- SHA256 for dedup
  status TEXT NOT NULL,           -- ready, verified, pending_approval, rejected, published
  verification_result JSONB,      -- Validation details
  duplicate_of TEXT,              -- If duplicate, ref to item_id
  FOREIGN KEY(upload_id) REFERENCES intake_queue_uploads(upload_id)
);
```

**Access Functions** (in `db_intake.py`):
- `create_upload_session(source, uploaded_by)` → upload_id
- `create_intake_item(upload_id, filename, path, size)` → item_id
- `update_item_status(item_id, new_status)` → bool
- `list_items_by_upload(upload_id)` → List[Item]
- `find_duplicate_by_hash(file_hash)` → Optional[item_id]

#### Models Context (`db_models.py`)

```sql
CREATE TABLE model_catalog_entries (
  model_id TEXT PRIMARY KEY,      -- UUID or slug
  local_model_id TEXT UNIQUE,     -- {slug}--{shortid} format
  title TEXT NOT NULL,
  description TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  source TEXT,                    -- 'intake', 'import', 'manual'
  manyfold_ref TEXT,              -- Foreign key to Manyfold if linked
  custom_fields JSONB DEFAULT '{}',  -- User-defined fields
  ranking REAL DEFAULT 0.0,       -- Aggregated score
  metadata JSONB DEFAULT '{}'
);

CREATE TABLE model_catalog_assets (
  asset_id TEXT PRIMARY KEY,
  model_id TEXT NOT NULL,
  asset_type TEXT,               -- 'model_file', 'photo', 'preview', 'geometry'
  filename TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  size_bytes INTEGER,
  file_hash TEXT,
  created_at TEXT NOT NULL,
  metadata JSONB,
  FOREIGN KEY(model_id) REFERENCES model_catalog_entries(model_id)
);

CREATE TABLE model_catalog_fields (
  field_id TEXT PRIMARY KEY,
  model_id TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT,
  value_type TEXT,               -- 'string', 'number', 'bool', 'json'
  created_at TEXT NOT NULL,
  FOREIGN KEY(model_id) REFERENCES model_catalog_entries(model_id),
  UNIQUE(model_id, key)
);
```

**Access Functions** (in `db_models.py`):
- `create_model_entry(title, description, source)` → model_id
- `get_model_entry(model_id)` → Optional[ModelEntry]
- `update_model_entry(model_id, **fields)` → bool
- `list_models(limit, offset, filter)` → List[ModelEntry]
- `create_asset(model_id, asset_type, filename, path)` → asset_id
- `get_custom_field(model_id, key)` → Optional[str]
- `set_custom_field(model_id, key, value)` → bool

#### Working Context (`db_working.py`)

```sql
CREATE TABLE working_groups (
  group_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  created_at TEXT NOT NULL,
  metadata JSONB
);

CREATE TABLE working_items (
  item_id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  status TEXT,                   -- 'active', 'completed', 'archived'
  created_at TEXT NOT NULL,
  FOREIGN KEY(group_id) REFERENCES working_groups(group_id)
);

CREATE TABLE working_group_model_links (
  link_id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL,
  model_id TEXT NOT NULL,
  linked_at TEXT NOT NULL,
  link_type TEXT,                -- 'source', 'ref', 'derived'
  FOREIGN KEY(group_id) REFERENCES working_groups(group_id),
  FOREIGN KEY(model_id) REFERENCES model_catalog_entries(model_id)
);
```

#### Archive Links Context (`db_archive_links.py`)

```sql
CREATE TABLE archive_model_links (
  link_id TEXT PRIMARY KEY,
  archive_id TEXT NOT NULL,
  model_id TEXT NOT NULL,
  confidence REAL DEFAULT 1.0,    -- Match confidence (0.0-1.0)
  match_type TEXT,               -- 'filename', 'uuid', 'manual'
  created_at TEXT NOT NULL,
  verified_at TEXT,
  notes TEXT,
  FOREIGN KEY(model_id) REFERENCES model_catalog_entries(model_id),
  UNIQUE(archive_id, model_id)
);
```

---

## Data Flow

### Model Creation Flow

```
User uploads file
    ↓
[router] POST /api/intake/browser
    ├─ Validate file (size, format)
    └─ Call intake_service.process_browser_upload()
        ├─ Compute file hash
        ├─ Check for duplicates (db_intake.find_duplicate_by_hash)
        ├─ Create upload session (db_intake.create_upload_session)
        └─ Store file in staging area
    ↓
[router] POST /api/intake/submit
    ├─ Validate intake items
    └─ Call intake_service.submit_intake()
        ├─ Verify source files
        ├─ Validate against schema
        ├─ Update intake_items status
        └─ Trigger enrichment (async)
    ↓
[router] POST /api/intake/uploads/{upload_id}/publish-to-local
    ├─ Check permissions
    └─ Call publishing_service.publish_to_local()
        ├─ Create model_catalog_entry (db_models)
        ├─ Move assets to permanent storage
        ├─ Create model_catalog_assets entries
        ├─ Update archive_model_links if applicable
        └─ Update intake_queue_uploads status
```

### Model Search Flow

```
Client requests model list
    ↓
[router] GET /api/models?search=gridfinity&limit=20
    ├─ Validate query parameters
    └─ Call model_search_service.search_models()
        ├─ Query db_models (local entries)
        ├─ Query Manyfold cache (if hybrid mode)
        ├─ Merge and deduplicate results
        ├─ Apply ranking (call model_statistics)
        ├─ Apply filters/sort
        └─ Return paginated results
```

### Model Detail Flow

```
Client requests model details
    ↓
[router] GET /api/models/{model_ref}/detail
    ├─ Parse model_ref (could be local_id, uuid, or manyfold_ref)
    └─ Call model_detail_service.get_detail()
        ├─ Fetch model_catalog_entry (db_models)
        ├─ Fetch assets (db_models.list_assets)
        ├─ Fetch custom fields (db_models.get_custom_fields)
        ├─ Fetch related models (model_search_service)
        ├─ Fetch archive links (db_archive_links)
        ├─ Enrich with Spoolman data (if available)
        └─ Return enriched detail object
```

### Photo Upload Flow

```
Client uploads photo
    ↓
[router] POST /api/models/{model_ref}/photos
    ├─ Validate file (image format, size)
    └─ Call model_media_service.upload_photo()
        ├─ Generate thumbnail
        ├─ Store original and thumbnail
        ├─ Create model_catalog_asset entry (type=photo)
        ├─ Optionally update model ranking
        └─ Return photo metadata
```

---

## Bounded Contexts

### Context 1: Intake (Upload & Publishing)

**Purpose**: Manage the workflow from file upload through validation to publishing to local authority.

**Entities**:
- Upload Session (captures batch metadata)
- Intake Item (individual file in upload)
- Verification State (validation results, holds)

**Use Cases**:
- Create upload session (browser or server-initiated)
- Compute file hashes and detect duplicates
- Validate source files
- Apply verification filters (user can defer, group, or reject)
- Publish to local authority (triggers model creation)
- Clean up staging files post-publish

**Dependencies**:
- Reads from: None (self-contained)
- Writes to: intake_queue_uploads, intake_items
- External calls: Filesystem (staging), Manyfold (adapter, optional)

**Key Invariants**:
- Each upload session has a unique upload_id
- Items in an upload follow a lifecycle: pending → verified → published (or rejected)
- File hash uniqueness per source (prevents re-uploading same file)

---

### Context 2: Models (Catalog Authority)

**Purpose**: Maintain local model catalog with custom enrichment and Manyfold integration.

**Entities**:
- Model Catalog Entry (metadata container)
- Model Asset (files, photos, geometry)
- Custom Field (user-defined data)

**Use Cases**:
- Create local model (direct or from intake)
- Retrieve model by ID, UUID, or reference
- Search models (local, Manyfold cache, or hybrid)
- Manage custom fields (tags, notes, metadata)
- Upload photos and manage media
- Rank models based on custom scoring
- Link to archive for enrichment

**Dependencies**:
- Reads from: db_models, db_archive_links (for enrichment)
- Writes to: model_catalog_entries, model_catalog_assets, model_catalog_fields
- External calls: Manyfold (cache queries), Filesystem (asset storage)

**Key Invariants**:
- Each model has a unique local_model_id (immutable, format: `{slug}--{shortid}`)
- Assets are immutable after creation
- Custom fields are user-editable
- Ranking is aggregated from multiple sources

---

### Context 3: Working Groups

**Purpose**: Organize active projects and working inventory separate from permanent catalog.

**Entities**:
- Working Group (project container)
- Working Item (individual file in project)
- Group Model Link (reference to catalog models)

**Use Cases**:
- Create working group (container for project)
- Add working items (files in project)
- Link models to group (for reference/cross-reference)
- Discover working files from filesystem
- Reorganize working items
- Archive completed projects

**Dependencies**:
- Reads from: db_working, db_models (for link validation)
- Writes to: working_groups, working_items, working_group_model_links
- External calls: Filesystem (discovery, file operations)

**Key Invariants**:
- Each working group has a unique group_id
- Working items are mutable (can be moved, deleted)
- Model links are references only (no ownership)

---

### Context 4: Archive Links

**Purpose**: Track bidirectional relationships between print archives and models.

**Entities**:
- Archive Model Link (relationship metadata)

**Use Cases**:
- Create link when print starts (webhook trigger)
- Update link confidence based on verification
- Find models for archive (reverse lookup)
- Find archives for model (forward lookup)
- Mark links as verified (user confirmation)

**Dependencies**:
- Reads from: db_archive_links, db_models (for validation)
- Writes to: archive_model_links
- External calls: Archive API (read), Spoolman (enrichment)

**Key Invariants**:
- Each archive can link to multiple models
- Each model can link to multiple archives
- Links have confidence scores (0.0-1.0)
- Links are created automatically or manually

---

## Key Abstractions

### AppState

**Purpose**: Share application-wide state between requests without global variables.

```python
@dataclass
class AppState:
    db_path: Path
    assets_root: Path
    model_catalog: "ModelCatalogManager"  # Convenience accessor
```

**Access**: `request.app.state`

**Immutable After Init**: Yes (thread-safe)

---

### ManyfoldClient

**Purpose**: Abstract Manyfold API interactions with caching and OAuth handling.

```python
class ManyfoldClient:
    async def get_model_summary(self, manyfold_id: str) -> Optional[ManyfoldModelSummary]:
        # Query cache, fallback to API
        pass

    async def search_models(self, query: str) -> List[ManyfoldModelSummary]:
        # Query cache
        pass

    async def upload_model(self, model_data: ModelData) -> ManyfoldModelSummary:
        # Create model on Manyfold
        pass
```

**Lifecycle**: Created at startup, destroyed at shutdown (via lifespan)

---

### Shared Helpers

**Purpose**: Centralize utility functions to reduce duplication.

**Current** (`_helpers.py`):
- Path resolution
- Timestamp utilities
- Validation helpers

**Planned** (`services/shared_helpers.py`):
- `_slugify_title(title)` → URL-safe slug
- `_sha256_file(path)` → File hash
- `_serialize_working_group(row)` → JSON
- `_serialize_project_row(row)` → JSON
- `_resolve_local_asset_storage_path(asset_type)` → Path

---

### Error Handling

**Domain Exceptions**:
```python
class ModelNotFoundError(Exception):
    pass

class DuplicateUploadError(Exception):
    pass

class VerificationFailedError(Exception):
    pass
```

**HTTP Mapping**:
- `ModelNotFoundError` → 404 Not Found
- `DuplicateUploadError` → 409 Conflict
- `VerificationFailedError` → 422 Unprocessable Entity
- `ValueError` → 400 Bad Request
- Unhandled → 500 Internal Server Error

---

## External Integration Points

### Manyfold

**Mode 1: Local Authority** (default)
- Disable Manyfold queries
- Use only local SQLite catalog
- Fallback: graceful degradation if Manyfold unavailable

**Mode 2: Hybrid**
- Query local SQLite + Manyfold cache
- Merge and deduplicate results
- Allow publishing to Manyfold (optional)

**Mode 3: Manyfold-Only** (legacy compatibility)
- Query Manyfold API for all operations
- Use Manyfold cache as authoritative source
- Fallback: None (requires Manyfold)

**Configuration**: Environment variable `MODEL_CATALOG_MODE` (default: `local`)

---

### Filesystem

**Directory Structure**:

```
{ASSETS_ROOT_HOST}/
├── local_models/           # Permanent local model storage
│   ├── {slug}--{shortid}/  # Model folder (immutable)
│   │   ├── 3mf/            # Original 3MF files
│   │   ├── photos/         # User-uploaded photos
│   │   ├── metadata.json   # Model metadata
│   │   └── .assets.json    # Asset inventory
│   └── ...
├── working/                # Temporary working files
│   ├── {group-id}/         # Working group folder
│   │   ├── files/          # Project working files
│   │   └── metadata.json
│   └── ...
└── intake_staging/         # Temporary intake staging
    ├── {upload-id}/        # Upload session folder
    │   ├── files/          # Uploaded files
    │   └── manifest.json   # Upload metadata
    └── ...
```

**Cleanup Policy**:
- **Intake Staging**: Delete after publish or 7 days (configurable)
- **Working**: User-managed (no automatic cleanup)
- **Local Models**: Immutable (no automatic cleanup, user-initiated delete)

---

### Archive API

**Webhook Contract** (from Bambu Lab API):

```json
{
  "event": "print_completed",
  "archive_id": "abc123",
  "printer_id": "X1-0001",
  "model": {
    "name": "gridfinity-bin.3mf",
    "size": 2048576
  },
  "printing": {
    "filename": "gridfinity-bin.3mf"
  }
}
```

**Response**: 200 OK (idempotent)

**Action**: Trigger archive_model_link creation (deferred to Phase 2.5)

---

### Spoolman Integration

**Enrichment Flow**:
1. User sets filament UUID on custom field
2. Model detail endpoint queries Spoolman
3. Returns filament metadata (color, material, weight)
4. Display in UI with color swatch

**API**: REST GET `/api/v1/spools/{spool_id}`

---

## API Contracts

### Model Detail Endpoint

**Request**:
```
GET /api/models/{model_ref}/detail
```

**Path Parameters**:
- `model_ref`: Local model ID, UUID, or Manyfold reference

**Query Parameters**:
- `include_enrichment` (bool, optional): Include photos, fields, archives
- `include_related` (bool, optional): Include related models
- `include_ranking` (bool, optional): Include ranking details

**Response** (200 OK):
```json
{
  "model_id": "uuid",
  "local_model_id": "gridfinity-bin--a1b2c3d4",
  "title": "Gridfinity Bin",
  "description": "Modular storage bin",
  "created_at": "2026-05-01T10:00:00Z",
  "updated_at": "2026-05-02T15:30:00Z",
  "assets": [
    {
      "asset_id": "uuid",
      "type": "model_file",
      "filename": "gridfinity-bin.3mf",
      "size_bytes": 2048576,
      "storage_path": "local_models/gridfinity-bin--a1b2c3d4/3mf/gridfinity-bin.3mf"
    }
  ],
  "custom_fields": {
    "tags": "storage,organizer",
    "material": "PLA",
    "filament_uuid": "12345-67890"
  },
  "enrichment": {
    "filament_info": {
      "color": "#FF6B35",
      "material": "PLA",
      "weight_grams": 100
    }
  },
  "related_models": [
    { "model_id": "...", "title": "...", "reason": "same_category" }
  ],
  "ranking": {
    "score": 8.5,
    "sources": ["print_count", "user_rating", "recency"]
  },
  "archive_links": [
    {
      "link_id": "uuid",
      "archive_id": "abc123",
      "confidence": 0.95,
      "match_type": "uuid",
      "verified_at": "2026-05-02T14:00:00Z"
    }
  ]
}
```

**Error Responses**:
- 404 Not Found: Model not found
- 422 Unprocessable Entity: Invalid model_ref format

---

### Model Search Endpoint

**Request**:
```
GET /api/models/search?q=gridfinity&limit=20&offset=0
```

**Query Parameters**:
- `q` (string, required): Search query
- `limit` (integer, optional, default=20, max=100): Page size
- `offset` (integer, optional, default=0): Pagination offset
- `filter` (string, optional): Filter expression (e.g., `tag:storage`)
- `sort` (string, optional, default=`relevance`): Sort field
- `include_manyfold` (bool, optional, default=true): Include Manyfold results

**Response** (200 OK):
```json
{
  "total": 42,
  "limit": 20,
  "offset": 0,
  "results": [
    {
      "model_id": "uuid",
      "local_model_id": "gridfinity-bin--a1b2c3d4",
      "title": "Gridfinity Bin",
      "source": "local",
      "ranking": 8.5,
      "asset_count": 5,
      "photo_count": 3
    }
  ],
  "facets": {
    "source": { "local": 35, "manyfold": 7 },
    "tag": { "storage": 15, "organizer": 12 }
  }
}
```

---

### Upload Endpoint

**Request**:
```
POST /api/intake/browser
Content-Type: multipart/form-data

file: <binary>
uploaded_by: "user@example.com" (optional)
```

**Response** (201 Created):
```json
{
  "upload_id": "uuid",
  "item_id": "uuid",
  "filename": "gridfinity-bin.3mf",
  "size_bytes": 2048576,
  "file_hash": "sha256hash...",
  "status": "pending",
  "duplicate_of": null
}
```

**Error Responses**:
- 409 Conflict: File hash already exists (duplicate)
- 413 Payload Too Large: File exceeds maximum size
- 422 Unprocessable Entity: Invalid file format

---

## Phase 2 Implementation Timeline

### Phase 2.1: Intake Router Decomposition (Weeks 1-2)
- Extract intake_queue_service.py
- Extract intake_verification_service.py
- Extract intake_cleanup_service.py
- Update intake.py to focus on publishing/adapters only
- Comprehensive test coverage

### Phase 2.2: Models Router Decomposition (Weeks 3-4)
- Extract model_search_service.py
- Extract model_detail_service.py
- Extract model_media_service.py
- Update models.py to focus on local authority only
- Comprehensive test coverage

### Phase 2.3: Database Context Split (Weeks 5-6)
- Split db.py into db_intake.py, db_models.py, db_working.py, db_archive_links.py
- Create db_migrations.py for schema management
- Rewrite db.py as connection factory + utilities
- Update all imports across codebase

### Phase 2.4: Working Router Optimization (Weeks 7-8)
- Extract working_groups_service.py
- Extract working_discovery_service.py
- Update working.py to delegate to services
- Refactor serialization helpers

---

## References

- [Phase 2 Refactoring Design](MODEL_CATALOG_PHASE_2_DESIGN.md)
- [Archive Linking Design](features/archive_linking/README.md) (Phase 2.5)
- [Model Export Specification](features/model_export/README.md) (Phase 2.6)
- [Local Model Storage & Naming Convention](LOCAL-MODEL-STORAGE-AND-NAMING-DESIGN.md)

