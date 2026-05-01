var intakeShared = window.ModelCatalogIntakeShared;
if (!intakeShared) {
  throw new Error("model-catalog-intake-shared.js must load before model-catalog-intake-home-card.js");
}

var escapeHtml = intakeShared.escapeHtml;
var basename = intakeShared.basename;
var formatBytes = intakeShared.formatBytes;
var formatLabel = intakeShared.formatLabel;
var summarizeStates = intakeShared.summarizeStates;
var callServiceWithResponse = intakeShared.callServiceWithResponse;
var selectInputOption = intakeShared.selectInputOption;
var postJsonWithAuth = intakeShared.postJsonWithAuth;
var setHelperValue = intakeShared.setHelperValue;
var sharedStyles = intakeShared.sharedStyles;

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
      sectionEntity: "",
      inboxSection: "inbox",
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
    var value = this._hass && this._hass.states[this._config.sourceModeEntity]
      ? String(this._hass.states[this._config.sourceModeEntity].state || "browser")
      : "browser";
    return value === "server" ? "server" : "browser";
  }

  _cleanupPolicy() {
    return this._hass && this._hass.states[this._config.cleanupPolicyEntity]
      ? String(this._hass.states[this._config.cleanupPolicyEntity].state || "keep")
      : "keep";
  }

  async _navigateToSection(option, fallbackPath) {
    try {
      var navigated = await selectInputOption(this._hass, this._config.sectionEntity, option);
      if (navigated) {
        return;
      }
    } catch (_error) {
      // Fall back to legacy path-based navigation.
    }

    if (fallbackPath) {
      window.location.assign(fallbackPath);
    }
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
    var normalizedPath = String(path || "").trim();
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
      var baseUrlEntity = this._hass.states["input_text.model_catalog_sidecar_base_url"];
      if (baseUrlEntity && baseUrlEntity.state) {
        return String(baseUrlEntity.state).trim();
      }
    }
    return String(this._config && this._config.model_sidecar_url || "").trim();
  }

  _serverPayloadSelections(sourceMode) {
    if (sourceMode !== "server") {
      return [];
    }
    return this._selectedList().map(function (entry) {
      var next = { type: entry.type, path: entry.path };
      if (entry.type === "folder") {
        next.recurse = !!entry.recurse;
        if (entry.recurse && entry.max_depth !== "" && entry.max_depth != null) {
          next.max_depth = Number(entry.max_depth);
        }
      }
      return next;
    });
  }

  _enabledBrowserFiles(sourceMode) {
    return sourceMode === "browser" ? this._browserFiles.slice() : [];
  }

  _appendBrowserFiles(fileList) {
    var nextByKey = {};
    this._browserFiles.forEach(function (entry) {
      var existingKey = String(entry.relative_path || entry.name || "").toLowerCase() + "::" + String(entry.size_bytes || 0);
      nextByKey[existingKey] = entry;
    });
    Array.prototype.slice.call(fileList || []).forEach(function (file) {
      if (!file || typeof file.arrayBuffer !== "function") {
        return;
      }
      var relativePath = String(file.webkitRelativePath || file.name || "").trim() || String(file.name || "").trim();
      var nextEntry = {
        file: file,
        name: String(file.name || relativePath || "upload.bin"),
        relative_path: relativePath,
        size_bytes: Number(file.size || 0),
      };
      var key = String(nextEntry.relative_path || nextEntry.name).toLowerCase() + "::" + String(nextEntry.size_bytes || 0);
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
    var binary = "";
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
      this._error = "Select at least one browser file or server-side file first.";
      this._render();
      return;
    }
    this._loading = true;
    this._error = "";
    this._status = "";
    this._result = null;
    this._render();
    try {
      var expandedSelections = [];
      var plainSelections = [];
      for (var si = 0; si < payloadSelections.length; si += 1) {
        var sel = payloadSelections[si];
        var selState = this._selected[sel.path] || {};
        if (sel.type === "folder" && selState.grouping_strategy && selState.grouping_strategy !== "none") {
          try {
            var discoverRequest = {
              folder_path: sel.path,
              grouping_strategy: selState.grouping_strategy,
            };
            if (sel.max_depth != null) {
              discoverRequest.max_depth = sel.max_depth;
            }
            var discoverResponse = await callServiceWithResponse(this._hass, "rest_command", "model_catalog_bulk_discover_working_groups", discoverRequest);
            var proposals = Array.isArray(discoverResponse && discoverResponse.proposals) ? discoverResponse.proposals : [];
            proposals.forEach(function (proposal) {
              (proposal.files || []).forEach(function (fileEntry) {
                if (fileEntry.path) {
                  expandedSelections.push({ type: "file", path: String(fileEntry.path) });
                }
              });
            });
          } catch (_discoverError) {
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
          throw new Error("Set input_text.model_catalog_sidecar_base_url to enable browser uploads.");
        }
        var encodedBrowserFiles = [];
        for (var browserIndex = 0; browserIndex < browserFiles.length; browserIndex += 1) {
          encodedBrowserFiles.push(await this._encodeBrowserFile(browserFiles[browserIndex]));
        }
        response = await postJsonWithAuth(this._hass, sidecarBaseUrl.replace(/\/$/, "") + "/api/intake/uploads/browser", {
          cleanup_policy: this._cleanupPolicy(),
          browser_files: encodedBrowserFiles,
          server_selections: finalSelections,
        });
      } else {
        response = await callServiceWithResponse(this._hass, "rest_command", "model_catalog_select_source_filesystem_entries", {
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
        ? "Browser files and server selections were queued together and validated."
        : (browserFiles.length ? "Browser files were queued to intake and validated." : "Selection queued to intake and validated." + (expandedSelections.length ? " (" + String(expandedSelections.length) + " files expanded from grouped folder(s).)" : ""));
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
    return ""
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
      return ""
        + '<article class="entry-row">'
        + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(entry.name || basename(entry.relative_path)) + '</div><div class="entry-path">' + escapeHtml(entry.relative_path || entry.name || "") + '</div></div><span class="chip">' + escapeHtml(formatBytes(entry.size_bytes || 0)) + '</span></div>'
        + '</article>';
    }).join("") + '</div>';
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
      return ""
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
    }, this).join("") + '</div>';
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
      this._navigateToSection(this._config.inboxSection, '/3d-printing/model-catalog');
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
      + '        <div><div class="title">' + escapeHtml(this._config.title) + '</div><div class="subtitle">Choose one source type for this batch, configure the selection, then queue it into Inbox.</div></div>'
      + '        <div class="button-row"><button class="button" data-action="refresh-intake">Refresh</button><button class="button primary" data-action="goto-inbox">Review Inbox</button></div>'
      + '      </div>'
      + '      ' + (this._error ? '<div class="status error">' + escapeHtml(this._error) + '</div>' : '')
      + '      ' + (this._status ? '<div class="status">' + escapeHtml(this._status) + '</div>' : '')
      + '    </div>'
      + resultHtml
      + this._queueSummaryHtml()
      + '    <section class="section">'
      + '      <div class="grid">'
      + '        <div class="field"><label for="source-mode-select">Step 1: Source For This Batch</label><select id="source-mode-select" class="select" data-action="source-mode"><option value="browser"' + (sourceMode === 'browser' ? ' selected' : '') + '>Browser Upload</option><option value="server"' + (sourceMode === 'server' ? ' selected' : '') + '>Server Browse</option></select></div>'
      + '        <div class="summary-card"><div class="summary-label">Current Batch Rule</div><div class="summary-value">' + escapeHtml(sourceMode === 'browser' ? 'Browser Upload' : 'Server Browse') + '</div><div class="muted">Both source panels remain visible, but only the selected source type contributes to the queued batch.</div></div>'
      + '      </div>'
      + '    </section>'
      + '<section class="section"><div class="title-row"><div><div class="title">Step 2A: Browser Upload</div><div class="subtitle">Pick local files or a local folder from this browser session. These files queue only when Step 1 is set to Browser Upload.</div></div><div class="button-row"><span class="chip' + (sourceMode === 'browser' ? ' ok' : '') + '">' + escapeHtml(sourceMode === 'browser' ? 'Active Source' : 'Inactive For This Batch') + '</span><button class="button" data-action="choose-browser-files">Add Files</button><button class="button" data-action="choose-browser-folder">Add Folder</button><button class="button warn" data-action="clear-browser-files"' + (!this._browserFiles.length ? ' disabled' : '') + '>Clear</button></div></div><input id="browser-file-input" class="hidden-upload-input" type="file" multiple data-action="browser-files"><input id="browser-folder-input" class="hidden-upload-input" type="file" multiple webkitdirectory directory data-action="browser-folder"><div class="muted">Browser-staged files: ' + String(this._browserFiles.length) + (sourceMode === 'browser' ? ' ready for this batch.' : ' are staged but ignored until Browser Upload is selected.') + '</div>' + this._renderBrowserEntries() + '</section>'
      + '    <div class="two-column">'
      + '      <section class="section">'
      + '        <div class="title-row"><div><div class="title">Step 2B: Server Browse</div><div class="subtitle">Select files or folders. Selected folders show Recurse, Max Depth, and Grouping controls inline.</div></div><div class="button-row"><span class="chip' + (sourceMode === 'server' ? ' ok' : '') + '">' + escapeHtml(sourceMode === 'server' ? 'Active Source' : 'Inactive For This Batch') + '</span><button class="button" data-action="browse-root">Roots</button>'
      +          (this._browse.parent_path ? '<button class="button" data-action="browse-parent" data-path="' + escapeHtml(this._browse.parent_path) + '">Up</button>' : '')
      + '        </div></div>'
      + '        <div class="muted">Current path: ' + escapeHtml(this._browse.path || '/') + '</div>'
      + this._renderBrowseEntries()
      + '      </section>'
      + '      <section class="section">'
      + '        <div class="title">Step 3: Queue Into Inbox</div>'
      + '        <div class="field"><label for="cleanup-policy-select">Cleanup Policy For This Batch</label><select id="cleanup-policy-select" class="select" data-action="cleanup-policy"><option value="keep"' + (this._cleanupPolicy() === 'keep' ? ' selected' : '') + '>keep</option><option value="delete_on_verified"' + (this._cleanupPolicy() === 'delete_on_verified' ? ' selected' : '') + '>delete_on_verified</option><option value="replace_with_stub"' + (this._cleanupPolicy() === 'replace_with_stub' ? ' selected' : '') + '>replace_with_stub</option></select></div>'
      + '        <div class="muted">Active source: ' + escapeHtml(sourceMode === 'browser' ? 'Browser Upload' : 'Server Browse') + '. Pending entries for this batch: ' + String(pendingSubmissionCount) + '.</div>'
      + ((serverSelections.length || browserFiles.length)
        ? '<div class="entries">'
          + browserFiles.map(function (entry) {
              return '<article class="entry-row"><div class="entry-name">' + escapeHtml(entry.name || basename(entry.relative_path)) + '</div><div class="entry-path">' + escapeHtml(entry.relative_path || entry.name || '') + '</div><div class="button-row"><span class="chip">browser</span><span class="chip">' + escapeHtml(formatBytes(entry.size_bytes || 0)) + '</span></div></article>';
            }).join('')
          + serverSelections.map(function (entry) {
              return '<article class="entry-row"><div class="entry-name">' + escapeHtml(basename(entry.path) || entry.path) + '</div><div class="entry-path">' + escapeHtml(entry.path) + '</div><div class="button-row"><span class="chip">' + escapeHtml(entry.type) + '</span>' + (entry.type === 'folder' ? '<span class="chip">recurse ' + escapeHtml(entry.recurse ? 'on' : 'off') + '</span>' + (entry.max_depth ? '<span class="chip">max depth ' + escapeHtml(entry.max_depth) + '</span>' : '') : '') + '</div></article>';
            }).join('')
          + '</div>'
        : '<div class="state-row">Select files or folders from the active source type, then queue this batch into Inbox.</div>')
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

if (!customElements.get('model-catalog-intake-home-card')) {
  customElements.define('model-catalog-intake-home-card', ModelCatalogIntakeHomeCard);
}
