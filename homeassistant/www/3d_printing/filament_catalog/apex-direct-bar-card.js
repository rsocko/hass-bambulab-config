var apexDirectBarReadyPromise = null;
var apexDirectImportTried = false;

class ApexDirectBarCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._chart = null;
    this._container = null;
    this._renderQueued = false;
  }

  setConfig(config) {
    if (!config) {
      throw new Error("apex-direct-bar-card requires configuration");
    }

    var hasEntities = Array.isArray(config.entities) && config.entities.length > 0;
    var hasSource = !!(config.source_entity && config.source_attribute);
    if (!hasEntities && !hasSource) {
      throw new Error("apex-direct-bar-card requires either entities[] or source_entity + source_attribute");
    }

    var axisTitle = config.axis_title;
    if (axisTitle === undefined || axisTitle === null) {
      axisTitle = config.value_name || "value";
    } else {
      axisTitle = String(axisTitle);
      if (axisTitle.trim() === "") {
        axisTitle = null;
      }
    }

    this._config = {
      title: config.title || "Bar Chart",
      height: config.height || 280,
      value_name: config.value_name || "value",
      axis_title: axisTitle,
      value_decimals: config.value_decimals === undefined || config.value_decimals === null
        ? null
        : Number(config.value_decimals),
      chart_type: config.chart_type || "bar",
      bar_mode: config.bar_mode || "standard",
      stack_category: config.stack_category || "Total",
      legend_show: config.legend_show !== false,
      legend_position: config.legend_position || "bottom",
      legend_font_size: config.legend_font_size || "12px",
      legend_max_width: Number(config.legend_max_width || 220),
      legend_item_margin_vertical: Number(config.legend_item_margin_vertical || 4),
      legend_item_margin_horizontal: Number(config.legend_item_margin_horizontal || 8),
      legend_offset_y: Number(config.legend_offset_y || 0),
      entities: hasEntities ? config.entities : [],
      source_entity: config.source_entity || null,
      source_attribute: config.source_attribute || null,
      source_mode: config.source_mode || "object",
      label_key: config.label_key || "name",
      value_key: config.value_key || "value",
      color_key: config.color_key || "color",
      category_key: config.category_key || null,
      segment_key: config.segment_key || null,
      value_scale: Number(config.value_scale || 1),
      max_items: config.max_items === undefined || config.max_items === null
        ? 12
        : Number(config.max_items),
      group_small_into_other: config.group_small_into_other === true,
      other_label: config.other_label || "Other",
      other_color: config.other_color || "#90A4AE",
      sort_desc: config.sort_desc !== false,
      sort_by_label: config.sort_by_label === true,
      horizontal: config.horizontal !== false,
      show_xaxis_labels: config.show_xaxis_labels !== false,
      auto_color_by_label: config.auto_color_by_label === true,
      label_map: config.label_map && typeof config.label_map === "object" ? config.label_map : {},
      color_map: config.color_map && typeof config.color_map === "object" ? config.color_map : {},
      tap_actions: config.tap_actions && typeof config.tap_actions === "object" ? config.tap_actions : {},
      marker_color: config.marker_color || "#FB8C00",
      default_color: config.default_color || "#42A5F5",
    };

    this._renderShell();
    this._queueRender();
  }

  set hass(hass) {
    this._hass = hass;
    this._queueRender();
  }

  disconnectedCallback() {
    if (this._chart && typeof this._chart.destroy === "function") {
      this._chart.destroy();
      this._chart = null;
    }
  }

  getCardSize() {
    return 5;
  }

  _renderShell() {
    this.shadowRoot.innerHTML =
      '<style>' +
      'ha-card{padding:12px;}' +
      '.title{font-size:1rem;font-weight:500;margin:0 0 8px 0;}' +
      '.error{color:var(--error-color);font-size:.9rem;line-height:1.35;}' +
      '</style>' +
      '<ha-card>' +
      '<div class="title">' + this._escapeHtml(this._config.title) + '</div>' +
      '<div id="chart"></div>' +
      '</ha-card>';

    this._container = this.shadowRoot.getElementById("chart");
  }

  _queueRender() {
    var self = this;
    if (self._renderQueued) {
      return;
    }
    self._renderQueued = true;

    Promise.resolve()
      .then(function () {
        return self._renderChart();
      })
      .catch(function (err) {
        self._showError(err && err.message ? err.message : String(err));
      })
      .then(function () {
        self._renderQueued = false;
      });
  }

  async _renderChart() {
    if (!this._container || !this._hass || !this._config) {
      return;
    }

    var ApexChartsCtor = await this._ensureApexCharts();
    if (!ApexChartsCtor) {
      throw new Error("ApexCharts runtime unavailable. Ensure apexcharts-card resource is loaded.");
    }

    var rows = this._buildRows();
    this._lastRows = rows;

    if (rows.length === 0) {
      this._showError("No chart data available.");
      return;
    }

    this._clearError();

    var self = this;

    var options = this._buildChartOptions(rows, self);

    if (!this._chart) {
      this._chart = new ApexChartsCtor(this._container, options);
      await this._chart.render();
      return;
    }

    await this._chart.updateOptions(options, false, false, false);
  }

  async _ensureApexCharts() {
    if (window.ApexCharts) {
      return window.ApexCharts;
    }

    if (!apexDirectBarReadyPromise) {
      apexDirectBarReadyPromise = this._resolveApexCharts();
    }

    return apexDirectBarReadyPromise;
  }

  _buildRows() {
    if (this._config.entities.length > 0) {
      return this._buildRowsFromEntities();
    }
    return this._buildRowsFromSource();
  }

  _buildRowsFromEntities() {
    var self = this;
    return this._config.entities
      .map(function (entry) {
        var st = self._hass.states[entry.entity];
        var raw = st ? st.state : "0";
        var parsed = parseFloat(raw);
        return {
          x: entry.name || (st && st.attributes && st.attributes.friendly_name) || entry.entity,
          y: isFinite(parsed) ? parsed : 0,
          fillColor: entry.color || self._config.default_color,
          tap_action: entry.tap_action || null,
        };
      })
      .filter(function (row) {
        return isFinite(row.y) && row.y > 0;
      });
  }

  _buildRowsFromSource() {
    var st = this._hass.states[this._config.source_entity];
    if (!st || !st.attributes) {
      return [];
    }

    var raw = st.attributes[this._config.source_attribute];
    var parsedData = this._parseSource(raw);

    var scale = isFinite(this._config.value_scale) && this._config.value_scale > 0 ? this._config.value_scale : 1;
    var rows = [];

    if (Array.isArray(parsedData)) {
      rows = parsedData
        .map(
          function (item) {
            var key = String(item && item[this._config.label_key] != null ? item[this._config.label_key] : "Unknown");
            var value = Number(item && item[this._config.value_key] != null ? item[this._config.value_key] : 0);
            var color = item && item[this._config.color_key]
              ? String(item[this._config.color_key])
              : (this._config.color_map[key] || (this._config.auto_color_by_label ? this._colorFromLabel(key) : this._config.default_color));
            return {
              x: this._config.label_map[key] || key,
              source_key: key,
              category: this._config.category_key ? String(item[this._config.category_key] || key) : null,
              segment: this._config.segment_key ? String(item[this._config.segment_key] || key) : null,
              y: isFinite(value) ? value * scale : 0,
              fillColor: color,
              tap_action: this._config.tap_actions[key] || null,
            };
          }.bind(this)
        )
        .filter(function (row) {
          return isFinite(row.y) && row.y > 0;
        });
    } else {
      rows = Object.entries(parsedData)
        .map(
          function (pair) {
            var key = String(pair[0]);
            var value = Number(pair[1] || 0);
            return {
              x: this._config.label_map[key] || key,
              source_key: key,
              y: isFinite(value) ? value * scale : 0,
              fillColor: this._config.color_map[key] || (this._config.auto_color_by_label ? this._colorFromLabel(key) : this._config.default_color),
              tap_action: this._config.tap_actions[key] || null,
            };
          }.bind(this)
        )
        .filter(function (row) {
          return isFinite(row.y) && row.y > 0;
        });
    }

    if (this._config.sort_by_label) {
      rows.sort(function (a, b) {
        return String(a.x || "").localeCompare(String(b.x || ""), undefined, { numeric: true, sensitivity: "base" });
      });
    } else {
      rows.sort(
        function (a, b) {
          return this._config.sort_desc ? b.y - a.y : a.y - b.y;
        }.bind(this)
      );
    }

    if (this._config.max_items > 0 && rows.length > this._config.max_items) {
      if (this._config.group_small_into_other) {
        var bySize = rows.slice().sort(function (a, b) {
          return b.y - a.y;
        });
        var keepCount = Math.max(1, this._config.max_items - 1);
        var kept = bySize.slice(0, keepCount);
        var remainder = bySize.slice(keepCount);
        var otherTotal = remainder.reduce(function (sum, row) {
          return sum + Number(row.y || 0);
        }, 0);

        if (otherTotal > 0) {
          kept.push({
            x: this._config.other_label,
            source_key: "__other__",
            y: otherTotal,
            fillColor: this._config.other_color,
            tap_action: null,
          });
        }

        rows = kept;
        if (this._config.sort_by_label) {
          rows.sort(function (a, b) {
            return String(a.x || "").localeCompare(String(b.x || ""), undefined, { numeric: true, sensitivity: "base" });
          });
        } else {
          rows.sort(
            function (a, b) {
              return this._config.sort_desc ? b.y - a.y : a.y - b.y;
            }.bind(this)
          );
        }
      } else {
        rows = rows.slice(0, this._config.max_items);
      }
    }

    return rows;
  }

  _buildSeries(rows) {
    if (this._config.chart_type === "donut") {
      return rows.map(function (r) {
        return Number(r.y || 0);
      });
    }
    if (this._config.chart_type === "treemap") {
      return [
        {
          name: this._config.value_name,
          data: rows.map(function (r) {
            return {
              x: String(r.x || ""),
              y: Number(r.y || 0),
              fillColor: r.fillColor,
            };
          }),
        },
      ];
    }
    return [
      {
        name: this._config.value_name,
        data: rows.map(function (r) {
          return Number(r.y || 0);
        }),
      },
    ];
  }

  _buildChartOptions(rows, self) {
    var chartType = this._config.chart_type === "donut"
      ? "donut"
      : (this._config.chart_type === "treemap"
        ? "treemap"
        : (this._config.chart_type === "radar" ? "radar" : "bar"));
    var labels = rows.map(function (r) { return String(r.x || ""); });
    var colors = rows.map(function (r) { return r.fillColor || self._config.default_color; });
    var isDark = !!(this._hass && this._hass.themes && this._hass.themes.darkMode);
    var textColor = isDark ? "#D1D5DB" : "#1F2937";
    var strongTextColor = isDark ? "#F3F4F6" : "#111827";
    var gridColor = isDark ? "rgba(148,163,184,0.28)" : "rgba(71,85,105,0.22)";

    if (chartType === "donut") {
      return {
        chart: {
          type: "donut",
          height: this._config.height,
          foreColor: textColor,
          toolbar: { show: false },
          animations: { enabled: false },
          events: {
            dataPointSelection: function (_event, _chartCtx, opts) {
              self._handlePointSelection(opts);
            },
          },
        },
        series: this._buildSeries(rows),
        labels: labels,
        colors: colors,
        legend: {
          show: this._config.legend_show,
          position: this._config.legend_position,
          width: this._config.legend_max_width,
          offsetY: this._config.legend_offset_y,
          itemMargin: {
            horizontal: this._config.legend_item_margin_horizontal,
            vertical: this._config.legend_item_margin_vertical,
          },
          markers: {
            width: 10,
            height: 10,
            radius: 10,
          },
          labels: {
            colors: textColor,
            useSeriesColors: false,
          },
          fontSize: this._config.legend_font_size,
        },
        dataLabels: {
          enabled: true,
          style: {
            colors: [strongTextColor],
          },
        },
        stroke: {
          show: true,
          width: 1,
        },
        tooltip: {
          theme: isDark ? "dark" : "light",
          y: {
            formatter: function (value) {
              return self._formatValue(value);
            },
          },
        },
        plotOptions: {
          pie: {
            donut: {
              size: "48%",
            },
          },
        },
      };
    }

    if (chartType === "treemap") {
      return {
        chart: {
          type: "treemap",
          height: this._config.height,
          foreColor: textColor,
          toolbar: { show: false },
          animations: { enabled: false },
          events: {
            dataPointSelection: function (_event, _chartCtx, opts) {
              self._handlePointSelection(opts);
            },
          },
        },
        series: this._buildSeries(rows),
        legend: {
          show: false,
        },
        dataLabels: {
          enabled: true,
          style: {
            colors: [strongTextColor],
          },
          formatter: function (_text, opts) {
            var point = opts && opts.w && opts.w.config && opts.w.config.series && opts.w.config.series[0] && opts.w.config.series[0].data
              ? opts.w.config.series[0].data[opts.dataPointIndex]
              : null;
            if (!point) {
              return "";
            }
            return String(point.x || "") + "\n" + self._formatValue(point.y);
          },
        },
        tooltip: {
          theme: isDark ? "dark" : "light",
          y: {
            formatter: function (value) {
              return self._formatValue(value);
            },
          },
        },
        plotOptions: {
          treemap: {
            distributed: true,
            enableShades: false,
          },
        },
        grid: {
          strokeDashArray: 0,
          borderColor: gridColor,
        },
      };
    }

    if (chartType === "radar") {
      return {
        chart: {
          type: "radar",
          height: this._config.height,
          foreColor: textColor,
          toolbar: { show: false },
          animations: { enabled: false },
          events: {
            dataPointSelection: function (_event, _chartCtx, opts) {
              self._handlePointSelection(opts);
            },
          },
        },
        series: this._buildSeries(rows),
        labels: labels,
        colors: [this._config.default_color],
        stroke: {
          width: 2,
        },
        fill: {
          opacity: 0.35,
        },
        markers: {
          size: 5,
          colors: [this._config.marker_color],
          strokeColors: isDark ? "#0F172A" : "#FFFFFF",
          strokeWidth: 2,
          fillOpacity: 1,
          strokeOpacity: 1,
          hover: {
            size: 7,
          },
        },
        xaxis: {
          labels: {
            show: true,
            offsetY: 8,
            style: {
              colors: labels.map(function () { return textColor; }),
            },
          },
        },
        yaxis: {
          show: false,
          tickAmount: 5,
          axisBorder: {
            show: false,
          },
          axisTicks: {
            show: false,
          },
          labels: {
            show: false,
            style: {
              colors: [textColor],
            },
            formatter: function (value) {
              return self._formatValue(value);
            },
          },
        },
        dataLabels: {
          enabled: false,
          formatter: function (value) {
            return self._formatValue(value);
          },
          style: {
            colors: [strongTextColor],
          },
        },
        legend: {
          show: this._config.legend_show,
          position: this._config.legend_position,
          labels: {
            colors: textColor,
            useSeriesColors: false,
          },
          fontSize: this._config.legend_font_size,
        },
        tooltip: {
          theme: isDark ? "dark" : "light",
          y: {
            formatter: function (value) {
              return self._formatValue(value);
            },
          },
        },
        plotOptions: {
          radar: {
            polygons: {
              strokeColors: gridColor,
              fill: {
                colors: isDark
                  ? ["rgba(148,163,184,0.10)", "rgba(148,163,184,0.18)"]
                  : ["rgba(100,116,139,0.08)", "rgba(100,116,139,0.16)"],
              },
            },
          },
        },
        grid: {
          strokeDashArray: 3,
          borderColor: gridColor,
        },
      };
    }

    if (this._config.bar_mode === "stacked_single_category") {
      return {
        chart: {
          type: "bar",
          height: this._config.height,
          foreColor: textColor,
          stacked: true,
          toolbar: { show: false },
          animations: { enabled: false },
          events: {
            dataPointSelection: function (_event, _chartCtx, opts) {
              self._handlePointSelection(opts);
            },
          },
        },
        series: rows.map(function (r) {
          return {
            name: String(r.x || "Series"),
            data: [Number(r.y || 0)],
            color: r.fillColor,
          };
        }),
        xaxis: {
          categories: [this._config.stack_category],
          title: { text: this._config.axis_title || "" },
          labels: {
            show: this._config.show_xaxis_labels,
            style: {
              colors: textColor,
            },
          },
          axisBorder: {
            color: gridColor,
          },
        },
        yaxis: {
          labels: {
            style: {
              colors: [textColor],
            },
          },
        },
        plotOptions: {
          bar: {
            horizontal: false,
            borderRadius: 2,
          },
        },
        dataLabels: {
          enabled: false,
        },
        legend: {
          show: this._config.legend_show,
          position: this._config.legend_position,
          labels: {
            colors: textColor,
            useSeriesColors: false,
          },
          fontSize: this._config.legend_font_size,
        },
        tooltip: {
          theme: isDark ? "dark" : "light",
          y: {
            formatter: function (value) {
              return self._formatValue(value);
            },
          },
        },
        grid: {
          strokeDashArray: 3,
          borderColor: gridColor,
        },
      };
    }

    if (this._config.bar_mode === "stacked_by_category") {
      var categories = [];
      var categoryIndex = {};
      var seriesMap = {};
      var seriesOrder = [];

      rows.forEach(function (row) {
        var cat = String(row.category || row.x || "Unknown");
        var seg = String(row.segment || row.x || "Segment");

        if (categoryIndex[cat] === undefined) {
          categoryIndex[cat] = categories.length;
          categories.push(cat);
          seriesOrder.forEach(function (existing) {
            seriesMap[existing].data.push(0);
          });
        }

        if (!seriesMap[seg]) {
          seriesMap[seg] = {
            name: seg,
            data: new Array(categories.length).fill(0),
            color: row.fillColor,
          };
          seriesOrder.push(seg);
        }

        while (seriesMap[seg].data.length < categories.length) {
          seriesMap[seg].data.push(0);
        }

        var idx = categoryIndex[cat];
        seriesMap[seg].data[idx] = (seriesMap[seg].data[idx] || 0) + Number(row.y || 0);
      });

      var stackedSeries = seriesOrder.map(function (name) {
        return seriesMap[name];
      });

      return {
        chart: {
          type: "bar",
          height: this._config.height,
          foreColor: textColor,
          stacked: true,
          toolbar: { show: false },
          animations: { enabled: false },
        },
        series: stackedSeries,
        xaxis: {
          categories: categories,
          title: { text: this._config.axis_title || "" },
          labels: {
            show: this._config.show_xaxis_labels,
            style: {
              colors: textColor,
            },
          },
          axisBorder: {
            color: gridColor,
          },
        },
        yaxis: {
          labels: {
            style: {
              colors: [textColor],
            },
            formatter: function (value) {
              return self._formatValue(value);
            },
          },
        },
        plotOptions: {
          bar: {
            horizontal: false,
            borderRadius: 2,
          },
        },
        dataLabels: {
          enabled: false,
        },
        legend: {
          show: this._config.legend_show,
          position: this._config.legend_position,
          labels: {
            colors: textColor,
            useSeriesColors: false,
          },
          fontSize: this._config.legend_font_size,
        },
        tooltip: {
          theme: isDark ? "dark" : "light",
          y: {
            formatter: function (value) {
              return self._formatValue(value);
            },
          },
        },
        grid: {
          strokeDashArray: 3,
          borderColor: gridColor,
        },
      };
    }

    return {
      chart: {
        type: "bar",
        height: this._config.height,
        foreColor: textColor,
        toolbar: { show: false },
        animations: { enabled: false },
        events: {
          dataPointSelection: function (_event, _chartCtx, opts) {
            self._handlePointSelection(opts);
          },
        },
      },
      series: this._buildSeries(rows),
      colors: colors,
      plotOptions: {
        bar: {
          horizontal: this._config.horizontal,
          borderRadius: 4,
          distributed: true,
        },
      },
      xaxis: {
        categories: labels,
        title: { text: this._config.axis_title || "" },
        labels: {
          show: this._config.show_xaxis_labels,
          style: {
            colors: textColor,
          },
        },
        axisBorder: {
          color: gridColor,
        },
      },
      yaxis: {
        labels: {
          style: {
            colors: labels.map(function () { return textColor; }),
          },
          formatter: function (value) {
            return self._formatValue(value);
          },
        },
      },
      dataLabels: {
        enabled: true,
        formatter: function (value) {
          return self._formatValue(value);
        },
        style: {
          colors: [strongTextColor],
        },
      },
      legend: { show: false },
      tooltip: {
        theme: isDark ? "dark" : "light",
        y: {
          formatter: function (value) {
            return self._formatValue(value);
          },
        },
      },
      grid: {
        strokeDashArray: 3,
        borderColor: gridColor,
      },
    };
  }

  _parseSource(raw) {
    if (this._config.source_mode === "array") {
      if (Array.isArray(raw)) {
        return raw;
      }
      if (typeof raw === "string" && raw.trim()) {
        try {
          var arr = JSON.parse(raw);
          return Array.isArray(arr) ? arr : [];
        } catch (_err) {
          return [];
        }
      }
      return [];
    }

    if (raw && typeof raw === "object" && !Array.isArray(raw)) {
      return raw;
    }
    if (typeof raw === "string" && raw.trim()) {
      try {
        var obj = JSON.parse(raw);
        return obj && typeof obj === "object" && !Array.isArray(obj) ? obj : {};
      } catch (_err2) {
        return {};
      }
    }
    return {};
  }

  _handlePointSelection(opts) {
    if (!opts || typeof opts.dataPointIndex !== "number" || !this._chart || !this._hass) {
      return;
    }

    var idx = this._config.bar_mode === "stacked_single_category" ? opts.seriesIndex : opts.dataPointIndex;
    var rows = this._lastRows || this._buildRows();
    if (idx < 0 || idx >= rows.length) {
      return;
    }

    var action = rows[idx].tap_action;
    if (!action || action.action !== "call-service" || !action.service) {
      return;
    }

    var serviceParts = String(action.service).split(".");
    if (serviceParts.length !== 2) {
      return;
    }

    var domain = serviceParts[0];
    var service = serviceParts[1];
    var data = action.data && typeof action.data === "object" ? action.data : {};
    var target = action.target && typeof action.target === "object" ? action.target : undefined;

    this._hass.callService(domain, service, data, target);
  }

  _clearError() {
    if (!this.shadowRoot) {
      return;
    }
    var errorEl = this.shadowRoot.querySelector(".error");
    if (errorEl && errorEl.parentElement) {
      errorEl.parentElement.removeChild(errorEl);
    }
  }

  _formatValue(value) {
    var n = Number(value);
    if (!isFinite(n)) {
      return String(value);
    }
    if (this._config.value_decimals !== null && isFinite(this._config.value_decimals)) {
      return n.toFixed(Math.max(0, this._config.value_decimals));
    }
    return String(n);
  }

  _colorFromLabel(label) {
    var s = String(label || "").toLowerCase();
    if (s.includes("black") && s.includes("white")) return "#94A3B8";
    if (s.includes("rainbow")) return "#8E44AD";
    if (s.includes("brown")) return "#8D6E63";
    if (s.includes("black")) return "#374151";
    if (s.includes("white")) return "#CBD5E1";
    if (s.includes("gray") || s.includes("grey") || s.includes("silver")) return "#9CA3AF";
    if (s.includes("blue")) return "#3B82F6";
    if (s.includes("green")) return "#22C55E";
    if (s.includes("red")) return "#EF4444";
    if (s.includes("orange")) return "#F97316";
    if (s.includes("yellow")) return "#EAB308";
    if (s.includes("purple") || s.includes("violet")) return "#8B5CF6";
    if (s.includes("pink")) return "#EC4899";
    return this._config.default_color;
  }

  async _resolveApexCharts() {
    if (window.ApexCharts) {
      return window.ApexCharts;
    }

    if (!apexDirectImportTried) {
      apexDirectImportTried = true;
      try {
        await import("/hacsfiles/apexcharts-card/apexcharts-card.js");
      } catch (_err) {
        // Ignore import errors and continue fallback checks.
      }
    }

    if (window.ApexCharts) {
      return window.ApexCharts;
    }

    return null;
  }

  _showError(message) {
    if (!this.shadowRoot) {
      return;
    }
    var chartEl = this.shadowRoot.getElementById("chart");
    if (!chartEl) {
      return;
    }
    chartEl.innerHTML = '<div class="error">' + this._escapeHtml(message) + "</div>";
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

if (!customElements.get("apex-direct-bar-card")) {
  customElements.define("apex-direct-bar-card", ApexDirectBarCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.find(function (c) { return c.type === "apex-direct-bar-card"; })) {
  window.customCards.push({
    type: "apex-direct-bar-card",
    name: "Apex Direct Bar Card",
    preview: false,
    description: "Direct ApexCharts.js bar card for categorical sensors",
  });
}
