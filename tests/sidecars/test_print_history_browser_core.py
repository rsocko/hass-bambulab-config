from __future__ import annotations

from datetime import datetime, timezone


from print_history_browser_core import activity_metric_total_labels, option_sets, project_archive, query_archives  # noqa: E402


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
            "file_path": "archives/101/model.3mf",
            "file_size": 98304,
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


def test_project_archive_extracts_compact_fields() -> None:
    archive = _projected_archives()[0]
    assert archive["id"] == 101
    assert archive["status"] == "completed"
    assert archive["enrichment_status"] == "complete"
    assert archive["filament_slots"][0]["color"] == "#112233"
    assert archive["object_count"] == 2
    assert archive["has_archive_error"] is False


def test_project_archive_flags_source_only_archive_errors() -> None:
    archive = _projected_archives()[1]

    assert archive["has_archive_error"] is True
    assert archive["missing_core_3mf"] is True
    assert archive["has_source_only"] is True
    assert archive["archive_error_type"] == "source_only"
    assert archive["archive_error_label"] == "Source 3MF Only"


def test_project_archive_ignores_stale_no_3mf_marker_when_primary_archive_exists() -> None:
    archive = project_archive(
        {
            "id": 229,
            "printer_id": 1,
            "print_name": "Batman Hueforge",
            "status": "completed",
            "file_path": "archive/1/20260412_191606_bat4 - 200x200.gcode/bat4 - 200x200.gcode.3mf",
            "file_size": 12216866,
            "content_hash": "bcfcdbd1e2091838a858d596be4d2f33fcfe74db766a569238f1c07472aa3a8e",
            "thumbnail_path": "archive/1/20260412_191606_bat4 - 200x200.gcode/thumbnail.png",
            "extra_data": {"no_3mf_available": True},
        }
    )

    assert archive["no_3mf_available"] is True
    assert archive["has_archive_error"] is False
    assert archive["missing_core_3mf"] is False



def test_query_archives_filters_sorts_and_pages() -> None:
    archives = _projected_archives()
    states = {
        "input_select.print_history_filter_status": "Completed",
        "input_select.print_history_filter_archive_error": "All",
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


def test_query_archives_uses_note_payload_names_when_slot_names_blank() -> None:
    archives = [_live_style_projected_archive()]
    states = {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_archive_error": "All",
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


def test_activity_metric_total_labels_use_kg_for_large_filament_totals() -> None:
    label, compact = activity_metric_total_labels(
        [
            {"filament_used_grams": 999.9},
            {"filament_used_grams": 20.1},
        ],
        "Filament Weight",
    )

    assert label == "1.02 kg"
    assert compact == "1.02 kg"


def test_query_archives_search_matches_archive_ids_and_operational_fields() -> None:
    archives = _projected_archives()
    base_states = {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_archive_error": "All",
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
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
    }

    cases = {
        "202": [202],
        "101": [101, 202],
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


def test_query_archives_this_month_uses_calendar_month_boundary() -> None:
    archives = _projected_archives()
    states = {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_archive_error": "All",
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


def test_query_archives_filters_archive_errors_by_specific_type() -> None:
    archives = _projected_archives()
    states = {
        "input_select.print_history_filter_status": "All",
        "input_select.print_history_filter_archive_error": "Source 3MF Only",
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
        "input_number.print_history_page_size": "10",
        "input_number.history_current_page": "1",
    }

    result = query_archives(archives, states, now=datetime(2026, 4, 10, tzinfo=timezone.utc))

    assert result.filtered_count == 1
    assert [archive["id"] for archive in result.page_items] == [202]


def test_option_sets_include_none_and_strip_system_tags() -> None:
    options = option_sets(_projected_archives())
    assert options["input_select.print_history_filter_project"] == ["All", "None", "Wall Art"]
    assert options["input_select.print_history_filter_tag"] == ["All", "None", "display", "hueforge", "qa"]
