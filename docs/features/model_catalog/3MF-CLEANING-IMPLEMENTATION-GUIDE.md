# 3MF Cleaning Implementation Guide

**Version**: 1.0  
**Date**: 2026-05-05  
**Purpose**: Tactical implementation guidance for Phase 1  
**Companion**: `3MF-CLEANING-AND-VALIDATION-DESIGN.md`

---

## Module Structure Overview

```
sidecars/model_catalog/app/
├── routers/
│   └── working.py
│       ├── @router.post("/groups/{group_id}/items/{item_id}/clean")
│       ├── @router.post("/groups/{group_id}/clean-batch")
│       ├── @router.get("/items/{item_id}/cleaning-preview")
│       ├── @router.get("/items/{item_id}/validation-report")
│       └── @router.get("/items/{item_id}/cleaning-history")
│
├── services/
│   ├── working_groups_service.py (EXISTING)
│   │   ├── clean_working_item() [NEW METHOD]
│   │   ├── batch_clean_working_group() [NEW METHOD]
│   │   ├── get_cleaning_preview() [NEW METHOD]
│   │   └── delegate to 3mf_cleaning_service
│   │
│   └── [NO NEW SERVICE FILE - keep logic in working_groups_service]
│
├── domain/
│   ├── 3mf_cleaner.py (NEW)
│   │   ├── class ThreeMFCleaner
│   │   ├── async def clean_3mf()
│   │   ├── async def extract_metadata_summary()
│   │   └── _parse_3dmodel_xml()
│   │
│   └── 3mf_validator.py (NEW)
│       ├── class ThreeMFValidator
│       ├── async def validate_structure()
│       ├── async def validate_xml_schema()
│       └── async def validate_compatibility()
│
├── db_working.py (EXISTING - extend schema)
│   ├── Add migration for cleaning fields
│   └── Add query helpers for audit trail
│
└── db_3mf_cleaning.py (NEW - audit tables)
    ├── create_cleaning_audit_record()
    ├── create_metadata_snapshot()
    ├── get_cleaning_history()
    └── get_cleaning_audit_by_id()
```

---

## File Implementation Details

### 1. `domain/3mf_cleaner.py` (NEW - 300-400 lines)

**Purpose**: Core 3MF extraction, cleaning, and repackaging logic.

```python
"""
3MF Cleaner Module

Core business logic for extracting, cleaning, and repackaging 3MF files.
Handles ZIP extraction, metadata filtering, and output validation.

No database operations here - just file I/O and data transformation.
"""

import asyncio
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


class CleaningResult(Enum):
    """Cleaning operation result status."""
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial"  # Cleaned but validation warnings
    FAILED = "failed"


@dataclass
class MetadataCategory:
    """Parsed metadata category with entries."""
    name: str
    entries: List[str]
    character_count: int


@dataclass
class CleaningSummary:
    """Summary of cleaning operation results."""
    auxiliaries_removed: bool
    auxiliaries_size_bytes: int
    metadata_entries_removed: int
    metadata_categories_removed: Dict[str, int]
    whitelist_entries_preserved: int
    output_size_reduction_percent: float
    removed_metadata_snapshot: List[MetadataCategory]


class ThreeMFCleaner:
    """Core 3MF file cleaner."""

    DEFAULT_METADATA_WHITELIST = {
        "<metadata name=\"Application\"",
        "<metadata name=\"BambuStudio:3mfVersion\"",
    }

    def __init__(self, temp_dir: Optional[Path] = None):
        """
        Initialize cleaner with optional temp directory.

        Args:
            temp_dir: Directory for temporary extraction. Defaults to system temp.
        """
        self.temp_dir = Path(temp_dir or tempfile.gettempdir())
        self.metadata_whitelist = self.DEFAULT_METADATA_WHITELIST

    async def clean_3mf(
        self,
        input_path: Path,
        output_path: Path,
        preserve_whitelist: Optional[List[str]] = None,
        backup_original: bool = True,
    ) -> Tuple[CleaningResult, CleaningSummary, Optional[str]]:
        """
        Clean a 3MF file by removing unnecessary metadata and Auxiliaries.

        Process:
        1. Create backup of original (optional)
        2. Extract 3MF ZIP contents to temp directory
        3. Remove Auxiliaries/ directory if present
        4. Parse and filter metadata from 3D/3dmodel.model
        5. Repackage into new 3MF file
        6. Validate output structure
        7. Clean up temp files

        Args:
            input_path: Path to original 3MF file
            output_path: Path for cleaned 3MF file
            preserve_whitelist: Metadata prefixes to preserve. Uses DEFAULT_METADATA_WHITELIST if not provided.
            backup_original: Whether to create backup before processing

        Returns:
            Tuple of (status, summary, error_message)
            - status: CleaningResult enum
            - summary: CleaningSummary with statistics
            - error_message: None if successful, error string if failed

        Raises:
            FileNotFoundError: If input file doesn't exist
            zipfile.BadZipFile: If input is not a valid ZIP
            ValueError: If critical file missing (3D/3dmodel.model)
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Set whitelist
        if preserve_whitelist:
            self.metadata_whitelist = set(preserve_whitelist)

        # Create backup if requested
        backup_path = None
        if backup_original:
            backup_path = self._create_backup(input_path)
            logger.info(f"Created backup: {backup_path}")

        # Create temporary extraction directory
        temp_extract_dir = self.temp_dir / f"3mf_clean_{datetime.now().timestamp()}"
        temp_extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Step 1: Extract 3MF (ZIP) contents
            logger.info(f"Extracting 3MF from: {input_path}")
            self._extract_3mf(input_path, temp_extract_dir)

            # Step 2: Remove Auxiliaries directory
            auxiliaries_removed, aux_size = self._remove_auxiliaries(temp_extract_dir)

            # Step 3: Filter metadata from 3D/3dmodel.model
            model_file = temp_extract_dir / "3D" / "3dmodel.model"
            if not model_file.exists():
                raise ValueError(f"Missing required file: 3D/3dmodel.model")

            metadata_removal_result = self._filter_model_metadata(model_file)

            # Step 4: Repackage into new 3MF
            logger.info(f"Repackaging into: {output_path}")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self._repackage_3mf(temp_extract_dir, output_path)

            # Step 5: Validate output
            output_is_valid = self._validate_output_structure(output_path)

            # Create summary
            input_size = input_path.stat().st_size
            output_size = output_path.stat().st_size
            size_reduction_pct = ((input_size - output_size) / input_size) * 100

            summary = CleaningSummary(
                auxiliaries_removed=auxiliaries_removed,
                auxiliaries_size_bytes=aux_size,
                metadata_entries_removed=metadata_removal_result["count"],
                metadata_categories_removed=metadata_removal_result["categories"],
                whitelist_entries_preserved=metadata_removal_result["whitelist_count"],
                output_size_reduction_percent=round(size_reduction_pct, 2),
                removed_metadata_snapshot=metadata_removal_result["snapshot"],
            )

            status = (
                CleaningResult.SUCCESS
                if output_is_valid
                else CleaningResult.PARTIAL_SUCCESS
            )

            logger.info(f"Cleaning complete. Status: {status}, Reduction: {size_reduction_pct:.1f}%")
            return status, summary, None

        except Exception as e:
            error_msg = f"Cleaning failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return CleaningResult.FAILED, None, error_msg

        finally:
            # Clean up temp directory
            if temp_extract_dir.exists():
                shutil.rmtree(temp_extract_dir, ignore_errors=True)
                logger.debug(f"Cleaned temp directory: {temp_extract_dir}")

    async def extract_metadata_summary(
        self, input_path: Path
    ) -> Dict[str, List[str]]:
        """
        Extract and categorize all metadata that would be removed (dry run).

        Returns:
            Dictionary mapping category names to lists of XML metadata entries.
            Example: {
                'creator': ['<metadata name="Author">John Doe</metadata>', ...],
                'description': ['<metadata name="Title">...', ...],
                ...
            }
        """
        input_path = Path(input_path)
        temp_extract_dir = self.temp_dir / f"3mf_preview_{datetime.now().timestamp()}"
        temp_extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._extract_3mf(input_path, temp_extract_dir)
            model_file = temp_extract_dir / "3D" / "3dmodel.model"

            if not model_file.exists():
                return {"error": ["Missing 3D/3dmodel.model"]}

            with open(model_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse and categorize metadata
            categories = self._categorize_metadata(content)
            return categories

        except Exception as e:
            logger.error(f"Error extracting metadata summary: {e}")
            return {"error": [f"Failed to extract metadata: {str(e)}"]}

        finally:
            if temp_extract_dir.exists():
                shutil.rmtree(temp_extract_dir, ignore_errors=True)

    # ===== Private Helper Methods =====

    def _create_backup(self, input_path: Path) -> Path:
        """Create timestamped backup of original file."""
        backup_dir = input_path.parent / "_backups"
        backup_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{input_path.stem}_{timestamp}{input_path.suffix}"

        shutil.copy2(input_path, backup_path)
        return backup_path

    def _extract_3mf(self, input_path: Path, extract_to: Path) -> None:
        """Extract 3MF ZIP contents to directory."""
        with zipfile.ZipFile(input_path, "r") as zip_ref:
            zip_ref.extractall(extract_to)
        logger.debug(f"Extracted {len(zip_ref.namelist())} files")

    def _remove_auxiliaries(self, extract_dir: Path) -> Tuple[bool, int]:
        """
        Remove Auxiliaries directory if present.

        Returns:
            Tuple of (was_removed, size_bytes)
        """
        aux_dir = extract_dir / "Auxiliaries"
        if not aux_dir.exists():
            return False, 0

        # Calculate size before deletion
        size = sum(f.stat().st_size for f in aux_dir.rglob("*") if f.is_file())

        shutil.rmtree(aux_dir)
        logger.info(f"Removed Auxiliaries directory ({size} bytes)")
        return True, size

    def _filter_model_metadata(self, model_file: Path) -> Dict:
        """
        Parse XML and remove non-whitelisted metadata.

        Returns:
            Dictionary with:
            - count: Number of metadata entries removed
            - categories: Dict mapping category names to counts
            - whitelist_count: Number of whitelisted entries preserved
            - snapshot: List of MetadataCategory objects (for audit)
        """
        with open(model_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        removed_lines = []
        preserved_lines = []
        categories_count = {}

        for line in lines:
            stripped = line.lstrip()
            is_metadata = stripped.startswith("<metadata")

            if is_metadata:
                # Check if it matches whitelist
                is_whitelisted = any(
                    stripped.startswith(w) for w in self.metadata_whitelist
                )

                if is_whitelisted:
                    preserved_lines.append(line)
                else:
                    removed_lines.append(line)
                    # Categorize removed metadata
                    category = self._extract_metadata_category(line)
                    categories_count[category] = categories_count.get(category, 0) + 1
            else:
                preserved_lines.append(line)

        # Write filtered XML back
        with open(model_file, "w", encoding="utf-8") as f:
            f.writelines(preserved_lines)

        # Create snapshot of removed metadata
        snapshot = self._create_metadata_snapshot(removed_lines, categories_count)

        logger.info(
            f"Removed {len(removed_lines)} metadata entries "
            f"({len(categories_count)} categories)"
        )

        return {
            "count": len(removed_lines),
            "categories": categories_count,
            "whitelist_count": len([l for l in preserved_lines if "<metadata" in l]),
            "snapshot": snapshot,
        }

    def _extract_metadata_category(self, line: str) -> str:
        """Extract category name from metadata line for classification."""
        if "Author" in line or "Creator" in line:
            return "creator"
        elif "Title" in line or "Description" in line:
            return "description"
        elif "Image" in line:
            return "images"
        elif "Setting" in line or "Filament" in line:
            return "settings"
        elif "Date" in line or "Time" in line:
            return "dates"
        else:
            return "other"

    def _categorize_metadata(self, xml_content: str) -> Dict[str, List[str]]:
        """Parse and categorize all metadata in XML content."""
        categories = {}
        for line in xml_content.split("\n"):
            if "<metadata" in line:
                category = self._extract_metadata_category(line)
                if category not in categories:
                    categories[category] = []
                categories[category].append(line.strip())
        return categories

    def _create_metadata_snapshot(
        self, removed_lines: List[str], categories_count: Dict[str, int]
    ) -> List[MetadataCategory]:
        """Create structured snapshot of removed metadata for audit."""
        snapshot = []
        for category, count in categories_count.items():
            entries = [
                line.strip()
                for line in removed_lines
                if self._extract_metadata_category(line) == category
            ]
            char_count = sum(len(e) for e in entries)
            snapshot.append(
                MetadataCategory(name=category, entries=entries, character_count=char_count)
            )
        return snapshot

    def _repackage_3mf(self, extract_dir: Path, output_path: Path) -> None:
        """Repackage cleaned files back into 3MF ZIP."""
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as new_zip:
            for root, _, files in extract_dir.walk():
                for file in files:
                    file_path = Path(root) / file
                    archive_name = file_path.relative_to(extract_dir)
                    new_zip.write(file_path, archive_name)

        logger.info(f"Repackaged to: {output_path}")

    def _validate_output_structure(self, output_path: Path) -> bool:
        """Validate that output ZIP is valid and has required files."""
        try:
            with zipfile.ZipFile(output_path, "r") as zf:
                # Check for required files
                required_files = ["3D/3dmodel.model", "[Content_Types].xml"]
                for required in required_files:
                    if required not in zf.namelist():
                        logger.warning(f"Missing required file in output: {required}")
                        return False

                # Try to parse model XML (basic check)
                try:
                    with zf.open("3D/3dmodel.model") as f:
                        ET.parse(f)
                except ET.ParseError as e:
                    logger.error(f"Output XML parse error: {e}")
                    return False

            logger.debug("Output structure validation passed")
            return True

        except zipfile.BadZipFile as e:
            logger.error(f"Output is not valid ZIP: {e}")
            return False
```

---

### 2. `domain/3mf_validator.py` (NEW - 250-350 lines)

**Purpose**: 3MF validation logic (structure, XML schema, compatibility).

```python
"""
3MF Validator Module

Validation logic for 3MF file integrity, schema compliance, and
compatibility with target printers/slicers.
"""

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """Validation strictness level."""
    STRICT = "strict"      # Fail on any issue
    MODERATE = "moderate"  # Warn on issues, don't fail
    PERMISSIVE = "permissive"  # Only fail on critical issues


@dataclass
class ValidationIssue:
    """Single validation issue or warning."""
    level: str  # "error", "warning", "info"
    code: str   # Machine-readable code
    message: str
    context: Optional[str] = None  # File/line where issue occurred


@dataclass
class ValidationReport:
    """Complete validation report."""
    is_valid: bool
    file_path: str
    overall_status: str  # "valid", "warnings", "invalid"
    issues: List[ValidationIssue]

    structure_validation: Dict
    xml_validation: Dict
    metadata_validation: Dict
    compatibility: Dict


class ThreeMFValidator:
    """3MF format validator."""

    def __init__(self, level: ValidationLevel = ValidationLevel.MODERATE):
        """Initialize validator with strictness level."""
        self.level = level

    async def validate_3mf(self, file_path: Path) -> ValidationReport:
        """
        Complete validation of 3MF file.

        Includes: structure, XML schema, metadata, compatibility.

        Returns:
            ValidationReport with all validation results and issues.
        """
        file_path = Path(file_path)
        issues = []

        # Step 1: Structure validation
        struct_result, struct_issues = self._validate_structure(file_path)
        issues.extend(struct_issues)

        if not struct_result.get("is_valid_zip"):
            # Can't proceed without valid ZIP
            return ValidationReport(
                is_valid=False,
                file_path=str(file_path),
                overall_status="invalid",
                issues=issues,
                structure_validation=struct_result,
                xml_validation={},
                metadata_validation={},
                compatibility={},
            )

        # Step 2: XML validation
        xml_result, xml_issues = self._validate_xml(file_path)
        issues.extend(xml_issues)

        # Step 3: Metadata validation
        meta_result, meta_issues = self._validate_metadata(file_path)
        issues.extend(meta_issues)

        # Step 4: Compatibility
        compat_result, compat_issues = self._validate_compatibility(file_path)
        issues.extend(compat_issues)

        # Determine overall status
        errors = [i for i in issues if i.level == "error"]
        warnings = [i for i in issues if i.level == "warning"]

        is_valid = len(errors) == 0
        if is_valid and len(warnings) == 0:
            overall_status = "valid"
        elif is_valid and len(warnings) > 0:
            overall_status = "warnings"
        else:
            overall_status = "invalid"

        return ValidationReport(
            is_valid=is_valid,
            file_path=str(file_path),
            overall_status=overall_status,
            issues=issues,
            structure_validation=struct_result,
            xml_validation=xml_result,
            metadata_validation=meta_result,
            compatibility=compat_result,
        )

    def _validate_structure(self, file_path: Path) -> tuple:
        """Validate ZIP structure and required files."""
        issues = []
        result = {
            "is_valid_zip": False,
            "has_required_files": False,
            "file_count": 0,
            "encoding": "unknown",
        }

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                result["is_valid_zip"] = True
                result["file_count"] = len(zf.namelist())

                # Check for required files
                required = ["3D/3dmodel.model", "[Content_Types].xml"]
                has_all = all(f in zf.namelist() for f in required)
                result["has_required_files"] = has_all

                if not has_all:
                    missing = [f for f in required if f not in zf.namelist()]
                    for m in missing:
                        issues.append(
                            ValidationIssue(
                                level="error",
                                code="MISSING_REQUIRED_FILE",
                                message=f"Missing required file: {m}",
                            )
                        )

        except zipfile.BadZipFile as e:
            issues.append(
                ValidationIssue(
                    level="error",
                    code="INVALID_ZIP",
                    message=f"File is not a valid ZIP: {e}",
                )
            )

        return result, issues

    def _validate_xml(self, file_path: Path) -> tuple:
        """Validate XML well-formedness and schema basics."""
        issues = []
        result = {"schema_compliant": True, "parsing_errors": []}

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                with zf.open("3D/3dmodel.model") as f:
                    try:
                        tree = ET.parse(f)
                        result["root_tag"] = tree.getroot().tag
                    except ET.ParseError as e:
                        result["schema_compliant"] = False
                        result["parsing_errors"].append(str(e))
                        issues.append(
                            ValidationIssue(
                                level="error",
                                code="XML_PARSE_ERROR",
                                message=f"Invalid XML in 3dmodel.model: {e}",
                            )
                        )

        except Exception as e:
            issues.append(
                ValidationIssue(
                    level="error",
                    code="XML_READ_ERROR",
                    message=f"Cannot read model XML: {e}",
                )
            )

        return result, issues

    def _validate_metadata(self, file_path: Path) -> tuple:
        """Validate metadata integrity."""
        issues = []
        result = {"has_whitelisted_metadata": False, "whitelisted_entries": []}

        whitelist = [
            "<metadata name=\"Application\"",
            "<metadata name=\"BambuStudio:3mfVersion\"",
        ]

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                with zf.open("3D/3dmodel.model") as f:
                    content = f.read().decode("utf-8")

                    found_entries = []
                    for line in content.split("\n"):
                        for w in whitelist:
                            if w in line:
                                found_entries.append(line.strip())

                    if found_entries:
                        result["has_whitelisted_metadata"] = True
                        result["whitelisted_entries"] = found_entries
                    else:
                        issues.append(
                            ValidationIssue(
                                level="warning",
                                code="NO_WHITELISTED_METADATA",
                                message="No whitelisted metadata found (Application, BambuStudio:3mfVersion)",
                            )
                        )

        except Exception as e:
            issues.append(
                ValidationIssue(
                    level="warning",
                    code="METADATA_CHECK_ERROR",
                    message=f"Cannot validate metadata: {e}",
                )
            )

        return result, issues

    def _validate_compatibility(self, file_path: Path) -> tuple:
        """Validate compatibility with Bambu Studio/printers."""
        issues = []
        result = {"compatible": True, "warnings": []}

        try:
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            if file_size_mb > 200:
                result["warnings"].append(
                    f"Large file ({file_size_mb:.1f}MB) may require optimization"
                )
                issues.append(
                    ValidationIssue(
                        level="warning",
                        code="LARGE_FILE",
                        message=f"File size {file_size_mb:.1f}MB may cause slicing delays",
                    )
                )

        except Exception as e:
            logger.warning(f"Compatibility check error: {e}")

        return result, issues
```

---

### 3. `db_3mf_cleaning.py` (NEW - 200+ lines)

**Purpose**: Database operations for cleaning audit trail and metadata snapshots.

```python
"""
3MF Cleaning Database Module

Database operations for storing cleaning audit trails, metadata snapshots,
and validation reports.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4
import logging

logger = logging.getLogger(__name__)


def create_cleaning_audit_record(
    db_module,
    working_item_id: str,
    working_group_id: str,
    input_file_path: str,
    input_file_size_bytes: int,
    output_file_path: Optional[str],
    output_file_size_bytes: Optional[int],
    backup_file_path: Optional[str],
    status: str,
    cleaning_summary: Dict,
    validation_report: Optional[Dict],
    performed_by: str = "home.assistant",
    error_message: Optional[str] = None,
) -> str:
    """
    Create new cleaning audit record.

    Returns:
        Record ID
    """
    record_id = str(uuid4())

    conn = sqlite3.connect(db_module.DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO working_item_cleaning_audit (
                id, working_item_id, working_group_id,
                operation_timestamp, performed_by, status,
                input_file_path, input_file_size_bytes,
                output_file_path, output_file_size_bytes,
                backup_file_path,
                auxiliaries_removed, auxiliaries_size_bytes,
                metadata_entries_removed_count, metadata_categories_removed,
                whitelist_entries_preserved, size_reduction_percent,
                validation_status, validation_report,
                error_message, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                working_item_id,
                working_group_id,
                datetime.utcnow().isoformat(),
                performed_by,
                status,
                str(input_file_path),
                input_file_size_bytes,
                str(output_file_path) if output_file_path else None,
                output_file_size_bytes,
                str(backup_file_path) if backup_file_path else None,
                cleaning_summary.get("auxiliaries_removed", False),
                cleaning_summary.get("auxiliaries_size_bytes", 0),
                cleaning_summary.get("metadata_entries_removed", 0),
                json.dumps(cleaning_summary.get("metadata_categories_removed", {})),
                cleaning_summary.get("whitelist_entries_preserved", 0),
                cleaning_summary.get("output_size_reduction_percent", 0),
                "passed" if validation_report and validation_report.get("is_valid") else "skipped",
                json.dumps(validation_report) if validation_report else None,
                error_message,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        logger.info(f"Created cleaning audit record: {record_id}")
        return record_id

    finally:
        conn.close()


def get_cleaning_history(
    db_module,
    working_item_id: str,
    limit: int = 10,
    offset: int = 0,
) -> List[Dict]:
    """
    Get cleaning history for a working item.

    Returns:
        List of cleaning audit records (most recent first)
    """
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT * FROM working_item_cleaning_audit
            WHERE working_item_id = ?
            ORDER BY operation_timestamp DESC
            LIMIT ? OFFSET ?
            """,
            (working_item_id, limit, offset),
        )

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    finally:
        conn.close()


def update_working_item_cleaning_state(
    db_module,
    working_item_id: str,
    cleaning_state: str,
    cleaned_file_path: Optional[str],
    cleaning_audit_record_id: str,
) -> None:
    """
    Update working item with cleaning state and audit trail link.

    Args:
        working_item_id: ID of working item
        cleaning_state: State like 'cleaned', 'failed'
        cleaned_file_path: Path to cleaned 3MF file
        cleaning_audit_record_id: Link to audit record
    """
    conn = sqlite3.connect(db_module.DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE working_items
            SET cleaning_state = ?,
                cleaned_file_path = ?,
                last_cleaning_timestamp = ?,
                last_cleaning_audit_id = ?
            WHERE id = ?
            """,
            (
                cleaning_state,
                cleaned_file_path,
                datetime.utcnow().isoformat(),
                cleaning_audit_record_id,
                working_item_id,
            ),
        )
        conn.commit()

    finally:
        conn.close()
```

---

### 4. Updates to `services/working_groups_service.py` (Extensions)

**Add these methods** to existing `WorkingGroupsService` class:

```python
# Add to existing WorkingGroupsService class

async def clean_working_item(
    self,
    working_group_id: str,
    item_id: str,
    options: dict = None,
) -> dict:
    """
    Clean a single working item's 3MF file.

    Args:
        working_group_id: ID of working group
        item_id: ID of working item (must be 3MF file)
        options: Cleaning options (backup_original, validate_output, etc.)

    Returns:
        {
            "status": "success|failed",
            "operation_id": "...",
            "output_file": "...",
            "cleaning_summary": {...},
            "validation_report": {...},
        }
    """
    options = options or {}

    try:
        # 1. Get working item
        item = self.db_working.get_working_item(item_id)
        if not item:
            raise ValueError(f"Working item not found: {item_id}")

        if not item["file_path"].endswith(".3mf"):
            raise ValueError(f"Item is not a 3MF file: {item['file_path']}")

        input_path = Path(item["file_path"])
        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        # 2. Determine output path
        output_folder = Path(input_path.parent) / "_cleaned"
        output_path = output_folder / input_path.name

        # 3. Clean using 3MFCleaner
        cleaner = ThreeMFCleaner()
        status, summary, error = await cleaner.clean_3mf(
            input_path,
            output_path,
            backup_original=options.get("backup_original", True),
        )

        # 4. Validate output (optional)
        validation_report = None
        if options.get("validate_output", True):
            validator = ThreeMFValidator()
            validation_report = await validator.validate_3mf(output_path)

        # 5. Create audit trail
        import sidecars.model_catalog.app.db_3mf_cleaning as db_cleaning
        audit_id = db_cleaning.create_cleaning_audit_record(
            self.db_working,
            working_item_id=item_id,
            working_group_id=working_group_id,
            input_file_path=str(input_path),
            input_file_size_bytes=input_path.stat().st_size,
            output_file_path=str(output_path) if status == "success" else None,
            output_file_size_bytes=output_path.stat().st_size if output_path.exists() else None,
            backup_file_path=None,  # Determined by cleaner
            status=status.value,
            cleaning_summary=summary.__dict__ if summary else {},
            validation_report=validation_report.__dict__ if validation_report else None,
        )

        # 6. Update working item state
        db_cleaning.update_working_item_cleaning_state(
            self.db_working,
            working_item_id=item_id,
            cleaning_state="cleaned" if status == "success" else "failed",
            cleaned_file_path=str(output_path) if status == "success" else None,
            cleaning_audit_record_id=audit_id,
        )

        return {
            "status": "success" if status == "success" else "failed",
            "operation_id": audit_id,
            "output_file": str(output_path) if status == "success" else None,
            "cleaning_summary": summary.__dict__ if summary else None,
            "validation_report": validation_report.__dict__ if validation_report else None,
            "error": error,
        }

    except Exception as e:
        logger.error(f"Error cleaning working item: {e}", exc_info=True)
        return {
            "status": "failed",
            "error": str(e),
        }

async def batch_clean_working_group(
    self,
    working_group_id: str,
    options: dict = None,
) -> dict:
    """
    Clean all 3MF files in a working group.

    Returns batch results with per-item status and aggregated statistics.
    """
    options = options or {}

    try:
        # Get all items in group
        items = self.db_working.get_working_items_for_group(working_group_id)
        
        # Filter to 3MF files only
        3mf_items = [i for i in items if i["file_path"].endswith(".3mf")]

        if not 3mf_items:
            return {
                "status": "no_items",
                "message": "No 3MF files found in working group",
                "total_items": 0,
            }

        results = []
        total_original_size = 0
        total_cleaned_size = 0
        total_metadata_removed = 0

        for item in 3mf_items:
            result = await self.clean_working_item(
                working_group_id,
                item["id"],
                options,
            )
            results.append(result)

            if result["status"] == "success":
                summary = result["cleaning_summary"]
                total_original_size += summary["auxiliaries_size_bytes"]
                total_cleaned_size += item.get("file_size", 0)  # Approximate
                total_metadata_removed += summary["metadata_entries_removed"]

        # Count successes/failures
        successful = sum(1 for r in results if r["status"] == "success")
        failed = sum(1 for r in results if r["status"] == "failed")

        return {
            "status": "success",
            "total_items": len(3mf_items),
            "successful": successful,
            "failed": failed,
            "items": results,
            "aggregate_statistics": {
                "total_metadata_removed": total_metadata_removed,
                "total_size_reduction_mb": (total_original_size - total_cleaned_size) / (1024 * 1024),
            },
        }

    except Exception as e:
        logger.error(f"Error batch cleaning: {e}", exc_info=True)
        return {
            "status": "failed",
            "error": str(e),
        }

async def get_cleaning_preview(
    self,
    item_id: str,
    include_metadata_details: bool = False,
) -> dict:
    """
    Preview what WILL BE removed without modifying the file.

    Returns metadata summary and size estimates.
    """
    try:
        item = self.db_working.get_working_item(item_id)
        if not item:
            raise ValueError(f"Working item not found: {item_id}")

        input_path = Path(item["file_path"])

        cleaner = ThreeMFCleaner()
        metadata_summary = await cleaner.extract_metadata_summary(input_path)

        return {
            "status": "success",
            "item_id": item_id,
            "file_path": str(input_path),
            "file_size_mb": input_path.stat().st_size / (1024 * 1024),
            "cleaning_preview": {
                "metadata_summary": metadata_summary,
                "estimated_metadata_removal": len(metadata_summary.get("other", [])),
            },
        }

    except Exception as e:
        logger.error(f"Error generating cleaning preview: {e}")
        return {
            "status": "failed",
            "error": str(e),
        }
```

---

### 5. Updates to `routers/working.py`

**Add these endpoints** to existing working routes:

```python
# Add to existing working.py router

@router.post("/groups/{group_id}/items/{item_id}/clean")
async def clean_working_item(
    group_id: str,
    item_id: str,
    request: CleanRequest,
    state: AppState = Depends(get_app_state),
):
    """Clean a single working item's 3MF file."""
    service = WorkingGroupsService(state.db)
    result = await service.clean_working_item(group_id, item_id, request.dict())
    
    if result["status"] == "failed":
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result


@router.post("/groups/{group_id}/clean-batch")
async def batch_clean_working_group(
    group_id: str,
    request: BatchCleanRequest,
    state: AppState = Depends(get_app_state),
):
    """Clean all 3MF files in a working group."""
    service = WorkingGroupsService(state.db)
    result = await service.batch_clean_working_group(group_id, request.dict())
    
    if result["status"] == "failed":
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result


@router.get("/items/{item_id}/cleaning-preview")
async def get_cleaning_preview(
    item_id: str,
    include_metadata_details: bool = False,
    state: AppState = Depends(get_app_state),
):
    """Preview what will be removed from a 3MF file."""
    service = WorkingGroupsService(state.db)
    result = await service.get_cleaning_preview(item_id, include_metadata_details)
    
    if result["status"] == "failed":
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result


@router.get("/items/{item_id}/cleaning-history")
async def get_cleaning_history(
    item_id: str,
    limit: int = 10,
    offset: int = 0,
    state: AppState = Depends(get_app_state),
):
    """Get cleaning history and audit trail for a working item."""
    import sidecars.model_catalog.app.db_3mf_cleaning as db_cleaning
    
    history = db_cleaning.get_cleaning_history(state.db, item_id, limit, offset)
    return {
        "item_id": item_id,
        "total_operations": len(history),
        "operations": history,
    }
```

---

## Testing Strategy

### Unit Tests (`tests/3mf_cleaning/`)

1. **test_cleaner.py**
   - Test 3MF extraction
   - Test metadata filtering
   - Test Auxiliaries removal
   - Test repackaging
   - Test large file handling

2. **test_validator.py**
   - Test ZIP validation
   - Test XML parsing
   - Test metadata preservation
   - Test compatibility checks

3. **test_database.py**
   - Test audit record creation
   - Test history retrieval
   - Test metadata snapshots

### Integration Tests

1. Clean real Bambu Studio downloaded file
2. Clean file from external slicer
3. Batch operations
4. Error handling (corrupted files, missing files)
5. Backup and recovery workflow

### Performance Tests

- Time to clean 10MB file: <5 seconds
- Time to clean 100MB file: <30 seconds
- Memory usage: <500MB peak
- Batch operation of 10 files: <120 seconds

---

## Development Checklist

- [ ] Create `domain/3mf_cleaner.py` (core logic)
- [ ] Create `domain/3mf_validator.py` (validation logic)
- [ ] Create `db_3mf_cleaning.py` (audit trail)
- [ ] Add database schema migrations
- [ ] Add API endpoints to `routers/working.py`
- [ ] Extend `services/working_groups_service.py`
- [ ] Write comprehensive unit tests
- [ ] Write integration tests
- [ ] Performance testing
- [ ] Documentation
- [ ] Code review
- [ ] Deploy to development
- [ ] User acceptance testing

---

## Error Handling Best Practices

1. **Always backup before modifying**
   ```python
   if backup_original:
       backup_path = cleaner._create_backup(input_path)
   ```

2. **Validate output before returning**
   ```python
   if not validator._validate_output_structure(output_path):
       raise ValidationError("Output validation failed")
   ```

3. **Store detailed error context**
   ```python
   audit_record = {
       "status": "failed",
       "error_message": str(e),
       "error_context": traceback.format_exc(),
   }
   ```

4. **Provide recovery mechanism**
   ```python
   # User can restore from backup
   if backup_path.exists():
       shutil.copy2(backup_path, input_path)
   ```

---

## Configuration & Environment Variables

```yaml
# config.yaml or env
cleaning:
  enabled: true
  temp_dir: "/tmp/3mf_cleaning"
  backup_policy: "keep_latest_5"
  backup_retention_days: 30
  validate_output: true
  max_file_size_mb: 500
  timeout_seconds: 60
  whitelist_default:
    - "<metadata name=\"Application\""
    - "<metadata name=\"BambuStudio:3mfVersion\""
```

---

**Next Steps**:
1. Review implementation structure with team
2. Begin Phase 1 implementation starting with `3mf_cleaner.py`
3. Develop unit tests in parallel
4. Integration testing with real Working Files
