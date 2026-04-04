class PrintHistoryColorFilterCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._signature = "";
    this._busyColor = "";
  }

  setConfig(config) {
    this._config = {
      colors_entity: "sensor.print_history_filtered",
      colors_attribute: "available_colors_json",
      tooltips_attribute: "available_color_tooltips_json",
      selected_entity: "input_text.print_history_filter_colors",
      toggle_script: "script.toggle_print_history_color_filter",
      slot_size: 38,
      ring_size: 30,
      fill_size: 22,
      selected_border_width: 3,
      unselected_border_width: 1,
      gap: 2,
      mobile_gap: 2,
      ...config,
    };
    this._signature = "";
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) {
      return;
    }

    const colorsState = hass.states?.[this._config.colors_entity];
    const selectedState = hass.states?.[this._config.selected_entity];
    const signature = [
      selectedState?.state || "",
      JSON.stringify(colorsState?.attributes?.[this._config.colors_attribute] || ""),
      JSON.stringify(colorsState?.attributes?.[this._config.tooltips_attribute] || ""),
      this._busyColor,
    ].join("|");

    if (signature === this._signature) {
      return;
    }
    this._signature = signature;
    this._render();
  }

  getCardSize() {
    return 2;
  }

  _escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _normalizeColor(value) {
    const raw = String(value || "").trim();
    return /^#[0-9a-fA-F]{6}$/.test(raw) ? raw.toLowerCase() : "";
  }

  _formatColorLabel(color) {
    return String(color || "").toUpperCase();
  }

  _availableColors() {
    const raw = this._hass?.states?.[this._config.colors_entity]?.attributes?.[this._config.colors_attribute];
    let values = [];

    if (Array.isArray(raw)) {
      values = raw;
    } else if (typeof raw === "string") {
      try {
        const parsed = JSON.parse(raw);
        values = Array.isArray(parsed) ? parsed : [];
      } catch (_err) {
        values = [];
      }
    }

    return values
      .map((value) => this._normalizeColor(value))
      .filter(Boolean);
  }

  _availableTooltips() {
    const raw = this._hass?.states?.[this._config.colors_entity]?.attributes?.[this._config.tooltips_attribute];
    let values = [];

    if (Array.isArray(raw)) {
      values = raw;
    } else if (typeof raw === "string") {
      try {
        const parsed = JSON.parse(raw);
        values = Array.isArray(parsed) ? parsed : [];
      } catch (_err) {
        values = [];
      }
    }

    return values.reduce((tooltips, value) => {
      if (!value || typeof value !== "object") {
        return tooltips;
      }

      const color = this._normalizeColor(value.color);
      const tooltip = String(value.tooltip || "").trim();
      if (color && tooltip) {
        tooltips.set(color, tooltip);
      }

      return tooltips;
    }, new Map());
  }

  _selectedColors() {
    const raw = this._hass?.states?.[this._config.selected_entity]?.state || "";
    return new Set(
      String(raw)
        .split(",")
        .map((value) => value.trim().toLowerCase())
        .filter(Boolean)
    );
  }

  async _toggleColor(color) {
    if (!this._hass || !this._config.toggle_script || this._busyColor) {
      return;
    }

    this._busyColor = color;
    this._render();

    const scriptId = String(this._config.toggle_script || "").replace(/^script\./, "");
    try {
      await this._hass.callService("script", scriptId, { color });
    } finally {
      this._busyColor = "";
      this._signature = "";
      this._render();
    }
  }

  _render() {
    if (!this._config || !this.shadowRoot) {
      return;
    }

    const colors = this._availableColors();
    const tooltips = this._availableTooltips();
    const selected = this._selectedColors();
    const slotSize = Number(this._config.slot_size || 38);
    const ringSize = Number(this._config.ring_size || 30);
    const fillSize = Number(this._config.fill_size || 22);
    const selectedBorderWidth = Number(this._config.selected_border_width || 3);
    const unselectedBorderWidth = Number(this._config.unselected_border_width || 1);
    const gap = Number(this._config.gap || 2);
    const mobileGap = Number(this._config.mobile_gap || gap);

    const swatches = colors
      .map((color) => {
        const isSelected = selected.has(color.toLowerCase());
        const isBusy = this._busyColor === color;
        const tooltip = tooltips.get(color.toLowerCase()) || this._formatColorLabel(color);
        const border = isSelected
          ? `${selectedBorderWidth}px solid var(--accent-color)`
          : `${unselectedBorderWidth}px solid rgba(255,255,255,0.24)`;
        const safeColor = this._escapeHtml(color);
        const safeTooltip = this._escapeHtml(tooltip);

        return `
          <button
            class="swatch ${isSelected ? "selected" : ""} ${isBusy ? "busy" : ""}"
            type="button"
            data-color="${safeColor}"
            aria-label="Toggle color ${safeTooltip} filter"
            aria-pressed="${isSelected ? "true" : "false"}"
            title="${safeTooltip}"
            style="width:${slotSize}px;height:${slotSize}px;"
          >
            <span class="ring" style="width:${ringSize}px;height:${ringSize}px;border:${border};">
              <span class="fill" style="width:${fillSize}px;height:${fillSize}px;background:${safeColor};"></span>
            </span>
            <span class="tooltip" role="tooltip">${safeTooltip}</span>
          </button>`;
      })
      .join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }

        ha-card {
          background: transparent;
          border: none;
          box-shadow: none;
          padding: 0;
        }

        .wrap {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: ${gap}px;
        }

        .swatch {
          appearance: none;
          -webkit-appearance: none;
          background: transparent;
          border: none;
          padding: 0;
          margin: 0;
          display: grid;
          place-items: center;
          cursor: pointer;
          overflow: visible;
          position: relative;
        }

        .ring {
          border-radius: 999px;
          display: flex;
          align-items: center;
          justify-content: center;
          box-sizing: border-box;
          transition: transform 0.12s ease, filter 0.12s ease, border-color 0.12s ease;
        }

        .fill {
          border-radius: 999px;
          display: block;
        }

        .tooltip {
          position: absolute;
          left: 50%;
          bottom: calc(100% + 6px);
          transform: translateX(-50%) translateY(4px);
          background: rgba(17, 24, 39, 0.94);
          color: #f9fafb;
          border-radius: 999px;
          padding: 3px 8px;
          font-size: 11px;
          line-height: 1.2;
          white-space: nowrap;
          pointer-events: none;
          opacity: 0;
          transition: opacity 0.12s ease, transform 0.12s ease;
          z-index: 2;
        }

        .swatch:hover .ring {
          filter: brightness(1.05);
        }

        .swatch:hover .tooltip,
        .swatch:focus-visible .tooltip {
          opacity: 1;
          transform: translateX(-50%) translateY(0);
        }

        .swatch:active .ring,
        .swatch.busy .ring {
          transform: scale(0.96);
        }

        .swatch:focus-visible {
          outline: none;
        }

        @media (max-width: 768px) {
          .wrap {
            gap: ${mobileGap}px;
          }
        }
      </style>
      <ha-card>
        <div class="wrap">${swatches}</div>
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll(".swatch").forEach((button) => {
      button.addEventListener("click", () => this._toggleColor(button.dataset.color || ""));
    });
  }
}

customElements.define("print-history-color-filter-card", PrintHistoryColorFilterCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "print-history-color-filter-card",
  name: "Print History Color Filter Card",
  description: "Compact selectable filament color swatches for print history filtering.",
});