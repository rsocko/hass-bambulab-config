from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = REPO_ROOT / "homeassistant" / "custom_components" / "bambuddy" / "print_history"
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))


from query import archive_activity_rows, option_sets, project_archive, query_archives  # noqa: E402
from store import PrintHistoryStore  # noqa: E402


def _projected_archives() -> list[dict]:
    raw = [
        {
            "id": 101,
            "printer_id": 1,
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
            "object_count": 2,
            "layer_height": 0.16,
            "designer": "Jane",
            "is_favorite": True,
            "tags": "display,hueforge,s:123",
            "notes": "User note\n\n+>{\"s\":\"c\",\"F\":[{\"n\":\"Blue PLA\",\"h\":\"#112233\"}]}",
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
            "object_count": 1,
            "layer_height": 0.20,
            "designer": "Alex",
            "is_favorite": False,
            "tags": "qa",
            "notes": "Failed print",
            "failure_reason": "Layer shift",
            "project_name": "",
            "extra_data": {"filament_slots": [{"tray": "B1", "color": "#445566", "used_grams": 15.0}]},
        },
    ]
    return [project_archive(item) for item in raw]


def test_variant3_query_contract_matches_browser_filters() -> None:
    archives = _projected_archives()
    states = {
        "input_select.print_history_filter_status": "Completed",
        "input_select.print_history_filter_enrichment_status": "All",
        "input_select.print_history_filter_material": "PLA",
        "input_select.print_history_filter_printer": "1",
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


def test_variant3_store_persists_archives_and_side_tables(tmp_path: Path) -> None:
    store = PrintHistoryStore(tmp_path / "print_history.db")
    store.initialize()

    archives = _projected_archives()
    store.replace_archives(archives)
    loaded = store.load_archives()

    assert [archive["id"] for archive in loaded] == [101, 202]
    assert loaded[0]["filament_slots"][0]["color"] == "#112233"


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


def test_variant3_activity_rows_expose_only_summary_fields() -> None:
    rows = archive_activity_rows(_projected_archives())

    assert rows[0]["print_name"] == "Hueforge Batman"
    assert rows[0]["status"] == "completed"
    assert "notes" not in rows[0]
    assert "payload_hash" not in rows[0]


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
        "input_select.print_history_filter_printer": "1",
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
    assert actual.activity_metric_total_label == expected.activity_metric_total_label
    assert actual.available_colors == expected.available_colors
    assert actual.available_color_tooltips == expected.available_color_tooltips


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
    assert rows[0]["filament_slots"][0]["color"] == "#112233"


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


def test_variant3_option_sets_keep_none_and_strip_system_tags() -> None:
    options = option_sets(_projected_archives())

    assert options["input_select.print_history_filter_project"] == ["All", "None", "Wall Art"]
    assert options["input_select.print_history_filter_tag"] == ["All", "None", "display", "hueforge", "qa"]