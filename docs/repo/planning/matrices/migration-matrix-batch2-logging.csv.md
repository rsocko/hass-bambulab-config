# Batch 2 Detailed Matrix: logging

Source scope: docs/features/logging/**/*.md
Row count: 8

Label alignment: this detailed matrix maps to global `C2` in documentation-migration-matrix.md.
Format: raw CSV text for machine import (spreadsheets/scripts).

Post-cleanup note (2026-05-23):
1. `current_path` values are historical migration-source paths, not a required current filesystem assertion.
2. `target_path` values identify canonical destinations for active docs.

current_path,owner_area,intended_lane,status,target_path,redirect_needed,notes
docs/features/logging/README.md,logging,root-readme,Active,docs/features/logging/README.md,No,Primary entry point
docs/features/logging/ARCHITECTURE.md,logging,design,Active,docs/features/logging/design/architecture.md,Yes,System architecture and boundaries
docs/features/logging/implementation-summary.md,logging,archive,Historical,docs/features/logging/archive/implementation-summary.md,Yes,Historical implementation snapshot
docs/features/logging/quick-start.md,logging,reference,Active,docs/features/logging/reference/quick-start.md,Yes,Operator quick-start guide
docs/features/logging/integrations/loki-promtail-README.md,logging,reference,Active,docs/features/logging/reference/integrations/loki-promtail.md,Yes,Loki and Promtail integration runbook
docs/features/logging/integrations/prometheus-README.md,logging,reference,Active,docs/features/logging/reference/integrations/prometheus.md,Yes,Prometheus metrics integration runbook
docs/features/logging/integrations/syslog-README.md,logging,reference,Active,docs/features/logging/reference/integrations/syslog.md,Yes,Syslog forwarding integration runbook
docs/features/logging/integrations/webhook-README.md,logging,reference,Active,docs/features/logging/reference/integrations/webhook.md,Yes,Webhook forwarding integration runbook
