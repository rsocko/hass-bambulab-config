#!/usr/bin/env python3
"""
Discover and import models from server-side inbox directory using the sidecar bulk endpoints.

Usage:
    python import_server_models.py --sidecar-url http://model-catalog.socko.us [--inbox-folder /path/to/inbox]

This script:
1. Calls /api/working-groups/bulk-discover to scan the inbox folder
2. Calls /api/working-groups/bulk-import to import discovered models
"""

import argparse
import sys
from typing import Any

import requests


class ServerModelImporter:
    """Import models from server-side inbox using sidecar bulk endpoints."""

    def __init__(self, sidecar_url: str, inbox_folder: str = "/inbox"):
        self.sidecar_url = sidecar_url.rstrip("/")
        self.inbox_folder = inbox_folder

    def discover(self) -> dict[str, Any]:
        """Discover models in the inbox folder."""
        payload = {
            "folder_path": self.inbox_folder,
            "grouping_strategy": "by-directory",
        }

        print(f"🔍 Discovering models in {self.inbox_folder}...")
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

    def import_proposals(self, discovery_result: dict[str, Any]) -> dict[str, Any]:
        """Import the discovered proposals."""
        proposals = discovery_result.get("proposals", [])
        
        if not proposals:
            print("ℹ️  No models found to import.")
            return {"success": True, "imported": []}

        print(f"\n📦 Importing {len(proposals)} model(s)...")
        
        payload = {
            "proposals": proposals,
            "source_folder": discovery_result.get("source_folder"),
            "grouping_strategy": discovery_result.get("grouping_strategy"),
            "discovered_at": discovery_result.get("discovered_at"),
        }

        try:
            response = requests.post(
                f"{self.sidecar_url}/api/working-groups/bulk-import",
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Import failed: {e}")

    def print_discovery_summary(self, result: dict[str, Any]) -> None:
        """Print discovery summary."""
        summary = result.get("summary", {})
        print("\n" + "=" * 60)
        print("DISCOVERY SUMMARY")
        print("=" * 60)
        print(f"📁 Folder: {result.get('source_folder')}")
        print(f"📊 Scanned files: {summary.get('scanned_file_count', 0)}")
        print(f"✓ Supported: {summary.get('supported_file_count', 0)}")
        print(f"📦 Proposals: {summary.get('proposal_count', 0)}")
        print(f"⚠️  Duplicates: {summary.get('duplicate_warning_count', 0)}")
        print(f"⚠️  Warnings: {summary.get('warning_count', 0)}")
        
        proposals = result.get("proposals", [])
        if proposals:
            print("\nProposals:")
            for proposal in proposals:
                print(f"  - {proposal.get('title')} ({proposal.get('file_count')} files)")

        if result.get("warnings"):
            print("\nWarnings:")
            for warning in result["warnings"]:
                print(f"  - {warning.get('type')}: {warning.get('message')}")

    def print_import_summary(self, result: dict[str, Any]) -> None:
        """Print import summary."""
        print("\n" + "=" * 60)
        print("IMPORT SUMMARY")
        print("=" * 60)
        print(f"✓ Created groups: {result.get('created_group_count', 0)}")
        print(f"✓ Created items: {result.get('created_item_count', 0)}")
        print(f"⊘ Skipped duplicates: {result.get('duplicate_skipped_count', 0)}")
        
        if result.get("created_groups"):
            print("\nCreated Groups:")
            for group in result["created_groups"]:
                print(f"  - {group.get('title')} (ID: {group.get('id')})")

        if result.get("skipped_groups"):
            print("\nSkipped Groups:")
            for group in result["skipped_groups"]:
                print(f"  - {group.get('title')}: {group.get('reason')}")

        print("=" * 60 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Discover and import models from server inbox",
    )
    parser.add_argument(
        "--sidecar-url",
        required=True,
        help="Sidecar API URL (e.g., http://model-catalog.socko.us)",
    )
    parser.add_argument(
        "--inbox-folder",
        default="/inbox",
        help="Path to inbox folder on server (default: /inbox)",
    )

    args = parser.parse_args()

    importer = ServerModelImporter(
        sidecar_url=args.sidecar_url,
        inbox_folder=args.inbox_folder,
    )

    try:
        # Discover models
        discovery = importer.discover()
        if not discovery.get("success"):
            print(f"❌ Discovery failed: {discovery.get('error')}")
            sys.exit(1)

        importer.print_discovery_summary(discovery)

        # Import discovered proposals
        import_result = importer.import_proposals(discovery)
        if not import_result.get("success"):
            print(f"❌ Import failed: {import_result.get('error')}")
            sys.exit(1)

        importer.print_import_summary(import_result)

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
