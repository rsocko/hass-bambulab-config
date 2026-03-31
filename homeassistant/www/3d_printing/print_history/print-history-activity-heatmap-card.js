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
    this._summaryContainer = null;
    this._detailsContainer = null;
    this._renderQueued = false;
    this._signature = "";
  }

  setConfig(config) {
    if (!config || !config.source_entity || !config.source_attribute) {
      throw new Error("print-history-activity-heatmap-card requires source_entity and source_attribute");
    }

    this._config = {
      title: config.title || "Print History Activity",
      source_entity: config.source_entity,
      source_attribute: config.source_attribute,
      mode_entity: config.mode_entity || "input_select.print_history_activity_metric",
      apply_filters_entity: config.apply_filters_entity || "input_boolean.print_history_activity_use_filters",
      selected_date_entity: config.selected_date_entity || "input_text.print_history_activity_selected_date",
      api_base_entity: config.api_base_entity || "input_text.bambuddy_api_base_url",
      weeks: Math.max(12, Number(config.weeks || 53)),
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

  disconnectedCallback() {
    if (this._chart && typeof this._chart.destroy === "function") {
      this._chart.destroy();
      this._chart = null;
    }
  }

  getCardSize() {
    return 10;
  }

  _buildSignature(hass) {
    var sourceState = hass.states[this._config.source_entity];
    var metricState = hass.states[this._config.mode_entity];
    var applyFiltersState = hass.states[this._config.apply_filters_entity];
    var selectedDateState = hass.states[this._config.selected_date_entity];
    var apiBaseState = hass.states[this._config.api_base_entity];

    return {
      sourceState: sourceState ? sourceState.state : "",
      sourceFetch: sourceState && sourceState.attributes ? sourceState.attributes.last_fetch || "" : "",
      metric: metricState ? metricState.state : "",
      applyFilters: applyFiltersState ? applyFiltersState.state : "",
      selectedDate: selectedDateState ? selectedDateState.state : "",
      apiBase: apiBaseState ? apiBaseState.state : "",
      status: this._stateValue("input_select.print_history_filter_status"),
      material: this._stateValue("input_select.print_history_filter_material"),
      printer: this._stateValue("input_select.print_history_filter_printer"),
      dateRange: this._stateValue("input_select.print_history_filter_date_range"),
      designer: this._stateValue("input_select.print_history_filter_designer"),
      layerHeight: this._stateValue("input_select.print_history_filter_layer_height"),
      sort: this._stateValue("input_select.print_history_sort"),
      favorites: this._stateValue("input_boolean.print_history_filter_favorites_only"),
      search: this._stateValue("input_text.print_history_search"),
      colors: this._stateValue("input_text.print_history_filter_colors"),
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
      "ha-card{padding:16px 16px 14px;}" +
      ".title{font-size:1rem;font-weight:600;margin:0 0 10px 0;}" +
      ".chart-wrap{min-height:300px;}" +
      ".heatmap{display:grid;grid-template-columns:40px minmax(0,1fr);column-gap:10px;align-items:start;}" +
      ".month-row{display:grid;grid-template-columns:repeat(var(--week-count,53),minmax(10px,1fr));column-gap:4px;margin-bottom:8px;padding-right:2px;}" +
      ".month-spacer{height:16px;}" +
      ".month-label{font-size:11px;line-height:1;color:var(--secondary-text-color);min-height:16px;white-space:nowrap;overflow:hidden;}" +
      ".day-labels{display:grid;grid-template-rows:repeat(7,18px);row-gap:4px;padding-top:24px;}" +
      ".day-label{display:flex;align-items:center;justify-content:flex-end;font-size:11px;color:var(--secondary-text-color);padding-right:4px;}" +
      ".cells{display:grid;grid-template-rows:repeat(7,18px);row-gap:4px;}" +
      ".heatmap-row{display:grid;grid-template-columns:repeat(var(--week-count,53),minmax(10px,1fr));column-gap:4px;}" +
      ".cell{appearance:none;border:none;border-radius:0;height:18px;min-width:10px;padding:0;cursor:pointer;box-shadow:inset 0 0 0 1px rgba(148,163,184,0.18);transition:transform .12s ease, box-shadow .12s ease, opacity .12s ease;background:rgba(148,163,184,0.14);}" +
      ".cell:hover{transform:translateY(-1px);box-shadow:inset 0 0 0 1px rgba(148,163,184,0.26),0 2px 6px rgba(15,23,42,0.18);}" +
      ".cell:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px;}" +
      ".cell.future{cursor:default;opacity:.72;}" +
      ".cell.selected{box-shadow:inset 0 0 0 2px rgba(15,23,42,0.85),0 0 0 2px var(--primary-background-color);}" +
      ".summary{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;}" +
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
      '<div class="title">' + this._escapeHtml(this._config.title) + "</div>" +
      '<div id="chart" class="chart-wrap"></div>' +
      '<div id="summary" class="summary"></div>' +
      '<div id="details" class="details"></div>' +
      "</ha-card>";

    this._chartContainer = this.shadowRoot.getElementById("chart");
    this._summaryContainer = this.shadowRoot.getElementById("summary");
    this._detailsContainer = this.shadowRoot.getElementById("details");
  }

  _queueRender() {
    var self = this;
    if (self._renderQueued) {
      return;
    }
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
  }

  async _renderCard() {
    if (!this._hass || !this._config || !this._chartContainer) {
      return;
    }

    var archives = this._getScopedArchives();
    var grouped = this._groupArchivesByDate(archives);
    var dataset = this._buildHeatmapDataset(grouped);

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

    var options = this._buildChartOptions(dataset);

    if (!this._chart) {
      this._chartContainer.innerHTML = "";
      this._chart = new ApexChartsCtor(this._chartContainer, options);
      await this._chart.render();
      await this._ensureChartVisible(dataset);
      return;
    }

    await this._chart.updateOptions(options, false, false, false);
    await this._ensureChartVisible(dataset);
  }

  _destroyChart() {
    if (this._chart && typeof this._chart.destroy === "function") {
      this._chart.destroy();
    }
    this._chart = null;
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
    var sourceState = this._hass.states[this._config.source_entity];
    var raw = sourceState && sourceState.attributes ? sourceState.attributes[this._config.source_attribute] : [];
    var archives = this._parseArchiveArray(raw)
      .map(this._normalizeArchive.bind(this))
      .filter(function (archive) {
        return !!archive.timestamp;
      })
      .sort(function (left, right) {
        return right.timestamp - left.timestamp;
      });

    if (!this._isOn(this._config.apply_filters_entity)) {
      return archives;
    }

    return archives.filter(this._matchesFilters.bind(this));
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

    return {
      id: archive && archive.id != null ? archive.id : null,
      printName: archive && archive.print_name ? String(archive.print_name) : "Unnamed",
      printerId: archive && archive.printer_id != null ? String(archive.printer_id) : "Unknown printer",
        filamentType: archive && archive.filament_type ? String(archive.filament_type) : "",
      designer: archive && archive.designer ? String(archive.designer) : "",
        isFavorite: !!(archive && archive.is_favorite),
      status: this._normalizeStatus(archive && archive.status),
      rawStatus: archive && archive.status ? String(archive.status) : "",
      timestamp: date,
      dateKey: date ? this._formatLocalDate(date) : "",
      formattedDate: date ? this._formatDateTime(date) : "Unknown date",
      filamentWeight: this._toNumber(archive && archive.filament_used_grams),
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
    var now = new Date();
    var archiveAgeDays = archive.timestamp ? (this._startOfDay(now) - this._startOfDay(archive.timestamp)) / 86400000 : Number.POSITIVE_INFINITY;
    var archiveStatus = archive.status;
    var searchBlob = [archive.printName, archive.designer, archive.tags]
      .join(" ")
      .toLowerCase();

    var matchesStatus = statusValue === "All" || this._matchesStatusFilter(statusValue, archiveStatus);
    var matchesMaterial = materialValue === "All" || String(archive.filamentType || "").toLowerCase() === String(materialValue).toLowerCase();
    var matchesPrinter = printerValue === "All" || String(archive.printerId) === String(printerValue);
    var matchesDesigner = designerValue === "All" || String(archive.designer).toLowerCase() === String(designerValue).toLowerCase();
    var matchesLayerHeight = layerHeightValue === "All" || String(archive.layerHeight) === String(layerHeightValue);
    var matchesFavorite = !favoritesOnly || isFavorite;
    var matchesSearch = !searchText || searchBlob.indexOf(searchText) !== -1;
    var matchesColors = !selectedColors.length || selectedColors.some(function (color) {
      return archive.colors.indexOf(color) !== -1;
    });
    var matchesDate = true;

    if (dateRangeValue === "Today") {
      matchesDate = archiveAgeDays < 1;
    } else if (dateRangeValue === "This Week") {
      matchesDate = archiveAgeDays < 7;
    } else if (dateRangeValue === "This Month") {
      matchesDate = archiveAgeDays < 30;
    } else if (dateRangeValue === "Last 30 Days") {
      matchesDate = archiveAgeDays < 30;
    } else if (dateRangeValue === "Last 90 Days") {
      matchesDate = archiveAgeDays < 90;
    }

    return matchesStatus && matchesMaterial && matchesPrinter && matchesDesigner && matchesLayerHeight && matchesFavorite && matchesSearch && matchesColors && matchesDate;
  }

  _matchesStatusFilter(statusValue, archiveStatus) {
    var selected = String(statusValue || "").toLowerCase();
    if (!selected || selected === "all") {
      return true;
    }
    if (selected === "completed") {
      return archiveStatus === "success";
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
            weight: 0,
            successCount: 0,
            failedCount: 0,
            stoppedCount: 0,
            printingCount: 0,
            otherCount: 0,
            colorWeights: {},
          };
        }

        var day = accumulator[key];
        day.archives.push(archive);
        day.count += 1;
        day.weight += archive.filamentWeight;

        if (archive.status === "success") {
          day.successCount += 1;
        } else if (archive.status === "failed") {
          day.failedCount += 1;
        } else if (archive.status === "stopped") {
          day.stoppedCount += 1;
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

  _buildHeatmapDataset(grouped) {
    var mode = this._stateValue(this._config.mode_entity) || "Print Count";
    var weeks = this._config.weeks;
    var startDay = ((this._config.start_day % 7) + 7) % 7;
    var today = this._startOfDay(new Date());
    var rangeEnd = today;
    var rangeStart = this._startOfWeek(rangeEnd, startDay);
    rangeStart = this._addDays(rangeStart, -((weeks - 1) * 7));

    var keys = Object.keys(grouped);
    var maxCount = 0;
    var maxWeight = 0;

    keys.forEach(function (key) {
      var day = grouped[key];
      maxCount = Math.max(maxCount, day.count || 0);
      maxWeight = Math.max(maxWeight, day.weight || 0);
      day.dominantColor = this._findDominantColor(day.colorWeights);
      day.outcomeColor = this._buildOutcomeColor(day);
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
      var weekStart = this._addDays(rangeStart, weekIndex * 7);
      var weekKey = this._formatLocalDate(weekStart);
      weekKeys.push(weekKey);

      for (var dayIndex = 0; dayIndex < 7; dayIndex += 1) {
        var currentDate = this._addDays(weekStart, dayIndex);
        var currentKey = this._formatLocalDate(currentDate);
        var isFuture = currentDate.getTime() > today.getTime();
        var stats = grouped[currentKey] || null;
        var point = this._buildPoint({
          weekKey: weekKey,
          date: currentDate,
          dateKey: currentKey,
          stats: stats,
          mode: mode,
          maxCount: maxCount,
          maxWeight: maxWeight,
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
      colorRanges: this._buildColorRanges(series, mode, maxCount, maxWeight),
      weekKeys: weekKeys,
      rangeStart: rangeStart,
      rangeEnd: rangeEnd,
      hasAnyPastCells: hasAnyPastCells,
      weeks: weeks,
    };
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
      } else if (input.mode === "Dominant Color") {
        value = Number(stats.count || 0);
        color = stats.dominantColor || this._emptyCellColor();
      } else if (input.mode === "Outcome Mix") {
        value = Number(stats.count || 0);
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
        weight: stats ? stats.weight : 0,
        dominantColor: stats ? stats.dominantColor || "" : "",
        outcomeColor: stats ? stats.outcomeColor : "",
        successCount: stats ? stats.successCount : 0,
        failedCount: stats ? stats.failedCount : 0,
        stoppedCount: stats ? stats.stoppedCount : 0,
        printingCount: stats ? stats.printingCount : 0,
        otherCount: stats ? stats.otherCount : 0,
        isFuture: input.isFuture,
      },
    };
  }

  _buildChartOptions(dataset) {
    var self = this;
    var isDark = !!(this._hass && this._hass.themes && this._hass.themes.darkMode);
    var textColor = isDark ? "#D1D5DB" : "#1F2937";
    var gridColor = isDark ? "rgba(148,163,184,0.22)" : "rgba(100,116,139,0.18)";

    return {
      chart: {
        type: "heatmap",
        height: 320,
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
        colors: [gridColor],
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
          top: 2,
          right: 4,
          bottom: 0,
          left: 0,
        },
      },
      states: {
        hover: {
          filter: {
            type: "none",
          },
        },
        active: {
          filter: {
            type: "darken",
            value: 0.08,
          },
        },
      },
      theme: {
        mode: isDark ? "dark" : "light",
      },
    };
  }

  _buildColorRanges(series, mode, maxCount, maxWeight) {
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

    if (mode === "Outcome Mix") {
      return ranges.concat(this._buildCategoricalColorRanges(series, function (point) {
        return point && point.meta && point.meta.outcomeColor ? point.meta.outcomeColor : emptyColor;
      }));
    }

    return ranges.concat(
      this._buildContinuousColorRanges(
        mode === "Filament Weight" ? maxWeight : maxCount,
        mode === "Filament Weight" ? "#DBEAFE" : "#DCFCE7",
        mode === "Filament Weight" ? "#1D4ED8" : "#15803D"
      )
    );
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
      'Prints: ' + String(meta.count || 0),
      'Weight: ' + this._formatWeight(meta.weight || 0),
      'Status: ' + String(meta.successCount || 0) + ' success, ' + String((meta.failedCount || 0) + (meta.stoppedCount || 0)) + ' fail/stop',
    ];

    if (mode === 'Dominant Color' && meta.dominantColor) {
      title.push('Dominant color: ' + meta.dominantColor.toUpperCase());
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

  _renderSummary(archives, grouped, dataset) {
    if (!this._summaryContainer) {
      return;
    }

    var selectedDate = String(this._stateValue(this._config.selected_date_entity) || "").trim();
    var totalWeight = archives.reduce(function (sum, archive) {
      return sum + Number(archive.filamentWeight || 0);
    }, 0);
    var activeDays = Object.keys(grouped).length;
    var scopeLabel = this._isOn(this._config.apply_filters_entity) ? "Scoped to current filters" : "Using full archive cache";
    var selectedLabel = selectedDate ? this._formatDateLabel(selectedDate) : "Tap a day to inspect prints";

    this._summaryContainer.innerHTML = [
      this._buildChipHtml(dataset.mode),
      this._buildChipHtml(scopeLabel),
      this._buildChipHtml(String(activeDays) + " active days"),
      this._buildChipHtml(String(archives.length) + " prints"),
      this._buildChipHtml(this._formatWeight(totalWeight)),
      this._buildChipHtml(selectedLabel),
    ].join("");
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
      String(day.count) + (day.count === 1 ? " print" : " prints"),
      this._formatWeight(day.weight),
      day.successCount + " success",
      (day.failedCount + day.stoppedCount) + " failures/stops",
    ].join(" | ");
    var items = day.archives.slice(0, this._config.max_detail_items).map(this._buildArchiveCardHtml.bind(this)).join("");
    var extra = day.archives.length > this._config.max_detail_items
      ? '<div class="details-empty">Showing the first ' + this._config.max_detail_items + ' prints for this day.</div>'
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
    var metaParts = [this._escapeHtml(archive.formattedDate), this._escapeHtml("Printer " + archive.printerId)];
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
      success: { label: "Completed", color: "#2E7D32" },
      failed: { label: "Failed", color: "#C62828" },
      stopped: { label: "Stopped", color: "#EF6C00" },
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
      '<div>Prints: <strong>' + this._escapeHtml(String(meta.count || 0)) + "</strong></div>",
      '<div>Weight: <strong>' + this._escapeHtml(this._formatWeight(meta.weight || 0)) + "</strong></div>",
      '<div>Status: <strong>' + this._escapeHtml(meta.successCount + " success, " + (meta.failedCount + meta.stoppedCount) + " fail/stop") + "</strong></div>",
    ];

    if (mode === "Dominant Color" && meta.dominantColor) {
      lines.push('<div style="display:flex;align-items:center;gap:8px;margin-top:4px"><span style="width:12px;height:12px;border-radius:999px;background:' + this._escapeHtml(meta.dominantColor) + ';display:inline-block"></span><span>Dominant color</span></div>');
    }
    if (mode === "Outcome Mix") {
      lines.push('<div style="margin-top:4px">Tap to inspect this day.</div>');
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
    var total = Number(day.count || 0);
    if (total <= 0) {
      return this._emptyCellColor();
    }

    var negatives = Number(day.failedCount || 0) + Number(day.stoppedCount || 0) + Number(day.otherCount || 0);
    var neutrals = Number(day.printingCount || 0);
    var ratio = (negatives + neutrals * 0.5) / total;
    var hue = Math.max(0, Math.min(120, 120 * (1 - ratio)));
    return this._hslToHex(hue, 72, 44);
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
      return "success";
    }
    if (raw === "failed" || raw === "cancelled" || raw === "aborted") {
      return "failed";
    }
    if (raw === "stopped") {
      return "stopped";
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
    if (!hours) {
      return "0h";
    }
    return hours >= 10 ? hours.toFixed(1) + "h" : hours.toFixed(1) + "h";
  }

  _formatWeight(weight) {
    return (this._toNumber(weight)).toFixed(1) + "g";
  }

  _formatCost(cost) {
    var value = this._toNumber(cost);
    return value > 0 ? "$" + value.toFixed(2) : "$0.00";
  }

  _formatDateTime(date) {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  }

  _formatDateLabel(dateKey) {
    var date = this._parseDate(dateKey + "T12:00:00");
    if (!date) {
      return dateKey;
    }
    return new Intl.DateTimeFormat(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(date);
  }

  _formatWeekLabel(weekKey, weekKeys, index) {
    if (index < 0) {
      return "";
    }
    var currentDate = this._parseDate(weekKey + "T12:00:00");
    if (!currentDate) {
      return "";
    }
    if (index === 0) {
      return new Intl.DateTimeFormat(undefined, { month: "short" }).format(currentDate);
    }
    var previousKey = weekKeys[index - 1];
    var previousDate = previousKey ? this._parseDate(previousKey + "T12:00:00") : null;
    if (!previousDate || previousDate.getMonth() !== currentDate.getMonth()) {
      return new Intl.DateTimeFormat(undefined, { month: "short" }).format(currentDate);
    }
    return "";
  }

  _parseDate(value) {
    var parsed = new Date(value);
    return isNaN(parsed.getTime()) ? null : parsed;
  }

  _formatLocalDate(date) {
    var year = date.getFullYear();
    var month = String(date.getMonth() + 1).padStart(2, "0");
    var day = String(date.getDate()).padStart(2, "0");
    return year + "-" + month + "-" + day;
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
    return "rgba(148,163,184,0.06)";
  }

  _emptyCellColor() {
    return this._hass && this._hass.themes && this._hass.themes.darkMode
      ? "rgba(148,163,184,0.16)"
      : "rgba(203,213,225,0.72)";
  }

  _pointStrokeColor(isFuture, hasData) {
    if (isFuture) {
      return "rgba(148,163,184,0.08)";
    }
    return hasData ? "rgba(15,23,42,0.16)" : "rgba(148,163,184,0.14)";
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
