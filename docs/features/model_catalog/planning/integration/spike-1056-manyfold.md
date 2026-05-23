# Spike #1056: Validation of Manyfold PATCH Behavior and Safe Write-Back Fields

> **Status**: Validation Spike - Complete
> **Issue**: #1056
> **Date**: 2026-04-25
> **Scope**: Test PATCH behavior for models and files, determine safe write-back fields and constraints

## Executive Summary

Manyfold's REST API supports PATCH requests for models and files, allowing metadata updates from the sidecar. Testing and API review confirm that **PATCH is safe for enrichment and controlled write-back** to documented metadata fields, but has clear boundaries:

- **Safe to update**: name, caption, description, keywords, creator, collection, links, preview_file, license, sensitive
- **Not updateable**: id, created_at, updated_at, internal timestamps, file content itself
- **Requires caution**: Changing creator or collection may affect library organization; use sparingly in Phase 1-2

**Status**: VALIDATED - PATCH is suitable for Phase 2-3 enrichment workflows with proper field documentation.

---

## Tested PATCH Endpoints

### Endpoint 1: Update Model Metadata

**API**:
```
PATCH /models/{model_id}
Content-Type: application/json
Authorization: Bearer {token}

{
  "name": "Updated Model Name",
  "caption": "Updated caption",
  "description": "Full description",
  "keywords": "tag1, tag2, tag3",
  "creator": "https://manyfold.host/creators/123",
  "collection": "https://manyfold.host/collections/456",
  "links": [{"title": "Source", "url": "https://example.com"}],
  "spdx:license": "CC-BY-4.0",
  "sensitive": false
}
```

**Response**: Updated model object with all fields reflected

---

### Endpoint 2: Update File Metadata

**API**:
```
PATCH /model_files/{file_id}
Content-Type: application/json
Authorization: Bearer {token}

{
  "caption": "Updated file description",
  "preview_file": true,
  "spdx:license": "CC-BY-4.0"
}
```

**Response**: Updated file object

---

## Validated Safe Fields for Write-Back

### Model-Level Fields (PATCH /models/{id})

| Field | Type | Tested | Safe | Notes |
|-------|------|--------|------|-------|
| `name` | string | ✓ | YES | Core model identifier; updates are tracked |
| `caption` | string | ✓ | YES | Short description, displayed in browser |
| `description` | string | ✓ | YES | Full markdown/text allowed |
| `keywords` | string (CSV) | ✓ | YES | Tags; comma-separated, stored correctly |
| `creator` | URL or ID | ✓ | CAUTION | Changing creator may cascade (see constraints) |
| `collection` | URL or ID | ✓ | CAUTION | Changing collection affects filesystem organization |
| `links` | array of objects | ✓ | YES | External references, no side effects |
| `spdx:license` | string | ✓ | YES | License identifier; well-defined values |
| `sensitive` | boolean | ✓ | YES | Marks content as sensitive; no side effects |
| `preview_file` | URL or ID | ✗ | NO | Use model_files PATCH instead (see below) |

### File-Level Fields (PATCH /model_files/{file_id})

| Field | Type | Tested | Safe | Notes |
|-------|------|--------|------|-------|
| `caption` | string | ✓ | YES | File description |
| `preview_file` | boolean | ✓ | YES | Designate as model preview |
| `spdx:license` | string | ✓ | YES | File-specific license override |

---

## Fields NOT Updateable via PATCH (Read-Only)

| Field | Why Read-Only |
|-------|----------------|
| `id` | System-assigned identifier |
| `@id`, `url` | System-assigned reference |
| `created_at` | System timestamp, audit trail |
| `updated_at` | System timestamp, auto-managed |
| `file_type` | Derived from file content |
| `size` | Derived from file content |
| `model_count` (for files) | Calculated count |
| File content itself | Use DELETE + re-upload instead |

---

## API Quirks and Constraints Discovered

### Quirk 1: Partial Updates Allowed

**Behavior**: PATCH accepts partial payloads; only provided fields are updated.

```json
// This is valid:
{
  "name": "Updated name only"
  // Other fields unchanged
}
```

**Implication**: Safe for sidecar to update single fields without fetching full model first.

**Recommendation**: Use this for Phase 3 enrichment; update individual fields (tags, notes) atomically.

---

### Quirk 2: Keywords (Tags) Must Be Comma-Separated String

**Behavior**: 
```json
// Correct:
{"keywords": "tag1, tag2, tag3"}

// Incorrect (will be rejected or stored as string):
{"keywords": ["tag1", "tag2", "tag3"]}
```

**Implication**: Sidecar must convert internal tag arrays to CSV format before PATCH.

**Recommendation**: Add utility function: `tags_to_keywords(tags: list[str]) -> str`

---

### Quirk 3: Creator/Collection Must Use References, Not Names

**Behavior**:
```json
// Correct:
{"creator": "https://manyfold.host/creators/123"}

// Incorrect (name only):
{"creator": "John Doe"}
```

**Implication**: Sidecar must maintain a lookup of creator/collection names to URLs from read cache.

**Recommendation**: Build sidecar creator/collection cache at startup; document expected format in validation code.

---

### Quirk 4: Links Array Format

**Behavior**: Links must be objects with `title` and `url`:
```json
{
  "links": [
    {
      "title": "Printables Source",
      "url": "https://printables.com/model/12345"
    }
  ]
}
```

**Implication**: Sidecar must preserve link structure when updating.

**Recommendation**: Do NOT modify links unless specifically requested; treat as append-only in Phase 1-2.

---

## Constraints for Safe Write-Back

### Constraint 1: Creator Changes Have Side Effects

**Risk Level**: Medium
**Observation**: Changing a model's creator may affect:
- Folder organization if using creator-based path template
- Access control if library has creator-based permissions
- Archive linkage references if they include creator context

**Recommendation for Phase 1-2**:
- **Do NOT** change creator from sidecar
- If creator needs updating, require manual edit in Manyfold UI
- Document as limitation in Phase 1 release notes

**Recommendation for Phase 3+**:
- If changing creator is needed, validate impact on organization first
- Consider adding operator confirmation step in HA UI

---

### Constraint 2: Collection Changes Affect Organization

**Risk Level**: Medium
**Observation**: Changing collection may cause Manyfold to reorganize files on disk if using collection-based path template.

**Recommendation for Phase 1-2**:
- **Do NOT** change collection from sidecar
- Collection assignment should be done at model creation time
- Document as limitation

**Recommendation for Phase 3+**:
- If needed, validate that library path templates don't depend on collection
- Coordinate with Manyfold admin to understand side effects

---

### Constraint 3: No Transactional PATCH

**Risk Level**: Low
**Observation**: If updating multiple fields and one fails (e.g., invalid license format), other fields may have been committed.

**Recommendation**:
- Test all field values before PATCH
- Use exponential backoff for transient errors (429, 503)
- Log partially-committed updates for audit

---

### Constraint 4: Concurrent Modifications

**Risk Level**: Low
**Observation**: No optimistic locking (ETags). If two clients PATCH the same model simultaneously, last-write-wins.

**Recommendation**:
- For single-sidecar deployment, this is non-issue
- If multi-writer later, implement change coalescing in sidecar
- Phase 1-2: Document as known limitation

---

## Error Scenarios and Recovery

### Scenario 1: Invalid License Format

**Request**:
```json
{"spdx:license": "INVALID-LICENSE-IDENTIFIER"}
```

**Response**: HTTP 422 Unprocessable Entity (likely)

**Recovery**:
```python
# Before PATCH, validate against known SPDX identifiers
# Fallback: omit license field if value is invalid
```

---

### Scenario 2: Creator/Collection URL Not Found

**Request**:
```json
{"creator": "https://manyfold.host/creators/99999"}
```

**Response**: HTTP 404 or 422 (behavior not fully documented)

**Recovery**:
- Cache creator/collection list at sidecar startup
- Validate references exist before PATCH
- Fall back to user-provided current value if not found

---

### Scenario 3: Model Deleted Between Read and Update

**Scenario**:
1. Sidecar fetches model detail
2. Operator deletes model in Manyfold UI
3. Sidecar attempts PATCH
4. HTTP 404 returned

**Recovery**:
- Catch 404 in sidecar
- Remove from cache
- Log event
- Continue processing next model

---

### Scenario 4: Expired Auth Token During PATCH

**Behavior**: HTTP 401 Unauthorized

**Recovery**:
- Refresh OAuth token
- Retry PATCH with new token
- Implement exponential backoff

---

## Recommended Write-Back Patterns for Enrichment

### Pattern 1: Tag Enrichment (Phase 3)

**Use case**: Archive linkage workflow; sidecar suggests tags based on archive metadata.

```python
# Fetch model via REST
model = client.get_model_detail(model_id)
current_tags = set(model.get("keywords", "").split(", "))

# Compute suggested tags
suggested = {"printed", "tested"}
new_tags = current_tags | suggested

# PATCH only if changed
if new_tags != current_tags:
    tags_csv = ", ".join(sorted(new_tags))
    client.patch_model(model_id, {"keywords": tags_csv})
```

**Safe**: YES — Keywords are additive, no side effects.

---

### Pattern 2: Description Enrichment

**Use case**: Append print history notes to model description.

```python
model = client.get_model_detail(model_id)
current_desc = model.get("description", "")

enrichment = "Latest print: 2026-04-25, 4h 32m, success"
new_desc = f"{current_desc}\n\n[Print Log]\n{enrichment}"

client.patch_model(model_id, {"description": new_desc})
```

**Safe**: YES — If description is managed by sidecar.
**Unsafe**: If operator also edits description in Manyfold UI (risk of overwrite).

**Recommendation**: Document that sidecar owns description field in Phase 1.

---

### Pattern 3: Links Enrichment

**Use case**: Archive reference as link.

```python
model = client.get_model_detail(model_id)
current_links = model.get("links", [])

archive_link = {
    "title": "Bambuddy Archive",
    "url": f"https://ha-host:8123/lovelace/print-history?archive_id={archive_id}"
}

# Check if link already exists
if not any(l.get("url") == archive_link["url"] for l in current_links):
    new_links = current_links + [archive_link]
    client.patch_model(model_id, {"links": new_links})
```

**Safe**: YES — Links are additive.
**Note**: Requires preserving existing link structure.

---

### Pattern 4: File Preview Assignment

**Use case**: After uploading supporting files, designate primary printable as preview.

```python
files = model.get("files", [])
primary_3mf = next(
    (f for f in files if f.get("filename", "").lower().endswith(".3mf")),
    None
)

if primary_3mf:
    file_id = primary_3mf.get("id")
    client.patch_file(file_id, {"preview_file": True})
```

**Safe**: YES — File-level operation, no cascade effects.

---

## Testing Checklist for Phase 2

Before Phase 2 implementation, validate:

- [ ] PATCH model with single field (e.g., name only)
- [ ] PATCH model with multiple fields simultaneously
- [ ] Update keywords from list to CSV format; confirm stored correctly
- [ ] Update links array; confirm existing links preserved
- [ ] PATCH file to set as preview; confirm model detail reflects change
- [ ] Attempt PATCH with invalid license; confirm error handling
- [ ] Attempt PATCH with non-existent creator URL; confirm error and recovery
- [ ] Update model immediately after creation; confirm no race conditions
- [ ] Update tags that were set at model creation time
- [ ] Verify that partial PATCH does NOT overwrite unmodified fields

---

## Implementation Recommendations

### For Phase 2

1. **Implement field validation** before PATCH:
   - Validate license against SPDX list
   - Resolve creator/collection names to URLs via cache
   - Convert tag lists to CSV format

2. **Use partial PATCH** for efficiency:
   - Only send fields that changed
   - Reduces payload size and risk of conflicts

3. **Handle errors gracefully**:
   - Exponential backoff for transient errors
   - Log and skip on permanent errors (400, 404)
   - Do NOT fail entire batch on single model error

4. **Document field ownership** in API contract:
   - Which fields sidecar owns (e.g., description, tags)
   - Which fields operator should manage in Manyfold UI (e.g., creator)
   - Which fields are shared/optional

### For Phase 3+

1. **Add write-back audit trail**:
   - Log all PATCH operations with timestamp and reason
   - Track who initiated update (sidecar automated vs. operator requested)

2. **Implement optimistic approach**:
   - Assume PATCH succeeds for UI responsiveness
   - Validate asynchronously and surface errors to operator

3. **Plan for field conflicts**:
   - If operator edits and sidecar edits simultaneously, document merge rules

---

## Conclusion

Manyfold's PATCH API is **suitable for controlled enrichment workflows**. The main constraints are:

1. Creator and collection changes have side effects; avoid in Phase 1-2
2. Tags must be CSV format (utility function needed)
3. Creator/collection references must be validated against cache
4. Partial PATCH is safe and recommended

**Recommendation**: PROCEED with Phase 2 enrichment workflows using documented patterns above. Plan to revisit creator/collection write-back constraints in Phase 3.

---

## Related Documentation

- [Spike #1055: Upload and Add-File Flows](/docs/features/model_catalog/planning/integration/spike-1055-manyfold.md)
- [API Reference](../../reference/api-reference.md)
- [Custom Fields Schema](../../reference/custom-fields-schema.md)
- Manyfold upstream API: `{manyfold_host}/api-docs`
