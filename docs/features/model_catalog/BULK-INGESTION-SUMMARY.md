# Model Catalog Review — Quick Summary

## 2026-04-29 Post-Manyfold Note

This document captures the original Phase 1.5 bulk-ingestion rationale.

- References below to uploading into Manyfold reflect the pre-transition design baseline.
- The active migration direction now keeps bulk discovery/import, queue persistence, and allowlisted source browsing as valid intake primitives while retiring Manyfold from the authoritative operational path.
- See `post-manyfold-transition-plan-2026-04.md` for the current phase mapping and destination model.

## 2026-04-26 Design Revision Note

The Phase 1.5 design has been revised to support remote-client workflows:

- Browser-selected local files can be uploaded to a sidecar intake queue.
- Sidecar-mounted server files can be browsed/selected from allowlisted roots.
- Both source modes feed a single review/import queue.
- Import processing uploads files to Manyfold through API-managed storage.
- Optional post-upload source policy supports `keep` (default), `delete_on_verified`, and `replace_with_stub`.
- Destructive source actions are gated on verified upload and allowlisted-root safety checks.

## Your Question

You asked whether the Model Catalog design accounts for:
1. **Bulk ingestion** of 500+ existing 3MF files with mixed organization
2. **Project relationships** for multiple related 3MF files
3. Whether "Grouping" from Working Files can carry through to curated catalog

## Answer: Partial, But Critical Gaps Identified

| Feature | Status | Assessment |
|---------|--------|-----------|
| **Working Groups** (logical grouping outside Manyfold) | ✅ Designed | Good foundation for your use case |
| **Bulk file discovery & import** | ❌ **Missing** | No workflow for "discover 500 files and group them" |
| **Project concept in Model Catalog** | ❌ **Missing** | Projects exist only in Print History / Bambuddy, not in Model Catalog |
| **Metadata enrichment (bulk)** | ⚠️ **Partial** | Single-file enrichment designed; no bulk workflow articulated |
| **Cross-system project navigation** | ❌ **Missing** | No linkage between Model Catalog projects and Print History projects |
| **Related model patterns** | ⚠️ **Implicit** | Manyfold supports multiple files per model, but not as a "family" concept |

## Key Gaps

### Gap 1: Bulk Ingestion Workflow
**Problem**: Design assumes one Working group at a time. No documented path for discovering and grouping 500+ files.

**Impact**: You'd be manually creating 20-50 working groups by hand.

**Recommendation**: Add Phase 1.5 with:
- Bulk-discover endpoint: scan folder, propose groups
- Bulk-import endpoint: create multiple working groups at once
- Deduplication and conflict detection
- HA UI for review before commit

---

### Gap 2: Project Concept Not Unified
**Problem**: 
- Print History has "projects" (for organizing archives)
- Model Catalog has "Working groups" (for organizing work-in-progress)
- Curated models have no project relationship
- No way to say "these N files belong to one project family"

**Current state**:
```
Print History Project
  └─ Archives (print outcomes)

Model Catalog Working Groups
  └─ Files (in-progress)

Manyfold Models
  └─ (no project concept)
```

**Impact**: You cannot organize "3 variants of the same screwdriver" as a logical unit that spans Working files, curated models, AND print history.

**Recommendation**: Add Model Catalog project model (sidecar-owned):
- Connects working groups + curated models + (optionally) Bambuddy projects
- Lets you say "this project has 2 working-group variants and 1 curated model"
- Enables unified project views in HA across all three zones

---

### Gap 3: Bulk Metadata Enrichment
**Problem**: Phase 3 defines taxonomy (colors, tags) but assumes manual entry. No bulk color extraction or tag assignment.

**Impact**: For 500 files, you'd manually assign colors and tags to each one (or each working group).

**Recommendation**: Add Phase 3.5 with:
- 3MF file analysis for color extraction
- Tag suggestion from folder names or filenames
- Bulk enrichment review and approval
- Async processing for large batches

---

### Gap 4: Grouping Doesn't Carry to Curated
**Problem**: You're asking if "Grouping" from Working files carries to the curated catalog. Answer: **not yet**.

**Current**:
- Working groups are logical and flexible
- When you publish to Manyfold, you publish files, not groups
- Curated models have no group/project reference

**Recommendation**: Add project_id to curated model metadata (sidecar-owned, not in Manyfold) so:
- Published models remember which project they came from
- You can later see all related variants/files together

---

## Three Important Design Concepts

### 1. Three Storage Zones (Current ✅)
```
Working Files          Curated Catalog    Print History
(sidecar-owned)       (Manyfold-owned)   (Bambuddy-owned)
└─ Logical groups     └─ Models, tags    └─ Archives, projects
   (not in Manyfold)     (long-lived)       (runtime outcomes)
```

### 2. Three Model Organization Patterns (New)

**A. Model Variants** — One curated model, multiple files
- Example: "Screwdriver base + handle + stand" (all parts of one assembly)
- Store in: One Manyfold model with multiple files attached

**B. Model Family / Project** — Multiple curated models grouped by project
- Example: "Desk accessories project" (organizer + screwdriver + wrench + stand)
- Store in: Multiple Manyfold models, linked by Model Catalog project

**C. Remix/Derivative** — One curated model with reference to source
- Example: "My remix of [designer]'s screwdriver"
- Store in: One Manyfold model with remix_source metadata

### 3. Project Ownership Recommendation

**Model Catalog projects** should be sidecar-owned because:
- Allows linking working groups + curated models + archives
- Doesn't require changes to Manyfold or Bambuddy
- Can evolve without upstream constraints
- Keeps projects out of Manyfold (respecting its current capabilities)

---

## Your Scenario: What Happens With Proposed Enhancements

### Today (Without Enhancements)
```
~/3D Printing/Tools/
├── screwdriver_base.3mf
├── screwdriver_handle.3mf
├── screwdriver_stand.3mf
└── wrench_v1.3mf

Workflow:
1. Manually create Working group "Tools"
2. Manually add each file
3. Manually extract and assign colors/tags
4. Manually publish to Manyfold
5. Manually link archives to curated models
```

### With Phase 1.5 & 3.5 Enhancements
```
~/3D Printing/Tools/
├── screwdriver_base.3mf
├── screwdriver_handle.3mf
├── screwdriver_stand.3mf
└── wrench_v1.3mf

Workflow:
1. HA Service: bulk_discover(folder_path, strategy="by-folder")
   → Auto-proposes "Tools" group with 4 files
2. Review & approve
3. HA Service: bulk_import(groups=[Tools])
   → Creates working group in seconds
4. HA Service: bulk_analyze(groups=[Tools])
   → 3MF analysis extracts colors, proposes tags
5. Review & approve enrichment
6. HA Service: bulk_enrich(enrichments=[...])
   → Applies colors and tags in bulk
7. Publish to Manyfold (one at a time, but metadata pre-filled)
8. Create Model Catalog project "Desk Accessories"
   → Links working group + curated models
9. Archives auto-link to curated models when printed
   → Can navigate: Archive → Model → Project → Related Groups
```

**Time saved**: Hours to days of manual clicking.

---

## Recommendations: Priority Order

### High Priority (Do Before Phase 1 Ships)
1. **Articulate bulk-ingest workflow** (Phase 1.5 design)
   - How to discover and group 500+ files efficiently
   - File deduplication and conflict handling
   
2. **Define Model Catalog project model** (Phase 4-5 enhancement)
   - Sidecar-owned project entity
   - Linkage to working groups, curated models, archives

3. **Define cross-feature contracts** (Phase 10 enhancement)
   - Archive → Model → Project → Working Group navigation
   - Print History project ↔ Model Catalog project linkage (optional)

### Medium Priority (Add to Phase 3)
4. **Bulk metadata enrichment** (Phase 3.5)
   - 3MF color extraction
   - Tag suggestion from filesystem structure
   - Bulk approval workflow

### Lower Priority (Can Defer)
5. Clarify model-family vs variants patterns (documentation)
6. Extended Manyfold API gap analysis (phase 10+)

---

## Next Steps

### For You (Immediate)
- [ ] Review the full assessment at `docs/features/model_catalog/bulk-ingestion-and-projects-assessment.md`
- [ ] Validate the "by-folder" bulk-discover strategy against your actual folder organization
- [ ] Confirm project ownership preference (sidecar vs Bambuddy vs hybrid)
- [ ] Decide which metadata signals matter most: colors, tags, or both?

### For Implementation Planning
- [ ] Add Phase 1.5 (bulk ingest) to the implementation roadmap
- [ ] Add Phase 3.5 (bulk enrichment) to Phase 3
- [ ] Add project model design to Phase 4-5
- [ ] Create cross-feature contract document

---

## Bottom Line

**The Working Group concept is solid and handles your grouping need well.** But the design assumes you're adding files one group at a time, not importing 500 files at once. 

**The main missing pieces are:**
1. **Bulk discovery & import workflow** (efficiency gap)
2. **Project as a shared concept** (organizational gap)
3. **Bulk metadata enrichment** (time-saving gap)

**With Phases 1.5 & 3.5 (new) added to the roadmap, your bulk-ingest scenario becomes practical.**

The assessment document provides detailed design proposals for all three gaps, including implementation examples and risk mitigations.

