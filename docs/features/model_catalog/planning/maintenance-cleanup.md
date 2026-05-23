# Model Catalog Cleanup & Reset Maintenance

> **Status**: Ready for use (integrated into sidecar CLI)
> **Last updated**: 2026-05-02
> **Purpose**: Safely reset model catalog database and/or filesystem for testing and development
> **Scope**: Admin-only utility; not required during normal operation

## Overview

The repository includes cleanup utilities for the Model Catalog sidecar, but the currently deployed container image only copies `/app/app` and does **not** include the `sidecars.model_catalog` CLI package. That means documented commands like `python -m sidecars.model_catalog cleanup ...` will fail inside the running container until the image packaging is updated.

For the current deployed image, the reliable host-side reset path is a `docker exec` Python snippet that runs directly inside the container against the configured DB and asset roots.

**Available layers**:
- **Host via `docker exec` Python snippet** (works with the current deployed image)
- **Sidecar CLI** (`python -m sidecars.model_catalog cleanup`) only after the image is rebuilt to include the CLI package
- **Standalone scripts** (legacy): Still in `tools/model_catalog/` for reference
- **Preset wrapper** (legacy): `tools/model_catalog/reset_model_catalog.py` for standalone use

---

## Quick Start

### Using Host-Side `docker exec` (Current Deployed Image)

From the host, run this to clear the database plus Catalog, Working Files, and Inbox contents while preserving the root folders themselves:
```bash
docker exec -i model-catalog python - <<'PY'
import os
import shutil
import sqlite3
from pathlib import Path

tables = [
  "model_catalog_assets",
  "model_catalog_custom_fields",
  "intake_queue_uploads",
  "working_items",
  "working_groups",
  "model_catalog_events",
  "model_catalog_links",
  "model_catalog_model_ranking",
  "manyfold_model_summary_cache",
  "model_catalog_entries",
]

db_path = Path(os.getenv("MODEL_CATALOG_DB_PATH", "/data/model_catalog.db"))
curated_root = Path(os.getenv("MODEL_CATALOG_CURATED_ASSETS_ROOT", "/assets/Model Catalog"))
working_root = Path(os.getenv("MODEL_CATALOG_WORKING_FILES_ROOT", "/assets/Model Working Files"))
inbox_root = Path((os.getenv("MODEL_CATALOG_INTAKE_ROOTS", "/assets/Model Inbox").split(",")[0]).strip())

print(f"Cleaning database: {db_path}")
if db_path.exists():
  conn = sqlite3.connect(db_path)
  try:
    conn.execute("PRAGMA foreign_keys=ON")
    for table in tables:
      exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
      ).fetchone()
      if not exists:
        print(f"  skip missing table: {table}")
        continue
      deleted = conn.execute(f"DELETE FROM {table}").rowcount
      print(f"  deleted {deleted} rows from {table}")
    conn.commit()
    conn.execute("VACUUM")
    print("  VACUUM complete")
  finally:
    conn.close()
else:
  print("  database file not found, skipping")

for label, root in [
  ("curated", curated_root),
  ("working", working_root),
  ("inbox", inbox_root),
]:
  print(f"Cleaning {label} root: {root}")
  if not root.exists():
    print("  root not found, skipping")
    continue
  files_deleted = 0
  dirs_deleted = 0
  for child in root.iterdir():
    if child.is_dir():
      shutil.rmtree(child)
      dirs_deleted += 1
    else:
      child.unlink()
      files_deleted += 1
  print(f"  deleted {files_deleted} files and {dirs_deleted} folders")

print("Model catalog cleanup complete.")
PY
```

### Using Sidecar CLI (Only After Rebuilding the Image)

These commands are correct for the repository layout, but they will not work in the currently deployed image until the CLI package is copied into the container image:
```bash
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all --execute
```

### Using Standalone Scripts (Legacy)

Still available for backward compatibility:
```bash
python tools/model_catalog/reset_model_catalog.py reset-all
python tools/model_catalog/reset_model_catalog.py reset-all --execute
```

---

## Sidecar CLI Commands

### cleanup reset-db

Clears all model catalog database tables only. Preserves filesystem zones.

**Use when**:
- Testing new database schema or migrations
- Corrupted database state
- Want to keep files but reset metadata

**Current deployed image**:
Use the host-side Python snippet above and remove the filesystem cleanup block if you want DB-only behavior.

**After image rebuild with CLI package included**:
```bash
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-db --execute
```

**What gets cleared**:
- `model_catalog_entries` (local model records)
- `model_catalog_assets` (file/image assets)
- `model_catalog_links` (archive linkage)
- `model_catalog_custom_fields` (enrichment metadata)
- `working_groups` & `working_items` (Working veneer state)
- `intake_queue_uploads` (browser upload queue)
- `manyfold_model_summary_cache` (API cache)
- `model_catalog_model_ranking` (ranking signals)
- `model_catalog_events` (audit log)

**What stays**:
- All files in `/assets/Model Catalog`, `/assets/Model Working Files`, `/assets/Model Inbox`
- Database file itself (schema is preserved)

### cleanup reset-all

Clears database **and** filesystem zones (curated, working, inbox). Zone root folders are preserved; only contents are deleted.

**Use when**:
- Full clean slate for integration tests
- Reset from corrupted or test state before running full test suite
- Verify catalog behavior from empty state

**Current deployed image**:
Use the host-side Python snippet above.

**After image rebuild with CLI package included**:
```bash
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all --execute
```

**What gets cleared**:
- All database tables (same as `reset-db`)
- All files and folders inside each zone root:
  - `/assets/Model Catalog/*` (all models and assets)
  - `/assets/Model Working Files/*` (all working groups and files)
  - `/assets/Model Inbox/*` (all intake staging)

**What stays**:
- Zone root directories themselves
- Database schema (columns and indexes remain)

**Selective zones**:
The current host-side snippet is intentionally the full reset path. For selective-zone cleanup today, use the legacy standalone script from the repo checkout or rebuild the image with the CLI package included.

### cleanup cleanup

Advanced granular cleanup with scope, table, and zone selection.

**Use when**:
- Need precise control over what gets cleared
- Targeting specific tables or zones
- Testing partial cleanup scenarios

**Command**:
This granular CLI is available in the repository source, but not in the currently deployed image. Use it after rebuilding the image to include the CLI package, or run the legacy standalone script from a repo checkout.

**Scope options**:

| Scope | Effect |
|-------|--------|
| `--scope db` | Clear only database tables |
| `--scope files` | Clear only filesystem zones |
| `--scope both` | Clear database and selected file zones (default) |

**Table selection** (default: all):
```bash
--tables model_catalog_entries model_catalog_assets model_catalog_links ...
```

**File zone selection** (default: all):
```bash
--file-zones curated working inbox
```

---

## Confirmation Flow

When you run the CLI with `--execute` (and without `--yes`), you'll be prompted three times:

1. **Exact phrase**: Type `DELETE MODEL CATALOG DATA`
2. **Random token**: Type the generated 6-character token (e.g., `A1B2C3`)
3. **Today's date**: Type today's date (e.g., `2026-05-02`)

This multi-step confirmation is intentionally verbose to prevent accidental data loss.

**Bypass confirmations**:
This applies only to the repository CLI after the image is rebuilt to include the CLI package.

```bash
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all --execute --yes
```

---

## Environment Variables

Commands auto-detect these if set:

- `MODEL_CATALOG_DB_PATH` — Path to SQLite DB (default: `/data/model_catalog.db`)
- `MODEL_CATALOG_CURATED_ASSETS_ROOT` — Catalog zone root (default: `/assets/Model Catalog`)
- `MODEL_CATALOG_WORKING_FILES_ROOT` — Working files zone root (default: `/assets/Model Working Files`)
- `MODEL_CATALOG_INTAKE_ROOTS` — Intake inbox zone roots (default: `/assets/Model Inbox`)

You can override these with command-line flags (`--db-path`, `--curated-root`, etc.).

---

## Common Workflows

### Full Test Reset Before Running Tests

```bash
# Use the host-side Python snippet from Quick Start
```

### Cleanup for CI/Automation

```bash
# Current deployed image: run the host-side Python snippet from Quick Start
# Future rebuilt image: docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all --execute --yes
```

### Database Corruption Recovery

```bash
# Current deployed image: use the host-side snippet and remove filesystem cleanup
# Future rebuilt image: docker exec model-catalog python -m sidecars.model_catalog cleanup cleanup --scope db --execute
```

### Compact Database After Large Deletions

```bash
# The host-side snippet already runs VACUUM.
```

### Keep Working Files, Reset Curated & Inbox

```bash
# Current deployed image: not available via the host snippet.
# Use the legacy standalone script from a repo checkout, or rebuild the image with the CLI package included.
```

---

## Important Notes

### Current Runtime Limitation

The repository contains a sidecar CLI, but the current image only copies `/app/app` into the container. As a result, `python -m sidecars.model_catalog ...` is not available in the running container until the image packaging is updated and redeployed.

For now, treat the host-side `docker exec` Python snippet as the production-safe cleanup path.

### Standalone Scripts (Legacy)

The scripts in `tools/model_catalog/` are maintained for backward compatibility but are not the primary integration point. Use them only if:
- You prefer a completely standalone script
- You're not using Docker/containers
- You're testing cleanup without the sidecar running

### Zone Root Preservation

Zone root directories are **never deleted**, only their contents. This means:
- `/assets/Model Catalog` folder stays (empty)
- `/assets/Model Working Files` folder stays (empty)
- `/assets/Model Inbox` folder stays (empty)

### Database Schema Preserved

When you clear database tables, the **schema** (tables, indexes, columns) remains. This is safe for repeated runs and testing.

### Dry-Run Always Safe

Dry-run mode produces no side effects. Always start with dry-run:
```bash
# Current deployed image: no dry-run helper is bundled in the container.
# Rebuild the image with the CLI package if you need an in-container dry-run.
```

### Backup Before Destructive Operations

For production environments, always backup your database and important files before running with `--execute`:

```bash
# Backup before cleanup
docker exec model-catalog bash -c 'cp /data/model_catalog.db /data/model_catalog.db.backup'
docker exec model-catalog bash -c 'tar -czf /data/assets-backup.tar.gz /assets/'

# Then run the host-side Python snippet from Quick Start
```

---

## Troubleshooting

### "DB path does not exist"

The database file doesn't exist yet. This is normal on first run; proceed with your test.

### "Permission denied" on filesystem cleanup

Ensure the container has read/write access to the zone root directories. Check file ownership and permissions inside the container:

```bash
docker exec model-catalog ls -la /assets/Model\ Catalog
docker exec model-catalog ls -la /assets/Model\ Working\ Files
docker exec model-catalog ls -la /assets/Model\ Inbox
```

### Confirmation prompt timeout or stuck

Just press Ctrl+C and re-run. Cleanup will not proceed without all three confirmations.

### "Invalid transition" error during atomic operations

Unlikely but can occur if database is corrupted. Try `--vacuum` flag or manually inspect database inside the container:

```bash
docker exec model-catalog sqlite3 /data/model_catalog.db ".tables"
```

### `No module named sidecars` inside container

This is expected with the current deployed image. The image copies `/app/app` but does not copy the `sidecars.model_catalog` package, so `python -m sidecars.model_catalog ...` is unavailable until the image is rebuilt.

For the current image, use the host-side Python snippet from Quick Start. Also verify the container is running:

```bash
docker ps | grep model-catalog
```

### Settings not loading correctly

The CLI reads from environment variables set in the sidecar container. Verify by checking the container environment:

```bash
docker exec model-catalog env | grep MODEL_CATALOG
```

After rebuilding the image with the CLI package, you can also pass explicit paths on the command line:

```bash
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all \
  --db-path /data/model_catalog.db \
  --curated-root "/assets/Model Catalog"
```

---

## Implementation Details

### Architecture

The cleanup CLI is implemented as:
- **Module**: `sidecars/model_catalog/cli/cleanup.py` — Click command group
- **Entry point**: `sidecars/model_catalog/__main__.py` — Main CLI dispatcher
- **Integration**: Imports from `app.settings` to use sidecar configuration
- **Dependency**: Click 8.1.13+ (added to `requirements.txt`)

### Running Inside the Container

The repository CLI is designed to run inside the container after the image packaging is updated to include the CLI package.

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8314"]
```

After that image rebuild, you can run a CLI command by overriding the CMD:

```bash
docker run -it model-catalog python -m sidecars.model_catalog cleanup reset-all --execute
```

Or use `docker exec` on a running container after the rebuild:

```bash
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all --execute
```

### Configuration Loading

The CLI uses the same `load_settings()` function as the FastAPI app, so it respects all environment variables and `.env` file settings. This ensures consistency between CLI and runtime configurations.

---

## See Also

- [LOCAL-MODEL-STORAGE-AND-NAMING-DESIGN.md](../LOCAL-MODEL-STORAGE-AND-NAMING-DESIGN.md) — Asset storage and folder naming
- [MAINTENANCE-NORMALIZE-MODEL-FOLDERS.md](../MAINTENANCE-NORMALIZE-MODEL-FOLDERS.md) — One-time folder normalization utility
- [Persistence And Backup Strategy](../persistence-and-backup-strategy.md) — Backup/restore runbook
- [Model Catalog Sidecar README](../../sidecars/model_catalog/README.md) — Sidecar deployment and configuration
