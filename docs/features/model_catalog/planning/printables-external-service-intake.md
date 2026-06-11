# Printables External Service Intake Design

> **Status**: Planning
> **Created**: 2026-06-11
> **Scope**: External Service intake via Printables.com URL paste, metadata capture, and later download feasibility.

## Purpose

Add Printables.com as a best-effort External Service intake provider for the Model Catalog. The first supported workflow is URL copy/paste into the existing source-intake flow, resolving public Printables model metadata server-side, and publishing that metadata into the local catalog with clear source provenance.

This design intentionally starts with metadata and link intake. Full file import is treated as a later decision because Printables appears to be file-oriented, often exposing STL and G-code files with temporary download links, while the current MakerWorld path is profile/instance-oriented and validates downloaded files as 3MF packages.

## Goals

1. Support Printables URL paste in the existing External Service intake endpoint.
2. Resolve public model metadata through a provider adapter.
3. Store normalized metadata and raw provider snapshots in existing source-intake records.
4. Publish Printables metadata into local catalog records using existing `printables` source vocabulary.
5. Keep MakerWorld behavior stable while extracting provider-neutral seams.
6. Document operational limits caused by relying on an unofficial Printables API surface.

## Non-Goals For MVP

1. No full STL, G-code, or 3MF file import from Printables in the first implementation slice.
2. No browser-side calls to Printables APIs.
3. No description or license scraping unless GraphQL proves insufficient and the added fragility is explicitly accepted.
4. No new source-intake database table.
5. No rewrite of the local catalog source or publication metadata model.

## Current Architecture Fit

The existing External Service intake flow is already close to provider-agnostic:

1. `POST /api/intake/source/capture` accepts a URL and capture mode.
2. `_detect_provider_id()` determines the source provider.
3. The provider adapter resolves metadata and file manifest details.
4. A row is inserted into `source_intake_records` with normalized fields and `snapshot_json` provenance.
5. Review, commit, and publish routes use the source record to create or update local catalog state.

Reusable pieces:

1. The source-intake database schema.
2. Snapshot and provenance storage.
3. Metadata-only publish behavior.
4. Local catalog source fields that already accept `printables`.

MakerWorld-specific pieces that need seams:

1. Provider detection.
2. Adapter construction.
3. Error messages and auth fallback wording.
4. Manifest instance selection.
5. Full-import download validation.

## Provider Model

Printables should be represented as a first-class provider adapter with provider ID `printables`.

The adapter should provide these capabilities:

1. Parse supported Printables model URLs.
2. Normalize canonical model URLs.
3. Resolve model metadata from the server-side sidecar.
4. Normalize creator, title, thumbnail, media, model ID, slug, stats, and raw response data.
5. Produce warnings for unavailable optional data.
6. Optionally discover file manifest entries if the live API proves reliable.
7. Record recent request diagnostics.
8. Enforce conservative rate limiting.

The adapter should not perform HTML scraping in the MVP.

## API Assumptions

Printables does not appear to publish an official public API contract. Practical integration appears to rely on an unofficial GraphQL endpoint at `https://api.printables.com/graphql/`.

Likely useful operations:

1. Model lookup by ID.
2. Search, if URL-less discovery is ever added.
3. Public file list retrieval.
4. Temporary download-link generation through a mutation, if full import is later supported.

Design implication: all Printables behavior must be best-effort, rate-limited, diagnostics-rich, and easy to disable or degrade.

## URL Scope

MVP should support public model detail URLs. Representative patterns to validate during exploration:

1. `https://www.printables.com/model/{id}-{slug}`.
2. `https://printables.com/model/{id}-{slug}`.
3. URLs with query strings or fragments.
4. Localized or alternate path variants, if present.

MVP should reject or defer non-model URLs such as user profiles, collections, contests, search pages, groups, and makes.

## Data Mapping

A resolved Printables model should map into existing source-intake fields:

| Source-intake field | Printables value |
|---|---|
| `provider_id` | `printables` |
| `source_url_canonical` | Normalized Printables model URL |
| `source_url_original` | Original pasted URL |
| `source_model_id` | Printables model ID as text |
| `source_collection_id` | Empty for MVP |
| `title` | Model title |
| `creator_name` | Public creator handle or display name when available |
| `creator_url` | Creator profile URL if reliably available |
| `description_raw` | Only if available through validated metadata API |
| `thumbnail_url` | Primary model image URL |
| `media_manifest_json` | Normalized public media entries |
| `file_manifest_json` | Provider-neutral file entries if reliable; empty is acceptable for metadata-only MVP |
| `confidence` | `high` or `medium` depending on resolved fields |
| `warnings_json` | Missing optional metadata, unsupported file types, or API limitations |
| `snapshot_json` | Raw GraphQL response plus source/provenance metadata |

When publishing metadata to the local catalog, use `printables` for source origin/publication source fields and preserve canonical/original source URLs.

## File Manifest Strategy

MakerWorld manifests are currently instance/profile-oriented. Printables should not be forced into that model long term.

Recommended provider-neutral manifest fields for Printables:

1. `provider_id`.
2. `file_id`.
3. `file_type`.
4. `filename`.
5. `file_size`.
6. `is_default`.
7. `download_requires_signed_url`.
8. `download_url_ttl_seconds`, if provided.
9. `source_model_id`.
10. `raw` provider payload excerpt where useful.

For MVP, file manifest entries can be captured but not downloaded. Full import should remain disabled until the route can download and validate non-3MF source assets intentionally.

## Full Import Decision

Full import is a separate design gate.

### Option A: Metadata-Only MVP

1. Supports URL paste and local metadata publish.
2. Does not download source files.
3. Lowest risk and fits the current catalog provenance flow.
4. Recommended first implementation.

### Option B: Expanded File Import

1. Adds temporary download-link generation.
2. Supports STL, G-code, and possibly 3MF assets.
3. Requires provider-neutral download handling.
4. Requires validation and asset ingestion rules beyond current 3MF validation.
5. Requires clearer UI for file selection and unsupported file types.

Recommendation: start with Option A and explicitly defer Option B.

## Development Phases

### Phase 0: API Exploration

Validate live behavior before coding against assumptions.

Tasks:

1. Test model-detail GraphQL query against 2-3 public model URLs.
2. Confirm URL-to-model-ID parsing.
3. Confirm available metadata fields.
4. Confirm media URL construction.
5. Confirm file list shape.
6. Probe download-link mutation without integrating it.
7. Record rate-limit and error behavior.
8. Confirm description/license availability or absence.

Exit criteria:

1. API notes are captured.
2. MVP fields are confirmed.
3. Unsupported or deferred fields are explicit.
4. Go/no-go for metadata MVP is recorded.

### Phase 1: Provider Seam Hardening

Extract MakerWorld-only assumptions without changing user-visible behavior.

Tasks:

1. Introduce provider detection for MakerWorld and Printables hosts.
2. Introduce provider adapter construction through a small registry or factory.
3. Keep MakerWorld auth behavior unchanged.
4. Make provider-specific unsupported/auth/error messages data-driven or adapter-driven.
5. Keep full-import behavior MakerWorld-only unless explicitly enabled by provider capabilities.

Exit criteria:

1. Existing MakerWorld source-intake tests pass.
2. The route can identify Printables URLs but can still return controlled unsupported or provider-unavailable responses before the adapter is complete.

### Phase 2: Printables Metadata Adapter

Add the server-side Printables adapter.

Tasks:

1. Add adapter dataclasses or provider-neutral resolved-result types.
2. Implement URL parsing and canonical URL generation.
3. Implement GraphQL request helper with timeout and rate limiting.
4. Normalize model metadata.
5. Normalize media manifest.
6. Normalize file manifest if reliable.
7. Add recent request diagnostics.
8. Add provider unit tests with mocked GraphQL responses.

Exit criteria:

1. URL parsing tests pass.
2. Metadata normalization tests pass.
3. Provider failure modes are tested.
4. No live network is needed for normal tests.

### Phase 3: Source Capture And Metadata Publish

Wire the adapter into existing source-intake behavior.

Tasks:

1. Enable Printables URL capture.
2. Insert normalized source records with `provider_id=printables`.
3. Support `link_only` fallback.
4. Support `metadata_only` publish to local model records.
5. Set local source fields to `printables`.
6. Preserve canonical and original source URLs.
7. Attach source snapshots and provenance.

Exit criteria:

1. API tests cover Printables capture.
2. API tests cover Printables metadata publish.
3. API tests cover unsupported full-import behavior.
4. Manual local catalog record review shows correct source provenance.

### Phase 4: Download Gate

Decide whether to implement full file import.

Tasks:

1. Review API exploration results for file downloads.
2. Decide supported file types.
3. Decide how files become local model assets.
4. Decide validation rules for STL, G-code, and 3MF.
5. Decide UI selection behavior.

Exit criteria:

1. A written decision exists: defer full import or implement it.
2. If implementing, provider-neutral manifest/download design is accepted.

### Phase 5: Optional Full Import

Only start after Phase 4 accepts file import.

Tasks:

1. Implement temporary download-link generation.
2. Add provider-neutral download method.
3. Validate downloaded assets by file type.
4. Stage or attach files as local model assets.
5. Add tests for temporary URL failure, expired URLs, unsupported file types, and successful imports.

Exit criteria:

1. Selected Printables source files can be imported without using MakerWorld instance semantics.
2. Existing MakerWorld 3MF flow still passes tests.

### Phase 6: Optional Enrichment

Only start if descriptions, licenses, or profile details are needed enough to justify scraping or more fragile APIs.

Tasks:

1. Decide whether HTML scraping is acceptable.
2. Add isolated scraping helper if accepted.
3. Keep scraping failures non-fatal.
4. Record license confidence separately from source metadata confidence.

Exit criteria:

1. Scraped fields are clearly marked as best-effort.
2. Metadata capture still succeeds when scraping fails.

### Phase 7: UI And Documentation

Make the user-facing behavior clear.

Tasks:

1. Add provider label/mode messaging only where the existing UI needs it.
2. Document Printables as best-effort and unofficial.
3. Document supported capture modes.
4. Document unsupported full-import behavior if deferred.
5. If Lovelace JS resources change, update `_resources.yaml` cache-busting version.

Exit criteria:

1. User-facing mode labels match actual backend capability.
2. Documentation explains limitations and operational expectations.

## Verification Strategy

1. Run existing MakerWorld source-intake tests after provider seam changes.
2. Add mocked Printables provider tests.
3. Add source-intake API tests for Printables capture, metadata publish, link-only fallback, unsupported full-import, and provider errors.
4. Run manually gated live smoke tests only after mocked tests pass.
5. Verify local model records include Printables source origin, canonical URL, creator, thumbnail, and attached source snapshot.
6. Run Lovelace cache-bust validation only if frontend resources are changed.

## Risks And Mitigations

| Risk | Mitigation |
|---|---|
| Unofficial API changes | Keep adapter isolated, add diagnostics, and document best-effort support. |
| Rate limiting or blocking | Use conservative QPS defaults and avoid browser-side calls. |
| Missing description/license data | Exclude from MVP or treat as manual/best-effort fields. |
| Temporary download URLs | Generate on demand only if full import is accepted. |
| File type mismatch | Keep full import disabled until STL/G-code/non-3MF handling is designed. |
| MakerWorld regression | Phase provider seam work with regression tests before adding Printables behavior. |

## Recommended First Slice

Implement phases 0 through 3 only:

1. Validate Printables GraphQL metadata shape.
2. Harden provider seams without changing MakerWorld behavior.
3. Add Printables metadata adapter.
4. Support URL paste capture and metadata-only publish.
5. Return clear unsupported behavior for full import.

This creates a useful Printables intake path while avoiding the larger non-3MF file-import decision until there is enough evidence to design it cleanly.