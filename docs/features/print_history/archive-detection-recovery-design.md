# Archive Detection And Recovery Design

> Analysis based on Bambuddy source (`maziggy/bambuddy`) and `ha_bambulab` source (`greghesp/ha-bambulab`) as reviewed on 2026-03-29.

Related documents:

- [archive-runtime-db-repair-guide.md](archive-runtime-db-repair-guide.md)
- [archive-runtime-field-impact-matrix.md](archive-runtime-field-impact-matrix.md)
- [archive-runtime-repair-deployment-options.md](archive-runtime-repair-deployment-options.md)
- [archive-runtime-repair-script-and-n8n-flow.md](archive-runtime-repair-script-and-n8n-flow.md)
- [archive-runtime-sidecar-api-and-compose.md](archive-runtime-sidecar-api-and-compose.md)
- [archive-historical-backfill-from-sd-card.md](archive-historical-backfill-from-sd-card.md)

## Goal

Add Home Assistant-side detection, exception surfacing, and best-effort recovery workflows for Bambuddy archives that were created through the fallback `no_3mf_available` path.

## Scope

### In scope

- detection of incomplete Bambuddy archives
- Home Assistant entity, automation, and dashboard design for exception visibility
- repair orchestration design that does not require Bambuddy code changes
- evaluation of Bambuddy API capabilities and `ha_bambulab` internals as recovery references

### Out of scope

- changing Bambuddy backend behavior
- building a custom Home Assistant integration around `ha_bambulab` private internals
- implementing the repair worker in this phase

## Requirements

### Functional requirements

1. Detect fallback or otherwise incomplete archives reliably
2. Surface incomplete records in `print_history` without requiring log inspection
3. Support a future repair workflow that can be manual first and automated later
4. Preserve traceability between broken fallback archives and any replacement archives

### Non-functional requirements

1. Prefer stable APIs over private implementation hooks
2. Keep HA-side state small enough for template sensors and dashboard rendering
3. Avoid creating silent background repair behavior that users cannot understand
4. Ensure failures remain visible even if recovery is unavailable

## Problem Definition

Bambuddy creates a fallback archive when its initial FTP retrieval of the printer-side `.3mf` fails at print start. Those archives typically have:

- `file_path = ""`
- `file_size = 0`
- `thumbnail_path = null`
- parsed metadata fields missing
- `extra_data.no_3mf_available = true`

These records are visible in print history but are operationally incomplete.

## Confirmed Bambuddy Behavior

### What Bambuddy does well

- At print start, it tries multiple filename variants and multiple remote paths
- It also falls back to directory listing and fuzzy filename matching
- If retrieval works, `ArchiveService.archive_print()` creates a normal archive with parsed metadata and thumbnail

### What Bambuddy cannot currently do after fallback

- `POST /archives/{id}/rescan` only reparses an already archived file on disk
- `POST /archives/{id}/source` and `POST /archives/upload-source` only attach source project files; they do not rebuild the main archive payload
- `POST /archives/upload` creates a new archive instead of repairing the broken one
- `POST /archives/{id}/reprint` explicitly fails if there is no archived `.3mf`

### Important implementation detail

For fallback archives, `file_path` is empty. Some source-upload code paths derive a destination directory from `archive.file_path`, which means fallback archives are not a reliable target for attachment-based repair. That makes `upload-source` a poor repair primitive for this case.

## Confirmed `ha_bambulab` Behavior

### What `ha_bambulab` already has

- Internal FTP logic to download the active print's `.3mf`
- Filename heuristics based on `subtask_name` and `gcode_file`
- Search over known printer paths, especially `/cache/` and `/`
- Retry behavior around printer timing and state transitions
- Local cache storage of downloaded print files under its own cache directory
- FTP upload primitives used to push files to the printer

### What `ha_bambulab` does not expose as a supported repair API

- No documented Home Assistant service to fetch an arbitrary printer-side `.3mf` and return it for downstream automation use
- No supported service to export a cached print file back into HA automations as a file payload
- No direct Bambuddy integration path

### Practical consequence

`ha_bambulab` proves the printer-side retrieval is feasible, but it is not currently a clean automation surface for repairing Bambuddy records.

## Chosen Path

### Primary architecture

- Home Assistant owns detection, state, and dashboard visibility
- `n8n` owns recovery orchestration
- Bambuddy remains the system of record for final archive creation

### Secondary fallback

If `n8n` is not available initially, a local `shell_command` bridge may be used for manual recovery only.

### Explicit deferral

A dedicated sidecar service is deferred until there is evidence that recovery behavior is common enough to justify a maintained API boundary.

For the current canonical runtime-repair options that sit alongside this detection-and-recovery design, see:

- [archive-runtime-db-repair-guide.md](archive-runtime-db-repair-guide.md)
- [archive-runtime-repair-deployment-options.md](archive-runtime-repair-deployment-options.md)
- [archive-runtime-sidecar-api-and-compose.md](archive-runtime-sidecar-api-and-compose.md)

## Feasible Recovery Paths Without Changing Bambuddy

## Decision Matrix

| Option | Archive visibility | Repair quality | Maintenance cost | Recommendation |
|--------|--------------------|----------------|------------------|----------------|
| HA detection only | High | None | Low | Implement first |
| External worker + Bambuddy upload | High | High | Medium | Best long-term path without Bambuddy changes |
| Source upload to fallback archive | Medium | Low | Medium | Keep only as fallback provenance path |
| Direct reuse of `ha_bambulab` internals | Medium | Medium | High | Avoid as primary architecture |

## Option 1: Detection Only In Home Assistant

### What to detect

An archive should be flagged as incomplete when any of the following is true:

- `extra_data.no_3mf_available == true`
- `file_path` is empty
- `file_size == 0`
- `thumbnail_path` is missing

### Detection timing

1. Event-driven check after `print_started` or `print_complete`
2. Periodic audit of the most recent archives

### Recommended implementation

- Add a `GET /archives/{id}` rest command for point inspection
- Add a script that inspects the current archive after a delay
- Add a trigger-based template sensor to store exception results
- Add a count sensor and an exceptions card in print history

### Best use

- first release of this feature area
- environments where recovery is not yet trusted enough to automate
- sites where printer-side FTP access from automation hosts is not available

### Value

- High
- Easy to implement
- No dependence on printer-side file transfer after the fact

## Option 2: Recovery By External FTP Fetch Plus Bambuddy Upload

### Workflow

1. HA or n8n detects an incomplete archive
2. A script attempts direct FTP retrieval from the printer using Bambuddy-style and `ha_bambulab`-style filename heuristics
3. If the `.3mf` is recovered, upload it to Bambuddy using `POST /archives/upload?printer_id=...`
4. Tag the old fallback archive and the new recovered archive to link them logically

### Why this works

- `POST /archives/upload` is a real archive creation path backed by `ArchiveService.archive_print()`
- It produces the full metadata/thumbnail pipeline
- It avoids relying on unsupported in-place repair behavior

### Recovered archive timestamp semantics

`POST /archives/upload` does not recreate the original print run timeline.

Current Bambuddy behavior when uploading a `.3mf` without live print context is:

- `status` is created as `archived`
- `started_at` is not reconstructed and remains empty
- `completed_at` is set to the time the new archive record is created

Current Bambuddy behavior when updating an archive through `PATCH /api/v1/archives/{id}` is:

- writable fields are limited to metadata fields exposed by `ArchiveUpdate`
- `started_at` and `completed_at` are not part of that schema
- recovery cannot write the original runtime timestamps back into the archive's canonical datetime columns without a Bambuddy backend change or direct database intervention

Important consequence:

- the new archive's timeline reflects recovery time, not the original print execution time
- `started_at`, `completed_at`, and `actual_time_seconds` are not extracted from the `.3mf` by the upload flow
- parser-derived fields such as thumbnail, content hash, filament usage, slice metadata, and print name can still be restored normally

### Recovery data-loss profile

Fields that are usually restorable from a valid `.3mf` upload:

- `file_path`
- `file_size`
- `content_hash`
- `thumbnail_path`
- parsed print metadata such as `print_name`, `print_time_seconds`, `filament_used_grams`, `filament_type`, `filament_color`, `layer_height`, `total_layers`, `nozzle_diameter`, `nozzle_temperature`, `sliced_for_model`

Fields that are not restored automatically by creating a replacement archive:

- original `started_at`
- original `completed_at`
- original `actual_time_seconds`
- original archive `status` semantics such as `completed` versus recovery-created `archived`
- original photos, favorites, tags, notes, and operator annotations unless copied separately
- exact lineage to the broken archive unless explicitly written after upload

### Recovery options for lost runtime fields

Option 1: Accept upload-time defaults.

- simplest workflow
- recovered archive has correct file metadata
- historical run timestamps remain lost from the canonical archive fields

Option 2: Preserve original runtime values in recovery metadata.

- recommended default
- after upload, write a structured recovery block into `notes` on the new archive
- optionally write a matching linkage block on the old fallback archive

Option 3: Preserve runtime values externally only.

- store recovery audit information in HA helper state, `n8n` execution logs, or a separate data store
- lowest risk to Bambuddy UI clutter
- weakest in-app auditability

Recommended choice: Option 2.

It preserves the missing historical context close to the archive record while accepting that Bambuddy's canonical timestamp columns will still reflect the new recovery event.

### Can recovery write the actual print timestamps?

Not with the current public Bambuddy API.

Confirmed constraints from Bambuddy source:

- `ArchiveUpdate` supports metadata fields such as `print_name`, `tags`, `notes`, `cost`, `failure_reason`, `quantity`, `external_url`, `printer_id`, `project_id`, and `status`
- `ArchiveUpdate` does not include `started_at` or `completed_at`
- `actual_time_seconds` is computed from `started_at` and `completed_at`, so it also cannot be restored as a canonical persisted field through normal API usage

Implication:

- the best current recovery behavior is to preserve original `started_at`, `completed_at`, and `actual_time_seconds` in machine-parseable notes
- if canonical timestamp restoration becomes a requirement, that needs either a Bambuddy code change to widen the update schema or a direct database repair path outside the supported API

The direct DB repair path, affected field surfaces, and adjacent deployment options are documented in:

- [archive-runtime-db-repair-guide.md](archive-runtime-db-repair-guide.md)
- [archive-runtime-field-impact-matrix.md](archive-runtime-field-impact-matrix.md)
- [archive-runtime-repair-deployment-options.md](archive-runtime-repair-deployment-options.md)

### Source project fallback viability

An original Bambu Studio `.3mf` project file can be a fallback source, but it is not equivalent to the printer-cached sliced `.3mf`.

Expected behavior from Bambuddy source:

- `POST /archives/{id}/source` and `POST /archives/upload-source` attach the file as `source_3mf_path` only
- `POST /archives/upload` will ingest the file as a new archive if it is a valid `.3mf`
- archive card `GCODE` versus `Source` labeling depends on sliced signals such as embedded G-code or populated `total_layers` / `print_time_seconds`

Design implication:

- a source project file is a viable provenance and viewer fallback
- it is a weak substitute for true archive reconstruction when the goal is to restore sliced-print metadata or a plate-specific print record
- prefer recovery-source ranking of `printer-cached sliced .3mf` first, then `original Bambu Studio source .3mf` only when no sliced file exists

### Bambu Studio re-slice/export fallback

Between those two tiers, include an explicit `re-slice then export plate sliced file` fallback.

Why:

- Bambu Studio can create a printer-destined sliced export without actually sending the job to the printer
- this output is structurally closer to Bambuddy's canonical archive input than a raw source-project `.3mf`

Limits:

- the export is only as accurate as the current slicer version, selected printer preset, process preset, filament mapping, and chosen plate
- it should be treated as a reconstructed sliced artifact, not guaranteed original evidence

Recommended ranking:

1. cached sliced `.3mf` from the printer or SD backup
2. Bambu Studio `Export plate sliced file` output derived from the source project
3. raw Bambu Studio source project attached or uploaded only as last resort

### Downsides

- Creates a second archive instead of repairing the original
- Requires custom script infrastructure outside stock HA YAML
- Requires printer FTP credentials and network access from the script runner

### Best fit

- `n8n` workflow
- PowerShell or Python helper launched from HA `shell_command`
- Small sidecar service on the same network as the printer

### Recommended fit

Use `n8n` as the primary orchestrator for this option.

Reasons:

- better visibility into retry and failure states
- easier operator-triggered and later automated flows
- clearer separation between HA UX logic and recovery execution logic

### Design note

The recovery worker should be treated as an adapter around Bambuddy and printer FTP, not as a new source of truth. Its job is to recover a missing `.3mf` and hand it back to Bambuddy for normal archive creation.

### Cleanup and provenance note

Recovery should include a cleanup pass that normalizes the old and new archive records after a successful upload.

Recommended cleanup goals:

- preserve a human-readable relationship between the fallback archive and the replacement archive
- keep the fallback archive visible as the historical runtime record
- keep the replacement archive visible as the canonical file-backed record
- avoid pretending that the replacement archive's top-level timestamps are the original print timestamps

Recommended `notes` augmentation on the recovered archive:

```text
[RECOVERY_AUDIT_V1]
{"recovered_from_archive_id":174,"recovery_source":"sd_cache_3mf","recovery_completed_at":"2026-04-04T18:20:00Z","original_status":"completed","original_started_at":"2026-03-29T02:50:40.735421","original_completed_at":"2026-03-29T14:24:30.547489","original_actual_time_seconds":41629}
```

Recommended `notes` augmentation on the fallback archive:

```text
[RECOVERY_AUDIT_V1]
{"replaced_by_archive_id":181,"replacement_created_at":"2026-04-04T18:20:00Z","replacement_preserves_file_metadata":true}
```

Implementation notes:

- append to existing notes instead of replacing them
- keep the recovery block machine-parseable and versioned
- mirror only the fields that would otherwise be lost or misleading after replacement creation
- do not duplicate large `extra_data` payloads into notes

### Optional operator cleanup path

Some users may prefer to keep the historical fallback archive as the runtime record. Others may prefer to remove it after they are satisfied that the recovered archive is complete.

Recommended policy options:

Option 1: Keep both records.

- safest audit trail
- preserves the original fallback archive as evidence of what happened
- recommended default

Option 2: Delete the historical fallback archive after operator review.

- supported by Bambuddy's `DELETE /api/v1/archives/{id}` endpoint
- only do this after verifying the replacement archive contains the expected file metadata, thumbnail, content hash, and recovery notes
- only do this if the operator accepts that the original runtime timestamps will then survive only in the replacement archive notes or in external logs

Recommended guardrails for deletion:

- require a manual operator action, not automatic cleanup
- require that the replacement archive already has a `[RECOVERY_AUDIT_V1]` block containing the original runtime fields
- capture the deleted archive ID in external notes or changelog documentation if long-term auditability matters

## Option 3: Recovery By Uploading Source 3MF To Fallback Archive

### Status

Not recommended as the primary recovery path.

### Reason

- Bambuddy source-upload endpoints attach `source_3mf_path`, but do not rebuild the main archive file, thumbnail, or parsed metadata
- For fallback archives with empty `file_path`, attachment destination logic is not trustworthy enough to use as the main repair flow

### Possible use

- Attach original project provenance only
- Useful for archival completeness, not for repairing history metadata

## Option 4: Leverage `ha_bambulab` Local Cache Indirectly

### Status

Potentially feasible, but only if you are willing to build around integration internals.

### What the source suggests

- `ha_bambulab` downloads print files into a local cache structure
- It has internal HTTP views for cache-presence/upload-to-printer workflows
- It does not expose a documented API to retrieve cached `.3mf` files for other consumers

### Recommendation

Treat this as an advanced custom-component path, not a maintainable HA automation path.

## Recommended Architecture

## Sequence Flows

### Detection flow

1. Bambuddy `print_started` webhook is received in HA
2. HA stores `archive_id`
3. After a configurable delay, HA fetches `GET /archives/{archive_id}`
4. HA computes integrity flags
5. If incomplete, HA emits an archive-exception event and updates exception state
6. Dashboard and notification layers react to the exception event

### Recovery flow

1. Archive exception exists for `archive_id`
2. Home Assistant invokes `n8n` with archive and printer context
3. Recovery worker receives printer identity, candidate filenames, and archive metadata
4. Worker retries FTP retrieval against known paths and normalized filename variants
5. On success, worker uploads `.3mf` to Bambuddy as a new archive
6. Worker updates tags or notes on both old and new archives
7. HA refreshes archive state and shows the relationship

## Layer 1: Detection And Visibility In `print_history`

### Data model additions

Extend the trimmed archive payload used by `script.load_history_page` to include:

- `file_path`
- `file_size`
- `thumbnail_path`
- `source_3mf_path`
- `extra_data.no_3mf_available`

### Derived fields

For each archive row, compute:

- `is_incomplete_archive`
- `missing_thumbnail`
- `missing_core_3mf`
- `has_source_only`

### UI additions

1. Inline warning badge on affected rows
2. New `Archive Exceptions` dashboard card listing incomplete records
3. Counter sensor for incomplete archives in the recent window

### UI goals

- affected rows should be noticeable without dominating the whole history view
- users should be able to distinguish `missing thumbnail only` from `missing core 3MF`
- the exception view should be useful even before any recovery workflow exists

## Layer 2: Event-Driven HA Detection

### Proposed flow

1. `print_started` stores `archive_id` as today
2. After a delay, call `GET /archives/{archive_id}`
3. If fallback indicators are present, mark the archive as incomplete and notify
4. Re-run the check after `print_complete`

### Why after `print_complete`

This catches cases where the printer file became available later, or where a recovery workflow has already created a replacement archive.

### Recommended trigger points

- `print_started` plus delay
- `print_complete`
- `print_failed`
- periodic audit for recent archives

## Layer 3: External Recovery Worker

### Retrieval heuristics to copy

Use the combined filename/path logic from Bambuddy and `ha_bambulab`:

- `subtask_name + ".gcode.3mf"`
- `subtask_name + ".3mf"`
- `gcode_file + ".3mf"`
- `gcode_file + ".gcode.3mf"`
- space-to-underscore variants

Search paths:

- `/cache/`
- `/`
- `/model/`
- `/data/`
- `/data/Metadata/`

If direct retrieval fails, directory-list and fuzzy-match on normalized names.

### Retry timing to copy

Blend Bambuddy and `ha_bambulab` timing approaches:

- immediate retry burst
- then delayed retries at roughly 5s to 60s
- final recovery attempt at or after print completion

### Input contract for worker

The future worker should receive:

- printer IP or printer identifier
- printer access code or credential reference
- Bambuddy `archive_id`
- Bambuddy `printer_id`
- `subtask_name`
- reported filename or `gcode_file`
- recovery mode (`manual`, `post_start`, `post_complete`, `scheduled_audit`)

### Transport recommendation

The default design assumes an HA-to-`n8n` webhook call. Keep the transport simple JSON over HTTP so the worker can evolve independently of HA YAML.

### Output behavior

On success:

- upload recovered `.3mf` to Bambuddy via `POST /archives/upload`
- PATCH or tag both archives to indicate the relationship
- optionally favorite or annotate the recovered archive as canonical
- append recovery audit metadata to `notes` so original fallback runtime timestamps remain visible even though the new archive uses recovery-time canonical fields

On failure:

- keep the fallback exception open
- include the last FTP error in the notification or notes

## Recommended Tagging Convention

For fallback archive:

- `exception:missing_3mf`
- `repair:pending`
- `replaced_by:{new_archive_id}` after success

For recovered archive:

- `repair:recovered`
- `recovered_from:{old_archive_id}`
- `recovery_source:sd_cache_3mf` or `recovery_source:manual_upload`

For irrecoverable archive after all attempts:

- `repair:failed`

## Suggested Package Additions

### New rest commands

- `bambuddy_get_archive_detail`
- `bambuddy_upload_archive_file`

### New scripts

- `check_archive_integrity`
- `audit_recent_archive_exceptions`
- `mark_archive_exception`
- `request_archive_recovery` (manual first)

### New template entities

- recent incomplete archive count sensor
- last incomplete archive sensor
- trigger-based archive exception state sensor

### New dashboard artifacts

- exception summary chip
- archive exceptions table or compact list
- row-level warning indicator in the main history table
- optional manual `Recover` action entry point that only appears once recovery orchestration exists

### Optional external integration

- `shell_command.bambuddy_recover_archive_from_printer`

## Recommendation Summary

### Implement now

1. Detection in HA
2. Exception surfacing in print history
3. Optional notification on incomplete archive creation

### Design review checkpoints

1. confirm the trimmed archive payload additions are acceptable for HA state size
2. confirm whether exception state should be event-only or persisted in helpers/sensors
3. confirm the `n8n` webhook contract and failure-response shape

### Implement next if you want automatic recovery

1. External FTP fetch worker
2. Bambuddy `POST /archives/upload` on success
3. Archive-linking tags/notes

### Avoid relying on

1. `POST /archives/{id}/rescan` for fallback archives
2. `POST /archives/{id}/source` as a true repair mechanism
3. undocumented `ha_bambulab` internals as your long-term primary interface

## Recommendation

Ship this as a design sequence, not as a single large implementation:

1. detection and exception visibility
2. manual recovery orchestration through `n8n`
3. automated recovery only after the first two are proven in practice
