"""AppState — lightweight per-request state container.

Extracted from main.py (issue #1192) so that router modules can import it
without creating a circular dependency back into main.py.
"""
from __future__ import annotations

from .db import bootstrap_database
from .settings import Settings


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_info = bootstrap_database(settings.db_path)
