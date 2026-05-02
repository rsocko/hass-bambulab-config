# Model Catalog Sidecar

**Phase 1.1**: Independent sidecar stack with local model authority, independent of Manyfold.

Current scope:

- FastAPI service scaffold with local SQLite authority
- Independent Docker Compose stack (no Manyfold dependency)
- Local model CRUD + asset management (Phase 1.1)
- Optional Manyfold integration (graceful degradation)
- Bind-mount file storage for host visibility
- Health, config, and diagnostics endpoints
- Archive-link read contract endpoint for HA/print_history integration

Unified endpoint authority modes:

- `local` - local SQLite authority only for `/api/models` and `/api/models/search` (default for the standalone stack)
- `hybrid` - merge frozen Manyfold cache with local models for compatibility
- `manyfold` - legacy compatibility mode backed by Manyfold cache

## Module Architecture

After the #1190 modularization epic, `main.py` is a thin composition root. All endpoint logic lives in feature routers under `app/routers/`, supported by shared domain modules and a services layer.

### App Factory (`main.py` — 65 lines)

Responsibilities: FastAPI app creation, lifespan (AppState + ManyfoldClient init/teardown), CORS middleware, router registration. Contains **zero** endpoint handlers.

### Routers (`app/routers/`)

| Router | Endpoints | Lines | Scope |
|--------|-----------|-------|-------|
| `system.py` | 8 | 320 | Health, config, diagnostics, OpenAPI, schema export |
| `source_filesystems.py` | 3 | 417 | Server-side filesystem browse for intake/working roots |
| `archive_links.py` | 8 | 534 | Archive↔model linking CRUD, candidate discovery, review |
| `working.py` | 26 | 2,845 | Working files explorer, groups, reindex, reorganize |
| `intake.py` | 16 | 3,399 | Intake queue, browser/server upload, publish, cleanup |
| `models.py` | 31 | 3,547 | Model list/search/detail, local CRUD, fields, ranking, photos, geometry, file download, related models |

All routers access shared state via `request.app.state.model_catalog` (AppState) and `request.app.state.manyfold_client` (ManyfoldClient).

### Domain Modules (`app/`)

| Module | Lines | Purpose |
|--------|-------|---------|
| `db.py` | 1,638 | SQLite schema, migrations, all DB read/write functions |
| `manyfold.py` | 1,455 | Manyfold API client, OAuth, cache, session bridge |
| `local_models.py` | 604 | Local model + asset CRUD (filesystem + SQLite) |
| `model_statistics.py` | 586 | Print statistics aggregation and ranking |
| `geometry_3mf.py` | 572 | 3MF geometry extraction for 3D viewer |
| `archive_linking.py` | 563 | Archive-link candidate matching and scoring |
| `model_export.py` | 551 | Model data export and serialization |
| `build_volume_helper.py` | 453 | Build volume detection and plate layout |
| `_helpers.py` | 228 | Shared path, timestamp, and validation utilities |
| `settings.py` | 98 | Pydantic settings from environment variables |
| `models.py` | 55 | Pydantic data models (ManyfoldModelSummary, LocalModelEntry) |
| `state.py` | 15 | AppState dataclass |

### Services (`app/services/`)

| Module | Lines | Purpose |
|--------|-------|---------|
| `intake_service.py` | 169 | Intake dedup detection, hash collection |

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
MODEL_CATALOG_CURATED_ASSETS_ROOT=/assets/Model Catalog
MODEL_CATALOG_INTAKE_ROOTS=/assets/Model Inbox
MODEL_CATALOG_WORKING_FILES_ROOT=/assets/Model Working Files
MANYFOLD_BASE_URL=http://manyfold:3214
MANYFOLD_CLIENT_ID=
MANYFOLD_CLIENT_SECRET=
```

See `.env.example` for complete template with detailed comments on each option.

## Deployment Tiers & Storage

### Independent Stack Deployment (Phase 1.1+)

The sidecar now runs as a standalone Docker stack with independent file storage:

- **Named Volume** (`/data`): Sidecar-owned SQLite database + ephemeral cache
- **Bind Mount** (`/assets`): Host-visible model files (OneDrive, local, NAS)
- **No dependency on Manyfold**: Standalone or optional integration

### Intake Queue Runtime Storage

Remote-client browser uploads do not write directly into `/assets`.

- Browser-uploaded files are staged under the parent folder of `MODEL_CATALOG_DB_PATH`.
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
			MODEL_CATALOG_DB_PATH: /data/model_catalog.db
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
└── imported/            # External imports from Manyfold (Phase 2+)
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

## Dockhand / Manyfold Stack Compose (Legacy)

The repo now standardizes on the independent stack in `docker-compose.yml`.

If your live environment still has a model catalog service embedded in the Manyfold stack, remove that duplicate service during cutover so only the standalone model-catalog service owns `model-catalog.socko.us`.

## Environment Variables

- `MANYFOLD_BASE_URL` — base URL for the Manyfold instance
- `MANYFOLD_MODELS_PATH` — API endpoint used to list Manyfold models; default `/models`
- `MANYFOLD_COLLECTIONS_PATH` — API endpoint used to list collections; default `/collections`
- `MANYFOLD_CREATORS_PATH` — API endpoint used to list creators; default `/creators`
- `MANYFOLD_OAUTH_TOKEN_PATH` — OAuth token endpoint path; default `/oauth/token`
- `MANYFOLD_CLIENT_ID` — OAuth client ID for machine-to-machine access
- `MANYFOLD_CLIENT_SECRET` — OAuth client secret for machine-to-machine access
- `MANYFOLD_OAUTH_SCOPES` — optional scope string sent during token acquisition when the OAuth server requires explicit requested permissions
- `MANYFOLD_SESSION_EMAIL` — optional Manyfold login email used to bootstrap a real web session when upload endpoints reject pure OAuth client-credentials
- `MANYFOLD_SESSION_PASSWORD` — optional Manyfold login password paired with `MANYFOLD_SESSION_EMAIL`; only needed for the upload/session bridge workaround
- `MODEL_CATALOG_DB_PATH` — SQLite path for sidecar local state
- `MODEL_CATALOG_REFRESH_TTL_SECONDS` — cache TTL for Manyfold summary refresh
- `MODEL_CATALOG_HOST` — local bind host for manual `uvicorn` runs
- `MODEL_CATALOG_PORT` — local bind port for manual `uvicorn` runs
- `MODEL_CATALOG_CURATED_ASSETS_ROOT` — sidecar-controlled published asset root for curated local storage
- `MODEL_CATALOG_INTAKE_ROOTS` — comma-separated container paths allowed for intake browse/select and intake cleanup
- `MODEL_CATALOG_WORKING_FILES_ROOT` — container path used by Working Files explorer, reindex, and reorganize destination
- `MODEL_CATALOG_IMAGE_TAG` — image tag emitted by `/config` and `/diagnostics` (injected at build time)
- `MODEL_CATALOG_IMAGE_VERSION` — semantic image version emitted by `/config` and `/diagnostics` (injected at build time)
- `MODEL_CATALOG_IMAGE_REVISION` — source commit SHA emitted by `/config` and `/diagnostics` (injected at build time)
- `MODEL_CATALOG_IMAGE_CREATED` — image build timestamp emitted by `/config` and `/diagnostics` (injected at build time)

## OAuth Notes

The sidecar now supports OAuth client-credentials for Manyfold API access.

Current recommendation:

- use a client with read-only access for the current phase
- set `MANYFOLD_OAUTH_SCOPES=public read` if your Manyfold OAuth server requires explicit requested permissions during client-credentials token acquisition
- use the official Manyfold REST API documented at `http://manyfold.socko.us/api/index.html`, which exposes `GET /models` with `client_credentials` scopes `public` and `read`
- send `Accept: application/vnd.manyfold.v0+json` when calling `GET /models`, because Manyfold uses content negotiation on that route and can otherwise redirect to the browser sign-in page
- expect preview image fetches to use the sidecar proxy endpoint rather than hotlinking raw Manyfold `model_files` URLs from Home Assistant
- expect the sidecar to bootstrap an anonymous Manyfold site session before retrying a `model_files` image fetch when a cold request returns HTML or an upstream error page
- if `POST /upload` redirects to `/users/sign_in` even though OAuth token acquisition succeeds, configure `MANYFOLD_SESSION_EMAIL` and `MANYFOLD_SESSION_PASSWORD` so the sidecar can bootstrap a real logged-in web session for the Tus upload endpoints
- in this deployment, `http://host.docker.internal:3214` is the known-good direct path from a container to Manyfold when service-name or public-host routes still redirect authenticated API requests to the sign-in page

Why scopes are configurable instead of hard-coded:

- some OAuth providers default to the client's full allowed scope set when no scope is requested
- some expect an explicit space-delimited scope string
- the sidecar only needs read access today, so keeping scopes explicit helps avoid accidentally over-privileged tokens

## Manyfold OAuth Troubleshooting

Observed on Manyfold `0.138.0 (cf629cff)` in single-user mode:

- deleting an OAuth application or API key from the UI can return a 404 instead of removing it
- this appears distinct from the older owner-authorization bug fixed upstream in `v0.135.0`
- in single-user mode, current policy checks may still block OAuth application delete paths and surface as a 404 via the authorization handler

Practical workaround for now:

- open a shell in the Manyfold app container
- start Rails console with `bin/rails console`
- if that fails, run `bundle exec rails console`
- if you are not already in the app directory, `cd /app` first

Useful Rails console commands:

```ruby
Doorkeeper::Application.all.pluck(:id, :name)
Doorkeeper::AccessToken.all.pluck(:id, :application_id, :created_at, :revoked_at)
```

Delete an OAuth application by id:

```ruby
Doorkeeper::Application.find(ID).destroy!
```

Revoke a token by id without deleting the application:

```ruby
Doorkeeper::AccessToken.find(ID).revoke
```

If you are not already inside the container, the usual host-side command is:

```bash
docker compose exec app bin/rails console
```

and the common fallback is:

```bash
docker compose exec app bundle exec rails console
```

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

This validates the live health/config/diagnostics/openapi endpoints plus the safe intake queue read and validation paths without creating or mutating Manyfold data.

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
