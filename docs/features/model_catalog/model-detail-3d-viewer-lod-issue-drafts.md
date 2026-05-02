# Model Detail 3D Viewer LOD - GitHub Issue Drafts

## Parent Issue Draft

Title:

`Model Catalog: 3D Viewer performance hardening with LOD, UX clarity, and caching follow-ups`

Body:

```markdown
## Summary

Large 3MF models can overwhelm interactive viewing due to payload size and mesh complexity. This issue tracks a phased hardening effort for model detail 3D viewing.

Design reference:
- docs/features/model_catalog/model-detail-3d-viewer-lod-and-performance-design.md

## Scope

- Introduce server-side LOD controls for geometry payloads (`lod=auto|full|medium|low`)
- Keep interactive rendering responsive for large files
- Make simplification status visible to the user
- Add caching and performance validation follow-ups

## Sub-Issues

- [ ] Backend LOD contract and cache strategy
- [ ] Frontend LOD UX and detail-state messaging
- [ ] Performance validation, telemetry, and regression tests

## Acceptance Criteria

- [ ] LOD contract documented and implemented end-to-end
- [ ] Viewer explicitly shows simplified/full detail state
- [ ] Large 3MF behavior produces actionable errors, not opaque failures
- [ ] Performance baseline and regression checks are captured
```

## Sub-Issue 1 Draft

Title:

`Model Catalog backend: geometry LOD contract and response caching`

Body:

```markdown
## Summary

Implement and harden geometry LOD behavior for model detail interactive preview.

## Scope

- Support `lod` query parameter: `auto|full|medium|low`
- Apply deterministic simplification for non-full modes
- Return `geometry.lod` metadata and optional `viewer_notice`
- Preserve existing size and complexity guardrails
- Add/plan cache keys for model/file/plate/lod/hash

## Acceptance Criteria

- [ ] Endpoint accepts `lod` and returns deterministic output
- [ ] `geometry.lod` includes requested/applied/simplified/source/rendered counts
- [ ] Simplification happens for large meshes in auto mode
- [ ] Existing complexity rejection behavior still works
- [ ] Caching strategy documented (and implemented if in scope)

## Files

- sidecars/model_catalog/app/routers/models.py
- sidecars/model_catalog/app/routers/models_media.py
- sidecars/model_catalog/app/services/model_media_service.py
```

## Sub-Issue 2 Draft

Title:

`Model Catalog frontend: 3D viewer LOD UX with simplified preview indicator`

Body:

```markdown
## Summary

Update the model detail 3D viewer to request auto LOD and make fidelity state explicit.

## Scope

- Request geometry using `lod=auto`
- Parse `geometry.lod` metadata
- Display detail state:
  - `Simplified Preview (low|medium)`
  - `Full Geometry`
- Keep existing error messaging improvements for large/complex/incompatible files

## Acceptance Criteria

- [ ] Viewer requests `lod=auto` for geometry endpoint and HA service
- [ ] Detail state appears in UI when model loads
- [ ] Simplified state shown when server applies LOD
- [ ] Resource URL version bumped for cache busting

## Files

- homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js
- homeassistant/packages/3d_printing/model_catalog/rest_commands/model_catalog_get_geometry.yaml
- homeassistant/packages/3d_printing/common/dashboards/_resources.yaml
```

## Sub-Issue 3 Draft

Title:

`Model Catalog 3D viewer: performance validation and telemetry regression coverage`

Body:

```markdown
## Summary

Add focused validation for LOD behavior and capture measurable outcomes for large-model rendering.

## Scope

- Add sidecar tests for LOD simplification behavior
- Verify complexity guardrails still return clear 422 payloads
- Capture baseline timing/payload metrics for representative models
- Define telemetry/log fields for future diagnostics

## Acceptance Criteria

- [ ] New regression tests validate LOD behavior
- [ ] Existing geometry guardrail tests remain green
- [ ] Baseline benchmark notes added to docs
- [ ] Rollout verification checklist completed

## Files

- tests/sidecars/test_model_catalog_sidecar.py
- docs/features/model_catalog/model-detail-3d-viewer-lod-and-performance-design.md
```
