from __future__ import annotations

from typing import Any

from tools.bambuddy import cleanup_printer_sd_files as cleanup_module
from tools.bambuddy.cleanup_printer_sd_files import (
    ArchiveRecord,
    ManifestRecord,
    RemoteFile,
    build_archive_indexes,
    build_manifest_indexes,
    build_report_sections,
    extract_list_entries,
    evaluate_remote_file,
    list_remote_files,
)


def test_hash_match_to_archived_3mf_is_delete() -> None:
    archive = ArchiveRecord(
        archive_id=101,
        filename="cache/test_piece.gcode.3mf",
        file_path="archive/1/test_piece.gcode.3mf",
        timelapse_path="",
        content_hash="A" * 64,
        notes="",
    )
    remote = RemoteFile(
        path="/cache/test_piece.gcode.3mf",
        name="test_piece.gcode.3mf",
        classification="gcode_3mf",
        size=123,
        sha256=("A" * 64,),
    )

    decision = evaluate_remote_file(
        remote,
        build_archive_indexes([archive]),
        build_manifest_indexes([]),
        {101: archive},
    )

    assert decision.action == "delete"
    assert decision.archive_ids == [101]
    assert decision.soft_matches == []


def test_filename_only_match_stays_manual_review() -> None:
    archive = ArchiveRecord(
        archive_id=101,
        filename="cache/test_piece.gcode.3mf",
        file_path="archive/1/test_piece.gcode.3mf",
        timelapse_path="",
        content_hash="",
        notes="",
    )
    remote = RemoteFile(
        path="/cache/test_piece.gcode.3mf",
        name="test_piece.gcode.3mf",
        classification="gcode_3mf",
        size=123,
    )

    decision = evaluate_remote_file(
        remote,
        build_archive_indexes([archive]),
        build_manifest_indexes([]),
        {101: archive},
    )

    assert decision.action == "review"
    assert decision.archive_ids == [101]
    assert decision.soft_matches == [
        {
            "match_type": "filename",
            "archive_ids": [101],
            "archive_names": ["test_piece.gcode.3mf"],
        }
    ]


def test_manifest_path_match_with_linked_archive_is_delete() -> None:
    archive = ArchiveRecord(
        archive_id=101,
        filename="cache/test_piece.3mf",
        file_path="archive/1/test_piece.3mf",
        timelapse_path="",
        content_hash="",
        notes="",
    )
    manifest = ManifestRecord(
        entry_id="abc",
        source_sha256="",
        source_md5="",
        normalized_paths=("/cache/test_piece.3mf",),
        linked_archive_ids=(101,),
    )
    remote = RemoteFile(
        path="/cache/test_piece.3mf",
        name="test_piece.3mf",
        classification="model_3mf",
        size=123,
    )

    decision = evaluate_remote_file(
        remote,
        build_archive_indexes([archive]),
        build_manifest_indexes([manifest]),
        {101: archive},
    )

    assert decision.action == "delete"
    assert decision.archive_ids == [101]
    assert decision.manifest_entry_ids == ["abc"]
    assert decision.soft_matches == []


def test_unique_timelapse_basename_is_delete() -> None:
    archive = ArchiveRecord(
        archive_id=101,
        filename="cache/test_piece.3mf",
        file_path="archive/1/test_piece.3mf",
        timelapse_path="archive/1/test_piece.mp4",
        content_hash="",
        notes="",
    )
    remote = RemoteFile(
        path="/timelapse/test_piece.mp4",
        name="test_piece.mp4",
        classification="timelapse",
        size=123,
    )

    decision = evaluate_remote_file(
        remote,
        build_archive_indexes([archive]),
        build_manifest_indexes([]),
        {101: archive},
    )

    assert decision.action == "delete"
    assert decision.archive_ids == [101]
    assert decision.soft_matches == [
        {
            "match_type": "timelapse_basename",
            "archive_ids": [101],
            "archive_names": ["test_piece.mp4"],
        }
    ]


def test_multiple_timelapse_matches_stay_review() -> None:
    archives = [
        ArchiveRecord(
            archive_id=101,
            filename="cache/test_piece.3mf",
            file_path="archive/1/test_piece.3mf",
            timelapse_path="archive/1/test_piece.mp4",
            content_hash="",
            notes="",
        ),
        ArchiveRecord(
            archive_id=102,
            filename="cache/test_piece_copy.3mf",
            file_path="archive/1/test_piece_copy.3mf",
            timelapse_path="archive/2/test_piece.mp4",
            content_hash="",
            notes="",
        ),
    ]
    remote = RemoteFile(
        path="/timelapse/test_piece.mp4",
        name="test_piece.mp4",
        classification="timelapse",
        size=123,
    )

    decision = evaluate_remote_file(
        remote,
        build_archive_indexes(archives),
        build_manifest_indexes([]),
        {archive.archive_id: archive for archive in archives},
    )

    assert decision.action == "review"
    assert decision.archive_ids == [101, 102]
    assert decision.soft_matches == [
        {
            "match_type": "timelapse_basename",
            "archive_ids": [101, 102],
            "archive_names": ["test_piece.mp4"],
        }
    ]


def test_unique_timelapse_stem_only_match_defaults_to_review() -> None:
    archive = ArchiveRecord(
        archive_id=101,
        filename="cache/test_piece.3mf",
        file_path="archive/1/test_piece.3mf",
        timelapse_path="archive/1/test_piece.mp4",
        content_hash="",
        notes="",
    )
    remote = RemoteFile(
        path="/timelapse/test_piece.avi",
        name="test_piece.avi",
        classification="timelapse",
        size=123,
    )

    decision = evaluate_remote_file(
        remote,
        build_archive_indexes([archive]),
        build_manifest_indexes([]),
        {101: archive},
    )

    assert decision.action == "review"
    assert decision.archive_ids == [101]
    assert decision.soft_matches == [
        {
            "match_type": "timelapse_stem",
            "archive_ids": [101],
            "archive_names": ["test_piece.mp4"],
        }
    ]


def test_unique_timelapse_stem_only_match_can_opt_into_delete() -> None:
    archive = ArchiveRecord(
        archive_id=101,
        filename="cache/test_piece.3mf",
        file_path="archive/1/test_piece.3mf",
        timelapse_path="archive/1/test_piece.mp4",
        content_hash="",
        notes="",
    )
    remote = RemoteFile(
        path="/timelapse/test_piece.avi",
        name="test_piece.avi",
        classification="timelapse",
        size=123,
    )

    decision = evaluate_remote_file(
        remote,
        build_archive_indexes([archive]),
        build_manifest_indexes([]),
        {101: archive},
        allow_stem_timelapse_delete=True,
    )

    assert decision.action == "delete"
    assert decision.archive_ids == [101]
    assert decision.soft_matches == [
        {
            "match_type": "timelapse_stem",
            "archive_ids": [101],
            "archive_names": ["test_piece.mp4"],
        }
    ]


def test_print_name_stem_only_match_is_reported_as_soft_match() -> None:
    archive = ArchiveRecord(
        archive_id=101,
        filename="archive-name.3mf",
        file_path="archive/1/archive-name.3mf",
        timelapse_path="",
        content_hash="",
        notes="",
        print_name="test_piece",
    )
    remote = RemoteFile(
        path="/cache/test_piece.3mf",
        name="test_piece.3mf",
        classification="model_3mf",
        size=123,
    )

    decision = evaluate_remote_file(
        remote,
        build_archive_indexes([archive]),
        build_manifest_indexes([]),
        {101: archive},
    )

    assert decision.action == "skip"
    assert decision.soft_matches == [
        {
            "match_type": "print_name_stem",
            "archive_ids": [101],
            "archive_names": ["test_piece"],
        }
    ]


def test_build_report_sections_groups_timelapse_and_non_timelapse_stem_matches() -> None:
    results = [
        {
            "path": "/timelapse/test_piece.avi",
            "name": "test_piece.avi",
            "classification": "timelapse",
            "decision": {
                "action": "review",
                "reason": "Unique archived timelapse stem-only match requires opt-in before deletion.",
                "archive_ids": [101],
                "soft_matches": [
                    {
                        "match_type": "timelapse_stem",
                        "archive_ids": [101],
                        "archive_names": ["test_piece.mp4"],
                    }
                ],
            },
        },
        {
            "path": "/cache/test_piece.3mf",
            "name": "test_piece.3mf",
            "classification": "model_3mf",
            "decision": {
                "action": "skip",
                "reason": "No archive-backed match found.",
                "archive_ids": [102],
                "soft_matches": [
                    {
                        "match_type": "print_name_stem",
                        "archive_ids": [102],
                        "archive_names": ["test_piece"],
                    }
                ],
            },
        },
    ]

    sections = build_report_sections(results)

    assert sections["review_candidates_for_allow_stem_tl_delete"]["count"] == 1
    assert sections["review_candidates_for_allow_stem_tl_delete"]["entries"][0]["path"] == "/timelapse/test_piece.avi"
    assert sections["non_timelapse_stem_matches"]["count"] == 1
    assert sections["non_timelapse_stem_matches"]["entries"][0]["path"] == "/cache/test_piece.3mf"


def test_skip_without_name_match_has_no_soft_matches() -> None:
    archive = ArchiveRecord(
        archive_id=101,
        filename="cache/other_piece.3mf",
        file_path="archive/1/other_piece.3mf",
        timelapse_path="",
        content_hash="",
        notes="",
    )
    remote = RemoteFile(
        path="/cache/test_piece.3mf",
        name="test_piece.3mf",
        classification="model_3mf",
        size=123,
    )

    decision = evaluate_remote_file(
        remote,
        build_archive_indexes([archive]),
        build_manifest_indexes([]),
        {101: archive},
    )

    assert decision.action == "skip"
    assert decision.soft_matches == []


def test_extract_list_entries_supports_bambuddy_printer_files_shape() -> None:
    payload = {
        "path": "/",
        "files": [
            {
                "name": "cache",
                "is_directory": True,
                "size": 0,
                "path": "/cache",
                "mtime": "2026-04-05T23:23:00",
            },
            {
                "name": "TFD_Optimus_v2.5_.3mf",
                "is_directory": False,
                "size": 901652,
                "path": "/TFD_Optimus_v2.5_.3mf",
                "mtime": "2026-04-22T07:26:00",
            },
        ],
    }

    entries = extract_list_entries(payload)

    assert len(entries) == 2
    assert entries[0]["is_directory"] is True
    assert entries[1]["path"] == "/TFD_Optimus_v2.5_.3mf"


def test_list_remote_files_handles_example_printer_files_response(monkeypatch: Any) -> None:
    responses = {
        "/": {
            "path": "/",
            "files": [
                {
                    "name": "timelapse",
                    "is_directory": True,
                    "size": 0,
                    "path": "/timelapse",
                    "mtime": "2026-04-05T23:11:00",
                },
                {
                    "name": "cache",
                    "is_directory": True,
                    "size": 0,
                    "path": "/cache",
                    "mtime": "2026-04-05T23:23:00",
                },
                {
                    "name": "TFD_Optimus_v2.5_.3mf",
                    "is_directory": False,
                    "size": 901652,
                    "path": "/TFD_Optimus_v2.5_.3mf",
                    "mtime": "2026-04-22T07:26:00",
                },
            ],
        },
        "/cache": {
            "path": "/cache",
            "files": [
                {
                    "name": "example.gcode.3mf",
                    "is_directory": False,
                    "size": 1234,
                    "path": "/cache/example.gcode.3mf",
                    "mtime": "2026-04-22T07:26:00",
                }
            ],
        },
        "/timelapse": {
            "path": "/timelapse",
            "files": [
                {
                    "name": "example.mp4",
                    "is_directory": False,
                    "size": 4567,
                    "path": "/timelapse/example.mp4",
                    "mtime": "2026-04-22T07:26:00",
                }
            ],
        },
    }

    def fake_request_json(method: str, url: str, headers: dict[str, str]) -> dict[str, Any]:
        assert method == "GET"
        assert headers == {"Accept": "application/json"}
        requested_path = url.split("path=", 1)[1]
        requested_path = requested_path.replace("%2F", "/")
        if requested_path == "":
            requested_path = "/"
        return responses[requested_path]

    monkeypatch.setattr(cleanup_module, "request_json", fake_request_json)

    remote_files = list_remote_files(
        base_url="http://bambuddy.socko.us",
        printer_id=1,
        roots=["/"],
        headers={"Accept": "application/json"},
    )

    assert [remote_file.path for remote_file in remote_files] == [
        "/TFD_Optimus_v2.5_.3mf",
        "/cache/example.gcode.3mf",
        "/timelapse/example.mp4",
    ]
    assert [remote_file.classification for remote_file in remote_files] == [
        "model_3mf",
        "gcode_3mf",
        "timelapse",
    ]
    archive = ArchiveRecord(
        archive_id=101,
        filename="cache/other_piece.3mf",
        file_path="archive/1/other_piece.3mf",
        timelapse_path="",
        content_hash="",
        notes="",
    )
    remote = RemoteFile(
        path="/cache/test_piece.3mf",
        name="test_piece.3mf",
        classification="model_3mf",
        size=123,
    )

    decision = evaluate_remote_file(
        remote,
        build_archive_indexes([archive]),
        build_manifest_indexes([]),
        {101: archive},
    )

    assert decision.action == "skip"
    assert decision.soft_matches == []


def test_extract_list_entries_supports_bambuddy_printer_files_shape() -> None:
    payload = {
        "path": "/",
        "files": [
            {
                "name": "cache",
                "is_directory": True,
                "size": 0,
                "path": "/cache",
                "mtime": "2026-04-05T23:23:00",
            },
            {
                "name": "TFD_Optimus_v2.5_.3mf",
                "is_directory": False,
                "size": 901652,
                "path": "/TFD_Optimus_v2.5_.3mf",
                "mtime": "2026-04-22T07:26:00",
            },
        ],
    }

    entries = extract_list_entries(payload)

    assert len(entries) == 2
    assert entries[0]["is_directory"] is True
    assert entries[1]["path"] == "/TFD_Optimus_v2.5_.3mf"


def test_list_remote_files_handles_example_printer_files_response(monkeypatch: Any) -> None:
    responses = {
        "/": {
            "path": "/",
            "files": [
                {
                    "name": "timelapse",
                    "is_directory": True,
                    "size": 0,
                    "path": "/timelapse",
                    "mtime": "2026-04-05T23:11:00",
                },
                {
                    "name": "cache",
                    "is_directory": True,
                    "size": 0,
                    "path": "/cache",
                    "mtime": "2026-04-05T23:23:00",
                },
                {
                    "name": "TFD_Optimus_v2.5_.3mf",
                    "is_directory": False,
                    "size": 901652,
                    "path": "/TFD_Optimus_v2.5_.3mf",
                    "mtime": "2026-04-22T07:26:00",
                },
            ],
        },
        "/cache": {
            "path": "/cache",
            "files": [
                {
                    "name": "example.gcode.3mf",
                    "is_directory": False,
                    "size": 1234,
                    "path": "/cache/example.gcode.3mf",
                    "mtime": "2026-04-22T07:26:00",
                }
            ],
        },
        "/timelapse": {
            "path": "/timelapse",
            "files": [
                {
                    "name": "example.mp4",
                    "is_directory": False,
                    "size": 4567,
                    "path": "/timelapse/example.mp4",
                    "mtime": "2026-04-22T07:26:00",
                }
            ],
        },
    }

    def fake_request_json(method: str, url: str, headers: dict[str, str]) -> dict[str, Any]:
        assert method == "GET"
        assert headers == {"Accept": "application/json"}
        requested_path = url.split("path=", 1)[1]
        requested_path = requested_path.replace("%2F", "/")
        if requested_path == "":
            requested_path = "/"
        return responses[requested_path]

    monkeypatch.setattr(cleanup_module, "request_json", fake_request_json)

    remote_files = list_remote_files(
        base_url="http://bambuddy.socko.us",
        printer_id=1,
        roots=["/"],
        headers={"Accept": "application/json"},
    )

    assert [remote_file.path for remote_file in remote_files] == [
        "/TFD_Optimus_v2.5_.3mf",
        "/cache/example.gcode.3mf",
        "/timelapse/example.mp4",
    ]
    assert [remote_file.classification for remote_file in remote_files] == [
        "model_3mf",
        "gcode_3mf",
        "timelapse",
    ]