# Multi-Color Spool Matching — Design Document

> **Status**: Design  
> **Created**: 2026-03-19  
> **Phases**: 3 (Foundation → Override Mechanism → Dashboard UX)

## Table of Contents

- [Problem Statement](#problem-statement)
- [How Multi-Color Data is Stored](#how-multi-color-data-is-stored)
- [Bambu Studio Tray Color — Single RGB Only](#bambu-studio-tray-color--single-rgb-only)
  - [Recommended Color Convention for Multi-Color Spools](#recommended-color-convention-for-multi-color-spools)
- [Current Matching Logic & Gaps](#current-matching-logic--gaps)
  - [spoolman\_tray\_map Template Sensor](#spoolman_tray_map-template-sensor)
  - [find\_matching\_spool\_in\_spoolman Script](#find_matching_spool_in_spoolman-script)
- [Proposed Priority Cascade](#proposed-priority-cascade)
- [Manual Override Mechanism](#manual-override-mechanism)
  - [Override Helpers](#override-helpers)
  - [Auto-Clear Behavior](#auto-clear-behavior)
  - [Dashboard Integration](#dashboard-integration)
- [Edge Cases & Scenarios](#edge-cases--scenarios)
- [Risk Assessment — Color-Based Multi-Color Matching](#risk-assessment--color-based-multi-color-matching)
- [Implementation Phases](#implementation-phases)
  - [Phase 1 — Fix Silent Matching Failure (Foundation)](#phase-1--fix-silent-matching-failure-foundation)
  - [Phase 2 — Manual Override Mechanism](#phase-2--manual-override-mechanism)
  - [Phase 3 — Dashboard UX](#phase-3--dashboard-ux)
- [Affected Files](#affected-files)

---

## Problem Statement

Spoolman supports multi-color filament spools (gradients, rainbow, etc.) by storing multiple hex color codes as a comma-delimited string rather than a single `color_hex` value. Both the `spoolman_tray_map` template sensor and the `find_matching_spool_in_spoolman` script currently match spools exclusively via the single-value `filament_color_hex` attribute — which is **absent** on multi-color spools. This means:

1. Multi-color spools without a Bambu UUID (e.g. Sunlu Rainbow) are **completely unmatchable** by automation today.
2. Multi-color Bambu spools (e.g. Dusk Glare) work only because UUID matching succeeds first — if that ever fails, color fallback will also fail.
3. There is no mechanism for a user to manually specify which spool is in a given tray when automatic matching fails.

---

## How Multi-Color Data is Stored

The Spoolman HA integration exposes color information using a **mutually exclusive** data model:

| Spool Type | `filament_color_hex` | `filament_multi_color_hexes` | `filament_multi_color_direction` |
|---|---|---|---|
| **Single-color** (e.g. Blue PLA, spool 25) | `"0A2989"` | *(absent)* | *(absent)* |
| **Multi-color** (Dusk Glare, spool 67) | *(absent)* | `"ffa11f,ff5900"` | `"longitudinal"` |
| **Multi-color** (Rainbow 04, spool 133) | *(absent)* | `"e292fe,fff994,6ef785,93e3fd"` | `"longitudinal"` |

### Live Examples from HA Instance

**Bambu Lab Dusk Glare PLA** — `sensor.spoolman_spool_67`:
- `filament_multi_color_hexes`: `ffa11f,ff5900` (2-color orange gradient)
- `filament_multi_color_direction`: `longitudinal`
- `extra_spool_uuid`: `A8B997CDC7244EDB976129ED5B7DCDFE` (UUID present — matching works today)
- `filament_color_hex`: *(not present)*

**Sunlu Rainbow 04 PLA** — `sensor.spoolman_spool_133`:
- `filament_multi_color_hexes`: `e292fe,fff994,6ef785,93e3fd` (4-color)
- `filament_multi_color_direction`: `longitudinal`
- `extra_spool_uuid`: `""` (empty — no UUID)
- `filament_color_hex`: *(not present)*
- **This spool is currently unmatchable by automation.**

**Sunlu Rainbow 02 PLA** — `sensor.spoolman_filament_96`:
- `multi_color_hexes`: `982abc,e63b7a,00a1d8` (3-color)

**Sunlu Rainbow 01 PLA** — `sensor.spoolman_filament_98`:
- `multi_color_hexes`: `ff3a2f,ff8800,ffcc01,33c759,00a1d8,982abc` (6-color)

### Where Multi-Color is Already Used (Display Only)

The `filament_multi_color_hexes` and `filament_multi_color_direction` attributes are already read and rendered in the dashboard layer:

- **AMS tray detail card** ([ams_tray_detail.yaml](../../../homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_detail.yaml)) — background gradient fill
- **AMS tray popup** ([ams_tray_popup.yaml](../../../homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_popup.yaml)) — header gradient, text contrast
- **Filament catalog spool card** ([catalog_spool_card.yaml](../../../homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_card.yaml))
- **Filament catalog popup** ([catalog_spool_popup_content.yaml](../../../homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/catalog_spool_popup_content.yaml))

These display paths are working correctly. The gap is in the **matching/sync logic** that feeds them.

---

## Bambu Studio Tray Color — Single RGB Only

**Confirmed**: The Bambu Lab integration AMS tray entity exposes a single `color` attribute as an 8-char hex with alpha channel (e.g. `#0A2989FF`).

- For **Bambu spools with RFID**, the color is read from the NFC/RFID tag automatically.
- For **non-Bambu spools** (or any spool without readable UUID data), the user must manually select a single RGB color via Bambu Studio's Device tab. **There is no multi-color picker.**

The `spoolman_tray_map` template sensor normalizes the 8-char hex to 6 chars by stripping `#` and removing the trailing alpha bytes.

### Recommended Color Convention for Multi-Color Spools

When manually setting up a multi-color spool in Bambu Studio, **use the first hex value from the spool's `multi_color_hexes` list**:

| Spool | `multi_color_hexes` | Set in Bambu Studio |
|---|---|---|
| Dusk Glare | `ffa11f,ff5900` | `#FFA11F` |
| Rainbow 04 | `e292fe,fff994,6ef785,93e3fd` | `#E292FE` |
| Rainbow 02 | `982abc,e63b7a,00a1d8` | `#982ABC` |
| Rainbow 01 | `ff3a2f,ff8800,ffcc01,33c759,00a1d8,982abc` | `#FF3A2F` |

**Rationale**: This is deterministic, codifiable in matching logic, and doesn't require the user to remember or look up a designated color. The matching logic can specifically check the first element of `multi_color_hexes` as a secondary match strategy.

---

## Current Matching Logic & Gaps

### spoolman_tray_map Template Sensor

**File**: [spoolman_tray_map.yaml](../../../homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml)

Current 2-tier matching:
1. **UUID match**: `spool_entities | selectattr('attributes.extra_spool_uuid', 'equalto', tray_uuid)`
2. **Color fallback**: `s.attributes.filament_color_hex | default('') | lower == tray_color` (excluding Bambu Lab vendor)

**Gap**: Multi-color spools have no `filament_color_hex` attribute. They are invisible to Tier 2.

### find_matching_spool_in_spoolman Script

**File**: [find_matching_spool_in_spoolman-script.yaml](../../../homeassistant/packages/3d_printing/spoolman_sync/scripts/find_matching_spool_in_spoolman-script.yaml)

The script builds a `spools_lower` list from the Spoolman REST API where each entry has:
```jinja
"color_hex_lower": "{{ (spool.filament.color_hex | default('', true) | ...)[:6] }}"
```

For multi-color filaments, `spool.filament.color_hex` is null/empty from the API. The `color_hex_lower` field becomes `""`, which never matches a real tray color.

---

## Proposed Priority Cascade

Updated matching order (both `spoolman_tray_map` and `find_matching_spool_in_spoolman`):

```
1. UUID Match (tray RFID tag → extra_spool_uuid)              ← highest confidence
2. Manual Override (input_text.{tray_name}_spool_override)     ← user-specified pin
3. Color Match — exact (filament_color_hex)                    ← single-color spools
4. Color Match — first multi-color hex                         ← multi-color convention
5. Color Match — any multi-color hex contains tray color       ← broadest fallback
6. Unmatched (with diagnostic reason)                          ← lowest
```

> **Note**: Tiers 3–5 all continue to apply existing disambiguators: material type, profile name, sealed status, and AMS location.

---

## Manual Override Mechanism

### Override Helpers

Create one `input_text` per tray slot (9 total). Each stores a Spoolman spool ID or empty string:

```yaml
# Example: homeassistant/packages/3d_printing/spoolman_sync/helpers/input_text/
ams_1_tray_1_spool_override:
  name: "AMS 1 Tray 1 Spool Override"
  max: 10
  initial: ""
  icon: mdi:link-variant-plus

ams_1_tray_2_spool_override:
  name: "AMS 1 Tray 2 Spool Override"
  max: 10
  initial: ""
  icon: mdi:link-variant-plus

# ... ams_1_tray_3, ams_1_tray_4
# ... ams_2_tray_1 through ams_2_tray_4
# ... external_spool_spool_override
```

### Auto-Clear Behavior

A lightweight automation should watch for tray content changes and clear stale overrides:

| Tray Event | Action |
|---|---|
| `tray_uuid` changed to a new non-empty/non-zero value | Clear override (new Bambu spool inserted, UUID match takes over) |
| `type` changed to `Empty` | Clear override (spool removed) |
| Only `color`, `remain`, or other attribute changed | Do NOT clear (informational update during printing) |

### Dashboard Integration

Add controls to the AMS tray popup:

- **"Pin Spool" button**: Opens a dropdown/selector of all unsealed spools from Spoolman. On selection, sets the `input_text` override for that tray.
- **Override indicator**: When an override is active, show a chip/badge on the tray detail card and in the popup header.
- **"Unpin" button**: Clears the override, falling back to automatic matching.
- For **unmatched trays** showing "Unknown Filament": the Pin Spool action becomes the primary call-to-action.

---

## Edge Cases & Scenarios

| # | Scenario | Current Behavior | After Phase 1 | After Phase 2 |
|---|---|---|---|---|
| 1 | Bambu multi-color spool with UUID (e.g. Dusk Glare) | ✅ UUID match | ✅ No change | ✅ No change |
| 2 | Non-Bambu multi-color spool, no UUID (e.g. Rainbow 04) | ❌ Unmatchable | ✅ First-color match | ✅ Override available |
| 3 | Non-Bambu spool with user-written NFC UUID | ✅ If `extra_spool_uuid` populated | ✅ No change | ✅ No change |
| 4 | Two multi-color spools sharing same first color | ❌ Silent fail | ⚠️ Ambiguous — existing tiebreakers apply | ✅ Override resolves |
| 5 | Spool in AMS but not yet added to Spoolman | ❌ No match | ❌ Still no match | ❌ Override can't help — add to Spoolman first |
| 6 | `filament_color_hex` on spool A matches a multi-color spool B's first hex | N/A | ⚠️ Single-color exact match takes priority (Tier 3 before Tier 4) | ✅ Override if wrong |
| 7 | External spool (non-AMS) with multi-color | Same gap as AMS | ✅ Same fix applies | ✅ Override for `external_spool` too |
| 8 | Spool UUID changes (re-wound, sticker swapped) | UUID mismatch | UUID mismatch → color fallback | ✅ Override covers; user updates UUID in Spoolman later |
| 9 | Print completion weight deduction for overridden spool | Script uses `find_matching_spool` which won't find it | Same | ✅ Override ID passed through to usage deduction |
| 10 | `spoolman_tray_map` color for dashboard rendering (overridden multi-color spool) | Uses tray_color from AMS entity | Uses tray_color | ✅ Reads `filament_multi_color_hexes` from pinned spool for gradient |
| 11 | Two single-color spools with identical color + material | ❌ Multiple match error | ❌ Same (outside multi-color scope) | ✅ Override resolves |
| 12 | User sets arbitrary (non-first) color in Bambu Studio for multi-color spool | N/A | ⚠️ First-color match fails; any-color match (Tier 5) may catch it | ✅ Override as fallback |

---

## Risk Assessment — Color-Based Multi-Color Matching

| Scenario | Risk | Mitigation |
|---|---|---|
| User follows first-color convention → matches correctly | Low | Document convention; add to custom field docs |
| User picks arbitrary color → first-color match fails | Medium | Tier 5 any-color fallback; manual override |
| Tray color matches BOTH a multi-color spool AND a single-color spool | Medium | Existing tiebreakers (material, profile_name, location, sealed); single-color exact match prioritized |
| Two multi-color spools share same first color | Low (current inventory) but possible | Manual override mechanism |

---

## Implementation Phases

### Phase 1 — Fix Silent Matching Failure (Foundation)

**Goal**: Multi-color spools can be automatically matched when using the first-color convention.

#### 1.1 Update `spoolman_tray_map` Template Sensor

**File**: `homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml`

In the color fallback block (after UUID matching fails), add multi-color checks:

```jinja
{# Existing: Exact match on filament_color_hex #}
{% if s.attributes.filament_color_hex | default('') | lower == tray_color
    and s.attributes.filament_vendor_name | default('') != 'Bambu Lab' %}
  {% set ns_color.spools = ns_color.spools + [s] %}

{# NEW: First-color match on multi_color_hexes #}
{% elif s.attributes.filament_multi_color_hexes | default('') != ''
    and (s.attributes.filament_multi_color_hexes.split(',')[0] | trim | replace('#','') | lower) == tray_color
    and s.attributes.filament_vendor_name | default('') != 'Bambu Lab' %}
  {% set ns_color.spools = ns_color.spools + [s] %}
{% endif %}
```

Optionally add a Tier 5 any-color check after the above yields no results.

#### 1.2 Update `find_matching_spool_in_spoolman` Script

**File**: `homeassistant/packages/3d_printing/spoolman_sync/scripts/find_matching_spool_in_spoolman-script.yaml`

Extend the `spools_lower` construction to include multi-color data:

```jinja
"color_hex_lower": "{{ ... }}",
"multi_color_hexes": "{{ spool.filament.multi_color_hexes | default('', true) }}",
"first_multi_color_hex": "{{ (spool.filament.multi_color_hexes | default('', true)).split(',')[0] | trim | replace('#','') | lower }}"
```

Add fallback matching when `color_hex_lower` match yields zero results:

```jinja
{# If no exact color match, try first multi-color hex #}
{% set matched_spools_multi = spools_lower
    | selectattr('first_multi_color_hex', 'equalto', query_hex_lower)
    | selectattr('material', 'equalto', parameters.target_type)
    | list %}
```

#### 1.3 Document the First-Color Convention

Update [spoolman-custom-fields.md](spoolman-custom-fields.md) and this document to describe the convention for setting a multi-color spool's color in Bambu Studio.

---

### Phase 2 — Manual Override Mechanism

**Goal**: Users can pin a specific Spoolman spool to any tray, covering all edge cases.

#### 2.1 Create Override Helper Entities (9 `input_text`)

**Location**: `homeassistant/packages/3d_printing/spoolman_sync/helpers/input_text/`

Create one file per tray (or a single combined file):
- `ams_1_tray_1_spool_override` through `ams_2_tray_4_spool_override`
- `external_spool_spool_override`

#### 2.2 Wire Override into `spoolman_tray_map`

Insert override check between UUID match and color fallback:

```jinja
{# --- MANUAL OVERRIDE CHECK --- #}
{% set override_entity = 'input_text.' ~ tray_name ~ '_spool_override' %}
{% set override_id = states(override_entity) | default('') | trim %}
{% if not match and override_id != '' and override_id | int(0) > 0 %}
  {% set match = spool_entities
    | selectattr('entity_id', 'equalto', 'sensor.spoolman_spool_' ~ override_id)
    | list %}
  {% if match | length == 1 %}
    {% set match_reason = 'Manual override (spool ' ~ override_id ~ ')' %}
  {% endif %}
{% endif %}
```

#### 2.3 Wire Override into `find_matching_spool_in_spoolman` Script

Accept optional `override_spool_id` parameter. If provided and non-empty, look up that spool ID directly in the Spoolman API response and return it (skipping UUID and color tiers).

#### 2.4 Wire Override into `active_tray_changed_update_spoolman` Automation

Read the tray's override helper before calling `find_matching_spool_in_spoolman`. Pass the override ID through.

#### 2.5 Wire Override into `print_complete-update_filament_usage` Automation

Ensure the weight deduction path also respects overrides — read the override for each tray that had print weight, pass the ID into the spool lookup.

#### 2.6 Create Auto-Clear Automation

New automation: watches tray UUID and type attributes. Clears the corresponding override `input_text` when:
- `tray_uuid` changes to a new non-empty value
- `type` becomes `Empty`

---

### Phase 3 — Dashboard UX

**Goal**: Users can manage overrides visually from the AMS tray popup.

#### 3.1 Add "Pin Spool" to AMS Tray Popup

In `ams_tray_popup.yaml`, add a conditional section:
- Shows a spool selector (e.g. dropdown built from `states.sensor | selectattr('entity_id', 'match', 'sensor.spoolman_spool_\\d+$')`)
- On selection, calls `input_text.set_value` for the tray's override helper
- Includes an "Unpin" button to clear the override

#### 3.2 Show Override Indicator on AMS Tray Detail Cards

In `ams_tray_detail.yaml`, add a custom field (e.g. a small pin icon) that appears when the tray's override helper is non-empty.

#### 3.3 Ensure Gradient Rendering for Overridden Multi-Color Spools

When an override is active, `spoolman_tray_map` should propagate the matched spool's `filament_multi_color_hexes` so the dashboard can render gradients even though the AMS tray entity only reports one color.

Confirm that `ams_tray_detail.yaml` and `ams_tray_popup.yaml` read multi-color data from the **spool entity** (they already do) rather than from `tray_map.color` — this should work without changes as long as `spool_id` is populated by the override.

---

## Affected Files

| File | Phase | Change |
|---|---|---|
| `homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml` | 1, 2 | Add multi-color color match; add override check |
| `homeassistant/packages/3d_printing/spoolman_sync/scripts/find_matching_spool_in_spoolman-script.yaml` | 1, 2 | Add multi-color fields to `spools_lower`; add override parameter |
| `homeassistant/packages/3d_printing/spoolman_sync/scripts/match_inserted_tray_spool-script.yaml` | 2 | Pass override ID through |
| `homeassistant/packages/3d_printing/spoolman_sync/automations/active_tray_changed_update_spoolman.yaml` | 2 | Read and pass override ID |
| `homeassistant/packages/3d_printing/spoolman_sync/automations/print_complete-update_filament_usage.yaml` | 2 | Read and pass override ID for weight deduction |
| `homeassistant/packages/3d_printing/spoolman_sync/helpers/input_text/` | 2 | New override helper files (9 total) |
| `homeassistant/packages/3d_printing/spoolman_sync/automations/` | 2 | New auto-clear automation |
| `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_popup.yaml` | 3 | Pin/Unpin spool controls |
| `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/ams_tray_detail.yaml` | 3 | Override indicator icon |
| `docs/features/spoolman_sync/spoolman-custom-fields.md` | 1 | Document first-color convention |
