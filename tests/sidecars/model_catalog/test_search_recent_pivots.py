import sqlite3

from sidecars.model_catalog.app.catalog_cache import read_cached_model_summaries
from sidecars.model_catalog.app.routers.models import _sort_value


def test_read_cached_model_summaries_extracts_created_and_updated_timestamps(tmp_path):
    db_path = tmp_path / "catalog_cache.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE model_summary_cache (
                model_url TEXT PRIMARY KEY,
                model_public_id TEXT,
                model_id TEXT,
                model_name TEXT NOT NULL,
                preview_url TEXT,
                creator_name TEXT,
                collection_names_json TEXT NOT NULL,
                keyword_names_json TEXT NOT NULL,
                raw_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO model_summary_cache (
                model_url, model_public_id, model_id, model_name, preview_url,
                creator_name, collection_names_json, keyword_names_json, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "https://example.test/models/alpha",
                "alpha",
                "1",
                "Alpha Model",
                None,
                "tester",
                "[]",
                "[]",
                '{"created_at":"2026-05-10T12:00:00Z","updatedAt":"2026-05-11T12:00:00Z"}',
            ),
        )
        connection.commit()
    finally:
        connection.close()

    summaries = read_cached_model_summaries(db_path=db_path)

    assert len(summaries) == 1
    assert summaries[0].created_at == "2026-05-10T12:00:00Z"
    assert summaries[0].updated_at == "2026-05-11T12:00:00Z"


def test_added_sort_prefers_newest_created_at():
    newer = {"name": "Newer", "created_at": "2026-05-12T00:00:00Z", "ranking": {}}
    older = {"name": "Older", "created_at": "2026-05-01T00:00:00Z", "ranking": {}}

    assert _sort_value(newer, "added") < _sort_value(older, "added")