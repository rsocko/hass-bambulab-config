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

### Unified Queue

- `POST /api/unified-queue/entries`
- `GET /api/unified-queue/entries/{queue_entry_id}`
- `GET /api/unified-queue/entries`
- `PATCH /api/unified-queue/entries/{queue_entry_id}`
- `DELETE /api/unified-queue/entries/{queue_entry_id}`
- `GET /api/v1/queues/{printer_id}/entries`
- `POST /api/v1/queues/{printer_id}/add`

`GET /api/v1/queues/{printer_id}/entries` query parameters:

- `state`: comma-separated states (`idea,todo,ready,started,blocked,done`)
- `source_kind`: comma-separated source kinds (`catalog_model,working_group,working_file,idea`)
- `sort`: `rank`, `created_at`, or `duration_bucket` with optional `:asc|:desc` (default `rank:asc`)
- `order`: optional override direction (`asc|desc`) when `sort` does not include suffix
- `limit`: max results per page (default `50`, max `200`)
- `offset`: pagination offset (default `0`)

Response includes:

- `entries`: paged queue entries
- `pagination`: `{ limit, offset, count, total, has_more }`
- `filters`: normalized applied filters
- `sort`: resolved sort field and direction

`POST /api/v1/queues/{printer_id}/add` request body:

- `source_kind`: required (`catalog_model`, `working_group`, `working_file`, `idea`)
- `source_id`: required unless `source_kind=idea`
- `copies`: optional integer (default `1`, min `1`)
- `duration_bucket`: optional (`quick`, `medium`, `overnight`, `marathon`, `unknown`; accepts aliases like `2-4h`)
- `ams_fit`: optional boolean (maps to `ams_ready_score`)
- `overnight_fit`: optional boolean (maps to `overnight_fit_score`)
- `state`: optional queue state override (default `todo`)
- `rank`: optional rank override (lower ranks are scheduled first)
- `queue_notes`: optional notes

Response:

- `201 Created`
- `Location` header set to `/api/unified-queue/entries/{queue_entry_id}`
- body includes `{ success, contract, printer_id, entry }`

Implementation note (SQLite foreign keys):

- Unified queue delete behavior relies on schema-level ON DELETE CASCADE relationships from `unified_queue_entries` to child tables such as `unified_queue_file_units` and `unified_queue_plate_units`.
- In SQLite, foreign-key enforcement is per-connection and disabled by default unless explicitly enabled.
- Sidecar DB connections must enable `PRAGMA foreign_keys = ON` in the shared connection factory; migration-time PRAGMA settings do not persist as a database-wide default for later runtime connections.
- If this PRAGMA is not enabled on runtime connections, deleting a queue entry can leave orphaned child rows even when CASCADE constraints exist in the schema.

Unified contract note:

- Legacy queue payload keys (`queue_status`, `queue_priority`, `print_file`, `print_settings`) are rejected on this endpoint to avoid overlapping queue semantics.
- The transitional `POST /api/unified-queue/migrate-legacy` bridge has been retired after cutover completion.
- One-time migration/validation steps are captured in `docs/features/model_catalog/unified-queue-cutover-runbook.md`.

Home Assistant package contract (UQ cutover):

- `rest_command.model_catalog_update_model_queue` has been removed.
- `model_catalog.queue_model_for_print` has been removed from package service declarations.
- Queue actions in dashboard cards and automations use unified queue commands only:
  - `rest_command.model_catalog_list_unified_queue_entries`
  - `rest_command.model_catalog_add_unified_queue_entry`
  - `rest_command.model_catalog_update_unified_queue_entry`
  - `rest_command.model_catalog_delete_unified_queue_entry`
- `rest_command.model_catalog_search_models` no longer forwards legacy queue parameters (`to_print_status`, `to_print_priority*`).

Model/search filtering supported by `GET /api/models` and `GET /api/models/search`:

- `taxonomy_origin_class` (`reprint`, `remix_or_tweak`, `custom_unique`)
- `taxonomy_change_axes` (`color`, `model`, `other`)
- `model_favorite`
- `model_rating`
- `colors_used` (Phase 3 baseline: hex-first; later phase may add optional `filament_id` linkage)

Frequents/Favorites Layer 2 contract:

- See `frequents-favorites-layer2-derivation-rules.md` for weighting, threshold, and tunable parameters (`frequent_window_days`, `frequent_min_prints`, `frequent_backfill_weight`).

Deprecation and migration timeline:

- Historical queue interfaces and migration milestones are documented in `docs/features/model_catalog/unified-queue-deprecation-timeline.md`.

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

### Working Groups (Bulk Intake)

- `POST /working-groups/bulk-discover`
- `POST /working-groups/bulk-import`

Compatibility aliases:

- `POST /api/working-groups/bulk-discover`
- `POST /api/working-groups/bulk-import`

`bulk-discover` request shape:

- `folder_path` (required)
- `grouping_strategy` (`by-folder`, `by-root`, `flat`)

`bulk-discover` behavior:

- scans nested folders for `.3mf`, `.stl`, `.obj`
- returns proposed groups and file lists without writing DB rows
- computes SHA256 hashes and returns duplicate warnings when a file hash already exists in `working_items`

`bulk-import` request shape:

- `proposals` (required list from reviewed discover output)
- `source_folder` (optional but recommended for metadata)
- `grouping_strategy` (optional; persisted into group discovery metadata)
- `discovery_timestamp` (optional; defaults to import-time if omitted)
- `stage` (optional default stage for created groups)

`bulk-import` behavior:

- supports proposal actions: `import`, `merge`, `skip`
- deduplicates by hash against existing inventory (`working_items.file_hash`, `model_catalog_assets.file_hash`, in-flight intake queue) and within the same import batch
- persists discovery metadata on each created `working_group`
- returns created groups/items plus skipped duplicate and failed-file details

### Intake Queue + Source Selection

Post-Manyfold note:

- The queue, source-selection, and cleanup-policy routes below remain valid and shipped.
- `POST /api/intake/uploads/{upload_id}/publish-to-local` is the authoritative publish path.
- `POST /api/intake/uploads/{upload_id}/upload-to-manyfold` is retained only as a legacy transition adapter and should not be used for new primary workflows.
- The active migration direction is sidecar-owned catalog authority as documented in `post-manyfold-transition-plan-2026-04.md`.

Route family:

- `POST /api/intake/uploads`
- `GET /api/intake/uploads`
- `DELETE /api/intake/uploads/{upload_id}`
- `POST /api/intake/uploads/{upload_id}/publish-to-local`
- `POST /api/intake/uploads/{upload_id}/upload-to-manyfold`
- `POST /api/intake/uploads/{upload_id}/cleanup`
- `GET /api/source-filesystems`
- `GET /api/source-filesystems/browse`
- `POST /api/source-filesystems/select`

Current behavior:

- browser local files are accepted via multipart upload into a temporary sidecar queue
- sidecar-mounted server roots are browsed and selected through explicit allowlisted roots
- source selection supports explicit files, folders, or mixed file+folder batches
- folder source entries support traversal control: `recurse` (bool)
- `POST /api/intake/uploads/{upload_id}/publish-to-local` is the active authoritative sink for reviewed queue/source inputs and creates or updates sidecar-owned local curated models plus typed local assets
- `POST /api/intake/uploads/{upload_id}/upload-to-manyfold` remains available only for legacy/transition workflows that still exercise the historical Manyfold adapter
- local publish persists queue provenance on the resulting local model through source-origin fields plus sidecar custom-field history (`intake_queue_upload_id`, `intake_source_entries`, `intake_publish_history`)
- legacy upload verification prefers Manyfold-reported hashes and falls back to filename+size matching when hashes are unavailable
- legacy upload success persists queue `file_hashes_json`, `manyfold_file_ids_json`, `verification_status`, and advances queue status from `uploaded_unverified` to `verified`
- local publish success copies imported files into sidecar-owned asset storage, persists file hashes into `file_hashes_json`, and advances queue status through `uploading -> uploaded_unverified -> verified`
- when `cleanup_policy` is `delete_on_verified` or `replace_with_stub`, cleanup runs only after verified queue completion and advances status to `cleanup_done` or `cleanup_failed`
- `POST /api/intake/uploads/{upload_id}/cleanup` retries cleanup for uploads already in `verified` or `cleanup_failed`
- failed uploads persist partial queue metadata, write an error payload, and transition the queue record to `failed`
- matching `working_items` rows persist provenance metadata in `source_metadata_json`; legacy Manyfold adapter runs also add a `manyfold_destination` object
- `replace_with_stub` overwrites the original file with a small audit marker containing the upload id and any available verification destination metadata
- optional source cleanup policies are applied only after verified processing

Source entry shape:

- `sources[]` where each item is either:
	- `{ "type": "file", ... }`
	- `{ "type": "folder", "path": "...", "recurse": true|false }`

Source cleanup policies:

- `keep` (default)
- `delete_on_verified`
- `replace_with_stub`

Planned safeguards:

- verification required before destructive source actions (hash preferred)
- destructive actions limited to configured allowed roots
- cleanup outcomes returned in import summaries and audit events

## Planned API Appendix

The routes below are **planned/draft contracts**, not currently shipped endpoints.

They are documented here because the Phase 3.5 `.3mf` parser/cache design now has a concrete API draft and should be discoverable from the main reference.

Source draft:

- [planning/3mf-cache-draft.md](../planning/3mf-cache-draft.md)

### 3MF Analysis

Planned route family:

- `POST /api/3mf-analysis/analyze`
- `GET /api/3mf-analysis/runs/{analysis_run_id}`
- `GET /api/3mf-analysis/by-hash/{source_sha256}`
- `GET /api/3mf-analysis/runs/{analysis_run_id}/previews`
- `POST /api/3mf-analysis/previews/{preview_id}/promote`
- `GET /api/3mf-analysis/runs/{analysis_run_id}/resources`
- `POST /api/3mf-analysis/resources/{resource_id}/selection`

Draft intent:

- provide a file-hash-keyed `.3mf` analysis cache reusable across bulk analyze, Working detail, publish-time preview selection, and later backfill workflows
- inventory preview candidates and allowlisted companion resources without surfacing raw model payload members as user-facing support files
- keep embedded `.3mf` provenance hints in the analysis cache while leaving fetched public-source metadata to later provenance flows

Draft cache entities:

- `three_mf_analysis_runs`
- `three_mf_analysis_previews`
- `three_mf_analysis_resources`

Draft refresh modes:

- `skip_if_current`
- `rebuild_cache_only`
- `replace_derived_artifacts`
- `full_refresh`

Boundary note:

- Phase 3.5 owns parser/cache and bulk-enrichment reuse
- Phase 5 owns publish-time preview/supporting-asset application
- Phase 7 owns public-source provenance resolution and refresh

### Slicing And Archive Preparation

Planned route family:

- `GET /api/slicer/providers`
- `POST /api/slice-jobs`
- `GET /api/slice-jobs/{slice_job_id}`
- `POST /api/slice-jobs/{slice_job_id}/overrides`
- `POST /api/slice-jobs/{slice_job_id}/execute`
- `POST /api/slice-jobs/{slice_job_id}/commit-archive`

Draft intent:

- orchestrate a reviewable source-`.3mf` to canonical-archive workflow from Model Catalog surfaces
- reuse the planned `.3mf` analysis cache plus existing intake queue and source selection routes
- keep actual slicing provider execution behind a stable sidecar contract so the UI can work with either upstream Bambuddy slicer mode or a future compatible local worker
- use Filament Catalog linkage for deterministic validation suggestions and filament substitution, not as a full preset-management clone

Boundary note:

- these are orchestration endpoints, not a replacement for Bambuddy canonical archive upload
- source-only provenance attachment remains distinct from canonical archive creation
- raw `.gcode` synthesis remains outside this route family

Design reference:

- [Print History Slicer Integration Design](../print-history-slicer-integration-design.md)

## Source of Truth

The live OpenAPI document is the contract source of truth:

- `/openapi.json`

Use this document for generated clients, schema checks, and endpoint validation in tests.