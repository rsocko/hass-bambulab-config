# MakerWorld URL Import Popup Assessment

> **Status**: Proposed assessment and mockup package for review before implementation
> **Last updated**: 2026-05-31
> **Related issues**: #1630, #1627, #1179, #1496
> **Companion mockup**: [mockups/makerworld-url-import-popup.html](mockups/makerworld-url-import-popup.html)

## 1. Why This Exists

The current external-source intake direction correctly says that MakerWorld and other URL-driven imports should plug into the existing intake system rather than becoming a separate product. However, issue #1630 changes one important presentation decision: the MakerWorld URL flow should no longer expand inline inside the Intake view itself. It should open as a popup child flow.

At the same time, issue #1627 broadens the destination model. MakerWorld URL import cannot be designed as "Catalog only" anymore. It must support a Working Files outcome without pretending that a downloaded MakerWorld model is already fully curated.

This document recommends a popup-based wizard that:

- reuses the shared intake shell and downstream steps where the problem is the same
- uses a purpose-built Source/Review experience where URL resolution differs from file or folder picking
- supports both review-first and explicit direct-commit behavior
- treats `Model` and `Working Files` as first-class destinations from the same resolved MakerWorld source record
- keeps `Next` as navigation only; execution begins only when a Commit-step CTA is pressed

## 2. Recommendation

### 2.1 Primary recommendation

Adopt a **popup child wizard** for MakerWorld URL import, launched from Intake Home, Queue Review quick actions, Working Files, or any future source shortcut.

The popup should use the same fixed modal shell, title-row pattern, stepper grammar, footer actions, validation badges, and commit summary language as the primary Intake wizard. It should not reuse the Browser Upload or Server Inbox Source step directly, because URL capture is not a tree-selection problem.

### 2.2 Step model

Recommended step labels for the popup flow:

1. **Source**
2. **Review**
3. **Choose Destination**
4. **Validate**
5. **Commit**

This keeps the same five-step rhythm and final-step language as the main Intake wizard while acknowledging that `Organize` is not the operator's primary task here. The file/folder grouping problem is replaced by a provider-review problem: which MakerWorld instance/profile is being imported, what metadata was resolved, and whether the operator wants metadata-only or full download.

### 2.3 Popup, not inline expansion

Use a popup because this flow has a different cognitive shape from the inline file-based intake views:

- it starts from one URL, not an expanding file tree
- it may need auth diagnostics, provider warnings, and instance/profile choice before destination selection
- it benefits from a contained `finish or close` interaction model
- it should be available from more than one entry point, not just the Intake page body

The popup should still write the same intake record and queue/job audit fields used by the generalized external-source intake contract.

## 3. What To Reuse Vs. What To Build Separately

### 3.1 Reuse directly

These pieces should be shared with the primary Intake wizard with minimal or no UX divergence:

- fixed popup shell size and pane-level scrolling
- top stepper and bottom footer action row
- destination chips and destination summary rows
- validation badges, warning cards, and commit-state annotations
- completion/result summary pattern
- queue/job audit language and `Job History` handoff

### 3.2 Reuse with adaptation

These pieces should keep the same visual language but use URL-import-specific content:

- right-pane result cards: use the same summary-card grammar as intake result cards, but show source metadata, creator, hero image, instance/profile details, and selected download mode
- left-pane editable metadata fields: same field rows and inline help style, but prefilled from MakerWorld instead of derived from uploaded files
- file-selection block: replace grouped include lists with an instance/profile picker and a `download selected 3MF` summary

### 3.3 Do not force reuse

These patterns belong to browser/server file intake and should not be copied into the URL popup just for consistency:

- tree browsing and folder recursion controls
- per-file remove semantics from the Source step
- overlapping selection consolidation rules
- folder-preservation wording from upload/inbox flows

The result should feel like a sibling of the primary Intake wizard, not a disguised file picker.

## 4. Proposed Operator Flow

### 4.1 Source

Left pane responsibilities:

- paste or confirm the MakerWorld URL
- show auth/session state for MakerWorld API access
- resolve the URL into a design record

The Source step should not offer fast-path or commit-mode choices. It only captures the URL, resolves metadata, and establishes whether the flow can continue.

Right pane responsibilities:

- resolved model hero card
- confidence and provider status
- creator/title/source URL
- gallery preview and available instance/profile summary

Behavior rule:

- pressing `Next` on Source only advances to Review after metadata capture succeeds
- pressing `Next` on Source does not download files, create final destination outputs, or execute commit work

### 4.2 Review

Left pane responsibilities:

- choose instance/profile when multiple are available
- default to metadata capture for supported MakerWorld URLs
- allow the operator to proceed with `metadata only` publish or `full download` after capture succeeds
- treat `link only` as a fallback-only outcome when MakerWorld auth/API resolution fails, with explicit `continue as link only` or `cancel` guidance rather than a normal primary mode choice
- edit title/tags if needed
- optionally choose `carry source notes into README` for Working Files

Right pane responsibilities:

- resolved metadata preview
- selected file/instance summary
- provenance and duplicate signals
- direct-commit eligibility banner when confidence is high and warnings are absent

Fast-path eligibility may be shown in Review as guidance, but execution still waits for the Commit step.

For `full download` selections, the system may stage the selected 3MF into sidecar temporary storage before Validate so duplicate analysis can inspect the real file name, file hash, and related intake heuristics. This staging download is not yet a commit.

### 4.3 Choose Destination

Offer the same target model defined by the generalized external-source intake design, but keep the initial popup focused on the destinations that actually fit MakerWorld provider pages:

- **Model**: default and primary recommendation for curated import
- **Working Files**: first-class alternative for remixing, slicer experimentation, or not-yet-curated downloads
- **Link Only**: fallback-only path when the operator chooses to continue after MakerWorld metadata capture fails or remains unavailable

`Idea`, `Project`, and `Collection` remain valid in the broader routing system but do not need to dominate the initial MakerWorld popup.

### 4.4 Validate

Use the same warning/status grammar as the main Intake wizard. Validation should summarize:

- auth and download readiness
- staged-download readiness when `full download` is selected
- duplicate or likely-match warnings
- destination-specific consequences
- whether the chosen action will create a queue-review item or commit immediately

Auth/API capture failures should surface as early as the Source or Review step whenever possible, not wait until Validate. Validate may repeat the warning, but the operator should already know they are now deciding between `continue as link only` and `cancel`.

Behavior rule:

- pressing `Next` on Validate only advances to Commit
- pressing `Next` on Validate does not create the final Working Files or Catalog output, or finalize the intake job
- Validate may say that a direct-commit path is eligible, but the side effect belongs only to the Commit-step CTA

Download timing rule:

- if the operator selected `metadata only`, Validate stays metadata-only and does not fetch the 3MF
- if the operator selected `full download`, the system may download the chosen 3MF into temporary intake staging before or during Validate so duplicate detection can compare hash, file name, and related file-backed signals
- this staged file is validation input only; it is not yet a committed Catalog asset, Working Files asset, or finalized intake upload

Metadata-only validation rule:

- metadata-only Validate cannot run file-hash comparison because no 3MF was staged
- metadata-only Validate should still run URL-based, source-record, title, creator, and other metadata-backed duplicate heuristics
- the UI should show file-backed checks such as `hash duplicate compare` and `staged filename compare` as `Not run` or `Unavailable in metadata-only mode`, not silently omit them

### 4.5 Commit

Commit is the first step where execution is allowed. It should have two states:

- **Pre-commit**: final checks, final route summary, and the actual execution CTA
- **Post-commit terminal state**: after execution starts and completes, the popup should stop behaving like a wizard and replace the normal step content with a terminal summary shell showing results, links, and audit outcome

If a staged validation download already exists, Commit should reuse that staged file instead of downloading the same 3MF a second time when possible.

Recommendation: do **not** add a sixth step for `Summary` or `Complete`. That would imply there is another operator decision point after commit, when there really is not. The better interaction model is:

- Step 5 `Commit` is the last navigable step
- once the operator presses a commit CTA, the popup transitions out of wizard-editing mode
- when execution completes, the popup shows a terminal summary state with no `Back` affordance
- the operator can then only `Close`, `Open Queue Review`, `Open Working Files`, `View Job History`, or other forward-moving destination actions

The final step must support both modes:

- **Review-first path**: create/update the intake record, route to Queue Review, and show where the operator picks it up next
- **Direct-commit path**: finalize immediately, reusing the staged 3MF when present (or downloading it if staging was not required), persist the local outcome, and show the final commit summary in the popup

This addresses the requirement to let the user move all the way to completion, including the download, when they explicitly want that path, while keeping `Commit` accurate as the execution step rather than a completion-only label.

## 5. Working Files Destination Contract (#1627)

### 5.1 When Working Files is the right outcome

MakerWorld -> Working Files should be treated as an intentional editing or staging flow, not as a second-class fallback. It is the right default when the operator wants to:

- remix or inspect the file before curating it into the Catalog
- preserve the upstream file in an active working folder
- use the file in slicer workflows without immediately creating a catalog model

### 5.2 Metadata policy for Working Files

Do not try to force the full MakerWorld snapshot into Working Files sidecar metadata. Reuse the existing Working Files sidecar contract cleanly.

Recommended carry-forward for a Working Files destination:

- `.modelmeta.json.display_title` <- MakerWorld title
- `.modelmeta.json.origin_url` <- canonical MakerWorld URL
- `.modelmeta.json.tags` <- reviewed tags or provider tags fallback
- `.modelmeta.json.primary_file` <- selected downloaded `.3mf` when determinable
- `.modelmeta.json.thumbnail` <- local preview image if a preview asset is persisted
- `.modelmeta.json.source_capture_record_id` <- sidecar `source_intake_records.id` for the originating capture

Keep richer provider metadata outside `.modelmeta.json`:

- creator identity
- raw description
- selected instance/profile IDs
- full API snapshot
- confidence/warning history

Those belong in the intake/source record and job audit trail, where they remain available if the operator later promotes the working folder into the Catalog.

`source_capture_record_id` is the bridge between those two worlds. It is a lightweight linkage field, not the payload itself. The authoritative MakerWorld snapshot remains in sidecar intake storage; the Working Files folder carries only the stable lookup key needed to rehydrate that capture later.

### 5.3 Optional README behavior

If the operator enables a `Create source note` option for Working Files, generate a lightweight `README.md` containing:

- title
- creator
- source URL
- selected instance/profile label
- capture timestamp
- source description excerpt

This uses the existing Working Files sidecar model without inventing a new metadata authority.

### 5.4 Carry-forward rule on Working Files -> Catalog publish

When a Working Files folder is later published into the Catalog, the publish flow must check for `.modelmeta.json.source_capture_record_id`.

If present:

- load the linked `source_intake_records` row
- treat `snapshot_json`, `media_manifest_json`, `file_manifest_json`, and related intake/job fields as the authoritative external-source audit record
- rehydrate the same Catalog-side metadata persistence used by direct MakerWorld Catalog import
- persist the curated Catalog-side supporting-file / custom-field representation there, not in the Working Files folder

If absent:

- continue as a normal filesystem-first Working Files publish with no external-source rehydration

This keeps Working Files lightweight while preserving deterministic carry-forward into Catalog.

## 6. Direct-Commit Policy

The popup should expose an explicit fast path when all fast-path rules already defined in the external-source intake design hold:

- operator-initiated action
- `high` confidence
- `provider_model_page`
- target is `model` or `working_file_group`
- no duplicate or collision warnings

Recommended CTA pattern:

- primary CTA in normal mode: `Next`
- primary CTA on Commit for immediate execution: `Commit and Download Now`
- primary CTA on Commit for deferred review: `Commit Intake Job`

If the operator uses the fast path, the popup should still:

- create the intake/source record
- write commit/job audit fields
- end on the same Commit step with a real summary, not a toast-only success

`Next` should never perform these side effects. `Next` is navigation only.

## 6.1 Temporary download cleanup

If a `full download` path staged a 3MF for validation, the popup needs an explicit cleanup contract.

Required behavior:

- if the operator cancels the wizard before Commit, delete the staged download and any derived temporary hash/inspection artifacts
- if the operator closes the popup before Commit, delete the staged download immediately or mark it for short-TTL cleanup on next sweep
- if the browser session dies unexpectedly, a sidecar cleanup sweep should remove abandoned staged downloads after a short expiration window
- if Commit succeeds, promote or reuse the staged file as part of the final intake/Working Files/Catalog path instead of deleting it first

This keeps the duplicate-checking behavior consistent with Browser Upload while preserving the wizard contract that only Commit creates the final outcome.

## 7. Mockup Notes

The companion HTML mockup shows **five separate wizard steps**, matching the recommended step model exactly:

1. **Source**
2. **Review**
3. **Choose Destination**
4. **Validate**
5. **Commit**

No mockup state should visually imply that the flow has fewer steps than the stepper advertises. If implementation later decides to merge adjacent steps, the step model itself should be reduced to match rather than leaving a five-step stepper over a three-screen flow.

After Commit executes, the popup should no longer act like a normal stepper flow. The recommended presentation is a terminal summary takeover of the popup body. That summary may keep the `Commit` step visually completed or may replace the stepper entirely, but it should not leave an active `Back` affordance that suggests the operator can return to pre-commit editing.

Low-fi text sketch of the recommended structure:

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ Intake Wizard: Source                                          [Close]    │
├────────────────────────────────────────────────────────────────────────────┤
│ [1 Source] [2 Review] [3 Choose Destination] [4 Validate] [5 Commit]     │
├──────────────────────────────────────┬─────────────────────────────────────┤
│ LEFT: Actions                        │ RIGHT: Results                      │
│ URL                                  │ Resolved MakerWorld design         │
│ [ makerworld.com/...____________ ]   │ hero image                         │
│ [Resolve]                            │ title / creator / confidence       │
│                                      │ selected instance + plate count    │
│ Metadata capture only                │ warnings / duplicate signals       │
│ press Next to continue               │                                     │
│                                      │ destination summary                │
│ Destination                          │ - Model or Working Files           │
│ [Model ▼]                            │ - queue review or direct commit    │
│                                      │                                     │
│ [Back] [Next]                        │                                     │
└──────────────────────────────────────┴─────────────────────────────────────┘
```

## 8. Implementation Guidance

If this direction is approved, implementation should follow these sequencing rules:

1. Build the popup as a child flow on top of the existing external-source intake APIs, not a parallel API surface.
2. Reuse the shared stepper/footer/validation/result components first.
3. Add `Working Files` destination support at the same time as the popup shell so issue #1627 is solved by design, not as a post-launch patch.
4. Keep Queue Review as the canonical review surface for deferred items; the popup is for authoring and optional immediate commit, not for becoming a second queue system.

## 9. Recommendation Summary

The recommended baseline is:

- popup child wizard, not inline expansion
- same intake shell and downstream component language
- URL-specific Source and Review steps
- `Model` and `Working Files` as first-class outcomes
- explicit Commit-step execution when policy allows it

That is the smallest design change that satisfies #1630 and #1627 without splitting the intake product into separate experiences.