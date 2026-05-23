# Catalog Redesign 2026-05 · Design Updates & Changes (2026-05-13)

## Summary

This document captures 8 interconnected design enhancements to the Catalog Redesign (2026-05), addressing operator workflows for Frequents curation, Project discovery, Queue organization, and Bambuddy integration.

---

## 1. Frequents Rail Visibility & Manual Control ✅

**Status:** Partially completed (design doc updated; mockups need manual update)

**Changes:**
- Frequents rail is now **toggleable** (hide/show) via control in header
- Visibility persists per-operator preference (stored in sidecar)
- Added **manual Frequent flagging**: every model card and popup get `⚡ Mark as frequent` / `⚡ Unmark as frequent` action
  - Overrides automatic inference (archive link count + recency window)
  - Manually flagged items always stay pinned first in the rail
  - Useful for utility prints with incomplete link history, or excluding outliers

**Design doc updates:**
- Ontology table row "Frequent": Changed from "derived (read-only)" to "boolean per model (derives from archive count + recency, but manually overridable)" with full explanation
- New subsection after US-1: "Frequents rail visibility & manual control"

**Mockup updates still needed:**
- M1 (Default landing): Add toggle/collapse button (−) to Frequents rail header
- M1 (Default landing): Update hint text to mention "manually flagged first"
- M1 (Default landing): Add `⚡ Mark as frequent` action to each freq-card
- M2 (Frequents tuning popover): Add section showing manually flagged items with option to unmark

---

## 2. Manual Frequent Flagging ✅

**Status:** Designed (see #1 above)

**Priority:** High — operators need this for utility prints and threshold exceptions

**Implementation notes:**
- Store as model-level `frequent_override: bool | null` (null = infer from archive count; true/false = manual override)
- Layer 2 projects `frequent` boolean: true if (manual override = true) OR (manual override != false AND archive_count ≥ threshold AND last_printed ≤ window)
- Action appears on: model cards (grid view), Frequents cards, popup hero, Favorites toggle area

---

## 3. Frequents Rail Toggleability ✅

**Status:** Designed (see #1 above)

**Implementation:**
- Header collapse button (−) to hide the rail
- State persists: `operator.catalog_rail_state.frequents_visible: bool`
- Default on first visit: true; then remember operator's choice

---

## 4. Bambuddy Projects vs Catalog Projects ✅

**Status:** Completed (decision documented)

**Decision:**
- **Keep both concepts distinct:**
  - **Bambuddy `print_project`**: execution record (1 per archive). Immutable history of actual prints.
  - **Catalog `Project`**: planning/intent entity (many models). Operator grouping for "what I'm building" with lifecycle (evaluating → planning → active → completed/archived/backlog).

- **Linkage:** Optional and user-initiated.
  - When a print completes (new archive created), optionally suggest linking to an in-flight Catalog Project if confidence threshold is met (filename match, folder hint, etc.)
  - "Link to Project…" action in Project detail when viewing print history
  - Catalog Project optionally exposes "completed prints rolled up from N associated print_projects" as a derived view

- **Archive ingestion:**
  - On archive creation, check for candidate Catalog Project matches
  - Show UI suggestion in relevant Catalog Project context: "New archive 'Shelf Bracket v2.1' matches unprinted model — link to this project?"

**Design doc updates:**
- Expanded the "Decision (Project vs Bambuddy Project)" subsection in §5.1 with full linkage strategy and archive ingestion flow

**Note:** This addresses the question of whether to consolidate or keep both. Keeping both with explicit linkage preserves the operational distinction (execution history vs. intent/planning) while allowing the operator to connect them when useful.

---

## 5. Queue Project Filter & Bulk Add ✅

**Status:** Designed (mockups need updates)

**Changes:**
- **Queue view gains Project filter:** Chip/dropdown that pivots the queue to show entries for a single project in all states (ready, started, done, blocked, backlog)
- **Bulk add action:** Catalog Project header offers "Queue all unprinted models" (existing, per US-3); also add as card action in collections-and-projects-nav.html
- **Pairing:** Clicking a project in Catalog left rail filter → shows models in grid + optional "Queue this project" shortcut CTA

**Design doc updates:**
- Added "Queue Project filter & bulk add" subsection under US-5 enhancements

**Mockup updates still needed:**
- M7 (Queue states) or M8b (NEW): Show queue view with Project filter chip
- collections-and-projects-nav.html: Add "Queue project" button on project cards (action row)

---

## 6. Add-to-Queue Dialog: Plate Picker Enhancement ✅

**Status:** Designed (mockup needs update)

**Current:**
- Dropdown: "single plate" or "ALL plates" only

**New:**
- Multi-select UI with:
  - Checkbox per plate in the model
  - [Select All] / [Deselect All] shortcuts
  - Inline metadata per plate (time estimate, color swatches, plate notes, etc.)
  - Clear confirmation before queuing

**Rationale:** Operators often want to queue specific subset of plates (e.g., all but the experimental variant; only colored plates, etc.)

**Design doc updates:**
- Added "Queue plate picker enhancement" subsection under US-5

**Mockup updates still needed:**
- M8 (Add-to-Queue dialog): Replace plate dropdown/picker with richer multi-select component

---

## 7. Backlog Model File Download (Future) ✅

**Status:** Designed (lower priority; defer to post-v1)

**Feature:**
- When a model sourced from an online service (makerworld, printables, thingiverse) is added to Queue `backlog` state, optionally download the actual 3MF/step files to protect against the model becoming unlisted later
- UX: post-add prompt "Download files for archival?" with one-click yes, or quiet background download if auto-download enabled

**Design doc updates:**
- Added "Backlog model file download (future)" subsection under US-5

**Implementation notes:**
- Store model source (`publication.source = makerworld | printables | thingiverse | original | other`)
- On backlog add, if source is external: invoke download endpoint (out of scope here; managed by intake/sidecar)
- Flag this for future phase planning (not blocking v1)

---

## 8. Drag & Drop for Organization ⚠️

**Status:** Design pattern identified (implementation complexity flagged)

**Scope:**
- **Potential use cases:**
  - Drag model card into project/collection from grid
  - Drag model between projects/collections
  - Re-rank within project evaluation board (3-column Kanban)

**Design decision:** Include as a feasible UX pattern in mockups, but **flag implementation complexity** for technical review. May require:
- Custom drag-drop event handlers vs. native browser API
- Conflict resolution for multi-membership (model in 2 collections, drag behavior TBD)
- Accessibility considerations (keyboard equivalents required)

**Mockup approach:**
- Show drag affordance (cursor: grab on hover, visual feedback on drag start)
- Document in legend/notes that implementation requires evaluation

---

## 9. Browser Extension & Stream Deck Import ⚠️

**Status:** Designed (future phase; requires coordination)

**New actions:**
- Add to project (opens project picker)
- Add to queue (direct, or opens Plan dialog)
- Add to collection (opens collection picker)
- Mark as favorite
- Mark as frequent (NEW)

**Scope:** Requires integration with intake/import surfaces and external handler coordination. **Defer to post-v1 phase.**

**Design doc note:** Record under US-11+ as part of broader external-source intake UX

---

## Implementation Checklist

### Design Documentation ✅
- [x] Catalog redesign 2026-05.md ontology updates
- [x] Bambuddy Project linkage decision
- [x] Frequents rail visibility & manual control section
- [x] Queue enhancements (plate picker, project filter, backlog DL)
- [ ] Drag & drop notes (design pattern identified; implementation flagged)
- [ ] Browser extension/Stream Deck import (note as future phase)

### Mockup Updates ⏳
- [ ] M1: Frequents rail toggle, manual flag action, updated hint
- [ ] M2: Manual Frequents flags display in tuning popover
- [ ] M8: Enhanced plate picker (multi-select)
- [ ] M7/M8b: Queue Project filter and view
- [ ] collections-and-projects-nav.html: "Queue project" action on cards
- [ ] (Optional) Drag affordance visualization in relevant mockups

---

## Notes for Next Phase

1. **Frequents manual flagging** is high-impact for utility prints; prioritize for v1.
2. **Bambuddy linkage** is optional but valuable; archive ingestion suggestion UI is the key UX piece.
3. **Queue project filter** pairs naturally with the new Projects grid view (collections-and-projects-nav.html); consider bundling.
4. **Plate picker** enhancement is straightforward UI improvement; can be done early.
5. **Backlog file download** is a safety feature; defer unless strong operator demand.
6. **Drag & drop** and **Browser Extension** are nice-to-have; defer and re-evaluate based on feedback.

---

**Document created:** 2026-05-13  
**Companion:** [catalog-redesign-2026-05.md](catalog-redesign-2026-05.md)  
**Mockups:** [design/mockups/catalog-redesign-mockups.html](design/mockups/catalog-redesign-mockups.html), [design/mockups/collections-and-projects-nav.html](design/mockups/collections-and-projects-nav.html)
