class PrintHistoryTimelapseEditorCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._loaded = false;
    this._loading = false;
    this._saving = false;
    this._status = "";
    this._statusTone = "info";
    this._infoBundle = null;
    this._thumbnailBundle = null;
    this._lastRenderSignature = "";
  }

  setConfig(config) {
    this._config = {
      archive_json: config && config.archive_json ? config.archive_json : "{}",
      entry_id: config && config.entry_id ? config.entry_id : "",
      detail_entity: config && config.detail_entity ? config.detail_entity : "",
      title: config && config.title ? config.title : "Timelapse Editor",
    };
    this._loaded = false;
    this._loading = false;
    this._saving = false;
    this._status = "";
    this._statusTone = "info";
    this._infoBundle = null;
    this._thumbnailBundle = null;
    this._lastRenderSignature = "";
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

  getCardSize() {
    return 6;
  }

  _computeRenderSignature(hass) {
    if (!this._config || !hass || !hass.states) {
      return "";
    }
    var detailEntityId = this._config.detail_entity || "";
    var detailState = detailEntityId ? hass.states[detailEntityId] : null;
    return [
      typeof this._config.archive_json === "string"
        ? this._config.archive_json
        : JSON.stringify(this._config.archive_json || {}),
      detailState ? String(detailState.state || "") : "",
      detailState ? String(detailState.last_updated || detailState.last_changed || "") : "",
      this._loaded ? "loaded" : "idle",
      this._saving ? "saving" : "",
      this._status,
    ].join("|");
  }

  _resolveArchive() {
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
        return Object.assign({}, parsed, detailState.attributes.archive);
      }
    }
    return parsed;
  }

  _escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _archiveId() {
    var archive = this._resolveArchive();
    return archive && archive.id != null ? Number(archive.id) : 0;
  }

  _timelapsePath() {
    var archive = this._resolveArchive();
    return String(archive && archive.timelapse_path || "").trim();
  }

  _querySuffix() {
    return this._config && this._config.entry_id
      ? "?entry_id=" + encodeURIComponent(String(this._config.entry_id))
      : "";
  }

  _infoUrl() {
    var archiveId = this._archiveId();
    return archiveId > 0 ? "/api/bambuddy/print-history/archive/" + encodeURIComponent(String(archiveId)) + "/timelapse/info" + this._querySuffix() : "";
  }

  _thumbnailsUrl() {
    var archiveId = this._archiveId();
    return archiveId > 0 ? "/api/bambuddy/print-history/archive/" + encodeURIComponent(String(archiveId)) + "/timelapse/thumbnails" + this._querySuffix() : "";
  }

  _processUrl() {
    var archiveId = this._archiveId();
    return archiveId > 0 ? "/api/bambuddy/print-history/archive/" + encodeURIComponent(String(archiveId)) + "/timelapse/process" : "";
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

  _setStatus(message, tone) {
    this._status = String(message || "").trim();
    this._statusTone = tone || "info";
    this._render();
  }

  async _fetchJson(endpoint) {
    var response = await fetch(endpoint, {
      method: "GET",
      headers: await this._authHeaders(false),
      credentials: "same-origin",
    });
    if (response.status === 401) {
      response = await fetch(endpoint, {
        method: "GET",
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
    if (!response.ok) {
      throw new Error(String(payload.message || payload.error || ("Request failed (HTTP " + String(response.status) + ")")));
    }
    return payload && typeof payload === "object" ? payload : {};
  }

  async _loadEditorData() {
    if (this._loading || this._saving) {
      return;
    }
    if (this._archiveId() <= 0 || !this._timelapsePath()) {
      this._setStatus("No attached timelapse is available for editor tools.", "error");
      return;
    }

    this._loading = true;
    this._status = "";
    this._render();
    try {
      var thumbnailsSeparator = this._querySuffix() ? "&" : "?";
      var results = await Promise.all([
        this._fetchJson(this._infoUrl()),
        this._fetchJson(this._thumbnailsUrl() + thumbnailsSeparator + "count=8&width=176"),
      ]);
      this._infoBundle = results[0];
      this._thumbnailBundle = results[1];
      this._loaded = true;
      this._status = "Editor tools loaded.";
      this._statusTone = "success";
    } catch (error) {
      this._loaded = false;
      this._infoBundle = null;
      this._thumbnailBundle = null;
      this._status = String(error && error.message ? error.message : error || "Could not load editor tools");
      this._statusTone = "error";
    }
    this._loading = false;
    this._render();
  }

  _readInputValue(selector) {
    var element = this.shadowRoot ? this.shadowRoot.querySelector(selector) : null;
    return element ? String(element.value || "").trim() : "";
  }

  _numericValue(selector, fallbackValue) {
    var raw = this._readInputValue(selector);
    if (!raw) {
      return fallbackValue;
    }
    var numeric = Number(raw);
    return isFinite(numeric) ? numeric : fallbackValue;
  }

  async _processTimelapse() {
    if (this._saving || !this._loaded) {
      return;
    }
    var archiveId = this._archiveId();
    if (archiveId <= 0) {
      this._setStatus("Archive context is unavailable.", "error");
      return;
    }
    var trimStart = this._numericValue("#trim-start", 0);
    var trimEnd = this._numericValue("#trim-end", null);
    var speed = this._numericValue("#playback-speed", 1);
    var saveMode = this._readInputValue("#save-mode") || "replace";
    var outputFilename = this._readInputValue("#output-filename");
    if (trimEnd != null && trimEnd !== "" && trimEnd <= trimStart) {
      this._setStatus("Trim end must be greater than trim start.", "error");
      return;
    }
    if (speed < 0.25 || speed > 4) {
      this._setStatus("Speed must be between 0.25x and 4x.", "error");
      return;
    }

    var formData = new FormData();
    if (this._config && this._config.entry_id) {
      formData.append("entry_id", String(this._config.entry_id));
    }
    formData.append("trim_start", String(trimStart));
    if (trimEnd != null && trimEnd !== "") {
      formData.append("trim_end", String(trimEnd));
    }
    formData.append("speed", String(speed));
    formData.append("save_mode", saveMode);
    if (outputFilename) {
      formData.append("output_filename", outputFilename);
    }
    var audioInput = this.shadowRoot ? this.shadowRoot.querySelector("#audio-file") : null;
    var audioFile = audioInput && audioInput.files && audioInput.files[0] ? audioInput.files[0] : null;
    if (audioFile) {
      formData.append("audio", audioFile, audioFile.name || "audio.mp3");
    }

    this._saving = true;
    this._status = "";
    this._render();
    try {
      var response = await fetch(this._processUrl(), {
        method: "POST",
        headers: await this._authHeaders(false),
        credentials: "same-origin",
        body: formData,
      });
      if (response.status === 401) {
        response = await fetch(this._processUrl(), {
          method: "POST",
          headers: await this._authHeaders(true),
          credentials: "same-origin",
          body: formData,
        });
      }
      var payload = {};
      try {
        payload = await response.json();
      } catch (_error) {
        payload = {};
      }
      if (!response.ok) {
        throw new Error(String(payload.message || payload.error || ("Processing failed (HTTP " + String(response.status) + ")")));
      }
      this._status = String(payload.process && payload.process.message || payload.message || "Timelapse processing finished.");
      this._statusTone = "success";
      this._infoBundle = null;
      this._thumbnailBundle = null;
      this._loaded = false;
      window.dispatchEvent(new CustomEvent("print-history-timelapse-processed", {
        detail: {
          archiveId: archiveId,
          archive: payload.archive && typeof payload.archive === "object" ? payload.archive : null,
          cacheBust: Date.now(),
        },
      }));
    } catch (error) {
      this._status = String(error && error.message ? error.message : error || "Processing failed");
      this._statusTone = "error";
    }
    this._saving = false;
    this._render();
  }

  _formatSeconds(value) {
    var total = Number(value || 0);
    if (!isFinite(total) || total <= 0) {
      return "0:00";
    }
    var minutes = Math.floor(total / 60);
    var seconds = Math.floor(total % 60);
    return String(minutes) + ":" + String(seconds).padStart(2, "0");
  }

  _thumbnailMarkup() {
    var thumbnails = this._thumbnailBundle && Array.isArray(this._thumbnailBundle.thumbnails) ? this._thumbnailBundle.thumbnails : [];
    var timestamps = this._thumbnailBundle && Array.isArray(this._thumbnailBundle.timestamps) ? this._thumbnailBundle.timestamps : [];
    if (!thumbnails.length) {
      return '<div class="empty-strip">No timeline thumbnails were generated for this timelapse yet.</div>';
    }
    return '<div class="thumb-strip">' + thumbnails.map(function (item, index) {
      var timestamp = timestamps[index] != null ? Number(timestamps[index]) : 0;
      return '<div class="thumb">'
        + '<img src="data:image/jpeg;base64,' + this._escapeHtml(String(item || "")) + '" alt="Timelapse frame ' + String(index + 1) + '">'
        + '<div class="thumb-time">' + this._escapeHtml(this._formatSeconds(timestamp)) + '</div>'
        + '</div>';
    }.bind(this)).join("") + '</div>';
  }

  _bindEvents() {
    if (!this.shadowRoot) {
      return;
    }
    var self = this;
    var loadButton = this.shadowRoot.querySelector('[data-action="load-editor"]');
    if (loadButton) {
      loadButton.addEventListener("click", function () {
        self._loadEditorData();
      });
    }
    var saveButton = this.shadowRoot.querySelector('[data-action="process-timelapse"]');
    if (saveButton) {
      saveButton.addEventListener("click", function () {
        self._processTimelapse();
      });
    }
  }

  _render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }

    var archive = this._resolveArchive();
    var archiveName = String(archive && archive.print_name || "Print Timelapse").trim() || "Print Timelapse";
    var hasTimelapse = !!this._timelapsePath();
    var duration = this._infoBundle && this._infoBundle.duration != null ? Number(this._infoBundle.duration) : 0;
    var formMarkup = !hasTimelapse
      ? '<div class="empty">Attach a timelapse before loading editor tools.</div>'
      : !this._loaded
        ? '<div class="editor-intro"><div class="section-copy">Load editor tools to fetch timelapse info and timeline thumbnails through the new HA proxy routes.</div><button class="action-button primary" type="button" data-action="load-editor"' + (this._loading || this._saving ? ' disabled' : '') + '>Load Editor Tools</button></div>'
        : '<div class="editor-shell">'
          + '<div class="field-grid">'
          + '<label class="field"><span>Trim Start</span><input id="trim-start" type="number" min="0" step="0.1" value="0"></label>'
          + '<label class="field"><span>Trim End</span><input id="trim-end" type="number" min="0" step="0.1" value="' + this._escapeHtml(duration ? String(duration) : "") + '" placeholder="End of clip"></label>'
          + '<label class="field"><span>Playback Speed</span><select id="playback-speed"><option value="0.5">0.5x</option><option value="1" selected>1x</option><option value="1.5">1.5x</option><option value="2">2x</option><option value="3">3x</option></select></label>'
          + '<label class="field"><span>Save Mode</span><select id="save-mode"><option value="replace" selected>Replace Current Timelapse</option><option value="new">Save As New File</option></select></label>'
          + '</div>'
          + '<label class="field wide"><span>Output Filename</span><input id="output-filename" type="text" placeholder="Only used when save mode is new"></label>'
          + '<label class="field wide"><span>Optional Audio Overlay</span><input id="audio-file" type="file" accept=".mp3,.wav,.m4a,.aac,.ogg,audio/mpeg,audio/wav,audio/aac,audio/ogg"></label>'
          + '<div class="section-copy">Use trim start and trim end for the clip window, then send the processing request through `timelapse/process`. Save as new remains backend-only for now and does not add alternate files to the Layer 1 archive projection.</div>'
          + this._thumbnailMarkup()
          + '<div class="footer-row"><div class="helper">Duration ' + this._escapeHtml(this._formatSeconds(duration)) + ' · editor data stays on-demand and out of Layer 1.</div><button class="action-button primary" type="button" data-action="process-timelapse"' + (this._saving ? ' disabled' : '') + '>' + (this._saving ? 'Processing...' : 'Save Timelapse Changes') + '</button></div>'
          + '</div>';

    var statusMarkup = this._status
      ? '<div class="status ' + this._escapeHtml(this._statusTone) + '">' + this._escapeHtml(this._status) + '</div>'
      : "";
    var loadingMarkup = this._loading
      ? '<div class="status info">Loading timelapse info and thumbnails...</div>'
      : "";

    this.shadowRoot.innerHTML = ''
      + '<style>'
      + ':host{display:block;color:var(--primary-text-color);}'
      + 'ha-card{display:block;border-radius:18px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);box-shadow:none;overflow:hidden;}'
      + '.shell{display:flex;flex-direction:column;gap:14px;padding:16px;}'
      + '.heading{display:flex;align-items:center;justify-content:space-between;gap:12px;}'
      + '.title{font-size:12px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:var(--secondary-text-color);}'
      + '.subtitle{font-size:14px;font-weight:700;line-height:1.35;}'
      + '.editor-intro,.editor-shell{display:flex;flex-direction:column;gap:14px;}'
      + '.field-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;}'
      + '.field{display:flex;flex-direction:column;gap:8px;font-size:12px;font-weight:700;color:var(--secondary-text-color);}'
      + '.field.wide{width:100%;}'
      + '.field input,.field select{width:100%;border-radius:12px;border:1px solid rgba(255,255,255,0.12);background:rgba(255,255,255,0.04);color:var(--primary-text-color);padding:12px 14px;font:inherit;box-sizing:border-box;}'
      + '.field input[type="file"]{padding:10px 12px;}'
      + '.field input::placeholder{color:var(--secondary-text-color);}'
      + '.section-copy,.helper{font-size:13px;line-height:1.5;color:var(--secondary-text-color);}'
      + '.action-button{display:inline-flex;align-items:center;justify-content:center;padding:11px 14px;border-radius:999px;border:1px solid rgba(255,255,255,0.12);background:rgba(255,255,255,0.04);color:var(--primary-text-color);font-size:12px;font-weight:800;cursor:pointer;}'
      + '.action-button.primary{border-color:rgba(96,165,250,0.28);background:rgba(30,64,175,0.18);}'
      + '.action-button[disabled]{opacity:0.6;cursor:default;}'
      + '.thumb-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;}'
      + '.thumb{display:flex;flex-direction:column;gap:8px;padding:8px;border-radius:14px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);}'
      + '.thumb img{display:block;width:100%;aspect-ratio:16 / 9;object-fit:cover;border-radius:10px;background:#050a13;}'
      + '.thumb-time{font-size:11px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:var(--secondary-text-color);}'
      + '.empty-strip,.empty,.status{border-radius:14px;padding:12px 14px;font-size:13px;line-height:1.5;}'
      + '.empty,.empty-strip{background:rgba(255,255,255,0.04);color:var(--secondary-text-color);}'
      + '.status.info{background:rgba(30,64,175,0.14);border:1px solid rgba(96,165,250,0.18);}'
      + '.status.success{background:rgba(15,118,110,0.18);border:1px solid rgba(45,212,191,0.18);}'
      + '.status.error{background:rgba(127,29,29,0.22);border:1px solid rgba(248,113,113,0.18);}'
      + '.footer-row{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;}'
      + '@media (max-width: 640px){.shell{padding:14px;}.footer-row{align-items:stretch;}.action-button{width:100%;}}'
      + '</style>'
      + '<ha-card>'
      + '<div class="shell">'
      + '<div class="heading"><div class="title">' + this._escapeHtml(this._config.title || "Timelapse Editor") + '</div><div class="subtitle">' + this._escapeHtml(archiveName) + '</div></div>'
      + statusMarkup
      + loadingMarkup
      + formMarkup
      + '</div>'
      + '</ha-card>';

    this._bindEvents();
  }
}

if (!customElements.get("print-history-timelapse-editor-card")) {
  customElements.define("print-history-timelapse-editor-card", PrintHistoryTimelapseEditorCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some(function (card) { return card && card.type === "print-history-timelapse-editor-card"; })) {
  window.customCards.push({
    type: "print-history-timelapse-editor-card",
    name: "Print History Timelapse Editor Card",
    description: "Load timelapse info, thumbnails, and processing controls through the HA proxy layer.",
  });
}