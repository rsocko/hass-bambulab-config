# Historical Archive Backfill From SD-Card Artifacts

## Purpose

Define how the existing fallback-archive recovery design can be extended to import older print records into Bambuddy when those prints happened before Bambuddy was installed and therefore no Bambuddy archive row exists yet.

This document is intentionally adjacent to the fallback-recovery docs, not a replacement for them.

## Short Answer

Yes, the current replacement-archive recovery design can be leveraged for historical backfill, but only partially.

What already carries over well:

- ranked source selection for `.3mf` inputs
- archive creation through `POST /api/v1/archives/upload?printer_id=...`
- optional canonical runtime repair through the existing Python repair core or sidecar
- provenance tags and structured recovery notes

What does **not** carry over by itself:

- discovering which SD-card files represent real historical prints
- preventing duplicate imports when an equivalent archive already exists
- distinguishing `already represented` from `same archived file but suspiciously different archive metadata`
- reconstructing original runtime timestamps from file upload alone
- restoring photos, timelapses, favorites, or print-log rows automatically

That means historical backfill needs one extra layer ahead of the current design:

- **intake and dedupe workflow** before upload

## Relationship To Existing Docs

Use these documents together:

- [archive-detection-recovery-design.md](archive-detection-recovery-design.md) for the replacement-archive model
- [archive-runtime-field-impact-matrix.md](archive-runtime-field-impact-matrix.md) for which runtime fields matter
- [archive-runtime-db-repair-guide.md](archive-runtime-db-repair-guide.md) for canonical timestamp repair limits
- [archive-runtime-sidecar-api-and-compose.md](archive-runtime-sidecar-api-and-compose.md) for the current repair boundary
- [archive-recovery-live-matrix-2026-04-04.md](archive-recovery-live-matrix-2026-04-04.md) for evidence already collected from the SD backup analysis

## What The Current Design Already Proves

The current print-history recovery docs establish four important points that also apply to historical backfill:

1. A printer-cached sliced `.3mf` is the best available reconstruction source.
2. Uploading that file through Bambuddy creates a canonical file-backed archive with thumbnail, content hash, and parser-derived metadata.
3. Upload alone does not restore the original runtime timeline.
4. Direct DB repair or a sidecar is the current practical path when canonical `created_at`, `started_at`, and `completed_at` must be corrected.

Those points are enough to justify a historical-import workflow.

## Key Difference: Backfill Versus Fallback Repair

Fallback repair starts with an existing Bambuddy archive ID.

Historical backfill does not.

So the backfill workflow must answer these questions first:

1. Which SD-card files represent completed historical prints worth importing?
2. Which of those already have an equivalent Bambuddy archive and should be skipped?
3. Which source is authoritative enough to upload as a canonical archive versus only attach as provenance?
4. Where should original timing come from if the file itself does not carry trustworthy runtime timestamps?

## Source Ranking For Historical Backfill

Use the same ranking already established for fallback recovery:

1. printer-cached sliced `.3mf`
2. Bambu Studio `Export plate sliced file` result derived from the original project
3. raw Bambu Studio source-project `.3mf`

Interpretation:

- tier 1 is suitable for canonical historical archive import
- tier 2 is acceptable but should be marked as reconstructed rather than original
- tier 3 is usually provenance-grade only and may not restore full sliced metadata parity

## What Data Can Be Restored

### Usually restorable from a sliced `.3mf` upload

- `file_path`
- `file_size`
- `content_hash`
- `thumbnail_path`
- `print_name`
- `print_time_seconds`
- `filament_used_grams`
- `filament_type`
- `filament_color`
- `layer_height`
- `total_layers`
- `nozzle_diameter`
- `nozzle_temperature`
- other parser-derived sliced metadata that Bambuddy already extracts today

### Not restored automatically by upload

- original `created_at`
- original `started_at`
- original `completed_at`
- original `actual_time_seconds`
- original print outcome semantics beyond the upload-time default `archived`
- photos
- timelapse attachment
- favorites
- operator notes and tags unless written separately
- `print_log_entries`

### Weaker or ambiguous when the source is a raw project `.3mf`

- exact printed plate
- embedded G-code availability
- `total_layers`
- `print_time_seconds`
- `filament_used_grams`
- final archive classification parity with a real sliced artifact

## Are The Existing Sidecar And Python Repair Design Sufficient?

Not by themselves.

The current repair core and sidecar are sufficient for **canonical field correction after an archive already exists**. They are not sufficient for **historical import orchestration**.

Today they support:

- `archive_id`
- `started_at`
- `completed_at`
- `created_at`
- `status`
- `failure_reason`
- audit note append to `notes`

That is enough to fix the key canonical runtime fields after upload.

It is **not** enough for:

- archive creation from a source file
- bulk intake of many SD-card candidates
- duplicate detection
- copying or attaching photos and timelapses
- copying favorites or other UI state
- repairing `print_log_entries`
- preserving a manifest of which source file created which archive

### Recommended conclusion

Keep the current repair core exactly for what it is good at:

- canonical runtime correction after upload

Add a separate import runner for historical backfill that does:

- file discovery
- evidence extraction
- dedupe
- upload
- post-upload tagging and notes
- optional call into the existing repair core when dates are available

## Historical Backfill Workflow

## Phase 1: Build a candidate manifest

For each candidate in the SD backup, record:

- `source_path`
- `source_type` (`sd_cache_3mf`, `bambu_studio_exported_sliced_3mf`, `bambu_studio_source_3mf`)
- `file_size`
- `source_md5`
- `source_sha256`
- sibling `.bbl` path if present
- file last-write time
- parsed filename stem
- confidence level
- evidence notes

Also record lightweight structural classification:

- has embedded `Metadata/*.gcode`
- has rich `slice_info.config`
- has plate previews
- looks like sliced artifact versus source project

### Current repo implementation

The repo now has a resumable manifest contract built around:

- [tools/bambuddy/generate_archive_backfill_manifest.py](../../../tools/bambuddy/generate_archive_backfill_manifest.py)
- [tests/phase3/print_history/Test-BambuddyArchiveRecovery.ps1](../../../tests/phase3/print_history/Test-BambuddyArchiveRecovery.ps1)

The generated manifest now carries additional operator-state fields per candidate:

- `processing_bucket`
- `selected_action`
- `batch_id`
- `import_status`
- `matched_archive_id`
- `created_archive_id`
- `last_attempted_at`
- `operator_note`

The generator also emits top-level resumability metadata:

- `schema_version`
- `batch_size`
- `candidate_counts_by_bucket`
- `batch_counts`
- `source_inventory`

Initial bucket behavior is intentionally conservative:

- `sd_cache_3mf` and `bambu_studio_exported_sliced_3mf` start as `batch_ready`
- `bambu_studio_source_3mf` starts as `manual_review`
- top-level directory inventory is recorded so non-import areas such as printer logs and media can be retained separately from archive inputs

Recommended manifest generation example:

```powershell
python .\tools\bambuddy\generate_archive_backfill_manifest.py `
   --source-root '.\bambuddy\Backup SD Card - 2026-04-03' `
   --output '.\tmp\archive_backfill_manifest.json' `
   --batch-size 25
```

Recommended inspect-only batch review example:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' `
   -Mode Backfill `
   -BaseUrl 'http://bambuddy.socko.us' `
   -PrinterId 1 `
   -ManifestPath '.\tmp\archive_backfill_manifest.json' `
   -BackfillAction Inspect `
   -BatchId 'batch-001' `
   -UpdateManifest `
   -ResultPath '.\tmp\archive_backfill_batch-001_inspect.json'
```

Recommended upload-and-annotate batch example:

```powershell
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' `
   -Mode Backfill `
   -BaseUrl 'http://bambuddy.socko.us' `
   -PrinterId 1 `
   -ManifestPath '.\tmp\archive_backfill_manifest.json' `
   -BackfillAction Full `
   -BatchId 'batch-001' `
   -UpdateManifest `
   -ResultPath '.\tmp\archive_backfill_batch-001_full.json'
```

With `-UpdateManifest`, the runner updates each candidate in place after it is inspected, skipped, uploaded, annotated, or fails. That makes batch execution resumable without maintaining a separate progress database.

### Optional runtime-repair flow

The same runner now supports an optional post-import runtime-repair stage:

- `-RepairAction None` leaves imports file-backed and provenance-only
- `-RepairAction Preview` computes proposed runtime values and stores them in output and manifest state without touching Bambuddy DB fields
- `-RepairAction Apply` sends the inferred runtime fields through the Bambuddy runtime-repair sidecar after import or against an already imported manifest candidate
- operator-facing sidecar base URL: `http://bambuddy-runtime-repair.socko.us`
- local-host fallback for direct port mapping: `http://127.0.0.1:8818`

Recommended preview example against an already imported candidate:

```powershell
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' `
   -Mode Backfill `
   -BaseUrl 'http://bambuddy.socko.us' `
   -PrinterId 1 `
   -ManifestPath '.\tmp\archive_backfill_manifest.json' `
   -ManifestEntryId '<entry_id>' `
   -BackfillAction Full `
   -RepairAction Preview `
   -RepairSidecarBaseUrl 'http://bambuddy-runtime-repair.socko.us' `
   -RepairSidecarToken $env:REPAIR_API_TOKEN `
   -UpdateManifest `
   -ResultPath '.\tmp\archive_backfill_repair_preview.json'
```

Recommended apply example against the deployed sidecar:

```powershell
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' `
   -Mode Backfill `
   -BaseUrl 'http://bambuddy.socko.us' `
   -PrinterId 1 `
   -ManifestPath '.\tmp\archive_backfill_manifest.json' `
   -ManifestEntryId '<entry_id>' `
   -BackfillAction Full `
   -RepairAction Apply `
   -RepairSidecarBaseUrl 'http://bambuddy-runtime-repair.socko.us' `
   -RepairSidecarToken $env:REPAIR_API_TOKEN `
   -UpdateManifest `
   -ResultPath '.\tmp\archive_backfill_repair_apply.json'
```

Current repair inference is intentionally conservative:

- `completed_at` prefers filesystem last-modified time, then ZIP/config timestamps if filesystem evidence is unavailable
- `started_at` is only estimated as `completed_at - print_time_seconds` when the uploaded archive exposes parser-backed `print_time_seconds`
- `created_at` follows the inferred completion time for completed-print style historical records
- automatic apply is blocked when timing confidence stays `low`
- status is not changed by default; add `-RepairSetCompletedStatus` only when you explicitly want medium-confidence imports to flip from `archived` to `completed`
- preview and apply are both sent through the existing sidecar `POST /admin/archive-runtime-repair` endpoint; preview uses sidecar `dry_run: true`, apply uses `dry_run: false`

This keeps preview and apply separate: preview is safe evidence review validated by the sidecar, while apply is an explicit administrative action executed through the same sidecar boundary that already owns direct DB access.

## Phase 2: Compare against existing Bambuddy archives

Build an index from current Bambuddy archives using at least:

- `id`
- `content_hash`
- `file_size`
- `filename`
- `print_name`
- `created_at`
- `started_at`
- `completed_at`
- `status`
- tags and notes

Then apply duplicate rules in this order.

### Duplicate rule 1: exact content hash match

If candidate `source_sha256` equals archive `content_hash`, treat it as already represented.

Result:

- do not upload a new archive
- optionally annotate the existing archive with provenance notes if that adds value

Important nuance:

- an exact hash match proves the archived file is already represented
- it does **not** prove the existing archive metadata is semantically correct for the intended print record
- if the matched archive has materially different `print_name`, suspicious duplicate-chain behavior, or prior repair flags, route the candidate to manual review instead of silently treating it as a clean skip

### Duplicate rule 2: existing import manifest match

If a local import manifest already maps the source hash or source path to an archive ID, skip it.

This is the main guard against rerunning the batch and creating duplicates later.

### Duplicate rule 2b: existing provenance-store match

If the Home Assistant print-history SQLite store already records the same `source_sha256`, `source_md5`, or normalized `source_path` as previously handled, skip or reopen the prior review record instead of creating a new archive.

This is how we avoid duplicate imports when the same print was:

- captured in real time by Bambuddy
- restored later from a fallback/replacement workflow
- imported separately from an SD-card backup or workstation export

### Duplicate rule 3: strong filename plus date-window match

If content hash is unavailable on the existing side, use a secondary heuristic only for manual-review candidates:

- normalized filename match
- similar file size
- plausible date proximity
- matching or very similar `print_name`

Do not auto-skip on this rule alone unless confidence is very high.

### Duplicate rule 4: suspicious same-hash, different-name chain

If a candidate or target archive would land in a duplicate chain where:

- `duplicate_sequence > 0`, or
- `original_archive_id` points to a different-looking print history entry, or
- same-hash archives have materially different normalized names,

do not auto-delete or auto-skip blindly.

Mark the case as `suspicious_duplicate` and route it through the mismatch-review workflow documented in [archive-mismatch-repair-design.md](archive-mismatch-repair-design.md).

## Phase 3: Upload only high-confidence canonical candidates

Auto-upload only when both are true:

- source classification says `sliced` or equivalent
- duplicate checks do not find an existing canonical archive

After upload, patch the new archive with:

- `historical_import:true` tag or equivalent
- `import_source:<source_type>`
- source hash in notes
- evidence summary in `[RECOVERY_AUDIT_V1]` or a sibling versioned note block

## Phase 4: Repair canonical runtime fields when dates are trustworthy

Only after the new archive exists:

1. decide whether runtime evidence is strong enough
2. if yes, call the existing Python repair core or sidecar to update:
   - `created_at`
   - `started_at`
   - `completed_at`
   - optional `status`
   - optional `failure_reason`
3. append an audit note saying where those values came from

If the date evidence is weak, keep canonical Bambuddy times as import-time values and store the best-known original timing only in notes.

## Date Sources And How Much They Help

### 1. Existing Bambuddy archive row

Best case, but only applies when there is already a fallback or mismatched record.

Strength:

- strongest source for original runtime semantics already known to Bambuddy

Use for:

- replacement-archive repair
- copying timing into a new recovered archive

### 2. SD-cache file last-write time

Available in the current analysis and already recorded in the live matrix.

Strength:

- helpful for ordering and rough completion-time inference

Limit:

- not authoritative for print start
- may reflect copy/export timing instead of print completion

### 3. `.bbl` sidecar metadata

The current repo analysis already proves `.bbl` sidecars are useful for:

- matching the cached `.3mf`
- plate-specific evidence
- MD5 verification

Potential value for dates:

- if those files also carry timing fields in your retained backups, they would be better than raw file mtime

Current limitation:

- the checked-in docs only validate MD5 and plate linkage, not a trustworthy start/end timestamp field

So treat `.bbl` dates as a thing to inspect, not as a proven canonical source yet.

### 3b. Filename and directory naming conventions

Possible value:

- filename stems may contain exported model names, plate labels, or workflow-specific timestamps
- cache or backup directory structure may imply whether the file came from printer cache versus workstation export

Limits:

- naming conventions are weak evidence for actual runtime
- they are useful for clustering, matching, and manual review, not for direct canonical timestamp writes by themselves

### 4. Home Assistant recorder history

Potentially strong if recorder retention covers the historical period.

Possible signals:

- printer state changes
- progress changes
- nozzle/bed activity
- AMS tray usage changes

Use for:

- estimating or confirming start/end windows
- deriving `status`

### 5. Bambuddy `print_log_entries`

Only relevant if a historical row already exists in Bambuddy.

Important constraint:

- `print_log_entries` are independent and do not auto-repair when `print_archives` is updated

That makes them useful as evidence, but not something the current repair path fixes automatically.

### 6. Timelapse or photo file timestamps

Potentially useful supporting evidence if media files survive in storage.

Good for:

- rough completion time
- confirming a print existed

Weak for:

- exact start time

### 7. Bambu Studio project metadata

Useful for model and slicer context.

Weak for:

- actual print runtime

### 8. 3MF internal timestamps and slicer config members

The manifest tooling already extracts:

- ZIP member min/max timestamps
- timestamp-like fields from selected config members

Use for:

- supporting evidence when corroborated by stronger sources
- choosing between multiple candidate completion windows

Weak for:

- treating the timestamp as direct proof of printer start or finish without corroboration

## Recommended Date Policy

Use three confidence tiers.

### High-confidence dates

Use for canonical repair.

Examples:

- existing fallback archive timing
- HA recorder history with clear start and finish transitions
- validated sidecar or log-derived timestamps tied to the exact file and plate

### Medium-confidence dates

Keep in notes by default, repair canonically only with operator approval.

Examples:

- `.bbl` timestamp fields not yet validated against known archives
- combined evidence from file mtime plus HA state history

### Low-confidence dates

Do not write canonically.

Examples:

- raw source-project timestamps
- copied-file modification times with no corroboration

## Recommended Timing Inference Pipeline

When no existing Bambuddy source archive exists, infer timing in this order.

### Step 1: infer `completed_at`

Preferred ranking:

1. HA recorder end-of-print transition for the matching print
2. validated `.bbl` completion-like field for the matching sliced artifact
3. filesystem last-write time for the cached/exported sliced file
4. latest corroborated ZIP/config timestamp inside the `.3mf`

### Step 2: infer `started_at`

Preferred ranking:

1. HA recorder start-of-print transition
2. validated `.bbl` start-like field
3. `completed_at - print_time_seconds` when the artifact is a sliced `.3mf` and `print_time_seconds` is parser-backed

Important rule:

- if `started_at` is derived from `completed_at - print_time_seconds`, mark it as estimated even when the overall timing confidence is medium or high

### Step 3: infer `created_at`

Use the best available archival milestone:

- original completion time when the archive logically represents a completed print record
- otherwise the strongest evidence timestamp that most closely reflects when the artifact was created on the printer/export path

### Step 4: assign confidence

Suggested rubric:

- `high`: recorder or validated sidecar evidence directly supports start and end
- `medium`: at least two independent sources agree, with one of them being file-backed or `.bbl` evidence
- `low`: only one weak source exists, or multiple weak sources conflict

### Step 5: choose canonical write versus provenance only

- `high`: allow automatic canonical repair after upload
- `medium`: require explicit operator approval or a follow-up `update to inferred times` action
- `low`: do not change canonical Bambuddy times; store inference only as provenance

## Where This Metadata Should Live

Your assumption is directionally correct: the natural place for metadata that Bambuddy does not model well is the existing Home Assistant print-history SQLite store, not a large expansion of Bambuddy notes or Layer 1 browser payloads.

Recommended storage split:

- **Bambuddy archive row**: keep canonical fields plus compact provenance markers such as `[HISTORICAL_IMPORT_V1]` or `[RECOVERY_AUDIT_V1]`
- **HA print-history SQLite store**: keep rich provenance, timing evidence, duplicate-review state, and operator decisions
- **Layer 1 page payload**: keep only compact summary fields needed broadly for browser/popup presentation

Recommended HA-side fields to maintain per archive or candidate:

- `origin_kind`
- `source_sha256`
- `source_md5`
- `source_path`
- `restored_from_archive_id`
- `replaced_archive_id`
- `duplicate_review_state`
- `inferred_started_at`
- `inferred_completed_at`
- `inferred_created_at`
- `timing_confidence`
- `timing_sources`
- `timing_applied_to_canonical`

Implementation note:

- the current integration store already maintains review and lineage tables, so extending that store is lower risk than overloading Bambuddy notes with full evidence blobs

## Recommended Import Manifest

Maintain a JSON or CSV manifest outside Bambuddy with one row per attempted source file:

- `source_path`
- `source_sha256`
- `source_md5`
- `source_type`
- `import_status` (`skipped_existing`, `uploaded`, `manual_review`, `failed`)
- `matched_archive_id`
- `created_archive_id`
- `date_confidence`
- `notes`

This manifest is the practical answer to avoiding duplicate imports over time.

Do not rely only on archive tags for idempotency.

## Initial Tooling In This Repo

The repo now has two operator-side building blocks for this workflow:

- `tools/bambuddy/generate_archive_backfill_manifest.py`
- `tests/phase3/print_history/Test-BambuddyArchiveRecovery.ps1 -Mode Backfill`

### Manifest generator

Example:

```powershell
python .\tools\bambuddy\generate_archive_backfill_manifest.py --source-root '.\bambuddy\Backup SD Card - 2026-04-03' --output '.\tmp\bambuddy-backfill-manifest.json'
```

What it records per candidate:

- hashes
- basic sliced-versus-source classification
- sibling `.bbl` linkage if present
- filesystem last-write time
- ZIP entry min/max timestamps from the `.3mf`
- best-effort timestamp candidates found in `.bbl` and selected config members inside the `.3mf`

Important limit:

- these timestamp candidates are evidence only until validated against known-good historical prints
- the current sidecar does not yet consume this manifest or these timing candidates directly

### Backfill helper mode

Inspect only:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' -Mode Backfill -BaseUrl 'http://bambuddy.socko.us' -PrinterId 1 -ManifestPath '.\tmp\bambuddy-backfill-manifest.json' -BackfillAction Inspect
```

Upload only high-confidence non-duplicate candidates:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' -Mode Backfill -BaseUrl 'http://bambuddy.socko.us' -PrinterId 1 -ManifestPath '.\tmp\bambuddy-backfill-manifest.json' -BackfillAction Full
```

Behavior:

- dedupes against existing Bambuddy archives by exact `content_hash`
- skips raw source-project `.3mf` inputs by default
- annotates created archives with `[HISTORICAL_IMPORT_V1]` notes and import tags in `Full` mode

### How to interpret Backfill results

The helper returns one result row per candidate.

Status meanings:

- `skipped_existing_content_hash`: a current Bambuddy archive already matches the file by exact hash; do not import again
- `skipped_manifest_state`: the manifest already records the candidate as handled; use this as an idempotency guard
- `inspect_ready`: candidate passed current automatic checks and is eligible for upload
- `manual_review_source_only`: candidate is a raw source-project `.3mf`; import only if you accept weaker print-history parity
- `uploaded`: archive was created, but the run did not add historical-import notes or tags because `BackfillAction` was `Upload`
- `uploaded_and_annotated`: archive was created and annotated with historical provenance metadata

Recommended operator policy:

- treat `skipped_existing_content_hash` as a final skip unless you have a reason to annotate the already-existing archive
- treat `inspect_ready` plus `source_type=sd_cache_3mf` as the main auto-import path
- treat `manual_review_source_only` as a hold state, not a failure
- treat suspicious same-hash, different-name matches as review cases, not automatic clean skips
- prefer manual review whenever the source is not sliced, the filename is ambiguous, or you plan to repair canonical runtime fields afterward

## What Makes A Candidate Strong Enough To Import

Best-case signals:

- `source_type = sd_cache_3mf`
- `confidence = high`
- `structural_signals.has_embedded_gcode = true`
- `structural_signals.has_slice_info = true`
- sibling `.bbl` exists and `structural_signals.bbl_hash_match = true`

Still usable, but weaker:

- `source_type = bambu_studio_exported_sliced_3mf`
- medium confidence with sliced signals present
- timestamps available only as filesystem or ZIP metadata

Usually manual-review only:

- `source_type = bambu_studio_source_3mf`
- no embedded G-code
- weak or conflicting timestamp evidence
- filename collisions with existing known archives

## How To Read Timestamp Evidence

The manifest captures timestamp candidates from several places, but they are not all equally trustworthy.

Interpret them like this:

- filesystem `last_modified`: useful for rough ordering and possible completion-time hints
- ZIP member timestamps from the `.3mf`: useful as supporting evidence for when the artifact was assembled
- `.bbl` timestamp-like fields: promising, but must be validated against known-good historical prints before using them canonically
- config-member timestamps inside the `.3mf`: useful for context, but not automatically equal to real printer runtime

Default rule:

- use timestamp evidence to rank confidence first
- only use it for canonical Bambuddy runtime repair after independent validation

To force a project-level source upload for manual experimentation, add:

```powershell
-AllowSourceProjectImport
```

## Recommended Notes Contract For Historical Imports

Use a versioned block on imported records.

Example:

```text
[HISTORICAL_IMPORT_V1]
{"import_source":"sd_cache_3mf","source_sha256":"...","source_md5":"...","source_path":"Backup SD Card/cache/example.3mf","date_confidence":"medium","original_started_at":"2026-03-31T18:04:12+00:00","original_completed_at":"2026-03-31T21:47:05+00:00","timing_source":"ha_recorder_plus_sd_mtime"}
```

Use `[RECOVERY_AUDIT_V1]` when the import is replacing an existing fallback archive.

Use `[HISTORICAL_IMPORT_V1]` when there was no original Bambuddy archive at all.

## Recommendation

Historical backfill is feasible and should reuse the current upload-plus-runtime-repair architecture, but it needs a dedicated intake layer.

Recommended implementation order:

1. keep using the existing manifest generator as the intake/evidence stage
2. add a persistent HA-side provenance store keyed by source hashes and archive lineage
3. expand dedupe to distinguish `already represented` from `suspicious duplicate/mismatch`
4. auto-upload only high-confidence sliced candidates that clear duplicate review
5. add a timing-inference scorer that ranks filesystem, `.bbl`, recorder, filename, and internal `.3mf` evidence
6. extend the sidecar with an explicit `apply inferred runtime` path or request flag for approved medium/high-confidence timing
7. keep low-confidence timing evidence in provenance metadata instead of forcing it into canonical fields

This keeps the current runtime-repair design narrow and defensible while making historical import possible without pretending the source files carry more truth than they actually do.