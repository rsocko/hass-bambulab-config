from __future__ import annotations

import fnmatch
import hashlib
import json
import mimetypes
import os
import sqlite3
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.models import (
    FieldGroup,
    RestoreAction,
    RestoreFieldAction,
    RestoreFieldActionSummary,
    RestoreFromRequest,
    RestoreFromResponse,
    RestoreReason,
    RestoreVerifyRequest,
    RestoreVerifyResponse,
)
from tools.bambuddy.runtime_repair_core import ensure_database_exists


@dataclass(frozen=True)
class FieldRule:
    path: str
    group: FieldGroup | str
    policy: str


FIELD_RULES: tuple[FieldRule, ...] = (
    FieldRule("started_at", FieldGroup.RUNTIME, "copy_source"),
    FieldRule("completed_at", FieldGroup.RUNTIME, "copy_source"),
    FieldRule("created_at", FieldGroup.RUNTIME, "copy_source"),
    FieldRule("status", FieldGroup.RUNTIME, "copy_source"),
    FieldRule("failure_reason", FieldGroup.RUNTIME, "copy_source"),
    FieldRule("is_favorite", FieldGroup.USER_METADATA, "copy_source"),
    FieldRule("cost", FieldGroup.USER_METADATA, "copy_source"),
    FieldRule("quantity", FieldGroup.USER_METADATA, "copy_source"),
    FieldRule("external_url", FieldGroup.USER_METADATA, "copy_source"),
    FieldRule("tags", FieldGroup.USER_METADATA, "merge_tags"),
    FieldRule("photos", FieldGroup.ASSET_STATE, "merge_photos"),
    FieldRule("notes", FieldGroup.LINEAGE, "merge_notes"),
    FieldRule("extra_data", FieldGroup.SNAPSHOT_SUBSET, "merge_extra_data"),
    FieldRule("file_path", "parser_target", "keep_target"),
    FieldRule("file_size", "parser_target", "keep_target"),
    FieldRule("content_hash", "parser_target", "keep_target"),
    FieldRule("thumbnail_path", "parser_target", "keep_target"),
    FieldRule("print_name", "parser_target", "keep_target"),
    FieldRule("print_time_seconds", "parser_target", "keep_target"),
    FieldRule("filament_used_grams", "parser_target", "keep_target"),
    FieldRule("filament_type", "parser_target", "keep_target"),
    FieldRule("filament_color", "parser_target", "keep_target"),
    FieldRule("layer_height", "parser_target", "keep_target"),
    FieldRule("total_layers", "parser_target", "keep_target"),
    FieldRule("nozzle_diameter", "parser_target", "keep_target"),
    FieldRule("nozzle_temperature", "parser_target", "keep_target"),
    FieldRule("sliced_for_model", "parser_target", "keep_target"),
    FieldRule("designer", "parser_target", "keep_target"),
    FieldRule("makerworld_url", "parser_target", "keep_target"),
)


def _parse_extra_data(value: Any) -> Any:
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value


def _media_root_from_db_path(db_path: Path) -> Path:
    return db_path.parent


def _resolve_media_path(media_root: Path, stored_path: str) -> Path:
    candidate = (media_root / stored_path).resolve()
    try:
        candidate.relative_to(media_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Media path escapes configured media root: {stored_path}") from exc
    return candidate


def _hash_file(file_path: Path) -> str | None:
    if not file_path.is_file():
        return None

    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_bytes(payload: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(payload)
    return digest.hexdigest()


def _optional_bambuddy_api_base_url() -> str | None:
    value = os.environ.get("BAMBUDDY_API_BASE_URL", "").strip().rstrip("/")
    return value or None


def _optional_bambuddy_api_key() -> str | None:
    value = os.environ.get("BAMBUDDY_API_KEY", "").strip()
    return value or None


def _optional_home_assistant_base_url() -> str | None:
    value = os.environ.get("HOME_ASSISTANT_BASE_URL", "").strip().rstrip("/")
    return value or None


def _optional_home_assistant_token() -> str | None:
    value = os.environ.get("HOME_ASSISTANT_TOKEN", "").strip()
    return value or None


def _read_url_bytes(url: str, headers: Mapping[str, str] | None = None) -> bytes:
    request = urllib.request.Request(
        url=url,
        method="GET",
        headers=dict(headers or {}),
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _archive_photo_download_url(archive_id: int, photo_path: str) -> str | None:
    base_url = _optional_bambuddy_api_base_url()
    if not base_url:
        return None
    file_name = Path(photo_path).name.strip()
    if not file_name:
        return None
    return f"{base_url}/api/v1/archives/{archive_id}/photos/{urllib.parse.quote(file_name)}"


def _extract_archive_detail_photos(archive: Mapping[str, Any]) -> list[dict[str, str]]:
    raw_photos = archive.get("photos")
    if not isinstance(raw_photos, list):
        return []

    photos: list[dict[str, str]] = []
    for item in raw_photos:
        if isinstance(item, str):
            path = item.strip()
            role = ""
        elif isinstance(item, Mapping):
            path = str(item.get("path") or item.get("url") or item.get("photo_path") or "").strip()
            role = str(item.get("role") or item.get("type") or "").strip()
        else:
            path = ""
            role = ""

        if path:
            photos.append({"path": path, "role": role})

    return photos


def _fetch_archive_detail(archive_id: int) -> dict[str, Any] | None:
    base_url = _optional_bambuddy_api_base_url()
    api_key = _optional_bambuddy_api_key()
    if not base_url or not api_key:
        return None

    payload = json.loads(
        _read_url_bytes(
            f"{base_url}/api/v1/archives/{archive_id}",
            headers={"X-API-Key": api_key},
        ).decode("utf-8")
    )
    if not isinstance(payload, dict):
        raise ValueError(f"Archive detail response for {archive_id} was not a JSON object")
    return payload


def _load_api_archive_photos(
    archive_id: int,
    media_root: Path | None = None,
) -> list[dict[str, Any]]:
    archive_detail = _fetch_archive_detail(archive_id)
    if archive_detail is None:
        return []

    photos: list[dict[str, Any]] = []
    for photo_index, photo in enumerate(_extract_archive_detail_photos(archive_detail)):
        photo_path = photo["path"]
        photo_role = photo["role"]
        entry: dict[str, Any] = {
            "photo_index": photo_index,
            "photo_path": photo_path,
            "photo_role": photo_role,
        }

        if media_root is not None and ("/" in photo_path or "\\" in photo_path):
            resolved_path = _resolve_media_path(media_root, photo_path)
            entry["resolved_path"] = str(resolved_path)
            entry["file_exists"] = resolved_path.is_file()
            entry["file_hash"] = _hash_file(resolved_path)

        download_url = _archive_photo_download_url(archive_id, photo_path)
        if download_url:
            entry["download_url"] = download_url
            if not entry.get("file_hash"):
                try:
                    entry["file_hash"] = _hash_bytes(_read_url_bytes(download_url))
                    entry["file_exists"] = True
                except Exception:
                    entry.setdefault("file_exists", False)

        photos.append(entry)

    return photos


def _build_photo_entry(
    media_root: Path | None,
    photo_index: int,
    photo_path: str,
    photo_role: str,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "photo_index": photo_index,
        "photo_path": photo_path,
        "photo_role": photo_role,
    }

    if media_root is None:
        return entry

    resolved_path = _resolve_media_path(media_root, photo_path)
    entry["resolved_path"] = str(resolved_path)
    entry["file_exists"] = resolved_path.is_file()
    entry["file_hash"] = _hash_file(resolved_path)
    return entry


def _load_archive_photos(
    connection: sqlite3.Connection,
    archive_id: int,
    media_root: Path | None = None,
) -> list[dict[str, Any]]:
    table_exists = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'archive_photos'"
    ).fetchone()
    if table_exists is None:
        return []

    rows = connection.execute(
        """
        SELECT photo_index, photo_path, photo_role
        FROM archive_photos
        WHERE archive_id = ?
        ORDER BY photo_index ASC
        """,
        (archive_id,),
    ).fetchall()

    return [
        _build_photo_entry(media_root, row["photo_index"], row["photo_path"], row["photo_role"] or "")
        for row in rows
        if row["photo_path"]
    ]


def load_archive_snapshot(
    connection: sqlite3.Connection,
    archive_id: int,
    media_root: Path | None = None,
) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM print_archives WHERE id = ?", (archive_id,)).fetchone()
    if row is None:
        raise ValueError(f"Archive ID {archive_id} not found")

    snapshot = {key: row[key] for key in row.keys()}
    snapshot["extra_data"] = _parse_extra_data(snapshot.get("extra_data"))
    db_photos = _load_archive_photos(connection, archive_id, media_root)
    api_photos = _load_api_archive_photos(archive_id, media_root) if not db_photos else []
    snapshot["photos"] = merge_photos(db_photos, api_photos)
    if "is_favorite" in snapshot and snapshot["is_favorite"] is not None:
        snapshot["is_favorite"] = bool(snapshot["is_favorite"])
    return snapshot


def _get_path_value(data: Mapping[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _normalize_value(path: str, value: Any) -> Any:
    if path == "tags":
        if value is None:
            return []
        return sorted({token.strip().lower() for token in str(value).split(",") if token.strip()})
    if path == "photos":
        return [
            {
                "photo_path": str(item.get("photo_path") or "").strip(),
                "photo_role": str(item.get("photo_role") or "").strip(),
                "file_hash": item.get("file_hash"),
                "file_exists": bool(item.get("file_exists")),
                "resolved_path": item.get("resolved_path"),
                "download_url": item.get("download_url"),
            }
            for item in (value or [])
            if isinstance(item, Mapping) and str(item.get("photo_path") or "").strip()
        ]
    if isinstance(value, str):
        return value.strip()
    return value


def _split_tags(value: Any) -> list[str]:
    if value is None:
        return []
    return [token.strip() for token in str(value).split(",") if token.strip()]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value.strip())
    return result


def merge_tags(source_value: Any, target_value: Any, exclude_patterns: list[str], include_tags: list[str]) -> str | None:
    source_tags = _split_tags(source_value)
    target_tags = _split_tags(target_value)
    include_set = {tag.strip().lower() for tag in include_tags if tag.strip()}

    def allowed_source_tag(tag: str) -> bool:
        lowered = tag.strip().lower()
        if include_set and lowered not in include_set:
            return False
        return not any(fnmatch.fnmatch(lowered, pattern.strip().lower()) for pattern in exclude_patterns)

    merged = _dedupe_preserve_order(target_tags + [tag for tag in source_tags if allowed_source_tag(tag)])
    return ",".join(merged) if merged else None


def _split_note_segments(value: str | None) -> tuple[list[str], list[str]]:
    if not value:
        return [], []

    plain_segments: list[str] = []
    structured_segments: list[str] = []
    for segment in [part.strip() for part in value.split("\n\n") if part.strip()]:
        if (segment.startswith("[") and "]" in segment) or segment.startswith("+>"):
            structured_segments.append(segment)
        else:
            plain_segments.append(segment)
    return plain_segments, structured_segments


def merge_notes(source_value: Any, target_value: Any) -> str | None:
    source_plain, source_structured = _split_note_segments(str(source_value) if source_value is not None else None)
    target_plain, target_structured = _split_note_segments(str(target_value) if target_value is not None else None)

    merged_plain = _dedupe_preserve_order(target_plain + source_plain)

    # Preserve target structured blocks. Do not blindly copy source fallback audit blocks
    # onto the recovered target archive.
    merged_structured = _dedupe_preserve_order(target_structured)

    merged_segments = merged_plain + merged_structured
    return "\n\n".join(merged_segments) if merged_segments else None


def _deep_fill_missing(target_value: Any, source_value: Any) -> Any:
    if isinstance(target_value, Mapping) and isinstance(source_value, Mapping):
        result = {key: value for key, value in target_value.items()}
        for key, source_item in source_value.items():
            if key in result:
                result[key] = _deep_fill_missing(result[key], source_item)
            else:
                result[key] = source_item
        return result

    if _is_missing(target_value):
        return source_value

    return target_value


def merge_extra_data(source_value: Any, target_value: Any) -> dict[str, Any]:
    source_mapping = source_value if isinstance(source_value, Mapping) else {}
    target_mapping = target_value if isinstance(target_value, Mapping) else {}
    merged = _deep_fill_missing(target_mapping, source_mapping)
    return dict(merged) if isinstance(merged, Mapping) else {}


def merge_photos(source_value: Any, target_value: Any) -> list[dict[str, Any]]:
    source_photos = _normalize_value("photos", source_value)
    target_photos = _normalize_value("photos", target_value)

    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in target_photos + source_photos:
        key = _photo_signature(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _photo_signature(photo: Mapping[str, Any]) -> tuple[str, str]:
    file_hash = str(photo.get("file_hash") or "").strip().lower()
    role = str(photo.get("photo_role") or "").strip().lower()
    if file_hash:
        return (f"hash:{file_hash}", role)
    return (f"path:{str(photo.get('photo_path') or '').strip().lower()}", role)


def _photos_to_upload(source_value: Any, target_value: Any) -> list[dict[str, Any]]:
    source_photos = _normalize_value("photos", source_value)
    target_photos = _normalize_value("photos", target_value)
    target_signatures = {_photo_signature(photo) for photo in target_photos}
    return [photo for photo in source_photos if _photo_signature(photo) not in target_signatures]


def _extract_enrichment_payload(notes_value: Any) -> dict[str, Any] | None:
    notes = str(notes_value or "")
    marker_index = notes.find("+>")
    if marker_index < 0:
        return None

    payload_raw = notes[marker_index + 2 :].strip()
    if not payload_raw:
        return None

    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        return None

    return payload if isinstance(payload, dict) else None


def _enrichment_status_label(notes_value: Any) -> str:
    payload = _extract_enrichment_payload(notes_value)
    if not payload:
        return "missing"

    code = str(payload.get("s") or "").strip().lower()
    return {
        "c": "complete",
        "p": "partial",
        "u": "unavailable",
    }.get(code, "missing")


def _enrichment_ready(notes_value: Any) -> bool:
    return _enrichment_status_label(notes_value) == "complete"


def _invoke_home_assistant_reenrich(archive_id: int) -> tuple[bool, str | None]:
    base_url = _optional_home_assistant_base_url()
    token = _optional_home_assistant_token()
    if not base_url or not token:
        return False, "run_reenrich requested but HOME_ASSISTANT_BASE_URL/HOME_ASSISTANT_TOKEN are not configured"

    request = urllib.request.Request(
        url=f"{base_url}/api/services/script/reenrich_print_history_archive",
        data=json.dumps({"archive_id": str(archive_id)}).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = getattr(response, "status", 200)
            if not (200 <= status < 300):
                return False, f"run_reenrich requested but Home Assistant returned HTTP {status}"
    except Exception as exc:
        return False, f"run_reenrich requested but Home Assistant call failed: {exc}"

    return True, None


def _bambuddy_api_base_url() -> str:
    value = _optional_bambuddy_api_base_url()
    if not value:
        raise ValueError("BAMBUDDY_API_BASE_URL is required for photo migration")
    return value


def _bambuddy_api_key() -> str:
    value = _optional_bambuddy_api_key()
    if not value:
        raise ValueError("BAMBUDDY_API_KEY is required for photo migration")
    return value


def _photo_file_name(source_photo: Mapping[str, Any]) -> str:
    file_name = Path(str(source_photo.get("photo_path") or "").strip()).name
    if file_name:
        return file_name
    raise ValueError("Photo file name could not be determined for upload")


def _read_source_photo_bytes(source_photo: Mapping[str, Any]) -> bytes:
    resolved_path_value = str(source_photo.get("resolved_path") or "").strip()
    if resolved_path_value:
        source_path = Path(resolved_path_value)
        if not source_path.is_file():
            raise ValueError(f"Photo file not found for upload: {source_path}")
        return source_path.read_bytes()

    download_url = str(source_photo.get("download_url") or "").strip()
    if download_url:
        return _read_url_bytes(download_url)

    raise ValueError(f"Photo missing resolved_path/download_url for upload: {source_photo.get('photo_path')}")


def _upload_archive_photo(target_archive_id: int, source_photo: Mapping[str, Any]) -> None:
    file_name = _photo_file_name(source_photo)
    content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    boundary = "----bambuddy-restore-" + uuid.uuid4().hex
    file_bytes = _read_source_photo_bytes(source_photo)
    body = (
        f"--{boundary}\r\n".encode()
        + f"Content-Disposition: form-data; name=\"file\"; filename=\"{file_name}\"\r\n".encode()
        + f"Content-Type: {content_type}\r\n\r\n".encode()
        + file_bytes
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = urllib.request.Request(
        url=f"{_bambuddy_api_base_url()}/api/v1/archives/{target_archive_id}/photos",
        data=body,
        method="POST",
        headers={
            "X-API-Key": _bambuddy_api_key(),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        status = getattr(response, "status", 200)
        if not (200 <= status < 300):
            raise ValueError(f"Photo upload failed with HTTP {status} for {file_name}")


def _normalized_action_value(field: str, value: Any) -> Any:
    return _normalize_value(field, value)


def _has_file_backed_signal(archive: Mapping[str, Any]) -> bool:
    return bool(archive.get("file_path") or archive.get("content_hash") or archive.get("thumbnail_path"))


def _warnings_for_restore(source_archive: Mapping[str, Any], target_archive: Mapping[str, Any], request: RestoreFromRequest) -> list[str]:
    warnings: list[str] = []
    if _get_path_value(source_archive, "extra_data.no_3mf_available") is True:
        warnings.append("source archive is incomplete and contains no_3mf_available=true")
    if not _has_file_backed_signal(target_archive):
        warnings.append("target archive does not appear to have file-backed recovery signals")

    requested_runtime_fields = ["started_at", "completed_at", "created_at", "status"]
    if FieldGroup.RUNTIME in request.field_groups and all(_is_missing(source_archive.get(field)) for field in requested_runtime_fields):
        warnings.append("source archive is missing all requested runtime fields")

    if source_archive.get("print_name") and target_archive.get("print_name") and source_archive.get("print_name") != target_archive.get("print_name"):
        warnings.append("source and target print_name differ; target parser-derived metadata will be preserved")
    return warnings


def _summarize(actions: list[RestoreFieldAction]) -> RestoreFieldActionSummary:
    summary = RestoreFieldActionSummary()
    for action in actions:
        attribute_name = f"{action.action.value}_count"
        current = getattr(summary, attribute_name)
        setattr(summary, attribute_name, current + 1)
    return summary


def _is_actionable_remaining_difference(action: RestoreFieldAction) -> bool:
    if action.action not in {RestoreAction.COPY, RestoreAction.MERGE, RestoreAction.OVERRIDE}:
        return False

    before = _normalized_action_value(action.field, action.target_before)
    after = _normalized_action_value(action.field, action.target_after)
    return before != after


def _is_non_blocking_difference(action: RestoreFieldAction) -> bool:
    return action.action in {
        RestoreAction.KEEP_TARGET,
        RestoreAction.SKIP_EQUAL,
        RestoreAction.SKIP_MISSING_SOURCE,
        RestoreAction.SKIP_DISALLOWED,
    }


def _delete_archive_row(connection: sqlite3.Connection, archive_id: int) -> None:
    deleted = connection.execute("DELETE FROM print_archives WHERE id = ?", (archive_id,))
    if deleted.rowcount == 0:
        raise ValueError(f"Archive ID {archive_id} not found for deletion")


def _apply_restore_actions(
    connection: sqlite3.Connection,
    archive_id: int,
    actions: list[RestoreFieldAction],
) -> tuple[list[str], list[str]]:
    scalar_updates: dict[str, Any] = {}
    updated_fields: list[str] = []
    photo_uploads: list[dict[str, Any]] = []
    warnings: list[str] = []
    uploaded_photo_count = 0

    for action in actions:
        if action.action not in {RestoreAction.COPY, RestoreAction.MERGE, RestoreAction.OVERRIDE}:
            continue
        if action.target_before == action.target_after:
            continue
        if action.field == "photos":
            photo_uploads = _photos_to_upload(action.source_value, action.target_before)
            continue
        if "." in action.field:
            continue
        scalar_updates[action.field] = (
            json.dumps(action.target_after, separators=(",", ":"))
            if action.field == "extra_data"
            else action.target_after
        )

    for photo in photo_uploads:
        try:
            _upload_archive_photo(archive_id, photo)
            uploaded_photo_count += 1
        except Exception as exc:
            photo_name = str(photo.get("photo_path") or "<unknown>").strip() or "<unknown>"
            warnings.append(f"skipped source photo '{photo_name}' during restore: {exc}")

    if scalar_updates:
        assignments = ", ".join(f"{field} = ?" for field in scalar_updates)
        values = list(scalar_updates.values())
        values.append(archive_id)
        connection.execute(f"UPDATE print_archives SET {assignments} WHERE id = ?", values)
        updated_fields.extend(sorted(scalar_updates.keys()))

    if uploaded_photo_count:
        updated_fields.append("photos")

    return updated_fields, warnings


def build_restore_field_actions(
    source_archive: Mapping[str, Any],
    target_archive: Mapping[str, Any],
    request: RestoreFromRequest,
) -> list[RestoreFieldAction]:
    """Build a dry-run field action list for restore_from planning.

    This is intentionally a planning skeleton only. It encodes the current merge
    policy categories and can be expanded into the eventual DB-backed merge path.
    """

    actions: list[RestoreFieldAction] = []
    override_values = request.overrides.model_dump(exclude_none=True)

    for rule in FIELD_RULES:
        if (
            isinstance(rule.group, FieldGroup)
            and rule.group not in request.field_groups
            and rule.policy != "disallowed"
        ):
            continue

        source_value = _get_path_value(source_archive, rule.path)
        target_value = _get_path_value(target_archive, rule.path)

        if rule.path in override_values:
            actions.append(
                RestoreFieldAction(
                    field=rule.path,
                    group=str(rule.group),
                    action=RestoreAction.OVERRIDE,
                    source_value=source_value,
                    target_before=target_value,
                    target_after=override_values[rule.path],
                    reason=RestoreReason.EXPLICIT_OVERRIDE,
                )
            )
            continue

        if rule.policy == "disallowed":
            actions.append(
                RestoreFieldAction(
                    field=rule.path,
                    group=str(rule.group),
                    action=RestoreAction.SKIP_DISALLOWED,
                    source_value=source_value,
                    target_before=target_value,
                    target_after=target_value,
                    reason=RestoreReason.FALLBACK_MARKER_MUST_NOT_BE_COPIED
                    if rule.path == "extra_data.no_3mf_available"
                    else RestoreReason.TRANSIENT_SNAPSHOT_NOT_SUPPORTED,
                )
            )
            continue

        if rule.policy == "keep_target":
            actions.append(
                RestoreFieldAction(
                    field=rule.path,
                    group=str(rule.group),
                    action=RestoreAction.KEEP_TARGET,
                    source_value=source_value,
                    target_before=target_value,
                    target_after=target_value,
                    reason=RestoreReason.TARGET_PARSER_FIELD_HAS_PRIORITY,
                )
            )
            continue

        normalized_source = _normalize_value(rule.path, source_value)
        normalized_target = _normalize_value(rule.path, target_value)

        if _is_missing(normalized_source):
            actions.append(
                RestoreFieldAction(
                    field=rule.path,
                    group=str(rule.group),
                    action=RestoreAction.SKIP_MISSING_SOURCE,
                    source_value=source_value,
                    target_before=target_value,
                    target_after=target_value,
                    reason=RestoreReason.SOURCE_MISSING,
                )
            )
            continue

        if normalized_source == normalized_target:
            actions.append(
                RestoreFieldAction(
                    field=rule.path,
                    group=str(rule.group),
                    action=RestoreAction.SKIP_EQUAL,
                    source_value=source_value,
                    target_before=target_value,
                    target_after=target_value,
                    reason=RestoreReason.NORMALIZED_VALUES_EQUAL,
                )
            )
            continue

        if rule.policy == "copy_source":
            actions.append(
                RestoreFieldAction(
                    field=rule.path,
                    group=str(rule.group),
                    action=RestoreAction.COPY,
                    source_value=source_value,
                    target_before=target_value,
                    target_after=source_value,
                    reason=RestoreReason.RUNTIME_TRUTH_PRESENT_ON_SOURCE,
                )
            )
            continue

        if rule.policy == "merge_tags":
            merged_tags = merge_tags(
                source_value,
                target_value,
                request.exclude_tags,
                request.include_tags,
            )
            actions.append(
                RestoreFieldAction(
                    field=rule.path,
                    group=str(rule.group),
                    action=RestoreAction.MERGE,
                    source_value=source_value,
                    target_before=target_value,
                    target_after=merged_tags,
                    reason=RestoreReason.MERGED_TAG_POLICY,
                )
            )
            continue

        if rule.policy == "merge_notes":
            merged_note_text = merge_notes(source_value, target_value)
            actions.append(
                RestoreFieldAction(
                    field=rule.path,
                    group=str(rule.group),
                    action=RestoreAction.MERGE,
                    source_value=source_value,
                    target_before=target_value,
                    target_after=merged_note_text,
                    reason=RestoreReason.MERGED_NOTES_POLICY,
                )
            )
            continue

        if rule.policy == "merge_extra_data":
            merged_extra_data = merge_extra_data(source_value, target_value)
            actions.append(
                RestoreFieldAction(
                    field=rule.path,
                    group=str(rule.group),
                    action=RestoreAction.MERGE,
                    source_value=source_value,
                    target_before=target_value,
                    target_after=merged_extra_data,
                    reason=RestoreReason.MERGED_EXTRA_DATA_POLICY,
                )
            )
            continue

        if rule.policy == "merge_photos":
            merged_photo_list = merge_photos(source_value, target_value)
            actions.append(
                RestoreFieldAction(
                    field=rule.path,
                    group=str(rule.group),
                    action=RestoreAction.MERGE,
                    source_value=source_value,
                    target_before=target_value,
                    target_after=merged_photo_list,
                    reason=RestoreReason.MERGED_PHOTOS_POLICY,
                )
            )
            continue

        actions.append(
            RestoreFieldAction(
                field=rule.path,
                group=str(rule.group),
                action=RestoreAction.SKIP_DISALLOWED,
                source_value=source_value,
                target_before=target_value,
                target_after=target_value,
                reason=RestoreReason.POLICY_NOT_YET_IMPLEMENTED,
            )
        )

    return actions


def build_restore_response(
    source_archive_id: int,
    target_archive_id: int,
    actions: list[RestoreFieldAction],
    warnings: list[str] | None = None,
    *,
    applied: bool,
    updated: bool,
    reenrich_requested: bool = False,
    reenrich_triggered: bool = False,
    updated_fields: list[str] | None = None,
) -> RestoreFromResponse:
    return RestoreFromResponse(
        source_archive_id=source_archive_id,
        target_archive_id=target_archive_id,
        updated=updated,
        applied=applied,
        reenrich_requested=reenrich_requested,
        reenrich_triggered=reenrich_triggered,
        field_action_summary=_summarize(actions),
        field_actions=actions,
        warnings=warnings or [],
        updated_fields=updated_fields or [],
    )


def restore_archive_from_source(db_path: Path, request: RestoreFromRequest) -> RestoreFromResponse:
    """DB-backed restore_from merge path.

    Dry-run returns the field action plan only.
    Apply mode writes actionable top-level field updates to the target archive.
    """

    ensure_database_exists(db_path)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        media_root = _media_root_from_db_path(db_path)
        source_archive = load_archive_snapshot(connection, request.source_archive_id, media_root)
        target_archive = load_archive_snapshot(connection, request.target_archive_id, media_root)
        actions = build_restore_field_actions(source_archive, target_archive, request)
        warnings = _warnings_for_restore(source_archive, target_archive, request)

        if request.dry_run:
            return build_restore_response(
                source_archive_id=request.source_archive_id,
                target_archive_id=request.target_archive_id,
                actions=actions,
                warnings=warnings,
                applied=False,
                updated=False,
                reenrich_requested=request.run_reenrich,
                reenrich_triggered=False,
                updated_fields=[],
            )

        updated_fields, apply_warnings = _apply_restore_actions(connection, request.target_archive_id, actions)
        connection.commit()
        warnings.extend(apply_warnings)
        reenrich_triggered = False
        if request.run_reenrich:
            reenrich_triggered, reenrich_warning = _invoke_home_assistant_reenrich(request.target_archive_id)
            if reenrich_warning:
                warnings.append(reenrich_warning)
        return build_restore_response(
            source_archive_id=request.source_archive_id,
            target_archive_id=request.target_archive_id,
            actions=actions,
            warnings=warnings,
            applied=True,
            updated=bool(updated_fields),
            reenrich_requested=request.run_reenrich,
            reenrich_triggered=reenrich_triggered,
            updated_fields=updated_fields,
        )
    finally:
        connection.close()


def restore_verify_after_merge(db_path: Path, request: RestoreVerifyRequest) -> RestoreVerifyResponse:
    ensure_database_exists(db_path)

    verification_request = RestoreFromRequest(
        source_archive_id=request.source_archive_id,
        target_archive_id=request.target_archive_id,
        field_groups=request.field_groups,
        tag_merge_mode=request.tag_merge_mode,
        notes_merge_mode=request.notes_merge_mode,
        preserve_target_parser_fields=request.preserve_target_parser_fields,
        copy_source_snapshot_subset=request.copy_source_snapshot_subset,
        exclude_tags=request.exclude_tags,
        include_tags=request.include_tags,
        dry_run=True,
    )

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        media_root = _media_root_from_db_path(db_path)
        source_archive = load_archive_snapshot(connection, request.source_archive_id, media_root)
        target_archive = load_archive_snapshot(connection, request.target_archive_id, media_root)
        warnings = _warnings_for_restore(source_archive, target_archive, verification_request)
        actions = build_restore_field_actions(source_archive, target_archive, verification_request)
        remaining_differences = [action for action in actions if _is_actionable_remaining_difference(action)]
        non_blocking_differences = [action for action in actions if _is_non_blocking_difference(action)]
        verified = not remaining_differences
        enrichment_status = _enrichment_status_label(target_archive.get("notes"))
        enrichment_ready = _enrichment_ready(target_archive.get("notes"))
        if not enrichment_ready:
            warnings.append(
                "target archive enrichment is not complete; run re-enrich before removing the original archive or use force_remove_without_reenrich=true"
            )
        removable = verified and (enrichment_ready or request.force_remove_without_reenrich)
        source_removed = False

        if request.remove_original and not verified:
            warnings.append("original archive cannot be removed while actionable differences remain")

        if request.remove_original and verified and not enrichment_ready and not request.force_remove_without_reenrich:
            warnings.append("original archive cannot be removed until enrichment is complete")

        if request.remove_original and verified and not enrichment_ready and request.force_remove_without_reenrich:
            warnings.append("original archive removal forced even though enrichment is not complete")

        if request.remove_original and verified and (enrichment_ready or request.force_remove_without_reenrich) and not request.dry_run:
            _delete_archive_row(connection, request.source_archive_id)
            connection.commit()
            source_removed = True

        return RestoreVerifyResponse(
            source_archive_id=request.source_archive_id,
            target_archive_id=request.target_archive_id,
            verified=verified,
            applied=bool(request.remove_original and not request.dry_run and source_removed),
            removable=removable,
            source_removed=source_removed,
            enrichment_status=enrichment_status,
            enrichment_ready=enrichment_ready,
            blocking_difference_count=len(remaining_differences),
            non_blocking_difference_count=len(non_blocking_differences),
            remaining_difference_count=len(remaining_differences),
            remaining_difference_summary=_summarize(remaining_differences),
            remaining_differences=remaining_differences,
            blocking_differences=remaining_differences,
            non_blocking_differences=non_blocking_differences,
            warnings=warnings,
        )
    finally:
        connection.close()
