class PrintHistoryPhotoGalleryCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._activeIndex = 0;
    this._expanded = false;
    this._images = [];
    this._archiveName = "Archive Photos";
    this._archiveId = "";
    this._archiveIdentity = "";
    this._localArchiveOverride = null;
    this._localPrimaryPhotoPath = null;
    this._localSelectedPrimaryPhotoPath = null;
    this._localHasPrimaryPhotoOverride = null;
    this._uploadInProgress = false;
    this._uploadStatus = "";
    this._uploadStatusTone = "info";
    this._preloadedSources = {};
    this._lastRenderSignature = "";
    this._overlayRoot = null;
    this._previousBodyOverflow = null;
    this._boundKeydownHandler = this._handleKeydown.bind(this);
    this._boundClickHandler = this._handleHostClick.bind(this);
    this._boundShadowClickHandler = this._handleShadowClick.bind(this);
    this._boundShadowChangeHandler = this._handleShadowChange.bind(this);
    this._boundOverlayClickHandler = this._handleOverlayClick.bind(this);
    this._boundOverlayHostClickHandler = this._handleOverlayHostClick.bind(this);
    this._boundOverlayCancelHandler = this._handleOverlayCancel.bind(this);
  }

  setConfig(config) {
    this._config = {
      archive_json: config && config.archive_json ? config.archive_json : "{}",
      archive_entity: config && config.archive_entity ? config.archive_entity : "",
      detail_entity: config && config.detail_entity ? config.detail_entity : "",
      api_base_entity: config && config.api_base_entity ? config.api_base_entity : "input_text.bambuddy_api_base_url",
      visibility_entity: config && config.visibility_entity ? config.visibility_entity : "",
      title: config && config.title ? config.title : "Archive Photos",
      include_thumbnail: !config || config.include_thumbnail !== false,
      compact: !!(config && config.compact),
    };
    this._archiveId = "";
    this._archiveIdentity = "";
    this._localArchiveOverride = null;
    this._localPrimaryPhotoPath = null;
    this._localSelectedPrimaryPhotoPath = null;
    this._localHasPrimaryPhotoOverride = null;
    this._activeIndex = 0;
    this._expanded = false;
    this._render();
  }

  set hass(hass) {
    var nextSignature = this._computeRenderSignature(hass);
    this._hass = hass;
    if (nextSignature === this._lastRenderSignature) {
      return;
    }
    this._lastRenderSignature = nextSignature;
    this._render();
  }

  connectedCallback() {
    window.addEventListener("keydown", this._boundKeydownHandler);
    this.addEventListener("click", this._boundClickHandler);
    if (this.shadowRoot) {
      this.shadowRoot.addEventListener("click", this._boundShadowClickHandler);
      this.shadowRoot.addEventListener("change", this._boundShadowChangeHandler);
    }
  }

  disconnectedCallback() {
    window.removeEventListener("keydown", this._boundKeydownHandler);
    this.removeEventListener("click", this._boundClickHandler);
    if (this.shadowRoot) {
      this.shadowRoot.removeEventListener("click", this._boundShadowClickHandler);
      this.shadowRoot.removeEventListener("change", this._boundShadowChangeHandler);
    }
    this._destroyOverlayRoot();
  }

  getCardSize() {
    return 4;
  }

  _handleKeydown(event) {
    if (!this._expanded) {
      return;
    }
    if (event.key === "Escape") {
      event.stopPropagation();
      this._setExpanded(false);
      return;
    }
    if (event.key === "ArrowLeft") {
      event.stopPropagation();
      this._moveActiveIndex(-1);
      return;
    }
    if (event.key === "ArrowRight") {
      event.stopPropagation();
      this._moveActiveIndex(1);
    }
  }

  _handleHostClick(event) {
    event.stopPropagation();
  }

  _handleShadowClick(event) {
    var target = event.target;
    if (!target || !target.closest) {
      return;
    }

    var indexButton = target.closest("[data-index]");
    if (indexButton) {
      event.stopPropagation();
      var index = Number(indexButton.getAttribute("data-index"));
      if (Number.isFinite(index)) {
        this._setActiveIndex(index);
      }
      return;
    }

    var actionButton = target.closest("[data-action]");
    if (!actionButton) {
      return;
    }

    event.stopPropagation();
    var action = actionButton.getAttribute("data-action");
    if (action === "prev") {
      this._moveActiveIndex(-1);
      return;
    }
    if (action === "next") {
      this._moveActiveIndex(1);
      return;
    }
    if (action === "viewer") {
      this._openViewerPopup();
      return;
    }
    if (action === "expand") {
      this._setExpanded(true);
      return;
    }
    if (action === "upload-photo") {
      this._openUploadPicker();
      return;
    }
    if (action === "collapse") {
      this._setExpanded(false);
      return;
    }
    if (action === "set-primary-photo") {
      this._applyPrimaryPhotoSelection(this._activePhotoPath());
      return;
    }
    if (action === "clear-primary-photo") {
      this._applyPrimaryPhotoSelection("");
      return;
    }
    if (action === "delete-photo") {
      this._deleteActivePhoto();
    }
  }

  _handleOverlayClick(event) {
    event.stopPropagation();

    var target = event.target;
    if (!target || !target.closest) {
      return;
    }

    var indexButton = target.closest("[data-index]");
    if (indexButton) {
      event.stopPropagation();
      var index = Number(indexButton.getAttribute("data-index"));
      if (Number.isFinite(index)) {
        this._setActiveIndex(index);
      }
      return;
    }

    var actionButton = target.closest("[data-action]");
    if (!actionButton) {
      return;
    }

    event.stopPropagation();
    var action = actionButton.getAttribute("data-action");
    if (action === "prev") {
      this._moveActiveIndex(-1);
      return;
    }
    if (action === "next") {
      this._moveActiveIndex(1);
      return;
    }
    if (action === "upload-photo") {
      this._openUploadPicker();
      return;
    }
    if (action === "collapse") {
      this._setExpanded(false);
      return;
    }
    if (action === "set-primary-photo") {
      this._applyPrimaryPhotoSelection(this._activePhotoPath());
      return;
    }
    if (action === "clear-primary-photo") {
      this._applyPrimaryPhotoSelection("");
      return;
    }
    if (action === "delete-photo") {
      this._deleteActivePhoto();
    }
  }

  _handleShadowChange(event) {
    var target = event.target;
    if (!target || target.getAttribute("data-upload-input") !== "true") {
      return;
    }
    var files = Array.prototype.slice.call(target.files || []);
    target.value = "";
    this._uploadSelectedFiles(files);
  }

  _handleOverlayHostClick(event) {
    event.stopPropagation();
    if (event.target === this._overlayRoot) {
      this._setExpanded(false);
    }
  }

  _handleOverlayCancel(event) {
    event.preventDefault();
    event.stopPropagation();
    this._setExpanded(false);
  }

  _parseArchive() {
    if (!this._config) {
      return {};
    }
    if (typeof this._config.archive_json === "string") {
      try {
        return JSON.parse(this._config.archive_json || "{}");
      } catch (_error) {
        return {};
      }
    }
    if (this._config.archive_json && typeof this._config.archive_json === "object") {
      return this._config.archive_json;
    }
    return {};
  }

  _resolveArchive() {
    var snapshotArchive = this._parseArchive();
    var archiveId = snapshotArchive && snapshotArchive.id != null ? snapshotArchive.id : null;

    if (archiveId == null) {
      return snapshotArchive;
    }

    return this._mergeDetailArchive(snapshotArchive, archiveId);
  }

  _mergeDetailArchive(archive, archiveId) {
    var detail = this._getDetailArchive(archiveId);
    if (!detail) {
      return archive;
    }

    var merged = Object.assign({}, archive || {}, detail || {});
    var detailPhotos = Array.isArray(detail.photos) ? detail.photos : [];
    var archivePhotos = Array.isArray(archive && archive.photos) ? archive.photos : [];

    if (detailPhotos.length) {
      merged.photos = detailPhotos;
    } else if (archivePhotos.length) {
      merged.photos = archivePhotos;
    }

    if (!merged.thumbnail_path && archive && archive.thumbnail_path) {
      merged.thumbnail_path = archive.thumbnail_path;
    }

    if (this._localArchiveOverride && typeof this._localArchiveOverride === "object") {
      merged = Object.assign({}, merged, this._localArchiveOverride);
    }

    if (this._localPrimaryPhotoPath !== null) {
      merged.primary_photo_path = this._localPrimaryPhotoPath;
    }

    if (this._localSelectedPrimaryPhotoPath !== null) {
      merged.selected_primary_photo_path = this._localSelectedPrimaryPhotoPath;
    }

    if (this._localHasPrimaryPhotoOverride !== null) {
      merged.has_primary_photo_override = this._localHasPrimaryPhotoOverride;
    }

    return merged;
  }

  _activePhotoPath() {
    var active = this._images && this._images.length ? this._images[this._activeIndex] : null;
    if (!active || active.kind !== "photo") {
      return "";
    }
    return String(active.filename || "").trim();
  }

  _normalizePhotoList(photoValues) {
    var seen = {};
    return (Array.isArray(photoValues) ? photoValues : []).reduce(function (photos, value) {
      var photoPath = String(value || "").trim();
      if (!photoPath || seen[photoPath]) {
        return photos;
      }
      seen[photoPath] = true;
      photos.push(photoPath);
      return photos;
    }, []);
  }

  _buildLocalArchiveState(updatedArchive, options) {
    var currentArchive = this._resolveArchive();
    var nextArchive = Object.assign({}, currentArchive || {});
    var normalizedOptions = options && typeof options === "object" ? options : {};
    var removedPhotoPath = String(normalizedOptions.removePhotoPath || "").trim();
    var appendedPhotoPaths = this._normalizePhotoList(normalizedOptions.appendPhotoPaths);

    if (updatedArchive && typeof updatedArchive === "object") {
      nextArchive = Object.assign(nextArchive, updatedArchive);
    }

    var photos = Array.isArray(updatedArchive && updatedArchive.photos)
      ? updatedArchive.photos
      : Array.isArray(nextArchive.photos)
        ? nextArchive.photos
        : [];
    photos = this._normalizePhotoList(photos);

    if (removedPhotoPath) {
      photos = photos.filter(function (photoPath) {
        return photoPath !== removedPhotoPath;
      });
      if (String(nextArchive.primary_photo_path || "").trim() === removedPhotoPath) {
        nextArchive.primary_photo_path = "";
      }
      if (String(nextArchive.selected_primary_photo_path || "").trim() === removedPhotoPath) {
        nextArchive.selected_primary_photo_path = "";
        if (nextArchive.has_primary_photo_override == null) {
          nextArchive.has_primary_photo_override = false;
        }
      }
    }

    if (appendedPhotoPaths.length) {
      photos = this._normalizePhotoList(photos.concat(appendedPhotoPaths));
    }

    nextArchive.photos = photos;
    return nextArchive;
  }

  _applyLocalArchiveState(updatedArchive, options) {
    var nextArchive = this._buildLocalArchiveState(updatedArchive, options);
    this._localArchiveOverride = nextArchive;
    this._localPrimaryPhotoPath = nextArchive.primary_photo_path != null
      ? String(nextArchive.primary_photo_path || "").trim()
      : this._localPrimaryPhotoPath;
    this._localSelectedPrimaryPhotoPath = nextArchive.selected_primary_photo_path != null
      ? String(nextArchive.selected_primary_photo_path || "").trim()
      : this._localSelectedPrimaryPhotoPath;
    this._localHasPrimaryPhotoOverride = nextArchive.has_primary_photo_override != null
      ? !!nextArchive.has_primary_photo_override
      : this._localHasPrimaryPhotoOverride;
    return nextArchive;
  }

  async _applyPrimaryPhotoSelection(photoPath) {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? archive.id : null;
    if (!this._hass || archiveId == null) {
      return;
    }

    var normalizedPhotoPath = String(photoPath || "").trim();
    try {
      var responseEnvelope = await this._hass.callService(
        "bambuddy",
        "set_print_history_primary_photo",
        {
          archive_id: archiveId,
          photo_path: normalizedPhotoPath,
        },
        undefined,
        true,
        true
      );
      var response = responseEnvelope && responseEnvelope.response && typeof responseEnvelope.response === "object"
        ? responseEnvelope.response
        : responseEnvelope;
      var updatedArchive = response && response.archive && typeof response.archive === "object"
        ? response.archive
        : null;
      var selection = response && response.primary_photo_selection && typeof response.primary_photo_selection === "object"
        ? response.primary_photo_selection
        : null;
      var nextArchive = this._applyLocalArchiveState(updatedArchive);
      this._localPrimaryPhotoPath = normalizedPhotoPath;
      this._localSelectedPrimaryPhotoPath = normalizedPhotoPath;
      this._localHasPrimaryPhotoOverride = true;
      if (nextArchive.primary_photo_path != null) {
        this._localPrimaryPhotoPath = String(nextArchive.primary_photo_path || "").trim();
      }
      if (nextArchive.selected_primary_photo_path != null) {
        this._localSelectedPrimaryPhotoPath = String(nextArchive.selected_primary_photo_path || "").trim();
      }
      if (nextArchive.has_primary_photo_override != null) {
        this._localHasPrimaryPhotoOverride = !!nextArchive.has_primary_photo_override;
      }
      if (selection && selection.photo_path != null) {
        this._localSelectedPrimaryPhotoPath = String(selection.photo_path || "").trim();
      }
      if (selection && selection.cleared) {
        this._localPrimaryPhotoPath = "";
        this._localSelectedPrimaryPhotoPath = "";
        this._localHasPrimaryPhotoOverride = false;
      }
      this._render();
    } catch (error) {
      // eslint-disable-next-line no-console
      console.warn("Failed to update Bambuddy primary photo", error);
    }
  }

  async _deleteActivePhoto() {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? archive.id : null;
    var photoPath = this._activePhotoPath();
    if (!this._hass || archiveId == null || !photoPath || this._uploadInProgress) {
      return;
    }

    if (!window.confirm("Delete this photo from the archive? This cannot be undone.")) {
      return;
    }

    this._setUploadStatus("Deleting photo...", "info", true);
    try {
      var responseEnvelope = await this._hass.callService(
        "bambuddy",
        "delete_print_history_photo",
        {
          archive_id: archiveId,
          photo_path: photoPath,
        },
        undefined,
        true,
        true
      );
      var response = responseEnvelope && responseEnvelope.response && typeof responseEnvelope.response === "object"
        ? responseEnvelope.response
        : responseEnvelope;
      var updatedArchive = response && response.archive && typeof response.archive === "object"
        ? response.archive
        : null;
      var nextArchive = this._applyLocalArchiveState(updatedArchive, { removePhotoPath: photoPath });
      var images = this._buildImages(nextArchive);
      this._activeIndex = Math.max(0, Math.min(this._activeIndex, images.length - 1));
      this._setUploadStatus("Photo deleted.", "success", false);
    } catch (error) {
      var message = error && error.message ? error.message : "Photo delete failed";
      this._setUploadStatus(message, "error", false);
    }
  }

  _setUploadStatus(message, tone, inProgress) {
    this._uploadStatus = String(message || "").trim();
    this._uploadStatusTone = tone === "error" ? "error" : tone === "success" ? "success" : "info";
    this._uploadInProgress = !!inProgress;
    this._render();
  }

  _openUploadPicker() {
    if (this._uploadInProgress || !this.shadowRoot) {
      return;
    }
    var input = this.shadowRoot.querySelector("input[data-upload-input='true']");
    if (input) {
      try {
        if (typeof input.showPicker === "function") {
          input.showPicker();
          return;
        }
      } catch (_error) {
        // Fall back to click() for browsers without showPicker support.
      }
      input.click();
    }
  }

  async _uploadSelectedFiles(fileList) {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? archive.id : null;
    if (!this._hass || typeof this._hass.callWS !== "function" || archiveId == null) {
      return;
    }

    var files = Array.prototype.slice.call(fileList || []).filter(function (file) {
      return !!(file && (String(file.type || "").indexOf("image/") === 0 || /\.(jpe?g|png|webp)$/i.test(String(file.name || ""))));
    });
    if (!files.length) {
      return;
    }

    var uploadedCount = 0;
    try {
      this._setUploadStatus("Preparing " + String(files.length) + (files.length === 1 ? " photo..." : " photos..."), "info", true);
      for (var index = 0; index < files.length; index += 1) {
        var file = files[index];
        var prepared = await this._prepareUploadPayload(file, archiveId, index);
        this._setUploadStatus(
          "Uploading " + String(index + 1) + " of " + String(files.length) + "...",
          "info",
          true
        );
        var response = await this._hass.callWS({
          type: "bambuddy/print_history_upload_photo",
          archive_id: archiveId,
          file_name: prepared.fileName,
          mime_type: prepared.mimeType,
          content_base64: prepared.contentBase64,
        });
        var updatedArchive = response && response.archive && typeof response.archive === "object"
          ? response.archive
          : null;
        var nextArchive = this._applyLocalArchiveState(updatedArchive, { appendPhotoPaths: [prepared.fileName] });
        var photoCount = Array.isArray(nextArchive.photos) ? nextArchive.photos.length : 0;
        if (photoCount > 0) {
          this._activeIndex = photoCount - 1 + (this._config && this._config.include_thumbnail ? 1 : 0);
        }
        uploadedCount += 1;
      }
      this._setUploadStatus(
        uploadedCount === 1 ? "Added 1 photo." : "Added " + String(uploadedCount) + " photos.",
        "success",
        false
      );
    } catch (error) {
      var message = error && error.message ? error.message : "Photo upload failed";
      this._setUploadStatus(message, "error", false);
    }
  }

  async _prepareUploadPayload(file, archiveId, index) {
    var image = await this._loadImageFromFile(file);
    try {
      var dimensions = this._scaledDimensions(image.width, image.height, 2048);
      var canvas = document.createElement("canvas");
      canvas.width = dimensions.width;
      canvas.height = dimensions.height;
      var context = canvas.getContext("2d");
      if (!context) {
        throw new Error("Canvas rendering is unavailable for upload") ;
      }
      context.drawImage(image, 0, 0, dimensions.width, dimensions.height);
      var blob = await this._canvasToBlob(canvas, "image/jpeg", 0.86);
      if (!blob) {
        throw new Error("Could not encode photo for upload");
      }
      return {
        fileName: this._buildUploadFileName(file && file.name, archiveId, index),
        mimeType: "image/jpeg",
        contentBase64: await this._blobToBase64(blob),
      };
    } finally {
      if (image && image.src && image.src.indexOf("blob:") === 0) {
        URL.revokeObjectURL(image.src);
      }
    }
  }

  _scaledDimensions(width, height, maxDimension) {
    var safeWidth = Math.max(1, Number(width) || 1);
    var safeHeight = Math.max(1, Number(height) || 1);
    var scale = Math.min(1, maxDimension / Math.max(safeWidth, safeHeight));
    return {
      width: Math.max(1, Math.round(safeWidth * scale)),
      height: Math.max(1, Math.round(safeHeight * scale)),
    };
  }

  _loadImageFromFile(file) {
    return new Promise(function (resolve, reject) {
      var objectUrl = URL.createObjectURL(file);
      var image = new Image();
      image.onload = function () {
        resolve(image);
      };
      image.onerror = function () {
        URL.revokeObjectURL(objectUrl);
        reject(new Error("Selected file is not a readable image"));
      };
      image.src = objectUrl;
    });
  }

  _canvasToBlob(canvas, mimeType, quality) {
    return new Promise(function (resolve, reject) {
      canvas.toBlob(function (blob) {
        if (!blob) {
          reject(new Error("Canvas export returned no data"));
          return;
        }
        resolve(blob);
      }, mimeType, quality);
    });
  }

  _blobToBase64(blob) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        var result = String(reader.result || "");
        var commaIndex = result.indexOf(",");
        resolve(commaIndex >= 0 ? result.slice(commaIndex + 1) : result);
      };
      reader.onerror = function () {
        reject(new Error("Could not read the encoded photo"));
      };
      reader.readAsDataURL(blob);
    });
  }

  _buildUploadFileName(originalName, archiveId, index) {
    var baseName = String(originalName || "manual-photo")
      .replace(/\.[^.]+$/, "")
      .replace(/[^a-z0-9]+/gi, "-")
      .replace(/^-+|-+$/g, "")
      .toLowerCase();
    if (!baseName) {
      baseName = "manual-photo";
    }
    var timestamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "z");
    return "archive-" + String(archiveId) + "-" + baseName + "-" + timestamp + "-" + String(index + 1) + ".jpg";
  }

  _resolvedEntryId() {
    var state = this._hass && this._hass.states ? this._hass.states["sensor.bambuddy_print_history_browser_status"] : null;
    return state && state.attributes && state.attributes.entry_id
      ? String(state.attributes.entry_id).trim()
      : "";
  }

  _buildArchiveViewerCardConfig(archive) {
    return {
      type: "custom:print-history-3d-viewer-card",
      archive_id: archive && archive.id != null ? String(archive.id) : "",
      archive_name: archive && archive.print_name ? String(archive.print_name) : "",
      archive_json: archive ? JSON.stringify(archive) : "{}",
      entry_id: this._resolvedEntryId(),
    };
  }

  _buildArchiveViewerPopupContent(archive) {
    return {
      type: "vertical-stack",
      cards: [this._buildArchiveViewerCardConfig(archive)],
    };
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

  _openViewerPopup() {
    var archive = this._resolveArchive();
    if (!archive || archive.id == null) {
      return;
    }
    this._fireBrowserModEvent("browser_mod.popup", {
      title: "3D Viewer",
      size: "wide",
      content: this._buildArchiveViewerPopupContent(archive),
    });
  }

  _buildUploadAction(buttonClass) {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? archive.id : null;
    if (archiveId == null) {
      return "";
    }
    var className = buttonClass || "action-button";
    var label = this._uploadInProgress ? "Uploading..." : "Add Photo";
    return this._buildActionButtonHtml({
      className: className,
      action: "upload-photo",
      disabled: this._uploadInProgress,
      icon: this._uploadInProgress ? "mdi:loading" : "mdi:plus",
      label: label,
      title: label,
    });
  }

  _buildViewerAction(buttonClass) {
    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? archive.id : null;
    if (archiveId == null) {
      return "";
    }
    var className = buttonClass || "icon-action viewer";
    var archiveName = archive && archive.print_name ? String(archive.print_name) : "archive";
    return '<button class="' + className + '" type="button" data-action="viewer" aria-label="Open 3D viewer for ' + this._escapeHtml(archiveName) + '" title="Open 3D Viewer"><ha-icon icon="mdi:cube-scan"></ha-icon></button>';
  }

  _buildExpandAction(buttonClass) {
    var archive = this._resolveArchive();
    var archiveName = archive && archive.print_name ? String(archive.print_name) : "archive";
    var className = buttonClass || "icon-action expand";
    return '<button class="' + className + '" type="button" data-action="expand" aria-label="Open full screen gallery for ' + this._escapeHtml(archiveName) + '" title="Open Full Screen"><ha-icon icon="mdi:fullscreen"></ha-icon></button>';
  }

  _renderUploadStatus() {
    if (!this._uploadStatus) {
      return "";
    }
    return '<div class="upload-status ' + this._escapeHtml(this._uploadStatusTone) + '">' + this._escapeHtml(this._uploadStatus) + '</div>';
  }

  _getDetailArchive(archiveId) {
    var entityId = this._config ? this._config.detail_entity : "";
    if (!entityId || !this._hass || !this._hass.states || !this._hass.states[entityId]) {
      return null;
    }

    var detailState = this._hass.states[entityId];
    if (String(detailState.state || "") !== String(archiveId)) {
      return null;
    }

    var raw = detailState.attributes ? detailState.attributes.archive_json : null;
    if (!raw) {
      return null;
    }

    try {
      var detail = typeof raw === "string" ? JSON.parse(raw || "{}") : raw;
      if (!detail || typeof detail !== "object") {
        return null;
      }
      if (detail.id != null && String(detail.id) !== String(archiveId)) {
        return null;
      }
      return detail;
    } catch (_error) {
      return null;
    }
  }

  _getBaseUrl() {
    var entityId = this._config ? this._config.api_base_entity : "input_text.bambuddy_api_base_url";
    var raw = this._hass && this._hass.states && this._hass.states[entityId]
      ? this._hass.states[entityId].state
      : "";
    return String(raw || "").replace(/\/$/, "");
  }

  _computeRenderSignature(hass) {
    if (!this._config || !hass || !hass.states) {
      return "";
    }

    var parts = [
      typeof this._config.archive_json === "string"
        ? this._config.archive_json
        : JSON.stringify(this._config.archive_json || {}),
    ];

    var detailEntityId = this._config.detail_entity || "";
    var detailState = detailEntityId ? hass.states[detailEntityId] : null;
    parts.push(detailState ? String(detailState.last_updated || detailState.last_changed || "") : "");
    parts.push(detailState ? String(detailState.state || "") : "");

    var baseEntityId = this._config.api_base_entity || "input_text.bambuddy_api_base_url";
    var baseState = hass.states[baseEntityId];
    parts.push(baseState ? String(baseState.state || "") : "");
    parts.push(baseState ? String(baseState.last_updated || baseState.last_changed || "") : "");

    var visibilityEntityId = this._config.visibility_entity || "";
    var visibilityState = visibilityEntityId ? hass.states[visibilityEntityId] : null;
    parts.push(visibilityState ? String(visibilityState.state || "") : "");
    parts.push(visibilityState ? String(visibilityState.last_updated || visibilityState.last_changed || "") : "");

    return parts.join("|");
  }

  _isVisible() {
    var entityId = this._config ? this._config.visibility_entity : "";
    if (!entityId) {
      return true;
    }
    var state = this._hass && this._hass.states && this._hass.states[entityId]
      ? this._hass.states[entityId].state
      : "on";
    return state !== "off";
  }

  _buildImages(archive) {
    var baseUrl = this._getBaseUrl();
    var archiveId = archive && archive.id != null ? archive.id : null;
    var primaryPhotoPath = String(archive && archive.primary_photo_path || "").trim();
    var hasPrimaryOverride = archive && archive.has_primary_photo_override != null
      ? !!archive.has_primary_photo_override
      : !!String(archive && archive.selected_primary_photo_path || "").trim();
    var hasPhotoPrimary = !!primaryPhotoPath;
    var images = [];
    var seen = {};

    if (!baseUrl || archiveId == null) {
      return images;
    }

    if (this._config.include_thumbnail && archive && archive.thumbnail_path) {
      images.push({
        key: "thumbnail",
        label: "Thumbnail",
        src: this._withArchiveMediaCacheKey(
          baseUrl + "/api/v1/archives/" + encodeURIComponent(String(archiveId)) + "/thumbnail",
          archive
        ),
        kind: "thumbnail",
        isPrimary: !primaryPhotoPath,
        hasPrimaryOverride: hasPrimaryOverride,
        hasPhotoPrimary: hasPhotoPrimary,
      });
      seen.thumbnail = true;
    }

    var photos = Array.isArray(archive && archive.photos) ? archive.photos : [];
    photos.forEach(function (filename, index) {
      var value = String(filename || "").trim();
      if (!value || seen[value]) {
        return;
      }
      seen[value] = true;
      images.push({
        key: value,
        label: "Photo " + String(index + 1),
        src: this._withArchiveMediaCacheKey(
          baseUrl + "/api/v1/archives/" + encodeURIComponent(String(archiveId)) + "/photos/" + encodeURIComponent(value),
          archive
        ),
        kind: "photo",
        filename: value,
        isPrimary: value === primaryPhotoPath,
        hasPrimaryOverride: hasPrimaryOverride,
        hasPhotoPrimary: hasPhotoPrimary,
      });
    }.bind(this));

    return images;
  }

  _buildPrimaryAction(active, buttonClass) {
    if (!active) {
      return "";
    }

    var className = buttonClass || "action-button";
    if (active.kind === "photo" && !active.isPrimary) {
      return this._buildActionButtonHtml({
        className: className,
        action: "set-primary-photo",
        icon: "mdi:image-check-outline",
        label: "Set List Image",
        title: "Set List Image",
      });
    }

    if (active.hasPhotoPrimary) {
      return this._buildActionButtonHtml({
        className: className,
        action: "clear-primary-photo",
        icon: "mdi:image-off-outline",
        label: "Use Thumbnail",
        title: "Use Thumbnail",
      });
    }

    return "";
  }

  _buildDeleteAction(active, buttonClass) {
    if (!active || active.kind !== "photo") {
      return "";
    }
    var className = buttonClass || "action-button";
    return this._buildActionButtonHtml({
      className: className + " danger",
      action: "delete-photo",
      disabled: this._uploadInProgress,
      icon: "mdi:close-thick",
      label: "Delete Photo",
      title: "Delete Photo",
    });
  }

  _findPreferredActiveIndex(images) {
    if (!Array.isArray(images) || !images.length) {
      return 0;
    }

    var primaryIndex = images.findIndex(function (image) {
      return !!(image && image.isPrimary);
    });

    return primaryIndex >= 0 ? primaryIndex : 0;
  }

  _photoCount(images) {
    if (!Array.isArray(images) || !images.length) {
      return 0;
    }

    return images.reduce(function (count, image) {
      return count + (image && image.kind === "photo" ? 1 : 0);
    }, 0);
  }

  _subtitleForImages(images) {
    var photoCount = this._photoCount(images);
    return photoCount > 0
      ? photoCount + (photoCount === 1 ? " photo" : " photos")
      : "Thumbnail only";
  }

  _moveActiveIndex(direction) {
    var images = this._images;
    if (!images.length) {
      return;
    }
    var nextIndex = this._activeIndex + direction;
    if (nextIndex < 0) {
      nextIndex = images.length - 1;
    } else if (nextIndex >= images.length) {
      nextIndex = 0;
    }
    this._setActiveIndex(nextIndex);
  }

  _setActiveIndex(index) {
    if (!this._images.length) {
      return;
    }
    if (!Number.isFinite(index) || index < 0 || index >= this._images.length) {
      return;
    }
    if (index === this._activeIndex) {
      return;
    }
    this._activeIndex = index;
    this._syncActiveImage();
  }

  _setExpanded(expanded) {
    var nextExpanded = !!expanded;
    if (nextExpanded === this._expanded) {
      return;
    }
    this._expanded = nextExpanded;
    this._syncExpandedState();
  }

  _preloadImages(images) {
    images.forEach(function (image) {
      if (!image || !image.src || this._preloadedSources[image.src]) {
        return;
      }
      this._preloadedSources[image.src] = true;
      var preloadImage = new Image();
      preloadImage.decoding = "async";
      preloadImage.src = image.src;
    }, this);
  }

  _ensureOverlayRoot() {
    var doc = this.ownerDocument || document;
    if (this._overlayRoot || !doc || !doc.body) {
      return;
    }

    this._overlayRoot = doc.createElement("dialog");
    this._overlayRoot.setAttribute("aria-label", "Full-screen gallery");
    this._overlayRoot.style.padding = "0";
    this._overlayRoot.style.border = "none";
    this._overlayRoot.style.background = "transparent";
    this._overlayRoot.style.margin = "0";
    this._overlayRoot.style.width = "100vw";
    this._overlayRoot.style.maxWidth = "100vw";
    this._overlayRoot.style.height = "100vh";
    this._overlayRoot.style.maxHeight = "100vh";
    this._overlayRoot.style.overflow = "hidden";
    this._overlayRoot.addEventListener("click", this._boundOverlayClickHandler);
    this._overlayRoot.addEventListener("click", this._boundOverlayHostClickHandler);
    this._overlayRoot.addEventListener("cancel", this._boundOverlayCancelHandler);
    doc.body.appendChild(this._overlayRoot);
  }

  _destroyOverlayRoot() {
    this._restoreBodyScrollLock();
    if (!this._overlayRoot) {
      return;
    }
    this._overlayRoot.removeEventListener("click", this._boundOverlayClickHandler);
    this._overlayRoot.removeEventListener("click", this._boundOverlayHostClickHandler);
    this._overlayRoot.removeEventListener("cancel", this._boundOverlayCancelHandler);
    if (this._overlayRoot.parentNode) {
      this._overlayRoot.parentNode.removeChild(this._overlayRoot);
    }
    this._overlayRoot = null;
  }

  _applyBodyScrollLock() {
    var doc = this.ownerDocument || document;
    if (!doc || !doc.body || this._previousBodyOverflow !== null) {
      return;
    }
    this._previousBodyOverflow = doc.body.style.overflow || "";
    doc.body.style.overflow = "hidden";
  }

  _restoreBodyScrollLock() {
    var doc = this.ownerDocument || document;
    if (!doc || !doc.body || this._previousBodyOverflow === null) {
      return;
    }
    doc.body.style.overflow = this._previousBodyOverflow;
    this._previousBodyOverflow = null;
  }

  _renderOverlay() {
    this._ensureOverlayRoot();
    if (!this._overlayRoot || !this._images.length) {
      return;
    }

    if (this._activeIndex >= this._images.length) {
      this._activeIndex = 0;
    }

    var active = this._images[this._activeIndex];
    var subtitle = this._subtitleForImages(this._images);
    var primaryAction = this._buildPrimaryAction(active, "button");
    var deleteAction = this._buildDeleteAction(active, "button");
    var uploadAction = this._buildUploadAction("button");
    var uploadStatus = this._renderUploadStatus();

    this._overlayRoot.innerHTML =
      "<style>" +
      ".phg-frame,.phg-frame *{box-sizing:border-box;}" +
      ".frame{position:fixed;inset:0;}" +
      ".backdrop{appearance:none;border:none;position:absolute;inset:0;background:rgba(4,8,15,0.94);padding:0;cursor:pointer;}" +
      ".shell{position:relative;z-index:1;display:grid;grid-template-rows:auto minmax(0,1fr) auto;gap:16px;height:100%;box-sizing:border-box;padding:clamp(16px,2.2vw,28px);padding-top:max(clamp(16px,2.2vw,28px), env(safe-area-inset-top));padding-right:max(clamp(16px,2.2vw,28px), env(safe-area-inset-right));padding-bottom:max(clamp(16px,2.2vw,28px), env(safe-area-inset-bottom));padding-left:max(clamp(16px,2.2vw,28px), env(safe-area-inset-left));}" +
      ".header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;color:#fff;}" +
      ".title{font:700 clamp(18px,2.2vw,28px)/1.2 system-ui,sans-serif;letter-spacing:0.01em;}" +
      ".subtitle{margin-top:6px;font:500 clamp(13px,1.4vw,15px)/1.45 system-ui,sans-serif;color:rgba(255,255,255,0.76);}" +
      ".actions{display:flex;align-items:center;gap:10px;}" +
      ".actions .button[disabled]{opacity:0.6;cursor:wait;}" +
      ".button{appearance:none;border:none;border-radius:999px;padding:12px 16px;background:rgba(255,255,255,0.14);color:#fff;font:700 13px/1 system-ui,sans-serif;cursor:pointer;backdrop-filter:blur(10px);display:inline-flex;align-items:center;gap:8px;}" +
      ".button.danger{background:rgba(183,28,28,0.3);color:#ffcdd2;}" +
      ".button-icon{--mdc-icon-size:16px;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;}" +
      ".button-icon.spin{animation:phgSpin 1s linear infinite;}" +
      ".upload-status{padding:10px 12px;border-radius:14px;font:600 13px/1.4 system-ui,sans-serif;}" +
      ".upload-status.info{background:rgba(255,255,255,0.12);color:rgba(255,255,255,0.88);}" +
      ".upload-status.success{background:rgba(46,125,50,0.2);color:#dcedc8;}" +
      ".upload-status.error{background:rgba(183,28,28,0.24);color:#ffcdd2;}" +
      ".stage{position:relative;display:flex;align-items:center;justify-content:center;min-height:0;border-radius:24px;overflow:hidden;background:linear-gradient(180deg, rgba(15,23,42,0.82), rgba(2,6,23,0.98));box-shadow:0 24px 60px rgba(0,0,0,0.42);}" +
      ".image-wrap{display:flex;align-items:center;justify-content:center;width:100%;height:100%;min-height:0;padding:clamp(10px,1.6vw,22px);box-sizing:border-box;}" +
      ".image{display:block;width:100%;height:100%;max-width:100%;max-height:100%;object-fit:contain;border-radius:18px;background:rgba(15,23,42,0.32);}" +
      ".nav{appearance:none;border:none;position:absolute;top:50%;transform:translateY(-50%);width:56px;height:56px;border-radius:999px;background:rgba(255,255,255,0.14);color:#fff;font-size:30px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(12px);}" +
      ".nav.prev{left:16px;}" +
      ".nav.next{right:16px;}" +
      ".filmstrip{display:flex;gap:12px;overflow-x:auto;padding:2px 2px 6px;}" +
      ".thumb{appearance:none;border:2px solid transparent;background:none;padding:0;border-radius:16px;overflow:hidden;cursor:pointer;flex:0 0 auto;opacity:0.82;transition:opacity 120ms ease,border-color 120ms ease,transform 120ms ease;}" +
      ".thumb.active{border-color:#90caf9;opacity:1;transform:translateY(-1px);}" +
      ".thumb img{display:block;width:108px;height:108px;object-fit:cover;background:rgba(15,23,42,0.35);}" +
      "@keyframes phgSpin{0%{transform:rotate(0deg);}100%{transform:rotate(360deg);}}" +
      "dialog[aria-label='Full-screen gallery']::backdrop{background:transparent;}" +
      "@media (max-width: 900px){.shell{grid-template-rows:auto minmax(0,1fr) auto;gap:12px;}.thumb img{width:84px;height:84px;}.nav{width:48px;height:48px;font-size:26px;}}" +
      "@media (max-width: 640px){.header{gap:12px;}.title{font-size:18px;}.subtitle{font-size:13px;}.button{padding:10px 14px;}.stage{border-radius:20px;}.image-wrap{padding:10px;}.nav.prev{left:10px;}.nav.next{right:10px;}.thumb img{width:72px;height:72px;}}" +
      "</style>" +
      '<div class="frame phg-frame">' +
      '<button class="backdrop" type="button" data-action="collapse" aria-label="Close full-screen gallery"></button>' +
      '<div class="shell" role="dialog" aria-modal="true" aria-label="' + this._escapeHtml(this._archiveName) + '">' +
      '<div class="header">' +
      '<div><div class="title">' + this._escapeHtml(this._archiveName) + '</div><div class="subtitle">' + this._escapeHtml(active.label) + ' \u00b7 ' + this._escapeHtml(subtitle) + '</div></div>' +
      '<div class="actions">' + uploadAction + primaryAction + deleteAction + '<button class="button" type="button" data-action="collapse">Close</button></div>' +
      '</div>' +
      uploadStatus +
      '<div class="stage">' +
      '<div class="image-wrap"><img class="image" src="' + this._escapeHtml(active.src) + '" alt="' + this._escapeHtml(active.filename || active.label || this._archiveName) + '" loading="eager" decoding="async"></div>' +
      (this._images.length > 1 ? '<button class="nav prev" type="button" data-action="prev" aria-label="Previous image">&#8249;</button><button class="nav next" type="button" data-action="next" aria-label="Next image">&#8250;</button>' : "") +
      '</div>' +
      '<div class="filmstrip">' + this._images.map(function (image, index) {
        return '<button class="thumb' + (index === this._activeIndex ? ' active' : '') + '" type="button" data-index="' + this._escapeHtml(String(index)) + '" aria-label="' + this._escapeHtml(image.label) + '">' +
          '<img src="' + this._escapeHtml(image.src) + '" alt="' + this._escapeHtml(image.filename || image.label || this._archiveName) + '">' +
          '</button>';
      }.bind(this)).join("") + '</div>' +
      '</div>' +
      '</div>';
  }

  _syncActiveImage() {
    if (!this.shadowRoot || !this._images.length) {
      return;
    }

    if (this._activeIndex >= this._images.length) {
      this._activeIndex = 0;
    }

    var active = this._images[this._activeIndex];
    var alt = this._escapeHtml(active.filename || active.label || this._archiveName);
    var viewerAction = this._buildViewerAction("icon-action viewer");
    var expandAction = this._buildExpandAction("icon-action expand");

    var stageImage = this.shadowRoot.querySelector(".stage-image");
    if (stageImage) {
      stageImage.src = active.src;
      stageImage.alt = alt;
      stageImage.loading = "eager";
      stageImage.decoding = "async";
    }

    var stageBadge = this.shadowRoot.querySelector(".stage-badge");
    if (stageBadge) {
      stageBadge.textContent = active.label;
    }

    var topbarActions = this.shadowRoot.querySelector(".topbar-actions");
    if (topbarActions) {
      topbarActions.innerHTML = viewerAction + expandAction;
    }

    Array.from(this.shadowRoot.querySelectorAll(".thumb"))
      .forEach(function (button) {
        var buttonIndex = Number(button.getAttribute("data-index"));
        button.classList.toggle("active", buttonIndex === this._activeIndex);
      }, this);

    var primaryAction = this._buildPrimaryAction(active, "action-button");
    var deleteAction = this._buildDeleteAction(active, "action-button");
    var uploadAction = this._buildUploadAction("action-button");

    var metaActions = this.shadowRoot.querySelector(".meta-actions");
    if (metaActions) {
      metaActions.innerHTML = uploadAction + primaryAction + deleteAction;
    }

    var uploadStatus = this.shadowRoot.querySelector(".upload-status-host");
    if (uploadStatus) {
      uploadStatus.innerHTML = this._renderUploadStatus();
    }

    if (this._expanded) {
      this._renderOverlay();
    }
  }

  _syncExpandedState() {
    if (this._expanded) {
      this._applyBodyScrollLock();
      this._renderOverlay();
      if (this._overlayRoot && !this._overlayRoot.open) {
        this._overlayRoot.showModal();
      }
      return;
    }

    this._restoreBodyScrollLock();
    if (this._overlayRoot) {
      if (this._overlayRoot.open) {
        this._overlayRoot.close();
      }
      this._overlayRoot.innerHTML = "";
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

  _buildActionButtonHtml(options) {
    var buttonOptions = options || {};
    var className = String(buttonOptions.className || "action-button").trim();
    var action = String(buttonOptions.action || "").trim();
    var label = String(buttonOptions.label || "").trim();
    if (!action || !label) {
      return "";
    }

    var title = String(buttonOptions.title || label).trim();
    var icon = String(buttonOptions.icon || "").trim();
    var iconHtml = icon
      ? '<ha-icon class="button-icon' + (icon === "mdi:loading" ? ' spin' : '') + '" icon="' + this._escapeHtml(icon) + '"></ha-icon>'
      : "";

    return '<button class="' + this._escapeHtml(className) + '" type="button" data-action="' + this._escapeHtml(action) + '" title="' + this._escapeHtml(title) + '" aria-label="' + this._escapeHtml(title) + '"' + (buttonOptions.disabled ? ' disabled' : '') + '>' + iconHtml + '<span>' + this._escapeHtml(label) + '</span></button>';
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

  _render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }

    if (!this._isVisible()) {
      this._setExpanded(false);
      this.shadowRoot.innerHTML = "<style>:host{display:none}</style>";
      return;
    }

    var archive = this._resolveArchive();
    var archiveId = archive && archive.id != null ? String(archive.id) : "";
    var archiveIdentity = this._archiveKey(archive);
    var shouldPreferPrimary = !this._archiveIdentity;
    if (this._archiveId && archiveId && archiveId !== this._archiveId) {
      shouldPreferPrimary = true;
      this._setExpanded(false);
      this._activeIndex = 0;
      this._localArchiveOverride = null;
      this._localPrimaryPhotoPath = null;
      this._localSelectedPrimaryPhotoPath = null;
      this._localHasPrimaryPhotoOverride = null;
    }
    this._archiveId = archiveId;
    this._archiveIdentity = archiveIdentity;

    var images = this._buildImages(archive);
    if (!images.length) {
      this._setExpanded(false);
      this._archiveIdentity = "";
      this.shadowRoot.innerHTML = "<style>:host{display:none}</style>";
      return;
    }

    if (shouldPreferPrimary) {
      this._activeIndex = this._findPreferredActiveIndex(images);
    }

    if (this._activeIndex >= images.length) {
      this._activeIndex = 0;
    }

    var active = images[this._activeIndex];
    var archiveName = archive && archive.print_name ? String(archive.print_name) : "Archive Photos";
    var subtitle = this._subtitleForImages(images);
    var primaryAction = this._buildPrimaryAction(active, "action-button");
    var deleteAction = this._buildDeleteAction(active, "action-button");
    var uploadAction = this._buildUploadAction("action-button");
    var viewerAction = this._buildViewerAction("icon-action viewer");
    var expandAction = this._buildExpandAction("icon-action expand");
    var compact = !!this._config.compact;
    this._images = images;
    this._archiveName = archiveName;
    this._preloadImages(images);

    this.shadowRoot.innerHTML =
      "<style>" +
      ":host{display:block;}" +
      "ha-card{padding:0;overflow:hidden;border-radius:18px;box-shadow:none;background:none;}" +
      ".wrap{display:flex;flex-direction:column;gap:10px;padding:0;}" +
      ".stage{position:relative;border-radius:18px;overflow:hidden;background:rgba(15,23,42,0.32);min-height:220px;}" +
      ".stage-button{appearance:none;border:none;background:none;padding:0;display:block;width:100%;cursor:zoom-in;}" +
      ".stage-image{display:block;width:100%;max-height:320px;min-height:220px;object-fit:cover;background:rgba(15,23,42,0.32);}" +
      ".topbar{position:absolute;top:12px;left:12px;right:12px;display:flex;justify-content:space-between;align-items:flex-start;gap:8px;pointer-events:none;}" +
      ".topbar-left{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0;}" +
      ".topbar-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;pointer-events:auto;}" +
      ".icon-action{position:static;width:30px;height:30px;border:none;border-radius:999px;background:rgba(255,255,255,0.06);color:var(--secondary-text-color);cursor:pointer;display:flex;align-items:center;justify-content:center;z-index:2;flex:0 0 auto;transition:background .16s ease,color .16s ease,box-shadow .16s ease,transform .16s ease;}" +
      ".icon-action:hover,.icon-action:focus-visible{background:rgba(148,163,184,0.18);color:var(--primary-text-color);box-shadow:0 0 0 1px rgba(255,255,255,0.10);transform:translateY(-1px);outline:none;}" +
      ".icon-action:active{transform:translateY(0);}" +
      ".icon-action.viewer{background:rgba(0,137,123,0.16);color:#7dd3c8;}" +
      ".icon-action.viewer:hover,.icon-action.viewer:focus-visible{background:rgba(0,137,123,0.28);color:#b6fff3;box-shadow:0 0 0 1px rgba(125,211,200,0.26);transform:translateY(-1px);outline:none;}" +
      ".icon-action.viewer:active{transform:translateY(0);}" +
      ".icon-action.expand{background:rgba(37,99,235,0.18);color:#bfd7ff;}" +
      ".icon-action.expand:hover,.icon-action.expand:focus-visible{background:rgba(37,99,235,0.3);color:#eff6ff;box-shadow:0 0 0 1px rgba(147,197,253,0.32);transform:translateY(-1px);outline:none;}" +
      ".icon-action.expand:active{transform:translateY(0);}" +
      ".stage-badge{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;background:rgba(0,0,0,0.58);color:#fff;font-size:11px;font-weight:700;backdrop-filter:blur(10px);}" +
      ".nav{appearance:none;border:none;position:absolute;top:50%;transform:translateY(-50%);width:38px;height:38px;border-radius:999px;background:rgba(0,0,0,0.54);color:#fff;font-size:22px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(10px);}" +
      ".nav.prev{left:12px;}" +
      ".nav.next{right:12px;}" +
      ".meta{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:0 2px;}" +
      ".meta-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end;}" +
      ".title{font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:var(--secondary-text-color);}" +
      ".subtitle{font-size:13px;line-height:1.45;color:var(--secondary-text-color);margin-top:4px;}" +
      ".action-button{appearance:none;border:none;border-radius:999px;padding:8px 12px;background:rgba(46,125,50,0.12);color:#2e7d32;font-size:12px;font-weight:700;cursor:pointer;white-space:nowrap;display:inline-flex;align-items:center;gap:6px;}" +
      ".action-button.danger{background:rgba(183,28,28,0.12);color:#b71c1c;}" +
      ".action-button[disabled]{opacity:0.6;cursor:wait;}" +
      ".action-button .button-icon{--mdc-icon-size:14px;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;}" +
      ".action-button .button-icon.spin{animation:phgSpin 1s linear infinite;}" +
      ".upload-status-host{min-height:0;}" +
      ".upload-status{margin:2px 2px 0;padding:10px 12px;border-radius:14px;font-size:12px;font-weight:600;line-height:1.4;}" +
      ".upload-status.info{background:rgba(21,101,192,0.10);color:#0d47a1;}" +
      ".upload-status.success{background:rgba(46,125,50,0.12);color:#2e7d32;}" +
      ".upload-status.error{background:rgba(183,28,28,0.12);color:#b71c1c;}" +
      ".thumbs{display:flex;gap:8px;overflow-x:auto;padding-bottom:2px;}" +
      ".thumb{appearance:none;border:1px solid transparent;background:none;padding:0;border-radius:14px;overflow:hidden;cursor:pointer;flex:0 0 auto;position:relative;}" +
      ".thumb.active{border-color:rgba(59,130,246,0.9);box-shadow:0 0 0 2px rgba(59,130,246,0.2);}" +
      ".thumb img{display:block;width:72px;height:72px;object-fit:cover;background:rgba(15,23,42,0.28);}" +
      ".thumb-label{position:absolute;left:6px;bottom:6px;padding:3px 6px;border-radius:999px;background:rgba(0,0,0,0.58);color:#fff;font-size:10px;font-weight:700;backdrop-filter:blur(10px);}" +
      "@keyframes phgSpin{0%{transform:rotate(0deg);}100%{transform:rotate(360deg);}}" +
      ":host([compact]) .wrap{gap:8px;}" +
      ":host([compact]) .stage{border-radius:16px;}" +
      ":host([compact]) .stage-image{max-height:220px;min-height:220px;}" +
      ":host([compact]) .thumb img{width:64px;height:64px;}" +
      "@media (max-width: 640px){.stage-image{max-height:260px;min-height:180px;}}" +
      "</style>" +
      "<ha-card>" +
      '<div class="wrap">' +
      '<div class="stage">' +
      '<button class="stage-button" type="button" data-action="expand">' +
      '<img class="stage-image" src="' + this._escapeHtml(active.src) + '" alt="' + this._escapeHtml(active.filename || active.label || archiveName) + '" loading="eager" decoding="async">' +
      "</button>" +
      '<div class="topbar">' +
      '<div class="topbar-left"><span class="stage-badge">' + this._escapeHtml(active.label) + "</span></div>" +
      '<div class="topbar-actions">' + viewerAction + expandAction + '</div>' +
      "</div>" +
      (images.length > 1 ? '<button class="nav prev" type="button" data-action="prev" aria-label="Previous image">&#8249;</button><button class="nav next" type="button" data-action="next" aria-label="Next image">&#8250;</button>' : "") +
      "</div>" +
      (compact ? "" : ('<div class="meta">' +
      '<div><div class="title">' + this._escapeHtml(this._config.title) + "</div><div class=\"subtitle\">" + this._escapeHtml(archiveName) + " \u00b7 " + this._escapeHtml(subtitle) + "</div></div>" +
      '<div class="meta-actions">' + uploadAction + primaryAction + deleteAction + '</div>' +
      "</div>")) +
      '<div class="upload-status-host">' + this._renderUploadStatus() + '</div>' +
      '<div class="thumbs">' + images.map(function (image, index) {
        return '<button class="thumb' + (index === this._activeIndex ? ' active' : '') + '" type="button" data-index="' + this._escapeHtml(String(index)) + '">' +
          '<img src="' + this._escapeHtml(image.src) + '" alt="' + this._escapeHtml(image.filename || image.label || archiveName) + '">' +
          '<span class="thumb-label">' + this._escapeHtml(image.label) + '</span>' +
          '</button>';
      }.bind(this)).join("") + '</div>' +
      '<input type="file" accept="image/*" multiple data-upload-input="true" tabindex="-1" aria-hidden="true" style="position:absolute;left:-9999px;width:1px;height:1px;opacity:0;pointer-events:none">' +
      "</div>" +
      "</ha-card>";

    if (compact) {
      this.setAttribute("compact", "");
    } else {
      this.removeAttribute("compact");
    }

    this._syncExpandedState();
    this._syncActiveImage();
  }
}

if (!customElements.get("print-history-photo-gallery-card")) {
  customElements.define("print-history-photo-gallery-card", PrintHistoryPhotoGalleryCard);
}