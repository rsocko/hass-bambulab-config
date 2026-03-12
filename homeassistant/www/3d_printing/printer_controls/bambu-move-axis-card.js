class BambuMoveAxisCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.device_id) {
      throw new Error("bambu-move-axis-card requires device_id");
    }
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
  }

  getCardSize() {
    return 4;
  }

  _render() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          width: 100%;
        }
        .wrap {
          position: relative;
          width: 100%;
          max-width: 460px;
          margin: 0 auto;
          aspect-ratio: 1 / 1;
        }
        svg {
          width: 100%;
          height: 100%;
          display: block;
        }
        .outer-slice {
          fill: rgba(127, 140, 141, 0.48);
          stroke: rgba(22, 22, 22, 0.85);
          stroke-width: 1;
          cursor: pointer;
          transition: fill 0.15s ease;
        }
        .inner-slice {
          fill: rgba(189, 195, 199, 0.58);
          stroke: rgba(22, 22, 22, 0.85);
          stroke-width: 1;
          cursor: pointer;
          transition: fill 0.15s ease;
        }
        .middle {
          fill: rgba(166, 177, 181, 0.8);
          stroke: rgba(22, 22, 22, 0.9);
          stroke-width: 1;
          cursor: pointer;
          transition: fill 0.15s ease;
        }
        .outer-slice:hover {
          fill: rgba(66, 165, 245, 0.5);
        }
        .inner-slice:hover {
          fill: rgba(158, 158, 158, 0.55);
        }
        .middle:hover {
          fill: rgba(33, 150, 243, 0.35);
        }
        .label {
          position: absolute;
          width: 28px;
          height: 28px;
          display: flex;
          align-items: center;
          justify-content: center;
          transform: translate(-50%, -50%);
          pointer-events: none;
          color: #000000;
        }
        .label ha-icon {
          --mdc-icon-size: 28px;
          color: #000000;
        }
      </style>
      <div class="wrap">
        <svg viewBox="0 0 200 200" aria-label="XY movement control">
          <g>
            <path class="inner-slice" data-axis="X" data-distance="-1" d="M 100 125 L 100 160 A60 60 0 0 1 40 100 L75 100 A25 25 0 0 0 100 125 Z" transform="rotate(45, 100, 100)"></path>
            <path class="outer-slice" data-axis="X" data-distance="-10" d="M 100 160 L 100 190 A90 90 0 0 1 10 100 L40 100 A60 60 0 0 0 100 160 Z" transform="rotate(45, 100, 100)"></path>
            <path class="inner-slice" data-axis="X" data-distance="1" d="M 100 75 L 100 40 A60 60 0 0 1 160 100 L125 100 A25 25 0 0 0 100 75 Z" transform="rotate(45, 100, 100)"></path>
            <path class="outer-slice" data-axis="X" data-distance="10" d="M 100 40 L 100 10 A90 90 0 0 1 190 100 L160 100 A60 60 0 0 0 100 40 Z" transform="rotate(45, 100, 100)"></path>
            <path class="inner-slice" data-axis="Y" data-distance="1" d="M 75 100 L 40 100 A60 60 0 0 1 100 40 L100 75 A25 25 0 0 0 75 100 Z" transform="rotate(45, 100, 100)"></path>
            <path class="outer-slice" data-axis="Y" data-distance="10" d="M 40 100 L 10 100 A90 90 0 0 1 100 10 L100 40 A60 60 0 0 0 40 100 Z" transform="rotate(45, 100, 100)"></path>
            <path class="inner-slice" data-axis="Y" data-distance="-1" d="M 125 100 L 160 100 A60 60 0 0 1 100 160 L100 125 A25 25 0 0 0 125 100 Z" transform="rotate(45, 100, 100)"></path>
            <path class="outer-slice" data-axis="Y" data-distance="-10" d="M 160 100 L 190 100 A90 90 0 0 1 100 190 L100 160 A60 60 0 0 0 160 100 Z" transform="rotate(45, 100, 100)"></path>
          </g>
          <circle class="middle" data-axis="HOME" data-distance="0" cx="100" cy="100" r="25"></circle>
        </svg>

        <div class="label" style="left: 30%; top: 50%;"><ha-icon icon="mdi:chevron-left"></ha-icon></div>
        <div class="label" style="left: 12.5%; top: 50%;"><ha-icon icon="mdi:chevron-double-left"></ha-icon></div>
        <div class="label" style="left: 70%; top: 50%;"><ha-icon icon="mdi:chevron-right"></ha-icon></div>
        <div class="label" style="left: 87.5%; top: 50%;"><ha-icon icon="mdi:chevron-double-right"></ha-icon></div>

        <div class="label" style="left: 50%; top: 30%;"><ha-icon icon="mdi:chevron-up"></ha-icon></div>
        <div class="label" style="left: 50%; top: 12.5%;"><ha-icon icon="mdi:chevron-double-up"></ha-icon></div>
        <div class="label" style="left: 50%; top: 70%;"><ha-icon icon="mdi:chevron-down"></ha-icon></div>
        <div class="label" style="left: 50%; top: 87.5%;"><ha-icon icon="mdi:chevron-double-down"></ha-icon></div>

        <div class="label" style="left: 50%; top: 50%; width: 36px; height: 36px;"><ha-icon icon="mdi:home"></ha-icon></div>
      </div>
    `;

    this.shadowRoot.querySelectorAll("path[data-axis], circle[data-axis]").forEach((el) => {
      el.addEventListener("click", this._handleClick.bind(this));
    });
  }

  async _handleClick(ev) {
    if (!this._hass || !this._config) return;
    const axis = ev.currentTarget.getAttribute("data-axis");
    const distance = Number(ev.currentTarget.getAttribute("data-distance") || 0);

    if (axis === "HOME") {
      const msg = this._config.home_confirmation ||
        "Home the printer? This brings the heat bed to the nozzle - remove any model from the bed first to avoid damage.";
      const ok = window.confirm(msg);
      if (!ok) return;
    }

    await this._hass.callService("bambu_lab", "move_axis", {
      device_id: this._config.device_id,
      axis,
      distance,
    });
  }
}

customElements.define("bambu-move-axis-card", BambuMoveAxisCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "bambu-move-axis-card",
  name: "Bambu Move Axis Card",
  description: "SVG path-based XY movement control for Bambu printers",
});
