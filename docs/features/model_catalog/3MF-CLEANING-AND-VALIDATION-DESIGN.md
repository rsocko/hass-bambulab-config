# 3MF Cleaning & Validation Integration Design

**Version**: 1.0  
**Date**: 2026-05-05  
**Status**: Design Doc (Ready for Review)  
**Related Issues**: #1327 (Clean 3MF functionality), #1190-#1197 (Phase 1 Foundation)  
**Reference Impl**: [3MFresh](https://github.com/brossow/3MFresh) by @brossow  

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Problem Statement](#problem-statement)
3. [Feature Scope](#feature-scope)
4. [Architecture](#architecture)
5. [Integration Points](#integration-points)
6. [API Design](#api-design)
7. [Implementation Phases](#implementation-phases)
8. [Data Model Extensions](#data-model-extensions)
9. [Considerations & Risks](#considerations--risks)
10. [Alternative Approaches](#alternative-approaches)
11. [Success Criteria](#success-criteria)

---

## Executive Summary

This design proposes adding **3MF cleaning and validation** capabilities to the Model Catalog sidecar, specifically targeting **Working Files** that are prepared for upload to MakerWorld or other online platforms. The implementation leverages proven concepts from the [3MFresh](https://github.com/brossow/3MFresh) project while integrating deeply with the Model Catalog's existing:

- **Working Groups** context for organizing "to-be-uploaded" files
- **Intake** workflow for validation gates
- **Archive Linking** for metadata enrichment

**Expected Outcomes**:
- Operators can clean 3MF files in bulk before uploading to external platforms
- Metadata history is preserved for audit/recovery
- 3MF validation ensures compatibility with target printers
- Dashboard shows cleaning results and validation status
- Minimal manual intervention for common cleaning operations

---

## Problem Statement

### Current State

1. **Downloaded 3MF files** from MakerWorld or other sources often contain:
   - Metadata tied to original creator
   - Model descriptions and images
   - Print setting profiles specific to other filaments
   - Auxiliary data (Auxiliaries directory in ZIP structure)

2. **Repurposing challenges**:
   - When modifying a downloaded profile for a new model, original metadata persists
   - Printer history and slicer interface still display old model information
   - Creates confusion between the original source and custom modifications
   - No standardized workflow for cleaning before re-upload

3. **No native HA/sidecar capability**:
   - Users must manually run 3MFresh script
   - No tracking of cleaning operations
   - No validation that cleaned files are still compatible with target printers
   - No integration with Working Files workflow

### Desired State

1. **Integrated cleaning workflow**:
   - Operator selects Working Files or uploads new 3MF
   - Sidecar offers preview of what will be removed
   - One-click cleaning with audit trail
   - Validation confirms output is compatible

2. **Working Files integration**:
   - New stage: `needs_cleaning` or `ready_to_clean`
   - Batch operations: clean multiple files at once
   - Automatic enrichment: tag with filament/print-time metadata from print history
   - Staging: cleaned output marked as `ready_to_upload`

3. **Dashboard visibility**:
   - Show what metadata will be removed
   - Display validation results (compatibility, schema compliance)
   - Link to print history for enrichment context
   - Export summary for manual review

---

## Feature Scope

### In Scope (MVP)

1. **3MF Cleaning** (Phase 1)
   - Extract 3MF as ZIP
   - Remove `Auxiliaries/` directory
   - Remove metadata except whitelisted entries
   - Re-package into clean 3MF
   - Preserve internal structure for Bambu Studio compatibility

2. **3MF Validation** (Phase 1)
   - Verify 3MF ZIP structure is valid
   - Confirm presence of `3D/3dmodel.model` file
   - Validate XML schema compliance (basic)
   - Verify whitelist preservation (Application, BambuStudio:3mfVersion)

3. **Working Files Integration** (Phase 1)
   - Add cleaning operation to working items
   - Track cleaning state in database
   - Store audit trail (what was removed, when, by whom)
   - Output to `{working_group_id}_cleaned/` subfolder

4. **Batch Operations** (Phase 1)
   - Clean multiple files in one request
   - Rollback on partial failure
   - Report per-file success/error status

5. **API Endpoints** (Phase 1)
   - `POST /api/working/items/{item_id}/clean` - Clean single file
   - `POST /api/working/groups/{group_id}/clean-batch` - Clean all items in group
   - `GET /api/working/items/{item_id}/cleaning-preview` - Show what will be removed
   - `GET /api/working/items/{item_id}/validation-report` - Validation results

### Out of Scope (Future Phases)

1. **Advanced Metadata Operations**
   - Selective metadata removal (per-field granularity)
   - Custom metadata injection
   - Filament profile optimization (separate concern)

2. **Print Profile Analysis**
   - Extracting and comparing print settings
   - Automatic filament material detection
   - Temperature/speed optimization recommendations

3. **Geometry Analysis**
   - STL/mesh extraction and preview
   - Model complexity scoring
   - Pre-slicing analysis

4. **External Platform Integration**
   - Direct upload to MakerWorld
   - Automatic metadata submission
   - License/attribution tracking

---

## Architecture

### High-Level Data Flow

```
┌──────────────────────────────────────────────────────────────┐
│ Working Group Item (3MF file)                                │
│ state: 'ready_to_clean' | 'in_progress' | 'cleaned'          │
│ cleaning_metadata: {...}                                     │
└────────────────────────┬─────────────────────────────────────┘
                         │
         ┌───────────────▼──────────────────┐
         │   Clean Request                  │
         │   - file_path                    │
         │   - preserve_whitelist []        │
         │   - output_folder                │
         └───────────────┬──────────────────┘
                         │
    ┌────────────────────▼──────────────────────────┐
    │  3MF Cleaning Service (NEW)                   │
    │  ┌──────────────────────────────────────────┐ │
    │  │ 1. Extract ZIP                           │ │
    │  │ 2. Remove Auxiliaries/                   │ │
    │  │ 3. Parse XML metadata                    │ │
    │  │ 4. Filter metadata (keep whitelist)      │ │
    │  │ 5. Validate output                       │ │
    │  │ 6. Repackage ZIP                         │ │
    │  │ 7. Store audit trail                     │ │
    │  └──────────────────────────────────────────┘ │
    └────────────────┬───────────────────────────────┘
                     │
    ┌────────────────▼──────────────────────────┐
    │  Output & Audit Trail                    │
    │  - clean_3mf_path                        │
    │  - removed_metadata_summary              │
    │  - validation_results                    │
    │  - cleaning_timestamp                    │
    │  - db_cleaning_record_id                 │
    └────────────────┬──────────────────────────┘
                     │
         ┌───────────▼──────────┐
         │ Update Working Item  │
         │ state: 'cleaned'     │
         │ Link to audit trail  │
         └──────────────────────┘
```

### Module Organization

```
sidecars/model_catalog/app/
├── routers/
│   └── working.py (add cleaning endpoints)
│
├── services/
│   ├── working_groups_service.py (orchestrate cleaning)
│   └── 3mf_cleaning_service.py (NEW)
│
├── domain/
│   └── 3mf_validator.py (NEW - validation logic)
│
├── db_working.py (add cleaning fields to schema)
└── db_3mf_cleaning.py (NEW - audit trail & metadata store)
```

### Service Layer Design

#### `3mf_cleaning_service.py` (NEW Module)

```python
class ThreeMFCleaner:
    """Core 3MF cleaning and validation logic."""
    
    def __init__(self, temp_dir: Path = None):
        self.temp_dir = temp_dir or Path(tempfile.gettempdir())
        self.metadata_whitelist = {
            "<metadata name=\"Application\"",
            "<metadata name=\"BambuStudio:3mfVersion\""
        }
    
    async def clean_3mf(
        self,
        input_path: Path,
        output_path: Path,
        preserve_whitelist: List[str] = None,
    ) -> CleaningResult:
        """
        Clean a 3MF file by removing unnecessary metadata and Auxiliaries.
        
        Returns: CleaningResult with status, removed_items, validation_status
        """
        
    async def validate_3mf(self, file_path: Path) -> ValidationReport:
        """
        Validate 3MF structure and content integrity.
        
        Checks:
        - ZIP integrity
        - Required files present (3D/3dmodel.model)
        - XML schema compliance (basic)
        - Metadata whitelist preserved
        
        Returns: ValidationReport with validation_status, issues, warnings
        """
        
    async def extract_metadata_summary(
        self,
        input_path: Path
    ) -> MetadataSummary:
        """
        Extract and categorize all metadata that would be removed.
        
        Returns: MetadataSummary with categories: application, model, creator, etc.
        """
        
    def _parse_3dmodel_xml(self, xml_content: str) -> Tuple[ET.Element, List[str]]:
        """Parse 3D/3dmodel.model and extract metadata lines for removal."""
```

#### `3mf_validator.py` (NEW Module)

```python
class ThreeMFValidator:
    """3MF format validation and schema compliance checking."""
    
    async def validate_structure(self, file_path: Path) -> StructureValidation:
        """Check ZIP structure, required files, encoding."""
        
    async def validate_xml_schema(self, file_path: Path) -> SchemaValidation:
        """Validate XML against basic 3MF schema expectations."""
        
    async def validate_compatibility(
        self,
        file_path: Path,
        target_printer: str = "BambuLab"
    ) -> CompatibilityReport:
        """
        Check compatibility with target printer/slicer.
        
        Includes: required metadata presence, geometry validity, etc.
        """
```

#### `working_groups_service.py` (Extensions)

```python
# Add to existing WorkingGroupsService class:

async def clean_working_item(
    self,
    working_group_id: str,
    item_id: str,
    options: CleaningOptions = None
) -> CleaningOperationResult:
    """
    Clean a single working item's 3MF file.
    
    1. Retrieve working item
    2. Validate it's a 3MF file
    3. Create backup of original
    4. Clean using 3MFCleaner
    5. Validate output
    6. Store audit trail in db
    7. Update working item metadata
    8. Return result
    """

async def batch_clean_working_group(
    self,
    working_group_id: str,
    options: CleaningOptions = None
) -> BatchCleaningResult:
    """
    Clean all 3MF files in a working group.
    
    Returns: per-file results, aggregated statistics, error handling
    """

async def get_cleaning_preview(
    self,
    working_group_id: str,
    item_id: str
) -> CleaningPreview:
    """
    Show what WOULD be removed without modifying the file.
    
    Returns: metadata_summary, estimated_size_reduction, warnings
    """
```

---

## Integration Points

### 1. Working Files Context

**Where it fits**:
- Working items now have optional `cleaning_state` field
- New stage in workflow: `ready_to_clean` → `in_progress_cleaning` → `cleaned`
- Output file stored as sibling or in `_cleaned/` subfolder

**Database Extensions** (see section on Data Model):
- New table: `working_item_cleaning_audit`
- New fields in `working_items`: cleaning_state, cleaning_timestamp, cleaned_file_path
- New table: `3mf_metadata_snapshots` for audit trail

**Workflow Stages**:
```
draft
  ↓
in_progress (user editing)
  ↓
needs_revision or ready_to_upload
  ├→ ready_to_clean (if from external source)
  │   ↓
  │   in_progress_cleaning (while cleaning)
  │   ↓
  │   cleaned (after successful cleaning)
  │   ↓
  │   ready_to_upload ← enrichment & validation
  │
  └→ ready_to_upload (if already clean)
```

### 2. Intake Workflow

**Clean-on-intake Option**:
- When uploading new files to intake, offer cleaning as optional pre-processing
- New intake verification gate: `requires_3mf_cleaning`
- Intake item can skip to cleaned state if operator opts in

**Integration**:
```
Intake Upload → Optional Cleaning → Verification → Publishing
```

### 3. Archive Linking & Enrichment

**Pre-upload Enrichment**:
- Before marking file as `ready_to_upload`, optionally link to print archives
- Query print history for filament/print-time metadata
- Inject into tags/notes field of cleaned 3MF via PATCH `/archives/{id}`
- Example: "PLA | 185°C | 55min print time"

### 4. Dashboard Integration (Future)

**Home Assistant Custom Card**:
- Show Working Files with cleaning status
- Bulk clean operation from card UI
- Diff view: before/after metadata
- One-click "prepare for MakerWorld" automation

**New Lovelace Card Section**:
```
Working Group: "Gridfinity Bins"
├─ bin-base.3mf          → ready_to_clean
├─ bin-drawer.3mf        → ready_to_clean
└─ bin-divider.3mf       → cleaned ✓

Batch Actions:
[Clean All] [Preview Changes] [Export Summary]
```

---

## API Design

### Endpoints (New)

#### 1. Clean Single Working Item

```http
POST /api/working/items/{item_id}/clean
Content-Type: application/json

{
  "preserve_whitelist": [
    "<metadata name=\"Application\"",
    "<metadata name=\"BambuStudio:3mfVersion\""
  ],
  "output_folder": "working/{group_id}/_cleaned",
  "backup_original": true,
  "validate_output": true
}

Response (200):
{
  "operation_id": "clean_op_abc123",
  "item_id": "item_xyz789",
  "status": "success",
  "input_file": "/home/user/working/gridfinity/bin.3mf",
  "output_file": "/home/user/working/gridfinity/_cleaned/bin.3mf",
  "backup_file": "/home/user/working/gridfinity/_backups/bin_20260505_143022.3mf",
  "cleaning_result": {
    "auxiliaries_removed": true,
    "auxiliaries_size_bytes": 2048576,
    "metadata_entries_removed": 23,
    "removed_metadata_categories": ["creator", "model_description", "images", "settings"],
    "whitelist_preserved": 2,
    "output_size_reduction_percent": 8.2
  },
  "validation_report": {
    "is_valid": true,
    "structure_ok": true,
    "schema_compliant": true,
    "compatibility_warnings": [],
    "timestamp": "2026-05-05T14:30:22Z"
  },
  "audit_trail": {
    "operation_timestamp": "2026-05-05T14:30:22Z",
    "performed_by": "home.assistant",
    "removed_metadata_snapshot": {...}
  }
}
```

#### 2. Batch Clean Working Group

```http
POST /api/working/groups/{group_id}/clean-batch
Content-Type: application/json

{
  "item_ids": ["item_1", "item_2", "item_3"],
  "preserve_whitelist": [...],
  "output_folder": "working/{group_id}/_cleaned",
  "backup_original": true,
  "stop_on_first_error": false
}

Response (200):
{
  "operation_id": "batch_clean_op_def456",
  "group_id": "group_abc",
  "status": "success",
  "total_items": 3,
  "successful": 3,
  "failed": 0,
  "items": [
    {
      "item_id": "item_1",
      "status": "success",
      "output_file": "...",
      "size_reduction_percent": 8.2
    },
    {
      "item_id": "item_2",
      "status": "success",
      "output_file": "...",
      "size_reduction_percent": 7.5
    },
    {
      "item_id": "item_3",
      "status": "success",
      "output_file": "...",
      "size_reduction_percent": 9.1
    }
  ],
  "aggregate_statistics": {
    "total_original_size_mb": 45.3,
    "total_cleaned_size_mb": 41.8,
    "total_reduction_percent": 7.7,
    "total_metadata_removed": 67,
    "total_auxiliaries_removed": 3
  }
}
```

#### 3. Preview Cleaning (Dry Run)

```http
GET /api/working/items/{item_id}/cleaning-preview
Query params:
  - include_metadata_details: boolean (default: false)

Response (200):
{
  "item_id": "item_xyz789",
  "input_file": "...",
  "input_size_bytes": 2048576,
  "cleaning_preview": {
    "would_remove_auxiliaries": true,
    "auxiliaries_size_bytes": 176512,
    "would_remove_metadata_count": 23,
    "would_remove_metadata_categories": {
      "creator": 3,
      "model_description": 5,
      "images": 8,
      "print_settings": 7
    },
    "estimated_output_size_bytes": 1872064,
    "estimated_reduction_percent": 8.6,
    "whitelist_would_be_preserved": [
      "<metadata name=\"Application\">Bambu Studio</metadata>",
      "<metadata name=\"BambuStudio:3mfVersion\">1.2.3</metadata>"
    ]
  },
  "validation_preview": {
    "current_structure_valid": true,
    "after_cleaning_likely_valid": true,
    "compatibility_issues": []
  },
  "metadata_snapshot": [
    {
      "category": "creator",
      "entries": [
        "<metadata name=\"Title\">Original Model</metadata>",
        "<metadata name=\"Author\">John Doe</metadata>",
        "<metadata name=\"Date\">2026-01-15</metadata>"
      ]
    },
    {...}
  ]
}
```

#### 4. Get Validation Report

```http
GET /api/working/items/{item_id}/validation-report

Response (200):
{
  "item_id": "item_xyz789",
  "file_path": "...",
  "validation_timestamp": "2026-05-05T14:30:22Z",
  "overall_status": "valid",
  "structure_validation": {
    "is_valid_zip": true,
    "has_3d_model_file": true,
    "encoding_valid": true,
    "issues": []
  },
  "xml_validation": {
    "schema_compliant": true,
    "malformed_xml": false,
    "parsing_errors": [],
    "warnings": []
  },
  "metadata_validation": {
    "whitelist_preserved": true,
    "whitelisted_entries": 2,
    "preserved_metadata": [
      "<metadata name=\"Application\">Bambu Studio</metadata>",
      "<metadata name=\"BambuStudio:3mfVersion\">1.2.3</metadata>"
    ]
  },
  "compatibility": {
    "bambu_lab_compatible": true,
    "estimated_print_time": null,
    "warnings": [
      "Large model (>500MB uncompressed) may require slicing optimization"
    ]
  }
}
```

#### 5. Get Cleaning History/Audit Trail

```http
GET /api/working/items/{item_id}/cleaning-history
Query params:
  - limit: int (default: 10)
  - offset: int (default: 0)

Response (200):
{
  "item_id": "item_xyz789",
  "total_cleaning_operations": 2,
  "operations": [
    {
      "operation_id": "clean_op_abc123",
      "timestamp": "2026-05-05T14:30:22Z",
      "performed_by": "home.assistant",
      "status": "success",
      "output_file": "...",
      "metadata_removed": {
        "count": 23,
        "categories": {...},
        "snapshot": [...]
      },
      "validation_status": "passed"
    },
    {...}
  ]
}
```

### Data Models (Request/Response)

```python
# Pydantic models for API contracts

class CleaningOptions(BaseModel):
    """Options for 3MF cleaning operation."""
    preserve_whitelist: List[str] = [
        "<metadata name=\"Application\"",
        "<metadata name=\"BambuStudio:3mfVersion\""
    ]
    output_folder: Optional[str] = None  # Default: working/{group_id}/_cleaned
    backup_original: bool = True
    validate_output: bool = True

class MetadataCategoryCount(BaseModel):
    creator: int = 0
    model_description: int = 0
    images: int = 0
    print_settings: int = 0
    other: int = 0

class CleaningResult(BaseModel):
    auxiliaries_removed: bool
    auxiliaries_size_bytes: int
    metadata_entries_removed: int
    removed_metadata_categories: Dict[str, int]
    whitelist_preserved: int
    output_size_reduction_percent: float

class ValidationReport(BaseModel):
    is_valid: bool
    structure_ok: bool
    schema_compliant: bool
    compatibility_warnings: List[str]
    timestamp: datetime

class CleaningOperationResult(BaseModel):
    operation_id: str
    item_id: str
    status: Literal["success", "failed", "partial"]
    input_file: str
    output_file: str
    backup_file: Optional[str]
    cleaning_result: CleaningResult
    validation_report: ValidationReport
    audit_trail: Dict[str, Any]

class BatchCleaningResult(BaseModel):
    operation_id: str
    group_id: str
    status: Literal["success", "failed", "partial"]
    total_items: int
    successful: int
    failed: int
    items: List[CleaningOperationResult]
    aggregate_statistics: Dict[str, Any]
```

---

## Implementation Phases

### Phase 1: Core Cleaning & Validation (2-3 weeks)

**Deliverables**:
1. `3mf_cleaning_service.py` with core cleaning logic
2. `3mf_validator.py` with validation checks
3. Database schema extensions (new tables, fields)
4. API endpoints (all 5 endpoints above)
5. Unit tests (60+ test cases)
6. CLI tool for batch testing

**Tasks**:
- [ ] Create 3MF extraction/repackaging logic
- [ ] Implement metadata filtering with whitelist
- [ ] Build validation framework
- [ ] Add database schema and migrations
- [ ] Implement all 5 API endpoints
- [ ] Write comprehensive tests
- [ ] Document API contracts
- [ ] Performance testing (large files)

**Database Migrations**:
```sql
-- Add to working_items table
ALTER TABLE working_items ADD COLUMN cleaning_state TEXT DEFAULT NULL;
ALTER TABLE working_items ADD COLUMN cleaned_file_path TEXT DEFAULT NULL;
ALTER TABLE working_items ADD COLUMN last_cleaning_timestamp DATETIME DEFAULT NULL;

-- New audit trail table
CREATE TABLE working_item_cleaning_audit (
    id TEXT PRIMARY KEY,
    working_item_id TEXT NOT NULL,
    operation_timestamp DATETIME NOT NULL,
    performed_by TEXT NOT NULL,
    status TEXT NOT NULL,  -- success, failed
    input_file_size_bytes INTEGER,
    output_file_size_bytes INTEGER,
    backup_file_path TEXT,
    cleaned_file_path TEXT,
    metadata_removed_count INTEGER,
    metadata_removed_categories JSON,
    validation_status TEXT,  -- passed, failed, skipped
    validation_report JSON,
    FOREIGN KEY (working_item_id) REFERENCES working_items(id)
);

-- Metadata snapshot table for audit
CREATE TABLE working_item_metadata_snapshots (
    id TEXT PRIMARY KEY,
    cleaning_audit_id TEXT NOT NULL,
    metadata_category TEXT NOT NULL,
    removed_entries JSON NOT NULL,
    FOREIGN KEY (cleaning_audit_id) REFERENCES working_item_cleaning_audit(id)
);
```

### Phase 2: Dashboard Integration (2 weeks)

**Deliverables**:
1. Custom Lovelace card for cleaning operations
2. Dashboard showing working files with cleaning status
3. Bulk operations UI
4. Cleaning history visualization

**Tasks**:
- [ ] Create Vue.js component for cleaning operations
- [ ] Add state management for batch operations
- [ ] Build metadata diff view
- [ ] Integrate with HA sidebar
- [ ] Add theme support

### Phase 3: Archive Linking & Enrichment (2 weeks)

**Deliverables**:
1. Pre-upload enrichment workflow
2. Automatic filament/print-time metadata injection
3. Archive linking for "cleaned" files

**Tasks**:
- [ ] Query print history for enrichment data
- [ ] Add enrichment to cleaning pipeline
- [ ] Test PATCH tags workflow
- [ ] Document enrichment strategy

### Phase 4: Advanced Features (Future)

- Print profile extraction and comparison
- Filament material detection
- Geometry analysis and complexity scoring
- Direct MakerWorld upload integration

---

## Data Model Extensions

### Database Schema Additions

#### `working_items` Table (Extensions)

```sql
-- Add these columns to existing working_items table
cleaning_state ENUM('not_applicable', 'ready_to_clean', 'in_progress', 'cleaned', 'failed') NULL
cleaned_file_path TEXT NULL
last_cleaning_timestamp DATETIME NULL
cleaning_error_message TEXT NULL
```

#### `working_item_cleaning_audit` Table (NEW)

```sql
CREATE TABLE working_item_cleaning_audit (
    id TEXT PRIMARY KEY,
    working_item_id TEXT NOT NULL,
    working_group_id TEXT NOT NULL,
    
    -- Operation metadata
    operation_timestamp DATETIME NOT NULL,
    performed_by TEXT NOT NULL,  -- "home.assistant" or user ID
    status ENUM('success', 'failed', 'partial') NOT NULL,
    
    -- File information
    input_file_path TEXT NOT NULL,
    input_file_size_bytes INTEGER NOT NULL,
    output_file_path TEXT NULL,
    output_file_size_bytes INTEGER NULL,
    backup_file_path TEXT NULL,
    
    -- Cleaning statistics
    auxiliaries_removed BOOLEAN,
    auxiliaries_size_bytes INTEGER NULL,
    metadata_entries_removed_count INTEGER NULL,
    metadata_categories_removed JSON NULL,  -- {creator: 3, images: 5, ...}
    whitelist_entries_preserved INTEGER NULL,
    size_reduction_percent FLOAT NULL,
    
    -- Validation results
    validation_status ENUM('passed', 'failed', 'skipped') DEFAULT 'skipped',
    validation_report JSON NULL,  -- Full validation result
    
    -- Error tracking
    error_message TEXT NULL,
    error_details JSON NULL,
    
    -- Audit trail
    notes TEXT NULL,
    
    -- Timestamps
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (working_item_id) REFERENCES working_items(id),
    FOREIGN KEY (working_group_id) REFERENCES working_groups(id),
    INDEX idx_working_item (working_item_id),
    INDEX idx_timestamp (operation_timestamp),
    INDEX idx_status (status)
);
```

#### `3mf_metadata_snapshots` Table (NEW)

```sql
CREATE TABLE 3mf_metadata_snapshots (
    id TEXT PRIMARY KEY,
    cleaning_audit_id TEXT NOT NULL,
    
    -- Metadata category
    category TEXT NOT NULL,  -- creator, description, images, settings, etc.
    
    -- Raw XML entries that were removed
    removed_entries JSON NOT NULL,  -- Array of XML strings
    
    -- Metadata details
    entry_count INTEGER NOT NULL,
    total_characters INTEGER NOT NULL,
    
    -- Timestamps
    captured_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (cleaning_audit_id) REFERENCES working_item_cleaning_audit(id),
    INDEX idx_cleaning_audit (cleaning_audit_id),
    INDEX idx_category (category)
);
```

### Data Models (Python)

```python
# domain/models.py additions

class CleaningState(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    READY_TO_CLEAN = "ready_to_clean"
    IN_PROGRESS = "in_progress"
    CLEANED = "cleaned"
    FAILED = "failed"

class CleaningAuditTrail(BaseModel):
    id: str
    working_item_id: str
    working_group_id: str
    operation_timestamp: datetime
    performed_by: str
    status: Literal["success", "failed", "partial"]
    input_file_path: str
    input_file_size_bytes: int
    output_file_path: Optional[str]
    output_file_size_bytes: Optional[int]
    backup_file_path: Optional[str]
    
    # Cleaning results
    auxiliaries_removed: bool
    auxiliaries_size_bytes: Optional[int]
    metadata_entries_removed_count: int
    metadata_categories_removed: Dict[str, int]
    whitelist_entries_preserved: int
    size_reduction_percent: float
    
    # Validation
    validation_status: Literal["passed", "failed", "skipped"]
    validation_report: Optional[ValidationReport]
    
    # Errors
    error_message: Optional[str]
    error_details: Optional[Dict[str, Any]]
    
    created_at: datetime
    updated_at: datetime

class MetadataSnapshot(BaseModel):
    id: str
    cleaning_audit_id: str
    category: str
    removed_entries: List[str]
    entry_count: int
    total_characters: int
    captured_at: datetime
```

---

## Considerations & Risks

### 1. File Integrity & Data Loss

**Risk**: Corrupted output file or loss of important metadata.

**Mitigations**:
- ✅ Always create backup of original before cleaning
- ✅ Validate output ZIP structure before returning
- ✅ Store metadata snapshot in audit trail for recovery
- ✅ Implement rollback mechanism (restore from backup)
- ✅ Comprehensive unit tests with real Bambu Studio files
- ✅ Integration tests against known problematic files

**Implementation**:
```python
# Always backup before cleaning
if not backup_path.exists():
    shutil.copy2(input_path, backup_path)

# Validate output before returning
validation = await validator.validate_3mf(output_path)
if not validation.is_valid:
    raise ValidationError(f"Output validation failed: {validation.issues}")
```

### 2. Performance at Scale

**Risk**: Large files (100MB+) may cause timeout or memory exhaustion.

**Mitigations**:
- ✅ Stream ZIP extraction instead of loading entire file into memory
- ✅ Implement chunked XML parsing for large model files
- ✅ Add configurable timeout (default: 60 seconds per file)
- ✅ Batch operation can process files in sequence, not parallel
- ✅ Monitor memory usage during extraction

**Implementation Approach**:
```python
# Use streaming ZIP extraction
with zipfile.ZipFile(input_path, 'r') as zf:
    # Process files incrementally
    for info in zf.filelist:
        if info.filename == "3D/3dmodel.model":
            # Stream parse XML without loading entire file
            with zf.open(info) as f:
                for line in f:
                    process_line(line.decode('utf-8'))
```

### 3. Metadata Whitelist Completeness

**Risk**: Essential metadata may be removed if whitelist is incomplete.

**Mitigations**:
- ✅ Document whitelist rationale (why these 2 entries are kept)
- ✅ Provide operator override for custom whitelist
- ✅ Preview endpoint shows exactly what will be removed
- ✅ Validation checks that required metadata preserved
- ✅ Start conservative: only remove Auxiliaries + confirmed-safe metadata

**Current Whitelist Rationale**:
- `<metadata name="Application">` — Tells slicer which tool created file (required)
- `<metadata name="BambuStudio:3mfVersion">` — Format version (required for Bambu Studio)

**Risk**: Unknown edge cases in Bambu Studio or other slicer requirements.

**Mitigation**: Phase 1 preserves all metadata by default, only removes Auxiliaries directory. Metadata removal comes in Phase 2 after user feedback.

### 4. Compatibility with Non-Standard 3MF Files

**Risk**: 3MF files from non-Bambu sources may have unexpected structure.

**Mitigations**:
- ✅ Validate ZIP structure before processing
- ✅ Check for required files (3D/3dmodel.model)
- ✅ Error handling for malformed XML
- ✅ Graceful degradation: if cleaning fails, return detailed error
- ✅ Test against files from: Fusion 360, Tinkercad, Prusa, Creality, etc.

**Error Handling**:
```python
try:
    with zipfile.ZipFile(input_path, 'r') as zf:
        if "3D/3dmodel.model" not in zf.namelist():
            raise ValidationError("Missing required 3D/3dmodel.model file")
        # Process...
except zipfile.BadZipFile:
    raise ValidationError(f"File is not a valid ZIP (3MF): {input_path}")
except ET.ParseError as e:
    raise ValidationError(f"XML parse error in 3dmodel.model: {e}")
```

### 5. Disk Space Management

**Risk**: Backup files and cleaned outputs consume disk space quickly.

**Mitigations**:
- ✅ Operator can optionally skip backup (with warning)
- ✅ Cleaned output overwrites input option (requires confirmation)
- ✅ Implement cleanup policy: delete backups older than N days
- ✅ Monitor disk space, warn if < 1GB free
- ✅ Dashboard shows backup/cleaned storage usage

**Configuration**:
```yaml
cleaning:
  backup_policy: "keep_latest_5"  # or "keep_7_days" or "no_backup"
  output_location: "same_folder"  # or "separate_cleaned_folder"
  warn_disk_space_mb: 1000
  auto_cleanup_older_than_days: 30
```

### 6. Audit Trail Explosion

**Risk**: Audit table grows rapidly if user cleans files multiple times.

**Mitigations**:
- ✅ Implement retention policy (keep last N operations)
- ✅ Archive old audit records to JSON files
- ✅ Database query optimization with indexes
- ✅ Pagination for audit trail endpoints

**Schema**:
- Index on `working_item_id` for fast lookups
- Index on `operation_timestamp` for sorting
- Retention policy: keep last 50 operations per item

### 7. Validation False Positives/Negatives

**Risk**: Validator may pass corrupted file or reject valid file.

**Mitigations**:
- ✅ Multiple validation layers: ZIP, XML schema, Bambu compatibility
- ✅ Conservative validation: only fail on confirmed errors
- ✅ Validation warnings vs. errors (don't block on warnings)
- ✅ Manual validation with Bambu Studio after cleaning
- ✅ Collect user feedback on false positives

**Validation Strategy**:
```python
# Level 1: ZIP structure
- Valid ZIP format
- Has 3D/3dmodel.model
- No corrupted entries

# Level 2: XML compliance
- Well-formed XML
- Required elements present
- Encoding valid (UTF-8)

# Level 3: Bambu compatibility (warnings)
- Whitelist metadata present
- No suspicious file patterns
- Size reasonable
```

### 8. Working File Storage Fragmentation

**Risk**: Cleaned files in separate folder may complicate file management.

**Mitigations**:
- ✅ Cleaned output always in predictable location: `{working_group_folder}/_cleaned/`
- ✅ Working item metadata tracks cleaned file path
- ✅ Dashboard shows both original and cleaned versions
- ✅ Option to overwrite original (with backup)
- ✅ Export/archive cleaned files to another location

**Folder Convention**:
```
working/
├── my-project/
│   ├── base.3mf                    (original)
│   ├── lid.3mf                     (original)
│   ├── _cleaned/
│   │   ├── base.3mf                (cleaned)
│   │   └── lid.3mf                 (cleaned)
│   └── _backups/
│       ├── base_20260505_143022.3mf
│       └── lid_20260505_143022.3mf
```

---

## Alternative Approaches

### Alternative 1: Cleaning as Intake Pre-Processing Only

**Approach**: Only offer cleaning during intake workflow, not for Working Files.

**Pros**:
- Simpler scope, faster to implement
- Cleaning triggers are well-defined (upload)
- Less database schema complexity

**Cons**:
- Doesn't address the main use case: cleaning files already in Working folders
- Users must re-upload to clean
- No integration with Working Files stages
- Misses opportunity for enrichment workflow

**Verdict**: ❌ Not recommended—scope is too limited.

---

### Alternative 2: External Task with HA Shell Commands

**Approach**: Instead of sidecar service, use HA shell_command to call 3MFresh CLI.

**Pros**:
- Minimal sidecar changes
- Leverages proven 3MFresh tool
- Lower implementation effort

**Cons**:
- No validation or audit trail in sidecar
- File paths harder to manage (shell escaping)
- No API integration with sidecar database
- Harder to show progress/status in HA
- Difficult to handle errors and recovery
- Batch operations require shell scripting

**Verdict**: ⚠️ Partial alternative for Phase 1 testing, but not production solution.

---

### Alternative 3: Client-Side Cleaning (Browser)

**Approach**: Implement cleaning in JavaScript, run in browser on downloaded files.

**Pros**:
- No server resources needed
- Works offline
- GDPR compliant (no file upload to server)

**Cons**:
- Large files difficult to handle in browser (memory constraints)
- No audit trail for compliance
- No validation without uploading results
- Limited to browser's ZIP handling capabilities
- UX complexity (file download/upload again)

**Verdict**: ⚠️ Viable for future "client-side" mode, but not primary solution.

---

### Alternative 4: Lazy Cleaning (Clean on Export)

**Approach**: Delay cleaning until file is exported/uploaded to external platform.

**Pros**:
- Cleaner workflow (clean only what's being published)
- Fewer temporary files
- Clear trigger (export action)

**Cons**:
- Doesn't help operators who already have files to clean
- Less user control (cleaning is implicit)
- Harder to preview what will be removed
- Batch operations harder to coordinate

**Verdict**: ⚠️ Can be combined with immediate cleaning, not replacement.

---

## Success Criteria

### Phase 1 Success Criteria (Core Functionality)

- [x] **Functional Correctness**
  - All 5 API endpoints working correctly
  - 95%+ of test cases passing (60+ tests)
  - Cleaned files open successfully in Bambu Studio
  - No data loss or corruption

- [x] **Integration**
  - Working items updated with cleaning state
  - Audit trail recorded in database
  - File backups created and accessible
  - Cleaning history queryable via API

- [x] **Performance**
  - Single file cleaning completes in <10 seconds (typical 10-50MB file)
  - Batch cleaning of 10 files completes in <120 seconds
  - Memory usage stays <500MB for large files (up to 500MB)
  - No timeout issues

- [x] **Validation**
  - Output validation runs automatically
  - Validation report shows expected accuracy
  - False positives/negatives logged for improvement

- [x] **Documentation**
  - API documentation complete (all endpoints)
  - Database schema documented
  - Implementation guide for developers
  - Usage guide for operators

### Phase 1 Validation Tests

**Test Scenarios**:
1. Clean typical Bambu Studio downloaded file (10MB)
2. Clean file from external slicer (Fusion 360, Prusa, etc.)
3. Clean file with minimal metadata (should be quick)
4. Clean file with maximum metadata (should remove all non-whitelisted)
5. Clean already-cleaned file (should be idempotent)
6. Batch clean 10 files simultaneously
7. Batch clean with one file failure (error handling)
8. Preview cleaning without modifying file
9. Validate output file integrity
10. Recover from backup after cleaning failure

### Success Metrics

- **User Satisfaction**: Feedback from initial testers (95%+ approval)
- **File Integrity**: 100% of cleaned files pass validation
- **Performance**: All operations complete within SLA
- **Adoption**: Used by 80%+ of operators within 2 weeks of release
- **Support**: <1 issue per 100 cleaning operations

---

## Next Steps

1. **Review & Feedback** (1 week)
   - Share design doc with team
   - Gather feedback on scope, API design, risks
   - Adjust based on feedback

2. **Prototyping** (1 week)
   - Create `3mf_cleaning_service.py` skeleton
   - Test with 3MFresh logic
   - Build first test case

3. **Implementation** (2-3 weeks)
   - Implement core services
   - Add API endpoints
   - Create database schema
   - Write comprehensive tests

4. **Integration Testing** (1 week)
   - Test with real Working Files
   - Test edge cases and error scenarios
   - Performance validation

5. **Documentation & Deployment** (1 week)
   - Finalize API documentation
   - Write operator guide
   - Deploy to main branch

---

## References

- [3MFresh Repository](https://github.com/brossow/3MFresh)
- [3MF File Format Specification](https://3mf.io/3mf-specification/)
- [Model Catalog Architecture](./MODEL_CATALOG_ARCHITECTURE.md)
- [Working Groups Design](./working-groups-and-veneer.md)
- [Issue #1327: Add Clean 3MF functionality to server](https://github.com/rsocko/hass-bambulab-config/issues/1327)

---

**Document Approval**:
- Status: **DRAFT** (Ready for Review)
- Author: Copilot (Design Doc)
- Next Review: After team feedback
- Last Updated: 2026-05-05
