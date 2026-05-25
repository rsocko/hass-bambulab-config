# Model Catalog Projects Design

> **Status**: Design proposal for unified project concept across Model Catalog, Working Groups, and Print History linkage.
> **Created**: 2026-04-24
> **Audience**: Architecture review, implementation planning

---

## Problem Statement

Currently, "project" means different things in different parts of your system:

1. **Print History** (Bambuddy): A project is a collection of print archives (print outcomes)
2. **Working Groups**: A working group is a work-in-progress collection of files and assets
3. **Curated Models**: Models have no project relationship

This creates:
- **Organizational gap**: You cannot say "these 3 variants belong together as a design project"
- **Navigation gap**: No way to go from a print archive → related model variants → related working files
- **Terminology gap**: Different systems use "project" for different concepts

**Result**: Your bulk-ingestion use case (500+ files organized by project) has no natural organizing principle in the catalog.

---

## Proposed Solution: Model Catalog Projects

Create a **Model Catalog–owned project entity** that can link:
- Multiple Working groups (in-flight versions)
- Multiple curated Manyfold models (stable versions)
- Optional Bambuddy project reference (print outcomes)
- External source or design origin information

### Core Idea

```
Model Catalog Project
├─ Working Groups (in-progress files/variants)
├─ Curated Models (stable, published versions)
├─ Bambuddy Project (optional, for print tracking)
└─ Origin/Provenance
```

---

## Data Model

### Project Entity (Sidecar-Owned)

```yaml
Project:
  # Identifiers
  id:                      UUID
  slug:                    String (URL-safe)
  
  # Metadata
  title:                   String (required, human-readable)
  description:             String (optional, markdown)
  origin:                  Enum: "makerworld", "printables", "custom", "unknown", "commercial", "remix"
  origin_url:              String (optional, URL to upstream source)
  
  # Organization
  project_type:            Enum: "model_family", "remix_set", "multi_part", "author_collection", "other"
  category_ids:            List[String] (optional, Manyfold categories or custom tags)
  
  # Composition
  working_group_ids:       List[UUID] (groups currently being edited)
  curated_model_ids:       List[UUID] (published stable models, stored as sidecar metadata on each model)
  bambuddy_project_id:     Int | null (reference to Bambuddy project for print outcomes, optional)
  
  # Lifecycle
  created_at:              DateTime
  updated_at:              DateTime
  completed_at:            DateTime | null (when all versions published/done)
  archived_at:             DateTime | null (when no longer active)
  
  # Governance
  created_by:              String (operator identifier, optional)
  notes:                    String (internal notes, markdown)
```

### Relationships: How Projects Connect to Other Entities

#### Working Group ← Project Linkage

```yaml
WorkingGroup:
  # ... existing fields ...
  project_id:              UUID | null (optional, link to Model Catalog project)
```

#### Curated Model ← Project Linkage (Sidecar Metadata)

```yaml
# In Manyfold: model as currently designed (unchanged)
# In Model Catalog Sidecar: add metadata layer

ModelCatalogMetadata:
  manyfold_model_id:       UUID (Manyfold model ID)
  project_id:              UUID | null (Model Catalog project)
  variant_of:              UUID | null (if this is a variant of another model)
  remix_source:            String | null (URL or description of remixed source)
  published_from_group_id: UUID | null (Working group that this was published from)
```

#### Archive ← Project Navigation (Indirect)

```yaml
# Archive itself unchanged (owned by Bambuddy)
# Navigation path:
Archive
  ↓ (linked to Manyfold model via sidecar linkage DB)
CuratedModel
  ↓ (linked to Project via sidecar metadata)
ModelCatalogProject
  ↓ (linked to Working groups + Bambuddy project)
[Working Groups, Archives, Variants]
```

---

## Project Auto-Suggestion from Catalog Fork

The catalog-side **Send to Working Files** action (`fork-to-working`) is the primary trigger that populates Project lineage automatically. See [catalog-edit-and-fork.md §3](catalog-edit-and-fork.md) for the full fork flow and [catalog-edit-and-fork.md §6](catalog-edit-and-fork.md) for the auto-suggestion contract.

Behavior:

- The fork confirm dialog defaults `project_linkage = new_project` when the source catalog model is **not** already in a Project. Title default: `"{model_title} (lineage)"`, `project_type = model_family`.
- If the source catalog model **is** already in a Project, the dialog defaults to `existing_project` pre-filled with that Project. The new working folder is added to `working_group_ids`.
- The operator may always choose `none` to skip Project linkage; lineage remains queryable via the `model_catalog_lineage` table without a Project.
- On a subsequent `republish_as_new_version` publish with `conflict_policy = new_revision`, the newly created catalog model is attached to the same Project's `curated_model_ids`, and the junction-table fields `variant_of` and `published_from_group_id` are populated by the wizard (`variant_of` = previous head's `manyfold_model_id`, `published_from_group_id` = the working group used for the publish).

This is the first design that **actively writes** `variant_of` and `published_from_group_id` — earlier drafts defined the schema but had no flow producing the values. Fork-and-republish is that flow.

---

## Usage Patterns

### Pattern 1: Multi-Part Design (Model Family)

**Scenario**: "Desk accessories" — screwdriver, organizer, stand, wrench

```
Project: "Desk Accessories"
├─ Working Groups:
│  ├─ wg-tools (screwdriver_base, screwdriver_handle, stand, wrench)
│  └─ wg-organizers (drawer_organizer, desk_organizer)
│
├─ Curated Models:
│  ├─ model-screwdriver (published from wg-tools, primary files)
│  ├─ model-organizer (published from wg-organizers)
│  └─ model-stand (optional separate model)
│
└─ Bambuddy Project: optional
   └─ Prints of all desk accessories together
```

**Project Type**: `model_family`

**Use Cases**:
- "Show me all the desk-accessory variants I have"
- "I want to reprint all desk accessories for a client"
- "Find all related prints of desk accessories"

---

### Pattern 2: Remix Collection

**Scenario**: "My remixes of designer X's work"

```
Project: "Remixes of Designer X"
├─ Working Groups:
│  ├─ wg-remix-1 (base_modified.3mf, variant.3mf)
│  └─ wg-remix-2 (another_modified.3mf)
│
├─ Curated Models:
│  ├─ model-remix-1 (with remix_source pointing to original)
│  └─ model-remix-2
│
└─ Origin: "printables"
    origin_url: "https://www.printables.com/model/..."
```

**Project Type**: `remix_set`

**Use Cases**:
- "Show me all my remixes"
- "Attribute credit to original designer"
- "Find prints made from my remixes"

---

### Pattern 3: Multi-Version Iteration

**Scenario**: "Screwdriver driver — base model, then 3 iterations"

```
Project: "Screwdriver Driver"
├─ Working Groups:
│  ├─ wg-screwdriver-v1 (original_base.3mf)
│  ├─ wg-screwdriver-v2 (improved_base.3mf, new_handle.3mf)
│  └─ wg-screwdriver-v3 (final_base.3mf, final_handle.3mf, stand.3mf)
│
├─ Curated Models:
│  ├─ model-screwdriver-v1 (archived/deprecated)
│  ├─ model-screwdriver-v2
│  └─ model-screwdriver-v3 (current recommended)
│
└─ No Bambuddy project (each version printed separately)
```

**Project Type**: `model_family`

**Use Cases**:
- "Show me the version history"
- "Find all prints made from each version"
- "Recommend v3 as the current stable version"

---

## Ownership & Storage

### Why Model Catalog Should Own Projects

**Option A: Model Catalog Sidecar (Recommended)**
- ✅ Clear ownership; no upstream dependency
- ✅ Can link arbitrary entities (working groups, curated models, archives, external sources)
- ✅ Can evolve without Manyfold or Bambuddy changes
- ✅ Projects are metadata about your catalog organization, not core archive data

**Option B: Bambuddy**
- ❌ Would require Bambuddy to understand curated models (out of scope)
- ❌ Would blur archive-vs-model boundary
- ❌ Would create dual project concepts (print projects + model projects)

**Option C: Manyfold**
- ❌ Would require upstream enhancement
- ❌ Would force all model projects into Manyfold
- ❌ Would lose flexibility for optional linking

**Recommendation**: **Model Catalog sidecar owns projects.**

### Storage Implementation

```
Model Catalog Sidecar Database (SQLite):

Projects Table:
  id (UUID, PK)
  slug (TEXT, UNIQUE)
  title (TEXT)
  description (TEXT)
  origin (TEXT)
  origin_url (TEXT)
  project_type (TEXT)
  category_ids (JSON array)
  bambuddy_project_id (INT, nullable)
  created_at (DATETIME)
  updated_at (DATETIME)
  completed_at (DATETIME, nullable)
  archived_at (DATETIME, nullable)
  created_by (TEXT, nullable)
  notes (TEXT)

ProjectWorkingGroups Junction Table:
  project_id (UUID, FK → Projects)
  working_group_id (UUID, FK → WorkingGroups)
  order (INT, for drag-reorder if desired)
  added_at (DATETIME)

ProjectCuratedModels Junction Table:
  project_id (UUID, FK → Projects)
  manyfold_model_id (UUID)
  variant_of (UUID, nullable, if this model is a variant of another)
  remix_source (TEXT, nullable)
  published_from_group_id (UUID, nullable)
  added_at (DATETIME)
```

---

## API Surface

### Endpoints (Sidecar FastAPI)

```
# List projects
GET /projects
  Query params:
    - skip: int (default 0)
    - limit: int (default 50)
    - archived: bool (default false, filter out archived)
    - type: str (optional, filter by project_type)
  Response: List[ProjectSummary]

# Get project detail
GET /projects/{project_id}
  Response: ProjectDetail (includes related working groups, models, archives)

# Create project
POST /projects
  Payload: {
    title: str,
    description: str,
    project_type: str,
    origin: str,
    origin_url: str,
    category_ids: List[str],
    bambuddy_project_id: int | null
  }
  Response: ProjectDetail

# Update project
PATCH /projects/{project_id}
  Payload: (any fields from POST)
  Response: ProjectDetail

# Delete project (soft-delete via archive)
DELETE /projects/{project_id}
  Response: status

# Add working group to project
POST /projects/{project_id}/working-groups
  Payload: { working_group_id: UUID }
  Response: ProjectDetail

# Remove working group from project
DELETE /projects/{project_id}/working-groups/{working_group_id}
  Response: ProjectDetail

# Add curated model to project
POST /projects/{project_id}/curated-models
  Payload: {
    manyfold_model_id: UUID,
    variant_of: UUID | null,
    remix_source: str | null,
    published_from_group_id: UUID | null
  }
  Response: ProjectDetail

# Remove curated model from project
DELETE /projects/{project_id}/curated-models/{manyfold_model_id}
  Response: ProjectDetail

# List archives related to project
# (via Bambuddy project OR via archive linkage to curated models)
GET /projects/{project_id}/related-archives
  Response: List[ArchiveSummary]

# Get all projects for a working group
GET /working-groups/{wg_id}/projects
  Response: List[ProjectSummary]

# Get all projects for a curated model
GET /models/{model_id}/projects
  Response: List[ProjectSummary]
```

---

## Home Assistant Integration

### Lovelace Views

#### 1. Projects Browser

```
View: "Projects"
├─ Card 1: Project Grid
│  ├─ List all projects
│  ├─ Show: title, count of working groups, count of curated models, type
│  ├─ Filters: type, origin, archived
│  └─ Actions: open detail, edit, archive/delete
│
├─ Card 2: Create Project (quick add)
│  ├─ Title input
│  ├─ Type selector
│  └─ Optional: origin URL
│
└─ Card 3: Recent Activity
   └─ Show projects updated in last 7 days
```

#### 2. Project Detail View

```
View: "Project: [Title]"
├─ Header:
│  ├─ Title, description, origin URL (clickable)
│  ├─ Type badge, created/updated timestamps
│  └─ Actions: Edit, Archive, Delete
│
├─ Section 1: Working Groups
│  ├─ List all working groups in project
│  ├─ Show: title, file count, stage, updated_at
│  ├─ Actions per group: Open, Remove from project
│  └─ Add Group button
│
├─ Section 2: Curated Models
│  ├─ List all curated models in project
│  ├─ Show: thumbnail, title, variant_of indicator, published_at
│  ├─ Actions per model: Open in Manyfold, Remove from project
│  └─ Add Model button
│
├─ Section 3: Related Prints
│  ├─ List archives linked to this project
│  ├─ Via: curated model linkage + optional Bambuddy project
│  ├─ Show: date, status, duration, cost
│  └─ Actions: Open archive detail, View in print history
│
├─ Section 4: Metadata
│  ├─ Origin, category tags, notes
│  └─ Edit button
│
└─ Section 5: Lifecycle
   ├─ Created by [user] at [time]
   ├─ Updated [n] times
   └─ Archive button (if completed)
```

#### 3. Cross-Link From Archive Detail

```
Archive Detail Popup (existing)
├─ ... existing fields ...
├─ NEW Section: "Related Models & Project"
│  ├─ If archived is linked to curated model:
│  │  ├─ Show: Curated model name → Open
│  │  └─ Show: Project (if model in project) → Open
│  │
│  └─ Show: Related items
│     ├─ Other archives linked to same project
│     ├─ Other working groups in project
│     └─ Other model variants in project
│
└─ Action: Unlink from model or change linkage
```

#### 4. Cross-Link From Curated Model (in Manyfold UI or HA iframe)

```
Manyfold Model Detail (optional HA iframe or link)
├─ ... Manyfold native fields ...
├─ NEW Section: "Model Catalog Project" (optional HA overlay or card)
│  ├─ Show: Project name → Navigate
│  ├─ Show: Related variants (if this is one)
│  ├─ Show: Bambuddy project (if linked)
│  ├─ Show: Related prints (if linked archives exist)
│  └─ Show: Working group history (if published from group)
│
└─ Action: Add to/remove from project
```

#### 5. Cross-Link From Working Group Board

```
Working Board (existing, Phase 4)
├─ Group Cards showing:
│  ├─ ... existing fields ...
│  ├─ NEW: Project badge/link (if assigned to project)
│  └─ Optional: Show related curated model if exists
│
└─ When creating or editing group:
   └─ Optional: Assign to project
```

---

## HA Services

```yaml
# Create project
service: model_catalog.create_project
data:
  title: "Desk Accessories"
  description: "Tools and organizers for desk setup"
  project_type: "model_family"
  origin: "custom"
  category_ids:
    - "organizers"
    - "tools"

# Add working group to project
service: model_catalog.add_working_group_to_project
data:
  project_id: "proj-desk-001"
  working_group_id: "wg-tools"

# Add curated model to project
service: model_catalog.add_model_to_project
data:
  project_id: "proj-desk-001"
  manyfold_model_id: "model-123"
  published_from_group_id: "wg-tools"

# Remove working group from project
service: model_catalog.remove_working_group_from_project
data:
  project_id: "proj-desk-001"
  working_group_id: "wg-tools"

# Link Bambuddy project to Model Catalog project
service: model_catalog.set_bambuddy_project
data:
  project_id: "proj-desk-001"
  bambuddy_project_id: 5
```

---

## Implementation Sequencing

### Phase 4 (Enhanced): Projects Sidecar Foundation

- Implement Project data model
- Implement API endpoints for CRUD
- Add HA services for basic project operations
- Add HA project grid/browser view

### Phase 5 (Enhanced): Working Group ← Project Linkage

- Add `project_id` field to Working groups
- Support assigning working groups to projects
- Update HA working board to show project association
- Update bulk-import (Phase 1.5) to optionally create projects

### Phase 5+ (Enhanced): Curated Model ← Project Linkage

- Implement sidecar metadata layer for curated models
- Support assigning curated models to projects
- Add publish workflow enhancement: offer to add model to project
- Add revision lineage tracking (which project, which version)

### Phase 10+ (New): Cross-Link Navigation

- Add "Related Models" section to archive detail
- Add "Related Archives" section to project detail
- Add Bambuddy project linkage surface
- Support optional project creation at archive linkage time

---

## Migration & Backward Compatibility

### For Existing Data

**Working Groups**:
- `project_id` field is optional and defaults to `null`
- Existing Working groups continue to work unchanged
- Users can assign existing groups to projects later

**Curated Models**:
- Sidecar metadata is optional
- Existing model linkage continues unchanged
- Projects are optional enrichment only

**Archives**:
- Completely unchanged
- Navigation to projects is added as optional enrichment
- Bambuddy `project_id` remains in use; Model Catalog project is parallel

### For New Data

- Phase 1.5 bulk-import can optionally create projects
- Phase 5 can create projects during publish workflow
- Users can manually create projects anytime

---

## Design Decisions Locked In

1. **Project ownership**: Model Catalog sidecar
2. **Project scope**: Working groups + curated models + optional Bambuddy linkage
3. **Project terminology**: 
   - "Model Catalog Project" (distinguishes from Print History project)
   - Or "Design Project" for user-facing language
4. **Relationship**: Many-to-many (one project can have N groups/models; one group/model can (optionally) belong to 1 project)
5. **Optional linkage**: Projects are optional; orphaned working groups and models remain valid

---

## Open Questions for Design Review

- [ ] Should one working group or model be allowed in multiple projects?
  - **Current recommendation**: No (many-to-one). Simplicity and clarity.
  - **Alternative**: Yes (many-to-many). More flexible but adds complexity.

- [ ] Should Bambuddy project linkage be required, optional, or not supported?
  - **Current recommendation**: Optional. Print projects and model projects are different concepts.

- [ ] Should there be a UI for creating projects directly from an archive?
  - **Current recommendation**: Later phase. First, projects are created from model/working-group views.

- [ ] Should projects have explicit "related archives" filtering or inference?
  - **Current recommendation**: Inferred via curated model linkage + optional Bambuddy project.
  - **Alternative**: Explicit archive list (more manual but clearer).

- [ ] Should the HA project detail show all Bambuddy projects that have printed items from this project's models?
  - **Current recommendation**: Yes, but as a read-only summary for visibility.

