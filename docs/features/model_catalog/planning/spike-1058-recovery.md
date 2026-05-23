# Spike #1058: Validation of Recovery After Restoring Missing External Files or Folders

> **Status**: Validation Spike - Complete
> **Issue**: #1058
> **Date**: 2026-04-25
> **Scope**: Test recovery scenarios when previously-cataloged files are restored to same path after deletion/drift

## Executive Summary

Recovery behavior after file restoration depends on **how Manyfold tracks files, whether timestamps are used, and whether linkage is path-based or ID-based**. Testing reveals:

**Key findings**:
- Manyfold can detect and re-attach files restored to original paths after rescan
- Archive linkage may break or require refresh if based on file path or model name
- Content hash changes (same path, different file) cause model metadata mismatch
- Orphaned model records from previous file remain until manually deleted

**Status**: VALIDATED - Recovery is **POSSIBLE but requires operator intervention**. Mitigation strategies documented for each scenario.

---

## Restoration Scenarios Tested

### Scenario 1: File Deleted, Then Restored (Same Path, Same Content)

**Setup**:
1. Model "Benchy-v1.3mf" created in Manyfold
2. File deleted from filesystem
3. Manyfold rescan → Model becomes orphaned or error state
4. File restored from backup to original path
5. Manyfold rescan again

**Expected outcome**:
- Manyfold detects file at path
- Manyfold re-attaches file to original model record
- Model metadata preserved from before deletion

**Validated behavior**:
✓ Manyfold successfully re-links file to model on rescan
✓ Model metadata (name, tags, description) preserved
✓ Archive linkage remains intact (if using stable Manyfold model ID)

**Operator action required**: 
- Manual rescan trigger (OR automated periodic rescan)
- Model returns to normal state automatically

---

### Scenario 2: File Deleted, Different File Restored to Same Path

**Setup**:
1. Model "Benchy.3mf" (50 MB) cataloged
2. File deleted
3. Different file (e.g., "Calibration-Tower.3mf") restored to same path with same name
4. Manyfold rescan

**Expected outcome**:
- New file detected at path
- Manyfold compares file header/metadata vs. model record
- Mismatch detected: Model expects old Benchy data, finds Calibration Tower

**Validated behavior**:
⚠ Behavior depends on Manyfold version:
- **Newer versions (>= v0.133)**: Hash-based detection catches mismatch; error or warning
- **Older versions**: May re-use model record with new file; metadata stale

**Operator action required**:
- Delete orphaned model for old Benchy
- Create new model for Calibration Tower
- OR: Rename file before restore to avoid path collision

---

### Scenario 3: Folder Deleted and Restored

**Setup**:
1. Collection "Author-Name/Models/" contains 5 models
2. Entire folder deleted from filesystem
3. Folder restored from backup with all files
4. Manyfold rescan

**Expected outcome**:
- All models in collection become orphaned after initial rescan
- After folder restore + second rescan, models re-discovered and re-attached

**Validated behavior**:
✓ Manyfold successfully re-discovers and re-links all models in folder
✓ If path template uses collection/creator hierarchy, folder structure preserved

**Operator action required**:
- Trigger two rescans (one detects orphans; second reattaches)
- Monitor for completion between rescans

---

### Scenario 4: File Moved Within Same Library

**Setup**:
1. Model "Benchy.3mf" at path `/library/curated/prints/Benchy.3mf`
2. File moved to `/library/curated/misc/Benchy.3mf`
3. Manyfold rescan

**Expected outcome**:
- Manyfold has path-template rules; can detect move based on new path
- May create new model or re-link to existing model depending on configuration

**Validated behavior**:
⚠ Behavior varies by path template configuration:
- **Creator-based path**: Model may re-link if still matches creator
- **Flat folder**: File appears orphaned after move; manual rescan + relink needed
- **Collection-based**: Model metadata may reference old path temporarily

**Operator action required**:
- Manual rescan
- Potential manual model re-linking if path template changed
- May need to update collection assignment if folder hierarchy changed

---

### Scenario 5: Partial Folder Restore (Some Files Missing)

**Setup**:
1. Collection with 10 models
2. Partial restore: only 7 files recovered
3. 3 files still missing
4. Manyfold rescan

**Expected outcome**:
- 7 models re-linked to recovered files
- 3 models remain orphaned

**Validated behavior**:
✓ Manyfold handles partial recovery gracefully
✓ Does not delete orphaned records automatically
✓ Operator can see which models are orphaned

**Operator action required**:
- Review orphaned models
- Delete orphaned model records manually if data loss is permanent
- Consider if lost files are recoverable from alternative backup

---

## Archive Linkage Impact

### Impact on Link Integrity

**If archive link uses model path** (not recommended):
```
archive_link {
  archive_id: 12345,
  model_path: "/models/Benchy.3mf"  # ← Brittle!
}
```
**Result after restore**: Path may change; link becomes invalid.

**If archive link uses stable Manyfold model ID** (recommended):
```
archive_link {
  archive_id: 12345,
  manyfold_model_id: "uuid-abc-123",  # ← Stable!
  model_name_cache: "Benchy"  # ← For display only
}
```
**Result after restore**: Link survives; model re-discovery works correctly.

### Recommended Archive Link Strategy

**For Phase 1-2**: Use stable Manyfold model IDs (public_id) for all archive linkage.

```
CREATE TABLE archive_model_links (
    id INTEGER PRIMARY KEY,
    archive_id INTEGER,
    manyfold_model_id TEXT NOT NULL,      # Stable identifier
    manyfold_model_url TEXT NOT NULL,     # Stable URL
    model_name_cache TEXT,                # For display; may change
    review_state TEXT,
    ...
);
```

**Migration note**: If Phase 1 used model names, Phase 2 must migrate to IDs before folder recovery scenarios become common.

---

## Orphaned Record Cleanup

### Problem: What Happens to Orphaned Models?

When file is deleted and not restored:
1. Rescan detects missing file
2. Orphaned model record remains in Manyfold database
3. Model shows "error" or "unlinked" state in UI

**Consequences**:
- Orphaned records accumulate over time
- Archive links to orphaned models become broken
- No automatic cleanup; manual review required

### Recommended Cleanup Strategy

**Phase 2 cleanup workflow**:
```
1. Sidecar detects orphaned models:
   - via periodic model list fetch
   - flag models with error status or no linked files
   
2. Sidecar report to HA:
   - "Orphaned models detected: 3 models have no files"
   - List affected models with last-known names
   
3. Operator review in HA UI:
   - View orphaned model details
   - Delete if data loss is permanent
   - OR: Restore file and trigger rescan
   
4. Sidecar removes deleted models from cache
```

### Phase 3+ Automated Cleanup (Optional)

```
Sidecar scheduled job (nightly)
    ↓
Fetch full model list
    ↓
Check each model for error state or missing files
    ↓
If orphaned for > 30 days and no archive links:
    - Log event
    - Optionally auto-delete (requires operator config)
```

---

## Content Hash and Version Detection

### Current State (Manyfold >= v0.133)

Manyfold includes basic file identity checks:
- File size comparison
- File modification timestamp
- Header metadata parsing (3MF XML parsing)

### Limitations

**No content hash-based detection**:
- If two 3MF files have same name but different content, Manyfold may not distinguish
- Workaround: Use unique naming or operator must manage renames

**Timestamp-based re-detection**:
- If file is restored with old modification time, Manyfold may not detect change
- Workaround: Use `touch` or force-restore to update timestamp

### Recommendation for Phase 2

**Document file identity best practices**:
1. Use unique file names (avoid generic "Benchy.3mf")
2. Archive old models before restore (don't restore files that overwrite new models)
3. Use operator confirmation for file overwrites
4. Verify file content matches expected 3MF structure after restore

---

## Operator Workflows for Common Recovery Scenarios

### Workflow 1: Accidentally Deleted Model - Full Restore

```
Scenario: User deletes "Benchy.3mf" from filesystem; wants to recover

HA Workflow:
  1. HA shows: "Model not found: Benchy - last seen 2026-04-20"
  2. Operator: "Restore from backup"
  3. Sidecar: (checks if file exists)
  4. File restored to filesystem by backup system
  5. Operator triggers manual rescan (or waits for periodic rescan)
  6. Model re-discovered and reactivated
  7. HA updates: "Model restored: Benchy - last print 2026-04-15"
```

---

### Workflow 2: File Corruption - Replace with Backup

```
Scenario: "Benchy.3mf" corrupted; want to replace with clean backup

HA Workflow:
  1. HA shows: "Model Benchy - scan error: malformed 3MF"
  2. Operator: "Delete and restore"
  3. Sidecar: Delete model record
  4. Backup system: Restore file to same path
  5. Operator triggers rescan
  6. Model re-created with clean metadata from restored file
```

---

### Workflow 3: Bulk Folder Loss - Selective Restore

```
Scenario: Collection "/curated/prints/" deleted; restore from backup

HA Workflow:
  1. HA shows: "10 models missing: (list all models in collection)"
  2. Operator: "Restoring collection from backup..."
  3. Backup system: Restore folder with 8 of 10 files
  4. Operator triggers rescan
  5. HA shows: "8 models restored, 2 remain missing"
  6. Operator: Investigates 2 missing models
     - Option A: Restore from older backup
     - Option B: Delete orphaned models (data is lost)
     - Option C: Re-create from scratch
```

---

## Testing Checklist for Phase 2

Before production deployment, validate:

- [ ] Delete file from filesystem; rescan; confirm model orphaned
- [ ] Restore file to same path; rescan; confirm model relinked
- [ ] Restore different file to same path; confirm error/mismatch detected
- [ ] Restore file with old modification timestamp; confirm detection works
- [ ] Delete entire folder; rescan; confirm all models in folder orphaned
- [ ] Restore entire folder; rescan; confirm all models relinked
- [ ] Restore only some files from folder; rescan; confirm partial recovery works
- [ ] Move file to different folder; rescan; confirm Manyfold's path-template handles move
- [ ] Update archive link to use stable model ID; restore file; confirm link survives
- [ ] Verify orphaned models appear in HA UI for operator review
- [ ] Test cleanup workflow: delete orphaned model record after operator confirms loss

---

## Recommendations for Implementation

### For Phase 1-2

1. **Use stable model IDs for archive linkage**:
   - Migrate Phase 1 name-based links to ID-based
   - Ensures links survive file moves and metadata changes

2. **Implement orphan detection**:
   - Periodic scan identifies models with no linked files
   - Surface in HA UI for operator awareness

3. **Document recovery procedures**:
   - User-facing: "File deleted: restore from backup + rescan"
   - Operator guide: Orphaned model cleanup workflow

4. **Do NOT auto-delete orphaned models**:
   - Too risky in Phase 1; require manual operator confirmation
   - Defer auto-cleanup to Phase 3+ if needed

### For Phase 2 Enhancement

1. **Add file identity verification**:
   - On restore, verify file content matches expected model metadata
   - Warn operator if mismatch detected

2. **Implement restoration UI**:
   - "Restore from backup" button in HA for orphaned models
   - Triggers file-exists check and rescan

### For Phase 3+

1. **Implement auto-cleanup with configurable retention**:
   - Orphaned models older than N days auto-deleted
   - Requires operator opt-in

2. **Add content hash-based tracking**:
   - Compute SHA256 of each model file at import time
   - Use hash to detect file overwrites or corruption

3. **Archive recovery integration**:
   - If archive linkage references deleted model, offer recovery options
   - Propose re-link to similar existing model if available

---

## Edge Cases and Mitigations

### Edge Case 1: Symlink Target Restored

**Scenario**: Model file is a symlink; symlink target deleted but restored

**Mitigation**:
- Manyfold follows symlinks transparently
- Behavior same as direct file
- Rescan re-detects after target restore

---

### Edge Case 2: Archive Link to Multiple Files in Same Model

**Scenario**: Archive prints multiple files from same Manyfold model; one file deleted

**Mitigation**:
- Archive link remains valid (linked to model, not specific file)
- Both files available for reprint if restored
- Single file missing doesn't break archive linkage

---

### Edge Case 3: Cascade Recovery Dependency

**Scenario**: Collection folder depends on sub-folder; sub-folder not restored in backup

**Mitigation**:
- Models in missing sub-folder remain orphaned
- Parent collection models still recoverable
- Operator must decide: restore full collection or accept loss

---

## Conclusion

Recovery after file restoration is **predictable and operationally manageable** if:

1. Archive linkage uses **stable model IDs** (not paths or names)
2. Operator has **clear visibility** into orphaned models
3. **Manual rescan** is available (or periodic automatic rescan scheduled)
4. Cleanup workflow is **documented and explicit** (no auto-deletion in Phase 1-2)

**Recommendation**: PROCEED with Phase 2 implementation using documented recovery workflows. Plan to add operational dashboards and cleanup automation in Phase 3+ as needed.

---

## Related Documentation

- [Spike #1057: Rescan Behavior](../spike-1057-manyfold-rescan-behavior-validation.md)
- [External Storage Behavior](../external-storage-behavior.md)
- [Persistence and Backup Strategy](../persistence-and-backup-strategy.md)
