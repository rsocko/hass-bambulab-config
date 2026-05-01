#!/usr/bin/env python3
"""Validate #1193 archive-link endpoints on deployed host."""

import requests
import json

base_url = 'http://model-catalog.socko.us/api'

# Test endpoints with proper payloads
test_cases = [
    ('GET', '/archive-links/1', None, '1. GET archive links'),
    ('POST', '/archive-links/1', {'manyfold_model_url': 'http://manyfold.local/models/test1'}, '2. POST create link'),
    ('PATCH', '/archive-links/1/1', {'is_active': False}, '3. PATCH update link'),
    ('GET', '/archive-links/1', None, '4. GET after update'),
    ('POST', '/archive-links/1/candidates/refresh', {'archive_name': 'Test Print'}, '5. POST refresh candidates'),
    ('POST', '/archive-links/1/1/deactivate', {}, '6. POST deactivate link'),
    ('POST', '/archive-links/1/cleanup-duplicates', {}, '7. POST cleanup duplicates'),
    ('POST', '/archive-links/1', {'manyfold_model_url': 'http://manyfold.local/models/test2', 'match_method': 'auto', 'review_state': 'new'}, '8. POST create candidate'),
]

print('Archive-Link Endpoint Validation')
print('=' * 70)

passed = 0
failed = 0

for method, path, payload, desc in test_cases:
    try:
        url = f'{base_url}{path}'
        if method == 'GET':
            resp = requests.get(url, timeout=5)
        elif method == 'POST':
            resp = requests.post(url, json=payload or {}, timeout=5)
        elif method == 'PATCH':
            resp = requests.patch(url, json=payload or {}, timeout=5)
        else:
            continue
        
        status = resp.status_code
        if status < 400:
            status_text = '✓ PASS'
            passed += 1
        else:
            status_text = '✗ FAIL'
            failed += 1
        
        print(f'{status_text:8} [{status:3}] {method:6} {path:45} - {desc}')
        
        if status >= 400:
            try:
                error = resp.json()
                detail = error.get('detail', str(error))
                print(f'         Error: {str(detail)[:70]}')
            except:
                print(f'         Response: {resp.text[:70]}')
    except Exception as e:
        print(f'✗ ERROR  [{type(e).__name__}] {method:6} {path:45}')
        print(f'         {str(e)[:70]}')
        failed += 1

print()
print(f'Results: {passed} passed, {failed} failed')
print('Deployment validation complete.')
