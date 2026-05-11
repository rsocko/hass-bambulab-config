# Print Queue Integration Guide

## Overview

The unified print queue package (`print_queue`) manages the Bambu Lab printer queue with intelligent features for filtering, sorting, planning, and archive suggestion matching.

## Architecture

```
homeassistant/
├── packages/3d_printing/
│   ├── print_queue/                     # New package
│   │   ├── print_queue_loader.yaml      # Feature loader (auto-included)
│   │   ├── dashboard_views/
│   │   │   └── print_queue_board.yaml   # Main Lovelace view
│   │   ├── MIGRATION_CHECKLIST.md       # User migration guide
│   │   └── DEPLOYMENT_VALIDATION.md     # Deployment checklist
│   ├── bambuddy_common/                 # Required: API config, webhook receiver
│   ├── print_history/                   # Related: Archive browsing, photo management
│   ├── print_statistics/                # Related: Stats dashboard
│   └── model_catalog/                   # Related: Model selection in add modal
└── www/3d_printing/
    └── print_queue/
        └── unified-queue-board-card.js  # Custom card (v=7)
```

## Dependencies

### Required Packages
- **bambuddy_common** - Provides API client config and webhook receiver
  - Needed for REST API integration with Bambuddy backend
  - Queue API endpoints: `/api/v1/queues/{printer_id}/entries`, etc.

### Related Packages
- **print_history** - Archive browsing and photo management
  - Entry detail drawer links to archives in print_history browser
  - Suggestion feature matches queued jobs to printed archives
- **model_catalog** - 3D model catalog
  - Add modal searches catalog for source selection
  - Quick add pulls from model catalog
- **print_statistics** - Statistics dashboard
  - Could pull failed job stats to inform planner decisions
  - Display alongside queue statistics

## Feature Integration Points

### 1. Add to Queue Modal

```
Add Modal (print_queue)
    ↓
    ├→ Catalog Models (model_catalog)
    │  └→ Model detail and thumbnails
    ├→ Working Groups (bambuddy_common)
    │  └→ Working file selections
    └→ POST /api/v1/queues/{printer_id}/add (bambuddy_common)
```

### 2. Medium-Confidence Suggestions

```
Suggestions Banner (print_queue)
    ↓
    ├→ Archive linkage from (print_history)
    │  └→ Display archive metadata
    └→ User Accept/Reject actions
        └→ Links queue entry to archive
            └→ Print History browser shows linked print
```

### 3. Queue Planner

```
Planner (print_queue)
    ↓
    ├→ Strategies: Aggressive, Balanced, Lazy
    ├→ Fetches entry data from /api/v1/queues/{printer_id}/entries
    ├→ Calculates optimal order based on:
    │  ├→ ams_score_pct (AMS-ready hours)
    │  ├→ overnight_fit_minutes (overnight capability)
    │  └→ estimated_total_minutes (job duration)
    └→ Applies via POST /api/v1/queues/{printer_id}/plan/apply
```

### 4. Entry Detail Drawer

```
Detail Drawer (print_queue)
    ↓
    ├→ File selection visualization
    ├→ Plate completion progress
    └→ Archive Linkage
        └→ Link to print_history browser
            └→ View full archive details, photos, etc.
```

## API Contract

### Queue Entries Endpoint

**Endpoint**: `GET /api/v1/queues/{printer_id}/entries`

**Response**:
```json
{
  "entries": [
    {
      "queue_entry_id": "entry_abc123",
      "title": "Calibration Cube",
      "source_kind": "catalog_model",
      "source_id": "model_xyz789",
      "state": "todo",
      "rank": 1,
      "copies_requested": 1,
      "estimated_total_minutes": 60,
      "ams_score_pct": 95,
      "overnight_fit_minutes": 420,
      "last_attempt_outcome": "success",
      "last_archive_id": "archive_123",
      "selected_files": [
        {"file_id": "f1", "file_name": "cube.3mf", "selected": true}
      ]
    }
  ]
}
```

### Suggestions Endpoint

**Endpoint**: `GET /api/v1/queues/{printer_id}/suggestions?status=suggested`

**Response**:
```json
{
  "suggestions": [
    {
      "suggestion_id": "sugg_001",
      "queue_entry_id": "entry_abc123",
      "archive_id": "archive_456",
      "confidence": "medium",
      "match_method": "fuzzy_model",
      "reasons": ["filename contains 'cube'", "model UUID match"],
      "status": "suggested"
    }
  ]
}
```

### Planner History Endpoint

**Endpoint**: `GET /api/v1/queues/{printer_id}/plan/history`

**Response**:
```json
{
  "history": [
    {
      "timestamp": "2026-05-10T14:30:00Z",
      "strategy": "balanced",
      "entries_reordered": 3
    }
  ]
}
```

### Planner Preview Endpoint

**Endpoint**: `GET /api/v1/queues/{printer_id}/plan/preview?strategy={strategy}`

**Response**:
```json
{
  "planned_order": [
    {
      "queue_entry_id": "entry_abc123",
      "title": "Calibration Cube",
      "reason": "Fits overnight window (420 min AMS ready)"
    }
  ]
}
```

## Deployment Workflow

### 1. Feature Flag: Enable in Loader

Edit `homeassistant/packages/3d_printing/_feature_loaders.yaml`:
```yaml
print_queue_loader: !include print_queue/print_queue_loader.yaml
```

### 2. Lovelace Dashboard Integration

Add to main dashboard or create new view:
```yaml
type: custom:unified-queue-board-card
printer_id: p1
```

### 3. Clear Cache & Reload

```bash
# Browser cache clear + hard refresh (Ctrl+Shift+R)
# Home Assistant reload: Reload custom components (Developer Tools)
```

### 4. Validate

Run tests:
```bash
pytest tests/print_queue/ -v
```

Check browser console for errors:
- Press F12 → Console tab
- Look for 404s or JavaScript errors

## Customization Points

### Change Auto-Refresh Interval

In `unified-queue-board-card.js`, locate `_refreshTimer`:
```javascript
this._refreshTimer = setInterval(() => this._loadQueueData(), 30000);  // 30 seconds
```

Change `30000` to desired milliseconds (e.g., `60000` for 60 seconds).

### Modify Default Filters

In `unified-queue-board-card.js`, locate `_filters` constructor:
```javascript
this._filters = {
  states: ['todo', 'ready', 'started', 'blocked'],  // Default states
  sources: [],  // Empty = all sources
  sort: 'rank',  // Default sort
};
```

### Adjust Strategy Weights

In planner backend, customize strategy scoring for your use case:
- **Aggressive**: Maximize overnight capability
- **Balanced**: Mix AMS and overnight
- **Lazy**: Prioritize AMS-ready jobs

## Troubleshooting

### Card Not Rendering

1. Check resource URL in `_resources.yaml`
  - Should be: `/local/3d_printing/print_queue/unified-queue-board-card.js?v=8`

2. Hard refresh browser (Ctrl+Shift+R)

3. Check browser console (F12)
   - Look for 404 errors
   - Look for JavaScript syntax errors

4. Verify feature loader is enabled

### API Endpoints Returning 404

1. Verify Bambuddy service is running
   - Check running containers: `docker ps | grep bambuddy`
   - Check service logs: `docker logs bambuddy`

2. Verify printer_id matches configuration
   - Default: `p1`
   - Check your printer's ID in settings

3. Test endpoint directly:
   ```bash
   curl -v http://localhost:8080/api/v1/queues/p1/entries
   ```

### Queue Not Updating

1. Check auto-refresh interval is running
   - Should see network requests every 30 seconds in F12 → Network tab

2. Verify API responses are valid
   - Check F12 → Network tab → Response tab

3. Check browser console for JavaScript errors

## Performance Considerations

### Large Queues (100+ entries)

- Filter to relevant states to reduce rendered items
- Consider increasing auto-refresh interval from 30s to 60s
- Virtualize queue list if performance degrades (future optimization)

### Network Latency

- Add modal may feel slow on high-latency connections
- Consider caching source options in browser storage

### Browser Compatibility

- Requires ES2020+ support (modern Chrome, Firefox, Safari, Edge)
- No IE11 support

## Future Enhancements

- [ ] Batch operations (reorder multiple entries, delete group)
- [ ] Queue import/export (save queue states)
- [ ] Advanced planner with AI optimization
- [ ] Archive preview in add modal
- [ ] Keyboard shortcuts for power users
- [ ] Dark/light theme toggle
- [ ] Printer-specific queue presets

## Support

For issues or questions:
1. Check [MIGRATION_CHECKLIST.md](./MIGRATION_CHECKLIST.md) for common problems
2. Review issue #1429 and related issues
3. File new issue with reproduction steps and browser logs
