# Phase 5 End-State UI And Handoff Design

> **Status**: Forward-looking design companion
> **Created**: 2026-04-30
> **Scope**: End-state UI direction that connects Wave 4 surfaces to later Phase 5 and Phase 6 work
> **Primary Drivers**: #1163, #1137, #1132, #1133, #1149, #1146, #213
>
> **Historical note (2026-05-01)**: The concrete Home Assistant dashboard implementation moved away from the hidden-subview child-view shell assumed here. The shipped UI now uses a single top-level `Model Catalog` view with helper-backed internal workspace navigation to preserve the global dashboard tabs.

---

## Purpose

Show how the Wave 4 intake and Working surfaces extend into the broader end-state product without forcing later-scope implementation into the first HA UI slice.

This document answers three questions:

1. Which Wave 4 surfaces must be designed to grow into publish and lineage flows?
2. Which future popups and screens are inevitable once preview promotion, supporting-asset import, and revision lineage land?
3. How should deployment, cleanup, and local-library intake concerns appear in the UI without fracturing the overall operator model?

---

## Relationship To Wave 4

Wave 4 establishes the first durable UI shell:

- Intake Home
- Intake Submission
- Inbox / Queue Review
- Working Board
- Working Group Detail
- Link Management
- Batch Result Summary

The later end-state should expand these same surfaces rather than replacing them.

Navigation assumption carried forward from Wave 4:

- `Model Catalog Home` remains the visible parent view in the global 3D Printing dashboard
- `Intake Home`, `Inbox Review`, `Working Board`, and the curated browser remain durable hidden child views/pages under Model Catalog
- publish, preview-promotion, asset-selection, and lineage flows layer on top as popups or drill-in subflows launched from those views
- the end-state should not collapse the intake workflow back into a single modal-only interaction

### Navigation Contract Carried Forward

Use multiple hidden views plus navigation cards/buttons plus `browser_mod` navigation for smooth transitions.

This preserves:

- real URLs and deep links for operator handoff and debugging
- clean YAML separation so each major Model Catalog surface stays independently versioned
- fast transitions without iframe-style compromises
- a navigation pattern that matches Home Assistant's native view model

Recommended navigation action pattern:

```yaml
tap_action:
	action: fire-dom-event
	browser_mod:
		command: navigate
		navigation_path: /dashboard-3d-printing/model-catalog-intake
```

Use the same pattern for `Curated`, `Working`, and `Inbox` child views from `Model Catalog Home` and from any cross-links between child views.

```text
Wave 4 shell
├─ Model Catalog Home
├─ Hidden child views for intake, inbox, working, and curated browsing
├─ Working board and detail
└─ Curated-link visibility

Future expansion
├─ Publish review and outcome selection
├─ Preview promotion and supporting-asset selection
├─ Revision lineage decisions
├─ Cleanup audit and retry history
└─ Remote / OneDrive / local-library intake variants
```

---

## End-State Surface Map

| Surface | First Appears | Future Expansion |
|---|---|---|
| Model Catalog Home | Wave 4 | richer cross-links, summary badges, remote-source presets, deployment health |
| Intake Home | Wave 4 | remote-client badges, volume health, OneDrive/local-library presets |
| Inbox Review | Wave 4 | publish recommendations, lineage hints, provenance confidence |
| Working Group Detail | Wave 4 | project context, publish readiness, preview candidates, revision lineage |
| Link Management | Wave 4 | richer relationship types, supersedes/canonical revision decisions |
| Publish Review Popup | Future | new screen anchored from Working Group Detail |
| Preview Promotion Picker | Future | subflow within publish review |
| Supporting Asset Picker | Future | subflow within publish review |
| Cleanup Audit Detail | Future | extension of result-summary panel |
| Import Source Presets | Future | extension of Intake Home / Submission |

### Shared State Carried Forward

The end-state should keep the same split defined in Wave 4:

- share durable operator preferences and cross-view summary entities
- keep transient selection and popup-local interaction state inside the active child view

That allows future publish, lineage, and import-presets flows to reuse the same helper/entity contract instead of inventing a separate navigation-state layer.

### Curated Browser Shell Carried Forward

The current core Model Catalog browser should also converge on the same browser-shell language as Print History.

Carry these rules forward beyond Wave 4:

- keep top and bottom page toolbars around long-lived browser lists
- keep `Compact`, `Media`, and `List` as the standard view-style vocabulary for curated browsing
- keep filter bars structured and always visible, with a single `Clear Filters` action
- keep `Query` as the primary text-search label rather than restoring a separate search-submit workflow
- keep bulk discovery/import inside intake-owned surfaces instead of appending it beneath curated browsing
- keep maintenance sync/reindex actions out of the main browsing chrome unless a later external-source workflow truly needs them

This ensures the Model Catalog domain reads as one coherent product rather than a mix of older Manyfold-era cards and newer Phase 5 intake surfaces.

---

## End-State Flow 1: Working Group To Publish Review

### Purpose

Extend the Working Group Detail popup into a deliberate publish-review workflow once #1132, #1133, #1163, and #1137 are implemented.

### Flow Summary

1. Operator opens Working Group Detail.
2. System shows readiness indicators and duplicate/revision warnings.
3. Operator launches Publish Review.
4. Operator chooses publish outcome.
5. Operator reviews preview and supporting assets.
6. Operator confirms lineage and project placement.
7. Publish result summary returns operator to the same group context.

### Mid-Fidelity Mockup

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Publish Review: Bit Holder Remix                                 [Close]    │
├──────────────────────────────────────────────────────────────────────────────┤
│ Outcome                                                                     │
│ (•) New canonical revision                                                  │
│ ( ) Add as additional file / variant                                        │
│ ( ) Keep separate curated model                                             │
│                                                                              │
│ Reconciliation                                                               │
│ existing curated match: Gridfinity Bit Holder v2                            │
│ basis: source URL + linked archives + filename overlap                      │
│                                                                              │
│ Preview + Assets                                                             │
│ extracted previews: 3   supporting assets: 4 allowlisted                    │
│ [Review Preview] [Review Assets]                                            │
│                                                                              │
│ Project                                                                      │
│ [ Existing Project: Gridfinity Family ▼ ]  [Create New Project]             │
│                                                                              │
│ [Publish] [Cancel]                                                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Design Guardrail

The publish-review surface must feel like an extension of Working Group Detail, not a separate application.

---

## End-State Flow 2: Preview Promotion Picker

### Drivers

- #1163
- #1137

### Purpose

Allow explicit promotion of an extracted preview to curated preview without silent replacement.

### Mid-Fidelity Mockup

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Choose Curated Preview                                           [Close]    │
├──────────────────────────────────────────────────────────────────────────────┤
│ Current curated preview: Bit Holder v2 cover                                │
│ Replacement policy: [ Ask Every Time ▼ ]                                    │
│                                                                              │
│ Candidate previews                                                           │
│ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐              │
│ │ plate_1.png      │ │ top_view.png     │ │ thumbnail.png    │              │
│ │ default candidate│ │ extracted alt    │ │ legacy fallback  │              │
│ │ [Select]         │ │ [Select]         │ │ [Select]         │              │
│ └──────────────────┘ └──────────────────┘ └──────────────────┘              │
│                                                                              │
│ [Use Selected Preview] [Cancel]                                             │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Design Guardrails

- show replacement behavior explicitly
- keep raw model payload members out of this picker
- preserve the analysis revision used for the decision

---

## End-State Flow 3: Supporting-Asset Picker

### Purpose

Choose which allowlisted supporting assets should accompany publish.

### Mid-Fidelity Mockup

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Supporting Assets For Publish                                    [Close]    │
├──────────────────────────────────────────────────────────────────────────────┤
│ Only allowlisted support artifacts are eligible.                            │
│                                                                              │
│ ☑ assembly-guide.pdf      PDF        from sibling file                      │
│ ☑ label.svg               SVG        from working assets                    │
│ ☐ print-notes.md          Markdown   keep sidecar-only                      │
│ ☐ plate_1.json            JSON       metadata only, do not publish          │
│                                                                              │
│ Import policy: [Opt-in selected only ▼]                                     │
│                                                                              │
│ [Attach Selected Assets] [Cancel]                                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Guardrails

- keep allowlist boundaries visible in the UI
- distinguish embedded resources from sibling files
- make the default conservative

---

## End-State Flow 4: Revision Lineage And Project Context

### Drivers

- #1132
- #1133

### Purpose

Expand link management and publish review with explicit lineage outcomes.

### UI Direction

- extend existing `mc-curated-link-row` with lineage badges
- add project badge and project selector to Working Group Detail header
- add a `Lineage` section to Publish Review rather than a separate standalone screen

### Lineage States

- `canonical revision`
- `supersedes`
- `superseded_by`
- `additional variant`
- `separate but related`

These should remain operator-reviewed decisions, not inferred auto-labels.

---

## End-State Flow 5: Cleanup Audit And Retry

### Drivers

- #1146
- #1149

### Purpose

Turn Wave 4 queue/result summaries into a more detailed audit trail when cleanup policy becomes operationally important.

### Mid-Fidelity Mockup

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Cleanup Audit: April Wave 4 samples                               [Close]   │
├──────────────────────────────────────────────────────────────────────────────┤
│ policy: replace_with_stub   root: /Working/remixes   verified: yes          │
│                                                                              │
│ ✓ holder_v3.3mf      replaced with stub   10:42                              │
│ ✓ label.svg          kept                  not eligible                       │
│ ✕ refs/photo.jpg     failed: access denied  retry available                  │
│                                                                              │
│ [Retry Failed Cleanup] [Open Deployment Guide]                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Design Guardrails

- cleanup is always downstream of verified upload
- failures must be reviewable without implying upload rollback
- deployment and allowlisted-root context should be close at hand

---

## End-State Flow 6: Local Library / OneDrive Intake

### Drivers

- #213
- #1149

### Purpose

Treat OneDrive or other local-library imports as a source preset layered onto the same intake shell rather than as a separate product.

### UI Direction

- add intake source presets on Intake Home: `browser upload`, `server browse`, `local library`, `remote client`
- preserve the same inbox and queue review surfaces
- surface collection and sub-collection hints when folder hierarchy suggests them

### Mid-Fidelity Mockup

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Intake Source Presets                                                       │
├──────────────────────────────────────────────────────────────────────────────┤
│ [ Browser Upload ] [ Server Browse ] [ Local Library ] [ Remote Client ]    │
│                                                                              │
│ Local Library preset                                                         │
│ root: OneDrive/3D Models                                                     │
│ collection hint: derive from top-level folder [x]                            │
│ sub-collection hint: derive from second-level folder [x]                     │
│                                                                              │
│ [Open Browse Picker] [Save As Default Preset]                                │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## End-State Component Extensions

The Wave 4 component system should be built so these future additions remain additive:

| Wave 4 Component | Future Extension |
|---|---|
| `mc-working-group-card` | publish-readiness and project badges |
| `mc-curated-link-row` | lineage-type badge and revision warning |
| `mc-result-summary-panel` | audit drill-in and retry buttons |
| `mc-source-mode-toggle` | presets for local library and remote client |
| `mc-file-member-table` | publish eligibility and asset classification columns |
| `mc-validation-banner` | publish conflict and provenance warnings |

---

## Documentation And Validation Handoff

### UI-Adjacent Docs That Should Link Here

- deployment/runtime guide for queue volume and remote-client flows
- [phase-5-publish-preview-and-supporting-assets-design.md](phase-5-publish-preview-and-supporting-assets-design.md)
- enhanced Working/lineage design doc when created

### What This Doc Does Not Require Yet

- final service payload definitions for publish
- exact project schema implementation
- OneDrive transport details
- full operator permissions model

Those can still evolve as long as the surface boundaries in this document remain intact.

---

## Issue Coverage

### #1163 / #1137

- publish review
- preview promotion picker
- supporting-asset picker

### #1132 / #1133

- project-aware Working detail
- publish outcome selection
- lineage section and link-type expansion

### #1149

- queue health visibility
- cleanup audit entry points
- source preset expansion for remote-client flows

### #1146

- cleanup audit detail and retry behavior
- explicit verified-upload precondition in UI wording

### #213

- local-library preset modeled as a source-mode variant
- collection/sub-collection hints in intake setup

---

## Related Docs

- [phase-5-wave-4-ha-ui-design.md](phase-5-wave-4-ha-ui-design.md)
- [projects-design.md](projects-design.md)
- [3mf-resource-extraction-and-online-provenance-design.md](3mf-resource-extraction-and-online-provenance-design.md)
- [phase-5-publish-preview-and-supporting-assets-design.md](phase-5-publish-preview-and-supporting-assets-design.md)
- [workflow-and-ingestion-guide.md](workflow-and-ingestion-guide.md)
