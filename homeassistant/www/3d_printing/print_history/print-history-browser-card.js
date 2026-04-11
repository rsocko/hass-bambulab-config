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
  }

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("click", this._boundClickHandler);
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
      ".grid.compact{grid-template-columns:repeat(auto-fit,minmax(320px,1fr));}" +
      ".grid.media{grid-template-columns:repeat(auto-fit,minmax(360px,1fr));}" +
      ".grid.detail{grid-template-columns:1fr;}" +
      ".card{position:relative;border:1px solid var(--divider-color);border-radius:22px;background:var(--ha-card-background,var(--card-background-color));overflow:hidden;cursor:pointer;transition:transform .14s ease, box-shadow .14s ease;}" +
      ".card:hover{transform:translateY(-1px);box-shadow:0 8px 24px rgba(15,23,42,0.12);}" +
      ".card-shell{display:grid;gap:16px;padding:18px;min-width:0;}" +
      ".card-shell.compact{grid-template-columns:minmax(0,1fr);min-height:260px;}" +
      ".card-shell.media,.card-shell.detail{grid-template-columns:minmax(148px,188px) minmax(0,1fr);align-items:start;}" +
      ".card-shell.media.no-image,.card-shell.detail.no-image{grid-template-columns:minmax(0,1fr);}" +
      ".thumb-wrap{width:100%;min-width:0;}" +
      ".thumb{width:100%;height:132px;object-fit:cover;border-radius:16px;display:block;background:rgba(15,23,42,0.18);}" +
      ".thumb.compact{height:180px;object-fit:contain;padding:6px;background:rgba(255,255,255,0.04);}" +
      ".content{display:flex;flex-direction:column;gap:10px;min-width:0;}" +
      ".header{display:flex;gap:10px;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;min-width:0;}" +
      ".name{font-size:18px;font-weight:700;line-height:1.2;overflow-wrap:anywhere;word-break:break-word;}" +
      ".subtle{font-size:12px;color:var(--secondary-text-color);overflow-wrap:anywhere;}" +
      ".chip-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;min-width:0;}" +
      ".chip{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:999px;background:rgba(255,255,255,0.05);color:var(--primary-text-color);font-size:11px;font-weight:600;line-height:1.2;min-width:0;max-width:100%;overflow-wrap:anywhere;}" +
      ".status-chip{color:#fff;font-weight:700;}" +
      ".metrics{display:grid;gap:10px;}" +
      ".metrics.compact{grid-template-columns:repeat(3,minmax(0,1fr));}" +
      ".metrics.detail{grid-template-columns:repeat(auto-fit,minmax(116px,1fr));}" +
      ".metric{padding:10px 12px;border-radius:16px;background:rgba(255,255,255,0.04);min-width:0;}" +
      ".metric-label{font-size:11px;color:var(--secondary-text-color);line-height:1.2;margin-bottom:4px;}" +
      ".metric-value{font-size:15px;font-weight:700;line-height:1.2;overflow-wrap:anywhere;}" +
      ".dots,.tags{display:flex;gap:6px;flex-wrap:wrap;align-items:center;}" +
      ".dot{width:14px;height:14px;border-radius:999px;box-shadow:inset 0 0 0 1px rgba(255,255,255,0.25);}" +
      ".tag{border-radius:999px;padding:3px 8px;font-size:10px;box-shadow:inset 0 0 0 1px rgba(36,50,66,0.14);color:#243242;}" +
      ".favorite{position:absolute;top:16px;right:16px;width:30px;height:30px;border:none;border-radius:999px;background:rgba(255,255,255,0.06);color:var(--secondary-text-color);cursor:pointer;display:flex;align-items:center;justify-content:center;z-index:2;}" +
      ".favorite.active{background:rgba(245,194,66,0.18);color:#f5c242;}" +
      ".failure{font-size:12px;color:#ffb4ab;line-height:1.4;overflow-wrap:anywhere;}" +
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
      enrichmentStatus: this._stateValue("input_select.print_history_filter_enrichment_status"),
      material: this._stateValue("input_select.print_history_filter_material"),
      printer: this._stateValue("input_select.print_history_filter_printer"),
      dateRange: this._stateValue("input_select.print_history_filter_date_range"),
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
      filteredUpdated: this._entityUpdated(this._config.filtered_entity),
      pageInfoUpdated: this._entityUpdated(this._config.page_info_entity),
      browserStatusUpdated: this._entityUpdated(this._config.browser_status_entity),
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

  _entityUpdated(entityId) {
    var entity = this._hass && this._hass.states ? this._hass.states[entityId] : null;
    return entity ? String(entity.last_updated || entity.last_changed || "") : "";
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
      enrichment_status: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_enrichment_status")),
      material: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_material")),
      printer: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_printer")),
      date_range: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_date_range")),
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
    var tags = normalized.userTags.slice(0, variant === "Detail" ? 6 : variant === "Media" ? 4 : 3);
    var hiddenTagCount = Math.max(0, normalized.userTags.length - tags.length);
    var chips = [];
    if (variant !== "Compact") {
      chips.push(this._renderInfoChip(normalized.metadata || "No additional metadata"));
    }
    if (variant === "Detail" && normalized.facts.length) {
      chips = chips.concat(normalized.facts.map(this._renderInfoChip.bind(this)));
    }

    return "" +
      '<article class="card" data-action="open" data-archive="' + archiveJson + '">' +
      '<button class="favorite' + (normalized.isFavorite ? ' active' : '') + '" data-action="favorite" data-archive-id="' + this._escapeAttribute(String(normalized.id || "")) + '" data-archive="' + archiveJson + '" aria-label="Toggle favorite">' +
      '<ha-icon icon="' + (normalized.isFavorite ? 'mdi:star' : 'mdi:star-outline') + '"></ha-icon>' +
      '</button>' +
      '<div class="card-shell ' + variant.toLowerCase() + (hasImage ? '' : ' no-image') + '">' +
      (hasImage ? '<div class="thumb-wrap"><img class="thumb ' + (variant === "Compact" ? 'compact' : '') + '" src="' + this._escapeAttribute(normalized.thumbnailUrl(baseUrl)) + '" alt="' + this._escapeAttribute(normalized.printName) + '"></div>' : '') +
      '<div class="content">' +
      '<div class="header">' +
      '<div style="min-width:0;flex:1 1 220px;max-width:100%;">' +
      '<div class="name">' + this._escapeHtml(normalized.printName) + '</div>' +
      '<div class="subtle">' + this._escapeHtml(normalized.startedLabel) + '</div>' +
      '</div>' +
      '<div class="chip status-chip" style="background:' + this._escapeAttribute(normalized.statusColor) + ';">' + this._escapeHtml(normalized.statusIcon + ' ' + normalized.statusLabel) + '</div>' +
      '</div>' +
      '<div class="chip-row">' +
      '<span class="chip">' + this._escapeHtml(normalized.archiveIdLabel) + '</span>' +
      (normalized.printerLabel ? '<span class="chip">' + this._escapeHtml(normalized.printerLabel) + '</span>' : '') +
      '<span class="chip" style="background:' + this._escapeAttribute(normalized.enrichmentColor) + ';color:#fff;">Enrichment ' + this._escapeHtml(normalized.enrichmentLabel) + '</span>' +
      '</div>' +
      (chips.length ? '<div class="chip-row">' + chips.join("") + '</div>' : '') +
      '<div class="metrics ' + (variant === "Compact" ? 'compact' : 'detail') + '">' +
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
      (normalized.failureReason ? '<div class="failure">' + this._escapeHtml(normalized.failureReason) + '</div>' : '') +
      '</div>' +
      '</div>' +
      '</article>';
  }

  _renderMetric(label, value) {
    return '<div class="metric"><div class="metric-label">' + this._escapeHtml(label) + '</div><div class="metric-value">' + this._escapeHtml(value) + '</div></div>';
  }

  _renderInfoChip(label) {
    return '<span class="chip">' + this._escapeHtml(label) + '</span>';
  }

  _normalizeArchive(archive) {
    var notesInfo = this._splitArchiveNotes(archive.notes);
    var enrichmentPayload = notesInfo.payload;
    var enrichmentRows = Array.isArray(enrichmentPayload && enrichmentPayload.F) ? enrichmentPayload.F : [];
    var enrichmentCode = String(archive.enrichment_status || (enrichmentPayload && enrichmentPayload.s) || "").toLowerCase();
    var enrichmentStatus = ({ c: "complete", p: "partial", u: "unavailable" })[enrichmentCode] || (enrichmentRows.length ? "partial" : "unavailable");
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
    var facts = [
      printerLabel ? "Printer: " + printerLabel : "",
      archive.filament_type ? String(archive.filament_type) : "",
      archive.layer_height ? String(archive.layer_height) + "mm layer" : "",
      archive.nozzle_diameter ? String(archive.nozzle_diameter) + "mm nozzle" : "",
      archive.object_count ? String(archive.object_count) + " object" + (Number(archive.object_count) === 1 ? "" : "s") : "",
      archive.designer ? "Designer: " + String(archive.designer) : "",
    ].filter(Boolean);
    var status = this._normalizeStatus(archive.status);

    return {
      id: archive.id,
      archive: archive,
      isFavorite: !!archive.is_favorite,
      printName: archive.print_name ? String(archive.print_name) : "Unnamed",
      startedLabel: this._formatDate(archive.started_at || archive.created_at),
      statusLabel: status === "completed" ? "Completed" : status === "failed" ? "Failed" : status === "cancelled" ? "Cancelled" : status === "printing" ? "Printing" : "Unknown",
      statusColor: status === "completed" ? "#2E7D32" : status === "failed" ? "#C62828" : status === "cancelled" ? "#EF6C00" : status === "printing" ? "#1565C0" : "#546E7A",
      statusIcon: status === "completed" ? "✅" : status === "failed" ? "❌" : status === "cancelled" ? "⛔" : status === "printing" ? "🖨️" : "⏳",
      enrichmentLabel: enrichmentStatus.charAt(0).toUpperCase() + enrichmentStatus.slice(1),
      enrichmentColor: enrichmentStatus === "complete" ? "#2E7D32" : enrichmentStatus === "partial" ? "#EF6C00" : "#546E7A",
      durationLabel: this._formatDuration(archive.actual_time_seconds != null ? archive.actual_time_seconds : archive.print_time_seconds),
      filamentLabel: this._formatNumber(archive.filament_used_grams, 1, "g"),
      costLabel: this._formatCurrency(archive.cost),
      objectLabel: String(archive.object_count || 1),
      archiveIdLabel: archive.id != null && archive.id !== "" ? ("Archive #" + archive.id) : "Archive unavailable",
      printerLabel: printerLabel,
      metadata: metadata,
      facts: facts,
      filamentChips: filamentChips,
      userTags: this._userTags(archive.tags),
      failureReason: archive.failure_reason ? String(archive.failure_reason) : "",
      thumbnailUrl: function (baseUrl) {
        return baseUrl && archive.id != null ? baseUrl + "/api/v1/archives/" + encodeURIComponent(String(archive.id)) + "/thumbnail" : "";
      },
    };
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
    if (!value) {
      return "Unknown";
    }
    var raw = String(value);
    var normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(raw) ? raw : (raw + "Z");
    var parsed = new Date(normalized);
    if (Number.isNaN(parsed.getTime())) {
      return "Unknown";
    }
    return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
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

    if (action === "open") {
      await this._openArchivePopup(archive);
    }
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
        triggers_update: ["sensor.print_history_popup_archive_detail"],
        variables: {
          archive_json: archiveJson,
        },
        tap_action: { action: "none" },
        hold_action: { action: "none" },
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
        columns: archiveStatus === "printing" ? 3 : 4,
        square: false,
        cards: [
          ...(archiveStatus === "printing" ? [] : [this._buildPopupActionButton(
            "Re-Enrich",
            "mdi:refresh-circle",
            "rgba(46,125,50,0.18)",
            { action: "call-service", service: "script.reenrich_print_history_archive", data: { archive_id: String(archiveId) } }
          )]),
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