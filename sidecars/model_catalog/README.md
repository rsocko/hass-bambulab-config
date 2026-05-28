# Model Catalog Sidecar

Canonical docs: docs/features/model_catalog/README.md
Documentation policy: this README is implementation-adjacent and local to the sidecar; canonical cross-feature/reference docs live under `docs/features/model_catalog/`.

**Phase 1.1**: Standalone sidecar stack with local model authority.

Current scope:

- FastAPI service scaffold with local SQLite authority
- Standalone Docker Compose stack
- Local model CRUD + asset management (Phase 1.1)
- Bind-mount file storage for host visibility
- Health, config, and diagnostics endpoints
- Archive-link read contract endpoint for HA/print_history integration

Endpoint authority mode:

- `local` - local SQLite authority for `/api/models` and `/api/models/search`

## Module Architecture

After Phase 2 refactoring (#1207-#1211), the architecture follows a clean layered design with clear bounded contexts and minimal cross-module dependencies.

**Phase 2 Status**: ✅ COMPLETE (intake, models, db contexts split; working context in progress)

### App Factory (`main.py` — 65 lines)

Responsibilities: FastAPI app creation, lifespan (AppState init/teardown), CORS middleware, router registration. Contains **zero** endpoint handlers.

### Routers (`app/routers/`)

| Router | Endpoints | Purpose |
|--------|-----------|---------|
| `system.py` | 8 | Health, config, diagnostics, OpenAPI, schema export |
| `source_filesystems.py` | 3 | Server-side filesystem browse for intake/working roots |
| `archive_links.py` | 8 | Archive↔model linking CRUD, candidate discovery, review |
| `intake.py` | 4 | **Publishing & adapters** (Queue/Verification/Cleanup moved to Phase 2.1) |
| `intake_queue.py` | 6 | **[NEW]** Queue CRUD, status transitions, audit logging |
| `intake_verification.py` | 4 | **[NEW]** Entry validation, source verification, dedup detection |
| `intake_cleanup.py` | 2 | **[NEW]** Post-upload source cleanup, staging management |
| `models.py` | 4 | **Local model authority CRUD** (Search/Detail/Media moved to Phase 2.2) |
| `models_search.py` | 3 | **[NEW]** Search, filtering, ranking, related models |
| `moatabase Layer (`app/db*.py`) — Organized by Bounded Context

| Module | Purpose |
|--------|---------|
| `db.py` | **Connection factory + common utilities** (rewritten as part of Phase 2.3) |
| `db_migrations.py` | **Schema initialization and versioning** (centralized) |
| `db_intake.py` | **Intake context**: Upload queue, validation state |
| `db_models.py` | **Models context**: Catalog entries, assets, custom fields |
| `db_working.py` | **Working files context marker** (legacy working_groups/items tables dropped in PR E.1) |
| `db_archive_links.py` | **Archive context**: Model↔archive relationships |
| `db_common.py` | **Shared patterns**: Common schema, queries |

### Domain Modules (`app/`)

| Module | Purpose |
|--------|---------|
| `local_models.py` | Local model + asset CRUD (filesystem + SQLite) |
| `model_statistics.py` | Print statistics aggregation and ranking |
| `geometry_3mf.py` | 3MF geometry extraction for 3D viewer |
| `archive_linking.py` | Archive-link candidate matching and scoring |
| `model_export.py` | Model data export and serialization |
| `build_volume_helper.py` | Build volume detection and plate layout |
| `_helpers.py` | Shared path, timestamp, and validation utilities |
| `settings.py` | Pydantic settings from environment variables |
| `models.py` | Pydantic data models (LocalModelEntry) |
| `state.py`g.py` | 563 | Archive-link candidate matching and scoring |
| `model_export.py` | 551 | Model data export and serialization |
| `build_volume_helper.py` | 453 | Build volume detection and plate layout |
| `_helpers.py` | 228 | Shared path, timestamp, and validation utilities |
| `settings.py` | 98 | Pydantic settings from environment variables |
| `models.py` | 55 | Pydantic data models (LocalModelEntry) |
| `state.py` | 15 | AppState dataclass |

### Services (`app/services/`) — Business Logic & Workflows

| Module | Purpose |
|--------|---------|
| `intake_service.py` | Intake dedup detection, hash collection |
| `model_detail_service.py` | Detail enrichment logic, field management |
| `shared_helpers.py` | Shared utilities (slugify, hash, serialize) |
| **Planned Phase 2.1**: `intake_queue_service.py`, `intake_verification_service.py`, `intake_cleanup_service.py` |
| **Planned Phase 2.2**: `model_search_service.py`, `model_media_service.py` |
| **Phase 2.4 (working_groups_service): DROPPED** — working_groups tables removed in PR E.1 (filesystem-only browser remains) |

## Quick Start

```bash
# 1. Create .env from template
cp .env.example .env

# Edit .env and set ASSETS_ROOT_HOST to your local path:
# ASSETS_ROOT_HOST=/mnt/c/OneDrive/Documents/3D Models

# 2. Ensure traefik network exists
docker network create traefik || true

# 3. Start the independent stack
docker compose up -d

# 4. Verify health
curl http://localhost:8314/healthz
```

See **Deployment** section below for detailed options.

## CLI Commands

The repository includes a Click CLI for maintenance operations, but the current deployed container image only copies `/app/app` and does not include the `sidecars.model_catalog` CLI package. Use the host-side `docker exec` Python snippet below with the current image. The `python -m sidecars.model_catalog ...` commands remain valid only after rebuilding the image to include the CLI package.

Current deployed image reset command:

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
	"model_catalog_events",
	"model_catalog_links",
	"model_catalog_model_ranking",
	"model_summary_cache",
	"model_catalog_entries",
]

db_path = Path(os.getenv("MODEL_CATALOG_DB_PATH", "/data/model_catalog.db"))
curated_root = Path(os.getenv("MODEL_CATALOG_CURATED_ASSETS_ROOT", "/assets/Model Catalog"))
working_root = Path(os.getenv("MODEL_CATALOG_WORKING_FILES_ROOT", "/assets/Model Working Files"))
inbox_root = Path((os.getenv("MODEL_CATALOG_INTAKE_ROOTS", "/assets/Model Inbox").split(",")[0]).strip())

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
				continue
			conn.execute(f"DELETE FROM {table}")
		conn.commit()
		conn.execute("VACUUM")
	finally:
		conn.close()

for root in [curated_root, working_root, inbox_root]:
	if not root.exists():
		continue
	for child in root.iterdir():
		if child.is_dir():
			shutil.rmtree(child)
		else:
			child.unlink()
PY
```

After rebuilding the image to include the CLI package, these commands work:

```bash
# Show available commands
docker exec model-catalog python -m sidecars.model_catalog cleanup --help

# Dry-run: see what would be reset
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all

# Reset database only
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-db --execute

# Reset database and filesystem zones
docker exec model-catalog python -m sidecars.model_catalog cleanup reset-all --execute

# Advanced granular cleanup (specific tables/zones)
docker exec model-catalog python -m sidecars.model_catalog cleanup cleanup --scope db --tables model_catalog_entries

# Show prod/test DB profile status and schema versions
docker exec model-catalog python -m sidecars.model_catalog db-profiles status

# Seed test DB from current prod DB (fails if test DB exists)
docker exec model-catalog python -m sidecars.model_catalog db-profiles seed-test-from-prod

# Force reseed test DB from prod
docker exec model-catalog python -m sidecars.model_catalog db-profiles seed-test-from-prod --force

# Apply latest schema migrations to both prod and test DBs
docker exec model-catalog python -m sidecars.model_catalog db-profiles sync-schema
```

Until that rebuild happens, do not use the `python -m sidecars.model_catalog ...` examples against the running `model-catalog` container.

See [MAINTENANCE-CLEANUP-AND-RESET.md](../../docs/features/model_catalog/MAINTENANCE-CLEANUP-AND-RESET.md) for complete documentation.

## Build An Image Locally

Build from the repository root:

```bash
docker build \
	-f sidecars/model_catalog/Dockerfile \
	-t registry.socko.us/model-catalog:0.1.0 \
	.
```

## Push To Local Registry

```bash
docker push registry.socko.us/model-catalog:0.1.0
```

After that, Dockhand can deploy from the registry image without building from source.

Repository workflow:

- `.github/workflows/build-model-catalog-sidecar.yml`

Default workflow registry:

- `registry.socko.us/model-catalog`

Workflow tag resolution:

- `version_mode=explicit` uses the exact `image_tag` you provide
- `version_mode=next_patch` inspects the registry, finds the latest semantic tag, and increments patch
- `version_mode=next_minor` inspects the registry, finds the latest semantic tag, and increments minor
- `version_mode=next_major` inspects the registry, finds the latest semantic tag, and increments major

The workflow writes a copy-ready version block into the GitHub Actions run summary:

- resolved tag
- full image reference
- `.env` line for compose such as `MODEL_CATALOG_IMAGE_TAG=0.1.0`
- optional `.env` line for compose as `MODEL_CATALOG_IMAGE_TAG=latest` when `push_latest=true`

## Compose Tag Management

The example compose file uses an environment variable for the image tag:

```yaml
image: registry.socko.us/model-catalog:${MODEL_CATALOG_IMAGE_TAG:-0.1.0}
```

Recommended update flow:

1. run the workflow
2. copy the `MODEL_CATALOG_IMAGE_TAG=...` line from the run summary
3. paste it into the stack `.env`
4. run `docker compose pull && docker compose up -d`

If you want to stop updating the stack `.env` for every release, run the workflow with `push_latest=true` and set the compose tag to `latest` once:

```text
MODEL_CATALOG_IMAGE_TAG=latest
```

That gives Dockhand a stable image reference to pull and recreate on demand, while the workflow still publishes the immutable semantic tag for rollback.

Suggested `.env` entries:

```text
ASSETS_ROOT_HOST=/mnt/c/OneDrive/Documents/3D Models
MODEL_CATALOG_IMAGE_TAG=0.1.0
MODEL_CATALOG_HOSTNAME=model-catalog.socko.us
MODEL_CATALOG_AUTHORITY_MODE=local
MODEL_CATALOG_DB_PROFILE=prod
MODEL_CATALOG_DB_PATH=/data/model_catalog.db
MODEL_CATALOG_DB_PATH_TEST=/data/model_catalog_test.db
MODEL_CATALOG_DB_BOOTSTRAP_ALL_PROFILES=true
MODEL_CATALOG_DB_SEED_TEST_FROM_PROD_ON_START=false
MODEL_CATALOG_DB_SEED_TEST_OVERWRITE=false
MODEL_CATALOG_CURATED_ASSETS_ROOT=/assets/Model Catalog
MODEL_CATALOG_INTAKE_ROOTS=/assets/Model Inbox
MODEL_CATALOG_WORKING_FILES_ROOT=/assets/Model Working Files
MODEL_CATALOG_MAKERWORLD_API_BASE_URL=https://api.bambulab.com/v1
MODEL_CATALOG_MAKERWORLD_AUTH_TOKEN=
MODEL_CATALOG_MAKERWORLD_METADATA_TIMEOUT_SECONDS=10
MODEL_CATALOG_MAKERWORLD_DOWNLOAD_TIMEOUT_SECONDS=60
MODEL_CATALOG_MAKERWORLD_RATE_LIMIT_QPS=2.0
```

See `.env.example` for complete template with detailed comments on each option.

MakerWorld note:

- `MODEL_CATALOG_MAKERWORLD_AUTH_TOKEN` is required for authenticated MakerWorld resolve/download flows.
- If it is unset, source capture still succeeds but degrades to `link_only` with `makerworld_auth_unavailable`.
- Set the real token only in the host stack `.env`, then redeploy `model-catalog` with `docker compose up -d model-catalog`.

## Deployment Tiers & Storage

### Independent Stack Deployment (Phase 1.1+)

The sidecar now runs as a standalone Docker stack with independent file storage:

- **Named Volume** (`/data`): Sidecar-owned SQLite database + ephemeral cache
- **Bind Mount** (`/assets`): Host-visible model files (OneDrive, local, NAS)
- **Standalone**: No external service dependencies

### Intake Queue Runtime Storage

Remote-client browser uploads do not write directly into `/assets`.

- Browser-uploaded files are staged under the parent folder of the active DB path (`MODEL_CATALOG_DB_PATH`, or profile-resolved prod/test path).
- With the default standalone compose (`MODEL_CATALOG_DB_PATH=/data/model_catalog.db`), the queue lives at `/data/intake_browser_uploads`.
- That means the existing `model_catalog_data` volume is the durable runtime store for:
	- `model_catalog.db`
	- `intake_browser_uploads/` browser-upload staging files
	- retry and cleanup state tied to queued uploads
- Size `/data` for your largest expected remote upload batches, not just for the SQLite file.
- Do not place `/data` on a read-only mount if browser-upload intake must work.

Operational recommendation:

- treat `/data` as the queue volume for remote-client intake
- back it up together with the SQLite database when queue continuity matters
- clear stale queue files only after confirming no active `queued`, `uploading`, or `cleanup_failed` items remain

Example runtime expectation:

```yaml
services:
	model-catalog:
		environment:
			MODEL_CATALOG_DB_PROFILE: prod
			MODEL_CATALOG_DB_PATH: /data/model_catalog.db
			MODEL_CATALOG_DB_PATH_TEST: /data/model_catalog_test.db
		volumes:
			- model_catalog_data:/data
			- /srv/3d-models:/assets
```

In that layout:

- browser uploads stage in `/data/intake_browser_uploads`
- server-browse selections resolve from `/assets/...`
- local publish can copy reviewed files from queue or server roots into sidecar-owned asset storage

Runtime path roles are split deliberately:

- `MODEL_CATALOG_CURATED_ASSETS_ROOT` controls sidecar-owned published storage.
- `MODEL_CATALOG_INTAKE_ROOTS` controls intake browse/select and intake cleanup scope.
- `MODEL_CATALOG_WORKING_FILES_ROOT` controls Working Files explorer, reindex, and reorganize destination.

These values must use container-visible paths, not host-native paths.

```text
MODEL_CATALOG_CURATED_ASSETS_ROOT=/assets/Model Catalog
MODEL_CATALOG_INTAKE_ROOTS=/assets/Model Inbox
MODEL_CATALOG_WORKING_FILES_ROOT=/assets/Model Working Files
```

Use this when curated storage, intake, and working files have distinct folders under the shared `/assets` mount.

```text
MODEL_CATALOG_INTAKE_ROOTS=/assets/Model Inbox,/assets/imported/remotes
```

Use this when intake browse should include additional staging areas without widening the working-files root.

Host-path mapping reminder:

- host bind mount: `D:\Model Library:/assets`
- intake/working/curated values: `/assets/...`
- not allowed in `MODEL_CATALOG_INTAKE_ROOTS` or `MODEL_CATALOG_WORKING_FILES_ROOT`: `D:\Model Library`

**File Organization in `/assets`**:
    - all local model files, assets, and photos are stored in `/assets/Model Catalog` (host-visible)
├── working/         # Active projects (Phase 1.5+)
├── inbox/           # Temporary staging (Phase 1.5+)
└── imported/        # External imports (Phase 2+)
```
```bash
# Create traefik network (shared reverse proxy network)
docker network create traefik

# Service joins the shared traefik network.
```


### Local Model Catalog Storage (`/assets/Model Catalog`)

All local model files, assets, and photos are stored in `/assets/Model Catalog` (host-visible and navigable).

**File Organization**:
```
/assets/Model Catalog/
├── model-id-1/
│   ├── model.3mf                 # Primary model file
│   ├── preview.jpg               # Preview image
│   ├── photo-abc123.jpg          # Uploaded photos
│   ├── photo-def456.jpg
│   └── extracted/                # Optional: extracted assets from 3MF files
│       ├── layer-preview.png
│       └── thumbnail.jpg
├── model-id-2/
│   ├── assembly.3mf
│   ├── preview.png
│   └── documentation.pdf
└── ...
```

**Key characteristics**:
- Each model's files are isolated in a folder named by `local_model_id`
- All files are stored at root level in that folder (flattened, not nested by type)
- Optional `extracted/` subdirectory for assets extracted from 3MF files
- Metadata (thumbnails, geometry) is still tracked in SQLite
- Storage paths are relative and stored in `model_catalog_assets` table

**Backup recommendation**:
- Back up `/assets/Model Catalog` alongside the database for atomic recovery
- This directory is host-visible, so standard file-based backups work directly

### Other Folder Organization in `/assets`
```
/assets/
├── Model Catalog/       # Local models (all assets, photos, files)
├── working/             # Active working groups (Phase 1.5+)
├── inbox/               # Temporary staging for intake (Phase 1.5+)
└── imported/            # External imports (Phase 2+)
```
### File Storage Architecture

See **detailed documentation**:
- [storage-architecture-and-file-organization.md](../../docs/features/model_catalog/storage-architecture-and-file-organization.md)
- [persistence-and-backup-strategy.md](../../docs/features/model_catalog/persistence-and-backup-strategy.md)

Topics covered:
- Bind mount vs named volume tradeoffs
- Backup automation (SQLite + file-level)
- Restore procedures
- OneDrive / NAS / local disk deployment options
- Inbox/working/catalog/imported tier organization

## Environment Variables

- `MODEL_CATALOG_DB_PROFILE` — active database profile (`prod` or `test`)
- `MODEL_CATALOG_DB_PATH` — SQLite path used for production profile (base path)
- `MODEL_CATALOG_DB_PATH_TEST` — SQLite path used for test/dev profile
- `MODEL_CATALOG_DB_BOOTSTRAP_ALL_PROFILES` — when `true`, startup migrations run for both prod and test DBs
- `MODEL_CATALOG_DB_SEED_TEST_FROM_PROD_ON_START` — when `true`, startup copies prod DB into test DB before bootstrapping
- `MODEL_CATALOG_DB_SEED_TEST_OVERWRITE` — when `true`, startup seed may overwrite an existing test DB
- `MODEL_CATALOG_HOST` — local bind host for manual `uvicorn` runs
- `MODEL_CATALOG_PORT` — local bind port for manual `uvicorn` runs
- `MODEL_CATALOG_CURATED_ASSETS_ROOT` — sidecar-controlled published asset root for curated local storage
- `MODEL_CATALOG_CURATED_ASSETS_ROOT_TEST` — optional test-profile curated root override
- `MODEL_CATALOG_INTAKE_ROOTS` — comma-separated container paths allowed for intake browse/select and intake cleanup
- `MODEL_CATALOG_INTAKE_ROOTS_TEST` — optional test-profile intake roots override for strict prod/test separation
- `MODEL_CATALOG_WORKING_FILES_ROOT` — container path used by Working Files explorer, reindex, and reorganize destination
- `MODEL_CATALOG_WORKING_FILES_ROOT_TEST` — optional test-profile working root override for strict prod/test separation
- `MODEL_CATALOG_MAKERWORLD_API_BASE_URL` — MakerWorld API base URL used for external source resolve/download
- `MODEL_CATALOG_MAKERWORLD_AUTH_TOKEN` — Bambu Cloud Bearer token for authenticated MakerWorld requests
- `MODEL_CATALOG_MAKERWORLD_METADATA_TIMEOUT_SECONDS` — timeout for MakerWorld metadata/resolve requests
- `MODEL_CATALOG_MAKERWORLD_DOWNLOAD_TIMEOUT_SECONDS` — timeout for MakerWorld binary downloads
- `MODEL_CATALOG_MAKERWORLD_RATE_LIMIT_QPS` — per-process MakerWorld request throttle target
- `MODEL_CATALOG_IMAGE_TAG` — image tag emitted by `/config` and `/diagnostics` (injected at build time)
- `MODEL_CATALOG_IMAGE_VERSION` — semantic image version emitted by `/config` and `/diagnostics` (injected at build time)
- `MODEL_CATALOG_IMAGE_REVISION` — source commit SHA emitted by `/config` and `/diagnostics` (injected at build time)
- `MODEL_CATALOG_IMAGE_CREATED` — image build timestamp emitted by `/config` and `/diagnostics` (injected at build time)



## Run Locally

```powershell
& "c:\dev\hass-bambulab-config\.venv\Scripts\python.exe" -m uvicorn sidecars.model_catalog.app.main:app --host 127.0.0.1 --port 8314
```

## Health Check

```bash
curl http://127.0.0.1:8314/healthz
```

## Optional Debug Tooling

The stack now includes three always-on diagnostics services alongside the main API:

- `model-catalog-datasette` - read-only SQLite browser for table inspection,
	schema browsing, exports, and ad-hoc `SELECT` queries
- `model-catalog-sqlite-web` - read-only SQLite visualizer with structure,
	indexes, foreign-key browsing, and richer table/query navigation
- `model-catalog-chartdb` - self-hosted ERD editor for importing the SQLite
	schema and producing diagrams or migration drafts

Practical commands:

```bash
# Start the full stack, including Datasette, sqlite-web, and ChartDB
docker compose up -d

# Open Datasette via Traefik
http://model-catalog-datasette.socko.us

# Open sqlite-web via Traefik
http://model-catalog-sqlite-web.socko.us

# Open ChartDB via Traefik
http://model-catalog-chartdb.socko.us
```

Notes:

- Datasette mounts the sidecar SQLite volume read-only and opens the database in
	immutable mode, so it is appropriate for diagnostics and ad-hoc read queries.
- sqlite-web also mounts the same volume read-only, so it is safe for schema and
	query exploration without bypassing application workflows.
- ChartDB is a self-hosted diagramming UI, not a direct SQLite file browser. For
	SQLite, use ChartDB's SQLite import flow, run its generated schema query inside
	Datasette or sqlite-web against `model_catalog.db`, then paste the result back
	into ChartDB to build the ERD.
- A generic writable DB UI is still not recommended for normal operations,
	because app-level workflows maintain additional invariants and audit events.

## Live Smoke Validation

For a non-destructive smoke check against the deployed sidecar:

```powershell
& "c:\Users\rysock\AppData\Local\Python\pythoncore-3.14-64\python.exe" \
	"c:\dev\hass-bambulab-config\tools\model_catalog\validate_live_sidecar_smoke.py" \
	--base-url "http://model-catalog.socko.us"
```

This validates the live health/config/diagnostics/openapi endpoints plus the safe intake queue read and validation paths without creating or mutating data.

For issue #1160 local-authority API cutover validation (creates a temporary local model, validates browse/search/detail/update behavior, then hard-deletes it):

```powershell
& "c:\Users\rysock\AppData\Local\Python\pythoncore-3.14-64\python.exe" \
	"c:\dev\hass-bambulab-config\tools\model_catalog\validate_live_issue1160_cutover.py" \
	--base-url "http://model-catalog.socko.us"
```

## API Docs Landing

When the sidecar is running, these API docs endpoints are available:

- `GET /` - docs landing page
- `GET /docs` - Swagger UI
- `GET /redoc` - ReDoc
- `GET /openapi.json` - OpenAPI schema

Repository references:

- `docs/features/model_catalog/api-reference.md`
- `docs/features/print_history/api-reference.md`

## Archive Link DTO Contract (Phase 1)

Phase 1 now includes an initial archive-facing read contract endpoint that avoids shared DB reads across features.

Endpoint:

```text
GET /api/archive-links/{archive_id}
```

Query params:

- `include_inactive` (optional, default `false`)

Response highlights:

- `contract`: currently `archive-link.v1alpha1`
- `archive_id`: requested Bambuddy archive ID
- `link`: current active link summary or `null`
- `links`: returned link rows (active only by default)
- `meta.count`: number of returned rows

Example:

```bash
curl "http://127.0.0.1:8314/api/archive-links/4812?include_inactive=true"
```

## Archive Link Workflow Endpoints (Phase 2)

Phase 2 extends archive-link support with CRUD and candidate review endpoints. The shipped baseline is popup-focused linkage and review; richer heuristic candidate discovery and queue/backlog behavior remain later-phase work.

CRUD:

- `POST /api/archive-links/{archive_id}`
- `PATCH /api/archive-links/{archive_id}/{link_id}`
- `POST /api/archive-links/{archive_id}/{link_id}/deactivate`

Candidate workflow:

- `POST /api/archive-links/{archive_id}/candidates/refresh`
- `POST /api/archive-links/{archive_id}/{link_id}/accept`
- `POST /api/archive-links/{archive_id}/{link_id}/reject`

Cleanup workflow:

- `POST /api/archive-links/{archive_id}/cleanup-duplicates`

Candidate refresh request payload:

- `archive_name` (required)
- `min_score` (optional, default `0.3`)
- `max_candidates` (optional, default `10`)
- `force_refresh_model_cache` (optional, default `false`)

Candidate review states currently used:

- `new`
- `accepted`
- `rejected`
- `expired`
