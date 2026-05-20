from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from sidecars.model_catalog.app.models import CatalogModelSummary
from sidecars.model_catalog.app.services.model_detail_service import build_model_detail_response


def _state_with_db_path(db_path: Path) -> SimpleNamespace:
    return SimpleNamespace(settings=SimpleNamespace(db_path=db_path))


def test_build_model_detail_response_not_found(monkeypatch) -> None:
    from sidecars.model_catalog.app.routers import models as models_router

    monkeypatch.setattr(models_router, "_summary_map", lambda _db_path: {})
    monkeypatch.setattr(models_router, "_resolve_model_summary", lambda _map, _model_ref: None)

    payload = build_model_detail_response(
        _state_with_db_path(Path("test.db")),
        Mock(),
        "missing-model",
        include_debug=False,
        helpers=models_router.__dict__,
    )

    assert payload["success"] is False
    assert payload["error"] == "model_not_found"
    assert payload["model_ref"] == "missing-model"


def test_build_model_detail_response_local_success(monkeypatch) -> None:
    from sidecars.model_catalog.app.routers import models as models_router

    summary = CatalogModelSummary(
        model_url="local://local-model-1",
        public_id="local-model-1",
        model_id="1",
        name="Local Model",
        preview_url=None,
        creator_name="Local Creator",
        collection_names=["Inbox"],
        keyword_names=["keyword-1"],
    )
    entry = SimpleNamespace(
        model_name="Local Model",
        model_description="Local description",
        creator_name="Local Creator",
        created_by="operator",
        collection_names=["Inbox"],
        tags=["local", "queued"],
        license_type="CC-BY",
        source_origin="intake_queue",
        source_origin_url="intake://uploads/u1",
        revision_hash=None,
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
        entity_type="model",
    )

    monkeypatch.setattr(models_router, "_summary_map", lambda _db_path: {summary.model_url: summary})
    monkeypatch.setattr(models_router, "_resolve_model_summary", lambda _map, _model_ref: summary)
    monkeypatch.setattr(models_router, "_is_local_summary", lambda _summary: True)
    monkeypatch.setattr(models_router, "read_local_model", lambda **_kwargs: entry)
    monkeypatch.setattr(
        models_router,
        "read_model_fields",
        lambda **_kwargs: {
            "difficulty_level": "beginner",
            "preview_photo_id": "photo-1",
            "uploaded_photos": ["photo-1"],
            "custom_key": "custom-value",
        },
    )
    monkeypatch.setattr(models_router, "read_model_ranking", lambda **_kwargs: None)
    monkeypatch.setattr(models_router, "list_model_assets", lambda **_kwargs: [])
    monkeypatch.setattr(models_router, "_select_local_preview_asset_id", lambda **_kwargs: None)
    monkeypatch.setattr(models_router, "_serialize_local_model_assets", lambda **_kwargs: [{"id": "asset-1"}])
    monkeypatch.setattr(models_router, "_local_summary_preview_url", lambda **_kwargs: "/preview.png")
    monkeypatch.setattr(models_router, "_local_entry_to_summary", lambda *_args, **_kwargs: summary)
    monkeypatch.setattr(models_router, "_structured_detail_metadata", lambda _fields: {"provenance": {}})
    monkeypatch.setattr(models_router, "_read_uploaded_photo_rows", lambda **_kwargs: [])
    monkeypatch.setattr(
        models_router,
        "_serialize_uploaded_photo_rows",
        lambda **_kwargs: [{"id": "photo-1", "is_preview": False}],
    )

    payload = build_model_detail_response(
        _state_with_db_path(Path("test.db")),
        Mock(),
        "local-model-1",
        include_debug=True,
        helpers=models_router.__dict__,
    )

    assert payload["success"] is True
    assert payload["authority"] == "local"
    assert payload["model"]["name"] == "Local Model"
    assert payload["model"]["files"][0]["id"] == "asset-1"
    assert payload["enrichment"]["difficulty_level"] == "beginner"
    assert payload["enrichment"]["custom_fields"]["custom_key"] == "custom-value"
    assert "preview_photo_id" not in payload["enrichment"]["custom_fields"]
    assert "uploaded_photos" not in payload["enrichment"]["custom_fields"]
    assert payload["preview_photo_id"] == "photo-1"
    assert payload["_debug"]["authority"] == "local"


def test_build_model_detail_response_catalog_degraded(monkeypatch) -> None:
    from sidecars.model_catalog.app.routers import models as models_router

    summary = CatalogModelSummary(
        model_url="https://catalog.test/models/123",
        public_id="remote-model",
        model_id="123",
        name="Remote Summary",
        preview_url="https://catalog.test/models/123/preview.png",
        creator_name="Remote Creator",
        collection_names=["Collection A"],
        keyword_names=["remote"],
    )

    monkeypatch.setattr(models_router, "_summary_map", lambda _db_path: {summary.model_url: summary})
    monkeypatch.setattr(models_router, "_resolve_model_summary", lambda _map, _model_ref: summary)
    monkeypatch.setattr(models_router, "_is_local_summary", lambda _summary: False)
    monkeypatch.setattr(models_router, "read_model_fields", Mock(side_effect=RuntimeError("fields unavailable")))
    monkeypatch.setattr(models_router, "read_archive_links", lambda **_kwargs: [])
    monkeypatch.setattr(models_router, "read_model_ranking", lambda **_kwargs: None)
    monkeypatch.setattr(models_router, "_structured_detail_metadata", lambda _fields: {})
    monkeypatch.setattr(models_router, "_archive_link_to_response", lambda _link: {})
    monkeypatch.setattr(models_router, "_map_catalog_model_files", lambda _files: [])
    monkeypatch.setattr(models_router, "_normalize_photo_urls", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(models_router, "_read_uploaded_photo_rows", lambda **_kwargs: [])
    monkeypatch.setattr(models_router, "_serialize_uploaded_photo_rows", lambda **_kwargs: [])
    monkeypatch.setattr(models_router, "_derive_photos_from_model_files", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        models_router,
        "_derive_photo_from_preview_url",
        lambda *_args, **_kwargs: [{"id": "preview:1", "is_preview": True}],
    )

    client = Mock()
    client.base_url = "https://catalog.test"
    client.get_model_detail.return_value = {
        "name": "Remote Model",
        "description": "Model from catalog",
        "keywords": ["remote", "catalog"],
    }
    client.list_model_files.side_effect = RuntimeError("files unavailable")
    client.list_model_photos.side_effect = RuntimeError("photos unavailable")

    payload = build_model_detail_response(
        _state_with_db_path(Path("test.db")),
        client,
        "remote-model",
        include_debug=True,
        helpers=models_router.__dict__,
    )

    assert payload["success"] is True
    assert payload["authority"] == "catalog"
    assert payload["degraded"] is True
    assert payload["model"]["name"] == "Remote Model"
    assert payload["model"]["tags"] == ["remote", "catalog"]
    assert payload["photos"][0]["id"] == "preview:1"
    assert "catalog_model_files_unavailable" in payload["_debug"]["degraded_reasons"]


def test_model_detail_helpers_include_idea_metadata_dependency() -> None:
    from sidecars.model_catalog.app.routers import models as models_router

    helpers = models_router._model_detail_service_helpers()
    assert "_read_idea_metadata" in helpers
    assert "read_archive_links_for_model" in helpers
