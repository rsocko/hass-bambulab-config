# Bambuddy Runtime Repair Sidecar

## Purpose

Small FastAPI sidecar that exposes an authenticated admin endpoint for canonical Bambuddy archive runtime repair.

This is intended for environments where Home Assistant, `n8n`, or another tool should call a stable HTTP API instead of writing to the Bambuddy SQLite database directly.

## Call Pattern

The sidecar exposes an HTTP API that can be called directly by either:

- Home Assistant
- `n8n`
- another internal service or operator tool

`n8n` is optional. It is only useful when you want extra orchestration around the repair call, such as approval gates, retries, or combining this step with other archive-recovery actions.

If all you need is canonical runtime repair, Home Assistant can call the sidecar directly.

## API Docs Landing

When the sidecar is running, these API docs endpoints are available:

- `GET /` - docs landing page
- `GET /docs` - Swagger UI
- `GET /redoc` - ReDoc
- `GET /openapi.json` - OpenAPI schema
- `GET /health` - health check

All `/admin/*` endpoints require Bearer token authentication.

## Build An Image Locally

Build from the repository root because the image includes shared tooling from `tools/`.

Example:

```bash
docker build \
  -f sidecars/bambuddy-runtime-repair/Dockerfile \
  -t registry.socko.us/bambuddy-runtime-repair:0.1.0 \
  .
```

## Push To Local Registry

```bash
docker push registry.socko.us/bambuddy-runtime-repair:0.1.0
```

After that, Dockhand can deploy from the registry image without building from source.

Repository workflow:

- `.github/workflows/build-bambuddy-runtime-repair.yml`

Default workflow registry:

- `registry.socko.us/bambuddy-runtime-repair`

Workflow tag resolution:

- `version_mode=explicit` uses the exact `image_tag` you provide
- `version_mode=next_patch` inspects the registry, finds the latest semantic tag, and increments patch
- `version_mode=next_minor` inspects the registry, finds the latest semantic tag, and increments minor
- `version_mode=next_major` inspects the registry, finds the latest semantic tag, and increments major
- if the registry has no semantic tags yet, the workflow bootstraps to `0.1.0` for `next_patch` and `next_minor`, or `1.0.0` for `next_major`

The workflow resolves the tag before build/push, so the built image always uses the resolved semantic version rather than a hard-coded default.

The workflow also writes a copy-ready version block into the GitHub Actions run summary:

- resolved tag
- full image reference
- `.env` line for compose such as `BAMBUDDY_RUNTIME_REPAIR_IMAGE_TAG=0.1.4`
- optional `.env` line for compose as `BAMBUDDY_RUNTIME_REPAIR_IMAGE_TAG=latest` when `push_latest=true`

## Compose Tag Management

The example compose file now uses an environment variable for the image tag instead of hard-coding the full image reference:

```yaml
image: registry.socko.us/bambuddy-runtime-repair:${BAMBUDDY_RUNTIME_REPAIR_IMAGE_TAG:-0.1.3}
```

That makes updates simpler:

1. run the workflow
2. copy the `BAMBUDDY_RUNTIME_REPAIR_IMAGE_TAG=...` line from the run summary
3. paste it into the compose `.env`
4. run `docker compose pull && docker compose up -d`

Suggested `.env` entry:

```text
BAMBUDDY_RUNTIME_REPAIR_IMAGE_TAG=0.1.3
```

If you prefer a mutable deployment target, run the workflow with `push_latest=true` and set the compose tag once:

```text
BAMBUDDY_RUNTIME_REPAIR_IMAGE_TAG=latest
```

That removes the need to update the stack file or `.env` for each release. The semantic tag is still pushed alongside `latest`, so you keep a pinned rollback target if you need one.

## Required Environment Variables

- `BAMBUDDY_DB_PATH`
- `REPAIR_API_TOKEN`
- `BAMBUDDY_API_BASE_URL` when using restore photo migration or Bambuddy-side archive removal
- `BAMBUDDY_API_KEY` when using restore photo migration or Bambuddy-side archive removal
- `HOME_ASSISTANT_BASE_URL` when using optional post-restore re-enrich
- `HOME_ASSISTANT_TOKEN` when using optional post-restore re-enrich
- optional `LOG_LEVEL`

Typical values:

```text
BAMBUDDY_DB_PATH=/data/bambuddy.db
REPAIR_API_TOKEN=<long-random-token>
BAMBUDDY_API_BASE_URL=http://bambuddy:8902
BAMBUDDY_API_KEY=<bambuddy-api-key>
HOME_ASSISTANT_BASE_URL=http://homeassistant:8123
HOME_ASSISTANT_TOKEN=<home-assistant-long-lived-token>
LOG_LEVEL=INFO
```

## Compose `.env` Entry

If your compose file uses `REPAIR_API_TOKEN: ${REPAIR_API_TOKEN}`, add this to the stack `.env` file that Dockhand or Docker Compose loads:

```text
REPAIR_API_TOKEN=replace-with-a-long-random-secret
```

Example with the other sidecar settings if you also externalize them:

```text
REPAIR_API_TOKEN=replace-with-a-long-random-secret
BAMBUDDY_DB_PATH=/data/bambuddy.db
BAMBUDDY_API_BASE_URL=http://bambuddy:8902
BAMBUDDY_API_KEY=replace-with-a-bambuddy-api-key
HOME_ASSISTANT_BASE_URL=http://homeassistant:8123
HOME_ASSISTANT_TOKEN=replace-with-a-home-assistant-long-lived-token
LOG_LEVEL=INFO
```

## Container Run Example

```bash
docker run -d \
  --name bambuddy-runtime-repair \
  --network bambuddy_net \
  -e BAMBUDDY_DB_PATH=/data/bambuddy.db \
  -e REPAIR_API_TOKEN=replace-me \
  -e BAMBUDDY_API_BASE_URL=http://bambuddy:8902 \
  -e BAMBUDDY_API_KEY=replace-me \
  -e HOME_ASSISTANT_BASE_URL=http://homeassistant:8123 \
  -e HOME_ASSISTANT_TOKEN=replace-me \
  -v bambuddy_data:/data \
  -p 127.0.0.1:8818:8080 \
  registry.socko.us/bambuddy-runtime-repair:0.1.0
```

## Same-Host `n8n` Note

If `n8n` is already running in a Docker container on the same host as Bambuddy, the cleanest pattern is:

1. run this sidecar on the same Docker network as `n8n` and Bambuddy
2. have `n8n` call `http://bambuddy-runtime-repair:8080/admin/archive-runtime-repair`
3. mount the same Bambuddy data volume into the sidecar, not into `n8n`

That avoids:

- SSH hops
- `docker exec` from inside `n8n`
- direct DB access from the `n8n` container

It does not mean `n8n` is required. It only means that if `n8n` is already part of the deployment, HTTP-to-sidecar is cleaner than command execution.

## Health Check

```bash
curl http://127.0.0.1:8818/health
```

PowerShell smoke-test helper:

```powershell
pwsh -File tools/bambuddy/Test-RuntimeRepairSidecar.ps1 -BaseUrl http://127.0.0.1:8818
```

## Storage Scan Endpoints

The sidecar also exposes authenticated archive storage inspection endpoints:

- `POST /admin/archive-storage/scan`
- `POST /admin/archive-storage/scan-batch`
- `GET /admin/archive-storage/summary`

These endpoints read Bambuddy archive metadata from `BAMBUDDY_DB_PATH` and scan the shared archive volume under the same data root.

Home Assistant now consumes the single and batch scan endpoints to cache per-archive storage metrics in the local Variant 3 store.

## Repair Request Example

```bash
curl -X POST http://127.0.0.1:8818/admin/archive-runtime-repair \
  -H "Authorization: Bearer replace-me" \
  -H "Content-Type: application/json" \
  -d '{
    "archive_id": 123,
    "started_at": "2026-03-31T18:04:12+00:00",
    "completed_at": "2026-03-31T21:47:05+00:00",
    "created_at": "2026-03-31T21:47:05+00:00",
    "status": "completed",
    "audit_note": "Recovered fallback archive after delayed 3MF retrieval",
    "dry_run": false
  }'
```

PowerShell smoke-test helper with dry run:

```powershell
pwsh -File tools/bambuddy/Test-RuntimeRepairSidecar.ps1 \
  -BaseUrl http://127.0.0.1:8818 \
  -Token replace-me \
  -ArchiveId 123 \
  -StartedAt 2026-03-31T18:04:12+00:00 \
  -CompletedAt 2026-03-31T21:47:05+00:00 \
  -CreatedAt 2026-03-31T21:47:05+00:00 \
  -Status completed
```

## First Dry-Run Tests

After the sidecar is up and `/health` responds, run these first:

Dry-run restore-from plan:

```powershell
pwsh -File tools/bambuddy/Test-RestoreFromSidecar.ps1 \
  -BaseUrl http://127.0.0.1:8818 \
  -Token $env:REPAIR_API_TOKEN \
  -SourceArchiveId 191 \
  -TargetArchiveId 200
```

Dry-run runtime-repair plan:

```powershell
pwsh -File tools/bambuddy/Test-RuntimeRepairSidecar.ps1 \
  -BaseUrl http://127.0.0.1:8818 \
  -Token $env:REPAIR_API_TOKEN \
  -ArchiveId 200 \
  -StartedAt 2026-03-31T18:04:12+00:00 \
  -CompletedAt 2026-03-31T21:47:05+00:00 \
  -CreatedAt 2026-03-31T21:47:05+00:00 \
  -Status completed \
  -AuditNote "Initial dry-run runtime repair for recovered historical archive"
```

Those commands stay in dry-run mode unless you add `-Apply`.

## Planned `restore_from` Endpoint

The sidecar now includes typed request and response models, plus a guarded endpoint stub for:

- `POST /admin/archive-restore-from`
- `POST /admin/archive-restore-verify`

Current status:

- request validation is implemented
- response models are defined
- merge-planning logic lives in `app/repair.py`
- DB-backed `dry_run` planning is implemented
- non-dry-run apply mode is implemented for actionable top-level restore fields and Bambuddy photo API uploads for source archive photos
- post-merge verification is implemented and can optionally remove the original archive when restore differences are clear and enrichment is complete, or when an explicit force flag is supplied

Current restore behavior for photo attachments:

- target parser-backed assets such as `file_path` and `thumbnail_path` stay on the recovered target archive
- source archive photo attachments are discovered from `archive_photos`, with Bambuddy `GET /archives/{id}` detail as the fallback when the DB photo table is empty or stale
- existing target photo attachments are preserved; only source-only photos are uploaded
- photo equivalence prefers content hash from local files or Bambuddy photo downloads, then falls back to path and role
- photo migration requires a reachable Bambuddy API base URL and API key in the sidecar environment

Current source-removal behavior after verify:

- when `remove_original=true` and verify allows removal, the sidecar now calls Bambuddy `DELETE /api/v1/archives/{id}` instead of deleting the SQLite row directly
- this preserves Bambuddy's own archive cleanup behavior for normal archive directories and avoids bypassing backend file-deletion logic
- remove-original requests now fail closed before target-finalization work starts if `BAMBUDDY_API_BASE_URL` or `BAMBUDDY_API_KEY` is missing
- if the Bambuddy API delete fails, the verify response reports `source_removed=false` and returns a warning

Current restore behavior for archive `extra_data` and re-enrich:

- source `extra_data` is deep-merged into target `extra_data` with target values taking priority on conflicts
- this preserves the original archived `_print_data.raw_data.ams` and related source metadata when the recovered target does not already have it
- optional post-restore re-enrich can call Home Assistant `script.reenrich_print_history_archive` when `run_reenrich` is requested and HA connection settings are configured
- if re-enrich is requested but HA connection settings are absent or the service call fails, restore still succeeds and returns a warning
- restore-verify now reports enrichment readiness and blocks source removal by default when the target archive is not yet enrichment-complete
- source removal can still be forced with `force_remove_without_reenrich=true`

PowerShell helpers:

- `tools/bambuddy/Test-RuntimeRepairSidecar.ps1`
- `tools/bambuddy/Test-RestoreFromSidecar.ps1`

## Verify Request Example

```bash
curl -X POST http://127.0.0.1:8818/admin/archive-restore-verify \
  -H "Authorization: Bearer replace-me" \
  -H "Content-Type: application/json" \
  -d '{
    "source_archive_id": 191,
    "target_archive_id": 200,
    "remove_original": false,
    "dry_run": true
  }'
```

Use `remove_original: true` with `dry_run: false` only after verification reports `verified: true` and `remaining_difference_count: 0`.

## Restore-From Request Example

```bash
curl -X POST http://127.0.0.1:8818/admin/archive-restore-from \
  -H "Authorization: Bearer replace-me" \
  -H "Content-Type: application/json" \
  -d '{
    "source_archive_id": 191,
    "target_archive_id": 200,
    "run_reenrich": true,
    "dry_run": false
  }'
```

If you prefer the PowerShell helper, add `-RunReenrich` to request the optional HA callback after apply.

For forced removal when enrichment is still incomplete, use `force_remove_without_reenrich: true` on `POST /admin/archive-restore-verify`, or `-ForceRemoveWithoutReenrich` with `tools/bambuddy/Test-RestoreFromSidecar.ps1 -Verify`.

Reference design documents:

- `docs/features/print_history/runtime-repair/archive-runtime-sidecar-api-and-compose.md`
- `docs/features/print_history/runtime-repair/archive-runtime-restore-from-field-matrix.md`
- `docs/features/print_history/runtime-repair/archive-runtime-restore-from-example-191-200.md`
- `docs/features/print_history/runtime-repair/archive-runtime-restore-from-runbook.md`

## Deployment Recommendation

For Dockhand-style registry deployment:

1. build locally from source
2. push the tagged image to the local registry
3. deploy the image reference in Dockhand
4. attach the same Bambuddy data volume and internal network