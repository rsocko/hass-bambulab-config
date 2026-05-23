# Phase 3.1 Implementation Guide: Edit Mode & Photo Management

**Scope**: Edit form, photo upload/gallery, save logic with conflict detection  
**Effort**: 30-35 hours  
**Priority**: HIGH  
**Status**: Ready for Development

**Post-Manyfold mapping**: legacy `Phase 3.1` now executes within current **Phase 4**.

---

## Overview

Phase 3.1 extends Phase 3.0's read-only detail popup with inline editing capabilities and photo management. Users can:
- Edit model metadata (name, description, tags, collection)
- Edit enrichment fields (print time, support type, difficulty, notes)
- Upload and manage model photos
- Handle conflicts when model changes upstream

---

## Architecture

### Components

1. **model-detail-edit-form.js** (New)
   - Edit form with validation
   - Enrichment field editor
   - Conflict detection UI

2. **model-detail-popup-card.js** (Enhanced)
   - Toggle edit mode
   - Integrate edit form
   - Integrate photo gallery
   - Save/cancel/conflict logic

3. **Sidecar Endpoints** (Enhanced)
   - `PATCH /api/models/{model_ref}` — Update model
   - `POST /api/models/{model_ref}/photos` — Upload photo

4. **HA Services** (New)
   - `model_catalog.update_model` — Commit edits
   - `model_catalog.upload_photo` — Upload photos

### Data Flow

```
User edits → Form validation → Conflict check → Save service → Sidecar update → Reload detail
```

---

## Implementation Tasks

### Task 1: Edit Form Component
**File**: `homeassistant/www/3d_printing/model_catalog/model-detail-edit-form.js`  
**Status**: ✅ Boilerplate created

**Checklist**:
- [ ] Populate form from model data
- [ ] Validate required fields (name, description)
- [ ] Validate field lengths (name: max 255 chars, description: max 5000)
- [ ] Handle enrichment fields
- [ ] Implement "Advanced" collapsible section
- [ ] Style with HA design tokens
- [ ] Test on mobile viewport

**Tests**:
```bash
tests/phase3/test_edit_form.py
```

**Reference**: See Phase 3.0 form patterns in print-history archive detail

---

### Task 2: Edit Mode Toggle
**File**: `homeassistant/www/3d_printing/model_catalog/model-detail-popup-card.js`

**Changes**:
- Add `[Edit]` button to header (visible when in Details tab)
- Add `_isEditMode` state flag
- Toggle between display and form rendering
- Add `[Save]` / `[Cancel]` buttons when editing

**Example**:
```javascript
toggleEditMode() {
  this._isEditMode = !this._isEditMode;
  this._render();
}

// In Details tab:
if (this._isEditMode) {
  return this._renderEditForm();
} else {
  return this._renderDetailsDisplay();
}
```

**Tests**:
```bash
tests/e2e/model_detail_edit_mode_toggle.spec.ts
```

---

### Task 3: Save/Conflict Detection
**File**: `homeassistant/www/3d_printing/model_catalog/model-detail-popup-card.js`

**Logic**:
1. Capture `last_modified_timestamp` on initial load
2. Before save, compare timestamp with upstream
3. If changed: Show conflict dialog with options:
   - "Reload" — Discard local, load upstream
   - "Overwrite" — Force save (last-write-wins)
   - "Cancel" — Keep editing

**Implementation**:
```javascript
async _handleSave(formData) {
  // Check for conflicts
  const response = await this._checkConflict(formData.model_ref);
  
  if (response.conflict) {
    this._showConflictDialog(response, formData);
    return;
  }
  
  // Save to sidecar
  await this._callSaveService(formData);
  
  // Reload model detail
  await this._loadModelDetail();
  this._isEditMode = false;
  this._render();
}
```

**Tests**:
```bash
tests/phase3/test_conflict_detection.py
```

---

### Task 4: Photo Gallery (Gallery Tab)
**File**: `homeassistant/www/3d_printing/model_catalog/model-detail-popup-card.js`  
**Gallery Tab Method**: `_renderGalleryTab()`

**Features**:
- Thumbnail grid view
- Preview modal (click thumbnail)
- Upload button (edit mode only)
- Delete photo (edit mode, with confirmation)
- Set as preview (star icon or context menu)

**Gallery Tab Structure**:
```html
<div class="gallery-container">
  <div class="gallery-grid">
    <div class="photo-thumbnail">
      <img src="..." />
      <div class="photo-actions">
        <button class="btn-preview">👁</button>
        <button class="btn-preview-star">⭐</button>
        <button class="btn-delete" (edit-mode-only)>🗑</button>
      </div>
    </div>
    ...
  </div>
  
  <div class="upload-section" (edit-mode-only)>
    <input type="file" multiple accept=".jpg,.png,.webp">
    <button>Upload Photos</button>
  </div>
</div>
```

**Tests**:
```bash
tests/e2e/model_detail_gallery_flow.spec.ts
```

---

### Task 5: Photo Upload Service
**File**: `homeassistant/packages/3d_printing/model_catalog/services/upload_photo.yaml`

**Service Definition**:
```yaml
model_catalog.upload_photo:
  description: Upload a photo to a model
  fields:
    model_ref:
      description: Model reference (public_id or model_id)
      example: "gridfinity-bin"
    photo_file:
      description: Base64-encoded photo or file path
      example: "data:image/jpeg;base64,..."
    set_as_preview:
      description: Set as preview photo
      example: false
```

**Implementation**:
1. Receive base64 photo from card
2. Validate file (JPG/PNG/WebP, max 10MB)
3. Call Bambuddy API (or sidecar endpoint)
4. Return photo ID and URL
5. Card updates gallery

**Tests**:
```bash
tests/phase3/test_photo_upload.py
```

---

### Task 6: Update Model Service
**File**: `homeassistant/packages/3d_printing/model_catalog/services/update_model.yaml`

**Service Definition**:
```yaml
model_catalog.update_model:
  description: Update model metadata and enrichment
  fields:
    model_ref:
      description: Model reference
      example: "gridfinity-bin"
    model_name:
      description: Model display name (optional)
    description:
      description: Model description (optional)
    tags:
      description: Comma-separated tags (optional)
    collection:
      description: Collection ID (optional)
    enrichment:
      description: Enrichment fields (optional)
      example:
        print_time_estimate: 3600
        support_type_hint: "tree"
        difficulty_level: "beginner"
```

**Implementation**:
1. Validate required conflict token
2. Serialize form data
3. Call sidecar PATCH endpoint
4. Return success/failure

**Sidecar Endpoint**: `PATCH /api/models/{model_ref}`
```python
@app.patch("/api/models/{model_ref}")
async def update_model(model_ref: str, request: ModelUpdateRequest):
    """Update model metadata and enrichment fields."""
    # 1. Resolve model reference
    model = resolve_model_ref(model_ref)
    
    # 2. Validate changes
    validate_model_update(model, request)
    
    # 3. Update Manyfold via API
    response = manyfold_client.patch_model(model.model_id, request)
    
    # 4. Update local enrichment
    update_enrichment_fields(model.model_id, request.enrichment)
    
    # 5. Return updated detail
    return get_model_detail(model_ref)
```

**Tests**:
```bash
tests/phase3/test_update_model_endpoint.py
```

---

### Task 7: Documentation & Examples
**Files**:
- `docs/features/model_catalog/phase-3.1-service-examples.yaml`
- `docs/features/model_catalog/phase-3.1-edit-guide.md`

**Examples**:
- Edit model via automation
- Upload photos programmatically
- Handle edit conflicts

---

## Testing Strategy

### Unit Tests (Python/pytest)
```
tests/phase3/
├── test_edit_form.py             # Form validation
├── test_conflict_detection.py     # Conflict logic
├── test_photo_upload_endpoint.py  # Upload service
├── test_update_model_endpoint.py  # Update service
└── test_enrichment_fields.py      # Enrichment validation
```

### Integration Tests (Playwright)
```
tests/e2e/
├── model_detail_edit_mode_toggle.spec.ts
├── model_detail_edit_flow.spec.ts
├── model_detail_gallery_flow.spec.ts
├── model_detail_conflict_resolution.spec.ts
└── model_detail_photo_upload.spec.ts
```

### Manual Testing Checklist
- [ ] Edit form renders correctly
- [ ] Form validation works (empty name rejected, etc.)
- [ ] Save works without conflicts
- [ ] Conflict detected and dialog shown
- [ ] Reload discards changes correctly
- [ ] Overwrite forces save correctly
- [ ] Photo upload succeeds
- [ ] Photo gallery displays thumbnails
- [ ] Set as preview updates model
- [ ] Delete photo with confirmation
- [ ] Mobile viewport works

---

## Success Criteria

- ✅ All 15+ tests pass
- ✅ Edit form fully functional with validation
- ✅ Conflict detection prevents data loss
- ✅ Photo upload/gallery works smoothly
- ✅ Documentation complete
- ✅ Mobile responsive
- ✅ Performance acceptable (<500ms form render)

---

## Dependencies

- Phase 3.0 MVP ✅ (required)
- Sidecar service running
- Manyfold API accessible
- HA 2024.1+ (for browser_mod compatibility)

---

## Rollback Plan

If Phase 3.1 causes issues:

1. Disable `model-detail-edit-form.js` resource
2. Remove edit button from `model-detail-popup-card.js`
3. Remove upload photo service
4. Remove update model service
5. Revert sidecar to Phase 3.0 (read-only)

---

## References

- Phase 3.0 Implementation: [phase-3-implementation-guide.md](/docs/features/model_catalog/planning/phase-3-guide.md)
- Design Document: [phase-3-detail-view-design.md](/docs/features/model_catalog/design/phase-3-detail-view.md)
- Print History Reference: [print-history-archive-actions-card.js](../../../homeassistant/www/3d_printing/print_history/print-history-archive-actions-card.js)
- Bambuddy REST API: [bambuddy/README.md](../../../bambuddy/README.md)
