const PRINT_HISTORY_VIEWER_CDN_MODULE_URL = "https://cdn.jsdelivr.net/npm/gcode-preview@2.18.0/+esm";

class PrintHistory3dViewerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._loadToken = 0;
    this._loadedSignature = "";
    this._preview = null;
    this._capture = null;
    this._uploadInProgress = false;
    this._rendererMode = "gcode";
    this._refreshButton = null;
    this._captureButton = null;
    this._cropButton = null;
    this._downloadCaptureButton = null;
    this._uploadCaptureButton = null;
    this._uploadPrimaryCaptureButton = null;
    this._boundRefreshHandler = this._handleRefresh.bind(this);
    this._boundCaptureHandler = this._handleCapture.bind(this);
    this._boundCropHandler = this._handleOpenCapturePage.bind(this, "crop");
    this._boundDownloadCaptureHandler = this._downloadCapture.bind(this);
    this._boundUploadCaptureHandler = this._handleUploadCapture.bind(this, false);
    this._boundUploadPrimaryCaptureHandler = this._handleUploadCapture.bind(this, true);
  }

  setConfig(config) {
    if (!config || config.archive_id == null || String(config.archive_id).trim() === "") {
      throw new Error("print-history-3d-viewer-card requires archive_id");
    }
    this._config = {
      archive_id: String(config.archive_id).trim(),
      archive_name: String(config.archive_name || "").trim(),
      entry_id: String(config.entry_id || "").trim(),
    };
    this._loadedSignature = "";
    this._renderShell();
    this._maybeLoad();
  }

  set hass(hass) {
    this._hass = hass;
    this._maybeLoad();
  }

  connectedCallback() {
    this._maybeLoad();
  }

  disconnectedCallback() {
    this._disposePreview(true);
    this._revokeCapture();
    this._detachShellListeners();
  }

  getCardSize() {
    return 18;
  }

  _handleRefresh() {
    this._loadedSignature = "";
    this._maybeLoad();
  }

  _detachShellListeners() {
    if (this._refreshButton) {
      this._refreshButton.removeEventListener("click", this._boundRefreshHandler);
      this._refreshButton = null;
    }
    if (this._captureButton) {
      this._captureButton.removeEventListener("click", this._boundCaptureHandler);
      this._captureButton = null;
    }
    if (this._cropButton) {
      this._cropButton.removeEventListener("click", this._boundCropHandler);
      this._cropButton = null;
    }
    if (this._downloadCaptureButton) {
      this._downloadCaptureButton.removeEventListener("click", this._boundDownloadCaptureHandler);
      this._downloadCaptureButton = null;
    }
    if (this._uploadCaptureButton) {
      this._uploadCaptureButton.removeEventListener("click", this._boundUploadCaptureHandler);
      this._uploadCaptureButton = null;
    }
    if (this._uploadPrimaryCaptureButton) {
      this._uploadPrimaryCaptureButton.removeEventListener("click", this._boundUploadPrimaryCaptureHandler);
      this._uploadPrimaryCaptureButton = null;
    }
  }

  _disposePreview(invalidateLoad = false) {
    if (invalidateLoad) {
      this._loadToken += 1;
    }
    if (this._preview && typeof this._preview.dispose === "function") {
      this._preview.dispose();
    }
    this._preview = null;
  }

  _maybeLoad() {
    if (!this.isConnected || !this._config || !this.shadowRoot || !this._hass) {
      return;
    }
    const signature = JSON.stringify(this._config);
    if (signature === this._loadedSignature) {
      return;
    }
    this._loadedSignature = signature;
    this._loadViewer();
  }

  _renderShell() {
    this._detachShellListeners();
    this.shadowRoot.innerHTML = "" +
      "<style>" +
      ":host{display:block;}" +
      "ha-card{padding:0;overflow:hidden;border-radius:24px;background:linear-gradient(180deg,#071019 0%,#09111b 100%);color:#f8fafc;}" +
      ".shell{display:grid;grid-template-rows:auto auto 1fr auto auto;gap:14px;min-height:720px;padding:18px;}" +
      ".panel{border:1px solid rgba(125,211,200,0.18);border-radius:20px;background:rgba(13,23,35,0.94);box-shadow:0 18px 50px rgba(0,0,0,0.22);backdrop-filter:blur(10px);}" +
      ".header{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:14px;padding:18px 20px;}" +
      ".eyebrow{font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#7dd3c8;font-weight:700;margin-bottom:6px;}" +
      "h1{margin:0;font-size:clamp(1.05rem,1.3vw + 0.8rem,1.55rem);line-height:1.2;}" +
      ".subtitle{margin-top:6px;color:#9fb0c0;font-size:0.93rem;}" +
      ".toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:flex-end;}" +
      ".button,.button:visited{display:inline-flex;align-items:center;justify-content:center;min-height:40px;padding:0 14px;border-radius:999px;border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.05);color:#f8fafc;text-decoration:none;font-size:0.92rem;font-weight:600;cursor:pointer;}" +
      ".button.primary{background:rgba(125,211,200,0.14);border-color:rgba(125,211,200,0.28);}" +
      ".button:disabled,.button[aria-disabled='true']{opacity:0.45;pointer-events:none;}" +
      ".chips{display:flex;flex-wrap:wrap;gap:10px;padding:0 20px 18px;}" +
      ".chip{display:inline-flex;align-items:center;gap:8px;min-height:32px;padding:0 12px;border-radius:999px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.06);color:#f8fafc;font-size:0.84rem;font-weight:600;}" +
      ".chip.warn{color:#fde68a;border-color:rgba(245,158,11,0.34);background:rgba(245,158,11,0.12);}" +
      ".status{padding:16px 20px;color:#9fb0c0;font-size:0.95rem;line-height:1.5;}" +
      ".status.error{color:#fecaca;}" +
      ".stage{position:relative;min-height:min(72vh,680px);overflow:hidden;background:linear-gradient(180deg,rgba(10,19,30,0.92),rgba(8,14,23,0.98)),radial-gradient(circle at top,rgba(125,211,200,0.08),transparent 34%);}" +
      ".canvas{width:100%;height:100%;display:block;}" +
      ".overlay{position:absolute;inset:18px 18px auto auto;display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;max-width:calc(100% - 36px);pointer-events:none;}" +
      ".overlay .chip{pointer-events:auto;}" +
      ".capture-panel{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(280px,0.95fr);gap:18px;padding:18px 20px;}" +
      ".capture-preview-wrap{position:relative;min-height:240px;border-radius:18px;overflow:hidden;border:1px solid rgba(255,255,255,0.06);background:linear-gradient(180deg,rgba(8,16,26,0.98),rgba(12,22,35,0.98));display:flex;align-items:center;justify-content:center;}" +
      ".capture-preview-wrap img{display:block;width:100%;height:100%;object-fit:contain;background:radial-gradient(circle at top,rgba(125,211,200,0.08),transparent 44%),#060c14;}" +
      ".capture-empty{padding:22px;color:#9fb0c0;font-size:0.94rem;line-height:1.6;text-align:left;}" +
      ".capture-meta{display:grid;align-content:start;gap:10px;}" +
      ".capture-kicker{font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#7dd3c8;font-weight:700;}" +
      ".capture-title{font-size:1.1rem;font-weight:700;color:#f8fafc;}" +
      ".capture-copy{color:#9fb0c0;font-size:0.94rem;line-height:1.55;}" +
      ".capture-status{min-height:22px;font-size:0.9rem;color:#9fb0c0;}" +
      ".capture-status.error{color:#fecaca;}" +
      ".capture-status.success{color:#86efac;}" +
      ".capture-actions{display:flex;flex-wrap:wrap;gap:10px;padding-top:4px;}" +
      ".fallback{display:none;padding:18px 20px 22px;border-top:1px solid rgba(255,255,255,0.06);background:rgba(18,31,46,0.98);}" +
      ".fallback.visible{display:block;}" +
      ".fallback-title{margin:0 0 8px;font-size:0.96rem;font-weight:700;}" +
      ".fallback-copy{margin:0 0 12px;color:#9fb0c0;line-height:1.5;font-size:0.92rem;}" +
      ".fallback pre{margin:0;padding:14px;border-radius:14px;overflow:auto;background:rgba(0,0,0,0.22);border:1px solid rgba(255,255,255,0.06);color:#dbeafe;font-family:'Cascadia Code',Consolas,monospace;font-size:0.8rem;line-height:1.45;max-height:220px;}" +
      ".footnote{padding:0 4px;color:#9fb0c0;font-size:0.82rem;line-height:1.5;}" +
      "@media (max-width:900px){.capture-panel{grid-template-columns:1fr;}}" +
      "@media (max-width:720px){.shell{padding:12px;min-height:600px;}.header{padding:16px;}.chips,.status,.fallback,.capture-panel{padding-left:16px;padding-right:16px;}.stage{min-height:58vh;}}" +
      "</style>" +
      "<ha-card>" +
      "<div class='shell'>" +
      "<section class='panel'>" +
      "<div class='header'>" +
      "<div>" +
      "<div class='eyebrow'>Print History Viewer</div>" +
      "<h1 id='viewer-title'>Loading archive viewer...</h1>" +
      "<div id='viewer-subtitle' class='subtitle'>Preparing Bambuddy archive preview.</div>" +
      "</div>" +
      "<div class='toolbar'>" +
      "<button id='capture-button' class='button primary' type='button'>Capture View</button>" +
      "<button id='crop-button' class='button' type='button'>Open Crop Tool</button>" +
      "<button id='refresh-button' class='button' type='button'>Refresh</button>" +
      "<a id='download-link' class='button' href='#' download='archive.gcode'>Download G-code</a>" +
      "</div></div>" +
      "<div id='capability-chips' class='chips'></div>" +
      "</section>" +
      "<section id='viewer-status' class='panel status'>Checking archive capabilities...</section>" +
      "<section class='panel stage'>" +
      "<canvas id='viewer-canvas' class='canvas'></canvas>" +
      "<div id='viewer-overlay' class='overlay'></div>" +
      "</section>" +
      "<section id='capture-panel' class='panel capture-panel'>" +
      "<div class='capture-preview-wrap'>" +
      "<img id='capture-preview-image' alt='Captured viewer render' hidden>" +
      "<div id='capture-empty' class='capture-empty'>Capture the current popup render to save a viewer-based archive image without reopening the viewer in another tab.</div>" +
      "</div>" +
      "<div class='capture-meta'>" +
      "<div class='capture-kicker'>Viewer Capture</div>" +
      "<div id='capture-title' class='capture-title'>No render captured yet</div>" +
      "<div id='capture-copy' class='capture-copy'>Capture uses the exact popup canvas that is already on screen, so the saved image matches the current preview framing and colors.</div>" +
      "<div id='capture-status' class='capture-status'></div>" +
      "<div class='capture-actions'>" +
      "<button id='download-capture-button' class='button' type='button' disabled>Download PNG</button>" +
      "<button id='upload-capture-button' class='button' type='button' disabled>Upload to Archive</button>" +
      "<button id='upload-primary-capture-button' class='button primary' type='button' disabled>Upload + Use In List View</button>" +
      "</div>" +
      "</div>" +
      "</section>" +
      "<section id='fallback-panel' class='panel fallback'>" +
      "<p class='fallback-title'>Raw G-code Fallback</p>" +
      "<p id='fallback-copy' class='fallback-copy'></p>" +
      "<pre id='fallback-snippet'></pre>" +
      "</section>" +
      "<div class='footnote'>Capture runs directly inside this popup against the current canvas. The crop tool still opens the standalone viewer so the advanced crop workflow can stay isolated.</div>" +
      "</div>" +
      "</ha-card>";

    this._refreshButton = this.shadowRoot.getElementById("refresh-button");
    this._captureButton = this.shadowRoot.getElementById("capture-button");
    this._cropButton = this.shadowRoot.getElementById("crop-button");
    this._downloadCaptureButton = this.shadowRoot.getElementById("download-capture-button");
    this._uploadCaptureButton = this.shadowRoot.getElementById("upload-capture-button");
    this._uploadPrimaryCaptureButton = this.shadowRoot.getElementById("upload-primary-capture-button");
    if (this._refreshButton) {
      this._refreshButton.addEventListener("click", this._boundRefreshHandler);
    }
    if (this._captureButton) {
      this._captureButton.addEventListener("click", this._boundCaptureHandler);
    }
    if (this._cropButton) {
      this._cropButton.addEventListener("click", this._boundCropHandler);
    }
    if (this._downloadCaptureButton) {
      this._downloadCaptureButton.addEventListener("click", this._boundDownloadCaptureHandler);
    }
    if (this._uploadCaptureButton) {
      this._uploadCaptureButton.addEventListener("click", this._boundUploadCaptureHandler);
    }
    if (this._uploadPrimaryCaptureButton) {
      this._uploadPrimaryCaptureButton.addEventListener("click", this._boundUploadPrimaryCaptureHandler);
    }
    this._updateCapturePanel();
  }

  _buildProxyUrl(path) {
    const entryId = this._config && this._config.entry_id ? this._config.entry_id : "";
    const suffix = entryId ? `?entry_id=${encodeURIComponent(entryId)}` : "";
    return `${path}${suffix}`;
  }

  _viewerPageUrl(mode) {
    const params = new URLSearchParams();
    params.set("archive_id", String(this._config.archive_id || ""));
    if (this._config.archive_name) {
      params.set("archive_name", this._config.archive_name);
    }
    if (this._config.entry_id) {
      params.set("entry_id", this._config.entry_id);
    }
    if (mode === "crop") {
      params.set("capture_mode", "crop");
    }
    return `/local/3d_printing/print_history/print-history-3d-viewer.html?${params.toString()}`;
  }

  _handleOpenCapturePage(mode) {
    const targetUrl = this._viewerPageUrl(mode);
    if (typeof window !== "undefined" && typeof window.open === "function") {
      window.open(targetUrl, "_blank", "noopener");
    }
  }

  _setCaptureStatus(message, tone) {
    const node = this.shadowRoot && this.shadowRoot.getElementById("capture-status");
    if (!node) {
      return;
    }
    node.textContent = String(message || "").trim();
    node.className = tone === "error"
      ? "capture-status error"
      : tone === "success"
        ? "capture-status success"
        : "capture-status";
  }

  _updateCapturePanel() {
    const image = this.shadowRoot && this.shadowRoot.getElementById("capture-preview-image");
    const empty = this.shadowRoot && this.shadowRoot.getElementById("capture-empty");
    const title = this.shadowRoot && this.shadowRoot.getElementById("capture-title");
    const copy = this.shadowRoot && this.shadowRoot.getElementById("capture-copy");
    if (!image || !empty || !title || !copy) {
      return;
    }

    if (this._capture && this._capture.objectUrl) {
      image.src = this._capture.objectUrl;
      image.hidden = false;
      empty.hidden = true;
      title.textContent = `${this._capture.width} x ${this._capture.height} PNG ready`;
      copy.textContent = `Archive #${this._config && this._config.archive_id ? this._config.archive_id : ""} full-frame capture prepared from the current popup canvas.`;
    } else {
      image.removeAttribute("src");
      image.hidden = true;
      empty.hidden = false;
      title.textContent = "No render captured yet";
      copy.textContent = "Capture uses the exact popup canvas that is already on screen, so the saved image matches the current preview framing and colors.";
    }

    if (this._downloadCaptureButton) {
      this._downloadCaptureButton.disabled = !this._capture;
    }
    if (this._uploadCaptureButton) {
      this._uploadCaptureButton.disabled = !this._capture || this._uploadInProgress;
    }
    if (this._uploadPrimaryCaptureButton) {
      this._uploadPrimaryCaptureButton.disabled = !this._capture || this._uploadInProgress;
    }
  }

  _revokeCapture() {
    if (this._capture && this._capture.objectUrl) {
      URL.revokeObjectURL(this._capture.objectUrl);
    }
    this._capture = null;
  }

  _scaledDimensions(width, height, maxDimension) {
    const safeWidth = Math.max(1, Number(width) || 1);
    const safeHeight = Math.max(1, Number(height) || 1);
    const scale = Math.min(1, maxDimension / Math.max(safeWidth, safeHeight));
    return {
      width: Math.max(1, Math.round(safeWidth * scale)),
      height: Math.max(1, Math.round(safeHeight * scale)),
    };
  }

  _canvasToBlob(canvas, mimeType, quality) {
    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (!blob) {
          reject(new Error("Canvas export returned no data"));
          return;
        }
        resolve(blob);
      }, mimeType, quality);
    });
  }

  _blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error("Could not encode capture for upload"));
      reader.onload = () => {
        const result = String(reader.result || "");
        const parts = result.split(",", 2);
        resolve(parts.length === 2 ? parts[1] : result);
      };
      reader.readAsDataURL(blob);
    });
  }

  _buildCaptureFileName() {
    const archiveId = String(this._config && this._config.archive_id ? this._config.archive_id : "archive").trim();
    const rendererMode = String(this._rendererMode || "viewer").trim().toLowerCase();
    const now = new Date();
    const timestamp = now.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
    return `viewer-capture-${archiveId}-${rendererMode}-${timestamp}.png`;
  }

  async _captureCurrentView() {
    const canvas = this.shadowRoot && this.shadowRoot.getElementById("viewer-canvas");
    if (!(canvas instanceof HTMLCanvasElement)) {
      throw new Error("Viewer canvas is not available.");
    }
    const sourceWidth = canvas.width || canvas.clientWidth || 0;
    const sourceHeight = canvas.height || canvas.clientHeight || 0;
    if (sourceWidth <= 0 || sourceHeight <= 0) {
      throw new Error("The viewer has not rendered a captureable frame yet.");
    }

    const dimensions = this._scaledDimensions(sourceWidth, sourceHeight, 2048);
    const exportCanvas = document.createElement("canvas");
    exportCanvas.width = dimensions.width;
    exportCanvas.height = dimensions.height;
    const context = exportCanvas.getContext("2d");
    if (!context) {
      throw new Error("Canvas rendering is unavailable for capture.");
    }
    context.drawImage(canvas, 0, 0, sourceWidth, sourceHeight, 0, 0, dimensions.width, dimensions.height);
    const blob = await this._canvasToBlob(exportCanvas, "image/png");

    this._revokeCapture();
    this._capture = {
      blob,
      objectUrl: URL.createObjectURL(blob),
      width: dimensions.width,
      height: dimensions.height,
      mimeType: "image/png",
      fileName: this._buildCaptureFileName(),
    };
    this._updateCapturePanel();
    this._setCaptureStatus("Captured the current popup view. Download it or upload it to the archive.", "success");
  }

  async _handleCapture() {
    try {
      await this._captureCurrentView();
    } catch (error) {
      const message = error && error.message ? error.message : String(error);
      this._setCaptureStatus(message || "Capture failed.", "error");
    }
  }

  _downloadCapture() {
    if (!this._capture || !this._capture.objectUrl) {
      return;
    }
    const anchor = document.createElement("a");
    anchor.href = this._capture.objectUrl;
    anchor.download = this._capture.fileName;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  }

  _buildAuthHeaders(extraHeaders) {
    const merged = Object.assign({}, extraHeaders || {});
    const accessToken = this._hass && this._hass.auth && this._hass.auth.data
      ? String(this._hass.auth.data.accessToken || "").trim()
      : "";
    if (accessToken) {
      merged.Authorization = `Bearer ${accessToken}`;
    }
    return merged;
  }

  async _uploadCapture(useAsPrimary) {
    if (!this._capture || !this._config || !this._config.archive_id) {
      return;
    }
    this._uploadInProgress = true;
    this._updateCapturePanel();
    this._setCaptureStatus(useAsPrimary ? "Uploading capture and promoting it for list view..." : "Uploading capture to the archive...", "info");

    try {
      const response = await fetch(
        this._buildProxyUrl(`/api/bambuddy/print-history/archive-viewer/${encodeURIComponent(this._config.archive_id)}/capture-upload`),
        {
          method: "POST",
          credentials: "same-origin",
          headers: this._buildAuthHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({
            file_name: this._capture.fileName,
            mime_type: this._capture.mimeType,
            content_base64: await this._blobToBase64(this._capture.blob),
            use_as_primary: !!useAsPrimary,
          }),
        }
      );
      let payload = null;
      try {
        payload = await response.json();
      } catch (_error) {
        payload = null;
      }
      if (!response.ok) {
        throw new Error(payload && payload.message ? payload.message : `Request failed with HTTP ${response.status}`);
      }
      const uploadedPhotoPath = String(payload && payload.uploaded_photo_path ? payload.uploaded_photo_path : this._capture.fileName || "").trim();
      if (uploadedPhotoPath) {
        this._capture.fileName = uploadedPhotoPath;
      }
      this._setCaptureStatus(
        useAsPrimary
          ? "Capture uploaded and promoted for list view rendering."
          : "Capture uploaded to the archive photo gallery.",
        "success"
      );
    } catch (error) {
      const message = error && error.message ? error.message : String(error);
      this._setCaptureStatus(message || "Capture upload failed.", "error");
    } finally {
      this._uploadInProgress = false;
      this._updateCapturePanel();
    }
  }

  async _handleUploadCapture(useAsPrimary) {
    await this._uploadCapture(useAsPrimary);
  }

  _escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _normalizeHex(value) {
    const raw = String(value || "").trim().replace(/^#/, "").replace(/"/g, "");
    if (!raw) {
      return "";
    }
    const trimmed = raw.length === 8 ? raw.slice(0, 6) : raw;
    return /^[0-9a-fA-F]{6}$/.test(trimmed) ? `#${trimmed.toUpperCase()}` : "";
  }

  _normalizeColors(colors) {
    if (!Array.isArray(colors)) {
      return [];
    }
    return colors.map(this._normalizeHex.bind(this)).filter(Boolean);
  }

  _extractFilamentColorsFromGcode(gcodeText) {
    const match = String(gcodeText || "").match(/^\s*;\s*filament_colour\s*=\s*(.+)$/im);
    if (!match || !match[1]) {
      return [];
    }
    return this._normalizeColors(match[1].split(";"));
  }

  _resolvePreviewColors(capabilities, gcodeText) {
    const gcodeColors = this._extractFilamentColorsFromGcode(gcodeText);
    if (gcodeColors.length) {
      return gcodeColors;
    }
    return this._normalizeColors(capabilities.filament_colors);
  }

  _normalizePreviewGcode(gcodeText, maxToolIndex) {
    const source = String(gcodeText || "");
    if (!source) {
      return source;
    }

    const maxKnownTool = Number.isInteger(maxToolIndex) && maxToolIndex >= 0 ? maxToolIndex : null;
    const lines = source.split("\n");
    const toolPattern = /^T(\d+)\s*$/;
    let currentTool = null;
    let sawAnyTool = false;

    const normalizedLines = lines.map((line) => {
      const match = line.match(toolPattern);
      if (!match) {
        return line;
      }

      sawAnyTool = true;
      const tool = Number(match[1]);
      if (!Number.isFinite(tool)) {
        return line;
      }

      let normalizedTool = tool;
      if (maxKnownTool != null) {
        if (tool >= 0 && tool <= maxKnownTool) {
          normalizedTool = tool;
        } else if (tool === 1000) {
          normalizedTool = 0;
        } else if (tool === 255 && currentTool != null) {
          normalizedTool = currentTool;
        } else if (currentTool != null) {
          normalizedTool = currentTool;
        } else {
          normalizedTool = 0;
        }
      }

      currentTool = normalizedTool;
      return `T${normalizedTool}`;
    });

    if (!sawAnyTool && maxKnownTool != null) {
      normalizedLines.unshift("T0");
    }

    return normalizedLines.join("\n");
  }

  _normalizeBuildVolume(buildVolume) {
    if (!buildVolume || typeof buildVolume !== "object") {
      return { x: 256, y: 256, z: 256 };
    }
    const x = Number(buildVolume.x || 256);
    const y = Number(buildVolume.y || 256);
    const z = Number(buildVolume.z || 256);
    return {
      x: Number.isFinite(x) && x > 0 ? x : 256,
      y: Number.isFinite(y) && y > 0 ? y : 256,
      z: Number.isFinite(z) && z > 0 ? z : 256,
    };
  }

  async _fetchViewerPayload() {
    return this._hass.callWS({
      type: "bambuddy/print_history_archive_viewer",
      archive_id: Number(this._config.archive_id),
      entry_id: this._config.entry_id || undefined,
      include_gcode: true,
    });
  }

  _setStatus(message, isError = false) {
    const status = this.shadowRoot && this.shadowRoot.getElementById("viewer-status");
    if (!status) {
      return;
    }
    status.textContent = message;
    status.className = isError ? "panel status error" : "panel status";
  }

  _setTitle(title, subtitle) {
    const titleNode = this.shadowRoot && this.shadowRoot.getElementById("viewer-title");
    const subtitleNode = this.shadowRoot && this.shadowRoot.getElementById("viewer-subtitle");
    if (titleNode) {
      titleNode.textContent = title;
    }
    if (subtitleNode) {
      subtitleNode.textContent = subtitle;
    }
  }

  _renderCapabilityChips(capabilities, colors) {
    const chips = this.shadowRoot && this.shadowRoot.getElementById("capability-chips");
    if (!chips) {
      return;
    }
    const buildVolume = this._normalizeBuildVolume(capabilities.build_volume);
    const chipMarkup = [
      `<span class='chip${capabilities.has_gcode ? "" : " warn"}'>G-code ${capabilities.has_gcode ? "Available" : "Unavailable"}</span>`,
      `<span class='chip${capabilities.has_model ? "" : " warn"}'>3D Model ${capabilities.has_model ? "Available" : "Unavailable"}</span>`,
      `<span class='chip'>Build ${buildVolume.x} x ${buildVolume.y} x ${buildVolume.z}</span>`,
    ];
    if (capabilities.has_source) {
      chipMarkup.push("<span class='chip'>Source 3MF Attached</span>");
    }
    if (colors.length) {
      chipMarkup.push(`<span class='chip'>${colors.length} Filament Color${colors.length === 1 ? "" : "s"}</span>`);
    }
    chips.innerHTML = chipMarkup.join("");
  }

  _renderOverlay(colors) {
    const overlay = this.shadowRoot && this.shadowRoot.getElementById("viewer-overlay");
    if (!overlay) {
      return;
    }
    const items = [];
    for (let index = 0; index < colors.length; index += 1) {
      const color = colors[index];
      items.push(
        `<span class='chip' title='Tool T${index}'><span style='display:inline-block;width:12px;height:12px;border-radius:999px;background:${this._escapeHtml(color)};box-shadow:inset 0 0 0 1px rgba(255,255,255,0.28);'></span>T${index}</span>`
      );
    }
    overlay.innerHTML = items.join("");
  }

  _setDownloadLink(gcodeUrl) {
    const downloadLink = this.shadowRoot && this.shadowRoot.getElementById("download-link");
    const archiveName = this._config && this._config.archive_name ? this._config.archive_name : `archive-${this._config.archive_id}`;

    if (downloadLink) {
      downloadLink.href = gcodeUrl;
      downloadLink.download = `${archiveName}.gcode`;
    }
  }

  _showFallback(message, gcodeText) {
    const panel = this.shadowRoot && this.shadowRoot.getElementById("fallback-panel");
    const copy = this.shadowRoot && this.shadowRoot.getElementById("fallback-copy");
    const snippet = this.shadowRoot && this.shadowRoot.getElementById("fallback-snippet");
    if (!panel || !copy || !snippet) {
      return;
    }
    panel.classList.add("visible");
    copy.textContent = message;
    snippet.textContent = String(gcodeText || "").split("\n").slice(0, 80).join("\n");
  }

  _hideFallback() {
    const panel = this.shadowRoot && this.shadowRoot.getElementById("fallback-panel");
    const copy = this.shadowRoot && this.shadowRoot.getElementById("fallback-copy");
    const snippet = this.shadowRoot && this.shadowRoot.getElementById("fallback-snippet");
    if (!panel || !copy || !snippet) {
      return;
    }
    panel.classList.remove("visible");
    copy.textContent = "";
    snippet.textContent = "";
  }

  async _loadViewer() {
    const token = ++this._loadToken;
    const archiveId = this._config && this._config.archive_id ? this._config.archive_id : "";
    const archiveTitle = this._config && this._config.archive_name ? this._config.archive_name : `Archive ${archiveId}`;

    if (!archiveId) {
      this._setTitle("Archive viewer unavailable", "No archive ID was provided to the popup.");
      this._setStatus("Archive viewer could not start because archive_id is missing.", true);
      this._showFallback("Launch this popup from a print-history archive card or popup action.", "");
      return;
    }

    this._setTitle(archiveTitle, `Archive #${archiveId}`);
    this._disposePreview();
  this._hideFallback();

    const gcodeUrl = this._buildProxyUrl(`/api/bambuddy/print-history/archive-viewer/${encodeURIComponent(archiveId)}/gcode`);
    this._setDownloadLink(gcodeUrl);

    try {
      this._setStatus("Checking Bambuddy archive capabilities...");
      const viewerPayload = await this._fetchViewerPayload();
      if (token !== this._loadToken) {
        return;
      }
      const capabilities = viewerPayload && typeof viewerPayload.capabilities === "object"
        ? viewerPayload.capabilities
        : {};

      if (!capabilities.has_gcode) {
        this._setStatus("This archive does not expose extracted G-code, so the preview cannot be rendered here.", true);
        this._showFallback(
          capabilities.has_model
            ? "The archive still has a 3D model, but Bambuddy does not expose a deep-linkable modal route that Home Assistant can reuse directly."
            : "This archive has neither extracted G-code nor a usable model preview path for this popup.",
          ""
        );
        return;
      }

      this._setStatus("Downloading G-code from Bambuddy...");
      const gcodeText = viewerPayload && typeof viewerPayload.gcode === "string" ? viewerPayload.gcode : "";
      if (!String(gcodeText || "").trim()) {
        this._setStatus("Bambuddy returned an empty G-code payload for this archive.", true);
        this._showFallback("The archive G-code payload was empty.", "");
        return;
      }

      const colors = this._resolvePreviewColors(capabilities, gcodeText);
      const previewGcode = this._normalizePreviewGcode(gcodeText, colors.length ? colors.length - 1 : null);
      this._renderCapabilityChips(capabilities, colors);
      this._renderOverlay(colors);

      const canvas = this.shadowRoot && this.shadowRoot.getElementById("viewer-canvas");
      if (!(canvas instanceof HTMLCanvasElement)) {
        throw new Error("Viewer canvas is not available.");
      }

      this._setStatus("Rendering G-code preview...");
      try {
        const GCodePreview = await import(PRINT_HISTORY_VIEWER_CDN_MODULE_URL);
        if (token !== this._loadToken) {
          return;
        }
        const preview = GCodePreview.init({
          canvas,
          buildVolume: this._normalizeBuildVolume(capabilities.build_volume),
          extrusionColor: colors.length ? colors : ["#7DD3C8", "#F59E0B", "#38BDF8", "#F97316"],
          disableGradient: true,
          backgroundColor: "#08101a",
          gridColor: "rgba(125, 211, 200, 0.18)",
          allowDragNDrop: false,
        });
        this._preview = preview;
        this._rendererMode = "gcode";
        preview.processGCode(previewGcode);
        this._setStatus("Rendered Bambuddy G-code preview. Use drag, pan, and zoom inside the canvas.");
      } catch (error) {
        const message = error && error.message ? error.message : String(error);
        this._setStatus("The interactive preview library could not be loaded, so the popup fell back to raw G-code.", true);
        this._showFallback(`Interactive preview failed to load: ${message}`, gcodeText);
      }
    } catch (error) {
      const message = error && error.message ? error.message : String(error);
      this._setStatus(message, true);
      this._showFallback(message, "");
    }
  }
}

if (!customElements.get("print-history-3d-viewer-card")) {
  customElements.define("print-history-3d-viewer-card", PrintHistory3dViewerCard);
}