# Model Catalog Landing Page Dashboard Design

> **Status:** Hi-fidelity design proposal with operator feedback incorporated.
> **Tracking issue:** [#1174](https://github.com/rsocko/hass-bambulab-config/issues/1174)
> **Scope:** A dynamic Home Assistant-first landing surface for the model catalog domain that summarizes operational state across Catalog, Working Files, Intake, External Imports, and the Unified Production Queue, then routes the operator into the correct detailed tab or popup to complete work.
> **Companion mockups:** [mockups/landing-dashboard.html](mockups/landing-dashboard.html), [mockups/landing-dashboard-compact.html](mockups/landing-dashboard-compact.html), [mockups/landing-dashboard-analytics.html](mockups/landing-dashboard-analytics.html)
> **Related design docs:** [catalog-card-design.md](catalog-card-design.md), [working-files-card-design.md](working-files-card-design.md), [../unified-production-queue-design.md](../unified-production-queue-design.md), [../external-source-intake-design.md](../external-source-intake-design.md), [../intake-inbox-design.md](../intake-inbox-design.md), [../architecture-overview.md](../architecture-overview.md)

---

## 1. Why this page exists

Issue #1174 asks for the "Model Catalog" landing page to feel more dynamic and dashboard-like.

That request is correct, but it needs one architectural guardrail: the landing page should **not** become a second copy of every specialized surface.

The system already has or is actively designing dedicated deep-work views for:

- **Catalog** browsing and model detail
- **Working Files** organization and group/file actions
- **Intake** wizard, queue, and inbox review
- **External service imports** and quick capture
- **Unified Production Queue** planning and execution handoff
- **Print History / linked archives** as adjacent execution truth

The landing page should therefore do three jobs only:

1. **Orient** the operator to current system state.
2. **Surface actionable exceptions** and near-term work.
3. **Jump directly** into the right detailed surface with context preserved.

This makes the landing page a **hub**, not a parallel application.

---

## 1.1 Confirmed operator decisions

The following decisions are now explicit:

1. **Search is universal by default.** It should search Catalog, Working Files, Queue, Intake, External capture records, and other relevant cross-domain content from one bar.
2. **Ideas are excluded by default** from the landing page's Ready To Print surface.
3. **Print-history failures appear only when relevant** to model-catalog workflow, queue state, or a landing-page action.
4. **Local Intake and External Intake stay separate** as dashboard modules and as detailed work surfaces.
5. **Some actions may launch directly from the dashboard** when they are shallow and safe.

The fifth point changes the page philosophy slightly: the landing page remains a hub, but it can also host a small number of **direct-launch operator actions** without requiring a stop at a separate page first.

---

## 2. Core design principle

### 2.1 The landing page is an operational dashboard, not a neutral menu

The old mental model implied by the issue body is:

- Working Groups
- Curated
- Recent Files
- Search
- Actions required
- Upload
- Inbox waiting

That list is useful, but it reads like a static menu. The redesigned landing page turns those into **live slices** of the current state:

- what needs attention now
- what is ready to print now
- what is changing most recently
- what has not yet been reviewed
- what can be launched in one click

### 2.2 Information first, action second, detail last

Each dashboard block follows the same contract:

1. Show a concise status summary.
2. Offer one or two obvious actions.
3. Provide a **Jump to ...** link that opens the correct detailed tab/view.

The landing page must never trap the operator in a shallow half-workflow.

---

## 3. Scope boundaries

### 3.1 What the landing page owns

- cross-domain status summaries
- cross-domain exception lists
- search entrypoint
- recently touched / recently imported / recently printed context
- quick actions that are safe and reversible
- deep links into the specialized tabs and popups

### 3.2 What it does not own

- full intake wizard editing
- full Working Files reorganization
- complete queue editing and planner operations
- full model metadata editing
- advanced model actions
- archive repair or print-history-native workflows

This preserves the approved Home Assistant-first hybrid architecture from [../architecture-overview.md](../architecture-overview.md).

---

## 4. Page structure

The recommended landing page is a **three-band dashboard**:

1. **Top band:** search + global status + primary quick actions
2. **Middle band:** actionable work queues
3. **Lower band:** recent activity and browse entrypoints

### 4.1 Top band

Contains:

- **Universal search bar**
  - search Catalog models, Working groups/files, queue entries, and pending external captures
  - keyboard-first entrypoint
  - quick scope chips: `All`, `Catalog`, `Working`, `Queue`, `Intake`, `External`
- **Global KPI strip**
  - catalog model count
  - working group count
  - ungrouped file count
  - active intake/inbox count
  - production queue ready count
  - external capture pending count
- **Primary quick actions**
  - `Upload / Intake`
  - `Capture URL`
  - `Open Queue`
  - `Review Working`

The updated design should also consider a more explicit **Key Actions** module that is cross-domain rather than section-owned. See §5.8.

The top band answers: "What is the state of the system, and what do I usually do first?"

### 4.2 Middle band: actionable work queues

This is the core of the page. It should be vertically ordered by urgency.

Recommended sections:

1. **Needs Attention**
2. **Ready To Print**
3. **Inbox / Intake Waiting**
4. **External Imports / Captures**

These are not arbitrary categories. They map to distinct detailed surfaces already designed elsewhere.

### 4.3 Lower band: recent activity and browse entrypoints

Contains:

- **Recent Working File changes**
- **Recent Catalog additions / updates**
- **Recent linked prints**
- **Browse entry cards** for Catalog, Working Files, Queue, Intake, External Intake

This band supports reconnaissance and low-friction navigation when no urgent exception exists.

---

## 5. Recommended modules

## 5.1 Needs Attention

This is the headline module and should sit top-left in desktop layout.

Purpose:

- aggregate the highest-value exceptions across domains into one prioritized list

Recommended item types:

- Catalog models with `catalog_quality_state != complete`
- Working groups with warnings or stale file-layout drift
- Ungrouped files waiting for organization
- queue entries blocked by missing filament or unresolved selection
- intake uploads with validation warnings or cleanup failures
- external captures with low-confidence metadata requiring review

Each row should show:

- object label
- domain badge (`Catalog`, `Working`, `Queue`, `Intake`, `External`)
- one-line reason
- severity tone
- one explicit primary action
- one `Jump to ...` link

Examples:

- `Hex Driver Stand v4` · `Catalog` · `Needs preview image` → `Open model` / `Jump to Catalog details`
- `Gridfinity jigs` · `Working` · `3 ungrouped related files detected` → `Review group` / `Jump to Working Groups`
- `Phone dock remix` · `External` · `Metadata confidence medium` → `Review capture` / `Jump to External Intake`

This section should cap visible rows and expose `View all attention items` into a dedicated filtered list view later.

## 5.2 Ready To Print

Purpose:

- provide an immediate operational answer to "what can I print next?"

Content sources:

- unified production queue entries in `ready` or `started`
- catalog models with lightweight queue state
- working groups marked ready to publish/print

Explicit exclusion by default:

- **idea-only** entries do not appear here unless the operator enables a separate Ideas view or filter

Each row should show:

- title
- source kind (`Catalog`, `Working`, `Idea`)
- file/plate summary
- duration bucket
- AMS-fit or filament-fit hint
- last attempt outcome if any

Primary actions:

- `Open Queue Item`
- `Send to Queue`
- `Jump to Queue Planner`

The landing page only previews queue candidates. Full reordering and planner optimization remain in [../unified-production-queue-design.md](../unified-production-queue-design.md).

## 5.3 Inbox / Intake Waiting

Purpose:

- make intake backlog visible without forcing the operator to live in the inbox screen

Content:

- staged uploads waiting for review
- validation-complete batches ready to commit
- batches with warnings or cleanup follow-up
- queue/job history summaries when a run recently completed

Cards should reflect the canonical intake direction from [../intake-inbox-design.md](../intake-inbox-design.md): wizard-first, inbox demoted, Job History visible.

Recommended sub-blocks:

- `Ready to commit`
- `Needs review`
- `Recent intake jobs`

Primary actions:

- `Open wizard`
- `Review inbox`
- `View job history`

### Intake page vs. dashboard launch

It does **not** make sense to force the operator through a separate Intake landing page when the action is obviously one of these:

- start a new local upload/import wizard
- reopen an intake batch already in progress
- review a specific inbox item or job

Recommended rule:

- the dashboard can launch the **wizard directly** for `Upload / Intake`
- the dashboard can jump directly into a specific inbox/job context
- a dedicated Intake page still exists as the **full workspace** for ongoing review/history/backlog work

So the right framing is not "dashboard or intake page". It is:

- **dashboard for initiation and routing**
- **intake page for sustained detailed intake work**

## 5.4 External Imports / Captures

Purpose:

- surface the non-file intake channels without conflating them with local browser/server intake

Content:

- recent URL captures
- browser extension captures
- Stream Deck captures
- collection migration jobs
- provider/channel health diagnostics

This section should reflect [../external-source-intake-design.md](../external-source-intake-design.md): the landing page is where the operator notices pending external work, not where they perform full provider-aware review.

Primary actions:

- `Capture URL`
- `Open workbench`
- `Review migration`

This remains a separate dashboard block from local Intake because the review contracts, confidence model, and provider/channel diagnostics are materially different.

## 5.5 Working Files Snapshot

Purpose:

- answer issue #1174's original Working Groups and File Ungrouped ask in one high-signal block

Recommended contents:

- grouped by stage: `Draft`, `In Progress`, `Ready`
- ungrouped file count
- one or two hot rows per stage showing last modified and file-count summary
- one recent file-change list for fast triage

Primary actions:

- `Open Groups`
- `Open Ungrouped`
- `Jump to All Files`

The detailed organization behavior stays in [working-files-card-design.md](working-files-card-design.md).

## 5.6 Catalog Snapshot

Purpose:

- answer issue #1174's Curated / counts / groups / most recent ask

Recommended contents:

- total models
- recently added models
- models needing metadata attention
- favorite or frequent models for quick re-open
- quality-state counts: `Needs preview`, `Needs tags`, `Needs photos`, `Complete`

Primary actions:

- `Browse Catalog`
- `Open recent model`
- `Jump to advanced actions` when appropriate

## 5.7 Recent Activity Rail

Purpose:

- bridge catalog identity with execution reality

Recommended event types:

- recent prints linked to models
- recent working-file modifications
- recent intake commits
- recent external captures
- queue completions or failures

Each item can deep-link into:

- model detail popup
- linked prints tab
- working group popup
- queue entry popup
- intake job history

This gives the landing page motion and history without turning it into a log viewer.

## 5.8 Key Actions

Purpose:

- provide one compact, operator-first action cluster regardless of where the underlying action originates

This module is separate from Needs Attention. Needs Attention is exception-driven. Key Actions is intent-driven.

Recommended actions:

- `Start local intake`
- `Capture external URL`
- `Create working group from ungrouped files`
- `Add ready item to queue`
- `Open queue planner`
- `Reopen last active model`
- `Review blocked queue item`
- `Review latest capture`

Recommended selection rule:

- show 4 to 8 action tiles only
- rank by recency, urgency, and operator frequency
- mix domains when useful instead of forcing one tile per domain

This is especially valuable in a more compact above-the-fold layout because it compresses a lot of workflow access into one predictable region.

---

## 6. Search results treatment

Universal search is only useful if the result display is equally deliberate.

Recommended result architecture:

### 6.1 Search opens an anchored result panel, not a full page by default

Behavior:

- typing in the search bar opens a docked result panel directly beneath the bar on desktop
- on mobile, the result panel becomes a full-height overlay sheet
- the result panel should support keyboard navigation from the first keystroke

### 6.2 Result grouping

Default grouped sections:

- `Catalog Models`
- `Working Groups`
- `Working Files`
- `Queue Entries`
- `Intake / Inbox`
- `External Captures`
- `Recent linked prints` when relevant to the query

### 6.3 Result row anatomy

Each result row should show:

- primary label
- domain badge
- one-line reason or metadata snippet
- optional status pill
- one primary direct action
- one secondary jump action when the primary action is not itself the jump

Examples:

- `Gridfinity Bin v2` · `Catalog` · `Needs preview image` · `Open model`
- `Drawer Labels Pack` · `Working Group` · `4 model files · modified 18m ago` · `Open group`
- `Phone Dock Remix Pack` · `External` · `Medium confidence capture` · `Review capture`

### 6.4 Result actions

Results should support both:

- **open the object directly**
- **jump to the owning detailed surface**

Example:

- a model search result can open the model popup directly
- the adjacent jump control can send the user to filtered Catalog browse if they want surrounding context

### 6.5 Search modes

Recommended quick filters above the grouped results:

- `All`
- `Needs attention`
- `Recently changed`
- `Ready to print`
- `In intake`
- `External pending`

This makes search behave as both a finder and a fast operational filter tray.

---

## 7. Jump-to contracts

The landing page must provide **context-preserving jumps** into deeper surfaces.

Recommended jump map:

| Landing module | Jump target | Expected context |
| --- | --- | --- |
| Needs Attention: Catalog item | Catalog detail popup or filtered browser | model id + attention reason |
| Needs Attention: Working item | Working Files Groups view | group id or ungrouped filter |
| Needs Attention: Queue item | Unified Production Queue | queue entry id |
| Needs Attention: Intake item | Intake inbox or wizard job view | upload id / job id |
| Needs Attention: External item | External intake workbench | intake record id |
| Ready To Print | Unified Production Queue | entry id or planner preset |
| Working snapshot | Working Files card | target tab: `Groups`, `All`, `Ungrouped` |
| Catalog snapshot | Catalog browser | optional quality-state/search filters |
| External imports | External workbench | provider/channel filter |
| Recent linked print | Model detail popup `Prints` tab or print-history popup | model ref / archive id |

The page should not use vague buttons like `Open` for route-level actions. Prefer explicit labels like:

- `Jump to Working Groups`
- `Jump to Queue Planner`
- `Jump to External Intake`
- `Open Model Details`

---

## 8. Data model and backend needs

The landing page is a cross-domain projection. That means it likely needs a dedicated sidecar summary endpoint rather than fanning out many independent UI calls.

Recommended response sections:

- `summary`
- `attention_items[]`
- `ready_queue_items[]`
- `intake_waiting[]`
- `external_pending[]`
- `working_snapshot`
- `catalog_snapshot`
- `recent_activity[]`

### 7.1 Minimal response shape

```json
{
  "summary": {
    "catalog_models": 412,
    "working_groups": 37,
    "ungrouped_files": 23,
    "intake_waiting": 6,
    "queue_ready": 9,
    "external_pending": 4
  },
  "attention_items": [
    {
      "kind": "catalog_model",
      "ref": "gridfinity-bin--a1b2c3d4",
      "title": "Gridfinity Bin v2",
      "reason": "Needs preview image",
      "severity": "medium",
      "jump_target": "catalog_detail",
      "jump_context": {"model_id": "gridfinity-bin--a1b2c3d4", "reason": "needs_preview"}
    }
  ]
}
```

### 7.2 Layering rule

This projection belongs in the sidecar / joined-UI layer, not in print-history Layer 1 and not in ad hoc Home Assistant template joins.

The landing page is a classic Layer 2 composition surface:

- it joins several authorities
- it derives operator-facing summaries
- it produces UI-focused jump metadata

---

## 9. Interaction model

### 8.1 Desktop layout

Recommended 12-column responsive grid:

- search / summary hero spans full width
- Needs Attention spans 5 columns
- Ready To Print spans 4 columns
- Inbox / Intake Waiting spans 3 columns
- External Imports spans 4 columns
- Working Snapshot spans 4 columns
- Catalog Snapshot spans 4 columns
- Recent Activity spans full width

Two additional variants are worth preserving in the mockup set:

- **Compact / above-the-fold variant**: more dense, fewer words, stronger use of chips, micro-KPIs, and condensed action trays
- **Analytics / visual variant**: more charts, trend bars, health rings, and operational indicators with less explanatory copy

### 8.2 Mobile layout

Mobile should stack in this order:

1. Search
2. Primary quick actions
3. Needs Attention
4. Ready To Print
5. Inbox / Intake Waiting
6. External Imports
7. Working Snapshot
8. Catalog Snapshot
9. Recent Activity

Reason:

- mobile is operational first, browse second

### 8.3 Visual tone

The mockup should keep the existing design corpus language:

- dark translucent cards
- crisp badges and section headers
- strong domain-color accents
- compact but readable operational rows

It should feel related to the existing catalog / working / queue mockups, not like a separate product.

For denser variants, the dashboard should deliberately prefer:

- KPI tiles
- spark bars / health bars / progress rings
- compact list rows
- small domain-coded icon chips

over long explanatory text blocks.

---

## 10. Content priorities

If the page becomes too busy, cut in this order:

1. reduce Recent Activity density
2. reduce browse-entry marketing copy
3. collapse secondary counts and prose
4. move lower-priority details into search or popover trays
5. never remove Needs Attention, Ready To Print, Key Actions, or jump links

The page succeeds if it answers:

- what needs action now
- what is ready next
- what changed recently
- where do I go to handle it

---

## 11. Revised recommendations

Based on current feedback, the recommended baseline is:

1. universal search by default
2. idea-only entries excluded from Ready To Print by default
3. print-history-derived failures shown only when they affect the current workflow
4. local Intake and External Intake kept as distinct modules
5. direct-launch actions allowed for shallow, high-frequency tasks
6. keep a dedicated Intake workspace even if the dashboard can initiate intake directly
7. add a Key Actions module so operator intent is not forced to start from source/domain ownership
8. reduce text load in at least one dashboard variant by shifting emphasis toward KPI tiles and compact visual indicators

---

## 12. Open design decisions to walk through

These are the main decisions worth explicit review with the operator.

### 12.1 Which variant should be the baseline visual direction?

There are now three viable directions:

- balanced dashboard
- compact above-the-fold dashboard
- KPI / visual operations dashboard

This is now the most important open choice because the architectural questions are mostly settled.

### 12.2 Should the Key Actions module be fixed or adaptive?

Recommendation:

- adaptive, but with a stable top 2 or 3 anchors

Why:

- fully dynamic action placement can feel noisy
- fully static actions ignore actual operational context

### 12.3 How much search should happen inline before routing away?

Recommendation:

- support real grouped results inline
- route away only when the user explicitly wants the full owning surface

### 12.4 Should the dashboard show more charts by default?

Recommendation:

- yes, but only compact operational charts

Good candidates:

- queue-ready vs blocked bar
- working stage distribution bars
- intake throughput mini-trend
- external capture confidence split
- catalog quality-state donut or stacked bar

Avoid:

- decorative analytics that do not affect routing or action selection

### 12.5 Intake page vs. dashboard launch depth

Recommendation:

- direct-launch the intake wizard from the dashboard
- keep the intake page as the dedicated review/history workspace

This is the clean compromise between speed and structure.

### 12.6 One unified search, or segmented search by default?

Recommendation:

- default to one universal search bar with scope chips

Why:

- the landing page is cross-domain by definition
- forcing the user to choose a domain before typing adds friction

### 12.7 Should Ready To Print include idea-only entries?

Recommendation:

- no, not by default
- keep idea-only entries in a clearly distinct queue/inbox slice

Why:

- "ready" should mean physically actionable

### 12.8 Should the landing page show print-history failures directly?

Recommendation:

- yes, only when they affect the queue or model workflow
- no, not as a full print-history feed

Why:

- the landing page is model-catalog-centric, not archive-centric

### 12.9 Should Intake and External Capture remain separate blocks?

Recommendation:

- yes

Why:

- local file intake and external-provider capture are operationally different and need different jumps

### 12.10 Should quick actions launch modals from the landing page, or always jump away?

Recommendation:

- allow only the safest immediate actions inline: `Upload / Intake`, `Capture URL`
- deeper work should jump away

Why:

- keeps the landing page from becoming another half-implemented workspace

---

## 13. Recommended next implementation slice

If this design is accepted, the best implementation order is:

1. create a single summary endpoint for the landing page projection
2. implement the shell card with search, KPI strip, and section layout
3. wire `Needs Attention` and `Working Snapshot` first
4. add queue and intake blocks
5. add external-import block and recent-activity rail last

This sequencing de-risks the page because it starts with the most distinctive value: cross-domain attention routing.