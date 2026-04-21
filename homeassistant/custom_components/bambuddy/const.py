from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform


DOMAIN = "bambuddy"
PLATFORMS: list[Platform] = [Platform.SENSOR]

CONF_API_KEY = "api_key"
CONF_BASE_URL = "base_url"
CONF_RUNTIME_REPAIR_BASE_URL = "runtime_repair_base_url"
CONF_RUNTIME_REPAIR_TOKEN = "runtime_repair_token"
CONF_FETCH_TIMEOUT_SECONDS = "fetch_timeout_seconds"
CONF_SCAN_INTERVAL_SECONDS = "scan_interval_seconds"
CONF_RESTORE_UPLOAD_MAX_BYTES = "restore_upload_max_bytes"

DEFAULT_FETCH_TIMEOUT_SECONDS = 30
DEFAULT_SCAN_INTERVAL_SECONDS = 300
DEFAULT_SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS)
DEFAULT_RESTORE_UPLOAD_MAX_BYTES = 512 * 1024 * 1024
DEFAULT_RESTORE_UPLOAD_SESSION_TTL = timedelta(minutes=30)

DATA_MANAGER = "manager"
DATA_RESTORE_UPLOADS = "restore_uploads"
DATA_RESTORE_WORKFLOW = "restore_workflow"
SERVICE_REFRESH_PRINT_HISTORY_BROWSER = "refresh_print_history_browser"
SERVICE_REFRESH_PRINT_HISTORY_ARCHIVE_DETAIL = "refresh_print_history_archive_detail"
SERVICE_QUERY_PRINT_HISTORY_BROWSER = "query_print_history_browser"
SERVICE_GET_FAILURE_ANALYSIS = "get_failure_analysis"
SERVICE_GET_PRINT_HISTORY_ARCHIVE_DETAIL = "get_print_history_archive_detail"
SERVICE_GET_PRINT_HISTORY_ARCHIVE_STORAGE_METRICS = "get_print_history_archive_storage_metrics"
SERVICE_REFRESH_PRINT_HISTORY_ARCHIVE_STORAGE_METRICS_BATCH = "refresh_print_history_archive_storage_metrics_batch"
SERVICE_GET_PRINT_HISTORY_ARCHIVE_ENRICHMENT_METADATA = "get_print_history_archive_enrichment_metadata"
SERVICE_UPDATE_PRINT_HISTORY_ARCHIVE = "update_print_history_archive"
SERVICE_UPDATE_PRINT_HISTORY_ARCHIVE_ENRICHMENT_METADATA = "update_print_history_archive_enrichment_metadata"
SERVICE_SET_PRINT_HISTORY_ARCHIVE_FAVORITE = "set_print_history_archive_favorite"
SERVICE_APPEND_PRINT_HISTORY_EVENT = "append_print_history_event"
SERVICE_SET_PRINT_HISTORY_PRIMARY_PHOTO = "set_print_history_primary_photo"
SERVICE_DELETE_PRINT_HISTORY_PHOTO = "delete_print_history_photo"
SERVICE_DELETE_PRINT_HISTORY_ARCHIVE = "delete_print_history_archive"
SERVICE_DISMISS_PRINT_HISTORY_MEDIA_REVIEW = "dismiss_print_history_media_review"
SERVICE_SET_PRINT_HISTORY_MEDIA_REVIEW_STATE = "set_print_history_media_review_state"
SERVICE_SET_PRINT_HISTORY_REVIEW_STATE = "set_print_history_review_state"
SERVICE_SET_PRINT_HISTORY_REPAIR_LINEAGE = "set_print_history_repair_lineage"
SERVICE_DELETE_PRINT_HISTORY_REPAIR_LINEAGE = "delete_print_history_repair_lineage"
SERVICE_REPAIR_PRINT_HISTORY_ARCHIVE_FROM_START = "repair_print_history_archive_from_start"
SERVICE_CORRECT_PRINT_HISTORY_ARCHIVE_METADATA = "correct_print_history_archive_metadata"
SERVICE_ESTIMATE_PARTIAL_USAGE = "estimate_partial_usage"
SERVICE_REFRESH_PRINT_HISTORY_ARCHIVE_STORAGE_METRICS = "refresh_print_history_archive_storage_metrics"
SERVICE_GET_PRINT_HISTORY_ARCHIVE_RESTORE_WORKFLOW = "get_print_history_archive_restore_workflow"
SERVICE_CREATE_PRINT_HISTORY_ARCHIVE_REPLACEMENT_FROM_UPLOAD = "create_print_history_archive_replacement_from_upload"
SERVICE_PLAN_PRINT_HISTORY_ARCHIVE_RESTORE = "plan_print_history_archive_restore"
SERVICE_APPLY_PRINT_HISTORY_ARCHIVE_RESTORE = "apply_print_history_archive_restore"
SERVICE_VERIFY_PRINT_HISTORY_ARCHIVE_RESTORE = "verify_print_history_archive_restore"
SERVICE_FINISH_PRINT_HISTORY_ARCHIVE_RESTORE = "finish_print_history_archive_restore"
SERVICE_REMOVE_PRINT_HISTORY_RESTORED_SOURCE_ARCHIVE = "remove_print_history_restored_source_archive"
SERVICE_CLEAR_PRINT_HISTORY_ARCHIVE_RESTORE = "clear_print_history_archive_restore"
STORE_FILENAME = "bambuddy_print_history_browser.db"
RESTORE_UPLOAD_DISCOVER_URL = "/api/bambuddy/print-history/archive-repair/replacement/discover"
ARCHIVE_VIEWER_GCODE_URL = "/api/bambuddy/print-history/archive-viewer/{archive_id}/gcode"
SOURCE_3MF_UPLOAD_URL = "/api/bambuddy/print-history/archive/{archive_id}/source-3mf/upload"
TIMELAPSE_INFO_URL = "/api/bambuddy/print-history/archive/{archive_id}/timelapse/info"
TIMELAPSE_THUMBNAILS_URL = "/api/bambuddy/print-history/archive/{archive_id}/timelapse/thumbnails"
TIMELAPSE_PROCESS_URL = "/api/bambuddy/print-history/archive/{archive_id}/timelapse/process"
TIMELAPSE_UPLOAD_URL = "/api/bambuddy/print-history/archive/{archive_id}/timelapse/upload"

EVENT_BAMBUDDY_WEBHOOK = "bambuddy_webhook_event"
REFRESH_WEBHOOK_EVENTS = {"print_complete", "print_failed", "print_started", "print_stopped"}

BROWSER_HELPER_ENTITY_IDS = [
    "input_select.print_history_filter_status",
    "input_select.print_history_filter_archive_error",
    "input_select.print_history_filter_enrichment_status",
    "input_select.print_history_filter_material",
    "input_select.print_history_filter_duplicates",
    "input_select.print_history_filter_printer",
    "input_select.print_history_filter_date_range",
    "input_text.print_history_filter_start_date",
    "input_text.print_history_filter_end_date",
    "input_select.print_history_filter_designer",
    "input_select.print_history_filter_project",
    "input_select.print_history_filter_layer_height",
    "input_select.print_history_filter_tag",
    "input_text.print_history_filter_tags",
    "input_select.print_history_filter_tags_mode",
    "input_boolean.print_history_filter_tags_untagged_only",
    "input_boolean.print_history_filter_favorites_only",
    "input_text.print_history_search",
    "input_text.print_history_filter_colors",
    "input_text.print_history_activity_selected_date",
    "input_select.print_history_activity_metric",
    "input_select.print_history_sort",
    "input_number.print_history_page_size",
    "input_number.history_current_page",
    "input_number.print_history_max_archives",
    "input_boolean.bambuddy_integration_enabled",
    "input_boolean.bambuddy_history_sync_enabled",
    "input_boolean.print_history_debug_instrumentation",
]

OPTION_SET_HELPERS = {
    "input_select.print_history_filter_material",
    "input_select.print_history_filter_color",
    "input_select.print_history_filter_printer",
    "input_select.print_history_filter_duplicates",
    "input_select.print_history_filter_designer",
    "input_select.print_history_filter_project",
    "input_select.print_history_filter_layer_height",
    "input_select.print_history_filter_tag",
}

REFRESH_TRIGGER_HELPERS = {
    "input_number.print_history_max_archives",
    "input_boolean.bambuddy_integration_enabled",
    "input_boolean.bambuddy_history_sync_enabled",
    "input_text.print_history_filter_start_date",
    "input_text.print_history_filter_end_date",
}

SIGNAL_BROWSER_UPDATED = "bambuddy_print_history_browser_updated"

ENTITY_STATUS = "bambuddy_print_history_browser_status"
ENTITY_FILTERED = "bambuddy_print_history_browser_filtered"
ENTITY_PAGE_ARCHIVES = "bambuddy_print_history_browser_page_archives"
ENTITY_PAGE_INFO = "bambuddy_print_history_browser_page_info"
ENTITY_ACTIVITY = "bambuddy_print_history_browser_activity"