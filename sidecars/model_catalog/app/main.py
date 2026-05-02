from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .manyfold import ManyfoldClient
from .routers import intake as intake_module
from .routers import working as working_module
from .routers.archive_links import router as archive_links_router
from .routers.intake import router as intake_router
from .routers.intake import _browser_intake_upload_storage_root
from .routers.models import router as models_router
from .routers.models import _local_entry_to_summary as _models_local_entry_to_summary
from .routers.models_detail import router as models_detail_router
from .routers.models_media import router as models_media_router
from .routers.models_search import router as models_search_router
from .routers.models import router as models_router
from .routers.source_filesystems import router as source_filesystems_router
from .routers.system import router as system_router
from .routers.working import router as working_router
from .services.shared_helpers import _sha256_file as _shared_sha256_file
from .services.shared_helpers import _resolve_local_asset_storage_path as _shared_resolve_local_asset_storage_path
from .settings import Settings, load_settings
from .state import AppState

# Backward-compatible helper exports used by tests and monkeypatches.
_sha256_file = _shared_sha256_file
_resolve_local_asset_storage_path = _shared_resolve_local_asset_storage_path
_local_entry_to_summary = _models_local_entry_to_summary


def _sha256_file_proxy(path):
    return _sha256_file(path)


intake_module._sha256_file = _sha256_file_proxy
working_module._sha256_file = _sha256_file_proxy


def create_app(*, settings: Settings | None = None, manyfold_client: ManyfoldClient | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved_settings = settings if settings is not None else load_settings()
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
            session_email=resolved_settings.manyfold_session_email,
            session_password=resolved_settings.manyfold_session_password,
        )
        try:
            yield
        finally:
            client: ManyfoldClient = app.state.manyfold_client
            client.close()

    app = FastAPI(title="Model Catalog Sidecar", version="0.1.0", lifespan=lifespan)

    # Enable CORS to allow requests from Home Assistant UI (different origin)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins; restrict in production if needed
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Feature routers (see routers/ for endpoint ownership)
    app.include_router(system_router)
    app.include_router(source_filesystems_router)
    app.include_router(archive_links_router)
    app.include_router(working_router)
    app.include_router(intake_router)
    app.include_router(models_search_router)
    app.include_router(models_detail_router)
    app.include_router(models_media_router)
    app.include_router(models_router)

    return app


app = create_app()

