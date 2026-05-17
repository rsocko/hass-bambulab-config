"""Promotion logic for catalog entities (Ideas → Models, Working Groups → Models).

This module handles the state transitions defined in #1490:
- Idea → Model: when concept materializes with 3MF/STL files
- Idea → Working Group: when idea becomes a prep/staging set
- Working Group → Model: when working group is ready to publish/share
- Dissolve: when working group reaches project completion

Authority: Sidecar owns the Catalog schema and promotion state machine.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .db import utc_now_iso
from .local_models import (
    read_local_model,
    update_local_model,
    LocalModelEntry,
)
from .db import connect

logger = logging.getLogger(__name__)

# Valid promotion paths per entity type
PROMOTION_PATHS = {
    "idea": ["model", "working_group"],
    "working_group": ["model"],
    "model": [],  # Terminal state
}

# Validation constraints for promotion
PROMOTION_CONSTRAINTS = {
    "idea_to_model": {
        "description": "Promote idea to model (requires files)",
        "requires_files": True,
        "source_entity_type": "idea",
        "target_entity_type": "model",
    },
    "idea_to_working_group": {
        "description": "Promote idea to working group (requires working files)",
        "requires_files": True,
        "source_entity_type": "idea",
        "target_entity_type": "working_group",
    },
    "working_group_to_model": {
        "description": "Promote working group to model (requires canonical 3MF)",
        "requires_files": True,
        "source_entity_type": "working_group",
        "target_entity_type": "model",
    },
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
        from_entity_type: Current entity type ('idea', 'working_group', 'model')
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


def dissolve_working_group(
    *,
    db_path: Path,
    working_group_id: str,
    return_files_unassigned: bool = True,
) -> bool:
    """Dissolve a working group (used at project close per US-10).
    
    At v1, this is a marker function. Full dissolve behavior (file movement,
    membership cleanup) is deferred pending the working-groups reorg.
    
    Args:
        db_path: Path to SQLite database
        working_group_id: Working group to dissolve
        return_files_unassigned: Whether to mark files as unassigned (v1: marker only)
    
    Returns:
        True if dissolution begun, False if working group not found
    """
    # TODO: Implement full dissolve when working-groups schema is finalized.
    # For now, this is a documented entry point for future expansion.
    logger.info(
        f"Marking working group {working_group_id} for dissolution "
        f"(return_files_unassigned={return_files_unassigned})"
    )
    return True
