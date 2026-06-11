# Social Saved Item Capture And Catalog Import Design

> **Status**: Proposed
> **Last updated**: 2026-06-11
> **Functional Owner**: model_catalog
> **Scope**: Turning saved items from Facebook and Instagram into Catalog intake records, with a review-first path to Model, Idea, Project, Collection, or Link Only outcomes.

## Why This Exists

The operator goal is not to mirror Facebook or Instagram. The goal is to turn saved items that represent 3D models, inspiration, or project leads into usable Catalog records with enough provenance to act on later.

This design assumes two facts:

1. Meta does not expose a supported consumer API for reading a user’s saved items or saved collections as a general-purpose catalog export surface.
2. The most realistic paths are manual export, browser-side capture, or authenticated automation that the user runs against their own account.

That means the product decision is not “which official API should we call?” It is “which capture path gives the best reliability, least user friction, and safest ingestion contract for the Catalog?”

## What Meta Officially Supports

The public Instagram Platform APIs are aimed at professional accounts and cover publishing, comments, insights, mentions, messaging, and embeds. They are not a saved-items export API.

For this use case, the useful conclusion is simple:

- do not design around a supported saved-items API
- do not assume saved posts can be read from the platform as a stable official endpoint
- treat consumer saved items as an external capture problem, not a platform integration problem

## Practical Options

| Option | What it can do | Strengths | Limits |
|---|---|---|---|
| Official Meta API | N/A for saved-item readout | Stable if it existed | No supported saved-items read path found |
| Instagram/Facebook data export | Potential manual backfill source | User-owned data path, lower policy risk than scraping | Not a live workflow and may not produce a clean Catalog-ready stream |
| Browser automation | Read current saved page and extract links or metadata | Best for authenticated access to the user’s own saved list | Fragile if the UI changes; needs logged-in session |
| Browser extension | Capture saved items in-page and push to the Catalog | Lowest-friction ongoing workflow on desktop | Requires custom extension work or adaptation |
| iOS Shortcuts | Capture one shared post or URL at a time | Good for mobile sharing and quick capture | Not a bulk export path |
| Open-source download/export tool | Backfill saved items into local files or CSV | Fastest way to seed a local archive | Often best as a one-time or periodic backfill, not a polished operator UX |

## Open Source Tools Worth Leveraging

### Instaloader

Instaloader is the strongest general-purpose open-source baseline for Instagram-side backfill.

What it gives us:

- saved-media support via the `:saved` target
- metadata and captions alongside media
- mature Python codebase
- a well-known CLI and library surface

What it does not solve by itself:

- turning saved items into Catalog entities with review states
- Facebook saved-item capture
- operator-friendly desktop/mobile workflows

Best use here:

- batch export of saved Instagram items into a local staging area
- one-time or periodic backfill before the interactive workflow exists

### mon-jai/instagram-export

This project is a good reference for a local archive-first workflow.

What it gives us:

- archive-oriented export for Instagram collections
- saved URL support, including `/saved/all-posts/` and collection URLs
- a browser-driven fetch flow and a local archive viewer

Why it matters here:

- it demonstrates a path from saved lists to a structured archive rather than just raw downloads
- it is closer to a reusable ingestion pipeline than a simple scraper script

Best use here:

- backfill or migration starting point
- reference implementation for archive structure and incremental fetch semantics

### skd1993/instagram-saved-scraper

This is a smaller legacy scraper that exports saved collections to CSV.

What it gives us:

- proof that the saved-collection page can be traversed and normalized into tabular output
- a simple list of extracted fields that can inform our intake schema

Limits:

- old and described by the author as hacky
- login/session handling is not a product-grade workflow
- better as a reference than as a foundation

Best use here:

- field discovery only
- quick prototype for CSV-shaped extraction

### ShaadyEmad/Instagram-Collection-Downloader

This is a GUI-oriented scraper/downloader for private saved collections.

What it gives us:

- Selenium-based traversal of the saved collection page
- a concrete “log in, scroll saved items, extract post URLs” pattern
- media download via yt-dlp

Limits:

- strong on download, weaker on structured metadata and Catalog integration
- desktop-only and operationally brittle compared with a purpose-built extension or sidecar route

Best use here:

- reference for browser automation behavior
- fallback for media-heavy backfill

## Recommended Product Direction

The best long-term shape is a hybrid capture system:

1. **Backfill path** for existing saved items
2. **Desktop browser capture** for ongoing use
3. **Mobile share-sheet capture** for one-off saves
4. **Optional automation fallback** only where it materially reduces friction

### Recommendation 1: Backfill first, with a local archive tool

Use an open-source exporter such as Instaloader or instagram-export to seed the initial dataset.

That gives us:

- immediate value without waiting for a custom extension
- a way to test the Catalog intake schema on real saved items
- a simple path to import a large historical backlog

### Recommendation 2: Build a lightweight browser extension or userscript

This should be the primary ongoing capture path on desktop.

The extension should:

- run on the Instagram or Facebook saved page
- extract the post URL, creator, caption preview, thumbnail, and any visible collection name
- send normalized payloads to the existing intake endpoint
- default the destination to `idea` or `link_only` unless the URL clearly resolves to a model page

This is the best place to add convenience without depending on Meta product changes.

### Recommendation 3: Add an iOS Shortcut for single-item capture

Shortcuts can receive shared content from the share sheet and act on URLs or copied text.

Use this for:

- “share this post into Catalog”
- “capture this URL to review later”
- quick mobile handoff when browsing on iPhone

This should stay intentionally small. It is a convenience path, not the bulk-ingestion path.

### Recommendation 4: Do not build on direct scraping as the only strategy

Pure scraping is acceptable as a technical mechanism, but not as the only design.

Reasons:

- UI changes will break it
- it is harder to reuse across desktop and mobile
- it is harder to make review-first and catalog-aware

Scraping should be a transport detail underneath a deliberate intake flow.

## Delivery Stages

### Stage 0: Decide the first capture target

The Catalog should treat saved items as one of these starting points:

- `idea` when the item is inspirational, incomplete, or ambiguous
- `link_only` when there is not enough metadata to justify a richer record yet
- `project` when the saved item clearly belongs to an active build effort
- `model` only when the saved item resolves to a canonical model page or downloadable model asset

This avoids forcing every save into a model record too early.

### Stage 1: Historical backfill

Goal: convert existing saved items into catalog entries without creating a UI dependency first.

Implementation shape:

- export saved items from a local authenticated session
- normalize to a staging format such as JSON or CSV
- import into the existing intake queue as review-required records
- preserve the original source URL and capture path

Outcome:

- the user gets immediate Catalog value from their existing saved history
- we validate the mapping from saved posts to catalog entities

### Stage 2: Desktop capture extension

Goal: make saving to the Catalog a one-click desktop action.

Implementation shape:

- browser extension or userscript on Instagram/Facebook saved pages
- extract visible post links and metadata
- post to the sidecar intake endpoint
- auto-suggest `idea` with a confidence score unless the post clearly points to a model source

Outcome:

- ongoing use becomes fast enough to stick
- the Catalog starts to receive saved items close to the moment they are saved

### Stage 3: Mobile share-sheet shortcut

Goal: capture a single saved item or shared post from iOS without requiring desktop access.

Implementation shape:

- Shortcuts action that accepts shared URLs or text
- normalize the URL and hand off to the same intake endpoint used by desktop capture
- keep the shortcut simple enough that it is trustworthy

Outcome:

- a mobile-friendly capture path for items discovered away from the desktop

### Stage 4: Optional semi-automated sync

Goal: reduce manual effort for users who save a lot of references.

Implementation shape:

- authenticated periodic capture against the saved list, only from the user’s own account
- batch materialize new items into the queue
- require review before commit

Outcome:

- the Catalog becomes a maintained inbox instead of a manual upload chore

This stage should be optional because it is the most fragile and the most policy-sensitive.

## Catalog Routing Rules

The intake contract from the broader external-source design applies here too.

Recommended routing:

- `social_saved_link` as the source profile
- `user_direct` for manual share/capture
- `batch_materialization` for a backfill or sync run
- `idea` as the default target
- `project` as the secondary target when the save has obvious build intent
- `model` only when the source clearly resolves to a model listing
- `link_only` when metadata is too weak to do anything safer

### Suggested payload fields

- source service: Facebook or Instagram
- source URL
- saved collection name, when visible
- creator handle or page name, when visible
- caption or text snippet
- thumbnail or preview URL, when available
- capture method: backfill, browser extension, shortcut, or manual paste
- confidence score
- suggested Catalog target

## Operational Constraints

- Capture only content the operator has rights or permission to save and process.
- Keep credentials inside the user’s authenticated browser or device session; do not ask for passwords in the app.
- Use review-first commit behavior for anything sourced from social saves.
- Treat the source page as unstable and design for graceful degradation.
- Do not assume a saved post is itself a 3D model. Many saves are just signals that point to a model page, a creator, or a project idea.

## Open Questions

1. Do we want the first release to support Instagram only, or Instagram plus Facebook from the same capture surface?
2. Should the first catalog target default to `idea` or `link_only` for ambiguous saves?
3. Do we want the browser extension to extract metadata only, or also initiate optional downloads when a 3D model source is detected?
4. Should a saved collection name become a Catalog Collection automatically, or remain review-only until the user confirms?

## Related Docs

- [External Source Intake Design](external-source-intake.md)
- [Intake Source Routing Contract](../reference/intake-source-routing-contract.md)
- [Intake Home and Queue Review Mockups](intake-home-queue-mockups.md)
