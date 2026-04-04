# Archive Runtime Sidecar API And Compose Draft

## Purpose

Define a concrete sidecar service shape for canonical Bambuddy archive runtime repair without modifying upstream Bambuddy.

This is the durable no-upstream option for print_history if direct DB repair becomes a recurring feature instead of a rare manual action.

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

## Suggested Compose Pattern

```yaml
services:
  bambuddy:
    image: maziggy/bambuddy:latest
    container_name: bambuddy
    volumes:
      - bambuddy_data:/data

  bambuddy-runtime-repair:
    build:
      context: ./sidecars/bambuddy-runtime-repair
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