# Intake Browser Upload V2 Contract Design

> Status: Proposed
> Last updated: 2026-05-02
> Scope: Replace or augment base64 JSON browser upload path with multipart and optional resumable chunk transport while preserving current intake state-machine semantics.

## Problem Statement

Current browser upload ingestion uses JSON payloads with base64 file content (`content_base64`) and server-side decode/write staging. This is functional and tested, but introduces avoidable payload inflation and memory pressure for larger 3MF uploads and batch submissions.

Current route and behavior:
- `POST /api/intake/uploads/browser`
- Content transport: JSON + base64
- Server operation: decode to bytes, stage under temporary upload directory, create intake queue entry

## Goals

1. Improve transport efficiency and reliability for larger files and multi-file batches.
2. Preserve existing intake queue and publish workflow semantics.
3. Keep migration low-risk with parallel v1 + v2 support.
4. Add deterministic idempotency and resumable upload affordances.

## Non-Goals

1. No change to downstream publish behavior (`publish-to-local`, cleanup, grouping, provenance).
2. No mandatory client migration cutover in the first delivery.
3. No change to model authority mode or Manyfold transition strategy.

## Current V1 Contract (Baseline)

### Request
- Endpoint: `POST /api/intake/uploads/browser`
- Body: JSON object with:
  - `browser_files[]` entries containing `filename`, `relative_path`, `content_base64`, optional metadata
  - `server_selections[]` optional

### Response
- Returns intake `upload_id`, queue metadata, warnings.

### Strengths
- Easy single JSON contract for browser UI.
- Existing validation and tests are stable.

### Constraints
- Base64 overhead (~33% larger transport payload).
- Full payload materialization in browser and backend request parsing path.
- Less resilient behavior when files become large.

## V2 Contract Overview

V2 introduces two compatible transport profiles:

1. **Profile A (default v2): multipart form upload**
2. **Profile B (optional): resumable upload sessions with chunking**

Both profiles produce the same downstream queue object model used by existing intake/publish routes.

## Profile A: Multipart Upload Contract

### Endpoint
- `POST /api/intake/uploads/v2/browser-multipart`

### Request (multipart/form-data)

Parts:
- `manifest` (JSON string):
  - `cleanup_policy`: `keep | delete_on_verified | replace_with_stub`
  - `server_selections[]` (optional)
  - `grouping_strategy` (optional)
  - `preserve_folder_structure` (optional)
  - `group_title_source` / `group_title` (optional)
  - `idempotency_key` (optional but recommended)
- `files[]` (binary file parts):
  - each part includes filename
  - optional paired metadata header or sidecar `files_meta[]` mapping in `manifest`

### Response
- Same shape as v1 where possible:
  - `success`, `upload_id`, `status`, `verification_status`, `cleanup_policy`
  - `source_entry_count`, `browser_file_count`, `warnings`, `created_at`
- Additions:
  - `contract`: `intake-upload-v2-multipart`
  - `idempotency`: `{ key, replayed }`

### Server Semantics

1. Parse and validate `manifest` first.
2. Stream each file part to staged storage; avoid loading full binary into memory.
3. Create normalized `source_entries_json` exactly like v1 outcome.
4. Reuse existing queue validation/state transition logic.

## Profile B: Resumable Upload Sessions (Optional)

### Endpoints
- `POST /api/intake/uploads/v2/sessions`
- `PUT /api/intake/uploads/v2/sessions/{session_id}/parts/{part_number}`
- `POST /api/intake/uploads/v2/sessions/{session_id}/finalize`
- `DELETE /api/intake/uploads/v2/sessions/{session_id}`

### Notes

- Intended for unstable networks or very large files.
- Stores temp part metadata and checksums.
- Finalize composes staged file(s), then creates standard intake queue upload.
- Can be implemented after Profile A; not required for first v2 release.

## Idempotency Design

### Keying

- Client sends `idempotency_key` per logical submission.
- Server stores `(idempotency_key, payload_signature, created_upload_id, created_at)` in a dedicated table.

### Behavior

1. Same key + same signature within TTL: return original response (`replayed=true`).
2. Same key + different signature: `409 idempotency_conflict`.
3. Missing key: process normally.

## Data Model Additions

Proposed tables:

1. `intake_upload_idempotency`
- `idempotency_key` unique
- `payload_signature`
- `upload_id`
- `created_at`
- `expires_at`

2. Optional resumable tables (if Profile B enabled)
- `intake_upload_sessions`
- `intake_upload_session_parts`

## Validation and Security

1. Keep existing path sanitization and supported extension checks.
2. Maintain allowlisted source root constraints for server selections.
3. Add max part size and max total upload limits configurable by env.
4. Reject unknown file/manifest mapping combinations deterministically.
5. Preserve existing cleanup policy guardrails.

## Backward Compatibility and Migration

1. Keep v1 endpoint unchanged during migration window.
2. Add feature flag to enable v2 route in stages.
3. Browser card can use capability probe (`/config` or explicit `GET /api/intake/capabilities`) to select v2.
4. StreamDeck and other automation clients can adopt v2 first without forcing HA card migration.

## Observability

Add structured telemetry fields:
- `transport_mode`: `v1_base64 | v2_multipart | v2_resumable`
- `payload_bytes_raw`
- `payload_bytes_encoded` (v1 only)
- `upload_duration_ms`
- `staging_write_duration_ms`
- `warnings_count`

## Performance Expectations

Expected improvements vs v1 for larger files:

1. Lower network bytes for equivalent payload.
2. Lower request parsing memory pressure.
3. Better success rate for large uploads.

No guaranteed meaningful latency win for very small files.

## Rollout Plan

1. Implement Profile A multipart route and idempotency table.
2. Add integration tests paralleling existing browser upload tests.
3. Update browser card with feature flag/capability fallback to v1.
4. Roll out to StreamDeck uploader using v2 first.
5. Evaluate telemetry; decide whether Profile B resumable is needed.

## Test Plan (Minimum)

1. Multipart single-file happy path.
2. Multipart multi-file with nested relative paths.
3. Mixed browser files + server selections.
4. Idempotency replay behavior.
5. Idempotency conflict behavior.
6. Oversize and unsupported extension handling.
7. Staging cleanup on partial failures.
8. Publish-to-local compatibility unchanged from v1.

## Open Questions

1. Do we require resumable/chunking in initial release, or defer until telemetry says needed?
2. Should v2 keep automatic `delete_on_verified` behavior for browser-staged files (recommended: yes, for parity)?
3. Should we expose a dedicated capabilities endpoint or fold into existing `/config` output?
