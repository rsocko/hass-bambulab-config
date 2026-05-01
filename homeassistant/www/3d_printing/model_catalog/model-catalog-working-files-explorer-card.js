(function () {
  var VIEW_OPTIONS = ["groups", "all", "ungrouped"];

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
    + 'ha-card{border-radius:20px;border:1px solid rgba(148,163,184,0.18);background:linear-gradient(180deg,rgba(15,23,42,0.08),rgba(15,23,42,0.02));}'
    + '.shell{display:grid;gap:14px;padding:16px;}'
    + '.title-row{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;flex-wrap:wrap;}'
    + '.title{font-size:18px;font-weight:800;line-height:1.2;}'
    + '.subtitle{font-size:12px;color:var(--secondary-text-color);}'
    + '.status{font-size:12px;font-weight:700;color:var(--secondary-text-color);}'
    + '.status.error{color:#f87171;}'
    + '.toolbar,.panel,.section{border-radius:18px;border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.12);padding:14px;}'
    + '.toolbar-row,.button-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;}'
    + '.tab-row{display:inline-flex;gap:8px;flex-wrap:wrap;}'
    + '.tab{min-height:36px;padding:0 12px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(148,163,184,0.12);font-size:12px;font-weight:700;cursor:pointer;}'
    + '.tab.active{background:rgba(30,64,175,0.24);border-color:rgba(96,165,250,0.5);}'
    + '.button{min-height:36px;padding:0 12px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(148,163,184,0.12);color:var(--primary-text-color);font-size:12px;font-weight:700;cursor:pointer;}'
    + '.button.primary{background:rgba(30,64,175,0.22);border-color:rgba(96,165,250,0.4);}'
    + '.button.warn{background:rgba(180,83,9,0.2);border-color:rgba(245,158,11,0.4);}'
    + '.button.danger{background:rgba(153,27,27,0.22);border-color:rgba(248,113,113,0.4);}'
    + '.button:disabled{opacity:.6;cursor:not-allowed;}'
    + '.field{display:grid;gap:6px;min-width:0;}'
    + '.field label{font-size:11px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;color:var(--secondary-text-color);}'
    + '.input,.select{width:100%;box-sizing:border-box;min-height:38px;padding:8px 10px;border-radius:12px;border:1px solid rgba(148,163,184,0.24);background:rgba(15,23,42,0.16);color:var(--primary-text-color);}'
    + '.grow{flex:1 1 220px;}'
    + '.grid{display:grid;gap:12px;grid-template-columns:repeat(2,minmax(0,1fr));}'
    + '.groups{display:grid;gap:10px;}'
    + '.group-card{display:grid;gap:8px;padding:12px;border-radius:14px;border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.1);cursor:pointer;}'
    + '.group-card.active{border-color:rgba(96,165,250,0.45);background:rgba(30,64,175,0.16);}'
    + '.chip{display:inline-flex;align-items:center;padding:3px 8px;border-radius:999px;border:1px solid rgba(96,165,250,0.35);background:rgba(30,64,175,0.2);font-size:11px;font-weight:700;text-transform:uppercase;}'
    + '.list{display:grid;gap:10px;}'
    + '.list-row{display:grid;gap:8px;padding:12px;border-radius:14px;border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.1);}'
    + '.list-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;flex-wrap:wrap;}'
    + '.row-title{font-size:14px;font-weight:700;overflow-wrap:anywhere;}'
    + '.row-subtitle{font-size:12px;color:var(--secondary-text-color);overflow-wrap:anywhere;}'
    + '.meta{display:flex;gap:8px;flex-wrap:wrap;color:var(--secondary-text-color);font-size:12px;}'
    + '.state-row{padding:18px;border-radius:14px;border:1px dashed rgba(148,163,184,0.28);text-align:center;color:var(--secondary-text-color);}'
    + '.split{display:grid;gap:12px;grid-template-columns:minmax(260px, 1fr) minmax(360px, 2fr);}'
    + '.selector{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:700;color:var(--secondary-text-color);}'
    + '@media (max-width: 900px){.split,.grid{grid-template-columns:1fr;}.shell{padding:14px;}}';

  class ModelCatalogWorkingFilesExplorerCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._hass = null;
      this._config = null;
      this._loading = false;
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
      this._boundClick = this._handleClick.bind(this);
    }

    setConfig(config) {
      this._config = {
        title: config && config.title ? String(config.title) : 'Working Files',
        per_page: config && config.per_page ? Number(config.per_page) : 200,
        auto_reindex_on_initial_load: !(config && config.auto_reindex_on_initial_load === false),
      };
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      if (this.isConnected && !this._loading && !this._hasLoadedExplorer) {
        this._loadExplorer();
      }
    }

    connectedCallback() {
      if (this.shadowRoot) {
        this.shadowRoot.addEventListener('click', this._boundClick);
      }
      if (this._hass && !this._loading && !this._hasLoadedExplorer) {
        this._loadExplorer();
      }
    }

    disconnectedCallback() {
      if (this.shadowRoot) {
        this.shadowRoot.removeEventListener('click', this._boundClick);
      }
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

    async _loadExplorer(options) {
      if (!this._hass || this._loading) {
        return;
      }
      var shouldForceReindex = !!(options && options.forceReindex);
      this._hasLoadedExplorer = true;
      this._loading = true;
      this._error = '';
      this._status = '';
      this._render();

      try {
        var shouldRunInitialReindex = !this._hasAttemptedInitialReindex && !!this._config.auto_reindex_on_initial_load;
        if (shouldForceReindex || shouldRunInitialReindex) {
          this._hasAttemptedInitialReindex = true;
          try {
            await this._reindexWorkingFiles();
          } catch (_reindexError) {
            if (shouldForceReindex) {
              this._status = 'Reindex failed; showing last indexed results.';
            }
          }
        }

        var response = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_explore_working_files', {
          view: this._view,
          q: this._query || undefined,
          extension: this._extension || undefined,
          limit: this._config.per_page,
          offset: 0,
        });
        this._summary = response.summary || {};
        this._groups = Array.isArray(response.groups) ? response.groups : [];
        this._files = Array.isArray(response.files) ? response.files : [];

        if (this._view === 'groups') {
          if (!this._groups.length) {
            this._selectedGroupId = 0;
          } else {
            var selected = this._currentSelectedGroup();
            if (!selected) {
              this._selectedGroupId = Number(this._groups[0].id || 0);
            }
          }
        }
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not load Working Files explorer.';
      } finally {
        this._loading = false;
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

    async _runReorganize() {
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
      if (action === 'select-group') {
        this._selectedGroupId = Number(target.getAttribute('data-group-id') || 0);
        this._selectedPaths = {};
        this._render();
        return;
      }
      if (action === 'toggle-select-path') {
        this._togglePathSelection(String(target.getAttribute('data-file-path') || ''));
        return;
      }
      if (action === 'launch-file') {
        this._openLocalPath(String(target.getAttribute('data-file-path') || ''));
        return;
      }
      if (action === 'open-explorer') {
        this._openExplorer(String(target.getAttribute('data-file-path') || ''));
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
      if (action === 'reorganize-selected-group') {
        this._runReorganize();
      }
    }

    _renderGroupsPane() {
      if (!this._groups.length) {
        return '<div class="state-row">No working groups are available.</div>';
      }
      return '<div class="groups">' + this._groups.map(function (group) {
        var active = Number(group.id) === Number(this._selectedGroupId || 0);
        var counts = group.counts || {};
        return ''
          + '<article class="group-card' + (active ? ' active' : '') + '" data-action="select-group" data-group-id="' + String(group.id) + '">'
          + '  <div class="title-row"><div><div class="row-title">' + escapeHtml(group.title || 'Untitled Group') + '</div><div class="row-subtitle">' + escapeHtml(group.notes || group.folder_hint || '') + '</div></div><span class="chip">' + escapeHtml(formatStage(group.stage || 'draft')) + '</span></div>'
          + '  <div class="meta"><span>3MF ' + String(counts.count_3mf || 0) + '</span><span>Other ' + String(counts.count_other || 0) + '</span><span>Total ' + String(counts.total || 0) + '</span></div>'
          + '</article>';
      }, this).join('') + '</div>';
    }

    _renderFileRows(fileRows) {
      if (!fileRows || !fileRows.length) {
        return '<div class="state-row">No files in this view.</div>';
      }
      return '<div class="list">' + fileRows.map(function (entry) {
        var canonicalPath = String(entry.source_path_canonical || entry.file_path || '');
        var launch = entry.launch || {};
        var windowsPath = String(launch.windows_path || '');
        var sourcePath = String(entry.file_path || entry.source_path_canonical || entry.source_path_raw || '');
        if (!windowsPath && /^[a-zA-Z]:[\\/]/.test(sourcePath)) {
          windowsPath = sourcePath;
        }
        var canLaunch = !!windowsPath;
        var memberships = Array.isArray(entry.group_memberships) ? entry.group_memberships : [];
        var selected = !!this._selectedPaths[canonicalPath];
        return ''
          + '<article class="list-row">'
          + '  <div class="list-top">'
          + '    <div>'
          + '      <div class="row-title">' + escapeHtml(entry.file_name_raw || basename(canonicalPath)) + '</div>'
          + '      <div class="row-subtitle">' + escapeHtml(canonicalPath) + '</div>'
          + '    </div>'
          + '    <label class="selector"><input type="checkbox" data-action="toggle-select-path" data-file-path="' + escapeHtml(canonicalPath) + '"' + (selected ? ' checked' : '') + '> Select</label>'
          + '  </div>'
          + '  <div class="meta"><span>Ext ' + escapeHtml(String(entry.file_extension || '').replace(/^\./, '') || 'file') + '</span><span>Size ' + escapeHtml(formatBytes(entry.file_size_bytes || 0)) + '</span><span>Groups ' + String(memberships.length) + '</span></div>'
          + '  <div class="button-row">'
          + '    <button class="button" data-action="launch-file" data-file-path="' + escapeHtml(windowsPath) + '"' + (canLaunch ? '' : ' disabled') + '>Launch</button>'
          + '    <button class="button" data-action="open-explorer" data-file-path="' + escapeHtml(windowsPath) + '"' + (canLaunch ? '' : ' disabled') + '>Explorer</button>'
          + '  </div>'
          + '</article>';
      }, this).join('') + '</div>';
    }

    _renderGroupsView() {
      var selectedGroup = this._currentSelectedGroup();
      var selectedFiles = selectedGroup && Array.isArray(selectedGroup.files) ? selectedGroup.files : [];
      return ''
        + '<div class="split">'
        + '  <section class="section">'
        + '    <div class="title-row"><div><div class="title">Groups</div><div class="subtitle">Group-first view with .3mf priority and reorganization support.</div></div></div>'
        + this._renderGroupsPane()
        + '  </section>'
        + '  <section class="section">'
        + '    <div class="title-row"><div><div class="title">' + escapeHtml(selectedGroup ? selectedGroup.title : 'Select a Group') + '</div><div class="subtitle">' + escapeHtml(selectedGroup ? (selectedGroup.folder_hint || '') : 'Pick a group to inspect files and run actions.') + '</div></div><div class="button-row"><button class="button warn" data-action="remove-selection-from-group"' + (selectedGroup ? '' : ' disabled') + '>Remove Selected</button><button class="button primary" data-action="reorganize-selected-group"' + (selectedGroup ? '' : ' disabled') + '>Reorganize</button></div></div>'
        + this._renderFileRows(selectedFiles)
        + '  </section>'
        + '</div>';
    }

    _renderAllOrUngrouped() {
      var selectedCount = this._selectedPathList().length;
      return ''
        + '<section class="section">'
        + '  <div class="title-row"><div><div class="title">' + (this._view === 'all' ? 'All Files' : 'Ungrouped Files') + '</div><div class="subtitle">Select files and create/add group memberships.</div></div><div class="status">Selected ' + String(selectedCount) + '</div></div>'
        + '  <div class="button-row"><button class="button primary" data-action="create-group-from-selection"' + (selectedCount ? '' : ' disabled') + '>Create Group</button><button class="button" data-action="add-selection-to-group"' + (selectedCount ? '' : ' disabled') + '>Add To Group</button></div>'
        + this._renderFileRows(this._files)
        + '</section>';
    }

    _render() {
      if (!this.shadowRoot || !this._config) {
        return;
      }

      var summary = this._summary || {};
      var bodyHtml = '';
      if (this._loading) {
        bodyHtml = '<div class="state-row">Loading Working Files...</div>';
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
        + '  <div class="shell">'
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
        + '        <div class="button-row"><button class="button" data-action="refresh">Refresh</button></div>'
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
