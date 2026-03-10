class SkipObjectsDirectCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._selected = new Set();
    this._submitting = false;
    this._message = "";
    this._error = false;
  }

  setConfig(config) {
    if (!config || !config.device_id || !config.printable_entity || !config.skipped_entity) {
      throw new Error("skip-objects-direct-card requires device_id, printable_entity, and skipped_entity");
    }
    this._config = {
      title: "Skip Objects",
      ...config,
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 5;
  }

  _getPrintableMap() {
    const state = this._hass?.states?.[this._config.printable_entity];
    const objects = state?.attributes?.objects;
    if (!objects || typeof objects !== "object") {
      return {};
    }
    return objects;
  }

  _getSkippedList() {
    const state = this._hass?.states?.[this._config.skipped_entity];
    const objects = state?.attributes?.objects;
    if (!Array.isArray(objects)) {
      return [];
    }
    return objects.map((x) => Number(x)).filter((x) => Number.isInteger(x));
  }

  _isSelectionDirty(skippedList) {
    for (const id of this._selected) {
      if (!skippedList.includes(id)) {
        return true;
      }
    }
    return false;
  }

  _setMessage(text, isError = false) {
    this._message = text;
    this._error = isError;
  }

  async _submitSkip() {
    if (!this._hass || !this._config || this._submitting) {
      return;
    }

    const skippedList = this._getSkippedList();
    const combined = Array.from(new Set([...skippedList, ...Array.from(this._selected)])).sort(
      (a, b) => a - b
    );

    if (combined.length === 0) {
      this._setMessage("No objects selected.", true);
      this._render();
      return;
    }

    this._submitting = true;
    this._setMessage("");
    this._render();

    try {
      await this._hass.callService("bambu_lab", "skip_objects", {
        device_id: this._config.device_id,
        objects: combined.join(","),
      });
      this._setMessage("Skip request sent.");
    } catch (err) {
      this._setMessage(`Failed to skip objects: ${err?.message || err}`, true);
    } finally {
      this._submitting = false;
      this._render();
    }
  }

  async _closePopup() {
    if (!this._hass) {
      return;
    }
    try {
      await this._hass.callService("browser_mod", "close_popup", {});
    } catch (err) {
      // Browser mod may not be available in all contexts.
    }
  }

  _render() {
    try {
      if (!this.shadowRoot || !this._config) {
        return;
      }

    const printable = this._getPrintableMap();
    const skippedList = this._getSkippedList();

    // Keep selection only for currently-known objects.
    const validIds = new Set(Object.keys(printable).map((k) => Number(k)));
    this._selected = new Set(Array.from(this._selected).filter((id) => validIds.has(id)));

    const sortedEntries = Object.entries(printable).sort((a, b) => Number(a[0]) - Number(b[0]));
    const canSubmit = this._isSelectionDirty(skippedList) && !this._submitting;

    const rows =
      sortedEntries.length === 0
        ? "<div class='empty'>No printable object data available.</div>"
        : sortedEntries
            .map(([idStr, name]) => {
              const id = Number(idStr);
              const isSkipped = skippedList.includes(id);
              const checked = isSkipped || this._selected.has(id);
              const disabled = isSkipped ? "disabled" : "";
              const status = isSkipped ? "<span class='pill skipped'>Skipped</span>" : "";
              return `
                <label class='row ${isSkipped ? "is-skipped" : ""}'>
                  <input type='checkbox' data-id='${id}' ${checked ? "checked" : ""} ${disabled}>
                  <span class='name'>${String(name)}</span>
                  <span class='meta'>ID ${id}</span>
                  ${status}
                </label>
              `;
            })
            .join("");

    const message = this._message
      ? `<div class='message ${this._error ? "error" : "ok"}'>${this._message}</div>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .card {
          background: var(--card-background-color, #1f1f1f);
          color: var(--primary-text-color, #fff);
          border-radius: 12px;
          padding: 12px;
          box-sizing: border-box;
          font-family: var(--paper-font-body1_-_font-family, sans-serif);
        }
        .header {
          font-size: 16px;
          font-weight: 700;
          margin-bottom: 8px;
        }
        .sub {
          font-size: 12px;
          color: var(--secondary-text-color, #9aa0a6);
          margin-bottom: 10px;
        }
        .list {
          display: grid;
          gap: 6px;
          max-height: 48vh;
          overflow: auto;
          padding-right: 2px;
        }
        .row {
          display: grid;
          grid-template-columns: 20px 1fr auto auto;
          align-items: center;
          gap: 8px;
          background: rgba(127, 127, 127, 0.12);
          border-radius: 8px;
          padding: 8px;
          cursor: pointer;
          user-select: none;
        }
        .row.is-skipped {
          opacity: 0.7;
        }
        .name {
          font-size: 13px;
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .meta {
          font-size: 11px;
          color: var(--secondary-text-color, #9aa0a6);
        }
        .pill {
          font-size: 10px;
          padding: 2px 6px;
          border-radius: 999px;
          border: 1px solid transparent;
        }
        .pill.skipped {
          color: #ef5350;
          border-color: #ef5350;
          background: rgba(239, 83, 80, 0.1);
        }
        .actions {
          margin-top: 10px;
          display: flex;
          gap: 8px;
          justify-content: flex-end;
        }
        button {
          border: 0;
          border-radius: 8px;
          padding: 8px 12px;
          font-size: 12px;
          font-weight: 600;
          cursor: pointer;
        }
        button.primary {
          background: var(--primary-color, #03a9f4);
          color: #fff;
        }
        button.secondary {
          background: rgba(127, 127, 127, 0.2);
          color: var(--primary-text-color, #fff);
        }
        button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .message {
          margin-top: 8px;
          padding: 8px;
          border-radius: 8px;
          font-size: 12px;
        }
        .message.ok {
          color: #43a047;
          background: rgba(67, 160, 71, 0.12);
        }
        .message.error {
          color: #e53935;
          background: rgba(229, 57, 53, 0.12);
        }
        .empty {
          color: var(--secondary-text-color, #9aa0a6);
          font-size: 12px;
          padding: 8px;
          background: rgba(127, 127, 127, 0.08);
          border-radius: 8px;
        }
      </style>
      <div class='card'>
        <div class='header'>${this._config.title}</div>
        <div class='sub'>Select one or more objects to skip. Already skipped objects are locked.</div>
        <div class='list'>${rows}</div>
        <div class='actions'>
          <button class='secondary' id='close-btn'>Close</button>
          <button class='primary' id='skip-btn' ${canSubmit ? "" : "disabled"}>${
            this._submitting ? "Sending..." : "Skip Selected"
          }</button>
        </div>
        ${message}
      </div>
    `;

      this.shadowRoot.querySelectorAll("input[type='checkbox'][data-id]").forEach((el) => {
        el.addEventListener("change", (ev) => {
          const id = Number(ev.target.getAttribute("data-id"));
          if (!Number.isInteger(id)) {
            return;
          }
          if (ev.target.checked) {
            this._selected.add(id);
          } else {
            this._selected.delete(id);
          }
          this._setMessage("");
          this._render();
        });
      });

      const skipBtn = this.shadowRoot.getElementById("skip-btn");
      if (skipBtn) {
        skipBtn.addEventListener("click", () => this._submitSkip());
      }

      const closeBtn = this.shadowRoot.getElementById("close-btn");
      if (closeBtn) {
        closeBtn.addEventListener("click", () => this._closePopup());
      }
    } catch (err) {
      if (this.shadowRoot) {
        this.shadowRoot.innerHTML = `<ha-card style="padding:12px;color:#b91c1c;">Skip Objects card error: ${String(err)}</ha-card>`;
      }
    }
  }
}

if (!customElements.get("skip-objects-direct-card")) {
  customElements.define("skip-objects-direct-card", SkipObjectsDirectCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "skip-objects-direct-card",
  name: "Skip Objects Direct Card",
  description: "Direct one-click popup picker for Bambu Lab skip objects",
});
