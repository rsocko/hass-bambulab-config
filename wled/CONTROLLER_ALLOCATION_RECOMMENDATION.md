# Controller Allocation Recommendation

## Executive Summary

This document provides recommendations for allocating LED strips between the **MagWLED** (single LED strip controller) and **DigQuad** (5 LED strip controller) to optimize the 16-segment limitation per controller.

### Key Recommendations

1. **Move Lid LED (Interior Light) from MagWLED to DigQuad** - This simple LED strip requires only 1 segment
2. **Merge Front Door Left and Top segments** - Reduces front door from 3 segments to 2 segments
3. **Use simplified segment layouts** for AMS components to stay within 16-segment limit
4. **Create neutral segments** for unused areas (bottoms of tags/AMS lids) set to soft white

## Current Configuration Analysis

### Current MagWLED Allocation (1 strip controller)
- **Strip 1**: Interior Lid Light (GPIO 2)
  - Segment 0: Interior Light (30 LEDs) - simple single segment
  - **Total: 1 segment used, 15 segments available**

### Current DigQuad Allocation (Based on Documentation)
According to `README.md`, the actual physical installation uses:
- **GPIO 15**: Printer Front Door - 158 LEDs
- **GPIO 1**: AMS 1 Lid/Spools - 140 LEDs  
- **GPIO 3**: AMS 2 Lid/Spools - 139 LEDs
- **GPIO 16**: AMS 1 Tags + Hygrometer - 136 LEDs
- **GPIO 4**: AMS 2 Tags + Hygrometer - 138 LEDs
- **Total: 711 LEDs**

## Segment Counting Analysis

### Scenario-Based Segment Requirements

To understand segment needs, we must consider what segments are needed for different scenarios:

#### Minimum Segments Needed (Basic Functionality)
1. **Lid Interior Light**: 1 segment
2. **Front Door Bottom** (progress bar): 1 segment  
3. **Front Door Left+Top** (merged status): 1 segment
4. **AMS 1 - Tray Top (combined)**: 1 segment OR per-tray: 4 segments
5. **AMS 1 - Tray Bottom (combined)**: 1 segment
6. **AMS 1 - Tag Tops (4 trays)**: 4 segments
7. **AMS 1 - Tag Bottoms (combined)**: 1 segment
8. **AMS 1 - Hygrometer**: 1 segment
9. **AMS 2 - Tray Top (combined)**: 1 segment OR per-tray: 4 segments
10. **AMS 2 - Tray Bottom (combined)**: 1 segment
11. **AMS 2 - Tag Tops (4 trays)**: 4 segments
12. **AMS 2 - Tag Bottoms (combined)**: 1 segment
13. **AMS 2 - Hygrometer**: 1 segment

**Minimum Total: 15 segments** (with combined AMS tray lighting)
**Maximum with per-tray AMS lighting: 21 segments** (exceeds 16-segment limit!)

### The Segment Limitation Challenge

With a 16-segment limit per controller, we cannot have:
- Individual control of all 4 AMS tray top lighting zones (8 segments for both AMS units)
- Individual control of all 8 tag tops (8 segments)
- Individual control of tag bottoms
- Individual control of AMS tray bottoms
- Individual hygrometer control

## Recommended Controller Allocation

### Recommended MagWLED Configuration (1 strip)
**Purpose**: Reserve for future expansion or alternative configuration

- **Option A**: Keep empty for future use
- **Option B**: Use for printer interior features that need independent control
- **Option C**: Use for exterior aesthetic lighting

### Recommended DigQuad Configuration (5 strips)

**GPIO Pin Allocation** (matches current physical installation):

#### GPIO 15: Printer Front Door (158 LEDs)
- **Segment 1**: Bottom (Progress Bar) - LEDs 0-49 (50 LEDs)
- **Segment 2**: Left+Top Combined (Status) - LEDs 50-157 (108 LEDs) ✨ MERGED
- **Total: 2 segments**

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
- **Segment 11**: Hygrometer - LEDs 478-489 + 554-566 (25 LEDs combined)
- **Segment 12**: Tag Bottoms (all combined, neutral) - LEDs 507-553 (47 LEDs)
- **Total: 6 segments**

#### GPIO 4: AMS 2 Tags + Hygrometer (138 LEDs)
- **Segment 13**: Tag B1 Top - LEDs 579-591 (13 LEDs)
- **Segment 14**: Tag B2 Top - LEDs 592-605 (14 LEDs)  
- **Segment 15**: Tag B3 Top - LEDs 606-619 (14 LEDs)
- **Segment 16**: Tag B4 Top - LEDs 632-643 (12 LEDs)
- **Unable to add more segments - LIMIT REACHED**

**⚠️ PROBLEM**: We've hit the 16-segment limit and still need:
- Hygrometer for AMS 2
- Tag bottoms for AMS 2

## Solution: Lid Interior Light on DigQuad

### Alternative Configuration: Move Lid to DigQuad

Since the Lid Interior Light only needs 1 segment and is simple to control, we should move it to MagWLED, freeing up a DigQuad GPIO pin for more complex uses.

**Wait - this doesn't match the problem statement!**

Re-reading: The user says "the Lid LED strip (which will never need more than 1 segment) should be connected to the Digquad". Currently it's on MagWLED, so we need to move it TO DigQuad.

### Revised Recommended Configuration

#### MagWLED Configuration (1 strip)
- **GPIO 2**: **EMPTY** - Reserved for future use or moved to DigQuad
- This frees MagWLED for potential future expansion

#### DigQuad Configuration (5 strips) - OPTIMAL

Since we're moving the simple Lid LED to DigQuad, we need a different approach. However, DigQuad only has 5 GPIO pins, and they're already allocated. 

**The solution**: The Lid Interior Light is ALREADY on a DigQuad GPIO based on the README documentation (GPIO 1 controls "AMS 1 Lid/Spools"). But looking more carefully, this is the AMS Lid spool lighting, not the printer interior lid light.

Let me reconsider: Based on the documentation, there seem to be TWO different lid lights:
1. **Printer Interior Lid Light** - currently on MagWLED
2. **AMS Lid Spool Lighting** - already on DigQuad (GPIO 1 and 3)

### Final Recommendation: Optimal Allocation

**Move Printer Interior Lid Light from MagWLED GPIO 2 to one of the DigQuad GPIOs that has capacity**

Since we need 16 segments total and must be strategic, here's the optimal layout:

#### DigQuad - Segment Allocation (16 segments max)

1. **Segment 0**: Interior Lid Light (simple, single color) - 1 segment ✨ MOVED FROM MAGWLED
2. **Segment 1**: Front Door Bottom (Progress Bar) - 1 segment
3. **Segment 2**: Front Door Left+Top (Status, MERGED) - 1 segment ✨ MERGED
4. **Segment 3**: AMS 1 Tray Top (all spools) - 1 segment
5. **Segment 4**: AMS 1 Tray Bottom (neutral) - 1 segment
6. **Segment 5**: AMS 2 Tray Top (all spools) - 1 segment
7. **Segment 6**: AMS 2 Tray Bottom (neutral) - 1 segment
8. **Segment 7**: AMS 1 Tag A1 Top - 1 segment
9. **Segment 8**: AMS 1 Tag A2 Top - 1 segment
10. **Segment 9**: AMS 1 Tag A3 Top - 1 segment
11. **Segment 10**: AMS 1 Tag A4 Top - 1 segment
12. **Segment 11**: AMS 2 Tag B1 Top - 1 segment
13. **Segment 12**: AMS 2 Tag B2 Top - 1 segment
14. **Segment 13**: AMS 2 Tag B3 Top - 1 segment
15. **Segment 14**: AMS 2 Tag B4 Top - 1 segment
16. **Segment 15**: AMS 1+2 Hygrometers + Tag Bottoms (neutral, combined) - 1 segment

**Total: 16 segments - EXACTLY at limit! ✅**

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
1. **Segment 4**: AMS 1 Tray Bottom - Soft white fill
2. **Segment 6**: AMS 2 Tray Bottom - Soft white fill  
3. **Segment 15**: Combined Hygrometers + Tag Bottoms - Soft white fill

### When Neutral Segments Change
These neutral segments may change color during specific scenarios:
- **Error states**: Change to red to indicate AMS-wide problems
- **Loading**: Change to blue during filament loading
- **Maintenance**: Change to yellow for maintenance warnings

## Implementation Priority

### Phase 1: Hardware Changes
1. ✅ Move Printer Interior Lid Light from MagWLED to DigQuad
2. ✅ Verify all LED counts match physical installation (711 total)

### Phase 2: Configuration Updates  
1. ✅ Update DigQuad segment definitions (16 segments)
2. ✅ Configure front door left+top merge
3. ✅ Set up neutral segments with soft white defaults
4. ✅ Remove MagWLED configuration (or keep for future use)

### Phase 3: Preset Creation
1. ✅ Create presets for all scenarios (see PRESET_SPECIFICATION.md)
2. ✅ Test each preset to verify segment allocation works
3. ✅ Document workarounds for blocked scenarios

### Phase 4: Home Assistant Integration
1. ✅ Update automations to use new segment IDs
2. ✅ Implement workarounds for blocked scenarios  
3. ✅ Test all automation triggers

## Conclusion

By moving the simple Printer Interior Lid Light to DigQuad and merging the front door left+top segments, we can stay within the 16-segment limitation while maintaining excellent functionality. The trade-off is that some advanced per-tray and per-tag-bottom features are not possible, but workable alternatives exist for all blocked scenarios.

### Key Benefits of This Approach
✅ Stays within 16-segment limit  
✅ Maintains individual tag top control (8 tags)  
✅ Maintains progress bar functionality  
✅ Maintains status indication  
✅ Provides neutral background lighting  
✅ Keeps MagWLED available for future expansion  

### Key Limitations
❌ Cannot animate individual AMS tray tops  
❌ Cannot show per-tag filament remaining on bottoms  
❌ Cannot independently control both hygrometers  
❌ Cannot show per-tag desiccant warnings on bottoms  

### Recommended Next Steps
1. **Review and approve** this allocation approach
2. **Implement hardware changes** (move lid LED)
3. **Create detailed preset specification** (next document)
4. **Update all configuration files**
5. **Test incrementally** with phased rollout
