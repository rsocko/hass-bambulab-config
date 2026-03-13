# Phased Implementation Guide

> **Updated 2026-03-13** — Restructured around the Home Assistant State Machine approach.

## Overview

This guide describes a **3-phase** implementation approach aligned with the deployed HA state machine architecture. Phase 1 is already complete and running.

### Architecture Summary

```
Printer Entities → Orchestrator Automation → Transition Script → Core State Helper → Apply Presets Script → WLED Controllers
```

The orchestrator watches printer status entities, computes E_* events, transitions the state machine, and applies WLED presets. See [ha-state-machine-package.md](ha-state-machine-package.md) for the full state diagram and entity mappings.

### Target Vision

The end goal is a fully-functioning LED system implementing all 33+ scenarios defined in [light-scenarios.md](light-scenarios.md), including:
- Priority-tiered overlays (T0 safety → T5 aesthetic)
- Active tray highlighting with filament color matching
- Idle rotation modes (desiccant status, filament remaining)
- Dynamic segment allocation under the 16-segment cap

Each phase builds toward this target incrementally.

## Prerequisites

- [x] DigQuad controller connected and running WLED (711 LEDs, 5 GPIO pins)
- [x] DigQuad added to Home Assistant (`light.dig_quad_v3`, `select.dig_quad_v3_preset`)
- [x] Bambu Lab integration configured (`sensor.ntk_ryansoffice_3dprinter_smart_status`, etc.)
- [x] Read [ha-state-machine-package.md](ha-state-machine-package.md)
- [x] Read [controller-allocation.md](controller-allocation.md)
- [x] Read [light-scenarios.md](light-scenarios.md) — master scenario catalog and target behavior spec

---

## Phase 1: Core State Machine (✅ COMPLETE)

**Goal**: HA state machine drives DigQuad through 9 core states via skeleton presets  
**Status**: Deployed and running as of 2026-03-13

### What Was Deployed

#### HA Package Files
| File | Purpose |
|------|---------|
| `wled_loader.yaml` | Package loader (automations, scripts, helpers) |
| `automations/wled_3dprinter_state_machine_orchestrator.yaml` | Single-writer orchestrator |
| `scripts/wled_3dprinter_transition_from_event-script.yaml` | Event → state mapping |
| `scripts/wled_3dprinter_apply_core_state_to_presets-script.yaml` | State → preset mapping |
| `helpers/input_boolean/wled_3dprinter_state_machine_enabled.yaml` | Master toggle |
| `helpers/input_boolean/wled_3dprinter_show_mode_enabled.yaml` | Show mode toggle |
| `helpers/input_select/wled_3dprinter_core_state.yaml` | Current state (S0–S8) |
| `helpers/input_text/wled_3dprinter_last_event.yaml` | Debug: last event |
| `helpers/input_text/wled_3dprinter_last_transition_reason.yaml` | Debug: trigger detail |

#### WLED Config
| File | Purpose |
|------|---------|
| `wled_state_machine_presets_Digquad_skeleton.json` | Presets 101–109 merged into DigQuad |
| `wled_state_machine_preset_map.json` | Reference: state → preset ID |
| `wled_cfg_Digquad.json` | Base controller configuration |

#### Current Segment Layout on DigQuad
The skeleton presets style segments 0 and 1 only. DigQuad currently exposes 5 segments in HA:

| Segment | Current Use |
|---------|-------------|
| 0 | Front area (color per state) |
| 1 | Status indicator (main seg, effect per state) |
| 2–4 | Present but not styled by skeleton presets |

### Phase 1 Validation Checklist

- [x] Helper entities appear in HA Developer Tools → States
- [x] `input_boolean.wled_3dprinter_state_machine_enabled` is ON
- [x] `automation.wled_3d_printer_state_machine_orchestrator` is ON
- [x] `input_select.wled_3dprinter_core_state` changes when printer state changes
- [x] `input_text.wled_3dprinter_last_event` shows the most recent E_* event
- [x] `select.dig_quad_v3_preset` changes to match the core state (SM S0–S8)
- [x] Logbook shows transition entries from "WLED 3D Printer State Machine"

### Phase 1 Test Scenarios

| Test | Trigger | Expected State | Expected Preset |
|------|---------|---------------|-----------------|
| Printer off | Power off printer | S0_OFFLINE | SM S0 Offline |
| Printer idle | Power on, wait for idle | S1_IDLE | SM S1 Idle |
| Start print | Begin a print | S2_PREP → S3_PRINTING | SM S2 Prep → SM S3 Printing |
| Pause from UI | Pause button | S4_PAUSED_USER | SM S4 Paused User |
| Resume | Resume button | S3_PRINTING | SM S3 Printing |
| Print done | Wait for completion | S6_FINISHING → S1_IDLE | SM S6 Finishing → SM S1 Idle |
| Show mode | Toggle show mode ON while idle | S8_SHOW | SM S8 Show |

### Known Issues from Phase 1

| Issue | Detail | Workaround |
|-------|--------|------------|
| MagWLED unavailable | `select.magwled_preset` shows unavailable | Check MagWLED power/network; preset script will error silently |
| Legacy automation conflict | `automation.bambu_lab_wled_controller_advanced` is ON | Disable it if it fights the state machine |
| Only segments 0–1 styled | Skeleton presets only define 2 segments | Addressed in Phase 2 |

---

## Phase 2: Segment Expansion + Preset Enhancement

**Goal**: Deploy the full 15-segment layout on DigQuad; expand presets 101–109 to style all segments per state  
**Status**: Not started  
**Prerequisite**: Phase 1 validated  
**Design reference**: [light-scenarios.md](light-scenarios.md) — Sections 3 (scenario catalog), 5 (smart defaults), 6 (baseline presets)

### 2.1: Deploy Full Segment Layout

Apply the target 16-segment layout from [wled_segments_Digquad_UPDATED.json](../../../wled/digquad-settings/wled_segments_Digquad_UPDATED.json):

| Seg | Name | GPIO | LED Range | Count | Purpose |
|-----|------|------|-----------|-------|---------|
| 0 | Front Door Bottom | 15 | 0–49 | 50 | Print progress bar |
| 1 | Front Door Left | 15 | 50–115 | 65 | Layer progress |
| 2 | Front Door Top | 15 | 116–157 | 43 | Status indicator |
| 3 | AMS 1 Tray Top | 1 | 158–215 | 58 | AMS 1 tray lighting |
| 4 | AMS 1 Tray Bottom | 1 | 241–297 | 57 | Neutral background |
| 5 | AMS 2 Tray Top | 3 | 298–357 | 60 | AMS 2 tray lighting |
| 6 | AMS 2 Tray Bottom | 3 | 382–436 | 55 | Neutral background |
| 7 | Tag A1 Top | 16 | 442–453 | 12 | Tray A1 tag |
| 8 | Tag A2 Top | 16 | 454–465 | 12 | Tray A2 tag |
| 9 | Tag A3 Top | 16 | 466–477 | 12 | Tray A3 tag |
| 10 | Tag A4 Top | 16 | 490–501 | 12 | Tray A4 tag |
| 11 | Tag B1 Top | 4 | 579–591 | 13 | Tray B1 tag |
| 12 | Tag B2 Top | 4 | 592–605 | 14 | Tray B2 tag |
| 13 | Tag B3 Top | 4 | 606–619 | 14 | Tray B3 tag |
| 14 | Tag B4 Top | 4 | 632–643 | 12 | Tray B4 tag |
| 15 | Neutral Backgrounds | 16,4 | Various | ~125 | Tag bottoms + hygrometers |

**Steps**:
1. **Backup first**: Take a backup snapshot of DigQuad (cfg.json + presets.json) following [backup-and-restore.md](backup-and-restore.md)
2. Open DigQuad WLED UI → Segments
3. Create segments 0–15 with the LED ranges above
4. Save the segment layout as a preset (e.g., preset 100 "Base Layout")
5. Verify each segment lights independently via the WLED UI

### 2.2: Expand State Machine Presets

Update `wled_state_machine_presets_Digquad_skeleton.json` so each preset (101–109) includes segment definitions for all 16 segments, not just 0–1.

**Design guidance per state**:

| State | Seg 0 (Progress) | Seg 1 (Layer) | Seg 2 (Status) | Seg 3–6 (AMS Trays) | Seg 7–14 (Tags) | Seg 15 (Backgrounds) |
|-------|-------------------|---------------|----------------|----------------------|------------------|----------------------|
| S0_OFFLINE | Off | Off | Dim amber solid | Off | Off | Off |
| S1_IDLE | Off | Off | Soft blue breathe | Soft white 30% | Soft white 25% | Soft white 25% |
| S2_PREP | Off | Off | Orange pulse | Dim orange | Off | Off |
| S3_PRINTING | Green (dynamic) | Green (dynamic) | Green solid | White 40% | Soft white 30% | Soft white 25% |
| S4_PAUSED_USER | Yellow hold | Yellow hold | Yellow blink | Yellow dim | Yellow dim | Dim |
| S5_PAUSED_ERROR | Red flash | Red flash | Red strobe | Red 60% | Red 60% | Red dim |
| S6_FINISHING | Full green | Full green | Green wipe | White 40% | Soft white 30% | Soft white 25% |
| S7_MAINTENANCE | Off | Off | Orange chase | Amber dim | Off | Off |
| S8_SHOW | Off | Off | Purple palette fx | Purple dim | Purple breathe | Purple dim |

**Steps**:
1. Edit `wled_state_machine_presets_Digquad_skeleton.json` to add `seg` entries for all 15 segments in each preset
2. Each preset should include `"start"` and `"stop"` bounds for segments, or reference existing segment IDs
3. Re-merge the updated presets into DigQuad
4. Verify each state looks correct by manually setting `input_select.wled_3dprinter_core_state` in HA Developer Tools

### 2.3: Validate Segment Expansion

**Test procedure**:
1. Open HA Developer Tools → Services
2. Call `input_select.select_option` on `input_select.wled_3dprinter_core_state` for each state
3. Call `script.wled_3dprinter_apply_core_state_to_presets` after each change
4. Verify all 15 segments respond correctly on the DigQuad

| Test | Set State To | Verify |
|------|-------------|--------|
| Offline look | S0_OFFLINE | Only seg 1 dim amber; all others off |
| Idle look | S1_IDLE | Seg 1 blue breathing; AMS/tags soft white |
| Printing look | S3_PRINTING | Seg 0 green; seg 1 green; AMS/tags lit |
| Error look | S5_PAUSED_ERROR | All segments red; seg 1 strobe |
| Show look | S8_SHOW | Purple effects on visible segments |

### 2.4: MagWLED Coordination

If MagWLED is back online:
1. Verify `select.magwled_preset` doesn't show `unavailable`
2. Create matching presets on MagWLED (at minimum: "Idle Standby" and "Normal Printing")
3. Run through states and verify MagWLED responds

**Rollback**: If segment expansion causes issues, re-upload the original skeleton presets (101–109 with segments 0–1 only) from the backup.

---

## Phase 3: Overlays & Advanced Features

**Goal**: Add active tray highlighting, telemetry overlays, and preset-based dynamic segments  
**Status**: Not started  
**Prerequisite**: Phase 2 validated  
**Design reference**: [light-scenarios.md](light-scenarios.md) — Sections 4 (segment limits), 8 (hybrid control), 10 (priority tiers), 11 (state machine overlays), 12 (idle rotation)

### 3.1: Active Tray Highlighting

Add scripts/automations that run **after** the core preset is applied to override specific tag segments with the active tray's filament color.

**Approach**:
1. Create a new script `wled_3dprinter_apply_active_tray_overlay` that:
   - Reads the current active tray from `sensor.ntk_ryansoffice_3dprinter_active_tray` (or applicable entity)
   - Gets the filament color (from Spoolman integration or manual helpers)
   - Uses the WLED API to override the matching tag segment (6–13) color
2. Call this script from the orchestrator after `wled_3dprinter_apply_core_state_to_presets` completes, but **only when core_state is S3_PRINTING**

**Success criteria**: Active tray tag glows with filament color during printing; all other tags remain at the base preset's soft white.

### 3.2: Preset-Based Segment Switching (Optional Advanced)

For full tag top+bottom control, implement the preset-based segment reconfiguration from [preset-based-segments.md](preset-based-segments.md):

- Presets 50–57: Each redefines segment boundaries so the active tag gets both top AND bottom control
- HA automation switches to the appropriate preset when the active tray changes
- ~500ms delay needed for WLED to reconfigure segments

This is optional; the simpler approach in 3.1 (tag-top-only highlighting) may be sufficient.

### 3.3: Telemetry Overlays (Idle-Only)

Add idle-state-only visual overlays for:
- **Tray risk**: Dim orange pulse on tags with low filament
- **Humidity warnings**: Red pulse on AMS tray segments when desiccant is old
- **Desiccant age**: Amber flash on tag for trays past desiccant replacement date

These overlays should:
- Only activate when `input_select.wled_3dprinter_core_state == S1_IDLE`
- Be suppressed during prep/printing/error/maintenance states
- Be implemented as separate scripts called by additional automations

### 3.4: Progress Bar Enhancement

During S3_PRINTING, dynamically update segment 0 brightness/length to reflect print progress:
- Listen to `sensor.ntk_ryansoffice_3dprinter_print_progress` (or similar)
- Scale segment 0 intensity proportional to completion percentage
- Consider using WLED HTTP API for finer control than preset switching

### 3.5: Phase 3 Validation

| Test | Expected |
|------|----------|
| Print with tray A1 | Tag segment 6 shows filament color |
| Switch from A1 to B2 mid-print | Segment 6 returns to neutral; segment 11 lights up |
| Idle with low filament in A3 | Only tag 8 pulses orange (idle overlay) |
| Start print after idle overlay | Overlay suppressed; printing preset takes over |
| Progress at 50% | Segment 0 at ~50% intensity or half-lit |

---

## Rollback Plan

### Quick Disable
Turn off `input_boolean.wled_3dprinter_state_machine_enabled` to stop the orchestrator immediately. The DigQuad will hold its last preset state.

### Phase Rollback
| Phase | Rollback |
|-------|----------|
| Phase 1 | Disable toggle; remove package from `_feature_loaders.yaml` |
| Phase 2 | Re-upload skeleton presets (101–109 segment 0+1 only) from backup |
| Phase 3 | Remove overlay scripts/automations; core presets continue to work |

### Full Recovery
1. Disable `input_boolean.wled_3dprinter_state_machine_enabled`
2. Restore DigQuad from backup snapshot (see `wled/backups/digquad/`)
3. Remove WLED package from `_feature_loaders.yaml`
4. Restart Home Assistant

---

## Testing Checklist

### Phase 1 (Core State Machine) — Complete
- [x] All helper entities appear
- [x] Orchestrator triggers on printer status changes
- [x] Core state transitions match expected event mapping
- [x] DigQuad preset changes with each state transition
- [x] Logbook records transitions
- [x] Show mode only activates from idle
- [x] Master toggle disables/enables orchestrator

### Phase 2 (Segment Expansion)
- [ ] All 15 segments visible and addressable in WLED UI
- [ ] Each preset (101–109) styles all segments appropriately
- [ ] Manual state override from Developer Tools works
- [ ] Full print lifecycle looks correct (idle → prep → printing → finishing → idle)
- [ ] Pause states (user and error) are visually distinct
- [ ] Backup taken before and after changes

### Phase 3 (Overlays & Advanced)
- [ ] Active tray tag highlights with filament color during printing
- [ ] Inactive tags remain at neutral preset color
- [ ] Tray switching mid-print updates the correct tag
- [ ] Idle overlays appear only in idle state
- [ ] Progress bar reflects print completion
- [ ] Overlays suppress during non-idle states

---

## Troubleshooting

### State Machine Not Transitioning
| Check | How |
|-------|-----|
| Orchestrator enabled? | `automation.wled_3d_printer_state_machine_orchestrator` should be `on` |
| Master toggle on? | `input_boolean.wled_3dprinter_state_machine_enabled` should be `on` |
| Printer entity available? | `sensor.ntk_ryansoffice_3dprinter_smart_status` should not be `unavailable` |
| Event stuck on E_NOOP? | Check `input_text.wled_3dprinter_last_event` — if E_NOOP, the smart_status may be an unmapped value |

### DigQuad Not Changing Presets
| Check | How |
|-------|-----|
| Preset entity? | `select.dig_quad_v3_preset` should show available options |
| Preset names match? | The apply script sends exact preset name strings like "SM S3 Printing" — verify they match installed presets |
| WLED reachable? | Try opening DigQuad WLED web UI in browser |

### MagWLED Issues
| Check | How |
|-------|-----|
| Power? | Check TP-Link smart plug `switch.tp_link_power_strip_ab64_wled_3dprinter` is ON |
| Network? | `sensor.magwled_ip` should show an IP; `select.magwled_preset` should not be `unavailable` |
| Preset names? | MagWLED needs presets named "Idle Standby" and "Normal Printing" to match the apply script |

### Conflict with Legacy Automation
If `automation.bambu_lab_wled_controller_advanced` is ON, it may override the state machine's preset selections. Disable it:
1. Go to HA → Settings → Automations
2. Find "Bambu Lab WLED Controller (advanced)"
3. Disable it
4. Verify state machine controls presets exclusively

---

**Version**: 2.0 (State Machine approach — 2026-03-13)  
**Phases**: 3 (Core ✅ → Segment Expansion → Overlays)  
**Architecture**: HA State Machine → WLED Presets 101–109
