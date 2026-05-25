from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sidecars.model_catalog.app.db import bootstrap_database, read_model_fields
from sidecars.model_catalog.app.main import create_app
from sidecars.model_catalog.app.settings import Settings

pytestmark = pytest.mark.skip(
    reason="Working groups deprecated (PR E). Tables dropped in PR E.1 schema migration; routes removed in PR E.2; tests deleted in PR E.3."
)


def _build_settings(tmp_path: Path) -> Settings:
    return Settings(
        catalog_base_url="http://catalog.test",
        db_path=tmp_path / "model_catalog.db",
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
        image_tag="0.1.0",
        image_version="0.1.0",
        image_revision="abc123",
        image_created="2026-04-22T00:00:00Z",
    )


def test_working_group_create_projects_catalog_projection(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/working-groups",
            json={"title": "Projection Group", "stage": "draft", "notes": "Projection notes"},
        )
        assert create_response.status_code == 200
        create_payload = create_response.json()
        assert create_payload.get("success") is True

        group = create_payload.get("group") or {}
        group_id = int(group.get("id") or 0)
        assert group_id > 0

        projection_id = f"working-group-{group_id}"
        model_response = client.get(f"/api/local/models/{projection_id}")
        assert model_response.status_code == 200
        model_payload = model_response.json()
        entry = model_payload.get("entry") or {}
        assert entry.get("entity_type") == "working_group"
        assert entry.get("model_name") == "Projection Group"

        fields = read_model_fields(db_path=settings.db_path, model_ref=projection_id)
        assert fields.get("working_group_id") == group_id
        assert fields.get("working_group_stage") == "draft"
        assert fields.get("working_group_notes") == "Projection notes"


def test_working_group_update_and_delete_sync_projection(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/working-groups",
            json={"title": "Sync Group", "stage": "draft", "notes": "Initial notes"},
        )
        assert create_response.status_code == 200
        group_id = int((create_response.json().get("group") or {}).get("id") or 0)
        assert group_id > 0

        update_response = client.patch(
            f"/api/working-groups/{group_id}",
            json={"title": "Sync Group Updated", "stage": "ready", "notes": ""},
        )
        assert update_response.status_code == 200

        projection_id = f"working-group-{group_id}"
        model_response = client.get(f"/api/local/models/{projection_id}")
        assert model_response.status_code == 200
        model_payload = model_response.json()
        entry = model_payload.get("entry") or {}
        assert entry.get("entity_type") == "working_group"
        assert entry.get("model_name") == "Sync Group Updated"

        fields = read_model_fields(db_path=settings.db_path, model_ref=projection_id)
        assert fields.get("working_group_stage") == "ready"
        assert fields.get("working_group_notes") is None

        delete_response = client.delete(f"/api/working-groups/{group_id}")
        assert delete_response.status_code == 200

        archived_projection_response = client.get(f"/api/local/models/{projection_id}")
        assert archived_projection_response.status_code == 404
