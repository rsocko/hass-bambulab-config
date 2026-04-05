from __future__ import annotations

import fnmatch
import json
import sqlite3
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
    FieldRule("notes", FieldGroup.LINEAGE, "merge_notes"),
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
    FieldRule("extra_data.no_3mf_available", FieldGroup.SNAPSHOT_SUBSET, "disallowed"),
    FieldRule("extra_data._print_data", FieldGroup.SNAPSHOT_SUBSET, "disallowed"),
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


def load_archive_snapshot(connection: sqlite3.Connection, archive_id: int) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM print_archives WHERE id = ?", (archive_id,)).fetchone()
    if row is None:
        raise ValueError(f"Archive ID {archive_id} not found")

    snapshot = {key: row[key] for key in row.keys()}
    snapshot["extra_data"] = _parse_extra_data(snapshot.get("extra_data"))
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
) -> list[str]:
    scalar_updates: dict[str, Any] = {}
    updated_fields: list[str] = []

    for action in actions:
        if action.action not in {RestoreAction.COPY, RestoreAction.MERGE, RestoreAction.OVERRIDE}:
            continue
        if action.target_before == action.target_after:
            continue
        if "." in action.field:
            continue
        scalar_updates[action.field] = action.target_after

    if scalar_updates:
        assignments = ", ".join(f"{field} = ?" for field in scalar_updates)
        values = list(scalar_updates.values())
        values.append(archive_id)
        connection.execute(f"UPDATE print_archives SET {assignments} WHERE id = ?", values)
        updated_fields.extend(sorted(scalar_updates.keys()))

    return updated_fields


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
    updated_fields: list[str] | None = None,
) -> RestoreFromResponse:
    return RestoreFromResponse(
        source_archive_id=source_archive_id,
        target_archive_id=target_archive_id,
        updated=updated,
        applied=applied,
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
        source_archive = load_archive_snapshot(connection, request.source_archive_id)
        target_archive = load_archive_snapshot(connection, request.target_archive_id)
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
                updated_fields=[],
            )

        updated_fields = _apply_restore_actions(connection, request.target_archive_id, actions)
        connection.commit()
        return build_restore_response(
            source_archive_id=request.source_archive_id,
            target_archive_id=request.target_archive_id,
            actions=actions,
            warnings=warnings,
            applied=True,
            updated=bool(updated_fields),
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
        source_archive = load_archive_snapshot(connection, request.source_archive_id)
        target_archive = load_archive_snapshot(connection, request.target_archive_id)
        warnings = _warnings_for_restore(source_archive, target_archive, verification_request)
        actions = build_restore_field_actions(source_archive, target_archive, verification_request)
        remaining_differences = [action for action in actions if _is_actionable_remaining_difference(action)]
        non_blocking_differences = [action for action in actions if _is_non_blocking_difference(action)]
        verified = not remaining_differences
        removable = verified
        source_removed = False

        if request.remove_original and not verified:
            warnings.append("original archive cannot be removed while actionable differences remain")

        if request.remove_original and verified and not request.dry_run:
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
