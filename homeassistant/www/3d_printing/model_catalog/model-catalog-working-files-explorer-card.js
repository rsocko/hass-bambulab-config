(function () {
  var VIEW_OPTIONS = ["groups", "all", "ungrouped"];
  var lastExplorerSnapshot = null;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function basename(pathValue) {
    var normalized = String(pathValue || "").replace(/\\/g, "/");
    if (!normalized) {
      return "";
    }
    var parts = normalized.split("/");
    return parts[parts.length - 1] || normalized;
  }

  function dirname(pathValue) {
    var normalized = String(pathValue || "").replace(/\\/g, "/");
    if (!normalized || normalized.indexOf("/") < 0) {
      return normalized;
    }
    return normalized.slice(0, normalized.lastIndexOf("/"));
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

  function formatStage(stage) {
    return String(stage || "draft")
      .split("_")
      .map(function (segment) {
        return segment ? segment.charAt(0).toUpperCase() + segment.slice(1) : "";
      })
      .join(" ");
  }

  function parseIsoDate(value) {
    if (!value) {
      return null;
    }
    var parsed = Date.parse(String(value));
    return Number.isFinite(parsed) ? new Date(parsed) : null;
  }

  function formatRelativeTime(value) {
    var parsed = parseIsoDate(value);
    if (!parsed) {
      return "-";
    }
    var seconds = Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 1000));
    if (seconds < 60) {
      return "just now";
    }
    if (seconds < 3600) {
      return String(Math.floor(seconds / 60)) + "m ago";
    }
    if (seconds < 86400) {
      return String(Math.floor(seconds / 3600)) + "h ago";
    }
    if (seconds < 604800) {
      return String(Math.floor(seconds / 86400)) + "d ago";
    }
    return String(Math.floor(seconds / 604800)) + "w ago";
  }

  function formatDateTime(value) {
    var parsed = parseIsoDate(value);
    if (!parsed) {
      return "-";
    }
    try {
      return parsed.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (_error) {
      return parsed.toISOString();
    }
  }

  function normalizePath(pathValue) {
    return String(pathValue || "").replace(/\\/g, "/");
  }

  function extensionFromPath(pathValue) {
    var name = basename(pathValue).toLowerCase();
    var index = name.lastIndexOf(".");
    return index >= 0 ? name.slice(index) : "";
  }

  function isModelExtension(extension) {
    return [".3mf", ".stl", ".step", ".stp", ".obj"].indexOf(String(extension || "").toLowerCase()) >= 0;
  }

  function isImageExtension(extension) {
    return [".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp"].indexOf(String(extension || "").toLowerCase()) >= 0;
  }

  function extensionBadge(extension) {
    return String(extension || "").replace(/^\./, "").toUpperCase() || "FILE";
  }

  function storageRelativePath(pathValue) {
    var normalized = normalizePath(pathValue);
    if (!normalized) {
      return { relative: "", storage: "Unknown" };
    }
    var lowered = normalized.toLowerCase();
    var markers = [
      { token: "/assets/model working files/", storage: "Working Files" },
      { token: "/assets/model inbox/", storage: "Model Inbox" },
      { token: "/model working files/", storage: "Working Files" },
      { token: "/model inbox/", storage: "Model Inbox" },
    ];
    for (var i = 0; i < markers.length; i += 1) {
      var marker = markers[i];
      var markerIndex = lowered.indexOf(marker.token);
      if (markerIndex >= 0) {
        return {
          relative: normalized.slice(markerIndex + marker.token.length).replace(/^\/+/, ""),
          storage: marker.storage,
        };
      }
    }
    return { relative: normalized.replace(/^\/+/, ""), storage: "Unknown" };
  }

  function commonPathPrefix(paths) {
    var splitPaths = (paths || []).map(function (pathValue) {
      return String(pathValue || "").split("/").filter(Boolean);
    }).filter(function (parts) {
      return parts.length > 1;
    });
    if (!splitPaths.length) {
      return "";
    }
    var prefix = splitPaths[0].slice(0, splitPaths[0].length - 1);
    for (var i = 1; i < splitPaths.length && prefix.length; i += 1) {
      var next = splitPaths[i].slice(0, splitPaths[i].length - 1);
      var cursor = 0;
      while (cursor < prefix.length && cursor < next.length && prefix[cursor].toLowerCase() === next[cursor].toLowerCase()) {
        cursor += 1;
      }
      prefix = prefix.slice(0, cursor);
    }
    return prefix.join("/");
  }

  function stageClassName(stage) {
    var normalized = String(stage || "draft").toLowerCase();
    if (normalized === "ready_to_publish") {
      return "ready_to_publish";
    }
    if (normalized === "in_progress") {
      return "in_progress";
    }
    return "draft";
  }

  function queueStateBorderColor(state) {
    var palette = {
      backlog: "#7a6a57",
      up_next: "#a07cff",
      preparing: "#ff9a3c",
      ready: "#e6d84a",
      in_progress: "#3aa9ff",
      blocked: "#ff6b6b",
      done: "#4fcf75",
    };
    return palette[state] || palette.up_next;
  }

  function normalizeQueueState(state) {
    var normalized = String(state || "").trim().toLowerCase();
    return ["backlog", "up_next", "preparing", "ready", "in_progress", "blocked", "done"].indexOf(normalized) >= 0
      ? normalized
      : "none";
  }

  function stageToQueueState(stage) {
    var normalized = String(stage || "").trim().toLowerCase();
    if (normalized === "ready_to_publish") {
      return "ready";
    }
    if (normalized === "in_progress") {
      return "in_progress";
    }
    return "backlog";
  }

  function initialsFromTitle(value) {
    var title = String(value || "").trim();
    if (!title) {
      return "WG";
    }
    var words = title
      .replace(/[^a-zA-Z0-9\s]+/g, " ")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    if (!words.length) {
      return title.slice(0, 2).toUpperCase();
    }
    if (words.length === 1) {
      return words[0].slice(0, 2).toUpperCase();
    }
    return (words[0].charAt(0) + words[1].charAt(0)).toUpperCase();
  }

  function hexToRgb(hexValue) {
    var raw = String(hexValue || "").trim().replace("#", "");
    if (raw.length === 3) {
      raw = raw.split("").map(function (char) { return char + char; }).join("");
    }
    if (!/^[0-9a-fA-F]{6}$/.test(raw)) {
      return { r: 122, g: 106, b: 87 };
    }
    return {
      r: parseInt(raw.slice(0, 2), 16),
      g: parseInt(raw.slice(2, 4), 16),
      b: parseInt(raw.slice(4, 6), 16),
    };
  }

  function rgbaFromHex(hexValue, alpha) {
    var rgb = hexToRgb(hexValue);
    return "rgba(" + String(rgb.r) + ", " + String(rgb.g) + ", " + String(rgb.b) + ", " + String(alpha) + ")";
  }

  function toFileUri(pathValue) {
    var normalized = String(pathValue || "").replace(/\\/g, "/");
    if (!normalized) {
      return "";
    }
    if (/^[a-zA-Z]:\//.test(normalized)) {
      return "file:///" + encodeURI(normalized);
    }
    return "file:///" + encodeURI(normalized.replace(/^\//, ""));
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
      var message = payload && payload.message ? String(payload.message) : "Service call failed (HTTP " + String(response.status) + ")";
      throw new Error(message);
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

  function fireBrowserModEvent(node, service, data) {
    var event = new CustomEvent("ll-custom", {
      bubbles: true,
      composed: true,
      detail: {
        browser_mod: {
          service: service,
          data: data,
          target: {},
        },
      },
    });

    if (document && document.body) {
      document.body.dispatchEvent(event);
      return;
    }

    node.dispatchEvent(event);
  }

  var sharedStyles = ''
    + 'ha-card{border-radius:0;border:none;background:transparent;box-shadow:none;}'
    + '.shell{display:grid;gap:14px;padding:6px 10px 10px;}'
    + '.title-row{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;flex-wrap:wrap;}'
    + '.title{font-size:18px;font-weight:800;line-height:1.2;}'
    + '.subtitle{font-size:12px;color:var(--secondary-text-color);}'
    + '.status{font-size:12px;font-weight:700;color:var(--secondary-text-color);}'
    + '.status.error{color:#f87171;}'
    + '.toolbar,.section{border-radius:16px;border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.14);padding:14px;}'
    + '.toolbar-row,.button-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;}'
    + '.tab-row{display:inline-flex;gap:8px;flex-wrap:wrap;}'
    + '.thumb-size-toggle{display:inline-flex;padding:2px;border:1px solid rgba(148,163,184,0.24);border-radius:999px;background:rgba(15,23,42,0.35);}'
    + '.thumb-size-toggle button{border:0;background:transparent;color:var(--secondary-text-color);font-size:10px;padding:4px 10px;border-radius:999px;cursor:pointer;}'
    + '.thumb-size-toggle button.active{background:rgba(167,139,250,0.20);color:#ddd6fe;}'
    + '.tab{min-height:34px;padding:0 12px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(148,163,184,0.12);font-size:12px;font-weight:700;cursor:pointer;}'
    + '.tab.active{background:rgba(20,184,166,0.2);border-color:rgba(94,234,212,0.36);color:#99f6e4;}'
    + '.button{min-height:34px;padding:0 12px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(148,163,184,0.12);color:var(--primary-text-color);font-size:12px;font-weight:700;cursor:pointer;}'
    + '.button.primary{background:rgba(20,184,166,0.2);border-color:rgba(94,234,212,0.34);color:#99f6e4;}'
    + '.button.warn{background:rgba(180,83,9,0.2);border-color:rgba(245,158,11,0.4);}'
    + '.button:disabled{opacity:.6;cursor:not-allowed;}'
    + '.field{display:grid;gap:6px;min-width:0;}'
    + '.field label{font-size:11px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;color:var(--secondary-text-color);}'
    + '.input,.select{width:100%;box-sizing:border-box;min-height:36px;padding:8px 10px;border-radius:10px;border:1px solid rgba(148,163,184,0.24);background:rgba(15,23,42,0.16);color:var(--primary-text-color);}'
    + '.select{color-scheme:light dark;}'
    + '.select option,.select optgroup{background:var(--card-background-color);color:var(--primary-text-color);}'
    + '.grow{flex:1 1 220px;}'
    + '.state-row{padding:18px;border-radius:14px;border:1px dashed rgba(148,163,184,0.28);text-align:center;color:var(--secondary-text-color);}'
    + '.loading-shell{display:grid;gap:10px;}'
    + '.loading-title{font-size:12px;font-weight:700;color:var(--secondary-text-color);}'
    + '.skeleton-list{display:grid;gap:8px;}'
    + '.skeleton-row{height:44px;border-radius:10px;border:1px solid rgba(148,163,184,0.2);background:linear-gradient(90deg, rgba(30,41,59,0.5) 0%, rgba(71,85,105,0.32) 50%, rgba(30,41,59,0.5) 100%);background-size:220% 100%;animation:mcwf-shimmer 1.25s linear infinite;}'
    + '@keyframes mcwf-shimmer{0%{background-position:100% 0;}100%{background-position:-100% 0;}}'
    + '.bulk-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:9px 12px;border:1px solid rgba(94,234,212,0.3);background:rgba(94,234,212,0.08);border-radius:12px;color:#99f6e4;font-size:12px;}'
    + '.bulk-bar .spacer{flex:1;}'
    + '.groups{display:grid;gap:10px;}'
    + '.group-row{position:relative;border:1px solid rgba(148,163,184,0.2);background:rgba(15,23,42,0.1);border-radius:14px;padding:12px 12px 10px 14px;--queue-border-color:#7a6a57;--group-icon-bg:rgba(122,106,87,0.26);--group-icon-fg:#f8fafc;--group-icon-ring:rgba(122,106,87,0.5);}'
    + '.group-row.active{border-color:rgba(94,234,212,0.34);background:rgba(20,184,166,0.08);}'
    + '.group-row::after{content:"";position:absolute;inset:0;border-radius:inherit;background:transparent;box-shadow:inset 5px 0 0 var(--queue-border-color,#a07cff);pointer-events:none;}'
    + '.group-header{display:grid;grid-template-columns:52px minmax(0,1fr) auto;gap:12px;align-items:start;}'
    + '.thumb{width:52px;height:52px;border-radius:10px;border:1px solid var(--group-icon-ring);display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:900;letter-spacing:.04em;color:var(--group-icon-fg);background:var(--group-icon-bg);text-transform:uppercase;}'
    + '.group-title{font-size:14px;font-weight:700;line-height:1.3;overflow-wrap:anywhere;cursor:pointer;}'
    + '.folder-hint{font-size:11px;color:var(--secondary-text-color);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
    + '.path-summary{margin-top:6px;font-size:10px;color:var(--secondary-text-color);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;display:flex;gap:8px;flex-wrap:wrap;}'
    + '.path-summary strong{color:#93c5fd;font-weight:700;}'
    + '.group-meta{display:flex;gap:10px;flex-wrap:wrap;margin-top:6px;color:var(--secondary-text-color);font-size:11px;}'
    + '.stage-chip{display:inline-flex;align-items:center;padding:2px 8px;border-radius:999px;border:1px solid rgba(148,163,184,0.3);font-size:10px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;background:rgba(100,116,139,0.2);color:#dbe7f2;box-shadow:inset 0 0 0 1px rgba(255,255,255,0.03);}'
    + '.stage-chip.draft{border-color:rgba(148,163,184,0.44);background:rgba(71,85,105,0.34);color:#e2e8f0;}'
    + '.stage-chip.in_progress{border-color:rgba(252,211,77,0.5);color:#fef3c7;background:rgba(245,158,11,0.32);}'
    + '.stage-chip.ready_to_publish{border-color:rgba(134,239,172,0.5);color:#dcfce7;background:rgba(46,125,50,0.36);}'
    + '.group-right{text-align:right;display:grid;gap:6px;justify-items:end;}'
    + '.updated{font-size:11px;color:var(--secondary-text-color);}'
    + '.updated strong{color:var(--primary-text-color);}'
    + '.expander{border:1px solid rgba(148,163,184,0.26);background:rgba(15,23,42,0.3);color:#cbd5e1;border-radius:10px;min-width:40px;height:40px;cursor:pointer;font-size:18px;font-weight:900;line-height:1;display:inline-flex;align-items:center;justify-content:center;}'
    + '.strip{margin-top:10px;border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.24);border-radius:12px;padding:10px;display:grid;gap:8px;}'
    + '.strip-head{display:flex;align-items:center;justify-content:space-between;gap:10px;color:var(--secondary-text-color);}'
    + '.strip-head-left{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0;}'
    + '.strip-title{font-size:10px;text-transform:uppercase;letter-spacing:.06em;font-weight:700;}'
    + '.subview-toggle{display:inline-flex;padding:2px;border:1px solid rgba(148,163,184,0.24);border-radius:999px;background:rgba(15,23,42,0.35);}'
    + '.subview-toggle button{border:0;background:transparent;color:var(--secondary-text-color);font-size:10px;padding:4px 10px;border-radius:999px;cursor:pointer;}'
    + '.subview-toggle button.active{background:rgba(94,234,212,0.18);color:#99f6e4;}'
    + '.folder-type-filters.inline{display:inline-flex;gap:6px;flex-wrap:wrap;align-items:center;}'
    + '.type-chip{min-height:24px;padding:4px 10px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(148,163,184,0.08);color:#cbd5e1;font-size:10px;font-weight:700;cursor:pointer;}'
    + '.type-chip.active{box-shadow:inset 0 0 0 1px rgba(255,255,255,0.04);}'
    + '.type-chip.type-all:hover,.type-chip.type-all:focus-visible,.type-chip.type-all.active{background:rgba(167,139,250,0.20);border-color:rgba(196,181,253,0.34);color:#ddd6fe;outline:none;}'
    + '.type-chip.type-models:hover,.type-chip.type-models:focus-visible,.type-chip.type-models.active{background:rgba(0,137,123,0.16);border-color:rgba(125,211,200,0.30);color:#7dd3c8;outline:none;}'
    + '.type-chip.type-images:hover,.type-chip.type-images:focus-visible,.type-chip.type-images.active{background:rgba(37,99,235,0.16);border-color:rgba(147,197,253,0.34);color:#93c5fd;outline:none;}'
    + '.type-chip.type-other:hover,.type-chip.type-other:focus-visible,.type-chip.type-other.active{background:rgba(245,158,11,0.16);border-color:rgba(252,211,77,0.34);color:#fcd34d;outline:none;}'
    + '.file-list{display:grid;gap:4px;}'
    + '.file-row{display:grid;grid-template-columns:var(--file-thumb-col,38px) minmax(0,1fr)92px 192px 96px 84px;gap:8px;align-items:center;padding:6px;border-radius:8px;}'
    + '.file-row:hover{background:rgba(255,255,255,0.03);}'
    + '.file-row.primary{background:rgba(245,194,66,0.08);border:1px solid rgba(245,194,66,0.22);}'
    + '.file-thumb{width:var(--thumb-size,34px);height:var(--thumb-size,34px);border-radius:8px;border:1px solid rgba(148,163,184,0.3);display:flex;align-items:center;justify-content:center;overflow:hidden;background:rgba(255,255,255,0.04);font-size:9px;font-weight:800;color:var(--secondary-text-color);}'
    + '.file-thumb img{width:100%;height:100%;object-fit:cover;display:block;}'
    + '.ext-badge{width:26px;height:24px;border-radius:6px;border:1px solid rgba(148,163,184,0.25);display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:800;color:var(--secondary-text-color);background:rgba(255,255,255,0.04);}'
    + '.file-thumb .ext-badge{width:var(--thumb-badge-width,26px);height:var(--thumb-badge-height,24px);font-size:var(--thumb-badge-font,9px);border:0;box-shadow:none;}'
    + '.ext-badge.x-3mf{color:#5eead4;border-color:rgba(94,234,212,0.3);background:rgba(94,234,212,0.12);}'
    + '.ext-badge.x-stl,.ext-badge.x-step,.ext-badge.x-stp,.ext-badge.x-obj{color:#93c5fd;border-color:rgba(96,165,250,0.32);background:rgba(96,165,250,0.12);}'
    + '.file-main{min-width:0;}'
    + '.file-name{font-size:12px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
    + '.file-path{font-size:10px;color:var(--secondary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;}'
    + '.file-size,.file-modified{font-size:11px;color:var(--secondary-text-color);text-align:right;white-space:nowrap;}'
    + '.file-modified strong{font-weight:700;}'
    + '.file-modified .sub{display:block;font-size:10px;color:var(--secondary-text-color);opacity:.85;}'
    + '.primary-slot{display:flex;justify-content:center;}'
    + '.selector-slot{display:flex;justify-content:flex-end;}'
    + '.primary-pill{display:inline-flex;padding:2px 7px;border-radius:999px;background:rgba(245,194,66,0.15);border:1px solid rgba(245,194,66,0.33);color:#f5c242;font-size:10px;font-weight:700;}'
    + '.primary-action{min-width:94px;min-height:28px;padding:0 10px;border-radius:999px;border:1px dashed rgba(148,163,184,0.32);background:rgba(15,23,42,0.24);color:#94a3b8;font-size:11px;font-weight:700;cursor:pointer;}'
    + '.primary-action:hover,.primary-action:focus-visible{border-style:solid;border-color:rgba(96,165,250,0.46);background:rgba(96,165,250,0.14);color:#dbeafe;outline:none;}'
    + '.primary-action.is-current{border-style:solid;border-color:rgba(245,194,66,0.42);background:rgba(245,194,66,0.16);color:#f5c242;cursor:default;}'
    + '.primary-action.is-current:hover,.primary-action.is-current:focus-visible{background:rgba(245,194,66,0.16);color:#f5c242;}'
    + '.selector{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:var(--secondary-text-color);}'
    + '.group-actions{display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding-top:8px;border-top:1px dashed rgba(148,163,184,0.2);}'
    + '.group-actions .spacer{flex:1;}'
    + '.other-strip{border:1px dashed rgba(148,163,184,0.26);border-radius:10px;padding:8px;display:grid;gap:6px;}'
    + '.other-head{display:flex;justify-content:space-between;font-size:10px;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.06em;}'
    + '.other-chips{display:flex;gap:5px;flex-wrap:wrap;}'
    + '.other-chip{display:inline-flex;align-items:center;padding:3px 8px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);font-size:10px;color:var(--secondary-text-color);}'
    + '.folder-explorer{display:grid;gap:8px;}'
    + '.folder-head-row{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;}'
    + '.folder-type-filters{display:flex;gap:6px;flex-wrap:wrap;}'
    + '.folder-breadcrumbs{display:flex;align-items:center;gap:4px;flex-wrap:wrap;}'
    + '.breadcrumb-up{appearance:none;border:0;background:transparent;padding:2px 6px;margin:0;border-radius:6px;color:var(--secondary-text-color);font-size:14px;font-weight:800;cursor:pointer;line-height:1.2;display:inline-flex;align-items:center;justify-content:center;min-width:22px;}'
    + '.breadcrumb-up:hover,.breadcrumb-up:focus-visible{background:rgba(148,163,184,0.18);color:var(--primary-text-color);outline:none;}'
    + '.breadcrumb-link{appearance:none;border:0;background:transparent;padding:2px 6px;margin:0;border-radius:6px;color:var(--secondary-text-color);font-size:12px;cursor:pointer;line-height:1.4;}'
    + '.breadcrumb-link:hover,.breadcrumb-link:focus-visible{background:rgba(148,163,184,0.18);color:var(--primary-text-color);outline:none;}'
    + '.breadcrumb-link.current{font-weight:700;color:var(--primary-text-color);}'
    + '.crumb-sep{font-size:12px;color:var(--secondary-text-color);opacity:.7;padding:0 2px;}'
    + '.folder-browser-list{display:grid;gap:6px;}'
    + '.browser-row{display:grid;grid-template-columns:var(--browser-icon-col,46px) minmax(0,1fr) 92px 192px auto;gap:8px;align-items:center;padding:8px 10px;border-radius:10px;border:1px solid rgba(148,163,184,0.2);background:rgba(15,23,42,0.24);text-align:left;}'
    + '.browser-row.folder{cursor:pointer;background:rgba(96,165,250,0.1);border-color:rgba(96,165,250,0.26);}'
    + '.browser-row.folder:hover{background:rgba(96,165,250,0.16);border-color:rgba(96,165,250,0.36);}'
    + '.browser-row.file:hover{background:rgba(255,255,255,0.03);}'
    + '.browser-icon{display:flex;align-items:center;justify-content:center;width:var(--browser-icon-width,42px);height:var(--browser-icon-height,28px);border-radius:8px;border:1px solid rgba(148,163,184,0.24);font-size:10px;font-weight:800;color:var(--secondary-text-color);background:rgba(255,255,255,0.04);}'
    + '.browser-icon img{width:100%;height:100%;object-fit:cover;display:block;}'
    + '.browser-row.folder .browser-icon{font-size:14px;color:#bfdbfe;border-color:rgba(96,165,250,0.34);background:rgba(96,165,250,0.14);}'
    + '.browser-name{min-width:0;font-size:12px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;justify-self:start;text-align:left;}'
    + '.browser-size,.browser-modified{font-size:11px;color:var(--secondary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:right;}'
    + '.browser-modified .sub{display:block;font-size:10px;color:var(--secondary-text-color);opacity:.85;}'
    + '.browser-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;}'
    + '.files-table{border:1px solid rgba(148,163,184,0.18);border-radius:12px;overflow:auto;background:rgba(15,23,42,0.1);}'
    + '.files-table table{width:100%;border-collapse:collapse;min-width:860px;}'
    + '.files-table th{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--secondary-text-color);padding:10px;border-bottom:1px solid rgba(148,163,184,0.2);text-align:left;background:rgba(15,23,42,0.35);}'
    + '.files-table td{padding:10px;border-bottom:1px solid rgba(148,163,184,0.12);font-size:12px;vertical-align:middle;}'
    + '.files-table tr:hover{background:rgba(94,234,212,0.06);}'
    + '.files-table tr.selected{background:rgba(94,234,212,0.1);}'
    + '.row-name{display:flex;gap:10px;align-items:center;min-width:0;}'
    + '.row-name-text{min-width:0;}'
    + '.row-name-title{font-size:12px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
    + '.row-name-sub{font-size:10px;color:var(--secondary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;}'
    + '.group-chips{display:flex;gap:4px;flex-wrap:wrap;}'
    + '.group-chip{display:inline-flex;align-items:center;padding:2px 7px;border-radius:999px;font-size:10px;border:1px solid rgba(96,165,250,0.28);background:rgba(96,165,250,0.12);color:#bfdbfe;}'
    + '.group-chip.empty{border-style:dashed;color:var(--secondary-text-color);background:transparent;}'
    + '.validation{font-size:11px;color:#86efac;}'
    + '.validation.warn{color:#fca5a5;}'
    + '.right{text-align:right;}'
    + '.shell.thumb-small{--thumb-size:34px;--file-thumb-col:38px;--browser-icon-col:46px;--browser-icon-width:42px;--browser-icon-height:28px;--thumb-badge-width:22px;--thumb-badge-height:20px;--thumb-badge-font:9px;}'
    + '.shell.thumb-medium{--thumb-size:58px;--file-thumb-col:62px;--browser-icon-col:66px;--browser-icon-width:62px;--browser-icon-height:42px;--thumb-badge-width:34px;--thumb-badge-height:30px;--thumb-badge-font:12px;}'
    + '.shell.thumb-large{--thumb-size:116px;--file-thumb-col:124px;--browser-icon-col:132px;--browser-icon-width:124px;--browser-icon-height:84px;--thumb-badge-width:68px;--thumb-badge-height:60px;--thumb-badge-font:20px;}'
    + '@media (max-width: 980px){.group-header{grid-template-columns:44px minmax(0,1fr);}.group-right{grid-column:1 / -1;justify-items:start;text-align:left;}.file-row{grid-template-columns:38px minmax(0,1fr)84px;}.file-row .file-size,.file-row .file-modified,.file-row .primary-slot{display:none;}.browser-row{grid-template-columns:46px minmax(0,1fr)auto;}.browser-row .browser-size,.browser-row .browser-modified{display:none;}}';

  class ModelCatalogWorkingFilesExplorerCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._hass = null;
      this._config = null;
      this._loading = false;
      this._loadingPhase = '';
      this._error = '';
      this._status = '';
      this._view = 'groups';
      this._query = '';
      this._extension = '';
      this._summary = {};
      this._groups = [];
      this._files = [];
      this._hasLoadedExplorer = false;
      this._hasAttemptedInitialReindex = false;
      this._selectedGroupId = 0;
      this._selectedPaths = {};
      this._collapsedGroups = {};
      this._groupSubViews = {};
      this._groupFolderTypeFilters = {};
      this._groupFolderBrowsePaths = {};
      this._loadingGroupFiles = {};
      this._thumbnailSize = 'small';
      this._backgroundReindexInFlight = false;
      this._lastAppliedScopeStamp = 0;
      this._catalogScope = 'working';
      this._boundClick = this._handleClick.bind(this);
      this._boundCatalogDataChanged = this._handleCatalogDataChanged.bind(this);
    }

    setConfig(config) {
      var requestedInitialGroupId = Number(config && config.initial_group_id ? config.initial_group_id : 0);
      var normalizedInitialGroupId = Number.isFinite(requestedInitialGroupId) && requestedInitialGroupId > 0
        ? Math.round(requestedInitialGroupId)
        : 0;
      var initialQuery = config && config.initial_query ? String(config.initial_query).trim() : '';
      this._config = {
        title: config && config.title ? String(config.title) : 'Working Files',
        per_page: config && config.per_page ? Number(config.per_page) : 120,
        auto_reindex_on_initial_load: !!(config && config.auto_reindex_on_initial_load === true),
        initial_group_id: normalizedInitialGroupId,
        initial_query: initialQuery,
      };
      if (initialQuery) {
        this._query = initialQuery;
      }
      if (normalizedInitialGroupId > 0) {
        this._selectedGroupId = normalizedInitialGroupId;
      }
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      if (this.isConnected && !this._loading && !this._hasLoadedExplorer) {
        this._loadExplorer();
      } else if (this.isConnected && !this._loading && this._isScopeStale()) {
        this._loadExplorer();
      }
    }

    connectedCallback() {
      if (this.shadowRoot) {
        this.shadowRoot.addEventListener('click', this._boundClick);
      }
      window.addEventListener('model-catalog-data-changed', this._boundCatalogDataChanged);
      if (this._hass && !this._loading) {
        if (!this._hasLoadedExplorer) {
          this._loadExplorer();
        } else if (this._isScopeStale()) {
          this._loadExplorer();
        }
      }
    }

    disconnectedCallback() {
      if (this.shadowRoot) {
        this.shadowRoot.removeEventListener('click', this._boundClick);
      }
      window.removeEventListener('model-catalog-data-changed', this._boundCatalogDataChanged);
    }

    getCardSize() {
      return 16;
    }

    _selectedPathList() {
      return Object.keys(this._selectedPaths).filter(function (pathValue) {
        return !!pathValue && !!this._selectedPaths[pathValue];
      }, this);
    }

    _currentSelectedGroup() {
      var selectedId = Number(this._selectedGroupId || 0);
      return this._groups.find(function (group) {
        return Number(group.id) === selectedId;
      }) || null;
    }

    async _reindexWorkingFiles() {
      return callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_reindex_working_files', {
        recurse: true,
        compute_hashes: false,
      });
    }

    async _runBackgroundInitialReindex() {
      if (this._backgroundReindexInFlight) {
        return;
      }
      this._backgroundReindexInFlight = true;
      this._status = 'Refreshing file index in background...';
      this._render();
      try {
        await this._reindexWorkingFiles();
        this._status = 'Index refreshed. Updating view...';
        this._render();
        await this._loadExplorer({ skipInitialReindex: true });
      } catch (_error) {
        this._status = 'Background reindex failed; showing current index.';
        this._render();
      } finally {
        this._backgroundReindexInFlight = false;
      }
    }

    async _loadExplorer(options) {
      if (!this._hass || this._loading) {
        return;
      }
      var shouldForceReindex = !!(options && options.forceReindex);
      var skipInitialReindex = !!(options && options.skipInitialReindex);
      var requestSignature = JSON.stringify({
        view: this._view,
        q: this._query || '',
        extension: this._extension || '',
        limit: this._config.per_page,
      });
      var hadRenderableData = (this._view === 'groups')
        ? !!(Array.isArray(this._groups) && this._groups.length)
        : !!(Array.isArray(this._files) && this._files.length);

      if (!hadRenderableData && !shouldForceReindex && lastExplorerSnapshot && lastExplorerSnapshot.signature === requestSignature) {
        this._summary = lastExplorerSnapshot.summary || {};
        this._groups = Array.isArray(lastExplorerSnapshot.groups) ? lastExplorerSnapshot.groups : [];
        this._files = Array.isArray(lastExplorerSnapshot.files) ? lastExplorerSnapshot.files : [];
        hadRenderableData = (this._view === 'groups')
          ? !!this._groups.length
          : !!this._files.length;
      }

      this._hasLoadedExplorer = true;
      this._loading = true;
      this._loadingPhase = shouldForceReindex ? 'Reindexing files...' : 'Loading Working Files...';
      this._error = '';
      this._status = hadRenderableData ? 'Updating results...' : '';
      this._render();

      var shared = window.ModelCatalogIntakeShared;
      var stampSnapshot = shared && typeof shared.getModelCatalogScopeStamp === 'function'
        ? shared.getModelCatalogScopeStamp(this._catalogScope || 'working')
        : 0;
      var shouldRunInitialReindex = false;

      try {
        if (shouldForceReindex) {
          try {
            await this._reindexWorkingFiles();
          } catch (_reindexError) {
            this._status = 'Reindex failed; showing last indexed results.';
          }
        } else if (shouldRunInitialReindex) {
          this._hasAttemptedInitialReindex = true;
        }

        var response = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_explore_working_files', {
          view: this._view,
          q: this._query || undefined,
          extension: this._extension || undefined,
          lightweight: this._view === 'groups' ? true : undefined,
          limit: this._config.per_page,
          offset: 0,
        });
        this._summary = response.summary || {};
        this._groups = Array.isArray(response.groups) ? response.groups : [];
        this._files = Array.isArray(response.files) ? response.files : [];
        lastExplorerSnapshot = {
          signature: requestSignature,
          summary: this._summary,
          groups: this._groups,
          files: this._files,
        };

        this._groups.forEach(function (group) {
          var id = Number(group && group.id);
          if (!id) {
            return;
          }
          if (!Object.prototype.hasOwnProperty.call(this._collapsedGroups, id)) {
            this._collapsedGroups[id] = true;
          }
          if (!Object.prototype.hasOwnProperty.call(this._groupSubViews, id)) {
            this._groupSubViews[id] = 'files';
          }
          if (!Object.prototype.hasOwnProperty.call(this._groupFolderTypeFilters, id)) {
            this._groupFolderTypeFilters[id] = 'models';
          }
          if (!Object.prototype.hasOwnProperty.call(this._groupFolderBrowsePaths, id)) {
            this._groupFolderBrowsePaths[id] = this._defaultGroupFolderPath(group);
          }
          if (!Object.prototype.hasOwnProperty.call(this._loadingGroupFiles, id)) {
            this._loadingGroupFiles[id] = false;
          }
        }, this);

        if (this._view === 'groups') {
          if (!this._groups.length) {
            this._selectedGroupId = 0;
          } else {
            var preferredGroupId = Number(this._config && this._config.initial_group_id || 0);
            if (preferredGroupId > 0) {
              var preferredGroup = this._groups.find(function (group) {
                return Number(group && group.id) === preferredGroupId;
              });
              if (preferredGroup) {
                this._selectedGroupId = preferredGroupId;
              }
            }
            var selected = this._currentSelectedGroup();
            if (!selected) {
              this._selectedGroupId = Number(this._groups[0].id || 0);
            }
          }
        }
        if (stampSnapshot > (Number(this._lastAppliedScopeStamp) || 0)) {
          this._lastAppliedScopeStamp = stampSnapshot;
        }
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not load Working Files explorer.';
      } finally {
        this._loading = false;
        this._loadingPhase = '';
        this._render();
      }

    }

    _openLocalPath(pathValue) {
      var uri = toFileUri(pathValue);
      if (!uri) {
        this._error = 'Launch path is empty.';
        this._render();
        return;
      }

      var opened = null;
      try {
        opened = window.open(uri, '_blank', 'noopener');
      } catch (_error) {
        opened = null;
      }

      if (opened) {
        this._status = 'Opened: ' + uri;
        this._error = '';
        this._render();
        return;
      }

      fireBrowserModEvent(this, 'browser_mod.javascript', {
        code: 'window.open(' + JSON.stringify(uri) + ', "_blank", "noopener");',
      });
      this._status = 'Requested open via Browser Mod: ' + uri;
      this._error = '';
      this._render();
    }

    _openExplorer(pathValue) {
      this._openLocalPath(dirname(pathValue));
    }

    _togglePathSelection(pathValue) {
      var normalized = String(pathValue || '').trim();
      if (!normalized) {
        return;
      }
      if (this._selectedPaths[normalized]) {
        delete this._selectedPaths[normalized];
      } else {
        this._selectedPaths[normalized] = true;
      }
      this._render();
    }

    _collectGroupPromptOptions() {
      if (!this._groups.length) {
        return '(No groups available)';
      }
      return this._groups.map(function (group) {
        return String(group.id) + ': ' + (group.title || 'Untitled Group');
      }).join('\n');
    }

    async _createGroupFromSelection() {
      var selectedPaths = this._selectedPathList();
      if (!selectedPaths.length) {
        this._error = 'Select one or more files first.';
        this._render();
        return;
      }
      var title = window.prompt('New working group title', basename(selectedPaths[0]) || 'Working Group');
      if (!title) {
        return;
      }

      this._loading = true;
      this._error = '';
      this._status = '';
      this._render();
      try {
        var created = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_create_working_group', {
          title: title,
          stage: 'draft',
          notes: 'Created from Working Files explorer selection',
        });
        var groupId = created && created.group ? Number(created.group.id || 0) : 0;
        if (!groupId) {
          throw new Error('Group was created but no group id was returned.');
        }

        await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_batch_add_working_group_memberships', {
          group_id: groupId,
          file_paths: selectedPaths,
          item_role: 'supporting',
          allow_multi_group: true,
        });
        this._selectedPaths = {};
        this._status = 'Created group and added ' + String(selectedPaths.length) + ' file(s).';
        this._view = 'groups';
        await this._loadExplorer();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not create group from selection.';
        this._loading = false;
        this._render();
      }
    }

    async _addSelectionToExistingGroup() {
      var selectedPaths = this._selectedPathList();
      if (!selectedPaths.length) {
        this._error = 'Select one or more files first.';
        this._render();
        return;
      }

      var answer = window.prompt('Enter destination group id:\n\n' + this._collectGroupPromptOptions(), this._groups.length ? String(this._groups[0].id) : '');
      if (!answer) {
        return;
      }
      var groupId = Number(answer);
      if (!Number.isFinite(groupId) || groupId <= 0) {
        this._error = 'A valid group id is required.';
        this._render();
        return;
      }

      this._loading = true;
      this._error = '';
      this._status = '';
      this._render();
      try {
        var response = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_batch_add_working_group_memberships', {
          group_id: groupId,
          file_paths: selectedPaths,
          item_role: 'supporting',
          allow_multi_group: true,
        });
        this._status = 'Added files to group ' + String(groupId) + ' (' + String(response && response.summary ? response.summary.added : 0) + ' added).';
        this._selectedPaths = {};
        await this._loadExplorer();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not add files to group.';
        this._loading = false;
        this._render();
      }
    }

    async _removeSelectionFromSelectedGroup() {
      var group = this._currentSelectedGroup();
      var selectedPaths = this._selectedPathList();
      if (!group) {
        this._error = 'Select a group first.';
        this._render();
        return;
      }
      if (!selectedPaths.length) {
        this._error = 'Select one or more files first.';
        this._render();
        return;
      }

      this._loading = true;
      this._error = '';
      this._status = '';
      this._render();
      try {
        var response = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_batch_remove_working_group_memberships', {
          group_id: group.id,
          file_paths: selectedPaths,
        });
        this._status = 'Removed ' + String(response && response.summary ? response.summary.removed : 0) + ' file(s) from group.';
        this._selectedPaths = {};
        await this._loadExplorer();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not remove group memberships.';
        this._loading = false;
        this._render();
      }
    }

    async _runReorganize(groupId) {
      if (groupId) {
        this._selectedGroupId = Number(groupId);
      }
      var group = this._currentSelectedGroup();
      if (!group) {
        this._error = 'Select a group first.';
        this._render();
        return;
      }

      this._loading = true;
      this._error = '';
      this._status = '';
      this._render();
      try {
        var dryRun = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_reorganize_working_group', {
          group_id: group.id,
          execute: false,
        });
        var moveCount = Array.isArray(dryRun.plan)
          ? dryRun.plan.filter(function (entry) { return entry.action === 'move'; }).length
          : 0;
        var conflictCount = Array.isArray(dryRun.conflicts) ? dryRun.conflicts.length : 0;
        if (!moveCount) {
          this._status = 'Reorganize dry-run: no files need to move.';
          this._loading = false;
          this._render();
          return;
        }
        if (conflictCount) {
          this._error = 'Reorganize blocked: ' + String(conflictCount) + ' conflict(s) found.';
          this._loading = false;
          this._render();
          return;
        }

        var confirmText = 'Move ' + String(moveCount) + ' file(s) into:\n' + String(dryRun.target_folder || '(unknown)') + '\n\nContinue?';
        if (!window.confirm(confirmText)) {
          this._loading = false;
          this._status = 'Reorganize cancelled.';
          this._render();
          return;
        }

        var executed = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_reorganize_working_group', {
          group_id: group.id,
          execute: true,
        });
        this._status = 'Reorganized ' + String(executed.moved_count || 0) + ' file(s).';
        this._selectedPaths = {};
        await this._loadExplorer();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not reorganize group files.';
        this._loading = false;
        this._render();
      }
    }

    async _setGroupPrimaryFile(groupId, filePath) {
      var resolvedGroupId = Number(groupId || 0);
      var resolvedFilePath = String(filePath || '').trim();
      if (!resolvedGroupId || !resolvedFilePath) {
        return;
      }

      this._loading = true;
      this._error = '';
      this._status = '';
      this._render();
      try {
        await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_update_working_group', {
          group_id: resolvedGroupId,
          primary_file_path: resolvedFilePath,
        });
        this._status = 'Primary file updated.';
        await this._loadExplorer();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not set primary file.';
        this._loading = false;
        this._render();
      }
    }

    _setView(nextView) {
      var normalized = String(nextView || '').trim().toLowerCase();
      if (VIEW_OPTIONS.indexOf(normalized) < 0) {
        return;
      }
      if (normalized === this._view) {
        return;
      }
      this._view = normalized;
      this._selectedPaths = {};
      this._selectedGroupId = 0;
      this._loadExplorer();
    }

    _setThumbnailSize(size) {
      var normalized = String(size || '').trim().toLowerCase();
      if (['small', 'medium', 'large'].indexOf(normalized) < 0) {
        return;
      }
      if (normalized === this._thumbnailSize) {
        return;
      }
      this._thumbnailSize = normalized;
      this._render();
    }

    _readFilters() {
      var root = this.shadowRoot;
      if (!root) {
        return;
      }
      var queryNode = root.querySelector('#working-files-query');
      var extensionNode = root.querySelector('#working-files-extension');
      this._query = queryNode ? String(queryNode.value || '').trim() : '';
      this._extension = extensionNode ? String(extensionNode.value || '').trim() : '';
    }

    _handleCatalogDataChanged(event) {
      var detail = event && event.detail && typeof event.detail === 'object' ? event.detail : {};
      var scopes = Array.isArray(detail.scopes) ? detail.scopes : [];
      if (scopes.length && scopes.indexOf('working') < 0 && scopes.indexOf('all') < 0) {
        return;
      }
      var stamp = Number(detail.stamp || 0) || 0;
      if (stamp) {
        this._lastAppliedScopeStamp = stamp;
      }
      this._loadExplorer();
    }

    _isScopeStale() {
      var shared = window.ModelCatalogIntakeShared;
      if (!shared || typeof shared.getModelCatalogScopeStamp !== 'function') {
        return false;
      }
      var latest = shared.getModelCatalogScopeStamp(this._catalogScope || 'working');
      return latest > (Number(this._lastAppliedScopeStamp) || 0);
    }

    _entryPath(entry) {
      return String((entry && (entry.source_path_canonical || entry.file_path || entry.source_path_raw)) || '').trim();
    }

    _entryExtension(entry) {
      return String((entry && entry.file_extension) || extensionFromPath(this._entryPath(entry)) || '').toLowerCase();
    }

    _entryMtime(entry) {
      if (!entry || typeof entry !== 'object') {
        return '';
      }
      if (entry.source_mtime) {
        return String(entry.source_mtime);
      }
      if (entry.source_metadata && entry.source_metadata.source_mtime) {
        return String(entry.source_metadata.source_mtime);
      }
      return '';
    }

    _entrySize(entry) {
      if (!entry || typeof entry !== 'object') {
        return 0;
      }
      var bytes = entry.file_size_bytes;
      if (!Number.isFinite(Number(bytes))) {
        bytes = entry.file_size;
      }
      return Number(bytes || 0);
    }

    _resolveSidecarUrl() {
      if (this._hass && this._hass.states) {
        var baseUrlEntity = this._hass.states['input_text.model_catalog_sidecar_base_url'];
        if (baseUrlEntity && baseUrlEntity.state) {
          return String(baseUrlEntity.state).trim();
        }
      }
      return '';
    }

    _resolvePreviewUrl(candidateUrl) {
      var candidate = String(candidateUrl || '').trim();
      if (!candidate) {
        return '';
      }
      if (!/^\/api\/(working-files|intake)\/preview/i.test(candidate)) {
        return candidate;
      }
      var sidecarBaseUrl = this._resolveSidecarUrl();
      if (!sidecarBaseUrl) {
        return candidate;
      }
      return sidecarBaseUrl.replace(/\/$/, '') + candidate;
    }

    _entryRelativePath(entry, group) {
      var storageRelative = storageRelativePath(this._entryPath(entry)).relative;
      return storageRelative || basename(this._entryPath(entry));
    }

    _entryRelativeDirectory(entry, group) {
      var relPath = this._entryRelativePath(entry, group);
      if (!relPath || relPath.indexOf('/') < 0) {
        return '';
      }
      return dirname(relPath);
    }

    _groupPathFootprint(group) {
      var files = this._groupFiles(group);
      if (!files.length) {
        var inferredStorage = storageRelativePath(group && group.folder_hint ? group.folder_hint : '').storage || 'Unknown';
        return {
          common_prefix: '',
          folder_count: 0,
          file_count: Number(group && group.counts && group.counts.total) || 0,
          storage_label: inferredStorage,
        };
      }
      var relPaths = files.map(function (entry) {
        return storageRelativePath(this._entryPath(entry));
      }, this);
      var relativeOnly = relPaths.map(function (entry) {
        return entry.relative;
      }).filter(Boolean);
      var folderSet = {};
      relPaths.forEach(function (entry) {
        var folder = dirname(entry.relative || '');
        if (folder) {
          folderSet[folder.toLowerCase()] = true;
        }
      });
      var storageCounts = {};
      relPaths.forEach(function (entry) {
        var key = String(entry.storage || 'Unknown');
        storageCounts[key] = Number(storageCounts[key] || 0) + 1;
      });
      var dominantStorage = Object.keys(storageCounts).sort(function (a, b) {
        return storageCounts[b] - storageCounts[a];
      })[0] || 'Unknown';
      return {
        common_prefix: commonPathPrefix(relativeOnly),
        folder_count: Object.keys(folderSet).length,
        file_count: files.length,
        storage_label: dominantStorage,
      };
    }

    _entryThumbnailUrl(entry) {
      var sourceMetadata = entry && entry.source_metadata && typeof entry.source_metadata === 'object'
        ? entry.source_metadata
        : {};
      var candidates = [
        sourceMetadata.thumbnail_url,
        sourceMetadata.preview_url,
        sourceMetadata.image_url,
        sourceMetadata.embedded_thumbnail_url,
        sourceMetadata.thumb_url,
      ];
      for (var i = 0; i < candidates.length; i += 1) {
        var candidate = String(candidates[i] || '').trim();
        if (!candidate) {
          continue;
        }
        if (/^(javascript:|vbscript:)/i.test(candidate)) {
          continue;
        }
        if (/^(https?:|\/|data:|blob:)/i.test(candidate)) {
          return this._resolvePreviewUrl(candidate);
        }
        return this._resolvePreviewUrl('/' + candidate.replace(/^\.?\//, ''));
      }
      var fallbackPath = this._entryPath(entry);
      var fallbackExt = this._entryExtension(entry);
      if (!fallbackPath || !/(\.3mf|\.png|\.jpe?g|\.webp|\.gif|\.svg|\.bmp)$/i.test(fallbackExt)) {
        return '';
      }
      var sidecarBaseUrl = this._resolveSidecarUrl();
      var previewPath = '/api/working-files/preview?path=' + encodeURIComponent(fallbackPath);
      return sidecarBaseUrl ? sidecarBaseUrl.replace(/\/$/, '') + previewPath : previewPath;
    }

    _groupFiles(group) {
      return Array.isArray(group && group.files) ? group.files : [];
    }

    _findGroupById(groupId) {
      var targetId = Number(groupId || 0);
      if (!targetId) {
        return null;
      }
      return this._groups.find(function (group) {
        return Number(group && group.id) === targetId;
      }) || null;
    }

    async _ensureGroupFilesLoaded(groupId) {
      var targetId = Number(groupId || 0);
      if (!targetId || !this._hass) {
        return;
      }
      var group = this._findGroupById(targetId);
      if (!group || group.files_loaded || this._loadingGroupFiles[targetId]) {
        return;
      }
      this._loadingGroupFiles[targetId] = true;
      this._render();
      try {
        var response = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_get_working_group', {
          group_id: targetId,
        });
        var detailGroup = response && response.group && typeof response.group === 'object' ? response.group : null;
        var items = Array.isArray(detailGroup && detailGroup.items) ? detailGroup.items : [];
        group.files = items.map(function (item) {
          var sourcePath = String(item && item.file_path || '');
          return {
            source_path_canonical: sourcePath,
            source_path_raw: sourcePath,
            file_path: sourcePath,
            file_size_bytes: Number(item && item.file_size || 0),
            source_mtime: item && item.updated_at ? item.updated_at : '',
            source_metadata: item && typeof item.source_metadata === 'object' ? item.source_metadata : {},
            launch: item && item.launch ? item.launch : null,
            group_memberships: item && Array.isArray(item.group_memberships) ? item.group_memberships : [],
          };
        });
        group.files_loaded = true;
        if (!group.counts || !Number(group.counts.total)) {
          var modelCount = group.files.filter(function (entry) {
            return this._entryExtension(entry) === '.3mf';
          }, this).length;
          group.counts = {
            total: group.files.length,
            count_3mf: modelCount,
            count_other: Math.max(0, group.files.length - modelCount),
          };
        }
        if (!String(this._groupFolderBrowsePaths[targetId] || '').trim()) {
          this._groupFolderBrowsePaths[targetId] = this._defaultGroupFolderPath(group);
        }
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not load files for this group.';
      } finally {
        this._loadingGroupFiles[targetId] = false;
        this._render();
      }
    }

    _latestGroupFile(group) {
      var files = this._groupFiles(group);
      var latest = null;
      var latestTime = 0;
      files.forEach(function (entry) {
        var date = parseIsoDate(this._entryMtime(entry));
        var stamp = date ? date.getTime() : 0;
        if (stamp > latestTime) {
          latestTime = stamp;
          latest = entry;
        }
      }, this);
      return latest;
    }

    _groupQueueState(group) {
      var candidates = [
        group && group.queue_state,
        group && group.print_queue_state,
        group && group.status,
      ];
      for (var i = 0; i < candidates.length; i += 1) {
        var normalized = normalizeQueueState(candidates[i]);
        if (normalized !== 'none') {
          return normalized;
        }
      }
      return stageToQueueState(group && group.stage);
    }

    _groupIconStyle(group, queueState) {
      var borderColor = queueStateBorderColor(queueState);
      return ''
        + '--queue-border-color:' + borderColor + ';'
        + '--group-icon-bg:' + rgbaFromHex(borderColor, 0.24) + ';'
        + '--group-icon-fg:#f8fafc;'
        + '--group-icon-ring:' + rgbaFromHex(borderColor, 0.52) + ';';
    }

    _defaultGroupFolderPath(group) {
      var footprint = this._groupPathFootprint(group);
      if (Number(footprint.folder_count || 0) === 1 && String(footprint.common_prefix || '').trim()) {
        return String(footprint.common_prefix).trim();
      }
      return '';
    }

    _entryMatchesFolderType(entry, typeFilter) {
      var normalized = String(typeFilter || 'all').trim().toLowerCase();
      var category = this._entryTypeCategory(entry);
      if (!normalized || normalized === 'all') {
        return true;
      }
      if (normalized === 'models') {
        return category === 'models';
      }
      if (normalized === 'images') {
        return category === 'images';
      }
      if (normalized === 'other') {
        return category === 'other';
      }
      return true;
    }

    _entryTypeCategory(entry) {
      var extension = this._entryExtension(entry);
      if (isModelExtension(extension)) {
        return 'models';
      }
      if (isImageExtension(extension)) {
        return 'images';
      }
      return 'other';
    }

    _folderTypeCounts(entries) {
      var counts = {
        all: entries.length,
        models: 0,
        images: 0,
        other: 0,
      };
      entries.forEach(function (entry) {
        var category = this._entryTypeCategory(entry);
        if (category === 'models') {
          counts.models += 1;
        } else if (category === 'images') {
          counts.images += 1;
        } else {
          counts.other += 1;
        }
      }, this);
      return counts;
    }

    _renderFileTypeFilters(groupFiles, groupId, typeFilter) {
      var counts = this._folderTypeCounts(groupFiles);
      return ''
        + '<div class="folder-type-filters inline">'
        + '<button class="type-chip type-all' + (typeFilter === 'all' ? ' active' : '') + '" data-action="set-group-file-type" data-group-id="' + String(groupId) + '" data-file-type="all">All ' + String(counts.all) + '</button>'
        + '<button class="type-chip type-images' + (typeFilter === 'images' ? ' active' : '') + '" data-action="set-group-file-type" data-group-id="' + String(groupId) + '" data-file-type="images">Images ' + String(counts.images) + '</button>'
        + '<button class="type-chip type-models' + (typeFilter === 'models' ? ' active' : '') + '" data-action="set-group-file-type" data-group-id="' + String(groupId) + '" data-file-type="models">Models ' + String(counts.models) + '</button>'
        + '<button class="type-chip type-other' + (typeFilter === 'other' ? ' active' : '') + '" data-action="set-group-file-type" data-group-id="' + String(groupId) + '" data-file-type="other">Other Files ' + String(counts.other) + '</button>'
        + '</div>';
    }

    _normalizeRelativePath(entry, group) {
      return normalizePath(this._entryRelativePath(entry, group) || basename(this._entryPath(entry))).replace(/^\/+/, '');
    }

    _joinFolderPath(parentPath, childName) {
      if (!parentPath) {
        return childName;
      }
      return parentPath + '/' + childName;
    }

    _parentFolderPath(folderPath) {
      var normalized = String(folderPath || '').trim();
      if (!normalized || normalized.indexOf('/') < 0) {
        return '';
      }
      return normalized.slice(0, normalized.lastIndexOf('/'));
    }

    _buildFolderBrowserIndex(groupFiles, group) {
      var index = { '': { folders: {}, files: [] } };
      groupFiles.forEach(function (entry) {
        var rel = this._normalizeRelativePath(entry, group);
        if (!rel) {
          return;
        }
        var parts = rel.split('/').filter(Boolean);
        if (!parts.length) {
          return;
        }
        var currentPath = '';
        for (var i = 0; i < parts.length - 1; i += 1) {
          var folderName = parts[i];
          var nextPath = this._joinFolderPath(currentPath, folderName);
          if (!index[currentPath]) {
            index[currentPath] = { folders: {}, files: [] };
          }
          if (!index[nextPath]) {
            index[nextPath] = { folders: {}, files: [] };
          }
          index[currentPath].folders[folderName] = nextPath;
          currentPath = nextPath;
        }
        if (!index[currentPath]) {
          index[currentPath] = { folders: {}, files: [] };
        }
        index[currentPath].files.push(entry);
      }, this);
      return index;
    }

    _renderFolderExplorer(groupFiles, group, groupId) {
      var typeFilter = String(this._groupFolderTypeFilters[groupId] || 'models');
      var browserIndex = this._buildFolderBrowserIndex(groupFiles, group);
      var currentPath = String(this._groupFolderBrowsePaths[groupId] || '');
      if (!Object.prototype.hasOwnProperty.call(browserIndex, currentPath)) {
        currentPath = this._defaultGroupFolderPath(group);
        if (!Object.prototype.hasOwnProperty.call(browserIndex, currentPath)) {
          currentPath = '';
        }
        this._groupFolderBrowsePaths[groupId] = currentPath;
      }
      var currentNode = browserIndex[currentPath] || { folders: {}, files: [] };
      var folderEntries = Object.keys(currentNode.folders).sort();
      var fileEntries = currentNode.files.filter(function (entry) {
        return this._entryMatchesFolderType(entry, typeFilter);
      }, this);

      var breadcrumbs = '';
      var crumbPath = '';
      var parts = currentPath ? currentPath.split('/').filter(Boolean) : [];
      if (currentPath) {
        breadcrumbs += '<button class="breadcrumb-up" data-action="folder-up" data-group-id="' + String(groupId) + '" title="Up one level" aria-label="Up one level">↑</button><span class="crumb-sep">|</span>';
      }
      breadcrumbs += '<button class="breadcrumb-link' + (parts.length ? '' : ' current') + '" data-action="set-group-folder-path" data-group-id="' + String(groupId) + '" data-folder-path="">Root</button>';
      parts.forEach(function (segment) {
        crumbPath = this._joinFolderPath(crumbPath, segment);
        breadcrumbs += '<span class="crumb-sep">&gt;</span><button class="breadcrumb-link' + (crumbPath === currentPath ? ' current' : '') + '" data-action="set-group-folder-path" data-group-id="' + String(groupId) + '" data-folder-path="' + escapeHtml(crumbPath) + '">' + escapeHtml(segment) + '</button>';
      }, this);

      var folderRows = '';
      if (!folderEntries.length && !fileEntries.length) {
        folderRows = '<div class="state-row">This folder is empty.</div>';
      } else {
        folderRows = '<div class="folder-browser-list">'
          + folderEntries.map(function (folderName) {
            var nextPath = currentNode.folders[folderName];
            var childNode = browserIndex[nextPath] || { folders: {}, files: [] };
            var childCount = childNode.files.length;
            return ''
              + '<button class="browser-row folder" data-action="set-group-folder-path" data-group-id="' + String(groupId) + '" data-folder-path="' + escapeHtml(nextPath) + '">'
              + '<span class="browser-icon">📁</span>'
              + '<span class="browser-name">' + escapeHtml(folderName) + '</span>'
              + '<span class="browser-size">-</span>'
              + '<span class="browser-modified">' + String(Object.keys(childNode.folders).length) + ' folder(s) · ' + String(childCount) + ' file(s)</span>'
              + '</button>';
          }).join('')
          + fileEntries.map(function (entry) {
            var pathValue = this._entryPath(entry);
            var extension = this._entryExtension(entry);
            var thumbnailUrl = this._entryThumbnailUrl(entry);
            var selected = !!this._selectedPaths[pathValue];
            return ''
              + '<div class="browser-row file">'
              + '<span class="browser-icon">'
              + (thumbnailUrl
                ? '<img src="' + escapeHtml(thumbnailUrl) + '" loading="lazy" alt="thumb">'
                : escapeHtml(extensionBadge(extension)))
              + '</span>'
              + '<span class="browser-name">' + escapeHtml(basename(pathValue)) + '</span>'
              + '<span class="browser-size">' + escapeHtml(formatBytes(this._entrySize(entry))) + '</span>'
              + '<span class="browser-modified"><strong>' + escapeHtml(formatRelativeTime(this._entryMtime(entry))) + '</strong><span class="sub">' + escapeHtml(formatDateTime(this._entryMtime(entry))) + '</span></span>'
              + '<span class="browser-actions"><button class="button" data-action="open-file-path" data-path="' + escapeHtml(pathValue) + '">Open</button><label class="selector"><input type="checkbox" data-action="toggle-select-path" data-file-path="' + escapeHtml(pathValue) + '"' + (selected ? ' checked' : '') + '>Select</label></span>'
              + '</div>';
          }, this).join('')
          + '</div>';
      }

      return ''
        + '<div class="folder-explorer">'
        + '<div class="folder-head-row">'
        + '<span class="subtitle">Folder explorer</span>'
        + '</div>'
        + '<div class="folder-breadcrumbs">' + breadcrumbs + '</div>'
        + folderRows
        + '</div>';
    }

    _toggleAllVisibleSelections() {
      var paths = (this._files || []).map(function (entry) {
        return this._entryPath(entry);
      }, this).filter(Boolean);
      if (!paths.length) {
        return;
      }
      var allSelected = paths.every(function (pathValue) {
        return !!this._selectedPaths[pathValue];
      }, this);
      if (allSelected) {
        paths.forEach(function (pathValue) {
          delete this._selectedPaths[pathValue];
        }, this);
      } else {
        paths.forEach(function (pathValue) {
          this._selectedPaths[pathValue] = true;
        }, this);
      }
      this._render();
    }

    _handleClick(event) {
      var target = event.target instanceof Element ? event.target.closest('[data-action]') : null;
      if (!target) {
        return;
      }
      var action = String(target.getAttribute('data-action') || '');
      if (!action) {
        return;
      }

      if (action === 'refresh') {
        this._readFilters();
        this._loadExplorer({ forceReindex: true });
        return;
      }
      if (action === 'apply-filters') {
        this._readFilters();
        this._loadExplorer();
        return;
      }
      if (action === 'set-view') {
        this._setView(String(target.getAttribute('data-view') || 'groups'));
        return;
      }
      if (action === 'set-thumbnail-size') {
        this._setThumbnailSize(String(target.getAttribute('data-size') || 'small'));
        return;
      }
      if (action === 'select-group') {
        this._selectedGroupId = Number(target.getAttribute('data-group-id') || 0);
        this._render();
        return;
      }
      if (action === 'toggle-group-collapsed') {
        var collapseGroupId = Number(target.getAttribute('data-group-id') || 0);
        if (collapseGroupId) {
          var nextCollapsed = !this._collapsedGroups[collapseGroupId];
          this._collapsedGroups[collapseGroupId] = nextCollapsed;
          this._render();
          if (!nextCollapsed) {
            this._ensureGroupFilesLoaded(collapseGroupId);
          }
        }
        return;
      }
      if (action === 'set-group-subview') {
        var subViewGroupId = Number(target.getAttribute('data-group-id') || 0);
        var nextSubView = String(target.getAttribute('data-subview') || 'files');
        if (subViewGroupId) {
          var resolvedSubView = nextSubView === 'folders' ? 'folders' : 'files';
          this._groupSubViews[subViewGroupId] = resolvedSubView;
          if (resolvedSubView === 'folders' && !String(this._groupFolderBrowsePaths[subViewGroupId] || '').trim()) {
            var selectedGroup = this._groups.find(function (candidate) {
              return Number(candidate && candidate.id) === subViewGroupId;
            });
            this._groupFolderBrowsePaths[subViewGroupId] = this._defaultGroupFolderPath(selectedGroup);
          }
          this._render();
        }
        return;
      }
      if (action === 'set-group-file-type') {
        var folderTypeGroupId = Number(target.getAttribute('data-group-id') || 0);
        var nextFolderType = String(target.getAttribute('data-file-type') || 'models').trim().toLowerCase();
        if (folderTypeGroupId) {
          this._groupFolderTypeFilters[folderTypeGroupId] = nextFolderType || 'models';
          this._render();
        }
        return;
      }
      if (action === 'set-group-folder-path') {
        var folderPathGroupId = Number(target.getAttribute('data-group-id') || 0);
        var nextFolderPath = String(target.getAttribute('data-folder-path') || '').trim();
        if (folderPathGroupId >= 0) {
          this._groupFolderBrowsePaths[folderPathGroupId] = nextFolderPath;
          this._render();
        }
        return;
      }
      if (action === 'folder-up') {
        var upFolderGroupId = Number(target.getAttribute('data-group-id') || 0);
        if (upFolderGroupId >= 0) {
          this._groupFolderBrowsePaths[upFolderGroupId] = this._parentFolderPath(this._groupFolderBrowsePaths[upFolderGroupId] || '');
          this._render();
        }
        return;
      }
      if (action === 'open-file-path') {
        this._openLocalPath(String(target.getAttribute('data-path') || ''));
        return;
      }
      if (action === 'toggle-select-path') {
        this._togglePathSelection(String(target.getAttribute('data-file-path') || ''));
        return;
      }
      if (action === 'toggle-select-all-visible') {
        this._toggleAllVisibleSelections();
        return;
      }
      if (action === 'create-group-from-selection') {
        this._createGroupFromSelection();
        return;
      }
      if (action === 'add-selection-to-group') {
        this._addSelectionToExistingGroup();
        return;
      }
      if (action === 'remove-selection-from-group') {
        this._removeSelectionFromSelectedGroup();
        return;
      }
      if (action === 'remove-selection-from-row-group') {
        var removeGroupId = Number(target.getAttribute('data-group-id') || 0);
        if (removeGroupId) {
          this._selectedGroupId = removeGroupId;
          this._removeSelectionFromSelectedGroup();
        }
        return;
      }
      if (action === 'reorganize-selected-group') {
        this._runReorganize();
        return;
      }
      if (action === 'reorganize-group') {
        this._runReorganize(Number(target.getAttribute('data-group-id') || 0));
        return;
      }
      if (action === 'set-group-primary-file') {
        this._setGroupPrimaryFile(
          Number(target.getAttribute('data-group-id') || 0),
          String(target.getAttribute('data-file-path') || ''),
        );
        return;
      }
      if (action === 'open-group-folder') {
        this._openLocalPath(String(target.getAttribute('data-path') || ''));
      }
    }

    _renderGroupsPane() {
      if (!this._groups.length) {
        return '<div class="state-row">No working groups are available.</div>';
      }
      return '<div class="groups">' + this._groups.map(function (group) {
        var groupId = Number(group.id || 0);
        var active = groupId === Number(this._selectedGroupId || 0);
        var collapsed = !!this._collapsedGroups[groupId];
        var subView = this._groupSubViews[groupId] === 'folders' ? 'folders' : 'files';
        var counts = group.counts || {};
        var stageClass = stageClassName(group.stage);
        var queueState = this._groupQueueState(group);
        var files = this._groupFiles(group);
        var pathFootprint = this._groupPathFootprint(group);
        var typeFilter = String(this._groupFolderTypeFilters[groupId] || 'models');
        var visibleFiles = files.filter(function (entry) {
          return this._entryMatchesFolderType(entry, typeFilter);
        }, this);
        var latest = this._latestGroupFile(group);
        var latestName = latest ? basename(this._entryPath(latest)) : '';
        var groupInitials = initialsFromTitle(group.title || 'WG');
        var groupStyle = this._groupIconStyle(group, queueState);
        var modelRowsHtml = '';
        if (!group.files_loaded && this._loadingGroupFiles[groupId]) {
          modelRowsHtml = '<div class="state-row">Loading group files...</div>';
        } else if (!group.files_loaded) {
          modelRowsHtml = '<div class="state-row">Expand to load files for this group.</div>';
        } else if (!visibleFiles.length) {
          modelRowsHtml = '<div class="state-row">No files match this type filter.</div>';
        } else {
          modelRowsHtml = '<div class="file-list">' + visibleFiles.map(function (entry) {
            var pathValue = this._entryPath(entry);
            var isPrimary = normalizePath(pathValue).toLowerCase() === normalizePath(group.primary_file_path || '').toLowerCase();
            var ext = this._entryExtension(entry);
            var extClass = 'x-' + ext.replace(/^\./, '');
            var selected = !!this._selectedPaths[pathValue];
            var primaryLabel = isPrimary ? 'Primary' : 'Make primary';
            return ''
              + '<div class="file-row' + (isPrimary ? ' primary' : '') + '">' 
              + '<span class="file-thumb">'
              + (this._entryThumbnailUrl(entry)
                ? '<img src="' + escapeHtml(this._entryThumbnailUrl(entry)) + '" loading="lazy" alt="thumb">'
                : '<span class="ext-badge ' + escapeHtml(extClass) + '">' + escapeHtml(extensionBadge(ext)) + '</span>')
              + '</span>'
              + '<span class="file-main"><div class="file-name">' + escapeHtml(basename(pathValue)) + '</div><div class="file-path">' + escapeHtml(this._entryRelativeDirectory(entry, group)) + '</div></span>'
              + '<span class="file-size">' + escapeHtml(formatBytes(this._entrySize(entry))) + '</span>'
              + '<span class="file-modified"><strong>' + escapeHtml(formatRelativeTime(this._entryMtime(entry))) + '</strong><span class="sub">' + escapeHtml(formatDateTime(this._entryMtime(entry))) + '</span></span>'
              + '<span class="primary-slot"><button class="primary-action' + (isPrimary ? ' is-current' : '') + '" data-action="set-group-primary-file" data-group-id="' + String(groupId) + '" data-file-path="' + escapeHtml(pathValue) + '"' + (isPrimary ? ' aria-current="true"' : '') + '>' + escapeHtml(primaryLabel) + '</button></span>'
              + '<span class="selector-slot"><label class="selector"><input type="checkbox" data-action="toggle-select-path" data-file-path="' + escapeHtml(pathValue) + '"' + (selected ? ' checked' : '') + '>Select</label></span>'
              + '</div>';
          }, this).join('') + '</div>';
        }

        var stripBody = subView === 'folders'
          ? this._renderFolderExplorer(files, group, groupId)
          : modelRowsHtml;

        return ''
          + '<article class="group-row stage-' + escapeHtml(stageClass) + (active ? ' active' : '') + '" style="' + escapeHtml(groupStyle) + '">'
          + '  <div class="group-header">'
          + '    <div class="thumb" title="' + escapeHtml(formatStage(group.stage || 'draft')) + '">' + escapeHtml(groupInitials) + '</div>'
          + '    <div>'
          + '      <div class="group-title" data-action="select-group" data-group-id="' + String(groupId) + '">' + escapeHtml(group.title || 'Untitled Group') + '</div>'
          + '      <div class="folder-hint">' + escapeHtml(pathFootprint.common_prefix || storageRelativePath(group.folder_hint || '').relative || group.notes || '') + '</div>'
          + '      <div class="path-summary"><span><strong>Storage:</strong> ' + escapeHtml(pathFootprint.storage_label) + '</span><span><strong>Files:</strong> ' + String(pathFootprint.file_count) + '</span><span><strong>Folders:</strong> ' + String(pathFootprint.folder_count) + '</span></div>'
          + '      <div class="group-meta"><span>Model ' + String(counts.count_3mf || 0) + '</span><span>Other ' + String(counts.count_other || 0) + '</span><span>Total ' + String(counts.total || 0) + '</span><span class="stage-chip ' + escapeHtml(stageClass) + '">' + escapeHtml(formatStage(group.stage || 'draft')) + '</span></div>'
          + '    </div>'
          + '    <div class="group-right"><span class="updated">Latest file change' + (latestName ? ' · ' + escapeHtml(latestName) : '') + '</span><span class="updated"><strong>' + escapeHtml(formatRelativeTime(this._entryMtime(latest || {}))) + '</strong> · ' + escapeHtml(formatDateTime(this._entryMtime(latest || {}))) + '</span><button class="expander" data-action="toggle-group-collapsed" data-group-id="' + String(groupId) + '">' + (collapsed ? '▸' : '▾') + '</button></div>'
          + '  </div>'
          + (collapsed ? '' : ''
            + '<div class="strip">'
            + '  <div class="strip-head"><span class="strip-head-left"><span class="strip-title">Working group files</span>' + this._renderFileTypeFilters(files, groupId, typeFilter) + '</span><span class="subview-toggle"><button data-action="set-group-subview" data-group-id="' + String(groupId) + '" data-subview="files" class="' + (subView === 'files' ? 'active' : '') + '">Files</button><button data-action="set-group-subview" data-group-id="' + String(groupId) + '" data-subview="folders" class="' + (subView === 'folders' ? 'active' : '') + '">Folders</button></span></div>'
            + stripBody
            + '</div>'
            + '<div class="group-actions"><button class="button" data-action="open-group-folder" data-path="' + escapeHtml(group.folder_hint || '') + '">Open Folder</button><button class="button primary" data-action="reorganize-group" data-group-id="' + String(groupId) + '">Reorganize</button><button class="button warn" data-action="remove-selection-from-row-group" data-group-id="' + String(groupId) + '">Remove Selected</button><span class="spacer"></span><label class="selector"><input type="radio" name="working-group-active" data-action="select-group" data-group-id="' + String(groupId) + '"' + (active ? ' checked' : '') + '>Active group</label></div>')
          + '</article>';
      }, this).join('') + '</div>';
    }

    _renderGroupsView() {
      var selectedCount = this._selectedPathList().length;
      return ''
        + '<section class="section">'
        + '  <div class="title-row"><div><div class="title">Groups</div></div><div class="status">Selected files ' + String(selectedCount) + '</div></div>'
        + (selectedCount
          ? '<div class="bulk-bar"><span>' + String(selectedCount) + ' file(s) selected</span><button class="button primary" data-action="add-selection-to-group">Add To Group</button><button class="button" data-action="create-group-from-selection">Create Group</button><span class="spacer"></span><button class="button warn" data-action="remove-selection-from-group">Remove From Active Group</button></div>'
          : '')
        + this._renderGroupsPane()
        + '</section>';
    }

    _renderAllOrUngrouped() {
      var selectedCount = this._selectedPathList().length;
      var allVisiblePaths = (this._files || []).map(function (entry) {
        return this._entryPath(entry);
      }, this).filter(Boolean);
      var allChecked = !!allVisiblePaths.length && allVisiblePaths.every(function (pathValue) {
        return !!this._selectedPaths[pathValue];
      }, this);
      var rowsHtml = '';
      if (!this._files.length) {
        rowsHtml = '<div class="state-row">No files in this view.</div>';
      } else {
        rowsHtml = ''
          + '<div class="files-table"><table><thead><tr>'
          + '<th><input type="checkbox" data-action="toggle-select-all-visible"' + (allChecked ? ' checked' : '') + '></th>'
          + '<th>Type</th>'
          + '<th>Name & folder</th>'
          + '<th class="right">Size</th>'
          + '<th class="right">Modified</th>'
          + '<th>Groups</th>'
          + '<th>Validation</th>'
          + '</tr></thead><tbody>'
          + this._files.map(function (entry) {
            var pathValue = this._entryPath(entry);
            var ext = this._entryExtension(entry);
            var extClass = 'x-' + ext.replace(/^\./, '');
            var memberships = Array.isArray(entry.group_memberships) ? entry.group_memberships : [];
            var selected = !!this._selectedPaths[pathValue];
            var warningCount = Array.isArray(entry.warnings) ? entry.warnings.length : 0;
            var validationState = String(entry.validation_state || 'clean').toLowerCase();
            return ''
              + '<tr' + (selected ? ' class="selected"' : '') + '>'
              + '<td><input type="checkbox" data-action="toggle-select-path" data-file-path="' + escapeHtml(pathValue) + '"' + (selected ? ' checked' : '') + '></td>'
              + '<td><span class="ext-badge ' + escapeHtml(extClass) + '">' + escapeHtml(extensionBadge(ext)) + '</span></td>'
              + '<td><div class="row-name"><div class="row-name-text"><div class="row-name-title">' + escapeHtml(entry.file_name_raw || basename(pathValue)) + '</div><div class="row-name-sub">' + escapeHtml(dirname(storageRelativePath(pathValue).relative || pathValue)) + '</div></div></div></td>'
              + '<td class="right">' + escapeHtml(formatBytes(this._entrySize(entry))) + '</td>'
              + '<td class="right">' + escapeHtml(formatRelativeTime(this._entryMtime(entry))) + '<div class="row-name-sub">' + escapeHtml(formatDateTime(this._entryMtime(entry))) + '</div></td>'
              + '<td><div class="group-chips">'
              + (memberships.length
                ? memberships.map(function (membership) {
                  return '<span class="group-chip">' + escapeHtml(membership.group_title || ('Group ' + String(membership.group_id || ''))) + '</span>';
                }).join('')
                : '<span class="group-chip empty">Ungrouped</span>')
              + '</div></td>'
              + '<td><span class="validation' + ((validationState !== 'clean' || warningCount) ? ' warn' : '') + '">' + ((validationState !== 'clean' || warningCount) ? (String(warningCount || 1) + ' warning') : 'Clean') + '</span></td>'
              + '</tr>';
          }, this).join('')
          + '</tbody></table></div>';
      }

      return ''
        + '<section class="section">'
        + '  <div class="title-row"><div><div class="title">' + (this._view === 'all' ? 'All Files' : 'Ungrouped Files') + '</div><div class="subtitle">Table-first triage with group membership visibility (issues #1076 and #1132 alignment).</div></div><div class="status">Selected ' + String(selectedCount) + '</div></div>'
        + '  <div class="button-row"><button class="button primary" data-action="create-group-from-selection"' + (selectedCount ? '' : ' disabled') + '>Create Group</button><button class="button" data-action="add-selection-to-group"' + (selectedCount ? '' : ' disabled') + '>Add To Group</button></div>'
        + rowsHtml
        + '</section>';
    }

    _renderLoadingState() {
      var phase = String(this._loadingPhase || 'Loading Working Files...');
      return ''
        + '<section class="section loading-shell">'
        + '  <div class="loading-title">' + escapeHtml(phase) + '</div>'
        + '  <div class="skeleton-list">'
        + '    <div class="skeleton-row"></div>'
        + '    <div class="skeleton-row"></div>'
        + '    <div class="skeleton-row"></div>'
        + '    <div class="skeleton-row"></div>'
        + '  </div>'
        + '</section>';
    }

    _render() {
      if (!this.shadowRoot || !this._config) {
        return;
      }

      var summary = this._summary || {};
      var bodyHtml = '';
      var hasRenderableData = (this._view === 'groups')
        ? !!(Array.isArray(this._groups) && this._groups.length)
        : !!(Array.isArray(this._files) && this._files.length);
      if (this._loading && !hasRenderableData) {
        bodyHtml = this._renderLoadingState();
      } else if (this._error) {
        bodyHtml = '<div class="state-row">' + escapeHtml(this._error) + '</div>';
      } else if (this._view === 'groups') {
        bodyHtml = this._renderGroupsView();
      } else {
        bodyHtml = this._renderAllOrUngrouped();
      }

      this.shadowRoot.innerHTML = ''
        + '<style>' + sharedStyles + '</style>'
        + '<ha-card>'
        + '  <div class="shell thumb-' + escapeHtml(this._thumbnailSize || 'small') + '">'
        + '    <div class="title-row">'
        + '      <div>'
        + '        <div class="title">' + escapeHtml(this._config.title) + '</div>'
        + '        <div class="subtitle">Root-first Working Files explorer with Groups, All Files, and Ungrouped views.</div>'
        + '      </div>'
        + '      <div class="status">All ' + String(summary.all_count || 0) + ' / Ungrouped ' + String(summary.ungrouped_count || 0) + ' / Groups ' + String(summary.group_count || this._groups.length || 0) + '</div>'
        + '    </div>'
        + '    ' + (this._status ? '<div class="status">' + escapeHtml(this._status) + '</div>' : '')
        + '    ' + (this._error ? '<div class="status error">' + escapeHtml(this._error) + '</div>' : '')
        + '    <section class="toolbar">'
        + '      <div class="title-row">'
        + '        <div class="tab-row">'
        + '          <button class="tab ' + (this._view === 'groups' ? 'active' : '') + '" data-action="set-view" data-view="groups">Groups</button>'
        + '          <button class="tab ' + (this._view === 'all' ? 'active' : '') + '" data-action="set-view" data-view="all">All Files</button>'
        + '          <button class="tab ' + (this._view === 'ungrouped' ? 'active' : '') + '" data-action="set-view" data-view="ungrouped">Ungrouped</button>'
        + '        </div>'
        + '        <div class="button-row"><span class="thumb-size-toggle"><button data-action="set-thumbnail-size" data-size="small" class="' + (this._thumbnailSize === 'small' ? 'active' : '') + '">Small</button><button data-action="set-thumbnail-size" data-size="medium" class="' + (this._thumbnailSize === 'medium' ? 'active' : '') + '">Medium</button><button data-action="set-thumbnail-size" data-size="large" class="' + (this._thumbnailSize === 'large' ? 'active' : '') + '">Large</button></span><button class="button" data-action="refresh">Refresh</button></div>'
        + '      </div>'
        + '      <div class="toolbar-row">'
        + '        <div class="field grow"><label for="working-files-query">Search</label><input id="working-files-query" class="input" type="text" value="' + escapeHtml(this._query) + '" placeholder="name, path, notes"></div>'
        + '        <div class="field"><label for="working-files-extension">Extension</label><select id="working-files-extension" class="select"><option value="">All</option><option value=".3mf"' + (this._extension === '.3mf' ? ' selected' : '') + '>3MF</option><option value=".stl"' + (this._extension === '.stl' ? ' selected' : '') + '>STL</option><option value=".step"' + (this._extension === '.step' ? ' selected' : '') + '>STEP</option><option value=".obj"' + (this._extension === '.obj' ? ' selected' : '') + '>OBJ</option><option value=".zip"' + (this._extension === '.zip' ? ' selected' : '') + '>ZIP</option></select></div>'
        + '        <div class="button-row"><button class="button primary" data-action="apply-filters">Apply</button></div>'
        + '      </div>'
        + '    </section>'
        + bodyHtml
        + '  </div>'
        + '</ha-card>';
    }
  }

  if (!customElements.get('model-catalog-working-files-explorer-card')) {
    customElements.define('model-catalog-working-files-explorer-card', ModelCatalogWorkingFilesExplorerCard);
  }
})();
