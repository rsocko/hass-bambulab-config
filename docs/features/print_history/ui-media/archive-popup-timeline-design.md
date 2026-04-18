# Archive Popup Timeline Design (Issue #868)

## Purpose

Add a durable per-archive intermediate event timeline to the Variant 3 print-history store and render it inside the archive popup timeline track.

This issue is not just a UI polish pass. The popup timeline depends on a first-class local event ledger so the UI can show real mid-print and post-print workflow events without scraping logs or overloading archive-core fields.

## Goals

1. persist intermediate timeline events per archive in the Variant 3 local store
2. expose those rows through archive detail hydration only
3. render intermediate timeline dots in the popup relative to their event time
4. keep hover text limited to event label plus formatted date/time
5. make close events individually visible even when exact positions would overlap

## Non-Goals

1. do not widen the base browser page payload with timeline rows
2. do not store popup wording, tooltip strings, or legend labels in Layer 1
3. do not persist this timeline back to Bambuddy by hiding it inside `notes`, `tags`, or other archive-core fields
4. do not duplicate the archive's canonical start or terminal timestamps inside the local ledger
5. do not fabricate extra display-only events beyond the durable event types captured by the store

## Ownership Boundary

The event timeline is a Variant 3 local-store concern.

Why:

- Bambuddy currently owns archive-core metadata, not a first-class event ledger
- several required events are HA-local workflow actions rather than Bambuddy-native archive fields
- the popup timeline is a detail consumer and should not force a larger shared archive payload

The correct split for this issue is:

- Bambuddy remains authoritative for archive-core fields
- Home Assistant Variant 3 store owns local timeline rows, review state, and repair provenance
- popup detail hydration joins those sources into a compact archive-detail response

If Bambuddy later gains a native archive-event resource, the persistence boundary can be revisited. That is not required for this issue.

## Event Types

Initial supported event types:

- `print_paused`
- `print_resumed`
- `photo_captured`
- `enrichment_applied`
- `repair_applied`

## Event Sources

Preferred sources in priority order:

1. verified native `bambu_lab` device signals for pause/resume when the current archive binding is already known
2. integration service calls from HA automations/scripts for local workflow events such as enrichment, repair, and photo capture
3. minimal derived backfill for historical rows only when needed, explicitly marked in `derived_from`

Guardrail:

- do not synthesize pause/resume from coarse status snapshots unless a trustworthy event source is unavailable and the repo explicitly approves that fallback later

## Storage Contract

Timeline rows live in a dedicated `archive_event_timeline` table inside the Variant 3 SQLite store.

Recommended logical row shape:

| Field | Notes |
|---|---|
| `archive_id` | archive foreign key |
| `event_type` | normalized event identifier |
| `event_time` | ISO timestamp |
| `event_source` | `bambuddy_webhook`, `bambu_lab`, `ha_script`, `ha_service`, etc. |
| `event_status` | optional normalized archive-status snapshot |
| `payload_json` | compact supporting context only |
| `derived_from` | filled only when event was inferred or backfilled |
| `event_key` | idempotence key used to suppress duplicates |

Rules:

- timeline writes must be append-oriented and idempotent
- repeated webhook delivery or repeated HA automation runs must not duplicate rows
- `replace_archives()` must preserve timeline rows for archives that still exist locally
- historical backfill rows must be clearly marked in `derived_from`

## Detail Hydration Contract

Timeline rows belong in archive detail hydration, not the base browser query payload.

The popup-facing DTO should be compact and normalized. Recommended shape:

```json
[
  {
    "type": "print_paused",
    "time": "2026-04-10T14:22:10Z",
    "source": "bambu_lab",
    "status": "paused",
    "label": "Print paused",
    "color_key": "pause"
  }
]
```

The detail response may keep raw provenance fields if useful for future diagnostics, but the popup should not need to reconstruct labels or colors from unstructured payload blobs.

## Popup Rendering Rules

### Timeline track

The existing popup track already shows start and end anchors. This issue extends that same track with intermediate event dots.

Base behavior:

1. start dot remains fixed at the left edge using the archive's canonical start time
2. end dot remains fixed at the right edge using the archive's canonical end time when present
3. intermediate event dots render between them based on relative event time

### Relative positioning

For events between the canonical start and end:

$$
position\_pct = \frac{event\_time - start\_time}{end\_time - start\_time} \times 100
$$

If end time is unavailable, fallback options are:

1. use the latest known event time as the temporary right boundary
2. if only one point exists, render just the start dot and omit intermediate placements

### Out-of-range events

Events may legitimately exist outside the canonical print window, especially when local workflow actions such as manual enrichment are recorded after the archive's terminal timestamp or when imported/repaired data surfaces an earlier pre-start event.

Rendering rule:

1. do not clamp those events onto the solid start-to-end segment
2. render one collapsed overflow dot before the start anchor for all pre-start events
3. render one collapsed overflow dot after the end anchor for all post-end events
4. connect each overflow dot back to the nearest anchor with a short dotted segment so the overflow remains visible without stretching the main track
5. the hover for an overflow dot must list every collapsed event with label plus formatted date/time

This keeps the canonical archive window visually honest while still preserving access to the full event audit trail.

### Anti-overlap rule

Timeline accuracy should remain approximate when events cluster tightly.

Rendering rule:

1. sort events chronologically
2. compute raw percentage positions
3. enforce a minimum visual gap between neighboring dots
4. nudge later dots slightly left or right within a small tolerance so each dot stays visible

The goal is readability over perfect pixel accuracy.

### Hover behavior

Visible inline text must remain minimal.

Allowed hover content:

- formatted date/time
- event label
- for overflow dots, a short summary line plus one line per collapsed event containing label and formatted date/time

Not allowed inline in the default popup body:

- verbose event details
- payload dumps
- multi-line provenance explanations attached to every dot

### Legend behavior

The popup should use a single hoverable info icon rather than an always-visible legend row.

On hover, the legend explains the color mapping only.

## Color Mapping

Recommended first-pass color keys:

| Color key | Event types |
|---|---|
| `pause` | `print_paused` |
| `resume` | `print_resumed` |
| `success` | `enrichment_applied` |
| `media` | `photo_captured` |
| `repair` | `repair_applied` |

Final palette should stay consistent with the popup's current status colors and remain distinguishable on the existing popup background.

## Layering Guardrails

This issue must preserve the existing three-layer contract.

- Layer 1: compact archive projection remains lean and does not gain a serialized event timeline
- Layer 2: archive detail hydration and integration query helpers can normalize event DTOs
- Layer 3: popup-specific layout, legend hover text, and overlap nudging remain presentation logic

Do not push popup-only legend labels or tooltip strings into the mirrored archive payload to simplify frontend rendering.

## Verification

Required validation:

1. timeline rows survive archive refreshes and schema migrations
2. duplicate event deliveries do not create duplicate dots
3. popup detail includes timeline rows while page query payload remains unchanged
4. dense event clusters remain individually visible
5. start-only and no-terminal archives still render cleanly without requiring duplicated ledger anchors
6. hover content remains limited to date/time plus label
7. pre-start and post-end events render as collapsed overflow dots with dotted connectors instead of being visually clamped inside the canonical window