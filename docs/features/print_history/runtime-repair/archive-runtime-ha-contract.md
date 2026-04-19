# Archive Runtime Repair Home Assistant Contract

## Purpose

Define the Home Assistant-side contract for triggering canonical Bambuddy archive runtime repair.

Home Assistant is the trigger and UX plane. It should not directly own SQLite mutation logic.

Clarification:

- the sidecar is an HTTP service that Home Assistant can call directly
- `n8n` is optional and is only needed when you want orchestration around that HTTP call or around broader archive-recovery workflows
- if runtime repair is the only action you need, direct HA -> sidecar is the preferred simple path

## Recommended Modes

### Mode 1: `rest_command` to sidecar

Preferred once the sidecar exists.

If Home Assistant and the sidecar share a Docker network, use the service DNS name directly, for example `http://bambuddy-runtime-repair:8080/...`.

This is the preferred path for canonical runtime repair when no extra orchestration is required.

### Mode 2: `rest_command` to `n8n`

Preferred near-term if `n8n` is the orchestration layer.

If `n8n` is already running on the same Docker host as Bambuddy, it can call the sidecar over the shared Docker network and Home Assistant can call `n8n` only.

Use this mode only when you want `n8n` to coordinate more than a single HTTP repair call.

### Mode 3: `shell_command` to SSH or `docker exec`

Acceptable for operator-triggered proof of concept.

## Payload Contract

Recommended HA payload fields:

- `archive_id`
- `started_at`
- `completed_at`
- `created_at`
- `status`
- `failure_reason`
- `audit_note`
- `trigger_source`

Example payload:

```json
{
  "archive_id": 123,
  "started_at": "2026-03-31T18:04:12+00:00",
  "completed_at": "2026-03-31T21:47:05+00:00",
  "created_at": "2026-03-31T18:04:12+00:00",
  "status": "completed",
  "failure_reason": null,
  "audit_note": "Recovered fallback archive after delayed 3MF retrieval",
  "trigger_source": "home_assistant_manual"
}
```

## Suggested HA Service Shapes

### `bambuddy.repair_print_history_archive_from_start`

Concrete service now implemented in the custom component for the common historical-repair case where the operator knows the print start time and wants HA to derive the other canonical runtime fields.

Behavior:

- requires `archive_id` and `started_at`
- computes `completed_at = started_at + duration`
- uses explicit `duration_seconds` when provided, otherwise falls back to archive `print_time_seconds`, then `actual_time_seconds`
- defaults `created_at` to `started_at` to match observed Bambuddy archive behavior
- can optionally force `status: completed`
- forwards the repair request to the runtime-repair sidecar and refreshes archive detail after apply

Use this service when the archive record already exists and the main missing fact is a trustworthy historical start timestamp.

Prefer `dry_run: true` first for validation.

#### When to use it

Use `bambuddy.repair_print_history_archive_from_start` when all of the following are true:

- the Bambuddy archive already exists
- you have a defensible historical `started_at` value from filesystem evidence, printer history, or other independent records
- the archive already has a reasonable duration, or you can provide one explicitly with `duration_seconds`
- you want canonical Bambuddy runtime fields repaired through the sidecar instead of keeping timing evidence only in notes

Typical cases:

- a historical `.3mf` was imported successfully but its runtime timestamps are wrong or missing
- a recovered replacement archive already exists and only the timing fields need correction
- an older archive was imported from SD backup evidence and you trust the start time more than any inferred completion time

#### When not to use it

Do not use this service when any of the following are true:

- the archive does not exist yet
- you do not trust the start timestamp enough to write canonical fields
- the main problem is bad archive content and you actually need replacement or restore, not timestamp repair
- the archive has no reliable duration and you do not want to supply `duration_seconds`

Use the restore workflow instead when you need to create a replacement archive, merge source metadata, or compare source and target archive fields before applying changes.

#### Preconditions

Before using the service, verify:

- the Bambuddy integration entry has runtime-repair base URL and token configured
- the target archive ID loads successfully in the local print-history store
- the provided start time uses a valid ISO timestamp
- the duration source is understood: explicit `duration_seconds` override, otherwise archive `print_time_seconds`, otherwise archive `actual_time_seconds`

#### Recommended operator flow

1. Open the archive and confirm you are repairing the correct existing archive ID.
2. Collect the best available historical start timestamp.
3. Decide whether archive duration should come from the existing archive or an explicit override.
4. Run the service with `dry_run: true` first.
5. Inspect the returned `computed_fields` payload, especially `started_at`, `completed_at`, `created_at`, `duration_seconds`, and `duration_source`.
6. Apply only when the preview matches the evidence you intend to preserve.

#### Dry-run example

```yaml
service: bambuddy.repair_print_history_archive_from_start
data:
  archive_id: 263
  started_at: "2026-04-02T19:43:19-04:00"
  dry_run: true
  set_status_completed: true
```

Expected outcome:

- no DB change is applied
- Home Assistant returns the sidecar preview plus `computed_fields`
- `completed_at` is derived from duration
- `created_at` defaults to the same timestamp as `started_at`

#### Apply example

```yaml
service: bambuddy.repair_print_history_archive_from_start
data:
  archive_id: 263
  started_at: "2026-04-02T19:43:19-04:00"
  set_status_completed: true
  audit_note: "Historical SD import repaired from verified start timestamp"
  dry_run: false
```

Expected outcome:

- the runtime-repair sidecar applies the canonical field update
- the integration refreshes archive detail after apply
- the returned payload includes the refreshed archive and repair response

#### Notes on field semantics

- `created_at` defaults to `started_at`, not `completed_at`, because observed Bambuddy archives align archive creation with print start time
- `completed_at` is still derived from duration unless you bypass this service and call the sidecar directly with explicit timestamps
- `status` is only forced to `completed` when `set_status_completed: true` is set and no explicit `status` is provided

### `rest_command.bambuddy_runtime_repair_request`

POSTs the payload to `n8n` or the sidecar.

Example YAML:

- `examples/bambuddy_runtime_repair_request.yaml`

### `script.print_history_request_runtime_repair`

Small wrapper that:

1. validates helper values
2. sends request payload
3. triggers archive refresh
4. surfaces the result to the operator

Example YAML:

- `examples/print_history_request_runtime_repair.yaml`

## Operator UX Recommendation

Expose runtime repair only from advanced archive actions, not from the default browsing flow.

Suggested operator affordances:

- popup action button for known recovery cases
- optional confirmation step
- visible result summary after request

## Result Handling

After the call returns, HA should:

1. refresh archive detail
2. refresh the archive list cache
3. optionally surface a persistent notification if repair failed

## Recommendation

Treat HA as the caller and observer. The write path should live in `n8n`, a CLI runner, or the sidecar service.

For a same-host Docker deployment, the cleanest split is usually:

- HA calls the sidecar over HTTP when runtime repair is a standalone action
- HA calls `n8n` only when runtime repair is one step in a larger orchestration flow
- `n8n` calls the sidecar over the Docker network when `n8n` is in the path
- only the sidecar mounts the Bambuddy DB volume