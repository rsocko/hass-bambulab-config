from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI

from .db import ArchiveModelLink, bootstrap_database, read_archive_links
from .manyfold import ManyfoldClient, read_cached_manyfold_summaries, refresh_manyfold_cache
from .settings import Settings, load_settings


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_info = bootstrap_database(settings.db_path)


def _image_metadata(settings: Settings) -> dict[str, str]:
    return {
        "image_tag": settings.image_tag,
        "image_version": settings.image_version,
        "image_revision": settings.image_revision,
        "image_created": settings.image_created,
    }


def _archive_link_to_response(link: ArchiveModelLink) -> dict[str, Any]:
    return {
        "id": link.id,
        "archive_id": link.bambuddy_archive_id,
        "manyfold_model_url": link.manyfold_model_url,
        "manyfold_model_public_id": link.manyfold_model_public_id,
        "manyfold_model_file_id": link.manyfold_model_file_id,
        "relationship_type": link.relationship_type,
        "link_role": link.link_role,
        "match_method": link.match_method,
        "match_confidence": link.match_confidence,
        "review_state": link.review_state,
        "is_active": link.is_active,
        "created_at": link.created_at,
        "updated_at": link.updated_at,
    }


def create_app(*, settings: Settings | None = None, manyfold_client: ManyfoldClient | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.model_catalog = AppState(resolved_settings)
        app.state.manyfold_client = manyfold_client or ManyfoldClient(
            resolved_settings.manyfold_base_url,
            models_path=resolved_settings.manyfold_models_path,
            collections_path=resolved_settings.manyfold_collections_path,
            creators_path=resolved_settings.manyfold_creators_path,
            oauth_token_path=resolved_settings.manyfold_oauth_token_path,
            client_id=resolved_settings.manyfold_client_id,
            client_secret=resolved_settings.manyfold_client_secret,
            oauth_scopes=resolved_settings.manyfold_oauth_scopes,
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
            "schema_version": state.db_info.schema_version,
        }

    @app.get("/config")
    def config() -> dict[str, Any]:
        state: AppState = app.state.model_catalog
        return {
            "manyfold_base_url": state.settings.manyfold_base_url,
            "manyfold_models_path": state.settings.manyfold_models_path,
            "manyfold_collections_path": state.settings.manyfold_collections_path,
            "manyfold_creators_path": state.settings.manyfold_creators_path,
            "manyfold_oauth_token_path": state.settings.manyfold_oauth_token_path,
            "manyfold_oauth_enabled": bool(state.settings.manyfold_client_id and state.settings.manyfold_client_secret),
            "manyfold_oauth_scopes": state.settings.manyfold_oauth_scopes,
            "db_path": str(state.settings.db_path),
            "refresh_ttl_seconds": state.settings.refresh_ttl_seconds,
            "host": state.settings.host,
            "port": state.settings.port,
            **_image_metadata(state.settings),
        }

    @app.get("/diagnostics")
    def diagnostics() -> dict[str, Any]:
        state: AppState = app.state.model_catalog
        return {
            "service": "model-catalog-sidecar",
            "db_tables": list(state.db_info.tables),
            "schema_version": state.db_info.schema_version,
            "manyfold_base_url": state.settings.manyfold_base_url,
            "manyfold_models_path": state.settings.manyfold_models_path,
            "manyfold_collections_path": state.settings.manyfold_collections_path,
            "manyfold_creators_path": state.settings.manyfold_creators_path,
            "manyfold_oauth_enabled": bool(state.settings.manyfold_client_id and state.settings.manyfold_client_secret),
            **_image_metadata(state.settings),
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

    @app.get("/api/archive-links/{archive_id}")
    def get_archive_links(archive_id: int, include_inactive: bool = False) -> dict[str, Any]:
        state: AppState = app.state.model_catalog
        links = read_archive_links(
            db_path=state.settings.db_path,
            archive_id=archive_id,
            active_only=not include_inactive,
        )
        active_link = next((link for link in links if link.is_active), None)
        return {
            "success": True,
            "contract": "archive-link.v1alpha1",
            "archive_id": archive_id,
            "link": _archive_link_to_response(active_link) if active_link else None,
            "links": [_archive_link_to_response(link) for link in links],
            "meta": {
                "count": len(links),
                "include_inactive": include_inactive,
            },
        }

    return app


app = create_app()
