# Model Catalog Implementation Plan

> Status: Proposed implementation plan.
> Scope: Single-library, archive-linked model catalog built inside the existing `bambuddy` integration boundary.

## Goal

Implement a practical first version of the model catalog without attempting to replace either Manyfold or Bambuddy.

The first version should:

- expose Manyfold-backed catalog records in Home Assistant
- attach Bambuddy archive linkage to those records
- keep structured linkage metadata in a local SQLite store
- surface archive-to-model actions inside existing print-history flows

The first version should not try to deliver:

- full Manyfold editing parity
- full Manyfold browsing parity
- full Bambuddy file-manager replacement
- generalized cross-system automation before the core linkage contract is stable

## Packaging Decision

The recommended first implementation extends the existing `bambuddy` custom integration.

Why:

- archive-centric flows are already there
- `print_history` is the first consumer of the linkage data
- the repo already favors consolidating custom integration logic when practical

Recommended boundary:

- `homeassistant/custom_components/bambuddy/` owns clients, storage, coordinators, services, and websocket support
- `homeassistant/www/3d_printing/` owns custom-card and popup UI behavior

## Phase Plan

### Phase 1: Local Linkage Storage And Service Skeleton

Outcome:

- the repo can persist archive-to-model links locally
- HA can create, accept, reject, and inspect links

Work items:

- add SQLite storage manager for `model_catalog_links`, `model_catalog_annotations`, and optional event rows
- add migration and schema bootstrap logic
- add service handlers for:
  - `bambuddy.get_archive_model_link`
  - `bambuddy.refresh_archive_model_link_candidates`
  - `bambuddy.create_archive_model_link`
  - `bambuddy.accept_archive_model_link`
  - `bambuddy.reject_archive_model_link`
  - `bambuddy.deactivate_archive_model_link`
  - `bambuddy.open_linked_model_target`
- add unit tests for storage CRUD and link review transitions

Deliverables:

- local DB file under `.storage`
- service responses matching the archive-popup contract
- no Manyfold write-back yet

### Phase 2: Manyfold Read Client And Model Cache

Outcome:

- HA can read Manyfold catalog data on demand and cache the minimum needed projection

Work items:

- add Manyfold API client with config fields for base URL, token, and SSL behavior
- implement read methods for:
  - list models
  - get model detail
  - get file detail when needed
  - optional creator/collection hydration
- add local cache or coordinator projection for:
  - model summary
  - preview URL
  - tags
  - creator/collection names
- add reconciliation path from Manyfold model URL/public ID into local linkage DB

Deliverables:

- HA can resolve linked Manyfold model summaries quickly
- archive popups can display linked model name, preview, and URL

### Phase 3: Archive Popup Integration

Outcome:

- the existing print-history popup becomes the main operator surface for archive-to-model linkage

Work items:

- add linked-model summary section to archive popup
- add actions for:
  - open linked model
  - refresh link candidates
  - accept candidate
  - reject candidate
- show compact state:
  - linked
  - no link
  - candidates pending review
  - ambiguous or rejected
- add lightweight manual-link flow entrypoint

Deliverables:

- archive popups support the first useful linkage workflow end-to-end

### Phase 4: Manual Model Search And Selection

Outcome:

- operators can manually pick a Manyfold model when automatic candidate generation is insufficient

Work items:

- add search-backed service or websocket query for Manyfold model search
- if Manyfold API search is too narrow, implement local cache filtering in HA
- provide popup UI for selecting a model and confirming link creation

Deliverables:

- low-friction manual linking without leaving HA

### Phase 5: Model Catalog Panel Or Card Surface

Outcome:

- HA has a model-catalog browse surface joined with archive-link context

Work items:

- add a lightweight card or panel that shows:
  - Manyfold preview
  - title
  - tags
  - creator/collection
  - linked archive count
  - latest linked archive status
- provide deep links to:
  - Manyfold model page
  - related archive popup or detail view

Deliverables:

- archive-linked model browsing inside HA without requiring full Manyfold iframe dependence

### Phase 6: Selective Manyfold Write-back

Outcome:

- HA can perform deterministic metadata updates to Manyfold when explicitly requested

Candidate write-back operations:

- update tags
- update description or notes
- update links
- assign creator or collection
- update preview file selection only if the workflow is deterministic

Guardrails:

- do not add repo-specific structured metadata into Manyfold fields as the primary store
- do not attempt broad synchronization before operator-reviewed workflows are stable

## Component Plan

### Integration-side modules

Recommended new modules under `homeassistant/custom_components/bambuddy/`:

- `manyfold_client.py`
- `model_catalog_store.py`
- `model_catalog_models.py`
- `model_catalog_service.py`
- `model_catalog_coordinator.py`
- `model_catalog_matcher.py`

Suggested responsibilities:

- `manyfold_client.py`: HTTP client and response normalization
- `model_catalog_store.py`: SQLite CRUD and migration logic
- `model_catalog_models.py`: typed row and DTO definitions
- `model_catalog_service.py`: HA service handlers and response envelopes
- `model_catalog_coordinator.py`: cache refresh and aggregate projections
- `model_catalog_matcher.py`: deterministic and heuristic candidate matching

### Frontend-side modules

Recommended additions under `homeassistant/www/3d_printing/` only after Phase 3 proves useful.

Candidate modules:

- archive popup section renderer for model linkage
- model-catalog search popup
- model-catalog card or panel

## Data Ownership Rules

### Manyfold authority

- model name
- caption
- description
- tags
- creator
- collection
- preview selection
- model file metadata

### Bambuddy authority

- archive facts
- runtime print metrics
- archive media
- printer status
- queue relationships

### Local linkage authority

- archive-to-model relationship
- match confidence
- review state
- provenance
- repo-specific structured annotations

## Initial Service Backlog

Implement in this order:

1. `bambuddy.get_archive_model_link`
2. `bambuddy.create_archive_model_link`
3. `bambuddy.accept_archive_model_link`
4. `bambuddy.reject_archive_model_link`
5. `bambuddy.refresh_archive_model_link_candidates`
6. `bambuddy.open_linked_model_target`

Later:

1. `bambuddy.search_model_library`
2. `bambuddy.sync_manyfold_model_metadata`

## Testing Plan

### Integration tests

- SQLite schema bootstrap and migration
- service validation and response shape
- candidate acceptance and rejection transitions
- Manyfold client error handling and auth failures

### UI tests

- popup renders linked state
- popup renders candidate-review state
- actions dispatch correct services

### End-to-end acceptance criteria

1. Operator opens an archive popup.
2. HA shows either no link, a linked model, or review candidates.
3. Operator can manually accept or create a link.
4. The next popup render shows the accepted link.
5. Operator can open the linked model target.

## Recommended Sequence For Actual Repo Work

1. Add storage layer and tests.
2. Add service layer and tests.
3. Add Manyfold read client.
4. Add popup integration.
5. Add manual search popup.
6. Add browse surface.
7. Add selective write-back only after the read-and-link path is stable.

## Explicit Non-Goals For First Slice

- no full Manyfold mirror inside HA
- no automatic broad metadata sync
- no generalized file reorganization
- no replacement of Manyfold library admin or path-template setup
- no replacement of Bambuddy archive management