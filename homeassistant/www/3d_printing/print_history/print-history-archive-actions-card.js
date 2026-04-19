class PrintHistoryArchiveActionsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._archiveOverride = null;
    this._mode = "main";
    this._busy = false;
    this._status = "";
    this._statusTone = "info";
    this._boundClickHandler = this._handleClick.bind(this);
    this._boundChangeHandler = this._handleChange.bind(this);
  }

  setConfig(config) {
    this._config = {
      archive_json: config && config.archive_json ? config.archive_json : "{}",
      detail_entity: config && config.detail_entity ? config.detail_entity : "",
      api_base_entity: config && config.api_base_entity ? config.api_base_entity : "input_text.bambuddy_api_base_url",
      upload_endpoint:
        config && config.upload_endpoint
          ? config.upload_endpoint
          : "/api/bambuddy/print-history/archive/{archive_id}/source-3mf/upload",
    };
    this._archiveOverride = null;
    this._mode = "main";
    this._busy = false;
    this._status = "";
    this._statusTone = "info";
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  connectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.addEventListener("click", this._boundClickHandler);
      this.shadowRoot.addEventListener("change", this._boundChangeHandler);
    }
  }

  disconnectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.removeEventListener("click", this._boundClickHandler);
      this.shadowRoot.removeEventListener("change", this._boundChangeHandler);
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
    this._render();
  }

  _setStatus(message, tone) {
    this._status = String(message || "").trim();
    this._statusTone = tone === "error" ? "error" : tone === "success" ? "success" : "info";
    this._render();
  }

  _setBusy(busy, message, tone) {
    this._busy = !!busy;
    if (message != null) {
      this._setStatus(message, tone);
      return;
    }
    this._render();
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
      this._handleDownload();
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
    if (action === "repair-archive") {
      this._handleRepair();
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

  _handleChange(event) {
    var target = event.target;
    if (!target || !target.matches || !target.matches("input[data-source-upload-input='true']")) {
      return;
    }
    var files = target.files;
    var file = files && files.length ? files[0] : null;
    target.value = "";
    if (file) {
      this._uploadSource3mf(file);
    }
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
      this._setStatus(error && error.message ? error.message : "Could not open the archive in slicer", "error");
    }
  }

  async _handleDownload() {
    try {
      this._setBusy(true, "Preparing download...", "info");
      var response = await this._requestArchiveAction("download");
      var downloadUrl = response && response.download_url ? String(response.download_url) : "";
      if (!downloadUrl) {
        throw new Error("No download URL was returned for this archive");
      }
      this._openWindow(downloadUrl, "_blank");
      this._busy = false;
      this._setStatus("Download started.", "success");
    } catch (error) {
      this._busy = false;
      this._setStatus(error && error.message ? error.message : "Could not start the download", "error");
    }
  }

  _makerWorldUrl(archive) {
    var directUrl = String((archive && archive.makerworld_url) || "").trim();
    if (directUrl) {
      return directUrl;
    }
    var designer = String((archive && archive.designer) || "").trim().replace(/^@+/, "");
    if (designer) {
      return "https://makerworld.com/en/@" + encodeURIComponent(designer);
    }
    return "";
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
    if (this._busy || !this.shadowRoot) {
      return;
    }
    var input = this.shadowRoot.querySelector("input[data-source-upload-input='true']");
    if (!input) {
      return;
    }
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
      var formData = new FormData();
      formData.append("file", file, file.name);
      var headers = {};
      var accessToken = this._hass && this._hass.auth && this._hass.auth.data ? this._hass.auth.data.accessToken : "";
      if (accessToken) {
        headers.Authorization = "Bearer " + accessToken;
      }
      var uploadEndpoint = String(this._config.upload_endpoint || "").replace("{archive_id}", encodeURIComponent(String(archiveId)));
      var response = await fetch(uploadEndpoint, {
        method: "POST",
        body: formData,
        headers: headers,
        credentials: "same-origin",
      });
      var payload = await response.json().catch(function () {
        return {};
      });
      if (!response.ok || payload.success === false) {
        throw new Error(payload && payload.message ? payload.message : "Source 3MF upload failed");
      }
      var nextArchive = payload && payload.archive && typeof payload.archive === "object"
        ? payload.archive
        : payload;
      this._busy = false;
      this._setArchive(nextArchive);
      this._setStatus("Source 3MF uploaded.", "success");
    } catch (error) {
      this._busy = false;
      this._setStatus(error && error.message ? error.message : "Source 3MF upload failed", "error");
    }
  }

  async _handleRepair() {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    var archiveName = archive && archive.print_name ? String(archive.print_name) : "Archive";
    if (!this._hass || typeof this._hass.callService !== "function" || archiveId <= 0) {
      return;
    }
    await this._hass.callService("browser_mod", "sequence", {
      sequence: [
        { service: "browser_mod.close_popup" },
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
              workflow_entity: "sensor.print_history_popup_restore_workflow",
              detail_entity: "sensor.print_history_popup_archive_detail",
              source_archive_helper: "input_text.print_history_restore_source_archive_id",
              target_archive_helper: "input_text.print_history_restore_target_archive_id",
              upload_session_helper: "input_text.print_history_restore_upload_session_id",
            },
          },
        },
      ],
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
      this._setStatus(error && error.message ? error.message : "Archive delete failed", "error");
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

  _renderSummary(archive) {
    var previewImage = this._resolveArchivePreviewImage(archive);
    var archiveId = archive && archive.id != null ? Number(archive.id) : 0;
    var archiveName = archive && archive.print_name ? String(archive.print_name) : "Untitled Archive";
    var sourceName = String((archive && archive.source_3mf_path) || "").trim();
    var sourceBadge = sourceName
      ? '<div class="summary-note">Source 3MF attached: ' + this._escapeHtml(sourceName.split(/[\\/]/).pop()) + "</div>"
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
      '</div>' +
      '</div>' +
      '</section>';
  }

  _renderStatus() {
    if (!this._status) {
      return "";
    }
    return '<div class="status ' + this._escapeHtml(this._statusTone) + '">' + this._escapeHtml(this._status) + '</div>';
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

  _renderMain(archive) {
    var hasModel = !!(archive && (archive.file_path || archive.source_3mf_path));
    var makerworldUrl = this._makerWorldUrl(archive);
    var hasSource = !!String((archive && archive.source_3mf_path) || "").trim();
    var makerworldLabel = String((archive && archive.makerworld_url) || "").trim() ? "View on MakerWorld" : "View Designer";
    return '<div class="actions-grid">' +
      this._renderActionButton("open-in-slicer", "Open in Slicer", "mdi:vector-polyline", { disabled: !hasModel || this._busy }) +
      this._renderActionButton("download-model", hasSource && !archive.file_path ? "Download Source 3MF" : "Download 3MF", "mdi:download", { disabled: !hasModel || this._busy }) +
      this._renderActionButton("open-makerworld", makerworldLabel, "mdi:earth", { disabled: !makerworldUrl || this._busy }) +
      this._renderActionButton("upload-source-3mf", hasSource ? "Replace Source 3MF" : "Upload Source 3MF", "mdi:upload", { disabled: this._busy }) +
      this._renderActionButton("repair-archive", "Repair Archive", "mdi:wrench-cog", { tone: "warning", disabled: this._busy }) +
      this._renderActionButton("delete-archive", "Delete Archive", "mdi:delete-outline", { tone: "danger", wide: true, disabled: this._busy }) +
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
      '.status.info{background:rgba(33,150,243,0.10);color:var(--primary-text-color);}' +
      '.status.success{background:rgba(46,125,50,0.14);color:var(--primary-text-color);}' +
      '.status.error{background:rgba(183,28,28,0.14);color:var(--primary-text-color);}' +
      '.actions-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;}' +
      '.action-button{display:flex;align-items:center;justify-content:flex-start;gap:10px;width:100%;min-height:48px;padding:12px 14px;border-radius:16px;border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.04);color:var(--primary-text-color);font:inherit;font-size:14px;font-weight:700;text-align:left;cursor:pointer;transition:background 120ms ease,border-color 120ms ease,transform 120ms ease;}' +
      '.action-button:hover:not(:disabled){background:rgba(255,255,255,0.08);border-color:rgba(255,255,255,0.14);transform:translateY(-1px);}' +
      '.action-button:disabled{opacity:0.45;cursor:default;transform:none;}' +
      '.action-button ha-icon{--mdc-icon-size:20px;flex:0 0 auto;}' +
      '.action-button.warning{background:rgba(239,108,0,0.14);border-color:rgba(255,167,38,0.22);}' +
      '.action-button.danger{background:rgba(183,28,28,0.14);border-color:rgba(239,68,68,0.24);}' +
      '.action-button.wide{grid-column:1 / -1;}' +
      '.confirm-copy{padding:4px 2px 2px;font-size:14px;line-height:1.55;color:var(--primary-text-color);}' +
      '.confirm-grid{grid-template-columns:1fr;}' +
      '.visually-hidden{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important;}' +
      '@media (max-width: 520px){.summary-grid{grid-template-columns:1fr;}.summary-preview{width:100%;height:140px;}.actions-grid{grid-template-columns:1fr;}}' +
      '</style>' +
      '<div class="shell">' +
      this._renderSummary(archive) +
      this._renderStatus() +
      (confirmDelete ? this._renderDeleteConfirm(archive, this._mode === "confirm-delete-2") : this._renderMain(archive)) +
      '<input class="visually-hidden" type="file" accept=".3mf,application/vnd.ms-package.3dmanufacturing-3dmodel+xml" data-source-upload-input="true">' +
      '</div>';
  }
}

customElements.define("print-history-archive-actions-card", PrintHistoryArchiveActionsCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "print-history-archive-actions-card",
  name: "Print History Archive Actions Card",
  description: "Advanced print-history archive actions for slicer, MakerWorld, download, source upload, repair, and delete.",
});