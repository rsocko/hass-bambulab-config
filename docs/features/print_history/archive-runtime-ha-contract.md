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
  "created_at": "2026-03-31T21:47:05+00:00",
  "status": "completed",
  "failure_reason": null,
  "audit_note": "Recovered fallback archive after delayed 3MF retrieval",
  "trigger_source": "home_assistant_manual"
}
```

## Suggested HA Service Shapes

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