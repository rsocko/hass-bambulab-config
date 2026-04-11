# Browser Instrumentation

## Purpose

The print-history browser and activity heatmap now include optional instrumentation intended for future debugging and performance analysis.

This instrumentation is designed to stay in the repo permanently, but remain disabled by default.

- Disabled: normal production behavior, no extra console noise, no visible UX change beyond the existing debounce behavior.
- Enabled: the browser cards emit timing and coalescing data that helps explain filter bursts, clear/reset behavior, query timings, and heatmap work.

## How To Enable

Turn on `input_boolean.print_history_debug_instrumentation`.

You can do that from either:

- the Print History settings popup opened from the top-right settings button in the browser header
- Developer Tools by toggling the helper directly

## What It Captures

When enabled, the browser writes debug entries to `window.__printHistoryDebug` and `console.debug`.

### Browser card entries

Channel names:

- `browser`
- `browser_error`

Fields include:

- `roundTripMs` — websocket query round-trip time seen by the browser card
- `pageItemCount` — number of archive cards returned for the current page
- `filteredCount` — total filtered result count
- `scheduledRefreshes` — how many refreshes were requested
- `executedRefreshes` — how many debounced refreshes actually ran
- `coalescedRefreshes` — how many requests were folded into an already-pending refresh
- `backend` — server-side timing payload when enabled
- `store` — current store stats returned by the Bambuddy query response

### Heatmap entries

Channel names:

- `heatmap_query`
- `heatmap_render`

Fields include:

- `durationMs` — query or render duration seen by the heatmap card
- `activityRowCount` — number of activity rows returned for the heatmap working set
- `scheduledRenders` — how many renders were requested
- `executedRenders` — how many debounced renders actually ran
- `coalescedRenders` — how many render requests were folded together
- `backend` — server-side timing payload when enabled
- `store` — current store stats returned by the Bambuddy query response

### Backend timing payload

When the helper is on, Bambuddy query responses include a `debug` object with:

- `query_ms` — time to compute the filtered query result
- `annotations_ms` — time to load annotation/review/repair metadata for visible page items
- `activity_rows_ms` — time to load heatmap activity rows when requested
- `total_ms` — total server-side query handling time
- `page_item_count`
- `filtered_count`
- `activity_row_count`
- `include_activity_rows`

## How To Inspect It

### Browser console

Open the browser dev tools console and filter for:

```text
[print-history-debug]
```

### Live in-page object

You can inspect the latest entries with:

```js
window.__printHistoryDebug
window.__printHistoryDebug.latest
window.__printHistoryDebug.events
```

This is useful for Playwright, DevTools, or manual reproduction runs.

## Intended Use

This is meant to be kept permanently as a dormant diagnostic tool.

That is preferable to adding temporary one-off logging every time a regression appears, because:

- the overhead is very low when disabled
- it gives a consistent workflow for future debugging
- it helps compare frontend debounce behavior against backend query cost

## When To Leave It Off

Leave it off during normal usage.

Reasons:

- avoids noisy console output
- keeps troubleshooting-only data out of routine sessions
- reduces the chance of confusing routine inspection with debug-only metrics

## Recommended Debug Workflow

1. Enable `input_boolean.print_history_debug_instrumentation`.
2. Reproduce the filter or clear/reset behavior.
3. Inspect `window.__printHistoryDebug.latest` and console debug lines.
4. Compare frontend coalescing counters against backend timing values.
5. Turn the helper back off after the session.