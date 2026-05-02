from .archive_links import router as archive_links_router
from .intake import router as intake_router
from .models_detail import router as models_detail_router
from .models_media import router as models_media_router
from .models_search import router as models_search_router
from .models import router as models_router
from .source_filesystems import router as source_filesystems_router
from .system import router as system_router
from .working import router as working_router

__all__ = [
    "archive_links_router",
    "intake_router",
    "models_detail_router",
    "models_media_router",
    "models_search_router",
    "models_router",
    "source_filesystems_router",
    "system_router",
    "working_router",
]
