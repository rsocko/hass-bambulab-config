# WLED Design Refinement - Summary Document

> **Updated 2026-03-13** — Reflects the deployed Home Assistant State Machine approach.

## Current Status

The WLED system is controlled by a **Home Assistant state machine** that is live and running:

- **Phase 1 (Core State Machine)**: ✅ Complete — 9 core states (S0–S8), presets 101–109 on DigQuad, HA package with orchestrator + scripts + helpers
- **Phase 2 (Segment Expansion)**: Not started — deploy full 15-segment layout and expand presets
- **Phase 3 (Overlays & Advanced)**: Not started — active tray highlighting, telemetry overlays

See [ha-state-machine-package.md](ha-state-machine-package.md) for the authoritative state diagram and entity mapping. See [phased-implementation-guide.md](phased-implementation-guide.md) for the 3-phase plan.

---

## Overview

This document provides a high-level summary of the WLED design refinement completed to address segment limitations and optimize the controller allocation for the Bambu Lab printer LED system.

## Preset-Based Segment Configuration (Future — Phase 3)

> **Note**: This technique is a valid future enhancement for Phase 3. It has not been deployed yet. The current system uses the state machine with presets 101–109.

**Advanced Technique**: Leverages WLED's ability to save segment definitions in presets (not just colors) to work around the 16-segment-per-controller limitation.

### What This Enables
✅ **Full Tag Highlighting**: Control BOTH top AND bottom of active tag with filament color  
✅ **Dynamic Layouts**: Switch between different 16-segment configurations on the fly  
✅ **No Hardware Changes**: Pure software solution via preset switching  
✅ **Context-Aware**: Automatically adapt segment layout based on active tray

### Implementation
- **Presets 50-57**: Each saves a different segment layout optimized for a specific active tray
- **Home Assistant**: Automation switches presets when active tray changes
- **Segments 6-7**: Always contain active tag top and bottom in these special presets
- **~500ms delay**: Time needed for WLED to reconfigure segments between presets

### Documentation
- **[preset-based-segments.md](preset-based-segments.md)** - Complete conceptual guide
- **[ha-automation-preset-based.md](ha-automation-preset-based.md)** - Automation examples
- **Example JSONs** in `digquad-settings/wled_preset_*_full_highlight.json`

---

## Problem Statement Addressed

The original problem statement requested:

1. ✅ **Controller allocation advice** - Which controller (MagWLED vs DigQuad) should control each LED strip
2. ✅ **Merge front door segments** - Combine left and top segments to free up a segment
3. ✅ **Preset specification** - Document all presets with scenarios for different active trays
4. ✅ **Segment limitation analysis** - Identify blocked scenarios and alternatives
5. ✅ **Neutral segments** - Define segments for unused areas with soft white
6. ✅ **Phased implementation** - Create a phased approach for testing and validation

## Key Deliverables

### 1. Controller Allocation Recommendation
**Document**: [controller-allocation.md](controller-allocation.md)

**Key Recommendations**:
- **Keep Interior Lid Light on MagWLED** (DigQuad at full capacity with 5 GPIO pins)
- No hardware changes needed
- Split front door into 3 independent segments (bottom, left, top) on DigQuad
- Use DigQuad for 711 LEDs across 5 GPIO pins (all in use)
- Optimized segment allocation: 16 segments on DigQuad + 1 on MagWLED

**Segment Breakdown**:
- **DigQuad (16 segments, 0 spare — WLED maximum)**:
  - Front Door: 3 segments (bottom=print progress, left=layer progress, top=status)
  - AMS 1 Trays: 2 segments (combined top, combined bottom)
  - AMS 2 Trays: 2 segments (combined top, combined bottom)
  - AMS 1 Tags: 4 segments (individual tops for A1-A4)
  - AMS 2 Tags: 4 segments (individual tops for B1-B4)
  - Neutral Backgrounds: 1 segment (tag bottoms + hygrometers)
- **MagWLED (1 segment, 15 spare)**:
  - Interior Lid: 1 segment
- **Total: 17 active segments (16+1) ✅**

### 2. Preset Specification
**Document**: [preset-specification.md](preset-specification.md)

**Presets Defined**: 31+ presets covering:
- Power & connectivity states (3 presets)
- Print lifecycle states (16 presets including 8 active tray variations)
- Error & warning states (5 presets)
- AMS-specific scenarios (5 presets)
- Maintenance & utility states (2 presets)

**Active Tray Scenarios**:
Each of the 8 trays (A1, A2, A3, A4, B1, B2, B3, B4) has its own preset that highlights the active tag with the filament color while keeping other tags dim.

### 3. Phased Implementation Guide
**Document**: [phased-implementation-guide.md](phased-implementation-guide.md)

**3 Implementation Phases** (aligned to the state machine approach):
1. **Phase 1**: Core State Machine (✅ Complete) — HA package, presets 101–109
2. **Phase 2**: Segment Expansion — deploy 15 segments, expand presets
3. **Phase 3**: Overlays & Advanced — active tray highlighting, telemetry overlays

### 4. Updated Segment Configuration
**Document**: [digquad-settings/wled_segments_Digquad_UPDATED.json](../../../wled/digquad-settings/wled_segments_Digquad_UPDATED.json)

Updated segment definitions reflect:
- 3 independent front door segments (bottom=progress, left=layers, top=status)
- Combined AMS tray top and bottom segments
- Individual tag top segments for all 8 trays
- Neutral background segment combining tag bottoms and hygrometers
- Actual LED counts from physical installation (711 total)

## Segment Limitations & Trade-offs

### Summary Policy (To Avoid Duplicate Telemetry)

- Desiccant-age and filament-remaining visuals are `idle-only` telemetry scenes.
- During prep/printing/error states, tray risk and active-print status must be shown on tag tops and door/status segments, not duplicated on tag-bottom telemetry scenes.
- Detailed behavior and state transitions remain defined in `light-scenarios.md`.

### What We CAN Do ✅

- ✅ **Individual tag highlighting**: Each of 8 tray tags gets individual control
- ✅ **Print progress bar**: Independent print percentage on front door bottom
- ✅ **Layer progress**: Independent layer progress on front door left
- ✅ **Status indication**: Independent status indicator on front door top
- ✅ **Basic AMS lighting**: Combined top/bottom lighting per AMS unit
- ✅ **Neutral backgrounds**: Tag bottoms and hygrometers have soft white light
- ✅ **All 31+ presets**: Complete scenario coverage

### What Static Fixed Layout Cannot Do Concurrently ❌

- ❌ **Per-tray AMS lid lighting for all trays simultaneously**
- ❌ **Individual tag bottom control for all trays simultaneously**
- ❌ **Independent hygrometer alerts while preserving all other tray-level details**
- ❌ **Full concurrent tray-detail fidelity in one static 16-segment map**

### Degraded Scenarios in Fixed Layout and Dynamic Workarounds

#### Degraded: Individual AMS Tray Top Animation
**Workaround**: Use dynamic segment/preset remap during active tray loading windows

#### Degraded: Per-Tray Filament Remaining on Tag Bottom
**Workaround**: Keep as idle-only telemetry; during active print use tag-top risk thresholds for used trays

#### Degraded: Humidity Warning on Specific AMS
**Workaround**: Use AMS tray top (segment 3 or 5) to pulse red to indicate which AMS has humidity issue

#### Degraded: Desiccant Age Warning per Tray
**Workaround**: Keep as idle-rotation telemetry; use temporary alert overlays only when escalation is needed

## Key Changes from Previous Configuration

### Hardware Changes
1. **NO Hardware Changes** - DigQuad already at full capacity (5 GPIO pins)
   - Interior Lid Light REMAINS on MagWLED GPIO 2
   - DigQuad has all 5 GPIO pins in use
   - Configuration respects physical hardware constraints

### Segment Changes
1. **Split Front Door into 3 independent segments** on DigQuad
   - Bottom (Seg 0): Print progress bar (50 LEDs)
   - Left (Seg 1): Layer progress (65 LEDs)
   - Top (Seg 2): Status indicator (43 LEDs)
   - Enables independent control of progress, layers, and status

2. **Combined AMS Tray Lighting** on DigQuad
   - Top LEDs combined per AMS (2 segments total)
   - Bottom LEDs combined per AMS (2 segments total)
   - Cannot animate individual tray loading, but can use tags

3. **Individual Tag Tops** on DigQuad
   - All 8 tags get individual segments (DigQuad segments 7-14)
   - Allows highlighting active tray with filament color
   - Maintains primary functionality

4. **Neutral Background Segment** on DigQuad
   - Combines all tag bottoms and hygrometers (DigQuad segment 15)
   - Set to soft white (#FFDCB4) at 25-30% brightness
   - Provides ambient lighting without drawing attention

5. **Interior Lid on MagWLED**
   - Simple on/off control (MagWLED segment 0)
   - Frees 15 segments on MagWLED for future expansion
   - Requires coordination with DigQuad in presets

### Preset Changes
1. **8 Active Tray Presets** (Presets 8-15)
   - One preset per active tray (A1, A2, A3, A4, B1, B2, B3, B4)
   - Each highlights the appropriate tag with filament color on DigQuad
   - MagWLED Interior Lid coordinated with DigQuad presets
   - Automation switches presets based on active tray sensor

2. **Dynamic Color Integration**
   - Tag colors pulled from Spoolman integration
   - Filament color matches actual spool
   - Requires Home Assistant automation to sync colors to DigQuad

3. **Two-Controller Coordination**
   - Home Assistant must control both DigQuad and MagWLED
   - Most presets affect DigQuad segments (0-15)
   - MagWLED segment 0 (Interior Lid) controlled separately
   - Service calls needed for both `light.digquad` and `light.magwled`

## Implementation Strategy

### Recommended Approach
**Timeline**: 4 weekends

- **Weekend 1**: Phases 1-2 (Basic lighting + Progress bar)
- **Weekend 2**: Phase 3 (AMS lighting)
- **Weekend 3**: Phase 4 (Individual tag control)
- **Weekend 4**: Phases 5-7 (Advanced features + Polish + Documentation)

### Minimum Viable Product (MVP)
**Timeline**: 2 weekends (Phases 1-3)

Provides:
- Basic lighting
- Progress bar
- Status indicators
- AMS lighting
- No individual tag control yet

### Critical Success Factors
1. ✅ Test incrementally (one phase at a time)
2. ✅ Validate each phase before moving to next
3. ✅ Create backups before major changes
4. ✅ Document any deviations from plan
5. ✅ Test with actual print jobs

## Files Created/Updated

### New Specification Documents
1. `controller-allocation.md` - Controller allocation strategy and segment analysis
2. `preset-specification.md` - Complete preset definitions with 31+ presets
3. `phased-implementation-guide.md` - 7-phase implementation plan
4. `summary.md` - This document (high-level overview)

### Updated Configuration Files
1. `digquad-settings/wled_segments_Digquad_UPDATED.json` - Updated segment definitions
2. `README.md` - Added reference to new specifications
3. `INDEX.md` - Updated with new specification files

### Existing Documents (Referenced)
1. `digquad-led-segments.md` - Exact LED counts and ranges
2. `light-scenarios.md` (Section 2: LED Function Map) - LED zone functions
3. `light-scenarios.md` - 33+ lighting scenarios
4. `quick-start.md` - Setup guide

## Benefits of This Approach

### Technical Benefits
- ✅ Respects DigQuad's 5 GPIO pin limit (no hardware changes)
- ✅ Stays within 16-segment limit per controller (16 on DigQuad, 1 on MagWLED)
- ✅ Maintains excellent functionality
- ✅ Individual control of all 8 tray tags
- ✅ Print progress bar, layer progress, and status indication
- ✅ Simplified wiring (each controller manages its own strips)
- ✅ MagWLED has 15 segments available for future expansion
- ✅ Individual control of all 8 tray tags
- ✅ Print progress bar, layer progress, and status indication
- ✅ Simplified wiring (single controller)
- ✅ Room for future expansion (MagWLED available)

### Implementation Benefits
- ✅ Phased approach allows incremental testing
- ✅ Early MVP delivery (Phases 1-3)
- ✅ Clear validation checkpoints
- ✅ Documented rollback procedures
- ✅ Comprehensive testing checklist

### Maintenance Benefits
- ✅ Well-documented configuration
- ✅ Clear preset specifications
- ✅ Easy troubleshooting guides
- ✅ Backup and recovery procedures

## Limitations & Considerations

### Known Limitations
1. Cannot individually animate AMS tray tops during loading
2. Cannot show per-tag filament remaining on tag bottoms
3. Full concurrent tray-level detail cannot fit in one static 16-segment layout
4. Tag bottom LEDs all show same color (neutral)

### Acceptable Trade-offs
These limitations are acceptable because:
- Tag tops can indicate active tray (primary functionality preserved)
- Workarounds exist for all blocked scenarios
- Most important features are maintained
- System is simpler and more maintainable

### Future Enhancements
If segment limitations become too restrictive:
1. Use MagWLED for AMS 2 tags (8 segments for full top+bottom control)
2. Eliminate AMS bottom lighting entirely (frees 2 segments)
3. Dynamic segment reconfiguration with guardrails (recommended for advanced scenarios)

## Validation & Testing

### Pre-Implementation Validation
- ✅ Segment count verified (16 on DigQuad + 1 on MagWLED = 17 segments)
- ✅ LED count verified (711 LEDs)
- ✅ All scenarios mapped to presets
- ✅ Workarounds documented for blocked scenarios

### Implementation Validation
Each phase includes:
- Clear success criteria
- Validation checkpoints
- Testing procedures
- Rollback instructions

### Post-Implementation Validation
Final testing includes:
- All 31+ presets
- Active tray scenarios (8 variations)
- Error states
- Loading/unloading animations
- Manual overrides
- Home Assistant integration

## Next Steps

### For Implementation
1. **Review** all three specification documents
2. **Approve** the controller allocation strategy
3. **Begin Phase 1** implementation (Basic Lighting)
4. **Follow** the phased implementation guide
5. **Validate** each phase before proceeding
6. **Document** any deviations or issues

### For Questions or Issues
1. Refer to troubleshooting sections in phased-implementation-guide.md
2. Check segment allocation in controller-allocation.md
3. Review preset definitions in preset-specification.md
4. Consult existing documentation (README.md, INDEX.md)

## Conclusion

This WLED design refinement provides a comprehensive solution to the segment limitation challenge. By strategically merging segments, moving the lid light, and using neutral backgrounds, we can stay within the 16-segment limit while maintaining excellent functionality.

The phased implementation approach ensures that you can:
- Build incrementally with validation at each step
- Achieve an MVP quickly (Phases 1-3)
- Add advanced features progressively (Phases 4-5)
- Polish and document thoroughly (Phases 6-7)

All key functionality is preserved:
- ✅ Progress bar
- ✅ Status indication
- ✅ Individual tag highlighting for all 8 trays
- ✅ Basic AMS lighting
- ✅ Error states
- ✅ Loading/unloading animations

The documented workarounds for blocked scenarios ensure that the system remains functional and useful despite the segment limitations.

---

**Document Version**: 1.0  
**Date**: 2024  
**Total LEDs**: 711  
**Total Segments**: 16  
**Total Presets**: 31+  
**Implementation Phases**: 7  
**Estimated Implementation Time**: 25-45 hours  

**Key Documents**:
- [controller-allocation.md](controller-allocation.md)
- [preset-specification.md](preset-specification.md)
- [phased-implementation-guide.md](phased-implementation-guide.md)
- [digquad-settings/wled_segments_Digquad_UPDATED.json](../../../wled/digquad-settings/wled_segments_Digquad_UPDATED.json)
