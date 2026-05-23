# Phase 3.1-3.3 Development Checklist

**Timeline**: Week 1-4 (est.) | **Total Effort**: ~125 hours | **Status**: Ready for Development

---

## Quick Links

- 📋 **Roadmap**: [phase-3.1-3.3-roadmap.md](../phase-3.1-3.3-roadmap.md) (comprehensive planning)
- 📚 **Phase 3.1 Guide**: [phase-3.1-implementation-guide.md](../phase-3.1-implementation-guide.md) (edit + photos)
- 📚 **Phase 3.2 Guide**: [phase-3.2-implementation-guide.md](../phase-3.2-implementation-guide.md) (3D viewer)
- 📚 **Phase 3.3 Guide**: [phase-3.3-implementation-guide.md](../phase-3.3-implementation-guide.md) (cross-system)
- 🎫 **GitHub Issues**: [.github/ISSUE_TEMPLATE/](../.github/ISSUE_TEMPLATE/)

---

## Development Phases Overview

```
Phase 3.1 (Edit Mode & Photo Management)
├─ Effort: 30-35 hours
├─ Timeline: Week 1-2
├─ Priority: HIGH (blocking for user feedback)
└─ Status: Ready to start

Phase 3.2 (3D Viewer with Three.js)
├─ Effort: 40-45 hours
├─ Timeline: Week 3 (can be parallel with 3.1)
├─ Priority: MEDIUM
└─ Status: Tasks 1-4 Complete ✅

Phase 3.3 (Cross-System Integration)
├─ Effort: 25-30 hours
├─ Timeline: Week 4 (can be parallel with 3.1-3.2)
├─ Priority: MEDIUM-LOW
└─ Status: Ready to start
```

---

## Phase 3.1: Edit Mode & Photo Management

### Component Scaffolding

- ✅ `model-detail-edit-form.js` (190 lines, boilerplate created)
- ⏳ `model-detail-popup-card.js` enhancements:
  - Edit button and mode toggle
  - Conflict detection dialog
  - Gallery tab implementation

### Services & Endpoints

- ⏳ `model_catalog.update_model` service (HA YAML)
- ⏳ `model_catalog.upload_photo` service (HA YAML)
- ⏳ Sidecar endpoints:
  - `PATCH /api/models/{model_ref}`
  - `POST /api/models/{model_ref}/photos`

### Testing

- ⏳ Unit tests: `test_edit_form.py`, `test_conflict_detection.py`, etc. (5 files)
- ⏳ Integration tests: `test_edit_flow.spec.ts`, `test_gallery_flow.spec.ts`, etc. (5 files)
- ⏳ Manual testing checklist (12 items)

### Documentation

- ⏳ `phase-3.1-service-examples.yaml` (examples)
- ⏳ `phase-3.1-edit-guide.md` (user guide)
- ✅ `phase-3.1-implementation-guide.md` (technical guide)

---

## Phase 3.2: 3D Viewer with Three.js

### Component Scaffolding

- ✅ `model-detail-3d-viewer-tab.js` (160 lines, boilerplate created)
- ✅ `stl-loader.js` (loaders/stl-loader.js)
- ⏳ `three-mf-loader.js` (new file, optional)

### Viewer Features

- ✅ Three.js scene setup and render loop (`viewer.js` — 900+ LOC, ModelViewer class)
- ✅ File loader (STL + geometry endpoint integration)
- ✅ Geometry rendering and auto-fit (FOV-aware distance calculation)
- ✅ Build volume visualization (Bambu P1S 256×256×256mm, transparent wireframe)
- ✅ Camera controls (OrbitControls — rotate, zoom, pan, reset, touch)
- ✅ Build Volume Helper (`build_volume_helper.py` — fit analysis, placement hints, difficulty)
- ⏳ Layer coloring (optional Phase 3.2+)

### Sidecar Endpoints

- ✅ `GET /api/models/{model_ref}/geometry/{file_id}` (geometry.py — fetch/convert 3D files)

### Testing

- ✅ `test_phase3_2_3d_viewer.py` — 18 tests passing (STL loader, geometry rendering, camera controls, endpoint)
- ✅ `test_phase3_2_build_volume.py` — 34 tests passing (fit analysis, placement, difficulty, warnings)
- ⏳ Integration tests: `test_3d_viewer_rendering.spec.ts`, etc. (4 files)
- ⏳ Performance tests (load time, frame rate, memory)
- ⏳ Browser compatibility verification

### Documentation

- ⏳ `phase-3.2-service-examples.yaml` (examples)
- ✅ `phase-3.2-implementation-guide.md` (technical guide)

---

## Phase 3.3: Cross-System Integration

### Archive Integration

- ⏳ Enhanced archive linking UI (filters, sorting, grid)
- ⏳ Archive detail card enhancement (View Source Model button)

### Related Models

- ⏳ `model-detail-related-models.js` (new component)
- ⏳ `GET /api/models/{model_ref}/related` endpoint (sidecar)

### Navigation Services

- ⏳ `model_catalog.navigate_to_model` service
- ⏳ `model_catalog.queue_model_for_print` service (historical planning artifact; retired)
- ⏳ `print_history.navigate_to_linked_model` service

### Optional Features

- ⏳ `model-timeline-card.js` (model print history timeline)
- ⏳ `unified_search.yaml` (cross-system search)

### Testing

- ⏳ Unit tests: `test_related_models_endpoint.py`, etc. (4 files)
- ⏳ Integration tests: `test_linked_archives.spec.ts`, etc. (5 files)
- ⏳ Manual testing checklist (10 items)

### Documentation

- ⏳ `phase-3.3-service-examples.yaml` (examples)
- ✅ `phase-3.3-implementation-guide.md` (technical guide)

---

## File Structure

```
homeassistant/
├── www/3d_printing/model_catalog/
│   ├── model-detail-popup-card.js ..................... 👈 Enhance (edit, conflict, gallery, archive)
│   ├── model-detail-edit-form.js ....................... ✅ Created (Phase 3.1)
│   ├── model-detail-3d-viewer-tab.js ................... ✅ Created (Phase 3.2)
│   ├── model-detail-related-models.js .................. ⏳ Phase 3.3
│   ├── loaders/
│   │   ├── stl-loader.js ............................... ✅ Created (Phase 3.2)
│   │   └── three-mf-loader.js .......................... ⏳ Phase 3.2 (optional)
│   └── utils/
│       └── similarity-scorer.js ........................ ⏳ Phase 3.3
├── packages/3d_printing/model_catalog/
│   ├── services/
│   │   ├── update_model.yaml ........................... ⏳ Phase 3.1
│   │   ├── upload_photo.yaml ........................... ⏳ Phase 3.1
│   │   ├── navigate_to_model.yaml ...................... ⏳ Phase 3.3
│   │   ├── queue_model_for_print.yaml ................. historical artifact (retired)
│   │   └── navigate_to_linked_model.yaml .............. ⏳ Phase 3.3
│   └── rest_commands/
│       ├── patch_model.yaml ............................ ⏳ Phase 3.1
│       ├── upload_photo.yaml ........................... ⏳ Phase 3.1
│       ├── get_geometry.yaml ........................... ⏳ Phase 3.2
│       └── get_related_models.yaml ..................... ⏳ Phase 3.3

sidecars/model_catalog/app/
├── main.py ............................................. 👈 Add endpoints
│   ├── PATCH /api/models/{model_ref} .................. ⏳ Phase 3.1
│   ├── POST /api/models/{model_ref}/photos ............ ⏳ Phase 3.1
│   ├── GET /api/models/{model_ref}/geometry/{file_id} . ✅ Phase 3.2 (geometry.py)
│   ├── GET /api/models/{model_ref}/related ............ ⏳ Phase 3.3
│   └── GET /api/archives/{archive_id}/model .......... ⏳ Phase 3.3

tests/phase3/
├── test_edit_form.py ................................... ⏳ Phase 3.1
├── test_conflict_detection.py .......................... ⏳ Phase 3.1
├── test_photo_upload_endpoint.py ....................... ⏳ Phase 3.1
├── test_update_model_endpoint.py ....................... ⏳ Phase 3.1
├── test_stl_loader.py .................................. ✅ Phase 3.2 (test_phase3_2_3d_viewer.py)
├── test_3mf_loader.py .................................. ⏳ Phase 3.2
├── test_geometry_rendering.py .......................... ✅ Phase 3.2 (test_phase3_2_3d_viewer.py)
├── test_build_volume_visualization.py ................. ✅ Phase 3.2 (test_phase3_2_build_volume.py)
├── test_related_models_endpoint.py ..................... ⏳ Phase 3.3
├── test_navigation_services.py ......................... ⏳ Phase 3.3
└── ... (20+ total test files)

tests/e2e/
├── model_detail_edit_mode_toggle.spec.ts .............. ⏳ Phase 3.1
├── model_detail_edit_flow.spec.ts ...................... ⏳ Phase 3.1
├── model_detail_gallery_flow.spec.ts .................. ⏳ Phase 3.1
├── model_detail_3d_viewer_rendering.spec.ts ........... ⏳ Phase 3.2
├── model_detail_3d_viewer_controls.spec.ts ............ ⏳ Phase 3.2
├── model_detail_linked_archives.spec.ts ............... ⏳ Phase 3.3
├── model_detail_related_models.spec.ts ................ ⏳ Phase 3.3
└── ... (15+ total E2E test files)

docs/features/model_catalog/
├── phase-3.1-implementation-guide.md .................. ✅ Created
├── phase-3.2-implementation-guide.md .................. ✅ Created
├── phase-3.3-implementation-guide.md .................. ✅ Created
├── phase-3.1-3.3-roadmap.md ............................ ✅ Created
└── (+ service examples, edit guide)
```

---

## Execution Plan

### Week 1: Phase 3.1 Setup & Core Components

**Days 1-2: Edit Form & Conflict Detection**
- [ ] Enhance `model-detail-popup-card.js`: Add edit button toggle
- [ ] Implement `model-detail-edit-form.js`: Form validation + data binding
- [ ] Add conflict detection logic
- [ ] Create test suite for edit form

**Days 3-4: Photo Management**
- [ ] Implement gallery tab in detail card
- [ ] Create photo upload service
- [ ] Create upload photo endpoint (sidecar)
- [ ] Add gallery tests

**Days 5: Services & Documentation**
- [ ] Implement `model_catalog.update_model` service
- [ ] Implement `model_catalog.upload_photo` service
- [ ] Add REST command wrappers
- [ ] Document service examples

### Week 2: Phase 3.1 Testing & Refinement

**Days 6-7: Integration Testing**
- [ ] Write integration tests (5 files, 15-20 tests)
- [ ] Run manual testing checklist
- [ ] Fix bugs and edge cases
- [ ] Performance profiling (<500ms form render)

**Day 8: Phase 3.1 Complete**
- [ ] All tests passing ✅
- [ ] Code review complete
- [ ] Documentation complete
- [ ] Ready to merge to main

### Week 3: Phase 3.2 Implementation (Parallel with Phase 3.1 refinement)

**Days 9-11: 3D Viewer Core**
- [ ] Set up Three.js scene and render loop
- [ ] Implement STL loader
- [ ] Add geometry rendering and auto-fit
- [ ] Build volume visualization

**Days 12-13: Controls & UI**
- [ ] Camera controls (OrbitControls)
- [ ] Toolbar and info display
- [ ] File selector
- [ ] Auto-fit camera logic

**Day 14: Testing**
- [ ] Write integration tests (4+ files, 12-15 tests)
- [ ] Performance testing (load time, frame rate)
- [ ] Browser compatibility verification

### Week 4: Phase 3.3 Implementation & Finalization

**Days 15-16: Related Models & Navigation**
- [ ] Implement related models component
- [ ] Add related models endpoint (sidecar)
- [ ] Create navigation services
- [ ] Enhance archive linking UI

**Days 17-18: Integration & Testing**
- [ ] Integration tests (5+ files, 10-15 tests)
- [ ] Cross-system navigation flow testing
- [ ] Performance verification

**Day 19-20: Final Polish & Documentation**
- [ ] All tests passing ✅
- [ ] Code review complete
- [ ] Documentation complete
- [ ] Merge all phases to main
- [ ] Deploy to production

---

## Success Metrics

### Phase 3.1 Success
- ✅ All 15+ tests passing
- ✅ Edit form functional with validation
- ✅ Conflict detection working
- ✅ Photo gallery functional
- ✅ No performance regression

### Phase 3.2 Success
- ✅ All 12+ tests passing
- ✅ STL rendering works
- ✅ Build volume visualization correct
- ✅ Camera controls smooth (60 FPS)
- ✅ Auto-fit working for all models
- ✅ <500ms load time

### Phase 3.3 Success
- ✅ All 10+ tests passing
- ✅ Related models displayed
- ✅ Navigation seamless
- ✅ Archive filtering/sorting working
- ✅ No performance regression

### Overall Success
- ✅ 35+ tests passing
- ✅ All documentation complete
- ✅ Code review approved
- ✅ Deploy to production
- ✅ User feedback collected

---

## Dependencies & Resources

### Required
- Phase 3.0 MVP ✅
- Sidecar service running ✅
- Manyfold API accessible ✅
- HA 2024.1+ ✅

### Development Tools
- Three.js (CDN): https://cdn.jsdelivr.net/npm/three@r128/
- OrbitControls (CDN): https://cdn.jsdelivr.net/npm/three@r128/examples/js/controls/OrbitControls.js
- pytest (Python testing)
- Playwright (E2E testing)
- Browser DevTools

### Reference Materials
- Phase 3 Design: [phase-3-detail-view-design.md](../phase-3-detail-view-design.md)
- Bambuddy API: [../../bambuddy/README.md](../../bambuddy/README.md)
- Print History: [../print_history/](../print_history/)
- Three.js Docs: https://threejs.org/docs/

---

## Issues & Problem Tracking

Use the GitHub issue templates to track development:
- 🎫 [Phase 3.1 Issue Template](.././.github/ISSUE_TEMPLATE/phase-3-1-implementation.md)
- 🎫 [Phase 3.2 Issue Template](.././.github/ISSUE_TEMPLATE/phase-3-2-implementation.md)
- 🎫 [Phase 3.3 Issue Template](.././.github/ISSUE_TEMPLATE/phase-3-3-implementation.md)

---

## Rollback Plan

If any phase causes production issues:

1. Disable the problematic phase's resources
2. Revert sidecar endpoints
3. Remove HA services
4. Restart HA
5. Manually revert git commits if needed

Example (Phase 3.1 rollback):
```bash
# Disable edit form resource
# Remove update_model and upload_photo services
# Revert sidecar PATCH endpoints
# git revert <commit>
# Restart sidecar and HA
```

---

## Next Steps

1. **Create GitHub Issues** from the templates
2. **Assign developers** to each phase
3. **Start Phase 3.1** immediately
4. **Run parallel development** on Phases 3.2 & 3.3
5. **Daily standups** to track progress
6. **Weekly reviews** for each phase completion

---

## Notes

- All phases follow proven Phase 3.0 patterns
- Components are modular and can be developed in parallel
- Each phase is independently testable
- Documentation is comprehensive for knowledge sharing
- Performance targets set and must be verified

---

**Last Updated**: 2026-04-20  
**Status**: ✅ Ready for Development  
**Next Milestone**: Phase 3.1 Complete (end of Week 2)
