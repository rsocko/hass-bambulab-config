# Development Home Assistant Strategy For Bambuddy

## Purpose

This document describes how to shift Bambuddy and print-history development from the current production-first flow to a Development Home Assistant instance while preserving a safe path to production.

It covers:

- what the Development Home Assistant instance needs
- what Bambuddy and print-history configuration needs to differ from production
- whether two Home Assistant instances can point `ha-bambulab` at the same physical printer
- CI/CD changes required for explicit `dev` and `prod` targeting
- rollout stages and promotion gates for production deploys

It does not implement the workflow changes. It defines the target operating model before those changes are made.

## Current-State Assumptions

The current repository and deployment model assume a single Home Assistant target in several important places.

- The deployable Home Assistant root is [README](../../../homeassistant/README.md).
- Package loading is driven by [homeassistant/packages/3d_printing/_feature_loaders.yaml](../..//homeassistant/packages/3d_printing/_feature_loaders.yaml).
- The main deploy workflow is [.github/workflows/deploy-homeassistant-template.yml](../../.github/workflows/deploy-homeassistant-template.yml).
- Push-triggered deploy dispatch is controlled by [.github/workflows/auto-dispatch-homeassistant-deploy.yml](../../.github/workflows/auto-dispatch-homeassistant-deploy.yml) and [.github/deploy/auto-deploy.env](../../.github/deploy/auto-deploy.env).
- Lovelace resource versioning and runtime registration are controlled by [Dashboard Deployment Behavior](/docs/repo/reference/dashboard-deployment-behavior.md) and [homeassistant/packages/3d_printing/common/dashboards/_resources.yaml](../../../homeassistant/packages/3d_printing/common/dashboards/_resources.yaml).

Additional current-state assumptions for this strategy:

- The Development Home Assistant instance is a separate Home Assistant deployment running in Docker on your Docker host.
- You want deploy tooling to be able to target either Development or Production Home Assistant explicitly.
- You expect Development Home Assistant to connect to the real printer for end-to-end validation when needed.
- You are not yet asking for the workflow code changes themselves. This document is the implementation plan and operating policy.

## Why Separate Dev HA Is The Right Boundary

For this repository, a separate Home Assistant instance is the correct isolation boundary.

The repo-local `bambuddy` integration is intentionally single-instance per Home Assistant. That is enforced in [homeassistant/custom_components/bambuddy/config_flow.py](../../homeassistant/custom_components/bambuddy/config_flow.py), where the config flow aborts with `single_instance_allowed` if an entry already exists.

That means:

- one HA instance can host one Bambuddy config entry
- two HA instances can each host their own Bambuddy config entry
- trying to model `dev` and `prod` Bambuddy side-by-side inside one HA instance is the wrong shape for this repo

Because your Development Home Assistant is already a separate Docker-hosted instance, the topology is aligned with the repo's current integration boundary rather than fighting it.

## Target Architecture

The recommended target architecture is:

```text
GitHub Actions / self-hosted runner
  -> explicit deploy target: dev or prod
  -> sync repo-managed HA config and www assets

Development Home Assistant
  -> same package-loader structure as prod
  -> its own Bambuddy config entry
  -> optional access to real printer through ha-bambulab
  -> dev-first validation for dashboards, package wiring, browser/backend changes

Production Home Assistant
  -> remains authoritative for normal operation
  -> receives promoted, validated changes only
```

Recommended operating posture:

- Development Home Assistant becomes the default validation target for Bambuddy and print-history work.
- Production Home Assistant remains the default authoritative runtime until the dev-first process is proven stable.
- Printer-affecting write automations should not be active in both environments at the same time without explicit gating.

## Required Setup On Development HA

### Base Home Assistant Wiring

Development Home Assistant should mirror the same package-loader wiring used by production.

In `configuration.yaml`, it should load:

```yaml
homeassistant:
  packages: !include packages/3d_printing/_feature_loaders.yaml
```

That contract is described in [README](../../../homeassistant/README.md).

### Required Packages And Loaders

At minimum, Development Home Assistant should load the same foundation packages as production and the Bambuddy/print-history packages under active development.

Recommended minimum loader set:

- `core_loader`
- `common_loader`
- `bambuddy_common_loader`
- `print_history_loader`
- `print_statistics_loader` if statistics behavior is part of the test surface

The active loader map lives in [homeassistant/packages/3d_printing/_feature_loaders.yaml](../../homeassistant/packages/3d_printing/_feature_loaders.yaml).

### Required Integrations And Services

Development Home Assistant should have the following installed and configured:

- `ha-bambulab`
- the repo-local `bambuddy` custom integration from [homeassistant/custom_components/bambuddy](../../homeassistant/custom_components/bambuddy)
- MQTT access if Bambuddy status/webhook-adjacent flows depend on it
- Spoolman if archive enrichment, spool matching, or filament-derived tags are being validated
- a usable camera entity if photo capture or image-linked flows are part of the test plan

Optional but often needed:

- matching dashboard custom cards/resources registered through `_resources.yaml`
- any helper entities referenced by active print-history cards or popup flows

### Dev-Specific Secrets And Config

Development Home Assistant needs its own environment-specific values even if it reaches shared services.

That includes:

- Bambuddy API key
- Bambuddy base URL
- runtime repair token and base URL if used
- Home Assistant supervisor token for workflow-driven validation
- SSH connectivity and known-hosts for deploys
- helper values like printer ID, base URLs, and any environment role toggles

Do not rely on one global repository-level HA target secret for both environments.

## Bambuddy And Print-History Configuration Differences

The dev instance should start as a near-mirror of production for package and component shape, but not necessarily for automation authority.

Recommended initial differences:

| Area | Development HA | Production HA |
|---|---|---|
| Deploy target | Explicit manual target | Explicit manual target |
| Bambuddy config entry | Separate dev HA entry | Existing prod entry |
| Printer-facing write automations | Off or gated initially | On |
| Archive mutation authority | Limited during early rollout | Primary |
| Photo capture | Optional or test-window only at first | Primary |
| Enrichment writes | Optional or gated at first | Primary |
| Notifications | Reduced/noisy items disabled | Normal |

### Recommended Gating Model

Before Development HA is allowed to exercise full end-to-end flows, introduce an environment-aware gating model for write-side behavior.

Examples:

- helper booleans that enable or disable archive mutation automations
- helper booleans that enable photo capture/upload automations
- helper booleans that enable enrichment or Spoolman write-back flows
- feature-loader level enablement if a whole feature should stay inactive in dev

Preferred rule:

- only one HA instance should be considered the active writer for printer/archive-affecting automations at a time

Without that rule, dual-HA testing against the same printer will create duplicate side effects.

## Can Two Home Assistant Instances Use ha-bambulab Against The Same Printer?

### Short Answer

Probably yes, but treat it as operationally sensitive rather than automatically safe.

### What We Can Say With Confidence

- This repository depends heavily on `ha-bambulab` entities and triggers.
- The upstream integration appears to support multiple config entries in general and tracks printers by serial.
- Within a single HA instance, upstream setup logic is designed to avoid blindly duplicating the same printer registration.
- There is no repo-local evidence of a hard prohibition against two separate Home Assistant instances connecting to the same physical printer.

### Practical Assessment

Using `ha-bambulab` from both Development and Production Home Assistant against the same printer is likely workable for observation and validation, especially if one environment is mostly read-only.

The risk is not just connection success. The risk is duplicated behavior:

- duplicate control commands
- duplicate print-start and print-complete automations
- duplicate camera and timelapse-related actions
- duplicate archive binding attempts
- duplicate Bambuddy archive mutations
- duplicate Spoolman updates
- duplicate notifications

### Recommended Policy

Use this rule set:

1. Both HA instances may connect to the printer.
2. Only one HA instance should be the normal authoritative writer/controller.
3. Development HA should begin with observation-first validation.
4. Full end-to-end tests on Development HA should happen during explicit test windows or after prod-side equivalents are gated off.

This keeps dev useful without turning live printing into a race between two automation stacks.

## Gotchas And Operational Risks

### 1. Duplicate Automation Side Effects

This is the main risk.

If both Home Assistant instances react to the same print events, they may both:

- resolve current archive IDs
- upload photos
- enrich archives
- write tags and notes
- trigger notifications

That can corrupt the operational signal even if nothing outright crashes.

### 2. Shared Backend Mutation Confusion

If dev and prod point at the same Bambuddy service or the same Spoolman instance, Development HA may mutate shared operational data while you are only trying to validate UI or browser behavior.

Recommended progression:

- early stage: shared backend is acceptable only for read-heavy validation
- later stage: consider dedicated dev Bambuddy and possibly dedicated dev Spoolman before sustained write testing

### 3. Resource Version Drift Still Applies

Dev-first deployment does not remove the Lovelace resource versioning contract.

When a tracked JS resource under `homeassistant/www/**` changes:

- bump the matching `?v=` URL in `_resources.yaml`
- ensure the deploy includes `www` content when needed
- ensure the workflow syncs the live resource registry correctly
- hard refresh the browser after deploy

This contract is documented in [Dashboard Deployment Behavior](/docs/repo/reference/dashboard-deployment-behavior.md).

### 4. Single-Target Workflow Assumptions

The current deploy workflow resolves HA connection details from a single target model.

Until that is changed, the biggest process risk is deploying dev-intended changes to prod or vice versa.

### 5. Feature-Loader Drift Between Environments

If Development HA and Production HA intentionally load different subsets of packages, differences in behavior may be explained by loader drift rather than the code under test.

Avoid unnecessary divergence. Keep the package shape aligned and gate behavior explicitly where needed.

### 6. Restart And Validation Differences

Some changes only become trustworthy after restart-based validation, especially when resources or registration behavior are involved. The existing deploy workflow already has resource re-verification behavior after restart. That discipline should remain stricter in prod than in dev.

## CI/CD Changes Required

### Objective

Make deployment environment-aware so a run can target either Development or Production Home Assistant explicitly.

### Recommended Model

Use GitHub Environments:

- `dev`
- `prod`

Store environment-scoped values there rather than relying on one global HA target.

Examples of environment-specific values:

- `HA_HOST`
- `HA_SSH_PORT`
- `HA_SSH_USER`
- `HA_CONFIG_PATH`
- `HA_SSH_KNOWN_HOSTS`
- supervisor token
- SSH key path or equivalent runner-side identity selection

### Workflow Changes

Update the main deploy workflow in [.github/workflows/deploy-homeassistant-template.yml](../../.github/workflows/deploy-homeassistant-template.yml) so it accepts an explicit target environment input and resolves the correct host, secrets, and validation behavior for that environment.

Update the wrapper workflow in [.github/workflows/auto-dispatch-homeassistant-deploy.yml](../../.github/workflows/auto-dispatch-homeassistant-deploy.yml) so any push-triggered behavior is explicit about whether it can target `dev`, `prod`, or neither.

Update [.github/deploy/auto-deploy.env](../../.github/deploy/auto-deploy.env) so branch-driven behavior no longer assumes one implicit Home Assistant target.

### Deployment Policy Recommendation

Recommended initial policy:

- Development deploys: manual dispatch only, explicit `dev` target
- Production deploys: manual dispatch only, explicit `prod` target
- Automatic push-triggered production deploys: leave disabled until the new environment-aware process is stable

That policy can relax later, but it is the safest starting point.

### Resource Sync And Cache-Busting

Do not fork the resource process for dev versus prod. Keep the same repo-managed source of truth and run the same safety checks per environment.

Important existing contracts to preserve:

- `_resources.yaml` remains the source of truth
- `www` deploy scope must match the change surface
- resource sync must survive HA restart
- browser hard refresh remains part of the deploy checklist for JS changes

## Recommended Rollout Stages

### Stage 0: Environment Preparation

Prepare Development HA so it can parse and load the same package structure as prod.

Exit criteria:

- loader include wiring is valid
- custom component is installed
- target packages load successfully
- dashboard resources register correctly

### Stage 1: Dev UI And Read-Path Validation

Use Development HA for:

- dashboard/card changes
- popup/view rendering
- browser/backend query flows
- print-history local store read behavior

Keep write-heavy automations gated off initially.

Exit criteria:

- print-history browser works on dev
- archive detail and popup flows render correctly
- deploy workflow can target dev reliably

### Stage 2: Controlled End-To-End Printer Validation

Enable live-printer testing from Development HA in controlled windows.

Scope may include:

- `ha-bambulab` live status and device data
- archive binding
- webhook handling
- photo upload testing
- enrichment testing

Exit criteria:

- no duplicate side effects from dev and prod during the same test
- live printer flows behave predictably
- rollback to prod-only authority is easy

### Stage 3: Manual Promotion To Production

Promote validated changes to Production HA with an explicit `prod` deploy.

Recommended process:

1. run dry-run against `prod`
2. run real deploy against `prod`
3. use change-appropriate reload or restart mode
4. hard refresh browser if JS resource URLs changed

### Stage 4: Reassess Automation

Only after repeated successful dev-first cycles should you reconsider any automatic deploy behavior.

Even then, keep production stricter than development.

## Production Promotion Rules

Use the following guidance for when to ship from dev to prod.

### Safe Early Promotion Candidates

- dashboard-only layout changes
- style changes
- print-history browser rendering changes
- resource version bumps after verified dev deploy

### Requires Stronger Validation

- Bambuddy backend/API behavior changes
- archive mutation paths
- startup automations
- photo upload/capture changes
- enrichment or Spoolman write-back logic
- feature-loader wiring changes

### Requires Production Caution

- anything that changes printer control behavior
- anything that changes when automations fire during live prints
- anything that could mutate shared production service state during test runs

## Recommended First Implementation Steps

After this document is accepted, the next implementation steps should be:

1. add this dev/prod strategy to the repo docs index
2. modify the deploy workflow to accept explicit environment selection
3. introduce environment-scoped GitHub secrets and variables
4. stand up and verify Development HA with matching package-loader wiring
5. add environment-aware gating for write-side Bambuddy and print-history automations
6. switch day-to-day validation of Bambuddy and print-history work to Development HA first

## Open Decisions Intentionally Deferred

These decisions should be made after the environment-aware deploy groundwork exists:

- whether dev Bambuddy should stay shared with prod temporarily or become dedicated quickly
- whether dev Spoolman should be shared or separate
- whether feature-branch auto-deploy to dev is worth enabling later
- which specific automations should be helper-gated versus loader-gated

## References

- [README](../../../homeassistant/README.md)
- [homeassistant/packages/3d_printing/_feature_loaders.yaml](../../../homeassistant/packages/3d_printing/_feature_loaders.yaml)
- [homeassistant/custom_components/bambuddy/config_flow.py](../../../homeassistant/custom_components/bambuddy/config_flow.py)
- [Deployment Workflow Reference](/docs/repo/reference/deployment-workflow-reference.md)
- [Deployment Structure](/docs/repo/reference/deployment-structure.md)
- [Dashboard Deployment Behavior](/docs/repo/reference/dashboard-deployment-behavior.md)