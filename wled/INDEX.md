# WLED Configuration - File Index

This index helps you navigate all the WLED configuration files and documentation.

## 📁 Directory Structure

```
wled/
├── README.md                              # Main overview and design document
├── QUICK_START.md                         # Fast-track setup guide
├── INDEX.md                               # This file - navigation guide
│
├── digquad-settings/                      # Digquad controller files
│   ├── wled_cfg_Digquad.json             # Controller configuration
│   ├── wled_presets_Digquad.json         # 14 preset definitions
│   └── wled_segments_Digquad.json        # Segment layout reference
│
├── magwled-settings/                      # MagWLED controller files
│   ├── wled_cfg_MagWLED.json             # Controller configuration
│   ├── wled_presets_MagWLED.json         # Original presets
│   ├── wled_presets_MagWLED_updated.json # Updated presets for AMS 2
│   └── wled_segments_MagWLED.json        # Segment layout reference
│
└── docs/                                  # Detailed documentation
    ├── wiring-diagram.md                  # Physical installation guide
    ├── visual-installation-guide.md       # ASCII art diagrams
    ├── segment-reference.md               # Quick reference card
    └── home-assistant-automations.md      # HA integration examples
```

## 🚀 Start Here

### For First-Time Users
1. **[QUICK_START.md](QUICK_START.md)** - Step-by-step setup guide (READ THIS FIRST!)
2. **[README.md](README.md)** - Understand the overall design and requirements
3. **[docs/visual-installation-guide.md](docs/visual-installation-guide.md)** - See ASCII diagrams of strip layout

### For Experienced Users
1. **[docs/segment-reference.md](docs/segment-reference.md)** - Quick lookup of segment IDs and mappings
2. **Configuration Files** - Jump directly to JSON configs in controller directories

## 📚 Document Guide

### Core Documentation

| File | Purpose | When to Read |
|------|---------|--------------|
| [README.md](README.md) | Complete overview of design, segment allocation, and hardware setup | Before starting |
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
| [digquad-settings/wled_segments_Digquad.json](digquad-settings/wled_segments_Digquad.json) | Segment definitions (reference only) | For manual segment creation |
| [magwled-settings/wled_cfg_MagWLED.json](magwled-settings/wled_cfg_MagWLED.json) | MagWLED controller config | Upload to MagWLED |
| [magwled-settings/wled_presets_MagWLED_updated.json](magwled-settings/wled_presets_MagWLED_updated.json) | Updated presets for AMS 2 tags | Import to MagWLED |
| [magwled-settings/wled_segments_MagWLED.json](magwled-settings/wled_segments_MagWLED.json) | Segment definitions (reference only) | For manual segment creation |

## 🎯 Use Case Guide

### "I want to install LED strips on my printer"
→ Start with **[QUICK_START.md](QUICK_START.md)**

### "I need to see where each LED strip goes"
→ Read **[docs/visual-installation-guide.md](docs/visual-installation-guide.md)**

### "I need to wire up the controllers"
→ Read **[docs/wiring-diagram.md](docs/wiring-diagram.md)**

### "I need to configure WLED controllers"
→ Use config files in **digquad-settings/** and **magwled-settings/**

### "I need to know what segment ID controls what"
→ Check **[docs/segment-reference.md](docs/segment-reference.md)**

### "I want to integrate with Home Assistant"
→ Read **[docs/home-assistant-automations.md](docs/home-assistant-automations.md)**

### "I'm troubleshooting an issue"
→ Check **[QUICK_START.md](QUICK_START.md)** (Common Issues section)  
→ Check **[docs/segment-reference.md](docs/segment-reference.md)** (Troubleshooting table)

## 📊 Configuration Summary

### Controllers
- **Digquad**: 5 LED strips, 15 segments, ~280 LEDs
- **MagWLED**: 1 LED strip, 8 segments, ~80 LEDs

### LED Strips
1. **Strip 1**: Printer interior (1 segment)
2. **Strip 2**: Printer front C-shape (3 segments)
3. **Strip 3**: AMS 1 lid spools (4 segments)
4. **Strip 4**: AMS 1 tags (4 segments)
5. **Strip 5**: AMS 2 lid spools (4 segments)
6. **Strip 6**: AMS 2 tags (8 segments)

### Presets

#### Digquad (14 presets)
- General: Normal Printing, Print Error, Print Complete, Idle, Maintenance, AMS Loading
- Per-Spool: Active Spool A1-A4, Active Spool B1-B4

#### MagWLED (11 presets)
- General: Normal Printing, Idle, Maintenance
- Per-Tag: Active Tag B1-B4, Upcoming Tag B1-B4

## 🔧 Customization

### Before Installation
- **LED Counts**: All LED counts in config files are EXAMPLES
- **Measure First**: Count exact LEDs in your strips before configuring
- **Update JSONs**: Modify config files with your actual measurements

### After Installation
- **Colors**: Adjust in preset files or WLED interface
- **Effects**: Try different WLED built-in effects
- **Brightness**: Tune to your preference
- **Automations**: Customize Home Assistant automations

## 📝 Checklist

Use this to track your progress:

- [ ] Read QUICK_START.md
- [ ] Read README.md for design overview
- [ ] Measured all LED strips
- [ ] Updated configuration files with actual LED counts
- [ ] Installed Strip 1 (Interior)
- [ ] Installed Strip 2 (Front C)
- [ ] Installed Strip 3 (AMS 1 Lid)
- [ ] Installed Strip 4 (AMS 1 Tags)
- [ ] Installed Strip 5 (AMS 2 Lid)
- [ ] Installed Strip 6 (AMS 2 Tags)
- [ ] Connected power supply
- [ ] Configured Digquad controller
- [ ] Configured MagWLED controller
- [ ] Created all segments
- [ ] Imported presets
- [ ] Tested all segments
- [ ] Added to Home Assistant
- [ ] Created automations
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
1. Read [QUICK_START.md](QUICK_START.md)
2. Follow [docs/visual-installation-guide.md](docs/visual-installation-guide.md)
3. Use [docs/segment-reference.md](docs/segment-reference.md) for lookups

### Intermediate
1. Review [README.md](README.md) for complete design
2. Study [docs/wiring-diagram.md](docs/wiring-diagram.md) for details
3. Customize preset JSON files

### Advanced
1. Read [docs/home-assistant-automations.md](docs/home-assistant-automations.md)
2. Create custom effects and automations
3. Implement progress bar visualization
4. Add filament color matching

## 📌 Quick Links

### Most Important Files
- 🚀 [QUICK_START.md](QUICK_START.md) - Start here!
- 📖 [README.md](README.md) - Full documentation
- 🔌 [docs/wiring-diagram.md](docs/wiring-diagram.md) - Wiring guide
- 📋 [docs/segment-reference.md](docs/segment-reference.md) - Quick reference

### Configuration Files
- ⚙️ [digquad-settings/wled_cfg_Digquad.json](digquad-settings/wled_cfg_Digquad.json)
- 🎨 [digquad-settings/wled_presets_Digquad.json](digquad-settings/wled_presets_Digquad.json)
- ⚙️ [magwled-settings/wled_cfg_MagWLED.json](magwled-settings/wled_cfg_MagWLED.json)
- 🎨 [magwled-settings/wled_presets_MagWLED_updated.json](magwled-settings/wled_presets_MagWLED_updated.json)

## 💡 Tips

- **Bookmark this file** for easy navigation
- **Print the segment reference** for quick lookup during configuration
- **Take photos** during installation for future reference
- **Document your LED counts** in a separate file
- **Backup configurations** before making changes
- **Test incrementally** - one strip at a time

## 📅 Revision History

- **v1.0** (2024): Initial complete WLED configuration package
  - 2 controller setup (Digquad + MagWLED)
  - 6 LED strips
  - 23 total segments (15 + 8)
  - 25 presets (14 + 11)
  - Complete documentation suite

---

**Ready to get started?** → Open [QUICK_START.md](QUICK_START.md) now! 🚀
