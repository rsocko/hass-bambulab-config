"""
Intake action eligibility service.

Centralized contract for which actions are valid in each intake state.
Used by both backend API endpoints and frontend UI to maintain consistency.
"""

from __future__ import annotations

from typing import Any

# Terminal states: once reached, intake workflow is complete
TERMINAL_STATES = {"grouped_new", "grouped_existing", "published_to_catalog", "published_by_destination", "rejected"}

# Active Queue states: operator decisions in progress
ACTIVE_QUEUE_STATES = {"submitted", "validated_ready", "validated_warning", "deferred"}

# All valid states
ALL_INTAKE_STATES = TERMINAL_STATES | ACTIVE_QUEUE_STATES


class ActionEligibility:
    """Defines which actions are valid for each intake state."""

    # Action names
    VALIDATE = "validate"
    GROUP_NEW = "group_new"
    GROUP_EXISTING = "group_existing"
    PUBLISH_CATALOG = "publish_catalog"
    DEFER = "defer"
    REJECT = "reject"
    REOPEN = "reopen"
    DELETE = "delete"

    # Eligibility matrix: state -> set of allowed actions
    ELIGIBILITY_MATRIX: dict[str, set[str]] = {
        "submitted": {VALIDATE, GROUP_NEW, GROUP_EXISTING, PUBLISH_CATALOG, DEFER, REJECT, DELETE},
        "validated_ready": {VALIDATE, GROUP_NEW, GROUP_EXISTING, PUBLISH_CATALOG, DEFER, REJECT, DELETE},
        "validated_warning": {VALIDATE, GROUP_NEW, GROUP_EXISTING, DEFER, REJECT, DELETE},
        "deferred": {VALIDATE, GROUP_NEW, GROUP_EXISTING, PUBLISH_CATALOG, REJECT, DELETE},
        "grouped_new": {DELETE, REOPEN},
        "grouped_existing": {DELETE, REOPEN},
        "published_to_catalog": {DELETE, REOPEN},
        "published_by_destination": {DELETE, REOPEN},
        "rejected": {DELETE, REOPEN},
    }

    @staticmethod
    def is_terminal(state: str) -> bool:
        """Check if a state is terminal (intake workflow complete)."""
        return str(state or "").strip().lower() in TERMINAL_STATES

    @staticmethod
    def is_active_queue(state: str) -> bool:
        """Check if a state is in Active Queue (operator decisions in progress)."""
        return str(state or "").strip().lower() in ACTIVE_QUEUE_STATES

    @staticmethod
    def is_valid_state(state: str) -> bool:
        """Check if a state is recognized."""
        return str(state or "").strip().lower() in ALL_INTAKE_STATES

    @staticmethod
    def get_allowed_actions(state: str) -> set[str]:
        """Get the set of allowed actions for a given state."""
        normalized_state = str(state or "").strip().lower()
        return ActionEligibility.ELIGIBILITY_MATRIX.get(normalized_state, set())

    @staticmethod
    def is_action_allowed(state: str, action: str) -> bool:
        """Check if a specific action is allowed in a given state."""
        allowed = ActionEligibility.get_allowed_actions(state)
        return str(action or "").strip().lower() in allowed

    @staticmethod
    def validate_action_eligibility(state: str, action: str) -> tuple[bool, str | None]:
        """
        Validate if an action is eligible for a state.
        
        Returns (is_eligible: bool, reason_code: str | None).
        If not eligible, reason_code explains why.
        """
        normalized_state = str(state or "").strip().lower()
        normalized_action = str(action or "").strip().lower()

        if not ActionEligibility.is_valid_state(normalized_state):
            return False, "invalid_state"

        if not ActionEligibility.is_action_allowed(normalized_state, normalized_action):
            # Generate a specific reason code for the rejection
            if ActionEligibility.is_terminal(normalized_state):
                return False, f"item_terminal_{normalized_state}"
            else:
                return False, f"action_not_valid_for_state_{normalized_state}"

        return True, None

    @staticmethod
    def validate_override_for_warning_state(state: str, action: str, override: bool) -> tuple[bool, str | None]:
        """
        Validate if an override is required and provided for warning state actions.
        
        Returns (is_valid: bool, reason_code: str | None).
        """
        normalized_state = str(state or "").strip().lower()
        normalized_action = str(action or "").strip().lower()

        # Group/publish actions from validated_warning require override flag
        if normalized_state == "validated_warning" and normalized_action in {
            ActionEligibility.GROUP_NEW,
            ActionEligibility.GROUP_EXISTING,
            ActionEligibility.PUBLISH_CATALOG,
        }:
            if not override:
                return False, "override_required_for_warning_state"

        return True, None

    @staticmethod
    def get_terminal_reason_code(state: str) -> str:
        """Get the terminal reason code for a terminal state."""
        normalized_state = str(state or "").strip().lower()
        if ActionEligibility.is_terminal(normalized_state):
            return f"item_terminal_{normalized_state}"
        return "invalid_state"

    @staticmethod
    def build_allowed_actions_payload(state: str) -> dict[str, Any]:
        """
        Build a payload describing allowed actions for the UI.
        
        Returns dict with:
        - is_terminal: bool
        - is_active_queue: bool
        - allowed_actions: list[str]
        - state_display_name: str
        """
        normalized_state = str(state or "").strip().lower()
        allowed = ActionEligibility.get_allowed_actions(normalized_state)

        # Friendly display names
        state_display_map = {
            "submitted": "New (Awaiting Review)",
            "validated_ready": "Ready (Validation Passed)",
            "validated_warning": "Review Required (Warnings)",
            "deferred": "Deferred",
            "grouped_new": "Complete (New Group Created)",
            "grouped_existing": "Complete (Attached to Group)",
            "published_to_catalog": "Complete (Published to Catalog)",
            "published_by_destination": "Complete (Routed By Destination)",
            "rejected": "Complete (Rejected)",
        }

        return {
            "is_terminal": ActionEligibility.is_terminal(normalized_state),
            "is_active_queue": ActionEligibility.is_active_queue(normalized_state),
            "allowed_actions": sorted(list(allowed)),
            "state_display_name": state_display_map.get(normalized_state, normalized_state),
        }
