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

### Duplicate rule 2: existing import manifest match

If a local import manifest already maps the source hash or source path to an archive ID, skip it.

This is the main guard against rerunning the batch and creating duplicates later.

### Duplicate rule 3: strong filename plus date-window match

If content hash is unavailable on the existing side, use a secondary heuristic only for manual-review candidates:

- normalized filename match
- similar file size
- plausible date proximity
- matching or very similar `print_name`

Do not auto-skip on this rule alone unless confidence is very high.

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

1. build a workstation-side or sidecar-assisted manifest generator for SD-card artifacts
2. add exact-hash dedupe against existing Bambuddy `content_hash`
3. auto-upload only high-confidence sliced candidates
4. call the existing runtime-repair core only when timing evidence is strong enough
5. keep weaker timing evidence in versioned notes instead of forcing it into canonical fields

This keeps the current runtime-repair design narrow and defensible while making historical import possible without pretending the source files carry more truth than they actually do.