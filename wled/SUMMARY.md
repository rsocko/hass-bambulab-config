# WLED Design Refinement - Summary Document

## Overview

This document provides a high-level summary of the WLED design refinement completed to address segment limitations and optimize the controller allocation for the Bambu Lab printer LED system.

## 🆕 NEW: Preset-Based Segment Configuration

**Major Enhancement Added**: An advanced technique that leverages WLED's ability to save segment definitions in presets (not just colors) to work around the 16-segment-per-controller limitation.

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
- **[PRESET_BASED_SEGMENTS.md](PRESET_BASED_SEGMENTS.md)** - Complete conceptual guide
- **[docs/ha_automation_preset_based.md](docs/ha_automation_preset_based.md)** - Automation examples
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
**Document**: [CONTROLLER_ALLOCATION_RECOMMENDATION.md](CONTROLLER_ALLOCATION_RECOMMENDATION.md)

**Key Recommendations**:
- **Keep Interior Lid Light on MagWLED** (DigQuad at full capacity with 5 GPIO pins)
- No hardware changes needed
- Merge front door left and top segments on DigQuad
- Use DigQuad for 711 LEDs across 5 GPIO pins (all in use)
- Optimized segment allocation: 15 segments on DigQuad + 1 on MagWLED

**Segment Breakdown**:
- **DigQuad (15 segments, 1 spare)**:
  - Front Door: 2 segments (merged left+top)
  - AMS 1 Trays: 2 segments (combined top, combined bottom)
  - AMS 2 Trays: 2 segments (combined top, combined bottom)
  - AMS 1 Tags: 4 segments (individual tops for A1-A4)
  - AMS 2 Tags: 4 segments (individual tops for B1-B4)
  - Neutral Backgrounds: 1 segment (tag bottoms + hygrometers)
- **MagWLED (1 segment, 15 spare)**:
  - Interior Lid: 1 segment
- **Total: 16 active segments (15+1) ✅**

### 2. Preset Specification
**Document**: [PRESET_SPECIFICATION.md](PRESET_SPECIFICATION.md)

**Presets Defined**: 31+ presets covering:
- Power & connectivity states (3 presets)
- Print lifecycle states (16 presets including 8 active tray variations)
- Error & warning states (5 presets)
- AMS-specific scenarios (5 presets)
- Maintenance & utility states (2 presets)

**Active Tray Scenarios**:
Each of the 8 trays (A1, A2, A3, A4, B1, B2, B3, B4) has its own preset that highlights the active tag with the filament color while keeping other tags dim.

### 3. Phased Implementation Guide
**Document**: [PHASED_IMPLEMENTATION_GUIDE.md](PHASED_IMPLEMENTATION_GUIDE.md)

**7 Implementation Phases**:
1. **Phase 1**: Basic Lighting & Connectivity (2-4 hours)
2. **Phase 2**: Progress Bar & Status Indicators (3-5 hours)
3. **Phase 3**: AMS Basic Lighting (4-6 hours)
4. **Phase 4**: Individual Tag Control (5-8 hours)
5. **Phase 5**: Advanced Features & Error Handling (6-10 hours)
6. **Phase 6**: Fine-Tuning & Optimization (3-5 hours)
7. **Phase 7**: Documentation & Maintenance (2-3 hours)

**Total Time**: 25-45 hours for complete implementation

### 4. Updated Segment Configuration
**Document**: [digquad-settings/wled_segments_Digquad_UPDATED.json](digquad-settings/wled_segments_Digquad_UPDATED.json)

Updated segment definitions reflect:
- Merged front door segments (left+top combined)
- Combined AMS tray top and bottom segments
- Individual tag top segments for all 8 trays
- Neutral background segment combining tag bottoms and hygrometers
- Actual LED counts from physical installation (711 total)

## Segment Limitations & Trade-offs

### What We CAN Do ✅

- ✅ **Individual tag highlighting**: Each of 8 tray tags gets individual control
- ✅ **Progress bar**: Independent progress indication on front door
- ✅ **Status indication**: Merged left+top for consistent status display
- ✅ **Basic AMS lighting**: Combined top/bottom lighting per AMS unit
- ✅ **Neutral backgrounds**: Tag bottoms and hygrometers have soft white light
- ✅ **All 31+ presets**: Complete scenario coverage

### What We CANNOT Do ❌

- ❌ **Per-tray AMS lid lighting**: Cannot individually control lighting above each of the 4 trays
- ❌ **Individual tag bottom control**: All tag bottoms share one segment (neutral color)
- ❌ **Separate hygrometer control**: Hygrometers share segment with tag bottoms
- ❌ **AMS tray bottom individual control**: All bottom lighting is combined per AMS

### Blocked Scenarios & Workarounds

#### Blocked: Individual AMS Tray Top Animation
**Workaround**: Use tag top to indicate which tray is loading (tag can flash/pulse)

#### Blocked: Per-Tray Filament Remaining on Tag Bottom
**Workaround**: Use tag top brightness/intensity to indicate level (100% = full, 25% = low)

#### Degraded: Humidity Warning on Specific AMS
**Workaround**: Use AMS tray top (segment 3 or 5) to pulse red to indicate which AMS has humidity issue

#### Degraded: Desiccant Age Warning per Tray
**Workaround**: Flash or pulse tag top orange to indicate desiccant warning

## Key Changes from Previous Configuration

### Hardware Changes
1. **NO Hardware Changes** - DigQuad already at full capacity (5 GPIO pins)
   - Interior Lid Light REMAINS on MagWLED GPIO 2
   - DigQuad has all 5 GPIO pins in use
   - Configuration respects physical hardware constraints

### Segment Changes
1. **Merged Front Door Left+Top** into single segment on DigQuad
   - Reduces from 3 segments to 2 segments on front door
   - Both areas show same status (consistent display)
   - Frees 1 segment for other uses

2. **Combined AMS Tray Lighting** on DigQuad
   - Top LEDs combined per AMS (2 segments total)
   - Bottom LEDs combined per AMS (2 segments total)
   - Cannot animate individual tray loading, but can use tags

3. **Individual Tag Tops** on DigQuad
   - All 8 tags get individual segments (DigQuad segments 6-13)
   - Allows highlighting active tray with filament color
   - Maintains primary functionality

4. **Neutral Background Segment** on DigQuad
   - Combines all tag bottoms and hygrometers (DigQuad segment 14)
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
   - Most presets affect DigQuad segments (0-14)
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
1. `CONTROLLER_ALLOCATION_RECOMMENDATION.md` - Controller allocation strategy and segment analysis
2. `PRESET_SPECIFICATION.md` - Complete preset definitions with 31+ presets
3. `PHASED_IMPLEMENTATION_GUIDE.md` - 7-phase implementation plan
4. `SUMMARY.md` - This document (high-level overview)

### Updated Configuration Files
1. `digquad-settings/wled_segments_Digquad_UPDATED.json` - Updated segment definitions
2. `README.md` - Added reference to new specifications
3. `INDEX.md` - Updated with new specification files

### Existing Documents (Referenced)
1. `digquad-led-segments.md` - Exact LED counts and ranges
2. `led-functions.md` - LED zone functions
3. `light-scenarios.md` - 33+ lighting scenarios
4. `QUICK_START.md` - Setup guide

## Benefits of This Approach

### Technical Benefits
- ✅ Respects DigQuad's 5 GPIO pin limit (no hardware changes)
- ✅ Stays within 16-segment limit per controller (15 on DigQuad, 1 on MagWLED)
- ✅ Maintains excellent functionality
- ✅ Individual control of all 8 tray tags
- ✅ Progress bar and status indication
- ✅ Simplified wiring (each controller manages its own strips)
- ✅ MagWLED has 15 segments available for future expansion
- ✅ Individual control of all 8 tray tags
- ✅ Progress bar and status indication
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
3. Cannot independently control both hygrometers
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
3. Dynamic segment reconfiguration (complex, not recommended)

## Validation & Testing

### Pre-Implementation Validation
- ✅ Segment count verified (16 segments)
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
1. Refer to troubleshooting sections in PHASED_IMPLEMENTATION_GUIDE.md
2. Check segment allocation in CONTROLLER_ALLOCATION_RECOMMENDATION.md
3. Review preset definitions in PRESET_SPECIFICATION.md
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
- [CONTROLLER_ALLOCATION_RECOMMENDATION.md](CONTROLLER_ALLOCATION_RECOMMENDATION.md)
- [PRESET_SPECIFICATION.md](PRESET_SPECIFICATION.md)
- [PHASED_IMPLEMENTATION_GUIDE.md](PHASED_IMPLEMENTATION_GUIDE.md)
- [digquad-settings/wled_segments_Digquad_UPDATED.json](digquad-settings/wled_segments_Digquad_UPDATED.json)
