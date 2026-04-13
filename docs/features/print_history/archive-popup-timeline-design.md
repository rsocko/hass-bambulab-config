# Archive Popup Timeline Design (Issue #868)

## Purpose

Add a durable per-archive event timeline to the Variant 3 print-history store and render it inside the archive popup timeline track.

This issue is not just a UI polish pass. The popup timeline depends on a first-class local event ledger so the UI can show real lifecycle and workflow events without scraping logs or overloading archive-core fields.

## Goals

1. persist timeline events per archive in the Variant 3 local store
2. expose those rows through archive detail hydration only
3. render intermediate timeline dots in the popup relative to their event time
4. keep hover text limited to event label plus formatted date/time
5. make close events individually visible even when exact positions would overlap

## Non-Goals

1. do not widen the base browser page payload with timeline rows
2. do not store popup wording, tooltip strings, or legend labels in Layer 1
3. do not persist this timeline back to Bambuddy by hiding it inside `notes`, `tags`, or other archive-core fields
4. do not fabricate extra display-only events beyond the durable event types captured by the store

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

- `print_started`
- `print_paused`
- `print_resumed`
- `print_finished`
- `print_failed`
- `print_stopped`
- `photo_captured`
- `enrichment_applied`
- `repair_applied`

## Event Sources

Preferred sources in priority order:

1. Bambuddy webhook events when the webhook payload already carries trustworthy archive correlation
2. verified native `bambu_lab` device events when Bambuddy does not emit an equivalent event
3. integration service calls from HA automations/scripts for local workflow events such as enrichment, repair, and photo capture
4. minimal derived backfill for historical rows only when needed, explicitly marked in `derived_from`

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
    "type": "print_started",
    "time": "2026-04-10T13:56:31Z",
    "source": "bambuddy_webhook",
    "status": "printing",
    "label": "Print started",
    "color_key": "start"
  }
]
```

The detail response may keep raw provenance fields if useful for future diagnostics, but the popup should not need to reconstruct labels or colors from unstructured payload blobs.

## Popup Rendering Rules

### Timeline track

The existing popup track already shows start and end anchors. This issue extends that same track with intermediate event dots.

Base behavior:

1. start dot remains fixed at the left edge
2. end dot remains fixed at the right edge when a terminal time exists
3. intermediate event dots render between them based on relative event time

### Relative positioning

For events between the canonical start and end:

$$
position\_pct = \frac{event\_time - start\_time}{end\_time - start\_time} \times 100
$$

If end time is unavailable, fallback options are:

1. use the latest known event time as the temporary right boundary
2. if only one point exists, render just the start dot and omit intermediate placements

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
| `start` | `print_started` |
| `pause` | `print_paused` |
| `resume` | `print_resumed` |
| `success` | `print_finished`, `enrichment_applied` |
| `failure` | `print_failed`, `print_stopped` |
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
5. start-only and no-terminal archives still render cleanly
6. hover content remains limited to date/time plus label