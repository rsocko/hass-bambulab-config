from .archive_links import router as archive_links_router
from .intake import router as intake_router
from .models import router as models_router
from .source_filesystems import router as source_filesystems_router
from .system import router as system_router
from .working import router as working_router

__all__ = [
    "archive_links_router",
    "intake_router",
    "models_router",
    "source_filesystems_router",
    "system_router",
    "working_router",
]
