# Model Catalog Sidecar

Minimal Phase 1A scaffold for the model-catalog service.

Current scope:

- FastAPI service scaffold
- health, config, and diagnostics endpoints
- SQLite schema bootstrap for model-catalog local state
- Manyfold read baseline for model summaries
- normalized summary endpoint for fetched or cached models

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

Suggested `.env` entries:

```text
MODEL_CATALOG_IMAGE_TAG=0.1.0
MANYFOLD_BASE_URL=http://manyfold:3214
MODEL_CATALOG_REFRESH_TTL_SECONDS=900
```

## Dockhand / Manyfold Stack Compose

There is not currently a committed Manyfold Dockhand stack file in this repo, so this sidecar ships two compose examples instead:

- `compose.example.yaml` — standalone sidecar deployment
- `compose.manyfold-stack.example.yaml` — example service block for adding the sidecar to a same-host Manyfold stack in Dockhand

For the Manyfold stack example, the expected pattern is:

- put the sidecar on the same Docker network as Manyfold
- keep the sidecar state in its own Docker volume
- keep the image tag in the stack `.env`
- point `MANYFOLD_BASE_URL` at the service name reachable inside the stack network

## Environment Variables

- `MANYFOLD_BASE_URL` — base URL for the Manyfold instance
- `MODEL_CATALOG_DB_PATH` — SQLite path for sidecar local state
- `MODEL_CATALOG_REFRESH_TTL_SECONDS` — cache TTL for Manyfold summary refresh
- `MODEL_CATALOG_HOST` — local bind host for manual `uvicorn` runs
- `MODEL_CATALOG_PORT` — local bind port for manual `uvicorn` runs

## Run Locally

```powershell
& "c:\dev\hass-bambulab-config\.venv\Scripts\python.exe" -m uvicorn sidecars.model_catalog.app.main:app --host 127.0.0.1 --port 8314
```

## Health Check

```bash
curl http://127.0.0.1:8314/healthz
```
