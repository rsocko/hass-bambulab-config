(function () {
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
    if (action === "create-group") {
      return "Create Groups";
    }
    if (action === "defer") {
      return "Defer";
    }
    if (action === "reject") {
      return "Reject";
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

  var sharedStyles = ''
    + 'ha-card{border-radius:20px;border:1px solid rgba(148,163,184,0.18);background:linear-gradient(180deg,rgba(15,23,42,0.08),rgba(15,23,42,0.02));}'
    + '.shell{display:grid;gap:14px;padding:16px;}'
    + '.header{display:grid;gap:8px;}'
    + '.title-row{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;flex-wrap:wrap;}'
    + '.title{font-size:18px;font-weight:800;line-height:1.2;}'
    + '.subtitle{font-size:12px;color:var(--secondary-text-color);}'
    + '.section,.panel,.entry-row,.summary-card,.banner{border-radius:18px;border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.12);}'
    + '.section,.panel,.banner{padding:14px;}'
    + '.toolbar-row,.button-row,.entry-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center;}'
    + '.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));}'
    + '.summary-card{padding:14px;display:grid;gap:6px;}'
    + '.summary-label{font-size:11px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;color:var(--secondary-text-color);}'
    + '.summary-value{font-size:16px;font-weight:800;overflow-wrap:anywhere;}'
    + '.field{display:grid;gap:6px;min-width:0;}'
    + '.field label{font-size:11px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;color:var(--secondary-text-color);}'
    + '.input,.select{width:100%;box-sizing:border-box;min-height:40px;padding:10px 12px;border-radius:12px;border:1px solid rgba(148,163,184,0.24);background:rgba(15,23,42,0.16);color:var(--primary-text-color);}'
    + '.select{color-scheme:light dark;}'
    + '.select option,.select optgroup{background:var(--card-background-color);color:var(--primary-text-color);}'
    + '.button{min-height:38px;padding:0 14px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(148,163,184,0.12);color:var(--primary-text-color);font-size:12px;font-weight:700;cursor:pointer;}'
    + '.button.primary{background:rgba(30,64,175,0.22);border-color:rgba(96,165,250,0.4);}'
    + '.button.warn{background:rgba(180,83,9,0.22);border-color:rgba(245,158,11,0.4);}'
    + '.button.danger{background:rgba(153,27,27,0.22);border-color:rgba(248,113,113,0.4);}'
    + '.button:disabled{opacity:.6;cursor:not-allowed;}'
    + '.status{font-size:12px;font-weight:700;color:var(--secondary-text-color);}'
    + '.status.error{color:#f87171;}'
    + '.chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;background:rgba(30,64,175,0.18);border:1px solid rgba(96,165,250,0.3);font-size:11px;font-weight:800;letter-spacing:.02em;text-transform:uppercase;}'
    + '.chip.warn{background:rgba(180,83,9,0.18);border-color:rgba(245,158,11,0.3);}'
    + '.chip.error{background:rgba(153,27,27,0.2);border-color:rgba(248,113,113,0.3);}'
    + '.chip.ok{background:rgba(22,101,52,0.22);border-color:rgba(74,222,128,0.3);}'
    + '.entries,.items{display:grid;gap:10px;}'
    + '.entry-row{display:grid;gap:10px;padding:12px;}'
    + '.entry-row.selected{border-color:rgba(96,165,250,0.4);background:rgba(30,64,175,0.18);}'
    + '.entry-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;flex-wrap:wrap;}'
    + '.entry-name{font-size:14px;font-weight:700;overflow-wrap:anywhere;}'
    + '.entry-path,.muted{font-size:12px;color:var(--secondary-text-color);overflow-wrap:anywhere;}'
    + '.state-row{padding:18px;border-radius:16px;border:1px dashed rgba(148,163,184,0.28);color:var(--secondary-text-color);text-align:center;}'
    + '.two-column{display:grid;gap:14px;grid-template-columns:minmax(0,1.2fr) minmax(0,0.8fr);}'
    + '.item-grid{display:grid;gap:8px;grid-template-columns:repeat(2,minmax(0,1fr));}'
    + '.link{color:var(--primary-color);cursor:pointer;text-decoration:underline;}'
    + '.batch-toolbar{display:grid;gap:10px;padding:12px;border-radius:18px;border:1px solid rgba(96,165,250,0.35);background:rgba(30,64,175,0.14);}'
    + '.result-summary{display:grid;gap:10px;padding:12px;border-radius:18px;border:1px solid rgba(148,163,184,0.22);background:rgba(15,23,42,0.16);}'
    + '.result-line{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;font-size:12px;}'
    + '.warning-box{display:grid;gap:6px;padding:12px;border-radius:14px;border:1px solid rgba(245,158,11,0.32);background:rgba(180,83,9,0.14);}'
    + '.warning-title{font-size:12px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;color:#fbbf24;}'
    + '.selector{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:700;color:var(--secondary-text-color);}'
    + '.hidden-upload-input{display:none;}'
    + '@media (max-width: 860px){.two-column,.grid,.item-grid{grid-template-columns:1fr;}.shell{padding:14px;}}';

  class ModelCatalogIntakeHomeCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._boundHandleClick = this._handleClick.bind(this);
      this._boundHandleChange = this._handleChange.bind(this);
      this._hass = null;
      this._config = null;
      this._loading = false;
      this._browseLoading = false;
      this._error = "";
      this._status = "";
      this._result = null;
      this._roots = [];
      this._browse = { path: "/", entries: [], parent_path: null, is_root: true };
      this._selected = {};
      this._browserFiles = [];
      this._intakeItems = [];
      this._queueUploads = [];
    }

    setConfig(config) {
      this._config = Object.assign({
        title: "Model Catalog Intake",
        sourceModeEntity: "input_select.intake_source_mode",
        cleanupPolicyEntity: "input_select.intake_cleanup_policy",
        browsePathEntity: "input_text.intake_browse_path",
      }, config || {});
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      if (this.isConnected && !this._loading && !this._roots.length) {
        this._refreshAll();
      }
    }

    connectedCallback() {
      if (this._hass && !this._loading && !this._roots.length) {
        this._refreshAll();
      }
      if (this.shadowRoot) {
        this.shadowRoot.addEventListener("click", this._boundHandleClick);
      }
    }

    disconnectedCallback() {
      if (this.shadowRoot) {
        this.shadowRoot.removeEventListener("click", this._boundHandleClick);
      }
    }

    getCardSize() {
      return 14;
    }

    _sourceMode() {
      return this._hass && this._hass.states[this._config.sourceModeEntity]
        ? String(this._hass.states[this._config.sourceModeEntity].state || "browser")
        : "browser";
    }

    _cleanupPolicy() {
      return this._hass && this._hass.states[this._config.cleanupPolicyEntity]
        ? String(this._hass.states[this._config.cleanupPolicyEntity].state || "keep")
        : "keep";
    }

    async _refreshAll() {
      if (!this._hass || this._loading) {
        return;
      }
      this._loading = true;
      this._error = "";
      this._render();
      try {
        var rootResponse = await callServiceWithResponse(this._hass, "rest_command", "model_catalog_list_source_filesystems", {});
        this._roots = Array.isArray(rootResponse.roots) ? rootResponse.roots : [];
        await this._loadBrowse(this._browse.path || "/");
        var itemsResponse = await callServiceWithResponse(this._hass, "rest_command", "model_catalog_list_intake_items", { limit: 100, offset: 0 });
        this._intakeItems = Array.isArray(itemsResponse.items) ? itemsResponse.items : [];
        var uploadResponse = await callServiceWithResponse(this._hass, "rest_command", "model_catalog_list_intake_uploads", { limit: 100 });
        this._queueUploads = Array.isArray(uploadResponse.uploads) ? uploadResponse.uploads : [];
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not load intake state.";
      } finally {
        this._loading = false;
        this._render();
      }
    }

    async _loadBrowse(path) {
      if (!this._hass) {
        return;
      }
      this._browseLoading = true;
      this._render();
      try {
        var response = await callServiceWithResponse(this._hass, "rest_command", "model_catalog_browse_source_filesystem", {
          path: path || "/",
        });
        this._browse = {
          path: response.path || "/",
          entries: Array.isArray(response.entries) ? response.entries : [],
          parent_path: response.parent_path || null,
          is_root: !!response.is_root,
          name: response.name || "",
        };
        await setHelperValue(this._hass, "input_text", this._config.browsePathEntity, this._browse.path);
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not browse source filesystem.";
      } finally {
        this._browseLoading = false;
        this._render();
      }
    }

    _toggleSelection(path, entryType) {
      var normalizedPath = String(path || '').trim();
      if (!normalizedPath) {
        return;
      }
      var nextSelected = Object.assign({}, this._selected);
      if (nextSelected[normalizedPath]) {
        delete nextSelected[normalizedPath];
      } else {
        nextSelected[normalizedPath] = {
          type: entryType,
          path: normalizedPath,
          recurse: true,
          max_depth: "",
          grouping_strategy: "none",
        };
      }
      this._selected = nextSelected;
      this._render();
    }

    _selectedList() {
      return Object.keys(this._selected).map(function (key) { return this._selected[key]; }, this);
    }

    _resolveSidecarUrl() {
      if (this._hass && this._hass.states) {
        var baseUrlEntity = this._hass.states['input_text.model_catalog_sidecar_base_url'];
        if (baseUrlEntity && baseUrlEntity.state) {
          return String(baseUrlEntity.state).trim();
        }
      }
      return String(this._config && this._config.model_sidecar_url || '').trim();
    }

    _serverPayloadSelections(sourceMode) {
      if (sourceMode === 'browser') {
        return [];
      }
      return this._selectedList().map(function (entry) {
        var next = { type: entry.type, path: entry.path };
        if (entry.type === 'folder') {
          next.recurse = !!entry.recurse;
          if (entry.recurse && entry.max_depth !== '' && entry.max_depth != null) {
            next.max_depth = Number(entry.max_depth);
          }
        }
        return next;
      });
    }

    _enabledBrowserFiles(sourceMode) {
      return sourceMode === 'server' ? [] : this._browserFiles.slice();
    }

    _appendBrowserFiles(fileList) {
      var nextByKey = {};
      this._browserFiles.forEach(function (entry) {
        var existingKey = String(entry.relative_path || entry.name || '').toLowerCase() + '::' + String(entry.size_bytes || 0);
        nextByKey[existingKey] = entry;
      });
      Array.prototype.slice.call(fileList || []).forEach(function (file) {
        if (!file || typeof file.arrayBuffer !== 'function') {
          return;
        }
        var relativePath = String(file.webkitRelativePath || file.name || '').trim() || String(file.name || '').trim();
        var nextEntry = {
          file: file,
          name: String(file.name || relativePath || 'upload.bin'),
          relative_path: relativePath,
          size_bytes: Number(file.size || 0),
        };
        var key = String(nextEntry.relative_path || nextEntry.name).toLowerCase() + '::' + String(nextEntry.size_bytes || 0);
        nextByKey[key] = nextEntry;
      });
      this._browserFiles = Object.keys(nextByKey).map(function (key) { return nextByKey[key]; }).sort(function (left, right) {
        return String(left.relative_path || left.name).localeCompare(String(right.relative_path || right.name));
      });
      this._render();
    }

    async _encodeBrowserFile(fileEntry) {
      var buffer = await fileEntry.file.arrayBuffer();
      var bytes = new Uint8Array(buffer);
      var chunkSize = 0x8000;
      var binary = '';
      for (var index = 0; index < bytes.length; index += chunkSize) {
        binary += String.fromCharCode.apply(null, bytes.subarray(index, index + chunkSize));
      }
      return {
        filename: fileEntry.name,
        relative_path: fileEntry.relative_path,
        content_base64: btoa(binary),
        file_last_modified_ms: fileEntry.file.lastModified || null,
      };
    }

    async _submitServerSelections() {
      if (!this._hass) {
        return;
      }
      var sourceMode = this._sourceMode();
      var payloadSelections = this._serverPayloadSelections(sourceMode);
      var browserFiles = this._enabledBrowserFiles(sourceMode);
      if (!payloadSelections.length && !browserFiles.length) {
        this._error = 'Select at least one browser file or server-side file first.';
        this._render();
        return;
      }
      this._loading = true;
      this._error = "";
      this._status = "";
      this._result = null;
      this._render();
      try {
        // For folder selections that have a grouping strategy, expand them via
        // bulk-discover first so individual files land in the intake queue.
        var expandedSelections = [];
        var plainSelections = [];
        for (var si = 0; si < payloadSelections.length; si += 1) {
          var sel = payloadSelections[si];
          var selState = this._selected[sel.path] || {};
          if (sel.type === 'folder' && selState.grouping_strategy && selState.grouping_strategy !== 'none') {
            try {
              var discoverRequest = {
                folder_path: sel.path,
                grouping_strategy: selState.grouping_strategy,
              };
              if (sel.max_depth != null) {
                discoverRequest.max_depth = sel.max_depth;
              }
              var discoverResponse = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_bulk_discover_working_groups', discoverRequest);
              var proposals = Array.isArray(discoverResponse && discoverResponse.proposals) ? discoverResponse.proposals : [];
              proposals.forEach(function (proposal) {
                (proposal.files || []).forEach(function (fileEntry) {
                  if (fileEntry.path) {
                    expandedSelections.push({ type: 'file', path: String(fileEntry.path) });
                  }
                });
              });
            } catch (_discoverError) {
              // Fallback: queue the folder as-is if discover fails.
              plainSelections.push(sel);
            }
          } else {
            plainSelections.push(sel);
          }
        }
        var finalSelections = plainSelections.concat(expandedSelections);
        var response;
        if (browserFiles.length) {
          var sidecarBaseUrl = this._resolveSidecarUrl();
          if (!sidecarBaseUrl) {
            throw new Error('Set input_text.model_catalog_sidecar_base_url to enable browser uploads.');
          }
          var encodedBrowserFiles = [];
          for (var browserIndex = 0; browserIndex < browserFiles.length; browserIndex += 1) {
            encodedBrowserFiles.push(await this._encodeBrowserFile(browserFiles[browserIndex]));
          }
          response = await postJsonWithAuth(this._hass, sidecarBaseUrl.replace(/\/$/, '') + '/api/intake/uploads/browser', {
            cleanup_policy: this._cleanupPolicy(),
            browser_files: encodedBrowserFiles,
            server_selections: finalSelections,
          });
        } else {
          response = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_select_source_filesystem_entries', {
            selections: finalSelections,
            cleanup_policy: this._cleanupPolicy(),
          });
        }
        var validation = await callServiceWithResponse(this._hass, "rest_command", "model_catalog_validate_intake_item", {
          item_id: response.upload_id,
        });
        this._result = {
          upload_id: response.upload_id,
          upload_status: response.status,
          selection_count: finalSelections.length + browserFiles.length,
          expanded_file_count: response.expanded_file_count != null ? response.expanded_file_count : response.source_entry_count,
          validation_state: validation.validation ? validation.validation.validation_state : "unknown",
          warnings: (response.warnings || []).concat(validation.validation ? validation.validation.warnings || [] : []),
          cleanup_policy: this._cleanupPolicy(),
        };
        this._status = browserFiles.length && finalSelections.length
          ? 'Browser files and server selections were queued together and validated.'
          : (browserFiles.length ? 'Browser files were queued to intake and validated.' : 'Selection queued to intake and validated.' + (expandedSelections.length ? ' (' + String(expandedSelections.length) + ' files expanded from grouped folder(s).)' : ''));
        this._selected = {};
        this._browserFiles = [];
        this._loading = false;
        await this._refreshAll();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not queue intake selection.";
        this._loading = false;
        this._render();
      }
    }

    async _setSourceMode(value) {
      if (!this._hass) {
        return;
      }
      await setHelperValue(this._hass, "input_select", this._config.sourceModeEntity, value);
      this._render();
    }

    async _setCleanupPolicy(value) {
      if (!this._hass) {
        return;
      }
      await setHelperValue(this._hass, "input_select", this._config.cleanupPolicyEntity, value);
      this._render();
    }

    _queueSummaryHtml() {
      var uploadCounts = summarizeStates(this._queueUploads, "status");
      var itemCounts = summarizeStates(this._intakeItems, "state");
      return ''
        + '<div class="grid">'
        + '  <div class="summary-card"><div class="summary-label">Source Mode</div><div class="summary-value">' + escapeHtml(formatLabel(this._sourceMode())) + '</div><div class="muted">Browser uploads now stage into the same intake queue contract as server-browse selections.</div></div>'
        + '  <div class="summary-card"><div class="summary-label">Cleanup Policy</div><div class="summary-value">' + escapeHtml(this._cleanupPolicy()) + '</div><div class="muted">Applied to new queue submissions. Browser-upload staging is managed by the sidecar before publish or delete.</div></div>'
        + '  <div class="summary-card"><div class="summary-label">Queue Health</div><div class="summary-value">Queued ' + String(uploadCounts.queued || 0) + ' / Verified ' + String(uploadCounts.verified || 0) + '</div><div class="muted">Failed ' + String(uploadCounts.failed || 0) + ' / Cleanup pending ' + String(uploadCounts.cleanup_pending || 0) + '</div></div>'
        + '  <div class="summary-card"><div class="summary-label">Inbox Snapshot</div><div class="summary-value">Ready ' + String(itemCounts.validated_ready || 0) + ' / Warning ' + String(itemCounts.validated_warning || 0) + '</div><div class="muted">Deferred ' + String(itemCounts.deferred || 0) + ' / Grouped ' + String((itemCounts.grouped_new || 0) + (itemCounts.grouped_existing || 0)) + '</div></div>'
        + '</div>';
    }

    _renderBrowserEntries() {
      if (!this._browserFiles.length) {
        return '<div class="state-row">Choose local files or a local folder to stage a browser-upload batch.</div>';
      }
      return '<div class="entries">' + this._browserFiles.map(function (entry) {
        return ''
          + '<article class="entry-row">'
          + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(entry.name || basename(entry.relative_path)) + '</div><div class="entry-path">' + escapeHtml(entry.relative_path || entry.name || '') + '</div></div><span class="chip">' + escapeHtml(formatBytes(entry.size_bytes || 0)) + '</span></div>'
          + '</article>';
      }).join('') + '</div>';
    }

    _renderBrowseEntries() {
      if (this._browseLoading) {
        return '<div class="state-row">Loading allowlisted source paths...</div>';
      }
      if (!this._browse.entries.length) {
        return '<div class="state-row">No allowlisted entries are available at this path.</div>';
      }
      return '<div class="entries">' + this._browse.entries.map(function (entry) {
        var selected = !!this._selected[entry.path];
        var selection = this._selected[entry.path] || { recurse: true, max_depth: "", grouping_strategy: "none" };
        return ''
          + '<article class="entry-row' + (selected ? ' selected' : '') + '">'
          + '  <div class="entry-top">'
          + '    <div>'
          + '      <div class="entry-name">' + escapeHtml(entry.name || basename(entry.path)) + '</div>'
          + '      <div class="entry-path">' + escapeHtml(entry.path || "") + '</div>'
          + '    </div>'
          + '    <div class="button-row">'
          + (entry.type === 'folder' ? '<span class="chip">Folder</span>' : '<span class="chip">File</span>')
          + (entry.type === 'file' && entry.size_bytes != null ? '<span class="chip">' + escapeHtml(formatBytes(entry.size_bytes)) + '</span>' : '')
          + '    </div>'
          + '  </div>'
          + '  <div class="entry-actions">'
          + (entry.type === 'folder'
            ? (selected
              ? '<button class="button" data-action="browse-path" data-path="' + escapeHtml(entry.path) + '">Open Contents</button>'
              : '<button class="button" data-action="browse-path" data-path="' + escapeHtml(entry.path) + '">Open</button>')
            : '')
          + '    <button class="button ' + (selected ? 'warn' : 'primary') + '" data-action="toggle-selection" data-entry-type="' + escapeHtml(entry.type) + '" data-path="' + escapeHtml(entry.path) + '">' + (selected ? 'Remove Selection' : 'Select') + '</button>'
          + '  </div>'
          + (selected && entry.type === 'folder'
            ? '<div class="item-grid">'
              + '<div class="field"><label>Recurse</label><select class="select" data-action="selection-recurse" data-path="' + escapeHtml(entry.path) + '"><option value="true"' + (selection.recurse ? ' selected' : '') + '>On</option><option value="false"' + (!selection.recurse ? ' selected' : '') + '>Off</option></select></div>'
              + '<div class="field"><label>Max Depth</label><input class="input" type="number" min="1" placeholder="Optional" value="' + escapeHtml(selection.max_depth) + '" data-action="selection-depth" data-path="' + escapeHtml(entry.path) + '"></div>'
              + '<div class="field"><label>Grouping</label><select class="select" data-action="selection-grouping" data-path="' + escapeHtml(entry.path) + '"><option value="none"' + (selection.grouping_strategy === 'none' ? ' selected' : '') + '>None (queue folder as-is)</option><option value="by-folder"' + (selection.grouping_strategy === 'by-folder' ? ' selected' : '') + '>by-folder</option><option value="by-root"' + (selection.grouping_strategy === 'by-root' ? ' selected' : '') + '>by-root</option><option value="flat"' + (selection.grouping_strategy === 'flat' ? ' selected' : '') + '>flat</option></select></div>'
              + '</div>'
            : '')
          + '</article>';
      }, this).join('') + '</div>';
    }

    _handleClick(event) {
      var target = event.target instanceof Element ? event.target.closest('[data-action]') : null;
      if (!target) {
        return;
      }
      event.preventDefault();
      var action = String(target.getAttribute('data-action') || '');
      if (!action) {
        return;
      }
      if (action === 'refresh-intake') {
        this._refreshAll();
        return;
      }
      if (action === 'browse-root') {
        this._loadBrowse('/');
        return;
      }
      if (action === 'browse-parent') {
        this._loadBrowse(target.getAttribute('data-path') || '/');
        return;
      }
      if (action === 'browse-path') {
        this._loadBrowse(target.getAttribute('data-path') || '/');
        return;
      }
      if (action === 'toggle-selection') {
        this._toggleSelection(String(target.getAttribute('data-path') || ''), String(target.getAttribute('data-entry-type') || 'file'));
        return;
      }
      if (action === 'choose-browser-files') {
        var fileInput = this.shadowRoot && this.shadowRoot.getElementById('browser-file-input');
        if (fileInput) {
          fileInput.click();
        }
        return;
      }
      if (action === 'choose-browser-folder') {
        var folderInput = this.shadowRoot && this.shadowRoot.getElementById('browser-folder-input');
        if (folderInput) {
          folderInput.click();
        }
        return;
      }
      if (action === 'clear-browser-files') {
        this._browserFiles = [];
        this._render();
        return;
      }
      if (action === 'submit-server-selection') {
        this._submitServerSelections();
        return;
      }
      if (action === 'goto-inbox') {
        window.location.assign('/3d-printing/model-catalog-inbox');
      }
    }

    _handleChange(event) {
      var target = event.target instanceof Element ? event.target : null;
      if (!target) {
        return;
      }
      var action = String(target.getAttribute('data-action') || '');
      if (action === 'source-mode') {
        this._setSourceMode(target.value);
        return;
      }
      if (action === 'browser-files' || action === 'browser-folder') {
        this._appendBrowserFiles(target.files);
        target.value = '';
        return;
      }
      if (action === 'cleanup-policy') {
        this._setCleanupPolicy(target.value);
        return;
      }
      var path = String(target.getAttribute('data-path') || '');
      if (!path || !this._selected[path]) {
        return;
      }
      if (action === 'selection-recurse') {
        this._selected = Object.assign({}, this._selected, {
          [path]: Object.assign({}, this._selected[path], {
            recurse: String(target.value) === 'true',
          }),
        });
        this._render();
        return;
      }
      if (action === 'selection-depth') {
        this._selected = Object.assign({}, this._selected, {
          [path]: Object.assign({}, this._selected[path], {
            max_depth: String(target.value || '').trim(),
          }),
        });
        this._render();
        return;
      }
      if (action === 'selection-grouping') {
        this._selected = Object.assign({}, this._selected, {
          [path]: Object.assign({}, this._selected[path], {
            grouping_strategy: String(target.value || 'none').trim(),
          }),
        });
        this._render();
      }
    }

    render() {
      this._render();
    }

    _render() {
      if (!this.shadowRoot || !this._config) {
        return;
      }
      var sourceMode = this._sourceMode();
      var browserFiles = this._enabledBrowserFiles(sourceMode);
      var serverSelections = this._serverPayloadSelections(sourceMode);
      var pendingSubmissionCount = browserFiles.length + serverSelections.length;
      var canSubmit = !this._loading && pendingSubmissionCount > 0;
      var selectedList = this._selectedList();
      var recentItems = this._intakeItems.slice(0, 5);
      var resultHtml = this._result
        ? '<section class="banner"><div class="title">Latest Result</div><div class="status">Upload ' + escapeHtml(this._result.upload_status) + ' / Validation ' + escapeHtml(this._result.validation_state) + ' / Cleanup ' + escapeHtml(this._result.cleanup_policy === 'keep' ? 'deferred (keep)' : 'pending policy') + '</div><div class="muted">Selection count ' + String(this._result.selection_count || 0) + ', expanded files ' + String(this._result.expanded_file_count || 0) + ', upload ' + escapeHtml(this._result.upload_id || '') + '</div>' + ((this._result.warnings || []).length ? '<div class="muted">Warnings: ' + escapeHtml((this._result.warnings || []).map(function (warning) { return warning.message || warning.code; }).join('; ')) + '</div>' : '') + '</section>'
        : '';

      this.shadowRoot.innerHTML = ''
        + '<style>' + sharedStyles + '</style>'
        + '<ha-card>'
        + '  <div class="shell">'
        + '    <div class="header">'
        + '      <div class="title-row">'
        + '        <div><div class="title">' + escapeHtml(this._config.title) + '</div><div class="subtitle">Queue-first intake summary, source-mode selection, cleanup policy, and allowlisted server browse.</div></div>'
        + '        <div class="button-row"><button class="button" data-action="refresh-intake">Refresh</button><button class="button primary" data-action="goto-inbox">Review Inbox</button></div>'
        + '      </div>'
        + '      ' + (this._error ? '<div class="status error">' + escapeHtml(this._error) + '</div>' : '')
        + '      ' + (this._status ? '<div class="status">' + escapeHtml(this._status) + '</div>' : '')
        + '    </div>'
        + resultHtml
        + this._queueSummaryHtml()
        + '    <section class="section">'
        + '      <div class="grid">'
        + '        <div class="field"><label for="source-mode-select">Source Mode</label><select id="source-mode-select" class="select" data-action="source-mode"><option value="browser"' + (sourceMode === 'browser' ? ' selected' : '') + '>Browser Upload</option><option value="server"' + (sourceMode === 'server' ? ' selected' : '') + '>Server Browse</option><option value="mixed"' + (sourceMode === 'mixed' ? ' selected' : '') + '>Mixed</option></select></div>'
        + '        <div class="field"><label for="cleanup-policy-select">Cleanup Policy</label><select id="cleanup-policy-select" class="select" data-action="cleanup-policy"><option value="keep"' + (this._cleanupPolicy() === 'keep' ? ' selected' : '') + '>keep</option><option value="delete_on_verified"' + (this._cleanupPolicy() === 'delete_on_verified' ? ' selected' : '') + '>delete_on_verified</option><option value="replace_with_stub"' + (this._cleanupPolicy() === 'replace_with_stub' ? ' selected' : '') + '>replace_with_stub</option></select></div>'
        + '      </div>'
        + '    </section>'
        + (sourceMode !== 'server'
          ? '<section class="section"><div class="title-row"><div><div class="title">Browser Upload</div><div class="subtitle">Pick local files or a local folder from this browser session. Mixed mode queues them together with selected allowlisted server paths.</div></div><div class="button-row"><button class="button" data-action="choose-browser-files">Add Files</button><button class="button" data-action="choose-browser-folder">Add Folder</button><button class="button warn" data-action="clear-browser-files"' + (!browserFiles.length ? ' disabled' : '') + '>Clear</button></div></div><input id="browser-file-input" class="hidden-upload-input" type="file" multiple data-action="browser-files"><input id="browser-folder-input" class="hidden-upload-input" type="file" multiple webkitdirectory directory data-action="browser-folder"><div class="muted">Browser-staged files: ' + String(browserFiles.length) + '</div>' + this._renderBrowserEntries() + '</section>'
          : '')
        + '    <div class="two-column">'
        + '      <section class="section">'
        + '        <div class="title-row"><div><div class="title">Server Browse</div><div class="subtitle">Select files or folders. Selected folders show Recurse, Max Depth, and Grouping controls inline.</div></div><div class="button-row"><button class="button" data-action="browse-root">Roots</button>'
        +          (this._browse.parent_path ? '<button class="button" data-action="browse-parent" data-path="' + escapeHtml(this._browse.parent_path) + '">Up</button>' : '')
        + '        </div></div>'
        + '        <div class="muted">Current path: ' + escapeHtml(this._browse.path || '/') + '</div>'
        + this._renderBrowseEntries()
        + '      </section>'
        + '      <section class="section">'
        + '        <div class="title">Submission</div>'
        + '        <div class="muted">Pending sources: ' + String(pendingSubmissionCount) + ' (' + String(serverSelections.length) + ' server / ' + String(browserFiles.length) + ' browser)</div>'
        + ((serverSelections.length || browserFiles.length)
          ? '<div class="entries">'
            + browserFiles.map(function (entry) {
                return '<article class="entry-row"><div class="entry-name">' + escapeHtml(entry.name || basename(entry.relative_path)) + '</div><div class="entry-path">' + escapeHtml(entry.relative_path || entry.name || '') + '</div><div class="button-row"><span class="chip">browser</span><span class="chip">' + escapeHtml(formatBytes(entry.size_bytes || 0)) + '</span></div></article>';
              }).join('')
            + serverSelections.map(function (entry) {
                return '<article class="entry-row"><div class="entry-name">' + escapeHtml(basename(entry.path) || entry.path) + '</div><div class="entry-path">' + escapeHtml(entry.path) + '</div><div class="button-row"><span class="chip">' + escapeHtml(entry.type) + '</span>' + (entry.type === 'folder' ? '<span class="chip">recurse ' + escapeHtml(entry.recurse ? 'on' : 'off') + '</span>' + (entry.max_depth ? '<span class="chip">max depth ' + escapeHtml(entry.max_depth) + '</span>' : '') : '') + '</div></article>';
              }).join('')
            + '</div>'
          : '<div class="state-row">Select browser files, server-side files, or both to add to the queue-first intake batch.</div>')
        + '        <div class="button-row"><button class="button primary" data-action="submit-server-selection"' + (!canSubmit ? ' disabled' : '') + '>Queue To Intake</button></div>'
        + '        <div class="muted">Recent activity</div>'
        + (recentItems.length ? '<div class="entries">' + recentItems.map(function (item) {
            var sourceEntry = item.source_entry || {};
            return '<article class="entry-row"><div class="entry-top"><div><div class="entry-name">' + escapeHtml(basename(sourceEntry.path || item.item_id)) + '</div><div class="entry-path">' + escapeHtml(sourceEntry.path || item.item_id) + '</div></div><span class="chip">' + escapeHtml(formatLabel(item.state || item.status)) + '</span></div></article>';
          }).join('') + '</div>' : '<div class="state-row">No intake items have been created yet.</div>')
        + '      </section>'
        + '    </div>'
        + '  </div>'
        + '</ha-card>';

      var selects = this.shadowRoot.querySelectorAll('select[data-action], input[data-action]');
      for (var index = 0; index < selects.length; index += 1) {
        selects[index].onchange = this._boundHandleChange;
        selects[index].oninput = this._boundHandleChange;
      }
    }
  }

  class ModelCatalogInboxReviewCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._hass = null;
      this._config = null;
      this._loading = false;
      this._error = '';
      this._status = '';
      this._items = [];
      this._workingGroups = [];
      this._stateFilter = '';
      this._selectMode = false;
      this._selectedIds = {};
      this._batchResult = null;
    }

    setConfig(config) {
      this._config = Object.assign({ title: 'Inbox Review' }, config || {});
      this._render();
    }

    set hass(hass) {
      this._hass = hass;
      if (this.isConnected && !this._loading && !this._items.length) {
        this._refresh();
      }
    }

    connectedCallback() {
      if (this._hass && !this._loading && !this._items.length) {
        this._refresh();
      }
      if (this.shadowRoot) {
        this.shadowRoot.addEventListener('click', this._handleClick.bind(this));
      }
    }

    disconnectedCallback() {
      if (this.shadowRoot) {
        this.shadowRoot.removeEventListener('click', this._handleClick.bind(this));
      }
    }

    getCardSize() {
      return 16;
    }

    async _refresh() {
      if (!this._hass || this._loading) {
        return;
      }
      this._loading = true;
      this._error = '';
      this._render();
      try {
        var itemsResponse = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_list_intake_items', {
          limit: 100,
          offset: 0,
          state_filter: this._stateFilter || undefined,
        });
        this._items = Array.isArray(itemsResponse.items) ? itemsResponse.items : [];
        var groupsResponse = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_list_working_groups', {
          limit: 200,
          offset: 0,
        });
        this._workingGroups = Array.isArray(groupsResponse.groups) ? groupsResponse.groups : [];
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not load inbox review state.';
      } finally {
        this._loading = false;
        this._render();
      }
    }

    async _validateItem(itemId) {
      this._loading = true;
      this._error = '';
      this._status = '';
      this._render();
      try {
        var response = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_validate_intake_item', { item_id: itemId });
        this._status = 'Validation complete: ' + (response.validation ? response.validation.validation_state : 'done');
        this._loading = false;
        await this._refresh();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not validate intake item.';
        this._loading = false;
        this._render();
      }
    }

    async _deferItem(itemId) {
      var note = window.prompt('Deferral note', 'Deferred by operator');
      if (note == null) {
        return;
      }
      this._loading = true;
      this._error = '';
      this._status = '';
      this._render();
      try {
        await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_defer_intake_item', { item_id: itemId, note: note });
        this._status = 'Item deferred.';
        this._loading = false;
        await this._refresh();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not defer intake item.';
        this._loading = false;
        this._render();
      }
    }

    async _rejectItem(itemId) {
      var note = window.prompt('Rejection note', 'Rejected by operator');
      if (note == null) {
        return;
      }
      this._loading = true;
      this._error = '';
      this._status = '';
      this._render();
      try {
        await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_reject_intake_item', { item_id: itemId, note: note });
        this._status = 'Item rejected.';
        this._loading = false;
        await this._refresh();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not reject intake item.';
        this._loading = false;
        this._render();
      }
    }

    async _createGroup(itemId, sourcePath) {
      var title = window.prompt('Working group title', basename(sourcePath || '') || 'Working Group');
      if (!title) {
        return;
      }
      this._loading = true;
      this._error = '';
      this._status = '';
      this._render();
      try {
        await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_group_intake_item', {
          item_id: itemId,
          action: 'create_working_group',
          title: title,
          stage: 'draft',
        });
        this._status = 'Working group created from intake item.';
        this._loading = false;
        await this._refresh();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not create working group.';
        this._loading = false;
        this._render();
      }
    }

    async _attachExisting(itemId) {
      var options = this._workingGroups.map(function (group) {
        return String(group.id) + ': ' + (group.title || 'Untitled Group');
      }).join('\n');
      var answer = window.prompt('Attach to existing working group. Enter the numeric group ID.\n\n' + options, this._workingGroups.length ? String(this._workingGroups[0].id) : '');
      if (!answer) {
        return;
      }
      var groupId = Number(answer);
      if (!Number.isFinite(groupId) || groupId <= 0) {
        this._error = 'A valid working group ID is required.';
        this._render();
        return;
      }
      this._loading = true;
      this._error = '';
      this._status = '';
      this._render();
      try {
        await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_group_intake_item', {
          item_id: itemId,
          action: 'attach_existing_working_group',
          working_group_id: groupId,
        });
        this._status = 'Intake item attached to existing working group.';
        this._loading = false;
        await this._refresh();
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not attach intake item to working group.';
        this._loading = false;
        this._render();
      }
    }

    _selectedItems() {
      return this._items.filter(function (item) {
        return !!this._selectedIds[item.item_id];
      }, this);
    }

    _toggleSelectMode(forceValue) {
      this._selectMode = typeof forceValue === 'boolean' ? forceValue : !this._selectMode;
      if (!this._selectMode) {
        this._selectedIds = {};
      }
      this._render();
    }

    _toggleItemSelection(itemId) {
      if (!itemId) {
        return;
      }
      if (this._selectedIds[itemId]) {
        delete this._selectedIds[itemId];
      } else {
        this._selectedIds[itemId] = true;
      }
      this._render();
    }

    async _runBatchAction(action) {
      var selectedItems = this._selectedItems();
      if (!selectedItems.length) {
        this._error = 'Select one or more inbox items first.';
        this._render();
        return;
      }

      var note = '';
      if (action === 'defer') {
        note = window.prompt('Batch deferral note', 'Deferred by operator (batch)');
        if (note == null) {
          return;
        }
      }
      if (action === 'reject') {
        note = window.prompt('Batch rejection note', 'Rejected by operator (batch)');
        if (note == null) {
          return;
        }
      }

      this._loading = true;
      this._error = '';
      this._status = '';
      this._batchResult = null;
      this._render();

      var results = [];
      for (var index = 0; index < selectedItems.length; index += 1) {
        var item = selectedItems[index];
        var sourceEntry = item.source_entry || {};
        try {
          if (action === 'validate') {
            var validationResponse = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_validate_intake_item', { item_id: item.item_id });
            var validationState = validationResponse.validation ? validationResponse.validation.validation_state : 'done';
            var validationWarnings = validationResponse.validation ? validationResponse.validation.warnings || [] : [];
            results.push({
              item_id: item.item_id,
              label: basename(sourceEntry.path || item.item_id),
              outcome: validationState === 'ready' ? 'succeeded' : 'partial',
              message: validationState === 'ready'
                ? 'validated ready'
                : 'validated ' + validationState + (validationWarnings.length ? ': ' + warningMessages(validationWarnings).join('; ') : ''),
            });
            continue;
          }

          if (action === 'create-group') {
            var title = basename(sourceEntry.path || '') || 'Working Group';
            await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_group_intake_item', {
              item_id: item.item_id,
              action: 'create_working_group',
              title: title,
              stage: 'draft',
            });
            results.push({
              item_id: item.item_id,
              label: basename(sourceEntry.path || item.item_id),
              outcome: 'succeeded',
              message: 'created working group ' + title,
            });
            continue;
          }

          if (action === 'defer') {
            await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_defer_intake_item', { item_id: item.item_id, note: note || 'Deferred by operator (batch)' });
            results.push({
              item_id: item.item_id,
              label: basename(sourceEntry.path || item.item_id),
              outcome: 'succeeded',
              message: 'deferred',
            });
            continue;
          }

          if (action === 'reject') {
            await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_reject_intake_item', { item_id: item.item_id, note: note || 'Rejected by operator (batch)' });
            results.push({
              item_id: item.item_id,
              label: basename(sourceEntry.path || item.item_id),
              outcome: 'succeeded',
              message: 'rejected',
            });
          }
        } catch (error) {
          results.push({
            item_id: item.item_id,
            label: basename(sourceEntry.path || item.item_id),
            outcome: 'failed',
            message: error && error.message ? String(error.message) : 'action failed',
          });
        }
      }

      this._batchResult = {
        action: action,
        total: results.length,
        succeeded: results.filter(function (result) { return result.outcome === 'succeeded'; }).length,
        partial: results.filter(function (result) { return result.outcome === 'partial'; }).length,
        failed: results.filter(function (result) { return result.outcome === 'failed'; }).length,
        results: results,
      };
      this._status = 'Batch ' + batchActionLabel(action).toLowerCase() + ' complete.';
      this._selectedIds = {};
      this._selectMode = false;
      this._loading = false;
      await this._refresh();
    }

    _handleClick(event) {
      var target = event.target instanceof Element ? event.target.closest('[data-action]') : null;
      if (!target) {
        return;
      }
      var action = String(target.getAttribute('data-action') || '');
      var itemId = String(target.getAttribute('data-item-id') || '');
      var sourcePath = String(target.getAttribute('data-source-path') || '');
      if (action === 'refresh-inbox') {
        this._refresh();
        return;
      }
      if (action === 'toggle-select-mode') {
        this._toggleSelectMode();
        return;
      }
      if (action === 'toggle-item-selection') {
        this._toggleItemSelection(itemId);
        return;
      }
      if (action === 'clear-batch-result') {
        this._batchResult = null;
        this._render();
        return;
      }
      if (action === 'batch-validate') {
        this._runBatchAction('validate');
        return;
      }
      if (action === 'batch-create-group') {
        this._runBatchAction('create-group');
        return;
      }
      if (action === 'batch-defer') {
        this._runBatchAction('defer');
        return;
      }
      if (action === 'batch-reject') {
        this._runBatchAction('reject');
        return;
      }
      if (action === 'validate-item') {
        this._validateItem(itemId);
        return;
      }
      if (action === 'defer-item') {
        this._deferItem(itemId);
        return;
      }
      if (action === 'reject-item') {
        this._rejectItem(itemId);
        return;
      }
      if (action === 'create-group') {
        this._createGroup(itemId, sourcePath);
        return;
      }
      if (action === 'attach-existing') {
        this._attachExisting(itemId);
      }
    }

    _handleFilterChange(event) {
      var target = event.target instanceof Element ? event.target : null;
      if (!target) {
        return;
      }
      this._stateFilter = String(target.value || '').trim();
      this._refresh();
    }

    _render() {
      if (!this.shadowRoot || !this._config) {
        return;
      }
      var selectedCount = this._selectedItems().length;
      this.shadowRoot.innerHTML = ''
        + '<style>' + sharedStyles + '</style>'
        + '<ha-card>'
        + '  <div class="shell">'
        + '    <div class="header"><div class="title-row"><div><div class="title">' + escapeHtml(this._config.title) + '</div><div class="subtitle">Review queue-first intake items before grouping them into Working.</div></div><div class="button-row"><button class="button" data-action="refresh-inbox">Refresh</button><button class="button ' + (this._selectMode ? 'warn' : '') + '" data-action="toggle-select-mode">' + (this._selectMode ? 'Cancel Select' : 'Select Items') + '</button></div></div>'
        + '    ' + (this._error ? '<div class="status error">' + escapeHtml(this._error) + '</div>' : '')
        + '    ' + (this._status ? '<div class="status">' + escapeHtml(this._status) + '</div>' : '')
        + '    </div>'
        + '    <section class="section"><div class="toolbar-row"><div class="field"><label for="inbox-state-filter">State Filter</label><select id="inbox-state-filter" class="select"><option value="">All</option><option value="submitted"' + (this._stateFilter === 'submitted' ? ' selected' : '') + '>Submitted</option><option value="validated_ready"' + (this._stateFilter === 'validated_ready' ? ' selected' : '') + '>Validated Ready</option><option value="validated_warning"' + (this._stateFilter === 'validated_warning' ? ' selected' : '') + '>Validated Warning</option><option value="deferred"' + (this._stateFilter === 'deferred' ? ' selected' : '') + '>Deferred</option><option value="rejected"' + (this._stateFilter === 'rejected' ? ' selected' : '') + '>Rejected</option><option value="grouped_new"' + (this._stateFilter === 'grouped_new' ? ' selected' : '') + '>Grouped New</option><option value="grouped_existing"' + (this._stateFilter === 'grouped_existing' ? ' selected' : '') + '>Grouped Existing</option></select></div><div class="status">Items: ' + String(this._items.length) + (this._selectMode ? ' / Selected: ' + String(selectedCount) : '') + '</div></div></section>'
        + '    ' + (this._selectMode ? '<section class="batch-toolbar"><div class="title-row"><div><div class="title">' + String(selectedCount) + ' selected</div><div class="subtitle">Batch review uses the existing item-level intake services and keeps mixed outcomes visible below.</div></div></div><div class="button-row"><button class="button primary" data-action="batch-validate"' + (!selectedCount ? ' disabled' : '') + '>Validate</button><button class="button primary" data-action="batch-create-group"' + (!selectedCount ? ' disabled' : '') + '>Create Groups</button><button class="button warn" data-action="batch-defer"' + (!selectedCount ? ' disabled' : '') + '>Defer</button><button class="button danger" data-action="batch-reject"' + (!selectedCount ? ' disabled' : '') + '>Reject</button><button class="button" data-action="toggle-select-mode">Cancel</button></div></section>' : '')
        + '    ' + (this._batchResult ? '<section class="result-summary"><div class="title-row"><div><div class="title">Batch Result Summary</div><div class="subtitle">' + escapeHtml(batchActionLabel(this._batchResult.action)) + ' across ' + String(this._batchResult.total) + ' item(s).</div></div><button class="button" data-action="clear-batch-result">Dismiss</button></div><div class="button-row"><span class="chip ok">Succeeded ' + String(this._batchResult.succeeded) + '</span><span class="chip warn">Partial ' + String(this._batchResult.partial) + '</span><span class="chip error">Failed ' + String(this._batchResult.failed) + '</span></div><div class="entries">' + this._batchResult.results.map(function (result) { return '<div class="result-line"><span>' + escapeHtml(result.label || result.item_id) + '</span><span>' + escapeHtml(result.message || result.outcome) + '</span></div>'; }).join('') + '</div></section>' : '')
        + '    ' + (this._loading && !this._items.length ? '<div class="state-row">Loading inbox items...</div>' : '')
        + '    ' + (!this._loading && !this._items.length ? '<div class="state-row">No intake items match the current filter.</div>' : '')
        + '    ' + (this._items.length ? '<div class="items">' + this._items.map(function (item) {
            var sourceEntry = item.source_entry || {};
            var warnings = parseDecisionWarnings(item);
            var warningsText = warningMessages(warnings).join('; ');
            if (!warningsText) {
              warningsText = item.decision_note || '';
            }
            var duplicateSignals = duplicateWarnings(item);
            var isSelected = !!this._selectedIds[item.item_id];
            return ''
              + '<article class="entry-row' + (isSelected ? ' selected' : '') + '">'
              + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(basename(sourceEntry.path || item.item_id)) + '</div><div class="entry-path">' + escapeHtml(sourceEntry.path || item.item_id) + '</div></div><div class="button-row">' + (this._selectMode ? '<label class="selector"><input type="checkbox" data-action="toggle-item-selection" data-item-id="' + escapeHtml(item.item_id) + '"' + (isSelected ? ' checked' : '') + '> Select</label>' : '') + '<span class="chip ' + ((item.state || '').indexOf('warning') >= 0 ? 'warn' : '') + '">' + escapeHtml(formatLabel(item.state || item.status)) + '</span><span class="chip ' + (duplicateSignals.length ? 'warn' : (String(item.verification_status || '').toLowerCase() === 'pass' ? 'ok' : '')) + '">' + escapeHtml(item.verification_status || item.status || 'unknown') + '</span></div></div>'
              + '  <div class="item-grid"><div class="summary-card"><div class="summary-label">Cleanup Policy</div><div class="summary-value">' + escapeHtml(item.cleanup_policy || 'keep') + '</div></div><div class="summary-card"><div class="summary-label">Queue Status</div><div class="summary-value">' + escapeHtml(item.status || 'queued') + '</div></div></div>'
              + (duplicateSignals.length ? '<div class="warning-box"><div class="warning-title">Duplicate Candidate</div><div class="muted">' + escapeHtml(warningMessages(duplicateSignals).join('; ')) + '</div></div>' : '')
              + (warningsText ? '<div class="muted">Validation / note: ' + escapeHtml(warningsText) + '</div>' : '')
              + (this._selectMode ? '<div class="muted">Row actions are replaced by the shared batch toolbar while selection mode is active.</div>' : '<div class="entry-actions"><button class="button" data-action="validate-item" data-item-id="' + escapeHtml(item.item_id) + '">Validate</button><button class="button primary" data-action="create-group" data-item-id="' + escapeHtml(item.item_id) + '" data-source-path="' + escapeHtml(sourceEntry.path || '') + '">Create Group</button><button class="button" data-action="attach-existing" data-item-id="' + escapeHtml(item.item_id) + '">Attach Existing</button><button class="button warn" data-action="defer-item" data-item-id="' + escapeHtml(item.item_id) + '">Defer</button><button class="button danger" data-action="reject-item" data-item-id="' + escapeHtml(item.item_id) + '">Reject</button></div>')
              + '</article>';
          }, this).join('') + '</div>' : '')
        + '  </div>'
        + '</ha-card>';

      var filterNode = this.shadowRoot.querySelector('#inbox-state-filter');
      if (filterNode) {
        filterNode.onchange = this._handleFilterChange.bind(this);
      }
    }
  }

  if (!customElements.get('model-catalog-intake-home-card')) {
    customElements.define('model-catalog-intake-home-card', ModelCatalogIntakeHomeCard);
  }
  if (!customElements.get('model-catalog-inbox-review-card')) {
    customElements.define('model-catalog-inbox-review-card', ModelCatalogInboxReviewCard);
  }
})();