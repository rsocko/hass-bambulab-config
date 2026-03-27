# Spool Replace / Refill Workflow — Design Document

> **Status:** Phase 1 Complete (2026-03-26) · Phases 2–5 Pending  
> **Package:** `spoolman_sync`  
> **Related Packages:** `filament_catalog`, `filament_tag`, `core`  
> **Entry Points:** Spool Popup (catalog), AMS Tray Popup (view_main)

---

## 1. Problem Statement

When a spool runs out during or between prints, the user must:
1. Identify the empty spool
2. Find a sealed replacement of the same filament
3. Transfer spool metadata (spool type, clip type, desiccant info, location)
4. Mark the new spool as unsealed and ready for use
5. Archive the spent spool in Spoolman

Today this is a fully manual process involving the Spoolman UI and multiple dashboard interactions. This design introduces a guided wizard-style flow within the existing HA dashboard popups to streamline the entire operation.

---

## 2. User Journey Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                          ENTRY POINTS                                │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌───────┐  ┌────────┐ ┌──────┐ │
│  │ AMS Tray     │  │ Spool Popup  │  │Sealed │  │Runout  │ │NFC   │ │
│  │ Popup        │  │ (Catalog)    │  │Spool  │  │Notifi- │ │Tag   │ │
│  │ "Replace     │  │ "Replace /   │  │Popup  │  │cation  │ │View  │ │
│  │  Spool"      │  │  Refill      │  │"Unseal│  │"Replace│ │"Re-  │ │
│  │  button      │  │  Spool"      │  │& Use" │  │ Spool" │ │place"│ │
│  └──────┬───────┘  └──────┬───────┘  └───┬───┘  └───┬────┘ └──┬───┘ │
│         │                 │              │           │         │      │
│  (only if tray has       │              │    (auto-created    │      │
│   matched spool —        │              │    on filament      │      │
│   NOT available when     │              │    runout; links  (mobile  │
│   tray goes empty        │              │    to catalog     NFC scan │
│   mid-print)             │              │    with pre-set   on AMS   │
│         │                │              │    source spool)  tag)     │
│         └────────┬───────┘              │           │         │      │
│                  │                      │           │         │      │
│                  ▼                      ▼           │         │      │
│         ┌───────────────────┐  ┌──────────────────┐ │         │      │
│         │ STEP 1: Validate  │  │ STEP 1b: Pick    │ │         │      │
│         │ Empty Spool       │  │ Empty Spool to   │ │         │      │
│         │ (warn if > 0g     │  │ Replace (opt.)   │ │         │      │
│         │  remaining)       │  │                  │ │         │      │
│         └────────┬──────────┘  └────────┬─────────┘ │         │      │
│                  │                      │           │         │      │
│                  ├──────────────────────┘           │         │      │
│                  │◄─────────────────────────────────┘         │      │
│                  │◄───────────────────────────────────────────┘      │
│                  ▼                                                    │
│   ┌─────────────────────────────┐                                    │
│   │ STEP 2: Select Replacement  │                                    │
│   │ (sealed spools, same        │                                    │
│   │  filament_id, show location)│                                    │
│   └──────────────┬──────────────┘                                    │
│                  ▼                                                    │
│   ┌─────────────────────────────┐                                    │
│   │ STEP 3: Configure Transfer  │                                    │
│   │ (checkboxes for copy/reset) │                                    │
│   └──────────────┬──────────────┘                                    │
│                  ▼                                                    │
│   ┌─────────────────────────────┐                                    │
│   │ STEP 4: Review & Execute    │                                    │
│   │ (summary → confirm →        │                                    │
│   │  patch + archive + reload)  │                                    │
│   └─────────────────────────────┘                                    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Entry Points — Detailed

### 3A. From an Empty/Active Spool (Primary Flow)

**Context:** The spool is loaded in an AMS tray or visible in the filament catalog. The user knows it's empty (or nearly empty) and wants to replace it.

**Trigger Location 1 — AMS Tray Popup:**
- A new **"Replace Spool"** button appears in the AMS tray popup bottom action row.
- **Visibility condition:** Only shown when the tray has a matched spool (`match_state === 'matched'` and `spool_id` exists). This avoids showing the button for empty or unmatched trays.
- The spool context (entity, spool ID, tray, filament_id) is passed into the wizard.

> **⚠ Mid-Print Empty Tray Limitation:** When a spool runs out mid-print, the Bambu Lab integration clears the tray data (UUID, color, type all become empty/null). The `spoolman_tray_map` sensor reports `match_state: 'empty'` for that tray, so there is no spool context to pass into the wizard. The AMS tray popup **will not show the "Replace Spool" button** for an emptied-out tray. This is by design — the user should instead use the **Filament Catalog** or the **Filament Runout Notification** (see Section 3C) to initiate the replace flow.

**Trigger Location 2 — Spool Popup (Catalog):**
- A direct **"Replace / Refill Spool"** button is added to the spool popup bottom action row.
- The bottom action row order is:
  - **Replace / Refill Spool** (left-most)
  - **Open in Spoolman**
  - **Reload**
  - **Close**
- The dedicated **Location** action button is removed from this row because location editing is already handled by the **Change Location** control directly above it.
- **Always visible** on every spool popup (not conditionally hidden), since the user might want to replace any spool. The wizard's Step 1 handles validation.

### 3B. From a Sealed Spool (Reverse Flow)

**Context:** The user is browsing sealed inventory and wants to unseal a spool to put into service.

**Trigger Location — Spool Popup (Catalog) for a sealed spool:**
- A prominent **"Unseal & Use"** button appears when the spool's `extra_sealed` is `true`.
- This launches a simplified flow:
  1. **Optionally** link to an empty spool it replaces (user can pick from empty/low-weight spools of the same `filament_id`, or skip this step)
  2. Configure the new spool's metadata (spool type, clip type, desiccant, location)
  3. Mark as unsealed → commit

**Why this direction works:** Starting from a sealed spool is useful when the user has the physical spool in hand and wants to set it up — they may not know or care which spool it replaces. The "link to empty spool" step is optional, and if chosen, the old spool gets archived just like the primary flow.

### 3C. From Filament Runout Notification (Automation-Driven)

**Context:** A spool runs out mid-print. The printer pauses with stage `paused_filament_runout`. The AMS tray is now empty — its UUID, color, and type are cleared by the Bambu Lab integration, so `spoolman_tray_map` reports `match_state: 'empty'` and there is no spool context on the tray.

> **Source Code Confirmation (greghesp/ha-bambulab `models.py`):** When a tray empties, the printer sends a payload containing only `{'id', 'state'}` fields. The `AMSTray.print_update()` method detects this via `METADATA_ONLY_FIELDS = {'id', 'state'}` / `is_empty_notification` and resets ALL 19 tray fields: `empty=True`, `tray_uuid=""`, `tag_uid=""`, `color="00000000"`, `name="Empty"`, `nozzle_temp_min=0`, `nozzle_temp_max=0`, `type=""`, `sub_brands=""`, `k_value=0`, `setting_id=""`, etc. However, the active tray INDEX is still set — `tray_now` from MQTT is decoded as `ams_index = tray_now >> 2` and `tray_index = tray_now & 0x3`. So we know WHICH tray ran out, but cannot identify WHICH spool was in it from the tray data alone.

**Problem:** The user cannot launch the replace wizard from the AMS tray popup because there is no matched spool to act on. They need to find the now-empty spool in the Filament Catalog — but they may not remember which spool it was, especially in a multi-AMS multi-filament setup.

**Solution — Filament Runout Detection Automation:**

A new automation (`filament_runout_capture_and_notify`) fires when the printer enters `paused_filament_runout`. It:

1. **Snapshots the last-known spool** for the affected tray before the tray data is cleared. This is done by reading `input_text.spool_replace_last_known_tray_spool` which is kept up-to-date by the existing `active_tray_changed_update_spoolman` automation (see "Last-Known Spool Tracking" below).
2. **Creates a persistent notification** with:
   - The spool name, ID, filament name, and location
   - A clear call-to-action: *"Open the Filament Catalog to replace this spool"*
   - A direct link to the 3D Printing dashboard (`/3d-printing`)
3. **Sends a mobile notification** (same pattern as `print_fault_notification.yaml`) with an actionable link to the dashboard.
4. **Stores the empty spool ID** in `input_text.spool_replace_source_spool_id` so the user can pick up the replace wizard from the Filament Catalog with the source spool pre-selected.

**Last-Known Spool Tracking:**

A new `input_text` helper per tray (or a single JSON helper) is maintained by the existing `active_tray_changed_update_spoolman` automation. Every time a tray's spool match is resolved, the automation writes the spool ID to the helper. When the tray later goes empty (filament runout), the helper still holds the last-known spool ID.

```yaml
# Helpers — one per tray
input_text:
  spool_replace_last_known_ams_1_tray_1: { name: "Last Known Spool — AMS 1 Tray 1", max: 10 }
  spool_replace_last_known_ams_1_tray_2: { name: "Last Known Spool — AMS 1 Tray 2", max: 10 }
  spool_replace_last_known_ams_1_tray_3: { name: "Last Known Spool — AMS 1 Tray 3", max: 10 }
  spool_replace_last_known_ams_1_tray_4: { name: "Last Known Spool — AMS 1 Tray 4", max: 10 }
  spool_replace_last_known_ams_2_tray_1: { name: "Last Known Spool — AMS 2 Tray 1", max: 10 }
  spool_replace_last_known_ams_2_tray_2: { name: "Last Known Spool — AMS 2 Tray 2", max: 10 }
  spool_replace_last_known_ams_2_tray_3: { name: "Last Known Spool — AMS 2 Tray 3", max: 10 }
  spool_replace_last_known_ams_2_tray_4: { name: "Last Known Spool — AMS 2 Tray 4", max: 10 }
  spool_replace_last_known_external_spool: { name: "Last Known Spool — External", max: 10 }
```

**Alternative — Simpler single-helper approach:** Instead of per-tray helpers, use the existing `active_tray` sensor to determine *which* tray ran out. The `active_tray` sensor (`sensor.ntk_ryansoffice_3dprinter_active_tray`) reports the last active tray. At the moment of `paused_filament_runout`, this tells us which tray was in use. Combined with the `print_started-capture_print_data` automation's tray snapshot (which stores the full tray→spool mapping at print start in `input_text.print_weight_backup`), the runout automation can look up the spool ID from the backup data without needing per-tray helpers.

**Recommended approach:** Use the `print_weight_backup` JSON (already captured at print start) to resolve the last-known spool for the active tray at runout time. This avoids adding 9 new helpers and leverages existing infrastructure.

**Trigger:** `sensor.ntk_ryansoffice_3dprinter_current_stage` transitions to `paused_filament_runout`

**Persistent Notification Example:**
```
♻ Filament Runout — Spool #42

Bambu Lab PLA Basic White ran out on AMS 1 Tray 2 during "Benchy v3".

Open the Filament Catalog to find and replace this spool.

[Open 3D Printing Dashboard →]
```

**Catalog Pre-Selection:** When the user opens the Filament Catalog, the replace wizard can check `input_text.spool_replace_source_spool_id`. If populated, the catalog could show a banner: *"Spool #42 ran out. Tap to start the replace wizard."* — or the notification link could include a query parameter / input_text flag that auto-opens the replace wizard for that spool.

### 3D. From the NFC Filament Tag View (Mobile)

**Context:** The user scans a filament NFC tag on their iPhone (e.g., the tag on the AMS tray itself) and the Filament Tag dashboard view loads. The `sensor.selected_spool` template sensor resolves the scanned `filament_id` to the matching **unsealed** spool entity. The user sees the spool info and realizes it's empty — they want to start a replacement.

**Trigger Location — "Replace / Refill Spool" button in `view_filament_tags.yaml`:**
- A new button is added to the **"Other Actions"** section of the filament tags view.
- **Visibility:** Only shown when `sensor.selected_spool` has resolved to a valid spool entity.
- The button writes the spool ID to `input_text.spool_replace_source_spool_id` and opens the Step 1 wizard popup via `browser_mod.popup`.

**Why this entry point matters:** The NFC scan flow is the most natural mobile interaction for a user standing in front of their 3D printer. They physically scan the tag → see the spool info → realize it's empty → tap "Replace" — all without navigating through the Filament Catalog or AMS popups. Unlike the AMS tray popup entry point (3A), this works even when the tray is already empty (the tag identifies the filament, not the tray), making it ideal for the post-runout scenario.

**Implementation:** The button calls `script.spool_replace_populate_candidates` (same as all other entry points) and then opens the wizard popup chain. Since the filament tag view is a full dashboard view (not a popup), the browser_mod popup opens on top of it — identical behavior to popups in the catalog view.

---

## 4. Wizard Steps — Detailed Specification

### Step 1: Validate the Empty Spool

**Inputs:** `source_spool_entity_id` (the spool being replaced)

**Logic:**
1. Read `remaining_weight` from the source spool entity.
2. **If `remaining_weight > 0`:**
   - Display a **warning banner** (orange/amber):
     > "This spool still shows {X}g remaining. Are you sure it's empty?"
   - Two buttons: **"Yes, It's Empty — Continue"** and **"Cancel"**
   - If the user continues, the workflow will reset `remaining_weight` to `0` on the source spool before archiving (Step 4).
3. **If `remaining_weight < 0`:**
   - This can happen when the usage automation over-deducts. Display an **info banner** (blue):
     > "This spool shows {X}g (negative). Weight will be reset to 0g before archiving."
   - The workflow will reset `remaining_weight` to `0` on the source spool before archiving.
4. **If `remaining_weight === 0` or `null`:**
   - No warning needed; proceed directly to Step 2.

**Output:** Validated source spool; decision to continue.

### Step 2: Select Replacement Spool

**Inputs:** `filament_id` from the source spool

**Display:**
- Title: *"Select a replacement spool"*
- Subtitle: *"Showing sealed spools of {filament_name} ({vendor})"*
- List all spools matching:
  - `filament_id` equals the source spool's `filament_id`
  - `extra_sealed` is `true`
  - `archived` is NOT `true`
- For each candidate, show:
  - Spool name & ID
  - Location (so the user knows where to grab it physically)
  - Color swatch
  - Initial weight
  - Purchase date (if available)
- If **zero candidates** are found:
  - Display a warning banner (orange background, black text): *"No sealed replacement spools found for this filament. You can archive the empty spool directly — this will set its weight to 0 and archive it in Spoolman."*
  - The **"Continue to Step 3"** button transforms into an **"Archive Empty Spool"** button (red background, `mdi:archive-arrow-down` icon).
  - Clicking **"Archive Empty Spool"** directly calls `spoolman.patch_spool` to set `remaining_weight: 0` and `archived: true` on the source spool, then closes the popup. This bypasses Steps 3–4 entirely.
  - **"Cancel"** remains active.
  - This prevents the user from advancing through Steps 3–4 with an invalid target spool while still offering a useful action.

**Implementation approach — Candidate Discovery:**

Because the popup runs as browser_mod JS inside a button-card template, the candidate list must be computed from entities already loaded in the HA frontend. The approach:

1. Use `sensor.spoolman_filament_totals` attribute `totals[filament_id].spools[]` to get all spools of the same filament.
2. For each candidate `spool.entity_id`, read `states[entity_id].attributes.extra_sealed` to filter for sealed-only.
3. This avoids any REST call and uses the same pattern as the existing "Other spools of same filament" section in the popup.

**Selection mechanism:**
- Since browser_mod popups can't easily do interactive list selection with state persistence, the recommended approach is:
  - Use an **`input_select` helper** (`input_select.spool_replace_target_spool`) that gets dynamically populated via a script before the popup opens.
  - The script reads sealed spools of the same filament_id and builds the options list as `"#{id} — {name} — {location}"` strings.
  - A `mushroom-select-card` in the popup lets the user pick from this dropdown.
  - A companion `input_text.spool_replace_target_spool_id` stores just the numeric ID (set by an automation triggered on the input_select change).

**Alternative approach (simpler, Phase 1):**
- Render the candidate list as read-only cards in the popup.
- Each card has a **"Select"** button that fires a `browser_mod.sequence` to:
  1. Write the selected spool ID to `input_text.spool_replace_target_spool_id`
  2. Close the current popup
  3. Open the Step 3 popup

### Step 3: Configure Transfer Options

**Inputs:** Source spool entity, target spool entity (from Step 2 selection)

**Display:**
A popup showing the source → target pairing, with checkboxes (implemented as `input_boolean` helpers) for each transfer option:

| Option | Helper Entity | Default | Behavior |
|---|---|---|---|
| Copy Spool Type | `input_boolean.spool_replace_copy_spool_type` | ON | Copy `extra_spool_type` from source → target |
| Copy Clip Type | `input_boolean.spool_replace_copy_clip_type` | ON | Copy `extra_clip_type` from source → target |
| Copy Desiccant Fill Date | `input_boolean.spool_replace_copy_desiccant_date` | OFF | Copy `extra_desiccant_filled` from source → target |
| Reset Desiccant Fill Date | `input_boolean.spool_replace_reset_desiccant_date` | ON | Set `extra_desiccant_filled` to `now()` on target |
| Copy Desiccant in Spool | `input_boolean.spool_replace_copy_desiccant_present` | ON | Copy `extra_desiccant_in_spool` from source → target |
| Replace Location | `input_boolean.spool_replace_copy_location` | ON | Set target location to source's current location |
| Mark as Used in Current Print | `input_boolean.spool_replace_mark_used` | OFF | Set `first_used` and `last_used` to `now()` on target |
| Archive Empty Spool | `input_boolean.spool_replace_archive_source` | ON | Archive the source spool in Spoolman (last step) |

**Mutual exclusion:** "Copy Desiccant Fill Date" and "Reset Desiccant Fill Date" are mutually exclusive. When one is toggled ON, the other should toggle OFF. This can be handled by an automation on the `input_boolean` state changes, or by using an `input_select` with options: `Copy from old spool` / `Reset to now` / `Skip`.

**Recommendation — Desiccant mode:** Use `input_select.spool_replace_desiccant_mode` with three options: `"Copy from old spool"`, `"Reset to today"`, `"Skip"`. This avoids mutual-exclusion complexity with booleans.

**Visual layout:** Show source spool summary (left/top) and target spool summary (right/bottom) with an arrow between them, then the checkbox options below. Use a `custom:layout-card` 2-column grid or vertical stack.

### Step 4: Review & Execute

**Display:** A confirmation popup summarizing all actions about to be taken:

```
── Summary ──────────────────────────────────
Source: Bambu Lab PLA Basic White #42 (0g remaining)
  → Will be archived

Target: Bambu Lab PLA Basic White #78 (sealed, Closet Shelf 2)
  → Unseal and set as active
  → Copy Spool Type: "Bambu Spool"
  → Copy Clip Type: "Slot Insert v2"
  → Reset desiccant fill date to today
  → Copy desiccant in spool: Yes
  → Set location to: AMS
  → Mark as used in current print (set first/last used)
─────────────────────────────────────────────
```

**Buttons:** **"Execute"** (primary) and **"Back"** / **"Cancel"**

**Execution sequence** (implemented as a HA script `script.spool_replace_execute`):

```yaml
sequence:
  # 1. Reset source spool weight to 0 if negative
  - action: spoolman.patch_spool
    data:
      id: "{{ source_spool_id }}"
      remaining_weight: 0

  # 2. Build merged extra object for target spool (read-merge-write pattern)
  #    CRITICAL: Spoolman replaces ALL extra fields on each call, so we must
  #    read existing fields, merge our changes, and write the full object back.
  - variables:
      target_current_extra: >-
        {{ state_attr('sensor.spoolman_spool_' ~ target_spool_id, 'extra') or {} }}
      target_extra_updates: >-
        {% set updates = namespace(d={}) %}
        {# Always unseal and set date_opened #}
        {% set updates.d = {'sealed': 'false', 'date_opened': now().isoformat()} %}
        {# Spool Type (if checked) #}
        {% if copy_spool_type %}
          {% set updates.d = dict(updates.d, spool_type=source_spool_type) %}
        {% endif %}
        {# Clip Type (if checked) #}
        {% if copy_clip_type %}
          {% set updates.d = dict(updates.d, clip_type=source_clip_type) %}
        {% endif %}
        {# Desiccant mode #}
        {% if desiccant_mode == 'Copy from old spool' %}
          {% set updates.d = dict(updates.d, desiccant_filled=source_desiccant_filled) %}
        {% elif desiccant_mode == 'Reset to today' %}
          {% set updates.d = dict(updates.d, desiccant_filled=now().isoformat()) %}
        {% endif %}
        {# Desiccant present (if checked) #}
        {% if copy_desiccant_present %}
          {% set updates.d = dict(updates.d, desiccant_in_spool=source_desiccant_in_spool) %}
        {% endif %}
        {{ updates.d }}
      target_merged_extra: "{{ dict(target_current_extra, **target_extra_updates) }}"

  # 3. Apply all extra field changes in a single call (avoids field loss)
  - action: spoolman.patch_spool
    data:
      id: "{{ target_spool_id }}"
      extra: "{{ target_merged_extra }}"

  # 4. Set non-extra fields on target (location, used dates)
  # 4a. Location (if checked)
  - if: "{{ copy_location }}"
    then:
      - action: spoolman.patch_spool
        data:
          id: "{{ target_spool_id }}"
          location: "{{ source_location }}"

  # 4b. Mark as used in current print (if checked)
  - if: "{{ mark_used }}"
    then:
      - action: spoolman.patch_spool
        data:
          id: "{{ target_spool_id }}"
          first_used: "{{ now().isoformat() }}"
          last_used: "{{ now().isoformat() }}"

  # 5. Archive the source spool (LAST — entity disappears from HA after this)
  - if: "{{ archive_source }}"
    then:
      - action: spoolman.patch_spool
        data:
          id: "{{ source_spool_id }}"
          archived: true

  # 6. Refresh changed entities (lightweight, no integration reload)
  - action: homeassistant.update_entity
    target:
      entity_id: "sensor.spoolman_spool_{{ target_spool_id }}"
  - action: homeassistant.update_entity
    target:
      entity_id: "sensor.spoolman_spool_{{ source_spool_id }}"

  # 7. Log the operation
  - action: system_log.write
    data:
      message: >-
        Spool Replace/Refill completed. Source spool #{{ source_spool_id }}
        ({{ 'archived' if archive_source else 'kept' }}) replaced by
        target spool #{{ target_spool_id }} (unsealed).
      level: info
      logger: homeassistant.components.bambulab.spool_replace

  - action: logbook.log
    data:
      name: Spool Replace/Refill
      message: >-
        Replaced spool #{{ source_spool_id }} with spool #{{ target_spool_id }}.
        Target unsealed and configured.
```

---

## 5. UI Implementation Strategy

### 5.1 Multi-Step Popup via browser_mod

The wizard uses **chained browser_mod popups**. Each step closes the current popup and opens the next. This is the same pattern used by the existing weight editor and pin selector — well-proven in this codebase.

**State persistence between steps** uses `input_text` and `input_boolean` helpers that are set before each popup opens.

### 5.2 Helper Entities Required

```yaml
# --- Workflow state ---
input_text:
  spool_replace_source_spool_id:
    name: "Spool Replace — Source Spool ID"
    max: 10
  spool_replace_target_spool_id:
    name: "Spool Replace — Target Spool ID"
    max: 10

# --- Transfer options ---
input_boolean:
  spool_replace_copy_spool_type:
    name: "Copy Spool Type"
    icon: mdi:package-variant
  spool_replace_copy_clip_type:
    name: "Copy Clip Type"
    icon: mdi:paperclip
  spool_replace_copy_desiccant_present:
    name: "Copy Desiccant Present"
    icon: mdi:water
  spool_replace_copy_location:
    name: "Copy Location"
    icon: mdi:map-marker
  spool_replace_mark_used:
    name: "Mark as Used in Current Print"
    icon: mdi:printer-3d-nozzle
  spool_replace_archive_source:
    name: "Archive Empty Spool"
    icon: mdi:archive

input_select:
  spool_replace_desiccant_mode:
    name: "Desiccant Fill Date Mode"
    options:
      - "Copy from old spool"
      - "Reset to today"
      - "Skip"
    icon: mdi:water-sync

  spool_replace_target_picker:
    name: "Replacement Spool Picker"
    options:
      - "No sealed spools found"
    icon: mdi:swap-horizontal
```

### 5.3 "Replace / Refill Spool" Button in Spool Popup

Added to the existing action button row in `catalog_spool_popup.yaml`:

```
[ Replace / Refill Spool ♻ ] [ Open in Spoolman ] [ Reload ] [ Close ]
```

The **Replace / Refill Spool** button launches the wizard directly (Step 1).

> **⚠ bubble-card `button_action` requirement:** When using `custom:bubble-card` with `button_type: 'name'`, the `tap_action` only fires when the **icon** is clicked. To make the **entire button** (icon + name label) clickable, the same action must also be set on `button_action.tap_action`. This applies to all bubble-card action buttons across all popups (catalog spool popup, AMS tray popup, filament tag view). See [bubble-card docs](https://github.com/Clooos/Bubble-Card) for details.

In the same popup KPI row, a new **Qty to Order** control is added to the right of **Total (all spools)**:

```
[ Remaining ] [ Cost per g ] [ Total (all spools) ] [ Qty to Order ]
```

The Qty card is vertically stacked:
- Label on top: `Qty to Order`
- Current value in the middle
- `+` and `-` buttons on the bottom row

Behavior rules:
- `+` increments `extra_purchase_qty` by 1
- `-` decrements by 1, but never below 0
- When value is `0`, `-` is disabled (non-clickable) and visually dimmed
- `+` / `-` use the same accent action styling as other popup buttons (`var(--primary-color)`, white icon/text)
- If `extra_purchase_qty` is missing on the spool, the UI treats it as `0` and still allows incrementing; the first `+` write creates/populates the field

#### Qty to Order Interaction Model (Option 1 vs Option 2)

**Option 1 (current, implemented): Write-through to Spoolman on each tap**
- Every `+` / `-` click sends a REST write to Spoolman filament `extra.purchase_qty` (string payload) immediately.
- UI correctness is anchored to backend state; if a write fails, no local-only value is shown.
- In browser_mod popup flows, the displayed value may not visually increment/decrement in-place until entity refresh (or popup reopen), even though the write succeeds.

**Option 2 (future, not implemented): Optimistic local popup state + background write**
- Clicking `+` / `-` updates a local shadow value instantly for better perceived responsiveness.
- The same backend write still occurs in the background.
- Requires explicit rollback/error handling if write fails, plus reconciliation to avoid drift between popup shadow state and real entity state.

**Design decision:** Keep Option 1 as default for reliability and simpler failure semantics. Consider Option 2 later only if faster in-popup visual feedback becomes a priority over implementation simplicity.

For sealed spools, a prominent **"Unseal & Use"** button is shown in the action row directly, replacing "Replace / Refill Spool" since the action semantics differ.

### 5.4 "Replace Spool" Button in AMS Tray Popup

Added to the AMS tray popup in `ams_tray_popup.yaml`, in the bottom action row:

```
[ Weight: 123.4g ] [ This Print: 45.2g ] [ ... ]
[ Desiccant: 12 days ] [ Mark Dried ] [ Mark Refilled ]
[ Replace Spool ♻ ] [ Open in Spoolman ] [ Reload ] [ Close ]
```

The same **Qty to Order** stacked KPI card is also added in the AMS popup KPI row to the right of **Total (all spools)**, with identical behavior:
- `+` increments `extra_purchase_qty`
- `-` decrements, clamped at `0`
- `-` is disabled when current qty is `0`
- Buttons use the popup accent action style for consistency

**Visibility:** Only shown when `match_state === 'matched'` and `spoolId` is set.

To keep the popup focused, **More Details** and **Pin/Unpin** are not included in the bottom action row design.

### 5.5 "Replace / Refill Spool" Button in NFC Filament Tag View

Added to the "Other Actions" section in `view_filament_tags.yaml`:

```
── Other Actions ──────────────────────
[ Load from Query String ]  [ Replace / Refill Spool ♻ ]  ← NEW
```

**Visibility:** Only enabled when `sensor.selected_spool` has resolved to a valid spool entity (spool_id is set). Disabled/greyed out otherwise (same pattern as the existing "Mark as Refilled" and "Mark as Dried" buttons).

**Behavior:** Writes the spool ID to `input_text.spool_replace_source_spool_id`, calls `script.spool_replace_populate_candidates`, and opens the Step 1 wizard popup via `browser_mod.popup`.

### 5.6 Mobile (iPhone) UI Assessment

The wizard is fully compatible with mobile Safari / HA Companion App on iPhone. No redesign is needed — the existing modal-based approach is mobile-friendly by default.

**Step-by-step assessment:**

| Step | UI Pattern | Mobile Compatibility | Notes |
|---|---|---|---|
| **Step 1: Validate** | Warning banner + 2 buttons | ✅ Excellent | Simple text + large tap targets. No scroll needed. |
| **Step 2: Select Replacement** | Scrollable list of spool cards | ✅ Good | Cards with "Select" buttons — natural mobile pattern. Lists scroll vertically. May need to limit visible info per card on narrow screens. |
| **Step 3: Configure Transfer** | Checkboxes (input_boolean toggles) + dropdown (input_select) | ✅ Good | Native HA toggle components render well on mobile. Single column — no side-by-side layout needed. |
| **Step 4: Review & Execute** | Summary text + Execute button | ✅ Excellent | Read-only summary, single primary button. Compact. |

**browser_mod popup behavior on mobile:**
- browser_mod renders popups as centered modals. On narrow screens (< 500px), the HA dialog overlay already fills most of the viewport width.
- The `size: normal` popup setting works fine on iPhone. No need for `size: fullscreen` or custom media queries.
- The chained popup pattern (close current → delay → open next) works identically on mobile.

**Layout recommendation for Step 3:**
The design calls for a source → target summary with an arrow. On mobile, use **vertical stack only** (source on top, arrow below, target below that). The `custom:layout-card` 2-column option mentioned in the design should be avoided — use a simple vertical stack that works on all screen widths. This is already the "(left/top)" fallback noted in the original design.

**Touch target sizing:**
All buttons in the wizard steps should maintain minimum 44×44 pt hit areas (Apple HIG). The existing button-card styles in this codebase already meet this threshold. The `input_boolean` toggle and `input_select` dropdown rendered via HA's native components also meet this.

**No adjustments needed** to the wizard steps themselves. The only implementation consideration is ensuring the Step 3 popup uses a vertical stack (not a 2-column grid) for the source/target summary, which is already the recommended layout for consistency across desktop and mobile.

---

## 6. Scripts

### 6.1 `script.spool_replace_populate_candidates`

**Purpose:** Populate `input_select.spool_replace_target_picker` with sealed spools of the same filament.

**Approach:**
- Accepts `filament_id` as input field
- Iterates `states.sensor` entities matching `sensor.spoolman_spool_*`
- Filters: `extra_sealed == true`, `archived != true`, `filament_id == target`
- Builds option list: `"#{id} — {name} — 📍 {location} — {initial_weight}g"`
- Calls `input_select.set_options` to populate the picker
- Falls back to `["No sealed spools found"]` if empty

### 6.2 `script.spool_replace_execute`

**Purpose:** Execute the full replace/refill workflow (as detailed in Step 4 above).

**Input fields:**
- `source_spool_id` (int)
- `target_spool_id` (int)
- All options read from `input_boolean` / `input_select` helpers at execution time

### 6.3 `script.spool_unseal_setup` (for reverse flow)

**Purpose:** Quick unseal without linking to an empty source spool.

**Input fields:**
- `target_spool_id` (int)
- Options from `input_boolean` helpers (subset: spool type, clip type, desiccant, location)

---

## 7. Spoolman API Considerations

### 7.1 Archiving via `spoolman.patch_spool`

**Confirmed:** The Spoolman REST API supports `PATCH /api/v1/spool/{id}` with `{ "archived": true }`. The HA Spoolman integration's `spoolman.patch_spool` service passes this field through directly — no REST command fallback is needed. Once archived, the spool entity is automatically removed from HA on the next Spoolman data refresh (the integration fetches with `allow_archived: False` by default).

```yaml
- action: spoolman.patch_spool
  data:
    id: "{{ source_spool_id }}"
    archived: true
```

> **Note:** There is no "inactive" state in Spoolman. Spools are either `archived: false` (active, default) or `archived: true` (archived, hidden from default views and HA entities). Archive is the only supported mechanism for removing spent spools from active inventory.

### 7.2 Unsealing

Setting `extra.sealed` to `false` and recording the open date via `spoolman.patch_spool`:

```yaml
- action: spoolman.patch_spool
  data:
    id: "{{ target_spool_id }}"
    extra:
      sealed: false
      date_opened: "{{ now().isoformat() }}"
```

The `date_opened` extra field already exists in Spoolman (type: Text, stores ISO 8601 datetime). The workflow sets it automatically when unsealing a spool.

### 7.3 Entity Refresh (NOT Integration Reload)

After patching spools, refresh the changed entities so HA picks up the new state:

```yaml
- action: homeassistant.update_entity
  target:
    entity_id: "sensor.spoolman_spool_{{ target_spool_id }}"
- action: homeassistant.update_entity
  target:
    entity_id: "sensor.spoolman_spool_{{ source_spool_id }}"
```

> **ANTIPATTERN — DO NOT USE `homeassistant.reload_config_entry`.**
> Reloading the entire Spoolman integration (`homeassistant.reload_config_entry`) tears down and reinitializes all spool sensors, websockets, and coordinator state. On resource-constrained hosts (e.g., Raspberry Pi), this causes extreme RAM spikes and can trigger OOM kills or full system reboots. Always use `homeassistant.update_entity` on specific spool entities instead.

### 7.4 Extra Field Merge Requirement (CRITICAL)

The Spoolman REST API uses **full replacement semantics** for the `extra` field: *"If extra is set, all existing extra fields will be removed and replaced with the new ones."* This means any `spoolman.patch_spool` call that includes `extra` must contain the **complete** extra object — not just the fields being changed — or existing fields will be deleted.

**Required pattern — read-merge-write:**

```yaml
# ❌ WRONG — overwrites all extra fields with just sealed + date_opened
- action: spoolman.patch_spool
  data:
    id: "{{ target_spool_id }}"
    extra:
      sealed: false
      date_opened: "{{ now().isoformat() }}"

# ✅ CORRECT — reads existing extra, merges changes, writes full object
# In the execution script, build a merged extra dict in a template:
- variables:
    target_extra: >-
      {% set current = state_attr('sensor.spoolman_spool_' ~ target_spool_id, 'extra') or {} %}
      {% set updates = {
        'sealed': 'false',
        'date_opened': now().isoformat()
      } %}
      {{ dict(current, **updates) }}
- action: spoolman.patch_spool
  data:
    id: "{{ target_spool_id }}"
    extra: "{{ target_extra }}"
```

**Impact on execution script:** All extra field updates in `script.spool_replace_execute` must be consolidated into a single `spoolman.patch_spool` call per spool with the full merged extra object. See the updated execution sequence in Section 4, Step 4.

| Scenario | Handling |
|---|---|
| **No sealed spools available** | Step 2 shows message + link to Spoolman. User cannot proceed. |
| **Source spool still has weight** | Step 1 warning. If user continues, weight reset to 0 at execution. |
| **Source spool has negative weight** | Info banner. Weight reset to 0 at execution. |
| **User cancels mid-wizard** | All state in `input_text`/`input_boolean` helpers is ephemeral — no cleanup needed. No Spoolman changes until Step 4's "Execute" is pressed. |
| **`spoolman.patch_spool` `archived` field** | ✅ Confirmed working. No fallback needed. Archived spools automatically disappear from HA entities. |
| **Extra field overwrites on partial update** | Spoolman uses full-replacement semantics for `extra`. The execution script uses read-merge-write pattern (see Section 7.4) to prevent field loss. |
| **Spoolman integration reload fails** | Log warning. User can manually reload via Developer Tools or the nightly reload automation will catch it. |
| **Multiple users trigger simultaneously** | Helpers are global singleton state. For a single-user home setup this is acceptable. If needed, prefix helpers with a session ID, but this adds significant complexity. |
| **Target spool was already unsealed by another process** | Wizard should re-check `extra_sealed` at execution time and warn if no longer sealed. Still allow proceed (idempotent unseal). |
| **Print in progress when replacing** | The "Mark as Used in Current Print" checkbox handles this. The `active_tray_changed` automation already tracks last_used; this checkbox sets `first_used` for a brand-new spool that hasn't triggered that automation yet. |
| **Spool runs out mid-print (tray goes empty)** | AMS tray popup won't show Replace button (no spool context). User is guided via persistent notification (Phase 3) or manually navigates to the Filament Catalog. The runout automation captures the last-known spool ID so the wizard can be pre-populated. |

---

## 9. Phased Implementation Plan

### Phase 1: Core Replace Flow (MVP)

**Scope:** End-to-end replace wizard from the spool popup (catalog).

**Deliverables:**
1. Helper entities (input_text, input_boolean, input_select)
2. `script.spool_replace_populate_candidates`
3. `script.spool_replace_execute` (with read-merge-write pattern for extra fields)
4. "Replace / Refill Spool" button in `catalog_spool_popup.yaml` (left-most in bottom action row)
5. "Qty to Order" stacked KPI card with `+` / `-` controls in both `catalog_spool_popup.yaml` and `ams_tray_popup.yaml`
6. Step 1–4 popup chain (browser_mod popups)

**Validation:**
- Test with a spool at 0g remaining → select sealed replacement → execute
- Test with a spool at 50g remaining → verify warning → continue → verify weight reset
- Test with negative weight spool → verify info banner → verify weight reset
- Test with no sealed candidates → verify empty-state message

### Phase 2: AMS Tray Popup + NFC Filament Tag View Integration

**Scope:** Add "Replace Spool" button to the AMS tray popup and "Replace / Refill Spool" button to the NFC filament tag view.

**Deliverables:**
1. "Replace Spool" button in `ams_tray_popup.yaml` action area
2. Context passing: tray → spool entity → wizard entry
3. Conditional visibility: only when `match_state === 'matched'` (no button on empty trays)
4. "Replace / Refill Spool" button in `view_filament_tags.yaml` "Other Actions" section
5. Button wiring: write spool ID → populate candidates → open Step 1 popup
6. Conditional enable: only when `sensor.selected_spool` resolves to valid spool entity
7. Mobile testing on iPhone (HA Companion App and mobile Safari)

**Notes:** The AMS popup already has the spool context (`spoolEntityId`, `spoolId`, `filamentId`) so wiring it into the same wizard is straightforward. For empty trays (mid-print runout), the user is directed to the Filament Catalog via the Phase 3 notification — the AMS popup deliberately does not try to reconstruct stale spool context.

### Phase 3: Filament Runout Detection & Notification

**Scope:** Detect mid-print spool runout and notify the user with an actionable link to the replace wizard.

**Deliverables:**
1. Automation `filament_runout_capture_and_notify` — triggers on `paused_filament_runout`, resolves last-known spool from `print_weight_backup`, creates persistent + mobile notification
2. Modification to `active_tray_changed_update_spoolman` — write spool ID to `input_text.spool_replace_source_spool_id` at runout detection (or publish as separate automation)
3. Optional: Filament Catalog banner that detects a pending spool replacement and offers one-tap wizard entry

**Notes:** This phase addresses the critical gap where the AMS tray loses spool context at runout. The persistent notification is the primary user-facing signal. The spool can still be found and acted on in the Filament Catalog even without the notification.

The NFC filament tag view entry point is the most natural mobile path for a user standing at their printer. The `sensor.selected_spool` template sensor resolves the scanned `filament_id` to the matching unsealed spool — this provides the source spool context even when the AMS tray is empty (the NFC tag identifies the filament, not the tray state). The wizard popups open on top of the filament tag dashboard view via `browser_mod.popup`, reusing the same Step 1–4 popup chain.

### Phase 4: Reverse Flow (Sealed → Unseal & Use)

**Scope:** "Unseal & Use" button on sealed spools in the catalog.

**Deliverables:**
1. `script.spool_unseal_setup` (simplified execution without source spool)
2. "Unseal & Use" button (conditional on `extra_sealed === true`) in spool popup
3. Optional step to link an empty spool for archiving
4. Set existing Spoolman `date_opened` field on unseal

### Phase 5: Enhancements

**Potential additions:**
- **Toast notifications** after execution (via `browser_mod.notification`)
- **Undo** capability (un-archive source spool within a timeout window)
- **Spool type / clip type picker** instead of copy-only (for cases where the new spool has a different physical format)
- **Batch replace** for multi-material prints where multiple spools ran out
- **Auto-open wizard** from notification deep link (set a flag in `input_text` that the catalog view detects and auto-triggers the popup)

---

## 10. Alternative Approaches Considered

### A. Script-only (no wizard UI)

Run a single script with all parameters passed as fields. Simpler but requires the user to know spool IDs and manually toggle settings — defeats the purpose of a guided workflow.

**Verdict:** Rejected for user-facing flow; the execution script itself is reusable for automation-triggered replacements.

### B. Automation-triggered (automatic spool swap detection)

When the AMS detects a new spool UUID in a tray that previously held a different spool, automatically trigger the replace flow. 

**Verdict:** Deferred to Phase 5. The AMS reports UUID changes via the Bambu Lab integration, but auto-replacement without user confirmation risks data loss (wrong spool matched, accidental archive). Better as a *suggested action* notification: "It looks like you swapped tray 2. Would you like to run the replace wizard?"

### E. AMS tray popup with stale/cached spool context

When a tray goes empty after filament runout, keep the last-known spool context visible in the AMS tray popup so the user can still launch the replace wizard from there.

**Verdict:** Rejected. The AMS tray popup's data comes from `spoolman_tray_map` which correctly reports `match_state: 'empty'` once the Bambu Lab integration clears the tray. Showing stale data in the tray popup would be misleading — the tray *is* empty. Instead, the Filament Runout Notification (Phase 3) guides the user to the correct spool in the Filament Catalog, which always has the full spool context.

### C. Dedicated dashboard view instead of popup wizard

A full dashboard tab for spool management with side-by-side source/target selection.

**Verdict:** Over-engineered for a single-user setup. The popup wizard aligns with existing UX patterns and keeps the action contextual to the spool being replaced.

### D. Spoolman webhook / event-driven

Use Spoolman's webhook feature to detect spool changes server-side and push updates to HA.

**Verdict:** Spoolman doesn't currently emit webhooks for spool field changes. Would require Spoolman-side development. Not viable.

---

## 11. File Layout (Proposed)

```
homeassistant/packages/3d_printing/spoolman_sync/
├── scripts/
│   ├── spool_replace_populate_candidates-script.yaml    # Phase 1
│   ├── spool_replace_execute-script.yaml                # Phase 1
│   └── spool_unseal_setup-script.yaml                   # Phase 4
├── automations/
│   └── (existing automations unchanged)
├── helpers/
│   ├── input_boolean/
│   │   ├── spool_replace_copy_spool_type.yaml           # Phase 1
│   │   ├── spool_replace_copy_clip_type.yaml            # Phase 1
│   │   ├── spool_replace_copy_desiccant_present.yaml    # Phase 1
│   │   ├── spool_replace_copy_location.yaml             # Phase 1
│   │   ├── spool_replace_mark_used.yaml                 # Phase 1
│   │   └── spool_replace_archive_source.yaml            # Phase 1
│   ├── input_select/
│   │   ├── spool_replace_desiccant_mode.yaml            # Phase 1
│   │   └── spool_replace_target_picker.yaml             # Phase 1
│   └── input_text/
│       ├── spool_replace_source_spool_id.yaml           # Phase 1
│       └── spool_replace_target_spool_id.yaml           # Phase 1

homeassistant/packages/3d_printing/spoolman_sync/
├── automations/
│   └── filament_runout_capture_and_notify.yaml           # Phase 3

homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/
├── catalog_spool_popup.yaml                             # Modified: Phase 1
├── ams_tray_popup.yaml                                  # Modified: Phase 2

homeassistant/packages/3d_printing/common/dashboard_views/
├── view_filament_tags.yaml                              # Modified: Phase 2

docs/features/spoolman_sync/
├── spool-replace-refill-design.md                       # This document
```

---

## 12. Spoolman Custom Field (Existing)

The workflow uses the existing `date_opened` extra field already defined in Spoolman:

| Field Key | Type | Description |
|---|---|---|
| `date_opened` | Text | ISO 8601 datetime when the spool was first opened/unsealed. Set automatically by the replace/unseal workflow. |

This field is set to `now()` whenever a spool is unsealed (both the replace flow and the standalone unseal flow). It enables inventory analytics: time-to-use from purchase, shelf life tracking, etc.

> **Note:** The `date_opened` field is exposed on spool entities as `extra_date_opened`.

---

## 13. Impact on Existing Automations

| Automation / Sensor | Impact |
|---|---|
| `sensor.spoolman_tray_map` | **No change.** Already excludes sealed spools and archived spools. After the workflow unseals a spool and archives the old one, tray_map will naturally pick up the new spool on next evaluation. |
| `active_tray_changed_update_spoolman` | **No change.** Will detect the new spool in the tray (if UUID differs) and update `last_used`. |
| `clear_manual_spool_override_on_tray_change` | **No change.** If the user physically swaps the spool, any pin override will be cleared. |
| `print_complete-update_filament_usage` | **No change.** Uses tray_map to resolve active spool; the new spool will be resolved correctly. |
| `filament_catalog_filter` | **No change.** Already filters by `sealed` and `archived` status. The new spool will appear as unsealed; the old spool will be excluded as archived. |
| `filament_catalog_metrics` | **No change.** Already skips archived spools in all metrics. |
| `sensor.selected_spool` (filament tag) | **No change.** Template sensor resolves `filament_id` to the matching unsealed spool. After replace, the new unsealed spool will be resolved correctly. The archived old spool (no longer an entity) will be naturally excluded. |
| `view_filament_tags.yaml` | **Modified (Phase 2).** New "Replace / Refill Spool" button added to "Other Actions" section. Uses the same wizard popup chain as all other entry points. |

---

## 14. Resolved Questions

> All questions from the design phase have been researched and resolved. Findings are based on source code review of Spoolman REST API v1, the HA Spoolman integration (`Disane87/spoolman-homeassistant`), and the Bambu Lab HA integration (`greghesp/ha-bambulab`).

1. **Does `spoolman.patch_spool` support `archived: true`?**
   **YES — Confirmed.** The Spoolman REST API accepts `archived: boolean (Default: false)` on `PATCH /api/v1/spool/{id}`. The HA Spoolman integration's `services.yaml` lists `archived` as a supported field, and the handler in `__init__.py` passes all fields (except `id`) through to the API verbatim: `data = {key: call.data[key] for key in call.data if key != 'id'}`. No REST command fallback is needed. Additionally, `async_get_data()` uses `{"allow_archived": False}` — once archived, the spool entity automatically disappears from HA.

2. **Batch `spoolman.patch_spool` calls — extra field replacement behavior:**
   **CRITICAL — Full replacement semantics.** The Spoolman API docs state: *"If extra is set, all existing extra fields will be removed and replaced with the new ones."* This means each `spoolman.patch_spool` call that includes `extra` must send the **complete** extra object — not just the fields being changed. The execution script must read all existing extra fields, merge the desired changes, then write the full object back in a single call. See Section 7.4 for the required read-merge-write pattern. This supersedes the earlier assumption of additive merge behavior.

3. **Spool Type / Clip Type picker values:**
   **Copy-only for Phase 1.** Values are copied from the source spool's `extra_spool_type` and `extra_clip_type`. A standalone picker with dynamically derived options is deferred to Phase 5.

4. **"Mark as Used in Current Print" behavior:**
   **Harmless duplication — documented.** The `active_tray_changed` automation may fire shortly after the physical spool swap, double-setting `last_used`. This is idempotent (timestamp update) and causes no data issues.

5. **Filament runout tray identification:**
   **Active tray INDEX is available but tray DATA is wiped.** Source code review of `AMSTray.print_update()` in the Bambu Lab integration confirms: when the printer sends a payload with only `{'id', 'state'}` fields (the `is_empty_notification` check), ALL tray data is reset — `empty=True`, `tray_uuid=""`, `tag_uid=""`, `color="00000000"`, `name="Empty"`, etc. (19 fields cleared). However, the active AMS/tray index derived from `tray_now` (`ams_index = tray_now >> 2`, `tray_index = tray_now & 0x3`) is still set — so we know WHICH tray ran out, but cannot identify WHICH spool was in it from the tray data alone. **The `print_weight_backup` JSON approach (already captured at print start) is the correct and necessary strategy** for resolving the last-known spool at runout time. See Section 3C.

6. **Multi-spool runout:**
   **Exceptionally rare — handled by existing workflow.** In the unlikely event multiple spools run out in the same print, each runout triggers the printer to pause at `paused_filament_runout`. The user resolves one at a time, resuming the print between each. The single-value `spool_replace_source_spool_id` helper is sufficient. No queue mechanism needed.
