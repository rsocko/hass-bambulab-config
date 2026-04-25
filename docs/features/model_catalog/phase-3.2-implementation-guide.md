# Phase 3.2 Implementation Guide: 3D Viewer with Three.js

**Scope**: STL/3MF rendering, build volume overlay, controls  
**Effort**: 40-45 hours  
**Priority**: MEDIUM  
**Status**: Ready for Development

---

## Overview

Phase 3.2 adds 3D model visualization directly in the detail popup. Users can:
- View STL/3MF geometry in browser
- Inspect model dimensions and scale
- Visualize placement on build platform (Bambu P1S)
- Rotate, zoom, pan the model
- Toggle build volume, grid, and layer coloring

---

## Architecture

### Components

1. **model-detail-3d-viewer-tab.js** (New)
   - Three.js scene setup
   - File selector and controls
   - Build volume visualization
   - Layer coloring (optional)

2. **Sidecar Endpoint** (New)
   - `GET /api/models/{model_ref}/geometry/{file_id}` — Fetch/convert 3D files

3. **HA Integration**
   - REST command for geometry endpoint (optional)

### Data Flow

```
Load model detail → Get file list → User selects file → Fetch STL from sidecar → 
Render in Three.js → Apply controls (rotate/zoom/pan) → Show build volume overlay
```

---

## Implementation Tasks

### Task 1: Three.js Boilerplate
**File**: `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js`  
**Status**: ✅ Boilerplate created

**Setup**:
- Load Three.js from CDN (lazy load)
- Create Scene, Camera, WebGLRenderer
- Set up lighting (2 lights: top-front and back)
- Create render loop with requestAnimationFrame

**Lighting Setup**:
```javascript
const light1 = new THREE.DirectionalLight(0xffffff, 0.8);
light1.position.set(1, 1, 1);
scene.add(light1);

const light2 = new THREE.DirectionalLight(0xffffff, 0.3);
light2.position.set(-1, -1, -1);
scene.add(light2);
```

**Tests**:
```bash
tests/phase3/test_3d_viewer_initialization.py
```

---

### Task 2: File Loader (STL/3MF)
**File**: `homeassistant/www/3d_printing/model_catalog/loaders/stl-loader.js`  
**File**: `homeassistant/www/3d_printing/model_catalog/loaders/three-mf-loader.js`

**STL Loader**:
- Parse binary/ASCII STL format
- Create THREE.BufferGeometry
- Compute bounding box
- Compute normals for shading

**3MF Loader** (Optional for 3.2):
- Use Three-bvh-csg library or online converter
- OR Convert 3MF → STL server-side, fetch STL
- Store layer information if available

**Sidecar Endpoint**: `GET /api/models/{model_ref}/geometry/{file_id}`
```python
@app.get("/api/models/{model_ref}/geometry/{file_id}")
async def get_geometry(model_ref: str, file_id: str):
    """Fetch 3D geometry file, converting if necessary."""
    # 1. Resolve model and file
    model = resolve_model_ref(model_ref)
    file = model.files[file_id]
    
    # 2. Fetch from Manyfold if not cached
    if file.type == "stl":
        return fetch_file(file.url)
    elif file.type == "3mf":
        # Option A: Convert 3MF → STL
        stl_data = convert_3mf_to_stl(file.url)
        return stl_data
        # Option B: Return 3MF directly, load in browser
        return fetch_file(file.url)
```

**Tests**:
```bash
tests/phase3/test_stl_loader.py
tests/phase3/test_3mf_loader.py
```

---

### Task 3: File Selector
**File**: `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js`

**Feature** (only shown for multi-file models):
- Dropdown of available files (filter by .stl, .3mf, .obj)
- Load selected file on change
- Show loading spinner during load
- Display error if load fails

**Example**:
```javascript
onFileChange(event) {
  const fileIndex = event.target.value;
  const file = this._files[fileIndex];
  
  this._loadGeometry(file);
}

async _loadGeometry(file) {
  this._showLoading();
  try {
    const response = await fetch(`/api/models/${this._modelRef}/geometry/${file.id}`);
    const arrayBuffer = await response.arrayBuffer();
    const geometry = STLLoader.parse(arrayBuffer);
    this._renderGeometry(geometry);
  } catch (error) {
    this._showError(error.message);
  }
}
```

---

### Task 4: Geometry Rendering & Auto-Fit
**File**: `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js`

**Implementation**:
1. Add geometry to scene
2. Compute bounding box
3. Center geometry at origin
4. Auto-fit camera to view entire model
5. Apply shading (smooth + wireframe toggle)

**Auto-Fit Algorithm**:
```javascript
fitCameraToGeometry(geometry) {
  const boundingBox = new THREE.Box3().setFromBufferGeometry(geometry);
  const size = boundingBox.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  const fov = this._camera.fov * (Math.PI / 180);
  let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));
  
  cameraZ *= 1.5; // Add padding
  this._camera.position.z = cameraZ;
  this._camera.lookAt(geometry.boundingBox.getCenter(new THREE.Vector3()));
}
```

**Tests**:
```bash
tests/phase3/test_geometry_rendering.py
```

---

### Task 5: Build Volume Visualization
**File**: `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js`

**Feature**: 
- Render transparent wireframe build platform
- Dimensions: 256×256×256mm (Bambu P1S, configurable)
- Optional: Show dimensions labels (X, Y, Z)
- Toggle visibility with button

**Implementation**:
```javascript
createBuildVolume() {
  const geometry = new THREE.BoxGeometry(256, 256, 256);
  const material = new THREE.LineBasicMaterial({
    color: 0x888888,
    linewidth: 1,
    transparent: true,
    opacity: 0.3,
  });
  const wireframe = new THREE.EdgesGeometry(geometry);
  const buildVolume = new THREE.LineSegments(wireframe, material);
  this._scene.add(buildVolume);
  return buildVolume;
}

toggleBuildVolume() {
  this._buildVolume.visible = !this._buildVolume.visible;
}
```

**Fit Check**:
- Compute model bounding box
- Check if within 256×256×256mm
- Display fit status: "✅ Fits" or "⚠️ Over-size (X: 350mm)"

**Tests**:
```bash
tests/phase3/test_build_volume_visualization.py
```

---

### Task 6: Camera Controls
**File**: `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js`

**Controls**:
- **Rotation**: Left mouse drag (or touch drag)
- **Zoom**: Mouse wheel (or pinch on touch)
- **Pan**: Right mouse drag + Shift (or two-finger drag on touch)
- **Reset**: Button to return to auto-fit view

**Library**: Use `THREE.OrbitControls` (from CDN)
```javascript
this._controls = new THREE.OrbitControls(this._camera, this._renderer.domElement);
this._controls.autoRotate = false;
this._controls.autoRotateSpeed = 0; // Manual control
this._controls.enableDamping = true;
this._controls.dampingFactor = 0.05;
```

**Tests**:
```bash
tests/e2e/model_detail_3d_viewer_controls.spec.ts
```

---

### Task 7: Toolbar & Info Display
**File**: `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js`

**Toolbar Buttons**:
- `[↻ Reset]` — Fit to view
- `[⊞ Grid]` — Toggle build platform grid
- `[🌈 Layers]` — Toggle layer coloring (Phase 3.2+ optional)
- `[⬇ Download]` — Download as STL (Phase 3.2+ optional)

**Info Display**:
- Dimensions: "256 × 256 × 180 mm"
- Build Volume Fit: "✅ Fits" or "⚠️ Over-size"
- Triangle count: "45,230 triangles"
- Rendering: "Three.js WebGL"

**Persistence**:
Store viewer state in session (toggle states, current file selection)

**Tests**:
```bash
tests/phase3/test_3d_viewer_toolbar.py
```

---

### Task 8: Layer Coloring (Optional)
**File**: `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js`

**Feature** (can defer to Phase 3.2+):
- If 3MF contains layer data: parse and color
- Otherwise: Auto-slice at configurable height (default 0.2mm)
- Color gradient: Blue (bottom) → Red (top)
- Slider to show/hide layers

**Implementation Note**: Complex, consider using existing Three.js layer visualization libraries.

---

## Testing Strategy

### Unit Tests (Python/pytest)
```
tests/phase3/
├── test_stl_loader.py
├── test_3mf_loader.py
├── test_geometry_rendering.py
├── test_build_volume_visualization.py
└── test_geometry_bounding_box.py
```

### Integration Tests (Playwright)
```
tests/e2e/
├── model_detail_3d_viewer_rendering.spec.ts
├── model_detail_3d_viewer_controls.spec.ts
├── model_detail_3d_viewer_fit_check.spec.ts
└── model_detail_3d_viewer_file_selector.spec.ts
```

### Performance Tests
- Model load time: Target <500ms for typical models
- Render frame rate: Target 60 FPS at 1920×1080
- Memory usage: Monitor for leaks on file switch

---

## Browser Compatibility

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+ (WebGL support required)
- Mobile: iOS Safari 14+, Chrome Android

**Note**: WebGL not available in IE11 or older browsers

---

## Success Criteria

- ✅ STL rendering works for typical models
- ✅ Build volume visualization overlays correctly
- ✅ Camera controls responsive and smooth
- ✅ Auto-fit works for all model sizes
- ✅ 12+ tests pass
- ✅ Performance acceptable (<500ms load, 60 FPS)
- ✅ Mobile-responsive (touch controls work)
- ✅ Documentation complete

---

## Dependencies

- Phase 3.0 MVP ✅ (required)
- Three.js library (CDN)
- THREE.OrbitControls (CDN)
- Sidecar service for geometry endpoint

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Large model performance | Lazy-load Three.js, cache geometry, limit file size to 50MB |
| WebGL not available | Graceful fallback to placeholder "Download to view" |
| 3MF parsing complexity | Start with STL only, add 3MF support in follow-up |
| Mobile touch performance | Use optimized raycasting, throttle events |

---

## References

- Three.js Documentation: https://threejs.org/docs/
- Three.js OrbitControls: https://threejs.org/examples/#misc_controls_orbit
- STL Format Spec: https://en.wikipedia.org/wiki/STL_(file_format)
- Phase 3.0 Implementation: [phase-3-implementation-guide.md](phase-3-implementation-guide.md)
- Design Document: [phase-3-detail-view-design.md](phase-3-detail-view-design.md)
