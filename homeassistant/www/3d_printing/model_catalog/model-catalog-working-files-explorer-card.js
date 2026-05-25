(function () {
  // ─── Utilities ──────────────────────────────────────────────────────────
  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function basename(pathValue) {
    var normalized = String(pathValue || '').replace(/\\/g, '/');
    if (!normalized) return '';
    var parts = normalized.split('/');
    return parts[parts.length - 1] || normalized;
  }

  function dirname(pathValue) {
    var normalized = String(pathValue || '').replace(/\\/g, '/');
    if (!normalized || normalized.indexOf('/') < 0) return normalized;
    return normalized.slice(0, normalized.lastIndexOf('/'));
  }

  function normalizePath(pathValue) {
    return String(pathValue || '').replace(/\\/g, '/');
  }

  function formatBytes(bytes) {
    var value = Number(bytes || 0);
    if (!Number.isFinite(value) || value <= 0) return '0 B';
    var units = ['B', 'KB', 'MB', 'GB', 'TB'];
    var index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
    var scaled = value / Math.pow(1024, index);
    return scaled.toFixed(scaled >= 10 || index === 0 ? 0 : 1) + ' ' + units[index];
  }

  function parseIsoDate(value) {
    if (!value) return null;
    var parsed = Date.parse(String(value));
    return Number.isFinite(parsed) ? new Date(parsed) : null;
  }

  function formatRelativeTime(value) {
    var parsed = parseIsoDate(value);
    if (!parsed) return '—';
    var seconds = Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 1000));
    if (seconds < 60) return 'just now';
    if (seconds < 3600) return Math.floor(seconds / 60) + 'm ago';
    if (seconds < 86400) return Math.floor(seconds / 3600) + 'h ago';
    if (seconds < 604800) return Math.floor(seconds / 86400) + 'd ago';
    return Math.floor(seconds / 604800) + 'w ago';
  }

  function formatDateTime(value) {
    var parsed = parseIsoDate(value);
    if (!parsed) return '—';
    try {
      return parsed.toLocaleString(undefined, {
        year: 'numeric', month: 'short', day: '2-digit',
        hour: '2-digit', minute: '2-digit',
      });
    } catch (_e) {
      return parsed.toISOString();
    }
  }

  function extensionFromPath(pathValue) {
    var name = basename(pathValue).toLowerCase();
    var index = name.lastIndexOf('.');
    return index >= 0 ? name.slice(index) : '';
  }

  function isModelExtension(extension) {
    return ['.3mf', '.stl', '.step', '.stp', '.obj'].indexOf(String(extension || '').toLowerCase()) >= 0;
  }

  function isImageExtension(extension) {
    return ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg', '.bmp'].indexOf(String(extension || '').toLowerCase()) >= 0;
  }

  function extensionBadge(extension) {
    return String(extension || '').replace(/^\./, '').toUpperCase() || 'FILE';
  }

  function fileThumbClass(extension) {
    var ext = String(extension || '').toLowerCase();
    if (ext === '.stl' || ext === '.obj') return 'stl';
    if (ext === '.step' || ext === '.stp') return 'step';
    if (isImageExtension(ext)) return 'img';
    if (ext === '.3mf') return '';
    return 'other';
  }

  function fileTypeLabel(extension) {
    var ext = String(extension || '').toLowerCase();
    if (isModelExtension(ext)) return 'model';
    if (isImageExtension(ext)) return 'image';
    return 'other';
  }

  function isSlicerLaunchableExtension(extension) {
    return String(extension || '').toLowerCase() === '.3mf';
  }

  function initialsFromTitle(value) {
    var title = String(value || '').trim();
    if (!title) return 'WG';
    var words = title.replace(/[^a-zA-Z0-9\s]+/g, ' ').trim().split(/\s+/).filter(Boolean);
    if (!words.length) return title.slice(0, 2).toUpperCase();
    if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
    return (words[0].charAt(0) + words[1].charAt(0)).toUpperCase();
  }

  // Deterministic 0..N-1 color index from a slug string.
  var THUMB_COLOR_COUNT = 8;
  function colorIndexFromSlug(value) {
    var str = String(value || '');
    var hash = 5381;
    for (var i = 0; i < str.length; i += 1) {
      hash = ((hash << 5) + hash + str.charCodeAt(i)) >>> 0;
    }
    return hash % THUMB_COLOR_COUNT;
  }

  // Image / 3MF extensions eligible for backend lazy preview endpoint.
  function isPreviewEligibleExtension(extension) {
    var ext = String(extension || '').toLowerCase();
    if (ext === '.3mf') return true;
    return isImageExtension(ext);
  }

  // Join two path-like segments with '/', skipping empties.
  function joinFolderPath(base, segment) {
    var a = String(base || '').replace(/\/+$/, '');
    var b = String(segment || '').replace(/^\/+/, '');
    if (!a) return b;
    if (!b) return a;
    return a + '/' + b;
  }

  // ─── HA service plumbing ────────────────────────────────────────────────
  async function authHeaders(hass, forceRefresh) {
    var auth = hass && hass.auth ? hass.auth : null;
    if (!auth) return {};
    if (forceRefresh && typeof auth.refreshAccessToken === 'function') {
      try { await auth.refreshAccessToken(); } catch (_e) { /* keep current token */ }
    }
    var token = auth.accessToken || (auth.data ? auth.data.accessToken : '');
    return token ? { Authorization: 'Bearer ' + token } : {};
  }

  function normalizeServiceResponse(payload) {
    if (Array.isArray(payload) && payload.length) return normalizeServiceResponse(payload[0]);
    if (payload && typeof payload === 'object') {
      if (payload.service_response && typeof payload.service_response === 'object') return normalizeServiceResponse(payload.service_response);
      if (payload.response && typeof payload.response === 'object') return normalizeServiceResponse(payload.response);
      if (payload.content && typeof payload.content === 'object'
          && (Object.prototype.hasOwnProperty.call(payload, 'status')
              || Object.prototype.hasOwnProperty.call(payload, 'headers'))) {
        return Object.assign({}, payload.content, { status: payload.status, headers: payload.headers });
      }
    }
    return payload && typeof payload === 'object' ? payload : {};
  }

  async function callServiceWithResponse(hass, domain, service, data) {
    var endpoint = '/api/services/' + encodeURIComponent(String(domain || '')) + '/' + encodeURIComponent(String(service || '')) + '?return_response';
    var body = JSON.stringify(data && typeof data === 'object' ? data : {});
    var response = await fetch(endpoint, {
      method: 'POST',
      headers: Object.assign({ 'Content-Type': 'application/json' }, await authHeaders(hass, false)),
      credentials: 'same-origin',
      body: body,
    });
    if (response.status === 401) {
      response = await fetch(endpoint, {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, await authHeaders(hass, true)),
        credentials: 'same-origin',
        body: body,
      });
    }
    var payload = {};
    try { payload = await response.json(); } catch (_e) { payload = {}; }
    if (!response.ok) {
      var message = payload && payload.message ? String(payload.message) : ('Service call failed (HTTP ' + String(response.status) + ')');
      throw new Error(message);
    }
    var normalized = normalizeServiceResponse(payload);
    if (normalized && normalized.success === false) {
      throw new Error(normalized.message || normalized.error || 'Request failed.');
    }
    if (normalized && typeof normalized.status === 'number' && normalized.status >= 400) {
      throw new Error(normalized.message || ('Request failed (HTTP ' + String(normalized.status) + ').'));
    }
    return normalized;
  }

  // ─── Constants ──────────────────────────────────────────────────────────
  var LOOSE_SLUG = '__loose__';
  var THUMB_SIZES = ['small', 'medium', 'large'];
  var TYPE_FILTERS = ['all', 'models', 'images', 'other'];
  var GROUP_FILTERS = ['all', 'with_sidecar', 'missing_sidecar', 'recent'];
  var SORT_OPTIONS = [
    { value: 'recent', label: 'Recently modified' },
    { value: 'name', label: 'Folder name (A→Z)' },
    { value: 'count', label: 'File count (high → low)' },
    { value: 'loose_first', label: 'Loose first, then folders' },
  ];

  // ─── Styles (adapted from working-files-folder-first-v1.html) ───────────
  var STYLES = ''
    + 'ha-card{border-radius:0;border:none;background:transparent;box-shadow:none;}'
    + ':host{--bg-card:rgba(28,33,42,0.92);--bg-strip:rgba(15,19,26,0.55);--border:rgba(148,163,184,0.18);--border-strong:rgba(148,163,184,0.32);--text:#e6edf3;--text-secondary:#9aa4b2;--text-muted:#6b7480;--accent:#5eead4;--accent-blue:#60a5fa;--accent-violet:#c4b5fd;--primary-amber:#f5c242;--shadow:0 4px 18px rgba(0,0,0,0.32);color:var(--text);font-family:"Inter",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}'
    + '.shell{display:grid;gap:14px;padding:6px 10px 10px;}'
    + '.banner{padding:10px 14px;border-radius:10px;border:1px solid var(--border);background:rgba(15,19,26,0.45);font-size:12.5px;color:var(--text-secondary);}'
    + '.banner.error{border-color:rgba(252,165,165,0.4);color:#fca5a5;background:rgba(252,165,165,0.06);}'
    + '.banner.status{border-color:rgba(94,234,212,0.28);color:var(--accent);background:rgba(94,234,212,0.06);}'
    /* Toolbar */
    + '.toolbar-shell{background:var(--bg-card);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow);overflow:hidden;}'
    + '.title-row{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:14px 18px;flex-wrap:wrap;}'
    + '.title-row .title{display:inline-flex;align-items:baseline;gap:12px;}'
    + '.title-row .title strong{font-size:17px;font-weight:800;}'
    + '.title-row .title .subtitle{font-size:12px;color:var(--text-muted);}'
    + '.title-row .right{display:inline-flex;gap:8px;align-items:center;flex-wrap:wrap;}'
    + '.indexed-pill{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:999px;background:rgba(94,234,212,0.06);border:1px solid rgba(94,234,212,0.22);color:var(--accent);font-size:11px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;}'
    + '.indexed-pill .dot{width:6px;height:6px;border-radius:50%;background:var(--accent);box-shadow:0 0 6px rgba(94,234,212,0.7);}'
    + '.thumb-size-toggle{display:inline-flex;padding:2px;background:rgba(15,19,26,0.6);border:1px solid var(--border);border-radius:999px;}'
    + '.thumb-size-toggle button{background:transparent;border:0;color:var(--text-secondary);padding:4px 11px;font-size:10.5px;font-weight:700;border-radius:999px;cursor:pointer;letter-spacing:0.06em;text-transform:uppercase;min-height:24px;}'
    + '.thumb-size-toggle button.active{background:rgba(167,139,250,0.20);color:#ddd6fe;}'
    + '.icon-btn{padding:0 12px;height:30px;border-radius:8px;border:1px solid rgba(148,163,184,0.24);background:rgba(148,163,184,0.10);color:var(--text);display:inline-flex;align-items:center;gap:6px;cursor:pointer;font-size:12px;font-weight:700;}'
    + '.icon-btn:hover:not(:disabled){background:rgba(148,163,184,0.20);}'
    + '.icon-btn:disabled{opacity:0.55;cursor:wait;}'
    + '.filterbar{padding:10px 18px;border-top:1px dashed var(--border);display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;}'
    + '.filterbar .left,.filterbar .right{display:inline-flex;align-items:center;gap:10px;flex-wrap:wrap;}'
    + '.filterbar .label{font-size:10.5px;letter-spacing:0.06em;text-transform:uppercase;color:var(--text-muted);font-weight:700;}'
    + '.chip-filter{display:inline-flex;align-items:center;gap:5px;font-size:11px;padding:5px 10px;border-radius:999px;background:rgba(255,255,255,0.04);border:1px solid var(--border);color:var(--text-secondary);cursor:pointer;}'
    + '.chip-filter.active{background:rgba(94,234,212,0.14);border-color:rgba(94,234,212,0.32);color:var(--accent);}'
    + '.sort{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;background:rgba(255,255,255,0.04);border:1px solid var(--border);}'
    + '.sort label{font-size:10px;color:var(--text-muted);letter-spacing:0.06em;text-transform:uppercase;font-weight:700;}'
    + '.sort select{background:transparent;border:0;color:var(--text);font-size:12px;cursor:pointer;outline:none;}'
    /* Group stack */
    + '.groups{display:grid;gap:12px;}'
    + '.group-row{position:relative;background:var(--bg-card);border:1px solid var(--border);border-radius:14px;padding:14px 16px 12px 16px;box-shadow:var(--shadow);transition:border-color 120ms ease;}'
    + '.group-row:hover{border-color:var(--border-strong);}'
    + '.group-header{display:grid;grid-template-columns:52px minmax(0,1fr) auto;gap:14px;align-items:start;cursor:pointer;}'
    + '.group-thumb{width:52px;height:52px;border-radius:10px;border:1px solid rgba(96,165,250,0.28);background:linear-gradient(135deg,rgba(96,165,250,0.18),rgba(96,165,250,0.06));color:#bfdbfe;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:800;letter-spacing:0.02em;flex-shrink:0;}'
    + '.group-thumb.no-sidecar{background:rgba(252,165,165,0.10);border-color:rgba(252,165,165,0.28);color:#fca5a5;}'
    + '.group-thumb.virtual{background:rgba(148,163,184,0.08);border-color:var(--border);color:var(--text-muted);font-weight:400;}'
    /* Per-slug color palette (applied only when sidecar exists and not virtual/loose) */
    + '.group-thumb.gc0{background:linear-gradient(135deg,rgba(96,165,250,0.22),rgba(96,165,250,0.06));border-color:rgba(96,165,250,0.32);color:#bfdbfe;}'
    + '.group-thumb.gc1{background:linear-gradient(135deg,rgba(167,139,250,0.22),rgba(167,139,250,0.06));border-color:rgba(167,139,250,0.32);color:#ddd6fe;}'
    + '.group-thumb.gc2{background:linear-gradient(135deg,rgba(94,234,212,0.22),rgba(94,234,212,0.06));border-color:rgba(94,234,212,0.32);color:#a7f3d0;}'
    + '.group-thumb.gc3{background:linear-gradient(135deg,rgba(245,194,66,0.22),rgba(245,194,66,0.06));border-color:rgba(245,194,66,0.32);color:#fde68a;}'
    + '.group-thumb.gc4{background:linear-gradient(135deg,rgba(244,114,182,0.22),rgba(244,114,182,0.06));border-color:rgba(244,114,182,0.32);color:#fbcfe8;}'
    + '.group-thumb.gc5{background:linear-gradient(135deg,rgba(248,113,113,0.22),rgba(248,113,113,0.06));border-color:rgba(248,113,113,0.32);color:#fecaca;}'
    + '.group-thumb.gc6{background:linear-gradient(135deg,rgba(132,204,22,0.22),rgba(132,204,22,0.06));border-color:rgba(132,204,22,0.32);color:#d9f99d;}'
    + '.group-thumb.gc7{background:linear-gradient(135deg,rgba(56,189,248,0.22),rgba(56,189,248,0.06));border-color:rgba(56,189,248,0.32);color:#bae6fd;}'
    + '.group-thumb.virtual .stack{display:grid;gap:2px;}'
    + '.group-thumb.virtual .stack span{display:block;width:22px;height:4px;border-radius:2px;background:rgba(148,163,184,0.45);}'
    + '.group-thumb.virtual .stack span:nth-child(2){background:rgba(148,163,184,0.32);width:18px;}'
    + '.group-thumb.virtual .stack span:nth-child(3){background:rgba(148,163,184,0.22);width:20px;}'
    + '.group-meta{min-width:0;}'
    + '.group-title-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}'
    + '.group-title{font-size:15px;font-weight:700;letter-spacing:-0.005em;overflow-wrap:anywhere;}'
    + '.group-row.virtual .group-title{color:var(--text-secondary);font-style:italic;}'
    + '.override-badge{font-size:10px;padding:1px 6px;border-radius:4px;background:rgba(245,194,66,0.14);color:var(--primary-amber);border:1px solid rgba(245,194,66,0.28);font-weight:700;letter-spacing:0.04em;text-transform:uppercase;}'
    + '.virtual-badge{font-size:10px;padding:1px 6px;border-radius:4px;background:rgba(148,163,184,0.10);color:var(--text-muted);border:1px solid var(--border);font-weight:700;letter-spacing:0.04em;text-transform:uppercase;}'
    + '.sidecar-dots{display:inline-flex;gap:4px;margin-left:4px;}'
    + '.sidecar-dot{width:7px;height:7px;border-radius:50%;background:rgba(148,163,184,0.25);}'
    + '.sidecar-dot.on{background:var(--accent);}'
    + '.sidecar-dot.warn{background:#fca5a5;}'
    + '.folder-hint{font-size:11.5px;color:var(--text-muted);font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,monospace;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
    + '.group-counts{display:flex;gap:12px;margin-top:6px;flex-wrap:wrap;}'
    + '.count{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;color:var(--text-secondary);font-variant-numeric:tabular-nums;}'
    + '.count .num{font-weight:700;color:var(--text);font-size:12.5px;}'
    + '.group-right{display:flex;align-items:center;gap:6px;align-self:start;}'
    + '.updated{font-size:11px;color:var(--text-muted);font-variant-numeric:tabular-nums;text-align:right;}'
    + '.updated strong{color:var(--text-secondary);font-weight:600;display:block;}'
    + '.overflow-btn{width:28px;height:28px;padding:0;border-radius:8px;background:transparent;border:1px solid transparent;color:var(--text-muted);cursor:pointer;font-size:16px;line-height:1;}'
    + '.overflow-btn:hover{background:rgba(255,255,255,0.06);color:var(--text);border-color:var(--border);}'
    + '.expander{width:26px;height:26px;padding:0;background:transparent;border:0;color:var(--text-muted);cursor:pointer;font-size:14px;}'
    + '.expander:hover{color:var(--text);}'
    + '.group-row.collapsed .group-body{display:none;}'
    + '.group-row.collapsed{padding-bottom:14px;}'
    /* Overflow menu */
    + '.overflow-menu{position:absolute;right:12px;top:56px;background:rgba(20,24,32,0.98);border:1px solid var(--border-strong);border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,0.45);padding:6px;min-width:240px;z-index:5;}'
    + '.overflow-menu button{display:flex;align-items:center;gap:8px;width:100%;background:transparent;border:0;color:var(--text);padding:7px 10px;border-radius:6px;font-size:12.5px;cursor:pointer;text-align:left;}'
    + '.overflow-menu button:hover{background:rgba(255,255,255,0.06);}'
    + '.overflow-menu button:disabled{opacity:0.45;cursor:not-allowed;}'
    + '.overflow-menu .sep{height:1px;background:var(--border);margin:4px 0;}'
    /* Group body */
    + '.group-body{margin-top:14px;padding-top:14px;border-top:1px solid var(--border);}'
    + '.body-loading{font-size:12px;color:var(--text-muted);padding:14px 4px;}'
    /* Sidecar strip */
    + '.sidecar{display:grid;grid-template-columns:1fr auto;gap:14px;padding:12px 14px;border:1px solid var(--border);border-radius:12px;background:rgba(15,19,26,0.45);}'
    + '.sidecar .body{min-width:0;}'
    + '.sidecar .tags{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px;}'
    + '.sidecar .tag{display:inline-flex;align-items:center;padding:2px 8px;border-radius:999px;background:rgba(96,165,250,0.10);border:1px solid rgba(96,165,250,0.28);color:#bfdbfe;font-size:10.5px;font-weight:600;}'
    + '.sidecar .notes{padding:9px 11px;border:1px dashed var(--border);border-radius:8px;background:rgba(255,255,255,0.02);font-size:12px;color:var(--text);line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere;}'
    + '.sidecar .notes h4{margin:0 0 4px;font-size:10px;letter-spacing:0.06em;text-transform:uppercase;color:var(--text-muted);font-weight:700;display:inline-flex;align-items:center;gap:6px;}'
    + '.sidecar .notes h4 .file-ref{color:var(--text-muted);font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,monospace;text-transform:none;letter-spacing:0;font-size:10.5px;font-weight:400;}'
    + '.sidecar .meta-source{margin-top:8px;font-size:10.5px;color:var(--text-muted);font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,monospace;overflow-wrap:anywhere;}'
    + '.sidecar .meta-source button{background:transparent;border:0;color:var(--accent);text-decoration:none;cursor:pointer;font:inherit;padding:0;}'
    + '.sidecar .meta-source button:hover{text-decoration:underline;}'
    + '.sidecar .side{display:grid;gap:6px;align-content:start;min-width:160px;}'
    + '.sidecar .side .kv{font-size:11px;color:var(--text-secondary);font-variant-numeric:tabular-nums;overflow-wrap:anywhere;}'
    + '.sidecar .side .kv .k{color:var(--text-muted);display:inline-block;min-width:70px;}'
    + '.sidecar.empty{grid-template-columns:1fr;background:rgba(255,255,255,0.02);border-style:dashed;color:var(--text-muted);font-size:12px;text-align:center;padding:10px 14px;}'
    + '.sidecar.empty code{background:rgba(255,255,255,0.06);padding:1px 5px;border-radius:4px;font-size:11px;}'
    /* Type chip bar */
    + '.type-bar{margin-top:12px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;}'
    + '.type-chips{display:inline-flex;gap:5px;flex-wrap:wrap;}'
    + '.type-chip{display:inline-flex;align-items:center;gap:5px;padding:4px 10px;border-radius:999px;background:rgba(255,255,255,0.04);border:1px solid var(--border);color:var(--text-secondary);font-size:11px;font-weight:700;cursor:pointer;}'
    + '.type-chip .ct{color:var(--text-muted);font-weight:600;}'
    /* Per-category colors mirror model-catalog-browser-card compact file-kind chips */
    + '.type-chip.cat-all.active{background:rgba(139,92,246,0.16);border-color:rgba(167,139,250,0.34);color:#c4b5fd;}'
    + '.type-chip.cat-all.active .ct{color:#c4b5fd;}'
    + '.type-chip.cat-models.active{background:rgba(0,137,123,0.16);border-color:rgba(125,211,200,0.30);color:#7dd3c8;}'
    + '.type-chip.cat-models.active .ct{color:#7dd3c8;}'
    + '.type-chip.cat-images.active{background:rgba(37,99,235,0.16);border-color:rgba(147,197,253,0.34);color:#93c5fd;}'
    + '.type-chip.cat-images.active .ct{color:#93c5fd;}'
    + '.type-chip.cat-other.active{background:rgba(245,158,11,0.16);border-color:rgba(252,211,77,0.34);color:#fcd34d;}'
    + '.type-chip.cat-other.active .ct{color:#fcd34d;}'
    /* Files|Folders view-mode toggle */
    + '.view-toggle{display:inline-flex;padding:2px;background:rgba(15,19,26,0.6);border:1px solid var(--border);border-radius:999px;}'
    + '.view-toggle button{background:transparent;border:0;color:var(--text-secondary);padding:4px 11px;font-size:10.5px;font-weight:700;border-radius:999px;cursor:pointer;letter-spacing:0.06em;text-transform:uppercase;min-height:24px;display:inline-flex;align-items:center;gap:5px;}'
    + '.view-toggle button.active{background:rgba(96,165,250,0.20);color:#bfdbfe;}'
    /* Breadcrumb + folder rows */
    + '.folder-breadcrumbs{margin-top:10px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:11.5px;color:var(--text-secondary);font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,monospace;}'
    + '.breadcrumb-up{width:24px;height:24px;padding:0;border-radius:6px;background:rgba(148,163,184,0.10);border:1px solid var(--border);color:var(--text);cursor:pointer;font-size:13px;line-height:1;display:inline-flex;align-items:center;justify-content:center;}'
    + '.breadcrumb-up:hover:not(:disabled){background:rgba(148,163,184,0.20);}'
    + '.breadcrumb-up:disabled{opacity:0.4;cursor:not-allowed;}'
    + '.breadcrumb-link{background:transparent;border:0;color:var(--accent-blue);cursor:pointer;font:inherit;padding:0 2px;border-radius:4px;}'
    + '.breadcrumb-link:hover{text-decoration:underline;}'
    + '.crumb-sep{color:var(--text-muted);}'
    + '.crumb-current{color:var(--text);font-weight:600;}'
    + '.folder-row{display:grid;grid-template-columns:var(--thumb-size,34px) minmax(0,1fr) 110px auto;gap:12px;align-items:center;padding:var(--row-pad,6px 8px);border-radius:10px;background:rgba(96,165,250,0.04);border:1px solid var(--border);cursor:pointer;transition:background 100ms ease;}'
    + '.folder-row:hover{background:rgba(96,165,250,0.10);}'
    + '.folder-row .folder-thumb{width:var(--thumb-size,34px);height:var(--thumb-size,34px);border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:calc(var(--thumb-size,34px) * 0.55);line-height:1;background:rgba(96,165,250,0.10);color:var(--accent-blue);border:1px solid rgba(96,165,250,0.28);}'
    + '.folder-row .folder-name{font-size:13px;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
    + '.folder-row .folder-sub{margin-top:2px;font-size:10.5px;color:var(--text-muted);font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
    + '.folder-row .folder-count{font-size:11.5px;color:var(--text-secondary);font-variant-numeric:tabular-nums;text-align:right;}'
    /* Lazy preview image inside file thumb */
    + '.file-thumb img.preview-img{width:100%;height:100%;object-fit:cover;border-radius:7px;display:block;opacity:0;transition:opacity 150ms ease;}'
    + '.file-thumb img.preview-img.loaded{opacity:1;}'
    + '.file-thumb.has-preview{padding:0;overflow:hidden;background:rgba(15,19,26,0.55);border-color:var(--border);}'
    /* File rows */
    + '.group-row[data-thumb="small"]{--thumb-size:34px;--row-pad:6px 8px;}'
    + '.group-row[data-thumb="medium"]{--thumb-size:58px;--row-pad:8px 10px;}'
    + '.group-row[data-thumb="large"]{--thumb-size:116px;--row-pad:10px 12px;}'
    + '.file-list{margin-top:10px;display:grid;gap:4px;}'
    + '.file-row{display:grid;grid-template-columns:var(--thumb-size,34px) minmax(0,1fr) 90px 110px auto;gap:12px;align-items:center;padding:var(--row-pad,6px 8px);border-radius:10px;background:rgba(255,255,255,0.015);border:1px solid transparent;transition:background 100ms ease;}'
    + '.file-row:hover{background:rgba(255,255,255,0.045);border-color:var(--border);}'
    + '.file-thumb{width:var(--thumb-size,34px);height:var(--thumb-size,34px);border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:calc(var(--thumb-size,34px) * 0.32);line-height:1;letter-spacing:-0.02em;background:rgba(94,234,212,0.10);color:var(--accent);border:1px solid rgba(94,234,212,0.28);}'
    + '.file-thumb.stl{background:rgba(96,165,250,0.10);color:var(--accent-blue);border-color:rgba(96,165,250,0.28);}'
    + '.file-thumb.step{background:rgba(167,139,250,0.10);color:var(--accent-violet);border-color:rgba(167,139,250,0.28);}'
    + '.file-thumb.img{background:rgba(245,194,66,0.10);color:var(--primary-amber);border-color:rgba(245,194,66,0.28);}'
    + '.file-thumb.other{background:rgba(148,163,184,0.10);color:var(--text-secondary);border-color:var(--border);}'
    + '.file-main{min-width:0;}'
    + '.file-name{font-size:13px;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
    + '.file-path{margin-top:2px;font-size:10.5px;color:var(--text-muted);font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
    + '.file-meta{font-size:11px;color:var(--text-secondary);font-variant-numeric:tabular-nums;text-align:right;}'
    + '.file-meta .sub{display:block;font-size:10px;color:var(--text-muted);margin-top:1px;}'
    + '.file-actions{display:inline-flex;gap:4px;justify-content:flex-end;align-items:center;flex-wrap:wrap;}'
    + '.file-action-split{position:relative;display:inline-flex;align-items:stretch;border:1px solid rgba(94,234,212,0.32);border-radius:8px;overflow:hidden;background:rgba(94,234,212,0.10);}'
    + '.file-action-split button{background:transparent;border:0;color:var(--accent);padding:5px 10px;font-size:11.5px;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;gap:5px;}'
    + '.file-action-split .open-main:hover{background:rgba(94,234,212,0.18);}'
    + '.file-action-split .file-action-toggle{padding:5px 7px;border-left:1px solid rgba(94,234,212,0.32);font-size:10px;}'
    + '.file-action-split .file-action-toggle:hover{background:rgba(94,234,212,0.18);}'
    + '.file-action-menu{position:absolute;right:0;top:calc(100% + 4px);background:rgba(20,24,32,0.98);border:1px solid var(--border-strong);border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,0.45);padding:4px;min-width:180px;z-index:10;display:flex;flex-direction:column;gap:2px;}'
    + '.file-action-menu button{background:transparent;border:0;color:var(--text);padding:6px 10px;font-size:11.5px;cursor:pointer;border-radius:6px;text-align:left;}'
    + '.file-action-menu button:hover{background:rgba(255,255,255,0.06);}'
    + '.btn-ghost{background:transparent;border:1px solid var(--border);color:var(--text-secondary);padding:4px 9px;border-radius:8px;font-size:11.5px;cursor:pointer;}'
    + '.btn-ghost:hover{background:rgba(255,255,255,0.04);color:var(--text);}'
    + '.empty-row{padding:14px;text-align:center;color:var(--text-muted);font-size:12px;border:1px dashed var(--border);border-radius:10px;background:rgba(255,255,255,0.02);}'
    + '@media (max-width:980px){.group-header{grid-template-columns:44px minmax(0,1fr);}.group-right{grid-column:1 / -1;justify-items:start;text-align:left;}.file-row{grid-template-columns:var(--thumb-size,34px) minmax(0,1fr) auto;}.file-row .file-meta{display:none;}}';

  // ─── Card class ─────────────────────────────────────────────────────────
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
      this._reindexing = false;
      this._tree = null;                // tree response payload
      this._lastIndexedAt = '';
      this._groupDetails = {};          // slug -> { detail, files, loading }
      this._collapsedGroups = {};       // slug -> bool (true = collapsed)
      this._typeFilters = {};           // slug -> 'all'|'models'|'images'|'other'
      this._thumbSize = 'medium';
      this._groupFilter = 'all';
      this._sort = 'recent';
      this._fileActionMenuKey = '';     // composite key 'slug|path'
      this._overflowMenuSlug = '';
      this._catalogScope = 'working';
      this._lastAppliedScopeStamp = 0;
      // Folder-navigation view-mode state (per non-loose group)
      this._groupViewMode = {};         // slug -> 'files'|'folders'
      this._groupFolderPath = {};       // slug -> current subfolder path under group root
      this._groupFolders = {};          // slug -> { folders: [{path,file_count,files}], loadedAt }
      this._previewObserver = null;
      this._boundClick = this._handleClick.bind(this);
      this._boundCatalogDataChanged = this._handleCatalogDataChanged.bind(this);
    }

    setConfig(config) {
      this._config = {
        title: config && config.title ? String(config.title) : 'Working Files',
      };
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      if (this.isConnected && !this._loading && this._tree === null) {
        this._loadTree();
      } else if (this.isConnected && !this._loading && this._isScopeStale()) {
        this._loadTree();
      }
    }

    connectedCallback() {
      if (this.shadowRoot) this.shadowRoot.addEventListener('click', this._boundClick);
      window.addEventListener('model-catalog-data-changed', this._boundCatalogDataChanged);
      this._ensurePreviewObserver();
      if (this._hass && !this._loading && this._tree === null) {
        this._loadTree();
      }
    }

    disconnectedCallback() {
      if (this.shadowRoot) this.shadowRoot.removeEventListener('click', this._boundClick);
      window.removeEventListener('model-catalog-data-changed', this._boundCatalogDataChanged);
      if (this._previewObserver) {
        try { this._previewObserver.disconnect(); } catch (_e) { /* ignore */ }
        this._previewObserver = null;
      }
    }

    getCardSize() { return 16; }

    _isScopeStale() {
      var shared = window.ModelCatalogIntakeShared;
      if (!shared || typeof shared.getModelCatalogScopeStamp !== 'function') return false;
      var latest = shared.getModelCatalogScopeStamp(this._catalogScope || 'working');
      return latest > (Number(this._lastAppliedScopeStamp) || 0);
    }

    _handleCatalogDataChanged(event) {
      var detail = event && event.detail && typeof event.detail === 'object' ? event.detail : {};
      var scopes = Array.isArray(detail.scopes) ? detail.scopes : [];
      if (scopes.length && scopes.indexOf('working') < 0 && scopes.indexOf('all') < 0) return;
      var stamp = Number(detail.stamp || 0) || 0;
      if (stamp) this._lastAppliedScopeStamp = stamp;
      this._refreshTree();
    }

    // ─── Data fetch ───────────────────────────────────────────────────────
    async _loadTree(options) {
      if (!this._hass || this._loading) return;
      this._loading = true;
      this._loadingPhase = (options && options.silent) ? '' : 'Loading working files...';
      this._error = '';
      this._render();
      try {
        var response = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_working_files_tree', {});
        this._tree = response || {};
        this._lastIndexedAt = new Date().toISOString();
        // Default expansion state: all collapsed except the first non-loose if nothing set yet
        var groups = Array.isArray(this._tree.groups) ? this._tree.groups : [];
        groups.forEach(function (group) {
          var slug = String(group && group.slug || '');
          if (!slug) return;
          if (!Object.prototype.hasOwnProperty.call(this._collapsedGroups, slug)) {
            this._collapsedGroups[slug] = true;
          }
          if (!Object.prototype.hasOwnProperty.call(this._typeFilters, slug)) {
            this._typeFilters[slug] = 'all';
          }
        }, this);
        if (!Object.prototype.hasOwnProperty.call(this._collapsedGroups, LOOSE_SLUG)) {
          this._collapsedGroups[LOOSE_SLUG] = true;
        }
        if (!Object.prototype.hasOwnProperty.call(this._typeFilters, LOOSE_SLUG)) {
          this._typeFilters[LOOSE_SLUG] = 'all';
        }
        var shared = window.ModelCatalogIntakeShared;
        if (shared && typeof shared.getModelCatalogScopeStamp === 'function') {
          this._lastAppliedScopeStamp = shared.getModelCatalogScopeStamp(this._catalogScope || 'working');
        }
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not load working files.';
      } finally {
        this._loading = false;
        this._loadingPhase = '';
        this._render();
      }
    }

    async _refreshTree() {
      await this._loadTree({ silent: true });
      // Re-fetch any already-expanded groups so counts/files stay fresh
      Object.keys(this._collapsedGroups).forEach(function (slug) {
        if (!this._collapsedGroups[slug]) {
          this._loadGroup(slug, { force: true });
        }
      }, this);
    }

    async _reindex() {
      if (!this._hass || this._reindexing) return;
      this._reindexing = true;
      this._status = 'Re-indexing working files...';
      this._render();
      try {
        await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_reindex_working_files', {
          recurse: true,
          compute_hashes: false,
        });
        this._status = 'Re-index complete. Refreshing...';
        await this._refreshTree();
        this._status = '';
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not re-index working files.';
      } finally {
        this._reindexing = false;
        this._render();
      }
    }

    async _loadGroup(slug, options) {
      var normalized = String(slug || '');
      if (!normalized || !this._hass) return;
      var force = !!(options && options.force);
      var entry = this._groupDetails[normalized];
      if (entry && entry.loading) return;
      if (entry && !force && entry.files && entry.detail) return;
      this._groupDetails[normalized] = Object.assign({}, entry || {}, { loading: true, error: '' });
      this._render();
      try {
        if (normalized === LOOSE_SLUG) {
          var loose = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_working_files_loose', {
            limit: 500, offset: 0,
          });
          this._groupDetails[normalized] = {
            loading: false,
            detail: null,
            files: Array.isArray(loose && loose.files) ? loose.files : [],
            pagination: loose && loose.pagination ? loose.pagination : null,
            error: '',
          };
        } else {
          var detail = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_working_files_group_detail', {
            folder_slug: normalized,
          });
          var filesResp = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_working_files_group_files', {
            folder_slug: normalized,
            mode: 'files',
            limit: 500,
            offset: 0,
          });
          this._groupDetails[normalized] = {
            loading: false,
            detail: detail,
            files: Array.isArray(filesResp && filesResp.files) ? filesResp.files : [],
            pagination: filesResp && filesResp.pagination ? filesResp.pagination : null,
            error: '',
          };
          // If user is currently viewing in folders mode, also (re)fetch folders payload.
          if (this._groupViewMode[normalized] === 'folders') {
            this._loadGroupFolders(normalized, { force: true });
          }
        }
      } catch (error) {
        this._groupDetails[normalized] = Object.assign({}, this._groupDetails[normalized] || {}, {
          loading: false,
          error: error && error.message ? String(error.message) : 'Could not load group.',
        });
      } finally {
        this._render();
      }
    }

    async _loadGroupFolders(slug, options) {
      var normalized = String(slug || '');
      if (!normalized || normalized === LOOSE_SLUG || !this._hass) return;
      var force = !!(options && options.force);
      var cached = this._groupFolders[normalized];
      if (cached && cached.loading) return;
      if (cached && !force && Array.isArray(cached.folders)) return;
      this._groupFolders[normalized] = Object.assign({}, cached || {}, { loading: true, error: '' });
      this._render();
      try {
        var resp = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_working_files_group_files', {
          folder_slug: normalized,
          mode: 'folders',
          limit: 500,
          offset: 0,
        });
        this._groupFolders[normalized] = {
          loading: false,
          folders: Array.isArray(resp && resp.folders) ? resp.folders : [],
          error: '',
        };
      } catch (error) {
        this._groupFolders[normalized] = {
          loading: false,
          folders: [],
          error: error && error.message ? String(error.message) : 'Could not load folders.',
        };
      } finally {
        this._render();
      }
    }

    // ─── Sidecar / preview URL helpers ────────────────────────────────────
    _resolveSidecarUrl() {
      var configured = this._config && this._config.model_sidecar_url ? String(this._config.model_sidecar_url) : '';
      var hass = this._hass;
      var state = '';
      if (hass && hass.states && hass.states['input_text.model_catalog_sidecar_base_url']) {
        state = String(hass.states['input_text.model_catalog_sidecar_base_url'].state || '');
      }
      var resolved = state && ['unknown', 'unavailable', 'none', ''].indexOf(state.toLowerCase()) < 0
        ? state
        : configured;
      return String(resolved || '').replace(/\/+$/, '');
    }

    _filePreviewUrl(entry) {
      if (!entry || typeof entry !== 'object') return '';
      var ext = String(entry.file_extension || extensionFromPath(entry.source_path_canonical || entry.path || '')).toLowerCase();
      if (!isPreviewEligibleExtension(ext)) return '';
      var canonical = String(entry.source_path_canonical || '').trim();
      if (!canonical) return '';
      var base = this._resolveSidecarUrl();
      if (!base) return '';
      return base + '/api/working-files/preview?path=' + encodeURIComponent(canonical);
    }

    _ensurePreviewObserver() {
      if (this._previewObserver) return this._previewObserver;
      if (typeof IntersectionObserver !== 'function') return null;
      var self = this;
      this._previewObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (record) {
          if (!record.isIntersecting) return;
          var img = record.target;
          var src = img && img.dataset ? img.dataset.lazySrc : '';
          if (src && !img.src) {
            img.src = src;
          }
          self._previewObserver.unobserve(img);
        });
      }, { rootMargin: '120px 0px', threshold: 0.01 });
      return this._previewObserver;
    }

    _attachLazyPreviews() {
      if (!this.shadowRoot) return;
      var observer = this._ensurePreviewObserver();
      var nodes = this.shadowRoot.querySelectorAll('img[data-lazy-src]:not([data-lazy-bound])');
      for (var i = 0; i < nodes.length; i += 1) {
        var img = nodes[i];
        img.dataset.lazyBound = '1';
        img.addEventListener('load', function () { this.classList.add('loaded'); });
        img.addEventListener('error', function () {
          var thumb = this.parentNode;
          if (thumb && thumb.classList) thumb.classList.remove('has-preview');
          if (thumb) thumb.removeChild(this);
        });
        if (observer) {
          observer.observe(img);
        } else {
          // Fallback: load immediately if no IntersectionObserver
          img.src = img.dataset.lazySrc;
        }
      }
    }

    // ─── Local helper / desktop actions (read-only side, kept) ────────────
    _openWindow(url, target) {
      var normalized = String(url || '').trim();
      if (!normalized) return;
      var anchor = document.createElement('a');
      anchor.href = normalized;
      anchor.target = target || '_self';
      anchor.rel = 'noopener noreferrer';
      anchor.style.display = 'none';
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
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
        : (action === 'open_in_slicer' ? 'Opening file in slicer...' : 'Opening file locally...');
      this._error = '';
      this._render();
      try {
        var response = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_create_working_file_local_action_token', {
          action: action,
          path: normalizedPath,
        });
        var launchUrl = String(response && response.launch_url ? response.launch_url : '').trim();
        if (!launchUrl) throw new Error('No helper launch URL was returned.');
        this._openWindow(launchUrl, '_self');
        this._showToast('Requested local action. If nothing happens, install or re-register the desktop helper.');
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not launch the local helper action.';
        this._render();
      }
    }

    _copyToClipboard(value) {
      var text = String(value || '');
      if (!text) return;
      var done = function (success) {
        this._showToast(success ? 'Copied path to clipboard.' : 'Failed to copy path.');
      }.bind(this);
      try {
        if (navigator && navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function () { done(true); }).catch(function () { done(false); });
          return;
        }
      } catch (_e) { /* fall through */ }
      try {
        var ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        done(true);
      } catch (_e) { done(false); }
    }

    _showToast(message) {
      this._status = String(message || '');
      this._render();
      var msg = this._status;
      setTimeout(function () {
        if (this._status === msg) {
          this._status = '';
          this._render();
        }
      }.bind(this), 3000);
    }

    // ─── Helpers ──────────────────────────────────────────────────────────
    _entryPath(entry) {
      return String((entry && (entry.source_path_canonical || entry.source_path_raw)) || '').trim();
    }

    _entryExtension(entry) {
      return String((entry && entry.file_extension) || extensionFromPath(this._entryPath(entry)) || '').toLowerCase();
    }

    _entryMtime(entry) {
      if (!entry || typeof entry !== 'object') return '';
      return String(entry.source_mtime || entry.last_seen_at || '');
    }

    _entrySize(entry) {
      var bytes = entry && entry.file_size_bytes;
      return Number.isFinite(Number(bytes)) ? Number(bytes) : 0;
    }

    _entryCategory(entry) {
      var ext = this._entryExtension(entry);
      if (isModelExtension(ext)) return 'models';
      if (isImageExtension(ext)) return 'images';
      return 'other';
    }

    _typeCounts(files) {
      var out = { all: files.length, models: 0, images: 0, other: 0 };
      files.forEach(function (entry) {
        var cat = this._entryCategory(entry);
        if (cat === 'models') out.models += 1;
        else if (cat === 'images') out.images += 1;
        else out.other += 1;
      }, this);
      return out;
    }

    _entryRelative(entry) {
      var full = normalizePath(this._entryPath(entry));
      var rootPath = normalizePath(String(entry && entry.root_path || ''));
      if (rootPath && full.toLowerCase().indexOf(rootPath.toLowerCase() + '/') === 0) {
        return full.slice(rootPath.length + 1);
      }
      return basename(full);
    }

    _modelmetaDisplayTitle(detail) {
      if (!detail || !detail.sidecar || !detail.sidecar.modelmeta) return '';
      var meta = detail.sidecar.modelmeta;
      var candidates = [meta.display_title, meta.title, meta.name];
      for (var i = 0; i < candidates.length; i += 1) {
        var value = String(candidates[i] || '').trim();
        if (value) return value;
      }
      return '';
    }

    _modelmetaTags(detail) {
      if (!detail || !detail.sidecar || !detail.sidecar.modelmeta) return [];
      var meta = detail.sidecar.modelmeta;
      var raw = meta.tags;
      if (!Array.isArray(raw)) return [];
      return raw.map(function (tag) { return String(tag || '').trim(); }).filter(Boolean);
    }

    _modelmetaSideKv(detail) {
      var kv = [];
      var meta = detail && detail.sidecar && detail.sidecar.modelmeta ? detail.sidecar.modelmeta : null;
      if (meta) {
        if (meta.primary_file) kv.push({ k: 'primary', v: String(meta.primary_file) });
        if (meta.origin_url || meta.origin) kv.push({ k: 'origin', v: String(meta.origin_url || meta.origin) });
        if (meta.license) kv.push({ k: 'license', v: String(meta.license) });
      }
      if (detail && detail.counts) {
        kv.push({ k: 'total size', v: formatBytes(Number(detail.counts.size_bytes || 0)) });
      }
      return kv;
    }

    _readmeExcerpt(readme) {
      var text = String(readme || '').trim();
      if (!text) return '';
      // Strip leading H1 if present
      text = text.replace(/^#\s+[^\n]*\n+/, '');
      if (text.length > 600) text = text.slice(0, 600).replace(/\s+\S*$/, '') + '…';
      return text;
    }

    // ─── Group filtering / sorting ────────────────────────────────────────
    _applyGroupFilter(groups) {
      var filter = this._groupFilter;
      if (filter === 'with_sidecar') {
        return groups.filter(function (g) { return g.has_modelmeta || g.has_readme; });
      }
      if (filter === 'missing_sidecar') {
        return groups.filter(function (g) { return !g.has_modelmeta && !g.has_readme; });
      }
      if (filter === 'recent') {
        var weekAgo = Date.now() - 7 * 24 * 3600 * 1000;
        return groups.filter(function (g) {
          var stamp = parseIsoDate(g.last_seen_at);
          return stamp && stamp.getTime() >= weekAgo;
        });
      }
      return groups;
    }

    _applyGroupSort(groups) {
      var copy = groups.slice();
      if (this._sort === 'name') {
        copy.sort(function (a, b) { return String(a.name || '').toLowerCase().localeCompare(String(b.name || '').toLowerCase()); });
      } else if (this._sort === 'count') {
        copy.sort(function (a, b) { return Number(b.file_count || 0) - Number(a.file_count || 0); });
      } else {
        // recent (default)
        copy.sort(function (a, b) {
          var ta = parseIsoDate(a.last_seen_at);
          var tb = parseIsoDate(b.last_seen_at);
          return (tb ? tb.getTime() : 0) - (ta ? ta.getTime() : 0);
        });
      }
      return copy;
    }

    _filterCounts(groups) {
      var weekAgo = Date.now() - 7 * 24 * 3600 * 1000;
      var counts = { all: groups.length, with_sidecar: 0, missing_sidecar: 0, recent: 0 };
      groups.forEach(function (g) {
        if (g.has_modelmeta || g.has_readme) counts.with_sidecar += 1; else counts.missing_sidecar += 1;
        var stamp = parseIsoDate(g.last_seen_at);
        if (stamp && stamp.getTime() >= weekAgo) counts.recent += 1;
      });
      return counts;
    }

    // ─── Renderers ────────────────────────────────────────────────────────
    _renderToolbar() {
      var groups = Array.isArray(this._tree && this._tree.groups) ? this._tree.groups : [];
      var loose = (this._tree && this._tree.loose) || { file_count: 0 };
      var totalFiles = groups.reduce(function (sum, g) { return sum + Number(g.file_count || 0); }, 0) + Number(loose.file_count || 0);
      var subtitle = String(groups.length) + ' folder-group' + (groups.length === 1 ? '' : 's')
        + ' · 1 loose-files bucket · ' + String(totalFiles) + ' files indexed';
      var filterCounts = this._filterCounts(groups);
      var filterLabels = {
        all: 'All groups', with_sidecar: 'With sidecar',
        missing_sidecar: 'Missing sidecar', recent: 'Recently changed',
      };
      var indexedLabel = this._lastIndexedAt
        ? 'Indexed ' + formatRelativeTime(this._lastIndexedAt)
        : 'Indexed';

      return ''
        + '<div class="toolbar-shell">'
        + '<div class="title-row">'
        + '<div class="title"><strong>' + escapeHtml(this._config.title || 'Working Files') + '</strong>'
        + '<span class="subtitle">' + escapeHtml(subtitle) + '</span></div>'
        + '<div class="right">'
        + '<span class="indexed-pill"><span class="dot"></span>' + escapeHtml(indexedLabel) + '</span>'
        + '<div class="thumb-size-toggle" role="group" aria-label="Thumb size">'
        + THUMB_SIZES.map(function (size) {
            return '<button data-action="set-thumb-size" data-size="' + size + '"'
              + (this._thumbSize === size ? ' class="active"' : '') + '>'
              + size.toUpperCase() + '</button>';
          }, this).join('')
        + '</div>'
        + '<button class="icon-btn" data-action="reindex" title="Re-scan the working-files root and refresh the DB-backed inventory"'
        + (this._reindexing ? ' disabled' : '') + '>'
        + '<span aria-hidden="true">↻</span> ' + (this._reindexing ? 'Re-indexing…' : 'Re-index')
        + '</button>'
        + '</div></div>'
        + '<div class="filterbar">'
        + '<div class="left"><span class="label">Show</span>'
        + GROUP_FILTERS.map(function (f) {
            return '<button class="chip-filter' + (this._groupFilter === f ? ' active' : '') + '"'
              + ' data-action="set-group-filter" data-filter="' + f + '">'
              + escapeHtml(filterLabels[f]) + ' <span style="opacity:.7;">· ' + String(filterCounts[f] || 0) + '</span></button>';
          }, this).join('')
        + '</div>'
        + '<div class="right"><div class="sort"><label>Sort</label>'
        + '<select data-action="set-sort">'
        + SORT_OPTIONS.map(function (opt) {
            return '<option value="' + opt.value + '"' + (this._sort === opt.value ? ' selected' : '') + '>'
              + escapeHtml(opt.label) + '</option>';
          }, this).join('')
        + '</select></div></div>'
        + '</div></div>';
    }

    _renderLooseHeader(loose) {
      var slug = LOOSE_SLUG;
      var collapsed = this._collapsedGroups[slug] !== false;
      var lastSeen = loose && loose.last_seen_at ? loose.last_seen_at : '';
      var rootPath = (this._tree && this._tree.root_path) ? String(this._tree.root_path) : '';
      return ''
        + '<div class="group-header" data-action="toggle-group" data-slug="' + escapeHtml(slug) + '">'
        + '<div class="group-thumb virtual" aria-hidden="true"><div class="stack"><span></span><span></span><span></span></div></div>'
        + '<div class="group-meta">'
        + '<div class="group-title-row">'
        + '<div class="group-title">(loose files)</div>'
        + '<span class="virtual-badge">VIRTUAL</span>'
        + '</div>'
        + '<div class="folder-hint">' + escapeHtml(rootPath || '/') + '/ <span style="color:var(--text-muted);">(top-level files with no parent folder)</span></div>'
        + '<div class="group-counts">'
        + '<div class="count"><span class="num">' + String(Number(loose && loose.file_count || 0)) + '</span> files</div>'
        + '<div class="count">' + escapeHtml(formatBytes(Number(loose && loose.size_bytes || 0))) + '</div>'
        + '</div>'
        + '</div>'
        + '<div class="group-right">'
        + '<div class="updated"><strong>' + escapeHtml(formatRelativeTime(lastSeen)) + '</strong>' + escapeHtml(formatDateTime(lastSeen)) + '</div>'
        + '<button class="expander" data-action="toggle-group" data-slug="' + escapeHtml(slug) + '" title="' + (collapsed ? 'Expand' : 'Collapse') + '">' + (collapsed ? '▾' : '▴') + '</button>'
        + '</div>'
        + '</div>';
    }

    _renderGroupHeader(group) {
      var slug = String(group.slug || '');
      var collapsed = this._collapsedGroups[slug] !== false;
      var detail = this._groupDetails[slug] && this._groupDetails[slug].detail;
      var displayTitle = detail ? this._modelmetaDisplayTitle(detail) : '';
      var title = displayTitle || group.name || slug;
      // Folder thumb color is always randomized per-slug. Sidecar presence/absence
      // is conveyed by the two status dots next to the title, not by the thumb color.
      var thumbClass = 'gc' + colorIndexFromSlug(slug);
      var folderHint = (this._tree && this._tree.root_path)
        ? String(this._tree.root_path) + '/' + String(group.name || slug) + '/'
        : String(group.name || slug) + '/';

      var dotsHtml = '<span class="sidecar-dots" title="Sidecar status">'
        + '<span class="sidecar-dot ' + (group.has_modelmeta ? 'on' : '') + '" title=".modelmeta.json ' + (group.has_modelmeta ? 'present' : 'missing') + '"></span>'
        + '<span class="sidecar-dot ' + (group.has_readme ? 'on' : '') + '" title="README.md ' + (group.has_readme ? 'present' : 'missing') + '"></span>'
        + '</span>';

      return ''
        + '<div class="group-header" data-action="toggle-group" data-slug="' + escapeHtml(slug) + '">'
        + '<div class="group-thumb ' + thumbClass + '" aria-hidden="true">' + escapeHtml(initialsFromTitle(title)) + '</div>'
        + '<div class="group-meta">'
        + '<div class="group-title-row">'
        + '<div class="group-title">' + escapeHtml(title) + '</div>'
        + (displayTitle ? '<span class="override-badge" title=\'Title overridden by .modelmeta.json "display_title"\'>TITLE OVERRIDE</span>' : '')
        + dotsHtml
        + '</div>'
        + '<div class="folder-hint">' + escapeHtml(folderHint) + '</div>'
        + '<div class="group-counts">'
        + '<div class="count"><span class="num">' + String(Number(group.file_count || 0)) + '</span> files</div>'
        + '<div class="count"><span class="num">' + String(Number(group.count_3mf || 0)) + '</span> 3MF</div>'
        + '<div class="count">' + escapeHtml(formatBytes(Number(group.size_bytes || 0))) + '</div>'
        + '</div>'
        + '</div>'
        + '<div class="group-right">'
        + '<div class="updated"><strong>' + escapeHtml(formatRelativeTime(group.last_seen_at)) + '</strong>' + escapeHtml(formatDateTime(group.last_seen_at)) + '</div>'
        + '<button class="overflow-btn" data-action="toggle-overflow" data-slug="' + escapeHtml(slug) + '" title="Group actions">⋯</button>'
        + '<button class="expander" data-action="toggle-group" data-slug="' + escapeHtml(slug) + '" title="' + (collapsed ? 'Expand' : 'Collapse') + '">' + (collapsed ? '▾' : '▴') + '</button>'
        + '</div>'
        + '</div>';
    }

    _renderOverflowMenu(group) {
      var slug = String(group.slug || '');
      if (this._overflowMenuSlug !== slug) return '';
      var folderPath = (this._tree && this._tree.root_path)
        ? String(this._tree.root_path) + '/' + String(group.name || slug)
        : '';
      return ''
        + '<div class="overflow-menu" aria-label="Group actions">'
        + '<button data-action="run-intake-wizard" data-folder-path="' + escapeHtml(folderPath) + '" disabled title="Wired in a follow-up PR"><span>🪄</span> Run Intake Wizard from this folder…</button>'
        + '<button data-action="add-to-project" data-folder-path="' + escapeHtml(folderPath) + '" disabled title="Wired in a follow-up PR"><span>📁</span> Add to Project…</button>'
        + '<button data-action="add-to-collection" data-folder-path="' + escapeHtml(folderPath) + '" disabled title="Wired in a follow-up PR"><span>🗂️</span> Add to Collection…</button>'
        + '<div class="sep"></div>'
        + '<button data-action="open-folder" data-path="' + escapeHtml(folderPath) + '"><span>↗</span> Open folder in file manager</button>'
        + (folderPath ? '<button data-action="copy-path" data-path="' + escapeHtml(folderPath) + '"><span>📋</span> Copy folder path</button>' : '')
        + '</div>';
    }

    _renderSidecar(group, detail) {
      // Loose bucket: always empty sidecar
      var slug = String(group.slug || '');
      if (slug === LOOSE_SLUG) {
        return '<div class="sidecar empty">Loose files have no sidecar. Move a file into a folder to give it a group with <code>.modelmeta.json</code> + <code>README.md</code> context.</div>';
      }
      if (!detail) return '';
      var sidecar = detail.sidecar || {};
      if (!sidecar.modelmeta && !sidecar.readme) {
        return '<div class="sidecar empty">No sidecar yet. Run <strong>Intake Wizard from this folder</strong> (via <code>⋯</code> menu) to author <code>.modelmeta.json</code> + <code>README.md</code>, or just edit them directly on disk.</div>';
      }
      var tags = this._modelmetaTags(detail);
      var readmeText = this._readmeExcerpt(sidecar.readme);
      var sideKv = this._modelmetaSideKv(detail);
      var metaPath = detail.folder_path ? String(detail.folder_path) + '/.modelmeta.json' : '';
      return ''
        + '<div class="sidecar">'
        + '<div class="body">'
        + (tags.length ? '<div class="tags">' + tags.map(function (t) { return '<span class="tag">' + escapeHtml(t) + '</span>'; }).join('') + '</div>' : '')
        + (readmeText
            ? '<div class="notes"><h4>README <span class="file-ref">· README.md</span></h4>' + escapeHtml(readmeText) + '</div>'
            : '')
        + (sidecar.modelmeta && metaPath
            ? '<div class="meta-source">meta-source: <button data-action="open-folder" data-path="' + escapeHtml(metaPath) + '" title="Open in file manager">' + escapeHtml(metaPath) + '</button></div>'
            : '')
        + '</div>'
        + (sideKv.length
            ? '<div class="side">' + sideKv.map(function (entry) {
                return '<div class="kv"><span class="k">' + escapeHtml(entry.k) + '</span> ' + escapeHtml(entry.v) + '</div>';
              }).join('') + '</div>'
            : '<div class="side"></div>')
        + '</div>';
    }

    _renderTypeBar(slug, files) {
      var counts = this._typeCounts(files);
      var current = this._typeFilters[slug] || 'all';
      var labels = { all: 'All', models: 'Models', images: 'Images', other: 'Other' };
      var viewToggleHtml = '';
      if (slug !== LOOSE_SLUG) {
        var viewMode = this._groupViewMode[slug] === 'folders' ? 'folders' : 'files';
        viewToggleHtml = ''
          + '<div class="view-toggle" role="group" aria-label="View mode">'
          + '<button class="' + (viewMode === 'files' ? 'active' : '') + '" data-action="set-group-view" data-slug="' + escapeHtml(slug) + '" data-view="files" title="Flat file list">FILES</button>'
          + '<button class="' + (viewMode === 'folders' ? 'active' : '') + '" data-action="set-group-view" data-slug="' + escapeHtml(slug) + '" data-view="folders" title="Folder navigation">FOLDERS</button>'
          + '</div>';
      }
      var catClassFor = { all: 'cat-all', models: 'cat-models', images: 'cat-images', other: 'cat-other' };
      return ''
        + '<div class="type-bar"><div class="type-chips">'
        + TYPE_FILTERS.map(function (filter) {
            return '<button class="type-chip ' + (catClassFor[filter] || '') + (current === filter ? ' active' : '') + '"'
              + ' data-action="set-type-filter" data-slug="' + escapeHtml(slug) + '" data-type="' + filter + '">'
              + escapeHtml(labels[filter]) + ' <span class="ct">· ' + String(counts[filter] || 0) + '</span></button>';
          }).join('')
        + '</div>'
        + viewToggleHtml
        + '</div>';
    }

    _renderFileRow(slug, entry) {
      var pathValue = this._entryPath(entry);
      var extension = this._entryExtension(entry);
      var thumbCls = fileThumbClass(extension);
      var previewUrl = this._filePreviewUrl(entry);
      var launch = entry && entry.launch && typeof entry.launch === 'object' ? entry.launch : {};
      var canLaunch = !!launch.can_launch_file;
      var canExplore = !!launch.can_open_in_explorer;
      var winPath = String(launch.windows_path || '');
      var menuKey = slug + '|' + pathValue;
      var menuOpen = this._fileActionMenuKey === menuKey;
      var relPath = this._entryRelative(entry);
      var openLabel = isSlicerLaunchableExtension(extension) ? 'Open in Slicer' : 'Open';

      var primaryAction = isSlicerLaunchableExtension(extension) ? 'open-in-slicer' : 'open-local';
      var actionsHtml = '';
      if (canLaunch) {
        actionsHtml += ''
          + '<span class="file-action-split">'
          + '<button class="open-main" data-action="' + primaryAction + '" data-path="' + escapeHtml(pathValue) + '">' + escapeHtml(openLabel) + '</button>'
          + '<button class="file-action-toggle" data-action="toggle-file-menu" data-menu-key="' + escapeHtml(menuKey) + '" aria-label="More open actions" aria-expanded="' + (menuOpen ? 'true' : 'false') + '">▾</button>'
          + (menuOpen
              ? '<span class="file-action-menu">'
                + '<button data-action="open-local" data-path="' + escapeHtml(pathValue) + '">Open in Desktop</button>'
                + (isSlicerLaunchableExtension(extension) ? '<button data-action="open-in-slicer" data-path="' + escapeHtml(pathValue) + '">Open in Slicer</button>' : '')
                + (winPath ? '<button data-action="copy-path" data-path="' + escapeHtml(winPath) + '">Copy Path</button>' : '')
                + '</span>'
              : '')
          + '</span>';
      } else if (isImageExtension(extension)) {
        actionsHtml += '<button class="btn-ghost" data-action="copy-path" data-path="' + escapeHtml(pathValue) + '">Copy Path</button>';
      }
      if (canExplore) {
        actionsHtml += '<button class="btn-ghost" data-action="open-folder" data-path="' + escapeHtml(dirname(pathValue)) + '" title="Open containing folder">⋯</button>';
      }

      return ''
        + '<div class="file-row">'
        + '<div class="file-thumb ' + thumbCls + (previewUrl ? ' has-preview' : '') + '">'
        + (previewUrl
            ? '<img class="preview-img" data-lazy-src="' + escapeHtml(previewUrl) + '" loading="lazy" decoding="async" alt="" />'
            : escapeHtml(extensionBadge(extension)))
        + '</div>'
        + '<div class="file-main">'
        + '<div class="file-name">' + escapeHtml(basename(pathValue)) + '</div>'
        + '<div class="file-path">' + escapeHtml(relPath || pathValue) + '</div>'
        + '</div>'
        + '<div class="file-meta">' + escapeHtml(formatBytes(this._entrySize(entry))) + '<span class="sub">' + escapeHtml(formatDateTime(this._entryMtime(entry))) + '</span></div>'
        + '<div class="file-meta">' + escapeHtml(extensionBadge(extension)) + '<span class="sub">' + escapeHtml(fileTypeLabel(extension)) + '</span></div>'
        + '<div class="file-actions">' + actionsHtml + '</div>'
        + '</div>';
    }

    _renderGroupBody(group) {
      var slug = String(group.slug || '');
      var entry = this._groupDetails[slug];
      if (!entry || entry.loading) {
        return '<div class="group-body"><div class="body-loading">Loading group contents…</div></div>';
      }
      if (entry.error) {
        return '<div class="group-body"><div class="banner error">' + escapeHtml(entry.error) + '</div></div>';
      }
      var detail = entry.detail || null;
      var files = Array.isArray(entry.files) ? entry.files : [];
      var typeFilter = this._typeFilters[slug] || 'all';
      var viewMode = (slug !== LOOSE_SLUG && this._groupViewMode[slug] === 'folders') ? 'folders' : 'files';

      var bodyHtml;
      if (viewMode === 'folders') {
        bodyHtml = this._renderFoldersView(slug, typeFilter);
      } else {
        var visibleFiles = files;
        if (typeFilter !== 'all') {
          visibleFiles = files.filter(function (f) { return this._entryCategory(f) === typeFilter; }, this);
        }
        if (!visibleFiles.length) {
          bodyHtml = '<div class="empty-row">No files match this type filter.</div>';
        } else {
          bodyHtml = '<div class="file-list">'
            + visibleFiles.map(function (e) { return this._renderFileRow(slug, e); }, this).join('')
            + '</div>';
        }
      }
      return ''
        + '<div class="group-body">'
        + this._renderSidecar(group, detail)
        + this._renderTypeBar(slug, files)
        + bodyHtml
        + '</div>';
    }

    _renderFoldersView(slug, typeFilter) {
      var folderState = this._groupFolders[slug];
      if (!folderState || folderState.loading) {
        // Kick off async load if not already loaded
        if (!folderState) this._loadGroupFolders(slug);
        return '<div class="body-loading">Loading folders…</div>';
      }
      if (folderState.error) {
        return '<div class="banner error">' + escapeHtml(folderState.error) + '</div>';
      }
      var allFolders = Array.isArray(folderState.folders) ? folderState.folders : [];
      var currentPath = String(this._groupFolderPath[slug] || '');

      // Build direct subfolders + direct files at current path
      var directFolderMap = {}; // childName -> { fileCount, subPath }
      var directFiles = [];
      allFolders.forEach(function (folder) {
        var fpath = String(folder.path || '');
        var fcount = Number(folder.file_count || 0);
        var ffiles = Array.isArray(folder.files) ? folder.files : [];
        if (fpath === currentPath) {
          // Files directly at currentPath
          ffiles.forEach(function (f) { directFiles.push(f); });
          return;
        }
        // Is fpath a descendant of currentPath?
        var prefix = currentPath ? currentPath + '/' : '';
        if (currentPath && fpath.indexOf(prefix) !== 0) return;
        var relative = fpath.slice(prefix.length);
        if (!relative) return;
        var firstSeg = relative.split('/')[0];
        if (!firstSeg) return;
        var childPath = joinFolderPath(currentPath, firstSeg);
        if (!directFolderMap[firstSeg]) {
          directFolderMap[firstSeg] = { name: firstSeg, path: childPath, fileCount: 0 };
        }
        directFolderMap[firstSeg].fileCount += fcount;
      });

      // Apply type filter to direct files
      if (typeFilter !== 'all') {
        directFiles = directFiles.filter(function (f) { return this._entryCategory(f) === typeFilter; }, this);
      }

      var folderNames = Object.keys(directFolderMap).sort(function (a, b) {
        return a.toLowerCase() < b.toLowerCase() ? -1 : (a.toLowerCase() > b.toLowerCase() ? 1 : 0);
      });

      var folderRowsHtml = folderNames.map(function (name) {
        var info = directFolderMap[name];
        return ''
          + '<div class="folder-row" data-action="folder-enter" data-slug="' + escapeHtml(slug) + '" data-path="' + escapeHtml(info.path) + '">'
          + '<div class="folder-thumb">📁</div>'
          + '<div class="folder-main">'
          + '<div class="folder-name">' + escapeHtml(name) + '</div>'
          + '<div class="folder-sub">' + escapeHtml(info.path) + '/</div>'
          + '</div>'
          + '<div class="folder-count">' + String(info.fileCount) + ' files</div>'
          + '<div class="file-actions"><span style="color:var(--text-muted);font-size:14px;">›</span></div>'
          + '</div>';
      }).join('');

      var fileRowsHtml = directFiles.map(function (e) { return this._renderFileRow(slug, e); }, this).join('');

      var emptyHtml = (!folderNames.length && !directFiles.length)
        ? '<div class="empty-row">This folder is empty.</div>'
        : '';

      return ''
        + this._renderBreadcrumb(slug, currentPath)
        + '<div class="file-list">' + folderRowsHtml + fileRowsHtml + '</div>'
        + emptyHtml;
    }

    _renderBreadcrumb(slug, currentPath) {
      var atRoot = !currentPath;
      var segments = currentPath ? currentPath.split('/').filter(Boolean) : [];
      var crumbs = [];
      // Root label = the group's folder name (e.g. "college-pennants") rather than literal "root"
      var rootLabel = slug;
      var groups = (this._tree && Array.isArray(this._tree.groups)) ? this._tree.groups : [];
      for (var gi = 0; gi < groups.length; gi += 1) {
        if (String(groups[gi].slug || '') === slug) {
          rootLabel = String(groups[gi].name || slug);
          break;
        }
      }
      crumbs.push('<button class="breadcrumb-link" data-action="folder-nav" data-slug="' + escapeHtml(slug) + '" data-path="">' + escapeHtml(rootLabel) + '</button>');
      var accum = '';
      segments.forEach(function (seg, idx) {
        accum = accum ? (accum + '/' + seg) : seg;
        if (idx === segments.length - 1) {
          crumbs.push('<span class="crumb-current">' + escapeHtml(seg) + '</span>');
        } else {
          crumbs.push('<button class="breadcrumb-link" data-action="folder-nav" data-slug="' + escapeHtml(slug) + '" data-path="' + escapeHtml(accum) + '">' + escapeHtml(seg) + '</button>');
        }
      });
      return ''
        + '<div class="folder-breadcrumbs">'
        + '<button class="breadcrumb-up" data-action="folder-up" data-slug="' + escapeHtml(slug) + '"' + (atRoot ? ' disabled' : '') + ' title="Up one level">↑</button>'
        + crumbs.join('<span class="crumb-sep">›</span>')
        + '</div>';
    }

    _renderLooseRow() {
      var loose = (this._tree && this._tree.loose) || { file_count: 0 };
      // Hide loose entry entirely if there are no loose files
      if (!Number(loose.file_count || 0)) return '';
      var slug = LOOSE_SLUG;
      var collapsed = this._collapsedGroups[slug] !== false;
      var pseudoGroup = { slug: slug, name: '(loose files)', file_count: loose.file_count, has_modelmeta: false, has_readme: false };
      var body = collapsed ? '' : this._renderGroupBody(pseudoGroup);
      return ''
        + '<div class="group-row virtual ' + (collapsed ? 'collapsed' : '') + '" data-thumb="' + this._thumbSize + '">'
        + this._renderLooseHeader(loose)
        + body
        + '</div>';
    }

    _renderGroup(group) {
      var slug = String(group.slug || '');
      var collapsed = this._collapsedGroups[slug] !== false;
      var body = collapsed ? '' : this._renderGroupBody(group);
      return ''
        + '<div class="group-row ' + (collapsed ? 'collapsed' : '') + '" data-thumb="' + this._thumbSize + '">'
        + this._renderGroupHeader(group)
        + this._renderOverflowMenu(group)
        + body
        + '</div>';
    }

    _renderGroups() {
      var groups = Array.isArray(this._tree && this._tree.groups) ? this._tree.groups : [];
      var filtered = this._applyGroupFilter(groups);
      var sorted = this._applyGroupSort(filtered);
      var looseFirst = this._sort === 'loose_first';
      var looseHtml = this._renderLooseRow();
      var groupsHtml = sorted.map(function (g) { return this._renderGroup(g); }, this).join('');
      if (!looseHtml && !groupsHtml) {
        return '<div class="empty-row">No working-files folders found. Click <strong>Re-index</strong> to scan the working-files root.</div>';
      }
      return '<div class="groups">'
        + (looseFirst || this._sort !== 'name' ? looseHtml + groupsHtml : looseHtml + groupsHtml)
        + '</div>';
    }

    _render() {
      if (!this.shadowRoot) return;
      var banners = '';
      if (this._error) banners += '<div class="banner error">' + escapeHtml(this._error) + '</div>';
      if (this._status) banners += '<div class="banner status">' + escapeHtml(this._status) + '</div>';
      if (this._loading && this._loadingPhase) {
        banners += '<div class="banner">' + escapeHtml(this._loadingPhase) + '</div>';
      }
      var content;
      if (!this._tree && this._loading) {
        content = '<div class="empty-row">Loading working files…</div>';
      } else if (!this._tree) {
        content = '<div class="empty-row">Connect to Home Assistant to load working files.</div>';
      } else {
        content = this._renderToolbar() + this._renderGroups();
      }
      this.shadowRoot.innerHTML = ''
        + '<style>' + STYLES + '</style>'
        + '<ha-card>'
        + '<div class="shell">'
        + banners
        + content
        + '</div>'
        + '</ha-card>';
      // Attach IntersectionObserver to any newly rendered lazy preview images.
      this._attachLazyPreviews();
    }

    // ─── Event handling ───────────────────────────────────────────────────
    _handleClick(event) {
      var target = null;
      var path = event && typeof event.composedPath === 'function' ? event.composedPath() : [];
      for (var i = 0; i < path.length; i += 1) {
        if (path[i] instanceof Element) {
          target = path[i].closest('[data-action]');
          if (target) break;
        }
      }
      if (!target && event.target instanceof Element) {
        target = event.target.closest('[data-action]');
      }
      if (!target) {
        // Click outside any data-action; close menus if open
        if (this._fileActionMenuKey || this._overflowMenuSlug) {
          this._fileActionMenuKey = '';
          this._overflowMenuSlug = '';
          this._render();
        }
        return;
      }

      var action = String(target.getAttribute('data-action') || '');
      if (!action) return;

      if (action === 'reindex') { this._reindex(); return; }
      if (action === 'set-thumb-size') {
        var size = String(target.getAttribute('data-size') || '').toLowerCase();
        if (THUMB_SIZES.indexOf(size) >= 0 && size !== this._thumbSize) {
          this._thumbSize = size;
          this._render();
        }
        return;
      }
      if (action === 'set-group-filter') {
        var filter = String(target.getAttribute('data-filter') || 'all');
        if (GROUP_FILTERS.indexOf(filter) >= 0 && filter !== this._groupFilter) {
          this._groupFilter = filter;
          this._render();
        }
        return;
      }
      if (action === 'set-sort') {
        // sort fires via change event normally — but click on option also routes here
        var val = String(target.value || target.getAttribute('data-value') || '');
        if (val && val !== this._sort) {
          this._sort = val;
          this._render();
        }
        return;
      }
      if (action === 'toggle-group') {
        var slug = String(target.getAttribute('data-slug') || '');
        if (!slug) return;
        var wasCollapsed = this._collapsedGroups[slug] !== false;
        this._collapsedGroups[slug] = !wasCollapsed;
        this._overflowMenuSlug = '';
        this._fileActionMenuKey = '';
        this._render();
        if (wasCollapsed) {
          this._loadGroup(slug);
        }
        return;
      }
      if (action === 'toggle-overflow') {
        var ovSlug = String(target.getAttribute('data-slug') || '');
        this._overflowMenuSlug = this._overflowMenuSlug === ovSlug ? '' : ovSlug;
        this._render();
        return;
      }
      if (action === 'set-type-filter') {
        var typeSlug = String(target.getAttribute('data-slug') || '');
        var typeVal = String(target.getAttribute('data-type') || 'all');
        if (typeSlug && TYPE_FILTERS.indexOf(typeVal) >= 0) {
          this._typeFilters[typeSlug] = typeVal;
          this._render();
        }
        return;
      }
      if (action === 'toggle-file-menu') {
        var key = String(target.getAttribute('data-menu-key') || '');
        this._fileActionMenuKey = this._fileActionMenuKey === key ? '' : key;
        this._render();
        return;
      }
      if (action === 'open-in-slicer') {
        this._fileActionMenuKey = '';
        this._launchLocalHelperAction('open_in_slicer', String(target.getAttribute('data-path') || ''));
        return;
      }
      if (action === 'open-local') {
        this._fileActionMenuKey = '';
        this._launchLocalHelperAction('open_local', String(target.getAttribute('data-path') || ''));
        return;
      }
      if (action === 'open-folder') {
        this._overflowMenuSlug = '';
        this._fileActionMenuKey = '';
        this._launchLocalHelperAction('open_folder', String(target.getAttribute('data-path') || ''));
        return;
      }
      if (action === 'copy-path') {
        this._overflowMenuSlug = '';
        this._fileActionMenuKey = '';
        this._copyToClipboard(String(target.getAttribute('data-path') || ''));
        return;
      }
      if (action === 'set-group-view') {
        var gvSlug = String(target.getAttribute('data-slug') || '');
        var gvView = String(target.getAttribute('data-view') || 'files');
        if (!gvSlug) return;
        if (gvView !== 'files' && gvView !== 'folders') gvView = 'files';
        if (this._groupViewMode[gvSlug] === gvView) return;
        this._groupViewMode[gvSlug] = gvView;
        // Reset breadcrumb when switching modes; only fetch folders payload when needed.
        if (gvView === 'folders') {
          if (typeof this._groupFolderPath[gvSlug] !== 'string') this._groupFolderPath[gvSlug] = '';
          this._loadGroupFolders(gvSlug);
        }
        this._render();
        return;
      }
      if (action === 'folder-enter' || action === 'folder-nav') {
        var feSlug = String(target.getAttribute('data-slug') || '');
        var fePath = String(target.getAttribute('data-path') || '');
        if (!feSlug) return;
        this._groupFolderPath[feSlug] = fePath;
        this._render();
        return;
      }
      if (action === 'folder-up') {
        var fuSlug = String(target.getAttribute('data-slug') || '');
        if (!fuSlug) return;
        var current = String(this._groupFolderPath[fuSlug] || '');
        if (!current) return;
        var idx = current.lastIndexOf('/');
        this._groupFolderPath[fuSlug] = idx >= 0 ? current.slice(0, idx) : '';
        this._render();
        return;
      }
    }
  }

  // ─── Sort <select> change handler ─────────────────────────────────────────
  // The click handler above can't reliably catch <select> changes; bind in
  // connectedCallback via a "change" listener inside the shadow root.
  var origConnected = ModelCatalogWorkingFilesExplorerCard.prototype.connectedCallback;
  ModelCatalogWorkingFilesExplorerCard.prototype.connectedCallback = function () {
    origConnected.call(this);
    if (this.shadowRoot && !this._boundChange) {
      this._boundChange = function (event) {
        var target = event && event.target;
        if (target && target.matches && target.matches('[data-action="set-sort"]')) {
          var val = String(target.value || '');
          if (val && val !== this._sort) {
            this._sort = val;
            this._render();
          }
        }
      }.bind(this);
      this.shadowRoot.addEventListener('change', this._boundChange);
    }
  };
  var origDisconnected = ModelCatalogWorkingFilesExplorerCard.prototype.disconnectedCallback;
  ModelCatalogWorkingFilesExplorerCard.prototype.disconnectedCallback = function () {
    origDisconnected.call(this);
    if (this.shadowRoot && this._boundChange) {
      this.shadowRoot.removeEventListener('change', this._boundChange);
      this._boundChange = null;
    }
  };

  if (!customElements.get('model-catalog-working-files-explorer-card')) {
    customElements.define('model-catalog-working-files-explorer-card', ModelCatalogWorkingFilesExplorerCard);
  }

  window.customCards = window.customCards || [];
  window.customCards.push({
    type: 'model-catalog-working-files-explorer-card',
    name: 'Model Catalog Working Files Explorer',
    description: 'Folder-first browser for the working-files root, with sidecar context per folder.',
  });
})();
