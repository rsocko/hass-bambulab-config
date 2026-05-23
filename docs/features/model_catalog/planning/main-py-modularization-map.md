# Main.py Modularization Issue Map

This issue map is designed for low-risk, deterministic delivery.

## Tracking Principles

- One bounded capability per issue.
- Explicit dependency chain.
- Behavior-preserving extraction only.
- Test gates are required before closing each issue.

## Epic

### Issue 1

Title: Model Catalog Sidecar Modularization Epic: Decompose app main.py safely

Labels:

- model-catalog
- enhancement
- phase-5
- medium-priority

Body:

- Problem: `sidecars/model_catalog/app/main.py` has become a high-churn monolith.
- Goal: move to router + service modules while preserving contracts.
- Scope:
  - Track slices in child issues.
  - Enforce no-contract-change migration.
  - Ensure full route parity before closing.
- Success criteria:
  - Child issues complete.
  - `main.py` reduced to composition and wiring.
  - Regression tests pass.

## Child Issues

### Issue 2 (depends on 1)

Title: Scaffold routers package and route-parity guardrails for model_catalog sidecar

Labels:

- model-catalog
- enhancement
- phase-5

Body:

- Create `app/routers` package and router shell modules.
- Wire routers into `create_app` without moving handlers yet.
- Add route-parity tests for representative endpoints.
- Acceptance:
  - No behavior changes.
  - Tests green.

### Issue 3 (depends on 2)

Title: Extract system and source-filesystem endpoints from app main.py into routers

Labels:

- model-catalog
- enhancement
- phase-5

Body:

- Move system endpoints (`/`, `/healthz`, `/config`, `/diagnostics`, schema/admin diagnostics).
- Move source filesystem browse/select endpoints.
- Acceptance:
  - Route parity maintained.
  - Existing tests pass.

### Issue 4 (depends on 2)

Title: Extract archive-link endpoints and candidate workflows into router and services

Labels:

- model-catalog
- enhancement
- phase-5

Body:

- Move archive-link CRUD/review/candidate-refresh endpoints.
- Extract helper logic into focused service functions.
- Acceptance:
  - Archive-link tests pass unchanged.
  - Payload contract unchanged.

### Issue 5 (depends on 2)

Title: Extract working-files, working-groups, projects, and bulk flows from app main.py

Labels:

- model-catalog
- enhancement
- phase-5

Body:

- Move working-files/workflow/project endpoints.
- Move shared path/membership helpers to services.
- Acceptance:
  - Working and bulk flow tests pass.
  - Deterministic path normalization behavior preserved.

### Issue 6 (depends on 2)

Title: Extract intake queue and upload workflows into dedicated intake router/service modules

Labels:

- model-catalog
- enhancement
- phase-5

Body:

- Move intake queue lifecycle endpoints and upload endpoints.
- Consolidate queue-state transitions in intake services.
- Acceptance:
  - Intake browse/upload tests pass.
  - State-machine behavior unchanged.

### Issue 7 (depends on 2)

Title: Extract model detail/search/media/ranking endpoints into models router and services

Labels:

- model-catalog
- enhancement
- phase-5

Body:

- Move model detail/search/fields/ranking/related/media endpoints.
- Move media and serialization helper logic to service modules.
- Acceptance:
  - Model detail/media tests pass.
  - No response schema drift.

### Issue 8 (depends on 3,4,5,6,7)

Title: Final main.py cleanup and ownership documentation after modularization

Labels:

- model-catalog
- documentation
- enhancement
- phase-5

Body:

- Remove dead code/imports from `main.py`.
- Keep only app composition and router registration.
- Update docs and ownership boundaries.
- Acceptance:
  - `main.py` is composition-focused.
  - Test suite green.
  - Documentation updated.

## Suggested Execution Order

1. Issue 1 (Epic)
2. Issue 2 (Scaffold + parity tests)
3. Issue 3 (System + source filesystems)
4. Issue 4 (Archive links)
5. Issue 5 (Working/projects/bulk)
6. Issue 6 (Intake)
7. Issue 7 (Models/media/ranking)
8. Issue 8 (Cleanup + docs)

## Deterministic Close Checklist (apply to each child issue)

- [ ] All moved routes are still registered with original paths/methods.
- [ ] Existing integration tests for affected domain pass.
- [ ] No payload contract drift in success and representative error cases.
- [ ] `main.py` line count reduced relative to baseline.
- [ ] Release notes/docs updated if boundary ownership changed.
