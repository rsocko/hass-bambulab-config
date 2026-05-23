# Model Catalog Sidecar Modularization Plan

## Purpose

Reduce change-risk and edit ambiguity in `sidecars/model_catalog/app/main.py` by moving to explicit router and service modules without changing external API contracts.

## Why This Work Is Needed

Current state indicators:

- `sidecars/model_catalog/app/main.py` is 9201 lines.
- The file contains 90+ API route decorators and many helper utilities.
- The file receives most `sidecars/model_catalog/app` commit churn.

This concentration increases:

- Merge conflict frequency.
- Regression blast radius per change.
- Difficulty for Copilot and human reviewers to isolate intent.

## Goals

- Keep all existing endpoints and payload contracts stable.
- Reduce `main.py` to app composition and bootstrapping.
- Group code by feature capability and ownership boundaries.
- Preserve deterministic behavior through incremental extraction and tests.

## Non-Goals

- No API redesign in this effort.
- No database schema redesign in this effort.
- No frontend behavior changes in this effort.

## Target Architecture

### 1) Composition Layer

- `sidecars/model_catalog/app/main.py`
  - Owns app creation, middleware, dependency wiring, and router inclusion only.
  - No feature-specific route handlers after migration completes.

### 2) Router Layer (FastAPI APIRouter Modules)

- `sidecars/model_catalog/app/routers/system.py`
  - health, config, diagnostics, schema export, debug admin endpoints.
- `sidecars/model_catalog/app/routers/working.py`
  - working-files, working-groups, projects, bulk discover/import.
- `sidecars/model_catalog/app/routers/models.py`
  - model list/search/detail/fields/ranking/related and media endpoints.
- `sidecars/model_catalog/app/routers/archive_links.py`
  - archive-link CRUD, review decisions, candidate refresh/repair.
- `sidecars/model_catalog/app/routers/intake.py`
  - intake submit, queue listing, validation/defer/reject/group, uploads, publish/upload cleanup.
- `sidecars/model_catalog/app/routers/source_filesystems.py`
  - source filesystem inventory, browse, select.

### 3) Service/Domain Layer

- `sidecars/model_catalog/app/services/intake_workflows.py`
  - intake queue transitions, cleanup policy normalization, publish history append.
- `sidecars/model_catalog/app/services/model_media.py`
  - uploaded photo decode/validate/storage/serialization.
- `sidecars/model_catalog/app/services/path_security.py`
  - root allowlist checks, compare-key normalization, root-dedup logic.
- `sidecars/model_catalog/app/services/ranking.py`
  - ranking score utilities, ranking payload serialization.
- `sidecars/model_catalog/app/services/serialization.py`
  - shared API response serializers.

### 4) Data Access Layer

Continue to use `sidecars/model_catalog/app/db.py` as the persistence boundary during this refactor.

## Deterministic Migration Strategy

Migration occurs in vertical slices with hard acceptance gates.

### Phase A: Scaffolding and Guardrails

- Add router package and module shells.
- Add integration smoke tests that validate route registration and unchanged status codes for key endpoints.
- Keep all handlers in `main.py` initially; wire routers as empty first.

Exit criteria:

- No endpoint behavior changes.
- Test suite remains green.

### Phase B: System + Source Filesystems Extraction

- Move low-coupling endpoints first:
  - `/`, `/healthz`, `/config`, `/diagnostics`
  - source-filesystem browse/select endpoints
- Keep helper functions near extracted router or shared service module.

Exit criteria:

- Existing tests pass.
- Added route parity tests pass.

### Phase C: Archive Links Extraction

- Extract archive-links endpoints and candidate-refresh flow.
- Move candidate scoring/review helpers into focused services.

Exit criteria:

- Archive-link integration tests pass unchanged.
- No contract drift in payload shape.

### Phase D: Working/Projects Extraction

- Extract working-files, working-groups, projects, bulk discover/import endpoints.
- Move file path and membership helpers to shared service modules.

Exit criteria:

- Working-group and bulk flow tests pass.
- Deterministic compare-key and dedup behavior unchanged.

### Phase E: Intake Extraction

- Extract intake submit/queue/upload/publish/upload-to-manyfold/cleanup endpoints.
- Consolidate queue status transition helpers in intake service module.

Exit criteria:

- Intake browse/upload adapter tests pass.
- No change to queue status state machine behavior.

### Phase F: Models and Media Extraction

- Extract model summary/detail/search/fields/ranking/related/media endpoints.
- Move photo/media/path helpers to dedicated service modules.

Exit criteria:

- Model detail and media tests pass.
- No response contract regressions.

### Phase G: Main Cleanup

- Remove dead imports/helpers from `main.py`.
- Keep `create_app` composition, middleware, and router registration.
- Add architecture note in code comments and docs.

Exit criteria:

- `main.py` reduced to composition-focused scope.
- Full targeted regression suite passes.

## Test and Validation Gates

For each phase, run:

- `tests/sidecars/test_model_catalog_sidecar.py` (targeted subsets where practical)
- `tests/sidecars/test_intake_browse_api.py`
- `tests/sidecars/test_intake_service.py`
- `tests/sidecars/test_manyfold_upload_adapter.py`
- `tests/phase3/test_phase1_local_authority.py` (targeted)

Add router parity tests:

- Confirm route exists and method set is unchanged.
- Confirm representative error payload and success payload examples remain stable.

## Risk Controls

- Single-slice PRs only. One bounded domain per PR.
- No behavior change mixed with extraction in the same PR.
- Preserve function signatures and endpoint paths during relocation.
- Keep temporary compatibility imports when needed, remove in final cleanup PR.

## Definition of Done

- `main.py` is composition-focused and no longer the feature monolith.
- Router/domain boundaries are explicit and discoverable.
- Existing API contracts and tests remain intact.
- Documentation and issue tracker reflect final module ownership.
