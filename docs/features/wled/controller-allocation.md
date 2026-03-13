# Controller Allocation Recommendation

## Executive Summary

This document provides recommendations for allocating LED strips between the **MagWLED** (single LED strip controller) and **DigQuad** (5 LED strip controller) to optimize the 16-segment limitation per controller.

### Key Recommendations

1. **Keep Lid LED (Interior Light) on MagWLED** - DigQuad is at full capacity (5 strips maximum) and cannot accept additional LED strips
2. **Split Front Door into 3 independent segments** - Bottom (print progress), Left (layer progress), Top (status indicator)
3. **Use simplified segment layouts** for AMS components to stay within 16-segment limit
4. **Create neutral segments** for unused areas (bottoms of tags/AMS lids) set to soft white

## Current Configuration Analysis

### Current MagWLED Allocation (1 strip controller)
- **Strip 1**: Interior Lid Light (GPIO 2)
  - Segment 0: Interior Light (~30 LEDs) - simple single segment
  - **Total: 1 segment used, 15 segments available**

### Current DigQuad Allocation (5 strips - AT MAXIMUM CAPACITY)
According to `digquad-led-segments.md`, the actual physical installation uses:
- **GPIO 15**: Printer Front Door - 158 LEDs
- **GPIO 1**: AMS 1 Lid/Spools - 140 LEDs  
- **GPIO 3**: AMS 2 Lid/Spools - 139 LEDs
- **GPIO 16**: AMS 1 Tags + Hygrometer - 136 LEDs
- **GPIO 4**: AMS 2 Tags + Hygrometer - 138 LEDs
- **Total: 711 LEDs across 5 GPIO pins (MAXIMUM CAPACITY)**

**⚠️ CRITICAL CONSTRAINT**: DigQuad has 5 GPIO outputs and all are currently in use. No additional LED strips can be connected to DigQuad.

## Segment Counting Analysis

### Scenario-Based Segment Requirements

To understand segment needs, we must consider what segments are needed for different scenarios:

#### Minimum Segments Needed (Basic Functionality)
1. **Front Door Bottom** (print progress bar): 1 segment  
2. **Front Door Left** (layer progress): 1 segment
3. **Front Door Top** (status indicator): 1 segment
4. **AMS 1 - Tray Top (combined)**: 1 segment OR per-tray: 4 segments
4. **AMS 1 - Tray Bottom (combined)**: 1 segment
5. **AMS 1 - Tag Tops (4 trays)**: 4 segments
6. **AMS 1 - Tag Bottoms (combined)**: 1 segment
7. **AMS 1 - Hygrometer**: 1 segment
8. **AMS 2 - Tray Top (combined)**: 1 segment OR per-tray: 4 segments
9. **AMS 2 - Tray Bottom (combined)**: 1 segment
10. **AMS 2 - Tag Tops (4 trays)**: 4 segments
11. **AMS 2 - Tag Bottoms (combined)**: 1 segment
12. **AMS 2 - Hygrometer**: 1 segment

**Minimum Total on DigQuad: 16 segments** (with combined AMS tray lighting — uses WLED maximum)
**Plus MagWLED: 1 segment** (Interior Lid Light)
**Grand Total: 17 segments across both controllers**

**Maximum with per-tray AMS lighting: 22 segments** (exceeds 16-segment limit per controller!)

### The Segment Limitation Challenge

With a 16-segment limit per controller, we cannot have:
- Individual control of all 4 AMS tray top lighting zones (8 segments for both AMS units)
- Individual control of all 8 tag tops (8 segments)
- Individual control of tag bottoms
- Individual control of AMS tray bottoms
- Individual hygrometer control

## Recommended Controller Allocation

### Recommended MagWLED Configuration (1 strip)
**Current Usage**: Interior Lid Light (~30 LEDs)

- **Strip 1**: Interior Lid Light (GPIO 2)
  - **Segment 0**: Interior Light - Simple on/off lighting
  - **Total: 1 segment used, 15 segments available**

**Rationale**: 
- MagWLED must continue to control at least one LED strip since DigQuad is at full capacity
- Interior Lid Light is simple (1 segment only) and doesn't need complex segmentation
- Keeps MagWLED available for future expansion or additional features
- **This is the ONLY viable configuration** given DigQuad's capacity constraint

### Recommended DigQuad Configuration (5 strips - AT MAXIMUM CAPACITY)

**GPIO Pin Allocation** (matches current physical installation):

#### GPIO 15: Printer Front Door (158 LEDs)
- **Segment 0**: Bottom (Print Progress Bar) - LEDs 0-49 (50 LEDs)
- **Segment 1**: Left (Layer Progress) - LEDs 50-115 (65 LEDs)
- **Segment 2**: Top (Status Indicator) - LEDs 116-157 (43 LEDs)
- **Total: 3 segments**

#### GPIO 1: AMS 1 Lid/Spools (140 LEDs)  
- **Segment 3**: Tray Top (all spools combined) - LEDs 158-215 (58 LEDs)
- **Segment 4**: Tray Bottom (all spools combined, neutral) - LEDs 241-297 (57 LEDs)
- **Total: 2 segments**

#### GPIO 3: AMS 2 Lid/Spools (139 LEDs)
- **Segment 5**: Tray Top (all spools combined) - LEDs 298-357 (60 LEDs)  
- **Segment 6**: Tray Bottom (all spools combined, neutral) - LEDs 382-436 (55 LEDs)
- **Total: 2 segments**

#### GPIO 16: AMS 1 Tags + Hygrometer (136 LEDs)
- **Segment 7**: Tag A1 Top - LEDs 442-453 (12 LEDs)
- **Segment 8**: Tag A2 Top - LEDs 454-465 (12 LEDs)
- **Segment 9**: Tag A3 Top - LEDs 466-477 (12 LEDs)
- **Segment 10**: Tag A4 Top - LEDs 490-501 (12 LEDs)
- **Total: 4 segments**

#### GPIO 4: AMS 2 Tags + Hygrometer (138 LEDs)
- **Segment 11**: Tag B1 Top - LEDs 579-591 (13 LEDs)
- **Segment 12**: Tag B2 Top - LEDs 592-605 (14 LEDs)  
- **Segment 13**: Tag B3 Top - LEDs 606-619 (14 LEDs)
- **Segment 14**: Tag B4 Top - LEDs 632-643 (12 LEDs)
- **Total: 4 segments**

#### Combined Neutral Backgrounds (spans GPIO 16 + GPIO 4)
- **Segment 15**: Hygrometers + Tag Bottoms (neutral) - Various LEDs (~125 LEDs combined)

**Current Count: 16 segments** (0-15) — **uses WLED maximum, 0 spare**

## Solution: Combine Neutral Backgrounds Strategically

Since we have exactly 16 segments available on DigQuad, we need to combine background segments efficiently.

### Final Recommended Configuration

#### DigQuad - Segment Allocation (16 segments used, 0 spare — WLED maximum)

0. **Segment 0**: Front Door Bottom (Print Progress Bar) - 1 segment
1. **Segment 1**: Front Door Left (Layer Progress) - 1 segment
2. **Segment 2**: Front Door Top (Status Indicator) - 1 segment
3. **Segment 3**: AMS 1 Tray Top (all spools) - 1 segment
4. **Segment 4**: AMS 1 Tray Bottom (neutral) - 1 segment
5. **Segment 5**: AMS 2 Tray Top (all spools) - 1 segment
6. **Segment 6**: AMS 2 Tray Bottom (neutral) - 1 segment
7. **Segment 7**: AMS 1 Tag A1 Top - 1 segment
8. **Segment 8**: AMS 1 Tag A2 Top - 1 segment
9. **Segment 9**: AMS 1 Tag A3 Top - 1 segment
10. **Segment 10**: AMS 1 Tag A4 Top - 1 segment
11. **Segment 11**: AMS 2 Tag B1 Top - 1 segment
12. **Segment 12**: AMS 2 Tag B2 Top - 1 segment
13. **Segment 13**: AMS 2 Tag B3 Top - 1 segment
14. **Segment 14**: AMS 2 Tag B4 Top - 1 segment
15. **Segment 15**: Hygrometers + Tag Bottoms (neutral, combined) - 1 segment

**Total: 16 segments on DigQuad, 0 spare (WLED maximum) ✅**

#### MagWLED - Segment Allocation (1 segment used, 15 spare)

0. **Segment 0**: Interior Lid Light - 1 segment (simple on/off)

**Total: 1 segment on MagWLED, 15 segments available for future expansion! ✅**

#### Grand Total System
- **DigQuad**: 16 segments used, 0 spare (WLED maximum)
- **MagWLED**: 1 segment used, 15 spare
- **Total Segments**: 17 active segments across both controllers
- **Total LEDs**: 711 LEDs on DigQuad + ~30 on MagWLED = ~741 LEDs

## Segment Limitations and Trade-offs

### What We CAN Do with This Configuration

✅ **Full tag highlighting**: Each of 8 tray tags gets individual control  
✅ **Print progress bar**: Independent print percentage on front door bottom  
✅ **Layer progress**: Independent layer progress on front door left  
✅ **Status indication**: Independent status indicator on front door top  
✅ **Basic AMS lighting**: Combined top/bottom lighting per AMS unit  
✅ **Neutral backgrounds**: Tag bottoms and hygrometers have soft white light  

### What Fixed Layout Cannot Do Simultaneously

In the fixed 16-segment DigQuad layout, the following are limited:

❌ **Per-tray AMS lid lighting** for all trays at once  
❌ **Individual tag bottom control** for all trays at once  
❌ **Independent hygrometer control** while also keeping detailed tag-bottom telemetry  
❌ **All detailed tray-level effects concurrently** (AMS tops + tag tops + tag bottoms + hygrometers)  

### Scenarios Degraded in Fixed Layout

Summary policy: keep `desiccant age` and `filament remaining` as idle telemetry scenes to avoid duplicate signaling during active print states.

The following scenarios are degraded in fixed layout and improved by hybrid dynamic strategy:

#### DEGRADED: Individual AMS Tray Top Animation
**Scenario**: Animate loading/unloading for a specific tray with LED chase on tray top  
**Why Degraded**: AMS tray tops are combined into single segment per AMS in fixed map  
**Hybrid Improvement**: Use preset-based or dynamic segment remap for active tray window

#### DEGRADED: Per-Tray Filament Remaining Display  
**Scenario**: Show filament remaining as a percentage on tag bottom LEDs  
**Why Degraded**: Tag bottoms are combined into one neutral segment in fixed map  
**Hybrid Improvement**: Keep filament-remaining detail in idle rotation; during prep/printing, render tray shortage risk on tag tops

#### DEGRADED: Humidity Warning on Specific AMS (Fixed Layout)
**Scenario**: Flash red on hygrometer for AMS with high humidity  
**Why Degraded**: Both hygrometers may share a combined segment in fixed map  
**Hybrid Improvement**: Allocate one temporary per-AMS hygrometer alert segment during humidity events

#### DEGRADED: Desiccant Age Warning per Tray (Fixed Layout)
**Scenario**: Show orange on tag bottom for old desiccant  
**Why Degraded**: Tag bottoms are combined in fixed map  
**Hybrid Improvement**: Keep desiccant detail in idle rotation; use temporary overlays only for escalated alerts

### Alternative Approaches

#### Alternative 1: Dynamic Segment Reconfiguration
**Approach**: Use presets that reconfigure segment definitions for specific scenarios  
**Pros**: Can achieve more granular control when needed  
**Cons**: Complex to implement, may cause delays during reconfiguration, risks losing state  
**Recommendation**: ✅ Recommended as primary advanced strategy when bounded by guardrails

#### Alternative 2: Eliminate AMS Bottom Lighting
**Approach**: Remove AMS tray bottom segments entirely (no lighting on bottom of AMS lids)  
**Pros**: Frees 2 segments for other uses  
**Cons**: Reduces overall lighting quality, less illumination of spools  
**Segments Freed**: 2 segments  
**New Possibilities**: Could add per-hygrometer control OR split some tag bottoms  
**Recommendation**: ⚠️ Consider if bottom lighting is not valued

#### Alternative 3: Eliminate Tag Bottom Lighting  
**Approach**: Remove tag bottom segments entirely  
**Pros**: Frees 1 segment  
**Cons**: Lose ability to show filament level, desiccant warnings on tags  
**Segments Freed**: 1 segment  
**New Possibilities**: Could add one more segment for per-AMS hygrometer control  
**Recommendation**: ⚠️ Consider if tag bottom functions can be moved to tag top

#### Alternative 4: Combine All Background Lighting (Recommended)
**Approach**: Combine AMS bottoms + Tag bottoms + Hygrometers into 1-2 segments set to neutral soft white  
**Pros**: Maximizes segments for active/dynamic lighting  
**Cons**: All background areas show same color  
**Segments Freed**: Multiple segments  
**Recommendation**: ✅ Recommended baseline strategy for fixed layout

#### Alternative 5: Use Second Controller (MagWLED) for Complex Zones
**Approach**: Put AMS 2 tags on MagWLED with full top+bottom control (8 segments)  
**Pros**: Full control of AMS 2 tag lighting with individual bottoms  
**Cons**: Requires two-controller coordination, more complex automation  
**Segments Available**: MagWLED has 16 segments for AMS 2 tags alone  
**Recommendation**: ⚠️ Possible but adds complexity

## Neutral Segment Recommendations

For segments that serve as "background" or "fill" lighting, use a neutral soft white color:

### Recommended Neutral Color
- **Color**: Soft Warm White
- **RGB**: (255, 220, 180)
- **Hex**: #FFDCB4  
- **Brightness**: 30-40%
- **Purpose**: Provides ambient lighting without drawing attention

### Neutral Segments in Configuration
1. **Segment 4** (DigQuad): AMS 1 Tray Bottom - Soft white fill
2. **Segment 6** (DigQuad): AMS 2 Tray Bottom - Soft white fill  
3. **Segment 15** (DigQuad): Combined Hygrometers + Tag Bottoms - Soft white fill

### When Neutral Segments Change
These neutral segments may change color during specific scenarios:
- **Error states**: Change to red to indicate AMS-wide problems
- **Loading**: Change to blue during filament loading
- **Maintenance**: Change to yellow for maintenance warnings

## Implementation Priority

### Phase 1: Hardware Changes
1. ✅ **NO HARDWARE CHANGES NEEDED** - DigQuad is at full capacity (5 GPIO pins)
2. ✅ Interior Lid Light remains on MagWLED
3. ✅ Verify all LED counts match physical installation (711 on DigQuad + ~30 on MagWLED)

### Phase 2: Configuration Updates  
1. ✅ Update DigQuad segment definitions (16 segments used, 0 spare)
2. ✅ Configure 3 independent front door segments (bottom, left, top)
3. ✅ Set up neutral segments with soft white defaults
4. ✅ Keep MagWLED configuration for Interior Lid Light (1 segment, 15 spare)

### Phase 3: Preset Creation
1. ✅ Create presets for all scenarios (see preset-specification.md)
2. ✅ Test each preset to verify segment allocation works
3. ✅ Document workarounds for blocked scenarios
4. ✅ Coordinate presets across both controllers when needed

### Phase 4: Home Assistant Integration
1. ✅ Update automations to use new segment IDs (DigQuad 0-15)
2. ✅ Implement workarounds for blocked scenarios
3. ✅ Configure MagWLED Interior Lid Light control  
3. ✅ Test all automation triggers

## Conclusion

By keeping the Printer Interior Lid Light on MagWLED (since DigQuad is at full capacity) and splitting the front door into 3 independent segments on DigQuad, we achieve an optimal configuration. This approach uses all 16 segments on DigQuad (0 spare) and 1 segment on MagWLED (with 15 spare for future expansion).

### Key Benefits of This Approach
✅ Respects DigQuad's 5 GPIO pin limit (no hardware changes needed)
✅ Uses all 16 segments on DigQuad for maximum functionality  
✅ 3 independent front door segments (print progress, layer progress, status)
✅ Maintains individual tag top control (8 tags)  
✅ Maintains progress bar and layer progress functionality  
✅ Maintains independent status indication  
✅ Provides neutral background lighting  
✅ Keeps MagWLED with 15 segments available for future expansion  
✅ Simple Interior Lid Light control on MagWLED (1 segment)

### Key Limitations
⚠️ Full concurrent fidelity across all tray-level dimensions is not possible in one static 16-segment map  
⚠️ Fixed layout degrades per-tray bottom metrics and hygrometer independence  
⚠️ Hybrid dynamic/preset strategy is required for high-detail tray-specific moments  

### Hardware Reality
⚠️ **CRITICAL**: DigQuad has 5 GPIO pins and ALL are in use:
- GPIO 15: Printer Front Door (158 LEDs)
- GPIO 1: AMS 1 Lid/Spools (140 LEDs)
- GPIO 3: AMS 2 Lid/Spools (139 LEDs)
- GPIO 16: AMS 1 Tags + Hygrometer (136 LEDs)
- GPIO 4: AMS 2 Tags + Hygrometer (138 LEDs)

**NO additional LED strips can be connected to DigQuad.** The Interior Lid Light MUST remain on MagWLED.

### Recommended Next Steps
1. **Review and approve** this allocation approach
2. **NO hardware changes needed** - current physical setup is correct
3. **Adopt hybrid strategy**: baseline fixed map + dynamic/preset overlays
4. **Create detailed scenario compatibility matrix and priority rules**
5. **Update all configuration files and automations** to reflect hybrid behavior
6. **Test incrementally** with phased rollout and fallback behavior
