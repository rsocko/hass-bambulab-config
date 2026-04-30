#!/usr/bin/env python3
"""
Attach geometry assets to existing local models.
"""

import requests
import json

# Models to attach with their server-side file info
models_to_attach = [
    {
        "local_model_id": "football-holder",
        "filename": "football holder.3mf",
        "file_path": "/assets/model inbox/football holder.3mf",
        "file_type": "3mf",
        "file_hash": "f7ac20809ef702c62547e35b3ddaedcb6f375797961aac37c32994c7b116a7ad",
        "file_size": 2527317,
    },
    {
        "local_model_id": "gridfinity-clipbasespacers-1x3-11mm",
        "filename": "Gridfinity_ClipBaseSpacers_1x3_11mm.stl",
        "file_path": "/assets/model inbox/Gridfinity_ClipBaseSpacers_1x3_11mm.stl",
        "file_type": "stl",
        "file_hash": "4cc6ddee7d4f60ac06f57516676583addb60adcea0a00593b58685b0825ec256",
        "file_size": 110284,
    },
    {
        "local_model_id": "il-ghoul-basic-",
        "filename": "IL_GHOUL_basic_.3mf",
        "file_path": "/assets/model inbox/IL_GHOUL_basic_.3mf",
        "file_type": "3mf",
        "file_hash": "3a35980ba13ff493849f50f903924ca32d7938f1313a5482c69600039d0e6cd5",
        "file_size": 13087901,
    },
    {
        "local_model_id": "p1s-xtouch-cable-pass",
        "filename": "p1s xtouch cable pass.3mf",
        "file_path": "/assets/model inbox/p1s xtouch cable pass.3mf",
        "file_type": "3mf",
        "file_hash": "625567aa668d913c802a609e9ef08a1ab501feab0541bdcb1081fd5f6320f7c8",
        "file_size": 2428080,
    },
]

sidecar_url = "http://model-catalog.socko.us"

print("Attaching geometry assets...\n")

for model_info in models_to_attach:
    asset_id = f"{model_info['filename'].rsplit('.', 1)[0]}-{model_info['file_type']}"
    
    payload = {
        "asset_id": asset_id,
        "asset_filename": model_info['filename'],
        "asset_type": model_info['file_type'],
        "asset_role": "primary",
        "file_size_bytes": model_info['file_size'],
        "file_hash": model_info['file_hash'],
        "storage_path": model_info['file_path'],
    }
    
    url = f"{sidecar_url}/api/local/models/{model_info['local_model_id']}/assets"
    
    print(f"Attaching {model_info['filename']} to {model_info['local_model_id']}...")
    print(f"  URL: {url}")
    print(f"  Payload: {json.dumps(payload, indent=4)}")
    
    try:
        resp = requests.post(url, json=payload, timeout=10)
        print(f"  Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"  Error: {resp.text}")
        else:
            print(f"  ✓ Success")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    print()
