# Archive Recovery `n8n` Workflow Design

## Purpose

Define the recommended `n8n` workflow architecture for recovering Bambuddy fallback archives without changing Bambuddy itself.

This document is design-only. It defines workflow structure, contracts, retry policy, and operational behavior, but not the final `n8n` implementation.

Related documents:

- [archive-detection-recovery-design.md](archive-detection-recovery-design.md)
- [archive-detection-implementation-plan.md](archive-detection-implementation-plan.md)
- [archive-runtime-db-repair-guide.md](../reference/archive-runtime-db-repair-guide.md)
- [archive-runtime-repair-deployment-options.md](../
docs/features/print_history/planning/
docs/features/print_history/planning/
docs/features/print_history/planning/runtime-repair/archive-runtime-repair-deployment-options.md


)
- [archive-runtime-repair-script-and-n8n-flow.md](../
docs/features/print_history/reference/
docs/features/print_history/reference/
docs/features/print_history/reference/runtime-repair/archive-runtime-repair-script-and-n8n-flow.md


)
- [archive-runtime-sidecar-api-and-compose.md](../
docs/features/print_history/reference/
docs/features/print_history/reference/
docs/features/print_history/reference/runtime-repair/archive-runtime-sidecar-api-and-compose.md


)
- [../../repo/bambuddy-archive-recovery-approach.md](../../repo/bambuddy-archive-recovery-approach.md)

## Workflow Goal

When Home Assistant identifies an incomplete Bambuddy archive, `n8n` should be able to:

1. receive a recovery request from HA
2. attempt printer-side `.3mf` retrieval using known filename and path heuristics
3. create a new canonical Bambuddy archive if recovery succeeds
4. annotate both the broken and recovered archives to preserve lineage
5. return a structured outcome to HA

If canonical runtime correction is required after recovery or for independently repaired archives, the same orchestration layer can also invoke the direct runtime-repair script described in [archive-runtime-repair-script-and-n8n-flow.md](../
docs/features/print_history/reference/
docs/features/print_history/reference/
docs/features/print_history/reference/runtime-repair/archive-runtime-repair-script-and-n8n-flow.md


).

## Why `n8n`

`n8n` is the preferred orchestration layer because this workflow is inherently multi-step and stateful:

- normalize names
- branch between direct-retrieval and directory-scan paths
- retry with delays
- upload on success
- annotate both archive records
- emit an explainable outcome

This is a better fit for `n8n` than embedding the same logic in HA YAML.

## Workflow Modes

### Mode 1: Manual recovery

Triggered by an operator from HA.

Use this first.

### Mode 2: Post-start automated recovery

Triggered shortly after initial incomplete archive detection.

Use only after manual mode is trusted.

### Mode 3: Post-complete automated recovery

Triggered after print completion, when the file may be easier to retrieve.

### Mode 4: Scheduled audit recovery

Triggered from a periodic audit for older incomplete records that are still repairable.

## Webhook Contract

## HA â†’ `n8n` request body

Recommended payload:

```json
{
  "archive_id": 174,
  "printer_id": 1,
  "printer_name": "P1S",
  "printer_ip": "192.168.1.50",
  "printer_access_code_ref": "secret://bambu/p1s",
  "subtask_name": "200mm x 200mm Deadpool & Wolverine Hueforge",
  "filename": "200mm x 200mm Deadpool & Wolverine Hueforge.3mf",
  "recovery_mode": "manual",
  "detected_reason": "no_3mf_available",
  "detected_at": "2026-03-29T03:02:00Z"
}
```

### Notes

- Prefer a credential reference over a raw access code in the payload if `n8n` secrets can resolve it.
- Include both `filename` and `subtask_name` because either may be better for filename derivation.

## `n8n` â†’ HA response body

Recommended payload:

```json
{
  "status": "recovered",
  "old_archive_id": 174,
  "new_archive_id": 175,
  "recovery_mode": "manual",
  "matched_remote_path": "/cache/200mm_x_200mm_Deadpool_&_Wolverine_Hueforge.3mf",
  "attempt_count": 6,
  "last_error": null,
  "completed_at": "2026-03-29T03:05:42Z"
}
```

Allowed `status` values:

- `recovered`
- `not_found`
- `ftp_error`
- `upload_failed`
- `annotation_failed`
- `invalid_request`

## Workflow Topology

## Stage 1: Request validation

Validate required fields:

- `archive_id`
- `printer_ip`
- enough naming context to derive candidate filenames

If missing, terminate with `invalid_request`.

## Stage 2: Candidate filename generation

Generate normalized candidates using Bambuddy and `ha_bambulab` behavior as references.

### Candidate set

- `subtask_name + ".gcode.3mf"`
- `subtask_name + ".3mf"`
- `filename` as sent
- normalized filename without path segments
- `gcode_file + ".3mf"` if available in future payloads
- space-to-underscore variants

### Normalization rules

- strip path prefixes
- preserve original candidate first
- create underscore variants second
- de-duplicate while preserving order

## Stage 3: Direct retrieval attempts

For each candidate filename, try these paths in order:

- `/cache/{candidate}`
- `/{candidate}`
- `/model/{candidate}`
- `/data/{candidate}`
- `/data/Metadata/{candidate}`

Stop immediately on successful retrieval.

## Stage 4: Directory-scan fallback

If direct retrieval fails:

1. list known directories
2. normalize filenames for fuzzy matching
3. look for `.3mf` files containing the normalized search term
4. retrieve the best match

Directories to scan:

- `/cache`
- `/`
- `/model`
- `/data`
- `/data/Metadata`

## Stage 5: Retry policy

### Manual mode

- one immediate pass
- optional one delayed retry after 10-15 seconds

### Automated post-start mode

- immediate attempt
- delayed retries at increasing intervals

Recommended intervals:

- `0s`
- `15s`
- `45s`
- `120s`

### Post-complete mode

- one or two targeted recovery attempts

### Audit mode

- single conservative pass only

## Stage 6: Bambuddy upload

On successful retrieval, call:

- `POST /api/v1/archives/upload?printer_id={printer_id}`

Use the recovered file as the upload payload.

Expected result:

- new archive ID
- normal Bambuddy archive parsing and thumbnail generation

### Important timestamp behavior

The upload endpoint creates a new archive from the recovered `.3mf`, but it does not restore the original print run timestamps.

Design assumption for the workflow:

- `started_at` on the new archive will not contain the original print start time
- `completed_at` on the new archive will reflect archive creation time during recovery
- `actual_time_seconds` is not reconstructed by the upload flow

Therefore the workflow must preserve original runtime values separately if they matter for auditability.

If preserving runtime values in notes is not sufficient for the deployment, use the separate canonical repair path documented in:

- [archive-runtime-db-repair-guide.md](../reference/archive-runtime-db-repair-guide.md)
- [archive-runtime-repair-script-and-n8n-flow.md](../
docs/features/print_history/reference/
docs/features/print_history/reference/
docs/features/print_history/reference/runtime-repair/archive-runtime-repair-script-and-n8n-flow.md


)

## Stage 7: Lineage annotation

After upload succeeds:

### Old archive

Add or merge tags/notes such as:

- `exception:missing_3mf`
- `repair:pending` or `repair:failed` before success
- replacement archive reference after success
- original runtime values retained as the historical source of truth for execution timing

### New archive

Add or merge tags/notes such as:

- `repair:recovered`
- `recovered_from:{old_archive_id}`
- recovery audit block carrying original fallback `started_at`, `completed_at`, `actual_time_seconds`, and original `status`

### Recommended notes contract

Append a small machine-readable block instead of overwriting existing notes.

Suggested format on the recovered archive:

```text
[RECOVERY_AUDIT_V1]
{"recovered_from_archive_id":174,"recovery_mode":"manual","recovery_source":"sd_cache_3mf","original_status":"completed","original_started_at":"2026-03-29T02:50:40.735421","original_completed_at":"2026-03-29T14:24:30.547489","original_actual_time_seconds":41629}
```

Suggested format on the fallback archive:

```text
[RECOVERY_AUDIT_V1]

```

For an eventual always-on service boundary rather than script execution, see [archive-runtime-sidecar-api-and-compose.md](../
docs/features/print_history/reference/
docs/features/print_history/reference/
docs/features/print_history/reference/runtime-repair/archive-runtime-sidecar-api-and-compose.md


).
{"replaced_by_archive_id":181,"replacement_status":"archived","replacement_completed_at":"2026-04-04T18:20:00Z"}
```

This keeps the canonical archive fields honest while still making the original runtime values available for future UI cleanup or reporting.

## Stage 8: Cleanup normalization

After successful upload and lineage annotation, run a lightweight cleanup pass.

Recommended cleanup actions:

- tag the old archive as replaced and resolved
- tag the new archive as recovered and canonical
- append recovery audit notes to both records
- preserve existing notes by appending rather than replacing
- leave top-level timestamp columns untouched to avoid implying unsupported in-place repair

Optional future cleanup:

- derive UI-friendly helper sensors from `[RECOVERY_AUDIT_V1]`
- collapse old and new records into one grouped row in HA while preserving separate Bambuddy records

If archive annotation fails after upload succeeds, return `annotation_failed` but still include the new archive ID.

## Failure Handling

### FTP not found

Return `not_found` when retrieval finishes cleanly but no matching `.3mf` is found.

### FTP transport issues

Return `ftp_error` when connection, TLS, or permission problems prevent a meaningful search.

### Bambuddy upload failure

Return `upload_failed` when retrieval succeeded but archive creation failed.

### Partial success rule

If file recovery worked and Bambuddy created a new archive, that should be treated as the primary success criterion even if post-upload annotation partially fails.

If annotation or cleanup fails, the workflow should report that the replacement archive is usable but historical runtime context may not be preserved in Bambuddy notes.

## Observability

The workflow should log:

- request payload summary
- candidate filenames tried
- remote paths tried
- list-scan matches discovered
- chosen matched path
- upload result
- annotation result
- final status

## Security Notes

- do not log raw access codes
- keep printer credentials in `n8n` credentials or environment variables where possible
- avoid passing secrets back to HA in the response payload

## Recommended HA Integration Model

### Initial phase

HA calls `n8n` only from a manual recovery action.

### Later phase

HA may call `n8n` automatically after incomplete archive detection and again after print completion.

### UX expectation

HA should treat the `n8n` workflow as asynchronous in spirit even if the webhook response is immediate. The UI should show recovery state separately from detection state.

## Validation Checklist

1. request with valid context reaches `n8n`
2. direct retrieval succeeds for a normal cache-path case
3. directory-scan fallback succeeds when direct path guesses fail
4. Bambuddy upload returns a new archive
5. old and new archives are linked clearly in tags or notes
6. HA can consume and display the returned status cleanly
7. original fallback runtime timestamps remain visible somewhere even though the new archive uses recovery-time canonical fields

## Recommendation

Implement manual `n8n` recovery first. Do not enable automated invocation until the workflow has been exercised against at least a few real fallback archives.


