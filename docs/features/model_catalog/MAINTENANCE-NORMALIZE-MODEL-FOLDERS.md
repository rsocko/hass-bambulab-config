# Model Folder Normalization Maintenance

> **Status**: Design, ready for implementation
> **Priority**: Low (optional maintenance, not blocking normal operation)
> **Created**: 2026-05-02
> **Related**: [LOCAL-MODEL-STORAGE-AND-NAMING-DESIGN.md](LOCAL-MODEL-STORAGE-AND-NAMING-DESIGN.md)

## Overview

This document specifies a future maintenance utility to normalize model folder names to the new `{name-slug}--{shortid}` convention.

**Trigger**: When the local model naming convention changes or an operator wants to reorganize folders to match the current standard (e.g., after upgrading the sidecar).

**Scope**: One-off admin cleanup tool; not part of normal operation and not required for catalog functionality.

---

## Problem Statement

The local model ID format evolved over time:
- **Old scheme** (before 2026-05-02): `{name-slug}` or `{name-slug}-{counter}` (e.g., `gridfinity-bin`, `benchy-2`)
- **New scheme** (2026-05-02+): `{name-slug}--{shortid}` (e.g., `gridfinity-bin--a1b2c3d4`)

Existing catalogs created before the convention change will have folders using the old scheme. While the sidecar continues to support both schemes, operators may want to:

1. **Normalize** legacy folders to the new scheme for consistency
2. **Clean up** duplicate or conflicting folder names safely
3. **Verify** that all database records and asset paths align post-migration

This maintenance tool provides a controlled, auditable way to perform this one-time reorganization.

---

## Workflow

### Phase 1: Assessment & Dry-Run

**Goal**: Show what would be renamed without making changes.

**Command**:
```bash
python tools/model_catalog/normalize_model_folders.py --dry-run
```

**Output**:
```
📋 MODEL FOLDER NORMALIZATION — DRY RUN
================================================

Database check:
  ✓ Connected to: /data/model_catalog.db
  ✓ Found 47 model entries

Storage check:
  ✓ Scanning: /assets/Model Catalog
  ✓ Found 45 folders

Recommendations:

1️⃣ OLD SCHEME (need normalization):
  gridfinity-bin
    → Current folder: /assets/Model Catalog/gridfinity-bin/
    → New folder: /assets/Model Catalog/gridfinity-bin--a1b2c3d4/
    → Action: RENAME FOLDER
    
  benchy (old convention)
    → Current folder: /assets/Model Catalog/benchy/
    → New folder: /assets/Model Catalog/benchy--f7e8c9d0/
    → Action: RENAME FOLDER

  storage-organizer-2 (collision resolution)
    → Current folder: /assets/Model Catalog/storage-organizer-2/
    → New folder: /assets/Model Catalog/storage-organizer--2b3a4c5d/
    → Action: RENAME FOLDER

2️⃣ ALREADY NORMALIZED:
  gridfinity-storage--d5e6f7a8 ✓
  benchy-calibration--c9d0e1f2 ✓

3️⃣ ISSUES FOUND:
  ⚠️ Missing folder (DB record but no folder):
     ID: "missing-model--xyz123"
     Action: FLAG FOR REVIEW (no folder to rename)

  ⚠️ Orphan folder (folder but no DB record):
     Folder: /assets/Model Catalog/unknown-model/
     Action: BACKUP RECOMMENDED before deleting

================================================
Summary:
  Total models in DB:          47
  Folders found:               45
  Old scheme folders:          18
  Already normalized:          25
  Missing folders:             2
  Orphan folders:              0

Estimated changes:            18 folder(s) to rename
Prerequisites to check:        None (database OK, storage OK)

Next step: Run with --confirm to execute changes.
```

### Phase 2: Pre-Execution Checks

**Goal**: Verify safety before making filesystem changes.

**Automatic checks** (run before confirmation):

1. **Database integrity**: 
   - All `local_model_id` values match their folders OR vice versa
   - No duplicate IDs
   - All asset records have valid `local_model_id` references

2. **Filesystem consistency**:
   - All folders are readable/writable
   - No permission issues
   - Sufficient disk space for in-place rename

3. **Backup readiness**:
   - If `--backup-path` provided: destination is writable and has space
   - Backup naming: `model-catalog-backup-YYYYMMDD-HHMMSS.tar.gz`

4. **Concurrency**:
   - No active uploads or queries detected
   - Sidecar can be safely paused

**Fail conditions** (blocks execution):
- Database locks detected → Recommend stopping sidecar first
- Insufficient disk space → Provide size estimate
- Permission errors → List problematic folders
- Unresolvable orphans → Require manual review

### Phase 3: Execution

**Command** (with confirmation):
```bash
python tools/model_catalog/normalize_model_folders.py \
  --confirm \
  --backup-path /backups/model-catalog \
  --pause-sidecar http://model-catalog:5000 \
  --verify-post-migration
```

**Parameters**:

| Flag | Purpose | Default |
|------|---------|---------|
| `--confirm` | Execute changes (required; no default dry-run) | N/A (must specify) |
| `--backup-path` | Where to store pre-migration backup | Optional (recommended) |
| `--pause-sidecar` | URL of sidecar to pause during migration | Optional (manual pause OK) |
| `--verify-post-migration` | Run consistency check after completion | `true` |
| `--verbose` | Detailed operation logging | `false` |
| `--parallelism` | Number of concurrent rename operations | `1` (sequential for safety) |

**Execution steps**:

1. **Pause sidecar** (if URL provided):
   ```
   → POST /api/system/pause-operations
   ✓ Sidecar paused
   ```

2. **Create backup** (if path provided):
   ```
   → Archiving: /assets/Model Catalog/
   → Destination: /backups/model-catalog/model-catalog-backup-20260502-143052.tar.gz
   ✓ Backup created (458 MB, checksum: abc123...)
   → Store checksum: /backups/model-catalog/MANIFEST.txt
   ✓ MANIFEST written
   ```

3. **Update database** (transaction):
   ```
   → Begin transaction
   → Update model_catalog_entries.local_model_id for 18 models
   → Update model_catalog_assets.model_catalog_entry_id references (if needed)
   ✓ Transaction committed (18 rows updated)
   ```

4. **Rename folders**:
   ```
   → gridfinity-bin → gridfinity-bin--a1b2c3d4  ✓
   → benchy → benchy--f7e8c9d0  ✓
   → storage-organizer-2 → storage-organizer--2b3a4c5d  ✓
   ... (16 more)
   ✓ All 18 folders renamed
   ```

5. **Verify migration**:
   ```
   → Checking database consistency...
   ✓ All model IDs updated
   ✓ All asset paths valid
   ✓ No orphans detected
   ✓ Checksums match
   ```

6. **Resume sidecar**:
   ```
   → POST /api/system/resume-operations
   ✓ Sidecar resumed
   ```

**Output**:
```
✅ MIGRATION COMPLETE
================================================
Pre-migration backup: /backups/model-catalog/model-catalog-backup-20260502-143052.tar.gz
  Checksum: sha256:abc123def456...
  Size: 458 MB
  Date: 2026-05-02T14:30:52Z

Changes applied:
  ✓ 18 folders renamed
  ✓ 18 database records updated
  ✓ 0 errors

Post-migration verification:
  ✓ Database consistency: PASS
  ✓ Filesystem consistency: PASS
  ✓ Asset integrity: PASS

Rollback command (if needed):
  python tools/model_catalog/normalize_model_folders.py --rollback 20260502-143052

Next: Review backup for retention, then delete when confident.
```

### Phase 4: Rollback (If Needed)

**Goal**: Restore from backup if issues are detected post-migration.

**Command**:
```bash
python tools/model_catalog/normalize_model_folders.py \
  --rollback 20260502-143052 \
  --pause-sidecar http://model-catalog:5000
```

**Actions**:
1. Pause sidecar
2. Restore backup tarball → `/assets/Model Catalog/`
3. Restore database from transaction log
4. Verify consistency
5. Resume sidecar

**Output**:
```
✅ ROLLBACK COMPLETE
================================================
Restored from backup: model-catalog-backup-20260502-143052.tar.gz
Restored database state: 2026-05-02T14:30:00Z (pre-migration)
Verification: PASS
```

---

## Implementation Details

### Script Structure

**Location**: `tools/model_catalog/normalize_model_folders.py`

**Main functions**:

```python
def assess_normalization(db_path: Path, storage_root: Path) -> NormalizationAssessment:
    """Scan database and filesystem, report what needs to be done."""
    
def plan_renames(assessment: NormalizationAssessment) -> list[RenameOperation]:
    """Compute rename operations from assessment."""
    
def validate_preconditions(plan: list[RenameOperation], settings: Settings) -> ValidationResult:
    """Check database integrity, permissions, space, concurrency."""
    
def create_backup(storage_root: Path, backup_path: Path) -> BackupManifest:
    """Archive catalog folder with checksums."""
    
def execute_migration(plan: list[RenameOperation], db_path: Path, storage_root: Path) -> MigrationResult:
    """Rename folders and update database in transaction."""
    
def verify_post_migration(db_path: Path, storage_root: Path) -> VerificationResult:
    """Consistency checks after migration."""
    
def rollback_migration(backup_manifest: BackupManifest, db_path: Path, storage_root: Path) -> RollbackResult:
    """Restore from backup."""
```

### Data Structures

```python
@dataclass
class NormalizationAssessment:
    """Assessment of current state and what needs normalization."""
    total_models_in_db: int
    folders_found: int
    old_scheme_count: int
    already_normalized_count: int
    missing_folders: list[str]  # DB records with no folder
    orphan_folders: list[Path]  # Folders with no DB record
    
@dataclass
class RenameOperation:
    """A single folder rename + DB update."""
    current_folder_name: str
    new_folder_name: str
    local_model_id: str
    action: str  # "rename_folder", "flag_for_review", etc.
    
@dataclass
class BackupManifest:
    """Metadata for backup tarball."""
    backup_path: Path
    timestamp: str
    checksum: str
    file_count: int
    total_size_bytes: int
    db_snapshot_timestamp: str
```

### Error Handling

**Recoverable errors** (skip and continue):
- Individual folder rename fails → Log, skip, continue with next
- Asset checksum mismatch → Flag, log, continue verification

**Blocking errors** (stop migration):
- Database transaction fails → Rollback, exit with error
- Insufficient disk space → Abort before any changes
- Sidecar concurrency detected → Recommend pause, exit

---

## Safety Considerations

### Immutability Principles

1. **Backup first**: Always create backup before filesystem changes
2. **Database-first updates**: Update DB in transaction before renaming folders
3. **Atomic operations**: Use filesystem transactions (or rename atomicity guarantees per OS)
4. **Verify after each step**: Checksums, record counts, reference integrity

### Concurrency

- **Assume exclusive access**: Operator is responsible for stopping sidecar during migration
- **Optional automatic pause**: If `--pause-sidecar` provided, attempt to pause via API
- **Timeout**: If sidecar doesn't pause within 10s, require manual intervention

### Rollback Path

- Every operation is logged with timestamp
- Backup tarball stored separately from catalog
- Rollback command provided in final output
- Post-rollback verification included

---

## User Workflow

### Scenario 1: Simple Upgrade (No Issues)

```bash
# 1. Dry-run to assess
python tools/model_catalog/normalize_model_folders.py --dry-run

# 2. Create backup
mkdir -p /backups/model-catalog

# 3. Execute with confirmation
python tools/model_catalog/normalize_model_folders.py \
  --confirm \
  --backup-path /backups/model-catalog \
  --pause-sidecar http://model-catalog:5000 \
  --verify-post-migration

# 4. Review results, then delete backup when confident
rm /backups/model-catalog/model-catalog-backup-*.tar.gz
```

### Scenario 2: Issues Detected

```bash
# 1. Dry-run finds orphans
python tools/model_catalog/normalize_model_folders.py --dry-run

# 2. Manual review: investigate orphan folders
ls -la /assets/Model\ Catalog/unknown-folder/

# 3. Decision: move orphan to backup, then run migration
mv /assets/Model\ Catalog/unknown-folder/ /tmp/orphan-backup/

# 4. Execute migration
python tools/model_catalog/normalize_model_folders.py --confirm --backup-path /backups

# 5. If issues: rollback
python tools/model_catalog/normalize_model_folders.py --rollback 20260502-143052
```

---

## Testing Strategy

### Unit Tests

- `test_assess_normalization_detects_old_scheme()`
- `test_plan_renames_generates_correct_new_ids()`
- `test_validate_preconditions_checks_integrity()`
- `test_backup_creates_valid_tarball()`
- `test_execute_migration_updates_db_and_folders()`
- `test_verify_post_migration_passes_on_clean_state()`
- `test_rollback_restores_backup()`

### Integration Tests

- `test_end_to_end_migration_from_dry_run_to_verification()`
- `test_rollback_after_partial_failure()`
- `test_concurrent_sidecar_pause_and_migration()`

### Manual Testing

- Small catalog (5 models) with mix of old/new schemes
- Large catalog (100+ models) to test performance
- Orphan and missing folder scenarios
- Rollback verification with backup restore

---

## Success Criteria

- ✅ All old-scheme folders normalized to new format
- ✅ Database records updated consistently
- ✅ Asset paths remain valid post-migration
- ✅ Orphan folders identified and handled safely
- ✅ Backup created and verified
- ✅ Rollback functional and tested
- ✅ Zero data loss scenarios
- ✅ Clear user communication at each step

---

## Deferred/Non-Goals

- Auto-migration on startup (manual operation only)
- Partial migrations (all-or-nothing approach)
- Migration of Manyfold-imported catalogs (separate concern)
- Real-time folder reorganization (one-time maintenance only)

---

## Future Enhancements

1. **Scheduled maintenance**: Optional cron job for operators who prefer hands-off approach
2. **HA integration**: Dashboard card to show migration status and trigger via UI
3. **Multi-catalog support**: Handle multiple curated roots in single operation
4. **Progress streaming**: WebSocket endpoint for real-time migration progress
5. **Analytics**: Track which migration paths most common (for future design decisions)
