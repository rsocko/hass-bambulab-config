# Bambuddy Archive Recovery Approach

## Purpose

Define the recommended approach for handling Bambuddy fallback archives from this repository without changing Bambuddy itself.

This document is the repo-level decision record. Feature-level detail lives in [../features/print_history/recovery/archive-detection-recovery-design.md](../features/print_history/recovery/archive-detection-recovery-design.md).

Additional print_history design references for canonical runtime repair and deployment patterns:

- [../features/print_history/runtime-repair/archive-runtime-db-repair-guide.md](../features/print_history/runtime-repair/archive-runtime-db-repair-guide.md)
- [../features/print_history/runtime-repair/archive-runtime-field-impact-matrix.md](../features/print_history/runtime-repair/archive-runtime-field-impact-matrix.md)
- [../features/print_history/runtime-repair/archive-runtime-repair-deployment-options.md](../features/print_history/runtime-repair/archive-runtime-repair-deployment-options.md)
- [../features/print_history/runtime-repair/archive-runtime-repair-script-and-n8n-flow.md](../features/print_history/runtime-repair/archive-runtime-repair-script-and-n8n-flow.md)
- [../features/print_history/runtime-repair/archive-runtime-sidecar-api-and-compose.md](../features/print_history/runtime-repair/archive-runtime-sidecar-api-and-compose.md)
- [../features/print_history/imports/archive-historical-backfill-from-sd-card.md](../features/print_history/imports/archive-historical-backfill-from-sd-card.md)
- [../features/print_history/imports/source-3mf-import-design.md](../features/print_history/imports/source-3mf-import-design.md)

## Executive Summary

The recommended approach is a three-part design:

1. Detect incomplete Bambuddy archives in Home Assistant
2. Surface those exceptions directly in `print_history`
3. Optionally recover by retrieving the printer-side `.3mf` externally and creating a new canonical Bambuddy archive via `POST /archives/upload`

This is the best available approach because Bambuddy currently has no supported in-place repair path for fallback archives whose `file_path` was never created.

## Why This Exists

Bambuddy creates fallback archives when initial printer-side `.3mf` retrieval fails. Those records remain visible in archive history but are missing critical data required for:

- thumbnails
- slicer metadata
- print weight and filament data derived from the `.3mf`
- archive capability diagnostics
- reprint behavior

That failure mode is now understood and documented, but it still needs a designed response on the Home Assistant side.

## Decision

### Chosen direction

Adopt a layered response:

- **Layer 1**: detection and visibility in Home Assistant
- **Layer 2**: event-driven archive integrity checks
- **Layer 3**: optional external recovery worker

### Chosen orchestration path

The recommended orchestration stack is:

1. **Home Assistant for detection and UX**
2. **`n8n` for multi-step recovery orchestration**
3. **`shell_command` only as a fallback bridge for manual recovery or proof-of-concept**
4. **sidecar service only if recovery frequency or complexity later justifies it**

For historical backfill and local forensic recovery, the repo now also documents a manifest-driven queue layer that sits ahead of the existing upload script. That path uses the forensics viewer only for operator triage and source selection; it does not change the decision that canonical archive creation should still flow through `POST /archives/upload`.

That queue layer now supports two executable branches from the same manifest writeback:

- canonical archive creation from sliced artifacts via the existing backfill uploader
- provenance-only source attachment to an existing archive via `POST /api/v1/archives/{id}/source`

The repo also carries an explicit Path 2 proof-of-concept packager for raw `.gcode` inputs, but that remains experimental until live parity is proven.

The current tooling now exposes that experiment in two concrete ways:

- the forensics viewer can export a Path 2 package-plan JSON for a selected raw `.gcode` source
- the manifest runner can execute a local `dry-run` that builds the synthetic package and compares it to one or more known-good `.gcode.3mf` references without touching Bambuddy upload flows
- the synthetic builder can optionally use a working reference package as a template for missing filament colours and map semantics, and the viewer now exposes structured manual inputs for the remaining Path 2 gaps

The latest comparison against a working backup source package showed the synthetic artifact is still far from canonical parity: a generated package from `cache/(Unsaved)_plate_4.gcode` had 6 entries while the working `Pants-ANGER_plate_4.gcode.3mf` reference had 47, including missing model payload, per-plate JSON, md5, preview families, and a much richer `project_settings.config` surface.

Follow-up comparison against paired multi-filament cache examples showed a narrower result: raw gcode can preserve useful filament structure such as `filament_ids`, `filament_type`, AMS/tool-change intent, `flush_volumes_matrix`, and `nozzle_diameter`, but it still does not reliably preserve the final filament colours or the exact filament-map conventions encoded in the working `.3mf` packages.

Those adjacent repair patterns are now documented in the print_history feature docs so the archive-fix plan covers both:

- replacement-archive recovery via `POST /archives/upload`
- optional canonical runtime repair via direct DB repair tooling or a sidecar/admin boundary

### Explicitly not chosen

- relying on Bambuddy `rescan` for fallback archives
- relying on Bambuddy `upload-source` as a true archive repair primitive
- relying on undocumented `ha_bambulab` internals as the primary integration contract

## Option Comparison

| Option | Viable? | Why it wins or loses |
|--------|---------|----------------------|
| HA detection only | Yes | Lowest risk, immediate value, no printer-side recovery required |
| HA or `n8n` recovery worker + `POST /archives/upload` | Yes | Best practical repair path without Bambuddy changes |
| Bambuddy `upload-source` against fallback archive | Weak | Adds provenance only; does not rebuild main archive metadata path |
| `ha_bambulab` internal cache reuse | Partial | Technically possible, but not a stable supported interface |
| Bambuddy in-place repair via API | No, not today | Requires upstream Bambuddy change |

## Why `n8n` Wins

Compared with `shell_command`, `n8n` is the better long-term orchestration choice because it handles:

- delayed retries and branching more cleanly
- HTTP + FTP + conditional logic in one place
- credentials and operator visibility better than raw shell execution
- future approval gates or notification callbacks more naturally

`shell_command` still has value as a thin bridge for initial manual recovery if `n8n` is not ready yet.

## Design Principles

### 1. Preserve Bambuddy as source of truth for archives

Home Assistant should not become the primary archive system. It should detect, annotate, surface, and optionally orchestrate repair.

### 2. Prefer supported APIs over internal coupling

Even though `ha_bambulab` contains mature FTP retrieval code, its internal cache and helper views are not the right foundation for a durable repository feature unless no better path exists.

### 3. Keep repair workflows explainable

When recovery happens, the system should make it obvious which archive was broken, which archive replaced it, and whether recovery fully succeeded.

### 4. Optimize for observability first

Detection and surfacing are more important than silent best-effort recovery. A visible exception path is valuable even before full automation exists.

## Architecture Overview

### Detection path

1. Print starts
2. Bambuddy creates either a normal archive or a fallback archive
3. Home Assistant stores the active `archive_id`
4. A delayed integrity check fetches archive detail from Bambuddy
5. If fallback indicators are present, HA records an archive exception
6. `print_history` surfaces the exception with warning affordances

### Recovery path

1. HA or n8n sees an incomplete archive
2. External worker retries printer-side `.3mf` retrieval using known filename and path heuristics
3. On success, worker uploads the recovered `.3mf` to Bambuddy using `POST /archives/upload`
4. Worker tags or annotates both old and new archives to preserve lineage
5. HA refreshes and clears or downgrades the exception state

## Recommended Phasing

### Phase A: Detection only

- add archive integrity checks
- add incomplete-archive indicators to history browsing
- add exception count and exception list views
- add notification hooks

### Phase B: Manual repair workflow

- design the external recovery runner contract
- allow operator-triggered recovery from HA into `n8n`
- document expected tagging and post-repair reconciliation

### Phase C: Automatic repair workflow

- run delayed and completion-time retrieval attempts
- automatically upload recovered `.3mf` files to Bambuddy
- auto-link old and recovered archives
- auto-close exceptions when the replacement archive is created

## Recommended Archive Linking Model

The old fallback archive should remain as an audit record, but it should be clearly marked.

### Fallback archive tags

- `exception:missing_3mf`
- `repair:pending` or `repair:failed`

### Replacement archive tags

- `repair:recovered`
- `recovered_from:{archive_id}`

These replacement tags are workflow markers, not permanent steady-state metadata. Once the runtime restore has verified cleanly and the original fallback archive is removed, collapse the surviving target back to notes-only provenance by removing `repair:recovered`, `recovered_from:{archive_id}`, and `recovery_source:*` from the target archive while retaining the structured recovery audit note.

### Optional notes linkage

Fallback archive note:

```text
Recovery attempted externally after fallback archive creation.
Replacement archive: #<new_id>
```

Recovered archive note:

```text
Recovered from fallback archive #<old_id> after delayed printer-side 3MF retrieval.
```

## Risks And Constraints

### Printer-side file availability is not guaranteed

Even a good recovery worker may fail if the printer no longer has the `.3mf`, or if the file was transient and removed quickly.

### Duplicate archive semantics require explicit UX

Because the no-change-Bambuddy path creates a new archive rather than repairing the old one, the UI must make the relationship obvious.

### `ha_bambulab` internals may drift

Its FTP logic is useful as a design reference, but consuming its private implementation directly would create upgrade risk.

## Recommended Next Step

Proceed with design-first implementation planning inside `print_history` only:

1. define the data additions to the trimmed history payload
2. define the exception sensor and dashboard contract
3. define the rest-command and script interfaces for archive integrity checks
4. define the HA-to-`n8n` recovery contract, but do not implement it yet
5. leave actual recovery execution external until the detection layer is stable

That planning surface now includes the dedicated runtime-repair docs under `docs/features/print_history/` so archive-fix design covers both replacement-archive recovery and canonical runtime correction.
