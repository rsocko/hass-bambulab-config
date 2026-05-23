# Phase 3.3 Implementation Plan: Cross-System Integration

Status: Historical
Last Reviewed: 2026-05-23
Functional Owner: repo-docs
Replaces: ../../../../PHASE-3.3-IMPLEMENTATION-PLAN.md
Replaced By: none


**Target Date:** May 3 - May 10, 2026 (1 week)  
**Dependencies:** Phase 3.1 ✅ & Phase 3.2 ✅ Complete  
**Successor:** None (Final Phase)

## Overview

Phase 3.3 completes the model catalog by integrating it with the broader printing ecosystem:
- Link archives to their source models
- Show recommendations based on print history
- Aggregate print statistics per model
- Enable export/backup of catalog metadata

## High-Level Architecture

```
Model Catalog (Phase 3.3) integrates with:

├─ Print History (Phase 2)
│  ├─ Archive-to-model linking (via filename)
│  ├─ Print statistics (success rate, avg time, filament)
│  └─ Photo references (from archive)
│
├─ Filament Catalog (Phase 1)
│  ├─ Filament usage by model
│  └─ Material recommendations
│
├─ Statistics Dashboard (Phase 4)
│  ├─ Model performance metrics
│  └─ Failure analysis per model
│
└─ Manyfold (external)
   ├─ Model metadata (name, creator, collections)
   └─ File library (STL, OBJ, GCODE)
```

## Detailed Implementation Tasks

### Task 1: Archive-to-Model Linking (Days 1-2)

**Endpoint:** `GET /api/archives/{archive_id}/model`

**Implementation:** `sidecars/model_catalog/app/main.py`

```python
@app.get("/api/archives/{archive_id}/model")
def get_archive_model_endpoint(archive_id: int):
    """
    Find source model for an archive.
    Strategy: filename matching (exact → fuzzy → not found)
    """
    # Get archive data from print_history (API call or local cache)
    archive = get_archive_by_id(archive_id)
    if not archive:
        return JSONResponse(status_code=404, content={"error": "Archive not found"})
    
    model_filename = archive.get("model_filename")
    if not model_filename:
        return {
            "success": True,
            "archive_id": archive_id,
            "model_ref": None,
            "reason": "No filename in archive",
        }
    
    # Strategy 1: Exact filename match
    summaries = read_cached_manyfold_summaries(db_path)
    for summary in summaries:
        for file_obj in summary.files or []:
            if file_obj.get("filename") == model_filename:
                return {
                    "success": True,
                    "archive_id": archive_id,
                    "model_ref": str(summary.public_id or summary.model_id),
                    "match_method": "exact_filename",
                    "confidence": "high",
                }
    
    # Strategy 2: Fuzzy name match (strip version/variant)
    base_name = extract_base_filename(model_filename)  # "test_v2.stl" → "test"
    for summary in summaries:
        if base_name.lower() in summary.name.lower():
            return {
                "success": True,
                "archive_id": archive_id,
                "model_ref": str(summary.public_id or summary.model_id),
                "match_method": "fuzzy_name",
                "confidence": "medium",
            }
    
    # Not found
    return {
        "success": True,
        "archive_id": archive_id,
        "model_ref": None,
        "match_method": None,
        "confidence": None,
        "reason": f"No model found matching '{model_filename}'",
    }

def extract_base_filename(filename: str) -> str:
    """
    Extract base name from filename.
    Examples:
      'gridfinity-bin.stl' → 'gridfinity-bin'
      'gridfinity-bin_v2.stl' → 'gridfinity-bin'
      'test_model_v2_updated.stl' → 'test_model'
    """
    # Remove extension
    name = filename.rsplit('.', 1)[0]
    
    # Remove version suffixes (_v2, _v2_updated, etc)
    name = re.sub(r'_v\d+.*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[-_]final.*$', '', name, flags=re.IGNORECASE)
    
    return name
```

**Tests:** [tests/phase3/test_phase3_3_cross_system.py::TestModelArchiveLinking](../../../../tests/phase3/test_phase3_3_cross_system.py#L9)

### Task 2: Related Models Algorithm (Days 2-3)

**Endpoint:** `GET /api/models/{model_ref}/related?limit=5`

**Enhanced Implementation:** `sidecars/model_catalog/app/main.py`

```python
@app.get("/api/models/{model_ref}/related")
def get_related_models_endpoint(model_ref: str, limit: int = 5) -> dict[str, Any]:
    """
    Get related models by similarity score.
    Scoring:
      - Collection match: +30
      - Creator match: +25
      - Each keyword match: +5
      - Max score: 100
    """
    base_summary = _resolve_model_summary(..., model_ref)
    if not base_summary:
        return JSONResponse(status_code=404, content={"error": "Model not found"})
    
    all_summaries = read_cached_manyfold_summaries(db_path)
    related = []
    
    for summary in all_summaries:
        if summary.model_id == base_summary.model_id:
            continue
        
        score, reasons = calculate_similarity_score(base_summary, summary)
        if score > 0:
            related.append({
                "model_id": summary.model_id,
                "public_id": summary.public_id,
                "name": summary.name,
                "creator_name": summary.creator_name,
                "collections": summary.collection_names or [],
                "keywords": summary.keyword_names or [],
                "preview_url": summary.preview_url,
                "similarity_score": score,
                "match_reasons": reasons,
            })
    
    # Sort and limit
    related.sort(key=lambda x: x["similarity_score"], reverse=True)
    related = related[:limit]
    
    return {
        "success": True,
        "model_ref": model_ref,
        "model_name": base_summary.name,
        "related_models": related,
        "count": len(related),
    }

def calculate_similarity_score(base: ManyfoldModelSummary, target: ManyfoldModelSummary) -> tuple[int, list[str]]:
    """Calculate similarity score and reasons."""
    score = 0
    reasons = []
    
    # Collection match: +30
    base_colls = set(base.collection_names or [])
    target_colls = set(target.collection_names or [])
    if base_colls & target_colls:
        score += 30
        shared_colls = ", ".join(base_colls & target_colls)
        reasons.append(f"Shared collection: {shared_colls}")
    
    # Creator match: +25
    if base.creator_name and base.creator_name == target.creator_name:
        score += 25
        reasons.append(f"Same creator: {base.creator_name}")
    
    # Keyword matches: +5 each
    base_kw = set(base.keyword_names or [])
    target_kw = set(target.keyword_names or [])
    matches = base_kw & target_kw
    if matches:
        score += len(matches) * 5
        shared_kw = ", ".join(sorted(matches))
        reasons.append(f"{len(matches)} shared keywords: {shared_kw}")
    
    # Cap at 100
    score = min(100, score)
    
    return score, reasons
```

**Tests:** [tests/phase3/test_phase3_3_cross_system.py::TestRelatedModelsAlgorithm](../../../../tests/phase3/test_phase3_3_cross_system.py#L34)

### Task 3: Recommendation Engine (Days 3-4)

**Endpoint:** `GET /api/recommendations?strategy=next_steps&limit=5`

**Implementation:** `sidecars/model_catalog/app/recommendations.py` (new)

```python
class RecommendationEngine:
    """Generate smart recommendations based on print history."""
    
    def __init__(self, model_summaries: list[ManyfoldModelSummary], 
                 archives: list[dict], stats: dict):
        self.models = {s.model_id: s for s in model_summaries}
        self.archives = archives
        self.stats = stats  # success_rate, avg_print_time per model
    
    def recommend_next_steps(self, recent_archives: list[dict], limit: int = 5) -> list[dict]:
        """
        Recommend follow-up prints based on recent prints.
        Strategy: Similar models, same creator, same collection
        """
        if not recent_archives:
            return []
        
        # Get the most recent successful print
        recent = next((a for a in recent_archives if a.get("success")), None)
        if not recent:
            return []
        
        # Find its model
        model_ref = self.find_model_for_archive(recent)
        if not model_ref:
            return []
        
        # Get related models and rank
        related = self.get_related_models(model_ref)
        recommendations = []
        
        for model in related[:limit]:
            rec = {
                "model_id": model["model_id"],
                "name": model["name"],
                "creator": model["creator_name"],
                "reason": f"Related to {recent.get('model_name')}",
                "match_reasons": model.get("match_reasons", []),
                "success_rate": self.stats.get(model["model_id"], {}).get("success_rate", 0),
                "avg_print_time": self.stats.get(model["model_id"], {}).get("avg_print_time", 0),
            }
            recommendations.append(rec)
        
        return recommendations
    
    def recommend_by_popularity(self, limit: int = 5) -> list[dict]:
        """Recommend trending/popular models."""
        popular = []
        
        for model_id, stats in self.stats.items():
            rec = {
                "model_id": model_id,
                "name": self.models[model_id].name if model_id in self.models else "Unknown",
                "reason": "Trending",
                "total_prints": stats.get("total_prints", 0),
                "success_rate": stats.get("success_rate", 0),
                "popularity_score": stats.get("total_prints", 0) * stats.get("success_rate", 0.5),
            }
            popular.append(rec)
        
        popular.sort(key=lambda x: x["popularity_score"], reverse=True)
        return popular[:limit]
    
    def recommend_by_difficulty_match(self, model_ref: str, limit: int = 5) -> list[dict]:
        """Recommend models at the same difficulty level."""
        base_model = self.models.get(model_ref)
        if not base_model:
            return []
        
        base_difficulty = base_model.enrichment.get("difficulty_level", "intermediate")
        
        matches = [
            m for m in self.models.values()
            if m.model_id != model_ref
            and m.enrichment.get("difficulty_level") == base_difficulty
        ]
        
        recommendations = [
            {
                "model_id": m.model_id,
                "name": m.name,
                "difficulty": base_difficulty,
                "reason": f"{base_difficulty.capitalize()} difficulty match",
                "success_rate": self.stats.get(m.model_id, {}).get("success_rate", 0),
            }
            for m in matches[:limit]
        ]
        
        return recommendations
```

**REST Command:** `homeassistant/packages/3d_printing/model_catalog/rest_commands.yaml`

```yaml
model_catalog_get_recommendations:
  url: "http://localhost:8090/api/recommendations"
  method: GET
  params:
    strategy: "{{ strategy | default('next_steps') }}"
    limit: "{{ limit | default(5) }}"
```

**Tests:** [tests/phase3/test_phase3_3_cross_system.py::TestRecommendationEngine](../../../../tests/phase3/test_phase3_3_cross_system.py#L95)

### Task 4: Print Statistics Aggregation (Days 4-5)

**Endpoint:** `GET /api/models/{model_ref}/print-stats`

**Implementation:** `sidecars/model_catalog/app/statistics.py` (new)

```python
class PrintStatistics:
    """Aggregate print statistics per model."""
    
    @staticmethod
    def aggregate_for_model(model_ref: str, archives: list[dict]) -> dict[str, Any]:
        """
        Aggregate print statistics across all archives of a model.
        Returns: total_prints, successful_prints, success_rate, avg/min/max times, 
                 filament used, failure reasons
        """
        model_archives = [a for a in archives if a.get("model_ref") == model_ref]
        
        if not model_archives:
            return {
                "model_ref": model_ref,
                "total_prints": 0,
                "successful_prints": 0,
                "success_rate": 0.0,
                "avg_print_time_seconds": 0,
                "min_print_time_seconds": 0,
                "max_print_time_seconds": 0,
                "total_filament_grams": 0,
                "avg_filament_per_print_grams": 0,
            }
        
        successful = [a for a in model_archives if a.get("success")]
        print_times = [a.get("print_time_seconds", 0) for a in successful]
        
        return {
            "model_ref": model_ref,
            "total_prints": len(model_archives),
            "successful_prints": len(successful),
            "success_rate": len(successful) / len(model_archives),
            "failure_rate": (len(model_archives) - len(successful)) / len(model_archives),
            "avg_print_time_seconds": sum(print_times) / len(print_times) if print_times else 0,
            "min_print_time_seconds": min(print_times) if print_times else 0,
            "max_print_time_seconds": max(print_times) if print_times else 0,
            "total_filament_grams": sum(a.get("filament_weight_grams", 0) for a in model_archives),
            "avg_filament_per_print_grams": sum(a.get("filament_weight_grams", 0) for a in model_archives) / len(model_archives) if model_archives else 0,
            "filament_by_color": aggregate_filament_by_color(model_archives),
            "failure_reasons": aggregate_failure_reasons(model_archives),
        }
    
    @staticmethod
    def get_filament_usage_by_color(model_ref: str, archives: list[dict]) -> dict[str, dict]:
        """Summarize filament usage by color."""
        model_archives = [a for a in archives if a.get("model_ref") == model_ref]
        usage = {}
        
        for archive in model_archives:
            color = archive.get("filament_color", "unknown").lower()
            weight = archive.get("filament_weight_grams", 0)
            
            if color not in usage:
                usage[color] = {
                    "color": color,
                    "total_weight_grams": 0,
                    "total_prints": 0,
                    "successful_prints": 0,
                }
            
            usage[color]["total_weight_grams"] += weight
            usage[color]["total_prints"] += 1
            if archive.get("success"):
                usage[color]["successful_prints"] += 1
        
        return usage
```

**Tests:** [tests/phase3/test_phase3_3_cross_system.py::TestPrintStatistics](../../../../tests/phase3/test_phase3_3_cross_system.py#L131)

### Task 5: Export Functionality (Days 5-6)

**Endpoints:** 
- `GET /api/catalog/export?format=json&collection=Miniatures`
- `GET /api/catalog/export?format=csv`

**Implementation:** `sidecars/model_catalog/app/export.py` (new)

```python
class CatalogExporter:
    """Export catalog in various formats."""
    
    @staticmethod
    def export_json(models: list[dict], include_enrichment: bool = True, 
                   filters: dict = None) -> str:
        """Export catalog as JSON."""
        export_data = []
        
        for model in models:
            if filters and not matches_filters(model, filters):
                continue
            
            export_model = {
                "model_id": model["model_id"],
                "public_id": model["public_id"],
                "name": model["name"],
                "description": model.get("description"),
                "creator_name": model.get("creator_name"),
                "collections": model.get("collection_names", []),
                "keywords": model.get("keyword_names", []),
                "preview_url": model.get("preview_url"),
                "files": model.get("files", []),
            }
            
            if include_enrichment:
                export_model["enrichment"] = model.get("enrichment", {})
            
            export_data.append(export_model)
        
        return json.dumps(export_data, indent=2)
    
    @staticmethod
    def export_csv(models: list[dict], filters: dict = None) -> str:
        """Export catalog as CSV."""
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "model_id", "public_id", "name", "creator", "collections", 
                "keywords", "difficulty", "print_time_est", "success_rate"
            ]
        )
        
        writer.writeheader()
        
        for model in models:
            if filters and not matches_filters(model, filters):
                continue
            
            writer.writerow({
                "model_id": model["model_id"],
                "public_id": model["public_id"],
                "name": model["name"],
                "creator": model.get("creator_name", ""),
                "collections": "; ".join(model.get("collection_names", [])),
                "keywords": "; ".join(model.get("keyword_names", [])),
                "difficulty": model.get("enrichment", {}).get("difficulty_level", ""),
                "print_time_est": model.get("enrichment", {}).get("print_time_estimate", ""),
                "success_rate": "",  # Would come from statistics
            })
        
        return output.getvalue()
```

**REST Command:**

```yaml
model_catalog_export_json:
  url: "http://localhost:8090/api/catalog/export"
  method: GET
  params:
    format: "json"
    include_enrichment: "true"

model_catalog_export_csv:
  url: "http://localhost:8090/api/catalog/export"
  method: GET
  params:
    format: "csv"
```

**Tests:** [tests/phase3/test_phase3_3_cross_system.py::TestExportFunctionality](../../../../tests/phase3/test_phase3_3_cross_system.py#L170)

### Task 6: Integration with Print History (Days 6-7)

**File:** `homeassistant/packages/3d_printing/print_history/scripts/archive_link_model.yaml`

**Script to Link Archive to Model:**

```yaml
archive_link_model:
  alias: Link Archive to Model
  description: |
    Associate an archive with its source model from the catalog.
    Called when print completes.
  fields:
    archive_id:
      name: Archive ID
      description: ID of the print archive
      required: true
    model_ref:
      name: Model Reference
      description: Model reference to link (if already known)
  sequence:
    - if: "{{ model_ref is undefined }}"
      then:
        # Query sidecar to find model
        - service: rest_command.model_catalog_get_archive_model
          data:
            archive_id: "{{ archive_id }}"
          response_variable: link_result
        - set_fact:
            linked_model_ref: "{{ link_result.model_ref }}"
      else:
        - set_fact:
            linked_model_ref: "{{ model_ref }}"
    
    # Store link in local database
    - service: rest_command.model_catalog_create_link
      data:
        archive_id: "{{ archive_id }}"
        model_ref: "{{ linked_model_ref }}"
    
    # Trigger update event for UI refresh
    - event: model_catalog_archive_linked
      event_data:
        archive_id: "{{ archive_id }}"
        model_ref: "{{ linked_model_ref }}"
```

**Automation to Trigger on Print Complete:**

```yaml
# automations/link_archive_on_print_complete.yaml
alias: Link Archive on Print Complete
description: |
  When a print completes, link the archive to its source model
triggers:
  - platform: state
    entity_id: sensor.print_history_last_archive
    to: "completed"
conditions: []
actions:
  - service: script.archive_link_model
    data:
      archive_id: "{{ trigger.to_state.attributes.archive_id }}"
mode: parallel
```

**Tests:** [tests/phase3/test_phase3_3_cross_system.py::TestAPIIntegration](../../../../tests/phase3/test_phase3_3_cross_system.py#L258)

### Task 7: Dashboard Card Updates (Days 6-7)

**Card: Model Statistics**

```javascript
// homeassistant/www/3d_printing/model_catalog/model-statistics-card.js
class ModelStatisticsCard extends HTMLElement {
  setConfig(config) {
    this.config = config;
  }
  
  async connectedCallback() {
    const model_ref = this.config.model_ref;
    
    // Fetch stats endpoint
    const response = await fetch(
      `https://model-catalog.socko.us/api/models/${model_ref}/print-stats`
    );
    const stats = await response.json();
    
    // Render statistics table
    const html = `
      <ha-card>
        <div class="card-content">
          <div class="stat-item">
            <span>Total Prints:</span>
            <strong>${stats.total_prints}</strong>
          </div>
          <div class="stat-item">
            <span>Success Rate:</span>
            <strong>${(stats.success_rate * 100).toFixed(1)}%</strong>
          </div>
          <div class="stat-item">
            <span>Avg Print Time:</span>
            <strong>${format_duration(stats.avg_print_time_seconds)}</strong>
          </div>
          <div class="stat-item">
            <span>Filament Used:</span>
            <strong>${stats.total_filament_grams.toFixed(1)}g</strong>
          </div>
        </div>
      </ha-card>
    `;
    
    this.innerHTML = html;
  }
}

customElements.define('model-statistics-card', ModelStatisticsCard);
```

**Tests:** Done (integration tests cover dashboard integration)

## Testing Strategy

### Unit Tests
```bash
pytest tests/phase3/test_phase3_3_cross_system.py -v
```

### Integration Tests
1. Test archive-to-model linking:
   - Complete a print
   - Verify archive linked to correct model
   - Check recommendation updates

2. Test recommendations:
   - Recent prints should show related models
   - Popular models ranked correctly
   - Difficulty matching works

3. Test statistics:
   - Multiple prints of same model
   - Verify aggregation (success rate, times, filament)
   - Check filament breakdown by color

4. Test export:
   - Export as JSON
   - Export as CSV
   - Verify filters work

## Success Criteria

- [ ] GET /api/archives/{archive_id}/model endpoint returns correct model
- [ ] Archive-to-model linking works (exact + fuzzy matching)
- [ ] Related models algorithm produces reasonable recommendations
- [ ] Recommendation engine strategies (next-steps, popularity, difficulty) work
- [ ] Print statistics properly aggregated and returned
- [ ] Export to JSON and CSV functional
- [ ] All 35 test methods in test_phase3_3_cross_system.py pass
- [ ] Archive linking automation triggers on print complete
- [ ] Model statistics displayed in dashboard
- [ ] Recommendations shown in model detail/print_history views

## Files Created/Modified

### New Files
- `sidecars/model_catalog/app/recommendations.py` (Recommendation engine)
- `sidecars/model_catalog/app/statistics.py` (Statistics aggregation)
- `sidecars/model_catalog/app/export.py` (Catalog export)
- `homeassistant/packages/3d_printing/model_catalog/scripts/archive_link_model.yaml`
- `homeassistant/packages/3d_printing/model_catalog/automations/link_archive_on_print_complete.yaml`
- `homeassistant/www/3d_printing/model_catalog/model-statistics-card.js`

### Modified Files
- `sidecars/model_catalog/app/main.py` (Add endpoints)
- `homeassistant/packages/3d_printing/model_catalog/rest_commands.yaml` (Add commands)
- `homeassistant/packages/3d_printing/print_history/automations.yaml` (Add trigger)

### Test Files
- Existing: [tests/phase3/test_phase3_3_cross_system.py](../../../../tests/phase3/test_phase3_3_cross_system.py) (360 lines, 35 tests)

## Timeline

| Day | Task | Owner |
|-----|------|-------|
| 1-2 | Archive-to-model linking | Backend |
| 2-3 | Related models algorithm | Backend |
| 3-4 | Recommendation engine | Backend |
| 4-5 | Statistics aggregation | Backend |
| 5-6 | Export functionality | Backend |
| 6-7 | HA integration + dashboard card | Integration |

## Sign-Off

**Plan Created:** April 25, 2026  
**Next Review:** May 3, 2026 (Kickoff)  
**Completion Target:** May 10, 2026

---

## Post-Phase 3 Roadmap (Future)

After Phase 3 completion, consider:
- Phase 4: Statistics Dashboard (trending models, failure analysis)
- Phase 5: Advanced filters (by difficulty, creator, material)
- Phase 6: Model versioning (track model changes over time)
- Phase 7: Community sharing (export/import model recommendations)
