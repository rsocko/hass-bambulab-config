# Bambuddy Issue Draft: Fallback Archives Have No In-Place Repair Path

## Title

Fallback archives created after initial printer FTP failure cannot be repaired in place

## Version

- Bambuddy `v0.2.2.2`

## Summary

When Bambuddy cannot retrieve the print `.3mf` from the printer at print start, it creates a fallback archive with no `file_path`, no thumbnail, and no parsed metadata. That fallback behavior is understandable, but there is no later API path to repair that same archive in place even if the file becomes retrievable later.

## Observed Behavior

For the affected archive, the API returned a minimal fallback record with no archived file:

```json
{
  "id": 174,
  "file_path": "",
  "file_size": 0,
  "thumbnail_path": null,
  "print_time_seconds": null,
  "filament_used_grams": null,
  "layer_height": null,
  "total_layers": null,
  "object_count": null,
  "extra_data": {
    "no_3mf_available": true
  }
}
```

The UI then shows an incomplete history item with missing thumbnail and missing print metadata.

## Evidence

The print-start log window shows the exact failure path:

- Print start detected for `200mm x 200mm Deadpool & Wolverine Hueforge.3mf`
- Bambuddy tried multiple filename/path combinations over FTP
- Several attempts failed with `550`
- `/cache/... .3mf` attempts failed with `[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol`
- Final log lines:

```text
Could not find 3MF file for print: 200mm x 200mm Deadpool & Wolverine Hueforge.3mf
Created fallback archive 174 for 200mm x 200mm Deadpool & Wolverine Hueforge (no 3MF available)
```

## Why This Matters

This leaves the archive permanently incomplete even though the underlying problem can be transient:

- the printer file may appear later
- the FTP/TLS failure may have been temporary
- the file may still be retrievable after a short delay or at print completion

At the moment, the archive remains a dead-end fallback record.

## Current API Limitation

The current archive repair-related APIs do not solve this case:

- `POST /api/v1/archives/{id}/rescan` requires a valid archived `file_path`
- `POST /api/v1/archives/{id}/source` only attaches a source 3MF, it does not rebuild the main archive file/thumbnail/metadata
- `POST /api/v1/archives/upload` creates a new archive, not a repair of the existing fallback archive

## Expected Behavior

Fallback archives should have a supported recovery path.

At least one of these would solve the problem:

1. Retry retrieval automatically after a short backoff window
2. Retry again on `print_complete`
3. Add an API such as `POST /api/v1/archives/{id}/repair-from-printer`
4. Add an API that accepts a `.3mf` upload and rebuilds the existing archive in place instead of creating a new one

## Suggested Fix

### Minimum viable improvement

- Keep the fallback archive behavior
- Mark it explicitly as repairable
- Add a repair API that retries the same printer-side lookup logic used at print start

### Better behavior

- On initial FTP failure, keep the fallback archive in a `pending_repair` state
- Retry file retrieval on a schedule, for example after 15s, 45s, 2m, and 5m
- Retry once more on `print_complete`
- Record attempted filenames, attempted paths, and the last error in `extra_data`
- Surface a clear UI badge like `Fallback archive: 3MF not recovered`

## Additional Note

The fallback path is particularly painful because other downstream features depend on the archived `.3mf`, including thumbnails, metadata extraction, capability checks, and reprint behavior.
