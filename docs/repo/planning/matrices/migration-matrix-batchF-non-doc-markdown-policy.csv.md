# Batch F Detailed Matrix: non_doc_markdown_policy

Source scope: markdown outside docs in sidecars/tests/openhasp/wled backups/archive notes
Row count: 14

Post-cleanup interpretation note (2026-05-23):
1. current_path is a migration-source field and may reference paths retained as local artifacts.
2. target_path is the canonical documentation destination (often in-place for local artifact docs).

Label alignment: this detailed matrix maps to owner-area F (non-doc markdown policy) in documentation-migration-matrix.md.
Format: raw CSV text for machine import (spreadsheets/scripts).

current_path,owner_area,intended_lane,status,target_path,redirect_needed,notes
sidecars/model_catalog/README.md,non_doc_markdown_policy,local-artifact,Active,sidecars/model_catalog/README.md,No,Implementation-adjacent sidecar guide; canonical docs cross-linked to docs/features/model_catalog
sidecars/model_catalog/app/README.md,non_doc_markdown_policy,local-artifact,Active,sidecars/model_catalog/app/README.md,No,Module-level implementation notes retained in-place
sidecars/bambuddy-runtime-repair/README.md,non_doc_markdown_policy,local-artifact,Active,sidecars/bambuddy-runtime-repair/README.md,No,Operational sidecar runbook retained in-place with canonical doc cross-links
tests/sidecars/model_catalog/README.md,non_doc_markdown_policy,local-artifact,Active,tests/sidecars/model_catalog/README.md,No,Test-suite quick reference retained in-place with canonical docs link
tests/sidecars/model_catalog/VALIDATION_TEST_REPORT.md,non_doc_markdown_policy,historical-test-artifact,Active,tests/sidecars/model_catalog/VALIDATION_TEST_REPORT.md,No,Validation report retained as historical test evidence
tests/spool_matching/README.md,non_doc_markdown_policy,local-artifact,Active,tests/spool_matching/README.md,No,Fixture-test notes retained in-place with canonical docs link
openhasp/README.md,non_doc_markdown_policy,local-artifact,Active,openhasp/README.md,No,Device-side files index retained with canonical docs link
openhasp/archive/xtouch-archive/README.md,non_doc_markdown_policy,archive-artifact,Active,openhasp/archive/xtouch-archive/README.md,No,Explicitly historical archive notes
openhasp/archive/xtouch-archive/XTOUCH_UI_VISUAL_SPEC.md,non_doc_markdown_policy,archive-artifact,Active,openhasp/archive/xtouch-archive/XTOUCH_UI_VISUAL_SPEC.md,No,Archived visual specification retained for provenance
wled/backups/README.md,non_doc_markdown_policy,local-artifact,Active,wled/backups/README.md,No,Backup operations guide retained with canonical docs link
wled/backups/magwled/NOTES_TEMPLATE.md,non_doc_markdown_policy,template-artifact,Active,wled/backups/magwled/NOTES_TEMPLATE.md,No,Snapshot notes template retained in-place
wled/backups/digquad/README_TEMPLATE.md,non_doc_markdown_policy,template-artifact,Active,wled/backups/digquad/README_TEMPLATE.md,No,Snapshot notes template retained in-place
wled/backups/digquad/2026-03-13.2 - Phase 1 Implemented/README.md,non_doc_markdown_policy,archive-artifact,Active,wled/backups/digquad/2026-03-13.2 - Phase 1 Implemented/README.md,No,Dated backup snapshot notes retained as historical artifact
wled/backups/digquad/2026-03-13.1 - Preinstall (baseline config)/readme.md,non_doc_markdown_policy,archive-artifact,Active,wled/backups/digquad/2026-03-13.1 - Preinstall (baseline config)/readme.md,No,Dated baseline backup notes retained as historical artifact
