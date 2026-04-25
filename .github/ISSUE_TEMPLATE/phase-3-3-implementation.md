---
name: Phase 3.3 Implementation Task
about: Track Phase 3.3 implementation task (Cross-System Integration)
title: "[Phase 3.3] "
labels: phase-3, enhancement, model-catalog
assignees: ''
---

## Phase 3.3: Cross-System Integration

**Objective**: Enable seamless navigation between models, archives, and projects

**Scope**:
- Enhanced archive linking and filtering
- Related models display (by similarity)
- Navigation services (model ↔ archive ↔ project)
- Model print history timeline
- Cross-system search (optional)

**Effort**: 25-30 hours | **Priority**: MEDIUM-LOW

---

## Implementation Tasks

### Archive Integration

- [ ] **Enhanced Archive Linking** (model-detail-popup-card.js)
  - Archive grid view with thumbnails
  - Filter options: All / Successful only / Failed only
  - Sort options: Date (newest) / Date (oldest) / Filament
  - Archive card: Click to view detail
  - Archive card: Print again button
  - Tests: `test_linked_archives.spec.ts`

- [ ] **Archive Detail Enhancement** (print-history-archive-actions-card.js)
  - Add "View Source Model" button
  - Add "Edit Model Metadata" button
  - Add "Similar Models" button
  - Tests: `test_archive_to_model_navigation.spec.ts`

### Related Models

- [ ] **Related Models Component** (`model-detail-related-models.js`)
  - Display similar models grid
  - Show similarity score (0-100%)
  - Show relationship reason (same creator, collection, tags)
  - Click to navigate to model
  - Tests: `test_related_models_component.spec.ts`

- [ ] **Related Models Endpoint** (`GET /api/models/{model_ref}/related`)
  - Similarity scoring algorithm:
    - Same collection: +30 points
    - Same creator: +25 points
    - Matching tags: +5 per tag
    - Matching keywords: +3 per keyword
  - Return top 5 models with scores
  - Tests: `test_related_models_endpoint.py`

### Navigation Services

- [ ] **model_catalog.navigate_to_model** Service
  - Open model detail popup
  - Track navigation source (for logging)
  - Tests: `test_navigate_to_model_service.py`

- [ ] **model_catalog.queue_model_for_print** Service
  - Add model to print queue
  - Optional: Specify file and settings
  - Tests: `test_queue_model_service.py`

- [ ] **print_history.navigate_to_linked_model** Service
  - Navigate from archive to source model
  - Tests: `test_navigate_from_archive_service.py`

### Optional Features (Phase 3.3+)

- [ ] **Model Timeline View** (`model-timeline-card.js`)
  - Horizontal timeline of all prints (last 6 months)
  - Show success/fail/stopped status
  - Hover for details
  - Click to navigate to archive
  - Tests: `test_model_timeline.spec.ts`

- [ ] **Cross-System Search** (unified_search.yaml)
  - REST sensor combining models + archives + projects
  - Endpoint: `GET /api/search?q=query`
  - Return combined results by type
  - Tests: `test_cross_system_search.py`

- [ ] **Project Integration** (future)
  - Link projects to models
  - Navigate project → model → archive

### Documentation & Testing

- [ ] Documentation: `phase-3.3-service-examples.yaml`
- [ ] Test Suite: 10+ tests covering all scenarios
- [ ] Navigation Flow Diagrams
- [ ] Implementation Guide: `phase-3.3-implementation-guide.md` ✅

---

## Testing Requirements

### Unit Tests
```
tests/phase3/
├── test_related_models_endpoint.py
├── test_navigation_services.py
├── test_archive_model_linking.py
└── test_cross_system_search.py
```

### Integration Tests
```
tests/e2e/
├── model_detail_related_models.spec.ts
├── model_detail_archive_navigation.spec.ts
├── archive_detail_to_model_navigation.spec.ts
├── model_timeline_view.spec.ts
└── cross_system_navigation_flow.spec.ts
```

### Manual Testing Checklist
- [ ] Archive grid renders with thumbnails
- [ ] Archive filter works (all/successful/failed)
- [ ] Archive sort works (date/filament)
- [ ] Click archive opens detail popup
- [ ] Print again button works
- [ ] Related models displayed
- [ ] Related models show similarity scores
- [ ] Click related model opens detail
- [ ] Archive detail shows "View Source Model" button
- [ ] Navigation back to model from archive works
- [ ] No performance regression (<100ms per navigation)

---

## Success Criteria

- ✅ Archive linking UI enhanced with filters/sorting
- ✅ Related models displayed with similarity scores
- ✅ Navigation services functional
- ✅ Model ↔ Archive navigation seamless
- ✅ 10+ tests pass
- ✅ Documentation complete
- ✅ No performance regression

---

## Dependencies

- Phase 3.0 MVP ✅
- Phase 3.1 (recommended, not blocking)
- print_history module ✅
- Sidecar service for related models endpoint

---

## Parallel Development

- Phase 3.1 and 3.2 can run in parallel with 3.3
- No hard dependencies between phases
- All phases follow Phase 3.0 architecture patterns

---

## References

- Implementation Guide: [phase-3.3-implementation-guide.md](../../docs/features/model_catalog/phase-3.3-implementation-guide.md)
- Roadmap: [phase-3.1-3.3-roadmap.md](../../docs/features/model_catalog/phase-3.1-3.3-roadmap.md)
- Design: [phase-3-detail-view-design.md](../../docs/features/model_catalog/phase-3-detail-view-design.md)
- Print History: [../print_history/](../../docs/features/print_history/)

---

## Navigation Flow Diagram

```
Model Detail Popup
├─ Archive 1 [Click] ──→ Archive Detail Popup
│  └─ [View Source Model] ──→ Model Detail (back to top)
├─ Archive 2 [Click] ──→ Archive Detail Popup
└─ Related Model [Click] ──→ Model Detail Popup

From Archive Detail:
├─ [View Source Model] ──→ Model Detail
├─ [Edit Model Metadata] ──→ Model Detail (edit tab)
└─ [Similar Models] ──→ Model Detail with "Related" tab
```

---

## Checklist

- [ ] Implementation started
- [ ] All tasks completed
- [ ] All tests passing
- [ ] Code reviewed
- [ ] Documentation updated
- [ ] Ready for release

---

/label phase-3 enhancement model-catalog
/assign @developer-name
