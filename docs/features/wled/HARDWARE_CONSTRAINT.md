# Hardware Constraint: DigQuad at Full Capacity

## Critical Understanding

**The DigQuad controller is at MAXIMUM CAPACITY and cannot accept additional LED strips.**

### DigQuad Hardware Specifications
- **GPIO Outputs**: 5 (maximum)
- **Current Usage**: ALL 5 GPIO pins in use
- **Remaining Capacity**: NONE

### Current DigQuad Connections (ALL 5 GPIO PINS)

| GPIO Pin | Connected LED Strip | LED Count | Purpose |
|----------|-------------------|-----------|---------|
| GPIO 15 | Printer Front Door | 158 LEDs | Progress bar + status indication |
| GPIO 1 | AMS 1 Lid/Spools | 140 LEDs | Spool illumination (top/bottom) |
| GPIO 3 | AMS 2 Lid/Spools | 139 LEDs | Spool illumination (top/bottom) |
| GPIO 16 | AMS 1 Tags + Hygrometer | 136 LEDs | Tag highlighting + humidity indicator |
| GPIO 4 | AMS 2 Tags + Hygrometer | 138 LEDs | Tag highlighting + humidity indicator |

**Total: 711 LEDs across 5 GPIO pins**

## Why Interior Lid Light Must Stay on MagWLED

1. **DigQuad has no available GPIO pins** - All 5 are in use
2. **Cannot disconnect existing strips** - All serve critical functions
3. **MagWLED must remain in use** - Has the Interior Lid Light connected
4. **No hardware changes possible** - Current configuration is physical reality

## MagWLED Configuration

### Current MagWLED Connection

| GPIO Pin | Connected LED Strip | LED Count | Purpose |
|----------|-------------------|-----------|---------|
| GPIO 2 | Interior Lid Light | ~30 LEDs | Simple interior illumination |

**Total: ~30 LEDs on 1 GPIO pin**

### MagWLED Capacity
- **GPIO Outputs**: 1 (single strip controller)
- **Current Usage**: 1 GPIO pin in use
- **Segment Capacity**: 16 segments (1 used, 15 available)
- **Future Expansion**: Yes, 15 segments available

## Segment Allocation Across Both Controllers

### DigQuad Segments (15 used, 1 spare)

| Segment ID | Name | LEDs | Purpose |
|------------|------|------|---------|
| 0 | Front Door Bottom | 50 | Progress bar |
| 1 | Front Door Left+Top | 108 | Status (merged) |
| 2 | AMS 1 Tray Top | 58 | Combined lighting |
| 3 | AMS 1 Tray Bottom | 57 | Neutral background |
| 4 | AMS 2 Tray Top | 60 | Combined lighting |
| 5 | AMS 2 Tray Bottom | 55 | Neutral background |
| 6 | AMS 1 Tag A1 Top | 12 | Individual control |
| 7 | AMS 1 Tag A2 Top | 12 | Individual control |
| 8 | AMS 1 Tag A3 Top | 12 | Individual control |
| 9 | AMS 1 Tag A4 Top | 12 | Individual control |
| 10 | AMS 2 Tag B1 Top | 13 | Individual control |
| 11 | AMS 2 Tag B2 Top | 14 | Individual control |
| 12 | AMS 2 Tag B3 Top | 14 | Individual control |
| 13 | AMS 2 Tag B4 Top | 12 | Individual control |
| 14 | Neutral Backgrounds | ~125 | Combined hygrometers + tag bottoms |

**Total: 15 segments on DigQuad, 1 spare segment available**

### MagWLED Segments (1 used, 15 spare)

| Segment ID | Name | LEDs | Purpose |
|------------|------|------|---------|
| 0 | Interior Lid Light | ~30 | Simple on/off lighting |

**Total: 1 segment on MagWLED, 15 spare segments available for future expansion**

## Benefits of This Configuration

### No Hardware Changes Required
✅ Respects physical hardware constraints
✅ No need to disconnect/reconnect LED strips
✅ Current wiring remains intact
✅ No risk of damaging connections

### Optimal Segment Usage
✅ DigQuad uses 15 of 16 available segments (93.75% utilization)
✅ MagWLED uses 1 of 16 available segments (6.25% utilization)
✅ Combined: 16 active segments across both controllers
✅ Future expansion possible on MagWLED (15 segments available)

### Maintains All Functionality
✅ Individual control of all 8 tray tags (A1-A4, B1-B4)
✅ Progress bar with dynamic updates
✅ Status indication (merged left+top)
✅ Basic AMS lighting (combined per unit)
✅ Neutral background lighting
✅ Simple interior lid control

## Two-Controller Coordination

### Home Assistant Integration

Since we use both controllers, Home Assistant automations must coordinate actions across both:

```yaml
# Example: Printer Idle Preset
automation:
  - alias: "WLED Printer Idle"
    trigger:
      - platform: state
        entity_id: sensor.printer_stage
        to: "idle"
    action:
      # Control DigQuad
      - service: light.turn_on
        target:
          entity_id: light.digquad
        data:
          preset: 2  # Idle preset for DigQuad segments
      
      # Control MagWLED
      - service: light.turn_on
        target:
          entity_id: light.magwled
        data:
          brightness: 102  # 40% for soft white interior lid
```

### Preset Coordination

Each scenario preset must specify:
1. **DigQuad segments** (0-14) - Complex lighting patterns
2. **MagWLED segment** (0) - Interior lid state

Example: Printing scenario
- DigQuad: Progress bar active, status green, active tray highlighted
- MagWLED: Interior lid bright white for visibility

## Why Previous Recommendation Was Incorrect

### Original (Incorrect) Recommendation
- ❌ "Move Interior Lid Light from MagWLED to DigQuad"
- ❌ "Free up MagWLED for future expansion"
- ❌ "Consolidate all LEDs on one controller"

### Why It Was Wrong
1. **DigQuad has no available GPIO pins** - All 5 are in use
2. **Cannot physically connect another strip** - Hardware limitation
3. **Would require disconnecting an existing critical strip** - Not viable

### Corrected Recommendation
- ✅ "Keep Interior Lid Light on MagWLED" - Respects hardware reality
- ✅ "DigQuad at full capacity" - Acknowledges constraint
- ✅ "Use both controllers" - Proper configuration

## Conclusion

**The Interior Lid Light MUST remain on MagWLED because DigQuad is at full capacity (5 GPIO pins, all in use).**

This configuration:
- Respects physical hardware constraints
- Uses 15 segments on DigQuad (1 spare)
- Uses 1 segment on MagWLED (15 spare for future)
- Maintains all functionality
- Requires two-controller coordination in Home Assistant
- Is the ONLY viable configuration given the hardware

**No hardware changes are needed or possible.** The current physical setup is correct and optimal.

---

**Document Purpose**: Clarify why the Interior Lid Light must stay on MagWLED  
**Hardware Reality**: DigQuad at full capacity (5/5 GPIO pins in use)  
**Configuration**: 15 segments on DigQuad + 1 on MagWLED = 16 active segments  
**Future Expansion**: MagWLED has 15 segments available
