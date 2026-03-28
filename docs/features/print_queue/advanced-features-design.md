# Print Queue — Advanced Features Design

> Based on full Bambuddy queue API: [`print_queue.py`](https://github.com/maziggy/bambuddy/blob/main/backend/app/api/routes/print_queue.py)
> Cross-references printer status API for filament/nozzle validation and archive API for reprint.

---

## Phase 4.1: Pre-Queue Filament Readiness Check

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/printers/available-filaments?model={model}` | Deduplicated filaments loaded across all active printers of a given model |
| `GET` | `/queue?printer_id={id}&status=pending` | Pending queue items (each has `required_filament_types`, `filament_type`) |
| `GET` | `/printers/{id}/status` | Live printer status with `ams[].tray[].tray_type`, `nozzles[].nozzle_diameter` |

### Feature Scope

**Readiness check** — Before a queue job starts printing, verify that the required filament types are actually loaded in the target printer's AMS. The Bambuddy scheduler already does this for model-based ("Any X1C") items, but HA can surface the status proactively to the user.

**Use cases:**
1. **Dashboard indicator** — "Next job needs PETG but only PLA is loaded" warning chip
2. **Pre-print notification** — Alert when a queue item's filament needs don't match the printer's loaded filaments
3. **Spool remaining check** — Cross-reference with `spoolman_tray_map` remain percentages to warn if loaded spool has insufficient filament for the next job

### Implementation

**Template sensor: `sensor.bambuddy_queue_filament_ready`**

The queue REST sensor already has `filament_type` and `filament_used_grams` per item. The printer status sensor has the loaded AMS tray data. A template sensor can cross-reference them:

```yaml
- sensor:
    - name: "Bambuddy Queue Next Job Filament Ready"
      unique_id: bambuddy_queue_next_job_filament_ready
      state: >-
        {% set queue = state_attr('sensor.bambuddy_print_queue', 'jobs') | default([], true) %}
        {% set pending = queue | selectattr('status', 'eq', 'pending') | list %}
        {% if pending | length == 0 %}empty
        {% else %}
          {% set next_job = pending[0] %}
          {% set needed = next_job.get('required_filament_types', []) | default([], true) %}
          {% set loaded = state_attr('sensor.bambuddy_printer_1_status', 'ams')
              | default([], true)
              | map(attribute='tray') | sum(start=[])
              | selectattr('tray_type', 'defined')
              | map(attribute='tray_type') | list %}
          {% if needed | reject('in', loaded) | list | length > 0 %}
            mismatch
          {% else %}
            ready
          {% endif %}
        {% endif %}
      icon: >-
        {% if is_state('sensor.bambuddy_queue_next_job_filament_ready', 'mismatch') %}
          mdi:alert-circle
        {% elif is_state('sensor.bambuddy_queue_next_job_filament_ready', 'ready') %}
          mdi:check-circle
        {% else %}
          mdi:tray-remove
        {% endif %}
      attributes:
        needed_types: >-
          {% set queue = state_attr('sensor.bambuddy_print_queue', 'jobs') | default([], true) %}
          {% set pending = queue | selectattr('status', 'eq', 'pending') | list %}
          {{ pending[0].get('required_filament_types', []) if pending | length > 0 else [] }}
        next_job_name: >-
          {% set queue = state_attr('sensor.bambuddy_print_queue', 'jobs') | default([], true) %}
          {% set pending = queue | selectattr('status', 'eq', 'pending') | list %}
          {{ pending[0].get('archive_name', 'Unknown') if pending | length > 0 else 'None' }}
```

**Automation: filament mismatch alert**
```yaml
automation:
  - id: bambuddy_queue_filament_mismatch_alert
    alias: "Bambuddy: Queue Filament Mismatch Alert"
    trigger:
      - trigger: state
        entity_id: sensor.bambuddy_queue_next_job_filament_ready
        to: "mismatch"
    condition:
      - condition: state
        entity_id: input_boolean.bambuddy_queue_alerts_enabled
        state: "on"
    action:
      - action: persistent_notification.create
        data:
          title: "🔴 Queue Filament Mismatch"
          message: >-
            Next job "{{ state_attr('sensor.bambuddy_queue_next_job_filament_ready', 'next_job_name') }}"
            needs {{ state_attr('sensor.bambuddy_queue_next_job_filament_ready', 'needed_types') | join(', ') }}
            but the required filament is not loaded. Load the correct filament or reorder the queue.
          notification_id: bambuddy_queue_filament_mismatch
```

### Phase & Dependencies

- **Phase**: 4.1 (after print_queue core)
- **Depends on**: bambuddy_common (API config), print_queue core (queue sensor), printer status sensor
- **Package**: print_queue
- **Effort**: Medium — template sensor with cross-referencing, one automation

---

## Phase 4.2: Queue Time Estimation & Completion Forecast

### API

Queue item responses already include `print_time_seconds` per item. For currently printing items, the printer status provides `remaining_time` in minutes.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/queue?printer_id={id}&status=pending` | Pending items with `print_time_seconds` |
| `GET` | `/printers/{id}/status` | `remaining_time` for active print (minutes) |

### Feature Scope

**Queue time estimation** — Sum the print times for all pending queue items and add the remaining time of the currently printing item to produce:
1. `sensor.bambuddy_queue_time_remaining` — Total seconds remaining for all queued + active prints
2. `sensor.bambuddy_queue_estimated_completion` — Estimated datetime when the queue will be empty

### Implementation

**Template sensor: `sensor.bambuddy_queue_time_remaining`**
```yaml
- sensor:
    - name: "Bambuddy Queue Time Remaining"
      unique_id: bambuddy_queue_time_remaining
      unit_of_measurement: "h"
      device_class: duration
      state: >-
        {% set queue = state_attr('sensor.bambuddy_print_queue', 'jobs') | default([], true) %}
        {% set pending_seconds = queue
            | selectattr('status', 'eq', 'pending')
            | map(attribute='print_time_seconds')
            | select('number')
            | sum %}
        {% set printing_seconds = queue
            | selectattr('status', 'eq', 'printing')
            | map(attribute='print_time_seconds')
            | select('number')
            | sum %}
        {# Use printer's remaining_time for more accurate active print estimate #}
        {% set remaining_min = states('sensor.bambulab_p1s_remaining_time') | int(0) %}
        {% set active_remaining = remaining_min * 60 if remaining_min > 0 else printing_seconds %}
        {% set total = pending_seconds + active_remaining %}
        {{ (total / 3600) | round(1) }}
      attributes:
        pending_job_count: >-
          {% set queue = state_attr('sensor.bambuddy_print_queue', 'jobs') | default([], true) %}
          {{ queue | selectattr('status', 'eq', 'pending') | list | length }}
        total_seconds: >-
          {% set queue = state_attr('sensor.bambuddy_print_queue', 'jobs') | default([], true) %}
          {% set pending = queue | selectattr('status', 'eq', 'pending')
              | map(attribute='print_time_seconds') | select('number') | sum %}
          {% set remaining_min = states('sensor.bambulab_p1s_remaining_time') | int(0) %}
          {{ pending + (remaining_min * 60) }}
```

**Template sensor: `sensor.bambuddy_queue_estimated_completion`**
```yaml
    - name: "Bambuddy Queue Estimated Completion"
      unique_id: bambuddy_queue_estimated_completion
      device_class: timestamp
      state: >-
        {% set total_sec = state_attr('sensor.bambuddy_queue_time_remaining', 'total_seconds') | int(0) %}
        {% if total_sec > 0 %}
          {{ (now() + timedelta(seconds=total_sec)).isoformat() }}
        {% else %}
          {{ now().isoformat() }}
        {% endif %}
```

**Dashboard integration** — Display as a countdown card:
- "Queue: 3 jobs, ~8.5 hours remaining"
- "Estimated completion: Tomorrow 6:30 AM"
- Progress bar showing current job progress within the queue context

### Phase & Dependencies

- **Phase**: 4.2 (parallel with 4.1)
- **Depends on**: print_queue core (queue sensor with `print_time_seconds`)
- **Package**: print_queue
- **Effort**: Low — two template sensors, dashboard card

---

## Phase 4.3: Smart Queue Notifications

### Feature Scope

Beyond the basic "job added" notification that Bambuddy already sends, HA can provide context-aware queue notifications:

1. **Queue empty** — All pending jobs completed, no more prints queued
2. **Plate clear reminder** — Printer is in FINISH/FAILED state and queue has pending items → remind user to clear the plate (or use `POST /printers/{id}/clear-plate`)
3. **Manual start waiting** — A queue item has `manual_start=true` and is next in line → "Job X is staged and ready, tap to start"
4. **Queue item failed** — A printing item transitioned to failed status with `error_message`

### Implementation

**Automation: queue empty notification**
```yaml
automation:
  - id: bambuddy_queue_empty_notification
    alias: "Bambuddy: Queue Empty"
    trigger:
      - trigger: state
        entity_id: sensor.bambuddy_queue_count
        to: "0"
    condition:
      - condition: template
        value_template: "{{ trigger.from_state.state | int(0) > 0 }}"
      - condition: state
        entity_id: input_boolean.bambuddy_queue_alerts_enabled
        state: "on"
    action:
      - action: persistent_notification.create
        data:
          title: "✅ Print Queue Complete"
          message: "All queued print jobs have finished."
          notification_id: bambuddy_queue_empty
```

**Automation: plate clear reminder**
```yaml
  - id: bambuddy_queue_plate_clear_reminder
    alias: "Bambuddy: Clear Plate for Next Job"
    trigger:
      - trigger: state
        entity_id: sensor.bambulab_p1s_print_status
        to: "completed"
      - trigger: state
        entity_id: sensor.bambulab_p1s_print_status
        to: "failed"
    condition:
      - condition: numeric_state
        entity_id: sensor.bambuddy_queue_count
        above: 0
    action:
      - action: persistent_notification.create
        data:
          title: "🔄 Clear Plate for Next Job"
          message: >-
            Print {{ 'completed' if trigger.to_state.state == 'completed' else 'failed' }}.
            {{ states('sensor.bambuddy_queue_count') }} job(s) remaining in queue.
            Clear the build plate to start the next print.
          notification_id: bambuddy_clear_plate_reminder
```

**Automation: manual start waiting**
```yaml
  - id: bambuddy_queue_manual_start_waiting
    alias: "Bambuddy: Manual Start Job Waiting"
    trigger:
      - trigger: state
        entity_id: sensor.bambuddy_print_queue
    condition:
      - condition: template
        value_template: >-
          {% set queue = state_attr('sensor.bambuddy_print_queue', 'jobs') | default([], true) %}
          {{ queue | selectattr('status', 'eq', 'pending')
              | selectattr('manual_start', 'eq', true) | list | length > 0 }}
    action:
      - action: persistent_notification.create
        data:
          title: "⏸️ Queue Job Waiting for Manual Start"
          message: >-
            {% set queue = state_attr('sensor.bambuddy_print_queue', 'jobs') | default([], true) %}
            {% set waiting = queue | selectattr('status', 'eq', 'pending')
                | selectattr('manual_start', 'eq', true) | list %}
            {{ waiting | length }} job(s) staged for manual start:
            {{ waiting | map(attribute='archive_name') | join(', ') }}
          notification_id: bambuddy_manual_start_waiting
```

### Phase & Dependencies

- **Phase**: 4.3 (after print_queue core)
- **Depends on**: print_queue core (queue sensor), ha-bambulab (print status sensor)
- **Package**: print_queue
- **Effort**: Low — 3-4 automations

---

## Phase 4.4: Nozzle Compatibility Guard

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/printers/{id}/status` | `nozzles[].nozzle_diameter`, `nozzle_rack[]` (H2C tool changer) |
| `GET` | `/queue?printer_id={id}&status=pending` | Queue items with `nozzle_diameter` from archive |

### Feature Scope

Prevent wasted prints by checking if the queue item's required nozzle diameter matches the printer's installed nozzle.

**Simple printers (P1S, X1C, A1)**: Single nozzle — compare `nozzles[0].nozzle_diameter` against queue item's `nozzle_diameter`.

**H2C/H2D (tool changer)**: Multiple nozzles in rack — check if any installed nozzle matches. The H2C `nozzle_rack[]` includes `nozzle_diameter` per slot.

### Implementation

**Template binary_sensor: `binary_sensor.bambuddy_queue_nozzle_mismatch`**
```yaml
- binary_sensor:
    - name: "Bambuddy Queue Nozzle Mismatch"
      unique_id: bambuddy_queue_nozzle_mismatch
      device_class: problem
      state: >-
        {% set queue = state_attr('sensor.bambuddy_print_queue', 'jobs') | default([], true) %}
        {% set next_pending = queue | selectattr('status', 'eq', 'pending') | list | first | default(none) %}
        {% if next_pending is none %}false
        {% else %}
          {% set needed = next_pending.get('nozzle_diameter', '0.4') | string %}
          {% set installed = state_attr('sensor.bambuddy_printer_1_status', 'nozzles')
              | default([]) | map(attribute='nozzle_diameter') | list %}
          {% if needed in installed %}false
          {% else %}true
          {% endif %}
        {% endif %}
      attributes:
        needed_nozzle: >-
          {% set queue = state_attr('sensor.bambuddy_print_queue', 'jobs') | default([], true) %}
          {% set next_pending = queue | selectattr('status', 'eq', 'pending') | list | first | default(none) %}
          {{ next_pending.get('nozzle_diameter', 'unknown') if next_pending else 'none' }}
        installed_nozzles: >-
          {{ state_attr('sensor.bambuddy_printer_1_status', 'nozzles')
              | default([]) | map(attribute='nozzle_diameter') | list }}
```

**Automation: nozzle mismatch alert**
```yaml
automation:
  - id: bambuddy_queue_nozzle_mismatch_alert
    alias: "Bambuddy: Queue Nozzle Mismatch Alert"
    trigger:
      - trigger: state
        entity_id: binary_sensor.bambuddy_queue_nozzle_mismatch
        to: "on"
    action:
      - action: persistent_notification.create
        data:
          title: "⚠️ Nozzle Mismatch"
          message: >-
            Next queue job needs a {{ state_attr('binary_sensor.bambuddy_queue_nozzle_mismatch', 'needed_nozzle') }}mm nozzle
            but installed: {{ state_attr('binary_sensor.bambuddy_queue_nozzle_mismatch', 'installed_nozzles') | join(', ') }}mm.
            Change the nozzle or reorder the queue.
          notification_id: bambuddy_nozzle_mismatch
```

### Phase & Dependencies

- **Phase**: 4.4 (parallel with 4.1-4.3)
- **Depends on**: print_queue core, printer status sensor (for `nozzles` attribute)
- **Package**: print_queue
- **Effort**: Low — one binary_sensor, one automation

---

## Phase 4.5: Batch Filament Planning

### Feature Scope

When multiple jobs are queued, analyze their filament requirements and suggest an optimal printing order that minimizes AMS swaps. This is most valuable for:
- Multi-printer setups with model-based queuing ("Any X1C")
- Sequential printing where changing filament between jobs wastes time

### Concept

A template sensor analyzes all pending queue items, groups them by primary filament type+color, and outputs a suggested batch order:

```json
{
  "groups": [
    {"filament": "PLA #FFFFFF", "jobs": ["Vase", "Box Lid", "Coaster"], "count": 3},
    {"filament": "PETG #000000", "jobs": ["Phone Case", "Bracket"], "count": 2},
    {"filament": "PLA #FF0000", "jobs": ["Keychain"], "count": 1}
  ],
  "current_reorder_savings": "2 filament swaps saved"
}
```

### Implementation

**Template sensor: `sensor.bambuddy_queue_filament_groups`**
```yaml
- sensor:
    - name: "Bambuddy Queue Filament Groups"
      unique_id: bambuddy_queue_filament_groups
      state: >-
        {% set queue = state_attr('sensor.bambuddy_print_queue', 'jobs') | default([], true) %}
        {% set pending = queue | selectattr('status', 'eq', 'pending') | list %}
        {% set types = pending | map(attribute='filament_type') | select('string') | unique | list %}
        {{ types | length }} filament type(s)
      attributes:
        groups: >-
          {% set queue = state_attr('sensor.bambuddy_print_queue', 'jobs') | default([], true) %}
          {% set pending = queue | selectattr('status', 'eq', 'pending') | list %}
          {% set ns = namespace(groups=[]) %}
          {% for job in pending %}
            {% set key = (job.get('filament_type', 'Unknown') ~ ' ' ~ job.get('filament_color', '')) | trim %}
            {% set existing = ns.groups | selectattr('filament', 'eq', key) | list | first | default(none) %}
            {% if existing is none %}
              {% set ns.groups = ns.groups + [{'filament': key, 'jobs': [job.get('archive_name', 'Unknown')]}] %}
            {% endif %}
          {% endfor %}
          {{ ns.groups }}
        unique_filament_count: >-
          {% set queue = state_attr('sensor.bambuddy_print_queue', 'jobs') | default([], true) %}
          {% set pending = queue | selectattr('status', 'eq', 'pending') | list %}
          {{ pending | map(attribute='filament_type') | select('string') | unique | list | length }}
```

**Dashboard integration** — A card showing filament groups with a visual indicator of how many swaps the current order requires vs. an optimized order. The actual reordering is done via `POST /api/v1/queue/reorder` from the Bambuddy UI — HA surfaces the insight, Bambuddy executes the reorder.

### Phase & Dependencies

- **Phase**: 4.5 (after core, non-critical)
- **Depends on**: print_queue core (queue sensor with filament attributes)
- **Package**: print_queue
- **Effort**: Medium — template sensor with grouping logic, dashboard card

---

## Phase 4.6: Reprint from HA

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/queue` | Add to queue with `archive_id`, `printer_id`, `ams_mapping`, `plate_id`, print options |

### Feature Scope

Add a "Reprint" button to the print history dashboard that re-queues a previous print. The queue add endpoint accepts an `archive_id` plus print options, so HA can re-queue any archive without needing the original 3MF.

**Key fields for queue add:**
- `archive_id` — Required, references the archive to reprint
- `printer_id` — Target printer (or `target_model` for any-printer)
- `plate_id` — For multi-plate 3MF files
- `ams_mapping` — AMS slot assignments (auto-generated from `spoolman_tray_map`)
- `bed_levelling`, `flow_cali`, `vibration_cali` — Calibration options
- `timelapse` — Enable timelapse
- `use_ams` — Use AMS (default true)
- `manual_start` — Stage without auto-start
- `copies` — Not in schema; achieved by adding multiple queue items

### Implementation

**REST Command: `bambuddy_reprint`**
```yaml
rest_command:
  bambuddy_reprint:
    url: "{{ states('input_text.bambuddy_api_base_url') }}/api/v1/queue"
    method: POST
    headers:
      X-API-Key: !secret bambuddy_api_key
      Content-Type: application/json
    payload: >-
      {
        "archive_id": {{ archive_id }},
        "printer_id": {{ printer_id | default(1) }}
      }
```

**Script: `bambuddy_reprint_from_archive`**
```yaml
script:
  bambuddy_reprint_from_archive:
    alias: "Bambuddy: Reprint from Archive"
    fields:
      archive_id:
        description: "Archive ID to reprint"
        required: true
        selector:
          number:
            min: 1
            mode: box
      printer_id:
        description: "Target printer ID (default: 1)"
        required: false
        selector:
          number:
            min: 1
            mode: box
    sequence:
      - action: rest_command.bambuddy_reprint
        data:
          archive_id: "{{ archive_id }}"
          printer_id: "{{ printer_id | default(1) }}"
      # Refresh queue sensor to show the new item
      - action: homeassistant.update_entity
        target:
          entity_id: sensor.bambuddy_print_queue
```

**Dashboard integration** — "Reprint" button on each archive row in the print history card. Tapping it calls `script.bambuddy_reprint_from_archive` with the archive_id. The job appears in the queue immediately.

### AMS Mapping Auto-Generation (Future)

When `spoolman_tray_map` is available, auto-generate `ams_mapping` by matching the archive's filament slots to current AMS tray positions:
1. Read archive filament requirements: `GET /archives/{id}/filament-requirements`
2. For each required slot, find a matching tray in `spoolman_tray_map` by UUID, then by color+material
3. Build the `ams_mapping` array and include it in the queue add request

This is complex enough to warrant its own sub-phase and depends on print_history enrichment being functional.

### Phase & Dependencies

- **Phase**: 4.6 (after print_queue core + print_history core)
- **Depends on**: bambuddy_common (API config), print_queue core, print_history (for archive_id context)
- **Package**: print_queue (REST command + script) + print_history (dashboard button)
- **Effort**: Medium — REST command, script, dashboard integration

---

## Priority & Cross-Reference Table

| Phase | Feature | Effort | Value | Dependencies |
|-------|---------|--------|-------|--------------|
| 4.1 | Pre-Queue Filament Readiness | Medium | High | print_queue core, printer status |
| 4.2 | Queue Time Estimation | Low | High | print_queue core |
| 4.3 | Smart Queue Notifications | Low | Medium | print_queue core, ha-bambulab |
| 4.4 | Nozzle Compatibility Guard | Low | High | print_queue core, printer status |
| 4.5 | Batch Filament Planning | Medium | Low | print_queue core |
| 4.6 | Reprint from HA | Medium | High | print_queue + print_history core |

**Recommended order**: 4.2 → 4.4 → 4.1 → 4.3 → 4.6 → 4.5

- 4.2 and 4.4 are low-effort, high-value — implement first
- 4.1 and 4.3 add safety net and UX polish
- 4.6 is the crown jewel (reprint from HA) but depends on print_history
- 4.5 is nice-to-have analysis, implement last

---

## Future Ideas (Not Phased)

### Queue-to-Archive Linking
When a queue item starts printing, Bambuddy creates an archive. A webhook or polling automation could capture the `archive_id` from the printing state and store it for end-to-end tracking (queue item → archive → enrichment → final record).

### Print Scheduling Dashboard
Use the `scheduled_time` field on queue items to build a visual calendar view of upcoming prints. Display as a timeline with estimated print durations overlaid.

### Filament-Aware Auto-Routing
For multi-printer farms with model-based queuing, automatically suggest which printer should get which job based on currently loaded filaments. Combines `available-filaments` endpoint with queue items' `required_filament_types` to minimize filament changes across the fleet.
