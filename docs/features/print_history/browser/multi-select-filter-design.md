# Print History Multi-Select Filter Design (Issue #784)

## Purpose

Define the first compact multi-select filter expansion for the print-history browser, starting with archive tags.

This document is design-only. It does not change the current shipped browser behavior yet.

The main question for issue `#784` is not whether multi-select filtering is possible. It is where that capability belongs in the current Variant 3 browser without recreating the color-filter footprint, bloating the always-visible header, or regressing filter-change responsiveness.

## Scope

Primary scope for this issue:

- replace the current single-select tag filter with a compact multi-select picker
- support selecting one or more user tags
- support explicit `Any` versus `All` tag-match logic
- preserve a filter-specific clear action that clears all selected tags for that filter
- keep the existing browser query/navigation path fast

Secondary scope for this design:

- evaluate whether the same pattern should extend to other filters such as designer, project, material, printer, or status
- define where multi-select does and does not make semantic sense

Out of scope for the first implementation:

- a broad generic rewrite of every filter into one unified state object
- adding large always-visible chip rows for non-color filters
- changing the color-filter presentation model
- widening Layer 1 with presentation-only labels or per-filter UI wording

## Current Baseline

The active print-history browser already has two useful precedents:

1. the color filter is already multi-select, but it consumes a lot of persistent header space because swatches must remain directly visible
2. the archive popup already uses a custom typeahead tag editor, so typeahead tag selection is an established interaction pattern in this feature area

The active browser backend is Variant 3:

- browser cards query the Bambuddy custom integration over websocket
- query-state still mirrors Home Assistant helpers so the browser card, heatmap, clear scripts, and page reset behavior stay aligned
- the local SQLite store already maintains normalized archive-tag rows and an index on normalized tag values

That means issue `#784` should build on the existing query/store contract instead of pushing more derived tag state into frontend-only local memory.

## Design Goals

1. make tag multi-select compact enough to live in the existing header without becoming another always-open strip like color
2. preserve the current fast navigation and filter-change feel
3. keep tag filtering explicitly limited to user-visible tags, not managed system tags
4. make `Any` versus `All` tag logic obvious instead of implicit
5. preserve filter-specific clear behavior so `Clear Tag Filter` clears all selected tags at once
6. keep the design reusable for later filters where multi-select is useful

## Non-Goals

1. do not move filter logic back into large Jinja entities or Layer 1 payload expansion
2. do not require a server round trip for every keypress in a typeahead input
3. do not turn every filter into a chip-row surface
4. do not introduce `AND` semantics for filters whose archive field is single-valued

## Primary Recommendation

### Tags should move to a compact popup picker, not an always-visible row

The tag filter should stop behaving like a plain single-select dropdown.

It should also not copy the color filter's persistent row of visible choices.

Recommended interaction:

1. the header keeps a single `Tag` filter pill in the normal filter row
2. tapping that pill opens a compact custom picker surface
3. the picker supports typeahead, multiple selected tags, and explicit `Any` or `All` logic
4. closing the picker leaves only a compact summary in the pill, such as `Tags: 3 Any` or `Tags: 2 All`

This is the right tradeoff because tags can be numerous and textual, so they benefit from search. At the same time, they do not need the always-visible glance affordance that color swatches need.

### Recommended picker layout

The first implementation should use a custom card or popup-sheet style picker, not a stack of native dropdowns.

Recommended sections inside the picker:

1. `Search tags` input with local typeahead filtering
2. `Selected` chip row for currently chosen tags
3. `Match mode` segmented control with `Any` and `All`
4. `Available tags` list with tap-to-toggle rows
5. footer actions: `Apply`, `Clear Tags`, `Close`

Optional but reasonable if low-cost:

- show a lightweight count beside each tag option when it is already cheaply available from cached option data or a targeted store query

Not required for the first version:

- per-tag color chips in the picker list
- per-keypress remote suggestions
- nested groups or advanced query-builder semantics

### First implementation slice

The first implementation should use the existing `Tag` header pill to open a popup-based picker rather than introducing a new persistent row in the header.

Recommended first-slice popup contents:

1. the shipped `print-history-tag-editor-card` bound to the tag-filter helper state
2. a small `Match Mode` control with `Any` and `All`
3. an `Untagged Only` toggle
4. a `Clear Tags` action in the popup

Important first-slice behavior:

- typeahead remains local inside the tag editor card
- tag add and remove actions persist only on commit actions such as Enter, comma, or chip removal
- filter changes do not occur on every keypress while the user is still typing
- the first slice may apply committed changes immediately rather than requiring a separate `Apply` button, because the editor persists only on commit boundaries instead of on every keystroke

This keeps the implementation compact while still meeting the main performance goal: no per-keypress backend queries.

### Match semantics

Recommended behavior for tag filtering:

- `Any`: archive matches when it contains at least one selected user tag
- `All`: archive matches only when it contains every selected user tag
- no selected tags: tag filter is inactive

Important semantic rule:

- `Any` and `All` only apply to actual tag selections
- they do not apply globally across unrelated filters

This keeps the logic predictable and avoids turning the browser into a general boolean query builder.

### Untagged behavior

The current single-select tag filter exposes a `None` path for archives with no user tags.

That behavior should remain available, but the first multi-select version should keep it constrained so the logic stays understandable.

Recommended rule:

- expose `Untagged` as a special picker option
- treat `Untagged` as mutually exclusive with selected tags in the first implementation

Why:

- `Untagged + Any(tag_a, tag_b)` is understandable but adds one more branch to filter summaries, clear chips, and active-state wording
- `Untagged + All(tag_a, tag_b)` is not meaningful

If mixed `Untagged or selected tags` browsing becomes important later, add it deliberately in a follow-up. Do not complicate issue `#784` with that extra branch up front.

## Query-State Recommendation

### Keep helper-backed shared state, but store selected tags like colors

The current architecture still benefits from helper-backed shared filter state because:

- the browser card reads it
- the heatmap reads it
- clear/reset scripts read it
- page-reset behavior depends on it
- debug instrumentation can reason about it consistently

Recommended state shape for tags:

- selected tags stored in a lightweight helper value similar to the color filter pattern
- match mode stored separately as a tiny helper value

Recommended implementation direction:

- `input_text.print_history_filter_tags` stores normalized selected tags as a compact CSV or similarly simple serialized form
- `input_select.print_history_filter_tags_mode` stores `Any` or `All`

Why this is preferred over a larger generic JSON helper in issue `#784`:

- it matches an existing successful pattern already used for colors
- it minimizes scope creep
- it avoids forcing every current filter consumer to adopt a broader filter-state migration just to ship tags first

### Clear behavior

The filter-specific clear action for tags should:

1. empty the selected tag helper
2. reset tag mode back to `Any`
3. reset current page to `1`

This preserves the current contract that clearing one filter clears all choices for that filter, not just the last selected item.

## Performance Guardrails

Issue `#784` should be treated as failed if it makes filter changes or view navigation noticeably slower.

### Guardrail 1: no Layer 1 expansion

Do not add multi-select labels, filter summaries, or tag-option UI strings to Layer 1 archive projection.

The active browser already moved away from large HA entity payloads. This issue should not reintroduce browser-facing payload growth just to support a picker.

### Guardrail 2: no per-keypress websocket query

Typeahead inside the picker should filter against already-available option data locally in the browser.

It should not call the backend on every keypress.

Good sources for picker options:

- cached tag options already exposed by the active browser status/query path
- a precomputed option list derived from the current store-backed option set

### Guardrail 3: keep inactive-filter cost near zero

When no tag filter is selected, query cost should remain effectively unchanged from today.

That means:

- do not force extra joins or scans when the tag filter is inactive
- only apply tag-specific store filtering when selected tags exist

### Guardrail 4: use the store's normalized tag path

The Variant 3 store already keeps normalized archive tags in a dedicated table with an index.

The multi-select tag query should use that normalized path rather than repeatedly reparsing raw comma-separated tag strings on every browser query.

Recommended SQL/query semantics:

- `Any` mode: match archive IDs with at least one selected normalized tag
- `All` mode: match archive IDs where the number of matched selected normalized tags equals the number of selected tags

### Guardrail 5: preserve debounce/coalescing behavior

Opening the picker, typing in its local search field, or toggling chips inside the picker should not trigger multiple redundant browser refreshes before the user actually applies a new selection.

Recommended behavior:

- local picker typing is local-only
- selection changes may stay local until `Apply`, or they may write immediately if debounce/coalescing remains stable
- `Clear Tags` should perform a single state update sequence, not many small writes

For the first implementation, an explicit `Apply` button is the safer performance choice.

## UX Contract

### Header summary

The visible tag pill in the header should stay compact.

Examples:

- `Tag: All`
- `Tags: 1 Any`
- `Tags: 3 Any`
- `Tags: 2 All`
- `Tag: Untagged`

The summary should communicate only the active state, not spell out every selected tag inline in the main header row.

For the first implementation, a helper-backed summary such as `All`, `Untagged`, `1 Any`, or `3 All` is sufficient. It does not need to enumerate actual tag names in the top controls.

### Active filter chips

The browser can still expose a clear chip or active-filter summary for tags, but it should summarize rather than enumerate every tag when the selection gets long.

Recommended summary chip:

- `Clear Tags (3)`

Do not spill a long textual tag list into the always-visible top controls.

### Mobile behavior

On mobile, the tag picker should open as a bottom sheet or popup sized for thumb selection.

Requirements:

- keep the main header footprint unchanged
- allow scrolling within the picker, not the whole view
- keep `Apply` and `Clear Tags` pinned or otherwise easy to reach

## Reuse And Extension To Other Filters

The same compact-picker pattern is not equally valuable for every filter.

### Strong candidates for later reuse

#### Designer

Recommended: yes, later.

Why it fits:

- the value set can grow over time
- typeahead is useful
- the current single-select pill can become limiting if users want to compare or browse several creators at once

Semantic limit:

- only `Any` semantics make sense because each archive has one designer value
- do not expose `All` for designer

#### Project

Recommended: yes, later.

Why it fits:

- projects can become numerous enough that typeahead helps
- some users may want to browse several projects together

Semantic limit:

- only `Any` semantics make sense
- preserve a special `No Project` pseudo-option similar to the current `None`

#### Material

Recommended: maybe later, lower priority.

Why it might fit:

- it is categorical and some users may want to browse PLA + PETG together

Why it is lower priority:

- the current value set is usually smaller than tags or designers
- material is often less exploratory than tags

### Filters that should remain single-select or fixed controls

#### Status

Recommended: keep as a compact fixed dropdown or segmented menu.

Why:

- the option set is small and finite
- `All` versus `Any` logic is unnecessary noise
- `AND` semantics do not make sense for a single archive status

Multi-select status may be useful someday, but it should not borrow the tag picker's `Any` and `All` model.

#### Archive Issue

Recommended: keep single-select.

Why:

- it is a small, operator-facing classification set
- the most common workflow is to focus one issue class at a time

#### Printer

Recommended: keep single-select for now.

Why:

- printer count is typically low
- a plain dropdown remains fast and readable
- value is lower than tags, designers, or projects

#### Date Range

Recommended: keep single-select.

Why:

- ranges are mutually exclusive presets
- multi-select date presets are not semantically clean

#### Favorites

Recommended: keep boolean.

Why:

- the current toggle already expresses the intent clearly

#### Layer Height

Recommended: keep single-select for now.

Why:

- multi-select is possible but niche
- it does not justify a custom picker ahead of tags, designer, or project

### Color stays special-case

The color filter should remain a special-case visual control.

Reason:

- color is inherently glanceable in a way tag/designer/project are not
- the existing swatch row trades space for immediate visual recognition

Issue `#784` should not try to force color into the same compact-picker pattern just for consistency.

## Recommended Phasing

### Phase 784A: Tags only

Ship the compact tag picker first.

Include:

- multi-select user tags
- `Any` and `All`
- `Untagged` as a mutually exclusive special option
- filter-specific clear behavior
- compact pill summary

Do not include:

- designer/project conversion in the same change
- generic filter-state migration

### Phase 784B: Optional compact-picker reuse

If Phase 784A is stable and performant, evaluate reusing the same control model for:

- designer
- project
- possibly material

Those follow-ons should use `Any` only.

## Acceptance Criteria

Issue `#784` is designed well enough for implementation when:

- tags have a compact multi-select interaction that does not require an always-visible choice row
- tag matching rules for `Any`, `All`, and `Untagged` are explicit
- the design keeps clear-all behavior scoped to the tag filter
- the design keeps typeahead local and avoids per-keypress backend work
- the design keeps inactive-tag cost near zero
- the design clearly explains which other filters are good follow-on candidates and which should stay single-select

## Implementation Notes For Copilot Or Human Implementers

Read these sources first:

1. this document
2. `docs/features/print_history/browser/filter-sort-design.md`
3. `docs/features/print_history/browser/top-controls-contract.md`
4. `docs/features/print_history/ui-media/archive-detail-popup-design.md`
5. `homeassistant/custom_components/bambuddy/print_history/query.py`
6. `homeassistant/custom_components/bambuddy/print_history/store.py`
7. `homeassistant/www/3d_printing/print_history/print-history-browser-card.js`
8. `homeassistant/www/3d_printing/print_history/print-history-tag-editor-card.js`

Implementation guardrails:

- preserve the three-layer browser contract
- preserve the current top-controls density; do not add a second always-visible text filter row for tags
- prefer store-backed normalized tag matching over reparsing raw tag strings per query
- keep system-managed tags hidden from user-facing filter choices
- keep browser and heatmap filter state aligned