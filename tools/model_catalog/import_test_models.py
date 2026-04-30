#!/usr/bin/env python3
"""
Import test models from assets/model_catalog/inbox into the local model catalog.

Usage:
    python import_test_models.py [--api-url http://localhost:8123]

This script:
1. Scans assets/model_catalog/inbox/ for .3mf/.stl files
2. Reads optional .yaml metadata files for each model
3. Creates local model entries via REST API
4. Associates geometry files as assets
5. Moves processed files to assets/model_catalog/validated/

Metadata YAML format:
    local_model_id: "my-model"
    model_name: "My Test Model"
    model_description: "Test description"
    creator_name: "Test Creator"
    collection_names: ["collection1"]
    keyword_names: ["keyword1", "keyword2"]
    tags: ["tag1", "tag2"]
"""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import yaml


class ModelImporter:
    """Import test models from inbox to local catalog."""

    def __init__(self, api_url: str = "http://localhost:8123"):
        self.api_url = api_url.rstrip("/")
        self.inbox_dir = Path(__file__).parent.parent.parent / "assets" / "model_catalog" / "inbox"
        self.validated_dir = Path(__file__).parent.parent.parent / "assets" / "model_catalog" / "validated"
        self.working_dir = Path(__file__).parent.parent.parent / "assets" / "model_catalog" / "working"
        
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.validated_dir.mkdir(parents=True, exist_ok=True)
        self.working_dir.mkdir(parents=True, exist_ok=True)

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _load_metadata(self, model_file: Path) -> dict[str, Any]:
        """
        Load metadata from accompanying YAML file or generate defaults.
        Looks for model_file.yaml or model_file.metadata.yaml.
        """
        yaml_candidates = [
            model_file.with_suffix(model_file.suffix + ".yaml"),  # file.3mf.yaml
            model_file.with_stem(model_file.stem + ".metadata"),  # file.metadata.yaml
            model_file.parent / f"{model_file.stem}.yaml",  # file.yaml
        ]

        for yaml_path in yaml_candidates:
            if yaml_path.exists():
                try:
                    with open(yaml_path, "r") as f:
                        return yaml.safe_load(f) or {}
                except Exception as e:
                    print(f"  ⚠️  Error reading {yaml_path.name}: {e}")
                    pass

        # Generate defaults from filename if no YAML found
        stem = model_file.stem
        # Convert snake_case/kebab-case to Title Case
        model_name = stem.replace("_", " ").replace("-", " ").title()

        return {
            "local_model_id": stem.lower().replace(" ", "-"),
            "model_name": model_name,
            "model_description": f"Test model: {model_name}",
            "creator_name": "Test Import",
            "collection_names": [],
            "keyword_names": [],
            "tags": ["test", "imported"],
        }

    def _create_model(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Create a local model entry via API."""
        payload = {
            "local_model_id": metadata.get("local_model_id"),
            "model_name": metadata.get("model_name"),
            "model_description": metadata.get("model_description"),
            "creator_name": metadata.get("creator_name"),
            "collection_names": metadata.get("collection_names", []),
            "keyword_names": metadata.get("keyword_names", []),
            "tags": metadata.get("tags", []),
        }

        try:
            response = requests.post(
                f"{self.api_url}/api/local/models",
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to create model: {e}")

    def _attach_asset(
        self,
        model_id: int,
        file_path: Path,
        asset_type: str,
        asset_role: str = "primary",
    ) -> dict[str, Any]:
        """Attach a geometry file as an asset."""
        file_size = file_path.stat().st_size
        file_hash = self._compute_file_hash(file_path)

        # For test import, store geometry in a simple location
        storage_path = f"/local/model-catalog/assets/{file_path.name}"

        payload = {
            "asset_id": f"{file_path.stem}_{asset_type}",
            "asset_filename": file_path.name,
            "asset_type": asset_type,
            "asset_role": asset_role,
            "file_size_bytes": file_size,
            "file_hash": file_hash,
            "storage_path": storage_path,
        }

        try:
            response = requests.post(
                f"{self.api_url}/api/local/models/{model_id}/assets",
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to attach asset: {e}")

    def _move_to_validated(self, file_path: Path) -> None:
        """Move processed file to validated directory."""
        dest = self.validated_dir / file_path.name
        shutil.move(str(file_path), str(dest))

    def import_models(self) -> dict[str, Any]:
        """Import all models from inbox directory."""
        results = {
            "imported": [],
            "skipped": [],
            "errors": [],
        }

        if not self.inbox_dir.exists():
            print(f"⚠️  Inbox directory not found: {self.inbox_dir}")
            return results

        model_files = list(self.inbox_dir.glob("*.3mf")) + list(self.inbox_dir.glob("*.stl"))
        
        if not model_files:
            print(f"ℹ️  No model files found in {self.inbox_dir}")
            return results

        print(f"\n📦 Importing {len(model_files)} model(s) from {self.inbox_dir.name}/\n")

        for model_file in sorted(model_files):
            print(f"Processing: {model_file.name}")

            try:
                # Load metadata
                metadata = self._load_metadata(model_file)
                model_id_str = metadata.get("local_model_id", model_file.stem)

                # Create model
                print(f"  → Creating model '{metadata.get('model_name')}'...")
                model = self._create_model(metadata)
                model_id = model.get("id")
                if not model_id:
                    raise RuntimeError(f"Invalid response: {model}")

                print(f"  ✓ Model created (ID: {model_id})")

                # Determine asset type
                asset_type = "3mf" if model_file.suffix.lower() == ".3mf" else "stl"

                # Attach geometry file
                print(f"  → Attaching {asset_type.upper()} geometry...")
                asset = self._attach_asset(model_id, model_file, asset_type, asset_role="primary")
                asset_id = asset.get("id")
                if not asset_id:
                    raise RuntimeError(f"Invalid asset response: {asset}")

                print(f"  ✓ Asset attached (ID: {asset_id})")

                # Move to validated
                self._move_to_validated(model_file)
                print(f"  ✓ Moved to validated/\n")

                results["imported"].append({
                    "filename": model_file.name,
                    "model_id": model_id,
                    "model_name": metadata.get("model_name"),
                    "asset_id": asset_id,
                })

            except Exception as e:
                print(f"  ✗ Error: {e}\n")
                results["errors"].append({
                    "filename": model_file.name,
                    "error": str(e),
                })

        return results

    def print_summary(self, results: dict[str, Any]) -> None:
        """Print import summary."""
        print("\n" + "=" * 60)
        print("IMPORT SUMMARY")
        print("=" * 60)
        print(f"✓ Imported:  {len(results['imported'])}")
        print(f"⚠ Errors:    {len(results['errors'])}")
        print(f"⊘ Skipped:   {len(results['skipped'])}")

        if results["imported"]:
            print("\n✓ Successfully imported:")
            for item in results["imported"]:
                print(f"  - {item['model_name']} ({item['filename']})")
                print(f"    Model ID: {item['model_id']}, Asset ID: {item['asset_id']}")

        if results["errors"]:
            print("\n✗ Errors:")
            for item in results["errors"]:
                print(f"  - {item['filename']}: {item['error']}")

        print("\n" + "=" * 60)
        print(f"📍 Validated models: {self.validated_dir}")
        print(f"🔗 API: {self.api_url}")
        print("=" * 60 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Import test models from inbox to local catalog",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8123",
        help="Home Assistant API base URL (default: http://localhost:8123)",
    )

    args = parser.parse_args()

    importer = ModelImporter(api_url=args.api_url)
    results = importer.import_models()
    importer.print_summary(results)

    # Exit with error if any failures
    if results["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
