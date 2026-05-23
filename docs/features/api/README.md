# API Documentation Landing

Issue alignment: #1123

This page is the docs landing point for API surfaces related to 3D printing feature work.

## Model Catalog

- API reference: `docs/features/model_catalog/reference/api-reference.md`
- Live sidecar docs landing: `GET /` on the model catalog sidecar
- Live Swagger UI: `GET /docs`
- Live ReDoc: `GET /redoc`
- Live OpenAPI JSON: `GET /openapi.json`

## Print History

- API reference: `docs/features/print_history/reference/api-reference.md`
- Live integration docs landing: `GET /api/bambuddy/print-history/docs` (requires Home Assistant auth)
- Bambuddy API catalog: `docs/features/bambuddy_common/reference/bambuddy-archive-api-catalog.md`
- OpenAPI correction notes: `docs/repo/reference/openapi-correction-notes.md`

## Bambuddy Runtime Repair Sidecar

- API reference: `sidecars/bambuddy-runtime-repair/README.md`
- Live sidecar docs landing: `GET /` on the runtime repair sidecar (requires bearer token auth)
- Live Swagger UI: `GET /docs`
- Live ReDoc: `GET /redoc`
- Live OpenAPI JSON: `GET /openapi.json`

## Notes

- Model catalog has a runtime swagger-capable API surface (FastAPI).
- Print history is integration-driven and documented through Bambuddy API contracts plus Home Assistant integration behavior.