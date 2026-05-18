# ADR-001: Archive Linkage Target & Graduation-Stable Identity

> Status: **Proposed** — awaiting review  
> Date: 2026-05-18  
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
| Working groups | Separate system (`working_group_model_links.model_ref`) — not propagated during graduation |
| Graduation | Creates a `model_catalog_entries` record with a new `local_model_id`; does NOT transfer existing links |

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
| Archive matched to a model by name/time heuristic | ✅ `local://model/{id}` | ❌ null | `model_printed_in_archive` |
| Archive matched to a specific .3mf by hash | ✅ `local://model/{id}` | ✅ asset_id | `model_file_printed_in_archive` |
| Slicer creates archive from known source file | ✅ `local://model/{id}` | ✅ asset_id | `model_file_printed_in_archive` |
| Operator manually links to model (no file picked) | ✅ `local://model/{id}` | ❌ null | `model_printed_in_archive` |
| Operator manually links to specific asset via picker | ✅ `local://model/{id}` | ✅ asset_id | `model_file_printed_in_archive` |

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
- Working Group: `working_groups.id` + `slug`
- Local Catalog Model: `local://model/{local_model_id}` (UUID, stable)

The local catalog model identity (`local_model_id`) is the **terminal stable identity**. Once a model reaches this stage, its ID never changes regardless of renames, re-categorization, or tag edits.

If an archive were linked to a Working Group identity and that group graduates to a catalog model, the link would become orphaned unless we explicitly handle the transition.

### Proposal: Graduation Writes a Link Migration

When a working group is published to the local catalog (via `publish_working_group_to_local_service`), the graduation logic MUST:

1. **Query** `model_catalog_links` for any rows where the model URL column matches a working-group-derived synthetic URL (if one exists) or where the public ID column matches the working group slug
2. **Rewrite** those rows' model URL to the new `local://model/{local_model_id}`
3. **Log** the rewrite as a `model_catalog_events` entry with `event_type=link_url_migrated`

### Identity Stability Contract

| Guarantee | Mechanism |
|-----------|-----------|
| Links survive Working → Catalog graduation | URL rewrite during `publish_working_group_to_local_service` |
| Links survive model rename | URL is UUID-based, not name-based — no change needed |
| Links survive asset rename within model | `asset_id` is UUID-based, not filename-based — no change needed |
| Links survive model re-categorization (tags/collections) | Identity is not derived from metadata — no change needed |
| Links survive Catalog → Working demotion | Reverse URL rewrite (preserve the original `local_model_id` in a memo field) |

### Pre-Condition: Working Groups Don't Have Archive Links Today

Currently, the model URL column in `model_catalog_links` only contains `local://model/{id}` URLs. Working groups are managed via the separate `working_group_model_links` table, which is a different system and does NOT flow into `model_catalog_links`.

**Design choice**: We will NOT introduce archive-linking for working groups directly. Instead:
- A working group must graduate to a local catalog model before it can be an archive link target
- This keeps the identity space to exactly ONE form: `local://model/{local_model_id}`
- The graduation step is lightweight; the catalog model is the stable anchor

### Schema Impact

**No new columns needed.** The existing `canonical_model_url_repair` function already handles URL rewrites. We extend this pattern:

- Add a `migrate_links_for_graduation(old_url: str, new_local_model_id: str)` helper to `db_archive_links.py`
- Call it from the graduation service
- Log via the existing `model_catalog_events` table

### Trade-offs

| Pro | Con |
|-----|-----|
| Single identity form (`local://model/{uuid}`) — minimal ambiguity | Graduation must be URL-aware (small code addition) |
| Only catalog-level models can be link targets — reduces ambiguity | Working groups cannot be linked until graduated (acceptable — they are WIP) |
| Existing `canonical_model_url_repair` pattern proves the migration is safe | If graduation is skipped (direct file use), no link exists until manual creation |
| Event log preserves audit trail of migrations | Adds ~10 LOC to the graduation path |
| Zero external dependencies — fully local | — |

---

## Implementation Checklist

### Immediate (unblocks Tier 1+)

- [ ] **Accept this ADR** — no schema migration required; behavioral only
- [ ] Update `candidate-discovery-strategy.md` to note that asset-level resolution is preferred when a hash match is found against `model_catalog_assets.file_hash`
- [ ] Add `migrate_links_for_graduation(old_url, new_local_model_id)` to `db_archive_links.py`
- [ ] Wire the migration call into `publish_working_group_to_local_service`
- [ ] Ensure candidate refresh scorer populates the asset ID column when `file_hash_exact` or `content_hash_exact` is the match method

### Later (Tier 5 / Slicer)

- [ ] Slicer commit path (#1454) MUST pass the asset ID for the source .3mf asset used
- [ ] Archive detail popup shows asset-level specificity when present (resolves filename from `model_catalog_assets`)

### Validation

- [ ] Create a local catalog model with multiple .3mf assets (each with `file_hash` populated)
- [ ] Run candidate discovery against an archive whose `source_hash` matches one asset — verify asset ID is populated
- [ ] Link an archive to the model (model-level only) — verify display
- [ ] Narrow the link to a specific asset — verify display shows filename
- [ ] Graduate a working group that has existing links — verify links survive with new `local://model/` URL
- [ ] Confirm `canonical_model_url_repair` after graduation leaves no orphaned links

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

### C: Indirect Linkage Through Working Groups

Rejected because:
- Working groups are transient by design (WIP staging area)
- Their identity is slug-based and mutable
- Adding them as link targets would introduce a second identity form in the link table

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

- [Candidate Discovery Strategy](candidate-discovery-strategy.md) — signal tiers and match methods
- [Archive-Model Link HA Service Contract](integration/archive-model-link-ha-service-and-popup-contract.md) — API surface
- [Implementation Sequence](ARCHIVE-LINKING-IMPLEMENTATION-SEQUENCE.md) — execution plan
