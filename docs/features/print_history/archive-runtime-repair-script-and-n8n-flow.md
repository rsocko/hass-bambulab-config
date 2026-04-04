# Archive Runtime Repair Script And `n8n` Flow

## Purpose

Define a concrete repair-script contract and a practical `n8n` workflow that can invoke it for print_history-driven fallback archive repair.

This is the direct follow-on from the higher-level recovery design. The goal here is a script that is simple enough to run with `docker exec`, but structured enough to sit behind `n8n` or a future sidecar.

## Reference Script Location

Reference implementation in this repo:

- `tools/bambuddy/repair_archive_runtime.py`

That script is intentionally operator-oriented:

- dry-run by default unless `--apply` is provided
- archive-level validation before write
- narrow writable field set
- JSON output for orchestration tools

## Script Interface

## CLI contract

```bash
python repair_archive_runtime.py \
  --db-path /data/bambuddy.db \
  --archive-id 123 \
  --started-at 2026-03-31T18:04:12+00:00 \
  --completed-at 2026-03-31T21:47:05+00:00 \
  --created-at 2026-03-31T21:47:05+00:00 \
  --status completed \
  --audit-note "Recovered fallback archive after delayed 3MF retrieval" \
  --apply
```

## Expected behavior

- load the target archive row
- validate supplied datetimes
- ensure `completed_at >= started_at` when both are present
- update only runtime and closely related audit fields
- return machine-readable JSON containing before and after values

## Recommended writable set

- `started_at`
- `completed_at`
- `created_at`
- `status`
- `failure_reason`
- optional note append to `notes`

## Example JSON output

```json
{
  "archive_id": 123,
  "applied": true,
  "changed": true,
  "before": {
    "started_at": null,
    "completed_at": null,
    "created_at": "2026-04-01T02:10:00+00:00",
    "status": "archived",
    "failure_reason": null,
    "notes": null
  },
  "after": {
    "started_at": "2026-03-31T18:04:12+00:00",
    "completed_at": "2026-03-31T21:47:05+00:00",
    "created_at": "2026-03-31T21:47:05+00:00",
    "status": "completed",
    "failure_reason": null,
    "notes": "[RUNTIME_REPAIR_V1] ..."
  }
}
```

## Recommended `n8n` Flow

## Topology

1. HA sends webhook request to `n8n`
2. `n8n` validates archive and runtime payload
3. `n8n` optionally fetches current Bambuddy archive detail
4. `n8n` runs the repair script through SSH or `docker exec`
5. `n8n` parses returned JSON
6. `n8n` optionally re-fetches archive detail for verification
7. `n8n` returns structured result to HA

## Suggested HA -> `n8n` payload

```json
{
  "archive_id": 123,
  "started_at": "2026-03-31T18:04:12+00:00",
  "completed_at": "2026-03-31T21:47:05+00:00",
  "created_at": "2026-03-31T21:47:05+00:00",
  "status": "completed",
  "failure_reason": null,
  "audit_note": "Recovered fallback archive after delayed 3MF retrieval",
  "trigger_source": "home_assistant_manual"
}
```

## Suggested `n8n` execution command

```bash
docker exec bambuddy python /opt/repair/repair_archive_runtime.py \
  --db-path /data/bambuddy.db \
  --archive-id {{$json.archive_id}} \
  --started-at {{$json.started_at}} \
  --completed-at {{$json.completed_at}} \
  --created-at {{$json.created_at}} \
  --status {{$json.status}} \
  --audit-note {{$json.audit_note}} \
  --apply
```

## Recommended `n8n` nodes

### Node 1: Webhook

Receive repair request from HA.

### Node 2: Validate Payload

Reject missing archive ID or malformed datetimes before touching Bambuddy.

### Node 3: Optional Preflight Fetch

Call `GET /api/v1/archives/{id}` to confirm current state and produce clearer operator logs.

### Node 4: Execute Repair Command

Run over:

- SSH to the Docker host
- local shell on the host where `n8n` runs
- or container exec wrapper

### Node 5: Parse Script JSON

Treat non-zero exit or invalid JSON as repair failure.

### Node 6: Optional Post-Repair Verification

Fetch the archive again and compare runtime fields.

### Node 7: Notify HA

Return:

- success or failure
- before and after summary
- operator-friendly message

## Minimal Manual Flow

For the first implementation, the flow can be simpler:

1. HA button triggers webhook
2. `n8n` runs the script
3. `n8n` returns success or failure

No retries, no side effects beyond the DB write.

## Recommendation

Treat the script as the write primitive and `n8n` as the orchestration wrapper.

That keeps the actual repair logic portable:

- CLI today
- `n8n` now
- sidecar or upstream API later