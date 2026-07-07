# Bambuddy & Spoolman Release Review — July 2026

## Overview

This directory contains spec documents assessing new releases of Bambuddy (v0.2.5 beta / v0.1.6 stable) and Spoolman (v0.23.0 / v0.23.1) against our `hass-bambulab-config` integration surface area.

## Releases Reviewed

| Software | Version | Type | Date |
|----------|---------|------|------|
| Bambuddy | v0.1.6 | Stable | 2026-01-31 |
| Bambuddy | v0.2.5b2-daily.20260706 | Daily Beta | 2026-07-06 |
| Spoolman | v0.23.0 | Stable | 2026-01-?? |
| Spoolman | v0.23.1 | Stable | 2026-02-?? |

## Spec Documents

| Document | Topic | Impact |
|----------|-------|--------|
| [build-plate-detection.md](./build-plate-detection.md) | Build Plate Detection — entities, storage, usage | New capability |
| [model-queue-scheduling.md](./model-queue-scheduling.md) | Model-based Queue — relevance assessment | Assessment |
| [advanced-auth.md](./advanced-auth.md) | Advanced Authentication — work & considerations | Configuration |
| [prometheus-bambuddy-metrics.md](./prometheus-bambuddy-metrics.md) | Bambuddy Prometheus Metrics endpoint | New capability |
| [external-camera-fix.md](./external-camera-fix.md) | External Camera transcoding fix — impact analysis | Low impact |
| [spoolman-adjust-spool.md](./spoolman-adjust-spool.md) | Adjust Spool / Measured Weight — API & coordination | Integration risk |
| [pwa-sidebar-embedding.md](./pwa-sidebar-embedding.md) | PWA support for Spoolman — future ideas | Future |
| [cors-considerations.md](./cors-considerations.md) | CORS variable — when it matters and how to configure | Configuration |

## Summary Verdict

- **Breaking changes:** None. Both releases are backwards-compatible.
- **Action required:** Auth considerations if upgrading to Bambuddy v0.2.x; Spoolman `adjust spool` coordination with our automations.
- **New opportunities:** Build plate tracking, Bambuddy native Prometheus metrics, queue scheduling enrichment.
