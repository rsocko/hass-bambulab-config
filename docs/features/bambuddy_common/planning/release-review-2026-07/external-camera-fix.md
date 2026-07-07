# External Camera Fix — Impact Analysis

## Feature Summary

Bambuddy v0.2.5b2 fixes a bug where cameras configured in HTTP-snapshot mode that served non-JPEG images (PNG, WebP, BMP) would cause browser errors and break plate detection and photo finishing. Bambuddy now auto-transcodes non-JPEG snapshots to JPEG via OpenCV.

## Our Camera Architecture

We do **NOT** use Bambuddy's camera system for image capture. Our architecture is:

```
HA Camera Entity (camera.ntk_ryansoffice_3dprinter_camera)
       ↓
HA camera.snapshot service → /config/www/printer_snapshots/*.jpg
       ↓
shell_command.bambuddy_upload_archive_photo (curl multipart POST)
       ↓
Bambuddy Archive (receives JPEG)
```

Key facts:
- We capture via HA's `camera.snapshot` action — this always produces JPEG
- We upload the JPEG file to Bambuddy via `curl` multipart form
- We do NOT point Bambuddy at a camera URL for it to pull from
- We do NOT rely on Bambuddy's camera streaming or snapshot-pull features

## Impact Assessment

**Impact: NONE for our current setup.**

This fix is relevant for users who:
1. Configure a camera URL *within Bambuddy's settings* (not HA)
2. Have that camera URL return non-JPEG content
3. Rely on Bambuddy's internal plate-detection or photo-finishing from that camera

Since we handle all camera work in HA and push pre-captured JPEG files, this bug and fix are completely transparent to us.

## Edge Cases to Consider

### If We Ever Add Bambuddy-Side Camera Config

If in the future we configure Bambuddy to pull directly from an HA camera's snapshot URL (e.g., `http://homeassistant.local:8123/api/camera_proxy/camera.xxx`), then:
- HA camera proxy serves JPEG by default ✓
- No issue expected even without this fix

### If We Add Non-JPEG Camera Sources to HA

If we add a camera to `input_text.bambuddy_capture_camera_entities` that produces PNG output:
- HA's `camera.snapshot` converts to JPEG at capture time ✓
- Our upload sends `.jpg` files ✓
- No issue

## Recommendation

**No action needed.** This fix is a "nice to have" safety net but doesn't affect our workflow. Document this finding and move on.

## Files Reviewed

- `homeassistant/packages/3d_printing/print_history/scripts/capture_and_upload_snapshot.yaml`
- `homeassistant/packages/3d_printing/print_history/shell_commands/bambuddy_upload_archive_photo.yaml`
- `homeassistant/packages/3d_printing/bambuddy_integration/automations/bambuddy_upload_snapshot.yaml`
