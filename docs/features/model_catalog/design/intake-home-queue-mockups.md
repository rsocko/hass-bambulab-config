# Intake Home And Queue Review Mockups

> **Status**: Design update for reintroduced Active Queue review
> **Created**: 2026-05-27
> **Scope**: Updated Intake view now that Active Queue returns as a distinct surface separate from the intake wizard.

## Purpose

Define the updated Intake-facing information architecture before implementation work resumes.

This document intentionally separates three concerns:

- `Intake Home` launches new work and summarizes queue/history state
- `Queue Review` advances queued items after handoff
- the intake wizard authors a new batch and should not be overloaded with queued-item triage

Use this mockup set with:

- [intake-inbox.md](./intake-inbox.md)
- [intake-wizard-mockups.md](./intake-wizard-mockups.md)
- [external-source-intake.md](./external-source-intake.md)

## Design Position

The updated Intake view should reintroduce the queue, but not by turning the wizard back into an inbox.

The preferred structure is:

1. `Intake Home` as the visible launchpad
2. `Queue Review` as a dedicated review workbench for active items
3. `Job History` as the completed-work surface

This keeps the wizard focused on batch authoring while still making queued work discoverable and actionable.

## Carry-Forward From Earlier External-Intake Mockups

The earlier standalone mockups remain useful as idea sources even though the preferred architecture has changed.

Sources reviewed:

- `mockups/external-intake-workbench-a.html`
- `mockups/external-intake-workbench-b.html`
- `mockups/external-intake-quick-capture.html`

Ideas to keep:

- channel-aware capture entry points such as URL paste, browser extension, Stream Deck, and collection capture
- a small `Recent captures` or `Pending captures` slice on Intake Home so external-source work is visible before it becomes a normal queue item
- quick-capture routing presets such as `link only`, `metadata only`, and `full import when confidence is high`
- collection-migration monitoring and exception handling as an Intake-adjacent capability
- lightweight channel-health telemetry so extension or webhook failures are visible without opening logs

Ideas not carried forward as-is:

- a separate full-screen `External Intake Workbench` that competes with Intake Home
- a provider-only review queue distinct from the main Queue Review surface
- a design that makes external-source imports feel like a different product from file- and folder-based intake

Resulting direction:

- Intake Home absorbs the best launchpad and monitoring ideas from the older mockups
- Queue Review becomes the single review surface for queued items regardless of whether they came from browser upload, server inbox, or external-source capture
- external-source-specific detail survives as item detail panels and metadata-default sections, not as a parallel queue product
- provider detection should be automatic once a URL is pasted; the dashboard should not ask the operator to run a separate detect step

## Surface A: Intake Home

`Intake Home` is a launch and monitoring surface.

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Intake                                                                 [Refresh] [Help]   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ Summary tiles                                                                        ▲ ▼  │
│ ┌──────────────────────┐ ┌──────────────────────┐ ┌──────────────────────┐ ┌───────────┐ │
│ │ Active Queue         │ │ Review Required      │ │ Completed Today       │ │ Sources   │ │
│ │ 7 items              │ │ 3 warning items      │ │ 5 jobs                │ │ Browser + │ │
│ │ 2 ready / 2 deferred │ │ duplicates, naming   │ │ 3 catalog / 2 working │ │ Server +  │ │
│ │ [Open Queue Review]  │ │ [Filter Warnings]    │ │ [Open Job History]    │ │ MakerWorld│ │
│ └──────────────────────┘ └──────────────────────┘ └──────────────────────┘ └───────────┘ │
├───────────────────────────────────────────────┬────────────────────────────────────────────┤
│ Start New Intake                             │ Active Queue Snapshot                      │
│                                               │                                            │
│ ┌───────────────────────────────────────────┐ │ submitted           2                      │
│ │ Upload                                    │ │ validated_ready     2                      │
│ │ Drop file, files, or folder to jump       │ │ validated_warning   3                      │
│ │ into the wizard with those sources        │ │ deferred            2                      │
│ │ already staged; user can still add more   │ │                      │
│ │ [Start Upload Wizard]                     │ │                      │
│ └───────────────────────────────────────────┘ │                                            │
│ ┌───────────────────────────────────────────┐ │ Top items                                     
│ │ Server Inbox Wizard                       │ │ - MakerWorld Big Brick Man          warning  │
│ │ Browse allowlisted roots                  │ │ - Gridfinity labels batch            ready    │
│ │ [Start Server Wizard]                     │ │ - lithophanes folder                 deferred │
│ └───────────────────────────────────────────┘ │ [Open Queue Review]                         │
│ ┌───────────────────────────────────────────┐ │                                            │
│ │ External Source Capture                   │ └────────────────────────────────────────────┘
│ │ [ https://makerworld.com/...           ]  │ Recent Job History                            │
│ │ provider detected automatically           │ - Published to catalog: Modular bin          │
│ │ [Capture] [Recent captures]               │ - Published to working: TPU feet              │
│ └───────────────────────────────────────────┘ │ Capture Ops                                   │
│                                               │ - Browser Extension: healthy                  │
│                                               │ - Stream Deck Webhook: last seen 2m          │
│                                               │ - Capture failures today: 1                  │
└───────────────────────────────────────────────┴────────────────────────────────────────────┘
```

### Intake Home Rules

- `Intake Home` should not display every queue-row action inline.
- It should provide enough signal to tell the operator whether to start a new batch or review existing work.
- External-source capture belongs here because it behaves like “start new intake,” not like queued triage.
- The first launch card should be labeled `Upload`, not `Browser Upload`, because drag-from-desktop is the primary mental model.
- That `Upload` card should act as a drag surface for a file, multiple files, or a folder while still supporting click-to-open wizard behavior.
- Dropping any of those sources should open the wizard with the dropped sources already staged on the Source step.
- After the wizard opens from a drop, the operator should still be able to add more files or folders before continuing.
- The URL field should be directly editable on the dashboard, with provider detection implied and automatic.
- Quick-capture presets may exist, but they should not dominate the main launchpad.
- Collection migration belongs here as an Intake-adjacent batch flow, but its exceptions should still feed the same Queue Review surface.
- Channel Health is useful, but it fits better as recent operational context than as a primary launch control.

## Surface B: Queue Review

`Queue Review` is where queued items advance.

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Queue Review                                             [Refresh] [Select] [Job History] │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ Filters: [All ▼] [Submitted] [Ready] [Warnings] [Deferred] [MakerWorld only ☐]           │
├───────────────────────────────────────┬────────────────────────────────────────────────────┤
│ Queue list                            │ Review detail                                      │
│                                       │                                                    │
│ > Big Brick Man                       │ Big Brick Man                                      │
│   MakerWorld                          │ makerworld.com/en/models/1295917                   │
│   validated_warning • duplicate       │ Status: validated_warning                          │
│                                       │ Queue transport: queued                            │
│   Gridfinity label set                │ Cleanup: keep                                      │
│   Server Inbox                        │                                                    │
│   validated_ready                     │ Warnings                                           │
│                                       │ - duplicate candidate                              │
│   Lithophane archive batch            │ - title collision                                  │
│   Browser Upload                      │                                                    │
│   deferred                            │ Prepopulated publish defaults                      │
│                                       │ - Title: Big Brick Man                             │
│ [Batch Validate] [Batch Publish]      │ - Creator: pippo_the_printer                       │
│ [Batch Defer] [Batch Reject]          │ - Description: Large display figurine              │
│                                       │ - Source origin: makerworld                        │
│                                       │ - Source URL: canonical MakerWorld URL             │
│                                       │ - Preview candidate: cover image                   │
│                                       │ - Tags: brick, figure                              │
│                                       │                                                    │
│                                       │ Actions                                            │
│                                       │ [Validate] [Publish Catalog] [Publish Working]     │
│                                       │ [Defer] [Reject] [Delete]                          │
└───────────────────────────────────────┴────────────────────────────────────────────────────┘
```

### Queue Review Rules

- Item detail should distinguish queue transport state from intake decision state.
- Queue Review should surface default publish metadata before the operator commits.
- `Publish Working` belongs here alongside `Publish Catalog`.
- Validation-action persistence for duplicate findings should eventually live here too.

## Surface C: Job History

`Job History` remains the completed-work view, not the active queue.

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Job History                                                          [Refresh] [Filters]  │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ Published to Catalog  │ Modular bin set        │ linked model: modular-bin--a1b2c3d4      │
│ Published to Working  │ TPU feet               │ folder: tpu-feet-v2                       │
│ Rejected              │ duplicate dragon       │ note: duplicate with curated item         │
│ Capture Ops           │ Browser Extension      │ healthy · last failure 1h ago             │
│ Capture Ops           │ Stream Deck Webhook    │ last seen 2m ago                           │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Job History / Ops Notes

- Channel Health is useful, but it should sit with recent execution and failure context rather than with the main intake launch controls.
- This can be rendered as a small `Capture Ops` panel in Job History or a neighboring operations view.

## MakerWorld-Specific Detail Pattern

MakerWorld items should show a provenance-aware detail panel in Queue Review.

Recommended sections:

- canonical source URL
- title / creator / description defaults
- preview image and gallery count
- selected/default instance
- tags and basic source stats when available
- operator overrides that will flow into publish

This is the main place where external-source metadata becomes visible and editable before final publish.

## Implementation Approach

### Home Assistant surfaces

- keep `Intake Home` as the launchpad and summary surface
- treat `Queue Review` as its own hidden child view or popup-capable workbench
- keep the wizard as popup-driven or child-view driven authoring flow

### Intake Home capabilities worth preserving from the older mockups

- inline URL paste with automatic provider detection
- desktop drag-and-drop directly onto the Upload launch card
- dropped file, files, or folder should prepopulate the wizard rather than bypass it
- `Recent captures` or `pending captures` list
- browser-extension pairing or health summary
- Stream Deck or webhook preset visibility
- collection-migration status and exceptions summary
- channel-health summary for extension/webhook/capture paths, preferably grouped with recent operations rather than main launch actions

### Settings placement

Low-frequency settings from the older mockups should not live on the main dashboard launch surface.

Examples:

- capture policy defaults such as `link only`, `metadata only`, or `full import when confidence is high`
- channel pairing or token management
- webhook configuration and rotation
- migration thresholds and batch exception policy

Preferred placement:

- a dedicated Intake settings popup
- a sidecar config or admin page
- or a tucked-away advanced settings affordance reachable from Intake Home

These settings are important, but they are changed much less often than capture and review actions.

### Queue Review capabilities required to feel complete

- validate
- publish curated
- publish working
- defer
- reject
- delete
- warning/finding detail visibility
- default metadata summary for external-source items

### Things intentionally not in scope for this update

- reopening queued items into the wizard for in-place mutation
- collapsing Queue Review back into Intake Home
- hiding queued-item advancement behind admin-only tools

## Companion HTML Mockup

See [mockups/intake-home-queue-workbench.html](./mockups/intake-home-queue-workbench.html) for a self-contained higher-fidelity mockup of the same design.