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
    this._dataSignature = "";
    this._selectionSignature = "";
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
    this._loading = false;
    this._refreshing = false;
    this._renderModel = null;
    this._tooltipFrame = 0;
    this._lastTooltipAnchor = null;
    this._boundTooltipMoveHandler = null;
    this._boundTooltipLeaveHandler = null;
    this._legendSelectedMode = "";
    this._legendSelectedIndex = -1;
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
      activity_metric_filter_entity: config.activity_metric_filter_entity || "input_select.print_history_filter_activity_metric",
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

    this._dataSignature = "";
    this._selectionSignature = "";
    this._renderModel = null;
    this._renderShell();
    this._queueRender();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) {
      return;
    }

    var dataSignature = JSON.stringify(this._buildDataSignature(hass));
    var selectionSignature = JSON.stringify(this._buildSelectionSignature(hass));

    if (dataSignature !== this._dataSignature) {
      this._dataSignature = dataSignature;
      this._selectionSignature = selectionSignature;
      this._queueRender();
      return;
    }

    if (selectionSignature !== this._selectionSignature) {
      this._selectionSignature = selectionSignature;
      this._applySelectionOnlyState();
    }
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
    this._detachTooltipTracking();
    if (this._chart && typeof this._chart.destroy === "function") {
      this._chart.destroy();
      this._chart = null;
    }
  }

  getCardSize() {
    return 10;
  }

  _buildDataSignature(hass) {
    var sourceState = this._config.source_entity ? hass.states[this._config.source_entity] : null;
    var metricState = hass.states[this._config.mode_entity];
    var apiBaseState = hass.states[this._config.api_base_entity];
    var filteredState = hass.states["sensor.bambuddy_print_history_browser_filtered"];
    var activityMetricFilterState = hass.states[this._config.activity_metric_filter_entity];

    return {
      sourceState: sourceState ? sourceState.state : "",
      sourceFetch: sourceState && sourceState.attributes ? sourceState.attributes.last_fetch || "" : "",
      filteredRevision: filteredState && filteredState.attributes ? String(filteredState.attributes.browser_revision || "") : "",
      metric: metricState ? metricState.state : "",
      activityMetricFilter: activityMetricFilterState ? activityMetricFilterState.state : "",
      apiBase: apiBaseState ? apiBaseState.state : "",
      status: this._stateValue("input_select.print_history_filter_status"),
      material: this._stateValue("input_select.print_history_filter_material"),
      printer: this._stateValue("input_select.print_history_filter_printer"),
      dateRange: this._stateValue("input_select.print_history_filter_date_range"),
      startDate: this._stateValue("input_text.print_history_filter_start_date"),
      endDate: this._stateValue("input_text.print_history_filter_end_date"),
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

  _buildSelectionSignature(hass) {
    var selectedDateState = hass.states[this._config.selected_date_entity];

    return {
      selectedDate: selectedDateState ? selectedDateState.state : "",
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
      ".chart-wrap.loading{overflow:hidden;}" +
      ".refresh-indicator{position:absolute;top:10px;right:10px;display:inline-flex;align-items:center;gap:6px;min-height:28px;padding:0 10px;border-radius:999px;background:rgba(15,23,42,0.68);border:1px solid rgba(255,255,255,0.10);backdrop-filter:blur(8px);color:#fff;font-size:11px;font-weight:700;line-height:1.1;letter-spacing:0.01em;z-index:5;pointer-events:none;box-shadow:0 8px 18px rgba(15,23,42,0.16);}" +
      ".refresh-indicator.hidden{display:none;}" +
      ".refresh-indicator.error{background:rgba(127,29,29,0.88);border-color:rgba(254,202,202,0.28);color:#fee2e2;}" +
      ".refresh-dot{width:8px;height:8px;border-radius:999px;background:currentColor;opacity:0.9;}" +
      ".apexcharts-tooltip{pointer-events:none;border:1px solid rgba(148,163,184,0.18);border-radius:14px;box-shadow:0 18px 40px rgba(15,23,42,0.22);overflow:hidden;}" +
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
      ".legend-main{display:inline-flex;align-items:center;gap:8px;}" +
      ".legend-swatches{display:inline-flex;align-items:center;gap:6px;}" +
      ".legend-swatch{appearance:none;-webkit-appearance:none;border:none;outline:none;padding:0;margin:0;display:inline-block;width:14px;height:14px;border-radius:4px;background:var(--cell-empty,rgba(148,163,184,0.14));box-shadow:none;line-height:0;cursor:default;transition:box-shadow 0.2s ease, transform 0.2s ease;}" +
      ".legend-swatch.interactive{cursor:pointer;}" +
      ".legend-swatch.interactive:hover{transform:scale(1.1);box-shadow:0 0 4px rgba(59,130,246,0.4);}" +
      ".legend-swatch.interactive:active{transform:scale(0.95);}" +
      ".legend-swatch.interactive:focus-visible{box-shadow:0 0 0 2px rgba(37,99,235,0.75);}" +
      ".legend-swatch.active{box-shadow:0 0 8px rgba(37,99,235,0.6), inset 0 0 0 2px rgba(37,99,235,1);border-radius:6px;}" +
      ".legend-note{font-size:11px;color:var(--secondary-text-color);opacity:0.9;}" +
      ".legend-separator{opacity:0.7;}" +
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
      "@keyframes printHistoryHeatmapShimmer{0%{background-position:200% 0;}100%{background-position:-200% 0;}}" +
      ".loading-shell{display:grid;gap:8px;}" +
      ".loading-month-row{display:grid;grid-template-columns:40px minmax(0,1fr);column-gap:10px;align-items:start;margin-top:6px;}" +
      ".loading-month-labels{display:grid;grid-template-columns:repeat(var(--week-count,53), minmax(var(--cell-size,10px),1fr));column-gap:4px;align-items:center;min-height:14px;}" +
      ".loading-grid{display:grid;grid-template-columns:40px minmax(0,1fr);column-gap:10px;align-items:start;}" +
      ".loading-day-labels{display:grid;grid-template-rows:repeat(7,var(--cell-size,18px));row-gap:4px;}" +
      ".loading-cells{display:grid;grid-template-rows:repeat(7,var(--cell-size,18px));row-gap:4px;}" +
      ".loading-row{display:grid;grid-template-columns:repeat(var(--week-count,53), minmax(var(--cell-size,10px),1fr));column-gap:4px;}" +
      ".loading-swatch-row{display:flex;justify-content:flex-end;align-items:center;gap:6px;min-height:18px;}" +
      ".loading-summary{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;}" +
      ".loading-pill,.loading-text,.loading-cell,.loading-swatch{position:relative;overflow:hidden;background:rgba(148,163,184,0.16);}" +
      ".loading-pill::after,.loading-text::after,.loading-cell::after,.loading-swatch::after{content:'';position:absolute;inset:0;background:linear-gradient(90deg, rgba(255,255,255,0), rgba(255,255,255,0.18), rgba(255,255,255,0));background-size:200% 100%;animation:printHistoryHeatmapShimmer 1.35s ease-in-out infinite;}" +
      ".loading-pill{height:30px;border-radius:999px;}" +
      ".loading-text{height:11px;border-radius:999px;align-self:center;}" +
      ".loading-cell{height:var(--cell-size,18px);border-radius:4px;}" +
      ".loading-swatch{width:14px;height:14px;border-radius:4px;}" +
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
    var showLoadingState = !self._renderModel;
    self._loading = true;
    self._refreshing = !showLoadingState;
    if (showLoadingState) {
      self._renderLoadingState();
    } else {
      self._showRefreshIndicator("Updating...");
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
          self._showError(self._describeRenderError(err));
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
      this._detachTooltipTracking();
      this._hideRefreshIndicator();
      this._loading = false;
      this._refreshing = false;
      return;
    }

    this._setHiddenState(false);

    if (!this._hasRenderableWidth()) {
      this._lastObservedWidth = 0;
      return;
    }

    try {
      await this._ensureDirectQueryData();

      var archives = this._getScopedArchives();
      var grouped = this._groupArchivesByDate(archives);
      var dataset = this._buildHeatmapDataset(grouped, this._resolveVisibleWeeks());
      var layout = this._buildChartLayout(dataset.weekKeys.length);
      this._renderModel = {
        archives: archives,
        grouped: grouped,
        dataset: dataset,
      };

      this._applyChartLayout(layout);

      this._renderLegend(dataset);
      this._renderSummary(archives, grouped, dataset);
      this._renderDetails(grouped);

      if (!dataset.hasAnyPastCells) {
        this._destroyChart();
        this._chartContainer.classList.remove("loading");
        this._chartContainer.innerHTML = '<div class="details-empty">No print history data is available for the current scope. Refresh the archive cache or relax the filters.</div>';
        this._hideRefreshIndicator();
        return;
      }

      var ApexChartsCtor = await this._ensureApexCharts();
      if (!ApexChartsCtor) {
        this._renderHeatmap(dataset);
        this._detachTooltipTracking();
        this._hideRefreshIndicator();
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
      this._attachTooltipTracking();
      this._applyEnrichmentPatternFills(dataset);
      await this._ensureChartVisible(dataset);
      await this._applySelectedVisualState(dataset);
      this._hideRefreshIndicator();
      this._recordDebug(renderStarted, dataset);
    } finally {
      this._loading = false;
      this._refreshing = false;
    }
  }

  _renderLoadingState() {
    if (!this._chartContainer || !this._config || !this._isVisible()) {
      return;
    }

    this._hideRefreshIndicator();

    var weekCount = this._resolveVisibleWeeks();
    var monthLabels = [];
    var dayLabels = [];
    var rows = [];
    var swatches = [];
    var chips = [];
    var index = 0;

    for (index = 0; index < 5; index += 1) {
      monthLabels.push('<span class="loading-text" style="width:' + String(index === 4 ? 48 : 34) + 'px;"></span>');
    }
    for (index = 0; index < 7; index += 1) {
      dayLabels.push('<span class="loading-text" style="width:' + String(index % 2 === 0 ? 22 : 16) + 'px;"></span>');
    }
    for (var row = 0; row < 7; row += 1) {
      var cells = [];
      for (var col = 0; col < weekCount; col += 1) {
        cells.push('<span class="loading-cell"></span>');
      }
      rows.push('<div class="loading-row">' + cells.join('') + '</div>');
    }
    for (index = 0; index < 5; index += 1) {
      swatches.push('<span class="loading-swatch"></span>');
    }
    for (index = 0; index < 3; index += 1) {
      chips.push('<span class="loading-pill" style="width:' + String(index === 1 ? 132 : 104) + 'px;"></span>');
    }

    this._destroyChart();
    this._chartContainer.classList.add("loading");
    this._chartContainer.innerHTML = '' +
      '<div class="loading-shell" style="--week-count:' + this._escapeHtml(String(weekCount || 53)) + '">' +
        '<div class="loading-grid"><div class="loading-day-labels">' + dayLabels.join('') + '</div><div class="loading-cells">' + rows.join('') + '</div></div>' +
        '<div class="loading-month-row"><span></span><div class="loading-month-labels">' + monthLabels.join('') + '</div></div>' +
      '</div>';
    if (this._legendContainer) {
      this._legendContainer.classList.remove("hidden");
      this._legendContainer.innerHTML = '<div class="loading-swatch-row">' + swatches.join('') + '</div>';
    }
    if (this._summaryContainer && !this._config.hide_summary) {
      this._summaryContainer.innerHTML = '<div class="loading-summary">' + chips.join('') + '</div>';
    }
    if (this._detailsContainer) {
      this._detailsContainer.innerHTML = "";
    }
  }

  _destroyChart() {
    this._detachTooltipTracking();
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
    this._chartContainer.classList.remove("loading");
    this._hideRefreshIndicator();
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

  _attachTooltipTracking() {
    if (!this._chartContainer) {
      return;
    }

    this._detachTooltipTracking();

    this._boundTooltipMoveHandler = function (event) {
      var target = event && event.target && typeof event.target.closest === "function"
        ? event.target.closest(".apexcharts-heatmap-rect")
        : null;
      if (!target) {
        return;
      }
      this._lastTooltipAnchor = target;
      this._queueTooltipPosition(target);
    }.bind(this);

    this._boundTooltipLeaveHandler = function () {
      this._lastTooltipAnchor = null;
    }.bind(this);

    this._chartContainer.addEventListener("mousemove", this._boundTooltipMoveHandler);
    this._chartContainer.addEventListener("mouseleave", this._boundTooltipLeaveHandler);
  }

  _detachTooltipTracking() {
    if (this._tooltipFrame) {
      cancelAnimationFrame(this._tooltipFrame);
      this._tooltipFrame = 0;
    }

    if (this._chartContainer && this._boundTooltipMoveHandler) {
      this._chartContainer.removeEventListener("mousemove", this._boundTooltipMoveHandler);
    }
    if (this._chartContainer && this._boundTooltipLeaveHandler) {
      this._chartContainer.removeEventListener("mouseleave", this._boundTooltipLeaveHandler);
    }

    this._boundTooltipMoveHandler = null;
    this._boundTooltipLeaveHandler = null;
    this._lastTooltipAnchor = null;
  }

  _queueTooltipPosition(anchorElement) {
    if (this._tooltipFrame) {
      cancelAnimationFrame(this._tooltipFrame);
    }

    this._tooltipFrame = requestAnimationFrame(function () {
      this._tooltipFrame = 0;
      this._positionTooltip(anchorElement || this._lastTooltipAnchor);
    }.bind(this));
  }

  _positionTooltip(anchorElement) {
    if (!this._chartContainer || !anchorElement) {
      return;
    }

    var tooltip = this._chartContainer.querySelector(".apexcharts-tooltip.apexcharts-active");
    if (!tooltip) {
      return;
    }

    var containerRect = this._chartContainer.getBoundingClientRect();
    var anchorRect = anchorElement.getBoundingClientRect();
    var tooltipRect = tooltip.getBoundingClientRect();

    if (!containerRect.width || !anchorRect.width || !tooltipRect.width || !tooltipRect.height) {
      return;
    }

    var gap = 10;
    var left = anchorRect.left - containerRect.left + anchorRect.width / 2 - tooltipRect.width / 2;
    var minLeft = 8;
    var maxLeft = Math.max(minLeft, containerRect.width - tooltipRect.width - 8);
    var clampedLeft = Math.max(minLeft, Math.min(maxLeft, left));
    var top = anchorRect.bottom - containerRect.top + gap;

    tooltip.style.left = this._formatDecimal(clampedLeft, 3) + "px";
    tooltip.style.top = this._formatDecimal(top, 3) + "px";
    tooltip.style.right = "auto";
    tooltip.style.bottom = "auto";
    tooltip.style.transform = "none";
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
      start_date: String(this._stateValue("input_text.print_history_filter_start_date") || "").trim(),
      end_date: String(this._stateValue("input_text.print_history_filter_end_date") || "").trim(),
      designer: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_designer")),
      project: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_project")),
      layer_height: this._normalizeFilterValue(this._stateValue("input_select.print_history_filter_layer_height")),
      tags: String(this._stateValue("input_text.print_history_filter_tags") || "").trim(),
      tag_mode: this._normalizeTagModeValue(this._stateValue("input_select.print_history_filter_tags_mode")),
      tag_untagged_only: this._isOn("input_boolean.print_history_filter_tags_untagged_only"),
      favorites_only: this._isOn("input_boolean.print_history_filter_favorites_only"),
      search: String(this._stateValue("input_text.print_history_search") || "").trim(),
      colors: String(this._stateValue("input_text.print_history_filter_colors") || "").trim(),
      sort: this._normalizeFilterValue(this._stateValue("input_select.print_history_sort")),
      activity_metric: this._normalizeFilterValue(this._stateValue(this._config.mode_entity)),
      activity_metric_filter: this._normalizeFilterValue(this._stateValue(this._config.activity_metric_filter_entity)),
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

  _normalizeTagModeValue(value) {
    return String(value || "").trim() === "All" ? "All" : "Any";
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
    var enrichmentPayload = this._extractEnrichmentPayload(archive && archive.notes);
    var enrichmentRows = Array.isArray(enrichmentPayload.F) ? enrichmentPayload.F : [];
    var filamentIdentityKeys = this._collectFilamentIdentityKeys(archive || {}, enrichmentRows);

    if (!dateKey && date) {
      dateKey = this._formatLocalDate(date);
    }

    return {
      id: archive && archive.id != null ? archive.id : null,
      originalArchiveId: archive && archive.original_archive_id != null ? String(archive.original_archive_id) : "",
      printName: archive && archive.print_name ? String(archive.print_name) : "Unnamed",
      printerId: archive && archive.printer_id != null ? String(archive.printer_id) : "Unknown printer",
      printerName: archive && archive.printer_name ? String(archive.printer_name) : "",
      printerLabel: archive && archive.printer_name ? String(archive.printer_name) : (archive && archive.printer_id != null ? String(archive.printer_id) : "Unknown printer"),
      filamentType: archive && archive.filament_type ? String(archive.filament_type) : "",
      designer: archive && archive.designer ? String(archive.designer) : "",
      projectName: archive && archive.project_name ? String(archive.project_name) : "",
      hasProject: this._archiveHasProject(archive),
      failureReason: archive && archive.failure_reason ? String(archive.failure_reason) : "",
      isFavorite: !!(archive && archive.is_favorite),
      duplicateSimilarCount: this._archiveDuplicateSimilarCount(archive),
      status: this._normalizeStatus(archive && archive.status),
      rawStatus: archive && archive.status ? String(archive.status) : "",
      enrichmentStatus: this._normalizeEnrichmentStatus(archive && archive.enrichment_status, enrichmentRows),
      timestamp: date,
      dateKey: dateKey,
      formattedDate: date ? this._formatDateTime(date) : "Unknown date",
      objectCount: Math.max(1, this._toNumber(archive && archive.object_count)),
      filamentWeight: this._toNumber(archive && archive.filament_used_grams),
      storageBytes: this._archiveStorageBytes(archive),
      filamentCount: this._countDistinctFilaments(archive),
      filamentIdentityKeys: filamentIdentityKeys,
      colorMode: this._resolveSingleMultiState(filamentIdentityKeys, colors),
      durationHours: this._secondsToHours(
        archive && (
          archive.effective_duration_seconds != null
            ? archive.effective_duration_seconds
            : (archive.actual_time_seconds != null ? archive.actual_time_seconds : archive.print_time_seconds)
        )
      ),
      cost: this._toNumber(archive && archive.cost),
      layerHeight: archive && archive.layer_height != null && archive.layer_height !== "" ? String(archive.layer_height) : "",
      tags: archive && archive.tags ? String(archive.tags) : "",
      userTags: this._userTags(archive && archive.tags),
      colors: colors,
      colorWeights: colorWeights,
    };
  }

  _matchesFilters(archive) {
    var statusValue = this._stateValue("input_select.print_history_filter_status");
    var materialValue = this._stateValue("input_select.print_history_filter_material");
    var printerValue = this._stateValue("input_select.print_history_filter_printer");
    var dateRangeValue = this._stateValue("input_select.print_history_filter_date_range");
    var startDateValue = String(this._stateValue("input_text.print_history_filter_start_date") || "").trim().slice(0, 10);
    var endDateValue = String(this._stateValue("input_text.print_history_filter_end_date") || "").trim().slice(0, 10);
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
    var searchBlob = [
      archive.id,
      archive.originalArchiveId,
      archive.printerId,
      archive.printName,
      archive.printerName,
      archive.designer,
      archive.projectName,
      archive.failureReason,
      archive.tags,
    ]
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
    if (matchesDate && startDateValue) {
      matchesDate = !!archive.dateKey && archive.dateKey >= startDateValue;
    }
    if (matchesDate && endDateValue) {
      matchesDate = !!archive.dateKey && archive.dateKey <= endDateValue;
    }
    if (startDateValue && endDateValue && startDateValue > endDateValue) {
      matchesDate = false;
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
            storageBytes: 0,
            cost: 0,
            filamentCount: 0,
            uniqueTagCount: 0,
            uniqueFilamentCount: 0,
            favoriteCount: 0,
            inProjectCount: 0,
            notInProjectCount: 0,
            duplicateSimilarCount: 0,
            singleColorCount: 0,
            multiColorCount: 0,
            durationHours: 0,
            successCount: 0,
            archivedCount: 0,
            failedCount: 0,
            cancelledCount: 0,
            printingCount: 0,
            otherCount: 0,
            colorWeights: {},
            uniqueTags: {},
            uniqueFilamentKeys: {},
            enrichmentCounts: this._emptyEnrichmentCounts(),
          };
        }

        var day = accumulator[key];
        day.archives.push(archive);
        day.count += 1;
        day.objectCount += archive.objectCount;
        day.weight += archive.filamentWeight;
        day.storageBytes += archive.storageBytes;
        day.cost += archive.cost;
        day.durationHours += archive.durationHours;
        day.filamentCount += archive.filamentCount;
        day.favoriteCount += archive.isFavorite ? 1 : 0;
        day.inProjectCount += archive.hasProject ? 1 : 0;
        day.notInProjectCount += archive.hasProject ? 0 : 1;
        day.duplicateSimilarCount += Number(archive.duplicateSimilarCount || 0);

        (archive.userTags || []).forEach(function (tag) {
          day.uniqueTags[String(tag).toLowerCase()] = true;
        });
        (archive.filamentIdentityKeys || []).forEach(function (keyValue) {
          day.uniqueFilamentKeys[keyValue] = true;
        });

        if (archive.colorMode === "single") {
          day.singleColorCount += 1;
        } else if (archive.colorMode === "multi") {
          day.multiColorCount += 1;
        }

        day.enrichmentCounts[archive.enrichmentStatus || "not defined"] = (day.enrichmentCounts[archive.enrichmentStatus || "not defined"] || 0) + 1;

        if (archive.status === "completed") {
          day.successCount += 1;
        } else if (archive.status === "archived") {
          day.archivedCount += 1;
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
      }.bind(this),
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
    var maxStorageBytes = 0;
    var maxCost = 0;
    var maxFilamentCount = 0;
    var maxDurationHours = 0;
    var maxUniqueTagCount = 0;
    var maxUniqueFilamentCount = 0;
    var maxFavoriteCount = 0;
    var maxDuplicateSimilarCount = 0;

    keys.forEach(function (key) {
      var day = grouped[key];
      maxCount = Math.max(maxCount, day.count || 0);
      maxObjectCount = Math.max(maxObjectCount, day.objectCount || 0);
      maxWeight = Math.max(maxWeight, day.weight || 0);
      maxStorageBytes = Math.max(maxStorageBytes, day.storageBytes || 0);
      maxCost = Math.max(maxCost, day.cost || 0);
      maxFilamentCount = Math.max(maxFilamentCount, day.filamentCount || 0);
      maxDurationHours = Math.max(maxDurationHours, day.durationHours || 0);
      day.uniqueTagCount = Object.keys(day.uniqueTags || {}).length;
      day.uniqueFilamentCount = Object.keys(day.uniqueFilamentKeys || {}).length;
      maxUniqueTagCount = Math.max(maxUniqueTagCount, day.uniqueTagCount || 0);
      maxUniqueFilamentCount = Math.max(maxUniqueFilamentCount, day.uniqueFilamentCount || 0);
      maxFavoriteCount = Math.max(maxFavoriteCount, day.favoriteCount || 0);
      maxDuplicateSimilarCount = Math.max(maxDuplicateSimilarCount, day.duplicateSimilarCount || 0);
      day.dominantColor = this._findDominantColor(day.colorWeights);
      day.outcomeColor = this._buildOutcomeColor(day);
      day.outcomeBand = this._buildOutcomeBand(day);
      day.singleMultiColor = this._buildSingleMultiColor(day);
      day.singleMultiLabel = this._buildSingleMultiLabel(day);
      day.projectMembershipColor = this._buildProjectMembershipColor(day);
      day.projectMembershipLabel = this._buildProjectMembershipLabel(day);
      day.enrichmentColor = this._buildEnrichmentColor(day);
      day.enrichmentBackground = this._buildEnrichmentBackground(day);
      day.enrichmentLabel = this._buildEnrichmentLabel(day);
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
          maxStorageBytes: maxStorageBytes,
          maxCost: maxCost,
          maxFilamentCount: maxFilamentCount,
          maxDurationHours: maxDurationHours,
          maxUniqueTagCount: maxUniqueTagCount,
          maxUniqueFilamentCount: maxUniqueFilamentCount,
          maxFavoriteCount: maxFavoriteCount,
          maxDuplicateSimilarCount: maxDuplicateSimilarCount,
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
        maxStorageBytes: maxStorageBytes,
        maxCost: maxCost,
        maxFilamentCount: maxFilamentCount,
        maxDurationHours: maxDurationHours,
        maxUniqueTagCount: maxUniqueTagCount,
        maxUniqueFilamentCount: maxUniqueFilamentCount,
        maxFavoriteCount: maxFavoriteCount,
        maxDuplicateSimilarCount: maxDuplicateSimilarCount,
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
      } else if (input.mode === "Storage Used") {
        value = Number(stats.storageBytes || 0);
        color = this._buildIntensityColor(value, input.maxStorageBytes || 0, "#E0F7FA", "#006064");
      } else if (input.mode === "Number of Printed Objects") {
        value = Number(stats.objectCount || 0);
        color = this._buildIntensityColor(value, input.maxObjectCount || 0, "#FEF3C7", "#D97706");
      } else if (input.mode === "Cost of Prints") {
        value = Number(stats.cost || 0);
        color = this._buildIntensityColor(value, input.maxCost || 0, "#FCE7F3", "#BE185D");
      } else if (input.mode === "Filaments Used") {
        value = Number(stats.filamentCount || 0);
        color = this._buildIntensityColor(value, input.maxFilamentCount || 0, "#E0F2FE", "#0369A1");
      } else if (input.mode === "Number of Unique Tags") {
        value = Number(stats.uniqueTagCount || 0);
        color = this._buildIntensityColor(value, input.maxUniqueTagCount || 0, "#CCFBF1", "#0F766E");
      } else if (input.mode === "Single vs Multi-Color Prints") {
        value = Number(stats.count || 0);
        color = stats.singleMultiColor || this._emptyCellColor();
      } else if (input.mode === "Number of Unique Filaments") {
        value = Number(stats.uniqueFilamentCount || 0);
        color = this._buildIntensityColor(value, input.maxUniqueFilamentCount || 0, "#E0E7FF", "#4338CA");
      } else if (input.mode === "In a Project vs Not in a Project") {
        value = Number(stats.count || 0);
        color = stats.projectMembershipColor || this._emptyCellColor();
      } else if (input.mode === "Number of Duplicates / Similar") {
        value = Number(stats.duplicateSimilarCount || 0);
        color = this._buildIntensityColor(value, input.maxDuplicateSimilarCount || 0, "#FFE4E6", "#BE123C");
      } else if (input.mode === "Enrichment Status") {
        value = Number(stats.count || 0);
        color = stats.enrichmentColor || this._emptyCellColor();
      } else if (input.mode === "Number of Favorites") {
        value = Number(stats.favoriteCount || 0);
        color = this._buildIntensityColor(value, input.maxFavoriteCount || 0, "#6B4F00", "#FACC15");
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
        storageBytes: stats ? stats.storageBytes : 0,
        cost: stats ? stats.cost : 0,
        filamentCount: stats ? stats.filamentCount : 0,
        uniqueTagCount: stats ? stats.uniqueTagCount : 0,
        uniqueFilamentCount: stats ? stats.uniqueFilamentCount : 0,
        favoriteCount: stats ? stats.favoriteCount : 0,
        inProjectCount: stats ? stats.inProjectCount : 0,
        notInProjectCount: stats ? stats.notInProjectCount : 0,
        duplicateSimilarCount: stats ? stats.duplicateSimilarCount : 0,
        singleColorCount: stats ? stats.singleColorCount : 0,
        multiColorCount: stats ? stats.multiColorCount : 0,
        singleMultiLabel: stats ? stats.singleMultiLabel || "" : "",
        projectMembershipLabel: stats ? stats.projectMembershipLabel || "" : "",
        durationHours: stats ? stats.durationHours : 0,
        dominantColor: stats ? stats.dominantColor || "" : "",
        outcomeColor: stats ? stats.outcomeColor : "",
        outcomeLabel: stats ? this._buildOutcomeLabel(stats) : "",
        enrichmentColor: stats ? stats.enrichmentColor || "" : "",
        enrichmentBackground: stats ? stats.enrichmentBackground || "" : "",
        enrichmentLabel: stats ? stats.enrichmentLabel || "" : "",
        enrichmentCompleteCount: stats ? (stats.enrichmentCounts.complete || 0) : 0,
        enrichmentNearCompleteCount: stats ? (stats.enrichmentCounts["near complete"] || 0) : 0,
        enrichmentMostlyCompleteCount: stats ? (stats.enrichmentCounts["mostly complete"] || 0) : 0,
        enrichmentPartialCount: stats ? (stats.enrichmentCounts["partially complete"] || 0) : 0,
        enrichmentUnavailableCount: stats ? (stats.enrichmentCounts.unavailable || 0) : 0,
        enrichmentNotDefinedCount: stats ? (stats.enrichmentCounts["not defined"] || 0) : 0,
        hasFullDayPrinting: stats ? !!stats.hasFullDayPrinting : false,
        successCount: stats ? stats.successCount : 0,
        archivedCount: stats ? stats.archivedCount : 0,
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
          return self._buildTooltip(point && point.meta ? point.meta : null, dataset.mode, point);
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
    this._applyEnrichmentPatternFills(dataset);
    this._positionSelectedOverlay(selection ? selection.element : null, selection ? selection.indexes : null, dataset);
    this._queueTooltipPosition(selection && selection.element ? selection.element : this._lastTooltipAnchor);
  }

  _applyEnrichmentPatternFills(dataset) {
    if (!this._chartContainer || !dataset || dataset.mode !== "Enrichment Status") {
      return;
    }

    var svg = this._chartContainer.querySelector("svg");
    if (!svg) {
      return;
    }

    var defs = this._ensureSvgDefs(svg);
    if (!defs) {
      return;
    }

    Array.from(defs.querySelectorAll("pattern[data-print-history-enrichment='true']")).forEach(function (pattern) {
      pattern.remove();
    });

    dataset.series.forEach(function (row, seriesIndex) {
      (row && Array.isArray(row.data) ? row.data : []).forEach(function (point, dataPointIndex) {
        var meta = point && point.meta ? point.meta : null;
        var rect = this._findRenderedHeatmapRect(seriesIndex, dataPointIndex);
        if (!rect || !meta || meta.isFuture) {
          return;
        }

        var segments = this._enrichmentSegmentsFromMeta(meta);
        if (segments.length <= 1) {
          rect.setAttribute("fill", point && point.fillColor ? point.fillColor : this._emptyCellColor());
          return;
        }

        var patternId = this._createEnrichmentPattern(defs, seriesIndex, dataPointIndex, segments);
        if (patternId) {
          rect.setAttribute("fill", "url(#" + patternId + ")");
        }
      }.bind(this));
    }.bind(this));
  }

  _ensureSvgDefs(svg) {
    if (!svg) {
      return null;
    }
    var defs = svg.querySelector("defs");
    if (defs) {
      return defs;
    }
    defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    svg.insertBefore(defs, svg.firstChild || null);
    return defs;
  }

  _findRenderedHeatmapRect(seriesIndex, dataPointIndex) {
    var seriesElement = this._findSeriesElement(seriesIndex);
    if (!seriesElement) {
      return null;
    }
    return seriesElement.querySelector('.apexcharts-heatmap-rect[j="' + String(dataPointIndex) + '"]');
  }

  _createEnrichmentPattern(defs, seriesIndex, dataPointIndex, segments) {
    if (!defs || !segments.length) {
      return "";
    }

    var patternId = [
      "print-history-enrichment",
      this._chart && this._chart.w && this._chart.w.globals ? this._chart.w.globals.cuid : "chart",
      String(seriesIndex),
      String(dataPointIndex),
    ].join("-");
    var pattern = document.createElementNS("http://www.w3.org/2000/svg", "pattern");
    var tileWidth = 16;
    var tileHeight = 16;
    var proportional = segments.length <= 3;
    var total = segments.reduce(function (sum, segment) {
      return sum + Number(segment.count || 0);
    }, 0);
    var cursor = 0;

    pattern.setAttribute("id", patternId);
    pattern.setAttribute("data-print-history-enrichment", "true");
    pattern.setAttribute("patternUnits", "userSpaceOnUse");
    pattern.setAttribute("width", String(tileWidth));
    pattern.setAttribute("height", String(tileHeight));
    pattern.setAttribute("patternTransform", "rotate(135)");

    segments.forEach(function (segment, index) {
      var width = proportional && total > 0
        ? (Number(segment.count || 0) / total) * tileWidth
        : tileWidth / segments.length;
      var end = index === segments.length - 1 ? tileWidth : cursor + width;
      var rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", this._formatDecimal(cursor, 3));
      rect.setAttribute("y", "0");
      rect.setAttribute("width", this._formatDecimal(Math.max(0, end - cursor), 3));
      rect.setAttribute("height", String(tileHeight));
      rect.setAttribute("fill", segment.color);
      pattern.appendChild(rect);
      cursor = end;
    }.bind(this));

    defs.appendChild(pattern);
    return patternId;
  }

  async _applySelectedPointState(dataset) {
    if (!this._chart || !dataset) {
      return null;
    }

    var selectedDate = String(this._stateValue(this._config.selected_date_entity) || "").trim();
    if (!selectedDate) {
      this._clearSelectedPointState();
      this._hideSelectedOverlay();
      return null;
    }

    var indexes = this._findPointIndexesByDate(dataset, selectedDate);
    if (!indexes) {
      this._clearSelectedPointState();
      this._hideSelectedOverlay();
      return null;
    }

    var currentSelection = this._getSelectedPointIndexes();
    if (currentSelection
      && currentSelection.seriesIndex === indexes.seriesIndex
      && currentSelection.dataPointIndex === indexes.dataPointIndex) {
      return {
        element: this._findRenderedPointElement(indexes),
        indexes: indexes,
      };
    }

    this._suppressPointSelection = true;
    try {
      if (currentSelection) {
        this._chart.toggleDataPointSelection(currentSelection.seriesIndex, currentSelection.dataPointIndex);
      }
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

  _getSelectedPointIndexes() {
    var selectedPoints = this._chart && this._chart.w && this._chart.w.globals
      ? this._chart.w.globals.selectedDataPoints
      : null;
    if (!selectedPoints || !Array.isArray(selectedPoints)) {
      return null;
    }

    for (var seriesIndex = 0; seriesIndex < selectedPoints.length; seriesIndex += 1) {
      var dataPoints = selectedPoints[seriesIndex];
      if (Array.isArray(dataPoints) && dataPoints.length) {
        return {
          seriesIndex: seriesIndex,
          dataPointIndex: dataPoints[0],
        };
      }
    }

    return null;
  }

  _clearSelectedPointState() {
    var indexes = this._getSelectedPointIndexes();
    if (!indexes || !this._chart || typeof this._chart.toggleDataPointSelection !== "function") {
      return;
    }

    this._suppressPointSelection = true;
    try {
      this._chart.toggleDataPointSelection(indexes.seriesIndex, indexes.dataPointIndex);
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

    if (mode === "Outcome" || mode === "Single vs Multi-Color Prints" || mode === "In a Project vs Not in a Project" || mode === "Enrichment Status") {
      return ranges.concat(this._buildCategoricalColorRanges(series, function (point) {
        if (!point || !point.meta) {
          return emptyColor;
        }
        if (mode === "Outcome") {
          return point.meta.outcomeColor ? point.meta.outcomeColor : emptyColor;
        }
        if (mode === "Single vs Multi-Color Prints") {
          return point.fillColor || emptyColor;
        }
        if (mode === "In a Project vs Not in a Project") {
          return point.fillColor || emptyColor;
        }
        return point.meta.enrichmentColor ? point.meta.enrichmentColor : emptyColor;
      }));
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
    if (mode === "Storage Used") {
      return { maxValue: maxima.maxStorageBytes || 0, startColor: "#E0F7FA", endColor: "#006064" };
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
    if (mode === "Number of Unique Tags") {
      return { maxValue: maxima.maxUniqueTagCount || 0, startColor: "#CCFBF1", endColor: "#0F766E" };
    }
    if (mode === "Number of Unique Filaments") {
      return { maxValue: maxima.maxUniqueFilamentCount || 0, startColor: "#E0E7FF", endColor: "#4338CA" };
    }
    if (mode === "Number of Duplicates / Similar") {
      return { maxValue: maxima.maxDuplicateSimilarCount || 0, startColor: "#FFE4E6", endColor: "#BE123C" };
    }
    if (mode === "Number of Favorites") {
      return { maxValue: maxima.maxFavoriteCount || 0, startColor: "#6B4F00", endColor: "#FACC15" };
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

    this._chartContainer.classList.remove("loading");

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
    var backgroundStyle = mode === "Enrichment Status" && meta && meta.enrichmentBackground
      ? meta.enrichmentBackground
      : point && point.fillColor ? point.fillColor : "";
    var style = backgroundStyle ? ' style="background:' + this._escapeHtml(backgroundStyle) + ';"' : "";
    var disabled = meta && meta.isFuture ? " disabled" : "";

    return '<button class="' + this._escapeHtml(classes.join(" ")) + '" type="button"' +
      (dateKey ? ' data-date-key="' + this._escapeHtml(dateKey) + '"' : "") +
      (title ? ' title="' + this._escapeHtml(title) + '" aria-label="' + this._escapeHtml(title) + '"' : "") +
      style +
      disabled +
      '></button>';
  }

  _buildHeatmapTitle(meta, mode) {
    var metrics = this._buildTooltipMetrics(meta);
    var primaryMetric = this._resolvePrimaryTooltipMetric(mode, metrics);
    var title = [meta.label];

    if (primaryMetric) {
      title.push(primaryMetric.label + ': ' + primaryMetric.value);
    }

    metrics.forEach(function (metric) {
      if (!metric || (primaryMetric && metric.key === primaryMetric.key)) {
        return;
      }
      title.push(metric.label + ': ' + metric.value);
    });

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

    this._lastTooltipAnchor = this._findRenderedHeatmapRect(opts.seriesIndex, opts.dataPointIndex) || this._lastTooltipAnchor;
    this._queueTooltipPosition(this._lastTooltipAnchor);

    this._handleDateSelection(meta.dateKey);
  }

  _applySelectionOnlyState() {
    if (!this._renderModel) {
      return;
    }

    this._syncSelectedCellClasses();
    this._renderSummary(this._renderModel.archives, this._renderModel.grouped, this._renderModel.dataset);
    this._renderDetails(this._renderModel.grouped);
    Promise.resolve(this._applySelectedVisualState(this._renderModel.dataset)).catch(function () {});
  }

  _syncSelectedCellClasses() {
    if (!this._chartContainer) {
      return;
    }

    var selectedDate = String(this._stateValue(this._config.selected_date_entity) || "").trim();
    Array.from(this._chartContainer.querySelectorAll(".cell[data-date-key]")).forEach(function (button) {
      button.classList.toggle("selected", !!selectedDate && button.getAttribute("data-date-key") === selectedDate);
    });
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

    var self = this;
    var filterState = this._stateValue(this._config.activity_metric_filter_entity);
    var legendValues = this._getLegendValuesForMode(mode);
    var selectedIndex = this._resolveSelectedLegendIndex(mode, legendValues, filterState);

    this._legendContainer.className = "legend";
    this._legendContainer.innerHTML =
      '<div class="legend-scale">' +
      (legend.note ? '<span class="legend-note">' + this._escapeHtml(legend.note) + '</span><span class="legend-separator" aria-hidden="true">|</span>' : "") +
      '<span class="legend-main">' +
      '<span>' + this._escapeHtml(legend.startLabel) + '</span>' +
      '<span class="legend-swatches">' + legend.colors.map(function (color, index) {
        var legendValue = legendValues[index] || "";
        var isInteractive = !!legendValue;
        var isActive = isInteractive && selectedIndex === index ? " active" : "";
        var interactiveClass = isInteractive ? " interactive" : "";
        var disabledAttr = isInteractive ? "" : " disabled";
        var ariaLabel = isInteractive ? ('Filter by ' + self._escapeHtml(legendValue)) : 'Legend swatch';
        return '<button type="button" class="legend-swatch' + interactiveClass + isActive + '" style="background:' + self._escapeHtml(color) + '" data-legend-value="' + self._escapeHtml(legendValue) + '" data-swatch-index="' + index + '" aria-label="' + ariaLabel + '"' + disabledAttr + '></button>';
      }).join("") + '</span>' +
      '<span>' + this._escapeHtml(legend.endLabel) + '</span>' +
      '</span>' +
      '</div>';

    Array.from(this._legendContainer.querySelectorAll(".legend-swatch")).forEach(function (button) {
      button.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        var target = event.currentTarget;
        var legendValue = target.getAttribute("data-legend-value");
        var swatchIndex = Number(target.getAttribute("data-swatch-index") || -1);
        self._handleLegendSwatchClick(mode, swatchIndex, legendValue);
      });
    });
  }

  _resolveSelectedLegendIndex(mode, legendValues, filterState) {
    if (!filterState || filterState === "All") {
      this._legendSelectedMode = "";
      this._legendSelectedIndex = -1;
      return -1;
    }

    if (
      this._legendSelectedMode === mode &&
      this._legendSelectedIndex >= 0 &&
      legendValues[this._legendSelectedIndex] === filterState
    ) {
      return this._legendSelectedIndex;
    }

    var firstMatchIndex = legendValues.indexOf(filterState);
    if (firstMatchIndex >= 0) {
      this._legendSelectedMode = mode;
      this._legendSelectedIndex = firstMatchIndex;
      return firstMatchIndex;
    }

    this._legendSelectedMode = "";
    this._legendSelectedIndex = -1;
    return -1;
  }

  _getLegendValuesForMode(mode) {
    switch (mode) {
      case "Outcome":
        return ["Stopped", "Failed", "Failed", "Complete", "Complete"];
      case "Single vs Multi-Color Prints":
        return ["Single Color", "Single Color", "Multi-Color", "Multi-Color", "Multi-Color"];
      case "Enrichment Status":
        return ["Pending", "Pending", "Pending", "Complete", "Complete"];
      case "In a Project vs Not in a Project":
        return ["In a Project", "In a Project", "Not in a Project", "Not in a Project", "Not in a Project"];
      default:
        return ["", "", "", "", ""];
    }
  }

  _handleLegendSwatchClick(mode, swatchIndex, legendValue) {
    if (!this._hass || !legendValue) {
      return;
    }

    var filterState = this._stateValue(this._config.activity_metric_filter_entity);
    var nextFilterValue = filterState === legendValue ? "All" : legendValue;

    if (nextFilterValue === "All") {
      this._legendSelectedMode = "";
      this._legendSelectedIndex = -1;
    } else {
      this._legendSelectedMode = mode;
      this._legendSelectedIndex = Math.max(0, Number(swatchIndex || 0));
    }

    this._hass.callService("input_select", "select_option", {
      option: nextFilterValue,
    }, {
      entity_id: this._config.activity_metric_filter_entity,
    });
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

    if (mode === "Single vs Multi-Color Prints") {
      return {
        startLabel: "More single-color",
        endLabel: "More multi-color",
        colors: ["#2563EB", "#4F46E5", "#7C3AED", "#A21CAF", "#D946EF"],
        note: "Balanced days blend toward purple.",
      };
    }

    if (mode === "Enrichment Status") {
      return {
        startLabel: "Unavailable",
        endLabel: "Complete",
        colors: ["#546E7A", "#EF6C00", "#6A1B9A", "#1565C0", "#2E7D32"],
      };
    }

    if (mode === "In a Project vs Not in a Project") {
      return {
        startLabel: "More in a project",
        endLabel: "More not in a project",
        colors: ["#2563EB", "#4F8FE0", "#7BB8CC", "#B7C78B", "#FACC15"],
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
    var totalStorageBytes = archives.reduce(function (sum, archive) {
      return sum + Number(archive.storageBytes || 0);
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
    if (mode === "Storage Used") {
      return this._formatBytes(totalStorageBytes);
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
    if (mode === "Number of Unique Tags") {
      return this._formatCount(this._collectUniqueArchiveTags(archives).length) + " unique tags";
    }
    if (mode === "Single vs Multi-Color Prints") {
      return this._buildSingleMultiArchiveSummary(archives);
    }
    if (mode === "Number of Unique Filaments") {
      return this._formatCount(this._collectUniqueArchiveFilaments(archives).length) + " unique filaments";
    }
    if (mode === "In a Project vs Not in a Project") {
      return this._buildProjectMembershipArchiveSummary(archives);
    }
    if (mode === "Enrichment Status") {
      return this._buildEnrichmentArchiveSummary(archives);
    }
    if (mode === "Number of Duplicates / Similar") {
      return this._formatCount(this._totalDuplicateSimilarArchives(archives)) + " duplicate/similar";
    }
    if (mode === "Number of Favorites") {
      return this._formatCount(archives.filter(function (archive) { return !!archive.isFavorite; }).length) + " favorites";
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
      this._formatCount(day.archivedCount) + " archived",
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
      archived: { label: "Archived", color: "#1D4ED8" },
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

  _buildTooltip(meta, mode, point) {
    if (!meta || !meta.dateKey) {
      return "";
    }

    var metrics = this._buildTooltipMetrics(meta);
    var primaryMetric = this._resolvePrimaryTooltipMetric(mode, metrics);
    var secondaryMetrics = metrics.filter(function (metric) {
      return !primaryMetric || metric.key !== primaryMetric.key;
    });
    var accentStyle = this._buildTooltipAccentStyle(mode, meta, point);
    var lines = [
      '<div style="padding:8px 10px;min-width:220px">',
      '<div style="display:flex;align-items:center;gap:8px;font-weight:700;margin-bottom:6px">' +
      (accentStyle ? '<span style="width:12px;height:12px;border-radius:3px;flex:0 0 auto;background:' + this._escapeHtml(accentStyle) + ';box-shadow:inset 0 0 0 1px rgba(255,255,255,0.28)"></span>' : '') +
      '<span>' + this._escapeHtml(meta.label) + '</span>' +
      "</div>",
    ];

    if (primaryMetric) {
      lines.push(
        '<div style="margin-bottom:8px;padding:8px 10px;border-radius:12px;background:rgba(59,130,246,0.12);border:1px solid rgba(59,130,246,0.22);' + (accentStyle ? ('box-shadow:inset 3px 0 0 ' + accentStyle + ';') : '') + '">' +
        '<div style="font-size:11px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;opacity:0.72">' + this._escapeHtml(primaryMetric.label) + '</div>' +
        '<div style="display:flex;align-items:center;gap:8px;margin-top:4px">' +
        (primaryMetric.swatch ? '<span style="width:12px;height:12px;border-radius:999px;background:' + this._escapeHtml(primaryMetric.swatch) + ';display:inline-block;box-shadow:inset 0 0 0 1px rgba(255,255,255,0.32)"></span>' : '') +
        '<span style="font-size:15px;font-weight:800;line-height:1.2">' + this._escapeHtml(primaryMetric.value) + '</span>' +
        '</div>' +
        '</div>'
      );
    }

    if (secondaryMetrics.length) {
      lines.push('<div style="display:grid;gap:4px;font-size:12px;line-height:1.35">');
      secondaryMetrics.forEach(function (metric) {
        lines.push('<div><span style="color:rgba(148,163,184,0.92);font-weight:500">' + this._escapeHtml(metric.label) + ':</span> <span style="font-weight:700;color:inherit">' + this._escapeHtml(metric.value) + '</span></div>');
      }.bind(this));
      lines.push('</div>');
    }

    if (mode === "Total Time Printing" && meta.hasFullDayPrinting) {
      lines.push('<div style="margin-top:4px">Printed all 24 hours.</div>');
    }
    lines.push("</div>");
    return lines.join("");
  }

  _buildTooltipAccentStyle(mode, meta, point) {
    if (mode === "Enrichment Status" && meta && meta.enrichmentBackground) {
      return meta.enrichmentBackground;
    }
    if (point && point.fillColor) {
      return point.fillColor;
    }
    if (meta && meta.outcomeColor) {
      return meta.outcomeColor;
    }
    if (meta && meta.dominantColor) {
      return meta.dominantColor;
    }
    return "";
  }

  _buildTooltipMetrics(meta) {
    var printCountText = 'Prints: ' + this._formatCount(meta.count || 0);

    return [
      { key: 'Print Count', label: 'Prints', value: printCountText.slice(8) },
      { key: 'Number of Printed Objects', label: 'Objects', value: this._formatCount(meta.objectCount || 0) },
      { key: 'Filament Weight', label: 'Weight', value: this._formatWeight(meta.weight || 0) },
      { key: 'Storage Used', label: 'Storage', value: this._formatBytes(meta.storageBytes || 0) },
      { key: 'Cost of Prints', label: 'Cost', value: this._formatCost(meta.cost || 0) },
      { key: 'Filaments Used', label: 'Filaments', value: this._formatCount(meta.filamentCount || 0) },
      { key: 'Number of Unique Tags', label: 'Unique tags', value: this._formatCount(meta.uniqueTagCount || 0) },
      { key: 'Number of Unique Filaments', label: 'Unique filaments', value: this._formatCount(meta.uniqueFilamentCount || 0) },
      { key: 'Number of Favorites', label: 'Favorites', value: this._formatCount(meta.favoriteCount || 0) },
      { key: 'In a Project vs Not in a Project', label: 'Project mix', value: meta.projectMembershipLabel || 'No project data' },
      { key: 'Number of Duplicates / Similar', label: 'Duplicate/similar', value: this._formatCount(meta.duplicateSimilarCount || 0) },
      { key: 'Total Time Printing', label: 'Time', value: this._formatHours(meta.durationHours || 0) },
      {
        key: 'Status',
        label: 'Status',
        value: this._formatCount(meta.successCount || 0) + ' completed, ' + this._formatCount(meta.archivedCount || 0) + ' archived, ' + this._formatCount(meta.failedCount || 0) + ' failed, ' + this._formatCount(meta.cancelledCount || 0) + ' cancelled',
      },
      { key: 'Single vs Multi-Color Prints', label: 'Color mix', value: meta.singleMultiLabel || 'No color mode data' },
      { key: 'Enrichment Status', label: 'Enrichment', value: this._buildEnrichmentMetaBreakdown(meta) },
      { key: 'Outcome', label: 'Outcome band', value: meta.outcomeLabel || 'No outcome data' },
      { key: 'Dominant Color', label: 'Dominant color', value: meta.dominantColor ? meta.dominantColor.toUpperCase() : 'No dominant color', swatch: meta.dominantColor || '' },
    ];
  }

  _resolvePrimaryTooltipMetric(mode, metrics) {
    var selectedMode = String(mode || '').trim() || 'Print Count';
    var primaryMetric = Array.isArray(metrics)
      ? metrics.find(function (metric) {
        return metric && metric.key === selectedMode;
      })
      : null;
    if (primaryMetric) {
      return primaryMetric;
    }
    return Array.isArray(metrics)
      ? metrics.find(function (metric) {
        return metric && metric.key === 'Print Count';
      }) || null
      : null;
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
    var archivedCount = Number(day.archivedCount || 0);
    var total = Number(day.count || 0);
    var archivedColor = "#1D4ED8";
    var palette = {
      1: "#D32F2F",
      2: "#F57C00",
      3: "#FBC02D",
      4: "#9CCC65",
      5: "#2E7D32",
    };
    var baseColor = palette[band] || this._emptyCellColor();

    if (archivedCount <= 0 || total <= 0) {
      return baseColor;
    }
    if (archivedCount >= total) {
      return archivedColor;
    }

    return this._mixHexColors(baseColor, archivedColor, Math.min(1, 0.2 + (archivedCount / total) * 0.8));
  }

  _buildOutcomeBand(day) {
    var total = Number(day.count || 0);
    var archivedCount = Number(day.archivedCount || 0);
    var scoredTotal = Math.max(0, total - archivedCount);
    if (total <= 0) {
      return 0;
    }
    if (scoredTotal <= 0) {
      return 5;
    }

    var negatives = Number(day.failedCount || 0) + Number(day.cancelledCount || 0) + Number(day.otherCount || 0);
    var neutrals = Number(day.printingCount || 0);
    var penalty = (negatives + neutrals * 0.5) / scoredTotal;

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

  _buildOutcomeLabel(day) {
    if (!day || Number(day.count || 0) <= 0) {
      return "";
    }

    var base = this._outcomeBandLabel(day.outcomeBand);
    var archivedCount = Number(day.archivedCount || 0);
    if (archivedCount <= 0) {
      return base;
    }
    if (archivedCount >= Number(day.count || 0)) {
      return "Archived";
    }
    return base ? ("Archived + " + base) : "Archived";
  }

  _normalizeMode(mode) {
    var normalized = String(mode == null ? "" : mode)
      .trim()
      .toLowerCase()
      .replace(/\s+/g, " ");
    var aliases = {
      "print count": "Print Count",
      "filament weight": "Filament Weight",
      "storage used": "Storage Used",
      "dominant color": "Dominant Color",
      outcome: "Outcome",
      "number of printed objects": "Number of Printed Objects",
      "cost of prints": "Cost of Prints",
      "filaments used": "Filaments Used",
      "number of unique tags": "Number of Unique Tags",
      "single vs multi-color prints": "Single vs Multi-Color Prints",
      "single vs multicolor prints": "Single vs Multi-Color Prints",
      "number of unique filaments": "Number of Unique Filaments",
      "in a project vs not in a project": "In a Project vs Not in a Project",
      "project vs not in a project": "In a Project vs Not in a Project",
      "number of duplicates / similar": "Number of Duplicates / Similar",
      "number of duplicates or similar": "Number of Duplicates / Similar",
      "enrichment status": "Enrichment Status",
      "number of favorites": "Number of Favorites",
      "total time printing": "Total Time Printing",
    };

      return aliases[normalized] || "Print Count";
  }

  _archiveHasProject(archive) {
    return !!((archive && archive.project_name && String(archive.project_name).trim()) || (archive && archive.project_id != null && String(archive.project_id).trim()));
  }

  _archiveDuplicateSimilarCount(archive) {
    var duplicateSequence = this._toNumber(archive && archive.duplicate_sequence);
    var duplicateCount = this._toNumber(archive && archive.duplicate_count);
    var originalArchiveId = this._toNumber(archive && archive.original_archive_id);
    var archiveId = this._toNumber(archive && archive.id);
    if (duplicateSequence > 0) {
      return 1;
    }
    if (originalArchiveId > 0 && archiveId > 0 && originalArchiveId !== archiveId) {
      return 1;
    }
    return Math.max(0, duplicateCount);
  }

  _userTags(raw) {
    var systemTagPrefixes = ["f:", "s:", "spoolman:", "vendor:", "material:", "cost:", "status:", "ha enrichment:", "ha_enrichment:"];
    var systemTagValues = ["ha_enriched:true"];
    var seen = {};
    return String(raw || "")
      .split(",")
      .map(function (entry) { return entry.trim(); })
      .filter(Boolean)
      .filter(function (tag) {
        var normalized = tag.toLowerCase();
        if (systemTagValues.indexOf(normalized) !== -1 || systemTagPrefixes.some(function (prefix) { return normalized.indexOf(prefix) === 0; })) {
          return false;
        }
        if (seen[normalized]) {
          return false;
        }
        seen[normalized] = true;
        return true;
      });
  }

  _extractEnrichmentPayload(value) {
    var raw = String(value || "");
    var markerIndex = raw.indexOf("+>");
    if (markerIndex < 0) {
      return {};
    }
    try {
      var parsed = JSON.parse(raw.slice(markerIndex + 2).trim());
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (_error) {
      return {};
    }
  }

  _normalizeEnrichmentStatus(statusValue, enrichmentRows) {
    var normalized = String(statusValue || "").trim().toLowerCase();
    var mapped = ({
      c: "complete",
      complete: "complete",
      t: "near complete",
      "near complete": "near complete",
      m: "mostly complete",
      n: "mostly complete",
      "mostly complete": "mostly complete",
      p: "partially complete",
      partial: "partially complete",
      "partially complete": "partially complete",
      u: "unavailable",
      unavailable: "unavailable",
      "not defined": "not defined",
    })[normalized] || "";
    if (mapped) {
      return mapped;
    }
    if (!Array.isArray(enrichmentRows) || !enrichmentRows.length) {
      return "not defined";
    }
    if (enrichmentRows.some(function (item) {
      return !this._hasResolvedEntityId(item && item.f);
    }.bind(this))) {
      return "partially complete";
    }
    if (enrichmentRows.some(function (item) {
      return !this._hasResolvedEntityId(item && item.s);
    }.bind(this))) {
      return "mostly complete";
    }
    if (enrichmentRows.some(function (item) {
      return String(item && item.t || "").trim() === "";
    })) {
      return "near complete";
    }
    return "complete";
  }

  _hasResolvedEntityId(value) {
    if (value === null || value === undefined) {
      return false;
    }
    var normalized = String(value).trim().toLowerCase();
    return normalized !== "" && normalized !== "null" && normalized !== "none";
  }

  _buildFilamentIdentityKey(row) {
    var filamentId = row && row.filament_id != null ? String(row.filament_id).trim() : (row && row.f != null ? String(row.f).trim() : "");
    if (filamentId) {
      return "f:" + filamentId.toLowerCase();
    }
    var spoolId = row && row.spool_id != null ? String(row.spool_id).trim() : (row && row.s != null ? String(row.s).trim() : "");
    if (spoolId) {
      return "s:" + spoolId.toLowerCase();
    }
    var name = String(row && row.name ? row.name : (row && row.n ? row.n : "")).trim().toLowerCase();
    var color = this._normalizeHexColor(row && (row.color || row.h));
    var type = String(row && row.type ? row.type : "").trim().toLowerCase();
    if (!name && !color && !type) {
      return "";
    }
    return "n:" + [name || "no-name", color || "no-color", type || "no-type"].join("|");
  }

  _collectFilamentIdentityKeys(archive, enrichmentRows) {
    var seen = {};
    var keys = [];
    var addKey = function (key) {
      if (!key || seen[key]) {
        return;
      }
      seen[key] = true;
      keys.push(key);
    };

    if (Array.isArray(enrichmentRows) && enrichmentRows.length) {
      enrichmentRows.forEach(function (row) {
        addKey(this._buildFilamentIdentityKey(row));
      }.bind(this));
      if (keys.length) {
        return keys;
      }
    }

    var slots = Array.isArray(archive && archive.filament_slots)
      ? archive.filament_slots
      : Array.isArray(archive && archive.extra_data && archive.extra_data.filament_slots)
        ? archive.extra_data.filament_slots
        : [];
    slots.forEach(function (slot) {
      var used = this._toNumber(slot && (slot.used_g != null ? slot.used_g : slot.used_grams));
      if (used <= 0) {
        return;
      }
      addKey(this._buildFilamentIdentityKey({
        filament_id: slot && slot.filament_id,
        spool_id: slot && slot.spool_id,
        name: slot && slot.name,
        type: slot && slot.type,
        color: slot && slot.color,
      }));
    }.bind(this));

    if (keys.length) {
      return keys;
    }

    String(archive && archive.filament_color ? archive.filament_color : "")
      .split(",")
      .map(function (value) {
        return this._normalizeHexColor(value);
      }.bind(this))
      .filter(Boolean)
      .forEach(function (color) {
        addKey("n:no-name|" + color + "|" + (String(archive && archive.filament_type ? archive.filament_type : "").trim().toLowerCase() || "no-type"));
      });

    return keys;
  }

  _resolveSingleMultiState(filamentIdentityKeys, colors) {
    var count = Array.isArray(filamentIdentityKeys) && filamentIdentityKeys.length
      ? filamentIdentityKeys.length
      : (Array.isArray(colors) ? colors.length : 0);
    if (count > 1) {
      return "multi";
    }
    if (count === 1) {
      return "single";
    }
    return "";
  }

  _emptyEnrichmentCounts() {
    return {
      complete: 0,
      "near complete": 0,
      "mostly complete": 0,
      "partially complete": 0,
      unavailable: 0,
      "not defined": 0,
    };
  }

  _buildSingleMultiColor(day) {
    var classified = Number(day.singleColorCount || 0) + Number(day.multiColorCount || 0);
    if (classified <= 0) {
      return this._emptyCellColor();
    }
    return this._mixHexColors("#2563EB", "#D946EF", Math.min(1, Math.max(0, Number(day.multiColorCount || 0) / classified)));
  }

  _buildSingleMultiLabel(day) {
    var singleCount = Number(day.singleColorCount || 0);
    var multiCount = Number(day.multiColorCount || 0);
    if (singleCount <= 0 && multiCount <= 0) {
      return "No color mode data";
    }
    return this._formatCount(singleCount) + " single-color, " + this._formatCount(multiCount) + " multi-color";
  }

  _buildProjectMembershipColor(day) {
    var classified = Number(day.inProjectCount || 0) + Number(day.notInProjectCount || 0);
    if (classified <= 0) {
      return this._emptyCellColor();
    }
    return this._mixHexColors("#2563EB", "#FACC15", Math.min(1, Math.max(0, Number(day.notInProjectCount || 0) / classified)));
  }

  _buildProjectMembershipLabel(day) {
    var inProjectCount = Number(day.inProjectCount || 0);
    var notInProjectCount = Number(day.notInProjectCount || 0);
    if (inProjectCount <= 0 && notInProjectCount <= 0) {
      return "No project data";
    }
    return this._formatCount(inProjectCount) + " in project, " + this._formatCount(notInProjectCount) + " not in project";
  }

  _buildProjectMembershipArchiveSummary(archives) {
    var inProjectCount = archives.filter(function (archive) { return !!archive.hasProject; }).length;
    return this._formatCount(inProjectCount) + " in project / " + this._formatCount(archives.length - inProjectCount) + " not";
  }

  _totalDuplicateSimilarArchives(archives) {
    return archives.reduce(function (sum, archive) {
      return sum + Number(archive.duplicateSimilarCount || 0);
    }, 0);
  }

  _buildEnrichmentColor(day) {
    var counts = day && day.enrichmentCounts ? day.enrichmentCounts : this._emptyEnrichmentCounts();
    var total = Object.keys(counts).reduce(function (sum, key) {
      return sum + Number(counts[key] || 0);
    }, 0);
    if (total <= 0) {
      return this._emptyCellColor();
    }
    var palette = {
      complete: "#2E7D32",
      "near complete": "#1565C0",
      "mostly complete": "#6A1B9A",
      "partially complete": "#EF6C00",
      unavailable: "#546E7A",
      "not defined": "#546E7A",
    };
    var rgb = { r: 0, g: 0, b: 0 };
    Object.keys(counts).forEach(function (key) {
      var color = this._hexToRgb(palette[key] || this._emptyCellColor());
      var weight = Number(counts[key] || 0) / total;
      rgb.r += color.r * weight;
      rgb.g += color.g * weight;
      rgb.b += color.b * weight;
    }.bind(this));
    return this._rgbToHex(rgb.r, rgb.g, rgb.b);
  }

  _buildEnrichmentBackground(day) {
    var segments = this._enrichmentSegments(day);
    if (!segments.length) {
      return this._emptyCellColor();
    }
    if (segments.length === 1) {
      return segments[0].color;
    }
    var total = segments.reduce(function (sum, segment) {
      return sum + Number(segment.count || 0);
    }, 0);
    var proportional = segments.length <= 3 && total > 0;
    var cursor = 0;
    var stops = [];
    segments.forEach(function (segment, index) {
      var width = proportional
        ? (Number(segment.count || 0) / total) * 100
        : 100 / segments.length;
      var end = index === segments.length - 1 ? 100 : cursor + width;
      stops.push(segment.color + " " + this._formatGradientStop(cursor));
      stops.push(segment.color + " " + this._formatGradientStop(end));
      cursor = end;
    }.bind(this));
    return "linear-gradient(135deg, " + stops.join(", ") + ")";
  }

  _buildEnrichmentLabel(day) {
    var counts = day && day.enrichmentCounts ? day.enrichmentCounts : this._emptyEnrichmentCounts();
    var total = Object.keys(counts).reduce(function (sum, key) {
      return sum + Number(counts[key] || 0);
    }, 0);
    if (total <= 0) {
      return "Not Defined";
    }
    var ranking = {
      complete: 5,
      "near complete": 4,
      "mostly complete": 3,
      "partially complete": 2,
      unavailable: 1,
      "not defined": 0,
    };
    var dominant = Object.keys(counts).reduce(function (best, key) {
      var count = Number(counts[key] || 0);
      if (!best || count > best.count || (count === best.count && ranking[key] > ranking[best.key])) {
        return { key: key, count: count };
      }
      return best;
    }, null);
    var label = this._enrichmentStatusLabel(dominant && dominant.key ? dominant.key : "not defined");
    return dominant && dominant.count === total ? label : (this._formatCount(dominant && dominant.count ? dominant.count : 0) + "/" + this._formatCount(total) + " " + label);
  }

  _enrichmentSegments(day) {
    var counts = day && day.enrichmentCounts ? day.enrichmentCounts : this._emptyEnrichmentCounts();
    var palette = {
      complete: "#2E7D32",
      "near complete": "#1565C0",
      "mostly complete": "#6A1B9A",
      "partially complete": "#EF6C00",
      unavailable: "#546E7A",
      "not defined": "#546E7A",
    };
    var ranking = {
      complete: 5,
      "near complete": 4,
      "mostly complete": 3,
      "partially complete": 2,
      unavailable: 1,
      "not defined": 0,
    };
    return Object.keys(counts)
      .map(function (key) {
        return {
          key: key,
          count: Number(counts[key] || 0),
          color: palette[key] || this._emptyCellColor(),
          rank: ranking[key] || 0,
        };
      }.bind(this))
      .filter(function (entry) {
        return entry.count > 0;
      })
      .sort(function (left, right) {
        if (left.rank !== right.rank) {
          return left.rank - right.rank;
        }
        return right.count - left.count;
      });
  }

  _enrichmentSegmentsFromMeta(meta) {
    return this._enrichmentSegments({
      enrichmentCounts: {
        complete: meta ? Number(meta.enrichmentCompleteCount || 0) : 0,
        "near complete": meta ? Number(meta.enrichmentNearCompleteCount || 0) : 0,
        "mostly complete": meta ? Number(meta.enrichmentMostlyCompleteCount || 0) : 0,
        "partially complete": meta ? Number(meta.enrichmentPartialCount || 0) : 0,
        unavailable: meta ? Number(meta.enrichmentUnavailableCount || 0) : 0,
        "not defined": meta ? Number(meta.enrichmentNotDefinedCount || 0) : 0,
      },
    });
  }

  _formatGradientStop(value) {
    return this._formatDecimal(Math.max(0, Math.min(100, value)), 2) + "%";
  }

  _enrichmentStatusLabel(status) {
    if (status === "not defined") {
      return "Not Defined";
    }
    return String(status || "")
      .replace(/\b\w/g, function (match) {
        return match.toUpperCase();
      });
  }

  _buildEnrichmentMetaBreakdown(meta) {
    if (!meta) {
      return "Not Defined";
    }
    var counts = [
      { key: "complete", count: Number(meta.enrichmentCompleteCount || 0) },
      { key: "near complete", count: Number(meta.enrichmentNearCompleteCount || 0) },
      { key: "mostly complete", count: Number(meta.enrichmentMostlyCompleteCount || 0) },
      { key: "partially complete", count: Number(meta.enrichmentPartialCount || 0) },
      { key: "unavailable", count: Number(meta.enrichmentUnavailableCount || 0) },
      { key: "not defined", count: Number(meta.enrichmentNotDefinedCount || 0) },
    ].filter(function (entry) {
      return entry.count > 0;
    });
    if (!counts.length) {
      return meta.enrichmentLabel || "Not Defined";
    }
    return counts.map(function (entry) {
      return this._formatCount(entry.count) + " " + this._enrichmentStatusLabel(entry.key);
    }.bind(this)).join(", ");
  }

  _collectUniqueArchiveTags(archives) {
    var seen = {};
    (archives || []).forEach(function (archive) {
      (archive.userTags || []).forEach(function (tag) {
        seen[String(tag).toLowerCase()] = true;
      });
    });
    return Object.keys(seen);
  }

  _collectUniqueArchiveFilaments(archives) {
    var seen = {};
    (archives || []).forEach(function (archive) {
      (archive.filamentIdentityKeys || []).forEach(function (keyValue) {
        seen[keyValue] = true;
      });
    });
    return Object.keys(seen);
  }

  _buildSingleMultiArchiveSummary(archives) {
    var counts = { single: 0, multi: 0 };
    (archives || []).forEach(function (archive) {
      if (archive.colorMode === "single") {
        counts.single += 1;
      } else if (archive.colorMode === "multi") {
        counts.multi += 1;
      }
    });
    return this._formatCount(counts.single) + " single / " + this._formatCount(counts.multi) + " multi";
  }

  _buildEnrichmentArchiveSummary(archives) {
    var counts = this._emptyEnrichmentCounts();
    (archives || []).forEach(function (archive) {
      var status = archive.enrichmentStatus || "not defined";
      counts[status] = (counts[status] || 0) + 1;
    });
    return this._buildEnrichmentLabel({ enrichmentCounts: counts });
  }

  _hexToRgb(value) {
    var normalized = this._normalizeHexColor(value) || "#000000";
    return {
      r: parseInt(normalized.slice(1, 3), 16),
      g: parseInt(normalized.slice(3, 5), 16),
      b: parseInt(normalized.slice(5, 7), 16),
    };
  }

  _rgbToHex(rgb) {
    var channel = function (value) {
      var bounded = Math.max(0, Math.min(255, Math.round(value)));
      var hex = bounded.toString(16);
      return hex.length === 1 ? "0" + hex : hex;
    };
    return "#" + channel(rgb.r) + channel(rgb.g) + channel(rgb.b);
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

  _formatBytes(totalBytes) {
    var value = Math.max(0, this._toNumber(totalBytes));
    var units = ["B", "KB", "MB", "GB", "TB"];
    var unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
      value /= 1024;
      unitIndex += 1;
    }
    if (unitIndex === 0) {
      return this._formatCount(value) + " " + units[unitIndex];
    }
    return this._formatTrimmedDecimal(value, 1) + " " + units[unitIndex];
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

  _formatTrimmedDecimal(value, digits) {
    return this._formatDecimal(value, digits).replace(/(?:\.0|,0)$/, "");
  }

  _archiveStorageBytes(archive) {
    var directBytes = this._toNumber(archive && archive.storage_total_bytes);
    if (directBytes > 0) {
      return directBytes;
    }
    var storageMetrics = archive && archive.storage_metrics && typeof archive.storage_metrics === "object"
      ? archive.storage_metrics
      : null;
    var metricValues = storageMetrics && storageMetrics.metrics && typeof storageMetrics.metrics === "object"
      ? storageMetrics.metrics
      : null;
    return Math.max(0, this._toNumber(metricValues && metricValues.total_bytes));
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
      return Math.round(Math.max(0, Math.min(255, channel))).toString(16).padStart(2, "0");
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

  _describeRenderError(error) {
    var message = error && error.message ? String(error.message).trim() : "";
    if (!message) {
      try {
        message = String(error || "").trim();
      } catch (_stringError) {
        message = "";
      }
    }
    if (!message || message === "[object Object]" || message.toLowerCase() === "unknown error") {
      message = "Heatmap query failed.";
    }
    if (/ERR_CONNECTION_REFUSED|websocket|networkerror|failed to fetch|connection (?:closed|lost|refused)|not connected/i.test(message)) {
      return "Home Assistant websocket unavailable. Retry after the connection recovers.";
    }
    return message;
  }

  _showError(message) {
    if (this._renderModel) {
      this._showRefreshIndicator("Couldn't refresh", true);
      return;
    }

    this._destroyChart();
    if (this._chartContainer) {
      this._chartContainer.classList.remove("loading");
      this._chartContainer.innerHTML = '<div class="error">' + this._escapeHtml(message) + "</div>";
    }
  }

  _ensureRefreshIndicator() {
    if (!this._chartContainer) {
      return null;
    }

    var indicator = this._chartContainer.querySelector(".refresh-indicator");
    if (!indicator) {
      indicator = document.createElement("div");
      indicator.className = "refresh-indicator hidden";
      this._chartContainer.appendChild(indicator);
    }
    return indicator;
  }

  _showRefreshIndicator(message, isError) {
    var indicator = this._ensureRefreshIndicator();
    if (!indicator) {
      return;
    }

    indicator.className = "refresh-indicator" + (isError ? " error" : "");
    indicator.innerHTML = '<span class="refresh-dot"></span><span>' + this._escapeHtml(message) + '</span>';
  }

  _hideRefreshIndicator() {
    if (!this._chartContainer) {
      return;
    }

    var indicator = this._chartContainer.querySelector(".refresh-indicator");
    if (indicator) {
      indicator.className = "refresh-indicator hidden";
      indicator.textContent = "";
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
