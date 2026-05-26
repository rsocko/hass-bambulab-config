from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import intake as intake_module
from .routers import intake_verification as intake_verification_module
from .routers import working as working_module
from .routers.archive_links import router as archive_links_router
from .routers.intake import router as intake_router
from .routers.intake import _browser_intake_upload_storage_root
from .routers.models import router as models_router
from .routers.models import _local_entry_to_summary as _models_local_entry_to_summary
from .routers.models_detail import router as models_detail_router
from .routers.models_media import router as models_media_router
from .routers.models_search import router as models_search_router
from .routers.slicer import router as slicer_router
from .routers.source_filesystems import router as source_filesystems_router
from .routers.system import router as system_router
from .routers.unified_queue import router as unified_queue_router
from .routers.working import router as working_router
from .services.intake_service import reject_orphaned_uploads
from .services.shared_helpers import _sha256_file as _shared_sha256_file
from .services.shared_helpers import _resolve_local_asset_storage_path as _shared_resolve_local_asset_storage_path
from .settings import Settings, load_settings
from .state import AppState

logger = logging.getLogger(__name__)

# Backward-compatible helper exports used by tests and monkeypatches.
_sha256_file = _shared_sha256_file
_resolve_local_asset_storage_path = _shared_resolve_local_asset_storage_path
_local_entry_to_summary = _models_local_entry_to_summary


def _sha256_file_proxy(path):
    return _sha256_file(path)


intake_module._sha256_file = _sha256_file_proxy
intake_verification_module._sha256_file = _sha256_file_proxy
working_module._sha256_file = _sha256_file_proxy


def create_app(*, settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved_settings = settings if settings is not None else load_settings()
        app.state.model_catalog = AppState(resolved_settings)
        app.state.catalog_client = None  # Legacy stub — no longer used

        # Reject any intake uploads left in active states from a previous
        # process — they are definitionally orphaned on startup.
        reject_orphaned_uploads(resolved_settings.db_path)

        try:
            yield
        finally:
            pass

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
    app.include_router(unified_queue_router)
    app.include_router(slicer_router)
    app.include_router(models_search_router)
    app.include_router(models_detail_router)
    app.include_router(models_media_router)
    app.include_router(models_router)

    return app


app = create_app()

