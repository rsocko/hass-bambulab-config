class PrintHistoryTimelapseCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._lastRenderSignature = "";
  }

  setConfig(config) {
    this._config = {
      archive_json: config && config.archive_json ? config.archive_json : "{}",
      detail_entity: config && config.detail_entity ? config.detail_entity : "",
      api_base_entity: config && config.api_base_entity ? config.api_base_entity : "input_text.bambuddy_api_base_url",
      title: config && config.title ? config.title : "Timelapse",
    };
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
      typeof this._config.archive_json === "string"
        ? this._config.archive_json
        : JSON.stringify(this._config.archive_json || {}),
      detailState ? String(detailState.state || "") : "",
      detailState ? String(detailState.last_updated || detailState.last_changed || "") : "",
      baseState ? String(baseState.state || "") : "",
      baseState ? String(baseState.last_updated || baseState.last_changed || "") : "",
    ].join("|");
  }

  _resolveArchive() {
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

  _getBaseUrl() {
    var entityId = this._config ? this._config.api_base_entity : "input_text.bambuddy_api_base_url";
    var raw = this._hass && this._hass.states && this._hass.states[entityId]
      ? this._hass.states[entityId].state
      : "";
    return String(raw || "").replace(/\/$/, "");
  }

  _timelapsePath(archive) {
    return String(archive && archive.timelapse_path || "").trim();
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
    });
    return baseUrl + "/api/v1/archives/" + encodeURIComponent(archiveId) + "/timelapse?v=" + encodeURIComponent(cacheKey);
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
    var playbackNotice = extension === "avi"
      ? '<div class="notice warning">This timelapse is still an AVI file. Playback may fail until Bambuddy finishes background MP4 conversion.</div>'
      : "";
    var content = !timelapseUrl
      ? '<div class="empty">No timelapse is attached to this archive.</div>'
      : '<div class="player-shell">'
        + '<video class="player" controls playsinline preload="metadata" src="' + this._escapeHtml(timelapseUrl) + '"></video>'
        + '<div class="meta-row"><div class="meta-copy"><div class="meta-title">' + this._escapeHtml(archiveName) + '</div>'
        + (filename ? '<div class="meta-file">' + this._escapeHtml(filename) + '</div>' : '')
        + '</div><a class="open-link" href="' + this._escapeHtml(timelapseUrl) + '" target="_blank" rel="noopener noreferrer">Open in new tab</a></div>'
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
      + '.empty,.notice{border-radius:14px;padding:12px 14px;font-size:13px;line-height:1.5;}'
      + '.empty{background:rgba(255,255,255,0.04);color:var(--secondary-text-color);}'
      + '.notice.warning{background:rgba(239,108,0,0.14);border:1px solid rgba(255,167,38,0.2);}'
      + '@media (max-width: 640px){.shell{padding:14px;}.player{max-height:56vh;}.meta-row{align-items:flex-start;}.open-link{width:100%;}}'
      + '</style>'
      + '<ha-card>'
      + '<div class="shell">'
      + '<div class="heading"><div class="title">' + this._escapeHtml(this._config.title || "Timelapse") + '</div></div>'
      + content
      + '</div>'
      + '</ha-card>';
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
    description: "Play a Bambuddy archive timelapse in a popup.",
  });
}