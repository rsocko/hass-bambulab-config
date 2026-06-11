# Model Catalog Storage Architecture & File Organization

> **Status**: Phase 1.1 design + Phase 1.5/2 roadmap  
> **Last updated**: 2026-04-29  
> **Scope**: Independent sidecar stack file storage, asset organization tiers, bind-mount vs named volume strategy

## Overview

The model catalog sidecar now manages its own file storage independently of Manyfold. This document defines:

1. **Physical storage layers** (named volume vs bind mount)
2. **Logical file organization tiers** (inbox → working → catalog → archive)
3. **Database schema** for asset tracking
4. **Backup/restore procedures** for both layers
5. **Deployment options** (standalone, host-mounted, NAS-backed, etc.)

---

## Physical Storage Layers

### Layer 1: Named Volume (`/data`) — Database & Cache

**Purpose**: Sidecar-owned, opaque to host  
**Owner**: Docker (sidecar container)  
**Backup Strategy**: Point-in-time DB snapshots  
**Restore**: Docker volume recovery + DB restoration

**Contents**:
```
/data/
├── model_catalog.db              # SQLite database (PRIMARY DURABLE STATE)
├── cache/
│   ├── geometry_analysis/        # Parsed 3MF geometry (ephemeral)
│   ├── preview_thumbnails/       # Generated previews (ephemeral)
│   └── metadata_cache/           # Cached API responses (ephemeral)
└── staging/                      # Internal temp workspace
```

**Properties**:
- **Size**: Small (MB - tens of MB for typical deployments)
- **Durability**: Primary state; requires backup
- **Recovery**: DB restore + re-scan of asset files
- **Host visibility**: None (opaque Docker volume)
- **Frequency**: Backed up on scheduled interval (daily/weekly)

### Layer 2: Bind Mount (`/assets`) — Model Files & Projects

**Purpose**: Host-visible model library  
**Owner**: Host filesystem (user responsibility)  
**Backup Strategy**: Host-level backup, continuous sync if cloud-backed  
**Restore**: File restore + metadata rescan

**Contents**:
```
/assets/
├── Model Catalog/                # Catalog models (local authority, Phase 1.1+)
│   └── {model_id}/
│       ├── model.3mf
│       ├── preview.jpg
│       └── metadata.json         # Optional metadata
│
├── Model Working Files/          # Working groups (Phase 1.5+)
│   └── {working_group_id}/
│       ├── model.3mf
│       ├── variant_1.3mf
│       ├── texture.png
│       └── notes.txt
│
├── Model Inbox/                  # Temporary staging (Phase 1.5+)
│   └── {session_id}/
│       ├── upload_1.3mf          # Uploaded file (TTL 1-2 hours)
│       ├── upload_2.3mf
│       └── session_metadata.json
│
└── Imported/                     # Imported models (Phase 2+)
    └── {source}/
        └── {model_id}/
            ├── model.3mf         # Copied from Manyfold or external
            └── source_url.txt    # Provenance
```

**Properties**:
- **Size**: Large (GB - as many models as you have)
- **Durability**: Host-visible; benefits from host backup tools
- **Recovery**: File restore + sidecar metadata rescan
- **Host visibility**: Full (user can browse, edit, organize)
- **Frequency**: Continuous or snapshot-based depending on host setup

---

## Logical File Organization Tiers

### Tier 1: Model Inbox (Temporary Staging)

**Path**: `/assets/Model Inbox/{session_id}/`
**Lifetime**: 1-2 hours (TTL-based cleanup)  
**Owner**: Sidecar  
**Phase**: 1.5+ (bulk import/discovery)

**Purpose**:
- Receive uploaded files from bulk import or HA file picker
- Stage files before review and grouping
- Deduplicate against existing working/catalog
- Deduplicate against existing Model Working Files/Model Catalog
- Preview extraction and metadata discovery

**Workflow**:
1. User uploads files → sidecar creates session in `/assets/inbox/{session_id}/`
2. Sidecar extracts preview images, detects duplicates, suggests grouping
3. User reviews in HA UI (bulk import card)
4. User approves → files moved to `/assets/working/`
5. TTL cleanup removes unapproved inbox after N hours

**Database Entry**:
```python
model_catalog_entries:
  storage_tier: 'inbox'
  storage_path: 'Model Inbox/{session_id}/upload.3mf'
  inbox_status: 'pending' | 'approved' | 'rejected'
  inbox_expires_at: datetime
```

### Tier 2: Model Working Files (Active Projects)

**Path**: `/assets/Model Working Files/{working_group_id}/`
**Lifetime**: Until published or deleted  
**Owner**: Sidecar + User (collaborative editing)  
**Phase**: 1.5+ (working group management)

**Purpose**:
- Group related files in a project or variant series
- Support active editing and experimentation
- Not yet stable enough to commit to catalog
- Can contain multiple formats (.3mf, .stl, .obj) and supporting files

**Workflow**:
1. Create working group from inbox or fresh upload
2. User edits files via sidecar upload UI or host filesystem
3. Sidecar indexes files, tracks changes
4. User can print from working group, collect results via Bambuddy
5. When stable, publish to catalog (move to `/assets/catalog/`)

**Database Entry**:
```python
model_catalog_entries:
  storage_tier: 'working'
  storage_path: 'Model Working Files/{working_group_id}/primary.3mf'
  working_group_id: str
  working_status: 'draft' | 'ready_for_review' | 'printing'
```

### Tier 3: Model Catalog (Published & Stable)

**Path**: `/assets/Model Catalog/{model_id}/`
**Lifetime**: Long-term (until deleted)  
**Owner**: Sidecar (managed)  
**Phase**: 1.1+ (local model authority)

**Purpose**:
- Stable, reusable source models created or curated locally
- Curated metadata and previews
- Can be linked to multiple archives
- Subject to curation and versioning

**Workflow**:
1. Create new model directly in catalog or promote from working
2. Version control via metadata fields
3. Can be referenced by multiple print archives
4. Can be re-printed with version history

**Delete behavior**:
- Catalog UI delete actions use the local-model API default soft delete (`DELETE /api/local/models/{local_model_id}?hard_delete=false`).
- Soft delete sets `deleted_at` and removes the model from active catalog/search views. It does not set `archived_at`; archived remains the separate hide/retire state.
- Deleted models are kept indefinitely by default. There is no automatic emptying/retention purge unless a future retention policy is explicitly enabled.
- The browser card exposes a Deleted view. Deleted models can be restored with `POST /api/local/models/{local_model_id}/restore`, which clears `deleted_at` and returns the model to active catalog views.
- Deleted models can be permanently purged with `DELETE /api/local/models/{local_model_id}/purge`. Purge removes the DB model row, asset rows, collection memberships, and local files under the configured Model Catalog asset root.
- Multi-select delete and purge are gated behind two confirmations: a destructive-action confirmation and a typed prompt (`DELETE` for moving to Deleted, `PURGE` for permanent purge), matching the Print History bulk delete guard pattern.
- Linked print archives are not deleted by model deletion.

**Database Entry**:
```python
model_catalog_entries:
  storage_tier: 'catalog'
  storage_path: 'Model Catalog/{model_id}/model.3mf'
  published_at: datetime
  version: str
  is_featured: bool
```

### Tier 4: Imported (External Sources)

**Path**: `/assets/Imported/{source}/{model_id}/`
**Lifetime**: Long-term (until deleted)  
**Owner**: Sidecar (managed)  
**Phase**: 2+ (Manyfold integration + external imports)

**Purpose**:
- Models copied from Manyfold library
- Models imported from external sources (Makerworld, Printables, etc.)
- Maintain provenance and source URL
- Avoid re-downloading duplicates

**Workflow**:
1. User requests import from Manyfold or external URL
2. Sidecar copies/downloads to `/assets/imported/{source}/{model_id}/`
3. Deduplication prevents duplicate storage
4. Provenance stored as metadata + source_url.txt file

**Database Entry**:
```python
model_catalog_entries:
  storage_tier: 'imported'
  storage_path: 'Imported/{source}/{model_id}/model.3mf'
  source_platform: 'manyfold' | 'makerworld' | 'printables' | 'url'
  source_url: str
  imported_from_id: str  # Original Manyfold ID, Makerworld ID, etc.
```

### Tier 5: Archive-Linked (Print History)

**Path**: N/A (linked, not stored)  
**Stored in**: Bambuddy archive storage  
**Owner**: Bambuddy (print-specific)  
**Phase**: 2+ (print history + archive linking)

**Purpose**:
- Reference to the exact model file used for a specific print
- Separate from source project files
- Part of print outcome, not library

**Not stored in this sidecar** — this is Bambuddy's responsibility  
See [source-3mf-storage-strategy.md](../../print_history/design/imports/source-3mf-storage-strategy.md)

---

## Database Schema Extensions

### `model_catalog_entries` (Existing) + New Fields

```sql
ALTER TABLE model_catalog_entries ADD COLUMN (
  storage_tier TEXT DEFAULT 'catalog',            -- Tier: catalog | working | inbox | imported
  storage_location TEXT DEFAULT 'onedrive_bind',  -- Physical location: onedrive_bind | sidecar_volume | external
  storage_path TEXT NOT NULL,                     -- Relative path within tier (e.g., 'catalog/uuid-123/model.3mf')
  absolute_storage_path TEXT VIRTUAL GENERATED
    AS (CASE 
      WHEN storage_location = 'onedrive_bind' THEN CONCAT('/assets/', storage_path)
      WHEN storage_location = 'sidecar_volume' THEN CONCAT('/data/files/', storage_path)
      ELSE storage_path
    END),
  
  -- Tier-specific metadata
  inbox_status TEXT,                  -- 'pending' | 'approved' | 'rejected' (for inbox tier)
  inbox_expires_at DATETIME,          -- TTL for inbox files
  
  working_group_id TEXT,              -- Reference to working group (for working tier)
  working_status TEXT,                -- 'draft' | 'ready_for_review' | 'printing'
  
  published_at DATETIME,              -- When published to catalog (for catalog tier)
  version TEXT,                       -- Version identifier (for catalog tier)
  is_featured BOOLEAN DEFAULT FALSE   -- Featured in UI (for catalog tier),
  
  source_platform TEXT,               -- 'manyfold' | 'makerworld' | 'printables' | etc. (for imported tier)
  source_url TEXT,                    -- Original URL (for imported tier)
  imported_from_id TEXT,              -- Original ID in source system (for imported tier)
  imported_at DATETIME,               -- When imported (for imported tier)
  
  -- Common metadata
  last_accessed_at DATETIME,          -- Track usage
  access_count INT DEFAULT 0,         -- Usage tracking for UI sorting
  is_favorite BOOLEAN DEFAULT FALSE,  -- User favoriting
  notes TEXT                          -- User notes per model
);
```

### `model_catalog_assets` (Existing) — No Changes

Already tracks files with `storage_path` and `asset_type`.

---

## Deployment Options

### Option 1: OneDrive Bind Mount (Default Recommended)

**Configuration**:
```yaml
volumes:
  - /mnt/c/OneDrive/Documents/3D Models:/assets  # Windows + OneDrive
  - model_catalog_data:/data
```

**`.env`**:
```
ASSETS_ROOT_HOST=/mnt/c/OneDrive/Documents/3D Models
```

**Advantages**:
- ✅ Files synchronized to cloud automatically
- ✅ Backup-friendly (OneDrive provides redundancy)
- ✅ Host-visible for casual browsing/editing
- ✅ Works with existing homelab backup tools

**Disadvantages**:
- ⚠️ Windows path translation (Hyper-V, WSL2)
- ⚠️ Sync latency if online-only files are common
- ⚠️ Operator must manage quota

**Backup**:
- OneDrive sync provides continuous backup
- Additional local/NAS copy via restic/kopia recommended
- DB backup still separate (see below)

### Option 2: Local Disk Bind Mount

**Configuration**:
```yaml
volumes:
  - /mnt/d/ModelAssets:/assets  # Local D: drive
  - model_catalog_data:/data
```

**Advantages**:
- ✅ No network latency
- ✅ Simpler path handling
- ✅ Works well with local backup tools

**Disadvantages**:
- ❌ No cloud redundancy
- ❌ Depends on local storage health
- ⚠️ Requires separate backup strategy

**Backup**:
- Set up host-level backup (restic, kopia, native tools)
- DB backup still separate

### Option 3: NAS/Network Mount

**Configuration**:
```yaml
volumes:
  - /mnt/nas/models:/assets       # NAS share via NFS/SMB
  - model_catalog_data:/data
```

**Advantages**:
- ✅ Centralized storage
- ✅ Built-in NAS redundancy
- ✅ Shared across multiple devices

**Disadvantages**:
- ⚠️ Network latency for large file operations
- ⚠️ Permissions complexity (NFS uid/gid mapping)
- ⚠️ NAS backup is operator's responsibility

**Backup**:
- Use NAS native replication (RAID, snapshots)
- Plus additional off-NAS copy (restic, kopia)
- DB backup still separate

### Option 4: Pure Sidecar Volume (NOT Recommended)

**Configuration**:
```yaml
volumes:
  - model_catalog_data:/data
  - model_assets:/assets  # Also a named volume
```

**Advantages**:
- ✅ Completely Docker-managed
- ✅ No host path complexity

**Disadvantages**:
- ❌ Not visible from host (no browsing/editing)
- ❌ Requires Docker tooling to inspect
- ❌ Harder to integrate with existing backup
- ❌ Scales poorly (large model libraries)

**Not recommended** for this use case. Only use if you have a specific reason.

---

## Backup & Restore Procedures

### Strategy 1: OneDrive + Named Volume (Default)

**Backup flow**:

1. **Database** (daily):
   ```bash
   docker exec model-catalog-sidecar sqlite3 /data/model_catalog.db \
     ".backup '/backup/snapshots/model_catalog_$(date +%Y%m%d).db'"
   ```

2. **Assets** (continuous):
   - OneDrive sync provides redundancy automatically
   - Add periodic copy to local backup: `cp -r /mnt/c/OneDrive/Documents/3D\ Models /backup/assets/latest/`

3. **Retention**:
   - OneDrive keeps deleted files in recycle bin (30-93 days)
   - Local backup via restic/kopia: 2-week daily, 1-month weekly, 1-year monthly

**Restore flow**:

1. **Database restore**:
   ```bash
   docker stop model-catalog-sidecar
   docker run -v model_catalog_data:/data \
     -v /backup/snapshots:/backup \
     alpine:latest \
     sqlite3 /data/model_catalog.db \
       ".restore /backup/model_catalog_20260425.db"
   docker start model-catalog-sidecar
   ```

2. **Asset restore** (if needed):
   ```bash
   cp -r /backup/assets/latest/* /mnt/c/OneDrive/Documents/3D\ Models/
   # Sidecar rescans on next startup
   ```

### Strategy 2: Local Disk + restic Backup

**Backup flow**:

1. **Database snapshot** (hourly):
   ```bash
   BACKUP_DIR=/mnt/backup/model-catalog
   mkdir -p $BACKUP_DIR/snapshots
   docker exec model-catalog-sidecar sqlite3 /data/model_catalog.db \
     ".backup '$BACKUP_DIR/snapshots/model_catalog_$(date +%Y%m%d_%H%M%S).db'"
   ```

2. **Push to restic** (daily):
   ```bash
   restic backup \
     /mnt/d/ModelAssets \
     $BACKUP_DIR/snapshots
   ```

3. **Retention** (restic policy):
   - 7 daily snapshots
   - 4 weekly snapshots
   - 12 monthly snapshots

**Restore flow**:

```bash
# List available snapshots
restic snapshots

# Restore to date
restic restore <snapshot-id> --target /mnt/restore/

# Or restore latest
restic restore latest --target /mnt/restore/
```

---

## Deployment Checklist

- [ ] Ensure `ASSETS_ROOT_HOST` directory exists and is writable
- [ ] Ensure `traefik` Docker network exists
- [ ] If using Manyfold, verify OAuth credentials are set
- [ ] Create `.env` from `.env.example` with your paths
- [ ] Run `docker compose config` to validate YAML
- [ ] Start stack: `docker compose up -d`
- [ ] Verify `/assets` is mounted: `docker exec model-catalog-sidecar ls /assets`
- [ ] Create subdirs (auto-created on first use, or pre-create):
  ```bash
  mkdir -p /path/to/assets/{catalog,working,inbox,imported}
  ```
- [ ] Test database connectivity: `docker compose exec model-catalog-sidecar sqlite3 /data/model_catalog.db ".tables"`
- [ ] Verify API: `curl http://localhost:8314/healthz`

---

## Future Considerations (Phase 2+)

1. **Asset versioning**: Track file history per model
2. **Storage quotas**: Limit inbox and working tiers by size
3. **Garbage collection**: Auto-cleanup old inbox, failed imports
4. **Deduplication**: Cross-tier content-hash dedup (warn before deleting)
5. **Compression**: Optional ZSTD compression for archival tier
6. **Cold storage**: Archive old catalog items to separate slower storage

---

## References

- [persistence-and-backup-strategy.md](./backup-strategy.md) - Database backup details
- [operator-workflow.md](./operator-workflow.md) - User-facing file organization guidance
- [source-3mf-storage-strategy.md](../../print_history/design/imports/source-3mf-storage-strategy.md) - Print archive storage
