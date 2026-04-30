#!/usr/bin/env python3
import requests

resp = requests.get('http://model-catalog.socko.us/api/local/models/football-holder')
data = resp.json()
print('Model:', data.get('model', {}).get('name'))
print('Assets:', len(data.get('assets', [])))
for asset in data.get('assets', []):
    print(f'  - {asset.get("filename")} ({asset.get("asset_type")})')
    print(f'    Storage: {asset.get("storage_path")}')
