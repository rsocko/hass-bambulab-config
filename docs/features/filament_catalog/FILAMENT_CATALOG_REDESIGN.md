# Filament Catalog Redesign — Design Document

> **Status**: Design finalized, ready for Phase 1 implementation
> **Last updated**: 2026-03-15

## Problem Statement

The current `view_filament_catalog.yaml` renders every Spoolman spool using a `custom:auto-entities` card with a flat `entities` card type. With **165 spools across 21 locations (representing 132 unique filaments)**, this takes several seconds to render and provides no grouping, filtering, or visual identity. It's an unusable raw entity list at this scale.

## Goals

1. **Fast initial render** — Compact cards with collapsible location sections; show useful content immediately
2. **Visual identity** — Spool color swatches, entity images, weight bars (reuse AMS tray card patterns)
3. **Organized views** — Group by location, filter by material/vendor/color/type
4. **Search** — Find spools by name, color name, vendor
5. **Rich detail popups** — Reuse the existing `ams_tray_popup` browser_mod popup pattern
6. **Actionable state indicators** — Desiccant age, low stock, needs repurchase
7. **Cost visibility** — Inventory value using spool/filament price data
8. **Density control** — Compact, medium, or spacious card views (future toggle)
9. **Incremental delivery** — Each phase is independently deployable and valuable

## Design Decisions (Resolved)

| Question | Decision | Rationale |
|---|---|---|
| **Location discovery** | Dynamic with ordered preference list | 21 locations exist; new ones may be added. Preferred order defined, unknown locations sort to end. |
| **Repurchase threshold** | Configurable `input_number`, default 150g | ~15% of a 1kg spool; adjustable from the UI |
| **Desiccant thresholds** | Reuse `spoolman_tray_map` logic exactly | Consistent throughout: green (<45d), yellow (45-60d), orange (60-75d), red (>75d) |
| **Default mobile view** | Location-grouped | Mirrors physical layout; no strong mobile-specific need yet |
| **Card density** | Compact default (Phase 1); density toggle is a future phase | 165 spools demands compact; medium/spacious as future option |
| **Cost info** | Include where appropriate | `price` is populated on spools; inventory value summary is viable |
| **Archived spools** | Excluded by default | `archived: false` filter; 165 count is active spools only |
| **Feature placement** | New `filament_catalog/` feature package | See [Feature Structure](#feature-structure) below |

---

## Feature Structure

### Why a Separate `filament_catalog/` Package

The filament catalog has outgrown `common/`. It needs:
- **Helpers**: `input_select` filter helpers, `input_text` search, `input_number` repurchase threshold
- **Template sensors**: Filtered spool list, alert computations, catalog metadata
- **Dashboard cards**: `catalog_spool_card`, `catalog_spool_popup`, `catalog_location_header`, filter bar
- **Dashboard view**: The view YAML itself
- **A loader**: To register helpers and template sensors with HA

This matches the pattern established by `filament_tag/`, `spoolman_sync/`, `air_quality/`, and other packages that own their full lifecycle.

### Package Layout

```
homeassistant/packages/3d_printing/
├── filament_catalog/
│   ├── filament_catalog_loader.yaml          ← HA package loader
│   ├── helpers/
│   │   └── filament_catalog_helpers.yaml     ← input_select filters, input_text search, input_number threshold
│   ├── template_sensors/
│   │   ├── filament_catalog_filter.yaml      ← Computed filtered spool list (Phase 2)
│   │   └── filament_catalog_alerts.yaml      ← Alert computations (Phase 5)
│   ├── dashboard_cards/
│   │   ├── card_templates/
│   │   │   ├── catalog_spool_card.yaml       ← Individual spool card (button-card template)
│   │   │   ├── catalog_spool_popup.yaml      ← Spool detail popup (browser_mod)
│   │   │   └── catalog_location_header.yaml  ← Location section header
│   │   ├── catalog_filter_bar.yaml           ← Filter chip bar (Phase 2)
│   │   └── catalog_alert_summary.yaml        ← Alert summary card (Phase 5)
│   └── dashboard_views/
│       └── view_filament_catalog.yaml        ← The main catalog view
├── common/
│   ├── dashboards/
│   │   └── 3d_printing.yaml                  ← Updated to !include from filament_catalog/
│   └── dashboard_cards/
│       └── card_templates/
│           └── (ams_* templates stay here — shared by both printer view and catalog)
```

### Wiring Changes

1. **`_feature_loaders.yaml`** — Add `filament_catalog: !include filament_catalog/filament_catalog_loader.yaml`
2. **`common/dashboards/3d_printing.yaml`** — Change the catalog view include:
   ```yaml
   # Before:
   - !include ../dashboard_views/view_filament_catalog.yaml
   # After:
   - !include ../../filament_catalog/dashboard_views/view_filament_catalog.yaml
   ```
3. **`common/dashboard_cards/card_templates/`** — The shared `ams_tray_popup`, `ams_tray_detail`, etc. stay in `common/` since they're used by both the printer dashboard and (potentially) the catalog popup.
4. **`filament_catalog/dashboard_cards/card_templates/`** — New catalog-specific card templates are registered via `button_card_templates` merge in the dashboard YAML.

### Migration Path

- Phase 1: Create `filament_catalog/` with `dashboard_cards/` and `dashboard_views/` (dashboard-only, no loader needed yet)
- Phase 2: Add `helpers/`, `template_sensors/`, and `filament_catalog_loader.yaml` when filter state and search are needed

---

## Data Model Reference

### `sensor.spoolman_spool_{id}` Attributes (Complete)

| Attribute | Type | Use in Catalog |
|---|---|---|
| `id` | int | Spool identifier |
| `friendly_name` | string | Display name |
| `remaining_weight` | float | Weight bar, sort, low-stock alert |
| `initial_weight` | float | Weight bar percentage baseline |
| `used_weight` | float | Display |
| `used_percentage` | float | Pre-computed % used — use for weight bars |
| `remaining_length` | float | Display (meters of filament left) |
| `entity_picture` | string | Spool image path (e.g. `/local/spoolman_images/spool_5.png`) |
| `filament_id` | int | Group by filament type |
| `filament_material` | string | Filter: Material (PLA, PETG…) |
| `filament_vendor_name` | string | Filter: Vendor (Bambu Lab, Sunlu…) |
| `filament_vendor_external_id` | string | Vendor identifier |
| `filament_name` | string | Search target, display name |
| `filament_color_hex` | string | Color swatch background (6-char hex, no `#`) |
| `filament_multi_color_hexes` | string | Comma-separated hex values for multi-color |
| `filament_multi_color_direction` | string | `"longitudinal"` or `"coaxial"` |
| `filament_extra_primary_color` | string | Filter: Primary Color (e.g. "Gray", "Blue") — **JSON-quoted** |
| `filament_extra_color_family` | string | Filter: Color Family (e.g. "Blacks & Whites") — **JSON-quoted** |
| `filament_extra_type_details` | string/JSON | Filter: Type (e.g. `["Matte"]`, `["Silk","Metallic"]`) |
| `filament_extra_profile_name` | string | Slicer profile name — **JSON-quoted** |
| `filament_extra_tracking_status` | string/JSON | Tag tracking info (e.g. `["Tag (Vertical)","NFC - Swatch"]`) |
| `filament_extra_filamentcolorxyz_url` | string | External color swatch URL — **JSON-quoted** |
| `filament_article_number` | string | Product/article number |
| `filament_density` | float | Material density (g/cm³) |
| `filament_diameter` | float | Filament diameter (mm) |
| `filament_weight` | float | Nominal spool weight (g) |
| `filament_spool_weight` | float | Empty spool weight (g) |
| `filament_settings_extruder_temp` | int | Recommended extruder temp (°C) |
| `filament_settings_bed_temp` | int | Recommended bed temp (°C) |
| `price` | float/null | Spool-specific price |
| `filament_price` | float/null | Filament-level price |
| `location` | string | Physical location (21 known values) |
| `comment` | string | Spool notes |
| `archived` | bool | Whether spool is archived |
| `first_used` | string/null | ISO datetime of first use |
| `last_used` | string/null | ISO datetime of most recent use |
| `registered` | string | ISO datetime when spool was added |
| `extra_spool_uuid` | string | Bambu Lab RFID UUID |
| `extra_spool_type` | string | Spool type (e.g. "Bambu Spool") |
| `extra_sealed` | bool | Whether spool is still sealed/unopened |
| `extra_desiccant_in_spool` | bool/null | Whether desiccant is present |
| `extra_desiccant_filled` | string/null | ISO datetime of last desiccant refill |
| `extra_last_dried` | string/null | ISO datetime of last drying |
| `extra_clip_type` | string | Clip type (e.g. "Slot Insert v2") |
| `extra_purchased_from` | string | Purchase source |
| `extra_purchase_date` | string | ISO datetime of purchase |
| `extra_tag` | string | NFC/RFID tag identifier |

> **Note**: Several `filament_extra_*` attributes are stored as JSON-quoted strings (e.g. `"\"Gray\""` instead of `"Gray"`). Templates must strip outer quotes.

### `sensor.spoolman_filament_totals` Attributes

Pre-computed aggregate data keyed by `filament_id`:
```
totals[filament_id] = {
  weight: float,       // total remaining grams across all spools
  count: int,          // number of spools
  spools: [{id, entity_id, name, location, remaining}]
}
```

### Known Location Values (21 locations from Spoolman)

Ordered by display preference:

| Group | Locations |
|---|---|
| **Printer-adjacent** | `AMS`, `AMS 2`, `Under AMS (Top Shelf)`, `Under AMS (Bottom Shelf)` |
| **Near printer** | `Shelf Near Door`, `Laser Printer Shelf`, `Under Desk (Right Side)`, `Floor` |
| **Closet shelves** | `Closet Shelf 1 (Top)`, `Closet Shelf 2`, `Closet Shelf 3`, `Closet Shelf 4` |
| **Closet racks** | `Closet Rack 1`, `Closet Rack 2`, `Closet Rack 3`, `Closet Rack 4` |
| **Closet under-racks** | `Closet Under Rack 1`, `Closet Under Rack 2`, `Closet Under Rack 3`, `Closet Under Rack 4` |
| **Storage** | `Cereal Dry Box - Closet` |

> The view dynamically discovers all locations from spool entities. The preferred display order is defined in the view; unknown/new locations appear at the end.

### `select.spoolman_spool_{id}_location` — Location Select Entities

- `state`: Current location string
- `attributes.options`: Full list of all 21 location values (same for every spool)

Used to change spool location from the catalog popup.

---

## Architecture Decisions

### Card Technology Choices

| Need | Card | Rationale |
|---|---|---|
| Layout/grouping | `custom:auto-entities` | Dynamic entity filtering, regex matching, sorting, `group_by` |
| Individual spool rendering | `custom:button-card` | Reuse `ams_tray_detail`-style patterns: color gradient background, weight indicators, text contrast logic |
| Tabs for grouping modes | `custom:tabbed-card` | Already used in project (print weight/cost tabs) |
| Section headers | `custom:button-card` | Reuse `ams_header`-style separator pattern |
| Collapsible sections | Markdown `<details>` or `custom:fold-entity-row` | Essential for 21 location groups with up to 20+ spools each |
| Detail popup | browser_mod popup | Consistent UX with printer dashboard |
| Chips/filters | `custom:mushroom-chips-card` | Quick filter toggle indicators |
| Template logic | `custom:config-template-card` | Dynamic entity resolution |

### New Template Cards Needed

1. **`catalog_spool_card`** — Standalone compact spool card. Reads attributes directly from `sensor.spoolman_spool_{id}` (no `spoolman_tray_map` dependency).
2. **`catalog_spool_popup`** — Adapted version of `ams_tray_popup` for catalog context. Same visual structure, adds cost info, removes print-weight comparison.
3. **`catalog_location_header`** — Location section header showing name and spool count.

### Key Design Principle: Direct Entity Access

The existing `ams_tray_detail` reads spool data through the `sensor.spoolman_tray_map` intermediary. The catalog cards bypass this and read directly from `sensor.spoolman_spool_{id}` attributes, since most spools aren't in AMS trays.

### Scale Considerations (165 Spools)

| Concern | Mitigation |
|---|---|
| Render performance | Compact cards (~60px), collapsible sections (only expanded sections render cards) |
| Scroll fatigue | Collapsible location groups; search/filter in Phase 2 |
| Template sensor overhead | `spoolman_filament_totals` already processes all spools; avoid duplicating heavy computation |
| `auto-entities` limit | Split into per-location sections rather than one giant auto-entities call |

---

## Phased Implementation Plan

### Phase 1: Location-Grouped Compact Spool Grid (MVP)
**Value**: Immediately useful — organized by physical location, visual identity, compact for 165 spools, collapsible sections.

#### View Structure
```
view_filament_catalog.yaml
├── Heading: "Filament Catalog" + inventory KPI chips (total spools, total weight, total value)
│
├── Location Section: "AMS" (5) ─────────────── [collapsible, expanded by default]
│   └── auto-entities grid of compact catalog_spool_cards
│       ├── [Card] [Card] [Card] [Card] [Card]
│
├── Location Section: "AMS 2" (5) ──────────── [collapsible, expanded by default]
│   └── auto-entities grid
│
├── Location Section: "Under AMS (Top Shelf)" (6) ── [collapsible]
│   └── ...
│
├── Location Section: "Under AMS (Bottom Shelf)" (8) ── [collapsible]
│   └── ...
│
├── Location Section: "Closet Shelf 1 (Top)" ── [collapsible, collapsed by default]
│   └── ...
│
│  ... (17 more location sections, dynamically generated)
│
└── Location Section: "(Unknown)" ── [catch-all for new locations]
```

#### Collapsible Section Strategy

**Approach**: Each location is a `vertical-stack` containing:
1. A `catalog_location_header` button card (tappable to expand/collapse)
2. A `conditional` card wrapping the `auto-entities` grid, controlled by an `input_boolean` per logical group

**Simplified approach for Phase 1**: Use `auto-entities` with `group_by: attribute` on `location`, which creates automatic grouped sections. This avoids per-location `input_boolean` helpers and gives us instant location grouping. Collapsibility can be added in Phase 2/3 via `fold-entity-row` or per-section conditionals.

#### `catalog_spool_card` — Compact Design (~60px height)

```
┌─────────────────────────────────────────┐
│ ┌────┐ Bambu Lab - Silk+ Blue    782g  │  ← entity picture + name + weight
│ │ 🖼 │ PLA  ░░░░░░▓▓▓▓▓▓▓ 78%    💧  │  ← material + weight bar + desiccant
│ └────┘                                  │
└─────────────────────────────────────────┘
  background: filament_color_hex at 25% opacity (gradient if multi-color)
  tap → catalog_spool_popup (browser_mod)
```

Components:
- **Background**: `filament_color_hex` at 25% opacity (multi-color gradient if applicable) — reuses `ams_tray_detail` logic
- **Entity image**: `show_entity_picture: true` from `entity_picture` attribute (40×40px circle)
- **Name**: `friendly_name` — contrast-aware text color based on background luminance
- **Weight text**: `remaining_weight` + `g` suffix, right-aligned
- **Material**: Small text (e.g., "PLA") below name
- **Weight bar**: Uses pre-computed `used_percentage` — green/yellow/orange/red thresholds from `ams_tray_label`
- **Desiccant indicator**: Water drop icon, color-coded using `spoolman_tray_map` desiccant logic (same thresholds: <45d green, 45-60d yellow, 60-75d orange, >75d red). Only shown for non-green status.
- **Tap action**: Opens `catalog_spool_popup`

#### `catalog_spool_popup` Design

Reuses the structure and visual language of `ams_tray_popup` with catalog-specific adaptations:

```
┌─────────────────────────────────────────────────────┐
│  ┌─ Color Banner ──────────────────────────────────┐│
│  │  Bambu Lab - Silk+ Blue                         ││
│  │  AMS · Slot 1  •  Spool #137                    ││
│  └─────────────────────────────────────────────────┘│
│                                                      │
│  [UUID chip if available]                            │
│                                                      │
│  [Material: PLA] [Vendor: Bambu Lab] [📍 Location]  │  ← tap location → more-info select
│  [Family: Blues] [● Primary: Blue] [Type: Silk]      │
│                                                      │
│  ┌────┐  Silk+ Blue PLA                             │  ← entity image + filament name
│  │ 🖼 │  #4169E1 • RGB(65,105,225)                  │     + hex/RGB label
│  └────┘                                              │
│                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │  782.0 g │ │ $12.50   │ │  1.8 kg  │            │  ← weight / cost / total (all spools)
│  │Remaining │ │Value Left│ │Total Inv │            │
│  └──────────┘ └──────────┘ └──────────┘            │
│                                                      │
│  📦 2 other spools of same filament                 │  ← expandable
│    • Silk+ Blue #2 (Spool #138) — Closet Rack 1    │
│    • Silk+ Blue #3 (Spool #139) — AMS 2            │
│                                                      │
│  🔥 Last Dried: Mar 1, 2026    [Mark as Dried]     │
│  💧 Desiccant: 12 days ago     [Refill Desiccant]  │
│                                                      │
│  📈 Weight History (since first use)                │  ← apexcharts-card
│  ┌──────────────────────────────────────────┐       │
│  │  ╲                                       │       │
│  │    ╲___         ╲                        │       │
│  │         ╲________╲____                   │       │
│  └──────────────────────────────────────────┘       │
│                                                      │
│  ℹ️ Purchased from: Bambu Lab · Dec 12, 2024       │  ← purchase info
│  🖨 Profile: Bambu PLA Matte · 220°C / 60°C       │  ← print settings
│                                                      │
│  [🔗 Open in Spoolman]  [📍 Change Location]       │  ← action buttons
└─────────────────────────────────────────────────────┘
```

Key differences from `ams_tray_popup`:
- **No "This Print" weight comparison** — catalog context has no active print concept
- **Cost card added** — Shows $ value remaining = `(remaining_weight / initial_weight) * price`
- **Purchase info row** — `extra_purchased_from` + `extra_purchase_date`
- **Print settings row** — `filament_settings_extruder_temp` / `filament_settings_bed_temp` + `filament_extra_profile_name`
- **Location change button** — Prominent action to change location via `select.spoolman_spool_{id}_location`

#### Inventory KPI Summary (Top of View)

```
┌─────────────────────────────────────────────────────────────┐
│  📦 165 spools · 132 filaments · 98.2 kg remaining · $2,134│
└─────────────────────────────────────────────────────────────┘
```

Computed via JS in a `custom:button-card` that iterates all `sensor.spoolman_spool_*` entities. Shows total spools (excluding archived), unique filament count, total remaining weight, and total inventory value.

#### Files to Create/Modify

| File | Action |
|---|---|
| `filament_catalog/dashboard_cards/card_templates/catalog_spool_card.yaml` | **Create** — Compact button-card template |
| `filament_catalog/dashboard_cards/card_templates/catalog_spool_popup.yaml` | **Create** — Popup template (browser_mod) |
| `filament_catalog/dashboard_cards/card_templates/catalog_location_header.yaml` | **Create** — Location section header |
| `filament_catalog/dashboard_cards/catalog_inventory_kpi.yaml` | **Create** — Top-of-view KPI summary |
| `filament_catalog/dashboard_views/view_filament_catalog.yaml` | **Create** — New view (replaces common version) |
| `common/dashboards/3d_printing.yaml` | **Modify** — Update `!include` path + add `button_card_templates` from catalog |
| `common/dashboard_views/view_filament_catalog.yaml` | **Delete** — Replaced by `filament_catalog/` version |

#### Estimated Complexity: Medium-High
Adapted from existing patterns but with scale-aware design (compact cards, auto-entities group_by, JS-computed KPIs).

---

### Phase 2: Filters & Search
**Value**: Find specific spools fast. Essential at 165 spools.

#### Filter Architecture: Template Sensor Approach (Option B)

At 165 spools, client-side filtering via `config-template-card` is too slow. Instead, a Jinja2 template sensor computes the filtered list server-side.

##### New Helpers

| Helper | Type | Purpose |
|---|---|---|
| `input_select.filament_catalog_filter_material` | input_select | `All`, `PLA`, `PETG`, `ABS`, `TPU`, … |
| `input_select.filament_catalog_filter_vendor` | input_select | `All`, `Bambu Lab`, `Sunlu`, `ELEGOO`, … |
| `input_select.filament_catalog_filter_color` | input_select | `All`, `Blue`, `Red`, `Gray`, `White`, … |
| `input_select.filament_catalog_filter_color_family` | input_select | `All`, `Blues`, `Reds`, `Blacks & Whites`, … |
| `input_select.filament_catalog_filter_type` | input_select | `All`, `Matte`, `Silk`, `Metallic`, `Marble`, … |
| `input_text.filament_catalog_search` | input_text | Free-text search across name, vendor, color |
| `input_number.filament_catalog_repurchase_threshold` | input_number | Default 150g, min 0, max 500, step 10 |

##### Template Sensor: `sensor.filament_catalog_filtered_spools`

Jinja2 template that:
1. Iterates all `sensor.spoolman_spool_*` entities
2. Excludes `archived = true`
3. Applies each active filter (skip if `All`)
4. Applies text search (case-insensitive match on `friendly_name`, `filament_vendor_name`, `filament_extra_primary_color`)
5. Outputs JSON list of matching entity IDs

The view's `auto-entities` references this sensor to decide which spools to display.

##### Filter Bar Design
```
┌──────────────────────────────────────────────────────────────────┐
│ 🔍 [___search___]                                                │
│ Material ▼  Vendor ▼  Color ▼  Family ▼  Type ▼    [Clear All] │
└──────────────────────────────────────────────────────────────────┘
```

Each filter rendered as a `mushroom-select-card` or compact `button-card` dropdown. "Clear All" button resets all filters to `All` and clears search text.

##### State-Based Filters (toggle chips below the filter bar)

| Filter | Logic | UI |
|---|---|---|
| **Needs Repurchase** | Last spool of `filament_id` AND `remaining_weight < input_number.threshold` | Toggle chip |
| **Desiccant Old (Y/O/R)** | `extra_desiccant_filled` age > 45 days | Toggle chip |
| **Low Stock** | `remaining_weight < 100g` | Toggle chip |
| **Unsealed Only** | `extra_sealed = false` | Toggle chip |

#### Files to Create/Modify

| File | Action |
|---|---|
| `filament_catalog/filament_catalog_loader.yaml` | **Create** — HA package loader |
| `filament_catalog/helpers/filament_catalog_helpers.yaml` | **Create** — All input helpers |
| `filament_catalog/template_sensors/filament_catalog_filter.yaml` | **Create** — Server-side filtered spool list |
| `filament_catalog/dashboard_cards/catalog_filter_bar.yaml` | **Create** — Filter bar card |
| `filament_catalog/dashboard_views/view_filament_catalog.yaml` | **Modify** — Integrate filter bar above spool grid |
| `_feature_loaders.yaml` | **Modify** — Register `filament_catalog` loader |

#### Estimated Complexity: High
Server-side template sensor with multi-field filtering, new helpers, loader registration.

---

### Phase 3: Enhanced Card Visuals & Density Toggle
**Value**: Richer visual detail + user-controlled density.

#### Enhancements to `catalog_spool_card`
1. **"Low Stock" badge** — Red overlay when `remaining_weight < 100g`
2. **"Sealed" indicator** — Lock icon for `extra_sealed = true`
3. **Last used timestamp** — Subtle "Used 4d ago" text from `last_used`
4. **Multi-spool count badge** — "×3" if `spoolman_filament_totals` shows multiple spools
5. **Color-coded left border** based on desiccant status (green/yellow/orange/red)
6. **Price per gram** — Small text showing `$X.XX/g` on card

#### Density Toggle

New `input_select.filament_catalog_density` helper with options: `Compact`, `Medium`, `Spacious`.

| Density | Card Height | Content | Columns (desktop) |
|---|---|---|---|
| **Compact** | ~60px | Image + name + weight + material + bar | 5-6 |
| **Medium** | ~100px | + vendor + last used + desiccant border + badges | 4 |
| **Spacious** | ~140px | + purchase info + full weight % + cost | 3 |

The `catalog_spool_card` template reads this helper and adjusts its layout via conditional CSS/grid areas.

#### Files to Modify

| File | Action |
|---|---|
| `filament_catalog/dashboard_cards/card_templates/catalog_spool_card.yaml` | **Modify** — Enhanced visuals + density modes |
| `filament_catalog/helpers/filament_catalog_helpers.yaml` | **Modify** — Add density helper |

#### Estimated Complexity: Medium

---

### Phase 4: Tabbed Views & Sort Options
**Value**: Multiple perspectives on 165 spools.

#### Tab Structure
```
[ By Location | By Material | By Vendor | By Color Family | By Filament | Alerts | All ]
```

- **By Location** (default): Phase 1 layout with `group_by: attribute: location`
- **By Material**: Sections: PLA, PETG, ABS, TPU, etc.
- **By Vendor**: Sections: Bambu Lab, Sunlu, ELEGOO, etc.
- **By Color Family**: Sections: Blues, Reds, Greens, Blacks & Whites, Rainbow, etc.
- **By Filament**: Aggregated view from `spoolman_filament_totals` — one row per `filament_id` with expandable spool list. Collapses 165 spools → 132 rows (and many are single-spool, so effectively shorter).
- **Alerts**: Only spools needing attention (low stock, desiccant old, repurchase)
- **All**: Single flat grid with sort control

#### Sort Controls

New `input_select.filament_catalog_sort`:
- `Name (A-Z)` / `Name (Z-A)`
- `Weight (Low → High)` / `Weight (High → Low)`
- `Last Used (Recent)` / `Last Used (Oldest)`
- `Cost (High → Low)` / `Cost (Low → High)`
- `Vendor → Name`

#### Files to Create/Modify

| File | Action |
|---|---|
| `filament_catalog/dashboard_views/view_filament_catalog.yaml` | **Replace** — Full tabbed layout |
| `filament_catalog/helpers/filament_catalog_helpers.yaml` | **Modify** — Add sort helper |

#### Estimated Complexity: Medium

---

### Phase 5: Advanced Alerts & Flags (Future)
**Value**: Proactive inventory management.

#### Alert Types

| Alert | Trigger | Visual |
|---|---|---|
| **Needs Repurchase** | Last spool of `filament_id` AND `remaining_weight` < `input_number.filament_catalog_repurchase_threshold` (default 150g) | Red badge |
| **Desiccant Overdue** | `extra_desiccant_filled` age > 60 days (orange/red threshold) | Orange water drop |
| **Needs Drying** | `extra_last_dried` > 90 days (or never) AND `extra_sealed = false` | Yellow heat icon |
| **Nearly Empty** | `remaining_weight` < 50g | Warning badge |
| **Unused (Stale)** | `last_used` > 6 months ago | Gray-out card |

#### Alert Summary Card
```
┌─────────────────────────────────────────────────────────────────┐
│ ⚠️ Inventory Alerts                                             │
│ 🔴 2 repurchase  🟠 5 desiccant  🟡 3 drying  ⚠️ 1 empty      │
│                                                   [View All →] │
└─────────────────────────────────────────────────────────────────┘
```

Placed below the KPI summary card. Tapping a chip switches to the Alerts tab with that filter pre-selected.

#### Template Sensor: `sensor.filament_catalog_alerts`

Computes alert counts and entity lists for each category. Used by both the summary card and the Alerts tab.

#### Files to Create/Modify

| File | Action |
|---|---|
| `filament_catalog/template_sensors/filament_catalog_alerts.yaml` | **Create** — Alert computation |
| `filament_catalog/dashboard_cards/catalog_alert_summary.yaml` | **Create** — Alert summary card |
| `filament_catalog/dashboard_cards/card_templates/catalog_spool_card.yaml` | **Modify** — Alert badges on cards |

#### Estimated Complexity: High

---

### Phase 6: Location Management & Drag-and-Drop (Future)
**Value**: Reorganize spool locations from the HA dashboard.

#### Phased Approach

**6a. Quick-action location buttons** (in `catalog_spool_popup`):
- Already partially available via Location chip → `more-info` on `select.spoolman_spool_{id}_location`
- Add dedicated "Move to…" section with quick-action buttons for common locations (AMS, AMS 2, shelves)
- Low effort, high value

**6b. Drag-and-drop** (future custom card):
- Would require a custom Lovelace card using HTML5 DnD or Sortable.js
- Calls `select.select_option` on `select.spoolman_spool_{id}_location` on drop
- Standalone HACS custom card project — out of scope for YAML-only implementation

---

### Phase 7: Density-Aware Statistics & Charts (Future)
**Value**: Visual analytics for inventory management.

#### Features
1. **Pie chart**: Weight distribution by material / vendor / color family (`custom:apexcharts-card`)
2. **Bar chart**: Spools per location
3. **Inventory value trend**: Total $ value over time (requires historical data)
4. **Usage rate**: Weight consumed per week/month per spool
5. **Filament recommendation**: Based on what's running low, suggest what to reorder

#### Files to Create
| File | Action |
|---|---|
| `filament_catalog/dashboard_cards/catalog_statistics.yaml` | **Create** — Statistics cards |

---

## Visual Reference: Comparison to Spoolman UI

The Spoolman screenshot shows a location-grouped layout with:
- Location headers with spool count badges (5, 5, 6, 8 spools per group)
- Spool cards: ID + name, material + weight + spool size, last used timestamp
- Colored swatch circle per spool
- Drag handles (our Phase 6b)
- Edit/visibility toggles

Our Phase 1 catalog achieves the same organizational structure but scaled for 21 locations and with:
- Richer visual treatment (color gradient backgrounds vs plain white cards)
- Weight progress bars (not just text)
- Desiccant health indicators
- Tap-to-detail popup with full spool info, charts, cost, and actions
- Integration with existing AMS tray visual language for consistency
- Inventory KPI summary (total weight, value, spool count)

---

## Additional Design Ideas & Suggestions

### Based on Available Entity Data

1. **Cost tracking** — `price` attribute enables per-spool value calculation: `(remaining_weight / initial_weight) * price`. Show on popup cards and in KPI summary.

2. **Filament type breakdown** — Pie chart (via `custom:apexcharts-card`) showing weight distribution by material, vendor, or color family. Phase 7 feature.

3. **"Similar spools" in popup** — When viewing a spool, show other spools with the same `filament_extra_primary_color` as alternatives (not just same `filament_id`).

4. **Spool age timeline** — Using `first_used` and `last_used`, identify spools sitting unused for months.

5. **QR/NFC quick access** — Link from catalog cards to the filament_tag scanning view.

6. **"By Filament" aggregated tab** — Groups 165 spools → 132 filaments. Each row shows total weight across all spools of that filament, expandable to individual spools.

7. **Print compatibility check** — If a print is active, highlight catalog spools that have enough weight for the current print.

8. **FilamentColors.xyz link** — `filament_extra_filamentcolorxyz_url` enables a direct link to the color swatch in the popup.

9. **Print settings in popup** — `filament_settings_extruder_temp` and `filament_settings_bed_temp` + `filament_extra_profile_name` give users quick reference to print profiles.

10. **Tracking status badges** — `filament_extra_tracking_status` shows which tags/swatches exist for each spool.

---

## Implementation Priority Summary

| Phase | Description | Effort | Dependency |
|---|---|---|---|
| **1** | Location-grouped compact grid + popup + KPIs | Medium-High | None |
| **2** | Filters, search, repurchase threshold helper | High | Phase 1 |
| **3** | Enhanced card visuals + density toggle | Medium | Phase 1 |
| **4** | Tabbed views + sort options | Medium | Phase 1; benefits from 2 |
| **5** | Alerts & flags | High | Phase 1; benefits from 2 |
| **6** | Location management (quick-action → drag-drop) | Medium → High | Phase 1 |
| **7** | Statistics & charts | Medium | Phase 1; benefits from 4 |

**Recommended starting order**: Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7

At 165 spools, **Phase 2 (filters/search) is now the immediate follow-up to Phase 1** — scrolling through 21 location groups without filtering is not practical for daily use. Phase 3 (density toggle + enhanced visuals) can follow once the core interaction pattern is solid.
