# Archive Skip History Bridge

## Goal

Add skipped-object archive support in the Home Assistant layer without expanding Bambuddy Layer 1 payloads or depending on new upstream archive fields.

## Confirmed Inputs

- Real archived gcode.3mf packages are the primary regeneration source.
- Archived packages can contain pick images under `Metadata/pick_{plate}.png`.
- Archive records already persist the archived gcode.3mf path for every archive.
- `source_3mf_path` is optional and must not be treated as the primary path.

## Chosen Path

Use Path 1 only.

- Persist local skip-event and overlay metadata in the HASS print-history store.
- Rebuild skip overlays later from archived gcode.3mf pick images plus the stored metadata.
- Keep the upstream archive update path compact and summary-only.
- Defer any Bambuddy photo-upload fallback unless real regeneration gaps are discovered.

## Local Persistence

Store two levels of local data:

1. Event timeline rows for each skip action.
2. Archive-scoped overlay regeneration metadata.

The archive-scoped metadata should be sufficient to replay the most recent skip state without depending on live printer entities.

Recommended fields:

- `overlay_version`
- `plate_number`
- `pick_image_asset_path`
- `pick_image_source`
- `skipped_ids`
- `printable_objects`
- `object_color_map`
- `requested_skip_ids`
- `trigger_source`
- `captured_at`

The exact payload can evolve, but the contract should stay archive-local and regeneration-focused.

## Layering

- Layer 1: keep archive projection compact.
- Layer 2: local detail hydration and skip overlay metadata.
- Layer 3: popup rendering and overlay regeneration.

Do not push rendered overlay images or verbose per-event details into archive `notes`.

## Deferred Fallback

If regeneration later proves incomplete, use a local-only fallback mapping for Bambuddy photo uploads.

- Upload the fallback image as a normal Bambuddy photo.
- Persist a local role such as `pick_overlay` for the returned filename.
- Exclude that role from the standard photo carousel locally.

Do not rely on upstream Bambuddy photo metadata because the upstream photo list is flat and role-free.

## Initial Implementation Slice

The first implementation slice should:

1. Add local store persistence for archive skip overlay metadata.
2. Expose that metadata in archive detail responses.
3. Add the `objects_skipped` timeline label.
4. Cover the store and manager behavior with focused tests.

Automation capture, popup rendering, and archive-summary patching can follow after this persistence slice is stable.