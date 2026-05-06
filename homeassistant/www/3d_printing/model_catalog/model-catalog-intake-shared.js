(function () {
  if (window.ModelCatalogIntakeShared) {
    return;
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function basename(filePath) {
    var normalized = String(filePath || "").replace(/\\/g, "/");
    if (!normalized) {
      return "";
    }
    var parts = normalized.split("/");
    return parts[parts.length - 1] || normalized;
  }

  function formatBytes(bytes) {
    var value = Number(bytes || 0);
    if (!Number.isFinite(value) || value <= 0) {
      return "0 B";
    }
    var units = ["B", "KB", "MB", "GB", "TB"];
    var index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
    var scaled = value / Math.pow(1024, index);
    return scaled.toFixed(scaled >= 10 || index === 0 ? 0 : 1) + " " + units[index];
  }

  function formatLabel(value) {
    return String(value || "")
      .split(/[_\s-]+/)
      .filter(Boolean)
      .map(function (part) {
        return part.charAt(0).toUpperCase() + part.slice(1);
      })
      .join(" ");
  }

  // Issue #1341: single source of truth for the user-facing labels of the
  // grouping_strategy enum used by both the Browser and Server intake flows.
  // Internal codes (none/by-folder/by-root/flat) are intentionally unchanged.
  var GROUPING_STRATEGY_LABELS = {
    "none": "Group with the batch",
    "by-folder": "Separate Models by Folder",
    "by-root": "This folder as its own Model",
    "flat": "Separate Models by File",
  };

  function normalizeGroupingStrategy(strategy, options) {
    var settings = options || {};
    var allowFolderStrategies = settings.allowFolderStrategies !== false;
    var normalized = String(strategy == null ? "none" : strategy).trim().toLowerCase() || "none";
    if (normalized === "by-file") {
      normalized = "flat";
    }
    if (normalized === "none" || normalized === "flat") {
      return normalized;
    }
    if (allowFolderStrategies && (normalized === "by-folder" || normalized === "by-root")) {
      return normalized;
    }
    return "none";
  }

  function groupingStrategyLabel(strategy) {
    var normalized = normalizeGroupingStrategy(strategy, { allowFolderStrategies: true });
    if (Object.prototype.hasOwnProperty.call(GROUPING_STRATEGY_LABELS, normalized)) {
      return GROUPING_STRATEGY_LABELS[normalized];
    }
    return GROUPING_STRATEGY_LABELS.none;
  }

  // kind: 'folder' (all four options) or 'file' (none + flat only). Folder
  // selections expose the full set; pure file batches hide the folder-specific
  // by-folder / by-root choices because they don't apply.
  function groupingOptionsHtml(currentValue, kind) {
    var isFileKind = String(kind || "folder").toLowerCase() === "file";
    var current = normalizeGroupingStrategy(currentValue, { allowFolderStrategies: !isFileKind });
    var keys = isFileKind
      ? ["none", "flat"]
      : ["none", "by-folder", "by-root", "flat"];
    return keys.map(function (key) {
      return '<option value="' + key + '"'
        + (current === key ? ' selected' : '')
        + '>' + escapeHtml(GROUPING_STRATEGY_LABELS[key]) + '</option>';
    }).join("");
  }

  function parseDecisionWarnings(item) {
    if (!item || !item.decision_note) {
      return [];
    }
    try {
      var parsed = JSON.parse(item.decision_note);
      return Array.isArray(parsed)
        ? parsed.filter(function (entry) { return entry && typeof entry === "object"; })
        : [];
    } catch (_error) {
      return [];
    }
  }

  function warningMessages(warnings) {
    return (warnings || []).map(function (warning) {
      if (!warning || typeof warning !== "object") {
        return "";
      }
      return String(warning.message || warning.code || "").trim();
    }).filter(Boolean);
  }

  function duplicateWarnings(item) {
    return parseDecisionWarnings(item).filter(function (warning) {
      var code = String(warning && warning.code ? warning.code : "").toLowerCase();
      var message = String(warning && warning.message ? warning.message : "").toLowerCase();
      return code.indexOf("duplicate") >= 0
        || code.indexOf("hash_match") >= 0
        || message.indexOf("duplicate") >= 0
        || message.indexOf("existing working item") >= 0;
    });
  }

  function batchActionLabel(action) {
    if (action === "validate") {
      return "Validate";
    }
    if (action === "publish-curated") {
      return "Publish Curated";
    }
    if (action === "create-group") {
      return "Send To Working Files";
    }
    if (action === "defer") {
      return "Defer";
    }
    if (action === "reject") {
      return "Reject";
    }
    if (action === "delete") {
      return "Delete";
    }
    return formatLabel(action);
  }

  function summarizeStates(items, key) {
    var counts = {};
    (items || []).forEach(function (item) {
      var name = String(item && item[key] ? item[key] : "unknown");
      counts[name] = (counts[name] || 0) + 1;
    });
    return counts;
  }

  async function authHeaders(hass, forceRefresh) {
    var auth = hass && hass.auth ? hass.auth : null;
    if (!auth) {
      return {};
    }
    if (forceRefresh && typeof auth.refreshAccessToken === "function") {
      try {
        await auth.refreshAccessToken();
      } catch (_error) {
        // Keep current token.
      }
    }
    var token = auth.accessToken || (auth.data ? auth.data.accessToken : "");
    return token ? { Authorization: "Bearer " + token } : {};
  }

  function normalizeServiceResponse(payload) {
    if (Array.isArray(payload) && payload.length) {
      return normalizeServiceResponse(payload[0]);
    }
    if (payload && typeof payload === "object") {
      if (payload.service_response && typeof payload.service_response === "object") {
        return normalizeServiceResponse(payload.service_response);
      }
      if (payload.response && typeof payload.response === "object") {
        return normalizeServiceResponse(payload.response);
      }
      if (
        payload.content
        && typeof payload.content === "object"
        && (Object.prototype.hasOwnProperty.call(payload, "status")
          || Object.prototype.hasOwnProperty.call(payload, "headers"))
      ) {
        return Object.assign({}, payload.content, {
          status: payload.status,
          headers: payload.headers,
        });
      }
    }
    return payload && typeof payload === "object" ? payload : {};
  }

  async function callServiceWithResponse(hass, domain, service, data) {
    var endpoint = "/api/services/" + encodeURIComponent(String(domain || "")) + "/" + encodeURIComponent(String(service || "")) + "?return_response";
    var body = JSON.stringify(data && typeof data === "object" ? data : {});

    var response = await fetch(endpoint, {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, await authHeaders(hass, false)),
      credentials: "same-origin",
      body: body,
    });

    if (response.status === 401) {
      response = await fetch(endpoint, {
        method: "POST",
        headers: Object.assign({ "Content-Type": "application/json" }, await authHeaders(hass, true)),
        credentials: "same-origin",
        body: body,
      });
    }

    var payload = {};
    try {
      payload = await response.json();
    } catch (_error) {
      payload = {};
    }

    if (!response.ok) {
      throw new Error(payload && payload.message ? String(payload.message) : "Service call failed (HTTP " + String(response.status) + ")");
    }

    var normalized = normalizeServiceResponse(payload);
    if (normalized && normalized.success === false) {
      throw new Error(normalized.message || normalized.error || "Request failed.");
    }
    if (normalized && typeof normalized.status === "number" && normalized.status >= 400) {
      throw new Error(normalized.message || ("Request failed (HTTP " + String(normalized.status) + ")."));
    }
    return normalized;
  }

  async function selectInputOption(hass, entityId, option) {
    if (!hass || !entityId || !option || typeof hass.callService !== "function") {
      return false;
    }
    await hass.callService("input_select", "select_option", {
      entity_id: entityId,
      option: option,
    });
    return true;
  }

  async function postJsonWithAuth(hass, endpoint, payload) {
    var body = JSON.stringify(payload && typeof payload === "object" ? payload : {});
    var response = await fetch(endpoint, {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, await authHeaders(hass, false)),
      mode: "cors",
      body: body,
    });

    if (response.status === 401) {
      response = await fetch(endpoint, {
        method: "POST",
        headers: Object.assign({ "Content-Type": "application/json" }, await authHeaders(hass, true)),
        mode: "cors",
        body: body,
      });
    }

    var parsed = {};
    try {
      parsed = await response.json();
    } catch (_error) {
      parsed = {};
    }

    if (!response.ok || (parsed && parsed.success === false)) {
      var jsonError = new Error(parsed && (parsed.message || parsed.error) ? String(parsed.message || parsed.error) : "Request failed.");
      jsonError.status = Number(response.status || 0);
      jsonError.payload = parsed;
      throw jsonError;
    }

    return parsed && typeof parsed === "object" ? parsed : {};
  }

  async function getJsonWithAuth(hass, endpoint) {
    var response = await fetch(endpoint, {
      method: "GET",
      headers: await authHeaders(hass, false),
      mode: "cors",
    });

    if (response.status === 401) {
      response = await fetch(endpoint, {
        method: "GET",
        headers: await authHeaders(hass, true),
        mode: "cors",
      });
    }

    var parsed = {};
    try {
      parsed = await response.json();
    } catch (_error) {
      parsed = {};
    }

    if (!response.ok) {
      var getError = new Error(parsed && (parsed.message || parsed.error) ? String(parsed.message || parsed.error) : "Request failed.");
      getError.status = Number(response.status || 0);
      getError.payload = parsed;
      throw getError;
    }

    return parsed && typeof parsed === "object" ? parsed : {};
  }

  async function postFormWithAuth(hass, endpoint, formData) {
    var response = await fetch(endpoint, {
      method: "POST",
      headers: await authHeaders(hass, false),
      mode: "cors",
      body: formData,
    });

    if (response.status === 401) {
      response = await fetch(endpoint, {
        method: "POST",
        headers: await authHeaders(hass, true),
        mode: "cors",
        body: formData,
      });
    }

    var parsed = {};
    try {
      parsed = await response.json();
    } catch (_error) {
      parsed = {};
    }

    if (!response.ok || (parsed && parsed.success === false)) {
      var formError = new Error(parsed && (parsed.message || parsed.error) ? String(parsed.message || parsed.error) : "Request failed.");
      formError.status = Number(response.status || 0);
      formError.payload = parsed;
      throw formError;
    }

    return parsed && typeof parsed === "object" ? parsed : {};
  }

  async function postFormWithAuthWithProgress(hass, endpoint, formData, onProgress) {
    async function sendRequest(forceRefresh) {
      var headers = await authHeaders(hass, forceRefresh);
      return new Promise(function (resolve, reject) {
        var xhr = new XMLHttpRequest();
        xhr.open("POST", endpoint, true);
        Object.keys(headers || {}).forEach(function (name) {
          xhr.setRequestHeader(name, headers[name]);
        });

        if (typeof onProgress === "function" && xhr.upload) {
          xhr.upload.onprogress = function (event) {
            try {
              onProgress({
                loaded: Number(event && event.loaded || 0),
                total: Number(event && event.total || 0),
                lengthComputable: !!(event && event.lengthComputable),
              });
            } catch (_progressError) {
              // Progress callbacks are best-effort.
            }
          };
        }

        xhr.onload = function () {
          var bodyText = String(xhr.responseText || "");
          var parsed = {};
          if (bodyText) {
            try {
              parsed = JSON.parse(bodyText);
            } catch (_parseError) {
              parsed = {};
            }
          }
          resolve({
            status: Number(xhr.status || 0),
            ok: Number(xhr.status || 0) >= 200 && Number(xhr.status || 0) < 300,
            payload: parsed,
          });
        };

        xhr.onerror = function () {
          reject(new Error("Network request failed."));
        };

        xhr.send(formData);
      });
    }

    var firstAttempt = await sendRequest(false);
    var response = firstAttempt;
    if (firstAttempt.status === 401) {
      response = await sendRequest(true);
    }

    if (!response.ok || (response.payload && response.payload.success === false)) {
      var formError = new Error(response.payload && (response.payload.message || response.payload.error)
        ? String(response.payload.message || response.payload.error)
        : "Request failed.");
      formError.status = Number(response.status || 0);
      formError.payload = response.payload;
      throw formError;
    }

    return response.payload && typeof response.payload === "object" ? response.payload : {};
  }

  var browserUploadCapabilityCache = {};

  function normalizeSidecarBaseUrl(sidecarBaseUrl) {
    return String(sidecarBaseUrl || "").trim().replace(/\/$/, "");
  }

  async function supportsBrowserUploadV2(hass, sidecarBaseUrl) {
    var normalizedBaseUrl = normalizeSidecarBaseUrl(sidecarBaseUrl);
    if (!normalizedBaseUrl) {
      return false;
    }
    if (Object.prototype.hasOwnProperty.call(browserUploadCapabilityCache, normalizedBaseUrl)) {
      return browserUploadCapabilityCache[normalizedBaseUrl];
    }
    try {
      var openapi = await getJsonWithAuth(hass, normalizedBaseUrl + "/openapi.json");
      var paths = openapi && typeof openapi === "object" ? openapi.paths : null;
      var supportsV2 = !!(paths && paths["/api/intake/uploads/v2/browser-multipart"]);
      browserUploadCapabilityCache[normalizedBaseUrl] = supportsV2;
      return supportsV2;
    } catch (_error) {
      browserUploadCapabilityCache[normalizedBaseUrl] = false;
      return false;
    }
  }

  async function encodeBrowserFileForV1(fileEntry) {
    var buffer = await fileEntry.file.arrayBuffer();
    var bytes = new Uint8Array(buffer);
    var chunkSize = 0x8000;
    var binary = "";
    for (var index = 0; index < bytes.length; index += chunkSize) {
      binary += String.fromCharCode.apply(null, bytes.subarray(index, index + chunkSize));
    }
    return {
      filename: fileEntry.name,
      relative_path: fileEntry.relative_path,
      content_base64: btoa(binary),
      grouping_strategy: String(fileEntry.grouping_strategy || 'none').trim(),
      preserve_folder_structure: fileEntry.preserve_folder_structure !== false,
      group_title_source: fileEntry.group_title_source,
      group_title: fileEntry.group_title,
      file_last_modified_ms: fileEntry.file && Number.isFinite(Number(fileEntry.file.lastModified))
        ? Number(fileEntry.file.lastModified)
        : undefined,
    };
  }

  function browserFileManifestEntry(fileEntry) {
    return {
      filename: fileEntry.name,
      relative_path: fileEntry.relative_path,
      grouping_strategy: String(fileEntry.grouping_strategy || 'none').trim(),
      preserve_folder_structure: fileEntry.preserve_folder_structure !== false,
      group_title_source: fileEntry.group_title_source,
      group_title: fileEntry.group_title,
      file_last_modified_ms: fileEntry.file && Number.isFinite(Number(fileEntry.file.lastModified))
        ? Number(fileEntry.file.lastModified)
        : undefined,
    };
  }

  function shouldFallbackToV1(error) {
    if (!error || typeof error !== "object") {
      return false;
    }
    var status = Number(error.status || 0);
    return status === 404 || status === 405 || status === 415 || status === 501;
  }

  async function uploadBrowserFilesWithFallback(hass, sidecarBaseUrl, browserFiles, serverSelections, cleanupPolicy, options) {
    var normalizedBaseUrl = normalizeSidecarBaseUrl(sidecarBaseUrl);
    if (!normalizedBaseUrl) {
      throw new Error("Set input_text.model_catalog_sidecar_base_url to enable browser uploads.");
    }

    var files = Array.isArray(browserFiles) ? browserFiles : [];
    var selections = Array.isArray(serverSelections) ? serverSelections : [];
    var callbacks = options && typeof options === "object" ? options : {};
    var onUploadProgress = typeof callbacks.onUploadProgress === "function" ? callbacks.onUploadProgress : null;
    var onPhase = typeof callbacks.onPhase === "function" ? callbacks.onPhase : null;
    var supportsV2 = await supportsBrowserUploadV2(hass, normalizedBaseUrl);

    if (supportsV2) {
      try {
        if (onPhase) {
          onPhase("uploading_files");
        }
        var multipartForm = new FormData();
        multipartForm.append("manifest", JSON.stringify({
          cleanup_policy: cleanupPolicy,
          server_selections: selections,
          browser_files: files.map(browserFileManifestEntry),
        }));
        files.forEach(function (fileEntry) {
          multipartForm.append("files[]", fileEntry.file, fileEntry.name || (fileEntry.file && fileEntry.file.name) || "upload.bin");
        });
        return await postFormWithAuthWithProgress(
          hass,
          normalizedBaseUrl + "/api/intake/uploads/v2/browser-multipart",
          multipartForm,
          onUploadProgress
        );
      } catch (error) {
        if (!shouldFallbackToV1(error)) {
          throw error;
        }
      }
    }

    if (onPhase) {
      onPhase("encoding_files");
    }
    var encodedBrowserFiles = [];
    var processedFiles = 0;
    for (var index = 0; index < files.length; index += 1) {
      encodedBrowserFiles.push(await encodeBrowserFileForV1(files[index]));
      processedFiles += 1;
      if (onUploadProgress) {
        onUploadProgress({
          files_processed: processedFiles,
          files_total: files.length,
          lengthComputable: false,
        });
      }
    }
    if (onPhase) {
      onPhase("submitting_request");
    }
    return postJsonWithAuth(hass, normalizedBaseUrl + "/api/intake/uploads/browser", {
      browser_files: encodedBrowserFiles,
      server_selections: selections,
      cleanup_policy: cleanupPolicy,
    });
  }

  async function setHelperValue(hass, domain, entityId, value) {
    if (!hass || !entityId) {
      return;
    }
    if (domain === "input_select") {
      await hass.callService("input_select", "select_option", { entity_id: entityId, option: value });
      return;
    }
    if (domain === "input_text") {
      await hass.callService("input_text", "set_value", { entity_id: entityId, value: value });
    }
  }

  function getModelCatalogScopeStamps() {
    if (!window.__modelCatalogScopeStamps || typeof window.__modelCatalogScopeStamps !== "object") {
      window.__modelCatalogScopeStamps = {};
    }
    return window.__modelCatalogScopeStamps;
  }

  function getModelCatalogScopeStamp(scope) {
    var stamps = getModelCatalogScopeStamps();
    var key = String(scope || "");
    if (!key) {
      return 0;
    }
    var allStamp = Number(stamps.all || 0) || 0;
    var scopeStamp = Number(stamps[key] || 0) || 0;
    return Math.max(allStamp, scopeStamp);
  }

  function fireModelCatalogDataChanged(scopes, detail) {
    var normalizedScopes = Array.isArray(scopes)
      ? scopes.filter(function (scope) { return !!scope; })
      : [];
    var stamp = (typeof performance !== "undefined" && typeof performance.now === "function")
      ? Math.floor(performance.now() * 1000) + Date.now()
      : Date.now();
    var stamps = getModelCatalogScopeStamps();
    if (!normalizedScopes.length) {
      stamps.all = stamp;
    } else {
      normalizedScopes.forEach(function (scope) {
        var key = String(scope || "");
        if (key) {
          stamps[key] = stamp;
        }
      });
    }
    window.dispatchEvent(new CustomEvent("model-catalog-data-changed", {
      bubbles: true,
      composed: true,
      detail: Object.assign({ scopes: normalizedScopes, stamp: stamp }, detail || {}),
    }));
  }

  var sharedStyles = ""
    + "ha-card{border-radius:20px;border:1px solid rgba(148,163,184,0.18);background:linear-gradient(180deg,rgba(15,23,42,0.08),rgba(15,23,42,0.02));}"
    + ".shell{display:grid;gap:14px;padding:16px;}"
    + ".header{display:grid;gap:8px;}"
    + ".title-row{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;flex-wrap:wrap;}"
    + ".title{font-size:18px;font-weight:800;line-height:1.2;}"
    + ".subtitle{font-size:12px;color:var(--secondary-text-color);}"
    + ".section,.panel,.entry-row,.summary-card,.banner{border-radius:18px;border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.12);}"
    + ".section,.panel,.banner{padding:14px;}"
    + ".toolbar-row,.button-row,.entry-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center;}"
    + ".grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));}"
    + ".summary-card{padding:14px;display:grid;gap:6px;}"
    + ".summary-label{font-size:11px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;color:var(--secondary-text-color);}"
    + ".summary-value{font-size:16px;font-weight:800;overflow-wrap:anywhere;}"
    + ".field{display:grid;gap:6px;min-width:0;}"
    + ".field label{font-size:11px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;color:var(--secondary-text-color);}"
    + ".input,.select{width:100%;box-sizing:border-box;min-height:40px;padding:10px 12px;border-radius:12px;border:1px solid rgba(148,163,184,0.24);background:rgba(15,23,42,0.16);color:var(--primary-text-color);}"
    + ".select{color-scheme:light dark;}"
    + ".select option,.select optgroup{background:var(--card-background-color);color:var(--primary-text-color);}"
    + ".button{min-height:38px;padding:0 14px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(148,163,184,0.12);color:var(--primary-text-color);font-size:12px;font-weight:700;cursor:pointer;}"
    + ".button.primary{background:rgba(30,64,175,0.22);border-color:rgba(96,165,250,0.4);}"
    + ".button.warn{background:rgba(180,83,9,0.22);border-color:rgba(245,158,11,0.4);}"
    + ".button.danger{background:rgba(153,27,27,0.22);border-color:rgba(248,113,113,0.4);}"
    + ".button:disabled{opacity:.6;cursor:not-allowed;}"
    + ".status{font-size:12px;font-weight:700;color:var(--secondary-text-color);}"
    + ".status.error{color:#f87171;}"
    + ".chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;background:rgba(30,64,175,0.18);border:1px solid rgba(96,165,250,0.3);font-size:11px;font-weight:800;letter-spacing:.02em;text-transform:uppercase;}"
    + ".chip.warn{background:rgba(180,83,9,0.18);border-color:rgba(245,158,11,0.3);}"
    + ".chip.error{background:rgba(153,27,27,0.2);border-color:rgba(248,113,113,0.3);}"
    + ".chip.ok{background:rgba(22,101,52,0.22);border-color:rgba(74,222,128,0.3);}"
    + ".entries,.items{display:grid;gap:10px;}"
    + ".entry-row{display:grid;gap:10px;padding:12px;}"
    + ".entry-row.selected{border-color:rgba(96,165,250,0.4);background:rgba(30,64,175,0.18);}"
    + ".entry-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;flex-wrap:wrap;}"
    + ".entry-name{font-size:14px;font-weight:700;overflow-wrap:anywhere;}"
    + ".entry-path,.muted{font-size:12px;color:var(--secondary-text-color);overflow-wrap:anywhere;}"
    + ".state-row{padding:18px;border-radius:16px;border:1px dashed rgba(148,163,184,0.28);color:var(--secondary-text-color);text-align:center;}"
    + ".two-column{display:grid;gap:14px;grid-template-columns:minmax(0,1.2fr) minmax(0,0.8fr);}"
    + ".item-grid{display:grid;gap:8px;grid-template-columns:repeat(2,minmax(0,1fr));}"
    + ".link{color:var(--primary-color);cursor:pointer;text-decoration:underline;}"
    + ".batch-toolbar{display:grid;gap:10px;padding:12px;border-radius:18px;border:1px solid rgba(96,165,250,0.35);background:rgba(30,64,175,0.14);}"
    + ".result-summary{display:grid;gap:10px;padding:12px;border-radius:18px;border:1px solid rgba(148,163,184,0.22);background:rgba(15,23,42,0.16);}"
    + ".result-line{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;font-size:12px;}"
    + ".warning-box{display:grid;gap:6px;padding:12px;border-radius:14px;border:1px solid rgba(245,158,11,0.32);background:rgba(180,83,9,0.14);}"
    + ".warning-title{font-size:12px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;color:#fbbf24;}"
    + ".selector{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:700;color:var(--secondary-text-color);}"
    + ".validation-check{display:inline-flex;align-items:center;gap:8px;color:var(--primary-text-color);}"
    + ".validation-check input{-webkit-appearance:none;appearance:none;width:16px;height:16px;margin:0;opacity:1;border-radius:4px;border:1px solid rgba(148,163,184,0.48);background:rgba(15,23,42,0.2);display:inline-grid;place-content:center;box-sizing:border-box;}"
    + ".validation-check input:checked{background:#16a34a;border-color:#4ade80;}"
    + ".validation-check input:checked::after{content:'';width:8px;height:5px;border-left:2px solid #f0fdf4;border-bottom:2px solid #f0fdf4;transform:rotate(-45deg) translateY(-1px);}"
    + ".validation-check.fail input{border-color:rgba(148,163,184,0.48);background:rgba(15,23,42,0.2);}"
    + ".validation-check.warn{color:#fbbf24;}"
    + ".validation-icon.warn{display:inline-grid;place-content:center;width:16px;height:16px;font-size:14px;line-height:1;color:#fbbf24;}"
    + ".link-button{background:transparent;border:0;padding:0;margin-left:8px;font:inherit;color:#fbbf24;text-decoration:underline;cursor:pointer;}"
    + ".link-button:hover{color:#fde047;}"
    + ".hidden-upload-input{position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;opacity:0;pointer-events:none;}"
    + "@media (max-width: 860px){.two-column,.grid,.item-grid{grid-template-columns:1fr;}.shell{padding:14px;}}";

  window.ModelCatalogIntakeShared = {
    authHeaders: authHeaders,
    basename: basename,
    batchActionLabel: batchActionLabel,
    callServiceWithResponse: callServiceWithResponse,
    duplicateWarnings: duplicateWarnings,
    escapeHtml: escapeHtml,
    formatBytes: formatBytes,
    formatLabel: formatLabel,
    fireModelCatalogDataChanged: fireModelCatalogDataChanged,
    normalizeGroupingStrategy: normalizeGroupingStrategy,
    groupingStrategyLabel: groupingStrategyLabel,
    groupingOptionsHtml: groupingOptionsHtml,
    getModelCatalogScopeStamp: getModelCatalogScopeStamp,
    getJsonWithAuth: getJsonWithAuth,
    parseDecisionWarnings: parseDecisionWarnings,
    postFormWithAuth: postFormWithAuth,
    postJsonWithAuth: postJsonWithAuth,
    selectInputOption: selectInputOption,
    setHelperValue: setHelperValue,
    sharedStyles: sharedStyles,
    summarizeStates: summarizeStates,
    supportsBrowserUploadV2: supportsBrowserUploadV2,
    uploadBrowserFilesWithFallback: uploadBrowserFilesWithFallback,
    warningMessages: warningMessages,
  };
})();