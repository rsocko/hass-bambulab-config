"""
Phase 3.4 Task 1: Export & Migration

Module for exporting model catalog data in multiple formats and
migrating model metadata between schema versions.

Provides:
- JSON export with optional enrichment
- CSV export with configurable columns
- Data validation and sanitization
- Schema version migration (v1 → v2, etc.)
- Import from various formats
- Backup and restore functionality
"""

import json
import csv
from io import StringIO
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import asdict, is_dataclass
from enum import Enum
from datetime import datetime


class ExportFormat(str, Enum):
    """Supported export formats."""
    JSON = "json"
    CSV = "csv"
    JSONL = "jsonl"  # JSON lines (one model per line)


class SchemaVersion(str, Enum):
    """Model schema versions for migrations."""
    V1 = "v1"  # Legacy format
    V2 = "v2"  # Current format with tags as list


class ExportFilter:
    """Filter criteria for exports."""
    
    def __init__(
        self,
        creator: Optional[str] = None,
        collection: Optional[str] = None,
        tags: Optional[List[str]] = None,
        has_prints: bool = False,
        difficulty_level: Optional[str] = None,
        min_success_rate: Optional[float] = None,
        status: Optional[str] = None,
    ):
        """Initialize export filter.
        
        Args:
            creator: Filter by creator name (case-insensitive)
            collection: Filter by collection (case-insensitive)
            tags: Filter by any of these tags
            has_prints: If True, only include models with print history
            difficulty_level: Filter by difficulty (easy/moderate/challenging)
            min_success_rate: Minimum print success rate
            status: Filter by status field
        """
        self.creator = creator.lower() if creator else None
        self.collection = collection.lower() if collection else None
        self.tags = [t.lower() for t in tags] if tags else None
        self.has_prints = has_prints
        self.difficulty_level = difficulty_level
        self.min_success_rate = min_success_rate
        self.status = status

    def matches(self, model: Dict[str, Any]) -> bool:
        """Check if model matches all filter criteria.
        
        Args:
            model: Model dictionary to check
            
        Returns:
            True if model matches all criteria
        """
        # Creator filter
        if self.creator:
            creator = (model.get("creator") or "").lower()
            if self.creator not in creator:
                return False
        
        # Collection filter
        if self.collection:
            collections = [c.lower() for c in model.get("collections", [])]
            if self.collection not in collections:
                return False
        
        # Tags filter (any match)
        if self.tags:
            model_tags = [t.lower() for t in model.get("tags", [])]
            if not any(tag in model_tags for tag in self.tags):
                return False
        
        # Has prints filter
        if self.has_prints:
            print_count = model.get("print_count", 0)
            if print_count == 0:
                return False
        
        # Difficulty filter
        if self.difficulty_level:
            if model.get("difficulty_level") != self.difficulty_level:
                return False
        
        # Success rate filter
        if self.min_success_rate is not None:
            success_rate = model.get("success_rate", 0)
            if success_rate < self.min_success_rate:
                return False
        
        # Status filter
        if self.status:
            if model.get("status") != self.status:
                return False
        
        return True


class ModelCatalogExporter:
    """Export model catalog in various formats."""

    def __init__(self):
        """Initialize exporter."""
        self.supported_formats = [
            ExportFormat.JSON,
            ExportFormat.CSV,
            ExportFormat.JSONL,
        ]

    def export(
        self,
        models: List[Dict[str, Any]],
        format: ExportFormat = ExportFormat.JSON,
        filter_criteria: Optional[ExportFilter] = None,
        include_enrichment: bool = False,
        columns: Optional[List[str]] = None,
        pretty: bool = False,
    ) -> str:
        """Export models in specified format.
        
        Args:
            models: List of model dictionaries
            format: Export format (JSON, CSV, or JSONL)
            filter_criteria: Optional ExportFilter
            include_enrichment: Include enrichment metadata for JSON
            columns: For CSV export, which columns to include
            pretty: For JSON, use pretty printing
            
        Returns:
            Exported data as string
        """
        # Apply filters
        if filter_criteria:
            models = [m for m in models if filter_criteria.matches(m)]
        
        # Export based on format
        if format == ExportFormat.JSON:
            return self._export_json(models, include_enrichment, pretty)
        elif format == ExportFormat.CSV:
            return self._export_csv(models, columns)
        elif format == ExportFormat.JSONL:
            return self._export_jsonl(models, include_enrichment)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _export_json(
        self,
        models: List[Dict[str, Any]],
        include_enrichment: bool = False,
        pretty: bool = False
    ) -> str:
        """Export as JSON."""
        export_data = []
        
        for model in models:
            item = self._prepare_model_for_export(model, include_enrichment)
            export_data.append(item)
        
        if pretty:
            return json.dumps(export_data, indent=2, default=str)
        else:
            return json.dumps(export_data, default=str)

    def _export_jsonl(
        self,
        models: List[Dict[str, Any]],
        include_enrichment: bool = False
    ) -> str:
        """Export as JSONL (one JSON object per line)."""
        lines = []
        
        for model in models:
            item = self._prepare_model_for_export(model, include_enrichment)
            lines.append(json.dumps(item, default=str))
        
        return "\n".join(lines)

    def _export_csv(
        self,
        models: List[Dict[str, Any]],
        columns: Optional[List[str]] = None
    ) -> str:
        """Export as CSV."""
        if not models:
            return ""
        
        # Determine columns if not specified
        if not columns:
            columns = self._get_csv_columns(models)
        
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=columns)
        
        # Write header
        writer.writeheader()
        
        # Write rows
        for model in models:
            row = {}
            for col in columns:
                value = model.get(col, "")
                # Convert lists to comma-separated strings
                if isinstance(value, (list, tuple)):
                    value = ",".join(str(v) for v in value)
                # Convert dicts to JSON strings
                elif isinstance(value, dict):
                    value = json.dumps(value)
                row[col] = value
            writer.writerow(row)
        
        return output.getvalue()

    def _prepare_model_for_export(
        self,
        model: Dict[str, Any],
        include_enrichment: bool = False
    ) -> Dict[str, Any]:
        """Prepare model data for export.
        
        Args:
            model: Model dictionary
            include_enrichment: Include enrichment metadata
            
        Returns:
            Prepared model for export
        """
        prepared = model.copy()
        
        # Add export metadata
        prepared["exported_at"] = datetime.now().isoformat()
        
        # Remove sensitive data
        if "internal_notes" in prepared:
            del prepared["internal_notes"]
        
        # Remove enrichment if not requested
        if not include_enrichment and "enrichment" in prepared:
            del prepared["enrichment"]
        
        return prepared

    def _get_csv_columns(self, models: List[Dict[str, Any]]) -> List[str]:
        """Determine CSV columns from model data.
        
        Args:
            models: List of models
            
        Returns:
            Ordered list of column names
        """
        # Start with core fields in order
        core_fields = [
            "model_ref",
            "name",
            "creator",
            "collections",
            "tags",
            "description",
            "status",
            "print_count",
            "success_rate",
            "difficulty_level",
        ]
        
        # Collect all unique fields from models
        all_fields = set()
        for model in models:
            all_fields.update(model.keys())
        
        # Build final column list: core fields first, then others alphabetically
        columns = []
        for field in core_fields:
            if field in all_fields:
                columns.append(field)
                all_fields.discard(field)
        
        # Add remaining fields alphabetically
        columns.extend(sorted(all_fields))
        
        return columns


class ModelSchemaMigrator:
    """Migrate model metadata between schema versions."""

    def __init__(self):
        """Initialize migrator."""
        self.migrations = {
            ("v1", "v2"): self._migrate_v1_to_v2,
            ("v2", "v1"): self._migrate_v2_to_v1,
        }

    def migrate(
        self,
        model: Dict[str, Any],
        from_version: str,
        to_version: str
    ) -> Dict[str, Any]:
        """Migrate model between versions.
        
        Args:
            model: Model to migrate
            from_version: Source version (v1, v2, etc.)
            to_version: Target version
            
        Returns:
            Migrated model
            
        Raises:
            ValueError: If migration path not supported
        """
        if from_version == to_version:
            return model.copy()
        
        key = (from_version, to_version)
        if key not in self.migrations:
            raise ValueError(f"No migration path from {from_version} to {to_version}")
        
        return self.migrations[key](model)

    def _migrate_v1_to_v2(self, model: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate from v1 (legacy) to v2 (current).
        
        Changes:
        - tags: comma-separated string → list of strings
        - id → model_id (for clarity)
        """
        migrated = model.copy()
        
        # Migrate tags from string to list
        if "tags" in migrated:
            tags = migrated["tags"]
            if isinstance(tags, str):
                migrated["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
            elif isinstance(tags, list):
                migrated["tags"] = tags
        
        # Rename id to model_id if present
        if "id" in migrated and "model_id" not in migrated:
            migrated["model_id"] = migrated.pop("id")
        
        # Add schema version marker
        migrated["schema_version"] = "v2"
        
        return migrated

    def _migrate_v2_to_v1(self, model: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate from v2 (current) to v1 (legacy).
        
        Changes:
        - tags: list of strings → comma-separated string
        - model_id → id
        """
        migrated = model.copy()
        
        # Migrate tags from list to string
        if "tags" in migrated:
            tags = migrated["tags"]
            if isinstance(tags, list):
                migrated["tags"] = ",".join(tags)
            elif isinstance(tags, str):
                migrated["tags"] = tags
        
        # Rename model_id back to id if present
        if "model_id" in migrated and "id" not in migrated:
            migrated["id"] = migrated.pop("model_id")
        
        # Remove schema version marker
        if "schema_version" in migrated:
            del migrated["schema_version"]
        
        return migrated

    def migrate_batch(
        self,
        models: List[Dict[str, Any]],
        from_version: str,
        to_version: str
    ) -> List[Dict[str, Any]]:
        """Migrate a batch of models.
        
        Args:
            models: List of models to migrate
            from_version: Source version
            to_version: Target version
            
        Returns:
            List of migrated models
        """
        return [
            self.migrate(model, from_version, to_version)
            for model in models
        ]


class ModelCatalogImporter:
    """Import model catalog from various formats."""

    def __init__(self):
        """Initialize importer."""
        self.supported_formats = [
            ExportFormat.JSON,
            ExportFormat.CSV,
            ExportFormat.JSONL,
        ]

    def import_data(
        self,
        data: str,
        format: ExportFormat = ExportFormat.JSON,
        from_version: Optional[str] = None,
        to_version: str = "v2"
    ) -> List[Dict[str, Any]]:
        """Import models from data string.
        
        Args:
            data: Data string in specified format
            format: Format of data (JSON, CSV, or JSONL)
            from_version: Original schema version (if migrating)
            to_version: Target schema version
            
        Returns:
            List of imported (and optionally migrated) models
        """
        # Parse based on format
        if format == ExportFormat.JSON:
            models = self._import_json(data)
        elif format == ExportFormat.CSV:
            models = self._import_csv(data)
        elif format == ExportFormat.JSONL:
            models = self._import_jsonl(data)
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        # Migrate if needed
        if from_version and from_version != to_version:
            migrator = ModelSchemaMigrator()
            models = migrator.migrate_batch(models, from_version, to_version)
        
        return models

    def _import_json(self, data: str) -> List[Dict[str, Any]]:
        """Import from JSON."""
        try:
            parsed = json.loads(data)
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict):
                return [parsed]
            else:
                raise ValueError("JSON must be array or object")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

    def _import_jsonl(self, data: str) -> List[Dict[str, Any]]:
        """Import from JSONL."""
        models = []
        for line in data.strip().split("\n"):
            if not line.strip():
                continue
            try:
                model = json.loads(line)
                models.append(model)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in line: {e}")
        return models

    def _import_csv(self, data: str) -> List[Dict[str, Any]]:
        """Import from CSV."""
        models = []
        reader = csv.DictReader(StringIO(data))
        
        for row in reader:
            model = {}
            for key, value in row.items():
                # Convert back from string to appropriate types
                if value == "":
                    model[key] = None
                elif value.lower() in ("true", "false"):
                    model[key] = value.lower() == "true"
                elif value.isdigit():
                    model[key] = int(value)
                else:
                    # Try parsing as JSON for lists/dicts
                    try:
                        if value.startswith("[") or value.startswith("{"):
                            model[key] = json.loads(value)
                        else:
                            # Treat as comma-separated if no spaces and contains comma
                            if "," in value and " " not in value:
                                model[key] = value.split(",")
                            else:
                                model[key] = value
                    except json.JSONDecodeError:
                        model[key] = value
            
            models.append(model)
        
        return models

    def validate_import(self, models: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """Validate imported models.
        
        Args:
            models: List of imported models
            
        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []
        
        for i, model in enumerate(models):
            # Check required fields
            if "model_ref" not in model or not model["model_ref"]:
                errors.append(f"Model {i}: Missing model_ref")
            
            if "name" not in model or not model["name"]:
                errors.append(f"Model {i}: Missing name")
            
            # Validate tags is list
            if "tags" in model and isinstance(model["tags"], str):
                errors.append(f"Model {i}: tags should be list, not string")
            
            # Validate collections is list
            if "collections" in model and isinstance(model["collections"], str):
                errors.append(f"Model {i}: collections should be list, not string")
        
        return len(errors) == 0, errors
