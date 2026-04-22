from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI

from .db import bootstrap_database
from .manyfold import ManyfoldClient, read_cached_manyfold_summaries, refresh_manyfold_cache
from .settings import Settings, load_settings


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_info = bootstrap_database(settings.db_path)


def create_app(*, settings: Settings | None = None, manyfold_client: ManyfoldClient | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.model_catalog = AppState(resolved_settings)
        app.state.manyfold_client = manyfold_client or ManyfoldClient(
            resolved_settings.manyfold_base_url,
            models_path=resolved_settings.manyfold_models_path,
            oauth_token_path=resolved_settings.manyfold_oauth_token_path,
            client_id=resolved_settings.manyfold_client_id,
            client_secret=resolved_settings.manyfold_client_secret,
        )
        try:
            yield
        finally:
            client: ManyfoldClient = app.state.manyfold_client
            client.close()

    app = FastAPI(title="Model Catalog Sidecar", version="0.1.0", lifespan=lifespan)

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        state: AppState = app.state.model_catalog
        return {
            "ok": True,
            "db_path": state.db_info.path,
            "table_count": len(state.db_info.tables),
        }

    @app.get("/config")
    def config() -> dict[str, Any]:
        state: AppState = app.state.model_catalog
        return {
            "manyfold_base_url": state.settings.manyfold_base_url,
            "manyfold_models_path": state.settings.manyfold_models_path,
            "manyfold_oauth_token_path": state.settings.manyfold_oauth_token_path,
            "manyfold_oauth_enabled": bool(state.settings.manyfold_client_id and state.settings.manyfold_client_secret),
            "db_path": str(state.settings.db_path),
            "refresh_ttl_seconds": state.settings.refresh_ttl_seconds,
            "host": state.settings.host,
            "port": state.settings.port,
        }

    @app.get("/diagnostics")
    def diagnostics() -> dict[str, Any]:
        state: AppState = app.state.model_catalog
        return {
            "service": "model-catalog-sidecar",
            "db_tables": list(state.db_info.tables),
            "manyfold_base_url": state.settings.manyfold_base_url,
            "manyfold_models_path": state.settings.manyfold_models_path,
            "manyfold_oauth_enabled": bool(state.settings.manyfold_client_id and state.settings.manyfold_client_secret),
        }

    @app.get("/api/models")
    def list_models(refresh: bool = False) -> dict[str, Any]:
        state: AppState = app.state.model_catalog
        client: ManyfoldClient = app.state.manyfold_client
        if refresh:
            summaries = refresh_manyfold_cache(db_path=state.settings.db_path, client=client)
            source = "manyfold"
        else:
            summaries = read_cached_manyfold_summaries(db_path=state.settings.db_path)
            source = "cache"
            if not summaries:
                summaries = refresh_manyfold_cache(db_path=state.settings.db_path, client=client)
                source = "manyfold"
        return {
            "source": source,
            "count": len(summaries),
            "models": [asdict(summary) for summary in summaries],
        }

    return app


app = create_app()
