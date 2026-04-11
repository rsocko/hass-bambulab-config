var printHistoryActivityReadyPromise = null;
var printHistoryActivityImportTried = false;

class PrintHistoryActivityHeatmapCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._chart = null;
    this._chartContainer = null;
    this._legendContainer = null;
    this._summaryContainer = null;
    this._detailsContainer = null;
    this._renderQueued = false;
    this._signature = "";
    this._resizeObserver = null;
    this._intersectionObserver = null;
    this._visibilityHandler = null;
    this._lastObservedWidth = 0;
    this._isHidden = false;
    this._suppressPointSelection = false;
    this._selectedOverlay = null;
    this._queryResponse = { activity_rows: [] };
    this._queryToken = 0;
    this._renderTimer = null;
    this._debugStats = {
      scheduledRenders: 0,
      executedRenders: 0,
      coalescedRenders: 0,
    };
  }

  setConfig(config) {
    if (!config) {
      throw new Error("print-history-activity-heatmap-card requires a config object");
    }

    this._config = {
      title: config.title || "Print History Activity",
      hide_title: config.hide_title === true,
      hide_summary: config.hide_summary === true,
      source_entity: config.source_entity || "",
      source_attribute: config.source_attribute || "",
      direct_query: config.direct_query !== false,
      mode_entity: config.mode_entity || "input_select.print_history_activity_metric",
      selected_date_entity: config.selected_date_entity || "input_text.print_history_activity_selected_date",
      show_details: config.show_details === true,
      api_base_entity: config.api_base_entity || "input_text.bambuddy_api_base_url",
      visibility_entity: config.visibility_entity || "",
      weeks: Math.max(12, Number(config.weeks || 52)),
      tablet_weeks: Math.max(12, Number(config.tablet_weeks || 32)),
      mobile_weeks: Math.max(12, Number(config.mobile_weeks || 20)),
      tablet_breakpoint: Math.max(480, Number(config.tablet_breakpoint || 960)),
      mobile_breakpoint: Math.max(320, Number(config.mobile_breakpoint || 640)),
      max_detail_items: Math.max(1, Number(config.max_detail_items || 12)),
      start_day: Number.isInteger(config.start_day) ? config.start_day : 0,
      day_labels: Array.isArray(config.day_labels) && config.day_labels.length === 7
        ? config.day_labels
        : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    };

    this._signature = "";
    this._renderShell();
    this._queueRender();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) {
      return;
    }

    var signature = JSON.stringify(this._buildSignature(hass));
    if (signature === this._signature) {
      return;
    }

    this._signature = signature;
    this._queueRender();
  }

  connectedCallback() {
    this._ensureResizeObserver();
    this._ensureVisibilityHooks();
    this._requestVisibilityRender();
  }

  disconnectedCallback() {
    if (this._resizeObserver) {
      this._resizeObserver.disconnect();
      this._resizeObserver = null;
    }
    if (this._intersectionObserver) {
      this._intersectionObserver.disconnect();
      this._intersectionObserver = null;
    }
    if (this._visibilityHandler) {
      window.removeEventListener("resize", this._visibilityHandler);
      window.removeEventListener("focus", this._visibilityHandler);
      window.removeEventListener("pageshow", this._visibilityHandler);
      window.removeEventListener("location-changed", this._visibilityHandler);
      document.removeEventListener("visibilitychange", this._visibilityHandler);
      this._visibilityHandler = null;
    }
    if (this._renderTimer) {
      clearTimeout(this._renderTimer);
      this._renderTimer = null;
    }
    if (this._chart && typeof this._chart.destroy === "function") {
      this._chart.destroy();
      this._chart = null;
    }
  }

  getCardSize() {
    return 10;
  }

  _buildSignature(hass) {
    var sourceState = this._config.source_entity ? hass.states[this._config.source_entity] : null;
    var metricState = hass.states[this._config.mode_entity];
    var selectedDateState = hass.states[this._config.selected_date_entity];
    var apiBaseState = hass.states[this._config.api_base_entity];
    var filteredState = hass.states["sensor.bambuddy_print_history_browser_filtered"];
    var pageInfoState = hass.states["sensor.bambuddy_print_history_browser_page_info"];

    return {
      sourceState: sourceState ? sourceState.state : "",
      sourceFetch: sourceState && sourceState.attributes ? sourceState.attributes.last_fetch || "" : "",
      filteredRevision: filteredState && filteredState.attributes ? String(filteredState.attributes.browser_revision || "") : "",
      pageInfoRevision: pageInfoState && pageInfoState.attributes ? String(pageInfoState.attributes.browser_revision || "") : "",
      metric: metricState ? metricState.state : "",
      selectedDate: selectedDateState ? selectedDateState.state : "",
      apiBase: apiBaseState ? apiBaseState.state : "",
      status: this._stateValue("input_select.print_history_filter_status"),
      material: this._stateValue("input_select.print_history_filter_material"),
      printer: this._stateValue("input_select.print_history_filter_printer"),
      dateRange: this._stateValue("input_select.print_history_filter_date_range"),
      designer: this._stateValue("input_select.print_history_filter_designer"),
      layerHeight: this._stateValue("input_select.print_history_filter_layer_height"),
      tag: this._stateValue("input_select.print_history_filter_tag"),
      sort: this._stateValue("input_select.print_history_sort"),
      favorites: this._stateValue("input_boolean.print_history_filter_favorites_only"),
      search: this._stateValue("input_text.print_history_search"),
      colors: this._stateValue("input_text.print_history_filter_colors"),
      visible: this._config.visibility_entity ? this._stateValue(this._config.visibility_entity) : "on",
      darkMode: !!(hass.themes && hass.themes.darkMode),
    };
  }

  _stateValue(entityId) {
    var entity = this._hass && this._hass.states ? this._hass.states[entityId] : null;
    return entity ? entity.state : "";
  }

  _renderShell() {
    this.shadowRoot.innerHTML =
      "<style>" +
      "ha-card{padding:6px 16px 10px;}" +
      ".title{font-size:1rem;font-weight:600;margin:0 0 4px 0;}" +
      ".chart-wrap{position:relative;min-height:var(--chart-min-height,300px);}" +
      ".heatmap{display:grid;grid-template-columns:40px minmax(0,1fr);column-gap:10px;align-items:start;background:var(--chart-gap-background,transparent);}" +
      ".month-row{display:grid;grid-template-columns:repeat(var(--week-count,53),minmax(var(--cell-size,10px),1fr));column-gap:4px;margin-bottom:6px;padding-right:2px;}" +
      ".month-spacer{height:14px;}" +
      ".month-label{font-size:11px;line-height:1;color:var(--secondary-text-color);min-height:14px;white-space:nowrap;overflow:hidden;}" +
      ".day-labels{display:grid;grid-template-rows:repeat(7,var(--cell-size,18px));row-gap:4px;padding-top:20px;}" +
      ".day-label{display:flex;align-items:center;justify-content:flex-end;font-size:11px;color:var(--secondary-text-color);padding-right:4px;}" +
      ".cells{display:grid;grid-template-rows:repeat(7,var(--cell-size,18px));row-gap:4px;}" +
      ".heatmap-row{display:grid;grid-template-columns:repeat(var(--week-count,53),minmax(var(--cell-size,10px),1fr));column-gap:4px;}" +
      ".cell{appearance:none;border:none;border-radius:0;height:var(--cell-size,18px);min-width:var(--cell-size,10px);padding:0;cursor:pointer;box-shadow:none;transition:transform .12s ease, box-shadow .12s ease, opacity .12s ease;background:var(--cell-empty,rgba(148,163,184,0.14));}" +
      ".cell:hover{transform:translateY(-1px);box-shadow:0 0 0 1px var(--cell-stroke-strong,rgba(148,163,184,0.26)),0 2px 6px rgba(15,23,42,0.18);}" +
      ".cell:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px;}" +
      ".cell.future{cursor:default;opacity:.72;}" +
      ".cell.selected{box-shadow:inset 0 0 0 2px rgba(15,23,42,0.85),0 0 0 2px var(--primary-background-color);}" +
      ".selected-cell-overlay{position:absolute;pointer-events:none;box-sizing:border-box;border:3px solid var(--primary-color);box-shadow:0 0 0 1px var(--annotation-outline-base,var(--card-background-color,#ffffff)),0 0 8px var(--annotation-outline-glow,rgba(59,130,246,0.45));z-index:4;display:none;}" +
      ".legend{display:flex;justify-content:flex-end;align-items:center;min-height:18px;margin-top:2px;}" +
      ".legend.hidden{display:none;}" +
      ".legend-scale{display:inline-flex;align-items:center;gap:8px;color:var(--secondary-text-color);font-size:12px;font-weight:500;}" +
      ".legend-swatches{display:inline-flex;align-items:center;gap:6px;}" +
      ".legend-swatch{width:14px;height:14px;border-radius:4px;background:var(--cell-empty,rgba(148,163,184,0.14));}" +
      ".legend-note{font-size:11px;color:var(--secondary-text-color);margin-left:10px;opacity:0.9;}" +
      ".summary{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;}" +
      ".chip{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;font-size:12px;font-weight:600;background:rgba(148,163,184,0.16);color:var(--primary-text-color);}" +
      ".details{margin-top:14px;}" +
      ".details-empty{padding:14px;border-radius:16px;background:rgba(148,163,184,0.12);color:var(--secondary-text-color);line-height:1.5;}" +
      ".detail-header{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;flex-wrap:wrap;margin-bottom:12px;}" +
      ".detail-title{font-size:0.98rem;font-weight:600;line-height:1.3;margin:0;}" +
      ".detail-subtitle{font-size:0.84rem;color:var(--secondary-text-color);line-height:1.4;margin-top:4px;}" +
      ".detail-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;}" +
      ".detail-card{display:grid;grid-template-columns:88px minmax(0,1fr);gap:12px;padding:12px;border-radius:18px;background:rgba(148,163,184,0.12);border:1px solid rgba(148,163,184,0.16);box-sizing:border-box;}" +
      ".thumb{width:88px;height:88px;border-radius:14px;object-fit:cover;background:rgba(15,23,42,0.24);display:block;}" +
      ".thumb-fallback{width:88px;height:88px;border-radius:14px;background:rgba(15,23,42,0.26);display:flex;align-items:center;justify-content:center;font-size:28px;}" +
      ".detail-body{min-width:0;display:flex;flex-direction:column;gap:8px;}" +
      ".detail-name{font-weight:700;line-height:1.25;overflow-wrap:anywhere;}" +
      ".detail-meta{font-size:12px;color:var(--secondary-text-color);line-height:1.45;overflow-wrap:anywhere;}" +
      ".detail-stats{display:flex;flex-wrap:wrap;gap:8px;font-size:12px;}" +
      ".status-pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:4px 10px;color:#fff;font-size:11px;font-weight:700;width:max-content;max-width:100%;}" +
      ".color-dots{display:flex;flex-wrap:wrap;gap:6px;}" +
      ".color-dot{width:12px;height:12px;border-radius:999px;box-shadow:inset 0 0 0 1px rgba(255,255,255,0.32);}" +
      ".error{color:var(--error-color);font-size:.9rem;line-height:1.4;padding:12px 0;}" +
      "</style>" +
      "<ha-card>" +
      (this._config.hide_title ? "" : ('<div class="title">' + this._escapeHtml(this._config.title) + "</div>")) +
      '<div id="chart" class="chart-wrap"></div>' +
      '<div id="legend" class="legend"></div>' +
      (this._config.hide_summary ? "" : '<div id="summary" class="summary"></div>') +
      (this._config.show_details ? '<div id="details" class="details"></div>' : "") +
      "</ha-card>";

    this._chartContainer = this.shadowRoot.getElementById("chart");
    this._legendContainer = this.shadowRoot.getElementById("legend");
    this._summaryContainer = this.shadowRoot.getElementById("summary");
    this._detailsContainer = this.shadowRoot.getElementById("details");
    this._ensureResizeObserver();
    this._ensureVisibilityHooks();
  }

  _ensureResizeObserver() {
    var self = this;
    if (this._resizeObserver || typeof ResizeObserver === "undefined" || !this._chartContainer) {
      return;
    }

    this._resizeObserver = new ResizeObserver(function (entries) {
      var entry = entries && entries[0] ? entries[0] : null;
      var width = entry && entry.contentRect ? Math.round(entry.contentRect.width) : 0;
      if (!width || Math.abs(width - self._lastObservedWidth) < 6) {
        return;
      }
      self._lastObservedWidth = width;
      self._queueRender();
    });

    this._resizeObserver.observe(this._chartContainer);
  }

  _ensureVisibilityHooks() {
    var self = this;
    if (!this._visibilityHandler) {
      this._visibilityHandler = function () {
        self._requestVisibilityRender();
      };

      window.addEventListener("resize", this._visibilityHandler);
      window.addEventListener("focus", this._visibilityHandler);
      window.addEventListener("pageshow", this._visibilityHandler);
      window.addEventListener("location-changed", this._visibilityHandler);
      document.addEventListener("visibilitychange", this._visibilityHandler);
    }

    if (this._intersectionObserver || typeof IntersectionObserver === "undefined") {
      return;
    }

    this._intersectionObserver = new IntersectionObserver(function (entries) {
      var entry = entries && entries[0] ? entries[0] : null;
      if (!entry || !entry.isIntersecting) {
        return;
      }
      self._requestVisibilityRender();
    }, {
      root: null,
      threshold: 0.01,
    });

    this._intersectionObserver.observe(this);
  }

  _requestVisibilityRender() {
    var self = this;
    requestAnimationFrame(function () {
      if (!self.isConnected || !self._config) {
        return;
      }
      if (document.visibilityState && document.visibilityState === "hidden") {
        return;
      }
      self._lastObservedWidth = 0;
      self._queueRender();
    });
  }

  _queueRender() {
    var self = this;
    self._debugStats.scheduledRenders += 1;
    if (self._renderTimer) {
      self._debugStats.coalescedRenders += 1;
      clearTimeout(self._renderTimer);
    }
    self._renderTimer = setTimeout(function () {
      self._renderTimer = null;
      if (self._renderQueued) {
        return;
      }
      self._debugStats.executedRenders += 1;
      self._renderQueued = true;

      Promise.resolve()
        .then(function () {
          return self._renderCard();
        })
        .catch(function (err) {
          self._showError(err && err.message ? err.message : String(err));
        })
        .then(function () {
          self._renderQueued = false;
        });
    }, 180);
  }

  async _renderCard() {
    if (!this._hass || !this._config || !this._chartContainer) {
      return;
    }
    var renderStarted = typeof performance !== "undefined" && typeof performance.now === "function" ? performance.now() : Date.now();

    if (!this._isVisible()) {
      this._setHiddenState(true);
      this._destroyChart();
      this._chartContainer.innerHTML = "";
      if (this._legendContainer) {
        this._legendContainer.innerHTML = "";
      }
      if (this._summaryContainer) {
        this._summaryContainer.innerHTML = "";
      }
      if (this._detailsContainer) {
        this._detailsContainer.innerHTML = "";
      }
      return;
    }

    this._setHiddenState(false);

    if (!this._hasRenderableWidth()) {
      this._lastObservedWidth = 0;
      return;
    }

    await this._ensureDirectQueryData();

    var archives = this._getScopedArchives();
    var grouped = this._groupArchivesByDate(archives);
    var dataset = this._buildHeatmapDataset(grouped, this._resolveVisibleWeeks());
    var layout = this._buildChartLayout(dataset.weekKeys.length);

    this._applyChartLayout(layout);

    this._renderLegend(dataset);
    this._renderSummary(archives, grouped, dataset);
    this._renderDetails(grouped);

    if (!dataset.hasAnyPastCells) {
      this._destroyChart();
      this._chartContainer.innerHTML = '<div class="details-empty">No print history data is available for the current scope. Refresh the archive cache or relax the filters.</div>';
      return;
    }

    var ApexChartsCtor = await this._ensureApexCharts();
    if (!ApexChartsCtor) {
      this._renderHeatmap(dataset);
      return;
    }

    this._clearError();

  var options = this._buildChartOptions(dataset, layout);

    if (this._chart) {
      this._destroyChart();
    }

    this._chartContainer.innerHTML = "";
    this._chart = new ApexChartsCtor(this._chartContainer, options);
    await this._chart.render();
    await this._ensureChartVisible(dataset);
    await this._applySelectedVisualState(dataset);
    this._recordDebug(renderStarted, dataset);
  }

  _destroyChart() {
    this._hideSelectedOverlay();
    if (this._chart && typeof this._chart.destroy === "function") {
      this._chart.destroy();
    }
    this._chart = null;
  }

  _isVisible() {
    if (!this._config || !this._config.visibility_entity) {
      return true;
    }
    return this._stateValue(this._config.visibility_entity) !== "off";
  }

  _setHiddenState(hidden) {
    if (this._isHidden === hidden) {
      return;
    }

    var card = this.shadowRoot ? this.shadowRoot.querySelector("ha-card") : null;
    if (card) {
      card.style.display = hidden ? "none" : "block";
    }
    this._isHidden = hidden;
    if (!hidden) {
      this._lastObservedWidth = 0;
    }
  }

  _hasRenderableWidth() {
    var width = this._chartContainer && this._chartContainer.clientWidth
      ? this._chartContainer.clientWidth
      : this.clientWidth || 0;
    return width > 0;
  }

  _clearError() {
    if (!this._chartContainer) {
      return;
    }
    var errorNode = this._chartContainer.querySelector(".error");
    if (errorNode) {
      this._chartContainer.innerHTML = "";
    }
  }

  async _ensureChartVisible(dataset) {
    await new Promise(function (resolve) { setTimeout(resolve, 0); });

    if (this._chartHasRenderableOutput()) {
      return;
    }

    this._destroyChart();
    this._renderHeatmap(dataset);
  }

  _chartHasRenderableOutput() {
    if (!this._chartContainer) {
      return false;
    }

    return !!this._chartContainer.querySelector(".apexcharts-canvas, svg, canvas");
  }

  _getScopedArchives() {
    var raw = [];
    if (this._config.direct_query) {
      raw = this._queryResponse && Array.isArray(this._queryResponse.activity_rows) ? this._queryResponse.activity_rows : [];
    } else {
      var sourceState = this._hass.states[this._config.source_entity];
      raw = sourceState && sourceState.attributes ? sourceState.attributes[this._config.source_attribute] : [];
    }
    var archives = this._parseArchiveArray(raw)
      .map(this._normalizeArchive.bind(this))
      .filter(function (archive) {
        return !!archive.timestamp;
      })
      .sort(function (left, right) {
        return right.timestamp - left.timestamp;
      });

    return this._config.direct_query ? archives : archives.filter(this._matchesFilters.bind(this));
  }

  async _ensureDirectQueryData() {
    if (!this._config.direct_query || !this._hass || typeof this._hass.callWS !== "function") {
      return;
    }

    var token = ++this._queryToken;
    var started = typeof performance !== "undefined" && typeof performance.now === "function" ? performance.now() : Date.now();
    this._queryResponse = await this._hass.callWS({
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
      favorites_only: this._isOn("input_boolean.print_history_filter_favorites_only"),
      search: String(this._stateValue("input_text.print_history_search") || "").trim(),
      colors: String(this._stateValue("input_text.print_history_filter_colors") || "").trim(),
      selected_day: String(this._stateValue(this._config.selected_date_entity) || "").trim(),
      sort: this._normalizeFilterValue(this._stateValue("input_select.print_history_sort")),
      activity_metric: this._normalizeFilterValue(this._stateValue(this._config.mode_entity)),
      include_activity_rows: true,
    });
    if (token !== this._queryToken) {
      return;
    }
    if (!this._queryResponse || typeof this._queryResponse !== "object") {
      this._queryResponse = { activity_rows: [] };
    }
    this._recordDebug(started, null, true);
  }

  _debugEnabled() {
    return this._stateValue("input_boolean.print_history_debug_instrumentation") === "on";
  }

  _recordDebug(started, dataset, queryOnly) {
    if (!this._debugEnabled()) {
      return;
    }
    var ended = typeof performance !== "undefined" && typeof performance.now === "function" ? performance.now() : Date.now();
    var activityRows = this._queryResponse && Array.isArray(this._queryResponse.activity_rows)
      ? this._queryResponse.activity_rows.length
      : 0;
    var payload = {
      at: new Date().toISOString(),
      channel: queryOnly ? "heatmap_query" : "heatmap_render",
      durationMs: Math.round((ended - started) * 10) / 10,
      activityRowCount: activityRows,
      scheduledRenders: this._debugStats.scheduledRenders,
      executedRenders: this._debugStats.executedRenders,
      coalescedRenders: this._debugStats.coalescedRenders,
      weekCount: dataset && dataset.weekKeys ? dataset.weekKeys.length : null,
      backend: this._queryResponse && this._queryResponse.debug ? this._queryResponse.debug : null,
      store: this._queryResponse && this._queryResponse.store ? this._queryResponse.store : null,
    };
    window.__printHistoryDebug = window.__printHistoryDebug || { events: [], latest: {} };
    window.__printHistoryDebug.events.push(payload);
    if (window.__printHistoryDebug.events.length > 100) {
      window.__printHistoryDebug.events.shift();
    }
    window.__printHistoryDebug.latest[payload.channel] = payload;
    if (typeof console !== "undefined" && typeof console.debug === "function") {
      console.debug("[print-history-debug]", payload);
    }
  }

  _normalizeFilterValue(value) {
    var normalized = String(value || "").trim();
    if (!normalized || normalized === "All") {
      return "";
    }
    return normalized;
  }

  _parseArchiveArray(raw) {
    if (Array.isArray(raw)) {
      return raw;
    }
    if (typeof raw === "string" && raw.trim()) {
      try {
        var parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
      } catch (_err) {
        return [];
      }
    }
    return [];
  }

  _normalizeArchive(archive) {
    var startedAt = archive && (archive.started_at || archive.created_at || archive.completed_at || "");
    var date = this._parseDate(startedAt);
    var colorWeights = this._collectColorWeights(archive || {});
    var colors = Object.keys(colorWeights);
    var dateKey = archive && (archive.archive_day || archive.archive_day_local || "");

    if (!dateKey && date) {
      dateKey = this._formatLocalDate(date);
    }

    return {
      id: archive && archive.id != null ? archive.id : null,
      printName: archive && archive.print_name ? String(archive.print_name) : "Unnamed",
      printerId: archive && archive.printer_id != null ? String(archive.printer_id) : "Unknown printer",
      printerName: archive && archive.printer_name ? String(archive.printer_name) : "",
      printerLabel: archive && archive.printer_name ? String(archive.printer_name) : (archive && archive.printer_id != null ? String(archive.printer_id) : "Unknown printer"),
      filamentType: archive && archive.filament_type ? String(archive.filament_type) : "",
      designer: archive && archive.designer ? String(archive.designer) : "",
      isFavorite: !!(archive && archive.is_favorite),
      status: this._normalizeStatus(archive && archive.status),
      rawStatus: archive && archive.status ? String(archive.status) : "",
      timestamp: date,
      dateKey: dateKey,
      formattedDate: date ? this._formatDateTime(date) : "Unknown date",
      objectCount: Math.max(1, this._toNumber(archive && archive.object_count)),
      filamentWeight: this._toNumber(archive && archive.filament_used_grams),
      filamentCount: this._countDistinctFilaments(archive),
      durationHours: this._secondsToHours(archive && (archive.actual_time_seconds != null ? archive.actual_time_seconds : archive.print_time_seconds)),
      cost: this._toNumber(archive && archive.cost),
      layerHeight: archive && archive.layer_height != null && archive.layer_height !== "" ? String(archive.layer_height) : "",
      tags: archive && archive.tags ? String(archive.tags) : "",
      colors: colors,
      colorWeights: colorWeights,
    };
  }

  _matchesFilters(archive) {
    var statusValue = this._stateValue("input_select.print_history_filter_status");
    var materialValue = this._stateValue("input_select.print_history_filter_material");
    var printerValue = this._stateValue("input_select.print_history_filter_printer");
    var dateRangeValue = this._stateValue("input_select.print_history_filter_date_range");
    var designerValue = this._stateValue("input_select.print_history_filter_designer");
    var layerHeightValue = this._stateValue("input_select.print_history_filter_layer_height");
    var tagValue = this._stateValue("input_select.print_history_filter_tag");
    var favoritesOnly = this._isOn("input_boolean.print_history_filter_favorites_only");
    var searchText = String(this._stateValue("input_text.print_history_search") || "").toLowerCase().trim();
    var selectedColors = String(this._stateValue("input_text.print_history_filter_colors") || "")
      .toLowerCase()
      .split(",")
      .map(function (value) {
        return value.trim();
      })
      .filter(Boolean);
      var isFavorite = !!archive.isFavorite;
    var todayKey = this._formatLocalDate(new Date());
    var archiveDate = archive.dateKey ? this._dateFromDateKey(archive.dateKey) : null;
    var todayDate = this._dateFromDateKey(todayKey);
    var archiveAgeDays = archiveDate && todayDate
      ? (todayDate.getTime() - archiveDate.getTime()) / 86400000
      : Number.POSITIVE_INFINITY;
    var archiveStatus = archive.status;
    var tagValues = this._parseTagList(archive.tags);
    var searchBlob = [archive.printName, archive.designer, archive.tags]
      .join(" ")
      .toLowerCase();

    var matchesStatus = statusValue === "All" || this._matchesStatusFilter(statusValue, archiveStatus);
    var matchesMaterial = materialValue === "All" || String(archive.filamentType || "").toLowerCase() === String(materialValue).toLowerCase();
    var matchesPrinter = printerValue === "All"
      || String(archive.printerId) === String(printerValue)
      || String(archive.printerLabel) === String(printerValue)
      || (archive.printerName && String(archive.printerName).toLowerCase() === String(printerValue).toLowerCase());
    var matchesDesigner = designerValue === "All" || String(archive.designer).toLowerCase() === String(designerValue).toLowerCase();
    var matchesLayerHeight = layerHeightValue === "All" || String(archive.layerHeight) === String(layerHeightValue);
    var matchesTag = !tagValue || String(tagValue).toLowerCase() === "all" || tagValues.indexOf(String(tagValue).toLowerCase()) !== -1;
    var matchesFavorite = !favoritesOnly || isFavorite;
    var matchesSearch = !searchText || searchBlob.indexOf(searchText) !== -1;
    var matchesColors = !selectedColors.length || selectedColors.some(function (color) {
      return archive.colors.indexOf(color) !== -1;
    });
    var matchesDate = true;

    if (dateRangeValue === "Today") {
      matchesDate = archive.dateKey === todayKey;
    } else if (dateRangeValue === "This Week") {
      matchesDate = archiveAgeDays < 7;
    } else if (dateRangeValue === "This Month") {
      matchesDate = !!archive.dateKey && archive.dateKey.slice(0, 7) === todayKey.slice(0, 7);
    } else if (dateRangeValue === "Last 30 Days") {
      matchesDate = archiveAgeDays < 30;
    } else if (dateRangeValue === "Last 90 Days") {
      matchesDate = archiveAgeDays < 90;
    }

    return matchesStatus && matchesMaterial && matchesPrinter && matchesDesigner && matchesLayerHeight && matchesTag && matchesFavorite && matchesSearch && matchesColors && matchesDate;
  }

  _parseTagList(raw) {
    return String(raw || "")
      .split(",")
      .map(function (value) {
        return value.trim().toLowerCase();
      })
      .filter(Boolean);
  }

  _matchesStatusFilter(statusValue, archiveStatus) {
    var selected = String(statusValue || "").toLowerCase();
    if (!selected || selected === "all") {
      return true;
    }
    if (selected === "completed") {
      return archiveStatus === "completed";
    }
    if (selected === "failed") {
      return archiveStatus === "failed";
    }
    return archiveStatus === selected;
  }

  _groupArchivesByDate(archives) {
    return archives.reduce(
      function (accumulator, archive) {
        var key = archive.dateKey;
        if (!key) {
          return accumulator;
        }

        if (!accumulator[key]) {
          accumulator[key] = {
            dateKey: key,
            archives: [],
            count: 0,
            objectCount: 0,
            weight: 0,
            cost: 0,
            filamentCount: 0,
            durationHours: 0,
            successCount: 0,
            failedCount: 0,
            cancelledCount: 0,
            printingCount: 0,
            otherCount: 0,
            colorWeights: {},
          };
        }

        var day = accumulator[key];
        day.archives.push(archive);
        day.count += 1;
        day.objectCount += archive.objectCount;
        day.weight += archive.filamentWeight;
        day.cost += archive.cost;
        day.durationHours += archive.durationHours;
        day.filamentCount += archive.filamentCount;

        if (archive.status === "completed") {
          day.successCount += 1;
        } else if (archive.status === "failed") {
          day.failedCount += 1;
        } else if (archive.status === "cancelled") {
          day.cancelledCount += 1;
        } else if (archive.status === "printing") {
          day.printingCount += 1;
        } else {
          day.otherCount += 1;
        }

        Object.keys(archive.colorWeights).forEach(function (color) {
          day.colorWeights[color] = (day.colorWeights[color] || 0) + archive.colorWeights[color];
        });

        return accumulator;
      },
      {}
    );
  }

  _buildHeatmapDataset(grouped, visibleWeeks) {
    var mode = this._normalizeMode(this._stateValue(this._config.mode_entity) || "Print Count");
    var weeks = Math.max(12, Number(visibleWeeks || this._config.weeks || 52));
    var startDay = ((this._config.start_day % 7) + 7) % 7;
    var todayKey = this._formatLocalDate(new Date());
    var rangeEnd = todayKey;
    var rangeStart = this._startOfWeekKey(rangeEnd, startDay);
    rangeStart = this._shiftDateKey(rangeStart, -((weeks - 1) * 7));

    var keys = Object.keys(grouped);
    var maxCount = 0;
    var maxObjectCount = 0;
    var maxWeight = 0;
    var maxCost = 0;
    var maxFilamentCount = 0;
    var maxDurationHours = 0;

    keys.forEach(function (key) {
      var day = grouped[key];
      maxCount = Math.max(maxCount, day.count || 0);
      maxObjectCount = Math.max(maxObjectCount, day.objectCount || 0);
      maxWeight = Math.max(maxWeight, day.weight || 0);
      maxCost = Math.max(maxCost, day.cost || 0);
      maxFilamentCount = Math.max(maxFilamentCount, day.filamentCount || 0);
      maxDurationHours = Math.max(maxDurationHours, day.durationHours || 0);
      day.dominantColor = this._findDominantColor(day.colorWeights);
      day.outcomeColor = this._buildOutcomeColor(day);
      day.outcomeBand = this._buildOutcomeBand(day);
      day.hasFullDayPrinting = Number(day.durationHours || 0) >= 24;
      day.archives.sort(function (left, right) {
        return right.timestamp - left.timestamp;
      });
    }.bind(this));

    var series = this._config.day_labels.map(function (label) {
      return { name: label, data: [] };
    });
    var weekKeys = [];
    var hasAnyPastCells = false;

    for (var weekIndex = 0; weekIndex < weeks; weekIndex += 1) {
      var weekKey = this._shiftDateKey(rangeStart, weekIndex * 7);
      weekKeys.push(weekKey);

      for (var dayIndex = 0; dayIndex < 7; dayIndex += 1) {
        var currentKey = this._shiftDateKey(weekKey, dayIndex);
        var isFuture = currentKey > todayKey;
        var stats = grouped[currentKey] || null;
        var point = this._buildPoint({
          weekKey: weekKey,
          dateKey: currentKey,
          stats: stats,
          mode: mode,
          maxCount: maxCount,
          maxObjectCount: maxObjectCount,
          maxWeight: maxWeight,
          maxCost: maxCost,
          maxFilamentCount: maxFilamentCount,
          maxDurationHours: maxDurationHours,
          isFuture: isFuture,
        });

        if (!isFuture) {
          hasAnyPastCells = true;
        }

        series[dayIndex].data.push(point);
      }
    }

    return {
      mode: mode,
      series: series,
      colorRanges: this._buildColorRanges(series, mode, {
        maxCount: maxCount,
        maxObjectCount: maxObjectCount,
        maxWeight: maxWeight,
        maxCost: maxCost,
        maxFilamentCount: maxFilamentCount,
        maxDurationHours: maxDurationHours,
      }),
      weekKeys: weekKeys,
      rangeStart: rangeStart,
      rangeEnd: rangeEnd,
      hasAnyPastCells: hasAnyPastCells,
      weeks: weeks,
    };
  }

  _resolveVisibleWeeks() {
    var desktopWeeks = Math.max(12, Number(this._config.weeks || 52));
    var tabletWeeks = Math.min(desktopWeeks, Math.max(12, Number(this._config.tablet_weeks || desktopWeeks)));
    var mobileWeeks = Math.min(tabletWeeks, Math.max(12, Number(this._config.mobile_weeks || tabletWeeks)));
    var width = this._chartContainer && this._chartContainer.clientWidth
      ? this._chartContainer.clientWidth
      : this.clientWidth || 0;

    if (width && width <= this._config.mobile_breakpoint) {
      return mobileWeeks;
    }
    if (width && width <= this._config.tablet_breakpoint) {
      return tabletWeeks;
    }
    return desktopWeeks;
  }

  _buildPoint(input) {
    var stats = input.stats;
    var color = this._emptyCellColor();
    var value = 0;

    if (input.isFuture) {
      value = -1;
      color = this._futureCellColor();
    } else if (stats) {
      if (input.mode === "Filament Weight") {
        value = Number(stats.weight || 0);
        color = this._buildIntensityColor(value, input.maxWeight || 0, "#DBEAFE", "#1D4ED8");
      } else if (input.mode === "Number of Printed Objects") {
        value = Number(stats.objectCount || 0);
        color = this._buildIntensityColor(value, input.maxObjectCount || 0, "#FEF3C7", "#D97706");
      } else if (input.mode === "Cost of Prints") {
        value = Number(stats.cost || 0);
        color = this._buildIntensityColor(value, input.maxCost || 0, "#FCE7F3", "#BE185D");
      } else if (input.mode === "Filaments Used") {
        value = Number(stats.filamentCount || 0);
        color = this._buildIntensityColor(value, input.maxFilamentCount || 0, "#E0F2FE", "#0369A1");
      } else if (input.mode === "Total Time Printing") {
        value = Number(stats.durationHours || 0);
        color = this._buildIntensityColor(value, input.maxDurationHours || 0, "#EDE9FE", "#6D28D9");
      } else if (input.mode === "Dominant Color") {
        value = Number(stats.count || 0);
        color = stats.dominantColor || this._emptyCellColor();
      } else if (input.mode === "Outcome") {
        value = Number(stats.outcomeBand || 0);
        color = stats.outcomeColor;
      } else {
        value = Number(stats.count || 0);
        color = this._buildIntensityColor(value, input.maxCount || 0, "#DCFCE7", "#15803D");
      }
    }

    return {
      x: input.weekKey,
      y: value,
      fillColor: color,
      strokeColor: this._pointStrokeColor(input.isFuture, !!stats),
      meta: {
        dateKey: input.dateKey,
        label: this._formatDateLabel(input.dateKey),
        count: stats ? stats.count : 0,
        objectCount: stats ? stats.objectCount : 0,
        weight: stats ? stats.weight : 0,
        cost: stats ? stats.cost : 0,
        filamentCount: stats ? stats.filamentCount : 0,
        durationHours: stats ? stats.durationHours : 0,
        dominantColor: stats ? stats.dominantColor || "" : "",
        outcomeColor: stats ? stats.outcomeColor : "",
        outcomeLabel: stats ? this._outcomeBandLabel(stats.outcomeBand) : "",
        hasFullDayPrinting: stats ? !!stats.hasFullDayPrinting : false,
        successCount: stats ? stats.successCount : 0,
        failedCount: stats ? stats.failedCount : 0,
        cancelledCount: stats ? stats.cancelledCount : 0,
        printingCount: stats ? stats.printingCount : 0,
        otherCount: stats ? stats.otherCount : 0,
        isFuture: input.isFuture,
      },
    };
  }

  _buildChartOptions(dataset, layout) {
    var self = this;
    var isDark = !!(this._hass && this._hass.themes && this._hass.themes.darkMode);
    var textColor = this._themeColor(["--primary-text-color"], isDark ? "#D1D5DB" : "#1F2937");
    var chartBackground = this._themeColor(["--ha-card-background", "--card-background-color", "--primary-background-color"], isDark ? "#111827" : "#ffffff");

    return {
      chart: {
        type: "heatmap",
        height: layout.chartHeight,
        parentHeightOffset: 0,
        background: chartBackground,
        foreColor: textColor,
        toolbar: { show: false },
        animations: { enabled: false },
        events: {
          dataPointSelection: function (_event, _chartCtx, opts) {
            self._handlePointSelection(opts, dataset);
          },
        },
      },
      series: dataset.series,
      legend: { show: false },
      dataLabels: { enabled: false },
      xaxis: {
        type: "category",
        categories: dataset.weekKeys,
        labels: {
          show: true,
          rotate: 0,
          hideOverlappingLabels: false,
          style: {
            colors: dataset.weekKeys.map(function () {
              return textColor;
            }),
            fontSize: "11px",
          },
          formatter: function (value, _timestamp, opts) {
            var index = opts && typeof opts.i === "number" ? opts.i : -1;
            return self._formatWeekLabel(value, dataset.weekKeys, index);
          },
        },
        axisBorder: {
          show: false,
        },
        axisTicks: {
          show: false,
        },
        tooltip: {
          enabled: false,
        },
      },
      yaxis: {
        reversed: true,
        labels: {
          minWidth: 28,
          maxWidth: 28,
          offsetX: -8,
          style: {
            colors: dataset.series.map(function () {
              return textColor;
            }),
            fontSize: "11px",
          },
        },
      },
      plotOptions: {
        heatmap: {
          radius: 0,
          enableShades: false,
          useFillColorAsStroke: false,
          colorScale: {
            ranges: dataset.colorRanges,
          },
        },
      },
      colors: ["#14B8A6"],
      stroke: {
        width: 2,
        colors: [chartBackground],
      },
      tooltip: {
        theme: isDark ? "dark" : "light",
        custom: function (opts) {
          var point = opts && opts.w && opts.w.config && opts.w.config.series && opts.w.config.series[opts.seriesIndex]
            ? opts.w.config.series[opts.seriesIndex].data[opts.dataPointIndex]
            : null;
          return self._buildTooltip(point && point.meta ? point.meta : null, dataset.mode);
        },
      },
      grid: {
        show: false,
        padding: {
          top: 0,
          right: 4,
          bottom: 0,
          left: 16,
        },
      },
      states: {
        hover: {
          filter: {
            type: "none",
          },
        },
        active: {
          allowMultipleDataPointsSelection: false,
          filter: {
            type: "darken",
            value: 0.18,
          },
        },
      },
      theme: {
        mode: isDark ? "dark" : "light",
      },
    };
  }

  async _applySelectedVisualState(dataset) {
    if (!this._chart) {
      return;
    }

    var selection = await this._applySelectedPointState(dataset);
    this._positionSelectedOverlay(selection ? selection.element : null, selection ? selection.indexes : null, dataset);
  }

  async _applySelectedPointState(dataset) {
    if (!this._chart || !dataset) {
      return null;
    }

    var selectedDate = String(this._stateValue(this._config.selected_date_entity) || "").trim();
    if (!selectedDate) {
      this._hideSelectedOverlay();
      return null;
    }

    var indexes = this._findPointIndexesByDate(dataset, selectedDate);
    if (!indexes) {
      this._hideSelectedOverlay();
      return null;
    }

    var selectedPoints = this._chart && this._chart.w && this._chart.w.globals
      ? this._chart.w.globals.selectedDataPoints
      : null;
    var currentSeriesSelection = selectedPoints && Array.isArray(selectedPoints[indexes.seriesIndex])
      ? selectedPoints[indexes.seriesIndex]
      : [];
    if (currentSeriesSelection.indexOf(indexes.dataPointIndex) !== -1) {
      return {
        element: this._findRenderedPointElement(indexes),
        indexes: indexes,
      };
    }

    this._suppressPointSelection = true;
    try {
      var selectedElement = this._chart.toggleDataPointSelection(indexes.seriesIndex, indexes.dataPointIndex);
      await Promise.resolve();
      return {
        element: selectedElement || this._findRenderedPointElement(indexes),
        indexes: indexes,
      };
    } finally {
      this._suppressPointSelection = false;
    }
  }

  _findRenderedPointElement(indexes) {
    if (!this._chartContainer || !indexes) {
      return null;
    }

    var selectors = [
      '.apexcharts-series[rel="' + String(indexes.seriesIndex + 1) + '"] path[j="' + String(indexes.dataPointIndex) + '"]',
      '.apexcharts-series[seriesName] path[j="' + String(indexes.dataPointIndex) + '"]',
      '.apexcharts-heatmap-rect[j="' + String(indexes.dataPointIndex) + '"]',
    ];

    for (var selectorIndex = 0; selectorIndex < selectors.length; selectorIndex += 1) {
      var match = this._chartContainer.querySelector(selectors[selectorIndex]);
      if (match) {
        return match;
      }
    }

    return this._findSelectedPointElement();
  }

  _findSelectedPointElement() {
    if (!this._chartContainer) {
      return null;
    }

    return this._chartContainer.querySelector('.apexcharts-series path.apexcharts-active, .apexcharts-series .apexcharts-active');
  }

  _positionSelectedOverlay(targetElement, indexes, dataset) {
    var overlay = this._ensureSelectedOverlay();
    if (!overlay || !this._chartContainer) {
      this._hideSelectedOverlay();
      return;
    }

    // Anchor the highlight to the rendered heatmap cell, not chart-axis math, so it stays aligned.
    if (targetElement) {
      var containerRect = this._chartContainer.getBoundingClientRect();
      var targetRect = targetElement.getBoundingClientRect();
      if (containerRect.width && containerRect.height && targetRect.width && targetRect.height) {
        var inset = 1.5;
        overlay.style.left = (targetRect.left - containerRect.left - inset) + 'px';
        overlay.style.top = (targetRect.top - containerRect.top - inset) + 'px';
        overlay.style.width = (targetRect.width + inset * 2) + 'px';
        overlay.style.height = (targetRect.height + inset * 2) + 'px';
        overlay.style.display = 'block';
        return;
      }
    }

    var fallbackBounds = this._computeSelectedOverlayBounds(indexes, dataset);
    if (!fallbackBounds) {
      this._hideSelectedOverlay();
      return;
    }

    overlay.style.left = fallbackBounds.left + 'px';
    overlay.style.top = fallbackBounds.top + 'px';
    overlay.style.width = fallbackBounds.width + 'px';
    overlay.style.height = fallbackBounds.height + 'px';
    overlay.style.display = 'block';
  }

  _computeSelectedOverlayBounds(indexes, dataset) {
    if (!indexes || !dataset || !this._chartContainer) {
      return null;
    }

    var seriesElement = this._findSeriesElement(indexes.seriesIndex);
    var pointCount = dataset.series && dataset.series[indexes.seriesIndex] && Array.isArray(dataset.series[indexes.seriesIndex].data)
      ? dataset.series[indexes.seriesIndex].data.length
      : 0;
    if (!seriesElement || !pointCount) {
      return null;
    }

    var containerRect = this._chartContainer.getBoundingClientRect();
    var seriesRect = seriesElement.getBoundingClientRect();
    if (!containerRect.width || !seriesRect.width || !seriesRect.height) {
      return null;
    }

    var cellWidth = seriesRect.width / pointCount;
    if (!cellWidth) {
      return;
    }

    var inset = 1.5;
    return {
      left: (seriesRect.left - containerRect.left + cellWidth * indexes.dataPointIndex - inset),
      top: (seriesRect.top - containerRect.top - inset),
      width: (cellWidth + inset * 2),
      height: (seriesRect.height + inset * 2),
    };
  }

  _findSeriesElement(seriesIndex) {
    if (!this._chartContainer || typeof seriesIndex !== 'number') {
      return null;
    }

    var selectors = [
      '.apexcharts-series[rel="' + String(seriesIndex + 1) + '"]',
      '.apexcharts-series[seriesName]:nth-of-type(' + String(seriesIndex + 1) + ')',
    ];

    for (var selectorIndex = 0; selectorIndex < selectors.length; selectorIndex += 1) {
      var match = this._chartContainer.querySelector(selectors[selectorIndex]);
      if (match) {
        return match;
      }
    }

    var seriesGroups = this._chartContainer.querySelectorAll('.apexcharts-series');
    return seriesGroups && seriesGroups[seriesIndex] ? seriesGroups[seriesIndex] : null;
  }

  _ensureSelectedOverlay() {
    if (!this._chartContainer) {
      return null;
    }

    if (!this._selectedOverlay || this._selectedOverlay.parentNode !== this._chartContainer) {
      if (this._selectedOverlay && this._selectedOverlay.parentNode) {
        this._selectedOverlay.parentNode.removeChild(this._selectedOverlay);
      }
      this._selectedOverlay = document.createElement('div');
      this._selectedOverlay.className = 'selected-cell-overlay';
      this._chartContainer.appendChild(this._selectedOverlay);
    }

    return this._selectedOverlay;
  }

  _hideSelectedOverlay() {
    if (this._selectedOverlay) {
      this._selectedOverlay.style.display = 'none';
    }
  }

  _findPointIndexesByDate(dataset, dateKey) {
    var series = dataset && Array.isArray(dataset.series) ? dataset.series : [];
    for (var seriesIndex = 0; seriesIndex < series.length; seriesIndex += 1) {
      var row = series[seriesIndex];
      var points = row && Array.isArray(row.data) ? row.data : [];
      for (var dataPointIndex = 0; dataPointIndex < points.length; dataPointIndex += 1) {
        var point = points[dataPointIndex];
        var meta = point && point.meta ? point.meta : null;
        if (meta && meta.dateKey === dateKey && !meta.isFuture) {
          return {
            seriesIndex: seriesIndex,
            dataPointIndex: dataPointIndex,
          };
        }
      }
    }

    return null;
  }

  _buildChartLayout(weekCount) {
    var safeWeekCount = Math.max(1, Number(weekCount) || 53);
    var containerWidth = this._chartContainer && this._chartContainer.clientWidth
      ? this._chartContainer.clientWidth
      : this.clientWidth || 960;
    var availableWidth = Math.max(240, containerWidth - 68);
    var cellSize = Math.max(8, Math.min(18, Math.floor(availableWidth / safeWeekCount)));
    var chartHeight = Math.max(136, cellSize * 7 + 54);

    return {
      cellSize: cellSize,
      chartHeight: chartHeight,
    };
  }

  _applyChartLayout(layout) {
    if (!this._chartContainer || !layout) {
      return;
    }

    this._chartContainer.style.setProperty("--cell-size", layout.cellSize + "px");
    this._chartContainer.style.setProperty("--chart-min-height", layout.chartHeight + "px");
    this._chartContainer.style.setProperty("--chart-gap-background", this._themeColor(["--ha-card-background", "--card-background-color", "--primary-background-color"], this._hass && this._hass.themes && this._hass.themes.darkMode ? "#111827" : "#ffffff"));
    this._chartContainer.style.setProperty("--cell-empty", this._emptyCellColor());
    this._chartContainer.style.setProperty("--cell-stroke", this._pointStrokeColor(false, false));
    this._chartContainer.style.setProperty("--cell-stroke-strong", this._pointStrokeColor(false, true));
    this._chartContainer.style.setProperty("--annotation-outline-base", this._themeColor(["--ha-card-background", "--card-background-color", "--primary-background-color"], this._hass && this._hass.themes && this._hass.themes.darkMode ? "#111827" : "#ffffff"));
    this._chartContainer.style.setProperty("--annotation-outline-glow", this._themeColor(["--primary-color"], "#2563EB"));
  }

  _buildColorRanges(series, mode, maxima) {
    var futureColor = this._futureCellColor();
    var emptyColor = this._emptyCellColor();
    var ranges = [
      { from: -1, to: -1, color: futureColor },
      { from: 0, to: 0, color: emptyColor },
    ];

    if (mode === "Dominant Color") {
      return ranges.concat(this._buildCategoricalColorRanges(series, function (point) {
        return point && point.meta && point.meta.dominantColor ? point.meta.dominantColor : emptyColor;
      }));
    }

    if (mode === "Outcome") {
      return ranges.concat([
        { from: 1, to: 1, color: "#D32F2F" },
        { from: 2, to: 2, color: "#F57C00" },
        { from: 3, to: 3, color: "#FBC02D" },
        { from: 4, to: 4, color: "#9CCC65" },
        { from: 5, to: 5, color: "#2E7D32" },
      ]);
    }

    var modeConfig = this._modeScaleConfig(mode, maxima || {});

    return ranges.concat(
      this._buildContinuousColorRanges(
        modeConfig.maxValue,
        modeConfig.startColor,
        modeConfig.endColor
      )
    );
  }

  _modeScaleConfig(mode, maxima) {
    if (mode === "Filament Weight") {
      return { maxValue: maxima.maxWeight || 0, startColor: "#DBEAFE", endColor: "#1D4ED8" };
    }
    if (mode === "Number of Printed Objects") {
      return { maxValue: maxima.maxObjectCount || 0, startColor: "#FEF3C7", endColor: "#D97706" };
    }
    if (mode === "Cost of Prints") {
      return { maxValue: maxima.maxCost || 0, startColor: "#FCE7F3", endColor: "#BE185D" };
    }
    if (mode === "Filaments Used") {
      return { maxValue: maxima.maxFilamentCount || 0, startColor: "#E0F2FE", endColor: "#0369A1" };
    }
    if (mode === "Total Time Printing") {
      return { maxValue: maxima.maxDurationHours || 0, startColor: "#EDE9FE", endColor: "#6D28D9" };
    }
    return { maxValue: maxima.maxCount || 0, startColor: "#DCFCE7", endColor: "#15803D" };
  }

  _buildCategoricalColorRanges(series, colorSelector) {
    var colorCodes = {};
    var nextCode = 1;
    var ranges = [];

    series.forEach(function (row) {
      row.data.forEach(function (point) {
        if (!point || !point.meta) {
          point.y = 0;
          return;
        }
        if (point.meta.isFuture) {
          point.y = -1;
          return;
        }
        if (!point.meta.count) {
          point.y = 0;
          return;
        }

        var color = this._normalizeHexColor(colorSelector(point)) || this._emptyCellColor();
        if (!colorCodes[color]) {
          colorCodes[color] = nextCode;
          ranges.push({ from: nextCode, to: nextCode, color: color });
          nextCode += 1;
        }
        point.y = colorCodes[color];
      }.bind(this));
    }.bind(this));

    return ranges;
  }

  _buildContinuousColorRanges(maxValue, startColor, endColor) {
    if (!maxValue || maxValue <= 0) {
      return [];
    }

    var bucketCount = 6;
    var ranges = [];
    for (var bucket = 1; bucket <= bucketCount; bucket += 1) {
      var from = bucket === 1 ? Number.EPSILON : ((bucket - 1) * maxValue) / bucketCount;
      var to = bucket === bucketCount ? maxValue : (bucket * maxValue) / bucketCount;
      ranges.push({
        from: from,
        to: to,
        color: this._buildIntensityColor(bucket, bucketCount, startColor, endColor),
      });
    }
    return ranges;
  }

  _renderHeatmap(dataset) {
    if (!this._chartContainer) {
      return;
    }

    var selectedDate = String(this._stateValue(this._config.selected_date_entity) || "").trim();
    var monthLabels = this._buildMonthLabels(dataset.weekKeys);
    var dayLabels = Array.isArray(this._config.day_labels) ? this._config.day_labels : [];
    var rowsHtml = dataset.series.map(function (series, rowIndex) {
      var label = dayLabels[rowIndex] || "";
      return {
        label: '<div class="day-label">' + this._escapeHtml(label) + '</div>',
        cells: '<div class="heatmap-row">' + series.data.map(function (point) {
          return this._buildHeatmapCell(point, selectedDate, dataset.mode);
        }.bind(this)).join("") + '</div>',
      };
    }.bind(this));

    this._chartContainer.innerHTML =
      '<div class="heatmap" style="--week-count:' + this._escapeHtml(String(dataset.weekKeys.length || 53)) + '">' +
      '<div class="month-spacer"></div>' +
      '<div class="month-row">' + monthLabels + '</div>' +
      '<div class="day-labels">' + rowsHtml.map(function (row) { return row.label; }).join("") + '</div>' +
      '<div class="cells">' + rowsHtml.map(function (row) { return row.cells; }).join("") + '</div>' +
      '</div>';

    Array.from(this._chartContainer.querySelectorAll(".cell[data-date-key]")).forEach(function (button) {
      button.addEventListener("click", function (event) {
        if (button.disabled) {
          event.preventDefault();
          return;
        }
        this._handleDateSelection(button.getAttribute("data-date-key"));
      }.bind(this));
    }.bind(this));
  }

  _buildMonthLabels(weekKeys) {
    var lastMonth = "";
    return weekKeys.map(function (weekKey) {
      var date = this._parseDate(weekKey + "T00:00:00");
      var month = date
        ? date.toLocaleDateString(undefined, { month: "short" })
        : "";
      var showLabel = month && month !== lastMonth;
      lastMonth = month || lastMonth;
      return '<div class="month-label">' + this._escapeHtml(showLabel ? month : "") + '</div>';
    }.bind(this)).join("");
  }

  _buildHeatmapCell(point, selectedDate, mode) {
    var meta = point && point.meta ? point.meta : null;
    var dateKey = meta && meta.dateKey ? meta.dateKey : "";
    var classes = ["cell"];
    if (meta && meta.isFuture) {
      classes.push("future");
    }
    if (dateKey && selectedDate === dateKey) {
      classes.push("selected");
    }

    var title = meta ? this._buildHeatmapTitle(meta, mode) : "";
    var style = point && point.fillColor ? ' style="background:' + this._escapeHtml(point.fillColor) + ';"' : "";
    var disabled = meta && meta.isFuture ? " disabled" : "";

    return '<button class="' + this._escapeHtml(classes.join(" ")) + '" type="button"' +
      (dateKey ? ' data-date-key="' + this._escapeHtml(dateKey) + '"' : "") +
      (title ? ' title="' + this._escapeHtml(title) + '" aria-label="' + this._escapeHtml(title) + '"' : "") +
      style +
      disabled +
      '></button>';
  }

  _buildHeatmapTitle(meta, mode) {
    var title = [
      meta.label,
      'Prints: ' + this._formatCount(meta.count || 0),
      'Objects: ' + this._formatCount(meta.objectCount || 0),
      'Weight: ' + this._formatWeight(meta.weight || 0),
      'Cost: ' + this._formatCost(meta.cost || 0),
      'Filaments: ' + this._formatCount(meta.filamentCount || 0),
      'Time: ' + this._formatHours(meta.durationHours || 0),
      'Status: ' + this._formatCount(meta.successCount || 0) + ' completed, ' + this._formatCount(meta.failedCount || 0) + ' failed, ' + this._formatCount(meta.cancelledCount || 0) + ' cancelled',
    ];

    if (mode === 'Dominant Color' && meta.dominantColor) {
      title.push('Dominant color: ' + meta.dominantColor.toUpperCase());
    }

    if (mode === 'Outcome' && meta.outcomeLabel) {
      title.push('Outcome: ' + meta.outcomeLabel);
    }

    if (mode === 'Total Time Printing' && meta.hasFullDayPrinting) {
      title.push('Printed all 24 hours');
    }

    return title.join(' | ');
  }

  _handleDateSelection(dateKey) {
    if (!dateKey || !this._hass) {
      return;
    }

    var selectedDate = String(this._stateValue(this._config.selected_date_entity) || "").trim();
    var nextDate = selectedDate === dateKey ? "" : dateKey;

    this._hass.callService("input_text", "set_value", {
      value: nextDate,
    }, {
      entity_id: this._config.selected_date_entity,
    });
  }

  _handlePointSelection(opts, dataset) {
    if (this._suppressPointSelection) {
      return;
    }

    if (!opts || typeof opts.seriesIndex !== "number" || typeof opts.dataPointIndex !== "number") {
      return;
    }

    var series = dataset && Array.isArray(dataset.series) ? dataset.series : [];
    var row = series[opts.seriesIndex];
    var point = row && Array.isArray(row.data) ? row.data[opts.dataPointIndex] : null;
    var meta = point && point.meta ? point.meta : null;
    if (!meta || !meta.dateKey || meta.isFuture || !this._hass) {
      return;
    }

    this._handleDateSelection(meta.dateKey);
  }

  _renderLegend(dataset) {
    if (!this._legendContainer) {
      return;
    }

    var mode = dataset && dataset.mode ? dataset.mode : "Print Count";
    var legend = this._buildLegendConfig(mode);
    if (!legend) {
      this._legendContainer.className = "legend hidden";
      this._legendContainer.innerHTML = "";
      return;
    }

    this._legendContainer.className = "legend";
    this._legendContainer.innerHTML =
      '<div class="legend-scale">' +
      '<span>' + this._escapeHtml(legend.startLabel) + '</span>' +
      '<span class="legend-swatches">' + legend.colors.map(function (color) {
        return '<span class="legend-swatch" style="background:' + this._escapeHtml(color) + '"></span>';
      }.bind(this)).join("") + '</span>' +
      '<span>' + this._escapeHtml(legend.endLabel) + '</span>' +
      (legend.note ? '<span class="legend-note">' + this._escapeHtml(legend.note) + '</span>' : "") +
      '</div>';
  }

  _buildLegendConfig(mode) {
    if (mode === "Dominant Color") {
      return null;
    }

    if (mode === "Outcome") {
      return {
        startLabel: "Cancelled / Failed",
        endLabel: "Completed",
        colors: ["#D32F2F", "#F57C00", "#FBC02D", "#9CCC65", "#2E7D32"],
      };
    }

    var modeConfig = this._modeScaleConfig(mode, { maxCount: 5 });
    return {
      startLabel: "Less",
      endLabel: "More",
      colors: [
        this._emptyCellColor(),
        this._buildIntensityColor(1, 4, modeConfig.startColor, modeConfig.endColor),
        this._buildIntensityColor(2, 4, modeConfig.startColor, modeConfig.endColor),
        this._buildIntensityColor(3, 4, modeConfig.startColor, modeConfig.endColor),
        this._buildIntensityColor(4, 4, modeConfig.startColor, modeConfig.endColor),
      ],
    };
  }

  _renderSummary(archives, grouped, dataset) {
    if (!this._summaryContainer) {
      return;
    }

    var selectedDate = String(this._stateValue(this._config.selected_date_entity) || "").trim();
    var activeDays = Object.keys(grouped).length;
    var summary = [
      this._buildChipHtml(dataset.mode),
      this._buildChipHtml(this._formatCount(activeDays) + " active days"),
      this._buildChipHtml(this._buildSummaryMetricText(archives, dataset.mode)),
    ];

    if (selectedDate) {
      summary.push(this._buildChipHtml(this._formatDateLabel(selectedDate)));
    }

    this._summaryContainer.innerHTML = summary.join("");
  }

  _buildSummaryMetricText(archives, mode) {
    var totalPrints = archives.length;
    var totalWeight = archives.reduce(function (sum, archive) {
      return sum + Number(archive.filamentWeight || 0);
    }, 0);
    var totalObjects = archives.reduce(function (sum, archive) {
      return sum + Number(archive.objectCount || 0);
    }, 0);
    var totalCost = archives.reduce(function (sum, archive) {
      return sum + Number(archive.cost || 0);
    }, 0);
    var totalDuration = archives.reduce(function (sum, archive) {
      return sum + Number(archive.durationHours || 0);
    }, 0);
    var totalFilaments = archives.reduce(function (sum, archive) {
      return sum + Number(archive.filamentCount || 0);
    }, 0);

    if (mode === "Filament Weight") {
      return this._formatWeight(totalWeight);
    }
    if (mode === "Number of Printed Objects") {
      return this._formatCount(totalObjects) + " objects";
    }
    if (mode === "Cost of Prints") {
      return this._formatCost(totalCost);
    }
    if (mode === "Filaments Used") {
      return this._formatCount(totalFilaments) + " filaments used";
    }
    if (mode === "Total Time Printing") {
      return this._formatHours(totalDuration);
    }
    return this._formatCount(totalPrints) + " prints";
  }

  _renderDetails(grouped) {
    if (!this._detailsContainer) {
      return;
    }

    var selectedDate = String(this._stateValue(this._config.selected_date_entity) || "").trim();
    if (!selectedDate) {
      this._detailsContainer.innerHTML = '<div class="details-empty">Tap any day cell to inspect the prints for that date. Use the helper above to clear the selection or manually enter a day.</div>';
      return;
    }

    var day = grouped[selectedDate];
    if (!day || !day.archives || !day.archives.length) {
      this._detailsContainer.innerHTML = '<div class="details-empty">No prints match ' + this._escapeHtml(this._formatDateLabel(selectedDate)) + ' for the current activity scope.</div>';
      return;
    }

    var subtitle = [
      this._formatCount(day.count) + (day.count === 1 ? " print" : " prints"),
      this._formatWeight(day.weight),
      this._formatCount(day.successCount) + " completed",
      this._formatCount(day.failedCount) + " failed",
      this._formatCount(day.cancelledCount) + " cancelled",
    ].join(" | ");
    var items = day.archives.slice(0, this._config.max_detail_items).map(this._buildArchiveCardHtml.bind(this)).join("");
    var extra = day.archives.length > this._config.max_detail_items
      ? '<div class="details-empty">Showing the first ' + this._formatCount(this._config.max_detail_items) + ' prints for this day.</div>'
      : "";

    this._detailsContainer.innerHTML =
      '<div class="detail-header">' +
      '<div>' +
      '<div class="detail-title">' + this._escapeHtml(this._formatDateLabel(selectedDate)) + "</div>" +
      '<div class="detail-subtitle">' + this._escapeHtml(subtitle) + "</div>" +
      "</div>" +
      this._buildChipHtml(day.dominantColor ? ("Dominant " + day.dominantColor.toUpperCase()) : "No dominant color") +
      "</div>" +
      '<div class="detail-grid">' + items + "</div>" +
      extra;
  }

  _buildArchiveCardHtml(archive) {
    var baseUrl = this._trimBaseUrl(this._stateValue(this._config.api_base_entity));
    var thumbHtml = archive.id && baseUrl
      ? '<img class="thumb" loading="lazy" src="' + this._escapeHtml(baseUrl + "/api/v1/archives/" + archive.id + "/thumbnail") + '" alt="">'
      : '<div class="thumb-fallback">3D</div>';
    var metaParts = [this._escapeHtml(archive.formattedDate), this._escapeHtml(archive.printerLabel || ("Printer " + archive.printerId))];
    if (archive.designer) {
      metaParts.push(this._escapeHtml(archive.designer));
    }
    if (archive.layerHeight) {
      metaParts.push(this._escapeHtml(archive.layerHeight + "mm"));
    }

    return (
      '<article class="detail-card">' +
      thumbHtml +
      '<div class="detail-body">' +
      this._buildStatusPill(archive.status) +
      '<div class="detail-name">' + this._escapeHtml(archive.printName) + "</div>" +
      '<div class="detail-meta">' + metaParts.join(" | ") + "</div>" +
      '<div class="detail-stats">' +
      '<span>' + this._escapeHtml(this._formatWeight(archive.filamentWeight)) + "</span>" +
      '<span>' + this._escapeHtml(this._formatHours(archive.durationHours)) + "</span>" +
      '<span>' + this._escapeHtml(this._formatCost(archive.cost)) + "</span>" +
      "</div>" +
      this._buildColorDots(archive.colors) +
      "</div>" +
      "</article>"
    );
  }

  _buildStatusPill(status) {
    var map = {
      completed: { label: "Completed", color: "#2E7D32" },
      failed: { label: "Failed", color: "#C62828" },
      cancelled: { label: "Cancelled", color: "#EF6C00" },
      printing: { label: "Printing", color: "#1565C0" },
      unknown: { label: "Unknown", color: "#546E7A" },
    };
    var entry = map[status] || map.unknown;
    return '<div class="status-pill" style="background:' + this._escapeHtml(entry.color) + '">' + this._escapeHtml(entry.label) + "</div>";
  }

  _buildColorDots(colors) {
    if (!Array.isArray(colors) || !colors.length) {
      return "";
    }
    return '<div class="color-dots">' + colors.slice(0, 6).map(function (color) {
      return '<span class="color-dot" style="background:' + this._escapeHtml(color) + '"></span>';
    }.bind(this)).join("") + "</div>";
  }

  _buildTooltip(meta, mode) {
    if (!meta || !meta.dateKey) {
      return "";
    }

    var lines = [
      '<div style="padding:8px 10px;min-width:180px">',
      '<div style="font-weight:700;margin-bottom:4px">' + this._escapeHtml(meta.label) + "</div>",
      '<div>Prints: <strong>' + this._escapeHtml(this._formatCount(meta.count || 0)) + "</strong></div>",
      '<div>Objects: <strong>' + this._escapeHtml(this._formatCount(meta.objectCount || 0)) + "</strong></div>",
      '<div>Weight: <strong>' + this._escapeHtml(this._formatWeight(meta.weight || 0)) + "</strong></div>",
      '<div>Cost: <strong>' + this._escapeHtml(this._formatCost(meta.cost || 0)) + "</strong></div>",
      '<div>Filaments: <strong>' + this._escapeHtml(this._formatCount(meta.filamentCount || 0)) + "</strong></div>",
      '<div>Time: <strong>' + this._escapeHtml(this._formatHours(meta.durationHours || 0)) + "</strong></div>",
      '<div>Status: <strong>' + this._escapeHtml(this._formatCount(meta.successCount) + " completed, " + this._formatCount(meta.failedCount) + " failed, " + this._formatCount(meta.cancelledCount) + " cancelled") + "</strong></div>",
    ];

    if (mode === "Dominant Color" && meta.dominantColor) {
      lines.push('<div style="display:flex;align-items:center;gap:8px;margin-top:4px"><span style="width:12px;height:12px;border-radius:999px;background:' + this._escapeHtml(meta.dominantColor) + ';display:inline-block"></span><span>Dominant color</span></div>');
    }
    if (mode === "Outcome" && meta.outcomeLabel) {
      lines.push('<div style="margin-top:4px">Outcome band: <strong>' + this._escapeHtml(meta.outcomeLabel) + '</strong></div>');
    }
    if (mode === "Total Time Printing" && meta.hasFullDayPrinting) {
      lines.push('<div style="margin-top:4px">Printed all 24 hours.</div>');
    }
    lines.push("</div>");
    return lines.join("");
  }

  _buildChipHtml(text) {
    return '<span class="chip">' + this._escapeHtml(text) + "</span>";
  }

  _buildIntensityColor(value, maxValue, startColor, endColor) {
    if (!maxValue || value <= 0) {
      return this._emptyCellColor();
    }
    var ratio = Math.max(0.12, Math.min(1, value / maxValue));
    return this._mixHexColors(startColor, endColor, ratio);
  }

  _buildOutcomeColor(day) {
    var band = this._buildOutcomeBand(day);
    var palette = {
      1: "#D32F2F",
      2: "#F57C00",
      3: "#FBC02D",
      4: "#9CCC65",
      5: "#2E7D32",
    };
    return palette[band] || this._emptyCellColor();
  }

  _buildOutcomeBand(day) {
    var total = Number(day.count || 0);
    if (total <= 0) {
      return 0;
    }

    var negatives = Number(day.failedCount || 0) + Number(day.cancelledCount || 0) + Number(day.otherCount || 0);
    var neutrals = Number(day.printingCount || 0);
    var penalty = (negatives + neutrals * 0.5) / total;

    if (penalty >= 0.8) {
      return 1;
    }
    if (penalty >= 0.55) {
      return 2;
    }
    if (penalty >= 0.3) {
      return 3;
    }
    if (penalty > 0) {
      return 4;
    }
    return 5;
  }

  _outcomeBandLabel(band) {
    var labels = {
      1: "Poor",
      2: "Rough",
      3: "Mixed",
      4: "Mostly Good",
      5: "Good",
    };
    return labels[band] || "";
  }

  _normalizeMode(mode) {
    var normalized = String(mode == null ? "" : mode)
      .trim()
      .toLowerCase()
      .replace(/\s+/g, " ");
    var aliases = {
      "print count": "Print Count",
      "filament weight": "Filament Weight",
      "dominant color": "Dominant Color",
      outcome: "Outcome",
      "number of printed objects": "Number of Printed Objects",
      "cost of prints": "Cost of Prints",
      "filaments used": "Filaments Used",
      "total time printing": "Total Time Printing",
    };
      return aliases[normalized] || "Print Count";
  }

  _countDistinctFilaments(archive) {
    var slots = Array.isArray(archive && archive.filament_slots)
      ? archive.filament_slots
      : Array.isArray(archive && archive.extra_data && archive.extra_data.filament_slots)
        ? archive.extra_data.filament_slots
        : [];
    var seen = {};

    slots.forEach(function (slot) {
      var used = this._toNumber(slot && slot.used_g);
      var color = this._normalizeHexColor(slot && slot.color);
      var type = String(slot && slot.type ? slot.type : "").trim().toLowerCase();
      var key = [color || "no-color", type || "no-type"].join("|");
      if (used > 0) {
        seen[key] = true;
      }
    }.bind(this));

    var count = Object.keys(seen).length;
    if (count > 0) {
      return count;
    }

    return String(archive && archive.filament_color ? archive.filament_color : "")
      .split(",")
      .map(function (value) {
        return this._normalizeHexColor(value);
      }.bind(this))
      .filter(Boolean)
      .filter(function (value, index, items) {
        return items.indexOf(value) === index;
      }).length;
  }

  _findDominantColor(colorWeights) {
    var dominant = "";
    var maxWeight = -1;
    Object.keys(colorWeights || {}).forEach(function (color) {
      var weight = Number(colorWeights[color] || 0);
      if (weight > maxWeight) {
        maxWeight = weight;
        dominant = color;
      }
    });
    return dominant;
  }

  _collectColorWeights(archive) {
    var weights = {};
    var slots = Array.isArray(archive.filament_slots) ? archive.filament_slots : [];
    var usableSlots = slots.filter(function (slot) {
      return this._normalizeHexColor(slot && slot.color) && this._toNumber(slot && slot.used_g) > 0;
    }.bind(this));

    if (usableSlots.length) {
      usableSlots.forEach(function (slot) {
        var color = this._normalizeHexColor(slot.color);
        var weight = this._toNumber(slot.used_g);
        weights[color] = (weights[color] || 0) + weight;
      }.bind(this));
      return weights;
    }

    var colors = String(archive.filament_color || "")
      .split(",")
      .map(this._normalizeHexColor.bind(this))
      .filter(Boolean);

    if (!colors.length) {
      return weights;
    }

    var totalWeight = this._toNumber(archive.filament_used_grams) || colors.length;
    var perColor = totalWeight / colors.length;
    colors.forEach(function (color) {
      weights[color] = (weights[color] || 0) + perColor;
    });

    return weights;
  }

  _normalizeStatus(status) {
    var raw = String(status || "").toLowerCase();
    if (raw === "completed" || raw === "success") {
      return "completed";
    }
    if (raw === "failed") {
      return "failed";
    }
    if (raw === "cancelled" || raw === "aborted" || raw === "stopped") {
      return "cancelled";
    }
    if (raw === "printing") {
      return "printing";
    }
    return raw || "unknown";
  }

  _normalizeHexColor(value) {
    var raw = String(value || "").trim();
    if (!raw) {
      return "";
    }
    if (raw.charAt(0) !== "#") {
      raw = "#" + raw;
    }
    if (/^#[0-9a-fA-F]{8}$/.test(raw)) {
      raw = raw.slice(0, 7);
    }
    if (!/^#[0-9a-fA-F]{6}$/.test(raw)) {
      return "";
    }
    return raw.toLowerCase();
  }

  _isOn(entityId) {
    return this._stateValue(entityId) === "on";
  }

  _toNumber(value) {
    var parsed = Number(value);
    return isFinite(parsed) ? parsed : 0;
  }

  _secondsToHours(value) {
    var seconds = this._toNumber(value);
    return seconds > 0 ? seconds / 3600 : 0;
  }

  _formatHours(hours) {
    var value = this._toNumber(hours);
    if (!value) {
      return "0h";
    }
    return this._formatDecimal(value, 1) + "h";
  }

  _formatWeight(weight) {
    return this._formatDecimal(weight, 1) + "g";
  }

  _formatCost(cost) {
    var value = this._toNumber(cost);
    return "$" + this._formatDecimal(value, 2);
  }

  _formatCount(value) {
    return new Intl.NumberFormat(undefined, {
      maximumFractionDigits: 0,
    }).format(this._toNumber(value));
  }

  _formatDecimal(value, digits) {
    return new Intl.NumberFormat(undefined, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(this._toNumber(value));
  }

  _formatDateTime(date) {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZone: this._haTimeZone(),
    }).format(date);
  }

  _formatDateLabel(dateKey) {
    var date = this._dateFromDateKey(dateKey);
    if (!date) {
      return dateKey;
    }
    return new Intl.DateTimeFormat(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    }).format(date);
  }

  _formatWeekLabel(weekKey, weekKeys, index) {
    if (index < 0) {
      return "";
    }
    var currentDate = this._dateFromDateKey(weekKey);
    if (!currentDate) {
      return "";
    }
    if (index === 0) {
      return new Intl.DateTimeFormat(undefined, { month: "short", timeZone: "UTC" }).format(currentDate);
    }
    var previousKey = weekKeys[index - 1];
    var previousDate = previousKey ? this._dateFromDateKey(previousKey) : null;
    if (!previousDate || previousDate.getUTCMonth() !== currentDate.getUTCMonth()) {
      return new Intl.DateTimeFormat(undefined, { month: "short", timeZone: "UTC" }).format(currentDate);
    }
    return "";
  }

  _parseDate(value) {
    var raw = String(value || "");
    var normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(raw) ? raw : raw + "Z";
    var parsed = new Date(normalized);
    return isNaN(parsed.getTime()) ? null : parsed;
  }

  _formatLocalDate(date) {
    var parts = new Intl.DateTimeFormat("en-US", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      timeZone: this._haTimeZone(),
    }).formatToParts(date);
    var year = "";
    var month = "";
    var day = "";
    parts.forEach(function (part) {
      if (part.type === "year") {
        year = part.value;
      } else if (part.type === "month") {
        month = part.value;
      } else if (part.type === "day") {
        day = part.value;
      }
    });
    if (!year || !month || !day) {
      year = String(date.getUTCFullYear());
      month = String(date.getUTCMonth() + 1).padStart(2, "0");
      day = String(date.getUTCDate()).padStart(2, "0");
    }
    return year + "-" + month + "-" + day;
  }

  _dateFromDateKey(dateKey) {
    var match = String(dateKey || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!match) {
      return null;
    }
    return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 12, 0, 0));
  }

  _shiftDateKey(dateKey, amount) {
    var date = this._dateFromDateKey(dateKey);
    if (!date) {
      return "";
    }
    date.setUTCDate(date.getUTCDate() + amount);
    return [
      String(date.getUTCFullYear()),
      String(date.getUTCMonth() + 1).padStart(2, "0"),
      String(date.getUTCDate()).padStart(2, "0"),
    ].join("-");
  }

  _startOfWeekKey(dateKey, startDay) {
    var date = this._dateFromDateKey(dateKey);
    if (!date) {
      return "";
    }
    var diff = (date.getUTCDay() - startDay + 7) % 7;
    return this._shiftDateKey(dateKey, -diff);
  }

  _haTimeZone() {
    return this._hass && this._hass.config && this._hass.config.time_zone
      ? String(this._hass.config.time_zone)
      : undefined;
  }

  _startOfDay(date) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate());
  }

  _startOfWeek(date, startDay) {
    var current = this._startOfDay(date);
    var diff = (current.getDay() - startDay + 7) % 7;
    return this._addDays(current, -diff);
  }

  _addDays(date, amount) {
    var copy = new Date(date.getTime());
    copy.setDate(copy.getDate() + amount);
    return copy;
  }

  _futureCellColor() {
    return this._withAlpha(this._themeColor(["--divider-color", "--secondary-background-color"], "#94a3b8"), 0.08, "rgba(148,163,184,0.08)");
  }

  _emptyCellColor() {
    return this._withAlpha(this._themeColor(["--divider-color", "--secondary-background-color"], this._hass && this._hass.themes && this._hass.themes.darkMode ? "#94a3b8" : "#cbd5e1"), this._hass && this._hass.themes && this._hass.themes.darkMode ? 0.18 : 0.24, this._hass && this._hass.themes && this._hass.themes.darkMode ? "rgba(148,163,184,0.18)" : "rgba(203,213,225,0.24)");
  }

  _pointStrokeColor(isFuture, hasData) {
    if (isFuture) {
      return this._withAlpha(this._themeColor(["--divider-color", "--secondary-text-color"], "#94a3b8"), 0.22, "rgba(148,163,184,0.22)");
    }
    return hasData
      ? this._withAlpha(this._themeColor(["--divider-color", "--secondary-text-color"], "#64748b"), 0.34, "rgba(100,116,139,0.34)")
      : this._withAlpha(this._themeColor(["--divider-color", "--secondary-text-color"], "#94a3b8"), 0.22, "rgba(148,163,184,0.22)");
  }

  _themeColor(variableNames, fallback) {
    if (typeof window === "undefined" || typeof window.getComputedStyle !== "function") {
      return fallback;
    }

    var names = Array.isArray(variableNames) ? variableNames : [variableNames];
    var targets = [this, this._chartContainer, document.documentElement];
    for (var targetIndex = 0; targetIndex < targets.length; targetIndex += 1) {
      var target = targets[targetIndex];
      if (!target) {
        continue;
      }
      var styles = window.getComputedStyle(target);
      for (var nameIndex = 0; nameIndex < names.length; nameIndex += 1) {
        var value = styles.getPropertyValue(names[nameIndex]);
        if (value && value.trim()) {
          return value.trim();
        }
      }
    }

    return fallback;
  }

  _withAlpha(color, alpha, fallback) {
    var rgb = this._parseColor(color || fallback);
    if (!rgb) {
      return fallback || color;
    }
    return "rgba(" + rgb.r + "," + rgb.g + "," + rgb.b + "," + Math.max(0, Math.min(1, alpha)) + ")";
  }

  _parseColor(color) {
    var value = String(color || "").trim();
    var normalizedHex = this._normalizeHexColor(value);
    var match;

    if (normalizedHex) {
      return this._hexToRgb(normalizedHex);
    }

    match = value.match(/^rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
    if (match) {
      return {
        r: Math.max(0, Math.min(255, parseInt(match[1], 10))),
        g: Math.max(0, Math.min(255, parseInt(match[2], 10))),
        b: Math.max(0, Math.min(255, parseInt(match[3], 10))),
      };
    }

    return null;
  }

  _mixHexColors(startColor, endColor, ratio) {
    var start = this._hexToRgb(startColor);
    var end = this._hexToRgb(endColor);
    var clamped = Math.max(0, Math.min(1, ratio));
    var mixed = {
      r: Math.round(start.r + (end.r - start.r) * clamped),
      g: Math.round(start.g + (end.g - start.g) * clamped),
      b: Math.round(start.b + (end.b - start.b) * clamped),
    };
    return this._rgbToHex(mixed.r, mixed.g, mixed.b);
  }

  _hexToRgb(color) {
    var normalized = this._normalizeHexColor(color) || "#000000";
    return {
      r: parseInt(normalized.slice(1, 3), 16),
      g: parseInt(normalized.slice(3, 5), 16),
      b: parseInt(normalized.slice(5, 7), 16),
    };
  }

  _rgbToHex(red, green, blue) {
    return "#" + [red, green, blue].map(function (channel) {
      return Math.max(0, Math.min(255, channel)).toString(16).padStart(2, "0");
    }).join("");
  }

  _hslToHex(hue, saturation, lightness) {
    var h = ((hue % 360) + 360) % 360;
    var s = Math.max(0, Math.min(100, saturation)) / 100;
    var l = Math.max(0, Math.min(100, lightness)) / 100;
    var c = (1 - Math.abs(2 * l - 1)) * s;
    var x = c * (1 - Math.abs((h / 60) % 2 - 1));
    var m = l - c / 2;
    var rgb;

    if (h < 60) {
      rgb = [c, x, 0];
    } else if (h < 120) {
      rgb = [x, c, 0];
    } else if (h < 180) {
      rgb = [0, c, x];
    } else if (h < 240) {
      rgb = [0, x, c];
    } else if (h < 300) {
      rgb = [x, 0, c];
    } else {
      rgb = [c, 0, x];
    }

    return this._rgbToHex(
      Math.round((rgb[0] + m) * 255),
      Math.round((rgb[1] + m) * 255),
      Math.round((rgb[2] + m) * 255)
    );
  }

  _trimBaseUrl(baseUrl) {
    var value = String(baseUrl || "").trim();
    if (!value) {
      return "";
    }
    return value.endsWith("/") ? value.slice(0, -1) : value;
  }

  async _ensureApexCharts() {
    if (window.ApexCharts) {
      return window.ApexCharts;
    }

    if (!printHistoryActivityReadyPromise) {
      printHistoryActivityReadyPromise = this._resolveApexCharts();
    }

    return printHistoryActivityReadyPromise;
  }

  async _resolveApexCharts() {
    if (window.ApexCharts) {
      return window.ApexCharts;
    }

    await this._waitForApexRuntime();
    if (window.ApexCharts) {
      return window.ApexCharts;
    }

    if (!printHistoryActivityImportTried) {
      printHistoryActivityImportTried = true;
      try {
        await import("/hacsfiles/apexcharts-card/apexcharts-card.js");
      } catch (_err) {
        // Ignore import errors and allow fallback checks below.
      }
    }

    await this._waitForApexRuntime();
    return window.ApexCharts || null;
  }

  async _waitForApexRuntime() {
    if (window.ApexCharts) {
      return;
    }

    if (typeof customElements !== "undefined" && customElements.whenDefined) {
      try {
        await Promise.race([
          customElements.whenDefined("apexcharts-card"),
          new Promise(function (resolve) { setTimeout(resolve, 800); }),
        ]);
      } catch (_err) {
        // Ignore and continue polling for the runtime.
      }
    }

    for (var attempt = 0; attempt < 8; attempt += 1) {
      if (window.ApexCharts) {
        return;
      }
      await new Promise(function (resolve) { setTimeout(resolve, 100); });
    }
  }

  _showError(message) {
    this._destroyChart();
    if (this._chartContainer) {
      this._chartContainer.innerHTML = '<div class="error">' + this._escapeHtml(message) + "</div>";
    }
  }

  _escapeHtml(input) {
    return String(input)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
}

if (!customElements.get("print-history-activity-heatmap-card")) {
  customElements.define("print-history-activity-heatmap-card", PrintHistoryActivityHeatmapCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.find(function (card) { return card.type === "print-history-activity-heatmap-card"; })) {
  window.customCards.push({
    type: "print-history-activity-heatmap-card",
    name: "Print History Activity Heatmap Card",
    preview: false,
    description: "GitHub-style daily heatmap for Bambuddy print history using ApexCharts.",
  });
}
