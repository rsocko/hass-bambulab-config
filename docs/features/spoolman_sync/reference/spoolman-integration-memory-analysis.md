# Spoolman HA Integration — Memory & Performance Analysis

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: spoolman_sync
Replaces: docs/features/spoolman_sync/spoolman-integration-memory-analysis.md
Replaced By: none


> **Integration:** [`Disane87/spoolman-homeassistant`](https://github.com/Disane87/spoolman-homeassistant)  
> **Analysis date:** 2026-03-26  
> **Source reviewed:** `main` branch — `coordinator.py`, `sensor.py`, `sensors/spool.py`, `__init__.py`, `spoolman_api.py`, `const.py`  
> **Test environment:** Raspberry Pi 5 (aarch64), HAOS, 162 spools → 5,014+ sensor entities

---

## Summary

The Spoolman HA integration creates an extreme number of entities per spool (~31 each), duplicates the full spool data structure in every entity, generates PIL images synchronously during setup, and runs cleanup scans on every coordinator update. On a Raspberry Pi with a moderate-to-large spool collection, this creates significant memory pressure. Calling `homeassistant.reload_config_entry` triggers a full teardown and rebuild of all entities/images, which can OOM-kill the system.

---

## Hotspot 1 — Entity Explosion (~31 entities per spool)

**File:** `sensor.py` — `_setup_spool_entities()`

Each spool registered in Spoolman creates the following sensor entities:

| # | Entity | Notes |
|---|--------|-------|
| 1 | Spool (main) | Primary entity with `extra_state_attributes` |
| 2 | FlowRate | |
| 3 | EstimatedRunOut | |
| 4 | UsedWeight | |
| 5 | RemainingLength | |
| 6 | UsedLength | |
| 7 | Location | |
| 8 | UsedPercentage | |
| 9 | Registered | |
| 10 | FirstUsed | |
| 11 | LastUsed | |
| 12 | Price | |
| 13 | SpoolWeight | |
| 14 | LotNumber | |
| 15 | Comment | |
| 16 | FilamentDensity | |
| 17 | FilamentDiameter | |
| 18 | ExtruderTemp | |
| 19 | BedTemp | |
| 20 | ArticleNumber | |
| 21 | FilamentName | |
| 22 | FilamentMaterial | |
| 23 | FilamentColorHex | |
| 24 | VendorName | |
| 25 | FilamentWeight | |
| 26+ | One sensor per `extra` field | Variable count |

Each entity is individually registered in the entity registry, device registry, and state machine.

**Impact:** 162 spools × ~31 entities = **5,014+ entities** in the author's instance. Each entity has its own state object, event listeners, and registry entries.

**Recommendation:** Most per-spool sensors should be **diagnostic entities** (disabled by default via `entity_registry_enabled_default = False`). Users who need `FilamentDensity` or `LotNumber` as standalone sensors can enable them. This would cut the active entity count by 70–80% with no loss of functionality.

---

## Hotspot 2 — Full Data Duplication Per Entity

**File:** `sensors/spool.py`

Every spool entity class stores `self._spool` — the **complete spool dict including the nested filament dict**. With 5,014 entities that all store the same base spool data (just reading different fields), this results in massive redundant memory usage.

Additionally, the `extra_state_attributes` property calls `flatten_dict(self._spool)` which **recursively walks the entire spool + filament dict every time HA reads any attribute** from any spool entity. This runs on every state report cycle.

```python
# Current pattern (per entity):
class SpoolSensor:
    def __init__(self, spool):
        self._spool = spool  # Full spool dict with nested filament

    @property
    def extra_state_attributes(self):
        return flatten_dict(self._spool)  # Recursive walk on every read
```

**Impact:** N entities × full spool dict size. For 162 spools with 31 entities each, that's 5,014 copies of increasingly large dicts. The `flatten_dict` call adds CPU overhead on every HA state read.

**Recommendation:**
- Store spool data **once** in the coordinator's `data` dict. Entities should hold only a spool ID and reference `self.coordinator.data[spool_id]`.
- Cache the `flatten_dict` result once per coordinator update cycle, not per-entity per-read.

---

## Hotspot 3 — PIL Image Generation at Setup

**File:** `sensor.py` — `_generate_entity_picture()`

During `async_setup_entry`, the integration creates a **PIL `Image.new()`** + `ImageDraw` object for every spool AND every filament. It draws a colored circle, converts to PNG bytes via `BytesIO`, and writes to disk at `www/spoolman_images/`.

```python
# Runs for EVERY spool + filament during setup:
img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)
draw.ellipse([10, 10, 90, 90], fill=color)
# ... save to disk
```

**Impact:** For 162 spools + their filaments, this is 200+ PIL image allocations executed synchronously during a single `async_setup_entry` call. On a Pi with limited RAM, this creates a significant memory spike at startup and reload.

**Recommendation:**
- **Lazy generation:** Only create images on first access, or via a background task after setup completes.
- **Cache check:** Skip regeneration if the file already exists on disk and the color hasn't changed.
- **Eliminate PIL entirely:** Use inline SVG data URIs for the entity picture. A colored circle is trivially representable as: `data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='40' fill='%23RRGGBB'/></svg>`. Zero disk I/O, zero PIL dependency for this use case.

---

## Hotspot 4 — Coordinator Fetches ALL Data Every Update

**File:** `coordinator.py` — `_async_update_data()`

Every coordinator update interval fetches **all spools** and **all filaments** from the Spoolman API, parses the full JSON response, and **replaces the entire data dict**. There is no incremental or delta update mechanism.

Each spool's `extra` field values are also individually processed through `json.loads()` during parsing.

**Impact:** On every update cycle, the integration:
1. Makes 2 HTTP requests (all spools + all filaments)
2. Parses two full JSON arrays
3. Runs `json.loads()` on every extra field of every spool
4. Replaces the full coordinator data dict (triggering entity updates for everything)

**Recommendation:**
- Use the **Spoolman WebSocket** endpoint for real-time change notifications. Only re-fetch spools that actually changed.
- Alternatively, implement ETag / `If-Modified-Since` caching so unchanged responses don't trigger a full data rebuild.
- At minimum, **diff the old and new data** and only fire entity updates for spools whose data actually changed.

---

## Hotspot 5 — Cleanup Runs on Every Coordinator Update

**File:** `__init__.py`

Two cleanup operations run on **every single coordinator update**, not just at setup or when the spool count changes:

1. **Orphan device cleanup** — Iterates all devices in the device registry to find and remove devices for deleted spools.
2. **Extra field sensor cleanup** — Iterates all entities in the entity registry to find and remove sensors for deleted extra fields.

**Impact:** On a system with 5,000+ entities and hundreds of devices, these registry scans add CPU and memory overhead on every update cycle (typically every 30–60 seconds).

**Recommendation:** Run cleanup only:
- On initial setup
- When the spool count changes (`len(new_data) != len(old_data)`)
- On a separate, less frequent timer (e.g., every 10 minutes)

---

## Hotspot 6 — `reload_config_entry` is Catastrophic

**File:** `__init__.py` — `async_unload_entry()` + `async_setup_entry()`

When `homeassistant.reload_config_entry` is called (or the integration is reloaded from the UI), the following sequence executes:

1. **Unload:** Destroys all ~5,000+ entities (entity registry cleanup), closes the API `aiohttp` session, removes all coordinator data, unloads all platforms
2. **Setup:** Re-runs `async_setup_entry` from scratch — re-fetches all spool + filament data from the API, re-generates all PIL images, re-creates all ~5,000+ entities, re-registers all devices, re-runs all cleanup scans

**Impact:** This is the **OOM kill trigger** on our Raspberry Pi 5. The teardown and rebuild of 5,000+ entities plus 200+ PIL images creates a RAM spike that exceeds available memory. If triggered twice in quick succession (e.g., user clicks "Execute" twice on a script that calls reload), the system reboots.

**Recommendation:**
- Add a **debounce/lock** to prevent concurrent reloads.
- For entity data refreshes, use `coordinator.async_request_refresh()` instead of a full reload.
- Document that `reload_config_entry` should be avoided in automations/scripts with large spool counts.
- Consider a **phased setup** that creates entities in batches with `await asyncio.sleep(0)` yields between batches to avoid monopolizing the event loop and spiking RAM.

---

## Extra Bug — `json.dumps()` Double-Encoding in `patch_spool`

**File:** `spoolman_api.py` — `patch_spool()`

The `patch_spool` method calls `json.dumps()` on each individual extra field value before sending to the API:

```python
# In spoolman_api.py:
extras = {k: json.dumps(v) for k, v in spool.extras.items()}
```

Since Home Assistant templates render everything as strings, a value like `"true"` becomes `'"true"'` (a JSON-encoded string containing a string). The Spoolman API rejects this double-encoded value with a **400 Bad Request**.

**Impact:** Any automation or script that uses `spoolman.patch_spool` to update extra fields will fail with 400 errors.

**Workaround:** Call the Spoolman REST API directly via `rest_command` with `{{ extra | tojson }}`, bypassing the integration's service call entirely.

**Recommendation (PR-worthy):** Remove the `json.dumps()` wrapping from extra field values. The values are already strings and should be sent as-is. The `aiohttp` session's `json=` parameter handles the outer JSON serialization.

---

## Impact Summary

| # | Hotspot | Memory Impact | CPU Impact | Fix Complexity |
|---|---------|--------------|------------|----------------|
| 1 | Entity explosion (31 per spool) | **Critical** | Medium | Low — set `entity_registry_enabled_default = False` |
| 2 | Full data duplication per entity | **Critical** | High | Medium — refactor to coordinator-referenced data |
| 3 | PIL image generation at setup | **High** | Medium | Low — SVG data URIs or lazy generation |
| 4 | Full data fetch every update | Medium | Medium | Medium — WebSocket or ETag caching |
| 5 | Cleanup on every update | Low–Medium | Medium | Low — conditional execution |
| 6 | Reload = full teardown + rebuild | **Critical** (burst) | **Critical** | Medium — debounce + phased setup |
| Bug | `json.dumps()` double-encoding | N/A | N/A | Low — remove the `json.dumps()` call |

---

## Suggested PR Approach

### Phase 1 — Quick Wins (Low risk, high impact)
1. Mark most per-spool sensors as diagnostic (disabled by default)
2. Fix the `json.dumps()` double-encoding bug in `patch_spool`
3. Move cleanup to conditional execution (only when spool count changes)
4. Add a debounce/lock to prevent concurrent reloads

### Phase 2 — Architecture Improvements
5. Refactor entity data to reference coordinator instead of storing copies
6. Replace PIL image generation with SVG data URIs (or lazy generation with caching)
7. Cache `flatten_dict` results per coordinator update cycle

### Phase 3 — Incremental Updates
8. Implement WebSocket-based change detection
9. Diff old vs new coordinator data; only update changed entities

---

## Why Boot Survives but Reload OOM-Kills

All of the same costly activities (coordinator fetch, entity creation, PIL image generation, cleanup scans) run during `async_setup_entry` on every HA boot. The boot path is identical to the reload path. So why does boot work but reload doesn't?

| Factor | Boot (clean start) | Reload (live system) |
|--------|-------------------|---------------------|
| Pre-existing entities in memory | **0** — clean slate | **~5,014** being torn down |
| Baseline RAM from other integrations | Minimal — integrations load sequentially | Full — everything already running |
| Peak memory | Setup cost only | Teardown **+** setup simultaneously |
| Python GC timing | N/A — no prior objects | Old entity objects pending GC while new ones allocate |

The critical difference is **reload creates roughly 2× peak memory**:

1. `async_unload_entry` destroys ~5,000 entities (entity registry ops, state machine cleanup, event bus unsubscriptions), but **Python's garbage collector doesn't free that memory instantly**.
2. `async_setup_entry` immediately starts allocating ~5,000 new entities, new PIL images, and new coordinator data **on top of the not-yet-collected old objects**.
3. The combined footprint hits: `running_system_baseline + old_entities_pending_gc + new_entities + PIL_images` — exceeding available RAM.

On boot, the Pi starts with just the OS + HA core. Integrations load sequentially into clean memory. The single setup cost fits in RAM (likely tight, but under the threshold).

On reload — especially if triggered twice in quick succession (e.g., user clicks Execute twice on a script that calls `reload_config_entry`) — the doubled allocation pushes past the OOM limit, the kernel kills the HA process, and the Pi reboots.

**Note on PIL images:** The images are generated sequentially (each `await hass.async_add_executor_job(...)` is awaited in the loop), so only one 100×100 image is in memory at a time before being saved to disk. The PIL overhead is real but not the primary killer. The main memory consumer is the **5,014 entity objects each holding a full spool dict copy**, doubled during reload.

---

## Test Environment Details

- **Hardware:** Raspberry Pi 5, aarch64
- **OS:** Home Assistant OS 17.1
- **HA Core:** 2026.3.4
- **Spoolman:** Server at `192.168.1.77:7912` (v1 API)
- **Spool count:** 162 registered spools
- **Entity count:** 5,014+ sensor entities from this integration alone
- **Observed failure:** `homeassistant.reload_config_entry` triggered from a script caused full system reboot (OOM kill)
