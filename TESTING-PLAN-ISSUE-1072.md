# Issue #1072 Testing & Validation Plan
## Phase 3: HA Filtered Backlog/Queue View

**Issue**: Implement HA backlog/queue views powered by sidecar queue fields and ranking signals.

**Status**: Changes committed and deployed. Testing and validation needed.

**Last Updated**: 2026-04-25

---

## Automated Tests ✅ PASSING

### Unit Tests - Model Catalog Sidecar (52 tests)
**Location**: `tests/sidecars/test_model_catalog_sidecar.py`

**Run command**:
```bash
python -m pytest tests/sidecars/test_model_catalog_sidecar.py -v
```

**Result**: ✅ **52/52 PASSED** (20.03s)

**Key test coverage**:
- `test_model_fields_can_be_managed_and_used_for_model_list_filters`
  - Tests setting and reading `to_print_status` and `to_print_priority` fields
  - Validates field filtering by status and priority ranges
  - Verifies sorting by priority works correctly

- `test_model_queue_endpoint_supports_status_and_priority_actions`
  - Tests POST `/api/models/{model_ref}/queue` endpoint
  - Validates actions: `mark_queued`, `priority_up`, `mark_done`
  - Confirms direct `to_print_status` and `to_print_priority` values
  - Validates response payload structure

- `test_model_search_supports_priority_filters`
  - Tests filtering search results by `to_print_priority_min` and `to_print_priority_max`
  - Validates models are excluded/included based on priority ranges

---

## Sidecar API Endpoints (Tested)

### 1. Queue Status/Priority Update
**Endpoint**: `POST /api/models/{model_ref}/queue`

**Actions**:
- `mark_queued` - Set `to_print_status` to "queued" with optional priority
- `priority_up` - Increment `to_print_priority` by 1
- `priority_down` - Decrement `to_print_priority` by 1
- `mark_done` - Set `to_print_status` to "done"
- `clear` - Remove queue state (set to_print_status to "none")

**Direct values**:
- `to_print_status` - Set directly to "none", "queued", or "done"
- `to_print_priority` - Set to numeric value
- `priority_delta` - Adjust priority by +/- delta

**Example requests**:
```bash
# Mark as queued with priority 5
curl -X POST http://localhost:8314/api/models/gridfinity-bin/queue \
  -H "Content-Type: application/json" \
  -d '{"action":"mark_queued","to_print_priority":5}'

# Increment priority
curl -X POST http://localhost:8314/api/models/gridfinity-bin/queue \
  -H "Content-Type: application/json" \
  -d '{"action":"priority_up"}'

# Set direct status
curl -X POST http://localhost:8314/api/models/gridfinity-bin/queue \
  -H "Content-Type: application/json" \
  -d '{"to_print_status":"done"}'
```

### 2. Search with Queue Filters
**Endpoint**: `GET /api/models?to_print_status=queued&to_print_priority_min=1&to_print_priority_max=10&sort=priority`

**Query parameters**:
- `to_print_status` - Filter by "none", "queued", "done"
- `to_print_priority_min` - Minimum priority (inclusive)
- `to_print_priority_max` - Maximum priority (inclusive)
- `sort` - Sort by "priority", "recent", "frequent", or "common"

---

## Home Assistant Integration (Manual Testing Required)

### 1. Dashboard View Access
**Path**: `http://<ha-url>:8123/dashboard/model-catalog`

**Dashboard card**: `custom:model-catalog-browser-card`

**Verification**:
- ✅ Model Catalog view loads without errors
- ⚠️ **Verify filter UI renders correctly** (see below)
- ⚠️ **Verify quick action buttons appear** (see below)

### 2. Filter UI Components (Manual Test)
**Location**: Model Catalog dashboard view

**Filters to test**:
1. **Queue Status Filter** (`#mc-queue` dropdown)
   - Options: All, None, Queued, Done
   - **Test**: Select "Queued" and verify only queued models appear
   - **Test**: Select "Done" and verify only done models appear

2. **Priority Range Filters** (`#mc-priority-min`, `#mc-priority-max` inputs)
   - **Test**: Set min=1, max=5 and verify models within range appear
   - **Test**: Set min=10 and verify only high-priority models appear
   - **Test**: Leave blank and verify no filtering occurs

3. **Sort Options** (dropdown)
   - "Priority" - Models sorted by `to_print_priority` descending (highest first)
   - "Recent" - By last print date
   - "Frequent" - By print count
   - "Common" - By other ranking signals
   - **Test**: Select "Priority" and verify order matches priorities

### 3. Quick Action Buttons (Manual Test)
**Location**: Model card in catalog view

**Buttons to test**:
1. **Queue Priority Up** (↑)
   - **Test**: Click on a queued model's up arrow
   - **Expected**: Model's `to_print_priority` increments by 1
   - **Expected**: UI updates to show new priority
   - **Expected**: Model position in sorted list may change

2. **Queue Priority Down** (↓)
   - **Test**: Click on a queued model's down arrow
   - **Expected**: Model's `to_print_priority` decrements by 1
   - **Expected**: UI updates to show new priority

3. **Mark as Queued** (+ button or queue action)
   - **Test**: Click on an un-queued model
   - **Expected**: Model's `to_print_status` changes to "queued"
   - **Expected**: Model appears in queue status filter results
   - **Expected**: Priority input appears if not already present

4. **Mark as Done** (✓ or complete action)
   - **Test**: Click on a queued model's done button
   - **Expected**: Model's `to_print_status` changes to "done"
   - **Expected**: Model no longer appears when filtering by "queued"

### 4. HA REST Commands (Manual Test)
**Location**: Configuration → Developer Tools → Services

**Service**: `rest_command.model_catalog_update_model_queue`

**Parameters**:
- `model_ref` - Model identifier or public_id (string)
- `action` - One of: mark_queued, mark_done, priority_up, priority_down, clear
- `to_print_status` - Direct value: "none", "queued", "done"
- `to_print_priority` - Numeric priority value
- `priority_delta` - Relative change to priority (+/-)

**Manual test**:
1. Open Developer Tools → Services
2. Search for `rest_command.model_catalog_update_model_queue`
3. Fill in example parameters:
   ```yaml
   model_ref: gridfinity-bin
   action: mark_queued
   to_print_priority: 5
   ```
4. Click Execute
5. **Expected**: Service succeeds with status 200
6. **Expected**: HA notification or logbook entry if configured
7. Verify via browser: Browse Model Catalog → search for model → confirm priority is 5

### 5. Backlog/Queue State Persistence (Manual Test)
**Test**: Queue state survives Home Assistant restart

**Steps**:
1. In Model Catalog view, queue 3 models with different priorities (e.g., 1, 5, 10)
2. Restart Home Assistant (Settings → System → Restart)
3. After restart, navigate back to Model Catalog
4. Filter by `to_print_status=queued` and `sort=priority`
5. **Expected**: Same 3 models appear, sorted by priority (10, 5, 1)
6. **Expected**: Priorities match what was set before restart

### 6. Search Results with Queue Filters (Manual Test)
**Location**: Model Catalog view

**Steps**:
1. In the dashboard, queue 5-10 models with varying priorities
2. Mark some as done, leave others queued
3. Filter by `to_print_status=queued`
4. **Expected**: Only queued models appear
5. Set priority range min=3, max=7
6. **Expected**: Only queued models with priority 3-7 appear
7. Change sort to "priority"
8. **Expected**: Models appear in descending priority order

### 7. Custom Card JavaScript Validation (Browser Console)
**Manual test**: Custom card loads and renders correctly

**Steps**:
1. Open Model Catalog dashboard
2. Open browser DevTools (F12)
3. Console tab - check for JavaScript errors
4. **Expected**: No errors related to `model-catalog-browser-card`
5. Elements tab - inspect model card elements
6. **Expected**: Filter inputs present: `#mc-queue`, `#mc-priority-min`, `#mc-priority-max`
7. **Expected**: Sort dropdown and buttons rendered correctly

---

## Archive Link → Queue Update (Stub Implementation)

### Current Status
**Automation**: `model_catalog_on_link_accepted.yaml`
- Currently logs to logbook only
- **TODO**: Replace with actual queue update logic

**When implemented**, test:
1. Accept an archive-model link in archive popup
2. **Expected**: Trigger fires and updates model's `to_print_status`
3. **Expected**: If print is marked complete, status should change to "done"
4. Verify in Model Catalog dashboard that status changed

---

## Configuration Checklist

- [ ] Model Catalog sidecar running and healthy
  - Health check: `http://localhost:8314/health`
- [ ] HA can reach sidecar at configured URL
  - Helper: `input_text.model_catalog_sidecar_base_url` should be set
- [ ] Manyfold integration configured in sidecar
  - Check sidecar logs: `docker logs model-catalog`
- [ ] REST command configured in HA
  - File: `homeassistant/packages/3d_printing/model_catalog/rest_commands/model_catalog_update_model_queue.yaml`
  - Should be auto-loaded via package loader

---

## Known Limitations & Notes

1. **Custom Card Not Yet Deployed to /local/**
   - The `model-catalog-browser-card.js` exists in source
   - Resource URL must be registered in HA dashboard resources
   - Check `homeassistant/packages/3d_printing/common/dashboards/_resources.yaml`

2. **Archive Link → Queue Update Automation**
   - Currently a stub that only logs to logbook
   - Phase 3 task: Replace with actual service call to update queue status
   - Would require calling `rest_command.model_catalog_update_model_queue` after link accepted

3. **No Playwright E2E Tests Yet**
   - UI tests would require Playwright setup
   - Manual browser testing in this plan covers critical UI flows

4. **Priority Values**
   - Numeric field, no hard constraints
   - Lower numbers = higher priority in current UI (0 = highest)
   - Sorting: descending by default (highest priority first)

---

## Acceptance Criteria Checklist

From issue #1072:
- [ ] **Backlog view filtered by `to_print_status` and/or priority**
  - ✅ Filter UI implemented in custom card
  - ⚠️ Manual test: Verify filters work end-to-end

- [ ] **Quick actions to re-rank / adjust priority / mark statuses**
  - ✅ Buttons implemented: up/down/mark-queued/mark-done
  - ⚠️ Manual test: Verify each button updates state correctly

- [ ] **Uses sidecar endpoints**
  - ✅ Sidecar endpoints implemented and unit-tested
  - ✅ HA REST commands configured
  - ⚠️ Manual test: Verify integration works end-to-end

---

## Next Steps (If Tests Pass)

1. **Deploy Changes**: If all manual tests pass, notify user that deployment is validated
2. **Archive Link Automation**: Implement Phase 3.5 update to `model_catalog_on_link_accepted.yaml` to call queue update service
3. **Browser Resource Versioning**: Verify dashboard resource URL is registered with cache-busting version parameter (per repo guidelines)
4. **Documentation**: Update user-facing docs on how to use the backlog/queue view

---

## Test Results Summary

| Component | Tests | Result | Notes |
|-----------|-------|--------|-------|
| Sidecar Unit Tests | 52 | ✅ PASSED | All queue/priority tests pass |
| API Endpoint | 3+ | ✅ TESTED | Mark/priority actions verified |
| Filter Logic | 2+ | ✅ TESTED | Status/priority filtering verified |
| HA Integration | TBD | ⚠️ MANUAL | See manual testing section |
| UI Rendering | TBD | ⚠️ MANUAL | See dashboard verification |
| Persistence | TBD | ⚠️ MANUAL | Test after HA restart |

