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

This matches how [Bambuddy](https://github.com/maziggy/bambuddy) works: its `getStatusDisplay()` function checks `stg_cur_name` first, and only falls back to the generic state label (`RUNNING` → "Printing") when no specific stage is active.

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

All 52 stage strings defined by ha-bambulab's `CURRENT_STAGE_IDS` (as of the time this was written), mapped to the sensor's displayed state and the equivalent label Bambuddy uses.

> **Note on `check_plaform`**: This is the exact string emitted by the ha-bambulab integration (the upstream typo is preserved intentionally so the match works).

| `current_stage` string | Sensor state | Bambuddy label | `status_class` |
|---|---|---|---|
| `printing` | Printing | Printing | `printing` |
| `heatbed_preheating` | Heating Bed | Heatbed preheating | `heating` |
| `heating_hotend` | Heating Nozzle | Heating nozzle | `heating` |
| `heating_chamber` | Heating Chamber | Heating chamber | `heating` |
| `heated_bedcooling` | Cooling Bed | Cooling heatbed | `heating` |
| `cooling_chamber` | Cooling Chamber | Cooling chamber | `heating` |
| `auto_bed_leveling` | Bed Leveling | Auto bed leveling | `leveling` |
| `bed_level_phase_1` | Bed Leveling | Auto bed leveling - phase 1 | `leveling` |
| `bed_level_phase_2` | Bed Leveling | Auto bed leveling - phase 2 | `leveling` |
| `bed_level_high_temperature` | Bed Leveling | High temperature auto bed leveling | `leveling` |
| `scanning_bed_surface` | Bed Leveling | Scanning bed surface | `leveling` |
| `homing_toolhead` | Homing / Checks | Homing toolhead | `printing` |
| `check_door_and_cover` | Homing / Checks | Auto Check: Door and Upper Cover | `printing` |
| `check_quick_release` | Homing / Checks | Auto Check: Quick Release Lever | `printing` |
| `check_plaform` | Homing / Checks | Auto Check: Platform | `printing` |
| `check_birdeye_camera_position` | Homing / Checks | Confirming BirdsEye Camera location | `printing` |
| `cleaning_nozzle_tip` | Nozzle Prep | Cleaning nozzle tip | `printing` |
| `checking_extruder_temperature` | Nozzle Prep | Checking extruder temperature | `printing` |
| `changing_filament` | Filament Change | Changing filament | `printing` |
| `filament_loading` | Filament Change | Filament loading | `printing` |
| `filament_unloading` | Filament Change | Filament unloading | `printing` |
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
| `identifying_build_plate_type` | Identifying Build Plate | Identifying build plate type | `printing` |
| `print_calibration_lines` | Printing Calibration Lines | Printing calibration lines | `printing` |
| `inspecting_first_layer` | Inspecting First Layer | Inspecting first layer | `printing` |
| `m400_pause` | Paused | M400 pause | `paused` |
| `paused_filament_runout` | Paused - Filament Runout | Paused (filament ran out) | `paused` |
| `paused_nozzle_clog` | Paused - Nozzle Clog | Pause (nozzle clog) | `paused` |
| `paused_first_layer_error` | Paused - First Layer Error | Pause (first layer error) | `paused` |
| `paused_ams_lost` | Paused - AMS Lost | Pause (AMS offline) | `paused` |
| `paused_user` | Paused User | Paused by the user | `paused` |
| `paused_front_cover_falling` | Paused Front Cover Falling | Pause (front cover fall off) | `paused` |
| `paused_skipped_step` | Paused Skipped Step | Pause (step loss) | `paused` |
| `paused_nozzle_temperature_malfunction` | Paused Nozzle Temperature Malfunction | Pause (nozzle temperature malfunction) | `paused` |
| `paused_heat_bed_temperature_malfunction` | Paused Heat Bed Temperature Malfunction | Pause (heatbed temperature malfunction) | `paused` |
| `paused_low_fan_speed_heat_break` | Paused Low Fan Speed Heat Break | Pause (low speed of the heatbreak fan) | `paused` |
| `paused_chamber_temperature_control_error` | Paused Chamber Temperature Control Error | Pause (chamber temperature control problem) | `paused` |
| `paused_user_gcode` | Paused User Gcode | Pause (Gcode inserted by user) | `paused` |
| `paused_nozzle_filament_covered_detected` | Paused Nozzle Filament Covered Detected | Pause (nozzle clumping) | `paused` |
| `paused_cutter_error` | Paused Cutter Error | Pause (cutter error) | `paused` |
| `idle` | Idle | — | `idle` |
| `offline` | Offline | — | `offline` |

> **Paused stages without a named branch** (e.g. `paused_user`, `paused_skipped_step`): the sensor uses `stage_label` (title-cased stage name) via the `stage.startswith('paused_')` wildcard, so they render as "Paused User", "Paused Skipped Step", etc.

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

## Consistency with Bambuddy

The sensor is functionally equivalent to Bambuddy's display logic. Key mapping:

| Concept | Bambuddy (frontend) | This sensor |
|---|---|---|
| Data source | `stg_cur` (numeric MQTT value) | `current_stage` string (ha-bambulab converts numeric → string) |
| Priority rule | `stg_cur_name` first, then `state` fallback | Stage branches first, then `print_status` fallback |
| Specific pauses | Named labels (filament runout, nozzle clog, etc.) | Same named labels; remaining pauses via `startswith('paused_')` wildcard |
| `prepare`/`slicing`/`init` | Title-cased raw value | "Preparing Print" (friendlier) |
| Unknown combinations | Not applicable (numeric lookup always resolves) | `Unmapped Printer State` + `detail` shows raw values |

### Stages in Bambuddy not yet in ha-bambulab

Bambuddy's `STAGE_NAMES` includes stages 52–66, 74, and 77 (H2D, H2C, and newer hardware stages) that ha-bambulab's `CURRENT_STAGE_IDS` does not yet map to string values. If ha-bambulab adds them in a future release, they will appear as new `current_stage` string values not in this sensor's `known_stages` list, triggering `Unmapped Printer State`.

---

## Handling unknown values (future-proofing)

The sensor is designed to degrade gracefully when the ha-bambulab integration or Bambu Lab firmware introduces new values:

1. **`known_statuses` / `known_stages` lists** in the `detail` attribute enumerate every value this sensor was built against. Any `(status, stage)` combination containing a value outside those lists immediately surfaces as `Unmapped: status="...", stage="..."` in `detail`.

2. **Main `state`** falls through to `Unmapped Printer State` for any combination not matched by an explicit branch.

3. **Automation alert**: [homeassistant/packages/3d_printing/core/dashboard_cards/smart-status-unmapped-alert.yaml](../../../../homeassistant/packages/3d_printing/common/dashboard_cards/smart-status-unmapped-alert.yaml) triggers a persistent notification whenever the sensor enters `Unmapped Printer State`, with a 30-second debounce, system log entry, and auto-dismiss when the state clears.

To add support for a new value, either:
- Add it to the relevant display branch in [homeassistant/packages/3d_printing/core/template_sensors/smart_status.yaml](../../../../homeassistant/packages/3d_printing/core/template_sensors/smart_status.yaml), **and** add it to `known_stages` in the `detail` block.
- Or, if it is a new stage that logically fits an existing group (e.g., a new paused reason), the `paused_*` wildcard will catch it automatically — just add it to `known_stages`.




