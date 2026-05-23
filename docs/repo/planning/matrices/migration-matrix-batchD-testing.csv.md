# Batch D Detailed Matrix: testing_docs

Source scope: docs/testing/*.md
Row count: 3

Post-cleanup interpretation note (2026-05-23):
1. `current_path` is a migration-source field and may reference paths removed by lane migration cleanup.
2. `target_path` is the canonical destination for active docs.

Label alignment: this detailed matrix maps to owner-area `D` (testing docs) in documentation-migration-matrix.md.
Format: raw CSV text for machine import (spreadsheets/scripts).

current_path,owner_area,intended_lane,status,target_path,redirect_needed,notes
docs/testing/QUICKSTART.md,testing_docs,reference,Active,docs/testing/reference/quickstart.md,Yes,Testing quick-start runbook
docs/testing/phase3-test-automation.md,testing_docs,reference,Active,docs/testing/reference/phase3-test-automation.md,Yes,Automation test guide
docs/testing/phase3-test-report.md,testing_docs,archive,Active,docs/testing/archive/phase3-test-report.md,Yes,Dated phase test report summary
