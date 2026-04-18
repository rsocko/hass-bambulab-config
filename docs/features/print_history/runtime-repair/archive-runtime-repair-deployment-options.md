# Bambuddy Archive Runtime Repair Deployment Options

## Purpose

Evaluate how a direct archive runtime repair script could be invoked without waiting for an upstream Bambuddy change.

The core question is how to safely execute a write against Bambuddy's SQLite database from adjacent systems such as Home Assistant or n8n.

## Short Answer

Yes, all three broad patterns are possible:

1. trigger the repair from Home Assistant
2. trigger it from an intermediate orchestration service such as n8n
3. run a sidecar API next to Bambuddy that owns the write path

The best option depends on how often this will run and how much operational rigor is needed.

## Recommended Ranking

### Best immediate path

`n8n` or another workflow runner invoking a container-local repair command.

Why:

- good operator visibility
- easy branching and approvals
- keeps SQL logic out of HA templates and YAML
- easy to add retries, notifications, and manual checkpoints

### Best durable no-upstream path

A sidecar container exposing a narrow admin API and mounting the same Bambuddy data volume.

Why:

- stable API surface for HA, n8n, or scripts
- central place for validation, audit logging, dry-run support, and backup hooks
- avoids coupling repair behavior to Home Assistant shell access

### Acceptable proof-of-concept path

Home Assistant calling an SSH or shell bridge that executes a repair command on the Bambuddy host or inside the Bambuddy container.

Why it is only a proof of concept:

- brittle credentials and command routing
- harder to reason about concurrency and failure reporting
- poor long-term ergonomics

## Option 1: Trigger From Home Assistant

## Viability

Yes, but use HA only as the trigger plane, not as the place where the SQL logic lives.

## Recommended pattern

Home Assistant automation or script calls one of:

- `shell_command` that uses `ssh` to the Docker host
- `shell_command` that hits a local HTTP repair endpoint
- `rest_command` against a sidecar API

## Preferred HA flow

1. HA detects an archive that needs canonical timestamp repair
2. HA sends archive ID and repaired values to an external runner
3. External runner performs the DB transaction
4. HA refreshes Bambuddy sensors and annotates the result

## What not to do

- do not mount and edit `bambuddy.db` from the HA container directly if you can avoid it
- do not embed raw SQL in HA YAML
- do not use a polling template sensor to perform writes

## Example bridge patterns

### SSH to Docker host

HA runs a command like:

```bash
ssh bambuddy-host "docker exec bambuddy python /app/scripts/repair_archive_runtime.py --archive-id 123 --started-at '2026-03-31T18:04:12+00:00' --completed-at '2026-03-31T21:47:05+00:00' --created-at '2026-03-31T21:47:05+00:00'"
```

### HTTP call to sidecar

HA sends a JSON payload to a small admin service:

```json
{
  "archive_id": 123,
  "started_at": "2026-03-31T18:04:12+00:00",
  "completed_at": "2026-03-31T21:47:05+00:00",
  "created_at": "2026-03-31T21:47:05+00:00",
  "status": "completed",
  "reason": "Recovered fallback archive after delayed 3MF retrieval"
}
```

## Recommendation for HA

Use Home Assistant as the UX and event source only. Do not make it the archive DB writer.

## Option 2: Trigger From n8n

## Viability

Yes. This is the strongest near-term option if you do not want to maintain a custom always-on sidecar yet.

## Why it fits well

- easy multi-step orchestration
- supports approval or manual checkpoint nodes
- can call Bambuddy API, FTP, SSH, and webhooks in one flow
- can log repair attempts and outputs centrally

## Recommended n8n flow

1. Receive webhook from HA with archive ID and reconstructed timestamps
2. Fetch current Bambuddy archive detail for sanity checking
3. Optionally snapshot or back up the DB
4. Execute one of:
   - SSH command to Docker host
   - `docker exec` into Bambuddy container
   - HTTP call to a repair sidecar
5. Refresh archive detail and verify repaired values
6. Call back into HA or notification channel with success or failure

## Good implementation variants

### Variant A: n8n -> SSH -> docker exec

Best for low frequency and minimal new infrastructure.

### Variant B: n8n -> sidecar HTTP API

Best if repair logic is becoming important enough to standardize.

## Recommendation for n8n

This is the best current bridge if you want actionability now without modifying upstream Bambuddy.

## Option 3: Sidecar Container

## Viability

Yes. This is the cleanest no-upstream pattern if runtime repair becomes a real feature rather than an emergency tool.

## Basic shape

Deploy a small container in the same Docker stack as Bambuddy that:

- mounts the Bambuddy data volume read-write
- knows where `bambuddy.db` lives
- exposes a narrow authenticated admin API
- performs validated repair transactions
- optionally writes an audit log or emits events

## Benefits

- isolates repair logic from HA and n8n
- allows dry-run, validation, and consistency checks
- can update both `print_archives` and optional related records in one place
- easier to evolve into a stable internal contract

## Risks

- extra service to own and secure
- still relies on DB schema coupling to upstream Bambuddy internals
- must be careful about auth and network exposure

## Suggested endpoint shape

### `POST /admin/archive-runtime-repair`

Request:

```json
{
  "archive_id": 123,
  "started_at": "2026-03-31T18:04:12+00:00",
  "completed_at": "2026-03-31T21:47:05+00:00",
  "created_at": "2026-03-31T21:47:05+00:00",
  "status": "completed",
  "failure_reason": null,
  "dry_run": false,
  "audit_note": "Recovered from fallback archive flow"
}
```

Response:

```json
{
  "archive_id": 123,
  "updated": true,
  "before": {
    "started_at": null,
    "completed_at": null,
    "created_at": "2026-04-01T02:10:00+00:00",
    "status": "archived"
  },
  "after": {
    "started_at": "2026-03-31T18:04:12+00:00",
    "completed_at": "2026-03-31T21:47:05+00:00",
    "created_at": "2026-03-31T21:47:05+00:00",
    "status": "completed"
  }
}
```

## Security requirements

- bind only on internal network
- require a dedicated token or mTLS
- keep endpoint admin-only
- log who initiated each repair

## Option 4: Put Repair Code Inside the Bambuddy Container Without Changing Upstream

## Viability

Yes, if you treat it as an operator-maintained overlay rather than an upstream feature.

Examples:

- bind-mount a repair script into the Bambuddy container and run it via `docker exec`
- create a derived local image that adds one repair script but does not modify Bambuddy app code

This can be effective, but you are still carrying local operational drift from upstream.

## Best Practical Recommendation

### If you want something soon

Use:

- HA for detection and operator controls
- n8n for orchestration
- SSH or `docker exec` to run a container-local repair script

### If you want something that can last

Build a sidecar admin API with a very small surface area.

### If you want the lowest conceptual risk

Wait for or build an upstream Bambuddy admin endpoint instead of depending on DB writes forever.

## Final Guidance

The question is not whether this can be triggered from HA, n8n, or a sidecar. It can.

The real design choice is where to put responsibility for:

- validation
- backups
- transaction safety
- audit logging
- auth

For that reason:

- HA should trigger
- n8n should orchestrate in the near term
- a sidecar should own the write path if this matures