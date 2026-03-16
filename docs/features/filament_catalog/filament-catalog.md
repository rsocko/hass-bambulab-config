# Filament Catalog — Design Document

> **Status**: Phase 1 complete, Phase 2 complete
> **Last updated**: 2026-03-16

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
| **Stock threshold** | Configurable `input_number.filament_catalog_stock_threshold`, default 150g | ~15% of a 1kg spool; adjustable from the UI. Originally called "repurchase threshold" — consolidated with the Low Stock toggle filter in Phase 2. |
| **Desiccant thresholds** | Reuse `spoolman_tray_map` logic exactly | Consistent throughout: green (<45d), yellow (45-60d), orange (60-75d), red (>75d) |
| **Default mobile view** | Location-grouped | Mirrors physical layout; no strong mobile-specific need yet |
| **Card density** | Compact default (Phase 1); density toggle is a future phase | 165 spools demands compact; medium/spacious as future option |
| **Cost info** | Include where appropriate | `price` is populated on spools; inventory value summary is viable |
| **Archived spools** | Excluded by default | `archived: false` filter; 165 count is active spools only |
| **Filter dropdown options** | Dynamically populated from spoolman entities | Avoids stale hardcoded lists; `sync_filter_options` automation runs on HA start (2-min delay), spoolman changes, and every 6h. Supports manual trigger. |
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
│   ├── automations/
│   │   └── sync_filter_options.yaml          ← Dynamically populates filter dropdowns from spoolman data
│   ├── helpers/
│   │   ├── input_boolean/                    ← Toggle filters (low stock, desiccant old)
│   │   ├── input_number/                     ← Stock threshold
│   │   ├── input_select/                     ← Dropdown filters (material, vendor, color, etc.)
│   │   └── input_text/                       ← Free-text search
│   ├── scripts/
│   │   └── filament_catalog_clear_filters.yaml  ← Reset all filters to defaults
│   ├── template_sensors/
│   │   ├── template_sensor_filament_catalog_filter.yaml  ← Server-side filtered spool list
│   │   └── filament_catalog_alerts.yaml      ← Alert computations (Phase 5 — not yet created)
│   ├── dashboard_cards/
│   │   ├── catalog_filter_bar.yaml           ← Filter bar with dropdowns, toggles, search (Phase 2)
│   │   └── catalog_inventory_kpi.yaml        ← Inventory KPI summary chips
│   └── dashboard_views/
│       └── view_filament_catalog.yaml        ← The main catalog view
├── common/
│   ├── dashboards/
│   │   └── 3d_printing.yaml                  ← Updated to !include from filament_catalog/
│   └── dashboard_cards/
│       └── card_templates/
│           ├── catalog_spool_card.yaml        ← Compact spool card (button-card template)
│           ├── catalog_spool_popup.yaml       ← Lightweight popup trigger (~110 lines)
│           ├── catalog_spool_popup_content.yaml ← Heavy popup display (~221 lines, on-demand)
│           ├── catalog_location_header.yaml   ← Location section header (available for Phase 4)
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
3. **`common/dashboard_cards/card_templates/`** — Both shared `ams_*` templates and catalog-specific templates (`catalog_spool_card`, `catalog_spool_popup`, `catalog_spool_popup_content`, `catalog_location_header`) live here, registered via the `button_card_templates` merge in the dashboard YAML.

### Migration Path

- Phase 1: Create `filament_catalog/` with `dashboard_cards/` and `dashboard_views/` (dashboard-only, no loader needed yet) — **DONE**
- Phase 2: Add `helpers/`, `template_sensors/`, `automations/`, and `filament_catalog_loader.yaml` — **DONE**

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

### Performance Constraints (Discovered in Phase 1)

Phase 1 implementation revealed critical performance constraints at 165 spools / 21 locations. These constraints **must** inform all future phases.

#### Hard Rule: ONE `auto-entities` Instance Per View

Each `auto-entities` instance subscribes to ALL Home Assistant entity state changes and re-evaluates its regex filters on every update. At 165 spools with ~500+ total HA entities:

- **21 auto-entities** (one per location grid): Completely blocked the browser main thread. View navigation broke — clicking other view tabs did nothing (icon changed but content never swapped). This persisted across ALL view types tested (`panel: true`, `custom:vertical-layout`, `type: sections`).
- **42 auto-entities** (21 headers + 21 grids): Even worse — same navigation failure plus visibly slow rendering.
- **1 auto-entities**: Navigation works instantly. Load time ~0.5s.

The view type was irrelevant — the issue was purely the number of `auto-entities` instances.

#### What Was Tried and Failed

| Approach | Result | Why It Failed |
|---|---|---|
| 42 `auto-entities` (original: 21 header + 21 grid) | View navigation completely broken | 42 independent state subscriptions saturated main thread |
| 21 `auto-entities` (headers converted to static cards) | View navigation still broken | 21 instances still too many |
| `type: custom:vertical-layout` (layout-card as view type) | Navigation broken | View type was not the cause |
| `panel: true` + `vertical-stack` wrapper | Spools didn't render (empty view) | `vertical-stack` incompatible with `auto-entities` child rendering |
| `panel: true` + `custom:layout-card` (vertical-layout) wrapper | Spools rendered but navigation still broken | Still had 21 auto-entities inside |
| `type: sections` + `max_columns: 1` | Navigation still broken with 21 auto-entities | View type was never the issue |
| 1 `auto-entities` + `type: sections` | Navigation worked but cards not full width | `sections` view adds its own padding/margins |
| **1 `auto-entities` + `panel: true` + `vertical-stack`** | **Everything works** | Single auto-entities + panel full-width = correct solution |

#### What Worked

| Fix | Impact |
|---|---|
| Reducing to 1 `auto-entities` instance | **Fixed view switching** — the critical blocker |
| `panel: true` with `vertical-stack` | Full-width card rendering |
| `triggers_update: sensor.spoolman_filament_totals` on KPI/header cards | Prevents re-render on unrelated entity changes |
| Removing `triggers_update: all` from spool cards | Prevents every card re-rendering on every state change |
| Capping apex chart to 30 days + disabling animations | Popup chart loads in ~2s instead of 10+ |
| Splitting popup into lightweight trigger (110 lines) + heavy content template (221 lines) | Popup JS only runs when opened, not on card render |
| Dynamic `statsPeriod` (hour ≤7d, day >7d) | Reduces chart data points |

#### Implications for Future Phases

1. **Phase 2 (Filters)**: Cannot use multiple `auto-entities` for filtered sub-views. Must use a single `auto-entities` with a template sensor controlling the entity list, or use `auto-entities` `filter.template` with JS.
2. **Phase 4 (Tabbed Views)**: Each tab's grouped view (By Material, By Vendor, etc.) must use ONE auto-entities with `sort` — cannot use per-group auto-entities. Location grouping headers must be rendered differently (e.g., card-level JS that inserts visual separators, or a single `button-card` template that conditionally shows a header when location changes).
3. **Phase 3 (Density Toggle)**: Safe — only changes card template CSS, no auto-entities impact.
4. **Phase 5 (Alerts)**: Alert badges on cards are safe (template JS). Alert summary card should use `triggers_update` to avoid re-render storms.
5. **General**: Any card using `Object.values(states).filter()` MUST have `triggers_update` set to a specific entity to prevent running on every state change.

### New Template Cards Needed

1. **`catalog_spool_card`** — Standalone compact spool card. Reads attributes directly from `sensor.spoolman_spool_{id}` (no `spoolman_tray_map` dependency).
2. **`catalog_spool_popup`** — Adapted version of `ams_tray_popup` for catalog context. Same visual structure, adds cost info, removes print-weight comparison.
3. **`catalog_location_header`** — Location section header showing name and spool count.

### Key Design Principle: Direct Entity Access

The existing `ams_tray_detail` reads spool data through the `sensor.spoolman_tray_map` intermediary. The catalog cards bypass this and read directly from `sensor.spoolman_spool_{id}` attributes, since most spools aren't in AMS trays.

### Scale Considerations (165 Spools)

| Concern | Mitigation |
|---|---|
| Render performance | Compact cards (~60px), single `auto-entities` instance for entire view |
| Scroll fatigue | Location label on each card; search/filter in Phase 2 |
| Template sensor overhead | `spoolman_filament_totals` already processes all spools; avoid duplicating heavy computation |
| `auto-entities` limit | **CRITICAL: Use ONE auto-entities instance.** Multiple instances (21+) block HA's main thread and break view navigation. See [Performance Constraints](#performance-constraints-discovered-in-phase-1). |
| `button-card` JS evaluation | Remove `triggers_update: all`; use `triggers_update: <specific_entity>` to prevent re-render storms |
| `Object.values(states)` cost | Each call iterates all HA entities (~500+). Minimize usage; pin to `triggers_update` so it runs infrequently |

---

## Phased Implementation Plan

### Phase 1: Compact Spool Grid (MVP) — IMPLEMENTED
**Status**: ✅ Complete (2026-03-15)
**Value**: Immediately useful — all 165 spools in a single responsive grid with visual identity, location labels, popup details, and inventory KPIs.

> **Important**: The original Phase 1 design called for per-location grouped sections using 42 `auto-entities` instances (21 header + 21 grid). This was **abandoned** due to catastrophic performance — see [Performance Constraints](#performance-constraints-discovered-in-phase-1). The shipped implementation uses a single flat grid.

#### Shipped View Structure
```
view_filament_catalog.yaml (panel: true + vertical-stack)
├── Inventory KPI chips (total spools, filaments, weight, avg cost per kg)
│
├── Filter Bar (Phase 2)
│   ├── Row 1: Material ▼  Vendor ▼  Color ▼  Family ▼
│   ├── Row 2: Type ▼  Location ▼  [Stock Threshold ━━━]  [Low Stock]
│   ├── Row 3: Sealed ▼  [Desiccant Old]
│   └── Row 4: 🔍 [search]  [123 Matches]  [Clear All]
│
└── Single auto-entities grid (columns: 5)
    ├── Source: sensor.filament_catalog_filtered_spools (entity_ids_json)
    ├── Fallback: all non-archived spools (if sensor unavailable)
    ├── [Card] [Card] [Card] [Card] [Card]   ← sorted by location attribute
    ├── [Card] [Card] [Card] [Card] [Card]
    └── ... (filtered spools, or all 165 when no filters active)
```

- **No location section headers** — replaced by a location label on each spool card
- **Single `auto-entities` instance** — sorts all spools by `location` attribute
- **`panel: true`** — full-width rendering
- **View switching works** — confirmed functional with this architecture

#### What Was Deferred from Original Phase 1 Design

| Planned Feature | Status | Reason |
|---|---|---|
| Per-location section headers | Deferred | Required 21+ auto-entities, broke navigation |
| Collapsible sections | Deferred | Depends on section headers |
| `group_by: attribute` on `location` | Not used | auto-entities `group_by` creates sub-instances |
| Preferred location ordering | Partial | `sort: attribute: location` gives alphabetical, not custom order |

#### Original Design (Abandoned)

The original Phase 1 design called for per-location collapsible sections with 21+ `auto-entities` instances. This was abandoned due to catastrophic performance. The per-location section headers and collapsible groups are deferred to Phase 4, which must use JS-based visual separators within a single `auto-entities` instance.

<details>
<summary>Click to expand original design (for historical reference)</summary>

```
view_filament_catalog.yaml
├── Heading: "Filament Catalog" + inventory KPI chips
│
├── Location Section: "AMS" (5) ─────────────── [collapsible, expanded by default]
│   └── auto-entities grid of compact catalog_spool_cards
│
├── Location Section: "AMS 2" (5) ──────────── [collapsible, expanded by default]
│   └── auto-entities grid
│
│  ... (19 more location sections, dynamically generated)
│
└── Location Section: "(Unknown)" ── [catch-all for new locations]
```

</details>

#### `catalog_spool_card` — Compact Design (~60px height)

```
┌─────────────────────────────────────────┐
│ ┌────┐ Silk+ Blue                782g  │  ← entity picture + filament name + weight
│ │ 🖼 │ PLA · Bambu Lab              💧  │  ← material · vendor label + desiccant
│ └────┘ ░░░░░░▓▓▓▓▓▓▓ 78%              │  ← weight bar
│ Under AMS (Top Shelf)                   │  ← location label
└─────────────────────────────────────────┘
  background: filament_color_hex at 25% opacity (gradient if multi-color)
  tap → catalog_spool_popup (browser_mod)
```

Grid layout: 4 rows × 4 columns
```
grid-template-areas:
  "i  n              remaining_weight  desiccant_icon"
  "i  l              l                 l"
  "i  weight_bar     weight_bar        weight_bar"
  "location_label    location_label    location_label  location_label"
```

Components:
- **Background**: `filament_color_hex` at 25% opacity (multi-color gradient if applicable, direction-aware: `coaxial` = vertical, `longitudinal` = horizontal)
- **Entity image** (`i`): `show_entity_picture: true` from `entity_picture` attribute (36×36px circle, colored border from `filament_color_hex`)
- **Name** (`n`): `filament_name` (falls back to `friendly_name`), 12px bold, truncated
- **Label** (`l`): `filament_material` + ` · ` + `filament_vendor_name`, 10px secondary color
- **Remaining weight**: `remaining_weight` formatted as `Xg`, 11px bold, right-aligned
- **Weight bar**: Uses pre-computed `used_percentage` — green (>50%) / yellow (>25%) / orange (>10%) / red (≤10%), 3px height
- **Desiccant indicator**: `mdi:water` icon, self-contained age calculation from `extra_desiccant_filled`. Hidden when <45 days (healthy). Color-coded: yellow (45-60d), orange (60-75d), red (>75d).
- **Location label**: `location` attribute, 11px, full-width span
- **Tap action**: Opens `catalog_spool_popup`

#### `catalog_spool_popup` Design

The popup is split into two templates for performance:
- **`catalog_spool_popup`** (~110 lines) — Lightweight trigger inherited by `catalog_spool_card`. Computes only chart config, action button data, and `fire-dom-event` tap action. Evaluated on every card render.
- **`catalog_spool_popup_content`** (~221 lines) — Heavy display template with all visual content. Rendered only on-demand when the popup opens (1 card at a time).

```
┌─────────────────────────────────────────────────────┐
│  ┌─ Color Banner ──────────────────────────────────┐│  ← catalog_spool_popup_content
│  │  Bambu Lab - Silk+ Blue                         ││
│  │  Spool #137  ·  Under AMS (Top Shelf)           ││
│  └─────────────────────────────────────────────────┘│
│                                                      │
│  [UUID chip if available]                            │
│                                                      │
│  [Material: PLA] [Vendor: Bambu Lab] [📍 Location✏]│  ← location pill has edit icon
│  [Family: Blues] [● Primary: Blue] [Type: Silk]      │
│  [✨ Multi-Color · longitudinal]                     │  ← shown only for multi-color
│                                                      │
│  ┌────┐  Silk+ Blue PLA                             │  ← entity image + filament name
│  │ 🖼 │  #4169E1 • RGB(65,105,225)                  │     + hex/RGB label (or multi-color list)
│  └────┘                                              │
│                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐    │
│  │  782.0 g │ │$0.025/g  │ │ 1,234.5 g        │    │  ← weight / cost per g / total across
│  │Remaining │ │Cost per g│ │ Total (3 spools) │    │     all spools of same filament
│  └──────────┘ └──────────┘ └──────────────────┘    │
│                                                      │
│  📦 2 other spools of same filament                 │  ← expandable <details>
│    • Silk+ Blue #2 (#138) — 📍 Closet Rack 1 456g  │     shows id, location, weight
│    • Silk+ Blue #3 (#139) — 📍 AMS 2         312g  │     clickable rows
│                                                      │
│  ┌────────────────────┐ ┌────────────────────┐      │
│  │ 🔥 Last Dried      │ │ 💧 Desiccant       │      │  ← 2-col grid
│  │ Mar 1, 2026        │ │ 12 days ago        │      │
│  └────────────────────┘ └────────────────────┘      │
│                                                      │
│  ℹ️ Purchased from: Bambu Lab on Dec 12, 2024 for $24.99│
│  🖨 Profile: Bambu PLA Matte · 220°C / 60°C       │
│                                                      │  ← end of catalog_spool_popup_content
│ ─────────────────────────────────────────────────── │
│  [🔥 Mark as Dried]  [💧 Mark Desiccant Refilled]  │  ← 2-col action row (catalog_spool_popup)
│                                                      │
│  📈 Weight History (up to 30 days)                  │  ← apexcharts-card with annotations:
│  ┌──────────────────────────────────────────┐       │     🟢 First Use  🔵 Desiccant  🟠 Last Dried
│  │  ╲              adaptive theme           │       │     hour period ≤7d, day period >7d
│  │    ╲___         ╲   (light/dark based    │       │     animations disabled for speed
│  │         ╲________╲  on filament color)   │       │
│  └──────────────────────────────────────────┘       │
│                                                      │
│  [ℹ️ More Details] [🔗 Spoolman] [🔄 Reload] [✕ Close]│  ← 4-col action row
└─────────────────────────────────────────────────────┘
```

Key design choices:
- **No "This Print" weight comparison** — catalog context has no active print concept
- **Cost per g KPI** — `price / initial_weight` (falls back to `filament_price`)
- **Filament totals KPI** — Total weight and spool count across all spools of the same `filament_id`, from `sensor.spoolman_filament_totals`
- **Purchase info pill** — `extra_purchased_from` + `extra_purchase_date` + `price`
- **Print settings pill** — `filament_extra_profile_name` + extruder/bed temps
- **Desiccant action buttons** — `spoolman.patch_spool` with `extra.last_dried` or `extra.desiccant_filled` set to `now`
- **Reload** — Calls `homeassistant.update_entity`, waits 1.5s, then closes popup
- **Open in Spoolman** — Direct link to `http://spoolman.socko.us/spool/show/{id}`
- **Adaptive chart theme** — Background and text color flip based on filament color luminance

#### Inventory KPI Summary (Top of View)

```
┌─────────────────────────────────────────────────────────────┐
│  📦 165 spools · 132 filaments · 98.2 kg remaining · Avg $22.50/kg│
└─────────────────────────────────────────────────────────────────────┘
```

Computed via JS in a `custom:button-card` that iterates all `sensor.spoolman_spool_*` entities. Shows total spools (excluding archived), unique filament count, total remaining weight, and average cost per kg across spools with known prices.

#### Files Created/Modified

| File | Action | Notes |
|---|---|---|
| `common/dashboard_cards/card_templates/catalog_spool_card.yaml` | **Created** | Compact button-card template with location label row |
| `common/dashboard_cards/card_templates/catalog_spool_popup.yaml` | **Created** | Lightweight popup trigger (110 lines) — only chart config + action buttons |
| `common/dashboard_cards/card_templates/catalog_spool_popup_content.yaml` | **Created** | Heavy popup display content (221 lines) — rendered on-demand in popup |
| `common/dashboard_cards/card_templates/catalog_location_header.yaml` | **Created** | Location section header (self-hiding). Not currently used in view but available for future phases |
| `filament_catalog/dashboard_cards/catalog_inventory_kpi.yaml` | **Created** | Top-of-view KPI summary with `triggers_update` |
| `filament_catalog/dashboard_views/view_filament_catalog.yaml` | **Created** | 48-line view: `panel: true` + `vertical-stack` + single `auto-entities` |
| `common/dashboards/3d_printing.yaml` | **Modified** | Updated `!include` path + `button_card_templates` merge |

#### Estimated Complexity: Medium-High
Adapted from existing patterns but with scale-aware design (compact cards, single auto-entities sorted by location, JS-computed KPIs).

> **Actual complexity**: High. The performance investigation consumed significant effort — multiple iterations of view type changes, auto-entities reductions, and template restructuring were required before finding the working architecture.

---

### Phase 2: Filters & Search — IMPLEMENTED
**Status**: ✅ Complete (2026-03-16)
**Value**: Find specific spools fast. Essential at 165 spools.

> **Performance constraint**: The filter implementation uses a single `auto-entities` instance. The template sensor approach filters server-side and the view's single `auto-entities` references the filtered entity list via `sensor.filament_catalog_filtered_spools`.

#### Filter Architecture: Template Sensor Approach

At 165 spools, client-side filtering via `config-template-card` is too slow. Instead, a Jinja2 template sensor (`sensor.filament_catalog_filtered_spools`) computes the filtered list server-side.

##### Helpers

| Helper | Type | Purpose |
|---|---|---|
| `input_select.filament_catalog_filter_material` | input_select | Dropdown — options populated dynamically |
| `input_select.filament_catalog_filter_vendor` | input_select | Dropdown — options populated dynamically |
| `input_select.filament_catalog_filter_color` | input_select | Dropdown — options populated dynamically |
| `input_select.filament_catalog_filter_color_family` | input_select | Dropdown — options populated dynamically |
| `input_select.filament_catalog_filter_type` | input_select | Dropdown — options populated dynamically |
| `input_select.filament_catalog_filter_location` | input_select | Dropdown — options populated dynamically |
| `input_select.filament_catalog_filter_sealed` | input_select | `All`, `Sealed`, `Unsealed` (static) |
| `input_text.filament_catalog_search` | input_text | Free-text search across name, vendor, color |
| `input_number.filament_catalog_stock_threshold` | input_number | Default 150g, min 0, max 500 |
| `input_boolean.filament_catalog_filter_low_stock` | input_boolean | Toggle: show only low-stock spools |
| `input_boolean.filament_catalog_filter_desiccant_old` | input_boolean | Toggle: show only spools with desiccant >45 days |

##### Dynamic Filter Option Sync

Filter dropdown options are **not hardcoded**. The `input_select` YAML files define only `['All']` as a startup default. Actual values are populated dynamically by the `sync_filter_options` automation.

**Automation: `filament_catalog_sync_filter_options`** (`automations/sync_filter_options.yaml`)

Triggers:
1. **HA start** — with a 2-minute delay to allow spoolman entities to fully load
2. **`sensor.spoolman_filament_totals` state change** — fires when spools are added, removed, or updated
3. **`time_pattern` every 6 hours** — safety net for any missed changes
4. **Manual trigger** — supported; safely skips the startup delay via `trigger.platform | default('')`

Behavior:
- Single pass through all non-archived `sensor.spoolman_spool_*` entities
- Collects unique values for each filter dimension (Material, Vendor, Primary Color, Color Family, Type, Location)
- Strips JSON outer quotes from `filament_extra_primary_color` and `filament_extra_color_family`
- Flattens the `filament_extra_type_details` JSON array into individual type values
- Calls `input_select.set_options` for each dropdown with `['All'] + sorted_unique_values`
- If a user's current selection no longer exists in the updated list, HA automatically resets to `All` (first option)

This approach avoids constant recomputation — the automation only runs when spoolman data actually changes, not on every template sensor evaluation.

##### Template Sensor: `sensor.filament_catalog_filtered_spools`

Jinja2 template that:
1. Iterates all `sensor.spoolman_spool_*` entities
2. Excludes `archived = true`
3. Applies each active dropdown filter (skip if `All`)
4. Applies toggle filters (low stock, desiccant old)
5. Applies text search (case-insensitive match on `friendly_name`, `filament_name`, `filament_vendor_name`, `filament_extra_primary_color`, `filament_extra_color_family`)
6. Outputs JSON list of matching entity IDs as `entity_ids_json` attribute
7. Provides `active_filter_summary` attribute listing active filter names

The view's `auto-entities` references this sensor to decide which spools to display.

##### Filter Bar Design
```
┌──────────────────────────────────────────────────────────────────┐
│ Material ▼  Vendor ▼  Color ▼  Family ▼                        │
│ Type ▼  Location ▼  [Stock Threshold ━━━]  [Low Stock]          │
│ Sealed ▼  [Desiccant Old]                                      │
│ 🔍 [___search___]              [123 Matches]  [Clear All]      │
└──────────────────────────────────────────────────────────────────┘
```

Rendered using `custom:bubble-card` with `sub_button_type: select` for dropdowns, slider for stock threshold, and toggle for boolean filters. "Clear All" calls `script.filament_catalog_clear_filters` which resets all helpers to defaults.

##### State-Based Filters (toggle chips in the filter bar)

| Filter | Logic | UI |
|---|---|---|
| **Desiccant Old** | `extra_desiccant_filled` age > 45 days | Toggle |
| **Low Stock** | `remaining_weight < stock_threshold` | Toggle |
| **Sealed State** | `extra_sealed` true/false | Dropdown (`All`/`Sealed`/`Unsealed`) |

#### Files Created/Modified

| File | Action | Notes |
|---|---|---|
| `filament_catalog/filament_catalog_loader.yaml` | **Modified** | Added `automation: !include_dir_list automations` |
| `filament_catalog/automations/sync_filter_options.yaml` | **Created** | Dynamic filter option sync automation |
| `filament_catalog/helpers/input_select/*.yaml` (6 files) | **Modified** | Replaced hardcoded options with `['All']` default |
| `filament_catalog/helpers/input_select/filament_catalog_filter_sealed.yaml` | **Unchanged** | Static options (`All`/`Sealed`/`Unsealed`) |
| `filament_catalog/helpers/input_boolean/*.yaml` (2 files) | **Created** | Low stock and desiccant old toggles |
| `filament_catalog/helpers/input_number/filament_catalog_stock_threshold.yaml` | **Created** | Configurable stock threshold |
| `filament_catalog/helpers/input_text/filament_catalog_search.yaml` | **Created** | Free-text search input |
| `filament_catalog/template_sensors/template_sensor_filament_catalog_filter.yaml` | **Created** | Server-side filtered spool list |
| `filament_catalog/dashboard_cards/catalog_filter_bar.yaml` | **Created** | Filter bar card (bubble-card) |
| `filament_catalog/scripts/filament_catalog_clear_filters.yaml` | **Created** | Reset all filters script |
| `filament_catalog/dashboard_views/view_filament_catalog.yaml` | **Modified** | Added filter bar include + template sensor-based auto-entities filter |

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
| `common/dashboard_cards/card_templates/catalog_spool_card.yaml` | **Modify** — Enhanced visuals + density modes |
| `filament_catalog/helpers/` | **Modify** — Add density helper (`input_select`) |

#### Estimated Complexity: Medium

---

### Phase 4: Tabbed Views & Sort Options
**Value**: Multiple perspectives on 165 spools.

> **Performance constraint**: Each tab view MUST use a single `auto-entities` instance. Per-group sections (e.g., per-material, per-vendor) cannot use separate `auto-entities` per group. Options:
> 1. Single `auto-entities` sorted by the relevant attribute (same as Phase 1 location sort) with location labels on cards
> 2. A template sensor per tab that outputs entity IDs in the desired group order, consumed by one `auto-entities`
> 3. A custom button-card template that inserts visual separator rows when the group attribute changes (requires JS in the card template)

#### Tab Structure
```
[ By Location | By Material | By Vendor | By Color Family | By Filament | Alerts | All ]
```

- **By Location** (default): Current Phase 1 layout — single auto-entities sorted by `location` attribute
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
| **Needs Repurchase** | Last spool of `filament_id` AND `remaining_weight` < `input_number.filament_catalog_stock_threshold` (default 150g) | Red badge |
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
| `common/dashboard_cards/card_templates/catalog_spool_card.yaml` | **Modify** — Alert badges on cards |

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

| Phase | Description | Effort | Dependency | Status |
|---|---|---|---|
| **1** | Compact spool grid + popup + KPIs | Medium-High | None | ✅ Complete |
| **2** | Filters, search, stock threshold helper | High | Phase 1 | ✅ Complete |
| **3** | Enhanced card visuals + density toggle | Medium | Phase 1 | |
| **4** | Tabbed views + sort options | Medium | Phase 1; benefits from 2 | |
| **5** | Alerts & flags | High | Phase 1; benefits from 2 | |
| **6** | Location management (quick-action → drag-drop) | Medium → High | Phase 1 | |
| **7** | Statistics & charts | Medium | Phase 1; benefits from 4 | |

**Recommended starting order**: Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7

Phases 1-2 are complete. Phase 3 (density toggle + enhanced visuals) is the next recommended step now that the core grid and filtering interaction pattern is solid.
