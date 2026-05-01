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
      throw new Error(parsed && (parsed.message || parsed.error) ? String(parsed.message || parsed.error) : "Request failed.");
    }

    return parsed && typeof parsed === "object" ? parsed : {};
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
    + ".hidden-upload-input{display:none;}"
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
    parseDecisionWarnings: parseDecisionWarnings,
    postJsonWithAuth: postJsonWithAuth,
    selectInputOption: selectInputOption,
    setHelperValue: setHelperValue,
    sharedStyles: sharedStyles,
    summarizeStates: summarizeStates,
    warningMessages: warningMessages,
  };
})();