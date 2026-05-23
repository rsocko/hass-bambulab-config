# Print History Heatmap Legend Filtering

> **Issue**: #1127 Add Ability to Filter Heatmap (and results) by the "Legend" values
> **Status**: Implemented
> **Created**: 2026-04-25
> **Depends on**: [filter-sort-design.md](filter-sort-design.md), [README.md](../../README.md)

## Problem Statement

Issue #1127 requests the ability to click a heatmap legend swatch (e.g., "Multi-Color Prints" → purple swatch) and have the heatmap filter to show only days matching that category, with print details below updated accordingly.

Current state: Legend is static and non-interactive.

## Solution: Legend-Driven Activity Metric Filtering

Instead of implementing multi-day selection (which would require entity model changes), we use the existing filter architecture to achieve the same user outcome with minimal code.

### Architecture Decision

**Mechanism**: Clickable legend swatches set the `input_select.print_history_filter_activity_metric` helper, which filters the heatmap data in the backend query.

**Why this approach**:
- ✅ Reuses existing filter pipeline (no new query infrastructure)
- ✅ Zero changes to date selection or detail-view entity models
- ✅ Card automatically re-renders with filtered data on helper change
- ✅ Zero performance impact (same query cost as other filter changes)
- ✅ Works seamlessly with existing multi-select archive actions
- ✅ Minimal code changes (~50 lines total)

### Filter Entity Contract

**Entity**: `input_select.print_history_filter_activity_metric`

**Type**: `input_select`

**Options** (one per heatmap metric mode):
```yaml
"All" (unfiltered)
"Print Count"
"Filament Weight"
"Storage Used"
"Number of Printed Objects"
"Cost of Prints"
"Filaments Used"
"Number of Unique Tags"
"Single vs Multi-Color Prints"
"Number of Unique Filaments"
"In a Project vs Not in a Project"
"Number of Duplicates / Similar"
"Enrichment Status"
"Number of Favorites"
"Total Time Printing"
"Outcome"
"Dominant Color"
```

**Behavior**:
- Set to `"All"` (default) → no activity metric filtering applied
- Set to any other value → backend filters to days where that metric would show a non-empty cell
- Frontend: Legend swatch shows active visual state (glow/border) when the current metric mode matches the filter value

### Legend Interactivity Contract

**Visual Feedback**:
- Swatches are rendered as `<button>` elements (not `<span>`)
- On click: set `input_select.print_history_filter_activity_metric` to the current mode
- Clicking again (when already set) clears the filter
- Active swatch gets a visual indicator (e.g., border, box-shadow, highlight)

**Interaction Flow**:
1. User views heatmap in "Single vs Multi-Color Prints" mode
2. User clicks legend swatch for "More multi-color" end of spectrum
3. Click handler reads current metric mode → sets filter to "Single vs Multi-Color Prints"
4. Card triggers re-render via filter change
5. Backend query runs with activity metric filter applied
6. Heatmap shows only days with prints (all visible days are multi-color-leaning)
7. Click again → clears filter → full heatmap returns

**Mobile Behavior**:
- Legend renders on mobile (same as desktop)
- Click targets remain accessible with same size/spacing

### Backend Query Changes

**New Parameter**: `activity_metric_filter` (optional, string)

**Semantics**: When provided and not `"All"`, filter to days where the specified metric produces a non-empty value or category match.

**Behavior**:
- `"Single vs Multi-Color Prints"` → include only days with single-color or multi-color prints
- `"In a Project vs Not in a Project"` → include only days with project or non-project prints
- `"Enrichment Status"` → include only days with enrichment data
- `"Outcome"` → include only days with success/failure/cancel outcomes
- For intensity-based metrics (Print Count, Filament Weight, etc.) → include days with non-zero values

**Backward Compatibility**: Omitting the parameter or passing `"All"` returns unfiltered results (current behavior).

### Frontend Card Changes

**Legend Rendering** (`_renderLegend` method):
- Make swatches clickable buttons instead of static spans
- Add click handler that calls new method `_handleLegendMetricClick()`
- Apply active styling when filter matches current mode

**New Method** (`_handleLegendMetricClick`):
- Get current heatmap metric mode
- Compare with current filter state
- If no filter set → set filter to current mode
- If filter already matches → clear filter
- Call HA service to update the filter entity

**Filter Propagation**:
- Existing `set hass()` method already watches all input_select entities
- No additional watchers needed
- Filter change triggers standard `_queueRender()` flow

### Styling

**Active Legend Swatch**:
```css
.legend-swatch.active {
  box-shadow: 0 0 8px rgba(37, 99, 235, 0.6),
              inset 0 0 0 2px rgba(37, 99, 235, 1);
  border-radius: 6px;
}
```

**Hover State**:
```css
.legend-swatch {
  cursor: pointer;
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.legend-swatch:hover {
  transform: scale(1.1);
}

.legend-swatch:active {
  transform: scale(0.95);
}
```

### Important Guardrails

1. **Do not disable legend interactivity**: If a mode has no legend (e.g., Dominant Color returns `null` legend), the mode itself is not clickable, but other modes' swatches remain interactive.

2. **Filter clears when mode changes**: If user is viewing "Single vs Multi-Color Prints" with a filter set, and then selects "Print Count" mode via the mode selector, the activity metric filter should clear automatically (same metric mode, different behavior).

3. **Summary reflects filter**: The summary chip display should ideally show when a heatmap filter is active (e.g., "Filtered to: Single Color Prints"). This is optional for MVP but recommended for UX clarity.

4. **No interaction during loading**: If a refresh is in progress, disable legend clicks until render completes.

5. **Preserve other filters**: Setting an activity metric filter does not affect existing filters (status, material, printer, etc.). All filters compose additively.

### Testing Checklist

- [ ] Click legend swatch → filter entity updates
- [ ] Heatmap re-renders with filtered days only
- [ ] Legend swatch shows active state
- [ ] Click again → filter clears → full heatmap returns
- [ ] Switch to different metric mode → activity filter clears (if needed)
- [ ] Mobile: legend swatches are clickable and responsive
- [ ] Performance: filter change takes same time as other filter changes
- [ ] Print details section updates to show prints from visible days
- [ ] Multi-select actions still work with filtered heatmap
- [ ] Other filters (status, material, etc.) compose correctly with activity metric filter

### Future Enhancements

1. **Multi-metric filtering**: Allow "OR" logic to select multiple metric values (e.g., "Multi-Color OR In a Project")
2. **Keyboard shortcuts**: Alt+Click to clear all filters, Shift+Click for multi-select
3. **Filter persistence**: Save activity metric filter to browser localStorage
4. **Quick-filter chips**: Add inline chips showing active metric filter below legend
5. **Intensity-based range selection**: For continuous metrics, allow clicking to set a min/max range

