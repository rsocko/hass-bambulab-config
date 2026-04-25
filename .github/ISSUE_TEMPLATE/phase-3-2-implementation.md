---
name: Phase 3.2 Implementation Task
about: Track Phase 3.2 implementation task (3D Viewer with Three.js)
title: "[Phase 3.2] "
labels: phase-3, enhancement, model-catalog
assignees: ''
---

## Phase 3.2: 3D Viewer with Three.js

**Objective**: Add 3D model visualization directly in detail popup

**Scope**:
- STL/3MF rendering in browser
- Build volume overlay (Bambu P1S)
- Camera controls (rotate, zoom, pan)
- Layer coloring (optional)

**Effort**: 40-45 hours | **Priority**: MEDIUM

---

## Implementation Tasks

### Core Components

- [ ] **Three.js Setup** (`model-detail-3d-viewer-tab.js`)
  - Scene, camera, renderer initialization
  - Lighting setup (2 lights)
  - Render loop with requestAnimationFrame
  - Tests: `test_3d_viewer_initialization.py`

- [ ] **File Loaders**
  - STL Loader: Parse binary/ASCII STL, create BufferGeometry
  - 3MF Loader: Convert to STL or load directly
  - Compute bounding box and normals
  - Tests: `test_stl_loader.py`, `test_3mf_loader.py`

- [ ] **File Selector** (for multi-file models)
  - Dropdown of available .stl/.3mf/.obj files
  - Load on change with spinner
  - Error display
  - Tests: `test_file_selector.spec.ts`

- [ ] **Geometry Rendering & Auto-Fit**
  - Add geometry to scene
  - Center at origin
  - Auto-fit camera to view
  - Apply shading (smooth + wireframe)
  - Tests: `test_geometry_rendering.py`

- [ ] **Build Volume Visualization**
  - Transparent wireframe (256×256×256mm)
  - Optional dimension labels
  - Toggle visibility
  - Fit check: Display if model fits or "Over-size"
  - Tests: `test_build_volume_visualization.py`

- [ ] **Camera Controls** (OrbitControls)
  - Rotation: Left drag
  - Zoom: Mouse wheel / pinch
  - Pan: Right drag + Shift
  - Reset button
  - Touch support
  - Tests: `test_3d_viewer_controls.spec.ts`

- [ ] **Toolbar & Info Display**
  - Buttons: Reset, Grid toggle, Layers toggle, Download
  - Info display: Dimensions, fit status, triangle count
  - Viewer state persistence
  - Tests: `test_3d_viewer_toolbar.py`

### Sidecar Endpoints

- [ ] **Geometry Endpoint** (`GET /api/models/{model_ref}/geometry/{file_id}`)
  - Fetch 3D file
  - Convert 3MF to STL if needed
  - Return as ArrayBuffer
  - Tests: `test_geometry_endpoint.py`

### Optional Features (Phase 3.2+)

- [ ] **Layer Coloring**
  - Parse 3MF layer data or auto-slice
  - Color gradient: Blue (bottom) → Red (top)
  - Layer slider
  - Tests: `test_layer_coloring.py`

- [ ] **Download STL**
  - Export rendered geometry as .stl
  - Tests: `test_download_stl.spec.ts`

### Documentation & Testing

- [ ] Documentation: `phase-3.2-service-examples.yaml`
- [ ] Test Suite: 12+ tests covering all scenarios
- [ ] Browser Compatibility: Chrome, Firefox, Safari, Mobile
- [ ] Performance Tests: <500ms load, 60 FPS at 1920×1080
- [ ] Implementation Guide: `phase-3.2-implementation-guide.md` ✅

---

## Testing Requirements

### Unit Tests
```
tests/phase3/
├── test_stl_loader.py
├── test_3mf_loader.py
├── test_geometry_rendering.py
├── test_build_volume_visualization.py
└── test_geometry_bounding_box.py
```

### Integration Tests
```
tests/e2e/
├── model_detail_3d_viewer_rendering.spec.ts
├── model_detail_3d_viewer_controls.spec.ts
├── model_detail_3d_viewer_fit_check.spec.ts
└── model_detail_3d_viewer_file_selector.spec.ts
```

### Performance Tests
- [ ] Model load time: <500ms (typical)
- [ ] Render frame rate: 60 FPS at 1920×1080
- [ ] Memory usage: Monitor for leaks on file switch
- [ ] Mobile viewport: Smooth controls on touch

### Browser Compatibility
- [ ] Chrome/Edge 90+
- [ ] Firefox 88+
- [ ] Safari 14+
- [ ] iOS Safari 14+
- [ ] Chrome Android

---

## Success Criteria

- ✅ STL rendering works for typical models
- ✅ Build volume visualization correct
- ✅ Camera controls responsive and smooth
- ✅ Auto-fit works for all sizes
- ✅ 12+ tests pass
- ✅ Performance acceptable (<500ms, 60 FPS)
- ✅ Mobile responsive
- ✅ Documentation complete

---

## Dependencies

- Phase 3.0 MVP ✅
- Phase 3.1 (can be parallel)
- Three.js library (from CDN)
- THREE.OrbitControls (from CDN)
- Sidecar service for geometry endpoint

---

## References

- Implementation Guide: [phase-3.2-implementation-guide.md](../../docs/features/model_catalog/phase-3.2-implementation-guide.md)
- Roadmap: [phase-3.1-3.3-roadmap.md](../../docs/features/model_catalog/phase-3.1-3.3-roadmap.md)
- Design: [phase-3-detail-view-design.md](../../docs/features/model_catalog/phase-3-detail-view-design.md)
- Three.js Docs: https://threejs.org/docs/

---

## Notes

### Three.js CDN URLs
- Three.js: https://cdn.jsdelivr.net/npm/three@r128/build/three.min.js
- OrbitControls: https://cdn.jsdelivr.net/npm/three@r128/examples/js/controls/OrbitControls.js
- STL Loader: https://cdn.jsdelivr.net/npm/three@r128/examples/js/loaders/STLLoader.js

### STL File Format Notes
- Binary STL: 84-byte header + triangle count (4 bytes) + triangles
- ASCII STL: Text format, less efficient but human-readable
- Support both formats in loader

### 3MF Format Notes
- Complex format with XML + embedded binary data
- Consider starting with STL only, add 3MF in follow-up
- Fallback: Use online converter service or convert server-side

---

## Checklist

- [ ] Implementation started
- [ ] All tasks completed
- [ ] All tests passing
- [ ] Code reviewed
- [ ] Performance verified
- [ ] Browser compatibility verified
- [ ] Documentation updated
- [ ] Ready for Phase 3.3

---

/label phase-3 enhancement model-catalog
/assign @developer-name
