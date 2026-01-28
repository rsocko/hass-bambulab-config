# Quick Start Guide - WLED Bambu Lab Printer Lighting

This guide will help you get started quickly with your WLED LED strip configuration for Bambu Lab printer and dual AMS setup.

## What's Included

This configuration package includes:

1. **Main README** (`README.md`) - Complete overview and segment allocation
2. **Wiring Diagram** (`docs/wiring-diagram.md`) - Detailed installation instructions
3. **Home Assistant Automations** (`docs/home-assistant-automations.md`) - Integration examples
4. **Digquad Configuration**:
   - `digquad-settings/wled_cfg_Digquad.json` - Controller configuration
   - `digquad-settings/wled_presets_Digquad.json` - 14 presets for various scenarios
   - `digquad-settings/wled_segments_Digquad.json` - Segment layout reference
5. **MagWLED Configuration**:
   - `magwled-settings/wled_cfg_MagWLED.json` - Existing controller config
   - `magwled-settings/wled_presets_MagWLED_updated.json` - Updated presets for AMS 2 tags
   - `magwled-settings/wled_segments_MagWLED.json` - Segment layout reference

## Quick Start Steps

### Step 1: Review the Design (5 minutes)

1. Read `README.md` to understand the overall design
2. Review segment allocation to see how segments are distributed
3. Note that we use 15/16 segments on Digquad and 8/16 on MagWLED

### Step 2: Measure Your LED Strips (30 minutes)

**CRITICAL**: Before installing, you must measure your actual LED counts!

1. Connect each strip to a controller one at a time
2. Count the exact number of LEDs in each strip
3. For segmented strips (like Strip 2), note where each section begins/ends
4. Document your measurements in a file

Example:
```
Strip 1: 30 LEDs (0-29)
Strip 2: 90 LEDs total
  - Bottom: 30 LEDs (30-59)
  - Left: 30 LEDs (60-89)
  - Top: 30 LEDs (90-119)
... etc.
```

### Step 3: Install LED Strips (1-2 hours)

Follow the detailed instructions in `docs/wiring-diagram.md`:

1. **Printer Interior** (Strip 1): Simple single strip in lid
2. **Printer Front** (Strip 2): C-shape bottom-left-top
3. **AMS 1 Lid** (Strip 3): Reverse C around spools
4. **AMS 1 Tags** (Strip 4): Across tag holders
5. **AMS 2 Lid** (Strip 5): Same as Strip 3
6. **AMS 2 Tags** (Strip 6): Same as Strip 4 but with top/bottom paths

### Step 4: Update Configuration Files (15 minutes)

1. Open `wled_cfg_Digquad.json`
2. Update LED counts in the `hw.led.ins[]` sections:
   ```json
   {
     "start": 0,
     "len": YOUR_ACTUAL_LED_COUNT,
     ...
   }
   ```
3. Update total LED count in `hw.led.total`
4. Save the file

5. Repeat for `wled_cfg_MagWLED.json` if needed

### Step 5: Configure WLED Controllers (30 minutes)

#### Digquad:
1. Connect to Digquad web interface (http://digquad.local or IP)
2. Go to Config > LED Preferences
3. Upload or manually enter configuration from `wled_cfg_Digquad.json`
4. Save and reboot

#### MagWLED:
1. Connect to MagWLED web interface
2. Update configuration if needed
3. Save and reboot

### Step 6: Create Segments (20 minutes)

After basic configuration, manually create segments in WLED interface:

#### Digquad Segments (reference: `wled_segments_Digquad.json`):
1. Segment 0: Interior (0-29 or your count)
2. Segment 1: Printer Bottom (30-59)
3. Segment 2: Printer Left (60-89)
4. Segment 3: Printer Top (90-119)
5. Segments 4-7: AMS1 Spools A1-A4
6. Segments 8-11: AMS1 Tags A1-A4
7. Segments 12-15: AMS2 Spools B1-B4

#### MagWLED Segments (reference: `wled_segments_MagWLED.json`):
1. Segments 0-3: AMS2 Tags B1-B4 Top
2. Segments 4-7: AMS2 Tags B1-B4 Bottom

Or use simplified 4-segment layout (see alternative in JSON file)

### Step 7: Import Presets (15 minutes)

#### Digquad Presets:
1. In WLED interface, go to Config > Presets
2. Import from `wled_presets_Digquad.json` or create manually:
   - Preset 1: Normal Printing
   - Preset 2: Print Error (red flashing)
   - Preset 3: Print Complete (green celebration)
   - Preset 4: Idle/Standby (dim blue breathing)
   - Preset 5: Maintenance Mode (bright white)
   - Preset 6: AMS Loading
   - Presets 7-10: Active Spool A1-A4
   - Presets 11-14: Active Spool B1-B4

#### MagWLED Presets:
1. Import from `wled_presets_MagWLED_updated.json`
2. Key presets:
   - Preset 1: Normal Printing
   - Preset 2: Idle/Standby
   - Preset 3: Maintenance
   - Presets 4-7: Active Tags B1-B4
   - Presets 8-11: Upcoming Tags B1-B4

### Step 8: Test Everything (30 minutes)

1. Test each preset manually in WLED interface
2. Verify all segments light up correctly
3. Check colors and effects
4. Adjust brightness and speed as needed
5. Test power supply under full load

### Step 9: Home Assistant Integration (1 hour)

Follow instructions in `docs/home-assistant-automations.md`:

1. Add both WLED devices to Home Assistant
2. Copy example automations to your configuration
3. Adjust entity names to match your setup
4. Test each automation manually
5. Monitor for proper operation during actual prints

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
- Each LED: ~60mA at full white
- Example with 280 LEDs: 280 × 0.06A = 16.8A maximum
- Typical usage at 50% brightness: ~8-9A
- **Recommendation**: 10-12A 5V power supply

⚠️ **Important**: For strips over 100 LEDs, use power injection at multiple points!

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

### Digquad Presets
| Preset | Name | Use Case |
|--------|------|----------|
| 1 | Normal Printing | Active print in progress |
| 2 | Print Error | HMS error detected |
| 3 | Print Complete | Successful completion |
| 4 | Idle/Standby | Printer not active |
| 5 | Maintenance | Working on printer |
| 6 | AMS Loading | Loading filament |
| 7-10 | Active Spool A1-A4 | Highlight active AMS1 spool |
| 11-14 | Active Spool B1-B4 | Highlight active AMS2 spool |

### MagWLED Presets
| Preset | Name | Use Case |
|--------|------|----------|
| 1 | Normal Printing | Active print |
| 2 | Idle/Standby | Not printing |
| 3 | Maintenance | Work mode |
| 4-7 | Active Tag B1-B4 | Currently active spool |
| 8-11 | Upcoming Tag B1-B4 | Spool used later in print |

## Automation Logic Summary

The automation system works as follows:

1. **Print State Changes**: Trigger different presets based on printer stage
2. **Active Tray Changes**: Highlight the currently active AMS spool
3. **Print Progress**: Update bottom segment as progress bar
4. **Error Detection**: Flash red when HMS errors occur
5. **Manual Control**: Dashboard buttons for maintenance and testing

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

### Change Colors
Edit preset JSON files before uploading, or use WLED interface after import.

### Add Effects
WLED has 100+ built-in effects. Try different ones for each preset!

### Sync Both Controllers
Enable UDP sync to have both controllers run the same effect.

### Progress Visualization
The bottom printer segment (Segment 1) is perfect for progress visualization:
- Use Home Assistant to read print percentage
- Update LED colors via WLED API
- Create a moving gradient or solid progress bar

### Filament-Matched Colors
If you use Spoolman:
- Read filament color from Spoolman entity
- Convert to RGB
- Set segment color via WLED API
- Makes it easy to identify which spool is active!

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

- **LED counts in configs are EXAMPLES** - you must measure yours!
- **Test everything before a long print**
- **Start with simple presets, add complexity later**
- **Keep backups of your working configurations**
- **Have fun customizing your setup!**

## Estimated Time Investment

- **Planning & Measuring**: 1 hour
- **Physical Installation**: 2-3 hours
- **WLED Configuration**: 1-2 hours
- **Home Assistant Setup**: 1-2 hours
- **Testing & Refinement**: 2-3 hours
- **Total**: 7-11 hours for complete setup

Good luck with your installation! 🎉
