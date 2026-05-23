# Smart Printer Status Sensor

**File:** [homeassistant/packages/3d_printing/core/template_sensors/smart_status.yaml](../../../../homeassistant/packages/3d_printing/core/template_sensors/smart_status.yaml)  
**Sensor:** `sensor.ntk_ryansoffice_3dprinter_smart_status`

This template sensor combines the two raw ha-bambulab integration entities:

| Source entity | ha-bambulab attribute | What it represents |
|---|---|---|
| `sensor.ntk_ryansoffice_3dprinter_print_status` | `gcode_state` | High-level print job state from the printer's G-code controller |
| `sensor.ntk_ryansoffice_3dprinter_current_stage` | stage description string | Current activity stage within a print job |

into a single, clean state value such as `Heating Bed`, `Bed Leveling`, `Printing`, or `Paused - Filament Runout`.

---

## Priority rule: stage over status

The key design principle (and the bug that was fixed) is that **`current_stage` takes priority over `print_status`** for determining the displayed state. The printer's `print_status` stays `running` throughout heating, bed leveling, calibration, and many other preparatory steps — so checking it first would always show "Printing" instead of what the printer is actually doing.

This matches how [Bambuddy](https://github.com/maziggy/bambuddy) works: its `get_stage_name()` function resolves `stg_cur` first, and only falls back to the generic state label (`RUNNING` → "Printing") when no specific stage is active.

---

## Sensor attributes

| Attribute | Description |
|---|---|
| `detail` | Friendly stage label while preparing/printing; `Unmapped: status="...", stage="..."` for unknown combinations |
| `status_raw` | Raw value of `print_status` |
| `stage_raw` | Raw value of `current_stage` |
| `status_class` | Normalised class for UI colour/icon logic (see table below) |
| `is_active` | `true` when the printer is actively printing or preparing |

### `status_class` values

| Class | When applied |
|---|---|
| `printing` | `print_status` is `running` or `printing`, or `current_stage` is `printing` |
| `preparing` | `print_status` is `prepare`, `slicing`, or `init` |
| `paused` | Any paused condition (status or stage) |
| `finished` | `print_status` is `finish` |
| `failed` | `print_status` is `failed` |
| `heating` | Stage is any heating or cooling-chamber stage |
| `leveling` | Stage is any bed leveling stage |
| `idle` | Both status and stage are `idle` |
| `offline` | Status or stage is `offline` |
| `unknown` | Status or stage is `unknown`, `unavailable`, `none`, or empty |
| `unmapped` | Combination falls through all known checks |

---

## Stage mapping table

All stage strings defined by ha-bambulab's `CURRENT_STAGE_IDS`, mapped to the sensor's displayed state and the equivalent label Bambuddy uses.

> **Last verified:** 2026-05-12 against ha-bambulab `const.py` v2.2.22 (stages 0–58, 59–66, 67–76, 77, -1, 255) and Bambuddy `bambu_mqtt.py` `STAGE_NAMES`.
>
> ha-bambulab v2.2.22 ([PR #1975](https://github.com/greghesp/ha-bambulab/pull/1975)) added stage IDs 67–76 — see the bucketed entries marked **(v2.2.22)** below.

> **Note on `check_plaform`**: This is the exact string emitted by the ha-bambulab integration (the upstream typo is preserved intentionally so the match works).

### Heating / Cooling

| `current_stage` string | Sensor state | Bambuddy label | `status_class` |
|---|---|---|---|
| `heatbed_preheating` | Heating Bed | Heatbed preheating | `heating` |
| `heating_hotend` | Heating Nozzle | Heating nozzle | `heating` |
| `heating_chamber` | Heating Chamber | Heating chamber | `heating` |
| `heated_bedcooling` | Cooling Bed | Cooling heatbed | `heating` |
| `cooling_chamber` | Cooling Chamber | Cooling chamber | `heating` |
| `cooling_nozzle` | **Cooling Nozzle** *(v2.2.22)* | Cooling nozzle | `heating` |
| `waiting_for_heatbed_temperature` | **Waiting for Bed Temp** | Waiting for heatbed temperature | `heating` |
| `thermal_preconditioning` | **Thermal Preconditioning** | Thermal Preconditioning | `heating` |

### Bed Leveling

| `current_stage` string | Sensor state | Bambuddy label | `status_class` |
|---|---|---|---|
| `auto_bed_leveling` | Bed Leveling | Auto bed leveling | `leveling` |
| `bed_level_phase_1` | Bed Leveling | Auto bed leveling - phase 1 | `leveling` |
| `bed_level_phase_2` | Bed Leveling | Auto bed leveling - phase 2 | `leveling` |
| `bed_level_high_temperature` | Bed Leveling | High temperature auto bed leveling | `leveling` |
| `scanning_bed_surface` | Bed Leveling | Scanning bed surface | `leveling` |
| `measuring_surface` | **Bed Leveling** | Measuring Surface | `leveling` |
| `build_plate_alignment_detection` | **Bed Leveling** *(v2.2.22)* | Build plate alignment detection | `leveling` |

### Homing / Checks

| `current_stage` string | Sensor state | Bambuddy label | `status_class` |
|---|---|---|---|
| `homing_toolhead` | Homing / Checks | Homing toolhead | `printing` |
| `check_door_and_cover` | Homing / Checks | Auto Check: Door and Upper Cover | `printing` |
| `check_quick_release` | Homing / Checks | Auto Check: Quick Release Lever | `printing` |
| `check_plaform` | Homing / Checks | Auto Check: Platform | `printing` |
| `check_birdeye_camera_position` | Homing / Checks | Confirming BirdsEye Camera location | `printing` |
| `check_material` | **Homing / Checks** | Auto Check: Material | `printing` |
| `check_material_position` | **Homing / Checks** | Auto Check: Material Position | `printing` |
| `moving_toolhead_to_center_of_heatbed` | **Homing / Checks** *(v2.2.22)* | Moving toolhead to center of heatbed | `printing` |
| `hotend_type_detection` | **Homing / Checks** *(v2.2.22)* | Hotend type detection | `printing` |
| `heatbed_surface_foreign_object_detection` | **Homing / Checks** *(v2.2.22)* | Heatbed surface foreign object detection | `printing` |
| `heatbed_underside_foreign_object_detection` | **Homing / Checks** *(v2.2.22)* | Heatbed underside foreign object detection | `printing` |

### Nozzle Prep

| `current_stage` string | Sensor state | Bambuddy label | `status_class` |
|---|---|---|---|
| `cleaning_nozzle_tip` | Nozzle Prep | Cleaning nozzle tip | `printing` |
| `checking_extruder_temperature` | Nozzle Prep | Checking extruder temperature | `printing` |
| `moving_toolhead_above_purge_chute` | **Nozzle Prep** *(v2.2.22)* | Moving toolhead above purge chute | `printing` |
| `pre_extrusion_before_printing` | **Nozzle Prep** *(v2.2.22)* | Pre-extrusion before printing | `printing` |

### Filament Change

| `current_stage` string | Sensor state | Bambuddy label | `status_class` |
|---|---|---|---|
| `changing_filament` | Filament Change | Changing filament | `printing` |
| `filament_loading` | Filament Change | Filament loading | `printing` |
| `filament_unloading` | Filament Change | Filament unloading | `printing` |

### Calibration

| `current_stage` string | Sensor state | Bambuddy label | `status_class` |
|---|---|---|---|
| `calibrating_extrusion` | Calibration | Calibrating dynamic flow | `printing` |
| `calibrating_extrusion_flow` | Calibration | Calibrating flow ratio | `printing` |
| `calibrating_micro_lidar` | Calibration | Calibrating Micro Lidar | `printing` |
| `calibrating_motor_noise` | Calibration | Motor noise cancellation | `printing` |
| `absolute_accuracy_calibration` | Calibration | Enhancing motion precision | `printing` |
| `check_absolute_accuracy_before_calibration` | Calibration | Measuring motion precision | `printing` |
| `check_absolute_accuracy_after_calibration` | Calibration | Measure motion accuracy | `printing` |
| `calibrate_nozzle_offset` | Calibration | Nozzle offset calibration | `printing` |
| `laser_calibration` | Calibration | Laser Calibration | `printing` |
| `calibrate_birdeye_camera` | Calibration | Calibrating BirdsEye Camera | `printing` |
| `sweeping_xy_mech_mode` | Calibration | Vibration compensation | `printing` |
| `motor_noise_showoff` | Calibration | Motor noise showoff | `printing` |
| `calibrating_live_view_camera` | **Calibration** | Live View Camera Calibration | `printing` |
| `calibrating_cutter_model_offset` | **Calibration** | Cutting Module Offset Calibration | `printing` |
| `measuring_rotary_attachment` | **Calibration** *(v2.2.22)* | Measuring rotary attachment | `printing` |
| `active_arc_fitting` | **Calibration** *(v2.2.22)* | Active arc fitting | `printing` |

### Printing / Inspection

| `current_stage` string | Sensor state | Bambuddy label | `status_class` |
|---|---|---|---|
| `printing` | Printing | Printing | `printing` |
| `identifying_build_plate_type` | Identifying Build Plate | Identifying build plate type | `printing` |
| `print_calibration_lines` | Printing Calibration Lines | Printing calibration lines | `printing` |
| `inspecting_first_layer` | Inspecting First Layer | Inspecting first layer | `printing` |

### Paused — explicitly named

| `current_stage` string | Sensor state (current) | **Sensor state (recommended)** | Bambuddy label | `status_class` |
|---|---|---|---|---|
| `m400_pause` | Paused | Paused | M400 pause | `paused` |
| `paused_filament_runout` | Paused - Filament Runout | *(no change)* | Paused (filament ran out) | `paused` |
| `paused_nozzle_clog` | Paused - Nozzle Clog | *(no change)* | Pause (nozzle clog) | `paused` |
| `paused_first_layer_error` | Paused - First Layer Error | *(no change)* | Pause (first layer error) | `paused` |
| `paused_ams_lost` | Paused - AMS Lost | *(no change)* | Pause (AMS offline) | `paused` |
| `paused_user` | ~~Paused User~~ | **Paused - User** | Paused by the user | `paused` |
| `paused_front_cover_falling` | ~~Paused Front Cover Falling~~ | **Paused - Front Cover** | Pause (front cover fall off) | `paused` |
| `paused_skipped_step` | ~~Paused Skipped Step~~ | **Paused - Step Loss** | Pause (step loss) | `paused` |
| `paused_nozzle_temperature_malfunction` | ~~Paused Nozzle Temperature Malfunction~~ | **Paused - Nozzle Temp** | Pause (nozzle temperature malfunction) | `paused` |
| `paused_heat_bed_temperature_malfunction` | ~~Paused Heat Bed Temperature Malfunction~~ | **Paused - Bed Temp** | Pause (heatbed temperature malfunction) | `paused` |
| `paused_low_fan_speed_heat_break` | ~~Paused Low Fan Speed Heat Break~~ | **Paused - Heatbreak Fan** | Pause (low speed of the heatbreak fan) | `paused` |
| `paused_chamber_temperature_control_error` | ~~Paused Chamber Temperature Control Error~~ | **Paused - Chamber Temp** | Pause (chamber temperature control problem) | `paused` |
| `paused_user_gcode` | ~~Paused User Gcode~~ | **Paused - G-code** | Pause (Gcode inserted by user) | `paused` |
| `paused_nozzle_filament_covered_detected` | ~~Paused Nozzle Filament Covered Detected~~ | **Paused - Nozzle Clumping** | Pause (nozzle clumping) | `paused` |
| `paused_cutter_error` | ~~Paused Cutter Error~~ | **Paused - Cutter Error** | Pause (cutter error) | `paused` |

### Idle / Offline

| `current_stage` string | Sensor state | `status_class` |
|---|---|---|
| `idle` | Idle | `idle` |
| `offline` | Offline | `offline` |

### `print_status` values (when no stage drives the display)

| `print_status` | Sensor state | Bambuddy label | `status_class` |
|---|---|---|---|
| `running` | Printing *(stage fallback)* | Printing | `printing` |
| `printing` | Printing *(stage fallback)* | Printing | `printing` |
| `prepare` | Preparing Print | "Prepare" *(title-cased)* | `preparing` |
| `slicing` | Preparing Print | "Slicing" *(title-cased)* | `preparing` |
| `init` | Preparing Print | "Init" *(title-cased)* | `preparing` |
| `pause` / `paused` | Paused | Paused | `paused` |
| `finish` | Print Finished | Finished | `finished` |
| `failed` | Print Failed | Failed | `failed` |
| `idle` | Idle *(when stage is also idle)* | Idle | `idle` |
| `offline` | Offline | — | `offline` |
| `unknown` | Unknown Printer State | — | `unknown` |

> **Difference from Bambuddy**: Bambuddy shows "Prepare", "Slicing", "Init" (title-cased raw values) for those statuses. This sensor maps all three to "Preparing Print" for a more user-friendly display.

---

## Review findings (2026-03-19)

### ha-bambulab v2.2.22 update (2026-05-12)

Release [v2.2.22](https://github.com/greghesp/ha-bambulab/releases/tag/v2.2.22) added 10 new stage IDs (67–76) via [PR #1975](https://github.com/greghesp/ha-bambulab/pull/1975). All 10 are now mapped in [smart_status.yaml](../../../../homeassistant/packages/3d_printing/core/template_sensors/smart_status.yaml) and in the stage tables above (look for the **(v2.2.22)** badge). New display labels added:

- `Cooling Nozzle` (`status_class: heating`)
- `Bed Leveling` for `build_plate_alignment_detection` (`status_class: leveling`)
- `Homing / Checks` for `moving_toolhead_to_center_of_heatbed`, `hotend_type_detection`, `heatbed_surface_foreign_object_detection`, `heatbed_underside_foreign_object_detection`
- `Nozzle Prep` for `moving_toolhead_above_purge_chute`, `pre_extrusion_before_printing`
- `Calibration` for `measuring_rotary_attachment`, `active_arc_fitting`

> **Unrelated breaking change in v2.2.22**: `sensor.<printer>_start_time` and `sensor.<printer>_end_time` switched from naive-local strings to `device_class: timestamp` (UTC ISO-8601). All numeric/`as_timestamp()` consumers in this repo are unaffected; the one consumer that called `.date()` / `.strftime()` directly ([print_end_time_friendly.yaml](../../../../homeassistant/packages/3d_printing/core/template_sensors/print_end_time_friendly.yaml)) was patched to apply `| as_local` before formatting. See [release notes](https://github.com/greghesp/ha-bambulab/releases/tag/v2.2.22) and [PR #1959](https://github.com/greghesp/ha-bambulab/pull/1959).

### Finding 1: Missing stages (52–58) — ha-bambulab added, sensor not updated

ha-bambulab's `CURRENT_STAGE_IDS` now includes stages 52–58. These are NOT in the sensor's `known_stages` list or display branches and will trigger "Unmapped Printer State":

| Stage ID | ha-bambulab string | Bambuddy label | Recommended group | Recommended state |
|---|---|---|---|---|
| 52 | `check_material` | Auto Check: Material | Homing / Checks | Homing / Checks |
| 53 | `calibrating_live_view_camera` | Live View Camera Calibration | Calibration | Calibration |
| 54 | `waiting_for_heatbed_temperature` | Waiting for heatbed temperature | Heating | Waiting for Bed Temp |
| 55 | `check_material_position` | Auto Check: Material Position | Homing / Checks | Homing / Checks |
| 56 | `calibrating_cutter_model_offset` | Cutting Module Offset Calibration | Calibration | Calibration |
| 57 | `measuring_surface` | Measuring Surface | Bed Leveling | Bed Leveling |
| 58 | `thermal_preconditioning` | Thermal Preconditioning | Heating | Thermal Preconditioning |

**Action:** Add all 7 stages to both the display branches and `known_stages`.

### Finding 2: Paused wildcard produces inconsistent, unfriendly labels

Only 4 `paused_*` stages have explicit "Paused - Reason" formatting. The remaining 11 paused stages fall through to the `stage.startswith('paused_')` wildcard, which renders them as title-cased raw names (e.g., "Paused Nozzle Filament Covered Detected" instead of "Paused - Nozzle Clumping").

**Problems:**
- **No dash separator** — explicit branches use "Paused - X", wildcard produces "Paused X"
- **Labels mirror internal naming** — "Paused Low Fan Speed Heat Break" is not user-friendly
- **Inconsistent length** — some are 5+ words long, others are 2 words

**Action:** Add explicit branches for ALL paused stages with human-friendly "Paused - Reason" labels. Keep the `startswith('paused_')` wildcard as a fallback for future unknown paused stages, but add a dash separator:
```jinja
{% elif stage.startswith('paused_') %}Paused - {{ stage | replace('paused_', '') | replace('_', ' ') | title }}
```

### Finding 3: `detail` attribute uses raw title-cased stage names

The `detail` attribute produces `{{ stage_label }}` which is `stage | replace('_', ' ') | title`. This generates labels like:
- "Check Absolute Accuracy Before Calibration" (7 words)
- "Paused Nozzle Filament Covered Detected" (no dash, unclear meaning)
- "Heated Bedcooling" (inconsistent compounding)

**Action:** Consider building a lookup mapping in `detail` that matches the human-readable labels used for `state`. At minimum, paused stages in `detail` should use the same "Paused - Reason" format.

### Finding 4: Bambuddy has stages not yet in ha-bambulab

Bambuddy maps stages 59–66, 74, and 77 that ha-bambulab does not yet have. These come from newer H2D/H2C firmware:

| Stage ID | Bambuddy label | Notes |
|---|---|---|
| 59 | Homing Blade Holder | H2C tool changer |
| 60 | Calibrating Camera Offset | H2D/H2C |
| 61 | Calibrating Blade Holder Position | H2C tool changer |
| 62 | Hotend Pick and Place Test | H2C tool changer |
| 63 | Waiting for Chamber temperature | H2D heating |
| 64 | Preparing Hotend | H2D/H2C |
| 65 | Calibrating nozzle clumping detection | AI detection |
| 66 | Purifying the chamber air | Air purification |
| 74 | Preparing | H2D startup |
| 77 | Preparing AMS | AMS prep |

When ha-bambulab adds these, they will surface as `Unmapped Printer State`. The alert automation will catch them, but the mapping table above provides the labels to use.

### Finding 5: `status_class` groups everything non-heating/leveling as `printing`

Stages for homing, nozzle prep, filament change, calibration, and checks all resolve to `status_class = 'printing'`. This means downstream consumers (dashboards, WLED) cannot distinguish "actively printing" from "calibrating" at the class level.

**Impact:** Low in practice — the WLED orchestrator already uses direct `smart_status` string matching and `stage` checks for its event logic rather than `status_class`. Dashboards display `smart_status` state text directly. No change recommended unless a downstream consumer specifically needs finer-grained classes.

### Finding 6: `status`/`stage` combination constraints

Not every `(status, stage)` pair is possible. The printer MQTT protocol has these constraints:

| `gcode_state` | Expected `stg_cur` values | Notes |
|---|---|---|
| `idle` | Only `idle` (-1 or 255) | Printer is not doing anything |
| `offline` | N/A (integration-level) | Integration cannot reach printer |
| `prepare` | `idle` or very early stages | Brief transitional state |
| `slicing` | `idle` | Cloud-slicing in progress |
| `init` | `idle` or early stages | Print job initializing |
| `running` | **Any stage 0–58** | All stages occur while status is `running` |
| `pause` | **Any `paused_*` stage, `m400_pause`**, or `printing` (if AMS pause during feed) | Stage specifies the pause reason |
| `finish` | `idle` or `printing` (briefly) | `finish` persists until next print; stage returns to `idle` independently |
| `failed` | `idle` or last active stage | Stage may lag behind status briefly |

Key observation: **During an active print, `status` stays `running` and `stage` cycles through all the prep/calibration/printing phases.** The `status` only changes on pause, completion, or failure. This is why the sensor correctly checks stage first.

---

## Consistency with Bambuddy

The sensor is functionally equivalent to Bambuddy's display logic. Key mapping:

| Concept | Bambuddy (backend) | This sensor |
|---|---|---|
| Data source | `stg_cur` (numeric MQTT value) → `STAGE_NAMES[stg_cur]` | `current_stage` string (ha-bambulab converts numeric → string) |
| Priority rule | `stg_cur` first via `get_stage_name()`, then `gcode_state` fallback | Stage branches first, then `print_status` fallback |
| Specific pauses | Named labels ("Paused (filament ran out)", "Pause (nozzle clog)", etc.) | Same named labels; remaining pauses via `startswith('paused_')` wildcard |
| `prepare`/`slicing`/`init` | Title-cased raw value | "Preparing Print" (friendlier) |
| Unknown combinations | `"Unknown stage (N)"` fallback | `Unmapped Printer State` + `detail` shows raw values |

### Stages in Bambuddy not yet in ha-bambulab

Bambuddy's `STAGE_NAMES` includes stages 59–66, 74, and 77 (H2D, H2C, and newer hardware stages) that ha-bambulab's `CURRENT_STAGE_IDS` does not yet map to string values. If ha-bambulab adds them in a future release, they will appear as new `current_stage` string values not in this sensor's `known_stages` list, triggering `Unmapped Printer State`.

---

## Handling unknown values (future-proofing)

The sensor is designed to degrade gracefully when the ha-bambulab integration or Bambu Lab firmware introduces new values:

1. **`known_statuses` / `known_stages` lists** in the `detail` attribute enumerate every value this sensor was built against. Any `(status, stage)` combination containing a value outside those lists immediately surfaces as `Unmapped: status="...", stage="..."` in `detail`.

2. **Main `state`** falls through to `Unmapped Printer State` for any combination not matched by an explicit branch.

3. **Automation alert**: [homeassistant/packages/3d_printing/core/automations/smart-status-unmapped-alert.yaml](../../../../homeassistant/packages/3d_printing/core/automations/smart-status-unmapped-alert.yaml) triggers a persistent notification whenever the sensor enters `Unmapped Printer State`, with a 30-second debounce, system log entry, and auto-dismiss when the state clears.

To add support for a new value, either:
- Add it to the relevant display branch in [homeassistant/packages/3d_printing/core/template_sensors/smart_status.yaml](../../../../homeassistant/packages/3d_printing/core/template_sensors/smart_status.yaml), **and** add it to `known_stages` in the `detail` block.
- Or, if it is a new stage that logically fits an existing group (e.g., a new paused reason), the `paused_*` wildcard will catch it automatically — just add it to `known_stages`.

---

## Recommended code changes

See [smart-status-review-2026-03-19.md](../archive/smart-status-review-2026-03-19.md) for the complete change specification with exact before/after templates.





