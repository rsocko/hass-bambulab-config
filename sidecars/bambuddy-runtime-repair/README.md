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

## Required Environment Variables

- `BAMBUDDY_DB_PATH`
- `REPAIR_API_TOKEN`
- optional `LOG_LEVEL`

Typical values:

```text
BAMBUDDY_DB_PATH=/data/bambuddy.db
REPAIR_API_TOKEN=<long-random-token>
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
LOG_LEVEL=INFO
```

## Container Run Example

```bash
docker run -d \
  --name bambuddy-runtime-repair \
  --network bambuddy_net \
  -e BAMBUDDY_DB_PATH=/data/bambuddy.db \
  -e REPAIR_API_TOKEN=replace-me \
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
- non-dry-run apply mode is implemented for actionable top-level restore fields
- post-merge verification is implemented and can optionally remove the original archive when no actionable differences remain

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
    "dry_run": false
  }'
```

Reference design documents:

- `docs/features/print_history/archive-runtime-sidecar-api-and-compose.md`
- `docs/features/print_history/archive-runtime-restore-from-field-matrix.md`
- `docs/features/print_history/archive-runtime-restore-from-example-191-200.md`
- `docs/features/print_history/archive-runtime-restore-from-runbook.md`

## Deployment Recommendation

For Dockhand-style registry deployment:

1. build locally from source
2. push the tagged image to the local registry
3. deploy the image reference in Dockhand
4. attach the same Bambuddy data volume and internal network