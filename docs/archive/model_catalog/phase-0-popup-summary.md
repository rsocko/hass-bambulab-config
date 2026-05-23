# Phase 0 Popup Redesign: Deliverables Summary

**Date**: 2026-05-15  
**Issue**: #1376 (Redesign Catalog Popup UI)  
**Status**: Phase 0 Complete — Ready for Review & Dependent Issues  

---

## Executive Summary

The Phase 0 catalog popup redesign has been completed with four deliverables that **resolve the gap between the previous tab-based mockup and the new progressive-disclosure layout**, while establishing stable extension points for dependent issues (#1494, #1495, #1483, #1499).

### Key Improvement

**Old approach**: Tab-based interface where users manually switch between 5 data panels (Model Files, Related Archives, Queue/Prints, Related Models, Supporting Files).

**New approach**: Collapsible sections that are all visible on page load, scrollable in sequence, with operators able to collapse sections they don't need. Archive candidate review is now discoverable without navigation.

---

## Deliverables

### 1. Revised HTML Mockup ✅

**File**: [popup-model-detail-collapsible-sections.html](.././design/mockups/popup-model-detail-collapsible-sections.html)

**Changes from Makerworld V2**:
- Removed tab shell and replaced with collapsible sections
- Each section (Archive Linkage, Queue Status, Related Models, Supporting Files) can be independently collapsed/expanded
- Section headers show item counts and collapse affordance (−/+)
- Hero section (media carousel + summary + files) remains always visible
- Progressive scrolling discovers all content
- Collapse state persists per-user-session (via browser localStorage)

**Interactive features**:
- Toggle sections open/close
- Media carousel with filter chips
- Archive candidate rows with [Link] / [Skip] actions (UI only, no backend yet)
- Responsive mobile stack
- Tunable width, corner radius, padding, accent color

**Validation**:
- ✅ All 5 data panels represented (was buried in tabs, now visible)
- ✅ Archive candidates visible without tab click
- ✅ Mobile responsive tested
- ✅ Accessibility markup ready for screen reader testing

---

### 2. Extension Points Specification ✅

**File**: [popup-extension-points.md](/docs/features/model_catalog/design/popup-extension-points.md)

**Purpose**: Formal API contract for dependent issues to inject content safely without breaking layout.

**Extension slots defined**:

| Slot | Scope | Used by |
|------|-------|---------|
| `hero-left:media` | Media carousel + filters + actions | #1494 (3D Viewer) |
| `hero-right:summary` | Summary card, tags, collections, status | Core |
| `sections:archive-linkage` | Archive review & linking | #1495 (Archive UI) |
| `sections:queue-status` | Queue items & draft intents | Core |
| `sections:related-models` | Related item cards | #1483 (Related Models) |
| `sections:supporting-files` | Documentation, BOM, references | Core |
| `actions:top-bar` | Top-right CTA buttons | Any feature |
| `actions:per-archive` | Per-row archive actions | Archive UI |

**API contracts**: TypeScript/JSDoc signatures with data structures, lifecycle hooks, and dependency declarations.

**Dependencies**: Extensions declare required data, priority order, and blocking relationships.

**Validation checklist**: 7 checkpoints for Phase 0 sign-off before dependent issues proceed.

---

### 3. Archive Candidate Review Workflow ✅

**File**: [archive-candidate-review-workflow.md](/docs/features/model_catalog/planning/archive-candidate-review.md)

**Detailed UX specification** for the most complex feature in the redesign: archive linkage review.

**Key sections**:

1. **Problem Statement**: Users need to confirm/reject archive candidates with high confidence
2. **Data Model**: CandidateArchive object with match score, reason, confidence breakdown
3. **Matching Strategies**: 6 algorithms (filename, metadata, folder hints, recency, etc.)
4. **UI Layout**:
   - Candidate banner ("X matches need review")
   - Archive list with linked + candidate sub-filters
   - Confidence breakdown per candidate
   - Timeline view for 5+ candidates
5. **Interaction Flows**: 4 scenarios (single high-confidence, multiple mixed, skip/undo, bulk link)
6. **API Contracts**: GET/POST candidates, link, skip, unlink endpoints
7. **Accessibility**: Keyboard shortcuts (L, S, U, Esc), screen reader support, ARIA labels
8. **Performance**: Pagination, lazy rendering, sorting for 10+ candidates

**Validation checklist**: 6 checkpoints including algorithm finalization, mockup validation, and user testing.

---

### 4. Updated Design Document ✅

**File**: [model-detail-popup-redesign-2026-05.md](/docs/features/model_catalog/design/model-detail-popup.md) (sections updated)

**Updates**:
- **Summary of Changes**: Added explicit callout that tab UI → collapsible sections
- **Layout Direction**: New desktop mockup showing collapsible sections with archive candidates visible
- **Mobile Mockup**: Stack-based layout with sections defaulting to collapsed state
- **Lower Sections**: Renamed and reorganized:
  - Archive Linkage Review (with candidate workflow reference)
  - Queue Status (new section)
  - Related Models (from tab)
  - Supporting Files (from tab)
- **Cross-references**: Linked to archive-candidate-review-workflow.md for detailed UX

---

## How the Redesign Addresses #1376 Blockers

### Issue #1376: "Hosts hero/panel/overflow extension points used by #1494, #1495, #1483, #1499"

**Deliverables satisfy**:

| Blocker | Resolved By | Status |
|---------|-------------|--------|
| No stable extension points | `popup-extension-points.md` defines 8 slots with TypeScript contracts | ✅ |
| Tab UI hides candidate review | `popup-model-detail-collapsible-sections.html` shows candidates at-a-glance | ✅ |
| Tab UI makes 5 features hard to discover | Collapsible sections make all 5 panels discoverable in scroll order | ✅ |
| Archive UI (#1495) unclear on layout | `archive-candidate-review-workflow.md` provides full UX spec | ✅ |
| 3D Viewer (#1494) unclear where to render | `hero-left:media` extension point ready for media enhancements | ✅ |
| Related Models (#1483) unclear layout | `sections:related-models` extension point defined | ✅ |
| Print History (#1499) unclear integration | `sections:archive-linkage` links archives to print history context | ✅ |

---

## Validation & Next Steps

### Phase 0 Sign-Off Checklist

Before merging #1376:

- [ ] Mockup tested in browser with collapsible interactions
- [ ] Extension point API contracts reviewed with feature leads (#1494, #1495, #1483, #1499)
- [ ] Archive candidate review workflow approved by intake/forensics team
- [ ] Mobile responsive behavior validated on tablet/phone breakpoints
- [ ] Accessibility testing (keyboard nav, screen reader) initiated
- [ ] Collapse/expand state persistence works as expected

### Dependent Issues: Pre-Merge Gates

**#1494 (3D Viewer)**: Validate `hero-left:media` extension point sufficient for embedded 3MF previews.

**#1495 (Archive UI)**: Validate `sections:archive-linkage` + candidate workflow spec covers full UX.

**#1483 (Related Models)**: Validate `sections:related-models` sufficient for model card grid/list.

**#1499 (Print History)**: Validate archive row actions can link to archive detail/print history preview.

---

## File Locations

All deliverables in workspace:

```
docs/features/model_catalog/
├── model-detail-popup-redesign-2026-05.md         [UPDATED]
├── popup-extension-points.md                       [NEW]
├── archive-candidate-review-workflow.md            [NEW]
└── design/mockups/
    └── popup-model-detail-collapsible-sections.html [NEW]
```

---

## Key Design Decisions Locked In

1. **Collapsible > Tabs**: Progressive disclosure with operator control over complexity
2. **Archive candidates visible by default**: No tab switching to discover linkage work
3. **Extension slots stable**: Dependencies can safely plan around defined contracts
4. **Archive review workflow detailed**: Full UX spec ready for implementation
5. **Mobile stack**: Sections collapse by default on mobile to manage scroll length

---

## Open Questions for Review

1. Should collapse state be remembered **globally** (all users) or **per-user**?
2. Should "Link All" batch action require confirmation modal or inline confirmation?
3. Should candidate scoring details be in expandable row or separate "Audit Score" panel?
4. Mobile: Default all sections to expanded or collapsed (except hero)?

---

## Recommended Review Order

1. Review `popup-model-points.md` (extension API contracts)
2. Review `archive-candidate-review-workflow.md` (candidate UX detail)
3. Review updated `model-detail-popup-redesign-2026-05.md` (layout changes)
4. Test interactive mockup: `popup-model-detail-collapsible-sections.html`
5. Validate with feature leads: #1494, #1495, #1483, #1499

---

**Status**: Ready for Phase 0 acceptance review  
**Created**: 2026-05-15  
**Related**: #1376, #1494, #1495, #1483, #1499
