# Quick Start Guide - WLED Bambu Lab Printer Lighting

This guide will help you get started quickly with your WLED LED strip configuration for Bambu Lab printer and dual AMS setup.

## What's Included

This configuration package includes:

1. **Specification Documents** (READ THESE FIRST):
   - `digquad-led-segments.md` - Exact LED specifications (711 LEDs total)
   - `light-scenarios.md` (Section 2: LED Function Map) - Detailed function specifications for each zone
   - `light-scenarios.md` - Complete catalog of 33+ lighting scenarios
2. **Main README** (`README.md`) - Complete overview integrated with specifications
3. **Wiring Diagram** ([docs/wiring-diagram.md](docs/wiring-diagram.md)) - Detailed installation instructions
4. **Home Assistant Automations** ([docs/home-assistant-automations.md](docs/home-assistant-automations.md)) - Integration examples
5. **Backup Guide** ([BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md)) - Backup/restore process and required files
6. **Digquad Configuration**:
   - `digquad-settings/wled_cfg_Digquad.json` - Controller configuration
   - `digquad-settings/wled_presets_Digquad.json` - Presets based on light-scenarios.md
   - `digquad-settings/wled_segments_Digquad.json` - Segment layout reference

## DigQuad File Deployment Matrix

Use this as the source of truth for what to load to DigQuad.

| File | Purpose | Load to DigQuad? | How |
|------|---------|------------------|-----|
| `wled/digquad-settings/wled_cfg_Digquad.json` | Base controller config | Yes | Upload as `/cfg.json` via `http://<digquad>/edit` (or restore equivalent), then reboot |
| `wled/digquad-settings/wled_presets_Digquad.json` | Main preset pack | Yes | Upload as `/presets.json` via `http://<digquad>/edit` |
| `wled/digquad-settings/wled_segments_Digquad_UPDATED.json` | Updated segment definitions reference | Manual apply | Use values to create/verify segments in UI; not directly consumed as `cfg.json`/`presets.json` |
| `wled/digquad-settings/wled_state_machine_presets_Digquad_skeleton.json` | State machine core-state presets (`101-109`) | Optional Yes | Merge/import selected presets into active `presets.json` (do not replace your full preset set blindly) |
| `wled/digquad-settings/wled_state_machine_preset_map.json` | State ID to preset mapping helper | No | Reference only for HA script mapping |
| `wled/digquad-settings/wled_cfg_Dig-Quad-V3.customization` | Human-authored config snapshot/template | No | Reference/archive only |
| `wled/digquad-settings/wled_presets_Dig-Quad-V3.customization` | Human-authored presets snapshot/template | No | Reference/archive only |
| `wled/digquad-settings/wled_preset_50_A1_full_highlight.json` | Example dynamic tray preset | Optional Yes | Merge specific preset into active `presets.json` if using preset-based dynamic layout |
| `wled/digquad-settings/wled_preset_54_B1_full_highlight.json` | Example dynamic tray preset | Optional Yes | Merge specific preset into active `presets.json` if using preset-based dynamic layout |

### Recommended load order

1. Back up current DigQuad (`backup-export.json`, `cfg.json`, `presets.json`).
2. Load `wled_cfg_Digquad.json` (or manually reconcile deltas with your current config).
3. Load `wled_presets_Digquad.json`.
4. If using the HA state machine skeleton, merge in presets from `wled_state_machine_presets_Digquad_skeleton.json` (`101-109`).
5. Validate segment bounds against `wled_segments_Digquad_UPDATED.json`.
6. Reboot and run validation tests.

### Important guardrail

- Treat `.customization` files as repository reference artifacts unless you intentionally convert them into active `cfg.json`/`presets.json` payloads.
- Do not overwrite live `presets.json` with a partial file unless you intend to replace the whole preset store.

## Quick Start Steps

### Step 1: Review the Specifications (15 minutes)

**CRITICAL**: Read these specification files first to understand the system:

1. **Read `digquad-led-segments.md`** - Exact LED counts and GPIO mapping:
   - Total LEDs: 711
   - GPIO 15: Printer Front Door (158 LEDs, range 0-157)
   - GPIO 1: AMS 1 Lid/Spools (140 LEDs, range 158-297)
   - GPIO 3: AMS 2 Lid/Spools (139 LEDs, range 298-436)
   - GPIO 16: AMS 1 Tags (136 LEDs, range 437-572)
   - GPIO 4: AMS 2 Tags (138 LEDs, range 573-710)

2. **Read `light-scenarios.md` (Section 2: LED Function Map)** - Understand what each zone does:
   - Progress bar (door bottom)
   - Status indicators (door left/top)
   - Spool illumination functions
   - Tag functions (color matching, filament %, errors)
   - Hygrometer indicators

3. **Review `light-scenarios.md`** - See all 33+ lighting scenarios:
   - Print lifecycle states
   - Error conditions
   - AMS operations
   - Maintenance modes

4. **Read `README.md`** - Complete overview integrated with specifications

### Step 2: Verify Hardware Requirements (10 minutes)

**LED Strips Required (711 LEDs total):**
- COB 160 LED/m strips for printer door and AMS lids (437 LEDs)
- Mini 2.7mm 160 LED/m strips for AMS tags (274 LEDs)
- See Amazon product links in `digquad-led-segments.md`

**Power Supply:**
- 711 LEDs × 0.06A = 42.66A maximum (full white, worst case)
- Typical usage at 30-50% brightness: 12-21A
- **Recommended**: 15-20A @ 5V power supply with headroom
- Power injection recommended for each GPIO output

**Controller:**
- Digquad LED Controller with 5 available GPIO outputs
- Configure GPIO pins: 15, 1, 3, 16, 4

### Step 3: Install LED Strips (2-3 hours)

Follow the detailed instructions in [docs/wiring-diagram.md](docs/wiring-diagram.md) and use LED specifications from `digquad-led-segments.md`:

1. **Printer Front Door** (GPIO 15, 158 LEDs):
   - COB 160 LED/m strip
   - C-shape layout: bottom (50), left (65), top (43)
   - Functions: Progress bar (bottom), status indicators (left/top)

2. **AMS 1 Lid/Spools** (GPIO 1, 140 LEDs):
   - COB 160 LED/m strip
   - Covers 4 trays with top and bottom sections
   - Functions: Spool illumination, active tray indication, loading animations

3. **AMS 2 Lid/Spools** (GPIO 3, 139 LEDs):
   - COB 160 LED/m strip
   - Similar to AMS 1, includes heating animation support

4. **AMS 1 Tags** (GPIO 16, 136 LEDs):
   - Mini 2.7mm 160 LED/m strip
   - Covers 4 tray tags plus hygrometer
   - Functions: Filament color matching, percentage display, error indication

5. **AMS 2 Tags** (GPIO 4, 138 LEDs):
   - Mini 2.7mm 160 LED/m strip
   - Similar to AMS 1 tags

### Step 4: Configure WLED Controller (30 minutes)

#### Digquad Configuration:
1. Connect to Digquad web interface (http://digquad.local or IP)
2. Go to Config > LED Preferences
3. Configure 5 GPIO outputs with actual LED counts:
   ```
   GPIO 15: 158 LEDs (Printer Door)
   GPIO 1:  140 LEDs (AMS 1 Lid)
   GPIO 3:  139 LEDs (AMS 2 Lid)
   GPIO 16: 136 LEDs (AMS 1 Tags)
   GPIO 4:  138 LEDs (AMS 2 Tags)
   Total:   711 LEDs
   ```
4. Set LED type (WS2812B or SK6812)
5. Save and reboot

### Step 4.5: Create Backup Snapshot (10 minutes)

Before segment edits and preset changes, capture a baseline snapshot:

1. Follow [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md).
2. Export UI backup and save as `backup-export.json`.
3. Download `/cfg.json` and `/presets.json` from `http://<wled-host>/edit`.
4. Store files in:
   - `wled/backups/digquad/YYYY-MM-DD_HHMM/`
   - `wled/backups/magwled/YYYY-MM-DD_HHMM/` (if applicable)
5. Add `NOTES.md` with firmware version and reason for snapshot.

### Step 5: Create Segments (30 minutes)

Create segments based on functional zones (refer to `light-scenarios.md` (Section 2: LED Function Map) for functions):

#### Suggested Segment Organization:
```
Segment 0: Printer Door Bottom (0-49) - Progress bar
Segment 1: Printer Door Left (50-114) - Status
Segment 2: Printer Door Top (115-157) - Status
Segment 3-6: AMS1 Trays (158-297) - By function or tray
Segment 7-10: AMS2 Trays (298-436) - By function or tray  
Segment 11-14: AMS1 Tags (437-572) - By tray + hygrometer
Segment 15: AMS2 Tags (573-710) - Can be further segmented
```

Or organize by functional zones:
- Progress indicators
- Status indicators
- Spool illumination
- Tag identification
- Hygrometer warnings

See `digquad-led-segments.md` for exact LED ranges.

### Step 6: Import Presets (20 minutes)

Import or create presets based on `light-scenarios.md`:

#### Key Preset Categories (33+ total):
1. **Power & Connectivity**: Offline, Idle, Busy
2. **Print Lifecycle**: Heating, Leveling, Printing, Paused, Finished
3. **Error States**: Filament runout, tangle, temperature error
4. **AMS Operations**: Loading, unloading, drying, humidity
5. **Maintenance**: Cooling, chamber light, cleaning
6. **Environmental**: Temperature warnings, power recovery
7. **Aesthetic**: Show mode, night mode, monitoring mode

Reference `light-scenarios.md` for detailed color and effect specifications for each scenario.

### Step 7: Test Everything (30 minutes)

1. Test each GPIO output independently
2. Verify all 711 LEDs light up correctly
3. Test each segment for proper range
4. Try each preset from `light-scenarios.md`
5. Adjust brightness and speed as needed
6. Test power supply under realistic load (not full white)
7. Verify LED functions from `light-scenarios.md` (Section 2: LED Function Map):
   - Progress bar animation (door bottom)
   - Status indicators (door left/top)
   - Spool highlighting
   - Tag color matching
   - Hygrometer warnings

### Step 8: Home Assistant Integration (1 hour)

Follow instructions in [docs/home-assistant-automations.md](docs/home-assistant-automations.md):

1. Add WLED device to Home Assistant
2. Create automations based on `light-scenarios.md`:
   - Map printer states to presets
   - Configure tray selection highlighting
   - Set up progress bar updates
   - Configure error state alerts
   - Set up humidity warnings
3. Test each automation manually
4. Monitor during actual prints

Example key automations:
- **Print Started** → Preset 8 (Printing state)
- **Heating Bed** → Preset 4 (Orange pulse)
- **Print Error** → Preset 10 (Red strobe)
- **Filament Loading** → Preset 17 (Blue chase)
- **Humidity High** → Preset 20 (Red hygrometer)
- **Print Complete** → Preset 11 (Green celebration)

## Common Issues and Solutions

### Issue: LEDs Don't Light Up
- Check power supply (5V, adequate current)
- Verify GPIO pin configuration
- Test with WLED web interface first
- Check ground connections

### Issue: Wrong Colors
- LED type might be wrong (WS2812B vs SK6812)
- RGB order might be wrong (try GRB, BGR, etc.)
- Adjust in Config > LED Preferences

### Issue: Segments Overlap or Don't Work
- Verify start/stop LED numbers
- Check for off-by-one errors
- Ensure no gaps or overlaps
- Segments must be in order

### Issue: Effects Are Choppy
- Reduce FPS in settings
- Simplify effects
- Check power stability
- Reduce active segments

## Power Requirements

Calculate your power needs:
- Total LEDs: 711
- Each LED: ~60mA at full white
- Maximum theoretical: 711 × 0.06A = 42.66A (full white, all LEDs)
- Typical usage at 30-50% brightness: ~12-21A
- **Recommendation**: 15-20A @ 5V power supply with adequate headroom

⚠️ **Important**: 
- Use power injection at each GPIO output for best performance
- Full white at 100% is rarely needed in practice
- Most scenarios use 30-50% brightness with mixed colors
- Test actual power draw during typical usage scenarios

## Safety Checklist

Before first use:
- [ ] Power supply rated for total current draw
- [ ] Proper wire gauge for current (18-22 AWG)
- [ ] All connections secure and insulated
- [ ] LED strips don't interfere with printer mechanics
- [ ] Strips away from hot surfaces
- [ ] Adequate ventilation
- [ ] Tested at full brightness for heat
- [ ] Emergency shutoff accessible

## Next Steps

After basic setup:

1. **Fine-tune Colors**: Adjust preset colors to your preference
2. **Create Custom Effects**: Use WLED's effect library
3. **Add Progress Bar**: Implement the advanced progress bar automation
4. **Sync Controllers**: Enable UDP sync for coordinated effects
5. **Filament Colors**: Match LEDs to actual filament colors using Spoolman data
6. **Add More Presets**: Create presets for specific scenarios
7. **Dashboard**: Add WLED controls to your Home Assistant dashboard

## Preset Quick Reference

Reference `light-scenarios.md` for complete details. Key presets:

### Power & Connectivity
| Preset | Name | Behavior |
|--------|------|----------|
| 1 | Offline | Dim amber on door |
| 2 | Idle | Soft blue breathing |
| 3 | Busy | Medium white, solid |

### Print Lifecycle
| Preset | Name | Behavior |
|--------|------|----------|
| 4 | Heating Bed | Orange pulse |
| 5 | Heating Nozzle | Yellow pulse |
| 6 | Bed Leveling | Blue pulse/chase |
| 7 | Purge Line | Cyan pulse |
| 8 | Printing | Green status, progress bar, filament colors |
| 9 | Paused (User) | Yellow blink |
| 10 | Paused (Error) | Red strobe |
| 11 | Print Finished | Green pulse celebration |

### Error States
| Preset | Name | Behavior |
|--------|------|----------|
| 12 | Filament Runout | Red on affected tray |
| 13 | Filament Jam | Orange strobe |
| 14 | AMS Error | Purple pulse |
| 15 | Temperature Error | Red strobe |

### AMS Operations
| Preset | Name | Behavior |
|--------|------|----------|
| 17 | Loading | Blue chase |
| 18 | Unloading | Teal chase |
| 19 | Drying Mode | Warm amber |
| 20 | Humidity High | Red hygrometer |
| 21 | Humidity Normal | White hygrometer |

See `light-scenarios.md` for all 33+ scenarios with detailed specifications.

## Automation Logic Summary

The automation system maps printer states to lighting scenarios (see `light-scenarios.md`):

1. **Print State Changes**: Trigger presets based on printer stage
2. **Active Tray Changes**: Highlight currently active AMS tray/tag
3. **Print Progress**: Update bottom segment progress bar (0-100%)
4. **Error Detection**: Flash red when HMS errors or filament issues occur
5. **AMS Operations**: Animate loading/unloading, show humidity warnings
6. **Manual Control**: Dashboard buttons for maintenance and testing

Key sensor mappings:
- `sensor.bambu_lab_x1c_current_stage` → Print lifecycle presets
- `sensor.bambu_lab_x1c_active_tray` → Tray/tag highlighting
- `sensor.bambu_lab_x1c_print_progress` → Progress bar percentage
- `sensor.bambu_lab_x1c_hms_errors` → Error state presets
- AMS humidity sensors → Hygrometer warnings

## Maintenance

### Weekly
- Check that all LEDs are working
- Verify automations are triggering correctly

### Monthly
- Clean LED strips with compressed air
- Check wire connections
- Verify power supply temperature

### As Needed
- Update WLED firmware
- Backup configurations
- Add new presets or effects

## Support and Resources

- **WLED Official**: https://kno.wled.ge/
- **Home Assistant WLED**: https://www.home-assistant.io/integrations/wled/
- **Bambu Lab HA Integration**: https://github.com/greghesp/ha-bambulab
- **This Repository**: https://github.com/rsocko/hass-bambulab-config

## Customization Tips

### Reference Specifications
- **LED Counts**: See `digquad-led-segments.md` for exact ranges
- **Functions**: See `light-scenarios.md` (Section 2: LED Function Map) for zone purposes
- **Scenarios**: See `light-scenarios.md` for all behaviors

### Change Colors
Edit preset files or use WLED interface to adjust colors per scenario.

### Add Effects
WLED has 100+ built-in effects. Try different ones for each preset!

### Progress Visualization
The bottom printer segment (0-50 LEDs) is dedicated for progress visualization:
- Read print percentage from Home Assistant
- Calculate LEDs to light: (percentage / 100) × 50
- Update LED colors via WLED API
- Create moving gradient or solid progress bar

### Filament-Matched Colors
Integrate with Spoolman:
- Read filament color from Spoolman entity
- Convert hex color to RGB
- Set tag segment color via WLED API
- Makes it easy to identify which spool is active!

### Function-Specific Features
Based on `light-scenarios.md` (Section 2: LED Function Map):
- **Door Bottom**: Animated progress with pause detection
- **Door Left/Top**: Pulsing green when printing, flashing red on error
- **Tag Top**: Color-match filament, show current use
- **Tag Bottom**: % filament left, desiccant warning, error indication
- **Hygrometer**: Humidity level warnings (>X% triggers red)

## Troubleshooting Checklist

If something doesn't work:

1. [ ] Is power supply adequate and connected?
2. [ ] Are all ground connections made?
3. [ ] Is WiFi configured correctly on controllers?
4. [ ] Can you access WLED web interface?
5. [ ] Are LED counts correct in configuration?
6. [ ] Are segments created with correct start/stop?
7. [ ] Do presets exist with correct IDs?
8. [ ] Are Home Assistant entity names correct?
9. [ ] Are automations enabled?
10. [ ] Check Home Assistant logs for errors

## Getting Help

If you encounter issues:

1. Check WLED web interface - does it work there?
2. Check Home Assistant logs
3. Verify entity IDs match your setup
4. Test presets manually before automating
5. Open an issue in this repository with details

## Contributing

Found a bug or have an improvement?
- Open an issue
- Submit a pull request
- Share your custom presets or automations

## Final Notes

- **All specifications are documented**: See `digquad-led-segments.md` for exact LED counts (711 total)
- **Functions are defined**: See `light-scenarios.md` (Section 2: LED Function Map) for what each zone does
- **Scenarios are cataloged**: See `light-scenarios.md` for all 33+ lighting behaviors
- **Test incrementally**: Verify each GPIO output before moving to the next
- **Start with simple presets**: Add complexity after basics work
- **Keep backups**: Save working configurations before changes
- **Monitor power**: Use realistic scenarios, not full white at 100%
- **Have fun customizing**: The system is designed to be flexible!

## Estimated Time Investment

- **Reading Specifications**: 30 minutes
- **Planning & Preparation**: 1 hour
- **Physical Installation**: 2-3 hours
- **WLED Configuration**: 1-2 hours
- **Home Assistant Setup**: 1-2 hours
- **Testing & Refinement**: 2-3 hours
- **Total**: 8-12 hours for complete setup

Good luck with your installation! 🎉

## Quick Reference Links

- 📊 [digquad-led-segments.md](digquad-led-segments.md) - LED specifications
- 🎯 [LED Function Map](light-scenarios.md#2-led-function-map-consolidated) - Zone functions
- 🎨 [light-scenarios.md](light-scenarios.md) - Scenario catalog
- 📖 [README.md](README.md) - Complete documentation
- 🔌 [docs/wiring-diagram.md](docs/wiring-diagram.md) - Installation guide
- 🏠 [docs/home-assistant-automations.md](docs/home-assistant-automations.md) - Automation examples

