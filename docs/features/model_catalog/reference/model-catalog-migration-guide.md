# Model Catalog Migration Guide

**Version**: 1.0 (Phase 2 Refactoring)  
**Effective Date**: 2026-05-02  
**Related Issues**: #1207 (Documentation)

---

## Table of Contents

1. [Overview](#overview)
2. [For External API Clients](#for-external-api-clients)
3. [For Home Assistant Integrations](#for-home-assistant-integrations)
4. [For Internal Developers](#for-internal-developers)
5. [Deprecation Schedule](#deprecation-schedule)
6. [Breaking Changes](#breaking-changes)

---

## Overview

Phase 2 refactoring restructures the Model Catalog Sidecar for improved maintainability and testability. **All changes are internal**—endpoint contracts remain unchanged.

### What Changed

- **Router Organization**: Large routers split into focused domains
- **Database Layer**: Reorganized by bounded context
- **Service Layer**: New services layer for business logic
- **Imports**: Some internal module paths changed

### What Didn't Change

- ✅ All HTTP endpoint URLs are identical
- ✅ All request/response schemas are unchanged
- ✅ All authentication mechanisms are unchanged
- ✅ All error handling is unchanged
- ✅ All configuration options are unchanged

---

## For External API Clients

### No Migration Required

If you're calling the Model Catalog API from Home Assistant, a UI client, or external service, **no changes are needed**. All endpoints work exactly as before.

### Endpoint Stability Guarantees

The following are guaranteed stable for at least 1 year:

```
GET /api/models
GET /api/models/search
GET /api/models/{model_ref}/detail
GET /api/models/{model_ref}/related
POST /api/models/{model_ref}/photos
DELETE /api/models/{model_ref}/photos/{photo_id}

GET /api/local/models
POST /api/local/models
PUT /api/local/models/{local_model_id}
DELETE /api/local/models/{local_model_id}

POST /api/intake/browser
POST /api/intake/uploads/{upload_id}/status
POST /api/intake/submit
POST /api/intake/uploads/{upload_id}/publish-to-local

GET /api/working/groups
POST /api/working/groups
GET /api/working/groups/{group_id}
POST /api/working/groups/{group_id}/items

GET /healthz
GET /api/config
```

### API Response Format Changes

**None**. Response schemas for all documented endpoints remain unchanged.

**Note**: If you're relying on undocumented fields in response bodies, those may change. Use only fields documented in the OpenAPI schema (`GET /openapi.json`).

---

## For Home Assistant Integrations

### Archive Enrichment Webhook

**Status**: Unchanged  
**Contract**: Stable  
**Action**: No migration needed

Home Assistant's Bambu Lab integration sends archive completion webhooks. The Model Catalog expects:

```json
{
  "event": "print_completed",
  "archive_id": "abc123",
  "printer_id": "X1-0001",
  "model": {
    "name": "gridfinity-bin.3mf",
    "size": 2048576
  }
}
```

**No changes to this contract.**

### Custom Entity Enrichment

If you've configured custom fields on models (e.g., via `PUT /api/models/{model_ref}/fields/{key}`), these continue to work exactly as before.

**Example**: Setting filament UUID for Spoolman enrichment

```bash
curl -X PUT http://localhost:8314/api/models/gridfinity-bin--a1b2c3d4/fields/filament_uuid \
  -H "Content-Type: application/json" \
  -d '{"value": "uuid-1234-5678"}'
```

This works exactly as in Phase 1. No changes needed.

---

## For Internal Developers

### Import Path Changes

**Phase 1 (Old)**:
```python
from app.db import create_model, get_model_detail, list_models
from app.intake_service import check_duplicate
```

**Phase 2 (New)**:
```python
from app.db_models import create_model_entry, get_model_entry
from app.db_intake import create_upload_session
from app.services.intake_service import check_duplicate
from app.services.model_detail_service import get_enriched_detail
```

### Shared Helpers Migration

**Phase 1 (Old)**:
```python
from app._helpers import slugify_title, sha256_file
```

**Phase 2 (New)**:
```python
from app.services.shared_helpers import slugify_title, sha256_file
from app._helpers import resolve_asset_path  # Still in _helpers.py
```

### Database Module Splits

**Phase 1 (Old)**:
```python
from app.db import (
    create_model, update_model, delete_model,
    create_upload, get_upload, update_upload_status,
    create_working_group, add_working_item
)
```

**Phase 2 (New)**:
```python
# By context:
from app.db_models import create_model, update_model, delete_model
from app.db_intake import create_upload, get_upload, update_upload_status
from app.db_working import create_working_group, add_working_item

# Still available in db.py for backward compatibility (Phase 2.3 shim):
from app.db import create_model  # Calls db_models.create_model internally
```

**Migration Path**: 
1. Phase 2.3 provides a compatibility shim in `db.py`
2. Update imports to context-specific modules
3. Phase 2.4 removes compatibility shim (1-2 months after Phase 2.3)

### Service Layer Usage

**Phase 1 (Old)**: Routers implemented logic directly

**Phase 2 (New)**: Routers delegate to services

**Example**:
```python
# Old (Phase 1):
@router.get("/detail/{model_id}")
async def get_detail(model_id: str, request: Request):
    entry = db.get_model_entry(model_id)
    assets = db.list_assets(model_id)
    fields = db.get_custom_fields(model_id)
    enrichment = get_spoolman_enrichment(entry)
    # ... manual assembly ...
    return {...}

# New (Phase 2):
@router.get("/detail/{model_id}")
async def get_detail(model_id: str, request: Request):
    service = ModelDetailService(db_models)
    return await service.get_enriched_detail(model_id)
```

**Benefits**: Easier to test, reuse, and maintain logic.

---

## Deprecation Schedule

### Phase 2.3: Database Compatibility Shim (Current)

The old `db.py` imports still work via a shim that forwards to context-specific modules.

```python
# Both work identically:
from app.db import create_model
from app.db_models import create_model_entry as create_model
```

**Deprecation Window**: 2 months

### Phase 2.5: Remove Compatibility Shim

All imports via `app.db` will be removed. Update to context-specific imports:

```python
from app.db_models import create_model_entry
from app.db_intake import create_upload_session
from app.db_working import create_working_group
```

---

## Breaking Changes

### None for API Clients

All HTTP endpoints and response schemas are unchanged.

### For Internal Code

#### 1. db.py Function Naming

Some functions were renamed for clarity in Phase 2.3:

| Old Name (Phase 1) | New Name (Phase 2) | Context | Status |
|----|----|----|----|
| `create_model` | `create_model_entry` | db_models | Compat shim until 2.5 |
| `get_model` | `get_model_entry` | db_models | Compat shim until 2.5 |
| `list_models` | `list_model_entries` | db_models | Compat shim until 2.5 |
| `create_upload` | `create_upload_session` | db_intake | Compat shim until 2.5 |
| `get_upload` | `get_upload_session` | db_intake | Compat shim until 2.5 |
| `update_upload_status` | `update_upload_session_status` | db_intake | Compat shim until 2.5 |

**Migration**: Update to new names; compat shim ensures old names still work until Phase 2.5.

#### 2. Service Constructor Changes

New services require the database module as a dependency:

```python
# Old (Phase 1 - not applicable):
# Services didn't exist

# New (Phase 2):
from app.services.model_detail_service import ModelDetailService
from app import db_models

service = ModelDetailService(db_models)
detail = service.get_enriched_detail(model_id)
```

#### 3. Error Handling

New domain-specific exceptions replace generic `ValueError`:

```python
# Old (Phase 1):
try:
    result = db.get_model(model_id)
    if not result:
        raise ValueError("Model not found")
except ValueError as e:
    return {"error": str(e)}

# New (Phase 2):
from app.services.exceptions import ModelNotFoundError

try:
    result = service.get_detail(model_id)
except ModelNotFoundError as e:
    return {"error": str(e)}
```

---

## Testing Impact

### Router Tests

Router tests should now mock services instead of database directly:

```python
# Old (Phase 1):
@pytest.fixture
def mock_db(monkeypatch):
    monkeypatch.setattr("app.db.get_model_entry", mock_get_model)

def test_get_detail(mock_db):
    response = client.get("/api/models/abc123/detail")
    assert response.status_code == 200

# New (Phase 2):
@pytest.fixture
def mock_service(monkeypatch):
    monkeypatch.setattr(
        "app.services.model_detail_service.ModelDetailService.get_enriched_detail",
        mock_get_detail
    )

def test_get_detail(mock_service):
    response = client.get("/api/models/abc123/detail")
    assert response.status_code == 200
```

### Service Tests

New service-level tests cover business logic:

```python
from app.services.model_detail_service import ModelDetailService
import app.db_models as db_models

@pytest.fixture
def service():
    return ModelDetailService(db_models)

def test_enrichment_adds_filament_info(service):
    # Create model with filament_uuid field
    # Call service.get_enriched_detail
    # Verify Spoolman data is included
    pass
```

---

## Performance Impact

### No User-Facing Changes

Response times are unchanged. Phase 2 refactoring does not alter the execution path for typical requests.

### Internal Improvements

- Service-level caching (future Phase 2.4+)
- Lazy loading of enrichment data (Phase 2.2)
- Parallel async queries (Phase 2.5+)

---

## Common Questions

### Q: Do I need to update my Home Assistant configuration?

**A**: No. All endpoints and webhooks work identically. No configuration changes needed.

### Q: Do I need to update my automation scripts?

**A**: No. If you're calling the API from automations, no changes needed.

### Q: Do I need to rebuild my Docker image?

**A**: No. Phase 2 refactoring is fully backward compatible. Deploy normally.

### Q: What if I'm using undocumented endpoints?

**A**: These are not guaranteed stable. Review the OpenAPI schema (`GET /openapi.json`) for the authoritative API contract.

### Q: Can I still set custom fields on models?

**A**: Yes, exactly as before:
```bash
PUT /api/models/{model_ref}/fields/{key} with value in body
```

### Q: How do I find the new module structure?

**A**: See [Model Catalog App README](/sidecars/model_catalog/README.md) for module organization and [Model Catalog Architecture](model-catalog-sidecar-architecture.md) for design details.

---

## Support & Questions

For questions about the refactoring:
- Review [model-catalog-sidecar-architecture.md](model-catalog-sidecar-architecture.md)
- Check [/sidecars/model_catalog/README.md](/sidecars/model_catalog/README.md) for module overview
- Open an issue on GitHub with the `model_catalog`, `documentation` labels

For API contract questions:
- Review OpenAPI schema: `GET /openapi.json`
- Check [model-catalog-sidecar-architecture.md § API Contracts](model-catalog-sidecar-architecture.md#api-contracts)

