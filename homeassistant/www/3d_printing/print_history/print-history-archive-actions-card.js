class PrintHistoryArchiveActionsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._archiveOverride = null;
    this._mode = "main";
    this._mainTab = "media";
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
    this._duplicateFamily = null;
    this._duplicateArchiveId = "";
    this._duplicateError = "";
    this._comparePayload = null;
    this._compareArchiveIds = [];
    this._compareError = "";
    this._compareBackMode = "main";
    this._initialCompareRequestKey = "";
    this._metadataCorrectionDraft = null;
    this._metadataCorrectionPreview = null;
    this._metadataCorrectionError = "";
    this._metadataCorrectionPreviewKey = "";
    this._timelapseScanResponse = null;
    this._lastRenderSignature = "";
    this._boundClickHandler = this._handleClick.bind(this);
    this._boundSourceUploadChangeHandler = this._handleSourceUploadChange.bind(this);
    this._boundArchiveUpdatedHandler = this._handleExternalArchiveUpdate.bind(this);
    // Model Catalog state
    this._modelLinks = [];
    this._modelLinksArchiveId = "";
    this._modelLinksBusy = false;
    this._modelLinksError = "";
    this._modelManualUrl = "";
    // Model Search Modal state
    this._modelSearchMode = false;
    this._modelSearchQuery = "";
    this._modelSearchCollection = "";
    this._modelSearchCreator = "";
    this._modelSearchTag = "";
    this._modelSearchPage = 1;
    this._modelSearchResults = [];
    this._modelSearchTotalPages = 0;
    this._modelSearchHasSearched = false;
    this._modelSearchBusy = false;
    this._modelSearchError = "";
    // 3MF Browser Upload Preview (Phase 1)
    this._sourceUploadPreview = null;           // Blob URL of extracted thumbnail
    this._sourceUploadPreviewFilename = "";    // Filename for display
    this._sourceUploadPreviewError = "";       // Error message if extraction fails
  }

  setConfig(config) {
    this._config = {
      archive_json: config && config.archive_json ? config.archive_json : "{}",
      detail_entity: config && config.detail_entity ? config.detail_entity : "",
      api_base_entity: config && config.api_base_entity ? config.api_base_entity : "input_text.bambuddy_api_base_url",
      model_catalog_sidecar_base_url_entity: config && config.model_catalog_sidecar_base_url_entity ? config.model_catalog_sidecar_base_url_entity : "input_text.model_catalog_sidecar_base_url",
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
    this._mainTab = "media";
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
    this._duplicateFamily = null;
    this._duplicateArchiveId = "";
    this._duplicateError = "";
    this._comparePayload = null;
    this._compareArchiveIds = [];
    this._compareError = "";
    this._compareBackMode = "main";
    this._initialCompareRequestKey = "";
    this._metadataCorrectionDraft = null;
    this._metadataCorrectionPreview = null;
    this._metadataCorrectionError = "";
    this._metadataCorrectionPreviewKey = "";
    this._metadataCorrectionBackMode = "main";
    this._timelapseScanResponse = null;
    this._lastRenderSignature = "";
    // Model Catalog state reset
    this._modelLinks = [];
    this._modelLinksArchiveId = "";
    this._modelLinksBusy = false;
    this._modelLinksError = "";
    this._modelManualUrl = "";
    // Model Search Modal state reset
    this._modelSearchMode = false;
    this._modelSearchQuery = "";
    this._modelSearchCollection = "";
    this._modelSearchCreator = "";
    this._modelSearchTag = "";
    this._modelSearchPage = 1;
    this._modelSearchResults = [];
    this._modelSearchTotalPages = 0;
    this._modelSearchHasSearched = false;
    this._modelSearchBusy = false;
    this._modelSearchError = "";
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
    window.addEventListener("bambuddy-print-history-archive-updated", this._boundArchiveUpdatedHandler);
    this._maybeLoadInitialCompare();
  }

  disconnectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.removeEventListener("click", this._boundClickHandler);
      this.shadowRoot.removeEventListener("change", this._boundSourceUploadChangeHandler);
    }
    window.removeEventListener("bambuddy-print-history-archive-updated", this._boundArchiveUpdatedHandler);
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
      if (detailState && detailState.attributes) {
        var detailArchiveRaw = detailState.attributes.archive_json;
        var detailStorageRaw = detailState.attributes.storage_metrics_json;
        var detailArchive = this._parseJson(detailArchiveRaw || "{}", {});
        var detailStorage = this._parseJson(detailStorageRaw || "{}", {});
        if (detailStorage && typeof detailStorage === "object" && Object.keys(detailStorage).length) {
          detailArchive = Object.assign({}, detailArchive, { storage_metrics: detailStorage });
        }
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

  _resolveCurrentArchiveId() {
    var archive = this._resolveArchive();
    return archive && archive.id != null ? String(archive.id) : "";
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

  _handleExternalArchiveUpdate(event) {
    var detail = event && event.detail && typeof event.detail === "object" ? event.detail : null;
    var updatedArchive = detail && detail.archive && typeof detail.archive === "object" ? detail.archive : null;
    var archiveId = updatedArchive && updatedArchive.id != null
      ? String(updatedArchive.id)
      : detail && detail.archive_id != null
        ? String(detail.archive_id)
        : "";
    var currentArchive = this._resolveArchive();
    var currentArchiveId = currentArchive && currentArchive.id != null ? String(currentArchive.id) : "";
    if (!archiveId || !updatedArchive || !currentArchiveId || archiveId !== currentArchiveId) {
      return;
    }

    this._setArchive(Object.assign({}, currentArchive, updatedArchive));
  }

  _normalizeMainTab(tabId) {
    var normalized = String(tabId || "").trim().toLowerCase();
    return normalized === "model" || normalized === "analytics" || normalized === "repair" || normalized === "danger"
      ? normalized
      : "media";
  }

  _setMainTab(tabId) {
    var nextTab = this._normalizeMainTab(tabId);
    if (this._mainTab === nextTab) {
      return;
    }
    this._mainTab = nextTab;
    this._render();
  }

  _mainTabConfig() {
    return [
      { id: "media", label: "Files & Media", icon: "mdi:folder-play-outline" },
      { id: "model", label: "Model", icon: "mdi:cube-outline" },
      { id: "analytics", label: "Analytics", icon: "mdi:chart-box-outline" },
      { id: "repair", label: "Repair & Metadata", icon: "mdi:wrench-cog-outline" },
      { id: "danger", label: "Danger", icon: "mdi:alert-octagon-outline" },
    ];
  }

  _renderMainTabs() {
    return '<div class="main-tablist" role="tablist" aria-label="Advanced action groups">'
      + this._mainTabConfig().map(function (tab) {
          var isActive = tab.id === this._mainTab;
          return '<button class="main-tab-button' + (isActive ? ' active' : '') + '" type="button" role="tab" aria-selected="' + (isActive ? 'true' : 'false') + '" data-action="switch-main-tab" data-tab-id="' + this._escapeHtml(tab.id) + '">'
            + '<ha-icon icon="' + this._escapeHtml(tab.icon) + '"></ha-icon>'
            + '<span>' + this._escapeHtml(tab.label) + '</span>'
            + '</button>';
        }.bind(this)).join("")
      + '</div>';
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
    if (action === "repair-choose-metadata") {
      this._mainTab = "repair";
      this._openMetadataCorrection("repair-chooser");
      return;
    }
    if (action === "repair-choose-replacement") {
      this._launchReplacementRepair();
      return;
    }
    if (action === "refresh-storage-metrics") {
      this._mainTab = "analytics";
      this._handleRefreshStorageMetrics();
      return;
    }
    if (action === "view-metadata") {
      this._mainTab = "repair";
      this._openMetadataViewer(false);
      return;
    }
    if (action === "open-correct-metadata") {
      this._mainTab = "repair";
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
      this._mainTab = "analytics";
      this._openFailureAnalysis();
      return;
    }
    if (action === "open-related") {
      this._mainTab = "analytics";
      this._loadRelatedCandidates({ compareIntent: false });
      return;
    }
    if (action === "open-duplicates") {
      this._mainTab = "analytics";
      this._loadDuplicateFamily();
      return;
    }
    if (action === "open-compare") {
      this._mainTab = "analytics";
      this._loadRelatedCandidates({ compareIntent: true });
      return;
    }
    if (action === "switch-main-tab") {
      this._setMainTab(button.getAttribute("data-tab-id") || "media");
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
    if (action === "duplicate-open") {
      this._handleOpenRelatedArchive(button.getAttribute("data-archive-id") || "");
      return;
    }
    if (action === "duplicate-compare") {
      this._handleCompareAgainstArchive(button.getAttribute("data-archive-id") || "", "duplicates");
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
    if (action === "back-repair-chooser") {
      this._mode = "repair-chooser";
      this._render();
      return;
    }
    if (action === "back-duplicates") {
      this._mode = "duplicates";
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
    // ─── Model Catalog actions ──────────────────────────────────────────────
    if (action === "model-reload-links") {
      this._modelLinksArchiveId = "";
      this._loadModelLinks(this._resolveCurrentArchiveId());
      return;
    }
    if (action === "model-refresh-candidates") {
      var currentArchive = this._resolveArchive();
      this._modelCatalogAction("refresh-candidates", this._resolveCurrentArchiveId(), null, {
        archive_name: currentArchive && currentArchive.print_name ? String(currentArchive.print_name) : "",
        source_file_name: currentArchive && currentArchive.filename ? String(currentArchive.filename) : "",
        source_hash: currentArchive && currentArchive.content_hash ? String(currentArchive.content_hash) : "",
        archive_completed_at: currentArchive && currentArchive.completed_at ? String(currentArchive.completed_at) : "",
      });
      return;
    }
    if (action === "model-accept-link") {
      this._modelCatalogAction("accept-link", this._resolveCurrentArchiveId(),
        button.getAttribute("data-link-id"),
        { model_url: button.getAttribute("data-model-url") || "" });
      return;
    }
    if (action === "model-reject-link") {
      this._modelCatalogAction("reject-link", this._resolveCurrentArchiveId(),
        button.getAttribute("data-link-id"), null);
      return;
    }
    if (action === "model-deactivate-link") {
      this._modelCatalogAction("deactivate-link", this._resolveCurrentArchiveId(),
        button.getAttribute("data-link-id"), null);
      return;
    }
    if (action === "model-create-link") {
      var manualInput = this.shadowRoot ? this.shadowRoot.querySelector("#model-manual-url-input") : null;
      var manualUrl = manualInput ? String(manualInput.value || "").trim() : "";
      this._modelManualUrl = manualUrl;
      this._modelCatalogAction("create-manual-link", this._resolveCurrentArchiveId(), null,
        { model_url: manualUrl });
      return;
    }
    if (action === "model-search-library") {
      this._modelSearchMode = true;
      this._modelSearchQuery = "";
      this._modelSearchCollection = "";
      this._modelSearchCreator = "";
      this._modelSearchTag = "";
      this._modelSearchPage = 1;
      this._modelSearchResults = [];
      this._modelSearchTotalPages = 0;
      this._modelSearchHasSearched = false;
      this._modelSearchBusy = false;
      this._modelSearchError = "";
      this._render();
      return;
    }
    if (action === "model-search-close") {
      this._modelSearchMode = false;
      this._modelSearchHasSearched = false;
      this._render();
      return;
    }
    if (action === "model-search-execute") {
      this._executeModelSearch(1);
      return;
    }
    if (action === "model-search-next-page") {
      this._executeModelSearch(this._modelSearchPage + 1);
      return;
    }
    if (action === "model-search-prev-page") {
      this._executeModelSearch(Math.max(1, this._modelSearchPage - 1));
      return;
    }
    if (action === "model-search-link-result") {
      var resultUrl = button.getAttribute("data-result-url") || "";
      this._modelCatalogAction("create-manual-link", this._resolveCurrentArchiveId(), null,
        { model_url: resultUrl });
      return;
    }
    // Phase 3.3 Model Catalog Navigation Actions
    if (action === "view-source-model") {
      this._handleViewSourceModel();
      return;
    }
    if (action === "edit-model-metadata") {
      this._handleEditModelMetadata();
      return;
    }
    if (action === "view-similar-models") {
      this._handleViewSimilarModels();
      return;
    }
  }

  async _handleSourceUploadChange(event) {
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
        // Phase 1: Extract 3MF thumbnail for preview (async, no blocking)
        this._extract3MFThumbnailPreview(file);
        this._uploadSource3mf(file);
      }
    }
    input.value = "";
  }

  // ─── Phase 1: 3MF Browser Preview Extraction ──────────────────────────────

  /**
   * Extract thumbnail for preview from 3MF or image file.
   * Supports both: 3MF embedded thumbnails and direct image file previews.
   * Runs async without blocking UI. Gracefully fails if extraction not possible.
   * @param {File} file - The 3MF or image file from file input
   */
  async _extract3MFThumbnailPreview(file) {
    if (!file || !file.name) {
      return;
    }

    try {
      // Direct image file preview (PNG, JPEG, GIF, WebP, etc.)
      if (file.type.startsWith("image/")) {
        const validImageTypes = ["image/png", "image/jpeg", "image/gif", "image/webp"];
        if (validImageTypes.includes(file.type)) {
          // Validate image file size
          const MAX_IMAGE_SIZE = 10 * 1024 * 1024; // 10 MB for direct images
          if (file.size <= MAX_IMAGE_SIZE) {
            if (this._sourceUploadPreview) {
              URL.revokeObjectURL(this._sourceUploadPreview);
            }
            this._sourceUploadPreview = URL.createObjectURL(file);
            this._sourceUploadPreviewFilename = file.name;
            this._sourceUploadPreviewError = "";
            this._render();
            return;
          }
        }
        return;
      }

      // 3MF ZIP extraction for embedded thumbnail
      if (!file.name.toLowerCase().endsWith(".3mf")) {
        return;
      }

      // Load JSZip if not already available.
      const jsZipReady = await this._ensureJsZipLoaded();
      if (!jsZipReady || typeof JSZip === "undefined") {
        console.warn("JSZip library not loaded, skipping 3MF preview extraction");
        return;
      }

      // Read file as ArrayBuffer
      const arrayBuffer = await file.arrayBuffer();
      if (!arrayBuffer || arrayBuffer.byteLength === 0) {
        return;
      }

      // Load ZIP
      const zip = new JSZip();
      await zip.loadAsync(arrayBuffer);

      // Build case-insensitive lookup to handle exporters that vary path casing.
      const zipEntries = Object.keys(zip.files || {});
      const entryLookup = {};
      for (const entryName of zipEntries) {
        entryLookup[String(entryName).toLowerCase()] = entryName;
      }

      // Try known thumbnail paths in priority order.
      const thumbnailPaths = [
        "metadata/thumbnail.png",
        "metadata/thumbnail.jpg",
        "metadata/thumbnail.jpeg",
        "thumbnails/thumbnail.png",
        "thumbnails/thumbnail.jpg",
        "thumbnails/thumbnail.jpeg",
        "3d/thumbnail.png",
        "3d/thumbnail.jpg",
        "3d/thumbnail.jpeg",
        "metadata/plate_1.png",
        "metadata/plate_1.jpg",
        "auxiliaries/model pictures/thumbnail.png",
        "auxiliaries/model pictures/thumbnail.jpg",
      ];

      for (const path of thumbnailPaths) {
        const matchedEntryName = entryLookup[path];
        const member = matchedEntryName ? zip.file(matchedEntryName) : null;
        if (!member) {
          continue;
        }
        try {
          const blob = await member.async("blob");

          if (!this._isSafe3MFThumbnail(blob, matchedEntryName)) {
            continue;
          }

          const inferredType = this._inferImageMimeTypeFromPath(matchedEntryName);
          const previewBlob = inferredType && blob.type !== inferredType
            ? new Blob([blob], { type: inferredType })
            : blob;

          if (this._sourceUploadPreview) {
            URL.revokeObjectURL(this._sourceUploadPreview);
          }
          this._sourceUploadPreview = URL.createObjectURL(previewBlob);
          this._sourceUploadPreviewFilename = file.name;
          this._sourceUploadPreviewError = "";
          this._render();
          return;
        } catch (_error) {
          // Continue to next path candidate.
        }
      }

      // Prefix fallback: find any image under common thumbnail folders.
      const fallbackPrefixes = [
        "metadata/",
        "thumbnails/",
        "3d/",
        "auxiliaries/model pictures/",
      ];
      const fallbackEntries = zipEntries
        .filter((name) => {
          const lower = String(name || "").toLowerCase();
          const imageExt = lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg");
          if (!imageExt) {
            return false;
          }
          return fallbackPrefixes.some((prefix) => lower.startsWith(prefix));
        })
        .sort();

      for (const matchedEntryName of fallbackEntries) {
        const member = zip.file(matchedEntryName);
        if (!member) {
          continue;
        }
        try {
          const blob = await member.async("blob");
          if (!this._isSafe3MFThumbnail(blob, matchedEntryName)) {
            continue;
          }

          const inferredType = this._inferImageMimeTypeFromPath(matchedEntryName);
          const previewBlob = inferredType && blob.type !== inferredType
            ? new Blob([blob], { type: inferredType })
            : blob;

          if (this._sourceUploadPreview) {
            URL.revokeObjectURL(this._sourceUploadPreview);
          }
          this._sourceUploadPreview = URL.createObjectURL(previewBlob);
          this._sourceUploadPreviewFilename = file.name;
          this._sourceUploadPreviewError = "";
          this._render();
          return;
        } catch (_error) {
          // Continue scanning candidates.
        }
      }
    } catch (error) {
      // Silently fail - allow upload to proceed without preview
      console.debug("3MF preview extraction failed (proceeding without preview):", error);
    }
  }

  /**
   * Validate 3MF thumbnail for safety (ZIP bomb detection, file size, MIME type)
   * @param {Blob} blob - The extracted image blob
   * @param {string} path - The path in the ZIP
   * @returns {boolean} - True if safe to use
   */
  _isSafe3MFThumbnail(blob, path) {
    const THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024; // 2 MB
    const ALLOWED_TYPES = ["image/png", "image/jpeg"];

    // Check file size
    if (blob.size > THUMBNAIL_MAX_BYTES) {
      return false;
    }

    // Check file extension
    const ext = String(path || "").toLowerCase();
    if (!ext.endsWith(".png") && !ext.endsWith(".jpg") && !ext.endsWith(".jpeg")) {
      return false;
    }

    // ZIP-extracted blobs often have an empty MIME type; infer by extension when absent.
    if (blob.type && !ALLOWED_TYPES.includes(blob.type)) {
      return false;
    }

    return true;
  }

  _inferImageMimeTypeFromPath(path) {
    var normalized = String(path || "").toLowerCase();
    if (normalized.endsWith(".png")) {
      return "image/png";
    }
    if (normalized.endsWith(".jpg") || normalized.endsWith(".jpeg")) {
      return "image/jpeg";
    }
    return "";
  }

  async _ensureJsZipLoaded() {
    if (typeof JSZip !== "undefined") {
      return true;
    }

    const existing = document.querySelector('script[data-print-history-jszip="1"]');
    if (existing) {
      if (existing.dataset.loaded === "1") {
        return typeof JSZip !== "undefined";
      }
      await new Promise((resolve) => {
        existing.addEventListener("load", resolve, { once: true });
        existing.addEventListener("error", resolve, { once: true });
      });
      return typeof JSZip !== "undefined";
    }

    await new Promise((resolve) => {
      const script = document.createElement("script");
      script.src = "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js";
      script.async = true;
      script.dataset.printHistoryJszip = "1";
      script.addEventListener("load", () => {
        script.dataset.loaded = "1";
        resolve();
      }, { once: true });
      script.addEventListener("error", resolve, { once: true });
      document.head.appendChild(script);
    });

    return typeof JSZip !== "undefined";
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

  _parseJson(value, fallbackValue) {
    try {
      var parsed = typeof value === "string" ? JSON.parse(value || "null") : value;
      return parsed == null ? fallbackValue : parsed;
    } catch (_error) {
      return fallbackValue;
    }
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
      this._mainTab,
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
    parts.push(String(this._duplicateArchiveId || ""));
    parts.push(String(this._duplicateError || ""));
    parts.push(JSON.stringify(this._duplicateFamily || {}));
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
      filament_used_grams: archive && archive.filament_used_grams != null ? String(archive.filament_used_grams) : "",
      cost: archive && archive.cost != null ? String(archive.cost) : "",
      quantity: archive && archive.quantity != null ? String(archive.quantity) : "",
      external_url: archive && archive.external_url ? String(archive.external_url) : "",
      reason: "",
    };
  }

  _openMetadataCorrection(backMode) {
    var archive = this._resolveArchive();
    this._metadataCorrectionDraft = this._buildMetadataCorrectionDraft(archive);
    this._metadataCorrectionPreview = null;
    this._metadataCorrectionError = "";
    this._metadataCorrectionPreviewKey = "";
    this._metadataCorrectionBackMode = backMode === "repair-chooser" ? "repair-chooser" : "main";
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
      filament_used_grams: this._metadataCorrectionFieldValue("filament_used_grams"),
      cost: this._metadataCorrectionFieldValue("cost"),
      quantity: this._metadataCorrectionFieldValue("quantity"),
      external_url: this._metadataCorrectionFieldValue("external_url"),
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
    ["filament_used_grams", "cost", "quantity"].forEach(function (fieldName) {
      var rawValue = String(draft[fieldName] || "").trim();
      var currentValue = archive && archive[fieldName] != null ? String(archive[fieldName]) : "";
      if (rawValue && rawValue !== currentValue) {
        payload[fieldName] = rawValue;
      }
    });
    var currentExternalUrl = archive && archive.external_url != null ? String(archive.external_url) : "";
    if (draft.external_url !== currentExternalUrl) {
      payload.external_url = draft.external_url;
    }
    if (!payload.reason) {
      throw new Error("Reason is required before previewing metadata changes.");
    }
    if (!("started_at" in payload) && !("completed_at" in payload) && !("created_at" in payload) && !("status" in payload) && !("failure_reason" in payload) && !("filament_used_grams" in payload) && !("cost" in payload) && !("quantity" in payload) && !("external_url" in payload)) {
      throw new Error("Change at least one metadata field before previewing.");
    }
    return payload;
  }

  async _runMetadataCorrection(dryRun) {
    this._metadataCorrectionError = "";
    try {
      var payload = this._collectMetadataCorrectionPayload();
      payload.dry_run = !!dryRun;
      var payloadKey = JSON.stringify(payload);
      this._setBusyState(true, dryRun ? "Previewing metadata correction..." : "Applying metadata correction...", "info", dryRun ? "metadata-correction-preview" : "metadata-correction-apply");
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
    if (Object.prototype.hasOwnProperty.call(impacts, "filament_used_grams_changed")) {
      rows.push("Filament weight: " + String(impacts.filament_used_grams_before != null ? impacts.filament_used_grams_before : "unknown") + "g -> " + String(impacts.filament_used_grams_after != null ? impacts.filament_used_grams_after : "unknown") + "g");
    }
    if (Object.prototype.hasOwnProperty.call(impacts, "cost_changed")) {
      rows.push("Cost: " + String(impacts.cost_before != null ? impacts.cost_before : "unknown") + " -> " + String(impacts.cost_after != null ? impacts.cost_after : "unknown"));
    }
    if (Object.prototype.hasOwnProperty.call(impacts, "quantity_changed")) {
      rows.push("Quantity: " + String(impacts.quantity_before != null ? impacts.quantity_before : "unknown") + " -> " + String(impacts.quantity_after != null ? impacts.quantity_after : "unknown"));
    }
    if (Object.prototype.hasOwnProperty.call(impacts, "external_url_changed")) {
      rows.push("External URL changed: " + (impacts.external_url_changed ? "yes" : "no"));
    }
    return '<div class="metadata-impact-list">' + rows.map(function (row) {
      return '<div class="metadata-impact-item">' + this._escapeHtml(row) + '</div>';
    }.bind(this)).join("") + '</div>';
  }

  _renderMetadataCorrectionView(archive) {
    var draft = this._metadataCorrectionDraft || this._buildMetadataCorrectionDraft(archive);
    var preview = this._metadataCorrectionPreview;
    var warnings = preview && Array.isArray(preview.warnings) ? preview.warnings : [];
    var updatedFields = preview && Array.isArray(preview.updated_fields) ? preview.updated_fields : [];
    var launchedFromRepairChooser = this._metadataCorrectionBackMode === "repair-chooser";
    return '<div class="section-stack metadata-correction-view">' +
      this._renderActionSection(
        launchedFromRepairChooser ? "Repair Archive · Correct Metadata" : "Correct Metadata",
        '<div class="actions-grid metadata-toolbar">' +
          this._renderActionButton(launchedFromRepairChooser ? "back-repair-chooser" : "back-main", launchedFromRepairChooser ? "Back to Repair Choices" : "Back to Actions", "mdi:arrow-left", { disabled: this._busy }) +
          this._renderActionButton("view-metadata", "View Archive Metadata", "mdi:code-json", { disabled: this._busy }) +
        '</div>' +
        '<div class="section-copy">Advanced correction writes directly to archived runtime and selected advanced metadata. Preview first, confirm the derived impact summary, then apply. A local audit record is written to the Variant 3 store when this runs.</div>'
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
          '<label class="metadata-field"><span class="metadata-field-label">Filament Weight (g)</span><input id="metadata-correction-filament_used_grams" class="metadata-input" type="number" min="0" step="0.01" value="' + this._escapeHtml(draft.filament_used_grams || "") + '" placeholder="58.98"></label>' +
          '<label class="metadata-field"><span class="metadata-field-label">Cost</span><input id="metadata-correction-cost" class="metadata-input" type="number" min="0" step="0.01" value="' + this._escapeHtml(draft.cost || "") + '" placeholder="1.47"></label>' +
          '<label class="metadata-field"><span class="metadata-field-label">Quantity</span><input id="metadata-correction-quantity" class="metadata-input" type="number" min="0" step="1" value="' + this._escapeHtml(draft.quantity || "") + '" placeholder="1"></label>' +
          '<label class="metadata-field"><span class="metadata-field-label">External URL</span><input id="metadata-correction-external_url" class="metadata-input" type="text" value="' + this._escapeHtml(draft.external_url || "") + '" placeholder="https://printables.com/model/12345"></label>' +
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

  _renderRepairChooserView(archive) {
    var archiveName = archive && archive.print_name ? String(archive.print_name) : "this archive";
    return '<div class="section-stack repair-chooser-view">' +
      this._renderActionSection(
        "Repair Archive",
        '<div class="actions-grid metadata-toolbar">' +
          this._renderActionButton("back-main", "Back to Actions", "mdi:arrow-left", { disabled: this._busy }) +
          this._renderActionButton("view-metadata", "View Archive Metadata", "mdi:code-json", { disabled: this._busy }) +
        '</div>' +
        '<div class="section-copy">Choose the repair path that matches the problem for <strong>' + this._escapeHtml(archiveName) + '</strong>. Metadata correction keeps the existing archive row and repairs canonical timing or status fields. Replacement repair launches the existing restore workflow when the archived file-backed record itself is wrong or incomplete.</div>'
      ) +
      this._renderActionSection(
        "Repair Paths",
        '<div class="actions-grid">' +
          this._renderActionButton("repair-choose-metadata", "Correct Metadata", "mdi:file-edit-outline", { tone: "warning", disabled: this._busy }) +
          this._renderActionButton("repair-choose-replacement", "Repair From Replacement 3MF", "mdi:file-replace-outline", { tone: "warning", disabled: this._busy }) +
        '</div>' +
        '<div class="section-copy">Use Correct Metadata when the archive row is correct but historical timing or outcome data needs repair. Use Repair From Replacement 3MF when the archived source file or parser-derived metadata needs to be replaced or merged.</div>'
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
    var archive = this._resolveArchive();
    if (this._timelapsePath(archive)) {
      this._setStatus("This archive already has a timelapse. Delete it first before uploading a different file.", "error");
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
    if (Array.isArray(payload) && payload.length) {
      var firstItem = payload[0];
      if (firstItem && typeof firstItem === "object") {
        return this._normalizeServiceResponse(firstItem);
      }
    }
    if (payload && typeof payload === "object") {
      if (payload.service_response && typeof payload.service_response === "object") {
        return this._normalizeServiceResponse(payload.service_response);
      }
      if (payload.response && typeof payload.response === "object") {
        return this._normalizeServiceResponse(payload.response);
      }
      if (
        payload.content
        && typeof payload.content === "object"
        && (Object.prototype.hasOwnProperty.call(payload, "status")
          || Object.prototype.hasOwnProperty.call(payload, "headers"))
      ) {
        return Object.assign({}, payload.content, {
          content: payload.content,
          status: payload.status,
          headers: payload.headers,
        });
      }
    }
    return payload && typeof payload === "object" ? payload : {};
  }

  _serviceResponseErrorMessage(payload, fallbackMessage) {
    var normalized = payload && typeof payload === "object" ? payload : {};
    var content = normalized.content && typeof normalized.content === "object" ? normalized.content : {};
    if (content.message && String(content.message).trim()) {
      return String(content.message).trim();
    }
    if (content.error && String(content.error).trim()) {
      return String(content.error).trim();
    }
    if (Array.isArray(content.detail) && content.detail.length) {
      return content.detail.map(function (item) {
        if (item && typeof item === "object" && item.msg) {
          return String(item.msg);
        }
        return String(item || "");
      }).filter(Boolean).join("; ") || fallbackMessage;
    }
    return fallbackMessage;
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

    var normalized = this._normalizeServiceResponse(payload);
    if (normalized && typeof normalized === "object" && Number(normalized.status || 0) >= 400) {
      throw {
        message: this._serviceResponseErrorMessage(
          normalized,
          "Service call failed (embedded HTTP " + String(normalized.status) + ")"
        ),
        body: normalized,
        status: Number(normalized.status || 0),
      };
    }

    return normalized;
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
    if (this._timelapsePath(archive)) {
      this._setStatus("This archive already has a timelapse. Delete it first before uploading a different file.", "error");
      return;
    }
    if (!/\.(mp4|avi|mkv)$/i.test(String(file.name || ""))) {
      this._setStatus("Timelapse upload only accepts .mp4, .avi, or .mkv files.", "error");
      return;
    }

    try {
      this._setBusyState(true, "Uploading timelapse...", "info", "upload-timelapse");
      var response = await this._postTimelapseUpload(file, archiveId);
      var payload = response && typeof response === "object" ? response : {};
      var nextArchive = payload && payload.archive && typeof payload.archive === "object"
        ? payload.archive
        : payload;
      this._busy = false;
      this._busyContext = "";
      this._setArchive(nextArchive);
      this._setStatus("Timelapse uploaded.", "success");
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
    if (archive && typeof archive === "object" && Object.prototype.hasOwnProperty.call(archive, "timelapse_path")) {
      return String(archive.timelapse_path || "").trim();
    }
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

  _storageMetricsNeedForceRefresh(archive) {
    if (!archive || typeof archive !== "object") {
      return false;
    }
    var storageMetrics = archive.storage_metrics;
    if (!storageMetrics || typeof storageMetrics !== "object") {
      return false;
    }
    var directTimelapsePath = archive && typeof archive === "object" && Object.prototype.hasOwnProperty.call(archive, "timelapse_path")
      ? String(archive.timelapse_path || "").trim()
      : String(archive && archive.timelapse_path || "").trim();
    var timelapseBytes = storageMetrics.metrics ? Number(storageMetrics.metrics.timelapse_bytes || 0) : 0;
    var artifactPath = storageMetrics.artifacts
      && storageMetrics.artifacts.timelapse_path
      && storageMetrics.artifacts.timelapse_path.relative_path
      ? String(storageMetrics.artifacts.timelapse_path.relative_path || "").trim()
      : "";
    if (directTimelapsePath) {
      return timelapseBytes <= 0 || !artifactPath;
    }
    return timelapseBytes > 0 || !!artifactPath;
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

  _timelapseScanDiagnosticsMarkup() {
    var response = this._timelapseScanResponse;
    if (!response || typeof response !== "object") {
      return "";
    }

    var scanResult = response.scan_result && typeof response.scan_result === "object" ? response.scan_result : {};
    var rows = [];
    var status = String(response.status || scanResult.status || "").trim();
    var attachedName = String(scanResult.filename || response.filename || "").trim();
    var autoAssignedPrinterId = Number(scanResult.auto_assigned_printer_id || response.auto_assigned_printer_id || 0);
    var matchStrategy = String(scanResult.match_strategy || scanResult.strategy || "").trim();
    var availableFiles = Array.isArray(scanResult.available_files) ? scanResult.available_files : [];
    var candidateNames = availableFiles.slice(0, 3).map(function (item) {
      return String(item && item.name || "").trim();
    }).filter(Boolean);

    if (status) {
      rows.push("<strong>Last scan status:</strong> " + this._escapeHtml(status));
    }
    if (attachedName) {
      rows.push("<strong>Attached file:</strong> " + this._escapeHtml(attachedName));
    }
    if (matchStrategy) {
      rows.push("<strong>Match strategy:</strong> " + this._escapeHtml(matchStrategy));
    }
    if (autoAssignedPrinterId > 0) {
      rows.push("<strong>Auto-assigned printer:</strong> " + this._escapeHtml(String(autoAssignedPrinterId)));
    }
    if (availableFiles.length) {
      rows.push("<strong>Candidate files:</strong> " + this._escapeHtml(String(availableFiles.length)) + (candidateNames.length ? " (" + this._escapeHtml(candidateNames.join(", ")) + (availableFiles.length > candidateNames.length ? ", ..." : "") + ")" : ""));
    }

    return rows.length
      ? '<div class="section-copy"><strong>Last scan details.</strong><br>' + rows.join("<br>") + '</div>'
      : "";
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
    var forceRefresh = this._storageMetricsNeedForceRefresh(archive);
    var requestKey = String(archiveId) + ":" + (forceRefresh ? "force" : "cache");
    if (!archiveId || this._busy) {
      return;
    }
    if (archive && archive.storage_metrics && typeof archive.storage_metrics === "object" && !forceRefresh) {
      this._storageMetricsLoadedKey = requestKey;
      return;
    }
    if (this._storageMetricsLoadedKey === requestKey || this._storageMetricsRequestKey === requestKey) {
      return;
    }
    this._storageMetricsRequestKey = requestKey;
    this._fetchArchiveStorageMetrics(forceRefresh).catch(function () {
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
      this._timelapseScanResponse = response && typeof response === "object" ? response : null;
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
      this._timelapseScanResponse = null;
      this._setStatus(this._describeError(error, "Timelapse scan failed"), "error");
    }
  }

  async _handleRepair() {
    this._mode = "repair-chooser";
    this._render();
  }

  _launchReplacementRepair() {
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
      this._busy = false;
      this._busyContext = "";
      await this._hass.callService("browser_mod", "close_popup", {});
    } catch (error) {
      this._busy = false;
      this._busyContext = "";
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

  _analyticsOverviewItems(archive) {
    var storage = this._storageMetricsData(archive);
    var metrics = storage && storage.metrics && typeof storage.metrics === "object" ? storage.metrics : {};
    var duplicateCount = Math.max(0, Number(archive && archive.duplicate_count || 0));
    var duplicateSequence = Math.max(0, Number(archive && archive.duplicate_sequence || 0));
    var originalArchiveId = Math.max(0, Number(archive && archive.original_archive_id || 0));
    var lineageValue = duplicateCount > 0
      ? String(duplicateCount + 1) + " in family"
      : originalArchiveId > 0
        ? "Copy of #" + String(originalArchiveId)
        : duplicateSequence > 0
          ? "Copy #" + String(duplicateSequence)
          : "Standalone";
    var lineageMeta = duplicateCount > 0
      ? "Includes this archive plus explicit Bambuddy duplicates."
      : originalArchiveId > 0
        ? "This archive is marked as a duplicate copy."
        : "No explicit duplicate lineage is attached.";
    return [
      {
        label: "Outcome",
        value: this._statusLabel(archive && archive.status),
        meta: "Current archive status.",
        accent: this._statusBadgeClass(archive && archive.status) === "success",
      },
      {
        label: "Archive Date",
        value: this._formatArchiveDate(archive && (archive.completed_at || archive.created_at || archive.started_at)),
        meta: "Primary timeline anchor for analytics and browsing.",
      },
      {
        label: "Tracked Storage",
        value: this._formatBytes(metrics.total_bytes || 0),
        meta: storage
          ? (storage.scan_status === "complete"
              ? "Filesystem scan is current."
              : storage.scan_status === "partial"
                ? "Filesystem scan is partial."
                : storage.scan_status === "missing"
                  ? "No tracked files were found."
                  : "Storage scan can be refreshed.")
          : "Load or refresh storage metrics.",
        accent: Number(metrics.total_bytes || 0) > 0,
      },
      {
        label: "Duplicate Lineage",
        value: lineageValue,
        meta: lineageMeta,
      },
    ];
  }

  _renderAnalyticsOverview(archive) {
    return '<section class="analytics-overview">'
      + this._analyticsOverviewItems(archive).map(function (item) {
          return '<div class="analytics-kpi' + (item.accent ? ' accent' : '') + '">'
            + '<div class="analytics-kpi-label">' + this._escapeHtml(item.label) + '</div>'
            + '<div class="analytics-kpi-value">' + this._escapeHtml(item.value) + '</div>'
            + '<div class="analytics-kpi-meta">' + this._escapeHtml(item.meta) + '</div>'
            + '</div>';
        }.bind(this)).join('')
      + '</section>';
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
    var summaryActions = timelapseName
      ? '<div class="summary-actions"><button class="summary-icon-button" type="button" data-action="view-timelapse" aria-label="Open timelapse for ' + this._escapeHtml(archiveName) + '" title="Open Timelapse"><ha-icon icon="mdi:movie-open-play-outline"></ha-icon></button></div>'
      : "";
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
      '<div class="summary-header"><div class="summary-title">' + this._escapeHtml(archiveName) + '</div>' + summaryActions + '</div>' +
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

  async _requestArchiveDuplicates() {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    if (!this._hass || typeof this._hass.callWS !== "function" || archiveId <= 0) {
      throw new Error("Archive action context is unavailable");
    }
    return this._hass.callWS({
      type: "bambuddy/print_history_archive_duplicates",
      archive_id: archiveId,
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

  _matchingDuplicateFamily(archiveId) {
    var normalizedArchiveId = archiveId != null ? String(archiveId) : "";
    if (!normalizedArchiveId || this._duplicateArchiveId !== normalizedArchiveId || !this._duplicateFamily || typeof this._duplicateFamily !== "object") {
      return null;
    }
    return this._duplicateFamily;
  }

  _setDuplicateState(payload, error, archiveId) {
    this._duplicateFamily = payload && typeof payload === "object" ? payload : null;
    this._duplicateError = String(error || "").trim();
    this._duplicateArchiveId = archiveId != null ? String(archiveId) : "";
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

  async _loadDuplicateFamily(options) {
    var settings = options || {};
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    if (archiveId <= 0) {
      this._setStatus("Duplicate family details are unavailable for this archive.", "error");
      return;
    }

    this._mode = "duplicates";
    this._render();

    var cachedFamily = !settings.forceRefresh ? this._matchingDuplicateFamily(archiveId) : null;
    if (cachedFamily) {
      this._lastRenderSignature = "";
      this._render();
      return;
    }

    try {
      this._setBusyState(true, "Loading duplicate family...", "info", "duplicates");
      var response = await this._requestArchiveDuplicates();
      this._busy = false;
      this._busyContext = "";
      this._setDuplicateState(response, "", archiveId);
      this._setStatus("Duplicate family loaded.", "success");
    } catch (error) {
      this._busy = false;
      this._busyContext = "";
      var message = this._describeError(error, "Could not load duplicate family");
      this._setDuplicateState(null, message, archiveId);
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

  async _handleCompareAgainstArchive(candidateArchiveId, backMode) {
    var archive = this._resolveArchive();
    var currentArchiveId = archive && archive.id != null ? Number(archive.id) : 0;
    var normalizedCandidateId = Number(candidateArchiveId || 0);
    if (currentArchiveId <= 0 || normalizedCandidateId <= 0) {
      this._setStatus("Compare target is unavailable.", "error");
      return;
    }
    await this._loadCompareForArchives([currentArchiveId, normalizedCandidateId], backMode || "related");
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

  _renderDuplicateFamilyMember(member) {
    var archiveId = Number(member && member.archive_id || 0);
    var roleLabel = String(member && member.role || "duplicate") === "source" ? "Source" : "Duplicate";
    var currentLabel = member && member.is_current ? "Current Print" : "";
    var sequence = Math.max(0, Number(member && member.duplicate_sequence || 0));
    var metaParts = ['#' + this._escapeHtml(String(archiveId)), this._escapeHtml(this._formatArchiveDate(member && member.created_at))];
    if (sequence > 0) {
      metaParts.push('Copy ' + this._escapeHtml(String(sequence)));
    }
    return '<div class="related-candidate">' +
      '<div class="related-candidate-header">' +
        '<div class="related-candidate-title-block">' +
          '<div class="related-candidate-title">' + this._escapeHtml(String(member && member.print_name || ("Archive " + archiveId))) + '</div>' +
          '<div class="related-candidate-meta">' + metaParts.join(' · ') + '</div>' +
        '</div>' +
        '<div class="related-candidate-badges">' +
          '<span class="candidate-status ' + this._escapeHtml(this._statusBadgeClass(member && member.status)) + '">' + this._escapeHtml(this._statusLabel(member && member.status)) + '</span>' +
          '<span class="candidate-score" style="background:' + this._escapeHtml(String(member && member.role || "") === "source" ? 'rgba(21,101,192,0.18)' : 'rgba(0,137,123,0.18)') + ';">' + this._escapeHtml(roleLabel) + '</span>' +
          (currentLabel ? '<span class="candidate-score" style="background:rgba(255,255,255,0.10);">' + this._escapeHtml(currentLabel) + '</span>' : '') +
        '</div>' +
      '</div>' +
      '<div class="related-candidate-copy">' + this._escapeHtml(
        String(member && member.role || "") === "source"
          ? 'Original source archive for this explicit duplicate family.'
          : 'Duplicate copy in the same explicit Bambuddy duplicate family.'
      ) + '</div>' +
      '<div class="actions-grid related-actions">' +
        this._renderActionButton("duplicate-open", "Open Archive", "mdi:open-in-new", { disabled: this._busy || archiveId <= 0 })
          .replace('data-action="duplicate-open"', 'data-action="duplicate-open" data-archive-id="' + this._escapeHtml(String(archiveId)) + '"') +
        this._renderActionButton("duplicate-compare", "Compare with This Print", "mdi:compare-horizontal", { disabled: this._busy || archiveId <= 0 || !!(member && member.is_current) })
          .replace('data-action="duplicate-compare"', 'data-action="duplicate-compare" data-archive-id="' + this._escapeHtml(String(archiveId)) + '"') +
      '</div>' +
    '</div>';
  }

  _renderDuplicateGroup(title, copy, members, toneClass) {
    if (!Array.isArray(members) || !members.length) {
      return "";
    }
    return '<div class="related-confidence-group ' + this._escapeHtml(String(toneClass || "neutral")) + '">' +
      '<div class="related-confidence-header">' +
        '<div class="related-confidence-title">' + this._escapeHtml(title) + '</div>' +
        '<div class="related-confidence-count">' + this._escapeHtml(String(members.length)) + '</div>' +
      '</div>' +
      '<div class="section-copy">' + this._escapeHtml(copy) + '</div>' +
      '<div class="related-list">' + members.map(function (member) {
        return this._renderDuplicateFamilyMember(member);
      }.bind(this)).join("") + '</div>' +
    '</div>';
  }

  _renderDuplicatesView(archive) {
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    var family = this._matchingDuplicateFamily(archiveId) || {};
    var source = family && family.source && typeof family.source === "object" ? family.source : null;
    var duplicates = family && Array.isArray(family.duplicates) ? family.duplicates : [];
    var toolbar = this._renderActionSection(
      "Duplicates",
      '<div class="actions-grid related-toolbar">' +
        this._renderActionButton("back-main", "Back to Actions", "mdi:arrow-left", { disabled: this._busy }) +
        this._renderActionButton("open-duplicates", this._busy ? "Loading..." : "Refresh Family", "mdi:refresh", { disabled: this._busy }) +
      '</div>' +
      '<div class="section-copy">' + this._escapeHtml("This view uses Bambuddy's explicit duplicate lineage fields, not the broader related-match feed. It works from either the source archive or any duplicate copy in the same family.") + '</div>'
    );
    var body;
    if (this._duplicateError) {
      body = '<div class="section-copy">' + this._escapeHtml(this._duplicateError) + '</div>';
    } else if (!source && !duplicates.length) {
      body = '<div class="section-copy">No explicit duplicate family is available for this archive yet.</div>';
    } else {
      body = '<div class="related-groups">' +
        this._renderDuplicateGroup(
          "Source Print",
          "Anchor archive for this duplicate family.",
          source ? [source] : [],
          "high"
        ) +
        this._renderDuplicateGroup(
          "Duplicate Copies",
          "Other archives that Bambuddy marks as copies in the same family.",
          duplicates,
          "medium"
        ) +
      '</div>';
    }
    return '<div class="section-stack">' + toolbar + this._renderActionSection("Family", body) + '</div>';
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
            if (String(row && row.field || "") === "content_hash" && cellValue !== '-') {
              var shortHash = cellValue.length > 18 ? (cellValue.slice(0, 10) + '...' + cellValue.slice(-8)) : cellValue;
              return '<td><span class="compare-hash" title="' + this._escapeHtml(cellValue) + '">' + this._escapeHtml(shortHash) + '</span></td>';
            }
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
    var toolbarAction = this._compareBackMode === "related" ? "back-related" : this._compareBackMode === "duplicates" ? "back-duplicates" : "back-main";
    var toolbarLabel = this._compareBackMode === "related" ? "Back to Matches" : this._compareBackMode === "duplicates" ? "Back to Duplicates" : "Back to Actions";
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
    
    // Model catalog section - shows when a model is linked
    var linkedModel = archive && archive.linked_model;
    var modelCatalogActions = linkedModel
      ? this._renderActionSection(
          "Model Catalog",
          '<div class="actions-grid">' +
            this._renderActionButton("view-source-model", "View Source Model", "mdi:cube-outline", { disabled: this._busy }) +
            this._renderActionButton("edit-model-metadata", "Edit Model Metadata", "mdi:pencil", { disabled: this._busy }) +
            this._renderActionButton("view-similar-models", "Similar Models", "mdi:relation-many-to-many", { disabled: this._busy }) +
          '</div>'
        )
      : '';
    
    var relationActions = this._renderActionSection(
      "Related, Duplicates & Compare",
      '<div class="actions-grid">' +
        this._renderActionButton("open-related", "Related Prints", "mdi:relation-many", { disabled: this._busy }) +
        this._renderActionButton("open-duplicates", "Duplicates", "mdi:content-copy", { disabled: this._busy }) +
        this._renderActionButton("open-compare", "Compare with Another Print", "mdi:compare-horizontal", { disabled: this._busy }) +
      '</div>' +
      '<div class="section-copy">Use Related Prints for broader similarity matches, Duplicates for explicit Bambuddy duplicate families, or Compare to inspect selected archives side by side without widening the browser payload.</div>'
    );
    var fileActions = '<div class="actions-grid">' +
      this._renderActionButton("download-model", "Download Gcode file", "mdi:download", { disabled: !hasGcodeFile || this._busy }) +
      (hasSource ? this._renderActionButton("download-source-3mf", "Download 3MF", "mdi:file-download-outline", { disabled: this._busy }) : "") +
      this._renderActionButton("upload-source-3mf", hasSource ? "Replace Source 3MF" : "Upload Source 3MF", "mdi:upload", { disabled: this._busy }) +
      (this._sourceUploadPreview ? ('<div style="grid-column: 1 / -1; margin-top: 8px; padding: 12px; border-radius: 4px; background: var(--card-background-color);">' +
        '<div style="font-size: 0.85rem; color: var(--secondary-text-color); margin-bottom: 8px;">3MF Browser Preview: ' + this._escapeHtml(this._sourceUploadPreviewFilename) + '</div>' +
        '<img src="' + this._sourceUploadPreview + '" style="max-width: 100%; max-height: 200px; border-radius: 4px; display: block;" />' +
        '</div>') : '') +
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
      ) + '</div>' + this._timelapseScanDiagnosticsMarkup()
    );
    var storageActions = this._renderStorageSection(archive);
    var analyticsActions = this._renderActionSection(
      "Failure Analysis",
      '<div class="actions-grid single-column">' +
        this._renderActionButton("open-failure-analysis", "Open Failure Analysis", "mdi:chart-line", { disabled: this._busy }) +
      '</div>' +
      '<div class="section-copy">Open the statistics failure-analysis view seeded to this archive so you can inspect nearby outcome context and comparable failed prints.</div>'
    );
    var repairActions = this._renderActionSection(
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
    var mainBody = this._mainTab === "analytics"
      ? '<div class="main-tab-panel" role="tabpanel">' + this._renderAnalyticsOverview(archive) + relationActions + storageActions + analyticsActions + '</div>'
      : this._mainTab === "repair"
        ? '<div class="main-tab-panel" role="tabpanel">' + repairActions + '</div>'
        : this._mainTab === "danger"
          ? '<div class="main-tab-panel" role="tabpanel">' + dangerActions + '</div>'
          : this._mainTab === "model"
            ? '<div class="main-tab-panel" role="tabpanel">' + this._renderModelTab(archive) + '</div>'
            : '<div class="main-tab-panel" role="tabpanel">'
              + modelCatalogActions
              + this._renderActionSection("Files", fileActions)
              + linkActions
              + timelapseActions
              + '</div>';
    return '<div class="section-stack tabbed-main">'
      + this._renderMainTabs()
      + mainBody
      + '<input id="source-upload-input" class="hidden-file-input" type="file" accept=".3mf,application/vnd.ms-package.3dmanufacturing-3dmodel+xml">'
      + '<input id="timelapse-upload-input" class="hidden-file-input" type="file" accept=".mp4,.avi,.mkv,video/mp4,video/x-msvideo,video/x-matroska">'
      + '</div>';
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

  // ─── Model Catalog Tab ────────────────────────────────────────────────────

  _modelCatalogBaseUrl() {
    var entityId = this._config && this._config.model_catalog_sidecar_base_url_entity
      ? this._config.model_catalog_sidecar_base_url_entity
      : "input_text.model_catalog_sidecar_base_url";
    if (!this._hass || !this._hass.states || !this._hass.states[entityId]) {
      return "";
    }
    var baseUrl = String(this._hass.states[entityId].state || "").trim();
    if (!/^https?:\/\//i.test(baseUrl)) {
      return "";
    }
    return baseUrl.replace(/\/$/, "");
  }

  _renderModelSearchModal(archive) {
    var archiveId = archive && archive.id ? String(archive.id) : "";
    var searchHtml = '<div class="model-search-modal-overlay">'
      + '<div class="model-search-modal">'
      + '<div class="model-search-modal-header">'
      + '<h2 class="model-search-modal-title">Search Model Library</h2>'
      + '<button class="model-search-modal-close" type="button" data-action="model-search-close"><ha-icon icon="mdi:close"></ha-icon></button>'
      + '</div>'
      + '<div class="model-search-modal-body">'
      + '<div class="model-search-form">'
      + '<div class="model-search-field">'
      + '<label for="model-search-q">Search</label>'
      + '<input type="text" id="model-search-q" class="model-search-input" placeholder="Model name..." value="' + this._escapeHtml(this._modelSearchQuery) + '">'
      + '</div>'
      + '<div class="model-search-field">'
      + '<label for="model-search-collection">Collection</label>'
      + '<input type="text" id="model-search-collection" class="model-search-input" placeholder="e.g., Gridfinity..." value="' + this._escapeHtml(this._modelSearchCollection) + '">'
      + '</div>'
      + '<div class="model-search-field">'
      + '<label for="model-search-creator">Creator</label>'
      + '<input type="text" id="model-search-creator" class="model-search-input" placeholder="e.g., Rysock..." value="' + this._escapeHtml(this._modelSearchCreator) + '">'
      + '</div>'
      + '<div class="model-search-field">'
      + '<label for="model-search-tag">Tag</label>'
      + '<input type="text" id="model-search-tag" class="model-search-input" placeholder="e.g., storage..." value="' + this._escapeHtml(this._modelSearchTag) + '">'
      + '</div>'
      + '<button class="model-search-button" type="button" data-action="model-search-execute" ' + (this._modelSearchBusy ? "disabled" : "") + '>'
      + (this._modelSearchBusy ? '<ha-icon icon="mdi:loading" class="spin-icon"></ha-icon> Searching…' : '<ha-icon icon="mdi:magnify"></ha-icon> Search')
      + '</button>'
      + '</div>';

    if (this._modelSearchBusy) {
      searchHtml += '<div class="model-search-results"><div class="model-search-loading"><ha-icon icon="mdi:loading" class="spin-icon"></ha-icon> Loading results…</div></div>';
    } else if (this._modelSearchError) {
      searchHtml += '<div class="model-search-results"><div class="model-search-error">' + this._escapeHtml(this._modelSearchError) + '</div></div>';
    } else if (!this._modelSearchResults.length && this._modelSearchHasSearched) {
      searchHtml += '<div class="model-search-results"><div class="model-search-empty"><p>No models found matching your search.</p></div></div>';
    } else if (this._modelSearchResults.length) {
      var self = this;
      var resultsHtml = this._modelSearchResults.map(function (result) {
        var resultUrl = result.model_url || "";
        var resultName = result.name || "Unnamed Model";
        var resultCreator = result.creator_name || "Unknown Creator";
        var linkedCount = result.linked_archive_count || 0;
        var collectionsList = (result.collection_names || []).join(", ") || "No Collection";
        return '<div class="model-search-result-card">'
          + '<div class="model-search-result-header">'
          + '<div>'
          + '<h3 class="model-search-result-name">' + self._escapeHtml(resultName) + '</h3>'
          + '<p class="model-search-result-meta">' + self._escapeHtml(resultCreator) + ' / ' + self._escapeHtml(collectionsList) + '</p>'
          + '</div>'
          + '<button class="model-search-result-link" type="button" data-action="model-search-link-result" data-result-url="' + self._escapeHtml(resultUrl) + '"><ha-icon icon="mdi:link-variant"></ha-icon> Link</button>'
          + '</div>'
          + '<p class="model-search-result-linked">Linked to ' + String(linkedCount) + ' archive' + (linkedCount !== 1 ? 's' : '') + '</p>'
          + '</div>';
      }).join("");
      var paginationHtml = this._modelSearchTotalPages > 1
        ? '<div class="model-search-pagination">'
          + (this._modelSearchPage > 1 ? '<button class="model-search-page-btn" type="button" data-action="model-search-prev-page"><ha-icon icon="mdi:chevron-left"></ha-icon> Previous</button>' : '')
          + '<span class="model-search-page-info">Page ' + String(this._modelSearchPage) + ' of ' + String(this._modelSearchTotalPages) + '</span>'
          + (this._modelSearchPage < this._modelSearchTotalPages ? '<button class="model-search-page-btn" type="button" data-action="model-search-next-page">Next <ha-icon icon="mdi:chevron-right"></ha-icon></button>' : '')
          + '</div>'
        : '';
      searchHtml += '<div class="model-search-results">' + resultsHtml + paginationHtml + '</div>';
    }

    searchHtml += '</div>'
      + '</div>'
      + '</div>';

    return searchHtml;
  }

  async _loadModelLinks(archiveId) {
    if (!archiveId || this._modelLinksBusy) {
      return;
    }
    this._modelLinksBusy = true;
    this._modelLinksError = "";
    this._lastRenderSignature = "";
    this._render();
    try {
      var result = await this._callServiceWithResponse("rest_command", "model_catalog_get_archive_links", {
        archive_id: String(archiveId),
        include_inactive: false,
      });
      this._modelLinks = Array.isArray(result && result.links) ? result.links : [];
      this._modelLinksArchiveId = String(archiveId);
    } catch (err) {
      this._modelLinksError = err && err.message ? String(err.message) : "Failed to load model links";
      this._modelLinks = [];
    } finally {
      this._modelLinksBusy = false;
      this._lastRenderSignature = "";
      this._render();
    }
  }

  async _executeModelSearch(pageNumber) {
    // Capture current form values
    var qInput = this.shadowRoot ? this.shadowRoot.querySelector("#model-search-q") : null;
    var collectionInput = this.shadowRoot ? this.shadowRoot.querySelector("#model-search-collection") : null;
    var creatorInput = this.shadowRoot ? this.shadowRoot.querySelector("#model-search-creator") : null;
    var tagInput = this.shadowRoot ? this.shadowRoot.querySelector("#model-search-tag") : null;
    
    this._modelSearchQuery = qInput ? String(qInput.value || "").trim() : "";
    this._modelSearchCollection = collectionInput ? String(collectionInput.value || "").trim() : "";
    this._modelSearchCreator = creatorInput ? String(creatorInput.value || "").trim() : "";
    this._modelSearchTag = tagInput ? String(tagInput.value || "").trim() : "";
    
    var baseUrl = this._modelCatalogBaseUrl();
    if (!baseUrl) {
      this._modelSearchError = "Model catalog sidecar not configured";
      this._render();
      return;
    }
    
    this._modelSearchPage = Math.max(1, pageNumber || 1);
    this._modelSearchHasSearched = true;
    this._modelSearchBusy = true;
    this._modelSearchError = "";
    this._lastRenderSignature = "";
    this._render();
    
    try {
      var data = await this._callServiceWithResponse("rest_command", "model_catalog_search_models", {
        q: this._modelSearchQuery,
        collection: this._modelSearchCollection,
        creator: this._modelSearchCreator,
        tag: this._modelSearchTag,
        refresh: true,
        page: this._modelSearchPage,
        per_page: 10,
      });
      this._modelSearchResults = Array.isArray(data && data.results) ? data.results : [];
      var paginationInfo = data && data.pagination ? data.pagination : {};
      this._modelSearchTotalPages = paginationInfo.total_pages || 0;
    } catch (err) {
      var message = err && err.message ? String(err.message) : "Search failed";
      if (message === "Failed to fetch") {
        message = "Search request failed. Verify the model catalog sidecar URL is reachable from Home Assistant.";
      }
      this._modelSearchError = message;
      this._modelSearchResults = [];
    } finally {
      this._modelSearchBusy = false;
      this._lastRenderSignature = "";
      this._render();
    }
  }

  async _modelCatalogAction(action, archiveId, linkId, extra) {
    if (this._modelLinksBusy) {
      return;
    }
    this._modelLinksBusy = true;
    this._modelLinksError = "";
    var statusMessage = "";
    var statusTone = "info";
    this._lastRenderSignature = "";
    this._render();
    try {
      if (action === "refresh-candidates") {
        var refreshResult = await this._callServiceWithResponse("rest_command", "model_catalog_refresh_archive_candidates", {
          archive_id: String(archiveId),
          archive_name: extra && extra.archive_name ? String(extra.archive_name) : "",
          source_file_name: extra && extra.source_file_name ? String(extra.source_file_name) : "",
          source_hash: extra && extra.source_hash ? String(extra.source_hash) : "",
          archive_completed_at: extra && extra.archive_completed_at ? String(extra.archive_completed_at) : "",
          force_refresh_model_cache: true,
        });
        var candidateCount = Array.isArray(refreshResult && refreshResult.candidates) ? refreshResult.candidates.length : 0;
        if (candidateCount > 0) {
          statusMessage = candidateCount === 1
            ? "Found 1 model candidate."
            : "Found " + String(candidateCount) + " model candidates.";
          statusTone = "success";
        } else {
          statusMessage = "No model candidates found for this archive name.";
        }
      } else if (action === "accept-link") {
        await this._callServiceWithResponse("script", "model_catalog_accept_and_notify", {
          archive_id: String(archiveId),
          link_id: Number(linkId),
          model_url: extra && extra.model_url ? String(extra.model_url) : "",
        });
        statusMessage = "Model link accepted.";
        statusTone = "success";
      } else if (action === "reject-link") {
        await this._callServiceWithResponse("rest_command", "model_catalog_reject_archive_link", {
          archive_id: String(archiveId),
          link_id: Number(linkId),
        });
        statusMessage = "Model candidate rejected.";
        statusTone = "success";
      } else if (action === "deactivate-link") {
        await this._callServiceWithResponse("rest_command", "model_catalog_deactivate_archive_link", {
          archive_id: String(archiveId),
          link_id: Number(linkId),
        });
        statusMessage = "Model link removed.";
        statusTone = "success";
      } else if (action === "create-manual-link") {
        var manualUrl = String(extra && extra.model_url ? extra.model_url : "").trim();
        if (!manualUrl) {
          this._modelLinksError = "Enter a model URL to create a manual link.";
          this._modelLinksBusy = false;
          this._lastRenderSignature = "";
          this._render();
          return;
        }
        await this._callServiceWithResponse("rest_command", "model_catalog_create_archive_link", {
          archive_id: String(archiveId),
          model_url: manualUrl,
          relationship_type: "printed_from",
        });
        this._modelManualUrl = "";
        // Close search modal if creating from search results
        this._modelSearchMode = false;
        statusMessage = "Manual model link created.";
        statusTone = "success";
      }
    } catch (err) {
      this._modelLinksError = err && err.message ? String(err.message) : "Action failed";
      this._setStatus(this._modelLinksError, "error");
    } finally {
      this._modelLinksBusy = false;
    }
    // Reload links after any action
    this._modelLinksArchiveId = "";
    await this._loadModelLinks(archiveId);
    if (statusMessage) {
      this._setStatus(statusMessage, statusTone);
    }
  }

  _renderModelLinkRow(link, archiveId) {
    var modelUrl = link.model_url ? String(link.model_url) : "";
    var modelName = link.model_name ? String(link.model_name) : "";
    var displayUrl = modelUrl.length > 60 ? modelUrl.slice(0, 57) + "…" : modelUrl;
    var role = String(link.link_role || "manual");
    var confidence = String(link.match_confidence || "");
    var reviewState = String(link.review_state || "");
    var isAccepted = reviewState === "accepted";

    var statusBadge = isAccepted
      ? '<span class="model-link-badge badge-accepted">confirmed</span>'
      : role === "candidate"
        ? '<span class="model-link-badge badge-candidate">candidate' + (confidence ? " · " + this._escapeHtml(confidence) : "") + '</span>'
        : '<span class="model-link-badge badge-manual">manual</span>';

    var noteHtml = "";
    if (link.review_note) {
      try {
        var parsed = JSON.parse(link.review_note);
        if (parsed && parsed.summary) {
          noteHtml = '<div class="model-link-note">' + this._escapeHtml(parsed.summary) + '</div>';
          if (parsed.signals && parsed.signals.length > 0) {
            noteHtml += '<div class="model-link-signals">';
            for (var si = 0; si < parsed.signals.length; si++) {
              var sig = parsed.signals[si];
              var label = String(sig.type || "").replace(/_/g, " ");
              var strength = String(sig.strength || "");
              noteHtml += '<span class="signal-pill signal-' + this._escapeHtml(strength) + '">' + this._escapeHtml(label) + '</span>';
            }
            noteHtml += '</div>';
          }
        } else {
          noteHtml = '<div class="model-link-note">' + this._escapeHtml(String(link.review_note)) + '</div>';
        }
      } catch (e) {
        noteHtml = '<div class="model-link-note">' + this._escapeHtml(String(link.review_note)) + '</div>';
      }
    }

    var acceptBtn = !isAccepted
      ? '<button class="model-link-action-btn btn-accept" type="button" data-action="model-accept-link" data-link-id="' + String(link.id) + '" data-model-url="' + this._escapeHtml(modelUrl) + '" ' + (this._modelLinksBusy ? "disabled" : "") + '>Accept</button>'
      : "";
    var rejectBtn = !isAccepted && role === "candidate"
      ? '<button class="model-link-action-btn btn-reject" type="button" data-action="model-reject-link" data-link-id="' + String(link.id) + '" ' + (this._modelLinksBusy ? "disabled" : "") + '>Reject</button>'
      : "";
    var deactivateBtn = isAccepted
      ? '<button class="model-link-action-btn btn-deactivate" type="button" data-action="model-deactivate-link" data-link-id="' + String(link.id) + '" ' + (this._modelLinksBusy ? "disabled" : "") + '>Remove</button>'
      : "";

    var catalogLink = modelUrl
      ? '<a class="model-link-url" href="' + this._escapeHtml(modelUrl) + '" target="_blank" rel="noopener noreferrer">' + this._escapeHtml(displayUrl) + '</a>'
      : '<span class="model-link-url-empty">(no URL)</span>';
    var nameHtml = modelName
      ? '<div class="model-link-name">' + this._escapeHtml(modelName) + '</div>'
      : '';

    return '<div class="model-link-row">'
      + '<div class="model-link-row-header">' + statusBadge + '</div>'
      + nameHtml
      + catalogLink
      + noteHtml
      + '<div class="model-link-row-actions">' + acceptBtn + rejectBtn + deactivateBtn + '</div>'
      + '</div>';
  }

  _renderModelTab(archive) {
    var archiveId = archive && archive.id ? String(archive.id) : "";

    // Auto-load on first view
    if (archiveId && archiveId !== this._modelLinksArchiveId && !this._modelLinksBusy) {
      this._loadModelLinks(archiveId);
    }

    var baseUrl = this._modelCatalogBaseUrl();
    if (!baseUrl) {
      return this._renderActionSection(
        "Model Catalog",
        '<div class="model-tab-empty"><ha-icon icon="mdi:server-off"></ha-icon>'
        + '<p>Set <code>input_text.model_catalog_sidecar_base_url</code> to a full sidecar base URL such as <code>http://host:8314</code> to enable model linking.</p></div>'
      );
    }

    var linksHtml = "";
    if (this._modelLinksBusy) {
      linksHtml = '<div class="model-tab-loading"><ha-icon icon="mdi:loading" class="spin-icon"></ha-icon> Loading…</div>';
    } else if (this._modelLinksError) {
      linksHtml = '<div class="model-tab-error">' + this._escapeHtml(this._modelLinksError) + '</div>';
    } else if (!this._modelLinks.length) {
      linksHtml = '<div class="model-tab-empty"><ha-icon icon="mdi:cube-off-outline"></ha-icon><p>No model links yet.</p></div>';
    } else {
      var self = this;
      linksHtml = this._modelLinks.map(function (link) {
        return self._renderModelLinkRow(link, archiveId);
      }).join("");
    }

    var manualForm = '<div class="model-manual-form">'
      + '<label class="model-manual-label">Model URL</label>'
      + '<input class="model-manual-input" type="text" id="model-manual-url-input" placeholder="local://model/my-model-name" value="' + this._escapeHtml(this._modelManualUrl || "") + '" ' + (this._modelLinksBusy ? "disabled" : "") + '>'
      + '<button class="model-link-action-btn btn-accept" type="button" data-action="model-create-link" ' + (this._modelLinksBusy ? "disabled" : "") + '>Link</button>'
      + '</div>';

    var header = '<div class="model-tab-toolbar">'
      + '<button class="model-link-action-btn" type="button" data-action="model-search-library" ' + (this._modelLinksBusy ? "disabled" : "") + '><ha-icon icon="mdi:library-shelves"></ha-icon> Search Library</button>'
      + '<button class="model-link-action-btn" type="button" data-action="model-refresh-candidates" ' + (this._modelLinksBusy ? "disabled" : "") + '><ha-icon icon="mdi:magnify"></ha-icon> Find Candidates</button>'
      + '<button class="model-link-action-btn" type="button" data-action="model-reload-links" ' + (this._modelLinksBusy ? "disabled" : "") + '><ha-icon icon="mdi:refresh"></ha-icon> Reload</button>'
      + '</div>';

    return this._renderActionSection(
      "Model Links",
      header + '<div class="model-links-list">' + linksHtml + '</div>' + manualForm
    );
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
        '.model-link-name{margin-top:6px;font-size:14px;font-weight:700;line-height:1.35;color:var(--primary-text-color);word-break:break-word;}' +
        '.model-link-url,.model-link-url-empty{display:inline-flex;margin-top:4px;font-size:12px;line-height:1.4;word-break:break-all;}' +
      '.summary-preview img{display:block;width:100%;height:100%;object-fit:cover;}' +
      '.summary-preview.placeholder{background:rgba(15,23,42,0.20);color:var(--secondary-text-color);}' +
      '.summary-preview.placeholder ha-icon{--mdc-icon-size:20px;}' +
      '.summary-header{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;}' +
      '.summary-title{font-size:15px;font-weight:700;line-height:1.35;word-break:break-word;}' +
      '.summary-actions{display:flex;align-items:center;gap:8px;flex:0 0 auto;}' +
      '.summary-icon-button{appearance:none;-webkit-appearance:none;display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:999px;border:1px solid rgba(96,165,250,0.24);background:rgba(30,64,175,0.16);color:var(--primary-text-color);cursor:pointer;box-shadow:none;}' +
      '.summary-icon-button:hover,.summary-icon-button:focus-visible{background:rgba(30,64,175,0.26);border-color:rgba(96,165,250,0.4);outline:none;}' +
      '.summary-icon-button ha-icon{--mdc-icon-size:18px;}' +
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
      '.tabbed-main{gap:14px;}' +
      '.analytics-overview{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;}' +
      '.analytics-kpi{border-radius:18px;border:1px solid rgba(255,255,255,0.08);background:linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02));padding:12px;display:grid;gap:6px;min-width:0;}' +
      '.analytics-kpi.accent{border-color:rgba(96,165,250,0.34);background:linear-gradient(180deg,rgba(30,64,175,0.18),rgba(255,255,255,0.03));}' +
      '.analytics-kpi-label{font-size:11px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:var(--secondary-text-color);}' +
      '.analytics-kpi-value{font-size:15px;font-weight:800;line-height:1.35;word-break:break-word;}' +
      '.analytics-kpi-meta{font-size:12px;line-height:1.45;color:var(--secondary-text-color);}' +
      '.main-tablist{display:flex;align-items:stretch;gap:10px;overflow:auto;padding:2px 0 4px;scrollbar-width:thin;}' +
      '.main-tab-button{appearance:none;-webkit-appearance:none;display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;padding:10px 14px;border-radius:999px;border:1px solid rgba(255,255,255,0.10);background:rgba(255,255,255,0.03);color:var(--primary-text-color);font:inherit;font-size:13px;font-weight:800;line-height:1.2;white-space:nowrap;cursor:pointer;flex:0 0 auto;}' +
      '.main-tab-button:hover,.main-tab-button:focus-visible{background:rgba(255,255,255,0.08);border-color:rgba(255,255,255,0.18);outline:none;}' +
      '.main-tab-button.active{background:rgba(30,64,175,0.20);border-color:rgba(96,165,250,0.40);box-shadow:inset 0 1px 0 rgba(255,255,255,0.04);}' +
      '.main-tab-button ha-icon{--mdc-icon-size:18px;flex:0 0 auto;}' +
      '.main-tab-panel{display:flex;flex-direction:column;gap:12px;min-width:0;}' +
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
      '.compare-hash{font-family:ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",Menlo,monospace;font-size:12px;line-height:1.4;word-break:break-all;}' +
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
      '.model-tab-toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;}' +
      '.model-tab-empty,.model-tab-loading,.model-tab-error{display:flex;flex-direction:column;align-items:center;gap:8px;padding:20px 12px;color:var(--secondary-text-color);font-size:13px;text-align:center;}' +
      '.model-tab-error{color:var(--error-color,#cf6679);}' +
      '.model-tab-loading .spin-icon,.model-tab-empty ha-icon,.model-tab-error ha-icon{--mdc-icon-size:28px;}' +
      '.model-links-list{display:grid;gap:10px;margin-bottom:14px;}' +
      '.model-link-row{border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:10px 12px;background:rgba(255,255,255,0.03);display:flex;flex-direction:column;gap:6px;}' +
      '.model-link-row-header{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}' +
      '.model-link-badge{display:inline-flex;align-items:center;border-radius:999px;padding:2px 8px;font-size:11px;font-weight:700;letter-spacing:.04em;}' +
      '.badge-accepted{background:rgba(34,197,94,0.18);color:#4ade80;}' +
      '.badge-candidate{background:rgba(234,179,8,0.18);color:#facc15;}' +
      '.badge-manual{background:rgba(96,165,250,0.18);color:#60a5fa;}' +
      '.model-link-url{font-size:12px;color:var(--primary-color,#03a9f4);word-break:break-all;text-decoration:none;}' +
      '.model-link-url:hover{text-decoration:underline;}' +
      '.model-link-url-empty{font-size:12px;color:var(--secondary-text-color);}' +
      '.model-link-note{font-size:11px;color:var(--secondary-text-color);font-style:italic;}' +
      '.model-link-signals{display:flex;gap:4px;flex-wrap:wrap;margin-top:2px;}' +
      '.signal-pill{display:inline-flex;align-items:center;border-radius:999px;padding:1px 7px;font-size:10px;font-weight:600;letter-spacing:.03em;background:rgba(148,163,184,0.14);color:var(--secondary-text-color);}' +
      '.signal-deterministic{background:rgba(34,197,94,0.18);color:#4ade80;}' +
      '.signal-strong{background:rgba(96,165,250,0.18);color:#60a5fa;}' +
      '.signal-moderate{background:rgba(234,179,8,0.18);color:#facc15;}' +
      '.signal-weak{background:rgba(148,163,184,0.14);color:var(--secondary-text-color);}' +
      '.model-link-row-actions{display:flex;gap:6px;flex-wrap:wrap;}' +
      '.model-link-action-btn{appearance:none;-webkit-appearance:none;border:1px solid rgba(148,163,184,0.24);background:rgba(15,23,42,0.92);color:var(--primary-text-color);border-radius:999px;padding:6px 12px;font:inherit;font-size:12px;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;gap:4px;}' +
      '.model-link-action-btn:hover:not(:disabled){background:rgba(30,41,59,0.96);border-color:rgba(96,165,250,0.36);}' +
      '.model-link-action-btn:disabled{opacity:.4;cursor:default;}' +
      '.btn-accept{border-color:rgba(34,197,94,0.36);color:#4ade80;}' +
      '.btn-accept:hover:not(:disabled){background:rgba(34,197,94,0.12);}' +
      '.btn-reject{border-color:rgba(239,68,68,0.36);color:#f87171;}' +
      '.btn-reject:hover:not(:disabled){background:rgba(239,68,68,0.08);}' +
      '.btn-deactivate{border-color:rgba(148,163,184,0.24);color:var(--secondary-text-color);}' +
      '.model-manual-form{display:flex;flex-direction:column;gap:8px;padding:10px 12px;border:1px solid rgba(255,255,255,0.08);border-radius:12px;background:rgba(255,255,255,0.02);}' +
      '.model-manual-label{font-size:11px;font-weight:700;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.06em;}' +
      '.model-manual-input{background:rgba(9,14,23,0.78);border:1px solid rgba(148,163,184,0.20);border-radius:8px;padding:6px 10px;color:var(--primary-text-color);font:inherit;font-size:12px;width:100%;box-sizing:border-box;}' +
      '.model-manual-input:focus{outline:none;border-color:rgba(96,165,250,0.36);}' +
      '.model-search-modal-overlay{display:block;width:100%;padding:0;box-sizing:border-box;overflow-x:hidden;}' +
      '.model-search-modal{background:var(--card-background-color,rgba(15,23,42,0.95));border:1px solid rgba(255,255,255,0.12);border-radius:20px;padding:16px;max-width:none;width:100%;max-height:min(68vh,720px);display:flex;flex-direction:column;gap:12px;box-shadow:0 12px 36px rgba(0,0,0,0.28);overflow:hidden;box-sizing:border-box;}' +
      '.model-search-modal-header{display:flex;align-items:center;justify-content:space-between;gap:12px;}' +
      '.model-search-modal-title{font-size:18px;font-weight:700;line-height:1.35;margin:0;}' +
      '.model-search-modal-close{appearance:none;-webkit-appearance:none;width:32px;height:32px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(15,23,42,0.92);color:var(--primary-text-color);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;}' +
      '.model-search-modal-close:hover{background:rgba(30,41,59,0.96);border-color:rgba(96,165,250,0.36);}' +
      '.model-search-modal-close ha-icon{--mdc-icon-size:20px;}' +
      '.model-search-modal-body{display:flex;flex-direction:column;gap:12px;overflow:auto;padding-right:4px;box-sizing:border-box;min-width:0;}' +
      '.model-search-form{display:grid;gap:12px;}' +
      '.model-search-field{display:grid;gap:6px;}' +
      '.model-search-field label{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--secondary-text-color);}' +
      '.model-search-input{background:rgba(9,14,23,0.78);border:1px solid rgba(148,163,184,0.20);border-radius:8px;padding:8px 12px;color:var(--primary-text-color);font:inherit;font-size:12px;width:100%;box-sizing:border-box;}' +
      '.model-search-input:focus{outline:none;border-color:rgba(96,165,250,0.36);}' +
      '.model-search-button{appearance:none;-webkit-appearance:none;background:rgba(59,130,246,0.16);border:1px solid rgba(96,165,250,0.36);border-radius:999px;padding:10px 16px;color:var(--primary-text-color);font:inherit;font-size:12px;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:6px;width:100%;}' +
      '.model-search-button:hover:not(:disabled){background:rgba(59,130,246,0.24);}' +
      '.model-search-button:disabled{opacity:.4;cursor:default;}' +
      '.model-search-button .spin-icon{--mdc-icon-size:16px;animation:phaSpin 0.8s linear infinite;}' +
      '.model-search-button ha-icon{--mdc-icon-size:16px;}' +
      '.model-search-results{display:grid;gap:10px;min-width:0;}' +
      '.model-search-loading,.model-search-empty,.model-search-error{display:flex;flex-direction:column;align-items:center;gap:8px;padding:20px 12px;color:var(--secondary-text-color);font-size:13px;text-align:center;}' +
      '.model-search-error{color:var(--error-color,#cf6679);}' +
      '.model-search-loading .spin-icon,.model-search-empty ha-icon,.model-search-error ha-icon{--mdc-icon-size:28px;}' +
      '.model-search-result-card{border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:12px;background:rgba(255,255,255,0.03);display:flex;flex-direction:column;gap:8px;}' +
      '.model-search-result-header{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;}' +
      '.model-search-result-name{font-size:14px;font-weight:700;line-height:1.35;margin:0;word-break:break-word;}' +
      '.model-search-result-meta{font-size:12px;line-height:1.4;color:var(--secondary-text-color);margin:4px 0 0;}' +
      '.model-search-result-link{appearance:none;-webkit-appearance:none;border:1px solid rgba(96,165,250,0.36);background:rgba(59,130,246,0.12);border-radius:999px;padding:6px 10px;color:var(--primary-text-color);font:inherit;font-size:11px;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;gap:4px;flex:0 0 auto;white-space:nowrap;}' +
      '.model-search-result-link:hover{background:rgba(59,130,246,0.20);}' +
      '.model-search-result-link ha-icon{--mdc-icon-size:14px;}' +
      '.model-search-result-linked{font-size:11px;color:var(--secondary-text-color);margin:0;}' +
      '.model-search-pagination{display:flex;align-items:center;justify-content:center;gap:12px;padding:12px;border-top:1px solid rgba(255,255,255,0.08);margin-top:8px;}' +
      '.model-search-page-info{font-size:12px;color:var(--secondary-text-color);}' +
      '.model-search-page-btn{appearance:none;-webkit-appearance:none;border:1px solid rgba(96,165,250,0.36);background:rgba(59,130,246,0.12);border-radius:999px;padding:6px 10px;color:var(--primary-text-color);font:inherit;font-size:11px;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;gap:4px;}' +
      '.model-search-page-btn:hover{background:rgba(59,130,246,0.20);}' +
      '.model-search-page-btn ha-icon{--mdc-icon-size:14px;}' +
      '@media (max-width: 900px){.analytics-overview{grid-template-columns:repeat(2,minmax(0,1fr));}}' +
      '@media (max-width: 700px){.main-tablist{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));overflow:visible;}.main-tab-button{width:100%;padding:12px 10px;white-space:normal;}.main-tab-button span{text-align:center;}}'  +
      '@media (max-width: 520px){.summary-grid{grid-template-columns:1fr;}.summary-preview{width:100%;height:140px;}.actions-grid{grid-template-columns:1fr;}.storage-grid{grid-template-columns:1fr;}.metadata-form-grid{grid-template-columns:1fr;}.json-panel-summary{align-items:flex-start;flex-direction:column;}.json-copy-button{width:100%;}.main-tablist{grid-template-columns:1fr;}.analytics-overview{grid-template-columns:1fr;}.model-search-modal{max-height:min(62vh,640px);padding:14px;}}' +
      '</style>' +
      '<div class="shell">' +
      this._renderSummary(archive) +
      this._renderStatus() +
      (this._modelSearchMode
        ? this._renderModelSearchModal(archive)
        : confirmDelete
          ? this._renderDeleteConfirm(archive, this._mode === "confirm-delete-2")
          : this._mode === "metadata"
            ? this._renderMetadataView(archive)
            : this._mode === "repair-chooser"
              ? this._renderRepairChooserView(archive)
            : this._mode === "correct-metadata"
              ? this._renderMetadataCorrectionView(archive)
            : this._mode === "related"
              ? this._renderRelatedView(archive)
            : this._mode === "duplicates"
              ? this._renderDuplicatesView(archive)
            : this._mode === "compare"
              ? this._renderCompareView(archive)
          : this._renderMain(archive)) +
      '</div>';
  }

  // Phase 3.3: Model Catalog Navigation Handlers
  _handleViewSourceModel() {
    var archive = this._resolveArchive();
    if (!archive || !archive.linked_model) {
      this._status = "No linked model found";
      this._statusTone = "warning";
      this._render();
      return;
    }
    var modelRef = archive.linked_model.model_ref || archive.linked_model.model_id || "";
    if (!modelRef) {
      this._status = "Cannot determine model reference";
      this._statusTone = "error";
      this._render();
      return;
    }
    // Dispatch event for browser_mod to open model-detail-popup-card
    window.dispatchEvent(new CustomEvent("ha-model-catalog-navigate", {
      detail: { action: "view-model", model_ref: modelRef }
    }));
    this._status = "Navigating to model detail...";
    this._statusTone = "info";
    this._render();
  }

  _handleEditModelMetadata() {
    var archive = this._resolveArchive();
    if (!archive || !archive.linked_model) {
      this._status = "No linked model found";
      this._statusTone = "warning";
      this._render();
      return;
    }
    var modelRef = archive.linked_model.model_ref || archive.linked_model.model_id || "";
    if (!modelRef) {
      this._status = "Cannot determine model reference";
      this._statusTone = "error";
      this._render();
      return;
    }
    // Dispatch event for model editing
    window.dispatchEvent(new CustomEvent("ha-model-catalog-navigate", {
      detail: { action: "edit-metadata", model_ref: modelRef }
    }));
    this._status = "Opening model editor...";
    this._statusTone = "info";
    this._render();
  }

  _handleViewSimilarModels() {
    var archive = this._resolveArchive();
    if (!archive || !archive.linked_model) {
      this._status = "No linked model found";
      this._statusTone = "warning";
      this._render();
      return;
    }
    var modelRef = archive.linked_model.model_ref || archive.linked_model.model_id || "";
    if (!modelRef) {
      this._status = "Cannot determine model reference";
      this._statusTone = "error";
      this._render();
      return;
    }
    // Dispatch event for similar models view
    window.dispatchEvent(new CustomEvent("ha-model-catalog-navigate", {
      detail: { action: "view-similar-models", model_ref: modelRef }
    }));
    this._status = "Loading similar models...";
    this._statusTone = "info";
    this._render();
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