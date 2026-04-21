class PrintHistoryArchiveActionsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._archiveOverride = null;
    this._mode = "main";
    this._metadataBundle = null;
    this._metadataArchiveId = "";
    this._metadataError = "";
    this._metadataRevision = 0;
    this._jsonClipboard = {};
    this._busy = false;
    this._busyContext = "";
    this._status = "";
    this._statusTone = "info";
    this._storageMetricsRequestKey = "";
    this._storageMetricsLoadedKey = "";
    this._relatedCandidates = [];
    this._relatedCandidatesLimit = 0;
    this._relatedArchiveId = "";
    this._relatedError = "";
    this._relatedCompareIntent = false;
    this._comparePayload = null;
    this._compareArchiveIds = [];
    this._compareError = "";
    this._compareBackMode = "main";
    this._initialCompareRequestKey = "";
    this._metadataCorrectionDraft = null;
    this._metadataCorrectionPreview = null;
    this._metadataCorrectionError = "";
    this._metadataCorrectionPreviewKey = "";
    this._lastRenderSignature = "";
    this._boundClickHandler = this._handleClick.bind(this);
    this._boundSourceUploadChangeHandler = this._handleSourceUploadChange.bind(this);
  }

  setConfig(config) {
    this._config = {
      archive_json: config && config.archive_json ? config.archive_json : "{}",
      detail_entity: config && config.detail_entity ? config.detail_entity : "",
      api_base_entity: config && config.api_base_entity ? config.api_base_entity : "input_text.bambuddy_api_base_url",
      related_limit_entity:
        config && config.related_limit_entity
          ? config.related_limit_entity
          : "input_number.print_history_related_candidate_limit",
      compare_archive_ids_json: config && config.compare_archive_ids_json ? config.compare_archive_ids_json : "[]",
      initial_mode: config && config.initial_mode ? config.initial_mode : "",
      compare_back_mode: config && config.compare_back_mode ? config.compare_back_mode : "main",
      entry_id: config && config.entry_id ? config.entry_id : "",
      upload_endpoint:
        config && config.upload_endpoint
          ? config.upload_endpoint
          : "/api/bambuddy/print-history/archive/{archive_id}/source-3mf/upload",
      timelapse_upload_endpoint:
        config && config.timelapse_upload_endpoint
          ? config.timelapse_upload_endpoint
          : "/api/bambuddy/print-history/archive/{archive_id}/timelapse/upload",
    };
    this._archiveOverride = null;
    this._mode = "main";
    this._metadataBundle = null;
    this._metadataArchiveId = "";
    this._metadataError = "";
    this._metadataRevision = 0;
    this._jsonClipboard = {};
    this._busy = false;
    this._busyContext = "";
    this._status = "";
    this._statusTone = "info";
    this._storageMetricsRequestKey = "";
    this._storageMetricsLoadedKey = "";
    this._relatedCandidates = [];
    this._relatedCandidatesLimit = 0;
    this._relatedArchiveId = "";
    this._relatedError = "";
    this._relatedCompareIntent = false;
    this._comparePayload = null;
    this._compareArchiveIds = [];
    this._compareError = "";
    this._compareBackMode = "main";
    this._initialCompareRequestKey = "";
    this._metadataCorrectionDraft = null;
    this._metadataCorrectionPreview = null;
    this._metadataCorrectionError = "";
    this._metadataCorrectionPreviewKey = "";
    this._lastRenderSignature = "";
    this._render();
  }

  set hass(hass) {
    var nextSignature = this._computeRenderSignature(hass);
    this._hass = hass;
    if (nextSignature === this._lastRenderSignature) {
      this._maybeLoadStorageMetrics();
      return;
    }
    this._lastRenderSignature = nextSignature;
    this._render();
    this._maybeLoadStorageMetrics();
    this._maybeLoadInitialCompare();
  }

  connectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.addEventListener("click", this._boundClickHandler);
      this.shadowRoot.addEventListener("change", this._boundSourceUploadChangeHandler);
    }
    this._maybeLoadInitialCompare();
  }

  disconnectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.removeEventListener("click", this._boundClickHandler);
      this.shadowRoot.removeEventListener("change", this._boundSourceUploadChangeHandler);
    }
  }

  getCardSize() {
    return 5;
  }

  _resolveArchive() {
    if (this._archiveOverride && typeof this._archiveOverride === "object") {
      return this._archiveOverride;
    }

    var parsed = {};
    try {
      parsed = JSON.parse(this._config && this._config.archive_json ? this._config.archive_json : "{}");
      parsed = parsed && typeof parsed === "object" ? parsed : {};
    } catch (_error) {
      parsed = {};
    }

    if (this._hass && this._config && this._config.detail_entity) {
      var detailState = this._hass.states && this._hass.states[this._config.detail_entity];
      if (detailState && detailState.attributes && detailState.attributes.archive && typeof detailState.attributes.archive === "object") {
        var detailArchive = detailState.attributes.archive;
        var parsedId = parsed && parsed.id != null ? String(parsed.id) : "";
        var detailId = detailArchive && detailArchive.id != null ? String(detailArchive.id) : "";
        if (!parsedId || !detailId || parsedId === detailId) {
          return Object.assign({}, parsed, detailArchive);
        }
      }
    }

    return parsed;
  }

  _setArchive(archive) {
    this._archiveOverride = archive && typeof archive === "object" ? archive : null;
    this._lastRenderSignature = "";
    this._render();
    this._maybeLoadStorageMetrics();
    this._maybeLoadInitialCompare();
  }

  _configuredCompareArchiveIds() {
    var parsed = [];
    try {
      parsed = JSON.parse(this._config && this._config.compare_archive_ids_json ? this._config.compare_archive_ids_json : "[]");
    } catch (_error) {
      parsed = [];
    }
    return this._normalizeCompareArchiveIds(Array.isArray(parsed) ? parsed : [parsed]);
  }

  _maybeLoadInitialCompare() {
    if (!this._hass || !this._config || this._busy) {
      return;
    }
    if (String(this._config.initial_mode || "").trim().toLowerCase() !== "compare") {
      return;
    }
    var compareIds = this._configuredCompareArchiveIds();
    if (compareIds.length < 2) {
      return;
    }
    var requestKey = compareIds.join(",") + "|" + String(this._config.compare_back_mode || "main");
    if (this._initialCompareRequestKey === requestKey) {
      return;
    }
    if (this._comparePayload && JSON.stringify(this._compareArchiveIds || []) === JSON.stringify(compareIds)) {
      this._initialCompareRequestKey = requestKey;
      return;
    }
    this._initialCompareRequestKey = requestKey;
    this._mode = "compare";
    this._render();
    this._loadCompareForArchives(compareIds, this._config.compare_back_mode || "main");
  }

  _mergeArchivePatch(patch) {
    var currentArchive = this._resolveArchive();
    if (!currentArchive || typeof currentArchive !== "object") {
      return;
    }
    this._setArchive(Object.assign({}, currentArchive, patch && typeof patch === "object" ? patch : {}));
  }

  _setStatus(message, tone) {
    this._status = String(message || "").trim();
    this._statusTone = tone === "error" ? "error" : tone === "success" ? "success" : "info";
    this._lastRenderSignature = "";
    this._render();
  }

  _setBusy(busy, message, tone) {
    this._busy = !!busy;
    this._busyContext = this._busy ? this._busyContext : "";
    if (message != null) {
      this._setStatus(message, tone);
      return;
    }
    this._lastRenderSignature = "";
    this._render();
  }

  _setBusyState(busy, message, tone, context) {
    this._busyContext = busy ? String(context || "").trim() : "";
    this._setBusy(busy, message, tone);
  }

  _fireBrowserModEvent(service, data) {
    var event = new CustomEvent("ll-custom", {
      bubbles: true,
      composed: true,
      detail: {
        browser_mod: {
          service: service,
          data: data,
          target: {},
        },
      },
    });

    if (document && document.body) {
      document.body.dispatchEvent(event);
      return;
    }

    this.dispatchEvent(event);
  }

  _describeError(error, fallbackMessage) {
    if (!error) {
      return fallbackMessage;
    }

    var diagnosticsMessage = this._formatUploadDiagnostics(error && error.body ? error.body.diagnostics : null);

    if (typeof error === "string") {
      var textError = error.trim();
      return textError || fallbackMessage;
    }

    if (error.message && String(error.message).trim()) {
      var normalizedMessage = String(error.message).trim();
      var httpDetailMatch = normalizedMessage.match(/^Bambuddy returned HTTP \d+:\s*(.+)$/i);
      if (httpDetailMatch && httpDetailMatch[1]) {
        normalizedMessage = String(httpDetailMatch[1]).trim();
      }
      return diagnosticsMessage
        ? normalizedMessage + " [" + diagnosticsMessage + "]"
        : normalizedMessage;
    }

    if (error.code && error.code !== "unknown_error") {
      var codeMessage = String(error.code).trim();
      if (error.details && String(error.details).trim()) {
        return codeMessage + ": " + String(error.details).trim();
      }
      return codeMessage;
    }

    if (error.body && typeof error.body === "object") {
      if (error.body.message && String(error.body.message).trim()) {
        return diagnosticsMessage
          ? String(error.body.message).trim() + " [" + diagnosticsMessage + "]"
          : String(error.body.message).trim();
      }
      if (error.body.error && String(error.body.error).trim()) {
        return diagnosticsMessage
          ? String(error.body.error).trim() + " [" + diagnosticsMessage + "]"
          : String(error.body.error).trim();
      }
    }

    if (error.details && String(error.details).trim()) {
      return String(error.details).trim();
    }

    try {
      var serialized = JSON.stringify(error);
      if (serialized && serialized !== "{}") {
        return serialized;
      }
    } catch (_jsonError) {
      // Ignore JSON serialization issues and fall through to the fallback.
    }

    return fallbackMessage;
  }

  _formatUploadDiagnostics(diagnostics) {
    if (!diagnostics || typeof diagnostics !== "object") {
      return "";
    }

    var summary = [];
    if (diagnostics.request_content_type) {
      summary.push("request=" + String(diagnostics.request_content_type));
    }
    if (diagnostics.file_content_type) {
      summary.push("file=" + String(diagnostics.file_content_type));
    }
    if (diagnostics.chunk_count != null) {
      summary.push("chunks=" + String(diagnostics.chunk_count));
    }
    if (diagnostics.byte_count != null) {
      summary.push("bytes=" + String(diagnostics.byte_count));
    }
    if (diagnostics.first_chunk_size != null) {
      summary.push("first_chunk=" + String(diagnostics.first_chunk_size));
    }
    return summary.join(", ");
  }

  _handleClick(event) {
    var target = event.target;
    if (!target || !target.closest) {
      return;
    }
    var button = target.closest("button[data-action]");
    if (!button || button.disabled) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();

    var action = String(button.getAttribute("data-action") || "");
    if (action === "open-in-slicer") {
      this._handleOpenInSlicer();
      return;
    }
    if (action === "download-model") {
      this._handleDownload("download_gcode", "Preparing G-code download...", "G-code download started.");
      return;
    }
    if (action === "download-source-3mf") {
      this._handleDownload("download_source_3mf", "Preparing source 3MF download...", "Source 3MF download started.");
      return;
    }
    if (action === "open-makerworld") {
      this._handleMakerWorld();
      return;
    }
    if (action === "upload-source-3mf") {
      this._openSourceUploadPicker();
      return;
    }
    if (action === "upload-timelapse") {
      this._openTimelapseUploadPicker();
      return;
    }
    if (action === "scan-timelapse") {
      this._handleScanTimelapse();
      return;
    }
    if (action === "view-timelapse") {
      this._openTimelapsePopup();
      return;
    }
    if (action === "repair-archive") {
      this._handleRepair();
      return;
    }
    if (action === "refresh-storage-metrics") {
      this._handleRefreshStorageMetrics();
      return;
    }
    if (action === "view-metadata") {
      this._openMetadataViewer(false);
      return;
    }
    if (action === "open-correct-metadata") {
      this._openMetadataCorrection();
      return;
    }
    if (action === "preview-correct-metadata") {
      this._handleMetadataCorrectionPreview();
      return;
    }
    if (action === "apply-correct-metadata") {
      this._handleMetadataCorrectionApply();
      return;
    }
    if (action === "open-failure-analysis") {
      this._openFailureAnalysis();
      return;
    }
    if (action === "open-related") {
      this._loadRelatedCandidates({ compareIntent: false });
      return;
    }
    if (action === "open-compare") {
      this._loadRelatedCandidates({ compareIntent: true });
      return;
    }
    if (action === "related-open") {
      this._handleOpenRelatedArchive(button.getAttribute("data-archive-id") || "");
      return;
    }
    if (action === "related-compare") {
      this._handleCompareAgainstArchive(button.getAttribute("data-archive-id") || "");
      return;
    }
    if (action === "refresh-metadata") {
      this._openMetadataViewer(true);
      return;
    }
    if (action === "back-main") {
      this._mode = "main";
      this._render();
      return;
    }
    if (action === "back-related") {
      this._mode = "related";
      this._render();
      return;
    }
    if (action === "copy-json") {
      this._handleCopyJson(button.getAttribute("data-copy-target") || "", button.getAttribute("data-copy-label") || "JSON");
      return;
    }
    if (action === "delete-archive") {
      this._mode = "confirm-delete-1";
      this._render();
      return;
    }
    if (action === "delete-archive-final") {
      this._handleDelete();
      return;
    }
    if (action === "continue-delete") {
      this._mode = "confirm-delete-2";
      this._render();
      return;
    }
    if (action === "cancel") {
      this._mode = "main";
      this._render();
    }
  }

  _handleSourceUploadChange(event) {
    var input = event && event.target ? event.target : null;
    if (!input) {
      return;
    }
    if (input.id !== "source-upload-input" && input.id !== "timelapse-upload-input") {
      return;
    }
    var files = input && input.files ? input.files : null;
    var file = files && files.length ? files[0] : null;
    if (file) {
      if (input.id === "timelapse-upload-input") {
        this._uploadTimelapse(file);
      } else {
        this._uploadSource3mf(file);
      }
    }
    input.value = "";
  }

  _getBaseUrl() {
    if (!this._hass || !this._config) {
      return "";
    }
    var entity = this._hass.states && this._hass.states[this._config.api_base_entity];
    if (!entity || entity.state == null) {
      return "";
    }
    return String(entity.state || "").trim().replace(/\/$/, "");
  }

  _computeRenderSignature(hass) {
    if (!this._config || !hass || !hass.states) {
      return "";
    }

    var parts = [
      typeof this._config.archive_json === "string"
        ? this._config.archive_json
        : JSON.stringify(this._config.archive_json || {}),
      JSON.stringify(this._archiveOverride || {}),
      this._mode,
      this._busy ? "1" : "0",
      this._status,
      this._statusTone,
    ];

    var detailEntityId = this._config.detail_entity || "";
    var detailState = detailEntityId ? hass.states[detailEntityId] : null;
    parts.push(detailState ? String(detailState.state || "") : "");
    parts.push(detailState ? String(detailState.last_updated || detailState.last_changed || "") : "");
    parts.push(String(this._metadataArchiveId || ""));
    parts.push(String(this._metadataError || ""));
    parts.push(String(this._metadataRevision || 0));
    parts.push(String(this._relatedArchiveId || ""));
    parts.push(String(this._relatedError || ""));
    parts.push(String(this._relatedCandidatesLimit || 0));
    parts.push(this._relatedCompareIntent ? "1" : "0");
    parts.push(JSON.stringify(this._relatedCandidates || []));
    parts.push(JSON.stringify(this._compareArchiveIds || []));
    parts.push(String(this._compareError || ""));
    parts.push(String(this._compareBackMode || "main"));
    parts.push(JSON.stringify(this._comparePayload || {}));

    var baseEntityId = this._config.api_base_entity || "input_text.bambuddy_api_base_url";
    var baseState = hass.states[baseEntityId];
    parts.push(baseState ? String(baseState.state || "") : "");
    parts.push(baseState ? String(baseState.last_updated || baseState.last_changed || "") : "");

    var relatedLimitEntityId = this._config.related_limit_entity || "input_number.print_history_related_candidate_limit";
    var relatedLimitState = hass.states[relatedLimitEntityId];
    parts.push(relatedLimitState ? String(relatedLimitState.state || "") : "");
    parts.push(relatedLimitState ? String(relatedLimitState.last_updated || relatedLimitState.last_changed || "") : "");

    return parts.join("|");
  }

  _archiveKey(archive) {
    if (!archive || typeof archive !== "object") {
      return "";
    }
    return JSON.stringify({
      id: archive.id != null ? String(archive.id) : "",
      print_name: archive.print_name || "",
      thumbnail_path: archive.thumbnail_path || "",
      primary_photo_path: archive.primary_photo_path || "",
      selected_primary_photo_path: archive.selected_primary_photo_path || "",
      photos: Array.isArray(archive.photos) ? archive.photos : [],
    });
  }

  _archiveMediaCacheKey(archive) {
    if (!archive || typeof archive !== "object") {
      return "";
    }
    return JSON.stringify({
      key: this._archiveKey(archive),
      source_updated_at: archive.source_updated_at || archive.updated_at || archive.completed_at || archive.created_at || "",
      has_primary_photo_override: !!archive.has_primary_photo_override,
    });
  }

  _withArchiveMediaCacheKey(url, archive) {
    var normalizedUrl = String(url || "").trim();
    if (!normalizedUrl) {
      return "";
    }
    var cacheKey = this._archiveMediaCacheKey(archive);
    if (!cacheKey) {
      return normalizedUrl;
    }
    return normalizedUrl + (normalizedUrl.indexOf("?") >= 0 ? "&" : "?") + "v=" + encodeURIComponent(cacheKey);
  }

  _setMetadataState(bundle, error, archiveId) {
    this._metadataBundle = bundle && typeof bundle === "object" ? bundle : null;
    this._metadataError = String(error || "").trim();
    this._metadataArchiveId = archiveId != null ? String(archiveId) : "";
    this._metadataRevision += 1;
    this._lastRenderSignature = "";
    this._render();
  }

  _matchingMetadataBundle(archiveId) {
    var normalizedArchiveId = archiveId != null ? String(archiveId) : "";
    if (!normalizedArchiveId || !this._metadataBundle || this._metadataArchiveId !== normalizedArchiveId) {
      return null;
    }
    return this._metadataBundle;
  }

  async _callArchiveDetailService(archiveId) {
    if (!this._hass || archiveId <= 0) {
      throw new Error("Archive action context is unavailable");
    }
    var payload = { archive_id: archiveId };
    if (this._config && this._config.entry_id) {
      payload.entry_id = String(this._config.entry_id);
    }
    return this._callServiceWithResponse("bambuddy", "get_print_history_archive_detail", payload);
  }

  async _openMetadataViewer(forceRefresh) {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    if (archiveId <= 0) {
      this._setStatus("Archive metadata is unavailable for this print.", "error");
      return;
    }

    this._mode = "metadata";
    this._render();

    if (!forceRefresh && this._matchingMetadataBundle(archiveId)) {
      return;
    }

    try {
      this._setBusyState(true, forceRefresh ? "Refreshing archive metadata..." : "Loading archive metadata...", "info", "metadata");
      var response = await this._callArchiveDetailService(archiveId);
      this._busy = false;
      this._busyContext = "";
      this._setMetadataState(response && typeof response === "object" ? response : {}, "", archiveId);
      this._setStatus(forceRefresh ? "Archive metadata refreshed." : "Archive metadata loaded.", "success");
    } catch (error) {
      var message = this._describeError(error, "Could not load archive metadata");
      this._busy = false;
      this._busyContext = "";
      this._setMetadataState(null, message, archiveId);
      this._setStatus(message, "error");
    }
  }

  async _handleCopyJson(copyTarget, copyLabel) {
    var key = String(copyTarget || "").trim();
    var label = String(copyLabel || "JSON").trim() || "JSON";
    var text = key ? this._jsonClipboard[key] : "";
    if (!text) {
      this._setStatus("Nothing is available to copy for " + label + ".", "error");
      return;
    }

    try {
      if (navigator && navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
        await navigator.clipboard.writeText(text);
      } else {
        var textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "readonly");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        textarea.style.pointerEvents = "none";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      this._setStatus(label + " copied to the clipboard.", "success");
    } catch (_error) {
      this._setStatus("Could not copy " + label + " to the clipboard.", "error");
    }
  }

  _prettyJson(value) {
    try {
      return JSON.stringify(value == null ? null : value, null, 2);
    } catch (error) {
      return JSON.stringify({
        error: "Could not serialize JSON payload",
        message: error && error.message ? String(error.message) : String(error || "Unknown error"),
      }, null, 2);
    }
  }

  _formatJsonLine(line) {
    var escaped = this._escapeHtml(line);
    return escaped.replace(
      /("(\\u[0-9a-fA-F]{4}|\\[^u]|[^\\"])*"\s*:|"(\\u[0-9a-fA-F]{4}|\\[^u]|[^\\"])*"|\btrue\b|\bfalse\b|\bnull\b|-?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?)/g,
      function (match) {
        var tokenClass = "number";
        if (/^".*":$/.test(match)) {
          tokenClass = "key";
        } else if (/^"/.test(match)) {
          tokenClass = "string";
        } else if (match === "true" || match === "false") {
          tokenClass = "boolean";
        } else if (match === "null") {
          tokenClass = "null";
        }
        return '<span class="token ' + tokenClass + '">' + match + '</span>';
      }
    );
  }

  _renderJsonCodeBlock(copyKey, value) {
    var text = this._prettyJson(value);
    var lines = text.split("\n");
    this._jsonClipboard[copyKey] = text;
    return {
      text: text,
      lineCount: lines.length,
      html: '<div class="json-code">' + lines.map(function (line, index) {
        return '<div class="json-line"><span class="json-gutter">' + String(index + 1) + '</span><span class="json-line-content">' + this._formatJsonLine(line) + '</span></div>';
      }.bind(this)).join("") + '</div>',
    };
  }

  _renderMetadataPanel(title, subtitle, copyKey, copyLabel, value, openByDefault) {
    var block = this._renderJsonCodeBlock(copyKey, value);
    return '<details class="json-panel"' + (openByDefault ? ' open' : '') + '>' +
      '<summary class="json-panel-summary">' +
      '<div class="json-panel-heading">' +
      '<div class="json-panel-title">' + this._escapeHtml(title) + '</div>' +
      '<div class="json-panel-meta">' + this._escapeHtml(String(block.lineCount)) + ' lines · ' + this._escapeHtml(String(block.text.length)) + ' chars</div>' +
      '</div>' +
      '<button class="json-copy-button" type="button" data-action="copy-json" data-copy-target="' + this._escapeHtml(copyKey) + '" data-copy-label="' + this._escapeHtml(copyLabel) + '">Copy</button>' +
      '</summary>' +
      (subtitle ? '<div class="json-panel-copy">' + this._escapeHtml(subtitle) + '</div>' : '') +
      '<div class="json-frame">' + block.html + '</div>' +
      '</details>';
  }

  _renderMetadataView(archive) {
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    var bundle = this._matchingMetadataBundle(archiveId);
    var localDetailPayload = bundle || {
      archive_id: archiveId,
      status: this._busy ? "loading" : "unavailable",
      error: this._metadataError || "Archive metadata has not been loaded yet.",
    };
    return '<div class="section-stack metadata-view">' +
      this._renderActionSection(
        "Metadata",
        '<div class="actions-grid metadata-toolbar">' +
          this._renderActionButton("back-main", "Back to Actions", "mdi:arrow-left", { disabled: this._busy }) +
          this._renderActionButton("refresh-metadata", "Refresh Metadata", "mdi:refresh", { disabled: this._busy }) +
        '</div>' +
        '<div class="section-copy">View-only debug payloads for this print. The archive payload is the hydrated record currently rendered by the UI. The local detail bundle comes from bambuddy.get_print_history_archive_detail and includes sync, provenance, review, and timeline rows stored in Home Assistant.</div>'
      ) +
      this._renderMetadataPanel(
        "Archive Payload",
        "Current archive object used by the print-history cards.",
        "archive-payload",
        "Archive payload JSON",
        archive || {},
        true
      ) +
      this._renderMetadataPanel(
        "Local Detail Bundle",
        bundle
          ? "Local store detail bundle returned by the Bambuddy archive-detail service."
          : this._metadataError
            ? "The archive-detail service did not return data."
            : "Load or refresh to fetch the local store detail bundle for this archive.",
        "local-detail-bundle",
        "Local detail bundle JSON",
        localDetailPayload,
        true
      ) +
      '</div>';
  }

  _buildMetadataCorrectionDraft(archive) {
    return {
      started_at: archive && archive.started_at ? String(archive.started_at) : "",
      completed_at: archive && archive.completed_at ? String(archive.completed_at) : "",
      created_at: archive && archive.created_at ? String(archive.created_at) : "",
      status: archive && archive.status ? String(archive.status) : "",
      failure_reason: archive && archive.failure_reason ? String(archive.failure_reason) : "",
      reason: "",
    };
  }

  _openMetadataCorrection() {
    var archive = this._resolveArchive();
    this._metadataCorrectionDraft = this._buildMetadataCorrectionDraft(archive);
    this._metadataCorrectionPreview = null;
    this._metadataCorrectionError = "";
    this._metadataCorrectionPreviewKey = "";
    this._mode = "correct-metadata";
    this._render();
  }

  _metadataCorrectionFieldValue(fieldName) {
    var input = this.shadowRoot ? this.shadowRoot.getElementById("metadata-correction-" + fieldName) : null;
    return input ? String(input.value || "") : "";
  }

  _collectMetadataCorrectionPayload() {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    if (archiveId <= 0) {
      throw new Error("Archive context is unavailable");
    }
    var draft = {
      started_at: this._metadataCorrectionFieldValue("started_at"),
      completed_at: this._metadataCorrectionFieldValue("completed_at"),
      created_at: this._metadataCorrectionFieldValue("created_at"),
      status: this._metadataCorrectionFieldValue("status"),
      failure_reason: this._metadataCorrectionFieldValue("failure_reason"),
      reason: this._metadataCorrectionFieldValue("reason"),
    };
    this._metadataCorrectionDraft = draft;

    var payload = {
      archive_id: archiveId,
      reason: draft.reason.trim(),
    };
    ["started_at", "completed_at", "created_at", "status"].forEach(function (fieldName) {
      var value = String(draft[fieldName] || "").trim();
      var currentValue = archive && archive[fieldName] != null ? String(archive[fieldName]) : "";
      if (value && value !== currentValue) {
        payload[fieldName] = value;
      }
    });
    var currentFailureReason = archive && archive.failure_reason != null ? String(archive.failure_reason) : "";
    if (draft.failure_reason !== currentFailureReason) {
      payload.failure_reason = draft.failure_reason;
    }
    if (!payload.reason) {
      throw new Error("Reason is required before previewing metadata changes.");
    }
    if (!("started_at" in payload) && !("completed_at" in payload) && !("created_at" in payload) && !("status" in payload) && !("failure_reason" in payload)) {
      throw new Error("Change at least one metadata field before previewing.");
    }
    return payload;
  }

  async _runMetadataCorrection(dryRun) {
    var payload = this._collectMetadataCorrectionPayload();
    payload.dry_run = !!dryRun;
    var payloadKey = JSON.stringify(payload);
    this._metadataCorrectionError = "";
    this._setBusyState(true, dryRun ? "Previewing metadata correction..." : "Applying metadata correction...", "info", dryRun ? "metadata-correction-preview" : "metadata-correction-apply");
    try {
      var response = await this._callServiceWithResponse("bambuddy", "correct_print_history_archive_metadata", payload);
      var correction = response && response.correction && typeof response.correction === "object" ? response.correction : {};
      this._metadataCorrectionPreview = correction;
      this._metadataCorrectionPreviewKey = payloadKey;
      if (!dryRun && response && response.archive && typeof response.archive === "object") {
        this._setArchive(response.archive);
      }
      this._busy = false;
      this._busyContext = "";
      this._setStatus(dryRun ? "Metadata correction preview ready." : "Metadata correction applied.", "success");
      return correction;
    } catch (error) {
      this._busy = false;
      this._busyContext = "";
      this._metadataCorrectionError = this._describeError(error, dryRun ? "Metadata correction preview failed" : "Metadata correction failed");
      this._setStatus(this._metadataCorrectionError, "error");
      throw error;
    }
  }

  async _handleMetadataCorrectionPreview() {
    try {
      await this._runMetadataCorrection(true);
    } catch (_error) {
      // Status is already surfaced to the user.
    }
  }

  async _handleMetadataCorrectionApply() {
    try {
      var nextPayload = this._collectMetadataCorrectionPayload();
      var payloadKey = JSON.stringify(Object.assign({}, nextPayload, { dry_run: true }));
      if (!this._metadataCorrectionPreview || payloadKey !== this._metadataCorrectionPreviewKey) {
        this._metadataCorrectionError = "Preview the current changes again before applying them.";
        this._setStatus(this._metadataCorrectionError, "error");
        this._render();
        return;
      }
      await this._runMetadataCorrection(false);
    } catch (_error) {
      // Status is already surfaced to the user.
    }
  }

  _renderMetadataCorrectionImpactList(impacts) {
    if (!impacts || typeof impacts !== "object") {
      return '<div class="section-copy">Derived impact preview is unavailable.</div>';
    }
    var rows = [];
    rows.push("Runtime before: " + (impacts.duration_seconds_before != null ? String(impacts.duration_seconds_before) + "s" : "unknown"));
    rows.push("Runtime after: " + (impacts.duration_seconds_after != null ? String(impacts.duration_seconds_after) + "s" : "unknown"));
    rows.push("Created day: " + String(impacts.created_day_before || "unknown") + " -> " + String(impacts.created_day_after || "unknown"));
    rows.push("Status changed: " + (impacts.status_changed ? "yes" : "no"));
    rows.push("Failure reason changed: " + (impacts.failure_reason_changed ? "yes" : "no"));
    return '<div class="metadata-impact-list">' + rows.map(function (row) {
      return '<div class="metadata-impact-item">' + this._escapeHtml(row) + '</div>';
    }.bind(this)).join("") + '</div>';
  }

  _renderMetadataCorrectionView(archive) {
    var draft = this._metadataCorrectionDraft || this._buildMetadataCorrectionDraft(archive);
    var preview = this._metadataCorrectionPreview;
    var warnings = preview && Array.isArray(preview.warnings) ? preview.warnings : [];
    var updatedFields = preview && Array.isArray(preview.updated_fields) ? preview.updated_fields : [];
    return '<div class="section-stack metadata-correction-view">' +
      this._renderActionSection(
        "Correct Metadata",
        '<div class="actions-grid metadata-toolbar">' +
          this._renderActionButton("back-main", "Back to Actions", "mdi:arrow-left", { disabled: this._busy }) +
          this._renderActionButton("view-metadata", "View Archive Metadata", "mdi:code-json", { disabled: this._busy }) +
        '</div>' +
        '<div class="section-copy">Advanced correction writes directly to archived runtime metadata. Preview first, confirm the derived impact summary, then apply. A local audit record is written to the Variant 3 store when this runs.</div>'
      ) +
      this._renderActionSection(
        "Editable Fields",
        '<div class="metadata-form-grid">' +
          '<label class="metadata-field"><span class="metadata-field-label">Created At</span><input id="metadata-correction-created_at" class="metadata-input" type="text" value="' + this._escapeHtml(draft.created_at || "") + '" placeholder="2026-04-21T13:00:00+00:00"></label>' +
          '<label class="metadata-field"><span class="metadata-field-label">Started At</span><input id="metadata-correction-started_at" class="metadata-input" type="text" value="' + this._escapeHtml(draft.started_at || "") + '" placeholder="2026-04-21T13:05:00+00:00"></label>' +
          '<label class="metadata-field"><span class="metadata-field-label">Completed At</span><input id="metadata-correction-completed_at" class="metadata-input" type="text" value="' + this._escapeHtml(draft.completed_at || "") + '" placeholder="2026-04-21T15:05:00+00:00"></label>' +
          '<label class="metadata-field"><span class="metadata-field-label">Status</span><select id="metadata-correction-status" class="metadata-input"><option value="">Keep current</option>' + ["completed", "failed", "cancelled", "printing"].map(function (statusValue) {
            var selected = String(draft.status || "").trim().toLowerCase() === statusValue ? ' selected' : '';
            return '<option value="' + statusValue + '"' + selected + '>' + statusValue + '</option>';
          }).join("") + '</select></label>' +
          '<label class="metadata-field metadata-field-full"><span class="metadata-field-label">Failure Reason</span><input id="metadata-correction-failure_reason" class="metadata-input" type="text" value="' + this._escapeHtml(draft.failure_reason || "") + '" placeholder="Optional"></label>' +
          '<label class="metadata-field metadata-field-full"><span class="metadata-field-label">Reason</span><textarea id="metadata-correction-reason" class="metadata-textarea" rows="3" placeholder="Document why this correction is needed.">' + this._escapeHtml(draft.reason || "") + '</textarea></label>' +
        '</div>' +
        (this._metadataCorrectionError ? '<div class="metadata-inline-error">' + this._escapeHtml(this._metadataCorrectionError) + '</div>' : '') +
        '<div class="actions-grid metadata-toolbar">' +
          this._renderActionButton("preview-correct-metadata", this._busy && this._busyContext === "metadata-correction-preview" ? "Previewing..." : "Preview Changes", "mdi:clipboard-text-search-outline", { tone: "warning", disabled: this._busy }) +
          this._renderActionButton("apply-correct-metadata", this._busy && this._busyContext === "metadata-correction-apply" ? "Applying..." : "Apply Correction", "mdi:content-save-alert-outline", { tone: "warning", disabled: this._busy || !preview }) +
        '</div>'
      ) +
      this._renderActionSection(
        "Preview",
        preview
          ? '<div class="metadata-preview-summary">' +
              '<div class="metadata-preview-line"><strong>Updated fields:</strong> ' + this._escapeHtml(updatedFields.length ? updatedFields.join(", ") : "none") + '</div>' +
              '<div class="metadata-preview-line"><strong>Correction ID:</strong> ' + this._escapeHtml(String(preview.correction_id || "pending")) + '</div>' +
            '</div>' +
            (warnings.length
              ? '<div class="metadata-warning-list">' + warnings.map(function (warning) {
                  return '<div class="metadata-warning-item">' + this._escapeHtml(String(warning || "")) + '</div>';
                }.bind(this)).join("") + '</div>'
              : '<div class="section-copy">No warnings were returned for this correction preview.</div>') +
            this._renderMetadataCorrectionImpactList(preview.derived_impacts)
          : '<div class="section-copy">Run Preview Changes to validate the update, see warnings, and review runtime/day-bucket impacts before applying.</div>'
      ) +
      '</div>';
  }

  _resolveArchivePreviewImage(archive) {
    var baseUrl = this._getBaseUrl();
    var archiveId = archive && archive.id != null ? archive.id : null;
    if (!baseUrl || archiveId == null) {
      return null;
    }

    var selectedPrimaryPhotoPath = String((archive && archive.selected_primary_photo_path) || "").trim();
    var primaryPhotoPath = String((archive && archive.primary_photo_path) || "").trim();
    var thumbnailPath = String((archive && archive.thumbnail_path) || "").trim();
    var hasPrimaryOverride = archive && archive.has_primary_photo_override != null
      ? !!archive.has_primary_photo_override
      : !!selectedPrimaryPhotoPath;
    var photos = Array.isArray(archive && archive.photos) ? archive.photos : [];
    var fallbackPhotoPath = photos.length ? String(photos[0] || "").trim() : "";

    if (thumbnailPath && !hasPrimaryOverride) {
      return {
        src: this._withArchiveMediaCacheKey(
          baseUrl + "/api/v1/archives/" + encodeURIComponent(String(archiveId)) + "/thumbnail",
          archive
        ),
        alt: archive && archive.print_name ? String(archive.print_name) : "Archive thumbnail",
      };
    }

    var previewPhotoPath = selectedPrimaryPhotoPath || primaryPhotoPath || fallbackPhotoPath;
    if (previewPhotoPath) {
      return {
        src: this._withArchiveMediaCacheKey(
          baseUrl + "/api/v1/archives/" + encodeURIComponent(String(archiveId)) + "/photos/" + encodeURIComponent(previewPhotoPath),
          archive
        ),
        alt: archive && archive.print_name ? String(archive.print_name) : "Archive preview",
      };
    }

    if (thumbnailPath) {
      return {
        src: this._withArchiveMediaCacheKey(
          baseUrl + "/api/v1/archives/" + encodeURIComponent(String(archiveId)) + "/thumbnail",
          archive
        ),
        alt: archive && archive.print_name ? String(archive.print_name) : "Archive thumbnail",
      };
    }

    return null;
  }

  _detectPlatform() {
    var userAgent = String(navigator.userAgent || "").toLowerCase();
    var platform = String(navigator.platform || "").toLowerCase();
    if (userAgent.indexOf("win") >= 0 || platform.indexOf("win") >= 0) {
      return "windows";
    }
    if (userAgent.indexOf("mac") >= 0 || platform.indexOf("mac") >= 0) {
      return "macos";
    }
    if (userAgent.indexOf("linux") >= 0 || platform.indexOf("linux") >= 0) {
      return "linux";
    }
    return "unknown";
  }

  _buildSlicerLaunchUrl(downloadUrl) {
    var normalized = String(downloadUrl || "").trim();
    if (!normalized) {
      return "";
    }
    if (this._detectPlatform() === "macos") {
      return "bambustudioopen://" + encodeURIComponent(normalized);
    }
    return "bambustudio://open?file=" + normalized;
  }

  _openWindow(url, target) {
    var normalized = String(url || "").trim();
    if (!normalized) {
      return;
    }
    var anchor = document.createElement("a");
    anchor.href = normalized;
    anchor.target = target || "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  }

  _statisticsNavigationUrl(extraParams) {
    var basePath = "/3d-printing/statistics";
    var params = extraParams && typeof extraParams === "object" ? extraParams : {};
    var query = new URLSearchParams();
    Object.keys(params).forEach(function (key) {
      var value = params[key];
      if (value == null || value === "") {
        return;
      }
      query.set(key, String(value));
    });
    var queryString = query.toString();
    return queryString ? basePath + "?" + queryString : basePath;
  }

  async _requestArchiveAction(intent) {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    if (!this._hass || typeof this._hass.callWS !== "function" || archiveId <= 0) {
      throw new Error("Archive action context is unavailable");
    }
    return this._hass.callWS({
      type: "bambuddy/print_history_archive_action",
      archive_id: archiveId,
      intent: intent,
    });
  }

  async _handleOpenInSlicer() {
    try {
      this._setBusy(true, "Preparing slicer launch...", "info");
      var response = await this._requestArchiveAction("open_in_slicer");
      var launchUrl = this._buildSlicerLaunchUrl(response && response.download_url ? response.download_url : "");
      if (!launchUrl) {
        throw new Error("No slicer launch URL was returned for this archive");
      }
      this._openWindow(launchUrl, "_self");
      this._busy = false;
      this._setStatus("Opening in slicer...", "success");
    } catch (error) {
      this._busy = false;
      this._setStatus(this._describeError(error, "Could not open the archive in slicer"), "error");
    }
  }

  async _handleDownload(intent, preparingMessage, successMessage) {
    try {
      this._setBusy(true, preparingMessage || "Preparing download...", "info");
      var response = await this._requestArchiveAction(intent || "download");
      var downloadUrl = response && response.download_url ? String(response.download_url) : "";
      if (!downloadUrl) {
        throw new Error("No download URL was returned for this archive");
      }
      this._openWindow(downloadUrl, "_blank");
      this._busy = false;
      this._setStatus(successMessage || "Download started.", "success");
    } catch (error) {
      this._busy = false;
      this._setStatus(this._describeError(error, "Could not start the download"), "error");
    }
  }

  async _openFailureAnalysis() {
    var archive = this._resolveArchive();
    var navigationUrl = this._statisticsNavigationUrl({
      source: "print_history",
      archive_id: archive && archive.id != null ? archive.id : "",
      printer_id: archive && archive.printer_id != null ? archive.printer_id : "",
      project_id: archive && archive.project_id != null ? archive.project_id : "",
    });

    if (this._hass && typeof this._hass.callService === "function") {
      try {
        await this._hass.callService("browser_mod", "close_popup", {});
      } catch (_error) {
        // Ignore popup-close failures and still navigate.
      }
    }
    this._openWindow(navigationUrl, "_self");
  }

  _decodeHtmlEntities(value) {
    if (!value) {
      return "";
    }
    var textarea = document.createElement("textarea");
    textarea.innerHTML = String(value);
    return textarea.value;
  }

  _makerWorldUrl(archive) {
    var directUrl = String((archive && archive.makerworld_url) || "").trim();
    if (!directUrl) {
      return "";
    }
    var decodedUrl = directUrl;
    for (var index = 0; index < 3; index += 1) {
      var nextValue = this._decodeHtmlEntities(decodedUrl).trim();
      if (!nextValue || nextValue === decodedUrl) {
        break;
      }
      decodedUrl = nextValue;
    }
    var urlMatch = decodedUrl.match(/https?:\/\/makerworld\.com\/[^\s"'<>]+/i);
    var normalizedUrl = urlMatch ? String(urlMatch[0]).trim() : "";
    if (!normalizedUrl || !/\/models\/\d+/i.test(normalizedUrl)) {
      return "";
    }
    return normalizedUrl;
  }

  _handleMakerWorld() {
    var url = this._makerWorldUrl(this._resolveArchive());
    if (!url) {
      this._setStatus("No MakerWorld link is available for this archive.", "error");
      return;
    }
    this._openWindow(url, "_blank");
  }

  _openSourceUploadPicker() {
    if (this._busy) {
      return;
    }
    var input = this.shadowRoot ? this.shadowRoot.getElementById("source-upload-input") : null;
    if (!input) {
      return;
    }
    input.value = "";
    try {
      if (typeof input.showPicker === "function") {
        input.showPicker();
        return;
      }
    } catch (_error) {
      // Fall back to click().
    }
    input.click();
  }

  _openTimelapseUploadPicker() {
    if (this._busy) {
      return;
    }
    var input = this.shadowRoot ? this.shadowRoot.getElementById("timelapse-upload-input") : null;
    if (!input) {
      return;
    }
    input.value = "";
    try {
      if (typeof input.showPicker === "function") {
        input.showPicker();
        return;
      }
    } catch (_error) {
      // Fall back to click().
    }
    input.click();
  }

  _fileToBase64(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        var result = String(reader.result || "");
        var commaIndex = result.indexOf(",");
        resolve(commaIndex >= 0 ? result.slice(commaIndex + 1) : result);
      };
      reader.onerror = function () {
        reject(new Error("Could not read the selected 3MF file"));
      };
      reader.readAsDataURL(file);
    });
  }

  async _authHeaders(forceRefresh) {
    var auth = this._hass && this._hass.auth ? this._hass.auth : null;
    if (!auth) {
      return {};
    }

    if (forceRefresh && typeof auth.refreshAccessToken === "function") {
      try {
        await auth.refreshAccessToken();
      } catch (_error) {
        // Fall through and use the last known token if refresh fails.
      }
    }

    var accessToken = auth.accessToken || (auth.data ? auth.data.accessToken : "");
    return accessToken ? { Authorization: "Bearer " + accessToken } : {};
  }

  _normalizeServiceResponse(payload) {
    if (payload && typeof payload === "object") {
      if (payload.service_response && typeof payload.service_response === "object") {
        return payload.service_response;
      }
      if (payload.response && typeof payload.response === "object") {
        return payload.response;
      }
    }
    return payload && typeof payload === "object" ? payload : {};
  }

  async _callServiceWithResponse(domain, service, data) {
    if (!this._hass) {
      throw new Error("Home Assistant context is unavailable");
    }
    var endpoint = "/api/services/" + encodeURIComponent(String(domain || "")) + "/" + encodeURIComponent(String(service || "")) + "?return_response";
    var requestBody = JSON.stringify(data && typeof data === "object" ? data : {});
    var response = await fetch(endpoint, {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, await this._authHeaders(false)),
      credentials: "same-origin",
      body: requestBody,
    });
    if (response.status === 401) {
      response = await fetch(endpoint, {
        method: "POST",
        headers: Object.assign({ "Content-Type": "application/json" }, await this._authHeaders(true)),
        credentials: "same-origin",
        body: requestBody,
      });
    }

    var payload = {};
    try {
      payload = await response.json();
    } catch (_error) {
      payload = {};
    }

    if (!response.ok) {
      throw payload && typeof payload === "object"
        ? {
            message: String(payload.message || payload.error || ("Service call failed (HTTP " + String(response.status) + ")")),
            body: payload,
            status: response.status,
          }
        : new Error("Service call failed (HTTP " + String(response.status) + ")");
    }

    return this._normalizeServiceResponse(payload);
  }

  _buildSourceUploadFormData(file) {
    var formData = new FormData();
    formData.append("file", file, file.name);
    if (this._config && this._config.entry_id) {
      formData.append("entry_id", String(this._config.entry_id));
    }
    return formData;
  }

  async _materializeSourceUploadFile(file) {
    if (!file) {
      throw new Error("No 3MF file was selected");
    }
    if (typeof file.arrayBuffer !== "function") {
      return file;
    }

    var buffer = await file.arrayBuffer();
    if (!buffer || buffer.byteLength === 0) {
      throw new Error("The selected 3MF file is empty");
    }

    var contentType = String(file.type || "application/vnd.ms-package.3dmanufacturing-3dmodel+xml").trim() || "application/vnd.ms-package.3dmanufacturing-3dmodel+xml";
    if (typeof File === "function") {
      return new File([buffer], String(file.name || "upload.3mf"), {
        type: contentType,
        lastModified: typeof file.lastModified === "number" ? file.lastModified : Date.now(),
      });
    }

    return new Blob([buffer], { type: contentType });
  }

  _normalizeTimelapseFileName(fileName) {
    var rawName = String(fileName || "").trim().replace(/[\\/]+/g, "/").split("/").pop() || "timelapse.mp4";
    var match = rawName.match(/^(.*?)(\.[^.]+)$/);
    if (!match) {
      return rawName;
    }
    return match[1] + match[2].toLowerCase();
  }

  _timelapseMimeTypeForFile(fileName, fileType) {
    var lowerName = String(fileName || "").toLowerCase();
    if (/\.avi$/i.test(lowerName)) {
      return "video/x-msvideo";
    }
    if (/\.mkv$/i.test(lowerName)) {
      return "video/x-matroska";
    }
    return String(fileType || "video/mp4").trim() || "video/mp4";
  }

  async _materializeTimelapseUploadFile(file) {
    if (!file) {
      throw new Error("No timelapse file was selected");
    }
    if (typeof file.arrayBuffer !== "function") {
      return file;
    }

    var normalizedName = this._normalizeTimelapseFileName(file.name || "timelapse.mp4");
    var buffer = await file.arrayBuffer();
    if (!buffer || buffer.byteLength === 0) {
      throw new Error("The selected timelapse file is empty");
    }

    var contentType = this._timelapseMimeTypeForFile(normalizedName, file.type);
    if (typeof File === "function") {
      return new File([buffer], normalizedName, {
        type: contentType,
        lastModified: typeof file.lastModified === "number" ? file.lastModified : Date.now(),
      });
    }

    return new Blob([buffer], { type: contentType });
  }

  async _postSourceUpload(file, archiveId) {
    if (file.size === 0) {
      throw new Error("The selected 3MF file is empty") ;
    }

    var uploadFile = await this._materializeSourceUploadFile(file);

    var uploadEndpoint = String(this._config.upload_endpoint || "")
      .replace("{archive_id}", encodeURIComponent(String(archiveId)));
    var response = await fetch(uploadEndpoint, {
      method: "POST",
      body: this._buildSourceUploadFormData(uploadFile),
      headers: await this._authHeaders(false),
      credentials: "same-origin",
    });
    if (response.status === 401) {
      response = await fetch(uploadEndpoint, {
        method: "POST",
        body: this._buildSourceUploadFormData(uploadFile),
        headers: await this._authHeaders(true),
        credentials: "same-origin",
      });
    }

    var payload = {};
    try {
      payload = await response.json();
    } catch (_error) {
      payload = {};
    }

    if (!response.ok || payload.success === false) {
      throw payload && typeof payload === "object"
        ? {
            message: String(payload.message || payload.error || ("Source 3MF upload failed (HTTP " + String(response.status) + ")")),
            body: payload,
            status: response.status,
          }
        : new Error("Source 3MF upload failed (HTTP " + String(response.status) + ")");
    }

    return payload && typeof payload === "object" ? payload : {};
  }

  _buildTimelapseUploadFormData(file) {
    var formData = new FormData();
    formData.append("file", file, file.name);
    if (this._config && this._config.entry_id) {
      formData.append("entry_id", String(this._config.entry_id));
    }
    return formData;
  }

  async _postTimelapseUpload(file, archiveId) {
    if (file.size === 0) {
      throw new Error("The selected timelapse file is empty");
    }

    var uploadFile = await this._materializeTimelapseUploadFile(file);
    var uploadEndpoint = String(this._config.timelapse_upload_endpoint || "")
      .replace("{archive_id}", encodeURIComponent(String(archiveId)));
    var response = await fetch(uploadEndpoint, {
      method: "POST",
      body: this._buildTimelapseUploadFormData(uploadFile),
      headers: await this._authHeaders(false),
      credentials: "same-origin",
    });
    if (response.status === 401) {
      response = await fetch(uploadEndpoint, {
        method: "POST",
        body: this._buildTimelapseUploadFormData(uploadFile),
        headers: await this._authHeaders(true),
        credentials: "same-origin",
      });
    }

    var payload = {};
    try {
      payload = await response.json();
    } catch (_error) {
      payload = {};
    }

    if (!response.ok || payload.success === false) {
      throw payload && typeof payload === "object"
        ? {
            message: String(payload.message || payload.error || ("Timelapse upload failed (HTTP " + String(response.status) + ")")),
            body: payload,
            status: response.status,
          }
        : new Error("Timelapse upload failed (HTTP " + String(response.status) + ")");
    }

    return payload && typeof payload === "object" ? payload : {};
  }

  async _uploadSource3mf(file) {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    if (!file || archiveId <= 0) {
      return;
    }
    if (!/\.3mf$/i.test(String(file.name || ""))) {
      this._setStatus("Source upload only accepts .3mf files.", "error");
      return;
    }

    try {
      this._setBusy(true, "Uploading source 3MF...", "info");
      var response = await this._postSourceUpload(file, archiveId);
      var payload = response && typeof response === "object" ? response : {};
      var nextArchive = payload && payload.archive && typeof payload.archive === "object"
        ? payload.archive
        : payload;
      this._busy = false;
      this._setArchive(nextArchive);
      this._setStatus("Source 3MF uploaded.", "success");
    } catch (error) {
      this._busy = false;
      this._setStatus(this._describeError(error, "Source 3MF upload failed"), "error");
    }
  }

  async _uploadTimelapse(file) {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    if (!file || archiveId <= 0) {
      return;
    }
    if (!/\.(mp4|avi|mkv)$/i.test(String(file.name || ""))) {
      this._setStatus("Timelapse upload only accepts .mp4, .avi, or .mkv files.", "error");
      return;
    }

    try {
      this._setBusyState(true, this._timelapsePath(archive) ? "Replacing timelapse..." : "Uploading timelapse...", "info", "upload-timelapse");
      var response = await this._postTimelapseUpload(file, archiveId);
      var payload = response && typeof response === "object" ? response : {};
      var nextArchive = payload && payload.archive && typeof payload.archive === "object"
        ? payload.archive
        : payload;
      this._busy = false;
      this._busyContext = "";
      this._setArchive(nextArchive);
      this._setStatus(payload && payload.upload && payload.upload.replaced_existing ? "Timelapse replaced." : "Timelapse uploaded.", "success");
    } catch (error) {
      this._busy = false;
      this._busyContext = "";
      this._setStatus(this._describeError(error, "Timelapse upload failed"), "error");
    }
  }

  _buildRepairSequence(archive) {
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    var archiveName = archive && archive.print_name ? String(archive.print_name) : "Archive";
    var archiveJson = archive ? JSON.stringify(archive) : "{}";
    return [
      {
        service: "browser_mod.close_popup",
      },
      {
        service: "input_text.set_value",
        data: {
          entity_id: "input_text.print_history_popup_archive_id",
          value: String(archiveId),
        },
      },
      {
        service: "input_text.set_value",
        data: {
          entity_id: "input_text.print_history_restore_source_archive_id",
          value: String(archiveId),
        },
      },
      {
        service: "input_text.set_value",
        data: {
          entity_id: "input_text.print_history_restore_target_archive_id",
          value: "",
        },
      },
      {
        service: "input_text.set_value",
        data: {
          entity_id: "input_text.print_history_restore_upload_session_id",
          value: "",
        },
      },
      {
        service: "bambuddy.clear_print_history_archive_restore",
        data: {
          source_archive_id: archiveId,
        },
      },
      {
        service: "browser_mod.popup",
        data: {
          title: "Repair " + archiveName,
          size: "wide",
          content: {
            type: "custom:print-history-archive-restore-card",
            archive_json: archiveJson,
            workflow_entity: "sensor.print_history_popup_restore_workflow",
            detail_entity: "sensor.print_history_popup_archive_detail",
            source_archive_helper: "input_text.print_history_restore_source_archive_id",
            target_archive_helper: "input_text.print_history_restore_target_archive_id",
            upload_session_helper: "input_text.print_history_restore_upload_session_id",
          },
        },
      },
    ];
  }

  _buildArchiveTimelapseCardConfig(archive) {
    return {
      type: "custom:print-history-timelapse-card",
      archive_json: archive ? JSON.stringify(archive) : "{}",
      entry_id: this._config && this._config.entry_id ? this._config.entry_id : "",
      detail_entity: this._config && this._config.detail_entity ? this._config.detail_entity : "",
      api_base_entity: this._config && this._config.api_base_entity ? this._config.api_base_entity : "input_text.bambuddy_api_base_url",
      title: "Timelapse",
    };
  }

  _buildArchiveTimelapseEditorCardConfig(archive) {
    return {
      type: "custom:print-history-timelapse-editor-card",
      archive_json: archive ? JSON.stringify(archive) : "{}",
      entry_id: this._config && this._config.entry_id ? this._config.entry_id : "",
      detail_entity: this._config && this._config.detail_entity ? this._config.detail_entity : "",
      title: "Timelapse Editor",
    };
  }

  _buildArchiveTimelapsePopupContent(archive) {
    return {
      type: "vertical-stack",
      cards: [
        this._buildArchiveTimelapseCardConfig(archive),
        this._buildArchiveTimelapseEditorCardConfig(archive),
      ],
    };
  }

  _timelapsePath(archive) {
    var directPath = String(archive && archive.timelapse_path || "").trim();
    if (directPath) {
      return directPath;
    }
    var storagePath = archive
      && archive.storage_metrics
      && archive.storage_metrics.artifacts
      && archive.storage_metrics.artifacts.timelapse_path
      && archive.storage_metrics.artifacts.timelapse_path.relative_path;
    return String(storagePath || "").trim();
  }

  _openTimelapsePopup() {
    var archive = this._resolveArchive();
    var timelapsePath = this._timelapsePath(archive);
    if (!archive || archive.id == null || !timelapsePath) {
      return;
    }
    this._fireBrowserModEvent("browser_mod.popup", {
      title: "Timelapse",
      size: "wide",
      content: this._buildArchiveTimelapsePopupContent(archive),
    });
  }

  _scanResultMessage(response) {
    var scanResult = response && typeof response === "object" && response.scan_result && typeof response.scan_result === "object"
      ? response.scan_result
      : {};
    var message = String(scanResult.message || response && response.message || "").trim();
    var availableFiles = Array.isArray(scanResult.available_files) ? scanResult.available_files : [];
    if (scanResult.status === "not_found" && availableFiles.length > 0) {
      return message + " Found " + String(availableFiles.length) + " candidate file" + (availableFiles.length === 1 ? "" : "s") + " on the printer.";
    }
    return message || "Timelapse scan finished.";
  }

  _scanResultTone(response) {
    var status = String(response && response.status || response && response.scan_result && response.scan_result.status || "").trim();
    if (status === "attached") {
      return "success";
    }
    if (status === "exists" || status === "not_found") {
      return "info";
    }
    return "error";
  }

  async _callStorageMetricsService(service, archiveId, forceRefresh) {
    if (!this._hass || typeof this._hass.callService !== "function" || archiveId <= 0) {
      throw new Error("Archive action context is unavailable");
    }
    var payload = {
      archive_id: archiveId,
      include_other_files: true,
      include_extension_breakdown: false,
    };
    if (service === "get_print_history_archive_storage_metrics") {
      payload.refresh = !!forceRefresh;
    }
    if (this._config && this._config.entry_id) {
      payload.entry_id = String(this._config.entry_id);
    }
    return this._callServiceWithResponse("bambuddy", service, payload);
  }

  async _fetchArchiveStorageMetrics(forceRefresh) {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    if (archiveId <= 0) {
      throw new Error("Archive action context is unavailable");
    }
    var response = await this._callStorageMetricsService(
      forceRefresh ? "refresh_print_history_archive_storage_metrics" : "get_print_history_archive_storage_metrics",
      archiveId,
      forceRefresh
    );
    if (!response || response.success === false) {
      throw new Error((response && (response.message || response.error)) || "Storage metrics request failed");
    }
    var metricsPayload = response && response.storage_metrics && typeof response.storage_metrics === "object"
      ? response.storage_metrics
      : null;
    if (!metricsPayload) {
      throw new Error("Storage metrics response did not include a metrics payload");
    }
    this._storageMetricsLoadedKey = String(archiveId);
    this._storageMetricsRequestKey = "";
    this._mergeArchivePatch({ storage_metrics: metricsPayload });
    return metricsPayload;
  }

  _maybeLoadStorageMetrics() {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    if (!archiveId || this._busy) {
      return;
    }
    if (archive && archive.storage_metrics && typeof archive.storage_metrics === "object") {
      this._storageMetricsLoadedKey = String(archiveId);
      return;
    }
    if (this._storageMetricsLoadedKey === String(archiveId) || this._storageMetricsRequestKey === String(archiveId)) {
      return;
    }
    this._storageMetricsRequestKey = String(archiveId);
    this._fetchArchiveStorageMetrics(false).catch(function () {
      this._storageMetricsRequestKey = "";
    }.bind(this));
  }

  async _handleRefreshStorageMetrics() {
    try {
      this._setBusyState(true, "Refreshing storage metrics...", "info", "storage-metrics");
      var storageMetrics = await this._fetchArchiveStorageMetrics(true);
      var totalBytes = storageMetrics && storageMetrics.metrics ? Number(storageMetrics.metrics.total_bytes || 0) : 0;
      this._busy = false;
      this._busyContext = "";
      this._setStatus(totalBytes > 0 ? ("Storage metrics refreshed. Total tracked storage: " + this._formatBytes(totalBytes) + ".") : "Storage metrics refreshed.", "success");
    } catch (error) {
      this._busy = false;
      this._busyContext = "";
      this._setStatus(this._describeError(error, "Storage metrics refresh failed"), "error");
    }
  }

  async _handleScanTimelapse() {
    try {
      this._setBusyState(true, "Scanning printer for timelapse...", "info", "scan-timelapse");
      var response = await this._requestArchiveAction("scan_timelapse");
      var nextArchive = response && response.archive && typeof response.archive === "object"
        ? response.archive
        : null;
      this._busy = false;
      this._busyContext = "";
      if (nextArchive) {
        this._setArchive(nextArchive);
      }
      this._setStatus(this._scanResultMessage(response), this._scanResultTone(response));
    } catch (error) {
      this._busy = false;
      this._busyContext = "";
      this._setStatus(this._describeError(error, "Timelapse scan failed"), "error");
    }
  }

  async _handleRepair() {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    if (archiveId <= 0) {
      return;
    }
    this._fireBrowserModEvent("browser_mod.sequence", {
      sequence: this._buildRepairSequence(archive),
    });
  }

  async _handleDelete() {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    if (!this._hass || typeof this._hass.callService !== "function" || archiveId <= 0) {
      return;
    }
    try {
      this._setBusy(true, "Deleting archive...", "info");
      await this._hass.callService("bambuddy", "delete_print_history_archive", {
        archive_id: archiveId,
      });
      await this._hass.callService("browser_mod", "close_popup", {});
    } catch (error) {
      this._busy = false;
      this._setStatus(this._describeError(error, "Archive delete failed"), "error");
    }
  }

  _escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _storageMetricsData(archive) {
    return archive && archive.storage_metrics && typeof archive.storage_metrics === "object"
      ? archive.storage_metrics
      : null;
  }

  _formatBytes(value) {
    var bytes = Number(value || 0);
    if (!isFinite(bytes) || bytes <= 0) {
      return "0 B";
    }
    var units = ["B", "KB", "MB", "GB", "TB"];
    var unitIndex = 0;
    var normalized = bytes;
    while (normalized >= 1024 && unitIndex < units.length - 1) {
      normalized /= 1024;
      unitIndex += 1;
    }
    var precision = normalized >= 100 || unitIndex === 0 ? 0 : normalized >= 10 ? 1 : 2;
    return normalized.toFixed(precision) + " " + units[unitIndex];
  }

  _storageMetricsSummaryLine(archive) {
    var storage = this._storageMetricsData(archive);
    if (!storage) {
      return "";
    }
    var metrics = storage.metrics && typeof storage.metrics === "object" ? storage.metrics : {};
    var totalBytes = Number(metrics.total_bytes || 0);
    if (isFinite(totalBytes) && totalBytes > 0) {
      return "Tracked storage: " + this._formatBytes(totalBytes);
    }
    if (storage.scan_status === "partial") {
      return "Storage metrics are partial for this archive.";
    }
    if (storage.scan_status === "missing") {
      return "Storage scan found no archive files.";
    }
    return "";
  }

  _storageBreakdownRows(archive) {
    var storage = this._storageMetricsData(archive);
    var metrics = storage && storage.metrics && typeof storage.metrics === "object" ? storage.metrics : {};
    return [
      { label: "Archive 3MF", value: this._formatBytes(metrics.archive_3mf_bytes || 0) },
      { label: "Thumbnail", value: this._formatBytes(metrics.thumbnail_bytes || 0) },
      { label: "Source 3MF", value: this._formatBytes(metrics.source_3mf_bytes || 0) },
      { label: "Timelapse", value: this._formatBytes(metrics.timelapse_bytes || 0) },
      { label: "F3D", value: this._formatBytes(metrics.f3d_bytes || 0) },
      {
        label: "Photos",
        value: this._formatBytes(metrics.photo_bytes || 0) + (Number(metrics.photo_count || 0) > 0 ? " · " + String(Number(metrics.photo_count || 0)) + " files" : ""),
      },
      {
        label: "Other Files",
        value: this._formatBytes(metrics.other_bytes || 0) + (Number(metrics.other_file_count || 0) > 0 ? " · " + String(Number(metrics.other_file_count || 0)) + " files" : ""),
      },
      { label: "Total", value: this._formatBytes(metrics.total_bytes || 0), accent: true },
    ];
  }

  _renderStorageSection(archive) {
    var storage = this._storageMetricsData(archive);
    var metrics = storage && storage.metrics && typeof storage.metrics === "object" ? storage.metrics : {};
    var scanStatus = storage && storage.scan_status ? String(storage.scan_status) : "not_scanned";
    var computedAt = storage && storage.computed_at ? String(storage.computed_at) : "";
    var scanError = storage && storage.scan_error ? String(storage.scan_error) : "";
    var missingCount = Number(metrics.files_missing_count || 0);
    var summaryCopy = !storage
      ? "Load the cached storage scan for this archive or refresh it from the Bambuddy sidecar. This helps break down space usage across the archive 3MF, source file, photos, timelapse, and unclassified leftovers."
      : scanStatus === "complete"
        ? "This breakdown comes from the local storage metrics cache backed by the Bambuddy sidecar filesystem scan."
        : scanStatus === "partial"
          ? "This archive has a partial storage scan. Some files were missing or the archive folder could not be fully resolved."
          : scanStatus === "missing"
            ? "The sidecar did not find tracked files for this archive."
            : "The storage scan cache is present but not complete yet.";
    var rowsMarkup = !storage
      ? '<div class="section-copy">No storage metrics are cached for this archive yet.</div>'
      : '<div class="storage-grid">' + this._storageBreakdownRows(archive).map(function (row) {
          return '<div class="storage-metric' + (row.accent ? ' accent' : '') + '">' +
            '<div class="storage-metric-label">' + this._escapeHtml(row.label) + '</div>' +
            '<div class="storage-metric-value">' + this._escapeHtml(row.value) + '</div>' +
          '</div>';
        }.bind(this)).join("") + '</div>';
    var metaParts = [];
    if (computedAt) {
      metaParts.push("Scanned " + computedAt.replace("T", " ").replace("Z", " UTC"));
    }
    if (missingCount > 0) {
      metaParts.push(String(missingCount) + " missing file" + (missingCount === 1 ? "" : "s"));
    }
    if (scanError) {
      metaParts.push(scanError);
    }
    return this._renderActionSection(
      "Storage",
      '<div class="actions-grid single-column">' +
        this._renderActionButton("refresh-storage-metrics", storage ? "Refresh Storage Metrics" : "Load Storage Metrics", "mdi:database-sync-outline", { disabled: this._busy }) +
      '</div>' +
      '<div class="section-copy">' + this._escapeHtml(summaryCopy) + '</div>' +
      rowsMarkup +
      (metaParts.length ? '<div class="storage-meta">' + this._escapeHtml(metaParts.join(" · ")) + '</div>' : '')
    );
  }

  _renderSummary(archive) {
    var previewImage = this._resolveArchivePreviewImage(archive);
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    var archiveName = archive && archive.print_name ? String(archive.print_name) : "Untitled Archive";
    var sourceName = String((archive && archive.source_3mf_path) || "").trim();
    var timelapseName = this._timelapsePath(archive);
    var storageSummary = this._storageMetricsSummaryLine(archive);
    var sourceBadge = sourceName
      ? '<div class="summary-note">Source 3MF attached: ' + this._escapeHtml(sourceName.split(/[\\/]/).pop()) + "</div>"
      : "";
    var timelapseBadge = timelapseName
      ? '<div class="summary-note">Timelapse attached: ' + this._escapeHtml(timelapseName.split(/[\\/]/).pop()) + "</div>"
      : "";
    var storageBadge = storageSummary
      ? '<div class="summary-note">' + this._escapeHtml(storageSummary) + '</div>'
      : "";
    return '<section class="summary-card">' +
      '<div class="summary-grid">' +
      (previewImage && previewImage.src
        ? '<div class="summary-preview"><img src="' + this._escapeHtml(previewImage.src) + '" alt="' + this._escapeHtml(previewImage.alt) + '"></div>'
        : '<div class="summary-preview placeholder"><ha-icon icon="mdi:image-off-outline"></ha-icon></div>') +
      '<div class="summary-meta">' +
      '<div class="summary-title">' + this._escapeHtml(archiveName) + '</div>' +
      '<div class="summary-id">Archive ID #' + this._escapeHtml(String(archiveId)) + '</div>' +
      sourceBadge +
      timelapseBadge +
        storageBadge +
      '</div>' +
      '</div>' +
      '</section>';
  }

  _renderStatus() {
    if (!this._status) {
      return "";
    }
    var busyCopy = this._busy && this._busyContext === "scan-timelapse"
      ? '<div class="status-detail">Bambuddy does not stream scan progress. This waits until printer folders have been checked and a matching file is downloaded or ruled out.</div>'
      : this._busy && this._busyContext === "upload-timelapse"
        ? '<div class="status-detail">Only one timelapse is tracked per archive. Upload accepts .mp4, .avi, or .mkv and large files can take a while before the refreshed archive detail comes back.</div>'
      : "";
    return '<div class="status ' + this._escapeHtml(this._statusTone) + (this._busy ? ' busy' : '') + '"><div class="status-main">' + this._escapeHtml(this._status) + '</div>' + busyCopy + '</div>';
  }

  _renderActionButton(action, label, icon, options) {
    var buttonOptions = options || {};
    var classes = ["action-button"];
    if (buttonOptions.tone) {
      classes.push(buttonOptions.tone);
    }
    if (buttonOptions.wide) {
      classes.push("wide");
    }
    return '<button class="' + classes.join(" ") + '" type="button" data-action="' + this._escapeHtml(action) + '"' +
      (buttonOptions.disabled ? ' disabled' : '') + '>' +
      '<ha-icon icon="' + this._escapeHtml(icon) + '"></ha-icon>' +
      '<span>' + this._escapeHtml(label) + '</span>' +
      '</button>';
  }

  _renderActionSection(title, body, options) {
    var sectionOptions = options || {};
    var classes = ["action-section"];
    if (sectionOptions.tone) {
      classes.push(sectionOptions.tone);
    }
    return '<section class="' + classes.join(" ") + '">' +
      '<div class="section-title">' + this._escapeHtml(title) + '</div>' +
      body +
      '</section>';
  }

  async _requestArchiveRelated(limit) {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    if (!this._hass || typeof this._hass.callWS !== "function" || archiveId <= 0) {
      throw new Error("Archive action context is unavailable");
    }
    return this._hass.callWS({
      type: "bambuddy/print_history_archive_related",
      archive_id: archiveId,
      limit: this._normalizeRelatedCandidateLimit(limit),
    });
  }

  async _requestArchiveCompare(archiveIds) {
    var normalizedIds = this._normalizeCompareArchiveIds(archiveIds);
    if (!this._hass || typeof this._hass.callWS !== "function" || normalizedIds.length < 2) {
      throw new Error("At least 2 archives are required for comparison");
    }
    return this._hass.callWS({
      type: "bambuddy/print_history_archive_compare",
      archive_ids: normalizedIds,
    });
  }

  _normalizeCompareArchiveIds(archiveIds) {
    var values = Array.isArray(archiveIds) ? archiveIds : [archiveIds];
    var normalized = [];
    var seen = {};
    values.forEach(function (value) {
      var archiveId = Number(value || 0);
      if (!archiveId || seen[archiveId]) {
        return;
      }
      seen[archiveId] = true;
      normalized.push(archiveId);
    });
    return normalized;
  }

  _relatedLimitEntityId() {
    return this._config && this._config.related_limit_entity
      ? this._config.related_limit_entity
      : "input_number.print_history_related_candidate_limit";
  }

  _configuredRelatedCandidateLimit() {
    var entityId = this._relatedLimitEntityId();
    var state = entityId && this._hass && this._hass.states ? this._hass.states[entityId] : null;
    var numericValue = Number(state && state.state || 10);
    if (!Number.isFinite(numericValue) || numericValue <= 0) {
      numericValue = 10;
    }
    return Math.max(1, Math.min(20, numericValue));
  }

  _normalizeRelatedCandidateLimit(limit) {
    var numericValue = Number(limit);
    if (!Number.isFinite(numericValue) || numericValue <= 0) {
      return this._configuredRelatedCandidateLimit();
    }
    return Math.max(1, Math.min(20, numericValue));
  }

  _matchingRelatedCandidates(archiveId, limit) {
    var normalizedArchiveId = archiveId != null ? String(archiveId) : "";
    var normalizedLimit = this._normalizeRelatedCandidateLimit(limit);
    if (!normalizedArchiveId || this._relatedArchiveId !== normalizedArchiveId || !Array.isArray(this._relatedCandidates)) {
      return null;
    }
    if (normalizedLimit !== Math.max(1, Number(this._relatedCandidatesLimit || 0))) {
      return null;
    }
    return this._relatedCandidates;
  }

  _setRelatedState(candidates, error, archiveId, compareIntent, limit) {
    this._relatedCandidates = Array.isArray(candidates) ? candidates : [];
    this._relatedCandidatesLimit = this._normalizeRelatedCandidateLimit(limit);
    this._relatedError = String(error || "").trim();
    this._relatedArchiveId = archiveId != null ? String(archiveId) : "";
    this._relatedCompareIntent = !!compareIntent;
    this._lastRenderSignature = "";
    this._render();
  }

  _setCompareState(payload, error, archiveIds, backMode) {
    this._comparePayload = payload && typeof payload === "object" ? payload : null;
    this._compareError = String(error || "").trim();
    this._compareArchiveIds = this._normalizeCompareArchiveIds(archiveIds || []);
    this._compareBackMode = String(backMode || "main");
    this._lastRenderSignature = "";
    this._render();
  }

  _candidateConfidenceBucket(candidate) {
    return String(candidate && candidate.confidence_bucket || "low").trim() || "low";
  }

  _candidateConfidenceLabel(candidate) {
    var bucket = this._candidateConfidenceBucket(candidate);
    if (bucket === "high") {
      return "High confidence";
    }
    if (bucket === "medium") {
      return "Medium confidence";
    }
    return "Low confidence";
  }

  _candidateConfidenceColor(candidate) {
    var bucket = this._candidateConfidenceBucket(candidate);
    if (bucket === "high") {
      return "rgba(46,125,50,0.18)";
    }
    if (bucket === "medium") {
      return "rgba(239,108,0,0.16)";
    }
    return "rgba(84,110,122,0.18)";
  }

  _statusLabel(status) {
    var normalized = String(status || "").trim().toLowerCase();
    if (!normalized) {
      return "Unknown";
    }
    if (normalized === "completed") {
      return "Completed";
    }
    if (normalized === "failed") {
      return "Failed";
    }
    if (normalized === "cancelled") {
      return "Cancelled";
    }
    if (normalized === "archived") {
      return "Archived";
    }
    return normalized.charAt(0).toUpperCase() + normalized.slice(1);
  }

  _statusBadgeClass(status) {
    var normalized = String(status || "").trim().toLowerCase();
    if (normalized === "completed") {
      return "success";
    }
    if (normalized === "failed") {
      return "danger";
    }
    if (normalized === "cancelled") {
      return "warning";
    }
    return "neutral";
  }

  _parseArchiveDate(value) {
    if (!value) {
      return null;
    }
    var raw = String(value || "").trim();
    var normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(raw) ? raw : (raw + "Z");
    var parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  _formatArchiveDate(value) {
    var parsed = this._parseArchiveDate(value);
    if (!parsed) {
      return "Unknown date";
    }
    try {
      return new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(parsed);
    } catch (_error) {
      return parsed.toISOString().slice(0, 10);
    }
  }

  _currentArchiveStatus() {
    var archive = this._resolveArchive();
    return String(archive && archive.status || "").trim().toLowerCase();
  }

  _isFailureContext() {
    var status = this._currentArchiveStatus();
    return status === "failed" || status === "cancelled";
  }

  _isHighConfidenceCompareCandidate(candidate) {
    var matchScore = Number(candidate && candidate.match_score || 0);
    if (matchScore >= 95) {
      return true;
    }
    if (this._isFailureContext()) {
      var currentArchive = this._resolveArchive();
      var currentName = String(currentArchive && currentArchive.print_name || "").trim().toLowerCase();
      var candidateName = String(candidate && candidate.print_name || "").trim().toLowerCase();
      var currentStatus = String(currentArchive && currentArchive.status || "").trim().toLowerCase();
      var candidateStatus = String(candidate && candidate.status || "").trim().toLowerCase();
      if (currentName && candidateName && currentName === candidateName && currentStatus && candidateStatus && currentStatus !== candidateStatus) {
        return true;
      }
    }
    return false;
  }

  _suggestedCompareCandidate(candidates) {
    var normalizedCandidates = Array.isArray(candidates) ? candidates : [];
    if (normalizedCandidates.length === 1) {
      return normalizedCandidates[0];
    }
    var highConfidence = normalizedCandidates.filter(function (candidate) {
      return this._isHighConfidenceCompareCandidate(candidate);
    }.bind(this));
    return highConfidence.length === 1 ? highConfidence[0] : null;
  }

  async _loadRelatedCandidates(options) {
    var settings = options || {};
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    if (archiveId <= 0) {
      this._setStatus("Related prints are unavailable for this archive.", "error");
      return;
    }

    var compareIntent = !!settings.compareIntent;
    var requestedLimit = this._normalizeRelatedCandidateLimit(settings.limit);
    this._mode = "related";
    this._render();

    var cachedCandidates = !settings.forceRefresh ? this._matchingRelatedCandidates(archiveId, requestedLimit) : null;
    if (cachedCandidates) {
      this._relatedCompareIntent = compareIntent;
      if (compareIntent) {
        var suggestedCandidate = this._suggestedCompareCandidate(cachedCandidates);
        if (suggestedCandidate) {
          await this._loadCompareForArchives([archiveId, suggestedCandidate.archive_id], "related");
          return;
        }
      }
      this._lastRenderSignature = "";
      this._render();
      return;
    }

    try {
      this._setBusyState(true, compareIntent ? "Loading compare candidates..." : "Loading related prints...", "info", "related");
      var response = await this._requestArchiveRelated(requestedLimit);
      var candidates = response && Array.isArray(response.candidates) ? response.candidates : [];
      this._busy = false;
      this._busyContext = "";
      this._setRelatedState(candidates, "", archiveId, compareIntent, response && response.limit);
      if (!candidates.length) {
        this._setStatus(compareIntent ? "No compare candidates were found for this print." : "No related prints were found for this archive.", "info");
        return;
      }
      if (compareIntent) {
        var bestCandidate = this._suggestedCompareCandidate(candidates);
        if (bestCandidate) {
          await this._loadCompareForArchives([archiveId, bestCandidate.archive_id], "related");
          return;
        }
        this._setStatus("Choose a related print to compare against this archive.", "info");
        return;
      }
      this._setStatus("Related prints loaded.", "success");
    } catch (error) {
      this._busy = false;
      this._busyContext = "";
      var message = this._describeError(error, compareIntent ? "Could not load compare candidates" : "Could not load related prints");
      this._setRelatedState([], message, archiveId, compareIntent);
      this._setStatus(message, "error");
    }
  }

  async _loadCompareForArchives(archiveIds, backMode) {
    var normalizedIds = this._normalizeCompareArchiveIds(archiveIds);
    if (normalizedIds.length < 2) {
      this._setStatus("Choose at least two archives to compare.", "error");
      return;
    }

    this._mode = "compare";
    this._render();

    try {
      this._setBusyState(true, "Loading archive comparison...", "info", "compare");
      var response = await this._requestArchiveCompare(normalizedIds);
      this._busy = false;
      this._busyContext = "";
      this._setCompareState(response, "", normalizedIds, backMode || "main");
      this._setStatus("Archive comparison loaded.", "success");
    } catch (error) {
      this._busy = false;
      this._busyContext = "";
      var message = this._describeError(error, "Could not load archive comparison");
      this._setCompareState(null, message, normalizedIds, backMode || "main");
      this._setStatus(message, "error");
    }
  }

  async _handleCompareAgainstArchive(candidateArchiveId) {
    var archive = this._resolveArchive();
    var currentArchiveId = archive && archive.id != null ? Number(archive.id) : 0;
    var normalizedCandidateId = Number(candidateArchiveId || 0);
    if (currentArchiveId <= 0 || normalizedCandidateId <= 0) {
      this._setStatus("Compare target is unavailable.", "error");
      return;
    }
    await this._loadCompareForArchives([currentArchiveId, normalizedCandidateId], "related");
  }

  _buildArchiveDetailPopupContent(archive) {
    var archiveJson = archive ? JSON.stringify(archive) : "{}";
    return {
      type: "vertical-stack",
      cards: [
        {
          type: "custom:print-history-photo-gallery-card",
          archive_json: archiveJson,
          detail_entity: "sensor.print_history_popup_archive_detail",
          api_base_entity: this._config && this._config.api_base_entity ? this._config.api_base_entity : "input_text.bambuddy_api_base_url",
          visibility_entity: "input_boolean.print_history_show_images",
          include_thumbnail: true,
        },
        {
          type: "custom:button-card",
          template: "print_history_archive_popup_content",
          entity: "sensor.print_history_popup_archive_detail",
          triggers_update: ["sensor.print_history_popup_archive_detail", "input_boolean.print_history_popup_is_favorite"],
          variables: {
            archive_json: archiveJson,
          },
          tap_action: { action: "none" },
          hold_action: { action: "none" },
        },
      ],
    };
  }

  _openArchiveDetailPopup(archive) {
    if (!archive || archive.id == null) {
      return;
    }
    var archiveId = Number(archive.id);
    var popupTitle = String(archive.print_name || ("Archive " + archiveId)) + " · #" + String(archiveId);
    this._fireBrowserModEvent("browser_mod.sequence", {
      sequence: [
        {
          service: "input_text.set_value",
          data: {
            entity_id: "input_text.print_history_popup_archive_id",
            value: String(archiveId),
          },
        },
        {
          service: archive.is_favorite ? "input_boolean.turn_on" : "input_boolean.turn_off",
          data: {
            entity_id: "input_boolean.print_history_popup_is_favorite",
          },
        },
        {
          service: "browser_mod.popup",
          data: {
            title: popupTitle,
            size: "normal",
            content: this._buildArchiveDetailPopupContent(archive),
          },
        },
      ],
    });
  }

  async _handleOpenRelatedArchive(candidateArchiveId) {
    var normalizedCandidateId = Number(candidateArchiveId || 0);
    if (normalizedCandidateId <= 0) {
      this._setStatus("Related archive details are unavailable.", "error");
      return;
    }

    try {
      this._setBusyState(true, "Loading archive popup...", "info", "related-open");
      var detail = await this._callArchiveDetailService(normalizedCandidateId);
      var archive = detail && detail.archive && typeof detail.archive === "object"
        ? detail.archive
        : null;
      this._busy = false;
      this._busyContext = "";
      if (!archive) {
        throw new Error("Archive detail did not include archive data");
      }
      this._openArchiveDetailPopup(archive);
      this._setStatus("Archive popup opened.", "success");
    } catch (error) {
      this._busy = false;
      this._busyContext = "";
      this._setStatus(this._describeError(error, "Could not open the related archive popup"), "error");
    }
  }

  _renderRelatedCandidate(candidate) {
    var archiveId = Number(candidate && candidate.archive_id || 0);
    var score = Number(candidate && candidate.match_score || 0);
    var statusLabel = this._statusLabel(candidate && candidate.status);
    var confidenceLabel = this._candidateConfidenceLabel(candidate);
    return '<div class="related-candidate">' +
      '<div class="related-candidate-header">' +
        '<div class="related-candidate-title-block">' +
          '<div class="related-candidate-title">' + this._escapeHtml(String(candidate && candidate.print_name || ("Archive " + archiveId))) + '</div>' +
          '<div class="related-candidate-meta">#' + this._escapeHtml(String(archiveId)) + ' · ' + this._escapeHtml(this._formatArchiveDate(candidate && candidate.created_at)) + '</div>' +
        '</div>' +
        '<div class="related-candidate-badges">' +
          '<span class="candidate-status ' + this._escapeHtml(this._statusBadgeClass(candidate && candidate.status)) + '">' + this._escapeHtml(statusLabel) + '</span>' +
          '<span class="candidate-score" style="background:' + this._escapeHtml(this._candidateConfidenceColor(candidate)) + ';">' + this._escapeHtml(confidenceLabel + ' · ' + score) + '</span>' +
        '</div>' +
      '</div>' +
      '<div class="related-candidate-copy">' + this._escapeHtml(String(candidate && candidate.match_reason || "Related candidate")) + '</div>' +
      '<div class="actions-grid related-actions">' +
        this._renderActionButton("related-open", "Open Archive", "mdi:open-in-new", { disabled: this._busy || archiveId <= 0 })
          .replace('data-action="related-open"', 'data-action="related-open" data-archive-id="' + this._escapeHtml(String(archiveId)) + '"') +
        this._renderActionButton("related-compare", "Compare with This Print", "mdi:compare-horizontal", { disabled: this._busy || archiveId <= 0 })
          .replace('data-action="related-compare"', 'data-action="related-compare" data-archive-id="' + this._escapeHtml(String(archiveId)) + '"') +
      '</div>' +
    '</div>';
  }

  _relatedConfidenceGroups(candidates) {
    var grouped = {
      high: [],
      medium: [],
      low: [],
    };
    (Array.isArray(candidates) ? candidates : []).forEach(function (candidate) {
      var bucket = this._candidateConfidenceBucket(candidate);
      if (!grouped[bucket]) {
        grouped.low.push(candidate);
        return;
      }
      grouped[bucket].push(candidate);
    }.bind(this));
    return grouped;
  }

  _renderRelatedCandidateGroup(title, copy, candidates, toneClass) {
    if (!Array.isArray(candidates) || !candidates.length) {
      return "";
    }
    return '<div class="related-confidence-group ' + this._escapeHtml(String(toneClass || "neutral")) + '">' +
      '<div class="related-confidence-header">' +
        '<div class="related-confidence-title">' + this._escapeHtml(title) + '</div>' +
        '<div class="related-confidence-count">' + this._escapeHtml(String(candidates.length)) + '</div>' +
      '</div>' +
      '<div class="section-copy">' + this._escapeHtml(copy) + '</div>' +
      '<div class="related-list">' + candidates.map(function (candidate) {
        return this._renderRelatedCandidate(candidate);
      }.bind(this)).join("") + '</div>' +
    '</div>';
  }

  _renderRelatedView(archive) {
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    var configuredLimit = this._configuredRelatedCandidateLimit();
    var candidates = this._matchingRelatedCandidates(archiveId, configuredLimit) || [];
    var groupedCandidates = this._relatedConfidenceGroups(candidates);
    var toolbar = this._renderActionSection(
      this._relatedCompareIntent ? "Choose Compare Target" : "Related Prints",
      '<div class="actions-grid related-toolbar">' +
        this._renderActionButton("back-main", "Back to Actions", "mdi:arrow-left", { disabled: this._busy }) +
        this._renderActionButton(this._relatedCompareIntent ? "open-compare" : "open-related", this._busy ? "Loading..." : "Refresh Matches", "mdi:refresh", { disabled: this._busy }) +
      '</div>' +
      '<div class="section-copy">' + this._escapeHtml(
        this._relatedCompareIntent
          ? "Compare starts from the same on-demand related-candidate feed. Exact content matches and failure-to-success pairs are preferred when a clear suggestion exists, and Home Assistant now applies a stable score-first sort instead of newest-first ordering."
          : "These candidates come from Bambuddy on demand. Exact duplicate-family matches rank above weaker name or filament suggestions, and Home Assistant now keeps the list score-first without a newest-first bias."
      ) + '</div>' +
      '<div class="section-copy">' + this._escapeHtml('Requesting up to ' + configuredLimit + ' related candidates per archive from the configuration popup.') + '</div>'
    );
    var body;
    if (this._relatedError) {
      body = '<div class="section-copy">' + this._escapeHtml(this._relatedError) + '</div>';
    } else if (!candidates.length) {
      body = '<div class="section-copy">No related prints are available for this archive yet.</div>';
    } else {
      body = '<div class="related-groups">' +
        this._renderRelatedCandidateGroup(
          "High Confidence",
          "Strongest matches. In Bambuddy today this is typically same print name or same file content, and these are the best default compare targets.",
          groupedCandidates.high,
          "high"
        ) +
        this._renderRelatedCandidateGroup(
          "Medium Confidence",
          "Possible matches worth checking when there is no clear high-confidence candidate.",
          groupedCandidates.medium,
          "medium"
        ) +
        this._renderRelatedCandidateGroup(
          "Low Confidence",
          "Fallback suggestions only. In Bambuddy today these are usually broader matches such as the same filament type, so treat them as browse candidates rather than implied lineage.",
          groupedCandidates.low,
          "low"
        ) +
      '</div>';
    }
    return '<div class="section-stack">' + toolbar + this._renderActionSection("Candidates", body) + '</div>';
  }

  _renderCompareTable(comparePayload) {
    var archives = comparePayload && Array.isArray(comparePayload.archives) ? comparePayload.archives : [];
    var comparisonRows = comparePayload && Array.isArray(comparePayload.comparison) ? comparePayload.comparison : [];
    if (!archives.length || !comparisonRows.length) {
      return '<div class="section-copy">Comparison details are unavailable.</div>';
    }
    return '<div class="compare-table-wrap"><table class="compare-table"><thead><tr><th>Setting</th>' +
      archives.map(function (archive) {
        return '<th><div class="compare-archive-name">' + this._escapeHtml(String(archive && archive.print_name || ("Archive " + archive.id))) + '</div>' +
          '<div class="compare-archive-status ' + this._escapeHtml(this._statusBadgeClass(archive && archive.status)) + '">' + this._escapeHtml(this._statusLabel(archive && archive.status)) + '</div></th>';
      }.bind(this)).join("") +
      '</tr></thead><tbody>' + comparisonRows.map(function (row) {
        var values = Array.isArray(row.values) ? row.values : [];
        return '<tr' + (row.has_difference ? ' class="difference"' : '') + '><td class="compare-field">' + this._escapeHtml(String(row.label || row.field || "Field")) + '</td>' +
          values.map(function (value) {
            var cellValue = value == null || value === "" ? "-" : String(value);
            return '<td>' + this._escapeHtml(cellValue) + (row.unit && cellValue !== '-' ? '<span class="compare-unit"> ' + this._escapeHtml(String(row.unit)) + '</span>' : '') + '</td>';
          }.bind(this)).join("") + '</tr>';
      }.bind(this)).join("") + '</tbody></table></div>';
  }

  _renderCompareInsights(comparePayload) {
    var successCorrelation = comparePayload && comparePayload.success_correlation && typeof comparePayload.success_correlation === "object"
      ? comparePayload.success_correlation
      : null;
    if (!successCorrelation) {
      return '<div class="section-copy">Success analysis is unavailable for this comparison.</div>';
    }
    if (!successCorrelation.has_both_outcomes) {
      return '<div class="section-copy">' + this._escapeHtml(String(successCorrelation.message || "Need both successful and failed prints to analyze correlation.")) + '</div>';
    }
    var insights = Array.isArray(successCorrelation.insights) ? successCorrelation.insights : [];
    return '<div class="compare-insights">' +
      '<div class="compare-insight-meta">' + this._escapeHtml(String(successCorrelation.successful_count || 0)) + ' successful · ' + this._escapeHtml(String(successCorrelation.failed_count || 0)) + ' failed</div>' +
      (insights.length
        ? '<div class="compare-insight-list">' + insights.map(function (insight) {
            return '<div class="compare-insight-item"><strong>' + this._escapeHtml(String(insight && insight.label || "Insight")) + ':</strong> ' + this._escapeHtml(String(insight && insight.insight || "")) + '</div>';
          }.bind(this)).join("") + '</div>'
        : '<div class="section-copy">No clear setting correlation was found across the selected outcomes.</div>') +
    '</div>';
  }

  _renderCompareView() {
    var comparePayload = this._comparePayload;
    var differences = comparePayload && Array.isArray(comparePayload.differences) ? comparePayload.differences : [];
    var toolbarAction = this._compareBackMode === "related" ? "back-related" : "back-main";
    var toolbarLabel = this._compareBackMode === "related" ? "Back to Matches" : "Back to Actions";
    return '<div class="section-stack">' +
      this._renderActionSection(
        "Compare Archives",
        '<div class="actions-grid related-toolbar">' +
          this._renderActionButton(toolbarAction, toolbarLabel, "mdi:arrow-left", { disabled: this._busy }) +
          this._renderActionButton("open-compare", this._busy ? "Loading..." : "Change Selection", "mdi:swap-horizontal", { disabled: this._busy || this._compareBackMode === "bulk" }) +
        '</div>' +
        '<div class="section-copy">' + this._escapeHtml("Compare is rendered locally in Home Assistant from Bambuddy's structured compare API. This keeps the workflow stable without depending on an upstream compare deep link.") + '</div>'
      ) +
      this._renderActionSection(
        "Differences",
        this._compareError
          ? '<div class="section-copy">' + this._escapeHtml(this._compareError) + '</div>'
          : '<div class="compare-difference-summary">' +
              '<div class="compare-difference-count">' + this._escapeHtml(String(differences.length)) + ' differing field' + (differences.length === 1 ? '' : 's') + '</div>' +
              (differences.length
                ? '<div class="compare-difference-list">' + differences.slice(0, 6).map(function (difference) {
                    return '<div class="compare-difference-item">' + this._escapeHtml(String(difference && difference.label || difference && difference.field || "Difference")) + '</div>';
                  }.bind(this)).join("") + '</div>'
                : '<div class="section-copy">The selected archives match across Bambuddy\'s current compare field set.</div>') +
            '</div>'
      ) +
      this._renderActionSection("Comparison", this._compareError ? '<div class="section-copy">Fix the compare request or choose a different set of archives.</div>' : this._renderCompareTable(comparePayload)) +
      this._renderActionSection("Success Analysis", this._compareError ? '<div class="section-copy">Success analysis is unavailable because the comparison did not load.</div>' : this._renderCompareInsights(comparePayload)) +
    '</div>';
  }

  _renderMain(archive) {
    var hasGcodeFile = !!String((archive && archive.file_path) || "").trim();
    var hasSource = !!String((archive && archive.source_3mf_path) || "").trim();
    var hasTimelapse = !!this._timelapsePath(archive);
    var makerworldUrl = this._makerWorldUrl(archive);
    var makerworldLabel = "View on MakerWorld";
    var relationActions = this._renderActionSection(
      "Related & Compare",
      '<div class="actions-grid">' +
        this._renderActionButton("open-related", "Related Prints", "mdi:relation-many", { disabled: this._busy }) +
        this._renderActionButton("open-compare", "Compare with Another Print", "mdi:compare-horizontal", { disabled: this._busy }) +
      '</div>' +
      '<div class="section-copy">Use on-demand related candidates to inspect duplicate-family matches, open a related archive popup, or choose another archive to compare against this print without widening the browser payload.</div>'
    );
    var fileActions = '<div class="actions-grid">' +
      this._renderActionButton("download-model", "Download Gcode file", "mdi:download", { disabled: !hasGcodeFile || this._busy }) +
      (hasSource ? this._renderActionButton("download-source-3mf", "Download 3MF", "mdi:file-download-outline", { disabled: this._busy }) : "") +
      this._renderActionButton("upload-source-3mf", hasSource ? "Replace Source 3MF" : "Upload Source 3MF", "mdi:upload", { disabled: this._busy }) +
      '</div>';
    var linkActions = this._renderActionSection(
      "Links",
      '<div class="actions-grid">' +
        this._renderActionButton("open-makerworld", makerworldLabel, "mdi:earth", { disabled: !makerworldUrl || this._busy }) +
      '</div>'
    );
    var timelapseActions = this._renderActionSection(
      "Timelapse",
      '<div class="actions-grid">' +
        (hasTimelapse
          ? this._renderActionButton("view-timelapse", "View Timelapse", "mdi:movie-open-play-outline", { disabled: this._busy })
          : this._renderActionButton("scan-timelapse", "Scan Printer for Timelapse", "mdi:movie-search-outline", { disabled: this._busy })) +
        this._renderActionButton("upload-timelapse", hasTimelapse ? "Replace Timelapse" : "Upload Timelapse", "mdi:movie-open-plus-outline", { disabled: this._busy }) +
      '</div>' +
      '<div class="section-copy">' + this._escapeHtml(
        hasTimelapse
          ? "This archive already has an attached timelapse. You can view it or replace it with a new .mp4, .avi, or .mkv upload. Only one timelapse is tracked per archive."
          : "Ask Bambuddy to scan the printer for a matching timelapse, or upload one manually as .mp4, .avi, or .mkv. If the archive is missing a printer and Bambuddy only has one configured printer, the scan will assign it automatically first. Only one timelapse is tracked per archive."
      ) + '</div>'
    );
    var storageActions = this._renderStorageSection(archive);
    var maintenanceActions = this._renderActionSection(
      "Archive",
      '<div class="actions-grid">' +
        this._renderActionButton("repair-archive", "Repair Archive", "mdi:wrench-cog", { tone: "warning", disabled: this._busy }) +
        this._renderActionButton("open-correct-metadata", "Correct Metadata", "mdi:file-edit-outline", { tone: "warning", disabled: this._busy }) +
        this._renderActionButton("open-failure-analysis", "Open Failure Analysis", "mdi:chart-line", { disabled: this._busy }) +
        this._renderActionButton("view-metadata", "View Archive Metadata", "mdi:code-json", { disabled: this._busy }) +
      '</div>'
    );
    var dangerActions = this._renderActionSection(
      "Danger Zone",
      '<div class="actions-grid single-column">' +
        this._renderActionButton("delete-archive", "Delete Archive", "mdi:delete-outline", { tone: "danger", disabled: this._busy }) +
      '</div>',
      { tone: "danger" }
    );
    return '<div class="section-stack">' +
      relationActions +
      this._renderActionSection("Files", fileActions) +
      linkActions +
      timelapseActions +
      storageActions +
      maintenanceActions +
      dangerActions +
      '<input id="source-upload-input" class="hidden-file-input" type="file" accept=".3mf,application/vnd.ms-package.3dmanufacturing-3dmodel+xml">' +
        '<input id="timelapse-upload-input" class="hidden-file-input" type="file" accept=".mp4,.avi,.mkv,video/mp4,video/x-msvideo,video/x-matroska">' +
      '</div>';
  }

  _renderDeleteConfirm(archive, secondLevel) {
    var archiveName = archive && archive.print_name ? String(archive.print_name) : "this archive";
    var body = secondLevel
      ? 'Delete <strong>' + this._escapeHtml(archiveName) + '</strong> from Bambuddy?<br><br><strong>PERMANENTLY REMOVES</strong> the archive, photos, thumbnails, source media, timeline, and related local metadata.<br><br>This also immediately purges the mirrored Home Assistant cache rows for the archive, photos, timeline, review state, and related local metadata.'
      : 'Delete <strong>' + this._escapeHtml(archiveName) + '</strong> from Bambuddy?<br><br>This will remove the archive, photos, thumbnails, source media, timeline, and related metadata as part of the archive delete.';
    return '<div class="confirm-copy">' + body + '</div>' +
      '<div class="actions-grid confirm-grid">' +
      this._renderActionButton(secondLevel ? "delete-archive-final" : "continue-delete", secondLevel ? "Delete Archive Now" : "Yes, Continue to Delete", secondLevel ? "mdi:delete-forever-outline" : "mdi:alert-outline", { tone: secondLevel ? "danger" : "warning", wide: true, disabled: this._busy }) +
      this._renderActionButton("cancel", "Cancel", "mdi:close", { wide: true, disabled: this._busy }) +
      '</div>';
  }

  _render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }
    var archive = this._resolveArchive();
    var confirmDelete = this._mode === "confirm-delete-1" || this._mode === "confirm-delete-2";
    this._jsonClipboard = {};
    this.shadowRoot.innerHTML = '<style>' +
      ':host{display:block;color:var(--primary-text-color);}' +
      '.shell{display:flex;flex-direction:column;gap:12px;}' +
      '.summary-card{border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.03);border-radius:18px;padding:10px 12px;}' +
      '.summary-grid{display:grid;grid-template-columns:104px minmax(0,1fr);gap:12px;align-items:center;}' +
      '.summary-preview{width:104px;height:58px;border-radius:12px;overflow:hidden;background:rgba(15,23,42,0.32);display:flex;align-items:center;justify-content:center;}' +
      '.summary-preview img{display:block;width:100%;height:100%;object-fit:cover;}' +
      '.summary-preview.placeholder{background:rgba(15,23,42,0.20);color:var(--secondary-text-color);}' +
      '.summary-preview.placeholder ha-icon{--mdc-icon-size:20px;}' +
      '.summary-title{font-size:15px;font-weight:700;line-height:1.35;word-break:break-word;}' +
      '.summary-id{margin-top:4px;font-size:13px;line-height:1.45;color:var(--secondary-text-color);}' +
      '.summary-note{margin-top:6px;font-size:12px;line-height:1.4;color:var(--secondary-text-color);word-break:break-word;}' +
      '.status{border-radius:14px;padding:10px 12px;font-size:13px;line-height:1.4;}' +
      '.status.busy{display:flex;flex-direction:column;gap:6px;}' +
      '.status-main{display:flex;align-items:center;gap:8px;min-height:20px;}' +
      '.status.busy .status-main::before{content:"";width:14px;height:14px;border-radius:999px;border:2px solid rgba(255,255,255,0.18);border-top-color:currentColor;animation:phaSpin 0.8s linear infinite;flex:0 0 auto;}' +
      '.status-detail{font-size:12px;line-height:1.5;color:var(--secondary-text-color);}' +
      '.status.info{background:rgba(33,150,243,0.10);color:var(--primary-text-color);}' +
      '.status.success{background:rgba(46,125,50,0.14);color:var(--primary-text-color);}' +
      '.status.error{background:rgba(183,28,28,0.14);color:var(--primary-text-color);}' +
      '.hidden-file-input{display:none;}' +
      '.section-stack{display:flex;flex-direction:column;gap:12px;}' +
      '.action-section{border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.025);border-radius:18px;padding:12px;display:flex;flex-direction:column;gap:10px;}' +
      '.action-section.danger{border-color:rgba(239,68,68,0.18);background:rgba(183,28,28,0.05);}' +
      '.section-title{font-size:11px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:var(--secondary-text-color);padding:0 2px;}' +
      '.section-copy{padding:0 2px;font-size:12px;line-height:1.5;color:var(--secondary-text-color);}' +
      '.storage-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;}' +
      '.storage-metric{border-radius:14px;border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.03);padding:10px 12px;display:grid;gap:4px;}' +
      '.storage-metric.accent{border-color:rgba(56,189,248,0.32);background:rgba(56,189,248,0.08);}' +
      '.storage-metric-label{font-size:11px;font-weight:800;letter-spacing:0.05em;text-transform:uppercase;color:var(--secondary-text-color);}' +
      '.storage-metric-value{font-size:14px;font-weight:700;line-height:1.35;word-break:break-word;}' +
      '.storage-meta{padding:0 2px;font-size:12px;line-height:1.5;color:var(--secondary-text-color);}' +
      '.actions-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;}' +
      '.actions-grid.single-column{grid-template-columns:1fr;}' +
      '.action-button{appearance:none;-webkit-appearance:none;display:flex;align-items:center;justify-content:flex-start;gap:10px;width:100%;min-height:48px;padding:12px 14px;border-radius:16px;border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.04);box-shadow:none;color:var(--primary-text-color);font:inherit;font-size:14px;font-weight:700;text-align:left;cursor:pointer;touch-action:manipulation;transition:none;}' +
      '.action-button:hover:not(:disabled),.action-button:focus-visible:not(:disabled){background:rgba(255,255,255,0.08);border-color:rgba(255,255,255,0.18);outline:none;}' +
      '.action-button:active:not(:disabled){background:rgba(255,255,255,0.10);border-color:rgba(255,255,255,0.22);}' +
      '.action-button:disabled{opacity:0.45;cursor:default;box-shadow:none;}' +
      '.action-button ha-icon{--mdc-icon-size:20px;flex:0 0 auto;}' +
      '.action-button.warning{background:rgba(239,108,0,0.14);border-color:rgba(255,167,38,0.22);}' +
      '.action-button.danger{background:rgba(183,28,28,0.14);border-color:rgba(239,68,68,0.24);}' +
      '.related-list{display:flex;flex-direction:column;gap:10px;}' +
      '.related-groups{display:grid;gap:12px;}' +
      '.related-confidence-group{display:grid;gap:10px;border-radius:18px;border:1px solid rgba(255,255,255,0.08);padding:12px;background:rgba(255,255,255,0.02);}' +
      '.related-confidence-group.high{border-color:rgba(46,125,50,0.24);background:rgba(46,125,50,0.06);}' +
      '.related-confidence-group.medium{border-color:rgba(239,108,0,0.2);background:rgba(239,108,0,0.05);}' +
      '.related-confidence-group.low{border-color:rgba(84,110,122,0.18);background:rgba(84,110,122,0.05);}' +
      '.related-confidence-header{display:flex;align-items:center;justify-content:space-between;gap:10px;}' +
      '.related-confidence-title{font-size:13px;font-weight:800;line-height:1.3;letter-spacing:0.04em;text-transform:uppercase;}' +
      '.related-confidence-count{display:inline-flex;align-items:center;justify-content:center;min-width:28px;height:28px;border-radius:999px;padding:0 8px;background:rgba(255,255,255,0.08);font-size:12px;font-weight:800;line-height:1;}' +
      '.related-candidate{border-radius:16px;border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.03);padding:12px;display:grid;gap:10px;}' +
      '.related-candidate-header{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;}' +
      '.related-candidate-title-block{min-width:0;display:grid;gap:4px;}' +
      '.related-candidate-title{font-size:14px;font-weight:700;line-height:1.35;word-break:break-word;}' +
      '.related-candidate-meta{font-size:12px;line-height:1.4;color:var(--secondary-text-color);}' +
      '.related-candidate-badges{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px;}' +
      '.candidate-status,.candidate-score,.compare-archive-status{display:inline-flex;align-items:center;border-radius:999px;padding:4px 8px;font-size:11px;font-weight:700;line-height:1.2;}' +
      '.candidate-status.success,.compare-archive-status.success{background:rgba(46,125,50,0.18);color:#c8e6c9;}' +
      '.candidate-status.warning,.compare-archive-status.warning{background:rgba(239,108,0,0.16);color:#ffe0b2;}' +
      '.candidate-status.danger,.compare-archive-status.danger{background:rgba(183,28,28,0.14);color:#ffcdd2;}' +
      '.candidate-status.neutral,.compare-archive-status.neutral{background:rgba(84,110,122,0.18);color:#cfd8dc;}' +
      '.candidate-score{color:var(--primary-text-color);}' +
      '.related-candidate-copy{font-size:12px;line-height:1.5;color:var(--secondary-text-color);}' +
      '.related-actions{grid-template-columns:repeat(2,minmax(0,1fr));}' +
      '.related-toolbar{grid-template-columns:repeat(2,minmax(0,1fr));}' +
      '.compare-difference-summary{display:grid;gap:10px;}' +
      '.compare-difference-count{font-size:14px;font-weight:700;line-height:1.35;}' +
      '.compare-difference-list{display:flex;flex-wrap:wrap;gap:8px;}' +
      '.compare-difference-item{border-radius:999px;padding:6px 10px;background:rgba(239,108,0,0.14);font-size:12px;font-weight:700;line-height:1.3;}' +
      '.compare-table-wrap{overflow:auto;}' +
      '.compare-table{width:100%;min-width:520px;border-collapse:collapse;}' +
      '.compare-table th,.compare-table td{padding:10px 12px;border-bottom:1px solid rgba(255,255,255,0.08);text-align:left;vertical-align:top;}' +
      '.compare-table thead th{font-size:12px;font-weight:800;letter-spacing:0.05em;text-transform:uppercase;color:var(--secondary-text-color);background:rgba(255,255,255,0.02);}' +
      '.compare-table tbody tr.difference{background:rgba(239,108,0,0.06);}' +
      '.compare-field{font-weight:700;white-space:nowrap;}' +
      '.compare-archive-name{font-size:13px;font-weight:700;line-height:1.35;color:var(--primary-text-color);word-break:break-word;text-transform:none;letter-spacing:normal;}' +
      '.compare-unit{color:var(--secondary-text-color);}' +
      '.compare-insights{display:grid;gap:10px;}' +
      '.compare-insight-meta{font-size:12px;font-weight:700;line-height:1.4;color:var(--secondary-text-color);}' +
      '.compare-insight-list{display:grid;gap:8px;}' +
      '.compare-insight-item{border-radius:14px;border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.03);padding:10px 12px;font-size:12px;line-height:1.5;}' +
      '.confirm-copy{padding:4px 2px 2px;font-size:14px;line-height:1.55;color:var(--primary-text-color);}' +
      '.confirm-grid{grid-template-columns:1fr;}' +
      '.metadata-toolbar{grid-template-columns:repeat(2,minmax(0,1fr));}' +
      '.metadata-form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;}' +
      '.metadata-field{display:grid;gap:6px;}' +
      '.metadata-field-full{grid-column:1 / -1;}' +
      '.metadata-field-label{font-size:11px;font-weight:800;letter-spacing:0.05em;text-transform:uppercase;color:var(--secondary-text-color);}' +
      '.metadata-input,.metadata-textarea{width:100%;border-radius:14px;border:1px solid rgba(255,255,255,0.10);background:rgba(15,23,42,0.50);color:var(--primary-text-color);font:inherit;padding:10px 12px;box-sizing:border-box;}' +
      '.metadata-input:focus,.metadata-textarea:focus{outline:none;border-color:rgba(96,165,250,0.38);background:rgba(15,23,42,0.7);}' +
      '.metadata-textarea{resize:vertical;min-height:88px;}' +
      '.metadata-inline-error{border-radius:14px;padding:10px 12px;background:rgba(183,28,28,0.14);font-size:12px;line-height:1.5;color:var(--primary-text-color);}' +
      '.metadata-preview-summary{display:grid;gap:8px;font-size:12px;line-height:1.5;}' +
      '.metadata-preview-line{color:var(--primary-text-color);}' +
      '.metadata-warning-list,.metadata-impact-list{display:grid;gap:8px;margin-top:10px;}' +
      '.metadata-warning-item,.metadata-impact-item{border-radius:14px;border:1px solid rgba(255,255,255,0.08);background:rgba(239,108,0,0.10);padding:10px 12px;font-size:12px;line-height:1.5;}' +
      '.json-panel{border:1px solid rgba(255,255,255,0.08);background:rgba(9,14,23,0.78);border-radius:18px;overflow:hidden;}' +
      '.json-panel[open]{border-color:rgba(96,165,250,0.18);box-shadow:inset 0 1px 0 rgba(255,255,255,0.04);}' +
      '.json-panel-summary{list-style:none;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;background:rgba(255,255,255,0.03);cursor:pointer;}' +
      '.json-panel-summary::-webkit-details-marker{display:none;}' +
      '.json-panel-heading{display:flex;flex-direction:column;gap:4px;min-width:0;}' +
      '.json-panel-title{font-size:13px;font-weight:700;line-height:1.35;word-break:break-word;}' +
      '.json-panel-meta{font-size:11px;line-height:1.35;color:var(--secondary-text-color);}' +
      '.json-copy-button{appearance:none;-webkit-appearance:none;border:1px solid rgba(148,163,184,0.24);background:rgba(15,23,42,0.92);color:var(--primary-text-color);border-radius:999px;padding:8px 12px;font:inherit;font-size:12px;font-weight:700;cursor:pointer;flex:0 0 auto;}' +
      '.json-copy-button:hover,.json-copy-button:focus-visible{background:rgba(30,41,59,0.96);border-color:rgba(96,165,250,0.36);outline:none;}' +
      '.json-panel-copy{padding:0 14px 12px;font-size:12px;line-height:1.5;color:var(--secondary-text-color);}' +
      '.json-frame{border-top:1px solid rgba(255,255,255,0.06);background:linear-gradient(180deg,rgba(5,10,18,0.96),rgba(10,15,24,0.98));max-height:440px;overflow:auto;}' +
      '.json-code{font-family:Consolas,"SFMono-Regular",Menlo,monospace;font-size:12px;line-height:1.6;padding:10px 0;min-width:max-content;}' +
      '.json-line{display:grid;grid-template-columns:56px minmax(0,1fr);align-items:start;}' +
      '.json-line:hover{background:rgba(255,255,255,0.03);}' +
      '.json-gutter{padding:0 12px 0 0;text-align:right;color:rgba(148,163,184,0.72);user-select:none;border-right:1px solid rgba(255,255,255,0.06);}' +
      '.json-line-content{display:block;padding:0 14px;white-space:pre;color:#d4d4d4;}' +
      '.token.key{color:#9cdcfe;}' +
      '.token.string{color:#ce9178;}' +
      '.token.number{color:#b5cea8;}' +
      '.token.boolean{color:#569cd6;}' +
      '.token.null{color:#c586c0;}' +
      '.visually-hidden{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important;}' +
      '@keyframes phaSpin{0%{transform:rotate(0deg);}100%{transform:rotate(360deg);}}' +
      '@media (max-width: 520px){.summary-grid{grid-template-columns:1fr;}.summary-preview{width:100%;height:140px;}.actions-grid{grid-template-columns:1fr;}.storage-grid{grid-template-columns:1fr;}.metadata-form-grid{grid-template-columns:1fr;}.json-panel-summary{align-items:flex-start;flex-direction:column;}.json-copy-button{width:100%;}}' +
      '</style>' +
      '<div class="shell">' +
      this._renderSummary(archive) +
      this._renderStatus() +
      (confirmDelete
        ? this._renderDeleteConfirm(archive, this._mode === "confirm-delete-2")
        : this._mode === "metadata"
          ? this._renderMetadataView(archive)
          : this._mode === "correct-metadata"
            ? this._renderMetadataCorrectionView(archive)
          : this._mode === "related"
            ? this._renderRelatedView(archive)
            : this._mode === "compare"
              ? this._renderCompareView(archive)
          : this._renderMain(archive)) +
      '</div>';
  }
}

if (!customElements.get("print-history-archive-actions-card")) {
  customElements.define("print-history-archive-actions-card", PrintHistoryArchiveActionsCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some(function (card) { return card && card.type === "print-history-archive-actions-card"; })) {
  window.customCards.push({
    type: "print-history-archive-actions-card",
    name: "Print History Archive Actions Card",
    description: "Advanced print-history archive actions for downloads, metadata inspection, source upload, storage metrics, repair, and delete.",
  });
}