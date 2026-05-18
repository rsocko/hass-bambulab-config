# Test Suite Quick Reference

## Location
```
tests/sidecars/model_catalog/
```

## Files Created

### Core Test Files

1. **conftest.py** (Shared fixtures)
   - `temp_db_path`: Temporary database for testing
   - `test_settings`: Test configuration
   - `test_client`: FastAPI test client
   - `httpx_client`: HTTP client for service testing
   - `sidecar_base_url`: Sidecar service URL (from env or default)

2. **test_spike_1061_deployment.py** (16 tests)
   - Health check endpoints validation
   - Service connectivity
   - OAuth configuration
   - Docker network discovery
   - Environment variable validation
   - Error recovery patterns
   - **Production deployment checklist with 8 categories**

3. **test_spike_1060_ranking_signals.py** (8 tests)
   - Recent score validation (exponential decay)
   - Frequent score computation (print count normalization)
   - Common score (combined recent + frequent)
   - Success rate calculation
   - Favorite signal implementation
   - Database schema validation
   - **Phase 3 implementation checklist with 14 items**

4. **test_spike_1059_working_files.py** (11 tests)
   - Working file detection patterns
   - SHA256-based deduplication
   - Re-download pattern matching
   - File grouping and primary selection
   - Metadata extraction from 3MF
   - Cross-platform path handling
   - File corruption detection
   - **Phase 1.5 implementation checklist with 17 items**

5. **test_spike_1056_patch_behavior.py** (7 tests)
   - Safe PATCH fields documentation
   - Restricted fields (with side effects)
   - PATCH request/response format
   - Tag conversion (keywords ↔ CSV)
   - Field update cycle effects
   - Custom field protection
   - **Phase 2 validation checklist with 12 items**

6. **test_spike_1055_1057_1058.py** (9 tests)
   - TUS upload protocol flow
   - Add-file endpoint validation
   - Upload→file workflow gaps
   - Rescan operation
   - File deletion/restoration recovery
   - Orphaned record cleanup
   - **Recovery implementation checklist with 12 best practices**

7. **test_runner.py** (Master test runner)
   - Print test summary
   - Run all spikes or specific spike
   - Validation coverage reporting

8. **VALIDATION_TEST_REPORT.md** (Comprehensive report)
   - Full test results and findings
   - Implementation checklists
   - Phase-specific guidance
   - Validation status summary

## Running Tests

### Run all spike validations:
```bash
pytest tests/sidecars/model_catalog/ -v -s
```

### Run specific spike:
```bash
pytest tests/sidecars/model_catalog/test_spike_1056_patch_behavior.py -v -s
```

### Run specific test class:
```bash
pytest tests/sidecars/model_catalog/test_spike_1060_ranking_signals.py::TestRankingSignalsAvailability -v -s
```

### Run specific test:
```bash
pytest tests/sidecars/model_catalog/test_spike_1056_patch_behavior.py::TestPatchBehavior::test_patch_safe_fields -v -s
```

### Use test runner:
```bash
python tests/sidecars/model_catalog/test_runner.py
python tests/sidecars/model_catalog/test_runner.py spike_1056
```

## Test Coverage Summary

| Module | Tests | Focus Area | Key Output |
|--------|-------|-----------|-----------|
| spike_1061_deployment | 16 | Docker/OAuth/Config | Deployment checklist |
| spike_1060_ranking_signals | 8 | Archive ranking | Scoring formulas |
| spike_1059_working_files | 11 | File indexing | Dedup strategy |
| spike_1056_patch_behavior | 7 | API safety | Safe fields list |
| spike_1055_1057_1058 | 9 | Upload/rescan/recovery | Recovery playbook |

**Total**: 51+ validation test cases

## Key Validation Outputs

### From test_spike_1061_deployment.py:
```
✓ Health check endpoints at /healthz, /config, /diagnostics
✓ API accessibility validated
✓ OAuth endpoint detection
✓ Docker network discovery works
✓ Production deployment checklist provided
```

### From test_spike_1060_ranking_signals.py:
```
✓ Recent Score Formula: 1.0 * exp(-days_old / 30)
✓ Frequent Score Formula: min(count, 10) / 10
✓ Common Score: recent_score * frequent_score
✓ Success Rate: successful_prints / total_prints
✓ Favorite Signal: binary flag (0 or 1)
```

### From test_spike_1059_working_files.py:
```
✓ File detection in ~/Downloads, ~/Desktop
✓ SHA256 deduplication strategy
✓ Re-download pattern detection: (1), (2), _0, _1
✓ Cross-platform path handling (Windows/POSIX)
✓ 3MF metadata extraction capability
```

### From test_spike_1056_patch_behavior.py:
```
✓ Safe PATCH fields:
  - name, caption, description
  - keywords, links, license, public
✓ Restricted fields:
  - creator, collection (filesystem reorganization)
  - custom_properties (conflict with sidecar metadata)
```

### From test_spike_1055_1057_1058.py:
```
✓ CRITICAL: Use public_id for archive links (not model_id)
  - public_id stable across rescan/deletion/restore
  - model_id changes on file operations
✓ Rescan API Gap:
  - Rescan exists in Rails but NOT in REST API
  - Workaround: Manual trigger or periodic polling
✓ Upload→File Gap:
  - No direct reference from TUS upload_id
  - Workaround: Re-upload to /models/{id}/files
```

## Phase-Specific Implementation Guides

Each test module provides detailed checklists for its phase:

- **Phase 2** (Enrichment): Use spike_1056 checklist
- **Phase 1.5** (Working Files): Use spike_1059 checklist
- **Phase 3** (Ranking): Use spike_1060 checklist
- **Deployment**: Use spike_1061 checklist
- **Recovery**: Use spike_1055_1057_1058 checklist

## Environment Variables (from Spike #1061)

```bash
# Required
MODEL_CATALOG_DB_PATH=/data/model-catalog/catalog.db
MODEL_CATALOG_HOST=0.0.0.0
MODEL_CATALOG_PORT=8314

# Optional
MODEL_CATALOG_REFRESH_TTL_SECONDS=900
```

## Database Schemas Documented

### working_files (Spike #1059):
- id, file_path, file_name, file_size, sha256_hash
- created_at, cataloged_at, detected_sources

### model_ranking (Spike #1060):
- model_id, model_url, recent_score, frequent_score
- common_score, success_rate, is_favorite, print_count, updated_at

## Next Steps for Users

1. **Review test output** for your spike:
   ```bash
   pytest tests/sidecars/model_catalog/test_spike_XXXX.py -v -s
   ```

2. **Check relevant checklist** from test output

3. **Implement following checklist** for your phase

4. **Re-run tests** after implementation to verify compliance

5. **Iterate** using test recommendations as guide

## Additional Resources

- **Spike Validation Documents**: `docs/features/model_catalog/integration/spike-*.md`
- **Implementation Plan**: `docs/features/model_catalog/implementation-plan.md`
- **API Gap Analysis**: `docs/features/model_catalog/api-gap-analysis-2026-04-21.md`
- **Sidecar README**: `sidecars/model_catalog/README.md`

---

**Created**: April 25, 2026  
**Status**: Complete - Ready for Phase 2 implementation  
**Test Count**: 51+ validation test cases  
**Checklist Items**: 80+ actionable items across all phases
