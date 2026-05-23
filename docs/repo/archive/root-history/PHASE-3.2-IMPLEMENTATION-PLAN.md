# Phase 3.2 Implementation Plan: 3D Viewer & STL Loader

Status: Historical
Last Reviewed: 2026-05-23
Functional Owner: repo-docs
Replaces: ../../../../PHASE-3.2-IMPLEMENTATION-PLAN.md
Replaced By: none


**Target Date:** April 26 - May 3, 2026 (1 week)  
**Dependencies:** Phase 3.1 ✅ Complete  
**Successor:** Phase 3.3 (Cross-System Integration)

## Overview

Phase 3.2 adds interactive 3D viewing capabilities to the Model Catalog. Users can:
- Preview STL/OBJ geometry before printing
- Rotate, zoom, and pan the model
- See model dimensions and build volume fit
- Detect over-sized models

## Architecture

### Component Stack

```
Frontend (Three.js):
  - viewer.js (Three.js scene, lights, camera)
  - loader.js (STL/OBJ parser)
  - controls.js (mouse/touch interactions)
  - build-volume.js (Bambu P1S visualization)

Backend (Sidecar):
  - GET /api/models/{model_ref}/geometry/{file_id} — Fetch geometry
  - geometry-parser.py — Parse STL/OBJ formats
  - geometry-metrics.py — Compute bounds, normals, centering

Dashboard:
  - print-history-3d-viewer-card.js (existing, reuse pattern)
  - model-detail-3d-viewer.js (new, for model catalog)
```

### Data Flow

```
User clicks model → Detail view loads
       ↓
Dashboard card queries GET /api/models/{ref}/geometry/{file_id}
       ↓
Sidecar streams STL file (base64 or binary)
       ↓
Three.js parser loads geometry
       ↓
Auto-fit camera, render scene
       ↓
User interacts (rotate/zoom) → Camera updates
```

## Detailed Implementation Tasks

### Task 1: Geometry Endpoint Implementation (Days 1-2)

**File:** `sidecars/model_catalog/app/main.py`

**Endpoint:** `GET /api/models/{model_ref}/geometry/{file_id}`

**Implementation:**
```python
@app.get("/api/models/{model_ref:path}/geometry/{file_id}")
def get_geometry_endpoint(model_ref: str, file_id: str):
    """
    Return geometry file info and download URL.
    Sidecar doesn't stream files; returns metadata for Three.js fetch.
    """
    summary = _resolve_model_summary(...)
    if not summary:
        return JSONResponse(status_code=404, content={"error": "Model not found"})
    
    # Get file metadata from Manyfold
    manyfold_detail = client.get_model_detail(summary.model_url)
    files = manyfold_detail.get("files", [])
    file_obj = next((f for f in files if str(f.get("id")) == file_id), None)
    
    if not file_obj:
        return JSONResponse(status_code=404, content={"error": "File not found"})
    
    # Return download URL and geometry hints
    return {
        "success": True,
        "file_id": file_id,
        "filename": file_obj.get("filename"),
        "file_type": get_file_type(file_obj.get("filename")),  # stl, obj, etc
        "download_url": f"/api/files/{file_id}/download",
        "file_size_bytes": file_obj.get("size"),
        "preview_url": file_obj.get("preview_url"),
    }
```

**Tests:** [tests/phase3/test_phase3_2_3d_viewer.py](../../../../tests/phase3/test_phase3_2_3d_viewer.py#L152)

### Task 2: STL Parser Implementation (Days 2-3)

**File:** `homeassistant/www/3d_printing/model_catalog/geometry-parser.js`

**Support:**
- Binary STL (80-byte header + triangle count + triangle data)
- ASCII STL (readable format)
- Format auto-detection

**Functions:**
```javascript
class STLParser {
  static parse(arrayBuffer) {
    // Auto-detect format
    const ascii = this.isASCII(arrayBuffer);
    return ascii ? this.parseASCII(arrayBuffer) : this.parseBinary(arrayBuffer);
  }
  
  static parseBinary(arrayBuffer) {
    // Skip 80-byte header
    const view = new DataView(arrayBuffer, 80);
    const triangleCount = view.getUint32(0, true);
    
    // Parse triangle data (12 bytes normal + 36 bytes vertices + 2 bytes attribute)
    const vertices = [];
    const normals = [];
    let offset = 4;  // After triangle count
    
    for (let i = 0; i < triangleCount; i++) {
      const normal = [
        view.getFloat32(offset, true),
        view.getFloat32(offset + 4, true),
        view.getFloat32(offset + 8, true),
      ];
      offset += 12;
      
      // 3 vertices
      for (let v = 0; v < 3; v++) {
        vertices.push(
          view.getFloat32(offset, true),
          view.getFloat32(offset + 4, true),
          view.getFloat32(offset + 8, true),
        );
        normals.push(...normal);
        offset += 12;
      }
      
      offset += 2;  // Skip attribute count
    }
    
    return { vertices, normals, triangleCount };
  }
  
  static parseASCII(arrayBuffer) {
    const text = new TextDecoder().decode(arrayBuffer);
    const vertices = [];
    const normals = [];
    let triangleCount = 0;
    
    const facetRegex = /facet normal ([\d.eE+-]+) ([\d.eE+-]+) ([\d.eE+-]+)/g;
    const vertexRegex = /vertex ([\d.eE+-]+) ([\d.eE+-]+) ([\d.eE+-]+)/g;
    
    let match;
    while ((match = facetRegex.exec(text)) !== null) {
      triangleCount++;
      const normal = [parseFloat(match[1]), parseFloat(match[2]), parseFloat(match[3])];
      
      // Extract 3 vertices for this facet
      let vertexMatch;
      let vertexCount = 0;
      while ((vertexMatch = vertexRegex.exec(text)) !== null && vertexCount < 3) {
        vertices.push(
          parseFloat(vertexMatch[1]),
          parseFloat(vertexMatch[2]),
          parseFloat(vertexMatch[3]),
        );
        normals.push(...normal);
        vertexCount++;
      }
    }
    
    return { vertices, normals, triangleCount };
  }
  
  static isASCII(arrayBuffer) {
    const view = new Uint8Array(arrayBuffer);
    const header = new TextDecoder().decode(view.slice(0, 5));
    return header.toLowerCase() === 'solid';
  }
}
```

**Tests:** [tests/phase3/test_phase3_2_3d_viewer.py::TestSTLLoader](../../../../tests/phase3/test_phase3_2_3d_viewer.py#L9)

### Task 3: Three.js Scene Setup (Days 3-4)

**File:** `homeassistant/www/3d_printing/model_catalog/viewer.js`

**Scene Configuration:**
```javascript
class ModelViewer {
  constructor(canvas) {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0xf5f5f5);
    
    // Camera (will auto-fit)
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    this.camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 10000);
    
    // Renderer
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    
    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    this.scene.add(ambientLight);
    
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(5, 5, 5);
    this.scene.add(directionalLight);
    
    // Mesh (will be populated by loadGeometry)
    this.mesh = null;
    
    // Controls (mouse/touch)
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    
    // Animation loop
    this.animate();
  }
  
  loadGeometry(geometryData) {
    // Parse vertices and normals
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(
      new Float32Array(geometryData.vertices), 3
    ));
    
    if (geometryData.normals) {
      geometry.setAttribute('normal', new THREE.BufferAttribute(
        new Float32Array(geometryData.normals), 3
      ));
    } else {
      geometry.computeVertexNormals();
    }
    
    // Material and mesh
    const material = new THREE.MeshPhongMaterial({
      color: 0x0077be,
      shininess: 100,
    });
    
    this.mesh = new THREE.Mesh(geometry, material);
    this.scene.add(this.mesh);
    
    // Auto-fit camera
    this.autoFitCamera();
  }
  
  autoFitCamera() {
    if (!this.mesh) return;
    
    const bbox = new THREE.Box3().setFromObject(this.mesh);
    const size = bbox.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = this.camera.fov * (Math.PI / 180);
    let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));
    
    this.camera.position.set(0, 0, cameraZ * 1.5);
    this.controls.target = bbox.getCenter(new THREE.Vector3());
    this.controls.update();
  }
  
  animate() {
    requestAnimationFrame(() => this.animate());
    this.renderer.render(this.scene, this.camera);
  }
}
```

**Tests:** [tests/phase3/test_phase3_2_3d_viewer.py::TestGeometryRendering](../../../../tests/phase3/test_phase3_2_3d_viewer.py#L38)

### Task 4: Build Volume Visualization (Days 4-5)

**File:** `homeassistant/www/3d_printing/model_catalog/build-volume.js`

**Bambu P1S Dimensions:** 256mm × 256mm × 256mm

**Implementation:**
```javascript
class BuildVolumeHelper {
  constructor(scene) {
    this.scene = scene;
    this.volume = null;
  }
  
  createBuildVolume() {
    const width = 256;  // mm
    const height = 256;  // mm
    const depth = 256;  // mm
    
    // Wireframe box
    const geometry = new THREE.BoxGeometry(width, height, depth);
    const material = new THREE.LineBasicMaterial({
      color: 0xff0000,
      linewidth: 1,
    });
    
    const wireframe = new THREE.LineSegments(
      new THREE.EdgesGeometry(geometry),
      material
    );
    
    this.volume = wireframe;
    this.scene.add(wireframe);
    
    return wireframe;
  }
  
  checkModelFit(mesh) {
    const bbox = new THREE.Box3().setFromObject(mesh);
    const size = bbox.getSize(new THREE.Vector3());
    
    const fits = {
      x: size.x <= 256,
      y: size.y <= 256,
      z: size.z <= 256,
    };
    
    return {
      fits: fits.x && fits.y && fits.z,
      dimensions: size,
      oversizeAxes: Object.entries(fits)
        .filter(([_, f]) => !f)
        .map(([axis]) => axis.toUpperCase()),
    };
  }
  
  updateVisibility(show) {
    if (this.volume) {
      this.volume.visible = show;
    }
  }
}
```

**Model Fit Detection Message:**
```javascript
function generateFitMessage(fitResult) {
  if (fitResult.fits) {
    return '✅ Fits on Bambu P1S';
  }
  
  const axes = fitResult.oversizeAxes.join(', ');
  const dims = fitResult.dimensions;
  return `⚠️ Over-size on ${axes}`;
}
```

**Tests:** [tests/phase3/test_phase3_2_3d_viewer.py::TestBuildVolumeVisualization](../../../../tests/phase3/test_phase3_2_3d_viewer.py#L112)

### Task 5: Camera Controls (Days 5-6)

**File:** `homeassistant/www/3d_printing/model_catalog/controls.js`

**Use Three.js OrbitControls (HACS package or embed)**

**Controls:**
- **Mouse Drag:** Rotate model
- **Scroll:** Zoom in/out
- **Shift + Drag:** Pan camera
- **Double-Click:** Reset view
- **Spacebar:** Toggle build volume

**Implementation:**
```javascript
class ViewerControls {
  constructor(viewer) {
    this.viewer = viewer;
    this.setupOrbitControls();
    this.setupKeyboardShortcuts();
  }
  
  setupOrbitControls() {
    const controls = new THREE.OrbitControls(
      this.viewer.camera,
      this.viewer.renderer.domElement
    );
    
    controls.autoRotate = false;
    controls.autoRotateSpeed = 5;
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.enableZoom = true;
    controls.enablePan = true;
    
    this.orbitControls = controls;
  }
  
  setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
      if (e.code === 'Space') {
        // Toggle build volume
        e.preventDefault();
        this.toggleBuildVolume();
      }
      if (e.code === 'KeyR') {
        // Reset view
        this.resetView();
      }
    });
  }
  
  toggleBuildVolume() {
    if (this.viewer.buildVolume) {
      this.viewer.buildVolume.visible = !this.viewer.buildVolume.visible;
    }
  }
  
  resetView() {
    this.viewer.autoFitCamera();
  }
}
```

**Tests:** [tests/phase3/test_phase3_2_3d_viewer.py::TestCameraControls](../../../../tests/phase3/test_phase3_2_3d_viewer.py#L196)

### Task 6: Dashboard Card Integration (Days 6-7)

**File:** `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer.js`

**Card Configuration:**
```yaml
type: custom:model-detail-3d-viewer
model_ref: gridfinity-bin
file_id: gridfinity-bin.stl
show_build_volume: true
auto_rotate: false
height: 600px
```

**Card Logic:**
```javascript
class ModelDetail3DViewerCard extends HTMLElement {
  setConfig(config) {
    this.config = config;
  }
  
  async connectedCallback() {
    const model_ref = this.config.model_ref;
    const file_id = this.config.file_id;
    
    // Fetch geometry endpoint
    const response = await fetch(
      `/api/rest_commands/model_catalog_get_geometry?model_ref=${model_ref}&file_id=${file_id}`
    );
    const data = await response.json();
    
    // Create viewer
    const canvas = document.createElement('canvas');
    this.appendChild(canvas);
    
    const viewer = new ModelViewer(canvas);
    
    // Load geometry (download from URL)
    const geomResponse = await fetch(data.download_url);
    const geometryData = await STLParser.parse(await geomResponse.arrayBuffer());
    
    viewer.loadGeometry(geometryData);
    
    // Show fit status
    const fitResult = viewer.buildVolume.checkModelFit(viewer.mesh);
    const messageDiv = document.createElement('div');
    messageDiv.className = 'fit-message';
    messageDiv.textContent = generateFitMessage(fitResult);
    this.appendChild(messageDiv);
  }
}

customElements.define('model-detail-3d-viewer', ModelDetail3DViewerCard);
```

**Tests:** [tests/phase3/test_phase3_2_3d_viewer.py::TestGeometryEndpoint](../../../../tests/phase3/test_phase3_2_3d_viewer.py#L240)

### Task 7: Resource Versioning (Day 7)

**File:** `homeassistant/packages/3d_printing/common/dashboards/_resources.yaml`

**Add Resources:**
```yaml
# Phase 3.2: 3D Viewer
- url: /local/3d_printing/model_catalog/geometry-parser.js?v=1
  type: module
- url: /local/3d_printing/model_catalog/viewer.js?v=1
  type: module
- url: /local/3d_printing/model_catalog/build-volume.js?v=1
  type: module
- url: /local/3d_printing/model_catalog/controls.js?v=1
  type: module
- url: /local/3d_printing/model_catalog/model-detail-3d-viewer.js?v=1
  type: module

# External: Three.js (via CDN or HACS)
- url: https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js
  type: js
```

**Important:** After merging this PR, increment resource URLs to cache-bust:
```yaml
- url: /local/3d_printing/model_catalog/geometry-parser.js?v=2
```

## Testing Strategy

### Unit Tests
```bash
pytest tests/phase3/test_phase3_2_3d_viewer.py::TestSTLLoader -v
pytest tests/phase3/test_phase3_2_3d_viewer.py::TestGeometryRendering -v
pytest tests/phase3/test_phase3_2_3d_viewer.py::TestBuildVolumeVisualization -v
```

### Integration Tests
1. Open model catalog
2. Select any model with STL file
3. Click "View 3D" button
4. Verify:
   - Geometry loads without errors
   - Camera auto-fits to model
   - Model displays correctly
   - Rotate/zoom/pan work
   - Build volume shows correctly
   - Fit message displays (✅ or ⚠️)

### Performance Tests
- Large models (>1MB): Should load within 2 seconds
- Triangle count: Support up to 500k triangles
- Memory: < 100MB for large models

## Success Criteria

- [ ] GET /api/models/{model_ref}/geometry/{file_id} endpoint functional
- [ ] STL parser handles binary and ASCII formats
- [ ] Three.js scene renders geometry correctly
- [ ] Build volume visualization works (256mm cube)
- [ ] Camera auto-fit on load
- [ ] Mouse controls (rotate/zoom/pan) responsive
- [ ] Model fit detection (✅ Fits / ⚠️ Over-size)
- [ ] Dashboard card integrated into model detail view
- [ ] All 25 test methods in TestGeometryRendering, TestBuildVolumeVisualization pass
- [ ] Resource URLs versioned in _resources.yaml

## Files Created/Modified

### New Files
- `homeassistant/www/3d_printing/model_catalog/geometry-parser.js` (STL parser)
- `homeassistant/www/3d_printing/model_catalog/viewer.js` (Three.js scene)
- `homeassistant/www/3d_printing/model_catalog/build-volume.js` (Bambu P1S viz)
- `homeassistant/www/3d_printing/model_catalog/controls.js` (Camera controls)
- `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer.js` (Card)

### Modified Files
- `sidecars/model_catalog/app/main.py` (Add geometry endpoint)
- `homeassistant/packages/3d_printing/common/dashboards/_resources.yaml` (Add resource URLs)
- `homeassistant/packages/3d_printing/model_catalog/rest_commands.yaml` (Add geometry command)

### Test Files
- Existing: [tests/phase3/test_phase3_2_3d_viewer.py](../../../../tests/phase3/test_phase3_2_3d_viewer.py) (310 lines, 25 tests)

## Dependencies

### External Libraries
- **Three.js** (v128+): 3D rendering
- **OrbitControls**: Camera manipulation (part of Three.js examples)
- **Manyfold API**: File metadata (already integrated)

### Browser Support
- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- (WebGL 2.0 required)

## Known Limitations

1. **File Streaming:** Sidecar returns metadata; Three.js fetches file directly
2. **Formats:** Only STL for Phase 3.2 (OBJ, GLTF in Phase 3.3)
3. **Texture/Color:** Single material color; texture support deferred
4. **Performance:** Very large models (>5M triangles) may be slow

## Timeline

| Day | Task | Owner |
|-----|------|-------|
| 1-2 | Geometry endpoint (main.py) | Backend |
| 2-3 | STL parser (JS) | Frontend |
| 3-4 | Three.js scene setup | Frontend |
| 4-5 | Build volume visualization | Frontend |
| 5-6 | Camera controls | Frontend |
| 6-7 | Dashboard card + resource versioning | Integration |

## Sign-Off

**Plan Created:** April 25, 2026  
**Next Review:** April 26, 2026 (Kickoff)  
**Milestone:** Ready for Phase 3.3 (May 3, 2026)
