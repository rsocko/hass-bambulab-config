from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    manyfold_base_url: str
    manyfold_models_path: str
    manyfold_oauth_token_path: str
    manyfold_client_id: str | None
    manyfold_client_secret: str | None
    manyfold_oauth_scopes: str | None
    db_path: Path
    refresh_ttl_seconds: int
    host: str
    port: int


def load_settings() -> Settings:
    base_url = os.getenv("MANYFOLD_BASE_URL", "http://manyfold.socko.us")
    models_path = os.getenv("MANYFOLD_MODELS_PATH", "/models")
    token_path = os.getenv("MANYFOLD_OAUTH_TOKEN_PATH", "/oauth/token")
    client_id = str(os.getenv("MANYFOLD_CLIENT_ID", "")).strip() or None
    client_secret = str(os.getenv("MANYFOLD_CLIENT_SECRET", "")).strip() or None
    oauth_scopes = str(os.getenv("MANYFOLD_OAUTH_SCOPES", "")).strip() or None
    db_path = Path(os.getenv("MODEL_CATALOG_DB_PATH", ":memory:"))
    refresh_ttl_seconds = int(os.getenv("MODEL_CATALOG_REFRESH_TTL_SECONDS", "900"))
    host = os.getenv("MODEL_CATALOG_HOST", "127.0.0.1")
    port = int(os.getenv("MODEL_CATALOG_PORT", "8314"))
    return Settings(
        manyfold_base_url=base_url.rstrip("/"),
        manyfold_models_path=models_path if models_path.startswith("/") else f"/{models_path}",
        manyfold_oauth_token_path=token_path if token_path.startswith("/") else f"/{token_path}",
        manyfold_client_id=client_id,
        manyfold_client_secret=client_secret,
        manyfold_oauth_scopes=oauth_scopes,
        db_path=db_path,
        refresh_ttl_seconds=refresh_ttl_seconds,
        host=host,
        port=port,
    )
