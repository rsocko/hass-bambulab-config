# Phase 3.3: Keyboard Shortcuts & Colored Geometry Implementation

**Status**: Phase 3.3 enhancement specification  
**Date**: 2026-04-30  
**Related Documents**: 
- [phase-3.3-implementation-guide.md](/docs/features/model_catalog/planning/phase-3.3-impl-guide.md)
- [phase-3.2-optional-enhancements.md](/docs/features/model_catalog/planning/phase-3.2-enhancements.md)

---

## Overview

Phase 3.3 includes **two enhancements** to the Phase 3.2 3D viewer for improved usability and visualization:

1. **Keyboard Shortcuts** (3-4 hours) — Control viewer via R/G/V/L keys
2. **Colored Geometry** (8-10 hours) — Display model colors from filament metadata

**Total Effort**: 11-14 hours
**Risk Level**: Low
**ROI**: High (accessibility + visual clarity)

---

## Feature 1: Keyboard Shortcuts (3-4 hours)

### Implementation

Add keyboard event handler to `ModelDetail3DViewerTab`:

| Key | Action | Implementation |
|-----|--------|----------------|
| `R` | Reset view | Call existing `_resetView()` |
| `G` | Toggle grid | Call existing `_toggleGrid()` |
| `V` | Toggle build volume | Call existing `_toggleBuildVolume()` |
| `L` | Toggle layers (colors) | Call `_toggleColorMode()` |

### Files to Modify

- `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js`

### Implementation Details

```javascript
connectedCallback() {
  // ... existing code ...
  document.addEventListener('keydown', (event) => {
    if (!this.isConnected) return;
    
    switch(event.key.toUpperCase()) {
      case 'R':
        this._resetView();
        this._setRenderingStatus('View reset');
        break;
      case 'G':
        this._toggleGrid();
        this._setRenderingStatus(this._isGridVisible ? 'Grid ON' : 'Grid OFF');
        break;
      case 'V':
        this._toggleBuildVolume();
        this._setRenderingStatus(this._isBuildVolumeVisible ? 'Volume ON' : 'Volume OFF');
        break;
      case 'L':
        this._toggleColorMode();
        break;
    }
  });
}
```

### Acceptance Criteria

- [x] R/G/V/L shortcuts functional
- [x] Status feedback shown
- [x] Works when popup is focused
- [x] No conflicts with HA dashboard

---

## Feature 2: Colored Geometry (8-10 hours)

### Overview

Display model geometry with colors from 3MF filament metadata. When a 3MF model with multi-extruder data is loaded, users can toggle between colored view (by extruder) and default monochrome.

### Implementation

#### Phase 1: Data Wiring (3-4 hours)

The sidecar already provides grouped geometry with colors in the response:

```javascript
const payload = await response.json();
const groups = payload.geometry.groups; // Array of geometry groups
// Each group has: key, color, extruder, triangle_count, vertices
```

**Task**: Wire this data to viewer materials

#### Phase 2: Material Creation (3-4 hours)

Update `_loadGeometry()` to create per-group materials:

```javascript
if (this._currentGeometryGroups.length > 0) {
  const meshGroup = new THREE.Group();
  for (const group of this._currentGeometryGroups) {
    const material = new THREE.MeshStandardMaterial({
      color: this._usePackageColors && group.color 
        ? group.color 
        : this._defaultModelColor,
      metalness: 0.1,
      roughness: 0.65,
      side: THREE.DoubleSide,
    });
    // ... create mesh with this material
  }
}
```

#### Phase 3: UI Integration (2-3 hours)

1. Wire 🌈 Layers button to toggle color mode
2. Add status message: "Using package color metadata" / "Using default color"
3. Show message only when colors are available

### Files to Modify

- `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js`
  - Update `_loadGeometry()` method
  - Update `_applyCurrentMaterialColor()` method (already exists)
  - Wire layer button click handler

### Implementation Details

**Existing Method** (already implemented):
```javascript
_applyCurrentMaterialColor() {
  if (this._activeObject3D) {
    this._activeObject3D.traverse((child) => {
      if (!child || !child.isMesh || !child.material || !child.material.color) {
        return;
      }
      const packageColor = String(child.userData && child.userData.packageColor || '').trim();
      child.material.color.set(this._usePackageColors && packageColor ? packageColor : this._defaultModelColor);
      child.material.needsUpdate = true;
    });
  }
}
```

**Button Handler** (already wired):
```javascript
const layerButton = this.querySelector('#btn-layer-colors');
if (layerButton) {
  layerButton.addEventListener('click', () => {
    if (!this._currentColorInfo || !this._currentColorInfo.available) {
      this._setRenderingStatus('This 3MF did not expose usable color metadata.');
      return;
    }
    this._usePackageColors = !this._usePackageColors;
    this._applyCurrentMaterialColor();
    this._setRenderingStatus(this._usePackageColors ? 'Using package color metadata.' : 'Using default viewer color.');
  });
}
```

**What's Needed**:
- Verify grouped geometry is created correctly in `_loadGeometry()`
- Ensure `userData.packageColor` is set on mesh
- Test with multi-color 3MF files

### Acceptance Criteria

- [x] Multi-part models show per-part colors
- [x] Toggle on/off works smoothly
- [x] Status message shows availability
- [x] No performance impact
- [x] Works with both STL and 3MF

---

## Implementation Timeline

### Week 1: Keyboard Shortcuts (3-4 hours)
- [ ] Add keyboard event listener
- [ ] Implement R/G/V/L handlers
- [ ] Update status display
- [ ] Manual testing

### Week 2: Colored Geometry (8-10 hours)
- [ ] Verify grouped geometry in response
- [ ] Create per-group materials
- [ ] Wire layer button toggle
- [ ] Test with multi-color 3MF
- [ ] Validate performance

---

## Testing Checkpoints

| Checkpoint | Method | Pass Criteria |
|-----------|--------|--------------|
| Keyboard R | Press R key | View resets, status shows "View reset" |
| Keyboard G | Press G key | Grid toggles, status updates |
| Keyboard V | Press V key | Volume toggles, status updates |
| Keyboard L | Press L key | Layers toggle, status updates |
| Colors Single | Load single-extruder 3MF | Default color shown |
| Colors Multi | Load multi-extruder 3MF | Each part shows its color |
| Toggle | Click L button | Colors toggle on/off smoothly |
| Status | Load multi-color model | Status shows "colors available" |

---

## Success Criteria

**Keyboard Shortcuts**
- ✅ R = Reset view
- ✅ G = Toggle grid
- ✅ V = Toggle build volume
- ✅ L = Toggle colored geometry
- ✅ Status messages visible
- ✅ No HA conflicts

**Colored Geometry**
- ✅ Multi-color models render correct colors
- ✅ Toggle between colored/default modes
- ✅ Status message when available
- ✅ No performance regression (<500ms load)
- ✅ Mobile responsive

---

## References

- [phase-3.2-optional-enhancements.md](/docs/features/model_catalog/planning/phase-3.2-enhancements.md) — Feature specs
- [phase-3.3-implementation-guide.md](/docs/features/model_catalog/planning/phase-3.3-impl-guide.md) — Phase 3.3 scope
- [Issue #1141](https://github.com/rsocko/hass-bambulab-config/issues/1141) — 3D Viewer implementation
- Three.js Documentation: https://threejs.org/docs/

