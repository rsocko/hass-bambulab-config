(function () {
  var STAGE_OPTIONS = ["draft", "in_progress", "needs_revision", "ready_to_publish", "archived"];
  var LINK_ROLE_OPTIONS = ["related", "likely_revision", "separate_variant"];

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

  function dirname(filePath) {
    var normalized = String(filePath || "").replace(/\\/g, "/");
    if (!normalized || normalized.indexOf("/") === -1) {
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
      .map(function (part) {
        return part ? part.charAt(0).toUpperCase() + part.slice(1) : "";
      })
      .join(" ");
  }

  function toFileUri(filePath) {
    var normalized = String(filePath || "").replace(/\\/g, "/");
    if (!normalized) {
      return "";
    }
    if (/^[a-zA-Z]:\//.test(normalized)) {
      return "file:///" + normalized;
    }
    return "file:///" + normalized.replace(/^\//, "");
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
        // Keep the current token if refresh fails.
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
        this._loading = false;
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

  function stageOptionsHtml(selectedValue, includeAll) {
    var options = includeAll ? [""].concat(STAGE_OPTIONS) : STAGE_OPTIONS.slice();
    return options.map(function (stage) {
      var value = stage;
      var label = stage ? formatStage(stage) : "All stages";
      var selected = String(selectedValue || "") === value ? " selected" : "";
      return '<option value="' + escapeHtml(value) + '"' + selected + '>' + escapeHtml(label) + '</option>';
    }).join("");
  }

  function linkRoleOptionsHtml(selectedValue) {
    return LINK_ROLE_OPTIONS.map(function (role) {
      var selected = String(selectedValue || "related") === role ? " selected" : "";
      return '<option value="' + escapeHtml(role) + '"' + selected + '>' + escapeHtml(formatStage(role)) + '</option>';
    }).join("");
  }

  function batchActionLabel(action) {
    if (action === "ready_to_publish") {
      return "Mark Ready";
    }
    if (action === "open_intake") {
      return "Open Intake";
    }
    if (action === "link_review") {
      return "Link Review";
    }
    return formatStage(action);
  }

  var sharedStyles = ''
    + 'ha-card{border-radius:20px;border:1px solid rgba(148,163,184,0.18);background:linear-gradient(180deg,rgba(15,23,42,0.08),rgba(15,23,42,0.02));}'
    + '.shell{display:grid;gap:14px;padding:16px;}'
    + '.header{display:grid;gap:8px;}'
    + '.title-row{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;flex-wrap:wrap;}'
    + '.title{font-size:18px;font-weight:800;line-height:1.2;}'
    + '.subtitle{font-size:12px;color:var(--secondary-text-color);}'
    + '.toolbar,.panel,.group-card,.section{border-radius:18px;border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.12);}'
    + '.toolbar,.panel,.section{padding:14px;}'
    + '.toolbar{display:grid;gap:12px;}'
    + '.toolbar-row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;}'
    + '.grow{flex:1 1 220px;}'
    + '.field{display:grid;gap:6px;min-width:0;}'
    + '.field label{font-size:11px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;color:var(--secondary-text-color);}'
    + '.input,.select,.textarea{width:100%;box-sizing:border-box;min-height:40px;padding:10px 12px;border-radius:12px;border:1px solid rgba(148,163,184,0.24);background:rgba(15,23,42,0.16);color:var(--primary-text-color);}'
    + '.select{color-scheme:light dark;}'
    + '.select option,.select optgroup{background:var(--card-background-color);color:var(--primary-text-color);}'
    + '.textarea{min-height:96px;resize:vertical;}'
    + '.button-row{display:flex;gap:8px;flex-wrap:wrap;}'
    + '.button{min-height:38px;padding:0 14px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(148,163,184,0.12);color:var(--primary-text-color);font-size:12px;font-weight:700;cursor:pointer;}'
    + '.button.primary{background:rgba(30,64,175,0.22);border-color:rgba(96,165,250,0.4);}'
    + '.button.warn{background:rgba(180,83,9,0.2);border-color:rgba(245,158,11,0.4);}'
    + '.button.danger{background:rgba(153,27,27,0.22);border-color:rgba(248,113,113,0.4);}'
    + '.button:disabled{opacity:.6;cursor:not-allowed;}'
    + '.status{font-size:12px;font-weight:700;color:var(--secondary-text-color);}'
    + '.status.error{color:#f87171;}'
    + '.groups{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));}'
    + '.group-card{display:grid;gap:10px;padding:14px;}'
    + '.group-card.selected{border-color:rgba(96,165,250,0.4);background:rgba(30,64,175,0.18);}'
    + '.chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;background:rgba(30,64,175,0.18);border:1px solid rgba(96,165,250,0.3);font-size:11px;font-weight:800;letter-spacing:.02em;text-transform:uppercase;}'
    + '.chip.ok{background:rgba(22,101,52,0.22);border-color:rgba(74,222,128,0.3);}'
    + '.meta-grid{display:grid;gap:10px;grid-template-columns:repeat(2,minmax(0,1fr));}'
    + '.meta-item{display:grid;gap:4px;min-width:0;}'
    + '.meta-label{font-size:11px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;color:var(--secondary-text-color);}'
    + '.meta-value{font-size:13px;overflow-wrap:anywhere;}'
    + '.state-row{padding:18px;border-radius:16px;border:1px dashed rgba(148,163,184,0.28);color:var(--secondary-text-color);text-align:center;}'
    + '.selector{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:700;color:var(--secondary-text-color);}'
    + '.batch-toolbar{display:grid;gap:10px;padding:12px;border-radius:18px;border:1px solid rgba(96,165,250,0.35);background:rgba(30,64,175,0.14);}'
    + '.result-summary{display:grid;gap:10px;padding:12px;border-radius:18px;border:1px solid rgba(148,163,184,0.22);background:rgba(15,23,42,0.16);}'
    + '.result-line{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;font-size:12px;}'
    + '.list{display:grid;gap:10px;}'
    + '.list-row{display:grid;gap:10px;padding:12px;border-radius:16px;border:1px solid rgba(148,163,184,0.16);background:rgba(15,23,42,0.1);}'
    + '.list-row-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;flex-wrap:wrap;}'
    + '.row-title{font-size:14px;font-weight:700;overflow-wrap:anywhere;}'
    + '.row-subtitle{font-size:12px;color:var(--secondary-text-color);overflow-wrap:anywhere;}'
    + '.muted{color:var(--secondary-text-color);}'
    + '.two-column{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));}'
    + '@media (max-width: 720px){.groups,.meta-grid,.two-column{grid-template-columns:1fr;}.shell{padding:14px;}}';

  class ModelCatalogWorkingGroupsCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._hass = null;
      this._config = null;
      this._loading = false;
      this._loaded = false;
      this._error = "";
      this._status = "";
      this._groups = [];
      this._search = "";
      this._stage = "";
      this._createOpen = false;
      this._selectMode = false;
      this._selectedIds = {};
      this._batchResult = null;

      this._boundClick = this._handleClick.bind(this);
    }

    setConfig(config) {
      this._config = {
        title: config && config.title ? String(config.title) : "Working Board",
        per_page: config && config.per_page ? Number(config.per_page) : 24,
      };
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      if (this.isConnected && !this._loaded && !this._loading) {
        this._loadGroups();
      }
    }

    connectedCallback() {
      if (this.shadowRoot) {
        this.shadowRoot.addEventListener("click", this._boundClick);
      }
      if (this._hass && !this._loaded && !this._loading) {
        this._loadGroups();
      }
    }

    disconnectedCallback() {
      if (this.shadowRoot) {
        this.shadowRoot.removeEventListener("click", this._boundClick);
      }
    }

    getCardSize() {
      return 10;
    }

    _readFilterInputs() {
      var root = this.shadowRoot;
      if (!root) {
        return;
      }
      var searchNode = root.querySelector("#working-board-search");
      var stageNode = root.querySelector("#working-board-stage");
      this._search = searchNode ? String(searchNode.value || "").trim().toLowerCase() : "";
      this._stage = stageNode ? String(stageNode.value || "").trim() : "";
    }

    async _loadGroups() {
      if (!this._hass || this._loading) {
        return;
      }
      this._loading = true;
      this._error = "";
      this._status = "";
      this._render();

      try {
        var response = await callServiceWithResponse(this._hass, "rest_command", "model_catalog_list_working_groups", {
          limit: this._config && this._config.per_page ? this._config.per_page : 24,
          stage: this._stage || undefined,
        });
        this._groups = Array.isArray(response.groups) ? response.groups : [];
        this._loaded = true;
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not load working groups.";
      } finally {
        this._loading = false;
        this._render();
      }
    }

    async _createGroup() {
      if (!this._hass) {
        return;
      }
      var root = this.shadowRoot;
      if (!root) {
        return;
      }
      var titleNode = root.querySelector("#create-group-title");
      var stageNode = root.querySelector("#create-group-stage");
      var notesNode = root.querySelector("#create-group-notes");
      var title = titleNode ? String(titleNode.value || "").trim() : "";
      if (!title) {
        this._error = "Group title is required.";
        this._render();
        return;
      }

      this._loading = true;
      this._error = "";
      this._status = "";
      this._render();
      try {
        await callServiceWithResponse(this._hass, "rest_command", "model_catalog_create_working_group", {
          title: title,
          stage: stageNode ? String(stageNode.value || "draft") : "draft",
          notes: notesNode ? String(notesNode.value || "") : "",
        });
        this._status = "Working group created.";
        this._createOpen = false;
        await this._loadGroups();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not create working group.";
        this._loading = false;
        this._render();
      }
    }

    _filteredGroups() {
      var search = this._search;
      return this._groups.filter(function (group) {
        if (!search) {
          return true;
        }
        var haystack = [group.title, group.notes, group.primary_file_path, group.folder_hint]
          .concat((group.items || []).map(function (item) { return item.file_path; }))
          .concat((group.links || []).map(function (link) { return link.model_ref; }))
          .join(" ")
          .toLowerCase();
        return haystack.indexOf(search) !== -1;
      });
    }

    _openGroupDetail(group) {
      fireBrowserModEvent(this, "browser_mod.popup", {
        title: group && group.title ? group.title : "Working Group",
        size: "wide",
        content: {
          type: "custom:model-catalog-working-group-detail-card",
          group_id: group.id,
        },
      });
    }

    _selectedGroups() {
      return this._groups.filter(function (group) {
        return !!this._selectedIds[group.id];
      }, this);
    }

    _toggleSelectMode(forceValue) {
      this._selectMode = typeof forceValue === "boolean" ? forceValue : !this._selectMode;
      if (!this._selectMode) {
        this._selectedIds = {};
      }
      this._render();
    }

    _toggleGroupSelection(groupId) {
      var numericId = Number(groupId || 0);
      if (!numericId) {
        return;
      }
      if (this._selectedIds[numericId]) {
        delete this._selectedIds[numericId];
      } else {
        this._selectedIds[numericId] = true;
      }
      this._render();
    }

    _openIntakeView() {
      window.location.assign('/3d-printing/model-catalog-intake');
    }

    _openSelectedLinkReview() {
      var groups = this._selectedGroups();
      if (!groups.length) {
        this._error = 'Select a working group first.';
        this._render();
        return;
      }
      if (groups.length !== 1) {
        this._error = 'Link review currently supports one selected working group at a time.';
        this._render();
        return;
      }
      this._status = '';
      this._error = '';
      this._openGroupDetail(groups[0]);
    }

    async _runBatchStageUpdate(stage) {
      var groups = this._selectedGroups();
      if (!groups.length) {
        this._error = 'Select one or more working groups first.';
        this._render();
        return;
      }

      this._loading = true;
      this._error = '';
      this._status = '';
      this._batchResult = null;
      this._render();

      var results = [];
      for (var index = 0; index < groups.length; index += 1) {
        var group = groups[index];
        try {
          await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_update_working_group', {
            group_id: group.id,
            title: group.title || '',
            stage: stage,
            notes: group.notes || '',
            primary_file_path: group.primary_file_path || '',
            folder_hint: group.folder_hint || '',
          });
          results.push({
            group_id: group.id,
            label: group.title || ('Group ' + String(group.id)),
            outcome: 'succeeded',
            message: 'marked ' + formatStage(stage),
          });
        } catch (error) {
          results.push({
            group_id: group.id,
            label: group.title || ('Group ' + String(group.id)),
            outcome: 'failed',
            message: error && error.message ? String(error.message) : 'update failed',
          });
        }
      }

      this._batchResult = {
        action: stage,
        total: results.length,
        succeeded: results.filter(function (result) { return result.outcome === 'succeeded'; }).length,
        partial: 0,
        failed: results.filter(function (result) { return result.outcome === 'failed'; }).length,
        results: results,
      };
      this._status = 'Batch ' + batchActionLabel(stage).toLowerCase() + ' complete.';
      this._selectedIds = {};
      this._selectMode = false;
      this._loading = false;
      await this._loadGroups();
    }

    _handleClick(event) {
      var target = event.target instanceof Element ? event.target.closest("[data-action]") : null;
      if (!target) {
        return;
      }
      var action = String(target.getAttribute("data-action") || "");
      if (!action) {
        return;
      }

      if (action === "refresh-board") {
        this._readFilterInputs();
        this._loadGroups();
        return;
      }
      if (action === "apply-search") {
        this._readFilterInputs();
        this._render();
        return;
      }
      if (action === "toggle-create") {
        this._createOpen = !this._createOpen;
        this._error = "";
        this._status = "";
        this._render();
        return;
      }
      if (action === 'toggle-select-mode') {
        this._toggleSelectMode();
        return;
      }
      if (action === 'toggle-group-selection') {
        this._toggleGroupSelection(target.getAttribute('data-group-id'));
        return;
      }
      if (action === 'batch-mark-ready') {
        this._runBatchStageUpdate('ready_to_publish');
        return;
      }
      if (action === 'open-intake') {
        this._openIntakeView();
        return;
      }
      if (action === 'link-review') {
        this._openSelectedLinkReview();
        return;
      }
      if (action === 'clear-batch-result') {
        this._batchResult = null;
        this._render();
        return;
      }
      if (action === "create-group") {
        this._createGroup();
        return;
      }
      if (action === "open-group") {
        var groupId = Number(target.getAttribute("data-group-id") || 0);
        var group = this._groups.find(function (candidate) { return Number(candidate.id) === groupId; });
        if (group) {
          this._openGroupDetail(group);
        }
      }
    }

    _renderGroup(group) {
      var primaryFileName = basename(group.primary_file_path || (group.items && group.items[0] ? group.items[0].file_path : "")) || "No primary file";
      var isSelected = !!this._selectedIds[group.id];
      return ''
        + '<article class="group-card' + (isSelected ? ' selected' : '') + '">'
        + '  <div class="title-row">'
        + '    <div>'
        + '      <div class="title">' + escapeHtml(group.title || "Untitled Group") + '</div>'
        + '      <div class="subtitle">' + escapeHtml(group.notes || group.folder_hint || "Sidecar-owned working group") + '</div>'
        + '    </div>'
        + '    <div class="button-row">' + (this._selectMode ? '<label class="selector"><input type="checkbox" data-action="toggle-group-selection" data-group-id="' + String(group.id) + '"' + (isSelected ? ' checked' : '') + '> Select</label>' : '') + '<span class="chip">' + escapeHtml(formatStage(group.stage)) + '</span></div>'
        + '  </div>'
        + '  <div class="meta-grid">'
        + '    <div class="meta-item"><div class="meta-label">Files</div><div class="meta-value">' + String((group.items || []).length) + '</div></div>'
        + '    <div class="meta-item"><div class="meta-label">Curated Links</div><div class="meta-value">' + String((group.links || []).length) + '</div></div>'
        + '    <div class="meta-item"><div class="meta-label">Primary</div><div class="meta-value">' + escapeHtml(primaryFileName) + '</div></div>'
        + '    <div class="meta-item"><div class="meta-label">Updated</div><div class="meta-value">' + escapeHtml(group.updated_at || group.created_at || "Unknown") + '</div></div>'
        + '  </div>'
        + (this._selectMode
          ? '<div class="muted">Row actions are replaced by the shared batch toolbar while selection mode is active.</div>'
          : '<div class="button-row"><button class="button primary" data-action="open-group" data-group-id="' + String(group.id) + '">Open</button><button class="button" data-action="open-intake">Open Intake</button></div>')
        + '</article>';
    }

    _render() {
      if (!this.shadowRoot || !this._config) {
        return;
      }
      var groups = this._filteredGroups();
      var bodyHtml = "";

      if (this._loading) {
        bodyHtml = '<div class="state-row">Loading working groups...</div>';
      } else if (this._error) {
        bodyHtml = '<div class="state-row">' + escapeHtml(this._error) + '</div>';
      } else if (!groups.length) {
        bodyHtml = '<div class="state-row">No working groups match the current filter state.</div>';
      } else {
        bodyHtml = '<div class="groups">' + groups.map(this._renderGroup.bind(this)).join("") + '</div>';
      }

      var createPanelHtml = this._createOpen
        ? ''
          + '<section class="panel">'
          + '  <div class="two-column">'
          + '    <div class="field"><label for="create-group-title">Group Title</label><input id="create-group-title" class="input" type="text" placeholder="Bracket Group"></div>'
          + '    <div class="field"><label for="create-group-stage">Stage</label><select id="create-group-stage" class="select">' + stageOptionsHtml("draft", false) + '</select></div>'
          + '  </div>'
          + '  <div class="field"><label for="create-group-notes">Notes</label><textarea id="create-group-notes" class="textarea" placeholder="Optional notes for the new working group"></textarea></div>'
          + '  <div class="button-row"><button class="button primary" data-action="create-group">Create Group</button><button class="button" data-action="toggle-create">Cancel</button></div>'
          + '</section>'
        : '';

      var selectedCount = this._selectedGroups().length;
      var batchToolbarHtml = this._selectMode
        ? ''
          + '<section class="batch-toolbar">'
          + '  <div class="title-row"><div><div class="title">' + String(selectedCount) + ' selected</div><div class="subtitle">Batch actions stay local to the Working Board and use the existing working-group update and popup flows.</div></div></div>'
          + '  <div class="button-row"><button class="button primary" data-action="batch-mark-ready"' + (!selectedCount ? ' disabled' : '') + '>Mark Ready</button><button class="button" data-action="open-intake"' + (!selectedCount ? ' disabled' : '') + '>Open Intake</button><button class="button" data-action="link-review"' + (!selectedCount ? ' disabled' : '') + '>Link Review</button><button class="button warn" data-action="toggle-select-mode">Cancel</button></div>'
          + '</section>'
        : '';

      var batchResultHtml = this._batchResult
        ? ''
          + '<section class="result-summary">'
          + '  <div class="title-row"><div><div class="title">Batch Result Summary</div><div class="subtitle">' + escapeHtml(batchActionLabel(this._batchResult.action)) + ' across ' + String(this._batchResult.total) + ' group(s).</div></div><button class="button" data-action="clear-batch-result">Close</button></div>'
          + '  <div class="button-row"><span class="chip ok">Succeeded ' + String(this._batchResult.succeeded) + '</span><span class="chip">Partial ' + String(this._batchResult.partial) + '</span><span class="chip warn">Failed ' + String(this._batchResult.failed) + '</span></div>'
          + '  <div class="list">' + this._batchResult.results.map(function (result) { return '<div class="result-line"><span>' + escapeHtml(result.label || ('Group ' + String(result.group_id || ''))) + '</span><span>' + escapeHtml(result.message || result.outcome) + '</span></div>'; }).join('') + '</div>'
          + '</section>'
        : '';

      this.shadowRoot.innerHTML = ''
        + '<style>' + sharedStyles + '</style>'
        + '<ha-card>'
        + '  <div class="shell">'
        + '    <div class="header">'
        + '      <div class="title-row">'
        + '        <div>'
        + '          <div class="title">' + escapeHtml(this._config.title) + '</div>'
        + '          <div class="subtitle">Browse sidecar-owned working groups, then open a detail popup to inspect items and manage curated links.</div>'
        + '        </div>'
        + '        <div class="button-row">'
        + '          <button class="button" data-action="refresh-board">Refresh</button>'
        + '          <button class="button ' + (this._selectMode ? 'warn' : '') + '" data-action="toggle-select-mode">' + (this._selectMode ? 'Cancel Select' : 'Select Groups') + '</button>'
        + '          <button class="button primary" data-action="toggle-create">' + (this._createOpen ? 'Close Create Form' : 'New Working Group') + '</button>'
        + '        </div>'
        + '      </div>'
        + '      ' + (this._status ? '<div class="status">' + escapeHtml(this._status) + '</div>' : '')
        + '      ' + (this._error ? '<div class="status error">' + escapeHtml(this._error) + '</div>' : '')
        + '    </div>'
        + '    <section class="toolbar">'
        + '      <div class="toolbar-row">'
        + '        <div class="field grow"><label for="working-board-search">Search</label><input id="working-board-search" class="input" type="text" value="' + escapeHtml(this._search) + '" placeholder="Group title, notes, file, or model ref"></div>'
        + '        <div class="field"><label for="working-board-stage">Stage</label><select id="working-board-stage" class="select">' + stageOptionsHtml(this._stage, true) + '</select></div>'
        + '      </div>'
        + '      <div class="button-row">'
        + '        <button class="button primary" data-action="apply-search">Apply Filters</button>'
        + '        <span class="status">Showing ' + String(groups.length) + ' group' + (groups.length === 1 ? '' : 's') + (this._selectMode ? ' / Selected ' + String(selectedCount) : '') + '</span>'
        + '      </div>'
        + '    </section>'
        + batchToolbarHtml
        + batchResultHtml
        + createPanelHtml
        + bodyHtml
        + '  </div>'
        + '</ha-card>';
    }
  }

  class ModelCatalogWorkingGroupDetailCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._hass = null;
      this._config = null;
      this._loading = false;
      this._group = null;
      this._error = "";
      this._status = "";
      this._searchResults = [];
      this._searchingFiles = false;

      this._boundClick = this._handleClick.bind(this);
    }

    setConfig(config) {
      this._config = Object.assign({}, config || {});
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      if (this.isConnected && this._config && this._config.group_id && !this._group && !this._loading) {
        this._loadGroup();
      }
    }

    connectedCallback() {
      if (this.shadowRoot) {
        this.shadowRoot.addEventListener("click", this._boundClick);
      }
      if (this._hass && this._config && this._config.group_id && !this._group && !this._loading) {
        this._loadGroup();
      }
    }

    disconnectedCallback() {
      if (this.shadowRoot) {
        this.shadowRoot.removeEventListener("click", this._boundClick);
      }
    }

    getCardSize() {
      return 12;
    }

    async _loadGroup() {
      if (!this._hass || !this._config || !this._config.group_id || this._loading) {
        return;
      }
      this._loading = true;
      this._error = "";
      this._render();
      try {
        var response = await callServiceWithResponse(this._hass, "rest_command", "model_catalog_get_working_group", {
          group_id: this._config.group_id,
        });
        this._group = response.group || null;
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not load working group detail.";
      } finally {
        this._loading = false;
        this._render();
      }
    }

    async _saveMetadata() {
      if (!this._group || !this._hass || !this.shadowRoot) {
        return;
      }
      var titleNode = this.shadowRoot.querySelector("#detail-title");
      var stageNode = this.shadowRoot.querySelector("#detail-stage");
      var notesNode = this.shadowRoot.querySelector("#detail-notes");
      this._loading = true;
      this._error = "";
      this._status = "";
      this._render();
      try {
        await callServiceWithResponse(this._hass, "rest_command", "model_catalog_update_working_group", {
          group_id: this._group.id,
          title: titleNode ? String(titleNode.value || "").trim() : this._group.title,
          stage: stageNode ? String(stageNode.value || this._group.stage) : this._group.stage,
          notes: notesNode ? String(notesNode.value || "") : this._group.notes,
        });
        this._status = "Working group updated.";
        this._loading = false;
        await this._loadGroup();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not update working group.";
        this._loading = false;
        this._render();
      }
    }

    async _searchWorkingFiles() {
      if (!this._hass || !this.shadowRoot) {
        return;
      }
      var queryNode = this.shadowRoot.querySelector("#attach-query");
      var extensionNode = this.shadowRoot.querySelector("#attach-extension");
      var query = queryNode ? String(queryNode.value || "").trim() : "";
      var extension = extensionNode ? String(extensionNode.value || "").trim() : "";
      if (!query) {
        this._error = "Enter a working-file search term first.";
        this._render();
        return;
      }

      this._searchingFiles = true;
      this._error = "";
      this._status = "";
      this._render();
      try {
        var response = await callServiceWithResponse(this._hass, "rest_command", "model_catalog_search_working_files", {
          q: query,
          extension: extension || undefined,
          limit: 12,
        });
        this._searchResults = Array.isArray(response.files) ? response.files : [];
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not search working files.";
      } finally {
        this._searchingFiles = false;
        this._render();
      }
    }

    async _attachFile(filePath, itemRole) {
      if (!this._group || !this._hass) {
        return;
      }
      this._loading = true;
      this._error = "";
      this._status = "";
      this._render();
      try {
        await callServiceWithResponse(this._hass, "rest_command", "model_catalog_attach_file_to_group", {
          group_id: this._group.id,
          file_path: filePath,
          item_role: itemRole || "supporting",
        });
        this._status = "File attached to working group.";
        this._loading = false;
        await this._loadGroup();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not attach file to working group.";
        this._loading = false;
        this._render();
      }
    }

    async _removeItem(itemId) {
      if (!this._group || !this._hass) {
        return;
      }
      if (!window.confirm("Remove this file from the working group?")) {
        return;
      }
      this._loading = true;
      this._error = "";
      this._status = "";
      this._render();
      try {
        await callServiceWithResponse(this._hass, "rest_command", "model_catalog_remove_working_group_item", {
          group_id: this._group.id,
          item_id: itemId,
        });
        this._status = "File removed from working group.";
        this._loading = false;
        await this._loadGroup();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not remove file from working group.";
        this._loading = false;
        this._render();
      }
    }

    async _addLink() {
      if (!this._group || !this._hass || !this.shadowRoot) {
        return;
      }
      var modelRefNode = this.shadowRoot.querySelector("#link-model-ref");
      var roleNode = this.shadowRoot.querySelector("#link-role");
      var modelRef = modelRefNode ? String(modelRefNode.value || "").trim() : "";
      if (!modelRef) {
        this._error = "Model reference is required to create a curated link.";
        this._render();
        return;
      }
      this._loading = true;
      this._error = "";
      this._status = "";
      this._render();
      try {
        await callServiceWithResponse(this._hass, "rest_command", "model_catalog_create_working_group_link", {
          group_id: this._group.id,
          model_ref: modelRef,
          link_role: roleNode ? String(roleNode.value || "related") : "related",
          metadata: {},
        });
        this._status = "Curated link saved.";
        this._loading = false;
        await this._loadGroup();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not create curated link.";
        this._loading = false;
        this._render();
      }
    }

    async _removeLink(linkId) {
      if (!this._group || !this._hass) {
        return;
      }
      if (!window.confirm("Remove this curated link?")) {
        return;
      }
      this._loading = true;
      this._error = "";
      this._status = "";
      this._render();
      try {
        await callServiceWithResponse(this._hass, "rest_command", "model_catalog_delete_working_group_link", {
          group_id: this._group.id,
          link_id: linkId,
        });
        this._status = "Curated link removed.";
        this._loading = false;
        await this._loadGroup();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not remove curated link.";
        this._loading = false;
        this._render();
      }
    }

    _openModel(modelRef) {
      if (!modelRef) {
        return;
      }
      fireBrowserModEvent(this, "browser_mod.popup", {
        title: modelRef,
        size: "wide",
        content: {
          type: "custom:model-detail-popup-card",
          model_ref: modelRef,
          model_entity: "input_text.model_catalog_sidecar_base_url",
        },
      });
    }

    _handleClick(event) {
      var target = event.target instanceof Element ? event.target.closest("[data-action]") : null;
      if (!target) {
        return;
      }
      var action = String(target.getAttribute("data-action") || "");
      if (!action) {
        return;
      }

      if (action === "refresh-detail") {
        this._loadGroup();
        return;
      }
      if (action === "save-metadata") {
        this._saveMetadata();
        return;
      }
      if (action === "search-working-files") {
        this._searchWorkingFiles();
        return;
      }
      if (action === "attach-search-result") {
        this._attachFile(String(target.getAttribute("data-file-path") || ""), String(target.getAttribute("data-item-role") || "supporting"));
        return;
      }
      if (action === "remove-item") {
        this._removeItem(Number(target.getAttribute("data-item-id") || 0));
        return;
      }
      if (action === "save-link") {
        this._addLink();
        return;
      }
      if (action === "remove-link") {
        this._removeLink(Number(target.getAttribute("data-link-id") || 0));
        return;
      }
      if (action === "open-model") {
        this._openModel(String(target.getAttribute("data-model-ref") || ""));
        return;
      }
      if (action === "open-primary" || action === "open-item-explorer" || action === "open-folder") {
        return;
      }
    }

    _renderSearchResults() {
      if (this._searchingFiles) {
        return '<div class="state-row">Searching indexed working files...</div>';
      }
      if (!this._searchResults.length) {
        return '<div class="state-row">No indexed working files loaded yet. Search after the working-file index has been populated.</div>';
      }
      return '<div class="list">' + this._searchResults.map(function (item) {
        return ''
          + '<article class="list-row">'
          + '  <div class="list-row-top">'
          + '    <div>'
          + '      <div class="row-title">' + escapeHtml(item.file_name_raw || basename(item.source_path_canonical)) + '</div>'
          + '      <div class="row-subtitle">' + escapeHtml(item.source_path_canonical || item.source_path_raw || "") + '</div>'
          + '    </div>'
          + '    <span class="chip">' + escapeHtml((item.file_extension || "").replace(/^\./, "") || "file") + '</span>'
          + '  </div>'
          + '  <div class="meta-grid">'
          + '    <div class="meta-item"><div class="meta-label">Size</div><div class="meta-value">' + escapeHtml(formatBytes(item.file_size_bytes)) + '</div></div>'
          + '    <div class="meta-item"><div class="meta-label">Validation</div><div class="meta-value">' + escapeHtml(item.validation_state || "ready") + '</div></div>'
          + '  </div>'
          + '  <div class="button-row">'
          + '    <button class="button primary" data-action="attach-search-result" data-item-role="primary" data-file-path="' + escapeHtml(item.source_path_canonical || item.source_path_raw || "") + '">Attach As Primary</button>'
          + '    <button class="button" data-action="attach-search-result" data-item-role="supporting" data-file-path="' + escapeHtml(item.source_path_canonical || item.source_path_raw || "") + '">Attach As Supporting</button>'
          + '  </div>'
          + '</article>';
      }).join("") + '</div>';
    }

    _render() {
      if (!this.shadowRoot || !this._config) {
        return;
      }

      var bodyHtml = "";
      if (this._loading && !this._group) {
        bodyHtml = '<div class="state-row">Loading working group...</div>';
      } else if (this._error && !this._group) {
        bodyHtml = '<div class="state-row">' + escapeHtml(this._error) + '</div>';
      } else if (!this._group) {
        bodyHtml = '<div class="state-row">Working group detail is not available.</div>';
      } else {
        var launchMeta = this._group.launch || {};
        var windowsLaunchEnabled = !!launchMeta.windows_launch_enabled;
        var primaryLaunch = launchMeta.primary || {};
        var folderLaunch = launchMeta.folder || {};
        var primaryFile = this._group.primary_file_path || ((this._group.items || []).length ? this._group.items[0].file_path : "");
        var folderPath = dirname(primaryFile) || this._group.folder_hint || (this._group.discovery && this._group.discovery.source_folder) || "";
        var primaryWindowsPath = String(primaryLaunch.windows_path || "");
        var folderWindowsPath = String(folderLaunch.windows_path || "");
        var disabledHint = windowsLaunchEnabled ? "" : "Launch and Explorer actions are disabled because ASSETS_ROOT_HOST is not mapped under /mnt/c.";
        var itemsHtml = (this._group.items || []).length
          ? '<div class="list">' + (this._group.items || []).map(function (item) {
              var itemLaunch = item && item.launch ? item.launch : {};
              var itemWindowsPath = String(itemLaunch.windows_path || "");
              var canLaunch = !!(itemLaunch && itemLaunch.can_launch_file && itemWindowsPath);
              var canExplorer = !!(itemLaunch && itemLaunch.can_open_in_explorer && itemWindowsPath);
              var launchHref = canLaunch ? toFileUri(itemWindowsPath) : "";
              var explorerHref = canExplorer ? toFileUri(dirname(itemWindowsPath)) : "";
              return ''
                + '<article class="list-row">'
                + '  <div class="list-row-top">'
                + '    <div>'
                + '      <div class="row-title">' + escapeHtml(basename(item.file_path)) + '</div>'
                + '      <div class="row-subtitle">' + escapeHtml(item.file_path || "") + '</div>'
                + '    </div>'
                + '    <span class="chip">' + escapeHtml(item.item_role || "supporting") + '</span>'
                + '  </div>'
                + '  <div class="button-row">'
                + (canLaunch
                  ? '    <a class="button" style="text-decoration:none;display:inline-flex;align-items:center;justify-content:center;" href="' + escapeHtml(launchHref) + '" target="_blank" rel="noopener noreferrer">Launch File</a>'
                  : '    <button class="button" disabled>Launch File</button>')
                + (canExplorer
                  ? '    <a class="button" style="text-decoration:none;display:inline-flex;align-items:center;justify-content:center;" href="' + escapeHtml(explorerHref) + '" target="_blank" rel="noopener noreferrer">Open In Explorer</a>'
                  : '    <button class="button" disabled>Open In Explorer</button>')
                + '    <button class="button danger" data-action="remove-item" data-item-id="' + String(item.id) + '">Remove</button>'
                + '  </div>'
                + '</article>';
            }).join("") + '</div>'
          : '<div class="state-row">No files are attached to this working group yet.</div>';

        var linksHtml = (this._group.links || []).length
          ? '<div class="list">' + (this._group.links || []).map(function (link) {
              return ''
                + '<article class="list-row">'
                + '  <div class="list-row-top">'
                + '    <div>'
                + '      <div class="row-title">' + escapeHtml(link.model_ref || "") + '</div>'
                + '      <div class="row-subtitle">Role: ' + escapeHtml(link.link_role || "related") + '</div>'
                + '    </div>'
                + '    <span class="chip">Linked</span>'
                + '  </div>'
                + '  <div class="button-row">'
                + '    <button class="button" data-action="open-model" data-model-ref="' + escapeHtml(link.model_ref || "") + '">Open Model</button>'
                + '    <button class="button danger" data-action="remove-link" data-link-id="' + String(link.id) + '">Unlink</button>'
                + '  </div>'
                + '</article>';
            }).join("") + '</div>'
          : '<div class="state-row">No curated links are attached yet.</div>';

        bodyHtml = ''
          + '<section class="section">'
          + '  <div class="title-row">'
          + '    <div>'
          + '      <div class="title">' + escapeHtml(this._group.title || "Untitled Group") + '</div>'
          + '      <div class="subtitle">Sidecar-owned working group detail for files, metadata, and curated link management.</div>'
          + '    </div>'
          + '    <div class="button-row">'
          + '      <button class="button" data-action="refresh-detail">Refresh</button>'
          + (folderPath
            ? (folderWindowsPath
              ? '<a class="button" style="text-decoration:none;display:inline-flex;align-items:center;justify-content:center;" href="' + escapeHtml(toFileUri(folderWindowsPath)) + '" target="_blank" rel="noopener noreferrer">Open Folder</a>'
              : '<button class="button" disabled>Open Folder</button>')
            : '')
          + (primaryFile
            ? (primaryWindowsPath
              ? '<a class="button" style="text-decoration:none;display:inline-flex;align-items:center;justify-content:center;" href="' + escapeHtml(toFileUri(primaryWindowsPath)) + '" target="_blank" rel="noopener noreferrer">Launch Primary</a>'
              : '<button class="button" disabled>Launch Primary</button>')
            : '')
          + '    </div>'
          + '  </div>'
          + '  ' + (this._status ? '<div class="status">' + escapeHtml(this._status) + '</div>' : '')
          + '  ' + (this._error ? '<div class="status error">' + escapeHtml(this._error) + '</div>' : '')
          + '  ' + (disabledHint ? '<div class="status">' + escapeHtml(disabledHint) + '</div>' : '')
          + '</section>'
          + '<div class="two-column">'
          + '  <section class="section">'
          + '    <div class="title">Metadata</div>'
          + '    <div class="field"><label for="detail-title">Title</label><input id="detail-title" class="input" type="text" value="' + escapeHtml(this._group.title || "") + '"></div>'
          + '    <div class="field"><label for="detail-stage">Stage</label><select id="detail-stage" class="select">' + stageOptionsHtml(this._group.stage || "draft", false) + '</select></div>'
          + '    <div class="field"><label for="detail-notes">Notes</label><textarea id="detail-notes" class="textarea">' + escapeHtml(this._group.notes || "") + '</textarea></div>'
          + '    <div class="button-row"><button class="button primary" data-action="save-metadata">Save Metadata</button></div>'
          + '  </section>'
          + '  <section class="section">'
          + '    <div class="title">Group Summary</div>'
          + '    <div class="meta-grid">'
          + '      <div class="meta-item"><div class="meta-label">Slug</div><div class="meta-value">' + escapeHtml(this._group.slug || "") + '</div></div>'
          + '      <div class="meta-item"><div class="meta-label">Stage</div><div class="meta-value">' + escapeHtml(formatStage(this._group.stage || "draft")) + '</div></div>'
          + '      <div class="meta-item"><div class="meta-label">Files</div><div class="meta-value">' + String((this._group.items || []).length) + '</div></div>'
          + '      <div class="meta-item"><div class="meta-label">Curated Links</div><div class="meta-value">' + String((this._group.links || []).length) + '</div></div>'
          + '      <div class="meta-item"><div class="meta-label">Folder Hint</div><div class="meta-value">' + escapeHtml(this._group.folder_hint || folderPath || "") + '</div></div>'
          + '      <div class="meta-item"><div class="meta-label">Updated</div><div class="meta-value">' + escapeHtml(this._group.updated_at || this._group.created_at || "") + '</div></div>'
          + '    </div>'
          + '  </section>'
          + '</div>'
          + '<div class="two-column">'
          + '  <section class="section">'
          + '    <div class="title">Files</div>'
          + '    ' + itemsHtml
          + '  </section>'
          + '  <section class="section">'
          + '    <div class="title">Curated Links</div>'
          + '    ' + linksHtml
          + '    <div class="field"><label for="link-model-ref">Add Model Reference</label><input id="link-model-ref" class="input" type="text" placeholder="gridfinity-bit-holder-v2"></div>'
          + '    <div class="field"><label for="link-role">Link Role</label><select id="link-role" class="select">' + linkRoleOptionsHtml("related") + '</select></div>'
          + '    <div class="button-row"><button class="button primary" data-action="save-link">Save Link</button></div>'
          + '  </section>'
          + '</div>'
          + '<section class="section">'
          + '  <div class="title">Search Working Files</div>'
          + '  <div class="toolbar-row">'
          + '    <div class="field grow"><label for="attach-query">Search</label><input id="attach-query" class="input" type="text" placeholder="bracket, holder, step"></div>'
          + '    <div class="field"><label for="attach-extension">Extension</label><select id="attach-extension" class="select"><option value="">All</option><option value=".3mf">3MF</option><option value=".stl">STL</option><option value=".step">STEP</option></select></div>'
          + '  </div>'
          + '  <div class="button-row"><button class="button primary" data-action="search-working-files">Search Indexed Files</button></div>'
          + '  ' + this._renderSearchResults()
          + '</section>';
      }

      this.shadowRoot.innerHTML = ''
        + '<style>' + sharedStyles + '</style>'
        + '<ha-card>'
        + '  <div class="shell">' + bodyHtml + '</div>'
        + '</ha-card>';
    }
  }

  if (!customElements.get("model-catalog-working-groups-card")) {
    customElements.define("model-catalog-working-groups-card", ModelCatalogWorkingGroupsCard);
  }
  if (!customElements.get("model-catalog-working-group-detail-card")) {
    customElements.define("model-catalog-working-group-detail-card", ModelCatalogWorkingGroupDetailCard);
  }
})();
