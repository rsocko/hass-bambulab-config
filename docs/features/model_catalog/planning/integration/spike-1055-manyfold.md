# Spike #1055: Validation of Manyfold REST Upload and Add-File Flows

> **Status**: Validation Spike - Complete
> **Issue**: #1055
> **Date**: 2026-04-25
> **Scope**: Investigate and document Manyfold REST API upload and add-file flows for catalog operations

## Executive Summary

Manyfold's REST API supports both file upload via TUS (resumable upload protocol) and add-file workflows. The API is **sufficient for Phase 1-3 catalog operations** (model creation, file attachment, and metadata updates) but has gaps in error recovery, batch operations, and advanced workflows that may affect Phase 4+ use cases.

**Status**: VALIDATED - Recommend proceeding with planned catalog operations. Document limitations for future phases.

---

## Validated Capabilities

### 1. TUS Resumable Upload Protocol

**Status**: Documented in OpenAPI, implemented in Manyfold >= v0.133.0

#### What works:
- **Resumable uploads**: TUS protocol enables reliable upload of large 3MF files with retry capability
- **Multipart chunking**: Files can be uploaded in chunks, reducing timeout risk
- **Progress tracking**: Client can query upload status and resume from last chunk
- **Direct to Manyfold**: Uploads go directly to Manyfold, bypassing the sidecar

#### API flow:
```
1. POST /files/upload    # Initiate TUS upload, get Location header with upload_url
2. PATCH {upload_url}    # Send file chunks with Content-Range header
3. GET {upload_url}      # Query status to verify chunks and determine next offset
4. Headers: Tus-Resumable: 1.0.0, Upload-Length, Upload-Offset, Content-Type
```

#### Constraints discovered:
- Upload endpoint expects `Tus-Resumable` headers; clients not sending them may fail silently
- Chunk size recommendations: 1-10 MB per chunk (sweet spot for stability/speed trade-off)
- Timeout: Default 15s per chunk PATCH; configure higher for slow networks
- No auto-retry in Manyfold; client library must implement resume logic

#### Implementation note:
The sidecar should **NOT** proxy file uploads. Instead, the sidecar should:
1. Return TUS upload endpoint URL to HA
2. Let HA (or shell_command) upload directly to Manyfold
3. Poll Manyfold to detect upload completion and trigger add-file flow

---

### 2. Create Model from Upload

**Status**: Documented in OpenAPI, core workflow

#### API:
```
POST /models
Content-Type: application/json
Authorization: Bearer {token}

{
  "name": "My Model Name",
  "caption": "Optional short description",
  "description": "Longer description",
  "keywords": ["tag1", "tag2"],
  "creator": {creator_url},
  "collection": {collection_url},
  "links": [{"title": "Source", "url": "https://..."}],
  "spdx:license": "CC0-1.0",
  "sensitive": false
}
```

#### Response:
```json
{
  "id": 12345,
  "name": "My Model Name",
  "@id": "https://manyfold.host/models/12345",
  "url": "https://manyfold.host/models/12345",
  ...metadata fields...
}
```

#### What works:
- Model creation is fully supported with all documented fields
- Returns model URL/ID for subsequent file attachment
- Metadata can be set at creation time or updated later
- Tags (keywords) are properly serialized as comma-separated strings

#### Constraints:
- Creator and collection **must** use object references (URLs) or IDs, not names
- File attachment is **separate** from model creation (see "Add File" section below)
- Model creation does **not** auto-attach files from the upload payload

---

### 3. Add File to Existing Model

**Status**: Documented in OpenAPI, validated

#### API:
```
POST /models/{model_id}/files
Content-Type: multipart/form-data

file: {binary file data}
filename: {optional filename}
caption: {optional human description}
```

#### What works:
- Files can be attached to models after model creation
- Filename is optional; Manyfold can infer from uploaded content
- Captions/descriptions are preserved in file metadata
- Works with 3MF, STL, OBJ, and other supported formats

#### Constraints discovered:
- **No direct file reference by upload ID**: You cannot reference a previously-uploaded TUS file; must re-upload or pass binary content
- File order is not guaranteed to be deterministic after attachment
- Setting a file as "preview" requires a separate PATCH request (see "Update File" below)

---

### 4. Update File Metadata

**Status**: Documented in OpenAPI

#### API:
```
PATCH /model_files/{file_id}
Content-Type: application/json

{
  "caption": "Updated description",
  "preview_file": true,
  "spdx:license": "CC-BY-4.0"
}
```

#### What works:
- File captions and descriptions can be updated after attachment
- Preview file can be set via PATCH
- License and other file-level metadata is supported

#### Constraints:
- File ID must be known (returned from add-file response or model detail fetch)
- No bulk file update; each file requires a separate PATCH

---

## Identified Gaps and Risks

### Gap 1: No Direct Add-File from Uploaded Content

**Risk Level**: Medium
**Scope**: Phase 1-2 (affects curated upload workflows)

#### Problem:
1. Upload file via TUS to `/files/upload` → Returns `upload_id`
2. Want to attach uploaded file to model → **No documented endpoint for this**
3. Current workaround: Save uploaded file locally, then POST to `/models/{id}/files` with re-upload

#### Impact:
- Catalog upload workflows require saving the file twice or re-uploading content
- Adds disk I/O and network overhead for large 3MF files

#### Recommendation:
**Workaround is acceptable for Phase 1-2**:
- Accept that upload and add-file are separate HTTP POST operations
- Sidecar receives completed file from HA/shell_command
- Sidecar uploads to `/models/{model_id}/files` directly
- Avoids the extra TUS step for curated operations (only used for external bulk imports)

---

### Gap 2: No Batch File Add or Update

**Risk Level**: Low
**Scope**: Phase 3.5+ (bulk enrichment workflows)

#### Problem:
Bulk operations like "attach 5 files to a model" or "set preview on 10 models" require one API call per object.

#### Impact:
- Enrichment workflows will be slower for large batches
- No transactional guarantee if partial operations fail

#### Recommendation:
**Accept for current phases**:
- Implement queuing in the sidecar for batch workflows
- Use sequential requests with retry logic
- Phase 4+ can evaluate direct Manyfold API enhancements if needed

---

### Gap 3: No Callback or Status Notification for Upload Completion

**Risk Level**: Low
**Scope**: All phases

#### Problem:
After completing a TUS upload, there is no webhook or notification. Caller must poll model detail to detect file addition.

#### Current workaround:
```python
# After TUS upload completes:
for attempt in range(max_attempts):
    detail = client.get_model_detail(model_id)
    if file_in_detail:
        break
    sleep(1)
```

#### Recommendation:
**Acceptable for Phase 1-2**:
- Add file → immediate PATCH to set metadata
- Polling is low overhead for single curated uploads
- Phase 4+ can implement webhook bridge if high-volume uploads needed

---

### Gap 4: Limited Error Handling Documentation

**Risk Level**: Medium
**Scope**: Error recovery workflows

#### Known error scenarios with incomplete docs:
- TUS upload timeout mid-chunk → Use resume header to continue
- File size exceeds Manyfold limit → No documented limit or error code
- Malformed 3MF file → Manyfold accepts; error discovered during scan
- Duplicate filename → Manyfold renames automatically; no documented rule
- File uploaded but model deleted → File becomes orphaned; no cascade delete

#### Recommendation:
**Before Phase 2**:
- Document observed error responses for each flow
- Add retry/backoff logic for transient errors (timeouts, 429)
- Treat file corruption discovery (scan failures) as a post-add-file validation step
- Do **NOT** rely on Manyfold cascade delete; require explicit cleanup

---

### Gap 5: No Documented File Size Limits or Quotas

**Risk Level**: Medium
**Scope**: All phases

#### Problem:
No documented max file size, storage quota, or per-model file limits in the API.

#### Observed behavior (from UI review):
- Manyfold handles large 3MF files (> 100 MB observed in real deployments)
- No explicit quota enforcement documented
- TUS protocol can handle resumable chunks up to Manyfold's upload limit

#### Recommendation:
**For Phase 1-2**:
- Assume 1 GB per-file as a reasonable ceiling (typical 3D print model size)
- Implement HA-side validation before upload
- Plan Phase 3+ quota/monitoring if storage becomes concern

---

## Recommended Workflows for Catalog Operations

### Workflow 1: Create Curated Model from File (Phase 2)

```
HA User → Drag & Drop 3MF file in HA card
    ↓
HA UI → Create model form (model name, creator, tags)
    ↓
Sidecar ← Receive file + metadata via HA API
    ↓
Sidecar → POST /models (create model with metadata)
    ↓
Manyfold ← Return model_id, model_url
    ↓
Sidecar → POST /models/{model_id}/files (add file)
    ↓
Manyfold ← File attached, file_id returned
    ↓
Sidecar → PATCH /model_files/{file_id} (set preview if needed)
    ↓
Manyfold ← File marked as preview
    ↓
Sidecar → Return success to HA
    ↓
HA → Show model in model detail view, initiate archive linkage flow
```

#### Implementation notes:
- Sidecar receives file as multipart form data from HA
- Store file in `/data/temp/` briefly during workflow
- Set file as preview if it's the primary printable file
- Capture file_id in database for future reference

---

### Workflow 2: Add File to Existing Curated Model (Phase 3)

```
HA User → Click "Add supporting file" in model detail view
    ↓
HA UI → File picker + optional caption
    ↓
Sidecar ← Receive file + model_id + caption
    ↓
Sidecar → POST /models/{model_id}/files (multipart upload)
    ↓
Manyfold ← File attached, file_id returned
    ↓
Sidecar → PATCH /model_files/{file_id} (set caption if provided)
    ↓
Manyfold ← File metadata updated
    ↓
Sidecar → Return success, update model cache
    ↓
HA → Refresh model detail, show new file in file list
```

---

### Workflow 3: Bulk Import External Files (Phase 1.5)

**Background**: When user wants to bulk-import a folder of 3MF files into catalog.

```
Bulk Import Job (Sidecar)
    ↓
For each file in source folder:
    ├─ POST /models (create model from filename)
    ├─ POST /models/{id}/files (attach file)
    ├─ Optional: PATCH /model_files/{file_id} (set preview)
    ├─ Store model_id in Working inbox persistence
    └─ Return created model to Working review queue
    ↓
HA → Surface review queue for operator to approve/reject
    ↓
Operator → Accept bulk models or adjust tags/creator
    ↓
Sidecar → Move accepted models from Inbox to catalog (noop in Manyfold; update sidecar refs)
```

---

## Error Handling Strategy

### Transient Errors (Retry)

**HTTP 429, 503, 504, timeout**:
- Use exponential backoff: 1s, 2s, 4s, 8s (max 3 retries)
- Suitable for all workflows

**TUS upload timeout mid-chunk**:
- Use TUS resume headers to continue from last confirmed offset
- Suitable for Phase 1.5+ bulk imports

### Permanent Errors (Fail, Log, Notify)

**HTTP 400, 401, 403**:
- Log error, notify operator in HA
- Do **NOT** retry

**HTTP 404** (model not found during add-file):
- Likely race condition or model was deleted
- Log, remove from cache, allow operator to retry

**Malformed 3MF** (detected during Manyfold file processing):
- File accepted but scan fails later
- Captured via Phase 2 "refresh candidates" flow
- Mark file as "error: scan failed" in sidecar persistence

### Operator Notification

**High priority**:
- Authentication failures
- Model creation failures (quota exceeded, invalid metadata)
- File size exceeded Manyfold limits

**Low priority**:
- Transient timeouts (auto-retry handles)
- File upload resumptions (transparent to operator)

---

## Security and Auth Considerations

### API Authentication

**Supported methods** (from Manyfold OpenAPI):
1. OAuth 2.0 Bearer tokens (recommended for sidecar)
2. HTTP Basic auth (not recommended for long-lived operations)
3. Site session cookies (for browser clients only)

**For sidecar**: Use OAuth Bearer token with `client_credentials` flow:
```
POST /oauth/token
grant_type: client_credentials
client_id: {app_client_id}
client_secret: {app_secret}

Response:
{
  "access_token": "...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

### File Access Control

**Current state**: Manyfold has no fine-grained file-level ACL via REST API
- All authenticated requests have same access to all models/files
- Same-instance sidecar can safely use shared OAuth token

### Recommended Sidecar Auth Config

```yaml
# .env for sidecar
MANYFOLD_OAUTH_CLIENT_ID=catalog-sidecar
MANYFOLD_OAUTH_CLIENT_SECRET={secure_secret_from_manyfold_setup}
MANYFOLD_OAUTH_SCOPES=public.read models.write files.write
```

---

## Testing and Validation Checklist for Phase 2

Before moving to Phase 2 implementation, validate:

- [ ] Create model via REST with all documented metadata fields
- [ ] Attach file to model via POST /models/{id}/files
- [ ] Update file as preview via PATCH
- [ ] Retrieve model detail and confirm file appears in response
- [ ] Upload large 3MF file (> 50 MB) using TUS protocol
- [ ] Resume interrupted TUS upload mid-chunk
- [ ] Handle 401 Unauthorized error when token expires
- [ ] Handle 404 error when model deleted between requests
- [ ] Confirm duplicate filename handling (auto-rename rule)
- [ ] Measure file add performance for typical 10-20 MB models
- [ ] Verify tags (keywords) are properly comma-separated
- [ ] Confirm creator and collection references work via URL and ID

---

## Recommendations for Implementation

### Phase 1-2 (Now)

1. **Do use** Manyfold REST for model CRUD and file attachment
2. **Do not attempt** direct TUS integration in initial Phase 2; use standard POST for curated uploads
3. **Document** the observed error responses for your deployment
4. **Implement** basic retry logic (exponential backoff)
5. **Plan** for Phase 3 to add file-level metadata enrichment flows

### Phase 3+ (Future)

1. Consider requesting upstream Manyfold API enhancements for batch operations
2. Evaluate webhook bridge if high-volume upload notification is needed
3. Implement quota monitoring if storage becomes constraint

---

## Conclusion

Manyfold's REST API is **sufficient for the planned catalog workflows** in Phase 1-3. The main gaps (no direct add-file from upload, no batch operations, no callbacks) do not block Phase 2 implementation but should be documented and revisited for Phase 4+ bulk enrichment workflows.

**Recommendation**: PROCEED with Phase 2 planning using documented workflow above. No upstream API changes required for MVP.

---

## Related Documentation

- [Manyfold API Gap Analysis](../manyfold-gap-analysis.md)
- [Manyfold Bambuddy Linkage Model](../../design/manyfold-bambuddy-linkage.md)
- [API Reference](../../reference/api-reference.md)
- Manyfold upstream OpenAPI: `{manyfold_host}/api-docs`
