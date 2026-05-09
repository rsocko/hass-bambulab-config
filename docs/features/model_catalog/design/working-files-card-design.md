# Working Files — Card Design (Groups / Files / Toolbar)

> **Status:** Hi-fidelity design proposal.
> **Scope:** Working Files explorer surface rendered today by [model-catalog-working-files-explorer-card.js](../../../../homeassistant/www/3d_printing/model_catalog/model-catalog-working-files-explorer-card.js). This document defines the redesigned UI; it complements (does not replace) the workflow contract in [working-files-workflow-redesign-issue-1169.md](../working-files-workflow-redesign-issue-1169.md) and reuses the visual grammar already established in [catalog-card-design.md](catalog-card-design.md).
> **Related issues:** #1215 (catalog list-view density / decisions), #1216 (catalog toolbar redesign). Working Files inherits both patterns where they apply, but **diverges in workflow** because the Working Files user is *organising and acting on files*, not browsing a curated index.
> **Companion HTML mockups (browser-viewable, fully self-contained):**
> - [mockups/working-files-groups.html](mockups/working-files-groups.html) — primary focus
> - [mockups/working-files-files.html](mockups/working-files-files.html) — All Files / Ungrouped
> - [mockups/working-files-toolbar.html](mockups/working-files-toolbar.html) — header / view tabs / filter bar
> - [mockups/working-files-group-popup.html](mockups/working-files-group-popup.html) — group details / edit popup
> - [mockups/index.html](mockups/index.html) — landing page

---

## 1. Why Working Files needs its own redesign

The Catalog Browser is a **discovery surface** — find a model, decide whether to print it, then leave. The cards in [catalog-card-design.md](catalog-card-design.md) optimise for that loop.

Working Files is an **organisation surface** — the operator already knows the files exist; they need to:

1. **See what's inside a group at a glance** — which `.3mf` files belong to "Gridfinity Holders v3"? When were they last modified? Which one is the current candidate?
2. **Act on a file without leaving the row** — open in slicer, copy launch path, mark as primary, remove from group.
3. **Reorganise quickly across groups** — pick files from `Ungrouped`, drop them into an existing group, run a reorganize.
4. **Trust freshness** — Working Files mutate constantly (slicer saves, manual renames, OneDrive sync). The UI must surface `mtime` prominently, not bury it in a popup.

The current explorer card is structurally sound (Groups | All Files | Ungrouped tabs, batch select, reindex on load) but visually it underuses the row — a group card shows only `3MF n · Other n · Total n` and forces a click into the right pane to see actual files. The design below restructures the **group row itself** as the primary surface so the operator can answer "what's in here, and what should I do next?" without a second click.

### Direct user input driving this proposal

> "The user will want to be able to see the model files (in particular) and potentially other files for a given working group right from the list view instead of requiring to open the popup. See last modified and other info so they can make quick updates."

That sentence is the design contract for §3 (Group row anatomy) and §4 (Inline file strip).

---

## 2. Schema parity & proposed additions

### 2.1 Fields the explorer endpoint already returns

Endpoint: `GET /api/working-files/explorer` ([sidecars/model_catalog/app/routers/working.py](../../../../sidecars/model_catalog/app/routers/working.py)).

Per **group** (`view=groups`):

- `id`, `slug`, `title`, `stage` (`draft` / `in_progress` / `ready_to_publish`)
- `notes`, `folder_hint`, `primary_file_path`
- `updated_at` (group-level, ISO timestamp)
- `counts.total`, `counts.count_3mf`, `counts.count_other`
- `launch` (mapped host-path context for the group folder)
- `files[]` — sorted with `.3mf` first, then geometry, then other

Per **file** (inside `files[]` and on the `view=all` / `view=ungrouped` payloads):

- `id`, `source_path_raw`, `source_path_canonical`, `source_path_compare_key`
- `file_name_raw`, `file_name_base_hint`, `file_extension`, `file_size_bytes`
- `sha256_hash`
- `source_mtime`, `source_ctime`, `source_birthtime`
- `validation_state`, `warnings[]`
- `detected_at`, `last_seen_at`, `root_path`
- `launch` (mapped host path for the file)
- `group_memberships[]` — list of `{ group_id, group_title, item_role }`

The available `source_mtime` is the field that powers the "Last modified" the user explicitly asked for. It is **already in the payload** — the redesign just promotes it from invisible to first-class.

### 2.2 Proposed additions ⚠️ *requires backend*

| Field | Where it's used | Why | Backend touch |
| --- | --- | --- | --- |
| `files[].is_primary` *(derived)* | Inline file strip "★ Primary" badge in Groups view | Operator needs to know which `.3mf` is the canonical one when a group has multiple variants. Already implied by `group.primary_file_path`; surface as a per-file boolean computed at serialization time. | Compute in `_serialize_working_group` by comparing `item.file_path` to `group.primary_file_path`. |
| `files[].linked_archive_count` *(optional)* | "Used in N prints" sub-label on file row | Lets the operator see if removing/moving a file would orphan archives. | Layer 2 join: count `print_history_archives` rows whose `model_ref` resolves to this file's hash or canonical path. Cache. |
| `group.last_file_mtime` *(derived)* | Group header "Last modified · 2h ago" | `group.updated_at` reflects metadata changes; operators care about *file* changes (slicer save). | `MAX(source_mtime)` across the group's files; compute at serialization. |
| `group.path_footprint` *(derived object)* | Group header "Physical layout" summary and folder chips | Groups are logical overlays; operators still need immediate visibility into the current physical folder spread. | Derive from `files[].source_path_canonical`: total distinct folders, max depth, dominant root segment, top folder segments with counts. |
| `files[].relative_group_path` *(derived)* | Inline file rows and Folders subview | Shows where each file currently lives relative to the group's dominant root without exposing noisy absolute paths. | Compute as relative path from `group.path_footprint.primary_root` (fallback to `dirname(source_path_canonical)`). |
| `group.derived_thumbnail_path` *(optional)* | Group thumbnail in Groups view | Today the explorer card has no group preview; reuse the primary `.3mf`'s plate render or a representative file thumbnail. | Layer 2: pull from existing 3MF metadata extraction; fallback to a placeholder cube SVG when absent. |
| `files[].slicer_kind` (`bambu` / `orca` / `prusa` / `unknown`) ⚠️ best-effort | "Open in" button label / icon hint | The "Open in Slicer" tokenized launch path needs to know which protocol to fire (`bambustudio://` vs `orcaslicer://`). | Detect from `.3mf` metadata or filename heuristics; fallback to user-configured default. |
| `summary.last_indexed_at` | Toolbar "Indexed 2m ago" pill | Operators forget when they last reindexed; surface it. | Already implied by reindex job log; expose in `summary` block. |

### 2.3 Layering guardrail (re-affirmed from repo policy)

Per [.github/copilot-instructions.md](../../../../.github/copilot-instructions.md), Layer 1 (`sensor.print_history_archives`) is off-limits for any of these additions. The Working Files explorer endpoint is a **sidecar projection** — it is the equivalent of a Layer 2 surface for the Working Files domain. All proposed additions live in that projection and in the card (Layer 3) for labels / colour tokens / tooltip wording.

---

## 3. Group row anatomy (the core change)

The Groups view today is a **two-pane split** (groups left, file list right). The redesign collapses that into a single **expandable row** so the file list lives inside the row itself, with the legacy split available as an opt-in "Detail" mode toggle for very large groups.

```
┌─ ha-card row (cursor:pointer on header → toggles expand) ─────────────────────┐
│ [STAGE RIBBON] [GROUP THUMB]  [TITLE · FOLDER HINT]   [STAGE CHIP] [UPDATED] │
│ [PHYSICAL LAYOUT: 27 files · 6 folders · depth 3 · root /Tools/Gridfinity]   │
│ [FOLDER CHIPS: Models (11) · Images (9) · Docs (4) · Exports (3)]             │
│                               [COUNTS: 3 model · 4 other · 1 archive]        │
│ ─────────────────────────────────────────────────────────────────────────────│
│  [FILES] [FOLDERS] (physical)                                                 │
│  MODEL FILES (always visible, .3mf first)                                    │
│   ▸ holder_v3.3mf      Models/Final/holder_v3.3mf   12 MB  2h ago  ★ [⋯]    │
│   ▸ holder_v2.3mf       9 MB   3d ago              [Slicer] [⋯]            │
│   ▸ holder_v1.stl       4 MB   1w ago              [⋯]                      │
│  FOLDERS SUBVIEW (toggle): Models/Final (4) · Images (9) · Docs (4)         │
│  OTHER FILES (collapsed by default if >3 — chevron to expand)               │
│   notes.md · dimensions.svg · render.png · +2 more                          │
│ ─────────────────────────────────────────────────────────────────────────────│
│  [Open Folder] [Reorganize] [Add Files] [Set Primary]    [bulk select ☐]    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Stage ribbon (left edge, 4 px)

Maps the `group.stage` field to a colour band:

- `draft` → slate `#475569`
- `in_progress` → amber `#F59E0B`
- `ready_to_publish` → green `#2E7D32`

Mirrors the queue ribbon from the catalog compact card so users associate "left-edge band = lifecycle state".

### 3.2 Group thumb (64 × 64)

Renders `group.derived_thumbnail_path` (proposed) when available, otherwise a typed placeholder:

- Cube glyph for groups whose primary file is `.3mf`
- Wireframe glyph for `.stl` / `.step` primary
- Generic folder glyph when no file kind dominates

Square (not landscape) because groups are conceptually folders, not photos.

### 3.3 Header line

- **Title** (`group.title`, 15 px / weight 700) — clickable, opens the legacy detail popup as the secondary entry path.
- **Folder hint** (`group.folder_hint`, 12 px secondary) — the relative path the operator sees on disk; truncates with ellipsis.
- **Stage chip** (right-aligned, pill) — `Draft` / `In Progress` / `Ready`.
- **Last modified** (right-aligned, 11 px tabular-nums) — `last_file_mtime` formatted as `2h ago` / `3d ago` / `1w ago`. Tooltip shows absolute timestamp + which file caused the most recent change.

### 3.4 Counts row

Three monospaced cells, no labels (icons only) so they read as a single row:

| Icon | Meaning | Source |
| --- | --- | --- |
| 🧊 | Model files (3MF + STL + STEP) | `counts.count_3mf` + count of geometry in `count_other` |
| 📄 | Other files | remainder of `counts.count_other` |
| 🖨 | Linked archive prints | sum of `files[].linked_archive_count` (proposed) |

### 3.5 Physical-layout summary row (always visible)

Groups are logical overlays, but the operator still needs path truth in the primary row. Add a compact "Physical layout" line under the title block:

- `27 files across 6 folders · deepest level 3 · root /Tools/Gridfinity`
- Source: `group.path_footprint` (proposed)
- Tooltip expands to show top folders and counts

Under that line, render top-folder chips from `group.path_footprint.top_segments`:

- `Models (11)`
- `Images (9)`
- `Docs (4)`
- `Exports (3)`

Clicking a chip filters the visible inline rows to that subtree (purely view-level filtering, no membership mutation).

### 3.6 Files/Folders subview toggle (inside expanded row)

Add a compact segmented toggle directly above the inline strip:

- `Files` (default)
- `Folders (physical)`

Behavior:

- `Files` shows the existing model-first rows plus other-file chips.
- `Folders` shows a lightweight relative tree rooted at `group.path_footprint.primary_root`.
- The toggle is local to each group row; it does not change global view tabs.
- Row-level actions remain identical in both subviews.

### 3.7 Inline file strip — "Model Files" section (always expanded)

The user-facing differentiator. Shows up to **5 model files** by default with a `+N more` expander. Each row is one line:

```
[icon] [filename]            [size]   [mtime]   [primary?]   [actions]
```

- **Icon**: extension glyph (3MF teal, STL blue, STEP purple).
- **Filename**: 13 px, weight 600. Click → opens the file detail popup focused on this file. Hover shows the full canonical path.
- **Relative path**: second line under filename from `files[].relative_group_path` (e.g., `Models/Final/holder_v3.3mf`) so the operator can see physical location without leaving Group view.
- **Size**: tabular-nums, right-aligned in its column.
- **mtime**: relative (`2h ago`); tooltip shows absolute. Cells beyond the visible 5 fold into "+N more" — clicking expands the strip in place (no popup, no navigation).
- **Primary badge**: amber star pill for the file matching `group.primary_file_path`. Click acts as "Set Primary" for any other `.3mf`.
- **Actions** (per row): `Slicer` (primary; visible only for `.3mf`), `⋯` overflow → Copy launch command, Copy explorer command, Remove from group, Open file detail.

Per [working-files-local-launch-and-slicer-integration-design.md](../working-files-local-launch-and-slicer-integration-design.md), the `Slicer` button uses the tokenized download URL approach (Option B); `Copy launch command` is the manual fallback. **No raw `file:///` link is rendered**, consistent with the browser security boundary memo recorded in repo memory.

### 3.8 Folders subview — relative tree (physical)

When `Folders` is active, replace the file-strip body with a compact tree:

- Root label: `group.path_footprint.primary_root`
- Default expansion: 2 levels
- Folder row fields: folder name, file count, latest `mtime`
- File leaf fields: filename, extension, relative path fragment, actions
- Clicking a folder scopes the row to that subtree until "Clear folder filter"

This tree is read-only by default. Membership changes still happen through group actions, and physical moves only happen via explicit `Reorganize`.

### 3.9 Inline file strip — "Other files" section (collapsed when >3)

Below the model-files section. Renders as a chip row (`name.ext` capsules) — each chip is clickable to open the file detail popup. Collapses to "📄 4 supporting files" when >3 to keep the row visually quiet; chevron to expand inline.

### 3.10 Group action row

Bottom of the row, single line:

- `Open Folder` — primary, uses the mapped host path
- `Reorganize` — runs the existing dry-run/confirm/execute flow from the redesign doc
- `Add Files` — opens a file-picker scoped to ungrouped inventory + arbitrary upload (future)
- `Set Primary` — only enabled when a `.3mf` row in the strip is selected
- `bulk select ☐` (right-aligned) — when checked, the row participates in the toolbar bulk-action bar (move-to-group, delete, etc.)

Add one helper line under `Reorganize`: "Materialize logical group into physical folder layout" so virtual-vs-physical behavior is explicit.

### 3.11 Click target precedence

Whole row header is clickable to toggle expansion. Inline action buttons stop propagation (matches the catalog compact-card pattern in §3.8 of [catalog-card-design.md](catalog-card-design.md)). The group title is a separate target — clicking the title (not the header background) opens the legacy detail popup for users who want the deeper tabbed surface. Folder chips and Folders-tree rows are interactive but scoped to filtering and navigation, not mutation.

---

## 4. Files view (All Files / Ungrouped)

This view is for *file-level* triage: find a file by name, see what groups it belongs to, drop it into the right group. The redesign keeps the existing `view=all` and `view=ungrouped` tabs and reformats the file list as a tabular row layout that mirrors the catalog **List view** ([catalog-card-design.md §5](catalog-card-design.md)) for visual consistency.

### 4.1 Columns

| # | Column | Width | Source |
| --- | --- | --- | --- |
| 1 | Bulk-select checkbox | 36 px | local UI state |
| 2 | Type icon | 32 px | `file_extension` |
| 3 | Name + folder | flex | `file_name_raw` + `dirname(source_path_canonical)` (truncates) |
| 4 | Size | 80 px right | `file_size_bytes` |
| 5 | Modified | 100 px right | `source_mtime` (relative; tooltip absolute) |
| 6 | Group memberships | 200 px | `group_memberships[]` — chip per group, click filters Groups view to that group |
| 7 | Validation | 80 px | `validation_state` + `warnings[]` (icon-only when clean; warning chip when not) |
| 8 | Actions | 180 px right | `Slicer` (3MF only), `⋯` (Copy cmd · Copy folder · Remove from all groups · File detail) |

### 4.2 Bulk-action bar (sticky)

Identical pattern to catalog list view: when ≥1 row is selected, a sticky bar slides in above the table:

- `+ Create group from selection`
- `+ Add to existing group…` (opens a small group-picker popover instead of `window.prompt`, which is the current implementation — see [model-catalog-working-files-explorer-card.js](../../../../homeassistant/www/3d_printing/model_catalog/model-catalog-working-files-explorer-card.js) `_addSelectionToExistingGroup`)
- `Move to group…` (single-target convenience for re-assignment)
- `Reorganize selected files…` (dry-run + execute against the destination group's folder)
- `Clear` (deselect all)

### 4.3 Empty / loading / error states

Reuse the dashed `state-row` from the existing card (visually consistent); add a "Run reindex" button to the empty state so the operator has a one-click recovery if the inventory is stale.

### 4.4 Popups & 3D viewer integration

The inline file strip + Files-view table cover the *read-and-act* loop without a popup. Two scenarios still need a modal surface, and one of them already has fully working infrastructure to reuse.

#### 4.4.1 Per-file 3D viewer — *reuse existing catalog viewer*

The catalog browser already renders a working Three.js viewer in a `browser_mod.popup` ([model-detail-3d-viewer-tab.js](../../../../homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js), with the STL/3MF loaders under [loaders/](../../../../homeassistant/www/3d_printing/model_catalog/loaders)). Working Files **must reuse this same component** — no new viewer is in scope.

- **Trigger surfaces:**
  - Groups view: clicking a filename in the inline Model Files strip, or the per-row `mdi:cube-scan` icon when the extension is renderable.
  - Files view: clicking the Name cell, or the per-row 3D viewer action in the `⋯` overflow.
- **Payload shape:** the existing viewer takes a `model-ref` (path or hash). The working-files endpoint already returns `id`, `source_path_canonical`, `sha256_hash`, and `file_extension` per file — sufficient to drive the viewer the same way the catalog does.
- **Eligibility:** STL and 3MF render directly. STEP / OBJ / unknown extensions disable the viewer affordance with the same disabled-state visual used for the Slicer button on STEP files.
- **Browser security boundary:** the viewer fetches via the sidecar proxy URL, never `file:///` — consistent with the [working files local-launch design](../working-files-local-launch-and-slicer-integration-design.md) and the existing `file:///` browser-security memo. No new security surface is introduced.
- **Implementation cost:** an action handler + tile/icon binding in the working-files card. No viewer code, no new sidecar endpoint.

#### 4.4.2 Per-group detail / edit popup — *replaces the current `window.prompt` flows*

The current explorer card uses `window.prompt(...)` for "New working group title" and "Enter destination group id" ([model-catalog-working-files-explorer-card.js](../../../../homeassistant/www/3d_printing/model_catalog/model-catalog-working-files-explorer-card.js#L418-L463)). That is an explicit design debt called out in §8 of this document and in [working-files-workflow-redesign-issue-1169.md](../working-files-workflow-redesign-issue-1169.md). The redesign replaces both with a single proper **Group details popup** opened on group-title click.

Mockup: [mockups/working-files-group-popup.html](mockups/working-files-group-popup.html).

Fields and bindings:

| Section | Field | Editable | Backing |
| --- | --- | --- | --- |
| Header | Title (rename) | yes | `working_groups.title` (slug auto-rederived via `_slugify_title` / `_unique_slug` in [working.py](../../../../sidecars/model_catalog/app/routers/working.py)) |
| Header | Stage | yes (segmented) | `working_groups.stage` |
| Header | Folder hint | read-only | `working_groups.folder_hint` |
| Header | Last modified · last indexed | read-only | `last_file_mtime` (proposed) · `last_indexed_at` |
| Notes | Multiline notes | yes | `working_groups.notes` |
| Files | Reorderable list of group members | manage | `group_memberships` (add / remove / set primary) |
| Files | Set primary radio | yes | `working_groups.primary_file_path` |
| Files | Per-file row: open in 3D viewer · open in slicer · copy launch · remove | yes | reuses §3.5 affordances |
| Linked | "Used in N prints" stub list | read-only | `linked_archive_count` (proposed) — placeholder list when zero |
| Footer | Save · Cancel · Delete group (destructive, confirmed) | — | calls `update_working_group_service` / existing delete service |

Reuses the existing `update_working_group_service` already imported in [working.py](../../../../sidecars/model_catalog/app/routers/working.py); no new endpoint required for title/stage/notes/primary edits.

#### 4.4.3 Per-file metadata popup — *not in scope*

A dedicated per-file editing popup (custom name, description, tags) is **explicitly out of scope** for this redesign. Working Files are filesystem artefacts whose identity is the path + hash; the inline file strip already exposes everything that is read-only useful (filename, size, mtime, primary, validation, group memberships). Per-file notes / tags / aliases would require new schema and risk drift from the on-disk source of truth.

If a future iteration warrants a per-file popup (e.g. cross-group provenance, archive linkage drill-down), it should be additive and read-only by default. It is **not** part of this redesign's acceptance criteria.

---

## 5. Toolbar / header redesign

Mirrors [catalog-card-design.md §7](catalog-card-design.md) (issue #1216) so users moving between Catalog and Working Files don't relearn controls. The differences are minimal but important:

### 5.1 Three-row stack

1. **Title row** — "Working Files" + inline indexed-state pill (`Indexed 2m ago` + `Reindex` icon button). The reindex button replaces the standalone `Refresh` button from the current card; it always runs `forceReindex: true`.
2. **View tabs + filter bar** — `Groups | All Files | Ungrouped` segmented control on the left (replaces three pill buttons with a tighter segmented control to free up horizontal real estate); filter inputs (search, extension, group-membership filter) stretch to the right.
3. **Page-control strip** — only rendered when the current view returns more than `per_page` rows (Groups view today doesn't paginate; Files views can).

### 5.2 New filter chips

- `Modified < 7d` — quick chip to scope to recently-touched files (a frequent operator question: "what did I work on this week?").
- `Has warnings` — scopes to files where `validation_state != 'ok'` or `warnings[]` is non-empty.
- `Group: <name>` chip appears when the operator clicks a group-membership chip in the Files view, scoping the list to that group's members.

### 5.3 New sort dropdown

Inline with the title (matching catalog #1216 pattern):

- Groups view: `Recently modified` (default, derived from `last_file_mtime`), `Title A→Z`, `Most files`, `Stage (Draft → Ready)`.
- Files view: `Recently modified` (default), `Name A→Z`, `Largest first`, `Most groups`.

### 5.4 Display toggles

- `Show thumbnails` (mirror of the catalog `Show media` toggle) — when off, the group thumb and file-type icons collapse to a single 16 px badge; row height drops from ~96 px to ~56 px for high-density scanning.
- `Group selection` (collapse vs expand all) — button toggles all rows expanded/collapsed for power-scan workflows.

---

## 6. Component anatomy reference table

| Component | Reuses from | New / divergent |
| --- | --- | --- |
| ha-card shell | catalog-card-design.md §3 | — |
| Stage ribbon | catalog queue ribbon | colour mapping is per-stage instead of per-queue |
| Inline file strip | *(new)* | Working Files specific; not in catalog cards |
| File-row mtime | *(new)* | promoted from currently-hidden `source_mtime` |
| Group memberships chip row | catalog publish-destination chips | identical visual grammar |
| List view rows | catalog list view | column set differs (size/mtime/groups instead of archives/success/published-to) |
| Toolbar 3-row stack | catalog toolbar (issue #1216) | adds Reindex pill, segmented view tabs |
| Bulk-action bar | catalog list view bulk bar | identical visual grammar |
| Sort dropdown in title row | catalog #1216 | different sort options |
| `Slicer` action button | working-files local-launch design | uses tokenized download URL (Option B) |
| 3D viewer popup | catalog [model-detail-3d-viewer-tab.js](../../../../homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js) | reused as-is; new entry points only |
| Group details / edit popup | *(new — replaces `window.prompt`)* | uses `browser_mod.popup` shell + existing `update_working_group_service` |

---

## 7. Backend touch points (summary)

| Surface | Layer | Change |
| --- | --- | --- |
| `GET /api/working-files/explorer` | sidecar (Layer 2-equivalent) | Add `last_file_mtime`, `is_primary` per file, optional `linked_archive_count`, optional `derived_thumbnail_path`, `last_indexed_at` in `summary`. |
| `working_groups.primary_file_path` | sidecar | Already exists; the per-file `is_primary` is purely derived. |
| Slicer launch tokenized URL | sidecar | Per the existing local-launch design doc — separate work item. |
| `model_catalog_explore_working_files` rest_command | HA package | No contract change required; new fields flow through transparently. |
| Card resource version | HA www | Bump version in [_resources.yaml](../../../../homeassistant/packages/3d_printing/common/dashboards/_resources.yaml) when card JS is updated, per repo guidance. |

---

## 8. Open questions

1. **Group thumbnails source** — is there an existing thumbnail extracted by the 3MF metadata pipeline we can reuse, or does this need a new extraction job? If new, defer thumbnail rendering to a follow-up phase and ship the redesign with the typed placeholder.
2. **Per-file linked-archive count cost** — the join against archives could be expensive on large libraries; gate behind a `with_archive_counts=true` query param if performance is a concern.
3. **Drag-and-drop** between groups — explicitly out of scope for this iteration. The bulk-action bar covers the same workflow without the accessibility cost. Re-evaluate after the first round of operator feedback.
4. **Group thumbnail aspect** — square (folder metaphor) vs landscape (parity with print-history)? Recommended: square 64×64 to visually distinguish "folder of files" from "individual archive".
5. **`window.prompt` removal** — the current "Add to group" / "Create group" flows use `window.prompt`; the redesign assumes a small popover. Implementation effort is non-trivial; flag as a separate follow-up if it slips this iteration. The Group details popup in §4.4.2 is the canonical replacement for the rename and destination-group prompts.
6. **Tags on working groups?** — the catalog supports tags; `working_groups` does not. The Group details popup in §4.4.2 deliberately does **not** include a Tags field pending a product decision. Adding tags would require either a `working_group_tags` join table or a JSON column on `working_groups` (Layer 2 schema add). Recommend deferring until there is operator demand; group-level `notes` covers the freeform-text use case in the meantime.
7. **3D viewer for non-`.3mf`/`.stl` files** — STEP / OBJ extensions today lack a Three.js loader in the catalog viewer. Decision: disable the viewer affordance for those extensions in this iteration; revisit if a STEP-capable loader is added to the catalog (it would be picked up automatically since Working Files reuses the same viewer).

---

## 9. Acceptance for design review

This proposal is approval-ready when reviewers confirm:

- Group row anatomy in §3 is the correct primary surface (not the legacy split-pane).
- Inline file strip showing `.3mf` files + last modified satisfies the "see model files from the list view" ask.
- Files view in §4 is the right home for cross-group triage.
- Toolbar redesign in §5 maintains parity with catalog #1216 without forcing it where it doesn't fit.
- Backend additions in §7 are acceptable in scope, with `linked_archive_count` and `derived_thumbnail_path` flagged as optional for a follow-up.
