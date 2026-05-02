# Working File Inventory And Normalization Spec

> Status: Wave 1 specification
> Issues: #1074, #1169
> Last updated: 2026-05-01
> Scope: Canonical rules for working-file discovery, normalization, duplicate identity, and group-first Working Files behavior in Phase 5 workflows.

## Purpose

Define a single, implementation-ready contract for:

- what files are in scope for intake and indexing
- how source paths and names are normalized
- how duplicate identity is computed
- how conflicts are surfaced to operators before commit
- how grouped and ungrouped Working Files views should behave

This document is authoritative for Phase 5 backend and HA workflow implementations.

## Phase Boundary (Issue #1169)

Current approved focus:

- start from indexing and organizing files in `/assets/Model Working Files`
- provide group-first and ungrouped Working Files operations

Deferred to a later phase:

- full Intake/Inbox to Working Files handoff pipeline

## Inventory Scope

### In Scope (Phase 5)

- Model geometry and project files:
  - `.3mf`
  - `.stl`
  - `.step`, `.stp`
  - `.obj`
- Optional packed intake artifacts:
  - `.zip` (intake accepted, contents handled by explicit extraction workflow)

### Out Of Scope (Phase 5)

- direct parsing/import of slicer profile bundles as first-class records
- recursive archive introspection for non-zip formats
- global media library dedupe across all model assets

## Discovery Roots

Working-file indexing and browse/select must be restricted to allowlisted roots configured for the sidecar.

When no explicit working-files root override is provided, implementations should prefer `/assets/Model Working Files` when that path is available via `MODEL_CATALOG_WORKING_FILES_ROOT`.

## Path Normalization Rules

Apply in this order.

1. Parse as filesystem path using `pathlib`.
2. Expand user markers when present (for example `~`).
3. Convert to absolute path and resolve symlinks where supported.
4. Normalize separators to platform-native form for IO.
5. Store a comparison key using lowercase forward-slash form.

Recommended persisted fields:

- `source_path_raw`: operator-provided input
- `source_path_canonical`: absolute canonical path used for IO
- `source_path_compare_key`: lowercase `/`-separated key used for equality checks

## Host Path Mapping For Launch Actions

For `Launch File` and `Show In Explorer`, container paths must be mapped to host-visible paths.

Mapping inputs:

- bind mount root from `ASSETS_ROOT_HOST`
- container assets root (default `/assets`)
- canonical indexed file path

Required behavior:

- map `/assets/<rest>` to `<ASSETS_ROOT_HOST>/<rest>`
- keep mapping read-only for launch actions (no implicit move/write)
- return both `container_path` and `host_path` in launch payloads
- if `ASSETS_ROOT_HOST` does not include `/mnt/c`, disable launch and explorer actions for this phase

WSL compatibility guidance:

- when host mapping begins with `/mnt/c`, launcher integrations should support Windows `C:\...` resolution for Explorer-based actions
- paths containing `/OneDrive` should be treated as user OneDrive-backed locations unless explicitly overridden
- `Show In Explorer` should open the containing folder for the mapped file path

## Filename Normalization Rules

Used for proposal grouping and weak duplicate hints only (never as hard identity).

1. Strip extension.
2. Trim leading/trailing whitespace.
3. Collapse repeated whitespace to a single space.
4. Lowercase for comparison.
5. Remove common reacquire suffixes for a base-name hint:
   - ` (1)`, ` (2)`, ...
   - `_0`, `_1`, ...
   - `-copy`, `_copy`

Recommended persisted fields:

- `file_name_raw`
- `file_name_base_hint`

## Identity And Dedupe Strategy

### Primary Identity

- `sha256(content)` is the canonical identity key for dedupe.

### Secondary Hints (non-authoritative)

- file size
- normalized base-name hint
- extension

Secondary hints may raise warnings but must not auto-merge records when hash differs.

### Dedupe Classes

- `exact_duplicate`: matching `sha256`
- `probable_duplicate`: same size + similar normalized base-name, hash missing/unavailable
- `name_collision`: same normalized base-name, different hash

Operator impact:

- `exact_duplicate`: warn and offer attach/skip/keep-as-variant
- `probable_duplicate`: warn, require explicit operator choice
- `name_collision`: informational warning only

## Grouping Rules For Bulk Discovery

Supported strategies:

- `by-folder`: one proposed group per qualifying folder
- `by-root`: root-level files grouped by immediate container pattern
- `flat`: all files into one proposal (not recommended for large imports)

Group proposal metadata must include:

- `grouping_strategy`
- `source_root`
- `source_paths`
- `duplicate_warnings`

## Group Membership Rules

Working groups are logical overlays over indexed files.

Required behavior:

- files may belong to multiple groups
- one optional primary-group marker may be used for default display intent
- adding an already-grouped file should warn, not block
- `Ungrouped` view means no current group memberships

## Working Group Slug Naming & Collision Handling

**Group slug generation**:
- Derived from group title via URL-safe lowercasing
- Example: "Gridfinity Holders" → `gridfinity-holders`

**Collision avoidance** (implemented):
- Simple append strategy: `{slug}`, `{slug}-2`, `{slug}-3`, etc.
- Example:
  - First "Gridfinity Holders" group → `gridfinity-holders`
  - Second "Gridfinity Holders" group → `gridfinity-holders-2`
  - Third → `gridfinity-holders-3`
- Implementation: [sidecars/model_catalog/app/routers/working.py](sidecars/model_catalog/app/routers/working.py#L425) `_unique_slug()` function

**File-level collision handling** (implemented in reorganize operation):
- When moving files into a group folder, apply `_unique_destination_path()` semantics
- If destination file already exists: `filename-2.ext`, `filename-3.ext`
- Example: moving `benchy.3mf` to a group folder that already contains `benchy.3mf` → creates `benchy-2.3mf`
- This applies at the individual file level, separate from group slug uniqueness

**Duplicate-content protection** (implemented in reorganize operation):
- Reorganize computes a SHA256 hash for each source file before move
- If target folder already contains a file with the same hash, reorganize skips that source file instead of renaming or moving it
- Same-name but different-hash files are treated as variants and still use rename semantics (`-2`, `-3`, ...)

**Reorganize API response signals**:
- Dry-run (`POST /api/working-groups/{group_id}/reorganize` with `execute=false`) returns:
  - `operation_plan` (alias: `plan`)
  - `collisions_detected`
  - `collision_renames`
  - `duplicate_hash_skips`
  - `duplicate_hash_skipped_count`
  - `conflicts` (only blocking issues)
- Execute (`execute=true`) returns:
  - `moved_count`
  - `operation_plan` (alias: `plan`)
  - `collisions_detected`
  - `collision_renames`
  - `duplicate_hash_skips`
  - `duplicate_hash_skipped_count`
  - `audit_events`
  - `inventory_refresh`

## Validation States

Working-file validation outcomes:

- `ready`
- `duplicate_candidate`
- `unsupported_type`
- `missing_source`
- `needs_manual_grouping`

Every non-ready state must include machine-readable warning codes and human-readable messages.

## Required Persistence Fields

Minimum schema contract for working-file index rows:

- `id`
- `source_path_raw`
- `source_path_canonical`
- `source_path_compare_key`
- `file_name_raw`
- `file_name_base_hint`
- `file_extension`
- `file_size_bytes`
- `sha256_hash` (nullable until computed)
- `detected_at`
- `last_seen_at`
- `validation_state`
- `warnings_json`
- `root_path`

## Acceptance Checklist (Issues #1074, #1169)

- supported file types and root-scope rules are documented
- path and filename normalization rules are explicit and ordered
- hash-first identity strategy is explicit
- dedupe classes and operator handling are explicit
- grouping strategy behavior is explicitly defined
- root-first indexing for `/assets/Model Working Files` is explicit
- multi-group membership semantics are explicit
- grouped vs ungrouped behavior is explicit

## Related Docs

- `docs/features/model_catalog/integration/spike-1059-working-file-indexing-validation.md`
- `docs/features/model_catalog/working-files-workflow-redesign-issue-1169.md`
- `docs/features/model_catalog/intake-inbox-design.md`
- `docs/features/model_catalog/phase-1.5-intake-implementation-breakdown.md`
- `docs/features/model_catalog/phase-delivery-and-validation.md`
