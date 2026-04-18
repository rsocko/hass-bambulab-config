# Bambuddy Issue Draft: Manual Re-Enrich Must Not Guess Through Duplicate Type+Color Matches

## Title

Manual archive re-enrichment should surface ambiguity instead of guessing when multiple archived tray candidates share the same type and color

## Summary

Home Assistant-side manual re-enrichment can reconstruct filament usage from Bambuddy archive data by combining:

- `extra_data.filament_slots[]`
- `extra_data._print_data.raw_data.ams[].tray[]`

That works only if archive contribution rows can be mapped back to a unique archived tray candidate. When two or more archived tray rows share the same normalized `type + color`, the system cannot safely infer which physical filament was actually used for that contribution row.

The resolver must treat that condition as ambiguous and report it to the operator instead of auto-selecting a spool.

## Why This Matters

Archive re-enrichment is operating after the print is over. At that point:

- the live tray map may no longer reflect the print-time tray contents
- the original spool may have been moved, consumed, archived, or replaced
- `filament_slots[].slot_id` is not an AMS tray number and cannot be used as a direct identity key

If the resolver guesses through duplicate `type + color` matches, it can write the wrong `s:<id>` tag and the wrong spool lineage into the archive.

## Relevant Archive Data Shape

Contribution rows come from `filament_slots[]`:

```json
{
  "slot_id": 1,
  "used_g": 61.5,
  "type": "PLA",
  "color": "#000000"
}
```

Print-time tray identity comes from archived `ams[].tray[]` rows:

```json
{
  "id": "1",
  "tray_type": "PLA",
  "tray_color": "000000FF",
  "tray_uuid": "1CF7FCD88593469C9BA35ECA4282CB0D"
}
```

Important constraint:

- `slot_id` is not the AMS tray index
- matching must be driven by normalized `type + color`, then by archived `tray_uuid` when a unique tray row exists

## Problem Case

Given one contributing archive row:

```json
{
  "slot_id": 1,
  "used_g": 61.5,
  "type": "PLA",
  "color": "#000000"
}
```

and two archived tray candidates:

```json
[
  {
    "id": "1",
    "tray_type": "PLA",
    "tray_color": "000000FF",
    "tray_uuid": "UUID_A"
  },
  {
    "id": "3",
    "tray_type": "PLA",
    "tray_color": "000000FF",
    "tray_uuid": "UUID_B"
  }
]
```

the system cannot prove whether the contribution came from `UUID_A` or `UUID_B`.

## Expected Behavior

When duplicate normalized `type + color` candidates exist for a single contributing archive row, manual re-enrichment should:

1. refuse to auto-select a spool candidate
2. refuse to emit a guessed `s:<id>` tag
3. emit `f:<id>` only if filament identity is still uniquely defensible
4. mark the result as ambiguous or partial rather than complete
5. surface a clear operator-facing message describing why the row could not be safely auto-resolved

## Acceptance Criteria

- The resolver reads `filament_slots[]` rows with `used_g > 0`.
- The resolver never interprets `slot_id` as an AMS tray number.
- Archive-slot color and archived-tray color are normalized before comparison.
- Archive-row to archived-tray matching requires exact normalized `type + color`.
- A single archived tray match allows UUID-based spool resolution.
- Multiple archived tray matches for the same `type + color` are treated as ambiguity, not as success.
- The resolver does not write guessed spool tags in ambiguous cases.
- The popup reports the ambiguity to the user.

## Suggested UX Copy

Example operator-facing message:

```text
Re-enrich could not safely resolve one filament row: multiple archived AMS trays matched PLA / #000000. No spool ID was written for that row.
```

## Design Reference

Canonical design reference:

- `docs/features/print_history/planning/archive-enrichment.md`