from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    manyfold_base_url: str
    db_path: Path
    refresh_ttl_seconds: int
    host: str
    port: int


def load_settings() -> Settings:
    base_url = os.getenv("MANYFOLD_BASE_URL", "http://manyfold.socko.us")
    db_path = Path(os.getenv("MODEL_CATALOG_DB_PATH", ":memory:"))
    refresh_ttl_seconds = int(os.getenv("MODEL_CATALOG_REFRESH_TTL_SECONDS", "900"))
    host = os.getenv("MODEL_CATALOG_HOST", "127.0.0.1")
    port = int(os.getenv("MODEL_CATALOG_PORT", "8314"))
    return Settings(
        manyfold_base_url=base_url.rstrip("/"),
        db_path=db_path,
        refresh_ttl_seconds=refresh_ttl_seconds,
        host=host,
        port=port,
    )
