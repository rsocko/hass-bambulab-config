# Model Catalog — Edit & Fork (Catalog ↔ Working Files)

> **Status:** Design proposal (authoritative for the Catalog → Working → Re-publish lifecycle).
> **Created:** 2026-05-25
> **Audience:** Architecture review, implementation planning
> **Related design docs:**
> - [catalog-advanced-actions.md](catalog-advanced-actions.md) — Hosts the new actions on the catalog popup.
> - [working-files.md](working-files.md) — Source/target of forks; intake re-publish lives here (§5).
> - [working-files-launch.md](working-files-launch.md) — Slicer-launch / replace-file contract reused by edit flows.
> - [projects.md](projects.md) — Optional Project linkage suggested on fork.
> - [local-model-storage.md](local-model-storage.md) — Immutable `{slug}--{shortid}` folder identity.
> - [../reference/external-storage-behavior.md](../reference/external-storage-behavior.md) — "No native promote/demote" stance.
> - [../reference/operator-workflow.md](../reference/operator-workflow.md) — "Do not treat the catalog as the default place for ad hoc iterative editing."

---

## 1. Why this exists

The existing operator stance is clear: do not edit catalog files in place; copy or branch into Working Files, edit, then publish a new canonical revision. However, today there is **no first-class action** for that copy-out flow, **no defined re-publish path** that targets an existing catalog model, and **no name-conflict / version policy** at the catalog tier. This document closes those gaps as a single coherent contract spanning the Catalog popup, the Intake Wizard, the sidecar database, and the Projects layer.

Concretely this design defines:

1. A new catalog-side action — **Send to Working Files** (`fork-to-working`) — formalizing the copy-out flow.
2. A new Intake Wizard destination mode — **Republish as new version of existing model** (`republish_as_new_version`) — with an explicit conflict-policy table.
3. A new optional catalog-side action — **Edit catalog file in place (Advanced)** (`edit-in-place-advanced`) — gated behind type-to-confirm + automatic versioned snapshot. Disabled by default.
4. New persistence — `model_catalog_lineage` and `model_catalog_revisions` tables — to capture fork lineage and per-revision file history.
5. Auto-suggested Project creation on fork, so multi-revision lineage is discoverable from a single Project page.

The design preserves the **immutable folder identity** contract from [local-model-storage.md](local-model-storage.md): the canonical re-publish path creates a new `{slug}--{shortid}` folder per revision; the legacy folder is untouched.

---

## 2. Scope and non-goals

### In scope

- Catalog → Working Files copy-out (the "fork" verb).
- Working Files → Catalog re-publish targeting an **existing** logical model (new revision OR overwrite-in-place OR error-on-conflict).
- Lineage and revision audit tables.
- Optional Project auto-suggest on fork.
- Optional opt-in in-place edit of catalog files via the companion helper, with snapshot guardrails.

### Out of scope

- Auto-pruning abandoned forks (operator-driven cleanup only).
- Automatic re-linking of historical archive records to a new revision (operator prompted, default = no).
- Reshaping the existing Intake Wizard `grouped_new` / `grouped_existing` Working destinations.
- Merging two diverged forks back into a single working folder (manual file management for now).

---

## 3. Fork: Catalog → Working Files

### 3.1 Action

| Action ID | Tab | Label | Icon | Tone |
| --- | --- | --- | --- | --- |
| `fork-to-working` | Files & Sources | Send to Working Files | `mdi:source-branch-plus` | — |

Lives on `custom:model-catalog-advanced-actions-card` (see [catalog-advanced-actions.md §3.2](catalog-advanced-actions.md)). The action is **copy-only** — there is no "Move out of Catalog" variant. The catalog row is preserved unconditionally as the prior published revision.

### 3.2 Confirm dialog (sub-mode: `fork-to-working-confirm`)

The operator picks:

| Field | Options | Default |
| --- | --- | --- |
| **Which files?** | `all` / `primary_only` / `pick` (multi-select list) | `all` |
| **Working folder name** | text (validated as a folder-safe slug) | `{slug}-edit-{YYYYMMDD}` |
| **Project linkage** | `none` / `new_project` / `existing_project` (picker) | `new_project` if model has no existing Project, else `existing_project` pre-filled |
| **Mark catalog as "edit in progress"** | boolean (sets a soft flag — informational only, non-blocking) | `false` |

The dialog also shows a destination-path preview (`Model Working Files/{folder}`) and a collision check: if the working folder name already exists, a "-2", "-3" suffix is appended (matches the legacy working-file-spec collision rule, applied here at folder level rather than file level).

### 3.3 Backend endpoint

`POST /api/models/{model_id}/fork-to-working` (sidecar router).

Request body:

```json
{
  "working_folder_name": "gridfinity-bin-edit-20260525",
  "files": "all",
  "file_paths": [],
  "project_linkage": {
    "mode": "new_project",
    "existing_project_id": null,
    "new_project_title": null
  },
  "mark_catalog_edit_in_progress": false
}
```

Response:

```json
{
  "working_folder_path": "/assets/Model Working Files/gridfinity-bin-edit-20260525",
  "files_copied": 7,
  "files_skipped": 0,
  "project_id": "proj_…",
  "lineage_id": 42
}
```

Side effects:

1. Creates the working folder under `MODEL_CATALOG_WORKING_ROOT`.
2. Copies the selected catalog files (preserving filenames; folder is empty before copy so there are no in-folder collisions to resolve).
3. Writes a pre-populated `.modelmeta.json` containing `source_catalog_model_id`, `source_catalog_revision_at` (timestamp), and copies forward `display_title`, `tags`, `origin_url`, `primary_file` if present.
4. Writes a stub `README.md` ("Forked from catalog model {title} on {date}. See lineage row {id}.").
5. Inserts a `model_catalog_lineage` row (§7.1).
6. Optionally creates a Project (§6) and attaches both the new working folder and the source catalog model to it.
7. Optionally sets `catalog_models.edit_in_progress_at` (timestamp) on the source row when `mark_catalog_edit_in_progress=true`. Purely informational; never blocks downstream operations.

### 3.4 Behavior when the catalog model is later deleted

The `delete-model` flow (see [catalog-advanced-actions.md §4](catalog-advanced-actions.md)) is extended:

- If any **active** `model_catalog_lineage` row references this model as `parent_model_id` with `outcome IS NULL`, the confirm-1 screen surfaces a warning panel listing the active forks with deep links to their working folders and offers a "Mark forks as orphaned" toggle (default off → forks become `outcome='parent_deleted'`).
- The fork itself is **not** deleted — Working Files survive catalog deletion per the existing preservation contract.

### 3.5 Concurrency

Forks are independent. Two operators may fork the same catalog model into separate working folders simultaneously; the design does not lock the parent. Reconciliation across forks is the operator's responsibility (or the Project page, once it lists siblings).

---

## 4. Re-publish: Working Files → existing Catalog model

### 4.1 New Intake Wizard destination mode

[working-files.md §5](working-files.md) currently exposes two Curated destination choices in the Organize step:

- `create_new` (new catalog model)
- `attach_existing` (attach to an existing catalog model without changing its files)

This design adds a third:

- **`republish_as_new_version`** — pick an existing catalog model as the **logical parent** of the publish operation. The publish honors one of three conflict modes (§4.2).

The mode is offered any time the wizard detects a `source_catalog_model_id` in the source folder's `.modelmeta.json`, and is also available manually from a target-picker.

### 4.2 Conflict policy

When publishing a working folder against an existing catalog model, file-name and content collisions are resolved by one of three modes selected in the Organize step:

| Mode | Folder behavior | Filename collision behavior | When to use | Audit |
| --- | --- | --- | --- | --- |
| **`new_revision`** *(default)* | A **new** `{slug}--{shortid}` folder is created. The previous folder is untouched. | None possible — different folder. | Standard "this is v2 of the design" case. Preserves the prior revision for reprints and archive linkage. | `model_catalog_revisions` row (`source='wizard_new_revision'`); `parent_model_id` set; `revision_number = N+1`. |
| **`overwrite_in_place`** | Files inside the existing catalog folder are replaced. | Replaced by name. Files not in the incoming set are **left in place** by default; the wizard offers an "also remove files missing from source" checkbox. | Hotfix / metadata-only correction / preview regen where prior bytes have no historical value. | Wizard **automatically snapshots** the existing folder to `Model Catalog/_revisions/{model_id}/{ts}/` before mutation. `model_catalog_revisions` row (`source='wizard_overwrite'`) records `files_changed`, `files_removed`, snapshot path. Type-to-confirm required. |
| **`error_on_conflict`** | Pre-flight check before any write. | If any incoming filename already exists in the target folder with a different hash, the publish aborts with `409 publish_conflict` listing the conflicting names. | Scripted / CI publishes that must never silently mutate. | No mutation, no revision row. |

Default = `new_revision`. The wizard surfaces a one-line preview ("Will create new folder `gridfinity-bin--f7e8c9d0`; 7 files copied. Previous revision `gridfinity-bin--a1b2c3d4` remains.") before commit.

**No `filename-2.ext` auto-suffixing is applied at the catalog tier.** The legacy `filename-2.ext` rule is retained for Working Files only (where two files with the same basename can legitimately coexist in one in-progress folder).

### 4.3 Successor / predecessor relationships

A successful `new_revision` publish:

1. Inserts the new catalog model row with `parent_model_id` set to the previous head and `revision_number = previous.revision_number + 1`.
2. Sets `superseded_by_model_id` on the previous head.
3. Clears `catalog_models.edit_in_progress_at` on the parent (if set).
4. Marks the `model_catalog_lineage` row associated with the source working folder as `outcome='republished'`, `republish_target_model_id=<new>`, `republished_at=<now>`.
5. Surfaces a one-time prompt in the wizard summary: **"Re-link {N} archives created after the fork to the new revision?"** — default **no**. If accepted, only archive links with `archive.print_started_at > lineage.forked_at` are migrated; older archives remain pointed at the prior revision.

### 4.4 Partial-file publishes

`new_revision` and `overwrite_in_place` both support partial updates: the wizard computes per-file hash diffs and shows a "3 files changed, 4 unchanged" summary. For `new_revision`, unchanged files are still copied into the new folder (each revision is a complete snapshot). For `overwrite_in_place`, unchanged files are not rewritten on disk.

### 4.5 Target may differ from fork parent

If the working folder was forked from model A but the operator selects model B as the republish target, the wizard warns ("This folder was forked from a different model.") and requires explicit confirmation. The `model_catalog_lineage` row records both `parent_model_id` (A) and `republish_target_model_id` (B).

### 4.6 Sources outside the Working Files root

`republish_as_new_version` is available for any Intake source (browser upload, server inbox, working files). When the source is not a working folder, no lineage row exists; the wizard records `model_catalog_revisions.source` accordingly and notes that no follow-up edit folder is registered.

---

## 5. In-place edit of catalog files (Advanced, off by default)

### 5.1 Stance

The default and recommended flow is **fork → edit → republish**. In-place editing of catalog files is **not** offered as a default affordance. The reasons are recorded in [../reference/operator-workflow.md](../reference/operator-workflow.md) and [../reference/external-storage-behavior.md](../reference/external-storage-behavior.md) and summarized here:

- No automatic version history at the catalog tier.
- OneDrive / cloud sync races on partial writes against hash-based dedupe, the 3D viewer cache, and archive linkage consumers.
- Catalog rows are referenced by archives, Projects, and ranking; immutable identity simplifies all of them.
- The companion-helper trust boundary ([working-files-local-helper-tray-heartbeat.md](working-files-local-helper-tray-heartbeat.md)) was scoped tight on purpose.

### 5.2 Opt-in action (when explicitly enabled)

| Action ID | Tab | Label | Icon | Tone |
| --- | --- | --- | --- | --- |
| `edit-in-place-advanced` | Files & Sources (Advanced section) | Edit catalog file in place (Advanced) | `mdi:file-edit-outline` | `danger` |

Gating:

1. Hidden unless `model_catalog_allow_in_place_catalog_edit` (sidecar settings / HA input_boolean) is `true`. Default `false`.
2. Visible only when the companion helper is reachable (heartbeat fresh).
3. Confirm sub-mode (`edit-in-place-confirm`) requires:
   - Type-to-confirm the catalog model title.
   - Acknowledge a one-line warning: "Archive links and Project lineage will not auto-update. This edit will be recorded in the revision log."

Side effects on accept:

1. Sidecar snapshots the current catalog folder to `Model Catalog/_revisions/{model_id}/{ts}/` before launch.
2. Inserts a `model_catalog_revisions` row with `source='in_place'`, `files_changed=[]` (filled in post-edit when the companion confirms file changes).
3. Tokenized companion launch opens the requested file in the slicer with the on-disk path under `Model Catalog/...`. Save writes through to the same path.
4. Post-edit, the companion notifies the sidecar to reindex the model folder (hashes, 3D viewer cache invalidation, thumbnail regen if applicable). `files_changed` and `sha_before`/`sha_after` are populated.

### 5.3 Failure modes covered

| Failure | Behavior |
| --- | --- |
| Snapshot fails (disk full, permission) | Edit aborts; no companion launch. |
| Companion crashes mid-edit | Snapshot remains intact; reindex on next sidecar boot detects unindexed mutation and surfaces a "catalog folder modified outside revision flow" warning on the model. |
| Cloud sync partial write race | Reindex hash mismatch triggers a `revisions.source='detected_drift'` row and the model card surfaces a warning chip; operator can restore the snapshot. |

### 5.4 Reverting

A revision row exposes a `Restore this snapshot` action (sub-mode under Files & Sources). The restore is itself a new `model_catalog_revisions` row (`source='restore'`, `restored_from_revision_id=…`) — restores never silently overwrite prior history.

---

## 6. Project auto-suggestion on fork

The fork dialog (§3.2) defaults `project_linkage = new_project` when the source catalog model is not currently in any Project. The Intake Wizard re-publish step (§4) shows the resolved Project context if one exists, and offers to attach the new revision to the same Project (default on).

Concretely:

- On fork with `project_linkage = new_project`: a Project is created with `title = "{model_title} (lineage)"`, `project_type = model_family`, `working_group_ids = [new_folder]`, `curated_model_ids = [source_model_id]`.
- On fork with `project_linkage = existing_project`: the new working folder is added to that Project's `working_group_ids`.
- On `new_revision` re-publish: the new catalog model is added to the same Project's `curated_model_ids`. Variant/lineage metadata is set per [projects.md](projects.md) (`variant_of`, `published_from_group_id`).
- Project linkage is **optional** at every step; operators may pick `none` and the lineage remains queryable via `model_catalog_lineage`.

---

## 7. Persistence additions

### 7.1 `model_catalog_lineage`

Tracks fork-to-working operations and their downstream outcomes.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | INTEGER PK | — |
| `parent_model_id` | TEXT | Source catalog model id. |
| `working_folder_path` | TEXT | Destination folder under `MODEL_CATALOG_WORKING_ROOT`. |
| `project_id` | TEXT NULL | Set if Project linkage was created/attached. |
| `forked_at` | TEXT (ISO) | — |
| `forked_by` | TEXT NULL | Operator identifier if available. |
| `outcome` | TEXT NULL | One of `republished`, `abandoned`, `parent_deleted`. NULL = active. |
| `republish_target_model_id` | TEXT NULL | Set when outcome = `republished`. May differ from `parent_model_id` (see §4.5). |
| `republished_at` | TEXT NULL | — |
| `notes` | TEXT NULL | — |

Indexes on `parent_model_id` and on `working_folder_path`.

### 7.2 `model_catalog_revisions`

Per-revision audit for every mutation of a catalog model's files (republish, in-place edit, restore, detected drift).

| Column | Type | Notes |
| --- | --- | --- |
| `id` | INTEGER PK | — |
| `model_id` | TEXT | Catalog model id at the time of the revision. |
| `revision_number` | INTEGER | Monotonic per `model_id`. |
| `parent_revision_id` | INTEGER NULL | Previous revision (for restore / drift bookkeeping). |
| `source` | TEXT | One of `wizard_new_revision`, `wizard_overwrite`, `in_place`, `restore`, `detected_drift`. |
| `source_intake_item_id` | TEXT NULL | Set when source = `wizard_*`. |
| `snapshot_path` | TEXT NULL | Set when a snapshot was taken (overwrite/in-place/restore). |
| `files_changed` | JSON | `[{path, sha_before, sha_after, size_before, size_after}]`. |
| `files_removed` | JSON | `[path, …]`. |
| `files_added` | JSON | `[path, …]`. |
| `operator` | TEXT NULL | — |
| `created_at` | TEXT (ISO) | — |
| `notes` | TEXT NULL | — |

For `new_revision`, the row records the **new** model_id with `revision_number = N+1` and `parent_revision_id` pointing to the previous head's revision row.

### 7.3 `catalog_models` extensions

Additive columns on the existing model row:

| Column | Type | Default | Notes |
| --- | --- | --- | --- |
| `parent_model_id` | TEXT NULL | NULL | Logical parent in a revision chain. |
| `revision_number` | INTEGER | `1` | Monotonic within a parent chain; `1` for first-published. |
| `superseded_by_model_id` | TEXT NULL | NULL | Set on the prior head when a `new_revision` publish completes. |
| `edit_in_progress_at` | TEXT NULL | NULL | Informational soft flag set by `fork-to-working`; cleared on republish. |

All four are nullable / defaulted to preserve backward compatibility with existing rows.

---

## 8. UX surfaces

### 8.1 Catalog popup (read-only chip)

The model-detail popup ([catalog-popup.md](catalog-popup.md)) adds a small chip when at least one of the following is true:

- `edit_in_progress_at IS NOT NULL` → chip: "Edit in progress" linking to the lineage row's working folder.
- `superseded_by_model_id IS NOT NULL` → chip: "Superseded by v{N+1}" linking to the successor model.
- `parent_model_id IS NOT NULL` → chip: "Revision {N} of {N-of-N}" linking back to the parent.

### 8.2 Advanced Actions — Files & Sources sub-mode `versions`

A new sub-mode listing the full revision chain for the current model:

- Predecessors (`parent_model_id` chain) with publish date, operator, and file-count delta.
- Successors (rows where `parent_model_id = this`).
- Active forks (rows in `model_catalog_lineage` with `outcome IS NULL`).

### 8.3 Working Files header — fork badge

A working folder whose `.modelmeta.json` carries a `source_catalog_model_id` shows a header badge "Forked from catalog: {title}" with a deep link to the catalog popup, plus a soft nudge if `forked_at` is older than 30 days with no republish.

### 8.4 Wizard summary — re-link prompt

Post-`new_revision` publish, the wizard summary screen surfaces the one-time archive re-link prompt described in §4.3. The prompt is also retrievable from the resulting catalog model's Prints tab for the next 7 days.

---

## 9. API additions (summary)

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/models/{model_id}/fork-to-working` | POST | §3.3 |
| `/api/models/{model_id}/lineage` | GET | List `model_catalog_lineage` rows where this model is parent. |
| `/api/models/{model_id}/revisions` | GET | List `model_catalog_revisions` rows for this model. |
| `/api/models/{model_id}/revisions/{revision_id}/restore` | POST | Restore a prior snapshot (§5.4). |
| `/api/intake/{item_id}/publish` | POST (extend) | Add `destination_mode = republish_as_new_version` and `conflict_policy` body fields. |
| `/api/models/{model_id}/edit-in-place/start` | POST | Companion-mediated in-place edit (snapshot + token). Only when allowed. |
| `/api/models/{model_id}/edit-in-place/complete` | POST | Companion notifies post-edit; sidecar reindexes + fills revision row. |

Companion service / rest_command wrappers follow the existing naming pattern (`model_catalog_fork_to_working`, `model_catalog_get_lineage`, `model_catalog_get_revisions`, `model_catalog_restore_revision`).

---

## 10. Open questions

1. **Snapshot retention.** How many `_revisions/{model_id}/*` snapshots should be retained per model before pruning? Recommend a soft cap (e.g. 10) with manual override; tracked separately from this design.
2. **Cross-Project revision moves.** If a `new_revision` is published into a different Project than its parent, should the parent automatically be moved as well? Recommend: no, but surface a banner.
3. **Companion-driven in-place edit on a model not under `MODEL_CATALOG_CURATED_ASSETS_ROOT`.** Out of scope; companion launch is restricted to configured roots.
4. **Bulk fork (multiple models at once).** Not in v1. Single-model action only.
5. **Re-link prompt window.** 7 days is a starting value; revisit after operator feedback.

---

## 11. Implementation phasing

Phase ordering follows risk and dependency, not a calendar:

1. **Persistence + read-only surfacing.** Add `model_catalog_lineage`, `model_catalog_revisions`, and the four `catalog_models` columns. Backfill `revision_number = 1` for existing rows. Expose `GET /api/models/{id}/lineage` and `/revisions`. No new operator-visible mutations.
2. **`fork-to-working` action.** Catalog popup chip + Advanced Actions row + endpoint. Project auto-suggest hooked in. Catalog model still unchanged after fork.
3. **`republish_as_new_version` in the Intake Wizard.** New destination mode + `conflict_policy = new_revision` (the default and the simplest of the three). Archive re-link prompt and supersession chip surface here.
4. **`conflict_policy = overwrite_in_place` + `error_on_conflict`.** Snapshot writer, restore endpoint, type-to-confirm wiring.
5. **`edit-in-place-advanced` (opt-in).** Companion-mediated launch + post-edit reindex. Settings flag default `false`.

Phases 1–3 deliver the principal user value (fork + republish with new-revision semantics). Phases 4–5 are advanced and may be deferred.

---

## 12. Layering check

Per [.github/copilot-instructions.md](../../../../.github/copilot-instructions.md):

- **Layer 1** (`sensor.print_history_archives`) — no changes. Archive linkage to specific revisions remains routed through the sidecar.
- **Layer 2** (sidecar) — new tables, endpoints, revision/lineage logic, snapshot handling.
- **Layer 3** (cards) — new sub-modes on `model-catalog-advanced-actions-card`, chips on the catalog popup, wizard step additions. Resource URL bumps required per the cache-bust contract.
