from __future__ import annotations

import pytest
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


import query as query_module  # noqa: E402
import store as store_module  # noqa: E402
from query import archive_activity_rows, option_sets, project_archive, query_archives  # noqa: E402
from store import PrintHistoryStore  # noqa: E402


def _projected_archives() -> list[dict]:
    raw = [
        {
            "id": 101,
            "printer_id": 1,
            "printer_name": "Workshop P1S",
            "print_name": "Hueforge Batman",
            "actual_time_seconds": 14400,
            "print_time_seconds": 15000,
            "filament_used_grams": 42.5,
            "filament_type": "PLA",
            "filament_color": "#112233,#ffffff",
            "status": "completed",
            "started_at": "2026-04-08T10:00:00Z",
            "completed_at": "2026-04-08T14:00:00Z",
            "created_at": "2026-04-08T09:58:00Z",
            "cost": 2.35,
            "duplicate_count": 2,
            "duplicate_sequence": 0,
            "original_archive_id": 101,
            "object_count": 2,
            "layer_height": 0.16,
            "designer": "Jane",
            "is_favorite": True,
            "tags": "display,hueforge,s:123",
            "notes": "User note\n\n+>{\"s\":\"c\",\"F\":[{\"n\":\"Blue PLA\",\"h\":\"#112233\"}]}",
            "file_path": "archives/101/model.3mf",
            "file_size": 98304,
            "photos": [
                "finish-overview.webp",
                {"path": "topdown-closeup.jpg", "role": "finish"},
                {"url": "detail-angle.png"},
            ],
            "thumbnail_path": "/api/v1/archives/101/thumbnail",
            "project_name": "Wall Art",
            "extra_data": {
                "filament_slots": [
                    {"tray": "A1", "name": "Blue PLA", "color": "#112233", "used_grams": 21.2},
                    {"tray": "A2", "name": "White PLA", "color": "#FFFFFF", "used_grams": 21.3},
                ]
            },
        },
        {
            "id": 202,
            "printer_id": 2,
            "printer_name": "Garage A1",
            "print_name": "Fixture Test",
            "actual_time_seconds": 3600,
            "print_time_seconds": 3700,
            "filament_used_grams": 15.0,
            "filament_type": "PETG",
            "filament_color": "#445566",
            "status": "failed",
            "started_at": "2026-03-15T08:00:00Z",
            "completed_at": "2026-03-15T09:00:00Z",
            "created_at": "2026-03-15T07:55:00Z",
            "cost": 0.75,
            "duplicate_count": 2,
            "duplicate_sequence": 1,
            "original_archive_id": 101,
            "object_count": 1,
            "layer_height": 0.20,
            "designer": "Alex",
            "is_favorite": False,
            "tags": "qa",
            "notes": "Failed print",
            "failure_reason": "Layer shift",
            "project_name": "",
            "source_3mf_path": "archive_sources/202/source.3mf",
            "extra_data": {
                "no_3mf_available": True,
                "filament_slots": [{"tray": "B1", "color": "#445566", "used_grams": 15.0}],
            },
        },
    ]
    return [project_archive(item) for item in raw]


def _live_style_projected_archive() -> dict:
    return project_archive(
        {
            "id": 218,
            "printer_id": 1,
            "printer_name": "Workshop P1S",
            "print_name": "EPIC Giant Moon - Plate 7",
            "actual_time_seconds": 13430,
            "print_time_seconds": 13285,
            "filament_used_grams": 58.42,
            "filament_type": "PLA",
            "filament_color": "#000000,#482960,#E8E6D0,#F7D959,#FFFFFF",
            "status": "completed",
            "started_at": "2026-04-10T13:56:31.547927",
            "completed_at": "2026-04-10T17:40:21.988315",
            "created_at": "2026-04-10T13:56:31",
            "cost": 0.99,
            "object_count": 1,
            "layer_height": "0.08",
            "designer": "doomtools",
            "is_favorite": False,
            "tags": "Hueforge,Space,f:6,s:225,f:5,s:260,f:135,s:259,f:44,s:58,f:86,s:119",
            "notes": "+>{\"F\":[{\"f\":6,\"h\":\"#FFFFFF\",\"n\":\"Bambu Lab Jade White PLA\",\"s\":225,\"t\":\"A1\",\"w\":1.7},{\"f\":5,\"h\":\"#000000\",\"n\":\"Bambu Lab Black PLA\",\"s\":260,\"t\":\"A3\",\"w\":26.4},{\"f\":135,\"h\":\"#E8E6D0\",\"n\":\"Polymaker PolyLite PLA Natural PLA\",\"s\":259,\"t\":\"A4\",\"w\":20.9},{\"f\":44,\"h\":\"#482960\",\"n\":\"Bambu Lab Indigo Purple PLA\",\"s\":58,\"t\":\"B1\",\"w\":8.3},{\"f\":86,\"h\":\"#F7D959\",\"n\":\"Bambu Lab Matte Lemon Yellow PLA\",\"s\":119,\"t\":\"B4\",\"w\":1.1}],\"s\":\"c\"}",
            "nozzle_diameter": "0.4",
            "nozzle_temperature": 220,
            "project_name": "",
            "extra_data": {
                "filament_slots": [
                    {"color": "#000000", "type": "PLA", "used_grams": 0},
                    {"color": "#482960", "type": "PLA", "used_grams": 0},
                    {"color": "#E8E6D0", "type": "PLA", "used_grams": 0},
                    {"color": "#F7D959", "type": "PLA", "used_grams": 0},
                    {"color": "#FFFFFF", "type": "PLA", "used_grams": 0},
                ]
            },
        }
    )


def _failed_duration_fallback_archive() -> dict:
    return project_archive(
        {
            "id": 213,
            "printer_id": 1,
            "printer_name": "Workshop P1S",
            "print_name": "Filament Swatch System - Plate 18",
            "actual_time_seconds": None,
            "print_time_seconds": 1834,
            "filament_used_grams": 7.56,
            "filament_type": "PLA",
            "filament_color": "#000000,#E8E6D0",
            "status": "failed",
            "started_at": "2026-04-09T23:46:54.459808",
            "completed_at": "2026-04-09T23:58:10.320886",
            "created_at": "2026-04-09T23:46:54",
            "cost": 0.19,
            "object_count": 1,
            "layer_height": 0.2,
            "designer": "",
            "is_favorite": False,
            "tags": "3D Printing,Filament",
            "notes": "Failed print",
            "failure_reason": "Adhesion failure",
            "project_name": "",
            "extra_data": {},
        }
    )


def test_variant3_query_contract_matches_browser_filters() -> None:
    archives = _projected_archives()
    states = {
        "input_select.print_history_filter_status": "Completed",
        "input_select.print_history_filter_archive_error": "All",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "PLA",
        "input_select.print_history_filter_duplicates": "Originals Only",
        "input_select.print_history_filter_printer": "Workshop P1S",
        "input_select.print_history_filter_date_range": "All Time",
        "input_select.print_history_filter_designer": "Jane",
        "input_select.print_history_filter_project": "Wall Art",
        "input_select.print_history_filter_layer_height": "0.16",
        "input_select.print_history_filter_tag": "display",
        "input_boolean.print_history_filter_favorites_only": "on",
        "input_text.print_history_search": "batman",
        "input_text.print_history_filter_colors": "#112233",
        "input_text.print_history_activity_selected_date": "2026-04-08",
        "input_select.print_history_sort": "Date (Newest)",
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
    }
    result = query_archives(archives, states, now=datetime(2026, 4, 9, tzinfo=timezone.utc))

    assert result.filtered_count == 1
    assert result.total_pages == 1
    assert result.page_items[0]["id"] == 101
    assert result.has_active_filters is True
    assert "#112233" in result.available_colors
    tooltip_by_color = {entry["color"]: entry["tooltip"] for entry in result.available_color_tooltips}
    assert tooltip_by_color["#112233"] == "Blue PLA (#112233)"
    assert tooltip_by_color["#ffffff"] == "White PLA (#FFFFFF)"


def test_variant3_query_contract_supports_archived_status_filter() -> None:
    archived_archive = project_archive(
        {
            "id": 303,
            "printer_id": 3,
            "printer_name": "Import Queue",
            "print_name": "Historical Import",
            "actual_time_seconds": 5400,
            "print_time_seconds": 5400,
            "filament_used_grams": 18.0,
            "filament_type": "PLA",
            "filament_color": "#3366CC",
            "status": "archived",
            "started_at": "2026-04-07T09:00:00Z",
            "completed_at": "2026-04-07T10:30:00Z",
            "created_at": "2026-04-07T09:00:00Z",
            "cost": 0.55,
            "object_count": 1,
            "project_name": "",
            "extra_data": {},
        }
    )
    archives = _projected_archives() + [archived_archive]
    states = {
        "input_select.print_history_filter_status": "Archived",
        "input_select.print_history_filter_archive_error": "All",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "All",
        "input_select.print_history_filter_duplicates": "All",
        "input_select.print_history_filter_printer": "All",
        "input_select.print_history_filter_date_range": "All Time",
        "input_select.print_history_filter_designer": "All",
        "input_select.print_history_filter_project": "All",
        "input_select.print_history_filter_layer_height": "All",
        "input_select.print_history_filter_tag": "All",
        "input_boolean.print_history_filter_favorites_only": "off",
        "input_text.print_history_search": "",
        "input_text.print_history_filter_colors": "",
        "input_text.print_history_activity_selected_date": "",
        "input_select.print_history_sort": "Date (Newest)",
        "input_select.print_history_activity_metric": "Print Count",
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
    }

    result = query_archives(archives, states, now=datetime(2026, 4, 10, tzinfo=timezone.utc))

    assert result.filtered_count == 1
    assert [archive["id"] for archive in result.page_items] == [303]


def test_variant3_query_contract_prefers_note_payload_names_when_slot_names_blank() -> None:
    archives = [_live_style_projected_archive()]
    states = {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_archive_error": "All",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "All",
        "input_select.print_history_filter_duplicates": "All",
        "input_select.print_history_filter_printer": "All",
        "input_select.print_history_filter_date_range": "All Time",
        "input_select.print_history_filter_designer": "All",
        "input_select.print_history_filter_project": "All",
        "input_select.print_history_filter_layer_height": "All",
        "input_select.print_history_filter_tag": "All",
        "input_boolean.print_history_filter_favorites_only": "off",
        "input_text.print_history_search": "",
        "input_text.print_history_filter_colors": "",
        "input_text.print_history_activity_selected_date": "",
        "input_select.print_history_sort": "Date (Newest)",
        "input_select.print_history_activity_metric": "Print Count",
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
    }

    result = query_archives(archives, states, now=datetime(2026, 4, 10, tzinfo=timezone.utc))
    tooltip_by_color = {entry["color"]: entry["tooltip"] for entry in result.available_color_tooltips}

    assert tooltip_by_color["#000000"] == "Bambu Lab Black PLA (#000000)"
    assert tooltip_by_color["#482960"] == "Bambu Lab Indigo Purple PLA (#482960)"
    assert tooltip_by_color["#e8e6d0"] == "Polymaker PolyLite PLA Natural PLA (#E8E6D0)"
    assert tooltip_by_color["#f7d959"] == "Bambu Lab Matte Lemon Yellow PLA (#F7D959)"
    assert tooltip_by_color["#ffffff"] == "Bambu Lab Jade White PLA (#FFFFFF)"


def test_variant3_query_search_matches_archive_ids_and_operational_fields() -> None:
    archives = _projected_archives()
    base_states = {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_archive_error": "All",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "All",
        "input_select.print_history_filter_duplicates": "All",
        "input_select.print_history_filter_printer": "All",
        "input_select.print_history_filter_date_range": "All Time",
        "input_select.print_history_filter_designer": "All",
        "input_select.print_history_filter_project": "All",
        "input_select.print_history_filter_layer_height": "All",
        "input_select.print_history_filter_tag": "All",
        "input_boolean.print_history_filter_favorites_only": "off",
        "input_text.print_history_filter_colors": "",
        "input_text.print_history_activity_selected_date": "",
        "input_select.print_history_sort": "Date (Newest)",
        "input_select.print_history_activity_metric": "Print Count",
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
    }

    cases = {
        "202": [202],
        "101": [101, 202],
        "workshop p1s": [101],
        "wall art": [101],
        "layer shift": [202],
    }

    for search_text, expected_ids in cases.items():
        result = query_archives(
            archives,
            {**base_states, "input_text.print_history_search": search_text},
            now=datetime(2026, 4, 10, tzinfo=timezone.utc),
        )
        assert [archive["id"] for archive in result.page_items] == expected_ids


def test_variant3_query_local_date_key_uses_home_assistant_timezone() -> None:
    original_timezone = query_module.dt_util.DEFAULT_TIME_ZONE
    try:
        query_module.dt_util.DEFAULT_TIME_ZONE = timezone(timedelta(hours=-7))

        assert query_module.local_date_key("2026-04-09T05:30:00Z") == "2026-04-08"
        assert query_module.archive_date_key({"started_at": "2026-04-09T05:30:00Z"}) == "2026-04-08"
    finally:
        query_module.dt_util.DEFAULT_TIME_ZONE = original_timezone


def test_variant3_query_effective_duration_falls_back_to_timestamps_for_failed_archive() -> None:
    archive = _failed_duration_fallback_archive()

    assert archive["actual_time_seconds"] == 0
    assert query_module.effective_duration_seconds(archive) == 675


def test_variant3_query_page_items_include_effective_duration_seconds() -> None:
    archive = _failed_duration_fallback_archive()
    states = {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_archive_error": "All",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "All",
        "input_select.print_history_filter_duplicates": "All",
        "input_select.print_history_filter_printer": "All",
        "input_select.print_history_filter_date_range": "All Time",
        "input_select.print_history_filter_designer": "All",
        "input_select.print_history_filter_project": "All",
        "input_select.print_history_filter_layer_height": "All",
        "input_select.print_history_filter_tag": "All",
        "input_boolean.print_history_filter_favorites_only": "off",
        "input_text.print_history_search": "",
        "input_text.print_history_filter_colors": "",
        "input_text.print_history_activity_selected_date": "",
        "input_select.print_history_sort": "Date (Newest)",
        "input_select.print_history_activity_metric": "Total Time Printing",
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
    }

    result = query_archives([archive], states, now=datetime(2026, 4, 10, tzinfo=timezone.utc))

    assert result.page_items[0]["effective_duration_seconds"] == 675


def test_variant3_store_persists_archives_and_side_tables(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()

    archives = _projected_archives()
    store.replace_archives(archives)
    loaded = store.load_archives()

    assert [archive["id"] for archive in loaded] == [101, 202]
    assert loaded[0]["duplicate_count"] == 2
    assert loaded[1]["duplicate_sequence"] == 1
    assert loaded[0]["original_archive_id"] == 101
    assert loaded[1]["original_archive_id"] == 101
    assert loaded[0]["filament_slots"][0]["color"] == "#112233"
    assert loaded[0]["photos"] == ["finish-overview.webp", "topdown-closeup.jpg", "detail-angle.png"]


def test_variant3_store_quarantine_helper_renames_cache_files(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store._db_path.write_text("broken-cache", encoding="utf-8")

    recovered = store._quarantine_unopenable_database()

    assert recovered is True
    assert store._db_path.exists() is False
    quarantined = [path.name for path in tmp_path.iterdir() if ".open-failure-" in path.name]
    assert len(quarantined) == 1


def test_variant3_store_quarantines_unopenable_cache_and_rebuilds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store._db_path.write_text("broken-cache", encoding="utf-8")
    real_connect = store_module.sqlite3.connect
    state = {"failed": False}

    def flaky_connect(path: str | Path, *args: object, **kwargs: object) -> sqlite3.Connection:
        if Path(path) == store._db_path and not state["failed"]:
            state["failed"] = True
            raise sqlite3.OperationalError("unable to open database file")
        return real_connect(path, *args, **kwargs)

    monkeypatch.setattr(store_module.sqlite3, "connect", flaky_connect)

    loaded = store.load_archives()

    assert loaded == []
    assert state["failed"] is True
    assert store._db_path.exists() is True


def test_variant3_query_contract_filters_duplicates_and_originals() -> None:
    archives = _projected_archives()
    base_states = {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_archive_error": "All",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "All",
        "input_select.print_history_filter_duplicates": "Duplicates Only",
        "input_select.print_history_filter_printer": "All",
        "input_select.print_history_filter_date_range": "All Time",
        "input_select.print_history_filter_designer": "All",
        "input_select.print_history_filter_project": "All",
        "input_select.print_history_filter_layer_height": "All",
        "input_select.print_history_filter_tag": "All",
        "input_boolean.print_history_filter_favorites_only": "off",
        "input_text.print_history_search": "",
        "input_text.print_history_filter_colors": "",
        "input_text.print_history_activity_selected_date": "",
        "input_select.print_history_sort": "Date (Newest)",
        "input_select.print_history_activity_metric": "Print Count",
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
    }

    duplicate_result = query_archives(archives, base_states, now=datetime(2026, 4, 9, tzinfo=timezone.utc))
    assert [archive["id"] for archive in duplicate_result.page_items] == [202]
    assert "duplicates" in duplicate_result.active_filters

    original_states = dict(base_states)
    original_states["input_select.print_history_filter_duplicates"] = "Originals Only"
    original_result = query_archives(archives, original_states, now=datetime(2026, 4, 9, tzinfo=timezone.utc))
    assert [archive["id"] for archive in original_result.page_items] == [101]


def test_variant3_store_persists_sync_metadata_and_note_payload_rows(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()

    archives = _projected_archives()
    store.replace_archives(archives)

    detail = store.load_archive(101)
    payload_rows = store.load_note_payload_rows(101)
    stats = store.load_store_stats()

    assert detail is not None
    assert detail["source_updated_at"] == "2026-04-08T14:00:00Z"
    assert detail["payload_hash"]
    assert detail["photos"] == ["finish-overview.webp", "topdown-closeup.jpg", "detail-angle.png"]
    assert payload_rows == [
        {
            "row_index": 0,
            "tray": "",
            "name": "Blue PLA",
            "type": "",
            "color": "#112233",
            "used_grams": 0.0,
            "filament_id": "",
            "spool_id": "",
            "ambiguity_code": "",
        }
    ]
    assert stats["archive_count"] == 2
    assert stats["note_payload_row_count"] == 1

    sync = store.load_sync_metadata(101)

    assert sync is not None
    assert sync["source_updated_at"] == "2026-04-08T14:00:00Z"
    assert sync["payload_hash"]


def test_variant3_store_preserves_archive_error_projection_fields(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()

    archives = _projected_archives()
    store.replace_archives(archives)

    detail = store.load_archive(202)

    assert detail is not None
    assert detail["has_archive_error"] is True
    assert detail["missing_core_3mf"] is True
    assert detail["has_source_only"] is True
    assert detail["archive_error_type"] == "source_only"


def test_variant3_option_sets_include_duplicate_filter() -> None:
    options = option_sets(_projected_archives())
    assert options["input_select.print_history_filter_duplicates"] == ["All", "Originals Only", "Duplicates Only"]


def test_variant3_store_migrates_legacy_schema_before_refresh(tmp_path: Path) -> None:
    db_path = tmp_path / "print_history.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE archives (
                archive_id INTEGER PRIMARY KEY,
                printer_id TEXT,
                print_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                started_at TEXT,
                completed_at TEXT,
                created_at TEXT,
                actual_time_seconds INTEGER NOT NULL DEFAULT 0,
                print_time_seconds INTEGER NOT NULL DEFAULT 0,
                filament_used_grams REAL NOT NULL DEFAULT 0,
                filament_type TEXT NOT NULL DEFAULT '',
                filament_color TEXT NOT NULL DEFAULT '',
                cost REAL NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL DEFAULT 0,
                object_count INTEGER NOT NULL DEFAULT 1,
                layer_height TEXT NOT NULL DEFAULT '',
                nozzle_diameter TEXT NOT NULL DEFAULT '',
                nozzle_temperature INTEGER NOT NULL DEFAULT 0,
                total_layers INTEGER NOT NULL DEFAULT 0,
                sliced_for_model TEXT NOT NULL DEFAULT '',
                designer TEXT NOT NULL DEFAULT '',
                makerworld_url TEXT NOT NULL DEFAULT '',
                is_favorite INTEGER NOT NULL DEFAULT 0,
                tags TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                failure_reason TEXT NOT NULL DEFAULT '',
                thumbnail_path TEXT NOT NULL DEFAULT '',
                project_id TEXT,
                project_name TEXT NOT NULL DEFAULT '',
                enrichment_status TEXT NOT NULL DEFAULT '',
                json_payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE archive_filament_rows (
                archive_id INTEGER NOT NULL,
                row_index INTEGER NOT NULL,
                tray TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                type TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT '',
                used_grams REAL NOT NULL DEFAULT 0,
                filament_id TEXT,
                spool_id TEXT,
                PRIMARY KEY (archive_id, row_index)
            );
            CREATE TABLE archive_tags (
                archive_id INTEGER NOT NULL,
                normalized_tag TEXT NOT NULL,
                tag TEXT NOT NULL,
                is_system INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (archive_id, normalized_tag)
            );
            CREATE TABLE archive_photos (
                archive_id INTEGER NOT NULL,
                photo_index INTEGER NOT NULL,
                photo_path TEXT NOT NULL,
                photo_role TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (archive_id, photo_index)
            );
            """
        )

    store = PrintHistoryStore(db_path)
    store.initialize()
    store.replace_archives(_projected_archives())

    stats = store.load_store_stats()
    detail = store.load_archive(101)

    assert stats["archive_count"] == 2
    assert stats["note_payload_row_count"] == 1
    assert detail is not None
    assert detail["payload_hash"]
    assert detail["source_updated_at"] == "2026-04-08T14:00:00Z"


def test_variant3_store_replace_archives_self_heals_partial_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "print_history.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE archives (
                archive_id INTEGER PRIMARY KEY,
                printer_id TEXT,
                print_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                started_at TEXT,
                completed_at TEXT,
                created_at TEXT,
                actual_time_seconds INTEGER NOT NULL DEFAULT 0,
                print_time_seconds INTEGER NOT NULL DEFAULT 0,
                filament_used_grams REAL NOT NULL DEFAULT 0,
                filament_type TEXT NOT NULL DEFAULT '',
                filament_color TEXT NOT NULL DEFAULT '',
                cost REAL NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL DEFAULT 0,
                object_count INTEGER NOT NULL DEFAULT 1,
                layer_height TEXT NOT NULL DEFAULT '',
                nozzle_diameter TEXT NOT NULL DEFAULT '',
                nozzle_temperature INTEGER NOT NULL DEFAULT 0,
                total_layers INTEGER NOT NULL DEFAULT 0,
                sliced_for_model TEXT NOT NULL DEFAULT '',
                designer TEXT NOT NULL DEFAULT '',
                makerworld_url TEXT NOT NULL DEFAULT '',
                is_favorite INTEGER NOT NULL DEFAULT 0,
                tags TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                failure_reason TEXT NOT NULL DEFAULT '',
                thumbnail_path TEXT NOT NULL DEFAULT '',
                project_id TEXT,
                project_name TEXT NOT NULL DEFAULT '',
                enrichment_status TEXT NOT NULL DEFAULT '',
                json_payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

    store = PrintHistoryStore(db_path)
    store.replace_archives(_projected_archives())

    stats = store.load_store_stats()
    payload_rows = store.load_note_payload_rows(101)

    assert stats["archive_count"] == 2
    assert stats["note_payload_row_count"] == 1
    assert payload_rows[0]["name"] == "Blue PLA"


def test_variant3_store_connection_errors_include_db_path_diagnostics(tmp_path: Path) -> None:
    conflict_path = tmp_path / "storage-conflict"
    conflict_path.write_text("not a directory", encoding="utf-8")

    store = PrintHistoryStore(conflict_path / "print_history.db")

    with pytest.raises(sqlite3.OperationalError) as exc_info:
        store.initialize()

    message = str(exc_info.value)
    assert "failed to ensure parent directory" in message
    assert "db_path=" in message
    assert "parent_exists=True" in message
    assert "parent_is_dir=False" in message


def test_variant3_activity_rows_expose_only_summary_fields() -> None:
    rows = archive_activity_rows(_projected_archives())

    assert rows[0]["print_name"] == "Hueforge Batman"
    assert rows[0]["printer_name"] == "Workshop P1S"
    assert rows[0]["status"] == "completed"
    assert "notes" not in rows[0]
    assert "payload_hash" not in rows[0]


def test_variant3_activity_rows_include_effective_duration_seconds() -> None:
    rows = archive_activity_rows([_failed_duration_fallback_archive()])

    assert rows[0]["effective_duration_seconds"] == 675


def test_variant3_store_query_and_annotations_are_store_backed(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()
    store.replace_archives(_projected_archives())

    with sqlite3.connect(tmp_path / "print_history.db") as connection:
        connection.execute(
            """
            INSERT INTO archive_review_state (archive_id, review_status, mismatch_flags, reviewed_at, review_note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (101, "needs_review", "color_mismatch", "2026-04-09T12:00:00Z", "Check source tray mapping"),
        )
        connection.execute(
            """
            INSERT INTO archive_repair_lineage (archive_id, related_archive_id, relation_type, created_at, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (101, 202, "reprint_of", "2026-04-09T12:05:00Z", "Retried after failure"),
        )

    states = {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "All",
        "input_select.print_history_filter_printer": "All",
        "input_select.print_history_filter_date_range": "All Time",
        "input_select.print_history_filter_designer": "All",
        "input_select.print_history_filter_project": "All",
        "input_select.print_history_filter_layer_height": "All",
        "input_select.print_history_filter_tag": "All",
        "input_boolean.print_history_filter_favorites_only": "off",
        "input_text.print_history_search": "",
        "input_text.print_history_filter_colors": "",
        "input_text.print_history_activity_selected_date": "",
        "input_select.print_history_sort": "Date (Newest)",
        "input_select.print_history_activity_metric": "Print Count",
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
    }

    result = store.load_query_result(states)
    annotations = store.load_query_annotations([101, 202])
    activity = store.load_activity_summary()

    assert result.filtered_count == 2
    assert result.page_items[0]["id"] == 101
    assert annotations["review_state_by_archive"]["101"]["review_status"] == "needs_review"
    assert annotations["repair_lineage_by_archive"]["101"][0]["relation_type"] == "reprint_of"
    assert annotations["sync_metadata_by_archive"]["101"]["payload_hash"]
    assert activity["archive_count"] == 2
    assert activity["active_day_count"] == 2


def test_variant3_store_query_matches_python_contract_across_filters(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()
    archives = _projected_archives()
    store.replace_archives(archives)

    states = {
        "input_select.print_history_filter_status": "Completed",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "PLA",
        "input_select.print_history_filter_printer": "Workshop P1S",
        "input_select.print_history_filter_date_range": "All Time",
        "input_select.print_history_filter_designer": "Jane",
        "input_select.print_history_filter_project": "Wall Art",
        "input_select.print_history_filter_layer_height": "0.16",
        "input_select.print_history_filter_tag": "display",
        "input_boolean.print_history_filter_favorites_only": "on",
        "input_text.print_history_search": "batman",
        "input_text.print_history_filter_colors": "#112233",
        "input_text.print_history_activity_selected_date": "2026-04-08",
        "input_select.print_history_sort": "Date (Newest)",
        "input_select.print_history_activity_metric": "Print Count",
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
    }

    expected = query_archives(archives, states, now=datetime(2026, 4, 9, tzinfo=timezone.utc))
    actual = store.load_query_result(states)

    assert actual.filtered_count == expected.filtered_count
    assert actual.total_pages == expected.total_pages
    assert actual.current_page == expected.current_page
    assert [archive["id"] for archive in actual.page_items] == [archive["id"] for archive in expected.page_items]
    assert actual.activity_active_days_label == expected.activity_active_days_label
    assert actual.activity_active_days_compact_label == expected.activity_active_days_compact_label
    assert actual.activity_metric_total_label == expected.activity_metric_total_label
    assert actual.activity_metric_total_compact_label == expected.activity_metric_total_compact_label
    assert actual.available_colors == expected.available_colors
    assert actual.available_color_tooltips == expected.available_color_tooltips


def test_variant3_store_query_uses_note_payload_names_for_tooltips_when_slot_names_blank(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()
    store.replace_archives([_live_style_projected_archive()])

    states = {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "All",
        "input_select.print_history_filter_printer": "All",
        "input_select.print_history_filter_date_range": "All Time",
        "input_select.print_history_filter_designer": "All",
        "input_select.print_history_filter_project": "All",
        "input_select.print_history_filter_layer_height": "All",
        "input_select.print_history_filter_tag": "All",
        "input_boolean.print_history_filter_favorites_only": "off",
        "input_text.print_history_search": "",
        "input_text.print_history_filter_colors": "",
        "input_text.print_history_activity_selected_date": "",
        "input_select.print_history_sort": "Date (Newest)",
        "input_select.print_history_activity_metric": "Print Count",
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
    }

    result = store.load_query_result(states)
    tooltip_by_color = {entry["color"]: entry["tooltip"] for entry in result.available_color_tooltips}

    assert tooltip_by_color["#000000"] == "Bambu Lab Black PLA (#000000)"
    assert tooltip_by_color["#482960"] == "Bambu Lab Indigo Purple PLA (#482960)"
    assert tooltip_by_color["#e8e6d0"] == "Polymaker PolyLite PLA Natural PLA (#E8E6D0)"
    assert tooltip_by_color["#f7d959"] == "Bambu Lab Matte Lemon Yellow PLA (#F7D959)"
    assert tooltip_by_color["#ffffff"] == "Bambu Lab Jade White PLA (#FFFFFF)"


def test_variant3_store_query_search_matches_archive_ids_and_operational_fields(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()
    store.replace_archives(_projected_archives())

    base_states = {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "All",
        "input_select.print_history_filter_printer": "All",
        "input_select.print_history_filter_date_range": "All Time",
        "input_select.print_history_filter_designer": "All",
        "input_select.print_history_filter_project": "All",
        "input_select.print_history_filter_layer_height": "All",
        "input_select.print_history_filter_tag": "All",
        "input_boolean.print_history_filter_favorites_only": "off",
        "input_text.print_history_filter_colors": "",
        "input_text.print_history_activity_selected_date": "",
        "input_select.print_history_sort": "Date (Newest)",
        "input_select.print_history_activity_metric": "Print Count",
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
    }

    cases = {
        "202": [202],
        "101": [101, 202],
        "workshop p1s": [101],
        "wall art": [101],
        "layer shift": [202],
    }

    for search_text, expected_ids in cases.items():
        result = store.load_query_result({**base_states, "input_text.print_history_search": search_text})
        assert [archive["id"] for archive in result.page_items] == expected_ids


def test_variant3_query_this_month_uses_calendar_month_boundary() -> None:
    archives = _projected_archives()
    states = {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "All",
        "input_select.print_history_filter_printer": "All",
        "input_select.print_history_filter_date_range": "This Month",
        "input_select.print_history_filter_designer": "All",
        "input_select.print_history_filter_project": "All",
        "input_select.print_history_filter_layer_height": "All",
        "input_select.print_history_filter_tag": "All",
        "input_boolean.print_history_filter_favorites_only": "off",
        "input_text.print_history_search": "",
        "input_text.print_history_filter_colors": "",
        "input_text.print_history_activity_selected_date": "",
        "input_select.print_history_sort": "Date (Newest)",
        "input_select.print_history_activity_metric": "Print Count",
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
    }

    this_month = query_archives(archives, states, now=datetime(2026, 4, 10, tzinfo=timezone.utc))
    last_30_days = query_archives(
        archives,
        {**states, "input_select.print_history_filter_date_range": "Last 30 Days"},
        now=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )

    assert [archive["id"] for archive in this_month.page_items] == [101]
    assert [archive["id"] for archive in last_30_days.page_items] == [101, 202]


def test_variant3_store_this_month_threshold_uses_first_day_of_month(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")

    assert store._date_range_threshold("This Month", datetime(2026, 4, 10, tzinfo=timezone.utc).date()) == "2026-04-01"
    assert store._date_range_threshold("Last 30 Days", datetime(2026, 4, 10, tzinfo=timezone.utc).date()) == "2026-03-12"


def test_variant3_store_activity_rows_ignore_selected_day(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()
    store.replace_archives(_projected_archives())

    states = {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "All",
        "input_select.print_history_filter_printer": "All",
        "input_select.print_history_filter_date_range": "All Time",
        "input_select.print_history_filter_designer": "All",
        "input_select.print_history_filter_project": "All",
        "input_select.print_history_filter_layer_height": "All",
        "input_select.print_history_filter_tag": "All",
        "input_boolean.print_history_filter_favorites_only": "off",
        "input_text.print_history_search": "",
        "input_text.print_history_filter_colors": "",
        "input_text.print_history_activity_selected_date": "2026-04-08",
        "input_select.print_history_sort": "Date (Newest)",
        "input_select.print_history_activity_metric": "Print Count",
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
    }

    rows = store.load_activity_rows(states)

    assert [row["id"] for row in rows] == [101, 202]
    assert rows[0]["printer_name"] == "Workshop P1S"
    assert rows[0]["filament_slots"][0]["color"] == "#112233"


def test_variant3_store_uses_effective_duration_for_failed_archive_sort_and_output(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()
    archives = [
        _failed_duration_fallback_archive(),
        project_archive(
            {
                "id": 301,
                "printer_id": 1,
                "printer_name": "Workshop P1S",
                "print_name": "Completed Control Print",
                "actual_time_seconds": 1200,
                "print_time_seconds": 1260,
                "filament_used_grams": 9.0,
                "filament_type": "PLA",
                "filament_color": "#abcdef",
                "status": "completed",
                "started_at": "2026-04-10T10:00:00Z",
                "completed_at": "2026-04-10T10:20:00Z",
                "created_at": "2026-04-10T10:00:00Z",
                "cost": 0.25,
                "object_count": 1,
                "layer_height": 0.2,
                "designer": "",
                "is_favorite": False,
                "tags": "",
                "notes": "",
                "project_name": "",
                "extra_data": {},
            }
        ),
    ]
    store.replace_archives(archives)

    states = {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "All",
        "input_select.print_history_filter_printer": "All",
        "input_select.print_history_filter_date_range": "All Time",
        "input_select.print_history_filter_designer": "All",
        "input_select.print_history_filter_project": "All",
        "input_select.print_history_filter_layer_height": "All",
        "input_select.print_history_filter_tag": "All",
        "input_boolean.print_history_filter_favorites_only": "off",
        "input_text.print_history_search": "",
        "input_text.print_history_filter_colors": "",
        "input_text.print_history_activity_selected_date": "",
        "input_select.print_history_sort": "Duration (Longest)",
        "input_select.print_history_activity_metric": "Total Time Printing",
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
    }

    result = store.load_query_result(states)
    detail = store.load_archive(213)
    activity_rows = store.load_activity_rows(states)

    assert [archive["id"] for archive in result.page_items] == [301, 213]
    assert result.page_items[1]["effective_duration_seconds"] == 675
    assert detail is not None
    assert detail["effective_duration_seconds"] == 675
    assert activity_rows[1]["effective_duration_seconds"] == 675
    assert result.activity_metric_total_label == "0.5 h"


def test_variant3_store_activity_metric_total_uses_kg_for_large_filament_totals(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()
    archives = [
        project_archive(
            {
                "id": 401,
                "printer_id": 1,
                "printer_name": "Workshop P1S",
                "print_name": "Large Weight Print",
                "actual_time_seconds": 1800,
                "print_time_seconds": 1800,
                "filament_used_grams": 1000.0,
                "filament_type": "PLA",
                "filament_color": "#123456",
                "status": "completed",
                "started_at": "2026-04-10T10:00:00Z",
                "completed_at": "2026-04-10T10:30:00Z",
                "created_at": "2026-04-10T10:00:00Z",
                "cost": 12.34,
                "object_count": 1,
                "layer_height": 0.2,
                "designer": "Maker",
                "is_favorite": False,
                "tags": "",
                "notes": "",
                "project_name": "",
                "extra_data": {},
            }
        ),
        project_archive(
            {
                "id": 402,
                "printer_id": 1,
                "printer_name": "Workshop P1S",
                "print_name": "Top Off Print",
                "actual_time_seconds": 900,
                "print_time_seconds": 900,
                "filament_used_grams": 15.0,
                "filament_type": "PLA",
                "filament_color": "#654321",
                "status": "completed",
                "started_at": "2026-04-11T10:00:00Z",
                "completed_at": "2026-04-11T10:15:00Z",
                "created_at": "2026-04-11T10:00:00Z",
                "cost": 0.5,
                "object_count": 1,
                "layer_height": 0.2,
                "designer": "Maker",
                "is_favorite": False,
                "tags": "",
                "notes": "",
                "project_name": "",
                "extra_data": {},
            }
        ),
    ]
    store.replace_archives(archives)

    result = store.load_query_result(
        {
            "input_select.print_history_filter_status": "All",
            "input_select.print_history_filter_enrichment_status": "All",
            "input_select.print_history_filter_material": "All",
            "input_select.print_history_filter_printer": "All",
            "input_select.print_history_filter_date_range": "All Time",
            "input_select.print_history_filter_designer": "All",
            "input_select.print_history_filter_project": "All",
            "input_select.print_history_filter_layer_height": "All",
            "input_select.print_history_filter_tag": "All",
            "input_boolean.print_history_filter_favorites_only": "off",
            "input_text.print_history_search": "",
            "input_text.print_history_filter_colors": "",
            "input_text.print_history_activity_selected_date": "",
            "input_select.print_history_sort": "Date (Newest)",
            "input_select.print_history_activity_metric": "Filament Weight",
            "input_number.print_history_page_size": "10",
            "input_number.history_current_page": "1",
        }
    )

    assert result.activity_metric_total_label == "1.01 kg"
    assert result.activity_metric_total_compact_label == "1.01 kg"


def test_variant3_store_selected_day_uses_shared_local_day_projection(tmp_path: Path, monkeypatch) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()
    monkeypatch.setattr(query_module, "local_timezone", lambda: timezone(timedelta(hours=-7)))

    archives = [
        project_archive(
            {
                "id": 303,
                "printer_id": 1,
                "printer_name": "Workshop P1S",
                "print_name": "Overnight Plate",
                "actual_time_seconds": 1800,
                "print_time_seconds": 1800,
                "filament_used_grams": 9.5,
                "filament_type": "PLA",
                "filament_color": "#123456",
                "status": "completed",
                "started_at": "2026-04-09T01:30:00Z",
                "completed_at": "2026-04-09T02:00:00Z",
                "created_at": "2026-04-09T01:25:00Z",
                "cost": 0.31,
                "object_count": 1,
                "layer_height": 0.2,
                "designer": "NightShift",
                "is_favorite": False,
                "tags": "overnight",
                "notes": "",
                "project_name": "Ops",
                "extra_data": {},
            }
        )
    ]
    store.replace_archives(archives)

    states = {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "All",
        "input_select.print_history_filter_printer": "All",
        "input_select.print_history_filter_date_range": "All Time",
        "input_select.print_history_filter_designer": "All",
        "input_select.print_history_filter_project": "All",
        "input_select.print_history_filter_layer_height": "All",
        "input_select.print_history_filter_tag": "All",
        "input_boolean.print_history_filter_favorites_only": "off",
        "input_text.print_history_search": "",
        "input_text.print_history_filter_colors": "",
        "input_text.print_history_activity_selected_date": "2026-04-08",
        "input_select.print_history_sort": "Date (Newest)",
        "input_select.print_history_activity_metric": "Print Count",
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
    }

    expected = query_archives(archives, states, now=datetime(2026, 4, 10, tzinfo=timezone.utc))
    actual = store.load_query_result(states)

    assert expected.filtered_count == 1
    assert [archive["id"] for archive in expected.page_items] == [303]
    assert [archive["id"] for archive in actual.page_items] == [303]


def test_variant3_store_mutation_helpers_update_review_and_lineage(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()
    store.replace_archives(_projected_archives())

    store.upsert_review_state(
        101,
        review_status="needs_review",
        mismatch_flags="color_mismatch,weight_delta",
        review_note="Check tray attribution",
        reviewed_at="2026-04-09T12:00:00Z",
    )
    store.upsert_repair_lineage(
        101,
        202,
        relation_type="reprint_of",
        note="Retried after failure",
        created_at="2026-04-09T12:05:00Z",
    )

    review_state = store.load_review_state(101)
    lineage = store.load_repair_lineage(101)
    deleted = store.delete_repair_lineage(101, 202, "reprint_of")

    assert review_state is not None
    assert review_state["review_status"] == "needs_review"
    assert review_state["mismatch_flags"] == "color_mismatch,weight_delta"
    assert lineage[0]["relation_type"] == "reprint_of"
    assert deleted == 1
    assert store.load_repair_lineage(101) == []


def test_variant3_store_detail_loads_review_and_lineage(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()
    store.replace_archives(_projected_archives())

    with sqlite3.connect(tmp_path / "print_history.db") as connection:
        connection.execute(
            """
            INSERT INTO archive_review_state (archive_id, review_status, mismatch_flags, reviewed_at, review_note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (101, "reviewed", "", "2026-04-09T12:00:00Z", "Verified"),
        )
        connection.execute(
            """
            INSERT INTO archive_repair_lineage (archive_id, related_archive_id, relation_type, created_at, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (101, 202, "derived_from", "2026-04-09T12:05:00Z", "Original failure"),
        )

    review_state = store.load_review_state(101)
    lineage = store.load_repair_lineage(101)
    sync = store.load_sync_metadata(101)

    assert review_state is not None
    assert review_state["review_status"] == "reviewed"
    assert lineage[0]["related_archive_id"] == 202
    assert sync is not None
    assert sync["last_synced_at"]


def test_variant3_store_appends_timeline_events_idempotently(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()
    store.replace_archives(_projected_archives())

    first = store.append_archive_event(
        101,
        event_type="print_paused",
        event_source="bambu_lab",
        event_time="2026-04-08T11:15:00Z",
        event_status="paused",
        payload={"print_name": "Hueforge Batman"},
    )
    second = store.append_archive_event(
        101,
        event_type="print_paused",
        event_source="bambu_lab",
        event_time="2026-04-08T11:15:00Z",
        event_status="paused",
        payload={"print_name": "Hueforge Batman"},
    )

    timeline = store.load_archive_event_timeline(101)
    stats = store.load_store_stats()

    assert first["event_key"] == second["event_key"]
    assert len(timeline) == 1
    assert timeline[0]["type"] == "print_paused"
    assert timeline[0]["source"] == "bambu_lab"
    assert timeline[0]["payload"] == {"print_name": "Hueforge Batman"}
    assert stats["event_timeline_count"] == 1


def test_variant3_store_preserves_timeline_events_across_replace_archives(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()
    archives = _projected_archives()
    store.replace_archives(archives)
    store.append_archive_event(
        101,
        event_type="enrichment_applied",
        event_source="ha_service",
        event_time="2026-04-08T14:00:00Z",
        event_status="completed",
    )

    store.replace_archives(archives)

    timeline = store.load_archive_event_timeline(101)

    assert len(timeline) == 1
    assert timeline[0]["type"] == "enrichment_applied"


def test_variant3_store_delta_sync_keeps_unchanged_rows_and_updates_last_synced_at(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDatetime(datetime):
        _now = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return cls._now.replace(tzinfo=None)
            return cls._now.astimezone(tz)

    monkeypatch.setattr(store_module, "datetime", FakeDatetime)

    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()
    archives = _projected_archives()
    store.replace_archives(archives)

    store.append_archive_event(
        101,
        event_type="enrichment_applied",
        event_source="ha_service",
        event_time="2026-04-08T14:00:00Z",
        event_status="completed",
    )

    with sqlite3.connect(tmp_path / "print_history.db") as connection:
        first_sync = connection.execute(
            "SELECT last_synced_at, updated_at FROM archives WHERE archive_id = ?",
            (101,),
        ).fetchone()

    FakeDatetime._now = datetime(2026, 4, 10, 12, 5, tzinfo=timezone.utc)
    store.replace_archives(archives)

    with sqlite3.connect(tmp_path / "print_history.db") as connection:
        second_sync = connection.execute(
            "SELECT last_synced_at, updated_at FROM archives WHERE archive_id = ?",
            (101,),
        ).fetchone()

    timeline = store.load_archive_event_timeline(101)

    assert first_sync is not None
    assert second_sync is not None
    assert first_sync[0] != second_sync[0]
    assert first_sync[1] == second_sync[1]
    assert len(timeline) == 1
    assert timeline[0]["type"] == "enrichment_applied"


def test_variant3_store_delta_sync_rebuilds_only_changed_archive_children(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()
    archives = _projected_archives()
    store.replace_archives(archives)

    changed_archives = _projected_archives()
    changed_archives[0] = {
        **changed_archives[0],
        "notes": "User note updated\n\n+>{\"s\":\"c\",\"F\":[{\"n\":\"Blue PLA\",\"h\":\"#112233\"}]}",
        "filament_slots": [
            {"tray": "A1", "name": "Blue PLA", "color": "#112233", "used_grams": 30.0},
        ],
    }
    store.append_archive_event(
        101,
        event_type="repair_applied",
        event_source="ha_service",
        event_time="2026-04-08T15:00:00Z",
        event_status="completed",
    )

    store.replace_archives(changed_archives)

    archive = store.load_archive(101)
    timeline = store.load_archive_event_timeline(101)

    with sqlite3.connect(tmp_path / "print_history.db") as connection:
        changed_child_count = connection.execute(
            "SELECT COUNT(*) FROM archive_filament_rows WHERE archive_id = ?",
            (101,),
        ).fetchone()[0]
        unchanged_child_count = connection.execute(
            "SELECT COUNT(*) FROM archive_filament_rows WHERE archive_id = ?",
            (202,),
        ).fetchone()[0]

    assert archive is not None
    assert archive["notes"].startswith("User note updated")
    assert changed_child_count == 1
    assert unchanged_child_count == 1
    assert len(timeline) == 1
    assert timeline[0]["type"] == "repair_applied"


def test_variant3_option_sets_keep_none_and_strip_system_tags() -> None:
    options = option_sets(_projected_archives())

    assert options["input_select.print_history_filter_printer"] == ["All", "Garage A1", "Workshop P1S"]
    assert options["input_select.print_history_filter_project"] == ["All", "None", "Wall Art"]
    assert options["input_select.print_history_filter_tag"] == ["All", "None", "display", "hueforge", "qa"]