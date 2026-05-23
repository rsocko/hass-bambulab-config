# Phase 3.1+ Roadmap: Model Detail View Evolution

**Status**: Planning  
**Prepared**: 2026-04-25  
**Based on**: Phase 3.0 MVP validated ✅

## Post-Manyfold Mapping Note

This roadmap keeps the legacy `Phase 3.1-3.3` file naming for continuity.

- Legacy Phases `3.1-3.3` now map to **Phase 4: UI Continuity and In-Flight Preservation**.
- The project-aware navigation portion that used to ride along with legacy `Phase 3.3` is now split from the narrower UI continuity slice and should be tracked against the current Phase 9 project-integration work when applicable.

---

## Overview

Phase 3.0 established the read-only detail popup with 4-tab interface. Phases 3.1–3.3 extend this with editing, media management, 3D inspection, and cross-system integration.

### Phasing Strategy

Each phase:
- ✅ Builds on proven patterns from Phase 3.0
- ✅ Maintains backward compatibility
- ✅ Can be deployed independently
- ✅ Includes test coverage
- ✅ Has clear success criteria

---

## Phase 3.1: Edit Mode & Photo Management

**Objective**: Enable inline enrichment editing and photo uploads without leaving HA

**Estimated Effort**: 30-35 hours  
**Priority**: HIGH (enables user feedback loop)  
**Dependencies**: Phase 3.0 MVP ✅

### Deliverables

#### 1. Edit Button & Toggle Mode
**File**: `homeassistant/www/3d_printing/model_catalog/model-detail-popup-card.js`

**Changes**:
- Add `[Edit]` button to header (visible in Details tab)
- Implement `_isEditMode` state flag
- Conditionally render form vs. display based on mode
- Add `[Save]` / `[Cancel]` buttons when in edit mode

```javascript
// Pseudo-code
toggleEditMode() {
  this._isEditMode = !this._isEditMode;
  this._render();
}

// In Details tab rendering:
if (this._isEditMode) {
  return this._renderDetailsForm(); // Editable form
} else {
  return this._renderDetailsDisplay(); // Read-only display
}
```

**Tests**: 
- Toggle enters/exits edit mode
- Form fields appear when editing
- Display reverts when canceling

#### 2. Editable Fields Form
**New Component**: `homeassistant/www/3d_printing/model_catalog/model-detail-edit-form.js`

**Editable Fields**:
- Model name (text input)
- Description (textarea with markdown preview)
- Tags (tag input with autocomplete)
- Collection assignment (dropdown)
- Creator (read-only, shown for context)
- Custom fields (dynamic based on enrichment schema)

**Enrichment Fields** (in collapsed "Advanced" section):
- Color scheme (color picker array)
- Print time estimate (number + unit)
- Support type hint (select: none / tree / linear / grid)
- Difficulty level (select: beginner / intermediate / advanced / expert)
- Print notes (textarea)
- License (text)
- Multi-color support (toggle)

**Validation**:
- Name required, max 255 chars
- Description max 5000 chars
- Tags comma-separated or chip-based
- Numbers must be positive
- Show inline validation errors

**Tests**:
- All fields render as expected
- Validation prevents invalid submission
- Markdown preview updates on change
- Form state persists while editing

#### 3. Save/Cancel Logic & HA Services
**New HA Services** (in `packages/3d_printing/model_catalog/services/`):

```yaml
# service: model_catalog.update_model
request:
  model_ref: string  # e.g., "gridfinity-bin"
  model_name: string (optional)
  description: string (optional)
  tags: list (optional)
  collection_id: string (optional)
  enrichment: object (optional)
    color_scheme: list
    print_time_seconds: number
    support_type_hint: string
    difficulty_level: string
    print_notes: string
    
response:
  success: boolean
  message: string
  updated_fields: list
  conflict: boolean  # if model changed upstream
```

**Implementation Pattern** (Bambuddy API-style):
1. Card calls REST command or service
2. HA calls Bambuddy `PATCH /models/{id}` endpoint
3. Bambuddy commits to Manyfold
4. Card reloads updated model detail from sidecar

**Sidecar Changes** (`sidecars/model_catalog/app/main.py`):
- Add `PATCH /api/models/{model_ref}` endpoint
- Validate fields before sending to Manyfold
- Update local SQLite enrichment table
- Return updated model detail

**Tests**:
- Valid update succeeds
- Invalid data rejected with error message
- Conflict detection (model changed upstream)
- Reload shows updated data

#### 4. Photo Management (Gallery Tab Implementation)
**File**: `homeassistant/www/3d_printing/model_catalog/model-detail-gallery-tab.js`

**Features**:
- Display photo grid (thumbnail view)
- Preview modal for full-size image
- Upload button (in edit mode)
- Set preview photo (context menu or button in edit mode)
- Delete photo (in edit mode, confirmation)
- Drag-to-reorder (in edit mode, optional)

**Photo Upload Mechanism**:
- Use `shell_command` (multipart/form-data required)
- OR use Bambuddy API directly with base64 encoding
- Support JPG, PNG, WebP (max 10MB)
- Thumbnail generation via Manyfold

**New HA Service**:
```yaml
# service: model_catalog.upload_photo
request:
  model_ref: string
  photo_file: string  # base64 or path
  set_as_preview: boolean (optional)
  
response:
  success: boolean
  photo_id: string
  photo_url: string
```

**Tests**:
- Gallery displays existing photos
- Upload adds new photo
- Preview modal opens/closes
- Delete removes photo
- Set preview updates model

#### 5. Conflict Detection & Reload
**Scenario**: User edits model, but another user (or Manyfold UI) updated it meanwhile.

**Implementation**:
- Include `last_modified_timestamp` in model detail response
- Before save, check if upstream timestamp changed
- If conflict: Show dialog with options:
  - "Reload" — Discard local changes, load upstream version
  - "Overwrite" — Force save local changes (last-write-wins)
  - "Cancel" — Keep editing, don't save

**Tests**:
- Conflict detected correctly
- Reload discards local changes
- Overwrite succeeds with warning

#### 6. Documentation & Examples
**Files**:
- `docs/features/model_catalog/phase-3.1-edit-guide.md` — Setup, examples, API reference
- `docs/features/model_catalog/phase-3.1-service-examples.yaml` — Example automations

**Examples**:
- Automation: "On model browser selection, open detail popup in edit mode"
- Service call: Update multiple fields at once
- Error handling: What to do if save fails

---

## Phase 3.2: 3D Viewer with Three.js

**Objective**: Display and inspect 3D geometry directly in HA

**Estimated Effort**: 40-45 hours  
**Priority**: MEDIUM (improves model inspection UX)  
**Dependencies**: Phase 3.0 MVP ✅  (Can implement in parallel with 3.1)

### Deliverables

#### 1. 3D Viewer Tab Implementation
**File**: `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js`

**Features**:
- Three.js scene with STL/3MF rendering
- File selector (for multi-file models)
- Rotation/zoom/pan controls
- Build volume visualization (Bambu P1S: 256×256×256mm)
- Layer coloring (optional)
- Measurements tool (optional for 3.2+)

**Architecture**:
- Extend `model-detail-popup-card.js` with 3D viewer child component
- Lazy-load Three.js from CDN
- Fetch 3D model files from Manyfold URLs
- Cache parsed geometry in session storage

**File Types Supported**:
- STL (ASCII & binary)
- 3MF (using lib3mf or three-bvh-csg)
- OBJ (optional)

#### 2. Sidecar 3D Geometry Endpoint
**Endpoint**: `GET /api/models/{model_ref}/geometry/{file_id}`

**Purpose**: 
- Proxy STL/3MF files from Manyfold
- Optional: Convert 3MF → STL for compatibility
- Cache parsed bounding box for build volume overlay

**Response**:
- Binary STL or JSON-encoded geometry
- Bounding box (min/max)
- Layer information (if available in 3MF)

#### 3. Build Volume Overlay
**Purpose**: Show wireframe build platform relative to model

**Implementation**:
- Bambu P1S: 256×256×256mm (or user-configurable)
- Render as transparent grid lines
- Toggle on/off in viewer controls

**Tests**:
- Build volume displays correctly
- Model scales appropriately
- Rotation/zoom work smoothly

#### 4. Layer Coloring (Optional)
**Purpose**: Visualize layer structure for support/multi-color planning

**Implementation**:
- If 3MF contains layer data: parse and color by layer
- Otherwise: auto-slice at 0.2mm intervals and color
- Color gradient: Blue (bottom) → Red (top)
- Toggle on/off, adjust slice height

#### 5. Measurement Tool (Optional for 3.2+)
**Purpose**: Measure distance between points on model

**Implementation**:
- Click two points on model surface
- Display 3D distance
- Optional: Project to XY plane and show footprint

---

## Phase 3.3: Cross-System Integration

**Objective**: Enable navigation between models, archives, and projects

**Estimated Effort**: 25-30 hours  
**Priority**: MEDIUM-LOW (enhancement, not blocking)  
**Dependencies**: Phase 3.0 MVP ✅, print_history ✅, print_statistics ✅

### Deliverables

#### 1. Linked Archives Enhanced View
**Current**: Phase 3.0 shows archive links in "Linked Prints" tab

**Enhancement** (3.3):
- Click archive to open archive detail popup (print-history pattern)
- Show archive thumbnail, date, status
- Quick filter: "Show all versions" / "Show successful prints"
- Sorting: By date, by filament, by status

#### 2. Related Models Navigation
**Purpose**: "Users who printed this also printed..."

**Implementation**:
- Add "Related Models" section in Details tab
- Fetch from Manyfold `/models/{id}/related` API
- Show similarity score (0-100%)
- Click to navigate to related model detail

**Sidecar Endpoint**: `GET /api/models/{model_ref}/related`

#### 3. Model ↔ Archive ↔ Project Navigation
**Purpose**: Navigate seamlessly between concepts

**Implementation**:
- Archive detail → "View Model" link (opens Phase 3.0 popup)
- Model detail → "Print this model" link (queues to print_queue)
- Project detail → "View all models in project" (filters model browser)

**New Services**:
```yaml
# service: model_catalog.queue_model_for_print (historical reference; retired)
request:
  model_ref: string
  filament_type: string (optional)
  print_settings: object (optional)
  
# service: model_catalog.navigate_to_model
request:
  model_ref: string
  
# service: print_history.navigate_to_linked_model
request:
  archive_id: number
```

#### 4. Cross-System Search
**Purpose**: Search across models, archives, projects in one place

**Implementation** (Optional):
- Add global search entity in HA
- Search by model name, creator, tags, filament, status
- Return unified results (models + archives + projects)
- Click result to navigate to appropriate detail view

#### 5. Unified Timeline View (Optional)
**Purpose**: Visualize model print history over time

**Implementation**:
- For a given model, show all linked archives on timeline
- Highlight successful vs. failed prints
- Hover to see details (date, duration, filament, result)
- Click to navigate to archive

---

## Implementation Timeline

### Recommended Sequence

```
Week 1-2: Phase 3.1 (Edit Mode)
  - Days 1-2: Edit form & validation
  - Days 3-4: Save/conflict logic
  - Days 5-7: Photo gallery & upload
  - Days 8-10: Tests & documentation

Week 3: Phase 3.2 (3D Viewer)
  - Days 1-3: Three.js integration
  - Days 4-5: File selector & controls
  - Days 6-7: Build volume overlay
  - Days 8: Tests & performance tuning

Week 4: Phase 3.3 (Integration)
  - Days 1-2: Enhanced archive linking
  - Days 3-4: Related models navigation
  - Days 5-6: Cross-system services
  - Days 7-8: Tests & documentation
```

**Parallel Work**:
- Phases 3.1 and 3.2 can be developed in parallel (different tabs)
- Phase 3.3 builds on 3.0/3.1, doesn't block either

---

## Architecture Pattern Review

All phases follow Phase 3.0 established patterns:

### Layer 1: Sidecar (Backend)
```
sidecars/model_catalog/app/main.py

GET /api/models/{ref}           ← Phase 3.0
GET /api/models/{ref}/detail    ← Phase 3.0
PATCH /api/models/{ref}         ← Phase 3.1 (update)
POST /api/models/{ref}/photos   ← Phase 3.1 (upload)
GET /api/models/{ref}/geometry  ← Phase 3.2
GET /api/models/{ref}/related   ← Phase 3.3
```

### Layer 2: HA Integration
```
homeassistant/packages/3d_printing/model_catalog/

helpers/                        ← Phase 3.0
rest_commands/                  ← Phase 3.0 + 3.1
services/                       ← Phase 3.1+3.3 (new)
automations/                    ← Phase 3.1+ (enhanced)
```

### Layer 3: Frontend (Custom Cards)
```
homeassistant/www/3d_printing/model_catalog/

model-detail-popup-card.js           ← Phase 3.0, enhanced in 3.1
model-detail-edit-form.js            ← Phase 3.1 (new)
model-detail-gallery-tab.js          ← Phase 3.1 (new)
model-detail-3d-viewer-tab.js        ← Phase 3.2 (new)
model-detail-related-models.js       ← Phase 3.3 (new)
```

---

## Testing Strategy

### Unit Tests (pytest)
```
tests/phase3/
  test_model_detail_endpoint.py       ← Phase 3.0 ✅
  test_model_detail_integration.py    ← Phase 3.0 ✅
  test_model_update_endpoint.py       ← Phase 3.1 (new)
  test_photo_upload_endpoint.py       ← Phase 3.1 (new)
  test_geometry_endpoint.py           ← Phase 3.2 (new)
  test_related_models_endpoint.py     ← Phase 3.3 (new)
```

### Integration Tests (Playwright)
```
tests/e2e/
  model_detail_edit_flow.spec.ts      ← Phase 3.1 (new)
  model_detail_gallery_flow.spec.ts   ← Phase 3.1 (new)
  model_detail_3d_viewer_flow.spec.ts ← Phase 3.2 (new)
  cross_system_navigation.spec.ts     ← Phase 3.3 (new)
```

### Test Coverage Goals
- Phase 3.1: 85%+ coverage for edit logic, photo upload
- Phase 3.2: 80%+ coverage for geometry loading, viewer controls
- Phase 3.3: 75%+ coverage for navigation, cross-system queries

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Conflict detection complexity | Start simple (timestamp-based), add merge logic later if needed |
| Photo upload file handling | Use base64 encoding via HA service first, shell_command as fallback |
| 3D viewer performance with large models | Lazy-load Three.js, cache parsed geometry, limit to 10MB files |
| Cross-system navigation complexity | Use event-based routing (HA services), avoid tight coupling |
| Breaking changes to Manyfold API | Vendor Manyfold client, pin versions, add API compatibility layer |

---

## Success Criteria

### Phase 3.1 ✅ Complete When:
- [ ] Edit form renders and validates
- [ ] Save/cancel works without conflicts
- [ ] Photo upload succeeds
- [ ] Gallery displays photos
- [ ] 15+ tests pass
- [ ] Documentation complete

### Phase 3.2 ✅ Complete When:
- [ ] 3D viewer renders STL/3MF
- [ ] Build volume overlay displays
- [ ] Rotation/zoom/pan work smoothly
- [ ] Performance acceptable (<500ms load)
- [ ] 12+ tests pass

### Phase 3.3 ✅ Complete When:
- [ ] Archive links clickable and navigate
- [ ] Related models appear and navigate
- [ ] Cross-system services work
- [ ] Timeline view (optional) displays
- [ ] 10+ tests pass

---

## Dependencies & Blockers

| Phase | Depends On | Status |
|-------|-----------|--------|
| 3.1 | 3.0 MVP | ✅ Ready |
| 3.2 | 3.0 MVP | ✅ Ready (parallel with 3.1) |
| 3.3 | 3.0 + print_history | ✅ Ready (parallel with 3.1+3.2) |

**No external blockers** — All three phases can be started immediately after Phase 3.0 release.

---

## Resource Allocation

- **Backend** (Sidecar): 15 hours total across all phases
- **HA Integration** (Services/Helpers): 20 hours total
- **Frontend** (Custom Cards): 60 hours total
- **Testing**: 20 hours total
- **Documentation**: 10 hours total

**Total**: ~125 hours (3-4 weeks for 1 FTE, or 6-8 weeks with part-time engagement)

---

## Next Actions

1. ✅ **Validate Phase 3.0** (complete, tests pass)
2. ⏳ **Create Phase 3.1 Epic** (GitHub issue, break into tasks)
3. ⏳ **Assign 3.1 Development** (start edit form implementation)
4. ⏳ **Prepare 3.2 Design** (Three.js integration spike)
5. ⏳ **Plan 3.3 API Extensions** (coordinate with print_history team)

---

## References

- **Phase 3.0 Implementation Guide**: [phase-3-implementation-guide.md](../phase-3-implementation-guide.md)
- **Phase 3.0 Design Document**: [phase-3-detail-view-design.md](../phase-3-detail-view-design.md)
- **Print History Reference** (similar patterns): [print-history-archive-actions-card.js](../../../homeassistant/www/3d_printing/print_history/print-history-archive-actions-card.js)
- **Bambuddy REST API Docs**: [bambuddy/README.md](../../../bambuddy/README.md)
- **Three.js Documentation**: https://threejs.org/docs/

---

**Prepared By**: GitHub Copilot  
**Status**: Ready for Planning & Assignment  
**Last Updated**: 2026-04-25
