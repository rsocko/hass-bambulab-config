var intakeShared = window.ModelCatalogIntakeShared || {};
var escapeHtml = intakeShared.escapeHtml;
var basename = intakeShared.basename;
var callServiceWithResponse = intakeShared.callServiceWithResponse;
var fireModelCatalogDataChanged = intakeShared.fireModelCatalogDataChanged;
var postJsonWithAuth = intakeShared.postJsonWithAuth;

var PRINTABLE_EXTENSIONS = {
  '.3mf': true,
  '.stl': true,
  '.step': true,
  '.stp': true,
  '.obj': true,
  '.amf': true,
  '.ply': true,
};

function normalizePath(pathValue) {
  return String(pathValue || '').replace(/\\/g, '/');
}

function fileKind(pathValue) {
  var normalized = normalizePath(pathValue).toLowerCase();
  var dotIndex = normalized.lastIndexOf('.');
  var extension = dotIndex >= 0 ? normalized.slice(dotIndex) : '';
  if (PRINTABLE_EXTENSIONS[extension]) {
    return 'model';
  }
  if (/\.(png|jpg|jpeg|webp|gif|bmp|svg|avif)$/i.test(normalized)) {
    return 'media';
  }
  return 'supporting';
}

function titleForStrategy(card, strategy, key) {
  if (!key || key === '__loose__') {
    return card._wizardMode === 'browser' ? card._browserBatchResolvedTitle() : 'Working Group';
  }
  if (strategy === 'flat') {
    return key;
  }
  return basename(key) || key;
}

function summarizeGroups(groups, strategy) {
  var plannedModels = groups.map(function (group) {
    var modelCount = 0;
    var mediaCount = 0;
    var supportingCount = 0;
    var files = group.files.map(function (entry) {
      var relativePath = normalizePath(entry.relative_path || entry.name || entry.path || '');
      var kind = fileKind(relativePath);
      if (kind === 'model') {
        modelCount += 1;
      } else if (kind === 'media') {
        mediaCount += 1;
      } else {
        supportingCount += 1;
      }
      return {
        relative_path: relativePath,
        filename: basename(relativePath || entry.name || ''),
        kind: kind,
      };
    });
    return {
      title: group.title,
      strategy: group.strategy,
      file_count: files.length,
      model_file_count: modelCount,
      media_file_count: mediaCount,
      supporting_file_count: supportingCount,
      files: files,
    };
  });
  var summary = {
    planned_model_count: plannedModels.length,
    file_count: 0,
    grouping_strategy: strategy,
  };
  plannedModels.forEach(function (model) {
    summary.file_count += Number(model.file_count || 0);
  });
  return { planned_models: plannedModels, summary: summary };
}

function buildBrowserPlanPreview(card) {
  var files = card._filterBrowserFilesForSubmit(card._browserFiles || []);
  if (!files.length) {
    return null;
  }
  var strategy = card._browserGroupingStrategy();
  var groups = [];
  if (strategy === 'by-folder') {
    var folderMap = {};
    files.forEach(function (entry) {
      var relativePath = normalizePath(entry.relative_path || entry.name || '');
      var parts = relativePath.split('/').filter(Boolean);
      var folderKey = parts.length > 1 ? parts.slice(0, -1).join('/') : '__loose__';
      if (!folderMap[folderKey]) {
        folderMap[folderKey] = { title: titleForStrategy(card, strategy, folderKey), strategy: 'by-folder', files: [] };
      }
      folderMap[folderKey].files.push(entry);
    });
    groups = Object.keys(folderMap).sort().map(function (key) { return folderMap[key]; });
  } else if (strategy === 'by-root') {
    var rootMap = {};
    files.forEach(function (entry) {
      var relativePath = normalizePath(entry.relative_path || entry.name || '');
      var parts = relativePath.split('/').filter(Boolean);
      var rootKey = parts.length > 1 ? parts[0] : '__loose__';
      if (!rootMap[rootKey]) {
        rootMap[rootKey] = { title: titleForStrategy(card, strategy, rootKey), strategy: 'by-root', files: [] };
      }
      rootMap[rootKey].files.push(entry);
    });
    groups = Object.keys(rootMap).sort().map(function (key) { return rootMap[key]; });
  } else if (strategy === 'flat') {
    var printable = files.filter(function (entry) { return fileKind(entry.relative_path || entry.name || '') === 'model'; });
    if (printable.length) {
      groups = printable.map(function (entry) {
        var stem = basename(entry.relative_path || entry.name || '').replace(/\.[^.]+$/, '');
        return { title: stem || 'Model', strategy: 'flat', files: [entry] };
      });
      files.forEach(function (entry) {
        if (fileKind(entry.relative_path || entry.name || '') === 'model') {
          return;
        }
        groups[0].files.push(entry);
      });
    } else {
      groups = [{ title: card._browserBatchResolvedTitle(), strategy: 'none', files: files.slice() }];
      strategy = 'none';
    }
  } else {
    groups = [{ title: card._browserBatchResolvedTitle(), strategy: 'none', files: files.slice() }];
    strategy = 'none';
  }
  var preview = summarizeGroups(groups, strategy);
  preview.contract = 'intake-plan.v1alpha1';
  preview.success = true;
  return preview;
}

function renderPlanSummary(card) {
  var preview = card._previewData;
  if (!preview || !preview.planned_models || !preview.planned_models.length) {
    return '<div class="state-row">No planned output yet. Advance to Organize after selecting sources to resolve the model plan.</div>';
  }
  return ''
    + '<div class="result-summary">'
    + '  <div class="result-line"><span>Planned models</span><strong>' + String(preview.summary.planned_model_count || preview.planned_models.length) + '</strong></div>'
    + '  <div class="result-line"><span>Files in batch</span><strong>' + String(preview.summary.file_count || 0) + '</strong></div>'
    + '</div>'
    + '<div class="entries">' + preview.planned_models.map(function (model) {
      var totalFiles = (model.files || []).length;
      var visibleFiles = (model.files || []).slice(0, 4);
      var files = visibleFiles.map(function (entry) {
        return '<div class="entry-path">' + escapeHtml(entry.relative_path || entry.filename || '') + '</div>';
      }).join('');
      if (totalFiles > visibleFiles.length) {
        files += '<div class="entry-path muted">... and ' + String(totalFiles - visibleFiles.length) + ' more files</div>';
      }
      return ''
        + '<article class="entry-row">'
        + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(model.title || 'Model') + '</div><div class="entry-path">' + escapeHtml(card._groupingStrategyLabel ? card._groupingStrategyLabel(model.strategy || 'none') : (model.strategy || 'none')) + '</div></div><div class="button-row"><span class="chip">' + String(model.file_count || 0) + ' files</span></div></div>'
        + files
        + '</article>';
    }).join('') + '</div>';
}

function renderValidationSummary(card) {
  if (!card._validationData) {
    return '<div class="state-row">Run validation to create one prepared upload snapshot that Commit can reuse.</div>';
  }
  var warningText = (card._validationData.warnings || []).map(function (warning) {
    return warning && (warning.message || warning.code) ? (warning.message || warning.code) : String(warning || '');
  }).filter(Boolean).slice(0, 5);
  return ''
    + '<div class="result-summary">'
    + '  <div class="result-line"><span>Prepared upload</span><strong>' + escapeHtml(card._validationData.upload_id || '') + '</strong></div>'
    + '  <div class="result-line"><span>Validation state</span><strong>' + escapeHtml(card._validationData.validation_state || 'unknown') + '</strong></div>'
    + '</div>'
    + (warningText.length ? '<div class="muted">Warnings: ' + escapeHtml(warningText.join('; ')) + '</div>' : '<div class="muted">This prepared upload is reused during Commit so the wizard does not create a duplicate queue item.</div>');
}

(function applyWizardOverrides() {
  var Card = customElements.get('model-catalog-intake-home-card');
  if (!Card || Card.prototype.__wizardStepOverridesApplied) {
    return;
  }
  var proto = Card.prototype;
  proto.__wizardStepOverridesApplied = true;

  var originalOpenWizard = proto._openWizard;
  var originalToggleSelection = proto._toggleSelection;
  var originalRemoveSelection = proto._removeSelection;
  var originalAppendBrowserFiles = proto._appendBrowserFiles;
  var originalRemoveBrowserFile = proto._removeBrowserFile;
  var originalHandleClick = proto._handleClick;
  var originalHandleChange = proto._handleChange;
  var originalHandleInput = proto._handleInput;
  var originalRenderLaunchPad = proto._renderLaunchPad;
  var originalRenderBrowserSelectionSummary = proto._renderBrowserSelectionSummary;
  var originalRenderServerSelectionRows = proto._renderServerSelectionRows;

  proto._wizardStepCount = function () {
    return 5;
  };

  proto._wizardStepLabel = function (stepNumber) {
    if (stepNumber === 1) {
      return 'Source';
    }
    if (stepNumber === 2) {
      return 'Organize';
    }
    if (stepNumber === 3) {
      return 'Choose Destination';
    }
    if (stepNumber === 4) {
      return 'Validate';
    }
    return 'Commit';
  };

  proto._groupingStrategyLabel = function (strategy) {
    var normalized = String(strategy || 'none').trim().toLowerCase();
    if (normalized === 'by-folder') {
      return 'Separate Models By Folder';
    }
    if (normalized === 'flat') {
      return 'Separate Models By File';
    }
    if (normalized === 'by-root') {
      return 'Each Root Folder Becomes A Model';
    }
    return 'Keep Together In Same Model';
  };

  proto._cleanupPolicyFriendlyLabel = function (policy) {
    var normalized = String(policy || 'keep').trim().toLowerCase();
    if (normalized === 'delete_on_verified') {
      return 'Delete Originals After Success';
    }
    if (normalized === 'replace_with_stub') {
      return 'Replace Originals With Stub Marker';
    }
    return 'Keep Originals In Place';
  };

  proto._renderLaunchPad = function () {
    var html = originalRenderLaunchPad.call(this);
    return html
      .replace(
        'Start one path at a time, review the batch, then commit it into the shared intake queue.',
        'Start one path at a time and move through the same shared flow: Source, Organize, Choose Destination, Validate, Commit.'
      )
      .replace(
        'Use the current browser session to add local files or a local folder, keep building the staged list, then review before commit.',
        'Use the current browser session to add local files or a local folder, then follow the shared Source -> Organize -> Choose Destination -> Validate -> Commit flow.'
      )
      .replace(
        ', select files or folders, configure recurse/grouping, then review before commit.',
        ', select files or folders, then follow the same Source -> Organize -> Choose Destination -> Validate -> Commit flow as Browser Upload.'
      );
  };

  proto._browserSelectionCounts = function () {
    var files = this._filterBrowserFilesForSubmit(this._browserFiles || []);
    var folderCount = this._browserTopLevelFolders().length;
    return {
      fileCount: files.length,
      folderCount: folderCount,
    };
  };

  proto._renderBrowserWizardSummary = function (showControls) {
    var counts = this._browserSelectionCounts();
    var fileCount = counts.fileCount;
    var folderCount = counts.folderCount;
    var groupingStrategy = this._browserGroupingStrategy();
    var recurse = this._browserRecurse();
    var titleSource = this._browserBatchTitleSource();
    var resolvedTitle = this._browserBatchResolvedTitle();
    if (!this._browserFiles.length) {
      return '<div class="state-row">No browser files selected yet. Add files or a folder to begin.</div>';
    }
    var titleSourceOptions = folderCount
      ? '<option value="folder"' + (titleSource === 'folder' ? ' selected' : '') + '>Folder name</option><option value="first-file"' + (titleSource === 'first-file' ? ' selected' : '') + '>First file</option><option value="custom"' + (titleSource === 'custom' ? ' selected' : '') + '>Custom</option>'
      : '<option value="first-file"' + (titleSource === 'first-file' ? ' selected' : '') + '>First file</option><option value="custom"' + (titleSource === 'custom' ? ' selected' : '') + '>Custom</option>';
    return ''
      + '<div class="result-summary">'
      + '  <div class="result-line"><span>Source path</span><strong>Browser Upload</strong></div>'
      + '  <div class="result-line"><span>Cleanup policy</span><strong>' + escapeHtml(this._cleanupPolicyFriendlyLabel('delete_on_verified')) + ' (automatic)</strong></div>'
      + '  <div class="result-line"><span>Selected files/folders</span><strong>' + String(fileCount) + ' files, ' + String(folderCount) + ' folders</strong></div>'
      + '  <div class="result-line"><span>Working Group Title</span><strong>' + escapeHtml(resolvedTitle || 'Working Group') + '</strong></div>'
      + '</div>'
      + (showControls
        ? '<div class="item-grid">'
          + (folderCount
            ? '    <div class="field"><label>Folder Scope</label><select class="select" data-action="browser-recurse"><option value="true"' + (recurse ? ' selected' : '') + '>Include subfolders (recursive)</option><option value="false"' + (!recurse ? ' selected' : '') + '>Just this folder</option></select></div>'
            : '')
          + '    <div class="field"><label>Group / Split</label><select class="select" data-action="browser-grouping"><option value="none"' + (groupingStrategy === 'none' ? ' selected' : '') + '>Keep Together In Same Model</option><option value="by-folder"' + (groupingStrategy === 'by-folder' ? ' selected' : '') + '>Separate Models By Folder</option><option value="by-root"' + (groupingStrategy === 'by-root' ? ' selected' : '') + '>Each Root Folder Becomes A Model</option><option value="flat"' + (groupingStrategy === 'flat' ? ' selected' : '') + '>Separate Models By File</option></select></div>'
          + (folderCount && recurse
            ? '    <div class="field"><label>Folder Structure</label><select class="select" data-action="browser-preserve-structure"><option value="true"' + (this._browserFiles[0] && this._browserFiles[0].preserve_folder_structure !== false ? ' selected' : '') + '>Preserve</option><option value="false"' + (this._browserFiles[0] && this._browserFiles[0].preserve_folder_structure === false ? ' selected' : '') + '>Flatten</option></select></div>'
            : '')
          + '    <div class="field"><label>Title Basis</label><select class="select" data-action="browser-title-source">' + titleSourceOptions + '</select></div>'
          + '    <div class="field"><label>Working Group Title</label><input class="input" type="text" value="' + escapeHtml(resolvedTitle) + '" data-action="browser-group-title" placeholder="Working Group"></div>'
          + '  </div><div class="muted">Organize controls how the selected browser files resolve into models. Validation and Commit reuse the resolved plan shown on the right.</div>'
        : '<div class="muted">Move to Organize to choose Group / Split behavior, title handling, and any folder-specific structure options.</div>');
  };

  proto._invalidateWizardArtifacts = function (options) {
    var settings = options || {};
    var uploadId = this._preparedUploadId;
    this._preparedUploadId = null;
    this._validationData = null;
    if (settings.clearPreview !== false) {
      this._previewData = null;
    }
    if (settings.deletePrepared && uploadId && this._hass) {
      callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_delete_intake_upload', {
        upload_id: uploadId,
      }).catch(function () {});
    }
  };

  proto._refreshWizardPreview = async function () {
    if (!this._wizardOpen || this._wizardStep < 2) {
      return;
    }
    if (this._wizardMode === 'browser') {
      this._previewData = buildBrowserPlanPreview(this);
      this._render();
      return;
    }
    var selections = this._serverPayloadSelections('server');
    if (!selections.length) {
      this._previewData = null;
      this._render();
      return;
    }
    try {
      this._previewData = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_plan_intake', {
        source_entries: selections,
      });
    } catch (_error) {
      this._previewData = null;
    }
    this._render();
  };

  proto._prepareWizardUpload = async function (forceNewUpload) {
    if (forceNewUpload) {
      this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: false });
    }
    if (this._preparedUploadId) {
      return { upload_id: this._preparedUploadId, status: 'queued', warnings: [] };
    }
    var sourceMode = this._sourceMode();
    var cleanupPolicy = this._cleanupPolicy();
    var payloadSelections = this._serverPayloadSelections(sourceMode);
    var browserFiles = this._enabledBrowserFiles(sourceMode);
    var response;
    if (browserFiles.length) {
      var sidecarBaseUrl = this._resolveSidecarUrl();
      var encodedBrowserFiles = [];
      for (var index = 0; index < browserFiles.length; index += 1) {
        encodedBrowserFiles.push(await this._encodeBrowserFile(browserFiles[index]));
      }
      response = await postJsonWithAuth(this._hass, sidecarBaseUrl.replace(/\/$/, '') + '/api/intake/uploads/browser', {
        browser_files: encodedBrowserFiles,
        server_selections: payloadSelections,
        cleanup_policy: cleanupPolicy,
      });
    } else {
      response = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_select_source_filesystem_entries', {
        selections: payloadSelections,
        cleanup_policy: cleanupPolicy,
      });
    }
    this._preparedUploadId = response.upload_id;
    return response;
  };

  proto._runWizardValidation = async function (forceNewUpload) {
    if (!this._hass) {
      return null;
    }
    this._loading = true;
    this._error = '';
    this._status = '';
    this._render();
    try {
      var uploadResponse = await this._prepareWizardUpload(forceNewUpload === true);
      var uploadId = uploadResponse.upload_id;
      var validationResponse = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_validate_intake_item', {
        item_id: uploadId,
      });
      var validation = validationResponse.validation || {};
      this._validationData = {
        upload_id: uploadId,
        validation_state: validation.validation_state || 'unknown',
        warnings: (uploadResponse.warnings || []).concat(validation.warnings || []),
      };
      this._status = 'Validation snapshot prepared. Review the outcome, then move to Commit.';
      return this._validationData;
    } catch (error) {
      this._error = error && error.message ? String(error.message) : 'Could not validate the intake batch.';
      return null;
    } finally {
      this._loading = false;
      this._render();
    }
  };

  proto._canAdvanceWizard = function () {
    if (this._wizardStep === 4) {
      return !!(this._validationData && this._validationData.upload_id);
    }
    return this._wizardMode === 'server' ? this._selectedList().length > 0 : this._browserFiles.length > 0;
  };

  proto._goToWizardStep = function (stepNumber) {
    var maxStep = this._wizardStepCount();
    var nextStep = Math.max(1, Math.min(maxStep, Number(stepNumber || 1)));
    if (nextStep > this._wizardStep && !this._canAdvanceWizard()) {
      this._error = this._wizardMode === 'server'
        ? 'Select at least one server file or folder first.'
        : 'Choose at least one browser file or folder first.';
      this._render();
      return;
    }
    this._error = '';
    this._wizardStep = nextStep;
    if (nextStep >= 2) {
      this._refreshWizardPreview();
    }
    this._render();
  };

  proto._openWizard = async function (mode) {
    this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
    return originalOpenWizard.call(this, mode);
  };

  proto._closeWizard = function () {
    this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
    this._wizardOpen = false;
    this._wizardMode = '';
    this._wizardStep = 1;
    this._cleanupPolicyValue = null;
    this._commitMode = 'queue';
    this._destinationChoice = 'curated';
    this._selected = {};
    this._clearBrowserFiles();
    this._render();
  };

  proto._toggleSelection = function (path, entryType) {
    originalToggleSelection.call(this, path, entryType);
    this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
    this._refreshWizardPreview();
  };

  proto._removeSelection = function (path) {
    originalRemoveSelection.call(this, path);
    this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
    this._refreshWizardPreview();
  };

  proto._appendBrowserFiles = function (fileList) {
    originalAppendBrowserFiles.call(this, fileList);
    this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
    this._refreshWizardPreview();
  };

  proto._removeBrowserFile = function (key) {
    originalRemoveBrowserFile.call(this, key);
    this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
    this._refreshWizardPreview();
  };

  proto._renderBrowserSelectionSummary = function () {
    return this._renderBrowserWizardSummary(true);
  };

  proto._renderServerSelectionRows = function (showSettings) {
    var html = originalRenderServerSelectionRows.call(this, showSettings);
    return html
      .replace(/<label>Grouping<\/label>/g, '<label>Group / Split</label>')
      .replace(/>None<\/option>/g, '>Keep Together In Same Model</option>')
      .replace(/>by-folder<\/option>/g, '>Separate Models By Folder</option>')
      .replace(/>by-root<\/option>/g, '>Each Root Folder Becomes A Model</option>')
      .replace(/>flat<\/option>/g, '>Separate Models By File</option>')
      .replace(/Folder structure is preserved in Curated catalog\./g, 'Folder structure is preserved in Curated Catalog.')
        .replace(/This title is copied to the queued file entries and becomes the default group title for follow-up working actions\./g, 'This title is copied to the queued file entries and becomes the default title if the batch later lands in Working Files.');
  };

  proto._renderWizardBody = function () {
    if (this._wizardStep === 1) {
      if (this._wizardMode === 'server') {
        return ''
          + '<div class="wizard-panel">'
          + '  <div class="title-row"><div><div class="title">Choose Server Files And Folders</div><div class="subtitle">Browse allowlisted roots and select the source entries for this intake batch.</div></div>'
          + (this._browse.parent_path ? '<button class="button" data-action="browse-parent" data-path="' + escapeHtml(this._browse.parent_path) + '">Up</button>' : '')
          + '  </div>'
          + '  <div class="muted">Current path: ' + escapeHtml(this._browse.path || '/') + '.</div>'
          + '  <div class="wizard-scroll-region">' + this._renderBrowseEntries() + '</div>'
          + '</div>'
          + '<div class="wizard-panel">'
          + '  <div class="title-row"><div><div class="title">Selected Source Entries</div><div class="subtitle">Move to Organize to define Group / Split rules and titles.</div></div><span class="chip ok">' + String(this._selectedList().length) + ' selected</span></div>'
          + '  <div class="wizard-selection-scroll">' + this._renderServerSelectionRows(false) + '</div>'
          + '</div>';
      }
      return ''
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Choose Local Files Or Folder</div><div class="subtitle">Build the staged upload batch from this browser session.</div></div><div class="button-row"><button class="button" data-action="choose-browser-files">Add Files</button><button class="button" data-action="choose-browser-folder">Add Folder</button><button class="button warn" data-action="clear-browser-files"' + (!this._browserFiles.length ? ' disabled' : '') + '>Clear All</button></div></div>'
        + '  <div class="wizard-selection-scroll">' + this._renderBrowserFileRows(true) + '</div>'
        + '</div>'
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Current Batch</div><div class="subtitle">Organize will resolve how these staged files split into models.</div></div></div>'
        + this._renderBrowserWizardSummary(false)
        + '</div>';
    }
    if (this._wizardStep === 2) {
      return ''
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Organize</div><div class="subtitle">Choose how files stay together or split apart. The right side shows the resolved outcome.</div></div></div>'
        + '  <div class="wizard-selection-scroll">' + (this._wizardMode === 'server' ? this._renderServerSelectionRows(true) : this._renderBrowserWizardSummary(true) + this._renderBrowserFileRows(false)) + '</div>'
        + '</div>'
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Resolved Output</div><div class="subtitle">This is the planned model set that later steps will validate and commit.</div></div></div>'
        + renderPlanSummary(this)
        + '</div>';
    }
    if (this._wizardStep === 3) {
      return ''
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Choose Destination</div><div class="subtitle">Pick whether the validated upload stays in Intake Queue or publishes immediately.</div></div></div>'
        + '  <div class="field"><label><input type="radio" name="commit-mode" value="queue"' + (this._commitMode === 'queue' ? ' checked' : '') + ' data-action="set-commit-mode"> <strong>Queue For Review</strong> - stop after validation and leave the batch in Intake Queue.</label></div>'
        + '  <div class="field"><label><input type="radio" name="commit-mode" value="execute_now"' + (this._commitMode === 'execute_now' ? ' checked' : '') + ' data-action="set-commit-mode"> <strong>Execute Now</strong> - publish immediately when validation is ready.</label></div>'
        + (this._commitMode === 'execute_now'
          ? '  <div class="field"><label for="destination-select">Publish Destination</label><select id="destination-select" class="select" data-action="set-destination"><option value="curated"' + (this._destinationChoice === 'curated' ? ' selected' : '') + '>Curated Catalog</option><option value="working"' + (this._destinationChoice === 'working' ? ' selected' : '') + '>Working Files</option></select></div>'
          : '')
        + '  <div class="field"><label for="wizard-cleanup-policy">Cleanup Policy</label>'
        + (this._wizardMode === 'browser'
          ? '<div class="muted">Browser uploads automatically use ' + escapeHtml(this._cleanupPolicyFriendlyLabel('delete_on_verified')) + '.</div>'
          : '<select id="wizard-cleanup-policy" class="select" data-action="cleanup-policy"><option value="keep"' + (this._cleanupPolicy() === 'keep' ? ' selected' : '') + '>Keep Originals In Place</option><option value="delete_on_verified"' + (this._cleanupPolicy() === 'delete_on_verified' ? ' selected' : '') + '>Delete Originals After Success</option><option value="replace_with_stub"' + (this._cleanupPolicy() === 'replace_with_stub' ? ' selected' : '') + '>Replace Originals With Stub Marker</option></select>')
        + '  </div>'
        + '</div>'
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Resolved Output</div><div class="subtitle">Destination and cleanup choices do not change the model plan shown here.</div></div></div>'
        + renderPlanSummary(this)
        + '</div>';
    }
    if (this._wizardStep === 4) {
      return ''
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Validate</div><div class="subtitle">Create one prepared upload snapshot and verify it before the final commit.</div></div></div>'
        + renderValidationSummary(this)
        + '</div>'
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Resolved Output</div><div class="subtitle">Validation checks the exact planned output shown here.</div></div></div>'
        + renderPlanSummary(this)
        + '</div>';
    }
    return ''
      + '<div class="wizard-panel">'
      + '  <div class="title-row"><div><div class="title">Commit Summary</div><div class="subtitle">Review the prepared upload, destination, and cleanup policy before the final commit.</div></div></div>'
      + renderValidationSummary(this)
      + '</div>'
      + '<div class="wizard-panel">'
      + '  <div class="title-row"><div><div class="title">Resolved Output</div><div class="subtitle">Commit reuses the same prepared upload and resolved plan.</div></div></div>'
      + renderPlanSummary(this)
      + '</div>';
  };

  proto._renderWizardFooter = function () {
    var atFirstStep = this._wizardStep === 1;
    var atLastStep = this._wizardStep === this._wizardStepCount();
    var commitButtonLabel = this._commitMode === 'execute_now'
      ? 'Commit To ' + (this._destinationChoice === 'working' ? 'Working Files' : 'Catalog')
      : 'Commit Intake Batch';
    return ''
      + '<div class="wizard-footer">'
      + '  <div class="button-row"><button class="button" data-action="close-wizard">Cancel</button>'
      + (!atFirstStep ? '<button class="button" data-action="wizard-back">Back</button>' : '')
      + '  </div>'
      + '  <div class="button-row">'
      + (this._wizardStep === 4
        ? '<button class="button primary" data-action="run-wizard-validation"' + (this._loading ? ' disabled' : '') + '>' + (this._validationData ? 'Re-Run Validation' : 'Run Validation') + '</button>' + '<button class="button" data-action="wizard-next"' + (!this._canAdvanceWizard() ? ' disabled' : '') + '>Next</button>'
        : (!atLastStep
          ? '<button class="button primary" data-action="wizard-next"' + (!this._canAdvanceWizard() || this._loading ? ' disabled' : '') + '>Next</button>'
          : '<button class="button primary" data-action="commit-wizard"' + (!this._canAdvanceWizard() || this._loading ? ' disabled' : '') + '>' + commitButtonLabel + '</button>'))
      + '  </div>'
      + '</div>';
  };

  proto._submitServerSelections = async function () {
    if (!this._hass) {
      return;
    }
    this._loading = true;
    this._error = '';
    this._status = '';
    this._result = null;
    this._render();
    try {
      var validationData = this._validationData || await this._runWizardValidation(false);
      if (!validationData || !validationData.upload_id) {
        this._loading = false;
        this._render();
        return;
      }
      var uploadId = validationData.upload_id;
      var publishResponse = null;
      var publishDestination = null;
      if (this._commitMode === 'execute_now' && validationData.validation_state === 'ready') {
        publishDestination = this._destinationChoice || 'curated';
        publishResponse = await callServiceWithResponse(this._hass, 'rest_command', publishDestination === 'working' ? 'model_catalog_publish_to_working' : 'model_catalog_publish_to_local', {
          upload_id: uploadId,
        });
      }
      this._result = {
        upload_id: uploadId,
        upload_status: publishResponse && publishResponse.status ? publishResponse.status : 'validated',
        selection_count: this._wizardMode === 'server' ? this._selectedList().length : this._browserFiles.length,
        expanded_file_count: this._previewData && this._previewData.summary ? this._previewData.summary.file_count : 0,
        validation_state: validationData.validation_state,
        warnings: validationData.warnings || [],
        cleanup_policy: this._wizardMode === 'browser' ? 'delete_on_verified' : this._cleanupPolicy(),
        publish_status: publishResponse && publishResponse.status ? publishResponse.status : null,
        local_model_id: publishResponse && publishResponse.local_model_id ? publishResponse.local_model_id : null,
        working_group_id: publishResponse && publishResponse.working_group_id ? publishResponse.working_group_id : null,
      };
      this._status = this._commitMode === 'execute_now' && publishResponse
        ? 'Validated upload published successfully.'
        : 'Validated upload left in Intake Queue for follow-up review.';
      if (publishResponse) {
        fireModelCatalogDataChanged([publishDestination === 'working' ? 'working' : 'curated'], {
          reason: 'execute-now-publish',
          uploadId: uploadId,
          localModelId: publishResponse.local_model_id || null,
          workingGroupId: publishResponse.working_group_id || null,
        });
      }
      this._preparedUploadId = null;
      this._validationData = null;
      this._previewData = null;
      this._selected = {};
      this._clearBrowserFiles();
      this._wizardOpen = false;
      this._wizardMode = '';
      this._wizardStep = 1;
      this._cleanupPolicyValue = null;
      this._commitMode = 'queue';
      this._destinationChoice = 'curated';
      this._loading = false;
      await this._refreshAll();
    } catch (error) {
      this._error = error && error.message ? String(error.message) : 'Could not commit the intake batch.';
      this._loading = false;
      this._render();
    }
  };

  proto._handleClick = function (event) {
    var target = event.target instanceof Element ? event.target.closest('[data-action]') : null;
    var action = target ? String(target.getAttribute('data-action') || '') : '';
    if (action === 'run-wizard-validation') {
      event.preventDefault();
      this._runWizardValidation(!!this._validationData);
      return;
    }
    if (action === 'clear-browser-files') {
      this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
    }
    originalHandleClick.call(this, event);
  };

  proto._handleChange = function (event) {
    var target = event.target instanceof Element ? event.target : null;
    var action = target ? String(target.getAttribute('data-action') || '') : '';
    originalHandleChange.call(this, event);
    if (/^(browser-|selection-|cleanup-policy$)/.test(action)) {
      this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
      this._refreshWizardPreview();
      return;
    }
    if (action === 'set-commit-mode' || action === 'set-destination') {
      this._validationData = null;
      this._render();
    }
  };

  proto._handleInput = function (event) {
    var target = event.target instanceof Element ? event.target : null;
    var action = target ? String(target.getAttribute('data-action') || '') : '';
    originalHandleInput.call(this, event);
    if (action === 'browser-group-title' || action === 'selection-group-title' || action === 'selection-group-title-files') {
      this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
      if (this._wizardStep > 2) {
        this._refreshWizardPreview();
      }
    }
  };
})();
