# Folder 3MF Catalog Design

> **Status**: Implemented vertical slices exist in repo tooling. This document is the current design and operator reference for the nondestructive folder-catalog workflow.

See also:

- `../../model_catalog/model-library-strategy.md`
- `../../model_catalog/integration/archive-to-library-linkage.md`

## Purpose

Define the workflow for cataloging a user-selected folder of historical `.3mf` and `.gcode.3mf` files, reconciling that catalog against Bambuddy archives, preserving operator decisions outside the source tree, and executing preview or import actions without mutating the selected folder.

This design sits between the older SD-card historical backfill docs and the popup-oriented source-3MF import docs.

Use this workflow when the source of truth is a Windows folder such as `C:\Users\rysock\OneDrive\3D Printing`, not an SD-card backup dump and not an already-selected archive popup.

## Current Scope

The current repo tooling covers five slices:

1. Nondestructive folder scan and manifest generation.
2. Separate mutable state storage keyed by `record_id`.
3. Reconciliation against Bambuddy archive inventory.
4. Local browser viewer with editable state and import-plan fields.
5. Queue execution for `inspect`, `dry-run`, and confirmed browser-triggered `run-backfill`.

Implemented tools:

- `tools/bambuddy/generate_folder_3mf_catalog.py`
- `tools/bambuddy/folder_3mf_catalog_state.py`
- `tools/bambuddy/reconcile_folder_3mf_catalog.py`
- `tools/bambuddy/folder_3mf_catalog_viewer.py`
- `tools/bambuddy/run_folder_3mf_catalog_import.py`

Focused validation currently covers the generator plus the state/reconcile/viewer/runner contract in:

- `tests/tools/test_generate_folder_3mf_catalog.py`
- `tests/tools/test_folder_3mf_catalog_workflow.py`

## Non-Negotiable Constraints

### Selected folder is read-only

The chosen source root must remain untouched.

- no writes inside the selected folder
- no staging or exports inside the selected folder
- no hidden sidecar metadata inside the selected folder
- no hydration or conversion step that mutates OneDrive-managed files

All mutable outputs live under an external working root such as `tmp/folder_3mf_catalog/<catalog-name>/`.

### Manifest and state are separate

The discovery manifest remains deterministic and rescan-driven.

Operator edits belong in the companion state file.

That state currently includes:

- disposition
- operator note
- manual tags
- selected archive id
- export workflow state
- import plan fields
- runner state

### Missing and cloud-only rows must persist

Rows do not disappear just because the source file moved, was removed, or is cloud-only.

Important statuses:

- `missing_on_rescan`
- `offline_onedrive`
- `blocked_missing`
- `blocked_offline`

## Working Model

### Layer 1: Discovery manifest

`generate_folder_3mf_catalog.py` scans the selected folder for `.3mf` and `.gcode.3mf` candidates, records support-file evidence, derives initial timestamp evidence from filesystem state, and emits a manifest with:

- path identity and hashes
- source classification
- archive-readiness signals
- availability state
- supporting-file evidence
- best inferred print time

The generator now performs an explicit Windows metadata probe before classifying OneDrive availability, including `GetFileAttributesW` and reparse-tag lookup when available. The record now carries `reparse_tag` and `availability_probe` in addition to the older file-attribute fields.

### Layer 2: Mutable state

`folder_3mf_catalog_state.py` stores operator choices outside the source tree. This keeps rescans safe while preserving workflow progress.

### Layer 3: Reconciliation

`reconcile_folder_3mf_catalog.py` compares candidates to Bambuddy archives using this order:

1. exact content hash
2. normalized filename token overlap
3. saved timestamp proximity

### Layer 4: Viewer

`folder_3mf_catalog_viewer.py` merges manifest and state and exposes:

- filters and detail view
- export workflow editing
- import plan editing
- queue actions from the browser

Current browser queue actions:

- `inspect`
- `dry-run`
- `run-backfill`

`run-backfill` is intentionally guarded. It requires:

- a configured state file
- `base_url`
- `printer_id`
- explicit confirmation phrase `RUN-BACKFILL`

The viewer also now lets the operator choose a custom synthetic manifest output path for `dry-run` and `run-backfill`. If blank, it falls back to the temp directory.

### Layer 5: Runner

`run_folder_3mf_catalog_import.py` now exposes `run_catalog_import(...)` for both CLI use and viewer-triggered execution.

Current runner behavior:

- `inspect` returns queue summary only
- `dry-run` emits a synthetic manifest preview and dry-run payload
- `run-backfill` creates new Bambuddy archives from ready sliced inputs and writes runner-state back to the catalog state
- `attach_source_only` uses `POST /api/v1/archives/{id}/source`
- provenance notes/tags are patched back onto Bambuddy archives after successful execution

The provenance note merge is now surgical for `[FOLDER_CATALOG_RECOVERY_V1]`: replacing that block leaves unrelated note blocks intact.

## Archive Execution Semantics

The current folder-catalog workflow supports two real execution branches and one preview-only branch.

### `create_archive_upload`

Use when the candidate is archive-ready and should become a canonical Bambuddy archive.

This still flows through the existing historical uploader/backfill contract rather than inventing a new upload path.

### `attach_source_only`

Use when the candidate should be attached as source provenance to an existing archive.

This is not canonical archive repair. It remains provenance-only.

### `dry-run`

Use to preview queue actions and synthetic manifest output without touching Bambuddy.

## Relationship To Other Import Docs

- `archive-historical-backfill-from-sd-card.md` remains the design for SD-card driven historical backfill.
- `source-3mf-import-design.md` remains the design for popup-scoped import into an existing archive.

The folder-catalog workflow is the bridge between them:

- broader than popup-scoped source import
- safer and more operator-driven than raw historical backfill from one fixed artifact source

## Current Gaps And Next Steps

Two next steps are intentionally deferred but now documented here so they do not live only in chat memory.

### 1. Viewer execution summary card

The viewer currently renders raw JSON results for queue actions. Add a compact summary card that shows:

- ready / blocked / manual counts
- synthetic manifest path used
- created archive count
- attachment count
- key errors or warnings

That should sit above the raw JSON block rather than replace it.

### 2. Persist viewer runner defaults

The browser panel currently requires re-entry of:

- synthetic manifest path
- `base_url`
- `printer_id`
- preferred `backfill_action`

Persist those as viewer defaults in catalog state so the panel remembers connection and output preferences across sessions.

Those defaults should remain operational preferences only. They should not be merged into the deterministic discovery manifest.

## Recommended Operator Flow

1. Generate the folder catalog manifest.
2. Reconcile it against Bambuddy archive inventory.
3. Open the viewer with the companion state file.
4. Set disposition, archive selection, export workflow, and import plan fields.
5. Run `inspect` or `dry-run` first from the browser.
6. Only run browser `run-backfill` after reviewing the preview and entering the explicit confirmation phrase.

## Quick Relaunch (OneDrive 3D Printing)

Use this command to relaunch the local viewer for the OneDrive catalog workspace:

```powershell
& "c:\dev\hass-bambulab-config\.venv\Scripts\python.exe" "c:\dev\hass-bambulab-config\tools\bambuddy\folder_3mf_catalog_viewer.py" --manifest "c:\dev\hass-bambulab-config\tmp\folder_3mf_catalog\onedrive-3d-printing\manifests\catalog_manifest.json" --state "c:\dev\hass-bambulab-config\tmp\folder_3mf_catalog\onedrive-3d-printing\state\catalog_state.json"
```

Expected output when successful:

`Serving folder 3MF catalog viewer at http://127.0.0.1:8766/`

## References

- `archive-historical-backfill-from-sd-card.md`
- `source-3mf-import-design.md`
- `source-3mf-storage-strategy.md`
- `../../../repo/bambuddy-archive-recovery-approach.md`
- `../reference/manual-reconciliation-launchpad.md`