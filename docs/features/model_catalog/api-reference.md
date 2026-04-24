# Model Catalog API Reference

Issue alignment: #1123 (API documentation and swagger-type landing page)

This feature exposes a FastAPI sidecar API.

## Live API Landing

When the sidecar is running:

- Landing page: `http://<host>:8314/`
- Swagger UI: `http://<host>:8314/docs`
- ReDoc: `http://<host>:8314/redoc`
- OpenAPI JSON: `http://<host>:8314/openapi.json`

## Core Endpoints

### Service

- `GET /` - API docs landing page with links to Swagger/ReDoc/OpenAPI
- `GET /healthz` - health and schema information
- `GET /config` - runtime configuration snapshot
- `GET /diagnostics` - service diagnostics and build metadata

### Models

- `GET /api/models`
- `GET /api/models/search`
- `GET /api/models/preview?source=<url-encoded-manyfold-model-file-url>`
- `GET /api/models/{model_ref}/fields`
- `GET /api/models/{model_ref}/fields/{field_key}`
- `PUT /api/models/{model_ref}/fields/{field_key}`
- `DELETE /api/models/{model_ref}/fields/{field_key}`
- `GET /api/models/{model_ref}/ranking`
- `PUT /api/models/{model_ref}/ranking`
- `POST /api/models/ranking/refresh`

Common custom-field keys exposed through the `fields` endpoints include:

- `to_print_status`
- `to_print_priority`
- `taxonomy_origin_class` (`reprint`, `remix_or_tweak`, `custom_unique`)
- `taxonomy_change_axes` (`color`, `model`, `other`)
- `model_favorite`
- `model_rating`
- `colors_used` (Phase 3 baseline: hex-first; later phase may add optional `filament_id` linkage)

Preview delivery contract:

- cached model summaries retain the upstream Manyfold `preview_url` source
- `GET /api/models` and `GET /api/models/search` rewrite that field to a sidecar-hosted `/api/models/preview` URL for Home Assistant consumption
- the preview endpoint first tries OAuth-authenticated upstream fetches, then bootstraps an anonymous Manyfold site session and retries when raw `model_files` routes require that session cookie to return image bytes

### Archive Links

- `GET /api/archive-links/{archive_id}`
- `POST /api/archive-links/{archive_id}`
- `PATCH /api/archive-links/{archive_id}/{link_id}`
- `POST /api/archive-links/{archive_id}/{link_id}/deactivate`
- `POST /api/archive-links/{archive_id}/cleanup-duplicates`
- `POST /api/archive-links/{archive_id}/candidates/refresh`
- `POST /api/archive-links/{archive_id}/{link_id}/accept`
- `POST /api/archive-links/{archive_id}/{link_id}/reject`
- `POST /api/admin/archive-links/repair-canonical-model-urls`

## Source of Truth

The live OpenAPI document is the contract source of truth:

- `/openapi.json`

Use this document for generated clients, schema checks, and endpoint validation in tests.