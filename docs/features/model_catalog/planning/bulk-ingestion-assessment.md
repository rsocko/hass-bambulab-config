# Model Catalog — Bulk Ingestion & Project Relationship Assessment

> **Status**: Historical design assessment and recommendations.
> **Created**: 2026-04-24
> **Scope**: Evaluation of bulk-ingestion workflows for large existing 3MF collections and project-relationship patterns across Model Catalog, Print History, and Manyfold.
> **Superseded by**: [../design/catalog-redesign-2026-05.md](../design/catalog-redesign-2026-05.md) for the active Projects/Collections IA and [../design/projects.md](../design/projects.md) for archived project-specific rationale.

## Post-Manyfold Status Note

This assessment predates the approved post-Manyfold phase renumbering.

- Legacy `Phase 1.5` bulk-ingest recommendations now map to current **Phase 5**.
- Legacy `Phase 3.5` bulk-enrichment recommendations now map primarily to current **Phase 6**.
- Legacy `Phase 10` project/navigation recommendations now map to current **Phase 9**.
- References below to Manyfold as an active curated destination reflect the pre-pivot baseline and should be read as historical context unless explicitly marked as optional adapter work.

---

## Executive Summary

The current Model Catalog design acknowledges bulk acquisition through the **Working Group** concept and the **Phase 1-2 candidate-discovery path**, but **the articulated workflows do not yet fully account for your specific bulk-ingestion scenario** where you have:

1. **Large existing collections** (hundreds of `.3mf` files)
2. **Mixed organization** (some in root folder, many in subfolders organized by project)
3. **Logical grouping needs** (multiple 3MF files that belong to a single project or model-family)
4. **Unknown metadata state** (no catalog yet; need efficient discovery and enrichment)

Additionally, **the "project" concept currently exists only in Print History (Bambuddy archives)** and is not yet integrated with Model Catalog's design. There is no unified **project identity** that spans both Working files and curated models.

### Key Findings

| Aspect | Current State | Gap | Risk Level |
|--------|---------------|-----|-----------|
| **Bulk file discovery and intake** | Working veneer supports logical grouping independent of folders | No unified intake queue or batch ingest workflow articulated | Medium |
| **Project relationship** | Defined only in Print History / Bambuddy archives | Not mirrored to Model Catalog or Working files | High |
| **Metadata enrichment** | Phase 3-4 plan assumes one file at a time | No bulk metadata ingestion or enrichment workflow | Medium-High |
| **Duplicate handling** | Working-side duplicate detection exists for re-downloads | Does not handle "same model, multiple versions" or "related models in same project" | Medium |
| **Cross-system project linkage** | Print History → Archive → Project exists | No Model Catalog ↔ Working Group ↔ Print History Project linkage | High |
| **Manyfold API coverage** | CRUD and upload supported | No bulk ingest, library scan, or path-template admin via API | Medium |

---

## Current Architecture Review

### What Exists (Well-Articulated)

1. **Working Groups** — Logical grouping outside Manyfold ✅
   - Can group multiple files as a related work item
   - Folder structure is optional (logical grouping primary)
   - Supports supporting assets (SVG, PDF, notes, screenshots)
   - Planned fields: `id`, `title`, `slug`, `notes`, `stage`, `primary_file_path`, `source_urls`, `related_manyfold_model_id`

2. **Single-File Publish Flow** — Working → Catalog ✅
  - Described in [Workflow And Ingestion Guide](../reference/workflow-ingestion.md)
   - Publish to catalog when stable
   - Canonical revision tracking planned
   - Reconciliation checks for duplicates

3. **Archive Linkage** — Bambuddy Archive → Curated Model ✅
   - Archive popup allows linking to Manyfold model
   - `project_id` can be assigned to archives from popup
   - Print History has `project_name` / `project_id` filter and display

4. **Three-Zone Model** — Working | Curated | Archive ✅
   - Clear separation of concerns
   - Working outside Manyfold by default
   - Bambuddy as archive authority

### What Is Missing (Gaps)

1. **Bulk Ingest And Intake Workflow** ❌
  - No documented path for "quick send this file into review" from the filesystem
   - No documented path for "I have 500 files and want to organize them into 20-50 Working groups"
   - No batch discovery or grouping recommendation
   - No bulk metadata scraping or enrichment
   - Phase 1-4 assume one Working group at a time

2. **Project as a First-Class Cross-System Concept** ❌
   - "Project" exists only in Print History / Bambuddy
   - Model Catalog has no native project concept
   - Working Groups are not projects; they are work-in-progress groupings
   - Curated models have no project relationship field
   - Print History projects cannot reference related Working groups or curated models

3. **Related Models Pattern** ❌
   - No support for "N versions of the same base model" as a family
   - No support for "M models that belong to one project" (distinct from duplicates)
   - Working groups are work-centric; curated models are model-centric
   - Bambuddy projects organize print archives, not model variants

4. **Bulk Metadata Workflows** ❌
   - No batch color extraction from 3MF files
   - No bulk tag assignment
   - No bulk category or collection assignment
   - Phase 3 taxonomy fields exist but no bulk-ingest path

5. **Manyfold Library Admin via API** ❌
   - No REST endpoint for library create/scan
   - No path-template preview via API
   - No bulk add-to-collection or tag operations
   - Derivative settings not exposed via API

---

## Your Specific Use Case — Gap Analysis

You are asking: **"I have 500+ existing `.3mf` files, mostly organized in subfolders by project. How do I efficiently add them to the catalog with proper grouping, metadata, and later print linkage?"**

### Phase: Discovery & Organization

**What you need:**
- Scan a folder tree (e.g., `~/3D Printing/`)
- Group files logically by folder/project
- Preview which files belong together
- Create Working groups in bulk or semi-bulk
- Optional: guess metadata from folder names or filenames

**What exists:**
- Working veneer supports logical grouping ✅
- Sidecar can ingest filesystem and infer groups ✅
- Working groups can link to optional folder hint ✅

**What is missing:**
- No batch filesystem scan and Working-group creation flow articulated
- No bulk grouping recommendation algorithm
- No folder-to-group inference rules documented
- No HA service or UI for "import Working groups from a folder tree"

### Phase: Metadata Enrichment

**What you need:**
- Extract colors from 3MF files (bulk)
- Assign tags from folder structure or filename patterns
- Optionally scrape external sources (Printables, Makerworld)
- Bulk apply category or collection to related models

**What exists:**
- Phase 3 carries `colors_used` as hex field ✅
- Phase 6 plans 3MF enrichment (photo upload, asset extraction) ✅
- Custom fields schema allows extensibility ✅

**What is missing:**
- Bulk 3MF color extraction not described
- No batch tag assignment workflow
- No bulk provenance capture (e.g., "found in folder X, no known source")
- No relationship between Working metadata and curated model metadata carry-forward

### Phase: Grouping Related Models

**What you need:**
- Group multiple 3MF files that form a project family (e.g., "base model + 3 variants")
- Later reference that family as a unit in print history
- Optionally curate them together or separately

**What exists:**
- Working groups support multiple files ✅
- Working-group `related_manyfold_model_id` points to curated equivalent ✅
- Print History has `project_id` field ✅

**What is missing:**
- No concept of "a curated model with multiple variant files" (Manyfold supports this at file level, but not as a first-class project concept)
- No forward reference from curated model back to Working group for ongoing editing
- Print History project cannot link to both curated model AND related working variants
- No "project" concept in Model Catalog that can bundle related curated models

---

## Print History / Bambuddy "Project" Concept

Print History already has a working project concept. Let's clarify what it is and is not:

### Current Print History Project Behavior

- **Owned by**: Bambuddy (via `/api/v1/projects/` endpoint)
- **Scope**: Archive-level (print outcomes)
- **Fields**: `project_id`, `project_name` in archive records
- **Usage**: Archives can be assigned to a project; projects appear as a filter in print browser
- **Lifecycle**: Created in Bambuddy; linked from HA archive popup
- **Metadata**: Minimal (just a name and ID; no relationships to models or working files)

### What It Cannot Do Today

- Link to a curated Manyfold model
- Link to Working groups
- Aggregate related 3MF files under one project family
- Serve as the organizing principle for the model catalog

### Design Consequence

The term "project" means different things in different parts of your system:

- **Print History**: "Which set of prints belong together" (a backlog/collection of completed or queued prints)
- **Your 3D files**: "Which source models/variants belong to a design family" (a design/authoring concept)
- **Working groups**: "What work am I doing right now" (a temporal/operational concept)

These are related but not identical.

---

## Recommended Changes to Model Catalog Design

### 1. Articulate Intake And Bulk-Ingestion Workflow (Phase 1.5 - New)

**Outcome**: Operators can efficiently submit ad hoc files into a review queue and populate Working groups from an existing folder tree.

**Approach**:

Add to the implementation plan:

```
### Phase 1.5: Intake Inbox, Bulk Discovery & Working-Group Creation

Outcome:
- Ad hoc files can be submitted into a reviewable Inbox
- Working groups can be populated from filesystem scan
- Browser-local uploads and server-side file selections converge into one queue pipeline
- Imported files are committed into Manyfold-managed storage via API, not path-only sidecar references
- Folder-to-group mapping can be configured or inferred
- Bulk grouping workflow exists in HA and sidecar

Work items:

1. Add sidecar endpoint: `POST /intake/submit`
  - Input: one or more paths plus source hint
  - Output: Intake Inbox items with validation results and duplicate hints
  - Keep items in Inbox until operator groups, rejects, or deliberately publishes them

1a. Add queue upload and source-browse contracts:
  - Browser local files: multipart upload endpoint for queue staging
  - Server sidecar mounts: browse/select endpoints constrained to allowlisted roots
  - Source list supports explicit files, folders, or mixed file+folder batches
  - Folder sources support `recurse` true/false
  - One normalized queue status model for both sources

2. Add sidecar endpoint: `POST /working-groups/bulk-discover`
   - Input: folder path, grouping strategy
   - Grouping strategy options:
     a. "by-folder" — each subfolder becomes a working group
     b. "by-root" — all files in root + immediate subfolders, one group per subfolder
     c. "flat" — all files in one group (not recommended for 500+ files)
   - Output: list of proposed working groups with file lists
   - Review before commit (do not auto-create)

3. Add sidecar endpoint: `POST /working-groups/bulk-import`
  - Input: list of reviewed groups or inbox items (name, files, folder_hint, optional stage)
   - Create all Working groups and file entries in batch
   - Deduplicate against existing Working groups by filename hash
   - Upload selected files to Manyfold via API and persist resulting Manyfold references
   - Output: created group IDs and summary

3a. Add optional post-upload source policy:
  - `keep` (default)
  - `delete_on_verified`
  - `replace_with_stub`
  - Run only after successful upload and verification checks (hash preferred)
  - Restrict destructive actions to configured allowed roots

4. Add HA automation/script:
  - Expose service to submit items to Inbox
  - Expose service to trigger bulk discover
  - Expose service to trigger bulk import
  - Card in HA to review Inbox items and approve proposed groups before import

5. Add sidecar Working-group and Intake fields to support:
   - `folder_hint` — the original filesystem folder(s) for reference
   - `file_hashes` — MD5 or SHA-256 of contained files for duplicate detection
   - `discovery_metadata` — "imported from folder X at time Y" provenance
    - `inbox_state` — pending/triaged/grouped staging state

6. Document folder-organization patterns:
   - "One folder per model" → one group per subfolder ✅
   - "Subfolders by model family, files are variants" → one group per subfolder ✅
   - "Flat root with hundreds of files" → need file-naming patterns or manual curation
   - "Mixed depth with projects as top-level folders" → can use "by-folder" strategy
    - "Quick-send from Explorer/Stream Deck" → lands in Inbox first, then operator decides Working vs direct publish

**Deliverables**:
- intake endpoint and Inbox review flow
- bulk-discover endpoint and HA flow
- bulk-import endpoint and error handling
- Working-group import UX in HA
- Documentation of folder-scanning best practices
```

This phase should treat direct-to-Manyfold upload as an exception path for already curated-quality files, not as the default intake baseline.

### 2. Introduce "Project" as a Shared Concept (New Layer)

**Problem**: Right now, "project" exists only in Print History. Your 3MF files and Working groups have no project concept.

**Recommendation**: Create a **Model-Catalog-owned project abstraction** that can link Working groups, curated models, and archives together.

**Approach**:

Add a new `project` entity to the Model Catalog sidecar:

```
### Project Data Model (Sidecar-Owned)

A project is a logical grouping of:
- related Working groups (in-flight versions)
- one or more curated Manyfold models (stable versions)
- optional Bambuddy project reference (for print outcomes)
- optional external source or design origin

Fields:
- `id` (UUID)
- `title` (human readable)
- `slug`
- `description`
- `origin` (e.g., "MakerWorld", "Printables", "Custom", "Unknown")
- `origin_url` (optional)
- `working_group_ids` (list of related in-flight groups)
- `curated_model_ids` (list of related stable Manyfold models)
- `bambuddy_project_id` (optional reference to Print History project)
- `project_type` (e.g., "model_family", "remix_set", "author_collection")
- `created_at`, `updated_at`

Relationships:
- One project can have N working groups
- One project can have N curated models
- One project can have 0-1 Bambuddy project (print outcomes)
- Working groups or models without a project remain valid
```

**Integration Points**:

1. **Working Groups** ← can belong to a project (optional `project_id` field)
2. **Curated Models** ← can belong to a project (optional `project_id` in sidecar metadata)
3. **Bambuddy Projects** ← can be linked from Model Catalog projects for archive navigation
4. **Print History** ← can reference both the print project AND the model project
5. **HA Surfaces** ← can filter/organize by project across all zones

**Design Consequence**: This keeps the project concept *out of Manyfold's core* (respecting its current capabilities) while still making it first-class in your Model Catalog and Print History navigation.

### 3. Define Multi-File Model Patterns (Clarification)

**Current State**: Manyfold supports multiple files per model (e.g., STL + Gcode variants), but there's no documented pattern for "variants of the same design".

**Recommendation**: Clarify three supported patterns:

**Pattern A: Model Variants (One Curated Model, Multiple Files)**
- Example: "Base model" + "Reduced infill version" + "Tall variant"
- Store in: One Manyfold model with multiple attached files
- Working representation: One Working group with multiple primary files
- Project reference: Optional; not required
- Use case: "I want to reprint this specific variant"

**Pattern B: Model Family (One Project, Multiple Curated Models)**
- Example: "A letter holder" + "A letter holder desk stand" + "A letter holder wall mount"
- Store in: Multiple Manyfold models, linked by project
- Working representation: Multiple Working groups or one group with multiple files, all in one project
- Project reference: Required; project_id shared across models
- Use case: "I want to reprint the whole collection together"

**Pattern C: Remix/Derivative (One Curated Model, Reference to Source)**
- Example: "Remixed version of <designer>'s model"
- Store in: One Manyfold model with `remix_source` metadata pointing to origin
- Working representation: One Working group
- Project reference: Optional; may belong to a project if multi-variant remix
- Use case: "I remixed something and want to track it with the original"

**Design Consequence**: These patterns are mutually exclusive for a given model. Working groups and bulk-ingest workflows should be designed with these patterns in mind.

### 4. Extend Bulk Metadata Ingestion (Phase 3-4 Refinement)

**Current State**: Phase 3-4 assume manual metadata enrichment; Phase 6 addresses photo/asset extraction but not bulk color or tag assignment.

**Recommendation**: Add a **bulk metadata enrichment workflow** before or after bulk Working-group creation.

**Approach**:

```
### Bulk Metadata Ingestion Sub-Phase (Phase 3.5)

Outcome:
- bulk color extraction from 3MF files
- bulk tag assignment from folder structure or file naming
- bulk provenance capture
- preview before commit

Work items:

1. Add 3MF parser integration to sidecar
   - Extract model dimensions, material slots, color information
   - Cache in SQLite with file hash as key
   - Support background/async processing for large batches

2. Add sidecar endpoint: `POST /working-groups/bulk-analyze`
   - Input: list of working group IDs
   - Process all files in groups
   - Extract colors, dimensions, material info
   - Propose tags from folder structure or naming patterns
   - Output: list of proposed enrichments with confidence scores

3. Add sidecar endpoint: `POST /working-groups/bulk-enrich`
   - Input: list of enrichments (with operator approval)
   - Apply colors, tags, and metadata in bulk
   - Track enrichment source for later audit

4. Add HA card for bulk enrichment review:
   - Show proposed colors for each group
   - Show proposed tags with confidence
   - Allow operator to override or skip individual items
   - Batch apply after review

5. Document tag-assignment heuristics:
   - Folder name → tag (e.g., "tools" folder → "tools" tag)
   - Filename pattern → category (e.g., "base_v1.3mf" → "base" tag)
   - Color extraction confidence levels

**Deliverables**:
- 3MF analysis service in sidecar
- bulk-enrich endpoints and error handling
- HA enrichment review card
- Documentation of tag/category heuristics
```

**Design Consequence**: This makes bulk ingestion more productive without forcing manual one-by-one enrichment.

### 5. Clarify Cross-Feature Data Contracts (New)

**Current State**: Model Catalog, Print History, and Bambuddy have separate data models; project linkage is undefined.

**Recommendation**: Add a new design document: **[Cross-Feature Project & Variant Linkage Contract](/docs/features/model_catalog/design/manyfold-bambuddy-linkage.md)** (to be created).

**Key Contracts**:

```
### Archive ↔ Curated Model ↔ Working Group ↔ Project Navigation

Scenario 1: "I just printed something and want to find the source model or working variants"
- Archive has: project_id (Bambuddy), optional source_3mf path
- Archive links to: curated Manyfold model via sidecar linkage DB
- Model can link back to: Model Catalog project (if curated as part of project)
- Project contains: related working groups for ongoing editing

Scenario 2: "I have a Working group and want to see related prints"
- Working group has: optional project_id (Model Catalog)
- Project links to: Bambuddy project (print outcomes)
- Bambuddy project contains: all archives with project_id

Scenario 3: "I'm curating a model family and want to track all the files and prints"
- Model Catalog project: one project, N working groups, N curated models
- Bambuddy project: zero or one (optional reference)
- HA surface: cross-links all related items in a unified project view

Storage:
- Project ownership: Model Catalog sidecar (not Manyfold, not Bambuddy)
- Project references: 
  - Working group → project_id (Model Catalog)
  - Curated model → project_id (Model Catalog sidecar metadata, not Manyfold)
  - Bambuddy project → optional model_catalog_project_id (Bambuddy API extension or HA-managed cross-reference)
  - Archive → project_id (Bambuddy native)

Query paths:
- "Give me all working groups in this project" → Model Catalog sidecar query
- "Give me all curated models in this project" → Model Catalog sidecar query
- "Give me all archives related to this project" → Bambuddy API + optional HA filter
- "Show me the project view" → HA aggregates all three
```

**Design Consequence**: This makes cross-system navigation explicit and operator-facing without tight coupling.

---

## Implementation Roadmap — Revised Sequencing

Current-sequence crosswalk:

- legacy `Phase 1.5` -> current `Phase 5`
- legacy `Phase 3.5` -> current `Phase 6`
- legacy `Phase 10+` -> current `Phase 9`

### Immediate (Before Phase 1 Implementation)

- [ ] **Design**: Finalize bulk-ingestion workflow (current Phase 5)
- [ ] **Design**: Define Model Catalog project model
- [ ] **Design**: Document cross-feature contracts (project + variant + archive linkage)
- [ ] **Validation spike**: Test sidecar feasibility for filesystem scanning and group inference

### Phase 1 (Unchanged, But Scoped Differently)

- Keep Phase 1 as sidecar scaffold
- Add Working-group discovery-metadata fields for audit trail
- Plan current Phase 5 as the immediate follow-up delivery slice for intake and bulk discovery/import

### Current Phase 5 (Legacy Phase 1.5)

- Implement bulk-discovery endpoint
- Implement bulk-import endpoint
- Add HA bulk-import card and workflow

### Phase 3 (Taxonomy) — Refined

- Unchanged core taxonomy
- **Add**: current Phase 6 bulk metadata enrichment work
- 3MF parsing and color extraction
- Bulk tag assignment and enrichment card in HA

### Phase 4 (Working Groups) — Unchanged

- Proceed as planned
- **Add**: Optional project_id field to Working groups
- HA board can optionally group by project

### Phase 5 (Publish) — Enhanced

- Proceed as planned
- **Add**: On publish, offer to add curated model to existing or new project
- Support creating a Model Catalog project during publish

### Current Phase 9 (Legacy Phase 10+ Project Management)

- Add sidecar project CRUD endpoints
- Implement HA project views and navigation
- Optional: surface Bambuddy project linkage

---

## Working-Groups Capability Expansion

The Working-group concept as currently designed **is sufficient for your bulk-ingestion use case**, but needs these enhancements:

### Current Working-Group Fields (Approved)

```yaml
id:                          # UUID
title:                       # Human name
slug:                        # URL-safe
notes:                       # Free text
stage:                       # draft | in_progress | needs_revision | ready_to_publish | archived
primary_file_path:           # One designated file
folder_hint:                 # Optional original filesystem path
source_urls:                 # List for external sources
related_manyfold_model_id:   # Optional curated model reference
created_at:                  
updated_at:
```

### Recommended Additions

```yaml
project_id:                  # NEW: Optional Model Catalog project reference
discovery_metadata:          # NEW: How this group was created
  imported_from_folder:      # Folder path used in bulk import
  imported_at:               # Timestamp
  discovery_strategy:        # "by-folder" | "by-root" | "manual"
file_hashes:                 # NEW: MD5 or SHA-256 of contained files for duplicate detection
files:                       # Array of file entries
  - path:
    hash:
    is_primary:
    is_supporting:           # true for SVG, PDF, notes, etc.
metadata_enrichment:         # NEW: Bulk enrichment state
  colors_proposed:           # From 3MF analysis
  colors_approved:           # Operator-approved colors
  tags_proposed:             # Suggested tags
  tags_approved:             # Applied tags
  enriched_at:               # When enrichment was applied
  enrichment_confidence:      # 0.0-1.0 score on suggestions
```

---

## Key Design Decisions Required

### 1. Project Ownership

**Question**: Should Model Catalog projects be stored in:

A) **Model Catalog sidecar (Recommended)**
   - Pro: Clear ownership; no upstream dependency on Manyfold or Bambuddy
   - Pro: Can link arbitrary external systems later
   - Pro: Easy to evolve without upstream constraints
   - Con: Adds new persistence layer

B) **Bambuddy (Alternative)**
   - Pro: Reduces silos; project is already used there
   - Con: Requires Bambuddy to understand curated models
   - Con: Would need Bambuddy enhancement to accept non-archive relationships

C) **Hybrid** (Not Recommended)
   - Pro: Reuses Bambuddy project for archive outcomes
   - Con: Creates dual project concepts; confusing

**Recommendation**: **A) Model Catalog sidecar owns Model Catalog projects.** Bambuddy projects remain archive-centric; HA can optionally link them.

### 2. Bulk Ingest Guardrails

**Question**: What safety checks should bulk-import enforce?

**Recommendation**:
- Deduplicate by file hash before import (warn if file already in another group)
- Require folder_hint or explicit source documentation
- Preview all proposed groups before committing (do not auto-create)
- Create audit trail in `discovery_metadata`
- Support rollback/delete of bulk-imported groups if needed within X hours

### 3. Cross-System Navigation

**Question**: How should HA surfaces navigate between Working groups, curated models, archives, and projects?

**Recommendation**:
- Model detail → "Related groups" section (Working groups in same project)
- Model detail → "Print history" section (archives linked to this model)
- Working group detail → "Curated version" link (if published)
- Archive detail → "Related models" section (working + curated variants)
- Archive detail → "Project" link (if in project)
- HA project view → aggregates all working groups + curated models + related archives

---

## Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Bulk import creates 500+ orphaned working groups | High | Review before commit; support bulk delete/rollback |
| Folder-based grouping doesn't match actual project structure | Medium | Require folder_hint documentation; support manual regrouping |
| 3MF color extraction is unreliable or incomplete | Medium | Make extracted colors advisory; allow operator override; track confidence |
| Project concept creates confusion with Bambuddy projects | Medium | Clear terminology: "Design Project" (Model Catalog) vs "Print Project" (Bambuddy) |
| Bulk enrichment takes too long for 500+ files | Medium | Run 3MF analysis async; cache results; allow incremental processing |
| Users forget to assign working groups to projects | Low | Optional; provide discovery card to find ungrouped items |

---

## Examples: Your Specific Use Case Walkthrough

### Scenario: You Have `~/3D Printing/` with This Structure

```
3D Printing/
├── Tools/
│   ├── screwdriver_base.3mf
│   ├── screwdriver_handle.3mf
│   ├── screwdriver_stand.3mf
│   └── wrench_v1.3mf
├── Organizers/
│   ├── drawer_organizer_base.3mf
│   ├── drawer_organizer_tall_variant.3mf
│   └── desk_organizer.3mf
├── Miniatures/
│   ├── d20_standard.3mf
│   ├── d20_marble_effect.3mf
│   └── d20_hex_etches.3mf
├── stray_model.3mf
└── README.txt
```

### Workflow (With Proposed Enhancements)

**Step 1: Bulk Discover** (Phase 1.5)
```
HA Service Call: ha_bulk_discover_working_groups
Parameters:
  folder_path: ~/3D Printing/
  grouping_strategy: "by-folder"

Result (Review):
  ✓ Group 1: "Tools" (4 files)
    - screwdriver_base.3mf (primary)
    - screwdriver_handle.3mf
    - screwdriver_stand.3mf
    - wrench_v1.3mf
  
  ✓ Group 2: "Organizers" (3 files)
    - drawer_organizer_base.3mf (primary)
    - drawer_organizer_tall_variant.3mf
    - desk_organizer.3mf
  
  ✓ Group 3: "Miniatures" (3 files)
    - d20_standard.3mf (primary)
    - d20_marble_effect.3mf
    - d20_hex_etches.3mf
  
  ⚠ Ungrouped: stray_model.3mf (in root, no folder)

Operator Decision:
  - Accept Groups 1-3 as-is
  - Move stray_model.3mf to Tools or create new group "Miscellaneous"
  - Proceed to Step 2
```

**Step 2: Bulk Import** (Phase 1.5)
```
HA Service Call: ha_bulk_import_working_groups
Parameters:
  groups: [Group 1, Group 2, Group 3]
  
Result:
  ✓ Created working_group: "Tools" (id: wg-001)
    - folder_hint: ~/3D Printing/Tools
    - discovery_metadata: {
        imported_from_folder: "~/3D Printing/Tools",
        imported_at: "2026-04-24T10:00:00Z",
        discovery_strategy: "by-folder"
      }
  
  ✓ Created working_group: "Organizers" (id: wg-002)
  ✓ Created working_group: "Miniatures" (id: wg-003)
```

**Step 3: Bulk Analyze & Enrich** (Phase 3.5)
```
HA Service Call: ha_bulk_analyze_working_groups
Parameters:
  working_group_ids: [wg-001, wg-002, wg-003]
  
Processing (Async):
  - 3MF Parser extracts:
    wg-001 "Tools":
      - Colors: [#2d3436, #f39c12, #e74c3c]
      - Dimensions: ~100mm x 50mm
      - Proposed tags: ["tools", "organizer", "storage"]
      - Confidence: 0.85
    
    wg-002 "Organizers":
      - Colors: [#34495e, #ecf0f1]
      - Dimensions: ~200mm x 150mm
      - Proposed tags: ["organizer", "drawer", "desk"]
      - Confidence: 0.90
    
    wg-003 "Miniatures":
      - Colors: [#ffffff]
      - Dimensions: ~15mm
      - Proposed tags: ["dice", "miniature", "gaming"]
      - Confidence: 0.92

Result (For Operator Review):
  Show enrichment card with:
    - Proposed colors (with swatches)
    - Proposed tags (with confidence scores)
    - Option to override or skip per group
```

**Step 4: Bulk Enrich** (Phase 3.5)
```
HA Service Call: ha_bulk_enrich_working_groups
Parameters:
  enrichments: [
    {
      working_group_id: wg-001,
      colors: [#2d3436, #f39c12, #e74c3c],
      tags: ["tools", "organizer"],
      approved_by_operator: true
    },
    {
      working_group_id: wg-002,
      colors: [#34495e, #ecf0f1],
      tags: ["organizer"],
      approved_by_operator: true,
      skip_tags: ["drawer", "desk"]  # Operator override
    },
    {
      working_group_id: wg-003,
      colors: [#ffffff],
      tags: ["dice", "miniature"],
      approved_by_operator: true
    }
  ]

Result:
  ✓ Applied enrichment to wg-001
  ✓ Applied enrichment to wg-002 (with overrides)
  ✓ Applied enrichment to wg-003
```

**Step 5: Create Projects & Organize** (Phase 5 / New)
```
HA UI: Create Model Catalog Project
  Title: "Desk Accessories"
  Description: "Tools and organizers for desk setup"
  Type: "model_family"
  
  Add Working Groups:
    - wg-001 (Tools)
    - wg-002 (Organizers)
  
  Result: Created project "proj-desk-001"
    - working_group_ids: [wg-001, wg-002]
    - related_models: []  # Will add after curating/publishing

HA UI: Create Model Catalog Project
  Title: "Dice & Gaming"
  Type: "miniature_collection"
  
  Add Working Groups:
    - wg-003 (Miniatures)
```

**Step 6: Publish & Curate** (Phase 5, modified)
```
When ready, for each working group:
  - Select primary files and supporting assets
  - Create curated Manyfold model
  - Assign to project
  
  Example:
    wg-001 "Tools" → creates "Tools Collection" in Manyfold
      - Add screwdriver_base.3mf as primary file
      - Add screwdriver_handle.3mf, screwdriver_stand.3mf as variants
      - Add wrench_v1.3mf as separate file (or as separate model)
      - Assign project_id: "proj-desk-001" (in sidecar metadata)
      - Tags inherited: ["tools", "organizer"]
      - Colors inherited: [#2d3436, #f39c12, #e74c3c]
```

**Step 7: Link & Print** (Phase 2)
```
Later, when you print from a curated model:
  - Archive is created by Bambuddy
  - Archive can be linked to curated Manyfold model
  - Archive can optionally be assigned to Bambuddy project
  - HA can cross-link:
    Archive → Curated Model → Model Catalog Project → Related Working Groups
    Archive → Bambuddy Project (optional)
```

---

## Summary Table: Gaps & Recommendations

| Gap | Recommendation | Phase | Implementation Effort |
|-----|-----------------|-------|----------------------|
| **No bulk ingest workflow** | Add current Phase 5 bulk-discover/import | Phase 5 | Medium |
| **No project concept in Model Catalog** | Create sidecar-owned project model | Phase 9 | Medium |
| **No project linkage across systems** | Define cross-feature contracts | Phase 9 | Low (design) |
| **No bulk metadata enrichment** | Add current Phase 6 bulk tag/color enrichment | Phase 6 | Medium |
| **No "related models" pattern** | Clarify three model patterns (variants/family/remix) | Phase 1-2 (design) | Low |
| **Working groups not discoverable by project** | Add project_id to working groups; HA project view | Phase 9 | Low |
| **Duplicate handling incomplete** | Add file-hash deduplication to bulk import | Phase 5 | Low |
| **No folder audit trail** | Add discovery_metadata to working groups | Phase 5 | Low |

---

## Next Steps

### Immediate (Design Phase)

1. **Validate**: Review this assessment against your actual folder structure. Does the current Phase 5 bulk-discover strategy match your organization patterns?

2. **Decide**: Accept or modify the project model recommendation. Confirm project ownership should be Model Catalog sidecar.

3. **Document**: Create the cross-feature project-linkage contract if approved.

### Implementation Sequencing

1. **Phase 1** (Unchanged): Sidecar scaffold
2. **Phase 5**: Bulk discovery & import
3. **Phase 2** (Unchanged): Archive linkage
4. **Phase 3** (Unchanged): Taxonomy + **Phase 6**: Bulk enrichment
5. **Phase 9**: Working groups + projects
6. ...rest unchanged

### Open Questions for You

- [ ] Does the "by-folder" grouping strategy match your folder organization?
- [ ] Do you have a preference for where projects should be stored (sidecar vs Bambuddy vs hybrid)?
- [ ] Would automated folder-to-group inference help, or would manual curation be preferred?
- [ ] For enrichment, which signals matter most: colors, tags, or both?
- [ ] Do you want to support "model families" (one project, N curated models) or keep models independent?

