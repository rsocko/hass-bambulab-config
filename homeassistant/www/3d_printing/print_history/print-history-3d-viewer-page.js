const CDN_MODULE_URL = "https://cdn.jsdelivr.net/npm/gcode-preview@2.18.0/+esm";

const appState = {
  params: null,
  rendererMode: "gcode",
  capture: null,
  uploadInProgress: false,
};

function getParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    archiveId: String(params.get("archive_id") || "").trim(),
    archiveName: String(params.get("archive_name") || "").trim(),
    entryId: String(params.get("entry_id") || "").trim(),
    bambuddyBase: String(params.get("bambuddy_base") || "").trim().replace(/\/$/, ""),
  };
}

function buildProxyUrl(path, entryId) {
  const suffix = entryId ? `?entry_id=${encodeURIComponent(entryId)}` : "";
  return `${path}${suffix}`;
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
  const response = await fetch(url, { credentials: "same-origin" });
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
  const response = await fetch(url, { credentials: "same-origin" });
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
  const response = await fetch(url, options);
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

function updateCapturePanel() {
  const panel = document.getElementById("capture-panel");
  const image = document.getElementById("capture-preview-image");
  const empty = document.getElementById("capture-empty");
  const title = document.getElementById("capture-title");
  const copy = document.getElementById("capture-copy");
  if (!panel || !image || !empty || !title || !copy) {
    return;
  }

  panel.classList.add("visible");
  if (appState.capture && appState.capture.objectUrl) {
    image.src = appState.capture.objectUrl;
    image.hidden = false;
    empty.hidden = true;
    title.textContent = `${appState.capture.width} x ${appState.capture.height} PNG ready`;
    copy.textContent = `Archive #${appState.params && appState.params.archiveId ? appState.params.archiveId : ""} viewer capture prepared from the current render surface.`;
  } else {
    image.removeAttribute("src");
    image.hidden = true;
    empty.hidden = false;
    title.textContent = "No render captured yet";
    copy.textContent = "Use the current canvas as a better archive image when the parser thumbnail is not representative, especially for multi-color prints.";
  }

  setButtonDisabled("download-capture-button", !appState.capture);
  setButtonDisabled("upload-capture-button", !appState.capture || appState.uploadInProgress);
  setButtonDisabled("upload-primary-capture-button", !appState.capture || appState.uploadInProgress);
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

function buildCaptureFileName() {
  const params = appState.params || {};
  const archiveId = String(params.archiveId || "archive").trim();
  const rendererMode = String(appState.rendererMode || "viewer").trim().toLowerCase();
  const now = new Date();
  const timestamp = now.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  return `viewer-capture-${archiveId}-${rendererMode}-${timestamp}.png`;
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

  const dimensions = scaledDimensions(sourceWidth, sourceHeight, 2048);
  const exportCanvas = document.createElement("canvas");
  exportCanvas.width = dimensions.width;
  exportCanvas.height = dimensions.height;
  const context = exportCanvas.getContext("2d");
  if (!context) {
    throw new Error("Canvas rendering is unavailable for capture.");
  }
  context.drawImage(sourceCanvas, 0, 0, dimensions.width, dimensions.height);
  const blob = await canvasToBlob(exportCanvas, "image/png");

  revokeCapture();
  appState.capture = {
    blob,
    objectUrl: URL.createObjectURL(blob),
    width: dimensions.width,
    height: dimensions.height,
    mimeType: "image/png",
    fileName: buildCaptureFileName(),
  };
  updateCapturePanel();
  setCaptureStatus("Captured the current viewer render. Download it or upload it to the archive.", "success");
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

async function uploadCapture(useAsPrimary) {
  if (!appState.capture || !appState.params || !appState.params.archiveId) {
    return;
  }
  appState.uploadInProgress = true;
  updateCapturePanel();
  setCaptureStatus(useAsPrimary ? "Uploading capture and promoting it for list view..." : "Uploading capture to the archive...", "info");

  try {
    const endpoint = buildProxyUrl(
      `/api/bambuddy/print-history/archive-viewer/${encodeURIComponent(appState.params.archiveId)}/capture-upload`,
      appState.params.entryId
    );
    const accessToken = resolveAccessToken();
    const headers = { "Content-Type": "application/json" };
    if (accessToken) {
      headers.Authorization = `Bearer ${accessToken}`;
    }
    const response = await fetchJsonWithBody(endpoint, {
      method: "POST",
      headers,
      credentials: "same-origin",
      body: JSON.stringify({
        file_name: appState.capture.fileName,
        mime_type: appState.capture.mimeType,
        content_base64: await blobToBase64(appState.capture.blob),
        use_as_primary: !!useAsPrimary,
      }),
    });
    const uploadedPhotoPath = String(response.uploaded_photo_path || appState.capture.fileName || "").trim();
    if (uploadedPhotoPath) {
      appState.capture.fileName = uploadedPhotoPath;
    }
    setCaptureStatus(
      useAsPrimary
        ? "Capture uploaded and promoted for list view rendering."
        : "Capture uploaded to the archive photo gallery.",
      "success"
    );
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
  const colors = normalizeColors(capabilities.filament_colors);
  renderCapabilityChips(capabilities, colors);
  renderOverlay(colors);

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

  setStatus("Rendering G-code preview...");
  try {
    const GCodePreview = await import(CDN_MODULE_URL);
    const preview = GCodePreview.init({
      canvas,
      buildVolume: normalizeBuildVolume(capabilities.build_volume),
      extrusionColor: colors.length ? colors : ["#7DD3C8", "#F59E0B", "#38BDF8", "#F97316"],
      backgroundColor: "#08101a",
      gridColor: "rgba(125, 211, 200, 0.18)",
      allowDragNDrop: false,
    });
    preview.processGCode(gcodeText);
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
  updateCapturePanel();
  const refreshButton = document.getElementById("refresh-button");
  const captureButton = document.getElementById("capture-button");
  const downloadCaptureButton = document.getElementById("download-capture-button");
  const uploadCaptureButton = document.getElementById("upload-capture-button");
  const uploadPrimaryCaptureButton = document.getElementById("upload-primary-capture-button");
  if (refreshButton) {
    refreshButton.addEventListener("click", () => window.location.reload());
  }
  if (captureButton) {
    captureButton.addEventListener("click", async () => {
      try {
        await captureCurrentView();
      } catch (error) {
        setCaptureStatus(error && error.message ? error.message : "Capture failed.", "error");
      }
    });
  }
  if (downloadCaptureButton) {
    downloadCaptureButton.addEventListener("click", () => downloadCapture());
  }
  if (uploadCaptureButton) {
    uploadCaptureButton.addEventListener("click", async () => uploadCapture(false));
  }
  if (uploadPrimaryCaptureButton) {
    uploadPrimaryCaptureButton.addEventListener("click", async () => uploadCapture(true));
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