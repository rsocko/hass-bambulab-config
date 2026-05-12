"""Model Catalog CLI commands."""

from .cleanup import cli as cleanup_cli
from .db_profiles import cli as db_profiles_cli

__all__ = ["cleanup_cli", "db_profiles_cli"]
