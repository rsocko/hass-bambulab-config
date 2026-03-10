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
    this._hoveredObject = 0;
    this._visibleContext = null;
    this._hiddenContext = null;
    this._lastPickImageUrl = "";
    this._boundClick = (ev) => this._handleCanvasClick(ev);
    this._boundMove = (ev) => this._handleCanvasHover(ev);
    this._boundOut = () => {
      this._hoveredObject = 0;
      this._colorizeCanvas();
    };
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
      stop_entity: "button.ntk_ryansoffice_3dprinter_stop_printing",
      pick_image_entity: "image.3d_printer_pick_image",
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
    return 9;
  }

  _rgbaToInt(r, g, b, a) {
    return r | (g << 8) | (b << 16) | (a << 24);
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

  _getPickImageUrl() {
    const imageEntity = this._hass?.states?.[this._config.pick_image_entity];
    const picture = imageEntity?.attributes?.entity_picture;
    if (!picture) {
      return "";
    }
    return picture;
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

  _initializeCanvas() {
    const canvas = this.shadowRoot?.getElementById("canvas");
    if (!canvas) {
      return;
    }

    if (!this._visibleContext) {
      this._visibleContext = canvas.getContext("2d", { willReadFrequently: true });
      canvas.addEventListener("click", this._boundClick);
      canvas.addEventListener("mousemove", this._boundMove);
      canvas.addEventListener("mouseout", this._boundOut);

      const hiddenCanvas = document.createElement("canvas");
      hiddenCanvas.width = 512;
      hiddenCanvas.height = 512;
      this._hiddenContext = hiddenCanvas.getContext("2d", { willReadFrequently: true });
    }

    const url = this._getPickImageUrl();
    if (!url || url === this._lastPickImageUrl) {
      this._colorizeCanvas();
      return;
    }

    this._lastPickImageUrl = url;
    const img = new Image();
    img.onload = () => {
      if (!this._hiddenContext || !this._visibleContext) {
        return;
      }
      this._hiddenContext.clearRect(0, 0, 512, 512);
      this._hiddenContext.drawImage(img, 0, 0, 512, 512);
      this._colorizeCanvas();
    };
    img.onerror = () => {
      this._setStatus("Unable to load pick image for object map.", true);
      this._render();
    };
    img.src = url;
  }

  _handleCanvasHover(event) {
    if (!this._hiddenContext) {
      return;
    }

    const canvas = event.target;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const pixel = this._hiddenContext.getImageData(x * scaleX, y * scaleY, 1, 1).data;
    const key = this._rgbaToInt(pixel[0], pixel[1], pixel[2], 0);

    if (key !== this._hoveredObject) {
      this._hoveredObject = key;
      this._colorizeCanvas();
    }
  }

  _handleCanvasClick(event) {
    if (!this._hiddenContext) {
      return;
    }

    const canvas = event.target;
    const canvasWidth = canvas.width;
    const canvasHeight = canvas.height;
    const canvasStyleWidth = canvas.offsetWidth;
    const canvasStyleHeight = canvas.offsetHeight;
    const scaleX = canvasStyleWidth / canvasWidth;
    const scaleY = canvasStyleHeight / canvasHeight;
    const rect = canvas.getBoundingClientRect();

    let x = event.clientX - rect.left;
    let y = event.clientY - rect.top;
    x = x / scaleX;
    y = y / scaleY;

    const imageData = this._hiddenContext.getImageData(x, y, 1, 1).data;
    const key = this._rgbaToInt(imageData[0], imageData[1], imageData[2], 0);
    if (!key) {
      return;
    }

    const skipped = new Set(this._skippedList());
    const printable = this._printableMap();
    if (!Object.prototype.hasOwnProperty.call(printable, String(key)) || skipped.has(key)) {
      return;
    }

    this._toggleId(key, !this._selected.has(key));
  }

  _colorizeCanvas() {
    if (!this._visibleContext || !this._hiddenContext) {
      return;
    }

    const printable = this._printableMap();
    const skipped = new Set(this._skippedList());
    const width = 512;
    const height = 512;

    const readImageData = this._hiddenContext.getImageData(0, 0, width, height);
    const readData = readImageData.data;

    this._visibleContext.putImageData(readImageData, 0, 0);
    const writeImageData = this._visibleContext.getImageData(0, 0, width, height);
    const writeData = writeImageData.data;
    const view = new DataView(writeData.buffer);

    const red = this._rgbaToInt(220, 38, 38, 230);
    const green = this._rgbaToInt(34, 197, 94, 215);
    const cyan = this._rgbaToInt(20, 184, 166, 220);
    const blue = this._rgbaToInt(37, 99, 235, 255);

    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const i = y * 4 * height + x * 4;
        const key = this._rgbaToInt(readData[i], readData[i + 1], readData[i + 2], 0);
        if (!key || !Object.prototype.hasOwnProperty.call(printable, String(key))) {
          continue;
        }

        if (skipped.has(key)) {
          view.setUint32(i, red, true);
        } else if (this._selected.has(key)) {
          view.setUint32(i, cyan, true);
        } else {
          view.setUint32(i, green, true);
        }

        if (key === this._hoveredObject) {
          if (x > 0) {
            const left = i - 4;
            const leftKey = this._rgbaToInt(readData[left], readData[left + 1], readData[left + 2], 0);
            if (leftKey !== key) {
              view.setUint32(i, blue, true);
            }
          }
          if (x < width - 1) {
            const right = i + 4;
            const rightKey = this._rgbaToInt(readData[right], readData[right + 1], readData[right + 2], 0);
            if (rightKey !== key) {
              view.setUint32(i, blue, true);
            }
          }
          if (y > 0) {
            const top = i - width * 4;
            const topKey = this._rgbaToInt(readData[top], readData[top + 1], readData[top + 2], 0);
            if (topKey !== key) {
              view.setUint32(i, blue, true);
            }
          }
          if (y < height - 1) {
            const bottom = i + width * 4;
            const bottomKey = this._rgbaToInt(readData[bottom], readData[bottom + 1], readData[bottom + 2], 0);
            if (bottomKey !== key) {
              view.setUint32(i, blue, true);
            }
          }
        }
      }
    }

    this._visibleContext.putImageData(writeImageData, 0, 0);
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
    try {
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
        .plate-wrap {
          position: relative;
          border-radius: 10px;
          overflow: hidden;
          background: #071019;
          border: 1px solid rgba(255,255,255,0.16);
          margin-bottom: 10px;
        }
        #canvas {
          display: block;
          width: 100%;
          height: auto;
          cursor: crosshair;
        }
        .legend {
          margin-top: 6px;
          margin-bottom: 10px;
          display: flex;
          gap: 10px;
          flex-wrap: wrap;
          font-size: 11px;
          color: var(--secondary-text-color, #9aa0a6);
        }
        .dot {
          display: inline-block;
          width: 10px;
          height: 10px;
          border-radius: 50%;
          margin-right: 4px;
          vertical-align: middle;
        }
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
          <div class="plate-wrap">
            <canvas id="canvas" width="512" height="512"></canvas>
          </div>
          <div class="legend">
            <span><span class="dot" style="background:#22c55e;"></span>Skippable</span>
            <span><span class="dot" style="background:#dc2626;"></span>Already skipped</span>
            <span><span class="dot" style="background:#14b8a6;"></span>Selected</span>
            <span><span class="dot" style="background:#2563eb;"></span>Hover outline</span>
          </div>
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

      this._initializeCanvas();
    } catch (err) {
      if (this.shadowRoot) {
        this.shadowRoot.innerHTML = `<ha-card style="padding:12px;color:#b91c1c;">Skip Objects Studio error: ${String(err)}</ha-card>`;
      }
    }
  }
}

if (!customElements.get("skip-objects-studio-card")) {
  customElements.define("skip-objects-studio-card", SkipObjectsStudioCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "skip-objects-studio-card",
  name: "Skip Objects Studio Card",
  description: "Feature-styled skip objects card for Bambu printers",
});
