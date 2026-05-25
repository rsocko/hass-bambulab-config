# Working Groups Deprecation Plan

> **Status:** Plan (no code changes yet).
> **Authoritative target design:** [../design/working-files.md](../design/working-files.md)
> **Last updated:** 2026-05-25

The Working Groups entity (DB rows + APIs + UI surfaces) is being removed in favor of the folder-first Working Files design. This document tracks the code/schema removal work. The design doc itself does not need to wait on this plan — it is already authoritative for new development.

---

## 1. Scope

In-scope to remove or transform:

- DB tables `working_groups`, `working_items`
- All `/api/working-groups/*` endpoints in `sidecars/model_catalog/app/routers/working.py`
- The `view=groups` / multi-group / `allow_multi_group` branches of `explore_working_files()`
- Bulk discover / import working groups services (around `working.py` L2175–L2186)
- Group reorganize-on-create services (dry-run + execute)
- `_working_group_url`, `_read_working_groups_for_matching`, `_read_working_group_summaries` in `archive_links.py` and supporting tests in `tests/sidecars/model_catalog/test_archive_link_candidate_discovery.py`
- `local://working-group/{id}` URL scheme in archive linking
- `entity_type == "working_group"` everywhere in the catalog cache, browser card, and archive link UI
- All `manyfold` linkage in working files surfaces (`related_manyfold_model_id`, working-group→manyfold pairs, the manyfold sidecar integration paths that only existed for working groups)
- Working-files explorer card filters that reference group selection / Active group / "Remove Selected from row group"

Out of scope (untouched):

- Model catalog `model_catalog_entries`, `model_catalog_assets`, `model_catalog_projects`
- Inbox + intake wizard core
- Working file inventory table (`working_file_inventory`) and any thumbnail / sha256 / mtime indexing
- Slicer / local-launch and tray-helper code paths
- Print history, queue, statistics, maintenance packages

---

## 2. Removal map

### 2.1 Backend (`sidecars/model_catalog/`)

| File | Action |
|---|---|
| `app/db_migrations.py` | Drop `working_groups` and `working_items` create-table migrations. Add a migration that drops the tables after one-time export (see §3). |
| `app/routers/working.py` | Replace `explore_working_files()` (L1681) and `list_working_groups()` (L2044) with the new endpoints defined in design doc §6.4 (`/tree`, `/groups/{slug}`, `/groups/{slug}/files`, `/reindex`, `/loose`). Delete bulk discover/import (L2175–L2186) and reorganize endpoints. |
| `app/routers/archive_links.py` | Delete `_working_group_url`, `_read_working_groups_for_matching`, `_read_working_group_summaries`. Remove `local://working-group/{id}` candidate generation. |
| `app/catalog_cache.py` | Drop the `working-group/` URL suffix branch (L70) and any working_group cache keys. |
| `cli/cleanup.py` | Drop `working_items` and `working_groups` from cleanup table lists (L20–L21). |
| Manyfold integration helpers under `app/` (anything keyed on `related_manyfold_model_id`) | Delete. |

### 2.2 Frontend (`homeassistant/www/3d_printing/model_catalog/`)

| File | Action |
|---|---|
| `model-catalog-working-files-explorer-card.js` | Full rewrite to single-view design from working-files.md §2 (separate task; not part of this deprecation PR). For this PR: remove the Search field (deferred per design §9), remove `_workingGroups` Active-group selector, remove `remove-selection-from-row-group` action, drop `?view=` parameters. |
| `model-catalog-browser-card.js` | Remove `_entityTypeFilters.showWorkingGroups` and the toggle chip (L44, L142, L1076, L1582–L1583, L3456). Remove `_workingGroupIdForModel()` and `working-group://` URL parsing (L207–L222). Remove "Open in Working Files" action wiring (L1801–L1807, L3750–L3753, L4335 `_openWorkingFilesExplorer`). Replace with a per-folder "Open in Working Files" affordance once the new explorer card lands. Drop `entity-type-pill.working-group` styling (L3602, L4655, L4772). |
| `model-catalog-bulk-import-card.js` | Decide: retire entirely (recommended) or repurpose as "Bulk Intake". Title strings reference "Bulk Working-Group Import" (L25, L387). |
| `model-catalog-inbox-review-card.js` | Drop `_workingGroups` state (L151), `working_group_ids` handling (L281–L291), the "Attach to existing working group" prompt (L517–L520), and the `open-working-section` button (L909). Inbox publishes to catalog Models; working group linkage no longer exists. |
| `model-catalog-intake-home-card.js` | Drop `workingGroupId` plumbing in publish response handler (L1422). |
| `model-catalog-intake-wizard-overrides.js` | Drop `workingGroupIds` plumbing (L4400). |
| `_resources.yaml` | Bump the version query string of every JS resource touched, per repo guidance. |

### 2.3 Tests (`tests/sidecars/model_catalog/`)

- `test_archive_link_candidate_discovery.py` — drop `_init_working_groups_schema` helper and the `TestWorkingGroupUrl`, `TestReadWorkingGroupsForMatching`, `TestReadWorkingGroupSummaries` suites; revise the cross-entity precedence tests that assert `working-group/...` ordering to only cover models + projects.
- Any intake / inbox tests that assert `working_group_id` / `working_group_ids` in publish responses must be updated to assert the new (group-less) shape.
- Add new tests covering the design doc §6.4 endpoints.

---

## 3. One-time migration / export

Before dropping the tables, write the contents of `working_groups` and `working_items` into sidecar files on disk:

1. For each `working_groups` row whose `folder_hint` matches an existing folder under `MODEL_CATALOG_WORKING_FILES_ROOT`:
   - Build a `.modelmeta.json` from `{title→display_title, primary_file_path→primary_file, tags, origin_url, thumbnail}`.
   - Write the file in that folder if one does not already exist; if one exists, merge non-conflicting keys and log conflicts to the migration report.
2. For rows with no folder_hint or with a mismatched hint, write nothing — log to the migration report so the operator can decide.
3. For files with N>1 group memberships, record cross-references in the migration report (no automatic file movement).
4. Emit a single migration report at `tmp/working-groups-migration-report.md` listing: groups exported, conflicts, orphans, multi-group files. Operator reviews before the table-drop migration runs.

This export is a one-time script (e.g. `sidecars/model_catalog/cli/export_working_groups_to_sidecars.py`), not a runtime migration. It runs once on each environment before the schema drop ships.

---

## 4. Deprecation window

Old REST surfaces should not just disappear. Sequence:

1. **PR A — design merged** (this commit): docs only; no code changes; new design is authoritative for new work.
2. **PR B — export tool**: ship the migration export script in §3. Operator runs it and reviews the report.
3. **PR C — endpoints respond 410 Gone**: replace the legacy `working-groups`/`view=groups` endpoint bodies with HTTP 410 + a JSON body pointing to the new endpoints. New endpoints from design §6.4 ship in the same PR.
4. **PR D — card rewrite**: explorer-card flips to the new single-view design; browser card and inbox card lose their working-group affordances.
5. **PR E — schema drop**: migration that drops `working_groups` and `working_items` tables. Remove now-dead code paths.
6. **PR F — manyfold removal**: separate clean-up sweep for any straggling `manyfold` references in working files code.

Each PR is independently reviewable and reversible up to PR E.

---

## 5. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Operator has groups with no folder_hint → loses curated titles/notes on schema drop | Export script (§3) flags these for manual triage before PR E lands. |
| Projects link to working groups by id and break | Projects layer is being reconciled in [../design/working-files.md §11](../design/working-files.md). PR D includes a Project re-link pass keyed on the folder path emitted in the export. |
| Archive links pointing at `local://working-group/{id}` go dead | PR C maps any inbound resolution of that URL scheme to a "deprecated" link card pointing the operator to the corresponding folder via the migration report. |
| Frontend cache: stale browser sessions still call `/api/working-groups/*` after PR C | HTTP 410 with explanatory body is more useful than silent 404; combined with the resource-version bump in PR D forces JS reload. |
| Bulk Import card users lose a workflow | Decide in PR D whether to retire the card or repurpose it as Bulk Intake. Either choice is acceptable; do not leave it half-wired. |

---

## 6. Definition of done

- `working_groups` and `working_items` tables do not exist after fresh migration replay.
- `grep -RIn "working_group" sidecars/ homeassistant/www/3d_printing/model_catalog/ tests/sidecars/model_catalog/` returns no live code matches (only archived design docs and CHANGELOG entries).
- `grep -RIn "manyfold" sidecars/ homeassistant/www/3d_printing/model_catalog/` returns no working-files-related matches.
- New endpoints from [../design/working-files.md §6.4](../design/working-files.md) are covered by tests.
- Explorer card matches the single-view UI in [../design/working-files.md §2](../design/working-files.md).
- Migration export report has been produced and acknowledged in the operator runbook.
