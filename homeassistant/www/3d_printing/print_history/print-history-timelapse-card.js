class PrintHistoryTimelapseCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._archiveOverride = null;
    this._infoBundle = null;
    this._infoArchiveId = "";
    this._infoLoading = false;
    this._infoError = "";
    this._playbackRate = 1;
    this._refreshToken = "";
    this._lastRenderSignature = "";
    this._boundProcessedHandler = this._handleTimelapseProcessed.bind(this);
  }

  connectedCallback() {
    window.addEventListener("print-history-timelapse-processed", this._boundProcessedHandler);
  }

  disconnectedCallback() {
    window.removeEventListener("print-history-timelapse-processed", this._boundProcessedHandler);
  }

  setConfig(config) {
    this._config = {
      archive_json: config && config.archive_json ? config.archive_json : "{}",
      entry_id: config && config.entry_id ? config.entry_id : "",
      detail_entity: config && config.detail_entity ? config.detail_entity : "",
      api_base_entity: config && config.api_base_entity ? config.api_base_entity : "input_text.bambuddy_api_base_url",
      title: config && config.title ? config.title : "Timelapse",
    };
    this._archiveOverride = null;
    this._infoBundle = null;
    this._infoArchiveId = "";
    this._infoLoading = false;
    this._infoError = "";
    this._playbackRate = 1;
    this._refreshToken = "";
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
    return 8;
  }

  _computeRenderSignature(hass) {
    if (!this._config || !hass || !hass.states) {
      return "";
    }

    var detailEntityId = this._config.detail_entity || "";
    var detailState = detailEntityId ? hass.states[detailEntityId] : null;
    var baseEntityId = this._config.api_base_entity || "input_text.bambuddy_api_base_url";
    var baseState = hass.states[baseEntityId];

    return [
      this._archiveOverride ? JSON.stringify(this._archiveOverride) : "",
      typeof this._config.archive_json === "string"
        ? this._config.archive_json
        : JSON.stringify(this._config.archive_json || {}),
      detailState ? String(detailState.state || "") : "",
      detailState ? String(detailState.last_updated || detailState.last_changed || "") : "",
      baseState ? String(baseState.state || "") : "",
      baseState ? String(baseState.last_updated || baseState.last_changed || "") : "",
      String(this._refreshToken || ""),
    ].join("|");
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

  _getBaseUrl() {
    var entityId = this._config ? this._config.api_base_entity : "input_text.bambuddy_api_base_url";
    var raw = this._hass && this._hass.states && this._hass.states[entityId]
      ? this._hass.states[entityId].state
      : "";
    return String(raw || "").replace(/\/$/, "");
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

  _timelapseUrl(archive) {
    var baseUrl = this._getBaseUrl();
    var archiveId = archive && archive.id != null ? String(archive.id) : "";
    var timelapsePath = this._timelapsePath(archive);
    if (!baseUrl || !archiveId || !timelapsePath) {
      return "";
    }

    var cacheKey = JSON.stringify({
      timelapse_path: timelapsePath,
      updated_at: archive && (archive.source_updated_at || archive.updated_at || archive.completed_at || archive.created_at || ""),
      refresh_token: this._refreshToken || "",
    });
    return baseUrl + "/api/v1/archives/" + encodeURIComponent(archiveId) + "/timelapse?v=" + encodeURIComponent(cacheKey);
  }

  _timelapseInfoUrl(archive) {
    var archiveId = archive && archive.id != null ? String(archive.id) : "";
    if (!archiveId) {
      return "";
    }
    var query = this._config && this._config.entry_id ? "?entry_id=" + encodeURIComponent(String(this._config.entry_id)) : "";
    return "/api/bambuddy/print-history/archive/" + encodeURIComponent(archiveId) + "/timelapse/info" + query;
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

  _timelapseFilename(path) {
    var normalized = String(path || "").trim().replace(/\\/g, "/");
    return normalized ? normalized.split("/").pop() : "";
  }

  _escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _formatSeconds(value) {
    var total = Number(value || 0);
    if (!isFinite(total) || total <= 0) {
      return "0:00";
    }
    var hours = Math.floor(total / 3600);
    var minutes = Math.floor((total % 3600) / 60);
    var seconds = Math.floor(total % 60);
    if (hours > 0) {
      return String(hours) + ":" + String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0");
    }
    return String(minutes) + ":" + String(seconds).padStart(2, "0");
  }

  _viewerStatMarkup(label, value) {
    var normalizedValue = String(value == null ? "" : value).trim();
    if (!normalizedValue) {
      return "";
    }
    return '<div class="stat"><div class="stat-label">' + this._escapeHtml(label) + '</div><div class="stat-value">' + this._escapeHtml(normalizedValue) + '</div></div>';
  }

  _handleTimelapseProcessed(event) {
    var detail = event && event.detail && typeof event.detail === "object" ? event.detail : {};
    var archive = this._resolveArchive();
    var currentArchiveId = archive && archive.id != null ? String(archive.id) : "";
    var eventArchiveId = detail.archiveId != null ? String(detail.archiveId) : "";
    if (!currentArchiveId || currentArchiveId !== eventArchiveId) {
      return;
    }
    if (detail.archive && typeof detail.archive === "object") {
      this._archiveOverride = Object.assign({}, archive, detail.archive);
    }
    this._refreshToken = String(detail.cacheBust || Date.now());
    this._infoBundle = null;
    this._infoArchiveId = "";
    this._infoError = "";
    this._lastRenderSignature = "";
    this._render();
  }

  async _loadInfo(archive) {
    var archiveId = archive && archive.id != null ? String(archive.id) : "";
    var timelapsePath = this._timelapsePath(archive);
    if (!archiveId || !timelapsePath || this._infoLoading || this._infoArchiveId === archiveId) {
      return;
    }

    this._infoLoading = true;
    this._infoError = "";
    this._render();
    try {
      var endpoint = this._timelapseInfoUrl(archive);
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
        throw new Error(String(payload.message || payload.error || ("Could not load timelapse info (HTTP " + String(response.status) + ")")));
      }
      this._infoBundle = payload && typeof payload === "object" ? payload : {};
      this._infoArchiveId = archiveId;
      this._infoError = "";
    } catch (error) {
      this._infoBundle = null;
      this._infoArchiveId = "";
      this._infoError = String(error && error.message ? error.message : error || "Could not load timelapse info");
    }

    this._infoLoading = false;
    this._render();
  }

  _applyPlaybackRate(nextRate) {
    var normalizedRate = Number(nextRate || 1);
    if (!isFinite(normalizedRate) || normalizedRate <= 0) {
      normalizedRate = 1;
    }
    this._playbackRate = normalizedRate;
    var player = this.shadowRoot ? this.shadowRoot.querySelector("video.player") : null;
    if (player) {
      player.playbackRate = normalizedRate;
    }
    this._updateRateButtons();
  }

  _updateRateButtons() {
    if (!this.shadowRoot) {
      return;
    }
    Array.prototype.slice.call(this.shadowRoot.querySelectorAll("[data-rate]"))
      .forEach(function (button) {
        var isActive = Number(button.getAttribute("data-rate")) === Number(this._playbackRate);
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
      }.bind(this));
  }

  _bindInteractions() {
    if (!this.shadowRoot) {
      return;
    }
    var self = this;
    var player = this.shadowRoot.querySelector("video.player");
    if (player) {
      player.playbackRate = this._playbackRate;
    }
    this._updateRateButtons();
    Array.prototype.slice.call(this.shadowRoot.querySelectorAll("[data-rate]"))
      .forEach(function (button) {
        button.addEventListener("click", function () {
          self._applyPlaybackRate(button.getAttribute("data-rate"));
        });
      });
  }

  _render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }

    var archive = this._resolveArchive();
    var timelapsePath = this._timelapsePath(archive);
    var timelapseUrl = this._timelapseUrl(archive);
    var filename = this._timelapseFilename(timelapsePath);
    var archiveName = String(archive && archive.print_name || "Print Timelapse").trim() || "Print Timelapse";
    var extension = filename && filename.indexOf(".") >= 0 ? filename.split(".").pop().toLowerCase() : "";
    var info = this._infoBundle && typeof this._infoBundle === "object" ? this._infoBundle : null;
    var playbackNotice = extension === "avi"
      ? '<div class="notice warning">This timelapse is still an AVI file. Playback may fail until Bambuddy finishes background MP4 conversion.</div>'
      : "";
    var statMarkup = info
      ? [
          this._viewerStatMarkup("Duration", this._formatSeconds(info.duration)),
          this._viewerStatMarkup("Resolution", info.width && info.height ? String(info.width) + " x " + String(info.height) : ""),
          this._viewerStatMarkup("Codec", info.codec || ""),
          this._viewerStatMarkup("FPS", info.fps ? String(info.fps) : ""),
        ].join("")
      : "";
    var rateMarkup = timelapseUrl
      ? '<div class="rate-row"><div class="rate-label">Playback Speed</div><div class="rate-buttons">'
        + [0.5, 1, 1.5, 2].map(function (rate) {
          var active = Number(this._playbackRate) === Number(rate);
          return '<button class="rate-button' + (active ? ' active' : '') + '" type="button" data-rate="' + this._escapeHtml(String(rate)) + '" aria-pressed="' + (active ? 'true' : 'false') + '">' + this._escapeHtml(String(rate) + 'x') + '</button>';
        }.bind(this)).join("")
        + '</div></div>'
      : "";
    var infoMarkup = this._infoLoading
      ? '<div class="notice info">Loading editor-friendly video metadata...</div>'
      : this._infoError
        ? '<div class="notice info">' + this._escapeHtml(this._infoError) + '</div>'
        : statMarkup
          ? '<div class="stats-grid">' + statMarkup + '</div>'
          : "";
    var content = !timelapseUrl
      ? '<div class="empty">No timelapse is attached to this archive.</div>'
      : '<div class="player-shell">'
        + '<video class="player" controls playsinline preload="metadata" src="' + this._escapeHtml(timelapseUrl) + '"></video>'
        + '<div class="meta-row"><div class="meta-copy"><div class="meta-title">' + this._escapeHtml(archiveName) + '</div>'
        + (filename ? '<div class="meta-file">' + this._escapeHtml(filename) + '</div>' : '')
        + '</div><a class="open-link" href="' + this._escapeHtml(timelapseUrl) + '" target="_blank" rel="noopener noreferrer">Open or Download</a></div>'
        + rateMarkup
        + infoMarkup
        + playbackNotice
        + '</div>';

    this.shadowRoot.innerHTML = ''
      + '<style>'
      + ':host{display:block;color:var(--primary-text-color);}'
      + 'ha-card{display:block;border-radius:18px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);box-shadow:none;overflow:hidden;}'
      + '.shell{display:flex;flex-direction:column;gap:14px;padding:16px;}'
      + '.heading{display:flex;align-items:center;justify-content:space-between;gap:12px;}'
      + '.title{font-size:12px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:var(--secondary-text-color);}'
      + '.player-shell{display:flex;flex-direction:column;gap:12px;}'
      + '.player{display:block;width:100%;max-height:min(72vh,720px);border-radius:16px;background:#050a13;outline:none;}'
      + '.meta-row{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;}'
      + '.meta-copy{display:flex;flex-direction:column;gap:4px;min-width:0;}'
      + '.meta-title{font-size:15px;font-weight:700;line-height:1.35;word-break:break-word;}'
      + '.meta-file{font-size:12px;line-height:1.45;color:var(--secondary-text-color);word-break:break-all;}'
      + '.open-link{display:inline-flex;align-items:center;justify-content:center;padding:10px 14px;border-radius:999px;border:1px solid rgba(96,165,250,0.28);background:rgba(30,64,175,0.18);color:var(--primary-text-color);font-size:12px;font-weight:700;text-decoration:none;white-space:nowrap;}'
      + '.open-link:hover,.open-link:focus-visible{background:rgba(30,64,175,0.28);border-color:rgba(96,165,250,0.42);outline:none;}'
      + '.rate-row{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;}'
      + '.rate-label{font-size:11px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:var(--secondary-text-color);}'
      + '.rate-buttons{display:flex;gap:8px;flex-wrap:wrap;}'
      + '.rate-button{border:1px solid rgba(255,255,255,0.12);background:rgba(255,255,255,0.04);color:var(--primary-text-color);padding:8px 10px;border-radius:999px;font-size:12px;font-weight:700;cursor:pointer;}'
      + '.rate-button.active{background:rgba(30,64,175,0.24);border-color:rgba(96,165,250,0.42);}'
      + '.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;}'
      + '.stat{padding:10px 12px;border-radius:14px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);}'
      + '.stat-label{font-size:11px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:var(--secondary-text-color);}'
      + '.stat-value{margin-top:4px;font-size:14px;font-weight:700;line-height:1.3;}'
      + '.empty,.notice{border-radius:14px;padding:12px 14px;font-size:13px;line-height:1.5;}'
      + '.empty{background:rgba(255,255,255,0.04);color:var(--secondary-text-color);}'
      + '.notice.warning{background:rgba(239,108,0,0.14);border:1px solid rgba(255,167,38,0.2);}'
      + '.notice.info{background:rgba(30,64,175,0.14);border:1px solid rgba(96,165,250,0.18);}'
      + '@media (max-width: 640px){.shell{padding:14px;}.player{max-height:56vh;}.meta-row{align-items:flex-start;}.open-link{width:100%;}}'
      + '</style>'
      + '<ha-card>'
      + '<div class="shell">'
      + '<div class="heading"><div class="title">' + this._escapeHtml(this._config.title || "Timelapse") + '</div></div>'
      + content
      + '</div>'
      + '</ha-card>';

    this._bindInteractions();
    if (timelapseUrl) {
      this._loadInfo(archive);
    }
  }
}

if (!customElements.get("print-history-timelapse-card")) {
  customElements.define("print-history-timelapse-card", PrintHistoryTimelapseCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some(function (card) { return card && card.type === "print-history-timelapse-card"; })) {
  window.customCards.push({
    type: "print-history-timelapse-card",
    name: "Print History Timelapse Card",
    description: "Play a Bambuddy archive timelapse with speed controls and metadata.",
  });
}