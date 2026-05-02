"""Intake queue schema.

This module documents the intake queue context. Intake operations
(upload verification, source entry processing, cleanup policies) are
handled by the routers and services.

Tables:
- intake_queue_uploads: Upload session tracking with verification state
"""

# This module is organized by bounded context for schema clarity.
# Intake operations are in routers/intake.py and services/
