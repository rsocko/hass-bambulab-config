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

    this._config = {
      title: config.title || "Bar Chart",
      height: config.height || 280,
      value_name: config.value_name || "value",
      chart_type: config.chart_type || "bar",
      entities: hasEntities ? config.entities : [],
      source_entity: config.source_entity || null,
      source_attribute: config.source_attribute || null,
      source_mode: config.source_mode || "object",
      label_key: config.label_key || "name",
      value_key: config.value_key || "value",
      color_key: config.color_key || "color",
      value_scale: Number(config.value_scale || 1),
      max_items: Number(config.max_items || 12),
      sort_desc: config.sort_desc !== false,
      horizontal: config.horizontal !== false,
      label_map: config.label_map && typeof config.label_map === "object" ? config.label_map : {},
      color_map: config.color_map && typeof config.color_map === "object" ? config.color_map : {},
      tap_actions: config.tap_actions && typeof config.tap_actions === "object" ? config.tap_actions : {},
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
            var color = item && item[this._config.color_key] ? String(item[this._config.color_key]) : (this._config.color_map[key] || this._config.default_color);
            return {
              x: this._config.label_map[key] || key,
              source_key: key,
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
              fillColor: this._config.color_map[key] || this._config.default_color,
              tap_action: this._config.tap_actions[key] || null,
            };
          }.bind(this)
        )
        .filter(function (row) {
          return isFinite(row.y) && row.y > 0;
        });
    }

    rows.sort(
      function (a, b) {
        return this._config.sort_desc ? b.y - a.y : a.y - b.y;
      }.bind(this)
    );

    if (this._config.max_items > 0 && rows.length > this._config.max_items) {
      rows = rows.slice(0, this._config.max_items);
    }

    return rows;
  }

  _buildSeries(rows) {
    if (this._config.chart_type === "donut") {
      return rows.map(function (r) {
        return Number(r.y || 0);
      });
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
    var chartType = this._config.chart_type === "donut" ? "donut" : "bar";
    var labels = rows.map(function (r) { return String(r.x || ""); });
    var colors = rows.map(function (r) { return r.fillColor || self._config.default_color; });

    if (chartType === "donut") {
      return {
        chart: {
          type: "donut",
          height: this._config.height,
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
          show: true,
          position: "bottom",
        },
        dataLabels: {
          enabled: true,
        },
        stroke: {
          show: true,
          width: 1,
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

    return {
      chart: {
        type: "bar",
        height: this._config.height,
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
        title: { text: this._config.value_name },
      },
      dataLabels: {
        enabled: true,
      },
      legend: { show: false },
      grid: { strokeDashArray: 3 },
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

    var idx = opts.dataPointIndex;
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
