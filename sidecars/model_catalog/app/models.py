from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CatalogModelSummary:
    """Catalog model summary used by search/list payloads."""
    model_url: str
    public_id: str | None
    model_id: str | None
    name: str
    preview_url: str | None
    creator_name: str | None
    collection_names: tuple[str, ...]
    keyword_names: tuple[str, ...]
    entity_type: str = "model"
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class LocalModelEntry:
    """Local catalog model record (Phase 1+)."""
    id: int
    local_model_id: str
    model_name: str
    model_description: str | None
    creator_name: str | None
    created_by: str | None
    collection_names: tuple[str, ...]
    keyword_names: tuple[str, ...]
    tags: tuple[str, ...]
    license_type: str | None
    preview_image_url: str | None
    source_origin: str | None
    source_origin_url: str | None
    revision_hash: str | None
    entity_type: str  # 'model', 'idea', or 'working_group'
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ModelAsset:
    """File/image asset attached to a local model."""
    id: int
    asset_id: str
    sort_order: int
    asset_filename: str
    asset_type: str  # "image", "3mf", "stl", "obj", "pdf", etc.
    asset_role: str  # "primary", "supporting", "preview", "documentation"
    file_size_bytes: int | None
    file_hash: str | None
    storage_path: str
    preview_url: str | None
    geometry_bounds: dict[str, Any] | None
    created_at: str
    updated_at: str
