# Issue #1490 Implementation Summary: Entity Types (Ideas + Working Groups)

**Status**: Backend COMPLETE ✅ | Frontend READY FOR INTEGRATION

**Scope**: One enum + 2 chips + minimal create + 2 promote actions. Lands membership plumbing once so Phase 3+ can render Ideas/WGs natively in Project/Collection/Tag views.

---

## What Was Implemented

### Backend (Complete)

#### 1. Database Schema Migration (v25)
- **File**: `sidecars/model_catalog/app/db_migrations.py`
- **Changes**:
  - Added `entity_type TEXT NOT NULL DEFAULT 'model'` column to `model_catalog_entries`
  - Added index on `entity_type` for efficient filtering
  - Default value ensures backward compatibility

#### 2. Data Model Updates
- **File**: `sidecars/model_catalog/app/models.py`
- **Changes**: Added `entity_type: str` field to `LocalModelEntry` dataclass

#### 3. CRUD Operations
- **File**: `sidecars/model_catalog/app/local_models.py`
- **Changes**:
  - Updated `create_local_model()` to accept `entity_type` parameter (default: `"model"`)
  - Updated `update_local_model()` to support changing entity_type via PATCH
  - Updated `_row_to_local_model_entry()` to read entity_type from DB rows
  - Row mapping handles backward compatibility (defaults to `"model"` if column absent)

#### 4. Promotion Logic Module
- **File**: `sidecars/model_catalog/app/promote.py` (NEW)
- **Exported Functions**:
  - `promote_entity()`: Atomically transition entities between types
  - `can_promote()`: Validate promotion paths
  - `dissolve_working_group()`: Placeholder for Phase 3 project-close behavior
- **Promotion Paths**:
  - `idea` → [`model`, `working_group`]
  - `working_group` → [`model`]
  - `model` → [] (terminal state)

#### 5. REST API Endpoints
- **File**: `sidecars/model_catalog/app/routers/models.py`
- **New/Updated Endpoints**:
  - **POST** `/api/local/models` — Create with `entity_type` parameter
  - **PUT** `/api/local/models/{id}/promote` — Transition entity type
  - **PATCH** `/api/local/models/{id}` — Update (now supports `entity_type`)
  - **GET** `/api/local/models/{id}` — Returns full entry with `entity_type`
  - **GET** `/api/local/models?limit=50&offset=0` — Returns all entries (now include `entity_type`)

#### 6. REST Commands for Home Assistant
- **File**: `homeassistant/packages/3d_printing/model_catalog/rest_commands/entity_types.yaml` (NEW)
- **Commands**:
  - `model_catalog_list_models_by_entity_type` — List all models (frontend filters by type)
  - `model_catalog_create_idea` — Quick-create idea via service call
  - `model_catalog_promote_entity` — Promote entity from HA automation

#### 7. Import in Router
- **File**: `sidecars/model_catalog/app/routers/models.py`
- **Added imports**: `from ..promote import promote_entity, can_promote`

---

## API Usage Examples

### Create an Idea
```bash
curl -X POST http://localhost:8000/api/local/models \
  -H "Content-Type: application/json" \
  -d '{
    "entity_type": "idea",
    "local_model_id": "desk-organizer-2025",
    "model_name": "Modular Desk Organizer",
    "model_description": "6-slot divider with adjustable heights",
    "tags": ["organizer", "desk"]
  }'
```

**Response**:
```json
{
  "success": true,
  "local_model_id": "desk-organizer-2025",
  "model_name": "Modular Desk Organizer",
  "entity_type": "idea",
  "summary": { ... }
}
```

### Promote Idea to Model
```bash
curl -X PUT http://localhost:8000/api/local/models/desk-organizer-2025/promote \
  -H "Content-Type: application/json" \
  -d '{
    "from_entity_type": "idea",
    "to_entity_type": "model"
  }'
```

**Response**:
```json
{
  "success": true,
  "local_model_id": "desk-organizer-2025",
  "entity_type": "model",
  "from_entity_type": "idea",
  "to_entity_type": "model",
  "summary": { ... }
}
```

### List Models Filtered by Entity Type (Frontend Job)
```bash
curl http://localhost:8000/api/local/models?limit=500
# Returns array with entity_type on each item:
# { "model_url": "...", "entity_type": "idea" | "working_group" | "model", ... }
```

---

## Frontend Integration Points

### What Exists (Ready to Extend)
- ✅ Sidecar API returns `entity_type` on all model responses
- ✅ REST commands available for create/promote via HA service calls
- ✅ Backend validation of promotion paths (frontend can check `can_promote()` via API or replicate the logic)

### What Needs Frontend Implementation (Phase 2.1)
See [ISSUE-1490-ENTITY-TYPES-FRONTEND-GUIDE.md](../ISSUE-1490-ENTITY-TYPES-FRONTEND-GUIDE.md) for detailed code patterns:

1. **Toolbar Chips** (`Show ideas`, `Show working groups`)
   - Toggle `_filterState.showIdeas` and `_filterState.showWorkingGroups`
   - Count entities of each type for badge display
   - Apply entity_type filter in `_applyFilters()`

2. **Quick-Add Idea Button** (`+ Add Idea`)
   - Call POST `/api/local/models` with `entity_type: "idea"`
   - Minimal form: title required, tags/description optional
   - Refresh model list on success

3. **Entity Type Badges** (💡 Idea, 🧰 Working Group)
   - Render on each card only if `entity_type !== 'model'`
   - Style with distinct colors per type

4. **Promote Actions** (popup overflow menu)
   - Show "Promote to Model" for ideas and working groups
   - Show "Promote to Working Group" for ideas
   - Call PUT `/api/local/models/{id}/promote` on confirm
   - Validate path before showing button using local promotion matrix

### Membership Plumbing (Phase 3+, Deferred)
- Render Ideas/WGs inline in Project views (same card style, different badge)
- Per-member candidate state in evaluating Projects (separate from this issue)
- Multi-select + bulk add to Project (handled by Projects/Collections phase)

---

## Testing the Backend

### Database Migration
```bash
cd sidecars/model_catalog
python -m pytest tests/ -k "test_migration" -v
# Verify schema includes entity_type column with default 'model'
```

### Create Idea and Promote
```bash
# 1. Start sidecar
python -m sidecars.model_catalog

# 2. Create idea
curl -X POST http://localhost:8000/api/local/models \
  -H "Content-Type: application/json" \
  -d '{"entity_type":"idea","local_model_id":"test-idea","model_name":"Test Idea"}'

# 3. Verify entity_type in response
# Expected: "entity_type": "idea"

# 4. Promote to model
curl -X PUT http://localhost:8000/api/local/models/test-idea/promote \
  -H "Content-Type: application/json" \
  -d '{"from_entity_type":"idea","to_entity_type":"model"}'

# 5. Verify promotion
# Expected: "entity_type": "model"

# 6. Try invalid promotion (model → idea) — should fail
curl -X PUT http://localhost:8000/api/local/models/test-idea/promote \
  -H "Content-Type: application/json" \
  -d '{"from_entity_type":"model","to_entity_type":"idea"}'
# Expected HTTP 400: "Invalid promotion path"
```

### List and Filter
```bash
# List all models (including ideas/working groups)
curl "http://localhost:8000/api/local/models?limit=50"

# Frontend filters in memory:
# const ideas = models.filter(m => m.entity_type === 'idea');
# const workingGroups = models.filter(m => m.entity_type === 'working_group');
# const onlyModels = models.filter(m => m.entity_type === 'model');
```

---

## Files Changed

### Backend
- ✅ `sidecars/model_catalog/app/db_migrations.py` — Migration 25
- ✅ `sidecars/model_catalog/app/models.py` — Added entity_type to LocalModelEntry
- ✅ `sidecars/model_catalog/app/local_models.py` — CRUD updates
- ✅ `sidecars/model_catalog/app/promote.py` — NEW promotion logic module
- ✅ `sidecars/model_catalog/app/routers/models.py` — API endpoints + imports

### Home Assistant
- ✅ `homeassistant/packages/3d_printing/model_catalog/rest_commands/entity_types.yaml` — NEW REST commands

### Documentation
- ✅ `docs/features/model_catalog/ISSUE-1490-ENTITY-TYPES-FRONTEND-GUIDE.md` — NEW frontend guide
- ✅ This file — Implementation summary

---

## Next Steps

### Phase 2.1 (Frontend Integration)
1. **Modify** `model-catalog-browser-card.js`:
   - Add filter state tracking for `showIdeas` and `showWorkingGroups`
   - Add toolbar chips (toggle filters + count badges)
   - Add entity type badges on cards
   - Add "Create Idea" button
   - Add promote actions in popup overflow

2. **Test** in HA:
   - Create ideas via UI
   - Toggle chips to show/hide ideas and working groups
   - Promote ideas to models
   - Verify card badges update correctly

### Phase 2.2 (Project Integration)
- Design deferred. When Projects/Collections phase lands, extend this to:
  - Render Ideas/WGs inline in Project views
  - Support candidate state tracking for Ideas
  - Enable bulk add-to-project from Catalog grid

### Phase 3+ (Full Membership)
- Ideas/WGs inherit all membership behavior (Project, Collection, Tag, Favorite, Visibility)
- Covered by existing schema; no further backend changes needed

---

## Design References

- **Catalog Redesign**: `docs/features/model_catalog/catalog-redesign-2026-05.md`
  - Section 5.1 (Ontology) — Entity type definitions and promotion paths
  - Section 5.9 (US-9, US-10) — Ideas and Working Groups as catalog citizens
- **Mockups**: `docs/features/model_catalog/design/mockups/catalog-redesign-mockups.html`
  - Sections "Catalog — Default landing", "Popup — Hero"

---

## Backward Compatibility

- ✅ Database migration adds NOT NULL DEFAULT 'model' column
- ✅ Existing models automatically get entity_type='model' on first query
- ✅ API responses include entity_type (new field, no breaking changes)
- ✅ CREATE/UPDATE endpoints accept entity_type (optional in PATCH, defaulting to no change)
- ✅ Promotion logic only runs on explicit PUT `/promote` call

**No forced data migrations or client updates required.**

---

## Success Criteria (Per #1490)

- ✅ **One enum**: `entity_type: model | idea | working_group` on catalog entries
- ✅ **2 promote actions**: Idea→Model, Idea→WG (WG→Model deferred to Phase 2.2)
- ✅ **Minimal create**: POST /api/local/models with entity_type parameter
- ✅ **Membership plumbing**: All three types share same membership/favorite/popup machinery
  - Not yet tested (Projects phase pending)
  - Schema supports it; deferred UI

---

## Deferred / Out of Scope

- ❌ Project/Collection integration (Phase 2.2)
- ❌ Per-member candidate state in evaluating Projects (Phase 3)
- ❌ Bulk promote or dissolve (Phase 3+)
- ❌ Historical backfill hooks (separate issue #1489)
- ❌ Slicer integration (separate issue #1486)
