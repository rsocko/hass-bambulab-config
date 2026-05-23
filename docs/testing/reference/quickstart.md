# Phase 3.0 Testing Quick Start

## Current Status
✅ Code deployed  
✅ Test infrastructure created  
⏳ Sidecar offline (not running)

---

## Quick Links
- **Validation Script**: `python tests/phase3/test_e2e_validation.py`
- **Test Documentation**: `docs/testing/reference/phase3-test-automation.md`
- **Test Report**: `docs/testing/archive/phase3-test-report.md`

---

## 3-Step Validation

### 1️⃣ Start Sidecar
```bash
cd sidecars/model_catalog
python -m app.main
```

### 2️⃣ Run Integration Tests
```bash
pytest tests/phase3/test_model_detail_integration.py -v
```
**Expected**: 30+ tests pass ✅

### 3️⃣ Run E2E Validation
```bash
python tests/phase3/test_e2e_validation.py
```
**Expected Output**:
```
======================================================================
PHASE 3.0 END-TO-END VALIDATION
======================================================================

Testing Sidecar...
✅ PASS Sidecar Health Check
✅ PASS Sidecar Config

Testing API Endpoints...
✅ PASS Model List Endpoint
✅ PASS Model Search Endpoint
✅ PASS Model Detail Endpoint

Testing HA Integration...
✅ PASS REST Command Configured
✅ PASS Helper Entities Configured
✅ PASS Custom Card File

======================================================================
SUMMARY: 8/8 passed, 0/8 failed
======================================================================
```

---

## What Was Created

### Test Files
1. `tests/phase3/test_model_detail_endpoint.py` - 8 sidecar endpoint tests
2. `tests/phase3/test_model_detail_integration.py` - 30+ integration tests
3. `tests/phase3/test_e2e_validation.py` - 8 E2E validator tests

### Documentation
1. `docs/testing/reference/phase3-test-automation.md` - Comprehensive testing guide
2. `docs/testing/archive/phase3-test-report.md` - Test summary and execution guide

---

## Deployed Components Being Tested

### Sidecar Endpoint
- **File**: `sidecars/model_catalog/app/main.py`
- **Endpoint**: `GET /api/models/{model_ref}/detail`
- **Test**: E2E validator tests endpoint response

### Custom Card
- **File**: `homeassistant/www/3d_printing/model_catalog/model-detail-popup-card.js`
- **Test**: Integration tests validate file structure and methods

### REST Command
- **File**: `homeassistant/packages/3d_printing/model_catalog/rest_commands/get_model_detail.yaml`
- **Test**: Integration tests validate configuration

### Helper Entities
- **File**: `homeassistant/packages/3d_printing/model_catalog/helpers/input_text/input_text_model_catalog_sidecar_base_url.yaml`
- **Test**: Integration tests validate entity definitions

---

## Manual Testing (Without Tests)

### Test Endpoint Directly
```bash
curl http://localhost:8314/api/models/gridfinity-bin/detail
```

### Test in HA
1. Set helper entity: `input_text.model_catalog_sidecar_base_url` = "http://localhost:8314"
2. Call service: `rest_command.get_model_detail` with `model_ref: "gridfinity-bin"`
3. Check card renders with data

### Test Card in Dashboard
```yaml
type: custom:model-detail-popup-card
model_ref: gridfinity-bin
model_entity: input_text.model_catalog_sidecar_base_url
```

---

## Troubleshooting

### Sidecar Won't Start
```bash
# Check Python version
python --version  # Must be 3.8+

# Check dependencies
pip install -r sidecars/model_catalog/requirements.txt

# Check logs
python -m app.main --debug
```

### Tests Won't Run
```bash
# Ensure pytest installed
pip install pytest

# Ensure working directory correct
cd /path/to/hass-bambulab-config

# Run with verbose output
pytest tests/phase3/ -v --tb=short
```

### Endpoint Returns 404
- Ensure model exists in Manyfold
- Check `public_id` or `model_id` format
- Verify sidecar can reach Manyfold API

---

## What's Next

After validation ✅:

1. **Merge** - Merge Phase 3.0 branch to main
2. **Announce** - Notify users of new Model Detail View
3. **Phase 3.1** - Implement gallery & 3D viewer tabs
4. **CI/CD** - Add tests to GitHub Actions

---

## Questions?

See full documentation:
- Testing guide: `docs/testing/reference/phase3-test-automation.md`
- Implementation report: `docs/features/model_catalog/phase-3-implementation-report.md`
- Design spec: `docs/features/model_catalog/phase-3-detail-view-design.md`
