# Phased Implementation Guide

> **Updated 2026-03-13** — Restructured around the Home Assistant State Machine approach.

## Overview

This guide describes a **6-phase** implementation approach aligned with the deployed HA state machine architecture. Phase 1 is complete; Phases 2-6 progressively close remaining gaps from [light-scenarios.md](light-scenarios.md).

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
| `wled_state_machine_presets_Digquad_skeleton.json` | Phase 1 presets 101–109 (2-segment only, rollback reference) |
| `wled_state_machine_presets_Digquad.json` | Current presets 100–109 (15-segment, full layout + Phase 3.1 progress) |
| `wled_state_machine_preset_map.json` | Reference: state → preset ID |
| `wled_segments_Digquad_UPDATED.json` | Reference: 15-segment layout definition |
| `wled_cfg_Digquad.json` | Base controller configuration |

#### Current Segment Layout on DigQuad
Phase 1 skeleton presets style segments 0 and 1 only. Phase 2 expands to 15 segments covering all 711 LEDs.

Interior Lid Light is controlled by MagWLED (separate controller, not DigQuad).

| Segment | Phase 1 Use | Phase 2 Use |
|---------|-------------|-------------|
| 0 | Front area (color per state) | Front Door Bottom (progress bar) |
| 1 | Status indicator (main seg, effect per state) | Front Door Left (layer progress) |
| 2–4 | Present but not styled by skeleton presets | Seg 2: Front Door Top (status), Seg 3: AMS1 Combined, Seg 4: AMS2 Combined |
| 5–14 | N/A | Seg 5–8: Tag A1–A4, Seg 9: AMS1 Backgrounds, Seg 10–13: Tag B1–B4, Seg 14: AMS2 Backgrounds |

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

**Goal**: Deploy the full 15-segment layout on DigQuad; expand presets 100–109 to style all segments per state  
**Status**: Implementation ready (files created, pending deployment)  
**Prerequisite**: Phase 1 validated  
**Design reference**: [light-scenarios.md](light-scenarios.md) — Sections 3 (scenario catalog), 5 (smart defaults), 6 (baseline presets)

### 2.1: Deploy Full Segment Layout

Apply the 15-segment layout from [wled_segments_Digquad_UPDATED.json](../../../wled/digquad-settings/wled_segments_Digquad_UPDATED.json):

| Seg | Name | GPIO | LED Range | Count | Purpose |
|-----|------|------|-----------|-------|---------|
| 0 | Front Door Bottom | 15 | 0–49 | 50 | Print progress bar |
| 1 | Front Door Left | 15 | 50–114 | 65 | Layer progress |
| 2 | Front Door Top | 15 | 115–157 | 43 | Status indicator |
| 3 | AMS1 Combined | 1 | 158–297 | 140 | AMS 1 tray lighting (top + bottom) |
| 4 | AMS2 Combined | 3 | 298–436 | 139 | AMS 2 tray lighting (top + bottom) |
| 5 | Tag A1 Top | 16 | 437–453 | 17 | Tray A1 tag (incl. side start) |
| 6 | Tag A2 Top | 16 | 454–465 | 12 | Tray A2 tag |
| 7 | Tag A3 Top | 16 | 466–489 | 24 | Tray A3 tag (incl. hygrometer) |
| 8 | Tag A4 Top | 16 | 490–501 | 12 | Tray A4 tag |
| 9 | AMS1 Tag Bottoms | 16 | 502–572 | 71 | AMS1 tag bottoms + backgrounds |
| 10 | Tag B1 Top | 4 | 573–591 | 19 | Tray B1 tag (incl. side start) |
| 11 | Tag B2 Top | 4 | 592–605 | 14 | Tray B2 tag |
| 12 | Tag B3 Top | 4 | 606–631 | 26 | Tray B3 tag (incl. hygrometer) |
| 13 | Tag B4 Top | 4 | 632–643 | 12 | Tray B4 tag |
| 14 | AMS2 Tag Bottoms | 4 | 644–710 | 67 | AMS2 tag bottoms + backgrounds |

**Total**: 711 LEDs, 15 segments, zero gaps, 1 spare slot under WLED 16-segment max  
**Note**: Interior Lid Light is controlled by MagWLED (separate controller), not DigQuad

**Layout decisions**:
- 3 door segments (Bottom/Left/Top) for independent progress bar, layer, and status control
- AMS top + bottom combined per unit (2 segments instead of 4) — minimal visual differentiation at this phase
- Side-wall and hygrometer LEDs absorbed into adjacent tag/background segments — Phase 3 can differentiate via API overlays

**Steps**:
1. **Backup first**: Take a backup snapshot of DigQuad (cfg.json + presets.json) into `wled/backups/digquad/2026-03-13 - 3 - Pre Phase 2/`
2. Merge `wled_state_machine_presets_Digquad.json` into DigQuad (this file contains presets 100–109)
3. Load Preset 100 ("SM Base Layout") once to establish the 15-segment layout with boundaries
4. Verify each segment lights independently via the WLED UI
5. Test each state preset (101–109) by selecting them in the WLED UI

### 2.2: Expand State Machine Presets

New file: `wled_state_machine_presets_Digquad.json` — replaces the Phase 1 skeleton with full 15-segment presets.  
Phase 1 skeleton preserved at `wled_state_machine_presets_Digquad_skeleton.json` for rollback.

**Preset 100 (SM Base Layout)**: Defines segment boundaries (start/stop) + neutral warm white on all segments.  
**Presets 101–109**: Style all 15 segments per state (no boundary changes — references existing segment IDs).

**Design guidance per state**:

| State | Seg 0 (Progress) | Seg 1 (Left) | Seg 2 (Top/Status) | Seg 3–4 (AMS) | Seg 5–8, 10–13 (Tags) | Seg 9, 14 (Backgrounds) |
|-------|-------------------|--------------|---------------------|----------------|------------------------|-------------------------|
| S0_OFFLINE | Off | Off | Dim amber solid | Off | Off | Off |
| S1_IDLE | Off | Off | Soft blue breathe | Soft white 30% | Soft white 25% | Soft white 25% |
| S2_PREP | Off | Off | Orange pulse | Dim orange | Off | Off |
| S3_PRINTING | Green Percent (dynamic) | Green Percent (dynamic) | Green slow breathe | White 40% | Soft white 30% | Soft white 25% |
| S4_PAUSED_USER | Keeps progress | Keeps progress | Yellow blink | Yellow dim | Yellow dim | Dim |
| S5_PAUSED_ERROR | Keeps progress | Keeps progress | Red strobe | Red 60% | Red 60% | Red dim |
| S6_FINISHING | Full green | Full green | Green wipe | White 40% | Soft white 30% | Soft white 25% |
| S7_MAINTENANCE | Off | Off | Orange chase | Amber dim | Off | Off |
| S8_SHOW | Off | Off | Purple palette fx | Purple dim | Purple breathe | Purple dim |

**Steps**:
1. Merge `wled_state_machine_presets_Digquad.json` into DigQuad's presets (replaces 101–109, adds 100)
2. Load Preset 100 once to establish segment layout
3. Verify each state by manually setting `input_select.wled_3dprinter_core_state` in HA Developer Tools
4. Call `script.wled_3dprinter_apply_core_state_to_presets` after each state change to apply the preset

### 2.3: Validate Segment Expansion

**Test procedure**:
1. Open HA Developer Tools → Services
2. Call `input_select.select_option` on `input_select.wled_3dprinter_core_state` for each state
3. Call `script.wled_3dprinter_apply_core_state_to_presets` after each change
4. Verify all 15 segments respond correctly on the DigQuad

| Test | Set State To | Verify |
|------|-------------|--------|
| Offline look | S0_OFFLINE | Only seg 2 (door top) dim amber; all others off |
| Idle look | S1_IDLE | Seg 2 blue breathing; AMS combined soft white; tags/backgrounds soft white |
| Prep look | S2_PREP | Seg 2 orange pulse; AMS combined dim orange; tags off |
| Printing look | S3_PRINTING | Segs 0–2 green; AMS white; tags/backgrounds soft white |
| Paused user | S4_PAUSED_USER | All segments yellow; seg 2 blinking |
| Error look | S5_PAUSED_ERROR | All segments red; segs 0–2 blinking |
| Finishing look | S6_FINISHING | Segs 0–1 green; seg 2 green wipe; AMS/tags lit |
| Maintenance | S7_MAINTENANCE | Seg 2 orange chase; AMS amber dim; tags off |
| Show look | S8_SHOW | Seg 2 purple fx; tags purple breathing; backgrounds purple dim |

### 2.4: MagWLED Coordination

If MagWLED is back online:
1. Verify `select.magwled_preset` doesn't show `unavailable`
2. Create matching presets on MagWLED (at minimum: "Idle Standby" and "Normal Printing")
3. Run through states and verify MagWLED responds

**Rollback**: If segment expansion causes issues, re-upload the original skeleton presets (101–109 with segments 0–1 only) from the backup.

---

## Phase 3: Core Overlays (3.1/3.2/3.4)

**Goal**: Add dynamic progress visualization, active tray highlighting, telemetry overlays, and preset-based dynamic segments  
**Status**: 3.1 implemented  
**Prerequisite**: Phase 2 validated  
**Design reference**: [light-scenarios.md](light-scenarios.md) — Sections 4 (segment limits), 8 (hybrid control), 10 (priority tiers), 11 (state machine overlays), 12 (idle rotation)

### 3.1: Progress Bar & Status Enhancement (✅ IMPLEMENTED)

During S3_PRINTING, segments 0, 1, and 2 on the front door dynamically visualize print progress, layer progress, and print health:

| Segment | Zone | Effect | Color | Data Source |
|---------|------|--------|-------|-------------|
| 0 | Front Door Bottom | Percent (fx 98) | Green fill `[0, 255, 40]` on dim white `[50, 44, 36]` background | `sensor.ntk_ryansoffice_3dprinter_print_progress` (0–100%) |
| 1 | Front Door Left | Percent (fx 98) | Blue fill `[0, 100, 255]` on dim white `[50, 44, 36]` background | `sensor.ntk_ryansoffice_3dprinter_current_layer` / `sensor.ntk_ryansoffice_3dprinter_total_layer_count` |
| 2 | Front Door Top | Breathe (fx 2), very slow (sx 20) | Green `[0, 200, 60]` | N/A — indicates healthy print in progress |

**How it works**:

1. When the state machine enters S3_PRINTING, preset 104 loads with:
   - Seg 0 and 1: Percent effect at ix=0 (empty) with dim white background glow
   - Seg 2: Very slow green breathe (indicates healthy print)
2. The **orchestrator** calls `script.wled_3dprinter_apply_progress_overlay` 500ms after applying the S3_PRINTING preset
3. The **progress overlay automation** (`wled_3dprinter_progress_overlay`) watches for changes to print progress and layer count sensors, and calls the overlay script to update `ix` values
4. The overlay script sends a targeted WLED JSON API request (via `rest_command.wled_digquad_update_state`) that updates ONLY the `ix` parameter on segments 0 and 1 — all other segment properties remain as set by preset 104
5. Pause/error presets (105, 106) only change **segment 2** (top bar) to yellow/red. Segments 0 and 1 retain the Percent effect with their last progress values, so the progress bars remain visible during pause/error states. On resume, preset 104 reloads and the overlay restores current progress values.

**ix mapping** (Percent effect uses 0–100 direct percentage):
- Segment 0: `ix = round(print_progress)` → 0=empty, 100=full
- Segment 1: `ix = round(current_layer / total_layers × 100)` → 0=empty, 100=full (safe division, 0 when total_layers is 0)

#### Files Created / Modified

| File | Change |
|------|--------|
| `helpers/input_text/wled_3dprinter_digquad_ip.yaml` | **New** — Input text helper for DigQuad WLED IP address (required for JSON API calls) |
| `rest_commands/wled_3dprinter_digquad_update_state.yaml` | **New** — Generic REST command to POST JSON to WLED `/json/state` endpoint |
| `scripts/wled_3dprinter_apply_progress_overlay-script.yaml` | **New** — Reads progress sensors, calculates ix, sends segment update via REST |
| `automations/wled_3dprinter_progress_overlay.yaml` | **New** — Triggers on progress/layer sensor changes; conditions on S3_PRINTING |
| `automations/wled_3dprinter_state_machine_orchestrator.yaml` | **Modified** — Added progress overlay call after S3_PRINTING preset application |
| `wled_loader.yaml` | **Modified** — Added `rest_command: !include_dir_merge_named rest_commands` |
| `wled_state_machine_presets_Digquad.json` (preset 104) | **Modified** — Seg 0: Percent fx green/white, Seg 1: Percent fx blue/white, Seg 2: slow green Breathe |

#### Setup Steps

1. Set `input_text.wled_3dprinter_digquad_ip` to the DigQuad's IP address (e.g., `192.168.1.xx`) in HA → Settings → Helpers
2. Verify `rest_command.wled_3dprinter_digquad_update_state` is available (HA → Developer Tools → Services)
3. Verify the Percent effect ID on your WLED build — effect ID **98** is confirmed for DigQuad at `192.168.50.103`. Check WLED UI → Effects or query `http://<ip>/json/effects` to verify. If different, update preset 104 `fx` values for segments 0 and 1.
4. Deploy updated preset 104 to DigQuad (merge from `wled_state_machine_presets_Digquad.json`)
5. Restart HA to load new automation, script, rest_command, and helper

#### Validation

| Test | Expected |
|------|----------|
| Enter S3_PRINTING | Seg 0 and 1 show dim white base (Percent at ix≈0), Seg 2 slow green breathe |
| Print at 50% | Seg 0 half-filled green on white background |
| Layer 25/100 | Seg 1 ~25% filled blue on white background |
| Print at 100% | Seg 0 fully green |
| Pause (user) | Seg 2 switches to yellow blink; segs 0/1 retain progress bars |
| Resume from pause | Progress overlay updates resume within ~2.5s |
| Pause (error) | Seg 2 switches to red strobe; segs 0/1 retain progress bars |
| DigQuad IP not set | Progress overlay skips gracefully (condition check on input_text length) |

### 3.2: Active Tray Highlighting

Add scripts/automations that run **after** the core preset is applied to override specific tag segments with the active tray's filament color.

**Approach**:
1. Create a new script `wled_3dprinter_apply_active_tray_overlay` that:
   - Reads the current active tray from `sensor.ntk_ryansoffice_3dprinter_active_tray` (use the AMS Index and Tray Index attributes)
   - Gets the filament color (active tray entity Color attribute)
   - Uses the WLED API to override the matching tag segment (5–8, 10–13) color
2. Call this script from the orchestrator after `wled_3dprinter_apply_core_state_to_presets` completes, but **only when core_state is S3_PRINTING**

**Success criteria**: Active tray tag glows with filament color during printing; all other tags remain at the base preset's soft white.

> Note: Former section 3.3 (preset-based segment switching) is intentionally moved to **Phase 6.1** so foundational behavior lands first.

### 3.4: Telemetry Overlays (Idle-Only)

Implemented idle-state-only visual overlays for:
- **Tray risk**: Tag overlays on segments `5-8` and `10-13`, using the same risk thresholds shown in dashboard tray cards
- **Humidity warnings**: Red pulse on AMS background segments `9` and `14`
- **Desiccant age**: Per-tray tag overlays driven by `sensor.spoolman_tray_map` desiccant status

Implementation notes:
- Only activate when `input_select.wled_3dprinter_core_state == S1_IDLE`
- Suppressed during prep/printing/error/maintenance states by state conditions
- Implemented as separate scripts coordinated by one idle overlay script and automation
- Threshold and alert logic intentionally mirrors dashboard behavior from:
   - `common/dashboard_cards/card_templates/ams_tray_detail.yaml`
   - `common/dashboard_cards/card_templates/ams_tray_popup.yaml`
   - `common/dashboard_cards/card_templates/ams_tray_label.yaml`

#### Files Created / Modified

| File | Change |
|------|--------|
| `helpers/input_number/wled_3dprinter_idle_tray_risk_threshold_grams.yaml` | **New** — low-filament threshold helper for idle tray risk overlays |
| `helpers/input_number/wled_3dprinter_idle_humidity_warning_threshold.yaml` | **New** — humidity threshold helper for idle AMS background warnings (default 50% to match dashboard red threshold) |
| `scripts/wled_3dprinter_apply_idle_telemetry_overlays-script.yaml` | **New** — idle overlay coordinator (preset reset + ordered overlay application) |
| `scripts/wled_3dprinter_apply_idle_tray_risk_overlay-script.yaml` | **New** — tray risk overlay script with dashboard-matched thresholds |
| `scripts/wled_3dprinter_apply_idle_humidity_overlay-script.yaml` | **New** — humidity warning overlay script for AMS background segments |
| `scripts/wled_3dprinter_apply_idle_desiccant_overlay-script.yaml` | **New** — desiccant-age overlay script per tray/tag |
| `automations/wled_3dprinter_idle_telemetry_overlays.yaml` | **New** — idle telemetry trigger automation |
| `automations/wled_3dprinter_state_machine_orchestrator.yaml` | **Modified** — calls idle overlay coordinator when state is `S1_IDLE` |
| `wled_loader.yaml` | **Modified** — adds `input_number` helper loader |

### 3.5: Phase 3 Validation

| Test | Expected |
|------|----------|
| **3.1 — Progress bars** | |
| Enter S3_PRINTING | Seg 0/1 dim white base, Seg 2 slow green breathe |
| Print at 50% | Seg 0 half-filled green on white |
| Layer 25/100 | Seg 1 ~25% filled blue on white |
| Pause (user) | Seg 2 overrides to yellow; segs 0/1 retain progress (preset 105) |
| Pause (error) | Seg 2 overrides to red; segs 0/1 retain progress (preset 106) |
| Resume from pause | Progress overlay restores within ~2.5s |
| **3.2 — Active tray** | |
| Print with tray A1 | Tag segment 5 shows filament color |
| Switch from A1 to B2 mid-print | Segment 5 returns to neutral; segment 11 lights up |
| **3.4 — Telemetry** | |
| Idle with low filament in A3 | Only tag 7 pulses orange (idle overlay) |
| Start print after idle overlay | Overlay suppressed; printing preset takes over |

---

## Phase 4: Print/Error Telemetry Completion

**Goal**: Convert key print/error scenarios from partial to fully targeted behavior (tray-aware where possible) without dynamic segment remap.

### 4.1: Affected-Tray Error Targeting

**Status**: In progress (v2 tray-fan-out + error differentiation live)

Implement:
1. Parse fault context to identify one or more affected trays (runout/jam/AMS fault).
2. Overlay red/orange priority visuals on impacted tag-top segments during `S5_PAUSED_ERROR`.
3. Preserve door progress/status priority and existing pause behavior.

Initial implementation in repo:
- `scripts/wled_3dprinter_apply_error_tray_overlay-script.yaml` (new)
- `automations/wled_3dprinter_error_tray_overlay.yaml` (new)
- `automations/wled_3dprinter_state_machine_orchestrator.yaml` (updated hook for `S5_PAUSED_ERROR`)

Current scope (v2):
- Parses tray references (`A1..B4`) from pause/error context and supports multi-tray tag fan-out when available.
- Falls back to active-tray targeting when no explicit tray token is present.
- For `ams_lost`, expands to the full affected AMS bank (`A1-A4` or `B1-B4`) when bank context is known.
- Differentiates visuals by error class (`runout`, `jam`, `ams_lost`, `first_layer`, `generic`) with distinct color/effect profiles.

Targets from scenario matrix:
- `Filament runout` (Partial -> closer to Implemented)
- `Filament tangle/jam` (Partial -> closer to Implemented)
- `AMS communication error` (Partial -> closer to Implemented)
- `Print paused (error)` affected-tray specificity

### 4.2: Feed/Selection Context Enhancements

Implement:
1. Add tray overlay logic for `filament_loading` / `filament_unloading` stages.
2. Add pre-print tray-selected visual (idle/prep-safe, suppress during higher-tier events).
3. Keep all overlays tier-aware so T1/T0 events always preempt.

Targets from scenario matrix:
- `Filament loading` (Partial)
- `Filament unloading` (Partial)
- `AMS tray selected (pre-print)` (Not implemented)
- `AMS tray actively feeding` (Partial)

### 4.3: Multi-Tray Print Participation (Static)

Implement:
1. Identify trays used in current print from available print/spool context.
2. Apply static multi-tag highlighting for participating trays in `S3_PRINTING`.
3. Reuse tray-risk thresholds where possible without adding high-frequency segment churn.

Targets from scenario matrix:
- `Spools used in current print` (Not implemented)

---

## Phase 5: Environmental + Utility Scenarios

**Goal**: Close remaining non-core operational scenarios (environmental alerts, visibility modes, utility states).

### 5.1: Environmental Alert States

Implement:
1. Add explicit chamber temperature high/low alert overlays.
2. Add door-open-during-print alert path.
3. Add dedicated cooling-down visual distinct from prep.

Targets from scenario matrix:
- `Door open during print` (Not implemented)
- `High chamber temperature` (Not implemented)
- `Low chamber temperature` (Not implemented)
- `Cooling down / fans post-print` (Not implemented)

### 5.2: Humidity/Drying Operational Modes

Implement:
1. Add non-idle escalation path for humidity high when appropriate.
2. Add explicit AMS drying mode visual profile.
3. Keep current idle humidity/desiccant overlays as baseline behavior.

Targets from scenario matrix:
- `AMS drying mode` (Not implemented)
- `AMS humidity high` (Partial)
- `AMS humidity normal` (Partial)

### 5.3: Utility Visibility Modes

Implement:
1. Add remote monitoring mode (camera-friendly illumination profile).
2. Add night mode with strict brightness caps and preemption rules.
3. Optionally define a dedicated chamber/manual-light profile if separate from baseline states.

Targets from scenario matrix:
- `Remote monitoring mode` (Not implemented)
- `Night mode` (Not implemented)
- `Chamber light manual mode` (Partial)

---

## Phase 6: Advanced Dynamic Segment Strategy

**Goal**: Implement higher-complexity behavior that requires dynamic segment or preset-layout switching under the 16-segment cap.

### 6.1: Preset-Based Segment Switching (Moved from former 3.3)

Implement:
1. Presets `50-57` with tray-focused segment definitions (active tray top+bottom emphasis).
2. Automation to switch preset family on active-tray change with debounce (~500ms).
3. Fallback logic back to baseline state presets if remap fails.

### 6.2: Idle Rotation Scenes (R1/R2/R3)

Implement:
1. R1 desiccant scene, R2 filament-remaining scene, R3 decorative scene.
2. Scheduler helpers (`enabled`, `scene`, `interval`) and lock/debounce.
3. Strict suppression outside `S1_IDLE`.

### 6.3: Allocator + Tier Finalization

Implement:
1. Add bounded dynamic segment pool and eviction policy (tier-first, FIFO intra-tier).
2. Pin door progress/status + active tray signals.
3. Enforce full tier preemption (`T0`..`T5`) and emergency fallback view.

Targets from scenario matrix:
- `Tag top + tag bottom full highlight for active tray` (Degraded -> improved)
- `Per-tray tag-bottom semantics` (Degraded -> improved in focused/rotating modes)
- `AMS independent hygrometer detail` (Degraded -> improved)

---

## Rollback Plan

### Quick Disable
Turn off `input_boolean.wled_3dprinter_state_machine_enabled` to stop the orchestrator immediately. The DigQuad will hold its last preset state.

### Phase Rollback
| Phase | Rollback |
|-------|----------|
| Phase 1 | Disable toggle; remove package from `_feature_loaders.yaml` |
| Phase 2 | Re-upload skeleton presets (101–109 segment 0+1 only) from `wled/backups/digquad/2026-03-13 - 2 - Phase 1 Implemented/` or `wled_state_machine_presets_Digquad_skeleton.json` |
| Phase 3.1 | Remove progress overlay automation + script + rest_command; revert preset 104 segs 0–2 to solid green; remove orchestrator progress overlay call |
| Phase 3.2/3.4 | Remove active-tray and idle-telemetry overlay scripts/automations; core presets continue to work |
| Phases 4-5 | Disable new overlay automations first, then remove related scripts/helpers incrementally |
| Phase 6 | Revert to fixed-layout preset path (disable dynamic remap/allocator automations and restore baseline preset family) |

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
- [ ] Pre-deployment backup saved to `wled/backups/digquad/2026-03-13 - 3 - Pre Phase 2/`
- [ ] `wled_state_machine_presets_Digquad.json` merged into DigQuad
- [ ] Preset 100 (SM Base Layout) loaded — 15 segments established
- [ ] All 15 segments visible and addressable in WLED UI
- [ ] Each preset (101–109) styles all 15 segments appropriately
- [ ] Manual state override from Developer Tools works
- [ ] Full print lifecycle looks correct (idle → prep → printing → finishing → idle)
- [ ] Pause states (user and error) are visually distinct
- [ ] S0 Offline: only seg 2 (door top) shows amber
- [ ] S1 Idle: seg 2 blue breathing, AMS/tags/backgrounds soft white
- [ ] S3 Printing: segs 0–2 green, AMS white, tags soft white
- [ ] S5 Error: all segments red, door segments blinking
- [ ] Interior Lid Light confirmed on MagWLED (not DigQuad)

### Phase 3 (Overlays & Advanced)

#### 3.1 Progress Bar & Status Enhancement
- [x] `input_text.wled_3dprinter_digquad_ip` set to DigQuad IP
- [x] `rest_command.wled_3dprinter_digquad_update_state` reachable (Developer Tools → Services)
- [x] Percent effect ID 98 confirmed on DigQuad WLED build
- [x] Updated preset 104 deployed to DigQuad
- [x] S3_PRINTING shows dim white base on segs 0 and 1
- [x] Seg 2 shows very slow green breathe during printing
- [x] Print progress fills seg 0 green proportionally
- [x] Layer progress fills seg 1 blue proportionally
- [x] Pause (user) overrides all door segments to yellow
- [x] Pause (error) overrides all door segments to red
- [x] Resume restores progress overlay within ~2.5 seconds
- [x] Overlay skips gracefully when DigQuad IP is not set

#### 3.2 (Implemented)
- [x] Active tray tag highlights with filament color during printing
- [x] Inactive tags remain at neutral preset color
- [x] Tray switching mid-print updates the correct tag

#### 3.3 (Deferred / Optional Advanced)
- [ ] Preset-based segment switching (50-57) for active tray top+bottom control

#### 3.4 (Implemented)
- [x] Idle overlays appear only in idle state
- [x] Overlays suppress during non-idle states
- [x] Tray risk thresholds mirror AMS tray dashboard logic
- [x] Desiccant status mapping mirrors AMS tray dashboard logic

### Phase 4 (Print/Error Telemetry Completion)
- [ ] Affected-tray targeting for runout/jam/AMS comm error overlays in paused-error path
- [ ] Tray-aware overlays for loading/unloading stages
- [ ] Pre-print tray-selected visual implemented
- [ ] Multi-tray participation highlight for current print implemented

### Phase 5 (Environmental + Utility)
- [ ] Cooling-down visual separated from prep visuals
- [ ] Door-open-during-print alert path implemented
- [ ] Chamber temperature high/low alert paths implemented
- [ ] AMS drying mode visual implemented
- [ ] Non-idle humidity escalation policy implemented
- [ ] Remote monitoring mode implemented
- [ ] Night mode implemented

### Phase 6 (Dynamic Segment Strategy)
- [ ] Preset-based segment switching (50-57) implemented with fallback path
- [ ] Idle rotation scenes R1/R2/R3 implemented and scheduler-backed
- [ ] Dynamic segment allocator (tier-aware) implemented
- [ ] Tier preemption + pinned segment policy validated end-to-end

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

**Version**: 3.1 (Roadmap expanded to Phases 4-6 — 2026-03-15)  
**Phases**: 6 (Core ✅ → Segment Expansion → Core Overlays ✅/deferred → Telemetry Completion → Environmental/Utility → Advanced Dynamic)  
**Architecture**: HA State Machine → WLED Presets 100–109 + JSON API Overlays (+ optional dynamic segment remap in Phase 6)
