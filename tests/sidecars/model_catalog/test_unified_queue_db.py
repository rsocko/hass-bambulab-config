from pathlib import Path

from app.db import bootstrap_database, connect
from app.db_unified_queue import (
    create_unified_queue_entry,
    create_unified_queue_file_unit,
    create_unified_queue_plate_unit,
    delete_unified_queue_entry,
    list_unified_queue_entries,
    list_unified_queue_file_units,
    list_unified_queue_plate_units,
    read_unified_queue_file_unit,
    read_unified_queue_plate_unit,
    update_unified_queue_entry,
    update_unified_queue_file_unit,
    update_unified_queue_plate_unit,
)


def _bootstrap(tmp_path: Path) -> Path:
    db_path = tmp_path / "model_catalog.db"
    bootstrap_database(db_path)
    return db_path


def test_unified_queue_tables_are_created(tmp_path: Path) -> None:
    db_path = _bootstrap(tmp_path)
    connection = connect(db_path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
    finally:
        connection.close()

    table_names = {str(row["name"]) for row in rows}
    assert "unified_queue_entries" in table_names
    assert "unified_queue_file_units" in table_names
    assert "unified_queue_plate_units" in table_names


def test_connect_enables_foreign_keys(tmp_path: Path) -> None:
    db_path = _bootstrap(tmp_path)
    connection = connect(db_path)
    try:
        row = connection.execute("PRAGMA foreign_keys").fetchone()
    finally:
        connection.close()

    assert row is not None
    assert int(row[0]) == 1


def test_unified_queue_crud_round_trip_for_entry_file_and_plate_units(tmp_path: Path) -> None:
    db_path = _bootstrap(tmp_path)

    entry = create_unified_queue_entry(
        db_path=db_path,
        queue_entry_id="uqe-001",
        source_kind="working_file",
        source_ref="wg-42",
        title="Cable Clip Batch",
        state="preparing",
        rank=10,
        copies_requested=2,
        selection_mode="selected_plates",
        estimated_total_minutes=180,
        duration_bucket="overnight",
        ams_ready_score=70,
        overnight_fit_score=90,
        queue_notes="Black PETG preferred",
    )
    assert entry.queue_entry_id == "uqe-001"
    assert entry.selection_mode == "selected_plates"
    assert entry.duration_bucket == "overnight"

    file_unit = create_unified_queue_file_unit(
        db_path=db_path,
        queue_entry_id=entry.queue_entry_id,
        file_unit_id="file-unit-1",
        file_id="working-file-123",
        file_name="Cable_Clip.3mf",
        estimated_minutes=75,
        filament_requirements={"material": "PETG", "colors": ["#000000"]},
        archive_link_summary={"count": 1, "recent_outcome": "success"},
    )
    assert file_unit.file_unit_id == "file-unit-1"
    assert file_unit.file_name == "Cable_Clip.3mf"
    assert file_unit.filament_requirements["material"] == "PETG"

    plate_unit = create_unified_queue_plate_unit(
        db_path=db_path,
        queue_entry_id=entry.queue_entry_id,
        file_unit_id=file_unit.file_unit_id,
        plate_unit_id="plate-unit-1",
        plate_key="plate_1",
        plate_name="Main plate",
        state="pending",
        estimated_minutes=38,
    )
    assert plate_unit.plate_unit_id == "plate-unit-1"
    assert plate_unit.plate_key == "plate_1"
    assert plate_unit.state == "pending"

    updated_entry = update_unified_queue_entry(
        db_path=db_path,
        queue_entry_id=entry.queue_entry_id,
        state="in_progress",
        rank=1,
        copies_completed=1,
        last_attempt_outcome="success",
    )
    assert updated_entry is not None
    assert updated_entry.state == "in_progress"
    assert updated_entry.rank == 1
    assert updated_entry.copies_completed == 1
    assert updated_entry.last_attempt_outcome == "success"

    updated_file = update_unified_queue_file_unit(
        db_path=db_path,
        queue_entry_id=entry.queue_entry_id,
        file_unit_id=file_unit.file_unit_id,
        selected=False,
        estimated_minutes=80,
    )
    assert updated_file is not None
    assert updated_file.selected is False
    assert updated_file.estimated_minutes == 80

    updated_plate = update_unified_queue_plate_unit(
        db_path=db_path,
        queue_entry_id=entry.queue_entry_id,
        file_unit_id=file_unit.file_unit_id,
        plate_unit_id=plate_unit.plate_unit_id,
        state="done",
        completed_by_archive_id="archive-8877",
        completion_confidence="high",
        attempt_count=2,
        last_attempt_outcome="success",
    )
    assert updated_plate is not None
    assert updated_plate.state == "done"
    assert updated_plate.completed_by_archive_id == "archive-8877"
    assert updated_plate.completion_confidence == "high"
    assert updated_plate.attempt_count == 2

    entries = list_unified_queue_entries(db_path=db_path)
    file_units = list_unified_queue_file_units(db_path=db_path, queue_entry_id=entry.queue_entry_id)
    plate_units = list_unified_queue_plate_units(
        db_path=db_path,
        queue_entry_id=entry.queue_entry_id,
        file_unit_id=file_unit.file_unit_id,
    )
    assert len(entries) == 1
    assert len(file_units) == 1
    assert len(plate_units) == 1

    stored_file = read_unified_queue_file_unit(
        db_path=db_path,
        queue_entry_id=entry.queue_entry_id,
        file_unit_id=file_unit.file_unit_id,
    )
    stored_plate = read_unified_queue_plate_unit(
        db_path=db_path,
        queue_entry_id=entry.queue_entry_id,
        file_unit_id=file_unit.file_unit_id,
        plate_unit_id=plate_unit.plate_unit_id,
    )
    assert stored_file is not None
    assert stored_plate is not None

    removed = delete_unified_queue_entry(db_path=db_path, queue_entry_id=entry.queue_entry_id)
    assert removed is True

    assert list_unified_queue_entries(db_path=db_path) == []
    assert list_unified_queue_file_units(db_path=db_path, queue_entry_id=entry.queue_entry_id) == []
    assert list_unified_queue_plate_units(
        db_path=db_path,
        queue_entry_id=entry.queue_entry_id,
        file_unit_id=file_unit.file_unit_id,
    ) == []