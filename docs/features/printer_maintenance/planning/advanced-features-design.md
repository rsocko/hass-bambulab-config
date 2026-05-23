# Printer Maintenance — Advanced Features Design

> Based on full Bambuddy maintenance API: [`maintenance.py`](https://github.com/maziggy/bambuddy/blob/main/backend/app/api/routes/maintenance.py)
> Cross-references printer status API (`runtime_seconds`, `nozzles`, AMS humidity), archive stats API, and printer control API (calibration).
> Builds on the core maintenance package defined in [README.md](\docs\features\printer_maintenance\README.md).
>
> **OpenAPI cross-check**: Re-validated against the live spec at `http://bambuddy.socko.us/openapi.json` on 2026-03-29.

---

## Bambuddy Maintenance API — Endpoint Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/maintenance/types` | All maintenance types (system + custom) |
| `POST` | `/maintenance/types` | Create custom maintenance type |
| `PATCH` | `/maintenance/types/{type_id}` | Update maintenance type |
| `DELETE` | `/maintenance/types/{type_id}` | Soft-delete system type or hard-delete custom |
| `POST` | `/maintenance/types/restore-defaults` | Restore soft-deleted system types |
| `GET` | `/maintenance/printers/{printer_id}` | Full maintenance overview for one printer |
| `GET` | `/maintenance/overview` | Maintenance overview for ALL active printers |
| `PATCH` | `/maintenance/items/{item_id}` | Update item (custom interval, enabled) |
| `POST` | `/maintenance/items/{item_id}/perform` | Mark task performed (reset counter) |
| `GET` | `/maintenance/items/{item_id}/history` | History log for specific item |
| `GET` | `/maintenance/summary` | Cross-printer summary (total due/warning counts) |
| `PATCH` | `/maintenance/printers/{printer_id}/hours` | Set/adjust total print hours |
| `POST` | `/maintenance/printers/{printer_id}/assign/{type_id}` | Assign custom type to printer |
| `DELETE` | `/maintenance/items/{item_id}` | Unassign custom type from printer |

### Key Data Model

Bambuddy tracks maintenance via **three tables**:

1. **`MaintenanceType`** — definition (name, description, default_interval_hours, interval_type [hours/days], icon, is_system)
2. **`PrinterMaintenance`** — per-printer item linking type → printer with custom overrides (custom_interval_hours, custom_interval_type, enabled, last_performed_hours, last_performed_at)
3. **`MaintenanceHistory`** — log of completions (hours_at_maintenance, notes, performed_at)

### Default System Types (model-aware)

| Task | Interval | Applies To |
|------|----------|------------|
| Clean Carbon Rods | 100 hrs | X1/P1 series |
| Lubricate Steel Rods | 50 hrs | P2S |
| Clean Steel Rods | 100 hrs | P2S |
| Lubricate Linear Rails | 50 hrs | A1/H2 series |
| Clean Linear Rails | 100 hrs | A1/H2 series |
| Clean Nozzle/Hotend | 100 hrs | All |
| Check Belt Tension | 200 hrs | All |
| Clean Build Plate | 25 hrs | All |
| Check PTFE Tube | 500 hrs | All |

---

## Phase 5.1: Multi-Printer Maintenance Summary Dashboard

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/maintenance/overview` | All printers' maintenance overviews in one call |
| `GET` | `/maintenance/summary` | Aggregated due/warning counts + printers with issues |

### Feature Scope

**Fleet-wide maintenance view** — For multi-printer setups, surface a single dashboard card that shows maintenance status across ALL printers. The core package (README) only tracks one printer at a time. This phase adds fleet awareness.

**Use cases:**
1. **Fleet health chip** — Single badge showing total due tasks across all printers
2. **Worst-printer-first sort** — Dashboard card listing printers ordered by most overdue tasks
3. **Weekly maintenance planner** — Template sensor that groups upcoming tasks by urgency

### Implementation

**REST sensor: `sensor.bambuddy_maintenance_fleet_summary`**

```yaml
- platform: rest
  name: "Bambuddy Maintenance Fleet Summary"
  unique_id: bambuddy_maintenance_fleet_summary
  resource: !secret bambuddy_maintenance_summary_url
  # e.g. http://bambuddy.local:5000/api/v1/maintenance/summary
  headers:
    X-API-Key: !secret bambuddy_api_key
  scan_interval: 600
  value_template: >-
    {% if value_json.total_due > 0 %}due
    {% elif value_json.total_warning > 0 %}warning
    {% else %}ok{% endif %}
  json_attributes:
    - total_due
    - total_warning
    - printers_with_issues
```

**REST sensor: `sensor.bambuddy_maintenance_fleet_overview`**

```yaml
- platform: rest
  name: "Bambuddy Maintenance Fleet Overview"
  unique_id: bambuddy_maintenance_fleet_overview
  resource: !secret bambuddy_maintenance_overview_url
  # e.g. http://bambuddy.local:5000/api/v1/maintenance/overview
  headers:
    X-API-Key: !secret bambuddy_api_key
  scan_interval: 600
  value_template: "{{ value_json | length }}"
  json_attributes_path: "$"
  json_attributes:
    - printer_id
    - printer_name
    - printer_model
    - total_print_hours
    - maintenance_items
    - due_count
    - warning_count
```

> **Note**: The `/overview` response is a JSON array (one object per printer). HA's `rest` sensor attribute handling for arrays may require a template sensor wrapper to iterate. Alternatively, poll `/summary` for counts and `/printers/{id}` per-printer for details.

**Template sensor: `sensor.maintenance_fleet_due_total`**

```yaml
- sensor:
    - name: "Maintenance Fleet Due Total"
      unique_id: maintenance_fleet_due_total
      state: >-
        {{ state_attr('sensor.bambuddy_maintenance_fleet_summary', 'total_due') | default(0, true) }}
      unit_of_measurement: "tasks"
      icon: mdi:wrench-clock
      attributes:
        warning_count: >-
          {{ state_attr('sensor.bambuddy_maintenance_fleet_summary', 'total_warning') | default(0, true) }}
        printers_needing_attention: >-
          {% set issues = state_attr('sensor.bambuddy_maintenance_fleet_summary', 'printers_with_issues') | default([], true) %}
          {{ issues | map(attribute='printer_name') | list }}
```

**Dashboard card** — Markdown card listing each printer's maintenance health:

```yaml
type: markdown
title: Fleet Maintenance Status
content: >-
  {% set issues = state_attr('sensor.bambuddy_maintenance_fleet_summary', 'printers_with_issues') | default([], true) %}
  {% if issues | length == 0 %}
  ✅ All printers healthy — no maintenance due
  {% else %}
  | Printer | Due | Warning |
  |---|---|---|
  {% for p in issues %}
  | {{ p.printer_name }} | {{ p.due_count }} | {{ p.warning_count }} |
  {% endfor %}
  {% endif %}
```

---

## Phase 5.2: Maintenance History Log & Trend Analysis

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/maintenance/items/{item_id}/history` | All completions for one maintenance item |
| `GET` | `/maintenance/printers/{printer_id}` | Full overview (includes `maintenance_items` with item IDs) |

### Feature Scope

**Maintenance journal** — Track when each task was last (and historically) completed. Useful for warranty documentation, identifying neglected tasks, and seeing maintenance cadence over time.

**Use cases:**
1. **History timeline card** — Show last N completions per task with notes
2. **Maintenance cadence tracking** — Is the user doing maintenance on schedule or always late?
3. **Export proof** — Persistent log of all maintenance actions performed (for warranty/support)

### Implementation

**REST sensor: `sensor.bambuddy_maintenance_history_{printer_id}_{item_id}`**

For the most critical items (e.g., nozzle, rods/rails), poll history for trend display:

```yaml
- platform: rest
  name: "Bambuddy Maintenance History - Printer 1 - Nozzle"
  unique_id: bambuddy_maintenance_history_p1_nozzle
  resource: !secret bambuddy_maintenance_history_nozzle_url
  # e.g. http://bambuddy.local:5000/api/v1/maintenance/items/{item_id}/history
  headers:
    X-API-Key: !secret bambuddy_api_key
  scan_interval: 3600  # hourly — history doesn't change often
  value_template: "{{ value_json | length }}"
  json_attributes_path: "$[0]"
  json_attributes:
    - performed_at
    - hours_at_maintenance
    - notes
```

**Template sensor: `sensor.maintenance_avg_interval_{task_name}`**

```yaml
- sensor:
    - name: "Maintenance Avg Interval - Nozzle Clean"
      unique_id: maintenance_avg_interval_nozzle_clean
      state: >-
        {# Calculate average hours between completions #}
        {% set history = state_attr('sensor.bambuddy_maintenance_history_p1_nozzle', 'history') | default([], true) %}
        {% if history | length < 2 %}unknown
        {% else %}
          {% set hours = history | map(attribute='hours_at_maintenance') | list | sort %}
          {% set intervals = [] %}
          {% for i in range(1, hours | length) %}
            {% set intervals = intervals + [hours[i] - hours[i-1]] %}
          {% endfor %}
          {{ (intervals | sum / intervals | length) | round(1) }}
        {% endif %}
      unit_of_measurement: "hrs"
      icon: mdi:chart-timeline-variant
```

> **Scaling note**: History sensors should only be created for the most important maintenance items. Don't poll history for every task — use the main overview endpoint for status, and history for drilldown only.

---

## Phase 5.3: Custom Maintenance Types from HA

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/maintenance/types` | Create new maintenance type (name, description, interval, interval_type, icon) |
| `POST` | `/maintenance/printers/{printer_id}/assign/{type_id}` | Assign type to printer |
| `DELETE` | `/maintenance/items/{item_id}` | Unassign custom type from printer |

### Feature Scope

**User-defined maintenance tasks** — Let users create custom maintenance tasks from HA (e.g., "Replace Desiccant", "Clean Enclosure Fan Filter", "Inspect Wiring Harness") and assign them to specific printers. Bambuddy already supports custom types via the web UI; this enables the same from HA.

**Use cases:**
1. **Accessory maintenance** — Track tasks for non-Bambu accessories (Bento Box filter, HEPA filter, external fan)
2. **Calendar-based tasks** — Some tasks are time-based not print-hours-based (e.g., "replace desiccant every 30 days")
3. **Per-printer custom tasks** — Assign tasks only to the printer that has the accessory

### Implementation

**REST commands: create + assign**

```yaml
bambuddy_create_maintenance_type:
  url: !secret bambuddy_maintenance_types_url
  method: POST
  headers:
    X-API-Key: !secret bambuddy_api_key
  content_type: application/json
  payload: >-
    {
      "name": "{{ name }}",
      "description": "{{ description | default('', true) }}",
      "default_interval_hours": {{ interval | default(100, true) }},
      "interval_type": "{{ interval_type | default('hours', true) }}",
      "icon": "{{ icon | default('Wrench', true) }}"
    }

bambuddy_assign_maintenance_type:
  url: "{{ bambuddy_base_url }}/api/v1/maintenance/printers/{{ printer_id }}/assign/{{ type_id }}"
  method: POST
  headers:
    X-API-Key: !secret bambuddy_api_key
```

**Script: `script.create_and_assign_maintenance_task`**

```yaml
create_and_assign_maintenance_task:
  alias: Create & Assign Maintenance Task
  description: Creates a custom maintenance type in Bambuddy and assigns it to a printer
  fields:
    name:
      description: Task name
      required: true
      example: "Replace Desiccant"
    description:
      description: Task description
      example: "Replace silica gel packets in AMS desiccant box"
    interval:
      description: Interval value
      default: 30
    interval_type:
      description: hours or days
      default: days
    printer_id:
      description: Target Bambuddy printer ID
      required: true
  sequence:
    - service: rest_command.bambuddy_create_maintenance_type
      data:
        name: "{{ name }}"
        description: "{{ description | default('', true) }}"
        interval: "{{ interval }}"
        interval_type: "{{ interval_type }}"
    # Note: assign step requires the type_id from the response.
    # HA rest_command doesn't return response bodies, so a follow-up
    # automation or manual step in Bambuddy UI may be needed for assignment.
    # Alternative: use shell_command with curl to capture the response.
```

> **Limitation**: HA's `rest_command` service does not return response bodies, making the two-step create→assign flow difficult to automate fully. For custom types, the recommended flow is: create the type in Bambuddy (UI or REST), then assign via HA REST command or Bambuddy UI. The `/overview` sensor will pick it up automatically once assigned.

---

## Phase 5.4: Print-Hours Calibration & Runtime Tracking

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `PATCH` | `/maintenance/printers/{printer_id}/hours` | Set total print hours (calculates offset from runtime_seconds) |
| `GET` | `/printers/{printer_id}/runtime-debug` | Debug: runtime_seconds, offset, total hours, MQTT state |

### Feature Scope

**Accurate hours for maintenance** — Bambuddy tracks `runtime_seconds` from MQTT (RUNNING + PAUSE states) plus a user-adjustable `print_hours_offset` for printers that had print time before Bambuddy was installed. This phase surfaces that data and lets users calibrate it from HA.

**Use cases:**
1. **Print hours counter** — Dashboard sensor showing total printer hours (runtime + offset)
2. **Hours calibration** — Script to set total hours from HA (e.g., when first setting up Bambuddy on a used printer)
3. **Runtime anomaly detection** — Alert if runtime_seconds grows unexpectedly (printer left in PAUSE for days)

### Implementation

**Template sensor: `sensor.printer_{name}_total_hours`**

The maintenance overview already returns `total_print_hours`. Expose it directly:

```yaml
- sensor:
    - name: "Printer 1 Total Hours"
      unique_id: printer_1_total_hours
      state: >-
        {{ state_attr('sensor.bambuddy_maintenance_status', 'total_print_hours') | default(0, true) | round(1) }}
      unit_of_measurement: "hrs"
      icon: mdi:timer-outline
      device_class: duration
```

**REST command: `rest_command.bambuddy_set_printer_hours`**

```yaml
bambuddy_set_printer_hours:
  url: "{{ bambuddy_base_url }}/api/v1/maintenance/printers/{{ printer_id }}/hours?total_hours={{ total_hours }}"
  method: PATCH
  headers:
    X-API-Key: !secret bambuddy_api_key
```

**Script: `script.calibrate_printer_hours`**

```yaml
calibrate_printer_hours:
  alias: Calibrate Printer Hours
  description: Set total print hours for a printer in Bambuddy
  fields:
    printer_id:
      description: Bambuddy printer ID
      required: true
    total_hours:
      description: Total lifetime hours to set
      required: true
      example: 500
  sequence:
    - service: rest_command.bambuddy_set_printer_hours
      data:
        printer_id: "{{ printer_id }}"
        total_hours: "{{ total_hours }}"
    - delay: "00:00:05"
    - service: homeassistant.update_entity
      target:
        entity_id: sensor.bambuddy_maintenance_status
```

**Automation: Runtime anomaly alert**

```yaml
alias: "Maintenance: Runtime Anomaly Alert"
trigger:
  - platform: numeric_state
    entity_id: sensor.printer_1_total_hours
    above: 100  # dynamic — would need to store "last known" and compare delta
condition:
  # Alert if hours increased by more than 24 in one day (printer stuck in PAUSE?)
  - condition: template
    value_template: >-
      {% set new = states('sensor.printer_1_total_hours') | float(0) %}
      {% set old = state_attr('sensor.printer_1_total_hours', 'previous_value') | float(0) %}
      {{ (new - old) > 24 }}
action:
  - service: persistent_notification.create
    data:
      title: "Runtime Anomaly: Printer 1"
      message: >-
        Printer 1 logged {{ states('sensor.printer_1_total_hours') }} hours total.
        Check if the printer was left paused or running unexpectedly.
```

> **Note**: The runtime anomaly is a nice-to-have. A simpler approach: just check if `runtime_seconds` delta per day exceeds 20 hours (suggesting the printer never stopped).

---

## Phase 5.5: Maintenance-Driven Calibration Reminders

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/maintenance/printers/{printer_id}` | Maintenance overview (check belt/vibration/motor items) |
| `POST` | `/printers/{printer_id}/calibration` | Trigger calibration (bed_leveling, vibration, motor_noise, nozzle_offset, high_temp_heatbed) |

### Feature Scope

**Auto-suggest calibration after maintenance** — When the user marks "Check Belt Tension" as complete in HA, automatically suggest or trigger a vibration compensation calibration. When "Clean Build Plate" is done, suggest bed leveling. Connect maintenance events to calibration actions.

**Use cases:**
1. **Post-maintenance calibration prompt** — Persistent notification: "You just completed belt tension check. Run vibration calibration?"
2. **One-tap calibration** — Actionable notification with a button to start calibration directly
3. **Maintenance → calibration pairing** — Documented best practices (belt → vibration comp, nozzle change → flow calibration)

### Maintenance → Calibration Mapping

| Maintenance Task | Suggested Calibration | API Parameters |
|---|---|---|
| Check Belt Tension | Vibration Compensation | `vibration=true` |
| Clean Build Plate | Bed Leveling | `bed_leveling=true` |
| Clean Nozzle/Hotend | (manual flow calibration) | N/A — requires printer-side UI |
| Lubricate Steel Rods / Linear Rails | Vibration + Motor Noise | `vibration=true, motor_noise=true` |
| (Nozzle replacement — custom type) | Nozzle Offset (dual-nozzle) | `nozzle_offset=true` |

### Implementation

**REST command: `rest_command.bambuddy_start_calibration`**

```yaml
bambuddy_start_calibration:
  url: >-
    {{ bambuddy_base_url }}/api/v1/printers/{{ printer_id }}/calibration?bed_leveling={{ bed_leveling | default(false) }}&vibration={{ vibration | default(false) }}&motor_noise={{ motor_noise | default(false) }}&nozzle_offset={{ nozzle_offset | default(false) }}&high_temp_heatbed={{ high_temp_heatbed | default(false) }}
  method: POST
  headers:
    X-API-Key: !secret bambuddy_api_key
```

**Automation: Post-maintenance calibration suggestion**

```yaml
alias: "Maintenance: Post-Task Calibration Suggestion"
description: >-
  When a maintenance task is completed via HA, suggest the appropriate
  calibration. Fires when the maintenance sensor refreshes and a task
  that was previously due/warning is now not-due.
trigger:
  - platform: state
    entity_id: sensor.bambuddy_maintenance_status
condition:
  # Only fire if a task was just marked complete
  # (detected by due_count decreasing)
  - condition: template
    value_template: >-
      {% set old_due = trigger.from_state.attributes.due_count | default(0, true) | int %}
      {% set new_due = trigger.to_state.attributes.due_count | default(0, true) | int %}
      {{ new_due < old_due }}
action:
  # Determine which task was just completed by comparing old vs new task lists
  - variables:
      old_due_items: >-
        {% set items = trigger.from_state.attributes.maintenance_items | default([], true) %}
        {{ items | selectattr('is_due', 'eq', true) | map(attribute='maintenance_type_name') | list }}
      new_due_items: >-
        {% set items = trigger.to_state.attributes.maintenance_items | default([], true) %}
        {{ items | selectattr('is_due', 'eq', true) | map(attribute='maintenance_type_name') | list }}
      completed_task: >-
        {{ old_due_items | reject('in', new_due_items) | first | default('unknown') }}
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ 'Belt' in completed_task }}"
        sequence:
          - service: persistent_notification.create
            data:
              title: "Calibration Suggested"
              message: >-
                Belt tension was just checked. Consider running vibration
                compensation calibration for optimal print quality.
              notification_id: maintenance_calibration_suggestion
      - conditions:
          - condition: template
            value_template: "{{ 'Build Plate' in completed_task }}"
        sequence:
          - service: persistent_notification.create
            data:
              title: "Calibration Suggested"
              message: >-
                Build plate was just cleaned. Consider running bed leveling
                calibration for optimal first layer adhesion.
              notification_id: maintenance_calibration_suggestion
      - conditions:
          - condition: template
            value_template: "{{ 'Lubricate' in completed_task }}"
        sequence:
          - service: persistent_notification.create
            data:
              title: "Calibration Suggested"
              message: >-
                Rod/rail lubrication complete. Consider running vibration
                compensation + motor noise calibration.
              notification_id: maintenance_calibration_suggestion
```

**Script: One-tap calibration from notification**

```yaml
run_post_maintenance_calibration:
  alias: Run Post-Maintenance Calibration
  fields:
    printer_id:
      required: true
    calibration_type:
      description: "belt, plate, or lube"
      required: true
  sequence:
    - choose:
        - conditions: "{{ calibration_type == 'belt' }}"
          sequence:
            - service: rest_command.bambuddy_start_calibration
              data:
                printer_id: "{{ printer_id }}"
                vibration: true
        - conditions: "{{ calibration_type == 'plate' }}"
          sequence:
            - service: rest_command.bambuddy_start_calibration
              data:
                printer_id: "{{ printer_id }}"
                bed_leveling: true
        - conditions: "{{ calibration_type == 'lube' }}"
          sequence:
            - service: rest_command.bambuddy_start_calibration
              data:
                printer_id: "{{ printer_id }}"
                vibration: true
                motor_noise: true
```

---

## Phase 5.5a: Maintenance Policy Tuning & Defaults Recovery

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `PATCH` | `/maintenance/items/{item_id}` | Change interval, interval type, enabled state |
| `DELETE` | `/maintenance/items/{item_id}` | Remove a maintenance item from a printer |
| `PATCH` | `/maintenance/types/{type_id}` | Update a custom type |
| `DELETE` | `/maintenance/types/{type_id}` | Delete or soft-delete a type |
| `POST` | `/maintenance/types/restore-defaults` | Restore the built-in default task set |

### Feature Scope

**Maintenance admin from HA** — Allow careful tuning of maintenance policy from HA without having to open Bambuddy for every interval or enable/disable adjustment.

**Use cases:**
1. **Per-printer interval override** — Lengthen or shorten a task interval for a specific printer or nozzle setup.
2. **Temporary disable** — Disable a task during a hardware experiment, then re-enable it later.
3. **Defaults recovery** — Restore the stock Bambuddy maintenance types after aggressive customizations.

### Implementation

**Scripts**:
- `bambuddy_update_maintenance_item`
- `bambuddy_remove_maintenance_item`
- `bambuddy_restore_default_maintenance_types`

**Dashboard integration**:
- Add an admin-only maintenance policy card with guarded buttons and confirmation dialogs.

### Phase & Dependencies

- **Phase**: 5.5a (after core maintenance status + mark-complete flow)
- **Depends on**: printer_maintenance core, confirmation UX for writes
- **Package**: printer_maintenance
- **Effort**: Medium
- **Value**: Medium — admin heavy, but valuable for evolving printer fleets

---

## Phase 5.5b: Wiki-Guided Exception Views

### Data Sources

From `MaintenanceStatus` / `PrinterMaintenanceOverview`:
- `maintenance_type_wiki_url`
- `due_count`, `warning_count`, overdue timing fields, and task descriptions

### Feature Scope

**Actionable maintenance alerts** — Make overdue tasks more self-explanatory by linking straight to remediation guidance.

**Use cases:**
1. **Help link in overdue card** — `Clean Nozzle/Hotend due` with a direct wiki link.
2. **Exception view for repeated overdue tasks** — Highlight tasks that have remained overdue across multiple refresh cycles.
3. **Maintenance popup drilldown** — Open a detail card with interval, last performed date, notes, and wiki link.

### Implementation

**Template sensor**:
- `sensor.bambuddy_overdue_maintenance_exceptions`
  - state: count of overdue tasks past a configured grace period
  - attributes: task name, printer, wiki URL, hours overdue

**Dashboard integration**:
- Add clickable wiki/help buttons to the maintenance catalog card and alert section.

### Phase & Dependencies

- **Phase**: 5.5b
- **Depends on**: printer_maintenance core
- **Package**: printer_maintenance
- **Effort**: Low
- **Value**: Medium-High — improves follow-through on maintenance alerts

---

## Phase 5.6: Nozzle Wear Intelligence

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/printers/{printer_id}/status` | Live nozzle info: `nozzles[].nozzle_type`, `nozzles[].nozzle_diameter`; H2D: `nozzle_rack[].wear`, `nozzle_rack[].stat` |
| `GET` | `/archives/stats` | Total print time, prints by filament type (abrasive filaments degrade nozzles faster) |
| `GET` | `/maintenance/printers/{printer_id}` | Current "Clean Nozzle/Hotend" task status |

### Feature Scope

**Nozzle lifecycle tracking** — Standard brass nozzles wear faster with abrasive filaments (CF, GF). Steel/hardened nozzles last longer but still need monitoring. This phase tracks nozzle usage patterns to predict replacement timing.

**Key data points:**
- `nozzle_type` from printer status (e.g., "stainless_steel", "hardened_steel")
- `nozzle_diameter` (0.4, 0.6, etc.)
- H2D tool-changer `nozzle_rack[].wear` — firmware-reported wear level
- Archive stats `prints_by_filament_type` — proportion of abrasive prints
- Print hours since last nozzle maintenance completion

**Use cases:**
1. **Nozzle wear score** — Weighted calculation: brass + CF prints = wear fast, hardened steel + PLA = wear slow
2. **H2D wear relay** — Surface the firmware's `nozzle_rack[].wear` value directly in HA (unique to tool-changer printers)
3. **Abrasive print counter** — Track what percentage of prints use CF/GF filaments and escalate nozzle-clean interval

### Implementation

**Template sensor: `sensor.printer_{name}_nozzle_wear_estimate`**

```yaml
- sensor:
    - name: "Printer 1 Nozzle Wear Estimate"
      unique_id: printer_1_nozzle_wear_estimate
      state: >-
        {# Weighted wear score: 0 = new, 100 = replace #}
        {% set nozzle_type = state_attr('sensor.bambuddy_printer_1_status', 'nozzles')
            | default([{}], true) | first | default({}, true) %}
        {% set type_name = nozzle_type.get('nozzle_type', 'stainless_steel') %}
        {% set maint = state_attr('sensor.bambuddy_maintenance_status', 'maintenance_items')
            | default([], true)
            | selectattr('maintenance_type_name', 'eq', 'Clean Nozzle/Hotend')
            | first | default({}, true) %}
        {% set hours_since = maint.get('hours_since_maintenance', 0) | float(0) %}
        {# Wear multiplier by nozzle material #}
        {% set multiplier = {
            'stainless_steel': 1.0,
            'hardened_steel': 0.5,
            'brass': 2.0
        }.get(type_name, 1.0) %}
        {# Base rate: 1% wear per hour, adjusted by nozzle type #}
        {% set wear = (hours_since * multiplier) | round(0) %}
        {{ [wear, 100] | min }}
      unit_of_measurement: "%"
      icon: >-
        {% set wear = states('sensor.printer_1_nozzle_wear_estimate') | int(0) %}
        {% if wear > 80 %}mdi:alert-circle
        {% elif wear > 50 %}mdi:alert
        {% else %}mdi:printer-3d-nozzle{% endif %}
      attributes:
        nozzle_type: >-
          {{ state_attr('sensor.bambuddy_printer_1_status', 'nozzles')
              | default([{}], true) | first | default({}, true)
              | attr('nozzle_type') | default('unknown') }}
        hours_since_clean: >-
          {% set maint = state_attr('sensor.bambuddy_maintenance_status', 'maintenance_items')
              | default([], true)
              | selectattr('maintenance_type_name', 'eq', 'Clean Nozzle/Hotend')
              | first | default({}, true) %}
          {{ maint.get('hours_since_maintenance', 0) | round(1) }}
```

**Template sensor (H2D only): `sensor.printer_{name}_nozzle_rack_wear`**

```yaml
- sensor:
    - name: "Printer H2D Nozzle Rack Wear"
      unique_id: printer_h2d_nozzle_rack_wear
      state: >-
        {% set rack = state_attr('sensor.bambuddy_printer_h2d_status', 'nozzle_rack') | default([], true) %}
        {% if rack | length == 0 %}unavailable
        {% else %}
          {% set max_wear = rack | map(attribute='wear') | select('number') | max | default(0) %}
          {{ max_wear }}
        {% endif %}
      icon: mdi:head-cog
      attributes:
        nozzles: >-
          {% set rack = state_attr('sensor.bambuddy_printer_h2d_status', 'nozzle_rack') | default([], true) %}
          {% set ns = namespace(result=[]) %}
          {% for n in rack %}
            {% set ns.result = ns.result + [{'slot': n.id, 'type': n.nozzle_type, 'diameter': n.nozzle_diameter, 'wear': n.wear}] %}
          {% endfor %}
          {{ ns.result }}
```

**Automation: Nozzle wear alert**

```yaml
alias: "Maintenance: Nozzle Wear Alert"
trigger:
  - platform: numeric_state
    entity_id: sensor.printer_1_nozzle_wear_estimate
    above: 80
action:
  - service: persistent_notification.create
    data:
      title: "Nozzle Wear High: Printer 1"
      message: >-
        Nozzle wear estimate is {{ states('sensor.printer_1_nozzle_wear_estimate') }}%.
        Type: {{ state_attr('sensor.printer_1_nozzle_wear_estimate', 'nozzle_type') }}.
        Consider cleaning or replacing the nozzle.
      notification_id: nozzle_wear_alert_p1
```

---

## Phase 5.7: AMS Humidity-Driven Desiccant Maintenance

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/printers/{printer_id}/status` | AMS unit humidity values: `ams[].humidity` (raw percentage or 1–5 index) |
| `POST` | `/printers/{printer_id}/drying/start` | Start AMS drying cycle (temp, duration, ams_id) |
| `POST` | `/printers/{printer_id}/drying/stop` | Stop AMS drying cycle |
| `POST` | `/maintenance/types` | Create "Replace Desiccant" custom type if needed |

### Feature Scope

**Humidity-aware desiccant tracking** — Link AMS humidity readings to a custom maintenance task for desiccant replacement. When humidity consistently stays above a threshold (even after drying), the desiccant is exhausted and needs replacing.

**Key insight**: Bambuddy's printer status includes `ams[].humidity` (raw sensor percentage on AMS-HT or index 1–5 on regular AMS) and `ams[].dry_time` (minutes remaining in drying cycle). If humidity remains high after a drying cycle completes, the desiccant is the problem.

**Use cases:**
1. **Desiccant health sensor** — Track humidity trend per AMS unit; flag if post-drying humidity is still high
2. **Auto-trigger drying** — When AMS humidity exceeds threshold, automatically start a drying cycle
3. **Desiccant replacement alert** — If humidity stays high after drying, alert user to replace desiccant

### Implementation

**Template sensor: `sensor.ams_{unit}_humidity_status`**

```yaml
- sensor:
    - name: "AMS 0 Humidity Status"
      unique_id: ams_0_humidity_status
      state: >-
        {% set ams_list = state_attr('sensor.bambuddy_printer_1_status', 'ams') | default([], true) %}
        {% set ams = ams_list | selectattr('id', 'eq', 0) | first | default({}, true) %}
        {% set humidity = ams.get('humidity', none) %}
        {% if humidity is none %}unknown
        {% elif humidity | int > 60 %}high
        {% elif humidity | int > 40 %}moderate
        {% else %}good{% endif %}
      icon: >-
        {% if is_state('sensor.ams_0_humidity_status', 'high') %}mdi:water-alert
        {% elif is_state('sensor.ams_0_humidity_status', 'moderate') %}mdi:water
        {% else %}mdi:water-check{% endif %}
      attributes:
        humidity_value: >-
          {% set ams_list = state_attr('sensor.bambuddy_printer_1_status', 'ams') | default([], true) %}
          {% set ams = ams_list | selectattr('id', 'eq', 0) | first | default({}, true) %}
          {{ ams.get('humidity', 'unknown') }}
        is_drying: >-
          {% set ams_list = state_attr('sensor.bambuddy_printer_1_status', 'ams') | default([], true) %}
          {% set ams = ams_list | selectattr('id', 'eq', 0) | first | default({}, true) %}
          {{ (ams.get('dry_time', 0) | int) > 0 }}
```

**Automation: Auto-trigger drying cycle**

```yaml
alias: "Maintenance: AMS Auto-Dry on High Humidity"
trigger:
  - platform: state
    entity_id: sensor.ams_0_humidity_status
    to: "high"
    for: "00:30:00"  # Sustained high humidity for 30 min
condition:
  # Don't start drying if printer is currently printing
  - condition: not
    conditions:
      - condition: state
        entity_id: sensor.bambu_p1s_current_stage
        state: "printing"
  # Don't start if already drying
  - condition: template
    value_template: >-
      {{ state_attr('sensor.ams_0_humidity_status', 'is_drying') != true }}
action:
  - service: rest_command.bambuddy_start_ams_drying
    data:
      printer_id: 1
      ams_id: 0
      temp: 55
      duration: 4
  - service: persistent_notification.create
    data:
      title: "AMS Drying Started"
      message: "AMS 0 humidity was high. Started a 4-hour drying cycle at 55°C."
```

**REST command: `rest_command.bambuddy_start_ams_drying`**

```yaml
bambuddy_start_ams_drying:
  url: >-
    {{ bambuddy_base_url }}/api/v1/printers/{{ printer_id }}/drying/start?ams_id={{ ams_id }}&temp={{ temp | default(55) }}&duration={{ duration | default(4) }}
  method: POST
  headers:
    X-API-Key: !secret bambuddy_api_key
```

**Automation: Desiccant replacement alert (humidity stays high after drying)**

```yaml
alias: "Maintenance: Desiccant Replacement Alert"
description: >-
  After a drying cycle completes, check if humidity has dropped.
  If it's still high, the desiccant is likely exhausted.
trigger:
  - platform: template
    value_template: >-
      {# Trigger when drying finishes (dry_time goes from >0 to 0) #}
      {% set ams_list = state_attr('sensor.bambuddy_printer_1_status', 'ams') | default([], true) %}
      {% set ams = ams_list | selectattr('id', 'eq', 0) | first | default({}, true) %}
      {{ (ams.get('dry_time', 0) | int) == 0 }}
condition:
  # Check if humidity is still high after drying completed
  - condition: state
    entity_id: sensor.ams_0_humidity_status
    state: "high"
action:
  - service: persistent_notification.create
    data:
      title: "Replace Desiccant: AMS 0"
      message: >-
        AMS 0 humidity is still high after drying cycle completed.
        The desiccant packets are likely exhausted and need replacing.
      notification_id: desiccant_alert_ams_0
```

---

## Phase 5.8: Bambuddy System Health Monitoring

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/archives/search/rebuild-index` | Rebuild FTS search index |
| `POST` | `/archives/backfill-hashes` | Calculate missing file hashes for archives |
| `POST` | `/archives/rescan-all` | Re-scan all archive files from disk |
| `POST` | `/archives/recalculate-costs` | Recalculate costs for all archives |
| `GET` | `/printers/{printer_id}/storage` | SD card storage used/free bytes |

### Feature Scope

**Bambuddy server health** — Monitor the Bambuddy application itself as infrastructure. Track SD card storage, database integrity operations, and trigger periodic maintenance tasks on the Bambuddy server.

**Use cases:**
1. **SD card storage sensor** — Alert when printer SD card is nearly full
2. **Scheduled index rebuild** — Weekly automation to keep search index fresh
3. **Archive integrity check** — Monthly hash backfill to detect corrupt/missing archives
4. **Cost recalculation** — After Spoolman pricing updates, recalculate all archive costs

### Implementation

**Template sensor: `sensor.printer_{name}_sd_storage`**

```yaml
- sensor:
    - name: "Printer 1 SD Card Storage"
      unique_id: printer_1_sd_storage
      state: >-
        {% set status = state_attr('sensor.bambuddy_printer_1_status', 'sdcard') | default({}, true) %}
        {% set used = status.get('used_bytes', 0) | float(0) %}
        {% set free = status.get('free_bytes', 0) | float(0) %}
        {% set total = used + free %}
        {% if total > 0 %}
          {{ ((used / total) * 100) | round(1) }}
        {% else %}unknown{% endif %}
      unit_of_measurement: "%"
      icon: mdi:micro-sd
      attributes:
        used_gb: >-
          {% set status = state_attr('sensor.bambuddy_printer_1_status', 'sdcard') | default({}, true) %}
          {{ (status.get('used_bytes', 0) | float / 1073741824) | round(2) }}
        free_gb: >-
          {% set status = state_attr('sensor.bambuddy_printer_1_status', 'sdcard') | default({}, true) %}
          {{ (status.get('free_bytes', 0) | float / 1073741824) | round(2) }}
```

**REST commands for Bambuddy admin tasks**

```yaml
bambuddy_rebuild_search_index:
  url: !secret bambuddy_archives_rebuild_index_url
  method: POST
  headers:
    X-API-Key: !secret bambuddy_api_key

bambuddy_backfill_hashes:
  url: !secret bambuddy_archives_backfill_hashes_url
  method: POST
  headers:
    X-API-Key: !secret bambuddy_api_key

bambuddy_recalculate_costs:
  url: !secret bambuddy_archives_recalculate_costs_url
  method: POST
  headers:
    X-API-Key: !secret bambuddy_api_key
```

**Automation: Weekly index rebuild + hash backfill**

```yaml
alias: "Bambuddy: Weekly Database Maintenance"
trigger:
  - platform: time
    at: "03:00:00"
condition:
  - condition: time
    weekday:
      - sun
action:
  - service: rest_command.bambuddy_rebuild_search_index
  - delay: "00:00:30"
  - service: rest_command.bambuddy_backfill_hashes
  - service: persistent_notification.create
    data:
      title: "Bambuddy Maintenance Complete"
      message: "Weekly search index rebuild and hash backfill completed."
      notification_id: bambuddy_weekly_maintenance
```

**Automation: SD card storage alert**

```yaml
alias: "Maintenance: SD Card Storage Alert"
trigger:
  - platform: numeric_state
    entity_id: sensor.printer_1_sd_storage
    above: 90
action:
  - service: persistent_notification.create
    data:
      title: "SD Card Nearly Full: Printer 1"
      message: >-
        Printer 1 SD card is {{ states('sensor.printer_1_sd_storage') }}% full
        ({{ state_attr('sensor.printer_1_sd_storage', 'free_gb') }} GB free).
        Consider clearing old files from the printer.
      notification_id: sd_storage_alert_p1
```

---

## Cross-Phase Dependencies

```
Phase 5.1 (Fleet Summary)     ← depends on core maintenance sensor
Phase 5.2 (History Log)       ← depends on core maintenance sensor (item IDs)
Phase 5.3 (Custom Types)      ← independent (creates types in Bambuddy)
Phase 5.4 (Hours Calibration) ← depends on core maintenance sensor
Phase 5.5 (Calibration Link)  ← depends on core + 5.4 (post-maintenance trigger)
Phase 5.6 (Nozzle Wear)       ← depends on core + printer status sensor
Phase 5.7 (AMS Humidity)      ← depends on printer status sensor (AMS data)
Phase 5.8 (System Health)     ← independent (Bambuddy admin + printer storage)
```

---

## Priority Ranking

| Priority | Phase | Rationale |
|----------|-------|-----------|
| 1 | 5.1 Fleet Summary | Essential for multi-printer setups; low effort, high visibility |
| 2 | 5.5 Calibration Link | Connects maintenance to calibration action; improves print quality |
| 3 | 5.4 Hours Calibration | Ensures maintenance intervals are accurate; needed for used printers |
| 4 | 5.7 AMS Humidity | Proactive desiccant management prevents print failures; uses existing API |
| 5 | 5.8 System Health | SD card monitoring + scheduled DB maintenance; infrastructure hygiene |
| 6 | 5.6 Nozzle Wear | Useful but heuristic-heavy; H2D wear data is most reliable |
| 7 | 5.2 History Log | Nice for documentation but not actionable day-to-day |
| 8 | 5.3 Custom Types | Limited by HA rest_command not returning responses; better done in Bambuddy UI |

---

## Future Ideas (Not Phased)

- **Maintenance cost tracking** — Create a Bambuddy tag `maintenance_cost:$X` on archives that were linked to a maintenance event (e.g., nozzle replacement mid-print due to clog). Correlate maintenance spend with print success rates.
- **Predictive maintenance** — Use archive failure patterns + maintenance history to predict when failures will spike. E.g., "Your last 3 failures happened between 95–105 hours after nozzle cleaning."
- **Consumable inventory** — Track spare nozzles, PTFE tubes, desiccant packets as inventory items with reorder alerts. Could integrate with Spoolman's broader "consumable" concept if it expands.
- **Maintenance QR codes** — Generate QR codes for each printer that link to a mobile-friendly HA view showing maintenance status. Stick QR on the printer enclosure for quick phone check.
- **MQTT relay integration** — Bambuddy publishes maintenance events via MQTT relay (`on_maintenance_reset`). Instead of polling, subscribe to MQTT events for real-time maintenance state updates in HA.
