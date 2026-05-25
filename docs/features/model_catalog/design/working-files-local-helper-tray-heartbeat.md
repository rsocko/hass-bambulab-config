# Working Files Local Helper Tray And Heartbeat Design

> **Status:** Proposed deferred design.
> **Tracking issue:** GitHub issue creation blocked locally (`gh auth` missing). See [issue-ready draft](../planning/working-files-local-helper-tray-heartbeat-issue.md).
> **Scope:** Follow-on design for the optional Windows local helper used by Working Files local-open actions. Covers tray-mode lifecycle, helper heartbeat/capability signaling, machine identity, and UI gating.
> **Companion docs:** [working-files-launch.md](working-files-launch.md), [working-files-workflow.md](working-files-workflow.md).

---

## 1. Why this exists

The first helper-backed Working Files slice is intentionally on-demand only:

- Windows registers `modelcatalog://`
- the browser launches the helper on demand
- the helper resolves a short-lived token
- the helper opens the real local file or folder in place

That is enough for `Open Local` and `Open Folder on Desktop`, but it leaves three gaps:

1. Home Assistant cannot reliably know whether the helper is installed.
2. The UI cannot honestly switch between helper-only buttons and fallback actions.
3. In-place edit workflows need a longer-lived local process if we want file watching, status callbacks, or richer diagnostics.

This doc defines the deferred tray/heartbeat layer that sits on top of the existing protocol helper.

## 2. Goals

- Let the dashboard know whether the helper is installed and recently healthy.
- Let the helper report machine-local capabilities such as:
  - open local file
  - open folder
  - open local file in slicer
  - OneDrive path inference available
- Support future in-place edit refresh flows without forcing a full Windows service upfront.
- Keep the current one-time protocol registration flow working even if the tray process is not running.

## 3. Non-goals

- Do not require a background process just to keep protocol launch working.
- Do not let the helper accept arbitrary file paths or free-form shell commands.
- Do not try to make browser-native protocol detection the gating mechanism.

## 4. Recommended runtime model

### 4.1 Split roles

Keep two helper roles distinct:

1. **Protocol launcher**
   - starts on demand from `modelcatalog://...`
   - resolves token and performs exactly one action
   - continues to work even if tray mode is disabled

2. **Tray/heartbeat process**
   - optional background process started at login
   - publishes helper health and capability state
   - may later own file-watch and refresh callbacks

This keeps the minimum local-open workflow simple while making room for richer stateful behavior later.

### 4.2 Startup model

Recommended first deferred version:

- tray app runs per-user at login using a Startup shortcut or scheduled task
- tray app remains lightweight and mostly idle
- tray app exposes no local unauthenticated command surface
- protocol launches still work even if tray app is not running

## 5. Heartbeat contract

### 5.1 Payload shape

The tray process should periodically report a heartbeat payload like:

```json
{
  "machine_id": "windows-rsock-laptop",
  "helper_version": "0.1.0",
  "reported_at": "2026-05-24T18:30:00Z",
  "capabilities": {
    "open_local": true,
    "open_folder": true,
    "open_in_slicer": false,
    "one_drive_consumer": true,
    "one_drive": true
  },
  "status": {
    "protocol_registered": true,
    "config_loaded": true,
    "sidecar_reachable": true
  }
}
```

### 5.2 Transport options

Acceptable first implementation options:

1. helper posts directly to a sidecar endpoint
2. helper posts to a Home Assistant webhook that stores the latest state

Recommendation:

- use a sidecar endpoint first, because the helper already depends on sidecar resolution for token flows

### 5.3 Freshness

Suggested freshness rules:

- helper sends heartbeat every 60 seconds
- UI considers helper healthy if last heartbeat is <= 180 seconds old
- stale heartbeat means helper actions are hidden or disabled with explicit messaging

## 6. Machine identity

### 6.1 First version

The first tray version should include machine identity even if the UI does not yet fully use it.

Suggested format:

- stable machine GUID derived at install time and stored in helper config
- optional human label shown in UI, for example `Rysock Laptop`

### 6.2 Why include it early

Without machine identity, multiple clients will overwrite each other’s helper state.

Including it early avoids redesign when:

- laptop and desktop both use Working Files
- server-side admin sessions should not advertise desktop-only helper state
- future per-machine routing becomes necessary

## 7. UI gating rules

The Working Files UI should not ask the browser whether `modelcatalog://` exists.

Instead:

1. read helper heartbeat/capability state
2. if fresh and matching the current machine scope, show helper-only actions:
   - `Open Local File`
   - `Open Folder`
   - `Open Local File in Slicer`
3. if missing or stale, fall back to:
   - `Copy Path`
   - `Copy Folder Path`
   - tokenized browser-safe slicer flow

Suggested messages:

- `Requires local helper`
- `Helper offline`
- `Helper online on another machine`

## 8. Future extension points

Once tray mode exists, it can later own:

- local file-watch after `Open Local File in Slicer`
- callback to `refresh-after-edit`
- callback to `replace-result`
- local diagnostics log collection and UI surfacing
- explicit slicer executable detection and protocol/provider reporting

## 9. Security guardrails

- heartbeat must not grant action authority by itself
- local actions still require short-lived per-action tokens
- helper must not accept raw path instructions from heartbeat state
- machine identity is descriptive, not an authorization substitute
- tray app must not expose arbitrary local command execution

## 10. Recommended follow-on implementation order

1. add sidecar helper heartbeat endpoint and latest-state storage
2. add per-machine helper config with generated machine id and label
3. add tray/startup mode for the helper
4. add Working Files UI gating based on fresh helper state
5. add helper-backed `Open Local File in Slicer`
6. add file-watch / refresh-after-edit callbacks

## 11. Decision summary

- Keep protocol launch one-shot and available without a background process.
- Add tray/heartbeat as an optional second layer.
- Use explicit helper state, not browser protocol detection, for UI gating.
- Include machine identity in the first heartbeat version to avoid repainting the model later.