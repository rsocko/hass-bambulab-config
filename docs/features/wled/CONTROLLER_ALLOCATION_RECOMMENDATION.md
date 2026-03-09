# Controller Allocation Recommendation

## Executive Summary

This document provides recommendations for allocating LED strips between the **MagWLED** (single LED strip controller) and **DigQuad** (5 LED strip controller) to optimize the 16-segment limitation per controller.

### Key Recommendations

1. **Keep Lid LED (Interior Light) on MagWLED** - DigQuad is at full capacity (5 strips maximum) and cannot accept additional LED strips
2. **Merge Front Door Left and Top segments** - Reduces front door from 3 segments to 2 segments
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
1. **Front Door Bottom** (progress bar): 1 segment  
2. **Front Door Left+Top** (merged status): 1 segment
3. **AMS 1 - Tray Top (combined)**: 1 segment OR per-tray: 4 segments
4. **AMS 1 - Tray Bottom (combined)**: 1 segment
5. **AMS 1 - Tag Tops (4 trays)**: 4 segments
6. **AMS 1 - Tag Bottoms (combined)**: 1 segment
7. **AMS 1 - Hygrometer**: 1 segment
8. **AMS 2 - Tray Top (combined)**: 1 segment OR per-tray: 4 segments
9. **AMS 2 - Tray Bottom (combined)**: 1 segment
10. **AMS 2 - Tag Tops (4 trays)**: 4 segments
11. **AMS 2 - Tag Bottoms (combined)**: 1 segment
12. **AMS 2 - Hygrometer**: 1 segment

**Minimum Total on DigQuad: 15 segments** (with combined AMS tray lighting)
**Plus MagWLED: 1 segment** (Interior Lid Light)
**Grand Total: 16 segments across both controllers**

**Maximum with per-tray AMS lighting: 21 segments** (exceeds 16-segment limit per controller!)

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
- **Segment 0**: Bottom (Progress Bar) - LEDs 0-49 (50 LEDs)
- **Segment 1**: Left+Top Combined (Status) - LEDs 50-157 (108 LEDs) ✨ MERGED
- **Total: 2 segments**

#### GPIO 1: AMS 1 Lid/Spools (140 LEDs)  
- **Segment 2**: Tray Top (all spools combined) - LEDs 158-215 (58 LEDs)
- **Segment 3**: Tray Bottom (all spools combined, neutral) - LEDs 241-297 (57 LEDs)
- **Total: 2 segments**

#### GPIO 3: AMS 2 Lid/Spools (139 LEDs)
- **Segment 4**: Tray Top (all spools combined) - LEDs 298-357 (60 LEDs)  
- **Segment 5**: Tray Bottom (all spools combined, neutral) - LEDs 382-436 (55 LEDs)
- **Total: 2 segments**

#### GPIO 16: AMS 1 Tags + Hygrometer (136 LEDs)
- **Segment 6**: Tag A1 Top - LEDs 442-453 (12 LEDs)
- **Segment 7**: Tag A2 Top - LEDs 454-465 (12 LEDs)
- **Segment 8**: Tag A3 Top - LEDs 466-477 (12 LEDs)
- **Segment 9**: Tag A4 Top - LEDs 490-501 (12 LEDs)
- **Segment 10**: Hygrometer - LEDs 478-489 + 554-566 (25 LEDs combined)
- **Segment 11**: Tag Bottoms (all combined, neutral) - LEDs 507-553 (47 LEDs)
- **Total: 6 segments**

#### GPIO 4: AMS 2 Tags + Hygrometer (138 LEDs)
- **Segment 12**: Tag B1 Top - LEDs 579-591 (13 LEDs)
- **Segment 13**: Tag B2 Top - LEDs 592-605 (14 LEDs)  
- **Segment 14**: Tag B3 Top - LEDs 606-619 (14 LEDs)
- **Segment 15**: Tag B4 Top - LEDs 632-643 (12 LEDs)
- **Total: 4 segments**

#### Combined Neutral Backgrounds
- **Segment 16**: Would need to combine AMS 2 hygrometer + tag bottoms, but we're at the 16-segment limit

**Current Count: 16 segments** (0-15)

## Solution: Combine Neutral Backgrounds Strategically

Since we have exactly 16 segments available on DigQuad, we need to combine background segments efficiently.

### Final Recommended Configuration

#### DigQuad - Segment Allocation (15 segments used, 1 spare)

0. **Segment 0**: Front Door Bottom (Progress Bar) - 1 segment
1. **Segment 1**: Front Door Left+Top (Status, MERGED) - 1 segment ✨ MERGED
2. **Segment 2**: AMS 1 Tray Top (all spools) - 1 segment
3. **Segment 3**: AMS 1 Tray Bottom (neutral) - 1 segment
4. **Segment 4**: AMS 2 Tray Top (all spools) - 1 segment
5. **Segment 5**: AMS 2 Tray Bottom (neutral) - 1 segment
6. **Segment 6**: AMS 1 Tag A1 Top - 1 segment
7. **Segment 7**: AMS 1 Tag A2 Top - 1 segment
8. **Segment 8**: AMS 1 Tag A3 Top - 1 segment
9. **Segment 9**: AMS 1 Tag A4 Top - 1 segment
10. **Segment 10**: AMS 2 Tag B1 Top - 1 segment
11. **Segment 11**: AMS 2 Tag B2 Top - 1 segment
12. **Segment 12**: AMS 2 Tag B3 Top - 1 segment
13. **Segment 13**: AMS 2 Tag B4 Top - 1 segment
14. **Segment 14**: AMS 1+2 Hygrometers + Tag Bottoms (neutral, combined) - 1 segment

**Total: 15 segments on DigQuad, 1 segment available for future use! ✅**

#### MagWLED - Segment Allocation (1 segment used, 15 spare)

0. **Segment 0**: Interior Lid Light - 1 segment (simple on/off)

**Total: 1 segment on MagWLED, 15 segments available for future expansion! ✅**

#### Grand Total System
- **DigQuad**: 15 segments used, 1 spare
- **MagWLED**: 1 segment used, 15 spare
- **Total Segments**: 16 active segments across both controllers
- **Total LEDs**: 711 LEDs on DigQuad + ~30 on MagWLED = ~741 LEDs

## Segment Limitations and Trade-offs

### What We CAN Do with This Configuration

✅ **Full tag highlighting**: Each of 8 tray tags gets individual control  
✅ **Progress bar**: Independent progress indication on front door  
✅ **Status indication**: Merged left+top for consistent status display  
✅ **Basic AMS lighting**: Combined top/bottom lighting per AMS unit  
✅ **Neutral backgrounds**: Tag bottoms and hygrometers have soft white light  

### What We CANNOT Do with This Configuration

❌ **Per-tray AMS lid lighting**: Cannot individually control the lighting above each of the 4 trays  
❌ **Individual tag bottom control**: All tag bottoms share one segment (neutral color)  
❌ **Separate hygrometer control**: Hygrometers share segment with tag bottoms  
❌ **AMS tray bottom individual control**: All bottom lighting is combined per AMS  

### Blocked Scenarios

The following scenarios are BLOCKED or DEGRADED by segment limitations:

#### BLOCKED: Individual AMS Tray Top Animation
**Scenario**: Animate loading/unloading for a specific tray with LED chase on tray top  
**Why Blocked**: AMS tray tops are combined into single segment per AMS  
**Alternative**: Use tag top to indicate which tray is loading (tag can flash/pulse)

#### BLOCKED: Per-Tray Filament Remaining Display  
**Scenario**: Show filament remaining as a percentage on tag bottom LEDs  
**Why Blocked**: Tag bottoms are combined into one neutral segment  
**Alternative**: Use tag top color intensity/brightness to indicate level, OR use single-color solid on tag top (e.g., dimmer = less filament)

#### DEGRADED: Humidity Warning on Specific AMS
**Scenario**: Flash red on hygrometer for AMS with high humidity  
**Why Degraded**: Both hygrometers share a combined segment  
**Alternative**: Use AMS tray top or tag segments to indicate which AMS has humidity issue

#### DEGRADED: Desiccant Age Warning per Tray
**Scenario**: Show orange on tag bottom for old desiccant  
**Why Degraded**: Tag bottoms are combined  
**Alternative**: Flash or pulse tag top orange to indicate desiccant warning

### Alternative Approaches for Blocked Scenarios

#### Alternative 1: Dynamic Segment Reconfiguration
**Approach**: Use presets that reconfigure segment definitions for specific scenarios  
**Pros**: Can achieve more granular control when needed  
**Cons**: Complex to implement, may cause delays during reconfiguration, risks losing state  
**Recommendation**: ❌ Not recommended - too complex

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
**Recommendation**: ✅ **RECOMMENDED** - This is included in final configuration above

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
1. **Segment 3** (DigQuad): AMS 1 Tray Bottom - Soft white fill
2. **Segment 5** (DigQuad): AMS 2 Tray Bottom - Soft white fill  
3. **Segment 14** (DigQuad): Combined Hygrometers + Tag Bottoms - Soft white fill

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
1. ✅ Update DigQuad segment definitions (15 segments used, 1 spare)
2. ✅ Configure front door left+top merge
3. ✅ Set up neutral segments with soft white defaults
4. ✅ Keep MagWLED configuration for Interior Lid Light (1 segment, 15 spare)

### Phase 3: Preset Creation
1. ✅ Create presets for all scenarios (see PRESET_SPECIFICATION.md)
2. ✅ Test each preset to verify segment allocation works
3. ✅ Document workarounds for blocked scenarios
4. ✅ Coordinate presets across both controllers when needed

### Phase 4: Home Assistant Integration
1. ✅ Update automations to use new segment IDs (DigQuad 0-14)
2. ✅ Implement workarounds for blocked scenarios
3. ✅ Configure MagWLED Interior Lid Light control  
3. ✅ Test all automation triggers

## Conclusion

By keeping the Printer Interior Lid Light on MagWLED (since DigQuad is at full capacity) and merging the front door left+top segments on DigQuad, we achieve an optimal configuration. This approach uses 15 segments on DigQuad (with 1 spare) and 1 segment on MagWLED (with 15 spare for future expansion).

### Key Benefits of This Approach
✅ Respects DigQuad's 5 GPIO pin limit (no hardware changes needed)
✅ Stays well within 16-segment limit (15 used on DigQuad, 1 spare)  
✅ Maintains individual tag top control (8 tags)  
✅ Maintains progress bar functionality  
✅ Maintains status indication  
✅ Provides neutral background lighting  
✅ Keeps MagWLED with 15 segments available for future expansion  
✅ Simple Interior Lid Light control on MagWLED (1 segment)

### Key Limitations
❌ Cannot animate individual AMS tray tops  
❌ Cannot show per-tag filament remaining on bottoms  
❌ Cannot independently control both hygrometers  
❌ Cannot show per-tag desiccant warnings on bottoms  

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
3. **Create detailed preset specification** (see PRESET_SPECIFICATION.md)
4. **Update all configuration files** to reflect 15 segments on DigQuad, 1 on MagWLED
5. **Test incrementally** with phased rollout
