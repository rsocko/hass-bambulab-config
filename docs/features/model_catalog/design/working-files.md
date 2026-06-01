# Working Files Design (Folder-First)

> **Status:** Authoritative design — supersedes the prior Working Groups model.
> **Last updated:** 2026-05-25
> **Supersedes:**
> - [archive/working-files-legacy-2026-05/working-files-workflow.md](archive/working-files-legacy-2026-05/working-files-workflow.md)
> - [archive/working-files-legacy-2026-05/working-files-card.md](archive/working-files-legacy-2026-05/working-files-card.md)
> - [archive/working-files-legacy-2026-05/working-file-spec.md](archive/working-files-legacy-2026-05/working-file-spec.md)
> - [archive/working-files-legacy-2026-05/mockups/](archive/working-files-legacy-2026-05/mockups/)
> **Related (still active):**
> - [working-files-launch.md](working-files-launch.md) — slicer / local-launch
> - [working-files-local-helper-tray-heartbeat.md](working-files-local-helper-tray-heartbeat.md) — tray helper
> - [intake-source-selection.md](intake-source-selection.md) — Intake Wizard source picker
> - [projects.md](projects.md) — Project / Collection layer (the only intentional logical container)

---

## 1. Core Principle

**A folder is a group. There is no separate Working Group entity.**

```
/assets/Model Working Files/                ← root
├── gridfinity-holders/                     ← one group
│   ├── v1/
│   │   └── holder-v1.3mf
│   ├── v2/
│   │   ├── holder-v2.3mf
│   │   └── README.md
│   └── .modelmeta.json
├── snowflake-ornament/                     ← one group
│   └── snowflake.3mf
└── quick-print.3mf                         ← part of the virtual "(loose files)" group
```

Rules:

1. **Each top-level folder under the Working Files root is a group.** Its name *is* the group name.
2. **Files sitting directly at the Working Files root** are presented together under one synthetic entry: `(loose files)`.
3. **Subfolders inside a group are internal organization**, not sub-groups. The card may navigate into them, but they do not appear in the top-level group list.
4. **No database rows for groups.** Group identity is the folder path; group membership is `file lives under that path`. The only DB-backed working data is the file inventory (used for indexing, hashes, thumbnails — see §6).
5. **Intentional logical grouping** (cross-folder bundling, stage/lifecycle, curated linkage) lives entirely on **Projects** and **Collections** — see [projects.md](projects.md). Working Files itself stays unopinionated.

This replaces and retires:

- `working_groups`, `working_items` tables and all related services
- multi-group membership, `allow_multi_group`, `primary_file_path`, `folder_hint`, `related_manyfold_model_id`
- the Groups / All Files / Ungrouped tri-state in the card
- group-level stage lifecycle (lives on Project now, if at all)
- bulk discover/import working groups, group reorganize-on-create
- any Manyfold references in working-files code paths (Manyfold is deprecated)

A separate deprecation plan covers the code/schema removal: [../planning/working-groups-deprecation.md](../planning/working-groups-deprecation.md).

---

## 2. UI Model

### 2.1 Single view — "Working Files"

The card has **one view**. No mode toggle. The toolbar is reduced to:

- Title: `Working Files`
- Refresh / reindex button
- (Future, see §9) Search

Tree structure shown:

```
Working Files
├── (loose files)                 ← virtual; only present if loose files exist
│   ├── quick-print.3mf
│   └── ...
├── gridfinity-holders            ← real folder = real group
├── snowflake-ornament
└── ...
```

### 2.2 Selecting a group

Selecting a top-level entry opens a detail pane for that group:

- Header: group display title (folder name unless overridden by sidecar `display_title`), file count, total size.
- Optional sidecar info: notes (rendered markdown), tags, origin link, primary file pin, thumbnail.
- **Files | Folders toggle** scoped to *this* group only. (Files = flat list of all files under the group folder; Folders = browse the nested folder structure.)
- File actions: preview, open in slicer / explorer (see [working-files-launch.md](working-files-launch.md)), copy path.
- Group actions:
  - `Add to Project…` / `Add to Collection…`
  - `Run Intake Wizard from this folder` (see §5)
  - `Open folder in Explorer`
  - (Sidecar edit affordance is optional — operator may also edit `.modelmeta.json` / `README.md` directly on disk.)

### 2.3 `(loose files)` virtual entry

Synthetic; not a folder on disk. Contains every file sitting directly at the Working Files root. Behaves like a group for display and Intake purposes:

- File actions work identically (preview, open, send to Project, run intake).
- Group-level actions that imply folder identity (`Open folder in Explorer` for the *group*) target the working-files root.
- Sidecar metadata is **not** supported on `(loose files)`; it has no folder of its own.
- It is hidden when there are no loose files.

### 2.4 No create/move services

Creating, renaming, splitting, merging, or moving groups happens in **Windows Explorer**. The card reflects the filesystem on next reindex.

The only file-system write the card itself initiates is the Intake Wizard (which may copy or move files into catalog storage — see §5).

---

## 3. Sidecar Metadata (Optional)

A group folder *may* contain either or both of:

- `.modelmeta.json` — structured fields, machine-readable, drives the card UI.
- `README.md` — free-form notes, rendered as markdown in the group detail pane.

Neither is required. A folder with no sidecar is a perfectly valid group.

### 3.1 `.modelmeta.json` schema

All fields optional. Unknown fields ignored (forward-compatible).

```jsonc
{
  "$schema": "https://hass-bambulab-config/schemas/modelmeta.v1.json",
  "display_title": "Gridfinity Magnet Holders",
  "primary_file": "v2/holder-v2.3mf",
  "tags": ["gridfinity", "magnet", "shop"],
  "origin_url": "https://makerworld.com/en/models/12345",
  "thumbnail": "v2/preview.png"
}
```

| Field | Type | Purpose |
|---|---|---|
| `display_title` | string | Override the folder name as shown in the UI. Folder name is still the canonical identity on disk. |
| `primary_file` | string (relative path) | The canonical `.3mf` / model. Used by `Open in Slicer` default, by Intake as the primary, and by previews. If absent, the card infers (largest `.3mf` matching folder slug, else first `.3mf` alphabetically). |
| `tags` | string[] | Flat cross-cutting labels. Surfaced in the group header and used by future search (§9). Not hierarchical. |
| `origin_url` | string | Source URL (Makerworld, Printables, etc.). Rendered as a link. |
| `thumbnail` | string (relative path) | Poster image for the group tile. If absent, the card infers from `.3mf` embedded thumbnail of `primary_file`. |
| `source_capture_record_id` | string | Optional sidecar linkage back to an external-source capture row. Used for rehydrate-on-publish flows; not operator-facing. |

**Not in sidecar (by design):**

- `status` / stage — lives on **Project** ([projects.md](projects.md)). A folder by itself has no lifecycle.
- `id` / `slug` — folder path is the identity. Renames update the identity.
- Any Manyfold reference — Manyfold is deprecated.
- Membership in projects/collections — those links live on the Project/Collection side.

`source_capture_record_id` is intentionally narrow: it links the folder back to sidecar-owned intake audit state, but it does not embed or duplicate the raw provider snapshot in Working Files.

### 3.2 `README.md`

Plain markdown. Rendered in the group detail pane under "Notes". No frontmatter required; if YAML frontmatter is present it is ignored by the card (use `.modelmeta.json` for structured fields).

### 3.3 Edit responsibility

Sidecar files are edited by the operator directly (VS Code, Notepad, etc.). The card may offer a convenience "edit" affordance in a later phase but is not required to. This keeps the card stateless with respect to group metadata.

---

## 4. What "loose files" and renames imply

### 4.1 Folder rename or move (external)

The folder *is* the group. Renaming it in Explorer renames the group. There is no DB row to update — next reindex picks up the new path. Sidecar files travel with the folder.

### 4.2 Project membership across renames

Projects link to a folder by **path**. A rename outside the card breaks that link.

- Detection: a Project pointing at a non-existent path is flagged in the Project UI as "orphaned".
- Resolution: operator re-points the Project at the new path. There is no auto-relink in v1.

(If rename-orphaning becomes a frequent problem, a future phase may add an opt-in `.modelmeta.json` `folder_id` UUID for stable identity across renames. Not in initial scope.)

### 4.3 Splitting / merging groups

Splitting = create a new folder in Explorer, move files in. Merging = drag one folder into another in Explorer. The card has no merge/split UI.

---

## 5. Intake Integration

The Intake Wizard remains the single path that produces catalog Models. Working Files becomes one of its **sources**, alongside Upload and Inbox.

### 5.1 Source choices in the wizard

The wizard's source-selection step (see [intake-source-selection.md](intake-source-selection.md)) gains a third entry:

| Source | Description |
|---|---|
| **Upload** | Browser file/folder upload (existing) |
| **Inbox** | Server-side Inbox folder (existing) |
| **Working Files** | Server-side Working Files root (new) |

Mechanically, Working Files is identical to Inbox in the wizard: the operator picks files/folders under the root using the same topmost-selection consolidation rules already defined in [intake-source-selection.md](intake-source-selection.md). No new selection logic.

### 5.2 Launch path from the card

From a group detail pane, **`Run Intake Wizard from this folder`** opens the wizard pre-configured with:

- source = Working Files
- preselected entry = this group's folder path
- recursive = true (operator can deselect items via the existing remove-from-source semantics)

This is the only "promote" path. There is no separate publish-from-group flow.

### 5.3 Copy vs Move

The wizard prompts the operator per run:

- **Copy (default, safe):** Files are copied into catalog storage. The Working Files folder is untouched. Use when the working folder is still actively edited.
- **Move:** Files are moved into catalog storage. The source folder is left in place (possibly empty); operator can delete it manually in Explorer. Use when the working folder is "done" and the catalog model is now the authoritative copy.

The choice is per intake run, exposed in the Source step UI. Default is Copy; the wizard never silently moves files.

### 5.3a Curated destination modes (Organize step)

The Organize step of the wizard exposes three Curated destination modes:

| Mode | Behavior |
|---|---|
| `create_new` *(existing)* | Create a new catalog model in a new `{slug}--{shortid}` folder. |
| `attach_existing` *(existing)* | Attach the published files to an existing catalog model without changing its files. |
| **`republish_as_new_version`** *(new)* | Publish against an existing catalog model as the **logical parent**, governed by the conflict-policy table below. Auto-offered when the source folder's `.modelmeta.json` carries `source_catalog_model_id` (set by the catalog-side **Send to Working Files** action). Authoritative spec: [catalog-edit-and-fork.md §4](catalog-edit-and-fork.md). |

#### Conflict policy for `republish_as_new_version`

| Policy | Folder behavior | Filename collision | When to use | Audit |
|---|---|---|---|---|
| **`new_revision`** *(default)* | New `{slug}--{shortid}` folder; prior folder untouched. | None possible. | Standard "v2 of the design". Preserves prior revision for reprints and archive linkage. | New `model_catalog_revisions` row (`source='wizard_new_revision'`); `parent_model_id` set; `revision_number = N+1`. |
| **`overwrite_in_place`** | Replaces files inside the existing catalog folder. | Replaced by name. Files missing from source are kept by default (opt-in checkbox to remove). | Hotfix / metadata-only correction / preview regen where prior bytes have no historical value. | Wizard automatically snapshots to `Model Catalog/_revisions/{model_id}/{ts}/` before mutation. Type-to-confirm required. |
| **`error_on_conflict`** | Pre-flight check; no mutation if any incoming filename collides with a different hash in the target. | Aborts with `409 publish_conflict`. | Scripted / CI publishes that must never silently mutate. | No revision row. |

Default is `new_revision`. The wizard surfaces a one-line preview (e.g. "Will create new folder `gridfinity-bin--f7e8c9d0`; 7 files copied. Previous revision `gridfinity-bin--a1b2c3d4` remains.") before commit. **No `filename-2.ext` auto-suffixing is applied at the catalog tier**; that rule remains a Working Files convention only.

After a successful `new_revision` publish, the wizard summary screen offers a one-time prompt to re-link archives created after the fork point to the new revision (default **no**).

### 5.4 Sidecar consumption

If the source folder has a `.modelmeta.json`, the wizard pre-populates corresponding fields in the Organize step:

- `display_title` → model title
- `primary_file` → primary file selection
- `tags` → model tags
- `origin_url` → origin metadata
- `thumbnail` → poster (if catalog supports operator-supplied thumbnails)

These are pre-fills, not locks; the operator may edit them in the wizard.

---

## 6. Indexing (Backend)

The card and Intake wizard both depend on a server-side index of the Working Files root. This stays largely as designed previously, minus all group-related concerns.

### 6.1 Scope

In-scope file types (model geometry + project files):

- `.3mf`, `.stl`, `.step`, `.stp`, `.obj`

Optional packed types (surface in lists but treat as opaque until Intake unpacks):

- `.zip`

Sidecar files (`.modelmeta.json`, `README.md`) are indexed as metadata, not as model files.

### 6.2 Root

- Indexing root: `/assets/Model Working Files`
- Constrained by `MODEL_CATALOG_WORKING_FILES_ROOT`
- Reindex may be scoped to a child folder, but the default is full-root.

### 6.3 Inventory record (`working_file_inventory`)

The only working-files DB table retained. Per-file row:

- relative path (under root)
- file type
- size, mtime
- sha256
- thumbnail-extracted blob path (for `.3mf`)
- last-indexed timestamp

No group_id, no membership, no folder_hint, no stage. The folder structure is derived at query time from `relative_path`.

### 6.4 Endpoints (new shape)

Replace the group-centric `/api/working-groups/*` and `/api/working-files/explore?view=...` surface with:

- `GET /api/working-files/tree` — top-level groups (folders under root) + `(loose files)` summary.
- `GET /api/working-files/groups/{folder_slug}` — group detail: files (flat), folder tree, sidecar contents.
- `GET /api/working-files/groups/{folder_slug}/files?mode=files|folders` — paginated file listing for the group, optionally folder-organized.
- `POST /api/working-files/reindex` — full or scoped reindex.
- `GET /api/working-files/loose` — files at the root.

Old endpoints are deprecated and removed per [../planning/working-groups-deprecation.md](../planning/working-groups-deprecation.md).

---

## 7. What we lose (explicit acknowledgement)

These were available under the old design and are intentionally dropped:

1. **Group-level lifecycle stage** (`draft → ready → published`) — relocates to Project, or simply unused.
2. **Cross-folder logical bundling** of files into a single group — use Projects for intentional bundling.
3. **Multi-group membership** of a single file — irrelevant when group = folder.
4. **Group title independent of folder name** — recoverable via `display_title` in `.modelmeta.json`.
5. **Stable group identity across external renames** — recoverable in a future phase via optional `folder_id` in sidecar (see §4.2).
6. **Group-level audit trail** of stage transitions and membership edits — gone (was tied to group lifecycle, which is gone).
7. **Group-reorganize-on-create** dry-run/execute service — gone; reorganization is operator-driven in Explorer.

None of these are blockers; each maps either to a Project-layer feature, to operator-in-Explorer behavior, or to "not actually needed in practice."

---

## 8. What we gain

1. One mental model: **a folder is a group**. The card, Explorer, Slicer, OneDrive, backups, and Git all agree.
2. No DB ↔ filesystem drift. Reindex is the only source of truth for working state.
3. Schema collapses: `working_groups` and `working_items` tables removed; `working_file_inventory` retained for indexing only.
4. Card collapses to a single view with one toolbar. No mode tri-state, no group chips, no membership ambiguity, no `Remove from all groups` vs `Remove from active group` choice.
5. No create/move/split/merge services to maintain. Group lifecycle = filesystem lifecycle.
6. Intake gets one new source (Working Files); no new selection logic is needed.
7. Intentional logical organization has one home: **Projects** ([projects.md](projects.md)).

---

## 9. Out of scope / later phases

The following are explicitly deferred:

- **Search.** A search box across the Working Files tree is not in v1. The single-tree view + group sidecars + reasonable group counts make it unnecessary at first. Revisit when a real user need appears.
- **Tag-based cross-cutting filters.** Tags are stored in sidecars and shown in headers, but a tag-filter UI is deferred until search lands.
- **In-card sidecar editor.** Editing `.modelmeta.json` and `README.md` happens in the operator's editor for v1.
- **Auto-relink on folder rename.** Path-keyed identity is acceptable in v1; folder rename + manual Project re-point is the recovery path.
- **Folder-level operations from the card** (rename, move, delete). Operator uses Explorer.
- **Group thumbnails synthesized from `.3mf`** when no sidecar `thumbnail` is set — desirable but a phase-2 polish.

---

## 10. Migration summary

Detailed in [../planning/working-groups-deprecation.md](../planning/working-groups-deprecation.md). High-level:

1. Existing `working_groups` rows whose `folder_hint` matches a real folder under the working root → the folder simply becomes the group; any operator-friendly fields (title, notes, primary_file_path) are exported into a `.modelmeta.json` written into that folder. Tags / origin_url / thumbnail join the same file.
2. Groups with no `folder_hint` or whose hint does not match a real folder → flagged in a one-time migration report; operator decides whether to discard or create a folder.
3. Files with N>1 group memberships → file stays on disk; sidecars in each candidate folder note the file path under `tags` (`shared-with:other-folder-name`) so cross-references survive. Operator can clean up post-migration.
4. Projects (`model_catalog_projects`) currently linking to working_groups by id → linkage rewrites to folder path.
5. All Manyfold references (`related_manyfold_model_id`, `bambuddy-manyfold` linkage paths in working files surfaces) → removed.
6. `working_items` and `working_groups` tables → dropped after migration export completes.
7. Card and API surfaces flip to the new endpoints in §6.4. Old endpoints return HTTP 410 with a pointer to the new ones during a deprecation window, then are removed.

---

## 11. Open items for follow-up

These are explicitly *not* decided here and need their own discussions:

1. **Project ↔ folder linkage cardinality.** Is a folder allowed in multiple Projects? Recommend one-to-many (a folder belongs to ≤1 Project) but [projects.md](projects.md) currently implies many-to-many. Reconcile before migration.
2. **Project lifecycle stage semantics.** With stage no longer on groups, the Project's stage definition needs to be tightened in [projects.md](projects.md).
3. **Intake "move" behavior on shared folders.** If a Working Files folder is referenced by a Project and the operator picks "Move" in the wizard, the Project link becomes orphaned. Wizard should warn.
4. **Loose-files Intake.** Can the operator launch Intake against the `(loose files)` virtual group? Recommended yes (treat as a flat selection of file paths), but worth confirming.
