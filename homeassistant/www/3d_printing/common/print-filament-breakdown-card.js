class PrintFilamentBreakdownCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._archiveSortMode = null;
  }

  setConfig(config) {
    const mode = String(config && config.mode ? config.mode : "weight").toLowerCase();
    const source = String(config && config.source ? config.source : "live").toLowerCase();
    const archiveSort = String(config && config.archive_sort ? config.archive_sort : "auto").toLowerCase();
    if (["weight", "cost"].indexOf(mode) === -1) {
      throw new Error("print-filament-breakdown-card: mode must be 'weight' or 'cost'.");
    }
    if (["live", "archive"].indexOf(source) === -1) {
      throw new Error("print-filament-breakdown-card: source must be 'live' or 'archive'.");
    }
    if (["auto", "tray", "amount"].indexOf(archiveSort) === -1) {
      throw new Error("print-filament-breakdown-card: archive_sort must be 'auto', 'tray', or 'amount'.");
    }

    this._config = {
      mode: mode,
      source: source,
      archive_sort: archiveSort,
      title: config && config.title ? String(config.title) : "",
      show_title: !config || config.show_title !== false,
      show_issues: config && typeof config.show_issues === "boolean"
        ? config.show_issues
        : source === "archive" && mode === "weight",
      show_archive_sort_toggle: config && typeof config.show_archive_sort_toggle === "boolean"
        ? config.show_archive_sort_toggle
        : source === "archive",
      entity: config && config.entity
        ? String(config.entity)
        : (mode === "weight" ? "sensor.print_weight_effective" : "sensor.print_cost"),
      tray_map_entity: config && config.tray_map_entity
        ? String(config.tray_map_entity)
        : "sensor.spoolman_tray_map",
      tray_entity_prefix: config && config.tray_entity_prefix
        ? String(config.tray_entity_prefix)
        : "sensor.p1s_01p00c460102350_",
      external_spool_entity: config && config.external_spool_entity
        ? String(config.external_spool_entity)
        : "sensor.ntk_ryansoffice_3dprinter_external_spool",
      archive_entity: config && config.archive_entity
        ? String(config.archive_entity)
        : "sensor.print_history_popup_archive_detail",
      archive_json: config && config.archive_json ? String(config.archive_json) : "",
      label_threshold: config && Number.isFinite(Number(config.label_threshold))
        ? Math.max(0, Number(config.label_threshold))
        : 10,
    };
    this._archiveSortMode = null;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return this._config && this._config.show_issues ? 5 : 4;
  }

  _render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }

    const view = this._buildViewModel();
    const sortToggleHtml = view.sortOptions && view.sortOptions.length
      ? `<div class="sort-toggle" role="group" aria-label="Archive filament sort order">${view.sortOptions.map((option) => `<button class="sort-toggle-button${option.active ? " is-active" : ""}" data-sort-mode="${this._escapeHtml(option.value)}" type="button">${this._escapeHtml(option.label)}</button>`).join("")}</div>`
      : "";
    const headerSideHtml = `<div class="header-side${sortToggleHtml ? " has-sort-toggle" : ""}"><div class="total">${this._escapeHtml(view.totalLabel)}</div>${sortToggleHtml}</div>`;
    const titleHtml = this._config.show_title
      ? `<div class="header"><div class="title">${this._escapeHtml(view.title)}</div>${headerSideHtml}</div>`
      : `<div class="header header-compact">${headerSideHtml}</div>`;
    const barHtml = view.placeholder
      ? `<div class="placeholder"><div class="placeholder-bar">${view.placeholderLabel ? `<span class="placeholder-label">${this._escapeHtml(view.placeholderLabel)}</span>` : ""}</div>${view.placeholderMessage ? `<div class="placeholder-message">${this._escapeHtml(view.placeholderMessage)}</div>` : ""}</div>`
      : view.segments.length
        ? `<div class="bar">${view.segments.map((segment) => this._renderSegment(segment)).join("")}</div>`
        : "";
    const legendHtml = view.legend.length
      ? `<div class="legend">${view.legend.map((row) => this._renderLegendRow(row)).join("")}</div>`
      : "";
    const noticeHtml = view.notices.length
      ? `<div class="notices">${view.notices.map((notice) => this._renderNotice(notice)).join("")}</div>`
      : "";
    const issueHtml = view.issues.length
      ? `<div class="issues">${view.issues.map((issue) => this._renderIssue(issue)).join("")}</div>`
      : "";
    const emptyHtml = !barHtml && !legendHtml && !noticeHtml
      ? `<div class="empty">${this._escapeHtml(view.emptyMessage)}</div>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        ha-card {
          background: none;
          border: none;
          box-shadow: none;
          padding: 8px;
        }
        .wrap {
          display: flex;
          flex-direction: column;
          gap: 10px;
          min-width: 0;
        }
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          min-width: 0;
        }
        .header-compact {
          justify-content: flex-start;
        }
        .header-side {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 10px;
          min-width: 0;
          flex-wrap: wrap;
        }
        .header-compact .header-side {
          display: grid;
          grid-template-columns: minmax(0,1fr) auto;
          align-items: center;
          width: 100%;
          gap: 12px;
        }
        .title {
          font-size: 14px;
          font-weight: 600;
          line-height: 1.2;
          min-width: 0;
        }
        .sort-toggle {
          display: inline-flex;
          justify-self: end;
          border-radius: 999px;
          background: rgba(127, 127, 127, 0.12);
          border: 1px solid var(--divider-color, rgba(127, 127, 127, 0.3));
          overflow: hidden;
        }
        .sort-toggle-button {
          appearance: none;
          border: 0;
          background: transparent;
          color: var(--secondary-text-color, #888);
          cursor: pointer;
          font: inherit;
          font-size: 11px;
          font-weight: 600;
          line-height: 1;
          padding: 7px 10px;
        }
        .sort-toggle-button.is-active {
          background: var(--primary-color, #03a9f4);
          color: var(--text-primary-color, #ffffff);
        }
        .total {
          font-size: 14px;
          font-weight: 700;
          line-height: 1.2;
          white-space: nowrap;
        }
        .bar,
        .placeholder-bar {
          display: flex;
          align-items: stretch;
          height: 30px;
          border-radius: 6px;
          overflow: hidden;
          border: 1px solid var(--divider-color, rgba(127, 127, 127, 0.3));
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }
        .placeholder-bar {
          justify-content: center;
          background: linear-gradient(135deg, rgba(153,153,153,0.95) 0%, rgba(204,204,204,0.95) 50%, rgba(153,153,153,0.95) 100%);
        }
        .placeholder-label {
          align-self: center;
          font-size: 11px;
          font-weight: 700;
          color: #333;
          text-shadow: 0 0 2px rgba(255,255,255,0.8);
        }
        .placeholder-message,
        .empty {
          font-size: 12px;
          color: var(--secondary-text-color, #888);
          line-height: 1.4;
        }
        .segment {
          display: flex;
          align-items: center;
          justify-content: center;
          position: relative;
          min-width: 0;
        }
        .segment-label {
          font-size: 11px;
          font-weight: 600;
          line-height: 1;
          padding: 0 4px;
          text-shadow: 0 0 2px rgba(0, 0, 0, 0.3);
          white-space: nowrap;
        }
        .legend {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .legend-row {
          display: grid;
          grid-template-columns: 12px minmax(0, 1fr);
          gap: 8px;
          align-items: start;
          font-size: 12px;
          line-height: 1.4;
          color: var(--primary-text-color);
        }
        .legend-swatch {
          width: 12px;
          height: 12px;
          border-radius: 2px;
          margin-top: 2px;
          border: 1px solid var(--divider-color, rgba(127, 127, 127, 0.3));
          box-sizing: border-box;
        }
        .legend-main {
          min-width: 0;
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .legend-line {
          overflow-wrap: anywhere;
          word-break: break-word;
        }
        .legend-tray {
          opacity: 0.65;
        }
        .legend-meta,
        .legend-warning {
          color: var(--secondary-text-color, #888);
          font-size: 11px;
        }
        .legend-warning {
          color: #ffcc80;
        }
        .notices {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .notice {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          padding: 8px 10px;
          border-radius: 10px;
          font-size: 11px;
          line-height: 1.45;
        }
        .notice-icon {
          width: 14px;
          height: 14px;
          border-radius: 999px;
          flex: 0 0 auto;
          margin-top: 1px;
        }
        .issues {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
          gap: 8px;
        }
        .issue {
          padding: 10px 12px;
          border-radius: 12px;
          border: 1px solid rgba(255, 255, 255, 0.08);
          background: rgba(255, 255, 255, 0.04);
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .issue-title {
          font-size: 12px;
          font-weight: 700;
          line-height: 1.3;
        }
        .issue-body {
          font-size: 11px;
          line-height: 1.45;
          color: var(--secondary-text-color, #888);
        }
      </style>
      <ha-card>
        <div class="wrap">
          ${titleHtml}
          ${sortToggleHtml}
          ${barHtml}
          ${legendHtml}
          ${noticeHtml}
          ${issueHtml}
          ${emptyHtml}
        </div>
      </ha-card>
    `;

    Array.from(this.shadowRoot.querySelectorAll(".sort-toggle-button")).forEach(function (button) {
      button.addEventListener("click", this._handleSortToggleClick.bind(this));
    }.bind(this));
  }

  _renderSegment(segment) {
    const borderRight = segment.isLast ? "" : "border-right:1px solid var(--divider-color, rgba(127, 127, 127, 0.3));";
    const borderInset = segment.needsInsetBorder ? "box-shadow: inset 0 0 0 1px rgba(127, 127, 127, 0.5);" : "";
    const background = segment.background.indexOf("gradient") >= 0 || segment.background.indexOf("rgba(") === 0
      ? `background:${segment.background};`
      : `background-color:${segment.background};`;
    return `<div class="segment" style="width:${segment.percent}%;${background}${borderRight}${borderInset}" title="${this._escapeHtml(segment.tooltip)}">${segment.showInlineLabel ? `<span class="segment-label" style="color:${segment.textColor};">${this._escapeHtml(segment.inlineLabel)}</span>` : ""}</div>`;
  }

  _renderLegendRow(row) {
    return `
      <div class="legend-row" title="${this._escapeHtml(row.tooltip)}">
        <span class="legend-swatch" style="background:${row.swatch};${row.needsInsetBorder ? "box-shadow: inset 0 0 0 1px rgba(127, 127, 127, 0.5);" : ""}"></span>
        <div class="legend-main">
          <div class="legend-line">${row.primary}</div>
          ${row.secondary ? `<div class="legend-meta">${row.secondary}</div>` : ""}
          ${row.warning ? `<div class="legend-warning">${row.warning}</div>` : ""}
        </div>
      </div>`;
  }

  _renderNotice(notice) {
    const tone = notice.tone === "warning"
      ? { background: "rgba(245,124,0,0.14)", border: "rgba(245,124,0,0.28)", icon: "#FFCC80" }
      : { background: "rgba(21,101,192,0.12)", border: "rgba(21,101,192,0.28)", icon: "#90CAF9" };
    return `<div class="notice" style="background:${tone.background};border:1px solid ${tone.border};"><span class="notice-icon" style="background:${tone.icon};"></span><span>${this._escapeHtml(notice.text)}</span></div>`;
  }

  _renderIssue(issue) {
    const tone = issue.tone === "info"
      ? { background: "rgba(21,101,192,0.12)", border: "rgba(21,101,192,0.28)", title: "#E3F2FD" }
      : { background: "rgba(245,124,0,0.14)", border: "rgba(245,124,0,0.28)", title: "#FFE0B2" };
    return `<div class="issue" style="background:${tone.background};border-color:${tone.border};"><div class="issue-title" style="color:${tone.title};">${this._escapeHtml(issue.title)}</div><div class="issue-body">${this._escapeHtml(issue.body)}</div></div>`;
  }

  _buildViewModel() {
    if (!this._hass || !this._config) {
      return {
        title: this._defaultTitle(),
        totalLabel: "Loading...",
        segments: [],
        legend: [],
        notices: [],
        issues: [],
        emptyMessage: "Loading filament breakdown...",
        placeholder: false,
        sortOptions: [],
      };
    }

    return this._config.source === "archive"
      ? this._buildArchiveViewModel()
      : this._buildLiveViewModel();
  }

  _buildLiveViewModel() {
    return this._config.mode === "weight"
      ? this._buildLiveWeightViewModel()
      : this._buildLiveCostViewModel();
  }

  _buildLiveWeightViewModel() {
    const weightEntity = this._hass.states[this._config.entity];
    if (!weightEntity) {
      return this._emptyViewModel("No print data", "No print data available.");
    }

    const totalWeight = this._toNumber(weightEntity.state);
    const attributes = weightEntity.attributes || {};
    const trayMapEntity = this._hass.states[this._config.tray_map_entity];
    const trayMap = trayMapEntity && trayMapEntity.attributes && typeof trayMapEntity.attributes.tray_map === "object"
      ? trayMapEntity.attributes.tray_map
      : {};
    const entries = [];
    let knownWeight = 0;

    Object.keys(attributes).forEach(function (key) {
      const value = attributes[key];
      const numericWeight = this._toNumber(value);
      if ((key.indexOf("AMS") === 0 || key === "External" || key === "External Spool") && numericWeight > 0) {
        let trayMapKey = "";
        let trayEntityId = "";
        let trayLabel = "";
        const match = key.match(/AMS (\d+) Tray (\d+)/);
        if (match) {
          const amsNum = match[1];
          const trayNum = match[2];
          trayMapKey = "ams_" + amsNum + "_tray_" + trayNum;
          trayEntityId = this._config.tray_entity_prefix + trayMapKey;
          trayLabel = String.fromCharCode(64 + parseInt(amsNum, 10)) + trayNum;
        } else if (key === "External" || key === "External Spool") {
          trayMapKey = "external_spool";
          trayEntityId = this._config.external_spool_entity;
          trayLabel = "Ext";
        }
        const trayData = trayMap[trayMapKey] || {};
        const trayEntity = trayEntityId ? this._hass.states[trayEntityId] : null;
        const displayName = trayData.name && trayData.name !== "Empty" ? String(trayData.name) : key;
        const rawColor = trayData.color || (trayEntity && trayEntity.attributes ? trayEntity.attributes.color : "") || "#cccccc";
        entries.push({
          name: key,
          displayName: displayName,
          trayLabel: trayLabel,
          color: this._normalizeHex(rawColor) || "#CCCCCC",
          weight: numericWeight,
          tooltipExtras: [],
        });
        knownWeight += numericWeight;
      }
    }.bind(this));

    if (!entries.length && totalWeight > 0) {
      return this._placeholderViewModel({
        title: this._defaultTitle(),
        totalLabel: "Total: " + this._formatWeight(totalWeight),
        label: "Breakdown unavailable",
        message: "Filament usage details are not available for this print.",
      });
    }
    if (!entries.length || (knownWeight <= 0 && totalWeight <= 0)) {
      return this._emptyViewModel(this._defaultTitle(), "No print active or no weight data available.", "Total: -");
    }

    const notices = [];
    if (String(attributes.data_source || "") === "backup") {
      notices.push({ tone: "info", text: "Using backup print-weight data after a Home Assistant restart." });
    }

    return this._buildChartViewModel({
      title: this._defaultTitle(),
      totalLabel: "Total: " + this._formatWeight(totalWeight > 0 ? totalWeight : knownWeight),
      totalValue: totalWeight > 0 ? totalWeight : knownWeight,
      entries: entries,
      valueKey: "weight",
      valueFormatter: this._formatWeight.bind(this),
      tooltipFormatter: function (entry, percent) {
        return entry.displayName + (entry.trayLabel ? " [" + entry.trayLabel + "]" : "") + ": " + this._formatWeight(entry.weight) + " (" + percent.toFixed(1) + "%)";
      }.bind(this),
      legendPrimary: function (entry) {
        return this._escapeHtml(entry.displayName) + (entry.trayLabel ? ` <span class="legend-tray">[${this._escapeHtml(entry.trayLabel)}]</span>` : "") + ": <strong>" + this._escapeHtml(this._formatWeight(entry.weight)) + "</strong> (" + this._escapeHtml(this._formatPercent(entry.percent)) + ")";
      }.bind(this),
      legendSecondary: function () {
        return "";
      },
      notices: notices,
      issues: [],
      sortOptions: [],
    });
  }

  _buildLiveCostViewModel() {
    const costEntity = this._hass.states[this._config.entity];
    if (!costEntity) {
      return this._emptyViewModel("Estimated Print Cost", "No cost data available.");
    }

    const breakdown = costEntity.attributes && typeof costEntity.attributes.breakdown === "object"
      ? costEntity.attributes.breakdown
      : null;
    const totalCost = this._toNumber(costEntity.state);
    if (!breakdown || !totalCost) {
      return this._emptyViewModel(this._defaultTitle(), "No print active or no cost data available.", "Total: -");
    }

    const entries = Object.keys(breakdown).map(function (trayKey) {
      const data = breakdown[trayKey] || {};
      let trayLabel = "";
      const trayMatch = trayKey.match(/AMS (\d+) Tray (\d+)/);
      if (trayMatch) {
        trayLabel = String.fromCharCode(64 + parseInt(trayMatch[1], 10)) + trayMatch[2];
      } else if (trayKey === "External" || trayKey === "External Spool") {
        trayLabel = "Ext";
      }
      return {
        name: data.name || trayKey,
        displayName: data.name || trayKey,
        tray: trayKey,
        trayLabel: trayLabel,
        color: this._normalizeHex(data.color || "#888888") || "#888888",
        cost: this._toNumber(data.cost),
        weight: this._toNumber(data.weight),
        pricePerKg: this._toNumber(data.price_per_kg),
        priceSource: String(data.price_source || "default"),
      };
    }.bind(this)).filter(function (entry) {
      return entry.cost > 0;
    });

    if (!entries.length) {
      return this._emptyViewModel(this._defaultTitle(), "No print active or no cost data available.", "Total: -");
    }

    const notices = [];
    if (entries.some(function (entry) { return entry.priceSource === "default"; })) {
      notices.push({ tone: "warning", text: "One or more trays are using the default price. Set spool or filament pricing in Spoolman for more accurate cost." });
    }

    return this._buildChartViewModel({
      title: this._defaultTitle(),
      totalLabel: "Total: " + this._formatCurrency(totalCost),
      totalValue: totalCost,
      entries: entries,
      valueKey: "cost",
      valueFormatter: this._formatCurrency.bind(this),
      tooltipFormatter: function (entry) {
        return entry.displayName + (entry.trayLabel ? " [" + entry.trayLabel + "]" : "") + ": " + this._formatCurrency(entry.cost) + " (" + this._formatWeight(entry.weight) + ")";
      }.bind(this),
      legendPrimary: function (entry) {
        return this._escapeHtml(entry.displayName) + (entry.trayLabel ? ` <span class="legend-tray">[${this._escapeHtml(entry.trayLabel)}]</span>` : "") + ": <strong>" + this._escapeHtml(this._formatCurrency(entry.cost)) + "</strong>";
      }.bind(this),
      legendSecondary: function (entry) {
        const suffix = entry.priceSource === "default" ? " *" : "";
        return this._formatWeight(entry.weight) + " @ " + this._formatCurrency(entry.pricePerKg) + "/kg" + suffix;
      }.bind(this),
      notices: notices,
      issues: [],
      sortOptions: [],
    });
  }

  _buildArchiveViewModel() {
    const archive = this._resolveArchive();
    if (!archive || typeof archive !== "object" || archive.id == null) {
      return this._emptyViewModel(this._defaultTitle(), "No archived filament data is available.", "Total: -");
    }

    const notesInfo = this._splitArchiveNotes(archive.notes);
    const payload = notesInfo.payload || {};
    const rows = Array.isArray(archive.enrichment_filaments)
      ? archive.enrichment_filaments
      : Array.isArray(payload.F)
        ? payload.F
        : [];
    const totalWeight = this._toNumber(archive.filament_used_grams);
    const totalCost = this._toNumber(archive.cost);
    const enrichmentReason = String(archive.enrichment_reason || payload.reason || "").trim();
    const enrichmentSource = String(archive.enrichment_source || payload.src || "").trim();

    const entries = rows.map(function (row, index) {
      const weight = this._toNumber(row && (row.w != null ? row.w : row.used_grams));
      return {
        name: String(row && (row.n || row.name) || "Filament " + (index + 1)).trim(),
        displayName: String(row && (row.n || row.name) || "Filament " + (index + 1)).trim(),
        trayLabel: String(row && (row.t || row.tray) || "").trim(),
        weight: weight,
        color: this._normalizeHex(row && (row.h || row.color)) || "#9E9E9E",
        spoolId: row && (row.s != null ? row.s : row.spool_id),
        filamentId: row && (row.f != null ? row.f : row.filament_id),
        ambiguity: String(row && (row.am || row.a || row.ambiguity_code) || "").trim(),
      };
    }.bind(this)).filter(function (entry) {
      return entry.weight > 0;
    });

    const resolvedWeight = totalWeight > 0 ? totalWeight : entries.reduce(function (sum, entry) {
      return sum + entry.weight;
    }, 0);
    const knownWeight = entries.reduce(function (sum, entry) {
      return sum + entry.weight;
    }, 0);
    const gapWeight = resolvedWeight > knownWeight + 0.2 ? resolvedWeight - knownWeight : 0;
    if (gapWeight > 0) {
      entries.push({
        name: "Unattributed usage",
        displayName: "Unattributed usage",
        trayLabel: "",
        weight: gapWeight,
        color: "repeating-linear-gradient(135deg, rgba(120,144,156,0.95) 0 8px, rgba(176,190,197,0.95) 8px 16px)",
        spoolId: null,
        filamentId: null,
        ambiguity: "",
        synthetic: true,
      });
    }

    const unresolvedTrayCount = rows.filter(function (row) {
      return !String(row && (row.t || row.tray) || "").trim();
    }).length;
    const unresolvedSpoolCount = rows.filter(function (row) {
      return !this._hasResolvedId(row && (row.s != null ? row.s : row.spool_id));
    }.bind(this)).length;
    const unresolvedFilamentCount = rows.filter(function (row) {
      return !this._hasResolvedId(row && (row.f != null ? row.f : row.filament_id));
    }.bind(this)).length;
    const ambiguityCounts = {};
    rows.forEach(function (row) {
      const label = this._describeEnrichmentAmbiguity(row && (row.am || row.a || row.ambiguity_code));
      if (!label) {
        return;
      }
      ambiguityCounts[label] = (ambiguityCounts[label] || 0) + 1;
    }.bind(this));

    const notices = [];
    if (enrichmentSource === "at1") {
      notices.push({ tone: "warning", text: "This archive is using archive-level fallback enrichment. Structured tray matches are incomplete." });
    } else if (enrichmentSource === "afs") {
      notices.push({ tone: "info", text: "Structured enrichment rows were restored from archived filament slot data." });
    }
    if (this._config.mode === "cost" && totalCost > 0 && resolvedWeight > 0 && entries.length) {
      notices.push({ tone: "info", text: "Archive cost is stored only as a total. Per-filament cost below is apportioned by weight." });
    }
    if (enrichmentReason) {
      notices.push({ tone: gapWeight > 0 || unresolvedSpoolCount || unresolvedFilamentCount ? "warning" : "info", text: enrichmentReason });
    }

    const issues = [];
    if (this._config.show_issues) {
      if (gapWeight > 0) {
        issues.push({
          tone: "warning",
          title: "Unattributed usage remains",
          body: this._formatWeight(gapWeight) + " of " + this._formatWeight(resolvedWeight) + " is not covered by structured enrichment rows.",
        });
      }
      if (unresolvedTrayCount > 0) {
        issues.push({
          tone: "warning",
          title: "Tray resolution incomplete",
          body: unresolvedTrayCount + " filament row" + (unresolvedTrayCount === 1 ? " is" : "s are") + " still missing a tray label.",
        });
      }
      if (unresolvedSpoolCount > 0) {
        issues.push({
          tone: "warning",
          title: "Spool matches unresolved",
          body: unresolvedSpoolCount + " filament row" + (unresolvedSpoolCount === 1 ? " is" : "s are") + " missing a resolved spool ID.",
        });
      }
      if (unresolvedFilamentCount > 0) {
        issues.push({
          tone: "warning",
          title: "Filament matches unresolved",
          body: unresolvedFilamentCount + " filament row" + (unresolvedFilamentCount === 1 ? " is" : "s are") + " missing a resolved filament ID.",
        });
      }
      Object.keys(ambiguityCounts).forEach(function (label) {
        const count = ambiguityCounts[label];
        issues.push({
          tone: "warning",
          title: "Ambiguous match retained",
          body: (count > 1 ? count + " rows: " : "") + label,
        });
      });
    }

    if (!entries.length && resolvedWeight > 0 && this._config.mode === "weight") {
      return this._placeholderViewModel({
        title: this._defaultTitle(),
        totalLabel: "Total: " + this._formatWeight(resolvedWeight),
        label: "Breakdown unavailable",
        message: "This archive preserves a total filament weight but no structured per-filament rows.",
        notices: notices,
        issues: issues,
      });
    }
    if (!entries.length && totalCost > 0 && this._config.mode === "cost") {
      return this._placeholderViewModel({
        title: this._defaultTitle(),
        totalLabel: "Total: " + this._formatCurrency(totalCost),
        label: "Cost attribution unavailable",
        message: "This archive stores only a total cost, so no per-filament cost breakdown can be shown.",
        notices: notices,
        issues: issues,
      });
    }
    if (!entries.length) {
      return this._emptyViewModel(this._defaultTitle(), "No archived filament breakdown is available.", "Total: -", notices, issues);
    }

    const chartEntries = entries.map(function (entry) {
      const nextEntry = Object.assign({}, entry);
      if (this._config.mode === "cost" && totalCost > 0 && resolvedWeight > 0) {
        nextEntry.cost = totalCost * (entry.weight / resolvedWeight);
      }
      return nextEntry;
    }.bind(this));
    const sortOptions = this._archiveSortOptions(chartEntries);
    const sortedEntries = this._sortArchiveEntries(chartEntries, this._config.mode === "cost" ? "cost" : "weight");

    if (this._config.mode === "cost") {
      if (!(totalCost > 0 && resolvedWeight > 0)) {
        return this._emptyViewModel(this._defaultTitle(), "No archive cost data is available for this print.", "Total: -", notices, issues);
      }
      return this._buildChartViewModel({
        title: this._defaultTitle(),
        totalLabel: "Total: " + this._formatCurrency(totalCost),
        totalValue: totalCost,
        entries: sortedEntries,
        valueKey: "cost",
        valueFormatter: this._formatCurrency.bind(this),
        tooltipFormatter: function (entry, percent) {
          const base = entry.displayName + (entry.trayLabel ? " [" + entry.trayLabel + "]" : "") + ": " + this._formatCurrency(entry.cost) + " from " + this._formatWeight(entry.weight) + " (" + percent.toFixed(1) + "%)";
          return entry.synthetic ? base + " | Derived from unresolved weight share" : base;
        }.bind(this),
        legendPrimary: function (entry) {
          return this._escapeHtml(entry.displayName) + (entry.trayLabel ? ` <span class="legend-tray">[${this._escapeHtml(entry.trayLabel)}]</span>` : "") + ": <strong>" + this._escapeHtml(this._formatCurrency(entry.cost)) + "</strong> (" + this._escapeHtml(this._formatPercent(entry.percent)) + ")";
        }.bind(this),
        legendSecondary: function (entry) {
          if (entry.synthetic) {
            return this._formatWeight(entry.weight) + " not yet attributed to a resolved filament row";
          }
          const parts = [this._formatWeight(entry.weight)];
          if (this._hasResolvedId(entry.spoolId)) {
            parts.push("Spool #" + String(entry.spoolId));
          }
          if (this._hasResolvedId(entry.filamentId)) {
            parts.push("Filament #" + String(entry.filamentId));
          }
          return parts.join(" · ");
        }.bind(this),
        warningFormatter: this._archiveWarningFormatter.bind(this),
        notices: notices,
        issues: issues,
        sortOptions: sortOptions,
      });
    }

    return this._buildChartViewModel({
      title: this._defaultTitle(),
      totalLabel: "Total: " + this._formatWeight(resolvedWeight),
      totalValue: resolvedWeight,
      entries: sortedEntries,
      valueKey: "weight",
      valueFormatter: this._formatWeight.bind(this),
      tooltipFormatter: function (entry, percent) {
        const base = entry.displayName + (entry.trayLabel ? " [" + entry.trayLabel + "]" : "") + ": " + this._formatWeight(entry.weight) + " (" + percent.toFixed(1) + "%)";
        return entry.synthetic ? base + " | Structured enrichment rows do not yet cover this usage." : base;
      }.bind(this),
      legendPrimary: function (entry) {
        return this._escapeHtml(entry.displayName) + (entry.trayLabel ? ` <span class="legend-tray">[${this._escapeHtml(entry.trayLabel)}]</span>` : "") + ": <strong>" + this._escapeHtml(this._formatWeight(entry.weight)) + "</strong> (" + this._escapeHtml(this._formatPercent(entry.percent)) + ")";
      }.bind(this),
      legendSecondary: function (entry) {
        if (entry.synthetic) {
          return "Structured enrichment rows do not yet account for this usage share.";
        }
        const parts = [];
        if (this._hasResolvedId(entry.spoolId)) {
          parts.push("Spool #" + String(entry.spoolId));
        }
        if (this._hasResolvedId(entry.filamentId)) {
          parts.push("Filament #" + String(entry.filamentId));
        }
        return parts.join(" · ");
      }.bind(this),
      warningFormatter: this._archiveWarningFormatter.bind(this),
      notices: notices,
      issues: issues,
      sortOptions: sortOptions,
    });
  }

  _buildChartViewModel(options) {
    const totalValue = options.totalValue > 0
      ? options.totalValue
      : options.entries.reduce(function (sum, entry) {
          return sum + Number(entry[options.valueKey] || 0);
        }, 0);
    const denominator = totalValue > 0
      ? totalValue
      : options.entries.reduce(function (sum, entry) {
          return sum + Number(entry[options.valueKey] || 0);
        }, 0);
    const segments = [];
    const legend = [];
    options.entries.forEach(function (entry, index) {
      const value = Number(entry[options.valueKey] || 0);
      if (!(value > 0)) {
        return;
      }
      const percent = denominator > 0 ? (value / denominator) * 100 : 0;
      const swatch = entry.color || "#888888";
      const rgb = this._hexToRgb(swatch);
      const brightness = rgb ? ((rgb.r * 299) + (rgb.g * 587) + (rgb.b * 114)) / 1000 : 128;
      const needsInsetBorder = !entry.synthetic && (brightness > 240 || brightness < 20);
      const textColor = brightness > 128 ? "#000000" : "#ffffff";
      entry.percent = percent;
      segments.push({
        percent: percent,
        background: swatch,
        tooltip: options.tooltipFormatter(entry, percent),
        inlineLabel: options.valueFormatter(value),
        showInlineLabel: percent > this._config.label_threshold,
        textColor: entry.synthetic ? "#263238" : textColor,
        needsInsetBorder: entry.synthetic ? false : needsInsetBorder,
        isLast: index === options.entries.length - 1,
      });
      legend.push({
        swatch: swatch,
        tooltip: options.tooltipFormatter(entry, percent),
        primary: options.legendPrimary(entry),
        secondary: options.legendSecondary ? this._escapeHtml(options.legendSecondary(entry)) : "",
        warning: options.warningFormatter ? this._escapeHtml(options.warningFormatter(entry)) : "",
        needsInsetBorder: entry.synthetic ? false : needsInsetBorder,
      });
    }.bind(this));

    return {
      title: options.title,
      totalLabel: options.totalLabel,
      segments: segments,
      legend: legend,
      notices: options.notices || [],
      issues: options.issues || [],
      emptyMessage: "No filament breakdown available.",
      placeholder: false,
      sortOptions: options.sortOptions || [],
    };
  }

  _handleSortToggleClick(event) {
    const mode = event && event.currentTarget && event.currentTarget.dataset
      ? String(event.currentTarget.dataset.sortMode || "").trim().toLowerCase()
      : "";
    if (!["tray", "amount"].includes(mode) || mode === this._archiveSortMode) {
      return;
    }
    this._archiveSortMode = mode;
    this._render();
  }

  _archiveSortOptions(entries) {
    if (!this._config || this._config.source !== "archive" || !this._config.show_archive_sort_toggle) {
      return [];
    }
    if (!Array.isArray(entries) || entries.length < 2 || !entries.some(function (entry) { return this._hasTrayLocation(entry); }.bind(this))) {
      return [];
    }
    const activeMode = this._getArchiveSortMode(entries);
    return [
      { value: "tray", label: "Tray Location", active: activeMode === "tray" },
      { value: "amount", label: "Amount", active: activeMode === "amount" },
    ];
  }

  _sortArchiveEntries(entries, valueKey) {
    const activeMode = this._getArchiveSortMode(entries);
    return entries.slice().sort(function (left, right) {
      if (activeMode === "tray") {
        const trayCompare = this._compareTrayLocation(left, right);
        if (trayCompare !== 0) {
          return trayCompare;
        }
      }
      const valueCompare = this._toNumber(right[valueKey]) - this._toNumber(left[valueKey]);
      if (Math.abs(valueCompare) > 0.0001) {
        return valueCompare;
      }
      if (activeMode !== "tray") {
        const trayCompare = this._compareTrayLocation(left, right);
        if (trayCompare !== 0) {
          return trayCompare;
        }
      }
      return String(left.displayName || left.name || "").localeCompare(String(right.displayName || right.name || ""), undefined, { sensitivity: "base" });
    }.bind(this));
  }

  _getArchiveSortMode(entries) {
    if (this._archiveSortMode === "tray" || this._archiveSortMode === "amount") {
      return this._archiveSortMode;
    }
    if (this._config && this._config.archive_sort === "tray") {
      return "tray";
    }
    if (this._config && this._config.archive_sort === "amount") {
      return "amount";
    }
    return entries.some(function (entry) { return this._hasTrayLocation(entry); }.bind(this)) ? "tray" : "amount";
  }

  _hasTrayLocation(entry) {
    return !!this._parseTrayLabel(entry && entry.trayLabel);
  }

  _compareTrayLocation(left, right) {
    const leftTray = this._parseTrayLabel(left && left.trayLabel);
    const rightTray = this._parseTrayLabel(right && right.trayLabel);
    if (leftTray && rightTray) {
      if (leftTray.rank !== rightTray.rank) {
        return leftTray.rank - rightTray.rank;
      }
      if (leftTray.slot !== rightTray.slot) {
        return leftTray.slot - rightTray.slot;
      }
      if (leftTray.label !== rightTray.label) {
        return leftTray.label.localeCompare(rightTray.label, undefined, { sensitivity: "base" });
      }
      return 0;
    }
    if (leftTray) {
      return -1;
    }
    if (rightTray) {
      return 1;
    }
    return 0;
  }

  _parseTrayLabel(value) {
    const label = String(value || "").trim().toUpperCase();
    if (!label) {
      return null;
    }
    const expandedAmsMatch = label.match(/^AMS(\d+)-(\d+)$/);
    if (expandedAmsMatch) {
      return {
        rank: Math.max(0, parseInt(expandedAmsMatch[1], 10) - 1),
        slot: parseInt(expandedAmsMatch[2], 10),
        label: label,
      };
    }
    const amsMatch = label.match(/^([A-Z])(\d+)$/);
    if (amsMatch) {
      return {
        rank: amsMatch[1].charCodeAt(0) - 65,
        slot: parseInt(amsMatch[2], 10),
        label: label,
      };
    }
    if (label === "EXT") {
      return {
        rank: 99,
        slot: 0,
        label: label,
      };
    }
    return null;
  }

  _archiveWarningFormatter(entry) {
    if (entry.synthetic) {
      return "Needs review";
    }
    const warnings = [];
    if (!String(entry.trayLabel || "").trim()) {
      warnings.push("Tray unresolved");
    }
    if (!this._hasResolvedId(entry.spoolId)) {
      warnings.push("Spool unresolved");
    }
    if (!this._hasResolvedId(entry.filamentId)) {
      warnings.push("Filament unresolved");
    }
    const ambiguity = this._describeEnrichmentAmbiguity(entry.ambiguity);
    if (ambiguity) {
      warnings.push(ambiguity);
    }
    return warnings.join(" • ");
  }

  _resolveArchive() {
    let snapshot = {};
    try {
      snapshot = JSON.parse(this._config.archive_json || "{}");
    } catch (_error) {
      snapshot = {};
    }

    const detailState = this._hass.states[this._config.archive_entity];
    if (!detailState) {
      return snapshot;
    }

    try {
      const detailRaw = detailState.attributes && detailState.attributes.archive_json ? detailState.attributes.archive_json : "{}";
      const detailArchive = typeof detailRaw === "string" ? JSON.parse(detailRaw || "{}") : detailRaw;
      const snapshotId = snapshot && snapshot.id != null ? String(snapshot.id) : "";
      const detailId = detailState.state != null ? String(detailState.state) : (detailArchive && detailArchive.id != null ? String(detailArchive.id) : "");
      if (!snapshotId || snapshotId === detailId) {
        return Object.assign({}, snapshot, detailArchive || {});
      }
    } catch (_error) {
      return snapshot;
    }

    return snapshot;
  }

  _splitArchiveNotes(value) {
    const raw = String(value || "");
    const markerIndex = raw.indexOf("+>");
    const recoveryIndex = raw.indexOf("[RECOVERY_AUDIT_V1]");
    const indexes = [markerIndex, recoveryIndex].filter(function (index) {
      return index >= 0;
    });
    if (!indexes.length) {
      return { userNotes: raw.trimEnd(), payload: null };
    }
    const cutoff = Math.min.apply(null, indexes);
    const userNotes = raw.slice(0, cutoff).replace(/\n+$/u, "");
    const payloadRaw = markerIndex >= 0 ? raw.slice(markerIndex + 2).trim() : "";
    try {
      return { userNotes: userNotes, payload: payloadRaw ? JSON.parse(payloadRaw) : null };
    } catch (_error) {
      return { userNotes: userNotes, payload: null };
    }
  }

  _defaultTitle() {
    if (this._config.title) {
      return this._config.title;
    }
    if (this._config.source === "archive") {
      return this._config.mode === "weight" ? "Archived Filament Weight" : "Archived Filament Cost";
    }
    return this._config.mode === "weight" ? "Current Print Weight" : "Estimated Print Cost";
  }

  _emptyViewModel(title, emptyMessage, totalLabel, notices, issues) {
    return {
      title: title || this._defaultTitle(),
      totalLabel: totalLabel || "Total: -",
      segments: [],
      legend: [],
      notices: notices || [],
      issues: issues || [],
      emptyMessage: emptyMessage,
      placeholder: false,
      sortOptions: [],
    };
  }

  _placeholderViewModel(options) {
    return {
      title: options.title || this._defaultTitle(),
      totalLabel: options.totalLabel || "Total: -",
      segments: [],
      legend: [],
      notices: options.notices || [],
      issues: options.issues || [],
      emptyMessage: "",
      placeholder: true,
      placeholderLabel: options.label || "Breakdown unavailable",
      placeholderMessage: options.message || "",
      sortOptions: [],
    };
  }

  _toNumber(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : 0;
  }

  _formatWeight(value) {
    const numeric = this._toNumber(value);
    return numeric > 0 ? numeric.toFixed(1).replace(/\.0$/, "") + "g" : "-";
  }

  _formatCurrency(value) {
    const numeric = this._toNumber(value);
    return numeric > 0 ? "$" + numeric.toFixed(2) : "-";
  }

  _formatPercent(value) {
    const numeric = this._toNumber(value);
    return numeric.toFixed(1) + "%";
  }

  _hasResolvedId(value) {
    if (value === null || value === undefined) {
      return false;
    }
    const normalized = String(value).trim().toLowerCase();
    return normalized !== "" && normalized !== "null" && normalized !== "none" && normalized !== "unknown";
  }

  _normalizeHex(value) {
    const raw = String(value || "").trim().replace(/^#/, "").replace(/"/g, "");
    if (!raw) {
      return "";
    }
    const trimmed = raw.length === 8 ? raw.slice(0, 6) : raw;
    return /^[0-9a-fA-F]{6}$/.test(trimmed) ? ("#" + trimmed.toUpperCase()) : "";
  }

  _hexToRgb(value) {
    const normalized = this._normalizeHex(value);
    if (!normalized) {
      return null;
    }
    return {
      r: parseInt(normalized.slice(1, 3), 16),
      g: parseInt(normalized.slice(3, 5), 16),
      b: parseInt(normalized.slice(5, 7), 16),
    };
  }

  _describeEnrichmentAmbiguity(value) {
    const normalized = String(value || "").trim();
    return ({
        a_tc: "Multiple candidate spools or filaments matched type+color",
        a_fb: "Archive-level fallback matched multiple candidate spools or filaments",
      s_uuid: "Multiple Spoolman spools matched archived tray UUID",
      s_tc: "Multiple Spoolman spools matched type+color",
    })[normalized] || normalized;
  }

  _escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
}

customElements.define("print-filament-breakdown-card", PrintFilamentBreakdownCard);