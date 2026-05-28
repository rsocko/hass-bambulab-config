from __future__ import annotations

import sqlite3
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

        state_filtered_response = client.get(
            "/api/models/search",
            params={
                "project_id": project_one["id"],
                "project_member_state": "chosen",
                "page": 1,
                "per_page": 10,
            },
        )
        assert state_filtered_response.status_code == 200
        state_filtered_results = state_filtered_response.json()["results"]
        assert len(state_filtered_results) == 1
        assert state_filtered_results[0]["public_id"] == "project-contract-model"

        empty_state_filtered_response = client.get(
            "/api/models/search",
            params={
                "project_id": project_one["id"],
                "project_member_state": "rejected",
                "page": 1,
                "per_page": 10,
            },
        )
        assert empty_state_filtered_response.status_code == 200
        assert empty_state_filtered_response.json()["results"] == []

        projects_response = client.get("/api/projects")
        assert projects_response.status_code == 200
        projects_payload = projects_response.json()
        assert projects_payload["visibility"]["show_archived"] is False
        assert {int(project["id"]) for project in projects_payload["projects"]} == {
            int(project_one["id"]),
            int(project_two["id"]),
        }


def test_project_internal_tasks_crud(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "title": "Garage Reorg",
                "task_backend": "internal",
                "status": "planning",
            },
        )
        assert create_response.status_code == 200
        project = create_response.json()["project"]
        project_id = int(project["id"])
        assert project["task_backend"] == "internal"

        task_create = client.post(
            f"/api/projects/{project_id}/tasks",
            json={
                "title": "Buy M3 screws",
                "notes": "Check the bin in the garage first.",
                "due_at": "2026-06-01T12:00:00Z",
            },
        )
        assert task_create.status_code == 200
        created_task = task_create.json()["task"]
        task_id = int(created_task["id"])
        assert created_task["status"] == "open"
        assert created_task["notes"] == "Check the bin in the garage first."
        assert created_task["due_at"] == "2026-06-01T12:00:00Z"

        task_toggle = client.patch(
            f"/api/projects/{project_id}/tasks/{task_id}",
            json={
                "status": "done",
                "notes": "Found a partial pack already.",
            },
        )
        assert task_toggle.status_code == 200
        updated_task = task_toggle.json()["task"]
        assert updated_task["status"] == "done"
        assert updated_task["notes"] == "Found a partial pack already."

        detail_response = client.get(f"/api/projects/{project_id}")
        assert detail_response.status_code == 200
        detail_project = detail_response.json()["project"]
        assert detail_project["task_backend"] == "internal"
        assert detail_project["task_summary"] == {"total": 1, "open": 0, "done": 1}
        assert len(detail_project["tasks"]) == 1
        assert detail_project["tasks"][0]["title"] == "Buy M3 screws"
        assert detail_project["tasks"][0]["notes"] == "Found a partial pack already."
        assert detail_project["tasks"][0]["due_at"] == "2026-06-01T12:00:00Z"

        task_delete = client.delete(f"/api/projects/{project_id}/tasks/{task_id}")
        assert task_delete.status_code == 200

        tasks_after_delete = client.get(f"/api/projects/{project_id}/tasks")
        assert tasks_after_delete.status_code == 200
        assert tasks_after_delete.json()["items"] == []


def test_project_task_backend_can_be_updated(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "title": "Task Backend Update",
                "task_backend": "none",
            },
        )
        assert create_response.status_code == 200
        project_id = int(create_response.json()["project"]["id"])

        update_response = client.patch(
            f"/api/projects/{project_id}",
            json={
                "title": "Task Backend Update",
                "task_backend": "internal",
            },
        )
        assert update_response.status_code == 200
        updated_project = update_response.json()["project"]
        assert updated_project["task_backend"] == "internal"

        detail_response = client.get(f"/api/projects/{project_id}")
        assert detail_response.status_code == 200
        assert detail_response.json()["project"]["task_backend"] == "internal"


def test_bootstrap_repairs_stale_project_task_schema_drift(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute("DROP TABLE IF EXISTS model_catalog_project_tasks")
        connection.execute("ALTER TABLE model_catalog_projects RENAME TO model_catalog_projects_drift_backup")
        connection.execute(
            """
            CREATE TABLE model_catalog_projects (
                id INTEGER PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT,
                notes TEXT,
                bambuddy_project_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                archived_at TEXT,
                status TEXT NOT NULL DEFAULT 'evaluating',
                project_type TEXT,
                origin TEXT,
                origin_url TEXT,
                completed_at TEXT,
                created_by TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO model_catalog_projects (
                id, slug, title, description, notes, bambuddy_project_id,
                created_at, updated_at, archived_at, status, project_type,
                origin, origin_url, completed_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "stale-project-task-schema",
                "Stale Project Task Schema",
                None,
                None,
                None,
                "2026-05-28T00:00:00Z",
                "2026-05-28T00:00:00Z",
                None,
                "evaluating",
                None,
                None,
                None,
                None,
                None,
            ),
        )
        connection.execute("DROP TABLE model_catalog_projects_drift_backup")
        connection.commit()
    finally:
        connection.close()

    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        detail_before = client.get("/api/projects/1")
        assert detail_before.status_code == 200
        assert detail_before.json()["project"]["task_backend"] == "none"

        update_response = client.patch(
            "/api/projects/1",
            json={
                "title": "Stale Project Task Schema",
                "task_backend": "internal",
            },
        )
        assert update_response.status_code == 200
        assert update_response.json()["project"]["task_backend"] == "internal"

        tasks_response = client.get("/api/projects/1/tasks")
        assert tasks_response.status_code == 200
        assert tasks_response.json()["task_backend"] == "internal"
        assert tasks_response.json()["items"] == []


def test_project_tasks_require_internal_backend(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "title": "Small One Off",
                "task_backend": "none",
            },
        )
        assert create_response.status_code == 200
        project_id = int(create_response.json()["project"]["id"])

        task_create = client.post(
            f"/api/projects/{project_id}/tasks",
            json={"title": "Should fail"},
        )
        assert task_create.status_code == 409
        assert task_create.json()["error"] == "task_backend_not_internal"