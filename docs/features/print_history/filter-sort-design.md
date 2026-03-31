# Print History — Filtering, Sorting & Pagination Design

> **Status**: Implemented baseline (2026-03-29)
> **Created**: 2026-03-28
> **Depends on**: [README.md](README.md), [bambuddy-archive-api-catalog.md](../../features/bambuddy_common/bambuddy-archive-api-catalog.md)
> **Pattern reference**: [filament-catalog.md](../filament_catalog/filament-catalog.md) Phase 2 (Filter Architecture)

## Problem Statement

This document captures the implemented baseline for the print history browser: a bulk archive cache in Layer 1, a server-side filter/sort/page layer in Layer 2, and an always-visible top control bar with card variants in Layer 3. It also remains the place to document follow-on refinements and scaling decisions.

## Goals

1. **Consistent UX** — Reuse the repository's existing filter/sort language and visual language from the Filament Catalog, with a permanently visible top control bar rather than modal browsing controls
2. **Server-side browser state** — Keep filter, sort, and page logic in HA template sensors so the dashboard only renders the current slice
3. **Responsive pagination** — Navigate pages without re-polling the API
4. **Scalable** — Work well at 50 archives, degrade gracefully at 1000+
5. **Focused page layout** — Keep the archive browser as the hero surface while keeping the controls accessible on the first screen
6. **Visual flexibility** — Support 2-3 archive record card variants so users can switch between dense browsing and larger media previews
7. **Incremental** — Can be added to the existing print_history package without breaking current functionality

---

## Data Strategy: Slim vs Full Archives

### The Core Question

The `/slim` endpoint returns a minimal set of fields (~200 bytes/archive). But meaningful filtering (e.g., by filament color) and card rendering (e.g., thumbnails, designer info) requires fields that only exist in the full `/archives` response.

### Field Comparison: Slim vs Full vs What We Need

| Field | In Slim? | In Full? | Needed For | Category |
|-------|----------|----------|------------|----------|
| `printer_id` | ✅ | ✅ | Printer filter | Filter |
| `print_name` | ✅ | ✅ | Search, display | Filter + Display |
| `print_time_seconds` | ✅ | ✅ | Sort | Sort |
| `actual_time_seconds` | ✅ | ✅ | Duration sort/display | Sort + Display |
| `filament_used_grams` | ✅ | ✅ | Sort, display | Sort + Display |
| `filament_type` | ✅ | ✅ | Material filter | Filter |
| `filament_color` | ✅ | ✅ | **Color filter**, color swatches | **Filter + Display** |
| `status` | ✅ | ✅ | Status filter | Filter |
| `started_at` | ✅ | ✅ | Date filter, sort | Filter + Sort |
| `completed_at` | ✅ | ✅ | Display | Display |
| `cost` | ✅ | ✅ | Sort, display | Sort + Display |
| `quantity` | ✅ | ✅ | Display | Display |
| `created_at` | ✅ | ✅ | Display | Display |
| **`id`** | ❌ | ✅ | **Thumbnail URL construction**, detail link | **Critical Display** |
| `layer_height` | ❌ | ✅ | Display, potential filter | Display |
| `nozzle_diameter` | ❌ | ✅ | Display | Display |
| `nozzle_temperature` | ❌ | ✅ | Display | Display |
| `total_layers` | ❌ | ✅ | Display | Display |
| `sliced_for_model` | ❌ | ✅ | Display | Display |
| `designer` | ❌ | ✅ | Display, search | Display |
| `makerworld_url` | ❌ | ✅ | Link | Display |
| `is_favorite` | ❌ | ✅ | Filter, display | Filter + Display |
| `tags` | ❌ | ✅ | Filter (enriched tags), search | Filter |
| `notes` | ❌ | ✅ | Search | Search |
| `failure_reason` | ❌ | ✅ | Display (on failures) | Display |
| `thumbnail_path` | ❌ | ✅ | Card image | Display |
| `extra_data.filament_slots[]` | ❌ | ✅ | Per-color grams, color swatches | Display |
| `extra_data._print_data.*` | ❌ | ✅ | Raw AMS tray data | *(Not needed)* |

### What's Missing from Slim That Actually Matters

1. **`id`** — Can't construct thumbnail URLs (`/archives/{id}/thumbnail`) without it. This alone makes slim insufficient for card rendering.
2. **`is_favorite`** — Can't filter or highlight favorites.
3. **`tags`** — Can't filter by enrichment tags (e.g., `vendor:Bambu Lab`, `spoolman:42`).
4. **`designer`** — Can't search by designer name.
5. **`layer_height`** — Nice for display but not critical for filtering.
6. **`filament_slots[]`** — Per-slot color hex codes and gram usage. Richer than the comma-separated `filament_color` string (which IS in slim). Useful for color swatch rendering.

Note: `filament_color` (comma-separated hex string like `#000000,#FFFFFF,#C12E1F`) IS in the slim response, so basic color filtering is possible without full data. However, per-slot breakdown requires `extra_data.filament_slots[]`.

### Options Evaluated

#### Option A: Use `/slim` as originally designed
- **Pro**: Small payload (~200 bytes/archive), fast
- **Con**: No `id` (no thumbnails), no favorites, no tags, no designer. The card would be text-only with no images. Fundamentally insufficient for a good history view.
- **Verdict**: ❌ Rejected — missing `id` is a dealbreaker

#### Option B: Use full `/archives` and trim in template
- **Source**: `GET /archives/?limit=500`
- **Pro**: ALL fields available — thumbnails, tags, favorites, designer, filament_slots
- **Con**: The full response includes `extra_data` with the enormous `_print_data.raw_data.ams[].tray[]` blob (~8-12 KB per archive). At 500 archives, that's 4-6 MB of JSON in a single sensor attribute.
- **Verdict**: ⚠️ Feasible ONLY if we trim `extra_data` down

#### Option C: Full `/archives` with Jinja2 field projection in Layer 1 ← **RECOMMENDED**
- **Source**: `GET /archives/?limit=500`
- **Approach**: The trigger-based template sensor fetches the full response, then the attribute template **projects** (cherry-picks) only the fields we need into a trimmed array before storing as `archives_json`.
- **How**: Jinja2 `for` loop builds a new list of dicts with only the ~20 fields we want, discarding `extra_data._print_data`, `file_path`, `content_hash`, `duplicates`, etc.
- **Per-archive size**: ~400-500 bytes (vs ~200 for slim, vs ~10-15 KB for raw full)
- **500 archives**: ~200-250 KB (comfortable for HA state machine)
- **Pro**: All useful fields available for filtering and display; bloat stripped at ingest
- **Con**: The initial API response is still large (fetched once, processed once, then discarded). Jinja2 projection loop adds ~0.5s processing on each fetch. This happens on trigger events (~5-min interval), NOT on filter changes.
- **Verdict**: ✅ Best balance — rich data for filtering/display, manageable storage

#### Option D: Two-tier fetch — slim for filter + on-demand detail
- **Approach**: Fetch `/slim` for the list. When rendering a card row, fetch `/archives/{id}` for thumbnail + details.
- **Con**: N+1 API calls on each page render. Rate limited. Slow. Complex. Doesn't solve the filter problem (no `id` in slim means we can't even fetch details).
- **Verdict**: ❌ Rejected — impractical

#### Option E: Fetch full JSON → save to disk → read from file
- **Approach**: A `shell_command` or automation fetches the full response to `/config/www/3d_printing/print_history/archives_cache.json`, then a `command_line` sensor reads from disk.
- **Pro**: Decouples fetch frequency from template evaluation. Could store the full raw response with no size concern.
- **Con**: HA's `command_line` sensor still parses the JSON in Jinja2 — same template evaluation cost. The disk roundtrip adds I/O latency. File management (permissions, cleanup) is fragile. And the real bottleneck is Jinja2 iteration, not the fetch or storage — so this doesn't meaningfully help.
- **Verdict**: ❌ Rejected — solves the wrong problem. The bottleneck is template eval speed, not storage.

#### Option F: Fetch full JSON → trim in Python (AppDaemon / custom component)
- **Approach**: A Python-based HA component or AppDaemon app fetches, trims, indexes, and exposes the data as a sensor.
- **Pro**: Python is orders of magnitude faster than Jinja2 for iteration/filtering. Could handle 5000+ archives easily.
- **Con**: Adds a runtime dependency (AppDaemon or custom component). Breaks the "pure YAML" approach. Overkill for <1000 archives.
- **Verdict**: ❌ Deferred — only consider if Jinja2 becomes the bottleneck at 1000+ archives

### Decision: Option C — Full Endpoint with Jinja2 Field Projection

The Layer 1 sensor fetches `GET /archives/?limit=500` and projects to a trimmed schema:

```jinja2
{# Project each archive to only the fields we need #}
{% set ns = namespace(trimmed=[]) %}
{% for a in raw_archives %}
  {% set slots = a.get('extra_data', {}).get('filament_slots', [])
       if a.get('extra_data') is mapping else [] %}
  {% set ns.trimmed = ns.trimmed + [dict(
    id=a.get('id'),
    printer_id=a.get('printer_id'),
    print_name=a.get('print_name', ''),
    print_time_seconds=a.get('print_time_seconds', 0),
    actual_time_seconds=a.get('actual_time_seconds'),
    filament_used_grams=a.get('filament_used_grams', 0),
    filament_type=a.get('filament_type', ''),
    filament_color=a.get('filament_color', ''),
    filament_slots=slots,
    status=a.get('status', ''),
    started_at=a.get('started_at', ''),
    completed_at=a.get('completed_at'),
    cost=a.get('cost', 0),
    object_count=a.get('object_count', 1),
    layer_height=a.get('layer_height'),
    total_layers=a.get('total_layers'),
    nozzle_diameter=a.get('nozzle_diameter'),
    designer=a.get('designer', ''),
    is_favorite=a.get('is_favorite', false),
    tags=a.get('tags', ''),
    notes=a.get('notes', ''),
    failure_reason=a.get('failure_reason', '')
  )] %}
{% endfor %}
{{ ns.trimmed | tojson }}
```

### Projected Archive Schema (~450 bytes per archive)

```json
{
  "id": 171,
  "printer_id": 1,
  "print_name": "Hueforge back to the future",
  "print_time_seconds": 15533,
  "actual_time_seconds": null,
  "filament_used_grams": 44.82,
  "filament_type": "PLA",
  "filament_color": "#000000,#FFFFFF,#C12E1F,#F4EE2A",
  "filament_slots": [
    {"slot_id": 1, "used_g": 29.69, "type": "PLA", "color": "#000000"},
    {"slot_id": 2, "used_g": 2.38, "type": "PLA", "color": "#FFFFFF"},
    {"slot_id": 7, "used_g": 8.45, "type": "PLA", "color": "#C12E1F"},
    {"slot_id": 8, "used_g": 4.3, "type": "PLA", "color": "#F4EE2A"}
  ],
  "status": "printing",
  "started_at": "2026-03-28T13:55:04.674129",
  "completed_at": null,
  "cost": 1.12,
  "object_count": 1,
  "layer_height": 0.08,
  "total_layers": 30,
  "nozzle_diameter": 0.4,
  "designer": "StefBull85",
  "is_favorite": false,
  "tags": "spoolman:42,vendor:Bambu Lab,ha_enriched:true",
  "notes": "",
  "failure_reason": ""
}
```

### Updated Size Estimates (Projected Schema)

| Archive Count | Projected JSON | vs Slim (~200B) | vs Raw Full (~10KB) | Template Eval | Practical? |
|---------------|---------------|-----------------|---------------------|---------------|------------|
| 50 | ~22 KB | +12 KB | -490 KB | <0.1s | ✅ Trivial |
| 200 | ~90 KB | +50 KB | -1.9 MB | ~0.3s | ✅ Comfortable |
| 500 | ~225 KB | +125 KB | -4.8 MB | ~0.8s | ✅ Good default |
| 1,000 | ~450 KB | +250 KB | -9.5 MB | ~2s | ⚠️ Noticeable |
| 2,000 | ~900 KB | +500 KB | -19 MB | ~4-5s | ⚠️ Sluggish |

The projected schema is roughly **2.2x** the size of slim but gives us every field needed for filtering and display. Compared to raw full (~10-15 KB/archive), it's a **95% reduction** (strips `_print_data`, AMS dumps, file paths, content hashes).

`quantity` still exists in the Bambuddy API, but the runtime browser/heatmap cache intentionally omits it. The active print history metrics use `object_count` for object totals and treat archive rows as the source of truth for print totals. If a future archive-detail popup wants to show API `quantity`, it can be added back as a display-only field without changing the current activity metrics.

### Additional Filters Enabled by Full Data

| Filter | Field | Helper Type |
|--------|-------|-------------|
| **Filament Color** | `filament_color` (also in slim) | `input_text` backing store + clickable color-chip row generated from unique colors across all archives |
| **Favorites** | `is_favorite` | `input_boolean` (`on` = favorites only) |
| **Has Tags** | `tags` (non-empty) | `input_boolean` |
| **Designer** | `designer` | `input_select` — dynamic |
| **Layer Height** | `layer_height` | `input_select` — dynamic (`0.04`, `0.08`, `0.12`, `0.16`, `0.20`) |

---

## Architecture Overview

### Why This Differs from the Filament Catalog

The Filament Catalog filters **HA entities** (`sensor.spoolman_spool_*`) that are already in the state machine — the template sensor iterates entity states directly. Print History data lives in an **external API** (Bambuddy). There are no per-archive HA entities.

This creates a data plumbing challenge: we need to get archive data into HA's template engine in a filterable form.

### Layered Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 1: API Data Fetch + Field Projection                      │
│  Trigger-based template sensor + REST command action              │
│  Calls GET /archives → projects to trimmed schema (~450B/item)   │
├──────────────────────────────────────────────────────────────────┤
│  Layer 2: Server-Side Filter + Sort + Page                        │
│  Template sensors read Layer 1 attribute + input helpers          │
│  Output metadata plus the current visible archive slice          │
├──────────────────────────────────────────────────────────────────┤
│  Layer 3: Dashboard UI                                           │
│  Always-visible browser header + variant-aware archive records   │
│  Reads from Layer 2 sensor attributes                            │
└──────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
                ┌──────────────────┐
                │ Bambuddy API     │
                │ GET /archives/   │
                │ ?limit=500       │
                └────────┬─────────┘
                         │  JSON array (full, ~5 MB)
                         ▼
        ┌─────────────────────────────────────┐
        │ sensor.print_history_archives       │  Layer 1
        │ (trigger-based template)            │
        │                                     │
        │ Jinja2 projects to trimmed schema   │
        │ Strips extra_data._print_data, etc. │
        │                                     │
        │ state: archive count                │
        │ attr.archives_json: trimmed array   │
        │ (~225 KB for 500 archives)          │
        └────────────────┬────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
   ┌─────────────┐ ┌──────────┐ ┌──────────────┐
   │ input_select│ │input_text│ │ input_number  │
   │ (status,    │ │ (search) │ │ (page, size)  │
   │ material,   │ │          │ │               │
   │ color,      │ └──────────┘ └───────────────┘
   │ printer,    │
   │ favorites,  │
   │ date_range, │
   │ sort)       │
   └──────┬──────┘
          │
          ▼
  ┌─────────────────────────────────┐
  │ sensor.print_history_filtered   │  Layer 2
  │ (standard template sensor)      │
  │                                 │
  │ state: filtered count           │
  │ attr.page_json: current page    │
  │ attr.total_pages: N             │
  │ attr.active_filters: summary    │
  └───────────────┬─────────────────┘
                  │
                  ▼
  ┌─────────────────────────────────┐
  │ Dashboard                       │  Layer 3
  │ • Browser toolbar + popups      │
  │ • Variant-aware archive cards   │
  │   w/ thumbnails from /archives  │
  │   /{id}/thumbnail               │
  │ • Pagination controls           │
  └─────────────────────────────────┘
```

---

## Layer 1: Data Fetch — Trigger-Based Template Sensor with Action

### Why This Approach

HA's `rest:` integration stores per-sensor values via `value_template`, but cannot store the full response array as an attribute (flat arrays are incompatible with `json_attributes` / `json_attributes_path`).

Starting with HA 2024.11, **trigger-based template sensors** support an `action` block that can call services and store response data as variables. Combined with `rest_command` response handling (HA 2023.7+), this gives us a clean way to fetch API data and store it in sensor attributes — all within native HA YAML.

### REST Command (data fetcher)

```yaml
# rest_commands/bambuddy_fetch_archives.yaml
bambuddy_fetch_archives:
  url: >-
    {{ states('input_text.bambuddy_api_base_url') }}/api/v1/archives/?limit={{
      states('input_number.print_history_max_archives') | int(500)
    }}
  method: GET
  headers:
    X-API-Key: !secret bambuddy_api_key
  content_type: application/json
```

### Trigger-Based Template Sensor (fetch + project + store)

```yaml
# template_sensors/print_history_archives.yaml
- trigger:
    # Regular polling
    - trigger: time_pattern
      minutes: "/5"
    # Refresh on print events (via Bambuddy webhook)
    - trigger: event
      event_type: bambuddy_webhook_event
      event_data:
        event: print_complete
    - trigger: event
      event_type: bambuddy_webhook_event
      event_data:
        event: print_failed
    - trigger: event
      event_type: bambuddy_webhook_event
      event_data:
        event: print_stopped
    # Refresh on HA start
    - trigger: homeassistant
      event: start
  action:
    - action: rest_command.bambuddy_fetch_archives
      response_variable: result
  sensor:
    - name: "Print History Archives"
      unique_id: print_history_archives
      icon: mdi:database-outline
      state: >-
        {% set content = result.get('content', '[]') %}
        {% if content is string %}
          {{ (content | from_json) | length }}
        {% else %}
          0
        {% endif %}
      attributes:
        archives_json: >-
          {# Project full archives to trimmed schema — strip extra_data._print_data #}
          {% set content = result.get('content', '[]') %}
          {% if content is string %}
            {% set raw = content | from_json %}
          {% elif content is iterable %}
            {% set raw = content | list %}
          {% else %}
            {% set raw = [] %}
          {% endif %}
          {% set ns = namespace(trimmed=[]) %}
          {% for a in raw %}
            {% set ed = a.get('extra_data', {}) if a.get('extra_data') is mapping else {} %}
            {% set slots = ed.get('filament_slots', []) %}
            {% set ns.trimmed = ns.trimmed + [dict(
              id=a.get('id'),
              printer_id=a.get('printer_id'),
              print_name=a.get('print_name', ''),
              print_time_seconds=a.get('print_time_seconds', 0),
              actual_time_seconds=a.get('actual_time_seconds'),
              filament_used_grams=a.get('filament_used_grams', 0),
              filament_type=a.get('filament_type', ''),
              filament_color=a.get('filament_color', ''),
              filament_slots=slots,
              status=a.get('status', ''),
              started_at=a.get('started_at', ''),
              completed_at=a.get('completed_at'),
              cost=a.get('cost', 0),
              object_count=a.get('object_count', 1),
              layer_height=a.get('layer_height'),
              total_layers=a.get('total_layers'),
              nozzle_diameter=a.get('nozzle_diameter'),
              designer=a.get('designer', ''),
              is_favorite=a.get('is_favorite', false),
              tags=a.get('tags', ''),
              notes=a.get('notes', ''),
              failure_reason=a.get('failure_reason', '')
            )] %}
          {% endfor %}
          {{ ns.trimmed | tojson }}
        last_fetch: >-
          {{ now().isoformat() }}
```

### Key Characteristics

- **Single entity** (`sensor.print_history_archives`) holds ALL fetched + projected archive data
- **Triggers on events** — immediate refresh when prints complete/fail, plus 5-minute polling
- **Field projection at ingest** — strips `extra_data._print_data` (AMS dumps, raw MQTT data) and other unused fields (`file_path`, `content_hash`, `duplicates`, `source_3mf_path`, etc.), keeping ~21 fields per archive
- **Activity metrics use `object_count`** — Layer 1 projects `object_count`, Layer 2 sums it for object totals, and print totals remain archive-count based
- **Preserves `filament_slots[]`** — extracted from `extra_data` before the rest is discarded. Provides per-slot color hex + grams for color swatch rendering.
- **Uses full `/archives/` endpoint** — not `/slim`, because `/slim` lacks `id` (needed for thumbnail URLs), `is_favorite`, `tags`, `designer`, and `extra_data.filament_slots[]`
- **~450 bytes/archive after projection** — vs ~200B (slim) and ~10-15 KB (raw full). 500 archives ≈ 225 KB.
- **Projection happens once per fetch** (every 5 min or on events), NOT on every filter change. Filter changes re-evaluate the already-trimmed data in Layer 2.

### What About the Existing REST Sensor?

The existing `bambuddy_print_history_sensor.yaml` (the `rest:` block with "last print" derived sensors) should be **kept for now**. It serves a different purpose — powering the `sensor.bambuddy_last_print_*` entities used for quick-glance tiles and automations. It polls at a low rate and is lightweight.

The new `print_history_archives` sensor is specifically for the filterable table view. They can coexist. In a future cleanup, the "last print" sensors could be derived from the archives data instead.

---

## Layer 2: Filter + Sort + Page — Template Sensor

### Filter Dimensions

Derived from the projected archive schema (full endpoint, trimmed fields):

| Filter | Helper Type | Options | Source Field |
|--------|-------------|---------|--------------|
| **Status** | `input_select` | `All`, `Completed`, `Failed`, `Stopped`, `Printing` | `status` |
| **Material** | `input_select` | `All`, + dynamic from fetched data | `filament_type` |
| **Color** | `input_text` + generated buttons | Multi-select color swatches derived from unique `filament_color` values; matches any selected color | `filament_color` (comma-sep hex) |
| **Printer** | `input_select` | `All`, + dynamic from fetched data (printer_id → name) | `printer_id` |
| **Date Range** | `input_select` | `All Time`, `Today`, `This Week`, `This Month`, `Last 30 Days`, `Last 90 Days` | `started_at` |
| **Favorites** | `input_boolean` | `off` = all archives, `on` = favorites only | `is_favorite` |
| **Designer** | `input_select` | `All`, + dynamic unique designers | `designer` |
| **Layer Height** | `input_select` | `All`, + dynamic (e.g., 0.04, 0.08, 0.12, 0.16, 0.20) | `layer_height` |
| **Search** | `input_text` | Free text on `print_name`, `designer`, `tags` | Multiple fields |

> **Color filter note**: The `filament_color` field is a comma-separated hex string (e.g., `#000000,#FFFFFF,#C12E1F`). The live UI exposes these values as clickable color swatches instead of a single dropdown. Multiple swatches can be active at once, and the filter matches any archive that used at least one selected color.

### Sort Options

The Bambuddy API has **no `sort` or `order` query params** (confirmed via OpenAPI spec). All sorting is client-side in the template sensor.

| Sort | Helper Value | Sort Key | Default? |
|------|-------------|----------|----------|
| Date (Newest) | `Date (Newest)` | `started_at` descending | ✅ Yes |
| Date (Oldest) | `Date (Oldest)` | `started_at` ascending | |
| Duration (Longest) | `Duration (Longest)` | `actual_time_seconds` descending | |
| Duration (Shortest) | `Duration (Shortest)` | `actual_time_seconds` ascending | |
| Cost (Highest) | `Cost (Highest)` | `cost` descending | |
| Cost (Lowest) | `Cost (Lowest)` | `cost` ascending | |
| Filament Used (Most) | `Filament (Most)` | `filament_used_grams` descending | |
| Filament Used (Least) | `Filament (Least)` | `filament_used_grams` ascending | |
| Name (A-Z) | `Name (A-Z)` | `print_name` ascending | |
| Name (Z-A) | `Name (Z-A)` | `print_name` ascending reversed | |

### Pagination

| Helper | Type | Purpose | Default |
|--------|------|---------|---------|
| `input_number.print_history_page_size` | input_number | Items per page | 10 (min 5, max 50) |
| `input_number.print_history_current_page` | input_number | Current page (1-indexed) | 1 |

Pagination is computed in the template sensor: the full filtered+sorted list is sliced by `[(page-1)*size : page*size]`.

**Page reset behavior**: When any filter or sort helper changes, an automation resets `print_history_current_page` to 1. This prevents showing an empty page when filters reduce the result set.

### Implemented Color Chip Row

The final working color filter uses a deliberately minimal generated-card structure:

- `custom:auto-entities` generates one built-in `button` card per unique hex color
- the chip action uses `perform-action` to call `script.toggle_print_history_color_filter`
- the active state is rendered with an accent ring in `card_mod`
- the visible chip color is applied through `ha-state-icon { color: <hex> !important; }`
- invalid non-hex values are ignored so placeholder values like `none` do not render as broken cards

This ended up being more reliable than earlier generated `custom:button-card` variants and is now the documented baseline.

### Input Helpers (New)

```yaml
# helpers/input_select/
input_select_print_history_filter_status:
  name: Print History Filter - Status
  options: ["All", "Completed", "Failed", "Stopped", "Printing"]
  initial: "All"
  icon: mdi:list-status

input_select_print_history_filter_material:
  name: Print History Filter - Material
  options: ["All"]  # Populated dynamically
  initial: "All"
  icon: mdi:flask-outline

input_select_print_history_filter_color:
  name: Print History Filter - Color
  options: ["All"]  # Populated dynamically from filament_color hex values
  initial: "All"
  icon: mdi:palette-outline

input_select_print_history_filter_printer:
  name: Print History Filter - Printer
  options: ["All"]  # Populated dynamically
  initial: "All"
  icon: mdi:printer-3d

input_select_print_history_filter_date_range:
  name: Print History Filter - Date Range
  options:
    - "All Time"
    - "Today"
    - "This Week"
    - "This Month"
    - "Last 30 Days"
    - "Last 90 Days"
  initial: "All Time"
  icon: mdi:calendar-range

input_boolean_print_history_filter_favorites_only:
  name: Print History Filter - Favorites Only
  icon: mdi:star

input_select_print_history_filter_designer:
  name: Print History Filter - Designer
  options: ["All"]  # Populated dynamically
  initial: "All"
  icon: mdi:account-outline

input_select_print_history_filter_layer_height:
  name: Print History Filter - Layer Height
  options: ["All"]  # Populated dynamically (e.g., 0.04, 0.08, 0.12, 0.16, 0.20)
  initial: "All"
  icon: mdi:layers-outline

input_select_print_history_sort:
  name: Print History Sort
  options:
    - "Date (Newest)"
    - "Date (Oldest)"
    - "Duration (Longest)"
    - "Duration (Shortest)"
    - "Cost (Highest)"
    - "Cost (Lowest)"
    - "Filament (Most)"
    - "Filament (Least)"
    - "Name (A-Z)"
    - "Name (Z-A)"
  initial: "Date (Newest)"
  icon: mdi:sort

# helpers/input_text/
input_text_print_history_search:
  name: Print History Search
  initial: ""
  max: 100
  icon: mdi:magnify

input_text_print_history_filter_colors:
  name: Print History Filter Colors
  initial: ""
  max: 255
  icon: mdi:palette

# helpers/input_number/
input_number_print_history_page_size:
  name: Print History Page Size
  min: 5
  max: 50
  step: 5
  initial: 10
  mode: slider
  icon: mdi:table-large

input_number_print_history_max_archives:
  name: Print History Max Archives
  min: 50
  max: 2000
  step: 50
  initial: 500
  mode: slider
  icon: mdi:database-cog
```

### Template Sensor: `sensor.print_history_filtered`

Jinja2 template that mirrors the Filament Catalog's `sensor.filament_catalog_filtered_spools` pattern:

```yaml
# template_sensors/print_history_filtered.yaml
- sensor:
    - name: "Print History Filtered"
      unique_id: print_history_filtered
      icon: mdi:filter-variant
      state: >-
        {% set fj = state_attr('sensor.print_history_filtered', 'filtered_count') | default(0) %}
        {{ fj }}
      attributes:
        filtered_count: >-
          {# Computed below — this is the total matching count before paging #}
          {% set raw = state_attr('sensor.print_history_archives', 'archives_json') | default('[]', true) %}
          {% if raw is string %}{% set archives = raw | from_json %}{% else %}{% set archives = raw | default([]) %}{% endif %}
          {%- set filter_status = states('input_select.print_history_filter_status') -%}
          {%- set filter_material = states('input_select.print_history_filter_material') -%}
          {%- set filter_color = states('input_select.print_history_filter_color') -%}
          {%- set filter_printer = states('input_select.print_history_filter_printer') -%}
          {%- set filter_date = states('input_select.print_history_filter_date_range') -%}
          {%- set filter_favorites = states('input_select.print_history_filter_favorites') -%}
          {%- set filter_designer = states('input_select.print_history_filter_designer') -%}
          {%- set filter_layer_height = states('input_select.print_history_filter_layer_height') -%}
          {%- set search_text = states('input_text.print_history_search') | lower | trim -%}
          {%- set now_ts = as_timestamp(now()) | float(0) -%}
          {%- set ns = namespace(matches=[]) -%}
          {%- for a in archives -%}
            {%- set status = a.get('status', '') | lower -%}
            {%- set material = a.get('filament_type', '') -%}
            {%- set colors = a.get('filament_color', '') -%}
            {%- set printer = a.get('printer_id', '') | string -%}
            {%- set name = a.get('print_name', '') | lower -%}
            {%- set designer = a.get('designer', '') -%}
            {%- set lh = a.get('layer_height') -%}
            {%- set is_fav = a.get('is_favorite', false) -%}
            {%- set tags = a.get('tags', '') | lower -%}
            {%- set started_raw = a.get('started_at', '') -%}
            {%- set started_ts = as_timestamp(started_raw, 0) | float(0) if started_raw else 0 -%}
            {%- set days_ago = ((now_ts - started_ts) / 86400) | float(0) if started_ts > 0 else 99999 -%}
            {%- set m_status = filter_status == 'All' or status == filter_status | lower -%}
            {%- set m_material = filter_material == 'All' or material | lower == filter_material | lower -%}
            {%- set m_color = filter_color == 'All' or filter_color in colors -%}
            {%- set m_printer = filter_printer == 'All' or printer == filter_printer -%}
            {%- set m_favorites = filter_favorites == 'All' or (filter_favorites == 'Favorites Only' and is_fav) -%}
            {%- set m_designer = filter_designer == 'All' or designer | lower == filter_designer | lower -%}
            {%- set m_layer_height = filter_layer_height == 'All' or (lh | string == filter_layer_height) -%}
            {%- set search_blob = (name ~ ' ' ~ designer ~ ' ' ~ tags) | lower -%}
            {%- set m_search = search_text == '' or search_text in search_blob -%}
            {%- if filter_date == 'Today' -%}
              {%- set m_date = days_ago < 1 -%}
            {%- elif filter_date == 'This Week' -%}
              {%- set m_date = days_ago < 7 -%}
            {%- elif filter_date == 'This Month' -%}
              {%- set m_date = days_ago < 30 -%}
            {%- elif filter_date == 'Last 30 Days' -%}
              {%- set m_date = days_ago < 30 -%}
            {%- elif filter_date == 'Last 90 Days' -%}
              {%- set m_date = days_ago < 90 -%}
            {%- else -%}
              {%- set m_date = true -%}
            {%- endif -%}
            {%- if m_status and m_material and m_color and m_printer and m_search and m_date and m_favorites and m_designer and m_layer_height -%}
              {%- set ns.matches = ns.matches + [a] -%}
            {%- endif -%}
          {%- endfor -%}
          {{ ns.matches | length }}
        # ... (full sort + page logic shown in detailed template below)
        page_json: >-
          {# Full implementation in the detailed section below #}
          ...
        total_pages: >-
          ...
        page_info: >-
          ...
        active_filters: >-
          ...
```

> The full Jinja2 template is lengthy. See [Detailed Template Sensor Logic](#detailed-template-sensor-logic) below for the complete implementation.

### Dynamic Filter Option Sync

Like the Filament Catalog, filter dropdown options should be dynamically populated from the actual data.

**Automation: `print_history_sync_filter_options`**

Triggers:
1. `sensor.print_history_archives` state change — fires when new data is fetched
2. `homeassistant.start` — with 3-minute delay (after trigger-based sensor has fetched)

Behavior:
- Reads `archives_json` attribute from `sensor.print_history_archives`
- Collects unique `filament_type` values → updates `input_select.print_history_filter_material`
- Collects unique hex colors from `filament_color` (splits comma-separated strings) → exposes them as the always-visible multi-select color-chip row
- Collects unique `printer_id` values (mapped to names if available) → updates `input_select.print_history_filter_printer`
- Collects unique `designer` values (non-empty) → updates `input_select.print_history_filter_designer`
- Collects unique `layer_height` values (formatted as strings) → updates `input_select.print_history_filter_layer_height`
- Prepends `All` to each list
- If current selection not in new list → HA resets the relevant helper to its default value

This mirrors the Filament Catalog's `sync_filter_options.yaml` pattern exactly.

### Page Reset Automation

**Automation: `print_history_reset_page_on_filter_change`**

Triggers:
- State change on any filter `input_select` or `input_text.print_history_search`

Action:
- Set `input_number.print_history_current_page` to 1

---

## Layer 3: Dashboard UI

### Browser Header

The Print History view now uses an always-visible header modeled after the Filament Catalog control pattern.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [ Search Prints........................ ] [Matches] [Open Bambuddy] [⚙]     │
│ [Status] [Material] [Printer] [Date]                                      │
│ [Designer] [Layer Height] [Favorites Only] [Sort]                          │
│ [Items Per Page Slider] [Compact] [Media] [Detail] [Refresh]               │
│ [Clear] [Refresh]                                                          │
│ Color Filters: All Colors or #FFFFFF • #000000                             │
│ [●] [●] [●] [●] [●] ... multi-select color chips                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

#### Header Responsibilities

| Control | Purpose | Notes |
|---------|---------|-------|
| `Search Prints` | Free-text search over name, designer, tags | Styled the same way as the catalog search field |
| `Matches` | Show the current filtered result count | Always visible near the search box |
| `Open Bambuddy` | Jump directly to Bambuddy's archive UI | Replaces the old large `Recent Prints` header card |
| `Settings` | Open only capture/history settings | Kept top-right; browsing controls stay on-page |
| Filter pills | Status/material/printer/date/designer/layer-height | Rounded cards with current value and active-state indicator |
| `Favorites Only` | Toggle favorites-only filtering | Boolean button rather than a dropdown |
| Layout toggles | Switch between `Compact`, `Media`, and `Detail` | Only one is active at a time |
| Items-per-page slider | Adjust page density without opening a popup | Mirrors the Filament Catalog threshold-slider pattern |
| `Clear` / `Refresh` | Reset active filters or refresh the cache | `Clear` is visually accented whenever any filter is active |
| Color chips | Multi-select filament-color filter | Clicking a swatch toggles it in the active filter set |

#### Settings Popup Scope

Only the capture/history settings remain in a popup:

1. Capture-stage toggles
2. Mid-print capture percentage
3. Secondary camera selection
4. History fetch enablement / cache size
5. Photo review timeout

### Archive Record Card Variants

The same filtered dataset is renderable in three presentation modes, but all three now share the same responsive full-width card grid.

| Variant | Best Use | Visual Characteristics |
|---------|----------|------------------------|
| `Compact` | Fast scanning, desktop/mobile browsing | Smaller hero image with compact KPI blocks and chips |
| `Media` | Visual browsing, choosing best print/photo | Large photo-first card with emphasis on image and result |
| `Detail` | Desktop inspection, troubleshooting, comparing runs | Richer metadata, tags, and failure details surfaced inline |

#### Variant Rules

- Prefer archive cover photo when available; fall back to the Bambuddy thumbnail endpoint.
- Keep action affordances consistent across variants so changing layout does not change behavior.
- The `Media` card should be allowed to use a noticeably larger image region than the compact row.
- Every variant should render inside the same two-column desktop grid and collapse to one column on narrow/mobile screens.
- Cards should use the full page width of a `panel: true` Lovelace view rather than a constrained section column.

### Planned Archive Detail Popup

Archive cards are now structured so a future tap action can open an archive-detail popup. That popup is intentionally not implemented yet, but the planned content should include:

1. Header with print name, result badge, date, printer, and favorite state
2. Large cover image / thumbnail with quick links back to Bambuddy
3. Print stats: planned vs actual duration, grams used, cost, quantity, layer height, nozzle size
4. Filament breakdown with color swatches and per-color usage when available
5. Designer / MakerWorld metadata and tags
6. Failure reason or stop context when the archive did not complete successfully
7. Future actions area for compare, favorite toggle, reprint, and archive diagnostics

### History Table Card

The live `print_history.yaml` renderer reads from `sensor.print_history_page_archives` and renders responsive archive cards rather than a single-column table. The page sensor still provides the already-filtered, already-sorted current slice, so the frontend only handles layout.

### Pagination Controls

```
┌──────────────────────────────────────────────────────────────────┐
│ [⏮] [◀] [Page 1 of 5] [▶] [⏭]                                   │
└──────────────────────────────────────────────────────────────────┘
```

| Control | Implementation |
|---------|----------------|
| First / Prev / Next / Last | `script.navigate_history` with `direction=first|prev|next|last` |
| Page info | `sensor.print_history_page_info` |
| Page size slider | Lives in the browser header, always visible |
| Refresh | `script.refresh_print_history_archives` |

**Pagination is instant** — changing the page helper triggers the template sensor to re-evaluate, slicing a different window of the already-filtered+sorted data. No API call needed. The pager appears both above and below the archive grid.

---

## Performance Analysis

### The "Pull All Data" Question

> *"Does this only work if we somehow pull ALL data (not paged)? Is that a concern?"*

**Short answer**: You don't need ALL data. A reasonable cap (default 500) works well. The projection step makes the full endpoint viable.

### Data Size Estimates (After Projection)

| Archive Count | API Response | Projected JSON | Template Eval (L1) | Template Eval (L2) | Practical? |
|---------------|-------------|---------------|---------------------|---------------------|------------|
| 50 | ~500 KB | ~22 KB | ~0.2s | <0.1s | ✅ Trivial |
| 200 | ~2 MB | ~90 KB | ~0.5s | ~0.2s | ✅ Comfortable |
| 500 | ~5 MB | ~225 KB | ~1s | ~0.5s | ✅ Good default |
| 1,000 | ~10 MB | ~450 KB | ~2-3s | ~1s | ⚠️ Noticeable on fetch |
| 2,000 | ~20 MB | ~900 KB | ~5-8s | ~2-3s | ⚠️ Sluggish |

*L1 = projection loop (runs on fetch events, ~every 5 min). L2 = filter/sort/page (runs on every helper change, but operates on already-projected data).*

**Key insight**: L1 projection is the heavier step but runs infrequently (fetch events). L2 filtering operates on the trimmed data and is fast even at 500 items. Filter/sort/page changes feel instant because they don't re-fetch.

### Why 500 Is the Right Default

- **2 prints/day × 250 days = 500** — covers ~8 months for active users
- **API response at 500**: ~5 MB (full JSON with `extra_data`). Fetched once, projected to ~225 KB, and stored. The 5 MB is transient (in Jinja2 variable during render), not persisted.
- **Projected data size**: ~225 KB is well within HA's state machine capacity
- **L2 template speed**: Iterating 500 flat dicts with ~5 filter checks each ≈ Filament Catalog's 165 entities with ~15 attribute lookups
- **Recorder optimization**: Exclude `archives_json` attribute from the recorder:
  ```yaml
  recorder:
    exclude:
      entity_globs:
        - sensor.print_history_archives
  ```

### How the Architecture Mitigates Scale

| Concern | Mitigation |
|---------|------------|
| **Large API response** | Transient — held in Jinja2 variable during projection, then discarded. Only the trimmed ~225 KB is stored as an attribute. |
| **Too much API data** | `input_number.print_history_max_archives` caps the `?limit=` param (default 500, max 2000) |
| **Slow L1 projection** | Runs only on trigger events (~5-min interval + webhooks), NOT on filter changes |
| **Slow L2 filtering** | Operates on projected data (~450 bytes/item). Date Range filter applied early to reduce working set. |
| **Large attribute in recorder** | Exclude `sensor.print_history_archives` from recorder |
| **5-minute polling for stale data** | Webhook triggers (`print_complete`, `print_failed`) refresh immediately on events that matter |
| **Very large histories** | Users with 2000+ archives should use date range filters or the Bambuddy web UI for deep history |

### Alternative: API-Side Pre-Filtering (Considered & Deferred)

The Bambuddy API supports `?status=X&printer_id=Y&search=Q` server-side. We COULD push filters to the API level:

```
GET /archives/?limit=500&status=completed&printer_id=1&search=benchy
```

**Pros**: Much smaller response, faster template evaluation.
**Cons**:
- Every filter change requires a new API call (latency + rate limits)
- Can't do instant client-side sort or page navigation
- Filter UX feels sluggish (API round-trip on each dropdown change)
- More complex implementation (REST command params change dynamically)

**Verdict**: Start with the client-side approach (pull 500, project, filter in template). If users report scale issues at 1000+ archives, add an optional "server-side mode" that pushes status + date range filters to the API as query params. This is an optimization, not a requirement.

### Alternative: Hybrid API Pre-Filter + Client Sort (Future Optimization)

If scale becomes an issue, the architecture supports a middle ground:

1. API pre-filters by **date range** (reduces dataset the most, e.g., "Last 30 Days" → ~60 archives)
2. Client-side handles **status**, **material**, **color**, **search**, **sort**, **page**

This would require switching from trigger-based template to a script + REST command flow where filter changes trigger an API re-fetch. The downside is that filter changes are no longer instant. This can be added later without changing the dashboard or filter helpers — only the data fetch layer changes.

### Activity Heatmap Metric Semantics

The shipped activity heatmap uses these metric definitions:

- **Print Count**: one per archive row after filters are applied
- **Number of Printed Objects**: sum of projected `object_count` values from the Bambuddy archive payload
- **Filaments Used**: sum of distinct populated `filament_slots` per archive, intended as a usage/activity signal rather than a unique-filament-in-history count

This keeps the browser and heatmap aligned on the same projected Layer 1 data contract and avoids deriving object totals from fallback printable-object blobs.

### Deferred: Backend-Only Heatmap Filtering / Single Source of Truth

The idea of moving all heatmap filtering out of the browser card and into Layer 2 was analyzed and intentionally deferred.

**Why it was deferred:**

- The activity heatmap currently consumes the full projected archive cache from `sensor.print_history_archives`
- The existing Layer 2 payload is page-oriented and optimized for the archive browser, not full-scope activity aggregation
- Reusing the paged Layer 2 payload for the heatmap would either truncate activity totals or force Layer 2 to mix two different concerns into one payload

**Future-safe direction:**

- Keep the current browser-first heatmap implementation for now
- If a stricter backend single source of truth is needed later, add a dedicated full-scope activity payload such as `activity_scope_json` or `activity_days_json`
- Have the heatmap read that dedicated activity payload instead of reconstructing its own filtered working set from page-oriented data

That future refactor is an architectural cleanup and consistency improvement, not a correctness blocker for the current implementation.

---

## Updated Package Structure

New and modified files (additions to existing `print_history/` package):

```
homeassistant/packages/3d_printing/print_history/
├── rest_commands/
│   ├── (existing files...)
│   └── bambuddy_fetch_archives.yaml             # NEW — GET /archives for bulk fetch
├── template_sensors/
│   ├── (existing files...)
│   ├── print_history_archives.yaml               # NEW — trigger-based, fetch + project + store
│   └── print_history_filtered.yaml               # NEW — filter/sort/page sensor
├── helpers/
│   ├── input_select/
│   │   ├── (existing files...)
│   │   ├── input_select_print_history_filter_status.yaml        # NEW
│   │   ├── input_select_print_history_filter_material.yaml      # NEW
│   │   ├── input_select_print_history_filter_printer.yaml       # NEW
│   │   ├── input_select_print_history_filter_date_range.yaml    # NEW
│   │   ├── input_select_print_history_filter_designer.yaml      # NEW
│   │   ├── input_select_print_history_filter_layer_height.yaml  # NEW
│   │   ├── input_select_print_history_sort.yaml                 # NEW
│   │   └── input_select_print_history_card_variant.yaml         # NEW
│   ├── input_boolean/
│   │   ├── (existing files...)
│   │   └── input_boolean_print_history_filter_favorites_only.yaml # NEW
│   ├── input_text/
│   │   ├── (existing files...)
│   │   ├── input_text_print_history_filter_colors.yaml          # NEW
│   │   └── input_text_print_history_search.yaml                 # NEW
│   └── input_number/
│       ├── (existing files...)
│       ├── input_number_print_history_page_size.yaml            # NEW
│       └── input_number_print_history_max_archives.yaml         # NEW
├── automations/
│   ├── (existing files...)
│   ├── print_history_sync_filter_options.yaml    # NEW — dynamic dropdown population
│   └── print_history_reset_page_on_filter.yaml   # NEW — reset to page 1 on filter change
├── scripts/
│   ├── (existing files...)
│   ├── print_history_clear_filters.yaml          # NEW — reset all filters to defaults
│   └── toggle_print_history_color_filter.yaml    # NEW — add/remove selected color chips
├── dashboard_cards/
│   ├── (existing files...)
│   ├── print_history_browser.yaml                # NEW — always-visible browser header
│   ├── print_history_pagination.yaml             # NEW — reusable top/bottom pager
│   └── print_history_archive_records.yaml        # NEW — variant-aware archive record renderer
└── dashboard_views/
  └── view_print_history.yaml                   # MODIFIED — switch to panel layout with top/bottom pagers
```

### Loader Updates

The existing `print_history_loader.yaml` already uses `!include_dir_merge_list` and `!include_dir_merge_named` for all domains. New files in existing directories are **auto-discovered** — no loader changes needed.

---

## Entity Reference (New Entities)

### Template Sensors

| Entity | Type | State | Key Attributes |
|--------|------|-------|----------------|
| `sensor.print_history_archives` | trigger template | Archive count (e.g., "487") | `archives_json` (full JSON array), `last_fetch` (ISO timestamp) |
| `sensor.print_history_filtered` | template | Filtered count (e.g., "47") | `page_json` (current page array), `total_pages`, `page_info`, `active_filters` |

### Helpers

| Entity | Type | Default |
|--------|------|---------|
| `input_select.print_history_filter_status` | input_select | `All` |
| `input_select.print_history_filter_material` | input_select | `All` (dynamic) |
| `input_select.print_history_filter_printer` | input_select | `All` (dynamic) |
| `input_select.print_history_filter_date_range` | input_select | `All Time` |
| `input_select.print_history_filter_designer` | input_select | `All` (dynamic) |
| `input_select.print_history_filter_layer_height` | input_select | `All` (dynamic) |
| `input_select.print_history_sort` | input_select | `Date (Newest)` |
| `input_select.print_history_card_variant` | input_select | `Media` |
| `input_boolean.print_history_filter_favorites_only` | input_boolean | `off` |
| `input_text.print_history_search` | input_text | `""` |
| `input_text.print_history_filter_colors` | input_text | `""` |
| `input_number.print_history_page_size` | input_number | 10 |
| `input_number.print_history_max_archives` | input_number | 500 |

### Automations

| ID | Trigger | Action |
|---|---|---|
| `print_history_sync_filter_options` | `sensor.print_history_archives` state change | Populate material + printer dropdown options from data |
| `print_history_reset_page_on_filter` | Any filter/sort/search helper state change | Set `print_history_current_page` → 1 |

### Scripts

| Script | Purpose |
|--------|---------|
| `script.print_history_clear_filters` | Reset all filter/sort/search helpers to defaults |

---

## Existing Entity Changes

### Potentially Removable (Post-Migration)

| Entity | Current Purpose | Replaced By |
|--------|----------------|-------------|
| `input_number.bambuddy_history_limit` | REST sensor `?limit=` param | `input_number.print_history_max_archives` |
| `sensor.print_history_page_archives` | Current visible page slice | Dashboard card entity |
| `script.load_history_page` | REST command pagination | Template sensor paging (no script needed) |
| `script.navigate_history` | Prev/next REST calls | Direct `input_number.set_value` on page helper |
| `sensor.print_history_page_info` | Page display string | `sensor.print_history_filtered` attr `page_info` |

These can be removed in a cleanup phase after the new filter system is validated.

### Kept As-Is

| Entity | Reason |
|--------|--------|
| `sensor.bambuddy_print_history` (REST) | Powers `sensor.bambuddy_last_print_*` quick-glance sensors |
| All `sensor.bambuddy_last_print_*` | Used by automations and other dashboard tiles |
| All photo capture / enrichment entities | Independent subsystems, unaffected |

---

## Detailed Template Sensor Logic

### `sensor.print_history_filtered` — Full Jinja2

The template sensor logic follows the same pattern as `sensor.filament_catalog_filtered_spools`:

1. Read raw data from Layer 1 sensor attribute
2. Read all filter helper states
3. Iterate archives, apply filters
4. Sort matching archives
5. Slice to current page
6. Output as JSON attributes

```jinja2
{# ── Read raw data ──────────────────────────────────────────── #}
{% set raw = state_attr('sensor.print_history_archives', 'archives_json')
     | default('[]', true) %}
{% if raw is string %}
  {% set archives = raw | from_json %}
{% elif raw is iterable %}
  {% set archives = raw | list %}
{% else %}
  {% set archives = [] %}
{% endif %}

{# ── Read filter helpers ────────────────────────────────────── #}
{% set filter_status = states('input_select.print_history_filter_status') %}
{% set filter_material = states('input_select.print_history_filter_material') %}
{% set filter_color = states('input_select.print_history_filter_color') %}
{% set filter_printer = states('input_select.print_history_filter_printer') %}
{% set filter_date = states('input_select.print_history_filter_date_range') %}
{% set filter_favorites = states('input_select.print_history_filter_favorites') %}
{% set filter_designer = states('input_select.print_history_filter_designer') %}
{% set filter_layer_height = states('input_select.print_history_filter_layer_height') %}
{% set search_text = states('input_text.print_history_search') | lower | trim %}
{% set sort_option = states('input_select.print_history_sort')
     | default('Date (Newest)', true) %}
{% set page_size = states('input_number.print_history_page_size') | int(10) %}
{% set current_page = states('input_number.print_history_current_page') | int(1) %}
{% set now_ts = as_timestamp(now()) | float(0) %}

{# ── Date range thresholds ──────────────────────────────────── #}
{% if filter_date == 'Today' %}
  {% set max_days = 1 %}
{% elif filter_date in ['This Week'] %}
  {% set max_days = 7 %}
{% elif filter_date in ['This Month', 'Last 30 Days'] %}
  {% set max_days = 30 %}
{% elif filter_date == 'Last 90 Days' %}
  {% set max_days = 90 %}
{% else %}
  {% set max_days = 999999 %}
{% endif %}

{# ── Filter pass ────────────────────────────────────────────── #}
{% set ns = namespace(matches=[]) %}
{% for a in archives %}
  {% set a_status = a.get('status', '') | lower %}
  {% set a_material = a.get('filament_type', '') %}
  {% set a_printer = a.get('printer_id', '') | string %}
  {% set a_name = a.get('print_name', '') | lower %}
  {% set a_started = a.get('started_at', '') %}
  {% set a_ts = as_timestamp(a_started, 0) | float(0) if a_started else 0 %}
  {% set a_days = ((now_ts - a_ts) / 86400) | float(0) if a_ts > 0 else 999999 %}

  {% set m_status = filter_status == 'All' or a_status == filter_status | lower %}
  {% set m_material = filter_material == 'All' or a_material | lower == filter_material | lower %}
  {% set m_printer = filter_printer == 'All' or a_printer == filter_printer %}
  {% set m_search = search_text == '' or search_text in a_name %}
  {% set m_date = a_days <= max_days %}

  {% if m_status and m_material and m_printer and m_search and m_date %}
    {# Build sort key based on sort_option #}
    {% if sort_option in ['Date (Newest)', 'Date (Oldest)'] %}
      {% set sk = a_ts %}
    {% elif sort_option in ['Duration (Longest)', 'Duration (Shortest)'] %}
      {% set sk = a.get('actual_time_seconds', 0) | float(0) %}
    {% elif sort_option in ['Cost (Highest)', 'Cost (Lowest)'] %}
      {% set sk = a.get('cost', 0) | float(0) %}
    {% elif sort_option in ['Filament (Most)', 'Filament (Least)'] %}
      {% set sk = a.get('filament_used_grams', 0) | float(0) %}
    {% elif sort_option in ['Name (A-Z)', 'Name (Z-A)'] %}
      {% set sk = a_name %}
    {% else %}
      {% set sk = a_ts %}
    {% endif %}
    {% set ns.matches = ns.matches + [dict(archive=a, sk=sk)] %}
  {% endif %}
{% endfor %}

{# ── Sort pass ──────────────────────────────────────────────── #}
{% set sort_desc = sort_option in [
  'Date (Newest)', 'Duration (Longest)', 'Cost (Highest)',
  'Filament (Most)', 'Name (Z-A)'] %}
{% set sorted_items = ns.matches | sort(attribute='sk', reverse=sort_desc) %}

{# ── Pagination ─────────────────────────────────────────────── #}
{% set total = sorted_items | length %}
{% set total_pages = ((total / page_size) | round(0, 'ceil')) | int %}
{% set total_pages = [total_pages, 1] | max %}
{% set safe_page = [[current_page, 1] | max, total_pages] | min %}
{% set offset = (safe_page - 1) * page_size %}
{% set page_items = sorted_items[offset:offset + page_size] %}

{# ── Output ─────────────────────────────────────────────────── #}
{# page_json: array of archive objects for current page #}
{% set page_archives = page_items | map(attribute='archive') | list %}
{{ page_archives | tojson }}
```

This pseudocode shows the structure. Each output attribute (`page_json`, `filtered_count`, `total_pages`, `page_info`, `active_filters`) follows this logic in separate attribute templates within the sensor definition.

---

## Browser Layout Wireframe

```
┌──────────────────────────────────────────────────────────────────────┐
│ ┌──────────── Browser Header ──────────────────────────────────────┐ │
│ │ Open Bambuddy  Settings                                          │ │
│ │ Status  Material  Printer  Date                                  │ │
│ │ Designer  Layer Height  Favorites  Sort                          │ │
│ │ Search  47 matches  Clear actions                                │ │
│ │ Multi-select color chips                                         │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│ ┌──────────── Top Control Strip ───────────────────────────────────┐ │
│ │ ⏮ ◀  1 of 5  Prints / Page  Compact  Media  Detail  🔄  ▶ ⏭     │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│ ┌─────────────────────── Print History Browser ───────────────────┐ │
│ │ [Media card] Hueforge BTTF                                     │ │
│ │ [larger image / cover photo]                                   │ │
│ │ Mar 28 · est 4.3h · 0.08mm · PLA · 44.8g · ★ printing         │ │
│ ├─────────────────────────────────────────────────────────────────┤ │
│ │ [Compact row] Darth Vader Saber P2 · PLA · 69.3g · ✅         │ │
│ ├─────────────────────────────────────────────────────────────────┤ │
│ │ [Detail card] Magnetic Frame P12                               │ │
│ │ Mar 28 · 1.8h · 0.08mm · tags · designer · failure detail      │ │
│ ├─────────────────────────────────────────────────────────────────┤ │
│ │ ...                                                             │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│ ┌─────────── Repeated Bottom Control Strip ───────────────────────┐ │
│ │ ⏮ ◀  1 of 5  Prints / Page  Compact  Media  Detail  🔄  ▶ ⏭     │ │
│ └───────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### Implementation Details

The browser entry surface now uses a permanently visible browser header plus a separate reusable control strip. Search, matches, settings, filter pills, clear actions, and the multi-select color chips live in the header; page navigation, page-size, layout toggles, and refresh live in `print_history_top_controls.yaml` and are rendered above and below the archive grid.

```yaml
# dashboard_cards/print_history_browser.yaml
type: vertical-stack
cards:
  - Open Bambuddy + settings
  - rounded filter pills
  - search + matches + clear actions
  - multi-select color chips

# dashboard_cards/print_history_top_controls.yaml
type: custom:config-template-card
card:
  - page navigation
  - page-size slider
  - Compact / Media / Detail toggles
  - refresh action
```

---

## Comparison: Filament Catalog vs Print History Filter

| Aspect | Filament Catalog | Print History |
|--------|-----------------|---------------|
| **Data source** | HA entity states (`sensor.spoolman_spool_*`) | External API → projected JSON attribute |
| **Data volume** | ~165 entities (fixed) | 50–2000 archives (growing) |
| **Data fetch** | Always in HA (Spoolman integration) | Trigger-based fetch with `rest_command` action + Jinja2 field projection |
| **Filter sensor** | `sensor.filament_catalog_filtered_spools` | `sensor.print_history_filtered` |
| **Filter inputs** | 12 input_selects + 1 input_text + 4 input_booleans + 3 input_numbers | 8 input_selects + 2 input_texts + 1 input_boolean + 2 input_numbers |
| **Grouping/tabs** | Yes (By Location, By Material, etc.) | No (flat list with sort) |
| **Sort** | 9 options (name, weight, cost, hue, etc.) | 10 options (date, duration, cost, filament, name) |
| **Pagination** | No (all shown, relies on auto-entities) | Yes (page_size + current_page) |
| **Primary browser controls** | `catalog_filter_bar.yaml` | `print_history_browser.yaml` |
| **Controls style** | expanded `bubble-card` sub-buttons | always-visible rounded control header with search, pills, and color chips |
| **Dynamic options** | `sync_filter_options` automation | `print_history_sync_filter_options` automation |
| **Clear filters** | `script.filament_catalog_clear_filters` | `script.clear_print_history_filters` |
| **Scale concern** | 165 is comfortable, >300 would need paging | 500 default cap, configurable to 2000 |

---

## Open Items

| # | Item | Impact | Blocking? |
|---|---|---|---|
| 1 | Verify `GET /archives/` response shape matches projection expectations | Ensure `extra_data.filament_slots` path is correct, and all projected fields exist | Yes — test against Bambuddy API |
| 2 | Verify trigger-based template sensor `action` + `rest_command` response handling works as designed | Core architecture dependency (HA 2024.11+ feature) | Yes — test on live HA instance |
| 3 | Determine if `GET /archives/` supports `?status=X` or `?printer_id=Y` for future API-side pre-filtering | Could enable hybrid mode at scale | No — client-side filtering works regardless |
| 4 | Recorder exclusion for `sensor.print_history_archives` | Large `archives_json` attribute shouldn't bloat the database | No — add to recorder config during implementation |
| 5 | Printer ID → name mapping | `printer_id` is an integer; need friendly name for dropdown display. May require a separate API call or helper mapping. | No — can use printer_id as display initially |
| 6 | Search: `input_text` vs API-side FTS | `GET /search?q=...` provides full-text search. Worth using for large datasets instead of Jinja2 string matching. | No — Jinja2 `in` operator is sufficient for <500 items |
| 7 | Decide whether archive cards stay display-only or gain a detail popup | Governs how favorites/compare/actions land without overloading the card surface | No — current browser already works without it |

---

## Implementation Phases

This feature can be added incrementally within the existing print_history package:

### Phase A: Data Layer (REST command + trigger template sensor)
- Create `bambuddy_fetch_archives` REST command
- Create `print_history_archives` trigger-based template sensor
- Verify data fetch and attribute storage
- Add recorder exclusion

### Phase B: Filter Helpers + Template Sensor
- Create all `input_select`, `input_text`, `input_number` helpers
- Create `print_history_filtered` template sensor
- Create `sync_filter_options` automation
- Create `reset_page_on_filter` automation
- Create `clear_filters` script
- Add `input_select.print_history_card_variant` for persisted layout choice

### Phase C: Dashboard Integration
- Create `print_history_browser.yaml` as the always-visible header surface
- Create `print_history_top_controls.yaml` as the reusable top/bottom control strip
- Update `view_print_history.yaml` to use a full-width panel layout with the header, control strip, archive grid, and repeated bottom controls
- Update history record rendering to read from `sensor.print_history_page_archives` and branch by card variant
- Add the multi-select color-chip row and layout toggle controls

Status: implemented baseline. Remaining dashboard work is mostly archive-detail drilldown and visual refinements rather than core browser plumbing.

### Phase D: Cleanup
- Remove dead compatibility artifacts only after confirming no external dashboards or scripts depend on them
- Consolidate `bambuddy_history_limit` → `print_history_max_archives`
- Update README.md entity reference
