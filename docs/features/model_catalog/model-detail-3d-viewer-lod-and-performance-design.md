# Model Detail 3D Viewer LOD and Performance Design

## Context

Large 3MF files can fail in two ways:

- Server-side geometry extraction can produce extremely large JSON payloads.
- Browser fallback parsers can fail on some 3MF variants.

This design defines a low-detail rendering path so interactive preview remains usable for large models.

## Current Behavior Summary

- Geometry endpoint: `GET /api/models/{model_ref}/geometry/{file_id}`
- 3MF extraction path: `sidecars/model_catalog/app/geometry_3mf.py`
- Viewer path: `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js`
- HA service proxy: `rest_command.model_catalog_get_geometry`

Previously, full triangle payloads were returned by default, which could exceed practical transport and browser parsing limits.

## External Learnings

### Manyfold

Manyfold combines:

- static render derivatives for card/list previews
- interactive rendering via a worker/offscreen renderer
- load behavior that can be gated by size/config

Relevant takeaway: avoid forcing full high-detail geometry payloads for every interactive request.

### Bambuddy / Print History

The print-history viewer path favors G-code preview rendering and avoids shipping huge mesh payloads to the popup path.

Relevant takeaway: prioritize a responsive interactive path first, even if fidelity is reduced.

## Goals

- Keep interactive model viewing responsive for large models.
- Avoid oversized geometry responses that overwhelm HA proxying or browser JSON parsing.
- Preserve deterministic behavior and predictable quality tiers.

## Non-Goals

- Perfect geometric decimation quality in Phase A/B.
- Replacing all rendering paths with a worker-based binary loader in this phase.

## API Design

### Query Parameter

- `lod`: `auto | full | medium | low`

### LOD Limits

- `low`: 150,000 triangles
- `medium`: 400,000 triangles
- `full`: no simplification, still subject to complexity guardrails

### Auto Selection

- source triangles > medium limit: apply `low`
- source triangles > low limit: apply `medium`
- otherwise: apply `full`

### Response Metadata

`geometry.lod` object:

- `requested`
- `applied`
- `simplified`
- `source_triangle_count`
- `rendered_triangle_count`

Optional top-level hint:

- `viewer_notice`: "Simplified preview applied for interactive performance"

## UI Design

Viewer always requests `lod=auto` for geometry endpoint calls.

Viewer displays a detail state in info panel:

- `Simplified Preview (low|medium)` when simplified
- `Full Geometry` otherwise

This makes fidelity changes explicit to end users.

## Implemented in Phase A/B

- Backend LOD support and geometry decimation in `models.py`
- HA rest command support for `lod` query parameter
- Frontend request default `lod=auto`
- Frontend detail indicator for simplified/full geometry
- Cache-busting resource URL update for the updated viewer module
- Regression tests for auto LOD simplification behavior

## Guardrails

- Size guardrail for 3MF package bytes remains in place.
- Complexity guardrail remains in place after LOD transformation.
- If payload still cannot be rendered interactively, endpoint returns 422 with clear error payload.

## Next Steps (Phase C/D)

1. Add server-side cache for LOD outputs keyed by model/file/plate/lod/source hash.
2. Add optional offline derivative generation for simplified meshes.
3. Evaluate worker-based binary rendering path to reduce JSON transport costs further.
4. Add user control for requested detail tier (Auto/High/Medium/Low) in viewer UI.
