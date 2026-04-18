class PrintHistoryBrowserCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._querySignature = "";
    this._viewSignature = "";
    this._queryToken = 0;
    this._refreshTimer = null;
    this._loading = false;
    this._error = "";
    this._response = { archives: [], query: {} };
    this._debugStats = {
      scheduledRefreshes: 0,
      executedRefreshes: 0,
      coalescedRefreshes: 0,
    };
    this._boundClickHandler = this._handleClick.bind(this);
    this._boundKeydownHandler = this._handleKeydown.bind(this);
  }

  setConfig(config) {
    this._config = {
      title: config && config.title ? config.title : "Print History",
      hide_title: !!(config && config.hide_title),
      show_empty_state: !config || config.show_empty_state !== false,
      variant_entity: config && config.variant_entity ? config.variant_entity : "input_select.print_history_card_variant",
      show_images_entity: config && config.show_images_entity ? config.show_images_entity : "input_boolean.print_history_show_images",
      page_entity: config && config.page_entity ? config.page_entity : "input_number.history_current_page",
      page_size_entity: config && config.page_size_entity ? config.page_size_entity : "input_number.print_history_page_size",
      api_base_entity: config && config.api_base_entity ? config.api_base_entity : "input_text.bambuddy_api_base_url",
      browser_status_entity: config && config.browser_status_entity ? config.browser_status_entity : "sensor.bambuddy_print_history_browser_status",
      filtered_entity: config && config.filtered_entity ? config.filtered_entity : "sensor.bambuddy_print_history_browser_filtered",
      page_info_entity: config && config.page_info_entity ? config.page_info_entity : "sensor.bambuddy_print_history_browser_page_info",
    };
    this._querySignature = "";
    this._viewSignature = "";
    this._renderShell();
    this._queueRefresh();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) {
      return;
    }

    var nextQuerySignature = this._buildQuerySignature(hass);
    var nextViewSignature = this._buildViewSignature(hass);

    if (nextQuerySignature !== this._querySignature) {
      this._querySignature = nextQuerySignature;
      this._queueRefresh();
      return;
    }

    if (nextViewSignature !== this._viewSignature) {
      this._viewSignature = nextViewSignature;
      this._renderBody();
    }
  }

  connectedCallback() {
    this.shadowRoot.addEventListener("click", this._boundClickHandler);
    this.shadowRoot.addEventListener("keydown", this._boundKeydownHandler);
  }

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("click", this._boundClickHandler);
    this.shadowRoot.removeEventListener("keydown", this._boundKeydownHandler);
    if (this._refreshTimer) {
      clearTimeout(this._refreshTimer);
      this._refreshTimer = null;
    }
  }

  getCardSize() {
    return 10;
  }

  _renderShell() {
    this.shadowRoot.innerHTML = "" +
      "<style>" +
      "ha-card{padding:14px 14px 16px;}" +
      ".title{font-size:1rem;font-weight:700;margin:0 0 12px;}" +
      ".status{padding:18px;border-radius:18px;background:rgba(148,163,184,0.12);color:var(--secondary-text-color);line-height:1.5;}" +
      ".status.error{color:var(--error-color);}" +
      ".grid{display:grid;gap:16px;}" +
      ".grid.compact{grid-template-columns:repeat(auto-fit,minmax(360px,1fr));}" +
      ".grid.media{grid-template-columns:repeat(auto-fit,minmax(320px,1fr));}" +
      ".grid.detail{grid-template-columns:1fr;}" +
      ".card{position:relative;border:1px solid color-mix(in srgb, var(--divider-color) 78%, rgba(255,255,255,0.12));border-radius:22px;background:linear-gradient(180deg, color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 95%, rgba(255,255,255,0.04)), color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 99%, rgba(255,255,255,0.01)));overflow:hidden;cursor:pointer;transition:border-color .16s ease, box-shadow .16s ease, background .16s ease;}" +
      ".card::before{content:'';position:absolute;inset:0;border-radius:inherit;box-shadow:inset 0 0 0 1px rgba(255,255,255,0.08);opacity:0;transition:opacity .16s ease;pointer-events:none;}" +
      ".card::after{content:'';position:absolute;left:0;top:0;bottom:0;width:5px;opacity:0;transition:opacity .16s ease, background .16s ease;pointer-events:none;}" +
      ".card:hover,.card:focus-visible,.card:focus-within{border-color:color-mix(in srgb, var(--secondary-text-color) 22%, var(--divider-color));box-shadow:0 0 0 1px rgba(255,255,255,0.05), 0 10px 22px rgba(15,23,42,0.10);background:linear-gradient(180deg, color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 86%, rgba(148,163,184,0.18)), color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 92%, rgba(148,163,184,0.10)));}" +
      ".card:hover::before,.card:focus-visible::before,.card:focus-within::before{opacity:1;}" +
      ".card:active{box-shadow:0 0 0 1px rgba(255,255,255,0.06), 0 6px 14px rgba(15,23,42,0.10);background:linear-gradient(180deg, color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 82%, rgba(148,163,184,0.20)), color-mix(in srgb, var(--ha-card-background,var(--card-background-color)) 90%, rgba(148,163,184,0.12)));}" +
      ".card:focus-visible{outline:none;}" +
      ".card.archive-error-warning::after{opacity:1;background:#EF6C00;}" +
      ".card.archive-error-error::after{opacity:1;background:#C62828;}" +
      ".card.duplicate-source{border-color:color-mix(in srgb, #1565C0 34%, var(--divider-color));}" +
      ".card.duplicate-source::after{opacity:1;background:#1565C0;}" +
      ".card.duplicate-copy{border-color:color-mix(in srgb, #00897B 34%, var(--divider-color));}" +
      ".card.duplicate-copy::after{opacity:1;background:#00897B;}" +
      ".card-shell{display:grid;gap:16px;padding:18px;min-width:0;}" +
      ".card-shell.compact,.card-shell.detail{grid-template-columns:minmax(148px,188px) minmax(0,1fr);align-items:start;}" +
      ".card-shell.compact.no-image,.card-shell.detail.no-image{grid-template-columns:minmax(0,1fr);}" +
      ".card-shell.compact{grid-template-columns:minmax(150px,188px) minmax(0,1fr);grid-template-areas:'thumb summary' 'name name' 'details details';column-gap:18px;row-gap:14px;align-items:start;}" +
      ".card-shell.compact.no-image{grid-template-columns:minmax(0,1fr);grid-template-areas:'summary' 'name' 'details';}" +
      ".card-shell.media{grid-template-columns:minmax(0,1fr);min-height:260px;}" +
      ".thumb-wrap{width:100%;min-width:0;}" +
      ".card-shell.compact .thumb-wrap{grid-area:thumb;align-self:start;}" +
      ".thumb{width:100%;height:132px;object-fit:cover;border-radius:16px;display:block;background:rgba(15,23,42,0.18);}" +
      ".thumb.media{height:180px;object-fit:contain;padding:6px;background:rgba(255,255,255,0.04);}" +
      ".card-shell.compact .thumb{height:136px;}" +
      ".content{display:flex;flex-direction:column;gap:10px;min-width:0;}" +
      ".content.compact-summary{grid-area:summary;gap:8px;align-self:start;}" +
      ".content.compact-name{grid-area:name;gap:6px;padding-top:2px;}" +
      ".content.compact-details{grid-area:details;gap:10px;min-width:0;}" +
      ".content-top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;min-width:0;}" +
      ".content-top.compact{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;column-gap:10px;min-width:0;}" +
      ".action-buttons{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex:0 0 auto;}" +
      ".action-buttons.compact-actions{width:100%;justify-content:flex-end;}" +
      ".compact-archive-id{font-size:12px;line-height:1.2;font-weight:700;color:var(--secondary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}" +
      ".role-emblem{display:inline-flex;align-items:center;gap:6px;margin:0 0 2px;padding:5px 10px;border-radius:999px;font-size:11px;font-weight:800;line-height:1.1;text-transform:uppercase;letter-spacing:0.05em;max-width:max-content;}" +
      ".role-emblem.source{background:rgba(21,101,192,0.14);color:#1565C0;}" +
      ".role-emblem.duplicate{background:rgba(0,137,123,0.16);color:#00897B;}" +
      ".header{display:flex;gap:10px;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;min-width:0;}" +
      ".header.compact{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;column-gap:12px;row-gap:8px;}" +
      ".name{font-size:18px;font-weight:700;line-height:1.2;overflow-wrap:anywhere;word-break:break-word;}" +
      ".name-note-inline{display:inline-flex;align-items:center;justify-content:center;vertical-align:middle;position:relative;top:-3px;margin-left:6px;color:var(--primary-color, var(--accent-color, #03a9f4));}" +
      ".name-note-inline ha-icon{--mdc-icon-size:14px;width:14px;height:14px;min-width:14px;min-height:14px;display:block;}" +
      ".card:hover .name,.card:focus-visible .name,.card:focus-within .name{text-decoration:underline;text-decoration-thickness:2px;text-decoration-color:color-mix(in srgb, var(--secondary-text-color) 40%, transparent);text-underline-offset:0.18em;}" +
      ".subtle{font-size:12px;color:var(--secondary-text-color);overflow-wrap:anywhere;}" +
      ".chip-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;min-width:0;}" +
      ".chip-row.compact-primary{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;column-gap:12px;row-gap:8px;}" +
      ".chip-row.compact-secondary{gap:6px;}" +
      ".chip-row.compact-status-line{display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-start;gap:6px 8px;min-width:0;}" +
      ".chip-row.compact-meta-line{justify-content:flex-start;align-items:center;gap:8px;}" +
      ".compact-date{font-size:12px;color:var(--secondary-text-color);font-weight:600;line-height:1.2;white-space:nowrap;flex:0 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;}" +
      ".color-enrichment-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;column-gap:12px;row-gap:8px;}" +
      ".color-enrichment-row .dots{min-width:0;}" +
      ".tag-project-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;column-gap:12px;row-gap:8px;min-width:0;}" +
      ".tag-project-row .tags{min-width:0;}" +
      ".tag-project-row .project-chip{justify-self:end;}" +
      ".chip{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:999px;background:rgba(255,255,255,0.05);color:var(--primary-text-color);font-size:11px;font-weight:600;line-height:1.2;min-width:0;max-width:100%;overflow-wrap:anywhere;}" +
      ".status-chip{color:#fff;font-weight:700;}" +
      ".archive-error-chip{color:#fff;font-weight:700;}" +
      ".chip.icon-chip{position:relative;display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;min-width:30px;padding:0;border-radius:999px;flex:0 0 auto;line-height:0;}" +
      ".chip.icon-chip ha-icon{--mdc-icon-size:15px;width:15px;height:15px;min-width:15px;min-height:15px;display:block;}" +
      ".icon-chip-badge{position:absolute;top:-3px;right:-3px;min-width:15px;height:15px;padding:0 4px;border-radius:999px;background:#1565C0;color:#fff;font-size:9px;font-weight:800;line-height:15px;text-align:center;box-sizing:border-box;}" +
      ".project-chip{display:inline-flex;align-items:center;border:1px solid var(--project-chip-color, rgba(255,255,255,0.14));background:var(--project-chip-background, rgba(255,255,255,0.05));color:var(--primary-text-color);padding:3px 8px;gap:4px;min-height:24px;height:24px;font-size:10px;max-width:min(100%,180px);line-height:1;box-sizing:border-box;overflow:hidden;}" +
      ".project-chip ha-icon{color:var(--project-chip-color, var(--primary-text-color));--mdc-icon-size:11px;width:11px;height:11px;min-width:11px;flex:0 0 11px;}" +
      ".project-chip span{display:block;min-width:0;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}" +
      ".metrics{display:grid;gap:10px;}" +
      ".metrics.media{grid-template-columns:repeat(3,minmax(0,1fr));}" +
      ".metrics.compact,.metrics.detail{grid-template-columns:repeat(auto-fit,minmax(116px,1fr));}" +
      ".metrics.compact-tight{grid-template-columns:repeat(3,minmax(0,1fr));}" +
      ".metric{padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.04);min-width:0;}" +
      ".card:hover .metric,.card:focus-visible .metric,.card:focus-within .metric{background:color-mix(in srgb, rgba(148,163,184,0.16) 100%, rgba(255,255,255,0.04));}" +
      ".metric-label{font-size:11px;color:var(--secondary-text-color);line-height:1.2;margin-bottom:4px;}" +
      ".metric-value{font-size:15px;font-weight:700;line-height:1.2;overflow-wrap:anywhere;}" +
      ".dots,.tags{display:flex;gap:6px;flex-wrap:wrap;align-items:center;}" +
      ".dot{width:14px;height:14px;border-radius:999px;box-shadow:inset 0 0 0 1px rgba(255,255,255,0.25);}" +
      ".tag{border-radius:999px;padding:3px 8px;font-size:10px;box-shadow:inset 0 0 0 1px rgba(36,50,66,0.14);color:#243242;}" +
      ".icon-action{position:static;width:30px;height:30px;border:none;border-radius:999px;background:rgba(255,255,255,0.06);color:var(--secondary-text-color);cursor:pointer;display:flex;align-items:center;justify-content:center;z-index:2;flex:0 0 auto;}" +
      ".icon-action.viewer{background:rgba(0,137,123,0.16);color:#7dd3c8;}" +
      ".favorite.active{background:rgba(245,194,66,0.18);color:#f5c242;}" +
      ".archive-error-text{font-size:12px;line-height:1.45;overflow-wrap:anywhere;}" +
      ".archive-error-text.warning{color:#FFD89B;}" +
      ".archive-error-text.error{color:#FFB4AB;}" +
      ".failure{font-size:12px;color:#ffb4ab;line-height:1.4;overflow-wrap:anywhere;}" +
      "@media (max-width: 760px){.card-shell.compact{grid-template-columns:minmax(132px,164px) minmax(0,1fr);}.header.compact,.chip-row.compact-primary,.tag-project-row{grid-template-columns:minmax(0,1fr);}.metrics.compact-tight{grid-template-columns:repeat(auto-fit,minmax(102px,1fr));}.tag-project-row .project-chip{justify-self:start;}}" +
      "@media (max-width: 560px){.card-shell.compact{grid-template-columns:1fr;grid-template-areas:'summary' 'thumb' 'name' 'details';}.card-shell.compact .thumb{max-width:188px;}.content-top.compact{grid-template-columns:minmax(0,1fr);row-gap:8px;}.action-buttons.compact-actions{justify-content:flex-start;}.tag-project-row .project-chip{max-width:100%;}}" +
      "</style>" +
      "<ha-card>" +
      (this._config && this._config.hide_title ? "" : '<div class="title"></div>') +
      '<div id="body" class="status">Loading print history…</div>' +
      "</ha-card>";

    var titleNode = this.shadowRoot.querySelector(".title");
    if (titleNode && this._config) {
      titleNode.textContent = this._config.title;
    }
  }

  _buildQuerySignature(hass) {
    return JSON.stringify({
      status: this._stateValue("input_select.print_history_filter_status"),
      archiveError: this._stateValue("input_select.print_history_filter_archive_error"),
      enrichmentStatus: this._stateValue("input_select.print_history_filter_enrichment_status"),
      material: this._stateValue("input_select.print_history_filter_material"),
      printer: this._stateValue("input_select.print_history_filter_printer"),
      dateRange: this._stateValue("input_select.print_history_filter_date_range"),
      startDate: this._stateValue("input_text.print_history_filter_start_date"),
      endDate: this._stateValue("input_text.print_history_filter_end_date"),
      designer: this._stateValue("input_select.print_history_filter_designer"),
      project: this._stateValue("input_select.print_history_filter_project"),
      layerHeight: this._stateValue("input_select.print_history_filter_layer_height"),
      tag: this._stateValue("input_select.print_history_filter_tag"),
      favoritesOnly: this._stateValue("input_boolean.print_history_filter_favorites_only"),
      search: this._stateValue("input_text.print_history_search"),
      colors: this._stateValue("input_text.print_history_filter_colors"),
      sort: this._stateValue("input_select.print_history_sort"),
      page: this._stateValue(this._config.page_entity),
      pageSize: this._stateValue(this._config.page_size_entity),
      filteredRevision: this._entityAttribute(this._config.filtered_entity, "browser_revision"),
      pageInfoRevision: this._entityAttribute(this._config.page_info_entity, "browser_revision"),
    });
  }

  _buildViewSignature() {
    return JSON.stringify({
      variant: this._variant(),
      showImages: this._showImages(),
      apiBase: this._apiBaseUrl(),
      count: Array.isArray(this._response.archives) ? this._response.archives.length : 0,
      error: this._error,
      loading: this._loading,
    });
  }

  _entityAttribute(entityId, attribute) {
    var entity = this._hass && this._hass.states ? this._hass.states[entityId] : null;
    return entity && entity.attributes ? String(entity.attributes[attribute] || "") : "";
  }

  _stateValue(entityId) {
    var entity = this._hass && this._hass.states ? this._hass.states[entityId] : null;
    return entity ? entity.state : "";
  }

  _queueRefresh() {
    if (!this._hass || !this._config) {
      return;
    }
    this._debugStats.scheduledRefreshes += 1;
    if (this._refreshTimer) {
      this._debugStats.coalescedRefreshes += 1;
      clearTimeout(this._refreshTimer);
    }
    this._loading = true;
    this._error = "";
    this._renderBody();
    this._refreshTimer = setTimeout(function () {
      this._refreshTimer = null;
      this._debugStats.executedRefreshes += 1;
      this._refreshData();
    }.bind(this), 180);
  }

  async _refreshData() {
    var token = ++this._queryToken;
    var started = typeof performance !== "undefined" && typeof performance.now === "function" ? performance.now() : Date.now();
    try {
      var response = await this._hass.callWS(this._buildQueryPayload());
      if (token !== this._queryToken) {
        return;
      }
      this._response = response && typeof response === "object" ? response : { archives: [], query: {} };
      this._error = "";
      this._recordDebug("browser", response, started);
    } catch (error) {
      if (token !== this._queryToken) {
        return;
      }
      this._response = { archives: [], query: {} };
      this._error = error && error.message ? error.message : String(error);
      this._recordDebug("browser_error", { error: this._error }, started);
    }
    this._loading = false;
    this._viewSignature = this._buildViewSignature(this._hass);
    this._renderBody();
  }

  _debugEnabled() {
    return this._stateValue("input_boolean.print_history_debug_instrumentation") === "on";
  }

  _recordDebug(channel, response, started) {
    if (!this._debugEnabled()) {
      return;
    }
    var ended = typeof performance !== "undefined" && typeof performance.now === "function" ? performance.now() : Date.now();
    var payload = {
      at: new Date().toISOString(),
      channel: channel,
      roundTripMs: Math.round((ended - started) * 10) / 10,
      pageItemCount: Array.isArray(this._response.archives) ? this._response.archives.length : 0,
      filteredCount: this._response && this._response.query ? this._response.query.filtered_count : null,
      scheduledRefreshes: this._debugStats.scheduledRefreshes,
      executedRefreshes: this._debugStats.executedRefreshes,
      coalescedRefreshes: this._debugStats.coalescedRefreshes,
      backend: response && response.debug ? response.debug : null,
      store: response && response.store ? response.store : null,
      error: response && response.error ? response.error : null,
    };
    window.__printHistoryDebug = window.__printHistoryDebug || { events: [], latest: {} };
    window.__printHistoryDebug.events.push(payload);
    if (window.__printHistoryDebug.events.length > 100) {
      window.__printHistoryDebug.events.shift();
    }
    window.__printHistoryDebug.latest[channel] = payload;
    if (typeof console !== "undefined" && typeof console.debug === "function") {
      console.debug("[print-history-debug]", payload);
    }
  }

  _buildQueryPayload() {
    return {
      type: "bambuddy/print_history_query",
      status: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_status")),
      archive_error: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_archive_error")),
      enrichment_status: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_enrichment_status")),
      material: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_material")),
      printer: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_printer")),
      date_range: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_date_range")),
      start_date: String(this._stateValue("input_text.print_history_filter_start_date") || "").trim(),
      end_date: String(this._stateValue("input_text.print_history_filter_end_date") || "").trim(),
      designer: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_designer")),
      project: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_project")),
      layer_height: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_layer_height")),
      tag: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_tag")),
      favorites_only: this._stateValue("input_boolean.print_history_filter_favorites_only") === "on",
      search: String(this._stateValue("input_text.print_history_search") || "").trim(),
      colors: String(this._stateValue("input_text.print_history_filter_colors") || "").trim(),
      sort: this._normalizeFilterValue(this._stateValue("input_select.print_history_sort")),
      page: Math.max(1, Number(this._stateValue(this._config.page_entity) || 1)),
      page_size: Math.max(1, Number(this._stateValue(this._config.page_size_entity) || 1)),
    };
  }

  _normalizeFilterValue(value) {
    var normalized = String(value || "").trim();
    if (!normalized || normalized === "All") {
      return "";
    }
    return normalized;
  }

  _variant() {
    var value = String(this._stateValue(this._config.variant_entity) || "Compact");
    return ["Compact", "Media", "Detail"].indexOf(value) >= 0 ? value : "Compact";
  }

  _showImages() {
    return this._stateValue(this._config.show_images_entity) !== "off";
  }

  _apiBaseUrl() {
    return String(this._stateValue(this._config.api_base_entity) || "").replace(/\/$/, "");
  }

  _renderBody() {
    var body = this.shadowRoot.getElementById("body");
    if (!body) {
      return;
    }

    if (this._loading) {
      body.className = "status";
      body.textContent = "Loading print history…";
      return;
    }

    if (this._error) {
      body.className = "status error";
      body.textContent = this._error;
      return;
    }

    var archives = Array.isArray(this._response.archives) ? this._response.archives : [];
    if (!archives.length && this._config.show_empty_state) {
      body.className = "status";
      body.textContent = "No matching archives. Adjust filters or refresh the archive cache.";
      return;
    }

    var variant = this._variant();
    var variantClass = variant.toLowerCase();
    body.className = "grid " + variantClass;
    body.innerHTML = archives.map(this._renderArchiveCard.bind(this, variant)).join("");
  }

  _renderArchiveCard(variant, archive) {
    var normalized = this._normalizeArchive(archive || {});
    var showImages = this._showImages();
    var baseUrl = this._apiBaseUrl();
    var hasImage = showImages && !!normalized.thumbnailUrl(baseUrl);
    var archiveJson = this._escapeAttribute(JSON.stringify(archive || {}));
    var tags = normalized.userTags.slice(0, variant === "Detail" ? 6 : variant === "Media" ? 4 : 6);
    var hiddenTagCount = Math.max(0, normalized.userTags.length - tags.length);
    var chips = [];
    if (variant !== "Compact") {
      chips.push(this._renderInfoChip(normalized.metadata || "No additional metadata"));
    }
    if (variant === "Detail" && normalized.facts.length) {
      chips = chips.concat(normalized.facts.map(this._renderInfoChip.bind(this)));
    }
    var cardClass = "card" + (normalized.roleClass ? (" " + normalized.roleClass) : "") + (normalized.hasArchiveError ? (" archive-error archive-error-" + normalized.archiveErrorSeverity) : "");
    var statusChip = '<div class="chip status-chip" style="background:' + this._escapeAttribute(normalized.statusColor) + ';">' + this._escapeHtml(normalized.statusIcon + ' ' + normalized.statusLabel) + '</div>';
    var projectChip = normalized.projectLabel
      ? '<span class="chip project-chip" style="--project-chip-color:' + this._escapeAttribute(normalized.projectColor) + ';--project-chip-background:' + this._escapeAttribute(normalized.projectBackground) + ';" title="' + this._escapeAttribute('Project: ' + normalized.projectLabel) + '"><ha-icon icon="mdi:folder-outline"></ha-icon><span>' + this._escapeHtml(normalized.projectLabel) + '</span></span>'
      : '';
    var compactArchiveId = normalized.compactArchiveIdLabel ? '<span class="compact-archive-id">' + this._escapeHtml(normalized.compactArchiveIdLabel) + '</span>' : '';
    var compactNoteInline = normalized.noteText
      ? '<span class="name-note-inline" title="' + this._escapeAttribute(normalized.noteText) + '"><ha-icon icon="mdi:note-text-outline"></ha-icon></span>'
      : '';
    var photoAction = normalized.photoCount > 0
      ? '<span class="chip icon-chip" title="' + this._escapeAttribute(normalized.photoCountLabel) + '"><ha-icon icon="mdi:image-multiple-outline"></ha-icon><span class="icon-chip-badge">' + this._escapeHtml(String(normalized.photoCount)) + '</span></span>'
      : '';
    var primaryChipRow = variant === 'Compact'
      ? '<div class="chip-row compact-secondary compact-meta-line">'
        + (normalized.hasArchiveError ? '<span class="chip archive-error-chip" style="background:' + this._escapeAttribute(normalized.archiveErrorColor) + ';">' + this._escapeHtml(normalized.archiveErrorIcon + ' ' + normalized.archiveErrorLabel) + '</span>' : '')
        + (normalized.printerLabel ? '<span class="chip">' + this._escapeHtml(normalized.printerLabel) + '</span>' : '')
        + (normalized.duplicateChipLabel ? '<span class="chip" title="' + this._escapeAttribute(normalized.duplicateTooltip) + '" style="background:' + this._escapeAttribute(normalized.duplicateChipColor) + ';color:#fff;">' + this._escapeHtml(normalized.duplicateChipLabel) + '</span>' : '')
        + '</div>'
      : '<div class="chip-row">'
        + (normalized.hasArchiveError ? '<span class="chip archive-error-chip" style="background:' + this._escapeAttribute(normalized.archiveErrorColor) + ';">' + this._escapeHtml(normalized.archiveErrorIcon + ' ' + normalized.archiveErrorLabel) + '</span>' : '')
        + '<span class="chip">' + this._escapeHtml(normalized.archiveIdLabel) + '</span>'
        + (normalized.printerLabel ? '<span class="chip">' + this._escapeHtml(normalized.printerLabel) + '</span>' : '')
        + (normalized.duplicateChipLabel ? '<span class="chip" title="' + this._escapeAttribute(normalized.duplicateTooltip) + '" style="background:' + this._escapeAttribute(normalized.duplicateChipColor) + ';color:#fff;">' + this._escapeHtml(normalized.duplicateChipLabel) + '</span>' : '')
        + '<span class="chip" style="background:' + this._escapeAttribute(normalized.enrichmentColor) + ';color:#fff;">Enrichment ' + this._escapeHtml(normalized.enrichmentLabel) + '</span>'
        + '</div>';
    var metricsClass = variant === 'Media' ? 'media' : (variant === 'Compact' ? 'compact-tight' : 'detail');

    var summaryContent = '' +
      '<div class="content compact-summary">' +
        '<div class="content-top compact">' +
        compactArchiveId +
        '<div class="action-buttons compact-actions">' +
        '<button class="icon-action viewer" data-action="viewer" data-archive="' + archiveJson + '" aria-label="Open 3D viewer for ' + this._escapeAttribute(normalized.printName) + '">' +
        '<ha-icon icon="mdi:cube-scan"></ha-icon>' +
        '</button>' +
        '<button class="icon-action favorite' + (normalized.isFavorite ? ' active' : '') + '" data-action="favorite" data-archive-id="' + this._escapeAttribute(String(normalized.id || "")) + '" data-archive="' + archiveJson + '" aria-label="Toggle favorite">' +
        '<ha-icon icon="' + (normalized.isFavorite ? 'mdi:star' : 'mdi:star-outline') + '"></ha-icon>' +
        '</button>' +
        photoAction +
        '</div>' +
        '</div>' +
      '<div class="chip-row compact-status-line">' +
      '<span class="compact-date">' + this._escapeHtml(normalized.startedLabel) + '</span>' +
      statusChip +
      '</div>' +
      primaryChipRow +
      '</div>';
    var compactNameContent = variant === 'Compact'
      ? '<div class="content compact-name">'
        + (normalized.roleEmblemLabel ? '<div class="role-emblem ' + this._escapeAttribute(normalized.roleEmblemClass) + '">' + this._escapeHtml(normalized.roleEmblemLabel) + '</div>' : '')
        + '<div class="name">' + this._escapeHtml(normalized.printName) + compactNoteInline + '</div>'
        + '</div>'
      : '';
    var detailContent = '' +
      '<div class="content compact-details">' +
      '<div class="metrics ' + metricsClass + '">' +
      this._renderMetric('Duration', normalized.durationLabel) +
      this._renderMetric('Filament', normalized.filamentLabel) +
      this._renderMetric('Cost', normalized.costLabel) +
      '</div>' +
      (normalized.filamentChips.length
        ? '<div class="color-enrichment-row"><div class="dots">' + normalized.filamentChips.slice(0, 6).map(function (chip) {
          return '<span class="dot" title="' + this._escapeAttribute(chip.tooltip) + '" style="background:' + this._escapeAttribute(chip.dotColor) + ';"></span>';
        }.bind(this)).join("") + '</div><span class="chip" style="background:' + this._escapeAttribute(normalized.enrichmentColor) + ';color:#fff;">Enrichment ' + this._escapeHtml(normalized.enrichmentLabel) + '</span></div>'
        : '<div class="chip-row" style="justify-content:flex-end;"><span class="chip" style="background:' + this._escapeAttribute(normalized.enrichmentColor) + ';color:#fff;">Enrichment ' + this._escapeHtml(normalized.enrichmentLabel) + '</span></div>') +
      ((tags.length || hiddenTagCount || projectChip) ? '<div class="tag-project-row">'
        + ((tags.length || hiddenTagCount) ? '<div class="tags">' + tags.map(function (tag) {
          return '<span class="tag" style="background:' + this._escapeAttribute(this._tagColor(tag)) + ';">' + this._escapeHtml(tag) + '</span>';
        }.bind(this)).join("") + (hiddenTagCount ? '<span class="chip">… +' + hiddenTagCount + '</span>' : '') + '</div>' : '<div></div>')
        + projectChip
        + '</div>' : '') +
      (normalized.hasArchiveError ? '<div class="archive-error-text ' + this._escapeAttribute(normalized.archiveErrorSeverity) + '">' + this._escapeHtml(normalized.archiveErrorSummary) + '</div>' : '') +
      (normalized.failureReason ? '<div class="failure">' + this._escapeHtml(normalized.failureReason) + '</div>' : '') +
      '</div>';

    if (variant !== 'Compact') {
      summaryContent = '' +
        '<div class="content">' +
          '<div class="content-top">' +
          '<span></span>' +
          '<div class="action-buttons">' +
          '<button class="icon-action viewer" data-action="viewer" data-archive="' + archiveJson + '" aria-label="Open 3D viewer for ' + this._escapeAttribute(normalized.printName) + '">' +
          '<ha-icon icon="mdi:cube-scan"></ha-icon>' +
          '</button>' +
          '<button class="icon-action favorite' + (normalized.isFavorite ? ' active' : '') + '" data-action="favorite" data-archive-id="' + this._escapeAttribute(String(normalized.id || "")) + '" data-archive="' + archiveJson + '" aria-label="Toggle favorite">' +
          '<ha-icon icon="' + (normalized.isFavorite ? 'mdi:star' : 'mdi:star-outline') + '"></ha-icon>' +
          '</button>' +
          '</div>' +
          '</div>' +
          (normalized.roleEmblemLabel ? '<div class="role-emblem ' + this._escapeAttribute(normalized.roleEmblemClass) + '">' + this._escapeHtml(normalized.roleEmblemLabel) + '</div>' : '') +
        '<div class="header">' +
        '<div style="min-width:0;flex:1 1 220px;max-width:100%;">' +
        '<div class="name">' + this._escapeHtml(normalized.printName) + '</div>' +
        '<div class="subtle">' + this._escapeHtml(normalized.startedLabel) + '</div>' +
        '</div>' +
        statusChip +
        '</div>' +
        primaryChipRow +
        (chips.length ? '<div class="chip-row">' + chips.join("") + '</div>' : '') +
        '<div class="metrics ' + metricsClass + '">' +
        this._renderMetric('Duration', normalized.durationLabel) +
        this._renderMetric('Filament', normalized.filamentLabel) +
        this._renderMetric('Cost', normalized.costLabel) +
        (variant === "Detail" ? this._renderMetric('Objects', normalized.objectLabel) : '') +
        '</div>' +
        (normalized.filamentChips.length ? '<div class="dots">' + normalized.filamentChips.slice(0, 6).map(function (chip) {
          return '<span class="dot" title="' + this._escapeAttribute(chip.tooltip) + '" style="background:' + this._escapeAttribute(chip.dotColor) + ';"></span>';
        }.bind(this)).join("") + '</div>' : '') +
        ((tags.length || hiddenTagCount) ? '<div class="tags">' + tags.map(function (tag) {
          return '<span class="tag" style="background:' + this._escapeAttribute(this._tagColor(tag)) + ';">' + this._escapeHtml(tag) + '</span>';
        }.bind(this)).join("") + (hiddenTagCount ? '<span class="chip">… +' + hiddenTagCount + '</span>' : '') + '</div>' : '') +
        (normalized.hasArchiveError ? '<div class="archive-error-text ' + this._escapeAttribute(normalized.archiveErrorSeverity) + '">' + this._escapeHtml(normalized.archiveErrorSummary) + '</div>' : '') +
        (normalized.failureReason ? '<div class="failure">' + this._escapeHtml(normalized.failureReason) + '</div>' : '') +
        '</div>';
      detailContent = '';
    }

    return "" +
      '<article class="' + cardClass + '" tabindex="0" role="button" data-action="open" data-archive="' + archiveJson + '" aria-label="Open details for ' + this._escapeAttribute(normalized.printName) + '">' +
      '<div class="card-shell ' + variant.toLowerCase() + (hasImage ? '' : ' no-image') + '">' +
      (hasImage ? '<div class="thumb-wrap"><img class="thumb ' + (variant === "Media" ? 'media' : '') + '" src="' + this._escapeAttribute(normalized.thumbnailUrl(baseUrl)) + '" alt="' + this._escapeAttribute(normalized.printName) + '"></div>' : '') +
      summaryContent +
      compactNameContent +
      detailContent +
      '</article>';
  }

  _renderMetric(label, value) {
    return '<div class="metric"><div class="metric-label">' + this._escapeHtml(label) + '</div><div class="metric-value">' + this._escapeHtml(value) + '</div></div>';
  }

  _renderInfoChip(label) {
    return '<span class="chip">' + this._escapeHtml(label) + '</span>';
  }

  _duplicateSummary(archive) {
    var archiveId = Math.max(0, Number(archive && archive.id || 0));
    var duplicateCount = Math.max(0, Number(archive && archive.duplicate_count || 0));
    var duplicateSequence = Math.max(0, Number(archive && archive.duplicate_sequence || 0));
    var originalArchiveId = Math.max(0, Number(archive && archive.original_archive_id || 0));
    var isSource = duplicateSequence === 0 && originalArchiveId > 0 && originalArchiveId === archiveId;
    var isDuplicate = !isSource && (originalArchiveId > 0 || duplicateSequence > 0);
    var isOriginal = duplicateCount > 0 && (isSource || !isDuplicate);
    var groupSize = duplicateCount > 0 ? (duplicateCount + 1) : 0;

    if (isDuplicate) {
      var duplicatePosition = groupSize > 0 ? Math.min(groupSize, Math.max(1, duplicateSequence + 1)) : Math.max(1, duplicateSequence + 1);
      var duplicateLabel = originalArchiveId > 0 ? ('Dup of #' + originalArchiveId) : (groupSize > 1 ? ('Duplicate ' + duplicatePosition + '/' + groupSize) : 'Duplicate');
      var duplicateTooltip = originalArchiveId > 0
        ? ('Duplicate copy derived from original archive #' + originalArchiveId)
        : 'Duplicate archive in a shared print set';
      return {
        chipLabel: duplicateLabel,
        chipColor: '#00897B',
        tooltip: duplicateTooltip,
        roleClass: 'duplicate-copy',
        roleEmblemLabel: 'Duplicate',
        roleEmblemClass: 'duplicate',
      };
    }

    if (isOriginal) {
      return {
        chipLabel: groupSize > 1 ? ('Source · ' + groupSize + ' prints') : 'Source',
        chipColor: '#1565C0',
        tooltip: groupSize > 1
          ? ('Original source archive for a duplicate set of ' + groupSize + ' prints')
          : 'Original source archive in a duplicate set',
        roleClass: 'duplicate-source',
        roleEmblemLabel: 'Source',
        roleEmblemClass: 'source',
      };
    }

    return {
      chipLabel: '',
      chipColor: '',
      tooltip: '',
      roleClass: '',
      roleEmblemLabel: '',
      roleEmblemClass: '',
    };
  }

  _normalizeArchive(archive) {
    var notesInfo = this._splitArchiveNotes(archive.notes);
    var enrichmentPayload = notesInfo.payload;
    var enrichmentRows = Array.isArray(enrichmentPayload && enrichmentPayload.F) ? enrichmentPayload.F : [];
    var enrichmentStatus = this._normalizeEnrichmentStatus(archive.enrichment_status || (enrichmentPayload && enrichmentPayload.s), enrichmentRows);
    var colors = String(archive.filament_color || "").split(",").map(this._normalizeHex).filter(Boolean);
    var filamentChips = enrichmentRows.length ? enrichmentRows.map(function (item, index) {
      var name = String(item && item.n || "").trim() || ("Filament " + (index + 1));
      var tray = String(item && item.t || "").trim();
      var hex = this._normalizeHex(item && item.h) || "rgba(255,255,255,0.2)";
      var ambiguity = this._describeEnrichmentAmbiguity(item && item.am);
      return {
        dotColor: hex,
        tooltip: [tray ? name + " (" + tray + ")" : name, this._normalizeHex(item && item.h), ambiguity].filter(Boolean).join(" | ") || name,
      };
    }.bind(this)) : colors.map(function (hex) {
      return { dotColor: hex, tooltip: hex };
    });
    var metadata = [archive.filament_type || "Unknown material", archive.layer_height ? String(archive.layer_height) + "mm" : "", archive.designer || ""].filter(Boolean).join(" · ");
    var printerLabel = archive.printer_name ? String(archive.printer_name) : (archive.printer_id != null && archive.printer_id !== "" ? ("Printer " + String(archive.printer_id)) : "");
    var duplicateSummary = this._duplicateSummary(archive);
    var facts = [
      printerLabel ? "Printer: " + printerLabel : "",
      archive.filament_type ? String(archive.filament_type) : "",
      archive.layer_height ? String(archive.layer_height) + "mm layer" : "",
      archive.nozzle_diameter ? String(archive.nozzle_diameter) + "mm nozzle" : "",
      archive.object_count ? String(archive.object_count) + " object" + (Number(archive.object_count) === 1 ? "" : "s") : "",
      archive.designer ? "Designer: " + String(archive.designer) : "",
    ].filter(Boolean);
    var status = this._normalizeStatus(archive.status);
    var archiveError = this._normalizeArchiveError(archive);

    return {
      id: archive.id,
      archive: archive,
      isFavorite: !!archive.is_favorite,
      printName: archive.print_name ? String(archive.print_name) : "Unnamed",
      startedLabel: this._formatDate(archive.started_at || archive.created_at),
      statusLabel: status === "completed" ? "Completed" : status === "archived" ? "Archived" : status === "failed" ? "Failed" : status === "cancelled" ? "Cancelled" : status === "printing" ? "Printing" : "Unknown",
      statusColor: status === "completed" ? "#2E7D32" : status === "archived" ? "#546E7A" : status === "failed" ? "#C62828" : status === "cancelled" ? "#EF6C00" : status === "printing" ? "#1565C0" : "#546E7A",
      statusIcon: status === "completed" ? "✅" : status === "archived" ? "📦" : status === "failed" ? "❌" : status === "cancelled" ? "⛔" : status === "printing" ? "🖨️" : "⏳",
      enrichmentLabel: enrichmentStatus.charAt(0).toUpperCase() + enrichmentStatus.slice(1),
      enrichmentColor: enrichmentStatus === "complete" ? "#2E7D32" : enrichmentStatus === "partial" ? "#EF6C00" : "#546E7A",
      durationLabel: this._formatDuration(
        archive.effective_duration_seconds != null
          ? archive.effective_duration_seconds
          : (archive.actual_time_seconds != null ? archive.actual_time_seconds : archive.print_time_seconds)
      ),
      filamentLabel: this._formatNumber(archive.filament_used_grams, 1, "g"),
      costLabel: this._formatCurrency(archive.cost),
      objectLabel: String(archive.object_count || 1),
      archiveIdLabel: archive.id != null && archive.id !== "" ? ("Archive #" + archive.id) : "Archive unavailable",
      compactArchiveIdLabel: archive.id != null && archive.id !== "" ? ("#" + archive.id) : "",
      printerLabel: printerLabel,
      duplicateChipLabel: duplicateSummary.chipLabel,
      duplicateChipColor: duplicateSummary.chipColor,
      duplicateTooltip: duplicateSummary.tooltip,
      roleClass: duplicateSummary.roleClass,
      roleEmblemLabel: duplicateSummary.roleEmblemLabel,
      roleEmblemClass: duplicateSummary.roleEmblemClass,
      metadata: metadata,
      facts: facts,
      filamentChips: filamentChips,
      projectLabel: archive.project_name ? String(archive.project_name).trim() : "",
      projectColor: this._projectColorForArchive(archive),
      projectBackground: this._projectBackgroundColorForArchive(archive),
      userTags: this._userTags(archive.tags),
      noteText: this._userNoteText(notesInfo.userNotes),
      photoCount: this._archivePhotoCount(archive),
      photoCountLabel: this._photoCountLabel(this._archivePhotoCount(archive)),
      hasArchiveError: archiveError.hasArchiveError,
      archiveErrorLabel: archiveError.label,
      archiveErrorSeverity: archiveError.severity,
      archiveErrorColor: archiveError.color,
      archiveErrorIcon: archiveError.icon,
      archiveErrorSummary: archiveError.summary,
      failureReason: archive.failure_reason ? String(archive.failure_reason) : "",
      thumbnailUrl: function (baseUrl) {
        var primaryPhotoPath = String(archive.primary_photo_path || "").trim();
        if (baseUrl && archive.id != null && primaryPhotoPath) {
          return baseUrl + "/api/v1/archives/" + encodeURIComponent(String(archive.id)) + "/photos/" + encodeURIComponent(primaryPhotoPath);
        }
        return baseUrl && archive.id != null && String(archive.thumbnail_path || "").trim()
          ? baseUrl + "/api/v1/archives/" + encodeURIComponent(String(archive.id)) + "/thumbnail"
          : "";
      },
    };
  }

  _normalizeArchiveError(archive) {
    var filePath = String(archive && archive.file_path || "").trim();
    var thumbnailPath = String(archive && archive.thumbnail_path || "").trim();
    var primaryPhotoPath = String(archive && archive.primary_photo_path || "").trim();
    var previewPath = primaryPhotoPath || thumbnailPath;
    var source3mfPath = String(archive && archive.source_3mf_path || "").trim();
    var missingCore3mf = !!(archive && archive.missing_core_3mf);
    var missingThumbnail = !!(archive && archive.missing_thumbnail);
    var hasSourceOnly = !!(archive && archive.has_source_only);
    var hasProjectedArchiveState = !!(archive && (
      Object.prototype.hasOwnProperty.call(archive, "has_archive_error") ||
      Object.prototype.hasOwnProperty.call(archive, "missing_core_3mf") ||
      Object.prototype.hasOwnProperty.call(archive, "missing_thumbnail") ||
      Object.prototype.hasOwnProperty.call(archive, "has_source_only")
    ));

    if (!hasProjectedArchiveState && !missingCore3mf && !missingThumbnail) {
      missingCore3mf = !!(archive && archive.no_3mf_available) || !filePath;
      hasSourceOnly = missingCore3mf && !!source3mfPath;
      missingThumbnail = !missingCore3mf && !previewPath;
    }

    if (hasSourceOnly) {
      return {
        hasArchiveError: true,
        severity: "error",
        label: String(archive && archive.archive_error_label || "Source 3MF Only"),
        summary: String(archive && archive.archive_error_summary || "Primary archive missing; source 3MF is attached separately."),
        color: "#C62828",
        icon: "⚠️",
      };
    }
    if (missingCore3mf) {
      return {
        hasArchiveError: true,
        severity: "error",
        label: String(archive && archive.archive_error_label || "Archive Incomplete"),
        summary: String(archive && archive.archive_error_summary || "Primary archived 3MF is missing and needs repair."),
        color: "#C62828",
        icon: "⚠️",
      };
    }
    if (missingThumbnail) {
      return {
        hasArchiveError: true,
        severity: "warning",
        label: String(archive && archive.archive_error_label || "Thumbnail Missing"),
        summary: String(archive && archive.archive_error_summary || "Preview image is unavailable for this archive."),
        color: "#EF6C00",
        icon: "⚠️",
      };
    }
    return {
      hasArchiveError: false,
      severity: "",
      label: "",
      summary: "",
      color: "",
      icon: "",
    };
  }

  _projectColorForArchive(archive) {
    var projectId = archive && archive.project_id != null ? String(archive.project_id).trim() : "";
    var projectName = archive && archive.project_name != null ? String(archive.project_name).trim().toLowerCase() : "";
    if (!projectId) {
      if (!projectName) {
        return "rgba(255,255,255,0.14)";
      }
    }
    var catalog = this._popupProjectCatalog();
    for (var index = 0; index < catalog.length; index += 1) {
      var option = catalog[index] || {};
      var optionId = String(option.id || "").trim();
      var optionName = String(option.name || "").trim().toLowerCase();
      if ((projectId && optionId === projectId) || (!projectId && projectName && optionName === projectName)) {
        return this._normalizeHex(option.color) || "rgba(255,255,255,0.14)";
      }
    }
    return "rgba(255,255,255,0.14)";
  }

  _projectBackgroundColorForArchive(archive) {
    return this._withAlpha(this._projectColorForArchive(archive), 0.18);
  }

  _withAlpha(color, alpha) {
    var normalized = this._normalizeHex(color);
    if (!normalized) {
      return "rgba(255,255,255,0.05)";
    }
    var red = parseInt(normalized.slice(1, 3), 16);
    var green = parseInt(normalized.slice(3, 5), 16);
    var blue = parseInt(normalized.slice(5, 7), 16);
    return "rgba(" + red + "," + green + "," + blue + "," + alpha + ")";
  }

  _userNoteText(value) {
    var text = String(value || "").trim();
    if (!text || /^system\b/i.test(text)) {
      return "";
    }
    return text;
  }

  _photoCountLabel(value) {
    var count = Math.max(0, Number(value || 0));
    if (!count) {
      return "";
    }
    return String(count) + " photo" + (count === 1 ? "" : "s");
  }

  _archivePhotoCount(archive) {
    var explicitCount = Number(archive && archive.photo_count);
    if (Number.isFinite(explicitCount) && explicitCount > 0) {
      return Math.max(0, Math.round(explicitCount));
    }
    return Array.isArray(archive && archive.photos) ? archive.photos.length : 0;
  }

  _userTags(value) {
    var systemTagPrefixes = ["f:", "s:", "spoolman:", "vendor:", "material:", "cost:", "status:", "ha enrichment:", "ha_enrichment:"];
    var systemTagValues = ["ha_enriched:true"];
    return String(value || "")
      .split(",")
      .map(function (entry) { return entry.trim(); })
      .filter(Boolean)
      .filter(function (tag) {
        var normalized = tag.toLowerCase();
        return systemTagValues.indexOf(normalized) === -1 && !systemTagPrefixes.some(function (prefix) {
          return normalized.indexOf(prefix) === 0;
        });
      });
  }

  _normalizeStatus(status) {
    var raw = String(status || "").toLowerCase();
    if (raw === "completed" || raw === "success") {
      return "completed";
    }
    if (raw === "archived") {
      return "archived";
    }
    if (raw === "cancelled" || raw === "aborted" || raw === "stopped") {
      return "cancelled";
    }
    return raw;
  }

  _normalizeHex(value) {
    var raw = String(value || "").trim().replace(/^#/, "").replace(/"/g, "");
    if (!raw) {
      return "";
    }
    var trimmed = raw.length === 8 ? raw.slice(0, 6) : raw;
    return /^[0-9a-fA-F]{6}$/.test(trimmed) ? ("#" + trimmed.toUpperCase()) : "";
  }

  _describeEnrichmentAmbiguity(value) {
    var normalized = String(value || "").trim();
    return ({
      a_tc: "Multiple archived AMS trays matched type+color",
      a_fb: "Multiple archived AMS trays matched archive-level fallback",
      s_uuid: "Multiple Spoolman spools matched archived tray UUID",
      s_tc: "Multiple Spoolman spools matched type+color",
    })[normalized] || normalized;
  }

  _normalizeEnrichmentStatus(statusValue, enrichmentRows) {
    var normalized = String(statusValue || "").trim().toLowerCase();
    var mapped = ({
      c: "complete",
      complete: "complete",
      p: "partial",
      partial: "partial",
      u: "unavailable",
      unavailable: "unavailable",
    })[normalized] || "";
    if (mapped === "complete" || mapped === "partial") {
      return mapped;
    }
    if (mapped === "unavailable") {
      return Array.isArray(enrichmentRows) && enrichmentRows.length ? "partial" : "unavailable";
    }
    if (!Array.isArray(enrichmentRows) || !enrichmentRows.length) {
      return "unavailable";
    }
    return enrichmentRows.some(function (item) {
      return !String(item && item.t || "").trim()
        || !this._hasResolvedEntityId(item && item.s)
        || !this._hasResolvedEntityId(item && item.f)
        || String(item && (item.am || item.a) || "").trim();
    }.bind(this)) ? "partial" : "complete";
  }

  _hasResolvedEntityId(value) {
    if (value === null || value === undefined) {
      return false;
    }
    var normalized = String(value).trim().toLowerCase();
    return normalized !== "" && normalized !== "null" && normalized !== "none";
  }

  _splitArchiveNotes(value) {
    var raw = String(value || "");
    var markerIndex = raw.indexOf("+>");
    var recoveryIndex = raw.indexOf("[RECOVERY_AUDIT_V1]");
    var indexes = [markerIndex, recoveryIndex].filter(function (index) { return index >= 0; });
    if (!indexes.length) {
      return { userNotes: raw.trimEnd(), payload: null };
    }
    var cutoff = Math.min.apply(null, indexes);
    var userNotes = raw.slice(0, cutoff).replace(/\n+$/u, "");
    var payloadRaw = markerIndex >= 0 ? raw.slice(markerIndex + 2).trim() : "";
    try {
      return { userNotes: userNotes, payload: payloadRaw ? JSON.parse(payloadRaw) : null };
    } catch (_error) {
      return { userNotes: userNotes, payload: null };
    }
  }

  _formatDate(value) {
    var parsed = this._parseDate(value);
    if (!parsed) {
      return "Unknown";
    }
    var formatOptions = {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZone: this._haTimeZone(),
    };
    if (this._dateYear(parsed) !== this._dateYear(new Date())) {
      formatOptions.year = "numeric";
    }
    return new Intl.DateTimeFormat(undefined, formatOptions).format(parsed);
  }

  _parseDate(value) {
    if (!value) {
      return null;
    }
    var raw = String(value);
    var normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(raw) ? raw : (raw + "Z");
    var parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  _dateYear(value) {
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      timeZone: this._haTimeZone(),
    }).format(value);
  }

  _haTimeZone() {
    return this._hass && this._hass.config && this._hass.config.time_zone
      ? String(this._hass.config.time_zone)
      : undefined;
  }

  _formatDuration(secondsValue) {
    var seconds = Number(secondsValue || 0);
    if (!seconds) {
      return "-";
    }
    if (seconds >= 3600) {
      return String(Math.round((seconds / 3600) * 10) / 10) + "h";
    }
    return String(Math.round(seconds / 60)) + "m";
  }

  _formatNumber(value, digits, suffix) {
    var numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      return "-";
    }
    return numeric.toFixed(digits).replace(/\.0$/, "") + suffix;
  }

  _formatCurrency(value) {
    var numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      return "-";
    }
    return "$" + numeric.toFixed(2);
  }

  _tagColor(tag) {
    var helper = window.PrintHistoryTagColors;
    return helper && typeof helper.colorForTag === "function" ? helper.colorForTag(tag) : "#86EFAC";
  }

  _statusEntityAttributes() {
    var state = this._hass && this._hass.states ? this._hass.states["sensor.bambuddy_print_history_browser_status"] : null;
    return state && state.attributes ? state.attributes : {};
  }

  _resolvedEntryId() {
    var attributes = this._statusEntityAttributes();
    return attributes && attributes.entry_id ? String(attributes.entry_id).trim() : "";
  }

  _buildArchiveViewerCardConfig(archive) {
    return {
      type: "custom:print-history-3d-viewer-card",
      archive_id: archive && archive.id != null ? String(archive.id) : "",
      archive_name: archive && archive.print_name ? String(archive.print_name) : "",
      entry_id: this._resolvedEntryId(),
      bambuddy_base: this._apiBaseUrl(),
    };
  }

  _buildArchiveViewerPopupContent(archive) {
    return {
      type: "vertical-stack",
      cards: [this._buildArchiveViewerCardConfig(archive)],
    };
  }

  _openArchiveViewerPopup(archive) {
    if (!archive || archive.id == null) {
      return;
    }
    var archiveName = archive.print_name || ("Archive " + archive.id);
    this._fireBrowserModEvent("browser_mod.popup", {
      title: "3D View · " + archiveName,
      size: "wide",
      content: this._buildArchiveViewerPopupContent(archive),
    });
  }

  _popupProjectCatalog() {
    var attributes = this._statusEntityAttributes();
    return Array.isArray(attributes.project_options) ? attributes.project_options : [];
  }

  _popupProjectLabel(projectId, projectName) {
    var projectIdText = projectId == null ? "" : String(projectId).trim();
    var projectNameText = projectName == null ? "" : String(projectName).trim();
    var catalog = this._popupProjectCatalog();
    for (var index = 0; index < catalog.length; index += 1) {
      var option = catalog[index] || {};
      if (String(option.id || "").trim() === projectIdText && String(option.label || "").trim()) {
        return String(option.label).trim();
      }
    }
    if (projectNameText) {
      return projectIdText ? projectNameText + " [" + projectIdText + "]" : projectNameText;
    }
    if (projectIdText) {
      return "Project [" + projectIdText + "]";
    }
    return "No Project";
  }

  _popupProjectOptions(archive) {
    var labels = ["No Project"];
    var catalog = this._popupProjectCatalog();
    for (var index = 0; index < catalog.length; index += 1) {
      var label = catalog[index] && catalog[index].label ? String(catalog[index].label).trim() : "";
      if (label && labels.indexOf(label) === -1) {
        labels.push(label);
      }
    }
    var selected = this._popupProjectLabel(archive && archive.project_id, archive && archive.project_name);
    if (selected !== "No Project" && labels.indexOf(selected) === -1) {
      labels.push(selected);
    }
    return {
      options: labels,
      selected: selected,
    };
  }

  async _handleClick(event) {
    var actionNode = event.target && event.target.closest ? event.target.closest("[data-action]") : null;
    if (!actionNode) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();

    var action = actionNode.getAttribute("data-action");
    var rawArchive = actionNode.getAttribute("data-archive") || actionNode.closest("[data-archive]")?.getAttribute("data-archive") || "{}";
    var archive = this._parseJson(rawArchive, {});

    if (action === "favorite") {
      await this._toggleFavorite(archive);
      return;
    }

    if (action === "viewer") {
      this._openArchiveViewerPopup(archive);
      return;
    }

    if (action === "open") {
      await this._openArchivePopup(archive);
    }
  }

  async _handleKeydown(event) {
    if (!event || (event.key !== "Enter" && event.key !== " ")) {
      return;
    }
    var target = event.target || null;
    if (!target || target.closest("[data-action=\"favorite\"]")) {
      return;
    }
    var cardNode = target.closest ? target.closest('.card[data-action="open"]') : null;
    if (!cardNode || cardNode !== target) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    var archive = this._parseJson(cardNode.getAttribute("data-archive") || "{}", {});
    await this._openArchivePopup(archive);
  }

  async _toggleFavorite(archive) {
    if (!archive || archive.id == null || !this._hass) {
      return;
    }
    await this._hass.callService("script", "toggle_print_history_archive_favorite", {
      archive_id: String(archive.id),
    });
    var archives = Array.isArray(this._response.archives) ? this._response.archives.slice() : [];
    this._response.archives = archives.map(function (item) {
      if (String(item && item.id) !== String(archive.id)) {
        return item;
      }
      return Object.assign({}, item, { is_favorite: !item.is_favorite });
    });
    this._viewSignature = this._buildViewSignature(this._hass);
    this._renderBody();
  }

  _buildPopupActionButton(name, icon, background, tapAction) {
    return {
      type: "custom:button-card",
      name: name,
      icon: icon,
      show_name: true,
      show_icon: true,
      show_state: false,
      tap_action: tapAction,
      hold_action: { action: "none" },
      styles: {
        card: [
          { padding: "12px 10px" },
          { "border-radius": "16px" },
          { "box-shadow": "none" },
          { border: "1px solid rgba(255,255,255,0.08)" },
          { background: background },
        ],
        grid: [
          { "grid-template-areas": '"i" "n"' },
          { "grid-template-columns": "1fr" },
          { "justify-items": "center" },
          { gap: "6px" },
        ],
        icon: [
          { width: "22px" },
          { height: "22px" },
          { color: "var(--primary-text-color)" },
        ],
        name: [
          { "font-size": "12px" },
          { "font-weight": "600" },
          { color: "var(--primary-text-color)" },
        ],
      },
    };
  }

  async _openArchivePopup(archive) {
    if (!archive || archive.id == null || !this._hass) {
      return;
    }

    var archiveId = archive.id;
    var archiveName = archive.print_name || ("Archive " + archiveId);
    var archiveInfo = this._splitArchiveNotes(archive.notes);
    var archiveUserTags = this._userTags(archive.tags);
    var archiveStatus = this._normalizeStatus(archive.status || "completed");
    var archiveFailureReason = String(archive.failure_reason || "").trim();
    var projectPicker = this._popupProjectOptions(archive);
    var statusOptions = ["Completed", "Failed", "Cancelled", "Printing"];
    var archiveStatusOption = archiveStatus ? archiveStatus.charAt(0).toUpperCase() + archiveStatus.slice(1) : "Completed";
    if (statusOptions.indexOf(archiveStatusOption) === -1) {
      statusOptions.push(archiveStatusOption);
    }
    var failureReasonOptions = [
      "Unspecified",
      "Adhesion failure",
      "Spaghetti / Detached",
      "Layer shift",
      "Clogged nozzle",
      "Filament runout",
      "Warping",
      "Stringing",
      "Under-extrusion",
      "Power failure",
      "User cancelled",
      "Other",
    ];
    if (archiveFailureReason && failureReasonOptions.indexOf(archiveFailureReason) === -1) {
      failureReasonOptions.push(archiveFailureReason);
    }
    var editablePrintName = String(archive.print_name || "").slice(0, 255);
    var editableTags = archiveUserTags.join(", ").slice(0, 255);
    var editableNotes = String(archiveInfo.userNotes || "").slice(0, 255);
    var archiveJson = JSON.stringify(archive);
    var cards = [
      {
        type: "custom:print-history-photo-gallery-card",
        archive_json: archiveJson,
        detail_entity: "sensor.print_history_popup_archive_detail",
        api_base_entity: "input_text.bambuddy_api_base_url",
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
      {
        type: "custom:tabbed-card",
        options: {},
        tabs: [
          {
            card: {
              type: "custom:print-filament-breakdown-card",
              source: "archive",
              mode: "weight",
              archive_entity: "sensor.print_history_popup_archive_detail",
              archive_json: archiveJson,
              show_title: false,
              show_issues: true,
            },
            attributes: {
              label: "Print Weight",
              icon: "mdi:weight-gram",
            },
          },
          {
            card: {
              type: "custom:print-filament-breakdown-card",
              source: "archive",
              mode: "cost",
              archive_entity: "sensor.print_history_popup_archive_detail",
              archive_json: archiveJson,
              show_title: false,
              show_issues: false,
            },
            attributes: {
              label: "Print Cost",
              icon: "mdi:currency-usd",
            },
          },
        ],
      },
      {
        type: "custom:print-history-tag-editor-card",
        entity: "input_text.print_history_popup_tags",
        suggestions_entity: "input_select.print_history_filter_tag",
        title: "Tags",
        placeholder: "Add a tag and press Enter",
        helper: "Reuse an existing tag or create a new one. Press Enter or comma to add.",
      },
      {
        type: "entities",
        show_header_toggle: false,
        entities: [
          { entity: "input_text.print_history_popup_print_name", name: "Print Name", icon: "mdi:printer-3d" },
          { entity: "input_select.print_history_popup_project", name: "Project", icon: "mdi:folder-outline" },
          { entity: "input_select.print_history_popup_status", name: "Status", icon: "mdi:list-status" },
          {
            type: "conditional",
            conditions: [{
              condition: "or",
              conditions: [
                { condition: "state", entity: "input_select.print_history_popup_status", state: "Failed" },
                { condition: "state", entity: "input_select.print_history_popup_status", state: "Cancelled" },
              ],
            }],
            row: { entity: "input_select.print_history_popup_failure_reason", name: "Failure Reason", icon: "mdi:alert-circle-outline" },
          },
          { entity: "input_text.print_history_popup_notes", name: "Notes", icon: "mdi:text-box-outline" },
        ],
      },
      {
        type: "grid",
        columns: archiveStatus === "printing" ? 5 : 6,
        square: false,
        cards: [
          ...(archiveStatus === "printing" ? [] : [this._buildPopupActionButton(
            "Re-Enrich",
            "mdi:refresh-circle",
            "rgba(46,125,50,0.18)",
            { action: "call-service", service: "script.reenrich_print_history_archive", data: { archive_id: String(archiveId) } }
          )]),
          this._buildPopupActionButton(
            "3D View",
            "mdi:cube-scan",
            "rgba(0,137,123,0.18)",
            {
              action: "fire-dom-event",
              browser_mod: {
                service: "browser_mod.popup",
                data: {
                  title: "3D View · " + archiveName,
                  size: "wide",
                  content: this._buildArchiveViewerPopupContent(archive),
                },
              },
            }
          ),
          {
            type: "custom:button-card",
            template: "print_history_archive_popup_favorite_button",
            variables: { archive_json: archiveJson, archive_id: String(archiveId) },
          },
          this._buildPopupActionButton(
            "Save",
            "mdi:content-save-outline",
            "rgba(21,101,192,0.18)",
            { action: "call-service", service: "script.save_print_history_archive_popup_edits" }
          ),
          this._buildPopupActionButton(
            "Repair",
            "mdi:wrench-cog",
            "rgba(239,108,0,0.18)",
            {
              action: "fire-dom-event",
              browser_mod: {
                service: "browser_mod.sequence",
                data: {
                  sequence: [
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
                        source_archive_id: Number(archiveId),
                      },
                    },
                    {
                      service: "browser_mod.popup",
                      data: {
                        title: `Repair ${archiveName}`,
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
                },
              },
            }
          ),
          this._buildPopupActionButton(
            "Close",
            "mdi:close",
            "rgba(255,255,255,0.04)",
            { action: "fire-dom-event", browser_mod: { service: "browser_mod.close_popup" } }
          ),
        ],
      },
    ];

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
          service: "input_text.set_value",
          data: {
            entity_id: "input_text.print_history_popup_print_name",
            value: editablePrintName,
          },
        },
        {
          service: "input_text.set_value",
          data: {
            entity_id: "input_text.print_history_popup_tags",
            value: editableTags,
          },
        },
        {
          service: "input_text.set_value",
          data: {
            entity_id: "input_text.print_history_popup_notes",
            value: editableNotes,
          },
        },
        {
          service: "input_select.set_options",
          data: {
            entity_id: "input_select.print_history_popup_project",
            options: projectPicker.options,
          },
        },
        {
          service: "input_select.select_option",
          data: {
            entity_id: "input_select.print_history_popup_project",
            option: projectPicker.selected,
          },
        },
        {
          service: "input_select.set_options",
          data: {
            entity_id: "input_select.print_history_popup_status",
            options: statusOptions,
          },
        },
        {
          service: "input_select.select_option",
          data: {
            entity_id: "input_select.print_history_popup_status",
            option: archiveStatusOption,
          },
        },
        {
          service: "input_select.set_options",
          data: {
            entity_id: "input_select.print_history_popup_failure_reason",
            options: failureReasonOptions,
          },
        },
        {
          service: "input_select.select_option",
          data: {
            entity_id: "input_select.print_history_popup_failure_reason",
            option: archiveFailureReason || "Unspecified",
          },
        },
        {
          service: "browser_mod.popup",
          data: {
            title: archiveName,
            size: "normal",
            content: {
              type: "vertical-stack",
              cards: cards,
            },
          },
        },
      ],
    });
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

  _parseJson(value, fallback) {
    try {
      return JSON.parse(value || "{}");
    } catch (_error) {
      return fallback;
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

  _escapeAttribute(value) {
    return this._escapeHtml(value).replace(/`/g, "&#96;");
  }
}

customElements.define("print-history-browser-card", PrintHistoryBrowserCard);