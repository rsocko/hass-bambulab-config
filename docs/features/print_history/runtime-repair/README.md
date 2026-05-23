# Print History Runtime Repair Docs

This folder holds the canonical-runtime repair and sidecar-backed restore docs.

- `archive-metadata-correction-design.md` - design for sidecar-backed single-archive metadata correction from Advanced Actions
- `../reference/archive-runtime-db-repair-guide.md` - direct DB repair guidance
- `../reference/archive-runtime-field-impact-matrix.md` - field-level impact analysis
- `archive-runtime-ha-contract.md` - Home Assistant repair contract guidance, including `bambuddy.repair_print_history_archive_from_start`
- `archive-runtime-repair-deployment-options.md` - deployment tradeoffs
- `archive-runtime-repair-script-and-n8n-flow.md` - script and orchestration workflow
- `archive-runtime-sidecar-api-and-compose.md` - sidecar API and compose contract
- `../planning/print-history-er-diagrams.md` - schema baseline and sidecar field touchpoint matrix
- `archive-runtime-restore-ha-ux-design.md` - restore UX design
- `../reference/archive-runtime-restore-ha-service-and-popup-contract.md` - HA service and popup contract
- `archive-runtime-restore-implementation-plan.md` - implementation plan
- `../reference/archive-runtime-restore-from-field-matrix.md` - source-to-target field merge policy
- `archive-runtime-restore-from-runbook.md` - operator runbook
- `../reference/archive-runtime-restore-from-example-191-200.md` - worked example

Start with `archive-runtime-sidecar-api-and-compose.md` if you are implementing sidecar-backed restore behavior.