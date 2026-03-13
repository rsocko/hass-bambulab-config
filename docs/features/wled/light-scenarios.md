# Bambu P1S + Dual AMS LED Scenario Catalog

Consolidated master list for LED behavior on a single DigQuad WLED controller (5 strips, 16 segment max).

Use this document to align:
- Scenario definitions
- Zone behavior expectations
- Segment-limit trade-offs
- Preset and automation strategy

See also:
- `docs/features/wled/digquad-led-segments.md`
- `docs/features/wled/CONTROLLER_ALLOCATION_RECOMMENDATION.md`

## 1. Scope and Constraints

### Hardware scope
- Printer: Bambu P1S
- AMS: Dual AMS (A1-A4 and B1-B4)
- Controller: Single DigQuad
- LED outputs in use: 5 (GPIO 15, 1, 3, 16, 4)
- WLED segment limit: 16 total

### Practical planning assumptions
- Keep one neutral/base visual state available at all times.
- Reserve per-tray granularity for tag tops first (highest value signal).
- Treat tag bottoms, hygrometers, and tray bottoms as "background" unless an alert requires override.
- Prefer state overlays over full segment-layout swaps when possible.

## 2. LED Function Map (Consolidated)

| Zone | Function priority |
|------|-------------------|
| Tag top (per tray) | Active tray, tray used in current print, filament color mapping, runout/error targeting |
| Tag bottom | Filament remaining, desiccant age, secondary error indicator |
| AMS tray top | Spool illumination, active spool emphasis, loading/unloading animation |
| AMS tray bottom/front | Ambient spool visibility, secondary active/error reinforcement |
| Hygrometers (top/bottom) | Humidity visibility, high-humidity warning, drying-mode confirmation |
| Printer door bottom | Print progress bar by percent complete |
| Printer door left/top | Print state and severity indicator (printing, paused, error, complete) |
| Printer interior/lid | Print visibility for camera and operator, high-level state tint |

## 3. Scenario Catalog (Cleaned + Merged)

Legend:
- `Priority`: `P1` critical safety/error, `P2` print workflow, `P3` utility/info, `P4` aesthetic
- `Granularity`: minimum useful control level
- `Limit risk`: likelihood of colliding with 16-segment cap on fixed layout

| Scenario                           | Priority | Recommended behavior                                                                     | Granularity needed                         | Limit risk |
| ---------------------------------- | -------- | ---------------------------------------------------------------------------------------- | ------------------------------------------ | ---------- |
| Printer offline / unreachable      | P2       | Door dim amber, most other zones off                                                     | Global + door status                       | Low        |
| Printer idle / ready (reset state) | P2       | Neutral white base, soft blue door status                                                | Global + door status                       | Low        |
| Printer busy (general non-idle)    | P2       | Medium white + state-color door                                                          | Global + door status                       | Low        |
| Heating bed                        | P2       | Orange emphasis (door pulse)                                                             | Door status + optional lid                 | Low        |
| Heating nozzle                     | P2       | Yellow emphasis (door pulse)                                                             | Door status + optional lid                 | Low        |
| Bed leveling / lidar               | P2       | Blue pulse/chase                                                                         | Door status                                | Low        |
| Purge line / nozzle cleaning       | P2       | Cyan pulse                                                                               | Door status                                | Low        |
| Printing (base)                    | P2       | Door progress + green status + active tray color                                         | Door progress + per-tag-top                | Medium     |
| Print paused (user)                | P2       | Yellow blink/pulse                                                                       | Door status + optional global              | Low        |
| Print paused (error)               | P1       | Red strobe + affected tray red                                                           | Door status + per-tag-top                  | Medium     |
| Print finished                     | P2       | Green pulse then return to ready                                                         | Door status + optional used-tray highlight | Low        |
| Cooling down / fans post-print     | P3       | Dim blue                                                                                 | Global or door status                      | Low        |
| Filament runout                    | P1       | Door red alert + affected tray red                                                       | Per-tag-top targeting                      | Medium     |
| Filament tangle / jam              | P1       | Orange strobe, active tray emphasis                                                      | Per-tag-top targeting                      | Medium     |
| AMS communication error            | P1       | Purple AMS alert + door status                                                           | Per-AMS grouping preferred                 | Medium     |
| Temperature fault                  | P1       | Global red/high visibility                                                               | Global + door status                       | Low        |
| Door open during print             | P1       | Bright white visibility and caution pattern                                              | Door + lid/global                          | Low        |
| Filament loading                   | P2       | Blue chase + active tray tag                                                             | Per-tag-top + optional AMS top             | Medium     |
| Filament unloading                 | P2       | Teal chase + active tray tag                                                             | Per-tag-top + optional AMS top             | Medium     |
| AMS drying mode                    | P3       | Warm amber AMS + bright hygrometer                                                       | Per-AMS + hygrometer                       | High       |
| AMS humidity high                  | P1       | Red hygrometer + AMS pulse                                                               | Per-AMS hygrometer ideal                   | High       |
| AMS humidity normal                | P3       | White hygrometer/base                                                                    | Per-AMS hygrometer ideal                   | High       |
| AMS tray selected (pre-print)      | P2       | Selected tray in filament color                                                          | Per-tag-top                                | Medium     |
| AMS tray actively feeding          | P2       | Bright active tray + subdued others                                                      | Per-tag-top                                | Medium     |
| Active spool (A1..B4 variants)     | P2       | Highlight active tag top and corresponding spool zone                                    | Per-tag-top + per-tray AMS top is ideal    | High       |
| Spools used in current print       | P3       | Highlight all participating trays with shortage-risk color logic from AMS tray dashboard | Multi-tag-top                              | High       |
| Spool empty (multi-tray possible)  | P1       | Highlight one or more affected trays simultaneously                                      | Multi-tag-top simultaneous                 | High       |
| Spool desiccant age warning        | P3       | Age color bands (yellow/orange/red), idle rotation scene only                            | Tag bottom per tray ideal                  | Medium     |
| Chamber light manual mode          | P3       | White visibility preset                                                                  | Global                                     | Low        |
| Nozzle cleaning required           | P3       | Orange maintenance pulse                                                                 | Door status + optional lid                 | Low        |
| High chamber temperature           | P1       | Red pulse warning                                                                        | Door/lid/global                            | Low        |
| Low chamber temperature            | P3       | Blue cool warning                                                                        | Door/lid/global                            | Low        |
| Power loss recovery                | P1       | Purple recovery pulse                                                                    | Door/lid/global                            | Low        |
| Remote monitoring mode             | P3       | Bright white for camera                                                                  | Global/lid + door                          | Low        |
| Night mode                         | P3       | Very dim warm white or off                                                               | Global                                     | Low        |
| Show mode                          | P4       | Aesthetic motion pattern                                                                 | Global + optional AMS effects              | Medium     |

## 4. Scenarios Most Likely to Hit 16-Segment Limits

These scenarios are the main risk areas on fixed segment layout with all 5 strips on one DigQuad:

1. `Per-tray AMS top` plus `per-tray tag top` plus `per-tray tag bottom` in one static layout.
2. Independent hygrometer control for AMS1 and AMS2 while also keeping independent tag bottoms.
3. Simultaneous multi-tray highlight with unique colors for "spools used in current print" when also preserving active progress/status segments.
4. Desiccant-age visualization on tag bottoms per tray during idle scenes (if combined with hygrometer detail).
5. Separate left and top front-door status segments instead of merged status segment.

### Recommended fixed-layout priority under limit
1. Keep `door bottom progress` and `door status` independent.
2. Keep `8 tag tops` individually addressable.
3. Keep AMS lid top/bottom as combined segments per AMS unless you adopt dynamic segment presets.
4. Merge hygrometers and non-critical tag bottoms into neutral/background where possible.

### Scenario Capability Matrix

Legend:
- `Supported`: works as intended
- `Degraded`: works with reduced granularity
- `Not combinable`: cannot be active with all requested details at the same time

| Scenario or Feature | Fixed 15-seg layout | Hybrid dynamic/preset layout | Notes |
|---------------------|---------------------|------------------------------|-------|
| Door progress + door status | Supported | Supported | Keep as always-on core behavior |
| Active tray highlight (8 tag tops) | Supported | Supported | Primary per-tray signal path |
| Spools used in current print (up to 8 tags) | Supported (static colors) | Supported (static or mixed effects) | Prefer static colors when many trays are active |
| Multi-tray runout/error indication | Supported | Supported | Use tag-top priority for targeting |
| Per-tray AMS top loading animation | Degraded | Supported | Fixed layout combines AMS top per AMS unit |
| Per-tray tag bottom semantics (filament %, desiccant) | Degraded | Supported | Treat as idle-rotation telemetry in active print states |
| Per-tag static progress bar (filament %) on tag tops | Supported (low resolution) | Supported | Feasible when each tag segment is individually addressable; typically 12-14 LEDs per tag |
| AMS1 and AMS2 independent hygrometer alerts | Degraded | Supported | Dynamic strategy can allocate per-AMS alert segments |
| Tag top + tag bottom full highlight for active tray | Degraded | Supported | Use tray-focused preset family or dynamic segment remap |
| Simultaneous full per-tray AMS top + full per-tray tag bottom + independent hygrometers | Not combinable | Degraded | Keep tag-bottom telemetry idle-only; dynamic can time-slice alerts only |
| Show mode + detailed operational telemetry at once | Not combinable | Degraded | Treat show mode as mutually exclusive with high-detail telemetry |

### Non-Combinable Scenario Sets (Without Prioritization)

These combinations exceed practical 16-segment concurrency even with careful fixed mapping:

1. Full per-tray AMS top animation + full per-tray tag bottom metrics + independent hygrometers + door progress/status.
2. Full active print telemetry + full decorative show-mode segmentation.
3. Simultaneous multi-tray detailed bottom metrics and per-tray AMS top effects for all trays.

### Combination Rules (Recommended)

1. `Safety and errors` override all decorative and secondary telemetry effects.
2. `Door progress/status` is never evicted by dynamic segments.
3. `Tag top tray targeting` is preferred over `tag bottom detail` when segment budget is tight.
4. `Hygrometer alerts` use temporary override segments only during alert windows.
5. `Show mode` only runs when printer state is idle and no active warnings exist.
6. `Desiccant age` and `filament remaining` scenes are idle-only and are suppressed in prep/printing/paused error states.

### Print-Weight Risk Threshold Logic (For Trays Used in Current Print)

Use the same threshold model as the `AMS_Tray_Details` dashboard logic:

1. `Red pulsing` (critical): `remaining_weight < print_weight`.
2. `Orange` (warning): `remaining_weight < print_weight * 1.1`.
3. `Yellow` (caution): `remaining_weight < print_weight * 1.2`.
4. `Normal tray color` (sufficient): `remaining_weight >= print_weight * 1.2`.

Behavior recommendation for trays in current print:

1. Tag top remains the primary indicator.
2. Critical shortage state uses pulse/strobe-style motion only for red state.
3. Orange/yellow states should remain readable and calmer (solid or gentle pulse).

## 5. Smart Defaults and Partial Overrides

Your idea is valid and useful if you enforce one rule: every scenario starts from a known base and only overrides what must change.

### Pattern: `Reset base` + `Scenario overlay`
1. Apply a `Reset/Ready` preset:
	- Power on all relevant LEDs.
	- Set neutral white (for example `#FFDCB4` at 25-40%).
	- Use non-attention effects (`Solid`) for base segments.
2. Apply a scenario action that updates only selected segments:
	- Progress, status, active tray, and any alert segments.
	- Leave non-mentioned segments untouched so they remain neutral.

### Important caveat
- In WLED, many saved presets store full state. Loading a full-state preset may reset segments you did not intend to modify.
- For reliable partial behavior, prefer HA calls that update specific segments (`wled.effect` / JSON API segment payload) after base preset load.

### Where this works best
- Printing overlays (progress + active tray) on top of neutral ambient lighting.
- Error overlays where only a subset needs urgent colors.
- Night mode exit: return to base quickly without recomputing every zone.

## 6. Recommended Baseline Presets

Keep these as stable anchors:

1. `Preset 1 - Reset/Ready Base`
	- Neutral white on all always-on/background zones.
	- No aggressive effects.
2. `Preset 2 - Idle`
	- Same as base + gentle door status breathing.
3. `Preset 3 - Error Global`
	- High-visibility fallback when targeting data is unknown.
4. `Preset 4 - Night`
	- Very low brightness warm white or off.

Then do scenario-specific overlays via automation instead of exploding preset count.

## 7. Confirmed Design Decisions

1. `Spools used in current print` should support up to all 8 trays when feasible.
2. Filament color matching only needs one primary location, preferably `tag top`; AMS top color-match is optional.
3. Dark filament colors should be auto-adjusted for visibility (lightness floor).
4. AMS1 and AMS2 hygrometers must remain independently visible, but only one hygrometer row (top or bottom) must be actively used for status; the other can stay baseline.
5. Preset-based segment reconfiguration is allowed and encouraged for advanced tray-specific behavior.

## 8. Hybrid Control Pattern: Baseline Presets + Dynamic Segments

This is the recommended operating model for flexibility under the 16-segment cap.

### Control layers
1. `Baseline preset layer`
	- Stable presets for reset/idle/night/error fallback.
	- Defines ambient/default zones and neutral background.
2. `Dynamic overlay layer` (Home Assistant)
	- Creates or updates temporary segments only for actively differentiated state.
	- Removes or reverts temporary segments when state changes.

### Example: active tray handoff
1. Apply baseline (`Preset 1` or `Preset 2`).
2. Detect active tray change (`A2` -> `B1`).
3. Remove previous temporary tray segment(s) for `A2`.
4. Create temporary segment(s) for `B1` tag top (and optionally AMS tray top if chosen).
5. Apply active color/effect to new segment(s).
6. Keep non-target zones unchanged at baseline.

### Practical guardrails
- Keep a small, bounded pool of dynamic segments (for example 1-3 temporary IDs) to avoid churn.
- Reuse segment IDs instead of continuously creating new ones.
- Prefer one-tray active differentiation for motion effects; for `spools used in current print`, use static color highlights where possible.
- If dynamic update fails, fall back to baseline preset plus door status alert.

### Dark filament visibility policy
- Convert spool hex to HSV/HSL and enforce minimum perceived brightness.
- Suggested floor: target luminance equivalent to `35-45%` brightness at current global brightness cap.
- Keep hue as close as possible while lifting value/lightness.

### Hygrometer policy
- Reserve one independently addressable hygrometer segment per AMS for alerting.
- Keep the second hygrometer row in baseline neutral unless specific alert mode is active.
- Use humidity alerts as overrides, not permanent segment expansion.

## 9. LED Zone Summary

| LED Zone | Primary Uses |
|---------|--------------|
| Lid / interior LEDs | Visibility, camera illumination, broad state color |
| Front door bottom | Print progress bar and completion signaling |
| Front door left/top | High-visibility state and severity indication |
| AMS top LEDs | Spool illumination, loading/unloading context, AMS health |
| Filament tag top LEDs | Tray-specific identity, active tray, runout/error targeting |
| Filament tag bottom LEDs | Filament %, desiccant age, secondary warnings |
| Hygrometer LEDs | Humidity visibility and high-humidity warnings |

## 10. Priority Tiers and Preemption Order

Use these tiers to decide what stays visible when segment budget is constrained.

### Tier definitions

| Tier | Category | Goal | Typical scenarios |
|------|----------|------|-------------------|
| T0 | Safety Critical | Protect equipment and operator awareness | Temperature fault, door open during print, power recovery fault states |
| T1 | Print Error Recovery | Fast diagnosis and recovery | Filament runout, jam/tangle, AMS communication error, paused (error) |
| T2 | Active Print Telemetry | Real-time print context | Printing base, active tray/feed, loading/unloading, progress |
| T3 | Environmental and Maintenance | Preventive and support signals | Hygrometer alerts, desiccant age, cooling down, cleaning required |
| T4 | Utility and Visibility | Quality-of-life illumination | Idle, chamber/manual light, remote monitoring |
| T5 | Aesthetic | Decorative only | Show mode and non-operational effects |

### Tier mapping for scenario groups

| Scenario group | Assigned tier |
|----------------|---------------|
| Temperature fault, emergency error visuals | T0 |
| Runout, jam, AMS comm error, paused(error) | T1 |
| Printing state, progress bar, active tray highlights | T2 |
| Hygrometer and desiccant indicators, drying mode | T3 |
| Idle, monitoring, chamber visibility | T4 |
| Show mode | T5 |

### Global preemption order

When multiple states are active, resolve in this order:

1. `T0 Safety Critical`
2. `T1 Print Error Recovery`
3. `T2 Active Print Telemetry`
4. `T3 Environmental and Maintenance`
5. `T4 Utility and Visibility`
6. `T5 Aesthetic`

### Eviction rules for dynamic segments

1. Never evict `door progress` or `door status` segments.
2. Evict lowest tier dynamic segments first.
3. Evict oldest segment first within same tier (FIFO) unless pinned.
4. Pin active tray tag-top segments while print state is active.
5. During T0/T1 events, force show-mode off and clear T5 overlays.

## 11. State Machine Specification (Home Assistant)

This state machine defines deterministic behavior for baseline presets and dynamic overlays.

### Core states

| State ID | Description | Baseline preset |
|----------|-------------|-----------------|
| S0_OFFLINE | Printer unreachable/offline | Preset 1 variant (offline) |
| S1_IDLE | Printer ready and not printing | Preset 2 |
| S2_PREP | Heating, leveling, purge, pre-print prep | Preset 2 + prep overlays |
| S3_PRINTING | Active print execution | Preset 1/2 + telemetry overlays |
| S4_PAUSED_USER | User pause | Pause overlay |
| S5_PAUSED_ERROR | Error-induced pause | Error overlay |
| S6_FINISHING | Print complete and cooldown | Finish/cooldown overlay |
| S7_MAINTENANCE | Cleaning, filament change, maintenance routines | Maintenance overlay |
| S8_SHOW | Aesthetic mode (idle only) | Show preset |

### Super-state overlays (orthogonal)

These may run on top of core states when tier permits:

| Overlay ID | Tier | Trigger |
|------------|------|---------|
| O_ERR_TEMP | T0 | Temperature fault |
| O_ERR_DOOR | T0 | Door open during print |
| O_ERR_FILAMENT | T1 | Runout/jam/tangle |
| O_ERR_AMS_COMMS | T1 | AMS comm failure |
| O_ACTIVE_TRAY | T2 | Active tray/feed detected |
| O_USED_TRAYS | T2 | Trays used in current print known |
| O_USED_TRAY_RISK | T1 | Any used tray has remaining_weight below warning thresholds |
| O_HYGRO_A | T3 | AMS1 humidity alert |
| O_HYGRO_B | T3 | AMS2 humidity alert |
| O_DESICCANT | T3 | Desiccant age threshold exceeded (idle or maintenance only) |
| O_REMOTE_VIEW | T4 | Remote monitoring active |

### Transition events

| Event | From | To |
|-------|------|----|
| E_OFFLINE | any | S0_OFFLINE |
| E_IDLE | S0_OFFLINE,S6_FINISHING,S7_MAINTENANCE,S8_SHOW | S1_IDLE |
| E_PREP_START | S1_IDLE | S2_PREP |
| E_PRINT_START | S2_PREP,S1_IDLE | S3_PRINTING |
| E_PAUSE_USER | S3_PRINTING | S4_PAUSED_USER |
| E_PAUSE_ERROR | any printing-related | S5_PAUSED_ERROR |
| E_RESUME | S4_PAUSED_USER,S5_PAUSED_ERROR | S3_PRINTING |
| E_PRINT_DONE | S3_PRINTING | S6_FINISHING |
| E_MAINT_START | S1_IDLE,S6_FINISHING | S7_MAINTENANCE |
| E_SHOW_ON | S1_IDLE | S8_SHOW |
| E_SHOW_OFF | S8_SHOW | S1_IDLE |

### Entry actions by core state

| State | Required actions |
|-------|------------------|
| S0_OFFLINE | Apply offline baseline, clear non-critical overlays |
| S1_IDLE | Apply idle baseline, clear T2/T3/T5 dynamic segments |
| S2_PREP | Apply prep tint overlay, ensure progress/status core segments active, suppress idle telemetry scenes |
| S3_PRINTING | Apply print baseline, allocate O_ACTIVE_TRAY and O_USED_TRAYS as needed, suppress idle telemetry scenes |
| S4_PAUSED_USER | Apply paused-user overlay, keep progress visible, suppress idle telemetry scenes |
| S5_PAUSED_ERROR | Apply error overlay (T1), suppress T4/T5 overlays and idle telemetry scenes |
| S6_FINISHING | Apply finish pulse then cooldown overlay; release tray-specific dynamic segments |
| S7_MAINTENANCE | Apply maintenance overlay, keep safety overlay path available |
| S8_SHOW | Apply show preset only if no T0-T3 overlay is active |

### Dynamic segment allocator contract

| Field | Requirement |
|-------|-------------|
| Max temp segment pool | 1-3 IDs on DigQuad |
| Pinned segments | Door progress, door status, active tray top |
| Allocation policy | Tier first, then FIFO within same tier |
| Failure behavior | Revert to baseline + maintain T0/T1 overlays |
| Debounce | 200-500 ms on tray/preset remap transitions |

### Pseudocode flow

```text
on event:
	update core_state
	active_overlays = evaluate_overlays()
	ranked = sort_by_tier(active_overlays)
	apply_baseline_for(core_state)
	ensure_pinned_segments()
	for overlay in ranked:
		if allocator.can_fit(overlay):
			allocator.apply(overlay)
		else:
			allocator.evict_lowest_priority_until_fit(overlay)
			if allocator.can_fit(overlay):
				allocator.apply(overlay)
	if allocator.error:
		apply_fallback_error_safe_view()
```

### HA implementation guidance

1. Use one orchestrator automation/script as the single writer for WLED state.
2. Build input sensors/helpers that produce normalized events (`E_*`).
3. Use a short lockout/debounce to prevent rapid segment churn.
4. Log state transitions and segment allocations for troubleshooting.
5. Keep an emergency service/script to force baseline recovery.

### Used-Trajectory Risk Rendering Rules

Apply these rules inside `O_USED_TRAYS` / `O_USED_TRAY_RISK` overlays:

1. Compute risk per used tray from `remaining_weight` and `print_weight`.
2. If any used tray is in critical red state, elevate overlay handling to T1 behavior.
3. Render per-tray risk color on tag tops:
	- Red + pulse if critical.
	- Orange solid/gentle pulse for warning.
	- Yellow solid for caution.
4. Preserve active tray distinguishability (for example by brightness or secondary accent).
5. Suspend idle rotation scenes (`R1`/`R2`) while `O_USED_TRAYS` or `O_USED_TRAY_RISK` is active.

## 12. Idle Rotation Mode (No Active Print)

Idle Rotation Mode is recommended when printer core state is `S1_IDLE` and no T0/T1 overlays are active.

### Entry conditions

1. Core state is `S1_IDLE` for at least `N` minutes (recommended `2-5`).
2. No active T0/T1 event overlays.
3. No active maintenance action requiring fixed visibility.

### Exit/preemption conditions

1. Any transition to `S2_PREP`, `S3_PRINTING`, `S4_PAUSED_USER`, or `S5_PAUSED_ERROR`.
2. Any T0/T1 overlay event (safety or print error).
3. Manual override from UI/HA helper.

### Rotation scenes

#### R1: Desiccant Status

1. AMS lid segments: solid blue (mode indicator).
2. Tag indicators per tray: red/orange/yellow/green by desiccant age threshold logic from Home Assistant dashboard.
3. Duration: recommended `20-45` seconds.
4. Idle-only: do not render this scene in prep/printing states.

#### R2: Filament Remaining

1. AMS lid segments: solid white for spool visibility.
2. Tags per tray:
	- Preferred: static per-tag progress representation using the tag segment itself (filled fraction based on %).
	- Fallback: threshold color state per tray (green/yellow/orange/red) if effect behavior is inconsistent.
3. Duration: recommended `20-45` seconds.
4. Idle-only: filament-remaining visuals move to `O_USED_TRAY_RISK` in active print contexts.

#### R3: Decorative Idle

1. Low-priority ambient animation with restrained brightness.
2. Must be preemptible immediately by any higher-tier event.
3. Duration: recommended `20-45` seconds.

### Notes on "true bar" per tag feasibility

1. A static bar per tag is feasible if each tag is its own segment and the effect supports a settable static progress value.
2. Resolution is limited by segment length (typically 12-14 LEDs per tag), so bars step in coarse increments.
3. This is different from single-color-per-tag only in information density, not segment count.
4. Per-tag true bars on tag bottoms are not feasible in fixed layout when bottoms are combined.

### Rotation scheduler policy

1. Sequence: `R1 -> R2 -> R3 -> repeat`.
2. Persist current step index in HA helper to resume predictably after brief interruptions.
3. Use lock/debounce to avoid rapid scene thrashing.

### Future Alternative: AMS-Focus Rotation (One AMS at a Time)

This alternative is recommended if you want richer idle detail without permanently increasing segment pressure.

#### Concept

1. Focus AMS A while AMS B stays in a single ambient segment.
2. Then focus AMS B while AMS A stays ambient.
3. Rotate focus on a timer.

#### Focus mode behavior

1. Focused AMS:
	- Per-tag top details enabled.
	- Per-tag bottom details optionally enabled via temporary split/remap.
2. Non-focused AMS:
	- Single dull ambient segment for lid/tag background.
3. Recommended ambient look for non-focused AMS:
	- Soft warm white or dim blue at low brightness.

#### Suggested mapping for filament remaining

1. Tag top: percent/level indicator (static bar-like representation, color coded by thresholds).
2. Tag bottom: whole-tag color/status indicator for the focused AMS (optional pulse).
3. Non-focused AMS tag tops/bottoms: ambient only.

#### Trade-offs

Pros:
1. Higher detail per AMS without permanently consuming extra segments.
2. Better visual clarity while inspecting one AMS at a time.
3. Keeps dynamic complexity bounded compared to "everything detailed at once".

Cons:
1. Slower global awareness because only one AMS is detailed at a time.
2. Slightly more orchestration complexity than simple global idle rotation.
3. Requires careful timing so users can scan both AMS units quickly.

#### Timing recommendations

1. Focus dwell time per AMS: `15-30` seconds.
2. Full cycle (`AMS A` + `AMS B` + optional decorative scene): `40-90` seconds.
3. Immediate preemption for any T0/T1 event.

#### Recommendation status

1. Documented as a `future alternative` for advanced idle telemetry.
2. Use only in `S1_IDLE`.
3. Keep default idle rotation as the simpler baseline unless additional fidelity is needed.

### Suggested HA helpers

1. `input_boolean.wled_idle_rotation_enabled`
2. `input_select.wled_idle_rotation_scene` (`R1`,`R2`,`R3`)
3. `input_number.wled_idle_rotation_interval_sec`
4. `input_datetime.wled_idle_rotation_last_change`

### Safety guardrails

1. Clamp brightness for idle scenes to avoid unnecessary heat/power draw.
2. Validate tray data availability before applying per-tag logic.
3. On data error, revert to baseline idle preset and retry next interval.
