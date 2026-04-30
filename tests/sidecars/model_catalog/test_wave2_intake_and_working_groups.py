from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


class FakeManyfoldClient:
    base_url = "http://manyfold.example"

    def close(self) -> None:
        return None


def _make_settings(db_path: Path, source_root: Path) -> Settings:
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
        source_filesystem_roots=(source_root.resolve(),),
    )


def _create_client(tmp_path: Path, source_root: Path) -> TestClient:
    db_path = tmp_path / "model_catalog.db"
    app = create_app(settings=_make_settings(db_path, source_root), manyfold_client=FakeManyfoldClient())
    client = TestClient(app)
    client.__enter__()
    return client


def test_working_files_reindex_and_list(tmp_path: Path) -> None:
    source_root = tmp_path / "working"
    source_root.mkdir(parents=True, exist_ok=True)
    model_file = source_root / "Football_Holder.3mf"
    model_file.write_bytes(b"3mf-bytes")

    client = _create_client(tmp_path, source_root)
    try:
        reindex_response = client.post(
            "/api/working-files/reindex",
            json={"compute_hashes": True, "recurse": True},
        )
        assert reindex_response.status_code == 200
        reindex_payload = reindex_response.json()
        assert reindex_payload["success"] is True
        assert reindex_payload["discovered"] == 1
        assert reindex_payload["inserted"] == 1

        list_response = client.get("/api/working-files", params={"q": "football"})
    finally:
        client.__exit__(None, None, None)

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["success"] is True
    assert list_payload["pagination"]["total"] == 1
    assert list_payload["files"][0]["file_name_raw"] == "Football_Holder.3mf"
    assert list_payload["files"][0]["sha256_hash"]


def test_working_group_crud_items_and_links(tmp_path: Path) -> None:
    source_root = tmp_path / "working"
    source_root.mkdir(parents=True, exist_ok=True)
    model_file = source_root / "Bracket_v2.stl"
    model_file.write_bytes(b"stl-bytes")

    client = _create_client(tmp_path, source_root)
    try:
        create_group = client.post(
            "/api/working-groups",
            json={"title": "Bracket Group", "stage": "draft"},
        )
        assert create_group.status_code == 200
        group_payload = create_group.json()
        group_id = group_payload["group"]["id"]

        add_item = client.post(
            f"/api/working-groups/{group_id}/items",
            json={"file_path": str(model_file), "item_role": "primary"},
        )
        assert add_item.status_code == 200

        add_link = client.post(
            f"/api/working-groups/{group_id}/links",
            json={"model_ref": "test-model-ref", "link_role": "related", "metadata": {"source": "test"}},
        )
        assert add_link.status_code == 200

        reverse_lookup = client.get("/api/models/test-model-ref/working-groups")
    finally:
        client.__exit__(None, None, None)

    assert reverse_lookup.status_code == 200
    reverse_payload = reverse_lookup.json()
    assert reverse_payload["success"] is True
    assert reverse_payload["group_count"] == 1
    assert reverse_payload["groups"][0]["id"] == group_id
    assert len(reverse_payload["groups"][0]["items"]) == 1
    assert len(reverse_payload["groups"][0]["links"]) == 1


def test_intake_submit_validate_and_group(tmp_path: Path) -> None:
    source_root = tmp_path / "inbox"
    source_root.mkdir(parents=True, exist_ok=True)
    source_file = source_root / "router_mount.step"
    source_file.write_bytes(b"step-bytes")

    client = _create_client(tmp_path, source_root)
    try:
        submit_response = client.post(
            "/api/intake/submit",
            json={
                "items": [{"source_path": str(source_file), "source_type": "filesystem_action"}],
                "auto_validate": True,
                "cleanup_policy": "keep",
            },
        )
        assert submit_response.status_code == 200
        submit_payload = submit_response.json()
        assert submit_payload["success"] is True
        assert submit_payload["created_count"] == 1

        item = submit_payload["items"][0]
        item_id = item["item_id"]
        assert item["state"] in {"validated_ready", "validated_warning"}
        assert item["validation"]["validation_state"] in {"ready", "duplicate_candidate"}

        validate_response = client.post(f"/api/intake/items/{item_id}/validate")
        assert validate_response.status_code == 200

        group_response = client.post(
            f"/api/intake/items/{item_id}/group",
            json={"action": "create_working_group", "title": "Router Mount Group"},
        )
        assert group_response.status_code == 200
        group_payload = group_response.json()
        assert group_payload["success"] is True
        assert group_payload["state"] == "grouped_new"
        assert group_payload["working_group_id"] > 0
        assert group_payload["added_items"] >= 1

        detail_response = client.get(f"/api/intake/items/{item_id}")
    finally:
        client.__exit__(None, None, None)

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["success"] is True
    assert detail_payload["item"]["state"] == "grouped_new"

    decoded_note = detail_payload["item"]["decision_note"]
    assert isinstance(decoded_note, str)
    assert "working_group_id" in decoded_note
