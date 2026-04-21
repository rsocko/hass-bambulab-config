class PrintStatisticsFailureAnalysisCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._loading = false;
    this._error = "";
    this._data = null;
    this._requestKey = "";
  }

  setConfig(config) {
    this._config = {
      title: config && config.title ? String(config.title) : "Failure Analysis Handoff",
      default_days: config && Number.isFinite(Number(config.default_days))
        ? Math.max(1, Number(config.default_days))
        : 30,
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._refreshIfNeeded(false);
    this._render();
  }

  getCardSize() {
    return 4;
  }

  async _refreshIfNeeded(force) {
    if (!this._hass || !this._config) {
      return;
    }
    const context = this._readQueryContext();
    const requestKey = JSON.stringify(context);
    if (!force && requestKey === this._requestKey && (this._data || this._loading || this._error)) {
      return;
    }
    this._requestKey = requestKey;
    this._loading = true;
    this._error = "";
    this._render();
    try {
      this._data = await this._hass.callWS(this._buildRequest(context));
    } catch (error) {
      this._data = null;
      this._error = this._describeError(error);
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _readQueryContext() {
    const search = new URLSearchParams(window.location.search);
    return {
      source: String(search.get("source") || "").trim(),
      archive_id: this._normalizeInt(search.get("archive_id")),
      printer_id: this._normalizeInt(search.get("printer_id")),
      project_id: this._normalizeInt(search.get("project_id")),
      days: this._normalizeInt(search.get("days")) || this._config.default_days,
      date_from: String(search.get("date_from") || "").trim(),
      date_to: String(search.get("date_to") || "").trim(),
    };
  }

  _buildRequest(context) {
    const payload = {
      type: "bambuddy/failure_analysis_query",
    };
    if (context.printer_id) {
      payload.printer_id = context.printer_id;
    }
    if (context.project_id) {
      payload.project_id = context.project_id;
    }
    if (context.date_from) {
      payload.date_from = context.date_from;
    }
    if (context.date_to) {
      payload.date_to = context.date_to;
    }
    if (!context.date_from && !context.date_to && context.days) {
      payload.days = context.days;
    }
    return payload;
  }

  _normalizeInt(value) {
    const normalized = Number.parseInt(String(value || "").trim(), 10);
    return Number.isFinite(normalized) && normalized > 0 ? normalized : null;
  }

  _describeError(error) {
    if (error && typeof error === "object") {
      if (typeof error.message === "string" && error.message.trim()) {
        return error.message.trim();
      }
      if (typeof error.code === "string" && error.code.trim()) {
        return error.code.trim();
      }
    }
    return "Could not load filtered failure analysis.";
  }

  _render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }
    const context = this._readQueryContext();
    const activeScope = this._buildScope(context);
    const metrics = this._buildMetrics(this._data, context);
    const reasons = this._buildReasonRows(this._data);
    const recent = this._buildRecentRows(this._data);
    const hasScopedFilters = Boolean(
      context.source || context.archive_id || context.printer_id || context.project_id || context.date_from || context.date_to
    );
    const subtitle = hasScopedFilters
      ? "Scoped from the current Statistics URL and loaded through the Bambuddy failure-analysis websocket query."
      : "No Print History scope is active. Showing a default query window without changing the aggregate sensor-backed dashboard tiles."
    ;
    const actionLinks = this._buildActionLinks(context);

    this.shadowRoot.innerHTML = `
      <style>
        ha-card {
          border-radius: 18px;
        }
        .wrap {
          display: grid;
          gap: 14px;
          padding: 16px;
        }
        .header {
          display: grid;
          gap: 6px;
        }
        .title-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          flex-wrap: wrap;
        }
        .title {
          font-size: 16px;
          font-weight: 700;
          line-height: 1.2;
        }
        .subtitle {
          font-size: 12px;
          line-height: 1.5;
          color: var(--secondary-text-color);
        }
        .scope {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }
        .chip {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          min-height: 28px;
          padding: 0 10px;
          border-radius: 999px;
          background: rgba(21, 101, 192, 0.12);
          color: var(--primary-text-color);
          border: 1px solid rgba(21, 101, 192, 0.18);
          font-size: 11px;
          font-weight: 700;
        }
        .chip.neutral {
          background: rgba(148, 163, 184, 0.14);
          border-color: rgba(148, 163, 184, 0.18);
        }
        .metrics {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));
          gap: 10px;
        }
        .metric {
          padding: 12px;
          border-radius: 16px;
          background: rgba(148, 163, 184, 0.10);
          border: 1px solid rgba(148, 163, 184, 0.14);
        }
        .metric-label {
          font-size: 11px;
          color: var(--secondary-text-color);
          margin-bottom: 6px;
        }
        .metric-value {
          font-size: 22px;
          font-weight: 800;
          line-height: 1.1;
        }
        .panels {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
        }
        .panel {
          padding: 14px;
          border-radius: 16px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid var(--divider-color, rgba(148, 163, 184, 0.18));
          min-width: 0;
        }
        .panel-title {
          font-size: 12px;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          margin-bottom: 10px;
        }
        .list {
          display: grid;
          gap: 8px;
        }
        .row {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          gap: 10px;
          align-items: start;
          font-size: 12px;
        }
        .row-title {
          font-weight: 700;
          overflow-wrap: anywhere;
        }
        .row-meta {
          color: var(--secondary-text-color);
          text-align: right;
          white-space: nowrap;
        }
        .empty,
        .error,
        .loading {
          font-size: 12px;
          line-height: 1.5;
          color: var(--secondary-text-color);
        }
        .error {
          color: #ffb4ab;
        }
        .actions {
          display: flex;
          gap: 10px;
          flex-wrap: wrap;
        }
        .action {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-height: 32px;
          padding: 0 12px;
          border-radius: 999px;
          border: 1px solid rgba(148, 163, 184, 0.18);
          color: var(--primary-text-color);
          text-decoration: none;
          font-size: 12px;
          font-weight: 700;
          background: rgba(255, 255, 255, 0.04);
        }
        .action.primary {
          background: rgba(21, 101, 192, 0.18);
          border-color: rgba(21, 101, 192, 0.24);
        }
        @media (max-width: 760px) {
          .panels {
            grid-template-columns: 1fr;
          }
        }
      </style>
      <ha-card>
        <div class="wrap">
          <div class="header">
            <div class="title-row">
              <div class="title">${this._escapeHtml(this._config.title)}</div>
              <div class="actions">${actionLinks}</div>
            </div>
            <div class="subtitle">${this._escapeHtml(subtitle)}</div>
          </div>
          <div class="scope">${activeScope}</div>
          ${this._loading ? '<div class="loading">Loading filtered failure analysis...</div>' : ''}
          ${this._error ? `<div class="error">${this._escapeHtml(this._error)}</div>` : ''}
          ${!this._loading && !this._error ? `
            <div class="metrics">${metrics}</div>
            <div class="panels">
              <div class="panel">
                <div class="panel-title">Failures By Reason</div>
                <div class="list">${reasons}</div>
              </div>
              <div class="panel">
                <div class="panel-title">Recent Failures</div>
                <div class="list">${recent}</div>
              </div>
            </div>
          ` : ''}
        </div>
      </ha-card>
    `;
  }

  _buildScope(context) {
    const chips = [];
    if (context.source) {
      chips.push(this._chip("Source", context.source, false));
    }
    if (context.archive_id) {
      chips.push(this._chip("Archive", String(context.archive_id), false));
    }
    if (context.printer_id) {
      chips.push(this._chip("Printer", String(context.printer_id), false));
    }
    if (context.project_id) {
      chips.push(this._chip("Project", String(context.project_id), false));
    }
    if (context.date_from || context.date_to) {
      chips.push(this._chip("Dates", [context.date_from || "...", context.date_to || "..."].join(" to "), false));
    } else {
      chips.push(this._chip("Window", String(context.days) + " days", chips.length === 0));
    }
    return chips.join("");
  }

  _chip(label, value, neutral) {
    return `<span class="chip${neutral ? ' neutral' : ''}">${this._escapeHtml(label)}: ${this._escapeHtml(value)}</span>`;
  }

  _buildMetrics(data, context) {
    const payload = data || {};
    const rows = [
      ["Total Prints", this._formatNumber(payload.total_prints)],
      ["Failed Prints", this._formatNumber(payload.failed_prints)],
      ["Failure Rate", this._formatPercent(payload.failure_rate)],
      ["Period Days", this._formatNumber(payload.period_days || context.days)],
    ];
    return rows.map((row) => `
      <div class="metric">
        <div class="metric-label">${this._escapeHtml(row[0])}</div>
        <div class="metric-value">${this._escapeHtml(row[1])}</div>
      </div>
    `).join("");
  }

  _buildReasonRows(data) {
    const source = data && data.failures_by_reason && typeof data.failures_by_reason === "object"
      ? Object.entries(data.failures_by_reason)
      : [];
    if (!source.length) {
      return '<div class="empty">No failure reasons were returned for the active scope.</div>';
    }
    return source
      .sort((left, right) => Number(right[1] || 0) - Number(left[1] || 0))
      .slice(0, 5)
      .map((entry) => `
        <div class="row">
          <div class="row-title">${this._escapeHtml(String(entry[0] || "Unknown"))}</div>
          <div class="row-meta">${this._escapeHtml(this._formatNumber(entry[1]))}</div>
        </div>
      `)
      .join("");
  }

  _buildRecentRows(data) {
    const rows = Array.isArray(data && data.recent_failures) ? data.recent_failures : [];
    if (!rows.length) {
      return '<div class="empty">No recent failure rows were returned for the active scope.</div>';
    }
    return rows.slice(0, 4).map((row) => {
      const title = row && (row.print_name || row.project_name || row.failure_reason || row.archive_id || "Failure");
      const metaParts = [];
      if (row && row.failure_reason) {
        metaParts.push(String(row.failure_reason));
      }
      if (row && row.printer_name) {
        metaParts.push(String(row.printer_name));
      }
      if (row && row.completed_at) {
        metaParts.push(this._formatDate(row.completed_at));
      } else if (row && row.created_at) {
        metaParts.push(this._formatDate(row.created_at));
      }
      return `
        <div class="row">
          <div class="row-title">${this._escapeHtml(String(title))}</div>
          <div class="row-meta">${this._escapeHtml(metaParts.join(" | "))}</div>
        </div>
      `;
    }).join("");
  }

  _buildActionLinks(context) {
    const links = [];
    if (context.source || context.archive_id || context.printer_id || context.project_id || context.date_from || context.date_to) {
      links.push('<a class="action" href="/3d-printing/statistics">Clear Scope</a>');
    }
    if (context.archive_id) {
      links.push(`<a class="action primary" href="/3d-printing/print-history?archive_id=${encodeURIComponent(String(context.archive_id))}">Back To Archive</a>`);
    }
    return links.join("");
  }

  _formatNumber(value) {
    const numeric = Number(value || 0);
    return Number.isFinite(numeric) ? numeric.toLocaleString() : "0";
  }

  _formatPercent(value) {
    const numeric = Number(value || 0);
    return Number.isFinite(numeric) ? numeric.toFixed(1) + "%" : "0.0%";
  }

  _formatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return String(value || "");
    }
    return date.toLocaleDateString();
  }

  _escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
}

customElements.define("print-statistics-failure-analysis-card", PrintStatisticsFailureAnalysisCard);

window.customCards = window.customCards || [];
if (!window.customCards.some(function (card) { return card && card.type === "print-statistics-failure-analysis-card"; })) {
  window.customCards.push({
    type: "print-statistics-failure-analysis-card",
    name: "Print Statistics Failure Analysis Card",
    description: "Reads Statistics URL query params and loads filtered Bambuddy failure analysis.",
  });
}