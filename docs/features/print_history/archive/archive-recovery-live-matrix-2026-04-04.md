# Archive Recovery Live Matrix 2026-04-04

Status: Archived
Last Reviewed: 2026-05-23
Functional Owner: print_history
Replaces: docs/features/print_history/recovery/archive-recovery-live-matrix-2026-04-04.md
Replaced By: none

## Purpose

Capture the current live Bambuddy fallback archive set, the best-known SD-card recovery source for each record, and the confidence level for replacement-archive recovery.

This is a point-in-time analysis based on:

- live Bambuddy API data from `http://bambuddy.socko.us/api/v1/archives/`
- SD-card backup files under `bambuddy/Backup SD Card - 2026-04-03/cache/`
- `.bbl` sidecar metadata in the same cache directory
- Bambuddy upload behavior from `.tmp/bambuddy-source`

## Recovery Source Priority

Use this fallback order when attempting replacement-archive recovery:

1. printer-cached sliced `.3mf`
2. Bambu Studio re-sliced and exported plate file
3. original Bambu Studio source project `.3mf`

Reason:

- tier 1 is closest to the real print artifact Bambuddy expects
- tier 2 can recreate a printer-destined sliced file offline, but it may differ from the original due to slicer version, preset, AMS mapping, or operator changes
- tier 3 is useful for provenance and model viewing, but is the weakest choice for canonical print-history reconstruction

## Current Fallback Set

As of 2026-04-04, the live fallback set contains exactly three archives:

- `174`
- `189`
- `191`

All three have the fallback signature:

- empty `file_path`
- `file_size = 0`
- missing `thumbnail_path`
- missing `content_hash`
- missing parser-derived metadata

Live recovery validation performed on 2026-04-04:

- archive `189` was successfully recovered to replacement archive `199`
- archive `191` was successfully recovered to replacement archive `200`
- both recoveries used the SD-cache sliced `.3mf` path and produced matching `content_hash` values
- archive `174` remains the only unresolved fallback case and should still be treated as `medium` confidence

## Recovery Matrix

| Fallback archive | Print name | Exact SD-card source file | Evidence | Confidence | Recommended recovery action |
| --- | --- | --- | --- | --- | --- |
| `174` | `200mm x 200mm Deadpool & Wolverine Hueforge` | `bambuddy/Backup SD Card - 2026-04-03/cache/200mm x 200mm Deadpool & Wolverine Hueforge.3mf` | matching `.bbl` sidecar `2_200mm x 200mm Deadpool & Wolverine Hueforge.bbl`; sidecar MD5 `FEAB4E6429CFA9E8A113295C3DB4B0CD` matches cached `.3mf`; cached `.3mf` SHA-256 `1AEDFF714998C7F18B179028B13F378683A2BB6D31A3C02BBB6CCF4790A87856` exactly matches successful live archive `181` | `medium` | recover only as a replacement/provenance archive, not as a guaranteed exact recreation of the original 174 run |
| `189` | `Hulk Stainglass Style Hueforge` | `bambuddy/Backup SD Card - 2026-04-03/cache/Adaptive Layer Height - 0.08mm layer, 2 walls, 100% infill.3mf` | matching `.bbl` sidecar `1_Adaptive Layer Height - 0.08mm layer, 2 walls, 100% infill.bbl`; sidecar MD5 `824D5690965E5088B4C6F3894CFB8858` matches cached `.3mf`; no competing live archive with the same filename | `high` | good candidate for replacement-archive recovery |
| `191` | `Captain America - Stainglass-style Hueforge` | `bambuddy/Backup SD Card - 2026-04-03/cache/200x200 - AMS Ready - Slice & Print.3mf` | matching `.bbl` sidecar `1_200x200 - AMS Ready - Slice & Print.bbl`; sidecar MD5 `0F00BC965D0D29A00DF496356B0526B1` matches cached `.3mf`; no competing live archive with the same filename | `high` | good candidate for replacement-archive recovery |

## Confirmed Live Results

### Archive 189

- fallback archive: `189`
- replacement archive: `199`
- recovery source: `sd_cache_3mf`
- outcome: success
- result tags:
	- old archive: `Hueforge,exception:missing_3mf,replaced_by:199`
	- new archive: `repair:recovered,recovered_from:189,recovery_source:sd_cache_3mf`

Validation summary:

- upload created a canonical archive with file path, thumbnail, and content hash
- `uploaded_content_hash` matched the SD-cache file SHA-256
- full mode successfully linked the old and new records without creating a second replacement after helper enhancement

### Archive 191

- fallback archive: `191`
- replacement archive: `200`
- recovery source: `sd_cache_3mf`
- outcome: success
- result tags:
	- old archive: `Hueforge,exception:missing_3mf,replaced_by:200`
	- new archive: `repair:recovered,recovered_from:191,recovery_source:sd_cache_3mf`

Validation summary:

- upload created a canonical archive with file path, thumbnail, and content hash
- `uploaded_content_hash` matched the SD-cache file SHA-256
- full mode successfully linked the old and new records

### Timestamp conclusion from live validation

- replacement archives `199` and `200` were created with recovery-time archive timestamps
- the original runtime timestamps were not written back into the canonical archive datetime fields
- current supported preservation path remains `[RECOVERY_AUDIT_V1]` notes on the recovered record

### Optional cleanup choice after successful recovery

After operator verification, there are two acceptable policies:

1. keep the historical fallback archive and the recovered archive together
2. manually delete the historical fallback archive through Bambuddy if the user prefers a cleaner archive list

Recommendation:

- keep both by default
- if deleting the fallback archive, ensure the recovered archive already contains the original runtime values in notes so historical timing is not lost entirely

## Confidence Rules Used

### High confidence

- exact cached `.3mf` exists
- matching `.bbl` sidecar exists
- sidecar MD5 matches the cached `.3mf`
- no competing live archive reuses the same filename in a way that creates ambiguity

### Medium confidence

- exact cached `.3mf` exists
- matching `.bbl` sidecar exists
- sidecar MD5 matches the cached `.3mf`
- but the filename collides with another successful archive or the cached file appears to correspond to a later plate/export rather than the original fallback run

## Candidate File Details

| Archive | Cached file | Last write time | SHA-256 |
| --- | --- | --- | --- |
| `174` | `200mm x 200mm Deadpool & Wolverine Hueforge.3mf` | `2026-03-30 21:10:16` | `1AEDFF714998C7F18B179028B13F378683A2BB6D31A3C02BBB6CCF4790A87856` |
| `189` | `Adaptive Layer Height - 0.08mm layer, 2 walls, 100% infill.3mf` | `2026-04-01 14:38:32` | `B4CF4E2F03A9E6B288A12E1B17FC2C6DC9F2C416ACA6B67251D23C05FABD8FDE` |
| `191` | `200x200 - AMS Ready - Slice & Print.3mf` | `2026-04-02 11:29:08` | `4EBA6B4EACE8D55A2C39C583E610AB7DD3DE22DBA54AB6D98C16F68AFD001953` |

## Case Notes

## Alternate Source Assessment: `Deadpool___Wolverine.3mf`

An original Bambu Studio project file is available at:

- `bambuddy/Backup SD Card - 2026-04-03/Deadpool___Wolverine.3mf`

Observed structure:

- contains full mesh/object payloads in `3D/Objects/object_1.model` and `3D/Objects/object_2.model`
- contains `Metadata/plate_1.json`, `Metadata/plate_2.json`, `Metadata/plate_1.png`, `Metadata/plate_2.png`, `Metadata/top_1.png`, `Metadata/top_2.png`
- contains `Metadata/project_settings.config` and `Metadata/model_settings.config`
- contains a very small `Metadata/slice_info.config` header only
- does **not** contain any embedded `Metadata/*.gcode` entries

Implications relative to Bambuddy source behavior:

- if attached through `POST /api/v1/archives/{id}/source` or `POST /api/v1/archives/upload-source`, Bambuddy will store it in `source_3mf_path` only; this is provenance attachment, not archive repair
- if uploaded through `POST /api/v1/archives/upload`, Bambuddy can still parse some metadata and generate a thumbnail, but the created archive will likely behave like a `Source` archive rather than a canonical `GCODE` archive

Why it is weaker than the printer-cached `.3mf`:

- Bambuddy archive parsing expects sliced signals such as embedded `Metadata/*.gcode` and richer `slice_info.config` plate metadata
- this file has no embedded G-code, so `has_gcode` will be false in archive capabilities
- `ArchivesPage.isSlicedFile()` treats a `.3mf` as sliced only when it has `total_layers` or `print_time_seconds`; this source file is unlikely to populate either field during upload
- multi-plate source projects do not tell `archive_print()` which plate was actually printed, so thumbnail and plate-specific metadata will default to the first available plate context

What Bambuddy can still recover from this source file if uploaded as a new archive:

- `file_path`
- `file_size`
- `content_hash`
- thumbnail image, likely defaulting to plate 1
- `print_name` or MakerWorld title/designer metadata if present in `3D/3dmodel.model`
- settings from `project_settings.config` such as `layer_height`, `nozzle_diameter`, printer model, printable area, and filament color/type lists
- model-viewer compatibility because the file contains real mesh data and plate JSON assets

What it probably will not recover well enough for canonical print-history replacement:

- embedded G-code availability
- `total_layers` from G-code header parsing
- `print_time_seconds` and `filament_used_grams` from sliced `slice_info.config`
- exact plate selection for a multi-plate print
- `GCODE` classification in the archive card UI

Practical recommendation:

- treat `Deadpool___Wolverine.3mf` as a fallback-of-last-resort source for archive `174`
- prefer the printer-cached sliced `.3mf` whenever available
- if the cached sliced file is unavailable, open the source project in Bambu Studio, slice the correct plate, and use `Export plate sliced file` before considering raw-source upload
- if used, annotate the resulting replacement archive as `source_only_recovery:true` or equivalent in recovery notes because it is likely to be useful for provenance and 3D viewing, but weaker for print-history parity

### Bambu Studio re-slice/export fallback

This is the recommended fallback between cached sliced files and raw source-project uploads.

Observed viability:

- Bambu Studio documents `Export plate sliced file` and `Export all plate sliced file` as an offline export path after slicing
- Bambu Studio source code separates generic project export from sliced-file export
- send-to-printer also runs through the slicing/export path before upload

Implication:

- you do not need to actually send to the printer to create a printer-destined-like artifact
- you do need a valid sliced result for the target plate before the export menu becomes available

Tradeoff:

- a re-sliced export is viable, but it is not guaranteed to be byte-identical to the original print artifact
- changes in printer profile, nozzle, Bambu Studio version, process preset, filament mapping, or plate selection can change the result

### Archive 174

This is the most ambiguous case.

Why:

- the cached `.3mf` is validated by sidecar MD5
- but that exact file also matches successful live archive `181`
- the sidecar is plate-specific (`2_...bbl`)
- the cached file timestamp is later than the fallback run represented by archive `174`

Interpretation:

- the SD-card file is a valid project-equivalent recovery source
- it is not strong evidence that the file is the original artifact for archive `174`
- the replacement archive should therefore be annotated as approximate provenance recovery, not exact historical reconstruction
- the original Bambu Studio file `Deadpool___Wolverine.3mf` is a weaker fallback than the cached sliced `.3mf`; use it only if the cached sliced file is unavailable

### Archive 189

This is a strong replacement candidate.

Why:

- unique filename in the live archive set
- matching `.bbl` sidecar with matching MD5
- cached `.3mf` contains the expected `Metadata/` preview, slice, and embedded gcode payloads required by Bambuddy upload parsing

### Archive 191

This is also a strong replacement candidate.

Why:

- unique filename in the live archive set
- matching `.bbl` sidecar with matching MD5
- cached `.3mf` contains the parser-relevant `Metadata/` payloads and plate preview assets

## Exact Recovery Workflow Drafts

### Archive 174 workflow

1. Read fallback archive `174` and preserve current `started_at`, `completed_at`, `actual_time_seconds`, `status`, tags, notes, and photos.
2. Preferred source order:
	a. `bambuddy/Backup SD Card - 2026-04-03/cache/200mm x 200mm Deadpool & Wolverine Hueforge.3mf`
	b. a Bambu Studio `Export plate sliced file` result produced from `bambuddy/Backup SD Card - 2026-04-03/Deadpool___Wolverine.3mf`
	c. raw `bambuddy/Backup SD Card - 2026-04-03/Deadpool___Wolverine.3mf` only as provenance/source fallback
3. Upload the highest-ranked available source with `POST /api/v1/archives/upload?printer_id=1`.
4. Expect Bambuddy to create a new canonical archive with recovered file metadata, thumbnail, content hash, and parsed print metadata.
5. Patch the old and new archives with lineage tags and `[RECOVERY_AUDIT_V1]` notes.
6. In the recovery notes, explicitly mark the result as one of:
	- `recovery_source:sd_cache_3mf`
	- `recovery_source:bambu_studio_exported_sliced_3mf`
	- `recovery_source:bambu_studio_source_3mf`
7. If the source was not the cached sliced file, explicitly mark the result as non-exact historical reconstruction.

What survives into the new archive automatically:

- `file_path`
- `file_size`
- `content_hash`
- `thumbnail_path`
- parsed slice metadata

What does not survive automatically:

- original `started_at`
- original `completed_at`
- original `actual_time_seconds`
- original fallback photos and notes
- certainty that the replacement file is the exact 174 print artifact

### Exact Bambu Studio export steps for archive 174 fallback

1. Open `bambuddy/Backup SD Card - 2026-04-03/Deadpool___Wolverine.3mf` in Bambu Studio.
2. Select the same printer family and nozzle profile used for the original job if known.
3. Confirm the correct plate is active. For Wolverine, this should be the plate whose model/preview matches the intended print.
4. Click `Slice plate`.
5. After slicing completes, use `File > Export > Export plate sliced file`.
6. Save the exported file to a staging folder and treat it as `recovery_source:bambu_studio_exported_sliced_3mf`.
7. Use that exported sliced file with the recovery helper in `Inspect`, then `Upload`, then `Full` mode.

Notes:

- if `Export plate sliced file` is disabled, the plate has not been sliced into a valid exportable result yet
- `Export Generic 3MF` is not the correct fallback for canonical archive recovery; it produces another project-style file, not the printer-destined sliced artifact

### Archive 189 workflow

1. Read fallback archive `189` and preserve its runtime fields and current notes.
2. Upload `bambuddy/Backup SD Card - 2026-04-03/cache/Adaptive Layer Height - 0.08mm layer, 2 walls, 100% infill.3mf`.
3. Confirm the new archive has a non-empty `file_path`, non-zero `file_size`, non-null `content_hash`, and a generated thumbnail.
4. Patch both records with lineage tags and `[RECOVERY_AUDIT_V1]` notes.
5. Mark the recovery as `confidence:high`.

Automatic survives:

- canonical file metadata
- parser-derived print metadata

Manual carry-forward only:

- original fallback `started_at`
- original fallback `completed_at`
- original fallback `actual_time_seconds`
- original fallback status semantics

### Archive 191 workflow

1. Read fallback archive `191` and preserve its runtime fields and current notes.
2. Upload `bambuddy/Backup SD Card - 2026-04-03/cache/200x200 - AMS Ready - Slice & Print.3mf`.
3. Confirm the new archive has a populated thumbnail, `content_hash`, and parsed print metadata.
4. Patch both records with lineage tags and `[RECOVERY_AUDIT_V1]` notes.
5. Mark the recovery as `confidence:high`.

Automatic survives:

- canonical file metadata
- parser-derived print metadata

Manual carry-forward only:

- original fallback `started_at`
- original fallback `completed_at`
- original fallback `actual_time_seconds`
- original fallback status semantics

## Recommendation

Use archives `189` and `191` as the first live replacement-recovery tests.

Reason:

- both have high-confidence SD-card matches
- both avoid the filename-collision ambiguity present in archive `174`
- both are better candidates for validating the recovery workflow before tackling approximate/provenance recovery cases