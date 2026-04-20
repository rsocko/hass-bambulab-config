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
    this._lastRenderSignature = "";
    this._boundClickHandler = this._handleClick.bind(this);
    this._boundSourceUploadChangeHandler = this._handleSourceUploadChange.bind(this);
  }

  setConfig(config) {
    this._config = {
      archive_json: config && config.archive_json ? config.archive_json : "{}",
      detail_entity: config && config.detail_entity ? config.detail_entity : "",
      api_base_entity: config && config.api_base_entity ? config.api_base_entity : "input_text.bambuddy_api_base_url",
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
  }

  connectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.addEventListener("click", this._boundClickHandler);
      this.shadowRoot.addEventListener("change", this._boundSourceUploadChangeHandler);
    }
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

    if (this._hass && this._config && this._config.detail_entity) {
      var detailState = this._hass.states && this._hass.states[this._config.detail_entity];
      if (detailState && detailState.attributes && detailState.attributes.archive && typeof detailState.attributes.archive === "object") {
        return detailState.attributes.archive;
      }
    }

    try {
      var parsed = JSON.parse(this._config && this._config.archive_json ? this._config.archive_json : "{}");
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (_error) {
      return {};
    }
  }

  _setArchive(archive) {
    this._archiveOverride = archive && typeof archive === "object" ? archive : null;
    this._lastRenderSignature = "";
    this._render();
    this._maybeLoadStorageMetrics();
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
    if (action === "refresh-metadata") {
      this._openMetadataViewer(true);
      return;
    }
    if (action === "back-main") {
      this._mode = "main";
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

    var baseEntityId = this._config.api_base_entity || "input_text.bambuddy_api_base_url";
    var baseState = hass.states[baseEntityId];
    parts.push(baseState ? String(baseState.state || "") : "");
    parts.push(baseState ? String(baseState.last_updated || baseState.last_changed || "") : "");

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
      this._setBusyState(true, String((archive && archive.timelapse_path) || "").trim() ? "Replacing timelapse..." : "Uploading timelapse...", "info", "upload-timelapse");
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
      detail_entity: this._config && this._config.detail_entity ? this._config.detail_entity : "",
      api_base_entity: this._config && this._config.api_base_entity ? this._config.api_base_entity : "input_text.bambuddy_api_base_url",
      title: "Timelapse",
    };
  }

  _buildArchiveTimelapsePopupContent(archive) {
    return {
      type: "vertical-stack",
      cards: [this._buildArchiveTimelapseCardConfig(archive)],
    };
  }

  _openTimelapsePopup() {
    var archive = this._resolveArchive();
    var timelapsePath = String(archive && archive.timelapse_path || "").trim();
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
    var timelapseName = String((archive && archive.timelapse_path) || "").trim();
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

  _renderMain(archive) {
    var hasGcodeFile = !!String((archive && archive.file_path) || "").trim();
    var hasSource = !!String((archive && archive.source_3mf_path) || "").trim();
    var hasTimelapse = !!String((archive && archive.timelapse_path) || "").trim();
    var makerworldUrl = this._makerWorldUrl(archive);
    var makerworldLabel = "View on MakerWorld";
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
      '.confirm-copy{padding:4px 2px 2px;font-size:14px;line-height:1.55;color:var(--primary-text-color);}' +
      '.confirm-grid{grid-template-columns:1fr;}' +
      '.metadata-toolbar{grid-template-columns:repeat(2,minmax(0,1fr));}' +
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
      '@media (max-width: 520px){.summary-grid{grid-template-columns:1fr;}.summary-preview{width:100%;height:140px;}.actions-grid{grid-template-columns:1fr;}.storage-grid{grid-template-columns:1fr;}.json-panel-summary{align-items:flex-start;flex-direction:column;}.json-copy-button{width:100%;}}' +
      '</style>' +
      '<div class="shell">' +
      this._renderSummary(archive) +
      this._renderStatus() +
      (confirmDelete
        ? this._renderDeleteConfirm(archive, this._mode === "confirm-delete-2")
        : this._mode === "metadata"
          ? this._renderMetadataView(archive)
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