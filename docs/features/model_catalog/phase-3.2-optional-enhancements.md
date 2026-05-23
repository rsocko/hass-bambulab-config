# Phase 3.3: Keyboard Shortcuts & Colored Geometry Enhancement

**Status**: Phase 3.3 enhancement specification  
**Date**: 2026-04-30  
**Related Issue**: #1141 (Phase 4/Phase 6: 3D Viewer with Three.js)  
**Scope**: Phase 3.3 viewer polish

---

## Overview

Phase 3.2 core implementation is **complete and production-ready** with four core features:
1. ✅ Interactive OrbitControls (rotate, zoom, pan)
2. ✅ 3MF file format support (multi-part rendering)
3. ✅ Build volume visualization (Bambu P1S reference box)
4. ✅ Viewer state persistence (sessionStorage)

Phase 3.3 adds **two enhancements** for improved usability and visualization:
1. Keyboard shortcuts for viewer control
2. Colored geometry display based on model metadata

---

## Feature 1: Colored Geometry Display (8-10 hours)

### Description

Display model geometry with colors based on extruder assignments and filament metadata from 3MF files.

### Current State

- **UI**: Toggle button (🌈 Layers) exists in toolbar but shows "not implemented yet"
- **Data**: Color metadata already extracted by `extract_3mf_geometry()` in sidecar
- **Status**: Backend ready, frontend needs wiring

### Implementation Requirements

- Extract color data from geometry endpoint response
- Group geometry by color in viewer (data already grouped)
- Apply material colors to mesh based on extruder assignment
- Wire 🌈 Layers button to toggle color mode on/off
- Show status message when multi-color available

### Data Flow

```
3MF package (sidecar)
├── extract_3mf_geometry()
│   ├── Filament color palette (from project settings)
│   ├── Extruder assignments (from model settings)
│   └── Grouped vertices by color
└── API response: geometry.groups[].color

Viewer (frontend)
├── Receive grouped geometry with colors
├── Create material per group
└── Toggle color mode on/off
```

### Implementation Details

#### File: `model-detail-3d-viewer-tab.js`

1. **Parse grouped geometry** from endpoint response:
```javascript
const groups = parsed.groups || [];  // Already in geometry payload
groups.forEach(group => {
  const color = group.color || this._defaultModelColor;
  // Create material with this color
});
```

2. **Wire 🌈 Layers button** to existing toggle:
```javascript
const layerButton = this.querySelector('#btn-layer-colors');
if (layerButton) {
  layerButton.addEventListener('click', () => {
    this._usePackageColors = !this._usePackageColors;
    this._applyCurrentMaterialColor();
  });
}
```

3. **Apply colors** (method already exists):
```javascript
_applyCurrentMaterialColor() {
  if (this._activeObject3D) {
    this._activeObject3D.traverse((child) => {
      if (child.isMesh && child.material) {
        const packageColor = child.userData.packageColor;
        child.material.color.set(
          this._usePackageColors && packageColor 
            ? packageColor 
            : this._defaultModelColor
        );
      }
    });
  }
}
```

### Acceptance Criteria

- [x] Color data extracted from geometry response
- [ ] Grouped geometry rendered with correct colors
- [ ] Layers button toggles between colored and default
- [ ] Status message shown when colors available
- [ ] Multi-part models show per-part colors correctly
- [ ] Performance unaffected
- [ ] Works on STL and 3MF files

### Effort Estimate

- **Time**: 8-10 hours
- **Complexity**: Low-Medium
- **Risk**: Minimal (uses existing data structures)

---

## Feature 2: Keyboard Shortcuts (3-4 hours)

### Acceptance Criteria

- [ ] All keyboard shortcuts functional
- [ ] No conflicts with HA dashboard shortcuts
- [ ] Feedback visible to user (status bar update)
- [ ] Disabled when popup not focused
- [ ] Works on desktop browsers (Chrome, Firefox, Safari)

### Effort Estimate

- **Time**: 3-4 hours
- **Complexity**: Low
- **Risk**: Minimal (non-breaking enhancement)

---

## Implementation Sequence

### Week 1: Keyboard Shortcuts (3-4 hours)
1. Add keyboard event listener to `ModelDetail3DViewerTab`
2. Implement shortcut handler for R/G/V/L keys
3. Update status display with feedback
4. Test for HA dashboard conflicts

### Week 1-2: Colored Geometry (8-10 hours)
1. Parse grouped geometry from sidecar response
2. Create materials per color group
3. Wire 🌈 Layers button to toggle
4. Add status message for multi-color models
5. Test with multi-part 3MF files
6. Validate performance

---

## Files to Modify

- `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js`
  - Add keyboard event handler (~50 LOC)
  - Wire color toggle button (~30 LOC)
  - Material color application already exists

---

## Success Criteria

**Keyboard Shortcuts**
- ✅ R = Reset view
- ✅ G = Toggle grid
- ✅ V = Toggle build volume
- ✅ L = Toggle layers (colored geometry)
- ✅ Feedback visible in status bar

**Colored Geometry**
- ✅ Multi-part models show correct colors
- ✅ Toggle on/off works smoothly
- ✅ Status message when colors available
- ✅ No performance regression
- ✅ Mobile responsive

---

## References

- **Phase 3.2 Completion**: [PHASE-3.2-3.3-TASK-3-TASK-2-COMPLETE.md](../../repo/archive/root-history/PHASE-3.2-3.3-TASK-3-TASK-2-COMPLETE.md)
- **3D Viewer Implementation**: [Issue #1141](https://github.com/rsocko/hass-bambulab-config/issues/1141)
- **Three.js Documentation**: https://threejs.org/docs/
- **Color Metadata Source**: `extract_3mf_geometry()` in `sidecars/model_catalog/app/geometry_3mf.py`

---

## Revision History

| Date | Status | Notes |
|------|--------|-------|
| 2026-04-30 | Created | Simplified scope - keyboard shortcuts and colored geometry only |

