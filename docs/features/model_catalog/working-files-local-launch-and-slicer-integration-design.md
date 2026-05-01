# Working Files Local Launch And Slicer Integration Design

> Status: Design proposal for approval
> Last updated: 2026-05-01
> Scope: Operator launch actions for Working Files, including browser-safe slicer launch, optional local companion integration, capability detection, and edited-file replacement flows.

## Purpose

Define how the Model Catalog `Working Files` surface should handle three operator needs that are currently in tension:

- launch a working `.3mf` into a slicer from Home Assistant
- open the true local file or containing folder on the client machine when possible
- support a safe path for replacing a Working file after the user modifies it in a slicer

The design must respect the browser security boundary already observed in production: an `http(s)` Home Assistant page cannot reliably navigate to `file:///C:/...` on the client machine.

## Problem Statement

The current Working Files card can compute correct Windows host paths from `/assets/...`, but modern Chromium-based browsers block `http(s) -> file://` navigation.

Temporary UI policy while this design is unresolved:

- hide the current `Launch` and `Explorer` buttons from the Working Files UI rather than showing broken actions
- do not restore local-launch affordances until either tokenized slicer launch or a companion-backed local-open path is implemented

Observed result:

- the UI can render valid `file:///C:/...` links
- clicking them from Home Assistant logs `Not allowed to load local resource`
- `Launch` and `Explorer` therefore fail even when the mapped path is correct

At the same time, Bambuddy demonstrates a viable `Open in Slicer` pattern that does not rely on local filesystem navigation:

- the frontend launches the slicer through a native application protocol such as `bambustudio://open?file=https://...`
- the slicer receives an authenticated or tokenized `http(s)` download URL
- the slicer fetches the file itself and opens it outside the browser sandbox

This document evaluates the viable options and recommends a hybrid design.

## Goals

- provide a reliable `Open in Slicer` action for `.3mf` files from Home Assistant
- preserve a path to true local-file and folder opens when the operator installs trusted local tooling
- avoid pretending that browser-only `file:///` links are a supported solution
- define how capability detection should work without depending on unreliable browser hacks
- define how an edited slicer result can replace a Working file safely

## Non-Goals

- building a general-purpose remote desktop or shell execution system
- exposing arbitrary client filesystem access to Home Assistant pages
- attempting to bypass browser restrictions with unsupported tricks
- silently mutating Working files without explicit operator intent

## Option Set

### Option A: Browser-Only `file:///` Launch

Description:

- Home Assistant renders `file:///C:/...` links for file launch and folder open

Pros:

- trivial UI implementation
- no extra software to install

Cons:

- not supported by modern Chromium and Edge from `http(s)` pages
- no reliable cross-browser behavior
- dead-end architecture for folder launch and file launch alike

Verdict:

- reject as a supported operator path
- keep only as historical context for why the current attempt failed

### Option B: Browser-To-Slicer Native Protocol With Tokenized Download URL

Description:

- Home Assistant calls a sidecar endpoint to mint a short-lived token for a specific Working file
- the frontend builds a tokenized download URL like `/api/working-files/{id}/dl/{token}/{filename}`
- the frontend launches a registered slicer protocol such as:
  - `bambustudio://open?file=https://ha-or-sidecar-host/...`
  - `orcaslicer://open?file=https://ha-or-sidecar-host/...`
- the slicer downloads the file and opens it locally

Pros:

- works within browser security constraints
- no custom local helper required when the slicer is already installed and registered
- aligns with Bambuddy's proven implementation pattern
- cleanly supports auth-required environments through short-lived tokens

Cons:

- opens a downloaded copy, not necessarily the original Working file in place
- cannot open a local folder in Explorer
- relies on slicer protocol registration existing on the client machine
- browser may show external-protocol prompts depending on browser and policy state

Verdict:

- recommended baseline for `Open in Slicer`
- not sufficient for `Open Local File` or `Open Folder`

### Option C: Custom Local Companion / Protocol Handler

Description:

- operator installs a local Windows companion application
- the installer registers a custom URI scheme such as `modelcatalog://` or `bambuddy://`
- Home Assistant launches that scheme from a user gesture
- the companion receives structured arguments and performs trusted local actions such as:
  - open the true local file path
  - open the containing folder in Explorer
  - optionally open the local file in a configured slicer
  - optionally report capability and status back to Home Assistant

Pros:

- can open the actual file in place
- can open Explorer for the true folder
- can support richer workflows such as replace-in-place, version backup, and edit acknowledgment
- avoids browser `file:///` restrictions because the browser launches an app, not a local file URL

Cons:

- requires local software installation and update path on each client machine
- more security-sensitive than Option B because it is a general-purpose escape from the browser sandbox
- browser cannot reliably pre-detect registration of arbitrary external protocols
- needs strong input validation and safe-root enforcement

Verdict:

- recommended only as an optional power-user path
- should be narrowly scoped to trusted local roots and explicit actions

### Option D: Hybrid Baseline + Optional Companion

Description:

- default supported path is Option B for slicer launch
- optional local companion augments the UI with true local open and Explorer actions
- replacement flow differs depending on whether the file was opened as a downloaded copy or opened in place

Pros:

- delivers value without making the whole feature depend on a local install
- supports richer local workflows when available
- cleanly separates browser-safe baseline from local-power-user extensions

Cons:

- more UX states to explain
- capability detection and fallback messaging must be explicit

Verdict:

- recommended overall direction

## Recommended Architecture

### Baseline

Support these actions in the Working Files UI:

- `Open in Slicer` for `.3mf` files using tokenized slicer-download URLs
- `Download Copy` as an explicit fallback when slicer launch fails or is unavailable

Do not present browser-only `Launch Local File` or `Explorer` actions as supported baseline features.

### Optional Enhanced Mode

When a trusted local companion is installed and confirmed available, additionally support:

- `Open Local File`
- `Open Folder`
- `Open Local File in Slicer`
- `Replace Working File With Edited Result` helper-assisted flows

## Protocol Handler Shapes

### Existing Slicer Protocols

These are app-owned handlers registered by the slicer installer, not by this repo.

Examples:

- `bambustudio://open?file=https://host/api/working-files/...`
- `orcaslicer://open?file=https://host/api/working-files/...`
- macOS-specific Bambu Studio variants such as `bambustudioopen://...` are outside the current Windows-first scope

Operational meaning:

- browser launches slicer
- slicer fetches the supplied URL
- slicer opens the fetched file

Important limitation:

- the browser is not handing the slicer the client-local `C:\...` Working path in this mode
- the slicer is opening a downloaded copy it fetched from the server URL

### Proposed Custom Companion Protocol

Example scheme:

- `modelcatalog://open-local?token=...`
- `modelcatalog://open-folder?token=...`
- `modelcatalog://open-in-slicer?token=...`
- `modelcatalog://replace-result?token=...`

Recommended contract:

1. browser launches companion with a short-lived opaque token, not a raw file path
2. companion exchanges token with the sidecar for action details
3. sidecar returns a tightly scoped action payload:
   - allowed action type
   - resolved local path under approved roots
   - optional expected file fingerprint
   - optional callback token for result reporting
4. companion performs the action locally

Why token-first is preferred over path-in-URL:

- avoids exposing local paths directly in browser-visible URLs
- reduces command-line parsing risk in the companion
- allows server-side expiry, auditing, and per-action scope
- supports richer future callbacks and replacement workflows

## Capability Detection

## Browser Constraint

Modern browsers do not expose a reliable API for a page to enumerate arbitrary installed native protocol handlers. This is intentional for privacy and fingerprinting reasons.

Consequences:

- Home Assistant cannot reliably know in advance whether `modelcatalog://` is registered
- trying to infer registration with hidden frames, timing, or focus hacks is not a supported design basis
- handler presence should not be modeled as a pure browser-discovered fact

### Supported Detection Strategies

#### Strategy 1: Optimistic Launch With Recovery UX

Behavior:

- show the button when the feature is relevant
- on click, attempt launch from an explicit user gesture
- if launch appears unsuccessful, show help text with install and retry guidance

Pros:

- simplest to implement
- no separate capability channel needed

Cons:

- poor first-run UX when the handler is missing
- browser feedback for missing handlers is inconsistent

Verdict:

- acceptable for slicer protocols owned by well-known apps
- weak for a custom companion path

#### Strategy 2: Explicit Operator Setting

Behavior:

- add a user setting such as `local_companion_expected: true|false`
- show or enable local-open actions only when the user opts in

Pros:

- simple and robust
- avoids pretending the browser can know more than it can

Cons:

- can drift from reality if the app is uninstalled or broken

Verdict:

- useful as a minimum gate, but not enough by itself for best UX

#### Strategy 3: Companion Health Signal

Behavior:

- the local companion publishes an explicit availability signal out-of-band
- Home Assistant reads that signal and uses it to enable or disable local actions

Possible implementations:

- companion calls a Home Assistant webhook or sidecar endpoint periodically with machine id, version, and capability state
- companion updates an HA entity through a local API or webhook bridge
- companion exposes a local status endpoint and another trusted component relays it to HA

Pros:

- reliable enable/disable state
- can include version, supported actions, and last-seen time
- avoids browser detection hacks

Cons:

- more plumbing than optimistic launch
- per-machine identity needs to be defined if multiple clients matter later

Verdict:

- recommended for the custom companion path

### Recommended Detection Model

- for `Open in Slicer`: show the button for supported file types and use optimistic launch with explanatory help
- for custom companion actions: require both
  - an explicit feature opt-in setting
  - a recent companion health signal

If the health signal is absent or stale:

- show the action disabled
- display concise install guidance

## Replacement And Edited-File Flows

The design must distinguish two fundamentally different edit models.

### Model 1: Downloaded-Copy Slicer Launch

This is the tokenized browser-to-slicer baseline.

Behavior:

- the slicer opens a downloaded copy fetched from the sidecar URL
- the user edits and saves a file in the slicer's chosen local workspace or download area
- the original Working file is unchanged

Implication:

- a replace flow must be explicit because there is no in-place mutation of the original Working file

#### Proposed Replace Flow For Downloaded-Copy Launch

1. user launches `Open in Slicer`
2. slicer downloads and opens a copy
3. user edits and saves the result locally
4. user returns to Home Assistant and chooses `Replace Working File`
5. UI asks for the updated `.3mf` via upload or helper-assisted pick
6. sidecar validates:
   - target Working file id
   - incoming file extension and MIME expectations
   - optional size/hash sanity
7. sidecar writes replacement using safe semantics:
   - create timestamped backup or previous revision record
   - atomically replace target file when possible
   - refresh Working index
8. UI shows updated metadata and revision history note

Pros:

- works without a local companion
- explicit and auditable

Cons:

- more steps for the operator
- not a true in-place edit path

### Model 2: Local-Path Open Through Companion

Behavior:

- companion opens the true local Working file path directly
- the slicer edits the actual file in place or saves over it
- the Working file changes on disk immediately

Implication:

- replacement may be unnecessary because the save already changed the target file
- the main remaining need is refresh, validation, and optional version backup

#### Proposed In-Place Edit Flow

1. user clicks `Open Local File in Slicer`
2. browser launches companion via `modelcatalog://...`
3. companion resolves token with sidecar and opens the exact Working file path in slicer
4. user edits and saves in slicer
5. one of the following occurs:
   - companion watches file change and reports completion back to sidecar
   - or user returns to HA and clicks `Refresh Modified File`
6. sidecar reindexes file metadata and optionally stores revision backup metadata

Pros:

- closest to the operator mental model of editing the real Working file
- no upload-back step required

Cons:

- requires local companion installation
- file watcher and callback semantics add complexity

### Hybrid Replace Design

The UI should expose a single conceptual action area but with mode-aware behavior:

- if the file was opened through tokenized slicer download only:
  - show `Replace Working File`
- if the file was opened through local companion in-place mode:
  - show `Refresh Edited File`
  - optionally show `Restore Previous Revision`

Recommended sidecar support:

- per-file revision or backup metadata for replacements
- audit events for `open_in_slicer`, `open_local`, `replace_file`, and `refresh_after_edit`
- optional optimistic file fingerprint tracking to detect whether the Working file changed after local edit

## API Sketch

### Baseline Slicer Launch

- `POST /api/working-files/{file_id}/slicer-token`
- `GET /api/working-files/{file_id}/dl/{token}/{filename}`

Frontend launch shape:

- `bambustudio://open?file=https://host/api/working-files/{file_id}/dl/{token}/{filename}`

### Companion Actions

- `POST /api/working-files/{file_id}/local-action-token`
  - request body includes requested action: `open_local`, `open_folder`, `open_in_slicer`, `replace_result`
- `POST /api/local-actions/resolve`
  - companion exchanges token for approved action payload
- `POST /api/local-actions/{action_id}/complete`
  - companion reports success or failure

### Replacement

- `POST /api/working-files/{file_id}/replace`
  - multipart upload for edited `.3mf`
- `POST /api/working-files/{file_id}/refresh-after-edit`
  - reindex and optionally capture new hash/mtime

## Security Requirements

- every token must be short-lived, single-purpose, and scoped to one file and action
- companion-resolved local paths must remain under approved roots derived from the Working-files authority
- do not pass arbitrary raw filesystem paths directly from the browser into the companion command line
- companion must reject unexpected actions, unknown roots, overly long inputs, and stale tokens
- companion must not support arbitrary shell execution, arbitrary path browse, or free-form command arguments
- replacement flow must support backup or rollback of the previous Working file revision

## UX Guidance

- label the baseline action as `Open in Slicer`, not `Launch`, to set correct expectations
- label companion-only actions explicitly:
  - `Open Local File`
  - `Open Folder`
  - `Open Local File in Slicer`
- when disabled, explain why:
  - `Requires local companion`
  - `Companion offline`
  - `Slicer launch supported for .3mf only`
- after launching an external protocol, show short inline guidance such as:
  - `Your slicer should open now. If nothing happens, verify the slicer is installed and allowed to handle protocol links.`

## Tradeoff Summary

| Option | Opens true local file | Opens Explorer | Works without extra install | Browser-safe | Supports easy replace flow | Recommended role |
| --- | --- | --- | --- | --- | --- | --- |
| Browser-only `file:///` | Yes in theory | Yes in theory | Yes | No | No | Reject |
| Tokenized slicer protocol | No, opens downloaded copy | No | Yes if slicer already installed | Yes | Yes, via explicit replace upload | Baseline |
| Custom companion | Yes | Yes | No | Yes, via app protocol | Yes, best for in-place edits | Optional enhancement |
| Hybrid | Yes when companion present | Yes when companion present | Yes for baseline slicer path | Yes | Yes | Recommended |

## Recommended Delivery Sequence

### Phase 1

- implement tokenized `Open in Slicer` for `.3mf`
- rename current launch affordance to match actual behavior
- remove unsupported browser-only local launch claims
- add explicit `Replace Working File` upload flow for edited copies

### Phase 2

- define local companion protocol and security contract
- implement companion health signal and HA capability gating
- add `Open Local File` and `Open Folder`

### Phase 3

- add helper-assisted in-place edit refresh flow
- add revision backup and restore for Working file replacements
- optionally add machine-specific capability reporting if multi-client support becomes relevant

## Open Questions

1. Should the baseline tokenized slicer host be Home Assistant, the sidecar origin, or a dedicated reverse-proxied sidecar path?
2. Should replacement revisions live as sidecar metadata only, or should previous file blobs also be retained on disk?
3. Is the companion single-user and single-machine only in the first version, or should the protocol already include machine identity?
4. Should `.stl` and other formats get `Open Local File` only, while `Open in Slicer` remains `.3mf`-first?

## Recommendation

Adopt the hybrid design.

- baseline: tokenized `Open in Slicer` with explicit replace-upload flow for edited copies
- enhancement: optional local companion for true local-path open, Explorer, and in-place edit refresh

This gives the Working Files surface a reliable browser-safe path immediately while leaving room for the richer local workflow you actually want, without pretending the browser alone can cross the local filesystem boundary.