# hass-bambulab-config

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: repo-docs
Replaces: none
Replaced By: none

This repo is a collection of the configuration and automation that I use within Home Assistant for integrating with my Bambu Lab 3D printer and related services (like Spoolman).

## Documentation Navigation

Start here for canonical documentation:

- [docs/README.md](docs/README.md)
- [docs/repo/planning/documentation-organization-guidance-and-migration-plan.md](docs/repo/planning/documentation-organization-guidance-and-migration-plan.md)
- [docs/repo/planning/documentation-migration-matrix.md](docs/repo/planning/documentation-migration-matrix.md)

Documentation lifecycle lanes used across owner areas:

1. `reference` - current as-built truth.
2. `design` - decision context and rationale.
3. `planning` - pre-implementation plans.
4. `archive` - historical, non-canonical artifacts.

## Core Entry Points

- Repository documentation index: [docs/README.md](docs/README.md)
- Feature docs root: [docs/features](docs/features)
- Deployment workflow reference: [docs/repo/deployment-workflow-reference.md](docs/repo/deployment-workflow-reference.md)
- Repository structure guide: [docs/repo/repo-layout.md](docs/repo/repo-layout.md)
- Detailed repository capabilities and operations reference: [docs/repo/reference/repository-capabilities-and-operations-reference.md](docs/repo/reference/repository-capabilities-and-operations-reference.md)

## Local Development and Testing Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pytest
```

For focused workflows and deeper operational context, use:

- [docs/repo/quick-start.md](docs/repo/quick-start.md)
- [docs/repo/reference/repository-capabilities-and-operations-reference.md](docs/repo/reference/repository-capabilities-and-operations-reference.md)

## Local Git Hook Setup

To enable the repo-managed pre-push guard for Lovelace JS cache-bust changes:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\setup-git-hooks.ps1
```

That sets `core.hooksPath` to `.githooks`, which enables `.githooks/pre-push` for this clone.
The hook runs `.github/scripts/check_lovelace_resource_versions.py` before each push and blocks the push if changed `homeassistant/www/3d_printing/**/*.js` files do not have the matching version bump chain.

If you want to run the same check manually in VS Code before pushing, use the task `Run Lovelace Resource Cache-Bust Check`.
That task now publishes failures into the Problems panel with clickable file links.
