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

- `entry_id` as a manifest-stable per-source candidate ID
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

- `entry_id`
- `processing_bucket`
- `selected_action`
- `batch_id`
- `import_status`
- `matched_archive_id`
- `created_archive_id`
- `last_attempted_at`
- `operator_note`
- `allow_same_content_reimport`

Identity and dedupe are intentionally separate:

- `entry_id` is the candidate identity used by the manifest and runner state machine
- `source_sha256` remains the archived file content hash used for duplicate detection
- that means multiple source files can legitimately share the same `source_sha256` without collapsing into one manifest row

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
   --output '.\bambuddy\backfill-state\archive_backfill_manifest_v2.json' `
   --batch-size 25
```

Recommended inspect-only batch review example:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' `
   -Mode Backfill `
   -BaseUrl 'http://bambuddy.socko.us' `
   -PrinterId 1 `
   -ManifestPath '.\bambuddy\backfill-state\archive_backfill_manifest_v2.json' `
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
   -ManifestPath '.\bambuddy\backfill-state\archive_backfill_manifest_v2.json' `

## Home Assistant Backfill Guardrail

During large historical imports, Home Assistant should run only the active Variant 3 browser backend:

- `homeassistant/custom_components/bambuddy/`
- `homeassistant/packages/3d_printing/print_history/template_sensors/`
- `homeassistant/packages/3d_printing/print_history/automations/`

The legacy REST polling path for `sensor.bambuddy_print_history` has been retired and moved under:

- `archive/print_history/legacy-yaml-browser/rest_sensors/`
- `archive/print_history/legacy-yaml-browser/helpers/input_number/`

That guardrail matters during backfill because the active Variant 3 integration already performs its own startup, webhook, and interval refresh. Keeping the legacy REST poller disabled avoids overlapping archive fetch cycles while imports are creating new Bambuddy archives.
   -BackfillAction Full `
   -BatchId 'batch-001' `
   -UpdateManifest `
   -ResultPath '.\tmp\archive_backfill_batch-001_full.json'
```

With `-UpdateManifest`, the runner updates each candidate in place after it is inspected, skipped, uploaded, annotated, or fails. That makes batch execution resumable without maintaining a separate progress database.

### Which `tmp` files need to be kept

For the current workflow, only the active manifest file needs to persist if the goal is to resume later without accidentally reimporting work that was already reviewed or processed.

Keep:

- `bambuddy/backfill-state/archive_backfill_manifest_v2.json` as the canonical resumable ledger for batch assignment, import status, matched archive IDs, created archive IDs, operator notes, and repair state

Do not rely on older or one-off outputs as the source of truth:

- `tmp/archive_backfill_manifest.json` is an older manifest version and should not remain the active ledger once v2 is in use
- `tmp/archive_backfill_batch-001_inspect_v2.json`, `tmp/archive_backfill_full_one.json`, and `tmp/archive_backfill_inspect.json` are per-run result snapshots
- `tmp/tiny_import_*.json` and `tmp/*repair*.json` are useful audit transcripts, but their important outcomes are already folded into the v2 manifest and the Bambuddy archive rows

Practical rule:

- if you want the minimum state needed to continue safely, keep `bambuddy/backfill-state/archive_backfill_manifest_v2.json`
- keep the other `tmp` JSON files only if you want an operator audit trail of specific preview, import, or repair runs

Current live checkpoint:

- archives `234` through `395`, plus `397`, `398`, `399`, `400`, `401`, and `402`, except anomalous `335`, are now recorded in the permanent manifest as completed historical imports with sidecar runtime repair applied
- candidate `E0B5292FB2715334668F6770768D92B08106DE61EB5FEAFB106643CE8D3489EE` (`cache/PLA - Small - works with 4 ½_ x 2 ¾_ wall plates and smaller.3mf`) returned `400 Bad Request`, but Bambuddy still created archive `335`; treat that archive as anomalous until it is reviewed and reconciled with the manifest
- candidate `A8EB3E6AF0CCC705A5F4AAF779C055AD9D94DA069EBF1BC23FC215E457750CC7` (`cache/Ø12x3mm  Magnet Version -0.2mm layer, arachne .3mf`) returned `400 Bad Request` and is now in manifest bucket `deferred` with `import_status: error`; no archive creation was observed in this run
- archive `250` was a manual legitimate same-hash reprint import from `cache/Filament_spool_holder_-_shelf_with_one_pipe.3mf` after operator confirmation that it was a real second print, not a duplicate to suppress
- they should not be re-run unless you are intentionally testing cleanup, replacement, or a new repair mode
- the most recent completed small runs created and repaired archives `254`, `255`, `256`, `257`, `258`, `259`, `260`, `261`, `262`, `263`, `264`, `265`, `266`, `267`, `268`, `269`, `270`, `271`, `272`, `273`, `274`, `275`, `276`, `277`, `278`, `279`, `280`, `281`, `282`, `283`, `284`, `285`, `286`, `287`, `288`, `289`, `290`, `291`, `292`, `293`, `294`, `295`, `296`, `297`, `298`, `299`, `300`, `301`, `302`, `303`, `304`, `305`, `306`, `307`, `308`, `309`, `310`, `311`, `312`, `313`, `314`, `315`, `316`, `317`, `318`, `319`, `320`, `321`, `322`, `323`, `324`, `325`, `326`, `327`, `328`, `329`, `330`, `331`, `332`, `333`, `334`, `336`, `337`, `338`, `339`, `340`, `341`, `342`, `343`, `344`, `345`, `346`, `347`, `348`, `349`, `350`, `351`, `352`, `353`, `354`, `355`, `356`, `357`, `358`, `359`, `360`, `361`, `362`, `363`, `364`, `365`, `366`, `367`, `368`, `369`, `370`, `372`, `373`, `374`, `375`, `376`, `377`, `378`, `379`, `380`, `381`, `382`, and `383`
- `D67FB61E6CE6E7CE38EE4C35BAD5E7146CDF5BDE04980A4543BD90ADC02F60A0` (`cache/100x100 - 0.08mm layer, 2 walls, 100% infill.3mf`) matched existing archive `73` by `content_hash` and was operator-reviewed as a true collapse, not a second-print import
- `F6C1FDB630EF5D1A0DFFE57418D60B2E10CFD99C39650FCB5D0A9DF37CCE03A7` (`cache/2 AMS.3mf`) matched existing archive `225` by `content_hash` and is now represented in the manifest as already in archive
- `1AEDFF714998C7F18B179028B13F378683A2BB6D31A3C02BBB6CCF4790A87856` (`cache/200mm x 200mm Deadpool & Wolverine Hueforge.3mf`) matched existing archive `181` by `content_hash`
- `76973985F87350420F8272E888DCAE3186774B9EE67F68FF53A85CB2299F7388` (`cache/200mm x 200mm Spiderman 4-color Hueforge.3mf`) matched existing archive `23` by `content_hash`
- `14FFD5889A13EFDFB609F7E9C0F3CB484375434A7EB5EB52FA8FBD5279FEFE16` (`cache/200mm x 200mm Stormtrooper Poker Hueforge.3mf`) matched existing archive `68` by `content_hash`
- `93CB5FDC3EF8CE8C21E4A757FC3C1D194AE6AFED68725F922D739EAE54DE32D8` (`cache/200mm x 400mm Darth Vader Light Saber 2-piece Hueforge.3mf`) matched existing archive `170` by `content_hash`
- `1BBEE9FFB7EB97E5DB97DD6FF9EB09658A3866CF41F82BB2BB3DD0B84D5AA7BA` (`cache/200mm x 400mm Luke Skywalker Light Saber 2-piece Hueforge.3mf`) matched existing archive `177` by `content_hash`
- `9CC0B28C8FC474FC2CDCA6CEA30900B4C2C9025CA565D3C49F602AFB10FC7E49` (`cache/200mm x 400mm Obi-Wan Light Saber 2-piece Hueforge.3mf`) matched existing archive `182` by `content_hash`
- `64F0988D6D0FDEFC84BC78B509AC12E89AAAF1A4DFC4F98BD4FD6652FC140015` (`cache/200mm, 6 color, 0.08mm layer, 1 walls, 100% infill.3mf`) matched existing archive `112` by `content_hash`
- `C3A3448D8C45C20CD2D555937F8B84726B33B288E48B2E5DE4CB8CD15457D2E9` (`cache/200x200 - 0.08mm layer, 2 walls, 100% infill.3mf`) matched existing archive `156` by `content_hash`
- `4EBA6B4EACE8D55A2C39C583E610AB7DD3DE22DBA54AB6D98C16F68AFD001953` (`cache/200x200 - AMS Ready - Slice & Print.3mf`) matched existing archive `200` by `content_hash`
- `95F373651EC9E55CA3B27AA78CDEF2AE9916FB7566A4AE2E35F1822EE9FAFEEB` (`cache/240-1w-1h-decor-drawer.stl + 240-1w-1h-decor-drawer.stl.3mf`) imported successfully as archive `263` with sidecar runtime repair applied
- `175A2230F4629EE3D1B461B0B8D9BBC851096137667B8D34BC005DDC8688923B` (`cache/600mm x 200mm 3-Piece Stormtrooper Hueforge Mural.3mf`) matched existing archive `124` by `content_hash`
- `5159262D9660C92CBF72811BD53EF70F8B35CEF221464A2F1D650C7E720B3CAC` (`cache/All (8) hooks on the same build plate.3mf`) matched existing archive `58` by `content_hash`
- `1480BD1FF6943C3C7291EF404679EAC35C87B44B9F7EC8AE3F137FDAA8747F23` (`cache/BAMBU - LEBRON signed lay - Large.3mf`) matched existing archive `77` by `content_hash`
- `CB431F9945339C850725F102B72DD9F95481934CC0F7CE32FA3D10858C8DBBCC` (`cache/BAMBU - LEBRON signed lay.3mf`) matched existing archive `75` by `content_hash`
- `FA78866937010B344D330CAA9CE9B5D489B56DA1C92927F28AE1E5F28D458EF7` (`cache/CURRY SIGNED - P2_Front_155x200.3mf`) matched existing archive `79` by `content_hash`
- `16E57F36BE95C328AFFDF1D5E6601DB77F4A64D9D8BB63B06FA6A525673D854C` (`cache/Designer Profile (Multi-Color, 0.16mm layer).3mf`) matched existing archive `184` by `content_hash`
- `C5646E6D686461D4E70EB8FB161304062C3DF0F793ACB96210BCE80563A0A49E::FE2847C2B3EB` (`cache/Standard.3mf`) matched newly created archive `302` by `content_hash` during the same grouped import run as `cache/Desiccant_Spool_Tumbler_-_Airflow_Remix.3mf`
- `70A983F366FED72AF997B0A540FA3925AD147F79F03DE6522A4815E987230DBD` (`cache/final toothbrush.3mf`) matched existing archive `147` by `content_hash`
- `9655586D79F50879A5A7DA1FF8629D6A792194B39C008C0A27542C42B474729D` (`cache/Fits A1_P1S_P2S_X1C 0.08mm layer, 2 walls, 100% infill.3mf`) matched existing archive `226` by `content_hash`
- `F767365DC8F034ED83C6418BE0C3E17C3C154BE0AD3A970DD0C6B42FF8BB6746` (`cache/gridfinity-baseplate (Desk drawer - no magnets)-250x220-446x338-5fa47_plate_1.3mf`) matched existing archive `15` by `content_hash`
- `1A3D1778A73356A7FE7AAB2477548BD09F1FCC48A289A94669ABDC5AA0A4967C` (`cache/gridfinity-baseplate (Desk drawer - no magnets)-250x220-446x338-5fa47_plate_2.3mf`) matched existing archive `14` by `content_hash`
- `52816CE2D2339622AB0E195E8764D827EB4746866632F8B92188E2995406F899` (`cache/Screw version 0.16mm layer, 2 walls, 15% infill.3mf`) matched existing archive `50` by `content_hash`
- `05F7CF9C8986D7AB41E20F0051CE3A7CF461C467020724ACB653D92F19128E54` (`cache/Printer Accessory Controller Box_Plate 1.3mf`) matched existing archive `13` by `content_hash`
- `63FD5A1BCD2E28E2B8BF4355E4E5ABFDAB55D01B0924D30702400AF695A02A02` (`cache/Printer Accessory Controller Box_plate_7.3mf`) matched existing archive `12` by `content_hash`
- `787C4FA28A78577C47DE76F40B7F82A8B44FB6CA61F2FDA244DF5F88AFFD2BA4` (`cache/Printable Frame (Optional).3mf`) matched existing archive `187` by `content_hash`
- `CA31D5976BB67AB3AEFC71FA47B33C638C592AD453ABE589C9FAF3A0A2D4898F` (`cache/Size 200x200 X1_P1_A1.3mf`) matched existing archive `183` by `content_hash`
- `F485F3F2628565961FEC938A0709F109CFA16517F835BD7981BC791CC9F5884D` (`cache/Parametric mount_Plate 1.3mf`) matched existing archive `7` by `content_hash`
- `C3075305B255BCCAAC267DDD3DD56C9BEB872BAD898BBA982ED74C24A0154B93` (`cache/My Parametric Project Box_plate_6.3mf`) matched existing archive `10` by `content_hash`
- `01FA70F261DD2060A6284CA78E1D5B9F3752ED03E3A7BF33B08CB52DE3ECC704` (`cache/Narrow - Strong Hook.3mf`) matched existing archive `53` by `content_hash`
- `214CF0B92C0833C3793F458584AC12FDE986452A37EBB8B1AFA82DF105315920` (`cache/My Parametric Project Box_plate_5.3mf`) matched existing archive `9` by `content_hash`
- `FBF724FF125F1C3AC839D950080D54B7A418684D06D41CD56CED8905C1878CB4` (`cache/My Parametric Project Box_Plate 1.3mf`) matched existing archive `11` by `content_hash`
- `20F27FDFAE8A74656FCC28F45B093DD1FEC63075EBBECD860F5174AC95BC947D` (`cache/Modular_Magnetic_Frame_System_for_Hueforge_Art.3mf`) matched existing archive `144` by `content_hash`
- `CC62299C244478E1A36CF9DCFD9B8C0C8113B447E5502E0E73693408DE52E886` (`cache/Stormtrooper Helmet Hueforge 200mm x 200mm.3mf`) matched existing archive `43` by `content_hash`
- `014F458549413655F7EFD446316CBA23B391AC107F0F74E560FED76DB7469E5B` (`cache/Modular Magnetic Frame System for Hueforge Art.3mf`) matched existing archive `169` by `content_hash`
- `9DC1C6863E0824E9B69E7124AF6808B0F5F44141324CD820E6E32A0FE071394A` (`cache/Magnetic Wall Mount for Hueforge.3mf`) matched existing archive `195` by `content_hash`
- `8E4A0602944A0366596137BF5E2DF921EDB65205633751BF2F4C6799C1355375` (`cache/TWO AMS - 200mm x 200mm Boba Fett 5-color Hueforge.3mf`) matched existing archive `21` by `content_hash`
- `40556AC96DF3F2EDE385C0A3A95C730A56C3C9B22AAF7D7E6E485AF4F10AE209` (`cache/Labels (Optional).3mf`) matched existing archive `188` by `content_hash`
- `ACE6EA5AB8C761082841604EAA123A1D1180E9A38518DA1538E84D69A9A8B9E6` (`cache/Laney Rivers 2026_Front_133x200.3mf`) matched existing archive `227` by `content_hash`
- `0CA648707E1DE734C18BF8C9D713CD161CAF86ADB337680C9B745304604630BB` (`cache/JJK-Shibuya_Front_106x142.stl.3mf`) matched existing archive `81` by `content_hash`
- `89A4612356233E6DC12CD45AA77FCD325E316993A1BC9E81F74D9EB674040BE7` (`cache/Ingenious Luulia (4).stl.3mf`) matched existing archive `5` by `content_hash`
- `C610BE07F18C51EEB32A2A684C0E58A7FC10D2B675F9EA8C1BE508F4A82CD8BC` (`cache/Ingenious Luulia (3).stl.3mf`) matched existing archive `4` by `content_hash`
- `B5350C4B475A8C181C4E257F8ECF019864F73310157B3285C3F758AD5B6EF1D3` (`cache/Yuji-Sukuna Jujutsu kaisen BM.3mf`) matched existing archive `82` by `content_hash`
- `FEC212637B4A24C1B4A4427B7DE7CF9FCDB2D9AAC5D522FD18ADBA836792201E` (`Deadpool___Wolverine_Deadpool.gcode.3mf`) matched existing archive `232` by `content_hash`
- `67F5F8C5EBEFEC8836CABC0898990161B7071CB9761FCED0071CA7BA59970A28` (`cache/gridfinity-baseplate (Desk drawer - no magnets)-250x220-446x338-5fa47_plate_3.3mf`) matched existing archive `16` by `content_hash`
- `F0E5C738DDECDD71D8F0329BBCB4A00B398188781820100723BF13FAE3161E3A` (`cache/Megumi_Shadow_Garden_Front_103x150.3mf`) matched existing archive `83` by `content_hash`
- `1CB8271709685EE82D10346E1DF4687E983596DC620F4D8D146C87D56344DAF8` (`cache/toothbrush holder.3mf`) matched existing archive `48` by `content_hash`
- `B4CF4E2F03A9E6B288A12E1B17FC2C6DC9F2C416ACA6B67251D23C05FABD8FDE` (`cache/Adaptive Layer Height - 0.08mm layer, 2 walls, 100% infill.3mf`) matched existing archive `199` by `content_hash`
- `1DD30ECF299CBE150733711A875AD0D7A28130FB2B2B67CA32C28BD27C225AF7` (`cache/Adaptive Layers .  100% Infill.3mf`) matched existing archive `228` by `content_hash`
- `1B8B123869C18FF118B3449F5868ED2F9E58008755BA2F051C5E04CDAA6DCF11` (`cache/AMS Filament Changes. 0.08mm layer, 1 walls, 100% infill..3mf`) matched existing archive `190` by `content_hash`
- `batch-001` and `batch-002` are exhausted, and the early `batch-003` small runs imported these additional candidates with sidecar runtime repair applied:
   - archive `264` <- `cache/240-2w-1h-case.stl.3mf`
   - archive `265` <- `cache/240-2w-1h-decor-drawer.stl.3mf`
   - archive `266` <- `cache/3 Color - 0.16mm layer, 2 walls, 15% infill.3mf`
   - archive `267` <- `cache/4 Micro Spatulas.3mf`
   - archive `268` <- `cache/4_Infill_Patterns_Reusable_Spool_-_Bambu_Lab_Refill_Compatible_-_Filament_Saver.3mf`
   - archive `269` <- `cache/60x200 - AMS Ready - Slice and Print - Wolverine & Deadpool.3mf`
   - archive `270` <- `cache/6x3 and dual 6x3 magnets.3mf`
   - archive `271` <- `cache/92x132mm_Stacking_Baskets_-_Eternity_Labs.3mf`
   - archive `272` <- `cache/_V2_ Filament Clips + Tool.3mf`
   - archive `273` <- `cache/All hands, 100%, recommended settings.3mf`
   - archive `274` <- `cache/AllPrinters-0.2mm layer, 2 walls, 15% infill.3mf`
   - archive `275` <- `cache/AMS Head.3mf`
   - archive `276` <- `cache/AMS Hygrometer LED Channel.3mf`
   - archive `277` <- `cache/ASA and PETG on Smooth Plate - Brims ON for ASA_.3mf`
   - archive `278` <- `cache/Assembled, 1 plate, 80mm high, 0.12mm layer, 8% infill.3mf`
   - archive `279` <- `cache/Bambu Spool.3mf`
   - archive `280` <- `cache/bambu-faceplate-1w-1h-accent-v12(grain variants)_Faceplate.3mf`
   - archive `281` <- `cache/bambu-faceplate-2w-1h-accent-v121 (grain variant 2)_plate_1.3mf`
   - archive `282` <- `cache/bambu-faceplate-2w-1h-accent-v121 (grain variant 2)_plate_2.3mf`
   - archive `283` <- `cache/bambu-faceplate-2w-1h-accent-v121 (grain variant 3)_plate_1.3mf`
   - archive `284` <- `cache/bambu-faceplate-2w-1h-accent-v121 (grain variant 3)_plate_2.3mf`
   - archive `285` <- `cache/BASE.stl.3mf`
   - archive `286` <- `cache/Basket Only V2 .3mf`
   - archive `287` <- `cache/Basket, Style 1 Lid and Style 2 Lid.3mf`
   - archive `288` <- `cache/Big printer - 0.16mm layer, 2 walls, 15% infill.3mf`
   - archive `289` <- `cache/Book Page Holder - 22 mm - 0.2mm layer, 2 walls, 15% infill.3mf`
   - archive `290` <- `cache/College Pennant - Georgia_Normal.3mf`
   - archive `291` <- `cache/Complete profile with sample card, holder and hanger.3mf`
   - archive `292` <- `cache/Connector, 0.2mm layer, 3 walls, 15% infill.3mf`
   - archive `293` <- `cache/Core - (Supports, Connectors, Lock-Pins, Pin-Bin).3mf`
   - archive `294` <- `cache/d2g-dq-lrs-100-long-box (extra holders).3mf`
   - archive `295` <- `cache/d2g-dq-lrs-100-long-box (extra holders)_plate_1.3mf`
   - archive `296` <- `cache/d2g-dq-lrs-100-long-lid.stl.3mf`
   - archive `297` <- `cache/Daring Curcan-Amur (1).stl + Daring Curcan-Amur.stl + Daring Curcan-Amur (1).stl.3mf`
   - archive `298` <- `cache/Daring Curcan-Amur (3).stl.3mf`
   - archive `299` <- `cache/Daring Curcan-Amur (5).3mf`
   - archive `300` <- `cache/Daring Curcan-Amur (6).stl + Daring Curcan-Amur (5).stl + Daring Curcan-Amur (5).stl + Daring Cur....3mf`
   - archive `301` <- `cache/Daring Curcan-Amur (6).stl.3mf`
   - archive `302` <- `cache/Desiccant_Spool_Tumbler_-_Airflow_Remix.3mf`
   - archive `303` <- `cache/Designers Profile (keep settings as is).3mf`
   - archive `304` <- `cache/drawer-stoppers.stl + drawer-stoppers.stl + drawer-stoppers.stl + drawer-stoppers.stl + drawer-st....3mf`
   - archive `305` <- `cache/Ellis Snowflake.3mf`
   - archive `306` <- `cache/Embedded_Magnet_Dispenser_Tool_for_3D_Prints.3mf`
   - archive `307` <- `cache/ESP32C3Mini-Bottom.3mf`
   - archive `308` <- `cache/faceplate with supports_Faceplate.3mf`
   - archive `309` <- `cache/Fantastic Bombul (2).stl.3mf`
   - archive `310` <- `cache/filament_swatch (larger - fits Phenmo Label).3mf`
   - archive `311` <- `cache/Football National Championship Trophy - Brick Accessory_Inner Part.3mf`
   - archive `312` <- `cache/Football National Championship Trophy - Brick Accessory_Outer Shell.3mf`
   - archive `313` <- `cache/Football National Championship Trophy - Brick Accessory_Trophy Base - Indiana 2025 Variant.3mf`
   - archive `314` <- `cache/For P1S, 0.2mm layer, 3 walls, 15% infill.3mf`
   - archive `315` <- `cache/Funnel - 0.16mm layer, 2 walls, 15% infill.3mf`
   - archive `316` <- `cache/gen2-quicklocks-v111.stl + gen2-quicklocks-v111.stl + gen2-quicklocks-v111.stl + gen2-quicklocks-....3mf`
   - archive `317` <- `cache/Generic Player and Jersey Options (0-9).3mf`
   - archive `318` <- `cache/GF Bins - Spool Parts (4H).3mf`
   - archive `319` <- `cache/GF Bins - Spool Parts (6H).3mf`
   - archive `320` <- `cache/gf-extended-bin-10x3x6-s1x1-444fa.stl.3mf`
   - archive `321` <- `cache/Golden Retriever.stl.3mf`
   - archive `322` <- `cache/grid 2x1 (with split) half size gf grid 6H.stl.3mf`
   - archive `323` <- `cache/Rivers Logo_plate_3.3mf`
   - archive `324` <- `cache/Rivers Logo_plate_6.3mf`
   - archive `325` <- `cache/Round_filament_box_for_spools.3mf`
   - archive `326` <- `cache/RallyChain_MichiganWolverines.3mf`
   - archive `327` <- `cache/Rivers Logo_4 Color.3mf`
   - archive `328` <- `cache/Sample Mosfet Stands.3mf`
   - archive `329` <- `cache/Rivers Logo 1 - Full Gray Layer.3mf`
   - archive `330` <- `cache/Silk Filament.3mf`
   - archive `331` <- `cache/PLA 0.2mm layer, 2 walls, 15% infill.3mf`
   - archive `332` <- `cache/Simple_Rugged_Large_Utility_Toolbox_With_Handle.3mf`
   - archive `333` <- `cache/Print by Object Print Profile 0.20 mm.3mf`
   - archive `334` <- `cache/PLA - ESP32 C3 Supermini - 4 Versions on Plates.3mf`
   - archive `336` <- `cache/PETG - 0.2mm layer, 3 walls, 10% infill.3mf`
   - archive `337` <- `cache/Parts Label - bambu-label-v12_Parts.3mf`
   - archive `338` <- `cache/Skull Bowl 0.12mm layer, 3 walls, 10% infill.3mf`
   - archive `339` <- `cache/Smart Controller Case ++_CUSTOM - Case.3mf`
   - archive `340` <- `cache/Parts Label - bambu-label-v12_Tools.3mf`
   - archive `341` <- `cache/Parts Label - bambu-label-v12_Electronics & PC Parts.3mf`
   - archive `342` <- `cache/Smart Controller Case ++_Custom - Lid.3mf`
   - archive `343` <- `cache/Painters Pyramid V2.3mf`
   - archive `344` <- `cache/P1x, X1x - 0.2mm layer, 2 walls, 15% infill.3mf`
   - archive `345` <- `cache/P2S, P1S_One Plate Print By Object_0.16mm layer_2 walls.3mf`
   - archive `346` <- `cache/Smart Controller Case ++_CUSTOM.3mf`
   - archive `347` <- `cache/openGrid Wall Mount, 0.2mm layer, 3 walls, 15% infill.3mf`
   - archive `348` <- `cache/Oversized_Rally_Chain_-_Michigan_Wolverines_M_Logo.3mf`
   - archive `349` <- `cache/openGrid under printer desk_Grid 8x8.3mf`
   - archive `350` <- `cache/Smart Controller Case ++_MagWLED Lid.3mf`
   - archive `351` <- `cache/openGrid 8x8_Plate 1.3mf`
   - archive `352` <- `cache/openGrid under printer desk_Grid - 9x5.3mf`
   - archive `353` <- `cache/Smart Controller Case ++_plate_6.3mf`
   - archive `354` <- `cache/Smart Controller Case ++_plate_7.3mf`
   - archive `355` <- `cache/openGrid 3x5_Plate 1.3mf`
   - archive `356` <- `cache/openGrid 5x9 stacked x2_Plate 1.3mf`
   - archive `357` <- `cache/Normal_Mahjong_Rack_with_Pusher.3mf`
   - archive `358` <- `cache/Smashing Snaget-Jaagub.stl.3mf`
   - archive `359` <- `cache/Snaps, 0.2mm layer, 2 walls, 15% infill.3mf`
   - archive `360` <- `cache/Split over more plates part count_plate below 64..3mf`
   - archive `361` <- `cache/Multicolor-Halfcut_0.2mm layer, 2 walls, 25% infill.3mf`
   - archive `362` <- `cache/Multicolor AMS, only 1 filament change.3mf`
   - archive `363` <- `cache/Modular_Spool_Stand,_Only_8_Grams_Each.3mf`
   - archive `364` <- `cache/Split Spiral, 0.2mm layer, 2 walls, 15% infill.3mf`
   - archive `365` <- `cache/Standard 0.2mm layer, 3 walls, 12% infill.3mf`
   - archive `366` <- `cache/MODULAR.3mf`
   - archive `367` <- `cache/Microfiber Holder.3mf`
   - archive `368` <- `cache/magnet-insert-10x2mm.stl + magnet-insert-10x2mm.stl + magnet-insert-10x2mm.stl + magnet-insert-10....3mf`
   - archive `369` <- `cache/Storage Trays for 6 Boxes each 70x70x25.3mf`
   - archive `370` <- `cache/top.stl + Assembly.3mf`
   - archive `372` <- `cache/LED Cover - AMS.stl + LED Cover - AMS.stl.3mf`
   - archive `373` <- `cache/LED Cover - AMS.3mf`
   - archive `374` <- `cache/LED Cover - AMS.stl.3mf`
   - archive `375` <- `cache/TPU, no Support, 0.2mm layer, 3 walls, 0% infill.3mf`
   - archive `376` <- `cache/LED Cover - AMS (Both Ends Open).3mf`
   - archive `377` <- `cache/Laser Printer Drawer - Gridfinity Base (470x285)_plate_6.3mf`
   - archive `378` <- `cache/Store & Dry Tray.3mf`
   - archive `379` <- `cache/Laser Printer Drawer - Gridfinity Base (470x285)_plate_4.3mf`
   - archive `380` <- `cache/Laser Printer Drawer - Gridfinity Base (470x285)_plate_3.3mf`
   - archive `381` <- `cache/University_of_Michigan_Chain_Necklace.3mf`
   - archive `382` <- `cache/Laser Printer Drawer - Gridfinity Base (470x285)_plate_5.3mf`
   - archive `383` <- `cache/Version 5 - All Sizes - 3 Plates Each, PETG.3mf`
   - archive `384` <- `cache/Inside_ledstrip_corner_guide.3mf`
   - archive `385` <- `cache/VerticalItemHolder_Plate 1.3mf`
   - archive `386` <- `cache/Ingenious Luulia (1).stl.3mf`
   - archive `387` <- `cache/Wallmount Frame for Deluxe 10_ Rack.3mf`
   - archive `388` <- `cache/Ingenious Luulia (2).stl.3mf`
   - archive `389` <- `cache/HomeRacker Shelf - 13W x 15D_Plate 1.3mf`
   - archive `390` <- `cache/Hygrometer - LED Case.stl.3mf`
   - archive `391` <- `cache/X-Wing_Kit_Card.3mf`
   - archive `392` <- `cache/HomeRacker - Shelf v21 - 13D x 11W_plate_7.3mf`
   - archive `393` <- `cache/HomeRacker - Shelf v21 - 13D x 11W_Shelf + Wall Anchor Slot.3mf`
   - archive `394` <- `cache/HomeRacker - Shelf v21 - 13D x 11W_plate_5.3mf`
   - archive `395` <- `cache/HomeRacker - Shelf v21 - 13D x 11W_plate_2.3mf`
   - archive `397` <- `cache/HomeRacker - Shelf v21 - 13D x 11W_Plate 1.3mf`
   - archive `398` <- `cache/HomeRacker - Shelf v21 - 11x15_plate_2.3mf`
   - archive `399` <- `cache/快速夹具（无须五金件）.3mf`
   - archive `400` <- `cache/gridplates-158x225-Standard-58de9.stl.3mf`
   - archive `401` <- `cache/Heisman Trophy - Brick Man_Trophy - single color no AMS.3mf`
   - archive `402` <- `cache/拆件版.3mf`
   - the final two `batch_ready` candidates both collapsed by exact `content_hash`, so the historical queue is exhausted without creating additional archives:
      - `B6BCB8C4AC5E4209762E5A0BBE750948A495CB95D26BD0790075D0ED975125FC` -> `cache/gridfinity-baseplate-250x220-446x338-5484a.stl_2.3mf` matched existing archive `8`
      - `AED394930768859ED4F96DE71D9C669F19D4C954F267706D4060599E2C219769` -> `cache/gridfinity-baseplate (Desk drawer - no magnets)-250x220-446x338-5fa47_plate_4.3mf` matched existing archive `17`
   - manifest summary is now `completed: 166`, `already_in_archive: 62`, `deferred: 2`, `manual_review: 1`
   - there are no remaining `batch_ready` historical SD-cache imports; follow-up work is limited to the existing deferred/manual-review anomalies

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
   -ManifestPath '.\bambuddy\backfill-state\archive_backfill_manifest_v2.json' `
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
   -ManifestPath '.\bambuddy\backfill-state\archive_backfill_manifest_v2.json' `
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

Legitimate reprint override:

- if the operator confirms the same archived file was printed multiple times, set that candidate's `allow_same_content_reimport` flag to `true` in the manifest
- with that flag set, inspect mode keeps the candidate in `batch_ready` and full mode imports a new archive even when another archive already has the same `content_hash`
- use this only for real repeated prints, not for accidental duplicate source files that point at the same historical event

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
python .\tools\bambuddy\generate_archive_backfill_manifest.py --source-root '.\bambuddy\Backup SD Card - 2026-04-03' --output '.\bambuddy\backfill-state\archive_backfill_manifest_v2.json'
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
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' -Mode Backfill -BaseUrl 'http://bambuddy.socko.us' -PrinterId 1 -ManifestPath '.\bambuddy\backfill-state\archive_backfill_manifest_v2.json' -BackfillAction Inspect
```

Upload only high-confidence non-duplicate candidates:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveRecovery.ps1' -Mode Backfill -BaseUrl 'http://bambuddy.socko.us' -PrinterId 1 -ManifestPath '.\bambuddy\backfill-state\archive_backfill_manifest_v2.json' -BackfillAction Full
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