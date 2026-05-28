from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sidecars.model_catalog.app.db import bootstrap_database, read_model_field
from sidecars.model_catalog.app.main import create_app
from sidecars.model_catalog.app.routers import models as models_router
from sidecars.model_catalog.app.settings import Settings


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
        image_created="2026-05-27T00:00:00Z",
    )


def test_project_lifecycle_crud_supports_true_project_fields(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "title": "Desk Accessories",
                "description": "Operator lifecycle test",
                "status": "planning",
                "project_type": "model_family",
                "origin": "custom",
                "created_by": "tester",
            },
        )
        assert create_response.status_code == 200
        project = create_response.json()["project"]
        assert project["status"] == "planning"
        assert project["project_type"] == "model_family"
        assert project["origin"] == "custom"
        assert project["created_by"] == "tester"

        project_id = int(project["id"])

        complete_response = client.patch(f"/api/projects/{project_id}", json={"status": "completed"})
        assert complete_response.status_code == 200
        completed = complete_response.json()["project"]
        assert completed["status"] == "completed"
        assert completed["completed_at"]

        archive_response = client.patch(f"/api/projects/{project_id}", json={"status": "archived"})
        assert archive_response.status_code == 200
        archived = archive_response.json()["project"]
        assert archived["status"] == "archived"
        assert archived["archived_at"]

        default_list = client.get("/api/projects")
        assert default_list.status_code == 200
        assert default_list.json()["projects"] == []

        archived_list = client.get("/api/projects", params={"show_archived": True})
        assert archived_list.status_code == 200
        assert archived_list.json()["projects"][0]["id"] == project_id


def test_model_can_belong_to_many_projects_with_membership_states(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        project_one = client.post("/api/projects", json={"title": "Prototype A"}).json()["project"]
        project_two = client.post("/api/projects", json={"title": "Prototype B"}).json()["project"]

        create_model = client.post(
            "/api/local/models",
            json={
                "local_model_id": "multi-project-model",
                "model_name": "Multi Project Model",
            },
        )
        assert create_model.status_code == 200

        replace_response = client.put(
            "/api/models/multi-project-model/projects",
            json={
                "project_memberships": [
                    {"project_id": project_one["id"], "member_state": "chosen"},
                    {"project_id": project_two["id"], "member_state": "candidate"},
                ]
            },
        )
        assert replace_response.status_code == 200
        membership_payload = replace_response.json()
        assert set(membership_payload["project_ids"]) == {project_one["id"], project_two["id"]}
        assert read_model_field(db_path=settings.db_path, model_ref="multi-project-model", field_key="project_id") is None

        get_response = client.get("/api/models/multi-project-model/projects")
        assert get_response.status_code == 200
        items = get_response.json()["items"]
        assert len(items) == 2
        assert {
            int(item["project_id"]): item["member_state"]
            for item in items
        } == {
            int(project_one["id"]): "chosen",
            int(project_two["id"]): "candidate",
        }

        first_detail = client.get(f"/api/projects/{project_one['id']}")
        assert first_detail.status_code == 200
        assert first_detail.json()["project"]["curated_model_count"] == 1

        delete_conflict = client.delete(f"/api/projects/{project_one['id']}")
        assert delete_conflict.status_code == 409

        single_replace = client.put(
            "/api/models/multi-project-model/projects",
            json={"project_ids": [project_one["id"]]},
        )
        assert single_replace.status_code == 200
        assert read_model_field(db_path=settings.db_path, model_ref="multi-project-model", field_key="project_id") == int(project_one["id"])


def test_model_search_and_detail_include_project_membership_contract(tmp_path: Path, monkeypatch) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    monkeypatch.setattr(
        models_router,
        "refresh_model_cache_with_status",
        lambda db_path, client: ([], {"outcome": "test", "preserved_cache": False}),
        raising=False,
    )

    with TestClient(app) as client:
        project_one = client.post("/api/projects", json={"title": "Project Contract A"}).json()["project"]
        project_two = client.post("/api/projects", json={"title": "Project Contract B"}).json()["project"]

        create_model = client.post(
            "/api/local/models",
            json={
                "local_model_id": "project-contract-model",
                "model_name": "Project Contract Model",
            },
        )
        assert create_model.status_code == 200

        replace_response = client.put(
            "/api/models/project-contract-model/projects",
            json={
                "project_memberships": [
                    {"project_id": project_one["id"], "member_state": "chosen"},
                    {"project_id": project_two["id"], "member_state": "candidate"},
                ]
            },
        )
        assert replace_response.status_code == 200

        search_response = client.get(
            "/api/models/search",
            params={"project_id": project_one["id"], "page": 1, "per_page": 10},
        )
        assert search_response.status_code == 200
        search_results = search_response.json()["results"]
        assert len(search_results) == 1

        search_model = search_results[0]
        assert set(search_model["project_ids"]) == {project_one["id"], project_two["id"]}
        assert search_model["project_count"] == 2
        assert search_model["project_id"] is None
        assert {
            int(item["project_id"]): item["member_state"]
            for item in search_model["project_memberships"]
        } == {
            int(project_one["id"]): "chosen",
            int(project_two["id"]): "candidate",
        }

        projects_response = client.get("/api/projects")
        assert projects_response.status_code == 200
        projects_payload = projects_response.json()
        assert projects_payload["visibility"]["show_archived"] is False
        assert {int(project["id"]) for project in projects_payload["projects"]} == {
            int(project_one["id"]),
            int(project_two["id"]),
        }