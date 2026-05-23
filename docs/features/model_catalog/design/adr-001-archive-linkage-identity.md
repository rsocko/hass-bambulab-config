# ADR-001: Archive Linkage Target & Graduation-Stable Identity

> Status: **Accepted**  
> Proposed: 2026-05-18  
> Accepted: 2026-05-18  
> Resolves: #1314, #1375  
> Scope: Local catalog ONLY — no external service dependency

---

## Context

The `model_catalog_links` table connects Bambuddy print-history archives to source models in the **local model catalog**. Two open design questions block all downstream implementation:

1. **#1314 — Linkage target granularity**: Should a link point to a *model record* (e.g., "Gridfinity Box"), a *specific asset file within that model* (e.g., `gridfinity-box-4x2.3mf`), or both?

2. **#1375 — Graduation stability**: When a Working File "graduates" to a Catalog model (or vice versa), does the existing linkage break, and how do we prevent that?

### Architectural Constraint

The model catalog operates as a **self-contained local system**. All model identity, storage, and linking is managed by the local SQLite-backed catalog sidecar. There is no runtime dependency on any external model hosting service. The link table columns retain legacy `manyfold_*` prefixes from a prior integration era, but semantically they map to local-only concepts:

| Legacy Column Name | Actual Semantic Role |
|-------------------|---------------------|
| `manyfold_model_url` | **Model URL** — stores `local://model/{local_model_id}` |
| `manyfold_model_public_id` | **Model public ID** — stores `local_model_id` |
| `manyfold_model_file_id` | **Asset ID** — stores `model_catalog_assets.asset_id` |

> **Note**: Column renames are deferred to a future schema-cleanup migration. This ADR operates on the semantic meaning, not the legacy column names.

### Current State

| Aspect | State |
|--------|-------|
| Model URL column | Always populated; stores `local://model/{local_model_id}` |
| Asset ID column | Column exists but is **never populated by automated discovery** — only via manual input |
| Local models | `model_catalog_entries` table, identified by `local_model_id` (UUID) |
| Model assets | `model_catalog_assets` table, each with `asset_id` (unique per model entry), `file_hash`, `storage_path` |
| Working groups | Separate system (`working_group_model_links.model_ref`) — can now also be archive link targets via `local://working-group/{id}` |
| Graduation | Creates a `model_catalog_entries` record with a new `local_model_id`; MUST rewrite any `local://working-group/` links |

### Why This Matters Now

- Candidate discovery (#1114, #1118) is in progress and needs to know whether to resolve matches to model-level or asset-level
- The slicer pipeline (#1182→#1186) will create new archives from a *specific .3mf file* — if the link only stores model-level, we lose provenance
- Tag sync (#1473) and image sync (#1474) depend on knowing whether metadata flows at model or asset level
- The Historical Print Wizard (#1483) will create links backward — stable identity prevents orphaning

---

## Decision 1: Linkage Target — Dual-Level (Model + Optional Asset)

### Proposal

Support **both** model-level and asset-level linkage in every link row, with asset-level as the preferred specificity when known:

```
model_url   (column: manyfold_model_url)     → always set; local://model/{local_model_id}
asset_id    (column: manyfold_model_file_id)  → set when the specific source asset is known
```

The link always identifies the parent model. When the specific .3mf (or other source file) is known, its `asset_id` from `model_catalog_assets` is also stored.

### Rules

| Scenario | Model URL | Asset ID | `relationship_type` |
|----------|-----------|----------|---------------------|
| Archive matched to a catalog model by name/time heuristic | ✅ `local://model/{id}` | ❌ null | `model_printed_in_archive` |
| Archive matched to a specific .3mf by hash | ✅ `local://model/{id}` | ✅ asset_id | `model_file_printed_in_archive` |
| Archive matched to a working group by name/file heuristic | ✅ `local://working-group/{id}` | ❌ null | `model_printed_in_archive` |
| Slicer creates archive from known source file | ✅ `local://model/{id}` | ✅ asset_id | `model_file_printed_in_archive` |
| Operator manually links to model (no file picked) | ✅ `local://model/{id}` | ❌ null | `model_printed_in_archive` |
| Operator manually links to working group | ✅ `local://working-group/{id}` | ❌ null | `model_printed_in_archive` |
| Operator manually links to specific asset via picker | ✅ `local://model/{id}` | ✅ asset_id | `model_file_printed_in_archive` |

### Relationship Type Convention

Existing candidate-refresh code uses `printed_from` as the default `relationship_type`. Going forward, new and updated links SHOULD use the values defined in this ADR:

| Value | Meaning |
|-------|--------|
| `model_printed_in_archive` | Link targets the model (asset ID is null) |
| `model_file_printed_in_archive` | Link targets a specific asset within the model |

Existing `printed_from` rows are treated as equivalent to `model_printed_in_archive` (model-level, no asset specificity). A one-time repair pass MAY normalize legacy values, but consumers SHOULD accept both forms.

### Behavior

- **Display**: When asset ID is set, UIs resolve the filename from `model_catalog_assets` and show it alongside the model name (e.g., "Gridfinity Box → `box-4x2.3mf`")
- **Navigation**: "Open in catalog" navigates to the model detail; asset-level specificity optionally highlights/scrolls to the asset
- **Candidate scoring**: Asset-level matches (`content_hash_exact`, `file_hash_exact` resolved against `model_catalog_assets.file_hash`) produce `match_confidence=high` and may auto-accept; model-level matches remain `review_only` unless deterministic
- **Upgradability**: A model-level link can be **narrowed** to asset-level later (e.g., when the operator selects the specific file in a review flow) — this is an update, not a new link
- **Asset deletion**: If an asset is removed from the catalog, the link retains the `asset_id` as a historical reference but asset-level display degrades to model-level with a "file removed" indicator

### Schema Impact

**None** — the asset ID column already exists (`manyfold_model_file_id TEXT`). The change is behavioral:
- Automated candidate discovery SHOULD populate the asset ID column when a deterministic file-hash match is found against `model_catalog_assets.file_hash`
- The slicer commit path (#1454) MUST populate it since it knows the exact source asset
- The candidate refresh scorer SHOULD attempt asset-level resolution before falling back to model-level

### How Asset Matching Works (Local Catalog)

```
Archive source_hash  →  match against model_catalog_assets.file_hash
                         ↓ (hit)
                     asset_id → model_catalog_entry_id → local_model_id
                         ↓
                     Link row: model_url = local://model/{local_model_id}
                               asset_id  = model_catalog_assets.asset_id
```

### Trade-offs

| Pro | Con |
|-----|-----|
| Preserves full provenance chain from source → sliced → printed | Slightly more complex candidate display (two lines vs one) |
| Enables per-asset print statistics (e.g., "this plate was printed 3 times") | Asset-level matching requires catalog assets to have `file_hash` populated |
| Aligns with the already-shipped schema column | Heuristic (name) matches will typically only resolve to model-level |
| No migration needed | — |
| Entirely self-contained — no external service calls | — |

---

## Decision 2: Graduation-Stable Identity Scheme

### Problem

A model's lifecycle in the local catalog follows this path:

```
Working File (folder scan)  →  Working Group (tracked/staged)  →  Local Catalog Model (permanent)
```

At each stage, the model's identity changes:
- Working File: path-based (`source_path_compare_key`)
- Working Group: `local://working-group/{id}` (integer PK, stable until graduation)
- Local Catalog Model: `local://model/{local_model_id}` (UUID, permanent)

The local catalog model identity (`local_model_id`) is the **terminal stable identity**. Working group identity (`local://working-group/{id}`) is stable within its lifecycle, but upon graduation it is rewritten to the catalog form. Both forms are valid link targets; graduation guarantees convergence.

### Proposal: Two Identity Forms with Graduation Migration

The model URL column in `model_catalog_links` accepts two identity forms:

| Identity Form | Applies To | Stability |
|---------------|------------|----------|
| `local://model/{local_model_id}` | Catalog models | Permanent (UUID-based) |
| `local://working-group/{id}` | Working groups | Stable until graduation, then rewritten |

Working groups use their `id` (integer primary key) — NOT the mutable `slug` — as the stable component of the synthetic URL.

Candidate discovery SHOULD search both catalog models and working groups when scoring archive matches. This reflects the real-world workflow: many prints happen from WIP models before they are curated into the catalog.

### Graduation Migration (Mandatory)

When a working group is published to the local catalog (via `publish_working_group_to_local_service`), the graduation logic MUST:

1. **Query** `model_catalog_links` for rows where `manyfold_model_url = 'local://working-group/{group_id}'`
2. **Rewrite** those rows' model URL to `local://model/{new_local_model_id}`
3. **Log** the rewrite as a `model_catalog_events` entry with `event_type=link_url_migrated`

The graduation function already records `source_origin_url=f"working-group://{group_id}"` and stores `published_from_group_id`, so the old→new mapping is always known.

### Identity Stability Contract

| Guarantee | Mechanism |
|-----------|-----------|
| Links survive Working → Catalog graduation | URL rewrite during `publish_working_group_to_local_service` |
| Links survive model rename | URL is UUID-based, not name-based — no change needed |
| Links survive asset rename within model | `asset_id` is UUID-based, not filename-based — no change needed |
| Links survive model re-categorization (tags/collections) | Identity is not derived from metadata — no change needed |
| Links survive Catalog → Working demotion | Reverse URL rewrite (preserve the original `local_model_id` in a memo field) |
| WG links are never orphaned by graduation | Mandatory rewrite step in graduation path |

### Display Behavior for WG Links

When a link's model URL is `local://working-group/{id}`, UIs SHOULD:
- Resolve the working group title from `working_groups` and display it with a "Working Files" badge
- Navigate to the working group detail view (not the catalog model view)
- After graduation, the link URL becomes `local://model/...` and normal catalog display applies

### Schema Impact

**No new columns needed.** The `manyfold_model_url TEXT` column already accepts any string. The existing `canonical_model_url_repair` function already handles URL rewrites. We extend this pattern:

- Add a `migrate_links_for_graduation(group_id: int, new_local_model_id: str)` helper to `db_archive_links.py`
- Call it from the graduation service
- Log via the existing `model_catalog_events` table

### Trade-offs

| Pro | Con |
|-----|-----|
| Archives can be linked to WIP models immediately — matches real workflow | Two identity forms in the URL column (mitigated by graduation rewrite) |
| Graduation automatically migrates links — no orphans | Candidate discovery must search both tables (~5 LOC) |
| Existing `canonical_model_url_repair` pattern proves the migration is safe | Display must handle WG badge (minor UI addition) |
| WG `id` (integer PK) is genuinely stable — not slug-dependent | — |
| Event log preserves audit trail of migrations | — |
| Zero external dependencies — fully local | — |

---

## Implementation Checklist

### Tier 0 — Design Acceptance (this ADR)

- [x] **Accept this ADR** — no schema migration required; behavioral only

### Tier 1 — Discovery Engine (implement alongside #1114 / #1118)

- [x] Update `candidate-discovery-strategy.md` to note that asset-level resolution is preferred when a hash match is found against `model_catalog_assets.file_hash`
- [x] Add `migrate_links_for_graduation(group_id, new_local_model_id)` to `db_archive_links.py`
- [x] Wire the migration call into `publish_working_group_to_local_service` (after model creation, before response)
- [x] Extend candidate discovery to search `working_groups` + `working_items` in addition to `model_catalog_entries` + `model_catalog_assets`
- [x] Ensure candidate refresh scorer populates the asset ID column when `file_hash_exact` or `content_hash_exact` is the match method
- [x] Normalize `relationship_type` values in new link creation to use `model_printed_in_archive` / `model_file_printed_in_archive`

### Tier 5 — Slicer Integration

- [ ] Slicer commit path (#1454) MUST pass the asset ID for the source .3mf asset used
- [ ] Archive detail popup shows asset-level specificity when present (resolves filename from `model_catalog_assets`)

### Validation

- [ ] Create a local catalog model with multiple .3mf assets (each with `file_hash` populated)
- [ ] Run candidate discovery against an archive whose `source_hash` matches one asset — verify asset ID is populated
- [ ] Link an archive to the model (model-level only) — verify display
- [ ] Narrow the link to a specific asset — verify display shows filename
- [ ] Link an archive to a working group — verify `local://working-group/{id}` URL stored and display shows "Working Files" badge
- [ ] Graduate that working group — verify links rewrite to `local://model/{new_uuid}` and display switches to catalog model view
- [ ] Confirm `canonical_model_url_repair` after graduation leaves no orphaned links
- [ ] Verify candidate discovery returns working group matches alongside catalog model matches

---

## Alternatives Considered

### A: Asset-Only Linkage (always require asset specificity)

Rejected because:
- Most heuristic matches (name overlap, time proximity) can only resolve to model-level
- Forcing asset resolution would make >60% of links impossible to create automatically
- Operators often don't care which specific .3mf was used for older prints

### B: Separate Link Table for Asset-Level

Rejected because:
- The asset ID column already exists and is optional/nullable
- A separate table introduces join complexity for a single nullable field
- The design anticipated this as a single-row dual-target pattern

### C: Prohibit Linkage to Working Groups Entirely

Considered but rejected in favor of the current approach because:
- Many prints happen from WIP models before graduation — prohibiting WG linkage creates a gap in provenance
- Working groups have a stable integer PK (`id`); the slug mutability concern is moot for the synthetic URL `local://working-group/{id}`
- The graduation migration (mandatory URL rewrite) ensures WG links converge to the single `local://model/{uuid}` form — the second identity form is transient, not permanent

### D: Content-Addressable Identity (hash-only, no URL)

Rejected because:
- Not all models have hashes (e.g., models with only STL/image assets, no .3mf source)
- Hash collisions across revisions of the same model would break uniqueness
- UUID-based identity is already proven and deployed
- Hashes are still used as a *matching signal* — they just don't replace the stable UUID as the link key

### E: External Service Dependency (Manyfold or similar)

Rejected because:
- Adds runtime dependency on an external service for a core feature (print-history provenance)
- Network latency and availability affect link resolution
- Identity managed by an external system can change without local notification
- The local catalog is the single source of truth — external sync can be a *supplemental* feature later but must not be in the critical path

---

## References

- [Candidate Discovery Strategy](/docs/features/model_catalog/planning/candidate-discovery.md) — signal tiers and match methods
- [Archive-Model Link HA Service Contract](/docs/features/model_catalog/reference/integration/archive-model-link-contract.md) — API surface
- [Implementation Sequence](/docs/features/model_catalog/planning/archive-linking-sequence.md) — execution plan
