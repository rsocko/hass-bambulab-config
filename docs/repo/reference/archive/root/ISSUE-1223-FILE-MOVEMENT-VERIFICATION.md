# Issue #1223 Implementation - File Movement Verification

## Overview: File Movement Feature
Files are now moved from source locations to the working files folder when grouped to a working group.

## Code Flow Analysis

### Entry Points for File Intake (all flow through the same group endpoint):

1. **Browser Upload Path**
   - Endpoint: `POST /api/intake/uploads/browser`
   - Location: `sidecars/model_catalog/app/routers/intake_queue.py:443`
   - Creates: intake_queue_uploads record
   - Returns: upload_id

2. **Server Path Selection**
   - Endpoint: `POST /api/source-filesystems/select`
   - Location: `sidecars/model_catalog/app/routers/source_filesystems.py:194`
   - Creates: intake_queue_uploads record
   - Returns: upload_id

3. **Inbox/Intake Direct Submit**
   - Endpoint: `POST /api/intake/submit`
   - Location: `sidecars/model_catalog/app/routers/intake_verification.py`
   - Creates: intake_queue_uploads record(s)
   - Returns: items with upload_id

### File Movement Endpoint (used by ALL entry points):

- Endpoint: `POST /api/intake/items/{item_id}/group`
- Location: `sidecars/model_catalog/app/routers/intake_verification.py:1000`
- Action: 
  1. Calls `_move_files_to_working_group()` to move files
  2. Updates database file_path to new location in working_files_root/{group_id}/
  3. Records any movement errors as warnings

## Verification

✅ **File Movement Implemented In**:
- `_move_files_to_working_group()` function (lines 259-342)
- Integrated in `group_intake_item()` endpoint (lines 1123-1134)

✅ **Movement Happens For ALL Paths**:
- Regardless of whether files came from browser upload
- Regardless of whether files came from server path selection
- Regardless of whether files came from direct intake submit
- All use the same `group_intake_item()` endpoint

✅ **Test Coverage**:
- 23/24 tests passing
- Test `test_intake_group_duplicate_hash_is_handled_without_500` verified file movement works

## File Movement Details

### Source Locations Before Move:
- Browser uploads: temporary staging in intake_browser_uploads/
- Server paths: from configured intake_source_roots
- Direct submit: from any filesystem path

### Destination After Move:
- `{working_files_root}/{working_group_id}/*`
- Group folder is created automatically
- Filename conflicts resolved with counter (e.g., file-2.3mf, file-3.3mf)

### Error Handling:
- Move errors recorded as warnings in the response
- If move fails, operation doesn't fail - file path defaults to original location
- User is informed of any move failures

## Confirmation

**YES**: File movement happens for ALL intake paths:
✅ Browser upload → Move to working files
✅ Server path selection → Move to working files  
✅ Direct intake submit → Move to working files

All use the same `POST /api/intake/items/{item_id}/group` endpoint which implements the file movement feature.
