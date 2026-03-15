# Power Monitoring

Real-time power usage tracking for the 3D printing station, powered by a **TP-Link Kasa Power Strip (AB64)** with per-outlet energy monitoring.

> **GitHub Issue:** [#426 — Show Power Usage](https://github.com/rsocko/hass-bambulab-config/issues/426)

---

## Overview

A compact dashboard card shows the aggregate power draw (watts) and today's energy consumption (kWh) at a glance. Tapping the card opens a detailed popup with:

- **Per-device power breakdown** — live wattage for each plug on the strip
- **Today's consumption by device** — kWh breakdown table
- **24-hour power history** — stacked area chart (ApexCharts) showing each device's contribution over time
- **Electrical detail** — voltage and current readings

## Hardware

| Device | Power Strip Plug | Entity ID Prefix |
|---|---|---|
| 3D Printer (Bambu P1S) | Plug 4 (entity: `ams_heater`) | `tp_link_power_strip_ab64_ams_heater_*` |
| WLED LED Strip | Plug 1 (entity: `wled_3dprinter`) | `tp_link_power_strip_ab64_wled_3dprinter_*` |
| Front Camera | Plug 6 (entity: `3d_printer_camera`) | `tp_link_power_strip_ab64_3d_printer_camera_*` |
| Filament Dryer | Plug 3 (entity: `3d_printer`) | `tp_link_power_strip_ab64_3d_printer_*` |
| AMS Heater | Plug 5 (entity: `plug_5`) | `tp_link_power_strip_ab64_plug_5_*` |
| Plug 2 (vacant) | Plug 2 (entity: `filament_dryer`) | `tp_link_power_strip_ab64_filament_dryer_*` |

> **Note:** The TP-Link integration entity IDs do not match the physical plug labels or device names due to historical renaming. The mapping above reflects the current confirmed assignment.

## Key Entities

### Aggregate (whole strip)

| Metric | Entity ID | Unit |
|---|---|---|
| Current power | `sensor.tp_link_power_strip_ab64_current_consumption` | W |
| Today's energy | `sensor.tp_link_power_strip_ab64_today_s_consumption` | kWh |
| This month's energy | `sensor.tp_link_power_strip_ab64_this_month_s_consumption` | kWh |
| Lifetime energy | `sensor.tp_link_power_strip_ab64_total_consumption` | kWh |
| Voltage | `sensor.tp_link_power_strip_ab64_voltage` | V |
| Current (amps) | `sensor.tp_link_power_strip_ab64_current` | A |

### Per-Device (pattern: `sensor.tp_link_power_strip_ab64_{plug}_*`)

Each plug exposes these sensor suffixes:

| Suffix | Meaning | Unit |
|---|---|---|
| `_current_consumption` | Live power draw | W |
| `_today_s_consumption` | Energy used today | kWh |
| `_this_month_s_consumption` | Energy used this month | kWh |
| `_total_consumption` | Lifetime energy | kWh |
| `_voltage` | Voltage | V |
| `_current` | Current draw | A |

## Dashboard Card

**File:** `homeassistant/packages/3d_printing/power_monitoring/dashboard_cards/power-usage-card.yaml`

### Main Card (inline on dashboard)

A compact `custom:button-card` showing:
- Lightning bolt icon (color-coded: green < 20W, orange 20–100W, red > 100W)
- Current aggregate watts
- Today's kWh consumption

### Popup (on tap)

Opens a `browser_mod.popup` containing:

1. **Summary chips** — current W, today kWh, month kWh, lifetime kWh
2. **Per-device breakdown** — mushroom cards for each plug showing live wattage
3. **Today's consumption table** — entities card with daily kWh per device
4. **Power history chart** — `custom:apexcharts-card` with 24h stacked area chart, 5-minute averaging
5. **Electrical detail** — voltage & current readings

## Prerequisites

| Component | Purpose |
|---|---|
| [TP-Link Kasa integration](https://www.home-assistant.io/integrations/tplink/) | Provides power strip entities |
| [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom) | Card UI components |
| [button-card](https://github.com/custom-cards/button-card) | Main compact card |
| [card-mod](https://github.com/thomasloven/lovelace-card-mod) | Card styling |
| [browser_mod](https://github.com/thomasloven/hass-browser_mod) | Popup dialogs |
| [apexcharts-card](https://github.com/RomRider/apexcharts-card) | Power history chart |

## File Structure

```
homeassistant/packages/3d_printing/power_monitoring/
└── dashboard_cards/
    └── power-usage-card.yaml    # Main card + popup definition
```

Included in the main dashboard view via:
```yaml
# view_main.yaml
- !include ../../power_monitoring/dashboard_cards/power-usage-card.yaml
```

## Future Enhancements

Per [issue #426](https://github.com/rsocko/hass-bambulab-config/issues/426):

- [ ] Per-print power tracking (estimated vs. actual)
- [ ] Power cost integration into print cost calculations
- [ ] Separate cost display for ancillary devices (LEDs, heater, etc.)
