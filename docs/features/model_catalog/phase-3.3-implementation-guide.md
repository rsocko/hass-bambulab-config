# Phase 3.3 Implementation Guide: Cross-System Integration

**Scope**: Archive linking, related models, navigation, timeline  
**Effort**: 25-30 hours  
**Priority**: MEDIUM-LOW  
**Status**: Ready for Development

**Post-Manyfold mapping**: legacy `Phase 3.3` splits across current **Phase 4** UI continuity and current **Phase 6** search/navigation work. Project-aware navigation now belongs with the current Phase 9 project-integration track.

---

## Overview

Phase 3.3 creates seamless navigation between models and archives, with project-aware navigation deferred to the later project-integration track. Users can:
- Click linked archives to view print details
- Browse related models by similarity
- Navigate between model and print surfaces
- View model print history timeline
- Search unified across all concepts

---

## Architecture

### Components

1. **model-detail-related-models.js** (New)
   - Display similar models with similarity score
   - Click to navigate to model detail

2. **model-detail-popup-card.js** (Enhanced)
   - Enhanced archive linking UI
   - Archive click-to-detail action
   - Cross-system navigation buttons

3. **Sidecar Endpoints** (New)
   - `GET /api/models/{model_ref}/related` — Similar models
   - `GET /api/archives/{archive_id}/model` — Navigate archive → model

4. **HA Services** (New)
   - `model_catalog.navigate_to_model` — Open model detail
   - `print_history.navigate_to_model` — From archive to model
   - `model_catalog.queue_model_for_print` — historical reference (retired; use unified queue commands)

---

## Implementation Tasks

### Task 1: Enhanced Archive Linking
**File**: `homeassistant/www/3d_printing/model_catalog/model-detail-popup-card.js`  
**Method**: `_renderLinkedPrintsTab()`

**Features**:
- Archive list with thumbnails
- Click to open archive detail popup
- Show archive status (success, failed, printing, etc.)
- Filter options: "Show all" / "Show successful only"
- Sorting: By date (newest first), by filament, by status

**Current Behavior** (Phase 3.0):
```
Linked Prints Tab:
  • Archive 1 (2026-04-20) — Successful
  • Archive 2 (2026-04-18) — Failed
  ...
```

**Enhanced Behavior** (Phase 3.3):
```
Linked Prints Tab:
  [Filter: All ▼] [Sort: Date ▼]
  
  Archive Grid:
  ┌─────────────────────────────────────┐
  │ [thumbnail]  Arch #100              │
  │ 2026-04-20 · 4h 30m · PLA           │
  │ Status: ✅ Successful               │
  │ [View Details] [Print Again]        │
  └─────────────────────────────────────┘
  
  ┌─────────────────────────────────────┐
  │ [thumbnail]  Arch #99               │
  │ 2026-04-18 · 3h 20m · PETG          │
  │ Status: ❌ Failed (spaghetti)       │
  │ [View Details] [Analyze] [Retry]    │
  └─────────────────────────────────────┘
```

**Implementation**:
```javascript
_renderLinkedPrintsTab() {
  const filters = this._createArchiveFilters();
  const archives = this._filterAndSortArchives(this._model.linked_archives);
  
  return html`
    <div class="linked-prints-container">
      <div class="archive-filters">
        <select @change=${this._onFilterChange}>
          <option>Show all archives</option>
          <option>Show successful only</option>
          <option>Show failed only</option>
        </select>
        <select @change=${this._onSortChange}>
          <option>Sort by date (newest)</option>
          <option>Sort by date (oldest)</option>
          <option>Sort by filament</option>
        </select>
      </div>
      
      <div class="archive-grid">
        ${archives.map(archive => this._renderArchiveCard(archive))}
      </div>
    </div>
  `;
}

_renderArchiveCard(archive) {
  return html`
    <div class="archive-card" @click=${() => this._openArchiveDetail(archive)}>
      <img src="${archive.thumbnail_url}" />
      <div class="archive-meta">
        <h4>Archive #${archive.id}</h4>
        <p>${formatDate(archive.created_at)} · ${formatDuration(archive.duration)} · ${archive.filament}</p>
        <p class="status ${archive.status}">${archive.status_label}</p>
      </div>
      <div class="archive-actions">
        <button @click=${() => this._openArchiveDetail(archive)}>View Details</button>
        <button @click=${() => this._printAgain(archive)}>Print Again</button>
      </div>
    </div>
  `;
}
```

**Tests**:
```bash
tests/e2e/model_detail_linked_archives.spec.ts
```

---

### Task 2: Related Models Display
**File**: `homeassistant/www/3d_printing/model_catalog/model-detail-related-models.js`

**Feature**: New component showing similar models

**UI**:
```
Related Models:
┌─────────────────────────────────────┐
│ Gridfinity Organizer (92% match)     │
│ [thumbnail]                         │
│ By: Same Creator                    │
│ [View Model]                        │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ Tool Holder (88% match)             │
│ [thumbnail]                         │
│ By: Similar Collection              │
│ [View Model]                        │
└─────────────────────────────────────┘
```

**Sidecar Endpoint**: `GET /api/models/{model_ref}/related`
```python
@app.get("/api/models/{model_ref}/related")
async def get_related_models(model_ref: str, limit: int = 5):
    """Get related models by similarity."""
    model = resolve_model_ref(model_ref)
    
    # Similarity scoring:
    # - Same collection: +30 points
    # - Same creator: +25 points
    # - Matching tags: +5 per tag
    # - Matching keywords: +3 per keyword
    
    related = []
    for other in all_models:
        if other.model_id == model.model_id:
            continue
        
        score = 0
        if other.collection_id == model.collection_id:
            score += 30
        if other.creator_id == model.creator_id:
            score += 25
        score += 5 * len(set(other.tags) & set(model.tags))
        score += 3 * len(set(other.keywords) & set(model.keywords))
        
        if score > 0:
            related.append({"model": other, "similarity": min(100, score)})
    
    # Sort and limit
    related.sort(key=lambda x: x["similarity"], reverse=True)
    return {"related_models": related[:limit]}
```

**Tests**:
```bash
tests/phase3/test_related_models_endpoint.py
tests/e2e/model_detail_related_models.spec.ts
```

---

### Task 3: Navigation Services
**File**: `homeassistant/packages/3d_printing/model_catalog/services/`

**New Services**:

#### model_catalog.navigate_to_model
```yaml
description: Open model detail popup
fields:
  model_ref:
    description: Model reference
    example: "gridfinity-bin"
  source:
    description: Where navigation originated (for logging)
    example: "archive_detail"
```

#### model_catalog.queue_model_for_print (historical, retired)
```yaml
description: Add model to print queue
fields:
  model_ref:
    description: Model reference
  file_id:
    description: Specific file to print (optional)
  settings:
    description: Print settings override (optional)
    example:
      bed_temp: 60
      nozzle_temp: 210
```

#### print_history.navigate_to_linked_model
```yaml
description: Navigate from archive to source model
fields:
  archive_id:
    description: Archive ID
```

**Implementation** (HA Automation Example):
```yaml
automation:
  - alias: "Open Model Detail from Archive"
    trigger:
      platform: event
      event_type: archive_action
      event_data:
        action: view_model
    action:
      - service: browser_mod.popup
        data:
          title: "{{ event.data.model_name }}"
          size: wide
          content:
            type: custom:model-detail-popup-card
            model_ref: "{{ event.data.model_ref }}"
```

**Tests**:
```bash
tests/phase3/test_navigation_services.py
```

---

### Task 4: Archive Detail Integration
**File**: `homeassistant/www/3d_printing/print_history/print-history-archive-actions-card.js`

**Enhancement**: Add "View Source Model" button/action
```
Archive Detail Card:
  [Archive #100]
  [... existing fields ...]
  
  [View Source Model] [Edit Model Metadata] [Similar Models]
  └─ Calls: model_catalog.navigate_to_model
```

**Reverse Navigation** (Archive → Model):
```javascript
onViewSourceModel() {
  const modelRef = this._archive.model_ref || this._archive.model_public_id;
  
  this._hass.callService('browser_mod', 'popup', {
    title: this._archive.model_name,
    size: 'wide',
    content: {
      type: 'custom:model-detail-popup-card',
      model_ref: modelRef,
    }
  });
}
```

---

### Task 5: Model Timeline View (Optional)
**File**: `homeassistant/www/3d_printing/model_catalog/model-timeline-card.js`

**Feature** (Can defer to Phase 3.3+):
- Horizontal timeline of all prints of this model
- Show date, duration, status, filament, result
- Hover to see details
- Click to navigate to archive

**UI**:
```
Model Print Timeline (Last 6 months):
┌──────────────────────────────────────────────┐
│ ✅ ✅ ❌ ✅ ✅ ✅ ❌ ✅ ✅ ✅        │
│ Apr  May  Jun  Jul  Aug  Sep  Oct  Nov  Dec │
│ (hover: 2026-04-20, 4h 30m, Success)        │
└──────────────────────────────────────────────┘

Legend:
✅ Success  ❌ Failed  ⏸ Stopped  🔄 In Progress
```

---

### Task 6: Cross-System Search (Optional)
**File**: `homeassistant/packages/3d_printing/model_catalog/sensors/unified_search.yaml`

**Feature** (Can defer):
- REST sensor that searches models, archives, projects
- Returns combined results with type indicator
- Used by dashboard search card

**Endpoint**: `GET /api/search?q=gridfinity`
```python
@app.get("/api/search")
async def search(q: str, limit: int = 20):
    """Unified search across models, archives, projects."""
    results = {
        "models": search_models(q, limit=5),
        "archives": search_archives(q, limit=5),
        "projects": search_projects(q, limit=5),
    }
    return results
```

---

## Testing Strategy

### Unit Tests (Python/pytest)
```
tests/phase3/
├── test_related_models_endpoint.py
├── test_navigation_services.py
├── test_archive_model_linking.py
└── test_cross_system_search.py
```

### Integration Tests (Playwright)
```
tests/e2e/
├── model_detail_related_models.spec.ts
├── model_detail_archive_navigation.spec.ts
├── archive_detail_to_model_navigation.spec.ts
├── model_timeline_view.spec.ts
└── cross_system_navigation_flow.spec.ts
```

---

## Success Criteria

- ✅ Archive linking UI enhanced with filters/sorting
- ✅ Related models displayed with similarity scores
- ✅ Click archive to view archive detail
- ✅ Click archive to queue for reprint
- ✅ Archive detail can navigate to model
- ✅ Navigation services work smoothly
- ✅ 10+ tests pass
- ✅ Documentation complete
- ✅ No performance regression (<100ms per navigation)

---

## Dependencies

- Phase 3.0 MVP ✅ (required)
- print_history module ✅ (for archive linking)
- Sidecar service for related models endpoint

---

## Rollback Plan

If Phase 3.3 causes issues:
1. Disable related models display
2. Disable navigation services
3. Revert archive card to Phase 3.0 view
4. Revert model detail card to read-only

---

## References

- Phase 3.0 Implementation: [phase-3-implementation-guide.md](phase-3-implementation-guide.md)
- Print History Design: [../print_history/](../print_history/)
- Design Document: [phase-3-detail-view-design.md](phase-3-detail-view-design.md)
