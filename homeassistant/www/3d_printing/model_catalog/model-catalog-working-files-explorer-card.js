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

  function formatCountLabel(label, count) {
    return String(label || "") + " \u00b7 " + String(Number(count || 0));
  }

  function isSlicerLaunchableExtension(extension) {
    return String(extension || '').toLowerCase() === '.3mf';
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

  function absoluteUrl(baseUrl, pathValue) {
    var pathText = String(pathValue || '').trim();
    if (!pathText) {
      return '';
    }
    if (/^https?:\/\//i.test(pathText)) {
      return pathText;
    }
    var base = String(baseUrl || '').trim();
    if (!base) {
      return pathText;
    }
    return base.replace(/\/$/, '') + (pathText.charAt(0) === '/' ? pathText : '/' + pathText);
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
    + '.button.compact{min-height:30px;padding:0 10px;font-size:11px;}'
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
    + '.group-header{display:grid;grid-template-columns:52px minmax(0,1fr) auto;gap:12px;align-items:start;cursor:pointer;}'
    + '.thumb{width:52px;height:52px;border-radius:10px;border:1px solid var(--group-icon-ring);display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:900;letter-spacing:.04em;color:var(--group-icon-fg);background:var(--group-icon-bg);text-transform:uppercase;}'
    + '.group-title-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}'
    + '.group-title{font-size:14px;font-weight:700;line-height:1.3;overflow-wrap:anywhere;cursor:pointer;}'
    + '.folder-hint{font-size:11px;color:var(--secondary-text-color);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
    + '.path-summary{margin-top:6px;font-size:10px;color:var(--secondary-text-color);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;display:flex;gap:8px;flex-wrap:wrap;}'
    + '.summary-row{margin-top:6px;display:flex;align-items:center;justify-content:flex-start;gap:10px;flex-wrap:wrap;}'
    + '.path-summary strong{color:#93c5fd;font-weight:700;}'
    + '.stage-chip{display:inline-flex;align-items:center;padding:2px 8px;border-radius:999px;border:1px solid rgba(148,163,184,0.3);font-size:10px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;background:rgba(100,116,139,0.2);color:#dbe7f2;box-shadow:inset 0 0 0 1px rgba(255,255,255,0.03);}'
    + '.stage-chip.draft{border-color:rgba(148,163,184,0.44);background:rgba(71,85,105,0.34);color:#e2e8f0;}'
    + '.stage-chip.in_progress{border-color:rgba(252,211,77,0.5);color:#fef3c7;background:rgba(245,158,11,0.32);}'
    + '.stage-chip.ready_to_publish{border-color:rgba(134,239,172,0.5);color:#dcfce7;background:rgba(46,125,50,0.36);}'
    + '.group-right{text-align:right;display:flex;align-items:center;gap:10px;justify-content:flex-end;}'
    + '.group-right-meta{display:grid;gap:6px;justify-items:end;}'
    + '.updated{font-size:11px;color:var(--secondary-text-color);}'
    + '.updated strong{color:var(--primary-text-color);}'
    + '.expander{border:1px solid rgba(148,163,184,0.26);background:rgba(15,23,42,0.3);color:#cbd5e1;border-radius:10px;min-width:40px;height:40px;cursor:pointer;font-size:18px;font-weight:900;line-height:1;display:inline-flex;align-items:center;justify-content:center;}'
    + '.strip{margin-top:10px;border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.24);border-radius:12px;padding:10px;display:grid;gap:8px;}'
    + '.strip-head{display:flex;align-items:center;justify-content:space-between;gap:10px;color:var(--secondary-text-color);}'
    + '.strip-head-left{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0;}'
    + '.strip-title{font-size:10px;text-transform:uppercase;letter-spacing:.06em;font-weight:700;}'
    + '.subview-toggle{display:inline-flex;padding:2px;border:1px solid rgba(148,163,184,0.24);border-radius:999px;background:rgba(15,23,42,0.35);}'
    + '.subview-toggle button{display:inline-flex;align-items:center;justify-content:center;min-height:24px;border:0;background:transparent;color:var(--secondary-text-color);font-size:10px;padding:4px 10px;border-radius:999px;cursor:pointer;text-transform:uppercase;line-height:1;}'
    + '.subview-toggle button.active{background:rgba(94,234,212,0.18);color:#99f6e4;}'
    + '.folder-type-filters.inline{display:inline-flex;gap:6px;flex-wrap:wrap;align-items:center;}'
    + '.type-chip{display:inline-flex;align-items:center;justify-content:center;min-height:24px;padding:4px 10px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(148,163,184,0.08);color:#cbd5e1;font-size:10px;font-weight:700;cursor:pointer;text-transform:uppercase;line-height:1;}'
    + '.type-chip.active{box-shadow:inset 0 0 0 1px rgba(255,255,255,0.04);}'
    + '.type-chip.type-all:hover,.type-chip.type-all:focus-visible,.type-chip.type-all.active{background:rgba(167,139,250,0.20);border-color:rgba(196,181,253,0.34);color:#ddd6fe;outline:none;}'
    + '.type-chip.type-models:hover,.type-chip.type-models:focus-visible,.type-chip.type-models.active{background:rgba(0,137,123,0.16);border-color:rgba(125,211,200,0.30);color:#7dd3c8;outline:none;}'
    + '.type-chip.type-images:hover,.type-chip.type-images:focus-visible,.type-chip.type-images.active{background:rgba(37,99,235,0.16);border-color:rgba(147,197,253,0.34);color:#93c5fd;outline:none;}'
    + '.type-chip.type-other:hover,.type-chip.type-other:focus-visible,.type-chip.type-other.active{background:rgba(245,158,11,0.16);border-color:rgba(252,211,77,0.34);color:#fcd34d;outline:none;}'
    + '.file-list{display:grid;gap:4px;}'
    + '.file-row{display:grid;grid-template-columns:var(--file-thumb-col,38px) minmax(0,1fr)92px 192px 96px 136px 84px;gap:8px;align-items:center;padding:6px;border-radius:8px;}'
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
    + '.copy-slot{display:flex;justify-content:center;}'
    + '.selector-slot{display:flex;justify-content:flex-end;}'
    + '.primary-pill{display:inline-flex;padding:2px 7px;border-radius:999px;background:rgba(245,194,66,0.15);border:1px solid rgba(245,194,66,0.33);color:#f5c242;font-size:10px;font-weight:700;}'
    + '.primary-action{min-width:94px;min-height:28px;padding:0 10px;border-radius:999px;border:1px dashed rgba(148,163,184,0.32);background:rgba(15,23,42,0.24);color:#94a3b8;font-size:11px;font-weight:700;cursor:pointer;}'
    + '.primary-action:hover,.primary-action:focus-visible{border-style:solid;border-color:rgba(96,165,250,0.46);background:rgba(96,165,250,0.14);color:#dbeafe;outline:none;}'
    + '.primary-action.is-current{border-style:solid;border-color:rgba(245,194,66,0.42);background:rgba(245,194,66,0.16);color:#f5c242;cursor:default;}'
    + '.primary-action.is-current:hover,.primary-action.is-current:focus-visible{background:rgba(245,194,66,0.16);color:#f5c242;}'
    + '.file-action-split{position:relative;display:inline-flex;align-items:center;justify-content:flex-end;}'
    + '.file-action-main{min-width:92px;border-top-right-radius:0;border-bottom-right-radius:0;padding:0 12px;}'
    + '.file-action-toggle{min-width:32px;padding:0 8px;border-top-left-radius:0;border-bottom-left-radius:0;margin-left:-1px;font-size:10px;line-height:1;}'
    + '.file-action-menu{position:absolute;top:calc(100% + 6px);right:0;display:grid;gap:4px;min-width:184px;padding:8px;border-radius:12px;border:1px solid rgba(148,163,184,0.22);background:rgba(15,23,42,0.98);box-shadow:0 12px 24px rgba(2,6,23,0.42);z-index:20;}'
    + '.file-action-menu .button{justify-content:flex-start;text-align:left;}'
    + '.selector{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:var(--secondary-text-color);}'
    + '.group-actions{display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding-top:8px;border-top:1px dashed rgba(148,163,184,0.2);}'
    + '.group-actions .spacer{flex:1;}'
    + '.dialog-scrim{position:fixed;inset:0;background:rgba(2,6,23,0.72);display:flex;align-items:center;justify-content:center;padding:18px;z-index:40;}'
    + '.dialog{width:min(720px,100%);max-height:min(82vh,900px);overflow:auto;border-radius:20px;border:1px solid rgba(148,163,184,0.24);background:linear-gradient(180deg, rgba(15,23,42,0.98) 0%, rgba(15,23,42,0.96) 100%);box-shadow:0 24px 80px rgba(2,6,23,0.55);padding:18px;display:grid;gap:14px;}'
    + '.dialog-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;}'
    + '.dialog-title{font-size:18px;font-weight:800;line-height:1.2;}'
    + '.dialog-copy{font-size:12px;color:var(--secondary-text-color);line-height:1.5;}'
    + '.dialog-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;}'
    + '.dialog-kpi{padding:10px 12px;border-radius:14px;border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.46);display:grid;gap:4px;}'
    + '.dialog-kpi-label{font-size:10px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:var(--secondary-text-color);}'
    + '.dialog-kpi-value{font-size:18px;font-weight:800;line-height:1.1;}'
    + '.dialog-card{padding:12px;border-radius:14px;border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.38);display:grid;gap:8px;}'
    + '.dialog-card.warn{border-color:rgba(245,158,11,0.34);background:rgba(120,53,15,0.18);}'
    + '.dialog-card.error{border-color:rgba(248,113,113,0.34);background:rgba(127,29,29,0.18);}'
    + '.dialog-card.success{border-color:rgba(52,211,153,0.34);background:rgba(6,78,59,0.18);}'
    + '.dialog-label{font-size:10px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:var(--secondary-text-color);}'
    + '.dialog-path{font-size:12px;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;word-break:break-word;}'
    + '.dialog-list{display:grid;gap:8px;max-height:220px;overflow:auto;}'
    + '.dialog-list-item{padding:10px 12px;border-radius:12px;border:1px solid rgba(148,163,184,0.14);background:rgba(255,255,255,0.03);display:grid;gap:4px;}'
    + '.dialog-list-top{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;}'
    + '.dialog-list-title{font-size:12px;font-weight:700;word-break:break-word;}'
    + '.dialog-list-meta{font-size:10px;color:var(--secondary-text-color);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;word-break:break-word;}'
    + '.dialog-list-note{font-size:11px;color:var(--secondary-text-color);line-height:1.4;}'
    + '.dialog-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap;}'
    + '.dialog-spinner{display:inline-flex;align-items:center;gap:8px;font-size:12px;color:var(--secondary-text-color);}'
    + '.dialog-spinner::before{content:"";width:14px;height:14px;border-radius:50%;border:2px solid rgba(148,163,184,0.24);border-top-color:#99f6e4;animation:mcwf-spin .8s linear infinite;}'
    + '@keyframes mcwf-spin{to{transform:rotate(360deg);}}'
    + '.section-head{padding-bottom:8px;}'
    + '.other-strip{border:1px dashed rgba(148,163,184,0.26);border-radius:10px;padding:8px;display:grid;gap:6px;}'
    + '.other-head{display:flex;justify-content:space-between;font-size:10px;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.06em;}'
    + '.other-chips{display:flex;gap:5px;flex-wrap:wrap;}'
    + '.other-chip{display:inline-flex;align-items:center;padding:3px 8px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);font-size:10px;color:var(--secondary-text-color);}'
    + '.folder-explorer{display:grid;gap:8px;}'
    + '.folder-head-row{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;}'
    + '.folder-type-filters{display:flex;gap:6px;flex-wrap:wrap;}'
    + '.folder-breadcrumbs{display:flex;align-items:center;gap:2px;flex-wrap:wrap;}'
    + '.breadcrumb-up{appearance:none;border:0;background:transparent;padding:0;margin:0;border-radius:6px;color:var(--secondary-text-color);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;}'
    + '.breadcrumb-up:hover,.breadcrumb-up:focus-visible{background:rgba(148,163,184,0.18);color:var(--primary-text-color);outline:none;}'
    + '.breadcrumb-up ha-icon{--mdc-icon-size:17px;}'
    + '.breadcrumb-link{appearance:none;border:0;background:transparent;padding:2px 8px;margin:0;border-radius:6px;color:var(--secondary-text-color);font-size:12px;cursor:pointer;line-height:1.4;min-height:24px;display:inline-flex;align-items:center;}'
    + '.breadcrumb-link:hover,.breadcrumb-link:focus-visible{background:rgba(148,163,184,0.18);color:var(--primary-text-color);outline:none;}'
    + '.breadcrumb-link.current{font-weight:700;color:var(--primary-text-color);}'
    + '.crumb-sep{display:inline-flex;align-items:center;justify-content:center;width:14px;height:24px;color:var(--secondary-text-color);opacity:.8;}'
    + '.crumb-sep ha-icon{--mdc-icon-size:14px;}'
    + '.folder-browser-list{display:grid;gap:6px;}'
    + '.browser-row{display:grid;grid-template-columns:var(--browser-icon-col,46px) minmax(0,1fr) 92px 192px auto;gap:8px;align-items:center;padding:8px 10px;border-radius:10px;border:1px solid rgba(148,163,184,0.2);background:rgba(15,23,42,0.24);text-align:left;}'
    + '.browser-row.folder{cursor:pointer;background:rgba(96,165,250,0.1);border-color:rgba(96,165,250,0.26);}'
    + '.browser-row.folder{grid-template-columns:var(--browser-icon-col,46px) minmax(0,1fr) auto;}'
    + '.browser-row.folder:hover{background:rgba(96,165,250,0.16);border-color:rgba(96,165,250,0.36);}'
    + '.browser-row.file:hover{background:rgba(255,255,255,0.03);}'
    + '.browser-icon{display:flex;align-items:center;justify-content:center;width:var(--browser-icon-width,42px);height:var(--browser-icon-height,28px);border-radius:8px;border:1px solid rgba(148,163,184,0.24);font-size:10px;font-weight:800;color:var(--secondary-text-color);background:rgba(255,255,255,0.04);}'
    + '.browser-icon img{width:100%;height:100%;object-fit:cover;display:block;}'
    + '.browser-row.folder .browser-icon{font-size:var(--browser-folder-icon-font,16px);line-height:1;color:#bfdbfe;border-color:rgba(96,165,250,0.34);background:rgba(96,165,250,0.14);}'
    + '.browser-name{min-width:0;font-size:12px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;justify-self:start;text-align:left;}'
    + '.browser-name .name-main{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
    + '.browser-name .sub{display:block;font-size:10px;color:var(--secondary-text-color);opacity:.9;font-weight:400;line-height:1.25;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
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
    + '.shell.thumb-small{--thumb-size:34px;--file-thumb-col:38px;--browser-icon-col:46px;--browser-icon-width:42px;--browser-icon-height:28px;--browser-folder-icon-font:16px;--thumb-badge-width:22px;--thumb-badge-height:20px;--thumb-badge-font:9px;}'
    + '.shell.thumb-medium{--thumb-size:58px;--file-thumb-col:62px;--browser-icon-col:66px;--browser-icon-width:62px;--browser-icon-height:42px;--browser-folder-icon-font:24px;--thumb-badge-width:34px;--thumb-badge-height:30px;--thumb-badge-font:12px;}'
    + '.shell.thumb-large{--thumb-size:116px;--file-thumb-col:124px;--browser-icon-col:132px;--browser-icon-width:124px;--browser-icon-height:84px;--browser-folder-icon-font:46px;--thumb-badge-width:68px;--thumb-badge-height:60px;--thumb-badge-font:20px;}'
    + '@media (max-width: 980px){.group-header{grid-template-columns:44px minmax(0,1fr);}.group-right{grid-column:1 / -1;justify-items:start;text-align:left;}.file-row{grid-template-columns:38px minmax(0,1fr)136px;}.file-row .file-size,.file-row .file-modified,.file-row .primary-slot,.file-row .selector-slot{display:none;}.browser-row{grid-template-columns:46px minmax(0,1fr)auto;}.browser-row .browser-size,.browser-row .browser-modified{display:none;}}';

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
      this._fileActionMenuPath = '';
      this._reorganizeDialog = null;
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
      this._status = '';
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
      this._launchLocalHelperAction('open_local', pathValue);
    }

    _openFolderPath(pathValue) {
      this._launchLocalHelperAction('open_folder', pathValue);
    }

    _openExplorer(pathValue) {
      this._openFolderPath(dirname(pathValue));
    }

    _toggleFileActionMenu(pathValue) {
      var normalized = String(pathValue || '').trim();
      if (!normalized) {
        return;
      }
      this._fileActionMenuPath = this._fileActionMenuPath === normalized ? '' : normalized;
      this._render();
    }

    _renderFileActionSplit(pathValue, extension, windowsPath) {
      var normalizedPath = String(pathValue || '').trim();
      if (!normalizedPath) {
        return '';
      }
      var menuOpen = this._fileActionMenuPath === normalizedPath;
      return ''
        + '<span class="file-action-split">'
        + '<button class="button file-action-main" data-action="open-file-path" data-path="' + escapeHtml(normalizedPath) + '">Open</button>'
        + '<button class="button file-action-toggle" aria-label="More open actions" aria-expanded="' + (menuOpen ? 'true' : 'false') + '" data-action="toggle-file-action-menu" data-file-path="' + escapeHtml(normalizedPath) + '">▾</button>'
        + (menuOpen
          ? '<span class="file-action-menu">'
            + '<button class="button" data-action="open-file-path" data-path="' + escapeHtml(normalizedPath) + '">Open in Desktop</button>'
            + (windowsPath ? '<button class="button" data-action="copy-command" data-command-type="file-path" data-command="' + escapeHtml(windowsPath) + '">Copy Path</button>' : '')
            + (isSlicerLaunchableExtension(extension) ? '<button class="button" data-action="open-in-slicer" data-file-path="' + escapeHtml(normalizedPath) + '">Open in Slicer</button>' : '')
            + '</span>'
          : '')
        + '</span>';
    }

    _renderFolderActionSplit(containerPath, windowsPath) {
      var normalizedPath = String(containerPath || '').trim();
      if (!normalizedPath) {
        return '';
      }
      var menuOpen = this._fileActionMenuPath === normalizedPath;
      return ''
        + '<span class="file-action-split">'
        + '<button class="button file-action-main" data-action="open-group-folder" data-path="' + escapeHtml(normalizedPath) + '">Open Folder on Desktop</button>'
        + '<button class="button file-action-toggle" aria-label="More folder actions" aria-expanded="' + (menuOpen ? 'true' : 'false') + '" data-action="toggle-file-action-menu" data-file-path="' + escapeHtml(normalizedPath) + '">▾</button>'
        + (menuOpen
          ? '<span class="file-action-menu">'
            + '<button class="button" data-action="open-group-folder" data-path="' + escapeHtml(normalizedPath) + '">Open Folder on Desktop</button>'
            + (windowsPath ? '<button class="button" data-action="copy-command" data-command-type="folder-path" data-command="' + escapeHtml(windowsPath) + '">Copy Path</button>' : '')
            + '</span>'
          : '')
        + '</span>';
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
      this._setReorganizeDialog({
        open: true,
        phase: 'planning',
        groupId: Number(group.id || 0),
        groupTitle: String(group.title || 'Working Files Group'),
        targetFolder: String(group.folder_hint || ''),
      });
      this._render();
      try {
        var dryRun = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_reorganize_working_group', {
          group_id: group.id,
          execute: false,
        });
        var dialog = this._normalizeReorganizePayload(group, dryRun, 'confirm');
        if (!dialog.moveCount && !dialog.duplicateCount) {
          dialog.phase = 'result';
        } else if (!dialog.canExecute) {
          dialog.phase = 'blocked';
        }
        this._loading = false;
        this._setReorganizeDialog(dialog);
      } catch (error) {
        this._loading = false;
        this._setReorganizeDialog({
          open: true,
          phase: 'blocked',
          groupId: Number(group.id || 0),
          groupTitle: String(group.title || 'Working Files Group'),
          targetFolder: String(group.folder_hint || ''),
          moveCount: 0,
          movedCount: 0,
          collisionCount: 0,
          duplicateCount: 0,
          operationPlan: [],
          collisionRenames: [],
          duplicateSkips: [],
          canExecute: false,
          raw: { message: error && error.message ? String(error.message) : 'Could not reorganize group files.' },
        });
        this._error = '';
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

    _buildSlicerLaunchUrl(downloadUrl) {
      var normalized = String(downloadUrl || '').trim();
      if (!normalized) {
        return '';
      }
      var platform = String(navigator.platform || '').toLowerCase();
      var userAgent = String(navigator.userAgent || '').toLowerCase();
      if (platform.indexOf('mac') >= 0 || userAgent.indexOf('mac') >= 0) {
        return 'bambustudioopen://' + encodeURIComponent(normalized);
      }
      return 'bambustudio://open?file=' + normalized;
    }

    _openWindow(url, target) {
      var normalized = String(url || '').trim();
      if (!normalized) {
        return;
      }
      var anchor = document.createElement('a');
      anchor.href = normalized;
      anchor.target = target || '_self';
      anchor.rel = 'noopener noreferrer';
      anchor.style.display = 'none';
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
    }

    _localHelperRequestMessage(action) {
      var requestLabel = action === 'open_folder'
        ? 'Requested local folder open.'
        : (action === 'open_in_slicer' ? 'Requested local slicer open.' : 'Requested local file open.');
      return requestLabel + ' If nothing happens, install or re-register the desktop helper on this machine.';
    }

    async _launchLocalHelperAction(action, pathValue) {
      var normalizedPath = String(pathValue || '').trim();
      if (!normalizedPath) {
        this._error = 'Launch path is empty.';
        this._render();
        return;
      }
      this._status = action === 'open_folder'
        ? 'Opening folder locally...'
        : (action === 'open_in_slicer' ? 'Opening local file in slicer...' : 'Opening file locally...');
      this._error = '';
      this._render();
      try {
        var response = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_create_working_file_local_action_token', {
          action: action,
          path: normalizedPath,
        });
        var launchUrl = String(response && response.launch_url ? response.launch_url : '').trim();
        if (!launchUrl) {
          throw new Error('No helper launch URL was returned.');
        }
        this._openWindow(launchUrl, '_self');
        this._showCopyToast(this._localHelperRequestMessage(action));
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not launch the local helper action.';
        this._render();
      }
    }

    async _openFileInSlicer(pathValue) {
      this._launchLocalHelperAction('open_in_slicer', pathValue);
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
        + '<button class="type-chip type-all' + (typeFilter === 'all' ? ' active' : '') + '" data-action="set-group-file-type" data-group-id="' + String(groupId) + '" data-file-type="all">' + escapeHtml(formatCountLabel('All', counts.all)) + '</button>'
        + '<button class="type-chip type-models' + (typeFilter === 'models' ? ' active' : '') + '" data-action="set-group-file-type" data-group-id="' + String(groupId) + '" data-file-type="models">' + escapeHtml(formatCountLabel('Models', counts.models)) + '</button>'
        + '<button class="type-chip type-images' + (typeFilter === 'images' ? ' active' : '') + '" data-action="set-group-file-type" data-group-id="' + String(groupId) + '" data-file-type="images">' + escapeHtml(formatCountLabel('Images', counts.images)) + '</button>'
        + '<button class="type-chip type-other' + (typeFilter === 'other' ? ' active' : '') + '" data-action="set-group-file-type" data-group-id="' + String(groupId) + '" data-file-type="other">' + escapeHtml(formatCountLabel('Other Files', counts.other)) + '</button>'
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

    _absoluteFolderPathForRelative(fullPath, relativePath, folderPath) {
      var normalizedFull = normalizePath(fullPath);
      var normalizedRelative = normalizePath(relativePath).replace(/^\/+/, '');
      var normalizedFolder = normalizePath(folderPath).replace(/^\/+/, '');
      if (!normalizedFull || !normalizedRelative) {
        return '';
      }
      var suffix = '/' + normalizedRelative;
      if (!normalizedFull.endsWith(suffix)) {
        return dirname(normalizedFull);
      }
      var rootPath = normalizedFull.slice(0, normalizedFull.length - suffix.length);
      if (!normalizedFolder) {
        return rootPath || '/';
      }
      return this._joinFolderPath(rootPath, normalizedFolder);
    }

    _parentFolderPath(folderPath) {
      var normalized = String(folderPath || '').trim();
      if (!normalized || normalized.indexOf('/') < 0) {
        return '';
      }
      return normalized.slice(0, normalized.lastIndexOf('/'));
    }

    _portableLocalPath(pathValue) {
      var normalized = String(pathValue || '').trim();
      if (!normalized) {
        return '';
      }
      var windowsPath = normalized.replace(/\//g, '\\');
      var marker = '\\OneDrive\\';
      var markerIndex = windowsPath.toLowerCase().indexOf(marker.toLowerCase());
      if (markerIndex < 0) {
        return windowsPath;
      }
      var relativePath = windowsPath.slice(markerIndex + '\\OneDrive'.length);
      if (!relativePath || relativePath.charAt(0) !== '\\') {
        relativePath = '\\' + relativePath.replace(/^\\+/, '');
      }
      return '%OneDriveConsumer%' + relativePath;
    }

    _buildFolderBrowserIndex(groupFiles, group) {
      var index = { '': { folders: {}, files: [], windowsPath: '', containerPath: '' } };
      groupFiles.forEach(function (entry) {
        var rel = this._normalizeRelativePath(entry, group);
        var containerPath = this._entryPath(entry);
        var launchContext = entry && entry.launch && typeof entry.launch === 'object' ? entry.launch : {};
        var windowsPath = String(launchContext.windows_path || '').trim();
        var containerDirectory = dirname(containerPath);
        var windowsDirectory = windowsPath ? dirname(windowsPath).replace(/\\/g, '/') : '';
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
            index[currentPath] = { folders: {}, files: [], windowsPath: '', containerPath: '' };
          }
          if (!index[nextPath]) {
            index[nextPath] = { folders: {}, files: [], windowsPath: '', containerPath: '' };
          }
          index[currentPath].folders[folderName] = nextPath;
          if (!index[nextPath].windowsPath && windowsDirectory) {
            index[nextPath].windowsPath = this._absoluteFolderPathForRelative(windowsDirectory, dirname(rel), nextPath);
          }
          if (!index[nextPath].containerPath && containerDirectory) {
            index[nextPath].containerPath = this._absoluteFolderPathForRelative(containerDirectory, dirname(rel), nextPath);
          }
          currentPath = nextPath;
        }
        if (!index[currentPath]) {
          index[currentPath] = { folders: {}, files: [], windowsPath: '', containerPath: '' };
        }
        if (!index[currentPath].windowsPath && windowsDirectory) {
          index[currentPath].windowsPath = windowsDirectory;
        }
        if (!index[currentPath].containerPath && containerDirectory) {
          index[currentPath].containerPath = containerDirectory;
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
      var currentNode = browserIndex[currentPath] || { folders: {}, files: [], windowsPath: '', containerPath: '' };
      var folderEntries = Object.keys(currentNode.folders).sort();
      var fileEntries = currentNode.files.filter(function (entry) {
        return this._entryMatchesFolderType(entry, typeFilter);
      }, this);

      var breadcrumbs = '';
      var crumbPath = '';
      var parts = currentPath ? currentPath.split('/').filter(Boolean) : [];
      if (currentPath) {
        breadcrumbs += '<button class="breadcrumb-up" data-action="folder-up" data-group-id="' + String(groupId) + '" title="Up one level" aria-label="Up one level"><ha-icon icon="mdi:arrow-up"></ha-icon></button><span class="crumb-sep" aria-hidden="true"><ha-icon icon="mdi:chevron-right"></ha-icon></span>';
      }
      breadcrumbs += '<button class="breadcrumb-link' + (parts.length ? '' : ' current') + '" data-action="set-group-folder-path" data-group-id="' + String(groupId) + '" data-folder-path="">Root</button>';
      parts.forEach(function (segment) {
        crumbPath = this._joinFolderPath(crumbPath, segment);
        breadcrumbs += '<span class="crumb-sep" aria-hidden="true"><ha-icon icon="mdi:chevron-right"></ha-icon></span><button class="breadcrumb-link' + (crumbPath === currentPath ? ' current' : '') + '" data-action="set-group-folder-path" data-group-id="' + String(groupId) + '" data-folder-path="' + escapeHtml(crumbPath) + '">' + escapeHtml(segment) + '</button>';
      }, this);

      var folderRows = '';
      if (!folderEntries.length && !fileEntries.length) {
        folderRows = '<div class="state-row">This folder is empty.</div>';
      } else {
        folderRows = '<div class="folder-browser-list">'
          + folderEntries.map(function (folderName) {
            var nextPath = currentNode.folders[folderName];
            var childNode = browserIndex[nextPath] || { folders: {}, files: [], windowsPath: '', containerPath: '' };
            var childCount = childNode.files.length;
            return ''
              + '<div class="browser-row folder" data-action="set-group-folder-path" data-group-id="' + String(groupId) + '" data-folder-path="' + escapeHtml(nextPath) + '">'
              + '<span class="browser-icon">📁</span>'
              + '<span class="browser-name"><span class="name-main">' + escapeHtml(folderName) + '</span><span class="sub">' + String(Object.keys(childNode.folders).length) + ' folder(s) · ' + String(childCount) + ' file(s)</span></span>'
              + '<span class="browser-actions">' + this._renderFolderActionSplit(childNode.containerPath, childNode.windowsPath) + '</span>'
              + '</div>';
          }, this).join('')
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
              + '<span class="browser-actions">'
              + this._renderFileActionSplit(pathValue, extension, entry && entry.launch ? entry.launch.windows_path : '')
              + '<label class="selector"><input type="checkbox" data-action="toggle-select-path" data-file-path="' + escapeHtml(pathValue) + '"' + (selected ? ' checked' : '') + '>Select</label></span>'
              + '</div>';
          }, this).join('')
          + '</div>';
      }

      return ''
        + '<div class="folder-explorer">'
        + '<div class="folder-head-row">'
        + '<span class="subtitle">Folder explorer</span>'
        + (currentNode.windowsPath
          ? '<span class="spacer"></span><button class="button" data-action="copy-command" data-command-type="folder-path" data-command="' + escapeHtml(currentNode.windowsPath) + '">Copy Current Folder Path</button>'
          : '')
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
      var target = null;
      var path = event && typeof event.composedPath === 'function' ? event.composedPath() : [];
      for (var pathIndex = 0; pathIndex < path.length; pathIndex += 1) {
        if (path[pathIndex] instanceof Element) {
          target = path[pathIndex].closest('[data-action]');
          if (target) {
            break;
          }
        }
      }
      if (!target && event.target instanceof Element) {
        target = event.target.closest('[data-action]');
      }
      if (!target) {
        if (this._fileActionMenuPath) {
          this._fileActionMenuPath = '';
          this._render();
        }
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
        this._fileActionMenuPath = '';
        this._openLocalPath(String(target.getAttribute('data-path') || ''));
        return;
      }
      if (action === 'toggle-file-action-menu') {
        this._toggleFileActionMenu(String(target.getAttribute('data-file-path') || ''));
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
      if (action === 'close-reorganize-dialog') {
        this._closeReorganizeDialog();
        return;
      }
      if (action === 'confirm-reorganize-dialog') {
        this._confirmReorganizeDialog();
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
        this._fileActionMenuPath = '';
        this._openFolderPath(String(target.getAttribute('data-path') || ''));
        return;
      }
      if (action === 'open-in-slicer') {
        this._fileActionMenuPath = '';
        this._openFileInSlicer(String(target.getAttribute('data-file-path') || ''));
        return;
      }
      if (action === 'copy-command') {
        this._fileActionMenuPath = '';
        var commandType = String(target.getAttribute('data-command-type') || 'explorer');
        var command = String(target.getAttribute('data-command') || '');
        this._copyToClipboard(command, commandType);
        return;
      }
    }

    _copyToClipboard(command, commandType) {
      if (!command) {
        return;
      }
      var copiedValue = String(command);
      if (commandType === 'file-path' || commandType === 'folder-path') {
        copiedValue = this._portableLocalPath(command);
      }
      var tooltip = '';
      if (commandType === 'file-path') {
        tooltip = copiedValue !== String(command)
          ? 'File path copied with %OneDriveConsumer%. Paste into Win+R or Explorer.'
          : 'File path copied! Paste into Win+R or Explorer to open it.';
      } else if (commandType === 'folder-path') {
        tooltip = copiedValue !== String(command)
          ? 'Folder path copied with %OneDriveConsumer%. Paste into Win+R or Explorer.'
          : 'Folder path copied! Paste into Win+R or Explorer to open it.';
      } else {
        tooltip = 'Path copied!';
      }
      
      try {
        navigator.clipboard.writeText(copiedValue).then(function () {
          this._showCopyToast(tooltip);
        }.bind(this)).catch(function (err) {
          console.warn('Copy failed, trying fallback:', err);
          this._copyToastViaExecCommand(copiedValue, tooltip);
        }.bind(this));
      } catch (err) {
        console.warn('Clipboard API unavailable, trying fallback:', err);
        this._copyToastViaExecCommand(copiedValue, tooltip);
      }
    }

    _copyToastViaExecCommand(command, tooltip) {
      try {
        var textArea = document.createElement('textarea');
        textArea.value = command;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        this._showCopyToast(tooltip);
      } catch (err) {
        console.error('Copy failed:', err);
        this._showCopyToast('Failed to copy path.');
      }
    }

    _showCopyToast(message) {
      this._status = message;
      this._render();
      setTimeout(function () {
        if (this._status === message) {
          this._status = '';
          this._render();
        }
      }.bind(this), 3000);
    }

    _closeReorganizeDialog() {
      this._reorganizeDialog = null;
      this._render();
    }

    _setReorganizeDialog(dialog) {
      this._reorganizeDialog = dialog;
      this._render();
    }

    _normalizeReorganizePayload(group, payload, phase) {
      var operationPlan = Array.isArray(payload && payload.operation_plan)
        ? payload.operation_plan
        : (Array.isArray(payload && payload.plan) ? payload.plan : []);
      var collisionRenames = Array.isArray(payload && payload.collision_renames)
        ? payload.collision_renames
        : (Array.isArray(payload && payload.conflicts) ? payload.conflicts : []);
      var duplicateSkips = Array.isArray(payload && payload.duplicate_hash_skips)
        ? payload.duplicate_hash_skips
        : [];
      var moveCount = Number(payload && payload.moved_count);
      if (!Number.isFinite(moveCount)) {
        moveCount = operationPlan.filter(function (entry) {
          return String(entry && entry.action || '').toLowerCase() === 'move';
        }).length;
      }
      var collisionCount = Number(payload && payload.collisions_detected);
      if (!Number.isFinite(collisionCount)) {
        collisionCount = collisionRenames.length;
      }
      var duplicateCount = Number(payload && payload.duplicate_hash_skipped_count);
      if (!Number.isFinite(duplicateCount)) {
        duplicateCount = duplicateSkips.length;
      }
      return {
        open: true,
        phase: phase,
        groupId: Number(group && group.id || 0),
        groupTitle: String(group && group.title || 'Working Files Group'),
        targetFolder: String(payload && (payload.target_folder || payload.folder_hint || (group && group.folder_hint) || '') || ''),
        canExecute: payload ? payload.can_execute !== false : true,
        moveCount: moveCount,
        collisionCount: collisionCount,
        duplicateCount: duplicateCount,
        operationPlan: operationPlan,
        collisionRenames: collisionRenames,
        duplicateSkips: duplicateSkips,
        movedCount: Number(payload && payload.moved_count || 0),
        auditEvents: Array.isArray(payload && payload.audit_events) ? payload.audit_events : [],
        raw: payload || {},
      };
    }

    _reorganizeEntryPaths(entry) {
      return {
        fromPath: String(entry && (entry.source_path || entry.file_path || entry.from_path || entry.source || entry.path) || ''),
        toPath: String(entry && (entry.target_path || entry.destination_path || entry.to_path || entry.target || entry.new_path) || ''),
      };
    }

    _renderReorganizeList(entries, emptyText) {
      if (!Array.isArray(entries) || !entries.length) {
        return '<div class="state-row">' + escapeHtml(emptyText) + '</div>';
      }
      return '<div class="dialog-list">' + entries.slice(0, 8).map(function (entry) {
        var paths = this._reorganizeEntryPaths(entry);
        var title = basename(paths.fromPath || paths.toPath || String(entry && entry.name || 'Item'));
        var note = String(entry && (entry.reason || entry.message || entry.note || '') || '').trim();
        var badge = String(entry && (entry.action || (entry.collision_renamed ? 'rename' : 'detail')) || 'detail');
        return ''
          + '<div class="dialog-list-item">'
          + '  <div class="dialog-list-top"><div class="dialog-list-title">' + escapeHtml(title || 'Planned item') + '</div><span class="group-chip">' + escapeHtml(formatStage(badge)) + '</span></div>'
          + (paths.fromPath ? '<div class="dialog-list-meta">From: ' + escapeHtml(paths.fromPath) + '</div>' : '')
          + (paths.toPath ? '<div class="dialog-list-meta">To: ' + escapeHtml(paths.toPath) + '</div>' : '')
          + (note ? '<div class="dialog-list-note">' + escapeHtml(note) + '</div>' : '')
          + '</div>';
      }, this).join('')
        + (entries.length > 8 ? '<div class="dialog-list-note">Showing first ' + String(Math.min(entries.length, 8)) + ' of ' + String(entries.length) + ' items.</div>' : '')
        + '</div>';
    }

    _renderReorganizeDialog() {
      var dialog = this._reorganizeDialog;
      if (!dialog || !dialog.open) {
        return '';
      }
      var phase = String(dialog.phase || 'planning');
      var targetFolder = String(dialog.targetFolder || '(unknown target)');
      var bodyHtml = '';
      var actionsHtml = '<button class="button" data-action="close-reorganize-dialog">Close</button>';

      if (phase === 'planning') {
        bodyHtml = ''
          + '<div class="dialog-card"><div class="dialog-spinner">Checking the reorganize plan for this group.</div></div>'
          + '<div class="dialog-card"><div class="dialog-label">Group</div><div class="dialog-path">' + escapeHtml(dialog.groupTitle) + '</div></div>';
        actionsHtml = '<button class="button" data-action="close-reorganize-dialog">Cancel</button>';
      } else if (phase === 'executing') {
        bodyHtml = ''
          + '<div class="dialog-card"><div class="dialog-spinner">Moving files into the target folder.</div></div>'
          + '<div class="dialog-card"><div class="dialog-label">Target Folder</div><div class="dialog-path">' + escapeHtml(targetFolder) + '</div></div>';
      } else {
        var message = String(dialog.raw && dialog.raw.message || '').trim();
        var headingText = 'Review the dry-run before moving files.';
        if (phase === 'result') {
          headingText = dialog.moveCount || dialog.movedCount
            ? 'The reorganize operation completed.'
            : 'No file moves were required.';
        } else if (phase === 'blocked') {
          headingText = message || 'The dry-run completed, but this group needs attention before continuing.';
        }
        bodyHtml = ''
          + '<div class="dialog-copy">' + escapeHtml(headingText) + '</div>'
          + '<div class="dialog-kpis">'
          + '  <div class="dialog-kpi"><div class="dialog-kpi-label">Moves</div><div class="dialog-kpi-value">' + String(phase === 'result' ? dialog.movedCount : dialog.moveCount) + '</div></div>'
          + '  <div class="dialog-kpi"><div class="dialog-kpi-label">Collision Renames</div><div class="dialog-kpi-value">' + String(dialog.collisionCount || 0) + '</div></div>'
          + '  <div class="dialog-kpi"><div class="dialog-kpi-label">Duplicate Skips</div><div class="dialog-kpi-value">' + String(dialog.duplicateCount || 0) + '</div></div>'
          + '</div>'
          + '<div class="dialog-card' + (phase === 'blocked' ? ' error' : (phase === 'result' ? ' success' : '')) + '"><div class="dialog-label">Target Folder</div><div class="dialog-path">' + escapeHtml(targetFolder) + '</div></div>';

        if (phase !== 'result') {
          bodyHtml += '<div class="dialog-card"><div class="dialog-label">Planned Moves</div>' + this._renderReorganizeList(dialog.operationPlan.filter(function (entry) {
            return String(entry && entry.action || '').toLowerCase() === 'move';
          }), 'No file moves are planned.') + '</div>';
        }

        if (dialog.collisionCount) {
          bodyHtml += '<div class="dialog-card warn"><div class="dialog-label">Collision Renames</div>' + this._renderReorganizeList(dialog.collisionRenames, 'No rename collisions were reported.') + '</div>';
        }
        if (dialog.duplicateCount) {
          bodyHtml += '<div class="dialog-card warn"><div class="dialog-label">Duplicate Hash Skips</div>' + this._renderReorganizeList(dialog.duplicateSkips, 'No duplicate hash skips were reported.') + '</div>';
        }

        if (phase === 'confirm') {
          actionsHtml = ''
            + '<button class="button" data-action="close-reorganize-dialog">Cancel</button>'
            + '<button class="button primary" data-action="confirm-reorganize-dialog">Run Reorganize</button>';
        }
      }

      return ''
        + '<div class="dialog-scrim" role="dialog" aria-modal="true" aria-label="Reorganize working group">'
        + '  <div class="dialog">'
        + '    <div class="dialog-head"><div><div class="dialog-title">Reorganize ' + escapeHtml(dialog.groupTitle) + '</div></div></div>'
        + bodyHtml
        + '    <div class="dialog-actions">' + actionsHtml + '</div>'
        + '  </div>'
        + '</div>';
    }

    async _confirmReorganizeDialog() {
      var dialog = this._reorganizeDialog;
      if (!dialog || !dialog.groupId) {
        return;
      }
      this._setReorganizeDialog(Object.assign({}, dialog, { phase: 'executing' }));
      try {
        var executed = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_reorganize_working_group', {
          group_id: dialog.groupId,
          execute: true,
        });
        var resultDialog = this._normalizeReorganizePayload({ id: dialog.groupId, title: dialog.groupTitle, folder_hint: dialog.targetFolder }, executed, 'result');
        this._selectedPaths = {};
        this._status = 'Reorganized ' + String(resultDialog.movedCount || 0) + ' file(s).';
        await this._loadExplorer();
        this._setReorganizeDialog(resultDialog);
      } catch (error) {
        this._setReorganizeDialog(Object.assign({}, dialog, {
          phase: 'blocked',
          canExecute: false,
          raw: { message: error && error.message ? String(error.message) : 'Could not reorganize group files.' },
        }));
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
              + '<span class="copy-slot">' + this._renderFileActionSplit(pathValue, ext, entry && entry.launch ? entry.launch.windows_path : '') + '</span>'
              + '<span class="selector-slot"><label class="selector"><input type="checkbox" data-action="toggle-select-path" data-file-path="' + escapeHtml(pathValue) + '"' + (selected ? ' checked' : '') + '>Select</label></span>'
              + '</div>';
          }, this).join('') + '</div>';
        }

        var stripBody = subView === 'folders'
          ? this._renderFolderExplorer(files, group, groupId)
          : modelRowsHtml;

        return ''
          + '<article class="group-row stage-' + escapeHtml(stageClass) + (active ? ' active' : '') + '" style="' + escapeHtml(groupStyle) + '">'
          + '  <div class="group-header" data-action="toggle-group-collapsed" data-group-id="' + String(groupId) + '">'
          + '    <div class="thumb" title="' + escapeHtml(formatStage(group.stage || 'draft')) + '">' + escapeHtml(groupInitials) + '</div>'
          + '    <div>'
          + '      <div class="group-title-row"><div class="group-title">' + escapeHtml(group.title || 'Untitled Group') + '</div><span class="stage-chip ' + escapeHtml(stageClass) + '">' + escapeHtml(formatStage(group.stage || 'draft')) + '</span></div>'
          + '      <div class="folder-hint">' + escapeHtml(pathFootprint.common_prefix || storageRelativePath(group.folder_hint || '').relative || group.notes || '') + '</div>'
          + '      <div class="summary-row"><div class="path-summary"><span><strong>Storage:</strong> ' + escapeHtml(pathFootprint.storage_label) + '</span><span><strong>Files:</strong> ' + String(pathFootprint.file_count) + '</span><span><strong>Folders:</strong> ' + String(pathFootprint.folder_count) + '</span></div><button class="button primary compact" data-action="reorganize-group" data-group-id="' + String(groupId) + '">Reorganize</button></div>'
          + '    </div>'
          + '    <div class="group-right"><div class="group-right-meta"><span class="updated">Latest file change' + (latestName ? ' · ' + escapeHtml(latestName) : '') + '</span><span class="updated"><strong>' + escapeHtml(formatRelativeTime(this._entryMtime(latest || {}))) + '</strong> · ' + escapeHtml(formatDateTime(this._entryMtime(latest || {}))) + '</span></div><button class="expander" data-action="toggle-group-collapsed" data-group-id="' + String(groupId) + '">' + (collapsed ? '▸' : '▾') + '</button></div>'
          + '  </div>'
          + (collapsed ? '' : ''
            + '<div class="strip">'
            + '  <div class="strip-head"><div class="strip-head-left"><span class="strip-title">Working group files</span>' + this._renderFileTypeFilters(files, groupId, typeFilter) + '</div><div class="subview-toggle"><button data-action="set-group-subview" data-group-id="' + String(groupId) + '" data-subview="files" class="' + (subView === 'files' ? 'active' : '') + '">Files</button><button data-action="set-group-subview" data-group-id="' + String(groupId) + '" data-subview="folders" class="' + (subView === 'folders' ? 'active' : '') + '">Folders</button></div></div>'
            + stripBody
            + '</div>'
            + '<div class="group-actions"><button class="button warn" data-action="remove-selection-from-row-group" data-group-id="' + String(groupId) + '">Remove Selected</button><span class="spacer"></span><label class="selector"><input type="radio" name="working-group-active" data-action="select-group" data-group-id="' + String(groupId) + '"' + (active ? ' checked' : '') + '>Active group</label></div>')
          + '</article>';
      }, this).join('') + '</div>';
    }

    _renderGroupsView() {
      var selectedCount = this._selectedPathList().length;
      return ''
        + '<section class="section">'
        + '  <div class="title-row section-head"><div><div class="title">Groups</div></div></div>'
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
        + '      </div>'
        + '    </div>'
        + '    ' + (this._status && this._status !== 'Updating results...' ? '<div class="status">' + escapeHtml(this._status) + '</div>' : '')
        + '    ' + (this._error ? '<div class="status error">' + escapeHtml(this._error) + '</div>' : '')
        + '    <section class="toolbar">'
        + '      <div class="title-row">'
        + '        <div class="tab-row">'
        + '          <button class="tab ' + (this._view === 'groups' ? 'active' : '') + '" data-action="set-view" data-view="groups">' + escapeHtml(formatCountLabel('Groups', summary.group_count || this._groups.length || 0)) + '</button>'
        + '          <button class="tab ' + (this._view === 'all' ? 'active' : '') + '" data-action="set-view" data-view="all">' + escapeHtml(formatCountLabel('All Files', summary.all_count || 0)) + '</button>'
        + '          <button class="tab ' + (this._view === 'ungrouped' ? 'active' : '') + '" data-action="set-view" data-view="ungrouped">' + escapeHtml(formatCountLabel('Ungrouped', summary.ungrouped_count || 0)) + '</button>'
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
        + (this._reorganizeDialog && this._reorganizeDialog.open ? this._renderReorganizeDialog() : '')
        + '  </div>'
        + '</ha-card>';

      var root = this.shadowRoot;
      if (root) {
        root.querySelectorAll('[data-action="set-group-file-type"]').forEach(function (button) {
          button.addEventListener('click', function (event) {
            event.preventDefault();
            event.stopPropagation();
            var folderTypeGroupId = Number(button.getAttribute('data-group-id') || 0);
            var nextFolderType = String(button.getAttribute('data-file-type') || 'models').trim().toLowerCase();
            if (folderTypeGroupId) {
              this._groupFolderTypeFilters[folderTypeGroupId] = nextFolderType || 'models';
              this._render();
            }
          }.bind(this));
        }, this);

        root.querySelectorAll('[data-action="set-group-subview"]').forEach(function (button) {
          button.addEventListener('click', function (event) {
            event.preventDefault();
            event.stopPropagation();
            var subViewGroupId = Number(button.getAttribute('data-group-id') || 0);
            var nextSubView = String(button.getAttribute('data-subview') || 'files');
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
          }.bind(this));
        }, this);
      }
    }
  }

  if (!customElements.get('model-catalog-working-files-explorer-card')) {
    customElements.define('model-catalog-working-files-explorer-card', ModelCatalogWorkingFilesExplorerCard);
  }
})();
