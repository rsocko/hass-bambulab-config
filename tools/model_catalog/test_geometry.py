#!/usr/bin/env python3
import requests
import json

# Get a model's assets first
resp = requests.get('http://model-catalog.socko.us/api/local/models/football-holder')
data = resp.json()
assets = data.get('assets', [])

if not assets:
    print('No assets found')
else:
    asset = assets[0]
    asset_id = asset.get('id')
    # Try different model reference formats
    model_refs = [
        'local://football-holder',
        'football-holder',
        'local-football-holder',
    ]
    
    print(f'Testing geometry endpoint...')
    print(f'  Asset ID: {asset_id}')
    print(f'  Storage: {asset.get("storage_path")}')
    print()
    
    for model_ref in model_refs:
        url = f'http://model-catalog.socko.us/api/models/{model_ref}/geometry/{asset_id}?include_debug=true'
        resp = requests.get(url)
        
        print(f'Model ref: {model_ref}')
        print(f'  Status: {resp.status_code}')
        result = resp.json()
        if 'error' in result:
            print(f'  Error: {result.get("error")}')
        elif 'geometry' in result:
            geo = result.get('geometry', {})
            geometries = geo.get('geometries', [])
            materials = geo.get('materials', {})
            
            print(f'  ✓ Geometry loaded')
            print(f'    Geometries count: {len(geometries)}')
            print(f'    Materials: {len(materials)}')
            
            if geometries:
                g = geometries[0]
                print(f'    First geometry:')
                print(f'      - Vertices: {len(g.get("vertices", [])) // 3} points')
                print(f'      - Faces: {len(g.get("faces", [])) // 3} triangles')
                print(f'      - Edges: {len(g.get("edges", [])) // 2}')
            if materials:
                print(f'    Materials: {list(materials.keys())}')
        else:
            print(f'    Response keys: {list(result.keys())}')
        print()
