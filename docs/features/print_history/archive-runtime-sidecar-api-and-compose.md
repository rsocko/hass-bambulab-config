# Archive Runtime Sidecar API And Compose Draft

## Purpose

Define a concrete sidecar service shape for canonical Bambuddy archive runtime repair without modifying upstream Bambuddy.

This is the durable no-upstream option for print_history if direct DB repair becomes a recurring feature instead of a rare manual action.

Clarification:

The sidecar is not `n8n`-only. It exposes a normal HTTP endpoint that Home Assistant can call directly.

`n8n` is optional and is only useful when you want orchestration around the sidecar call or around broader recovery steps.

## Sidecar Responsibilities

The sidecar should own:

- request validation
- Bambuddy DB access
- repair transaction execution
- dry-run support
- audit logging
- narrow authentication

The sidecar should not own:

- print detection logic
- `.3mf` retrieval logic
- dashboard UX

Those remain with HA and optionally `n8n`.

## API Surface

## Supported Input Mode Today

Today the sidecar supports one repair mode only:

- target archive ID plus explicit runtime metadata fields

That means the caller provides the destination archive and whichever runtime fields should be corrected.

Current request model:

- `archive_id`
- `started_at`
- `completed_at`
- `created_at`
- `status`
- `failure_reason`
- `audit_note`
- `dry_run`

The sidecar then:

- loads the current target archive row
- validates the provided inputs
- updates only the provided runtime-repair fields
- appends an audit block to `notes` when `audit_note` is supplied

## Variations Supported Today

### 1. Direct explicit repair

Yes. This is the current implementation.

Example:

- archive ID `123`
- explicit `started_at`, `completed_at`, `created_at`
- optional `status`
- optional `failure_reason`

### 2. Partial repair

Yes.

You do not need to send every field. The service updates only the fields you provide.

Examples:

- only `created_at`
- only `status`
- only `started_at` and `completed_at`

### 3. Dry-run diff

Yes.

Set `dry_run: true` and the sidecar returns before and after values without applying the DB update.

## Variations Not Implemented Yet

### 1. Source archive ID plus target archive ID copy mode

Not implemented today.

This would look something like:

- `source_archive_id`
- `target_archive_id`
- optional `copy_fields`

and would mean:

- load source archive row
- copy selected runtime metadata from source to target
- optionally override some copied fields with explicit values

This is a reasonable future extension, especially for the repaired-entry case you described, but the current sidecar does not support it.

### 2. Bulk repair

Not implemented today.

No array-of-repairs or batch endpoint exists yet.

### 3. Arbitrary metadata copy

Not implemented today.

The service is intentionally limited to runtime-repair fields and related audit note handling. It does not currently copy tags, cost, external URL, photos, or other archive metadata.

## `POST /admin/archive-runtime-repair`

### Request

```json
{
  "archive_id": 123,
  "started_at": "2026-03-31T18:04:12+00:00",
  "completed_at": "2026-03-31T21:47:05+00:00",
  "created_at": "2026-03-31T21:47:05+00:00",
  "status": "completed",
  "failure_reason": null,
  "audit_note": "Recovered fallback archive after delayed 3MF retrieval",
  "dry_run": false
}
```

### Response

```json
{
  "archive_id": 123,
  "updated": true,
  "applied": true,
  "before": {
    "started_at": null,
    "completed_at": null,
    "created_at": "2026-04-01T02:10:00+00:00",
    "status": "archived"
  },
  "after": {
    "started_at": "2026-03-31T18:04:12+00:00",
    "completed_at": "2026-03-31T21:47:05+00:00",
    "created_at": "2026-03-31T21:47:05+00:00",
    "status": "completed"
  }
}
```

## `GET /health`

Return basic liveness information only.

## Validation Rules

- archive must exist
- only allow the approved repair fields
- reject malformed datetimes
- reject `completed_at < started_at`
- reject unknown statuses
- require admin token

## Authentication Model

Use one of:

- internal-only bind plus reverse-proxy auth
- static bearer token on internal Docker network
- mTLS if the environment already uses it

For this use case, internal Docker networking plus a dedicated bearer token is the practical default.

## Registry Image Deployment

If your deployment platform pulls from a registry but does not build from source, build the image locally and push it first.

Example local build and push:

```bash
docker build -f sidecars/bambuddy-runtime-repair/Dockerfile -t registry.local:5000/bambuddy-runtime-repair:0.1.0 .
docker push registry.local:5000/bambuddy-runtime-repair:0.1.0
```

The sidecar is therefore compatible with a Dockhand-style deployment model as long as the built image is available in the registry.

## Suggested Compose Pattern

```yaml
services:
  bambuddy:
    image: maziggy/bambuddy:latest
    container_name: bambuddy
    volumes:
      - bambuddy_data:/data

  bambuddy-runtime-repair:
    image: registry.local:5000/bambuddy-runtime-repair:0.1.0
    container_name: bambuddy-runtime-repair
    environment:
      BAMBUDDY_DB_PATH: /data/bambuddy.db
      REPAIR_API_TOKEN: ${REPAIR_API_TOKEN}
    volumes:
      - bambuddy_data:/data
    ports:
      - "127.0.0.1:8818:8080"
    depends_on:
      - bambuddy
    restart: unless-stopped

volumes:
  bambuddy_data:
```

Reference file:

- `../../../sidecars/bambuddy-runtime-repair/compose.example.yaml`

## Same-Host `n8n` Note

If `n8n` is already running in Docker on the same host as Bambuddy, prefer HTTP between containers over `docker exec`.

Recommended pattern:

1. attach `n8n` and `bambuddy-runtime-repair` to the same Docker network
2. let `n8n` call `http://bambuddy-runtime-repair:8080/admin/archive-runtime-repair`
3. mount the Bambuddy DB volume only into the sidecar

That keeps the sidecar as the only component with direct DB write access.

If no extra orchestration is needed, Home Assistant can call the same sidecar endpoint directly and skip `n8n` entirely.

## Suggested Container Internals

- lightweight FastAPI app
- one small service module that wraps the same repair logic as the CLI script
- JSON logging to stdout
- no direct dependency on Bambuddy runtime code unless needed for config discovery

## Suggested Internal Code Shape

- `app.py` or `main.py` for HTTP layer
- `repair.py` for validation and DB transaction logic
- `models.py` only if typed request and response models help clarity

## Relationship To The CLI Script

The sidecar should reuse the same repair core as the reference CLI where possible.

Desired layering:

- repair core library
- CLI wrapper
- HTTP wrapper

That avoids having two different implementations of the archive write logic.

## Recommendation

Do not build the sidecar first unless you already know this workflow will recur.

The right order is:

1. validate the repair logic with the CLI script
2. run it through `n8n` or operator tooling
3. promote it into a sidecar only if the workflow proves durable