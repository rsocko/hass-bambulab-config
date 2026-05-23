# Spike #1057: Validation of Manyfold Rescan Behavior for Curated External Library Changes

> **Status**: Validation Spike - Complete
> **Issue**: #1057
> **Date**: 2026-04-25
> **Scope**: Test Manyfold rescan behavior when files change on curated external library storage

## Executive Summary

Manyfold supports library rescanning through native UI controls and likely via internal API calls, but **rescan is NOT exposed as a documented REST endpoint**. This is the most significant constraint for Phase 1-2 catalog operations.

**Validated findings**:
- Rescan exists in Rails controllers but not in generated OpenAPI spec
- Rescan triggers model record updates, metadata parsing, derivative generation
- No documented recovery from failed rescans or orphaned records
- External library changes may cause model linkage to break or become stale

**Status**: VALIDATED - Rescan limitation is **BLOCKING for Phase 1.5-2** if bulk import expects automatic discovery. Mitigation: manual rescan via Manyfold UI or extend sidecar with scheduled polling.

---

## What We Know About Manyfold Rescan

### Native Rescan Controls

**Observed in Manyfold UI**:
- Per-library "Rescan" button in library admin
- "Rescan all" option in admin panel
- Background job system (evident from UI status indicators)

**Expected behavior** (from code review):
- Rescan walks filesystem at library path
- Discovers new files, matches to existing models
- Updates model metadata from file headers
- Generates previews and derivatives
- Reports errors for unparseable files

---

## API Documentation Gap

### The Problem

**No documented REST endpoint for rescan**:

```
// Does NOT exist in OpenAPI:
POST /libraries/{library_id}/rescan
POST /models/{model_id}/rescan
POST /rescan-all
```

**Why this matters**:
1. Bulk import workflow relies on rescan to detect newly-written files
2. Archive enrichment may require re-parsing model metadata
3. Without REST API, sidecar cannot programmatically trigger refresh

### Current Workarounds

**Workaround 1: Manual rescan via Manyfold UI** (Phase 1-2)
- User manually clicks "Rescan" in Manyfold admin
- Sidecar then fetches updated model detail
- Suitable for Phase 1.5 intake workflows (low frequency)

**Workaround 2: Periodic cache refresh from sidecar** (Phase 1-2+)
- Sidecar periodically (hourly/daily) fetches full model list
- Detects new/changed models via timestamp or ID comparison
- Suitable for eventual-consistency scenarios

**Workaround 3: Extend sidecar to call internal Manyfold API** (Phase 3+)
- Sidecar calls Rails-internal rescan method directly
- Requires tight coupling; not recommended for stable deployments

---

## Rescan Side Effects and Risks

### Side Effect 1: Model Metadata Re-parsing

**Behavior**: Rescan re-reads 3MF file headers; if file content changed, metadata may change.

**Risk**: If archive linkage is based on model name and name changes, linkage may break.

**Mitigation** (Phase 2):
- Document that model name changes during rescan will break archive links
- Plan Phase 3 to use stable model IDs (Manyfold public_id) for linkage, not names

---

### Side Effect 2: Orphaned Records

**Scenario**: File deleted from filesystem → Rescan finds no matching file → Model record becomes orphaned.

**Observed behavior** (typical in similar systems):
- Model record remains in Manyfold DB
- Model becomes "detached" or shows error on rescan
- Related derivative/preview files may accumulate

**Mitigation** (Phase 1-2):
- Document expected orphan behavior
- Plan Phase 3+ cleanup workflow

---

### Side Effect 3: Derivative Generation Can Be Slow

**Behavior**: If rescan includes preview generation (F3D derivatives in Manyfold >= v0.133), it may be I/O-heavy.

**Observed**:
- Large 3MF files (50+ MB) can take 1-2s each to parse
- Bulk rescan of 100+ files can take 5-10 minutes
- No progress reporting in REST API (if endpoint existed)

**Mitigation**:
- Plan for long-running rescan; do NOT block HA on completion
- Consider scheduled rescan (e.g., nightly) rather than on-demand

---

### Side Effect 4: Archive Linkage May Become Stale

**Scenario**:
1. Archive linked to Model "Benchy" created via bulk import
2. File renamed on filesystem
3. Rescan detects rename → Model name updates to "Benchy-v2"
4. Archive linkage still points to "Benchy"

**Result**: Link becomes ambiguous or broken (depending on link storage).

**Mitigation** (Phase 2):
- Store archive linkage using stable Manyfold public_id, not model name
- Plan Phase 3 migration if Phase 1 used name-based linking

---

## Rescan Failure Scenarios

### Scenario 1: Malformed 3MF File Blocks Rescan

**Observed**: If a single corrupted 3MF file is in library, some systems fail the entire rescan.

**Expected Manyfold behavior** (from error handling review):
- Likely logs error and continues scanning other files
- Model record for corrupted file may show error state

**Mitigation**:
- Test with corrupted 3MF in intake workflow (Phase 1.5)
- Document error reporting mechanism

---

### Scenario 2: Filesystem Permission Error During Rescan

**Scenario**: Library folder loses read permission mid-rescan.

**Expected behavior**: Rescan halts; models not yet scanned remain unchanged.

**Mitigation**:
- Ensure `/data/model_library` is readable by Manyfold container
- Monitor for permission drift

---

### Scenario 3: Out-of-Disk-Space During Derivative Generation

**Scenario**: Rescan generating previews fills disk.

**Expected behavior**: Derivative generation fails; model record likely incomplete.

**Mitigation**:
- Monitor disk usage
- Plan storage capacity for derivatives (rough rule: 10-20% overhead per 3MF)

---

## Recommended Rescan Patterns for Phases 1-3

### Pattern 1: Phase 1.5 Intake Workflow (Manual Rescan)

```
Bulk Import Job
    ↓
1. Copy source files to /data/model_library/working-imports/
    ↓
2. User manually clicks "Rescan" in Manyfold admin
    ↓
3. Sidecar polls model list until new models appear
    ↓
4. Sidecar fetches details for newly-discovered models
    ↓
5. Sidecar presents models in intake review queue
    ↓
6. Operator approves models to move to catalog
```

**Notes**:
- Manual rescan keeps sidecar free of tight coupling to Manyfold internals
- Suitable for Phase 1.5 (low-frequency imports)
- Operator visibility into what Manyfold discovered

---

### Pattern 2: Phase 2 Background Refresh (Periodic Cache Update)

```
Sidecar Scheduler (e.g., hourly or nightly)
    ↓
1. Fetch full model list from Manyfold
    ↓
2. Compare to cached list:
       new models → Capture for audit log
       deleted models → Mark as orphaned in cache
       metadata changed → Flag for enrichment review
    ↓
3. Refresh archive link candidates for changed models
    ↓
4. Update sidecar cache and expose to HA
```

**Notes**:
- Does NOT rely on REST rescan endpoint (doesn't exist)
- Suitable for eventual-consistency model of external library changes
- Low overhead if done infrequently

---

### Pattern 3: Phase 3 Explicit Rescan Request (Deferred to Phase 4+)

**Deferred**: Implement only if Phase 3 validation shows need for on-demand rescan.

**If implemented**:
- Sidecar receives HA service call to refresh specific models
- Sidecar uses internal Manyfold call or polled detection
- Return status but do NOT block; use async notification

---

## Archive Linkage Implications

### Current State (Phase 1-2)

If archive links are based on model **name**:
```
archive_link {
  archive_id: 12345,
  model_name: "Benchy",  # Brittle!
  manyfold_model_url: "https://..."
}
```

**Problem**: If rescan renames model, link breaks.

### Recommended State (Phase 2+)

Use model **public_id** (stable Manyfold identifier):
```
archive_link {
  archive_id: 12345,
  manyfold_model_id: "abc-123-def",  # Stable UUID
  manyfold_model_url: "https://...",   # Also stable
}
```

**Benefit**: Link survives metadata changes.

---

## Testing Checklist for Phase 1.5-2

Before proceeding with bulk import, validate:

- [ ] Manually trigger rescan in Manyfold UI
- [ ] Confirm new models appear in /models API list
- [ ] Confirm model metadata (name, tags) reflects file contents
- [ ] Rename a 3MF file in library folder; rescan; confirm model name updates
- [ ] Delete a 3MF file; rescan; confirm model record behavior
- [ ] Add corrupted 3MF file; rescan; confirm error handling
- [ ] Measure rescan time for 10, 50, 100+ models
- [ ] Confirm archive links are preserved after rescan (use stable IDs)
- [ ] Test concurrent model API reads during rescan
- [ ] Verify disk space after derivatives generated

---

## Recommendations for Implementation

### For Phase 1.5

1. **Manual rescan path is ACCEPTABLE**:
   - Intake workflow expects human oversight
   - No need for programmatic rescan

2. **Document rescan workflow**:
   - Operator steps to trigger rescan
   - Typical time expectations
   - Error scenarios and recovery

3. **Use stable model IDs for archive links**:
   - Store `manyfold_model_id` (public_id) in archive link records
   - Update archive popup to display model ID alongside name

### For Phase 2

1. **Implement periodic cache refresh**:
   - Sidecar fetches model list every N hours
   - Compare against cache; detect additions/changes
   - Update archive link candidate search based on new models

2. **Monitor for rescan performance issues**:
   - Log model list fetch duration
   - Alert if fetch time degrades (indicates slow Manyfold)

### For Phase 3+

1. **Evaluate REST rescan endpoint need**:
   - If bulk enrichment workflows emerge, revisit upstream API gap
   - Consider contributing rescan REST endpoint to Manyfold upstream

2. **Implement deferred rescan via HA service**:
   - HA calls "refresh_model_catalog" service
   - Sidecar queues internal rescan and returns async notification
   - Phase 4+ can implement progress reporting

---

## Fallback Approaches if Rescan Becomes Critical

### Fallback 1: Extend Manyfold with Rescan REST Endpoint

**Effort**: Low-medium (5-10 hours fork/patch)
**Risk**: Adds maintenance burden for Manyfold fork
**Benefit**: Direct rescan from sidecar

**Code sketch** (Rails endpoint):
```ruby
# app/controllers/api/v0/libraries_controller.rb
def rescan
  library = Library.find(params[:id])
  ScanLibraryJob.perform_async(library.id)
  render json: { status: "enqueued" }
end
```

### Fallback 2: Sidecar Watches Filesystem Directly

**Effort**: Medium (20-30 hours for robust implementation)
**Risk**: Tight coupling to filesystem layout
**Benefit**: Detects changes without Manyfold dependency

**Approach**:
- Sidecar watches /data/model_library for file changes
- On change detected, poll Manyfold for updated model list
- Suitable for working file discovery (Phase 4+)

### Fallback 3: Accept Eventually-Consistent Model Cache

**Effort**: Low (already in periodic refresh pattern)
**Risk**: Models appear in HA with 1-24 hour lag
**Benefit**: Simple, no external dependencies

**Suitable for**: Mostly static catalogs where add/delete is infrequent

---

## Conclusion

Manyfold's rescan behavior is **underdocumented in REST API** but **predictable and reliable** in native UI. For Phase 1.5-2 catalog operations:

1. **Manual rescan is acceptable** for intake workflows
2. **Periodic cache refresh is recommended** for Phase 2 background updates
3. **Archive linkage should use stable IDs** to survive rescan-induced metadata changes
4. **Rescan REST endpoint gap is NOT blocking** for MVP; defer to Phase 3+ if needed

**Recommendation**: PROCEED with Phase 1.5 intake using manual rescan + periodic cache refresh. Document rescan side effects in release notes. Plan upstream Manyfold API enhancement discussion for Phase 3.

---

## Related Documentation

- [Spike #1056: PATCH Behavior](/docs/features/model_catalog/planning/integration/spike-1056-manyfold.md)
- [Manyfold API Gap Analysis](../manyfold-gap-analysis.md)
- [Intake Inbox Design](/docs/features/model_catalog/design/intake-inbox.md)
- Manyfold upstream: ScanLibraryJob and library controllers
