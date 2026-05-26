# Print History Slicer Integration Design

> **Status**: Design proposal for review
> **Last updated**: 2026-05-16
> **Scope**: Model Catalog orchestration for source `.3mf` validation, optional filament override, local headless slicing, and canonical Bambuddy archive creation.

See also:

- [Historical Print Backfill Via Model Catalog](/docs/features/model_catalog/design/print-history-backfill.md)
- [3MF Analysis Cache Schema And API Draft](../planning/3mf-cache-draft.md)
- [Print History Slicer Implementation Plan](/docs/features/model_catalog/planning/print-history-slicer-plan.md)
- [Source 3MF Import Design](/docs/features/print_history/design/imports/source-3mf-import-design.md)
- [Filament Catalog - Design Document](/docs/features/filament_catalog/README.md)
- [Working Files Local Launch And Slicer Integration Design](/docs/features/model_catalog/design/working-files-launch.md)

## Purpose

Define how this repo should add a wizard-style `source .3mf -> canonical archive` workflow without collapsing existing boundaries between:

- source/project `.3mf` provenance
- archive-ready sliced `.gcode.3mf`
- Bambuddy canonical archive creation

The recommended direction is to let Model Catalog own the operator workflow, validation layer, and slicer-worker execution while Bambuddy remains the canonical archive store.

## Confirmed Current State

### Bambuddy can already be leveraged when its slicer stack is deployed

Upstream Bambuddy now has a documented Slicer API sidecar flow for headless Bambu Studio or OrcaSlicer execution.

Operationally, that means a server-side workflow already exists for:

- source `.3mf` or STL intake
- multi-plate discovery and selection
- printer/process/filament preset selection
- background slice jobs
- `.gcode.3mf` output suitable for Bambuddy-oriented flows

### What is already wired locally in this repo

The local Home Assistant Bambuddy integration already supports tokenized archive and source download URLs for `open_in_slicer` flows through:

- Bambuddy `POST /api/v1/archives/{id}/slicer-token`
- Bambuddy `POST /api/v1/archives/{id}/source-slicer-token`

That support is for opening an existing archive or source file in a local slicer. It is **not** a local implementation of the upstream job-oriented Slicer API.

### What is not yet wired locally

This repo does not currently expose a sidecar or HA client wrapper for:

- creating new slice jobs from source `.3mf`
- validating missing printer/process/filament metadata before slicing
- applying controlled filament substitutions
- committing the resulting sliced artifact back into Bambuddy as a new canonical archive

### Current answer to `can we use it already?`

Yes, but that is no longer the preferred architecture for this repo.

Supported operational modes are:

1. **Local Model Catalog worker preferred**
   - deploy the slicer worker beside the Model Catalog sidecar and keep source-file access, validation, and job orchestration local to the system that already owns the `.3mf` files
2. **Direct Bambuddy usage possible**
   - if the target Bambuddy deployment already has the optional Slicer API stack enabled, the operator can use Bambuddy's own UI and API directly
3. **Manual fallback**
   - if no slicer worker is deployed, the operator remains in the existing manual or forensics-driven path

## Goals

- start from Model Catalog or historical backfill context rather than a separate slicer-only tool
- validate source `.3mf` completeness before slicing
- use Filament Catalog linkage as a deterministic validation and substitution aid
- keep the slicer worker close to the Model Catalog source-of-truth files
- keep Bambuddy as the canonical archive owner
- preserve provenance by attaching the original source `.3mf` separately when useful
- allow a review-heavy operator flow for older-history reconstruction
- let the operator set the historical print timestamp that should be written into Print History

## Non-Goals

- recreating Bambu Studio preset management in this repo
- storing a full local clone of Bambu or Orca printer/process/filament presets
- treating raw `.gcode` as an equivalent archive source
- collapsing source-only provenance and canonical archive creation into one step
- building a free-form filament editor in the first implementation slice

## Architectural Position

### Owning surfaces

- **Model Catalog sidecar** owns orchestration, validation, operator warnings, override state, and job audit state
- **Model Catalog sidecar** owns the persisted backfill job record, including operator-selected historical print timestamps
- **Local slicer worker** runs beside Model Catalog and has direct access to the source `.3mf` working set plus controlled temp/output storage
- **Filament Catalog / Spoolman linkage** provides the deterministic filament registry used for validation suggestions and allowed substitutions
- **Bambuddy** remains the destination system for canonical archive creation and optional source attachment
- **Bundled slicer runtime** performs actual slicing. The first-class runtime is a local worker container using Bambu Studio or OrcaSlicer headlessly

### Why this belongs in Model Catalog

Model Catalog already owns:

- intake queue and source selection
- future `.3mf` analysis cache direction
- operator-reviewed working and backfill flows
- cross-feature linkage into Print History

That makes it the right place to drive a source-to-archive wizard while keeping the final archive write in Bambuddy.

### Why local-first is the preferred deployment model

In this repo, Model Catalog already owns the source files.

That means a local worker has concrete advantages over a Bambuddy-hosted slicer service:

- no extra cross-system source upload hop before validation or slicing
- direct reuse of the planned `.3mf` analysis cache and source-selection logic
- easier use of Filament Catalog linkage during validation and substitution
- cleaner audit trail because the same sidecar family owns source selection, validation, and slice-job state
- simpler future extension to non-Bambuddy outputs without moving the execution boundary again

## Persisted Job Contract

The reviewed flow should persist draft and terminal state in a dedicated Model Catalog table instead of relying on transient browser state.

Current contract:

- table: `model_catalog_print_history_jobs`
- migration version: `16`

Minimum persisted fields:

- workflow identity and source selection (`workflow_kind`, `source_kind`, `source_ref`, `local_model_id`, `working_group_id`)
- operator outcome intent (`archive_intent`, `attach_source_after_create`)
- review state (`status`, `validation_warnings_json`, `overrides_json`, `last_error`)
- historical timestamp state (`requested_print_started_at`, `requested_print_completed_at`, `requested_print_timezone`, `date_override_strategy`)
- worker execution state (`worker_provider`, `worker_job_id`, `selected_plate_key`, `selected_plate_index`, `sliced_output_path`)
- final commit state (`target_archive_id`, `created_archive_id`, `commit_request_json`, `result_summary_json`)

The important design constraint is that historical timestamp review survives refresh, restart, and partial failure.

Recommended interpretation:

- use Bambuddy as the canonical archive sink
- do **not** make Bambuddy the primary slicer orchestrator for Model Catalog-owned files

## Recommended Deployment Modes

### Mode A: Local Model Catalog slicer worker

Preferred first implementation.

Flow:

1. Model Catalog selects or uploads a source `.3mf`
2. Model Catalog sidecar creates a local slice job
3. Local slicer worker returns validation gaps, plate information, and preset choices
4. Operator chooses plate and any allowed overrides
5. Local slicer worker performs the slice and returns an archive-ready `.gcode.3mf`
6. Model Catalog commits that file through Bambuddy canonical archive upload

Why this is preferred:

- keeps source-file ownership and slicer execution in the same domain
- avoids pushing model-owned files into Bambuddy just to start a job
- makes validation and Filament Catalog linkage easier to implement deterministically
- still allows the final archive-of-record to remain in Bambuddy

### Mode B: Remote Bambuddy slicer provider

Optional compatibility mode, not the preferred one.

Requirements:

- expose the same high-level concepts as Mode A
- return structured validation warnings and allowed actions
- emit a real `.gcode.3mf`

This mode should be intentionally compatible with Mode A at the DTO level if support is added later.

### Mode C: Manual Operator Fallback

If no provider is available:

- operator can still use existing `open_in_slicer` token flows for manual editing
- operator can still use forensics and manual archive upload paths
- the Model Catalog slice wizard should show an unavailable state rather than pretending it can complete automatically

## Local Worker Architecture

### Deployment shape

Recommended services:

1. **Model Catalog sidecar**
   - API owner, SQLite owner, intake/source-selection owner
2. **Slicer worker container**
   - runs Bambu Studio or OrcaSlicer headlessly
   - receives validated job requests from Model Catalog only
3. **Shared working volume**
   - read access to source `.3mf` storage
   - write access to temp and output artifacts

Recommended container boundary:

- keep Bambu Studio or OrcaSlicer-specific process management out of the main sidecar process
- treat the worker as an internal service, not a user-facing API exposed directly to Home Assistant browsers

### Runtime responsibilities

**Model Catalog sidecar** should own:

- intake/source selection
- `.3mf` analysis cache lookup
- validation synthesis
- filament candidate generation from Filament Catalog
- operator override persistence
- archive commit to Bambuddy

**Slicer worker** should own:

- slicer-native source inspection when additional runtime metadata is needed
- printer/process/filament preset enumeration for configured runtime
- actual slice execution
- output artifact emission and worker diagnostics

### Storage layout

Recommended storage classes:

- `source` for operator-owned input `.3mf` files already managed by Model Catalog
- `analysis-cache` for reusable parsed metadata and preview data
- `slice-staging` for worker temp inputs and patched copies
- `slice-output` for resulting `.gcode.3mf` artifacts pending archive commit
- `slice-audit` for diagnostics, stderr capture, job metadata snapshots, and optional manifest outputs

Recommended rule:

- the worker should never mutate the original source file in place
- any patched metadata should be applied to a staged working copy only

### Security and trust boundaries

The worker should be treated as trusted but narrow.

Required safeguards:

- allow only Model Catalog sidecar calls, not browser-direct job creation
- accept only allowlisted file roots or sidecar-minted staged files
- cap temp/output retention and clean up abandoned jobs
- redact sensitive host paths from user-facing DTOs where possible
- keep Bambuddy API credentials in Model Catalog sidecar config, not inside browser code

## Recommended End-To-End Flow

### Step 1: Select source artifact

Source entrypoints:

- existing intake upload
- existing source-filesystem browse/select flow
- model detail action for a known source `.3mf`
- historical backfill action from a model or working group

### Step 2: Analyze and classify

Reuse or extend the planned `.3mf` analysis cache to derive:

- source hash
- file kind and sliced-state hints
- plate count and plate labels
- printer metadata hints
- process metadata hints
- filament metadata hints

### Step 3: Validate

The validation layer should stay narrow and deterministic.

Only three categories are first-class:

1. **Printer profile completeness**
   - `printer_model`
   - `nozzle_diameter`
   - `process_profile_name`
2. **Filament completeness**
   - filament definitions
   - process-to-filament assignment
   - tray or AMS mapping when needed by the worker runtime
3. **Process profile completeness**
   - layer-height or process preset identity
   - speed or quality preset identity
   - cooling and support preset identity when required for worker execution

### Step 4: Present warnings and limited fixes

The first slice should allow controlled fixes only:

- choose printer profile from a known allowlist
- choose plate from discovered plates
- choose process preset from a known allowlist
- choose filament substitutions from allowed Filament Catalog matches

Do **not** support arbitrary free-form filament creation in the first slice.

### Step 4.5: Review historical print timestamps

Before execution or archive commit, require an operator review of the print-history timestamps that should represent the original event.

Recommended behavior:

- show any inferred timestamp candidates from source metadata, archive candidates, or filesystem evidence
- let the operator set start and completion time explicitly
- persist the reviewed values into the job record before slicing starts
- include the reviewed timestamps in the final Bambuddy archive-commit request

### Step 5: Slice job execution

Once the validation state is satisfiable:

- create slice job
- execute via local slicer worker
- poll job status
- capture returned output metadata and diagnostics

### Step 6: Commit canonical archive and provenance

On success:

1. upload sliced output to Bambuddy as a new canonical archive
2. include reviewed historical timestamp fields in the archive-creation request
3. write archive linkage back into Model Catalog
4. optionally attach the original source `.3mf` to the created archive as provenance
5. store operator decisions and worker metadata for audit and later retry

## Validation Layer Design

> **Implementation note (2026-05-16)**: The validation layer described in this
> section was **deferred** during implementation.  The upstream bambu-studio-api
> (orca-slicer runtime) already handles printer, process, and filament preset
> validation at slice-time and returns structured errors.  Building a parallel
> validation / filament-substitution layer in the Model Catalog sidecar would
> duplicate that work.  The sections below are preserved as design reference in
> case a future pre-flight dry-run validation surface is needed.

The validation UI should treat timestamp review as a first-class review category beside printer, process, and filament completeness.

### Printer validation

Minimal contract:

- `printer_model`
- `nozzle_diameter`
- `process_profile_name`

Result states:

- `valid`
- `warning_missing`
- `warning_mismatch`
- `blocking_unknown`

Allowed remediation:

- select a known printer profile from configured worker-supported options

### Filament validation

This is the only override surface that should be emphasized in the initial UX.

The validator should detect:

- missing filament profile definition
- incomplete filament profile definition
- missing object-to-filament assignment
- missing or ambiguous tray mapping
- filament profile present but not clearly mappable to any known linked filament

#### Filament Catalog linkage role

The Filament Catalog should act as a **validation and substitution registry**, not as a full preset store.

Recommended matching signals, strongest first:

1. exact linked `filament_id` when future `colors_used` entries carry it
2. exact profile-name match from Spoolman or filament-catalog metadata
3. material + primary color or hex match
4. material-only fallback to a deterministic default

Recommended candidate shape:

```json
{
  "filament_id": 226,
  "display_name": "Bambu PLA Basic Red",
  "material": "PLA",
  "hex": "#C12E1F",
  "profile_name": "Bambu PLA Basic",
  "source": "filament_catalog"
}
```

#### Override policy

The first implementation should use **Option A only** from the design question in the prompt:

- allow selection from a predefined, deterministic filament registry
- do not allow arbitrary custom filament entry

Reason:

- keeps the service thin
- reduces drift from Bambu Studio compatibility
- makes audit and retry behavior predictable

#### Suggested registry source

The registry should be built from existing Filament Catalog or Spoolman projections, not a disconnected JSON file hand-maintained in parallel.

Candidate fields already present in the repo ecosystem include:

- `filament_id`
- material
- vendor name
- display name
- color hex
- profile name
- recommended nozzle and bed temperatures when available

### Process validation

Keep this to identity and completeness checks only.

The validator should detect:

- missing process preset reference
- incomplete process preset reference
- obviously incompatible nozzle-process combination when the worker can detect it

Allowed remediation:

- select a process preset from worker-supplied choices

## Structured Warning Contract

Recommended warning payload shape:

```json
{
  "warnings": [
    {
      "code": "missing_filament_assignment",
      "severity": "warning",
      "plate_index": 0,
      "slot_index": 2,
      "message": "Plate 1 filament slot 2 has no assigned filament profile."
    }
  ],
  "actions": [
    {
      "type": "select_filament",
      "plate_index": 0,
      "slot_index": 2,
      "options": [
        {
          "filament_id": 226,
          "display_name": "Bambu PLA Basic Red"
        },
        {
          "filament_id": 341,
          "display_name": "Sunlu PLA+ Red"
        }
      ]
    }
  ]
}
```

## Proposed Sidecar API Draft

These are **planned sidecar endpoints**, not current shipped endpoints.

Route family:

- `GET /api/slicer/providers`
- `POST /api/slice-jobs`
- `GET /api/slice-jobs/{slice_job_id}`
- `POST /api/slice-jobs/{slice_job_id}/overrides`
- `POST /api/slice-jobs/{slice_job_id}/execute`
- `POST /api/slice-jobs/{slice_job_id}/commit-archive`

### `GET /api/slicer/providers`

Purpose:

- report whether the configured local slicer worker is reachable
- report supported capabilities such as plate discovery, process preset listing, and filament override

### `POST /api/slice-jobs`

Recommended request anchors:

- `upload_id` from intake queue
- `analysis_run_id` from `.3mf` cache
- optional `source_path` for controlled filesystem sources

Suggested request shape:

```json
{
  "upload_id": 42,
  "analysis_run_id": 17,
  "provider": "model_catalog_local",
  "intent": "create_canonical_archive"
}
```

Suggested response shape:

```json
{
  "slice_job_id": 91,
  "status": "needs_validation",
  "provider": "model_catalog_local",
  "plates": [
    {
      "plate_index": 0,
      "label": "Plate 1"
    }
  ],
  "warnings": [],
  "actions": []
}
```

### `POST /api/slice-jobs/{slice_job_id}/overrides`

Purpose:

- persist selected plate
- persist selected printer and process preset
- persist selected deterministic filament substitutions

### `POST /api/slice-jobs/{slice_job_id}/execute`

Purpose:

- trigger local worker execution once the validation state is satisfiable

Expected state transitions:

- `draft`
- `needs_validation`
- `ready_to_slice`
- `running`
- `slice_failed`
- `slice_succeeded`
- `archive_commit_failed`
- `completed`

### `POST /api/slice-jobs/{slice_job_id}/commit-archive`

Purpose:

- upload worker output to Bambuddy canonical archive endpoint
- optionally attach source `.3mf`
- persist archive link outcome in local Model Catalog state

## Suggested Persistence Additions

The sidecar should persist a compact slice-job record with:

- source hash
- source origin
- provider type and provider job id
- chosen plate index
- chosen printer/process preset identifiers
- chosen filament substitutions
- validation warnings snapshot
- output file metadata
- resulting archive id when successful
- operator id or session attribution when available
- worker runtime family (`bambu_studio` or `orcaslicer`)
- worker binary version or image tag
- staged source path
- output staging path
- cleanup state
- archive commit attempt count

This should be compact and JSON-friendly, consistent with current sidecar patterns.

## Internal Worker Contract

The local worker contract can remain internal to the Model Catalog deployment.

Recommended worker routes:

- `GET /healthz`
- `POST /jobs/analyze`
- `POST /jobs/slice`
- `GET /jobs/{worker_job_id}`
- `DELETE /jobs/{worker_job_id}`

Recommended worker request shape:

```json
{
  "job_id": "slice-91",
  "source_path": "/data/staging/slice-91/input.3mf",
  "plate_index": 0,
  "printer_profile": "X1 Carbon 0.4",
  "process_profile": "0.20mm Strength",
  "filament_overrides": [
    {
      "slot_index": 2,
      "profile_name": "Bambu PLA Basic",
      "display_name": "Bambu PLA Basic Red"
    }
  ]
}
```

Worker response requirements:

- stable machine-readable state
- explicit output artifact path and filename on success
- explicit diagnostic log summary on failure
- no direct Bambuddy calls from the worker

## UX Direction Summary

The UX should present this as a **reviewable archive-preparation wizard**, not a raw slicer control panel.

Primary operator questions:

1. Is this source `.3mf` complete enough to slice server-side?
2. If not, can the missing pieces be filled from known printer, process, and filament choices?
3. Which plate should become the canonical historical archive?
4. Should the original source `.3mf` also be attached as provenance?

## Phase Recommendation

### Phase 1

- ~~add local worker capability detection~~ ✅ Slice 1
- ~~create read-only validation + slice-job orchestration contract~~ ✅ Slice 2
- ~~wire to local worker only~~ ✅ Slice 4
- ~~allow deterministic filament substitution from Filament Catalog candidates~~ — Deferred; upstream bambu-studio-api handles preset validation

### Phase 2

- persist job history and retry behavior
- reuse `.3mf` analysis cache directly
- write archive linkage and provenance follow-up automatically

### Phase 3

- harden local worker packaging, cleanup, and observability
- richer cross-feature ranking from archive-created filament provenance back into `colors_used`

### Optional later phase

- add a remote Bambuddy-compatible provider adapter only if there is later operational value in supporting both deployment modes

## Success Criteria

This design is successful when:

- the operator can start from a model or intake source and create a canonical Bambuddy archive without leaving the repo's main workflow
- filament fixes stay deterministic and audit-friendly
- source-only provenance remains distinct from canonical archive creation
- the UI works cleanly against a local worker owned by the Model Catalog deployment
- raw `.gcode` remains an explicit non-goal rather than a silently widened input path
