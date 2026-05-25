# Intake Wizard — Sidecar Metadata Enrichment

Status: **Phases 1 + 2 shipped (backend discovery + curated README attach)** — Phase 3 (frontend wizard panel) not yet implemented

Phase 1 changes:
- `sidecars/model_catalog/app/routers/intake_verification.py` — added `_discover_source_metadata()` and call site in `_summarize_planned_group()`.
- `tests/sidecars/model_catalog/test_intake_plan_sidecar_metadata.py` — 6 unit tests (high/medium/low confidence, no-sidecar, malformed `.modelmeta.json`, README size routing).
- Constants: `_README_INLINE_THRESHOLD_CHARS = 1024`, `_README_INCLUDE_MAX_CHARS = 16 * 1024`.
- Shipped contract (per planned model on `/api/intake/plan` response):
  ```jsonc
  "detected_metadata": {
    "confidence": "high|medium|low",
    "sources": [{"folder", "folder_path", "has_modelmeta", "has_readme", "readme_bytes"}],
    "merged": {
      "display_title?", "tags?", "origin_url?", "primary_file?",
      "readme_text?", "readme_truncated?", "readme_route?"  // "inline" | "attached"
    },
    "thumbnail_hint?": {"filename", "source_folder", "in_selection"},
    "parse_errors?": [{"folder", "sidecar", "error"}]
  }
  ```
- Field is **omitted entirely** when no sidecars are discovered (zero UI impact until Phase 3 wiring lands).

Phase 2 changes:
- `sidecars/model_catalog/app/routers/intake.py` — added `_collect_source_readmes()` helper plus opt-in attach block inside `_publish_group_to_local_destination` keyed on `destination_plan["attach_source_readme"]`. When the flag is true for a curated destination, the publisher walks `source_entries` (folders → that folder; files → parent folder), pulls each `README.md` once (dedup by hash against already-imported assets), copies it into the curated assets root, and registers a new `documentation` asset.
- New per-group response key `attached_readmes: [{source_folder, source_path, asset_id, filename}]` is added to publish results when the flag is set (omitted/empty otherwise).
- `tests/sidecars/model_catalog/test_intake_publish_attach_source_readme.py` — 4 tests covering file-typed selection happy path, default-off behavior, missing README, and dedupe when the README is already in `group_files`.
- No schema or API surface changes beyond the new opt-in flag; frontend wiring (Phase 3) will toggle it from the Organize step's "Detected metadata" panel.

Owner: Model Catalog
Related design docs:
- [intake-inbox.md](../design/intake-inbox.md) — canonical wizard baseline
- [intake-source-selection.md](../design/intake-source-selection.md) — Source step + exclusion propagation
- [intake-wizard-mockups.md](../design/intake-wizard-mockups.md) — Step 1 mockups
- [working-files.md](../design/working-files.md) — Working Files store + `.modelmeta.json` sidecar contract
- [working-files-launch.md](../design/working-files-launch.md) — "Run Intake Wizard from this folder" launch path
- [intake-grouping.md](../design/intake-grouping.md) — Organize step

## Problem

When the intake wizard's source includes a folder that already has a `.modelmeta.json` and/or `README.md` (most commonly a Working Files folder, but also possible in Server Inbox / Browser Upload), that pre-existing metadata is currently ignored. The user must re-type title/tags/notes/origin_url even when the answers already live next to the files.

We want to surface that metadata and let the user opt in to carrying it forward into the destination Catalog item — without duplicating data, without adding wizard steps, and without overwriting anything the user has already edited.

## Non-goals

- No schema changes to `.modelmeta.json`.
- No new wizard step.
- No automatic write-back to the source sidecar.
- No dry-run / server preview round trip (the data is already in the plan-preview response).
- v1 does **not** import the `thumbnail` referenced by a sidecar as a curated thumbnail asset. Tracked as a follow-up.

## Where it fits

Inside the existing **Organize** step (step 2 of the 5-step canonical flow: Source → Organize → Destination → Validate → Commit).

The Organize step already collects per-group `title`, `tags`, `notes`, `origin_url`. We attach a collapsible **"Detected metadata from source"** panel to each group card that has sidecar data in scope, with per-field opt-in.

Rationale:
- Target fields already exist there — no new wizard surface needed.
- Sidecar discovery happens server-side during plan preview, so by the time the user reaches Organize the data is already attached to each group.
- A 6th step for "review some prefilled fields" is heavier than the value it adds.

## Sidecar discovery

For each planned group:

1. Compute the nearest common ancestor folder of the selected source paths.
   - For Working Files / Server Inbox: ancestor on the real filesystem under the source root.
   - For Browser Upload: ancestor within the staged upload tree (real disk paths are not chased).
2. Walk upward from that ancestor — but not above the relevant root — looking for `.modelmeta.json` and `README.md`.
3. Classify the result by **confidence**:

| Selection pattern | Detected scope | Confidence |
|---|---|---|
| Entire folder selected (contains the sidecar) | That folder's sidecar | **High** |
| Subfolder or subset of one parent folder selected | Parent folder's sidecar | **Medium** |
| Files spanning multiple folders with different sidecars | All discovered sidecars | **Low** |
| No sidecar in scope | none | hide the panel |

Reuses [`_read_folder_sidecar()`](../../../../sidecars/model_catalog/app/routers/working.py) — no new read helper required for the per-folder fetch. A new `_discover_source_metadata()` helper performs the ancestor walk + classification + merge.

## Merging multiple sidecars (Low confidence)

When a single planned group spans multiple sidecars:

- **Tags**: union of all sidecars' tags (deduped, order preserved).
- **Scalar fields** (`display_title`, `origin_url`, `primary_file`): first non-empty wins, sources sorted by folder name for determinism.
- **README**: concatenated with `\n\n---\n\n` separators, each section prefixed with the source folder name as a small header.
- All fields shown **unchecked** in the UI regardless of high-confidence defaults.

## Field-by-field rules

| Sidecar field | Group field | Default check state | Apply rule |
|---|---|---|---|
| `display_title` | title | Checked at High confidence | Apply only if user has not manually edited the title; otherwise show "User-edited" pill, leave alone unless user re-checks. |
| `tags` | tags | Checked at High confidence | **Union by default** with a `Replace` toggle. |
| `origin_url` | origin_url | Checked at High confidence | Auto only if the field is empty; if user typed one, leave alone unless re-checked. |
| `README.md` body | notes / asset | **Always opt-in** (unchecked) | Routed by size — see below. |
| `primary_file` | primary_file | Checked at High confidence if the referenced file is in the selection | Skipped if file is not selected. |
| `thumbnail` (filename) | curated thumbnail asset | **Deferred to follow-up** | Detection flagged in panel only. |

## README handling

Size threshold: **> 1024 chars** routes from inline to attached asset.

### Working destination

README **already lives on disk** in that folder. The wizard does not import or attach it — that would duplicate.

UI: shows an informational chip "README.md is preserved in the source folder." No checkbox.

### Curated destination

| README size | Route | Notes behavior |
|---|---|---|
| ≤ 1024 chars | Inline into `notes` field | No asset attached |
| > 1024 chars | Attach as catalog asset (`asset_kind` matches existing doc/other convention — implementer to detect) | `notes` field auto-populated with `"See attached README.md"` **only if the user has not entered their own notes** |

UI:
- One unified "README.md" row in the panel.
- Chip indicates auto-detected mode: `Inline in notes` or `Attach as file (12.4 KB)`.
- Single primary checkbox to opt in/out.
- Secondary "Switch mode" link to flip inline ↔ attached.

## Backend contract

Extend the plan-preview endpoint response so each group includes (when discovery yields anything):

```json
{
  "detected_metadata": {
    "confidence": "high",
    "sources": [
      {
        "folder": "gridfinity-bin",
        "has_modelmeta": true,
        "has_readme": true,
        "readme_bytes": 482
      }
    ],
    "merged": {
      "display_title": "Gridfinity Bin 2x1",
      "tags": ["gridfinity", "storage"],
      "origin_url": "https://makerworld.com/...",
      "primary_file": "bin-2x1.3mf",
      "readme_text": "…",
      "readme_truncated": false,
      "readme_route": "inline"
    },
    "thumbnail_hint": {
      "filename": "thumb.png",
      "in_selection": false
    }
  }
}
```

- README text included inline up to ~16 KB; flag `readme_truncated: true` above that. The full file is still attached on apply via re-read at publish time.
- `readme_route` is the server's suggestion (`inline` ≤ 1024 chars else `attached`). The UI can flip it.
- `detected_metadata` is omitted entirely when no sidecar is discovered.

No publish-path API changes are required for v1: the existing destination plan already accepts `title`, `notes`, `tags`, `origin_url`. The frontend updates the group plan in place when the user clicks **Apply checked**.

Catalog-destination README-as-asset implementation will piggy-back on the existing asset-attachment path used for staged files; the README is just an additional file appended to the publish payload with its detected `asset_kind`.

## Frontend contract

In [model-catalog-intake-wizard-overrides.js](../../../../homeassistant/www/3d_printing/model_catalog/model-catalog-intake-wizard-overrides.js), Organize step group card:

- Render the panel only when `group.detected_metadata` is present.
- Render confidence pill (`High` / `Medium` / `Low`) with hover hint.
- Per-field rows with checkbox + value preview + (where applicable) mode toggle.
- For Working destination, hide the README row entirely and show the informational chip.
- "Apply checked" button updates the wizard's group plan in place and disables itself until user changes a selection again.
- Tags row includes a `Union | Replace` segmented control (default `Union`).
- No persistence of "ignored sidecar" state — re-opening the wizard recomputes defaults.

Resource cache-bust required: bump the `_resources.yaml` entry for the overrides file when shipping the JS change.

## Edge cases

- **Empty sidecar** (`.modelmeta.json` exists but has no useful fields) → omit `detected_metadata`.
- **Malformed `.modelmeta.json`** → skip silently for that source; log server-side; do not block plan preview.
- **README is binary** (rare) → skip with a flag; do not attempt to inline.
- **User edits a field after applying** → user wins; field is not re-applied unless they re-check it.
- **Working → Working append mode**: detected metadata is still shown but defaults are unchecked, since the target folder already has its own sidecar that publish-time merge handles. Mostly a no-op for the user; consider hiding entirely if noise complaints arise.
- **Multi-group plan, all from same parent sidecar** → each group gets the same `detected_metadata` independently; user applies per group. (Acceptable for v1; bulk-apply could be a follow-up.)

## Files to touch

| File | Change |
|---|---|
| [sidecars/model_catalog/app/routers/intake.py](../../../../sidecars/model_catalog/app/routers/intake.py) | New `_discover_source_metadata()` helper; wire into plan-preview response; README-as-asset path for curated publish |
| [sidecars/model_catalog/app/routers/working.py](../../../../sidecars/model_catalog/app/routers/working.py) | Reuse `_read_folder_sidecar()`; no public-API changes expected |
| [homeassistant/www/3d_printing/model_catalog/model-catalog-intake-wizard-overrides.js](../../../../homeassistant/www/3d_printing/model_catalog/model-catalog-intake-wizard-overrides.js) | Organize-step panel render + apply handler |
| [homeassistant/packages/3d_printing/common/dashboards/_resources.yaml](../../../../homeassistant/packages/3d_printing/common/dashboards/_resources.yaml) | Cache-bust the JS resource version |
| `tests/sidecars/model_catalog/` | Discovery unit tests + plan-preview integration tests covering High/Medium/Low confidence and README routing |

## Open follow-ups (not v1)

- Import `thumbnail` referenced by sidecar as curated thumbnail asset.
- Bulk "Apply detected metadata to all groups" button when multiple groups share a single sidecar.
- Optional "Re-sync from source" affordance on the catalog item after publish, to re-pull sidecar values later.

## Decision log

| Decision | Choice |
|---|---|
| New wizard step? | No — inline panel in Organize |
| Scope of sources | All sources (Working Files, Server Inbox, Browser Upload) |
| Destinations covered | Both Curated and Working |
| Default check state at High confidence | Title/tags/origin auto-checked; README always opt-in |
| README inline ↔ asset threshold | 1024 chars |
| Notes when README attached | `"See attached README.md"` only if user has not entered own notes |
| Asset kind for attached README | Match existing catalog convention (implementer to detect; likely `other`) |
| Multi-sidecar merge | Union tags; first-non-empty wins for scalars; README concatenated with `---` separators |
| Tags merge default | Union, with `Replace` toggle |
| Thumbnail import | Deferred to follow-up |
