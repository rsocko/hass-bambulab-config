# Legacy Router Snapshots (Reference Only)

This folder holds historical snapshots of inactive model-catalog router code.

Rules:
- Do not import files from this folder in runtime code.
- Do not place snapshot copies inside `sidecars/model_catalog/app/routers/`.
- Keep active router implementations authoritative in `sidecars/model_catalog/app/routers/`.
- Add a short note in related docs when a snapshot is added here.

Current snapshot inventory:
- `intake_old.py`: pre-decomposition intake router snapshot retained for historical reference.
