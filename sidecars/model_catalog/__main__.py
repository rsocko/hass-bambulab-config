"""Model Catalog sidecar CLI entry point.

Usage:
  python -m sidecars.model_catalog cleanup reset-db --execute
  python -m sidecars.model_catalog cleanup reset-all --execute
  python -m sidecars.model_catalog cleanup cleanup --scope db

Note:
  The repository contains this CLI entry point, but the currently deployed Docker image
  only copies /app/app and may not include the sidecars.model_catalog package until the
  image packaging is updated and rebuilt.
"""

from __future__ import annotations

import click

from .cli.cleanup import cli as cleanup_cli
from .cli.db_profiles import cli as db_profiles_cli


@click.group()
def main() -> None:
    """Model Catalog sidecar — maintenance and operations."""
    pass


main.add_command(cleanup_cli, name="cleanup")
main.add_command(db_profiles_cli, name="db-profiles")


if __name__ == "__main__":
    main()
