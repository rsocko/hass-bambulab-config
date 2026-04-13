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

DEFAULT_FETCH_TIMEOUT_SECONDS = 30
DEFAULT_SCAN_INTERVAL_SECONDS = 300
DEFAULT_SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS)

DATA_MANAGER = "manager"
SERVICE_REFRESH_PRINT_HISTORY_BROWSER = "refresh_print_history_browser"
SERVICE_QUERY_PRINT_HISTORY_BROWSER = "query_print_history_browser"
SERVICE_GET_PRINT_HISTORY_ARCHIVE_DETAIL = "get_print_history_archive_detail"
SERVICE_SET_PRINT_HISTORY_REVIEW_STATE = "set_print_history_review_state"
SERVICE_SET_PRINT_HISTORY_REPAIR_LINEAGE = "set_print_history_repair_lineage"
SERVICE_DELETE_PRINT_HISTORY_REPAIR_LINEAGE = "delete_print_history_repair_lineage"
SERVICE_ESTIMATE_PARTIAL_USAGE = "estimate_partial_usage"
STORE_FILENAME = "bambuddy_print_history_browser.db"

EVENT_BAMBUDDY_WEBHOOK = "bambuddy_webhook_event"
REFRESH_WEBHOOK_EVENTS = {"print_complete", "print_failed", "print_started", "print_stopped"}

BROWSER_HELPER_ENTITY_IDS = [
    "input_select.print_history_filter_status",
    "input_select.print_history_filter_archive_error",
    "input_select.print_history_filter_enrichment_status",
    "input_select.print_history_filter_material",
    "input_select.print_history_filter_printer",
    "input_select.print_history_filter_date_range",
    "input_select.print_history_filter_designer",
    "input_select.print_history_filter_project",
    "input_select.print_history_filter_layer_height",
    "input_select.print_history_filter_tag",
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
    "input_select.print_history_filter_designer",
    "input_select.print_history_filter_project",
    "input_select.print_history_filter_layer_height",
    "input_select.print_history_filter_tag",
}

REFRESH_TRIGGER_HELPERS = {
    "input_number.print_history_max_archives",
    "input_boolean.bambuddy_integration_enabled",
    "input_boolean.bambuddy_history_sync_enabled",
}

SIGNAL_BROWSER_UPDATED = "bambuddy_print_history_browser_updated"

ENTITY_STATUS = "bambuddy_print_history_browser_status"
ENTITY_FILTERED = "bambuddy_print_history_browser_filtered"
ENTITY_PAGE_ARCHIVES = "bambuddy_print_history_browser_page_archives"
ENTITY_PAGE_INFO = "bambuddy_print_history_browser_page_info"
ENTITY_ACTIVITY = "bambuddy_print_history_browser_activity"