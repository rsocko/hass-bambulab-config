# Manyfold API Gap Analysis for Model Catalog Planning

> Generated: 2026-04-21
> Scope: Manyfold 2026 releases, current REST/API coverage, native-UI-only capabilities, and implications for a custom model-catalog UI that keeps Manyfold as the archival store.

## Sources Reviewed

- GitHub releases for `manyfold3d/manyfold` in 2026 through `v0.137.0`
- Generated OpenAPI document at `app/api/v0/openapi.json`
- Request specs under `spec/requests/api/v0/**` and `spec/requests/api/oembed/**`
- Relevant controllers, serializers, routes, and UI components for lists, likes, comments, follows, reports, libraries, previews, and OAuth app management

## Executive Summary

Manyfold's current machine-facing API is useful, but deliberately incomplete. It is strongest for core catalog CRUD, file upload, file metadata, and creator-group management. It is weak or absent for most of the social, moderation, library-administration, and workflow features that the native UI gained during 2026.

For your narrower use case, this is more encouraging than a full-UI-replacement analysis might suggest. If the goal is primarily to organize a mostly single-user library, tag models, and link them to Bambuddy archives or similar external records, Manyfold is a reasonable archival backend. The main constraint is not likes or comments. The main constraint is that Manyfold does not currently provide a first-class place to store arbitrary app-specific metadata.

The biggest blockers for your model-catalog use case are:

- No generic metadata extension point for fields like Bambuddy archive linkage, enrichment provenance, or cross-system IDs
- No REST API for library management, path-template preview, or scan-oriented admin workflows
- Narrower search/filter coverage in the documented API than the native UI supports
- No documented REST surface for bulk-edit, merge, sync, scan, or problem-management workflows that the native UI already supports

The social gaps are real, but probably secondary for your stated plan:

- No first-class REST API for lists or likes
- No first-class REST API for comments, comment moderation, or comment federation
- No REST API for moderation reports, follows, or most federation-facing actions

## What the API Does Cover Today

The generated OpenAPI document currently exposes these major surfaces:

- `Collections`: list, create, get, update, delete
- `Creators`: list, create, get, update, delete
- `Models`: list, create-from-upload, get, update, delete
- `Files`: add file to model, get file, update file, delete file
- `User Groups`: list, create, get, update, delete under a creator
- `File Uploading`: TUS resumable upload flow
- `oEmbed`: model, collection, creator embeds
- `NodeInfo`: instance metadata

That gives you a sound base for:

- Catalog browsing by model, creator, and collection
- Creating and editing core records
- Uploading assets and attaching them to models
- Managing model/file metadata like captions, descriptions, tags, preview-file assignment, presupported relationships, and license
- Managing creator user groups and member invitations via email or fediverse address

For a single-user or mostly single-user catalog, the strongest immediately usable fields are:

- `name`
- `caption`
- `description`
- `keywords` for tags
- `links`
- `creator`
- `collection`
- `preview_file`

## 2026 Release Coverage Assessment

### `v0.131.0` - User Groups, Rhino 3DM

Assessment: **good API coverage for the headline feature**.

- The release added user groups and explicitly added API endpoints for user group management.
- OpenAPI and request specs confirm group CRUD under `/creators/{creator_id}/groups`.
- This is one of the strongest 2026 areas from an API perspective.

Notes:

- Rhino 3DM support is a file/rendering capability rather than a dedicated API surface.
- You can consume affected files through the normal model/file endpoints, but there is no special format-specific API.

### `v0.132.0` - Group Invitations, API Keys for Contributors, Long-Lived Bearer Tokens, Bambu Studio Links

Assessment: **partial coverage**.

- Group invitation flow is covered through the group API: the request schema supports `add_members` and `remove_members`, and the implementation accepts usernames, email addresses, and fediverse addresses.
- OAuth client-credentials token exchange is documented via `/oauth/token`, and the OpenAPI security scheme is built around it.

Gaps:

- OAuth application management itself is still native-UI-only under `/oauth/applications`.
- The release made API keys and bearer tokens more usable, but not fully self-service via API.
- If your custom UI needs users to create or rotate client apps and long-lived tokens, you still need the native UI or upstream API additions.
- "Open in Bambu Studio" is a native helper/UI concern. It is built from signed file URLs and client-side logic, not from a dedicated REST endpoint.

### `v0.133.0` - Static 3D Preview Images via F3D

Assessment: **partial coverage**.

- Model responses expose `preview_file`.
- File responses expose `contentUrl`, `encodingFormat`, `contentSize`, and `previewable`.
- That is enough for a custom UI to display the file Manyfold has selected as the preview source.

Gaps:

- The release also introduced derivative-generation settings and workflow behavior; those settings are not exposed as a dedicated REST admin API.
- There is no documented REST surface for derivative configuration, backfill control, or status.
- Native preview-card behavior is richer than what the API advertises directly.

Practical reading: you can consume preview outputs, but you cannot fully administer preview generation from the current REST API.

### `v0.134.0` - Lists and Likes

Assessment: **no first-class REST API coverage**.

- Lists exist in the native app as authenticated HTML routes under `/lists`.
- Likes are implemented as a special "liked" list and native UI buttons patch that list.
- The list and like flows are not present in the OpenAPI document.

Important nuance:

- Manyfold does expose `like_count` into its ActivityPub serializers for federation-facing objects.
- That is not the same as having supported Manyfold REST endpoints for listing likes, toggling likes, reading a user's liked items, or managing arbitrary lists from a custom app.

Impact:

- A custom UI cannot rely on a documented REST contract for lists or likes today.
- For your stated plan, this is likely non-blocking unless you later want a favorites workflow inside your replacement catalog UI.

### `v0.135.0` - Per-Library Path Templates and Path Preview

Assessment: **no REST API coverage**.

- The feature is implemented in library admin UI and a preview route that returns an HTML fragment.
- Libraries are managed through native controllers and forms; the generated API does not expose library CRUD.
- Path-template preview is implemented through `/libraries/preview` and rendered HTML, not through a JSON API.

Impact:

- A custom UI cannot fully replace library setup and path-template management through supported REST calls.
- If you expect to keep a single stable library and manage it infrequently, this may be acceptable.
- If you want your custom UI to own ingestion setup and path parsing, this remains a real gap.

### `v0.136.0` - Comments, Reporting, Moderation

Assessment: **no first-class Manyfold REST API coverage**.

- Comments are handled by `CommentsController` with HTML-oriented routes under the commentable resources.
- Reporting and moderation are similarly native-UI oriented.
- Comments and reports do not appear in the OpenAPI document.

Impact:

- A custom UI cannot safely implement native comment threads, comment deletion, report submission, or moderation queues via the current documented API.
- For your current single-user organizational use case, this appears low priority.

### `v0.137.0` - Comment Federation

Assessment: **ActivityPub coverage, but no Manyfold REST coverage**.

- Federation is implemented through ActivityPub/Federails serializers, handlers, and routes.
- Incoming remote notes become comments, and outgoing comments federate.
- None of this is represented as Manyfold REST endpoints in the documented API.

Impact:

- This matters mainly if you want a social or federated replacement UI.
- For your model-catalog use case, this is background context rather than a primary blocker.

## Native UI Features That Exceed the API Today

These are the biggest gaps between what a user can do in the native UI and what a custom UI can do through the documented API.

### 1. Library and Ingestion Administration

Native UI includes:

- Library create/edit/delete
- Per-library path template configuration
- Parse-preview UI for path templates
- Filesystem scan and library-oriented admin flows

API status:

- No library CRUD in OpenAPI
- No JSON path-template preview endpoint
- No documented admin API for derivative settings or library scanning

This is probably the most important non-metadata gap for your setup.

### 2. Catalog Workflow Operations

Native UI includes:

- Model scan
- Model merge
- Bulk edit and bulk update
- Link sync
- Problem resolution flows

API status:

- These routes exist in the Rails app, but they are not represented in the generated Manyfold API
- A custom UI would not have a supported machine contract for these operations

If your custom catalog needs only basic model editing and tagging, you may not care. If you want deeper curation workflows, you will.

### 3. Search and Filtering Depth

The REST model list supports only a narrow filter set compared with the native UI.

Documented model list filters include:

- `page`
- `order`
- `creator`
- `collection`

Native UI supports materially richer browsing patterns, including:

- Text search (`q`)
- Tag filters
- Link filters
- Library-context browsing
- Various view-specific affordances

Impact:

- A custom UI built only on the documented API will either have weaker browse/search capabilities or need its own companion index/search layer.

### 4. Social and Moderation Features

Native UI includes:

- Lists
- Likes
- Comments
- Comment reporting and moderation
- Follow/unfollow actions
- Local timeline and federation-facing social views

API status:

- No documented REST resources for lists
- No documented REST resources for likes
- No documented REST resources for comments
- No documented REST resources for reports/moderation
- No documented REST resources for follows

These are meaningful parity gaps, but they do not look central to your current catalog-and-linking goal.

### 5. Permissions and Admin Settings

Native UI includes:

- Editing permissions through forms
- Moderation settings
- User management settings
- Site-wide settings, appearance, analysis, federation, and multiuser configuration

API status:

- Current resource schemas for models, creators, and collections do not expose a permissions model
- No dedicated settings/admin REST surface in OpenAPI
- No documented user-management or moderation-management REST API

For a single-user library, this may also be tolerable as long as you are willing to leave those tasks in native Manyfold.

## Clarification: Manyfold Does Not Currently Support Native Custom Fields

Manyfold does **not** appear to provide a general custom-field feature in either:

- the documented REST API, or
- the native UI models reviewed here.

When I referred to "custom metadata fields" earlier, I did **not** mean that Manyfold already has a supported custom-field system that the API fails to expose. I meant the opposite: if you want fields such as archive linkage, external IDs, enrichment state, or your own catalog annotations, Manyfold does not currently give you a clean native field model for them.

### What is available today

The existing model-facing metadata you can use cleanly through the REST API is limited to built-in fields such as:

- `name`
- `caption`
- `description`
- `links`
- `creator`
- `collection`
- `spdx:license`
- `sensitive`
- `keywords`
- `preview_file`

These are real Manyfold fields with corresponding serializers and deserializers.

### What is not available today

The reviewed API and native model surfaces do **not** show support for:

- A freeform JSON metadata object
- Arbitrary key/value fields per model
- Namespaced custom properties owned by third-party apps
- A dedicated external-reference bag for systems like Bambuddy
- Per-model structured annotations for workflow state or enrichment provenance

That means Bambuddy-archive linkage and similar catalog enrichment cannot be stored cleanly in Manyfold via the existing REST API unless you repurpose existing fields like description or links, which is usually a poor fit.

## Implications for Linking Manyfold Models to Bambuddy Archives

This is the part most directly relevant to your plan.

### What Manyfold can already hold reasonably well

Manyfold can already hold:

- The model record itself
- Files and preview assets
- Tags via `keywords`
- Human-facing links via `links`
- General notes/description text
- Creator and collection structure

So if your goal is mainly:

- organize models
- tag them
- browse them visually
- attach normal outbound links

the current API is good enough.

### What does not fit cleanly

It does not cleanly fit structured linkage such as:

- `bambuddy_archive_id`
- `bambuddy_printer_id`
- `print_history_entry_id`
- linkage confidence/status
- enrichment timestamps
- local override flags
- cross-system relationship notes that should not be exposed as user-facing prose

You could force some of this into:

- `links`, if a plain URL is enough
- `description`, if unstructured prose is acceptable
- `keywords`, if a coarse tag is enough

But those are not good substitutes for structured integration metadata.

## Recommended Integration Strategy for Your Use Case

### Short-term recommendation

Treat Manyfold as:

- Canonical storage for models, files, creators, and collections
- Upload and download authority
- Preview/file-hosting authority
- One source of truth for user-facing descriptive metadata

Then keep your structured linkage metadata outside Manyfold in a companion store keyed by Manyfold object URL or public ID.

For your specific use case, that is likely the cleanest design.

### Why this fits your stated plan

You do not want to recreate the entire Manyfold UI.

You primarily want to:

- organize a single-user library
- tag and curate models
- link models to archives and related operational records

That means you can ignore large parts of the native-UI parity problem and focus on a narrower split:

- Manyfold handles archival catalog records and assets
- Your custom catalog layer handles cross-system enrichment and convenience views

### What I would leave in native Manyfold

Even in your narrower plan, these areas are still better left in native Manyfold unless you extend the server:

- Library setup and path-template preview
- OAuth application and token-management UI
- Advanced bulk or scan workflows you may only use occasionally

### What I would comfortably build in a custom UI

- Custom browse surfaces joined with Bambuddy archive metadata
- Alternate tagging and catalog organization views
- Archive linkage dashboards
- Quality-control or enrichment review queues
- Custom search/indexing across Manyfold plus Bambuddy data

## Additional Risks and Notes

### API stability risk

Manyfold's own API documentation explicitly warns that:

- the API is not complete
- it is not yet at v1
- it is subject to breaking changes

That makes it a workable integration target, but not a high-stability platform contract yet.

### Auth bootstrap gap

The token endpoint exists, but OAuth application management is still native-UI-based. A polished custom UI experience for third-party or multi-client integration would need either:

- reliance on native Manyfold for token/app setup, or
- new API endpoints for managing OAuth applications and personal long-lived tokens

### Licensing note

Manyfold changed from MIT to AGPL-3.0 in `v0.135.0`. If you modify and deploy a forked Manyfold server or tightly integrated derivative UI as part of the same deployed application, that has licensing implications and should be reviewed carefully.

## Bottom Line

Manyfold does **not** appear to support native custom fields today. The gap is not "custom fields exist but the API does not expose them." The gap is that neither the reviewed API nor the reviewed UI/model surfaces provide a general-purpose custom metadata facility for structured third-party annotations.

For your actual goal, that is manageable. Manyfold's API is already good enough for core catalog CRUD, files, uploads, tagging, links, and basic organization. The clean approach is to let Manyfold own archival records and assets, while your own catalog layer owns structured linkage metadata such as Bambuddy archive associations.

## Suggested Next Steps

1. Define the external linkage schema you want to own outside Manyfold, especially archive IDs, provenance, sync state, and review flags.
2. Decide which built-in Manyfold fields you want to use directly for user-facing catalog content: tags, links, description, creator, and collection are the obvious candidates.
3. If you want, the next useful artifact is a concrete data model and sync strategy for "Manyfold model <-> Bambuddy archive" linkage.

## Related Docs

- [manyfold-bambuddy-linkage-model.md](c:\dev\hass-bambulab-config\docs\features\model_catalog\manyfold-bambuddy-linkage-model.md)