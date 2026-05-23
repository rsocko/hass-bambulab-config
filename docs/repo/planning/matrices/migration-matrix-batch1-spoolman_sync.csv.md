# Batch 1 Detailed Matrix: spoolman_sync

Source scope: docs/features/spoolman_sync/**/*.md
Row count: 42

Label alignment: local `Batch 1` = global `C1` in documentation-migration-matrix.md.
Format: raw CSV text for machine import (spreadsheets/scripts).

current_path,owner_area,intended_lane,status,target_path,redirect_needed,notes
docs/features/spoolman_sync/README.md,spoolman_sync,root-readme,Active,docs/features/spoolman_sync/README.md,No,Primary entry point for feature
docs/features/spoolman_sync/solution-summary.md,spoolman_sync,archive,Completed,docs/features/spoolman_sync/archive/solution-summary-print-weight-persistence.md,Yes,Historical completion summary for print weight persistence solution
docs/features/spoolman_sync/spool-replace-refill-design.md,spoolman_sync,design,Active,docs/features/spoolman_sync/design/spool-replace-refill.md,Yes,Multi-phase design (Phases 1-5)
docs/features/spoolman_sync/spool-replace-refill-testing.md,spoolman_sync,planning,Active,docs/features/spoolman_sync/planning/spool-replace-refill-test-plan.md,Yes,Test plan for Phases 1-3
docs/features/spoolman_sync/ams-tray-assignment-phase3-test-plan.md,spoolman_sync,planning,Active,docs/features/spoolman_sync/planning/ams-tray-assignment-phase3-test-plan.md,Yes,UI integration validation test plan
docs/features/spoolman_sync/installation-guide.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/persistent-error-logging-installation.md,Yes,Installation runbook for error logging system
docs/features/spoolman_sync/quick-reference.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/error-logging-quick-reference.md,Yes,Quick reference card for error logging
docs/features/spoolman_sync/ams-tray-assignment-design.md,spoolman_sync,design,Active,docs/features/spoolman_sync/design/ams-tray-assignment.md,Yes,Core design for pushing metadata from Spoolman to printer trays
docs/features/spoolman_sync/bambuddy-partial-usage-implementation-plan.md,spoolman_sync,planning,Active,docs/features/spoolman_sync/planning/bambuddy-partial-usage-implementation-plan.md,Yes,Plan-only execution path for failed/partial print filament accounting
docs/features/spoolman_sync/error-logging-implementation-summary.md,spoolman_sync,archive,Completed,docs/features/spoolman_sync/archive/error-logging-pr-summary.md,Yes,PR completion summary for persistent error logging feature
docs/features/spoolman_sync/bambuddy-partial-usage-contracts.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/bambuddy-partial-usage-contracts.md,Yes,API and policy contracts for partial-usage workflow
docs/features/spoolman_sync/spool-replace-refill-wireframes.md,spoolman_sync,design,Active,docs/features/spoolman_sync/design/spool-replace-refill-wireframes.md,Yes,Popup wireframes and implementation checklist
docs/features/spoolman_sync/entity-relationship-diagram.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/entity-relationship-diagram.md,Yes,Runtime entities and operational contracts
docs/features/spoolman_sync/sensor-rest-spoolman-api-get-spools.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/sensor-rest-spoolman-api-get-spools.md,No,REST integration configuration for Spoolman spools
docs/features/spoolman_sync/print-complete-update-filament-usage.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/print-complete-update-filament-usage.md,No,Core automation for updating Spoolman on print completion
docs/features/spoolman_sync/spoolman-purchase-import.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/spoolman-purchase-import-workflow.md,Yes,Workflow for turning purchase confirmations into spool records
docs/features/spoolman_sync/bambuddy-partial-usage-rollout-validation.md,spoolman_sync,planning,Active,docs/features/spoolman_sync/planning/bambuddy-partial-usage-rollout-runbook.md,Yes,Rollout and validation runbook for partial-usage feature
docs/features/spoolman_sync/spool-matching-design-analysis.md,spoolman_sync,design,Active,docs/features/spoolman_sync/design/spool-matching-logic-unification.md,Yes,Comparison and unification recommendations for spool-matching logic
docs/features/spoolman_sync/print-weight-persistence.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/print-weight-persistence-overview.md,Yes,Solution overview for HA restart during active print
docs/features/spoolman_sync/reset-tray-filament-design.md,spoolman_sync,design,Active,docs/features/spoolman_sync/design/reset-tray-filament.md,Yes,Design for resetting tray filament info
docs/features/spoolman_sync/multicolor-spool-matching-design.md,spoolman_sync,design,Active,docs/features/spoolman_sync/design/multicolor-spool-matching.md,Yes,Design for automatic multi-color spool matching
docs/features/spoolman_sync/missed-print-recovery-design.md,spoolman_sync,design,Active,docs/features/spoolman_sync/design/missed-print-recovery.md,Yes,Design for recovery of missed successful-print decrements
docs/features/spoolman_sync/manual-spool-matching-design.md,spoolman_sync,design,Active,docs/features/spoolman_sync/design/manual-spool-matching.md,Yes,Design for user-controlled pin/unpin tray matching
docs/features/spoolman_sync/find-matching-spools.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/find-matching-spool-script.md,Yes,Home Assistant script for identifying spool from tray metadata
docs/features/spoolman_sync/error-logging-flow.md,spoolman_sync,design,Active,docs/features/spoolman_sync/design/error-logging-flow.md,Yes,Flow diagram for print job error handling
docs/features/spoolman_sync/batch-assignment-scenarios.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/batch-assignment-scenarios.md,Yes,Scenarios for concurrent and batched spool events
docs/features/spoolman_sync/active-tray-changed-update-spoolman.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/active-tray-changed-update-automation.md,Yes,Automation for updating Spoolman last-used on tray changes
docs/features/spoolman_sync/spoolman-custom-fields.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/spoolman-custom-fields.md,No,Extra fields required in Spoolman instance
docs/features/spoolman_sync/popup-reactivity-refactor-design.md,spoolman_sync,design,Active,docs/features/spoolman_sync/design/popup-reactivity-refactor.md,Yes,Design for AMS and Filament Catalog popup reactivity refactor
docs/features/spoolman_sync/reload-spoolman-integration-nightly.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/reload-spoolman-integration-automation.md,Yes,Nightly automation for reloading Spoolman integration
docs/features/spoolman_sync/spoolman-integration-memory-analysis.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/spoolman-integration-memory-analysis.md,Yes,Performance and memory analysis of Spoolman HA integration
docs/features/spoolman_sync/system-logging.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/system-logging-overview.md,Yes,System logging implementation overview for automations
docs/features/spoolman_sync/update-spool-last-used.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/update-spool-last-used-script.md,Yes,Home Assistant script for updating last/first used timestamps
docs/features/spoolman_sync/persistent-error-logging.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/persistent-error-logging.md,No,Implementation overview for error logging system
docs/features/spoolman_sync/ams-tray-assignment-phase2-test-plan.md,spoolman_sync,planning,Active,docs/features/spoolman_sync/planning/ams-tray-assignment-phase2-test-plan.md,Yes,Validation plan for Phase 2
docs/features/spoolman_sync/ams-tray-assignment-data-mapping.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/ams-tray-assignment-data-mapping.md,Yes,Data mapping reference for tray assignment
docs/features/spoolman_sync/spool-matching-validation-self-test.md,spoolman_sync,planning,Active,docs/features/spoolman_sync/planning/spool-matching-validation-self-test.md,Yes,Self-test validation plan for spool matching logic
docs/features/spoolman_sync/bambuddy-partial-usage-sidecar-design.md,spoolman_sync,design,Active,docs/features/spoolman_sync/design/bambuddy-partial-usage-sidecar.md,Yes,Design for partial-usage sidecar service
docs/features/spoolman_sync/print-weight-persistence-visual.md,spoolman_sync,design,Active,docs/features/spoolman_sync/design/print-weight-persistence-visual.md,Yes,Visual flow diagram for system architecture
docs/features/spoolman_sync/print-weight-persistence-quickstart.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/print-weight-persistence-quickstart.md,Yes,Quick start guide for print weight persistence
docs/features/spoolman_sync/print-weight-persistence-implementation.md,spoolman_sync,archive,Completed,docs/features/spoolman_sync/archive/print-weight-persistence-implementation.md,Yes,Implementation summary for print weight persistence
docs/features/spoolman_sync/notification-example.md,spoolman_sync,reference,Active,docs/features/spoolman_sync/reference/error-notification-example.md,Yes,Example persistent notification for Spoolman sync errors
