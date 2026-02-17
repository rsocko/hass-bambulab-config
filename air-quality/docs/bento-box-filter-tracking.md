# Bento Box Filter Tracking System

## Overview

The Bento Box filter tracking system monitors HEPA and carbon filter usage based on fan runtime, helping you know exactly when to replace filters for optimal air quality.

## Features

- **Automatic Runtime Tracking** - Tracks fan runtime in hours for both filters
- **Usage Percentage** - Shows how much filter life has been used
- **Replacement Alerts** - Notifications at 75%, 90%, and 100% usage
- **Days Since Replacement** - Tracks time since last filter change
- **Easy Reset** - Simple scripts to reset counters after replacement
- **Configurable Thresholds** - Adjust max hours based on your usage

## Why Track Filter Runtime?

Filter replacement should be based on **actual usage**, not just time elapsed, because:

1. **Variable Usage** - Filters accumulate particles only when the fan runs
2. **High-VOC Materials** - ABS/ASA printing stresses carbon filters more
3. **Cost Optimization** - Replace only when needed, not on arbitrary schedules
4. **Air Quality** - Know exactly when filtration efficiency drops
5. **Maintenance Planning** - Get advance warning to order replacements

## Filter Replacement Guidelines

### HEPA Filter
- **Default Threshold**: 2000 hours
- **Typical Lifespan**: 
  - 24/7 operation: ~83 days
  - 8h/day average: ~250 days
  - Actual varies based on usage patterns
- **Signs of wear**:
  - Visible dirt/discoloration
  - Reduced airflow
  - PM2.5 readings don't improve when fan runs

### Carbon Filter
- **Default Threshold**: 1000 hours
- **Typical Lifespan**:
  - 24/7 operation: ~42 days
  - 8h/day average: ~125 days
  - Shorter with high-VOC materials (ABS, ASA, PC)
- **Signs of wear**:
  - VOC readings don't improve when fan runs
  - Odors not being filtered
  - Filter feels saturated or heavy

## Installation

### Step 1: Add Input Helpers

Copy the contents of `bento_box_filter_helpers.yaml` to your Home Assistant configuration.

**Option A: Add to configuration.yaml**
```yaml
# In your configuration.yaml, add:
input_number: !include bento_box_filter_helpers.yaml
input_datetime: !include bento_box_filter_helpers.yaml
input_boolean: !include bento_box_filter_helpers.yaml
template: !include bento_box_filter_helpers.yaml
```

**Option B: Include entire file**
```yaml
# In your configuration.yaml:
homeassistant:
  packages:
    bento_box_filters: !include air-quality/bento_box_filter_helpers.yaml
```

**Option C: Manual entry via UI**
1. Settings > Devices & Services > Helpers
2. Add each input helper manually using values from the YAML file

After adding, restart Home Assistant or reload:
- Developer Tools > YAML > Input Helpers

### Step 2: Import Automations

Import these automations via Settings > Automations & Scenes:

1. **`bento_box_filter_runtime_tracking.yaml`**
   - Tracks fan runtime every minute
   - Accumulates hours for both filters
   - Can be disabled via toggle

2. **`bento_box_filter_alerts.yaml`**
   - Sends notifications at key thresholds
   - Creates persistent alerts for overdue filters
   - Runs hourly

### Step 3: Add Reset Scripts

Add these to your `scripts.yaml`:

```yaml
reset_hepa_filter:
  alias: Reset HEPA Filter Counter
  sequence:
    - action: input_number.set_value
      target:
        entity_id: input_number.bento_box_hepa_runtime_hours
      data:
        value: 0
    - action: input_datetime.set_datetime
      target:
        entity_id: input_datetime.bento_box_hepa_last_replaced
      data:
        datetime: "{{ now().isoformat() }}"
    - action: notify.notify
      data:
        message: "HEPA filter counter reset"

reset_carbon_filter:
  alias: Reset Carbon Filter Counter
  sequence:
    - action: input_number.set_value
      target:
        entity_id: input_number.bento_box_carbon_runtime_hours
      data:
        value: 0
    - action: input_datetime.set_datetime
      target:
        entity_id: input_datetime.bento_box_carbon_last_replaced
      data:
        datetime: "{{ now().isoformat() }}"
    - action: notify.notify
      data:
        message: "Carbon filter counter reset"
```

### Step 4: Add Dashboard Cards

Choose from 4 card styles in `dashboards/bento-box-filter-cards.yaml`:
1. **Compact Horizontal** - Side-by-side filter status
2. **Detailed Vertical** - Comprehensive info with reset buttons
3. **Gauge Cards** - Visual meter representation
4. **Progress Bars** - Bar chart style (requires bar-card)

Copy desired style to your dashboard.

### Step 5: Initial Setup

1. **Set current runtime** (if filters are used):
   - Estimate current hours based on usage
   - Or start from 0 for new filters
   
2. **Set last replacement date**:
   - Enter when filters were last changed
   - Or set to "now" if starting fresh

3. **Adjust thresholds** (optional):
   - HEPA: Default 2000h (adjust 100-10000h)
   - Carbon: Default 1000h (adjust 100-10000h)

## Usage

### Daily Operation

The system works automatically:
1. Fan runs → Runtime accumulates
2. Filters tracked → Usage percentage updates
3. Thresholds reached → Notifications sent
4. You replace filters → Reset counters

### Monitoring

**Dashboard Cards** show:
- Current usage percentage
- Total runtime hours
- Days since last replacement
- Status (Good / Monitor / Replace Soon / Replace Now)
- Color-coded indicators

**Notifications** sent at:
- **75%** - Monitor (yellow) - "Check filters"
- **90%** - Replace Soon (orange) - "Order replacements"
- **100%** - Overdue (red) - "Replace immediately"

### After Filter Replacement

1. **Replace physical filters**
2. **Reset counter via dashboard button** or:
   - Developer Tools > Services
   - Call `script.reset_hepa_filter` or `script.reset_carbon_filter`
3. **Confirm reset** in dashboard (should show 0%)

## Sensor Reference

### Input Helpers

| Entity | Purpose | Default |
|--------|---------|---------|
| `input_number.bento_box_hepa_runtime_hours` | HEPA runtime | 0 |
| `input_number.bento_box_carbon_runtime_hours` | Carbon runtime | 0 |
| `input_number.bento_box_hepa_max_hours` | HEPA threshold | 2000h |
| `input_number.bento_box_carbon_max_hours` | Carbon threshold | 1000h |
| `input_datetime.bento_box_hepa_last_replaced` | HEPA replace date | - |
| `input_datetime.bento_box_carbon_last_replaced` | Carbon replace date | - |
| `input_boolean.bento_box_filter_tracking_enabled` | Enable tracking | On |

### Template Sensors

| Entity | Shows |
|--------|-------|
| `sensor.bento_box_hepa_filter_usage` | HEPA usage % |
| `sensor.bento_box_carbon_filter_usage` | Carbon usage % |
| `sensor.bento_box_filter_status` | Overall status |

### Sensor Attributes

Each filter sensor provides:
- `runtime_hours` - Total hours accumulated
- `max_hours` - Replacement threshold
- `remaining_hours` - Hours until replacement
- `status` - good / warning / replace_soon / overdue
- `days_since_replacement` - Days since last reset

## Customization

### Adjust Replacement Thresholds

Via UI:
1. Settings > Devices & Services > Helpers
2. Find "Bento Box HEPA/Carbon Filter Max Hours"
3. Adjust value

Via YAML:
```yaml
input_number:
  bento_box_hepa_max_hours:
    initial: 2500  # Increase from 2000
  
  bento_box_carbon_max_hours:
    initial: 800   # Decrease from 1000
```

### Change Alert Thresholds

Edit `bento_box_filter_alerts.yaml`:

```yaml
# Change from 75% to 80%
- condition: template
  value_template: "{{ hepa_usage >= 80 and hepa_usage < 90 }}"
```

### Disable Specific Alerts

Comment out sections in `bento_box_filter_alerts.yaml`:

```yaml
# Disable 75% warning alerts
# - conditions:
#     - condition: template
#       value_template: "{{ hepa_usage >= 75 and hepa_usage < 90 }}"
#   sequence:
#     - action: notify.notify
#       ...
```

### Track Differently for Each Filter

If you want different tracking (e.g., carbon degrades faster with high-VOC):

Create separate automations or modify runtime tracking:

```yaml
# In runtime tracking automation:
- action: input_number.set_value
  target:
    entity_id: input_number.bento_box_carbon_runtime_hours
  data:
    value: >
      {% set increment = runtime_increment %}
      {% set filament_type = state_attr('sensor.ntk_ryansoffice_3dprinter_active_tray', 'type') | upper %}
      {% set high_voc = filament_type in ['ABS', 'ASA', 'PC', 'NYLON'] %}
      {% if high_voc %}
        {{ (current_carbon_runtime | float + increment * 1.5) | round(2) }}
      {% else %}
        {{ (current_carbon_runtime | float + increment) | round(2) }}
      {% endif %}
```

## Maintenance Schedule Recommendations

### Conservative (Maximum Filtration)
- **HEPA**: Replace every 1500 hours
- **Carbon**: Replace every 750 hours
- Best for: Frequent high-VOC printing, sensitive users

### Standard (Recommended)
- **HEPA**: Replace every 2000 hours
- **Carbon**: Replace every 1000 hours
- Best for: Mixed usage, typical 3D printing

### Extended (Budget-Conscious)
- **HEPA**: Replace every 2500 hours
- **Carbon**: Replace every 1200 hours
- Best for: Mostly PLA printing, good ventilation
- **Note**: Monitor air quality sensors for degradation

### High-VOC Usage
- **HEPA**: Replace every 2000 hours
- **Carbon**: Replace every 600-800 hours
- Best for: Frequent ABS/ASA/PC printing
- **Reason**: Carbon filters saturate faster with strong VOCs

## Troubleshooting

### Runtime Not Accumulating

**Check:**
1. Tracking enabled: `input_boolean.bento_box_filter_tracking_enabled` is On
2. Fan entity correct: `fan.bento_box_fan` exists and shows "on" state
3. Automation enabled: `bento_box_filter_runtime_tracking` is active
4. Check automation traces for errors

### Alerts Not Sending

**Check:**
1. Alert automation enabled
2. Usage percentage calculated correctly
3. Notification service configured
4. Check automation traces

### Sensors Showing "Unknown"

**Check:**
1. Input helpers created and loaded
2. Template sensors have valid data
3. Restart Home Assistant
4. Check Developer Tools > States for entities

### Usage Percentage Incorrect

**Verify:**
1. Runtime hours are reasonable
2. Max hours threshold is correct
3. Calculation: (runtime / max_hours) × 100

### Want to Reset Completely

**To start fresh:**
1. Set both runtime counters to 0
2. Set replacement dates to now
3. Optionally reset thresholds to defaults

## Filter Replacement Procedure

### When to Replace

**Replace when:**
- ✅ Usage reaches 100%
- ✅ Air quality sensors show reduced filtration
- ✅ Visual inspection shows dirt/saturation
- ✅ Airflow seems reduced
- ✅ Odors not being filtered (carbon)

**Optional early replacement:**
- Before printing critical parts
- After extended high-VOC printing
- When maximum filtration needed

### Replacement Steps

1. **Order Filters**
   - HEPA: [Specify your filter model]
   - Carbon: [Specify your filter model]
   - Order at 90% usage for timely arrival

2. **Replace Physical Filters**
   - Power off Bento Box fan
   - Remove old filters
   - Clean filter housing if needed
   - Install new filters
   - Verify proper seating

3. **Reset Counters**
   - Use dashboard reset buttons, or
   - Call scripts via Developer Tools
   - Verify counters show 0%

4. **Document**
   - Note replacement in maintenance log
   - Save old filter condition photo (optional)
   - Record any air quality improvements

## Cost Analysis

### Example Calculation

**Assumptions:**
- HEPA filter: $30 every 2000h
- Carbon filter: $20 every 1000h
- Average usage: 8h/day

**Annual Costs:**
- HEPA: $30 × (365 × 8h / 2000h) = ~$44/year
- Carbon: $20 × (365 × 8h / 1000h) = ~$58/year
- **Total: ~$102/year**

**Compare to:**
- Arbitrary schedule (every 3 months): ~$200/year
- **Savings: ~$98/year with runtime tracking**

## Integration with Existing Systems

### Air Quality Automations

Filter tracking integrates with:
- Bento Box fan control automation
- Air quality alerts
- Print start/complete automations

All work independently - no conflicts.

### Maintenance Dashboard

Combine with other maintenance tracking:
```yaml
# Example: Printer maintenance section
type: vertical-stack
cards:
  - type: markdown
    content: "# Printer Maintenance"
  
  # Bento Box filters
  - [Include filter cards here]
  
  # Other maintenance items
  - type: custom:mushroom-template-card
    primary: "Nozzle Cleaning"
    secondary: "Due in X days"
```

## Advanced Features

### Predictive Replacement

Calculate estimated replacement date:

```yaml
template:
  - sensor:
      - name: "Bento Box HEPA Replacement Date"
        state: >
          {% set runtime = states('input_number.bento_box_hepa_runtime_hours') | float(0) %}
          {% set max_hours = states('input_number.bento_box_hepa_max_hours') | float(2000) %}
          {% set remaining = max_hours - runtime %}
          
          # Estimate based on recent usage (last 7 days)
          {% set daily_avg = 8 %}  # Adjust based on your usage
          {% set days_remaining = (remaining / daily_avg) | round(0) %}
          
          {{ (now() + timedelta(days=days_remaining)).strftime('%Y-%m-%d') }}
```

### Usage Statistics

Track usage patterns:

```yaml
# Calculate average daily runtime
template:
  - sensor:
      - name: "Bento Box Average Daily Runtime"
        state: >
          {% set runtime = states('input_number.bento_box_hepa_runtime_hours') | float(0) %}
          {% set days = state_attr('sensor.bento_box_hepa_filter_usage', 'days_since_replacement') | int(1) %}
          {{ (runtime / days) | round(1) }}
        unit_of_measurement: "h/day"
```

### Filter Cost Tracking

Add cost tracking:

```yaml
input_number:
  bento_box_hepa_filter_cost:
    name: "HEPA Filter Cost"
    min: 0
    max: 200
    step: 0.01
    unit_of_measurement: "$"
    icon: mdi:currency-usd

template:
  - sensor:
      - name: "HEPA Filter Cost Per Hour"
        state: >
          {% set cost = states('input_number.bento_box_hepa_filter_cost') | float(30) %}
          {% set max_hours = states('input_number.bento_box_hepa_max_hours') | float(2000) %}
          {{ (cost / max_hours) | round(3) }}
        unit_of_measurement: "$/h"
```

## Support

### Common Questions

**Q: Do I need to track both filters separately?**
A: Yes. HEPA and carbon filters have different lifespans and purposes.

**Q: What if I forget to reset after replacement?**
A: Usage will exceed 100%, alerts will continue. Reset when you remember - accuracy preserved going forward.

**Q: Can I track runtime by fan speed?**
A: Yes, modify the tracking automation to weight runtime by speed percentage.

**Q: My filters last longer/shorter than defaults?**
A: Adjust the max hours thresholds to match your experience.

**Q: Does this work with other fans?**
A: Yes! Adapt entity IDs for any fan entity in Home Assistant.

## Related Documentation

- [Bento Box Fan Control](bento-box-fan-filament-control.md) - Main fan automation
- [Air Quality Integration](README.md) - Complete air quality system
- [Filter Replacement Schedule](FILTER_MAINTENANCE.md) - Detailed maintenance guide

## Summary

The Bento Box filter tracking system provides:

✅ **Automatic runtime tracking** based on actual fan usage  
✅ **Usage percentage** for easy monitoring  
✅ **Replacement alerts** at key thresholds  
✅ **Easy reset** after filter changes  
✅ **Cost optimization** through usage-based replacement  
✅ **Integration** with existing air quality system  

**No more guessing - know exactly when to replace your filters! 🔧🌬️✨**
