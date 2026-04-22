# Model Catalog Implementation Plan

> Status: Updated implementation plan incorporating issues #171, #173, #175, #177, #178, #179, #180, #181, #182, #183, #186, #190, #215, #221, #222, #224, #642.
> Last updated: 2026-04-21
> Scope: Single-user personal model catalog — Manyfold as archive authority, Bambuddy as print authority, new catalog sidecar for extended operations, HA as operator surface.

## Goal

Deliver a personal 3D model catalog that:

- uses Manyfold as the authoritative model library
- links Manyfold models to Bambuddy print archives
- extends Manyfold with custom fields (origin type, publish status, print queue, notes) stored in a local sidecar DB
- surfaces everything in Home Assistant for archive popup linkage, catalog browse, and photo/ingestion actions
- enables 3MF asset extraction, mobile photo upload, and phased online model ingestion

For full architecture rationale and folder structure design, see [Architecture Overview](architecture-overview.md).
For custom fields schema, see [Custom Fields Schema](custom-fields-schema.md).
For print queue analysis, see [Print Queue Assessment](print-queue-assessment.md).
For workflow and ingestion design, see [Workflow And Ingestion Guide](workflow-and-ingestion-guide.md).

## Packaging Decision

The implementation spans two delivery boundaries:

**1. Catalog sidecar** (new separate Docker container):

- Python / FastAPI service
- Owns the SQLite DB: linkage, custom fields, Manyfold summary cache
- Provides REST API consumed by HA and optionally direct browser calls
- Handles background jobs: 3MF parsing, photo upload, ingestion, storage monitoring

**2. HA integration** (extends existing `bambuddy` custom component or new `model_catalog` component):

- Connects to sidecar REST API and Manyfold API
- Surfaces data in archive popups, catalog cards, and service calls
- Custom JS cards under `homeassistant/www/3d_printing/`

The sidecar is separate from Bambuddy by design. See [Architecture Overview — Why A Separate Sidecar](architecture-overview.md#why-a-separate-sidecar-not-an-extension-of-bambuddy).

## Phase Plan

### Phase 0: Sidecar Service Scaffold (NEW)

Outcome:

- catalog sidecar exists as a runnable Docker service
- SQLite DB schema is bootstrapped
- HA can reach the sidecar and confirm health

Work items:

- scaffold FastAPI service with health endpoint
- implement SQLite schema bootstrap and migration runner for all tables:
  - `model_catalog_links` (from linkage model doc)
  - `model_catalog_annotations` (from linkage model doc)
  - `model_catalog_link_events` (audit, optional)
  - `model_catalog_model_fields` (custom fields, from custom fields schema doc)
  - `manyfold_model_summary_cache` (cached Manyfold projections)
- add Docker Compose entry and config for sidecar
- add HA config entry pointing at sidecar base URL
- add HA service: `model_catalog.ping_sidecar`

Deliverables:

- Docker container runs and serves health endpoint
- DB schema created on first start
- HA confirms connectivity

### Phase 1: Custom Fields And Service Skeleton

Outcome:

- sidecar can persist archive-to-model links and custom model fields
- HA can create, accept, reject, and inspect links
- HA can read and write custom fields for a model

Issues addressed: #171 (custom fields), #190 (to_print_status and to_print_priority fields)

Work items:

- implement custom field endpoints in sidecar:
  - `GET /models/{model_id}/fields`
  - `PUT /models/{model_id}/fields/{key}`
  - `DELETE /models/{model_id}/fields/{key}`
  - `GET /models?to_print_status=queued`
- implement linkage service endpoints in sidecar:
  - `GET /archives/{archive_id}/link`
  - `POST /archives/{archive_id}/link`
  - `PUT /archives/{archive_id}/link/{link_id}/accept`
  - `PUT /archives/{archive_id}/link/{link_id}/reject`
  - `DELETE /archives/{archive_id}/link/{link_id}`
- add HA service wrappers:
  - `model_catalog.get_archive_model_link`
  - `model_catalog.create_archive_model_link`
  - `model_catalog.accept_archive_model_link`
  - `model_catalog.reject_archive_model_link`
  - `model_catalog.deactivate_archive_model_link`
  - `model_catalog.get_model_fields`
  - `model_catalog.set_model_field`
- add unit tests for storage CRUD and link review transitions
- add unit tests for custom field get/set/delete

Deliverables:

- sidecar API handles linkage and custom field operations
- HA services map to sidecar endpoints
- no Manyfold read client yet

### Phase 2: Manyfold Read Client And Model Cache

Outcome:

- sidecar can read Manyfold catalog data and cache the minimum needed projection
- HA can resolve Manyfold model summaries quickly for popup renders

Issues addressed: #224 (OEmbed investigation started; unblocks #172)

Work items:

- add Manyfold API client in sidecar with config fields for base URL, token, and SSL behavior
- implement read methods:
  - list models (with pagination)
  - get model detail
  - get file detail when needed
  - creator and collection hydration
- add sidecar cache table for Manyfold model summaries:
  - name, caption, keywords, preview URL, creator, collection, updated_at
- add sidecar endpoint: `GET /manyfold/models` (cached, paged)
- add sidecar endpoint: `GET /manyfold/models/{model_id}` (cached)
- add reconciliation from Manyfold model URL or public ID into local linkage DB
- investigate OEmbed: test Manyfold oEmbed endpoint, check CORS and CSP requirements, document fix path (#224)

Deliverables:

- sidecar caches Manyfold model summaries
- HA can resolve linked Manyfold model summaries quickly
- archive popups can display linked model name, preview, and URL
- OEmbed root cause documented and fix path identified

### Phase 3: Archive Popup Integration

Outcome:

- the print-history archive popup becomes the primary operator surface for archive-to-model linkage
- operator can link an archive to a Manyfold model with suggested candidates or manual search

Issues addressed: #178 (archive→model linkage surface), #190 (mark done when archive linked)

Work items:

- add linked-model summary section to archive popup:
  - model name, preview thumbnail, tags, collection
  - link to full Manyfold model page
  - custom fields summary: origin type, to_print_status
- add popup actions:
  - open linked model in Manyfold
  - refresh link candidates
  - accept candidate
  - reject candidate
  - manually set link (opens model search)
- show compact link state: linked / no link / candidates pending review / rejected
- when accepting a link: offer to update `to_print_status` to `done` if currently `queued`
- add lightweight manual-link entrypoint for when auto-candidates are wrong

Deliverables:

- archive popups support the core linkage workflow end-to-end
- print queue status updates on link acceptance

### Phase 4: Photo Upload Workflow

Outcome:

- operator can upload finished-print photos from mobile and attach them to a Manyfold model record

Issues addressed: #186 (photo workflow for finished models), #178 (upload photo to linked model)

Work items:

- add sidecar endpoint: `POST /models/{model_id}/photos` (multipart upload)
- sidecar uploads photo to Manyfold via API file-upload endpoint
- auto-set as preview if no preview currently set; otherwise surface "set as preview" option
- add HA service: `model_catalog.upload_model_photo`
- add HA file-upload widget in archive popup (linked model section) and model catalog card
- document iOS Shortcut flow using HA companion webhook

Deliverables:

- operator can upload a finished-print photo from the archive popup or catalog card
- photo appears in Manyfold model record
- iOS Shortcut path documented

### Phase 5: 3MF Parsing And Asset Extraction

Outcome:

- sidecar can parse `.3mf` files to extract embedded images and documents and upload them to Manyfold
- HA surfaces a "parse 3MF" action for individual models
- naming conflicts are detected before upload

Issues addressed: #173 (3MF parsing), #179 (manually added files and rescan), #221 (images via parsing), #182 (naming conflict handling)

Work items:

- add sidecar `3mf_parser` module: unzip `.3mf`, extract images and PDFs, skip geometry and slicer config
- add sidecar endpoint: `POST /models/{model_id}/parse-3mf`
  - idempotent: skip already-uploaded assets by content hash
  - `force=true` to replace assets from updated 3MF
  - returns extracted asset list and upload status
- set `3mf_parsed_at` custom field after successful parse
- auto-set Manyfold preview if none exists after parse
- add configurable `auto_parse_3mf` mode (default: off)
- add naming conflict detection: check for same name + collection before any upload and surface warning in HA
- add HA service: `model_catalog.parse_model_3mf`
- add unit tests for 3MF extraction logic

Deliverables:

- sidecar can extract and upload 3MF assets
- HA action triggers parse on demand
- auto-parse configurable per operator preference
- naming conflicts surface before upload proceeds

### Phase 6: Preview Refresh, Storage Monitoring, And Collection Hierarchy

Outcome:

- HA surfaces stale-preview warnings and a refresh action
- HA shows storage sensors for Manyfold library and preview cache
- model catalog card renders Manyfold collection hierarchy as an expandable tree

Issues addressed: #175 (refresh preview), #215 (collection hierarchy UX), #222 (storage monitoring)

Work items:

- add stale preview detection: compare Manyfold `file.updated_at` vs `preview_last_refreshed_at` custom field
- set `catalog_quality_state: needs_preview` for stale models
- add sidecar endpoint: `POST /models/{model_id}/refresh-preview`
- add sidecar endpoint: `GET /collections/tree` (full nested collection tree, cached)
- add sidecar endpoints for storage metrics:
  - `GET /storage/stats`
  - `POST /storage/trim-stale-previews`
- add HA sensors: `sensor.manyfold_library_total_mb`, `sensor.manyfold_preview_storage_mb`
- add HA action: `model_catalog.trim_stale_previews`
- add HA alert automation template for storage threshold
- update model catalog card to render expandable collection tree sidebar
- add filter toggle: show current collection only vs. include descendants

Deliverables:

- stale previews flagged and refreshable
- storage sensors visible in HA
- collection hierarchy navigable in catalog card

### Phase 7: Model Catalog Browse Card And Print Queue View

Outcome:

- HA has a full model-catalog browse card joined with custom field and archive-link context
- HA has a filtered "print queue" card showing models marked as queued

Issues addressed: #190 (print queue card surface), #215 (collection hierarchy fully integrated)

Work items:

- add model catalog browse card:
  - Manyfold preview thumbnail
  - model name, tags, collection
  - origin type badge (original / remix)
  - linked archive count and latest archive status
  - custom fields summary
  - deep links: Manyfold model page, archive popup
- add print queue card:
  - filtered to `to_print_status: queued`
  - sorted by `to_print_priority`
  - shows model name, preview, priority indicator
  - action to mark as done
- add manual search + link popup from catalog card context (replaces Phase 4 search popup that was archive-scoped)

Deliverables:

- full model catalog browse surface in HA
- print queue backlog visible as a filtered dashboard card

### Phase 8: Online Model Ingestion — Phase 1 (Provenance Tracking)

Outcome:

- operator can paste a Printables or Makerworld URL and have the source recorded in the sidecar DB without automation

Issues addressed: #183 (online model ingestion, Phase 1)

Work items:

- add sidecar endpoint: `POST /ingestion/record-source`
  - accepts `url`, detects `source_platform` from domain
  - stores as `source_download_url` and `source_platform` custom fields for a given model, or as a pending ingestion record if no model yet exists
- add sidecar endpoint: `GET /ingestion/pending` (list of source records not yet linked to a Manyfold model)
- add HA service: `model_catalog.record_model_source`
- add HA card section: "unlinked source URLs" for the operator to associate with a cataloged model when ready

Deliverables:

- operator can record source provenance before or after cataloging
- pending sources are visible and linkable in HA

### Phase 9: Online Model Ingestion — Phase 2 (Metadata Scraping)

Outcome:

- sidecar can fetch model metadata from a Printables or Makerworld URL and pre-populate a Manyfold draft

Issues addressed: #183 (online model ingestion, Phase 2)

Work items:

- add sidecar `ingestion` module: Printables and Makerworld metadata fetcher (API-first, scrape fallback)
- fetch: name, description, tags, images, creator, license
- create draft Manyfold model record via API
- populate custom fields: `source_download_url`, `source_platform`, `origin_type`
- surface draft in HA for operator review before finalizing
- add sidecar endpoint: `POST /ingestion/ingest-url`
- add HA service: `model_catalog.ingest_model_from_url`

Deliverables:

- metadata scraping from Printables/Makerworld
- operator-reviewed draft flow before Manyfold record is created

### Phase 10: Selective Manyfold Write-back

Outcome:

- sidecar can perform deterministic, operator-reviewed metadata updates to Manyfold
- only safe, limited fields are written back; no broad sync

Work items:

- implement write-back endpoint in sidecar: `POST /models/{model_id}/sync-to-manyfold`
  - supported fields: `keywords` (tags), `links`, `description` addendum
  - operator must explicitly trigger; no automatic broad sync
- add safeguards: read current Manyfold state before write, only PATCH changed fields, log operation
- add HA service: `model_catalog.sync_model_to_manyfold`
- do NOT store repo-specific structured metadata (archive IDs, sidecar fields) in Manyfold as primary truth

Deliverables:

- operator can push selected metadata changes to Manyfold without leaving HA
- safeguards prevent accidental overwrites

## Component Plan

### Sidecar modules

New Python modules under the catalog sidecar service:

- `manyfold_client.py` — HTTP client and response normalization for Manyfold API
- `bambuddy_client.py` — HTTP client for Bambuddy API (archive lookups)
- `db/` — SQLite schema, migrations, and CRUD modules:
  - `schema.py` — schema bootstrap and migration runner
  - `links.py` — linkage table CRUD
  - `fields.py` — custom fields table CRUD
  - `cache.py` — Manyfold summary cache CRUD
- `parsers/` — 3MF parsing, asset extraction
- `ingestion/` — source URL recording, metadata scraping
- `storage_monitor.py` — storage size calculation and stale preview detection
- `routes/` — FastAPI route modules grouped by concern

### HA-side modules

Recommended additions:

- `model_catalog_client.py` — sidecar REST client in HA custom component
- `model_catalog_service.py` — HA service handlers
- `model_catalog_coordinator.py` — poll-based coordinator for sensors and cache refresh
- Custom JS cards under `homeassistant/www/3d_printing/`:
  - archive popup model linkage section
  - model-catalog browse card
  - print queue card
  - model search popup

## Data Ownership Rules

### Manyfold authority

- model name, caption, description
- tags (`keywords`)
- creator, collection
- preview file selection
- model files and their metadata
- license

### Bambuddy authority

- archive facts, timestamps, completion outcome
- runtime print metrics
- archive media (printer camera, timelapse)
- spool and filament tracking per archive
- native printer queue

### Sidecar DB authority

- archive-to-model relationship and linkage state
- match confidence, review state, provenance
- all custom fields (origin type, publish status, queue flags, notes, timestamps)
- Manyfold model summary cache
- ingestion state and pending source records
- catalog quality state assessments

## Testing Plan

### Sidecar tests

- SQLite schema bootstrap and migration
- linkage CRUD and review state transitions
- custom field get/set/delete
- 3MF parser: image extraction, document extraction, geometry skip, idempotence
- Manyfold client: response normalization, error handling, auth failures
- Ingestion: URL parsing, source platform detection, scraping output shape
- Storage monitor: file size accumulation, stale preview detection

### HA tests

- services dispatch correctly to sidecar endpoints
- popup renders linked, unlinked, and candidate-review states correctly
- actions dispatch correct service calls

### End-to-end acceptance criteria

1. Operator opens an archive popup — sees "no link" state.
2. Operator opens model search, selects a Manyfold model — link is created.
3. Popup now shows linked model name, preview, and custom fields.
4. Operator uploads a finished-print photo from mobile — photo appears in Manyfold.
5. Sidecar parses model 3MF — extracted images appear in Manyfold.
6. Storage sensor shows current library size in HA.
7. Operator records a Printables source URL — provenance saved; pending ingestion appears in HA.

## Explicit Non-Goals

- no full Manyfold UI parity inside HA
- no automatic broad metadata sync between Manyfold and sidecar
- no shared or combined write authority over the Library filesystem between Manyfold and any other tool
- no replacement of Manyfold library setup, path templates, or admin workflows
- no replacement of Bambuddy archive management or printer queue
- no multi-user or sharing features (single-user personal use only)
- no time-series photo galleries per model
- no automated copying of printer camera frames to Manyfold model records
