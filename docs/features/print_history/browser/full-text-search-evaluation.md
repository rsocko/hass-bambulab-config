# Print History Full-Text Search Evaluation

> **Issue**: `#840`  
> **Question**: should the print-history browser use Bambuddy's `/api/v1/archives/search` full-text endpoint, and should the existing search box expose a toggle between standard search and full-text search?

## Recommendation

- Keep the existing browser text box on the current local "standard search" path.
- Do **not** replace the current text box behavior with Bambuddy full-text search.
- Do **not** add a user-facing toggle to the main browser text box in the current design.
- If Bambuddy full-text search is added later, treat it as a **separate capability** with explicit wording and scope, not as a hidden backend swap for the current search helper.

## Why This Is Not A Drop-In Fit

The shipped browser contract is built around a local query pipeline:

- browser cards call the integration over websocket
- the integration queries the local Variant 3 store
- the same helper-backed filters drive page results, counts, active-filter chips, and activity drill-in behavior

Today the browser search helper is part of that shared local query model.

Current local search fields:

- `id`
- `original_archive_id`
- `printer_id`
- `print_name`
- `printer_name`
- `designer`
- `project_name`
- `failure_reason`
- `tags`

Bambuddy `/archives/search?q=...` searches a different field set:

- `print_name`
- `filename`
- `tags`
- `notes`
- `designer`
- `filament_type`

That means full-text search would add useful coverage for `filename`, `notes`, and `filament_type`, but it would also **drop** some current browser search behavior if used as the default search path:

- archive ID lookup
- original-archive ID lookup
- printer ID and printer-name lookup
- project-name lookup
- failure-reason lookup

The current browser text box is therefore not just "free-text search". It is also an operational lookup field for archive IDs, printer identifiers, project names, and failure cues.

## Change Scope If Used In The Main Browser

Using Bambuddy full-text search as part of the active browser query path would require more than a small endpoint swap.

Required changes would include:

- new query-mode semantics in the websocket/browser contract
- remote search calls on text changes instead of purely local store queries
- debounce, loading, error, and stale-result handling for typing-driven search
- a deterministic merge strategy between remote full-text matches and local filters, sorting, pagination, and activity views
- alignment between browser results and heatmap/activity drill-in behavior that currently share the same helper state
- test updates for store, manager, and frontend query behavior

This is not an impossible change, but it is a meaningful design change because the current browser deliberately treats search as one local filter among many.

## Value Assessment

### What Full-Text Search Would Add

- search inside archive `notes`
- search by source `filename`
- wildcard-oriented FTS behavior from Bambuddy
- a better fit for assistant or voice-style "find prints about X" entry points

### What It Does Not Clearly Improve

- the current browser's operational search workflow
- local query performance for the current Variant 3 architecture
- filter consistency across browser results and activity summaries

Variant 3 already keeps an indexed local store and avoids Jinja/state-machine payload limits. That removes the main performance reason that would otherwise push us toward a server-side text-search dependency for the normal browser text box.

## Recommended Product Shape

### Current Browser

Keep the existing text box as the canonical browser search control.

That preserves:

- current helper semantics
- current tests and query expectations
- current activity/browser consistency
- current support for ID, printer, project, and failure-oriented lookup

### Future Full-Text Capability

If this capability is added later, prefer one of these shapes:

1. A separate advanced search action such as `Search Notes / Filename`.
2. An assistant-facing or service-facing entry point where full-text semantics are already expected.
3. A deliberately labeled alternate mode in a secondary dialog or popup, not in the always-visible main text box.

Recommended constraint if later implemented:

- keep "standard search" as the default browser behavior
- label full-text mode explicitly
- document that result semantics differ from the standard browser search

## Toggle Recommendation

The current answer is **no**.

Do not add a persistent user toggle for `standard` vs `full-text` search to the existing browser search box.

Reasons:

- it adds mode confusion to a high-frequency control
- the two modes do not search the same fields
- the browser currently relies on one shared search helper across multiple query surfaces
- the value is real but narrow, mostly around `notes` and `filename`

If a toggle ever becomes necessary, it should appear only after full-text search has a clearly separate interaction model and a concrete user story that justifies the added UI complexity.

## Decision

For issue `#840`, the recommended approach is:

- keep Phase 2.14 open as an optional enhancement
- do not integrate Bambuddy full-text search into the primary browser text box right now
- do not add a main-browser toggle right now
- revisit it later only as an explicit secondary search capability