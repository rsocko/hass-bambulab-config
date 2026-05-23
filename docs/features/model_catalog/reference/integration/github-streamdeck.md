# GitHub Work Items: Upload V2 + StreamDeck Integration

> Status: Proposed issue set
> Last updated: 2026-05-02
> Purpose: Track implementation from design to delivery for intake upload v2 transport and StreamDeck desktop upload workflow.

## Linked Design Docs

- `docs/features/model_catalog/design/integration/intake-browser-upload.md`
- `docs/features/model_catalog/design/integration/streamdeck-upload.md`

Cross-cutting UI follow-on:

- issue #1290 should be implemented against the progress/busy-state contract added to the v2 upload design and intake wizard docs.

## Labels (Suggested)

- `model_catalog`
- `integration`
- `api`
- `performance`
- `desktop-automation`
- `streamdeck`
- `phase-5`

## Epic 1: Intake Upload V2 Transport

### Issue 1.1
Title: Model Catalog: Add v2 multipart browser upload endpoint

Acceptance Criteria:
- [ ] Add `POST /api/intake/uploads/v2/browser-multipart`
- [ ] Accept multipart `files[]` + JSON `manifest`
- [ ] Stage uploaded files without base64 decoding path
- [ ] Reuse existing queue entry semantics (`upload_id`, status, warnings)
- [ ] Preserve source metadata (`relative_path`, grouping hints)
- [ ] Add OpenAPI docs and endpoint examples

### Issue 1.2
Title: Model Catalog: Add intake upload idempotency support

Acceptance Criteria:
- [ ] Add DB migration for idempotency table
- [ ] Enforce key + payload signature replay behavior
- [ ] Return deterministic replay response with `replayed=true`
- [ ] Return `409` on key/signature mismatch
- [ ] Add unit + integration tests for replay/conflict

### Issue 1.3
Title: Model Catalog: Add v2 upload telemetry and diagnostics

Acceptance Criteria:
- [ ] Emit transport mode field (`v1_base64`/`v2_multipart`)
- [ ] Capture upload timing metrics
- [ ] Capture payload byte counters
- [ ] Add diagnostics visibility in existing service diagnostics surface
- [ ] Validate no sensitive content in logs
- [ ] Expose enough phase/timing metadata to support #1290 progress UI without logging sensitive file content

### Issue 1.4
Title: Model Catalog: Browser uploader feature-flagged v2 adoption with v1 fallback

Acceptance Criteria:
- [ ] Add capability probe or config gate for v2 route
- [ ] Keep v1 route unchanged
- [ ] Browser uploader selects v2 when available
- [ ] Automatic fallback to v1 on unavailable/unsupported v2
- [ ] Add compatibility tests for mixed-mode deployments
- [ ] Keep the wizard progress shell consistent across v2 primary and v1 fallback, degrading from byte-progress to phase-progress when necessary

### Issue 1.4a
Title: Model Catalog: Intake wizard progress, busy-state, and cancellation affordances

Acceptance Criteria:
- [ ] Browser upload shows determinate transfer progress when transport exposes real byte counts
- [ ] Validate and Commit surfaces show phase-based processing states for server-side work
- [ ] Wizard actions that would mutate inputs are disabled while upload/validate/commit is actively running
- [ ] Operator can cancel before irreversible publish starts; UI clearly indicates when cancel is no longer available
- [ ] Completion and failure states link cleanly into Job History/result entities instead of leaving the wizard in an ambiguous busy state

Notes:
- This issue depends on the queue/status metadata from 1.3 and the browser adoption shell in 1.4.
- This is the implementation bridge for GitHub issue #1290.

### Issue 1.5
Title: Model Catalog: Optional resumable upload session contract (deferred capability)

Acceptance Criteria:
- [ ] Define and implement session create/part/finalize routes
- [ ] Verify part checksum and assemble staged file deterministically
- [ ] Ensure finalize produces standard queue upload semantics
- [ ] Add cleanup/expiry for abandoned sessions
- [ ] Add performance and resilience tests for large file scenarios

## Epic 2: StreamDeck Desktop Upload Workflow

### Issue 2.1
Title: StreamDeck uploader MVP: Windows Explorer selection resolver + queue-only mode

Acceptance Criteria:
- [ ] Implement robust selected-file discovery from focused Explorer window
- [ ] Validate path and extension preflight before API call
- [ ] Submit queue request to sidecar intake endpoint
- [ ] Return terminal status and `upload_id`
- [ ] Add local structured logging

### Issue 2.2
Title: StreamDeck uploader: validate and publish-to-local workflow modes

Acceptance Criteria:
- [ ] Add `validate` mode with intake validate call
- [ ] Add `publish` mode with publish-to-local call
- [ ] Support metadata payload injection (name, tags, creator, collections)
- [ ] Return `local_model_id` and summary in success path
- [ ] Add mode-specific failure handling

### Issue 2.3
Title: StreamDeck uploader: idempotent retry and transient failure policy

Acceptance Criteria:
- [ ] Generate deterministic idempotency keys client-side
- [ ] Retry transient network/server errors with bounded attempts
- [ ] Preserve same key on retries
- [ ] Distinguish replay success vs true duplicate conflicts
- [ ] Add retry policy tests

### Issue 2.4
Title: StreamDeck UX feedback: status mapping and operator notifications

Acceptance Criteria:
- [ ] Map key states for success/warning/failure
- [ ] Include concise failure messages suitable for key display
- [ ] Optional Windows toast integration for detailed output
- [ ] Add action history log references to the UI output

### Issue 2.5
Title: StreamDeck uploader: v2 multipart primary with v1 fallback

Acceptance Criteria:
- [ ] Prefer v2 multipart route when available
- [ ] Fallback to v1 base64 route for compatibility
- [ ] Add capability detection and explicit override config
- [ ] Verify parity of queue/publish outcomes across modes

## Cross-Cutting QA and Release Work

### Issue 3.1
Title: Integration test suite expansion for v2 and StreamDeck workflows

Acceptance Criteria:
- [ ] Add backend tests for multipart + idempotency
- [ ] Add contract tests for response parity between v1 and v2
- [ ] Add end-to-end script tests for StreamDeck workflow wrapper
- [ ] Validate cleanup policies and publish compatibility remain correct

### Issue 3.2
Title: Documentation updates for upload transport and desktop automation

Acceptance Criteria:
- [ ] Update API reference to accurately describe current and v2 contracts
- [ ] Add StreamDeck usage and troubleshooting guide
- [ ] Add migration notes from v1 base64 to v2 multipart
- [ ] Add rollback guidance and compatibility matrix

## Dependency Order

1. 1.1 -> 1.2 -> 1.3 -> 1.4
2. 2.1 can start in parallel with 1.1
3. 2.5 depends on 1.1 and 1.4
4. 3.1 and 3.2 complete before production rollout

## Suggested Milestones

1. Milestone A: V2 backend route + idempotency
2. Milestone B: StreamDeck MVP queue/validate/publish
3. Milestone C: v2 primary adoption + docs + full QA

## Optional GitHub CLI Commands

Use from repo root if `gh` is authenticated:

```bash
# Example
# gh issue create --title "Model Catalog: Add v2 multipart browser upload endpoint" --body-file /tmp/issue-1-1.md --label model_catalog --label api --label performance
```

Each issue body in this document can be copied directly into issue creation commands.
