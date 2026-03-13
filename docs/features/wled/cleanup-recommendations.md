# WLED Configuration — File Cleanup Recommendations

> **Updated 2026-03-13** — Refreshed after config file cleanup.

## Background

The WLED documentation and configuration evolved through several design phases:
1. **Original design** — hardware specs, scenario catalog, manual presets (1–49)
2. **Preset-based segment technique** — presets 50–57 for dynamic segment switching
3. **Home Assistant State Machine** — the deployed approach using presets 101–109

Several legacy and superseded config files have been removed. This document reflects the current filesystem state.

---

## Configuration Files (`wled/digquad-settings/`)

| File | Status | Deployed? | Notes |
|------|--------|-----------|-------|
| `wled_state_machine_presets_Digquad_skeleton.json` | **Active** | Yes (presets 101–109) | The live preset file |
| `wled_state_machine_preset_map.json` | **Active** | N/A (reference) | State → preset ID mapping, used by HA scripts |
| `wled_segments_Digquad_UPDATED.json` | **Reference** | Not yet | Target 15-segment layout for Phase 2 |
| `wled_preset_50_A1_full_highlight.json` | **Future** | No | Example for Phase 3 preset-based segments |
| `wled_preset_54_B1_full_highlight.json` | **Future** | No | Example for Phase 3 preset-based segments |

## Configuration Files (`wled/magwled-settings/`)

**Directory is now empty.** All MagWLED config files have been removed:

## Backup Directory (`wled/backups/`)

| Item | Status | Notes |
|------|--------|-------|
| `backups/README.md` | **Current** | Backup conventions |
| `backups/digquad/.gitkeep` | Placeholder | Keeps directory in git |
| `backups/digquad/README_TEMPLATE.md` | **Current** | Template for backup notes |
| `backups/digquad/2026-03-13 - Preinstall (baseline config)/` | **Current** | Most recent baseline snapshot |
| `backups/magwled/.gitkeep` | Placeholder | Keeps directory in git |
| `backups/magwled/NOTES_TEMPLATE.md` | **Current** | Template for backup notes |

## Documentation Files (`docs/features/wled/`)

| File | Status | Notes |
|------|--------|-------|
| `INDEX.md` | **Current** | Updated 2026-03-13 |
| `README.md` | **Current** | Updated 2026-03-13 |
| `quick-reference.md` | **Current** | Updated 2026-03-13 |
| `ha-state-machine-package.md` | **Current** | Authoritative state machine reference |
| `phased-implementation-guide.md` | **Current** | Rewritten 2026-03-13 (3-phase approach) |
| `light-scenarios.md` | **Current** | 33+ scenario catalog — target vision for Phases 2/3 |
| `cleanup-recommendations.md` | **Current** | This file |
| `controller-allocation.md` | **Current** | Hardware constraints still accurate |
| `hardware-constraint.md` | **Current** | DigQuad capacity documentation |
| `backup-and-restore.md` | **Current** | Procedures still valid |
| `digquad-led-segments.md` | **Current** | Physical LED specs (711 LEDs) |
| `summary.md` | **Current** | Updated 2026-03-13 |
| `segment-reference.md` | **Reference** | Segment lookup tables |
| `wiring-diagram.md` | **Reference** | Physical wiring guide |
| `visual-installation-guide.md` | **Reference** | ASCII art strip layout |
| `preset-specification.md` | **Legacy** | Presets 1–49 never deployed; retained as design reference |
| `quick-start.md` | **Legacy** | Pre-state-machine setup; hardware steps still useful |
| `home-assistant-automations.md` | **Legacy** | Pre-state-machine automations (has banner) |
| `preset-based-segments.md` | **Future** | Phase 3 dynamic segment technique |
| `ha-automation-preset-based.md` | **Future** | Phase 3 automations (has banner) |
| `preset-based-visual-guide.md` | **Future** | Phase 3 visual guide (has banner) |
| `quick-start-preset-based.md` | **Future** | Phase 3 quick start |
| `package-placeholder.md` | **Superseded** | HA package now exists; **safe to remove** |

## HA Package Files (`homeassistant/packages/3d_printing/wled/`)

| File | Status | Notes |
|------|--------|-------|
| `wled_loader.yaml` | **Active** | Package loader |
| `automations/wled_3dprinter_state_machine_orchestrator.yaml` | **Active** | Single-writer orchestrator |
| `scripts/wled_3dprinter_transition_from_event-script.yaml` | **Active** | Event → state mapping |
| `scripts/wled_3dprinter_apply_core_state_to_presets-script.yaml` | **Active** | State → preset mapping |
| All helper YAML files | **Active** | 5 helper definitions |

---

## HA Automation Conflict

There is a **non-repo automation** in Home Assistant:

| Automation | Entity | State |
|------------|--------|-------|
| Bambu Lab WLED Controller (advanced) | `automation.bambu_lab_wled_controller_advanced` | ON |
| Turn off WLED with Chamber Light | `automation.turn_off_wled_with_chamber_light` | OFF |

**Recommendation**: Disable `automation.bambu_lab_wled_controller_advanced` to prevent it from conflicting with the state machine orchestrator. It was likely created before the state machine was deployed.

---

## Remaining Cleanup Opportunities

| File | Status | Action |
|------|--------|--------|
| `package-placeholder.md` | Superseded | Safe to delete — the HA package it was placeholding for now exists |

All other legacy and future docs have clear status banners. No further file removals are recommended at this time — the remaining files either support the active deployment or document future phases.

---

**Version**: 2.0 (2026-03-13)
