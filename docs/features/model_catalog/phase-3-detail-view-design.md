# Phase 3: Model Detail View & Edit — Design Doc

> **Status**: Design & Architecture Planning  
> **Created**: 2026-04-25  
> **Scope**: Popup-based model detail view and inline editing in Home Assistant UI  
> **Related Issue**: #1125

---

## Overview

Phase 3 delivers a comprehensive detail view and edit interface for individual models from the Manyfold catalog, directly in the Home Assistant UI. This allows operators to view model information, manage photos, inspect 3D geometry, and make enrichment edits without leaving HA or opening the Manyfold native interface.

### Goal

Enable rich model introspection and curation directly within HA, following the same proven patterns established by the print history archive detail popup.

### Primary Operator Workflows

1. **Model Inspection**: View full model details, photos, and 3D rendering
2. **Media Management**: Upload additional photos, view photo gallery, set preferred preview
3. **Field Enrichment**: Edit model name, description, tags, collection memberships, and custom fields
4. **Cross-System Navigation**: Understand linked archives, navigate to related prints
5. **Problem Diagnosis**: Review metadata state, enrichment provenance, validation status

---

## Design Direction

### Architecture Principles

**Leverage Existing Patterns:**
- Reuse the archive detail popup as the container pattern
- Adapt print-history photo gallery for model media review
- Adapt print-history 3D viewer for source 3MF inspection (with adjustments for source vs. runtime)

**Separation of Concerns:**
- **Layer 1 (Sidecar)**: Fetch model details from Manyfold, normalize, cache
- **Layer 2 (HA Integration)**: Enrich with linkage metadata, archive cross-references, custom fields
- **Layer 3 (Frontend)**: Render popup, gallery, 3D viewer, edit forms

**Deterministic & Stateless:**
- All operations derive from upstream state (Manyfold) + local SQLite
- Edit operations are explicit commits, not auto-save
- No optimistic local state that can diverge from upstream

---

## Surface 1: Detail View Popup

### Visual Structure

```
┌─────────────────────────────────────────────────────────────────┐
│ Model Detail Popup                              [Close]          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ┌─ Header ─────────────────────────────────────────────────────┐ │
│ │ [thumbnail]  Model Name                                      │ │
│ │              Creator: Author Name                             │ │
│ │              Collections: Parent / Child                       │ │
│ │              Tags: tag1 · tag2 · tag3                         │ │
│ │                                                               │ │
│ │  [Edit] [Archive Link] [Print] [Download]                     │ │
│ └───────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ ┌─ Tabbed Navigation ───────────────────────────────────────────┐ │
│ │ [Details] [Media Gallery] [3D Viewer] [Linked Prints]        │ │
│ └───────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ ┌─ Tab: Details ────────────────────────────────────────────────┐ │
│ │ Description:                                                  │ │
│ │ [Long-form description text with markdown support]           │ │
│ │                                                               │ │
│ │ Quick Stats:                                                  │ │
│ │  • Files: 3 (1 STL, 2 3MF)                                    │ │
│ │  • Estimated print time: 2h 15m (for default setup)           │ │
│ │  • Build volume: 165 × 165 × 180mm                            │ │
│ │  • Linked archives: 7 (last printed 3d ago)                   │ │
│ │  • Created: 2026-03-15  Updated: 2026-04-20                  │ │
│ │                                                               │ │
│ │ Enrichment Status:                                            │ │
│ │  • License: CC-BY-4.0                                         │ │
│ │  • Presupported: Yes (Bambu Studio confirmed)                 │ │
│ │  • Supports multi-color: Yes (by-layer sequencing)           │ │
│ │  • Supports tree supports: Recommended                        │ │
│ │                                                               │ │
│ │ Related Models:                                               │ │
│ │  • Gridfinity Bin (89%)  [View]                               │ │
│ │  • Gridfinity Organizer (84%)  [View]                         │ │
│ └───────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ [Save Changes] [Cancel] [Delete Model]                         │
└─────────────────────────────────────────────────────────────────┘
```

### Header Section (Always Visible)

**Displays:**
- Model thumbnail/preview image
- Model name (editable in edit mode)
- Creator name with link to creator detail
- Collection path (Parent > Child)
- Tag chip row (clickable to filter, removable in edit mode)
- Quick action buttons:
  - `[Edit]` — Enter edit mode
  - `[Archive Link]` — View linked archives or search/create link
  - `[Print]` — Queue to printer via Bambuddy (if available)
  - `[Download]` — Download model files
  - `[Manyfold]` — Open in native Manyfold UI

### Tabbed Content Areas

#### Tab 1: Details (Primary Inspection Surface)

**Description Block:**
- Display Manyfold caption + description as read-only formatted text
- In edit mode, provide rich-text editor or markdown input
- Support inline rendering of model links

**Quick Stats:**
- File count and types (STL, 3MF, OBJ, etc.)
- Estimated print time (derived from largest/default file)
- Build volume dimensions (if available in metadata)
- Linked print count and most recent print date
- Model creation and last-update timestamps

**Enrichment Status:**
- License (displayed, editable via dropdown if authorized)
- Presupported indicator (Bambu Studio, Cura, etc.)
- Multi-color support hint (if model includes markers or metadata)
- Support type recommendations (tree, linear, etc.)

**Related/Variant Models:**
- Show calculated similarity scores
- Clickable preview to switch to related model
- Indicate family relationships (if phase 4 projects exist)

#### Tab 2: Media Gallery

**Implementation:** Adapt `print-history-photo-gallery-card.js` for model context

**Displays:**
- Thumbnail grid or carousel of model preview image + any user-provided photos
- Manyfold's `preview_file` as primary image
- Additional photos from model description or gallery uploads
- Photo metadata: filename, upload date, view count

**Actions:**
- Upload additional photos (for enrichment)
- Set as model preview image (if user has permission)
- Delete photos
- View full-screen slideshow

**Constraints:**
- Only allow photo operations if user is model creator or admin
- Preserve Manyfold's canonical preview-file association as source of truth
- Local photo uploads stored in sidecar or Bambuddy photo service

#### Tab 3: 3D Viewer

**Implementation:** Adapt `print-history-3d-viewer-card.js` for 3MF source files

**Key Differences from Print History:**
- No layer scrubber (source files don't have slice/layer information until sliced)
- Geometry visualization only (no nozzle path, no extrusion preview)
- Multiple file support (model may have several STL/3MF files)
- File selector dropdown to switch between files
- Build volume is model-agnostic unless metadata specifies target printer
- No time/layer animation

**Features:**
- 3D rotation, zoom, pan (standard Three.js OrbitControls)
- Ambient lighting with shadows (reference print-history viewer styling)
- Build volume grid overlay (optional, configurable)
- Measurement tool to inspect dimensions
- Cross-section / slice view (advanced feature, optional for phase 3)
- Capture snapshot and save as model thumbnail candidate
- Color picker for visualization mode (wireframe, flat, smooth)

**Rendering Options:**
- Line width adjustment
- Background color picker
- Transparency/opacity slider for multi-color visualization
- Grid overlay toggle
- Axes display toggle

#### Tab 4: Linked Prints (Archive Cross-Reference)

**Implementation:** Query bambuddy linkage store for archives linked to this model

**Displays:**
- List of print archives linked to this model (via `model_catalog_links` table)
- Archive summary: name, date, status, filament, duration
- Quick link to open archive detail popup
- Candidate unlink action (if not confirmed)

**Actions:**
- Open linked archive (navigate to print history popup)
- View all prints of this model (filter print-history view)
- Unlink if match is uncertain
- Re-link if previous link was deleted

---

## Surface 2: Media Gallery Card (Adapted)

### Design Approach

Reuse the core gallery from print history with these adaptations:

| Feature | Print History | Model Detail | Notes |
|---------|---------------|--------------|-------|
| Gallery trigger | Card + popup | Tab within detail popup | Embedded, not floating |
| Photo source | Archive photos from Bambuddy | Model preview + enrichment uploads | Simpler, no captured sequence |
| Primary photo selection | User-settable override | Preview-file is authoritative | Gallery shows which is preferred |
| Photo upload | Client resize + websocket | Same (reuse service) | Consistent upload flow |
| Photo delete | Bambuddy service call | Model photo record (local) | May need new service |
| Editing permissions | Archive owner | Model creator or admin | Enforce via HA user roles |

### Gallery Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ Media Gallery                                  [Expand] [Close] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │  [preview image - large display]                            │ │
│ │                                                             │ │
│ │  Current: Primary Preview ★                                │ │
│ │  [Prev] [Next] [Full-Screen]                               │ │
│ │                                                             │ │
│ │  [Upload Photo] [Download] [Delete] [Use As Preview]      │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ Thumbnails:                                                    │
│ [thumb1★] [thumb2] [thumb3] [thumb4] ...  [+]               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Surface 3: 3D Viewer Card (Adapted for Source Models)

### Architecture Differences

**Print History 3D Viewer:**
- Input: gcode or compiled/sliced geometry
- Purpose: Preview sliced result + timing
- Features: layer scrubber, extrusion width, travel moves, animation

**Model 3D Viewer (Phase 3):**
- Input: raw 3MF, STL, OBJ source files
- Purpose: Inspect geometry, estimate build volume fit
- Features: solid geometry, lighting, materials, multi-file switching

### Core Features

```
┌─────────────────────────────────────────────────────────────────┐
│ 3D Viewer                                      [Configuration]   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ File Selector:  [Dropdown: Select file from model]             │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │  [3D Canvas - ThreeJS renderer]                             │ │
│ │                                                             │ │
│ │  Interaction:                                               │ │
│ │   - Drag to rotate                                          │ │
│ │   - Scroll to zoom                                          │ │
│ │   - Right-click drag to pan                                 │ │
│ │                                                             │ │
│ │  [Reset View] [Fit All] [Axes] [Grid]                      │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ Rendering Options:                                              │
│  • Background Color: [color picker]                             │
│  • Wireframe Mode: [toggle]                                     │
│  • Show Axes: [toggle]  Show Grid: [toggle]                     │
│  • Line Width: [slider] 1-5                                     │
│  • Opacity: [slider] 0-100%                                     │
│                                                                 │
│ Measurement:                                                    │
│  • Build Volume: 256 × 256 × 256 mm (estimated)                │
│  • Model Bounds: [auto-calculated]                             │
│                                                                 │
│ Actions:                                                        │
│  [Capture Screenshot] [Download STL] [View in Manyfold]        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Implementation Libraries & Approach

**Recommended Approach:**
The best balance of determinism, reusability, and maintainability is a **lib3mf-backed service layer** with a **Three.js frontend**.

#### Option A: lib3mf Service Layer + Three.js Frontend (Recommended)

**Architecture:**
```
┌─────────────────────────────────────────────┐
│ HA Custom Card (Vue + Three.js)             │
│  - User interactions, UI, rendering control │
└─────────────────────────┬───────────────────┘
                          ↓
┌─────────────────────────────────────────────┐
│ REST API (model_catalog_3d_service)         │
│  - GET /models/{id}/geometry                │
│  - GET /models/{id}/materials               │
│  - POST /models/{id}/validate-printability  │
└─────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────┐
│ lib3mf Parser (Dockerized Service)          │
│  - Parse 3MF/STL/OBJ files                  │
│  - Extract geometry + metadata              │
│  - Validate structure & materials           │
│  - Convert to Three.js compatible format    │
└─────────────────────────────────────────────┘
```

**Why this approach:**
- ✅ lib3mf is the 3MF Consortium standard library (C++, WASM)
- ✅ Dockerized service keeps parsing isolated and reusable
- ✅ Three.js is lightweight, well-documented, battle-tested
- ✅ Matches your preference for deterministic, modular subsystems
- ✅ Can be used for other features (print preview, damage inspection, etc.)
- ✅ Supports streaming/lazy load for large files

**Implementation Sequencing:**
1. **Phase 3 Minimum**: Pre-render static thumbnails from Manyfold, embed as scene setup
2. **Phase 3+ Feature**: Add lib3mf service layer for live parsing
3. **Phase 3+ Enhancement**: Add printability validation (requires slicing engine)

#### Option B: 3mfViewer Consortium (React + Three.js + lib3mf WASM)

**Pros:**
- Official 3MF Consortium viewer
- Pure JavaScript/WASM (no server needed)
- Supports materials, colors, metadata
- Actively maintained

**Cons:**
- Heavier bundle size (~5MB WASM)
- React dependency conflicts
- Less flexible for HA card integration
- Harder to customize for HA design language

**Use Case:** If you need full material/color support early, consider forking 3mfViewer's Three.js setup.

#### Option C: Manyfold Source (Reference Only)

**Status:** Manyfold has a basic 3D viewer but it's primarily for UI internal use.

**Assessment:** Not suitable as a direct reuse candidate—better to model the architecture and adapt for HA.

---

## Editable Fields & Edit Mode

### Field Inventory

**From Manyfold (API Writable):**
- `name` — Model title
- `caption` — Short description (< 200 chars)
- `description` — Long-form markdown
- `keywords` — Tags (comma-separated or array)
- `links` — External references (URLs)
- `collection_id` — Parent collection
- `preview_file_id` — Which file is the preview

**From Enrichment Layer (Custom Fields - Local SQLite):**
- `color_scheme` — Suggested filament colors (derived from model geometry or user annotation)
- `print_time_estimate` — Operator estimate (can override auto-calc)
- `support_type_hint` — Recommended support strategy
- `multi_color_scheme` — Color layer mapping (if model supports it)
- `difficulty_level` — Beginner / Intermediate / Advanced
- `print_notes` — Operator tips (print failures, settings, variants)
- `external_reference` — Link to original source/designer
- `bambuddy_project_id` — Optional Bambuddy project association

**Read-Only (For Information):**
- Creator (linked to creator detail, not editable from model view)
- File metadata (file count, formats, sizes)
- Upload timestamps
- Manyfold-internal linkage (user follows, likes, etc. — if fetched)

### Edit Mode UX

**Activation:**
- Click `[Edit]` button in header
- Form overlays details tab
- Cancel/Save buttons replace action buttons

**Validation:**
- Client-side: required fields, format validation
- Server-side: API validation on save
- Error display: inline beneath field with help text

**Autosave vs. Explicit Save:**
- **No autosave** — matches HA pattern for deterministic updates
- **Explicit Save** — user clicks `[Save Changes]` to commit
- **Confirmation** — show diff preview before final save

**Conflict Handling:**
- If model is modified in Manyfold while editing in HA:
  - Display warning: "Model has been updated. Reload to see latest."
  - Offer `[Reload]` or `[Compare]` option
  - Prevent conflicting save

### Form Layout (Edit Mode)

```
┌─────────────────────────────────────────────────────────────────┐
│ Edit Model Details                           [Compare] [Reload] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Model Name: [text input - 100 chars max]                       │
│                                                                 │
│ Collection: [dropdown - select from hierarchy]                 │
│                                                                 │
│ Tags: [multi-select chips with autocomplete]                   │
│       [Suggested: tag1, tag2, tag3 (from color analysis)]     │
│       [Tip: Tags help group related models]                    │
│                                                                 │
│ Description: [rich text editor or markdown]                    │
│  [Character count: 347/5000]                                   │
│  [Preview below ↓]                                             │
│                                                                 │
│ Enrichment Fields:                                              │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Color Scheme: [color chips from model geometry]             │ │
│ │              [+ Add custom color]                           │ │
│ │                                                             │ │
│ │ Support Type: [Dropdown: None / Linear / Tree]              │ │
│ │               Tip: Based on model geometry analysis          │ │
│ │                                                             │ │
│ │ Difficulty: [Dropdown: Beginner / Intermediate / Advanced] │ │
│ │                                                             │ │
│ │ Print Notes: [Text area for operator tips]                  │ │
│ │             [Example: "Best with 0.4mm nozzle, 210°C"]      │ │
│ │                                                             │ │
│ │ Linked Bambuddy Project: [Dropdown or search box]           │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ [Save Changes] [Cancel Changes] [Reset to Defaults]           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Service Layer Requirements

### New HA Services (Phase 3)

```yaml
model_catalog.get_model_detail:
  description: Fetch complete model detail with enrichment
  fields:
    model_id:
      description: Manyfold model ID
    entry_id:
      description: Optional HA integration entry ID
  returns:
    model:
      model_id: int
      name: string
      description: string
      tags: [string]
      creator: object
      collection: object
      files: [object]
      preview_file_id: int
      created_at: timestamp
      updated_at: timestamp
      enrichment:
        color_scheme: [string]
        print_time_estimate: int (seconds)
        support_type_hint: string
        difficulty_level: string
        print_notes: string
      linked_archives:
        - archive_id: int
          archive_name: string
          print_date: timestamp
          status: string
      related_models:
        - model_id: int
          name: string
          similarity_score: float

model_catalog.update_model:
  description: Update model name, description, tags, enrichment
  fields:
    model_id:
      description: Manyfold model ID
    updates:
      description: Fields to update
      type: object
  returns:
    success: boolean
    errors: [string] if any

model_catalog.upload_model_photo:
  description: Upload additional photo for model (enrichment)
  fields:
    model_id: int
    image_data: base64 or URL
    is_preview: boolean (optional, set as model preview?)
  returns:
    photo_id: int
    url: string
    error: string if failed

model_catalog.get_3d_geometry:
  description: Fetch geometry for 3D viewer
  fields:
    model_id: int
    file_id: int
    format: string (threejs-json | gltf | obj)
  returns:
    geometry_url: string
    materials: [object] if available
    bounds: {min: {x,y,z}, max: {x,y,z}}
    error: string if unsupported format

model_catalog.link_archive_to_model:
  description: Link print archive to this model
  fields:
    model_id: int
    archive_id: int
    confidence: string (manual | high | medium | low)
  returns:
    link_id: int
    success: boolean

model_catalog.unlink_archive:
  description: Remove archive link
  fields:
    link_id: int
  returns:
    success: boolean
```

### Sidecar Endpoints (New/Updated)

```
GET  /models/{model_id}
     Response: normalized model detail + enrichment metadata

GET  /models/{model_id}/geometry?file_id={file_id}&format={threejs|gltf|obj}
     Response: 3D geometry data or URL to fetch

GET  /models/{model_id}/photos
     Response: list of model photos (preview + any enrichment uploads)

POST /models/{model_id}/photos
     Body: multipart image upload
     Response: photo metadata + URL

DELETE /models/{model_id}/photos/{photo_id}
     Response: success

PATCH /models/{model_id}
      Body: {name, description, tags, enrichment_fields}
      Response: updated model record

GET  /models/{model_id}/archives
     Response: list of linked print archives

POST /models/{model_id}/archives
     Body: {archive_id, confidence}
     Response: link record

DELETE /models/{model_id}/archives/{link_id}
      Response: success
```

---

## Custom 3D Viewer Card Implementation

### Web Component Structure

```javascript
class ModelDetail3dViewerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    
    // State
    this._hass = null;
    this._config = null;
    this._model = null;
    this._geometry = null;
    this._selectedFileId = null;
    this._viewerSettings = {
      backgroundColor: "#08101A",
      renderGrid: true,
      renderAxes: true,
      wireframe: false,
      opacity: 1.0,
      lineWidth: 1,
    };
    
    // ThreeJS objects
    this._scene = null;
    this._camera = null;
    this._renderer = null;
    this._controls = null;
    this._geometryMeshes = [];
  }

  setConfig(config) {
    this._config = config;
    this._renderShell();
  }

  set hass(hass) {
    this._hass = hass;
    this._maybeLoad();
  }

  connectedCallback() {
    this._attachListeners();
    this._maybeLoad();
  }

  async _maybeLoad() {
    if (!this.isConnected || !this._config || !this._hass) return;
    
    // Fetch model detail from HA service
    const result = await this._hass.callService(
      "model_catalog",
      "get_model_detail",
      { model_id: this._config.model_id }
    );
    
    this._model = result.model;
    await this._loadGeometry(this._model.files[0].id);
    this._render();
  }

  async _loadGeometry(fileId) {
    const result = await this._hass.callService(
      "model_catalog",
      "get_3d_geometry",
      { 
        model_id: this._config.model_id,
        file_id: fileId,
        format: "threejs-json"
      }
    );
    
    // Parse and load into ThreeJS scene
    this._geometry = await this._parseGeometry(result.geometry_url);
    this._updateScene();
  }

  _initializeThreeJS() {
    const container = this.shadowRoot.querySelector(".viewer-container");
    
    this._scene = new THREE.Scene();
    this._scene.background = new THREE.Color(this._viewerSettings.backgroundColor);
    
    this._camera = new THREE.PerspectiveCamera(
      75,
      container.clientWidth / container.clientHeight,
      0.1,
      1000
    );
    
    this._renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this._renderer.setSize(container.clientWidth, container.clientHeight);
    this._renderer.shadowMap.enabled = true;
    
    container.appendChild(this._renderer.domElement);
    
    // Lighting
    const light = new THREE.DirectionalLight(0xffffff, 0.8);
    light.position.set(10, 20, 10);
    light.castShadow = true;
    this._scene.add(light);
    
    this._scene.add(new THREE.AmbientLight(0xffffff, 0.4));
    
    // Controls
    this._controls = new THREE.OrbitControls(this._camera, this._renderer.domElement);
    this._controls.enableDamping = true;
    this._controls.dampingFactor = 0.05;
    
    // Render loop
    this._renderLoop();
  }

  _renderLoop = () => {
    requestAnimationFrame(this._renderLoop);
    this._controls.update();
    this._renderer.render(this._scene, this._camera);
  }

  _updateScene() {
    // Clear old meshes
    this._geometryMeshes.forEach(mesh => this._scene.remove(mesh));
    this._geometryMeshes = [];
    
    // Add new geometry
    if (this._geometry) {
      const mesh = new THREE.Mesh(
        this._geometry,
        new THREE.MeshStandardMaterial({
          color: 0x7dd3c8,
          metalness: 0.3,
          roughness: 0.6,
          wireframe: this._viewerSettings.wireframe,
          opacity: this._viewerSettings.opacity,
          transparent: this._viewerSettings.opacity < 1,
        })
      );
      
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      this._scene.add(mesh);
      this._geometryMeshes.push(mesh);
      
      // Auto-fit camera
      this._fitCameraToObject();
    }
  }

  _fitCameraToObject() {
    if (this._geometryMeshes.length === 0) return;
    
    const box = new THREE.Box3().setFromObject(
      this._geometryMeshes[0]
    );
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = this._camera.fov * (Math.PI / 180);
    const cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));
    
    this._camera.position.z = cameraZ * 1.5;
    this._camera.lookAt(box.getCenter(new THREE.Vector3()));
    this._controls.target = box.getCenter(new THREE.Vector3());
    this._controls.update();
  }

  // UI event handlers, settings updates, etc.
}

customElements.define("model-detail-3d-viewer-card", Model Detail3dViewerCard);
```

### Dependencies

- **Three.js** (existing in print history, reuse)
- **OrbitControls.js** (existing, reuse)
- **lib3mf WASM** (if Phase 3+ feature)
- **Three.js loaders** (GLTFLoader, STLLoader, OBJLoader)

---

## Implementation Roadmap

### Phase 3.0: Detail View MVP (Required)

**Deliverables:**
1. ✅ Detail popup container and tabbed navigation
2. ✅ Details tab: static metadata display (no edit mode yet)
3. ✅ Media Gallery tab: adapt print-history gallery for model (display only)
4. ✅ 3D Viewer tab: static Three.js viewer with thumbnail data from Manyfold
5. ✅ Linked Prints tab: show archives linked to model
6. ✅ New services: `get_model_detail`, `get_3d_geometry`
7. ✅ Custom card: `model-detail-popup-card.js`

**Estimated Effort:** 40-50 hours

---

### Phase 3.1: Edit Mode (Follow-Up)

**Deliverables:**
1. ✅ Edit button and form overlay
2. ✅ Editable fields: name, description, tags, collection
3. ✅ Save/Cancel logic with HA service calls
4. ✅ Conflict detection and reload handling
5. ✅ Enrichment field form (color, support type, difficulty, notes)
6. ✅ New services: `update_model`, `upload_model_photo`

**Estimated Effort:** 25-30 hours

---

### Phase 3.2+: Advanced Features (Optional Future)

**Candidates:**
1. Photo upload and gallery management for enrichment
2. lib3mf service integration for live geometry parsing
3. Printability validation (requires slicing engine)
4. Cross-system navigation (archive → project → related models)
5. Bulk edit operations for related models

---

## Reference Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│ Home Assistant UI Layer                                       │
│                                                               │
│  ┌─ Detail Popup ─────────────────────────────────────────┐  │
│  │  [Header] [Tabs] [Tab Content]                         │  │
│  │   • Details Tab (form + display)                       │  │
│  │   • Gallery Tab (photo-gallery-card adapter)           │  │
│  │   • 3D Viewer Tab (3d-viewer-card)                     │  │
│  │   • Linked Prints Tab (archive list + links)           │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌─ Custom Cards (Web Components) ─────────────────────────┐ │
│  │  • model-detail-popup-card.js                          │  │
│  │  • model-detail-3d-viewer-card.js (extends viewer)     │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
└─────────────────────────────────┬──────────────────────────────┘
                                  │ HA Services & Integration API
                                  ↓
┌──────────────────────────────────────────────────────────────┐
│ HA Integration Layer (bambuddy custom component)             │
│                                                               │
│  Services:                                                   │
│   • model_catalog.get_model_detail                           │
│   • model_catalog.update_model                               │
│   • model_catalog.get_3d_geometry                            │
│   • model_catalog.upload_model_photo                         │
│   • model_catalog.link_archive_to_model                      │
│                                                               │
│  Data Flow:                                                  │
│   • Fetch from model_catalog sidecar                         │
│   • Enrich with local SQLite linkage metadata                │
│   • Return normalized DTO                                    │
│                                                               │
└─────────────────────────────────┬──────────────────────────────┘
                                  │ REST API
                                  ↓
┌──────────────────────────────────────────────────────────────┐
│ Model Catalog Sidecar (FastAPI Service)                      │
│                                                               │
│  Endpoints:                                                  │
│   GET /models/{id}                                           │
│   GET /models/{id}/geometry?file_id=X&format=Y               │
│   GET /models/{id}/photos                                    │
│   PATCH /models/{id}                                         │
│   GET /models/{id}/archives                                  │
│                                                               │
│  Data Access:                                                │
│   • Fetch from Manyfold REST API                             │
│   • Query local SQLite (enrichment, linkage)                 │
│   • Cache normalized records                                 │
│                                                               │
└─────────────────────────────────┬──────────────────────────────┘
                                  │ REST API
                                  ↓
┌──────────────────────────────────────────────────────────────┐
│ Upstream Data Sources                                        │
│                                                               │
│  • Manyfold API (model metadata, files, preview)             │
│  • Model Catalog SQLite Store (linkage, enrichment)          │
│  • Bambuddy API (archive details for linked prints)          │
│  • lib3mf Service (geometry parsing) [Phase 3+ feature]      │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Open Design Questions

1. **Build Volume Estimation**: Should the 3D viewer auto-detect model bounds or show a configurable printer profile (e.g., X1C 256×256×256)?

2. **Presupported Metadata**: Manyfold doesn't store printer-specific presupported info. Should we:
   - Infer from file format (Bambu Studio .3mf)?
   - Manual enrichment field (user-settable)?
   - External service lookup (third-party presupported DB)?

3. **Multi-Color Visualization**: Should the viewer support:
   - Rendering multiple colors if .3mf contains paint definitions?
   - Layer-by-layer color indication (requires slicing)?
   - Simplified heuristic (detect geometry regions)?

4. **Photo Permission Model**: Should photo upload be:
   - Restricted to model creator?
   - Allowed for any authenticated user (enrichment contributor)?
   - Operator-role-based?

5. **Library-Level Context**: Should detail popup include:
   - Count of related print queues?
   - Filament inventory check for linked filaments?
   - Recent search/favorite history for quick re-access?

---

## Integration With Existing Features

### Print History Archive Popup

**Linkage Point:** Archive detail popup includes "Linked Model" block

**Interaction:**
- Click `[View]` in linked-model block → opens model detail popup
- Same pattern as print history photo-gallery interaction
- Modal stacking: archive → model detail

### Manyfold Native UI

**No Replacement Intent:** Model detail popup is read-only surface supplementary to Manyfold native UI

**Navigation:**
- Include `[Open in Manyfold]` button for full editor/social features
- Manyfold remains authoritative for creator/collection management
- HA is view/enrichment/linkage layer

### Model Catalog Browser (Phase 2)

**Relationship:**
- Model catalog browser lists/searches models
- Click model → opens detail popup
- Detail popup is detail view for single model

---

## Success Criteria

- ✅ Detail popup renders without errors for all models in user's Manyfold instance
- ✅ Photo gallery display matches print-history styling and usability
- ✅ 3D viewer loads geometry and renders without performance issues for models <50MB
- ✅ Edit mode saves changes to Manyfold via REST API with success/error handling
- ✅ Linked archives display correctly and navigate to archive detail popup
- ✅ Services handle missing/invalid data gracefully (fallback display)
- ✅ All HA service contracts documented and testable
- ✅ Custom cards installable via standard HA mechanisms (www/custom_components)
- ✅ Mobile responsive (phone/tablet gallery works as expected)

---

## References

- [Print History Photo Gallery Implementation](../../print_history/print-history-photo-gallery-card.js)
- [Print History 3D Viewer Implementation](../../print_history/print-history-3d-viewer-card.js)
- [Manyfold API Documentation](https://manyfold.app/api/v0)
- [3MF Consortium Specifications](https://3mf.io/)
- [3mfViewer Reference Implementation](https://github.com/3MFConsortium/3mf-viewer)
- [Three.js Documentation](https://threejs.org/docs/)
- [lib3mf Reference](https://github.com/3MFConsortium/lib3mf)

---

## Next Steps

1. **Review & Approve:** This design with stakeholders
2. **Clarify Open Questions:** Address design questions section above
3. **Architecture Review:** Validate service layer contracts
4. **Begin Phase 3.0:** Implement detail popup MVP
5. **Update GitHub Issue:** Link to this design doc and update #1125
