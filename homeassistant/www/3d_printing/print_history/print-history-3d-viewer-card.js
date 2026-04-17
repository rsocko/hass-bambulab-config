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
    this._refreshButton = null;
    this._boundRefreshHandler = this._handleRefresh.bind(this);
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
    this._detachShellListeners();
  }

  getCardSize() {
    return 14;
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
      ".shell{display:grid;grid-template-rows:auto auto 1fr auto;gap:14px;min-height:680px;padding:18px;}" +
      ".panel{border:1px solid rgba(125,211,200,0.18);border-radius:20px;background:rgba(13,23,35,0.94);box-shadow:0 18px 50px rgba(0,0,0,0.22);backdrop-filter:blur(10px);}" +
      ".header{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:14px;padding:18px 20px;}" +
      ".eyebrow{font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#7dd3c8;font-weight:700;margin-bottom:6px;}" +
      "h1{margin:0;font-size:clamp(1.05rem,1.3vw + 0.8rem,1.55rem);line-height:1.2;}" +
      ".subtitle{margin-top:6px;color:#9fb0c0;font-size:0.93rem;}" +
      ".toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:flex-end;}" +
      ".button,.button:visited{display:inline-flex;align-items:center;justify-content:center;min-height:40px;padding:0 14px;border-radius:999px;border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.05);color:#f8fafc;text-decoration:none;font-size:0.92rem;font-weight:600;cursor:pointer;}" +
      ".button.primary{background:rgba(125,211,200,0.14);border-color:rgba(125,211,200,0.28);}" +
      ".button[aria-disabled='true']{opacity:0.45;pointer-events:none;}" +
      ".chips{display:flex;flex-wrap:wrap;gap:10px;padding:0 20px 18px;}" +
      ".chip{display:inline-flex;align-items:center;gap:8px;min-height:32px;padding:0 12px;border-radius:999px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.06);color:#f8fafc;font-size:0.84rem;font-weight:600;}" +
      ".chip.warn{color:#fde68a;border-color:rgba(245,158,11,0.34);background:rgba(245,158,11,0.12);}" +
      ".status{padding:16px 20px;color:#9fb0c0;font-size:0.95rem;line-height:1.5;}" +
      ".status.error{color:#fecaca;}" +
      ".stage{position:relative;min-height:min(72vh,680px);overflow:hidden;background:linear-gradient(180deg,rgba(10,19,30,0.92),rgba(8,14,23,0.98)),radial-gradient(circle at top,rgba(125,211,200,0.08),transparent 34%);}" +
      ".canvas{width:100%;height:100%;display:block;}" +
      ".overlay{position:absolute;inset:18px 18px auto auto;display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;max-width:calc(100% - 36px);pointer-events:none;}" +
      ".overlay .chip{pointer-events:auto;}" +
      ".fallback{display:none;padding:18px 20px 22px;border-top:1px solid rgba(255,255,255,0.06);background:rgba(18,31,46,0.98);}" +
      ".fallback.visible{display:block;}" +
      ".fallback-title{margin:0 0 8px;font-size:0.96rem;font-weight:700;}" +
      ".fallback-copy{margin:0 0 12px;color:#9fb0c0;line-height:1.5;font-size:0.92rem;}" +
      ".fallback pre{margin:0;padding:14px;border-radius:14px;overflow:auto;background:rgba(0,0,0,0.22);border:1px solid rgba(255,255,255,0.06);color:#dbeafe;font-family:'Cascadia Code',Consolas,monospace;font-size:0.8rem;line-height:1.45;max-height:220px;}" +
      ".footnote{padding:0 4px;color:#9fb0c0;font-size:0.82rem;line-height:1.5;}" +
      "@media (max-width:720px){.shell{padding:12px;min-height:560px;}.header{padding:16px;}.chips,.status,.fallback{padding-left:16px;padding-right:16px;}.stage{min-height:58vh;}}" +
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
      "<section id='fallback-panel' class='panel fallback'>" +
      "<p class='fallback-title'>Raw G-code Fallback</p>" +
      "<p id='fallback-copy' class='fallback-copy'></p>" +
      "<pre id='fallback-snippet'></pre>" +
      "</section>" +
      "<div class='footnote'>This popup prioritizes the Bambuddy G-code preview path. If the preview library cannot load in your browser, the raw G-code fallback remains available.</div>" +
      "</div>" +
      "</ha-card>";

    this._refreshButton = this.shadowRoot.getElementById("refresh-button");
    if (this._refreshButton) {
      this._refreshButton.addEventListener("click", this._boundRefreshHandler);
    }
  }

  _buildProxyUrl(path) {
    const entryId = this._config && this._config.entry_id ? this._config.entry_id : "";
    const suffix = entryId ? `?entry_id=${encodeURIComponent(entryId)}` : "";
    return `${path}${suffix}`;
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