#!/usr/bin/env python3
"""
Import models directly into local catalog from discovered files.

This creates local models using /api/local/models POST endpoint
and attaches geometry files as assets.
"""

import argparse
import sys
from typing import Any

import requests


class DirectModelImporter:
    """Create local models directly from discovered files."""

    def __init__(self, sidecar_url: str):
        self.sidecar_url = sidecar_url.rstrip("/")

    def discover(self, folder: str) -> dict[str, Any]:
        """Discover models in folder."""
        payload = {
            "folder_path": folder,
            "grouping_strategy": "flat",
        }

        try:
            response = requests.post(
                f"{self.sidecar_url}/api/working-groups/bulk-discover",
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Discovery failed: {e}")

    def create_model_from_file(self, file_info: dict[str, Any]) -> dict[str, Any]:
        """Create a local model from a discovered file."""
        filename = file_info.get("filename", "").strip()
        file_path = file_info.get("path", "").strip()
        
        if not filename:
            raise ValueError("Missing filename")

        # Generate model ID from filename (remove extension, slugify)
        model_id = filename.rsplit(".", 1)[0].lower().replace(" ", "-").replace("_", "-")
        
        # Clean up model name (remove extension, title case)
        model_name = filename.rsplit(".", 1)[0]

        payload = {
            "local_model_id": model_id,
            "model_name": model_name,
            "model_description": f"Imported from {filename}",
            "creator_name": "Server Import",
            "collection_names": ["Imported Models"],
            "keyword_names": [],
            "tags": ["imported", "test"],
        }

        print(f"  Creating model: {model_name} ({model_id})...")
        try:
            response = requests.post(
                f"{self.sidecar_url}/api/local/models",
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            result = response.json()
            model_id = result.get("summary", {}).get("model_id")
            print(f"    ✓ Created (ID: {model_id})")
            return {"id": model_id, **result}
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to create model: {e}")

    def attach_geometry(self, model_id: int, file_info: dict[str, Any], file_type: str) -> dict[str, Any]:
        """Attach geometry file as asset."""
        filename = file_info.get("filename", "").strip()
        file_path = file_info.get("path", "").strip()
        file_hash = file_info.get("sha256", "").strip()

        if not filename:
            raise ValueError("Missing filename")

        asset_id = f"{filename.rsplit('.', 1)[0]}-{file_type}"

        payload = {
            "asset_id": asset_id,
            "asset_filename": filename,
            "asset_type": file_type,
            "asset_role": "primary",
            "file_size_bytes": file_info.get("size_bytes"),
            "file_hash": file_hash,
            "storage_path": file_path,  # Use the full server path
        }

        print(f"  Attaching {file_type.upper()} geometry: {filename}...")
        try:
            response = requests.post(
                f"{self.sidecar_url}/api/local/models/{model_id}/assets",
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            asset = response.json()
            print(f"    ✓ Attached (Asset ID: {asset.get('id')})")
            return asset
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to attach asset: {e}")

    def import_discovered(self, discovery: dict[str, Any]) -> list[dict[str, Any]]:
        """Import all discovered models."""
        results = []
        
        for proposal in discovery.get("proposals", []):
            for file_info in proposal.get("files", []):
                filename = file_info.get("filename", "").lower()
                
                # Determine file type
                if filename.endswith(".3mf"):
                    file_type = "3mf"
                elif filename.endswith(".stl"):
                    file_type = "stl"
                else:
                    print(f"  ⊘ Skipping unsupported file: {filename}")
                    continue

                print(f"\n📦 {filename}")
                try:
                    # Create model
                    model = self.create_model_from_file(file_info)
                    model_id = model.get("id")

                    # Attach geometry
                    asset = self.attach_geometry(model_id, file_info, file_type)

                    results.append({
                        "filename": filename,
                        "model_id": model_id,
                        "model_name": model.get("model_name"),
                        "asset_id": asset.get("id"),
                        "success": True,
                    })

                except Exception as e:
                    print(f"    ✗ Error: {e}")
                    results.append({
                        "filename": filename,
                        "success": False,
                        "error": str(e),
                    })

        return results

    def print_summary(self, results: list[dict[str, Any]]) -> None:
        """Print import summary."""
        success = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        print("\n" + "=" * 60)
        print("IMPORT SUMMARY")
        print("=" * 60)
        print(f"✓ Imported:  {len(success)}")
        print(f"✗ Failed:    {len(failed)}")

        if success:
            print("\n✓ Successfully imported:")
            for r in success:
                print(f"  - {r.get('model_name')} ({r.get('filename')})")
                print(f"    Model ID: {r.get('model_id')}")

        if failed:
            print("\n✗ Failed:")
            for r in failed:
                print(f"  - {r.get('filename')}: {r.get('error')}")

        print("=" * 60 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Import discovered models as local catalog entries",
    )
    parser.add_argument(
        "--sidecar-url",
        required=True,
        help="Sidecar API URL",
    )
    parser.add_argument(
        "--inbox-folder",
        default="/assets/model inbox",
        help="Inbox folder path",
    )

    args = parser.parse_args()

    importer = DirectModelImporter(sidecar_url=args.sidecar_url)

    try:
        print(f"🔍 Discovering models in {args.inbox_folder}...\n")
        discovery = importer.discover(args.inbox_folder)

        if not discovery.get("success"):
            print(f"❌ Discovery failed: {discovery.get('error')}")
            sys.exit(1)

        summary = discovery.get("summary", {})
        print(f"📊 Found: {summary.get('supported_file_count')} model(s)\n")

        # Import discovered models
        print(f"📦 Importing models...\n")
        results = importer.import_discovered(discovery)
        importer.print_summary(results)

        if any(not r.get("success") for r in results):
            sys.exit(1)

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
