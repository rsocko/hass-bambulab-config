# AMS Tray & External Spool Custom Popup

## Overview

Clicking any AMS tray card or the External Spool card in the 3D printing dashboard opens a rich `browser_mod.popup` dialog.  
The popup is built entirely in JavaScript at click-time — all values are live from the current HA state.

---

## Features

| Feature | Source |
|---------|--------|
| Spool name & ID | `sensor.spoolman_tray_map` → `sensor.spoolman_spool_N` |
| Filament material type | `filament_material` attribute |
| Vendor / manufacturer | `filament_vendor_name` attribute |
| Storage location | `location` attribute |
| Color swatch (auto contrast) | `tray_map.color` → filament name + entity picture + hex/RGB values (selectable); auto brightness text contrast |
| Base Color | `filament_extra_base_color` attribute (e.g. Blue, Red, White) |
| Color Family | `filament_extra_color_family` attribute (e.g. Blacks & Whites, Browns, Rainbow) |
| Filament attributes | `filament_extra_type_details` attribute (e.g. Matte, Metallic, Silk) |
| Remaining weight | `remaining_weight` attribute |
| Total weight (all spools) | Sum of `remaining_weight` across all spools sharing same `filament_id` |
| Current print usage | `sensor.ntk_ryansoffice_3dprinter_print_weight` |
| Last dried date | `extra_last_dried` attribute |
| Desiccant status + age | `extra_desiccant_filled` attribute |
| Mark as Refilled button | `spoolman.patch_spool` service call; combined row with desiccant info |
| Bambu Spool UUID | `extra_spool_uuid` attribute — shown as a centered chip card below the header when set (selectable text) |
| Spoolman web UI link | "Open in Spoolman" button in the bottom row alongside More Details & Close |
| Dynamic weight history | `history-graph` auto-scaled from `first_used` date |
| Other spools of same filament | Collapsible section listing all spools sharing the same `filament_id`; data pre-computed by `sensor.spoolman_filament_totals`; each spool is clickable to open a mini-popup with its location and remaining weight |
| More Details button | Opens HA entity info dialog |
| Close button | Closes the popup dialog (mobile-friendly) |
| Fallback (no spool) | Shows raw tray entity via `entities` card |

---

## Popup Sections

### 1. Header
- Spool friendly name
- Tray slot label + Spool ID
- Background tinted with filament color (15% opacity)
- Left border accent in filament color

### 2. UUID Chip (conditional)
Single `custom:mushroom-chips-card` with `alignment: 'center'`; only shown when `extra_spool_uuid` is set:
- **UUID** — `mdi:identifier` grey — Bambu spool UUID from `extra_spool_uuid`; text is selectable for copy-paste

### 3. Material / Vendor / Location (chips row, centered)
Single `custom:mushroom-chips-card` with `alignment: 'center'` and three compact template chips:
- **Material** — `mdi:texture-box` orange — filament type (PLA, PETG, ABS…)
- **Vendor** — `mdi:factory` purple — brand name
- **Location** — `mdi:map-marker` blue — spool storage location

### 4. Color Family / Primary Color / Attributes (chips row, centered)
Single `custom:mushroom-chips-card` with `alignment: 'center'` and three compact template chips:
- **Color Family** — `mdi:palette-swatch-variant` indigo — color group (e.g. Color Family: Blacks & Whites) from `filament_extra_color_family`
- **Primary Color** — `mdi:circle` in the filament color — human-readable color name (e.g. Primary Color: Blue) from `filament_extra_base_color`
- **Attributes** — `mdi:tag-multiple` green — filament finish/type tags (e.g. Matte, Metallic, Silk) from `filament_extra_type_details`; JSON array is parsed to comma-separated values; shows `N/A` when not set

### 5. Color Swatch (full-width, single row)
`custom:button-card` spanning full popup width with icon on the left and text towards the right:
- **Left**: Spool entity picture (40×40px, circular) with contrasting circular border — falls back to entity icon if no entity picture is set
- **Right top**: actual filament name from Spoolman (`filament_name` attribute, falls back to material type)
- **Right bottom**: hex color code • RGB values (text is selectable for copy-paste)
- Background is the filament color with auto-contrast text (NTSC luminance)

### 6. Remaining / This Print / Total Weight (horizontal)
Three items in one `horizontal-stack`:
- **Remaining** — `mdi:weight-gram` teal — current remaining grams for this spool
- **This Print** — grams required by current print job; color-coded to match dashboard: 🟢 green (sufficient, ≥ 20% buffer) → 🟡 yellow (within 20% buffer) → 🟠 orange (within 10% buffer) → 🔴 red with `mdi:printer-3d-nozzle-alert` icon (will run out)
- **Total (all spools)** — `mdi:layers-triple` cyan — total remaining weight across all spools sharing the same `filament_id` in Spoolman, with spool count (e.g. `1052.4 g (4 spools)`)

### 7. Last Dried / Desiccant / Mark as Refilled (horizontal)
Three items in one `horizontal-stack`:
- **Last Dried** — `mdi:thermometer-lines` deep-orange — date when spool was last dried from `extra_last_dried`; shows `Never` if not set
- **Desiccant** — `mdi:water` / `mdi:water-off` color-coded — desiccant age text (e.g. "18 days ago"); mushroom-template-card with named color from status
- **Mark as Refilled** — `custom:button-card` (`mdi:water-plus`) — calls `spoolman.patch_spool` with `extra.desiccant_filled = new Date().toISOString()`; primary-color background

### 8. Weight History Chart
`history-graph` card:
- `hours_to_show` is dynamically calculated from the `first_used` attribute
- Shows full history since spool was first used (minimum 24 hours)
- Falls back to 7 days (168 hours) if `first_used` is not set
- Title: `Weight History (N days)`

### 9. Other Spools of Same Filament (conditional, collapsible)
Only shown when there are other spools in Spoolman sharing the same `filament_id` as the current spool. Positioned just above the bottom row buttons.

Data source: the `spools` list inside `sensor.spoolman_filament_totals.attributes.totals[filament_id]` — computed server-side by the template sensor, so no O(n) state iteration happens in the browser.

- **Collapsible summary**: A `markdown` card with HTML5 `<details>/<summary>` showing count and text list. Summary shows `📦 N other spool(s) of same filament`; expand to see each spool's name, location, and remaining weight.
- **Interactive spool cards**: One `custom:button-card` per other spool, showing spool name + 📍 location + remaining weight. Tapping opens a mini-popup for that spool with:
  - Name header (`mdi:package-variant`)
  - Location and remaining weight chips
  - **More Details** button — opens HA entity info dialog for that spool
  - **Close** button — dismisses the mini-popup

### 10. Bottom Row — More Details, Open in Spoolman, Reload & Close
`custom:layout-card` with `grid-template-columns: 1fr 1fr 1fr 1fr` containing four `custom:button-card` buttons side-by-side:
- **More Details** — triggers `action: more-info` for `sensor.spoolman_spool_{id}`; `mdi:information-outline` icon; `var(--primary-color)` background
- **Open in Spoolman** — opens `http://spoolman.example.com/spool/show/{id}` in a new tab; Spoolman icon (dashboardicons.com via jsDelivr CDN); `var(--primary-color)` background
- **Reload from Spoolman** — calls `homeassistant.update_entity` on `sensor.spoolman_spool_{id}` to force a fresh pull of spool data from Spoolman; `mdi:refresh` icon; `var(--primary-color)` background
- **Close** — fires `browser_mod.close_popup` to dismiss the dialog; `mdi:close-circle-outline` icon; `var(--primary-color)` background; useful on mobile where the standard dismiss gesture may not be available

---

## Fallback Popup (No Spool Matched)

When the tray has filament but no Spoolman spool could be matched:

- Header shows: `{tray label} — No Spool` with grey `mdi:help-rhombus` icon
- Displays the match failure reason (e.g. "No unsealed spool with color #FF5733")
- Shows raw tray entity data via `entities` card

---

## Implementation Details

### Popup Trigger

Each tray detail card uses a `tap_action` JavaScript expression (`[[[ ]]]`) that:
1. Reads `sensor.spoolman_tray_map` to resolve the spool ID
2. Reads the spool entity attributes for details
3. Computes color, history duration, desiccant status in JS
4. Returns a `fire-dom-event` action triggering `browser_mod.popup`

### JavaScript Structure

```javascript
// --- Constants per-tray (only these 4 change between trays) ---
const tray          = 'ams_1_tray_1';
const trayLabel     = 'AMS 1 · Slot 1';
const trayEntityId  = 'sensor.p1s_01p00c460102350_ams_1_tray_1';
const printWeightKey = 'AMS 1 Tray 1';

// --- Shared logic ---
// 1. Read tray map & spool entity
// 2. Compute color (hex, RGB, textColor, bgRgba)
// 3. Compute history duration from first_used
// 4. Compute desiccant age text + color
// 5. Compute print weight status / icon
// 6. Read other spools from sensor.spoolman_filament_totals (pre-computed, no O(n) state iteration)

// --- Return popup action ---
return {
  action: 'fire-dom-event',
  browser_mod: {
    service: 'browser_mod.popup',
    data: {
      title: spoolName,
      size: 'wide',
      content: { type: 'vertical-stack', cards: [ ... ] }
    }
  }
};
```

### Desiccant Reset Service Call

The **Mark as Refilled** button (`mdi:water-plus`) uses a static `call-service` tap_action. The ISO timestamp (`nowISO`) is
computed when the popup opens — this is sufficient since desiccant tracking precision is at the day level,
and users typically click Reset within seconds of opening the popup.

```javascript
// nowISO is set when popup opens
const nowISO = new Date().toISOString();

// Reset button tap_action (static object, no nested [[[ ]]])
{
  action: 'call-service',
  service: 'spoolman.patch_spool',
  service_data: {
    id: spoolIdInt,
    extra: { desiccant_filled: nowISO }
  }
}
```

### Dynamic History Duration

```javascript
let historyHours = 168;                   // default: 7 days
let historyLabel  = '7 days';

if (firstUsed) {
  const days = Math.max(1, Math.floor(
    (Date.now() - new Date(firstUsed)) / 86400000
  ));
  historyHours = days * 24;
  historyLabel = days + (days === 1 ? ' day' : ' days');
}
```

### Color Contrast Algorithm

```javascript
// NTSC luminance formula
const luminance = (r * 299 + g * 587 + b * 114) / 1000;
const textColor  = luminance > 128 ? '#000000' : '#ffffff';
const borderColor = luminance > 128 ? '#333333' : '#ffffff';
```

### Filament Name

The color swatch top line uses `filament_name` from the Spoolman entity attributes (the actual product name, e.g. "PLA Basic"), falling back to `filament_material` (e.g. "PLA") if not set:

```javascript
const filamentName = spoolEntity?.attributes?.filament_name || material;
```

### Swatch Icon

The swatch uses `entity: spoolEntityId` in `custom:button-card` so the card automatically resolves and displays the Spoolman entity's icon. The icon is styled with a circular contrasting background (20% opacity black/white based on luminance) and a matching border.

---

## Tray Configuration Reference

| Tray Key | Display Label | Print Weight Key |
|----------|---------------|------------------|
| `ams_1_tray_1` | AMS 1 · Slot 1 | `AMS 1 Tray 1` |
| `ams_1_tray_2` | AMS 1 · Slot 2 | `AMS 1 Tray 2` |
| `ams_1_tray_3` | AMS 1 · Slot 3 | `AMS 1 Tray 3` |
| `ams_1_tray_4` | AMS 1 · Slot 4 | `AMS 1 Tray 4` |
| `ams_2_tray_1` | AMS 2 · Slot 1 | `AMS 2 Tray 1` |
| `ams_2_tray_2` | AMS 2 · Slot 2 | `AMS 2 Tray 2` |
| `ams_2_tray_3` | AMS 2 · Slot 3 | `AMS 2 Tray 3` |
| `ams_2_tray_4` | AMS 2 · Slot 4 | `AMS 2 Tray 4` |
| `external_spool` | External Spool | `External` |

---

## Reusing on Other Dashboards

The popup is self-contained in each card's `tap_action`.  
To reuse on another dashboard or view:

1. Copy the full `tap_action` string from one of the tray `custom:button-card` entries in [homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing](../../../homeassistant/packages/3d_printing/common/dashboards/3d_printing.yaml)
2. Paste it as the `tap_action` of any `custom:button-card` on the target dashboard
3. Update the four constants at the top:
   ```javascript
   const tray          = '...';   // tray key matching spoolman_tray_map
   const trayLabel     = '...';   // human-readable slot name
   const trayEntityId  = '...';   // raw tray sensor entity_id
   const printWeightKey = '...';  // attribute key in print_weight sensor
   ```

**Dependencies:**
- `browser_mod` (HACS integration, registered in browser)
- `sensor.spoolman_tray_map` template sensor (from [homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml](../../../homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml))
- `sensor.spoolman_spool_*` entities (Spoolman HA integration)
- Bambu Lab HA integration tray sensors

---

## Customization

### Spoolman URL

Find and replace in the tap_action JS:
```javascript
// Current (default)
'http://homeassistant.local:7912/spools/' + spoolId

// By IP
'http://192.168.1.100:7912/spools/' + spoolId

// External / HTTPS
'https://spoolman.yourdomain.com/spools/' + spoolId
```

### Default History Duration (when no first_used date)

```javascript
let historyHours = 168;   // change to 336 (14 days), 720 (30 days), etc.
```

---

## Requirements

| Requirement | Notes |
|------------|-------|
| browser_mod | HACS integration; must be registered in the browser visiting the dashboard |
| Spoolman HA integration | Provides `sensor.spoolman_spool_*` entities |
| Bambu Lab HA integration | Provides tray sensors |
| custom:mushroom-cards | HACS frontend card |
| custom:button-card | HACS frontend card |

---

## Future Enhancements

| Enhancement | Notes |
|------------|-------|
| ~~Location dropdown~~ | **Implemented** — uses native `select.spoolman_spool_{id}_location` entity from Spoolman integration v1.1 |
| Total inventory | Sum weight across all spools of same material type |
| Quality/age warnings | Alert when `first_used` > configurable age threshold |
| Custom notes | Display/edit `extra.notes` field per spool |
| Print estimate bar | Visual gauge of remaining vs required for current print |

---

## Related Files

| File | Purpose |
|------|---------|
| [homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing](../../../homeassistant/packages/3d_printing/common/dashboards/3d_printing.yaml) | Main dashboard — contains the popup tap_action JS |
| [homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml](../../../homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml) | `spoolman_tray_map` sensor template |
| [ams-tray-popup-visual.md](ams-tray-popup-visual.md) | Visual mockup and layout guide |
| [homeassistant/packages/3d_printing/spoolman_sync/](../../../homeassistant/packages/3d_printing/spoolman_sync/) | Spoolman sync automations |






