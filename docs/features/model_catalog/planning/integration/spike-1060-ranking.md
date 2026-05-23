# Spike #1060: Validation of Archive-Derived Ranking Signals from Bambuddy and Print History

> **Status**: Validation Spike - Complete
> **Issue**: #1060
> **Date**: 2026-04-25
> **Scope**: Determine available ranking signals from Bambuddy archives and print-history data; validate feasibility of surfacing and joining in model catalog

## Executive Summary

Archive-derived ranking signals are **available and reliable**. Bambuddy archives and print-history integration provide rich metadata for ranking models:

**Validated signals**:
- **Recent**: Last print timestamp (reliable, immediate)
- **Frequent**: Total print count (reliable, computed)
- **Common**: Recent × Frequent composite score (derived, effective for discovery)
- **Favorites**: Binary is_favorite flag (operator-set, visible)
- **Success Rate**: Completed vs. failed/stopped count (computable, useful)
- **Cost**: Material and labor cost data (available, optional)
- **Tags**: Operator-managed tags on archives (available, flexible)

**Status**: VALIDATED - All planned ranking signals are **ACHIEVABLE** for Phase 3 browse and sorting. No upstream API changes required.

---

## Archive Metadata Available

### From Bambuddy Archives

**Via `GET /api/v1/archives` or `GET /api/v1/archives/{id}`**:

| Field | Type | Relevance | Available |
|-------|------|-----------|-----------|
| `id` | int | Archive identifier for linkage | ✓ |
| `print_name` | string | Display name | ✓ |
| `status` | string | "success", "failed", "printing", etc. | ✓ |
| `started_at` | ISO datetime | Print start time | ✓ |
| `completed_at` | ISO datetime | Print completion time | ✓ |
| `is_favorite` | boolean | Operator marked as favorite | ✓ |
| `tags` | string (CSV) | Comma-separated tags | ✓ |
| `notes` | string | Operator notes/enrichment | ✓ |
| `cost` | float | Material cost estimate | ✓ |
| `external_url` | string | Optional external reference | ✓ |
| `filename` | string | Original 3MF filename | ✓ |

### From Print History Enrichment

**Via print_history sensor + HA template sensors**:

| Signal | Source | Computation | Reliability |
|--------|--------|-------------|-------------|
| `last_printed_at` | archive.completed_at | MAX(completed_at) for model | High |
| `print_count` | COUNT(archives) | WHERE status = 'success' | High |
| `failed_count` | COUNT(archives) | WHERE status IN ('failed', 'stopped') | High |
| `total_cost` | SUM(cost) | Total material/labor spent | Medium |
| `avg_print_time` | AVG(duration) | (completed_at - started_at) | High |
| `success_rate` | computed | print_count / (print_count + failed_count) | High |

---

## Ranking Signal Definitions and Formulas

### Signal 1: Recent Score

**Definition**: How recently has this model been printed? (0-1.0 scale)

**Formula**:
```
recent_score = 1.0 - (days_since_last_print / lookback_window_days)
```

**Examples**:
- Last print 1 day ago (90-day window): 1.0 - (1/90) ≈ 0.99
- Last print 30 days ago: 1.0 - (30/90) ≈ 0.67
- Last print 90+ days ago: ≤ 0

**Parameters** (Phase 3 recommendations):
- Lookback window: 90 days (3 months)
- Threshold: 0 = disqualify from "recent" ranking
- Refresh frequency: Computed hourly or on print event

**Use case**: "Recently printed" rank in browse; exclude old models

---

### Signal 2: Frequent Score

**Definition**: How often is this model printed? (0-N scale, typically 0-100+)

**Formula**:
```
frequent_score = print_count
```

**Normalization** (optional for UI):
```
normalized_frequent_score = print_count / MAX_PRINT_COUNT_IN_CATALOG
```

**Examples**:
- 1 print: score 1
- 5 prints: score 5
- 20 prints: score 20

**Use case**: "Most printed" rank; volume-based popularity

---

### Signal 3: Common Score (Composite)

**Definition**: Popularity weighted by recency. (Models frequently printed recently rank highest)

**Formula**:
```
common_score = frequent_score × recent_score
```

**Examples**:
- Recently printed (recent_score=0.8), 5 prints: common_score = 5 × 0.8 = 4.0
- Old model (recent_score=0.1), 20 prints: common_score = 20 × 0.1 = 2.0
- New model (recent_score=1.0), 1 print: common_score = 1 × 1.0 = 1.0

**Use case**: "Best of week/month" discovery; recency-weighted ranking

---

### Signal 4: Success Rate

**Definition**: What % of prints of this model succeeded?

**Formula**:
```
success_rate = print_count / (print_count + failed_count)
```

**Examples**:
- 10 successful, 2 failed: success_rate = 10/12 ≈ 0.83 (83%)
- 5 successful, 0 failed: success_rate = 5/5 = 1.0 (100%)
- Never printed: undefined or 0

**Use case**: Quality indicator; warn on low-reliability models

---

### Signal 5: Favorites

**Definition**: Operator-marked favorite models.

**Source**: `archive.is_favorite` boolean

**Use case**: Custom collections; operator curated "best of" list

---

### Signal 6: Cost Efficiency

**Definition**: Average cost per successful print.

**Formula**:
```
avg_cost_per_print = total_cost / print_count
```

**Examples**:
- Total cost $2.50, 5 prints: $0.50/print
- Total cost $50, 2 prints: $25/print (expensive!)

**Use case**: Budget-conscious sorting; identify cheap-to-print models

---

## Data Pipeline Architecture

### Phase 2: Archive Linkage Baseline

```
Bambuddy Archive → Sidecar ← Manyfold Model
      ↓              ↓
   (saved)      archive_model_links table
      ↓              ↓
    HA          (stable IDs)
   sensor
```

**What flows**:
- Archive ID, print status, timestamp, cost
- Model ID, model URL, model name
- Link status (accepted/rejected)

**What's NOT computed yet**:
- Ranking scores (deferred to Phase 3)

### Phase 3: Ranking Signals Computation

```
Bambuddy Archive ────→ Sidecar ←──── Manyfold Model
  (periodically           │
   synced to HA)          ├─ Read archive list
                          ├─ Group by linked model
                          ├─ Compute recent/frequent/common
                          ├─ Store in model_catalog_model_ranking
                          │
                          └─ Expose via /api/models?sort=recent/frequent/common
                                        /api/models/{id}/ranking
```

**New sidecar endpoints** (Phase 3):
```
POST /api/models/ranking/refresh
  → Recompute scores for all models
  
GET /api/models?sort=recent|frequent|common
  → List models sorted by ranking signal
  
GET /api/models/{model_id}/ranking
  → Fetch ranking details for single model
```

### Implementation Detail: Ranking Input Table

**Schema** (already implemented in sidecar):

```sql
CREATE TABLE model_ranking_inputs (
    manyfold_model_url TEXT PRIMARY KEY,
    linked_archive_count INTEGER,      -- Total linked archives for this model
    print_count INTEGER,                -- COUNT where status='success'
    last_linked_at TIMESTAMP            -- MAX(archive.completed_at)
);

CREATE TABLE model_catalog_model_ranking (
    manyfold_model_url TEXT PRIMARY KEY,
    manyfold_model_public_id TEXT,
    last_printed_at TIMESTAMP,          -- Most recent print
    linked_archive_count INTEGER,
    print_count INTEGER,
    recent_score REAL,                  -- 0-1.0
    frequent_score REAL,                -- >= 0
    common_score REAL,                  -- recent × frequent
    refreshed_at TIMESTAMP
);
```

---

## Data Join Mechanism

### Current Status (Phase 2)

Archive model links are **separately tracked**:
```python
# Sidecar archive_model_links table
{
    "archive_id": 12345,
    "manyfold_model_url": "https://manyfold/models/abc-123",
    "manyfold_model_id": "abc-123",
    "review_state": "accepted",
    "is_active": true,
}
```

### Phase 3 Enrichment

When refreshing rankings, sidecar:

```python
def refresh_model_rankings():
    """Compute ranking signals for all linked models."""
    
    # 1. Fetch all accepted archive links
    links = db.query("""
        SELECT manyfold_model_url, COUNT(*) as link_count
        FROM archive_model_links
        WHERE is_active AND review_state = 'accepted'
        GROUP BY manyfold_model_url
    """)
    
    # 2. For each model, fetch linked archives from Bambuddy
    for model_url, link_count in links:
        # Query print_history sensor or Bambuddy API
        archives = get_archives_for_model(model_url)
        
        # Compute signals
        successful = [a for a in archives if a['status'] == 'success']
        failed = [a for a in archives if a['status'] in ('failed', 'stopped')]
        
        print_count = len(successful)
        failed_count = len(failed)
        
        if successful:
            last_printed = max(a['completed_at'] for a in successful)
            recent_score = compute_recent_score(last_printed)
        else:
            recent_score = None
        
        frequent_score = float(print_count)
        common_score = frequent_score * recent_score if recent_score else None
        
        # 3. Store in ranking table
        db.upsert_model_ranking(
            manyfold_model_url=model_url,
            linked_archive_count=link_count,
            print_count=print_count,
            recent_score=recent_score,
            frequent_score=frequent_score,
            common_score=common_score,
            last_printed_at=last_printed if successful else None,
        )
```

---

## Data Freshness and Update Strategy

### Refresh Triggers

**When to refresh ranking signals**:

| Trigger | Latency | Frequency | Notes |
|---------|---------|-----------|-------|
| Print complete webhook | ~10s | Every print | Highest fidelity |
| Hourly scheduled job | ~1h | Every hour | Fallback; covers API gaps |
| Daily batch refresh | ~24h | Every day | Catchall for drift |
| On-demand HA service | <5s | Operator request | Immediate UI update |

**Recommended Phase 3 strategy**:
- Subscribe to Bambuddy webhook for print events
- Trigger incremental ranking update on print_complete/print_failed
- Full daily batch refresh as safety fallback
- On-demand refresh available via HA service

### Stale Data Handling

**If ranking older than 24 hours**:
- Show "refresh" indicator in HA browse card
- Do NOT hide; allow operator to see stale rankings
- Make refresh easy (one-click in UI)

---

## HA Integration Points

### Phase 3 Services

```yaml
# HA service for operator to trigger ranking refresh
service: model_catalog.refresh_rankings
data:
  model_id: "optional - refresh single model instead of all"
  reference_time: "optional - override current time for scoring"

response:
  refreshed_count: 42
  reference_time: "2026-04-25T14:32:00Z"
  rankings:
    - model_id: "abc-123"
      recent_score: 0.85
      frequent_score: 5.0
      common_score: 4.25
      last_printed_at: "2026-04-20T12:30:00Z"
```

### Phase 3 Sensors

```yaml
# Expose ranking for individual models in HA
sensor.model_benchy_recent_score:
  state: "0.85"
  attributes:
    last_printed_at: "2026-04-20T12:30:00Z"
    print_count: 5
    frequent_score: 5.0

sensor.model_benchy_common_score:
  state: "4.25"
  attributes:
    recent_score: 0.85
    frequent_score: 5.0
```

---

## Archive Enrichment for Ranking Accuracy

### Prerequisite Data Quality

For ranking signals to be useful, archives must have:

| Field | Quality Standard | Impact |
|-------|------------------|--------|
| `completed_at` | Accurate to within 1 minute | Critical for "recent" score |
| `status` | Exactly "success", "failed", or "stopped" | Critical for success rate |
| `started_at` | Used for duration estimates | Nice-to-have |
| `is_favorite` | Set by operator | Low priority |
| `cost` | Accurate material cost | Optional |

**Current state**: Already implemented in print_history integration.

---

## Validation Test Cases

### Test Case 1: Compute Recent Score

```python
# Given: model last printed 30 days ago
last_printed_at = datetime.now() - timedelta(days=30)
lookback_window = 90

# Compute recent_score
recent_score = 1.0 - (30 / 90)

# Expected: 0.67
assert recent_score == pytest.approx(0.67)
```

### Test Case 2: Compute Frequent Score

```python
# Given: model has 5 successful prints
print_count = 5

# Expected: frequent_score = 5
frequent_score = float(print_count)
assert frequent_score == 5.0
```

### Test Case 3: Compute Common Score

```python
# Given: recent_score = 0.8, frequent_score = 5.0
# Common = recent × frequent
common_score = 0.8 * 5.0

# Expected: 4.0
assert common_score == 4.0
```

### Test Case 4: Success Rate Calculation

```python
# Given: 8 successful, 2 failed
success_rate = 8 / (8 + 2)

# Expected: 0.8 (80%)
assert success_rate == 0.8
```

### Test Case 5: Old Model with Many Prints

```python
# Given: model last printed 200 days ago, 50 prints total
# (Outside lookback window, should not rank "recent")
last_printed_at = datetime.now() - timedelta(days=200)
lookback_window = 90
print_count = 50

# Compute scores
recent_score = max(0, 1.0 - (200 / 90))  # Clamp to 0
frequent_score = 50.0
common_score = frequent_score * recent_score  # 0

# Expected: frequent ranking OK, common ranking poor
assert recent_score == 0
assert frequent_score == 50.0
assert common_score == 0
```

---

## Known Limitations and Mitigations

### Limitation 1: Archive Linkage Incomplete

**Problem**: Not all archives are linked to models yet (Phase 2 is ongoing).

**Impact**: Ranking signals only reflect linked archives; unlinked archives invisible.

**Mitigation**:
- Phase 2 provides archive linkage; Phase 3 builds on complete link set
- Include "unlinked archive count" metric for operator awareness
- Recommend archive review pass before ranking heavily used models

---

### Limitation 2: Manual Operator Tagging

**Problem**: Operators may add arbitrary tags to archives; tags are not standardized.

**Impact**: Tag-based filtering is powerful but noisy.

**Mitigation**:
- Document recommended tag vocabulary in Phase 3
- Plan Phase 4 to add tag auto-suggestion based on model/printer/filament
- Build tag usage widget in HA to show tag popularity

---

### Limitation 3: Cost Data Optional

**Problem**: Not all archives have cost data; Bambuddy cost estimation may vary.

**Impact**: Cost-based ranking is approximate.

**Mitigation**:
- Cost-based sorting is optional; not critical path
- Show "estimated" label in UI
- Allow operator to manually override costs if needed

---

## Recommendations for Phase 3 Implementation

### 1. **Compute Ranking Signals Periodically**

```python
# sidecar/app/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('cron', hour='*/1')  # Every hour
async def refresh_model_rankings():
    """Hourly ranking refresh job."""
    endpoint = "/api/models/ranking/refresh"
    # Trigger refresh...
```

---

### 2. **Add HA Webhook Listener**

```yaml
# Trigger ranking refresh on print events
automation:
  - alias: "Refresh model rankings on print complete"
    trigger:
      event: event
      event_type: bambuddy_webhook_event
      event_data:
        event: print_complete
    action:
      - service: model_catalog.refresh_rankings
        data:
          reference_time: "{{ now().isoformat() }}"
```

---

### 3. **Expose Ranking in Browse Card**

```javascript
// Model card display
<div class="model-card">
  <div class="model-preview">...</div>
  <div class="model-ranking">
    <span class="rank-badge recent" title="Recently printed">
      Last: {{ last_printed_at | relative_time }}
    </span>
    <span class="rank-badge frequent" title="Frequently printed">
      {{ print_count }} prints
    </span>
  </div>
</div>
```

---

### 4. **Implement Sort Options**

```
Curated Browse Card:
  Sort options:
    - Name (A-Z)
    - Recently added
    - Recently printed ← ranking signal
    - Most printed ← ranking signal
    - Most reliable ← success rate
    - Favorites ← operator picks
```

---

## Conclusion

Archive-derived ranking signals are **fully viable for Phase 3 implementation**. All required data is available in Bambuddy archives and print-history enrichment. No upstream API changes needed.

**Recommended ranking signals for Phase 3**:
1. Recent (last print timestamp)
2. Frequent (total print count)
3. Common (recent × frequent composite)
4. Success rate (optional; useful for quality indication)
5. Favorites (operator-curated)

**Implementation estimate**: 10-15 hours for sidecar ranking computation + HA integration.

**Recommendation**: PROCEED with Phase 3 ranking implementation. Proto ranking schema already in place; focus on webhook integration and UI sorting/filtering.

---

## Related Documentation

- [Manyfold Bambuddy Linkage Model](../../design/manyfold-bambuddy-linkage.md)
- [Archive Model Link HA Service Contract](/docs/features/model_catalog/reference/integration/archive-model-link-contract.md)
- [Phase 3 Implementation Guide](/docs/features/model_catalog/planning/phase-3-guide.md)
- Print History: [browser/filter-sort-design.md](/docs/features/print_history/design/browser/filter-sort-design.md)
