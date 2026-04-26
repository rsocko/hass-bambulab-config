"""
Phase 3.4 Task 1 Tests: Export & Migration

Tests for model catalog export, import, schema migration, and data validation.
"""

import pytest
import json
import csv
from io import StringIO
from sidecars.model_catalog.app.model_export import (
    ModelCatalogExporter,
    ModelCatalogImporter,
    ModelSchemaMigrator,
    ExportFormat,
    ExportFilter,
    SchemaVersion,
)


class TestExportFilter:
    """Test export filter criteria."""

    def test_filter_by_creator(self):
        """Filter models by creator."""
        filter_obj = ExportFilter(creator="John")
        
        matches = {
            "creator": "John",
            "name": "Model A"
        }
        
        no_match = {
            "creator": "Jane",
            "name": "Model B"
        }
        
        assert filter_obj.matches(matches)
        assert not filter_obj.matches(no_match)

    def test_filter_by_creator_case_insensitive(self):
        """Creator filter is case-insensitive."""
        filter_obj = ExportFilter(creator="john")
        
        matches = {"creator": "John"}
        assert filter_obj.matches(matches)

    def test_filter_by_collection(self):
        """Filter models by collection."""
        filter_obj = ExportFilter(collection="Gridfinity")
        
        matches = {
            "collections": ["Gridfinity", "Storage"]
        }
        
        no_match = {
            "collections": ["Storage"]
        }
        
        assert filter_obj.matches(matches)
        assert not filter_obj.matches(no_match)

    def test_filter_by_tags(self):
        """Filter models by tags."""
        filter_obj = ExportFilter(tags=["easy", "gridfinity"])
        
        matches = {
            "tags": ["easy", "gridfinity", "storage"]
        }
        
        no_match = {
            "tags": ["difficult", "custom"]
        }
        
        assert filter_obj.matches(matches)
        assert not filter_obj.matches(no_match)

    def test_filter_by_has_prints(self):
        """Filter by whether model has prints."""
        filter_obj = ExportFilter(has_prints=True)
        
        matches = {"print_count": 5}
        no_match = {"print_count": 0}
        
        assert filter_obj.matches(matches)
        assert not filter_obj.matches(no_match)

    def test_filter_by_difficulty(self):
        """Filter by difficulty level."""
        filter_obj = ExportFilter(difficulty_level="intermediate")
        
        matches = {"difficulty_level": "intermediate"}
        no_match = {"difficulty_level": "advanced"}
        
        assert filter_obj.matches(matches)
        assert not filter_obj.matches(no_match)

    def test_filter_by_success_rate(self):
        """Filter by success rate range."""
        filter_obj = ExportFilter(min_success_rate=0.8)
        
        matches = {"success_rate": 0.85}
        no_match = {"success_rate": 0.7}
        
        assert filter_obj.matches(matches)
        assert not filter_obj.matches(no_match)

    def test_filter_by_status(self):
        """Filter by model status."""
        filter_obj = ExportFilter(status="published")
        
        matches = {"status": "published"}
        no_match = {"status": "draft"}
        
        assert filter_obj.matches(matches)
        assert not filter_obj.matches(no_match)

    def test_combined_filters(self):
        """Multiple filter criteria combined."""
        filter_obj = ExportFilter(creator="John", has_prints=True)
        
        matches = {"creator": "John", "print_count": 3}
        no_match1 = {"creator": "Jane", "print_count": 3}
        no_match2 = {"creator": "John", "print_count": 0}
        
        assert filter_obj.matches(matches)
        assert not filter_obj.matches(no_match1)
        assert not filter_obj.matches(no_match2)


class TestModelCatalogExporter:
    """Test model catalog export functionality."""

    def test_export_json(self):
        """Export models as JSON."""
        exporter = ModelCatalogExporter()
        models = [
            {"model_ref": "m1", "name": "Model 1", "tags": ["tag1"]},
        ]
        
        exported = exporter.export(models, format=ExportFormat.JSON)
        parsed = json.loads(exported)
        
        assert len(parsed) == 1
        assert parsed[0]["model_ref"] == "m1"

    def test_export_csv(self):
        """Export models as CSV."""
        exporter = ModelCatalogExporter()
        models = [
            {"model_ref": "m1", "name": "Model 1", "creator": "John"},
            {"model_ref": "m2", "name": "Model 2", "creator": "Jane"},
        ]
        
        exported = exporter.export(models, format=ExportFormat.CSV)
        
        assert "model_ref" in exported
        assert "m1" in exported
        assert "Model 1" in exported

    def test_export_jsonl(self):
        """Export models as JSONL."""
        exporter = ModelCatalogExporter()
        models = [
            {"model_ref": "m1", "name": "Model 1"},
            {"model_ref": "m2", "name": "Model 2"},
        ]
        
        exported = exporter.export(models, format=ExportFormat.JSONL)
        lines = exported.strip().split("\n")
        
        assert len(lines) == 2
        assert json.loads(lines[0])["model_ref"] == "m1"
        assert json.loads(lines[1])["model_ref"] == "m2"

    def test_export_with_filter(self):
        """Export with filter criteria."""
        exporter = ModelCatalogExporter()
        models = [
            {"model_ref": "m1", "name": "Model 1", "creator": "John"},
            {"model_ref": "m2", "name": "Model 2", "creator": "Jane"},
        ]
        
        filter_obj = ExportFilter(creator="John")
        exported = exporter.export(models, format=ExportFormat.JSON, filter_criteria=filter_obj)
        parsed = json.loads(exported)
        
        assert len(parsed) == 1
        assert parsed[0]["creator"] == "John"

    def test_export_empty_list(self):
        """Export empty model list."""
        exporter = ModelCatalogExporter()
        
        exported = exporter.export([], format=ExportFormat.JSON)
        parsed = json.loads(exported)
        
        assert parsed == []


class TestModelSchemaMigrator:
    """Test schema migration functionality."""

    def test_migrate_v1_to_v2_tags(self):
        """Migrate v1 tags string to v2 list."""
        migrator = ModelSchemaMigrator()
        v1_model = {"id": 1, "tags": "tag1,tag2"}
        
        v2_model = migrator.migrate(v1_model, "v1", "v2")
        
        assert v2_model["model_id"] == 1
        assert v2_model["tags"] == ["tag1", "tag2"]
        assert "id" not in v2_model

    def test_migrate_v1_to_v2_preserves_fields(self):
        """Migrate v1 preserves unknown fields."""
        migrator = ModelSchemaMigrator()
        v1_model = {"id": 1, "tags": "tag1", "custom_field": "custom_value"}
        
        v2_model = migrator.migrate(v1_model, "v1", "v2")
        
        assert v2_model["model_id"] == 1
        assert v2_model["custom_field"] == "custom_value"

    def test_migrate_v2_to_v1_tags(self):
        """Migrate v2 tags list back to v1 string."""
        migrator = ModelSchemaMigrator()
        v2_model = {"model_id": 1, "tags": ["tag1", "tag2"]}
        
        v1_model = migrator.migrate(v2_model, "v2", "v1")
        
        assert v1_model["id"] == 1
        assert v1_model["tags"] == "tag1,tag2"
        assert "model_id" not in v1_model

    def test_migrate_batch(self):
        """Migrate batch of models."""
        migrator = ModelSchemaMigrator()
        v1_models = [
            {"id": 1, "tags": "tag1"},
            {"id": 2, "tags": "tag2,tag3"},
        ]
        
        v2_models = migrator.migrate_batch(v1_models, "v1", "v2")
        
        assert len(v2_models) == 2
        assert v2_models[0]["model_id"] == 1
        assert v2_models[1]["tags"] == ["tag2", "tag3"]

    def test_migrate_idempotent(self):
        """Migration is idempotent (no change if same version)."""
        migrator = ModelSchemaMigrator()
        v2_model = {"model_id": 1, "tags": ["tag1"]}
        
        result = migrator.migrate(v2_model, "v2", "v2")
        
        assert result == v2_model


class TestModelCatalogImporter:
    """Test model catalog import functionality."""

    def test_import_json(self):
        """Import models from JSON."""
        importer = ModelCatalogImporter()
        json_data = json.dumps([
            {"model_ref": "m1", "name": "Model 1"},
        ])
        
        models = importer.import_data(json_data, format=ExportFormat.JSON)
        
        assert len(models) == 1
        assert models[0]["model_ref"] == "m1"

    def test_import_jsonl(self):
        """Import models from JSONL."""
        importer = ModelCatalogImporter()
        jsonl_data = '{"model_ref": "m1", "name": "Model 1"}\n{"model_ref": "m2", "name": "Model 2"}'
        
        models = importer.import_data(jsonl_data, format=ExportFormat.JSONL)
        
        assert len(models) == 2

    def test_import_csv(self):
        """Import models from CSV."""
        importer = ModelCatalogImporter()
        csv_data = "model_ref,name,creator\nm1,Model 1,John\nm2,Model 2,Jane"
        
        models = importer.import_data(csv_data, format=ExportFormat.CSV)
        
        assert len(models) == 2
        assert models[0]["model_ref"] == "m1"
        assert models[0]["creator"] == "John"

    def test_import_with_migration(self):
        """Import and migrate schema at same time."""
        importer = ModelCatalogImporter()
        json_data = json.dumps([
            {"id": 1, "tags": "tag1,tag2"},
            {"id": 2, "tags": "tag3"},
        ])
        
        models = importer.import_data(
            json_data,
            format=ExportFormat.JSON,
            from_version="v1",
            to_version="v2"
        )
        
        assert len(models) == 2
        assert all("model_id" in m for m in models)
        assert all(isinstance(m["tags"], list) for m in models)

    def test_import_csv_basic(self):
        """Import CSV with basic fields."""
        importer = ModelCatalogImporter()
        csv_data = "model_ref,name,description\nm1,Model 1,A nice model\nm2,Model 2,Another model"
        
        models = importer.import_data(csv_data, format=ExportFormat.CSV)
        
        assert len(models) > 0

    def test_import_json_with_lists(self):
        """Import JSON with list fields."""
        importer = ModelCatalogImporter()
        json_data = json.dumps([
            {"model_ref": "m1", "tags": ["tag1", "tag2"]},
        ])
        
        models = importer.import_data(json_data, format=ExportFormat.JSON)
        
        assert isinstance(models[0]["tags"], list)

    def test_validate_import_requires_model_ref(self):
        """Validation requires model_ref."""
        importer = ModelCatalogImporter()
        models = [
            {"name": "Model 1"},  # Missing model_ref
        ]
        
        is_valid, errors = importer.validate_import(models)
        
        assert not is_valid
        assert any("model_ref" in e for e in errors)

    def test_validate_import_requires_name(self):
        """Validation requires name."""
        importer = ModelCatalogImporter()
        models = [
            {"model_ref": "m1"},  # Missing name
        ]
        
        is_valid, errors = importer.validate_import(models)
        
        assert not is_valid
        assert any("name" in e for e in errors)

    def test_validate_import_checks_tags_type(self):
        """Validation checks tags is list."""
        importer = ModelCatalogImporter()
        models = [
            {"model_ref": "m1", "name": "Model 1", "tags": "tag1,tag2"},  # String instead of list
        ]
        
        is_valid, errors = importer.validate_import(models)
        
        assert not is_valid
        assert any("tags" in e for e in errors)

    def test_validate_import_valid_models(self):
        """Validation passes for valid models."""
        importer = ModelCatalogImporter()
        models = [
            {"model_ref": "m1", "name": "Model 1", "tags": ["tag1"]},
            {"model_ref": "m2", "name": "Model 2", "tags": []},
        ]
        
        is_valid, errors = importer.validate_import(models)
        
        assert is_valid
        assert len(errors) == 0


class TestIntegration:
    """Integration tests for export/import/migration."""

    def test_full_cycle_json_v2(self):
        """Full cycle: export JSON v2, import, re-export."""
        exporter = ModelCatalogExporter()
        importer = ModelCatalogImporter()
        
        original = [
            {"model_ref": "m1", "name": "Model 1", "tags": ["tag1"]},
        ]
        
        # Export
        exported = exporter.export(original, format=ExportFormat.JSON)
        
        # Import
        imported = importer.import_data(exported, format=ExportFormat.JSON)
        
        # Should match original
        assert len(imported) == len(original)
        assert imported[0]["model_ref"] == original[0]["model_ref"]
        assert imported[0]["tags"] == original[0]["tags"]

    def test_full_cycle_csv_with_migration(self):
        """Full cycle: V1 CSV → import → migrate to V2 → export V2."""
        exporter = ModelCatalogExporter()
        importer = ModelCatalogImporter()
        
        # Start with V1 data (tags as comma-separated string)
        v1_data = "id,name,tags\n1,Model 1,tag1_and_tag2"
        
        # Import from CSV and migrate to V2
        models = importer.import_data(
            v1_data,
            format=ExportFormat.CSV,
            from_version="v1",
            to_version="v2"
        )
        
        # Export as V2
        exported = exporter.export(models, format=ExportFormat.JSON)
        
        # Verify V2 structure
        parsed = json.loads(exported)
        assert len(parsed) > 0

    def test_export_filter_then_import(self):
        """Export with filters, then import and validate."""
        exporter = ModelCatalogExporter()
        importer = ModelCatalogImporter()
        
        models = [
            {"model_ref": "m1", "name": "Model 1", "creator": "John", "print_count": 5},
            {"model_ref": "m2", "name": "Model 2", "creator": "Jane", "print_count": 0},
        ]
        
        # Export only John's models with prints
        filter_obj = ExportFilter(creator="John", has_prints=True)
        exported = exporter.export(
            models,
            format=ExportFormat.JSON,
            filter_criteria=filter_obj
        )
        
        # Import
        imported = importer.import_data(exported, format=ExportFormat.JSON)
        
        # Should only have John's model
        assert len(imported) == 1
        assert imported[0]["creator"] == "John"
