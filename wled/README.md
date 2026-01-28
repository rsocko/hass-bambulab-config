# WLED Configuration for Bambu Lab Printer LED Setup

This directory contains WLED configuration files for controlling LED strips on a Bambu Lab printer with dual AMS units.

## Hardware Setup

### Controllers
- **Digquad LED Controller**: 5 LED strips (Strips 1-5)
- **MagWLED Controller**: 1 LED strip (Strip 6)

### LED Strip Layout

#### Strip 1 - Printer Interior Lighting
- **Location**: Inside printer lid
- **Purpose**: General interior illumination
- Current Blueprint starting point: https://github.com/PaulBiod/HA-bambulab-wled and similar: https://github.com/jberreth/bambu-status-wled-ha-blueprint
- **Segments**: 1 segment

#### Strip 2 - Printer Front Display (C-Shape)
- **Location**: Front of printer - bottom, left side, top
- **Layout**: 'C' shape wrapping around the front
- **Segments**: 3 segments
  - Bottom: Print progress bar
  - Left: Status indicator
  - Top: Status indicator

#### Strip 3 - AMS 1 Lid Spool Lighting
- **Location**: Top of AMS 1 lid
- **Layout**: Reverse 'C' shape across top and wrapping left
- **Purpose**: Illuminate individual spools
- **Segments**: 4 segments (one per spool slot)

#### Strip 4 - AMS 1 Tag Lighting
- **Location**: Front of AMS 1
- **Layout**: Across the top of tag holders (simplified top-only path)
- **Purpose**: Highlight active and upcoming spools
- **Segments**: 4 segments (one per spool slot, top path only)

#### Strip 5 - AMS 2 Lid Spool Lighting
- **Location**: Top of AMS 2 lid
- **Layout**: Same as Strip 3, reverse 'C' shape
- **Purpose**: Illuminate individual spools
- **Segments**: 4 segments (one per spool slot)

#### Strip 6 - AMS 2 Tag Lighting
- **Location**: Front of AMS 2
- **Layout**: Same as Strip 4
- **Purpose**: Highlight active and upcoming spools
- **Segments**: 8 segments (4 top paths + 4 bottom paths)

## Segment Allocation

### Digquad Controller (16 total segments - all used)
1. Segment 0: Strip 1 - Interior Light (full strip)
2. Segment 1: Strip 2 - Printer Bottom (progress bar)
3. Segment 2: Strip 2 - Printer Left (status)
4. Segment 3: Strip 2 - Printer Top (status)
5. Segment 4: Strip 3 - AMS1 Spool A1
6. Segment 5: Strip 3 - AMS1 Spool A2
7. Segment 6: Strip 3 - AMS1 Spool A3
8. Segment 7: Strip 3 - AMS1 Spool A4
9. Segment 8: Strip 4 - AMS1 Tag A1
10. Segment 9: Strip 4 - AMS1 Tag A2
11. Segment 10: Strip 4 - AMS1 Tag A3
12. Segment 11: Strip 4 - AMS1 Tag A4
13. Segment 12: Strip 5 - AMS2 Spool B1
14. Segment 13: Strip 5 - AMS2 Spool B2
15. Segment 14: Strip 5 - AMS2 Spool B3
16. Segment 15: Strip 5 - AMS2 Spool B4

### MagWLED Controller (8 segments - within 16 limit)
1. Segment 0: Strip 6 - AMS2 Tag B1
2. Segment 1: Strip 6 - AMS2 Tag B2
3. Segment 2: Strip 6 - AMS2 Tag B3
4. Segment 3: Strip 6 - AMS2 Tag B4
5. Segment 4: Strip 6 - AMS2 Tag B1 (bottom)
6. Segment 5: Strip 6 - AMS2 Tag B2 (bottom)
7. Segment 6: Strip 6 - AMS2 Tag B3 (bottom)
8. Segment 7: Strip 6 - AMS2 Tag B4 (bottom)

## Wiring Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    DIGQUAD CONTROLLER                    │
├─────────────────────────────────────────────────────────┤
│ Port 1: Strip 1 - Printer Interior                      │
│ Port 2: Strip 2 - Printer Front (C-shape)               │
│ Port 3: Strip 3 - AMS 1 Lid Spools                      │
│ Port 4: Strip 4 - AMS 1 Tags                            │
│ Port 5: Strip 5 - AMS 2 Lid Spools                      │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    MAGWLED CONTROLLER                    │
├─────────────────────────────────────────────────────────┤
│ Port 1: Strip 6 - AMS 2 Tags                            │
└─────────────────────────────────────────────────────────┘
```

## Presets

### Preset 1: Normal Printing
- Interior: Bright white
- Printer Front Bottom: Progress bar effect (e.g., rainbow moving)
- Printer Front Left/Top: Green (print running normally)
- Active AMS Spool: Bright white or color-matched to filament
- Inactive AMS Spools: Dim warm white
- Active Spool Tag: Bright color (matching filament or highlight color)
- Upcoming Spool Tags: Dimmed highlight color
- Unused Spool Tags: Off or very dim

### Preset 2: Print Error
- Interior: Red pulsing
- Printer Front: All red pulsing
- AMS remains as normal operation

### Preset 3: Print Complete
- Interior: Green
- Printer Front: Green chase/rainbow effect
- AMS lighting remains static

### Preset 4: Idle/Standby
- Interior: Dim warm white
- Printer Front: Soft blue breathing
- All AMS spools: Dim warm white
- All tags: Off

### Preset 5: Maintenance Mode
- Interior: Bright white (100%)
- Printer Front: Bright white
- All AMS: Bright white
- All tags: Bright white

### Preset 6: AMS Loading
- Interior: Dim
- Printer Front: Dim
- Active AMS spools: Chase effect showing loading
- Tags: Blink on slot being loaded

## Configuration Files

- `digquad-settings/`: Configuration for the Digquad controller
  - `wled_cfg_Digquad.json`: Main configuration with segment definitions
  - `wled_presets_Digquad.json`: Preset definitions for various scenarios
  - `wled_segments_Digquad.json`: Detailed segment layout reference

- `magwled-settings/`: Configuration for the MagWLED controller
  - `wled_cfg_MagWLED.json`: Main configuration (existing)
  - `wled_presets_MagWLED.json`: Preset definitions for AMS 2 tags
  - `wled_segments_MagWLED.json`: Detailed segment layout reference

## LED Count Requirements

Before implementing, you need to measure and document the LED counts for each strip:

### Strip 1 (Interior)
- Total LEDs: ___

### Strip 2 (Printer Front C-shape)
- Bottom segment LEDs: ___
- Left segment LEDs: ___
- Top segment LEDs: ___
- Total LEDs: ___

### Strip 3 (AMS 1 Lid)
- Spool A1 LEDs: ___
- Spool A2 LEDs: ___
- Spool A3 LEDs: ___
- Spool A4 LEDs: ___
- Total LEDs: ___

### Strip 4 (AMS 1 Tags)
- Tag A1 top LEDs: ___
- Tag A2 top LEDs: ___
- Tag A3 top LEDs: ___
- Tag A4 top LEDs: ___
- Tag A1 bottom LEDs: ___
- Tag A2 bottom LEDs: ___
- Tag A3 bottom LEDs: ___
- Tag A4 bottom LEDs: ___
- Total LEDs: ___

### Strip 5 (AMS 2 Lid)
- Spool B1 LEDs: ___
- Spool B2 LEDs: ___
- Spool B3 LEDs: ___
- Spool B4 LEDs: ___
- Total LEDs: ___

### Strip 6 (AMS 2 Tags)
- Tag B1 top LEDs: ___
- Tag B2 top LEDs: ___
- Tag B3 top LEDs: ___
- Tag B4 top LEDs: ___
- Tag B1 bottom LEDs: ___
- Tag B2 bottom LEDs: ___
- Tag B3 bottom LEDs: ___
- Tag B4 bottom LEDs: ___
- Total LEDs: ___

## Home Assistant Integration

Once the WLED controllers are configured:

1. Add both WLED devices to Home Assistant via the WLED integration
2. Create automations to control presets based on printer state
3. Use the Bambu Lab integration sensors to trigger appropriate presets:
   - `sensor.bambu_lab_x1c_current_stage`: Print stage
   - `sensor.bambu_lab_x1c_active_tray`: Active AMS tray
   - `sensor.bambu_lab_x1c_print_progress`: Print percentage

### Example Automation Triggers
- Print Started → Preset 1 (Normal Printing)
- Print Error → Preset 2 (Print Error)
- Print Complete → Preset 3 (Print Complete)
- Printer Idle → Preset 4 (Idle/Standby)
- AMS Tray Changed → Update active spool segments

## Implementation Steps

1. **Physical Installation**
   - Mount LED strips according to the layout diagram
   - Connect strips to respective controller ports
   - Power up controllers

2. **LED Count Measurement**
   - Test each strip to determine exact LED counts
   - Update the LED count requirements section above

3. **WLED Configuration**
   - Upload `wled_cfg_Digquad.json` to Digquad controller
   - Update `wled_cfg_MagWLED.json` for MagWLED controller
   - Adjust segment start/stop positions based on actual LED counts

4. **Preset Configuration**
   - Upload preset files to respective controllers
   - Test each preset manually
   - Fine-tune colors and effects as needed

5. **Home Assistant Integration**
   - Add WLED devices to Home Assistant
   - Create automations for automatic preset switching
   - Test automation triggers

## Notes and Recommendations

### Power Considerations
- Calculate total power draw: Each LED can draw up to 60mA at full white
- Ensure power supply can handle maximum load
- Consider using multiple power injection points for long strips

### Segment Limitations
- Digquad uses 16 segments (at the 16 segment limit)
- MagWLED uses 8 segments (8 under the 16 limit)
- No room for expansion on Digquad without reorganizing segments
- MagWLED has room for future expansion or adjustments

### Future Enhancements
- Add temperature-based color coding for AMS slots
- Implement humidity level indicators using AMS segments
- Create custom effects for different print filament types
- Add notification patterns for maintenance reminders

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
