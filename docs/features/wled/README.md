# WLED Configuration for Bambu Lab Printer LED Setup

> **Updated 2026-03-13** — Aligned to HA State Machine architecture.

This directory contains WLED configuration, documentation, and Home Assistant integration files for controlling LED strips on a Bambu Lab X1C printer with dual AMS units.

## Dependencies & Requirements

> **Foundation:** This feature requires the [Core](../core/README.md) package and the [ha-bambulab](https://github.com/greghesp/ha-bambulab) integration — see [Foundation Packages](../../README.md#foundation-packages). This feature does **not** depend on [Common](../common/README.md) — it controls physical LED hardware via HA automations, not dashboard cards.

### External Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [WLED](https://kno.wled.ge/) firmware on LED controllers | **Yes** | LED control firmware on DigQuad and/or MagWLED controllers |
| [WLED HA integration](https://www.home-assistant.io/integrations/wled/) | **Yes** | Built-in HA integration for WLED device discovery and control |
| DigQuad LED controller | **Yes** | 5-output controller driving 711 LEDs across 5 strips |
| MagWLED LED controller | No | Interior lid light (48 LEDs) — currently offline. System works without it. |
| 5V power supply (15–20A recommended) | **Yes** | Powers the LED strips — see [Power Considerations](#notes-and-recommendations) |

### Related Features

| Feature | Relationship |
|---|---|
| [Printer LED](../printer_led/README.md) | Dashboard controls for the WLED lights — depends on this feature |
| [Core](../core/README.md) | Smart status values drive state machine transitions (S0–S8) |

## Current Architecture: HA State Machine

The system uses a **Home Assistant state machine** that monitors printer status, transitions through **9 core states** (S0–S8), and applies WLED presets (101–109) to the DigQuad controller automatically.

**Phase 1 (Core State Machine) is deployed and running.** Phases 2–3 (segment expansion, overlays) are future work.

### Quick Links

| Document                                                         | Purpose                                                           |
| ---------------------------------------------------------------- | ----------------------------------------------------------------- |
| [quick-reference.md](quick-reference.md)                         | **Start here** — architecture overview, entities, phase status    |
| [ha-state-machine-package.md](ha-state-machine-package.md)       | State diagram, event mapping, preset mapping                      |
| [light-scenarios.md](light-scenarios.md)                         | Target vision — 33+ LED scenarios, priority tiers, overlay system |
| [phased-implementation-guide.md](phased-implementation-guide.md) | 3-phase implementation with test procedures                       |
| [INDEX.md](INDEX.md)                                             | Master file index with status of every document                   |

### Key Hardware Facts

- **DigQuad** — 5 GPIO pins, 711 LEDs, at **full capacity** (cannot add more strips)
- **MagWLED** — 1 GPIO pin, 48 LEDs (interior lid light, currently offline)
- **No hardware changes needed** — current physical setup is optimal

## Hardware Setup

### Controllers
- **Digquad LED Controller**: 5 LED outputs (GPIO 15, 1, 3, 16, 4)
- **MagWLED Controller**: 1 LED output (GPIO 2)
- **Total System LEDs**: 711

### LED Strip Layout

For detailed LED segment specifications, see [digquad-led-segments.md](digquad-led-segments.md).
For LED function details, see [LED Function Map](light-scenarios.md#2-led-function-map-consolidated).
For comprehensive scenario catalog, see [light-scenarios.md](light-scenarios.md).

#### Strip 1 - Printer Front Display (C-Shape)
- **GPIO Pin**: 15
- **LED Type**: COB 160 LED/m ([Amazon Product Link](https://www.amazon.com))
- **Location**: Front of printer door - bottom, left side, top
- **Layout**: 'C' shape wrapping around the front
- **Total LEDs**: 158 (LED Range: 0-157)
- **Segments**: 3 segments
  - **Bottom** (0-49): 50 LEDs - Print progress bar
  - **Left** (50-114): 65 LEDs - Status indicator (pulsing green when printing, flashing red on error)
  - **Top** (115-157): 43 LEDs - Status indicator (same as left side)
- **Functions**: Display print progress, print status, error indication

#### Strip 2 - AMS 1 Lid Spool Lighting
- **GPIO Pin**: 1
- **LED Type**: COB 160 LED/m ([Amazon Product Link](https://www.amazon.com))
- **Location**: Top of AMS 1 lid and spools
- **Total LEDs**: 140 (LED Range: 158-297)
- **Segments**: Can be configured as 4 segments (one per spool) or detailed by top/bottom
  - **Tray 1 Top**: 17 LEDs
  - **Tray 2 Top**: 12 LEDs
  - **Tray 3 Top**: 13 LEDs
  - **Tray 4 Top**: 13 LEDs
  - Side wall: 25 LEDs
  - **Tray 4 Bottom**: 14 LEDs
  - **Tray 3 Bottom**: 13 LEDs
  - **Tray 2 Bottom**: 13 LEDs
  - **Tray 1 Bottom**: 14 LEDs
- **Functions**: Illuminate spools, indicate current spool in use, show errors, animate loading/unloading

#### Strip 3 - AMS 2 Lid Spool Lighting
- **GPIO Pin**: 3
- **LED Type**: COB 160 LED/m ([Amazon Product Link](https://www.amazon.com))
- **Location**: Top of AMS 2 lid and spools
- **Total LEDs**: 139 (LED Range: 298-436)
- **Segments**: Can be configured as 4 segments (one per spool) or detailed by top/bottom
  - **Tray 1 Top**: 18 LEDs
  - **Tray 2 Top**: 13 LEDs
  - **Tray 3 Top**: 13 LEDs
  - **Tray 4 Top**: 14 LEDs
  - Side wall: 25 LEDs
  - **Tray 4 Bottom**: 14 LEDs
  - **Tray 3 Bottom**: 14 LEDs
  - **Tray 2 Bottom**: 13 LEDs
  - **Tray 1 Bottom**: 12 LEDs
- **Functions**: Same as AMS 1, plus animation when heating spool slot (AMS2 only)

#### Strip 4 - AMS 1 Tag Lighting
- **GPIO Pin**: 16
- **LED Type**: Mini 2.7mm wide 160 LED/m ([Amazon Product Link](https://www.amazon.com))
- **Location**: Front of AMS 1 tags and hygrometer
- **Total LEDs**: 136 (LED Range: 437-572)
- **Segments**: Complex layout including tags and hygrometer
  - Side (at start): 5 LEDs
  - **Tray 1 Top**: 12 LEDs
  - **Tray 2 Top**: 12 LEDs
  - **Tray 3 Top**: 12 LEDs
  - **Hygrometer (bottom)**: 12 LEDs
  - **Tray 4 Top**: 12 LEDs
  - Side wall: 5 LEDs
  - **Tray 4 Bottom**: 12 LEDs
  - **Tray 3 Bottom**: 15 LEDs
  - **Tray 2 Bottom**: 14 LEDs
  - **Hygrometer (top)**: 13 LEDs
  - **Tray 1 Bottom**: 12 LEDs
- **Functions**: Color-match filament, show % filament left, indicate filament in use, desiccant warning, spool errors

#### Strip 5 - AMS 2 Tag Lighting
- **GPIO Pin**: 4
- **LED Type**: Mini 2.7mm wide 160 LED/m ([Amazon Product Link](https://www.amazon.com))
- **Location**: Front of AMS 2 tags and hygrometer
- **Total LEDs**: 138 (LED Range: 573-710)
- **Segments**: Complex layout including tags and hygrometer
  - Side (at start): 6 LEDs
  - **Tray 1 Top**: 13 LEDs
  - **Tray 2 Top**: 14 LEDs
  - **Tray 3 Top**: 14 LEDs
  - **Hygrometer (bottom)**: 12 LEDs
  - **Tray 4 Top**: 12 LEDs
  - Side wall: 5 LEDs
  - **Tray 4 Bottom**: 12 LEDs
  - **Tray 3 Bottom**: 15 LEDs
  - **Tray 2 Bottom**: 15 LEDs
  - **Hygrometer (top)**: 13 LEDs
  - **Tray 1 Bottom**: 11 LEDs
- **Functions**: Same as AMS 1 tags

#### Interior Lights
- Controlled via existing Home Assistant automation
- Use rules to control colors based on print status & stage
- See [light-scenarios.md](light-scenarios.md) for recommended behaviors

## Segment Allocation

The segment allocation can be organized based on functional needs. For the actual LED ranges and GPIO pin mappings, see [digquad-led-segments.md](digquad-led-segments.md).

### Suggested Digquad Segments
1. Segment 0: Printer Door Bottom (0-50) - Progress bar
2. Segment 1: Printer Door Left (51-115) - Status indicator
3. Segment 2: Printer Door Top (116-157) - Status indicator
4. Segment 3-6: AMS1 Tray Lighting (158-297) - Can be split by tray or top/bottom
5. Segment 7-10: AMS2 Tray Lighting (298-436) - Can be split by tray or top/bottom
6. Segment 11-14: AMS1 Tags (437-572) - Complex segmentation for tags and hygrometer
7. Segment 15: Reserved for additional AMS1 segments

Note: With 711 total LEDs across 5 GPIO outputs, segment planning should be based on functional zones rather than fixed allocations. Refer to [LED Function Map](light-scenarios.md#2-led-function-map-consolidated) for specific use cases.

## Wiring Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    DIGQUAD CONTROLLER                    │
├─────────────────────────────────────────────────────────┤
│ GPIO 15: Printer Front Door (C-shape) - 158 LEDs        │
│ GPIO 1:  AMS 1 Lid/Spools - 140 LEDs                    │
│ GPIO 3:  AMS 2 Lid/Spools - 139 LEDs                    │
│ GPIO 16: AMS 1 Tags + Hygrometer - 136 LEDs             │
│ GPIO 4:  AMS 2 Tags + Hygrometer - 138 LEDs             │
│                                                          │
│ Total: 711 LEDs                                          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                 INTERIOR LIGHTING                        │
├─────────────────────────────────────────────────────────┤
│ Controlled via existing Home Assistant automations      │
│ See: https://github.com/PaulBiod/HA-bambulab-wled       │
│ and: https://github.com/jberreth/bambu-status-wled-ha-  │
│      blueprint                                           │
└─────────────────────────────────────────────────────────┘
```

For detailed wiring specifications and LED ranges, see [digquad-led-segments.md](digquad-led-segments.md).

## Presets

The system currently uses **state machine presets 101–109** on the DigQuad controller, one per core state:

| Preset | State | Description |
|--------|-------|-------------|
| 101 | S0 Offline | Printer powered off / unreachable |
| 102 | S1 Idle | Powered on, not printing |
| 103 | S2 Preparing | Heating, leveling, calibrating |
| 104 | S3 Printing | Active print in progress |
| 105 | S4 Paused | Print paused (user or filament) |
| 106 | S5 Complete | Print finished |
| 107 | S6 Error | Error state |
| 108 | S7 Updating | Firmware update |
| 109 | S8 Show | Demo / rainbow mode |

These are skeleton presets (segments 0 + 1 only). Phase 2 will expand them to the full 15-segment layout. See [ha-state-machine-package.md](ha-state-machine-package.md) for the complete state and event mapping.

> **Note:** The original preset specification (presets 1–33) in [preset-specification.md](preset-specification.md) was a design document that was **never deployed**. It is retained as legacy reference only.

For detailed function specifications for each zone, see [LED Function Map](light-scenarios.md#2-led-function-map-consolidated).

## Configuration Files

- `digquad-settings/`: Configuration for the Digquad controller
  - `wled_cfg_Digquad.json`: Main configuration with segment definitions
  - `wled_presets_Digquad.json`: Preset definitions for various scenarios
  - `wled_segments_Digquad.json`: Detailed segment layout reference
- `magwled-settings/`: Configuration snapshots for MagWLED controller
- `backups/`: Versioned controller snapshots (DigQuad and MagWLED)
  - See [wled/backups/README.md](../../../wled/backups/README.md) for folder conventions
  - See [backup-and-restore.md](backup-and-restore.md) for backup/restore steps

## LED Specifications

### Actual LED Counts (Measured)

**Total System LEDs: 711**

#### Printer Front Door (GPIO 15)
- **Total LEDs**: 158 (Range: 0-157)
- Bottom segment: 50 LEDs (0-50)
- Left segment: 65 LEDs (51-115)
- Top segment: 43 LEDs (116-157)

#### AMS 1 Lid/Spools (GPIO 1)
- **Total LEDs**: 140 (Range: 158-297)
- See [digquad-led-segments.md](digquad-led-segments.md) for detailed breakdown

#### AMS 2 Lid/Spools (GPIO 3)
- **Total LEDs**: 139 (Range: 298-436)
- See [digquad-led-segments.md](digquad-led-segments.md) for detailed breakdown

#### AMS 1 Tags (GPIO 16)
- **Total LEDs**: 136 (Range: 437-572)
- Includes filament tags and hygrometer lighting
- See [digquad-led-segments.md](digquad-led-segments.md) for detailed breakdown

#### AMS 2 Tags (GPIO 4)
- **Total LEDs**: 138 (Range: 573-710)
- Includes filament tags and hygrometer lighting
- See [digquad-led-segments.md](digquad-led-segments.md) for detailed breakdown

For complete LED specifications with exact segment ranges, refer to [digquad-led-segments.md](digquad-led-segments.md).

## Home Assistant Integration

The HA state machine package handles all WLED control automatically. The package lives at `homeassistant/packages/3d_printing/wled/` and includes:

- **Orchestrator automation** — watches printer sensors, computes E_* events, transitions states
- **Transition script** — applies the correct preset when state changes
- **Helpers** — `input_select` for state, `input_boolean` for enable/disable, `input_text` for last event

See [ha-state-machine-package.md](ha-state-machine-package.md) for the full architecture and [quick-reference.md](quick-reference.md) for entity names.
- **Printer Idle** → Preset 2 (Idle/Standby)
- **AMS Tray Changed** → Update active tray segments with filament color
- **Filament Loading** → Preset 17 (Loading animation)
- **Humidity High** → Preset 20 (Humidity warning)
- **Door Open** → Preset 16 (Door open warning)

## Implementation Steps

1. **Physical Installation**
   - Mount LED strips according to the layout specifications in [digquad-led-segments.md](digquad-led-segments.md)
   - Follow the detailed physical installation guide in [wiring-diagram.md](wiring-diagram.md)
   - Connect strips to Digquad controller GPIO pins (15, 1, 3, 16, 4)
   - Power up controller with adequate 5V power supply

2. **WLED Configuration**
   - Upload `wled_cfg_Digquad.json` to Digquad controller
   - Configure GPIO outputs with actual LED counts (711 total)
   - Adjust segment start/stop positions based on [digquad-led-segments.md](digquad-led-segments.md)
   - Verify all 711 LEDs are properly addressed

3. **Preset Configuration**
   - Upload preset files to controller
   - Configure presets according to [light-scenarios.md](light-scenarios.md)
   - Test each preset manually to verify behavior
   - Fine-tune colors and effects as needed

4. **Home Assistant Integration**
   - Add WLED device to Home Assistant
   - Create automations based on [home-assistant-automations.md](home-assistant-automations.md)
   - Map printer states to appropriate presets from [light-scenarios.md](light-scenarios.md)
   - Test automation triggers with actual print jobs

5. **Function Validation**
  - Test each LED function from [LED Function Map](light-scenarios.md#2-led-function-map-consolidated)
   - Verify progress bar display on printer door bottom
   - Confirm filament color matching on tags
   - Test hygrometer humidity indicators
   - Validate error state displays

## Notes and Recommendations

### Power Considerations
- Calculate total power draw: Each LED can draw up to 60mA at full white
- Total LEDs: 711
- Maximum draw: 711 × 0.06A = 42.66A at full white (unlikely scenario)
- Typical usage at 30-50% brightness: ~12-21A
- **Recommendation**: 15-20A 5V power supply with adequate headroom
- Use power injection at multiple points for strips over 100 LEDs

### LED Type Specifications
- **Printer Door**: COB 160 LED/m strips
- **AMS Lid/Spools**: COB 160 LED/m strips
- **AMS Tags**: Mini 2.7mm wide 160 LED/m strips
- Verify LED type compatibility (WS2812B, SK6812, etc.) in WLED configuration

### Segment Planning
- Plan segments based on functional zones (see [LED Function Map](light-scenarios.md#2-led-function-map-consolidated))
- WLED supports up to 16 segments per controller (with some configurations supporting more)
- Organize segments by function rather than strict physical layout
- Key functional zones:
  - Progress indication (door bottom)
  - Status indication (door left/top)
  - Spool illumination (AMS lids)
  - Tag highlighting (AMS fronts)
  - Hygrometer indication (AMS fronts)

### Future Enhancements
- Add temperature-based color coding for AMS slots
- Implement humidity level indicators using hygrometer LEDs
- Create custom effects for different print filament types
- Add notification patterns for maintenance reminders
- Implement filament color matching from Spoolman integration
- Add desiccant age warning on tag bottom LEDs
- Display remaining filament percentage on tags

### Troubleshooting
- If segments don't align properly, verify LED counts
- If colors are incorrect, check LED type in WLED config
- If effects are choppy, reduce FPS or simplify effects
- For sync issues, ensure both controllers are on same network

## Support

For issues or questions:
- WLED Documentation: https://kno.wled.ge/
- Home Assistant WLED Integration: https://www.home-assistant.io/integrations/wled/
- Repository Issues: https://github.com/rsocko/hass-bambulab-config/issues
