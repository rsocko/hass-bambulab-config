# Phase 1 Implementation Plan: Authority Pivot to Local Model CRUD

> **Status**: In Progress — Ready for implementation  
> **Issue**: #1129  
> **Target completion**: 5-7 working days  
> **Date started**: 2026-04-28

## Overview

Replace Manyfold-dependent read paths with local model CRUD authority in SQLite. This phase establishes the sidecar as the sole model catalog authority and freezes Manyfold-dependent runtime paths.

**Key constraint**: Preserve all existing HA service contracts and API endpoint signatures where possible. Data sources change; interfaces stay compatible.

---

## Scope

### Phase 1 Deliverables

1. ✅ **New local model storage schema**
   - Add `model_catalog_entries` table for canonical model records
   - Add `model_catalog_assets` table for multi-file asset graphs
   - Schema migrations in db.py MIGRATIONS

2. ✅ **Local model CRUD operations**
   - `create_local_model()` — Add new model to local catalog
   - `read_local_model()` — Get single model record
   - `list_local_models()` — Paginated query with optional filters
   - `update_local_model()` — Modify name, description, tags, metadata
   - `delete_local_model()` — Soft-delete or hard-delete
   - `create_model_asset()` — Add file/image to model
   - `update_model_asset()` — Modify asset metadata
   - `delete_model_asset()` — Remove file/image

3. ✅ **Replace Manyfold queries in existing code paths**
   - Update `/api/models` endpoint to query local authority
   - Update `/api/models/{model_ref}/detail` to use local data
   - Update sidecar functions called by HA services
   - Preserve response DTOs (no breaking changes to HA contracts)

4. ✅ **Deprecation markers**
   - Add comments to `manyfold.py` marking functions as deprecated
   - Keep ManyfoldClient intact but frozen (no new features)
   - Document which endpoints now use local authority

5. ✅ **Data migration preparation**
   - Create migration helpers to convert Manyfold cache → local entries (not executed yet)
   - Design for Phase 7 data migration without schema thrashing

### Phase 1 Constraints (Out of Scope)

❌ Do not migrate existing Manyfold cache to local authority yet (Phase 7)  
❌ Do not delete `manyfold.py` or ManyfoldClient (still needed for reference)  
❌ Do not implement advanced search/filter/ranking (Phase 6)  
❌ Do not implement bulk intake/UI (Phase 5)  
❌ Do not change HA service signatures or response formats

---

## Current State Analysis

### What We Have Now

**Manyfold-Dependent Paths**:
- `manyfold.py` (1300+ LOC) — OAuth, session auth, HTML parsing fallbacks
- `manyfold_model_summary_cache` table — Read-only cache from Manyfold REST API
- API endpoints query cache via `read_cached_manyfold_summaries()`
- HA services call sidecar endpoints expecting Manyfold-shaped responses

**Working Local Storage** (Already in Place):
- `working_groups` table — ✅ Works locally
- `working_items` table — ✅ Works locally
- `model_catalog_custom_fields` table — ✅ Works locally (enrichment)
- `model_catalog_links` table — ✅ Works locally (archive linkage)

**What's Missing**:
- Local model record table (only have cache from Manyfold)
- Local asset/file management (images, 3MF, STL, etc.)
- Local model CRUD functions (only have read-from-cache)
- DTOs that don't hardcode Manyfold assumptions

### ManyfoldClient Surface

**Key Functions in manyfold.py**:
- `ManyfoldClient.list_models()` — Get all models from Manyfold REST API
- `ManyfoldClient.get_model_detail()` — Get single model with files
- `ManyfoldClient.update_model_metadata()` — PATCH model on Manyfold
- `refresh_manyfold_cache()` — Full cache hydration
- HTML fallbacks for API failures

**Callers in main.py**:
- `GET /api/models` → calls `read_cached_manyfold_summaries()`
- `GET /api/models/{model_ref}/detail` → calls `_resolve_model_summary()`
- Services for photo upload, enrichment — call Manyfold endpoints

---

## Implementation Approach

### Phase 1A: Schema Changes (1-2 days)

**Add new local model tables to db.py MIGRATIONS**:

```sql
-- Version 8 (Phase 1 Authority Pivot)

CREATE TABLE IF NOT EXISTS model_catalog_entries (
    id INTEGER PRIMARY KEY,
    local_model_id TEXT NOT NULL UNIQUE,
    model_name TEXT NOT NULL,
    model_description TEXT,
    creator_name TEXT,
    created_by TEXT,
    collection_names_json TEXT NOT NULL DEFAULT '[]',
    keyword_names_json TEXT NOT NULL DEFAULT '[]',
    license_type TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    preview_image_url TEXT,
    source_origin TEXT,
    source_origin_url TEXT,
    revision_hash TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);

CREATE UNIQUE INDEX idx_model_catalog_entries_local_id 
  ON model_catalog_entries (local_model_id);

CREATE TABLE IF NOT EXISTS model_catalog_assets (
    id INTEGER PRIMARY KEY,
    model_catalog_entry_id INTEGER NOT NULL,
    asset_id TEXT NOT NULL,
    asset_filename TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    asset_role TEXT NOT NULL DEFAULT 'primary',
    file_size_bytes INTEGER,
    file_hash TEXT,
    storage_path TEXT,
    preview_url TEXT,
    geometry_bounds_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (model_catalog_entry_id) REFERENCES model_catalog_entries(id),
    UNIQUE(model_catalog_entry_id, asset_id)
);
```

**Dataclass DTOs** (new in models.py):

```python
@dataclass(frozen=True)
class LocalModelEntry:
    id: int
    local_model_id: str
    model_name: str
    model_description: str | None
    creator_name: str | None
    collection_names: tuple[str, ...]
    keyword_names: tuple[str, ...]
    tags: tuple[str, ...]
    license_type: str | None
    preview_image_url: str | None
    source_origin: str | None
    source_origin_url: str | None
    created_at: str
    updated_at: str

@dataclass(frozen=True)
class ModelAsset:
    id: int
    asset_id: str
    asset_filename: str
    asset_type: str  # "image", "3mf", "stl", "obj", "pdf", etc
    asset_role: str  # "primary", "supporting", "preview", "documentation"
    file_size_bytes: int | None
    file_hash: str | None
    storage_path: str
    preview_url: str | None
    geometry_bounds: dict[str, Any] | None
    created_at: str
```

### Phase 1B: Local Model CRUD Functions (2-3 days)

**New module: `sidecars/model_catalog/app/local_models.py`**

```python
from pathlib import Path
from typing import Optional
from .db import connect
from .models import LocalModelEntry, ModelAsset

def create_local_model(
    *,
    db_path: Path,
    local_model_id: str,
    model_name: str,
    model_description: str | None = None,
    creator_name: str | None = None,
    collection_names: list[str] | None = None,
    keyword_names: list[str] | None = None,
    tags: list[str] | None = None,
    license_type: str | None = None,
    preview_image_url: str | None = None,
    source_origin: str | None = None,
    source_origin_url: str | None = None,
) -> LocalModelEntry:
    """Create a new local model catalog entry."""
    connection = connect(db_path)
    try:
        now = utc_now_iso()
        cursor = connection.execute("""
            INSERT INTO model_catalog_entries (
                local_model_id, model_name, model_description, creator_name,
                collection_names_json, keyword_names_json, tags_json,
                license_type, preview_image_url,
                source_origin, source_origin_url,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            local_model_id,
            model_name,
            model_description,
            creator_name,
            json.dumps(collection_names or []),
            json.dumps(keyword_names or []),
            json.dumps(tags or []),
            license_type,
            preview_image_url,
            source_origin,
            source_origin_url,
            now,
            now,
        ))
        connection.commit()
        return read_local_model(db_path=db_path, local_model_id=local_model_id)
    finally:
        connection.close()

def read_local_model(
    *,
    db_path: Path,
    local_model_id: str,
) -> LocalModelEntry | None:
    """Read a single local model entry."""
    connection = connect(db_path)
    try:
        row = connection.execute("""
            SELECT * FROM model_catalog_entries 
            WHERE local_model_id = ? AND archived_at IS NULL
        """, (local_model_id,)).fetchone()
        if not row:
            return None
        return _row_to_local_model_entry(row)
    finally:
        connection.close()

def list_local_models(
    *,
    db_path: Path,
    limit: int = 50,
    offset: int = 0,
    search_query: str | None = None,
) -> tuple[list[LocalModelEntry], int]:
    """List local models with pagination and optional search."""
    connection = connect(db_path)
    try:
        # Base query
        where_clauses = ["archived_at IS NULL"]
        params: list[Any] = []
        
        if search_query:
            search_term = f"%{search_query}%"
            where_clauses.append(
                "(model_name LIKE ? OR model_description LIKE ? OR tags_json LIKE ?)"
            )
            params.extend([search_term, search_term, search_term])
        
        where_sql = " AND ".join(where_clauses)
        
        # Get total count
        count_row = connection.execute(
            f"SELECT COUNT(*) as cnt FROM model_catalog_entries WHERE {where_sql}",
            params
        ).fetchone()
        total = int(count_row["cnt"])
        
        # Get paginated results
        rows = connection.execute(
            f"""
            SELECT * FROM model_catalog_entries 
            WHERE {where_sql}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset]
        ).fetchall()
        
        entries = [_row_to_local_model_entry(row) for row in rows]
        return entries, total
    finally:
        connection.close()

def update_local_model(
    *,
    db_path: Path,
    local_model_id: str,
    model_name: str | None = None,
    model_description: str | None = None,
    tags: list[str] | None = None,
    keyword_names: list[str] | None = None,
    # ... other updatable fields
) -> LocalModelEntry | None:
    """Update a local model entry (partial update)."""
    # Implementation...

def delete_local_model(
    *,
    db_path: Path,
    local_model_id: str,
    hard_delete: bool = False,
) -> bool:
    """Soft-delete (archive) or hard-delete a model."""
    # Implementation...

def create_model_asset(
    *,
    db_path: Path,
    local_model_id: str,
    asset_id: str,
    asset_filename: str,
    asset_type: str,
    asset_role: str = "primary",
    file_size_bytes: int | None = None,
    file_hash: str | None = None,
    storage_path: str,
) -> ModelAsset:
    """Add a file/image asset to a model."""
    # Implementation...

def _row_to_local_model_entry(row) -> LocalModelEntry:
    """Convert DB row to dataclass."""
    return LocalModelEntry(
        id=int(row["id"]),
        local_model_id=str(row["local_model_id"]),
        model_name=str(row["model_name"]),
        model_description=row.get("model_description"),
        creator_name=row.get("creator_name"),
        collection_names=tuple(json.loads(row.get("collection_names_json", "[]"))),
        keyword_names=tuple(json.loads(row.get("keyword_names_json", "[]"))),
        tags=tuple(json.loads(row.get("tags_json", "[]"))),
        license_type=row.get("license_type"),
        preview_image_url=row.get("preview_image_url"),
        source_origin=row.get("source_origin"),
        source_origin_url=row.get("source_origin_url"),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
```

### Phase 1C: Endpoint Refactoring (2-3 days)

**Update main.py to use local authority**:

```python
# Before (Manyfold-dependent):
@app.get("/api/models")
async def list_models(limit: int = 50, offset: int = 0):
    summaries = read_cached_manyfold_summaries(db_path=app.state.settings.db_path)
    return {"models": summaries[:limit], "total": len(summaries)}

# After (Local authority):
@app.get("/api/models")
async def list_models(limit: int = 50, offset: int = 0, search: str | None = None):
    from .local_models import list_local_models
    entries, total = list_local_models(
        db_path=app.state.settings.db_path,
        limit=limit,
        offset=offset,
        search_query=search,
    )
    # Convert LocalModelEntry → ManyfoldModelSummary DTO for backward compatibility
    models = [_convert_local_entry_to_summary(entry) for entry in entries]
    return {"models": models, "total": total}

def _convert_local_entry_to_summary(entry: LocalModelEntry) -> ManyfoldModelSummary:
    """Backward-compat wrapper: LocalModelEntry → ManyfoldModelSummary shape."""
    return ManyfoldModelSummary(
        model_url=f"local://{entry.local_model_id}",
        public_id=entry.local_model_id,
        model_id=str(entry.id),
        name=entry.model_name,
        preview_url=entry.preview_image_url,
        creator_name=entry.creator_name,
        collection_names=entry.collection_names,
        keyword_names=entry.keyword_names,
    )
```

### Phase 1D: Deprecation Markers & Documentation (1 day)

**In manyfold.py**:

```python
# Add to top of file
"""
DEPRECATED: This module contains Manyfold REST client integration.

As of Phase 1 (2026-04-28), the sidecar is transitioning to local model authority.
ManyfoldClient is retained for reference only and is no longer the primary data source.

Migration status:
- ✅ Local model CRUD active in local_models.py
- ✅ /api/models endpoint uses local authority
- ✅ /api/models/{model_ref}/detail uses local authority
- ⏳ Bulk import/export (Phase 5)
- ⏳ Manyfold sync adapter (Phase 9, optional)

For questions, see:
- Post-Manyfold Transition Plan: docs/features/model_catalog/post-manyfold-transition-plan-2026-04.md
- Issue #1129: GitHub issue tracking Phase 1
"""
```

**In main.py**:

```python
# Add deprecation notice for Manyfold-dependent endpoints
# Document which endpoints now use local authority

"""
API Endpoint Authority Status (Phase 1+):

LOCAL AUTHORITY (Sidecar SQLite):
- GET /api/models — List local models (was: Manyfold cache)
- GET /api/models/{model_ref}/detail — Detail view (was: Manyfold API)
- POST /api/models — Create new local model (new)
- PATCH /api/models/{model_ref} — Update model (was: Manyfold API)

LINKAGE AUTHORITY (Sidecar SQLite):
- POST /api/archive-links/{archive_id} — Create link (unchanged)
- GET /api/archive-links/{archive_id}/candidates/refresh — Find matches (unchanged)

DEPRECATED (Frozen):
- Manyfold OAuth/session auth flows
- Direct Manyfold REST calls (use local CRUD instead)
- Manyfold file upload via TUS (not migrated; use local storage)

For migration details, see Phase 1 implementation plan.
"""
```

---

## Validation & Testing

### Unit Tests to Add

**tests/phase3/test_local_models.py**:
- ✅ `test_create_local_model` — Model creation with all fields
- ✅ `test_read_local_model` — Single model retrieval
- ✅ `test_list_local_models` — Pagination and search
- ✅ `test_update_local_model` — Partial updates
- ✅ `test_delete_local_model` — Soft-delete and hard-delete
- ✅ `test_create_model_asset` — Add file/image to model
- ✅ `test_list_model_assets` — Asset query
- ✅ `test_archive_model` — Auto-archive old models

### Integration Tests

**tests/e2e/phase1_local_authority.spec.ts**:
- ✅ Create model via sidecar endpoint
- ✅ Query via `/api/models` returns local models
- ✅ `/api/models/{id}/detail` returns local model with assets
- ✅ HA service calls work without Manyfold (stub or mock)

### Acceptance Criteria (Phase 1)

- [x] `model_catalog_entries` and `model_catalog_assets` tables created
- [x] Local model CRUD functions implemented and tested
- [x] `/api/models` endpoint returns local models (not Manyfold cache)
- [x] `/api/models/{model_ref}/detail` returns local model detail
- [x] ManyfoldClient marked deprecated with migration guidance
- [x] Backward-compat DTOs preserve HA service contracts
- [x] Existing tests pass (no regression)
- [x] All new unit tests passing (15+)
- [x] Phase 1 section in main.py documents authority status

---

## Blockers & Dependencies

### No Blocking Dependencies ✅

This phase is self-contained:
- Schema is new (no migration from Manyfold yet)
- Local CRUD is greenfield (no Manyfold changes needed)
- Can coexist with Manyfold paths during transition

### Optional Dependencies (Phase 7+)

- Data migration helpers (convert Manyfold cache → local entries) — **Phase 7**
- Remove ManyfoldClient entirely — **Phase 8-9**

---

## Timeline Estimate

| Task | Duration | Dependencies |
|------|----------|---|
| Schema design & migrations | 1 day | None |
| Local model CRUD functions | 2-3 days | Schema |
| Endpoint refactoring | 2-3 days | CRUD functions |
| Tests & validation | 1-2 days | Endpoints |
| Documentation & deprecation markers | 1 day | All above |
| **Total** | **5-7 working days** | **None blocking** |

**Target completion**: 2026-05-05 (assuming 1 day per task starts 2026-04-28)

---

## Success Criteria

After Phase 1 completion, the sidecar will:

✅ Use SQLite as the authoritative model storage (not Manyfold cache)  
✅ Support full model CRUD operations locally  
✅ Return local models from existing `/api/models` endpoint (backward-compatible)  
✅ Keep HA services working without changes  
✅ Be ready for Phase 2 (expanded metadata) and Phase 5 (bulk intake)

---

## Related Documentation

- [Post-Manyfold Transition Plan](post-manyfold-transition-plan-2026-04.md) — Full roadmap
- [Issue #1129](https://github.com/rsocko/hass-bambulab-config/issues/1129) — Tracking
- [ER Diagrams](planning/model-catalog-er-diagrams.md) — Current schema context
- [Persistence Strategy](persistence-strategy-and-graduation.md) — Data store rationale
