# Filament Catalog — Design Document

> **Status**: Phase 1–4 complete (5 phases total, Phase 5 split into 5A–5E sub-phases)
> **Last updated**: 2026-03-19

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
│   │   └── filament_catalog_metrics.yaml      ← Metrics & alert computations (Phase 5)
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
4. **Phase 5 (Metrics & Insights)**: Chart cards are safe — they read from a pre-computed template sensor. All chart cards MUST use `triggers_update: sensor.filament_catalog_metrics` to avoid re-render storms. The collapsible insights panel has zero cost when hidden (conditional card).
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
│   ├── Row 1: View ▼  Sort ▼
│   ├── Row 2: Material ▼  Vendor ▼  Color ▼  Family ▼
│   ├── Row 3: Type ▼  Location ▼  [Stock Threshold ━━━]  [Low Stock]
│   ├── Row 4: Sealed ▼  [Desiccant Old]  [Large Cards]
│   └── Row 5: 🔍 [search]  [123 Matches]  [Clear Filters]
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
│  📈 Weight History (default: full history)          │  ← apexcharts-card with annotations:
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
- **History range behavior** — Chart span is controlled by `input_select.filament_catalog_history_range` (`Last 30 Days` / `Full History`). The popup no longer renders a range dropdown; default helper value is `Full History`, and it can be changed manually via HA entity tools.

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
| `input_select.filament_catalog_history_range` | input_select | Popup chart history control: `Last 30 Days` or `Full History` (default `Full History`) |
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
│ View ▼  Sort ▼                                                  │
│ Material ▼  Vendor ▼  Color ▼  Family ▼                        │
│ Type ▼  Location ▼  [Stock Threshold ━━━]  [Low Stock]          │
│ Sealed ▼  [Desiccant Old]  [Large Cards]                        │
│ 🔍 [___search___]              [123 Matches]  [Clear Filters]   │
└──────────────────────────────────────────────────────────────────┘
```

Rendered using `custom:bubble-card` with `sub_button_type: select` for dropdowns, slider for stock threshold, and toggle for boolean filters. "Clear Filters" calls `script.filament_catalog_clear_filters` which resets all helpers to defaults.

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

### Phase 3: Enhanced Card Visuals & Density Toggle ✅
**Value**: Richer visual detail + user-controlled density.
**Status**: Complete.

#### Enhancements to `catalog_spool_card`
1. **"Low Stock" badge** — Red weight text + inset red box-shadow when `remaining_weight < 100g`
2. **"Sealed" indicator** — `mdi:package-variant-closed` icon (blue) in the status icon slot when `extra_sealed = true`. When sealed, the desiccant age icon is **never** shown.
3. **Last used timestamp** — Subtle "Used Xd ago" text in bottom-right of card from `last_used`
4. **Alert-priority left border** — 3px left border color reflects the **worst** active alert across desiccant age and remaining weight:
   - **No alerts**: transparent (no decoration)
   - **Yellow** (`#FFC107`): desiccant 45–59 days old OR remaining weight 25–50%
   - **Orange** (`#FF9800`): desiccant 60–74 days old OR remaining weight 10–25%
   - **Red** (`#f44336`): desiccant ≥ 75 days old OR remaining weight ≤ 10%
   - **Light gray** (`#bdbdbd`): desiccant is present but fill date is undefined
   - **Sealed**: transparent (no decoration)
   - When multiple alert conditions exist, the most severe color wins (e.g., yellow desiccant + red weight → red border)
5. **Type details in subhead** — Label now shows `Material · Type1 · Type2 - Vendor` (dot-delimited type details parsed from `filament_extra_type_details`)
6. **Taller weight progress bar** — Increased from 3px to 5px (1.5×) for better visibility
7. **Lighter subhead & weight % font** — Label and weight percentage use `var(--primary-text-color)` at `opacity: 0.55` for improved readability over `var(--secondary-text-color)`

#### Density Toggle

New `input_boolean.filament_catalog_large_cards` helper — a simple on/off toggle.

| Mode | Columns (desktop) | Description |
|---|---|---|
| **Off** (default) | 5 | Compact grid — all Phase 3 enhancements visible |
| **On** | 3 | Large grid — wider cards with more room for labels and details |

The view uses two `conditional` card wrappers around `auto-entities` instances: one for compact (5 columns, shown when toggle is off/unavailable) and one for large (3 columns, shown when toggle is on). Both use the same `catalog_spool_card` template and filter logic. The toggle button is in the filter bar's third row.

#### Files Modified / Created

| File | Action |
|---|---|
| `common/dashboard_cards/card_templates/catalog_spool_card.yaml` | **Modified** — All Phase 3 card enhancements |
| `filament_catalog/helpers/input_boolean/filament_catalog_large_cards.yaml` | **Created** — Large cards toggle |
| `filament_catalog/dashboard_views/view_filament_catalog.yaml` | **Modified** — Conditional compact/large grid |
| `filament_catalog/dashboard_cards/catalog_filter_bar.yaml` | **Modified** — Added Large Cards toggle button |

#### Grid Layout (card template)

```
Row 1: [entity_picture] [name]           [remaining_weight] [status_icon]
Row 2: [entity_picture] [label: mat·types-vendor]             [label]
Row 3: [entity_picture] [weight_bar ————————————————]         [weight_bar]
Row 4: [location_label]                   [last_used]
```

- `status_icon`: sealed icon (blue `mdi:package-variant-closed`) OR desiccant warning (`mdi:water` in yellow/orange/red). Sealed always takes priority.
- `remaining_weight`: turns red when low stock (`< 100g`).
- `border-left`: 3px color-coded by worst active alert (desiccant age or remaining weight). Transparent when no alerts; light gray when desiccant date is undefined.
- `box-shadow`: subtle red inset glow for low-stock spools (`< 100g`).

---

### Phase 4: Tabbed Views & Sort Options — IMPLEMENTED
**Status**: ✅ Complete (2026-03-16)
**Value**: Multiple perspectives on 165 spools.

> **Performance constraint**: Each tab view MUST use a single `auto-entities` instance. Per-group sections (e.g., per-material, per-vendor) cannot use separate `auto-entities` per group. Options:
> 1. Single `auto-entities` sorted by the relevant attribute (same as Phase 1 location sort) with location labels on cards
> 2. A template sensor per tab that outputs entity IDs in the desired group order, consumed by one `auto-entities`
> 3. A custom button-card template that inserts visual separator rows when the group attribute changes (requires JS in the card template)
>
> **Shipped approach**: Combined options 2 and 3. The template sensor outputs a `grouped_entity_ids_json` attribute containing pre-sorted, pre-grouped entity lists. The auto-entities filter template reads this and injects lightweight `catalog_group_header` cards (spanning all grid columns via `card_mod :host`) at group boundaries. No `Object.values(states)` in headers — group name and count are passed as variables.

#### Tab Structure
```
[ By Location | By Material | By Vendor | By Color Family | By Filament | All ]
```

- **By Location** (default): Current Phase 1 layout — single auto-entities sorted by `location` attribute
- **By Material**: Sections: PLA, PETG, ABS, TPU, etc.
- **By Vendor**: Sections: Bambu Lab, Sunlu, ELEGOO, etc.
- **By Color Family**: Sections: Blues, Reds, Greens, Blacks & Whites, Rainbow, etc.
- **By Filament**: Aggregated view from `spoolman_filament_totals` — one row per `filament_id` with expandable spool list. Collapses 165 spools → 132 rows (and many are single-spool, so effectively shorter).
- **All**: Single flat grid with sort control

> **Note**: "Alerts" was originally a tab but was removed since it behaves as a filter, not a grouping perspective. The existing Low Stock and Desiccant Old toggles in the filter bar serve this purpose.

#### Sort Controls

New `input_select.filament_catalog_sort`:
- `Name (A-Z)` / `Name (Z-A)`
- `Weight (Low → High)` / `Weight (High → Low)`
- `Last Used (Recent)` / `Last Used (Oldest)`
- `Cost (High → Low)` / `Cost (Low → High)`
- `Vendor → Name`
- `Hue` — Sorts by color hue in rainbow order (red → orange → yellow → green → cyan → blue → purple). Converts each spool's `filament_extra_primary_color` hex to HSV hue (0–360°). Near-achromatic colors (saturation < 8% — whites, grays, blacks) sort after all chromatic colors, ordered by brightness. Spools with missing or invalid hex values sort last. When a group-by tab is active, hue sorting applies within each group.

#### Shipped Architecture

**Grouping approach**: Server-side grouped output in `sensor.filament_catalog_filtered_spools` → `grouped_entity_ids_json` attribute. Each group is `{name, count, entities}`. The auto-entities filter template iterates groups and injects `catalog_group_header` cards at boundaries. Groups span all grid columns via `card_mod: style: ':host { grid-column: 1 / -1 !important; }'`.

**Sorting approach**: Two-pass stable sort in the template sensor: (1) sort by `sk` (sort key from selected sort option, with direction), (2) stable sort by `gv` (group attribute). This yields primary group ordering with secondary sort within groups.

**"All" tab**: Flat sorted list, no group headers.

**"By Filament" tab**: Deferred to future phase — requires aggregated view with different card template.

#### Files Created/Modified

| File | Action | Notes |
|---|---|---|
| `filament_catalog/helpers/input_select/filament_catalog_tab.yaml` | **Created** | Tab selector: By Location, By Material, By Vendor, By Color Family, All |
| `filament_catalog/helpers/input_select/filament_catalog_sort.yaml` | **Created** | Sort options: Name, Weight, Last Used, Cost, Vendor then Name (ascending/descending), Hue (rainbow color sort) |
| `common/dashboard_cards/card_templates/catalog_group_header.yaml` | **Created** | Lightweight group separator — reads variables only, no entity iteration |
| `filament_catalog/template_sensors/template_sensor_filament_catalog_filter.yaml` | **Modified** | Added `grouped_entity_ids_json` attribute, tab/sort logic, derived `entity_ids_json` from grouped output |
| `filament_catalog/dashboard_cards/catalog_filter_bar.yaml` | **Modified** | Added View (tab) and Sort dropdowns in new top row |
| `filament_catalog/dashboard_views/view_filament_catalog.yaml` | **Modified** | Replaced auto-entities templates to use grouped data with inline headers; removed `sort:` property |

#### Estimated Complexity: Medium (Actual: Medium-High)

---

### Phase 5: Metrics, Insights & Alert Analytics (Future)
**Value**: Visual analytics for inventory management with proactive alert visibility — all in one place.
**Status**: Not started

> Phase 5 combines the original alert-counting concept (former Phase 5) with statistics and charts (former Phase 7). Rather than building dedicated alert UI, filtering tabs, or summary cards, alert counts surface **as chart data** alongside other inventory metrics. Phase 3 already provides card-level visual indicators (left border, badges, desiccant icons); this phase adds the aggregate "how many and what kind" view.
>
> **Sub-phase structure**: Phase 5 is broken into five incremental sub-phases (5A–5E). Each sub-phase is independently deployable and valuable. Sub-phases 5A–5C depend only on existing Spoolman entity data. Sub-phase 5D requires a print history data source (Bambuddy, custom webhook, or similar). Sub-phase 5E is a parallel infrastructure track for advanced BI tooling.

#### Issue Tracker

All Phase 5 work is tracked in [GitHub Project #18](https://github.com/users/rsocko/projects/18/views/1). The table below maps each sub-phase to its source issues:

| Sub-Phase | Issues |
|---|---|
| **5A** | [#103](https://github.com/rsocko/hass-bambulab-config/issues/103), [#150](https://github.com/rsocko/hass-bambulab-config/issues/150), [#152](https://github.com/rsocko/hass-bambulab-config/issues/152), [#101](https://github.com/rsocko/hass-bambulab-config/issues/101), [#102](https://github.com/rsocko/hass-bambulab-config/issues/102), [#133](https://github.com/rsocko/hass-bambulab-config/issues/133), [#118](https://github.com/rsocko/hass-bambulab-config/issues/118), [#117](https://github.com/rsocko/hass-bambulab-config/issues/117), [#105](https://github.com/rsocko/hass-bambulab-config/issues/105) |
| **5B** | [#115](https://github.com/rsocko/hass-bambulab-config/issues/115) |
| **5C** | [#641](https://github.com/rsocko/hass-bambulab-config/issues/641), [#104](https://github.com/rsocko/hass-bambulab-config/issues/104) |
| **5D** | [#116](https://github.com/rsocko/hass-bambulab-config/issues/116), [#649](https://github.com/rsocko/hass-bambulab-config/issues/649), [#650](https://github.com/rsocko/hass-bambulab-config/issues/650), [#110](https://github.com/rsocko/hass-bambulab-config/issues/110), [#111](https://github.com/rsocko/hass-bambulab-config/issues/111), [#112](https://github.com/rsocko/hass-bambulab-config/issues/112), [#113](https://github.com/rsocko/hass-bambulab-config/issues/113), [#114](https://github.com/rsocko/hass-bambulab-config/issues/114), [#642](https://github.com/rsocko/hass-bambulab-config/issues/642) |
| **5E** | [#149](https://github.com/rsocko/hass-bambulab-config/issues/149), [#109](https://github.com/rsocko/hass-bambulab-config/issues/109), [#130](https://github.com/rsocko/hass-bambulab-config/issues/130), [#148](https://github.com/rsocko/hass-bambulab-config/issues/148), [#106](https://github.com/rsocko/hass-bambulab-config/issues/106), [#107](https://github.com/rsocko/hass-bambulab-config/issues/107) |

---

#### Phase 5A: Inventory Insights & Alert Analytics
**Data source**: Spoolman entities only (available now)
**Dependency**: Phases 1–2
**Estimated Complexity**: High

Phase 5A delivers the core metrics panel using data already present on `sensor.spoolman_spool_*` entities. No print history or external data sources required.

##### 5A.1 — Inventory Distribution Charts

| Chart | Type | Data Source | Issue | Notes |
|---|---|---|---|---|
| Weight by Material | Tree map | `filament_material` × `remaining_weight` | [#105](https://github.com/rsocko/hass-bambulab-config/issues/105) | Implemented as `custom:apex-direct-bar-card` with `chart_type: treemap` |
| Weight by Vendor | Pie/Bar | `filament_vendor_name` × `remaining_weight` | [#105](https://github.com/rsocko/hass-bambulab-config/issues/105) | Implemented as `apexcharts-card` bar chart |
| Weight by Color Family | Pie/Bar | `filament_extra_color_family` × `remaining_weight` | [#105](https://github.com/rsocko/hass-bambulab-config/issues/105) | Implemented as `apexcharts-card` bar chart |
| Spools per Location | Bar | Count of spools grouped by `location` | — | |
| Weight by Primary Color | Stacked Bar | `filament_extra_primary_color` + `filament_color_hex` + `remaining_weight` | [#105](https://github.com/rsocko/hass-bambulab-config/issues/105) | Implemented as a stacked bar with real filament colors and `max_items: 0` (show all filaments) |

These charts answer: "How is my filament inventory distributed?" All data is directly available from spool entity attributes. These distribution charts use `remaining_weight` (not `initial_weight`) to reflect *current* inventory value rather than what was purchased.

##### 5A.1.1 — Inventory Distribution Charts (by count of Spool)

| Chart | Type | Data Source | Issue |
|---|---|---|---|
| Count by Material | Pie/Bar | Count of spools grouped by `filament_material` | [#105](https://github.com/rsocko/hass-bambulab-config/issues/105) |
| Count by Vendor | Pie/Bar | Count of spools grouped by `filament_vendor_name` | [#105](https://github.com/rsocko/hass-bambulab-config/issues/105) |
| Count by Color Family | Pie/Bar | Count of spools grouped by `filament_extra_color_family` | [#105](https://github.com/rsocko/hass-bambulab-config/issues/105) |

These charts answer: "How is my filament inventory distributed but using count instead of weight?" All data is directly available from spool entity attributes.

> **Update**: The dedicated "Count by Primary Color" chart was removed from the insights panel.
##### 5A.2 — Alert Aggregation Charts

Instead of a standalone alert summary card or dedicated alert tab, alert counts appear as chart segments. Phase 3's card visuals already handle per-spool indicators; this answers "how many of each problem do I have?" at a glance.

| Alert Category | Trigger | Issue(s) |
|---|---|---|
| **Running Low** | `remaining_weight` < stock threshold (tiered: Red/Orange/Yellow) | [#103](https://github.com/rsocko/hass-bambulab-config/issues/103), [#150](https://github.com/rsocko/hass-bambulab-config/issues/150) |
| **Nearly Empty** | `remaining_weight` < 50g | [#150](https://github.com/rsocko/hass-bambulab-config/issues/150) |
| **Needs Repurchase** | Last spool of `filament_id` AND `remaining_weight` < threshold | [#150](https://github.com/rsocko/hass-bambulab-config/issues/150) |
| **Desiccant Overdue** | `extra_desiccant_filled` age > 60 days (tiered: R/O/Y/G/Missing) | [#152](https://github.com/rsocko/hass-bambulab-config/issues/152) |
| **Missing Desiccant** | `extra_desiccant_in_spool = false` for custom or other spools | [#101](https://github.com/rsocko/hass-bambulab-config/issues/101), [#102](https://github.com/rsocko/hass-bambulab-config/issues/102) |
| **Needs Drying** | `extra_last_dried` > 90 days AND `extra_sealed = false` | — |
| **Unused (Stale)** | `last_used` > 6 months ago | — |

The horizontal bar chart uses clickable segments that set the corresponding catalog filter (existing Phase 2 toggle or new lightweight `input_boolean` where needed).

##### 5A.3 — Data Quality Reports

Proactive detection of inventory data issues. Rendered as a compact card list below the charts (or as a dedicated "Health Check" section in the insights panel).

| Report | Description | Issue |
|---|---|---|
| **Multiple Unsealed Duplicates** | Flags filaments where >1 spool is unsealed for the same `filament_id` — indicates a spool that should be consumed before opening another | [#133](https://github.com/rsocko/hass-bambulab-config/issues/133) |
| **Orphan Filaments** | Filament definitions in Spoolman with zero associated spools — candidates for cleanup | [#118](https://github.com/rsocko/hass-bambulab-config/issues/118) |
| **Duplicate Hex Colors** | Multiple filaments sharing the same `filament_color_hex` — may cause incorrect AMS color matching | [#117](https://github.com/rsocko/hass-bambulab-config/issues/117) |

> **Scope decision**: AMS vs. Spoolman weight drift is removed from Filament Catalog quality checks. This signal is more actionable on the main dashboard while a spool is actively in AMS, and provides limited value in static catalog analytics.

##### 5A Implementation Design

###### Placement: Collapsible Metrics Panel at Top of Catalog View

The metrics panel lives **inside** the existing Filament Catalog view — not on a separate view/tab. It sits between the KPI chips and the filter bar as a collapsible `<details>`-style section (using `custom:fold-entity-row` or a conditional card gated by a toggle):

```
view_filament_catalog.yaml (panel: true + vertical-stack)
├── Inventory KPI chips (existing)
│
├── [📊 Show Insights]  ← input_boolean toggle or mushroom chip
│   └── Collapsible Metrics Panel (shown when toggle is on)
│       ├── Row 1: [Tree map: Weight by Material] [Donut: Count by Material]
│       ├── Row 2: [Bar: Weight by Vendor] [Bar: Count by Vendor]
│       ├── Row 3: [Bar: Weight by Color Family] [Bar: Count by Color Family]
│       ├── Row 4: [Stacked Bar: Weight by Primary Color (all filaments)]
│       ├── Row 5: [Bar: Alert Counts by Type]  ← clickable segments
│       ├── Row 6: [Data Quality: Issues Found]  ← compact list
│       └── (Rows 7+: added incrementally by 5B–5D)
│
├── Filter Bar (existing)
└── Single auto-entities grid (existing)
```

**Why not a separate tab or view?**
- A separate view would break the flow — users want to see metrics *and then act* on the catalog below.
- A separate tab inside `tabbed-card` would need its own `auto-entities` instance (performance violation) or require leaving the catalog context.
- A collapsible panel keeps it zero-cost when hidden, and contextually useful when shown.

**Why not a popup?**
- Popups are good for single-entity detail (spool popup), but metrics benefit from persistent visibility while scrolling through the catalog.
- A user might open the insights panel, see "5 desiccant overdue," click that bar segment to filter, then scroll the catalog — all without dismissing anything.

###### Toggle Helper

`input_boolean.filament_catalog_show_insights` — Controls visibility of the metrics panel. Default: off (collapsed). The toggle chip appears in the KPI row or as a standalone mushroom chip.

###### Clickable Chart Segments → Filter Integration

Chart segments are **interactive** — tapping a segment applies the corresponding filter to the catalog grid below:

| Chart | Click Action |
|---|---|
| Tree map: Weight by Material → "PLA" tile | Sets `input_select.filament_catalog_filter_material` to `PLA` |
| Bar: Spools per Location → "AMS" bar | Sets `input_select.filament_catalog_filter_location` to `AMS` |
| Bar: Alert Counts → "Desiccant Overdue" bar | Turns on `input_boolean.filament_catalog_filter_desiccant_old` |
| Bar: Alert Counts → "Low Stock" bar | Turns on `input_boolean.filament_catalog_filter_low_stock` |
| Bar: Alert Counts → "Needs Drying" / "Stale" | Sets a new dedicated filter or search term (see below) |

**Implementation**: `custom:apexcharts-card` supports `chart.events.dataPointSelection` which can trigger a `browser_mod` service call or `fire-dom-event`. For HA-native integration, each clickable segment calls `input_select.select_option` or `input_boolean.turn_on` via `tap_action: call-service`.

> **Note**: For alert types that don't have existing filter toggles (Needs Drying, Stale), clicking those bars could set a search term or add new lightweight `input_boolean` toggles. Alternatively, these can initially be display-only with filter integration added incrementally.

###### Template Sensor: `sensor.filament_catalog_metrics`

A dedicated template sensor pre-computes all chart data server-side to avoid heavy JS in apexcharts configs:

```yaml
attributes:
  # 5A.1 — Distribution
  weight_by_material_json: '{"PLA": 45200, "PETG": 12300, ...}'  # grams
  weight_by_vendor_json: '{"Bambu Lab": 38000, "Sunlu": 15000, ...}'
  weight_by_color_family_json: '{"Blues": 12000, "Reds": 8000, ...}'
  count_by_material_json: '{"PLA": 42, "PETG": 16, ...}'
  count_by_vendor_json: '{"Bambu Lab": 31, "Sunlu": 28, ...}'
  count_by_color_family_json: '{"Blues": 19, "Reds": 12, ...}'
  count_by_primary_color_json: '{"Blue": 14, "Gray": 10, ...}'
  primary_color_weight_segments_json: '[{"name":"Blue","weight":8200,"hex":"#4169E1"}, ...]'
  spools_by_location_json: '{"AMS": 5, "Closet Shelf 1": 12, ...}'

  # 5A.2 — Alerts
  alert_counts_json: '{"repurchase": 2, "desiccant": 5, "drying": 3, "empty": 1, "stale": 4, "missing_desiccant": 2}'
  alert_entity_ids_json: '{"repurchase": ["sensor.spoolman_spool_12", ...], ...}'

  # 5A.3 — Data Quality
  data_quality_json: '{"multiple_unsealed": [...], "orphan_filaments": [...], "duplicate_hex": [...]}'

  # Summary
  total_inventory_value: 3245.50
  avg_cost_per_kg: 22.50
```

The sensor triggers on `sensor.spoolman_filament_totals` changes (same as the filter sensor), so it recomputes only when spool data changes — not on every state change.

###### Modularity: Card-Per-Chart Pattern

Each chart is its own includable card file, making it easy to add/remove/reorder:

```
filament_catalog/
├── dashboard_cards/
│   ├── catalog_insights_panel.yaml          ← wrapper: conditional on toggle + vertical-stack
│   ├── insights/
│   │   ├── chart_weight_by_material.yaml    ← custom apex-direct-bar-card (treemap)
│   │   ├── chart_weight_by_vendor.yaml      ← custom apex-direct-bar-card (bar)
│   │   ├── chart_weight_by_color_family.yaml ← custom apex-direct-bar-card (bar)
│   │   ├── chart_weight_by_primary_color.yaml  ← weight by primary color (bar)
│   │   ├── chart_count_by_material.yaml     ← count distribution
│   │   ├── chart_count_by_vendor.yaml       ← count distribution
│   │   ├── chart_count_by_color_family.yaml ← count distribution
│   │   ├── chart_spools_by_location.yaml    ← custom apex-direct-bar-card (bar)
│   │   ├── chart_alert_counts.yaml          ← custom apex-direct-bar-card (horizontal bar, clickable)
│   │   ├── card_data_quality_reports.yaml   ← button-card list of data quality issues
│   │   └── (future sub-phase charts added here)
│   └── ...
├── template_sensors/
│   └── filament_catalog_metrics.yaml        ← pre-computed chart data
```

The `catalog_insights_panel.yaml` is a `conditional` card (condition: `input_boolean.filament_catalog_show_insights` is on) wrapping a `vertical-stack` of `horizontal-stack` rows that `!include` each chart card. Adding a new chart = create the card file + add an `!include` line.

###### Performance Considerations

- **`triggers_update`**: Every chart card MUST use `triggers_update: sensor.filament_catalog_metrics` to prevent re-render on unrelated entity changes.
- **Conditional wrapper**: When the insights panel is collapsed (toggle off), the chart cards are not rendered at all — zero performance cost.
- **No additional `auto-entities`**: Charts read from the pre-computed template sensor attributes, not from entity iteration.
- **Apex chart settings**: Disable animations (`chart.animations.enabled: false`), limit data points for trend charts.

###### 5A Files to Create/Modify

| File | Action |
|---|---|
| `filament_catalog/template_sensors/filament_catalog_metrics.yaml` | **Create** — Pre-computed chart + alert + data quality data |
| `filament_catalog/dashboard_cards/catalog_insights_panel.yaml` | **Create** — Conditional wrapper for insights section |
| `filament_catalog/dashboard_cards/insights/chart_weight_by_material.yaml` | **Create** — Pie chart |
| `filament_catalog/dashboard_cards/insights/chart_weight_by_vendor.yaml` | **Create** — Pie chart |
| `filament_catalog/dashboard_cards/insights/chart_weight_by_color_family.yaml` | **Create** — Pie chart |
| `filament_catalog/dashboard_cards/insights/chart_spools_by_location.yaml` | **Create** — Bar chart |
| `filament_catalog/dashboard_cards/insights/chart_alert_counts.yaml` | **Create** — Alert breakdown (clickable) |
| `filament_catalog/dashboard_cards/insights/card_data_quality_reports.yaml` | **Create** — Data quality issue list |
| `filament_catalog/helpers/input_boolean/filament_catalog_show_insights.yaml` | **Create** — Insights panel toggle |
| `filament_catalog/dashboard_views/view_filament_catalog.yaml` | **Modify** — Insert insights panel between KPIs and filter bar |
| `filament_catalog/dashboard_cards/catalog_filter_bar.yaml` | **Modify** — Add insights toggle chip (optional) |

---

#### Phase 5B: Cost Analytics
**Data source**: Spoolman `price` / `filament_price` attributes (available now)
**Dependency**: Phase 5A (metrics sensor + insights panel infrastructure)
**Estimated Complexity**: Medium

Phase 5B extends the metrics sensor and insights panel with cost-focused analytics. All data comes from the existing `price` and `filament_price` spool attributes — no print history required for the base cost views.

##### Charts & KPIs

| Chart / KPI | Type | Data Source | Issue |
|---|---|---|---|
| Avg Cost per kg by Material | Bar | `price / initial_weight` grouped by `filament_material` | [#115](https://github.com/rsocko/hass-bambulab-config/issues/115) |
| Avg Cost per kg by Vendor | Bar | `price / initial_weight` grouped by `filament_vendor_name` | [#115](https://github.com/rsocko/hass-bambulab-config/issues/115) |
| Inventory Value by Material | Stacked bar | `(remaining_weight / initial_weight) × price` grouped by material | — |
| Inventory Value Trend | Line | HA long-term statistics on `sensor.filament_catalog_metrics.total_inventory_value` | — |
| Total Spent (all-time) | KPI chip | Sum of `price` across all spools (including archived) | — |

> **Note on Inventory Value Trend**: Requires HA Recorder to track `sensor.filament_catalog_metrics` over time. The line chart will only have data from the point the sensor is created onward. Consider whether this should be a separate `sensor.filament_inventory_value` (numeric state) for better HA statistics integration.

##### Metrics Sensor Additions

New attributes added to `sensor.filament_catalog_metrics`:

```yaml
attributes:
  # ... existing 5A attributes ...

  # 5B — Cost
  avg_cost_per_kg_by_material_json: '{"PLA": 22.50, "PETG": 28.00, ...}'   # $/kg
  avg_cost_per_kg_by_vendor_json: '{"Bambu Lab": 25.00, "Sunlu": 18.00, ...}'
  inventory_value_by_material_json: '{"PLA": 1200.00, "PETG": 450.00, ...}'
  total_spent_all_time: 4500.00    # includes archived spools
```

##### 5B Files to Create/Modify

| File | Action |
|---|---|
| `filament_catalog/template_sensors/filament_catalog_metrics.yaml` | **Modify** — Add cost attributes |
| `filament_catalog/dashboard_cards/insights/chart_cost_by_material.yaml` | **Create** — Bar chart |
| `filament_catalog/dashboard_cards/insights/chart_cost_by_vendor.yaml` | **Create** — Bar chart |
| `filament_catalog/dashboard_cards/insights/chart_inventory_value_trend.yaml` | **Create** — Line chart (requires HA statistics) |
| `filament_catalog/dashboard_cards/catalog_insights_panel.yaml` | **Modify** — Add cost row |

---

#### Phase 5C: Usage & Recency Analytics
**Data source**: Spoolman `last_used` / `first_used` attributes + HA weight history
**Dependency**: Phase 5A (metrics sensor + insights panel infrastructure)
**Estimated Complexity**: Medium

Phase 5C leverages the `last_used` and `first_used` timestamps already on spool entities, plus HA's long-term statistics on `remaining_weight`, to surface usage patterns. No external print history integration is required — but the insights become richer once Phase 5D adds per-print data.

##### Charts & Features

| Chart / Feature | Type | Data Source | Issue |
|---|---|---|---|
| Recently Used Spools | Card strip / list | Top N spools sorted by `last_used` descending | [#641](https://github.com/rsocko/hass-bambulab-config/issues/641) |
| Usage by Color | Pie / bar | `initial_weight - remaining_weight` grouped by `filament_extra_primary_color` | [#104](https://github.com/rsocko/hass-bambulab-config/issues/104) |
| Usage Rate (weight/week) | Line sparkline | HA long-term statistics on `sensor.spoolman_spool_{id}` `remaining_weight` | — |
| Stale Spool Identification | Ranked list | Spools where `last_used` > 6 months ago, sorted by staleness | — |
| Spool Lifecycle Timeline | Horizontal bar | `registered → first_used → last_used → now` per spool | — |

##### Recently Used Spools — Multi-Surface Feature ([#641](https://github.com/rsocko/hass-bambulab-config/issues/641))

This issue requests showing recently used spools in several places:
1. **Insights panel**: A horizontal strip of the 5–10 most recently used spool cards (compact `catalog_spool_card` at reduced size)
2. **Main dashboard**: A "Recent Spools" card showing the last 3–5 used spools as mini swatches with names
3. **Mobile-friendly picker**: A sort option "Last Used (Recent)" already exists in Phase 4 — may be sufficient for the mobile use case

The "recently used" data comes from `last_used` on each spool entity. The `stacked bar graph or line chart` suggested in the issue would show usage frequency over time — this overlaps with Phase 5D's print history charts and can be enhanced once that data is available.

##### Usage by Color ([#104](https://github.com/rsocko/hass-bambulab-config/issues/104))

Total weight consumed (`initial_weight - remaining_weight`) grouped by primary color. Renders as a pie chart where each slice uses the actual `filament_color_hex` as its fill color — creating a visually distinctive chart that immediately communicates color usage patterns.

> **Limitation**: This shows *total consumed to date*, not consumption over a specific period. Period-based consumption tracking (e.g., "grams of blue used this month") requires print history data (Phase 5D) or snapshotting weight values over time via HA statistics.

##### Metrics Sensor Additions

```yaml
attributes:
  # ... existing 5A/5B attributes ...

  # 5C — Usage & Recency
  recently_used_json: '[{"entity_id": "sensor.spoolman_spool_42", "last_used": "2026-03-15T...", "name": "..."}, ...]'
  usage_by_color_json: '{"#4169E1": 1200, "#FF0000": 800, ...}'   # grams consumed, keyed by hex
  usage_by_color_family_json: '{"Blues": 3400, "Reds": 2100, ...}'
  stale_spools_json: '[{"entity_id": "...", "last_used": "2025-08-01", "days_idle": 228}, ...]'
```

##### 5C Files to Create/Modify

| File | Action |
|---|---|
| `filament_catalog/template_sensors/filament_catalog_metrics.yaml` | **Modify** — Add usage/recency attributes |
| `filament_catalog/dashboard_cards/insights/card_recently_used.yaml` | **Create** — Recent spools strip |
| `filament_catalog/dashboard_cards/insights/chart_usage_by_color.yaml` | **Create** — Color-aware pie chart |
| `filament_catalog/dashboard_cards/insights/card_stale_spools.yaml` | **Create** — Stale spool ranked list |
| `filament_catalog/dashboard_cards/catalog_insights_panel.yaml` | **Modify** — Add usage row |

---

#### Phase 5D: Print History Analytics
**Data source**: Print history (Bambuddy, custom webhook, or combination) + Power monitoring
**Dependency**: Phase 5A + **Print history integration** (not yet built)
**Estimated Complexity**: High
**Status**: ⚠️ Blocked — print history data source not yet determined

> **Critical dependency**: Phase 5D requires a structured print history data source that does not yet exist in this project. The data source decision is tracked across several open issues:
> - [#251](https://github.com/rsocko/hass-bambulab-config/issues/251) — **Explore Bambuddy** (confirmed to have print archive; confirmed to record weight by filament for multi-filament prints)
> - [#248](https://github.com/rsocko/hass-bambulab-config/issues/248) — Look into OpenSpoolman for print history / spool usage
> - [#249](https://github.com/rsocko/hass-bambulab-config/issues/249) — Review Printstack capabilities
> - [#235](https://github.com/rsocko/hass-bambulab-config/issues/235) — Review NodeRed Automation for History++
> - [#197](https://github.com/rsocko/hass-bambulab-config/issues/197) / [#198](https://github.com/rsocko/hass-bambulab-config/issues/198) — Define fields / metadata to store
>
> Until the print history data model is finalized, this sub-phase documents the **desired metrics** so the data source requirements are clear. The charts below describe *what* to display; the exact template sensor attributes will depend on the chosen data source's schema.

##### Print Time Metrics

| Chart | Type | Description | Issue |
|---|---|---|---|
| Activity Heatmap | GitHub-style grid | Days × weeks grid colored by hours printed or number of prints per day. Each cell colored by intensity. | [#110](https://github.com/rsocko/hass-bambulab-config/issues/110) |
| Hours per Week | Bar | Weekly print hours over the last N weeks | [#111](https://github.com/rsocko/hass-bambulab-config/issues/111) |
| Hours per Month | Bar | Monthly print hours over the last N months | [#112](https://github.com/rsocko/hass-bambulab-config/issues/112) |
| Utilization Rate | KPI / gauge | Percentage of days in the last 30/90/365 days with at least one active print | [#113](https://github.com/rsocko/hass-bambulab-config/issues/113) |

> **Implementation note**: The GitHub-style activity heatmap ([#110](https://github.com/rsocko/hass-bambulab-config/issues/110)) may require a custom card or creative use of `apexcharts-card` heatmap series. Alternatively, a `custom:button-card` with CSS grid rendering colored cells from a template sensor attribute could work within the existing card ecosystem.

##### Cost per Print

| Chart / KPI | Type | Description | Issue |
|---|---|---|---|
| Filament Cost per Print | KPI / bar | `Σ(weight_used × cost_per_g)` for each print — derived from spool IDs used per print | [#116](https://github.com/rsocko/hass-bambulab-config/issues/116) |
| Power Cost per Print | KPI | Printer power consumption during print × electricity rate | [#649](https://github.com/rsocko/hass-bambulab-config/issues/649) |
| Total Cost per Print | KPI | Filament cost + power cost | [#649](https://github.com/rsocko/hass-bambulab-config/issues/649) |
| Per-Print Power Breakdown | Bar / line | Estimated vs. actual power per print; cumulative power over time | [#650](https://github.com/rsocko/hass-bambulab-config/issues/650) |

> **Note on power data ([#649](https://github.com/rsocko/hass-bambulab-config/issues/649), [#650](https://github.com/rsocko/hass-bambulab-config/issues/650))**: Power monitoring for the printer is a separate feature area (see `power_monitoring/` docs). Per-print power requires correlating print start/end timestamps with power sensor readings. Estimated power could come from print duration × average wattage. Actual power requires integration with a smart plug or energy monitor. Whether this shows estimated, actual, or cumulative data is an open design question.

##### Energy vs. Print Time ([#114](https://github.com/rsocko/hass-bambulab-config/issues/114))

Scatter plot or dual-axis chart showing energy consumption (kWh) vs. print time (hours) per print. Useful for identifying inefficient prints (high energy for short prints, or vice versa). Requires both print history timestamps and power monitoring data.

##### Spool-to-Print Tracking ([#642](https://github.com/rsocko/hass-bambulab-config/issues/642))

Each print record should store:
- `filament_id` and `spool_id` for every spool used
- Material/color metadata for each spool at time of print
- Flag for unidentified filament (spool could not be matched)
- Multi-filament prints: weight consumed per spool

This enables rich queries like "which prints used this spool?" and "show all prints with PLA" that feed the charts above. The exact schema depends on the print history data source decision.

> **Open questions for 5D**:
> 1. Will Bambuddy be the primary print history source, or will a custom webhook/database be built?
> 2. Does Bambuddy expose print history via HA entities, REST API, or both?
> 3. How will multi-filament print records link to individual spool IDs?
> 4. What is the electricity rate source — manual input_number, or fetched from a utility integration?
> 5. Should power data come from a smart plug (actual) or estimated from print duration?

##### 5D Files to Create/Modify (Tentative)

| File | Action |
|---|---|
| `filament_catalog/template_sensors/filament_catalog_metrics.yaml` | **Modify** — Add print history attributes |
| `filament_catalog/dashboard_cards/insights/chart_print_activity_heatmap.yaml` | **Create** — GitHub-style activity grid |
| `filament_catalog/dashboard_cards/insights/chart_print_hours_weekly.yaml` | **Create** — Weekly bar chart |
| `filament_catalog/dashboard_cards/insights/chart_print_hours_monthly.yaml` | **Create** — Monthly bar chart |
| `filament_catalog/dashboard_cards/insights/chart_cost_per_print.yaml` | **Create** — Per-print cost breakdown |
| `filament_catalog/dashboard_cards/insights/chart_energy_vs_time.yaml` | **Create** — Scatter / dual-axis |
| `filament_catalog/dashboard_cards/insights/kpi_utilization_rate.yaml` | **Create** — Printer utilization gauge |
| `filament_catalog/dashboard_cards/catalog_insights_panel.yaml` | **Modify** — Add print history rows |

---

#### Phase 5E: Advanced BI & External Tooling
**Data source**: Various (Spoolman, HA, Prometheus, Grafana)
**Dependency**: Independent — can run in parallel with 5A–5D
**Estimated Complexity**: Variable (research + infrastructure)
**Status**: ⚠️ Research / exploration phase

Phase 5E is a parallel track exploring external BI tooling as an alternative or complement to the HA-native insights panel. These are longer-horizon items that may influence the approach for 5A–5D or provide more powerful visualization capabilities.

| Item | Description | Issue |
|---|---|---|
| **Prometheus Integration** | Push Spoolman spool data to Prometheus for time-series storage. Enables historical queries not possible with HA Recorder alone. | [#149](https://github.com/rsocko/hass-bambulab-config/issues/149) |
| **Grafana Dashboards** | Build Grafana dashboards for spool info/history. May embed in HA via `webpage` card or run standalone. | [#109](https://github.com/rsocko/hass-bambulab-config/issues/109), [#130](https://github.com/rsocko/hass-bambulab-config/issues/130) |
| **Filametrics Exploration** | Research Filametrics features, reports, and metrics for inspiration and potential integration. | [#148](https://github.com/rsocko/hass-bambulab-config/issues/148) |
| **SimplyPrint Reports** | Catalog available reports from SimplyPrint to determine if any can be reused or extended. | [#106](https://github.com/rsocko/hass-bambulab-config/issues/106) |
| **PowerBI Prototypes** | Create prototype dashboards in PowerBI for advanced analytics that may be difficult in HA. | [#107](https://github.com/rsocko/hass-bambulab-config/issues/107) |

> **Decision**: Phase 5E outputs should feed *back* into the design of 5A–5D. For example, if Grafana proves significantly better for time-series charts, Phase 5D's print history charts might embed Grafana panels rather than using `apexcharts-card`. The Prometheus integration ([#149](https://github.com/rsocko/hass-bambulab-config/issues/149)) is particularly relevant — it could become the long-term statistics backend for inventory value trends (5B) and usage rate tracking (5C).

##### Relationship to HA-Native Charts

The HA-native approach (apexcharts-card + template sensors) is the **primary path** for Phases 5A–5C because:
- No additional infrastructure needed
- Charts live inline with the catalog (contextual)
- Clickable segments integrate with catalog filters (interactive)
- Zero-cost when collapsed

External tools (Grafana, PowerBI) are better suited for:
- Complex time-series queries spanning months/years
- Multi-dimensional drill-down (not feasible in HA cards)
- Print history analytics requiring SQL-like queries
- Sharing dashboards with others who don't have HA access

The two approaches are not mutually exclusive — simple/interactive charts stay in HA, while complex analytics can live in Grafana.

---

#### Phase 5 Summary

| Sub-Phase | Description | Data Source | Blocked? | Effort |
|---|---|---|---|---|
| **5A** | Inventory insights, alerts, data quality | Spoolman entities | No | High |
| **5B** | Cost analytics | Spoolman `price` attributes | No | Medium |
| **5C** | Usage & recency | Spoolman `last_used` + HA statistics | No | Medium |
| **5D** | Print history analytics | Bambuddy / TBD | **Yes** — print history not yet built | High |
| **5E** | External BI tooling | Various | No (research) | Variable |

**Recommended order**: 5A → 5B → 5C (can start 5E research in parallel at any time) → 5D (once print history source is determined)

#### Estimated Complexity: High (total across all sub-phases)

---

## Non-Requirements

The following features have been explicitly evaluated and **will not be implemented** in the Filament Catalog:

| Feature | Reason |
|---|---|
| **Drag-and-drop spool reordering / location management** | Would require a custom Lovelace card (HTML5 DnD or Sortable.js) — fundamentally not a YAML-dashboard feature. Spoolman's own UI already provides drag-and-drop location management. The catalog popup's existing Location chip → `more-info` on `select.spoolman_spool_{id}_location` is sufficient for individual moves. |
| **Dedicated Alerts tab / view** | Alert counts are surfaced as chart data in the Metrics & Insights panel (Phase 5). Per-spool alert indicators already exist as card-level badges and border colors (Phase 3). A standalone alerts tab would duplicate existing functionality. |
| **Custom Lovelace card development** | The catalog is built entirely with existing community cards (`button-card`, `auto-entities`, `apexcharts-card`, `bubble-card`, etc.). No custom JavaScript card development is planned. |
| **Spoolman data editing beyond location** | Editing spool metadata (name, vendor, material, notes, etc.) is Spoolman's domain. The catalog is a read-focused dashboard with limited write actions (mark dried, refill desiccant, change location). |

---

## Visual Reference: Comparison to Spoolman UI

The Spoolman screenshot shows a location-grouped layout with:
- Location headers with spool count badges (5, 5, 6, 8 spools per group)
- Spool cards: ID + name, material + weight + spool size, last used timestamp
- Colored swatch circle per spool
- Drag handles (not planned — see [Non-Requirements](#non-requirements))
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

2. **Filament type breakdown** — Pie chart (via `custom:apexcharts-card`) showing weight distribution by material, vendor, or color family. Phase 5 feature.

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
|---|---|---|---|---|
| **1** | Compact spool grid + popup + KPIs | Medium-High | None | ✅ Complete |
| **2** | Filters, search, stock threshold helper | High | Phase 1 | ✅ Complete |
| **3** | Enhanced card visuals + density toggle | Medium | Phase 1 | ✅ Complete |
| **4** | Tabbed views + sort options | Medium | Phase 1; benefits from 2 | ✅ Complete |
| **5A** | Inventory insights, alerts, data quality | High | Phase 1; benefits from 2, 4 | |
| **5B** | Cost analytics | Medium | Phase 5A | |
| **5C** | Usage & recency analytics | Medium | Phase 5A | |
| **5D** | Print history analytics | High | Phase 5A + print history source (TBD) | ⚠️ Blocked |
| **5E** | Advanced BI & external tooling | Variable | Independent (research) | |

**Recommended order**: Phase 1 → 2 → 3 → 4 → **5A → 5B → 5C** (start 5E research in parallel) → **5D** (once print history source is determined)

Phases 1–4 are complete. Phase 5 is broken into five incremental sub-phases:
- **5A–5C** are unblocked and use existing Spoolman data — these are the immediate next steps
- **5D** requires a print history integration (Bambuddy, OpenSpoolman, or custom) that is still being evaluated ([#251](https://github.com/rsocko/hass-bambulab-config/issues/251), [#248](https://github.com/rsocko/hass-bambulab-config/issues/248), [#249](https://github.com/rsocko/hass-bambulab-config/issues/249))
- **5E** is an independent research track that can proceed at any time and may influence the implementation approach for 5A–5D
