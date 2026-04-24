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
- `GET /api/models/{model_ref}/fields`
- `GET /api/models/{model_ref}/fields/{field_key}`
- `PUT /api/models/{model_ref}/fields/{field_key}`
- `DELETE /api/models/{model_ref}/fields/{field_key}`
- `GET /api/models/{model_ref}/ranking`
- `PUT /api/models/{model_ref}/ranking`
- `POST /api/models/ranking/refresh`

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