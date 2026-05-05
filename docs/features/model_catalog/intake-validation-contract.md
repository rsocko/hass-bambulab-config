# Intake Validation Contract

This document defines the concrete behavior of the Intake wizard Validate step and the shared queue validation endpoint.

## Scope

The Validate step uses `POST /api/intake/items/{item_id}/validate`.

That endpoint is shared by:

- the guided wizard Validate step
- the Active Queue review actions

Because both surfaces call the same endpoint, validation behavior is not specific to browser upload v2. A transport change can surface the route more often, but the validation rules live in the shared backend handler.

## Current Checks

The shipped validation step currently performs these checks in order:

1. Selected sources are present and readable.
2. Resolved files use supported model or image types.
3. Resolved file hashes do not match existing Working items.
4. The resolved plan contains at least one file to commit.

These checks operate on the resolved file list produced from the queued source entries. The endpoint does not just validate raw selections; it validates the exact prepared upload snapshot that Commit will reuse.

## Warning Codes

The backend currently emits these warning codes from validation:

| Warning code | Meaning |
| --- | --- |
| `missing_source` | A selected file no longer exists at validation time. |
| `source_unreadable` | A file exists but could not be read or hashed. |
| `unsupported_type` | A selected file resolved to an unsupported extension. |
| `working_group_hash_match` | A resolved file hash already exists in Working inventory. |
| `needs_manual_grouping` | Validation resolved zero files, so Commit cannot proceed. |

## Validation State Mapping

The endpoint summarizes the result into `validation.validation_state`.

| Validation state | Meaning |
| --- | --- |
| `ready` | All current checks passed. |
| `missing_source` | At least one selected source is missing or unreadable. |
| `unsupported_type` | Only unsupported files resolved, so nothing valid remains. |
| `source_warning` | Source expansion produced warnings that require operator attention. |
| `duplicate_candidate` | One or more resolved files match existing Working hashes. |
| `needs_manual_grouping` | No files resolved from the selected source entries. |

Queue state mapping:

- `ready` -> `validated_ready`
- any other validation state -> `validated_warning`

## API Payload Shape

The Validate endpoint returns a `validation` object with:

- `validation_state`
- `warnings`
- `file_hash_count`
- `checks`

`checks` is an ordered checklist for the UI:

```json
[
  {
    "key": "source_access",
    "label": "Selected sources are present and readable",
    "passed": true,
    "detail": "Resolved 4 file(s) for validation."
  }
]
```

The current checklist keys are:

- `source_access`
- `supported_types`
- `duplicate_scan`
- `commit_ready`
- `excluded_items_summary` (NEW — Issue #1324)

## New Validation Check: Exclusion Summary (Issue #1324)

**Key**: `excluded_items_summary`

**When added**:
- Always present in validation response
- After Source step (items may have been excluded/removed)

**Behavior**:
- **Always passes**: This check is informational only, not blocking
- Shows count of excluded items
- Allows user to proceed to Commit with exclusions in place

**Response format**:
```json
{
  "key": "excluded_items_summary",
  "label": "Exclusion summary",
  "passed": true,
  "detail": "3 files and 1 subfolder excluded from selected sources. Proceeding with 12 remaining items for import."
}
```

**Edge cases**:
- If `excluded_items[]` is empty: Check still present but detail reads "No items excluded"
- If `excluded_items[]` has N items: Count shown in detail message
- Multiple source entries: Aggregate count from all entries

**Rationale**:
- Users need visibility into what will be excluded before final commit
- Informational check does not block workflow (user decision already made in Source step)
- Warning-level prominence in UI (shown as check item, not as blocking error)

## UI Contract

The wizard Validate step should display:

- prepared upload id
- validation state
- ordered checklist with disabled checkboxes that reflect `checks[].passed`
- warning summary text when warnings exist
- **NEW**: exclusion summary check with count (if any items were excluded)

The checklist is meant to show what already passed and what still needs attention before Commit. The exclusion summary is an informational item showing what was excluded during Source step. It should not invent additional client-only validation rules that diverge from the backend response.

## Future Extension Boundary

The design docs still reserve room for later checks such as overlapping server selections, destination-specific conflicts, and richer collision analysis. Those should be added by extending the shared backend contract first, then surfacing them in the wizard checklist.