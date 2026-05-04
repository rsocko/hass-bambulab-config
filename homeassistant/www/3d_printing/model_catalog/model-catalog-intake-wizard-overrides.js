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

function browserRootKey(relativePath) {
  var parts = normalizePath(relativePath).split('/').filter(Boolean);
  return parts.length > 1 ? parts[0] : '';
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
        var customTitle = String(entry.group_title || '').trim();
        return { title: customTitle || stem || 'Model', strategy: 'flat', files: [entry] };
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
  var checks = Array.isArray(card._validationData.checks) && card._validationData.checks.length
    ? card._validationData.checks
    : [
        {
          key: 'source_access',
          label: 'Selected sources are present and readable',
          passed: ['missing_source', 'source_warning'].indexOf(card._validationData.validation_state) === -1,
          detail: 'Validation resolves the selected files before commit.',
        },
        {
          key: 'supported_types',
          label: 'Resolved files use supported model or image types',
          passed: card._validationData.validation_state !== 'unsupported_type',
          detail: 'Unsupported file types stay visible here instead of failing silently.',
        },
        {
          key: 'duplicate_scan',
          label: 'Resolved files do not match existing working items',
          passed: card._validationData.validation_state !== 'duplicate_candidate',
          detail: 'Duplicate detection compares resolved file hashes against working inventory.',
        },
        {
          key: 'commit_ready',
          label: 'Resolved plan contains at least one file to commit',
          passed: card._validationData.validation_state !== 'needs_manual_grouping',
          detail: 'Validation only advances when the prepared upload resolves into a real file set.',
        },
      ];
  var warningText = (card._validationData.warnings || []).map(function (warning) {
    return warning && (warning.message || warning.code) ? (warning.message || warning.code) : String(warning || '');
  }).filter(Boolean).slice(0, 5);
  return ''
    + '<div class="result-summary">'
    + '  <div class="result-line"><span>Prepared upload</span><strong>' + escapeHtml(card._validationData.upload_id || '') + '</strong></div>'
    + '  <div class="result-line"><span>Validation state</span><strong>' + escapeHtml(card._validationData.validation_state || 'unknown') + '</strong></div>'
    + '</div>'
    + '<div class="entries">' + checks.map(function (check) {
      var passed = !!check.passed;
      return ''
        + '<article class="entry-row">'
        + '  <div class="entry-top"><div><div class="entry-name"><label class="validation-check ' + (passed ? 'pass' : 'fail') + '"><input type="checkbox" disabled' + (passed ? ' checked' : '') + '> ' + escapeHtml(check.label || check.key || 'Check') + '</label></div><div class="entry-path">' + escapeHtml(check.detail || '') + '</div></div><div class="button-row"><span class="chip ' + (passed ? 'ok' : 'warn') + '">' + escapeHtml(passed ? 'pass' : 'attention') + '</span></div></div>'
        + '</article>';
    }).join('') + '</div>'
    + (warningText.length ? '<div class="muted">Warnings: ' + escapeHtml(warningText.join('; ')) + '</div>' : '<div class="muted">This prepared upload is reused during Commit so the wizard does not create a duplicate queue item.</div>');
}

function destinationGroupKey(model, index) {
  var files = model && Array.isArray(model.files) ? model.files : [];
  var firstFile = files.length ? String(files[0].relative_path || files[0].filename || '') : '';
  return [
    String(index),
    String(model && model.title ? model.title : ''),
    String(model && model.strategy ? model.strategy : ''),
    String(model && model.file_count ? model.file_count : files.length),
    firstFile,
  ].join('|');
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
  var originalRender = proto._render;
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

  proto._browserTopFolderNames = function () {
    return this._browserTopLevelFolders();
  };

  proto._browserRootBuckets = function () {
    var buckets = {};
    this._filterBrowserFilesForSubmit(this._browserFiles || []).forEach(function (entry) {
      var rootKey = browserRootKey(entry.relative_path || entry.name || '');
      if (!rootKey) {
        return;
      }
      if (!buckets[rootKey]) {
        buckets[rootKey] = [];
      }
      buckets[rootKey].push(entry);
    });
    return buckets;
  };

  proto._browserLooseFiles = function () {
    return this._filterBrowserFilesForSubmit(this._browserFiles || []).filter(function (entry) {
      return !browserRootKey(entry.relative_path || entry.name || '');
    });
  };

  proto._browserRootTitleSource = function (entry) {
    var normalized = String(entry && entry.group_title_source || '').trim().toLowerCase();
    if (normalized === 'folder' || normalized === 'first-file' || normalized === 'custom') {
      return normalized;
    }
    return 'folder';
  };

  proto._browserRootResolvedTitle = function (rootKey, entry) {
    var explicitTitle = String(entry && entry.group_title || '').trim();
    if (explicitTitle) {
      return explicitTitle;
    }
    if (this._browserRootTitleSource(entry) === 'first-file') {
      return basename(String(entry && (entry.relative_path || entry.name) || '')).replace(/\.[^.]+$/, '') || rootKey || 'Working Group';
    }
    return rootKey || 'Working Group';
  };

  proto._browserLooseTitleSource = function () {
    var files = this._browserLooseFiles();
    if (!files.length) {
      return 'first-file';
    }
    var normalized = String(files[0].group_title_source || '').trim().toLowerCase();
    if (normalized === 'first-file' || normalized === 'custom') {
      return normalized;
    }
    return 'first-file';
  };

  proto._browserLooseResolvedTitle = function () {
    var files = this._browserLooseFiles();
    if (!files.length) {
      return 'Working Group';
    }
    var explicitTitle = String(files[0].group_title || '').trim();
    if (explicitTitle) {
      return explicitTitle;
    }
    return basename(String(files[0].relative_path || files[0].name || '')).replace(/\.[^.]+$/, '') || 'Working Group';
  };

  proto._updateBrowserEntriesWhere = function (predicate, updates) {
    this._browserFiles = this._browserFiles.map(function (entry) {
      if (!predicate(entry)) {
        return entry;
      }
      return Object.assign({}, entry, updates);
    });
  };

  proto._updateBrowserRootMeta = function (rootKey, updates) {
    this._updateBrowserEntriesWhere(function (entry) {
      return browserRootKey(entry.relative_path || entry.name || '') === rootKey;
    }, updates);
  };

  proto._updateBrowserLooseMeta = function (updates) {
    this._updateBrowserEntriesWhere(function (entry) {
      return !browserRootKey(entry.relative_path || entry.name || '');
    }, updates);
  };

  proto._fileBatchGroupingStrategy = function () {
    var fileEntries = this._fileSelectionEntries ? this._fileSelectionEntries() : [];
    if (!fileEntries.length) {
      return 'none';
    }
    var normalized = String(fileEntries[0].grouping_strategy || 'none').trim().toLowerCase();
    return normalized === 'flat' ? 'flat' : 'none';
  };

  proto._renderSharedPerFileNameRows = function (entries, options) {
    var settings = options || {};
    var inputAction = String(settings.inputAction || '');
    var pathAttribute = String(settings.pathAttribute || 'data-path');
    return '<div class="entries">' + (entries || []).filter(function (entry) {
      return fileKind(entry.relative_path || entry.name || entry.path || '') === 'model';
    }).map(function (entry) {
      var entryPath = String(entry.relative_path || entry.name || entry.path || '');
      var defaultTitle = basename(entryPath).replace(/\.[^.]+$/, '') || 'Model';
      var currentTitle = String(entry.group_title || '').trim() || defaultTitle;
      return ''
        + '<article class="entry-row">'
        + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(defaultTitle) + '</div><div class="entry-path">' + escapeHtml(entryPath) + '</div></div><span class="chip">model</span></div>'
        + '  <div class="field"><label>Model Name</label><input class="input" type="text" value="' + escapeHtml(currentTitle) + '" data-action="' + escapeHtml(inputAction) + '" ' + pathAttribute + '="' + escapeHtml(entryPath) + '" placeholder="Model"></div>'
        + '</article>';
    }).join('') + '</div>';
  };

  proto._renderSharedFileBatchCard = function (options) {
    var settings = options || {};
    var entries = settings.entries || [];
    var groupingValue = String(settings.groupingValue || 'none').trim().toLowerCase();
    var titleSource = String(settings.titleSource || 'first-file').trim().toLowerCase();
    var resolvedTitle = String(settings.resolvedTitle || 'Working Group');
    var groupingAction = String(settings.groupingAction || '');
    var titleSourceAction = String(settings.titleSourceAction || '');
    var groupTitleAction = String(settings.groupTitleAction || '');
    var perFileTitleAction = String(settings.perFileTitleAction || '');
    var description = String(settings.description || 'Applies to selected files in this intake batch.');
    var showBatchTitleField = !(groupingValue === 'flat');
    return ''
      + '<article class="entry-row">'
      + '<div class="entry-top"><div><div class="entry-name">Selected Files Batch</div><div class="entry-path">' + escapeHtml(description) + '</div></div><div class="button-row"><span class="chip">' + String(entries.length) + ' files</span></div></div>'
      + '<div class="item-grid">'
      + '<div class="field"><label>Group / Split</label><select class="select" data-action="' + escapeHtml(groupingAction) + '"><option value="none"' + (groupingValue === 'none' ? ' selected' : '') + '>Keep Together In Same Model</option><option value="flat"' + (groupingValue === 'flat' ? ' selected' : '') + '>Separate Models By File</option></select></div>'
      + '<div class="field"><label>Title Basis</label><select class="select" data-action="' + escapeHtml(titleSourceAction) + '"><option value="first-file"' + (titleSource === 'first-file' ? ' selected' : '') + '>First file</option><option value="custom"' + (titleSource === 'custom' ? ' selected' : '') + '>Custom</option></select></div>'
      + (showBatchTitleField
        ? '<div class="field"><label>Working Group Title</label><input class="input" type="text" value="' + escapeHtml(resolvedTitle) + '" data-action="' + escapeHtml(groupTitleAction) + '" placeholder="Working Group"></div>'
        : '')
      + '</div>'
      + (groupingValue === 'flat' && titleSource === 'custom'
        ? '<div class="title-row"><div><div class="title">Per-File Model Names</div><div class="subtitle">Custom names apply to each model created by Separate Models By File.</div></div></div>'
            + this._renderSharedPerFileNameRows(entries, {
              inputAction: perFileTitleAction,
              pathAttribute: settings.perFilePathAttribute || 'data-path',
            })
        : '')
      + '</article>';
  };

  proto._browserFlatCustomTitleRows = function (files) {
    var modelFiles = (files || this._filterBrowserFilesForSubmit(this._browserFiles || [])).filter(function (entry) {
      return fileKind(entry.relative_path || entry.name || '') === 'model';
    });
    if (!modelFiles.length) {
      return '';
    }
    return '<div class="entries">' + modelFiles.map(function (entry) {
      var relativePath = String(entry.relative_path || entry.name || '');
      var defaultTitle = basename(relativePath).replace(/\.[^.]+$/, '') || 'Model';
      var currentTitle = String(entry.group_title || '').trim() || defaultTitle;
      return ''
        + '<article class="entry-row">'
        + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(defaultTitle) + '</div><div class="entry-path">' + escapeHtml(relativePath) + '</div></div><span class="chip">model</span></div>'
        + '  <div class="field"><label>Model Name</label><input class="input" type="text" value="' + escapeHtml(currentTitle) + '" data-action="browser-flat-model-title" data-relative-path="' + escapeHtml(relativePath) + '" placeholder="Model"></div>'
        + '</article>';
    }).join('') + '</div>';
  };

  proto._renderBrowserOrganizeRows = function () {
    var rootBuckets = this._browserRootBuckets();
    var rootKeys = Object.keys(rootBuckets).sort();
    var looseFiles = this._browserLooseFiles();
    var sections = [];
    if (looseFiles.length) {
      sections.push(this._renderSharedFileBatchCard({
        entries: looseFiles,
        groupingValue: String(looseFiles[0].grouping_strategy || 'none').trim().toLowerCase(),
        titleSource: this._browserLooseTitleSource(),
        resolvedTitle: this._browserLooseResolvedTitle(),
        groupingAction: 'browser-loose-grouping',
        titleSourceAction: 'browser-loose-title-source',
        groupTitleAction: 'browser-loose-group-title',
        perFileTitleAction: 'browser-flat-model-title',
        perFilePathAttribute: 'data-relative-path',
        description: 'Applies to individually selected browser files in this intake batch.',
      }));
    }
    rootKeys.forEach(function (rootKey) {
      var files = rootBuckets[rootKey];
      var representative = files[0] || {};
      var groupingStrategy = String(representative.grouping_strategy || 'none').trim().toLowerCase();
      var titleSource = this._browserRootTitleSource(representative);
      var resolvedTitle = this._browserRootResolvedTitle(rootKey, representative);
      sections.push(''
        + '<article class="entry-row">'
        + '<div class="entry-top"><div><div class="entry-name">' + escapeHtml(rootKey) + '</div><div class="entry-path">Folder upload</div></div><div class="button-row"><span class="chip">Folder</span><span class="chip">' + String(files.length) + ' files</span></div></div>'
        + '<div class="item-grid">'
        + '<div class="field"><label>Folder Scope</label><select class="select" data-action="browser-root-recurse" data-root="' + escapeHtml(rootKey) + '"><option value="true"' + (representative.recurse !== false ? ' selected' : '') + '>Include subfolders (recursive)</option><option value="false"' + (representative.recurse === false ? ' selected' : '') + '>Just this folder</option></select></div>'
        + '<div class="field"><label>Group / Split</label><select class="select" data-action="browser-root-grouping" data-root="' + escapeHtml(rootKey) + '"><option value="none"' + (groupingStrategy === 'none' ? ' selected' : '') + '>Keep Together In Same Model</option><option value="by-folder"' + (groupingStrategy === 'by-folder' ? ' selected' : '') + '>Separate Models By Folder</option><option value="by-root"' + (groupingStrategy === 'by-root' ? ' selected' : '') + '>Each Root Folder Becomes A Model</option><option value="flat"' + (groupingStrategy === 'flat' ? ' selected' : '') + '>Separate Models By File</option></select></div>'
        + (representative.recurse !== false ? '<div class="field"><label>Folder Structure</label><select class="select" data-action="browser-root-preserve-structure" data-root="' + escapeHtml(rootKey) + '"><option value="true"' + (representative.preserve_folder_structure !== false ? ' selected' : '') + '>Preserve</option><option value="false"' + (representative.preserve_folder_structure === false ? ' selected' : '') + '>Flatten</option></select></div>' : '')
        + '<div class="field"><label>Title Basis</label><select class="select" data-action="browser-root-title-source" data-root="' + escapeHtml(rootKey) + '"><option value="folder"' + (titleSource === 'folder' ? ' selected' : '') + '>Folder name</option><option value="first-file"' + (titleSource === 'first-file' ? ' selected' : '') + '>First file</option><option value="custom"' + (titleSource === 'custom' ? ' selected' : '') + '>Custom</option></select></div>'
        + '<div class="field"><label>Working Group Title</label><input class="input" type="text" value="' + escapeHtml(resolvedTitle) + '" data-action="browser-root-group-title" data-root="' + escapeHtml(rootKey) + '" placeholder="Working Group"></div>'
        + '<div class="muted">These options apply only to the folder ' + escapeHtml(rootKey) + '.</div>'
        + '</div>'
        + '</article>');
    }, this);
    return sections.length ? '<div class="entries">' + sections.join('') + '</div>' : '<div class="state-row">No browser files selected yet. Add files or a folder to begin.</div>';
  };

  proto._renderBrowserWizardSummary = function (showControls) {
    var counts = this._browserSelectionCounts();
    var fileCount = counts.fileCount;
    var folderCount = counts.folderCount;
    var folderNames = this._browserTopFolderNames();
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
      + (showControls && groupingStrategy !== 'flat'
        ? '  <div class="result-line"><span>Working Group Title</span><strong>' + escapeHtml(resolvedTitle || 'Working Group') + '</strong></div>'
        : '')
      + '</div>'
      + (showControls
        ? '<div class="item-grid">'
          + (folderCount
            ? '    <div class="field"><label>Selected Folder</label><div class="muted">' + escapeHtml(folderCount === 1 ? folderNames[0] : String(folderCount) + ' folders selected') + '</div></div><div class="field"><label>Folder Scope</label><select class="select" data-action="browser-recurse"><option value="true"' + (recurse ? ' selected' : '') + '>Include subfolders (recursive)</option><option value="false"' + (!recurse ? ' selected' : '') + '>Just this folder</option></select></div>'
            : '')
          + '    <div class="field"><label>Group / Split</label><select class="select" data-action="browser-grouping"><option value="none"' + (groupingStrategy === 'none' ? ' selected' : '') + '>Keep Together In Same Model</option><option value="by-folder"' + (groupingStrategy === 'by-folder' ? ' selected' : '') + '>Separate Models By Folder</option><option value="by-root"' + (groupingStrategy === 'by-root' ? ' selected' : '') + '>Each Root Folder Becomes A Model</option><option value="flat"' + (groupingStrategy === 'flat' ? ' selected' : '') + '>Separate Models By File</option></select></div>'
          + (folderCount && recurse
            ? '    <div class="field"><label>Folder Structure</label><select class="select" data-action="browser-preserve-structure"><option value="true"' + (this._browserFiles[0] && this._browserFiles[0].preserve_folder_structure !== false ? ' selected' : '') + '>Preserve</option><option value="false"' + (this._browserFiles[0] && this._browserFiles[0].preserve_folder_structure === false ? ' selected' : '') + '>Flatten</option></select></div>'
            : '')
          + '    <div class="field"><label>Title Basis</label><select class="select" data-action="browser-title-source">' + titleSourceOptions + '</select></div>'
          + (groupingStrategy !== 'flat'
            ? '    <div class="field"><label>Working Group Title</label><input class="input" type="text" value="' + escapeHtml(resolvedTitle) + '" data-action="browser-group-title" placeholder="Working Group"></div>'
            : '')
          + '  </div>'
          + ((groupingStrategy === 'flat' && titleSource === 'custom')
            ? '<div class="title-row"><div><div class="title">Per-File Model Names</div><div class="subtitle">Custom names apply to each model created by Separate Models By File.</div></div></div>' + this._browserFlatCustomTitleRows()
            : '')
          + '<div class="muted">Organize controls how the selected browser files resolve into models. Validation and Commit reuse the resolved plan shown on the right.</div>'
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
      this._syncGroupDestinationsFromPreview();
      this._render();
      return;
    }
    var selections = this._serverPayloadSelections('server');
    if (!selections.length) {
      this._previewData = null;
      this._groupDestinations = [];
      this._render();
      return;
    }
    try {
      this._previewData = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_plan_intake', {
        source_entries: selections,
      });
      this._syncGroupDestinationsFromPreview();
    } catch (_error) {
      this._previewData = null;
      this._groupDestinations = [];
    }
    this._render();
  };

  proto._syncGroupDestinationsFromPreview = function () {
    var plannedModels = this._previewData && Array.isArray(this._previewData.planned_models)
      ? this._previewData.planned_models
      : [];
    var existingPlans = Array.isArray(this._groupDestinations) ? this._groupDestinations : [];
    var nextPlans = [];
    for (var index = 0; index < plannedModels.length; index += 1) {
      var model = plannedModels[index] || {};
      var groupKey = destinationGroupKey(model, index);
      var previous = null;
      for (var existingIndex = 0; existingIndex < existingPlans.length; existingIndex += 1) {
        if (existingPlans[existingIndex] && existingPlans[existingIndex]._group_key === groupKey) {
          previous = existingPlans[existingIndex];
          break;
        }
      }
      nextPlans.push(Object.assign({
        _group_key: groupKey,
        destination: 'curated',
        match_mode: 'new',
        model_ref: '',
        working_group_id: null,
        lookup_query: '',
        lookup_results: [],
        lookup_loading: false,
        lookup_error: '',
        selected_summary: null,
      }, previous || {}, {
        _group_key: groupKey,
      }));
    }
    this._groupDestinations = nextPlans;
    return nextPlans;
  };

  proto._updateGroupDestinationState = function (groupIndex, updates) {
    var plans = this._syncGroupDestinationsFromPreview();
    if (groupIndex < 0 || groupIndex >= plans.length) {
      return null;
    }
    var nextPlan = Object.assign({}, plans[groupIndex], updates || {});
    this._groupDestinations = plans.slice();
    this._groupDestinations[groupIndex] = nextPlan;
    return nextPlan;
  };

  proto._destinationPlansReady = function () {
    var plans = this._syncGroupDestinationsFromPreview();
    if (!plans.length) {
      return false;
    }
    for (var index = 0; index < plans.length; index += 1) {
      var plan = plans[index] || {};
      var destination = String(plan.destination || 'curated').trim().toLowerCase();
      var matchMode = String(plan.match_mode || 'new').trim().toLowerCase();
      if (destination !== 'curated' && destination !== 'working') {
        return false;
      }
      if (matchMode === 'existing') {
        if (destination === 'working') {
          if (!(Number(plan.working_group_id) > 0)) {
            return false;
          }
        } else if (!String(plan.model_ref || '').trim()) {
          return false;
        }
      }
    }
    return true;
  };

  proto._buildDestinationPublishPayload = function () {
    var plans = this._syncGroupDestinationsFromPreview();
    return plans.map(function (plan) {
      var payload = {
        destination: String(plan.destination || 'curated').trim().toLowerCase(),
        match_mode: String(plan.match_mode || 'new').trim().toLowerCase(),
      };
      if (payload.match_mode === 'existing') {
        if (payload.destination === 'working') {
          payload.working_group_id = Number(plan.working_group_id || 0);
        } else {
          payload.model_ref = String(plan.model_ref || '').trim();
        }
      }
      return payload;
    });
  };

  proto._destinationSelectionSummary = function (plan) {
    var destination = String(plan && plan.destination ? plan.destination : 'curated').trim().toLowerCase();
    var matchMode = String(plan && plan.match_mode ? plan.match_mode : 'new').trim().toLowerCase();
    var selected = plan && plan.selected_summary ? plan.selected_summary : null;
    if (matchMode !== 'existing') {
      return destination === 'working'
        ? 'Create a new Working Files group.'
        : 'Create a new Curated Catalog model.';
    }
    if (selected) {
      return String(selected.primary || '') + (selected.secondary ? ' - ' + String(selected.secondary) : '');
    }
    return destination === 'working'
      ? 'Select an existing Working Files group.'
      : 'Select an existing Curated Catalog model.';
  };

  proto._curatedLookupResultMeta = function (result) {
    var primary = String((result && (result.name || result.title || result.public_id || result.model_id || result.model_ref)) || 'Catalog Model').trim();
    var idValue = String((result && (result.public_id || result.model_id || result.model_ref || result.id)) || '').trim();
    var creatorNames = Array.isArray(result && result.creator_names) ? result.creator_names.filter(Boolean).join(', ') : '';
    var collections = Array.isArray(result && result.collection_names) ? result.collection_names.filter(Boolean).join(', ') : '';
    return {
      id: idValue,
      primary: primary,
      secondary: creatorNames || collections || idValue,
    };
  };

  proto._workingLookupResultMeta = function (result) {
    var project = result && result.project && result.project.title ? String(result.project.title) : '';
    var itemCount = Array.isArray(result && result.items) ? result.items.length : 0;
    return {
      id: String(result && result.id ? result.id : '').trim(),
      primary: String((result && result.title) || 'Working Group').trim(),
      secondary: [
        result && result.stage ? String(result.stage) : '',
        project,
        itemCount ? String(itemCount) + ' items' : '',
      ].filter(Boolean).join(' - '),
    };
  };

  proto._runGroupDestinationLookup = async function (groupIndex) {
    if (!this._hass) {
      return;
    }
    var plans = this._syncGroupDestinationsFromPreview();
    if (groupIndex < 0 || groupIndex >= plans.length) {
      return;
    }
    var plan = plans[groupIndex] || {};
    var query = String(plan.lookup_query || '').trim();
    if (!query) {
      this._updateGroupDestinationState(groupIndex, {
        lookup_results: [],
        lookup_error: '',
        lookup_loading: false,
      });
      this._render();
      return;
    }
    this._updateGroupDestinationState(groupIndex, {
      lookup_loading: true,
      lookup_error: '',
      lookup_results: [],
    });
    this._render();
    try {
      var response;
      if (String(plan.destination || 'curated') === 'working') {
        response = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_list_working_groups', {
          q: query,
          limit: 8,
          offset: 0,
        });
        this._updateGroupDestinationState(groupIndex, {
          lookup_loading: false,
          lookup_error: '',
          lookup_results: Array.isArray(response && response.groups) ? response.groups : [],
        });
      } else {
        response = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_search_models', {
          q: query,
          page: 1,
          per_page: 8,
        });
        this._updateGroupDestinationState(groupIndex, {
          lookup_loading: false,
          lookup_error: '',
          lookup_results: Array.isArray(response && response.results) ? response.results : [],
        });
      }
    } catch (error) {
      this._updateGroupDestinationState(groupIndex, {
        lookup_loading: false,
        lookup_error: error && error.message ? String(error.message) : 'Could not search existing destinations.',
        lookup_results: [],
      });
    }
    this._render();
  };

  proto._selectGroupDestinationResult = function (groupIndex, resultIndex) {
    var plans = this._syncGroupDestinationsFromPreview();
    if (groupIndex < 0 || groupIndex >= plans.length) {
      return;
    }
    var plan = plans[groupIndex] || {};
    var results = Array.isArray(plan.lookup_results) ? plan.lookup_results : [];
    if (resultIndex < 0 || resultIndex >= results.length) {
      return;
    }
    var result = results[resultIndex];
    if (String(plan.destination || 'curated') === 'working') {
      var workingMeta = this._workingLookupResultMeta(result);
      this._updateGroupDestinationState(groupIndex, {
        working_group_id: Number(workingMeta.id || 0),
        model_ref: '',
        selected_summary: workingMeta,
      });
    } else {
      var curatedMeta = this._curatedLookupResultMeta(result);
      this._updateGroupDestinationState(groupIndex, {
        model_ref: curatedMeta.id,
        working_group_id: null,
        selected_summary: curatedMeta,
      });
    }
    this._render();
  };

  proto._renderDestinationAssignments = function () {
    var plannedModels = this._previewData && Array.isArray(this._previewData.planned_models)
      ? this._previewData.planned_models
      : [];
    var plans = this._syncGroupDestinationsFromPreview();
    if (!plannedModels.length) {
      return '<div class="state-row">No planned groups available yet. Return to Organize to resolve the model plan first.</div>';
    }
    return '<div class="entries">' + plannedModels.map(function (model, index) {
      var plan = plans[index] || {};
      var destination = String(plan.destination || 'curated');
      var matchMode = String(plan.match_mode || 'new');
      var isWorking = destination === 'working';
      var resultRows = '';
      if (matchMode === 'existing') {
        if (plan.lookup_loading) {
          resultRows = '<div class="muted">Searching existing ' + escapeHtml(isWorking ? 'Working Files groups' : 'Curated Catalog models') + '...</div>';
        } else if (plan.lookup_error) {
          resultRows = '<div class="muted">' + escapeHtml(plan.lookup_error) + '</div>';
        } else if (Array.isArray(plan.lookup_results) && plan.lookup_results.length) {
          resultRows = '<div class="entries">' + plan.lookup_results.map(function (result, resultIndex) {
            var meta = isWorking ? this._workingLookupResultMeta(result) : this._curatedLookupResultMeta(result);
            var isSelected = isWorking
              ? Number(plan.working_group_id || 0) === Number(meta.id || 0)
              : String(plan.model_ref || '') === String(meta.id || '');
            return ''
              + '<article class="entry-row">'
              + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(meta.primary) + '</div><div class="entry-path">' + escapeHtml(meta.secondary || '') + '</div></div><div class="button-row"><button class="button' + (isSelected ? ' primary' : '') + '" data-action="select-destination-result" data-group-index="' + String(index) + '" data-result-index="' + String(resultIndex) + '">' + (isSelected ? 'Selected' : 'Use This') + '</button></div></div>'
              + '</article>';
          }, this).join('') + '</div>';
        } else if (String(plan.lookup_query || '').trim()) {
          resultRows = '<div class="muted">No matches found yet for this search.</div>';
        }
      }
      return ''
        + '<article class="entry-row">'
        + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(model.title || ('Group ' + String(index + 1))) + '</div><div class="entry-path">' + String(model.file_count || 0) + ' files - ' + String(model.model_file_count || 0) + ' model, ' + String(model.media_file_count || 0) + ' media, ' + String(model.supporting_file_count || 0) + ' supporting</div></div><div class="button-row"><span class="chip">' + escapeHtml(model.strategy || 'none') + '</span></div></div>'
        + '  <div class="item-grid">'
        + '    <div class="field"><label>Destination</label><select class="select" data-action="group-destination" data-group-index="' + String(index) + '"><option value="curated"' + (destination === 'curated' ? ' selected' : '') + '>Curated Catalog</option><option value="working"' + (destination === 'working' ? ' selected' : '') + '>Working Files</option></select></div>'
        + '    <div class="field"><label>Mode</label><select class="select" data-action="group-match-mode" data-group-index="' + String(index) + '"><option value="new"' + (matchMode === 'new' ? ' selected' : '') + '>New</option><option value="existing"' + (matchMode === 'existing' ? ' selected' : '') + '>Add To Existing</option></select></div>'
        + '    <div class="field"><label>Selection</label><div class="muted">' + escapeHtml(this._destinationSelectionSummary(plan)) + '</div></div>'
        + '  </div>'
        + (matchMode === 'existing'
          ? '  <div class="item-grid">'
            + '    <div class="field"><label>' + escapeHtml(isWorking ? 'Find Working Group' : 'Find Catalog Model') + '</label><input class="input" type="text" value="' + escapeHtml(plan.lookup_query || '') + '" data-action="group-lookup-query" data-group-index="' + String(index) + '" placeholder="Search by name or id"></div>'
            + '    <div class="field"><label>&nbsp;</label><button class="button" data-action="run-destination-search" data-group-index="' + String(index) + '"' + (plan.lookup_loading ? ' disabled' : '') + '>Search</button></div>'
            + '  </div>'
            + resultRows
          : '<div class="muted">This group will create a new ' + escapeHtml(isWorking ? 'Working Files group.' : 'Curated Catalog model.') + '</div>')
        + '</article>';
    }, this).join('') + '</div>';
  };

  proto._renderDestinationSummary = function () {
    var plannedModels = this._previewData && Array.isArray(this._previewData.planned_models)
      ? this._previewData.planned_models
      : [];
    var plans = this._syncGroupDestinationsFromPreview();
    if (!plannedModels.length) {
      return '<div class="state-row">No destination assignments yet.</div>';
    }
    return '<div class="entries">' + plannedModels.map(function (model, index) {
      var plan = plans[index] || {};
      var destination = String(plan.destination || 'curated') === 'working' ? 'Working Files' : 'Curated Catalog';
      var matchMode = String(plan.match_mode || 'new') === 'existing' ? 'Add To Existing' : 'New';
      return ''
        + '<article class="entry-row">'
        + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(model.title || ('Group ' + String(index + 1))) + '</div><div class="entry-path">' + escapeHtml(this._destinationSelectionSummary(plan)) + '</div></div><div class="button-row"><span class="chip">' + escapeHtml(destination) + '</span><span class="chip">' + escapeHtml(matchMode) + '</span></div></div>'
        + '</article>';
    }, this).join('') + '</div>';
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
        checks: Array.isArray(validation.checks) ? validation.checks : [],
      };
      this._status = this._validationData.validation_state === 'ready'
        ? 'Validation snapshot prepared. Review the destination assignments, then commit.'
        : 'Validation finished with blockers. Resolve them before commit.';
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
    if (this._wizardStep === 3) {
      return this._destinationPlansReady();
    }
    if (this._wizardStep === 4) {
      return !!(this._validationData && this._validationData.upload_id && this._validationData.validation_state === 'ready');
    }
    if (this._wizardStep === 5) {
      return this._destinationPlansReady() && !!(this._validationData && this._validationData.upload_id && this._validationData.validation_state === 'ready');
    }
    return this._wizardMode === 'server' ? this._selectedList().length > 0 : this._browserFiles.length > 0;
  };

  proto._goToWizardStep = function (stepNumber) {
    var maxStep = this._wizardStepCount();
    var nextStep = Math.max(1, Math.min(maxStep, Number(stepNumber || 1)));
    if (nextStep > this._wizardStep && !this._canAdvanceWizard()) {
      if (this._wizardStep === 3) {
        this._error = 'Choose a destination for every planned group. Existing matches require a selected target.';
      } else if (this._wizardStep === 4) {
        this._error = this._validationData && this._validationData.upload_id
          ? 'Validation must be ready before commit.'
          : 'Run validation before continuing.';
      } else {
        this._error = this._wizardMode === 'server'
          ? 'Select at least one server file or folder first.'
          : 'Choose at least one browser file or folder first.';
      }
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
    this._groupDestinations = [];
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
    if (!showSettings) {
      var html = originalRenderServerSelectionRows.call(this, showSettings);
      return html
        .replace(/<label>Grouping<\/label>/g, '<label>Group \/ Split<\/label>')
        .replace(/>None<\/option>/g, '>Keep Together In Same Model</option>')
        .replace(/>by-folder<\/option>/g, '>Separate Models By Folder</option>')
        .replace(/>by-root<\/option>/g, '>Each Root Folder Becomes A Model</option>')
        .replace(/>flat<\/option>/g, '>Separate Models By File</option>')
        .replace(/Folder structure is preserved in Curated catalog\./g, 'Folder structure is preserved in Curated Catalog.')
        .replace(/This title is copied to the queued file entries and becomes the default group title for follow-up working actions\./g, 'This title is copied to the queued file entries and becomes the default title if the batch later lands in Working Files.');
    }
    var selections = this._selectedList();
    var fileEntries = this._fileSelectionEntries();
    var fileBatchTitleSource = this._fileBatchTitleSource();
    var fileBatchResolvedTitle = this._fileBatchResolvedTitle();
    var fileBatchGrouping = this._fileBatchGroupingStrategy();
    if (!selections.length) {
      return '<div class="state-row">No server files or folders selected yet.</div>';
    }
    return '<div class="entries">'
      + (fileEntries.length
        ? this._renderSharedFileBatchCard({
            entries: fileEntries,
            groupingValue: fileBatchGrouping,
            titleSource: fileBatchTitleSource,
            resolvedTitle: fileBatchResolvedTitle,
            groupingAction: 'selection-grouping-files',
            titleSourceAction: 'selection-title-source-files',
            groupTitleAction: 'selection-group-title-files',
            perFileTitleAction: 'selection-file-model-title',
            perFilePathAttribute: 'data-path',
            description: 'Applies to all individually selected server files in this intake batch.',
          })
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
          + (entry.type === 'folder'
            ? '<div class="item-grid">'
              + '<div class="field"><label>Folder Scope</label><select class="select" data-action="selection-recurse" data-path="' + escapeHtml(entry.path) + '"><option value="true"' + (entry.recurse ? ' selected' : '') + '>Include subfolders (recursive)</option><option value="false"' + (!entry.recurse ? ' selected' : '') + '>Just this folder</option></select></div>'
              + '<div class="field"><label>Group / Split</label><select class="select" data-action="selection-grouping" data-path="' + escapeHtml(entry.path) + '"><option value="none"' + (entry.grouping_strategy === 'none' ? ' selected' : '') + '>Keep Together In Same Model</option><option value="by-folder"' + (entry.grouping_strategy === 'by-folder' ? ' selected' : '') + '>Separate Models By Folder</option><option value="by-root"' + (entry.grouping_strategy === 'by-root' ? ' selected' : '') + '>Each Root Folder Becomes A Model</option><option value="flat"' + (entry.grouping_strategy === 'flat' ? ' selected' : '') + '>Separate Models By File</option></select></div>'
              + (entry.recurse
                ? '<div class="field"><label>Folder Structure</label><select class="select" data-action="selection-preserve-structure" data-path="' + escapeHtml(entry.path) + '"><option value="true"' + (entry.preserve_folder_structure !== false ? ' selected' : '') + '>Preserve</option><option value="false"' + (entry.preserve_folder_structure === false ? ' selected' : '') + '>Flatten</option></select></div>'
                : '')
              + '<div class="field"><label>Title Basis</label><select class="select" data-action="selection-title-source" data-path="' + escapeHtml(entry.path) + '"><option value="folder"' + (titleSource === 'folder' ? ' selected' : '') + '>Folder name</option><option value="first-file"' + (titleSource === 'first-file' ? ' selected' : '') + '>First file</option><option value="custom"' + (titleSource === 'custom' ? ' selected' : '') + '>Custom</option></select></div>'
              + '<div class="field"><label>Working Group Title</label><input class="input" type="text" value="' + escapeHtml(resolvedTitle) + '" data-action="selection-group-title" data-path="' + escapeHtml(entry.path) + '" placeholder="Working Group"></div>'
              + '<div class="muted">This title is preserved into the intake queue and becomes the default when this batch is sent to Working Files.' + (entry.recurse ? ' Folder structure is preserved in Curated Catalog.' : '') + '</div>'
              + '</div>'
            : '<div class="button-row"><span class="chip">title ' + escapeHtml(resolvedTitle) + '</span><span class="chip">' + escapeHtml(fileBatchGrouping === 'flat' ? 'separate model' : 'same model batch') + '</span></div>')
          + '</article>';
      }, this).join('') + '</div>';
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
        + '  <div class="wizard-selection-scroll">' + (this._wizardMode === 'server' ? this._renderServerSelectionRows(true) : this._renderBrowserOrganizeRows()) + '</div>'
        + '</div>'
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Resolved Output</div><div class="subtitle">This is the planned model set that later steps will validate and commit.</div></div></div>'
        + renderPlanSummary(this)
        + '</div>';
    }
    if (this._wizardStep === 3) {
      return ''
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Pick Destination</div><div class="subtitle">Choose Curated Catalog or Working Files for each planned group. Organize stays fixed here.</div></div></div>'
        + '  <div class="wizard-selection-scroll">' + this._renderDestinationAssignments() + '</div>'
        + '</div>'
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Assignment Summary</div><div class="subtitle">Each planned group keeps its structure and only changes destination.</div></div></div>'
        + '  <div class="wizard-selection-scroll">' + this._renderDestinationSummary() + '</div>'
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
      + '  <div class="title-row"><div><div class="title">Commit Summary</div><div class="subtitle">Review the prepared upload, cleanup policy, and destination assignments before the final publish.</div></div></div>'
      + renderValidationSummary(this)
      + '  <div class="field"><label for="wizard-cleanup-policy">Cleanup Policy</label>'
      + (this._wizardMode === 'browser'
        ? '<div class="muted">Browser uploads automatically use ' + escapeHtml(this._cleanupPolicyFriendlyLabel('delete_on_verified')) + '.</div>'
        : '<select id="wizard-cleanup-policy" class="select" data-action="cleanup-policy"><option value="keep"' + (this._cleanupPolicy() === 'keep' ? ' selected' : '') + '>Keep Originals In Place</option><option value="delete_on_verified"' + (this._cleanupPolicy() === 'delete_on_verified' ? ' selected' : '') + '>Delete Originals After Success</option><option value="replace_with_stub"' + (this._cleanupPolicy() === 'replace_with_stub' ? ' selected' : '') + '>Replace Originals With Stub Marker</option></select>')
      + '  </div>'
      + this._renderDestinationSummary()
      + '</div>'
      + '<div class="wizard-panel">'
      + '  <div class="title-row"><div><div class="title">Resolved Output</div><div class="subtitle">Commit reuses the same prepared upload and resolved plan.</div></div></div>'
      + renderPlanSummary(this)
      + '</div>';
  };

  proto._renderWizardFooter = function () {
    var atFirstStep = this._wizardStep === 1;
    var atLastStep = this._wizardStep === this._wizardStepCount();
    var commitButtonLabel = 'Publish Destinations';
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
      if (validationData.validation_state !== 'ready') {
        throw new Error('Validation must be ready before commit.');
      }
      if (!this._destinationPlansReady()) {
        throw new Error('Choose a destination for every planned group before commit.');
      }
      var uploadId = validationData.upload_id;
      var sidecarBaseUrl = this._resolveSidecarUrl();
      var publishResponse = await postJsonWithAuth(this._hass, sidecarBaseUrl.replace(/\/$/, '') + '/api/intake/uploads/' + encodeURIComponent(String(uploadId || '')) + '/publish-by-destination', {
        group_destinations: this._buildDestinationPublishPayload(),
      });
      var changedCollections = [];
      if (Array.isArray(publishResponse && publishResponse.curated_model_ids) && publishResponse.curated_model_ids.length) {
        changedCollections.push('curated');
      }
      if (Array.isArray(publishResponse && publishResponse.working_group_ids) && publishResponse.working_group_ids.length) {
        changedCollections.push('working');
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
        curated_model_ids: publishResponse && Array.isArray(publishResponse.curated_model_ids) ? publishResponse.curated_model_ids : [],
        working_group_ids: publishResponse && Array.isArray(publishResponse.working_group_ids) ? publishResponse.working_group_ids : [],
        group_results: publishResponse && Array.isArray(publishResponse.group_results) ? publishResponse.group_results : [],
      };
      this._status = 'Validated upload published successfully.';
      if (publishResponse && changedCollections.length) {
        fireModelCatalogDataChanged(changedCollections, {
          reason: 'publish-by-destination',
          uploadId: uploadId,
          curatedModelIds: publishResponse.curated_model_ids || [],
          workingGroupIds: publishResponse.working_group_ids || [],
        });
      }
      this._preparedUploadId = null;
      this._validationData = null;
      this._previewData = null;
      this._groupDestinations = [];
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
    if (action === 'run-destination-search') {
      event.preventDefault();
      this._runGroupDestinationLookup(Number(target.getAttribute('data-group-index') || -1));
      return;
    }
    if (action === 'select-destination-result') {
      event.preventDefault();
      this._selectGroupDestinationResult(
        Number(target.getAttribute('data-group-index') || -1),
        Number(target.getAttribute('data-result-index') || -1)
      );
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
    if (action === 'selection-title-source-files') {
      this._updateSelectedFileBatchMeta({
        group_title_source: String(target.value || 'first-file').trim(),
        group_title: '',
      });
      this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
      this._refreshWizardPreview();
      this._render();
      return;
    }
    if (action === 'selection-grouping-files') {
      var groupingValue = String(target.value || 'none').trim().toLowerCase();
      this._updateSelectedFileBatchMeta({
        grouping_strategy: groupingValue,
        group_title_source: groupingValue === 'flat' ? 'first-file' : this._fileBatchTitleSource(),
        group_title: '',
      });
      this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
      this._refreshWizardPreview();
      return;
    }
    if (action === 'browser-loose-grouping') {
      var looseGrouping = String(target.value || 'none').trim();
      this._updateBrowserLooseMeta({
        grouping_strategy: looseGrouping,
        group_title_source: looseGrouping === 'flat' ? 'first-file' : this._browserLooseTitleSource(),
        group_title: '',
      });
      this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
      this._refreshWizardPreview();
      return;
    }
    if (action === 'browser-loose-title-source') {
      this._updateBrowserLooseMeta({
        group_title_source: String(target.value || 'first-file').trim(),
        group_title: '',
      });
      this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
      this._refreshWizardPreview();
      return;
    }
    if (action === 'browser-root-recurse' || action === 'browser-root-grouping' || action === 'browser-root-preserve-structure' || action === 'browser-root-title-source') {
      var rootKey = String(target.getAttribute('data-root') || '');
      if (!rootKey) {
        return;
      }
      var rootUpdates = {};
      if (action === 'browser-root-recurse') {
        rootUpdates.recurse = String(target.value || 'true').toLowerCase() === 'true';
      } else if (action === 'browser-root-grouping') {
        rootUpdates.grouping_strategy = String(target.value || 'none').trim();
        rootUpdates.group_title_source = rootUpdates.grouping_strategy === 'flat' ? 'first-file' : this._browserRootTitleSource((this._browserRootBuckets()[rootKey] || [])[0] || {});
        rootUpdates.group_title = '';
      } else if (action === 'browser-root-preserve-structure') {
        rootUpdates.preserve_folder_structure = String(target.value || 'true').toLowerCase() === 'true';
      } else if (action === 'browser-root-title-source') {
        rootUpdates.group_title_source = String(target.value || 'folder').trim();
        rootUpdates.group_title = '';
      }
      this._updateBrowserRootMeta(rootKey, rootUpdates);
      this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
      this._refreshWizardPreview();
      return;
    }
    if (action === 'group-destination') {
      var destinationIndex = Number(target.getAttribute('data-group-index') || -1);
      this._updateGroupDestinationState(destinationIndex, {
        destination: String(target.value || 'curated').trim().toLowerCase(),
        model_ref: '',
        working_group_id: null,
        lookup_query: '',
        lookup_results: [],
        lookup_error: '',
        lookup_loading: false,
        selected_summary: null,
      });
      this._render();
      return;
    }
    if (action === 'group-match-mode') {
      var matchIndex = Number(target.getAttribute('data-group-index') || -1);
      this._updateGroupDestinationState(matchIndex, {
        match_mode: String(target.value || 'new').trim().toLowerCase(),
        model_ref: '',
        working_group_id: null,
        lookup_query: '',
        lookup_results: [],
        lookup_error: '',
        lookup_loading: false,
        selected_summary: null,
      });
      this._render();
      return;
    }
    if (/^(browser-|selection-|cleanup-policy$)/.test(action)) {
      this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
      this._refreshWizardPreview();
      return;
    }
  };

  proto._handleInput = function (event) {
    var target = event.target instanceof Element ? event.target : null;
    var action = target ? String(target.getAttribute('data-action') || '') : '';
    originalHandleInput.call(this, event);
    if (action === 'browser-loose-group-title') {
      this._updateBrowserLooseMeta({
        group_title_source: 'custom',
        group_title: String(target.value || '').trim(),
      });
      return;
    }
    if (action === 'browser-root-group-title') {
      var rootKey = String(target.getAttribute('data-root') || '');
      if (!rootKey) {
        return;
      }
      this._updateBrowserRootMeta(rootKey, {
        group_title_source: 'custom',
        group_title: String(target.value || '').trim(),
      });
      return;
    }
    if (action === 'browser-flat-model-title') {
      var relativePath = String(target.getAttribute('data-relative-path') || '');
      if (!relativePath) {
        return;
      }
      this._updateBrowserEntriesWhere(function (entry) {
        return String(entry.relative_path || entry.name || '') === relativePath;
      }, {
        group_title_source: 'custom',
        group_title: String(target.value || '').trim(),
      });
      return;
    }
    if (action === 'selection-file-model-title') {
      var selectionPath = String(target.getAttribute('data-path') || '');
      if (!selectionPath || !this._selected[selectionPath]) {
        return;
      }
      this._selected = Object.assign({}, this._selected, {
        [selectionPath]: Object.assign({}, this._selected[selectionPath], {
          group_title_source: 'custom',
          group_title: String(target.value || '').trim(),
        }),
      });
      return;
    }
    if (action === 'group-lookup-query') {
      this._updateGroupDestinationState(Number(target.getAttribute('data-group-index') || -1), {
        lookup_query: String(target.value || ''),
      });
      return;
    }
    if (action === 'browser-group-title' || action === 'selection-group-title' || action === 'selection-group-title-files') {
      this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
      if (this._wizardStep > 2) {
        this._refreshWizardPreview();
      }
    }
  };
})();
