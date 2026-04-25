---
name: Phase 3.1 Implementation Task
about: Track Phase 3.1 implementation task (Edit Mode & Photo Management)
title: "[Phase 3.1] "
labels: phase-3, enhancement, model-catalog
assignees: ''
---

## Phase 3.1: Edit Mode & Photo Management

**Objective**: Add inline editing and photo management to model detail popup

**Scope**:
- Edit model metadata (name, description, tags, collection)
- Edit enrichment fields (print time, support type, difficulty, notes)
- Upload and manage model photos
- Conflict detection for concurrent edits

**Effort**: 30-35 hours | **Priority**: HIGH

---

## Implementation Tasks

### Core Components

- [ ] **Edit Form Component** (`model-detail-edit-form.js`)
  - Form validation (required fields, length checks)
  - Enrichment field editor
  - Advanced section (collapsible)
  - Tests: `test_edit_form.py`

- [ ] **Edit Mode Toggle** (enhance `model-detail-popup-card.js`)
  - Edit button in header
  - Toggle between display/edit rendering
  - Save/Cancel buttons
  - Tests: `test_edit_mode_toggle.spec.ts`

- [ ] **Conflict Detection** (enhance `model-detail-popup-card.js`)
  - Compare last_modified_timestamp
  - Conflict dialog with Reload/Overwrite/Cancel options
  - Tests: `test_conflict_detection.py`

- [ ] **Photo Gallery Tab** (enhance `model-detail-popup-card.js`)
  - Thumbnail grid view
  - Preview modal
  - Upload button (edit mode only)
  - Delete photo with confirmation
  - Set as preview
  - Tests: `test_gallery_flow.spec.ts`

### Services & Endpoints

- [ ] **Update Model Service** (`model_catalog.update_model`)
  - Validate required conflict token
  - Serialize form data
  - Call sidecar PATCH endpoint
  - Tests: `test_update_model_endpoint.py`

- [ ] **Photo Upload Service** (`model_catalog.upload_photo`)
  - Base64 photo validation (max 10MB)
  - Call Bambuddy API or sidecar
  - Return photo ID and URL
  - Tests: `test_photo_upload_endpoint.py`

- [ ] **Sidecar Endpoints**
  - `PATCH /api/models/{model_ref}` — Update model
  - `POST /api/models/{model_ref}/photos` — Upload photo
  - Tests: `test_sidecar_endpoints.py`

### Documentation & Testing

- [ ] Documentation: `phase-3.1-service-examples.yaml`
- [ ] Test Suite: 15+ tests covering all scenarios
- [ ] Manual Testing Checklist: Verify all features on desktop/mobile
- [ ] Implementation Guide: `phase-3.1-implementation-guide.md` ✅

---

## Testing Requirements

### Unit Tests
```
tests/phase3/
├── test_edit_form.py
├── test_conflict_detection.py
├── test_photo_upload_endpoint.py
├── test_update_model_endpoint.py
└── test_enrichment_fields.py
```

### Integration Tests
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
- [ ] Form validation works (reject empty name, etc.)
- [ ] Save works without conflicts
- [ ] Conflict detected and dialog shown correctly
- [ ] Reload discards changes
- [ ] Overwrite forces save
- [ ] Photo upload succeeds
- [ ] Photo gallery displays thumbnails
- [ ] Set as preview updates model
- [ ] Delete photo with confirmation
- [ ] Mobile viewport responsive
- [ ] Performance acceptable (<500ms form render)

---

## Success Criteria

- ✅ All 15+ tests pass
- ✅ Edit form fully functional with validation
- ✅ Conflict detection prevents data loss
- ✅ Photo upload/gallery works smoothly
- ✅ Documentation complete
- ✅ Mobile responsive
- ✅ Performance acceptable (<500ms)

---

## Dependencies

- Phase 3.0 MVP ✅
- Sidecar service running
- Manyfold API accessible
- HA 2024.1+

---

## References

- Implementation Guide: [phase-3.1-implementation-guide.md](../../docs/features/model_catalog/phase-3.1-implementation-guide.md)
- Roadmap: [phase-3.1-3.3-roadmap.md](../../docs/features/model_catalog/phase-3.1-3.3-roadmap.md)
- Design: [phase-3-detail-view-design.md](../../docs/features/model_catalog/phase-3-detail-view-design.md)

---

## Checklist

- [ ] Implementation started
- [ ] All tasks completed
- [ ] All tests passing
- [ ] Code reviewed
- [ ] Documentation updated
- [ ] Ready for Phase 3.2

---

/label phase-3 enhancement model-catalog
/assign @developer-name
