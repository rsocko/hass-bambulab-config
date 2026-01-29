# WLED Configuration - File Index

This index helps you navigate all the WLED configuration files and documentation.

## 🆕 NEW: Preset-Based Segment Configuration

**Advanced technique unlocked!** Work around the 16-segment limitation by using WLED presets to save different segment layouts!

### Core Documents
- **[PRESET_BASED_SEGMENTS.md](PRESET_BASED_SEGMENTS.md)** - Comprehensive guide (17KB)
- **[QUICK_START_PRESET_BASED.md](QUICK_START_PRESET_BASED.md)** - Quick start guide (9KB)
- **[docs/preset_based_visual_guide.md](docs/preset_based_visual_guide.md)** - Visual guide with diagrams (18KB)
- **[docs/ha_automation_preset_based.md](docs/ha_automation_preset_based.md)** - Home Assistant automation examples (18KB)

### Example Configurations
- **[digquad-settings/wled_preset_50_A1_full_highlight.json](digquad-settings/wled_preset_50_A1_full_highlight.json)** - Preset 50 (A1)
- **[digquad-settings/wled_preset_54_B1_full_highlight.json](digquad-settings/wled_preset_54_B1_full_highlight.json)** - Preset 54 (B1)

**Key Benefit**: Highlight BOTH top AND bottom of active tag LEDs with filament color!

---

## 📁 Directory Structure

```
wled/
├── README.md                              # Main overview and design document
├── QUICK_START.md                         # Fast-track setup guide
├── INDEX.md                               # This file - navigation guide
│
├── digquad-led-segments.md                # ⭐ ACTUAL LED specifications (711 LEDs)
├── led-functions.md                       # ⭐ LED function specifications by zone
├── light-scenarios.md                     # ⭐ Complete scenario catalog (33+ scenarios)
│
├── digquad-settings/                      # Digquad controller files
│   ├── wled_cfg_Digquad.json             # Controller configuration
│   ├── wled_presets_Digquad.json         # Preset definitions
│   └── wled_segments_Digquad.json        # Segment layout reference
│
└── docs/                                  # Detailed documentation
    ├── wiring-diagram.md                  # Physical installation guide
    ├── visual-installation-guide.md       # ASCII art diagrams
    ├── segment-reference.md               # Quick reference card
    └── home-assistant-automations.md      # HA integration examples
```

## ⭐ New Specification Files

### Core Specifications (READ THESE FIRST!)
| File | Purpose | When to Read |
|------|---------|--------------|
| [QUICK_REFERENCE.md](QUICK_REFERENCE.md) | **One-page quick reference card** | Start here for overview |
| [SUMMARY.md](SUMMARY.md) | **High-level summary of design refinement** | After quick reference |
| [CONTROLLER_ALLOCATION_RECOMMENDATION.md](CONTROLLER_ALLOCATION_RECOMMENDATION.md) | **Controller allocation strategy and segment limitation analysis** | Before any configuration changes |
| [PRESET_SPECIFICATION.md](PRESET_SPECIFICATION.md) | **Complete specification of 31+ presets with active tray scenarios** | During preset creation |
| [PHASED_IMPLEMENTATION_GUIDE.md](PHASED_IMPLEMENTATION_GUIDE.md) | **7-phase implementation plan with validation checkpoints** | During implementation |
| [digquad-led-segments.md](digquad-led-segments.md) | **Exact LED counts and ranges for all 711 LEDs** | Before any configuration |
| [led-functions.md](led-functions.md) | **Specific function of each LED zone** | During planning and configuration |
| [light-scenarios.md](light-scenarios.md) | **Complete catalog of 33+ lighting scenarios** | For preset creation and automation |

## 🚀 Start Here

### For First-Time Users
1. **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - ⭐ **START HERE!** One-page overview
2. **[SUMMARY.md](SUMMARY.md)** - High-level summary of design refinement
3. **[CONTROLLER_ALLOCATION_RECOMMENDATION.md](CONTROLLER_ALLOCATION_RECOMMENDATION.md)** - Understand segment limitations and controller allocation
4. **[PRESET_SPECIFICATION.md](PRESET_SPECIFICATION.md)** - Review all 31+ preset definitions
5. **[PHASED_IMPLEMENTATION_GUIDE.md](PHASED_IMPLEMENTATION_GUIDE.md)** - Follow 7-phase implementation plan
6. **[digquad-led-segments.md](digquad-led-segments.md)** - Understand actual LED counts (711 total)
7. **[led-functions.md](led-functions.md)** - Learn what each LED zone does
8. **[light-scenarios.md](light-scenarios.md)** - See all possible lighting scenarios
9. **[QUICK_START.md](QUICK_START.md)** - Step-by-step setup guide
10. **[README.md](README.md)** - Complete overview and integration guide
11. **[docs/visual-installation-guide.md](docs/visual-installation-guide.md)** - See ASCII diagrams of strip layout

### For Experienced Users
1. **[digquad-led-segments.md](digquad-led-segments.md)** - Quick reference for LED ranges
2. **[docs/segment-reference.md](docs/segment-reference.md)** - Segment IDs and mappings
3. **Configuration Files** - Jump directly to JSON configs in controller directories

## 📚 Document Guide

### Specification Documents (New!)

| File | Purpose | When to Read |
|------|---------|--------------|
| [CONTROLLER_ALLOCATION_RECOMMENDATION.md](CONTROLLER_ALLOCATION_RECOMMENDATION.md) | Controller allocation strategy, segment limitation analysis, and alternatives | **BEFORE configuration** |
| [PRESET_SPECIFICATION.md](PRESET_SPECIFICATION.md) | Complete specification of 31+ presets with all active tray scenarios | During preset creation |
| [PHASED_IMPLEMENTATION_GUIDE.md](PHASED_IMPLEMENTATION_GUIDE.md) | 7-phase implementation plan with validation and rollback procedures | During implementation |
| [digquad-led-segments.md](digquad-led-segments.md) | Exact LED counts, GPIO pins, and LED ranges for all 711 LEDs | **BEFORE configuration** |
| [led-functions.md](led-functions.md) | Detailed function specifications for each LED zone | During planning |
| [light-scenarios.md](light-scenarios.md) | Complete catalog of 33+ lighting scenarios with behaviors | For automation design |

### Core Documentation

| File | Purpose | When to Read |
|------|---------|--------------|
| [README.md](README.md) | Complete overview of design, updated with actual specifications | Before starting |
| [QUICK_START.md](QUICK_START.md) | Condensed setup guide with clear steps | During installation |

### Installation Guides

| File | Purpose | When to Read |
|------|---------|--------------|
| [docs/wiring-diagram.md](docs/wiring-diagram.md) | Detailed wiring instructions, power calculations, safety | During physical install |
| [docs/visual-installation-guide.md](docs/visual-installation-guide.md) | ASCII art diagrams showing strip placement | During physical install |

### Reference Materials

| File | Purpose | When to Read |
|------|---------|--------------|
| [docs/segment-reference.md](docs/segment-reference.md) | Quick lookup tables for segments, presets, colors | During configuration & troubleshooting |

### Integration

| File | Purpose | When to Read |
|------|---------|--------------|
| [docs/home-assistant-automations.md](docs/home-assistant-automations.md) | Example HA automations and integrations | After WLED setup complete |

### Configuration Files

| File | Purpose | When to Use |
|------|---------|-------------|
| [digquad-settings/wled_cfg_Digquad.json](digquad-settings/wled_cfg_Digquad.json) | Digquad controller base config | Upload to Digquad |
| [digquad-settings/wled_presets_Digquad.json](digquad-settings/wled_presets_Digquad.json) | 14 presets for printer/AMS control | Import to Digquad |
| [digquad-settings/wled_segments_Digquad.json](digquad-settings/wled_segments_Digquad.json) | Original segment definitions (reference only) | For manual segment creation |
| [digquad-settings/wled_segments_Digquad_UPDATED.json](digquad-settings/wled_segments_Digquad_UPDATED.json) | **UPDATED segment definitions (16 segments, optimized)** | **Recommended for new installations** |
| [magwled-settings/wled_cfg_MagWLED.json](magwled-settings/wled_cfg_MagWLED.json) | MagWLED controller config (legacy) | Upload to MagWLED if used |
| [magwled-settings/wled_presets_MagWLED_updated.json](magwled-settings/wled_presets_MagWLED_updated.json) | Updated presets for AMS 2 tags (legacy) | Import to MagWLED if used |
| [magwled-settings/wled_segments_MagWLED.json](magwled-settings/wled_segments_MagWLED.json) | Segment definitions (legacy, reference only) | For manual segment creation |

## 🎯 Use Case Guide

### "I want to know the exact LED specifications"
→ Read **[digquad-led-segments.md](digquad-led-segments.md)** (711 LEDs total)

### "I need controller allocation advice"
→ Read **[CONTROLLER_ALLOCATION_RECOMMENDATION.md](CONTROLLER_ALLOCATION_RECOMMENDATION.md)** (MagWLED vs DigQuad)

### "I want to understand segment limitations"
→ Read **[CONTROLLER_ALLOCATION_RECOMMENDATION.md](CONTROLLER_ALLOCATION_RECOMMENDATION.md)** (16-segment limit analysis)

### "I want to see all preset definitions"
→ Read **[PRESET_SPECIFICATION.md](PRESET_SPECIFICATION.md)** (31+ presets with active tray scenarios)

### "I need a phased implementation plan"
→ Read **[PHASED_IMPLEMENTATION_GUIDE.md](PHASED_IMPLEMENTATION_GUIDE.md)** (7 phases with validation)

### "I want to understand what each LED zone does"
→ Read **[led-functions.md](led-functions.md)**

### "I want to see all possible lighting scenarios"
→ Read **[light-scenarios.md](light-scenarios.md)** (33+ scenarios)

### "I want to install LED strips on my printer"
→ Start with **[QUICK_START.md](QUICK_START.md)**

### "I need to see where each LED strip goes"
→ Read **[docs/visual-installation-guide.md](docs/visual-installation-guide.md)**

### "I need to wire up the controllers"
→ Read **[docs/wiring-diagram.md](docs/wiring-diagram.md)**

### "I need to configure WLED controllers"
→ Use config files in **digquad-settings/**

### "I need to know what segment ID controls what"
→ Check **[docs/segment-reference.md](docs/segment-reference.md)**

### "I want to integrate with Home Assistant"
→ Read **[docs/home-assistant-automations.md](docs/home-assistant-automations.md)**

### "I'm troubleshooting an issue"
→ Check **[QUICK_START.md](QUICK_START.md)** (Common Issues section)  
→ Check **[docs/segment-reference.md](docs/segment-reference.md)** (Troubleshooting table)

## 📊 Configuration Summary

### System Overview
- **Total LEDs**: 711
- **Controller**: Digquad (5 GPIO outputs)
- **LED Types**: COB 160 LED/m and Mini 2.7mm 160 LED/m

### LED Distribution by GPIO
1. **GPIO 15**: Printer Front Door - 158 LEDs (0-157)
2. **GPIO 1**: AMS 1 Lid/Spools - 140 LEDs (158-297)
3. **GPIO 3**: AMS 2 Lid/Spools - 139 LEDs (298-436)
4. **GPIO 16**: AMS 1 Tags + Hygrometer - 136 LEDs (437-572)
5. **GPIO 4**: AMS 2 Tags + Hygrometer - 138 LEDs (573-710)

### Key Functional Zones
- **Progress Bar**: Printer door bottom (50 LEDs)
- **Status Indicators**: Printer door left/top (108 LEDs)
- **Spool Lighting**: AMS 1 & 2 lids (279 LEDs)
- **Tag Lighting**: AMS 1 & 2 tags (274 LEDs)
- **Hygrometer Indicators**: Included in tag lighting

### Scenarios
- **33+ lighting scenarios** defined in [light-scenarios.md](light-scenarios.md)
- Covers all printer states, errors, AMS operations, and maintenance modes

## 🔧 Customization

### Before Installation
- **LED Specifications**: All specifications are now documented in [digquad-led-segments.md](digquad-led-segments.md)
- **Actual Measurements**: 711 LEDs total across 5 GPIO outputs
- **Review Functions**: Check [led-functions.md](led-functions.md) to understand each zone
- **Plan Scenarios**: Review [light-scenarios.md](light-scenarios.md) for preset planning

### After Installation
- **Colors**: Adjust in preset files or WLED interface
- **Effects**: Try different WLED built-in effects
- **Brightness**: Tune to your preference
- **Automations**: Customize Home Assistant automations based on [light-scenarios.md](light-scenarios.md)
- **Segments**: Organize based on functional zones from [led-functions.md](led-functions.md)

## 📝 Checklist

Use this to track your progress:

- [ ] Read CONTROLLER_ALLOCATION_RECOMMENDATION.md (allocation strategy)
- [ ] Read PRESET_SPECIFICATION.md (31+ preset definitions)
- [ ] Read PHASED_IMPLEMENTATION_GUIDE.md (implementation plan)
- [ ] Read digquad-led-segments.md (LED specifications)
- [ ] Read led-functions.md (function specifications)
- [ ] Read light-scenarios.md (scenario catalog)
- [ ] Read QUICK_START.md
- [ ] Read README.md for design overview
- [ ] Obtained LED strips (711 LEDs total)
- [ ] Installed Printer Front Door LEDs (GPIO 15, 158 LEDs)
- [ ] Installed AMS 1 Lid LEDs (GPIO 1, 140 LEDs)
- [ ] Installed AMS 2 Lid LEDs (GPIO 3, 139 LEDs)
- [ ] Installed AMS 1 Tag LEDs (GPIO 16, 136 LEDs)
- [ ] Installed AMS 2 Tag LEDs (GPIO 4, 138 LEDs)
- [ ] **Moved Interior Lid Light from MagWLED to DigQuad**
- [ ] Connected power supply (15-20A @ 5V recommended)
- [ ] Configured Digquad controller with UPDATED segment definitions
- [ ] Created 16 optimized segments (merged front door, combined backgrounds)
- [ ] Imported/created presets from PRESET_SPECIFICATION.md
- [ ] Tested all segments
- [ ] Added to Home Assistant
- [ ] Created automations for active tray scenarios
- [ ] Tested with actual print
- [ ] Documented final configuration

## 🆘 Getting Help

### Troubleshooting Resources
1. **[QUICK_START.md](QUICK_START.md)** - Common issues section
2. **[docs/segment-reference.md](docs/segment-reference.md)** - Troubleshooting quick reference
3. **[docs/wiring-diagram.md](docs/wiring-diagram.md)** - Troubleshooting guide section

### External Resources
- **WLED Documentation**: https://kno.wled.ge/
- **WLED GitHub**: https://github.com/Aircoookie/WLED
- **Home Assistant WLED**: https://www.home-assistant.io/integrations/wled/
- **Bambu Lab HA Integration**: https://github.com/greghesp/ha-bambulab

### Repository
- **Issues**: https://github.com/rsocko/hass-bambulab-config/issues
- **Discussions**: Share your setup and ask questions

## 🎓 Learning Path

### Beginner
1. Read [CONTROLLER_ALLOCATION_RECOMMENDATION.md](CONTROLLER_ALLOCATION_RECOMMENDATION.md) - Understand segment limitations
2. Read [PRESET_SPECIFICATION.md](PRESET_SPECIFICATION.md) - Review preset definitions
3. Read [PHASED_IMPLEMENTATION_GUIDE.md](PHASED_IMPLEMENTATION_GUIDE.md) - Start with Phase 1
4. Read [digquad-led-segments.md](digquad-led-segments.md) - Understand LED layout
5. Read [led-functions.md](led-functions.md) - Learn zone functions
6. Read [light-scenarios.md](light-scenarios.md) - See all scenarios
7. Follow [QUICK_START.md](QUICK_START.md) - Setup guide
8. Use [docs/visual-installation-guide.md](docs/visual-installation-guide.md) - Visual reference

### Intermediate
1. Review [README.md](README.md) for complete design
2. Study [docs/wiring-diagram.md](docs/wiring-diagram.md) for details
3. Create segments based on [led-functions.md](led-functions.md)
4. Configure presets from [light-scenarios.md](light-scenarios.md)

### Advanced
1. Read [docs/home-assistant-automations.md](docs/home-assistant-automations.md)
2. Map scenarios from [light-scenarios.md](light-scenarios.md) to automations
3. Implement progress bar visualization (door bottom)
4. Add filament color matching (from Spoolman)
5. Configure humidity warnings (hygrometer LEDs)

## 📌 Quick Links

### Most Important Files
- 🎯 [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - **START HERE!** One-page overview
- 📄 [SUMMARY.md](SUMMARY.md) - High-level summary
- ⭐ [CONTROLLER_ALLOCATION_RECOMMENDATION.md](CONTROLLER_ALLOCATION_RECOMMENDATION.md) - Allocation strategy & limitations
- ⭐ [PRESET_SPECIFICATION.md](PRESET_SPECIFICATION.md) - 31+ preset definitions
- ⭐ [PHASED_IMPLEMENTATION_GUIDE.md](PHASED_IMPLEMENTATION_GUIDE.md) - 7-phase implementation
- ⭐ [digquad-led-segments.md](digquad-led-segments.md) - LED specifications (711 LEDs)
- ⭐ [led-functions.md](led-functions.md) - Zone functions
- ⭐ [light-scenarios.md](light-scenarios.md) - Scenario catalog (33+)
- 🚀 [QUICK_START.md](QUICK_START.md) - Setup guide
- 📖 [README.md](README.md) - Full documentation
- 🔌 [docs/wiring-diagram.md](docs/wiring-diagram.md) - Wiring guide
- 📋 [docs/segment-reference.md](docs/segment-reference.md) - Quick reference

### Configuration Files
- ⚙️ [digquad-settings/wled_cfg_Digquad.json](digquad-settings/wled_cfg_Digquad.json)
- 🎨 [digquad-settings/wled_presets_Digquad.json](digquad-settings/wled_presets_Digquad.json)
- ✨ [digquad-settings/wled_segments_Digquad_UPDATED.json](digquad-settings/wled_segments_Digquad_UPDATED.json) - **Recommended**

## 💡 Tips

- **Read specifications first** - digquad-led-segments.md has exact LED counts
- **Understand functions** - led-functions.md explains what each zone does
- **Plan scenarios** - light-scenarios.md defines all 33+ lighting behaviors
- **Bookmark this file** for easy navigation
- **Print the segment reference** for quick lookup during configuration
- **Take photos** during installation for future reference
- **Backup configurations** before making changes
- **Test incrementally** - one GPIO output at a time

## 📅 Revision History

- **v1.1** (2024): Added comprehensive specifications
  - Added digquad-led-segments.md with exact LED counts (711 total)
  - Added led-functions.md with zone function specifications
  - Added light-scenarios.md with 33+ lighting scenarios
  - Updated all documentation to reference actual specifications
  - Consolidated to single Digquad controller (5 GPIO outputs)
  
- **v1.0** (2024): Initial complete WLED configuration package
  - 2 controller setup (Digquad + MagWLED)
  - 6 LED strips
  - 24 total segments (16 + 8)
  - 25 presets (14 + 11)
  - Complete documentation suite

---

**Ready to get started?** → Open [QUICK_REFERENCE.md](QUICK_REFERENCE.md) first, then [PHASED_IMPLEMENTATION_GUIDE.md](PHASED_IMPLEMENTATION_GUIDE.md) now! 🚀
