# Implementation Strategy Options

> **Status**: Decision reference.
> **Last updated**: 2026-04-22

## Purpose

Compare the three realistic implementation strategies discussed during the design review and record the approved baseline.

## Options

### Option 1: Pure REST Sidecar

Sidecar runs separately and talks to Manyfold only through documented REST APIs.

### Option 2: Same-Stack Sidecar

Sidecar runs in the same Docker stack as Manyfold, may share network and selected volumes, but still treats Manyfold REST as the primary product contract.

### Option 3: Direct Manyfold Enhancement

Implement required capabilities by extending Manyfold directly via fork and/or upstream PRs.

## Decision Matrix

| Dimension | Pure REST Sidecar | Same-Stack Sidecar | Direct Manyfold Enhancement |
|---|---|---|---|
| Delivery speed | Good | Good | Slower for repo-specific needs |
| Upgrade risk | Low | Low to medium | Medium to high if forked |
| Operational complexity | Medium | Medium | Medium |
| Access to internal capabilities | Limited | Limited to moderate via volumes and local topology, but still contract-safe | Highest |
| Data-authority clarity | Strong | Strong | Can blur boundaries if too much is pushed into Manyfold |
| Working veneer fit | Strong | Strongest practical fit | Weak unless Manyfold is changed substantially |
| Curated catalog enhancement fit | Good | Good | Good for broadly useful native features |
| Long-term maintainability | Good | Good | Good only if upstreamed; weaker if long-lived fork |

## Recommendation

Approved baseline:

- prefer **same-stack sidecar** when operationally convenient
- continue using **Manyfold REST** as the primary integration contract
- avoid **direct Manyfold DB writes** as the baseline product strategy

## Why Same-Stack Wins

- keeps deployment ergonomics simple
- allows shared volume access for Working or ingestion helpers when needed
- preserves clean authority boundaries
- avoids binding the solution to Manyfold internals too early

## When Direct Manyfold Enhancement Is Worth It

Pursue upstream PRs selectively when:

- the feature is broadly useful outside this repo
- it naturally belongs in Manyfold's domain
- the sidecar boundary is already clear and proven

Examples might include:

- safe additional REST coverage for native model/file flows
- scan/problem visibility improvements
- native metadata surfaces that would help many users

## What To Avoid

- treating a private Manyfold fork as the first implementation path for repo-specific workflow logic
- binding core model-catalog behavior to direct DB writes
- assuming a fork eliminates the need for Working-group and linkage state outside Manyfold