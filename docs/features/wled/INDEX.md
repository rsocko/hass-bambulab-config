# WLED Configuration — File Index

> **Updated 2026-03-13** — Restructured around the HA State Machine approach.

## Current Architecture: HA State Machine

The system uses a Home Assistant state machine that monitors printer status, transitions through 9 core states (S0–S8), and applies WLED presets (101–109) to the DigQuad controller. See [ha-state-machine-package.md](ha-state-machine-package.md) for the authoritative reference.

---

## Start Here (Recommended Reading Order)

| #   | Document                                                         | Status      | Purpose                                                      |
| --- | ---------------------------------------------------------------- | ----------- | ------------------------------------------------------------ |
| 1   | [quick-reference.md](quick-reference.md)                         | **Current** | One-page overview of architecture, entities, and phases      |
| 2   | [ha-state-machine-package.md](ha-state-machine-package.md)       | **Current** | State diagram, E_* event mapping, preset mapping, phase plan |
| 3   | [controller-allocation.md](controller-allocation.md)             | **Current** | Hardware constraints, segment strategy                       |
| 4   | [digquad-led-segments.md](digquad-led-segments.md)               | **Current** | Physical LED counts and GPIO mapping (711 LEDs)              |
| 5   | [phased-implementation-guide.md](phased-implementation-guide.md) | **Current** | 3-phase guide aligned to state machine                       |
| 6   | [backup-and-restore.md](backup-and-restore.md)                   | **Current** | Backup/restore procedures                                    |

---

## Directory Structure

```
docs/features/wled/
├── README.md                       ← Overview and quick links
├── INDEX.md                        ← This file
├── quick-reference.md              ← Start here
├── ha-state-machine-package.md     ← State machine reference
├── phased-implementation-guide.md  ← 3-phase implementation
├── light-scenarios.md              ← Target vision: 33+ LED scenarios
├── controller-allocation.md        ← Hardware constraints
├── digquad-led-segments.md         ← Physical LED specs (711 LEDs)
├── hardware-constraint.md          ← DigQuad capacity limits
├── backup-and-restore.md           ← Backup/restore procedures
├── cleanup-recommendations.md      ← File status and cleanup guidance
├── summary.md                      ← Design history
├── segment-reference.md            ← Segment lookup tables
├── wiring-diagram.md               ← Physical wiring guide
├── visual-installation-guide.md    ← ASCII strip layout
├── preset-specification.md         ← Legacy: preset 1–49 spec (not deployed)
├── preset-based-segments.md        ← Future: dynamic segments (Phase 3)
├── preset-based-visual-guide.md    ← Future: visual guide (Phase 3)
├── ha-automation-preset-based.md   ← Future: preset-based automations (Phase 3)
├── quick-start-preset-based.md     ← Future: preset-based quick start (Phase 3)
├── home-assistant-automations.md   ← Legacy: pre-state-machine automations
└── quick-start.md                  ← Legacy: pre-state-machine setup

wled/
├── digquad-settings/
│   ├── wled_state_machine_presets_Digquad_skeleton.json ← Active: presets 101–109
│   ├── wled_state_machine_preset_map.json       ← Active: reference mapping
│   ├── wled_segments_Digquad_UPDATED.json       ← Reference: target layout (Phase 2)
│   ├── wled_preset_50_A1_full_highlight.json    ← Future: preset-based segments
│   └── wled_preset_54_B1_full_highlight.json    ← Future: preset-based segments
├── magwled-settings/                            ← Empty (configs removed; re-export from device)
└── backups/
    ├── README.md
    ├── digquad/
    │   ├── README_TEMPLATE.md
    │   ├── 2026-03-13 - Preinstall (baseline config)/  ← Baseline cfg + presets snapshot
    │   └── 2026-03-13 - 2 - Phase 1 Implemented/      ← Post-Phase 1 cfg + presets snapshot
    └── magwled/
        └── NOTES_TEMPLATE.md

homeassistant/packages/3d_printing/wled/
├── wled_loader.yaml                             ← Active: package loader
├── automations/
│   └── wled_3dprinter_state_machine_orchestrator.yaml ← Active
├── scripts/
│   ├── wled_3dprinter_transition_from_event-script.yaml ← Active
│   └── wled_3dprinter_apply_core_state_to_presets-script.yaml ← Active
└── helpers/
    ├── input_boolean/
    │   ├── wled_3dprinter_state_machine_enabled.yaml ← Active
    │   └── wled_3dprinter_show_mode_enabled.yaml     ← Active
    ├── input_select/
    │   └── wled_3dprinter_core_state.yaml            ← Active
    └── input_text/
        ├── wled_3dprinter_last_event.yaml            ← Active
        └── wled_3dprinter_last_transition_reason.yaml ← Active
```

---

## Document Status Legend

| Status | Meaning |
|--------|---------|
| **Current** | Reflects deployed state machine approach |
| **Reference** | Accurate background/hardware info, still useful |
| **Future** | Valid design for Phase 3+, not yet deployed |
| **Legacy** | Pre-state-machine approach; retained for reference but not the active path |
| **Superseded** | Replaced by newer version |
| **Archive** | Historical snapshot; do not deploy |

## All Documents by Status

### Current (Deployed / Accurate)

| Document                                                         | Purpose                         |
| ---------------------------------------------------------------- | ------------------------------- |
| [quick-reference.md](quick-reference.md)                         | One-page architecture reference |
| [ha-state-machine-package.md](ha-state-machine-package.md)       | State machine specification     |
| [phased-implementation-guide.md](phased-implementation-guide.md) | 3-phase implementation plan     |
| [controller-allocation.md](controller-allocation.md)             | Hardware allocation analysis    |
| [hardware-constraint.md](hardware-constraint.md)                 | DigQuad capacity limitations    |
| [backup-and-restore.md](backup-and-restore.md)                   | Backup procedures               |
| [digquad-led-segments.md](digquad-led-segments.md)               | Physical LED specs (711 LEDs)   |

### Reference (Background / Hardware)

| Document | Purpose |
|----------|---------|
| [light-scenarios.md](light-scenarios.md) | 33+ lighting scenario catalog |
| [segment-reference.md](segment-reference.md) | Segment ID quick reference |
| [wiring-diagram.md](wiring-diagram.md) | Physical wiring guide |
| [visual-installation-guide.md](visual-installation-guide.md) | ASCII strip layout diagrams |
| [summary.md](summary.md) | Design evolution history |
| [README.md](README.md) | Original overview |

### Future (Phase 3+)

| Document | Purpose |
|----------|---------|
| [preset-based-segments.md](preset-based-segments.md) | Dynamic segment switching technique |
| [quick-start-preset-based.md](quick-start-preset-based.md) | Quick start for preset-based approach |
| [ha-automation-preset-based.md](ha-automation-preset-based.md) | Preset-based HA automations |
| [preset-based-visual-guide.md](preset-based-visual-guide.md) | Visual guide for dynamic segments |

### Legacy (Pre-State-Machine)

| Document | Purpose |
|----------|---------|
| [preset-specification.md](preset-specification.md) | Presets 1–49 spec (never deployed on device) |
| [quick-start.md](quick-start.md) | Original setup guide (pre-state-machine) |
| [home-assistant-automations.md](home-assistant-automations.md) | Traditional HA automations |

---

## Configuration Files by Status

### Active Settings (`wled/digquad-settings/`)

| File | Status | Purpose |
|------|--------|--------|
| `wled_state_machine_presets_Digquad_skeleton.json` | **Active** | Deployed as presets 101–109 |
| `wled_state_machine_preset_map.json` | **Active** | Reference for HA scripts |
| `wled_segments_Digquad_UPDATED.json` | **Reference** | Target layout for Phase 2 |
| `wled_preset_50_A1_full_highlight.json` | **Future** | Phase 3 preset-based segments |
| `wled_preset_54_B1_full_highlight.json` | **Future** | Phase 3 preset-based segments |

### Backup Snapshots (`wled/backups/digquad/`)

| Folder | Contents |
|--------|----------|
| `2026-03-13 - Preinstall (baseline config)/` | `wled_cfg_Dig-Quad-V3.json`, `wled_presets_Dig-Quad-V3.json` — baseline before state machine |
| `2026-03-13 - 2 - Phase 1 Implemented/` | `wled_cfg_Dig-Quad-V3.json`, `wled_presets_Dig-Quad-V3.json` — after Phase 1 deployment |

---

## Use Case Guide

### "I just want to understand the current system"
→ [quick-reference.md](quick-reference.md)

### "I need to understand the state machine"
→ [ha-state-machine-package.md](ha-state-machine-package.md)

### "What do I do next?"
→ [phased-implementation-guide.md](phased-implementation-guide.md) (Phase 2: Segment Expansion)

### "What are the hardware specs?"
→ [digquad-led-segments.md](digquad-led-segments.md) (711 LEDs, 5 GPIO pins)

### "I need to back up before making changes"
→ [backup-and-restore.md](backup-and-restore.md)

### "I want to see all lighting scenarios"
→ [light-scenarios.md](light-scenarios.md) (33+ scenarios — reference)

### "I'm troubleshooting"
→ [phased-implementation-guide.md](phased-implementation-guide.md) (Troubleshooting section)
→ [quick-reference.md](quick-reference.md) (Quick Diagnostic table)

---

## System Summary

| Attribute | Value |
|-----------|-------|
| Total LEDs | 711 (DigQuad) + 48 (MagWLED) |
| GPIO pins used | 5 of 5 on DigQuad + 1 on MagWLED |
| Active presets | 101–109 (state machine) |
| Core states | 9 (S0_OFFLINE through S8_SHOW) |
| HA entities | 5 helpers + 2 scripts + 1 automation |
| Current phase | Phase 1 complete; Phase 2 next |

---

**Version**: 2.0 (State Machine approach — 2026-03-13)
- [ ] Read README.md for design overview
- [ ] Obtained LED strips (711 LEDs total)
- [ ] Installed Printer Front Door LEDs (GPIO 15, 158 LEDs)
- [ ] Installed AMS 1 Lid LEDs (GPIO 1, 140 LEDs)
- [ ] Installed AMS 2 Lid LEDs (GPIO 3, 139 LEDs)
- [ ] Installed AMS 1 Tag LEDs (GPIO 16, 136 LEDs)
- [ ] Installed AMS 2 Tag LEDs (GPIO 4, 138 LEDs)
- [ ] Confirm Interior Lid Light remains on MagWLED and sync behavior with DigQuad automations
- [ ] Connected power supply (15-20A @ 5V recommended)
- [ ] Configured Digquad controller with UPDATED segment definitions
- [ ] Created 16 optimized segments (3 front door segments, combined backgrounds)
- [ ] Imported/created presets from preset-specification.md
- [ ] Tested all segments
- [ ] Added to Home Assistant
- [ ] Created automations for active tray scenarios
- [ ] Tested with actual print
- [ ] Documented final configuration

## 🆘 Getting Help

### Troubleshooting Resources
1. **[quick-start.md](quick-start.md)** - Common issues section
2. **[segment-reference.md](segment-reference.md)** - Troubleshooting quick reference
3. **[wiring-diagram.md](wiring-diagram.md)** - Troubleshooting guide section

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
1. Read [controller-allocation.md](controller-allocation.md) - Understand segment limitations
2. Read [preset-specification.md](preset-specification.md) - Review preset definitions
3. Read [phased-implementation-guide.md](phased-implementation-guide.md) - Start with Phase 1
4. Read [digquad-led-segments.md](digquad-led-segments.md) - Understand LED layout
5. Read [LED Function Map](light-scenarios.md#2-led-function-map-consolidated) - Learn zone functions
6. Read [light-scenarios.md](light-scenarios.md) - See all scenarios
7. Follow [quick-start.md](quick-start.md) - Setup guide
8. Use [visual-installation-guide.md](visual-installation-guide.md) - Visual reference

### Intermediate
1. Review [README.md](README.md) for complete design
2. Study [wiring-diagram.md](wiring-diagram.md) for details
3. Create segments based on [LED Function Map](light-scenarios.md#2-led-function-map-consolidated)
4. Configure presets from [light-scenarios.md](light-scenarios.md)

### Advanced
1. Read [home-assistant-automations.md](home-assistant-automations.md)
2. Map scenarios from [light-scenarios.md](light-scenarios.md) to automations
3. Implement progress bar visualization (door bottom)
4. Add filament color matching (from Spoolman)
5. Configure humidity warnings (hygrometer LEDs)

## 📌 Quick Links

### Most Important Files
- 🎯 [quick-reference.md](quick-reference.md) - **START HERE!** One-page overview
- 📄 [summary.md](summary.md) - High-level summary
- ⭐ [controller-allocation.md](controller-allocation.md) - Allocation strategy & limitations
- ⭐ [preset-specification.md](preset-specification.md) - 31+ preset definitions
- ⭐ [phased-implementation-guide.md](phased-implementation-guide.md) - 7-phase implementation
- ⭐ [backup-and-restore.md](backup-and-restore.md) - Backup and restore workflow
- ⭐ [digquad-led-segments.md](digquad-led-segments.md) - LED specifications (711 LEDs)
- ⭐ [LED Function Map](light-scenarios.md#2-led-function-map-consolidated) - Zone functions
- ⭐ [light-scenarios.md](light-scenarios.md) - Scenario catalog (33+)
- 🚀 [quick-start.md](quick-start.md) - Setup guide
- 📖 [README.md](README.md) - Full documentation
- 🔌 [wiring-diagram.md](wiring-diagram.md) - Wiring guide
- 📋 [segment-reference.md](segment-reference.md) - Quick reference

### Configuration Files
- ✨ [digquad-settings/wled_segments_Digquad_UPDATED.json](../../../wled/digquad-settings/wled_segments_Digquad_UPDATED.json) - Target segment layout (Phase 2)
- 🎨 [digquad-settings/wled_state_machine_presets_Digquad_skeleton.json](../../../wled/digquad-settings/wled_state_machine_presets_Digquad_skeleton.json) - Active presets 101–109

## 💡 Tips

- **Read specifications first** - digquad-led-segments.md has exact LED counts
- **Understand functions** - light-scenarios.md Section 2 explains what each zone does
- **Plan scenarios** - light-scenarios.md defines all 33+ lighting behaviors
- **Bookmark this file** for easy navigation
- **Print the segment reference** for quick lookup during configuration
- **Take photos** during installation for future reference
- **Backup configurations** before making changes
- **Test incrementally** - one GPIO output at a time

## 📅 Revision History

- **v1.1** (2024): Added comprehensive specifications
  - Added digquad-led-segments.md with exact LED counts (711 total)
  - Consolidated zone function specifications into light-scenarios.md Section 2
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

**Ready to get started?** → Open [quick-reference.md](quick-reference.md) first, then [phased-implementation-guide.md](phased-implementation-guide.md) now! 🚀
