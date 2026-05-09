# Model Catalog — Card Design (Compact / List / Media)

> **Status:** Hi-fidelity design proposal.
> **Scope:** Catalog Browser cards rendered by [model-catalog-browser-card.js](../../../../homeassistant/www/3d_printing/model_catalog/model-catalog-browser-card.js) for the three view modes the card already exposes (`compact`, `list`, `media`). This document supersedes the rough card sketches in [ux-concepts-and-mockups.md](../ux-concepts-and-mockups.md), which is retained as the low-fidelity index covering surrounding surfaces (Working Board, filter trays, etc.).
> **Companion HTML mockups (Hi-Res, browser-viewable, fully self-contained):**
> - [mockups/toolbar.html](mockups/toolbar.html) — toolbar/header patterns including scope toggle
> - [mockups/compact.html](mockups/compact.html) — primary focus
> - [mockups/list.html](mockups/list.html)
> - [mockups/media.html](mockups/media.html)
> - [mockups/collections.html](mockups/collections.html) — collections browse mode and hierarchy patterns
> - [mockups/index.html](mockups/index.html) — landing page that cross-links them all

---

## 1. Design approach

The Catalog has three jobs that the cards must each serve at the same density they're tuned for:

1. **Recognize the model fast** — primary photo, name, badge of origin (custom unique vs remix vs derivative), source platform, publish destinations.
2. **Decide whether to act on it now** — queue state, recent/frequent/common signals, filament-fit hints, archive count (have I printed this already, and how recently?).
3. **Act without leaving the card** — Open detail, Queue/Dequeue, Send to slicer, Open in publish destination — all reachable from the card surface without a second click into a popup.

The proposal layers those jobs across the three view modes so each card type has a single dominant job:

| View | Dominant job | Density | Default desktop columns |
| --- | --- | --- | --- |
| **Compact** | Recognise + decide (high-volume browsing) | Information-dense | **3 columns ≥ 1280 px**, 2 columns 880–1279 px, 1 column < 880 px |
| **Media** | Recognise (visual triage) | Photo-led | **3 columns ≥ ~1000 px**, 2 columns ~660–999 px, 1 column < 660 px (auto-fit `minmax(320px, 1fr)`, parity with Print History media) |
| **List** | Decide + scan against metric columns | Tabular density | Single column, full-width row |

Print History is the closest reference inside the repo. The proposal **borrows its visual grammar** (rounded `ha-card` shells, dark translucent surfaces, pill-status chips, dot-style filament swatches with hover tooltips, action-row at the bottom of the content column) so a user moving between Print History and Model Catalog feels continuity. It **diverges** wherever a Print History pattern doesn't fit a model:

- Print History keys off a single archive run; the catalog card keys off a "model with N archives", so the prominent metric block becomes **Archives count + last printed**, not duration/filament/cost from a single run.
- Print History uses status pills (`Completed`, `Failed`, …) tied to the run outcome. The catalog uses **provenance pills** (`Custom unique`, `Remix`, `Derivative`) plus a **source chip** (`Source: MakerWorld`, `Source: Printables`, `Source: Local Original`) and **publish destination chips** (`MakerWorld`, `Printables`, `Manyfold`).
- Print History's left rail "role emblem" is repurposed as a **queue-state ribbon** on the catalog card so the queue is always visible at a glance.

---

## 2. Schema parity & proposed new fields

### 2.1 Fields the cards consume today

These come straight from the existing browser endpoint backing [model-catalog-browser-card.js](../../../../homeassistant/www/3d_printing/model_catalog/model-catalog-browser-card.js). The cards use the same identifiers:

- `model_ref` (stable identifier; queue + media-index keys hash off this)
- `name`, `designer`
- `primary_photo` / `thumbnail_path`, `photos[]` (drives the media gallery in `media` mode — the existing `_setModelMediaIndex` carousel still applies)
- `collection`
- `tags[]`
- `origin_type` — one of `custom_unique`, `remix`, `derivative`
- `source_platform` — canonical source platform ID (`makerworld`, `printables`, `thingiverse`, `cults3d`, `manyfold`, `other`, `original_local`)
- `source_download_url` — optional original source URL shown in detail popup and used for click-through from source chip when available
- `published_to[]` — array of `{ destination_id, destination_label, url }` (e.g. `makerworld`, `printables`, `manyfold`)
- `archives_count`
- `to_print_status` — one of `none`, `queued`, `printing`, `done` (drives the queue chip and queue actions handled by the card's `queue-*` action dispatcher)
- `recent`, `frequent`, `common` — boolean signals already exposed by the browser
- `last_printed_at`
- `working_state` — `draft`, `in_progress`, `ready_to_publish` (Working Board surface)

### 2.2 Proposed additions ⚠️ *requires backend*

Each new field below is **opt-in for the card**; the design degrades cleanly when a field is absent.

| Field | Where it's used | Why | Backend touch point |
| --- | --- | --- | --- |
| `success_rate_pct` ⚠️ requires backend | Compact + List metric block; tooltip in Media | Closes the "have I been able to print this reliably?" question without opening detail. Print History already calculates per-archive outcomes; aggregate over `model_ref`. | Layer 2 projection (sidecar) joins archives by `model_ref`; do not push into Layer 1 (`sensor.print_history_archives`). |
| `last_outcome` (`completed`/`failed`/`cancelled`) ⚠️ requires backend | Compact corner badge; List status column | Lets the user see if the most recent attempt failed before queueing again. | Same Layer 2 join. |
| `total_filament_grams_used` ⚠️ requires backend | Compact metric block; List | Fits the "decide" job (have I burned a roll on this already?). | Sum across archives; cache. |
| `primary_filament_palette[]` (hex array) ⚠️ requires backend | Compact + Media swatches | Catalog currently has no first-class color metadata; Print History derives from enrichment. Promoting the palette to the model gives the catalog card a visual swatch row that matches Print History. | Layer 2: most-recent or canonical-archive palette per model; do not embed in Layer 1. |
| `file_kinds` (counts of `3mf` / `gcode.3mf` / `stl` / `step` / `image`) ⚠️ requires backend | Compact bottom strip; List | The catalog represents grouped files; surface "what's in here" without opening the file explorer. Mirrors Manyfold's per-format chip row. | Computed from existing working-files explorer payload. |
| `dimensions_mm` (`{x,y,z}`) ⚠️ requires backend | Compact tooltip; List secondary | Quick fit-on-plate sanity. | Read from canonical 3MF metadata when present. |
| `notes_excerpt` (first 140 chars of long notes) ⚠️ requires backend | Compact 1-line under tags; Media body | Surfaces hand-curated context (Manyfold uses notes prominently). | Truncate server-side to keep payload small. |
| `is_favorite` (already exists in Print History world) — confirm parity | Star toggle on all three views | Print History uses a star tap target; catalog card should match. | Use existing favorites store keyed by `model_ref`. |

### 2.3 Layering guardrail (repo policy)

Per [the repo Copilot guidance](../../../../.github/copilot-instructions.md), all of the proposed Layer-2 additions **must not** balloon Layer 1 (`sensor.print_history_archives`). Filament palette promotion in particular is the kind of view-facing transformation the guardrail explicitly calls out — derive in Layer 2 from existing enrichment payloads.

---

## 3. Component anatomy

All three view modes share the same building blocks, sized differently:

```
┌─ ha-card (cursor:pointer — click opens model detail popup) ───────────────┐
│  [QUEUE RIBBON]  [PRIMARY MEDIA]   [CIRCLE BUTTONS: Viewer · ★ · ⋯]      │
│                                    [HEADER: NAME · DESIGNER · DATE]       │
│                                    [PROVENANCE + SOURCE + PUBLISH CHIPS]  │
│                                    [SIGNAL CHIPS: recent/frequent/common] │
│                                    [METRIC BLOCK: archives · last · …]    │
│                                    [FILAMENT SWATCHES]  [FILE-KIND CHIPS] │
│                                    [TAGS]                                  │
│                                    [ACTION ROW: Open · Queue · Slicer]    │
└────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Queue ribbon (left, 4 px wide)
Color-coded edge band so the queue state is visible at the speed of skimming a page of cards. Maps:

- `none` → transparent
- `queued` → amber `#F59E0B`
- `printing` → blue `#1E88E5` (animated 1-pixel shimmer)
- `done` → green `#2E7D32`

### 3.2 Provenance pill (always visible)
- `custom_unique` → `MDI:diamond-stone` icon, indigo background `rgba(99,102,241,0.18)`, border `rgba(165,180,252,0.32)`
- `remix` → `MDI:source-branch`, teal `rgba(20,184,166,0.18)`
- `derivative` → `MDI:graph-outline`, slate `rgba(100,116,139,0.20)`

### 3.3 Source chip (new)
Render exactly one source chip when `source_platform` is present. This chip answers "where this came from" and is intentionally distinct from publish destinations.

Display rules:

- `source_platform=original_local` → `Source: Local original`
- known platform IDs → `Source: MakerWorld` / `Source: Printables` / ...
- `source_platform=other` with known URL host → `Source: <host>`
- missing source platform and `origin_type=custom_unique` → `Source: Not set` (muted)
- missing source platform and non-unique origin → `Source: Unknown` (warning-muted)

Interaction rules:

- if `source_download_url` exists, clicking the chip opens that source URL in a new tab
- otherwise the chip is read-only and opens no link

### 3.4 Publish destinations chip row
Each `published_to[]` entry renders as a clickable chip with the destination's brand initial (no logos shipped — keep it text-first to avoid asset drift). Hover shows the URL; click opens in a new tab.

Source-vs-destination semantics:

- source is singular provenance (where the model entered your library)
- publish destinations are zero-or-more outbound locations (where you later published it)
- the same platform may appear in both without being redundant (for example: sourced from Printables, later published to MakerWorld + Printables)

### 3.5 Metric block
Three slots, all monospaced numerics on a 14 px baseline so they read as a single row even when one is missing:

| Slot | Label | Source |
| --- | --- | --- |
| 1 | `Archives` | `archives_count` |
| 2 | `Last printed` | `last_printed_at`, formatted `2d ago`, `3w ago`, … |
| 3 | `Success` | `success_rate_pct` (proposed) — falls back to `—` |

### 3.6 Filament swatches
Reuses the Print History dot-row pattern from [print-history-color-filter-card.js](../../../../homeassistant/www/3d_printing/www/3d_printing/print_history/print-history-color-filter-card.js) — 14 px circles, inset 1 px white-alpha border, hover tooltip with the filament name and hex. Source field: `primary_filament_palette[]` (proposed) with fallback to "—".

### 3.7 File-kind chips (updated)
Up to **three semantic chips** group the model's files, replacing the old per-format text chips (`3MF · 4`, `STL · 2`, etc.):

| Chip | Icon | Contents | Colour |
| --- | --- | --- | --- |
| **Model Files** | 🧊 cube SVG | 3MF + STL + GCODE count combined | Teal accent |
| **Images** | 🖼 image SVG | JPG / PNG / render count | Blue |
| **Docs / Other** | 📄 file SVG | STEP + PDF + misc count | Warm tan |

Chips are only rendered when the count > 0 (cards with only model files show one chip; a card with model files + images shows two). Inspired by Manyfold's per-format chip row but collapsed to semantic groups to avoid visual clutter at compact density.

Source field: `file_kinds` (proposed) — individual counts folded in Layer 2.

### 3.8 Circle icon action buttons (new)
Three 28 px circle buttons sit **top-right of the content column** (above the name, right-aligned via `display:flex; justify-content:flex-end`). They stop click propagation so the card-level click-to-open is not triggered:

| Button | Class | Icon | Colour |
| --- | --- | --- | --- |
| 3D Viewer | `.icon-action.viewer` | Cube/layer SVG | Teal — `rgba(0,137,123,0.14)` bg, `#7dd3c8` fg |
| Favourite | `.icon-action.favorite` / `.favorite.active` | ★ (★ filled when active) | Default: muted; Active: amber `#f5c242`, `rgba(245,194,66,0.20)` bg |
| More | `.icon-action` (generic) | ⋯ | Default subtle |

Visual grammar matches the `print-history-browser-card.js` `.icon-action` / `.action-buttons` pattern exactly (same border-radius, hover lift, box-shadow ring, transition spec). The `⋯` More overflow menu replaces the old `<button class="btn icon-only">` in the action row; the slicer button remains in the action row.

### 3.9 Clickable card
The whole card surface (`cursor: pointer`, `tabindex="0"`) opens the model detail popup on click. Hover adds a subtle `translateY(-1px)` lift and stronger border. Circle buttons (§3.7) call `event.stopPropagation()` so their own click targets are independent.

### 3.10 Action row (revised)
Two primary actions (Open detail, Queue/Dequeue) + slicer button on the right. The `⋯` More overflow has moved to the circle button set (§3.7) — the action row no longer carries it.

```
[Open]  [Queue / Dequeue]              [slicer 🖨]
```

---

## 4. Compact view — primary deliverable

**Job:** information-dense browsing across a curated catalog page.
**Layout:** 3 columns desktop, internal 2-column split (thumb 132 px / content 1fr).
**Card height:** target 220 ± 10 px so 9 cards fit a 1080 px viewport without scroll.

### 4.1 Why information-dense (thumb updated)

Per the user's design direction the compact card should land closer to a Manyfold/Printables grid card than to the existing 1-up Print History layout — the catalog is an inventory, not an event log. To honour that:

- The thumb is sized **120×134 (landscape)**, matching the Print History card proportions (`width:100%; height:132px` in a `minmax(150px,188px)` column). This prevents tall portrait crops from dominating a dense grid and keeps visual weight balanced with the wider content column. Models are most often photographed on a flat print bed, so a landscape crop is more natural.
- The thumb carries a **photo counter badge** (`"1 / 7"`) in the top-right corner — the same semi-transparent pill used in Print History — which tells the user how many photos are attached without opening the detail view. The number advances when the user clicks a photo carousel control.
- The metric block sits **above** the tags so a user scrolling can scan archives counts without their eyes drifting to tag soup.
- The action row collapses to two icons (Open, Queue) at this density, with all secondary actions in the `⋯` overflow.
- Tags are limited to **3 visible + `+N` overflow** (existing Print History pattern in [print_history_archive_card_compact.yaml](../../../../archive/print_history/legacy-dashboard-card-templates/print_history_archive_card_compact.yaml) uses the same `tagLimit = 3`).

### 4.2 Field map (top → bottom inside the content column)

1. **Circle buttons row** — `.card-top-actions`: 3D Viewer · Favourite ★ · More ⋯ (right-aligned, stop propagation)
2. **Name** (15 px, weight 700) + **designer** (12 px, secondary) + **last-printed timestamp** (11 px, right-aligned)
3. **Provenance pill** + **source chip** + **publish chip row** + **signal chips** (`Recent`, `Frequent`, `Common`) — all on one wrapping row
4. **Metric block** (3 cells, 11 px label / 14 px value) — Archives · Last printed · Success
5. **Filament swatches** (14 px dots) + **file-kind semantic chips** (right-aligned, up to 3 — Model Files · Images · Docs)
6. **Tags** (max 3 visible + `+N` overflow)
7. **Action row** — `Open`, `Queue`/`Dequeue`, `⋯`(slicer)

### 4.3 States the mockup demonstrates

The HTML compact mockup shows nine cards covering: queued + printing + done + none queue states, custom-unique + remix + derivative provenance, published-to-MakerWorld, published-to-Printables-and-Manyfold, no-photo fallback, recent + frequent + common signal combos, and a large `+N` tag overflow.

---

## 5. List view

**Job:** scan dozens of models against shared metric columns; bulk select.
**Layout:** single full-width row, 56 px tall, 5 metric columns + checkbox + thumbnail + name + actions.

The list view is intentionally **not** a re-styled compact card. It's a tabular row with fixed column widths so the eye can run vertically down a single metric. Print History's compact card collapses to a single-column stack at narrow widths — list view is the "I have lots of these and need to compare" surface, so it preserves the column structure even at narrow widths and starts horizontally scrolling at < 880 px.

Columns (left → right):
1. **Checkbox** (bulk select)
2. **Queue ribbon** (4 px)
3. **Thumbnail** (48×48, rounded 8)
4. **Name + designer** (truncates with ellipsis at 32 chars)
5. **Provenance pill** (icon-only at narrow widths)
6. **Archives** (right-aligned, monospace)
7. **Last printed** (right-aligned, relative)
8. **Success** (right-aligned, percentage; `—` when unknown)
9. **Source** (`Source: MakerWorld`, compact chip)
10. **Published-to** (chip row, max 2 visible + `+N`)
11. **Tags** (1 visible + `+N`)
12. **Actions** (Open · Queue · `⋯`)

---

## 6. Media view

**Job:** visual-first triage; "which one looks right?"
**Layout:** auto-fit grid (3 columns ≥ ~1000 px desktop, 2 columns ~660–999 px, 1 column < 660 px) using `repeat(auto-fit, minmax(320px, 1fr))` for parity with the print-history media grid. A **4:3** hero photo dominates the card; metadata sits beneath in a thin caption strip.

**Why 4:3, not 16:10/16:9.** The source material driving this card is overwhelmingly square-ish: MakerWorld and Printables cover renders are 1:1, Manyfold renders trend square, and Bambu plate stills are 4:3. A wider 16:9/16:10 frame either letterboxes those or top/bottom-crops the model — exactly the part of the image needed for triage. 4:3 lets `object-fit: cover` honor the source without truncating the model. The narrower hero also shrinks the natural card width enough to fit three across at typical dashboard widths, matching the print-history media density the design borrows its grammar from (see §1).

The media view is the closest analog to MakerWorld's and Printables's grid cards (see §7). The photo is **the** primary affordance; everything else is a thin caption strip with provenance pill, publish destination chips, and a single primary action (Open detail). The carousel arrows already wired up via `media-prev` / `media-next` in [model-catalog-browser-card.js](../../../../homeassistant/www/3d_printing/model_catalog/model-catalog-browser-card.js) sit overlaid at the bottom-center of the photo on hover.

Caption strip rows:
1. Name + designer (single line, truncates)
2. Provenance pill + source chip + publish chips + queue chip (when `queued`/`printing`)
3. Filament swatches (right-aligned)

---

## 7. Toolbar & header redesign (issue #1216)

**Job:** give the catalog browser a header that mirrors the print-history toolbar grammar without copying it wholesale, so users can move between the two surfaces without re-learning controls. See the dedicated mockup at [mockups/toolbar.html](mockups/toolbar.html) for three side-by-side layout options plus a merged collections-centric state:

- **Option A (recommended)** — three rows above the grid (title with inline sort → filter bar → centered page-control strip). ~158 px of header chrome. Highest discoverability and tightest parity with print-history.
- **Option B (denser, two rows)** — collapses Option A's title row and page-control strip into one combined header, leaving header + filter bar above the grid. ~102 px of chrome (~52 px less than A). Page nav is no longer centered.
- **Option C (single row, filters in popover)** — title + search + Filters-button + page nav + sort/view/per-page/toggles all on one row; collection/creator/tag/queue/favorites/other-files filters move into a popover behind a single button with an active-filter count badge. ~66 px of chrome (~58 % less than A). Lowest filter discoverability.
- **Merged collections-centric state (recommended behavior, not a fourth architecture)** — uses the same shell as Option A/B/C, but swaps in collections-specific controls when scope is `Collections`.

### 7.0 Unified Integration Model (shared shell + adaptive slots)

The collections-centric toolbar must be treated as a **state of the same toolbar**, not a separate toolbar design.

Shared shell remains constant:

1. scope selection and global identity controls
2. search/filter row
3. pagination/density/display controls (where applicable by option)

Adaptive slots by scope:

- when scope is `All models (flat)`:
  - model sort controls
  - model-centric filters (creator, tags, queue state, favorites, other files)
- when scope is `Collections`:
  - collection sort (`Name`, `Recent activity`, `Model count`)
  - mixed-node display segment (`Mixed`, `Collections only`, `Models only`)
  - in-node search chip/toggle
  - path/depth controls (`current only`, `include descendants`)

This keeps interaction memory intact and avoids having two toolbar systems to maintain.

### 7.0.1 Per-option merge rules

- Option A: collections controls appear as title-row chips/segments plus filter-row path/depth controls.
- Option B: collections controls map to labelled selects/toggles inside the combined header trailing cluster.
- Option C: collections controls move into the Filters popover and keep only high-priority toggles visible in-row.

### 7.0.2 Control priority for wrapping

When width is constrained, preserve this priority order:

1. scope toggle
2. search input
3. mixed-node display segment
4. sort selector
5. path/depth selectors
6. secondary chips

If controls must collapse, move lower-priority controls into overflow/popover before hiding core controls.

### 7.1 Layout (three rows above the grid)

The header decomposes into three stacked, full-width rows that sit above the card grid:

1. **Title row** — `Catalog Browser` + an inline `Sort` pill on the right. Per #1216, sort moves *out* of the filter panel and *into* the title row so it's always visible without scrolling.
  - Add an always-visible `Import` dropdown in this title row with two jump actions: `Browser Upload` and `Server Inbox`.
2. **Filter bar** — search input + the existing select filters (collection, creator, tag, queue) + two new filter chips (`Favorites only`, `Has other files`).
3. **Page-control strip** — centered between the filter bar and the grid; never above the filter bar. The strip groups *navigation* + *density* + *display toggles*. A simplified mirror strip repeats below the grid.

This ordering matches print-history's structure (filter pills → centered control strip → grid → mirror strip) so muscle memory transfers between the two browsers.

Collections-mode integration for this same layout:

- Title row keeps scope toggle and swaps sort label to `Sort collections`.
- Filter row keeps search, adds mixed-node segment and in-node chip, and replaces model-specific filters with collection path/depth filters.
- Page strip remains unchanged so navigation and density controls behave identically across scopes.

### 7.2 Page-control cluster (navigation)

- **First / Prev / Next / Last** are icon-only buttons using chevron + double-chevron glyphs (parity with print-history's `mdi:page-first` / `mdi:chevron-left` / `mdi:chevron-right` / `mdi:page-last`). Replaces today's text labels.
- **Page indicator** reads `1 / 5 · 47 models` — page X of Y plus the **total count** (#1216 "Count"). Total is rendered in accent color so the live number is the eye-catch.
- Disabled states (first page → first/prev grey out; last page → next/last grey out) are required.

### 7.3 Density cluster (Models / Page + View variant)

- **Models / Page** is a `<select>` with steps `12 · 24 · 48 · 96`. Persisted via the same helper pattern used by print-history (or a new `input_number.model_catalog_per_page` if a slider is preferred — the mockup defaults to a select for discrete values).
- **View variant** becomes a single `<select>` (Compact · Media · List) per #1216 "Drop down for Card". Replaces the three toggle buttons currently rendered by `_renderViewToggle` in [model-catalog-browser-card.js](../../../../homeassistant/www/3d_printing/model_catalog/model-catalog-browser-card.js). Rationale: saves ~80 px of horizontal real estate on the strip and keeps the high-frequency controls (page nav) visually dominant. *Alternative considered* — keep three toggle buttons but icon-only; rejected because the dropdown matches the user's stated print-history preference ("matches print-history sort pattern").

### 7.4 Display-toggle cluster (Show media + Refresh)

- **Show / hide media** is an eye toggle (`aria-pressed`), mirroring `input_boolean.print_history_show_images`. Add a sibling helper `input_boolean.model_catalog_show_images`; all three card variants (compact / media / list) read it and render a no-thumbnail variant when off.
- **Refresh** is a single icon button. Spins (CSS keyframe) while the load is in flight; clears when the response resolves. Wires to `_requestLoad(this._currentPage(), true)` with a forced-bypass flag.

### 7.5 Favorite controls (per-card star + top-level filter)

Split across two surfaces, by design:

- **Per-card quick-toggle** — amber star icon-action already drafted in §3.7 / [mockups/compact.html](mockups/compact.html). Toggles `is_favorite` on the model, optimistic update.
- **Top-level Favorites-only filter** — amber pill on the filter bar, scopes the grid to favorited models. New search-payload field `favorites_only: bool`.

Both share the same color treatment (amber, matching print-history's `.favorite.active`) so users associate the visual with the favorite concept regardless of where they encounter it.

### 7.6 Other Files filter + per-card chips

#1216 calls for an "Other Files (PDF, etc.)" indicator. Implemented in two places:

- **Top-level filter chip** (`Has other files`) on the filter bar — scopes the grid to models that include any non-3D file (PDF assembly instructions, BOMs, READMEs, etc.). New search-payload field `has_other_files: bool`.
- **Per-card chip group** — already partially in place (`file_kinds` proposed field, §2.2). The compact card surfaces three chips: Model Files / Images / Docs. The Docs chip is the per-card "other files" affordance; clicking it scrolls the detail popup to the file-list section.

**Layering guardrail (re-affirmed):** the *labels* ("Model Files", "Docs", "Has other files") and the *category buckets* are presentation concerns and live in the card / toolbar code, not in the Layer 1 archive sensor. Layer 2 derives `file_kinds` from the existing enrichment payload (mime type / extension grouping); Layer 3 (the card) chooses chip wording, color, and which kinds are aggregated under "Docs".

### 7.7 Backend touch points

| Control | Layer | New surface needed |
| --- | --- | --- |
| Sort dropdown (now in title row) | Layer 3 | none — already wired |
| Models / Page select | Layer 3 + helper | `input_number.model_catalog_per_page` *or* persist client-side |
| View variant dropdown | Layer 3 | none — repackages existing `_renderViewToggle` actions |
| Show / hide media toggle | Layer 3 + helper | `input_boolean.model_catalog_show_images` (mirrors print-history) |
| Refresh button | Layer 3 | none — `_requestLoad(page, force=true)` already exists |
| Favorites-only filter | Layer 2 + Layer 3 | extend search payload with `favorites_only`; backend filter on `is_favorite` projection |
| Has-other-files filter | Layer 2 + Layer 3 | extend search payload with `has_other_files`; backend filter on `file_kinds` projection |
| Per-card star (favorite) | Layer 1/2 + Layer 3 | `is_favorite` field already proposed in §2.2; toggle action wires through existing model-update API |
| Per-card file-kind chips | Layer 2 + Layer 3 | `file_kinds` projection (§2.2); chip labels stay in Layer 3 |
| Import dropdown (`Browser Upload` / `Server Inbox`) | Layer 3 + navigation action | UI-only menu in catalog header that routes into shared intake wizard with source mode preselected |

Layer 1 (`sensor.print_history_archives` and the equivalent model-catalog projection) **must not** absorb chip labels, color tokens, or filter-pill wording — those are presentation concerns owned by the dashboard and the custom card.

### 7.8 Mockup deliverables

- [mockups/toolbar.html](mockups/toolbar.html) — Option A (recommended) and Option B/C alternatives, plus a merged collections-centric toolbar state using the same shell, with inline anatomy notes and a per-bullet mapping table.
- [mockups/compact.html](mockups/compact.html), [mockups/list.html](mockups/list.html), [mockups/media.html](mockups/media.html) — header banner points at toolbar.html; the existing in-mockup filter bar is retained as a placeholder so each variant continues to read standalone.

### 7.9 Intake Entry Contract (issue #1321)

Catalog includes two intake entry paths:

- always-visible `Import` dropdown in the catalog toolbar (`Browser Upload`, `Server Inbox`)
- optional quick-drop card on wider layouts only

Quick-drop is an acceleration path, not a replacement. Narrow layouts retain only the Import dropdown.

---

## Collections Browsing Mode (new)

This section adds a first-class browse scope for collections without replacing the existing flat model browser.

### Collections Scope Toggle

Add a required scope control in the catalog header, adjacent to sort/view controls:

- `All models (flat)`
- `Collections`

Behavior contract:

- `All models (flat)` preserves the current card/list/media behavior and pagination semantics.
- `Collections` switches the primary results to collection cards (not model cards).
- Scope choice is sticky per user (local storage helper) but does not affect backend ingest/indexing.

### Collection Card Anatomy

Collection cards are intentionally summary-first and action-forward:

- cover mosaic (2x2 or adaptive 3x2 depending card size), with each tile framed at 4:3 to align with compact/media thumbnail proportions
- title + optional path chip (`Parent / Child`)
- counts row: `models`, `sub-collections`, `prints`
- recency row: `recently updated`, `last printed`
- quick actions: `Open`, `More`

Desktop recommendation:

- 3 columns at >= 1280 px
- 2 columns at 880-1279 px
- 1 column below 880 px

### Collection Cover Image Derivation

Use deterministic sampling, not random-on-each-render.

Cover source priority per model:

1. model selected image (operator-picked primary)
2. model thumbnail/primary photo
3. derived 3MF thumbnail
4. placeholder tile

Sampling strategy (deterministic, stable):

- sort candidate models by:
  - explicit pin order (if available), then
  - `last_printed_at` desc, then
  - name asc
- take first `N` models where `N` equals tile slots (4 default)
- keep this ordering stable until collection membership or pinning changes

Rationale:

- avoids visual flicker between refreshes
- keeps frequently-used models visually represented
- remains explainable to operators (not "why did the cover change?")

Optional enhancement:

- allow `cover_mode` per collection: `auto`, `pinned`, `manual`
- `manual` lets operator pin up to 6 cover contributors

### Hierarchy Model

Support hierarchical collections with a nullable parent pointer:

- `collection_id`
- `parent_collection_id` (nullable)

Model membership rules:

- A model may belong to multiple collections.
- Membership is explicit per collection (no implied membership propagation).
- Models may exist at any hierarchy level (root or nested).
- No implicit inheritance of model membership to descendants.

Guardrails:

- prevent cycles on create/move
- prevent self-parenting
- enforce max depth (recommended: 4) for dashboard usability

### Rendering A Mixed Node (models + sub-collections)

When opening a collection node that contains both models and sub-collections, use a two-section result list under one toolbar state:

1. `Sub-collections` section (card grid)
2. `Models in this collection` section (selected view variant: compact/list/media)

Default ordering:

- sub-collections first (promotes navigation)
- then direct models

Operator controls:

- `Show: Mixed | Collections only | Models only`
- `Sort collections by: Name | Recent activity | Model count`
- model sort keeps existing sort dropdown semantics

This avoids flattening nested structure into one ambiguous feed while still supporting direct model actions at parent levels.

Mockup fidelity note:

- mixed-node examples in `mockups/collections.html` are representative placeholders for density/section behavior
- implementation should render real collection cards for sub-collections and the selected model view variant (`Compact`/`Media`/`List`) for models

### List View In Collections Scope

`List` view must remain fully supported when scope is `Collections`.

Rendering rules by display segment:

1. `Collections only`
  - render a collection-row table (not model-row table)
  - row fields: collection name/path, direct model count, child collection count, last activity, actions
2. `Models only`
  - render the existing model list-row table exactly as in flat scope
  - include collection-path column (or chip cell) to preserve context
3. `Mixed`
  - render one unified list with typed rows:
    - collection rows first
    - model rows second
  - each row includes a `Type` indicator (`Collection` or `Model`) for scan clarity

No Collection handling in list mode:

- at root, `No Collection` appears as a collection row when `unassigned_model_count > 0`
- opening that row with `Models only` or `Mixed` shows unassigned model rows

Sorting in list mode:

- collection rows use collection sort controls
- model rows use model sort controls
- in `Mixed`, primary sort remains type order (collections then models), with secondary sort applied within each type bucket

### Navigation Pattern

In `Collections` scope, use breadcrumb navigation:

- `All Collections / Functional / Gridfinity`

Add a compact "up one level" control in the toolbar for keyboard and touch parity.

Search semantics:

- global search (default): returns collections and models
- in-node search (optional chip): scopes to current collection subtree

### Unassigned Models In Collections Scope

When scope is `Collections`, models with zero collection memberships must remain visible through a system bucket:

- show a synthetic `No Collection` collection card at root when unassigned count > 0
- card label: `No Collection`
- subtitle: `System bucket` (or equivalent neutral wording)
- clicking opens a virtual node containing unassigned models only

Rules:

- `No Collection` appears only at root collection level
- it is not parentable, renamable, or deletable
- if unassigned count is 0, hide the card

This avoids silently dropping models from view when operators switch to collections scope.

### Paging Contract For Mixed Mode

Mixed mode (`Sub-collections` + `Models in this collection`) uses one unified pager from the top toolbar.

Algorithm:

1. Build ordered result stream:
  - all matching sub-collections first
  - all matching direct models second
2. Apply one page slice (`page`, `per_page`) to that ordered stream.
3. Render section headers only for item types present in the current slice.

Implications:

- a page may contain only sub-collections, only models, or both
- toolbar pager remains consistent across `Mixed`, `Collections only`, and `Models only`
- no second pager appears inside sections

UI clarity aids:

- show result summary chip in toolbar: `X collections · Y models`
- keep `Show: Mixed | Collections only | Models only` segment visible to quickly constrain result type

### Minimal Data Contract (Layer 2 projection)

Collection browsing should be served by Layer 2 projection data and must not move UI wording into Layer 1.

Proposed collection projection fields:

- `collection_id`, `name`, `parent_collection_id`, `path`
- `model_count_direct`, `model_count_total`
- `child_collection_count`
- `last_activity_at`, `last_printed_at`
- `cover_tiles[]` (resolved media URLs + contributor model refs)
- `unassigned_model_count` (root-only summary for `No Collection` system bucket)

Layering rule:

- tile selection metadata can live in Layer 2
- labels like `Models in this collection` and chip copy remain Layer 3

### Open Decisions For Review

### Approved Defaults (2026-05-09)

1. **Model membership**: multi-collection membership is supported in v1.
2. **Hierarchy depth**: max depth recommendation remains `4`.
3. **Mixed node ordering**: `Sub-collections` render first by default.
4. **Collection actions**: no collection-level print queue action in v1 (`Open`, `More` only).
5. **Cover mode**: ship `auto` in v1; `manual` remains a follow-up phase.

## 8. Comparative analysis (deep)

What follows is a per-tool reading of how comparable surfaces solve the same job, and what we're borrowing or rejecting.

### 8.1 Manyfold

- **Source:** [manyfold.app/features](https://manyfold.app/features), [github.com/manyfold3d/manyfold](https://github.com/manyfold3d/manyfold). Manyfold is a Rails + Bootstrap 5 + THREE.js self-hosted DAM for 3D models with first-class scanning, tagging, creators, collections, likes, and multi-user permissions. The feature page calls out **previews**, **organisation (tags / creators / lists / collections / folder structure)**, **problem detection (inefficient formats, missing metadata)**, **federation**, and a **REST API**. ([manyfold.app/features](https://manyfold.app/features))
- **What we borrow:**
  - **File-format chip row** (Manyfold surfaces format counts per model; we mirror this with the `file_kinds` proposed field).
  - **Creator emphasis** — Manyfold treats the creator/designer as a navigable entity, not a metadata afterthought. We elevate `designer` to the second header line and make it tappable in a follow-up phase.
  - **Problem-detection signal** — Manyfold marks models that fail format/metadata heuristics; we already have `recent`/`frequent`/`common` signal chips and can add a `Needs attention` chip later from the same channel.
- **What we don't borrow:**
  - Manyfold's likes/comments/federation row — out of scope for a single-user HA install.
  - Bootstrap-style filled cards with heavy elevation; we keep the translucent dark surface that matches the rest of HA.

### 8.2 Bambuddy File Manager (local repo)

- **Source:** the [print-history-archive-actions-card.js](../../../../homeassistant/www/3d_printing/print_history/print-history-archive-actions-card.js) main-tabs `Files & Media` panel, plus the [working-files explorer](../../../../homeassistant/www/3d_printing/model_catalog/model-catalog-working-files-explorer-card.js).
- **What we borrow:**
  - The `[icon] [label] [count]` capsule pattern used to surface "Files & Media" counts on the action card; reused as our `file_kinds` chips.
  - The compact `Open in Slicer` quick action — promoted in our card as the third primary action when a slicer-launchable artifact is present.
- **What we don't borrow:**
  - The full multi-tab action surface — that's a detail-popup pattern, not a card pattern. The card's `⋯` overflow menu is the link into the existing actions card.

### 8.3 MakerWorld

- **Source observation:** MakerWorld's grid card is a 16:9 hero photo with floating "auto-rotate to next photo" hover behavior, a like/download counter strip in the bottom-left of the photo, the model title beneath the photo (1–2 lines, truncates), and the creator avatar + name on the line below. (Live page returns `403` to fetchers; pattern observed from public browsing.)
- **What we borrow:**
  - **Hero-first media card** — drives our Media view layout.
  - **Carousel-on-hover** — already wired in our browser via `media-prev`/`media-next`; we make the arrows visible only on hover/focus to keep the card calm at rest.
  - **Counters baked into the photo** — we adapt this for the queue chip, which sits as an overlay in the photo's top-left when the model is `queued` or `printing`.
- **What we don't borrow:**
  - Like / download social counters — not part of a private HA install.
  - MakerWorld's brand-coloured "Bambu Lab" attribution badge — replaced by our generic publish destination chip.

### 8.4 Printables

- **Source:** [printables.com/model](https://www.printables.com/model). The grid card pattern: hero photo with photo-count badge top-right, **per-file color swatches rendered as `█ █ █` blocks** at the bottom of the photo, title (medium weight, 2-line clamp) under the photo, then a single line with creator avatar + name + creator-tier badge, then a counter row (`likes` and `downloads`).
- **What we borrow:**
  - **Per-file color swatches as a row** — directly inspired our filament swatch row in Compact and Media. Printables proves swatches are scannable at this size.
  - **Multi-photo badge** — the small `1/7` indicator overlaid on the photo carousel is a great affordance; we adopt it for the Media view.
  - **2-line title clamp** — used in Compact so longer model names don't shrink the metric block.
- **What we don't borrow:**
  - The category-tag colour bar Printables uses to brand cards by category — too noisy for a personal catalog.
  - Sidebar filter ribbons inside cards (Printables uses card-level "featured / contest / make" pills); we keep that information in the filter tray, not on the card.

### 8.5 Thingiverse

- **Source observation:** Thingiverse's grid card is the simplest of the four — square hero photo, title (1-line truncate), creator name, like + collect counters. Hover swaps the hero photo to a secondary photo if available. (The public `/explore/popular` page returns `404` to fetchers; pattern observed from public browsing.)
- **What we borrow:**
  - **Hover-photo-swap** — the second click-target pattern. We don't need this in Compact (too noisy at 3-up density) but we adopt it on Media when more than one photo is available.
- **What we don't borrow:**
  - Thingiverse's information sparseness — we have *more* signal to surface (queue, archives, success), so a Thingiverse-density card would underuse the space.

### 8.6 Print History (sibling repo feature)

- **Source:** [print-history-browser-card.js](../../../../homeassistant/www/3d_printing/print_history/print-history-browser-card.js) and the legacy YAML templates ([compact](../../../../archive/print_history/legacy-dashboard-card-templates/print_history_archive_card_compact.yaml), [media](../../../../archive/print_history/legacy-dashboard-card-templates/print_history_archive_card_media.yaml), [detail](../../../../archive/print_history/legacy-dashboard-card-templates/print_history_archive_card_detail.yaml)).
- **What we borrow (whole-cloth):**
  - Card shell tokens (`border-radius:18`, translucent surface, hairline border).
  - Status pill style (rounded 999 px, 4×10 padding, 11 px / weight 700, icon + label).
  - Tag pill style (small, coloured background, dark text, inset border).
  - Filament dot pattern (14 px circle, inset white-alpha border, hover tooltip).
  - Metric block 3-up grid (`auto-fit minmax(116px,1fr)`).
- **What we diverge on:**
  - Replace the run-status pill with the **provenance pill** (the model has provenance, runs have status).
  - Replace the corner star (favorite) with a **queue ribbon** on the left edge — it's a more frequently-acted state for a catalog row.
  - Replace duration/filament/cost metrics with **archives / last printed / success rate**.

---

## 9. Open questions

1. `success_rate_pct` denominator: do we count cancelled prints against success, or only completed-vs-failed? Recommend the latter (mirror Print History's existing distinction).
2. `published_to[]` ordering: should "owned" destinations (Manyfold, local catalog) sort before remote (MakerWorld, Printables)? Recommend yes.
3. Should the queue ribbon respect a per-printer queue (multi-printer households) or stay global? Out of scope for this iteration; design accommodates a future per-printer chip in the action row.
