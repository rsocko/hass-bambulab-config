# Model Detail Popup Redesign (Phase 0) — Complete Deliverables Index

**Date**: 2026-05-15  
**Issue**: #1376  
**Scope**: Stable popup UI with extension points for #1494, #1495, #1483, #1499

---

## 📋 Documents (Read in This Order)

### 1. **Summary & Status** (START HERE)
   - [PHASE-0-POPUP-REDESIGN-SUMMARY.md](./PHASE-0-POPUP-REDESIGN-SUMMARY.md)
   - 5-min executive overview, validation checklist, next steps

### 2. **Extension Points API** (For Feature Leads)
   - [popup-extension-points.md](./popup-extension-points.md)
   - 8 extension slots, TypeScript contracts, dependency resolution
   - **Review**: Feature teams #1494, #1495, #1483, #1499

### 3. **Archive Candidate Review Workflow** (For Archive UI)
   - [archive-candidate-review-workflow.md](./archive-candidate-review-workflow.md)
   - Candidate scoring, confidence breakdown, keyboard shortcuts, accessibility
   - **Review**: #1495 (Archive UI), intake/forensics team

### 4. **Updated Design Document** (For Context)
   - [model-detail-popup-redesign-2026-05.md](./model-detail-popup-redesign-2026-05.md) (Sections 1–2 updated)
   - New collapsible layout mockups (desktop + mobile)
   - Section organization & edit pattern

---

## 🎨 Interactive Mockup

- **[popup-model-detail-collapsible-sections.html](./design/mockups/popup-model-detail-collapsible-sections.html)**
  - Open in browser to test
  - Collapsible sections, archive candidate rows, media carousel
  - Tunable width, padding, accent color
  - Mobile toggle

---

## ✅ What Changed From Tab UI

| Aspect | Old (Tabs) | New (Collapsible) | Benefit |
|--------|-----------|------|---------|
| **Navigation** | Click tabs to switch panels | All sections visible, scroll to discover | No friction; candidates visible immediately |
| **Archive Candidates** | Hidden in "Related Archives" tab | Visible in dedicated section with UX | Operators don't miss linkage work |
| **Queue Status** | Separate "Queue/Prints" tab | Collapsible Queue Status section | Always findable; can collapse if not needed |
| **Collapse/Expand** | N/A (tab-based) | Per-section [−/+] buttons | Operator controls complexity |
| **Mobile UX** | Tab UI stacks poorly | Sections stack naturally; collapse on mobile | Better mobile experience |

---

## 🔌 Extension Points at a Glance

| Extension Point | Purpose | Used By |
|-----------------|---------|---------|
| `hero-left:media` | Media carousel enhancements | #1494 (3D Viewer) |
| `hero-right:summary` | Summary card additions | Core |
| `sections:archive-linkage` | Archive review UI | #1495 (Archive UI) |
| `sections:queue-status` | Queue status display | Core |
| `sections:related-models` | Related model cards | #1483 (Related Models) |
| `sections:supporting-files` | Documentation/BOM | Core |
| `actions:top-bar` | Top bar buttons | Any feature |
| `actions:per-archive` | Archive row actions | Archive UI |

See **popup-extension-points.md** for full TypeScript contracts & data models.

---

## 🎯 Key Decisions Locked

1. **Collapsible sections** (not tabs) for progressive disclosure
2. **Archive candidates visible by default** (no tab switching)
3. **Queue status as own section** (not buried in archive list)
4. **4 lower sections** (Archive Linkage, Queue Status, Related Models, Supporting Files)
5. **Extension slots stable** for dependent issues to plan around

---

## ⚠️ Open Questions for Review

1. Collapse state: global or per-user?
2. Batch "Link All" action: modal confirm or inline?
3. Candidate scoring audit: expandable row or separate panel?
4. Mobile: sections expanded by default or collapsed (except hero)?

---

## 📅 Validation Checklist (Before Merge)

- [ ] Mockup tested with collapsible interactions
- [ ] Extension points reviewed by #1494, #1495, #1483, #1499
- [ ] Archive candidate workflow approved by intake team
- [ ] Mobile responsive (tablet, phone breakpoints)
- [ ] Accessibility (keyboard nav, screen reader)
- [ ] Collapse/expand state persistence verified

---

## 🚀 For Dependent Issues

Each of these can proceed with confidence that:
- Extension points are stable and documented
- Data models are defined (TypeScript contracts)
- Archive candidate review UX is fully specified
- Mobile/accessibility requirements are captured

**Start**: Review popup-extension-points.md for your slot.

---

**Created**: 2026-05-15 | **Status**: Phase 0 Complete | **Ready for**: Feature team review
