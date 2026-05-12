"""AppState — lightweight per-request state container.

Extracted from main.py (issue #1192) so that router modules can import it
without creating a circular dependency back into main.py.
"""
from __future__ import annotations

from .db_profiles import bootstrap_profile_databases, seed_test_database_from_prod
from .settings import Settings


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_seed_result: dict[str, object] | None = None
        if settings.seed_test_db_from_prod_on_start:
            self.db_seed_result = seed_test_database_from_prod(
                settings=settings,
                force=settings.seed_test_db_overwrite,
            )

        self.db_info_by_profile = bootstrap_profile_databases(settings=settings)
        self.db_info = self.db_info_by_profile[settings.db_profile]
