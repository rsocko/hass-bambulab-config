# Manyfold API Design Notes

> **Status**: Current-state integration notes based on upstream review as of 2026-04-21.

## Purpose

Capture the parts of Manyfold that are relevant to this repo's planned model-library work in Home Assistant.

## Current Strengths

Manyfold is currently the stronger candidate for:

- model-oriented metadata
- creators and collections
- long-lived source-library browsing
- embeddable model viewing
- API-driven model updates

## Relevant Capability Summary

### Library And Scan Model

Manyfold can point at an existing filesystem library and scan it directly.

Important caveat:

- it is still a managed library model, not a passive read-only catalog design
- organize or path-template behavior can move or rename files
- Manyfold-managed artifacts such as `datapackage.json` and `.manyfold` derivative data are part of the broader design space

That makes it a poor co-owner of a shared writable tree.

### Metadata Surface

Manyfold exposes a richer model metadata domain than Bambuddy.

Current model concepts include:

- name
- notes or description
- tags
- creator
- collection
- license
- preview file
- linked files

### API Direction

Current upstream direction indicates usable read and write API surfaces for:

- listing models
- reading model detail
- updating model metadata
- reading collections
- updating collection metadata

This makes Manyfold a better fit than Bambuddy for Home Assistant write-back against a reusable source-model library.

### Embedding Direction

Manyfold is currently the better iframe candidate for model browsing and 3D model display.

That does not mean iframe should be the only integration path. It means Manyfold can carry more of the rich browsing UI while HA owns cross-system orchestration.

## Risks And Caveats

### Filesystem Ownership Risk

Manyfold should not share write authority over the same tree Bambuddy may also manage.

### Sync Scope Risk

Manyfold has better model metadata than Bambuddy, but not every field should be mirrored blindly into HA or Bambuddy.

The repo should prefer:

- explicit link facts
- selective surfaced metadata
- low-ambiguity write-back rules

### UI Scope Risk

If HA tries to replace all Manyfold UI flows, the implementation burden rises quickly.

The likely better model is:

- Manyfold remains the deep model-editor UI when needed
- HA provides the operational overview and cross-system shortcuts

## Recommended Role In This Repo

If Manyfold is kept in the architecture, its recommended role is:

- authoritative source-model library on its own folder tree
- metadata source for creators, collections, tags, notes, and source links
- optional embedded browse or view surface inside HA
- target for selective HA-driven write-back

It should not be treated as the archive system, and it should not be allowed to co-manage the same writable library tree as Bambuddy.