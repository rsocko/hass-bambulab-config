# WLED Quick Reference Card

> **Updated 2026-03-13** — Reflects the current **Home Assistant State Machine** approach.

## Current Architecture

The WLED system uses a **Home Assistant state machine** that:
1. Monitors printer status entities (smart_status, stage, HMS errors)
2. Computes event IDs (E_OFFLINE, E_IDLE, E_PRINT_START, etc.)
3. Transitions through 9 core states (S0–S8)
4. Applies matching WLED presets (101–109) to DigQuad and MagWLED

**Core doc**: [ha-state-machine-package.md](ha-state-machine-package.md)

## Key Documents (Read in Order)

| # | Document | Purpose |
|---|----------|---------|
| 1 | [ha-state-machine-package.md](ha-state-machine-package.md) | **Start here.** State diagram, event mapping, phase plan |
| 2 | [controller-allocation.md](controller-allocation.md) | Hardware constraints + segment strategy |
| 3 | [digquad-led-segments.md](digquad-led-segments.md) | Physical LED counts and GPIO mapping (711 LEDs) |
| 4 | [phased-implementation-guide.md](phased-implementation-guide.md) | 3-phase guide aligned to state machine |
| 5 | [cleanup-recommendations.md](cleanup-recommendations.md) | Config file status and cleanup guidance |

## Hardware Reality

- **DigQuad**: 711 LEDs across 5 GPIO pins — **at full capacity, no changes possible**
- **MagWLED**: 48 LEDs (Interior Lid Light) on GPIO 2 — **currently unavailable/offline**
- Interior Lid Light stays on MagWLED; cannot move to DigQuad

## State Machine — 9 Core States

| State | Preset ID | DigQuad Visual | MagWLED |
|-------|-----------|----------------|---------|
| S0_OFFLINE | 101 | Dim amber status bar | Idle Standby |
| S1_IDLE | 102 | Soft blue breathing | Normal Printing |
| S2_PREP | 103 | Orange pulsing | Normal Printing |
| S3_PRINTING | 104 | Green solid | Normal Printing |
| S4_PAUSED_USER | 105 | Yellow blink | Normal Printing |
| S5_PAUSED_ERROR | 106 | Red strobe | Idle Standby |
| S6_FINISHING | 107 | Green wipe | Normal Printing |
| S7_MAINTENANCE | 108 | Orange chase | Normal Printing |
| S8_SHOW | 109 | Purple palette | Normal Printing |

## HA Entities (Deployed)

| Entity | Type | Purpose |
|--------|------|---------|
| `input_boolean.wled_3dprinter_state_machine_enabled` | Toggle | Master ON/OFF for state machine |
| `input_boolean.wled_3dprinter_show_mode_enabled` | Toggle | Aesthetic show mode (idle only) |
| `input_select.wled_3dprinter_core_state` | Select | Current state (S0–S8) |
| `input_text.wled_3dprinter_last_event` | Text | Last E_* event (debug) |
| `input_text.wled_3dprinter_last_transition_reason` | Text | Trigger detail (debug) |
| `select.dig_quad_v3_preset` | WLED | Active DigQuad preset |
| `select.magwled_preset` | WLED | Active MagWLED preset |

## Current DigQuad Segment Layout

The skeleton presets (101–109) currently control **segments 0 and 1** only:

| Segment | Purpose | Notes |
|---------|---------|-------|
| 0 | Front door / progress area | Color set per state |
| 1 | Status indicator (main seg) | Effect + color set per state |
| 2–4 | Additional segments | Present in WLED but not yet styled by state machine presets |

> **Next step**: Expand presets 101–109 to control all active segments once the full segment layout is deployed.

## Implementation Phases

| Phase | Scope | Status |
|-------|-------|--------|
| **Phase 1**: Core State Machine | HA helpers, scripts, orchestrator, skeleton presets 101-109 | ✅ Deployed |
| **Phase 2**: Segment Expansion | Deploy full 15-segment layout on DigQuad, expand presets to style all segments | Not started |
| **Phase 3**: Overlays & Advanced | Active tray highlighting, telemetry overlays, MagWLED coordination | Not started |

See [phased-implementation-guide.md](phased-implementation-guide.md) for full details and test guidance.

## Quick Diagnostic

Check these in HA Developer Tools → States:

| Check | Entity | Expected |
|-------|--------|----------|
| State machine ON? | `input_boolean.wled_3dprinter_state_machine_enabled` | `on` |
| Current state? | `input_select.wled_3dprinter_core_state` | Matches printer activity |
| Last event? | `input_text.wled_3dprinter_last_event` | Recent E_* event |
| DigQuad preset? | `select.dig_quad_v3_preset` | SM S*_* matching state |
| Orchestrator running? | `automation.wled_3d_printer_state_machine_orchestrator` | `on` |

## Known Issues

| Issue | Detail |
|-------|--------|
| MagWLED unavailable | `select.magwled_preset` shows unavailable — check device power/network |
| Legacy automation conflict | `automation.bambu_lab_wled_controller_advanced` is also ON — may fight the state machine for control. Disable if unexpected behavior occurs. |
| Only 2 segments styled | Skeleton presets only set segments 0+1; remaining segments need expansion in Phase 2 |

## Configuration Files Status

| File | Status | Action |
|------|--------|--------|
| `wled_state_machine_presets_Digquad_skeleton.json` | ✅ Active | Deployed as presets 101–109 |
| `wled_state_machine_preset_map.json` | ✅ Active | Reference for HA scripts |
| `wled_cfg_Digquad.json` | ✅ Active | Base controller config |
| `wled_presets_Digquad.json` | ⚠️ Legacy | Presets 1–14 not loaded; see [cleanup-recommendations.md](cleanup-recommendations.md) |
| `wled_segments_Digquad_UPDATED.json` | 📋 Reference | Target layout for Phase 2 |
| `wled_segments_Digquad.json` | 📦 Superseded | Use UPDATED version |
| `wled_preset_50/54_*.json` | 🔮 Future | Phase 3 preset-based segments |
| `.customization` files | 📦 Archive | Not for upload |

---

**Version**: 2.0 (State Machine approach — 2026-03-13)
**Architecture**: HA State Machine → WLED Presets 101–109
**Total LEDs**: 711 (DigQuad) + 48 (MagWLED)
**Hardware Constraint**: DigQuad at full GPIO capacity; MagWLED currently offline
**Estimated Time**: 25-45 hours for complete implementation  

**🚀 Ready to start? Read [phased-implementation-guide.md](phased-implementation-guide.md) and begin with Phase 1!**
