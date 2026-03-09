# AMS Tray & External Spool Popup — Visual Guide

## Overview

Clicking any AMS tray card or the External Spool card opens a rich `browser_mod.popup` dialog.  
The popup is built dynamically in JavaScript at click-time, so all values (color, weight, material, etc.) are live.

---

## Popup Layout (Spool Matched)

```
╔══════════════════════════════════════════════════════════╗
║  🧵  Bambu Lab PLA Basic Black                          ║  ← spool name
║      AMS 1 · Slot 1  •  Spool #42                      ║  ← location + spool ID
║      UUID: a1b2c3d4-e5f6-...  (selectable)             ║  ← UUID in header (when set)
║  ┄ ┄ ┄ ┄ ┄ ┄ left border = filament color ┄ ┄ ┄ ┄ ┄ ┄  ║  ← color-tinted background
╠══════════════════════════════════════════════════════════╣
║  [🧱 Material: PLA] [🏭 Vendor: Bambu] [📍 Location: B] ║  ← compact mushroom chips
╠══════════════════════════════════════════════════════════╣
║  [⚫ Base: Black] [🎨 Family: B&W] [🏷️ Type: Matte]     ║  ← compact mushroom chips
╠══════════════════════════════════════════════════════════╣
║  ╔═══════════════╦═══════════════╦═══════════════╗      ║
║  ║               ║  ⚖️  248.3 g  ║  🖨️  12.5 g   ║      ║  ← Color swatch / Remaining / Print
║  ║  ██  #1A1A1A ║   Remaining  ║   This Print  ║      ║
║  ║  (filament   ║              ║  (green/red)  ║      ║
║  ║   color bg)  ║              ║              ║      ║
║  ╚═══════════════╩═══════════════╩═══════════════╝      ║
╠══════════════════════════════════════════════════════════╣
║  ╔══════════╦══════════╦═══════════╦══════════════╗     ║
║  ║ 📦 1052g ║ 🌡️ Dec12 ║ 💧 18 days║ [💧Refilled] ║     ║  ← Total / LastDried / Desiccant / Button
║  ║ (4 spools)║  Dried  ║ Desiccant ║              ║     ║    all in one row
║  ╚══════════╩══════════╩═══════════╩══════════════╝     ║
╠══════════════════════════════════════════════════════════╣
║  Weight History (14 days)                               ║
║  300g ┤                                                 ║
║  250g ┤─────╮                                           ║
║  200g ┤     ╰─────╮                                     ║
║  150g ┤           ╰────────                             ║  ← Dynamic history chart
║       └──────────────────────────────                   ║    duration = days since first_used
║       Day 1      Day 7       Day 14                     ║
╠══════════════════════════════════════════════════════════╣
║  ┌──────────────────────────────────────────────────┐   ║
║  │ ℹ️ More Details │ 🔵 Open in Spoolman │ ✕ Close  │   ║  ← 3-button bottom row
║  └──────────────────────────────────────────────────┘   ║
╚══════════════════════════════════════════════════════════╝
```

---

## Section Details

### Row 1 — Header
| Element | Description |
|---------|-------------|
| Icon | `mdi:spool` colored to match filament |
| Primary | Spool friendly name from Spoolman |
| Secondary | Tray slot label + Spool ID; **UUID line** appended when `extra_spool_uuid` is set (text is selectable) |
| Background | Filament color at 15% opacity with left border accent |

### Row 2 — Material / Vendor / Location
Single `custom:mushroom-chips-card` with three compact template chips:
| Chip | Icon | Color | Content |
|------|------|-------|---------|
| Material | `mdi:texture-box` | Orange | `Material: <type>` |
| Vendor | `mdi:factory` | Purple | `Vendor: <name>` |
| Location | `mdi:map-marker` | Blue | `Location: <place>` |

### Row 3 — Base Color / Color Family / Attributes
Single `custom:mushroom-chips-card` with three compact template chips:
| Chip | Icon | Color | Content |
|------|------|-------|---------|
| Base Color | `mdi:circle` | Filament color | `Base: <name>` from `filament_extra_base_color` |
| Color Family | `mdi:palette-swatch-variant` | Indigo | `Family: <group>` from `filament_extra_color_family` |
| Attributes | `mdi:tag-multiple` | Green | `Type: <tag1>, <tag2>` from `filament_extra_type_details` (JSON array parsed to CSV); `N/A` if not set |

### Row 4 — Color Swatch / Weight / Print Usage
| Card | Description |
|------|-------------|
| Color Swatch | Full background of filament color hex; text auto-adjusts to black/white for contrast |
| Remaining | Current remaining weight in grams for this spool from Spoolman |
| This Print | Weight required for current print job (from `sensor.ntk_ryansoffice_3dprinter_print_weight`); icon turns red with alert if spool won't have enough |

### Row 5 — Total Weight / Last Dried / Desiccant / Mark as Refilled
Four items in one `horizontal-stack`:
| Item | Icon | Color | Value |
|------|------|-------|-------|
| Total (all spools) | `mdi:layers-triple` | Cyan | Sum of weights for same `filament_id`, with spool count |
| Last Dried | `mdi:thermometer-lines` | Deep Orange | Date from `extra_last_dried`; shows `Never` if not set |
| Desiccant | `mdi:water` / `mdi:water-off` | Status color | Age text (e.g. "18 days ago"); `mushroom-template-card` |
| Mark as Refilled | `mdi:water-plus` | Primary | `custom:button-card` calling `spoolman.patch_spool` |

Desiccant icon color: 🟢 Green (fresh) → 🟡 Yellow → 🟠 Orange → 🔴 Red (old)

### Row 6 — Weight History Chart
- Uses Home Assistant's built-in `history-graph` card
- Duration is **dynamic**: if `first_used` attribute exists, shows full history since that date; otherwise defaults to 7 days
- Title shows: `Weight History (N days)`

### Row 7 — Bottom Row (More Details / Open in Spoolman / Close)
Three `custom:button-card` buttons in a `custom:layout-card` with `grid-template-columns: 1fr 1fr 1fr`:
- **More Details** — opens HA entity info dialog for `sensor.spoolman_spool_<id>`
- **Open in Spoolman** — opens `{SPOOLMAN_BASE_URL}/{id}` in a new tab; Spoolman icon from dashboardicons.com
- **Close** — fires `browser_mod.close_popup` to dismiss the dialog

---

## Fallback Popup (No Spool Matched)

When the tray has filament but no Spoolman spool could be matched:

```
╔══════════════════════════════════════════════════════════╗
║  ❓  AMS 1 · Slot 2 — No Spool                          ║
║      No unsealed spool with color #FF5733               ║
╠══════════════════════════════════════════════════════════╣
║  Tray Details                                           ║
║  ┌──────────────────────────────────────────────────┐   ║
║  │  sensor.p1s_..._ams_1_tray_2                    │   ║  ← Raw tray entity
║  │  Color: #FF5733                                  │   ║
║  │  UUID:  a1b2c3d4...                              │   ║
║  │  Type:  PLA                                      │   ║
║  └──────────────────────────────────────────────────┘   ║
╚══════════════════════════════════════════════════════════╝
```

---

## Color Swatch Examples

### Dark Filament → White Text
```
╔══════════════╗
║              ║
║  #1A1A1A     ║  ← white text on near-black background
║              ║
╚══════════════╝
```

### Light Filament → Black Text
```
╔══════════════╗
║              ║
║  #FFFFFF     ║  ← black text on white background
║              ║
╚══════════════╝
```

Brightness formula (NTSC luminance):
```javascript
(r * 299 + g * 587 + b * 114) / 1000 > 128  →  black text
                                           ≤ 128  →  white text
```

---

## Desiccant Status Color Guide

| Age | Icon | Color | Hex |
|-----|------|-------|-----|
| < 30 days | 💧 | Green | `#4caf50` |
| 30–45 days | 💧 | Yellow | `#ffcc00` |
| 45–60 days | 💧 | Orange | `#ff9900` |
| > 60 days  | 💧 | Red | `#cc0000` |
| No data / empty | 💧 | Grey | `#9e9e9e` |

---

## Print Weight Indicator States

| State | Icon | Color | Meaning |
|-------|------|-------|---------|
| Not printing | `mdi:printer-3d-nozzle` | Grey | No active print |
| Sufficient | `mdi:printer-3d-nozzle` | Green | Remaining ≥ print required × 1.2 |
| Approaching | `mdi:printer-3d-nozzle` | Yellow | Remaining < print required × 1.2 (within 20% buffer) |
| Close | `mdi:printer-3d-nozzle` | Orange | Remaining < print required × 1.1 (within 10% buffer) |
| Not enough | `mdi:printer-3d-nozzle-alert` | Red | Remaining < print required — will run out |

---

## Customization Reference

### Change Spoolman URL

In the JavaScript tap_action for each card, find and update:
```javascript
tap_action: { action: 'url', url_path: 'http://homeassistant.local:7912/spools/' + spoolId }
```

Common alternatives:
```javascript
'http://192.168.1.100:7912/spools/' + spoolId       // by IP
'https://spoolman.yourdomain.com/spools/' + spoolId  // external
```

### Change Default History Duration

Modify the fallback `historyHours` value (default: `168` = 7 days):
```javascript
let historyHours = 720;  // 30 days default when no first_used
```

### Adjust Color Contrast Threshold

Modify the brightness comparison (default: `128`):
```javascript
// Current
(r * 299 + g * 587 + b * 114) / 1000 > 128 ? '#000000' : '#ffffff'

// More black text (raise threshold)
> 150 ? '#000000' : '#ffffff'

// More white text (lower threshold)
> 100 ? '#000000' : '#ffffff'
```

---

## Reusing the Popup on Other Dashboards

The popup logic lives entirely within each tray card's `tap_action` JavaScript expression.
To reuse it on another dashboard:

1. Copy the `tap_action` JavaScript string from any tray's `custom:button-card` in [homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing](../../../../homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing)
2. Change the four constants at the top of the function:
   ```javascript
   const tray = 'ams_1_tray_1';          // tray key in spoolman_tray_map
   const trayLabel = 'AMS 1 · Slot 1';   // display label
   const trayEntityId = 'sensor.p1s_01p00c460102350_ams_1_tray_1';  // raw tray entity
   const printWeightKey = 'AMS 1 Tray 1'; // attribute key in print_weight sensor
   ```
3. Paste as the `tap_action` value in any `custom:button-card` on the target dashboard

**Requirements for the popup to work on any dashboard:**
- `browser_mod` HACS integration installed and registered
- `sensor.spoolman_tray_map` template sensor loaded (from [homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml](../../../../homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml))
- `sensor.spoolman_spool_*` entities from the Spoolman integration
- The tray/external spool sensors from the Bambu Lab HA integration

---

## Future Enhancement Ideas

The popup JavaScript is modular and easy to extend. Potential additions:

| Feature | Implementation Notes |
|---------|---------------------|
| Location change dropdown | `input_select` calling `spoolman.patch_spool` with new location |
| Related spools list | Iterate `sensor.spoolman_spool_*` filtering by material/color match |
| Spool age / quality warning | Compare `first_used` to today; warn if > 12 months |
| Notes / ratings per spool | Use Spoolman `extra` fields; display in popup |
| Print estimation comparison | Cross-check `remaining_weight` vs `print_weight` with visual bar |

---

For full implementation details, see [ams-tray-popup.md](ams-tray-popup.md)




