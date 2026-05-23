# StreamDeck Upload Functionality Design

> Status: Proposed
> Last updated: 2026-05-02
> Scope: Desktop quick action from StreamDeck to submit selected local model files into Model Catalog intake and publish workflows.

## Summary

Design a deterministic desktop-triggered upload path for StreamDeck that can:

1. Resolve selected file(s) from Windows Explorer.
2. Submit upload(s) to Model Catalog intake.
3. Optionally validate and publish to local catalog.
4. Return clear success/failure feedback to operator.

The design should support the current intake semantics and be compatible with the proposed v2 multipart transport.

## User Stories

1. As an operator, I press one StreamDeck key to ingest the currently selected model file from Explorer.
2. As an operator, I can choose quick modes: queue-only, validate, publish-to-local.
3. As an operator, I get immediate feedback if upload/publish fails.
4. As an operator, retries do not create duplicate uploads accidentally.

## Architecture

StreamDeck Key Action -> Local Wrapper Script -> Selection Resolver -> Upload Client -> Model Catalog API

### Components

1. **Selection Resolver (Windows)**
- Determine focused Explorer selection.
- Normalize path(s) and validate extension preflight.

2. **Upload Client**
- Preferred: v2 multipart endpoint.
- Fallback: current v1 base64 endpoint.

3. **Workflow Executor**
- Mode A: queue-only
- Mode B: queue + validate
- Mode C: queue + publish-to-local

4. **Feedback Adapter**
- Success/Warning/Failure states for StreamDeck action display/logs.

## Operating Modes

### Mode A: Queue Only

1. Resolve selected file(s).
2. Upload to intake.
3. Return `upload_id` and status.

### Mode B: Queue + Validate

1. Queue upload.
2. Call `POST /api/intake/items/{item_id}/validate`.
3. Return validation state and warnings.

### Mode C: Queue + Publish Local

1. Queue upload.
2. Optionally validate.
3. Call `POST /api/intake/uploads/{upload_id}/publish-to-local` with optional metadata.
4. Return resulting `local_model_id` and imported asset summary.

## API Contracts

### Current Compatible Contracts

- `POST /api/intake/uploads/browser` (v1 base64)
- `POST /api/intake/items/{item_id}/validate`
- `POST /api/intake/uploads/{upload_id}/publish-to-local`

### Preferred Future Contract

- `POST /api/intake/uploads/v2/browser-multipart` (from v2 design)

## Client Configuration

Local config file (example keys):

- `base_url`
- `api_mode`: `auto | v2 | v1`
- `default_workflow`: `queue | validate | publish`
- `timeout_seconds`
- `idempotency_prefix`
- `default_metadata` (creator, tags, collections)

## Idempotency and Duplicate Prevention

1. Client generates deterministic `idempotency_key` from:
- selected canonical path(s)
- file size + mtime hash
- workflow mode
- short time bucket (optional)

2. Client retries with same key on transient failures.
3. Server returns replay response when already accepted.

## Error Handling

### Retryable

- Network timeout
- 502/503/504
- Temporary sidecar unavailability

### Non-Retryable

- Unsupported extension
- Validation errors
- `409 idempotency_conflict`
- `404 upload_not_found` after finalize failures

## Security and Trust Boundaries

1. StreamDeck script runs locally with local-user permissions.
2. API base URL should be local-network scoped.
3. If API auth is introduced later, support token in env var or encrypted local secret store.

## UX and Operator Feedback

Minimal required feedback fields:

1. Final state: `queued | validated_ready | validated_warning | published_to_catalog | failed`
2. `upload_id`
3. `local_model_id` when published
4. warning/error summary message

Optional enhancements:

- push Windows toast notifications
- StreamDeck key state color mapping
- action history log

## Telemetry and Logging

Log per invocation:

- `action_id`
- selected path(s)
- API mode used (v1/v2)
- workflow mode
- latency per step
- terminal outcome

Store local logs for troubleshooting and deterministic replay analysis.

## Test Plan

1. Single selected file happy path (all modes).
2. Unsupported extension preflight rejection.
3. API down timeout handling.
4. Publish mode with metadata injection.
5. Retry and idempotency replay behavior.
6. Multi-file selection handling (if enabled).

## Delivery Phases

### Phase SD-1 (MVP)

- Windows selection resolver
- queue-only mode
- v1 fallback support
- basic success/failure feedback

### Phase SD-2

- validate and publish modes
- metadata templating
- improved error diagnostics

### Phase SD-3

- v2 multipart primary
- idempotency and retries
- richer UI feedback and telemetry

## Open Questions

1. Should first release support only single-file selection for deterministic behavior?
2. Should publish mode be opt-in only (default queue-only)?
3. How much metadata should be user-configurable vs fixed defaults?
