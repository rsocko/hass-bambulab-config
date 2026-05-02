# Model Catalog Cleanup & Reset Maintenance

> **Status**: Ready for use (integrated into sidecar CLI)
> **Last updated**: 2026-05-02
> **Purpose**: Safely reset model catalog database and/or filesystem for testing and development
> **Scope**: Admin-only utility; not required during normal operation

## Overview

The cleanup utilities are integrated into the Model Catalog sidecar as a Click CLI command group. All operations default to **dry-run mode** and require explicit confirmation or `--execute` flag to apply changes.

**Three layers**:
- **Sidecar CLI** (primary): `python -m sidecars.model_catalog cleanup` — runs inside the container or from host via `docker exec`
- **Standalone scripts** (legacy): Still in `tools/model_catalog/` for reference, but the sidecar CLI is preferred
- **Preset wrapper** (legacy): `tools/model_catalog/reset_model_catalog.py` for standalone use

---

## Quick Start

### Using Sidecar CLI (Recommended)

From host via `docker exec`:
```bash
# Dry-run: see what would be reset (DB + files)
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all

# Execute with confirmations
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all --execute
```

Or inside the container:
```bash
# Dry-run
python -m sidecars.model_catalog cleanup reset-all

# Execute with confirmations
python -m sidecars.model_catalog cleanup reset-all --execute

# Non-interactive (automation)
python -m sidecars.model_catalog cleanup reset-all --execute --yes
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

**Command**:
```bash
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-db --execute
```

**Local (inside container)**:
```bash
python -m sidecars.model_catalog cleanup reset-db --execute
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

**Command**:
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
```bash
# Reset DB + only curated and inbox zones (keep working files)
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all \
  --file-zones curated inbox --execute
```

### cleanup cleanup

Advanced granular cleanup with scope, table, and zone selection.

**Use when**:
- Need precise control over what gets cleared
- Targeting specific tables or zones
- Testing partial cleanup scenarios

**Command**:
```bash
# Dry-run: show what would be deleted from specific tables
docker exec model-catalog python -m sidecars.model_catalog cleanup cleanup \
  --scope db \
  --tables model_catalog_entries model_catalog_assets

# Execute: delete only working files zone
docker exec model-catalog python -m sidecars.model_catalog cleanup cleanup \
  --scope files \
  --file-zones working \
  --execute

# Full cleanup with DB compaction
docker exec model-catalog python -m sidecars.model_catalog cleanup cleanup \
  --scope both \
  --execute \
  --vacuum
```

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

When you run with `--execute` (and without `--yes`), you'll be prompted three times:

1. **Exact phrase**: Type `DELETE MODEL CATALOG DATA`
2. **Random token**: Type the generated 6-character token (e.g., `A1B2C3`)
3. **Today's date**: Type today's date (e.g., `2026-05-02`)

This multi-step confirmation is intentionally verbose to prevent accidental data loss.

**Bypass confirmations** (for CI/automation only):
```bash
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all --execute --yes
```

---

## Environment Variables

Commands auto-detect these if set:

- `MODEL_CATALOG_DB_PATH` — Path to SQLite DB (default: `/data/model_catalog.db`)
- `MODEL_CATALOG_CURATED_ASSETS_ROOT` — Curated catalog zone root (default: `/assets/Model Catalog`)
- `MODEL_CATALOG_WORKING_FILES_ROOT` — Working files zone root (default: `/assets/Model Working Files`)
- `MODEL_CATALOG_INTAKE_ROOTS` — Intake inbox zone roots (default: `/assets/Model Inbox`)

You can override these with command-line flags (`--db-path`, `--curated-root`, etc.).

---

## Common Workflows

### Full Test Reset Before Running Tests

```bash
# Dry-run to verify scope
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all

# Execute with confirmations
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all --execute
```

### Cleanup for CI/Automation

```bash
# Non-interactive reset (all zones, DB + files)
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all --execute --yes
```

### Database Corruption Recovery

```bash
# Dry-run to see what's affected
docker exec model-catalog python -m sidecars.model_catalog cleanup cleanup --scope db

# Reset DB only, preserve files and timestamps
docker exec model-catalog python -m sidecars.model_catalog cleanup cleanup --scope db --execute
```

### Compact Database After Large Deletions

```bash
# Reclaim disk space from deleted rows
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-db --execute --vacuum
```

### Keep Working Files, Reset Curated & Inbox

```bash
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all \
  --file-zones curated inbox \
  --execute
```

---

## Important Notes

### Sidecar CLI is Primary

The sidecar CLI (`python -m sidecars.model_catalog cleanup`) is the recommended and preferred way to run cleanup operations. It's:
- Integrated into the sidecar package
- Uses the same settings and configuration as the running sidecar
- Consistent with how the sidecar operates in production

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
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all
```

### Backup Before Destructive Operations

For production environments, always backup your database and important files before running with `--execute`:

```bash
# Backup before cleanup
docker exec model-catalog bash -c 'cp /data/model_catalog.db /data/model_catalog.db.backup'
docker exec model-catalog bash -c 'tar -czf /data/assets-backup.tar.gz /assets/'

# Then run cleanup
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all --execute
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

### Command not found inside container

Ensure the sidecar container has Click installed (it's in `sidecars/model_catalog/requirements.txt`). If running from host via `docker exec`, verify the container is running:

```bash
docker ps | grep model-catalog
```

### Settings not loading correctly

The CLI reads from environment variables set in the sidecar container. Verify by checking the container environment:

```bash
docker exec model-catalog env | grep MODEL_CATALOG
```

Or pass explicit paths on the command line:

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

The sidecar Dockerfile allows running CLI commands after the service starts:

```dockerfile
CMD ["uvicorn", "sidecars.model_catalog.app.main:app", "--host", "0.0.0.0", "--port", "8314"]
```

To run a CLI command, override the CMD:

```bash
docker run -it model-catalog python -m sidecars.model_catalog cleanup reset-all --execute
```

Or use `docker exec` on a running container:

```bash
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all --execute
```

### Configuration Loading

The CLI uses the same `load_settings()` function as the FastAPI app, so it respects all environment variables and `.env` file settings. This ensures consistency between CLI and runtime configurations.

---

## See Also

- [LOCAL-MODEL-STORAGE-AND-NAMING-DESIGN.md](LOCAL-MODEL-STORAGE-AND-NAMING-DESIGN.md) — Asset storage and folder naming
- [MAINTENANCE-NORMALIZE-MODEL-FOLDERS.md](MAINTENANCE-NORMALIZE-MODEL-FOLDERS.md) — One-time folder normalization utility
- [Persistence And Backup Strategy](persistence-and-backup-strategy.md) — Backup/restore runbook
- [Model Catalog Sidecar README](../../sidecars/model_catalog/README.md) — Sidecar deployment and configuration
