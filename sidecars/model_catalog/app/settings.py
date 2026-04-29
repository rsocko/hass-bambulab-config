from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    manyfold_base_url: str
    manyfold_models_path: str
    manyfold_collections_path: str
    manyfold_creators_path: str
    manyfold_oauth_token_path: str
    manyfold_client_id: str | None
    manyfold_client_secret: str | None
    manyfold_oauth_scopes: str | None
    db_path: Path
    refresh_ttl_seconds: int
    host: str
    port: int
    image_tag: str
    image_version: str
    image_revision: str
    image_created: str
    manyfold_session_email: str | None = None
    manyfold_session_password: str | None = None
    source_filesystem_roots: tuple[Path, ...] = ()
    authority_mode: str = "hybrid"


def load_settings() -> Settings:
    base_url = os.getenv("MANYFOLD_BASE_URL", "http://manyfold.socko.us")
    models_path = os.getenv("MANYFOLD_MODELS_PATH", "/models")
    collections_path = os.getenv("MANYFOLD_COLLECTIONS_PATH", "/collections")
    creators_path = os.getenv("MANYFOLD_CREATORS_PATH", "/creators")
    token_path = os.getenv("MANYFOLD_OAUTH_TOKEN_PATH", "/oauth/token")
    client_id = str(os.getenv("MANYFOLD_CLIENT_ID", "")).strip() or None
    client_secret = str(os.getenv("MANYFOLD_CLIENT_SECRET", "")).strip() or None
    oauth_scopes = str(os.getenv("MANYFOLD_OAUTH_SCOPES", "")).strip() or None
    session_email = str(os.getenv("MANYFOLD_SESSION_EMAIL", "")).strip() or None
    session_password = str(os.getenv("MANYFOLD_SESSION_PASSWORD", "")).strip() or None
    db_path = Path(os.getenv("MODEL_CATALOG_DB_PATH", ":memory:"))
    refresh_ttl_seconds = int(os.getenv("MODEL_CATALOG_REFRESH_TTL_SECONDS", "900"))
    host = os.getenv("MODEL_CATALOG_HOST", "127.0.0.1")
    port = int(os.getenv("MODEL_CATALOG_PORT", "8314"))
    image_tag = os.getenv("MODEL_CATALOG_IMAGE_TAG", "unknown")
    image_version = os.getenv("MODEL_CATALOG_IMAGE_VERSION", "unknown")
    image_revision = os.getenv("MODEL_CATALOG_IMAGE_REVISION", "unknown")
    image_created = os.getenv("MODEL_CATALOG_IMAGE_CREATED", "unknown")
    authority_mode = str(os.getenv("MODEL_CATALOG_AUTHORITY_MODE", "")).strip().lower()
    standalone_mode = str(os.getenv("MODEL_CATALOG_STANDALONE_MODE", "")).strip().lower() in {"1", "true", "yes", "on"}
    if not authority_mode:
        authority_mode = "local" if standalone_mode else "hybrid"
    source_filesystem_roots_raw = os.getenv("SOURCE_FILESYSTEM_ROOTS", "")
    source_filesystem_roots: tuple[Path, ...] = tuple(
        Path(p.strip()).expanduser().resolve()
        for p in source_filesystem_roots_raw.split(",")
        if p.strip()
    )
    return Settings(
        manyfold_base_url=base_url.rstrip("/"),
        manyfold_models_path=models_path if models_path.startswith("/") else f"/{models_path}",
        manyfold_collections_path=collections_path if collections_path.startswith("/") else f"/{collections_path}",
        manyfold_creators_path=creators_path if creators_path.startswith("/") else f"/{creators_path}",
        manyfold_oauth_token_path=token_path if token_path.startswith("/") else f"/{token_path}",
        manyfold_client_id=client_id,
        manyfold_client_secret=client_secret,
        manyfold_oauth_scopes=oauth_scopes,
        db_path=db_path,
        refresh_ttl_seconds=refresh_ttl_seconds,
        host=host,
        port=port,
        image_tag=image_tag,
        image_version=image_version,
        image_revision=image_revision,
        image_created=image_created,
        manyfold_session_email=session_email,
        manyfold_session_password=session_password,
        source_filesystem_roots=source_filesystem_roots,
        authority_mode=authority_mode,
    )
