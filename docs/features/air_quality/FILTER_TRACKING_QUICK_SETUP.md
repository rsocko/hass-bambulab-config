# Bento Box Filter Tracking - Quick Setup Guide

## What This Does

Automatically tracks how long your Bento Box fan has run to tell you exactly when to replace HEPA and carbon filters. No more guessing!

## Quick Start (15 Minutes)

### Step 1: Add Input Helpers (5 minutes)

**Option A: Via UI (Easiest)**
1. Settings > Devices & Services > Helpers
2. Click "+ Create Helper" for each:

**Create these Input Numbers:**
- Name: `Bento Box HEPA Filter Runtime`
  - Min: 0, Max: 10000, Step: 0.1, Unit: h
  - Entity ID will be: `input_number.bento_box_hepa_runtime_hours`

- Name: `Bento Box Carbon Filter Runtime`
  - Min: 0, Max: 10000, Step: 0.1, Unit: h

- Name: `Bento Box HEPA Filter Max Hours`
  - Min: 100, Max: 10000, Step: 50, Initial: 2000, Unit: h

- Name: `Bento Box Carbon Filter Max Hours`
  - Min: 100, Max: 10000, Step: 50, Initial: 1000, Unit: h

**Create these Date/Time Helpers:**
- Name: `Bento Box HEPA Filter Last Replaced`
  - Has date: Yes, Has time: Yes

- Name: `Bento Box Carbon Filter Last Replaced`
  - Has date: Yes, Has time: Yes

**Create this Toggle:**
- Name: `Bento Box Filter Tracking Enabled`
  - Initial: On

**Option B: Via YAML (Faster)**
1. Add `bento_box_filter_helpers.yaml` to your configuration
2. Restart Home Assistant

### Step 2: Import Automations (5 minutes)

**Runtime Tracking:**
1. Settings > Automations & Scenes > "+ Create Automation"
2. Click "⋮" menu > "Edit in YAML"
3. Paste entire contents of `bento_box_filter_runtime_tracking.yaml`
4. Save as "Bento Box Filter Runtime Tracking"

**Replacement Alerts:**
1. Create another automation
2. Paste contents of `bento_box_filter_alerts.yaml`
3. Save as "Bento Box Filter Replacement Alerts"

### Step 3: Add Reset Scripts (3 minutes)

Add to your `scripts.yaml`:

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

Reload scripts: Developer Tools > YAML > Scripts

### Step 4: Add Dashboard Card (2 minutes)

The Bento Box filter card in [bento-box-filter-cards.yaml](../../../homeassistant/packages/3d_printing/air_quality/dashboard_cards/bento-box-filter-cards.yaml) is a single compact mushroom card. Tapping it opens a browser_mod popup with full filter detail and reset buttons.

1. Edit your dashboard
2. Add card > Manual
3. Paste the YAML from the file (or use `!include`)
4. Save

> **Requires:** mushroom, card-mod, and browser-mod (HACS)

### Step 5: Set Initial Values (Optional)

If your filters are already used:

**Estimate runtime:**
- Check how long you've had filters
- Estimate average hours per day fan runs
- Example: 30 days × 8 hours/day = 240 hours

**Set values:**
1. Developer Tools > Services
2. Service: `input_number.set_value`
3. Target: `input_number.bento_box_hepa_runtime_hours`
4. Value: 240
5. Call service
6. Repeat for carbon filter

**Or start fresh:**
- Leave at 0 if filters are new
- Set replacement dates to today

## What Happens Next

### Automatic Operation
1. Fan runs → Runtime accumulates
2. Reaches 75% → Get notification "Monitor filters"
3. Reaches 90% → Get notification "Replace soon, order now"
4. Reaches 100% → Get notification "Replace immediately"

### When You Replace Filters
1. Replace physical filters
2. Tap the Bento Box card on your dashboard to open the popup
3. Tap "Reset HEPA" and/or "Reset Carbon" buttons in the popup
4. Counters reset to 0%

## Dashboard Display

Main dashboard shows a single compact card:
```
┌──────────────────────────────────────┐
│  ✅ Bento Box                        │
│  Good · HEPA 45% · Carbon 67%       │
└──────────────────────────────────────┘
```

Tapping opens a popup with full details, fan speed control, and reset buttons.

Color codes:
- 🟢 Green: 0-74% (Good)
- 🟡 Yellow: 75-89% (Monitor)
- 🟠 Orange: 90-99% (Replace Soon)
- 🔴 Red: 100%+ (Overdue)

## Notification Examples

**At 75%:**
```
ℹ️ HEPA Filter - Monitor
Usage: 75%
Remaining: ~500h
Consider ordering replacement filter.
```

**At 90%:**
```
⚠️ Carbon Filter - Replace Soon
Usage: 90%
Remaining: ~100h
Order replacement filter now.
```

**At 100%:**
```
🚨 HEPA Filter Overdue
Usage: 102%
Runtime: 2040h
Replace filter immediately for optimal air filtration.
```

## Default Settings

**HEPA Filter:**
- Max hours: 2000h
- If fan runs 8h/day: ~250 days per filter
- If fan runs 24/7: ~83 days per filter

**Carbon Filter:**
- Max hours: 1000h
- If fan runs 8h/day: ~125 days per filter
- If fan runs 24/7: ~42 days per filter
- **Note:** High-VOC materials (ABS, ASA) reduce lifespan

## Customization

### Change Replacement Thresholds

Via dashboard or:
1. Settings > Helpers
2. Find "Bento Box HEPA/Carbon Filter Max Hours"
3. Adjust value

**Conservative:** HEPA 1500h, Carbon 750h  
**Standard:** HEPA 2000h, Carbon 1000h (default)  
**Extended:** HEPA 2500h, Carbon 1200h

### Disable Tracking Temporarily

1. Find "Bento Box Filter Tracking Enabled" helper
2. Toggle off
3. Runtime won't accumulate while disabled

### Change Alert Frequency

Edit `bento_box_filter_alerts.yaml`:
```yaml
# Change from hourly to every 6 hours
triggers:
  - trigger: time_pattern
    hours: "/6"  # Was "/1"
```

## Troubleshooting

**Runtime not accumulating?**
- Check "Bento Box Filter Tracking Enabled" is On
- Verify `fan.bento_box_fan` entity exists and works
- Check automation "Bento Box Filter Runtime Tracking" is enabled

**No alerts?**
- Check automation "Bento Box Filter Replacement Alerts" is enabled
- Verify notification service is configured
- Test by manually setting usage to 76%

**Sensors showing "Unknown"?**
- Restart Home Assistant
- Check all input helpers are created
- Verify entity IDs match exactly

**Want to reset completely?**
- Set both runtime counters to 0
- Set replacement dates to now
- Reset max hours to defaults if changed

## When to Replace Filters

### Replace When:
- ✅ Usage reaches 90-100%
- ✅ Visual inspection shows heavy dirt/discoloration
- ✅ Airflow seems reduced
- ✅ Odors not being filtered (carbon)
- ✅ Air quality sensors show reduced filtration

### Don't Replace If:
- ❌ Low usage but time has passed (trust the runtime!)
- ❌ Filters look clean and airflow good
- ❌ Air quality readings are excellent

## Cost Savings Example

**Without tracking (time-based):**
- Replace every 3 months regardless
- Cost: ~$200/year

**With runtime tracking (usage-based):**
- Replace when actually needed
- Cost: ~$102/year
- **Savings: ~$98/year!**

## Next Steps

1. ✅ Complete setup above
2. ✅ Monitor for a few weeks
3. ✅ Adjust thresholds if needed
4. ✅ Set reminders in calendar when filters reach 90%
5. ✅ Order replacement filters in advance

## Support

**Detailed documentation:**
- [docs/bento-box-filter-tracking.md](docs/bento-box-filter-tracking.md) - Complete guide
- [docs/features/air_quality/README.md](README.md) - Air quality system overview

**Questions?**
- Check automation traces in Home Assistant
- Review logbook for filter events
- Verify entity IDs in Developer Tools > States

## Summary

You now have:
✅ Automatic runtime tracking  
✅ Usage percentage monitoring  
✅ Multi-tier replacement alerts  
✅ Easy filter reset process  
✅ Cost-optimized maintenance  

**No more guessing when to replace filters - let the system tell you! 🔧✨**



