# Issue #1127 Implementation: Heatmap Legend Filtering

## Summary
Implemented the ability to click on heatmap legend swatches to filter the heatmap and results to only show days matching that legend value.

## Architecture Overview

### Data Flow
1. **Frontend (JavaScript Card)**: User clicks legend swatch â†’ Sets filter entity value
2. **Helper Entity**: `input_select.print_history_filter_activity_metric` stores the selected filter value
3. **WebSocket Query**: Heatmap card sends `activity_metric_filter` parameter to backend
4. **Backend Processing**: Filter logic in `_matching_archive_ids()` filters archives based on metric
5. **Results**: Only archives matching the selected metric value are returned

### Key Components

#### 1. Frontend Changes (heatmap card)
**File**: `homeassistant/www/3d_printing/print_history/print-history-activity-heatmap-card.js`

- **Config Option**: `activity_metric_filter_entity` (defaults to `input_select.print_history_filter_activity_metric`)
- **Data Signature**: Added `activityMetricFilter` to track filter entity state changes
- **Legend Rendering**: Updated `_renderLegend()` to:
  - Attach data attributes to swatches: `data-legend-value`, `data-swatch-index`
  - Add "active" CSS class when swatch matches current filter
  - Attach click handlers to each swatch
- **Legend Value Mapping**: New `_getLegendValuesForMode()` function maps color indices to filter values:
  - **Outcome**: `["Stopped", "Failed", "Failed", "Complete", "Complete"]`
  - **Single vs Multi-Color**: `["Single Color", "Single Color", "Multi-Color", "Multi-Color", "Multi-Color"]`
  - **Enrichment Status**: `["Pending", "Pending", "Pending", "Complete", "Complete"]`
  - **In a Project vs Not in a Project**: `["In a Project", "In a Project", "Not in a Project", "Not in a Project", "Not in a Project"]`
- **Click Handler**: `_handleLegendSwatchClick()` toggles between filter value and "All"
- **WebSocket Query**: Passes `activity_metric_filter` parameter to backend

#### 2. Helper Entity (Input Select)
**File**: `homeassistant/packages/3d_printing/print_history/helpers/input_select/input_select_print_history_filter_activity_metric.yaml`

Options:
- `All` (default - no filtering)
- `Complete`
- `Failed`
- `Stopped`
- `Single Color`
- `Multi-Color`
- `Pending`
- `In a Project`
- `Not in a Project`

#### 3. Backend Changes

##### manager.py
- Added `"activity_metric_filter": "input_select.print_history_filter_activity_metric"` to `QUERY_OVERRIDE_ENTITY_MAP`

##### store.py (_query_filters)
- Extracts `activity_metric_filter` from states and stores in filter dict:
  ```python
  "activity_metric_filter": states.get("input_select.print_history_filter_activity_metric", "All").strip()
  ```

##### store.py (_matching_archive_ids)
- Added filtering logic for each supported activity mode:

**Outcome Mode**:
- Maps filter values to status codes: `"Complete" â†’ "completed"`, `"Failed" â†’ "failed"`, etc.
- Filters: `LOWER(a.status) = ?`

**Single vs Multi-Color Mode**:
- Counts distinct filament colors using archive_filament_rows table
- `Single Color`: `COUNT(DISTINCT colors) <= 1`
- `Multi-Color`: `COUNT(DISTINCT colors) > 1`

**Enrichment Status Mode**:
- Maps enrichment status values
- Filters: `LOWER(a.enrichment_status) = ?`

**Project Membership Mode**:
- `In a Project`: `TRIM(COALESCE(a.project_name, '')) != ''`
- `Not in a Project`: `TRIM(COALESCE(a.project_name, '')) = ''`

##### query.py
- Added new filter to `ACTIVE_FILTER_DEFAULTS`:
  ```python
  "input_select.print_history_filter_activity_metric": "All"
  ```

#### 4. Resource Versioning
- Updated `homeassistant/packages/3d_printing/common/dashboards/_resources.yaml`
- Incremented heatmap card version: `v=58` â†’ `v=59`

## Usage

1. **Select Activity Metric**: Use the existing "Print History Activity Metric" selector to choose the metric (Outcome, Single vs Multi-Color, etc.)
2. **View Heatmap**: The heatmap displays colored days based on the selected metric
3. **Click Legend**: Click any swatch in the legend to filter
4. **See Results**: Only archives matching that metric value are displayed
5. **Clear Filter**: Click the same swatch again to return to "All"

## Examples

### Filtering by Outcome
1. Set activity metric to "Outcome"
2. Legend shows: Cancelled/Failed â† â†’ Completed
3. Click the green swatch to see only completed prints
4. Heatmap refilters to show only days with completed prints

### Filtering by Single vs Multi-Color
1. Set activity metric to "Single vs Multi-Color Prints"
2. Legend shows: More single-color â† â†’ More multi-color
3. Click the purple swatch to see only multi-color prints
4. Results update immediately

## Testing Checklist

- [ ] Legend swatches are clickable
- [ ] Clicking a swatch updates the filter entity
- [ ] Heatmap days update to show only matching archives
- [ ] Details section shows only filtered results
- [ ] Clicking the same swatch again clears the filter
- [ ] "All" value shows full results
- [ ] Works for all metric modes: Outcome, Single vs Multi-Color, Enrichment Status, Project Membership
- [ ] Filter persists when changing other dashboard filters
- [ ] Browser cache is cleared (use Ctrl+Shift+R) to load v=59

## Performance Considerations

- Filtering is done at query time in the SQL WHERE clause (not post-processing)
- For "Single vs Multi-Color", uses a correlated subquery which may be slower than other filters
- Archive rows are cached by the heatmap card to minimize re-queries

## Future Enhancements

1. Add filtering for "Number of Duplicates" mode
2. Add filtering for "Number of Favorites" mode  
3. Add filtering for "Dominant Color" mode (would need special handling)
4. Support multi-select filtering (hold Shift to add/remove multiple values)
5. Add visual indicators for which swatch is currently filtered

## Related Files

- Design Documentation: `
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/browser/heatmap-legend-filtering.md



`
- Filter Architecture: `
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/
docs/features/print_history/design/browser/filter-sort-design.md



`
- Archive Browser API: `homeassistant/custom_components/bambuddy/print_history/store.py`
- Heatmap Card: `homeassistant/www/3d_printing/print_history/print-history-activity-heatmap-card.js`


