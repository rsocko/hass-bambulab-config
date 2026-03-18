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
    if (!config || !Array.isArray(config.entities) || config.entities.length === 0) {
      throw new Error("apex-direct-bar-card requires a non-empty entities array");
    }

    this._config = {
      title: config.title || "Bar Chart",
      height: config.height || 280,
      value_name: config.value_name || "value",
      entities: config.entities,
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

    var rows = this._config.entities.map(
      function (entry) {
        var st = this._hass.states[entry.entity];
        var raw = st ? st.state : "0";
        var parsed = parseFloat(raw);
        return {
          x: entry.name || (st && st.attributes && st.attributes.friendly_name) || entry.entity,
          y: isFinite(parsed) ? parsed : 0,
          fillColor: entry.color || "#42A5F5"
        };
      }.bind(this)
    );

    var options = {
      chart: {
        type: "bar",
        height: this._config.height,
        toolbar: { show: false },
        animations: { enabled: false },
      },
      series: [
        {
          name: this._config.value_name,
          data: rows,
        },
      ],
      plotOptions: {
        bar: {
          horizontal: true,
          borderRadius: 4,
          distributed: false,
        },
      },
      xaxis: {
        title: { text: this._config.value_name },
      },
      dataLabels: {
        enabled: true,
      },
      legend: { show: false },
      grid: { strokeDashArray: 3 },
    };

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
