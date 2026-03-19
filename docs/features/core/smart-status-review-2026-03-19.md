# Smart Status Sensor — Review & Code Change Recommendations

**Date:** 2026-03-19  
**Scope:** `homeassistant/packages/3d_printing/core/template_sensors/smart_status.yaml`  
**References:** ha-bambulab `const.py` (`CURRENT_STAGE_IDS`), Bambuddy `bambu_mqtt.py` (`STAGE_NAMES`)

---

## Summary of findings

| # | Issue | Severity | Effort |
|---|---|---|---|
| 1 | 7 missing stages (52–58) — triggers "Unmapped Printer State" | **High** | Low |
| 2 | 11 paused stages render with inconsistent formatting | Medium | Low |
| 3 | `detail` attribute uses raw title-cased names instead of friendly labels | Low | Medium |
| 4 | `status_class` does not distinguish calibration/checks from printing | Low | Optional |
| 5 | Documentation was stale (now updated in `smart-status.md`) | Medium | Done |

---

## Change 1 — Add missing stages 52–58

### 1a. `state` template — Heating group

Add `waiting_for_heatbed_temperature` and `thermal_preconditioning` to the heating branch.

**Before:**
```jinja
{% elif stage in ['heatbed_preheating', 'heating_hotend', 'heating_chamber', 'heated_bedcooling', 'cooling_chamber'] %}
  {% if stage == 'heatbed_preheating' %}Heating Bed
  {% elif stage == 'heating_hotend' %}Heating Nozzle
  {% elif stage == 'heating_chamber' %}Heating Chamber
  {% elif stage == 'cooling_chamber' %}Cooling Chamber
  {% else %}Cooling Bed{% endif %}
```

**After:**
```jinja
{% elif stage in ['heatbed_preheating', 'heating_hotend', 'heating_chamber', 'heated_bedcooling', 'cooling_chamber', 'waiting_for_heatbed_temperature', 'thermal_preconditioning'] %}
  {% if stage == 'heatbed_preheating' %}Heating Bed
  {% elif stage == 'heating_hotend' %}Heating Nozzle
  {% elif stage == 'heating_chamber' %}Heating Chamber
  {% elif stage == 'cooling_chamber' %}Cooling Chamber
  {% elif stage == 'waiting_for_heatbed_temperature' %}Waiting for Bed Temp
  {% elif stage == 'thermal_preconditioning' %}Thermal Preconditioning
  {% else %}Cooling Bed{% endif %}
```

### 1b. `state` template — Bed Leveling group

Add `measuring_surface`.

**Before:**
```jinja
{% elif stage in ['auto_bed_leveling', 'bed_level_phase_1', 'bed_level_phase_2', 'bed_level_high_temperature', 'scanning_bed_surface'] %}Bed Leveling
```

**After:**
```jinja
{% elif stage in ['auto_bed_leveling', 'bed_level_phase_1', 'bed_level_phase_2', 'bed_level_high_temperature', 'scanning_bed_surface', 'measuring_surface'] %}Bed Leveling
```

### 1c. `state` template — Homing / Checks group

Add `check_material` and `check_material_position`.

**Before:**
```jinja
{% elif stage in ['homing_toolhead', 'check_door_and_cover', 'check_quick_release', 'check_plaform', 'check_birdeye_camera_position'] %}Homing / Checks
```

**After:**
```jinja
{% elif stage in ['homing_toolhead', 'check_door_and_cover', 'check_quick_release', 'check_plaform', 'check_birdeye_camera_position', 'check_material', 'check_material_position'] %}Homing / Checks
```

### 1d. `state` template — Calibration group

Add `calibrating_live_view_camera` and `calibrating_cutter_model_offset`.

**Before:**
```jinja
{% elif stage in ['calibrating_extrusion', 'calibrating_extrusion_flow', 'calibrating_micro_lidar', 'calibrating_motor_noise', 'absolute_accuracy_calibration', 'check_absolute_accuracy_before_calibration', 'check_absolute_accuracy_after_calibration', 'calibrate_nozzle_offset', 'laser_calibration', 'calibrate_birdeye_camera', 'sweeping_xy_mech_mode', 'motor_noise_showoff'] %}Calibration
```

**After:**
```jinja
{% elif stage in ['calibrating_extrusion', 'calibrating_extrusion_flow', 'calibrating_micro_lidar', 'calibrating_motor_noise', 'absolute_accuracy_calibration', 'check_absolute_accuracy_before_calibration', 'check_absolute_accuracy_after_calibration', 'calibrate_nozzle_offset', 'laser_calibration', 'calibrate_birdeye_camera', 'sweeping_xy_mech_mode', 'motor_noise_showoff', 'calibrating_live_view_camera', 'calibrating_cutter_model_offset'] %}Calibration
```

### 1e. `status_class` template — Heating group

Mirror the heating change.

**Before:**
```jinja
{% elif stage in ['heatbed_preheating', 'heating_hotend', 'heating_chamber', 'heated_bedcooling', 'cooling_chamber'] %}heating
```

**After:**
```jinja
{% elif stage in ['heatbed_preheating', 'heating_hotend', 'heating_chamber', 'heated_bedcooling', 'cooling_chamber', 'waiting_for_heatbed_temperature', 'thermal_preconditioning'] %}heating
```

### 1f. `status_class` template — Leveling group

Mirror the leveling change.

**Before:**
```jinja
{% elif stage in ['auto_bed_leveling', 'bed_level_phase_1', 'bed_level_phase_2', 'bed_level_high_temperature', 'scanning_bed_surface'] %}leveling
```

**After:**
```jinja
{% elif stage in ['auto_bed_leveling', 'bed_level_phase_1', 'bed_level_phase_2', 'bed_level_high_temperature', 'scanning_bed_surface', 'measuring_surface'] %}leveling
```

### 1g. `known_stages` list — add all 7 new stages

Append these to the end of the `known_stages` list (before the closing `]`):

```
'check_material', 'calibrating_live_view_camera', 'waiting_for_heatbed_temperature',
'check_material_position', 'calibrating_cutter_model_offset', 'measuring_surface', 'thermal_preconditioning'
```

---

## Change 2 — Fix paused wildcard formatting

Replace the 4 explicit paused branches + wildcard with explicit branches for ALL known paused stages. Keep the wildcard as a fallback for future unknown paused stages, but add a dash separator.

**Before:**
```jinja
    {% if stage == 'paused_filament_runout' %}Paused - Filament Runout
      {% elif stage == 'paused_nozzle_clog' %}Paused - Nozzle Clog
      {% elif stage == 'paused_first_layer_error' %}Paused - First Layer Error
      {% elif stage == 'paused_ams_lost' %}Paused - AMS Lost
      {% elif stage.startswith('paused_') %}{{ stage_label }}
      {% else %}Paused{% endif %}
```

**After:**
```jinja
    {% if stage == 'paused_filament_runout' %}Paused - Filament Runout
      {% elif stage == 'paused_nozzle_clog' %}Paused - Nozzle Clog
      {% elif stage == 'paused_first_layer_error' %}Paused - First Layer Error
      {% elif stage == 'paused_ams_lost' %}Paused - AMS Lost
      {% elif stage == 'paused_user' %}Paused - User
      {% elif stage == 'paused_front_cover_falling' %}Paused - Front Cover
      {% elif stage == 'paused_skipped_step' %}Paused - Step Loss
      {% elif stage == 'paused_nozzle_temperature_malfunction' %}Paused - Nozzle Temp
      {% elif stage == 'paused_heat_bed_temperature_malfunction' %}Paused - Bed Temp
      {% elif stage == 'paused_low_fan_speed_heat_break' %}Paused - Heatbreak Fan
      {% elif stage == 'paused_chamber_temperature_control_error' %}Paused - Chamber Temp
      {% elif stage == 'paused_user_gcode' %}Paused - G-code
      {% elif stage == 'paused_nozzle_filament_covered_detected' %}Paused - Nozzle Clumping
      {% elif stage == 'paused_cutter_error' %}Paused - Cutter Error
      {% elif stage.startswith('paused_') %}Paused - {{ stage | replace('paused_', '') | replace('_', ' ') | title }}
      {% else %}Paused{% endif %}
```

### Also update the `detail` attribute's paused rendering

**Before (in `detail`):**
```jinja
{% elif status in ['pause', 'paused'] or stage.startswith('paused_') or stage in ['m400_pause', 'paused_filament_runout'] %}
  {{ stage_label if stage.startswith('paused_') else 'Paused' }}
```

**After:**
```jinja
{% elif status in ['pause', 'paused'] or stage.startswith('paused_') or stage in ['m400_pause', 'paused_filament_runout'] %}
  {% if stage == 'paused_filament_runout' %}Paused - Filament Runout
  {% elif stage == 'paused_nozzle_clog' %}Paused - Nozzle Clog
  {% elif stage == 'paused_first_layer_error' %}Paused - First Layer Error
  {% elif stage == 'paused_ams_lost' %}Paused - AMS Lost
  {% elif stage == 'paused_user' %}Paused - User
  {% elif stage == 'paused_front_cover_falling' %}Paused - Front Cover
  {% elif stage == 'paused_skipped_step' %}Paused - Step Loss
  {% elif stage == 'paused_nozzle_temperature_malfunction' %}Paused - Nozzle Temp
  {% elif stage == 'paused_heat_bed_temperature_malfunction' %}Paused - Bed Temp
  {% elif stage == 'paused_low_fan_speed_heat_break' %}Paused - Heatbreak Fan
  {% elif stage == 'paused_chamber_temperature_control_error' %}Paused - Chamber Temp
  {% elif stage == 'paused_user_gcode' %}Paused - G-code
  {% elif stage == 'paused_nozzle_filament_covered_detected' %}Paused - Nozzle Clumping
  {% elif stage == 'paused_cutter_error' %}Paused - Cutter Error
  {% elif stage.startswith('paused_') %}Paused - {{ stage | replace('paused_', '') | replace('_', ' ') | title }}
  {% else %}Paused{% endif %}
```

---

## Change 3 (optional) — Improve `detail` attribute with friendly labels

The `detail` attribute currently uses `stage_label` (raw title-cased stage name) for active print stages. This produces labels like "Check Absolute Accuracy Before Calibration" instead of the more user-friendly "Measuring Motion Precision" (Bambuddy's label).

### Option A: Explicit label mapping (recommended)

Replace the catch-all `{{ stage_label }}` with a lookup dict. This is more verbose but produces consistently friendly labels:

```jinja
{% elif status in ['running', 'printing', 'prepare', 'slicing', 'init'] and stage not in ['printing', 'idle', 'unknown', 'unavailable'] %}
  {% set friendly = {
    'heatbed_preheating': 'Heating Bed',
    'heating_hotend': 'Heating Nozzle',
    'heating_chamber': 'Heating Chamber',
    'heated_bedcooling': 'Cooling Bed',
    'cooling_chamber': 'Cooling Chamber',
    'waiting_for_heatbed_temperature': 'Waiting for Bed Temp',
    'thermal_preconditioning': 'Thermal Preconditioning',
    'auto_bed_leveling': 'Bed Leveling',
    'bed_level_phase_1': 'Bed Leveling Phase 1',
    'bed_level_phase_2': 'Bed Leveling Phase 2',
    'bed_level_high_temperature': 'High Temp Bed Leveling',
    'scanning_bed_surface': 'Scanning Bed Surface',
    'measuring_surface': 'Measuring Surface',
    'homing_toolhead': 'Homing Toolhead',
    'check_door_and_cover': 'Auto Check: Door & Cover',
    'check_quick_release': 'Auto Check: Quick Release',
    'check_plaform': 'Auto Check: Platform',
    'check_birdeye_camera_position': 'Camera Position Check',
    'check_material': 'Auto Check: Material',
    'check_material_position': 'Auto Check: Material Position',
    'cleaning_nozzle_tip': 'Cleaning Nozzle',
    'checking_extruder_temperature': 'Checking Extruder Temp',
    'changing_filament': 'Changing Filament',
    'filament_loading': 'Loading Filament',
    'filament_unloading': 'Unloading Filament',
    'calibrating_extrusion': 'Dynamic Flow Calibration',
    'calibrating_extrusion_flow': 'Flow Ratio Calibration',
    'calibrating_micro_lidar': 'Micro Lidar Calibration',
    'calibrating_motor_noise': 'Motor Noise Cancellation',
    'absolute_accuracy_calibration': 'Motion Precision',
    'check_absolute_accuracy_before_calibration': 'Measuring Motion Precision',
    'check_absolute_accuracy_after_calibration': 'Verifying Motion Precision',
    'calibrate_nozzle_offset': 'Nozzle Offset Calibration',
    'laser_calibration': 'Laser Calibration',
    'calibrate_birdeye_camera': 'Camera Calibration',
    'calibrating_live_view_camera': 'Live View Camera Cal',
    'calibrating_cutter_model_offset': 'Cutting Module Cal',
    'sweeping_xy_mech_mode': 'Vibration Compensation',
    'motor_noise_showoff': 'Motor Noise Showoff',
    'identifying_build_plate_type': 'Identifying Build Plate',
    'print_calibration_lines': 'Calibration Lines',
    'inspecting_first_layer': 'Inspecting First Layer'
  } %}
  {{ friendly.get(stage, stage_label) }}
```

### Option B: Keep title-cased raw labels (no change)

The current approach is simpler and self-maintaining — any new stage automatically gets a reasonable label. The trade-off is some labels are verbose or use internal naming conventions.

**Recommendation:** Option A is preferred if this sensor feeds user-visible notifications or dashboards. Option B is fine if `detail` is only used for debugging/logging.

---

## Change 4 (optional) — Add finer-grained `status_class` values

Currently, `calibration`, `homing`, `nozzle_prep`, and `filament_change` stages all resolve to `status_class = 'printing'`. If downstream consumers need to distinguish these:

```jinja
{% elif stage in ['calibrating_extrusion', ..., 'motor_noise_showoff', 'calibrating_live_view_camera', 'calibrating_cutter_model_offset'] %}calibrating
{% elif stage in ['homing_toolhead', 'check_door_and_cover', ..., 'check_material_position'] %}checking
{% elif stage in ['changing_filament', 'filament_loading', 'filament_unloading'] %}filament_change
```

**Impact assessment:** The WLED orchestrator uses `smart_status` string matching, not `status_class`, so it would be unaffected. Dashboard color logic using `status_class` would need updates. **Not recommended unless a clear consumer need exists.**

---

## Downstream impact of changes

### WLED state machine orchestrator

File: `homeassistant/packages/3d_printing/wled/automations/wled_3dprinter_state_machine_orchestrator.yaml`

The orchestrator's `E_PREP_START` trigger list checks for smart_status values:
```yaml
- "Heating Bed"
- "Heating Nozzle"
- "Bed Leveling"
- "Calibration"
- ...
```

**Impact of Change 1:** The new stages go into existing groups (Heating, Bed Leveling, Homing / Checks, Calibration), so the WLED orchestrator will handle them correctly **with no changes needed** — they produce the same group labels.

However, `Waiting for Bed Temp` and `Thermal Preconditioning` are new state values not currently in the `E_PREP_START` list. These need to be added:
```yaml
- "Waiting for Bed Temp"
- "Thermal Preconditioning"
```

**Impact of Change 2:** Paused state labels change. The WLED orchestrator checks for states starting with "Paused" which will continue to match all pause formats (both "Paused - X" and "Paused"). No changes needed.

### OpenHASP display

File: `homeassistant/packages/3d_printing/openhasp_display/openhasp/officetouch5.yaml`

Uses `smart_status` for display text. Changed labels will render differently but the values are now **more user-friendly**, which is the goal.

### Dashboards

Dashboard views display `smart_status` directly. Changed labels improve readability. No template changes needed.

### Unmapped alert automation

File: `homeassistant/packages/3d_printing/core/automations/smart-status-unmapped-alert.yaml`

After Change 1, the 7 new stages will no longer trigger the alert — they'll map to known groups. This is the desired behavior.

---

## Implementation order

1. **Change 1 (stages 52–58)** — Apply immediately. Prevents false "Unmapped" alerts.
2. **Change 2 (paused formatting)** — Apply next. Fixes user-visible label quality.
3. **Update WLED `E_PREP_START`** — Add `Waiting for Bed Temp` and `Thermal Preconditioning`.
4. **Change 3 (detail labels)** — Optional improvement. Can be deferred.
5. **Change 4 (status_class)** — Only if downstream need is identified.

---

## Complete updated `smart_status.yaml` (Changes 1 + 2 applied)

Below is the full sensor definition with Changes 1 and 2 applied. Change 3 (detail improvement) is left as optional and not included here.

```yaml
# Docs: docs/features/core/smart-status.md
- name: "ntk_ryansoffice_3dprinter_smart_status"
  state: >
    {% set status = states('sensor.ntk_ryansoffice_3dprinter_print_status') | lower %}
    {% set stage = states('sensor.ntk_ryansoffice_3dprinter_current_stage') | lower %}
    {% set stage_label = stage | replace('_', ' ') | title %}
    {% if status == 'offline' or stage == 'offline' %}Offline
    {% elif status == 'failed' %}Print Failed
    {% elif status == 'finish' %}Print Finished
    {% elif status in ['pause', 'paused'] or stage.startswith('paused_') or stage in ['m400_pause', 'paused_filament_runout'] %}
      {% if stage == 'paused_filament_runout' %}Paused - Filament Runout
      {% elif stage == 'paused_nozzle_clog' %}Paused - Nozzle Clog
      {% elif stage == 'paused_first_layer_error' %}Paused - First Layer Error
      {% elif stage == 'paused_ams_lost' %}Paused - AMS Lost
      {% elif stage == 'paused_user' %}Paused - User
      {% elif stage == 'paused_front_cover_falling' %}Paused - Front Cover
      {% elif stage == 'paused_skipped_step' %}Paused - Step Loss
      {% elif stage == 'paused_nozzle_temperature_malfunction' %}Paused - Nozzle Temp
      {% elif stage == 'paused_heat_bed_temperature_malfunction' %}Paused - Bed Temp
      {% elif stage == 'paused_low_fan_speed_heat_break' %}Paused - Heatbreak Fan
      {% elif stage == 'paused_chamber_temperature_control_error' %}Paused - Chamber Temp
      {% elif stage == 'paused_user_gcode' %}Paused - G-code
      {% elif stage == 'paused_nozzle_filament_covered_detected' %}Paused - Nozzle Clumping
      {% elif stage == 'paused_cutter_error' %}Paused - Cutter Error
      {% elif stage.startswith('paused_') %}Paused - {{ stage | replace('paused_', '') | replace('_', ' ') | title }}
      {% else %}Paused{% endif %}
    {% elif stage in ['heatbed_preheating', 'heating_hotend', 'heating_chamber', 'heated_bedcooling', 'cooling_chamber', 'waiting_for_heatbed_temperature', 'thermal_preconditioning'] %}
      {% if stage == 'heatbed_preheating' %}Heating Bed
      {% elif stage == 'heating_hotend' %}Heating Nozzle
      {% elif stage == 'heating_chamber' %}Heating Chamber
      {% elif stage == 'cooling_chamber' %}Cooling Chamber
      {% elif stage == 'waiting_for_heatbed_temperature' %}Waiting for Bed Temp
      {% elif stage == 'thermal_preconditioning' %}Thermal Preconditioning
      {% else %}Cooling Bed{% endif %}
    {% elif stage in ['auto_bed_leveling', 'bed_level_phase_1', 'bed_level_phase_2', 'bed_level_high_temperature', 'scanning_bed_surface', 'measuring_surface'] %}Bed Leveling
    {% elif stage in ['homing_toolhead', 'check_door_and_cover', 'check_quick_release', 'check_plaform', 'check_birdeye_camera_position', 'check_material', 'check_material_position'] %}Homing / Checks
    {% elif stage in ['cleaning_nozzle_tip', 'checking_extruder_temperature'] %}Nozzle Prep
    {% elif stage in ['changing_filament', 'filament_loading', 'filament_unloading'] %}Filament Change
    {% elif stage in ['calibrating_extrusion', 'calibrating_extrusion_flow', 'calibrating_micro_lidar', 'calibrating_motor_noise', 'absolute_accuracy_calibration', 'check_absolute_accuracy_before_calibration', 'check_absolute_accuracy_after_calibration', 'calibrate_nozzle_offset', 'laser_calibration', 'calibrate_birdeye_camera', 'sweeping_xy_mech_mode', 'motor_noise_showoff', 'calibrating_live_view_camera', 'calibrating_cutter_model_offset'] %}Calibration
    {% elif stage == 'identifying_build_plate_type' %}Identifying Build Plate
    {% elif stage == 'print_calibration_lines' %}Printing Calibration Lines
    {% elif stage == 'inspecting_first_layer' %}Inspecting First Layer
    {% elif status in ['running', 'printing'] or stage == 'printing' %}Printing
    {% elif status in ['prepare', 'slicing', 'init'] %}Preparing Print
    {% elif status == 'idle' and stage == 'idle' %}Idle
    {% elif status in ['unknown', 'unavailable', 'none', ''] or stage in ['unknown', 'unavailable', 'none', ''] %}Unknown Printer State
    {% else %}Unmapped Printer State{% endif %}
  attributes:
    detail: >
      {% set status_raw = states('sensor.ntk_ryansoffice_3dprinter_print_status') %}
      {% set stage_raw = states('sensor.ntk_ryansoffice_3dprinter_current_stage') %}
      {% set status = status_raw | lower %}
      {% set stage = stage_raw | lower %}
      {% set stage_label = stage | replace('_', ' ') | title %}
      {% set known_statuses = ['failed', 'finish', 'idle', 'init', 'offline', 'pause', 'paused', 'prepare', 'running', 'printing', 'slicing', 'unknown', 'unavailable', 'none', ''] %}
      {% set known_stages = [
        'offline', 'idle', 'unknown', 'unavailable', 'none', '',
        'printing', 'auto_bed_leveling', 'heatbed_preheating', 'sweeping_xy_mech_mode', 'changing_filament', 'm400_pause', 'paused_filament_runout',
        'heating_hotend', 'calibrating_extrusion', 'scanning_bed_surface', 'inspecting_first_layer', 'identifying_build_plate_type', 'calibrating_micro_lidar',
        'homing_toolhead', 'cleaning_nozzle_tip', 'checking_extruder_temperature', 'paused_user', 'paused_front_cover_falling', 'calibrating_extrusion_flow',
        'paused_nozzle_temperature_malfunction', 'paused_heat_bed_temperature_malfunction', 'filament_unloading', 'paused_skipped_step', 'filament_loading',
        'calibrating_motor_noise', 'paused_ams_lost', 'paused_low_fan_speed_heat_break', 'paused_chamber_temperature_control_error', 'cooling_chamber',
        'paused_user_gcode', 'motor_noise_showoff', 'paused_nozzle_filament_covered_detected', 'paused_cutter_error', 'paused_first_layer_error',
        'paused_nozzle_clog', 'check_absolute_accuracy_before_calibration', 'absolute_accuracy_calibration', 'check_absolute_accuracy_after_calibration',
        'calibrate_nozzle_offset', 'bed_level_high_temperature', 'check_quick_release', 'check_door_and_cover', 'laser_calibration', 'check_plaform',
        'check_birdeye_camera_position', 'calibrate_birdeye_camera', 'bed_level_phase_1', 'bed_level_phase_2', 'heating_chamber', 'heated_bedcooling',
        'print_calibration_lines',
        'check_material', 'calibrating_live_view_camera', 'waiting_for_heatbed_temperature',
        'check_material_position', 'calibrating_cutter_model_offset', 'measuring_surface', 'thermal_preconditioning'
      ] %}
      {% if status not in known_statuses or stage not in known_stages %}
        Unmapped: status="{{ status_raw }}", stage="{{ stage_raw }}"
      {% elif status in ['finish'] or (status == 'idle' and stage == 'idle') or status == 'offline' or stage == 'offline' or status in ['unknown', 'unavailable', 'none', ''] or stage in ['unknown', 'unavailable', 'none', ''] %}
        {{ '' }}
      {% elif status in ['pause', 'paused'] or stage.startswith('paused_') or stage in ['m400_pause', 'paused_filament_runout'] %}
        {% if stage == 'paused_filament_runout' %}Paused - Filament Runout
        {% elif stage == 'paused_nozzle_clog' %}Paused - Nozzle Clog
        {% elif stage == 'paused_first_layer_error' %}Paused - First Layer Error
        {% elif stage == 'paused_ams_lost' %}Paused - AMS Lost
        {% elif stage == 'paused_user' %}Paused - User
        {% elif stage == 'paused_front_cover_falling' %}Paused - Front Cover
        {% elif stage == 'paused_skipped_step' %}Paused - Step Loss
        {% elif stage == 'paused_nozzle_temperature_malfunction' %}Paused - Nozzle Temp
        {% elif stage == 'paused_heat_bed_temperature_malfunction' %}Paused - Bed Temp
        {% elif stage == 'paused_low_fan_speed_heat_break' %}Paused - Heatbreak Fan
        {% elif stage == 'paused_chamber_temperature_control_error' %}Paused - Chamber Temp
        {% elif stage == 'paused_user_gcode' %}Paused - G-code
        {% elif stage == 'paused_nozzle_filament_covered_detected' %}Paused - Nozzle Clumping
        {% elif stage == 'paused_cutter_error' %}Paused - Cutter Error
        {% elif stage.startswith('paused_') %}Paused - {{ stage | replace('paused_', '') | replace('_', ' ') | title }}
        {% else %}Paused{% endif %}
      {% elif status in ['running', 'printing', 'prepare', 'slicing', 'init'] and stage not in ['printing', 'idle', 'unknown', 'unavailable'] %}
        {{ stage_label }}
      {% else %}
        {{ status_raw | replace('_', ' ') | title }}
      {% endif %}
    status_raw: "{{ states('sensor.ntk_ryansoffice_3dprinter_print_status') }}"
    stage_raw: "{{ states('sensor.ntk_ryansoffice_3dprinter_current_stage') }}"
    status_class: >
      {% set status = states('sensor.ntk_ryansoffice_3dprinter_print_status') | lower %}
      {% set stage = states('sensor.ntk_ryansoffice_3dprinter_current_stage') | lower %}
      {% if status == 'offline' or stage == 'offline' %}offline
      {% elif status == 'failed' %}failed
      {% elif status == 'finish' %}finished
      {% elif status in ['pause', 'paused'] or stage.startswith('paused_') or stage in ['m400_pause', 'paused_filament_runout'] %}paused
      {% elif stage in ['heatbed_preheating', 'heating_hotend', 'heating_chamber', 'heated_bedcooling', 'cooling_chamber', 'waiting_for_heatbed_temperature', 'thermal_preconditioning'] %}heating
      {% elif stage in ['auto_bed_leveling', 'bed_level_phase_1', 'bed_level_phase_2', 'bed_level_high_temperature', 'scanning_bed_surface', 'measuring_surface'] %}leveling
      {% elif status in ['running', 'printing'] or stage == 'printing' %}printing
      {% elif status in ['prepare', 'slicing', 'init'] %}preparing
      {% elif status == 'idle' and stage == 'idle' %}idle
      {% elif status in ['unknown', 'unavailable', 'none', ''] or stage in ['unknown', 'unavailable', 'none', ''] %}unknown
      {% else %}unmapped{% endif %}
    is_active: >
      {% set status = states('sensor.ntk_ryansoffice_3dprinter_print_status') | lower %}
      {% set stage = states('sensor.ntk_ryansoffice_3dprinter_current_stage') | lower %}
      {{ status in ['running', 'printing', 'prepare', 'slicing', 'init'] or stage == 'printing' }}
```
