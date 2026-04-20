from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.models import (
    ArchiveStorageArtifactFile,
    ArchiveStorageArtifactSet,
    ArchiveStorageMetrics,
    ArchiveStorageScanBatchRequest,
    ArchiveStorageScanBatchResponse,
    ArchiveStorageScanRequest,
    ArchiveStorageScanResponse,
    ArchiveStorageSummaryResponse,
)
from tools.bambuddy.runtime_repair_core import ensure_database_exists


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_json(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def _as_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _load_archive_row(connection: sqlite3.Connection, archive_id: int) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM print_archives WHERE id = ?", (archive_id,)).fetchone()
    if row is None:
        raise ValueError(f"Archive ID {archive_id} not found")
    return row


def _under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _resolve_relative_path(base_dir: Path, raw_path: Any) -> tuple[str, Path | None]:
    relative_path = _as_text(raw_path).replace("\\", "/")
    if not relative_path:
        return "", None

    candidate = Path(relative_path)
    absolute = candidate if candidate.is_absolute() else base_dir / candidate
    if not _under_root(absolute, base_dir):
        return relative_path, None
    return relative_path, absolute


def _file_info(base_dir: Path, raw_path: Any) -> ArchiveStorageArtifactFile:
    relative_path, absolute_path = _resolve_relative_path(base_dir, raw_path)
    exists = bool(absolute_path is not None and absolute_path.exists() and absolute_path.is_file())
    return ArchiveStorageArtifactFile(
        relative_path=relative_path,
        exists=exists,
        bytes=absolute_path.stat().st_size if exists else 0,
    )


def _photo_entries(raw_photos: Any) -> list[str]:
    raw_list = _coerce_json(raw_photos, [])
    if not isinstance(raw_list, list):
        return []
    photo_names: list[str] = []
    for item in raw_list:
        if isinstance(item, str):
            normalized = item.strip().replace("\\", "/")
            if normalized:
                photo_names.append(Path(normalized).name)
            continue
        if isinstance(item, dict):
            candidate = _as_text(item.get("path") or item.get("photo_path") or item.get("url"))
            if candidate:
                photo_names.append(Path(candidate.replace("\\", "/")).name)
    seen: set[str] = set()
    ordered: list[str] = []
    for item in photo_names:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _source_snapshot_hash(archive_row: sqlite3.Row) -> str:
    encoded = json.dumps(
        {
            "file_path": _as_text(archive_row["file_path"] if "file_path" in archive_row.keys() else ""),
            "thumbnail_path": _as_text(archive_row["thumbnail_path"] if "thumbnail_path" in archive_row.keys() else ""),
            "source_3mf_path": _as_text(archive_row["source_3mf_path"] if "source_3mf_path" in archive_row.keys() else ""),
            "timelapse_path": _as_text(archive_row["timelapse_path"] if "timelapse_path" in archive_row.keys() else ""),
            "f3d_path": _as_text(archive_row["f3d_path"] if "f3d_path" in archive_row.keys() else ""),
            "photos": _photo_entries(archive_row["photos"] if "photos" in archive_row.keys() else []),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _sum_photo_entries(archive_dir: Path | None, photo_names: list[str]) -> tuple[list[ArchiveStorageArtifactFile], int, int]:
    if archive_dir is None or not archive_dir.exists() or not archive_dir.is_dir():
        return [], 0, len(photo_names)

    photos_dir = archive_dir / "photos"
    photo_files: list[ArchiveStorageArtifactFile] = []
    total_bytes = 0
    missing_count = 0
    for name in photo_names:
        photo_path = photos_dir / name
        exists = photo_path.exists() and photo_path.is_file()
        byte_count = photo_path.stat().st_size if exists else 0
        if not exists:
            missing_count += 1
        else:
            total_bytes += byte_count
        photo_files.append(
            ArchiveStorageArtifactFile(relative_path=f"photos/{name}", exists=exists, bytes=byte_count)
        )
    return photo_files, total_bytes, missing_count


def _scan_other_files(
    archive_dir: Path | None,
    *,
    known_files: set[Path],
    include_extension_breakdown: bool,
    max_other_entries: int,
) -> tuple[int, int, dict[str, int]]:
    if archive_dir is None or not archive_dir.exists() or not archive_dir.is_dir():
        return 0, 0, {}

    other_bytes = 0
    other_count = 0
    extension_counter: Counter[str] = Counter()
    scanned_entries = 0

    for candidate in archive_dir.rglob("*"):
        if not candidate.is_file():
            continue
        scanned_entries += 1
        if max_other_entries > 0 and scanned_entries > max_other_entries:
            break
        if candidate in known_files:
            continue
        try:
            byte_count = candidate.stat().st_size
        except OSError:
            continue
        other_bytes += byte_count
        other_count += 1
        if include_extension_breakdown:
            extension_counter[(candidate.suffix.lower() or "[noext]")] += byte_count

    return other_bytes, other_count, dict(sorted(extension_counter.items()))


def scan_archive_storage(db_path: Path, request: ArchiveStorageScanRequest) -> ArchiveStorageScanResponse:
    ensure_database_exists(db_path)
    started_at = datetime.now(UTC)
    base_dir = db_path.parent

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        archive_row = _load_archive_row(connection, request.archive_id)

    file_info = _file_info(base_dir, archive_row["file_path"] if "file_path" in archive_row.keys() else "")
    thumbnail_info = _file_info(base_dir, archive_row["thumbnail_path"] if "thumbnail_path" in archive_row.keys() else "")
    source_info = _file_info(base_dir, archive_row["source_3mf_path"] if "source_3mf_path" in archive_row.keys() else "")
    timelapse_info = _file_info(base_dir, archive_row["timelapse_path"] if "timelapse_path" in archive_row.keys() else "")
    f3d_info = _file_info(base_dir, archive_row["f3d_path"] if "f3d_path" in archive_row.keys() else "")

    archive_dir: Path | None = None
    if file_info.exists and file_info.relative_path:
        _, resolved_file = _resolve_relative_path(base_dir, file_info.relative_path)
        archive_dir = resolved_file.parent if resolved_file is not None else None

    photo_names = _photo_entries(archive_row["photos"] if "photos" in archive_row.keys() else [])
    photo_files, photo_bytes, photo_missing = _sum_photo_entries(archive_dir, photo_names)

    known_files: set[Path] = set()
    for relative_path, info in (
        (file_info.relative_path, file_info),
        (thumbnail_info.relative_path, thumbnail_info),
        (source_info.relative_path, source_info),
        (timelapse_info.relative_path, timelapse_info),
        (f3d_info.relative_path, f3d_info),
    ):
        if info.exists and relative_path:
            _, resolved = _resolve_relative_path(base_dir, relative_path)
            if resolved is not None:
                known_files.add(resolved)
    if archive_dir is not None:
        for photo in photo_files:
            if photo.exists and photo.relative_path:
                known_files.add(archive_dir / photo.relative_path)

    other_bytes = 0
    other_file_count = 0
    extension_breakdown: dict[str, int] = {}
    if request.include_other_files:
        other_bytes, other_file_count, extension_breakdown = _scan_other_files(
            archive_dir,
            known_files=known_files,
            include_extension_breakdown=request.include_extension_breakdown,
            max_other_entries=request.max_other_entries,
        )

    files_missing_count = photo_missing
    for info in (file_info, thumbnail_info, source_info, timelapse_info, f3d_info):
        if info.relative_path and not info.exists:
            files_missing_count += 1

    total_bytes = (
        file_info.bytes
        + thumbnail_info.bytes
        + source_info.bytes
        + timelapse_info.bytes
        + f3d_info.bytes
        + photo_bytes
        + other_bytes
    )

    explicit_exists = any(
        info.exists for info in (file_info, thumbnail_info, source_info, timelapse_info, f3d_info)
    ) or bool(photo_bytes > 0)

    if total_bytes <= 0 and not explicit_exists:
        scan_status = "missing"
    elif archive_dir is None and (photo_names or request.include_other_files):
        scan_status = "partial"
    elif files_missing_count > 0:
        scan_status = "partial"
    else:
        scan_status = "complete"

    computed_at = _utc_now_iso()
    scan_duration_ms = round((datetime.now(UTC) - started_at).total_seconds() * 1000, 1)

    return ArchiveStorageScanResponse(
        archive_id=request.archive_id,
        scan_status=scan_status,
        scan_basis="sqlite+filesystem",
        base_dir=str(base_dir),
        resolved_archive_dir=str(archive_dir) if archive_dir is not None else "",
        metrics=ArchiveStorageMetrics(
            total_bytes=total_bytes,
            archive_3mf_bytes=file_info.bytes,
            thumbnail_bytes=thumbnail_info.bytes,
            source_3mf_bytes=source_info.bytes,
            timelapse_bytes=timelapse_info.bytes,
            f3d_bytes=f3d_info.bytes,
            photo_bytes=photo_bytes,
            photo_count=sum(1 for item in photo_files if item.exists),
            other_bytes=other_bytes,
            other_file_count=other_file_count,
            files_missing_count=files_missing_count,
        ),
        artifacts=ArchiveStorageArtifactSet(
            file_path=file_info,
            thumbnail_path=thumbnail_info,
            source_3mf_path=source_info,
            timelapse_path=timelapse_info,
            f3d_path=f3d_info,
            photos=photo_files,
        ),
        extension_breakdown=extension_breakdown,
        source_snapshot_hash=_source_snapshot_hash(archive_row),
        computed_at=computed_at,
        scan_duration_ms=scan_duration_ms,
    )


def scan_archive_storage_batch(db_path: Path, request: ArchiveStorageScanBatchRequest) -> ArchiveStorageScanBatchResponse:
    results: list[ArchiveStorageScanResponse] = []
    errors: list[dict[str, Any]] = []
    normalized_ids = []
    seen: set[int] = set()
    for archive_id in request.archive_ids:
        value = int(archive_id)
        if value > 0 and value not in seen:
            seen.add(value)
            normalized_ids.append(value)

    for archive_id in normalized_ids[: request.max_archives]:
        try:
            results.append(
                scan_archive_storage(
                    db_path,
                    ArchiveStorageScanRequest(
                        archive_id=archive_id,
                        force=request.force,
                        include_other_files=request.include_other_files,
                        include_extension_breakdown=request.include_extension_breakdown,
                        max_other_entries=request.max_other_entries,
                    ),
                )
            )
        except (FileNotFoundError, ValueError) as exc:
            errors.append({"archive_id": archive_id, "error": str(exc)})

    return ArchiveStorageScanBatchResponse(
        requested_count=len(normalized_ids),
        completed_count=len(results),
        failed_count=len(errors),
        results=results,
        errors=errors,
        computed_at=_utc_now_iso(),
    )


def summarize_archive_storage(db_path: Path) -> ArchiveStorageSummaryResponse:
    ensure_database_exists(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT id FROM print_archives ORDER BY id ASC").fetchall()
    batch = scan_archive_storage_batch(
        db_path,
        ArchiveStorageScanBatchRequest(
            archive_ids=[int(row["id"]) for row in rows],
            include_other_files=True,
            include_extension_breakdown=False,
            max_archives=max(1, len(rows)),
        ),
    )
    totals = ArchiveStorageMetrics()
    for item in batch.results:
        totals.total_bytes += item.metrics.total_bytes
        totals.archive_3mf_bytes += item.metrics.archive_3mf_bytes
        totals.thumbnail_bytes += item.metrics.thumbnail_bytes
        totals.source_3mf_bytes += item.metrics.source_3mf_bytes
        totals.timelapse_bytes += item.metrics.timelapse_bytes
        totals.f3d_bytes += item.metrics.f3d_bytes
        totals.photo_bytes += item.metrics.photo_bytes
        totals.photo_count += item.metrics.photo_count
        totals.other_bytes += item.metrics.other_bytes
        totals.other_file_count += item.metrics.other_file_count
        totals.files_missing_count += item.metrics.files_missing_count
    return ArchiveStorageSummaryResponse(
        archive_count=len(batch.results),
        failed_count=batch.failed_count,
        totals=totals,
        computed_at=batch.computed_at,
    )