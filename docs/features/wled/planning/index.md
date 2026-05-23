# WLED Configuration â€” File Index

- Status: Active
- Last Reviewed: 2026-05-23
- Functional Owner: wled
- Replaces: docs/features/wled/INDEX.md
- Replaced By: n/a


> **Updated 2026-03-13** â€” Restructured around the HA State Machine approach.

## Current Architecture: HA State Machine

The system uses a Home Assistant state machine that monitors printer status, transitions through 9 core states (S0â€“S8), and applies WLED presets (101â€“109) to the DigQuad controller. See [ha-state-machine-package.md](../reference/ha-state-machine-package.md) for the authoritative reference.

---

## Start Here (Recommended Reading Order)

| #   | Document                                                         | Status      | Purpose                                                      |
| --- | ---------------------------------------------------------------- | ----------- | ------------------------------------------------------------ |
| 1   | [quick-reference.md](../reference/quick-reference.md)                         | **Current** | One-page overview of architecture, entities, and phases      |
| 2   | [ha-state-machine-package.md](../reference/ha-state-machine-package.md)       | **Current** | State diagram, E_* event mapping, preset mapping, phase plan |
| 3   | [controller-allocation.md](../reference/controller-allocation.md)             | **Current** | Hardware constraints, segment strategy                       |
| 4   | [digquad-led-segments.md](../reference/digquad-led-segments.md)               | **Current** | Physical LED counts and GPIO mapping (711 LEDs)              |
| 5   | [phased-implementation-guide.md](phased-implementation-guide.md) | **Current** | 3-phase guide aligned to state machine                       |
| 6   | [backup-and-restore.md](../reference/backup-and-restore.md)                   | **Current** | Backup/restore procedures                                    |

---

## Directory Structure

```
docs/features/wled/
â”œâ”€â”€ README.md                       â† Overview and quick links
â”œâ”€â”€ INDEX.md                        â† This file
â”œâ”€â”€ quick-reference.md              â† Start here
â”œâ”€â”€ ha-state-machine-package.md     â† State machine reference
â”œâ”€â”€ phased-implementation-guide.md  â† 3-phase implementation
â”œâ”€â”€ light-scenarios.md              â† Target vision: 33+ LED scenarios
â”œâ”€â”€ controller-allocation.md        â† Hardware constraints
â”œâ”€â”€ digquad-led-segments.md         â† Physical LED specs (711 LEDs)
â”œâ”€â”€ hardware-constraint.md          â† DigQuad capacity limits
â”œâ”€â”€ backup-and-restore.md           â† Backup/restore procedures
â”œâ”€â”€ cleanup-recommendations.md      â† File status and cleanup guidance
â”œâ”€â”€ summary.md                      â† Design history
â”œâ”€â”€ segment-reference.md            â† Segment lookup tables
â”œâ”€â”€ wiring-diagram.md               â† Physical wiring guide
â”œâ”€â”€ visual-installation-guide.md    â† ASCII strip layout
â”œâ”€â”€ preset-specification.md         â† Legacy: preset 1â€“49 spec (not deployed)
â”œâ”€â”€ preset-based-segments.md        â† Future: dynamic segments (Phase 3)
â”œâ”€â”€ preset-based-visual-guide.md    â† Future: visual guide (Phase 3)
â”œâ”€â”€ ha-automation-preset-based.md   â† Future: preset-based automations (Phase 3)
â”œâ”€â”€ quick-start-preset-based.md     â† Future: preset-based quick start (Phase 3)
â”œâ”€â”€ home-assistant-automations.md   â† Legacy: pre-state-machine automations
â””â”€â”€ quick-start.md                  â† Legacy: pre-state-machine setup

wled/
â”œâ”€â”€ digquad-settings/
â”‚   â”œâ”€â”€ wled_state_machine_presets_Digquad_skeleton.json â† Active: presets 101â€“109
â”‚   â”œâ”€â”€ wled_state_machine_preset_map.json       â† Active: reference mapping
â”‚   â”œâ”€â”€ wled_segments_Digquad_UPDATED.json       â† Reference: target layout (Phase 2)
â”‚   â”œâ”€â”€ wled_preset_50_A1_full_highlight.json    â† Future: preset-based segments
â”‚   â””â”€â”€ wled_preset_54_B1_full_highlight.json    â† Future: preset-based segments
â”œâ”€â”€ magwled-settings/                            â† Empty (configs removed; re-export from device)
â””â”€â”€ backups/
    â”œâ”€â”€ README.md
    â”œâ”€â”€ digquad/
    â”‚   â”œâ”€â”€ README_TEMPLATE.md
    â”‚   â”œâ”€â”€ 2026-03-13 - Preinstall (baseline config)/  â† Baseline cfg + presets snapshot
    â”‚   â””â”€â”€ 2026-03-13 - 2 - Phase 1 Implemented/      â† Post-Phase 1 cfg + presets snapshot
    â””â”€â”€ magwled/
        â””â”€â”€ NOTES_TEMPLATE.md

homeassistant/packages/3d_printing/wled/
â”œâ”€â”€ wled_loader.yaml                             â† Active: package loader
â”œâ”€â”€ automations/
â”‚   â””â”€â”€ wled_3dprinter_state_machine_orchestrator.yaml â† Active
â”œâ”€â”€ scripts/
â”‚   â”œâ”€â”€ wled_3dprinter_transition_from_event-script.yaml â† Active
â”‚   â””â”€â”€ wled_3dprinter_apply_core_state_to_presets-script.yaml â† Active
â””â”€â”€ helpers/
    â”œâ”€â”€ input_boolean/
    â”‚   â”œâ”€â”€ wled_3dprinter_state_machine_enabled.yaml â† Active
    â”‚   â””â”€â”€ wled_3dprinter_show_mode_enabled.yaml     â† Active
    â”œâ”€â”€ input_select/
    â”‚   â””â”€â”€ wled_3dprinter_core_state.yaml            â† Active
    â””â”€â”€ input_text/
        â”œâ”€â”€ wled_3dprinter_last_event.yaml            â† Active
        â””â”€â”€ wled_3dprinter_last_transition_reason.yaml â† Active
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
| [quick-reference.md](../reference/quick-reference.md)                         | One-page architecture reference |
| [ha-state-machine-package.md](../reference/ha-state-machine-package.md)       | State machine specification     |
| [phased-implementation-guide.md](phased-implementation-guide.md) | 3-phase implementation plan     |
| [controller-allocation.md](../reference/controller-allocation.md)             | Hardware allocation analysis    |
| [hardware-constraint.md](../reference/hardware-constraint.md)                 | DigQuad capacity limitations    |
| [backup-and-restore.md](../reference/backup-and-restore.md)                   | Backup procedures               |
| [digquad-led-segments.md](../reference/digquad-led-segments.md)               | Physical LED specs (711 LEDs)   |

### Reference (Background / Hardware)

| Document | Purpose |
|----------|---------|
| [light-scenarios.md](../design/light-scenarios.md) | 33+ lighting scenario catalog |
| [segment-reference.md](../reference/segment-reference.md) | Segment ID quick reference |
| [wiring-diagram.md](../reference/wiring-diagram.md) | Physical wiring guide |
| [visual-installation-guide.md](../reference/visual-installation-guide.md) | ASCII strip layout diagrams |
| [summary.md](../archive/summary-2026-03-13.md) | Design evolution history |
| [README.md](../README.md) | Original overview |

### Future (Phase 3+)

| Document | Purpose |
|----------|---------|
| [preset-based-segments.md](../design/preset-based-segments.md) | Dynamic segment switching technique |
| [quick-start-preset-based.md](quick-start-preset-based.md) | Quick start for preset-based approach |
| [ha-automation-preset-based.md](../design/preset-based-automation-examples.md) | Preset-based HA automations |
| [preset-based-visual-guide.md](../design/preset-based-visual-guide.md) | Visual guide for dynamic segments |

### Legacy (Pre-State-Machine)

| Document | Purpose |
|----------|---------|
| [preset-specification.md](../archive/preset-specification-legacy.md) | Presets 1â€“49 spec (never deployed on device) |
| [quick-start.md](../reference/quick-start-legacy.md) | Original setup guide (pre-state-machine) |
| [home-assistant-automations.md](../archive/home-assistant-automations-legacy.md) | Traditional HA automations |

---

## Configuration Files by Status

### Active Settings (`wled/digquad-settings/`)

| File | Status | Purpose |
|------|--------|--------|
| `wled_state_machine_presets_Digquad_skeleton.json` | **Active** | Deployed as presets 101â€“109 |
| `wled_state_machine_preset_map.json` | **Active** | Reference for HA scripts |
| `wled_segments_Digquad_UPDATED.json` | **Reference** | Target layout for Phase 2 |
| `wled_preset_50_A1_full_highlight.json` | **Future** | Phase 3 preset-based segments |
| `wled_preset_54_B1_full_highlight.json` | **Future** | Phase 3 preset-based segments |

### Backup Snapshots (`wled/backups/digquad/`)

| Folder | Contents |
|--------|----------|
| `2026-03-13 - Preinstall (baseline config)/` | `wled_cfg_Dig-Quad-V3.json`, `wled_presets_Dig-Quad-V3.json` â€” baseline before state machine |
| `2026-03-13 - 2 - Phase 1 Implemented/` | `wled_cfg_Dig-Quad-V3.json`, `wled_presets_Dig-Quad-V3.json` â€” after Phase 1 deployment |

---

## Use Case Guide

### "I just want to understand the current system"
â†’ [quick-reference.md](../reference/quick-reference.md)

### "I need to understand the state machine"
â†’ [ha-state-machine-package.md](../reference/ha-state-machine-package.md)

### "What do I do next?"
â†’ [phased-implementation-guide.md](phased-implementation-guide.md) (Phase 2: Segment Expansion)

### "What are the hardware specs?"
â†’ [digquad-led-segments.md](../reference/digquad-led-segments.md) (711 LEDs, 5 GPIO pins)

### "I need to back up before making changes"
â†’ [backup-and-restore.md](../reference/backup-and-restore.md)

### "I want to see all lighting scenarios"
â†’ [light-scenarios.md](../design/light-scenarios.md) (33+ scenarios â€” reference)

### "I'm troubleshooting"
â†’ [phased-implementation-guide.md](phased-implementation-guide.md) (Troubleshooting section)
â†’ [quick-reference.md](../reference/quick-reference.md) (Quick Diagnostic table)

---

## System Summary

| Attribute | Value |
|-----------|-------|
| Total LEDs | 711 (DigQuad) + 48 (MagWLED) |
| GPIO pins used | 5 of 5 on DigQuad + 1 on MagWLED |
| Active presets | 101â€“109 (state machine) |
| Core states | 9 (S0_OFFLINE through S8_SHOW) |
| HA entities | 5 helpers + 2 scripts + 1 automation |
| Current phase | Phase 1 complete; Phase 2 next |

---

**Version**: 2.0 (State Machine approach â€” 2026-03-13)
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

## ðŸ†˜ Getting Help

### Troubleshooting Resources
1. **[quick-start.md](../reference/quick-start-legacy.md)** - Common issues section
2. **[segment-reference.md](../reference/segment-reference.md)** - Troubleshooting quick reference
3. **[wiring-diagram.md](../reference/wiring-diagram.md)** - Troubleshooting guide section

### External Resources
- **WLED Documentation**: https://kno.wled.ge/
- **WLED GitHub**: https://github.com/Aircoookie/WLED
- **Home Assistant WLED**: https://www.home-assistant.io/integrations/wled/
- **Bambu Lab HA Integration**: https://github.com/greghesp/ha-bambulab

### Repository
- **Issues**: https://github.com/rsocko/hass-bambulab-config/issues
- **Discussions**: Share your setup and ask questions

## ðŸŽ“ Learning Path

### Beginner
1. Read [controller-allocation.md](../reference/controller-allocation.md) - Understand segment limitations
2. Read [preset-specification.md](../archive/preset-specification-legacy.md) - Review preset definitions
3. Read [phased-implementation-guide.md](phased-implementation-guide.md) - Start with Phase 1
4. Read [digquad-led-segments.md](../reference/digquad-led-segments.md) - Understand LED layout
5. Read [LED Function Map](../design/light-scenarios.md#2-led-function-map-consolidated) - Learn zone functions
6. Read [light-scenarios.md](../design/light-scenarios.md) - See all scenarios
7. Follow [quick-start.md](../reference/quick-start-legacy.md) - Setup guide
8. Use [visual-installation-guide.md](../reference/visual-installation-guide.md) - Visual reference

### Intermediate
1. Review [README.md](../README.md) for complete design
2. Study [wiring-diagram.md](../reference/wiring-diagram.md) for details
3. Create segments based on [LED Function Map](../design/light-scenarios.md#2-led-function-map-consolidated)
4. Configure presets from [light-scenarios.md](../design/light-scenarios.md)

### Advanced
1. Read [home-assistant-automations.md](../archive/home-assistant-automations-legacy.md)
2. Map scenarios from [light-scenarios.md](../design/light-scenarios.md) to automations
3. Implement progress bar visualization (door bottom)
4. Add filament color matching (from Spoolman)
5. Configure humidity warnings (hygrometer LEDs)

## ðŸ“Œ Quick Links

### Most Important Files
- ðŸŽ¯ [quick-reference.md](../reference/quick-reference.md) - **START HERE!** One-page overview
- ðŸ“„ [summary.md](../archive/summary-2026-03-13.md) - High-level summary
- â­ [controller-allocation.md](../reference/controller-allocation.md) - Allocation strategy & limitations
- â­ [preset-specification.md](../archive/preset-specification-legacy.md) - 31+ preset definitions
- â­ [phased-implementation-guide.md](phased-implementation-guide.md) - 7-phase implementation
- â­ [backup-and-restore.md](../reference/backup-and-restore.md) - Backup and restore workflow
- â­ [digquad-led-segments.md](../reference/digquad-led-segments.md) - LED specifications (711 LEDs)
- â­ [LED Function Map](../design/light-scenarios.md#2-led-function-map-consolidated) - Zone functions
- â­ [light-scenarios.md](../design/light-scenarios.md) - Scenario catalog (33+)
- ðŸš€ [quick-start.md](../reference/quick-start-legacy.md) - Setup guide
- ðŸ“– [README.md](../README.md) - Full documentation
- ðŸ”Œ [wiring-diagram.md](../reference/wiring-diagram.md) - Wiring guide
- ðŸ“‹ [segment-reference.md](../reference/segment-reference.md) - Quick reference

### Configuration Files
- âœ¨ [digquad-settings/wled_segments_Digquad_UPDATED.json](../../../wled/digquad-settings/wled_segments_Digquad_UPDATED.json) - Target segment layout (Phase 2)
- ðŸŽ¨ [digquad-settings/wled_state_machine_presets_Digquad_skeleton.json](../../../wled/digquad-settings/wled_state_machine_presets_Digquad_skeleton.json) - Active presets 101â€“109

## ðŸ’¡ Tips

- **Read specifications first** - digquad-led-segments.md has exact LED counts
- **Understand functions** - light-scenarios.md Section 2 explains what each zone does
- **Plan scenarios** - light-scenarios.md defines all 33+ lighting behaviors
- **Bookmark this file** for easy navigation
- **Print the segment reference** for quick lookup during configuration
- **Take photos** during installation for future reference
- **Backup configurations** before making changes
- **Test incrementally** - one GPIO output at a time

## ðŸ“… Revision History

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

**Ready to get started?** â†’ Open [quick-reference.md](../reference/quick-reference.md) first, then [phased-implementation-guide.md](phased-implementation-guide.md) now! ðŸš€




