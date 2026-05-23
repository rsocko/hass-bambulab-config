# Archive Recovery Interim Test Plan

## Purpose

Define a safe, staged method for testing replacement-archive recovery before any Home Assistant automation or `n8n` workflow is allowed to create records automatically.

This plan intentionally separates:

- read-only inspection
- upload-only record creation
- lineage annotation and cleanup
- later HA-driven orchestration

## Recommended Order

1. dry-run inspection against a known fallback archive
2. upload-only recovery for one high-confidence case
3. manual lineage annotation of old and new archives
4. repeat for the second high-confidence case
5. only then design HA or `n8n` orchestration around the proven manual flow

## Recommended First Test Cases

Start with these archives in order:

1. `189`
2. `191`
3. `174` only after the first two are validated

For archive `174`, prefer this source order:

1. `bambuddy/Backup SD Card - 2026-04-03/cache/200mm x 200mm Deadpool & Wolverine Hueforge.3mf`
2. Bambu Studio `Export plate sliced file` output produced from `bambuddy/Backup SD Card - 2026-04-03/Deadpool___Wolverine.3mf`
3. `bambuddy/Backup SD Card - 2026-04-03/Deadpool___Wolverine.3mf` only as a last-resort source-project fallback

## Test Harness

Use the helper script at:

- `tests/phase3/print_history/Test-BambuddyArchiveRecovery.ps1`

The helper supports these modes:

- `Inspect` - read-only
- `Upload` - create replacement archive only
- `Full` - create replacement archive and patch both old and new records with lineage metadata

Supported `RecoverySource` values:

- `sd_cache_3mf`
- `bambu_studio_exported_sliced_3mf`
- `bambu_studio_source_3mf`

## Stage 1: Read-only inspection

Goal:

- prove the fallback record and candidate source file line up before any write occurs

Command pattern:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' -Mode Inspect -BaseUrl 'http://bambuddy.socko.us' -PrinterId 1 -FallbackArchiveId 189 -SourceFilePath '.\bambuddy\Backup SD Card - 2026-04-03\cache\Adaptive Layer Height - 0.08mm layer, 2 walls, 100% infill.3mf' -RecoverySource 'sd_cache_3mf'
```

Expected outcome:

- fallback archive summary printed
- source file hash printed
- candidate recovery audit blocks printed
- no Bambuddy record created

## Stage 2: Upload-only recovery

Goal:

- verify Bambuddy can create a new canonical archive from the selected `.3mf`

Command pattern:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' -Mode Upload -BaseUrl 'http://bambuddy.socko.us' -PrinterId 1 -FallbackArchiveId 189 -SourceFilePath '.\bambuddy\Backup SD Card - 2026-04-03\cache\Adaptive Layer Height - 0.08mm layer, 2 walls, 100% infill.3mf' -RecoverySource 'sd_cache_3mf'
```

Expected outcome:

- a new archive is created
- the returned archive has non-empty `file_path`
- the returned archive has non-null `content_hash`
- the returned archive has a thumbnail

Validation checks:

- `GET /api/v1/archives/{new_id}` shows canonical file metadata
- the new archive `status` is `archived`
- the new archive `completed_at` reflects recovery time, not original print-complete time

## Stage 3: Full lineage and cleanup pass

Goal:

- preserve historical runtime context even though the new archive has recovery-time canonical timestamps

Command pattern:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' -Mode Full -BaseUrl 'http://bambuddy.socko.us' -PrinterId 1 -FallbackArchiveId 189 -SourceFilePath '.\bambuddy\Backup SD Card - 2026-04-03\cache\Adaptive Layer Height - 0.08mm layer, 2 walls, 100% infill.3mf' -ExistingReplacementArchiveId 199 -RecoverySource 'sd_cache_3mf'
```

Expected outcome:

- old archive receives replacement linkage tags and notes
- new archive receives recovery linkage tags and notes
- original fallback timing remains visible in `[RECOVERY_AUDIT_V1]`

## Timestamp model clarification

The runtime timestamps are not restored from the `.3mf` file itself.

Observed Bambuddy behavior from source:

- when Bambuddy sees a live print start, it creates or updates the archive using Bambuddy-observed event timing
- fallback archives created during a missing-3MF condition set `started_at` from `datetime.now(timezone.utc)` at fallback creation time
- `archive_print()` also sets `started_at` and `completed_at` from current server time based on archive status, not from parsed 3MF metadata
- upload recovery therefore creates a valid file-backed archive, but its canonical datetime fields reflect recovery-time processing, not the original historical print run

Practical takeaway:

- the 3MF is the source of sliced metadata such as print time estimate, filament usage, layers, temperatures, and thumbnails
- the actual runtime start/end values come from Bambuddy's live print lifecycle handling, not from the uploaded 3MF artifact

## Recovery audit contract

The interim test plan assumes this note block format:

```text
[RECOVERY_AUDIT_V1]
{"recovered_from_archive_id":189,"recovery_source":"sd_cache_3mf","original_status":"completed","original_started_at":"2026-04-01T19:48:07.427184","original_completed_at":"2026-04-02T02:44:14.275476","original_actual_time_seconds":24966}
```

The fallback archive should also receive the inverse linkage block:

```text
[RECOVERY_AUDIT_V1]
{"replaced_by_archive_id":<new_id>,"replacement_status":"archived"}
```

## API-Level Interim Steps

If you do not want to use the helper script, the manual flow is:

1. `GET /api/v1/archives/{fallback_id}`
2. `POST /api/v1/archives/upload?printer_id=1` with multipart `.3mf` file upload
3. `PATCH /api/v1/archives/{fallback_id}` to append tags and notes
4. `PATCH /api/v1/archives/{new_id}` to append tags and notes
5. `GET /api/v1/archives/{new_id}` to verify the created record

## Post-recovery cleanup runbook

If the operator wants a cleaner archive list after successful recovery, cleanup must stay manual.

Recommended decision order:

1. verify the replacement archive has file metadata, thumbnail, content hash, and `[RECOVERY_AUDIT_V1]`
2. verify the replacement archive notes include the original runtime values
3. decide whether to keep the fallback archive as a historical exception record or delete it

Default recommendation:

- keep both records

Optional manual deletion path:

1. record the fallback archive ID and replacement archive ID in change notes
2. confirm the replacement archive contains the original runtime values in notes
3. issue `DELETE /api/v1/archives/{fallback_id}` from Bambuddy UI or API
4. re-open the replacement archive and verify notes/tags still communicate provenance clearly

Deletion warning:

- deleting the fallback archive removes the easiest in-app copy of the original runtime record
- after deletion, the recovered archive notes become the primary retained source for original timing context

## Source-project fallback test

If you want to assess a Bambu Studio project file without creating records, run the helper in `Inspect` mode against the source file path.

Example:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' -Mode Inspect -BaseUrl 'http://bambuddy.socko.us' -PrinterId 1 -FallbackArchiveId 174 -SourceFilePath '.\bambuddy\Backup SD Card - 2026-04-03\Deadpool___Wolverine.3mf' -RecoverySource 'bambu_studio_source_3mf'
```

Interpretation rule:

- this validates provenance linkage only
- it does not prove that an upload would recreate a `GCODE` archive with sliced print metadata parity

## Bambu Studio re-slice fallback test

If the cached sliced file is unavailable, create a printer-destined fallback artifact in Bambu Studio.

Procedure for `174`:

1. Open `bambuddy/Backup SD Card - 2026-04-03/Deadpool___Wolverine.3mf`.
2. Select the intended printer profile and confirm the target plate.
3. Click `Slice plate`.
4. Use `File > Export > Export plate sliced file` once it becomes enabled.
5. Save the exported file to a local staging path.
6. Run the helper in `Inspect` mode first using `-RecoverySource 'bambu_studio_exported_sliced_3mf'`.

Example:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' -Mode Inspect -BaseUrl 'http://bambuddy.socko.us' -PrinterId 1 -FallbackArchiveId 174 -SourceFilePath 'C:\path\to\exported\Deadpool_Wolverine_plate2.gcode.3mf' -RecoverySource 'bambu_studio_exported_sliced_3mf'
```

Interpretation rule:

- this is the preferred fallback when no original cached sliced `.3mf` is available
- it is stronger than raw source-project upload, but still a reconstructed artifact rather than guaranteed original evidence

## HA-Friendly Interim Method

Do not make HA perform multipart file upload directly as the first implementation step.

Preferred interim method:

1. keep HA read-only for detection and exception surfacing
2. run the PowerShell helper manually from the workstation that holds the SD backup
3. once the manual flow is proven, wrap the helper or equivalent logic in `n8n`
4. only after that decide whether HA should expose a manual `Recover` button that triggers the external runner

Note:

- if local PowerShell policy blocks script execution, use `Set-ExecutionPolicy -Scope Process Bypass` for the current shell session only rather than changing machine-wide policy

## Suggested Validation Checklist

- fallback archive remains unchanged except for lineage metadata
- replacement archive has file-backed metadata
- replacement archive does not pretend to own the original runtime timestamps
- original runtime timestamps are preserved in notes
- tags make the old/new relationship obvious
- no second recovery run is attempted for the same fallback without operator intent

## Recommendation

Use this interim plan to prove the recovery semantics on `189` first, then `191`, then revisit whether `174` should be recovered as a medium-confidence provenance replacement.