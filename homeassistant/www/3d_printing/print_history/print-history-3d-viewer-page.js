const CDN_MODULE_URL = "https://cdn.jsdelivr.net/npm/gcode-preview@2.18.0/+esm";

const CROP_PRESETS = {
  free: null,
  square: 1,
  landscape4x3: 4 / 3,
  landscape16x9: 16 / 9,
};

const appState = {
  params: null,
  rendererMode: "gcode",
  capture: null,
  uploadInProgress: false,
  cropMode: false,
  cropAspectPreset: "square",
  cropRect: null,
  cropDrag: null,
};

function getParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    archiveId: String(params.get("archive_id") || "").trim(),
    archiveName: String(params.get("archive_name") || "").trim(),
    entryId: String(params.get("entry_id") || "").trim(),
    bambuddyBase: String(params.get("bambuddy_base") || "").trim().replace(/\/$/, ""),
    captureMode: String(params.get("capture_mode") || "").trim().toLowerCase(),
  };
}

function buildProxyUrl(path, entryId) {
  const suffix = entryId ? `?entry_id=${encodeURIComponent(entryId)}` : "";
  return `${path}${suffix}`;
}

function getCropAspectRatio() {
  return Object.prototype.hasOwnProperty.call(CROP_PRESETS, appState.cropAspectPreset)
    ? CROP_PRESETS[appState.cropAspectPreset]
    : CROP_PRESETS.square;
}

function getStageElement() {
  const stage = document.getElementById("viewer-stage");
  return stage instanceof HTMLElement ? stage : null;
}

function getStageMetrics() {
  const stage = getStageElement();
  if (!stage) {
    return null;
  }
  const rect = stage.getBoundingClientRect();
  const width = Math.max(1, stage.clientWidth || Math.round(rect.width) || 1);
  const height = Math.max(1, stage.clientHeight || Math.round(rect.height) || 1);
  return { width, height, rect };
}

function setButtonDisabled(id, disabled) {
  const button = document.getElementById(id);
  if (!button) {
    return;
  }
  button.disabled = !!disabled;
  if (disabled) {
    button.setAttribute("aria-disabled", "true");
  } else {
    button.removeAttribute("aria-disabled");
  }
}

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function normalizeHex(value) {
  const raw = String(value || "").trim().replace(/^#/, "").replace(/"/g, "");
  if (!raw) {
    return "";
  }
  const trimmed = raw.length === 8 ? raw.slice(0, 6) : raw;
  return /^[0-9a-fA-F]{6}$/.test(trimmed) ? `#${trimmed.toUpperCase()}` : "";
}

function normalizeColors(colors) {
  if (!Array.isArray(colors)) {
    return [];
  }
  return colors.map(normalizeHex).filter(Boolean);
}

function extractFilamentColorsFromGcode(gcodeText) {
  const match = String(gcodeText || "").match(/^\s*;\s*filament_colour\s*=\s*(.+)$/im);
  if (!match || !match[1]) {
    return [];
  }
  return normalizeColors(match[1].split(";"));
}

function resolvePreviewColors(capabilities, gcodeText) {
  const gcodeColors = extractFilamentColorsFromGcode(gcodeText);
  if (gcodeColors.length) {
    return gcodeColors;
  }
  return normalizeColors(capabilities.filament_colors);
}

function normalizePreviewGcode(gcodeText, maxToolIndex) {
  const source = String(gcodeText || "");
  if (!source) {
    return source;
  }

  const maxKnownTool = Number.isInteger(maxToolIndex) && maxToolIndex >= 0 ? maxToolIndex : null;
  const lines = source.split("\n");
  const toolPattern = /^T(\d+)\s*$/;
  let currentTool = null;
  let sawAnyTool = false;

  const normalizedLines = lines.map((line) => {
    const match = line.match(toolPattern);
    if (!match) {
      return line;
    }

    sawAnyTool = true;
    const tool = Number(match[1]);
    if (!Number.isFinite(tool)) {
      return line;
    }

    let normalizedTool = tool;
    if (maxKnownTool != null) {
      if (tool >= 0 && tool <= maxKnownTool) {
        normalizedTool = tool;
      } else if (tool === 1000) {
        normalizedTool = 0;
      } else if (tool === 255 && currentTool != null) {
        normalizedTool = currentTool;
      } else if (currentTool != null) {
        normalizedTool = currentTool;
      } else {
        normalizedTool = 0;
      }
    }

    currentTool = normalizedTool;
    return `T${normalizedTool}`;
  });

  if (!sawAnyTool && maxKnownTool != null) {
    normalizedLines.unshift("T0");
  }

  return normalizedLines.join("\n");
}

function normalizeBuildVolume(buildVolume) {
  if (!buildVolume || typeof buildVolume !== "object") {
    return { x: 256, y: 256, z: 256 };
  }
  const x = Number(buildVolume.x || 256);
  const y = Number(buildVolume.y || 256);
  const z = Number(buildVolume.z || 256);
  return {
    x: Number.isFinite(x) && x > 0 ? x : 256,
    y: Number.isFinite(y) && y > 0 ? y : 256,
    z: Number.isFinite(z) && z > 0 ? z : 256,
  };
}

async function fetchJson(url) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: buildAuthHeaders(),
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch (_error) {
    payload = null;
  }
  if (!response.ok) {
    const message = payload && payload.message ? payload.message : `Request failed with HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload || {};
}

async function fetchText(url) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: buildAuthHeaders(),
  });
  const text = await response.text();
  if (!response.ok) {
    let message = `Request failed with HTTP ${response.status}`;
    try {
      const payload = JSON.parse(text || "{}");
      if (payload && payload.message) {
        message = payload.message;
      }
    } catch (_error) {
      message = text || message;
    }
    throw new Error(message);
  }
  return text;
}

async function fetchJsonWithBody(url, options) {
  const mergedHeaders = Object.assign({}, buildAuthHeaders(), options && options.headers ? options.headers : {});
  const response = await fetch(url, Object.assign({}, options || {}, { headers: mergedHeaders }));
  let payload = null;
  try {
    payload = await response.json();
  } catch (_error) {
    payload = null;
  }
  if (!response.ok) {
    const message = payload && payload.message ? payload.message : `Request failed with HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload || {};
}

function setStatus(message, isError = false) {
  const status = document.getElementById("viewer-status");
  if (!status) {
    return;
  }
  status.textContent = message;
  status.className = isError ? "panel status error" : "panel status";
}

function setTitle(title, subtitle) {
  const titleNode = document.getElementById("viewer-title");
  const subtitleNode = document.getElementById("viewer-subtitle");
  if (titleNode) {
    titleNode.textContent = title;
  }
  if (subtitleNode) {
    subtitleNode.textContent = subtitle;
  }
  document.title = title;
}

function renderCapabilityChips(capabilities, colors) {
  const chips = document.getElementById("capability-chips");
  if (!chips) {
    return;
  }
  const buildVolume = normalizeBuildVolume(capabilities.build_volume);
  const chipMarkup = [
    `<span class="chip${capabilities.has_gcode ? "" : " warn"}">G-code ${capabilities.has_gcode ? "Available" : "Unavailable"}</span>`,
    `<span class="chip${capabilities.has_model ? "" : " warn"}">3D Model ${capabilities.has_model ? "Available" : "Unavailable"}</span>`,
    `<span class="chip">Build ${buildVolume.x} x ${buildVolume.y} x ${buildVolume.z}</span>`,
  ];
  if (capabilities.has_source) {
    chipMarkup.push('<span class="chip">Source 3MF Attached</span>');
  }
  if (colors.length) {
    chipMarkup.push(`<span class="chip">${colors.length} Filament Color${colors.length === 1 ? "" : "s"}</span>`);
  }
  chips.innerHTML = chipMarkup.join("");
}

function renderOverlay(colors) {
  const overlay = document.getElementById("viewer-overlay");
  if (!overlay) {
    return;
  }
  const items = [];
  for (let index = 0; index < colors.length; index += 1) {
    const color = colors[index];
    items.push(
      `<span class="chip" title="Tool T${index}"><span style="display:inline-block;width:12px;height:12px;border-radius:999px;background:${escapeHtml(color)};box-shadow:inset 0 0 0 1px rgba(255,255,255,0.28);"></span>T${index}</span>`
    );
  }
  overlay.innerHTML = items.join("");
}

function setArchiveLinks(params, gcodeUrl) {
  const downloadLink = document.getElementById("download-link");
  const archivesLink = document.getElementById("archives-link");

  if (downloadLink) {
    downloadLink.href = gcodeUrl;
    downloadLink.download = `${params.archiveName || `archive-${params.archiveId}`}.gcode`;
  }

  if (archivesLink) {
    if (params.bambuddyBase) {
      const search = params.archiveName ? `?search=${encodeURIComponent(params.archiveName)}` : "";
      archivesLink.href = `${params.bambuddyBase}/archives${search}`;
      archivesLink.removeAttribute("aria-disabled");
    } else {
      archivesLink.href = "#";
      archivesLink.setAttribute("aria-disabled", "true");
    }
  }
}

function showFallback(message, gcodeText) {
  const panel = document.getElementById("fallback-panel");
  const copy = document.getElementById("fallback-copy");
  const snippet = document.getElementById("fallback-snippet");
  if (!panel || !copy || !snippet) {
    return;
  }
  panel.classList.add("visible");
  copy.textContent = message;
  snippet.textContent = String(gcodeText || "").split("\n").slice(0, 80).join("\n");
}

function setCaptureStatus(message, tone) {
  const node = document.getElementById("capture-status");
  if (!node) {
    return;
  }
  node.textContent = String(message || "").trim();
  node.className = tone === "error"
    ? "capture-status error"
    : tone === "success"
      ? "capture-status success"
      : "capture-status";
}

function cropPresetLabel() {
  switch (appState.cropAspectPreset) {
    case "free":
      return "Freeform crop";
    case "landscape4x3":
      return "Landscape 4:3 crop";
    case "landscape16x9":
      return "Landscape 16:9 crop";
    default:
      return "Square crop";
  }
}

function updateCapturePanel() {
  const panel = document.getElementById("capture-panel");
  const image = document.getElementById("capture-preview-image");
  const empty = document.getElementById("capture-empty");
  const title = document.getElementById("capture-title");
  const copy = document.getElementById("capture-copy");
  const controls = document.getElementById("capture-controls");
  const note = document.getElementById("capture-note");
  const captureButton = document.getElementById("capture-button");
  const cropToggleButton = document.getElementById("crop-toggle-button");
  if (!panel || !image || !empty || !title || !copy) {
    return;
  }

  panel.classList.add("visible");
  if (appState.capture && appState.capture.objectUrl) {
    image.src = appState.capture.objectUrl;
    image.hidden = false;
    empty.hidden = true;
    title.textContent = `${appState.capture.width} x ${appState.capture.height} PNG ready`;
    copy.textContent = `Archive #${appState.params && appState.params.archiveId ? appState.params.archiveId : ""} ${appState.capture.cropLabel || "viewer capture"} prepared from the current render surface.`;
  } else {
    image.removeAttribute("src");
    image.hidden = true;
    empty.hidden = false;
    title.textContent = "No render captured yet";
    copy.textContent = appState.cropMode
      ? `Adjust the ${cropPresetLabel().toLowerCase()} and then capture it. Square is the thumbnail-like default, while landscape presets are better for wide card framing.`
      : "Use the current canvas as a better archive image when the parser thumbnail is not representative, especially for multi-color prints.";
  }

  if (controls) {
    controls.classList.toggle("visible", appState.cropMode);
  }
  if (note) {
    note.textContent = appState.cropMode
      ? "Square stays closest to the stock 200x200-like thumbnail behavior. Landscape presets usually frame better for the list card and camera-style previews."
      : "Square is the best starting point when you want a thumbnail-like replacement. Landscape presets usually frame better for the list card and camera-style previews.";
  }
  if (captureButton) {
    captureButton.textContent = "Capture View";
  }
  if (cropToggleButton) {
    cropToggleButton.textContent = appState.cropMode ? "Capture Crop" : "Crop Capture";
  }

  setButtonDisabled("download-capture-button", !appState.capture);
  setButtonDisabled("upload-capture-button", !appState.capture || appState.uploadInProgress);
}

function revokeCapture() {
  if (appState.capture && appState.capture.objectUrl) {
    URL.revokeObjectURL(appState.capture.objectUrl);
  }
  appState.capture = null;
}

function getViewerCanvas() {
  const canvas = document.getElementById("viewer-canvas");
  return canvas instanceof HTMLCanvasElement ? canvas : null;
}

function buildDefaultCropRect(width, height) {
  const safeWidth = Math.max(1, Number(width) || 1);
  const safeHeight = Math.max(1, Number(height) || 1);
  const maxWidth = safeWidth * 0.78;
  const maxHeight = safeHeight * 0.78;
  const ratio = getCropAspectRatio();
  let cropWidth = maxWidth;
  let cropHeight = maxHeight;

  if (ratio) {
    cropHeight = cropWidth / ratio;
    if (cropHeight > maxHeight) {
      cropHeight = maxHeight;
      cropWidth = cropHeight * ratio;
    }
  }

  return {
    x: Math.round((safeWidth - cropWidth) / 2),
    y: Math.round((safeHeight - cropHeight) / 2),
    width: Math.round(cropWidth),
    height: Math.round(cropHeight),
  };
}

function clampCropRect(rect, stageWidth, stageHeight) {
  const minSize = 48;
  const safeWidth = Math.max(1, Number(stageWidth) || 1);
  const safeHeight = Math.max(1, Number(stageHeight) || 1);
  const ratio = getCropAspectRatio();
  let width = Math.max(minSize, Math.min(Number(rect.width) || minSize, safeWidth));
  let height = Math.max(minSize, Math.min(Number(rect.height) || minSize, safeHeight));

  if (ratio) {
    height = width / ratio;
    if (height > safeHeight) {
      height = safeHeight;
      width = height * ratio;
    }
    if (height < minSize) {
      height = minSize;
      width = height * ratio;
    }
    if (width < minSize) {
      width = minSize;
      height = width / ratio;
    }
    if (width > safeWidth) {
      width = safeWidth;
      height = width / ratio;
    }
  }

  let x = Number(rect.x) || 0;
  let y = Number(rect.y) || 0;
  x = Math.min(Math.max(0, x), Math.max(0, safeWidth - width));
  y = Math.min(Math.max(0, y), Math.max(0, safeHeight - height));
  return {
    x: Math.round(x),
    y: Math.round(y),
    width: Math.round(width),
    height: Math.round(height),
  };
}

function ensureCropRect(reset) {
  const metrics = getStageMetrics();
  if (!metrics) {
    return null;
  }
  if (!appState.cropRect || reset) {
    appState.cropRect = clampCropRect(buildDefaultCropRect(metrics.width, metrics.height), metrics.width, metrics.height);
    return appState.cropRect;
  }
  appState.cropRect = clampCropRect(appState.cropRect, metrics.width, metrics.height);
  return appState.cropRect;
}

function updateCropOverlay() {
  const layer = document.getElementById("crop-layer");
  const box = document.getElementById("crop-box");
  const maskTop = document.getElementById("crop-mask-top");
  const maskLeft = document.getElementById("crop-mask-left");
  const maskRight = document.getElementById("crop-mask-right");
  const maskBottom = document.getElementById("crop-mask-bottom");
  const select = document.getElementById("crop-aspect-select");
  if (!layer || !box || !maskTop || !maskLeft || !maskRight || !maskBottom) {
    return;
  }

  layer.classList.toggle("active", appState.cropMode);
  layer.setAttribute("aria-hidden", appState.cropMode ? "false" : "true");
  if (select) {
    select.value = appState.cropAspectPreset;
  }

  if (!appState.cropMode) {
    return;
  }
  const metrics = getStageMetrics();
  const rect = ensureCropRect(false);
  if (!metrics || !rect) {
    return;
  }

  box.style.left = `${rect.x}px`;
  box.style.top = `${rect.y}px`;
  box.style.width = `${rect.width}px`;
  box.style.height = `${rect.height}px`;

  maskTop.style.left = "0px";
  maskTop.style.top = "0px";
  maskTop.style.width = `${metrics.width}px`;
  maskTop.style.height = `${rect.y}px`;

  maskLeft.style.left = "0px";
  maskLeft.style.top = `${rect.y}px`;
  maskLeft.style.width = `${rect.x}px`;
  maskLeft.style.height = `${rect.height}px`;

  maskRight.style.left = `${rect.x + rect.width}px`;
  maskRight.style.top = `${rect.y}px`;
  maskRight.style.width = `${Math.max(0, metrics.width - rect.x - rect.width)}px`;
  maskRight.style.height = `${rect.height}px`;

  maskBottom.style.left = "0px";
  maskBottom.style.top = `${rect.y + rect.height}px`;
  maskBottom.style.width = `${metrics.width}px`;
  maskBottom.style.height = `${Math.max(0, metrics.height - rect.y - rect.height)}px`;
}

function setCropMode(enabled) {
  appState.cropMode = !!enabled;
  appState.cropDrag = null;
  if (appState.cropMode) {
    ensureCropRect(!appState.cropRect);
    setCaptureStatus("Crop mode is active. Square is the thumbnail-like default; switch to a landscape preset if you want wider framing.", "info");
  }
  updateCropOverlay();
  updateCapturePanel();
}

function resetCropRect() {
  if (!appState.cropMode) {
    return;
  }
  ensureCropRect(true);
  updateCropOverlay();
  setCaptureStatus(`Reset to ${cropPresetLabel().toLowerCase()}.`, "info");
}

function buildCornerRect(anchorX, anchorY, pointerX, pointerY, handle, stageWidth, stageHeight) {
  const minSize = 48;
  const ratio = getCropAspectRatio();
  let width = Math.max(minSize, Math.abs(pointerX - anchorX));
  let height = Math.max(minSize, Math.abs(pointerY - anchorY));

  if (ratio) {
    if (width / height > ratio) {
      height = width / ratio;
    } else {
      width = height * ratio;
    }
  }

  const x = handle.indexOf("w") >= 0 ? anchorX - width : anchorX;
  const y = handle.indexOf("n") >= 0 ? anchorY - height : anchorY;
  return clampCropRect({ x, y, width, height }, stageWidth, stageHeight);
}

function pointerPosition(event) {
  const stage = getStageElement();
  if (!stage) {
    return null;
  }
  const rect = stage.getBoundingClientRect();
  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  };
}

function handleCropPointerDown(event) {
  if (!appState.cropMode) {
    return;
  }
  const metrics = getStageMetrics();
  const rect = ensureCropRect(false);
  if (!metrics || !rect) {
    return;
  }
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  const position = pointerPosition(event);
  if (!position) {
    return;
  }

  const handle = target.dataset && target.dataset.handle ? String(target.dataset.handle) : "";
  if (handle) {
    let anchorX = rect.x;
    let anchorY = rect.y;
    if (handle === "nw") {
      anchorX = rect.x + rect.width;
      anchorY = rect.y + rect.height;
    } else if (handle === "ne") {
      anchorX = rect.x;
      anchorY = rect.y + rect.height;
    } else if (handle === "sw") {
      anchorX = rect.x + rect.width;
      anchorY = rect.y;
    } else if (handle === "se") {
      anchorX = rect.x;
      anchorY = rect.y;
    }
    appState.cropDrag = {
      type: "resize",
      handle,
      anchorX,
      anchorY,
      stageWidth: metrics.width,
      stageHeight: metrics.height,
    };
  } else if (target.id === "crop-box" || target.closest("#crop-box")) {
    appState.cropDrag = {
      type: "move",
      startX: position.x,
      startY: position.y,
      originX: rect.x,
      originY: rect.y,
      width: rect.width,
      height: rect.height,
      stageWidth: metrics.width,
      stageHeight: metrics.height,
    };
  }

  if (appState.cropDrag) {
    event.preventDefault();
  }
}

function handleWindowPointerMove(event) {
  if (!appState.cropDrag || !appState.cropMode) {
    return;
  }
  const position = pointerPosition(event);
  if (!position) {
    return;
  }

  if (appState.cropDrag.type === "move") {
    const nextX = appState.cropDrag.originX + (position.x - appState.cropDrag.startX);
    const nextY = appState.cropDrag.originY + (position.y - appState.cropDrag.startY);
    appState.cropRect = clampCropRect(
      {
        x: nextX,
        y: nextY,
        width: appState.cropDrag.width,
        height: appState.cropDrag.height,
      },
      appState.cropDrag.stageWidth,
      appState.cropDrag.stageHeight
    );
  } else if (appState.cropDrag.type === "resize") {
    appState.cropRect = buildCornerRect(
      appState.cropDrag.anchorX,
      appState.cropDrag.anchorY,
      position.x,
      position.y,
      appState.cropDrag.handle,
      appState.cropDrag.stageWidth,
      appState.cropDrag.stageHeight
    );
  }

  updateCropOverlay();
}

function handleWindowPointerUp() {
  if (!appState.cropDrag) {
    return;
  }
  appState.cropDrag = null;
}

function applyCropPreset(value) {
  appState.cropAspectPreset = Object.prototype.hasOwnProperty.call(CROP_PRESETS, value) ? value : "square";
  if (appState.cropMode) {
    ensureCropRect(true);
    updateCropOverlay();
  }
  updateCapturePanel();
}

function scaledDimensions(width, height, maxDimension) {
  const safeWidth = Math.max(1, Number(width) || 1);
  const safeHeight = Math.max(1, Number(height) || 1);
  const scale = Math.min(1, maxDimension / Math.max(safeWidth, safeHeight));
  return {
    width: Math.max(1, Math.round(safeWidth * scale)),
    height: Math.max(1, Math.round(safeHeight * scale)),
  };
}

function canvasToBlob(canvas, mimeType, quality) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error("Canvas export returned no data"));
        return;
      }
      resolve(blob);
    }, mimeType, quality);
  });
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Could not encode capture for upload"));
    reader.onload = () => {
      const result = String(reader.result || "");
      const parts = result.split(",", 2);
      resolve(parts.length === 2 ? parts[1] : result);
    };
    reader.readAsDataURL(blob);
  });
}

function buildCaptureFileName(isCropped) {
  const params = appState.params || {};
  const archiveId = String(params.archiveId || "archive").trim();
  const rendererMode = String(appState.rendererMode || "viewer").trim().toLowerCase();
  const now = new Date();
  const timestamp = now.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  return `viewer-capture-${archiveId}-${rendererMode}${isCropped ? "-crop" : ""}-${timestamp}.png`;
}

async function captureCurrentView() {
  const sourceCanvas = getViewerCanvas();
  if (!sourceCanvas) {
    throw new Error("Viewer canvas is not available.");
  }
  const sourceWidth = sourceCanvas.width || sourceCanvas.clientWidth || 0;
  const sourceHeight = sourceCanvas.height || sourceCanvas.clientHeight || 0;
  if (sourceWidth <= 0 || sourceHeight <= 0) {
    throw new Error("The viewer has not rendered a captureable frame yet.");
  }

  const metrics = getStageMetrics();
  const cropRect = appState.cropMode ? ensureCropRect(false) : null;
  const sourceX = cropRect && metrics ? Math.max(0, Math.round((cropRect.x / metrics.width) * sourceWidth)) : 0;
  const sourceY = cropRect && metrics ? Math.max(0, Math.round((cropRect.y / metrics.height) * sourceHeight)) : 0;
  const sourceCropWidth = cropRect && metrics ? Math.max(1, Math.round((cropRect.width / metrics.width) * sourceWidth)) : sourceWidth;
  const sourceCropHeight = cropRect && metrics ? Math.max(1, Math.round((cropRect.height / metrics.height) * sourceHeight)) : sourceHeight;
  const dimensions = scaledDimensions(sourceCropWidth, sourceCropHeight, 2048);
  const exportCanvas = document.createElement("canvas");
  exportCanvas.width = dimensions.width;
  exportCanvas.height = dimensions.height;
  const context = exportCanvas.getContext("2d");
  if (!context) {
    throw new Error("Canvas rendering is unavailable for capture.");
  }
  context.drawImage(
    sourceCanvas,
    sourceX,
    sourceY,
    sourceCropWidth,
    sourceCropHeight,
    0,
    0,
    dimensions.width,
    dimensions.height
  );
  const blob = await canvasToBlob(exportCanvas, "image/png");
  const cropLabel = cropRect ? cropPresetLabel() : "Full-frame capture";

  revokeCapture();
  appState.capture = {
    blob,
    objectUrl: URL.createObjectURL(blob),
    width: dimensions.width,
    height: dimensions.height,
    mimeType: "image/png",
    fileName: buildCaptureFileName(!!cropRect),
    cropLabel,
  };
  updateCapturePanel();
  setCaptureStatus(`Captured ${cropLabel.toLowerCase()}. Download it or upload it to the archive.`, "success");
}

function downloadCapture() {
  if (!appState.capture || !appState.capture.objectUrl) {
    return;
  }
  const anchor = document.createElement("a");
  anchor.href = appState.capture.objectUrl;
  anchor.download = appState.capture.fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function resolveAccessToken() {
  try {
    const rawTokens = localStorage.getItem("hassTokens");
    if (rawTokens) {
      const parsedTokens = JSON.parse(rawTokens);
      const accessToken = parsedTokens && parsedTokens.access_token
        ? String(parsedTokens.access_token).trim()
        : "";
      if (accessToken) {
        return accessToken;
      }
    }
  } catch (_error) {
    // Ignore malformed localStorage token payloads and try other contexts.
  }

  const candidates = [window, window.parent, window.top];
  const visited = [];
  for (let index = 0; index < candidates.length; index += 1) {
    const candidate = candidates[index];
    if (!candidate || visited.indexOf(candidate) !== -1) {
      continue;
    }
    visited.push(candidate);
    try {
      const root = candidate.document && typeof candidate.document.querySelector === "function"
        ? candidate.document.querySelector("home-assistant")
        : null;
      const accessToken = root && root.hass && root.hass.auth && root.hass.auth.data
        ? String(root.hass.auth.data.accessToken || "").trim()
        : "";
      if (accessToken) {
        return accessToken;
      }
    } catch (_error) {
      // Ignore cross-window access failures and keep searching.
    }
  }
  return "";
}

function buildAuthHeaders() {
  const accessToken = resolveAccessToken();
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
}

async function uploadCapture() {
  if (!appState.capture || !appState.params || !appState.params.archiveId) {
    return;
  }
  appState.uploadInProgress = true;
  updateCapturePanel();
  setCaptureStatus("Uploading capture to the archive...", "info");

  try {
    const endpoint = buildProxyUrl(
      `/api/bambuddy/print-history/archive-viewer/${encodeURIComponent(appState.params.archiveId)}/capture-upload`,
      appState.params.entryId
    );
    const response = await fetchJsonWithBody(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        file_name: appState.capture.fileName,
        mime_type: appState.capture.mimeType,
        content_base64: await blobToBase64(appState.capture.blob),
      }),
    });
    const uploadedPhotoPath = String(response.uploaded_photo_path || appState.capture.fileName || "").trim();
    if (uploadedPhotoPath) {
      appState.capture.fileName = uploadedPhotoPath;
    }
    setCaptureStatus("Capture uploaded to the archive photo gallery.", "success");
  } catch (error) {
    setCaptureStatus(error && error.message ? error.message : "Capture upload failed.", "error");
  } finally {
    appState.uploadInProgress = false;
    updateCapturePanel();
  }
}

async function renderPreview(params) {
  if (!params.archiveId) {
    setTitle("Archive viewer unavailable", "No archive ID was provided to the popup.");
    setStatus("Archive viewer could not start because archive_id is missing.", true);
    showFallback("Launch this popup from a print-history archive card or popup action.", "");
    return;
  }

  const archiveTitle = params.archiveName || `Archive ${params.archiveId}`;
  setTitle(archiveTitle, `Archive #${params.archiveId}`);

  const capabilitiesUrl = buildProxyUrl(`/api/bambuddy/print-history/archive-viewer/${encodeURIComponent(params.archiveId)}/capabilities`, params.entryId);
  const gcodeUrl = buildProxyUrl(`/api/bambuddy/print-history/archive-viewer/${encodeURIComponent(params.archiveId)}/gcode`, params.entryId);
  setArchiveLinks(params, gcodeUrl);

  setStatus("Checking Bambuddy archive capabilities...");
  const capabilities = await fetchJson(capabilitiesUrl);

  if (!capabilities.has_gcode) {
    setStatus("This archive does not expose extracted G-code, so the preview cannot be rendered here.", true);
    showFallback(
      capabilities.has_model
        ? "The archive still has a 3D model, but Bambuddy does not expose a deep-linkable modal route that Home Assistant can reuse directly."
        : "This archive has neither extracted G-code nor a usable model preview path for this popup.",
      ""
    );
    return;
  }

  setStatus("Downloading G-code from Bambuddy...");
  const gcodeText = await fetchText(gcodeUrl);
  if (!String(gcodeText || "").trim()) {
    setStatus("Bambuddy returned an empty G-code payload for this archive.", true);
    showFallback("The archive G-code payload was empty.", "");
    return;
  }

  const canvas = document.getElementById("viewer-canvas");
  if (!(canvas instanceof HTMLCanvasElement)) {
    throw new Error("Viewer canvas is not available.");
  }

  const colors = resolvePreviewColors(capabilities, gcodeText);
  const previewGcode = normalizePreviewGcode(gcodeText, colors.length ? colors.length - 1 : null);
  renderCapabilityChips(capabilities, colors);
  renderOverlay(colors);

  setStatus("Rendering G-code preview...");
  try {
    const GCodePreview = await import(CDN_MODULE_URL);
    const preview = GCodePreview.init({
      canvas,
      buildVolume: normalizeBuildVolume(capabilities.build_volume),
      extrusionColor: colors.length ? colors : ["#7DD3C8", "#F59E0B", "#38BDF8", "#F97316"],
      disableGradient: true,
      backgroundColor: "#08101a",
      gridColor: "rgba(125, 211, 200, 0.18)",
      allowDragNDrop: false,
    });
    preview.processGCode(previewGcode);
    appState.rendererMode = "gcode";
    setStatus("Rendered Bambuddy G-code preview. Use drag, pan, and zoom inside the canvas.");
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    setStatus("The interactive preview library could not be loaded, so the popup fell back to raw G-code.", true);
    showFallback(`Interactive preview failed to load: ${message}`, gcodeText);
  }
}

async function bootstrap() {
  const params = getParams();
  appState.params = params;
  if (params.captureMode === "crop") {
    appState.cropMode = true;
  }
  updateCapturePanel();
  updateCropOverlay();
  const refreshButton = document.getElementById("refresh-button");
  const captureButton = document.getElementById("capture-button");
  const cropToggleButton = document.getElementById("crop-toggle-button");
  const cropAspectSelect = document.getElementById("crop-aspect-select");
  const resetCropButton = document.getElementById("reset-crop-button");
  const cancelCropButton = document.getElementById("cancel-crop-button");
  const cropLayer = document.getElementById("crop-layer");
  const downloadCaptureButton = document.getElementById("download-capture-button");
  const uploadCaptureButton = document.getElementById("upload-capture-button");
  if (refreshButton) {
    refreshButton.addEventListener("click", () => window.location.reload());
  }
  if (captureButton) {
    captureButton.addEventListener("click", async () => {
      try {
        if (appState.cropMode) {
          setCropMode(false);
        }
        await captureCurrentView();
      } catch (error) {
        setCaptureStatus(error && error.message ? error.message : "Capture failed.", "error");
      }
    });
  }
  if (cropToggleButton) {
    cropToggleButton.addEventListener("click", async () => {
      try {
        if (!appState.cropMode) {
          setCropMode(true);
          return;
        }
        await captureCurrentView();
      } catch (error) {
        setCaptureStatus(error && error.message ? error.message : "Crop capture failed.", "error");
      }
    });
  }
  if (cropAspectSelect) {
    cropAspectSelect.addEventListener("change", (event) => {
      const target = event.target;
      applyCropPreset(target && target.value ? String(target.value) : "square");
    });
  }
  if (resetCropButton) {
    resetCropButton.addEventListener("click", () => resetCropRect());
  }
  if (cancelCropButton) {
    cancelCropButton.addEventListener("click", () => setCropMode(false));
  }
  if (cropLayer) {
    cropLayer.addEventListener("pointerdown", handleCropPointerDown);
  }
  window.addEventListener("pointermove", handleWindowPointerMove);
  window.addEventListener("pointerup", handleWindowPointerUp);
  window.addEventListener("resize", () => {
    if (!appState.cropMode) {
      return;
    }
    ensureCropRect(false);
    updateCropOverlay();
  });
  if (downloadCaptureButton) {
    downloadCaptureButton.addEventListener("click", () => downloadCapture());
  }
  if (uploadCaptureButton) {
    uploadCaptureButton.addEventListener("click", async () => uploadCapture());
  }

  try {
    await renderPreview(params);
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    setStatus(message, true);
    showFallback(message, "");
  }
}

bootstrap();