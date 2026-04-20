# Timelapse Actions And Viewer

## Scope

This document covers the shipped print-history timelapse slice in Home Assistant:

- scan a Bambuddy archive for a printer-side timelapse from the popup `Advanced Actions` card
- upload or replace one attached timelapse manually from the same popup
- open a timelapse viewer popup from either the archive popup media header or the advanced-actions popup

This is intentionally narrower than the older roadmap idea of full `timelapse review` or `timelapse processing` workflows.

## Current UX

The current print-history popup exposes timelapse in two places.

### 1. Archive popup media header

If the archive detail has `timelapse_path`, the top-right media action cluster shows a timelapse button next to the 3D-view button.

That button opens a dedicated popup viewer backed by `custom:print-history-timelapse-card`.

### 2. Advanced Actions popup

The advanced-actions popup includes a `Timelapse` section.

When no timelapse is attached, it shows:

- `Scan Printer for Timelapse`
- `Upload Timelapse`

When a timelapse is already attached, it shows:

- `View Timelapse`
- `Replace Timelapse`

## Bambuddy Contract That Drives The UX

The current Bambuddy archive model stores a single `timelapse_path`, not a list.

That means:

- an archive can only have one attached timelapse at a time
- upload is a replace operation, not an additive multi-file operation
- scan stops early with `status = exists` if Bambuddy already sees an attached timelapse

This is why the HA copy says `Only one timelapse is tracked per archive.`

## Scan Behavior

The scan action uses Bambuddy `POST /api/v1/archives/{id}/timelapse/scan` through the Home Assistant `bambuddy/print_history_archive_action` websocket path.

Current behavior:

- the HA frontend does not call Bambuddy directly
- the integration performs the scan, then refreshes archive detail back into the local print-history store
- the popup uses the refreshed local-store snapshot, not an ad hoc frontend-only payload

### Progress And Status

Bambuddy does not stream scan progress.

The current UI therefore only shows a busy state with explanatory copy while the request is running. There is no true percent-complete progress bar.

### Single-Printer Fallback For Missing `printer_id`

Some Bambuddy archives exist under `archive/unassigned/...` and have `printer_id = null` even though the rest of the archive was captured successfully.

The timelapse scan path now handles that narrow case in Home Assistant:

- if the archive has no `printer_id`
- and Bambuddy currently exposes exactly one configured printer
- HA patches that sole `printer_id` back into the Bambuddy archive first
- then retries the timelapse scan

This fallback is intentionally limited to the single-printer case so HA does not guess incorrectly in multi-printer setups.

## Upload Behavior

Manual timelapse upload does not go over the HA websocket as base64.

Instead, the advanced-actions card uses an authenticated Home Assistant multipart upload proxy, matching the existing source-3MF upload pattern. That keeps larger video files off the websocket transport.

Current upload constraints:

- accepted extensions are `.mp4`, `.avi`, and `.mkv`
- the HA proxy enforces the configured restore-upload byte limit from the Bambuddy integration
- if the archive already has a timelapse, HA deletes the old Bambuddy timelapse first and then uploads the replacement
- after upload, HA refreshes archive detail and updates the local print-history store immediately

## Viewer Behavior

The timelapse viewer popup streams Bambuddy `GET /api/v1/archives/{id}/timelapse` into an HTML5 `<video>` element.

The viewer also exposes:

- a direct `Open in new tab` link
- a lightweight metadata summary
- a warning when the current file extension is not browser-friendly yet

### Non-MP4 Note

Bambuddy accepts `.avi` and `.mkv` uploads, but browser playback is best with MP4.

Bambuddy's archive service writes the uploaded file first and then background-converts non-MP4 timelapses to MP4 when possible. That means there can be a short window where an uploaded AVI or MKV exists but browser playback is still limited.

## Why This Is Not Full Timelapse Review Yet

The shipped slice intentionally stops before the larger deferred workflow.

Still not implemented in Home Assistant:

- manual candidate selection from Bambuddy `available_files` when scan returns `status = not_found`
- delete timelapse action in the popup
- timelapse `info`, `thumbnails`, or `process` UI
- a dedicated timelapse review queue or media-review table integration
- timeline-strip review and post-process presets

Those remain follow-on work and should not be conflated with the current scan/upload/viewer feature.