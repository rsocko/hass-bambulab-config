# Phase 0 Popup Redesign — Quick Reference Card

**Issue**: #1376  
**Status**: ✅ Phase 0 Complete  
**Date**: 2026-05-15

---

## 🎯 Problem Solved

**Old UI**: Tab-based interface; users had to click tabs to see archive candidates, queue status, related models, supporting files. Archive linkage review was buried and easy to miss.

**New UI**: Collapsible sections; all content visible on scroll, archive candidates discoverable at a glance, operators can collapse sections they don't need.

---

## 📚 Four Deliverables

| # | File | Purpose | For Whom |
|---|------|---------|----------|
| 1 | `popup-model-detail-phase0-extension-host.html` | **Interactive mockup** — test the Phase 0 merged host layout | Designers, UX testers |
| 2 | `popup-extension-points.md` | **API contracts** — 8 extension slots for dependent features | Feature leads #1494, #1495, #1483, #1499 |
| 3 | `archive-candidate-review-workflow.md` | **Full UX spec** — candidate review, scoring, keyboard nav, accessibility | Archive UI team (#1495) |
| 4 | `model-detail-popup-redesign-2026-05.md` (updated) | **Design doc** — collapsible layout, new mockups | All stakeholders |

---

## 🔌 Extension Points (8 slots)

```
HERO (Always visible)
├── hero-left:media        → Media carousel + filters (#1494)
└── hero-right:summary     → Summary block + file inspector (core)

LOWER SECTIONS (Collapsible)
├── sections:archive-linkage    → Archive review + candidates (#1495)
├── sections:queue-status       → Queue items & draft intents (core)
├── sections:related-models     → Related model cards (#1483)
└── sections:supporting-files   → Documentation, BOM, etc. (core)

ACTIONS
├── actions:top-bar        → CTA buttons (any feature)
└── actions:per-archive    → Per-row archive actions (#1495)
```

---

## ✨ Key Improvements

| Feature | Tab UI | Collapsible | Win |
|---------|--------|-------------|-----|
| Candidate discovery | Hidden | Visible | No missed work |
| Navigation friction | 5 tabs | None | Better UX |
| Mobile UX | Awkward | Natural stack | Mobile-friendly |
| Extensibility | Hard-coded | 8 extension points | Feature-unblocked |

---

## 📋 Reading Guide

**5-minute overview**:
→ PHASE-0-POPUP-REDESIGN-SUMMARY.md

**Feature implementation**:
→ popup-extension-points.md (your extension point)

**Archive candidate review**:
→ archive-candidate-review-workflow.md

**Visual walkthrough**:
→ popup-model-detail-phase0-extension-host.html (open in browser)

---

## ⚠️ Open for Feedback

- Collapse state: save globally or per-user?
- Batch actions: confirm modal or inline?
- Scoring details: expandable row or audit panel?
- Mobile defaults: expand sections or keep collapsed?

---

## ✅ Ready for

- [x] Feature team review (#1494, #1495, #1483, #1499)
- [x] Design/UX sign-off
- [x] Dependent issue planning
- [ ] Phase 0 acceptance (7-item checklist)
- [ ] Implementation

---

**Files**: `docs/features/model_catalog/`  
**Mockup**: `design/mockups/popup-model-detail-phase0-extension-host.html`  
**Status**: Ready for review
