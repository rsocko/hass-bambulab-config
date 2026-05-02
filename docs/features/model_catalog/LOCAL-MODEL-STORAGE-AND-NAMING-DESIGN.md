# Local Model Storage and Naming Design

> **Status**: Approved, implemented 2026-05-02
> **Scope**: Folder naming convention, asset storage structure, and rename behavior for local catalog models
> **Related**: [LOCAL-MODEL-IMPORT-GUIDE.md](LOCAL-MODEL-IMPORT-GUIDE.md), [architecture-overview.md](architecture-overview.md)

## Overview

Local model entries in the sidecar curated catalog are stored as folders under `MODEL_CATALOG_CURATED_ASSETS_ROOT` (e.g., `/assets/Model Catalog`). Each folder corresponds to one model record and contains all associated model assets (3MF, images, documents, etc.).

This document specifies:
1. **Naming convention** for model folders
2. **Immutability contract** for folder names
3. **Rename behavior** when a user updates a model's display name
4. **Future maintenance operations** for folder reorganization

---

## Naming Convention: `<name-slug>--<shortid>`

### Format

```
{slug}--{shortid}

where:
  slug     = lowercased hyphenated name (e.g., 'gridfinity-bin', 'benchy-calibration')
  shortid  = 8-character stable suffix derived from UUID4 (e.g., 'a1b2c3d4')
  
Examples:
  gridfinity-bin--a1b2c3d4
  benchy-calibration--f7e8c9d0
  storage-organizer--2b3a4c5d
```

### Rationale

| Aspect | Benefit |
|--------|---------|
| **Name-first**: Slug at the start makes folders discoverable without opening HA/sidecar UI | Useful when exploring asset storage outside the solution (e.g., backup navigation, manual recovery) |
| **Human-readable**: Slug is derived from the model name, preserving intent | Operators can infer folder purpose without additional metadata lookups |
| **Unique**: Short ID suffix guarantees uniqueness regardless of slug collisions | Two models named "Gridfinity Bin" receive different folders, no counter suffix needed |
| **Stable**: Short ID is generated once at creation and never changes | Folder paths are stable references; renaming or recreating a model does not move assets |
| **Collision-safe**: UUID4-based suffix (truncated to 8 chars) has negligible collision probability (~1 in 4 billion for typical catalogs) | No complex collision detection logic required; rare edge cases degrade gracefully |

---

## Immutability Contract

### Folder Names Are Stable

**The local model ID (folder name) is immutable.** It is set once at model creation and cannot be changed by user actions.

### Why Immutability Matters

1. **Asset Storage Stability**: Model assets are stored under the `local_model_id` folder path. Moving folders on every name change would require:
   - Updating all asset references in the database
   - Physical filesystem operations (costly, error-prone)
   - Risk of breaking external references (e.g., backup paths, manual file access)

2. **External References**: Asset paths may be referenced outside the HA/sidecar system:
   - Backup and recovery procedures
   - File system snapshots
   - Manual access to assets (e.g., editing images outside HA)
   - Integration with external tools

3. **Simplicity**: Decoupling folder identity from display name reduces complexity and risk:
   - Model metadata (name, description, etc.) can be edited freely
   - The storage structure remains unaffected
   - Rename operations are simple (database-only updates)

---

## Model Rename Behavior

### Scenario: User Changes Model Display Name

**Action**: User edits a model via HA dashboard or API and changes `model_name` from "Gridfinity Bin" to "Gridfinity Storage Container".

**Result**:
- ✅ Model name updated in database (`model_name` field)
- ✅ Model reflects new name in HA UI and API responses
- ❌ **Folder name does NOT change** (remains `gridfinity-bin--a1b2c3d4`)
- ❌ Model assets remain in the original folder path

### Why No Automatic Rename?

Automatic folder renames would introduce:
- **Concurrency risk**: Active asset uploads or reads could fail mid-operation
- **Backup complexity**: Old paths in snapshots/backups become stale
- **Unrecoverable data loss**: If rename fails partway, assets could become orphaned
- **External breakage**: Any external tooling or documentation referencing the old path breaks

---

## Current Behavior: Name → ID Generation

When a model is created (via import, intake queue, or API):

1. **Slug derivation**: Model name is converted to a URL-safe slug:
   - Lowercased, spaces → hyphens, non-alphanumeric stripped
   - Examples: "Gridfinity Bin" → `gridfinity-bin`, "Benchy (v3)" → `benchy-v3`

2. **Short ID generation**: A random 8-character suffix is created from UUID4

3. **ID assignment**: Combined ID is assigned: `gridfinity-bin--a1b2c3d4`

4. **Uniqueness check**: If (extremely unlikely) the combined ID exists, a new short ID is generated and checked again

5. **Folder creation**: Folder is created at `{MODEL_CATALOG_CURATED_ASSETS_ROOT}/gridfinity-bin--a1b2c3d4/`

---

## Future: Maintenance Operations

### Optional Maintenance Command (Future Work)

A future maintenance utility could be added to help organize legacy model folders to the new naming convention:

**Purpose**: Normalize older model folders (if using older naming schemes) to the `<slug>--<shortid>` format.

**Behavior**:
- **Dry-run mode**: Preview which folders would be renamed (no changes)
- **Validation**: Check database consistency before any filesystem changes
- **Pause operational updates**: Prevent concurrent model edits during migration
- **Backup guidance**: Recommend backup before running
- **Detailed report**: List all renamed folders and any failures

**Example**:
```bash
# Dry-run: show what would be renamed
python tools/model_catalog/normalize_model_folders.py --dry-run

# Execute rename with backup recommendation
python tools/model_catalog/normalize_model_folders.py --confirm --backup-path /backup/model-catalog-pre-normalize
```

This tool is **not required** for normal operation and should be treated as a one-off admin cleanup utility.

---

## Storage Structure Example

```
/assets/Model Catalog/
├── gridfinity-bin--a1b2c3d4/
│   ├── gridfinity-bin.3mf                    ← primary model
│   ├── gridfinity-bin-preview.png            ← preview image
│   ├── gridfinity-bin-assembly.md            ← documentation
│   └── ...
├── benchy-calibration--f7e8c9d0/
│   ├── benchy-v4.stl                         ← primary model
│   ├── benchy-with-callouts.png              ← supporting image
│   └── ...
└── storage-organizer--2b3a4c5d/
    ├── organizer-base.3mf
    ├── organizer-dividers.3mf
    ├── assembly-instructions.pdf
    └── ...
```

---

## API Behavior

### Creating a New Model

**Endpoint**: `POST /api/local/models`

**Request**:
```json
{
  "local_model_id": null,        /* Can be omitted or null */
  "model_name": "Gridfinity Bin",
  "description": "Modular storage container"
}
```

**Response**:
```json
{
  "success": true,
  "local_model_id": "gridfinity-bin--a1b2c3d4",  /* Auto-generated */
  "model_name": "Gridfinity Bin"
}
```

### Updating a Model Name

**Endpoint**: `PATCH /api/local/models/{local_model_id}`

**Request**:
```json
{
  "model_name": "Gridfinity Storage Container"   /* Changed */
}
```

**Response**:
```json
{
  "success": true,
  "local_model_id": "gridfinity-bin--a1b2c3d4",  /* Unchanged */
  "model_name": "Gridfinity Storage Container"
}
```

**Folder remains**: `gridfinity-bin--a1b2c3d4/` (unchanged)

---

## Guidelines for HA/UI Implementation

### When Displaying Models

1. **Show the display name** (`model_name`) in UI labels, titles, search results
2. **Do not expose** the local_model_id as a primary identifier to end users (it's a storage key)
3. **Search should prioritize** display name, but can fallback to ID if needed

### When Exporting or Documenting

1. **Include both** `model_name` and `local_model_id` when creating references
2. **For backup/disaster recovery guidance**, recommend backing up the entire `{MODEL_CATALOG_CURATED_ASSETS_ROOT}` folder tree (folder structure is preserved exactly)
3. **If providing file paths** to users (e.g., in error messages), show the full path: `/assets/Model Catalog/gridfinity-bin--a1b2c3d4/`

---

## Summary

| Item | Decision |
|------|----------|
| **Folder naming** | `{slug}--{shortid}` format, generated at creation |
| **Mutability** | Immutable; cannot be changed via rename |
| **Rename behavior** | Updates `model_name` in DB only; folder stays unchanged |
| **External references** | Safe; folder paths remain stable across the model's lifetime |
| **Collision handling** | Negligible with UUID-based shortid; graceful fallback to new generation |
| **Future maintenance** | Optional one-off cleanup tool (not required for normal operation) |

This design balances **human readability** with **storage stability**, ensuring that folder paths remain reliable references even as model metadata evolves.
