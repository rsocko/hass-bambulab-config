# Spool Matching Logic — Design Analysis & Unification Recommendations

> **Date:** 2026-03-19  
> **Scope:** Comparison of spool-matching logic between the `spoolman_tray_map` template sensor (dashboard/UI layer) and the `find_matching_spool_in_spoolman` script (automation/sync layer).

---

## 1. Executive Summary

Two independent implementations perform the same conceptual task — match a physical spool in an AMS tray (or external spool holder) to a spool record in Spoolman. They differ in data source, matching criteria, disambiguation depth, and feature scope. Several of these differences introduce functional gaps and potential false matches in the template sensor (dashboard) path.

### Implementation Status (2026-03-19)

Option A was implemented in this repository:
- Matching authority moved to `sensor.spoolman_tray_map` for active-tray and print-complete update paths
- Template matcher updated with UUID miss fallthrough, color+material matching, vendor-aware Bambu fallback, and AMS disambiguation
- Sealed spool exclusion remains intentional in template matching
- Legacy script matcher retained for diagnostics and parity testing
- New self-test added to validate template-vs-legacy matching parity

| Aspect | Template Sensor (`spoolman_tray_map`) | Script (`find_matching_spool_in_spoolman`) |
|--------|---------------------------------------|-------------------------------------------|
| Location | `core/template_sensors/spoolman_tray_map.yaml` | `spoolman_sync/scripts/find_matching_spool_in_spoolman-script.yaml` |
| Consumers | Dashboard cards, popups, desiccant tracking | Print-complete automation, active-tray-changed automation, manual match script |
| Execution model | Reactive Jinja2 template (runs on every state change of any dependency) | On-demand HA script (invoked by automations) |
| Data source | HA entities (`sensor.spoolman_spool_*`) via Spoolman HA integration | Spoolman REST API (`rest_command.spoolman_getspools`) |

---

## 2. Matching Logic — Side-by-Side Comparison

### 2.1 UUID-Based Matching (Primary Path)

Both implementations share the same high-level structure: if the tray has a valid UUID (non-empty, not all zeros), attempt to match it against spool records.

| Step | Template Sensor | Script |
|------|----------------|--------|
| **UUID source** | `state_attr(tray_entity, 'tray_uuid')` | `parameters.target_uuid` (passed by caller) |
| **Validity check** | `tray_uuid != '' and tray_uuid != EMPTY_UUID` | `target_uuid is not none and target_uuid != '' and not regex_match('^0+$')` |
| **Search target** | `spool_entities \| selectattr('attributes.extra_spool_uuid', 'equalto', tray_uuid)` | `spools.content \| selectattr('extra.spool_uuid', 'equalto', '"' ~ target_uuid ~ '"')` |
| **Exact 1 match** | ✅ Return spool | ✅ Return spool with `success: true` |
| **Multiple matches** | ✅ Error message, clear match | ✅ Error, log, `success: false` |
| **0 matches** | ⚠️ Sets `match_reason` only — **no fallback to color matching** | ✅ Falls through to color+type matching |

**Gap identified:** When UUID matching returns 0 results in the template sensor, the code sets `match_reason = 'No unsealed spool with UUID ...'` but does **not** fall through to color-based matching. The Jinja `{% else %}` block (color matching) only runs when `tray_uuid` is empty/invalid. This means a Bambu spool whose UUID has not yet been recorded in Spoolman will show as "Unknown Filament" on the dashboard, even though the script would successfully match it by color+type and then auto-populate the UUID.

### 2.2 Color/Attribute Fallback (Secondary Path)

| Criterion | Template Sensor | Script |
|-----------|----------------|--------|
| **Color hex** | ✅ Normalized (strip `#`, strip alpha, lowercase, first 6 chars) | ✅ Normalized (strip `#`, strip `"`, lowercase, first 6 chars) |
| **Material type** | ❌ **Not checked** | ✅ `selectattr('material', 'equalto', target_type)` |
| **Profile name** | ❌ **Not checked** | ✅ Checked for `bambu_only` path: `selectattr('profile_name', 'equalto', target_name)` |
| **Vendor filter** | Always: `vendor_name != 'Bambu Lab'` | Contextual: `vendor == 'Bambu Lab'` when `bambu_only`, `vendor != 'Bambu Lab'` otherwise |
| **Sealed filtering** | Pre-filtered globally: `rejectattr('extra_sealed', 'equalto', true)` | Not pre-filtered; sealed status used only in disambiguation |

**Gaps identified:**

1. **No material type matching in template:** If you have a red PLA spool and a red PETG spool (same hex color, different material), the template sensor cannot distinguish between them and will either (a) return the wrong one if exactly one is unsealed, or (b) report "Multiple unsealed spools" if both are.

2. **No profile name matching in template:** Two Bambu PLA Basic (Matte) and Bambu PLA Basic (Silk) spools of the same color would be ambiguous. The script uses `profile_name` for the Bambu path to differentiate them.

3. **Vendor filter logic is inverted for Bambu UUID-failed path:** In the script, when a Bambu spool's UUID isn't found, the `bambu_only` flag is set to `true` from the UUID step, so the color fallback searches **within** Bambu Lab spools. In the template, the color fallback **always** excludes Bambu Lab, meaning a Bambu spool that failed UUID matching will never be found in color fallback. This is a functional bug.

### 2.3 Disambiguation (Multiple Matches)

| Strategy | Template Sensor | Script |
|----------|----------------|--------|
| **AMS location preference** | ❌ Not implemented | ✅ If exactly 1 match in "AMS" location → use it |
| **Unsealed/opened preference** | ❌ Not implemented (but sealed spools are pre-filtered) | ✅ If multiple with 0 in AMS and exactly 1 unsealed → use it |
| **Multiple in AMS** | N/A | ✅ Explicit error: "Multiple spools found in AMS" |
| **Handling > 1 match** | Sets error reason, returns no match | Rich branching: AMS count → unsealed count → explicit error |

**Gap:** The template sensor's pre-filtering of sealed spools is roughly equivalent to the script's unsealed preference for the initial pool, but the template has no AMS location tiebreaker. If you have 2 unsealed red PLA spools (one in AMS, one on shelf), the template cannot choose while the script correctly picks the AMS one.

### 2.4 Empty Tray Detection

| Scenario | Template Sensor | Script |
|----------|----------------|--------|
| **AMS empty** | ✅ `type == 'Empty'` → return `empty_tray_result` | N/A (caller skips zero-weight trays) |
| **External empty** | ✅ Rich detection: `name == 'Empty'` OR (UUID empty AND color empty/alpha-00) | Handled in `active_tray_changed` automation (transition-safe logic) |

Both handle empty detection, but at different layers. The template sensor handles it inline; the automation layer handles it in pre-processing before invoking the script.

### 2.5 UUID Auto-Population

| Actor | Template Sensor | Script / Automations |
|-------|----------------|---------------------|
| **Auto-update during print** | ❌ Not possible (read-only template) | ✅ `active_tray_changed` automation patches `extra.spool_uuid` if Bambu spool matched by color and UUID is empty |
| **Manual UI update** | ❌ Not directly (manual tray matching action removed from popup; pin workflow is tray_map-driven) | ✅ UUID patch/update remains in automation/script write paths where applicable |
| **Conditions** | N/A | Tray UUID valid AND spool is Bambu Lab vendor AND spool has no existing UUID |

### 2.6 Additional Features (Exclusive to Each)

| Feature | Template Sensor Only | Script Only |
|---------|---------------------|-------------|
| **Desiccant tracking** | ✅ Full age-based color status (green/yellow/orange/red) | ❌ |
| **Weight history & remaining** | ✅ Via popup card (reads `spoolman_spool_*` attributes) | ❌ (uses weight for usage deduction) |
| **Print weight safety indicator** | ✅ Color-coded sufficiency display | ❌ |
| **Error logging/recovery** | ❌ | ✅ Persistent error log, manual recovery script |
| **Multi-AMS entity resolution** | Hardcoded tray entity dict | Dynamically parses AMS/tray numbers from `print_weight` attribute keys |
| **Backup/restore (HA restart)** | ❌ | ✅ Full persistence system |

---

## 3. Scenario Coverage Matrix

| Scenario | Template Sensor | Script | Notes |
|----------|:-:|:-:|-------|
| Bambu spool with UUID in Spoolman | ✅ | ✅ | Both match by UUID |
| Bambu spool, UUID NOT in Spoolman | ❌ | ✅ | **Template fails**: excludes Bambu Lab in color fallback; Script succeeds and auto-populates UUID |
| Non-Bambu spool, unique color+type | ⚠️ | ✅ | Template matches by color only (ignores type) — risky if same color, different type |
| Non-Bambu spool, ambiguous color | ❌ | ⚠️ | Template: no disambiguation. Script: tries AMS location / unsealed |
| Same color, different material type | ❌ | ✅ | Template cannot differentiate |
| Same color+type, different profile | ❌ | ✅ | Template cannot differentiate; Script checks profile_name (Bambu path) |
| Multiple unsealed, 1 in AMS | ❌ | ✅ | Template: error. Script: picks AMS spool |
| External spool | ✅ | ✅ | Both handle with specific detection |
| External spool 2 (dual nozzle) | ❌ | ✅ | Template maps only 1 external spool entity |
| Spool runout/swap mid-print | N/A | ✅ | Script detects missing UUID and skips |
| HA restart during print | N/A | ✅ | Script has backup/restore system |
| UUID duplicate (data integrity) | ✅ | ✅ | Both detect and report |
| Sealed spool only (no unsealed match) | ❌ | ⚠️ | Template pre-filters sealed. Script tries to match but may return error |

---

## 4. Root Cause of Divergence

The two implementations exist because they serve different runtime contexts:

1. **Template sensor** must be a pure Jinja2 expression that runs inside HA's template engine. It cannot invoke service calls, REST APIs, or scripts. It can only read HA entity states and attributes.

2. **Script** runs as a full HA action sequence. It can call REST APIs, invoke services, use `choose` branching, and return structured responses.

This fundamental constraint means the template sensor cannot directly call the script. However, the matching *logic* (criteria and disambiguation rules) should still be consistent between them.

---

## 5. Unification Recommendations

### 5.1 Can the Logic Be Defined Once?

**Partial unification is achievable. Full unification is not practical.**

The HA template engine (Jinja2) and the script engine (YAML actions) have incompatible execution models. The template cannot call scripts or REST commands, and the script cannot be "inlined" into a template. However:

#### Option A: Template Sensor as Authoritative Matcher (Recommended)

**Upgrade the template sensor's matching logic to match the script's quality**, then have the automations consume `spoolman_tray_map` instead of calling the script independently.

**Pros:**
- Single source of truth for tray→spool mapping
- Dashboard and automations always agree
- Template re-evaluates whenever tray data or spool entities change (reactive)
- Removes the REST API call from the hot path (automations become faster)

**Cons:**
- Template sensor Jinja2 has limited debugging capability
- Complex disambiguation logic in Jinja2 can be hard to maintain
- Template sensor doesn't have access to `profile_name` unless it's exposed as an entity attribute by the Spoolman HA integration

**Implementation steps:**
1. Add material type matching to color fallback in template
2. Add `bambu_only` path: when UUID fails for a spool that had a UUID, search within Bambu Lab vendor instead of excluding it
3. Add AMS location and unsealed disambiguation
4. Add profile_name matching if available via entity attributes
5. Have automations read from `sensor.spoolman_tray_map` attribute instead of calling the script
6. Keep the script for write-path operations only (UUID update, manual recovery)

#### Option B: Script as Authoritative Matcher, Cache Results in a Sensor

Create a trigger-based template sensor that listens for a custom event (e.g., `bambulab_tray_map_updated`) fired by the script, and stores the script's result as an attribute.

**Pros:**
- Script retains full Spoolman API access and disambiguation power
- Template just displays cached results

**Cons:**
- Requires automations to fire the event whenever tray data changes
- Introduces latency (sensor updates only after automation runs)
- More moving parts; risk of stale data if event isn't fired

#### Option C: Keep Both, Sync the Logic Manually (Current State, Improved)

Align the template sensor's matching criteria with the script's, but accept they are two codebases.

**Pros:**
- Minimal architectural change
- Each layer optimized for its context

**Cons:**
- Ongoing maintenance burden
- Must manually keep logic in sync
- Easy to introduce drift

### 5.2 Recommendation

**Option A** provides the best balance. Specifically:

| Change | Priority | Effort |
|--------|----------|--------|
| Add material type to template color fallback | **Critical** | Low |
| Add `bambu_only` fallback path to template (UUID miss → search Bambu vendor) | **Critical** | Medium |
| Add AMS location preference disambiguation | High | Medium |
| Add unsealed preference disambiguation | High | Low (already pre-filtered) |
| Fall through from UUID miss to color matching in template | **Critical** | Low |
| Add profile_name matching if attribute available | Medium | Low |
| Add External Spool 2 to template tray dict | Low | Trivial |
| Have print-complete automation read tray_map instead of calling script | Medium | Medium |

Status: Completed (core matching consumers now read `sensor.spoolman_tray_map`).

### 5.3 Keeping Logic in Sync (If Option C is Chosen)

If both implementations are kept:

1. **Create a shared decision table** (this document's Section 3 matrix) as a test specification
2. **Add integration tests** using HA's `test` service or a custom script that simulates tray states and validates both paths produce the same result
3. **Document the matching algorithm once** with explicit rules, and mark both files as implementing it (cross-reference comments already exist)
4. **Use a change checklist**: any PR modifying matching logic in one must verify the other

---

## 6. Specific Bugs and Fixes

### 6.1 [CRITICAL] Template: UUID Miss Does Not Fall Through to Color Matching

**File:** `homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml`

**Current behavior:** When `tray_uuid` is valid but no spool has that UUID, the `{% if %}` branch sets `match_reason` but `match` remains empty. No color fallback executes because color matching is inside the `{% else %}` (UUID not provided) branch.

**Impact:** Bambu spools with unrecognized UUIDs (new spool, UUID not yet in Spoolman) show as "Unknown Filament" on dashboard even though the script would match them.

**Fix:** Restructure to attempt UUID first, then fall through to color+type if UUID yields 0 matches:
```jinja2
{# Attempt UUID match first #}
{% set match = [] %}
{% set match_reason = none %}
{% set tried_uuid = false %}

{% if tray_uuid and tray_uuid != '' and tray_uuid != EMPTY_UUID %}
  {% set tried_uuid = true %}
  {% set match = spool_entities | selectattr('attributes.extra_spool_uuid', 'equalto', tray_uuid) | list %}
  {% if match | length > 1 %}
    {% set match_reason = 'Multiple spools with UUID ' ~ tray_uuid %}
    {% set match = [] %}
  {% endif %}
{% endif %}

{# Fall through to color+type if UUID matched nothing or was not available #}
{% if match | length == 0 and match_reason is none %}
  {# Color + type matching with vendor-awareness #}
  ...
{% endif %}
```

### 6.2 [CRITICAL] Template: No Material Type Matching in Color Fallback

**Current:** Only matches `filament_color_hex`. Two spools of the same color but different materials will conflict.

**Fix:** Add type matching to the color fallback loop:
```jinja2
{% set tray_material = state_attr(tray_entity, 'type') | default('') | upper %}
...
{% if s.attributes.filament_color_hex | default('') | lower == tray_color
    and (s.attributes.filament_material | default('') | upper) == tray_material
    and s.attributes.filament_vendor_name | default('') != 'Bambu Lab' %}
```

### 6.3 [CRITICAL] Template: Bambu Spool Color Fallback Excluded

**Current:** Color fallback always filters `vendor != 'Bambu Lab'`. Bambu spools that failed UUID matching can never match.

**Fix:** Context-aware vendor filter:
```jinja2
{# If we tried UUID (Bambu spool) but found nothing, search WITHIN Bambu Lab #}
{% set is_bambu_path = tried_uuid %}

{% for s in spool_entities %}
  {% set vendor = s.attributes.filament_vendor_name | default('') %}
  {% set vendor_ok = (vendor == 'Bambu Lab') if is_bambu_path else (vendor != 'Bambu Lab') %}
  {% if s.attributes.filament_color_hex | default('') | lower == tray_color
      and vendor_ok %}
    ...
  {% endif %}
{% endfor %}
```

### 6.4 [HIGH] Template: No AMS Location Disambiguation

**Fix:** After the color+type matching, if multiple matches remain:
```jinja2
{% if match | length > 1 %}
  {# Prefer spool in AMS location #}
  {% set ams_matches = match | selectattr('attributes.location', 'equalto', 'AMS') | list %}
  {% if ams_matches | length == 1 %}
    {% set match = ams_matches %}
  {% elif ams_matches | length > 1 %}
    {% set match_reason = 'Multiple spools in AMS with color #' ~ tray_color ~ ' and type ' ~ tray_material %}
    {% set match = [] %}
  {% else %}
    {% set match_reason = 'Multiple unsealed spools with color #' ~ tray_color ~ ' and type ' ~ tray_material ~ ', none in AMS' %}
    {% set match = [] %}
  {% endif %}
{% endif %}
```

### 6.5 [LOW] Template: Missing External Spool 2 Entry

**Fix:** Add to tray dict:
```yaml
'external_spool_2': 'sensor.ntk_ryansoffice_3dprinter_external_spool2'
```

---

## 7. Functional Divergences Worth Keeping

Some differences between the two paths are intentional and should remain:

| Divergence | Reason |
|------------|--------|
| **Template sensor includes desiccant tracking** | Only relevant for display; automations don't need it |
| **Script calls REST API directly** | UUID auto-update requires write operations not available in templates |
| **Script has error logging/recovery** | Write-path concern; template is read-only |
| **Script has backup/restore for HA restarts** | Runtime concern for automations only |
| **Template pre-filters sealed spools** | Performance optimization for a reactive template; script evaluates sealed status in disambiguation |

---

## 8. Missing Scenarios (Neither Implementation Covers)

| Scenario | Description | Risk | Recommendation |
|----------|-------------|------|----------------|
| **Multi-color spool matching** | Multi-color spools have composite hex codes; matching logic assumes single color | Low (rare) | Could compare first 6 chars of multi-color hex arrays; monitor for user reports |
| **Spool depleted to 0g** | Spoolman spool at 0g remaining is still unsealed; could match when a fresh spool of same type is loaded | Medium | Consider filtering spools with `remaining_weight <= 0` from candidates, or preferring spool with most remaining |
| **Color drift / hex rounding** | Printer-reported hex might differ slightly from Spoolman hex (rounding, gamma) | Low | Could add a tolerance (e.g., ΔE < 3 in LAB space) but complexity likely not worth it |
| **Spool location changes during print** | If spool is moved in Spoolman mid-print, template updates but automation uses stale match | Very Low | Acceptable; prints are relatively short |
| **Multiple printers sharing spool inventory** | Second printer could match to spools currently in first printer's AMS | Medium (if multi-printer) | Add printer-specific location (e.g., "AMS - P1S Office") or filter by active printer |
| **UUID reassignment** | If a Bambu spool is physically replaced but same UUID sticker is reused | Very Low | Out of scope; RFID tags are factory-unique |

---

## 9. Proposed Implementation Plan

### Phase 1 — Fix Critical Template Sensor Gaps (Immediate)

1. Restructure template `spoolman_tray_map.yaml` UUID→color fallthrough
2. Add material type to color matching
3. Add Bambu-aware vendor filter (context-sensitive based on whether UUID was tried)
4. Verify template matches the script's behavior for the top 5 scenarios

Status: Completed.

### Phase 2 — Add Disambiguation to Template (Short-term)

5. Add AMS location preference when multiple color+type matches
6. Consider adding `filament_material` attribute check (verify attribute name in Spoolman HA integration)
7. Add External Spool 2 to tray dict
8. Add profile_name matching if Spoolman HA integration exposes it via entity attributes

Status: Completed for AMS disambiguation and profile-aware matching when profile attributes are exposed.

### Phase 3 — Evaluate Automation Consumption of Tray Map (Medium-term)

9. For `active_tray_changed` automation: evaluate reading `sensor.spoolman_tray_map` attribute to get the pre-matched spool ID, then only calling Spoolman API for write operations (update UUID, update last_used)
10. For `print_complete` automation: keep the script path since it needs backup/restore logic and per-tray weight data that operates differently

Status: Implemented with `tray_map` as matcher while preserving existing backup/restore and write-path behavior.

### Phase 4 — Cross-Validation (Ongoing)

11. Add a diagnostic script or template sensor that compares tray_map results against script results and flags mismatches
12. Document the unified matching algorithm as a specification in `docs/features/spoolman_sync/matching-algorithm-spec.md`

Status:
- Item 11 completed via `script.spool_matching_logic_self_test`
- Item 12 remains optional future documentation work

---

## 10. Appendix — File Reference

| File | Role |
|------|------|
| `homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml` | Template sensor — dashboard matching engine |
| `homeassistant/packages/3d_printing/spoolman_sync/scripts/find_matching_spool_in_spoolman-script.yaml` | Script — automation matching engine |
| `homeassistant/packages/3d_printing/spoolman_sync/automations/active_tray_changed_update_spoolman.yaml` | Automation — active tray sync + UUID auto-update |
| `homeassistant/packages/3d_printing/spoolman_sync/automations/print_complete-update_filament_usage.yaml` | Automation — print completion filament usage |
| `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_popup.yaml` | Dashboard — rich popup consuming tray_map |
| `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_detail.yaml` | Dashboard — compact card consuming tray_map |
