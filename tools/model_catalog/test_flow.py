#!/usr/bin/env python3
import requests
import json
import time

# Step 1: Create a model
print("Step 1: Creating test model...")
model_id_suffix = str(int(time.time()) % 10000)
create_resp = requests.post(
    'http://model-catalog.socko.us/api/local/models',
    json={
        'local_model_id': f'test-benchy-{model_id_suffix}',
        'model_name': 'Test Benchy',
        'model_description': 'Test',
        'creator_name': 'Test',
        'collection_names': [],
        'keyword_names': [],
        'tags': ['test'],
    }
)
print(f"  Status: {create_resp.status_code}")
create_data = create_resp.json()
print(f"  Response keys: {create_data.keys()}")

model_id = create_data.get('summary', {}).get('model_id')
print(f"  Model ID: {model_id}")

if not model_id:
    print("  ERROR: No model ID returned!")
    print(f"  Full response: {json.dumps(create_data, indent=2)}")
else:
    # Step 2: List models
    print("\nStep 2: Listing models...")
    list_resp = requests.get('http://model-catalog.socko.us/api/local/models?limit=10')
    list_data = list_resp.json()
    # The response has "models" key, not "items"
    models = list_data.get('models', [])
    print(f"  Count: {len(models)}")
    if models:
        for item in models[-3:]:
            print(f"    - {item.get('name')} (ID: {item.get('model_id')})")
    else:
        print(f"  Full response: {json.dumps(list_data, indent=2)}")
