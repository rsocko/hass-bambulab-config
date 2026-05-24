"""AppState — lightweight per-request state container.

Extracted from main.py (issue #1192) so that router modules can import it
without creating a circular dependency back into main.py.
"""
from __future__ import annotations

import time

from .db_profiles import bootstrap_profile_databases, seed_test_database_from_prod
from .settings import Settings


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.local_action_tokens: dict[str, dict[str, object]] = {}
        self.local_action_token_ttl_seconds = 300
        self.local_action_tokens_last_pruned_at = time.time()
        self.working_file_slicer_tokens: dict[str, dict[str, object]] = {}
        self.working_file_slicer_token_ttl_seconds = 300
        self.working_file_slicer_tokens_last_pruned_at = time.time()
        self.db_seed_result: dict[str, object] | None = None
        if settings.seed_test_db_from_prod_on_start:
            self.db_seed_result = seed_test_database_from_prod(
                settings=settings,
                force=settings.seed_test_db_overwrite,
            )

        self.db_info_by_profile = bootstrap_profile_databases(settings=settings)
        self.db_info = self.db_info_by_profile[settings.db_profile]
