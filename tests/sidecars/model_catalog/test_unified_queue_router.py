from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


class FakeManyfoldClient:
    base_url = "http://manyfold.example"

    def close(self) -> None:
        return None


def _make_settings(db_path: Path) -> Settings:
    return Settings(
        manyfold_base_url="http://manyfold.example",
        manyfold_models_path="/models",
        manyfold_collections_path="/collections",
        manyfold_creators_path="/creators",
        manyfold_oauth_token_path="/oauth/token",
        manyfold_client_id="test-client",
        manyfold_client_secret="test-secret",
        manyfold_oauth_scopes=None,
        db_path=db_path,
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
        image_tag="test",
        image_version="test",
        image_revision="test",
        image_created="test",
    )


def _create_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "model_catalog.db"
    app = create_app(settings=_make_settings(db_path), manyfold_client=FakeManyfoldClient())
    client = TestClient(app)
    client.__enter__()
    return client


def test_unified_queue_entry_crud_happy_path(tmp_path: Path) -> None:
    client = _create_client(tmp_path)
    try:
        create_response = client.post(
            "/api/unified-queue/entries",
            json={
                "source_kind": "working_group",
                "source_id": "wg-001",
                "title": "Bracket Batch",
                "copies": 2,
                "duration_bucket": "2-4h",
            },
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["success"] is True
        entry_id = created["entry"]["queue_entry_id"]
        assert created["entry"]["source_id"] == "wg-001"
        assert created["entry"]["copies"] == 2
        assert created["entry"]["duration_bucket"] == "medium"

        get_response = client.get(f"/api/unified-queue/entries/{entry_id}")
        assert get_response.status_code == 200
        assert get_response.json()["entry"]["queue_entry_id"] == entry_id

        update_response = client.patch(
            f"/api/unified-queue/entries/{entry_id}",
            json={
                "state": "started",
                "copies_completed": 1,
                "rank": 1,
            },
        )
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["entry"]["state"] == "started"
        assert updated["entry"]["copies_completed"] == 1
        assert updated["entry"]["rank"] == 1

        list_response = client.get("/api/unified-queue/entries", params={"state": "started", "limit": 10, "offset": 0})
        assert list_response.status_code == 200
        listed = list_response.json()
        assert listed["success"] is True
        assert listed["pagination"]["total"] == 1
        assert listed["entries"][0]["queue_entry_id"] == entry_id

        delete_response = client.delete(f"/api/unified-queue/entries/{entry_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["deleted"] is True

        missing_after_delete = client.get(f"/api/unified-queue/entries/{entry_id}")
        assert missing_after_delete.status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_unified_queue_validation_and_error_responses(tmp_path: Path) -> None:
    client = _create_client(tmp_path)
    try:
        invalid_source_kind = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "bad", "source_id": "x", "copies": 1},
        )
        assert invalid_source_kind.status_code == 400
        assert invalid_source_kind.json()["success"] is False

        missing_source_id = client.post(
            "/api/unified-queue/entries",
            json={"source_kind": "working_file", "copies": 1},
        )
        assert missing_source_id.status_code == 400

        invalid_pagination = client.get("/api/unified-queue/entries", params={"limit": 0})
        assert invalid_pagination.status_code == 400

        not_found_patch = client.patch("/api/unified-queue/entries/missing-id", json={"state": "done"})
        assert not_found_patch.status_code == 404

        not_found_delete = client.delete("/api/unified-queue/entries/missing-id")
        assert not_found_delete.status_code == 404
    finally:
        client.__exit__(None, None, None)
