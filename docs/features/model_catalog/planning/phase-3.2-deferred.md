# Phase 3.3: Keyboard Shortcuts & Colored Geometry

**Status**: Phase 3.3 implementation tasks  
**Date**: 2026-04-30  
**Related Issue**: [#1141 - Phase 4: 3D Viewer with Three.js](https://github.com/rsocko/hass-bambulab-config/issues/1141)  
**Status**: ✅ Complete (Phase 3.2) + 📋 Planned (Phase 3.3)

---

## Phase 3.2 Status: COMPLETE & PRODUCTION-READY

### Core Features Delivered ✅

All **4 core features** are implemented, tested, and ready for deployment:

| Feature | Status | Tests | Notes |
|---------|--------|-------|-------|
| Interactive OrbitControls | ✅ Complete | 18/18 | Rotate, zoom, pan with mouse & touch |
| 3MF File Format Support | ✅ Complete | 34/34 | Multi-part rendering, color metadata |
| Build Volume Visualization | ✅ Complete | 18/18 | Bambu P1S 256×256×256mm reference |
| Viewer State Persistence | ✅ Complete | 18/18 | SessionStorage for file, grid, volume |

**Total Test Pass Rate**: 125+/126 (99.2%)

---

## Phase 3.3 Enhancements: Keyboard Shortcuts & Colored Geometry

### Feature 1: Keyboard Shortcuts (3-4 hours)

Add keyboard control for common viewer operations:

| Key | Action | Uses Existing Method |
|-----|--------|----------------------|
| `R` | Reset view | `_resetView()` ✅ |
| `G` | Toggle grid | `_toggleGrid()` ✅ |
| `V` | Toggle build volume | `_toggleBuildVolume()` ✅ |
| `L` | Toggle colored geometry | `_toggleColorMode()` (NEW) |

**Acceptance Criteria**
- ✅ All 4 shortcuts functional
- ✅ Status feedback in status bar
- ✅ Works when popup focused
- ✅ No HA dashboard conflicts

---

### Feature 2: Colored Geometry (8-10 hours)

Display multi-part models with per-extruder colors from 3MF metadata.

**Current State**
- ✅ Color data extracted by `extract_3mf_geometry()` in sidecar
- ✅ Grouped geometry available in API response
- ✅ UI button (🌈 Layers) exists but shows "not implemented yet"

**Implementation Tasks**
1. Verify grouped geometry with colors in API response
2. Create materials per color group in `_loadGeometry()`
3. Wire 🌈 Layers button to toggle color mode
4. Add status message when colors available

**Acceptance Criteria**
- ✅ Multi-part models show per-part colors
- ✅ Toggle on/off works smoothly  
- ✅ Status message shows availability
- ✅ No performance regression
- ✅ Works with STL and 3MF files

---

## Files to Modify

- `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js`
  - Add keyboard event handler (~30-50 LOC)
  - Add `_toggleColorMode()` method (~15-20 LOC)
  - Update `_loadGeometry()` to use color groups
  - Verify material creation for grouped geometry

---

## Implementation Timeline

**Week 1**: Keyboard Shortcuts (3-4h)
- [ ] Add keyboard event listener
- [ ] Implement R/G/V/L handlers
- [ ] Manual testing

**Week 2**: Colored Geometry (8-10h)
- [ ] Verify grouped geometry in API response
- [ ] Create per-group materials
- [ ] Wire layer toggle button
- [ ] Test with multi-color 3MF files

**Total Phase 3.3**: 11-14 hours

---

## Design Documents

| Document | Content |
|----------|---------|
| [phase-3.2-optional-enhancements.md](/docs/features/model_catalog/planning/phase-3.2-enhancements.md) | Detailed feature specs |
| [phase-3.3-3d-viewer-enhancements.md](/docs/features/model_catalog/design/phase-3.3-viewer.md) | Implementation details |
| [Phase 3.3 Implementation Guide](/docs/features/model_catalog/planning/phase-3.3-impl-guide.md) | Archive linking + more |

---

## Success Criteria

**Phase 3.3 Complete When**:
- ✅ All 4 keyboard shortcuts functional and tested
- ✅ Colored geometry renders correctly for multi-extruder models
- ✅ Toggle on/off works smoothly
- ✅ Status messages show availability
- ✅ No performance regression (<500ms load)
- ✅ Manual testing on Chrome, Firefox, Safari

---

## Key Decisions

✅ **Scope**: Only keyboard shortcuts + colored geometry  
✅ **No**: E2E tests, export to STL, measurement tool, layer slicing  
✅ **Timeline**: Phase 3.3 (11-14 hours alongside archive linking)  
✅ **Implementation**: Minimal complexity, uses existing structures

---

## References

- **Implementation Guide**: [phase-3.3-3d-viewer-enhancements.md](/docs/features/model_catalog/design/phase-3.3-viewer.md)
- **Feature Specs**: [phase-3.2-optional-enhancements.md](/docs/features/model_catalog/planning/phase-3.2-enhancements.md)
- **Related Issue**: [#1141](https://github.com/rsocko/hass-bambulab-config/issues/1141)
- **Phase 3.3 Overview**: [phase-3.3-implementation-guide.md](/docs/features/model_catalog/planning/phase-3.3-impl-guide.md)

