# Bambuddy Archive Enrichment Audit - 2026-04-12

## Scope

This audit reviews the full Bambuddy export in `bambuddy/sampleArchive-2026-04-12.json` and focuses only on archives whose enrichment is incomplete, unavailable, or missing.

Definitions used in this document:

- `complete`: hidden `+>` payload exists and reports `s:"c"`
- `partial`: hidden `+>` payload exists and reports `s:"p"`
- `unavailable`: hidden `+>` payload exists and reports `s:"u"`
- `missing`: archive has no hidden `+>` payload at all

The current review found 15 affected archives:

- 6 partial
- 2 unavailable
- 7 missing

## Root Cause Categories

### Category A - Archived AMS Tray Ambiguity

Pattern:

- payload source is `afs`
- at least one row has ambiguity code `a_tc`
- row keeps a filament ID but cannot safely resolve a tray or spool ID

Current meaning:

- the archive contains enough type and color information to identify a filament family
- multiple archived AMS tray candidates share the same normalized type and color
- manual re-enrich correctly refuses to guess which tray UUID or spool record was actually used

Recommended workflow changes:

- preserve stronger print-time provenance before the print ends
- consume print-start snapshot provenance during terminal reconciliation when the live tray map has drifted
- keep `a_tc` conservative in manual re-enrich until stronger evidence exists
- add a later provenance tier based on archived AMS UUIDs first and only then optional time-window spool history

### Category B - Archive-Derived Recovery Without Enough Provenance

Pattern:

- payload source is `afs`
- rows are missing tray, spool, and sometimes filament IDs
- status is `u`

Current meaning:

- re-enrich ran, but the archive did not provide enough evidence to prove spool lineage
- this shows up in historical-import or recovery-heavy cases where archived slot rows are present but tray linkage is not defensible
- manual re-enrich now has a strict time-window fallback using Spoolman `first_used` and `last_used`, but only when that evidence narrows the remaining candidate set to one spool

Recommended workflow changes:

- keep payloads explicitly unavailable rather than writing guessed spool lineage
- add a date-based spool-history fallback only after UUID, snapshot, and exact archive metadata paths are exhausted
- store a row-level reason when temporal matching is used so operator review can distinguish inferred lineage from exact lineage
- preserve the temporal result as inferred provenance rather than treating it as equivalent to UUID-backed lineage

### Category C - Missing Hidden Enrichment Payload

Pattern:

- archive has no `+>` payload at all

Current meaning:

- either the archive pre-dates the current enrichment flow, the automatic workflow never wrote a payload, or a failure/recovery path completed without re-enriching the archive afterward

Recommended workflow changes:

- improve automatic terminal reconciliation so print-start spool provenance survives live tray-map changes
- add a targeted backfill path for archives with missing payloads
- ensure repair and recovery workflows can explicitly request re-enrich when the archive becomes canonical

## Per-Archive Findings

| Archive ID | Print Name                               | Archive Status | Enrichment Status | Category | Why It Is Incomplete                                                                                         | Recommended Action                                                                                                        |
| ---------- | ---------------------------------------- | -------------- | ----------------- | -------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| 190        | Spiderman Hueforge (Black & White)       | completed      | unavailable       | B        | Archive-derived rows exist, but at least one row cannot prove tray, spool, or filament lineage.              | Keep unavailable for now; revisit with archived UUID plus temporal history fallback.                                      |
| 202        | Hueforge Artemis Nasa                    | completed      | partial           | A        | One white row is marked `a_tc`, so filament can be inferred but tray/spool cannot be safely chosen.          | Do not force a spool guess; improve future provenance capture and re-enrich only if stronger evidence becomes available.  |
| 203        | Bambu Tools - Bambu Lab Tool Set LABELED | completed      | partial           | A        | White row is ambiguous across duplicate archived AMS tray candidates.                                        | Preserve partial state; future recovery should prefer archived UUID or print-start snapshot before any temporal fallback. |
| 205        | Game of Thrones Poster - Hueforge Art    | completed      | partial           | A        | White row is ambiguous, so spool/tray lineage is intentionally withheld.                                     | Preserve partial state until stronger provenance exists.                                                                  |
| 206        | Batman B&W Hueforge                      | failed         | missing           | C        | Failed archive has no hidden enrichment payload.                                                             | Low priority unless this failure row needs forensic lineage.                                                              |
| 207        | Batman B&W Hueforge                      | failed         | missing           | C        | Failed archive has no hidden enrichment payload.                                                             | Low priority unless this failure row needs forensic lineage.                                                              |
| 208        | Batman B&W Hueforge                      | completed      | missing           | C        | Completed fallback-style row has no hidden enrichment payload even though related repaired duplicates exist. | Re-enrich after missing-payload backfill workflow is added.                                                               |
| 213        | Filament Swatch System - Plate 18        | failed         | partial           | A        | Black row is ambiguous and therefore has no safe spool/tray attribution.                                     | Keep partial; do not overwrite with guessed lineage.                                                                      |
| 222        | Spiderman Hueforge                       | archived       | unavailable       | B        | Historical import row lacks enough provenance to map some colors to tray or spool lineage.                   | Add historical-import review path with optional temporal matching and explicit confidence markers.                        |
| 229        | Batman Hueforge                          | completed      | partial           | A        | White row remains ambiguous after archive-derived recovery.                                                  | Preserve partial state; use as a validation fixture for future recovery improvements.                                     |
| 230        | Batman Hueforge                          | failed         | partial           | A        | Same ambiguous white row persists on related duplicate/failure lineage.                                      | Preserve partial state; do not guess spool lineage across duplicate family.                                               |
| 231        | Batman Hueforge                          | failed         | partial           | A        | Same ambiguous white row persists on canonical duplicate family member.                                      | Preserve partial state; use as a test fixture for ambiguity-safe re-enrich.                                               |

## Workflow Review

### Automated Enrichment

Current automated enrichment is defined in `homeassistant/packages/3d_printing/print_history/automations/bambuddy_capture_archive_id.yaml` and `homeassistant/packages/3d_printing/print_history/automations/bambuddy_enrich_archive_on_complete.yaml`.

Observed gaps before this implementation pass:

- print start stored only `tray_name:spool_id`
- terminal reconciliation relied on the live tray map and did not consume the stored snapshot
- if the live tray map changed before completion, the archive could lose spool, filament, or color fidelity even when print-start provenance existed

Implementation started in this pass:

- the print-start snapshot is being expanded to keep compact `tray_name:spool_id:filament_id:color` entries
- terminal enrichment is being updated to use that snapshot as a fallback when live tray-map data is missing or lower fidelity

This does not solve archived `a_tc` ambiguity for older rows, but it reduces future automatic misses caused by tray-map drift.

### Manual Re-Enrich

Current manual re-enrich is defined in `homeassistant/packages/3d_printing/print_history/scripts/reenrich_print_history_archive.yaml`.

Important current behavior:

- it already refuses to guess through duplicate archived `type + color` tray matches
- it emits `a_tc`, `a_fb`, `s_uuid`, and `s_tc` rather than writing guessed spool IDs
- it can infer filament ID without spool ID when only the filament family is uniquely defensible

Needed next steps:

- archived AMS UUID matching should remain the first recovery path
- print-time snapshot provenance should become a second recovery path for newer archives that captured it
- time-window spool history matching should only run after those stronger sources fail, and it must preserve explicit confidence and reason metadata

### Repair and Recovery Handoff

Recovered and duplicate-family archives show that canonical repair is not the same as canonical enrichment. Recovery workflows should be able to request re-enrich explicitly after restore or replacement so repaired archives do not remain in a missing or partial state by default.

## Recommended Implementation Order

1. Strengthen automatic print-start snapshot capture and terminal fallback usage.
2. Add tests that prove snapshot fallback can restore spool, filament, and color lineage without relying on the live tray map.
3. Add a missing-payload review/backfill path for older completed archives.
4. Extend manual re-enrich to consult archived AMS UUIDs, then deterministic location hints, then optional time-window spool history.
5. Keep ambiguous rows partial unless one of those stronger provenance paths reduces the candidate set to one defensible match.

## Backfill Batches

The new `script.backfill_print_history_archive_enrichment` service is intended to run targeted batches after workflow changes land.

Suggested first batches from this audit:

- Missing payloads: `185,187,204,206,207,208`
- Partial payloads: `202,203,205,213,229,230,231`
- Unavailable payloads: `190,222`

Example service data:

```yaml
service: script.backfill_print_history_archive_enrichment
data:
	archive_ids_csv: "185,187,204,206,207,208"
```

## Test Fixtures To Preserve

Use these archives as durable fixtures when expanding coverage:

- `202`, `203`, `205`, `213`, `229`, `230`, `231` for `a_tc` ambiguity
- `190`, `222` for unavailable archive-derived recovery
- `185`, `187`, `204`, `206`, `207`, `208` for missing hidden payload coverage

## Notes

This audit intentionally keeps Layer 1 lean. The recommended fixes improve provenance capture and recovery decisions without moving display-only labels or popup wording into the archive ingest layer.