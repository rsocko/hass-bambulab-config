class ApexDirectBarCard extends HTMLElement {
  static _apexReadyPromise = null;

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._chart = null;
    this._container = null;
    this._isRendering = false;
  }

  setConfig(config) {
    if (!config || !Array.isArray(config.entities) || config.entities.length === 0) {
      throw new Error("apex-direct-bar-card requires a non-empty entities array");
    }

    this._config = {
      title: "Bar Chart",
      height: 280,
      value_name: "spools",
      entities: config.entities,
      ...config,
    };

    this._renderShell();
    this._scheduleRender();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) {
      return;
    }
    this._scheduleRender();
  }

  disconnectedCallback() {
    if (this._chart) {
      this._chart.destroy();
      this._chart = null;
    }
  }

  getCardSize() {
    return 5;
  }

  _renderShell() {
    if (!this.shadowRoot) {
      return;
    }

    this.shadowRoot.innerHTML = `
      <style>
        ha-card {
          padding: 12px;
        }
        .title {
          font-size: 1rem;
          font-weight: 500;
          margin: 0 0 8px 0;
        }
        .error {
          color: var(--error-color);
          font-size: 0.9rem;
          line-height: 1.35;
        }
      </style>
      <ha-card>
        <div class="title">${this._config.title}</div>
        <div id="chart"></div>
      </ha-card>
    `;

    this._container = this.shadowRoot.getElementById("chart");
  }

  _scheduleRender() {
    if (this._isRendering) {
      return;
    }

    this._isRendering = true;
    Promise.resolve()
      .then(() => this._renderChart())
      .catch((err) => this._showError(err?.message || String(err)))
      .finally(() => {
        this._isRendering = false;
      });
  }

  async _renderChart() {
    if (!this._container || !this._hass || !this._config) {
      return;
    }

    const ApexChartsCtor = await this._ensureApexCharts();
    if (!ApexChartsCtor) {
      throw new Error(
        "ApexCharts runtime not available. Verify /hacsfiles/apexcharts-card/apexcharts-card.js is loaded as a Lovelace resource."
      );
    }

    const rows = this._config.entities.map((entry) => {
      const st = this._hass.states[entry.entity];
      const raw = st ? st.state : "0";
      const value = Number.parseFloat(raw);
      return {
        name: entry.name || st?.attributes?.friendly_name || entry.entity,
        color: entry.color || "#42A5F5",
        value: Number.isFinite(value) ? value : 0,
      };
    });

    const categories = rows.map((r) => r.name);
    const values = rows.map((r) => r.value);
    const colors = rows.map((r) => r.color);

    const options = {
      chart: {
        type: "bar",
        height: this._config.height,
        toolbar: { show: false },
        animations: { enabled: false },
      },
      series: [
        {
          name: this._config.value_name,
          data: values,
        },
      ],
      plotOptions: {
        bar: {
          horizontal: true,
          borderRadius: 4,
          distributed: true,
        },
      },
      colors,
      dataLabels: {
        enabled: true,
      },
      xaxis: {
        title: {
          text: this._config.value_name,
        },
      },
      yaxis: {
        categories,
      },
      grid: {
        strokeDashArray: 3,
      },
      legend: {
        show: false,
      },
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

    if (!ApexDirectBarCard._apexReadyPromise) {
      ApexDirectBarCard._apexReadyPromise = new Promise((resolve) => {
        // If apexcharts-card already loaded ApexCharts globally, this resolves immediately.
        if (window.ApexCharts) {
          resolve(window.ApexCharts);
          return;
        }

        const script = document.createElement("script");
        script.src = "/hacsfiles/apexcharts-card/apexcharts-card.js";
        script.onload = () => resolve(window.ApexCharts || null);
        script.onerror = () => resolve(null);
        document.head.appendChild(script);
      });
    }

    return ApexDirectBarCard._apexReadyPromise;
  }

  _showError(message) {
    if (!this.shadowRoot) {
      return;
    }
    const chartEl = this.shadowRoot.getElementById("chart");
    if (!chartEl) {
      return;
    }
    chartEl.innerHTML = `<div class="error">${message}</div>`;
  }
}

customElements.define("apex-direct-bar-card", ApexDirectBarCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "apex-direct-bar-card",
  name: "Apex Direct Bar Card",
  preview: false,
  description: "Direct ApexCharts.js bar card for categorical sensors",
});
