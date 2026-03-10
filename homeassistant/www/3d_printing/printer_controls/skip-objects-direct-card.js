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
    this._hoveredObject = 0;
    this._visibleContext = null;
    this._hiddenContext = null;
    this._canvasEl = null;
    this._lastPickImageUrl = "";
    this._haSignature = "";
    this._boundClick = (ev) => this._handleCanvasClick(ev);
    this._boundMove = (ev) => this._handleCanvasHover(ev);
    this._boundOut = () => {
      this._hoveredObject = 0;
      this._colorizeCanvas();
    };
  }

  setConfig(config) {
    if (!config || !config.device_id || !config.printable_entity || !config.skipped_entity) {
      throw new Error("skip-objects-direct-card requires device_id, printable_entity, and skipped_entity");
    }

    this._config = {
      title: "Skip Objects",
      pick_image_entity: "image.3d_printer_pick_image",
      ...config,
    };
    this._haSignature = "";
    this._render();
  }

  set hass(hass) {
    const previous = this._hass;
    this._hass = hass;
    if (!this._config) {
      return;
    }
    if (!previous) {
      this._render();
      return;
    }

    const printable = hass?.states?.[this._config.printable_entity];
    const skipped = hass?.states?.[this._config.skipped_entity];
    const pickImage = hass?.states?.[this._config.pick_image_entity];
    const signature = [
      printable?.state || "",
      JSON.stringify(printable?.attributes?.objects || {}),
      skipped?.state || "",
      JSON.stringify(skipped?.attributes?.objects || []),
      pickImage?.state || "",
      pickImage?.attributes?.entity_picture || "",
    ].join("|");

    if (signature === this._haSignature) {
      return;
    }
    this._haSignature = signature;
    this._render();
  }

  getCardSize() {
    return 7;
  }

  _rgbaToInt(r, g, b, a) {
    return r | (g << 8) | (b << 16) | (a << 24);
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

  _getPickImageUrl() {
    const imageEntity = this._hass?.states?.[this._config.pick_image_entity];
    let picture = imageEntity?.attributes?.entity_picture;
    if (!picture) {
      return "";
    }

    if (picture.startsWith("http://") || picture.startsWith("https://")) {
      try {
        const parsed = new URL(picture);
        // Force same-origin request so canvas getImageData remains readable.
        picture = `${parsed.pathname}${parsed.search}${parsed.hash}`;
      } catch (_err) {
        return picture;
      }
    }

    return picture;
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

  _initializeCanvas() {
    const canvas = this.shadowRoot?.getElementById("canvas");
    if (!canvas) {
      return;
    }

    let needsImageReload = false;

    if (this._canvasEl !== canvas) {
      this._canvasEl = canvas;
      this._visibleContext = canvas.getContext("2d", { willReadFrequently: true });
      canvas.addEventListener("click", this._boundClick);
      canvas.addEventListener("mousemove", this._boundMove);
      canvas.addEventListener("mouseout", this._boundOut);

      const hiddenCanvas = document.createElement("canvas");
      hiddenCanvas.width = 512;
      hiddenCanvas.height = 512;
      this._hiddenContext = hiddenCanvas.getContext("2d", { willReadFrequently: true });
      needsImageReload = true;
    }

    const url = this._getPickImageUrl();
    if (!url) {
      this._setMessage("No pick image URL available.", true);
      return;
    }

    if (!needsImageReload && url === this._lastPickImageUrl) {
      this._colorizeCanvas();
      return;
    }

    this._lastPickImageUrl = url;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      if (!this._hiddenContext || !this._visibleContext) {
        return;
      }
      this._hiddenContext.clearRect(0, 0, 512, 512);
      this._hiddenContext.drawImage(img, 0, 0, 512, 512);
      this._colorizeCanvas();
    };
    img.onerror = () => {
      this._setMessage("Unable to load pick image for object map.", true);
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

    const skipped = new Set(this._getSkippedList());
    const printable = this._getPrintableMap();
    if (!Object.prototype.hasOwnProperty.call(printable, String(key)) || skipped.has(key)) {
      return;
    }

    if (this._selected.has(key)) {
      this._selected.delete(key);
    } else {
      this._selected.add(key);
    }
    this._setMessage("");
    this._render();
  }

  _colorizeCanvas() {
    if (!this._visibleContext || !this._hiddenContext) {
      return;
    }

    try {
      const printable = this._getPrintableMap();
      const skipped = new Set(this._getSkippedList());
      const width = 512;
      const height = 512;

      const readImageData = this._hiddenContext.getImageData(0, 0, width, height);
      const readData = readImageData.data;

      this._visibleContext.putImageData(readImageData, 0, 0);
      const writeImageData = this._visibleContext.getImageData(0, 0, width, height);
      const writeData = writeImageData.data;
      const view = new DataView(writeData.buffer);

      const red = this._rgbaToInt(224, 82, 82, 220);
      const green = this._rgbaToInt(72, 187, 120, 215);
      const yellow = this._rgbaToInt(245, 158, 11, 230);
      const blue = this._rgbaToInt(59, 130, 246, 255);

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
            view.setUint32(i, yellow, true);
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
    } catch (err) {
      this._setMessage(`Unable to read pick image pixels: ${err?.message || err}`, true);
    }
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
      this._selected.clear();
      this._hoveredObject = 0;
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
    } catch (_err) {
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
      const skipped = new Set(skippedList);

      const validIds = new Set(Object.keys(printable).map((k) => Number(k)));
      this._selected = new Set(
        Array.from(this._selected).filter((id) => validIds.has(id) && !skipped.has(id))
      );

      const sortedEntries = Object.entries(printable).sort((a, b) => Number(a[0]) - Number(b[0]));
      const canSubmit = this._isSelectionDirty(skippedList) && !this._submitting;

      const rows =
        sortedEntries.length === 0
          ? "<div class='empty'>No printable object data available.</div>"
          : sortedEntries
              .map(([idStr, name]) => {
                const id = Number(idStr);
                const isSkipped = skipped.has(id);
                const isSelected = this._selected.has(id);
                const checked = isSkipped || isSelected;
                const disabled = isSkipped ? "disabled" : "";
                const status = isSkipped
                  ? "<span class='pill skipped'>Skipped</span>"
                  : isSelected
                    ? "<span class='pill selected'>Selected</span>"
                    : "";
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
            margin-bottom: 6px;
          }
          .sub {
            font-size: 12px;
            color: var(--secondary-text-color, #9aa0a6);
            margin-bottom: 10px;
          }
          .plate-wrap {
            position: relative;
            border-radius: 10px;
            overflow: hidden;
            background: #0b0f14;
            border: 1px solid rgba(148, 163, 184, 0.2);
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
          .list {
            display: grid;
            gap: 6px;
            max-height: 34vh;
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
          .row.is-skipped { opacity: 0.7; }
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
          .pill.selected {
            color: #f59e0b;
            border-color: #f59e0b;
            background: rgba(245, 158, 11, 0.12);
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
          <div class='sub'>Tap the plate image or use the list. Green is skippable and red is already skipped.</div>
          <div class='plate-wrap'>
            <canvas id='canvas' width='512' height='512'></canvas>
          </div>
          <div class='legend'>
            <span><span class='dot' style='background:#48bb78;'></span>Skippable</span>
            <span><span class='dot' style='background:#e05252;'></span>Already skipped</span>
            <span><span class='dot' style='background:#f59e0b;'></span>Selected</span>
            <span><span class='dot' style='background:#3b82f6;'></span>Hover outline</span>
          </div>
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

      this._initializeCanvas();
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
