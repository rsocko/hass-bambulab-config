# Phase 3.1-3.3 Quick Reference Guide

**Status**: Ready for Development | **Duration**: ~4 weeks | **Effort**: ~125 hours

---

## 🚀 Getting Started (5 minutes)

### For Project Managers

1. Open [phase-3.1-3.3-development-checklist.md](../phase-3.1-3.3-development-checklist.md)
2. Assign developers to each phase (can be parallel)
3. Create GitHub issues from templates (see below)
4. Track progress on GitHub project board

### For Developers (Phase 3.1)

1. Read [phase-3.1-implementation-guide.md](../phase-3.1-implementation-guide.md) (15 min)
2. Review existing files:
   - `homeassistant/www/3d_printing/model_catalog/model-detail-edit-form.js` (boilerplate exists)
   - `homeassistant/www/3d_printing/model_catalog/model-detail-popup-card.js` (enhance)
3. Start with Task 1: Edit Form Component
4. Run tests: `pytest tests/phase3/test_edit_form.py`

### For Developers (Phase 3.2)

1. Read [phase-3.2-implementation-guide.md](../phase-3.2-implementation-guide.md) (15 min)
2. Review existing files:
   - `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js` (boilerplate exists)
3. Start with Task 1: Three.js Setup
4. Bookmark Three.js docs: https://threejs.org/docs/

### For Developers (Phase 3.3)

1. Read [phase-3.3-implementation-guide.md](../phase-3.3-implementation-guide.md) (15 min)
2. Review print_history reference: `docs/features/print_history/`
3. Start with Task 1: Enhanced Archive Linking
4. Study archive data structure in existing code

---

## 📋 GitHub Issue Templates

Use these to track development:

**Phase 3.1**: [Create Issue](../../.github/ISSUE_TEMPLATE/phase-3-1-implementation.md)
```bash
# Copy this template into a new GitHub issue:
.github/ISSUE_TEMPLATE/phase-3-1-implementation.md
```

**Phase 3.2**: [Create Issue](../../.github/ISSUE_TEMPLATE/phase-3-2-implementation.md)
```bash
# Copy this template into a new GitHub issue:
.github/ISSUE_TEMPLATE/phase-3-2-implementation.md
```

**Phase 3.3**: [Create Issue](../../.github/ISSUE_TEMPLATE/phase-3-3-implementation.md)
```bash
# Copy this template into a new GitHub issue:
.github/ISSUE_TEMPLATE/phase-3-3-implementation.md
```

---

## 📚 Documentation Map

```
docs/features/model_catalog/
├── phase-3.1-3.3-roadmap.md ...................... 📊 Executive Summary
├── phase-3.1-3.3-development-checklist.md ....... 📋 Master Execution Plan
├── phase-3.1-implementation-guide.md ............ 🔨 Phase 3.1 Technical Guide
├── phase-3.2-implementation-guide.md ............ 🔨 Phase 3.2 Technical Guide
├── phase-3.3-implementation-guide.md ............ 🔨 Phase 3.3 Technical Guide
├── phase-3-implementation-guide.md .............. 📖 Phase 3.0 Reference (completed)
├── phase-3-detail-view-design.md ................ 🎨 Design Specifications
├── model-detail-popup-card.js ................... 💻 Main Card Component (Phase 3.0)
└── ... (other model_catalog files)
```

---

## ⏱️ Timeline

```
Week 1-2: Phase 3.1 (Edit Mode & Photos)
│  Day 1-2: Edit form + conflict detection
│  Day 3-4: Photo gallery + upload service
│  Day 5:   Services + documentation
│  Day 6-8: Integration testing + refinement
└─ Complete ✅

Week 3: Phase 3.2 (3D Viewer) [can start Day 5]
│  Day 9-11:  Three.js setup + file loaders + rendering
│  Day 12-13: Controls + toolbar
│  Day 14:    Integration testing
└─ Complete ✅

Week 4: Phase 3.3 (Cross-System) [can start Day 9]
│  Day 15-16: Related models + navigation
│  Day 17-18: Integration testing
│  Day 19-20: Polish + documentation
└─ Complete ✅
```

---

## 🔨 Implementation Roadmap (Per Phase)

### Phase 3.1 Tasks (in order)

1. **Edit Form Component** (3-4 hours)
   - File: `model-detail-edit-form.js` ✅ boilerplate exists
   - What: Populate form, validation, enrichment fields

2. **Edit Mode Toggle** (2-3 hours)
   - File: enhance `model-detail-popup-card.js`
   - What: Edit button, toggle rendering, Save/Cancel

3. **Conflict Detection** (3-4 hours)
   - File: enhance `model-detail-popup-card.js`
   - What: Compare timestamps, show conflict dialog

4. **Photo Gallery** (4-5 hours)
   - File: enhance `model-detail-popup-card.js`
   - What: Gallery tab, thumbnails, upload, delete

5. **Update Model Service** (2-3 hours)
   - File: new `model_catalog.update_model` service
   - File: sidecar `PATCH /api/models/{ref}` endpoint

6. **Photo Upload Service** (2-3 hours)
   - File: new `model_catalog.upload_photo` service
   - File: sidecar `POST /api/models/{ref}/photos` endpoint

7. **Testing** (8-12 hours)
   - 5 unit test files (~40 test cases)
   - 5 integration test files (~30 test cases)
   - Manual testing checklist

### Phase 3.2 Tasks (in order)

1. **Three.js Setup** (3-4 hours)
   - Scene, camera, renderer, lighting, render loop

2. **File Loaders** (5-6 hours)
   - STL loader: parse binary/ASCII
   - 3MF loader: convert or load directly
   - Compute bounding box, normals

3. **Geometry Rendering** (3-4 hours)
   - Add to scene, center at origin
   - Auto-fit camera
   - Smooth + wireframe shading

4. **Build Volume** (2-3 hours)
   - Wireframe cube (256×256×256mm)
   - Fit check (display "Fits" or "Over-size")

5. **Camera Controls** (2-3 hours)
   - OrbitControls: rotate, zoom, pan, reset
   - Touch support

6. **Toolbar & Info** (2-3 hours)
   - Buttons: Reset, Grid, Layers, Download
   - Info: Dimensions, fit, triangle count

7. **Testing & Performance** (15-20 hours)
   - 5 unit test files
   - 4 integration test files
   - Performance profiling (<500ms, 60 FPS)
   - Browser compatibility

### Phase 3.3 Tasks (in order)

1. **Archive Linking** (3-4 hours)
   - Grid UI with thumbnails
   - Filters: All / Successful / Failed
   - Sort: Date / Filament

2. **Related Models** (3-4 hours)
   - Component: `model-detail-related-models.js`
   - Endpoint: `/api/models/{ref}/related`
   - Similarity algorithm

3. **Navigation Services** (2-3 hours)
   - `navigate_to_model` service
   - `queue_model_for_print` service (historical plan item; retired in unified queue cutover)
   - `navigate_to_linked_model` service

4. **Archive Detail Enhancement** (1-2 hours)
   - "View Source Model" button
   - Integrate with navigation

5. **Optional Features** (5-10 hours, can defer)
   - Model timeline card
   - Unified search endpoint

6. **Testing** (5-8 hours)
   - 4 unit test files
   - 5 integration test files
   - Manual testing checklist

---

## 📊 Key Resources

### Documentation
- **Roadmap**: [phase-3.1-3.3-roadmap.md](../phase-3.1-3.3-roadmap.md)
- **Design**: [phase-3-detail-view-design.md](../phase-3-detail-view-design.md)
- **Phase 3.0 Reference**: [phase-3-implementation-guide.md](../phase-3-implementation-guide.md)

### Code References
- **Main Card**: `homeassistant/www/3d_printing/model_catalog/model-detail-popup-card.js`
- **Print History Archive Card**: `homeassistant/www/3d_printing/print_history/print-history-archive-actions-card.js`
- **Sidecar Main**: `sidecars/model_catalog/app/main.py`
- **Bambuddy API**: `bambuddy/README.md`

### External Resources
- **Three.js**: https://threejs.org/docs/
- **OrbitControls**: https://threejs.org/examples/#misc_controls_orbit
- **STL Format**: https://en.wikipedia.org/wiki/STL_(file_format)

---

## ✅ Success Criteria Summary

### Phase 3.1 Success
- [ ] All 15+ tests passing
- [ ] Edit form works with validation
- [ ] Conflict detection prevents data loss
- [ ] Photo gallery functional
- [ ] Services integrated with HA
- [ ] <500ms form render time

### Phase 3.2 Success
- [ ] All 12+ tests passing
- [ ] STL rendering works
- [ ] Build volume visualization correct
- [ ] Controls smooth (60 FPS)
- [ ] <500ms load time
- [ ] Mobile responsive

### Phase 3.3 Success
- [ ] All 10+ tests passing
- [ ] Related models display
- [ ] Navigation seamless
- [ ] Archive UI enhanced
- [ ] <100ms per navigation

---

## 🚨 Common Pitfalls (Learn from Phase 3.0)

1. **Import Paths**: Use `app.main` not `main` when testing sidecar
2. **Test Fixtures**: Add all required Settings fields (image metadata, etc.)
3. **Async Operations**: Don't forget `async def` / `await` in tests
4. **Resource URLs**: Update cache-buster in `_resources.yaml` after JS changes
5. **Mobile Viewport**: Test on actual mobile, not just browser emulation

---

## 🔄 Parallel Development Strategy

**Can start simultaneously**:
- Phase 3.1 components (Days 1-5)
- Phase 3.2 boilerplate (Days 5+)
- Phase 3.3 planning (Days 5+)

**Dependencies**:
- Phase 3.1 must complete before Phase 3.1 testing
- Phase 3.2 can start while Phase 3.1 testing runs
- Phase 3.3 can start while Phase 3.2 is running

**Recommended Staggering**:
```
Team A: Phase 3.1 (Days 1-14)
Team B: Phase 3.2 (Days 9-20, starts Day 9)
Team C: Phase 3.3 (Days 15-20, starts Day 15)
```

---

## 📞 Support & Questions

**For unclear specifications**:
→ See detailed guide (`phase-3.X-implementation-guide.md`)

**For design questions**:
→ See design document (`phase-3-detail-view-design.md`)

**For execution planning**:
→ See development checklist (`phase-3.1-3.3-development-checklist.md`)

**For sidecar reference**:
→ See Phase 3.0 guide (`phase-3-implementation-guide.md`)

---

## 🎯 Checklist for Getting Started

- [ ] Read this quick reference (5 min)
- [ ] Read phase-specific implementation guide (15 min)
- [ ] Review boilerplate code (if exists)
- [ ] Create GitHub issue from template
- [ ] Clone repo and check out branch
- [ ] Review test examples in same directory
- [ ] Start with Task 1 of phase
- [ ] Run tests as you code: `pytest tests/phase3/...`
- [ ] Ask questions if specifications unclear
- [ ] Update issue as you progress

---

**Last Updated**: 2026-04-20  
**Status**: ✅ Complete Planning Phase - Ready to Code  
**Next**: Assign developers and create GitHub issues
