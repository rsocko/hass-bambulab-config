from __future__ import annotations

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


def test_variant3_activity_rows_expose_only_summary_fields() -> None:
    rows = archive_activity_rows(_projected_archives())

    assert rows[0]["print_name"] == "Hueforge Batman"
    assert rows[0]["status"] == "completed"
    assert "notes" not in rows[0]
    assert "payload_hash" not in rows[0]


def test_variant3_option_sets_keep_none_and_strip_system_tags() -> None:
    options = option_sets(_projected_archives())

    assert options["input_select.print_history_filter_project"] == ["All", "None", "Wall Art"]
    assert options["input_select.print_history_filter_tag"] == ["All", "None", "display", "hueforge", "qa"]