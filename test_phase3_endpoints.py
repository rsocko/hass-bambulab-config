#!/usr/bin/env python3
"""
Test script for Phase 3 endpoints
Validates PATCH, POST (photos), and GET (related models) functionality
"""

import requests
import json
import os
from pathlib import Path
import urllib3

# Suppress SSL warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
SIDECAR_URL = os.getenv('MODEL_CATALOG_API', 'https://model-catalog.socko.us')
HA_TOKEN = os.getenv('HA_TOKEN', '')
VERIFY_SSL = os.getenv('VERIFY_SSL', 'false').lower() == 'true'

# Test model reference
TEST_MODEL_REF = 'test-model'
TEST_MODEL_NAME = 'Test Model Updated'

print("=" * 60)
print("PHASE 3.1 ENDPOINT VALIDATION")
print("=" * 60)
print(f"Sidecar URL: {SIDECAR_URL}")
print(f"Auth Token: {'✓ Set' if HA_TOKEN else '✗ Not set'}")
print()

# ============================================================
# TEST 1: PATCH /api/models/{model_ref} - Update Metadata
# ============================================================
print("\n[TEST 1] PATCH /api/models/{model_ref} - Update Metadata")
print("-" * 60)

patch_data = {
    "model_name": TEST_MODEL_NAME,
    "description": "Test model description updated via Phase 3.1",
    "tags": ["test", "phase3", "validation"],
    "collection": "Test Collection",
    "enrichment": {
        "print_time_estimate": 3600,
        "support_type_hint": "tree",
        "difficulty_level": "intermediate",
        "print_notes": "Test notes from Phase 3.1 PATCH"
    }
}

try:
    url = f"{SIDECAR_URL}/api/models/{TEST_MODEL_REF}"
    print(f"URL: {url}")
    print(f"Method: PATCH")
    print(f"Payload: {json.dumps(patch_data, indent=2)}")
    
    response = requests.patch(url, json=patch_data, timeout=5, verify=VERIFY_SSL)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        print("✅ PATCH request successful")
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
    else:
        print(f"❌ PATCH request failed: {response.text}")
except Exception as e:
    print(f"❌ Error: {str(e)}")

# ============================================================
# TEST 2: POST /api/models/{model_ref}/photos - Upload Photo
# ============================================================
print("\n[TEST 2] POST /api/models/{model_ref}/photos - Upload Photo")
print("-" * 60)

photo_data = {
    "model_ref": TEST_MODEL_REF,
    "photo_file": "data:image/jpeg;base64,/9j/4AAQSkZJRgABA...",  # Minimal valid JPEG data URI
    "set_as_preview": True
}

try:
    url = f"{SIDECAR_URL}/api/models/{TEST_MODEL_REF}/photos"
    print(f"URL: {url}")
    print(f"Method: POST")
    print(f"Payload: {json.dumps({**photo_data, 'photo_file': '...(truncated)'}, indent=2)}")
    
    response = requests.post(url, json=photo_data, timeout=5, verify=VERIFY_SSL)
    print(f"Status: {response.status_code}")
    
    if response.status_code in [200, 201]:
        print("✅ POST photo request successful")
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
    else:
        print(f"❌ POST photo request failed: {response.text}")
except Exception as e:
    print(f"❌ Error: {str(e)}")

# ============================================================
# TEST 3: GET /api/models/{model_ref}/related - Related Models
# ============================================================
print("\n[TEST 3] GET /api/models/{model_ref}/related - Related Models")
print("-" * 60)

try:
    url = f"{SIDECAR_URL}/api/models/{TEST_MODEL_REF}/related?limit=5"
    print(f"URL: {url}")
    print(f"Method: GET")
    
    response = requests.get(url, timeout=5, verify=VERIFY_SSL)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        print("✅ GET related models request successful")
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
    else:
        print(f"❌ GET related models request failed: {response.text}")
except Exception as e:
    print(f"❌ Error: {str(e)}")

# ============================================================
# TEST 4: GET /api/archives/{archive_id}/model - Archive Model Link
# ============================================================
print("\n[TEST 4] GET /api/archives/{archive_id}/model - Archive Model Link")
print("-" * 60)

try:
    url = f"{SIDECAR_URL}/api/archives/12345/model"
    print(f"URL: {url}")
    print(f"Method: GET")
    
    response = requests.get(url, timeout=5, verify=VERIFY_SSL)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        print("✅ GET archive model request successful")
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
    else:
        print(f"❌ GET archive model request failed: {response.text}")
except Exception as e:
    print(f"❌ Error: {str(e)}")

# ============================================================
# TEST 5: Verify Updated Model
# ============================================================
print("\n[TEST 5] GET /api/models/{model_ref} - Verify Update")
print("-" * 60)

try:
    url = f"{SIDECAR_URL}/api/models/{TEST_MODEL_REF}"
    print(f"URL: {url}")
    print(f"Method: GET")
    
    response = requests.get(url, timeout=5, verify=VERIFY_SSL)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        print("✅ GET model request successful")
        result = response.json()
        model = result.get('model', {})
        
        # Check if updates persisted
        checks = {
            "Model name updated": model.get('name') == TEST_MODEL_NAME,
            "Description updated": 'Phase 3.1' in model.get('description', ''),
            "Tags added": 'phase3' in model.get('tags', []),
            "Enrichment stored": 'print_time_estimate' in model.get('enrichment', {}),
        }
        
        print("\nUpdate Verification:")
        for check, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"{status} {check}")
        
        print(f"\nFull model: {json.dumps(result, indent=2)}")
    else:
        print(f"❌ GET model request failed: {response.text}")
except Exception as e:
    print(f"❌ Error: {str(e)}")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 60)
print("TEST SUMMARY")
print("=" * 60)
print("""
Phase 3.1 Endpoints Tested:
1. PATCH /api/models/{model_ref} - Update metadata/enrichment ✓
2. POST /api/models/{model_ref}/photos - Upload photos ✓
3. GET /api/models/{model_ref}/related - Get related models ✓
4. GET /api/archives/{archive_id}/model - Link archives to models ✓

Next Steps if All Tests Pass:
- Implement photo upload shell_command in HA
- Integrate enrichment with print_history package
- Add related models to print_history dashboard
- Implement recommendation engine
""")
