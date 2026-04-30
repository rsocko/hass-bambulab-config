# Working File Inventory And Normalization Spec

> Status: Wave 1 specification
> Issue: #1074
> Last updated: 2026-04-30
> Scope: Canonical rules for working-file discovery, normalization, and duplicate identity in Phase 5 intake workflows.

## Purpose

Define a single, implementation-ready contract for:

- what files are in scope for intake and indexing
- how source paths and names are normalized
- how duplicate identity is computed
- how conflicts are surfaced to operators before commit

This document is authoritative for Phase 5 backend and HA workflow implementations.

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

Required behavior:

- all source paths are resolved to absolute canonical paths
- all canonical paths must remain within an allowlisted root
- path traversal attempts are rejected
- rejected paths return explicit validation errors

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

## Acceptance Checklist (Issue #1074)

- supported file types and root-scope rules are documented
- path and filename normalization rules are explicit and ordered
- hash-first identity strategy is explicit
- dedupe classes and operator handling are explicit
- grouping strategy behavior is explicitly defined

## Related Docs

- `docs/features/model_catalog/integration/spike-1059-working-file-indexing-validation.md`
- `docs/features/model_catalog/intake-inbox-design.md`
- `docs/features/model_catalog/phase-1.5-intake-implementation-breakdown.md`
- `docs/features/model_catalog/phase-delivery-and-validation.md`
