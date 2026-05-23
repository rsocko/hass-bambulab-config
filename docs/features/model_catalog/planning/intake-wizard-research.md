# Intake Wizard Lifecycle, Cancellation, and Cleanup Behavior

> **Status**: Research Report  
> **Created**: 2026-06-14  
> **Scope**: What happens to queue records and uploaded files when a wizard session is interrupted, discarded, or abandoned.

---

## Executive Summary

The model catalog intake wizard has a **client-only cancellation model**. When the operator closes or discards a wizard session, **all cleanup is purely frontend JavaScript state resets** — no backend API calls are made to delete queue records, remove staged files, or roll back any server-side artifacts. This creates a gap: if a wizard session reaches the point where server-side state is created (queue record INSERT, staged browser upload files on disk), those artifacts persist indefinitely after wizard dismissal.

The system compensates for this gap through:
1. A manual `DELETE /api/intake/uploads/{upload_id}` endpoint (restricted to `queued` and `failed` status records)
2. A CLI `cleanup` tool with nuclear-scope `reset-db` and `reset-all` commands
3. An operational recommendation in the README to "clear stale queue files only after confirming no active items remain"

There is **no automatic or scheduled cleanup of orphaned queue records or staged files**.

---

## Area 1: Frontend Wizard Cancellation & Discard Behavior

### Key Files
- [model-catalog-intake-home-card.js](../../../homeassistant/www/3d_printing/model_catalog/model-catalog-intake-home-card.js)

### `_closeWizard(options)` — Lines 1036–1063

This is the single exit path for wizard dismissal (both user-initiated and programmatic). It performs **exclusively client-side state resets**:

```javascript
_closeWizard(options) {
    var force = options && options.force;
    if (!force && this._isWizardDirty()) {
      this._wizardCloseConfirmOpen = true;
      this._render();
      return;
    }
    this._wizardOpen = false;
    this._wizardMode = "";
    this._wizardStep = 1;
    this._cleanupPolicyValue = null;
    this._commitMode = 'queue';
    this._destinationChoice = 'curated';
    this._selected = {};
    this._clearBrowserFiles();
    // ... direct-launch popup close
}
```

**Critical finding**: There is zero communication with any backend API. No `DELETE` call, no `POST /cancel`, no cleanup signal of any kind.

### `_clearBrowserFiles()` — Lines 524–530

Revokes browser-local `URL.createObjectURL()` preview URLs and empties the in-memory file array. This only affects browser blob memory, not any files already uploaded/staged on the server.

```javascript
_clearBrowserFiles() {
    this._revokeBrowserPreviewUrls(this._browserFiles);
    this._browserFiles = [];
    this._excludedBrowserKeys = {};
}
```

### `disconnectedCallback()` — Line 131

Called when the custom element is removed from the DOM. Only revokes browser preview object URLs — no backend cleanup:

```javascript
disconnectedCallback() {
    this._revokeBrowserPreviewUrls(this._browserFiles);
}
```

### Close Confirmation Dialog — Lines 1023–1031

When the wizard has dirty state (`_isWizardDirty()` returns true), the close action shows a confirmation dialog with "Keep Editing" / "Discard And Close" buttons. The "Discard And Close" button calls `_closeWizard({ force: true })`, which performs the same client-only reset.

### `_isWizardDirty()` — Lines 990–999

Returns `true` if any of:
- Wizard step > 1 (user navigated past source selection)
- Server browse selections exist
- Browser files have been staged

### `_handleClick` Action Routing — Lines 1822–1923

The relevant action mappings:
- `'close-wizard'` → `_closeWizard()` (with dirty check)
- `'confirm-close-wizard'` → `_closeWizard({ force: true })` (bypass dirty check)
- `'dismiss-close-confirm'` → `_dismissWizardCloseConfirm()` (return to editing)
- `'commit-wizard'` → `_submitServerSelections()` (actual submission)

### `_submitServerSelections()` — Lines 1282–1458

This is the **successful completion path**. It:
1. Calls backend APIs to create queue records (`rest_command.model_catalog_select_source_filesystem_entries` or `uploadBrowserFilesWithFallback`)
2. Calls validation API (`rest_command.model_catalog_validate_intake_item`)
3. Optionally calls publish API (`rest_command.model_catalog_publish_to_local` or `model_catalog_publish_to_working`)
4. On success, resets all client state (same variables as `_closeWizard`)
5. On **error**, only sets `this._error` for display — does NOT clean up any server-side artifacts created in steps 1–2

This means if the submit flow **partially succeeds** (queue record created, validation fails, user sees error, then closes wizard), the queue record and any staged files persist on the server.

---

## Area 2: Queue Record Lifecycle (Backend)

### Key Files
- [intake_queue.py](../../../sidecars/model_catalog/app/routers/intake_queue.py)
- [intake_cleanup.py](../../../sidecars/model_catalog/app/routers/intake_cleanup.py)
- [intake_verification.py](../../../sidecars/model_catalog/app/routers/intake_verification.py)

### Queue Record Creation

Records are inserted into `intake_queue_uploads` via `_create_intake_queue_upload_record()` (line 767). Every wizard submission that reaches the backend creates a record with:
- `upload_id`: UUID
- `status`: `"queued"`
- `source_entries_json`: serialized list of file/folder selections
- `cleanup_policy`: operator's chosen policy
- `created_at` / `updated_at`: timestamps

### State Machine

The queue follows a strict state machine defined in `VALID_STATUS_TRANSITIONS` (lines 65–74):

```
queued → uploading → uploaded_unverified → verified → cleanup_pending → cleanup_done
                                                    → cleanup_failed
(any) → failed
```

### DELETE Endpoint — `DELETE /api/intake/uploads/{upload_id}` (Line 1816)

The **only** way to delete a queue record via API:
- **Restricted to `queued` and `failed` statuses only**
- Records in `uploading`, `uploaded_unverified`, `verified`, `cleanup_pending`, etc. cannot be deleted via this endpoint (returns HTTP 409)
- When deleting, also removes browser upload staging directories via `_browser_upload_stage_directories()`

### No Auto-Cleanup Mechanism

There is no TTL, scheduled task, cron job, or background process that automatically detects and removes orphaned queue records. The only TTL-based cleanup is for **idempotency keys** (`intake_upload_idempotency` table, 24-hour TTL at line 85), not for queue records themselves.

### Browser Upload Staging

Browser files are staged to disk at `{db_parent}/intake_browser_uploads/{upload_id}/` (line 88). The `_browser_intake_upload_storage_root()` function (line 87) resolves this path relative to the database directory.

Staging directory structure:
- Each upload gets its own UUID-named subdirectory under `intake_browser_uploads/`
- Files are written during the `POST /api/intake/uploads/browser` or `POST /api/intake/uploads/v2/browser-multipart` endpoints
- These directories persist until explicitly cleaned up by the DELETE endpoint or CLI tools

### Cleanup Policy Execution

Source cleanup (deleting or stubbing original files) only runs:
- Via `POST /api/intake/uploads/{upload_id}/cleanup` endpoint
- Only when `verification_status` = `"pass"` and `status` in `{"verified", "cleanup_failed"}`
- Policy `"keep"` skips all file operations
- Policy `"delete_on_verified"` deletes source files
- Policy `"replace_with_stub"` replaces source files with metadata `.stub.txt` files

This cleanup is about **source files** (the original files the operator selected), not about the queue record or staging directory themselves.

---

## Area 3: CLI Cleanup Tools

### Key File
- [cleanup.py](../../../sidecars/model_catalog/cli/cleanup.py)

The CLI provides three commands, all **manual and destructive**:

### `reset-db`
- Deletes all rows from 10 database tables (including `intake_queue_uploads`)
- Preserves filesystem zones
- Requires triple confirmation (phrase + token + date) unless `--yes` is passed
- Dry-run by default

### `reset-all`
- Deletes all DB rows AND filesystem zone contents
- Operates on three zones: `curated`, `working`, `inbox`
- The `inbox` zone maps to `settings.intake_source_roots[0]`
- **Does NOT explicitly target the `intake_browser_uploads` staging directory** — this is only cleaned if it falls under one of the configured zones

### `cleanup`
- Granular version: choose scope (`db`, `files`, `both`), specific tables, specific zones
- Same triple confirmation, same dry-run default

### Gap: No Targeted Orphan Cleanup

None of these CLI commands offer a surgical "clean up abandoned queue records and their staging directories" mode. They are all-or-nothing reset tools. There is no `cleanup-orphans` or `prune-stale-uploads` subcommand.

---

## Area 4: What Persists After Wizard Interruption

### Scenario Analysis

| Interruption Point | Queue Record? | Staged Files? | Source Files? |
|---|---|---|---|
| Before Step 1 commit (browsing, selecting) | No | No | Untouched |
| After browser file selection but before submit | No | No (files only in browser memory) | Untouched |
| During `_submitServerSelections()` — before backend call | No | No | Untouched |
| After queue record created but before validation | **Yes** (`queued` status) | **Yes** (for browser uploads) | Untouched |
| After validation succeeds but before publish | **Yes** (`queued` status) | **Yes** (for browser uploads) | Untouched |
| After publish succeeds | **Yes** (status advanced) | **Yes** (for browser mode) | Moved/copied to destination |
| After publish fails mid-way | **Yes** (`queued` status) | **Yes** (for browser uploads) | Partially moved |
| User closes wizard after error in submit flow | **Yes** | **Yes** (for browser uploads) | Depends on error point |
| User closes wizard after successful submit | No (wizard resets) | No (cleared) | Depends on cleanup policy |
| Browser tab/page refresh during wizard | No record if pre-submit | **Yes** if post-submit | Untouched if pre-submit |

### Key Takeaway

The critical window is **after the backend creates the queue record but before the wizard completes successfully**. This includes:
1. Validation failure → user sees error → closes wizard → queue record orphaned
2. Publish failure → user sees error → closes wizard → queue record orphaned  
3. Network error during any backend call → queue record may or may not exist
4. Browser crash/refresh after submit call started → queue record likely exists

In all of these cases:
- The queue record persists with `status = "queued"` in the SQLite database
- For browser uploads, staged files persist on disk under `intake_browser_uploads/{upload_id}/`
- Server-mode selections leave no staged files (they reference original paths)

### Recovery Path

The operator can recover by:
1. Viewing the queue via the intake home card (which shows queue health KPIs including `queued` count)
2. Manually deleting orphaned records via the DELETE endpoint (only for `queued`/`failed` status)
3. Using CLI `reset-db` or `cleanup` for bulk cleanup (destructive)

There is no automated "detect and offer to clean up" workflow in the UI.

---

## Area 5: Design Documentation Coverage

### [intake-inbox-design.md](/docs/features/model_catalog/design/intake-inbox.md)

The design document covers:
- Wizard as the canonical intake experience (wizard-first, queue demoted to background)
- Locking and exit behavior during long-running operations (lines 89–99)
- Progress phase model for busy states
- Cancel affordance design: "show `Cancel` only while the operation is still safely abortable"
- Post-handoff visibility: "the current job must remain discoverable in Job History"

**Gap**: The design document does not address:
- What happens to queue records when the wizard is dismissed after partial backend execution
- How orphaned staging directories should be detected and cleaned
- Whether there should be an automatic TTL-based cleanup for stale `queued` records
- Recovery UI for abandoned wizard sessions

### [intake-state-machine.md](../reference/intake-state-machine.md)

Covers the item-level state machine (`submitted` → `validated_ready` → `grouped_new`/`published_to_catalog`), but this is the **intake item** state machine, not the **queue upload** state machine. The queue upload state machine (`queued` → `uploading` → `verified` → ...) is defined in code only (`VALID_STATUS_TRANSITIONS` in `intake_queue.py`).

The state machine document includes "Terminal State Recovery (Admin Override Only)" for reopening terminal items, but does not address queue upload record lifecycle or orphan handling.

### [import-flow-diagrams.md](/docs/features/model_catalog/reference/import-flows.md)

Contains flow diagrams for the import process. References cleanup policy as part of wizard planning. Does not address interruption, cancellation, or orphan scenarios.

### Sidecar README

The [sidecar README](../../../sidecars/model_catalog/README.md) includes the only explicit operational guidance about stale files:

> "clear stale queue files only after confirming no active `queued`, `uploading`, or `cleanup_failed` items remain"

This acknowledges the orphan problem exists but offers only a manual, caveat-laden operational recommendation.

### Test Coverage

The [validation test report](../../../tests/sidecars/model_catalog/VALIDATION_TEST_REPORT.md) includes unchecked items:
- `[ ] Test orphaned record cleanup`
- `[ ] Test orphaned record detection via API`

These are listed as planned but unimplemented test cases.

---

## Summary of Gaps

1. **No backend cleanup on wizard close**: `_closeWizard()` makes zero API calls. Any server-side artifacts from a partial submit persist.

2. **No automatic orphan detection**: No TTL, no scheduled cleanup, no background task scans for stale `queued` records.

3. **No targeted orphan cleanup tool**: CLI tools are all-or-nothing resets. No surgical `prune-stale-uploads` or `cleanup-orphans` command.

4. **Submit error path doesn't clean up**: When `_submitServerSelections()` catches an error, it only sets `this._error` for display. It does not attempt to delete the queue record that may have been created before the error.

5. **Browser upload staging directory not cleaned on close**: Staged files in `intake_browser_uploads/{upload_id}/` are only cleaned by the DELETE endpoint or CLI reset. Wizard close does not trigger cleanup.

6. **DELETE endpoint status restriction**: The API only allows deleting `queued` and `failed` records. If a record somehow advances to `uploading` or `uploaded_unverified` without completing, it cannot be deleted via API without first transitioning to `failed`.

7. **Design docs don't address the gap**: The intake design documents cover busy states and progress phases but do not specify cancellation cleanup or orphan recovery behavior.

8. **No UI for orphan recovery**: The queue health KPIs show counts, but there's no "clean up abandoned sessions" action or warning for stale records.
