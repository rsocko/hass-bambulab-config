# Historical Print Backfill Via Model Catalog

> **Status**: Later-phase cross-feature design reference.
> **Last updated**: 2026-05-09

## Purpose

Define how the model catalog enables direct, operator-driven, server-side recovery and backfill of older or incomplete print-history records.

This workflow replaces legacy CLI/manifest-based orchestration with a modern, UI-driven wizard. Operators can push model-linked print history records with custom timestamps and status, without relying on forensics scripts or client-side tools.

## Why This Belongs Here

Some historical recovery work starts from the archive side.

Some starts from the model side:

- the operator knows the model or source artifact already
- print history is missing or incomplete
- prior local analysis has already identified likely source files, sliced artifacts, timestamps, or provenance hints

Issue `#1043` is about making the model catalog a practical launch point for that second category.

## Existing Building Blocks

The repo already has meaningful recovery machinery:

- `tools/bambuddy/gcode_forensics_viewer.py`
- `tools/bambuddy/run_forensics_import_queue.py`
- `tools/bambuddy/folder_3mf_catalog_viewer.py`
- `tools/bambuddy/run_folder_3mf_catalog_import.py`
- print-history import docs under `docs/features/print_history/imports/`

Important existing behaviors:

- the forensics runner can create a canonical Bambuddy archive from an archive-ready sliced artifact
- the forensics runner can also attach a source `.3mf` as provenance-only to an existing archive
- the folder 3MF catalog workflow already supports operator-reviewed inspect, dry-run, and confirmed backfill execution
- the source-3MF import design already distinguishes canonical archive creation from provenance-only source attachment

This means the design does not need a brand-new archive recovery engine. It needs a catalog-facing, operator-driven workflow that orchestrates the existing engines server-side, with all review and commit steps surfaced in the UI.

## Recommended User Flow

The first implementation remains catalog-first.

That means the initial reviewed flow launches from a curated Model Catalog record while preserving a later extension point for Working-group entry.

### Entry Point

Start from a model-catalog detail surface for a curated model or relevant Working group.

The UI should show a `Backfill Older Print History` or similarly named recovery entrypoint only when the operator is intentionally working on historical recovery.

### Review Step

The recovery surface should help the operator answer:

- is there already a likely archive for this model?
- is there prior manifest or forensics analysis tied to this source or a nearby artifact?
- is the available file only source-level provenance, or is it archive-ready?
## Operator-Driven Add Historical Print Wizard: User Flow

The new flow launches from the Model Catalog popup for a curated model (or relevant Working Group). The operator initiates the "Recover Print History" (or "Add Historical Print") action, which opens a wizard:

1. **Scan** — The backend searches for archive/print candidates using filename, hash, and metadata.
2. **Review** — The operator reviews candidates (with confidence scores, source paths, slicer-derived metadata), selects one, or opts to create a new historical record.
3. **Timestamps** — The operator enters or confirms print start/completion timestamps (with timezone/note), with prefill from evidence when available.
4. **Commit** — The backend creates a print history record (flagged as backfill) and links it to the model. All actions are explicit and require operator confirmation.

**Key Principles:**
- No dependency on CLI/manifest tools or client scripting.
- All review and commit steps are surfaced in the UI.
- Backfilled records are clearly labeled and excluded from frequents calculations by default.
- The workflow is fully documented and mockups are updated to match.

**Persistence:**
The reviewed backfill flow persists state in a dedicated Model Catalog table (`model_catalog_print_history_jobs`), capturing source selection, chosen outcome, timestamps, validation warnings, operator notes, and final archive linkage.

**Success Criteria:**
- Operators can add historical print records faster and more reliably than with disconnected forensics tools.
- Canonical archive creation and provenance-only source attachment remain distinct.
- Historical timestamps are always reviewed and set explicitly before commit.
- The final outcome flows back into the normal archive-linkage and model-catalog experience, not a detached workflow.