from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sidecars.model_catalog.app.db import bootstrap_database, read_model_fields
from sidecars.model_catalog.app.main import create_app
from sidecars.model_catalog.app.settings import Settings


def _build_settings(tmp_path: Path) -> Settings:
    return Settings(
        manyfold_base_url="http://manyfold.test",
        manyfold_models_path="/models",
        manyfold_collections_path="/collections",
        manyfold_creators_path="/creators",
        manyfold_oauth_token_path="/oauth/token",
        manyfold_client_id="client-id",
        manyfold_client_secret="client-secret",
        manyfold_oauth_scopes="public read",
        db_path=tmp_path / "model_catalog.db",
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
        image_tag="0.1.0",
        image_version="0.1.0",
        image_revision="abc123",
        image_created="2026-04-22T00:00:00Z",
    )


def test_create_idea_persists_idea_metadata(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings, manyfold_client=None)

    with TestClient(app) as client:
        response = client.post(
            "/api/local/models",
            json={
                "local_model_id": "idea-metadata-test",
                "model_name": "Idea Metadata Test",
                "entity_type": "idea",
                "external_links": [
                    {"url": "https://example.com/original", "label": "Original"},
                    "https://example.com/reference",
                    {"url": ""},
                ],
                "notes": "  Prototype concept for US-9  ",
                "sketch_image": {"url": "https://example.com/sketch.png"},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload.get("success") is True
        assert payload.get("entity_type") == "idea"

        detail_response = client.get("/api/local/models/idea-metadata-test")
        assert detail_response.status_code == 200
        detail_payload = detail_response.json()
        idea_metadata = detail_payload.get("idea_metadata") or {}

        assert idea_metadata.get("notes") == "Prototype concept for US-9"
        assert idea_metadata.get("external_links") == [
            {"url": "https://example.com/original", "label": "Original"},
            {"url": "https://example.com/reference"},
        ]
        assert idea_metadata.get("sketch_image") == {"url": "https://example.com/sketch.png"}

        persisted_fields = read_model_fields(db_path=settings.db_path, model_ref="idea-metadata-test")
        assert persisted_fields.get("notes") == "Prototype concept for US-9"
        assert persisted_fields.get("external_links") == [
            {"url": "https://example.com/original", "label": "Original"},
            {"url": "https://example.com/reference"},
        ]


def test_idea_metadata_requires_idea_entity_type(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings, manyfold_client=None)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/local/models",
            json={
                "local_model_id": "model-with-idea-metadata",
                "model_name": "Regular Model",
                "entity_type": "model",
                "notes": "Should fail because this is model",
            },
        )

        assert create_response.status_code == 400
        assert "Idea metadata fields" in str(create_response.json().get("error") or "")

        seed_response = client.post(
            "/api/local/models",
            json={
                "local_model_id": "idea-for-transition",
                "model_name": "Idea For Transition",
                "entity_type": "idea",
                "notes": "Idea-only notes",
            },
        )
        assert seed_response.status_code == 200

        transition_response = client.patch(
            "/api/local/models/idea-for-transition",
            json={"entity_type": "model"},
        )
        assert transition_response.status_code == 200

        detail_response = client.get("/api/local/models/idea-for-transition")
        assert detail_response.status_code == 200
        detail_payload = detail_response.json()
        idea_metadata = detail_payload.get("idea_metadata") or {}
        assert idea_metadata.get("notes") is None
        assert idea_metadata.get("external_links") == []
        assert idea_metadata.get("sketch_image") is None
