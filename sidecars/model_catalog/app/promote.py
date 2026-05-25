"""Promotion logic for catalog entities (Ideas → Models).

This module handles the state transitions defined in #1490:
- Idea → Model: when concept materializes with 3MF/STL files

Authority: Sidecar owns the Catalog schema and promotion state machine.

PR E.3 cleanup: Working Group entity_type promotions and the ``dissolve_working_group``
marker were removed as part of the working-groups deprecation (see
``docs/features/model_catalog/planning/working-groups-deprecation.md``).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .local_models import (
    read_local_model,
    update_local_model,
    LocalModelEntry,
)

logger = logging.getLogger(__name__)

# Valid promotion paths per entity type
PROMOTION_PATHS: dict[str, list[str]] = {
    "idea": ["model"],
    "model": [],  # Terminal state
}


def can_promote(
    from_entity_type: str,
    to_entity_type: str,
) -> bool:
    """Check if a promotion path is valid."""
    return to_entity_type in PROMOTION_PATHS.get(from_entity_type, [])


def promote_entity(
    *,
    db_path: Path,
    local_model_id: str,
    from_entity_type: str,
    to_entity_type: str,
    **promotion_metadata: Any,
) -> LocalModelEntry | None:
    """Promote an entity to a new type.
    
    Args:
        db_path: Path to SQLite database
        local_model_id: Entity to promote
        from_entity_type: Current entity type ('idea', 'model')
        to_entity_type: Target entity type
        **promotion_metadata: Additional context (unused at v1; reserved for future use)
    
    Returns:
        Updated LocalModelEntry or None if promotion fails
    """
    # Validate promotion path
    if not can_promote(from_entity_type, to_entity_type):
        logger.warning(
            f"Invalid promotion path: {from_entity_type} -> {to_entity_type}"
        )
        return None
    
    # Read current entity
    entry = read_local_model(db_path=db_path, local_model_id=local_model_id)
    if not entry:
        logger.warning(f"Entity not found: {local_model_id}")
        return None
    
    # Verify current type matches
    if entry.entity_type != from_entity_type:
        logger.warning(
            f"Entity type mismatch: expected {from_entity_type}, got {entry.entity_type}"
        )
        return None
    
    # At v1, we just flip the entity_type. No validation of file presence yet.
    # This is intentional: the UI/frontend is responsible for confirming
    # preconditions before calling promote_entity.
    logger.info(
        f"Promoting {local_model_id} from {from_entity_type} to {to_entity_type}"
    )
    
    return update_local_model(
        db_path=db_path,
        local_model_id=local_model_id,
        entity_type=to_entity_type,
    )
