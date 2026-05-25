/*
 * model-catalog-working-files-explorer-card.js
 *
 * Single-view Working Files explorer.
 *
 * Consumes the new working-files filesystem-truth endpoints (PR C):
 *   GET /api/working-files/tree
 *   GET /api/working-files/loose?limit&offset
 *   GET /api/working-files/groups/{folder_slug}
 *   GET /api/working-files/groups/{folder_slug}/files?mode=files|folders
 *
 * Design reference: docs/features/model_catalog/design/working-files.md (§2).
 *
 * The card never mutates the filesystem. Reindex triggers the kept
 * /api/working-files/reindex endpoint; per-file launch uses the existing
 * local-action-token rest_command (open_folder / open_in_slicer / open_file).
 */
(function () {
  "use strict";

  // ---------- formatting helpers ----------
  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function basename(pathValue) {
    var normalized = String(pathValue || "").replace(/\\/g, "/");
    if (!normalized) return "";
    var parts = normalized.split("/");
    return parts[parts.length - 1] || normalized;
  }

  function dirname(pathValue) {
    var normalized = String(pathValue || "").replace(/\\/g, "/");
    if (!normalized || normalized.indexOf("/") < 0) return normalized;
    return normalized.slice(0, normalized.lastIndexOf("/"));
  }

  function formatBytes(bytes) {
    var value = Number(bytes || 0);
    if (!Number.isFinite(value) || value <= 0) return "0 B";
    var units = ["B", "KB", "MB", "GB", "TB"];
    var index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
    var scaled = value / Math.pow(1024, index);
    return scaled.toFixed(scaled >= 10 || index === 0 ? 0 : 1) + " " + units[index];
  }

  function parseIsoDate(value) {
    if (!value) return null;
    var parsed = Date.parse(String(value));
    return Number.isFinite(parsed) ? new Date(parsed) : null;
  }

  function formatRelativeTime(value) {
    var parsed = parseIsoDate(value);
    if (!parsed) return "-";
    var seconds = Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 1000));
    if (seconds < 60) return "just now";
    if (seconds < 3600) return Math.floor(seconds / 60) + "m ago";
    if (seconds < 86400) return Math.floor(seconds / 3600) + "h ago";
    if (seconds < 604800) return Math.floor(seconds / 86400) + "d ago";
    return Math.floor(seconds / 604800) + "w ago";
  }

  function formatDateTime(value) {
    var parsed = parseIsoDate(value);
    if (!parsed) return "-";
    try {
      return parsed.toLocaleString(undefined, {
        year: "numeric", month: "short", day: "2-digit",
        hour: "2-digit", minute: "2-digit",
      });
    } catch (_err) {
      return parsed.toISOString();
    }
  }

  function extensionFromName(name) {
    var lower = String(name || "").toLowerCase();
    var index = lower.lastIndexOf(".");
    return index >= 0 ? lower.slice(index) : "";
  }

  function extensionBadge(extension) {
    return String(extension || "").replace(/^\./, "").toUpperCase() || "FILE";
  }

  function isModelExtension(ext) {
    return [".3mf", ".stl", ".step", ".stp", ".obj"].indexOf(String(ext || "").toLowerCase()) >= 0;
  }

  function isSlicerLaunchableExtension(ext) {
    return [".3mf", ".stl", ".step", ".stp", ".obj", ".gcode"].indexOf(String(ext || "").toLowerCase()) >= 0;
  }

  function isImageExtension(ext) {
    return [".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp"].indexOf(String(ext || "").toLowerCase()) >= 0;
  }

  function portableLocalPath(pathValue) {
    var raw = String(pathValue || "");
    if (!raw) return raw;
    // Re-write user-profile OneDrive paths to use %OneDriveConsumer% so they're portable
    var match = /^([a-zA-Z]):[\\/]Users[\\/][^\\/]+[\\/]OneDrive([\\/].*)?$/.exec(raw.replace(/\\/g, "\\"));
    if (match) {
      return "%OneDriveConsumer%" + (match[2] || "").replace(/\//g, "\\");
    }
    return raw;
  }

  // ---------- HA service call helpers ----------
  async function authHeaders(hass, forceRefresh) {
    var auth = hass && hass.auth ? hass.auth : null;
    if (!auth) return {};
    if (forceRefresh && typeof auth.refreshAccessToken === "function") {
      try { await auth.refreshAccessToken(); } catch (_e) {}
    }
    var token = auth.accessToken || (auth.data ? auth.data.accessToken : "");
    return token ? { Authorization: "Bearer " + token } : {};
  }

  function normalizeServiceResponse(payload) {
    if (Array.isArray(payload) && payload.length) return normalizeServiceResponse(payload[0]);
    if (payload && typeof payload === "object") {
      if (payload.service_response && typeof payload.service_response === "object") {
        return normalizeServiceResponse(payload.service_response);
      }
      if (payload.response && typeof payload.response === "object") {
        return normalizeServiceResponse(payload.response);
      }
      if (payload.content && typeof payload.content === "object"
        && (Object.prototype.hasOwnProperty.call(payload, "status")
          || Object.prototype.hasOwnProperty.call(payload, "headers"))) {
        return Object.assign({}, payload.content, {
          status: payload.status,
          headers: payload.headers,
        });
      }
    }
    return payload && typeof payload === "object" ? payload : {};
  }

  async function callServiceWithResponse(hass, domain, service, data) {
    var endpoint = "/api/services/" + encodeURIComponent(String(domain || ""))
      + "/" + encodeURIComponent(String(service || "")) + "?return_response";
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
    try { payload = await response.json(); } catch (_e) { payload = {}; }

    if (!response.ok) {
      var message = payload && payload.message ? String(payload.message)
        : "Service call failed (HTTP " + String(response.status) + ")";
      throw new Error(message);
    }

    var normalized = normalizeServiceResponse(payload);
    // Sidecar 410 envelope surfaces as success:false with error code
    if (normalized && normalized.success === false) {
      throw new Error(normalized.message || normalized.error
        || "Request failed.");
    }
    if (normalized && typeof normalized.status === "number" && normalized.status >= 400) {
      throw new Error(normalized.message
        || ("Request failed (HTTP " + String(normalized.status) + ")."));
    }
    return normalized;
  }

  // ---------- CSS ----------
  var sharedStyles = ''
    + 'ha-card{border-radius:0;border:none;background:transparent;box-shadow:none;}'
    + '.shell{display:grid;gap:12px;padding:6px 10px 10px;}'
    + '.title-row{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;}'
    + '.title{font-size:18px;font-weight:800;line-height:1.2;}'
    + '.subtitle{font-size:12px;color:var(--secondary-text-color);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;}'
    + '.title-actions{display:inline-flex;gap:8px;align-items:center;flex-wrap:wrap;}'
    + '.status{font-size:12px;font-weight:700;color:var(--secondary-text-color);}'
    + '.status.error{color:#f87171;}'
    + '.button{min-height:32px;padding:0 12px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(148,163,184,0.12);color:var(--primary-text-color);font-size:12px;font-weight:700;cursor:pointer;}'
    + '.button.primary{background:rgba(20,184,166,0.2);border-color:rgba(94,234,212,0.34);color:#99f6e4;}'
    + '.button.compact{min-height:28px;padding:0 10px;font-size:11px;}'
    + '.button:disabled{opacity:.6;cursor:not-allowed;}'
    + '.layout{display:grid;grid-template-columns:minmax(220px,300px) minmax(0,1fr);gap:12px;align-items:start;}'
    + '@media (max-width:760px){.layout{grid-template-columns:1fr;}}'
    + '.sidebar{border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.14);border-radius:14px;padding:8px;display:grid;gap:2px;max-height:70vh;overflow:auto;}'
    + '.tree-item{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;padding:8px 10px;border-radius:10px;border:1px solid transparent;background:transparent;color:var(--primary-text-color);text-align:left;cursor:pointer;font:inherit;}'
    + '.tree-item:hover,.tree-item:focus-visible{background:rgba(148,163,184,0.10);outline:none;}'
    + '.tree-item.active{background:rgba(20,184,166,0.16);border-color:rgba(94,234,212,0.36);}'
    + '.tree-item.loose{font-style:italic;color:var(--secondary-text-color);}'
    + '.tree-item.loose.active{color:#99f6e4;font-style:normal;}'
    + '.tree-name{font-size:13px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;}'
    + '.tree-meta{font-size:10px;color:var(--secondary-text-color);text-align:right;white-space:nowrap;}'
    + '.tree-meta .sub{display:block;font-size:9px;opacity:.8;}'
    + '.tree-empty{padding:14px;text-align:center;color:var(--secondary-text-color);font-size:12px;}'
    + '.tree-sidecar-dots{display:inline-flex;gap:3px;margin-left:6px;}'
    + '.tree-sidecar-dots span{display:inline-block;width:6px;height:6px;border-radius:50%;background:rgba(148,163,184,0.5);}'
    + '.tree-sidecar-dots span.modelmeta{background:#5eead4;}'
    + '.tree-sidecar-dots span.readme{background:#93c5fd;}'
    + '.detail{border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.14);border-radius:14px;padding:14px;display:grid;gap:12px;min-width:0;}'
    + '.detail-empty{padding:30px;text-align:center;color:var(--secondary-text-color);font-size:13px;}'
    + '.detail-head{display:grid;gap:6px;}'
    + '.detail-title{font-size:17px;font-weight:800;line-height:1.2;}'
    + '.detail-path{font-size:11px;color:var(--secondary-text-color);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;word-break:break-all;}'
    + '.detail-kpis{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--secondary-text-color);}'
    + '.detail-kpis strong{color:var(--primary-text-color);font-weight:700;margin-right:4px;}'
    + '.detail-actions{display:flex;gap:8px;flex-wrap:wrap;}'
    + '.sidecar{border:1px solid rgba(148,163,184,0.22);background:rgba(15,23,42,0.22);border-radius:12px;padding:12px;display:grid;gap:10px;}'
    + '.sidecar-row{display:grid;gap:4px;}'
    + '.sidecar-label{font-size:10px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:var(--secondary-text-color);}'
    + '.sidecar-tags{display:flex;gap:4px;flex-wrap:wrap;}'
    + '.sidecar-tag{display:inline-flex;padding:2px 8px;border-radius:999px;font-size:10px;border:1px solid rgba(96,165,250,0.32);background:rgba(96,165,250,0.12);color:#bfdbfe;}'
    + '.sidecar-md{font-size:12px;line-height:1.5;color:var(--primary-text-color);white-space:pre-wrap;font-family:inherit;background:rgba(15,23,42,0.4);border-radius:8px;padding:10px;border:1px solid rgba(148,163,184,0.16);max-height:240px;overflow:auto;}'
    + '.sidecar-link{font-size:12px;color:#93c5fd;word-break:break-all;}'
    + '.sidecar-thumb{max-width:160px;max-height:120px;border-radius:8px;border:1px solid rgba(148,163,184,0.22);}'
    + '.mode-toggle{display:inline-flex;padding:2px;border:1px solid rgba(148,163,184,0.24);border-radius:999px;background:rgba(15,23,42,0.35);}'
    + '.mode-toggle button{border:0;background:transparent;color:var(--secondary-text-color);font-size:10px;padding:5px 12px;border-radius:999px;cursor:pointer;text-transform:uppercase;font-weight:700;}'
    + '.mode-toggle button.active{background:rgba(20,184,166,0.2);color:#99f6e4;}'
    + '.list-head{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;}'
    + '.list-title{font-size:11px;text-transform:uppercase;letter-spacing:.06em;font-weight:700;color:var(--secondary-text-color);}'
    + '.file-table{border:1px solid rgba(148,163,184,0.18);border-radius:12px;overflow:auto;background:rgba(15,23,42,0.1);max-height:60vh;}'
    + '.file-table table{width:100%;border-collapse:collapse;min-width:520px;}'
    + '.file-table th{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--secondary-text-color);padding:8px 10px;border-bottom:1px solid rgba(148,163,184,0.2);text-align:left;background:rgba(15,23,42,0.35);position:sticky;top:0;}'
    + '.file-table td{padding:8px 10px;border-bottom:1px solid rgba(148,163,184,0.10);font-size:12px;vertical-align:middle;}'
    + '.file-table tr:hover{background:rgba(94,234,212,0.05);}'
    + '.ext-badge{display:inline-flex;align-items:center;justify-content:center;width:30px;height:22px;border-radius:6px;border:1px solid rgba(148,163,184,0.25);font-size:9px;font-weight:800;color:var(--secondary-text-color);background:rgba(255,255,255,0.04);}'
    + '.ext-badge.x-3mf{color:#5eead4;border-color:rgba(94,234,212,0.3);background:rgba(94,234,212,0.12);}'
    + '.ext-badge.x-stl,.ext-badge.x-step,.ext-badge.x-stp,.ext-badge.x-obj{color:#93c5fd;border-color:rgba(96,165,250,0.32);background:rgba(96,165,250,0.12);}'
    + '.ext-badge.x-img{color:#fcd34d;border-color:rgba(252,211,77,0.32);background:rgba(252,211,77,0.10);}'
    + '.file-name{font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:260px;}'
    + '.file-sub{font-size:10px;color:var(--secondary-text-color);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:260px;}'
    + '.file-meta{font-size:11px;color:var(--secondary-text-color);white-space:nowrap;text-align:right;}'
    + '.file-actions{display:inline-flex;gap:4px;justify-content:flex-end;}'
    + '.folder-section{border:1px solid rgba(96,165,250,0.22);background:rgba(96,165,250,0.06);border-radius:10px;padding:10px;display:grid;gap:6px;}'
    + '.folder-section-head{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:11px;color:#bfdbfe;font-weight:700;}'
    + '.folder-section-path{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:var(--secondary-text-color);font-size:10px;}'
    + '.skeleton{height:34px;border-radius:8px;border:1px solid rgba(148,163,184,0.2);background:linear-gradient(90deg, rgba(30,41,59,0.5) 0%, rgba(71,85,105,0.32) 50%, rgba(30,41,59,0.5) 100%);background-size:220% 100%;animation:mcwf-shimmer 1.25s linear infinite;}'
    + '@keyframes mcwf-shimmer{0%{background-position:100% 0;}100%{background-position:-100% 0;}}'
    + '.alert{padding:10px 12px;border-radius:10px;border:1px dashed rgba(248,113,113,0.34);background:rgba(127,29,29,0.18);color:#fecaca;font-size:12px;}'
    + '.muted{color:var(--secondary-text-color);}'
    ;

  // ---------- card ----------
  var LOOSE_KEY = "__loose__";

  class ModelCatalogWorkingFilesExplorerCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._hass = null;
      this._config = null;

      this._tree = null;        // {root_path, root_launch, groups: [...], loose: {...}}
      this._loadingTree = false;
      this._treeError = "";

      this._selectedKey = null; // LOOSE_KEY | folder_slug | null
      this._detail = null;      // group-detail payload or loose-detail payload
      this._loadingDetail = false;
      this._detailError = "";

      this._filesMode = "files"; // 'files' | 'folders'
      this._files = null;        // last files payload
      this._loadingFiles = false;
      this._filesError = "";

      this._status = "";
      this._reindexInFlight = false;
      this._hasLoaded = false;
      this._boundClick = this._handleClick.bind(this);
      this._boundCatalogChanged = this._handleCatalogChanged.bind(this);
    }

    setConfig(config) {
      this._config = {
        title: (config && config.title) ? String(config.title) : "Working Files",
        initial_folder_slug: (config && config.initial_folder_slug)
          ? String(config.initial_folder_slug).trim() : "",
      };
      if (this._config.initial_folder_slug && !this._selectedKey) {
        this._selectedKey = this._config.initial_folder_slug;
      }
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      if (this.isConnected && !this._loadingTree && !this._hasLoaded) {
        this._loadTree();
      }
    }

    connectedCallback() {
      if (this.shadowRoot) {
        this.shadowRoot.addEventListener("click", this._boundClick);
      }
      window.addEventListener("model-catalog-data-changed", this._boundCatalogChanged);
      if (this._hass && !this._hasLoaded && !this._loadingTree) {
        this._loadTree();
      }
    }

    disconnectedCallback() {
      if (this.shadowRoot) {
        this.shadowRoot.removeEventListener("click", this._boundClick);
      }
      window.removeEventListener("model-catalog-data-changed", this._boundCatalogChanged);
    }

    getCardSize() { return 12; }

    _handleCatalogChanged() {
      if (this._hass && this.isConnected) {
        this._loadTree({ silent: true });
      }
    }

    // ---------- data loads ----------
    async _loadTree(options) {
      var silent = !!(options && options.silent);
      if (!this._hass || this._loadingTree) return;
      this._loadingTree = true;
      if (!silent) {
        this._treeError = "";
      }
      this._render();
      try {
        var response = await callServiceWithResponse(
          this._hass, "rest_command", "model_catalog_working_files_tree", {}
        );
        this._tree = {
          root_path: String(response.root_path || ""),
          root_launch: response.root_launch || null,
          groups: Array.isArray(response.groups) ? response.groups.slice() : [],
          loose: response.loose && typeof response.loose === "object"
            ? response.loose : { file_count: 0, size_bytes: 0, last_seen_at: null },
        };
        // Sort groups: by display name (case-insensitive)
        this._tree.groups.sort(function (a, b) {
          var an = String((a && a.name) || "").toLowerCase();
          var bn = String((b && b.name) || "").toLowerCase();
          return an < bn ? -1 : (an > bn ? 1 : 0);
        });
        this._hasLoaded = true;

        // Resolve / repair selection
        if (this._selectedKey) {
          if (this._selectedKey === LOOSE_KEY) {
            if (!this._tree.loose || !this._tree.loose.file_count) {
              this._selectedKey = null;
              this._detail = null;
              this._files = null;
            } else if (!silent) {
              this._loadDetail();
            }
          } else {
            var exists = this._tree.groups.some(function (g) {
              return g && g.slug === this._selectedKey;
            });
            if (!exists) {
              this._selectedKey = null;
              this._detail = null;
              this._files = null;
            } else if (!silent) {
              this._loadDetail();
            }
          }
        }
      } catch (error) {
        this._treeError = (error && error.message) ? String(error.message)
          : "Could not load working files tree.";
      } finally {
        this._loadingTree = false;
        this._render();
      }
    }

    async _loadDetail() {
      if (!this._hass || !this._selectedKey) return;
      var key = this._selectedKey;
      this._loadingDetail = true;
      this._detailError = "";
      this._render();
      try {
        var response;
        if (key === LOOSE_KEY) {
          response = await callServiceWithResponse(
            this._hass, "rest_command", "model_catalog_working_files_loose",
            { limit: 500, offset: 0 }
          );
          // For loose, the "detail" IS the same payload as files (no sidecar).
          if (this._selectedKey !== key) return;
          this._detail = {
            kind: "loose",
            root_path: String(response.root_path || ""),
            counts: {
              file_count: (response.pagination && response.pagination.total)
                ? Number(response.pagination.total)
                : (Array.isArray(response.files) ? response.files.length : 0),
              size_bytes: this._sumSizes(response.files),
            },
            files: Array.isArray(response.files) ? response.files : [],
            folder_launch: this._tree && this._tree.root_launch,
          };
          // Loose has no Folders mode — always files
          this._filesMode = "files";
          this._files = { files: this._detail.files };
        } else {
          response = await callServiceWithResponse(
            this._hass, "rest_command", "model_catalog_working_files_group_detail",
            { folder_slug: key }
          );
          if (this._selectedKey !== key) return;
          this._detail = {
            kind: "group",
            folder_slug: response.folder_slug || key,
            folder_path: String(response.folder_path || ""),
            folder_launch: response.folder_launch || null,
            counts: response.counts || {},
            last_seen_at: response.last_seen_at || null,
            subfolders: Array.isArray(response.subfolders) ? response.subfolders : [],
            sidecar: response.sidecar || null,
          };
          this._files = null;
          // Load file/folder listing for the current mode
          this._loadFiles();
        }
      } catch (error) {
        if (this._selectedKey === key) {
          this._detailError = (error && error.message) ? String(error.message)
            : "Could not load detail for the selected folder.";
          this._detail = null;
          this._files = null;
        }
      } finally {
        if (this._selectedKey === key) {
          this._loadingDetail = false;
          this._render();
        }
      }
    }

    async _loadFiles() {
      if (!this._hass || !this._selectedKey || this._selectedKey === LOOSE_KEY) return;
      var key = this._selectedKey;
      var mode = this._filesMode === "folders" ? "folders" : "files";
      this._loadingFiles = true;
      this._filesError = "";
      this._render();
      try {
        var response = await callServiceWithResponse(
          this._hass, "rest_command", "model_catalog_working_files_group_files",
          { folder_slug: key, mode: mode, limit: 500, offset: 0 }
        );
        if (this._selectedKey !== key || this._filesMode !== mode) return;
        this._files = {
          mode: mode,
          files: Array.isArray(response.files) ? response.files : null,
          folders: Array.isArray(response.folders) ? response.folders : null,
          pagination: response.pagination || null,
        };
      } catch (error) {
        if (this._selectedKey === key && this._filesMode === mode) {
          this._filesError = (error && error.message) ? String(error.message)
            : "Could not load files for the selected folder.";
        }
      } finally {
        if (this._selectedKey === key && this._filesMode === mode) {
          this._loadingFiles = false;
          this._render();
        }
      }
    }

    _sumSizes(files) {
      if (!Array.isArray(files)) return 0;
      var total = 0;
      for (var i = 0; i < files.length; i++) {
        var f = files[i];
        var s = Number(f && f.file_size_bytes);
        if (Number.isFinite(s) && s > 0) total += s;
      }
      return total;
    }

    // ---------- actions ----------
    async _onReindex() {
      if (this._reindexInFlight || !this._hass) return;
      this._reindexInFlight = true;
      this._status = "Reindexing working files...";
      this._render();
      try {
        await callServiceWithResponse(
          this._hass, "rest_command", "model_catalog_reindex_working_files",
          { recurse: true, compute_hashes: false }
        );
        this._status = "Reindex complete. Refreshing...";
        this._render();
        await this._loadTree({ silent: true });
        if (this._selectedKey) {
          await this._loadDetail();
        }
        this._status = "";
      } catch (error) {
        this._status = (error && error.message)
          ? "Reindex failed: " + String(error.message)
          : "Reindex failed.";
      } finally {
        this._reindexInFlight = false;
        this._render();
      }
    }

    _selectKey(key) {
      if (this._selectedKey === key) return;
      this._selectedKey = key;
      this._detail = null;
      this._files = null;
      this._detailError = "";
      this._filesError = "";
      this._filesMode = "files";
      this._render();
      if (key) this._loadDetail();
    }

    _setFilesMode(mode) {
      var next = mode === "folders" ? "folders" : "files";
      if (this._filesMode === next) return;
      this._filesMode = next;
      this._files = null;
      this._render();
      this._loadFiles();
    }

    async _launchLocal(action, pathValue) {
      var path = String(pathValue || "").trim();
      if (!path) {
        this._status = "Launch path is empty.";
        this._render();
        return;
      }
      this._status = (action === "open_folder")
        ? "Opening folder locally..."
        : (action === "open_in_slicer" ? "Opening in slicer..." : "Opening locally...");
      this._render();
      try {
        var response = await callServiceWithResponse(
          this._hass, "rest_command", "model_catalog_create_working_file_local_action_token",
          { action: action, path: path }
        );
        var launchUrl = String((response && response.launch_url) || "").trim();
        if (!launchUrl) throw new Error("No helper launch URL returned.");
        try { window.open(launchUrl, "_self"); } catch (_e) {}
        this._status = "Sent request to local desktop helper. If nothing happens, install/re-register the helper.";
      } catch (error) {
        this._status = (error && error.message)
          ? "Launch failed: " + String(error.message)
          : "Launch failed.";
      } finally {
        this._render();
      }
    }

    _copyPath(pathValue) {
      var raw = String(pathValue || "");
      if (!raw) return;
      var portable = portableLocalPath(raw);
      var doneMsg = portable !== raw
        ? "Path copied with %OneDriveConsumer%. Paste into Win+R or Explorer."
        : "Path copied. Paste into Win+R or Explorer.";
      var self = this;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(portable).then(function () {
            self._toast(doneMsg);
          }).catch(function () {
            self._copyFallback(portable, doneMsg);
          });
          return;
        }
      } catch (_e) {}
      this._copyFallback(portable, doneMsg);
    }

    _copyFallback(text, doneMsg) {
      try {
        var ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        this._toast(doneMsg);
      } catch (_e) {
        this._toast("Failed to copy path.");
      }
    }

    _toast(message) {
      this._status = message;
      this._render();
      var self = this;
      setTimeout(function () {
        if (self._status === message) {
          self._status = "";
          self._render();
        }
      }, 3000);
    }

    // ---------- event delegation ----------
    _handleClick(event) {
      var target = event.target;
      while (target && target !== this.shadowRoot) {
        if (target.dataset && target.dataset.action) {
          var action = target.dataset.action;
          if (action === "select-group") {
            this._selectKey(target.dataset.slug || null);
            return;
          }
          if (action === "select-loose") {
            this._selectKey(LOOSE_KEY);
            return;
          }
          if (action === "reindex") {
            this._onReindex();
            return;
          }
          if (action === "refresh-tree") {
            this._loadTree({ silent: false });
            if (this._selectedKey) this._loadDetail();
            return;
          }
          if (action === "set-mode-files") {
            this._setFilesMode("files");
            return;
          }
          if (action === "set-mode-folders") {
            this._setFilesMode("folders");
            return;
          }
          if (action === "launch") {
            this._launchLocal(
              String(target.dataset.launch || "open_file"),
              String(target.dataset.path || "")
            );
            return;
          }
          if (action === "copy-path") {
            this._copyPath(String(target.dataset.path || ""));
            return;
          }
        }
        target = target.parentNode;
      }
    }

    // ---------- rendering ----------
    _render() {
      if (!this.shadowRoot) return;
      var bodyHtml = this._renderShell();
      this.shadowRoot.innerHTML = "<style>" + sharedStyles + "</style>"
        + "<ha-card><div class='shell'>" + bodyHtml + "</div></ha-card>";
    }

    _renderShell() {
      var html = "";
      html += this._renderTitle();
      if (this._status) {
        html += "<div class='status'>" + escapeHtml(this._status) + "</div>";
      }
      if (this._treeError) {
        html += "<div class='alert'>" + escapeHtml(this._treeError)
          + " <button class='button compact' data-action='refresh-tree'>Retry</button></div>";
      }
      html += "<div class='layout'>"
        + "<div class='sidebar'>" + this._renderTree() + "</div>"
        + "<div class='detail'>" + this._renderDetail() + "</div>"
        + "</div>";
      return html;
    }

    _renderTitle() {
      var title = (this._config && this._config.title) || "Working Files";
      var rootPath = this._tree && this._tree.root_path ? this._tree.root_path : "";
      var reindexDisabled = this._reindexInFlight ? " disabled" : "";
      var refreshLabel = this._reindexInFlight ? "Reindexing..." : "Reindex";
      return "<div class='title-row'>"
        + "<div>"
        + "<div class='title'>" + escapeHtml(title) + "</div>"
        + (rootPath ? "<div class='subtitle'>" + escapeHtml(rootPath) + "</div>" : "")
        + "</div>"
        + "<div class='title-actions'>"
        + "<button class='button compact' data-action='refresh-tree'>Refresh</button>"
        + "<button class='button primary compact' data-action='reindex'" + reindexDisabled + ">"
        + escapeHtml(refreshLabel) + "</button>"
        + "</div>"
        + "</div>";
    }

    _renderTree() {
      if (this._loadingTree && !this._tree) {
        return "<div class='skeleton'></div><div class='skeleton'></div><div class='skeleton'></div>";
      }
      if (!this._tree) {
        return "<div class='tree-empty'>No data.</div>";
      }
      var html = "";
      var loose = this._tree.loose || {};
      var looseCount = Number(loose.file_count || 0);
      if (looseCount > 0) {
        var looseActive = this._selectedKey === LOOSE_KEY ? " active" : "";
        html += "<button class='tree-item loose" + looseActive + "' data-action='select-loose'>"
          + "<span class='tree-name'>(loose files)</span>"
          + "<span class='tree-meta'>"
          + "<strong>" + String(looseCount) + "</strong>"
          + "<span class='sub'>" + escapeHtml(formatBytes(loose.size_bytes)) + "</span>"
          + "</span>"
          + "</button>";
      }
      var groups = this._tree.groups || [];
      if (!groups.length && !looseCount) {
        html += "<div class='tree-empty'>"
          + "<div>No working files indexed.</div>"
          + "<div style='margin-top:6px;'><button class='button compact' data-action='reindex'>Reindex now</button></div>"
          + "</div>";
        return html;
      }
      for (var i = 0; i < groups.length; i++) {
        var g = groups[i];
        if (!g || !g.slug) continue;
        var active = this._selectedKey === g.slug ? " active" : "";
        var dots = "";
        if (g.has_modelmeta || g.has_readme) {
          dots = "<span class='tree-sidecar-dots'>"
            + (g.has_modelmeta ? "<span class='modelmeta' title='Has .modelmeta.json'></span>" : "")
            + (g.has_readme ? "<span class='readme' title='Has README.md'></span>" : "")
            + "</span>";
        }
        html += "<button class='tree-item" + active + "' data-action='select-group' data-slug='"
          + escapeHtml(g.slug) + "'>"
          + "<span class='tree-name'>" + escapeHtml(g.name || g.slug) + dots + "</span>"
          + "<span class='tree-meta'>"
          + "<strong>" + String(Number(g.file_count || 0)) + "</strong>"
          + "<span class='sub'>" + escapeHtml(formatBytes(g.size_bytes)) + "</span>"
          + "</span>"
          + "</button>";
      }
      return html;
    }

    _renderDetail() {
      if (!this._selectedKey) {
        return "<div class='detail-empty'>"
          + "Select a folder on the left to view its files.<br>"
          + "<span class='muted'>Use <strong>Reindex</strong> after adding or moving files in Windows Explorer.</span>"
          + "</div>";
      }
      if (this._loadingDetail && !this._detail) {
        return "<div class='skeleton'></div><div class='skeleton'></div><div class='skeleton'></div>";
      }
      if (this._detailError) {
        return "<div class='alert'>" + escapeHtml(this._detailError) + "</div>";
      }
      if (!this._detail) {
        return "<div class='detail-empty'>No detail available.</div>";
      }
      if (this._detail.kind === "loose") {
        return this._renderLooseDetail();
      }
      return this._renderGroupDetail();
    }

    _renderLooseDetail() {
      var d = this._detail;
      var rootPath = d.root_path || (this._tree && this._tree.root_path) || "";
      var folderLaunch = d.folder_launch || (this._tree && this._tree.root_launch);
      var counts = d.counts || {};
      var html = "<div class='detail-head'>"
        + "<div class='detail-title'>(loose files)</div>"
        + (rootPath ? "<div class='detail-path'>" + escapeHtml(rootPath) + "</div>" : "")
        + "<div class='detail-kpis'>"
        + "<span><strong>" + String(Number(counts.file_count || 0)) + "</strong> files</span>"
        + "<span><strong>" + escapeHtml(formatBytes(counts.size_bytes)) + "</strong></span>"
        + "</div>"
        + "</div>";
      html += this._renderFolderActions(rootPath, folderLaunch, /*allowIntake*/ false);
      html += "<div class='list-head'><div class='list-title'>Files</div></div>";
      html += this._renderFilesTable(d.files || [], rootPath);
      return html;
    }

    _renderGroupDetail() {
      var d = this._detail;
      var sidecar = d.sidecar || null;
      var displayTitle = (sidecar && sidecar.modelmeta && sidecar.modelmeta.display_title)
        ? String(sidecar.modelmeta.display_title)
        : basename(d.folder_path || d.folder_slug || "");
      var counts = d.counts || {};
      var html = "<div class='detail-head'>"
        + "<div class='detail-title'>" + escapeHtml(displayTitle) + "</div>"
        + (d.folder_path ? "<div class='detail-path'>" + escapeHtml(d.folder_path) + "</div>" : "")
        + "<div class='detail-kpis'>"
        + "<span><strong>" + String(Number(counts.file_count || 0)) + "</strong> files</span>"
        + "<span><strong>" + escapeHtml(formatBytes(counts.size_bytes)) + "</strong></span>"
        + (counts.count_3mf ? "<span><strong>" + String(Number(counts.count_3mf)) + "</strong> .3mf</span>" : "")
        + (d.last_seen_at ? "<span>last seen <strong>" + escapeHtml(formatRelativeTime(d.last_seen_at)) + "</strong></span>" : "")
        + "</div>"
        + "</div>";
      html += this._renderFolderActions(d.folder_path, d.folder_launch, /*allowIntake*/ true);
      if (sidecar) html += this._renderSidecar(sidecar);
      html += "<div class='list-head'>"
        + "<div class='list-title'>" + (this._filesMode === "folders" ? "Folders" : "Files") + "</div>"
        + "<div class='mode-toggle'>"
        + "<button class='" + (this._filesMode === "files" ? "active" : "") + "' data-action='set-mode-files'>Files</button>"
        + "<button class='" + (this._filesMode === "folders" ? "active" : "") + "' data-action='set-mode-folders'>Folders</button>"
        + "</div>"
        + "</div>";
      if (this._filesError) {
        html += "<div class='alert'>" + escapeHtml(this._filesError) + "</div>";
      } else if (this._loadingFiles && !this._files) {
        html += "<div class='skeleton'></div><div class='skeleton'></div><div class='skeleton'></div>";
      } else if (this._filesMode === "folders") {
        html += this._renderFoldersList();
      } else {
        var files = (this._files && this._files.files) || [];
        html += this._renderFilesTable(files, d.folder_path);
      }
      return html;
    }

    _renderFolderActions(folderPath, folderLaunch, allowIntake) {
      var pathStr = String(folderPath || "");
      var canOpen = !!(folderLaunch && folderLaunch.can_open_in_explorer);
      var buttons = "";
      if (canOpen && pathStr) {
        buttons += "<button class='button compact' data-action='launch' data-launch='open_folder' data-path='"
          + escapeHtml(pathStr) + "'>Open folder in Explorer</button>";
      }
      if (pathStr) {
        buttons += "<button class='button compact' data-action='copy-path' data-path='"
          + escapeHtml(pathStr) + "'>Copy folder path</button>";
      }
      if (allowIntake && pathStr) {
        // Intake-from-folder is a future feature; rendered as a disabled hint for now.
        buttons += "<button class='button compact' disabled title='Coming soon — see design §2.2'>Run Intake from folder</button>";
      }
      if (!buttons) return "";
      return "<div class='detail-actions'>" + buttons + "</div>";
    }

    _renderSidecar(sidecar) {
      var html = "<div class='sidecar'>";
      var mm = sidecar.modelmeta || null;
      var readme = sidecar.readme || null;
      if (mm) {
        if (mm.notes || mm.description) {
          html += "<div class='sidecar-row'>"
            + "<div class='sidecar-label'>Notes</div>"
            + "<div class='sidecar-md'>" + escapeHtml(String(mm.notes || mm.description)) + "</div>"
            + "</div>";
        }
        if (Array.isArray(mm.tags) && mm.tags.length) {
          html += "<div class='sidecar-row'><div class='sidecar-label'>Tags</div><div class='sidecar-tags'>";
          for (var i = 0; i < mm.tags.length; i++) {
            html += "<span class='sidecar-tag'>" + escapeHtml(String(mm.tags[i])) + "</span>";
          }
          html += "</div></div>";
        }
        if (mm.origin_url || mm.source_url || mm.makerworld_url) {
          var url = String(mm.origin_url || mm.source_url || mm.makerworld_url);
          html += "<div class='sidecar-row'>"
            + "<div class='sidecar-label'>Origin</div>"
            + "<div class='sidecar-link'><a href='" + escapeHtml(url) + "' target='_blank' rel='noopener'>"
            + escapeHtml(url) + "</a></div>"
            + "</div>";
        }
        if (mm.primary_file) {
          html += "<div class='sidecar-row'>"
            + "<div class='sidecar-label'>Primary file</div>"
            + "<div class='detail-path'>" + escapeHtml(String(mm.primary_file)) + "</div>"
            + "</div>";
        }
      }
      if (readme && readme.text) {
        html += "<div class='sidecar-row'>"
          + "<div class='sidecar-label'>README</div>"
          + "<div class='sidecar-md'>" + escapeHtml(String(readme.text)) + "</div>"
          + "</div>";
      }
      html += "</div>";
      return html;
    }

    _renderFilesTable(files, parentPath) {
      if (!Array.isArray(files) || !files.length) {
        return "<div class='detail-empty muted'>No files.</div>";
      }
      var html = "<div class='file-table'><table><thead><tr>"
        + "<th>Type</th><th>Name</th><th>Size</th><th>Modified</th><th></th>"
        + "</tr></thead><tbody>";
      for (var i = 0; i < files.length; i++) {
        var f = files[i] || {};
        var nameRaw = String(f.file_name_raw || f.file_name_base_hint || basename(f.source_path_raw || ""));
        var ext = String(f.file_extension || extensionFromName(nameRaw));
        var size = formatBytes(f.file_size_bytes);
        var mtime = f.source_mtime || f.last_seen_at || f.detected_at;
        var path = String(f.source_path_raw || "");
        var launch = f.launch || {};
        var canSlicer = !!launch.can_launch_file && isSlicerLaunchableExtension(ext);
        var canExplorer = !!launch.can_open_in_explorer;
        var badgeClass = "ext-badge";
        if (isModelExtension(ext)) badgeClass += " x-" + ext.replace(/^\./, "");
        else if (isImageExtension(ext)) badgeClass += " x-img";
        var actions = "";
        if (canSlicer) {
          actions += "<button class='button compact' data-action='launch' data-launch='open_in_slicer' data-path='"
            + escapeHtml(path) + "' title='Open in slicer'>Slicer</button>";
        }
        if (canExplorer) {
          actions += "<button class='button compact' data-action='launch' data-launch='open_folder' data-path='"
            + escapeHtml(path) + "' title='Show in Explorer'>Folder</button>";
        }
        actions += "<button class='button compact' data-action='copy-path' data-path='"
          + escapeHtml(path) + "' title='Copy path'>Copy</button>";

        var displaySub = path && parentPath && path.indexOf(parentPath) === 0
          ? path.slice(parentPath.length).replace(/^[\\/]+/, "")
          : path;
        html += "<tr>"
          + "<td><span class='" + badgeClass + "'>" + escapeHtml(extensionBadge(ext)) + "</span></td>"
          + "<td>"
          + "<div class='file-name' title='" + escapeHtml(nameRaw) + "'>" + escapeHtml(nameRaw) + "</div>"
          + (displaySub && displaySub !== nameRaw
            ? "<div class='file-sub' title='" + escapeHtml(displaySub) + "'>" + escapeHtml(displaySub) + "</div>"
            : "")
          + "</td>"
          + "<td class='file-meta'>" + escapeHtml(size) + "</td>"
          + "<td class='file-meta' title='" + escapeHtml(formatDateTime(mtime)) + "'>"
          + escapeHtml(formatRelativeTime(mtime)) + "</td>"
          + "<td><div class='file-actions'>" + actions + "</div></td>"
          + "</tr>";
      }
      html += "</tbody></table></div>";
      return html;
    }

    _renderFoldersList() {
      var folders = (this._files && this._files.folders) || [];
      if (!folders.length) {
        return "<div class='detail-empty muted'>No subfolders.</div>";
      }
      var detail = this._detail || {};
      var html = "";
      for (var i = 0; i < folders.length; i++) {
        var fld = folders[i] || {};
        var pathStr = String(fld.path || "");
        var totalSize = this._sumSizes(fld.files);
        html += "<div class='folder-section'>"
          + "<div class='folder-section-head'>"
          + "<div>"
          + "<div>" + escapeHtml(basename(pathStr) || pathStr) + "</div>"
          + "<div class='folder-section-path'>" + escapeHtml(pathStr) + "</div>"
          + "</div>"
          + "<div class='file-meta'>"
          + "<strong>" + String(Number(fld.file_count || (fld.files ? fld.files.length : 0))) + "</strong> files · "
          + escapeHtml(formatBytes(totalSize))
          + "</div>"
          + "</div>"
          + this._renderFilesTable(fld.files || [], pathStr)
          + "</div>";
      }
      return html;
    }
  }

  if (!customElements.get("model-catalog-working-files-explorer-card")) {
    customElements.define("model-catalog-working-files-explorer-card", ModelCatalogWorkingFilesExplorerCard);
  }

  if (!window.customCards) window.customCards = [];
  window.customCards.push({
    type: "model-catalog-working-files-explorer-card",
    name: "Model Catalog: Working Files Explorer",
    description: "Filesystem-truth Working Files browser (single-view).",
  });
})();
