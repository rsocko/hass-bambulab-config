# Archive Detection Implementation Plan

> Design-only plan for Home Assistant-side detection and exception surfacing. This document does not define final YAML implementation details, only the intended contracts and rollout order.

## Purpose

Translate the archive detection and recovery design into a concrete implementation plan for the `print_history` package while deferring code changes.

Related documents:

- [archive-detection-recovery-design.md](archive-detection-recovery-design.md)
- [archive-recovery-live-matrix-2026-04-04.md](archive-recovery-live-matrix-2026-04-04.md)
- [archive-recovery-interim-test-plan.md](archive-recovery-interim-test-plan.md)
- [../../repo/bambuddy-archive-recovery-approach.md](../../repo/bambuddy-archive-recovery-approach.md)

## Recommended Delivery Sequence

### Phase 1: Detection and visibility

Goal: make incomplete Bambuddy archives visible and explainable in Home Assistant.

### Phase 2: Manual recovery orchestration

Goal: allow a user to trigger repair through an external recovery runner without changing Bambuddy.

### Phase 3: Automated recovery orchestration

Goal: make recovery automatic only after detection and manual repair flows prove stable.

## Chosen Recovery Runner Strategy

### Primary recommendation: `n8n`

Use `n8n` as the long-term orchestration layer for repair attempts.

Reasons:

- better fit for multi-step branching and retry behavior
- easier inspection of failed runs than `shell_command`
- easier credential handling and HTTP/FTP orchestration
- natural fit for delayed retries and human approval gates

### Secondary option: `shell_command`

Use `shell_command` only as a simple manual bridge from HA to a local PowerShell or Python recovery script.

Best use cases:

- quick operator-triggered recovery
- proof-of-concept before `n8n` is built
- environments that do not already run `n8n`

### Deferred option: sidecar service

Use a dedicated sidecar service only if recovery becomes frequent enough to justify a maintained API boundary.

This is the cleanest engineering boundary, but not the best first move.

## Home Assistant Design Contract

## Data Layer

### Existing source

`script.load_history_page` already trims archive responses for dashboard use.

### Planned additions to trimmed row shape

- `file_path`
- `file_size`
- `thumbnail_path`
- `source_3mf_path`
- `extra_data.no_3mf_available`

### Planned derived fields

- `is_incomplete_archive`
- `missing_core_3mf`
- `missing_thumbnail`
- `has_source_only`
- `repair_state`

## Entity Plan

### REST commands

1. `bambuddy_get_archive_detail`
2. `bambuddy_upload_archive_file`

The upload command is included in the design now so the shape is clear, even though automated recovery is later-phase work.

### Scripts

1. `check_archive_integrity`
2. `audit_recent_archive_exceptions`
3. `mark_archive_exception`
4. `request_archive_recovery` — phase 2, operator-triggered only

### Sensors

1. `sensor.bambuddy_incomplete_archives_count`
2. `sensor.bambuddy_last_incomplete_archive`
3. trigger-based exception-state sensor storing the current exception set or recent exception summary

### Helpers

Only add helpers if event-only state proves insufficient.

Preferred default:

- keep exception state in trigger-based template sensors rather than proliferating helper entities

## Automation Plan

### Phase 1 automations

1. delayed post-`print_started` integrity check
2. post-`print_complete` integrity re-check
3. periodic audit of recent archives
4. optional notification on newly detected incomplete archive

### Phase 2 automations

1. operator action from dashboard or script call requests recovery
2. HA forwards request to `n8n` webhook or local script bridge
3. HA refreshes relevant archive views after recovery outcome

### Phase 3 automations

1. auto-trigger recovery after incomplete archive detection
2. retry after print completion
3. suppress repeated repair attempts once failure threshold is reached

## Dashboard Plan

### Main print history table

Add row-level indicators for:

- incomplete core archive
- missing thumbnail only
- repaired replacement available

### New exception card

Show:

- affected archive ID
- print name
- detection time
- reason summary
- repair state
- optional action button for manual recovery

### Optional status chip

Add a compact chip for the top-level dashboard showing the count of active archive exceptions.

## Event Model

### New HA-level event concept

`bambuddy_archive_exception`

Suggested payload:

- `archive_id`
- `printer_id`
- `print_name`
- `reason`
- `missing_core_3mf`
- `missing_thumbnail`
- `detected_at`
- `detection_mode` (`post_start`, `post_complete`, `periodic_audit`)

### Why event-first

This keeps the design composable:

- notifications can subscribe later
- dashboards can summarize sensor state derived from events
- recovery logic can listen without coupling directly to one automation

## `n8n` Recovery Contract

### Trigger shape

HA should eventually send a POST to an `n8n` webhook with:

- `archive_id`
- `printer_id`
- `printer_name`
- `printer_ip`
- `subtask_name`
- `filename`
- `recovery_mode`
- `detected_reason`

### Expected `n8n` flow

1. normalize filenames and variants
2. try direct FTP retrieval against known paths
3. if needed, list directories and fuzzy-match
4. if file recovered, upload to Bambuddy via `POST /archives/upload`
5. tag or annotate old and new archives
6. return success or failure payload to HA

### Expected return payload

- `status` (`recovered`, `not_found`, `ftp_error`, `upload_failed`)
- `old_archive_id`
- `new_archive_id` if recovered
- `last_error`

## Validation Plan

### Phase 1 validation

1. fallback archive is detected from API detail alone
2. history table shows warning indicators correctly
3. exception card stays lightweight and understandable

### Phase 2 validation

1. operator can trigger recovery manually
2. successful recovery creates a new Bambuddy archive
3. lineage between old and new archives is clear in tags or notes
4. original fallback runtime timestamps are preserved in recovery notes because the replacement archive uses recovery-time canonical fields

### Interim test method before HA orchestration

Use a workstation-side helper first rather than attempting multipart upload directly from HA.

Recommended path:

1. run the PowerShell helper in `Inspect` mode for a high-confidence case
2. run the helper in `Upload` mode and verify the created archive in Bambuddy
3. run the helper in `Full` mode to validate lineage tags and recovery notes
4. only then wrap the same semantics in `n8n` or a manual HA action

Reference files:

- [archive-recovery-live-matrix-2026-04-04.md](archive-recovery-live-matrix-2026-04-04.md)
- [archive-recovery-interim-test-plan.md](archive-recovery-interim-test-plan.md)
- `tests/phase3/print_history/Test-BambuddyArchiveRecovery.ps1`

### Phase 3 validation

1. automated retries do not loop endlessly
2. repeated failures settle into a stable `repair:failed` state
3. recovered archives remove or downgrade active exception state

## Recommendation

Implement only Phase 1 first. Complete manual recovery design and workflow review before any automatic recovery behavior is enabled.
