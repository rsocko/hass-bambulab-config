# Print History Slicer UX Mockups

> **Status**: UX planning reference with low-fi mockups
> **Last updated**: 2026-05-09
> **Scope**: Operator-facing Model Catalog and Print History slicing wizard for source `.3mf` validation, filament substitution, and canonical archive creation.

See also:

- [Print History Slicer Plan](../planning/print-history-slicer-plan.md)
- [Print History Slicer Implementation Plan](/docs/features/model_catalog/planning/print-history-slicer-plan.md)
- [Historical Print Backfill Via Model Catalog](/docs/features/model_catalog/design/print-history-backfill.md)
- [UX Concepts And Mockups](/docs/features/model_catalog/design/ux-concepts.md)

## Purpose

Show how the slicing workflow should look when exposed through Model Catalog and Print History entrypoints.

The UI should feel like a guided review flow, not a general-purpose slicer replacement.

## UX Principles

- keep the user anchored to the model, source artifact, and intended archive outcome
- surface validation issues before any expensive slice job starts
- make filament substitution the only prominent override path in the first slice
- preserve a clear distinction between `Create Archive` and `Attach Source Only`
- expose local worker availability explicitly so the UI does not promise background slicing where none exists
- require explicit review of the historical print date/time before the archive commit is finalized

## Surface 1: Model Detail Entry Point

Primary purpose:

- let an operator launch archive creation from a known model or source `.3mf`

Must show:

- primary source file
- source classification summary
- archive/backfill context
- clear action split between canonical archive creation and source-only attachment

### Low-Fi Visual

```text
+------------------------------------------------------------------------------+
� Model Detail: Gridfinity Bit Holder v3                                      �
+------------------------------------------------------------------------------�
� Source file: holder_v3_source.3mf       Type: source project 3MF            �
� Linked archives: 2                     Last printed: 2025-09-18             �
�                                                                              �
� Recovery Actions                                                             �
� +--------------------------------------------------------------------------+ �
� � Create Historical Archive                                                � �
� � Validate source, choose plate, review filament mappings, and slice on   � �
� � the server before uploading to Bambuddy.                                 � �
� �                                                                          � �
� � [Create Archive From Source 3MF]                                         � �
� +--------------------------------------------------------------------------+ �
�                                                                              �
� +--------------------------------------------------------------------------+ �
� � Attach Source Only                                                       � �
� � Keep this file as provenance for an existing archive without creating a � �
� � new canonical print-history record.                                      � �
� �                                                                          � �
� � [Attach To Existing Archive]                                             � �
� +--------------------------------------------------------------------------+ �
+------------------------------------------------------------------------------+
```

## Surface 2: Validation Review Step

Primary purpose:

- stop the operator before slice execution if the local worker cannot reliably use the file as-is

Must show:

- local worker availability
- detected printer, process, and filament metadata
- warnings grouped by severity
- allowed fixes only

### Low-Fi Visual

```text
+------------------------------------------------------------------------------+
� Create Archive From Source 3MF                                               �
+------------------------------------------------------------------------------�
� Worker: Local Model Catalog Slicer  Status: Reachable                        �
� Source: holder_v3_source.3mf      Plates discovered: 3                       �
�                                                                              �
� Validation Summary                                                           �
� [warning] Printer profile mismatch                                           �
�   Source says: X1 Carbon 0.4                                                 �
�   Worker default: X1 Carbon 0.6                                              �
�   Action: [Select Printer Profile v]                                         �
�                                                                              �
� [warning] Plate 2 filament slot 2 is missing                                 �
�   Expected material: PLA                                                     �
�   Filament Catalog matches: 3                                                �
�   Action: [Choose Filament v]                                                �
�                                                                              �
� [info] Process preset found                                                  �
�   0.20mm Strength                                                            �
�                                                                              �
� Historical Print Timing                                                      �
� Started:  [2025-09-18 19:42]   Completed: [2025-09-18 22:08]                �
� Source: filesystem mtime + operator correction                               �
� [ ] Mark as approximate                                                      �
�                                                                              �
� Plate                                                                        �
� [Plate 1 v]  Plate 1 cover render shown here                                 �
�                                                                              �
� [Cancel] [Save Draft] [Continue To Slice]                                    �
+------------------------------------------------------------------------------+
```

## Surface 3: Filament Substitution Picker

Primary purpose:

- let the operator make a deterministic substitution using known Filament Catalog entries

Must show:

- expected material and color hints
- ranked candidate matches
- why each candidate was suggested
- no free-form custom editor in the first slice

### Low-Fi Visual

```text
+---------------------------------------------------------------------+
� Choose Filament For Plate 2 Slot 2                                 �
+---------------------------------------------------------------------�
� Needed by source file                                               �
� Material: PLA                                                       �
� Color hint: Red / #C12E1F                                           �
�                                                                     �
� Suggested matches                                                   �
� +---------------------------------------------------------------+   �
� � [#C12E1F] Bambu PLA Basic Red                                �   �
� � Match: exact material + hex + profile name                   �   �
� � Spools available: 2                                           �   �
� � [Select]                                                      �   �
� +---------------------------------------------------------------+   �
�                                                                     �
� +---------------------------------------------------------------+   �
� � [#B92A24] Sunlu PLA+ Red                                      �   �
� � Match: material + nearby primary color                        �   �
� � Spools available: 1                                           �   �
� � [Select]                                                      �   �
� +---------------------------------------------------------------+   �
�                                                                     �
� [Cancel]                                                            �
+---------------------------------------------------------------------+
```

## Surface 4: Slice Job Progress

Primary purpose:

- let the operator monitor a background worker job without exposing raw slicer internals

Must show:

- selected plate and applied overrides
- worker status
- returned warnings or failure details
- clear next action on success

### Low-Fi Visual

```text
+------------------------------------------------------------------------------+
� Slice Job In Progress                                                        �
+------------------------------------------------------------------------------�
� Source: holder_v3_source.3mf      Plate: 1                                   �
� Printer: X1C 0.4                 Process: 0.20mm Strength                    �
� Filament substitutions: 1                                                    �
� Worker: Local Model Catalog Slicer                                           �
�                                                                              �
� Status                                                                       �
� [##########------] Slicing plate 1                                           �
�                                                                              �
� Job events                                                                   �
� - Source uploaded to worker                                                  �
� - Historical print timing saved                                              �
� - Validation overrides applied                                               �
� - Slice started                                                              �
�                                                                              �
� On success, this flow will upload the resulting .gcode.3mf to Bambuddy and  �
� offer optional source attachment.                                            �
�                                                                              �
� [Dismiss] [View Details]                                                     �
+------------------------------------------------------------------------------+
```

## Surface 5: Completion Summary

Primary purpose:

- confirm whether a canonical archive was created and what follow-up happened

Must show:

- new archive id
- source attachment outcome
- archive-link outcome back into Model Catalog
- retry option when commit failed after slice success

### Success Variant

```text
+------------------------------------------------------------------------------+
� Archive Created                                                              �
+------------------------------------------------------------------------------�
� New Bambuddy archive: #1842                                                  �
� Historical print completed at: 2025-09-18 22:08                             �
� Model link: accepted                                                         �
� Source 3MF attached: yes                                                     �
� Plate used: 1                                                                �
� Filament substitutions: 1                                                    �
�                                                                              �
� [Open Archive] [Open Linked Model] [Create Another]                          �
+------------------------------------------------------------------------------+
```

### Partial-Failure Variant

```text
+------------------------------------------------------------------------------+
� Slice Succeeded, Archive Commit Failed                                       �
+------------------------------------------------------------------------------�
� Worker output exists and can be retried.                                     �
� Failure: Bambuddy upload returned HTTP 502                                   �
�                                                                              �
� Safe actions                                                                 �
� [Retry Archive Commit] [Download Output] [Discard Draft]                     �
+------------------------------------------------------------------------------+
```

## Surface 6: Worker Unavailable State

Primary purpose:

- explain why the workflow cannot complete automatically

### Low-Fi Visual

```text
+------------------------------------------------------------------------------+
� Create Archive From Source 3MF                                               �
+------------------------------------------------------------------------------�
� Worker status: Unavailable                                                   �
�                                                                              �
� Automatic server-side slicing is not configured for this environment.        �
�                                                                              �
� Available fallbacks                                                          �
� - Open the source in your local slicer                                       �
� - Produce a sliced .gcode.3mf manually                                       �
� - Return here or use the existing archive upload workflow                    �
�                                                                              �
� [Open In Slicer] [Download Source] [Close]                                   �
+------------------------------------------------------------------------------+
```

## Decision Notes

- The first slice should not show an editable filament form.
- Filament substitution should be framed as a repair for known validation gaps, not a creative customization tool.
- `Attach Source Only` should stay visible as a separate action whenever the source file is useful but canonical archive creation is not yet justified.
- Plate preview imagery should come from the planned `.3mf` analysis cache when available, otherwise from local worker discovery payloads.
- The historical print date/time should be editable in the reviewed flow and should not be buried as a post-success metadata fixup.

## Recommended Implementation Order

1. Entry point and worker-availability state
2. Validation summary with printer, process, and filament warnings
3. Deterministic filament picker backed by Filament Catalog candidates
4. Historical print timestamp review and draft-save behavior
5. Slice job progress and completion states
6. Backfill-specific shortcuts from model detail and working-group surfaces
