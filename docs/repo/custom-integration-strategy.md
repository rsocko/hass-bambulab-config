# Custom Integration Strategy

This note captures the current architectural assessment of this repository and outlines a practical go-forward strategy for packaging, reuse, and long-term maintainability.

It is intentionally opinionated. The goal is not to convert everything into Python because that sounds more "productized". The goal is to move only the parts that benefit from becoming custom integrations, while preserving the parts that are already well-served by Home Assistant packages, Lovelace YAML, blueprints, and existing third-party integrations.

---

## Executive Summary

This repository is primarily a **Home Assistant application layer** built on top of:

- `ha-bambulab`
- `Spoolman`
- `WLED`
- `OpenHASP`
- `Bambuddy`
- Lovelace + HACS frontend cards

It is **not** best modeled as many separate custom integrations.

Current recommendation:

1. Build **one custom integration now**: `bambuddy`
2. Keep the **dashboard/application shell in YAML**
3. Keep **user-policy orchestration** in YAML automations or transition selected flows to **blueprints**
4. Reassess later whether a **second integration** is justified for printer orchestration and derived-state logic

Current recommendation on count:

- **Now**: 1 integration
- **Later if needed**: 2 integrations total
- **Not recommended**: splitting the current repository into many backend integrations

---

## Current Repo Shape

At a high level, the repository already separates into three layers.

### 1. Backend / domain adapters

These are the pieces that talk to external APIs or maintain derived domain state.

Examples:

- `bambuddy_common`
- `print_history`
- `print_queue`
- `print_statistics`
- `printer_maintenance`
- parts of `core`
- parts of `spoolman_sync`

### 2. Orchestration / policy

These are the pieces that decide what should happen in response to events.

Examples:

- notifications
- WLED reactions
- maintenance reminders
- print-complete side effects
- selected printer-state-driven automations

### 3. Presentation / UI composition

These are the pieces that assemble dashboards and interactive views.

Examples:

- `common`
- `printer_dashboards`
- `dashboard_cards`
- `dashboard_views`
- `www/` assets
- HACS card dependencies

That layering is already reflected in the package structure and loader map under:

- `homeassistant/packages/3d_printing/_feature_loaders.yaml`
- `docs/repo/deployment-structure.md`
- `docs/repo/repo-layout.md`

---

## What Should Become a Custom Integration

### Strong candidate now: `bambuddy`

`Bambuddy` is the clearest and strongest custom integration candidate in the repository.

Why it fits:

- it has a clear external API boundary
- it already has a package split that maps well to integration concepts
- it owns real backend concerns: auth, API calls, polling, webhook normalization, queue/archive/stats/maintenance reads and actions
- it is currently carrying complexity in REST commands, REST sensors, helper state, and orchestration that would be cleaner as native Python entities/services/coordinators

Recommended `bambuddy` integration responsibilities:

- config flow and options flow
- API client and auth management
- polling coordinators / webhook event normalization
- native entities for queue, print history, statistics, maintenance, sync/result state, and other backend-owned state
- integration services for Bambuddy-specific actions
- diagnostics and structured logging

What should move out of YAML into the integration:

- Bambuddy REST commands
- most Bambuddy REST sensors
- helper entities used only to store Bambuddy configuration or transport intermediate state
- backend refresh logic that exists only to glue the API to Home Assistant

Concrete example now implemented in this repo:

- the Bambuddy partial-usage review flow keeps review policy in YAML
- but the runtime-repair sidecar base URL and bearer token now live on the
	Bambuddy config entry
- YAML automations call an integration service boundary
	(`bambuddy.estimate_partial_usage`) instead of a raw credentialed
	`rest_command`

What should remain outside the integration:

- dashboard YAML
- dashboard card composition
- blueprints / automations that consume Bambuddy entities and services
- optional custom cards

---

## What Should Stay as YAML / Lovelace

The dashboard and UI composition layer should remain YAML-first.

This includes:

- `common`
- `printer_dashboards`
- most `dashboard_cards`
- most `dashboard_views`
- shared button-card templates
- view composition and popup composition
- custom resource registration patterns

Reasons to keep this layer in YAML:

- it is already modular and maintainable
- users can inspect and customize it directly
- Home Assistant natively supports YAML dashboards
- it can continue to consume built-in cards, HACS cards, and any future custom cards
- turning UI composition into Python would add cost without improving the core domain model

This repo already documents the YAML dashboard/resource model in:

- `docs/repo/dashboard-deployment-behavior.md`
- `docs/features/common/README.md`

---

## What Should Stay as Automations or Become Blueprints

Not all event-driven logic belongs in a custom integration.

Keep as YAML automations or transition to blueprints when the behavior is mostly **user policy** rather than backend product logic.

Examples:

- notifications
- WLED reactions
- room-lighting side effects
- maintenance reminders with user-specific thresholds or channels
- post-print household workflows
- tablet/openhasp-facing scene or workflow behavior

Why:

- users may want to customize timing, routing, thresholds, and side effects
- automations and scripts provide native traceability in Home Assistant
- blueprints are a better sharing mechanism for reusable user workflows than burying those flows inside Python code

Use a blueprint when:

- the workflow is reusable across users
- it needs a small number of configurable inputs
- it should remain user-editable and visible in HA

Keep it as raw YAML automation when:

- it is highly site-specific
- it is still changing rapidly
- it would not generalize cleanly into blueprint inputs

---

## Should There Be a Second Integration?

### Maybe later: printer orchestration / derived-state integration

There is a possible future second integration if the current YAML/template/helper layer around printer orchestration becomes too costly to maintain.

Likely scope if this becomes necessary:

- smart-status modeling
- printer-derived entities
- spool/tray matching and correlation logic
- selected event-listener behavior tightly coupled to printer domain state
- selected backend-side command surfaces that are not really user-policy automations

This likely pulls from:

- `core`
- `spoolman_sync`
- selected backend logic from `error_alerts`
- possibly a narrow subset of `printer_controls`

### Do not build this second integration yet unless there is a real maintenance problem

Good reasons to add the second integration later:

- templates have become too complex or fragile
- helper/entity sprawl is hard to reason about
- state derivation is duplicated in too many places
- performance issues are caused by large template recomputation chains
- backend orchestration logic is hard to test and debug in YAML

Bad reasons:

- "more Python must be better"
- "it would look more like a product"
- "we want fewer YAML files"

---

## Recommended Integration Count

### Recommended now

- **1 integration**: `bambuddy`

### Recommended long-term ceiling unless the product surface changes materially

- **2 integrations total**

### Not recommended

- a separate integration for every current package
- treating dashboard/UI packages as backend integrations
- splitting into several tightly coupled micro-integrations with heavy cross-dependencies

Why not many integrations:

- the repo is one coherent Home Assistant solution, not several independent products
- too many integrations would increase install complexity and support burden
- HACS and HA UX work better when backend boundaries are meaningful
- many current packages are application-shell or policy layers, not integration boundaries

---

## Packaging Guidance

### Recommended packaging model

1. **Custom integration repo** for `bambuddy`
2. **YAML dashboard/application layer** remains in this style of package/Lovelace structure
3. **Blueprints** for reusable policy/workflow automations
4. **Optional separate frontend plugin repo** only if a truly reusable custom JS card is created

### Why not force everything into one HACS integration repo

Because Home Assistant and HACS treat these as different surfaces:

- custom integrations
- Lovelace dashboards/views/resources
- blueprints
- dashboard plugins / custom cards

Trying to make one integration repo "own" all YAML, dashboards, blueprints, and frontend assets usually creates more friction than value.

---

## Design Rules of Thumb

### Move something into an integration when it is:

- backend-owned state
- external API communication
- durable domain modeling
- config-flow-worthy setup/configuration
- a reusable service/API surface
- easier to validate and maintain in Python than in templates/helpers/scripts

### Keep something in YAML when it is:

- Lovelace composition
- dashboard layout
- card/view assembly
- site-specific workflow orchestration
- fast-moving glue logic that benefits from easy local edits

### Prefer blueprints when it is:

- reusable user workflow logic
- parameterized automation or script behavior
- something users should be able to configure without editing Python

### Consider a second integration only when:

- the orchestration/derived-state layer has become a clear backend subsystem in its own right
- there is measurable maintenance or performance pain in staying YAML-first

---

## Proposed Go-Forward Plan

### Phase A — Productize Bambuddy first

Build one custom integration for Bambuddy and let it absorb the current API-heavy YAML surface.

Deliverables:

- config flow
- options flow
- entities
- services
- diagnostics
- polling / webhook normalization

### Phase B — Keep dashboards and UI package-first

Continue using Lovelace YAML and existing HACS cards for:

- dashboard composition
- feature views
- popups
- styling and card templates

### Phase C — Extract reusable policy into blueprints

Start with flows that are clearly reusable across users, such as:

- print-complete notifications
- print-failed notifications
- selected maintenance alerts
- selected printer-state-driven auxiliary reactions

### Phase D — Reassess orchestration boundary later

Only after Bambuddy is stable, evaluate whether the printer-derived-state layer should remain YAML-based or evolve into a second integration.

---

## Non-Goals / Anti-Patterns

The following are **not** recommended goals for this repository.

### 1. Do not convert the whole repo into Python

That would collapse UI composition, policy orchestration, and backend modeling into one layer and make the system harder to customize.

### 2. Do not use a custom integration as a general-purpose YAML file installer

Even if technically possible, having the integration create package files, dashboard YAML, or other user config files is not a clean architectural model.

### 3. Do not create many small tightly coupled integrations

If multiple "integrations" cannot be reasonably installed, versioned, and understood independently, they are probably not real integration boundaries.

---

## Proposed Classification Snapshot

### Move into `bambuddy` integration now

- `bambuddy_common`
- backend portions of `print_history`
- future `print_queue`
- future `print_statistics`
- future `printer_maintenance`

### Keep YAML / Lovelace long-term

- `common`
- `printer_dashboards`
- most `dashboard_cards`
- most `dashboard_views`
- most UI composition and popup design

### Keep as YAML or convert to blueprints

- `notifications`
- most `printer_led`
- most `wled`
- selected `error_alerts` side effects
- selected site-specific printer workflows

### Reassess later for possible second integration

- `core`
- `spoolman_sync`
- selected derived-state and orchestration logic around the printer domain

---

## Bottom Line

This repository should be treated as:

- **one clear backend integration opportunity now** (`bambuddy`)
- **one possible later backend integration opportunity** if printer orchestration complexity justifies it
- **a continuing YAML-first Home Assistant application shell** for dashboards, composition, and user-policy workflows

That is the lowest-risk path that improves maintainability without destroying the flexibility that makes the current repository effective.