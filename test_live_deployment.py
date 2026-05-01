#!/usr/bin/env python3
import requests
import json

base_url = 'http://model-catalog.socko.us/api'

test_cases = [
    ('GET', '/working-files', None, 'List working files'),
    ('POST', '/working-groups', {'title': 'Test Group'}, 'Create group'),
    ('GET', '/working-groups', None, 'List groups'),
    ('POST', '/projects', {'title': 'Test Project'}, 'Create project'),
    ('GET', '/projects', None, 'List projects'),
]

print('Live Deployment Validation - #1194 Working Endpoints')
print('=' * 70)

passed = 0
failed = 0

for method, path, payload, label in test_cases:
    try:
        if method == 'GET':
            resp = requests.get(f'{base_url}{path}', timeout=10)
        else:
            resp = requests.post(f'{base_url}{path}', json=payload, timeout=10)
        
        if resp.status_code in (200, 201):
            print(f'✓ PASS [{resp.status_code}] {method:4} {path:25} - {label}')
            passed += 1
        else:
            print(f'✗ FAIL [{resp.status_code}] {method:4} {path:25} - {label}')
            failed += 1
    except Exception as e:
        print(f'✗ ERROR {method:4} {path:25} - {label} :: {str(e)[:50]}')
        failed += 1

print('=' * 70)
print(f'Results: {passed} passed, {failed} failed')
if passed == 5:
    print('✓ All endpoints working!')
