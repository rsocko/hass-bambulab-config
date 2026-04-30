# Phase 5 Wave 4: HA UI Design For Intake, Working Groups, And Curation Actions

> **Status**: Implementation-facing UI design
> **Created**: 2026-04-30
> **Scope**: Phase 5 Wave 4 operator surfaces for issues #1077, #1082, and #1145
> **Authority**: [PHASE-5-EXECUTION-SEQUENCE](PHASE-5-EXECUTION-SEQUENCE.md), [phase-delivery-and-validation](phase-delivery-and-validation.md), [workflow-and-ingestion-guide](workflow-and-ingestion-guide.md)

---

## Purpose

Define the Home Assistant operator surfaces for the first complete Phase 5 working workflow:

- intake submission from browser upload or server-browse sources
- inbox and queue review before grouping
- working-group browsing and detail inspection
- curated-link management from working groups
- batch curation actions with clear result feedback

This document is intentionally implementation-facing. It covers the immediate Wave 4 UI slice and names the reusable components, surface contracts, and state patterns needed to build it.

Future-facing publish, lineage, preview-promotion, and library-import surfaces are documented separately in [phase-5-end-state-ui-and-handoff-design.md](phase-5-end-state-ui-and-handoff-design.md).

---

## Design Goals

1. Reuse the proven interaction language from Print History wherever the operator mental model overlaps.
2. Keep intake, Working, and curated concerns visibly separate even when they appear in one operator flow.
3. Show state, verification, and cleanup outcomes explicitly so batch and queue actions feel auditable.
4. Design for growth into publish and lineage flows without forcing those later decisions into the Wave 4 implementation.

---

## Design Inputs

### Immediate Wave 4 Drivers

- **#1077**: browse working groups, inspect files, manage curated-model links
- **#1082**: batch selection and curation workflow actions with feedback and progress
- **#1145**: source mode, queue visibility, folder-selection controls, cleanup policy, result summaries

### Near-Term End-State Drivers

- **#1132 / #1133**: project-aware Working groups, publish workflow, revision lineage
- **#1163 / #1137**: publish-time preview promotion and supporting-asset selection
- **#1146**: cleanup auditability and retry semantics
- **#1149**: deployment/runtime visibility for queue volume and remote-client flows
- **#213**: local-library/OneDrive intake path as a variant of the same intake UX

### Reused UI Contracts

- Print History three-layer split: lean backend projection, HA integration shaping, frontend formatting
- Print History toolbar and multi-select semantics
- Print History popup composition for detail surfaces
- Filament Catalog grouping and scale patterns for larger browser surfaces
- Existing Model Catalog detail-popup conventions for metadata density and linked-entity drill-in

---

## Scope Boundaries

### In Scope For This Doc

- Intake Home surface
- Intake Submission popup
- Server Browse picker popup
- Inbox and Queue review surface
- Working Board
- Working Group Detail popup
- Link Management popup
- Batch Action mode and result-summary affordances
- Cleanup-policy configuration and outcome visibility

### Explicitly Out Of Scope For Wave 4 Implementation

- full publish execution UI
- revision-lineage editors
- extracted-preview promotion workflow
- supporting-asset import picker
- OneDrive-specific authentication or remote-browser flow

Those later surfaces still influence layout and component decisions here, but they are not required to ship the first Wave 4 slice.

---

## Information Architecture

The operator should experience Phase 5 Wave 4 as one coherent Working workflow with separate surface entry points:

```text
Model Catalog Home
├─ Intake Home
│  ├─ Submit Intake
│  │  ├─ Browser Upload Mode
│  │  └─ Server Browse Mode
│  ├─ Inbox / Queue Review
│  └─ Result Summary / Audit Snapshot
├─ Working Board
│  ├─ Stage View
│  ├─ Recent Activity View
│  └─ Project View (future-ready, optional in Wave 4)
└─ Working Group Detail
   ├─ Files
   ├─ Metadata
   ├─ Curated Links
   └─ Batch / Intake Actions
```

---

## Reusable Component System

The Wave 4 UI should be broken into reusable elements rather than large one-off cards.

| Component | Purpose | Reuse Target |
|---|---|---|
| `mc-surface-header` | Title, subtitle, counts, primary actions | Intake Home, Working Board |
| `mc-source-mode-toggle` | Browser upload vs server browse segmented control | Intake popup, future remote-import surfaces |
| `mc-queue-status-chip` | Visual queue/upload/verify/cleanup state | Inbox rows, group detail, result summaries |
| `mc-validation-banner` | Duplicate, warning, unsupported, missing-source summary | Inbox detail, group detail, batch result modal |
| `mc-selection-toolbar` | Multi-select mode, counts, bulk actions | Working Board, Inbox review |
| `mc-working-group-card` | Group summary card with stage, files, link status | Board grid and list variants |
| `mc-file-member-table` | Primary file, supporting files, attach/detach actions | Group detail, future publish review |
| `mc-curated-link-row` | Curated link summary with status and actions | Group detail, link popup |
| `mc-result-summary-panel` | Success/fail/partial counts and per-item outcomes | Intake completion, batch actions |
| `mc-confirm-action-modal` | Explicit destructive confirmation and guardrails | Cleanup retry, unlink, reject, detach |

### Shared State Contract

Follow the Print History split:

- **HA helpers** hold mode-level state such as source mode, cleanup policy, and whether bulk mode is active.
- **Card-local state** holds selected working-group IDs, selected inbox item IDs, open row expansion, and active tabs.
- **Service responses** provide authoritative progress and outcome payloads; the UI should not invent long-lived optimistic states.

---

## Surface 1: Intake Home

### Purpose

Provide the top-level landing surface for new submissions, current queue visibility, and quick access into inbox review.

### Required Content

- source mode summary
- cleanup policy summary
- queue counts by state
- inbox counts by validation state
- primary actions: submit intake, review inbox, review recent results

### Mid-Fidelity Mockup

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Model Catalog Intake                                                        │
├──────────────────────────────────────────────────────────────────────────────┤
│ New submissions, validation, queue, and Working-group handoff               │
│                                                                              │
│ [Submit Intake] [Review Inbox] [Recent Results]                             │
│                                                                              │
│ Source Mode        Cleanup Policy        Queue Health                        │
│ ┌───────────────┐  ┌──────────────────┐  ┌────────────────────────────────┐ │
│ │ Server Browse │  │ keep             │  │ queued 12  verify 2  failed 1 │ │
│ │ Root: Working │  │ allowlisted only │  │ cleanup pending 3              │ │
│ │ recurse: on   │  │ verified required│  │ last batch: partial            │ │
│ └───────────────┘  └──────────────────┘  └────────────────────────────────┘ │
│                                                                              │
│ Inbox Snapshot                                                               │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ ready 8   duplicate candidates 3   unsupported 1   deferred 4           │ │
│ │ Most recent: Gridfinity Holder remix batch from /OneDrive/Working        │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Recent Activity                                                              │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ 10:42  Imported 6 items → 4 new groups, 1 attached, 1 duplicate skipped │ │
│ │ 10:18  Cleanup retry succeeded for Hose Adapter batch                    │ │
│ │ 09:57  Validation flagged 2 missing sources in server browse batch       │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Interaction Notes

- This is a dashboard summary surface, not the place for detailed row editing.
- Queue health should use the same compact status-summary semantics as Print History counters.
- On mobile, the three summary panels stack vertically before the activity block.

---

## Surface 2: Intake Submission Popup

### Purpose

Collect submission inputs for both source modes without splitting the UX into two unrelated tools.

### Key Decisions

- Source mode is a top-of-popup segmented control.
- Browser upload and server browse share the same footer controls and cleanup-policy summary.
- Folder recursion options appear only when folder selection exists.

### Mid-Fidelity Mockup

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Submit Intake                                                  [Close]      │
├──────────────────────────────────────────────────────────────────────────────┤
│ [ Browser Upload ] [ Server Browse ]                                        │
│                                                                              │
│ Batch Label: [ April Wave 4 samples_______________________________ ]         │
│ Notes:       [ remix candidates + local revisions________________ ]         │
│                                                                              │
│ Source Selection                                                             │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ Browser mode                                                            │ │
│ │ [Drop files here]  or  [Choose Files] [Choose Folder]                  │ │
│ │ Selected: 7 files, 1 folder                                             │ │
│ │ Folder options: recurse [x]   max depth [ 2 ]                           │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Cleanup Policy                                                               │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ (•) keep    ( ) delete_on_verified    ( ) replace_with_stub             │ │
│ │ Destructive policies apply only to allowlisted server-side roots.       │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Expected Outcome                                                             │
│ queue items will be created, validated, and held for review before grouping  │
│                                                                              │
│ [Submit To Inbox] [Cancel]                                                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Server Browse Variant

- Replace the browser file-drop area with a summary of current root, selected paths, and a button to open the browse picker.
- Preserve the same cleanup and footer sections.

---

## Surface 3: Server Browse Picker

### Purpose

Give operators a controlled, allowlisted filesystem picker that feels like part of the same intake flow.

### Mid-Fidelity Mockup

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Server Browse: Working Root                                     [Close]     │
├──────────────────────────────────────────────────────────────────────────────┤
│ Roots: [ Working ▼ ]  Current Path: /remixes/gridfinity                      │
│                                                                              │
│ [..]  [Search current folder__________________]                              │
│                                                                              │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ ☑ folder  bit-holder-v3/      12 files     modified 2026-04-28          │ │
│ │ ☐ file    holder_v3.3mf       18 MB        2026-04-28                    │ │
│ │ ☑ file    label.svg           44 KB        2026-04-27                    │ │
│ │ ☐ folder  refs/               6 files      2026-04-20                    │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Selection Options                                                            │
│ recurse folders [x]   max depth [ 2 ]   include mixed file+folder batch [x] │
│                                                                              │
│ [Add Selection To Intake] [Cancel]                                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Interaction Notes

- The picker must make allowlisted-root boundaries obvious.
- If a path is unavailable or stale, show an inline validation banner rather than a generic toast.
- Search is folder-local only in Wave 4. Full indexed search belongs later.

---

## Surface 4: Inbox And Queue Review

### Purpose

Review submitted items before creating or attaching Working groups.

### Layout Strategy

- Desktop uses a two-pane layout: filterable list on the left, detail on the right.
- Mobile collapses to a stacked list with expandable row detail.
- Queue-state and validation-state chips must stay visible in the row summary.

### Mid-Fidelity Mockup

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Inbox Review                                                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│ Search [ gridfinity __________________ ]  Filters [State ▼] [Source ▼]      │
│ [Select Items]  16 items                                                     │
│                                                                              │
│ ┌──────────────────────────────┬───────────────────────────────────────────┐ │
│ │ READY                        │ Gridfinity Holder v3                      │ │
│ │ queued → verified            │ source: server browse /Working/remixes    │ │
│ │ 18 MB  3MF                   │ hash matched no duplicates                │ │
│ │ [Create Group] [Attach]      │                                           │ │
│ ├──────────────────────────────┼───────────────────────────────────────────┤ │
│ │ DUPLICATE CANDIDATE          │ Validation Summary                        │ │
│ │ queued → verified            │ likely match: Bit Holder v2 Working group │ │
│ │ [Review]                     │ basis: filename + hash + folder hint      │ │
│ ├──────────────────────────────┼───────────────────────────────────────────┤ │
│ │ UNSUPPORTED                  │ Proposed Actions                          │ │
│ │ failed validation            │ [Create New Group] [Attach Existing]      │ │
│ │ [Dismiss]                    │ [Defer] [Reject]                          │ │
│ └──────────────────────────────┴───────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Required States

- `ready`
- `duplicate_candidate`
- `unsupported_type`
- `missing_source`
- `validated_with_warnings`
- `cleanup_pending`
- `cleanup_failed`

### Interaction Notes

- Create and attach actions should be row-local for single-item work.
- Bulk mode swaps these row actions for checkbox selection and the shared selection toolbar.
- Result summaries should open inline after actions instead of relying only on transient notifications.

---

## Surface 5: Working Board

### Purpose

Provide the first durable operator surface for sidecar-owned Working groups.

### Default Views

- Stage view: `draft`, `in_progress`, `needs_revision`, `ready_to_publish`, `archived`
- Recent activity view
- Optional project grouping hook kept dormant unless project metadata exists

### Mid-Fidelity Mockup

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Working Board                                                                │
├──────────────────────────────────────────────────────────────────────────────┤
│ Search [ holder _____________________ ] View [ By Stage ▼ ] Sort [Recent ▼] │
│ Filters [Project ▼] [Link Status ▼] [Stage ▼]                [Select Groups] │
│                                                                              │
│ Draft (2)                                                                    │
│ ┌────────────────────┐ ┌────────────────────┐                                │
│ │ Bit Holder Remix   │ │ Hose Adapter Test  │                                │
│ │ files: 6           │ │ files: 3           │                                │
│ │ primary: v3.3mf    │ │ primary: rev-b.step│                                │
│ │ curated links: 1   │ │ curated links: none│                                │
│ │ last action: today │ │ duplicate warning  │                                │
│ │ [Open] [Link]      │ │ [Open] [Review]    │                                │
│ └────────────────────┘ └────────────────────┘                                │
│                                                                              │
│ Ready To Publish (1)                                                         │
│ ┌────────────────────┐                                                       │
│ │ Desk Tray Final    │                                                       │
│ │ files: 7           │                                                       │
│ │ project: Desk Set  │                                                       │
│ │ curated links: 2   │                                                       │
│ │ [Open] [Batch]     │                                                       │
│ └────────────────────┘                                                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Interaction Notes

- Visual style should follow Print History browser-card density rather than a kanban-heavy aesthetic.
- Card footer actions stay terse: `Open`, `Link`, `Review`, `Batch`.
- The board must support list-density fallback for larger datasets.

---

## Surface 6: Working Group Detail Popup

### Purpose

Show group metadata, attached files, validation context, and curated links in one popup.

### Tab Model

- `Summary`
- `Files`
- `Curated Links`
- `Intake History`

This mirrors the successful print-history popup pattern while adapting content for Working data.

### Mid-Fidelity Mockup

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Working Group: Bit Holder Remix                                   [Close]   │
├──────────────────────────────────────────────────────────────────────────────┤
│ [preview]  Stage: draft      Files: 6      Curated links: 1                 │
│ project: Gridfinity family   source hints: makerworld remix + local edits   │
│ [Edit Metadata] [Attach File] [Open Folder] [Open Primary]                  │
│                                                                              │
│ [ Summary ] [ Files ] [ Curated Links ] [ Intake History ]                  │
│                                                                              │
│ Summary                                                                      │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ notes: widened socket clearance, label plate added                      │ │
│ │ duplicate signals: older v2 group matched by source URL + filename      │ │
│ │ last intake batch: April Wave 4 samples                                 │ │
│ │ cleanup policy used: keep                                                │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Files                                                                        │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ primary  holder_v3.3mf          18 MB   [Make Primary] [Detach]         │ │
│ │ asset    label.svg              44 KB   [Detach]                         │ │
│ │ asset    print-notes.md          3 KB   [Detach]                         │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Required Actions

- edit metadata
- attach or detach file
- mark primary file
- add or remove curated link
- jump to relevant intake result when the item originated from inbox

---

## Surface 7: Link Management Popup

### Purpose

Manage the veneer relationship between a Working group and curated catalog records.

### Mid-Fidelity Mockup

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Curated Links For Bit Holder Remix                               [Close]    │
├──────────────────────────────────────────────────────────────────────────────┤
│ Search curated catalog [ bit holder ____________________________ ]           │
│                                                                              │
│ Existing Links                                                               │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ Gridfinity Bit Holder v2   canonical prior revision   [Open] [Unlink]   │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Search Results                                                               │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ [preview] Gridfinity Bit Holder v3 draft candidate                      │ │
│ │ collection: Shop / Gridfinity   last archive: 4d ago                    │ │
│ │ [Link As Related] [Link As Likely Revision]                             │ │
│ ├──────────────────────────────────────────────────────────────────────────┤ │
│ │ [preview] Desk Bit Holder Insert                                         │ │
│ │ [Link As Separate Variant]                                               │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Interaction Notes

- The link type vocabulary should remain intentionally light in Wave 4.
- Future lineage types can extend this popup, but current language should center on visibility and operator review instead of irreversible publish semantics.

---

## Surface 8: Batch Selection And Result Feedback

### Purpose

Support issue #1082 with consistent multi-select mode and auditable outcomes.

### Toolbar Pattern

Reuse the Print History rule:

- one explicit `Select` mode toggle
- shared helper for whether bulk mode is active
- selected IDs remain local to the card
- action toolbar replaces normal controls while in multi-select mode

### Mid-Fidelity Mockup

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ 4 groups selected                                                           │
│ [Mark Ready] [Assign Project] [Open Intake Action] [Link Review] [Cancel]   │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ Batch Result Summary                                                        │
├──────────────────────────────────────────────────────────────────────────────┤
│ succeeded: 2   partial: 1   failed: 1                                       │
│                                                                              │
│ ✓ Desk Tray Final        marked ready_to_publish                            │
│ ✓ Hose Adapter v4        attached to project Desk Set                       │
│ ! Bit Holder Remix       skipped: duplicate link conflict                   │
│ ✕ Old Import Recovery    failed: missing source path                        │
│                                                                              │
│ [Review Failures] [Close]                                                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Feedback Rules

- Never reduce a mixed-result batch to a single green success toast.
- Surface per-item outcomes and keep failures reviewable.
- For long-running actions, show progress text and step names rather than only an indeterminate spinner.

---

## Visual Semantics

### Relationship To Print History

- Use the same top-control density and mobile compression philosophy.
- Use the same popup framing and action placement.
- Use similar state-chip semantics for duplicate, warning, and processed states.
- Prefer row and card layouts that emphasize preview plus metadata summary, not form-heavy admin panels.

### Relationship To Filament Catalog

- Reuse filter grouping concepts when the Working dataset grows.
- Use compact/list density switching for larger inventories.
- Keep grouped sections readable without turning the board into a full kanban board.

---

## Responsive Behavior

### Desktop

- Two-pane review layouts are allowed.
- Popups may use `wide` sizing when detail density requires it.

### Mobile

- Top controls must degrade to horizontally scrollable compact controls.
- Batch toolbar actions collapse to icon-plus-short-label buttons.
- Review rows stack summary above action strip.
- File tables in group detail become card rows instead of dense grids.

---

## State And Error Design

Each primary surface must support the following states explicitly:

| State | Where It Appears | Required Treatment |
|---|---|---|
| Empty | Intake Home, Working Board, Inbox | Clear primary next action |
| Loading | All list/detail surfaces | Skeletons matching final layout |
| Duplicate warning | Inbox, Group Detail | Inline banner plus review path |
| Partial success | Batch result, intake completion | Per-item breakdown |
| Cleanup failed | Inbox, result summary | Retry affordance and audit wording |
| Missing source | Inbox, browse picker | Explicit path context |
| Unverified upload | Queue summary, detail | Status chip and no destructive cleanup action |

---

## Service And Helper Mapping

Wave 4 UI should expect the following HA-facing wiring without embedding business logic in cards:

- `model_catalog.create_working_group`
- `model_catalog.update_working_group`
- `model_catalog.attach_file_to_group`
- `model_catalog.set_upload_source`
- `model_catalog.set_cleanup_policy`
- batch workflow actions exposed through dedicated services rather than card-local mutation

Suggested helpers:

- `input_select.model_catalog_upload_source_mode`
- `input_select.model_catalog_cleanup_policy`
- `input_boolean.model_catalog_working_bulk_mode`
- `input_text.model_catalog_bulk_action_request`

---

## Acceptance Criteria Coverage

### #1077

- working groups are visible on the Working Board
- each group opens a detail popup with files, metadata, and curated links
- link management has a dedicated popup instead of overloading the board row

### #1082

- select mode, multi-select state, and batch toolbar are defined
- result-summary patterns explicitly cover success, failure, and partial success
- intake actions remain reachable from Working surfaces

### #1145

- source-mode toggle is a first-class control
- server browse supports file, folder, and mixed selection
- recursion and max-depth controls are explicit
- cleanup policy and queue/result visibility are designed into the primary intake flow

---

## Implementation Notes

1. Build the reusable components first, then assemble the surfaces.
2. Keep wording neutral and operational; avoid publish-specific language in Wave 4 controls.
3. Preserve Layer 1 lean-data discipline by deriving presentation labels in HA/frontend layers.
4. Treat the Working Board as the Wave 4 anchor surface and Intake Home as the new operator entry surface.

---

## Related Docs

- [intake-inbox-design.md](intake-inbox-design.md)
- [working-groups-and-veneer.md](working-groups-and-veneer.md)
- [workflow-and-ingestion-guide.md](workflow-and-ingestion-guide.md)
- [projects-design.md](projects-design.md)
- [phase-5-end-state-ui-and-handoff-design.md](phase-5-end-state-ui-and-handoff-design.md)
