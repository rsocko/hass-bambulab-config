"""Model Catalog sidecar CLI entry point.

Usage:
  python -m sidecars.model_catalog cleanup reset-db --execute
  python -m sidecars.model_catalog cleanup reset-all --execute
  python -m sidecars.model_catalog cleanup cleanup --scope db
"""

from __future__ import annotations

import click

from .cli.cleanup import cli as cleanup_cli


@click.group()
def main() -> None:
    """Model Catalog sidecar — maintenance and operations."""
    pass


main.add_command(cleanup_cli, name="cleanup")


if __name__ == "__main__":
    main()
