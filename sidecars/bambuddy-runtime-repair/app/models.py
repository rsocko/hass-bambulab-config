from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FieldGroup(StrEnum):
    RUNTIME = "runtime"
    USER_METADATA = "user_metadata"
    LINEAGE = "lineage"
    SNAPSHOT_SUBSET = "snapshot_subset"
    ASSET_STATE = "asset_state"


class TagMergeMode(StrEnum):
    MERGE_PRESERVE_TARGET = "merge_preserve_target"
    SOURCE_ONLY = "source_only"
    TARGET_ONLY = "target_only"


class NotesMergeMode(StrEnum):
    APPEND_STRUCTURED = "append_structured"
    TARGET_ONLY = "target_only"
    SOURCE_THEN_TARGET = "source_then_target"


class SnapshotSubset(StrEnum):
    TRAY_UUIDS = "tray_uuids"
    SOURCE_SUBTASK_NAME = "source_subtask_name"
    AMS_SLOT_SUMMARY = "ams_slot_summary"


class RestoreAction(StrEnum):
    COPY = "copy"
    MERGE = "merge"
    KEEP_TARGET = "keep_target"
    SKIP_EQUAL = "skip_equal"
    SKIP_MISSING_SOURCE = "skip_missing_source"
    SKIP_DISALLOWED = "skip_disallowed"
    OVERRIDE = "override"


class RestoreReason(StrEnum):
    RUNTIME_TRUTH_PRESENT_ON_SOURCE = "runtime_truth_present_on_source"
    SOURCE_MISSING = "source_missing"
    NORMALIZED_VALUES_EQUAL = "normalized_values_equal"
    TARGET_PARSER_FIELD_HAS_PRIORITY = "target_parser_field_has_priority"
    FALLBACK_MARKER_MUST_NOT_BE_COPIED = "fallback_marker_must_not_be_copied"
    TRANSIENT_SNAPSHOT_NOT_SUPPORTED = "transient_snapshot_not_supported"
    MERGED_TAG_POLICY = "merged_tag_policy"
    MERGED_NOTES_POLICY = "merged_notes_policy"
    MERGED_PHOTOS_POLICY = "merged_photos_policy"
    MERGED_EXTRA_DATA_POLICY = "merged_extra_data_policy"
    EXPLICIT_OVERRIDE = "explicit_override"
    POLICY_NOT_YET_IMPLEMENTED = "policy_not_yet_implemented"


class RuntimeRepairRequest(BaseModel):
    archive_id: int
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None
    status: str | None = None
    failure_reason: str | None = None
    audit_note: str | None = None
    dry_run: bool = False


class HealthResponse(BaseModel):
    status: str
    db_path: str


class ArchivePartialUsageEstimateRequest(BaseModel):
    archive_id: int
    printer_id: int | None = None
    print_status: str
    last_layer_num: int | None = None
    last_progress: float | None = None
    resolve_spoolman_matches: bool = True
    keep_tracking_row: bool = True


class ArchivePartialUsageSlotEstimate(BaseModel):
    slot_id: int
    estimated_used_g: float
    total_job_used_g: float | None = None
    global_tray_id: int | None = None
    tray_uuid: str | None = None
    tag_uid: str | None = None
    spoolman_spool_id: int | None = None
    resolution_method: str | None = None
    confidence: str


class ArchivePartialUsageEstimateResponse(BaseModel):
    archive_id: int
    printer_id: int | None = None
    print_status: str
    source_state: dict[str, Any] = Field(default_factory=dict)
    calculation: dict[str, Any] = Field(default_factory=dict)
    per_slot: list[ArchivePartialUsageSlotEstimate] = Field(default_factory=list)
    totals: dict[str, Any] = Field(default_factory=dict)
    dedupe: dict[str, Any] = Field(default_factory=dict)


class ArchivePartialUsageConsumeRequest(BaseModel):
    archive_id: int
    dedupe_key: str
    consumed_by: str
    applied_spool_ids: list[int] = Field(default_factory=list)
    applied_total_g: float | None = None
    print_status: str


class ArchivePartialUsageConsumeResponse(BaseModel):
    archive_id: int
    dedupe_key: str
    consumed: bool
    already_consumed: bool
    prior_consumer: str | None = None
    recorded_at: str


class ArchiveSpoolInspectionResponse(BaseModel):
    archive_id: int
    archive: dict[str, Any]
    table_presence: dict[str, bool] = Field(default_factory=dict)
    enrichment: dict[str, Any] = Field(default_factory=dict)
    archive_snapshot: dict[str, Any] = Field(default_factory=dict)
    native_linkage: dict[str, Any] = Field(default_factory=dict)
    comparison: dict[str, Any] = Field(default_factory=dict)
    advisories: list[str] = Field(default_factory=list)


class RuntimeRepairResponse(BaseModel):
    archive_id: int
    applied: bool
    changed: bool
    before: dict[str, Any]
    after: dict[str, Any]
    updated_fields: list[str]


class RestoreFromOverrides(BaseModel):
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None
    status: str | None = None
    failure_reason: str | None = None
    is_favorite: bool | None = None
    cost: float | None = None
    quantity: int | None = None
    external_url: str | None = None


class RestoreFromRequest(BaseModel):
    source_archive_id: int
    target_archive_id: int
    field_groups: list[FieldGroup] = Field(
        default_factory=lambda: [
            FieldGroup.RUNTIME,
            FieldGroup.USER_METADATA,
            FieldGroup.LINEAGE,
            FieldGroup.ASSET_STATE,
            FieldGroup.SNAPSHOT_SUBSET,
        ]
    )
    tag_merge_mode: TagMergeMode = TagMergeMode.MERGE_PRESERVE_TARGET
    notes_merge_mode: NotesMergeMode = NotesMergeMode.APPEND_STRUCTURED
    preserve_target_parser_fields: bool = True
    copy_source_snapshot_subset: list[SnapshotSubset] = Field(default_factory=list)
    exclude_tags: list[str] = Field(
        default_factory=lambda: ["exception:missing_3mf", "replaced_by:*"]
    )
    include_tags: list[str] = Field(default_factory=list)
    overrides: RestoreFromOverrides = Field(default_factory=RestoreFromOverrides)
    run_reenrich: bool = False
    dry_run: bool = False

    @model_validator(mode="after")
    def validate_archive_pair(self) -> "RestoreFromRequest":
        if self.source_archive_id == self.target_archive_id:
            raise ValueError("source_archive_id and target_archive_id must differ")
        return self


class RestoreFieldAction(BaseModel):
    field: str
    group: str
    action: RestoreAction
    source_value: Any | None = None
    target_before: Any | None = None
    target_after: Any | None = None
    reason: RestoreReason


class RestoreFieldActionSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    copy_count: int = Field(0, alias="copy", serialization_alias="copy")
    merge_count: int = Field(0, alias="merge", serialization_alias="merge")
    keep_target_count: int = Field(0, alias="keep_target", serialization_alias="keep_target")
    skip_equal_count: int = Field(0, alias="skip_equal", serialization_alias="skip_equal")
    skip_missing_source_count: int = Field(
        0,
        alias="skip_missing_source",
        serialization_alias="skip_missing_source",
    )
    skip_disallowed_count: int = Field(
        0,
        alias="skip_disallowed",
        serialization_alias="skip_disallowed",
    )
    override_count: int = Field(0, alias="override", serialization_alias="override")


class RestoreFromResponse(BaseModel):
    source_archive_id: int
    target_archive_id: int
    updated: bool
    applied: bool
    reenrich_requested: bool = False
    reenrich_triggered: bool = False
    field_action_summary: RestoreFieldActionSummary
    field_actions: list[RestoreFieldAction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    updated_fields: list[str] = Field(default_factory=list)


class RestoreVerifyRequest(BaseModel):
    source_archive_id: int
    target_archive_id: int
    field_groups: list[FieldGroup] = Field(
        default_factory=lambda: [
            FieldGroup.RUNTIME,
            FieldGroup.USER_METADATA,
            FieldGroup.LINEAGE,
            FieldGroup.ASSET_STATE,
            FieldGroup.SNAPSHOT_SUBSET,
        ]
    )
    tag_merge_mode: TagMergeMode = TagMergeMode.MERGE_PRESERVE_TARGET
    notes_merge_mode: NotesMergeMode = NotesMergeMode.APPEND_STRUCTURED
    preserve_target_parser_fields: bool = True
    copy_source_snapshot_subset: list[SnapshotSubset] = Field(default_factory=list)
    exclude_tags: list[str] = Field(
        default_factory=lambda: ["exception:missing_3mf", "replaced_by:*"]
    )
    include_tags: list[str] = Field(default_factory=list)
    remove_original: bool = False
    force_remove_without_reenrich: bool = False
    dry_run: bool = True

    @model_validator(mode="after")
    def validate_archive_pair(self) -> "RestoreVerifyRequest":
        if self.source_archive_id == self.target_archive_id:
            raise ValueError("source_archive_id and target_archive_id must differ")
        return self


class RestoreVerifyResponse(BaseModel):
    source_archive_id: int
    target_archive_id: int
    verified: bool
    applied: bool
    removable: bool
    source_removed: bool
    enrichment_status: str = "missing"
    enrichment_ready: bool = False
    blocking_difference_count: int
    non_blocking_difference_count: int
    remaining_difference_count: int
    remaining_difference_summary: RestoreFieldActionSummary
    remaining_differences: list[RestoreFieldAction] = Field(default_factory=list)
    blocking_differences: list[RestoreFieldAction] = Field(default_factory=list)
    non_blocking_differences: list[RestoreFieldAction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
