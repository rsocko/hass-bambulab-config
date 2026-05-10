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
var uploadBrowserFilesWithFallback = intakeShared.uploadBrowserFilesWithFallback;
var normalizeGroupingStrategy = intakeShared.normalizeGroupingStrategy;
var isArchivePath = intakeShared.isArchivePath;

var BROWSER_PREVIEW_IMAGE_EXTENSIONS = {
  ".png": true,
  ".jpg": true,
  ".jpeg": true,
  ".webp": true,
  ".gif": true,
  ".bmp": true,
  ".svg": true,
  ".avif": true,
};

var BROWSER_PREVIEW_3MF_EXTENSIONS = {
  ".3mf": true,
};

var BROWSER_ARCHIVE_EXTENSIONS = {
  ".zip": true,
};

var BROWSER_3MF_THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024;

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
    this._busyState = null;
    this._roots = [];
    this._browse = { path: "/", entries: [], parent_path: null, is_root: true };
    this._selected = {};
    this._browserFiles = [];
    // Issue #1324: keys (from _browserFileKey) of browser entries the user has
    // "removed" on the Source step. Excluded entries stay in _browserFiles so
    // the left tree can still show them (struck-through with a Restore button)
    // for parity with the Server path. They are filtered out of every consumer
    // that builds the staged list, plan preview, organize step, or upload
    // payload via _filterBrowserFilesForSubmit.
    this._excludedBrowserKeys = {};
    this._intakeItems = [];
    this._queueUploads = [];
    this._wizardOpen = false;
    this._wizardCloseConfirmOpen = false;
    this._wizardMode = "";
    this._wizardStep = 1;
    this._launchWizardMode = "";
    this._launchWizardConsumed = false;
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
      launch_wizard: "",
    }, config || {});
    this._launchWizardMode = this._normalizeLaunchWizardMode(this._config.launch_wizard);
    this._launchWizardConsumed = false;
    if (this._launchWizardMode) {
      this._wizardOpen = true;
      this._wizardMode = this._launchWizardMode;
      this._wizardStep = 1;
    }
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this.isConnected && !this._loading && !this._roots.length) {
      this._refreshAll();
    }
    this._maybeAutoLaunchWizard();
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
    this._maybeAutoLaunchWizard();
  }

  disconnectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.removeEventListener("click", this._boundHandleClick);
      this.shadowRoot.removeEventListener("change", this._boundHandleChange);
      this.shadowRoot.removeEventListener("input", this._boundHandleInput);
    }
    this._revokeBrowserPreviewUrls(this._browserFiles);
  }

  getCardSize() {
    return 12;
  }

  _normalizeLaunchWizardMode(value) {
    var normalized = String(value || "").trim().toLowerCase();
    if (normalized === "server") {
      return "server";
    }
    if (normalized === "browser") {
      return "browser";
    }
    return "";
  }

  _maybeAutoLaunchWizard() {
    var mode = this._normalizeLaunchWizardMode(this._launchWizardMode);
    if (!mode || this._launchWizardConsumed || !this._hass) {
      return;
    }
    this._launchWizardConsumed = true;
    this._wizardOpen = true;
    this._wizardMode = mode;
    this._wizardStep = 1;
    this._render();
    this._openWizard(mode).catch(function () {
      // Leave the intake card visible if auto-launch fails for any reason.
    });
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
    return this._wizardMode === "browser" ? 2 : 3;
  }

  _wizardStepLabel(stepNumber) {
    if (stepNumber === 1) {
      return this._wizardMode === "server" ? "Select" : "Choose";
    }
    if (this._wizardMode === "server" && stepNumber === 2) {
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

  _isBrowserImageFile(file) {
    if (!file) {
      return false;
    }
    var mimeType = String(file.type || "").toLowerCase();
    if (mimeType.indexOf("image/") === 0) {
      return true;
    }
    var fileName = String(file.name || "");
    var extension = fileName.lastIndexOf(".") >= 0 ? fileName.slice(fileName.lastIndexOf(".")).toLowerCase() : "";
    return !!BROWSER_PREVIEW_IMAGE_EXTENSIONS[extension];
  }

  _isBrowser3mfFile(file) {
    if (!file) {
      return false;
    }
    var fileName = String(file.name || "");
    var extension = fileName.lastIndexOf(".") >= 0 ? fileName.slice(fileName.lastIndexOf(".")).toLowerCase() : "";
    return !!BROWSER_PREVIEW_3MF_EXTENSIONS[extension];
  }

  _isBrowserArchiveFile(file) {
    if (!file) {
      return false;
    }
    var fileName = String(file.name || "");
    if (typeof isArchivePath === 'function') {
      return !!isArchivePath(fileName);
    }
    var extension = fileName.lastIndexOf(".") >= 0 ? fileName.slice(fileName.lastIndexOf(".")).toLowerCase() : "";
    return !!BROWSER_ARCHIVE_EXTENSIONS[extension];
  }

  _browserArchiveRootName(file) {
    return pathStem(String(file && file.name || "").trim()) || basename(String(file && file.name || "").trim()) || "archive";
  }

  _normalizeBrowserArchiveMemberPath(memberPath) {
    return String(memberPath || "")
      .replace(/\\/g, "/")
      .split("/")
      .filter(function (part) {
        return part && part !== "." && part !== "..";
      })
      .join("/");
  }

  async _expandBrowserArchiveFile(file, currentBrowserTitleSource, currentBrowserTitle) {
    if (!(await this._ensureJsZipLoaded()) || typeof JSZip === "undefined") {
      return null;
    }
    var archiveRoot = this._browserArchiveRootName(file);
    var zip = await JSZip.loadAsync(file);
    var nextEntries = [];
    var memberNames = Object.keys(zip.files || {}).sort();
    for (var index = 0; index < memberNames.length; index += 1) {
      var memberName = memberNames[index];
      var zipEntry = zip.files[memberName];
      if (!zipEntry || zipEntry.dir) {
        continue;
      }
      var normalizedMemberPath = this._normalizeBrowserArchiveMemberPath(memberName);
      if (!normalizedMemberPath) {
        continue;
      }
      var memberBlob = await zipEntry.async("blob");
      var leafName = basename(normalizedMemberPath) || String(memberName || file.name || "archive.bin");
      var memberFile;
      try {
        memberFile = new File([memberBlob], leafName, {
          type: memberBlob.type || file.type || "application/octet-stream",
          lastModified: file.lastModified || Date.now(),
        });
      } catch (_error) {
        memberFile = memberBlob;
        memberFile.name = leafName;
        memberFile.lastModified = file.lastModified || Date.now();
      }
      var memberRelativePath = [archiveRoot].concat(normalizedMemberPath.split("/").filter(Boolean)).join("/");
      var previewUrl = await this._createBrowserPreviewUrl(memberFile);
      nextEntries.push({
        file: memberFile,
        name: leafName,
        relative_path: memberRelativePath,
        size_bytes: Number(memberBlob.size || 0),
        preview_url: previewUrl,
        grouping_strategy: this._browserHasFolderUpload() ? this._browserGroupingStrategy() : 'none',
        recurse: this._browserRecurse(),
        preserve_folder_structure: true,
        group_title_source: 'folder',
        group_title: currentBrowserTitleSource === 'custom' ? currentBrowserTitle : '',
        source_container_type: 'archive',
        source_container_name: String(file.name || archiveRoot || 'archive'),
      });
    }
    return nextEntries;
  }

  _inferImageMimeTypeFromPath(path) {
    var normalized = String(path || "").toLowerCase();
    if (normalized.endsWith(".png")) {
      return "image/png";
    }
    if (normalized.endsWith(".jpg") || normalized.endsWith(".jpeg")) {
      return "image/jpeg";
    }
    return "";
  }

  async _ensureJsZipLoaded() {
    if (typeof JSZip !== "undefined") {
      return true;
    }

    var existing = document.querySelector('script[data-model-catalog-jszip="1"]');
    if (existing) {
      if (existing.dataset.loaded === "1") {
        return typeof JSZip !== "undefined";
      }
      await new Promise(function (resolve) {
        existing.addEventListener("load", resolve, { once: true });
        existing.addEventListener("error", resolve, { once: true });
      });
      return typeof JSZip !== "undefined";
    }

    await new Promise(function (resolve) {
      var script = document.createElement("script");
      script.src = "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js";
      script.async = true;
      script.dataset.modelCatalogJszip = "1";
      script.addEventListener("load", function () {
        script.dataset.loaded = "1";
        resolve();
      }, { once: true });
      script.addEventListener("error", resolve, { once: true });
      document.head.appendChild(script);
    });

    return typeof JSZip !== "undefined";
  }

  _isSafeBrowser3mfThumbnail(blob, entryPath) {
    if (!blob || typeof blob.size !== "number") {
      return false;
    }
    if (blob.size > BROWSER_3MF_THUMBNAIL_MAX_BYTES) {
      return false;
    }
    var lowerPath = String(entryPath || "").toLowerCase();
    if (!lowerPath.endsWith(".png") && !lowerPath.endsWith(".jpg") && !lowerPath.endsWith(".jpeg")) {
      return false;
    }
    var allowedTypes = { "image/png": true, "image/jpeg": true };
    if (blob.type && !allowedTypes[blob.type]) {
      return false;
    }
    return true;
  }

  async _extractBrowser3mfThumbnailUrl(file) {
    if (!this._isBrowser3mfFile(file)) {
      return "";
    }
    var jsZipReady = await this._ensureJsZipLoaded();
    if (!jsZipReady || typeof JSZip === "undefined") {
      return "";
    }

    var buffer = await file.arrayBuffer();
    if (!buffer || !buffer.byteLength) {
      return "";
    }

    var zip = new JSZip();
    await zip.loadAsync(buffer);

    var zipEntries = Object.keys(zip.files || {});
    var entryLookup = {};
    zipEntries.forEach(function (name) {
      entryLookup[String(name).toLowerCase()] = name;
    });

    var knownPaths = [
      "metadata/thumbnail.png",
      "metadata/thumbnail.jpg",
      "metadata/thumbnail.jpeg",
      "thumbnails/thumbnail.png",
      "thumbnails/thumbnail.jpg",
      "thumbnails/thumbnail.jpeg",
      "3d/thumbnail.png",
      "3d/thumbnail.jpg",
      "3d/thumbnail.jpeg",
      "metadata/plate_1.png",
      "metadata/plate_1.jpg",
      "auxiliaries/model pictures/thumbnail.png",
      "auxiliaries/model pictures/thumbnail.jpg",
    ];

    var card = this;
    var toPreviewUrl = async function (entryName) {
      var member = zip.file(entryName);
      if (!member) {
        return "";
      }
      var blob = await member.async("blob");
      if (!card._isSafeBrowser3mfThumbnail(blob, entryName)) {
        return "";
      }
      var inferred = card._inferImageMimeTypeFromPath(entryName);
      var previewBlob = inferred && blob.type !== inferred
        ? new Blob([blob], { type: inferred })
        : blob;
      try {
        return URL.createObjectURL(previewBlob);
      } catch (_error) {
        return "";
      }
    };

    for (var i = 0; i < knownPaths.length; i += 1) {
      var matched = entryLookup[knownPaths[i]];
      if (!matched) {
        continue;
      }
      try {
        var knownPreviewUrl = await toPreviewUrl(matched);
        if (knownPreviewUrl) {
          return knownPreviewUrl;
        }
      } catch (_knownError) {
        // Try next candidate.
      }
    }

    var fallbackPrefixes = ["metadata/", "thumbnails/", "3d/", "auxiliaries/model pictures/"];
    var fallbackEntries = zipEntries.filter(function (name) {
      var lower = String(name || "").toLowerCase();
      var imageExt = lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg");
      if (!imageExt) {
        return false;
      }
      return fallbackPrefixes.some(function (prefix) {
        return lower.indexOf(prefix) === 0;
      });
    }).sort();

    for (var j = 0; j < fallbackEntries.length; j += 1) {
      try {
        var fallbackPreviewUrl = await toPreviewUrl(fallbackEntries[j]);
        if (fallbackPreviewUrl) {
          return fallbackPreviewUrl;
        }
      } catch (_fallbackError) {
        // Continue.
      }
    }

    return "";
  }

  async _createBrowserPreviewUrl(file) {
    if (typeof URL === "undefined" || typeof URL.createObjectURL !== "function") {
      return "";
    }
    if (this._isBrowserImageFile(file)) {
      try {
        return URL.createObjectURL(file);
      } catch (_error) {
        return "";
      }
    }
    if (this._isBrowser3mfFile(file)) {
      try {
        return await this._extractBrowser3mfThumbnailUrl(file);
      } catch (_extractError) {
        return "";
      }
    }
    return "";
  }

  _revokeBrowserPreviewUrl(previewUrl) {
    if (!previewUrl || typeof URL === "undefined" || typeof URL.revokeObjectURL !== "function") {
      return;
    }
    try {
      URL.revokeObjectURL(previewUrl);
    } catch (_error) {
      // Ignore revoke errors.
    }
  }

  _revokeBrowserPreviewUrls(entries) {
    (entries || []).forEach(function (entry) {
      this._revokeBrowserPreviewUrl(entry && entry.preview_url ? String(entry.preview_url) : "");
    }, this);
  }

  _clearBrowserFiles() {
    this._revokeBrowserPreviewUrls(this._browserFiles);
    this._browserFiles = [];
    // Issue #1324: clearing the staging set also clears any pending exclusions.
    this._excludedBrowserKeys = {};
  }

  _setBusyState(nextState) {
    this._busyState = Object.assign({
      phase: "",
      detail: "",
      mode: "indeterminate",
      percent: null,
      files_done: null,
      files_total: null,
      bytes_done: null,
      bytes_total: null,
    }, nextState || {});
    this._render();
  }

  _setBusyPhase(phase, detail) {
    this._setBusyState({
      phase: String(phase || "Working"),
      detail: String(detail || ""),
      mode: "indeterminate",
      percent: null,
    });
  }

  _updateUploadProgress(progress, context) {
    var details = context || {};
    var filesTotal = Number(details.files_total || 0);
    var bytesTotal = Number(details.bytes_total || 0);
    var loaded = Number(progress && progress.loaded || 0);
    var total = Number(progress && progress.total || 0);
    var filesProcessed = Number(progress && progress.files_processed || 0);
    var lengthComputable = !!(progress && progress.lengthComputable && total > 0);

    if (!lengthComputable) {
      this._setBusyState({
        phase: "Uploading files",
        detail: filesTotal > 0
          ? ("Preparing file " + String(Math.min(Math.max(filesProcessed, 0), filesTotal)) + " of " + String(filesTotal))
          : "Preparing browser upload payload",
        mode: "indeterminate",
        files_done: filesProcessed > 0 ? filesProcessed : null,
        files_total: filesTotal > 0 ? filesTotal : null,
      });
      return;
    }

    var safeTotal = total > 0 ? total : (bytesTotal > 0 ? bytesTotal : 0);
    var percent = safeTotal > 0 ? Math.max(0, Math.min(100, Math.round((loaded / safeTotal) * 100))) : null;
    this._setBusyState({
      phase: "Uploading files",
      detail: "Transferring browser files to intake staging",
      mode: "determinate",
      percent: percent,
      files_done: filesTotal > 0 ? Math.min(filesTotal, filesProcessed || filesTotal) : null,
      files_total: filesTotal > 0 ? filesTotal : null,
      bytes_done: loaded,
      bytes_total: safeTotal,
    });
  }

  _clearBusyState() {
    this._busyState = null;
  }

  // Issue #1324: returns true when the given browser entry key has been marked
  // as excluded by the user on the Source step. Excluded entries remain in
  // _browserFiles for display purposes but are filtered out of all submit/plan
  // consumers via _filterBrowserFilesForSubmit.
  _isBrowserKeyExcluded(key) {
    return !!(this._excludedBrowserKeys && this._excludedBrowserKeys[String(key || '')]);
  }

  _setBrowserKeyExcluded(key, excluded) {
    var nextExcluded = Object.assign({}, this._excludedBrowserKeys || {});
    var normalizedKey = String(key || '');
    if (!normalizedKey) {
      return;
    }
    if (excluded) {
      nextExcluded[normalizedKey] = true;
    } else {
      delete nextExcluded[normalizedKey];
    }
    this._excludedBrowserKeys = nextExcluded;
  }

  _excludedBrowserKeyCount() {
    return Object.keys(this._excludedBrowserKeys || {}).length;
  }

  // Issue #1350: count only files excluded WITHIN a parent folder that still
  // has at least one included sibling (i.e., real "excluded from this folder's
  // intake" semantics). Files whose entire root folder has been removed are
  // not counted because the root no longer participates in the batch — the
  // user simply hasn't selected it. Loose root-level files that are excluded
  // are likewise treated as just-not-selected.
  _meaningfulExcludedBrowserCount() {
    var files = this._browserFiles || [];
    if (!files.length) {
      return 0;
    }
    var card = this;
    var rootTotals = {};
    var rootExcluded = {};
    var rootlessExcluded = 0;
    files.forEach(function (entry) {
      var relativePath = String(entry.relative_path || entry.name || '').replace(/\\/g, '/');
      var pathParts = relativePath.split('/').filter(function (part) { return !!part; });
      var rootKey = pathParts.length > 1 ? pathParts[0] : '';
      var isExcluded = card._isBrowserKeyExcluded(card._browserFileKey(entry));
      if (!rootKey) {
        // Loose root-level file: an excluded loose file is just "not selected".
        if (isExcluded) {
          rootlessExcluded += 1;
        }
        return;
      }
      rootTotals[rootKey] = (rootTotals[rootKey] || 0) + 1;
      if (isExcluded) {
        rootExcluded[rootKey] = (rootExcluded[rootKey] || 0) + 1;
      }
    });
    var meaningful = 0;
    Object.keys(rootExcluded).forEach(function (rootKey) {
      // Only count if the parent folder still has at least one included file.
      if (rootExcluded[rootKey] < rootTotals[rootKey]) {
        meaningful += rootExcluded[rootKey];
      }
    });
    return meaningful;
  }

  // Issue #1350: count browser-staged files that are NOT excluded so the
  // wizard's Next button is disabled when the user has effectively cleared
  // the staging area (every uploaded file removed).
  _activeBrowserFileCount() {
    var files = this._browserFiles || [];
    var card = this;
    var count = 0;
    files.forEach(function (entry) {
      if (!card._isBrowserKeyExcluded(card._browserFileKey(entry))) {
        count += 1;
      }
    });
    return count;
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
    var card = this;
    this._browserFiles.forEach(function (entry) {
      // Issue #1324: skip entries the user has marked as excluded so the
      // selected-folder summary reflects what will actually be uploaded.
      if (card._isBrowserKeyExcluded(card._browserFileKey(entry))) {
        return;
      }
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

  _browserRecurse() {
    if (!this._browserFiles.length) {
      return true;
    }
    return this._browserFiles[0].recurse !== false;
  }

  _filterBrowserFilesForSubmit(files) {
    var entries = Array.isArray(files) ? files : [];
    if (!entries.length) {
      return [];
    }
    // Issue #1324: drop any entry the user has explicitly removed/excluded on
    // the Source step before applying the recursive-vs-flat scope filter.
    var card = this;
    var nonExcluded = entries.filter(function (entry) {
      return !card._isBrowserKeyExcluded(card._browserFileKey(entry));
    });
    if (!nonExcluded.length) {
      return [];
    }
    if (!this._browserHasFolderUpload() || this._browserRecurse()) {
      return nonExcluded.slice();
    }
    return nonExcluded.filter(function (entry) {
      var relativePath = String(entry.relative_path || entry.name || '').replace(/\\/g, '/');
      var pathParts = relativePath.split('/').filter(function (part) { return !!part; });
      // Non-recursive folder mode keeps only direct children of selected roots.
      return pathParts.length <= 2;
    });
  }

  _browserGroupingStrategy() {
    if (!this._browserFiles.length) {
      return 'none';
    }
    return normalizeGroupingStrategy(this._browserFiles[0] && this._browserFiles[0].grouping_strategy, {
      allowFolderStrategies: true,
    });
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
      if (entry.grouping_strategy) {
        next.grouping_strategy = String(entry.grouping_strategy || 'none').trim();
      }
      if (entry.preserve_folder_structure !== undefined && entry.preserve_folder_structure !== null) {
        next.preserve_folder_structure = entry.preserve_folder_structure !== false;
      }
      if (entry.group_title_source) {
        next.group_title_source = this._selectionTitleSource(entry);
      }
      if (entry.group_title || entry.group_title_source) {
        next.group_title = this._resolvedGroupTitle(entry);
      }
      if (entry.type === "folder") {
        next.recurse = !!entry.recurse;
      }
      return next;
    }, this);
  }

  _enabledBrowserFiles(sourceMode) {
    return sourceMode === "browser" ? this._filterBrowserFilesForSubmit(this._browserFiles) : [];
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
    this._wizardCloseConfirmOpen = false;
    this._wizardMode = nextMode;
    this._wizardStep = 1;
    this._cleanupPolicyValue = this._defaultCleanupPolicy(nextMode);
    this._commitMode = 'queue';
    this._destinationChoice = 'curated';
    this._error = "";
    this._status = "";
    this._result = null;
    this._selected = {};
    this._clearBrowserFiles();
    await this._setSourceMode(nextMode);
    if (nextMode === "server") {
      await this._loadBrowse('/');
      return;
    }
    this._render();
  }

  _isWizardDirty() {
    if (this._wizardStep > 1) {
      return true;
    }
    try {
      if (this._selectedList && this._selectedList().length > 0) {
        return true;
      }
    } catch (err) { /* noop */ }
    if (Array.isArray(this._browserFiles) && this._browserFiles.length > 0) {
      return true;
    }
    return false;
  }

  _openWizardCloseConfirm() {
    this._wizardCloseConfirmOpen = true;
    this._render();
  }

  _dismissWizardCloseConfirm() {
    if (!this._wizardCloseConfirmOpen) {
      return;
    }
    this._wizardCloseConfirmOpen = false;
    this._render();
  }

  _renderWizardCloseConfirm() {
    if (!this._wizardCloseConfirmOpen) {
      return '';
    }
    return ''
      + '<div class="wizard-close-confirm" role="dialog" aria-modal="true" aria-label="Discard intake selections">'
      + '  <div class="wizard-close-confirm-backdrop" data-action="dismiss-close-confirm"></div>'
      + '  <div class="wizard-close-confirm-dialog">'
      + '    <div class="title">Discard Intake Selections?</div>'
      + '    <div class="muted">Your in-progress selections and wizard setup will be lost.</div>'
      + '    <div class="button-row wizard-close-confirm-actions">'
      + '      <button class="button" data-action="dismiss-close-confirm">Keep Editing</button>'
      + '      <button class="button danger" data-action="confirm-close-wizard">Discard And Close</button>'
      + '    </div>'
      + '  </div>'
      + '</div>';
  }

  _closeWizard(options) {
    var force = !!(options && options.force);
    if (!force && this._isWizardDirty()) {
      this._openWizardCloseConfirm();
      return;
    }
    this._wizardCloseConfirmOpen = false;
    this._wizardOpen = false;
    this._wizardMode = "";
    this._wizardStep = 1;
    this._cleanupPolicyValue = null;
    this._commitMode = 'queue';
    this._destinationChoice = 'curated';
    this._selected = {};
    this._clearBrowserFiles();
    this._render();
  }

  _canAdvanceWizard() {
    if (this._wizardMode === "server") {
      return this._selectedList().length > 0;
    }
    // Issue #1350: only count non-excluded browser entries.
    return this._activeBrowserFileCount() > 0;
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
      // Issue #1352: when selecting a folder, drop any previously-selected
      // descendants so they collapse into the folder's "included in selection"
      // visualization instead of double-counting on the right-side list and
      // appearing as explicitly selected when the user re-enters the folder.
      if (entryType === 'folder') {
        var prefix = normalizedPath.replace(/\/+$/, '') + '/';
        Object.keys(nextSelected).forEach(function (existingPath) {
          if (existingPath !== normalizedPath && existingPath.indexOf(prefix) === 0) {
            delete nextSelected[existingPath];
          }
        });
      }
      nextSelected[normalizedPath] = {
        type: entryType,
        path: normalizedPath,
        recurse: true,
        grouping_strategy: "none",
        preserve_folder_structure: true,
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

  async _appendBrowserFiles(fileList) {
    var currentBrowserTitleSource = this._browserBatchTitleSource();
    var currentBrowserTitle = this._browserBatchResolvedTitle();
    var nextByKey = {};
    this._browserFiles.forEach(function (entry) {
      nextByKey[this._browserFileKey(entry)] = entry;
    }, this);
    var incomingFiles = Array.prototype.slice.call(fileList || []);
    for (var index = 0; index < incomingFiles.length; index += 1) {
      var file = incomingFiles[index];
      if (!file || typeof file.arrayBuffer !== "function") {
        continue;
      }
      var relativePath = String(file.webkitRelativePath || file.name || "").trim() || String(file.name || "").trim();
      if (this._isBrowserArchiveFile(file)) {
        try {
          var archiveEntries = await this._expandBrowserArchiveFile(file, currentBrowserTitleSource, currentBrowserTitle);
          if (archiveEntries && archiveEntries.length) {
            for (var archiveIndex = 0; archiveIndex < archiveEntries.length; archiveIndex += 1) {
              var archiveEntry = archiveEntries[archiveIndex];
              var archiveKey = this._browserFileKey(archiveEntry);
              var existingArchiveEntry = nextByKey[archiveKey];
              if (existingArchiveEntry && existingArchiveEntry.preview_url && existingArchiveEntry.preview_url !== archiveEntry.preview_url) {
                this._revokeBrowserPreviewUrl(existingArchiveEntry.preview_url);
              }
              nextByKey[archiveKey] = archiveEntry;
              if (this._isBrowserKeyExcluded(archiveKey)) {
                this._setBrowserKeyExcluded(archiveKey, false);
              }
            }
            continue;
          }
        } catch (_error) {
          // Fall back to treating the archive like a regular file if browser-side
          // expansion is unavailable or the archive is unreadable.
        }
      }
      var previewUrl = await this._createBrowserPreviewUrl(file);
      var nextEntry = {
        file: file,
        name: String(file.name || relativePath || "upload.bin"),
        relative_path: relativePath,
        size_bytes: Number(file.size || 0),
        preview_url: previewUrl,
        grouping_strategy: this._browserHasFolderUpload() ? this._browserGroupingStrategy() : 'none',
        recurse: this._browserRecurse(),
        preserve_folder_structure: true,
        group_title_source: currentBrowserTitleSource,
        group_title: currentBrowserTitleSource === 'custom' ? currentBrowserTitle : '',
      };
      var nextKey = this._browserFileKey(nextEntry);
      var existingEntry = nextByKey[nextKey];
      if (existingEntry && existingEntry.preview_url && existingEntry.preview_url !== nextEntry.preview_url) {
        this._revokeBrowserPreviewUrl(existingEntry.preview_url);
      }
      nextByKey[nextKey] = nextEntry;
      // Issue #1324: re-adding a previously excluded entry is a deliberate user
      // act (re-pick of the same file or folder), so treat it as an implicit
      // Restore.
      if (this._isBrowserKeyExcluded(nextKey)) {
        this._setBrowserKeyExcluded(nextKey, false);
      }
    }
    this._browserFiles = Object.keys(nextByKey).map(function (key) { return nextByKey[key]; }).sort(function (left, right) {
      return String(left.relative_path || left.name).localeCompare(String(right.relative_path || right.name));
    });
    this._render();
  }

  _removeBrowserFile(key) {
    var nextFiles = [];
    this._browserFiles.forEach(function (entry) {
      if (this._browserFileKey(entry) === key) {
        this._revokeBrowserPreviewUrl(entry.preview_url);
        return;
      }
      nextFiles.push(entry);
    }, this);
    this._browserFiles = nextFiles;
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
      grouping_strategy: String(fileEntry.grouping_strategy || 'none').trim(),
      preserve_folder_structure: fileEntry.preserve_folder_structure !== false,
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

  _supportsServerPreview(pathValue) {
    var normalized = String(pathValue || "").toLowerCase();
    return /\.(3mf|png|jpg|jpeg|webp|gif|svg)$/.test(normalized);
  }

  _serverPreviewUrl(pathValue) {
    var normalizedPath = String(pathValue || "").trim();
    if (!normalizedPath || !this._supportsServerPreview(normalizedPath)) {
      return "";
    }
    var endpoint = "/api/intake/preview?path=" + encodeURIComponent(normalizedPath);
    var sidecarBaseUrl = this._resolveSidecarUrl();
    if (!sidecarBaseUrl) {
      return endpoint;
    }
    return sidecarBaseUrl.replace(/\/$/, "") + endpoint;
  }

  _serverPreviewMarkup(pathValue, displayName) {
    var previewUrl = this._serverPreviewUrl(pathValue);
    if (!previewUrl) {
      return '<div class="entry-thumb placeholder">No preview</div>';
    }
    return '<div class="entry-thumb"><img class="entry-thumb-image" src="' + escapeHtml(previewUrl) + '" alt="Preview for ' + escapeHtml(displayName) + '" loading="lazy" decoding="async"></div>';
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
    this._setBusyPhase("Preparing intake job", "Collecting and normalizing selected files");
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
        var totalBrowserBytes = browserFiles.reduce(function (sum, entry) {
          var size = entry && entry.file ? Number(entry.file.size || 0) : 0;
          return sum + (Number.isFinite(size) ? size : 0);
        }, 0);
        response = await uploadBrowserFilesWithFallback(
          this._hass,
          sidecarBaseUrl,
          browserFiles,
          finalSelections,
          cleanupPolicy,
          {
            onPhase: function (phaseCode) {
              if (phaseCode === "encoding_files") {
                this._setBusyPhase("Uploading files", "Encoding files for fallback upload mode");
              } else if (phaseCode === "submitting_request") {
                this._setBusyPhase("Uploading files", "Submitting intake upload request");
              }
            }.bind(this),
            onUploadProgress: function (progressPayload) {
              this._updateUploadProgress(progressPayload, {
                files_total: browserFiles.length,
                bytes_total: totalBrowserBytes,
              });
            }.bind(this),
          }
        );
      } else {
        this._setBusyPhase("Preparing intake job", "Resolving server selections and staging queue item");
        response = await callServiceWithResponse(this._hass, "rest_command", "model_catalog_select_source_filesystem_entries", {
          selections: finalSelections,
          cleanup_policy: cleanupPolicy,
        });
      }
      this._setBusyPhase("Validating plan", "Running pre-commit intake validation");
      var validation = await callServiceWithResponse(this._hass, "rest_command", "model_catalog_validate_intake_item", {
        item_id: response.upload_id,
      });
      var validationState = validation.validation ? validation.validation.validation_state : "unknown";
      var publishResponse = null;
      var publishDestination = null;
      if (this._commitMode === 'execute_now' && validationState === 'ready') {
        publishDestination = this._destinationChoice || 'curated';
        var publishService = publishDestination === 'working' ? 'model_catalog_publish_to_working' : 'model_catalog_publish_to_local';
        this._setBusyPhase(
          publishDestination === 'working' ? 'Publishing to Working Files' : 'Publishing to Catalog',
          'Committing validated intake plan to destination'
        );
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
          var destinationText = publishDestination === 'working' ? 'working files' : 'the catalog';
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
          this._status = "Validation produced warnings, so the batch remains in the background queue for follow-up review.";
        }
      } else {
        this._status = browserFiles.length
          ? "Browser batch queued to intake and validated."
          : "Server selection queued to intake and validated." + (expandedSelections.length ? " (" + String(expandedSelections.length) + " files expanded from grouped folder selections.)" : "");
      }
      this._selected = {};
      this._clearBrowserFiles();
      this._wizardOpen = false;
      this._wizardMode = "";
      this._wizardStep = 1;
      this._cleanupPolicyValue = null;
      this._commitMode = 'queue';
      this._destinationChoice = 'curated';
      this._loading = false;
      // Issue #1323: release the host page scroll lock that _openWizard set.
      // Without this, the dashboard remains unscrollable after a successful
      // queue/publish until the browser is hard-refreshed.
      if (typeof this._restoreBackgroundScroll === 'function') {
        this._restoreBackgroundScroll();
      }
      this._clearBusyState();
      await this._refreshAll();
    } catch (error) {
      this._error = error && error.message ? String(error.message) : "Could not queue intake selection.";
      this._loading = false;
      this._clearBusyState();
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
      + '  <div class="summary-card"><div class="summary-label">Queue Snapshot</div><div class="summary-value">Ready ' + String(itemCounts.validated_ready || 0) + ' / Warning ' + String(itemCounts.validated_warning || 0) + '</div><div class="muted">Deferred ' + String(itemCounts.deferred || 0) + ' / Completed ' + String((itemCounts.grouped_new || 0) + (itemCounts.grouped_existing || 0) + (itemCounts.published_to_catalog || 0)) + '</div></div>'
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
      var archiveName = String(entry.source_container_name || '').trim();
      var previewUrl = String(entry.preview_url || "");
      var previewMarkup = previewUrl
        ? '<div class="entry-thumb"><img class="entry-thumb-image" src="' + escapeHtml(previewUrl) + '" alt="Image preview for ' + escapeHtml(displayName) + '" loading="lazy" decoding="async"></div>'
        : '<div class="entry-thumb placeholder">No preview</div>';
      return ''
        + '<article class="entry-row">'
        + '  <div class="entry-top">'
        + previewMarkup
        + '<div><div class="entry-name">' + escapeHtml(displayName) + '</div><div class="entry-path">' + escapeHtml(relativePath || entry.name || "") + '</div>' + (folderPath ? '<div class="muted">Folder: ' + escapeHtml(folderPath) + '</div>' : '') + (archiveName ? '<div class="muted">Archive: ' + escapeHtml(archiveName) + '</div>' : '') + '</div><div class="button-row"><span class="chip">browser</span>' + (archiveName ? '<span class="chip">archive content</span>' : (folderPath ? '<span class="chip">folder upload</span>' : '<span class="chip">single file</span>')) + '<span class="chip">' + escapeHtml(formatBytes(entry.size_bytes || 0)) + '</span>'
        + (showActions ? '<button class="button warn" data-action="remove-browser-file" data-key="' + escapeHtml(this._browserFileKey(entry)) + '">Remove</button>' : '')
        + '  </div></div>'
        + '</article>';
    }, this).join('') + '</div>';
  }

  _renderBrowserSelectionSummary() {
    var topFolders = this._browserTopLevelFolders();
    var folderCount = topFolders.length;
    var groupingStrategy = this._browserGroupingStrategy();
    var recurse = this._browserRecurse();
    var filteredFileCount = this._filterBrowserFilesForSubmit(this._browserFiles).length;
    var titleSource = this._browserBatchTitleSource();
    var resolvedTitle = this._browserBatchResolvedTitle();
    return ''
      + '<div class="result-summary">'
      + '  <div class="result-line"><span>Source path</span><strong>Browser Upload</strong></div>'
      + '  <div class="result-line"><span>Cleanup policy</span><strong>delete_on_verified (automatic)</strong></div>'
        + '  <div class="result-line"><span>Cleanup policy</span><strong>delete_on_verified (automatic)</strong></div>'
      + (folderCount ? '  <div class="result-line"><span>Files queued now</span><strong>' + String(filteredFileCount) + '</strong></div>' : '')
      + '  <div class="result-line"><span>Staged folders</span><strong>' + String(folderCount) + '</strong></div>'
      + (folderCount
        ? '  <div class="result-line"><span>Folder scope</span><strong>' + escapeHtml(recurse ? 'Include subfolders (recursive)' : 'Just this folder') + '</strong></div>'
        : '')
      + (folderCount
        ? '  <div class="result-line"><span>Grouping</span><strong>' + escapeHtml(groupingStrategy) + '</strong></div>'
        : '')
      + (this._browserFiles.length
        ? '  <div class="item-grid">'
          + (folderCount
            ? '    <div class="field"><label>Folder Scope</label><select class="select" data-action="browser-recurse"><option value="true"' + (recurse ? ' selected' : '') + '>Include subfolders (recursive)</option><option value="false"' + (!recurse ? ' selected' : '') + '>Just this folder</option></select></div>'
            : '')
          + (folderCount
            ? '    <div class="field"><label>Grouping</label><select class="select" data-action="browser-grouping"><option value="none"' + (groupingStrategy === 'none' ? ' selected' : '') + '>None</option><option value="by-folder"' + (groupingStrategy === 'by-folder' ? ' selected' : '') + '>by-folder</option><option value="by-root"' + (groupingStrategy === 'by-root' ? ' selected' : '') + '>by-root</option><option value="flat"' + (groupingStrategy === 'flat' ? ' selected' : '') + '>flat</option></select></div>'
            : '')
          + (folderCount && recurse
            ? '    <div class="field"><label>Folder Structure</label><select class="select" data-action="browser-preserve-structure"><option value="true"' + (this._browserFiles[0] && this._browserFiles[0].preserve_folder_structure !== false ? ' selected' : '') + '>Preserve</option><option value="false"' + (this._browserFiles[0] && this._browserFiles[0].preserve_folder_structure === false ? ' selected' : '') + '>Flatten</option></select></div>'
            : '')
          + '    <div class="field"><label>Title Basis</label><select class="select" data-action="browser-title-source"><option value="folder"' + (titleSource === 'folder' ? ' selected' : '') + '>Folder name</option><option value="first-file"' + (titleSource === 'first-file' ? ' selected' : '') + '>First file</option><option value="custom"' + (titleSource === 'custom' ? ' selected' : '') + '>Custom</option></select></div>'
          + '    <div class="field"><label>Working Group Title</label><input class="input" type="text" value="' + escapeHtml(resolvedTitle) + '" data-action="browser-group-title" placeholder="Working Group"></div>'
          + '  </div><div class="muted">This title is carried into Inbox for browser-uploaded files and folders. ZIP archives are expanded in the browser into browsable folder trees before upload, so the wizard can treat them like a container instead of a flat file.' + (folderCount ? ' Folder uploads now expose the same recurse and grouping controls as the server picker.' : '') + ((folderCount && recurse) ? ' Preserve folder structure is supported in Catalog.' : '') + '</div>'
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
      var displayName = String(entry.name || basename(entry.path) || "");
      var isArchive = entry.type === 'file' && typeof isArchivePath === 'function' && isArchivePath(entry.path || '');
      var selectable = entry.selectable !== false;
      var previewMarkup = entry.type === 'file' && !isArchive
        ? this._serverPreviewMarkup(entry.path, displayName)
        : (isArchive 
          ? '<div class="entry-thumb placeholder"><ha-icon icon="mdi:folder-zip-outline"></ha-icon><div style="font-size: 0.75rem; margin-top: 4px;">zip</div></div>'
          : '<div class="entry-thumb placeholder">Folder</div>');
      return ''
        + '<article class="entry-row' + (selected ? ' selected' : '') + '">'
        + '  <div class="entry-top">'
        + previewMarkup
        + '    <div>'
        + '      <div class="entry-name">' + escapeHtml(displayName) + '</div>'
        + '      <div class="entry-path">' + escapeHtml(entry.path || '') + '</div>'
        + '    </div>'
        + '    <div class="button-row">'
        + (entry.type === 'folder' ? '<span class="chip">Folder</span>' : (isArchive ? '<span class="chip">Archive</span>' : '<span class="chip">File</span>'))
        + (isArchive ? '<span class="chip">Archive Container</span>' : '')
        + (!selectable ? '<span class="chip">View Only</span>' : '')
        + (entry.type === 'file' && entry.size_bytes != null ? '<span class="chip">' + escapeHtml(formatBytes(entry.size_bytes)) + '</span>' : '')
        + '    </div>'
        + '  </div>'
        + '  <div class="entry-actions">'
        + ((entry.type === 'folder' || isArchive) ? '<button class="button" data-action="browse-path" data-path="' + escapeHtml(entry.path) + '">Open</button>' : '')
        + (selectable
          ? '    <button class="button ' + (selected ? 'warn' : 'primary') + '" data-action="toggle-selection" data-entry-type="' + escapeHtml(entry.type) + '" data-path="' + escapeHtml(entry.path) + '">' + (selected ? 'Remove' : 'Select') + '</button>'
          : '')
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
          + '<div class="muted">This title is copied to the queued file entries and becomes the default group title for follow-up working actions.</div>'
          + '</div>'
          + '</article>'
        : '')
      + selections.map(function (entry) {
      var titleSource = this._selectionTitleSource(entry);
      var resolvedTitle = this._resolvedGroupTitle(entry);
      var entryName = String(basename(entry.path) || entry.path);
      var previewMarkup = entry.type === 'file'
        ? this._serverPreviewMarkup(entry.path, entryName)
        : '<div class="entry-thumb placeholder">Folder</div>';
      return ''
        + '<article class="entry-row">'
        + '  <div class="entry-top">' + previewMarkup + '<div><div class="entry-name">' + escapeHtml(entryName) + '</div><div class="entry-path">' + escapeHtml(entry.path) + '</div></div><div class="button-row"><span class="chip">' + escapeHtml(entry.type) + '</span><button class="button warn" data-action="remove-selection" data-path="' + escapeHtml(entry.path) + '">Remove</button></div></div>'
        + (entry.type === 'folder' && showSettings
          ? '<div class="item-grid">'
            + '<div class="field"><label>Folder Scope</label><select class="select" data-action="selection-recurse" data-path="' + escapeHtml(entry.path) + '"><option value="true"' + (entry.recurse ? ' selected' : '') + '>Include subfolders (recursive)</option><option value="false"' + (!entry.recurse ? ' selected' : '') + '>Just this folder</option></select></div>'
            + '<div class="field"><label>Grouping</label><select class="select" data-action="selection-grouping" data-path="' + escapeHtml(entry.path) + '"><option value="none"' + (entry.grouping_strategy === 'none' ? ' selected' : '') + '>None</option><option value="by-folder"' + (entry.grouping_strategy === 'by-folder' ? ' selected' : '') + '>by-folder</option><option value="by-root"' + (entry.grouping_strategy === 'by-root' ? ' selected' : '') + '>by-root</option><option value="flat"' + (entry.grouping_strategy === 'flat' ? ' selected' : '') + '>flat</option></select></div>'
            + (entry.recurse
              ? '<div class="field"><label>Folder Structure</label><select class="select" data-action="selection-preserve-structure" data-path="' + escapeHtml(entry.path) + '"><option value="true"' + (entry.preserve_folder_structure !== false ? ' selected' : '') + '>Preserve</option><option value="false"' + (entry.preserve_folder_structure === false ? ' selected' : '') + '>Flatten</option></select></div>'
              : '')
            + '<div class="field"><label>Title Basis</label><select class="select" data-action="selection-title-source" data-path="' + escapeHtml(entry.path) + '"><option value="folder"' + (titleSource === 'folder' ? ' selected' : '') + '>Folder name</option><option value="first-file"' + (titleSource === 'first-file' ? ' selected' : '') + '>First file</option><option value="custom"' + (titleSource === 'custom' ? ' selected' : '') + '>Custom</option></select></div>'
            + '<div class="field"><label>Working Group Title</label><input class="input" type="text" value="' + escapeHtml(resolvedTitle) + '" data-action="selection-group-title" data-path="' + escapeHtml(entry.path) + '" placeholder="Working Group"></div>'
            + '<div class="muted">This title is preserved into the intake queue and becomes the default when this batch is sent to Working Files.' + (entry.recurse ? ' Folder structure is preserved in Catalog.' : '') + '</div>'
            + '</div>'
          : (entry.type === 'folder'
            ? '<div class="button-row"><span class="chip">scope ' + escapeHtml(entry.recurse ? 'recursive' : 'just this folder') + '</span><span class="chip">' + escapeHtml(entry.grouping_strategy || 'none') + '</span><span class="chip">title ' + escapeHtml(resolvedTitle) + '</span></div>'
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
      + '  <div class="title-row"><div><div class="title">New Intake Batch</div><div class="subtitle">Start one path at a time, review the batch, then commit it into the shared intake queue.</div></div><div class="button-row"><button class="button" data-action="refresh-intake">Refresh</button><button class="button primary" data-action="goto-inbox">Open Job History</button></div></div>'
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
      + '  <div class="title-row"><div><div class="title">Recent Intake Activity</div><div class="subtitle">Latest queue handoffs and validation state from the shared intake contract.</div></div></div>'
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
          + '  <div class="title-row"><div><div class="title">Preview And Group Defaults</div><div class="subtitle">Review the queued entries and edit the default Working Group title before committing the batch.</div></div></div>'
          + (this._browse.parent_path ? '<button class="button" data-action="browse-parent" data-path="' + escapeHtml(this._browse.parent_path) + '">Up</button>' : '')
          + '  <div class="muted">Folder imports keep the title basis and custom title you set here. File rows now request server-side previews for image and 3MF paths when available.</div>'
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
          + '  <div class="muted">Folder imports keep the title basis and custom title you set here. You can still override the title later from Inbox. File rows now request server-side previews for image and 3MF paths when available.</div>'
          + '  <div class="wizard-selection-scroll">' + this._renderServerSelectionRows(true) + '</div>'
          + '</div>';
      }
      return ''
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Choose Commit Mode & Destination</div><div class="subtitle">Select how you want to proceed with these files.</div></div></div>'
        + '  <div class="field"><label><input type="radio" name="commit-mode" value="queue"' + (this._commitMode === 'queue' ? ' checked' : '') + ' data-action="set-commit-mode"> <strong>Queue for Review</strong> - Safe path for careful validation</label></div>'
        + '  <div class="field"><label><input type="radio" name="commit-mode" value="execute_now"' + (this._commitMode === 'execute_now' ? ' checked' : '') + ' data-action="set-commit-mode"> <strong>Execute Now</strong> - Validate and publish directly (power users)</label></div>'
        + (this._commitMode === 'execute_now'
          ? '  <div class="field"><label for="destination-select">Publication Destination</label><select id="destination-select" class="select" data-action="set-destination"><option value="curated"' + (this._destinationChoice === 'curated' ? ' selected' : '') + '>Catalog</option><option value="working"' + (this._destinationChoice === 'working' ? ' selected' : '') + '>Working Files</option></select><div class="muted">Choose where to publish: Catalog is the authoritative library, Working Files are for drafts and projects.</div></div>'
          : '')
        + '  <div class="muted">Queue mode: Items go to Active Queue for verification and grouping review. Execute Now: Skips queue, goes straight to publication if validation passes.</div>'
        + '</div>';
    }

    if (this._wizardStep === 1) {
      return ''
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Choose Local Files Or Folder</div><div class="subtitle">Add files or folders from this device. You can repeat the action and build a staged list before moving on.</div></div><div class="button-row"><button class="button" data-action="choose-browser-files">Add Files</button><button class="button" data-action="choose-browser-folder">Add Folder</button></div></div>'
        + this._renderBrowserSelectionSummary()
        + '  <div class="wizard-selection-scroll">' + this._renderBrowserFileRows(true) + '</div>'
        + '</div>';
    }
    return ''
      + '<div class="wizard-panel">'
      + '  <div class="title-row"><div><div class="title">Choose Commit Mode & Destination</div><div class="subtitle">Select how you want to proceed with these files.</div></div></div>'
      + '  <div class="field"><label><input type="radio" name="commit-mode" value="queue"' + (this._commitMode === 'queue' ? ' checked' : '') + ' data-action="set-commit-mode"> <strong>Queue for Review</strong> - Safe path for careful validation</label></div>'
      + '  <div class="field"><label><input type="radio" name="commit-mode" value="execute_now"' + (this._commitMode === 'execute_now' ? ' checked' : '') + ' data-action="set-commit-mode"> <strong>Execute Now</strong> - Validate and publish directly (power users)</label></div>'
      + (this._commitMode === 'execute_now'
        ? '  <div class="field"><label for="destination-select">Publication Destination</label><select id="destination-select" class="select" data-action="set-destination"><option value="curated"' + (this._destinationChoice === 'curated' ? ' selected' : '') + '>Catalog</option><option value="working"' + (this._destinationChoice === 'working' ? ' selected' : '') + '>Working Files</option></select><div class="muted">Choose where to publish: Catalog is the authoritative library, Working Files are for drafts and projects.</div></div>'
        : '')
      + '  <div class="muted">Queue mode: Items go to Active Queue for verification and grouping review. Execute Now: Skips queue, goes straight to publication if validation passes.</div>'
      + this._renderBrowserSelectionSummary()
      + '</div>';
  }

  _renderWizardFooter() {
    var atFirstStep = this._wizardStep === 1;
    var atLastStep = this._wizardStep === this._wizardStepCount();
    var commitButtonLabel = "Commit Intake Batch";
    if (atLastStep && this._commitMode === 'execute_now') {
      var destination = this._destinationChoice === 'working' ? 'Working Files' : 'Catalog';
      commitButtonLabel = "Validate & Publish to " + destination;
    }
    if (this._loading) {
      commitButtonLabel = "Working...";
    }
    return ''
      + '<div class="wizard-footer">'
      + '  <div class="button-row"><button class="button" data-action="close-wizard"' + (this._loading ? ' disabled' : '') + '>Cancel</button></div>'
      + '  <div class="button-row">'
      + (!atFirstStep ? '<button class="button" data-action="wizard-back"' + (this._loading ? ' disabled' : '') + '>Back</button>' : '')
      + (!atLastStep
        ? '<button class="button primary" data-action="wizard-next"' + (!this._canAdvanceWizard() || this._loading ? ' disabled' : '') + '>Next</button>'
        : '<button class="button primary" data-action="commit-wizard"' + (!this._canAdvanceWizard() || this._loading ? ' disabled' : '') + '>' + commitButtonLabel + '</button>')
      + '  </div>'
      + '</div>';
  }

  _renderBusyState() {
    if (!this._loading || !this._busyState) {
      return '';
    }
    var busy = this._busyState;
    var progressMarkup = '';
    if (busy.mode === 'determinate' && busy.percent != null) {
      progressMarkup = ''
        + '<div class="busy-progress">'
        + '  <div class="busy-progress-track"><div class="busy-progress-fill" style="width:' + String(Math.max(0, Math.min(100, Number(busy.percent || 0)))) + '%"></div></div>'
        + '  <div class="busy-progress-meta">'
        + '    <strong>' + String(Math.max(0, Math.min(100, Number(busy.percent || 0)))) + '%</strong>'
        + (busy.bytes_total ? '<span>' + escapeHtml(formatBytes(busy.bytes_done || 0)) + ' / ' + escapeHtml(formatBytes(busy.bytes_total || 0)) + '</span>' : '')
        + (busy.files_total ? '<span>Files ' + String(busy.files_done || 0) + ' / ' + String(busy.files_total || 0) + '</span>' : '')
        + '  </div>'
        + '</div>';
    }
    return ''
      + '<div class="wizard-busy-shell" aria-live="polite">'
      + '  <div class="wizard-busy-spinner" aria-hidden="true"></div>'
      + '  <div class="wizard-busy-content">'
      + '    <div class="wizard-busy-phase">' + escapeHtml(String(busy.phase || 'Working')) + '</div>'
      + (busy.detail ? '<div class="wizard-busy-detail">' + escapeHtml(String(busy.detail)) + '</div>' : '')
      + progressMarkup
      + '  </div>'
      + '</div>';
  }

  _renderWizard() {
    return ''
      + '<div class="wizard-modal" role="dialog" aria-modal="true" aria-label="' + escapeHtml(this._wizardTitle()) + '">'
      + '  <div class="wizard-backdrop"></div>'
      + '  <div class="wizard-dialog">'
      + '    <div class="wizard-header"><div><div class="title">' + escapeHtml(this._wizardTitle()) + '</div></div></div>'
      + this._renderWizardProgress()
      + (this._error ? '<div class="status error">' + escapeHtml(this._error) + '</div>' : '')
      + (this._status ? '<div class="status">' + escapeHtml(this._status) + '</div>' : '')
      + this._renderBusyState()
      + '    <div class="wizard-body">' + this._renderWizardBody() + '</div>'
      + this._renderWizardFooter()
      + '    <input id="browser-file-input" class="hidden-upload-input" type="file" multiple data-action="browser-files">'
      + '    <input id="browser-folder-input" class="hidden-upload-input" type="file" multiple webkitdirectory directory data-action="browser-folder">'
        + this._renderWizardCloseConfirm()
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
    if (this._loading) {
      return;
    }
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
    if (action === 'dismiss-close-confirm') {
      this._dismissWizardCloseConfirm();
      return;
    }
    if (action === 'confirm-close-wizard') {
      this._closeWizard({ force: true });
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
    if (action === 'remove-browser-file') {
      this._removeBrowserFile(String(target.getAttribute('data-key') || ''));
      return;
    }
    if (action === 'goto-inbox') {
      this._navigateToSection(this._config.inboxSection, '/3d-printing/model-catalog');
    }
  }

  async _handleChange(event) {
    var target = event.target instanceof Element ? event.target : null;
    if (!target) {
      return;
    }
    if (this._loading) {
      return;
    }
    var action = String(target.getAttribute('data-action') || '');
    if (action === 'browser-files' || action === 'browser-folder') {
      await this._appendBrowserFiles(target.files);
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
    if (action === 'browser-preserve-structure') {
      var preserveStructure = String(target.value || 'true').toLowerCase() === 'true';
      this._updateBrowserBatchMeta({
        preserve_folder_structure: preserveStructure,
      });
      this._render();
      return;
    }
    if (action === 'browser-recurse') {
      var browserRecurse = String(target.value || 'true').toLowerCase() === 'true';
      this._updateBrowserBatchMeta({
        recurse: browserRecurse,
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
      var recurseValue = String(target.value) === 'true';
      this._selected = Object.assign({}, this._selected, {
        [path]: Object.assign({}, this._selected[path], {
          recurse: recurseValue,
          preserve_folder_structure: recurseValue ? this._selected[path].preserve_folder_structure !== false : true,
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
    if (action === 'selection-preserve-structure') {
      var preserveValue = String(target.value || 'true').toLowerCase() === 'true';
      this._selected = Object.assign({}, this._selected, {
        [path]: Object.assign({}, this._selected[path], {
          preserve_folder_structure: preserveValue,
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
    if (this._loading) {
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
      + '.entry-thumb{width:56px;height:56px;flex:0 0 56px;border-radius:10px;border:1px solid rgba(148,163,184,0.24);background:rgba(15,23,42,0.24);display:grid;place-items:center;overflow:hidden;color:var(--secondary-text-color);font-size:10px;font-weight:700;text-transform:uppercase;}'
      + '.entry-thumb.placeholder{letter-spacing:.04em;padding:4px;text-align:center;line-height:1.2;}'
      + '.entry-thumb-image{display:block;width:100%;height:100%;object-fit:cover;}'
      + '.wizard-scroll-region{min-height:0;max-height:460px;overflow:auto;padding-right:4px;}'
      + '.wizard-selection-scroll{min-height:0;max-height:460px;overflow:auto;padding-right:4px;}'
      + '.wizard-review-scroll{min-height:0;max-height:420px;overflow:auto;padding-right:4px;}'
      + '.wizard-footer{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding-top:4px;}'
      + '.wizard-close-confirm{position:absolute;inset:0;display:grid;place-items:center;z-index:30;padding:18px;box-sizing:border-box;}'
      + '.wizard-close-confirm-backdrop{position:absolute;inset:0;background:rgba(2,6,23,0.58);}'
      + '.wizard-close-confirm-dialog{position:relative;display:grid;gap:10px;width:min(460px,calc(100% - 20px));max-height:calc(100% - 20px);overflow:auto;padding:18px;border-radius:16px;border:1px solid rgba(148,163,184,0.28);background:var(--card-background-color,rgba(15,23,42,0.98));box-shadow:0 20px 56px rgba(2,6,23,0.45);}'
      + '.wizard-close-confirm-dialog .title{font-size:18px;line-height:1.25;}'
      + '.wizard-close-confirm-actions{justify-content:flex-end;}'
      + '.wizard-busy-shell{display:flex;align-items:flex-start;gap:12px;padding:12px 14px;border-radius:14px;border:1px solid rgba(96,165,250,0.35);background:rgba(30,64,175,0.15);}'
      + '.wizard-busy-spinner{width:18px;height:18px;border-radius:50%;border:2px solid rgba(148,163,184,0.45);border-top-color:rgba(96,165,250,0.95);animation:intakeSpin .9s linear infinite;flex:0 0 18px;margin-top:2px;}'
      + '.wizard-busy-content{display:grid;gap:6px;min-width:0;}'
      + '.wizard-busy-phase{font-size:13px;font-weight:800;line-height:1.25;}'
      + '.wizard-busy-detail{font-size:12px;color:var(--secondary-text-color);overflow-wrap:anywhere;}'
      + '.busy-progress{display:grid;gap:6px;}'
      + '.busy-progress-track{height:8px;border-radius:999px;overflow:hidden;background:rgba(148,163,184,0.24);}'
      + '.busy-progress-fill{height:100%;background:linear-gradient(90deg,rgba(59,130,246,0.95),rgba(56,189,248,0.9));}'
      + '.busy-progress-meta{display:flex;gap:10px;flex-wrap:wrap;font-size:11px;color:var(--secondary-text-color);}'
      + '@keyframes intakeSpin{to{transform:rotate(360deg);}}'
      // Issue #1322 tweaks: hover affordances, right-aligned action buttons, larger summary font, file-type icon, intake path row
      + '.button{transition:background-color .12s ease,border-color .12s ease,filter .12s ease,transform .12s ease;}'
      + '.button:hover:not(:disabled){filter:brightness(1.18);transform:translateY(-1px);background:rgba(148,163,184,0.22);}'
      + '.button.primary:hover:not(:disabled){background:rgba(30,64,175,0.34);}'
      + '.button.warn:hover:not(:disabled){background:rgba(180,83,9,0.32);}'
      + '.button.danger:hover:not(:disabled){background:rgba(153,27,27,0.34);}'
      + '.entry-row .entry-top{align-items:flex-start;}'
      + '.entry-row .entry-main{flex:1 1 auto;min-width:0;text-align:left;display:grid;gap:2px;}'
      + '.entry-row .entry-top > .button-row,.entry-row .entry-top > .entry-type-icon{margin-left:auto;}'
      + '.entry-row .entry-actions{margin-left:auto;justify-content:flex-end;}'
      + '.title-row > .button-row{margin-left:auto;}'
      + '.entry-type-icon{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:8px;color:var(--secondary-text-color);background:rgba(15,23,42,0.18);border:1px solid rgba(148,163,184,0.18);flex:0 0 32px;}'
      + '.entry-type-icon ha-icon{--mdc-icon-size:20px;width:20px;height:20px;}'
      + '.wizard-panel .result-line{font-size:14px;}'
      + '.wizard-panel .result-line strong{font-size:14px;font-weight:800;}'
      + '.wizard-panel .result-line span{font-weight:600;}'
      + '.intake-path-row{display:flex;align-items:center;gap:10px;padding:6px 0;}'
      + '.intake-path-row .intake-path-text{font-size:14px;font-weight:600;color:var(--primary-text-color);overflow-wrap:anywhere;}'
      + '.button.icon-only{min-width:38px;width:38px;padding:0;display:inline-flex;align-items:center;justify-content:center;}'
      + '.button.icon-only ha-icon{--mdc-icon-size:18px;width:18px;height:18px;}'
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
