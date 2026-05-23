# Model Catalog — Advanced Actions Card Design

> **Status:** Hi-fidelity design proposal.
> **Tracking issue:** [#1227 — "Advanced Actions" card for models](https://github.com/rsocko/hass-bambulab-config/issues/1227)
> **Scope:** A new Lovelace custom card — `custom:model-catalog-advanced-actions-card` — that mirrors the Print History [print-history-archive-actions-card.js](../../../../homeassistant/www/3d_printing/print_history/print-history-archive-actions-card.js) UX and architecture, applied to **catalog models** (not archives). Includes a proper **DELETE** flow (two-stage confirmation) which the Catalog does not have today.
> **Companion mockup:** [mockups/catalog-advanced-actions.html](mockups/catalog-advanced-actions.html).
> **Related design docs:** [catalog-popup.md](catalog-popup.md), [working-files-card.md](working-files-card.md), [working-files-workflow-redesign-issue-1169.md](working-files-workflow-redesign-issue-1169.md).

---

## 1. Why a separate "Advanced Actions" card

The existing model-detail popup (see [catalog-popup.md](catalog-popup.md)) is a **read-and-act-quickly** surface — it shows photos, key fields, related archives, and a small action row. Issue #1227 calls out the gap: there is no single place to perform the **less-frequent, higher-stakes** model operations:

- Delete a model (currently impossible from any UI).
- Bulk-edit metadata (title, description, tags, source URL, queue state, publish destinations).
- Manage source files (working-files / 3MF associations) without round-tripping through Working Files.
- Browse linked archive prints with confidence drill-down (today this is print-history's territory; the model-side mirror is missing).
- Re-run intake / re-classify / re-detect candidates.
- Push to / refresh from Manyfold.
- View raw metadata JSON for diagnostics.

These operations exist as scattered services and rest_commands today; nothing presents them as a coherent surface. The Print History "Advanced Actions" popup solved exactly this problem for archives — applying the same pattern to models is both a UX win and a way to retire ad-hoc affordances buried in the existing popup.

Publish workflow boundary:

- `Publish to Catalog` (operator Promote flow) is primarily launched from Working Groups surfaces.
- Catalog Advanced Actions remains the follow-up surface for post-publish maintenance, reconciliation, and metadata repair.

### Inheritance contract

The Model Catalog card **inherits the Print History card's architecture wholesale** (5-tab top nav, sub-mode drill-downs, busy/status footer, two-stage delete confirm, search modal, JSON viewer). Differences are only in the *contents* of each tab. This is deliberate so:

1. Operators don't relearn navigation between archives and models.
2. Code reuse is high — most rendering primitives port directly.
3. The card can be a sibling file (`model-catalog-advanced-actions-card.js`) rather than a fork.

---

## 2. Tab map (Catalog vs. Print History)

The PH card has 5 tabs: `media | model | analytics | repair | danger`. The Catalog card maps to the same 5 slots with reframed semantics:

| Slot | PH Tab | Catalog Tab | Catalog Icon | Purpose |
| --- | --- | --- | --- | --- |
| 1 | Media | **Media** | `mdi:folder-multiple-image` | Photos, primary thumbnail, source `.3mf`/STL list, downloads, 3D viewer, Manyfold sync. |
| 2 | Model | **Files & Sources** | `mdi:source-branch` | Working-group memberships, working-file links, source URLs (MakerWorld / Printables / Manyfold), upload-replace primary. |
| 3 | Analytics | **Prints** | `mdi:printer-3d` | Linked archive prints (this model has been printed N times), success-rate insight, "find more candidates", duplicate-model detection. |
| 4 | Repair | **Metadata** | `mdi:tag-text-outline` | Edit title, description, tags, queue state, publish destinations; view raw JSON; re-run intake/classify; reorder photos. |
| 5 | Danger | **Danger** | `mdi:alert-octagon-outline` | Two-stage delete; archive (soft-delete) toggle; merge into another catalog entry. |

The order matches PH so the tab strip "feels" identical.

### 2.1 Why "Files & Sources" replaces "Model"

In the PH card, the "Model" tab is for **linking the archive to a catalog model**. From the catalog's perspective, the inverse — "what files / sources / projects does this model own?" — is the natural mirror. Keeping the slot in position 2 lets operators jump from the model-detail popup's source/file row directly into the same tab without thinking about which surface they're on.

---

## 3. Common vs. unique actions matrix

### 3.1 Common (carry forward as-is)

These ports straight from PH. Only labels and target IDs change.

| Action / Pattern | PH counterpart | Catalog target |
| --- | --- | --- |
| 5-tab `_mainTabConfig` + `_setMainTab` | identical | identical |
| Sub-mode drill-down with breadcrumb back nav | identical | identical |
| Busy/status footer (`_busy`, `_busyContext`, tone) | identical | identical |
| Two-stage delete confirmation (`confirm-delete-1` → `confirm-delete-2`) | identical | identical |
| JSON metadata viewer with copy + line numbers | identical | re-target to model JSON |
| Search modal (form + paginated grid) | model library search | catalog search (find duplicate / merge target) |
| Confidence-grouped candidate lists (high / medium / low) | related archives | linked archives + duplicate models |
| Async tab-load on first view + cache | identical | identical |
| Tone classes (`warning` / `danger`) | identical | identical |

### 3.2 Unique to Catalog (new actions)

| Action ID | Tab | Label | Icon | Tone | Backing service / endpoint | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `view-3d-viewer` | Media | Open in 3D viewer | `mdi:cube-scan` | — | reuses `custom:model-detail-3d-viewer-tab` | Same reuse pattern as Working Files popup §4.4.1. |
| `download-primary-3mf` | Media | Download primary 3MF | `mdi:file-download-outline` | — | sidecar download URL | Disabled if no primary 3MF. |
| `replace-primary-thumbnail` | Media | Replace primary thumbnail | `mdi:image-edit-outline` | — | `model_catalog_set_photo_preview` | Reuses 3MF preview-extraction pattern. |
| `reorder-photos` | Media | Reorder photos | `mdi:image-multiple-outline` | — | `model_catalog_upload_photo` ordering | Drag-handle list (sub-mode). |
| `manyfold-push` | Media | Push to Manyfold | `mdi:cloud-upload-outline` | — | (existing Manyfold upload path) | See [model_catalog/intake](../) memos for upload contract. |
| `manyfold-refresh` | Media | Refresh from Manyfold | `mdi:cloud-sync-outline` | — | (existing Manyfold detail fetch) | — |
| `add-source-url` | Files & Sources | Add source URL | `mdi:link-plus` | — | `model_catalog_update_model` (sources field) | Inline form. |
| `link-working-group` | Files & Sources | Link working group | `mdi:folder-multiple-plus` | — | `model_catalog_create_working_group_link` | Group picker popover. |
| `unlink-working-group` | Files & Sources | Remove link | — | `warning` | `model_catalog_delete_working_group_link` | Per-row. |
| `spawn-working-group` | Files & Sources | Create working group from this model | `mdi:folder-plus-outline` | — | `model_catalog_create_working_group` | Pre-fills title from model. |
| `attach-working-file` | Files & Sources | Attach file to group | `mdi:file-link` | — | `model_catalog_attach_file_to_group` | Single-file picker. |
| `find-related-models` | Prints | Find related models | `mdi:relation-many` | — | `model_catalog_get_related_models` | Mirror of PH related; keyed by hash / tag overlap. |
| `find-linked-archives` | Prints | Linked archive prints | `mdi:printer-3d` | — | `model_catalog_get_archive_links` (reverse lookup) | Lists archives that reference this model. |
| `find-duplicate-models` | Prints | Find duplicate models | `mdi:content-duplicate` | — | (proposed) `/api/models/{id}/duplicates` | Backend addition; see §5. |
| `compare-with-model` | Prints | Compare with another model | `mdi:compare-horizontal` | — | (reuses compare scaffold) | Mirror of PH compare. |
| `edit-tags` | Metadata | Edit tags | `mdi:tag-multiple-outline` | — | `model_catalog_update_model` | Tag chip editor sub-mode. |
| `edit-fields` | Metadata | Edit basic fields | `mdi:pencil` | — | `model_catalog_update_model` | Title / description / queue / publish destinations. |
| `view-metadata-json` | Metadata | View Model Metadata | `mdi:code-json` | — | `model_catalog_get_archive_model` (or model GET) | JSON viewer. |
| `reclassify` | Metadata | Re-run intake / classify | `mdi:refresh-auto` | `warning` | `model_catalog_validate_intake_item` (or sidecar reclassify) | Soft action; reports diff. |
| `regenerate-thumbnails` | Metadata | Regenerate thumbnails | `mdi:image-sync-outline` | `warning` | (proposed) sidecar endpoint | Backend addition. |
| `archive-model` | Danger | Archive model (soft) | `mdi:archive-outline` | `warning` | (proposed) `model_catalog_set_archived` | Reversible; sets `archived_at`. |
| `unarchive-model` | Danger | Restore archived model | `mdi:archive-arrow-up-outline` | — | (same endpoint, inverse) | Visible only if archived. |
| `merge-into` | Danger | Merge into another model | `mdi:source-merge` | `warning` | (proposed) `/api/models/{id}/merge` | Picks a target via search modal; redirects on success. |
| `delete-model` | Danger | Delete model | `mdi:delete-outline` | `danger` | (proposed) `model_catalog_delete_model` | Two-stage confirm; see §4. |

### 3.3 PH actions explicitly **not** ported

| PH action | Why excluded |
| --- | --- |
| `download-model` (gcode) | Catalog doesn't own gcode; archives do. |
| `view-timelapse` / `scan-timelapse` / `upload-timelapse` | Timelapse is per-print, lives on archives. |
| `repair-archive` / `repair-from-replacement` | Archive-specific repair flow; not meaningful for catalog models. The catalog equivalent is "Re-run intake / classify" in the Metadata tab. |
| `model-search-library` (linking archive to model) | The inverse — "find candidate archives for this model" — is offered in the Prints tab as `find-linked-archives`. |

---

## 4. Delete flow (the headline ask)

Issue #1227 explicitly calls for a DELETE option. The Catalog currently has **no model deletion path** anywhere in the UI; the design borrows the PH two-stage pattern verbatim.

### 4.1 Stages

1. **`main` → click `delete-model`** — switches mode to `confirm-delete-1`, renders a destructive callout listing what *will* and *will not* be deleted (see §4.2).
2. **`confirm-delete-1` → click `continue-delete`** — switches to `confirm-delete-2`, requires the operator to type the model title to enable the final button (PH does not currently require typing; see open question 8.1).
3. **`confirm-delete-2` → click `delete-model-final`** — calls the backend delete endpoint, on success closes the popup and emits a card-level `model-deleted` event so the browser card refreshes.

`Cancel` on either confirmation returns to mode `main` (matches PH).

### 4.2 What gets deleted vs. preserved

The confirm-1 screen must spell this out so the operator knows the blast radius. Recommended copy:

| Asset | Action |
| --- | --- |
| Model row in `models` table | DELETED |
| Photo blobs / metadata | DELETED |
| Working-group **links** to this model | DELETED (links only — groups remain) |
| Source archive **links** | DELETED (links only — archives remain) |
| Linked working files on disk | **PRESERVED** (filesystem untouched) |
| Linked archives in print history | **PRESERVED** |
| Manyfold upstream record | **PRESERVED** (operator can delete in Manyfold separately) |

### 4.3 Backend endpoint (proposed)

`DELETE /api/models/{model_id}` in [sidecars/model_catalog/app/routers/](../../../../sidecars/model_catalog/app/routers/) — does not exist today. Recommended contract:

- Returns `{ "deleted": true, "model_id": "...", "links_removed": { "working_groups": N, "archives": N }, "photos_removed": N }`.
- Cascades deletes for `model_photos`, `model_archive_links`, `model_working_group_links` rows.
- Does **not** touch `working_files`, `working_groups`, `print_history_archives`.
- Wraps in a single transaction; on failure, returns 4xx/5xx and the card surfaces the error in the status footer.

A `model_catalog_delete_model` rest_command wraps the endpoint for HA service-call use.

---

## 5. Backend touch points

Most actions reuse existing rest_commands enumerated under [homeassistant/packages/3d_printing/model_catalog/rest_commands/](../../../../homeassistant/packages/3d_printing/model_catalog/rest_commands/). The following are **new** or **need extension**:

| Touch point | Layer | Status | Notes |
| --- | --- | --- | --- |
| `DELETE /api/models/{model_id}` | sidecar router | **NEW** | See §4.3. |
| `model_catalog_delete_model` rest_command | HA package | **NEW** | Wraps the above. |
| `POST /api/models/{model_id}/archive` (soft) | sidecar router | **NEW** | Sets `archived_at`; reversible. |
| `model_catalog_set_archived` rest_command | HA package | **NEW** | — |
| `POST /api/models/{model_id}/merge` | sidecar router | **NEW** | Body: `{ target_model_id }`. Migrates links + photos + sources; deletes source row. |
| `model_catalog_merge_models` rest_command | HA package | **NEW** | — |
| `POST /api/models/{model_id}/regenerate-thumbnails` | sidecar router | **NEW (optional)** | Async job; status surfaces via existing job pattern. |
| `GET /api/models/{model_id}/duplicates` | sidecar router | **NEW (optional)** | Hash + name + tag heuristic; mirrors PH duplicates contract. |
| `model_catalog_get_archive_links` (reverse-lookup mode) | existing | **EXTEND** | Add `?by_model_id=...` query param so we don't need a new endpoint for "linked archive prints". |
| `model_catalog_update_model` | existing | reuse | Covers tags, title, description, queue state, publish destinations, sources. |

### Layering guardrail

Per [.github/copilot-instructions.md](../../../../.github/copilot-instructions.md), all additions live in the sidecar (Layer 2-equivalent for the catalog domain) and the card (Layer 3). No `sensor.print_history_archives` (Layer 1) changes are required or proposed.

---

## 6. Sub-modes (drill-downs)

Mirrors the PH `_mode` state machine. Only catalog-specific modes are listed; all others (`metadata`, `confirm-delete-1`, `confirm-delete-2`, etc.) keep the PH semantics.

| Mode | Reached from | Purpose | Back |
| --- | --- | --- | --- |
| `main` | (default) | Renders 5 tabs | — |
| `metadata` | Metadata → View Model Metadata | JSON viewer with copy | `back-main` |
| `edit-fields` | Metadata → Edit basic fields | Form: title, description, queue, publish destinations | `back-main` |
| `edit-tags` | Metadata → Edit tags | Tag chip editor + autocomplete | `back-main` |
| `reclassify-preview` | Metadata → Re-run intake / classify | Shows diff before applying | `back-main` |
| `linked-archives` | Prints → Linked archive prints | Confidence-grouped archive list (reuses PH related layout) | `back-main` |
| `duplicate-models` | Prints → Find duplicate models | Same layout as PH duplicates | `back-main` |
| `compare-models` | Prints → Compare with another model | Field-by-field comparison | `back-prints` / `back-main` |
| `merge-pick-target` | Danger → Merge into another model | Search modal → pick target | `back-main` |
| `confirm-delete-1` | Danger → Delete model | First confirmation | `cancel` |
| `confirm-delete-2` | confirm-delete-1 | Final confirmation, type-to-confirm | `cancel` |

---

## 7. Card config inputs (`setConfig`)

Mirrors PH where applicable; renames archive-keyed inputs to model-keyed.

| Property | Default | Purpose |
| --- | --- | --- |
| `model_json` | `"{}"` | Stringified or live model object (parity with PH `archive_json`). |
| `model_id_entity` | `""` | Optional fallback — entity holding the active model id. |
| `model_catalog_sidecar_base_url_entity` | `"input_text.model_catalog_sidecar_base_url"` | Already exists. |
| `api_base_entity` | `"input_text.bambuddy_api_base_url"` | For services that route through Bambuddy. |
| `initial_mode` | `""` | Pre-select a mode (e.g. `"metadata"` from a deep link). |
| `initial_tab` | `"media"` | Pre-select a tab. |
| `compare_model_ids_json` | `"[]"` | Pre-selected models for compare. |
| `entry_id` | `""` | Catalog config entry id. |

---

## 8. Open questions

1. **Type-to-confirm on final delete?** PH does not require typing; for the catalog the destructive surface is broader (links + photos cascading). Recommend requiring the operator to type the model title in `confirm-delete-2`. Defer if scope creeps.
2. **Soft archive vs. hard delete vs. both?** Both. Soft archive (`archived_at`) is the everyday "hide it" affordance; hard delete is the irreversible cleanup. Card shows soft archive in the Danger tab as a less-destructive alternative *above* the delete button.
3. **Merge UX — auto-pick or manual?** Recommend manual for v1 (pick target via the existing catalog search modal). A future "find duplicates → merge selected" bulk path can layer on top of the duplicate-models sub-mode.
4. **Where does the entry button live?** On the model-detail popup ([catalog-popup.md](catalog-popup.md)), as a `mdi:dots-horizontal` overflow icon in the top-right action row, mirroring the PH browser card pattern. Optionally also on each catalog browser card (compact / list / media) as the `⋯` overflow — same pattern proposed in [working-files-card.md §3.7](working-files-card.md).
5. **Bulk version?** Issue #1227 doesn't explicitly call for it, but a `compare_model_ids_json` config input (parity with PH) leaves the door open for a future bulk-action surface invoked from list-view selection. Out of scope for v1.
6. **Manyfold push when no Manyfold integration is configured** — the action should be conditionally hidden (parity with how PH `view-timelapse` is hidden when no timelapse exists) rather than disabled-with-tooltip.
7. **Tags vs. queue state vs. publish destinations** — three logically distinct fields; the design doc keeps them in `edit-fields` (queue, publish destinations) and `edit-tags` (tags) sub-modes for visual focus. Reconsider if operator feedback says they're all edited together in practice.
8. **Photo reorder UX** — drag-handle list inside a sub-mode is the PH-consistent answer; lightweight implementation could defer to the existing photo upload affordance (re-upload re-orders) for v1.

---

## 9. Acceptance for design review

Approval-ready when reviewers confirm:

- 5-tab map in §2 is the right reframe of PH semantics for catalog models.
- The action matrix in §3 covers the operator's everyday and high-stakes flows; nothing critical is missing.
- The two-stage delete in §4 is acceptable — the cascade boundary in §4.2 matches expectations (links cascade, files / archives / Manyfold do not).
- The new backend endpoints in §5 are scoped acceptably; any can be deferred to a follow-up phase as long as the v1 card has DELETE.
- The card lives at `homeassistant/www/3d_printing/model_catalog/model-catalog-advanced-actions-card.js` and follows the same `_resources.yaml` versioning contract as other catalog JS resources, per [.github/copilot-instructions.md](../../../../.github/copilot-instructions.md).
