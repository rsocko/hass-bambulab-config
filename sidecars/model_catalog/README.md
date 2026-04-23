# Model Catalog Sidecar

Minimal Phase 1A scaffold for the model-catalog service.

Current scope:

- FastAPI service scaffold
- health, config, and diagnostics endpoints
- SQLite schema bootstrap for model-catalog local state
- Manyfold read baseline for model summaries
- normalized summary endpoint for fetched or cached models
- first archive-link read contract endpoint for HA/print_history integration

## Build An Image Locally

Build from the repository root:

```bash
docker build \
	-f sidecars/model_catalog/Dockerfile \
	-t registry.socko.us/model-catalog-sidecar:0.1.0 \
	.
```

## Push To Local Registry

```bash
docker push registry.socko.us/model-catalog-sidecar:0.1.0
```

After that, Dockhand can deploy from the registry image without building from source.

Repository workflow:

- `.github/workflows/build-model-catalog-sidecar.yml`

Default workflow registry:

- `registry.socko.us/model-catalog-sidecar`

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
image: registry.socko.us/model-catalog-sidecar:${MODEL_CATALOG_IMAGE_TAG:-0.1.0}
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
MODEL_CATALOG_IMAGE_TAG=0.1.0
MANYFOLD_BASE_URL=http://manyfold:3214
MANYFOLD_MODELS_PATH=/models
MANYFOLD_OAUTH_TOKEN_PATH=/oauth/token
MANYFOLD_CLIENT_ID=replace-with-oauth-client-id
MANYFOLD_CLIENT_SECRET=replace-with-oauth-client-secret
MANYFOLD_OAUTH_SCOPES=public read
MODEL_CATALOG_REFRESH_TTL_SECONDS=900
```

Known-good fallback from live debugging:

```text
MANYFOLD_BASE_URL=http://host.docker.internal:3214
```

That path previously worked from an n8n container using the same OAuth client against `GET /models` with `Accept: application/vnd.manyfold.v0+json`.

## Dockhand / Manyfold Stack Compose

There is not currently a committed Manyfold Dockhand stack file in this repo, so this sidecar ships two compose examples instead:

- `compose.example.yaml` — standalone sidecar deployment
- `compose.manyfold-stack.example.yaml` — example service block for adding the sidecar to a same-host Manyfold stack in Dockhand

For the Manyfold stack example, the expected pattern is:

- put the sidecar on the same Docker network as Manyfold
- keep the sidecar state in its own Docker volume
- keep the image tag in the stack `.env`
- point `MANYFOLD_BASE_URL` at the service name reachable inside the stack network
- if authenticated `GET /models` still redirects to `/users/sign_in`, switch `MANYFOLD_BASE_URL` to `http://host.docker.internal:3214` and keep the `host-gateway` mapping in the sidecar service

## Environment Variables

- `MANYFOLD_BASE_URL` — base URL for the Manyfold instance
- `MANYFOLD_MODELS_PATH` — API endpoint used to list Manyfold models; default `/models`
- `MANYFOLD_COLLECTIONS_PATH` — API endpoint used to list collections; default `/collections`
- `MANYFOLD_CREATORS_PATH` — API endpoint used to list creators; default `/creators`
- `MANYFOLD_OAUTH_TOKEN_PATH` — OAuth token endpoint path; default `/oauth/token`
- `MANYFOLD_CLIENT_ID` — OAuth client ID for machine-to-machine access
- `MANYFOLD_CLIENT_SECRET` — OAuth client secret for machine-to-machine access
- `MANYFOLD_OAUTH_SCOPES` — optional scope string sent during token acquisition when the OAuth server requires explicit requested permissions
- `MODEL_CATALOG_DB_PATH` — SQLite path for sidecar local state
- `MODEL_CATALOG_REFRESH_TTL_SECONDS` — cache TTL for Manyfold summary refresh
- `MODEL_CATALOG_HOST` — local bind host for manual `uvicorn` runs
- `MODEL_CATALOG_PORT` — local bind port for manual `uvicorn` runs
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
