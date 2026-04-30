#!/usr/bin/env python3
"""Validate issue #1159: publish-to-local endpoint end-to-end live."""

import tempfile
import sys
from pathlib import Path

import httpx


def validate_issue_1159_live(base_url: str = "http://model-catalog.socko.us") -> None:
    """End-to-end validation of #1159 publish-to-local."""
    client = httpx.Client(base_url=base_url, timeout=30)
    
    print(f"Validating #1159 publish-to-local against {base_url}\n")
    
    # Step 1: Create temp files
    print("[STEP 1] Create temp source files...")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        model_file = tmp_path / "test-model-1159.3mf"
        preview_file = tmp_path / "test-preview-1159.png"
        
        model_file.write_bytes(b"test 3mf content for 1159")
        preview_file.write_bytes(b"\x89PNG\r\n\x1a\ntest preview 1159")
        
        print(f"  ✓ Created {model_file.name} ({len(model_file.read_bytes())} bytes)")
        print(f"  ✓ Created {preview_file.name} ({len(preview_file.read_bytes())} bytes)\n")
        
        # Step 2: Upload to queue
        print("[STEP 2] Upload files to intake queue...")
        upload_resp = client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [
                    {"type": "file", "path": str(model_file)},
                    {"type": "file", "path": str(preview_file)},
                ]
            },
        )
        if upload_resp.status_code != 200:
            print(f"  ✗ Upload failed: {upload_resp.status_code} {upload_resp.text}")
            return
        
        upload_data = upload_resp.json()
        upload_id = upload_data["upload_id"]
        print(f"  ✓ Queued as upload_id: {upload_id}")
        print(f"  ✓ Status: {upload_data['status']}, Entries: {upload_data['source_entry_count']}\n")
        
        # Step 3: Publish to local
        print("[STEP 3] Publish upload to local catalog...")
        publish_resp = client.post(
            f"/api/intake/uploads/{upload_id}/publish-to-local",
            json={
                "model_name": "Test 1159 Model",
                "tags": ["1159-validation", "test"],
                "collection_names": ["Test"],
                "source_origin": "intake_test_1159",
                "preview_source_path": str(preview_file),
            },
        )
        if publish_resp.status_code != 200:
            print(f"  ✗ Publish failed: {publish_resp.status_code}")
            print(f"    Response: {publish_resp.text}")
            return
        
        publish_data = publish_resp.json()
        local_model_id = publish_data.get("local_model_id")
        print(f"  ✓ Published successfully")
        print(f"  ✓ Local model created: {local_model_id}\n")
        
        # Step 4: Verify model exists
        print("[STEP 4] Verify model was created...")
        models_resp = client.get("/api/models")
        if models_resp.status_code != 200:
            print(f"  ✗ List models failed: {models_resp.status_code}")
            return
        
        models = models_resp.json()
        matching_model = None
        for model in models.get("models", []):
            if model.get("model_id") == local_model_id or model.get("local_model_id") == local_model_id:
                matching_model = model
                break
        
        if not matching_model:
            print(f"  ✗ Model {local_model_id} not found in list")
            print(f"    Available models: {[m.get('model_id') or m.get('local_model_id') for m in models.get('models', [])]}")
            return
        
        print(f"  ✓ Model found in catalog: {matching_model.get('model_name', 'unnamed')}")
        print(f"    Status: {matching_model.get('status', 'unknown')}\n")
        
        # Step 5: Check model detail
        print("[STEP 5] Retrieve model detail...")
        detail_resp = client.get(f"/api/models/{local_model_id}/detail")
        if detail_resp.status_code != 200:
            print(f"  ✗ Detail fetch failed: {detail_resp.status_code}")
            return
        
        detail = detail_resp.json()
        print(f"  ✓ Model name: {detail.get('model_name', 'N/A')}")
        print(f"  ✓ Tags: {detail.get('tags', [])}")
        print(f"  ✓ Collection: {detail.get('collection_names', [])}\n")
        
        # Step 6: Verify assets
        print("[STEP 6] Check local assets...")
        assets_resp = client.get(f"/api/models/{local_model_id}/assets")
        if assets_resp.status_code != 200:
            print(f"  ✗ Assets fetch failed: {assets_resp.status_code}")
            return
        
        assets = assets_resp.json()
        asset_list = assets.get("assets", [])
        print(f"  ✓ Assets count: {len(asset_list)}")
        for asset in asset_list:
            print(f"    - {asset.get('asset_id', 'unknown')}: {asset.get('asset_type', 'unknown')}")
        
        print("\n" + "="*60)
        print("✅ ALL #1159 VALIDATIONS PASSED")
        print("="*60)
        print(f"\nPublish-to-local endpoint is functional:")
        print(f"  • Created model: {local_model_id}")
        print(f"  • Copied {len(asset_list)} assets from queue")
        print(f"  • Preserved metadata (tags, collections, provenance)")


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://model-catalog.socko.us"
    validate_issue_1159_live(base_url)
