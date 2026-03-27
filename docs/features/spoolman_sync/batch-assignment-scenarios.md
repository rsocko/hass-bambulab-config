# Batch Assignment & Multi-Spool Queue Scenarios

> How the tray assignment system handles concurrent and batched spool events.

## Architecture

Three independent queue-backed subsystems, each with its own UI chip:

| # | Subsystem | Storage | Sensor | Chip Color | When Visible |
|---|-----------|---------|--------|------------|--------------|
| 1 | **Pending Tray Selection** | `input_text.pending_tray_selections_queue` | `sensor.pending_tray_selection_queue` | Orange | Spools need manual tray pick |
| 2 | **Deferred Queue** | `input_text.deferred_tray_assignments_queue` | `sensor.deferred_tray_assignment_queue` | Amber | Printer was busy, retrying later |
| 3 | **Informational Status** | `sensor.last_tray_assignment_result` | (same) | Varies | Last event outcome (success/fail/skip) |

Queue storage is compact JSON in `input_text` helpers (max 255 chars):
- Pending tray: `[{"s": <spool_id>}]`
- Deferred: `[{"s": <spool_id>, "t": <tray_code>}]` where tray_code = `AMS_unit * 10 + tray_slot` (e.g. 11 = AMS 1 Tray 1, 0 = External)

## Scenarios

### 1. Single spool scanned — tray resolved automatically

| Step | What happens |
|------|--------------|
| User scans spool NFC tag | Automation fires `spool_location_change_assign_tray` |
| Tray found via location match | `assign_spool_to_printer_tray` called with tray entity |
| Printer idle | Assignment succeeds immediately |
| **User sees** | Green chip: "Spool Name → AMS 1 Tray 2" |

### 2. Single spool scanned — no tray match (manual pick needed)

| Step | What happens |
|------|--------------|
| User scans spool NFC tag | Automation fires |
| No matching tray found | Spool appended to `pending_tray_selections_queue` |
| **User sees** | Orange chip: "Spool Name — tap to select tray" |
| User taps chip | Popup: spool info + AMS tray grid |
| User taps tray button | `assign_pending_spool_to_tray` reads first from queue, assigns, pops |

### 3. Multiple spools scanned rapidly — all need tray pick

| Step | What happens |
|------|--------------|
| User scans spool A, B, C in quick succession | Each fires separate automation instance (`mode: parallel`) |
| No tray matches for any | Each appends to `pending_tray_selections_queue` (dedup by spool_id) |
| **User sees** | Orange chip: "Spool A + 2 more — tap to select tray" |
| User taps chip | Popup shows Spool A info + "Spool 1 of 3 — which tray?" |
| User picks tray for A | A assigned & popped; chip updates to show Spool B (1 of 2) |
| Repeat for B, C | Queue drains to empty, chip disappears |

### 4. Multiple spools scanned — printer busy

| Step | What happens |
|------|--------------|
| Spools A, B, C scanned; trays resolved | Each calls `assign_spool_to_printer_tray` |
| Printer printing → `print_status` not idle | Each assignment appended to `deferred_tray_assignments_queue` (dedup) |
| **User sees** | Amber chip: "3 assignments deferred" |
| Print finishes | `auto_retry_deferred_tray_assignments` triggers after 10s settle |
| `retry_all_deferred_tray_assignments` processes queue FIFO | Each popped → assigned → 5s delay → next |
| All succeed | Deferred chip disappears; green info chip shows last result |

### 5. Mixed: some auto-resolve, some need tray pick, printer busy

| Step | What happens |
|------|--------------|
| Spools A (tray known, busy), B (no tray), C (tray known, busy) | A: deferred; B: pending tray; C: deferred |
| **User sees** | Orange chip (1 pending) + Amber chip (2 deferred) — both visible simultaneously |
| User picks tray for B | If printer still busy → B also deferred. If idle → B assigned immediately. |
| Printer finishes | Auto-retry processes A, C (and B if it was deferred) |

### 6. Spool scanned while deferred queue draining

| Step | What happens |
|------|--------------|
| `retry_all` processing queue; user scans new spool D | `assign_spool_to_printer_tray` runs (mode: queued), serializes after current retry |
| If printer still idle | D assigned immediately |
| If printer became busy again | D appended to deferred queue; `retry_all` loop detects busy, stops |

### 7. Duplicate spool scanned

| Step | What happens |
|------|--------------|
| Spool A already in pending/deferred queue; user scans A again | Dedup check: spool_id already present → skip append |
| **User sees** | No change to queue count |

### 8. Cancel all

| Step | What happens |
|------|--------------|
| User taps Cancel on any chip popup | `cancel_pending_tray_assignment` clears **all** queues + legacy helper |
| **User sees** | All chips disappear |

## Concurrency Model

```
Automation: mode: parallel, max: 150
  └─ Each spool event resolves variables independently
     └─ Calls assign script: mode: queued
        └─ Operations serialize through script engine
           └─ Queue reads/writes are atomic per script run
```

Key guarantee: template evaluation in the automation happens in parallel (fast), but `input_text.set_value` calls in the assign script are serialized by HA's script queuing mode. This prevents two events from reading the same queue state and both appending.

## Queue Format Reference

### Pending Tray Selections

```json
[{"s": 42}, {"s": 108}]
```
- `s`: Spoolman spool ID (integer)
- FIFO order: first scanned = first shown in picker
- Max ~12 items in 255 chars

### Deferred Assignments

```json
[{"s": 42, "t": 11}, {"s": 108, "t": 24}]
```
- `s`: Spoolman spool ID (integer)
- `t`: Tray code — `AMS_unit * 10 + tray_slot` (e.g. 11 = AMS1T1, 24 = AMS2T4, 0 = External)
- Max ~8 items in 255 chars (covers all AMS slots)
