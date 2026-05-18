"""Catalog model cache utilities.

Provides URL canonicalization, cached model lookups, and summary reading
from the local model_summary_cache table.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .db_common import connect
from .models import CatalogModelSummary

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CachedCatalogModel:
    summary: CatalogModelSummary
    raw_payload: dict[str, Any]


# Backward-compat alias during transition.

def _extract_model_id(payload: dict[str, Any]) -> str | None:
    explicit_id = str(payload.get("id") or "").strip()
    if explicit_id:
        return explicit_id

    ref = str(payload.get("@id") or payload.get("url") or "").strip()
    if not ref:
        return None

    path = urlsplit(ref).path or ref
    parts = [segment for segment in path.split("/") if segment]
    if len(parts) >= 2 and parts[-2] == "models":
        return parts[-1]
    return None


def _model_ref_from_payload(payload: dict[str, Any]) -> str | None:
    public_id = str(payload.get("public_id") or "").strip()
    if public_id:
        return public_id

    model_id = _extract_model_id(payload)
    if model_id:
        return model_id

    ref = str(payload.get("@id") or payload.get("url") or "").strip()
    return ref or None


def canonicalize_model_url(base_url: str, model_url: str, *, fallback_model_id: Any | None = None) -> str:
    """Normalize a model URL to a canonical form.

    For local:// URLs this is a pass-through. For relative or HTTP URLs,
    resolves against base_url to produce a canonical absolute URL.
    """
    normalized = str(model_url or "").strip()
    if not normalized and fallback_model_id is not None:
        return f"{base_url.rstrip('/')}/models/{fallback_model_id}"
    if normalized.startswith("/"):
        return f"{base_url.rstrip('/')}{normalized}"
    if normalized.startswith("http://") or normalized.startswith("https://"):
        parsed = urlsplit(normalized)
        if parsed.path.startswith("/models/"):
            canonical = f"{base_url.rstrip('/')}{parsed.path}"
            if parsed.query:
                canonical += f"?{parsed.query}"
            return canonical
    return normalized


def read_cached_model_summaries(*, db_path) -> list[CatalogModelSummary]:
    """Read all cached model summaries from the model_summary_cache table."""
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT model_url, model_public_id, model_id,
                   model_name, preview_url, creator_name,
                   collection_names_json, keyword_names_json
            FROM model_summary_cache
            ORDER BY model_name COLLATE NOCASE
            """
        ).fetchall()
    finally:
        connection.close()
    summaries: list[CatalogModelSummary] = []
    for row in rows:
        summaries.append(
            CatalogModelSummary(
                model_url=str(row["model_url"]),
                public_id=str(row["model_public_id"] or "").strip() or None,
                model_id=str(row["model_id"] or "").strip() or None,
                name=str(row["model_name"]),
                preview_url=str(row["preview_url"] or "").strip() or None,
                creator_name=str(row["creator_name"] or "").strip() or None,
                collection_names=tuple(json.loads(str(row["collection_names_json"] or "[]"))),
                keyword_names=tuple(json.loads(str(row["keyword_names_json"] or "[]"))),
            )
        )
    return summaries


def read_cached_catalog_models(*, db_path) -> list[CachedCatalogModel]:
    """Read all cached models including raw payload from model_summary_cache."""
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT model_url, model_public_id, model_id,
                   model_name, preview_url, creator_name,
                   collection_names_json, keyword_names_json, raw_json
            FROM model_summary_cache
            ORDER BY model_name COLLATE NOCASE
            """
        ).fetchall()
    finally:
        connection.close()

    cached_models: list[CachedCatalogModel] = []
    for row in rows:
        raw_json = str(row["raw_json"] or "{}").strip() or "{}"
        try:
            raw_payload = json.loads(raw_json)
        except json.JSONDecodeError:
            raw_payload = {}
        if not isinstance(raw_payload, dict):
            raw_payload = {}
        cached_models.append(
            CachedCatalogModel(
                summary=CatalogModelSummary(
                    model_url=str(row["model_url"]),
                    public_id=str(row["model_public_id"] or "").strip() or None,
                    model_id=str(row["model_id"] or "").strip() or None,
                    name=str(row["model_name"]),
                    preview_url=str(row["preview_url"] or "").strip() or None,
                    creator_name=str(row["creator_name"] or "").strip() or None,
                    collection_names=tuple(json.loads(str(row["collection_names_json"] or "[]"))),
                    keyword_names=tuple(json.loads(str(row["keyword_names_json"] or "[]"))),
                ),
                raw_payload=raw_payload,
            )
        )
    return cached_models
