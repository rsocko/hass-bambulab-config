# GitHub Actions Dashboard

A self-contained, zero-dependency HTML dashboard for monitoring GitHub Actions workflows on a 7″ (1024×600) always-on display. Designed for glanceable awareness of CI/CD status without leaving the homelab.

## Quick Start

```powershell
cd tools
.\start-actions-dashboard.ps1       # opens http://localhost:9090
```

On first load you'll be prompted for a **GitHub Personal Access Token** (classic, `repo` scope). The token is stored in `localStorage` only — nothing is sent anywhere except the GitHub API.

If no token is set the dashboard enters **Demo Mode** with synthetic data so the UI can be explored without a live connection.

## Files

| File | Purpose |
|------|---------|
| `tools/gh-actions-dashboard.html` | Single-file dashboard (HTML + CSS + JS, ~1 500 lines) |
| `tools/start-actions-dashboard.ps1` | One-click PowerShell launcher — Python HTTP server + browser open |

## Architecture

```
┌─────────────────────────────────────┐
│  Browser (localhost:9090)           │
│  ┌───────────────────────────────┐  │
│  │ gh-actions-dashboard.html     │  │
│  │ ┌──────┐ ┌──────┐ ┌────────┐ │  │
│  │ │ HTML │ │ CSS  │ │   JS   │ │  │
│  │ └──────┘ └──────┘ └───┬────┘ │  │
│  └────────────────────────┼──────┘  │
│                           │ fetch() │
└───────────────────────────┼─────────┘
                            ▼
              GitHub REST API v3
              /repos/{owner}/{repo}/actions/...
```

Everything lives in a single HTML file — no build step, no bundler, no framework. A Python `http.server` is used only to avoid CORS issues with `file://` origins.

### State Model

```js
const S = {
  token,          // GitHub PAT (localStorage)
  runs: [],       // workflow runs from API
  expanded: Set,  // expanded run IDs
  jobs: {},       // runId → jobs (cached for completed)
  countdown,      // seconds until next refresh
  demo,           // true when no token
  fetching,       // in-flight guard
};
```

State is held in a plain object; `render()` is called after every mutation and rebuilds the DOM from `S`.

## Features

### KPI Strip
Four hero cards at the top of the viewport:

| Card | Metric | Highlight Color |
|------|--------|-----------------|
| Running | Active in-progress runs | `--running` (blue) |
| Queued | Waiting/pending runs | `--pending` (yellow) |
| Failed | Runs with `conclusion === 'failure'` | `--failure` (red) |
| Last OK | Relative time of most recent success | `--success` (green) |

Cards glow with a box-shadow when their value is non-zero (or for "Last OK", always).

The `Last OK` card keeps the relative value as the primary line, shows the workflow short name underneath, and always shows the exact local completion time on a third line.

### Status Beacon
A full-width colored banner below the KPI strip indicating overall health:

- **All Clear** (green) — no failures, nothing running
- **Running** (blue) — at least one active run
- **Failures Detected** (red) — at least one recent failure

### Workflow List
Runs are grouped by workflow name, sorted so active/failed groups float to the top. Each group shows the most recent runs with:

- Workflow short name + run number
- Triggering actor avatar
- Trigger type icon (push ⬆, PR ⤴, manual ▶, schedule ⏰)
- Relative time with a local absolute timestamp underneath (`Started` for active/queued runs, `Ended` for completed runs)
- Expandable job detail with per-step status icons

### Run Summary Popup
Clicking the 📋 button on any completed run opens a modal overlay with:

1. **Run metadata** — commit SHA, first line of commit message, branch, total duration
2. **Step table** — each meaningful step listed with a status icon:
   - ✓ success (green)
   - ✗ failure (red, bold)
   - ⊘ skipped (dimmed, italic)

Internal "Set up job", "Complete job", and "Post …" housekeeping steps are filtered out.

> **Note:** GitHub's `$GITHUB_STEP_SUMMARY` markdown is *not* exposed through the REST API (`output.summary` is null for Actions-created check runs). The dashboard probes for it first (future-proofing) and falls back to the step-data view described above.

### Auto-Refresh
- Configurable interval (default 15 s) with a countdown indicator and animated progress bar
- Manual refresh button (⟳) with debounce
- Rate-limit awareness — the remaining X-RateLimit header is displayed; polling pauses gracefully if exhausted
- Relative time labels are refreshed client-side every 15 seconds between API polls so `ago` text does not go stale while the underlying run data is unchanged

For always-on installed-app use, steady-state refresh is intentionally limited: a small pulse runs only when a real data refresh completes, active runs keep a small spinning status ring, and the 15-second timer only recalculates visible timestamp strings. That timer does not add GitHub API requests.

### Settings Overlay
Gear icon opens a settings panel where the user can change:

- Refresh interval (seconds)
- Max runs to fetch (API page size, max 100)
- Token management (view masked, update, or clear)

All settings persist in `localStorage`.

### Demo Mode
When no token is configured the dashboard generates realistic synthetic workflow data so the full UI can be previewed — including the summary popup with mock deploy output.

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Single HTML file | Zero deployment friction — copy one file, serve it |
| No framework | Keeps bundle at ~40 KB, loads instantly on low-power devices |
| `localStorage` for token | Avoids server-side secrets; token never leaves the browser |
| Python HTTP server | Ships with every OS that has Python; avoids CORS from `file://` |
| Dark theme only | Matches the ambient homelab display use-case; reduces glare |
| Large fonts + touch targets | Optimized for 7″ 1024×600 display viewed at arm's length |

## CSS Theme Variables

All colors are defined as CSS custom properties on `:root` and can be overridden:

```css
--bg-primary, --bg-secondary, --bg-tertiary
--border
--text-primary, --text-secondary, --text-tertiary
--success, --failure, --pending, --running, --cancelled, --accent
--font-mono, --font-sans
```

## Extensibility Points

### Adding a New Workflow
The `SHORT` constant maps full workflow names to short display labels. Add an entry for any new workflow file and it will automatically appear:

```js
const SHORT = {
  'Auto-Dispatch Home Assistant Deploy':          'Auto-Dispatch',
  'Deploy Home Assistant Config (HAOS Template)': 'Deploy HA',
  // add new workflows here
};
```

No other code changes are needed — the API returns all workflows and grouping is automatic.

### Custom Summary Providers
`showSummary()` is structured as a chain of attempts:

1. **Check-run `output.summary`** — if a third-party app or future GitHub feature populates this field, the dashboard renders it as markdown automatically.
2. **`buildStepSummary()` fallback** — builds the step-table view from jobs API data.

To add a new source (e.g., fetching an artifact, querying a deployment API), insert it between steps 1 and 2 in `showSummary()`.

### Markdown Rendering
`mdToHtml()` is a lightweight converter supporting headings, bold, code, tables, lists, and horizontal rules. It is used for demo-mode summaries and would render any real `output.summary` markdown if the API starts returning it.

### Theming
Override `:root` CSS variables to create a light theme or match a different display environment. All component styles reference variables rather than hard-coded colors.

### Different Repository
Change the `OWNER` and `REPO` constants at the top of the `<script>` block:

```js
const OWNER = 'your-org';
const REPO  = 'your-repo';
```

## Future Considerations

- **Artifact download** — if deploy workflows attach summary artifacts (`actions/upload-artifact`), the dashboard could fetch and render them for richer deploy reports.
- **Webhook / SSE push** — replace polling with a server-sent-events proxy for instant updates (requires a small sidecar).
- **Multi-repo view** — generalize the dashboard to monitor multiple repositories side-by-side on a wider display.
- **Notification sounds** — play an audible alert on failure detection for a true ambient monitoring experience.
- **Light theme toggle** — a settings toggle that swaps CSS variables for daytime readability.
- **Step duration column** — the jobs API returns `started_at`/`completed_at` per step; these could be shown in the summary table to identify slow steps.
- **Re-run button** — trigger a workflow re-run directly from the dashboard via `POST /actions/runs/{id}/rerun`.
- **Mobile responsive layout** — the current layout is fixed for 1024×600; a media-query breakpoint could adapt it for phone screens.

## API Usage

The dashboard uses these GitHub REST API endpoints:

| Endpoint | Purpose |
|----------|---------|
| `GET /repos/{owner}/{repo}/actions/runs` | List recent workflow runs |
| `GET /repos/{owner}/{repo}/actions/runs/{id}/jobs` | List jobs + steps for a run |
| `GET /repos/{owner}/{repo}/check-runs/{id}` | Probe for `output.summary` on a job |

All requests include `Authorization: Bearer {token}` and `Accept: application/vnd.github+json`. Rate-limit headers are tracked and displayed.
