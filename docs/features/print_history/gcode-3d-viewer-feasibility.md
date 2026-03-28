# GCode & 3D Model Viewing in Home Assistant — Feasibility Analysis

## What Bambuddy Does

Bambuddy provides two distinct 3D viewing modes in its React frontend:

### 1. Model Viewer (Three.js)

**File**: `frontend/src/components/ModelViewer.tsx`
**Tech**: Three.js + JSZip + OrbitControls

Downloads the 3MF file from `/archives/{id}/download` (or source from `/archives/{id}/source`), unzips in-browser with JSZip, parses the XML `.model` files to extract:
- Mesh data (vertices, triangles)
- Component references and build transforms
- Multi-plate support (filter by `selectedPlateId`)
- Per-extruder coloring from `filamentColors` array

Renders a fully interactive 3D mesh with orbit controls, zoom, reset. Handles multi-object, multi-plate models with per-extruder coloring.

### 2. GCode Viewer (gcode-preview)

**File**: `frontend/src/components/GcodeViewer.tsx`
**Tech**: `gcode-preview` npm library (`WebGLPreview`) — NOT Three.js

Downloads extracted G-code from `/archives/{id}/gcode`, renders extrusion paths as colored lines:
- Layer-by-layer slider (1 to totalLayers)
- Multi-tool color via `filamentColors` array
- Tool remapping for T0-T7 tool changes
- Shows the actual sliced toolpath, not the 3D model geometry

### Relevant API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /archives/{id}/capabilities` | Check `has_model`, `has_gcode`, `has_source`, get `build_volume` and `filament_colors` |
| `GET /archives/{id}/gcode` | Extract G-code as `text/plain` |
| `GET /archives/{id}/download` | Download 3MF file |
| `GET /archives/{id}/thumbnail` | Get thumbnail PNG (unauthenticated) |
| `GET /archives/{id}/plate-preview` | Get slicer plate preview image |

---

## Approaches for Home Assistant

### Option A: Iframe Embed (Recommended)

**Embed the Bambuddy archive page directly** in an HA dashboard using a `webpage` card or `browser_mod` popup.

Bambuddy serves each archive at `{bambuddy_url}/archives/{id}`. This page already includes the model viewer, gcode viewer, photos, metadata, and all interactive controls.

**Implementation:**
```yaml
# Lovelace card — static iframe
type: iframe
url: "http://bambuddy.local:8902/archives/171"
aspect_ratio: "16:9"
```

Or dynamically based on the current archive:
```yaml
# Using auto-entities or custom:config-template-card
type: iframe
url: >-
  http://bambuddy.local:8902/archives/{{ states('input_text.bambuddy_current_archive_id') }}
```

**Popup via browser_mod:**
```yaml
tap_action:
  action: fire-dom-event
  browser_mod:
    service: browser_mod.popup
    data:
      title: "Archive Preview"
      content:
        type: iframe
        url: "http://bambuddy.local:8902/archives/171"
        aspect_ratio: "16:9"
```

**Pros:**
- Zero development effort
- Full Bambuddy UI including all viewers, photos, metadata
- Automatically stays up-to-date with Bambuddy updates
- Interactive (orbit, zoom, layer scrub)

**Cons:**
- Requires Bambuddy to be network-accessible from the browser
- Bambuddy auth may block the embed (check CORS / cookie settings)
- Not "native" HA look and feel
- Can't control which viewer mode is initially shown

**Auth consideration**: Bambuddy uses API key auth for API calls, but the web UI may have its own session auth. If the iframe prompts for login, this approach becomes less seamless. Test whether the archive page is accessible without auth when accessed from the same network.

### Option B: Thumbnail + Preview Images (Simplest)

Skip 3D rendering entirely. Use Bambuddy's pre-rendered images:

```yaml
# Generic camera or picture entity card
type: picture-entity
entity: sensor.bambuddy_last_archive
image: "http://bambuddy.local:8902/api/v1/archives/171/thumbnail"
```

The `/thumbnail` and `/plate-preview` endpoints are **unauthenticated** (designed for `<img>` tags), so they work directly in HA picture cards.

**Pros:**
- Trivially simple
- No auth issues (thumbnail endpoints are public)
- Fast loading
- Works on all devices

**Cons:**
- Static image, no interactivity
- No layer-by-layer view
- No orbit/zoom

### Option C: Custom Lovelace Card (Complex)

Port the `gcode-preview` library to a custom HA Lovelace card that fetches gcode from Bambuddy's API and renders it.

**Architecture:**
```
Custom Card (TypeScript/Lit)
  → Fetch /archives/{id}/capabilities (check has_gcode)
  → Fetch /archives/{id}/gcode (get gcode text)
  → Initialize WebGLPreview from gcode-preview
  → Render canvas with layer slider
```

**Pros:**
- Native HA integration
- Full control over appearance
- No iframe auth issues

**Cons:**
- Significant development effort (custom card development, testing)
- Must maintain the card across HA and gcode-preview library updates
- WebGL may not work well on all HA frontends (companion app, tablets)
- Only handles gcode, not 3MF model viewing (would need Three.js too)

### Option D: Standalone HTML Page + Popup

Create a static HTML page (served from HA's `www/` folder) that loads `gcode-preview` from CDN and fetches gcode from Bambuddy's API.

```html
<!-- www/3d_printing/gcode-viewer.html -->
<script src="https://cdn.jsdelivr.net/npm/gcode-preview/dist/gcode-preview.min.js"></script>
<script>
  const params = new URLSearchParams(window.location.search);
  const archiveId = params.get('id');
  fetch(`/api/v1/archives/${archiveId}/gcode`, { headers: {'X-API-Key': 'KEY'} })
    .then(r => r.text())
    .then(gcode => {
      const preview = new GCodePreview.WebGLPreview({ canvas: document.getElementById('canvas') });
      preview.processGCode(gcode);
    });
</script>
<canvas id="canvas" style="width:100%;height:100%"></canvas>
```

Open via browser_mod popup:
```yaml
tap_action:
  action: navigate
  navigation_path: "/local/3d_printing/gcode-viewer.html?id=171"
```

**Pros:**
- Moderate effort (simple HTML page)
- Interactive gcode preview
- Served from HA, no external auth

**Cons:**
- API key exposed in client-side HTML (security concern)
- CORS: Bambuddy API must accept requests from HA's origin
- Not a true Lovelace card (separate page)
- Maintenance of the HTML page

---

## Recommendation

| Approach | Effort | Quality | Recommended For |
|----------|--------|---------|-----------------|
| **A: Iframe** | None | High | **Primary approach** — try this first |
| **B: Thumbnails** | Minimal | Medium | **Always include** — dashboard card images |
| C: Custom card | High | Highest | Only if iframe doesn't work |
| D: Standalone HTML | Medium | Medium | Fallback if iframe has auth issues |

**Start with B (thumbnails) for dashboard cards** — use `/archives/{id}/thumbnail` in picture cards. This works immediately with no auth issues.

**Add A (iframe) for detail view** — when a user taps the archive card, open a `browser_mod` popup with an iframe to the Bambuddy archive page. This gives full 3D viewing with zero development.

**Only consider C or D** if Bambuddy's web UI has auth/CORS issues that block iframe embedding on the local network.

---

## Implementation Plan

### Phase 2 (print_history)
- Use `/archives/{id}/thumbnail` for archive card images (already unauthenticated)
- Use `/archives/{id}/plate-preview` for plate-specific thumbnails

### Phase 2.1 (enhanced viewing)
- Test iframe embed of Bambuddy archive page
- If iframe works: add `browser_mod` popup action to archive cards
- If iframe blocked: evaluate Option D (standalone HTML page)

### Future
- Custom Lovelace card only if there's demand for native HA 3D viewing
