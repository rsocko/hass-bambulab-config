# Printer Temperature Cards - Quick Start Guide

## 🎯 What You Get

Two temperature cards showing:
- 🌡️ **Nozzle Temperature**: Current + Target with color-coded heating/cooling indicator
- 🛏️ **Bed Temperature**: Current + Target with color-coded heating/cooling indicator

## 🚀 5-Minute Setup

### Step 1: Install Prerequisites (HACS)

1. Open **HACS** in Home Assistant
2. Click **Frontend**
3. Search and install:
   - **Mushroom Cards** ✓
   - **card-mod** ✓
4. **Restart Home Assistant**

### Step 2: Find Your Printer Entity Name

1. Go to **Developer Tools** → **States**
2. Search for `temperature`
3. Find your printer's sensors (example: `sensor.bambulab_x1c_nozzle_temperature`)
4. Note the printer name part (example: `bambulab_x1c`)

### Step 3: Copy Card Configuration

1. Open [homeassistant/packages/3d_printing/printer_temps/dashboard_cards/printer-temps.yaml](../../../homeassistant/packages/3d_printing/printer_temps/dashboard_cards/printer-temps.yaml)
2. Copy the full configuration (starts with `type: horizontal-stack`)
3. Paste into your Home Assistant dashboard:
   - Edit Dashboard → Add Card → Manual Card → Paste → Save

## 📱 Example Configuration

For a printer named `bambulab_x1c`:

```yaml
type: horizontal-stack
cards:
  - type: custom:mushroom-template-card
    entity: sensor.bambulab_x1c_nozzle_temperature
    primary: >-
      {% set target = states('sensor.bambulab_x1c_nozzle_target_temperature') | float(0) %}
      {{ target | round(0) }}°C
    # ... (rest of configuration)
```

## 🎨 Color Meanings

| Color | Icon | State | Meaning |
|-------|------|-------|---------|
| 🔴 Red | ⬆️ | Heating | Target > Current (+2°C) |
| 🔵 Blue | ⬇️ | Cooling | Target < Current (-2°C) |
| ⚪ Grey | 🌡️ | Stable | At target (±2°C) |

## 📐 Layout Options

### Option 1: Side-by-Side (Recommended)
```
┌───────────────┬───────────────┐
│ 🔴  220°C     │ 🔵  80°C      │
│    218°C      │    85°C       │
└───────────────┴───────────────┘
```
**Use**: `type: horizontal-stack`

### Option 2: Stacked Vertically
```
┌───────────────┐
│ 🔴  220°C     │
│    218°C      │
├───────────────┤
│ 🔵  80°C      │
│    85°C       │
└───────────────┘
```
**Use**: `type: vertical-stack`

### Option 3: Separate Cards
Place each card independently in your dashboard

## 🔧 Common Issues

### "Unknown" or "Unavailable"

**Fix**: Check entity names match exactly

```bash
# In Developer Tools → States, search for:
- sensor.YOUR_PRINTER_nozzle_temperature
- sensor.YOUR_PRINTER_nozzle_target_temperature
- sensor.YOUR_PRINTER_bed_temperature
- sensor.YOUR_PRINTER_bed_target_temperature
```

### Colors Not Showing

**Fix**: Install card-mod from HACS, restart HA, clear browser cache

### Temperatures Not Updating

**Fix**: Ensure Bambu Lab integration uses **LAN mode** (required for temperature sensors)

1. Settings → Devices & Services
2. Find Bambu Lab integration
3. Configure → Enable LAN mode
4. Restart integration

## 📖 Full Documentation

See [printer-temps-cards.md](printer-temps-cards.md) for:
- Detailed customization options
- Advanced layout examples
- Troubleshooting guide
- Technical details

## ✅ Checklist

- [ ] Mushroom Cards installed from HACS
- [ ] card-mod installed from HACS
- [ ] Home Assistant restarted
- [ ] Printer entity name identified
- [ ] YAML customized with correct entity names
- [ ] Card added to dashboard
- [ ] Temperatures displaying correctly
- [ ] Colors changing based on heating/cooling state

## 🎉 You're Done!

Your printer temperature cards should now be displaying beautifully with color-coded heating/cooling indicators!

---

**Need Help?** See the full documentation or open an issue in the repository.




