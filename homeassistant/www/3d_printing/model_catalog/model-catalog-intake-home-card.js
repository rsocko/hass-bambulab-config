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
var fireModelCatalogDataChanged = intakeShared.fireModelCatalogDataChanged;
var selectInputOption = intakeShared.selectInputOption;
var postJsonWithAuth = intakeShared.postJsonWithAuth;
var setHelperValue = intakeShared.setHelperValue;
var sharedStyles = intakeShared.sharedStyles;

function pathStem(path) {
  var name = basename(path || '');
  if (!name) {
    return '';
  }
  var dotIndex = name.lastIndexOf('.');
  return dotIndex > 0 ? name.slice(0, dotIndex) : name;
}

class ModelCatalogIntakeHomeCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._boundHandleClick = this._handleClick.bind(this);
    this._boundHandleChange = this._handleChange.bind(this);
    this._boundHandleInput = this._handleInput.bind(this);
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
    this._wizardOpen = false;
    this._wizardMode = "";
    this._wizardStep = 1;
    this._cleanupPolicyValue = null;
    this._commitMode = "queue"; // "queue" or "execute_now"
    this._destinationChoice = "curated"; // "curated" or "working"
    this._previewData = null;
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
      this.shadowRoot.addEventListener("change", this._boundHandleChange);
      this.shadowRoot.addEventListener("input", this._boundHandleInput);
    }
  }

  disconnectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.removeEventListener("click", this._boundHandleClick);
      this.shadowRoot.removeEventListener("change", this._boundHandleChange);
      this.shadowRoot.removeEventListener("input", this._boundHandleInput);
    }
  }

  getCardSize() {
    return 12;
  }

  _sourceMode() {
    var value = this._hass && this._hass.states[this._config.sourceModeEntity]
      ? String(this._hass.states[this._config.sourceModeEntity].state || "browser")
      : "browser";
    return value === "server" ? "server" : "browser";
  }

  _normalizeCleanupPolicy(value) {
    var normalized = String(value || "keep").trim().toLowerCase();
    if (normalized === "delete_on_verified" || normalized === "replace_with_stub") {
      return normalized;
    }
    return "keep";
  }

  _helperCleanupPolicy() {
    return this._hass && this._hass.states[this._config.cleanupPolicyEntity]
      ? this._normalizeCleanupPolicy(this._hass.states[this._config.cleanupPolicyEntity].state)
      : "keep";
  }

  _defaultCleanupPolicy(mode) {
    return mode === "browser" ? "delete_on_verified" : "keep";
  }

  _cleanupPolicy() {
    if (this._cleanupPolicyValue) {
      return this._cleanupPolicyValue;
    }
    return this._helperCleanupPolicy();
  }

  _wizardStepCount() {
    return 3;
  }

  _wizardStepLabel(stepNumber) {
    if (stepNumber === 1) {
      return this._wizardMode === "server" ? "Select" : "Choose";
    }
    if (stepNumber === 2) {
      return "Preview";
    }
    return "Commit";
  }

  _wizardTitle() {
    return this._wizardMode === "server"
      ? "Import From Server Inbox"
      : "Upload Files Or Folder";
  }

  _browserFileKey(entry) {
    return String(entry.relative_path || entry.name || "").toLowerCase() + "::" + String(entry.size_bytes || 0);
  }

  _selectedList() {
    return Object.keys(this._selected).map(function (key) { return this._selected[key]; }, this);
  }

  _fileSelectionEntries() {
    return this._selectedList().filter(function (entry) {
      return entry && entry.type === 'file';
    });
  }

  _fileBatchTitleSource() {
    var fileEntries = this._fileSelectionEntries();
    if (!fileEntries.length) {
      return 'first-file';
    }
    return this._selectionTitleSource(fileEntries[0]);
  }

  _fileBatchResolvedTitle() {
    var fileEntries = this._fileSelectionEntries();
    if (!fileEntries.length) {
      return 'Working Group';
    }
    return this._resolvedGroupTitle(fileEntries[0]);
  }

  _updateSelectedFileBatchMeta(updates) {
    var nextSelected = Object.assign({}, this._selected);
    Object.keys(nextSelected).forEach(function (key) {
      var entry = nextSelected[key];
      if (!entry || entry.type !== 'file') {
        return;
      }
      nextSelected[key] = Object.assign({}, entry, updates);
    });
    this._selected = nextSelected;
  }

  _browserTopLevelFolders() {
    var folderMap = {};
    this._browserFiles.forEach(function (entry) {
      var relativePath = String(entry.relative_path || entry.name || '').replace(/\\/g, '/');
      var pathParts = relativePath.split('/').filter(function (part) { return !!part; });
      if (pathParts.length > 1) {
        folderMap[pathParts[0]] = true;
      }
    });
    return Object.keys(folderMap);
  }

  _browserHasFolderUpload() {
    return this._browserTopLevelFolders().length > 0;
  }

  _browserGroupingStrategy() {
    if (!this._browserFiles.length) {
      return 'none';
    }
    var normalized = String(this._browserFiles[0] && this._browserFiles[0].grouping_strategy || '').trim().toLowerCase();
    if (normalized === 'by-folder' || normalized === 'by-root' || normalized === 'flat') {
      return normalized;
    }
    return 'none';
  }

  _browserBatchTitleSource() {
    if (!this._browserFiles.length) {
      return 'first-file';
    }
    var firstEntry = this._browserFiles[0];
    var normalized = String(firstEntry && firstEntry.group_title_source || '').trim().toLowerCase();
    if (normalized === 'folder' || normalized === 'first-file' || normalized === 'custom') {
      return normalized;
    }
    return this._browserTopLevelFolders().length === 1 ? 'folder' : 'first-file';
  }

  _defaultBrowserBatchTitle() {
    if (!this._browserFiles.length) {
      return 'Working Group';
    }
    if (this._browserGroupingStrategy() === 'flat') {
      var flatFirstEntry = this._browserFiles[0];
      return pathStem(flatFirstEntry && (flatFirstEntry.relative_path || flatFirstEntry.name) || '') || basename(flatFirstEntry && (flatFirstEntry.relative_path || flatFirstEntry.name) || '') || 'Working Group';
    }
    var titleSource = this._browserBatchTitleSource();
    var topFolders = this._browserTopLevelFolders();
    if (titleSource === 'custom') {
      return String(this._browserFiles[0] && this._browserFiles[0].group_title || '').trim() || 'Working Group';
    }
    if (titleSource === 'folder' && topFolders.length === 1) {
      return topFolders[0];
    }
    var firstEntry = this._browserFiles[0];
    return pathStem(firstEntry && (firstEntry.relative_path || firstEntry.name) || '') || basename(firstEntry && (firstEntry.relative_path || firstEntry.name) || '') || 'Working Group';
  }

  _browserBatchResolvedTitle() {
    if (!this._browserFiles.length) {
      return 'Working Group';
    }
    var explicitTitle = String(this._browserFiles[0] && this._browserFiles[0].group_title || '').trim();
    if (explicitTitle) {
      return explicitTitle;
    }
    return this._defaultBrowserBatchTitle();
  }

  _updateBrowserBatchMeta(updates) {
    this._browserFiles = this._browserFiles.map(function (entry) {
      return Object.assign({}, entry, updates);
    });
  }

  _browserGroupingTitleSource(groupingStrategy) {
    return groupingStrategy === 'flat' ? 'first-file' : 'folder';
  }

  _selectionTitleSource(entry) {
    var normalized = String(entry && entry.group_title_source || '').trim().toLowerCase();
    if (normalized === 'folder' || normalized === 'first-file' || normalized === 'custom') {
      return normalized;
    }
    if (entry && entry.grouping_strategy === 'flat') {
      return 'first-file';
    }
    return 'folder';
  }

  _defaultGroupTitle(entry, proposals) {
    var titleSource = this._selectionTitleSource(entry);
    if (titleSource === 'custom') {
      return String(entry && entry.group_title || '').trim() || basename(entry && entry.path || '') || 'Working Group';
    }
    if (titleSource === 'first-file') {
      if (Array.isArray(proposals) && proposals.length) {
        var firstProposal = proposals[0] || {};
        if (firstProposal.title) {
          return String(firstProposal.title).trim();
        }
        var firstFile = Array.isArray(firstProposal.files) && firstProposal.files.length ? firstProposal.files[0] : null;
        if (firstFile && firstFile.filename) {
          return pathStem(firstFile.filename) || String(firstFile.filename);
        }
      }
      return pathStem(entry && entry.path || '') || basename(entry && entry.path || '') || 'Working Group';
    }
    return basename(entry && entry.path || '') || 'Working Group';
  }

  _resolvedGroupTitle(entry, proposals) {
    var explicitTitle = String(entry && entry.group_title || '').trim();
    if (explicitTitle) {
      return explicitTitle;
    }
    return this._defaultGroupTitle(entry, proposals);
  }

  _serverPayloadSelections(sourceMode) {
    if (sourceMode !== "server") {
      return [];
    }
    return this._selectedList().map(function (entry) {
      var next = { type: entry.type, path: entry.path };
      if (entry.group_title_source) {
        next.group_title_source = this._selectionTitleSource(entry);
      }
      if (entry.group_title || entry.group_title_source) {
        next.group_title = this._resolvedGroupTitle(entry);
      }
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

  async _openWizard(mode) {
    var nextMode = mode === "server" ? "server" : "browser";
    this._wizardOpen = true;
    this._wizardMode = nextMode;
    this._wizardStep = 1;
    this._cleanupPolicyValue = this._defaultCleanupPolicy(nextMode);
    this._commitMode = 'queue';
    this._destinationChoice = 'curated';
    this._error = "";
    this._status = "";
    this._result = null;
    this._selected = {};
    this._browserFiles = [];
    await this._setSourceMode(nextMode);
    if (nextMode === "server") {
      await this._loadBrowse('/');
      return;
    }
    this._render();
  }

  _closeWizard() {
    this._wizardOpen = false;
    this._wizardMode = "";
    this._wizardStep = 1;
    this._cleanupPolicyValue = null;
    this._commitMode = 'queue';
    this._destinationChoice = 'curated';
    this._selected = {};
    this._browserFiles = [];
    this._render();
  }

  _canAdvanceWizard() {
    if (this._wizardMode === "server") {
      return this._selectedList().length > 0;
    }
    return this._browserFiles.length > 0;
  }

  _goToWizardStep(stepNumber) {
    var maxStep = this._wizardStepCount();
    var nextStep = Math.max(1, Math.min(maxStep, Number(stepNumber || 1)));
    if (nextStep > this._wizardStep && !this._canAdvanceWizard()) {
      this._error = this._wizardMode === "server"
        ? "Select at least one server file or folder first."
        : "Choose at least one browser file or folder first.";
      this._render();
      return;
    }
    this._error = "";
    this._wizardStep = nextStep;
    this._render();
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
        group_title_source: entryType === 'folder' ? 'folder' : this._fileBatchTitleSource(),
        group_title: '',
      };
    }
    this._selected = nextSelected;
    this._render();
  }

  _removeSelection(path) {
    var nextSelected = Object.assign({}, this._selected);
    delete nextSelected[path];
    this._selected = nextSelected;
    this._render();
  }

  _appendBrowserFiles(fileList) {
    var currentBrowserTitleSource = this._browserBatchTitleSource();
    var currentBrowserTitle = this._browserBatchResolvedTitle();
    var nextByKey = {};
    this._browserFiles.forEach(function (entry) {
      nextByKey[this._browserFileKey(entry)] = entry;
    }, this);
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
        grouping_strategy: this._browserHasFolderUpload() ? this._browserGroupingStrategy() : 'none',
        group_title_source: currentBrowserTitleSource,
        group_title: currentBrowserTitleSource === 'custom' ? currentBrowserTitle : '',
      };
      nextByKey[this._browserFileKey(nextEntry)] = nextEntry;
    }, this);
    this._browserFiles = Object.keys(nextByKey).map(function (key) { return nextByKey[key]; }).sort(function (left, right) {
      return String(left.relative_path || left.name).localeCompare(String(right.relative_path || right.name));
    });
    this._render();
  }

  _removeBrowserFile(key) {
    this._browserFiles = this._browserFiles.filter(function (entry) {
      return this._browserFileKey(entry) !== key;
    }, this);
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
      group_title_source: fileEntry.group_title_source,
      group_title: fileEntry.group_title,
    };
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

  async _submitServerSelections() {
    if (!this._hass) {
      return;
    }
    var sourceMode = this._sourceMode();
    var cleanupPolicy = this._cleanupPolicy();
    var payloadSelections = this._serverPayloadSelections(sourceMode);
    var browserFiles = this._enabledBrowserFiles(sourceMode);
    if (!payloadSelections.length && !browserFiles.length) {
      this._error = sourceMode === "server"
        ? "Select at least one server file or folder first."
        : "Select at least one browser file or folder first.";
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
                  expandedSelections.push({
                    type: "file",
                    path: String(fileEntry.path),
                    group_title_source: this._selectionTitleSource(selState),
                    group_title: this._resolvedGroupTitle(selState, proposals),
                  });
                }
              }, this);
            }, this);
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
          browser_files: encodedBrowserFiles,
          server_selections: finalSelections,
        });
      } else {
        response = await callServiceWithResponse(this._hass, "rest_command", "model_catalog_select_source_filesystem_entries", {
          selections: finalSelections,
          cleanup_policy: cleanupPolicy,
        });
      }
      var validation = await callServiceWithResponse(this._hass, "rest_command", "model_catalog_validate_intake_item", {
        item_id: response.upload_id,
      });
      var validationState = validation.validation ? validation.validation.validation_state : "unknown";
      var publishResponse = null;
      var publishDestination = null;
      if (this._commitMode === 'execute_now' && validationState === 'ready') {
        publishDestination = this._destinationChoice || 'curated';
        var publishService = publishDestination === 'working' ? 'model_catalog_publish_to_working' : 'model_catalog_publish_to_local';
        publishResponse = await callServiceWithResponse(this._hass, 'rest_command', publishService, {
          upload_id: response.upload_id,
        });
      }
      this._result = {
        upload_id: response.upload_id,
        upload_status: publishResponse && publishResponse.status ? publishResponse.status : response.status,
        selection_count: finalSelections.length + browserFiles.length,
        expanded_file_count: response.expanded_file_count != null ? response.expanded_file_count : response.source_entry_count,
        validation_state: validationState,
        warnings: (response.warnings || []).concat(validation.validation ? validation.validation.warnings || [] : []),
        cleanup_policy: response.cleanup_policy || cleanupPolicy,
        publish_status: publishResponse && publishResponse.status ? publishResponse.status : null,
        local_model_id: publishResponse && publishResponse.local_model_id ? publishResponse.local_model_id : null,
        working_group_id: publishResponse && publishResponse.working_group_id ? publishResponse.working_group_id : null,
      };
      if (this._commitMode === 'execute_now') {
        if (publishResponse) {
          var destinationText = publishDestination === 'working' ? 'working files' : 'the curated catalog';
          this._status = browserFiles.length
            ? "Browser batch validated and published to " + destinationText + "."
            : "Server selection validated and published to " + destinationText + "." + (expandedSelections.length ? " (" + String(expandedSelections.length) + " files expanded from grouped folder selections.)" : "");
          var fireEvent = publishDestination === 'working' ? 'working' : 'curated';
          fireModelCatalogDataChanged([fireEvent], {
            reason: 'execute-now-publish',
            uploadId: response.upload_id,
            localModelId: publishResponse.local_model_id || null,
            workingGroupId: publishResponse.working_group_id || null,
          });
        } else {
          this._status = "Validation produced warnings, so the batch remains in Inbox for review.";
        }
      } else {
        this._status = browserFiles.length
          ? "Browser batch queued to intake and validated."
          : "Server selection queued to intake and validated." + (expandedSelections.length ? " (" + String(expandedSelections.length) + " files expanded from grouped folder selections.)" : "");
      }
      this._selected = {};
      this._browserFiles = [];
      this._wizardOpen = false;
      this._wizardMode = "";
      this._wizardStep = 1;
      this._cleanupPolicyValue = null;
      this._commitMode = 'queue';
      this._destinationChoice = 'curated';
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
    var nextValue = this._normalizeCleanupPolicy(value);
    this._cleanupPolicyValue = nextValue;
    this._render();
    if (!this._hass) {
      return;
    }
    try {
      await setHelperValue(this._hass, "input_select", this._config.cleanupPolicyEntity, nextValue);
    } catch (error) {
      this._cleanupPolicyValue = this._helperCleanupPolicy();
      this._error = error && error.message ? String(error.message) : "Could not update cleanup policy.";
      this._render();
    }
  }

  _queueSummaryHtml() {
    var uploadCounts = summarizeStates(this._queueUploads, "status");
    var itemCounts = summarizeStates(this._intakeItems, "state");
    return ""
      + '<div class="grid">'
      + '  <div class="summary-card"><div class="summary-label">Queue Health</div><div class="summary-value">Queued ' + String(uploadCounts.queued || 0) + ' / Verified ' + String(uploadCounts.verified || 0) + '</div><div class="muted">Failed ' + String(uploadCounts.failed || 0) + ' / Cleanup pending ' + String(uploadCounts.cleanup_pending || 0) + '</div></div>'
      + '  <div class="summary-card"><div class="summary-label">Inbox Snapshot</div><div class="summary-value">Ready ' + String(itemCounts.validated_ready || 0) + ' / Warning ' + String(itemCounts.validated_warning || 0) + '</div><div class="muted">Deferred ' + String(itemCounts.deferred || 0) + ' / Grouped ' + String((itemCounts.grouped_new || 0) + (itemCounts.grouped_existing || 0)) + '</div></div>'
      + '  <div class="summary-card"><div class="summary-label">Intake Roots</div><div class="summary-value">' + String(this._roots.length) + ' configured</div><div class="muted">Server browse is constrained to allowlisted sidecar roots.</div></div>'
      + '  <div class="summary-card"><div class="summary-label">Batch Policy</div><div class="summary-value">' + escapeHtml(this._cleanupPolicy()) + '</div><div class="muted">Applied when the wizard commits a new intake batch.</div></div>'
      + '</div>';
  }

  _renderBrowserFileRows(showActions) {
    if (!this._browserFiles.length) {
      return '<div class="state-row">No browser files staged yet. Add files or a folder to begin.</div>';
    }
    return '<div class="entries">' + this._browserFiles.map(function (entry) {
      var relativePath = String(entry.relative_path || entry.name || "").replace(/\\/g, '/');
      var pathParts = relativePath.split('/').filter(function (part) { return !!part; });
      var displayName = basename(relativePath || entry.name || "") || entry.name || relativePath || "upload.bin";
      var folderPath = pathParts.length > 1 ? pathParts.slice(0, -1).join('/') : '';
      return ''
        + '<article class="entry-row">'
        + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(displayName) + '</div><div class="entry-path">' + escapeHtml(relativePath || entry.name || "") + '</div>' + (folderPath ? '<div class="muted">Folder: ' + escapeHtml(folderPath) + '</div>' : '') + '</div><div class="button-row"><span class="chip">browser</span>' + (folderPath ? '<span class="chip">folder upload</span>' : '<span class="chip">single file</span>') + '<span class="chip">' + escapeHtml(formatBytes(entry.size_bytes || 0)) + '</span>'
        + (showActions ? '<button class="button warn" data-action="remove-browser-file" data-key="' + escapeHtml(this._browserFileKey(entry)) + '">Remove</button>' : '')
        + '  </div></div>'
        + '</article>';
    }, this).join('') + '</div>';
  }

  _renderBrowserSelectionSummary() {
    var topFolders = this._browserTopLevelFolders();
    var folderCount = topFolders.length;
    var groupingStrategy = this._browserGroupingStrategy();
    var titleSource = this._browserBatchTitleSource();
    var resolvedTitle = this._browserBatchResolvedTitle();
    return ''
      + '<div class="result-summary">'
      + '  <div class="result-line"><span>Source path</span><strong>Browser Upload</strong></div>'
      + '  <div class="result-line"><span>Cleanup policy</span><strong>delete_on_verified (automatic)</strong></div>'
      + '  <div class="result-line"><span>Staged files</span><strong>' + String(this._browserFiles.length) + '</strong></div>'
      + '  <div class="result-line"><span>Staged folders</span><strong>' + String(folderCount) + '</strong></div>'
      + (folderCount
        ? '  <div class="result-line"><span>Grouping</span><strong>' + escapeHtml(groupingStrategy) + '</strong></div>'
        : '')
      + (this._browserFiles.length
        ? '  <div class="item-grid">'
          + (folderCount
            ? '    <div class="field"><label>Grouping</label><select class="select" data-action="browser-grouping"><option value="none"' + (groupingStrategy === 'none' ? ' selected' : '') + '>None</option><option value="by-folder"' + (groupingStrategy === 'by-folder' ? ' selected' : '') + '>by-folder</option><option value="by-root"' + (groupingStrategy === 'by-root' ? ' selected' : '') + '>by-root</option><option value="flat"' + (groupingStrategy === 'flat' ? ' selected' : '') + '>flat</option></select></div>'
            : '')
          + '    <div class="field"><label>Title Basis</label><select class="select" data-action="browser-title-source"><option value="folder"' + (titleSource === 'folder' ? ' selected' : '') + '>Folder name</option><option value="first-file"' + (titleSource === 'first-file' ? ' selected' : '') + '>First file</option><option value="custom"' + (titleSource === 'custom' ? ' selected' : '') + '>Custom</option></select></div>'
          + '    <div class="field"><label>Working Group Title</label><input class="input" type="text" value="' + escapeHtml(resolvedTitle) + '" data-action="browser-group-title" placeholder="Working Group"></div>'
          + '  </div><div class="muted">This title is carried into Inbox for browser-uploaded files and folders.' + (folderCount ? ' Folder uploads now expose the same grouping control as the server picker.' : '') + '</div>'
        : '')
      + '</div>';
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
      return ''
        + '<article class="entry-row' + (selected ? ' selected' : '') + '">'
        + '  <div class="entry-top">'
        + '    <div>'
        + '      <div class="entry-name">' + escapeHtml(entry.name || basename(entry.path)) + '</div>'
        + '      <div class="entry-path">' + escapeHtml(entry.path || '') + '</div>'
        + '    </div>'
        + '    <div class="button-row">'
        + (entry.type === 'folder' ? '<span class="chip">Folder</span>' : '<span class="chip">File</span>')
        + (entry.type === 'file' && entry.size_bytes != null ? '<span class="chip">' + escapeHtml(formatBytes(entry.size_bytes)) + '</span>' : '')
        + '    </div>'
        + '  </div>'
        + '  <div class="entry-actions">'
        + (entry.type === 'folder' ? '<button class="button" data-action="browse-path" data-path="' + escapeHtml(entry.path) + '">Open</button>' : '')
        + '    <button class="button ' + (selected ? 'warn' : 'primary') + '" data-action="toggle-selection" data-entry-type="' + escapeHtml(entry.type) + '" data-path="' + escapeHtml(entry.path) + '">' + (selected ? 'Remove' : 'Select') + '</button>'
        + '  </div>'
        + '</article>';
    }, this).join('') + '</div>';
  }

  _renderServerSelectionRows(showSettings) {
    var selections = this._selectedList();
    var fileEntries = this._fileSelectionEntries();
    var fileBatchTitleSource = this._fileBatchTitleSource();
    var fileBatchResolvedTitle = this._fileBatchResolvedTitle();
    if (!selections.length) {
      return '<div class="state-row">No server files or folders selected yet.</div>';
    }
    return '<div class="entries">'
      + ((showSettings && fileEntries.length)
        ? '<article class="entry-row">'
          + '<div class="entry-top"><div><div class="entry-name">Selected Files Batch</div><div class="entry-path">Applies to all individually selected files in this queue batch.</div></div><div class="button-row"><span class="chip">' + String(fileEntries.length) + ' files</span></div></div>'
          + '<div class="item-grid">'
          + '<div class="field"><label>Title Basis</label><select class="select" data-action="selection-title-source-files"><option value="first-file"' + (fileBatchTitleSource === 'first-file' ? ' selected' : '') + '>First file</option><option value="custom"' + (fileBatchTitleSource === 'custom' ? ' selected' : '') + '>Custom</option></select></div>'
          + '<div class="field"><label>Working Group Title</label><input class="input" type="text" value="' + escapeHtml(fileBatchResolvedTitle) + '" data-action="selection-group-title-files" placeholder="Working Group"></div>'
          + '<div class="muted">This title is copied to the queued file entries and becomes the default group title in Inbox.</div>'
          + '</div>'
          + '</article>'
        : '')
      + selections.map(function (entry) {
      var titleSource = this._selectionTitleSource(entry);
      var resolvedTitle = this._resolvedGroupTitle(entry);
      return ''
        + '<article class="entry-row">'
        + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(basename(entry.path) || entry.path) + '</div><div class="entry-path">' + escapeHtml(entry.path) + '</div></div><div class="button-row"><span class="chip">' + escapeHtml(entry.type) + '</span><button class="button warn" data-action="remove-selection" data-path="' + escapeHtml(entry.path) + '">Remove</button></div></div>'
        + (entry.type === 'folder' && showSettings
          ? '<div class="item-grid">'
            + '<div class="field"><label>Recurse</label><select class="select" data-action="selection-recurse" data-path="' + escapeHtml(entry.path) + '"><option value="true"' + (entry.recurse ? ' selected' : '') + '>On</option><option value="false"' + (!entry.recurse ? ' selected' : '') + '>Off</option></select></div>'
            + '<div class="field"><label>Max Depth</label><input class="input" type="number" min="1" placeholder="Optional" value="' + escapeHtml(entry.max_depth) + '" data-action="selection-depth" data-path="' + escapeHtml(entry.path) + '"></div>'
            + '<div class="field"><label>Grouping</label><select class="select" data-action="selection-grouping" data-path="' + escapeHtml(entry.path) + '"><option value="none"' + (entry.grouping_strategy === 'none' ? ' selected' : '') + '>None</option><option value="by-folder"' + (entry.grouping_strategy === 'by-folder' ? ' selected' : '') + '>by-folder</option><option value="by-root"' + (entry.grouping_strategy === 'by-root' ? ' selected' : '') + '>by-root</option><option value="flat"' + (entry.grouping_strategy === 'flat' ? ' selected' : '') + '>flat</option></select></div>'
            + '<div class="field"><label>Title Basis</label><select class="select" data-action="selection-title-source" data-path="' + escapeHtml(entry.path) + '"><option value="folder"' + (titleSource === 'folder' ? ' selected' : '') + '>Folder name</option><option value="first-file"' + (titleSource === 'first-file' ? ' selected' : '') + '>First file</option><option value="custom"' + (titleSource === 'custom' ? ' selected' : '') + '>Custom</option></select></div>'
            + '<div class="field"><label>Working Group Title</label><input class="input" type="text" value="' + escapeHtml(resolvedTitle) + '" data-action="selection-group-title" data-path="' + escapeHtml(entry.path) + '" placeholder="Working Group"></div>'
            + '<div class="muted">This title is preserved into Inbox and becomes the default when this batch is sent to Working Files.</div>'
            + '</div>'
          : (entry.type === 'folder'
            ? '<div class="button-row"><span class="chip">recurse ' + escapeHtml(entry.recurse ? 'on' : 'off') + '</span>' + (entry.max_depth ? '<span class="chip">max depth ' + escapeHtml(entry.max_depth) + '</span>' : '') + '<span class="chip">' + escapeHtml(entry.grouping_strategy || 'none') + '</span><span class="chip">title ' + escapeHtml(resolvedTitle) + '</span></div>'
            : '<div class="button-row"><span class="chip">title ' + escapeHtml(resolvedTitle) + '</span></div>'))
        + '</article>';
    }, this).join('') + '</div>';
  }

  _renderLaunchPad() {
    var rootNames = this._roots.map(function (root) {
      return basename(root.path || root.name || '/');
    }).filter(Boolean).slice(0, 3);
    return ''
      + '<section class="section">'
      + '  <div class="title-row"><div><div class="title">New Intake Batch</div><div class="subtitle">Start one path at a time, review the batch, then commit it into Inbox.</div></div><div class="button-row"><button class="button" data-action="refresh-intake">Refresh</button><button class="button primary" data-action="goto-inbox">Review Inbox</button></div></div>'
      + '  <div class="wizard-launch-grid">'
      + '    <article class="launch-card">'
      + '      <div class="launch-kicker">Path 1</div><div class="launch-title">Upload Files / Folder</div><div class="muted">Use the current browser session to add local files or a local folder, keep building the staged list, then review before commit.</div><div class="button-row"><button class="button primary" data-action="open-browser-wizard">Start Upload Wizard</button></div>'
      + '    </article>'
      + '    <article class="launch-card">'
      + '      <div class="launch-kicker">Path 2</div><div class="launch-title">Sync / Import From Server Inbox</div><div class="muted">Browse allowlisted server roots' + (rootNames.length ? ' such as ' + escapeHtml(rootNames.join(', ')) : '') + ', select files or folders, configure recurse/grouping, then review before commit.</div><div class="button-row"><button class="button primary" data-action="open-server-wizard">Start Server Wizard</button></div>'
      + '    </article>'
      + '  </div>'
      + '</section>';
  }

  _renderRecentActivity() {
    var recentItems = this._intakeItems.slice(0, 5);
    return ''
      + '<section class="section">'
      + '  <div class="title-row"><div><div class="title">Recent Intake Activity</div><div class="subtitle">Latest queue handoffs and validation state from the shared Inbox contract.</div></div></div>'
      + (recentItems.length
        ? '<div class="entries">' + recentItems.map(function (item) {
            var sourceEntry = item.source_entry || {};
            return '<article class="entry-row"><div class="entry-top"><div><div class="entry-name">' + escapeHtml(basename(sourceEntry.path || item.item_id)) + '</div><div class="entry-path">' + escapeHtml(sourceEntry.path || item.item_id) + '</div></div><span class="chip">' + escapeHtml(formatLabel(item.state || item.status)) + '</span></div></article>';
          }).join('') + '</div>'
        : '<div class="state-row">No intake items have been created yet.</div>')
      + '</section>';
  }

  _renderWizardProgress() {
    var steps = [];
    for (var stepNumber = 1; stepNumber <= this._wizardStepCount(); stepNumber += 1) {
      steps.push(''
        + '<div class="wizard-step' + (stepNumber === this._wizardStep ? ' current' : '') + (stepNumber < this._wizardStep ? ' complete' : '') + '">'
        + '  <div class="wizard-step-number">' + String(stepNumber) + '</div>'
        + '  <div class="wizard-step-label">' + escapeHtml(this._wizardStepLabel(stepNumber)) + '</div>'
        + '</div>');
    }
    return '<div class="wizard-progress">' + steps.join('') + '</div>';
  }

  _renderWizardBody() {
    if (this._wizardMode === 'server') {
      if (this._wizardStep === 1) {
        return ''
          + '<div class="wizard-panel">'
          + '  <div class="title-row"><div><div class="title">Select Server Files Or Folders</div><div class="subtitle">Browse the allowlisted server directory and build the selection list for this batch.</div></div><div class="button-row"><button class="button" data-action="browse-root">Roots</button>'
          + (this._browse.parent_path ? '<button class="button" data-action="browse-parent" data-path="' + escapeHtml(this._browse.parent_path) + '">Up</button>' : '')
          + '  </div></div>'
          + '  <div class="muted">Current path: ' + escapeHtml(this._browse.path || '/') + '.</div>'
          + '  <div class="wizard-scroll-region">' + this._renderBrowseEntries() + '</div>'
          + '</div>'
          + '<div class="wizard-panel">'
          + '  <div class="title-row"><div><div class="title">Current Selection</div><div class="subtitle">Configure recurse, depth, and grouping per folder, then advance to review.</div></div><span class="chip ok">' + String(this._selectedList().length) + ' selected</span></div>'
          + '  <div class="field"><label for="cleanup-policy-select">Cleanup Policy For This Batch</label><select id="cleanup-policy-select" class="select" data-action="cleanup-policy"><option value="keep"' + (this._cleanupPolicy() === 'keep' ? ' selected' : '') + '>keep</option><option value="delete_on_verified"' + (this._cleanupPolicy() === 'delete_on_verified' ? ' selected' : '') + '>delete_on_verified</option><option value="replace_with_stub"' + (this._cleanupPolicy() === 'replace_with_stub' ? ' selected' : '') + '>replace_with_stub</option></select></div>'
          + '  <div class="wizard-selection-scroll">' + this._renderServerSelectionRows(true) + '</div>'
          + '</div>';
      }
      if (this._wizardStep === 2) {
        return ''
          + '<div class="wizard-panel">'
          + '  <div class="title-row"><div><div class="title">Preview And Group Defaults</div><div class="subtitle">Review the queued entries and edit the default Working Group title before committing to Inbox.</div></div></div>'
          + '  <div class="result-summary"><div class="result-line"><span>Selected entries</span><strong>' + String(this._selectedList().length) + '</strong></div><div class="result-line"><span>Estimated files</span><strong>' + String(this._selectedList().length) + ' or more</strong></div></div>'
          + '  <div class="muted">Folder imports keep the title basis and custom title you set here. You can still override the title later from Inbox.</div>'
          + '  <div class="wizard-selection-scroll">' + this._renderServerSelectionRows(true) + '</div>'
          + '</div>';
      }
      return ''
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Choose Commit Mode & Destination</div><div class="subtitle">Select how you want to proceed with these files.</div></div></div>'
        + '  <div class="field"><label><input type="radio" name="commit-mode" value="queue"' + (this._commitMode === 'queue' ? ' checked' : '') + ' data-action="set-commit-mode"> <strong>Queue for Review</strong> - Safe path for careful validation</label></div>'
        + '  <div class="field"><label><input type="radio" name="commit-mode" value="execute_now"' + (this._commitMode === 'execute_now' ? ' checked' : '') + ' data-action="set-commit-mode"> <strong>Execute Now</strong> - Validate and publish directly (power users)</label></div>'
        + (this._commitMode === 'execute_now'
          ? '  <div class="field"><label for="destination-select">Publication Destination</label><select id="destination-select" class="select" data-action="set-destination"><option value="curated"' + (this._destinationChoice === 'curated' ? ' selected' : '') + '>Curated Catalog</option><option value="working"' + (this._destinationChoice === 'working' ? ' selected' : '') + '>Working Files</option></select><div class="muted">Choose where to publish: Curated Catalog is the authoritative library, Working Files are for drafts and projects.</div></div>'
          : '')
        + '  <div class="muted">Queue mode: Items go to Active Queue for verification and grouping review. Execute Now: Skips queue, goes straight to publication if validation passes.</div>'
        + '</div>';
    }

    if (this._wizardStep === 1) {
      return ''
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Choose Local Files Or Folder</div><div class="subtitle">Add files or folders from this device. You can repeat the action and build a staged list before moving on.</div></div><div class="button-row"><button class="button" data-action="choose-browser-files">Add Files</button><button class="button" data-action="choose-browser-folder">Add Folder</button><button class="button warn" data-action="clear-browser-files"' + (!this._browserFiles.length ? ' disabled' : '') + '>Clear All</button></div></div>'
        + this._renderBrowserSelectionSummary()
        + '  <div class="wizard-selection-scroll">' + this._renderBrowserFileRows(true) + '</div>'
        + '</div>';
    }
    if (this._wizardStep === 2) {
      return ''
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Preview Browser Uploads</div><div class="subtitle">Review the staged files and folders before choosing how to commit this batch.</div></div><span class="chip ok">' + String(this._browserFiles.length) + ' pending</span></div>'
        + this._renderBrowserSelectionSummary()
        + '  <div class="muted">Folder uploads can use the same grouping selector as the server picker. Files still upload from this browser session and can be reviewed after queueing.</div>'
        + '  <div class="wizard-review-scroll">' + this._renderBrowserFileRows(false) + '</div>'
        + '</div>';
    }
    return ''
      + '<div class="wizard-panel">'
      + '  <div class="title-row"><div><div class="title">Choose Commit Mode & Destination</div><div class="subtitle">Select how you want to proceed with these files.</div></div></div>'
      + '  <div class="field"><label><input type="radio" name="commit-mode" value="queue"' + (this._commitMode === 'queue' ? ' checked' : '') + ' data-action="set-commit-mode"> <strong>Queue for Review</strong> - Safe path for careful validation</label></div>'
      + '  <div class="field"><label><input type="radio" name="commit-mode" value="execute_now"' + (this._commitMode === 'execute_now' ? ' checked' : '') + ' data-action="set-commit-mode"> <strong>Execute Now</strong> - Validate and publish directly (power users)</label></div>'
      + (this._commitMode === 'execute_now'
        ? '  <div class="field"><label for="destination-select">Publication Destination</label><select id="destination-select" class="select" data-action="set-destination"><option value="curated"' + (this._destinationChoice === 'curated' ? ' selected' : '') + '>Curated Catalog</option><option value="working"' + (this._destinationChoice === 'working' ? ' selected' : '') + '>Working Files</option></select><div class="muted">Choose where to publish: Curated Catalog is the authoritative library, Working Files are for drafts and projects.</div></div>'
        : '')
      + '  <div class="muted">Queue mode: Items go to Active Queue for verification and grouping review. Execute Now: Skips queue, goes straight to publication if validation passes.</div>'
      + this._renderBrowserSelectionSummary()
      + '</div>';
  }

  _renderWizardFooter() {
    var atFirstStep = this._wizardStep === 1;
    var atLastStep = this._wizardStep === this._wizardStepCount();
    var commitButtonLabel = "Commit To Inbox";
    if (atLastStep && this._commitMode === 'execute_now') {
      var destination = this._destinationChoice === 'working' ? 'Working Files' : 'Catalog';
      commitButtonLabel = "Validate & Publish to " + destination;
    }
    return ''
      + '<div class="wizard-footer">'
      + '  <div class="button-row"><button class="button" data-action="close-wizard">Cancel</button>'
      + (!atFirstStep ? '<button class="button" data-action="wizard-back">Back</button>' : '')
      + '  </div>'
      + '  <div class="button-row">'
      + (!atLastStep
        ? '<button class="button primary" data-action="wizard-next"' + (!this._canAdvanceWizard() ? ' disabled' : '') + '>Next</button>'
        : '<button class="button primary" data-action="commit-wizard"' + (!this._canAdvanceWizard() || this._loading ? ' disabled' : '') + '>' + commitButtonLabel + '</button>')
      + '  </div>'
      + '</div>';
  }

  _renderWizard() {
    return ''
      + '<div class="wizard-modal" role="dialog" aria-modal="true" aria-label="' + escapeHtml(this._wizardTitle()) + '">'
      + '  <div class="wizard-backdrop" data-action="close-wizard"></div>'
      + '  <div class="wizard-dialog">'
      + '    <div class="wizard-header"><div><div class="title">' + escapeHtml(this._wizardTitle()) + '</div><div class="subtitle">Choose one intake path, move step by step, then commit the reviewed batch into Inbox.</div></div><button class="button" data-action="close-wizard">Close</button></div>'
      + this._renderWizardProgress()
      + (this._error ? '<div class="status error">' + escapeHtml(this._error) + '</div>' : '')
      + (this._status ? '<div class="status">' + escapeHtml(this._status) + '</div>' : '')
      + '    <div class="wizard-body">' + this._renderWizardBody() + '</div>'
      + this._renderWizardFooter()
      + '    <input id="browser-file-input" class="hidden-upload-input" type="file" multiple data-action="browser-files">'
      + '    <input id="browser-folder-input" class="hidden-upload-input" type="file" multiple webkitdirectory directory data-action="browser-folder">'
      + '  </div>'
      + '</div>';
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
    if (action === 'set-commit-mode') {
      return;
    }
    if (action === 'browser-files' || action === 'browser-folder') {
      return;
    }
    event.preventDefault();
    if (action === 'refresh-intake') {
      this._refreshAll();
      return;
    }
    if (action === 'open-browser-wizard') {
      this._openWizard('browser');
      return;
    }
    if (action === 'open-server-wizard') {
      this._openWizard('server');
      return;
    }
    if (action === 'close-wizard') {
      this._closeWizard();
      return;
    }
    if (action === 'wizard-next') {
      this._goToWizardStep(this._wizardStep + 1);
      return;
    }
    if (action === 'wizard-back') {
      this._goToWizardStep(this._wizardStep - 1);
      return;
    }
    if (action === 'commit-wizard') {
      this._submitServerSelections();
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
    if (action === 'remove-selection') {
      this._removeSelection(String(target.getAttribute('data-path') || ''));
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
    if (action === 'remove-browser-file') {
      this._removeBrowserFile(String(target.getAttribute('data-key') || ''));
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
    if (action === 'browser-files' || action === 'browser-folder') {
      this._appendBrowserFiles(target.files);
      target.value = '';
      return;
    }
    if (action === 'cleanup-policy') {
      this._setCleanupPolicy(target.value);
      return;
    }
    if (action === 'browser-title-source') {
      this._updateBrowserBatchMeta({
        group_title_source: String(target.value || 'first-file').trim(),
        group_title: '',
      });
      this._render();
      return;
    }
    if (action === 'browser-grouping') {
      var groupingStrategy = String(target.value || 'none').trim();
      var titleSource = this._browserGroupingTitleSource(groupingStrategy);
      this._updateBrowserBatchMeta({
        grouping_strategy: groupingStrategy,
        group_title_source: groupingStrategy === 'none' ? this._browserBatchTitleSource() : titleSource,
        group_title: '',
      });
      this._render();
      return;
    }
    if (action === 'browser-group-title') {
      return;
    }
    if (action === 'set-commit-mode') {
      this._commitMode = String(target.value || 'queue');
      this._render();
      return;
    }
    if (action === 'set-destination') {
      this._destinationChoice = String(target.value || 'curated');
      this._render();
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
      var groupingValue = String(target.value || 'none').trim();
      this._selected = Object.assign({}, this._selected, {
        [path]: Object.assign({}, this._selected[path], {
          grouping_strategy: groupingValue,
          group_title_source: groupingValue === 'flat' ? 'first-file' : this._selectionTitleSource(this._selected[path]),
        }),
      });
      this._render();
      return;
    }
    if (action === 'selection-title-source-files') {
      this._updateSelectedFileBatchMeta({
        group_title_source: String(target.value || 'first-file').trim(),
        group_title: '',
      });
      this._render();
      return;
    }
    if (action === 'selection-group-title-files') {
      return;
    }
    if (action === 'selection-title-source') {
      this._selected = Object.assign({}, this._selected, {
        [path]: Object.assign({}, this._selected[path], {
          group_title_source: String(target.value || 'folder').trim(),
          group_title: '',
        }),
      });
      this._render();
      return;
    }
    if (action === 'selection-group-title') {
      return;
    }
  }

  _handleInput(event) {
    var target = event.target instanceof Element ? event.target : null;
    if (!target) {
      return;
    }
    var action = String(target.getAttribute('data-action') || '');
    if (action === 'browser-group-title') {
      this._updateBrowserBatchMeta({
        group_title_source: 'custom',
        group_title: String(target.value || '').trim(),
      });
      return;
    }
    if (action === 'selection-group-title-files') {
      this._updateSelectedFileBatchMeta({
        group_title_source: 'custom',
        group_title: String(target.value || '').trim(),
      });
      return;
    }
    if (action === 'selection-group-title') {
      var path = String(target.getAttribute('data-path') || '');
      if (!path || !this._selected[path]) {
        return;
      }
      this._selected = Object.assign({}, this._selected, {
        [path]: Object.assign({}, this._selected[path], {
          group_title_source: 'custom',
          group_title: String(target.value || '').trim(),
        }),
      });
    }
  }

  render() {
    this._render();
  }

  _render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }
    var resultHtml = this._result
      ? '<section class="banner"><div class="title">Latest Result</div><div class="status">Upload ' + escapeHtml(this._result.upload_status) + ' / Validation ' + escapeHtml(this._result.validation_state) + ' / Cleanup ' + escapeHtml(this._result.cleanup_policy === 'keep' ? 'deferred (keep)' : 'pending policy') + (this._result.publish_status ? ' / Publish ' + escapeHtml(this._result.publish_status) : '') + '</div><div class="muted">Selection count ' + String(this._result.selection_count || 0) + ', expanded files ' + String(this._result.expanded_file_count || 0) + ', upload ' + escapeHtml(this._result.upload_id || '') + (this._result.local_model_id ? ', local model ' + escapeHtml(this._result.local_model_id) : '') + '</div>' + ((this._result.warnings || []).length ? '<div class="muted">Warnings: ' + escapeHtml((this._result.warnings || []).map(function (warning) { return warning.message || warning.code; }).join('; ')) + '</div>' : '') + '</section>'
      : '';
    var extraStyles = ''
      + '.wizard-launch-grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));}'
      + '.launch-card{display:grid;gap:10px;padding:18px;border-radius:20px;border:1px solid rgba(148,163,184,0.2);background:linear-gradient(180deg,rgba(30,41,59,0.18),rgba(15,23,42,0.1));}'
      + '.launch-kicker{font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--secondary-text-color);}'
      + '.launch-title{font-size:18px;font-weight:800;line-height:1.2;}'
      + '.wizard-modal{position:fixed;inset:0;z-index:20;display:grid;place-items:center;padding:24px;box-sizing:border-box;}'
      + '.wizard-backdrop{position:absolute;inset:0;background:rgba(15,23,42,0.58);backdrop-filter:blur(6px);}'
      + '.wizard-dialog{position:relative;display:grid;gap:14px;width:min(1080px,100%);max-height:min(92vh,980px);overflow:auto;padding:18px;border-radius:24px;border:1px solid rgba(148,163,184,0.22);background:linear-gradient(180deg,rgba(15,23,42,0.96),rgba(15,23,42,0.9));box-shadow:0 28px 80px rgba(2,6,23,0.45);}'
      + '.wizard-header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;}'
      + '.wizard-progress{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));}'
      + '.wizard-step{display:grid;gap:6px;padding:12px;border-radius:16px;border:1px solid rgba(148,163,184,0.18);background:rgba(30,41,59,0.45);}'
      + '.wizard-step.current{border-color:rgba(96,165,250,0.45);background:rgba(30,64,175,0.18);}'
      + '.wizard-step.complete{border-color:rgba(74,222,128,0.34);background:rgba(22,101,52,0.18);}'
      + '.wizard-step-number{font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--secondary-text-color);}'
      + '.wizard-step-label{font-size:14px;font-weight:800;}'
      + '.wizard-body{display:grid;gap:14px;grid-template-columns:minmax(0,1fr) minmax(0,1fr);align-items:start;}'
      + '.wizard-panel{display:grid;gap:12px;align-content:start;min-height:0;padding:14px;border-radius:18px;border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.22);}'
      + '.wizard-scroll-region{min-height:0;max-height:460px;overflow:auto;padding-right:4px;}'
      + '.wizard-selection-scroll{min-height:0;max-height:460px;overflow:auto;padding-right:4px;}'
      + '.wizard-review-scroll{min-height:0;max-height:420px;overflow:auto;padding-right:4px;}'
      + '.wizard-footer{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding-top:4px;}'
      + '@media (max-width: 860px){.wizard-body{grid-template-columns:1fr;}.wizard-dialog{padding:14px;max-height:94vh;}.wizard-modal{padding:12px;}}';

    this.shadowRoot.innerHTML = ''
      + '<style>' + sharedStyles + extraStyles + '</style>'
      + '<ha-card>'
      + '  <div class="shell">'
      + '    <div class="header">'
      + '      <div class="title-row">'
      + '        <div><div class="title">' + escapeHtml(this._config.title) + '</div><div class="subtitle">Run intake as a true stepwise flow: pick one path, review the staged batch, then commit it into Inbox.</div></div>'
      + '      </div>'
      + '      ' + (this._error && !this._wizardOpen ? '<div class="status error">' + escapeHtml(this._error) + '</div>' : '')
      + '      ' + (this._status && !this._wizardOpen ? '<div class="status">' + escapeHtml(this._status) + '</div>' : '')
      + '    </div>'
      + resultHtml
      + this._queueSummaryHtml()
      + this._renderLaunchPad()
      + this._renderRecentActivity()
      + '  </div>'
      + '</ha-card>'
      + (this._wizardOpen ? this._renderWizard() : '');
  }
}

if (!customElements.get('model-catalog-intake-home-card')) {
  customElements.define('model-catalog-intake-home-card', ModelCatalogIntakeHomeCard);
}
