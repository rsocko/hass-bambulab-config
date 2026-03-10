class SkipObjectsStudioCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._selected = new Set();
    this._busy = false;
    this._status = "";
    this._error = false;
  }

  setConfig(config) {
    if (!config || !config.device_id || !config.printable_entity || !config.skipped_entity) {
      throw new Error(
        "skip-objects-studio-card requires device_id, printable_entity, and skipped_entity"
      );
    }

    this._config = {
      title: "Object Skip Studio",
      subtitle: "Protect active prints by excluding failed parts",
      stop_entity: "button.ntk_ryansoffice_3dprinter_stop_print",
      min_objects: 2,
      max_objects: 64,
      ...config,
    };

    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 7;
  }

  _printableMap() {
    const st = this._hass?.states?.[this._config.printable_entity];
    const map = st?.attributes?.objects;
    if (!map || typeof map !== "object") {
      return {};
    }
    return map;
  }

  _skippedList() {
    const st = this._hass?.states?.[this._config.skipped_entity];
    const list = st?.attributes?.objects;
    if (!Array.isArray(list)) {
      return [];
    }
    return list.map((v) => Number(v)).filter((v) => Number.isInteger(v));
  }

  _isAvailable(printableCount) {
    const stopEntity = this._config.stop_entity;
    const stopAvailable = stopEntity
      ? this._hass?.states?.[stopEntity]?.state !== "unavailable"
      : true;

    return (
      stopAvailable &&
      printableCount >= Number(this._config.min_objects) &&
      printableCount <= Number(this._config.max_objects)
    );
  }

  _setStatus(text, isError = false) {
    this._status = text;
    this._error = isError;
  }

  _collectIds() {
    const map = this._printableMap();
    return Object.keys(map)
      .map((k) => Number(k))
      .filter((k) => Number.isInteger(k))
      .sort((a, b) => a - b);
  }

  _selectAllUnskipped() {
    const skipped = new Set(this._skippedList());
    const all = this._collectIds();
    this._selected = new Set(all.filter((id) => !skipped.has(id)));
    this._setStatus("");
    this._render();
  }

  _clearSelection() {
    this._selected.clear();
    this._setStatus("");
    this._render();
  }

  _toggleId(id, checked) {
    if (checked) {
      this._selected.add(id);
    } else {
      this._selected.delete(id);
    }
    this._setStatus("");
    this._render();
  }

  async _submit() {
    if (this._busy || !this._hass) {
      return;
    }

    const skipped = this._skippedList();
    const merged = Array.from(new Set([...skipped, ...Array.from(this._selected)])).sort(
      (a, b) => a - b
    );

    if (merged.length === 0) {
      this._setStatus("No new objects selected.", true);
      this._render();
      return;
    }

    this._busy = true;
    this._setStatus("");
    this._render();

    try {
      await this._hass.callService("bambu_lab", "skip_objects", {
        device_id: this._config.device_id,
        objects: merged.join(","),
      });
      this._setStatus("Skip request sent.");
      this._selected.clear();
    } catch (err) {
      this._setStatus(`Failed to send skip request: ${err?.message || err}`, true);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }

    const printable = this._printableMap();
    const skipped = new Set(this._skippedList());
    const ids = Object.keys(printable)
      .map((k) => Number(k))
      .filter((k) => Number.isInteger(k))
      .sort((a, b) => a - b);

    const valid = new Set(ids);
    this._selected = new Set(Array.from(this._selected).filter((id) => valid.has(id) && !skipped.has(id)));

    const available = this._isAvailable(ids.length);
    const selectedCount = this._selected.size;
    const skippedCount = skipped.size;

    const cards = ids.length
      ? ids
          .map((id) => {
            const name = String(printable[String(id)] ?? `Object ${id}`);
            const isSkipped = skipped.has(id);
            const checked = isSkipped || this._selected.has(id);
            return `
              <label class="obj ${isSkipped ? "obj-skipped" : ""}">
                <input type="checkbox" data-id="${id}" ${checked ? "checked" : ""} ${isSkipped ? "disabled" : ""}>
                <span class="obj-name" title="${name}">${name}</span>
                <span class="obj-id">#${id}</span>
                ${isSkipped ? '<span class="badge">skipped</span>' : ""}
              </label>
            `;
          })
          .join("")
      : '<div class="empty">No printable object metadata is available yet.</div>';

    const status = this._status
      ? `<div class="status ${this._error ? "status-error" : "status-ok"}">${this._status}</div>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        .wrap {
          border-radius: 14px;
          overflow: hidden;
          background: var(--card-background-color);
          border: 1px solid rgba(255,255,255,0.08);
        }
        .hero {
          padding: 14px;
          background: linear-gradient(125deg, #0f766e 0%, #155e75 48%, #1e3a8a 100%);
          color: #f8fafc;
        }
        .title { font-size: 18px; font-weight: 800; letter-spacing: 0.2px; }
        .subtitle { font-size: 12px; opacity: 0.9; margin-top: 2px; }
        .metrics {
          margin-top: 10px;
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }
        .pill {
          font-size: 11px;
          font-weight: 700;
          border-radius: 999px;
          padding: 4px 8px;
          background: rgba(255,255,255,0.18);
          color: #f8fafc;
        }
        .body { padding: 12px; }
        .toolbar { display:flex; gap:8px; flex-wrap:wrap; margin-bottom: 10px; }
        button {
          border: 0;
          border-radius: 10px;
          padding: 8px 10px;
          font-size: 12px;
          font-weight: 700;
          cursor: pointer;
        }
        .btn-muted { background: rgba(148,163,184,0.18); color: var(--primary-text-color); }
        .btn-go { background: #0f766e; color: #ecfeff; margin-left: auto; }
        .btn-go:disabled { opacity: 0.5; cursor: not-allowed; }
        .grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 8px;
        }
        @media (max-width: 680px) {
          .grid { grid-template-columns: 1fr; }
        }
        .obj {
          display: grid;
          grid-template-columns: 20px 1fr auto auto;
          gap: 8px;
          align-items: center;
          padding: 9px;
          border-radius: 10px;
          background: rgba(148,163,184,0.08);
          border: 1px solid rgba(148,163,184,0.15);
        }
        .obj-skipped { opacity: 0.72; }
        .obj-name {
          font-size: 12px;
          font-weight: 600;
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .obj-id { font-size: 11px; opacity: 0.75; }
        .badge {
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 0.4px;
          font-weight: 700;
          color: #fca5a5;
          border: 1px solid rgba(252,165,165,0.6);
          border-radius: 999px;
          padding: 2px 6px;
        }
        .empty {
          font-size: 12px;
          opacity: 0.8;
          padding: 10px;
          border-radius: 10px;
          background: rgba(148,163,184,0.08);
        }
        .status {
          margin-top: 10px;
          border-radius: 10px;
          padding: 8px 10px;
          font-size: 12px;
          font-weight: 600;
        }
        .status-ok { color: #15803d; background: rgba(21,128,61,0.14); }
        .status-error { color: #b91c1c; background: rgba(185,28,28,0.14); }
        .unavailable {
          margin-top: 10px;
          border-radius: 10px;
          padding: 10px;
          font-size: 12px;
          font-weight: 600;
          color: #b45309;
          background: rgba(245,158,11,0.14);
        }
      </style>
      <ha-card class="wrap">
        <div class="hero">
          <div class="title">${this._config.title}</div>
          <div class="subtitle">${this._config.subtitle}</div>
          <div class="metrics">
            <span class="pill">Objects ${ids.length}</span>
            <span class="pill">Skipped ${skippedCount}</span>
            <span class="pill">Selected ${selectedCount}</span>
          </div>
        </div>
        <div class="body">
          <div class="toolbar">
            <button class="btn-muted" id="select-all" ${available ? "" : "disabled"}>Select all available</button>
            <button class="btn-muted" id="clear">Clear selection</button>
            <button class="btn-go" id="submit" ${!available || selectedCount === 0 || this._busy ? "disabled" : ""}>${
              this._busy ? "Sending..." : "Skip Selected"
            }</button>
          </div>
          ${available ? "" : '<div class="unavailable">Skip Objects is currently unavailable. Start an active print with 2+ objects.</div>'}
          <div class="grid">${cards}</div>
          ${status}
        </div>
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll("input[type='checkbox'][data-id]").forEach((el) => {
      el.addEventListener("change", (ev) => {
        const id = Number(ev.target.getAttribute("data-id"));
        if (!Number.isInteger(id)) {
          return;
        }
        this._toggleId(id, ev.target.checked);
      });
    });

    const selectAll = this.shadowRoot.getElementById("select-all");
    if (selectAll) {
      selectAll.addEventListener("click", () => this._selectAllUnskipped());
    }

    const clear = this.shadowRoot.getElementById("clear");
    if (clear) {
      clear.addEventListener("click", () => this._clearSelection());
    }

    const submit = this.shadowRoot.getElementById("submit");
    if (submit) {
      submit.addEventListener("click", () => this._submit());
    }
  }
}

customElements.define("skip-objects-studio-card", SkipObjectsStudioCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "skip-objects-studio-card",
  name: "Skip Objects Studio Card",
  description: "Feature-styled skip objects card for Bambu printers",
});
