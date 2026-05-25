var intakeShared = window.ModelCatalogIntakeShared || {};
var escapeHtml = intakeShared.escapeHtml;
var basename = intakeShared.basename;
var callServiceWithResponse = intakeShared.callServiceWithResponse;
var fireModelCatalogDataChanged = intakeShared.fireModelCatalogDataChanged;
var postJsonWithAuth = intakeShared.postJsonWithAuth;
var uploadBrowserFilesWithFallback = intakeShared.uploadBrowserFilesWithFallback;
var groupingStrategyLabel = intakeShared.groupingStrategyLabel;
var groupingOptionsHtml = intakeShared.groupingOptionsHtml;
var normalizeGroupingStrategy = intakeShared.normalizeGroupingStrategy;
var sharedNormalizePath = intakeShared.normalizePath;
var sharedFileTypeIconName = intakeShared.fileTypeIconName;
var sharedFileKind = intakeShared.fileKind;
var displayTitleFromPath = intakeShared.displayTitleFromPath || function (pathValue) {
  return basename(pathValue || '').replace(/\.[^.]+$/, '');
};

var PRINTABLE_EXTENSIONS = {
  '.3mf': true,
  '.stl': true,
  '.step': true,
  '.stp': true,
  '.obj': true,
  '.amf': true,
  '.ply': true,
};

var normalizePath = sharedNormalizePath || function (pathValue) {
  return String(pathValue || '').replace(/\\/g, '/');
};

function compareBrowseNames(leftValue, rightValue) {
  return String(leftValue || '').localeCompare(String(rightValue || ''), undefined, {
    numeric: true,
    sensitivity: 'base',
  });
}

function sortedBrowseEntries(entries) {
  return (Array.isArray(entries) ? entries.slice() : []).sort(function (left, right) {
    var leftIsFolder = left && left.type === 'folder';
    var rightIsFolder = right && right.type === 'folder';
    if (leftIsFolder !== rightIsFolder) {
      return leftIsFolder ? -1 : 1;
    }
    var byName = compareBrowseNames(left && left.name, right && right.name);
    if (byName !== 0) {
      return byName;
    }
    return compareBrowseNames(left && left.path, right && right.path);
  });
}

function sortedSelectedEntries(entries) {
  return (Array.isArray(entries) ? entries.slice() : []).sort(function (left, right) {
    var leftIsFolder = left && left.type === 'folder';
    var rightIsFolder = right && right.type === 'folder';
    if (leftIsFolder !== rightIsFolder) {
      return leftIsFolder ? -1 : 1;
    }
    var byPath = compareBrowseNames(left && left.path, right && right.path);
    if (byPath !== 0) {
      return byPath;
    }
    return compareBrowseNames(left && left.name, right && right.name);
  });
}

// Issue #1322: pick an MDI icon for the file type indicator shown in source-step rows.
var fileTypeIconName = sharedFileTypeIconName || function (pathValue) {
  var normalized = normalizePath(pathValue).toLowerCase();
  var dotIndex = normalized.lastIndexOf('.');
  var extension = dotIndex >= 0 ? normalized.slice(dotIndex) : '';
  if (PRINTABLE_EXTENSIONS[extension]) {
    return 'mdi:cube-outline';
  }
  if (/\.(png|jpg|jpeg|webp|gif|bmp|svg|avif|heic|tif|tiff)$/i.test(normalized)) {
    return 'mdi:image-outline';
  }
  if (extension === '.pdf') {
    return 'mdi:file-pdf-box';
  }
  if (/\.(doc|docx|odt|rtf|txt|md)$/i.test(normalized)) {
    return 'mdi:file-document-outline';
  }
  if (/\.(zip|rar|7z|tar|gz|bz2|xz)$/i.test(normalized)) {
    return 'mdi:zip-box-outline';
  }
  if (/\.(gcode|g)$/i.test(normalized)) {
    return 'mdi:printer-3d-nozzle';
  }
  return 'mdi:file-outline';
};

function entryTypeIconMarkup(pathValue, isFolder, isArchiveFolder) {
  if (isFolder) {
    return '<span class="entry-type-icon" aria-hidden="true"><ha-icon icon="' + (isArchiveFolder ? 'mdi:folder-zip-outline' : 'mdi:folder-outline') + '"></ha-icon></span>';
  }
  return '<span class="entry-type-icon" aria-hidden="true"><ha-icon icon="' + fileTypeIconName(pathValue) + '"></ha-icon></span>';
}

// Issue #1323: shared markup for the "preview" thumbnail block when the entry
// is a folder. Shows an MDI folder icon with the word "folder" underneath so
// folders are visually distinct from files in both Server and Browser paths.
function folderPreviewMarkup(isArchiveFolder) {
  return ''
    + '<div class="entry-thumb folder-thumb" aria-hidden="true">'
    + '<ha-icon icon="' + (isArchiveFolder ? 'mdi:folder-zip-outline' : 'mdi:folder-outline') + '"></ha-icon>'
    + '<div class="folder-thumb-label">' + (isArchiveFolder ? 'zip' : 'folder') + '</div>'
    + '</div>';
}

function getBrowserArchiveContainerName(folderNode, folderPath) {
  var names = {};
  var pending = [folderNode];
  while (pending.length) {
    var node = pending.pop();
    (node.files || []).forEach(function (fileItem) {
      var entry = fileItem && fileItem.entry ? fileItem.entry : {};
      if (String(entry.source_container_type || '').toLowerCase() !== 'archive') {
        return;
      }
      var relativePath = normalizeBrowserRelativePath(entry.relative_path || entry.name || fileItem.path || '');
      if (browserRootKey(relativePath) !== folderPath) {
        return;
      }
      var containerName = String(entry.source_container_name || '').trim();
      if (containerName) {
        names[containerName] = true;
      }
    });
    Object.keys(node.folders || {}).forEach(function (key) {
      pending.push(node.folders[key]);
    });
  }
  var archiveNames = Object.keys(names);
  return archiveNames.length === 1 ? archiveNames[0] : '';
}

// Issue #1322: strip the implementation-detail "/assets/" prefix when showing the server browse path,
// so operators see "Model Inbox/..." instead of "/assets/Model Inbox/...".
function formatBrowsePathForDisplay(rawPath) {
  var normalized = normalizePath(rawPath || '/');
  if (!normalized || normalized === '/') {
    return 'Model Inbox/';
  }
  var stripped = normalized.replace(/^\/+/, '');
  if (stripped.toLowerCase().indexOf('assets/') === 0) {
    stripped = stripped.slice('assets/'.length);
  } else if (stripped.toLowerCase() === 'assets') {
    stripped = '';
  }
  if (!stripped) {
    return 'Model Inbox/';
  }
  return stripped;
}

var fileKind = sharedFileKind || function (pathValue) {
  var normalized = normalizePath(pathValue).toLowerCase();
  var dotIndex = normalized.lastIndexOf('.');
  var extension = dotIndex >= 0 ? normalized.slice(dotIndex) : '';
  if (PRINTABLE_EXTENSIONS[extension]) {
    return 'model';
  }
  if (/\.(png|jpg|jpeg|webp|gif|bmp|svg|avif)$/i.test(normalized)) {
    return 'media';
  }
  if (/\.(zip|rar|7z|tar|gz|bz2|xz)$/i.test(normalized)) {
    return 'archive';
  }
  return 'supporting';
};

function browserRootKey(relativePath) {
  var parts = normalizePath(relativePath).split('/').filter(Boolean);
  return parts.length > 1 ? parts[0] : '';
}

function normalizeBrowserRelativePath(pathValue) {
  return normalizePath(pathValue).replace(/^\/+/, '');
}

function browserParentRelativePath(pathValue) {
  var normalized = normalizeBrowserRelativePath(pathValue);
  if (!normalized) {
    return '';
  }
  var parts = normalized.split('/').filter(Boolean);
  if (parts.length <= 1) {
    return '';
  }
  return parts.slice(0, -1).join('/');
}

function formatBrowserPathForDisplay(pathValue) {
  var normalized = normalizeBrowserRelativePath(pathValue);
  return normalized ? normalized : 'Browser Upload';
}

function buildBrowserSourceTree(files) {
  var root = {
    name: '',
    path: '',
    folders: {},
    files: [],
  };
  (files || []).forEach(function (entry) {
    var relativePath = normalizeBrowserRelativePath(entry.relative_path || entry.name || '');
    if (!relativePath) {
      return;
    }
    var parts = relativePath.split('/').filter(Boolean);
    var cursor = root;
    var accum = [];
    for (var i = 0; i < parts.length - 1; i += 1) {
      var segment = parts[i];
      accum.push(segment);
      if (!cursor.folders[segment]) {
        cursor.folders[segment] = {
          name: segment,
          path: accum.join('/'),
          folders: {},
          files: [],
        };
      }
      cursor = cursor.folders[segment];
    }
    cursor.files.push({
      name: parts[parts.length - 1],
      path: relativePath,
      entry: entry,
    });
  });
  return root;
}

function getBrowserTreeNode(root, pathValue) {
  var normalized = normalizeBrowserRelativePath(pathValue);
  if (!normalized) {
    return root;
  }
  var parts = normalized.split('/').filter(Boolean);
  var cursor = root;
  for (var i = 0; i < parts.length; i += 1) {
    if (!cursor || !cursor.folders || !cursor.folders[parts[i]]) {
      return root;
    }
    cursor = cursor.folders[parts[i]];
  }
  return cursor || root;
}

function titleForStrategy(card, strategy, key) {
  if (!key || key === '__loose__') {
    return card._wizardMode === 'browser' ? card._browserBatchResolvedTitle() : 'Folder';
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
    var archiveCount = 0;
    var supportingCount = 0;
    var files = group.files.map(function (entry) {
      var relativePath = normalizePath(entry.relative_path || entry.name || entry.path || '');
      var kind = fileKind(relativePath);
      if (kind === 'model') {
        modelCount += 1;
      } else if (kind === 'media') {
        mediaCount += 1;
      } else if (kind === 'archive') {
        archiveCount += 1;
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
      archive_file_count: archiveCount,
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
  function mergeNoneStrategyGroups(groups) {
    var merged = [];
    var noneIndex = -1;
    (groups || []).forEach(function (group) {
      var strategy = String(group && group.strategy || 'none').trim().toLowerCase();
      if (strategy !== 'none') {
        merged.push(group);
        return;
      }
      if (noneIndex < 0) {
        noneIndex = merged.length;
        merged.push(Object.assign({}, group, {
          files: (group && group.files ? group.files.slice() : []),
        }));
        return;
      }
      var existing = merged[noneIndex];
      existing.files = (existing.files || []).concat((group && group.files) || []);
      var incomingExplicitTitle = String(group && group.group_title || '').trim();
      var existingExplicitTitle = String(existing.group_title || '').trim();
      if (!existingExplicitTitle && incomingExplicitTitle) {
        existing.group_title = incomingExplicitTitle;
        existing.title = incomingExplicitTitle;
      }
    });
    return merged;
  }

  function groupsForSection(sectionFiles, requestedStrategy, sectionTitle, sectionGroupTitle, options) {
    var settings = options || {};
    var sectionStrategy = normalizeGroupingStrategy(requestedStrategy, {
      allowFolderStrategies: settings.allowFolderStrategies !== false,
    });
    var explicitGroupTitle = String(sectionGroupTitle || '').trim();
    var sectionGroups = [];
    if (!sectionFiles.length) {
      return sectionGroups;
    }
    if (sectionStrategy === 'by-folder') {
      var folderMap = {};
      sectionFiles.forEach(function (entry) {
        var relativePath = normalizePath(entry.relative_path || entry.name || '');
        var parts = relativePath.split('/').filter(Boolean);
        var folderKey = parts.length > 1 ? parts.slice(0, -1).join('/') : '__loose__';
        if (!folderMap[folderKey]) {
          folderMap[folderKey] = {
            title: titleForStrategy(card, sectionStrategy, folderKey),
            strategy: 'by-folder',
            files: [],
          };
        }
        folderMap[folderKey].files.push(entry);
      });
      Object.keys(folderMap).sort().forEach(function (key) {
        sectionGroups.push(folderMap[key]);
      });
      return sectionGroups;
    }
    if (sectionStrategy === 'by-root') {
      sectionGroups.push({
        title: sectionTitle || titleForStrategy(card, 'by-root', '__loose__'),
        strategy: 'by-root',
        group_title: explicitGroupTitle,
        files: sectionFiles.slice(),
      });
      return sectionGroups;
    }
    if (sectionStrategy === 'flat') {
      var printable = sectionFiles.filter(function (entry) {
        return fileKind(entry.relative_path || entry.name || '') === 'model';
      });
      if (printable.length) {
        sectionGroups = printable.map(function (entry) {
          var stem = basename(entry.relative_path || entry.name || '').replace(/\.[^.]+$/, '');
          var customTitle = String(entry.group_title || '').trim();
          return {
            title: customTitle || stem || 'Model',
            strategy: 'flat',
            group_title: customTitle,
            files: [entry],
          };
        });
        sectionFiles.forEach(function (entry) {
          if (fileKind(entry.relative_path || entry.name || '') === 'model') {
            return;
          }
          sectionGroups[0].files.push(entry);
        });
        return sectionGroups;
      }
      sectionStrategy = 'none';
    }
    sectionGroups.push({
      title: sectionTitle || card._browserBatchResolvedTitle(),
      strategy: sectionStrategy,
      group_title: explicitGroupTitle,
      files: sectionFiles.slice(),
    });
    return sectionGroups;
  }

  var groups = [];
  var rootBuckets = card._browserRootBuckets ? card._browserRootBuckets() : {};
  var rootKeys = Object.keys(rootBuckets).sort();
  rootKeys.forEach(function (rootKey) {
    var bucketFiles = rootBuckets[rootKey] || [];
    if (!bucketFiles.length) {
      return;
    }
    var representative = bucketFiles[0] || {};
    groups = groups.concat(groupsForSection(
      bucketFiles,
      representative.grouping_strategy,
      card._browserRootResolvedTitle ? card._browserRootResolvedTitle(rootKey, representative) : rootKey,
      representative.group_title,
      { allowFolderStrategies: true }
    ));
  });

  var looseFiles = card._browserLooseFiles ? card._browserLooseFiles() : [];
  if (looseFiles.length) {
    looseFiles.forEach(function (entry) {
      var relativePath = String(entry.relative_path || entry.name || '');
      var looseTitle = basename(relativePath).replace(/\.[^.]+$/, '') || 'Model';
      groups = groups.concat(groupsForSection(
        [entry],
        entry.grouping_strategy,
        looseTitle,
        entry.group_title,
        { allowFolderStrategies: false }
      ));
    });
  }

  groups = mergeNoneStrategyGroups(groups);

  var strategies = {};
  groups.forEach(function (group) {
    strategies[String(group && group.strategy || 'none')] = true;
  });
  var strategyKeys = Object.keys(strategies);
  var preview = summarizeGroups(groups, strategyKeys.length === 1 ? strategyKeys[0] : 'mixed');
  preview.contract = 'intake-plan.v1alpha1';
  preview.success = true;
  return preview;
}

/**
 * Build a nested tree structure from a flat list of file entries.
 * Each entry should have relative_path or filename.
 * Returns an object: { folders: { name: subtree, ... }, files: [{ name, entry }, ...] }
 */
function buildFileTree(files) {
  var root = { folders: {}, files: [] };
  (files || []).forEach(function (entry) {
    var path = String(entry.relative_path || entry.filename || '');
    var parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
    if (!parts.length) return;
    var node = root;
    for (var i = 0; i < parts.length - 1; i++) {
      var folder = parts[i];
      if (!node.folders[folder]) {
        node.folders[folder] = { folders: {}, files: [] };
      }
      node = node.folders[folder];
    }
    node.files.push({ name: parts[parts.length - 1], entry: entry });
  });
  return root;
}

/**
 * Render a file tree node as nested HTML for the Review pane.
 * Folders are rendered as collapsible sections (collapsed by default).
 */
function renderFileTreeNode(node, depth) {
  var d = depth || 0;
  var indent = d * 16;
  var html = '';
  var folderNames = Object.keys(node.folders).sort();
  folderNames.forEach(function (folderName) {
    var subtree = node.folders[folderName];
    var childCount = countTreeFiles(subtree);
    html += ''
      + '<div class="file-tree-folder" style="padding-left:' + indent + 'px;">'
      + '  <div class="file-tree-toggle" data-tree-action="toggle">'
      + '    <span class="file-tree-arrow">&#9654;</span>'
      + '    <span class="file-tree-icon">&#128193;</span>'
      + '    <span class="file-tree-label">' + escapeHtml(folderName) + '/</span>'
      + '    <span class="file-tree-count muted">(' + childCount + ')</span>'
      + '  </div>'
      + '  <div class="file-tree-children" style="display:none;">'
      + renderFileTreeNode(subtree, d + 1)
      + '  </div>'
      + '</div>';
  });
  node.files.forEach(function (f) {
    var ext = (f.name.match(/\.([^.]+)$/) || ['', ''])[1].toLowerCase();
    var icon = ext === '3mf' || ext === 'stl' || ext === 'obj' ? '&#128196;' : '&#128462;';
    html += '<div class="file-tree-file" style="padding-left:' + (indent + 16) + 'px;">'
      + '<span class="file-tree-icon">' + icon + '</span>'
      + '<span class="file-tree-label">' + escapeHtml(f.name) + '</span>'
      + '</div>';
  });
  return html;
}

function countTreeFiles(node) {
  var count = node.files.length;
  Object.keys(node.folders).forEach(function (k) {
    count += countTreeFiles(node.folders[k]);
  });
  return count;
}

/**
 * Render the full collapsible file tree for a planned model.
 * Shows a toggle button; tree is hidden by default.
 */
function renderFileTreeBlock(files, opts) {
  var options = opts || {};
  var flatten = options.flatten || false;
  var treeHtml = '';
  var duplicateWarning = '';

  if (flatten) {
    // Show all files as flat basenames (how they'll appear at destination).
    var basenames = (files || []).map(function (entry) {
      var path = String(entry.relative_path || entry.filename || '');
      var parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
      return parts.length ? parts[parts.length - 1] : path;
    });
    // Detect duplicate basenames.
    var nameCount = {};
    basenames.forEach(function (name) {
      var key = name.toLowerCase();
      nameCount[key] = (nameCount[key] || 0) + 1;
    });
    var duplicates = Object.keys(nameCount).filter(function (k) { return nameCount[k] > 1; });
    if (duplicates.length) {
      duplicateWarning = '<div class="file-tree-conflict-warning">&#9888; ' + String(duplicates.length) + ' filename conflict' + (duplicates.length > 1 ? 's' : '') + ' — duplicates will be auto-renamed (e.g. file-2.ext)</div>';
    }
    treeHtml = basenames.map(function (name) {
      var isDuplicate = nameCount[name.toLowerCase()] > 1;
      var ext = (name.match(/\.([^.]+)$/) || ['', ''])[1].toLowerCase();
      var icon = ext === '3mf' || ext === 'stl' || ext === 'obj' ? '&#128196;' : '&#128462;';
      return '<div class="file-tree-file' + (isDuplicate ? ' file-tree-duplicate' : '') + '">'
        + '<span class="file-tree-icon">' + icon + '</span>'
        + '<span class="file-tree-label">' + escapeHtml(name) + '</span>'
        + (isDuplicate ? ' <span class="file-tree-dup-badge">duplicate</span>' : '')
        + '</div>';
    }).join('');
  } else {
    var tree = buildFileTree(files);
    treeHtml = renderFileTreeNode(tree, 0);
  }

  return ''
    + '<div class="file-tree-block">'
    + '  <div class="file-tree-toggle-header" data-tree-action="toggle-root">'
    + '    <span class="file-tree-arrow">&#9654;</span>'
    + '    <span class="entry-path" style="cursor:pointer;">Show file tree</span>'
    + '  </div>'
    + '  <div class="file-tree-root" style="display:none;">'
    + duplicateWarning
    + treeHtml
    + '  </div>'
    + '</div>';
}

function renderPlanSummary(card, options) {
  var settings = options || {};
  var preview = card._previewData;
  var isLoading = card._loading || card._previewLoading || false;
  var isPublishing = isLoading && card._wizardStep === card._wizardStepCount();
  var uploadProgress = card._uploadProgress || null;
  var uploadProgressText = '';
  if (uploadProgress && uploadProgress.mode === 'determinate' && uploadProgress.percent != null) {
    uploadProgressText = String(Math.max(0, Math.min(100, Number(uploadProgress.percent || 0)))) + '%';
    if (uploadProgress.bytes_total) {
      uploadProgressText += ' (' + String(uploadProgress.bytes_done || 0) + ' / ' + String(uploadProgress.bytes_total || 0) + ' bytes)';
    }
  } else if (uploadProgress && uploadProgress.detail) {
    uploadProgressText = String(uploadProgress.detail || '');
  }
  var skipSummary = settings.skipSummary || false;
  if (!preview || !preview.planned_models || !preview.planned_models.length) {
    if (isLoading) {
      return '<div class="state-row recalculating"><span class="intake-spinner spin-20"></span> ' + (isPublishing ? 'Publishing to destinations...' : 'Recalculating output...') + (uploadProgressText ? '<div class="muted" style="margin-top:6px;">' + escapeHtml(uploadProgressText) + '</div>' : '') + '</div>';
    }
    // When the plan call has succeeded but produced zero models, surface the
    // backend warnings here on the Organize step so the user knows BEFORE they
    // try to advance to Choose Destination. The Next button is also blocked.
    if (preview && Array.isArray(preview.warnings) && preview.warnings.length) {
      var warningItems = preview.warnings.map(function (warning) {
        var w = warning || {};
        var msg = String(w.message || w.code || 'Unknown issue').replace(/\/assets\//gi, '');
        var key = String(w.path || '').replace(/\\/g, '/').replace(/^\/+/, '').replace(/\/+$/, '').toLowerCase();
        return '<li data-warning-key="' + escapeHtml(key) + '">' + escapeHtml(msg) + '</li>';
      }).join('');
      return ''
        + '<div class="state-row" style="border-left:3px solid #f59e0b; text-align:left;">'
        + '  <div><strong>No models or files will be created from the current selection.</strong></div>'
        + '  <ul style="margin:6px 0 0 18px; padding:0;">' + warningItems + '</ul>'
        + '  <div class="muted" style="margin-top:6px;">Return to Select to pick a different folder, or add eligible model files (e.g. .3mf, .stl) to the selected folder before continuing.</div>'
        + '</div>';
    }
    return '<div class="state-row">No planned output yet. Advance to Organize after selecting sources to resolve the model plan.</div>';
  }
  var destinationPlans = settings.includeDestinations && typeof card._syncGroupDestinationsFromPreview === 'function'
    ? card._syncGroupDestinationsFromPreview()
    : [];
  // Partial-failure banner: when SOME planned models exist but the backend
  // also returned warnings (e.g. one of several selected folders was empty
  // or contained only unsupported files), surface those warnings inline so
  // the user knows their selection is being silently trimmed. Non-blocking:
  // the user can still advance with the partial plan.
  var warningsBanner = '';
  if (preview && Array.isArray(preview.warnings) && preview.warnings.length) {
    var bannerItems = preview.warnings.map(function (warning) {
      var w = warning || {};
      var msg = String(w.message || w.code || 'Unknown issue').replace(/\/assets\//gi, '');
      var key = String(w.path || '').replace(/\\/g, '/').replace(/^\/+/, '').replace(/\/+$/, '').toLowerCase();
      return '<li data-warning-key="' + escapeHtml(key) + '">' + escapeHtml(msg) + '</li>';
    }).join('');
    warningsBanner = ''
      + '<div class="state-row" style="border-left:3px solid #f59e0b; margin-bottom:8px; text-align:left;">'
      + '  <div><strong>Some selections will not contribute any files.</strong></div>'
      + '  <ul style="margin:6px 0 0 18px; padding:0;">' + bannerItems + '</ul>'
      + '  <div class="muted" style="margin-top:6px;">You can continue with the planned models below, or return to Select to remove these entries.</div>'
      + '</div>';
  }
  var summaryHtml = '';
  if (!skipSummary) {
    summaryHtml = ''
      + '<div class="result-summary">'
      + '  <div class="result-line"><span>Files in batch</span><strong>' + String(preview.summary.file_count || 0) + '</strong></div>'
      + '  <div class="result-line"><span>Planned models</span><strong>' + String(preview.summary.planned_model_count || preview.planned_models.length) + '</strong></div>';
    if (isLoading) {
      summaryHtml += '  <div class="result-line muted"><span class="intake-spinner spin-16" style="margin-right:6px;"></span>' + (isPublishing ? 'Publishing...' : 'Recalculating...') + '</div>';
      if (uploadProgressText) {
        summaryHtml += '  <div class="result-line muted">' + escapeHtml(uploadProgressText) + '</div>';
      }
    }
    summaryHtml += '</div>';
  }
  var entriesHtml = '<div class="entries' + (isLoading ? ' loading-entries' : '') + '">' + preview.planned_models.map(function (model, index) {
    var destinationPlan = destinationPlans[index] || null;
    var totalFiles = (model.files || []).length;
    var destinationMarkup = '';
    var files = renderFileTreeBlock(model.files || [], { flatten: model.preserve_folder_structure === false });
    if (destinationPlan) {
      var matchLabel = String(destinationPlan.match_mode || 'new') === 'existing' ? 'Add To Existing' : 'New';
      destinationMarkup = ''
        + '<div class="button-row"><span class="chip">Catalog</span><span class="chip">' + escapeHtml(matchLabel) + '</span></div>'
        + '<div class="entry-path muted">' + escapeHtml(card._destinationSelectionSummary(destinationPlan)) + '</div>';
    }
    return ''
      + '<article class="entry-row' + (isLoading ? ' loading-item' : '') + '" data-model-index="' + String(index) + '">' 
      + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(model.title || 'Model') + '</div><div class="entry-path">' + escapeHtml(card._groupingStrategyLabel ? card._groupingStrategyLabel(model.strategy || 'none') : (model.strategy || 'none')) + '</div></div><div class="button-row"><span class="chip">' + String(model.file_count || 0) + ' files</span></div></div>'
      + destinationMarkup
      + files
      + '</article>';
  }).join('') + '</div>';
  return warningsBanner + summaryHtml + entriesHtml;
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
          label: 'Resolved files do not match existing indexed files (hard/soft)',
          passed: card._validationData.validation_state !== 'duplicate_candidate',
          detail: 'Duplicate detection compares hard hash matches plus soft filename variants (for example, copy suffixes like (2)).',
        },
        {
          key: 'commit_ready',
          label: 'Resolved plan contains at least one file to commit',
          passed: card._validationData.validation_state !== 'needs_manual_grouping',
          detail: 'Validation only advances when the prepared upload resolves into a real file set.',
        },
        // Issue #1347: fallback exclusion summary so the chip reflects the
        // wizard-side exclusion count even if the backend omits the check.
        (function () {
          var fallbackExcluded = 0;
          if (Array.isArray(card._excludedItems)) {
            fallbackExcluded += card._excludedItems.length;
          }
          if (typeof card._excludedBrowserKeyCount === 'function') {
            fallbackExcluded += card._excludedBrowserKeyCount();
          }
          return {
            key: 'excluded_items_summary',
            label: 'Exclusion summary',
            passed: true,
            detail: fallbackExcluded > 0
              ? (String(fallbackExcluded) + ' items excluded from selected sources.')
              : 'No items excluded.',
            excluded_count: fallbackExcluded,
          };
        })(),
      ];
  var warningText = (card._validationData.warnings || []).map(function (warning) {
    return warning && (warning.message || warning.code) ? (warning.message || warning.code) : String(warning || '');
  }).filter(Boolean).slice(0, 5);
  var decisionMap = card && card._validationDecisionMap && typeof card._validationDecisionMap === 'object'
    ? card._validationDecisionMap
    : {};
  var overrideSummary = card && typeof card._validationOverrideSummary === 'function'
    ? card._validationOverrideSummary()
    : null;
  var overrideSummaryHtml = '';

  function trimIntakeSourcePrefix(pathValue) {
    var normalized = String(pathValue || '').replace(/\\/g, '/').trim();
    if (!normalized) {
      return '';
    }
    var withoutPrefix = normalized.replace(/^\/assets\/model inbox\//i, '');
    withoutPrefix = withoutPrefix.replace(/^\/assets\/model inbox$/i, '');
    return withoutPrefix.replace(/^\/+/, '');
  }

  function sourceFolderDisplay(group, firstFinding) {
    var finding = firstFinding && typeof firstFinding === 'object' ? firstFinding : {};
    var filename = String(group && group.source_name || finding.filename || '').trim();
    var relativePath = String(finding.relative_path || '').trim().replace(/\\/g, '/');
    if (relativePath) {
      var relParts = relativePath.split('/').filter(Boolean);
      if (relParts.length > 1) {
        return relParts.slice(0, -1).join('/');
      }
    }
    var fullPath = String(group && group.source_path || finding.path || '').trim().replace(/\\/g, '/');
    if (!fullPath) {
      return '';
    }
    var trimmed = trimIntakeSourcePrefix(fullPath);
    if (filename && trimmed.toLowerCase().endsWith('/' + filename.toLowerCase())) {
      trimmed = trimmed.slice(0, Math.max(0, trimmed.length - (filename.length + 1)));
    }
    if (filename && trimmed.toLowerCase() === filename.toLowerCase()) {
      return '';
    }
    return trimmed;
  }

  function conflictPathDisplay(pathValue, filename) {
    var normalized = trimIntakeSourcePrefix(pathValue);
    var fileNameText = String(filename || '').trim();
    if (fileNameText && normalized.toLowerCase() === fileNameText.toLowerCase()) {
      return '';
    }
    return normalized;
  }

  function tableFolderDisplay(pathValue, filename) {
    var normalized = trimIntakeSourcePrefix(pathValue);
    var fileNameText = String(filename || '').trim();
    if (!normalized) {
      return '';
    }
    if (fileNameText && normalized.toLowerCase().endsWith('/' + fileNameText.toLowerCase())) {
      normalized = normalized.slice(0, Math.max(0, normalized.length - (fileNameText.length + 1)));
    }
    if (fileNameText && normalized.toLowerCase() === fileNameText.toLowerCase()) {
      return '';
    }
    return normalized;
  }

  function conflictSourceLabel(conflictItem) {
    if (!conflictItem || typeof conflictItem !== 'object') {
      return String(conflictItem || '').trim();
    }
    var parentKind = String(conflictItem.parent_kind || '').trim().replace(/_/g, ' ');
    var parentName = String(conflictItem.parent_name || '').trim();
    if (parentKind) {
      parentKind = parentKind.split(' ').filter(Boolean).map(function (token) {
        return token.charAt(0).toUpperCase() + token.slice(1);
      }).join(' ');
    }
    if (parentKind && parentName) {
      return parentKind + ': ' + parentName;
    }
    if (parentName) {
      return parentName;
    }
    return String(conflictItem.label || '').trim();
  }

  function intakePreviewUrl(card, pathValue) {
    var rawPath = String(pathValue || '').trim();
    if (!rawPath) {
      return '';
    }
    var normalizedPath = rawPath.replace(/\\/g, '/');
    var isAbsoluteWindows = /^[A-Za-z]:\//.test(normalizedPath);
    var isAbsolutePosix = normalizedPath.indexOf('/') === 0;
    if (!isAbsoluteWindows && !isAbsolutePosix) {
      return '';
    }
    if (!card || typeof card._resolveSidecarUrl !== 'function') {
      return '';
    }
    var sidecarBaseUrl = String(card._resolveSidecarUrl() || '').replace(/\/$/, '');
    if (!sidecarBaseUrl) {
      return '';
    }
    return sidecarBaseUrl + '/api/intake/preview?path=' + encodeURIComponent(rawPath);
  }

  function normalizeConflictPreviewUrl(card, previewUrl, fallbackPath) {
    var rawPreview = String(previewUrl || '').trim();
    if (rawPreview) {
      if (/^(https?:|data:|blob:)/i.test(rawPreview)) {
        return rawPreview;
      }
      if (rawPreview.indexOf('/') === 0 && card && typeof card._resolveSidecarUrl === 'function') {
        var sidecarBaseUrl = String(card._resolveSidecarUrl() || '').replace(/\/$/, '');
        if (sidecarBaseUrl) {
          return sidecarBaseUrl + rawPreview;
        }
      }
    }
    return intakePreviewUrl(card, fallbackPath);
  }

  function validationExtBadgeMarkup(filename) {
    var ext = String(filename || '').replace(/^.*\./, '.').toLowerCase();
    if (!ext || ext === filename || ext.indexOf('.') !== 0) { ext = ''; }
    var extUpper = ext.replace('.', '').toUpperCase() || '?';
    var extClass = ext ? 'x-' + ext.replace('.', '') : '';
    return '<div class="validation-thumb-button validation-ext-badge ' + escapeHtml(extClass) + '">' + escapeHtml(extUpper) + '</div>';
  }

  function compareThumbMarkup(previewUrl, imageLabel, findingKey, columnRole, filename) {
    if (!previewUrl) {
      return '<div class="validation-thumb-wrap">' + validationExtBadgeMarkup(filename) + '</div>';
    }
    var label = String(imageLabel || 'Preview image');
    var key = String(findingKey || 'finding');
    var role = String(columnRole || 'source');
    var fallbackBadge = validationExtBadgeMarkup(filename);
    return ''
      + '<div class="validation-thumb-wrap">'
      + '  <button type="button" class="validation-thumb-button" data-action="validation-open-image-preview" data-image-url="' + escapeHtml(previewUrl) + '" data-image-label="' + escapeHtml(label) + '" data-image-key="' + escapeHtml(key) + '" data-image-role="' + escapeHtml(role) + '">'
      + '    <img class="validation-thumb-image" src="' + escapeHtml(previewUrl) + '" alt="' + escapeHtml(label) + '" loading="lazy" decoding="async"'
      + '      onerror="this.closest(\'.validation-thumb-wrap\').innerHTML=' + escapeHtml("'" + fallbackBadge.replace(/'/g, "\\'") + "'") + ';">'
      + '  </button>'
      + '  <div class="validation-thumb-hover" aria-hidden="true">'
      + '    <img class="validation-thumb-hover-image" src="' + escapeHtml(previewUrl) + '" alt="' + escapeHtml(label) + '" loading="lazy" decoding="async">'
      + '  </div>'
      + '</div>';
  }

  function renderValidationImageLightbox(card) {
    var state = card && card._validationImagePreview && typeof card._validationImagePreview === 'object'
      ? card._validationImagePreview
      : null;
    if (!state || !state.url) {
      return '';
    }
    var label = String(state.label || 'Comparison preview');
    return ''
      + '<div class="validation-lightbox" data-action="validation-close-image-preview">'
      + '  <div class="validation-lightbox-backdrop" data-action="validation-close-image-preview"></div>'
      + '  <div class="validation-lightbox-dialog">'
      + '    <div class="validation-lightbox-header">'
      + '      <div class="validation-lightbox-title">' + escapeHtml(label) + '</div>'
      + '      <button type="button" class="button" data-action="validation-close-image-preview">Close</button>'
      + '    </div>'
      + '    <div class="validation-lightbox-body">'
      + '      <img class="validation-lightbox-image" src="' + escapeHtml(state.url) + '" alt="' + escapeHtml(label) + '" loading="eager" decoding="async">'
      + '    </div>'
      + '  </div>'
      + '</div>';
  }

  function renderConflictItem(conflictItem) {
    if (conflictItem && typeof conflictItem === 'object') {
      var parentKind = String(conflictItem.parent_kind || '').trim().replace(/_/g, ' ');
      var parentName = String(conflictItem.parent_name || '').trim();
      var parentKindLabel = parentKind
        ? parentKind.split(' ').filter(Boolean).map(function (token) {
          return token.charAt(0).toUpperCase() + token.slice(1);
        }).join(' ')
        : '';
      var parentLabel = parentName
        ? ((parentKindLabel ? (parentKindLabel + ': ') : '') + parentName)
        : '';
      var filename = String(conflictItem.filename || '').trim();
      var pathText = conflictPathDisplay(conflictItem.path, filename);
      var primary = parentLabel || String(conflictItem.label || filename || 'Conflict target').trim();
      var secondary = pathText || (filename && filename !== primary ? filename : '');
      return ''
        + '<li>'
        + '  <div class="validation-conflict-primary">' + escapeHtml(primary) + '</div>'
        + (secondary ? ('  <div class="validation-conflict-secondary">' + escapeHtml(secondary) + '</div>') : '')
        + '</li>';
    }
    var fallbackText = String(conflictItem || '').trim();
    if (!fallbackText) {
      return '';
    }
    return '<li><div class="validation-conflict-primary">' + escapeHtml(fallbackText) + '</div></li>';
  }

  function violationSeverityRank(finding) {
    var code = String(finding && finding.violation_code || '').toLowerCase();
    if (code.indexOf('hash') >= 0) {
      return 1;
    }
    if (code.indexOf('exact') >= 0) {
      return 2;
    }
    if (code.indexOf('soft') >= 0 || code.indexOf('near') >= 0) {
      return 3;
    }
    return 4;
  }

  function violationSeverityClass(finding) {
    var rank = violationSeverityRank(finding);
    if (rank === 1) {
      return 'severity-hash';
    }
    if (rank === 2) {
      return 'severity-exact';
    }
    if (rank === 3) {
      return 'severity-soft';
    }
    return 'severity-other';
  }

  function violationSeverityLabel(finding) {
    var rank = violationSeverityRank(finding);
    if (rank === 1) {
      return 'Hash match';
    }
    if (rank === 2) {
      return 'Exact name';
    }
    if (rank === 3) {
      return 'Soft name';
    }
    return 'Other';
  }

  if (overrideSummary && Number(overrideSummary.totalFindings || 0) > 0) {
    var unresolvedCount = Number(overrideSummary.pendingFindings || 0);
    var resolvedCount = Number(overrideSummary.resolvedFindings || 0);
    var summaryChipClass = overrideSummary.canProceed ? 'ok' : 'warn';
    var summaryChipLabel = overrideSummary.canProceed
      ? 'Override ready'
      : (unresolvedCount > 0 ? (String(unresolvedCount) + ' pending') : 'needs attention');
    overrideSummaryHtml = ''
      + '<div class="result-summary">'
      + '  <div class="result-line"><span>Duplicate override actions</span><strong>' + String(resolvedCount) + ' / ' + String(Number(overrideSummary.totalFindings || 0)) + ' decided</strong></div>'
      + '  <div class="result-line"><span>Status</span><strong><span class="chip ' + summaryChipClass + '">' + escapeHtml(summaryChipLabel) + '</span></strong></div>'
      + '</div>';
  }
  // Issue #1307: drop the "Prepared upload <GUID>" line (implementation detail, not
  // useful to operators) and surface validation_state in UPPER CASE for emphasis.
  // The Destination Plan section that used to render at the bottom of this summary
  // has also been removed — destinations are summarized on the right pane only.
  return ''
    + '<div class="result-summary">'
    + '  <div class="result-line"><span>Validation state</span><strong>' + escapeHtml(String(card._validationData.validation_state || 'unknown').toUpperCase()) + '</strong></div>'
    + '</div>'
    + overrideSummaryHtml
    + '<div class="entries">' + checks.map(function (check) {
      var passed = !!check.passed;
      // Issue #1347: the informational "excluded_items_summary" check should
      // surface the excluded count as a Warning (orange) with a "Go to Select
      // Step" link so the user can return to the Select step to review/restore
      // exclusions, instead of rendering a misleading "pass" badge.
      var excludedCount = (check && typeof check.excluded_count === 'number') ? check.excluded_count : 0;
      var isExclusionCheck = check && check.key === 'excluded_items_summary';
      var hasExclusions = isExclusionCheck && excludedCount > 0;
      var checkClass = hasExclusions ? 'warn' : (passed ? 'pass' : 'fail');
      var iconHtml;
      if (hasExclusions) {
        iconHtml = '<span class="validation-icon warn" aria-hidden="true">⚠</span>';
      } else if (!passed) {
        iconHtml = '<span class="validation-icon fail" aria-hidden="true">✕</span>';
      } else {
        iconHtml = '<input type="checkbox" disabled' + (passed ? ' checked' : '') + '>';
      }
      var chipClass;
      var chipLabel;
      if (hasExclusions) {
        chipClass = 'warn';
        chipLabel = 'Warning · ' + String(excludedCount) + ' excluded';
      } else if (isExclusionCheck) {
        chipClass = 'ok';
        chipLabel = 'none excluded';
      } else {
        chipClass = passed ? 'ok' : 'warn';
        chipLabel = passed ? 'pass' : 'attention';
      }
      var actionHtml = hasExclusions
        ? '<button class="link-button" data-action="wizard-jump-step" data-step="1">Go to Select Step</button>'
        : '';
      var findings = Array.isArray(check && check.findings) ? check.findings : [];
      var findingsHtml = '';
      if (findings.length) {
        var grouped = {};
        findings.forEach(function (finding, findingIndex) {
          var offenderPath = String((finding && finding.path) || '').trim();
          var offenderName = String((finding && finding.filename) || '').trim();
          if (!offenderName && offenderPath) {
            offenderName = basename(offenderPath);
          }
          var sourceKey = (offenderPath || ('__name__:' + offenderName) || ('__index__:' + String(findingIndex))).toLowerCase();
          if (!grouped[sourceKey]) {
            grouped[sourceKey] = {
              source_name: offenderName || 'Source File',
              source_path: offenderPath,
              source_relative_path: String((finding && finding.relative_path) || '').trim(),
              violations: [],
            };
          }
          var findingKey = (typeof card._validationFindingKey === 'function')
            ? card._validationFindingKey(String(check.key || ''), finding, findingIndex)
            : (String(check.key || '') + '|' + String(findingIndex));
          grouped[sourceKey].violations.push({
            finding_key: findingKey,
            finding: finding || {},
            display_index: findingIndex + 1,
          });
        });

        var groupedRows = Object.keys(grouped).map(function (groupKey) {
          var group = grouped[groupKey];
          var firstFinding = group.violations.length ? (group.violations[0].finding || {}) : {};
          var sourceFolder = sourceFolderDisplay(group, firstFinding);
          var sortedViolations = group.violations.slice().sort(function (left, right) {
            var leftRank = violationSeverityRank(left && left.finding);
            var rightRank = violationSeverityRank(right && right.finding);
            if (leftRank !== rightRank) {
              return leftRank - rightRank;
            }
            return String(left && left.finding_key || '').localeCompare(String(right && right.finding_key || ''));
          });
          var violationsHtml = sortedViolations.map(function (violationRow) {
            var finding = violationRow.finding || {};
            var findingKey = String(violationRow.finding_key || '');
            var displayIndex = Number(violationRow.display_index || 0) > 0
              ? Number(violationRow.display_index)
              : 1;
            var violationLabel = String(finding.violation_label || finding.violation_code || 'Match').trim() || 'Match';
            var severityClass = violationSeverityClass(finding);
            var severityLabel = violationSeverityLabel(finding);
            var conflictTargets = Array.isArray(finding.conflicts_with)
              ? finding.conflicts_with.filter(Boolean).slice(0, 5)
              : [];
            var firstConflictTarget = conflictTargets.length ? conflictTargets[0] : null;
            var primaryConflict = firstConflictTarget && typeof firstConflictTarget === 'object'
              ? firstConflictTarget
              : null;
            var findingPath = String(finding.path || '').trim();
            var findingFilename = String(finding.filename || '').trim();
            var conflictPath = primaryConflict ? String(primaryConflict.path || '').trim() : '';
            var conflictFilename = primaryConflict
              ? String(primaryConflict.filename || '').trim()
              : String(firstConflictTarget || '').trim();
            var currentDecision = String(decisionMap[findingKey] || 'review').trim();
            if (String(check.key || '') === 'batch_duplicate_scan' && currentDecision === 'allow_duplicate') {
              currentDecision = 'keep_both';
            }
            var sourcePathForTable = sourceFolder;
            if (!sourcePathForTable) {
              var normalizedSourcePath = String(findingPath || '').replace(/\\/g, '/').trim();
              sourcePathForTable = trimIntakeSourcePrefix(normalizedSourcePath);
            }
            var sourceFolderForTable = tableFolderDisplay(sourcePathForTable, findingFilename);
            var conflictPathForTable = tableFolderDisplay(conflictPath, conflictFilename);
            var isInventoryMatch = String(check.key || '') === 'duplicate_scan';
            var leftColumnHeader = isInventoryMatch ? 'Source file (incoming)' : 'Source file';
            var rightColumnHeader = isInventoryMatch ? 'Inventory match (existing)' : 'Matched file';
            var sourcePreviewUrl = intakePreviewUrl(card, findingPath);
            var conflictPreviewUrl = normalizeConflictPreviewUrl(card, primaryConflict && primaryConflict.preview_url, conflictPath);
            var isMoreInfoExpanded = !!(card && card._validationInfoExpandedMap && card._validationInfoExpandedMap[findingKey]);
            var decisionLabelMap = {
              review: 'Pending: Needs review',
              exclude_source: 'Selected: Exclude source file',
              allow_duplicate: isInventoryMatch
                ? 'Selected: Keep source file (inventory match allowed)'
                : 'Selected: Keep source and continue',
              keep_both: 'Selected: Keep both files',
              exclude_conflict: 'Selected: Exclude conflicting file',
              exclude_both: 'Selected: Exclude both files',
            };
            var decisionText = String(decisionLabelMap[currentDecision] || 'Pending: Needs review');
            var actionControl = '';
            if (String(check.key || '') === 'duplicate_scan') {
              actionControl = ''
                + '<div class="validation-action-control">'
                + '  <label>Action</label>'
                + '  <select class="select" data-action="validation-finding-action" data-finding-key="' + escapeHtml(findingKey) + '" data-finding-path="' + escapeHtml(findingPath) + '" data-finding-filename="' + escapeHtml(findingFilename) + '" data-check-key="' + escapeHtml(String(check.key || '')) + '">'
                + '    <option value="review"' + (currentDecision === 'review' ? ' selected' : '') + '>Needs review</option>'
                + '    <option value="exclude_source"' + (currentDecision === 'exclude_source' ? ' selected' : '') + '>Exclude source file from import</option>'
                + '    <option value="allow_duplicate"' + (currentDecision === 'allow_duplicate' ? ' selected' : '') + '>Keep source file and continue</option>'
                + '  </select>'
                + '</div>';
            } else if (String(check.key || '') === 'batch_duplicate_scan') {
              actionControl = ''
                + '<div class="validation-action-control">'
                + '  <label>Action</label>'
                + '  <select class="select" data-action="validation-finding-action" data-finding-key="' + escapeHtml(findingKey) + '" data-finding-path="' + escapeHtml(findingPath) + '" data-finding-filename="' + escapeHtml(findingFilename) + '" data-conflict-path="' + escapeHtml(conflictPath) + '" data-conflict-filename="' + escapeHtml(conflictFilename) + '" data-check-key="' + escapeHtml(String(check.key || '')) + '">'
                + '    <option value="review"' + (currentDecision === 'review' ? ' selected' : '') + '>Needs review</option>'
                + '    <option value="exclude_source"' + (currentDecision === 'exclude_source' ? ' selected' : '') + '>Exclude source file from import</option>'
                + '    <option value="exclude_conflict"' + (currentDecision === 'exclude_conflict' ? ' selected' : '') + '>Exclude matched file from import</option>'
                + '    <option value="exclude_both"' + (currentDecision === 'exclude_both' ? ' selected' : '') + '>Exclude both files from import</option>'
                + '    <option value="keep_both"' + (currentDecision === 'keep_both' ? ' selected' : '') + '>Keep both files</option>'
                + '  </select>'
                + '</div>';
            }
            var sourceScope = String(finding.scope || 'batch');
            var targetScope = String(primaryConflict && primaryConflict.scope || 'unknown');
            var fullWidthDetails = [
              { key: 'Check', value: String(check.key || 'duplicate_scan') },
              { key: 'Match type', value: violationLabel },
            ];
            var matchSource = primaryConflict ? conflictSourceLabel(primaryConflict) : '';
            if (!matchSource && firstConflictTarget && typeof firstConflictTarget !== 'object') {
              matchSource = String(firstConflictTarget || '').trim();
            }
            if (matchSource) {
              fullWidthDetails.push({ key: 'Match source', value: matchSource });
            }
            var normalizedConflictPath = trimIntakeSourcePrefix(conflictPath);
            var conflictPathLooksLikeFilename = !!normalizedConflictPath
              && normalizedConflictPath.indexOf('/') < 0
              && (!conflictFilename || normalizedConflictPath.toLowerCase() === conflictFilename.toLowerCase());
            var meaningfulConflictPath = conflictPathLooksLikeFilename ? '' : normalizedConflictPath;
            var conflictPathDisplayText = conflictPathForTable
              || matchSource
              || String(primaryConflict && primaryConflict.label || '').trim()
              || String(primaryConflict && primaryConflict.parent_name || '').trim()
              || meaningfulConflictPath
              || conflictFilename
              || String(firstConflictTarget || '').trim();
            if (finding.sha256) {
              fullWidthDetails.push({ key: 'SHA256', value: String(finding.sha256) });
            }
            if (finding.normalized_name) {
              fullWidthDetails.push({ key: 'Normalized name', value: String(finding.normalized_name) });
            }
            if (typeof finding.match_score === 'number') {
              fullWidthDetails.push({ key: 'Match score', value: String(finding.match_score) });
            }
            var comparisonTableHtml = ''
              + '<div class="validation-match-table">'
              + '  <div class="validation-match-header">' + escapeHtml(leftColumnHeader) + '</div>'
              + '  <div class="validation-match-header">' + escapeHtml(rightColumnHeader) + '</div>'
              + '  <div class="validation-match-cell validation-match-path">' + escapeHtml(sourceFolderForTable || '(path unavailable)') + '</div>'
              + '  <div class="validation-match-cell validation-match-path">' + escapeHtml(conflictPathDisplayText || '(path unavailable)') + '</div>'
              + '  <div class="validation-match-cell validation-match-name">' + escapeHtml(findingFilename || group.source_name || 'Source File') + '</div>'
              + '  <div class="validation-match-cell validation-match-name">' + escapeHtml(conflictFilename || 'Unknown match') + '</div>'
              + '  <div class="validation-match-cell validation-match-preview">' + compareThumbMarkup(sourcePreviewUrl, (findingFilename || 'Source') + ' preview', findingKey, 'source', findingFilename) + '</div>'
              + '  <div class="validation-match-cell validation-match-preview">' + compareThumbMarkup(conflictPreviewUrl, (conflictFilename || 'Match') + ' preview', findingKey, 'match', conflictFilename) + '</div>'
              + '  <div class="validation-match-toggle"><button type="button" class="link-button" data-action="validation-toggle-more-info" data-finding-key="' + escapeHtml(findingKey) + '">' + (isMoreInfoExpanded ? 'Hide more info' : 'Show more info') + '</button></div>';
            if (isMoreInfoExpanded) {
              var _fmtBytes = (window.ModelCatalogIntakeShared && window.ModelCatalogIntakeShared.formatBytes) || function (n) { return n != null ? String(n) + ' B' : ''; };
              var _fmtDate = function (v) {
                if (!v) return '';
                try { var d = new Date(v); return isNaN(d.getTime()) ? String(v) : d.toLocaleString(); } catch (e) { return String(v); }
              };
              var srcSize = finding.size_bytes;
              var matchSize = primaryConflict ? primaryConflict.size_bytes : null;
              var srcMtime = finding.source_mtime;
              var matchMtime = primaryConflict ? primaryConflict.source_mtime : null;
              if (srcSize != null || matchSize != null) {
                comparisonTableHtml += ''
                  + '  <div class="validation-match-cell validation-match-meta"><span class="muted">Size:</span> ' + escapeHtml(srcSize != null ? _fmtBytes(srcSize) : '\u2014') + '</div>'
                  + '  <div class="validation-match-cell validation-match-meta"><span class="muted">Size:</span> ' + escapeHtml(matchSize != null ? _fmtBytes(matchSize) : '\u2014') + '</div>';
              }
              if (srcMtime || matchMtime) {
                comparisonTableHtml += ''
                  + '  <div class="validation-match-cell validation-match-meta"><span class="muted">Modified:</span> ' + escapeHtml(srcMtime ? _fmtDate(srcMtime) : '\u2014') + '</div>'
                  + '  <div class="validation-match-cell validation-match-meta"><span class="muted">Modified:</span> ' + escapeHtml(matchMtime ? _fmtDate(matchMtime) : '\u2014') + '</div>';
              }
              comparisonTableHtml += ''
                + '  <div class="validation-match-cell validation-match-meta"><span class="muted">Source scope:</span> ' + escapeHtml(sourceScope) + '</div>'
                + '  <div class="validation-match-cell validation-match-meta"><span class="muted">Match scope:</span> ' + escapeHtml(targetScope) + '</div>';
              comparisonTableHtml += fullWidthDetails.map(function (row) {
                return '<div class="validation-match-detail-row"><span class="validation-match-detail-key">' + escapeHtml(row.key) + '</span> ' + escapeHtml(row.value || '') + '</div>';
              }).join('');
            }
            comparisonTableHtml += '</div>';
            return ''
              + '<div class="validation-violation-row ' + severityClass + '">'
              + '  <div class="validation-violation-top">'
              + '    <div class="validation-violation-label">Violation ' + String(displayIndex) + ': ' + escapeHtml(violationLabel) + ' <span class="validation-severity-chip ' + severityClass + '">' + escapeHtml(severityLabel) + '</span></div>'
              + (actionControl || '')
              + '  </div>'
              + '  <div class="validation-violation-body">'
              + '    ' + comparisonTableHtml
              + '  </div>'
              + '</div>';
          }).join('');
          return ''
            + '<div class="validation-source-row">'
            + '  <div class="validation-source-violations">' + violationsHtml + '</div>'
            + '</div>';
        }).join('');

        findingsHtml = ''
          + '<div class="validation-findings">'
          + groupedRows
          + '</div>';
      }
      return ''
        + '<article class="entry-row validation-check-row">'
        + '  <div class="entry-top validation-check-header"><div class="entry-name"><label class="validation-check ' + checkClass + '">' + iconHtml + ' ' + escapeHtml(check.label || check.key || 'Check') + '</label></div><div class="button-row validation-status-chip"><span class="chip ' + chipClass + '">' + escapeHtml(chipLabel) + '</span></div></div>'
        + '  <div class="validation-check-content"><div class="entry-path">' + escapeHtml(check.detail || '') + (actionHtml ? ' ' + actionHtml : '') + '</div>' + findingsHtml + '</div>'
        + '</article>';
    }).join('') + '</div>'
    + (warningText.length ? '<div class="muted">Warnings: ' + escapeHtml(warningText.join('; ')) + '</div>' : '')
    + renderValidationImageLightbox(card);
}

// Issue #1311: Cleanup Impact Preview for the Commit step's left pane.
// Shows categorized file lists based on the selected cleanup policy so the user
// knows exactly which files will be deleted, stubbed, or left untouched.
function renderCleanupImpactPreview(card) {
  var policy = typeof card._cleanupPolicy === 'function' ? card._cleanupPolicy() : 'keep';
  var isBrowser = card._wizardMode === 'browser';
  var effectivePolicy = isBrowser ? 'delete_on_verified' : policy;
  var preview = card._previewData;
  if (!preview || !Array.isArray(preview.planned_models) || !preview.planned_models.length) {
    return '';
  }

  // Collect all planned source file paths (these are subject to cleanup).
  var plannedPaths = [];
  preview.planned_models.forEach(function (model) {
    (model.files || []).forEach(function (file) {
      var p = String(file.path || '').replace(/\\/g, '/');
      if (p) { plannedPaths.push(p); }
    });
  });

  // Collect excluded items (these remain untouched regardless of policy).
  var excludedItems = Array.isArray(card._excludedItems) ? card._excludedItems : [];
  var excludedDisplay = excludedItems.map(function (p) {
    return String(p || '').replace(/\\/g, '/');
  }).filter(Boolean);

  // Collect warning paths (unsupported files, etc.) — these also remain untouched.
  var warningPaths = [];
  var warnings = preview.warnings || (card._validationData && card._validationData.warnings) || [];
  if (Array.isArray(warnings)) {
    warnings.forEach(function (w) {
      if (w && w.path) {
        var wp = String(w.path).replace(/\\/g, '/');
        if (wp && plannedPaths.indexOf(wp) === -1) { warningPaths.push(wp); }
      }
    });
  }

  var untouchedPaths = excludedDisplay.concat(warningPaths);

  // For "keep" policy, everything is untouched.
  if (effectivePolicy === 'keep') {
    return ''
      + '<div class="cleanup-impact-block">'
      + '  <div class="cleanup-impact-title">Cleanup Impact</div>'
      + '  <div class="cleanup-impact-info">All <strong>' + String(plannedPaths.length) + '</strong> source file' + (plannedPaths.length !== 1 ? 's' : '') + ' will remain in their original location after publish.</div>'
      + (untouchedPaths.length
        ? '  <div class="cleanup-impact-info muted">' + String(untouchedPaths.length) + ' excluded/unsupported file' + (untouchedPaths.length !== 1 ? 's' : '') + ' also remain untouched.</div>'
        : '')
      + '</div>';
  }

  // Build the action label.
  var actionLabel = effectivePolicy === 'delete_on_verified' ? 'Deleted after success' : 'Replaced with stub marker';
  var actionIcon = effectivePolicy === 'delete_on_verified' ? '&#128465;' : '&#128196;';

  // Build a simple flat file list for the "affected" category.
  var affectedListHtml = plannedPaths.map(function (p) {
    var parts = p.split('/');
    var name = parts[parts.length - 1] || p;
    return '<div class="cleanup-impact-file"><span class="cleanup-impact-icon">' + actionIcon + '</span>' + escapeHtml(name) + '</div>';
  }).join('');

  // Build the "untouched" list.
  var untouchedListHtml = untouchedPaths.map(function (p) {
    var parts = String(p).split('/');
    var name = parts[parts.length - 1] || p;
    return '<div class="cleanup-impact-file untouched"><span class="cleanup-impact-icon">&#128274;</span>' + escapeHtml(name) + '</div>';
  }).join('');

  // Stub example block (only for replace_with_stub).
  var stubExampleHtml = '';
  if (effectivePolicy === 'replace_with_stub') {
    stubExampleHtml = ''
      + '<div class="cleanup-impact-stub-example file-tree-block">'
      + '  <div class="cleanup-impact-toggle" data-tree-action="toggle-root">'
      + '    <span class="file-tree-arrow">&#9654;</span>'
      + '    <span style="cursor:pointer;font-size:12px;">What does a stub file look like?</span>'
      + '  </div>'
      + '  <div class="file-tree-root" style="display:none;">'
      + '    <div class="cleanup-impact-stub-content">'
      + '      <code>[MODEL_CATALOG_UPLOAD_STUB_V1]<br>'
      + '      upload_id=&lt;batch-id&gt;<br>'
      + '      source_path=&lt;original/path/file.3mf&gt;<br>'
      + '      local_model_id=&lt;model-slug--id&gt;<br>'
      + '      status=source_replaced_after_verified_publish</code>'
      + '    </div>'
      + '    <div class="muted" style="margin-top:4px;font-size:11px;">'
      + '      Each original file is replaced with a <code>.stub.txt</code> sibling containing this metadata, so you can trace where the file was published.'
      + '    </div>'
      + '  </div>'
      + '</div>';
  }

  // Folder cleanup note (only for delete_on_verified).
  var folderNote = '';
  if (effectivePolicy === 'delete_on_verified') {
    folderNote = '<div class="cleanup-impact-info muted" style="margin-top:6px;">'
      + 'Parent folders that become empty after deletion are also removed automatically. '
      + 'Folders containing excluded or unsupported files will <strong>not</strong> be removed.'
      + '</div>';
  }

  return ''
    + '<div class="cleanup-impact-block">'
    + '  <div class="cleanup-impact-title">Cleanup Impact</div>'
    + '  <div class="cleanup-impact-section file-tree-block">'
    + '    <div class="cleanup-impact-section-header">'
    + '      <span class="chip ' + (effectivePolicy === 'delete_on_verified' ? 'warn' : '') + '">' + actionLabel + '</span>'
    + '      <span class="muted">' + String(plannedPaths.length) + ' file' + (plannedPaths.length !== 1 ? 's' : '') + '</span>'
    + '    </div>'
    + '    <div class="cleanup-impact-toggle" data-tree-action="toggle-root">'
    + '      <span class="file-tree-arrow">&#9654;</span>'
    + '      <span class="entry-path" style="cursor:pointer;font-size:12px;">Show files</span>'
    + '    </div>'
    + '    <div class="file-tree-root" style="display:none;">' + affectedListHtml + '</div>'
    + '  </div>'
    + (untouchedPaths.length
      ? '  <div class="cleanup-impact-section file-tree-block">'
        + '    <div class="cleanup-impact-section-header">'
        + '      <span class="chip ok">Left untouched</span>'
        + '      <span class="muted">' + String(untouchedPaths.length) + ' file' + (untouchedPaths.length !== 1 ? 's' : '') + '</span>'
        + '    </div>'
        + '    <div class="cleanup-impact-toggle" data-tree-action="toggle-root">'
        + '      <span class="file-tree-arrow">&#9654;</span>'
        + '      <span class="entry-path" style="cursor:pointer;font-size:12px;">Show files</span>'
        + '    </div>'
        + '    <div class="file-tree-root" style="display:none;">' + untouchedListHtml + '</div>'
        + '  </div>'
      : '')
    + folderNote
    + stubExampleHtml
    + '</div>';
}

// Issue #1307: compact roll-up of validation checks for the Commit step's left pane.
// Counts checks by outcome (pass / warn / fail) so the user sees a one-line summary
// instead of the full per-rule list (which is shown on the Validate step).
function renderValidationSummaryCompact(card) {
  if (!card._validationData) {
    return '<div class="state-row">Validation has not run yet.</div>';
  }
  var checks = Array.isArray(card._validationData.checks) ? card._validationData.checks : [];
  var passed = 0;
  var warnings = 0;
  var attention = 0;
  checks.forEach(function (check) {
    var excludedCount = (check && typeof check.excluded_count === 'number') ? check.excluded_count : 0;
    var isExclusionCheck = check && check.key === 'excluded_items_summary';
    if (isExclusionCheck && excludedCount > 0) {
      warnings += 1;
    } else if (check && check.passed) {
      passed += 1;
    } else {
      attention += 1;
    }
  });
  var stateLabel = String(card._validationData.validation_state || 'unknown').toUpperCase();
  return ''
    + '<div class="result-summary">'
    + '  <div class="result-line"><span>Validation state</span><strong>' + escapeHtml(stateLabel) + '</strong></div>'
    + '  <div class="result-line"><span>Checks</span><strong>'
    + String(passed) + ' passed'
    + (warnings ? ' &middot; ' + String(warnings) + ' warning' + (warnings === 1 ? '' : 's') : '')
    + (attention ? ' &middot; ' + String(attention) + ' need' + (attention === 1 ? 's' : '') + ' attention' : '')
    + '</strong></div>'
    + '</div>';
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

// Issue #1324: compute which ancestor folders are "partial" (contain excluded descendants).
// Returns a plain object mapping normalised path => true for any folder that has at least
// one excluded item anywhere beneath it.
function computePartialIndicators(excludedPaths) {
  var indicators = {};
  if (!excludedPaths || !excludedPaths.length) {
    return indicators;
  }
  excludedPaths.forEach(function (excludedPath) {
    var parts = normalizePath(excludedPath).split('/').filter(Boolean);
    for (var depth = 1; depth < parts.length; depth += 1) {
      indicators['/' + parts.slice(0, depth).join('/')] = true;
    }
  });
  return indicators;
}

// Issue #1324: true when itemPath is a descendant of any path in the selectedPaths array.
function isChildOfSelection(itemPath, selectedPaths) {
  var normalized = normalizePath(itemPath);
  for (var i = 0; i < selectedPaths.length; i += 1) {
    var sel = normalizePath(selectedPaths[i]);
    var prefix = sel === '/' ? '/' : sel + '/';
    if (sel !== normalized && normalized.indexOf(prefix) === 0) {
      return true;
    }
  }
  return false;
}

// Issue #1349: true when any path in selectedPaths is a descendant of folderPath.
// Used to mark unselected parent folders that contain selected items so the
// left-side browse tree can decorate them with a dashed border (vs the solid
// colored border applied to a folder that is itself selected).
function hasSelectedDescendants(folderPath, selectedPaths) {
  var normalized = normalizePath(folderPath);
  var prefix = normalized === '/' ? '/' : normalized + '/';
  for (var i = 0; i < selectedPaths.length; i += 1) {
    var sel = normalizePath(selectedPaths[i]);
    if (sel !== normalized && sel.indexOf(prefix) === 0) {
      return true;
    }
  }
  return false;
}

// Issue #1349: dirname of a normalized server path (e.g. /foo/bar/baz.3mf -> /foo/bar).
// Trailing slash is stripped first so folders behave the same as files.
function serverParentPath(pathValue) {
  var raw = String(pathValue || '').replace(/\/+$/, '');
  var slash = raw.lastIndexOf('/');
  if (slash <= 0) {
    return '/';
  }
  return raw.slice(0, slash);
}

// Issue #1324: return the subset of excludedItems whose paths are under parentPath.
function getExcludedItemsUnderPath(parentPath, excludedItems) {
  var normalized = normalizePath(parentPath);
  var prefix = normalized === '/' ? '/' : normalized + '/';
  return (excludedItems || []).filter(function (p) {
    var np = normalizePath(p);
    return np !== normalized && np.indexOf(prefix) === 0;
  });
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
  var originalServerPayloadSelections = proto._serverPayloadSelections;
  var originalSelectedList = proto._selectedList;
  var originalCloseWizard = proto._closeWizard;

  proto._wizardStepCount = function () {
    return 5;
  };

  // Issue #1322: plural top wizard title for the Browser path; Server path keeps
  // its existing 'Import From Server Inbox' title from the base card.
  proto._wizardTitle = function () {
    return this._wizardMode === 'server' ? 'Import From Server Inbox' : 'Upload Files or Folders';
  };

  proto._wizardStepLabel = function (stepNumber) {
    if (stepNumber === 1) {
      return 'Select';
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
    // Issue #1341: delegate to the shared helper so Browser/Server flows stay
    // in lockstep with bulk-import and any future surface that needs to render
    // the user-facing label for a grouping_strategy enum value.
    return groupingStrategyLabel(strategy);
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
        'Start one path at a time and move through the same shared flow: Select, Organize, Choose Destination, Validate, Commit.'
      )
      .replace(
        'Use the current browser session to add local files or a local folder, keep building the staged list, then review before commit.',
        'Use the current browser session to add local files or a local folder, then follow the shared Select -> Organize -> Choose Destination -> Validate -> Commit flow.'
      )
      .replace(
        ', select files or folders, configure recurse/grouping, then review before commit.',
        ', select files or folders, then follow the same Select -> Organize -> Choose Destination -> Validate -> Commit flow as Browser Upload.'
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

  // Keep selected-entry rendering deterministic across all steps (Source,
  // Organize, Validate, Commit) instead of depending on object insertion order.
  proto._selectedList = function () {
    var entries = originalSelectedList ? originalSelectedList.call(this) : [];
    return sortedSelectedEntries(entries);
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
      return basename(String(entry && (entry.relative_path || entry.name) || '')).replace(/\.[^.]+$/, '') || rootKey || 'Folder';
    }
    return rootKey || 'Folder';
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
      return 'Folder';
    }
    var explicitTitle = String(files[0].group_title || '').trim();
    if (explicitTitle) {
      return explicitTitle;
    }
    return basename(String(files[0].relative_path || files[0].name || '')).replace(/\.[^.]+$/, '') || 'Folder';
  };

  proto._renderBrowserLooseFileCard = function (entry) {
    var relativePath = String(entry && (entry.relative_path || entry.name) || '');
    var displayName = basename(relativePath) || relativePath || 'upload.bin';
    var defaultTitle = displayName.replace(/\.[^.]+$/, '') || 'Folder';
    var groupingValue = normalizeGroupingStrategy(entry && entry.grouping_strategy || 'none', { allowFolderStrategies: false });
    var titleSource = String(entry && entry.group_title_source || '').trim().toLowerCase() === 'custom' ? 'custom' : 'first-file';
    var resolvedTitle = String(entry && entry.group_title || '').trim() || defaultTitle;
    var previewUrl = String(entry && entry.preview_url || '');
    var previewMarkup = previewUrl
      ? '<div class="entry-thumb"><img class="entry-thumb-image" src="' + escapeHtml(previewUrl) + '" alt="Image preview for ' + escapeHtml(displayName) + '" loading="lazy" decoding="async"></div>'
      : '<div class="entry-thumb placeholder">No preview</div>';
    return ''
      + '<article class="entry-row" data-source-key="browser-file:' + escapeHtml(relativePath) + '">'
      + '  <div class="entry-top">'
      + previewMarkup
      + '    <div class="entry-main">'
      + '      <div class="entry-name">' + escapeHtml(displayName) + '</div>'
      + '      <div class="entry-path">Loose browser file</div>'
      + '    </div>'
      + '    ' + entryTypeIconMarkup(relativePath, false)
      + '  </div>'
      + '  <div class="item-grid">'
      + '    <div class="field" style="grid-column:1 / -1;"><label>Group / Split</label><select class="select" data-action="browser-loose-file-grouping" data-relative-path="' + escapeHtml(relativePath) + '">' + groupingOptionsHtml(groupingValue, 'file') + '</select></div>'
      + '    <div class="field"><label>Title Basis</label><select class="select" data-action="browser-loose-file-title-source" data-relative-path="' + escapeHtml(relativePath) + '"><option value="first-file"' + (titleSource === 'first-file' ? ' selected' : '') + '>First file</option><option value="custom"' + (titleSource === 'custom' ? ' selected' : '') + '>Custom</option></select></div>'
      + (titleSource === 'custom'
        ? '    <div class="field"><label>Model/Group Title</label><input class="input" type="text" value="' + escapeHtml(resolvedTitle) + '" data-action="browser-loose-file-group-title" data-relative-path="' + escapeHtml(relativePath) + '" placeholder="Folder"></div>'
        : '')
      + '  </div>'
      + '</article>';
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
    return normalizeGroupingStrategy(fileEntries[0].grouping_strategy || 'none', { allowFolderStrategies: false });
  };

  proto._renderSharedPerFileNameRows = function (entries, options) {
    var settings = options || {};
    var inputAction = String(settings.inputAction || '');
    var pathAttribute = String(settings.pathAttribute || 'data-path');
    return '<div class="entries">' + (entries || []).filter(function (entry) {
      return fileKind(entry.relative_path || entry.name || entry.path || '') === 'model';
    }).map(function (entry) {
      var entryPath = String(entry.relative_path || entry.name || entry.path || '');
      var defaultTitle = displayTitleFromPath(entryPath) || 'Model';
      var currentTitle = String(entry.group_title || '').trim();
      return ''
        + '<article class="entry-row">'
        + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(defaultTitle) + '</div><div class="entry-path">' + escapeHtml(entryPath) + '</div></div><span class="chip">model</span></div>'
        + '  <div class="field"><label>Custom Model Name</label><input class="input" type="text" value="' + escapeHtml(currentTitle) + '" data-action="' + escapeHtml(inputAction) + '" ' + pathAttribute + '="' + escapeHtml(entryPath) + '" placeholder="' + escapeHtml(defaultTitle) + '"></div>'
        + '</article>';
    }).join('') + '</div>';
  };

  proto._renderSharedFileBatchCard = function (options) {
    var settings = options || {};
    var entries = settings.entries || [];
    var groupingValue = String(settings.groupingValue || 'none').trim().toLowerCase();
    var titleSource = String(settings.titleSource || 'first-file').trim().toLowerCase();
    var resolvedTitle = String(settings.resolvedTitle || 'Folder');
    var groupingAction = String(settings.groupingAction || '');
    var titleSourceAction = String(settings.titleSourceAction || '');
    var groupTitleAction = String(settings.groupTitleAction || '');
    var perFileTitleAction = String(settings.perFileTitleAction || '');
    var description = String(settings.description || 'Applies to selected files in this intake batch.');
    var sourceKey = String(settings.sourceKey || '');
    var showBatchTitleField = !(groupingValue === 'flat');
    return ''
      + '<article class="entry-row"' + (sourceKey ? ' data-source-key="' + escapeHtml(sourceKey) + '"' : '') + '>'
      + '<div class="entry-top"><div><div class="entry-name">Selected Files Batch</div><div class="entry-path">' + escapeHtml(description) + '</div></div><div class="button-row"><span class="chip">' + String(entries.length) + ' files</span></div></div>'
      + '<div class="item-grid">'
      + '<div class="field" style="grid-column:1 / -1;"><label>Group / Split</label><select class="select" data-action="' + escapeHtml(groupingAction) + '">' + groupingOptionsHtml(groupingValue, 'file') + '</select></div>'
      + '<div class="field"><label>Title Basis</label><select class="select" data-action="' + escapeHtml(titleSourceAction) + '"><option value="first-file"' + (titleSource === 'first-file' ? ' selected' : '') + '>First file</option><option value="custom"' + (titleSource === 'custom' ? ' selected' : '') + '>Custom</option></select></div>'
      + (showBatchTitleField
        ? '<div class="field"><label>Model/Group Title</label><input class="input" type="text" value="' + escapeHtml(resolvedTitle) + '" data-action="' + escapeHtml(groupTitleAction) + '" placeholder="Folder"></div>'
        : '')
      + '</div>'
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
      var defaultTitle = displayTitleFromPath(relativePath) || 'Model';
      var currentTitle = String(entry.group_title || '').trim();
      return ''
        + '<article class="entry-row">'
        + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(defaultTitle) + '</div><div class="entry-path">' + escapeHtml(relativePath) + '</div></div><span class="chip">model</span></div>'
        + '  <div class="field"><label>Custom Model Name</label><input class="input" type="text" value="' + escapeHtml(currentTitle) + '" data-action="browser-flat-model-title" data-relative-path="' + escapeHtml(relativePath) + '" placeholder="' + escapeHtml(defaultTitle) + '"></div>'
        + '</article>';
    }).join('') + '</div>';
  };

  proto._renderBrowserOrganizeRows = function () {
    var rootBuckets = this._browserRootBuckets();
    var rootKeys = Object.keys(rootBuckets).sort();
    var looseFiles = this._browserLooseFiles();
    var sections = [];
    if (looseFiles.length) {
      looseFiles.slice().sort(function (left, right) {
        var leftPath = String(left.relative_path || left.name || '');
        var rightPath = String(right.relative_path || right.name || '');
        return leftPath.localeCompare(rightPath);
      }).forEach(function (entry) {
        sections.push(this._renderBrowserLooseFileCard(entry));
      }, this);
    }
    rootKeys.forEach(function (rootKey) {
      var files = rootBuckets[rootKey];
      var representative = files[0] || {};
      var groupingStrategy = normalizeGroupingStrategy(representative.grouping_strategy || 'none', { allowFolderStrategies: true });
      var titleSource = this._browserRootTitleSource(representative);
      var resolvedTitle = this._browserRootResolvedTitle(rootKey, representative);
      sections.push(''
        + '<article class="entry-row" data-source-key="browser-root:' + escapeHtml(rootKey) + '">'
        + '<div class="entry-top">' + folderPreviewMarkup() + '<div class="entry-main"><div class="entry-name">' + escapeHtml(rootKey) + '</div><div class="entry-path">Folder upload</div></div><div class="button-row"><span class="chip">Folder</span><span class="chip">' + String(files.length) + ' files</span></div></div>'
        + '<div class="item-grid">'
        + '<div class="field" style="grid-column:1 / -1;"><label>Group / Split</label><select class="select" data-action="browser-root-grouping" data-root="' + escapeHtml(rootKey) + '">' + groupingOptionsHtml(groupingStrategy, 'folder') + '</select></div>'
        + '<div class="field"><label>Folder Scope</label><select class="select" data-action="browser-root-recurse" data-root="' + escapeHtml(rootKey) + '"><option value="true"' + (representative.recurse !== false ? ' selected' : '') + '>Include subfolders (recursive)</option><option value="false"' + (representative.recurse === false ? ' selected' : '') + '>Just this folder</option></select></div>'
        + (representative.recurse !== false
          ? '<div class="field"><label>Folder Structure</label><select class="select" data-action="browser-root-preserve-structure" data-root="' + escapeHtml(rootKey) + '"><option value="true"' + (representative.preserve_folder_structure !== false ? ' selected' : '') + '>Preserve</option><option value="false"' + (representative.preserve_folder_structure === false ? ' selected' : '') + '>Flatten</option></select></div>'
          : '<div class="field" style="visibility:hidden;" aria-hidden="true"><label>Folder Structure</label><select class="select" disabled><option>Hidden</option></select></div>')
        + '<div class="field"><label>Title Basis</label><select class="select" data-action="browser-root-title-source" data-root="' + escapeHtml(rootKey) + '"><option value="folder"' + (titleSource === 'folder' ? ' selected' : '') + '>Folder name</option><option value="first-file"' + (titleSource === 'first-file' ? ' selected' : '') + '>First file</option><option value="custom"' + (titleSource === 'custom' ? ' selected' : '') + '>Custom</option></select></div>'
        + '<div class="field"><label>Model/Group Title</label><input class="input" type="text" value="' + escapeHtml(resolvedTitle) + '" data-action="browser-root-group-title" data-root="' + escapeHtml(rootKey) + '" placeholder="Folder"></div>'
        + '<div class="muted" style="grid-column:1 / -1;">These options apply only to the folder ' + escapeHtml(rootKey) + '.</div>'
        + '</div>'
        + '</article>');
    }, this);
    return sections.length ? '<div class="entries">' + sections.join('') + '</div>' : '<div class="state-row">No browser files selected yet. Add files or a folder to begin.</div>';
  };

  proto._renderBrowserWizardSummary = function (showControls) {
    var counts = this._browserSelectionCounts();
    var fileCount = counts.fileCount;
    var folderCount = counts.folderCount;
    // Issue #1324: surface excluded count alongside the selected counts so the
    // user has a visible cue that some staged items were removed (parity with
    // Server path).
    // Issue #1350: only count files excluded WITHIN a parent folder that
    // still has included siblings. A whole-folder-removed at root is not
    // "Excluded" — it's just not selected — so it must not inflate this chip.
    var excludedFileCount = typeof this._meaningfulExcludedBrowserCount === 'function'
      ? this._meaningfulExcludedBrowserCount()
      : (typeof this._excludedBrowserKeyCount === 'function' ? this._excludedBrowserKeyCount() : 0);
    var folderNames = this._browserTopFolderNames();
    var groupingStrategy = this._browserGroupingStrategy();
    var recurse = this._browserRecurse();
    var titleSource = this._browserBatchTitleSource();
    var resolvedTitle = this._browserBatchResolvedTitle();
    if (!this._browserFiles.length) {
      // Issue: avoid duplicate empty-state in the wizard right pane. The
      // companion call to _renderBrowserSourceEntries(false) already renders
      // the "No browser files staged yet" message, and the Organize step that
      // shows controls renders its own empty state from _renderBrowserOrganizeRows.
      // Return empty here so neither path shows two stacked empty rows.
      return '';
    }
    var titleSourceOptions = folderCount
      ? '<option value="folder"' + (titleSource === 'folder' ? ' selected' : '') + '>Folder name</option><option value="first-file"' + (titleSource === 'first-file' ? ' selected' : '') + '>First file</option><option value="custom"' + (titleSource === 'custom' ? ' selected' : '') + '>Custom</option>'
      : '<option value="first-file"' + (titleSource === 'first-file' ? ' selected' : '') + '>First file</option><option value="custom"' + (titleSource === 'custom' ? ' selected' : '') + '>Custom</option>';
    // Issue #1356: Step 1 right pane uses chips instead of a key/value summary box.
    // Source path is intentionally omitted (it's implicit -- this is Browser Upload).
    // Issue #1356: chips mirror the entry-row "⚠ N excluded" chip style which
    // uses inline unicode glyphs (no <ha-icon>) so the icon and label share a
    // baseline naturally — matching what the user sees on the folder card.
    var chipMarkup = ''
      + '<div class="button-row intake-summary-chips">'
      + '  <span class="chip">📁 ' + String(folderCount) + ' Folders</span>'
      + '  <span class="chip">📄 ' + String(fileCount) + ' Files</span>'
      + (excludedFileCount > 0 ? '  <span class="chip warn">⚠ ' + String(excludedFileCount) + ' Excluded</span>' : '')
      + '</div>';
    return ''
      + (showControls
        ? '<div class="result-summary">'
          + '  <div class="result-line"><span>Selected files/folders</span><strong>' + String(fileCount) + ' files, ' + String(folderCount) + ' folders' + (excludedFileCount > 0 ? ', ' + String(excludedFileCount) + ' excluded' : '') + '</strong></div>'
          + (groupingStrategy !== 'flat'
            ? '  <div class="result-line"><span>Model/Group Title</span><strong>' + escapeHtml(resolvedTitle || 'Folder') + '</strong></div>'
            : '')
          + '</div>'
        : chipMarkup)
      + (showControls
        ? '<div class="item-grid">'
          + (folderCount
            ? '    <div class="field" style="grid-column:1 / -1;"><label>Group / Split</label><select class="select" data-action="browser-grouping">' + groupingOptionsHtml(groupingStrategy, 'folder') + '</select></div><div class="field"><label>Folder Scope</label><select class="select" data-action="browser-recurse"><option value="true"' + (recurse ? ' selected' : '') + '>Include subfolders (recursive)</option><option value="false"' + (!recurse ? ' selected' : '') + '>Just this folder</option></select></div>'
            : '')
          + (folderCount && recurse
            ? '    <div class="field"><label>Folder Structure</label><select class="select" data-action="browser-preserve-structure"><option value="true"' + (this._browserFiles[0] && this._browserFiles[0].preserve_folder_structure !== false ? ' selected' : '') + '>Preserve</option><option value="false"' + (this._browserFiles[0] && this._browserFiles[0].preserve_folder_structure === false ? ' selected' : '') + '>Flatten</option></select></div>'
            : (folderCount ? '    <div class="field" style="visibility:hidden;" aria-hidden="true"><label>Folder Structure</label><select class="select" disabled><option>Hidden</option></select></div>' : ''))
          + '    <div class="field"><label>Title Basis</label><select class="select" data-action="browser-title-source">' + titleSourceOptions + '</select></div>'
          + (groupingStrategy !== 'flat'
            ? '    <div class="field"><label>Model/Group Title</label><input class="input" type="text" value="' + escapeHtml(resolvedTitle) + '" data-action="browser-group-title" placeholder="Folder"></div>'
            : '')
          + '  </div>'
          + ((groupingStrategy === 'flat' && titleSource === 'custom')
            ? '<div class="title-row"><div><div class="title">Per-File Model Names</div><div class="subtitle">Optional overrides. Leave blank to use the cleaned filename-derived model name.</div></div></div>' + this._browserFlatCustomTitleRows()
            : '')
          + '<div class="muted">Organize controls how the selected browser files resolve into models. Validation and Commit reuse the resolved plan shown on the right.</div>'
        : '');
  };

  // Issue #1345: parity with browser side — surface a summary block at the top
  // of the Server right pane so operators see selected files/folders and the
  // resolved planned-model count alongside the per-entry list.
  proto._renderServerWizardSummary = function () {
    var selections = this._selectedList();
    if (!selections.length) {
      return '';
    }
    var fileCount = 0;
    var folderCount = 0;
    selections.forEach(function (entry) {
      if (entry && entry.type === 'folder') {
        folderCount += 1;
      } else {
        fileCount += 1;
      }
    });
    var excludedItems = Array.isArray(this._excludedItems) ? this._excludedItems : [];
    var excludedCount = excludedItems.length;
    // Issue #1356: Step 1 right pane uses chips instead of a key/value summary
    // box. Source path is intentionally omitted from the right pane (the user
    // can see/navigate it on the left).
    // Issue #1356: chips mirror the entry-row "⚠ N excluded" chip style which
    // uses inline unicode glyphs (no <ha-icon>) so the icon and label share a
    // baseline naturally — matching what the user sees on the folder card.
    return ''
      + '<div class="button-row intake-summary-chips">'
      + '  <span class="chip">📁 ' + String(folderCount) + ' Folders</span>'
      + '  <span class="chip">📄 ' + String(fileCount) + ' Files</span>'
      + (excludedCount > 0 ? '  <span class="chip warn">⚠ ' + String(excludedCount) + ' Excluded</span>' : '')
      + '</div>';
  };

  proto._invalidateWizardArtifacts = function (options) {
    var settings = options || {};
    var uploadId = this._preparedUploadId;
    this._preparedUploadId = null;
    this._validationData = null;
    this._validationDecisionMap = {};
    this._validationInfoExpandedMap = {};
    this._validationImagePreview = null;
    if (settings.clearPreview !== false) {
      this._previewData = null;
    }
    if (settings.deletePrepared && uploadId && this._hass) {
      callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_delete_intake_upload', {
        upload_id: uploadId,
      }).catch(function () {});
    }
  };

  proto._closeWizard = function (options) {
    var force = !!(options && options.force);
    var isDirty = typeof this._isWizardDirty === 'function' && this._isWizardDirty();
    if (!force && isDirty) {
      return originalCloseWizard.call(this, options);
    }
    if (typeof this._invalidateWizardArtifacts === 'function') {
      this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
    }
    return originalCloseWizard.call(this, options);
  };

  proto._refreshWizardPreview = async function () {
    if (!this._wizardOpen || this._wizardStep < 2) {
      return;
    }
    var requestToken = Number(this._previewRefreshToken || 0) + 1;
    this._previewRefreshToken = requestToken;
    this._previewLoading = true;
    this._render();
    try {
      if (this._wizardMode === 'browser') {
        this._previewData = buildBrowserPlanPreview(this);
        this._syncGroupDestinationsFromPreview();
      } else {
        var selections = this._serverPayloadSelections('server');
        if (!selections.length) {
          this._previewData = null;
          this._groupDestinations = [];
        } else {
          this._previewData = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_plan_intake', {
            source_entries: selections,
          });
          this._syncGroupDestinationsFromPreview();
        }
      }
    } catch (error) {
      // Surface the failure rather than silently emptying the preview, which
      // previously rendered as a blank "Choose Destination" step with no clue
      // why. Operators need to see backend errors (e.g., 403 path_not_allowed
      // from intake plan when a selected path is no longer within the allowed
      // intake roots) so they can recover.
      this._previewData = null;
      this._groupDestinations = [];
      var msg = error && error.message ? String(error.message) : 'Could not generate intake plan.';
      this._error = 'Plan failed: ' + msg;
      try { console.warn('[model-catalog intake] plan_intake failed:', error); } catch (_logErr) { /* no-op */ }
    } finally {
      if (this._previewRefreshToken === requestToken) {
        this._previewLoading = false;
        this._render();
      }
    }
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
          if (!String(plan.target_folder_slug || '').trim()) {
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
          payload.target_folder_slug = String(plan.target_folder_slug || '').trim();
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
        ? 'Create a new Working Files folder.'
        : 'Create a new Catalog model.';
    }
    if (selected) {
      return String(selected.primary || '')
        + (selected.secondary ? ' - ' + String(selected.secondary) : '')
        + (destination === 'working' ? ' - existing folder title preserved' : ' - existing model name preserved');
    }
    return destination === 'working'
      ? 'Select an existing Working Files folder. Existing folder title is preserved.'
      : 'Select an existing Catalog model. Existing model name is preserved.';
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
    var slug = String((result && result.slug) || '').trim();
    var displayTitle = String((result && (result.display_title || result.name)) || 'Folder').trim();
    var fileCount = result && result.file_count != null ? Number(result.file_count) : null;
    return {
      id: slug,
      primary: displayTitle,
      secondary: [
        slug && slug !== displayTitle ? slug : '',
        fileCount != null ? String(fileCount) + ' files' : '',
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
        response = await callServiceWithResponse(this._hass, 'rest_command', 'model_catalog_list_working_folders', {
          q: query,
          limit: 8,
          offset: 0,
        });
        this._updateGroupDestinationState(groupIndex, {
          lookup_loading: false,
          lookup_error: '',
          lookup_results: Array.isArray(response && response.folders) ? response.folders : [],
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
        target_folder_slug: String(workingMeta.id || '').trim(),
        model_ref: '',
        selected_summary: workingMeta,
      });
    } else {
      var curatedMeta = this._curatedLookupResultMeta(result);
      this._updateGroupDestinationState(groupIndex, {
        model_ref: curatedMeta.id,
        target_folder_slug: '',
        selected_summary: curatedMeta,
      });
    }
    this._render();
  };

  proto._renderEmptyDestinationState = function () {
    // Surface backend plan warnings (e.g. "no_eligible_files") so the operator
    // understands why their selection produced zero planned groups instead of
    // seeing a generic "Return to Organize" message that misdirects them.
    var warnings = this._previewData && Array.isArray(this._previewData.warnings)
      ? this._previewData.warnings
      : [];
    if (this._previewLoading) {
      return '<div class="state-row">Generating intake plan...</div>';
    }
    if (!this._previewData) {
      return '<div class="state-row">No selection yet. Return to Choose Files to pick folders or files for intake.</div>';
    }
    if (warnings.length) {
      var items = warnings.map(function (warning) {
        var w = warning || {};
        var msg = String(w.message || w.code || 'Unknown issue').replace(/\/assets\//gi, '');
        return '<li>' + escapeHtml(msg) + '</li>';
      }).join('');
      return ''
        + '<div class="state-row" style="border-left:3px solid #f59e0b; text-align:left;">'
        + '  <div><strong>No eligible model files found in the current selection.</strong></div>'
        + '  <ul style="margin:6px 0 0 18px; padding:0;">' + items + '</ul>'
        + '  <div class="muted" style="margin-top:6px;">Return to Choose Files and pick a different folder, or add eligible model files (e.g. .3mf, .stl) to the selected folder.</div>'
        + '</div>';
    }
    return '<div class="state-row">No eligible model files were found in the current selection. Return to Choose Files to pick a different folder.</div>';
  };

  proto._renderDestinationAssignments = function () {
    var plannedModels = this._previewData && Array.isArray(this._previewData.planned_models)
      ? this._previewData.planned_models
      : [];
    var plans = this._syncGroupDestinationsFromPreview();
    if (!plannedModels.length) {
      return this._renderEmptyDestinationState();
    }
    return '<div class="entries">' + plannedModels.map(function (model, index) {
      var plan = plans[index] || {};
      var destination = String(plan.destination || 'curated');
      var matchMode = String(plan.match_mode || 'new');
      var isWorking = destination === 'working';
      var resultRows = '';
      if (matchMode === 'existing') {
        if (plan.lookup_loading) {
          resultRows = '<div class="muted">Searching existing ' + escapeHtml(isWorking ? 'Working Files folders' : 'Catalog models') + '...</div>';
        } else if (plan.lookup_error) {
          resultRows = '<div class="muted">' + escapeHtml(plan.lookup_error) + '</div>';
        } else if (Array.isArray(plan.lookup_results) && plan.lookup_results.length) {
          resultRows = '<div class="entries">' + plan.lookup_results.map(function (result, resultIndex) {
            var meta = isWorking ? this._workingLookupResultMeta(result) : this._curatedLookupResultMeta(result);
            var isSelected = isWorking
              ? String(plan.target_folder_slug || '') === String(meta.id || '')
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
        + '  <div class="entry-top"><div><div class="entry-name">' + escapeHtml(model.title || ('Group ' + String(index + 1))) + '</div><div class="entry-path">' + String(model.file_count || 0) + ' files - ' + String(model.model_file_count || 0) + ' model, ' + String(model.media_file_count || 0) + ' media, ' + String(model.archive_file_count || 0) + ' archive, ' + String(model.supporting_file_count || 0) + ' supporting</div></div><div class="button-row"><span class="chip">' + escapeHtml(model.strategy || 'none') + '</span></div></div>'
        + '  <div class="item-grid">'
        + '    <div class="field"><label>Destination</label><select class="select" data-action="group-destination" data-group-index="' + String(index) + '"><option value="curated"' + (destination === 'curated' ? ' selected' : '') + '>Catalog</option><option value="working"' + (destination === 'working' ? ' selected' : '') + '>Working Files</option></select></div>'
        + '    <div class="field"><label>Mode</label><select class="select" data-action="group-match-mode" data-group-index="' + String(index) + '"><option value="new"' + (matchMode === 'new' ? ' selected' : '') + '>New</option><option value="existing"' + (matchMode === 'existing' ? ' selected' : '') + '>Add To Existing</option></select></div>'
        + '    <div class="field"><label>Selection</label><div class="muted">' + escapeHtml(this._destinationSelectionSummary(plan)) + '</div></div>'
        + '  </div>'
        + (matchMode === 'existing'
          ? '  <div class="item-grid">'
            + '    <div class="field"><label>' + escapeHtml(isWorking ? 'Find Working Folder' : 'Find Catalog Model') + '</label><input class="input" type="text" value="' + escapeHtml(plan.lookup_query || '') + '" data-action="group-lookup-query" data-group-index="' + String(index) + '" placeholder="Search by name or id"></div>'
            + '    <div class="field"><label>&nbsp;</label><button class="button" data-action="run-destination-search" data-group-index="' + String(index) + '"' + (plan.lookup_loading ? ' disabled' : '') + '>Search</button></div>'
            + '  </div>'
            + resultRows
          : '<div class="muted">This group will create a new ' + escapeHtml(isWorking ? 'Working Files folder.' : 'Catalog model.') + '</div>')
        + '</article>';
    }, this).join('') + '</div>';
  };

  proto._renderDestinationSummary = function () {
    var plannedModels = this._previewData && Array.isArray(this._previewData.planned_models)
      ? this._previewData.planned_models
      : [];
    var plans = this._syncGroupDestinationsFromPreview();
    if (!plannedModels.length) {
      return this._renderEmptyDestinationState();
    }
    return '<div class="entries">' + plannedModels.map(function (model, index) {
      var plan = plans[index] || {};
      var destination = String(plan.destination || 'curated') === 'working' ? 'Working Files' : 'Catalog';
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
      var totalBrowserBytes = browserFiles.reduce(function (sum, entry) {
        var size = entry && entry.file ? Number(entry.file.size || 0) : 0;
        return sum + (Number.isFinite(size) ? size : 0);
      }, 0);
      this._uploadProgress = {
        phase: 'Uploading files',
        detail: 'Preparing browser upload payload',
        mode: 'indeterminate',
        percent: null,
        bytes_done: null,
        bytes_total: totalBrowserBytes,
      };
      if (typeof this._setBusyPhase === 'function') {
        this._setBusyPhase('Uploading files', 'Preparing browser upload payload');
      }
      response = await uploadBrowserFilesWithFallback(this._hass, sidecarBaseUrl, browserFiles, payloadSelections, cleanupPolicy, {
        onPhase: function (phaseCode) {
          if (phaseCode === 'encoding_files') {
            this._uploadProgress = {
              phase: 'Uploading files',
              detail: 'Encoding files for fallback upload mode',
              mode: 'indeterminate',
              percent: null,
              bytes_done: null,
              bytes_total: totalBrowserBytes,
            };
            if (typeof this._setBusyPhase === 'function') {
              this._setBusyPhase('Uploading files', 'Encoding files for fallback upload mode');
            }
            this._render();
            return;
          }
          if (phaseCode === 'submitting_request') {
            this._uploadProgress = {
              phase: 'Preparing intake job',
              detail: 'Submitting upload request',
              mode: 'indeterminate',
              percent: null,
              bytes_done: null,
              bytes_total: totalBrowserBytes,
            };
            if (typeof this._setBusyPhase === 'function') {
              this._setBusyPhase('Preparing intake job', 'Submitting upload request');
            }
            this._render();
          }
        }.bind(this),
        onUploadProgress: function (progressPayload) {
          var loaded = Number(progressPayload && progressPayload.loaded || 0);
          var total = Number(progressPayload && progressPayload.total || 0);
          var lengthComputable = !!(progressPayload && progressPayload.lengthComputable && total > 0);
          if (lengthComputable) {
            var percent = Math.max(0, Math.min(100, Math.round((loaded / total) * 100)));
            this._uploadProgress = {
              phase: 'Uploading files',
              detail: 'Transferring browser files',
              mode: 'determinate',
              percent: percent,
              bytes_done: loaded,
              bytes_total: total,
            };
            if (typeof this._updateUploadProgress === 'function') {
              this._updateUploadProgress(progressPayload, {
                files_total: browserFiles.length,
                bytes_total: totalBrowserBytes,
              });
            } else {
              this._render();
            }
            return;
          }
          this._uploadProgress = {
            phase: 'Uploading files',
            detail: 'Preparing files for upload',
            mode: 'indeterminate',
            percent: null,
            bytes_done: null,
            bytes_total: totalBrowserBytes,
          };
          this._render();
        }.bind(this),
      });
    } else {
      this._uploadProgress = null;
      if (typeof this._setBusyPhase === 'function') {
        this._setBusyPhase('Preparing intake job', 'Resolving server selections and staging queue item');
      }
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
    if (typeof this._setBusyPhase === 'function') {
      this._setBusyPhase('Validating plan', 'Preparing and validating resolved output');
    }
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
      this._validationDecisionMap = {};
      this._validationInfoExpandedMap = {};
      this._validationImagePreview = null;
      this._status = this._validationData.validation_state === 'ready'
        ? 'Validation snapshot prepared. Review the destination assignments, then commit.'
        : 'Validation finished with blockers. Resolve them before commit.';
      return this._validationData;
    } catch (error) {
      this._error = error && error.message ? String(error.message) : 'Could not validate the intake batch.';
      return null;
    } finally {
      this._uploadProgress = null;
      if (typeof this._clearBusyState === 'function') {
        this._clearBusyState();
      }
      this._loading = false;
      this._render();
    }
  };

  proto._validationFindingKey = function (checkKey, finding, index) {
    var entry = finding && typeof finding === 'object' ? finding : {};
    var parts = [
      String(checkKey || ''),
      String(entry.path || ''),
      String(entry.filename || ''),
      String(entry.violation_code || ''),
      String(index || 0),
    ];
    return parts.join('|').toLowerCase();
  };

  proto._validationDecisionForFinding = function (checkKey, finding, index) {
    var key = this._validationFindingKey(checkKey, finding, index);
    if (!this._validationDecisionMap || typeof this._validationDecisionMap !== 'object') {
      this._validationDecisionMap = {};
    }
    return String(this._validationDecisionMap[key] || 'review').trim();
  };

  proto._setValidationDecisionForFinding = function (checkKey, finding, index, decision) {
    var key = this._validationFindingKey(checkKey, finding, index);
    if (!this._validationDecisionMap || typeof this._validationDecisionMap !== 'object') {
      this._validationDecisionMap = {};
    }
    var next = Object.assign({}, this._validationDecisionMap);
    var normalizedDecision = String(decision || 'review').trim().toLowerCase();
    if (!normalizedDecision || normalizedDecision === 'review') {
      delete next[key];
    } else {
      next[key] = normalizedDecision;
    }
    this._validationDecisionMap = next;
    return key;
  };

  proto._persistValidationActionDecision = function (payload) {
    var uploadId = this._validationData && this._validationData.upload_id
      ? String(this._validationData.upload_id)
      : '';
    if (!uploadId || !this._hass) {
      return Promise.resolve(null);
    }
    var sidecarBaseUrl = this._resolveSidecarUrl();
    return postJsonWithAuth(
      this._hass,
      sidecarBaseUrl.replace(/\/$/, '') + '/api/intake/items/' + encodeURIComponent(uploadId) + '/validation-actions',
      { action: payload }
    );
  };

  proto._validationOverrideSummary = function () {
    var checks = this._validationData && Array.isArray(this._validationData.checks)
      ? this._validationData.checks
      : [];
    var duplicateCheckKeys = { duplicate_scan: true, batch_duplicate_scan: true };
    var totalFindings = 0;
    var pendingFindings = 0;
    var resolvedFindings = 0;
    var hasNonOverrideBlocker = false;
    var resolvedDecisions = {
      allow_duplicate: true,
      keep_both: true,
      exclude_source: true,
      exclude_conflict: true,
      exclude_both: true,
    };

    checks.forEach(function (check) {
      var checkKey = String(check && check.key || '').trim();
      var checkFindings = Array.isArray(check && check.findings) ? check.findings : [];
      if (!duplicateCheckKeys[checkKey]) {
        if (check && check.passed === false) {
          hasNonOverrideBlocker = true;
        }
        return;
      }
      if (!checkFindings.length && check && check.passed === false) {
        hasNonOverrideBlocker = true;
        return;
      }
      checkFindings.forEach(function (finding, findingIndex) {
        totalFindings += 1;
        var decision = this._validationDecisionForFinding(checkKey, finding, findingIndex);
        if (resolvedDecisions[decision]) {
          resolvedFindings += 1;
        } else {
          pendingFindings += 1;
        }
      }, this);
    }, this);

    var hasFindings = totalFindings > 0;
    var canProceed = !hasNonOverrideBlocker && (
      String(this._validationData && this._validationData.validation_state || '').trim().toLowerCase() === 'ready'
      || (hasFindings && pendingFindings === 0)
    );

    return {
      totalFindings: totalFindings,
      pendingFindings: pendingFindings,
      resolvedFindings: resolvedFindings,
      hasNonOverrideBlocker: hasNonOverrideBlocker,
      hasFindings: hasFindings,
      canProceed: canProceed,
      requiresWarningOverride: !hasNonOverrideBlocker && hasFindings && pendingFindings === 0,
    };
  };

  proto._validationReadyForCommit = function () {
    if (!this._validationData || !this._validationData.upload_id) {
      return false;
    }
    var validationState = String(this._validationData.validation_state || '').trim().toLowerCase();
    if (validationState === 'ready') {
      return true;
    }
    if (validationState !== 'duplicate_candidate') {
      return false;
    }
    var summary = this._validationOverrideSummary();
    return !!(summary && summary.canProceed && summary.requiresWarningOverride);
  };

  proto._applyValidationFindingExclusion = function (findingPath) {
    var pathValue = String(findingPath || '').trim();
    if (!pathValue) {
      return false;
    }

    if (this._wizardMode === 'browser') {
      var browserPath = normalizeBrowserRelativePath(pathValue);
      var matched = false;
      (this._browserFiles || []).forEach(function (entry) {
        var relativePath = normalizeBrowserRelativePath(entry && (entry.relative_path || entry.name || '') || '');
        if (relativePath && relativePath === browserPath) {
          this._setBrowserKeyExcluded(this._browserFileKey(entry), true);
          matched = true;
        }
      }, this);
      if (!matched) {
        return false;
      }
    } else {
      var currentExcluded = Array.isArray(this._excludedItems) ? this._excludedItems.slice() : [];
      if (currentExcluded.indexOf(pathValue) === -1) {
        currentExcluded.push(pathValue);
      }
      this._excludedItems = currentExcluded;
    }

    this._status = 'Excluded source item from import. Re-run validation to refresh findings.';
    this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
    this._refreshWizardPreview();
    this._render();
    return true;
  };

  proto._canAdvanceWizard = function () {
    if (this._wizardStep === 2) {
      // Block advancing from Organize to Choose Destination when the resolved
      // plan has zero models. This catches the common case of selecting an
      // empty folder (or a folder of only unsupported files) and prevents the
      // user from sleepwalking into a dead-end Choose Destination step.
      if (this._previewLoading) {
        return false;
      }
      var plannedModels = this._previewData && Array.isArray(this._previewData.planned_models)
        ? this._previewData.planned_models
        : [];
      return plannedModels.length > 0;
    }
    if (this._wizardStep === 3) {
      return this._destinationPlansReady();
    }
    if (this._wizardStep === 4) {
      return this._validationReadyForCommit();
    }
    if (this._wizardStep === 5) {
      return this._destinationPlansReady() && this._validationReadyForCommit();
    }
    return this._wizardMode === 'server' ? this._selectedList().length > 0 : this._activeBrowserFileCount() > 0;
  };

  proto._goToWizardStep = function (stepNumber) {
    var maxStep = this._wizardStepCount();
    var nextStep = Math.max(1, Math.min(maxStep, Number(stepNumber || 1)));
    if (nextStep > this._wizardStep && !this._canAdvanceWizard()) {
      if (this._wizardStep === 2) {
        // Empty-plan guard: tell the user exactly why and where to fix it,
        // instead of silently letting them step into Choose Destination.
        if (this._previewLoading) {
          this._error = 'Still resolving the intake plan. Please wait a moment and try again.';
        } else {
          this._error = 'No models or files will be created from the current selection. Return to Select and pick a folder that contains eligible model files (e.g. .3mf, .stl).';
        }
      } else if (this._wizardStep === 3) {
        this._error = 'Choose a destination for every planned group. Existing matches require a selected target.';
      } else if (this._wizardStep === 4) {
        this._error = this._validationData && this._validationData.upload_id
          ? 'Validation must be ready before commit, or every duplicate finding must have an explicit action.'
          : 'Run validation before continuing.';
      } else {
        this._error = this._wizardMode === 'server'
          ? 'Select at least one server file or folder first.'
          : 'Choose at least one browser file or folder first.';
      }
      this._render();
      return;
    }
    // Issue #1316: navigating backward from the validation or commit step
    // invalidates previous validation results so the user must re-run
    // validation when they return — selections or destinations may have changed.
    if (nextStep < this._wizardStep && this._wizardStep >= 4) {
      this._invalidateWizardArtifacts({ clearPreview: false, deletePrepared: true });
    }
    this._error = '';
    this._wizardStep = nextStep;
    if (nextStep >= 2) {
      this._refreshWizardPreview();
    }
    this._render();
    // Auto-run validation when navigating to the Validate step for the first
    // time (no existing data).  The user can still re-run via the button.
    if (nextStep === 4 && !this._validationData) {
      this._runWizardValidation(false);
    }
  };

  // Issue #1323: lock the host page scroll while the modal is open so the
  // mouse wheel cannot inadvertently scroll the dashboard behind the wizard.
  proto._lockBackgroundScroll = function () {
    try {
      var body = document && document.body;
      if (!body) {
        return;
      }
      if (this.__previousBodyOverflow == null) {
        this.__previousBodyOverflow = body.style.overflow || '';
      }
      body.style.overflow = 'hidden';
    } catch (_err) { /* no-op */ }
  };

  proto._restoreBackgroundScroll = function () {
    try {
      var body = document && document.body;
      if (!body) {
        return;
      }
      if (this.__previousBodyOverflow != null) {
        body.style.overflow = this.__previousBodyOverflow;
        this.__previousBodyOverflow = null;
      } else {
        body.style.overflow = '';
      }
    } catch (_err) { /* no-op */ }
  };

  proto._openWizard = async function (mode, options) {
    this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
    var nextMode = mode === 'server' ? 'server' : 'browser';
    var openOptions = options && typeof options === 'object' ? options : {};
    var requestedStartPath = openOptions.startPath ? String(openOptions.startPath) : '';
    var requestedRootKind = openOptions.rootKind === 'working' ? 'working'
      : openOptions.rootKind === 'intake' ? 'intake'
      : '';
    this._lockBackgroundScroll();
    if (nextMode === 'server') {
      // Issue #1323: open the Server intake directly inside the Model Inbox
      // root so operators do not need to navigate down from "/" each time.
      this._wizardOpen = true;
      this._wizardMode = 'server';
      this._wizardStep = 1;
      this._cleanupPolicyValue = this._defaultCleanupPolicy('server');
      this._commitMode = 'queue';
      this._destinationChoice = 'curated';
      this._error = '';
      this._status = '';
      this._result = null;
      this._selected = {};
      this._excludedItems = []; // Issue #1324
      this._excludedBrowserKeys = {}; // Issue #1324: clear browser exclusions on open
      this._browserSourcePath = '';
      this._clearBrowserFiles();
      await this._setSourceMode('server');
      // Issue #1323: open the Server intake directly inside the configured intake
      // root for the active DB profile (prod vs test) instead of hardcoding
      // "/assets/Model Inbox". The backend resolves intake roots via
      // MODEL_CATALOG_INTAKE_ROOTS / MODEL_CATALOG_INTAKE_ROOTS_TEST, and the
      // currently-allowlisted set is exposed via _roots (loaded by _refresh).
      // Falling back to "/" surfaces the virtual root listing of all configured
      // roots when no preferred root can be determined.
      var preferredRoot = '';
      var preferredKind = 'intake';
      try {
        var roots = Array.isArray(this._roots) ? this._roots : [];
        var kindMatches = requestedRootKind
          ? roots.filter(function (r) { return r && r.kind === requestedRootKind && r.path; })
          : [];
        var pool = kindMatches.length ? kindMatches : roots;
        // Prefer the first accessible root; otherwise fall back to the first
        // configured root regardless of accessibility.
        var firstAccessible = pool.find(function (r) { return r && r.accessible && r.path; });
        var firstAny = pool.find(function (r) { return r && r.path; });
        var chosen = firstAccessible || firstAny || null;
        if (chosen) {
          preferredRoot = chosen.path || '';
          preferredKind = chosen.kind === 'working' ? 'working' : 'intake';
        }
        // If a specific startPath was requested, honor it (only when it is
        // within one of the configured roots — the backend re-enforces this).
        if (requestedStartPath) {
          var startMatch = roots.find(function (r) {
            if (!r || !r.path) { return false; }
            var rp = String(r.path).replace(/\\/g, '/').toLowerCase();
            var sp = String(requestedStartPath).replace(/\\/g, '/').toLowerCase();
            return sp === rp || sp.indexOf(rp + '/') === 0;
          });
          if (startMatch) {
            preferredRoot = requestedStartPath;
            preferredKind = startMatch.kind === 'working' ? 'working' : 'intake';
          }
        }
      } catch (_rootErr) {
        preferredRoot = '';
      }
      this._intakeRootKind = preferredKind;
      if (preferredRoot) {
        try {
          await this._loadBrowse(preferredRoot);
        } catch (_err) {
          this._error = '';
          await this._loadBrowse('/');
        }
      } else {
        await this._loadBrowse('/');
      }
      // If the preferred root returned no entries (e.g., transient API hiccup),
      // fall back to the virtual root and clear any stale error from the
      // previous attempt so the wizard does not show a misleading red banner.
      if (!this._browse || !this._browse.path || !this._browse.entries) {
        this._error = '';
        await this._loadBrowse('/');
      }
      // If the fallback succeeded, clear any stale error from the prior attempt.
      if (this._browse && this._browse.entries) {
        this._error = '';
      }
      return;
    }
    this._browserSourcePath = '';
    return originalOpenWizard.call(this, mode, openOptions);
  };

  proto._closeWizard = function (options) {
    var force = !!(options && options.force);
    if (!force && typeof this._isWizardDirty === 'function' && this._isWizardDirty()) {
      if (typeof this._openWizardCloseConfirm === 'function') {
        this._openWizardCloseConfirm();
        return;
      }
    }
    this._wizardCloseConfirmOpen = false;
    this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
    this._wizardOpen = false;
    this._wizardMode = '';
    this._wizardStep = 1;
    this._cleanupPolicyValue = null;
    this._commitMode = 'queue';
    this._destinationChoice = 'curated';
    this._groupDestinations = [];
    this._previewLoading = false;
    this._selected = {};
    this._excludedItems = []; // Issue #1324
    this._excludedBrowserKeys = {}; // Issue #1324: clear browser exclusions on close
    this._highlightSelection = null;
    this._browserSourcePath = '';
    this._clearBrowserFiles();
    // Issue #1323: release the background scroll lock when the modal closes.
    this._restoreBackgroundScroll();
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
    this._browserSourcePath = '';
    this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
    this._refreshWizardPreview();
  };

  // Issue #1324: in the wizard the per-file Remove button should mark the entry
  // as excluded (consistent with Server path semantics) instead of physically
  // dropping it from _browserFiles. The entry stays in the left tree with a
  // strike-through and Restore button, and disappears from the staged list /
  // plan / upload payload via _filterBrowserFilesForSubmit. The home-card's
  // legacy remove handler still routes through proto._removeBrowserFile, so
  // we override it here for the wizard surface.
  proto._removeBrowserFile = function (key) {
    var normalizedKey = String(key || '');
    if (!normalizedKey) {
      return;
    }
    this._setBrowserKeyExcluded(normalizedKey, true);
    this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
    this._refreshWizardPreview();
    this._render();
  };

  proto._renderBrowserSelectionSummary = function () {
    return this._renderBrowserWizardSummary(true);
  };

  // Issue #1324: inject excluded_items into every folder selection payload so
  // the backend intake_grouping.py _prefilter_excluded_items() can honour them.
  proto._serverPayloadSelections = function (sourceMode) {
    var selections = originalServerPayloadSelections
      ? originalServerPayloadSelections.call(this, sourceMode)
      : [];
    var excludedItems = Array.isArray(this._excludedItems) ? this._excludedItems : [];
    if (!excludedItems.length || !selections || !selections.length) {
      return selections;
    }
    return selections.map(function (sel) {
      return Object.assign({}, sel, { excluded_items: excludedItems });
    });
  };

  // Issue #1322: replace original browser file row renderer so we drop the noisy
  // "browser"/"single file" chips, surface a file-type icon top right, and let
  // CSS left-align the title/path block next to the preview square.
  proto._renderBrowserFileRows = function (showActions) {
    if (!this._browserFiles.length) {
      return '<div class="state-row">No browser files staged yet. Add files or a folder to begin.</div>';
    }
    var formatBytes = (window.ModelCatalogIntakeShared && window.ModelCatalogIntakeShared.formatBytes) || function (n) { return String(n || 0); };
    var card = this;
    return '<div class="entries">' + this._browserFiles.map(function (entry) {
      var relativePath = String(entry.relative_path || entry.name || '').replace(/\\/g, '/');
      var pathParts = relativePath.split('/').filter(function (part) { return !!part; });
      var displayName = (window.ModelCatalogIntakeShared && window.ModelCatalogIntakeShared.basename
        ? window.ModelCatalogIntakeShared.basename(relativePath || entry.name || '')
        : relativePath) || entry.name || relativePath || 'upload.bin';
      var folderPath = pathParts.length > 1 ? pathParts.slice(0, -1).join('/') : '';
      var previewUrl = String(entry.preview_url || '');
      var previewMarkup = previewUrl
        ? '<div class="entry-thumb"><img class="entry-thumb-image" src="' + escapeHtml(previewUrl) + '" alt="Image preview for ' + escapeHtml(displayName) + '" loading="lazy" decoding="async"></div>'
        : '<div class="entry-thumb placeholder">No preview</div>';
      return ''
        + '<article class="entry-row">'
        + '  <div class="entry-top">'
        + previewMarkup
        + '    <div class="entry-main">'
        + '      <div class="entry-name">' + escapeHtml(displayName) + '</div>'
        // Issue #1323: show only the folder path (not the file itself) under
        // the filename. Loose single-file picks have no folder path so we
        // omit the line entirely instead of repeating the filename.
        + (folderPath
          ? '      <div class="entry-path">' + escapeHtml(folderPath) + '</div>'
          : '')
        + '      <div class="muted">' + escapeHtml(formatBytes(entry.size_bytes || 0)) + '</div>'
        + '    </div>'
        + '    ' + entryTypeIconMarkup(relativePath, false)
        + '  </div>'
        + (showActions
          ? '  <div class="entry-actions"><button class="button warn" data-action="remove-browser-file" data-key="' + escapeHtml(card._browserFileKey(entry)) + '">Remove</button></div>'
          : '')
        + '</article>';
    }).join('') + '</div>';
  };

  proto._renderBrowserSourceEntries = function (showActions) {
    var files = this._browserFiles || [];
    if (!files.length) {
      return '<div class="state-row">No browser files staged yet. Add files or a folder to begin.</div>';
    }
    var formatBytes = (window.ModelCatalogIntakeShared && window.ModelCatalogIntakeShared.formatBytes) || function (n) { return String(n || 0); };
    var card = this;

    // Issue #1354: the right pane mirrors the Server right pane contract —
    // top-level uploaded folders appear as a single folder row (NOT recursive
    // file lists), and loose files (no parent folder) appear as individual
    // file rows. Excluding individual items inside a folder on the left does
    // NOT collapse the folder row on the right; it only adds a "⚠ N excluded"
    // chip. A folder disappears from the right pane only when ALL of its
    // descendants are excluded (Server parity: remove-folder == deselect).
    // Issue #1349: each row remains a click-to-jump affordance back to the
    // staged-tree on the left.
    if (!showActions) {
      // Group all (including excluded) files by their top-level folder so the
      // folder row is stable even while individual files are excluded.
      var folderGroups = {};
      var folderOrder = [];
      var looseFiles = [];
      files.forEach(function (entry) {
        var relativePath = normalizeBrowserRelativePath(entry.relative_path || entry.name || '');
        var rootKey = browserRootKey(relativePath);
        if (rootKey) {
          if (!folderGroups[rootKey]) {
            folderGroups[rootKey] = { total: 0, excluded: 0 };
            folderOrder.push(rootKey);
          }
          folderGroups[rootKey].total += 1;
          if (card._isBrowserKeyExcluded(card._browserFileKey(entry))) {
            folderGroups[rootKey].excluded += 1;
          }
        } else if (!card._isBrowserKeyExcluded(card._browserFileKey(entry))) {
          looseFiles.push(entry);
        }
      });
      // A folder disappears from the right pane when all of its files are
      // excluded (parity with Server's remove-selection -> drops from right).
      var visibleFolders = folderOrder.filter(function (rootKey) {
        var info = folderGroups[rootKey];
        return info.total > info.excluded;
      });
      visibleFolders.sort(function (a, b) { return a.localeCompare(b); });
      looseFiles.sort(function (a, b) {
        var ap = String(a.relative_path || a.name || '');
        var bp = String(b.relative_path || b.name || '');
        return ap.localeCompare(bp);
      });
      if (!visibleFolders.length && !looseFiles.length) {
        return '<div class="state-row">No browser files staged yet. Add files or a folder to begin.</div>';
      }
      var folderMarkup = visibleFolders.map(function (rootKey) {
        var info = folderGroups[rootKey];
        var activeCount = info.total - info.excluded;
        var countLine = info.excluded > 0
          ? String(activeCount) + ' files · ' + String(info.excluded) + ' excluded'
          : String(info.total) + ' files';
        var exclusionChip = info.excluded > 0
          ? '<span class="chip warn" title="Items excluded from this folder\'s intake">⚠ ' + String(info.excluded) + ' excluded</span>'
          : '';
        return ''
          + '<article class="entry-row selected right-pane-jump" data-browse-key="' + escapeHtml(rootKey) + '" data-action="jump-browser-parent" data-parent="' + escapeHtml(rootKey) + '" title="Jump to this folder on the left">'
          + '  <div class="entry-top">'
          + folderPreviewMarkup()
          + '    <div class="entry-main">'
          + '      <div class="entry-name">' + escapeHtml(rootKey) + '</div>'
          + '      <div class="entry-path">' + escapeHtml(formatBrowserPathForDisplay(rootKey)) + '</div>'
          + '      <div class="muted">' + escapeHtml(countLine) + '</div>'
          + '    </div>'
          + '    ' + entryTypeIconMarkup(rootKey, true)
          + '  </div>'
          + '  <div class="entry-actions">'
          + '<span class="chip ok">Selected</span>'
          + exclusionChip
          + '<button class="button warn" data-action="remove-browser-folder" data-path="' + escapeHtml(rootKey) + '">Remove</button>'
          + '  </div>'
          + '</article>';
      }).join('');
      var fileMarkup = looseFiles.map(function (entry) {
        var relativePath = normalizeBrowserRelativePath(entry.relative_path || entry.name || '');
        var displayName = String(entry.name || relativePath || '');
        var parentPath = browserParentRelativePath(relativePath);
        var previewUrl = String(entry.preview_url || '');
        var previewMarkup = previewUrl
          ? '<div class="entry-thumb"><img class="entry-thumb-image" src="' + escapeHtml(previewUrl) + '" alt="Image preview for ' + escapeHtml(displayName) + '" loading="lazy" decoding="async"></div>'
          : '<div class="entry-thumb placeholder">No preview</div>';
        return ''
          + '<article class="entry-row selected right-pane-jump" data-browse-key="' + escapeHtml(card._browserFileKey(entry)) + '" data-action="jump-browser-parent" data-parent="' + escapeHtml(parentPath) + '" title="Jump to parent folder on the left">'
          + '  <div class="entry-top">'
          + previewMarkup
          + '    <div class="entry-main">'
          + '      <div class="entry-name">' + escapeHtml(displayName) + '</div>'
          + (parentPath
            ? '      <div class="entry-path">' + escapeHtml(formatBrowserPathForDisplay(parentPath)) + '</div>'
            : '')
          + '      <div class="muted">' + escapeHtml(formatBytes(entry.size_bytes || 0)) + '</div>'
          + '    </div>'
          + '    ' + entryTypeIconMarkup(relativePath, false)
          + '  </div>'
          + '  <div class="entry-actions">'
          + '<span class="chip ok">Selected</span>'
          + '<button class="button warn" data-action="remove-browser-file" data-key="' + escapeHtml(card._browserFileKey(entry)) + '">Remove</button>'
          + '  </div>'
          + '</article>';
      }).join('');
      return '<div class="entries">' + folderMarkup + fileMarkup + '</div>';
    }

    // Left pane (showActions=true): tree-navigated browse with Remove/Restore
    // actions. This is the only place the user navigates browser-source
    // folders; the right pane is a flat selection summary.
    var treeFiles = files;
    var tree = buildBrowserSourceTree(treeFiles);
    var currentPath = normalizeBrowserRelativePath(this._browserSourcePath || '');
    var node = getBrowserTreeNode(tree, currentPath);
    if (currentPath && (!node || node.path !== currentPath)) {
      currentPath = '';
      this._browserSourcePath = '';
      node = tree;
    }
    var folderNames = Object.keys(node.folders || {}).sort();
    var fileRows = (node.files || []).slice().sort(function (a, b) {
      return String(a.name || '').localeCompare(String(b.name || ''));
    });
    if (!folderNames.length && !fileRows.length) {
      return '<div class="state-row">No entries available at this path.</div>';
    }
    var foldersMarkup = folderNames.map(function (folderName) {
      var folderNode = node.folders[folderName];
      var folderPath = folderNode.path;
      var archiveContainerName = !currentPath ? getBrowserArchiveContainerName(folderNode, folderPath) : '';
      var isArchiveFolder = !!archiveContainerName;
      var displayFolderName = isArchiveFolder ? archiveContainerName : folderName;
      var fileCount = 0;
      // Issue #1324: count active vs excluded descendants so the folder row
      // can mirror the Server path (⚠ N excluded badge + Restore when fully
      // excluded) for parity across paths.
      var excludedCount = 0;
      var pending = [folderNode];
      while (pending.length) {
        var next = pending.pop();
        (next.files || []).forEach(function (fileItem) {
          fileCount += 1;
          if (card._isBrowserKeyExcluded(card._browserFileKey(fileItem.entry || {}))) {
            excludedCount += 1;
          }
        });
        Object.keys(next.folders || {}).forEach(function (k) {
          pending.push(next.folders[k]);
        });
      }
      var activeCount = fileCount - excludedCount;
      var fullyExcluded = fileCount > 0 && activeCount === 0;
      // Issue #1350: unify with Server path styling.
      //   At root (currentPath==='') the visible folders ARE the user's
      //   explicit selections → solid border + "Selected" chip + Remove.
      //   At non-root (drilled into a parent) sub-folders are children of
      //   that selection → dashed border + "Included in Selection" + Remove.
      //   Fully-excluded folders inside a parent → dashed duller border +
      //   "Excluded" + Select.
      //   Fully-excluded folders AT ROOT → NEUTRAL (no border, no chip)
      //   because there is no parent context that they're excluded from —
      //   the user simply hasn't selected them. They stay listed so the
      //   user can re-Select without re-uploading.
      var atRoot = !currentPath;
      var isSelected = !fullyExcluded && atRoot;
      var indirectlySelected = !fullyExcluded && !atRoot;
      var excludedNested = fullyExcluded && !atRoot;
      var notSelectedAtRoot = fullyExcluded && atRoot;
      var folderRowClass = 'entry-row'
        + (isSelected ? ' selected' : '')
        + (indirectlySelected ? ' included-in-selection' : '')
        + (excludedNested ? ' excluded' : '');
      var countLine = fullyExcluded
        ? String(fileCount) + ' files (none selected)'
        : (excludedCount > 0
          ? String(activeCount) + ' files · ' + String(excludedCount) + ' excluded'
          : String(fileCount) + ' files');
      var folderActionButton = '';
      if (fullyExcluded) {
        // Issue #1350: label parity with Server path — "Select" not "Restore".
        folderActionButton = '    <button class="button primary" data-action="restore-browser-folder" data-path="' + escapeHtml(folderPath) + '">Select</button>';
      } else {
        folderActionButton = '    <button class="button warn" data-action="remove-browser-folder" data-path="' + escapeHtml(folderPath) + '">Remove</button>';
      }
      return ''
        + '<article class="' + folderRowClass + '" data-browse-key="' + escapeHtml(folderPath) + '">'
        + '  <div class="entry-top">'
        + folderPreviewMarkup(isArchiveFolder)
        + '    <div class="entry-main">'
        + '      <div class="entry-name">' + escapeHtml(displayFolderName) + '</div>'
        + '      <div class="entry-path">' + escapeHtml(formatBrowserPathForDisplay(folderPath)) + '</div>'
        + '      <div class="muted">' + escapeHtml(countLine) + '</div>'
        + '    </div>'
        + '    ' + entryTypeIconMarkup(isArchiveFolder ? archiveContainerName : folderPath, true, isArchiveFolder)
        + '  </div>'
        + '  <div class="entry-actions">'
        + (isSelected ? '    <span class="chip ok">Selected</span>' : '')
        + (indirectlySelected ? '    <span class="chip">Included in Selection</span>' : '')
        + (excludedNested ? '    <span class="chip warn">Excluded</span>' : '')
        + (excludedCount > 0 && !fullyExcluded ? '    <span class="chip warn" title="Items excluded from this folder">⚠ ' + String(excludedCount) + ' excluded</span>' : '')
        + '    <button class="button" data-action="browser-open-path" data-path="' + escapeHtml(folderPath) + '">Open</button>'
        + folderActionButton
        + '  </div>'
        + '</article>';
    }).join('');
    var filesMarkup = fileRows.map(function (item) {
      var entry = item.entry || {};
      var previewUrl = String(entry.preview_url || '');
      var previewMarkup = previewUrl
        ? '<div class="entry-thumb"><img class="entry-thumb-image" src="' + escapeHtml(previewUrl) + '" alt="Image preview for ' + escapeHtml(item.name) + '" loading="lazy" decoding="async"></div>'
        : '<div class="entry-thumb placeholder">No preview</div>';
      // Issue #1350: file rows mirror the folder treatment — at root files
      // are "Selected", inside a folder they are "Included in Selection",
      // excluded files get a duller dashed border with a Select button to
      // re-include them. No strike-through (parity with Server path).
      var entryKey = card._browserFileKey(entry);
      var isExcluded = card._isBrowserKeyExcluded(entryKey);
      // Issue #1350: a removed file at root has no parent context, so it
      // renders neutral (no border, no chip) like an unselected item rather
      // than "Excluded". Inside a folder, an excluded file keeps the dashed
      // duller border + "Excluded" chip because it was excluded from the
      // parent folder's intake.
      var fileSelected = !isExcluded && !currentPath;
      var fileIndirectlySelected = !isExcluded && !!currentPath;
      var fileExcludedNested = isExcluded && !!currentPath;
      var fileRowClass = 'entry-row'
        + (fileSelected ? ' selected' : '')
        + (fileIndirectlySelected ? ' included-in-selection' : '')
        + (fileExcludedNested ? ' excluded' : '');
      var fileActions = isExcluded
        ? '<button class="button primary" data-action="restore-browser-file" data-key="' + escapeHtml(entryKey) + '">Select</button>'
        : '<button class="button warn" data-action="remove-browser-file" data-key="' + escapeHtml(entryKey) + '">Remove</button>';
      return ''
        + '<article class="' + fileRowClass + '" data-browse-key="' + escapeHtml(entryKey) + '">'
        + '  <div class="entry-top">'
        + previewMarkup
        + '    <div class="entry-main">'
        + '      <div class="entry-name">' + escapeHtml(item.name) + '</div>'
        + '      <div class="entry-path">' + escapeHtml(formatBrowserPathForDisplay(currentPath)) + '</div>'
        + '      <div class="muted">' + escapeHtml(formatBytes(entry.size_bytes || 0)) + '</div>'
        + '    </div>'
        + '    ' + entryTypeIconMarkup(item.path, false)
        + '  </div>'
        + '  <div class="entry-actions">'
        + (fileSelected ? '<span class="chip ok">Selected</span>' : '')
        + (fileIndirectlySelected ? '<span class="chip">Included in Selection</span>' : '')
        + (fileExcludedNested ? '<span class="chip warn">Excluded</span>' : '')
        + fileActions
        + '  </div>'
        + '</article>';
    }).join('');
    return '<div class="entries">' + foldersMarkup + filesMarkup + '</div>';
  };

  proto._renderBrowseEntriesMirror = function () {
    if (this._browseLoading) {
      return '<div class="state-row">Loading allowlisted source paths...</div>';
    }
    if (!this._browse.entries.length) {
      return '<div class="state-row">No allowlisted entries are available at this path.</div>';
    }
    var selectedPaths = Object.keys(this._selected || {});
    var excludedItems = Array.isArray(this._excludedItems) ? this._excludedItems : [];
    var orderedEntries = sortedBrowseEntries(this._browse.entries);
    return '<div class="entries">' + orderedEntries.map(function (entry) {
      var selected = !!this._selected[entry.path];
      var childOfSelection = !selected && isChildOfSelection(entry.path, selectedPaths);
      var isExcluded = excludedItems.indexOf(entry.path) !== -1;
      var isArchive = entry.type !== 'folder' && fileKind(entry.path) === 'archive';
      var selectable = entry.selectable !== false;
      var rowClass = 'entry-row'
        + (selected ? ' selected' : '')
        + (childOfSelection ? ' included-in-selection' : '')
        + (isExcluded ? ' excluded' : '');
      var displayName = String(entry.name || basename(entry.path) || entry.path);
      return ''
        + '<article class="' + rowClass + '">'
        + '  <div class="entry-top">'
        + (entry.type === 'folder' || isArchive ? folderPreviewMarkup() : this._serverPreviewMarkup(entry.path, displayName))
        + '    <div class="entry-main">'
        + '      <div class="entry-name">' + escapeHtml(displayName) + '</div>'
        + '      <div class="entry-path">' + escapeHtml(formatBrowsePathForDisplay(this._browse.path || '/')) + '</div>'
        + '    </div>'
        + '    ' + entryTypeIconMarkup(entry.path, entry.type === 'folder')
        + '  </div>'
        + '  <div class="entry-actions">'
        + (selected ? '<span class="chip ok">Selected</span>' : '')
        + (!selected && childOfSelection ? '<span class="chip">Included in Selection</span>' : '')
        + (isArchive ? '<span class="chip">Archive Container</span>' : '')
        + (isExcluded ? '<span class="chip warn">Excluded</span>' : '')
        + ((entry.type === 'folder' || isArchive) ? '<button class="button" data-action="browse-path" data-path="' + escapeHtml(entry.path) + '">Open</button>' : '')
        + (!selectable ? '<span class="chip">View Only</span>' : '')
        + '  </div>'
        + '</article>';
    }, this).join('') + '</div>';
  };

  // Issue #1322 + #1324: file-type icon top right, classed middle block for
  // left-alignment. Issue #1324 adds child-of-selection detection so that when
  // browsing inside a selected folder, each item shows an ✕ Exclude button
  // instead of a Select/Remove toggle. Selected folders also surface a ⚠️ badge
  // when one or more of their children have been excluded.
  proto._renderBrowseEntries = function () {
    if (this._browseLoading) {
      return '<div class="state-row">Loading allowlisted source paths...</div>';
    }
    if (!this._browse.entries.length) {
      return '<div class="state-row">No allowlisted entries are available at this path.</div>';
    }
    var formatBytes = (window.ModelCatalogIntakeShared && window.ModelCatalogIntakeShared.formatBytes) || function (n) { return String(n || 0); };
    var card = this;
    // Issue #1323: the path line under each entry shows only the parent dir.
    var parentDisplayPath = formatBrowsePathForDisplay(this._browse.path || '/');
    // Issue #1324: pre-compute sets needed for child-of-selection and exclusion checks.
    var selectedPaths = Object.keys(card._selected || {});
    var excludedItems = Array.isArray(card._excludedItems) ? card._excludedItems : [];
    var orderedEntries = sortedBrowseEntries(this._browse.entries);
    return '<div class="entries">' + orderedEntries.map(function (entry) {
      var selected = !!card._selected[entry.path];
      var displayName = String(entry.name || (window.ModelCatalogIntakeShared && window.ModelCatalogIntakeShared.basename ? window.ModelCatalogIntakeShared.basename(entry.path) : entry.path) || '');
      var isFolder = entry.type === 'folder';
      var isArchive = !isFolder && fileKind(entry.path) === 'archive';
      var selectable = entry.selectable !== false;
      var previewMarkup = !isFolder && !isArchive
        ? card._serverPreviewMarkup(entry.path, displayName)
        : folderPreviewMarkup(isArchive);
      // Issue #1324: detect whether this entry is inside an already-selected folder.
      var childOfSelection = !selected && isChildOfSelection(entry.path, selectedPaths);
      // Issue #1324: detect whether this entry is explicitly excluded.
      var isExcluded = selectable && excludedItems.indexOf(entry.path) !== -1;
      // Issue #1324: count how many excluded items live under a selected folder.
      var excludedUnder = (selected && isFolder) ? getExcludedItemsUnderPath(entry.path, excludedItems).length : 0;
      // Issue #1349: mark unselected parent folders that contain selected items
      // so the left-side browse tree can show a dashed primary border (vs the
      // solid border for a folder that is itself selected).
      var containsSelection = !selected && isFolder && hasSelectedDescendants(entry.path, selectedPaths);
      var rowClass = 'entry-row'
        + (selected ? ' selected' : '')
        + (childOfSelection ? ' included-in-selection' : '')
        + (containsSelection ? ' contains-selection' : '')
        + (isExcluded ? ' excluded' : '');
      return ''
        + '<article class="' + rowClass + '" data-path="' + escapeHtml(entry.path) + '">'
        + '  <div class="entry-top">'
        + previewMarkup
        + '    <div class="entry-main">'
        + '      <div class="entry-name">' + escapeHtml(displayName) + '</div>'
        + (parentDisplayPath ? '      <div class="entry-path">' + escapeHtml(parentDisplayPath) + '</div>' : '')
        + (!isFolder && entry.size_bytes != null ? '      <div class="muted">' + escapeHtml(formatBytes(entry.size_bytes)) + '</div>' : '')
        + '    </div>'
        + '    ' + entryTypeIconMarkup(entry.path, isFolder, isArchive)
        + '  </div>'
        + '  <div class="entry-actions">'
        // Issue #1350: unified chips/buttons across browser+server paths.
        //   Selected         → solid border + highlighted bg + "Selected" + Remove
        //   Indirectly sel.  → dashed border + highlighted bg + "Included in Selection" + Remove
        //   Excluded         → dashed duller border + no bg + "Excluded" + Select
        //   Contains sel.    → dashed border + no bg + "1 or more children included" + Open + Select
        //   Not selected     → no border + Select (file) / Open + Select (folder)
        + (selected ? '<span class="chip ok" style="align-self:center;">Selected</span>' : '')
        + (childOfSelection && !isExcluded ? '<span class="chip" style="align-self:center;">Included in Selection</span>' : '')
        + (isArchive ? '<span class="chip" style="align-self:center;">Archive Container</span>' : '')
        + (!selectable ? '<span class="chip" style="align-self:center;">View Only</span>' : '')
        + (isExcluded ? '<span class="chip warn" style="align-self:center;">Excluded</span>' : '')
        + (containsSelection ? '<span class="chip" style="align-self:center;">1 or more children included</span>' : '')
        + (selected && excludedUnder > 0 ? '<span class="chip warn" style="align-self:center;" title="Items excluded from this folder">⚠ ' + String(excludedUnder) + ' excluded</span>' : '')
        // Open button for folders and archives (always visible)
        + ((isFolder || isArchive) ? '<button class="button" data-action="browse-path" data-path="' + escapeHtml(entry.path) + '">Open</button>' : '')
        // Action buttons (Issue #1350: use Remove/Select labels consistently):
        //   - excluded item            → Select button (re-include via unexclude-item)
        //   - child of selected folder → Remove button (exclude-item action)
        //   - top-level / unselected   → Select / Remove toggle
        + (!selectable
          ? ''
          : (isExcluded
          ? '<button class="button primary" data-action="unexclude-item" data-path="' + escapeHtml(entry.path) + '">Select</button>'
          : (childOfSelection
            ? '<button class="button warn" data-action="exclude-item" data-path="' + escapeHtml(entry.path) + '" title="Remove this item from the parent folder\'s intake">Remove</button>'
            : '<button class="button ' + (selected ? 'warn' : 'primary') + '" data-action="toggle-selection" data-entry-type="' + escapeHtml(entry.type) + '" data-path="' + escapeHtml(entry.path) + '">' + (selected ? 'Remove' : 'Select') + '</button>')))
        + '  </div>'
        + '</article>';
    }).join('') + '</div>';
  };

  proto._renderServerSelectionRows = function (showSettings) {
    if (!showSettings) {
      // Issue #1343: Select-step right pane shows the chosen entries only —
      // organization chips (scope/grouping/title) belong to the Organize step,
      // and card chrome (icon top-right, formatted parent path, no filename)
      // must match the left pane for visual consistency. Remove is still
      // exposed because users may want to drop an entry from the staged batch.
      var selections = this._selectedList();
      if (!selections.length) {
        return '<div class="state-row">No server files or folders selected yet.</div>';
      }
      var card = this;
      var excludedItems = Array.isArray(card._excludedItems) ? card._excludedItems : [];
      return '<div class="entries">'
        + selections.map(function (entry) {
          var entryName = String(basename(entry.path) || entry.path);
          var isFolder = entry.type === 'folder';
          var isArchive = !isFolder && fileKind(entry.path) === 'archive';
          var previewMarkup = isFolder || isArchive
            ? folderPreviewMarkup(isArchive)
            : card._serverPreviewMarkup(entry.path, entryName);
          var rawPath = String(entry.path || '').replace(/\/+$/, '');
          var slashIdx = rawPath.lastIndexOf('/');
          var parentPath = slashIdx >= 0 ? rawPath.slice(0, slashIdx) : '';
          var displayParentPath = formatBrowsePathForDisplay(parentPath || '/');
          var excludedUnder = (isFolder && excludedItems.length)
            ? getExcludedItemsUnderPath(entry.path, excludedItems).length
            : 0;
          var exclusionChip = excludedUnder > 0
            ? '<span class="chip warn" title="Items excluded from this folder\'s intake">⚠ ' + String(excludedUnder) + ' excluded</span>'
            : '';
          return ''
            + '<article class="entry-row selected right-pane-jump" data-path="' + escapeHtml(entry.path) + '" data-action="jump-server-parent" data-parent="' + escapeHtml(parentPath || '/') + '" title="Jump to parent folder on the left">'
            + '  <div class="entry-top">'
            + previewMarkup
            + '    <div class="entry-main">'
            + '      <div class="entry-name">' + escapeHtml(entryName) + '</div>'
            + '      <div class="entry-path">' + escapeHtml(displayParentPath) + '</div>'
            + '    </div>'
            + '    ' + entryTypeIconMarkup(entry.path, isFolder, isArchive)
            + '  </div>'
            + '  <div class="entry-actions">'
            + '<span class="chip ok">Selected</span>'
            + (isArchive ? '<span class="chip">Archive Container</span>' : '')
            + exclusionChip
            + '<button class="button warn" data-action="remove-selection" data-path="' + escapeHtml(entry.path) + '">Remove</button>'
            + '  </div>'
            + '</article>';
        }).join('') + '</div>';
    }
    var selections = this._selectedList();
    var fileEntries = this._fileSelectionEntries();
    var fileBatchTitleSource = this._fileBatchTitleSource();
    var fileBatchResolvedTitle = this._fileBatchResolvedTitle();
    var fileBatchGrouping = this._fileBatchGroupingStrategy();
    // Issue #1324: pre-compute exclusion context for this render pass.
    var excludedItems = Array.isArray(this._excludedItems) ? this._excludedItems : [];
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
            sourceKey: 'server-file-batch',
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
        var isArchive = entry.type === 'file' && fileKind(entry.path) === 'archive';
        var previewMarkup = entry.type === 'file' && !isArchive
          ? this._serverPreviewMarkup(entry.path, entryName)
          : folderPreviewMarkup(isArchive);
        // Issue #1324: exclusion count chip for selected folders.
        var excludedUnder = (entry.type === 'folder' && excludedItems.length)
          ? getExcludedItemsUnderPath(entry.path, excludedItems).length
          : 0;
        var exclusionChip = excludedUnder > 0
          ? '<span class="chip warn" title="Items excluded from this folder\'s intake">⚠ ' + String(excludedUnder) + ' excluded</span>'
          : '';
        var displayPath = formatBrowsePathForDisplay(entry.path);
        return ''
          + '<article class="entry-row" data-path="' + escapeHtml(entry.path) + '">'
          + '  <div class="entry-top">' + previewMarkup + '<div><div class="entry-name">' + escapeHtml(entryName) + '</div><div class="entry-path">' + escapeHtml(displayPath) + '</div></div><div class="button-row"><span class="chip">' + escapeHtml(entry.type === 'folder' || isArchive ? (isArchive ? 'archive' : entry.type) : entry.type) + '</span>' + (isArchive ? '<span class="chip">Archive Container</span>' : '') + exclusionChip + (this._wizardStep === 2 ? '' : '<button class="button warn" data-action="remove-selection" data-path="' + escapeHtml(entry.path) + '">Remove</button>') + '</div></div>'
          + (entry.type === 'folder'
            ? '<div class="item-grid">'
              + '<div class="field" style="grid-column:1 / -1;"><label>Group / Split</label><select class="select" data-action="selection-grouping" data-path="' + escapeHtml(entry.path) + '">' + groupingOptionsHtml(entry.grouping_strategy, 'folder') + '</select></div>'
              + '<div class="field"><label>Folder Scope</label><select class="select" data-action="selection-recurse" data-path="' + escapeHtml(entry.path) + '"><option value="true"' + (entry.recurse ? ' selected' : '') + '>Include subfolders (recursive)</option><option value="false"' + (!entry.recurse ? ' selected' : '') + '>Just this folder</option></select></div>'
              + (entry.recurse
                ? '<div class="field"><label>Folder Structure</label><select class="select" data-action="selection-preserve-structure" data-path="' + escapeHtml(entry.path) + '"><option value="true"' + (entry.preserve_folder_structure !== false ? ' selected' : '') + '>Preserve</option><option value="false"' + (entry.preserve_folder_structure === false ? ' selected' : '') + '>Flatten</option></select></div>'
                : '<div class="field" style="visibility:hidden;" aria-hidden="true"><label>Folder Structure</label><select class="select" disabled><option>Hidden</option></select></div>')
              + '<div class="field"><label>Title Basis</label><select class="select" data-action="selection-title-source" data-path="' + escapeHtml(entry.path) + '"><option value="folder"' + (titleSource === 'folder' ? ' selected' : '') + '>Folder name</option><option value="first-file"' + (titleSource === 'first-file' ? ' selected' : '') + '>First file</option><option value="custom"' + (titleSource === 'custom' ? ' selected' : '') + '>Custom</option></select></div>'
              + '<div class="field"><label>Model/Group Title</label><input class="input" type="text" value="' + escapeHtml(resolvedTitle) + '" data-action="selection-group-title" data-path="' + escapeHtml(entry.path) + '" placeholder="Folder"></div>'
              + '<div class="muted" style="grid-column:1 / -1;">This title is preserved into the intake queue and becomes the default when this batch is committed.' + (entry.recurse ? ' Folder structure is preserved in Catalog.' : '') + '</div>'
              + '</div>'
            : '<div class="button-row"><span class="chip">title ' + escapeHtml(resolvedTitle) + '</span><span class="chip">' + escapeHtml(fileBatchGrouping === 'flat' ? 'separate model' : 'same model batch') + '</span></div>'
              + (fileBatchGrouping === 'flat' && fileBatchTitleSource === 'custom' && !isArchive && fileKind(entry.path) === 'model'
                ? '<div class="field"><label>Custom Model Name</label><input class="input" type="text" value="' + escapeHtml(String(entry.group_title || '').trim()) + '" data-action="selection-file-model-title" data-path="' + escapeHtml(entry.path) + '" placeholder="' + escapeHtml(displayTitleFromPath(entry.path) || 'Model') + '"></div>'
                : ''))
          + '</article>';
      }, this).join('') + '</div>';
  };

  var originalRenderWizard = proto._renderWizard;

  // Issue #1323: stable wizard height with independent left/right scroll, MDI
  // folder preview styling, and theme-aware (light/dark) colors. We layer
  // these as a scoped <style> block prepended to the wizard markup so we do
  // not have to copy the whole base render pipeline.
  proto._renderWizard = function () {
    var baseHtml = originalRenderWizard.call(this);
    var overrideStyles = ''
      + '<style>'
      // Lock the dialog to a stable height based on the viewport so steps
      // don't change overall height, and let inner panels own scrolling.
      + '.wizard-modal{overscroll-behavior:contain;}'
      + '.wizard-dialog{height:min(92vh,980px);min-height:560px;max-height:min(92vh,980px);overflow:hidden;display:flex;flex-direction:column;gap:14px;'
        + 'background:var(--card-background-color,linear-gradient(180deg,rgba(15,23,42,0.96),rgba(15,23,42,0.9)));color:var(--primary-text-color);border-color:var(--divider-color,rgba(148,163,184,0.22));}'
      + '.wizard-body{flex:1 1 auto;min-height:0;overflow:hidden;align-items:stretch;}'
      + '.wizard-panel{min-height:0;overflow:hidden;display:flex;flex-direction:column;overscroll-behavior:contain;'
        + 'background:var(--secondary-background-color,rgba(15,23,42,0.22));border-color:var(--divider-color,rgba(148,163,184,0.18));}'
      + '.wizard-panel-scroll{flex:1 1 auto;min-height:0;overflow:auto;overscroll-behavior:contain;padding-right:4px;}'
      + '.wizard-scroll-region,.wizard-selection-scroll,.wizard-review-scroll{max-height:none;overflow:visible;padding-right:0;}'
      + '.wizard-panel > .title-row,.wizard-panel > .intake-path-row{flex:0 0 auto;}'
      // Theme-friendly chrome
      + '.wizard-step{background:var(--secondary-background-color,rgba(30,41,59,0.45));border-color:var(--divider-color,rgba(148,163,184,0.18));}'
      + '.wizard-step.current{background:rgba(96,165,250,0.18);border-color:var(--primary-color,rgba(96,165,250,0.45));}'
      + '.wizard-step.complete{background:rgba(74,222,128,0.18);border-color:rgba(74,222,128,0.45);}'
      + '.wizard-dialog .entry-row{background:var(--card-background-color,rgba(15,23,42,0.12));border-color:var(--divider-color,rgba(148,163,184,0.18));}'
      + '.wizard-dialog .entry-row.selected{background:rgba(96,165,250,0.18);border-color:var(--primary-color,rgba(96,165,250,0.4));}'
      + '.wizard-dialog .entry-row.highlighted{background:rgba(var(--rgb-primary-color,96 165 250),0.25);border-color:rgba(var(--rgb-primary-color,96 165 250),0.4);}'
      + '.wizard-dialog .entry-row.related{opacity:0.65;}'
      // Empty-selection association: when a left row that produced no planned
      // models is clicked on the Organize step, light up the matching warning
      // banner item(s) on the right so the operator sees the relationship.
      + '.wizard-dialog li[data-warning-key].highlighted-warning{background:rgba(245,158,11,0.30);border-radius:6px;padding:2px 6px;font-weight:600;}'
      // Issue #1343: a row that lives inside a selected folder must NOT be
      // dimmed — give it a bold dashed primary outline so the "included in
      // selection" relationship is obvious instead of looking inactive.
      + '.wizard-dialog .entry-row.included-in-selection{opacity:1;border-style:dashed;border-width:2px;border-color:var(--primary-color,#60a5fa);background:rgba(96,165,250,0.08);}'
      + '.wizard-dialog .entry-row.included-in-selection .chip{background:rgba(96,165,250,0.28);border-color:var(--primary-color,#60a5fa);color:var(--primary-text-color);font-weight:600;opacity:1;}'
      // Issue #1349: a folder that contains selected/included items (but is
      // not itself selected) gets a dashed primary border so the user can
      // visually distinguish it from a fully-selected folder (solid border).
      + '.wizard-dialog .entry-row.contains-selection:not(.selected):not(.excluded){border-style:dashed;border-width:2px;border-color:var(--primary-color,#60a5fa);background:rgba(96,165,250,0.04);}'
      // Issue #1350: an excluded item / fully-excluded folder gets a duller
      // dashed border with NO highlighted background — visually distinct from
      // selected (solid + bg) and indirectly-selected (dashed + bg). No
      // strike-through or opacity dim — the row remains fully readable so the
      // user can re-Select it.
      + '.wizard-dialog .entry-row.excluded{border-style:dashed;border-width:2px;border-color:rgba(96,165,250,0.4);background:transparent;opacity:1;}'
      + '.wizard-dialog .entry-row.excluded .entry-name{text-decoration:none;opacity:1;}'
      // Issue #1349: rows in the right pane are clickable to jump to the
      // entry's parent folder on the left (which now owns all navigation).
      + '.wizard-dialog .entry-row.right-pane-jump{cursor:pointer;}'
      + '.wizard-dialog .entry-row.right-pane-jump:hover{background:rgba(96,165,250,0.12);border-color:var(--primary-color,rgba(96,165,250,0.55));}'
      // Issue #1355: Select-step cross-pane highlighting — visually link left
      // and right entries when a right-pane jump is clicked or a left-pane row
      // is tapped. Cyan accent distinguishes from the blue Selected / Organize
      // highlights.
      + '.wizard-dialog .entry-row.select-linked{background:rgba(56,189,248,0.18);border-color:rgba(56,189,248,0.45);box-shadow:inset 4px 0 0 0 rgba(56,189,248,0.9);}'
      + '.wizard-dialog .entry-row.select-dimmed{opacity:0.5;}'
      + '.wizard-dialog .entry-row.loading-item{opacity:0.5;pointer-events:none;}'
      + '@keyframes spin{from{transform:rotate(0deg);}to{transform:rotate(360deg);}}'
      + '.intake-spinner{display:inline-block;border-radius:50%;border:2px solid rgba(148,163,184,0.45);border-top-color:rgba(96,165,250,0.95);animation:spin .9s linear infinite;flex-shrink:0;}'
      + '.intake-spinner.spin-20{width:20px;height:20px;}'
      + '.intake-spinner.spin-16{width:16px;height:16px;}'
      + '.wizard-dialog .entry-thumb{background:var(--secondary-background-color,rgba(15,23,42,0.24));border-color:var(--divider-color,rgba(148,163,184,0.24));color:var(--secondary-text-color);}'
      + '.wizard-dialog .input,.wizard-dialog .select{background:var(--card-background-color,rgba(15,23,42,0.16));border-color:var(--divider-color,rgba(148,163,184,0.24));color:var(--primary-text-color);}'
      + '.wizard-dialog .button{background:var(--secondary-background-color,rgba(148,163,184,0.12));border-color:var(--divider-color,rgba(148,163,184,0.24));color:var(--primary-text-color);}'
      + '.wizard-dialog .button.primary{background:var(--primary-color,rgba(30,64,175,0.22));border-color:var(--primary-color,rgba(96,165,250,0.4));color:var(--text-primary-color,var(--primary-text-color));}'
      + '.wizard-dialog .result-summary{background:var(--secondary-background-color,rgba(15,23,42,0.16));border-color:var(--divider-color,rgba(148,163,184,0.22));}'
      + '.wizard-dialog .state-row{color:var(--secondary-text-color);border-color:var(--divider-color,rgba(148,163,184,0.28));}'
      + '.wizard-dialog .chip{background:rgba(96,165,250,0.18);border-color:var(--primary-color,rgba(96,165,250,0.3));color:var(--primary-text-color);}'
        + '.wizard-dialog .chip.warn{background:rgba(180,83,9,0.22);border-color:rgba(245,158,11,0.45);color:#fcd34d;}'
        + '.wizard-dialog .chip.ok{background:rgba(22,101,52,0.24);border-color:rgba(74,222,128,0.38);color:#dcfce7;}'
        + '.wizard-dialog .chip.error{background:rgba(153,27,27,0.22);border-color:rgba(248,113,113,0.38);color:#fecaca;}'
        + '.wizard-dialog .entry-row.included-in-selection .chip.warn{background:rgba(180,83,9,0.24);border-color:rgba(245,158,11,0.5);color:#fcd34d;font-weight:700;}'
        + '.wizard-dialog .entry-row.included-in-selection .chip.ok{background:rgba(22,101,52,0.24);border-color:rgba(74,222,128,0.4);color:#dcfce7;font-weight:700;}'
      // Issue #1366: keep icon chrome and glyph positioning centered in both
      // axes across all wizard panes and icon-only controls.
      + '.wizard-dialog .entry-type-icon{display:inline-flex;align-items:center;justify-content:center;background:var(--card-background-color,rgba(15,23,42,0.18));border-color:var(--divider-color,rgba(148,163,184,0.18));color:var(--primary-text-color);}'
      + '.wizard-dialog .entry-type-icon ha-icon{display:block;margin:0;}'
      + '.wizard-dialog .button.icon-only{display:inline-flex;align-items:center;justify-content:center;}'
      + '.wizard-dialog .button.icon-only ha-icon{display:block;margin:0;}'
      // Folder preview thumbnail styling (mdi:folder + small "folder" label).
      + '.wizard-dialog .entry-thumb.folder-thumb{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;color:var(--primary-text-color);}'
      + '.wizard-dialog .entry-thumb.folder-thumb ha-icon{--mdc-icon-size:28px;width:28px;height:28px;color:var(--primary-color,#60a5fa);}'
      + '.wizard-dialog .entry-thumb.folder-thumb .folder-thumb-label{font-size:10px;font-weight:700;letter-spacing:.04em;text-transform:lowercase;color:var(--secondary-text-color);}'
      // Browser file row: keep file-type icon at the top-right corner.
      + '.wizard-dialog .entry-row .entry-actions{justify-content:flex-end;}'
      + '.wizard-panel.recalculating-panel::after{content:"";position:absolute;inset:0;background:rgba(15,23,42,0.45);z-index:10;border-radius:18px;pointer-events:none;}'
      + '.wizard-panel.recalculating-panel{position:relative;}'
      + '.entries.loading-entries{opacity:0.5;pointer-events:none;}'
      // Issue #1307: fixed (non-scrolling) panels for the Validate-step results
      // and Commit-step summary so the operator-facing chrome stays put while
      // the right-pane Resolved Output handles scrolling on its own.
      // Left pane scrolls independently so long validation checklists are fully reachable.
      + '.wizard-validate-fixed{flex:1 1 auto;min-height:0;display:flex;flex-direction:column;gap:10px;padding-right:4px;overflow-y:auto;overscroll-behavior:contain;}'
      + '.wizard-validate-fixed .entries{display:flex;flex-direction:column;gap:6px;}'
      + '.wizard-dialog .validation-check-row{width:100%;box-sizing:border-box;}'
      + '.wizard-dialog .validation-check-header{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:10px;}'
      + '.wizard-dialog .validation-check-content{width:100%;min-width:0;}'
      + '.wizard-dialog .validation-findings{display:flex;flex-direction:column;gap:10px;margin-top:8px;width:100%;align-self:stretch;}'
      + '.wizard-dialog .validation-source-row{border:1px solid var(--divider-color,rgba(148,163,184,0.24));border-radius:10px;padding:10px;background:var(--secondary-background-color,rgba(15,23,42,0.18));width:100%;box-sizing:border-box;align-self:stretch;}'
      + '.wizard-dialog .validation-source-header{font-size:13px;font-weight:700;color:var(--primary-text-color);}'
      + '.wizard-dialog .validation-source-path{font-size:12px;line-height:1.3;color:var(--secondary-text-color);margin-top:4px;word-break:break-all;}'
      + '.wizard-dialog .validation-source-violations{display:flex;flex-direction:column;gap:8px;width:100%;}'
      + '.wizard-dialog .validation-violation-row{display:grid;grid-template-columns:minmax(0,1fr);gap:8px;padding:8px;border:1px dashed var(--divider-color,rgba(148,163,184,0.26));border-radius:8px;background:var(--card-background-color,rgba(15,23,42,0.14));}'
      + '.wizard-dialog .validation-violation-top{display:grid;grid-template-columns:minmax(0,1fr) 220px;gap:10px;align-items:start;}'
      + '.wizard-dialog .validation-violation-body{grid-column:1 / -1;}'
      + '.wizard-dialog .validation-violation-row.severity-hash{border-color:rgba(248,113,113,0.6);background:rgba(127,29,29,0.16);}'
      + '.wizard-dialog .validation-violation-row.severity-exact{border-color:rgba(245,158,11,0.55);background:rgba(120,53,15,0.14);}'
      + '.wizard-dialog .validation-violation-row.severity-soft{border-color:rgba(96,165,250,0.45);background:rgba(30,64,175,0.1);}'
      + '.wizard-dialog .validation-violation-label{font-size:12px;font-weight:700;color:var(--primary-text-color);margin-bottom:4px;}'
      + '.wizard-dialog .validation-severity-chip{display:inline-flex;align-items:center;margin-left:8px;padding:1px 6px;border-radius:999px;font-size:10px;letter-spacing:.03em;text-transform:uppercase;border:1px solid transparent;vertical-align:middle;}'
      + '.wizard-dialog .validation-severity-chip.severity-hash{border-color:rgba(248,113,113,0.45);background:rgba(127,29,29,0.22);color:#fecaca;}'
      + '.wizard-dialog .validation-severity-chip.severity-exact{border-color:rgba(245,158,11,0.45);background:rgba(120,53,15,0.2);color:#fde68a;}'
      + '.wizard-dialog .validation-severity-chip.severity-soft{border-color:rgba(96,165,250,0.45);background:rgba(30,64,175,0.2);color:#bfdbfe;}'
      + '.wizard-dialog .validation-severity-chip.severity-other{border-color:rgba(148,163,184,0.4);background:rgba(71,85,105,0.2);color:#e2e8f0;}'
      + '.wizard-dialog .validation-match-table{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);border:1px solid var(--divider-color,rgba(148,163,184,0.25));border-radius:8px;}'
      + '.wizard-dialog .validation-match-header{padding:6px 8px;background:rgba(15,23,42,0.36);font-size:11px;font-weight:700;letter-spacing:.03em;text-transform:uppercase;color:var(--secondary-text-color);border-bottom:1px solid var(--divider-color,rgba(148,163,184,0.25));}'
      + '.wizard-dialog .validation-match-cell{padding:6px 8px;font-size:12px;line-height:1.35;color:var(--primary-text-color);border-bottom:1px solid var(--divider-color,rgba(148,163,184,0.2));white-space:normal;overflow-wrap:anywhere;word-break:break-word;}'
      + '.wizard-dialog .validation-match-cell:nth-child(2n){border-left:1px solid var(--divider-color,rgba(148,163,184,0.2));}'
      + '.wizard-dialog .validation-match-name{font-weight:700;overflow-wrap:anywhere;word-break:break-word;}'
      + '.wizard-dialog .validation-match-path{font-size:11px;color:var(--secondary-text-color);overflow-wrap:anywhere;word-break:break-word;}'
      + '.wizard-dialog .validation-match-preview{display:flex;align-items:center;justify-content:flex-start;min-height:52px;}'
      + '.wizard-dialog .validation-thumb-wrap{position:relative;display:inline-flex;align-items:center;justify-content:center;}'
      + '.wizard-dialog .validation-thumb-button{display:inline-flex;align-items:center;justify-content:center;width:44px;height:44px;padding:0;border:1px solid var(--divider-color,rgba(148,163,184,0.35));border-radius:8px;background:rgba(15,23,42,0.35);cursor:zoom-in;overflow:hidden;}'
      + '.wizard-dialog .validation-thumb-image{width:100%;height:100%;object-fit:cover;display:block;}'
      + '.wizard-dialog .validation-thumb-hover{position:fixed;width:180px;height:180px;padding:6px;border-radius:10px;border:1px solid var(--divider-color,rgba(148,163,184,0.4));background:rgba(15,23,42,0.95);box-shadow:0 10px 24px rgba(2,6,23,0.55);opacity:0;pointer-events:none;transform:translateY(4px);transition:opacity .14s ease,transform .14s ease;z-index:100;}'
      + '.wizard-dialog .validation-thumb-hover.visible{opacity:1;transform:translateY(0);}'
      + '.wizard-dialog .validation-thumb-hover-image{width:100%;height:100%;object-fit:contain;display:block;border-radius:6px;}'
      + '.wizard-dialog .validation-thumb-missing{font-size:11px;color:var(--secondary-text-color);}'
      + '.wizard-dialog .validation-ext-badge{font-size:11px;font-weight:800;color:var(--secondary-text-color);cursor:default;}'
      + '.wizard-dialog .validation-ext-badge.x-3mf{color:#5eead4;border-color:rgba(94,234,212,0.3);background:rgba(94,234,212,0.12);}'
      + '.wizard-dialog .validation-ext-badge.x-stl,.wizard-dialog .validation-ext-badge.x-step,.wizard-dialog .validation-ext-badge.x-stp,.wizard-dialog .validation-ext-badge.x-obj{color:#93c5fd;border-color:rgba(96,165,250,0.32);background:rgba(96,165,250,0.12);}'
      + '.wizard-dialog .validation-match-toggle{grid-column:1/-1;padding:6px 8px;border-bottom:1px solid var(--divider-color,rgba(148,163,184,0.2));}'
      + '.wizard-dialog .validation-match-detail-row{grid-column:1/-1;padding:6px 8px;border-bottom:1px solid var(--divider-color,rgba(148,163,184,0.2));font-size:11px;line-height:1.35;color:var(--primary-text-color);overflow-wrap:anywhere;word-break:break-word;}'
      + '.wizard-dialog .validation-match-detail-key{color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.03em;margin-right:8px;}'
      + '.wizard-dialog .validation-lightbox{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;z-index:50;}'
      + '.wizard-dialog .validation-lightbox-backdrop{position:absolute;inset:0;background:rgba(2,6,23,0.78);}'
      + '.wizard-dialog .validation-lightbox-dialog{position:relative;max-width:min(90vw,920px);max-height:88vh;width:100%;padding:12px;border-radius:12px;border:1px solid var(--divider-color,rgba(148,163,184,0.35));background:rgba(15,23,42,0.98);display:flex;flex-direction:column;gap:10px;}'
      + '.wizard-dialog .validation-lightbox-header{display:flex;align-items:center;justify-content:space-between;gap:10px;}'
      + '.wizard-dialog .validation-lightbox-title{font-size:13px;font-weight:700;color:var(--primary-text-color);}'
      + '.wizard-dialog .validation-lightbox-body{flex:1 1 auto;min-height:0;display:flex;align-items:center;justify-content:center;}'
      + '.wizard-dialog .validation-lightbox-image{max-width:100%;max-height:72vh;object-fit:contain;border-radius:8px;}'
      + '.wizard-dialog .validation-status-chip{align-self:flex-start;justify-self:end;}'
      + '.wizard-dialog .validation-icon.fail{display:inline-grid;place-content:center;width:16px;height:16px;font-size:13px;line-height:1;color:#f87171;}'
      + '.wizard-dialog .validation-action-control{display:flex;flex-direction:column;gap:4px;justify-self:end;width:100%;max-width:220px;}'
      + '.wizard-dialog .validation-action-control label{font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--secondary-text-color);}'
      + '.wizard-dialog .validation-action-control .select{width:100%;}'
      + '.wizard-dialog .validation-action-selected{font-size:11px;line-height:1.3;color:var(--secondary-text-color);}'
      + '@media (max-width: 900px){.wizard-dialog .validation-violation-top{grid-template-columns:1fr;}.wizard-dialog .validation-action-control{max-width:none;justify-self:stretch;}}'
      + '.wizard-commit-fixed{flex:0 0 auto;display:flex;flex-direction:column;gap:14px;padding-right:4px;overflow:hidden;}'
      + '.wizard-cleanup-policy-block{padding:12px;border-radius:14px;border:1px solid var(--primary-color,rgba(96,165,250,0.45));background:rgba(96,165,250,0.08);}'
      + '.wizard-cleanup-policy-block .field label{font-weight:700;color:var(--primary-text-color);font-size:14px;}'
      + '.wizard-cleanup-policy-block .select{margin-top:6px;}'
      + '.wizard-commit-policy-chip{flex:0 0 auto;display:flex;align-items:baseline;gap:10px;padding:10px 14px;border-radius:12px;border:1px solid var(--primary-color,rgba(96,165,250,0.45));background:rgba(96,165,250,0.12);margin-bottom:10px;}'
      + '.wizard-commit-policy-chip .muted{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--secondary-text-color);}'
      + '.wizard-commit-policy-chip strong{font-size:14px;color:var(--primary-text-color);}'
      + '.cleanup-impact-block{padding:12px;border-radius:14px;border:1px solid var(--divider-color,rgba(148,163,184,0.25));background:rgba(30,41,59,0.45);}'
      + '.cleanup-impact-title{font-weight:700;font-size:13px;color:var(--primary-text-color);margin-bottom:8px;}'
      + '.cleanup-impact-info{font-size:12px;line-height:1.5;color:var(--secondary-text-color);}'
      + '.cleanup-impact-section{margin-top:8px;padding:8px 0;border-top:1px solid var(--divider-color,rgba(148,163,184,0.15));}'
      + '.cleanup-impact-section-header{display:flex;align-items:center;gap:8px;margin-bottom:4px;}'
      + '.cleanup-impact-toggle{display:flex;align-items:center;gap:4px;cursor:pointer;user-select:none;}'
      + '.cleanup-impact-file{display:flex;align-items:center;gap:6px;font-size:12px;padding:2px 0;color:var(--primary-text-color);}'
      + '.cleanup-impact-file.untouched{color:var(--secondary-text-color);}'
      + '.cleanup-impact-icon{font-size:13px;flex:0 0 auto;width:18px;text-align:center;}'
      + '.cleanup-impact-stub-example{margin-top:10px;padding-top:8px;border-top:1px solid var(--divider-color,rgba(148,163,184,0.15));}'
      + '.cleanup-impact-stub-content{padding:8px 10px;border-radius:8px;background:rgba(15,23,42,0.6);font-size:11px;line-height:1.6;color:var(--secondary-text-color);overflow-x:auto;}'
      + '.cleanup-impact-stub-content code{font-family:monospace;font-size:11px;white-space:pre-wrap;color:var(--secondary-text-color);}'
      + '@media (max-width: 860px){.wizard-dialog{height:auto;max-height:94vh;}}'
      + '</style>';
    return overrideStyles + baseHtml;
  };

  proto._normalizeHighlightPath = function (value) {
    return String(value || '')
      .replace(/\\/g, '/')
      .replace(/^\/+/, '')
      .replace(/\/+$/, '')
      .toLowerCase();
  };

  proto._leftRowSourceKey = function (leftRow) {
    if (!leftRow) {
      return '';
    }
    var explicitKey = String(leftRow.getAttribute('data-source-key') || '').trim();
    if (explicitKey) {
      return explicitKey;
    }
    var pathAttr = String(leftRow.getAttribute('data-path') || '').trim();
    if (pathAttr) {
      return 'server:' + pathAttr;
    }
    var rootSelect = leftRow.querySelector('[data-root]');
    if (rootSelect) {
      var rootValue = String(rootSelect.getAttribute('data-root') || '').trim();
      if (rootValue) {
        return 'browser-root:' + rootValue;
      }
    }
    var relativePathTarget = leftRow.querySelector('[data-relative-path]');
    if (relativePathTarget) {
      var relativePath = String(relativePathTarget.getAttribute('data-relative-path') || '').trim();
      if (relativePath) {
        return 'browser-file:' + relativePath;
      }
    }
    if (leftRow.querySelector('[data-action="selection-grouping-files"]')) {
      return 'server-file-batch';
    }
    return '';
  };

  proto._modelMatchesSourceKey = function (model, sourceKey) {
    var normalizedKey = String(sourceKey || '').trim();
    if (!normalizedKey) {
      return false;
    }
    var files = Array.isArray(model && model.files) ? model.files : [];
    var card = this;
    if (normalizedKey === 'server-file-batch') {
      return files.some(function (file) {
        return String(file && file.source_entry_type || '').trim().toLowerCase() === 'file';
      });
    }
    if (normalizedKey.indexOf('server:') === 0) {
      var sourcePath = card._normalizeHighlightPath(normalizedKey.slice('server:'.length));
      if (!sourcePath) {
        return false;
      }
      return files.some(function (file) {
        var sourceEntryPath = card._normalizeHighlightPath(file && file.source_entry_path || '');
        return sourceEntryPath === sourcePath || sourceEntryPath.indexOf(sourcePath + '/') === 0;
      });
    }
    if (normalizedKey.indexOf('browser-root:') === 0) {
      var rootKey = card._normalizeHighlightPath(normalizedKey.slice('browser-root:'.length));
      if (!rootKey) {
        return false;
      }
      return files.some(function (file) {
        var relativePath = card._normalizeHighlightPath(file && (file.relative_path || file.filename) || '');
        return relativePath === rootKey || relativePath.indexOf(rootKey + '/') === 0;
      });
    }
    if (normalizedKey.indexOf('browser-file:') === 0) {
      var fileKey = card._normalizeHighlightPath(normalizedKey.slice('browser-file:'.length));
      if (!fileKey) {
        return false;
      }
      return files.some(function (file) {
        var relativePath = card._normalizeHighlightPath(file && (file.relative_path || file.filename) || '');
        return relativePath === fileKey;
      });
    }
    return false;
  };

  // Issue #1328: Build deterministic left<->right mapping for Organize highlights.
  proto._buildModelSourceMapping = function (leftEntries, rightEntries) {
    var mapping = {
      leftToRight: {},
      rightToLeft: {},
      leftSourceKeys: {},
      rightModelIndices: {},
    };
    if (!this._previewData || this._wizardStep !== 2) {
      return mapping;
    }
    var plannedModels = Array.isArray(this._previewData.planned_models) ? this._previewData.planned_models : [];
    var modelIndexToRightIndices = {};
    (rightEntries || []).forEach(function (rightRow, rightIndex) {
      var modelIndexRaw = rightRow && rightRow.getAttribute ? rightRow.getAttribute('data-model-index') : null;
      var modelIndex = Number(modelIndexRaw);
      if (!Number.isFinite(modelIndex)) {
        modelIndex = rightIndex;
      }
      mapping.rightModelIndices[rightIndex] = modelIndex;
      mapping.rightToLeft[rightIndex] = [];
      if (!modelIndexToRightIndices[modelIndex]) {
        modelIndexToRightIndices[modelIndex] = [];
      }
      modelIndexToRightIndices[modelIndex].push(rightIndex);
    });

    (leftEntries || []).forEach(function (leftRow, leftIndex) {
      var sourceKey = this._leftRowSourceKey(leftRow);
      mapping.leftSourceKeys[leftIndex] = sourceKey;
      mapping.leftToRight[leftIndex] = [];
      if (!sourceKey) {
        return;
      }
      plannedModels.forEach(function (model, modelIndex) {
        if (!this._modelMatchesSourceKey(model, sourceKey)) {
          return;
        }
        var matchedRightIndices = modelIndexToRightIndices[modelIndex] || [];
        matchedRightIndices.forEach(function (rightIndex) {
          if (mapping.leftToRight[leftIndex].indexOf(rightIndex) === -1) {
            mapping.leftToRight[leftIndex].push(rightIndex);
          }
          if (mapping.rightToLeft[rightIndex].indexOf(leftIndex) === -1) {
            mapping.rightToLeft[rightIndex].push(leftIndex);
          }
        });
      }, this);
    }, this);
    return mapping;
  };

  // Issue #1328: Attach event listeners for left/right side highlighting in ORGANIZE step
  proto._attachFileTreeListeners = function () {
    if (!this.shadowRoot) return;
    var container = this.shadowRoot.querySelector('.wizard-body') || this.shadowRoot;
    if (container.__fileTreeListenerAttached) return;
    container.__fileTreeListenerAttached = true;
    container.addEventListener('click', function (event) {
      var toggleRoot = event.target.closest('[data-tree-action="toggle-root"]');
      if (toggleRoot) {
        event.stopPropagation();
        var block = toggleRoot.closest('.file-tree-block');
        if (!block) return;
        var root = block.querySelector('.file-tree-root');
        if (!root) return;
        var isOpen = root.style.display !== 'none';
        root.style.display = isOpen ? 'none' : '';
        toggleRoot.classList.toggle('expanded', !isOpen);
        var label = toggleRoot.querySelector('.entry-path');
        if (label) label.textContent = isOpen ? 'Show file tree' : 'Hide file tree';
        return;
      }
      var toggleFolder = event.target.closest('[data-tree-action="toggle"]');
      if (toggleFolder) {
        event.stopPropagation();
        var folder = toggleFolder.closest('.file-tree-folder');
        if (!folder) return;
        var children = folder.querySelector('.file-tree-children');
        if (!children) return;
        var wasOpen = children.style.display !== 'none';
        children.style.display = wasOpen ? 'none' : '';
        folder.classList.toggle('expanded', !wasOpen);
        return;
      }
    }, false);
  };

  // ---------------------------------------------------------------
  // Issue #1355: Select-step cross-pane highlight
  // ---------------------------------------------------------------
  // When a right-pane entry is clicked (jump-server-parent / jump-browser-parent)
  // _handleClick stores the target key in _selectStepHighlight. After the
  // resulting navigation + re-render, this method auto-applies a cyan accent
  // on the matching left & right entries and dims the rest. Left-pane rows
  // also get click listeners so the user can tap any left entry to see which
  // right-pane entries it relates to (bidirectional, same concept as the
  // Organize step's _attachHighlightListeners).
  proto._attachSelectStepHighlightListeners = function () {
    if (!this.shadowRoot || this._wizardStep !== 1) {
      return;
    }
    var self = this;
    var panels = this.shadowRoot.querySelectorAll('.wizard-panel');
    if (panels.length < 2) {
      return;
    }
    var leftPanel = panels[0];
    var rightPanel = panels[1];
    var leftEntries = leftPanel.querySelectorAll('.entry-row');
    var rightEntries = rightPanel.querySelectorAll('.entry-row');
    if (!leftEntries.length || !rightEntries.length) {
      return;
    }
    var isServer = this._wizardMode === 'server';
    var keyAttr = isServer ? 'data-path' : 'data-browse-key';

    function getKey(row) {
      return String(row.getAttribute(keyAttr) || '').replace(/\/+$/, '');
    }

    function keysRelated(a, b) {
      if (!a || !b) { return false; }
      if (a === b) { return true; }
      if (b.indexOf(a + '/') === 0) { return true; }
      if (a.indexOf(b + '/') === 0) { return true; }
      return false;
    }

    // Build left↔right mapping
    var leftToRight = {};
    var rightToLeft = {};
    var li, ri;
    for (li = 0; li < leftEntries.length; li += 1) {
      leftToRight[li] = [];
    }
    for (ri = 0; ri < rightEntries.length; ri += 1) {
      rightToLeft[ri] = [];
    }
    for (li = 0; li < leftEntries.length; li += 1) {
      var lk = getKey(leftEntries[li]);
      if (!lk) { continue; }
      for (ri = 0; ri < rightEntries.length; ri += 1) {
        var rk = getKey(rightEntries[ri]);
        if (!rk) { continue; }
        if (keysRelated(lk, rk)) {
          leftToRight[li].push(ri);
          rightToLeft[ri].push(li);
        }
      }
    }

    function clearHighlights() {
      for (var i = 0; i < leftEntries.length; i += 1) {
        leftEntries[i].classList.remove('select-linked', 'select-dimmed');
      }
      for (var j = 0; j < rightEntries.length; j += 1) {
        rightEntries[j].classList.remove('select-linked', 'select-dimmed');
      }
    }

    function applyRightHighlight(targetRi) {
      clearHighlights();
      if (targetRi < 0 || targetRi >= rightEntries.length) { return; }
      rightEntries[targetRi].classList.add('select-linked');
      var leftMatches = rightToLeft[targetRi] || [];
      for (var i = 0; i < leftEntries.length; i += 1) {
        leftEntries[i].classList.add(leftMatches.indexOf(i) !== -1 ? 'select-linked' : 'select-dimmed');
      }
      for (var j = 0; j < rightEntries.length; j += 1) {
        if (j !== targetRi) {
          rightEntries[j].classList.add('select-dimmed');
        }
      }
    }

    function applyLeftHighlight(targetLi) {
      clearHighlights();
      if (targetLi < 0 || targetLi >= leftEntries.length) { return; }
      leftEntries[targetLi].classList.add('select-linked');
      var rightMatches = leftToRight[targetLi] || [];
      for (var i = 0; i < rightEntries.length; i += 1) {
        rightEntries[i].classList.add(rightMatches.indexOf(i) !== -1 ? 'select-linked' : 'select-dimmed');
      }
      for (var j = 0; j < leftEntries.length; j += 1) {
        if (j !== targetLi) {
          leftEntries[j].classList.add('select-dimmed');
        }
      }
    }

    // Auto-apply from persisted highlight state
    var hl = self._selectStepHighlight;
    if (hl && hl.key) {
      var targetKey = String(hl.key).replace(/\/+$/, '');
      var found = false;
      if (hl.side === 'right') {
        for (ri = 0; ri < rightEntries.length; ri += 1) {
          if (getKey(rightEntries[ri]) === targetKey) {
            applyRightHighlight(ri);
            found = true;
            break;
          }
        }
      } else {
        for (li = 0; li < leftEntries.length; li += 1) {
          if (getKey(leftEntries[li]) === targetKey) {
            applyLeftHighlight(li);
            found = true;
            break;
          }
        }
      }
      if (!found) {
        self._selectStepHighlight = null;
      }
    }

    // Left-pane click listeners for bidirectional highlighting.
    // Right-pane highlighting is driven by the jump handlers (data-action on
    // the article itself) → _selectStepHighlight → auto-apply above.
    for (li = 0; li < leftEntries.length; li += 1) {
      (function (leftRow, idx) {
        leftRow.addEventListener('click', function (event) {
          var interactive = event.target.closest('button,select,input,textarea,[data-action]');
          if (interactive) { return; }
          event.stopPropagation();
          if (leftRow.classList.contains('select-linked')) {
            clearHighlights();
            self._selectStepHighlight = null;
          } else {
            applyLeftHighlight(idx);
            self._selectStepHighlight = { side: 'left', key: getKey(leftRow) };
          }
        }, false);
      })(leftEntries[li], li);
    }
  };

  proto._attachHighlightListeners = function () {
    if (!this.shadowRoot || this._wizardStep !== 2) {
      return;
    }
    var self = this;
    var panels = this.shadowRoot.querySelectorAll('.wizard-panel');
    if (panels.length < 2) {
      return;
    }
    var leftPanel = panels[0];
    var rightPanel = panels[1];
    var leftEntries = leftPanel.querySelectorAll('.entry-row');
    var rightEntries = rightPanel.querySelectorAll('.entry-row');
    // Issue #1xxxx: warning banner items can be highlighted from the left side
    // when a selected source produced no planned models (and therefore has no
    // right-pane row to associate with).
    var warningItems = rightPanel.querySelectorAll('li[data-warning-key]');
    
    // Build deterministic relationships once per render.
    var modelMapping = this._buildModelSourceMapping(leftEntries, rightEntries);

    // Map each left row to the warning banner items whose path matches the
    // left source's key (server:<path>, browser-root:<path>, browser-file:<path>).
    var leftToWarning = {};
    leftEntries.forEach(function (_leftRow, leftIndex) {
      leftToWarning[leftIndex] = [];
      var sk = String(modelMapping.leftSourceKeys[leftIndex] || '');
      var colon = sk.indexOf(':');
      if (colon < 0) {
        return;
      }
      var pathPart = sk.slice(colon + 1).replace(/\\/g, '/').replace(/^\/+/, '').replace(/\/+$/, '').toLowerCase();
      if (!pathPart) {
        return;
      }
      warningItems.forEach(function (li, wi) {
        var key = String(li.getAttribute('data-warning-key') || '').trim();
        if (key && key === pathPart) {
          leftToWarning[leftIndex].push(wi);
        }
      });
    });

    function clearHighlights() {
      leftEntries.forEach(function (row) {
        row.classList.remove('highlighted', 'related');
      });
      rightEntries.forEach(function (row) {
        row.classList.remove('highlighted', 'related');
      });
      warningItems.forEach(function (li) {
        li.classList.remove('highlighted-warning');
      });
    }

    function leftIndicesForRightMatches(rightMatches, excludeLeftIndex) {
      var matchedLeftIndices = [];
      if (!Array.isArray(rightMatches) || !rightMatches.length) {
        return matchedLeftIndices;
      }
      leftEntries.forEach(function (_leftRow, candidateLeftIndex) {
        if (candidateLeftIndex === excludeLeftIndex) {
          return;
        }
        var candidateMatches = modelMapping.leftToRight[candidateLeftIndex] || [];
        var overlaps = candidateMatches.some(function (candidateRightIndex) {
          return rightMatches.indexOf(candidateRightIndex) !== -1;
        });
        if (overlaps) {
          matchedLeftIndices.push(candidateLeftIndex);
        }
      });
      return matchedLeftIndices;
    }

    function applyLeftSelection(leftIndex) {
      clearHighlights();
      if (leftIndex == null || leftIndex < 0 || leftIndex >= leftEntries.length) {
        return;
      }
      leftEntries[leftIndex].classList.add('highlighted');
      var rightMatches = modelMapping.leftToRight[leftIndex] || [];
      var siblingLeftMatches = leftIndicesForRightMatches(rightMatches, leftIndex);
      siblingLeftMatches.forEach(function (siblingLeftIndex) {
        leftEntries[siblingLeftIndex].classList.add('related');
      });
      // Always light up any matching warning banner items so a left source
      // that produced no models still has a visible association on the right.
      var warningMatches = leftToWarning[leftIndex] || [];
      warningMatches.forEach(function (wi) {
        warningItems[wi].classList.add('highlighted-warning');
      });
      if (!rightMatches.length) {
        return;
      }
      rightEntries.forEach(function (rightRow, rightIndex) {
        if (rightMatches.indexOf(rightIndex) !== -1) {
          rightRow.classList.add('highlighted');
        } else {
          rightRow.classList.add('related');
        }
      });
    }

    function applyRightSelection(rightIndex) {
      clearHighlights();
      if (rightIndex == null || rightIndex < 0 || rightIndex >= rightEntries.length) {
        return;
      }
      rightEntries[rightIndex].classList.add('highlighted');
      var leftMatches = modelMapping.rightToLeft[rightIndex] || [];
      if (!leftMatches.length) {
        return;
      }
      leftEntries.forEach(function (leftRow, leftIndex) {
        if (leftMatches.indexOf(leftIndex) !== -1) {
          leftRow.classList.add('highlighted');
        } else {
          leftRow.classList.add('related');
        }
      });
    }

    function findLeftIndexBySourceKey(sourceKey) {
      var normalized = String(sourceKey || '').trim();
      if (!normalized) {
        return -1;
      }
      for (var i = 0; i < leftEntries.length; i += 1) {
        if (String(modelMapping.leftSourceKeys[i] || '') === normalized) {
          return i;
        }
      }
      return -1;
    }

    // Restore highlight from previous render after regroup/split changes.
    if (this._highlightSelection && this._highlightSelection.type === 'left') {
      var restoredLeftIndex = findLeftIndexBySourceKey(this._highlightSelection.sourceKey);
      if (restoredLeftIndex < 0 && Number.isFinite(this._highlightSelection.leftIndex)) {
        restoredLeftIndex = this._highlightSelection.leftIndex;
      }
      if (restoredLeftIndex >= 0) {
        applyLeftSelection(restoredLeftIndex);
      }
    } else if (this._highlightSelection && this._highlightSelection.type === 'right') {
      var restoredRightIndex = -1;
      for (var rightIdx = 0; rightIdx < rightEntries.length; rightIdx += 1) {
        if (Number(modelMapping.rightModelIndices[rightIdx]) === Number(this._highlightSelection.modelIndex)) {
          restoredRightIndex = rightIdx;
          break;
        }
      }
      if (restoredRightIndex >= 0) {
        applyRightSelection(restoredRightIndex);
      }
    }

    leftEntries.forEach(function (leftRow, leftIndex) {
      leftRow.setAttribute('data-entry-index', leftIndex);

      leftRow.addEventListener('click', function (event) {
        var interactiveTarget = event.target.closest('button,select,input,textarea,[data-action],[data-tree-action]');
        if (interactiveTarget) {
          return;
        }
        event.stopPropagation();
        var isCurrentlyHighlighted = leftRow.classList.contains('highlighted') && !leftRow.classList.contains('related');
        if (!isCurrentlyHighlighted) {
          applyLeftSelection(leftIndex);
          self._highlightSelection = {
            type: 'left',
            leftIndex: leftIndex,
            sourceKey: modelMapping.leftSourceKeys[leftIndex] || '',
          };
        } else {
          clearHighlights();
          self._highlightSelection = null;
        }
      }, false);
    });

    rightEntries.forEach(function (rightRow, rightIndex) {
      rightRow.addEventListener('click', function (event) {
        var interactiveTarget = event.target.closest('button,select,input,textarea,[data-action],[data-tree-action]');
        if (interactiveTarget) {
          return;
        }
        event.stopPropagation();
        var isCurrentlyHighlighted = rightRow.classList.contains('highlighted') && !rightRow.classList.contains('related');
        if (!isCurrentlyHighlighted) {
          applyRightSelection(rightIndex);
          self._highlightSelection = {
            type: 'right',
            modelIndex: Number(modelMapping.rightModelIndices[rightIndex]),
          };
        } else {
          clearHighlights();
          self._highlightSelection = null;
        }
      }, false);
    });

    // Issue #1558: hover thumbnail preview — position:fixed to escape overflow clipping.
    var thumbWraps = rightPanel.querySelectorAll('.validation-thumb-wrap');
    thumbWraps.forEach(function (wrap) {
      wrap.addEventListener('mouseenter', function () {
        var hoverEl = wrap.querySelector('.validation-thumb-hover');
        if (!hoverEl) return;
        var btnRect = wrap.getBoundingClientRect();
        var hoverW = 192; var hoverH = 192;
        var left = btnRect.right + 8;
        var top = btnRect.top - 6;
        if (left + hoverW > window.innerWidth) { left = btnRect.left - hoverW - 8; }
        if (top + hoverH > window.innerHeight) { top = window.innerHeight - hoverH - 8; }
        if (top < 4) { top = 4; }
        hoverEl.style.left = left + 'px';
        hoverEl.style.top = top + 'px';
        hoverEl.classList.add('visible');
      }, false);
      wrap.addEventListener('mouseleave', function () {
        var hoverEl = wrap.querySelector('.validation-thumb-hover');
        if (hoverEl) { hoverEl.classList.remove('visible'); }
      }, false);
    });
  };

  proto._renderIntakeRootKindSwitcher = function () {
    var roots = Array.isArray(this._roots) ? this._roots : [];
    var hasIntake = roots.some(function (r) { return r && r.kind === 'intake' && r.path; });
    var hasWorking = roots.some(function (r) { return r && r.kind === 'working' && r.path; });
    if (!hasIntake || !hasWorking) {
      return '';
    }
    var current = this._intakeRootKind === 'working' ? 'working' : 'intake';
    function btn(kind, label) {
      var active = kind === current;
      var style = 'padding:4px 10px;border-radius:999px;border:1px solid var(--divider-color);'
        + 'background:' + (active ? 'var(--primary-color)' : 'transparent') + ';'
        + 'color:' + (active ? 'var(--text-primary-color, #fff)' : 'var(--primary-text-color)') + ';'
        + 'font-size:12px;cursor:pointer;';
      return '<button type="button" class="intake-root-kind-btn'
        + (active ? ' is-active' : '')
        + '" data-action="intake-root-kind-switch" data-kind="' + kind + '"'
        + ' style="' + style + '"'
        + (active ? ' aria-pressed="true"' : ' aria-pressed="false"')
        + '>' + label + '</button>';
    }
    return ''
      + '<div class="intake-root-kind-row" role="group" aria-label="Choose source location" '
      + 'style="display:flex;gap:6px;padding:6px 12px 0 12px;align-items:center;">'
      + '<span style="font-size:12px;color:var(--secondary-text-color);margin-right:6px;">Source:</span>'
      + btn('intake', 'Model Inbox')
      + btn('working', 'Working Files')
      + '</div>';
  };

  proto._renderWizardBody = function () {
    if (this._wizardStep === 1) {
      if (this._wizardMode === 'server') {
        return ''
          + '<div class="wizard-panel">'
          + '  <div class="title-row"><div><div class="title">Choose Files &amp; Folders</div><div class="subtitle">Choose or Drag &amp; Drop Files to Build an Upload Batch</div></div></div>'
          + this._renderIntakeRootKindSwitcher()
          + '  <div class="intake-path-row">'
          + (this._browse.parent_path
              ? '<button class="button icon-only" data-action="browse-parent" data-path="' + escapeHtml(this._browse.parent_path) + '" aria-label="Up one folder" title="Up one folder"><ha-icon icon="mdi:arrow-up"></ha-icon></button>'
              : '')
          + '    <div class="intake-path-text">' + escapeHtml(formatBrowsePathForDisplay(this._browse.path || '/')) + '</div>'
          + '  </div>'
          + '  <div class="wizard-panel-scroll"><div class="wizard-scroll-region">' + this._renderBrowseEntries() + '</div></div>'
          + '</div>'
          + '<div class="wizard-panel">'
          + '  <div class="title-row"><div><div class="title">Selected Source Entries</div><div class="subtitle">Click an entry to jump to its parent on the left.</div></div></div>'
          // Issue #1356: chips live in the fixed header (mirroring the
          // .intake-path-row on the left) so the scrolling list aligns
          // vertically with the left pane and the chips have breathing
          // room above the entries.
          + '  <div class="intake-path-row intake-summary-chips-row">' + this._renderServerWizardSummary() + '</div>'
            // Issue #1345: the right pane now shows only the chosen entries
            // (no mirrored navigation tree, no second path/breadcrumb row).
            // Navigation lives on the left pane; the right pane is a
            // selection summary plus the per-entry list.
            + '  <div class="wizard-panel-scroll"><div class="wizard-selection-scroll">' + this._renderServerSelectionRows(false) + '</div></div>'
          + '</div>';
      }
          var browserPath = normalizeBrowserRelativePath(this._browserSourcePath || '');
          var browserParentPath = browserParentRelativePath(browserPath);
      return ''
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Choose Files &amp; Folders</div><div class="subtitle">Choose or Drag &amp; Drop Files to Build an Upload Batch</div></div><div class="button-row"><button class="button" data-action="choose-browser-files">Add Files</button><button class="button" data-action="choose-browser-folder">Add Folder</button></div></div>'
          + '  <div class="intake-path-row">'
          + (browserPath
            ? '<button class="button icon-only" data-action="browser-parent-path" data-path="' + escapeHtml(browserParentPath) + '" aria-label="Up one folder" title="Up one folder"><ha-icon icon="mdi:arrow-up"></ha-icon></button>'
            : '')
          + '    <div class="intake-path-text">' + escapeHtml(formatBrowserPathForDisplay(browserPath)) + '</div>'
          + '  </div>'
          + '  <div class="wizard-panel-scroll"><div class="wizard-selection-scroll">' + this._renderBrowserSourceEntries(true) + '</div></div>'
        + '</div>'
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Current Batch</div><div class="subtitle">Click an entry to jump to its parent on the left.</div></div></div>'
        // Issue #1356: chips live in the fixed header (mirroring the
        // .intake-path-row on the left) so the scrolling list aligns
        // vertically with the left pane and the chips have breathing
        // room above the entries.
        + '  <div class="intake-path-row intake-summary-chips-row">' + this._renderBrowserWizardSummary(false) + '</div>'
        + '  <div class="wizard-panel-scroll">' + this._renderBrowserSourceEntries(false) + '</div>'
        + '</div>';
    }
    if (this._wizardStep === 2) {
      var preview = this._previewData;
      var isLoading = this._loading || this._previewLoading || false;
      var recalculatingBadge = '<div style="position:absolute;top:64px;left:50%;transform:translateX(-50%);display:flex;align-items:center;gap:8px;background:rgba(30,41,59,0.85);padding:8px 12px;border-radius:8px;z-index:11;font-size:12px;"><span class="intake-spinner spin-16"></span>Recalculating...</div>';
      var planSummaryMarkup = preview && preview.planned_models && preview.planned_models.length 
        ? '<div class="result-summary' + (isLoading ? ' recalculating' : '') + '">'
          + '  <div class="result-line"><span>Files in batch</span><strong>' + String(preview.summary.file_count || 0) + '</strong></div>'
          + '  <div class="result-line"><span>Planned models</span><strong>' + String(preview.summary.planned_model_count || preview.planned_models.length) + '</strong></div>'
          + '</div>'
        : '';
      return ''
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Organize</div><div class="subtitle">Choose how files stay together or split apart.</div></div></div>'
        + '  <div class="wizard-panel-scroll"><div class="wizard-selection-scroll">' + (this._wizardMode === 'server' ? this._renderServerSelectionRows(true) : this._renderBrowserOrganizeRows()) + '</div></div>'
        + '</div>'
        + '<div class="wizard-panel' + (isLoading ? ' recalculating-panel' : '') + '" style="display:flex;flex-direction:column;position:relative;">'
        + '  <div class="title-row"><div><div class="title">Review</div><div class="subtitle">Review how the models and groups will be organized</div></div></div>'
        + planSummaryMarkup
        + '  <div class="wizard-panel-scroll" style="flex:1 1 auto;min-height:0;overflow:auto;">' + renderPlanSummary(this, { includeDestinations: false, skipSummary: true }) + '</div>'
        + (isLoading ? recalculatingBadge : '')
        + '</div>';
    }
    if (this._wizardStep === 3) {
      return ''
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Pick Destination</div><div class="subtitle">Send each planned group to the Catalog or to Working Files.</div></div></div>'
        + '  <div class="wizard-panel-scroll"><div class="wizard-selection-scroll">' + this._renderDestinationAssignments() + '</div></div>'
        + '</div>'
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Assignment Summary</div><div class="subtitle">Each planned group keeps its structure and only changes destination.</div></div></div>'
        + '  <div class="wizard-panel-scroll"><div class="wizard-selection-scroll">' + this._renderDestinationSummary() + '</div></div>'
        + '</div>';
    }
    if (this._wizardStep === 4) {
      // Issue #1307: the validation results section on the left is now fixed
      // (no inner scroll) and shows ONLY the validation summary — Destination
      // Plan was removed from this pane.
      // Issue #1364: show blur overlay + spinner on the left pane while validation is running.
      var isValidating = !!this._loading;
      var validatingBadge = '<div style="position:absolute;top:64px;left:50%;transform:translateX(-50%);display:flex;align-items:center;gap:8px;background:rgba(30,41,59,0.85);padding:8px 12px;border-radius:8px;z-index:11;font-size:12px;"><span class="intake-spinner spin-16"></span>Running validation...</div>';
      return ''
        + '<div class="wizard-panel' + (isValidating ? ' recalculating-panel' : '') + '" style="display:flex;flex-direction:column;position:relative;">'
        + '  <div class="title-row"><div><div class="title">Validate</div><div class="subtitle">Create one prepared upload snapshot and verify it before the final commit.</div></div></div>'
        + '  <div class="wizard-validate-fixed">' + renderValidationSummary(this) + '</div>'
        + (isValidating ? validatingBadge : '')
        + '</div>'
        + '<div class="wizard-panel">'
        + '  <div class="title-row"><div><div class="title">Resolved Output</div><div class="subtitle">Validation checks the exact planned output shown here.</div></div></div>'
        + '  <div class="wizard-panel-scroll">' + renderPlanSummary(this) + '</div>'
        + '</div>';
    }
    var isBrowserMode = this._wizardMode === 'browser';
    var isPublishing = !!this._loading;
    var publishingBadge = '<div style="position:absolute;top:64px;left:50%;transform:translateX(-50%);display:flex;align-items:center;gap:8px;background:rgba(30,41,59,0.85);padding:8px 12px;border-radius:8px;z-index:11;font-size:12px;"><span class="intake-spinner spin-16"></span>Publishing to destinations...</div>';
    // Issue #1307: Commit step layout cleanup.
    //   Left  -> compact validation summary (counts, not full list)
    //            + cleanup policy selector (Server only) — entire panel fixed,
    //            no inner scroll, no destination/list rehash.
    //   Right -> fixed header chip showing the chosen Cleanup Policy at the
    //            top (Server only) above the scrollable Resolved Output.
    var cleanupPolicyValue = this._cleanupPolicy();
    var cleanupPolicyLabel = typeof this._cleanupPolicyFriendlyLabel === 'function'
      ? this._cleanupPolicyFriendlyLabel(cleanupPolicyValue)
      : String(cleanupPolicyValue || '');
    return ''
      + '<div class="wizard-panel' + (isPublishing ? ' recalculating-panel' : '') + '" style="display:flex;flex-direction:column;position:relative;">'
      + '  <div class="title-row"><div><div class="title">Commit Summary</div><div class="subtitle">' + (isBrowserMode ? 'Confirm validation results before the final publish.' : 'Confirm validation results and choose how the originals are handled after publish.') + '</div></div></div>'
      + '  <div class="wizard-commit-fixed">'
      + renderValidationSummaryCompact(this)
      + (isBrowserMode
        ? ''
        : '<div class="wizard-cleanup-policy-block">'
          + '<div class="field"><label for="wizard-cleanup-policy">Cleanup Policy</label>'
          + '<select id="wizard-cleanup-policy" class="select" data-action="cleanup-policy"><option value="keep"' + (cleanupPolicyValue === 'keep' ? ' selected' : '') + '>Keep Originals In Place</option><option value="delete_on_verified"' + (cleanupPolicyValue === 'delete_on_verified' ? ' selected' : '') + '>Delete Originals After Success</option><option value="replace_with_stub"' + (cleanupPolicyValue === 'replace_with_stub' ? ' selected' : '') + '>Replace Originals With Stub Marker</option></select>'
          + '</div>'
          + '</div>')
      + '  </div>'
      + '  <div class="wizard-panel-scroll">' + renderCleanupImpactPreview(this) + '</div>'
      + (isPublishing ? publishingBadge : '')
      + '</div>'
      + '<div class="wizard-panel">'
      + '  <div class="title-row"><div><div class="title">Resolved Output</div><div class="subtitle">Commit reuses the same prepared upload, resolved plan, and destination mapping.</div></div></div>'
      + (isBrowserMode
        ? ''
        : '  <div class="wizard-commit-policy-chip"><span class="muted">Cleanup Policy</span><strong>' + escapeHtml(cleanupPolicyLabel) + '</strong></div>')
      + '  <div class="wizard-panel-scroll">' + renderPlanSummary(this, { includeDestinations: true }) + '</div>'
      + '</div>';
  };

  proto._renderWizardFooter = function () {
    var atFirstStep = this._wizardStep === 1;
    var atLastStep = this._wizardStep === this._wizardStepCount();
    var commitButtonLabel = 'Publish Destinations';
    return ''
      + '<div class="wizard-footer">'
      + '  <div class="button-row"><button class="button" data-action="close-wizard"' + (this._loading ? ' disabled' : '') + '>Cancel</button></div>'
      + '  <div class="button-row">'
      + (!atFirstStep ? '<button class="button" data-action="wizard-back"' + (this._loading ? ' disabled' : '') + '>Back</button>' : '')
      + (this._wizardStep === 4
        ? '<button class="button" data-action="run-wizard-validation"' + (this._loading ? ' disabled' : '') + '>Re-Validate</button>' + '<button class="button primary" data-action="wizard-next"' + (!this._canAdvanceWizard() || this._loading ? ' disabled' : '') + '>Next</button>'
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
    this._uploadProgress = null;
    if (typeof this._setBusyPhase === 'function') {
      this._setBusyPhase('Publishing destinations', 'Publishing validated batch to selected destinations');
    }
    this._render();
    try {
      var validationData = this._validationData || await this._runWizardValidation(false);
      if (!validationData || !validationData.upload_id) {
        this._loading = false;
        this._render();
        return;
      }
      if (!this._validationReadyForCommit()) {
        throw new Error('Validation must be ready before commit, or every duplicate finding must have an explicit action.');
      }
      if (!this._destinationPlansReady()) {
        throw new Error('Choose a destination for every planned group before commit.');
      }
      var uploadId = validationData.upload_id;
      var sidecarBaseUrl = this._resolveSidecarUrl();
      var warningOverride = false;
      var overrideSummary = this._validationOverrideSummary();
      if (String(validationData.validation_state || '').trim().toLowerCase() !== 'ready') {
        warningOverride = !!(overrideSummary && overrideSummary.requiresWarningOverride);
      }
      // Issue #1307: send cleanup_policy with the publish so a Commit-step policy
      // change is applied without forcing a re-validation. Browser path is locked
      // to delete_on_verified per the existing UX contract.
      var commitCleanupPolicy = this._wizardMode === 'browser' ? 'delete_on_verified' : this._cleanupPolicy();
      var publishResponse = await postJsonWithAuth(this._hass, sidecarBaseUrl.replace(/\/$/, '') + '/api/intake/uploads/' + encodeURIComponent(String(uploadId || '')) + '/publish-by-destination', {
        group_destinations: this._buildDestinationPublishPayload(),
        cleanup_policy: commitCleanupPolicy,
        override_warning: warningOverride,
      });
      var changedCollections = [];
      if (Array.isArray(publishResponse && publishResponse.curated_model_ids) && publishResponse.curated_model_ids.length) {
        changedCollections.push('curated');
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
        group_results: publishResponse && Array.isArray(publishResponse.group_results) ? publishResponse.group_results : [],
      };
      this._status = 'Validated upload published successfully.';
      if (publishResponse && changedCollections.length) {
        fireModelCatalogDataChanged(changedCollections, {
          reason: 'publish-by-destination',
          uploadId: uploadId,
          curatedModelIds: publishResponse.curated_model_ids || [],
        });
      }
      this._preparedUploadId = null;
      this._validationData = null;
      this._validationDecisionMap = {};
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
      // Issue #1323: release the host page scroll lock that _openWizard set.
      // Without this, navigating away after a successful publish leaves
      // body.style.overflow = 'hidden' until the user hard-refreshes.
      if (typeof this._restoreBackgroundScroll === 'function') {
        this._restoreBackgroundScroll();
      }
      if (typeof this._clearBusyState === 'function') {
        this._clearBusyState();
      }
      await this._refreshAll();
    } catch (error) {
      this._error = error && error.message ? String(error.message) : 'Could not commit the intake batch.';
      this._loading = false;
      this._uploadProgress = null;
      if (typeof this._clearBusyState === 'function') {
        this._clearBusyState();
      }
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
    if (action === 'browser-open-path') {
      event.preventDefault();
      this._skipNextWizardScrollRestore = true;
      this._selectStepHighlight = null;
      this._browserSourcePath = normalizeBrowserRelativePath(target.getAttribute('data-path') || '');
      this._render();
      return;
    }
    if (action === 'browser-parent-path') {
      event.preventDefault();
      this._skipNextWizardScrollRestore = true;
      this._selectStepHighlight = null;
      this._browserSourcePath = normalizeBrowserRelativePath(target.getAttribute('data-path') || '');
      this._render();
      return;
    }
    if (action === 'remove-browser-folder') {
      event.preventDefault();
      // Issue #1324: align with Server path — "removing" a folder marks all
      // descendants as excluded so they remain visible on the left tree (with
      // strike-through + Restore) but are dropped from the staged list, plan
      // preview, and upload payload via _filterBrowserFilesForSubmit.
      var folderPath = normalizeBrowserRelativePath(target.getAttribute('data-path') || '');
      if (folderPath) {
        var prefix = folderPath + '/';
        var card = this;
        (this._browserFiles || []).forEach(function (entry) {
          var relativePath = normalizeBrowserRelativePath(entry.relative_path || entry.name || '');
          if (relativePath === folderPath || relativePath.indexOf(prefix) === 0) {
            card._setBrowserKeyExcluded(card._browserFileKey(entry), true);
          }
        });
        this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
        this._refreshWizardPreview();
        this._render();
      }
      return;
    }
    // Issue #1324: restore (un-exclude) all descendants of a previously
    // excluded browser folder. Triggered from the folder's Restore button.
    if (action === 'restore-browser-folder') {
      event.preventDefault();
      var restoreFolderPath = normalizeBrowserRelativePath(target.getAttribute('data-path') || '');
      if (restoreFolderPath) {
        var restorePrefix = restoreFolderPath + '/';
        var restoreCard = this;
        (this._browserFiles || []).forEach(function (entry) {
          var relativePath = normalizeBrowserRelativePath(entry.relative_path || entry.name || '');
          if (relativePath === restoreFolderPath || relativePath.indexOf(restorePrefix) === 0) {
            restoreCard._setBrowserKeyExcluded(restoreCard._browserFileKey(entry), false);
          }
        });
        this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
        this._refreshWizardPreview();
        this._render();
      }
      return;
    }
    // Issue #1324: restore a single previously excluded browser file.
    if (action === 'restore-browser-file') {
      event.preventDefault();
      var restoreKey = String(target.getAttribute('data-key') || '');
      if (restoreKey) {
        this._setBrowserKeyExcluded(restoreKey, false);
        this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
        this._refreshWizardPreview();
        this._render();
      }
      return;
    }
    // Issue #1324: exclude a specific item that lives inside a selected folder.
    if (action === 'exclude-item') {
      event.preventDefault();
      var excludePath = String(target.getAttribute('data-path') || '');
      if (excludePath) {
        var currentExcluded = Array.isArray(this._excludedItems) ? this._excludedItems : [];
        if (currentExcluded.indexOf(excludePath) === -1) {
          this._excludedItems = currentExcluded.concat([excludePath]);
        }
        this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
        this._refreshWizardPreview();
        this._render();
      }
      return;
    }
    // Issue #1324: restore (un-exclude) a previously excluded item.
    if (action === 'unexclude-item') {
      event.preventDefault();
      var restorePath = String(target.getAttribute('data-path') || '');
      if (restorePath) {
        this._excludedItems = (Array.isArray(this._excludedItems) ? this._excludedItems : [])
          .filter(function (p) { return p !== restorePath; });
        this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
        this._refreshWizardPreview();
        this._render();
      }
      return;
    }
    // Issue #1347: jump backward to a specific wizard step (used by the
    // Validate step's "Go to Select Step" link when exclusions are present).
    if (action === 'wizard-jump-step') {
      event.preventDefault();
      var jumpTarget = parseInt(target.getAttribute('data-step') || '0', 10);
      if (jumpTarget >= 1 && jumpTarget <= this._wizardStepCount() && jumpTarget < this._wizardStep) {
        this._goToWizardStep(jumpTarget);
      }
      return;
    }
    if (action === 'validation-toggle-more-info') {
      event.preventDefault();
      var infoKey = String(target.getAttribute('data-finding-key') || '').trim().toLowerCase();
      if (!infoKey) {
        return;
      }
      if (!this._validationInfoExpandedMap || typeof this._validationInfoExpandedMap !== 'object') {
        this._validationInfoExpandedMap = {};
      }
      var nextInfoMap = Object.assign({}, this._validationInfoExpandedMap);
      nextInfoMap[infoKey] = !nextInfoMap[infoKey];
      this._validationInfoExpandedMap = nextInfoMap;
      this._render();
      return;
    }
    if (action === 'validation-open-image-preview') {
      event.preventDefault();
      var imageUrl = String(target.getAttribute('data-image-url') || '').trim();
      if (!imageUrl) {
        return;
      }
      this._validationImagePreview = {
        url: imageUrl,
        label: String(target.getAttribute('data-image-label') || 'Comparison preview').trim(),
      };
      this._render();
      return;
    }
    if (action === 'validation-close-image-preview') {
      event.preventDefault();
      this._validationImagePreview = null;
      this._render();
      return;
    }
    // Issue #1349: clicking a Server right-pane row jumps the left-side
    // browse tree to that entry's parent folder. The right pane is no
    // longer used for navigation (it only summarizes the current selection).
    if (action === 'jump-server-parent') {
      event.preventDefault();
      this._skipNextWizardScrollRestore = true;
      this._selectStepHighlight = { side: 'right', key: String(target.getAttribute('data-path') || '') };
      var serverParent = String(target.getAttribute('data-parent') || '/') || '/';
      this._loadBrowse(serverParent);
      return;
    }
    // Issue #1349: clicking a Browser right-pane row jumps the left-side
    // staged-files tree to that file's parent folder for parity with the
    // Server path.
    if (action === 'jump-browser-parent') {
      event.preventDefault();
      this._skipNextWizardScrollRestore = true;
      this._selectStepHighlight = { side: 'right', key: String(target.getAttribute('data-browse-key') || '') };
      this._browserSourcePath = normalizeBrowserRelativePath(target.getAttribute('data-parent') || '');
      this._render();
      return;
    }
    if (action === 'browse-parent' || action === 'browse-path') {
      this._skipNextWizardScrollRestore = true;
      this._selectStepHighlight = null;
    }
    if (action === 'intake-root-kind-switch') {
      event.preventDefault();
      var nextKind = String(target.getAttribute('data-kind') || '') === 'working' ? 'working' : 'intake';
      if (this._intakeRootKind === nextKind) {
        return;
      }
      var rootsList = Array.isArray(this._roots) ? this._roots : [];
      var match = rootsList.find(function (r) { return r && r.kind === nextKind && r.accessible && r.path; })
        || rootsList.find(function (r) { return r && r.kind === nextKind && r.path; });
      if (!match) {
        return;
      }
      this._intakeRootKind = nextKind;
      this._skipNextWizardScrollRestore = true;
      this._selectStepHighlight = null;
      this._loadBrowse(match.path);
      return;
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
    if (action === 'browser-loose-file-grouping') {
      var groupingPath = String(target.getAttribute('data-relative-path') || '');
      if (!groupingPath) {
        return;
      }
      var nextGrouping = String(target.value || 'none').trim().toLowerCase();
      this._updateBrowserEntriesWhere(function (entry) {
        return String(entry.relative_path || entry.name || '') === groupingPath;
      }, {
        grouping_strategy: nextGrouping,
      });
      this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
      this._refreshWizardPreview();
      this._render();
      return;
    }
    if (action === 'browser-loose-file-title-source') {
      var titlePath = String(target.getAttribute('data-relative-path') || '');
      if (!titlePath) {
        return;
      }
      var nextTitleSource = String(target.value || 'first-file').trim().toLowerCase();
      var existingEntry = (this._browserFiles || []).find(function (entry) {
        return String(entry.relative_path || entry.name || '') === titlePath;
      }) || {};
      this._updateBrowserEntriesWhere(function (entry) {
        return String(entry.relative_path || entry.name || '') === titlePath;
      }, {
        group_title_source: nextTitleSource,
        group_title: nextTitleSource === 'custom' ? String(existingEntry.group_title || '') : '',
      });
      this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
      this._refreshWizardPreview();
      this._render();
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
        target_folder_slug: '',
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
        target_folder_slug: '',
        lookup_query: '',
        lookup_results: [],
        lookup_error: '',
        lookup_loading: false,
        selected_summary: null,
      });
      this._render();
      return;
    }
    if (action === 'validation-finding-action') {
      var findingKey = String(target.getAttribute('data-finding-key') || '').trim().toLowerCase();
      var findingPath = String(target.getAttribute('data-finding-path') || '').trim();
      var findingFilename = String(target.getAttribute('data-finding-filename') || '').trim();
      var conflictPath = String(target.getAttribute('data-conflict-path') || '').trim();
      var conflictFilename = String(target.getAttribute('data-conflict-filename') || '').trim();
      var checkKey = String(target.getAttribute('data-check-key') || '').trim();
      var selectedDecision = String(target.value || 'review').trim().toLowerCase();
      if (!this._validationDecisionMap || typeof this._validationDecisionMap !== 'object') {
        this._validationDecisionMap = {};
      }
      var nextDecisionMap = Object.assign({}, this._validationDecisionMap);
      if (selectedDecision === 'review' || !selectedDecision) {
        delete nextDecisionMap[findingKey];
      } else {
        nextDecisionMap[findingKey] = selectedDecision;
      }
      this._validationDecisionMap = nextDecisionMap;
      this._persistValidationActionDecision({
        finding_key: findingKey,
        decision: selectedDecision,
        check_key: checkKey,
        source_path: findingPath,
        source_name: findingFilename,
        target_path: conflictPath,
        target_name: conflictFilename,
      }).catch(function (_error) {
        // Keep the local selection even if audit logging fails; commit validation
        // flow still enforces explicit decisions before proceeding.
      });
      if (selectedDecision === 'exclude_source' || selectedDecision === 'exclude_conflict' || selectedDecision === 'exclude_both') {
        var exclusionPaths = [];
        if (selectedDecision === 'exclude_source' || selectedDecision === 'exclude_both') {
          exclusionPaths.push(findingPath);
        }
        if (selectedDecision === 'exclude_conflict' || selectedDecision === 'exclude_both') {
          exclusionPaths.push(conflictPath);
        }
        var normalizedExclusions = [];
        exclusionPaths.forEach(function (pathEntry) {
          var normalizedPath = String(pathEntry || '').trim();
          if (normalizedPath && normalizedExclusions.indexOf(normalizedPath) === -1) {
            normalizedExclusions.push(normalizedPath);
          }
        });
        var appliedCount = 0;
        normalizedExclusions.forEach(function (pathEntry) {
          if (this._applyValidationFindingExclusion(pathEntry)) {
            appliedCount += 1;
          }
        }, this);
        if (appliedCount === 0) {
          this._error = 'Could not exclude this finding because the source path could not be resolved.';
          this._render();
        }
        return;
      }
      this._error = '';
      this._render();
      return;
    }
    if (/^(browser-|selection-)/.test(action)) {
      this._invalidateWizardArtifacts({ deletePrepared: true, clearPreview: true });
      this._refreshWizardPreview();
      return;
    }
    // Issue #1307: changing the cleanup policy in the Commit step must NOT
    // invalidate the prepared upload — the policy is applied at publish/cleanup
    // time and the publish-by-destination call now ships the chosen value so
    // the upload row is updated server-side without re-validating.
    if (action === 'cleanup-policy') {
      this._render();
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
    if (action === 'browser-loose-file-group-title') {
      var looseRelativePath = String(target.getAttribute('data-relative-path') || '');
      if (!looseRelativePath) {
        return;
      }
      this._updateBrowserEntriesWhere(function (entry) {
        return String(entry.relative_path || entry.name || '') === looseRelativePath;
      }, {
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

  // Issue #1328: Override _render to attach highlight listeners after DOM update
  proto._captureWizardScrollState = function () {
    if (!this.shadowRoot) {
      return [];
    }
    var scrollers = this.shadowRoot.querySelectorAll('.wizard-panel-scroll, .wizard-validate-fixed');
    return Array.prototype.map.call(scrollers, function (node, index) {
      return {
        index: index,
        top: Number(node.scrollTop || 0),
      };
    });
  };

  proto._restoreWizardScrollState = function (state) {
    if (!this.shadowRoot || !Array.isArray(state) || !state.length) {
      return;
    }
    var scrollers = this.shadowRoot.querySelectorAll('.wizard-panel-scroll, .wizard-validate-fixed');
    state.forEach(function (entry) {
      var node = scrollers[entry.index];
      if (!node) {
        return;
      }
      node.scrollTop = Number(entry.top || 0);
    });
  };

  proto._render = function () {
    var stepBeforeRender = Number(this._wizardStep || 0);
    var shouldRestoreScroll = !!(this._wizardOpen && !this._skipNextWizardScrollRestore);
    var scrollState = shouldRestoreScroll ? this._captureWizardScrollState() : null;
    // Clear highlighting when leaving step 2
    if (this._wizardStep !== 2) {
      this._highlightSelection = null;
    }
    // Issue #1355: clear Select-step highlight when leaving step 1
    if (this._wizardStep !== 1) {
      this._selectStepHighlight = null;
    }
    originalRender.call(this);
    // Attach highlight listeners after rendering completes
    setTimeout(function () {
      this._attachFileTreeListeners();
      this._attachSelectStepHighlightListeners();
      this._attachHighlightListeners();
      // Restore only on same-step rerenders; step transitions should start at
      // the top of the new pane.
      if (scrollState && Number(this._wizardStep || 0) === stepBeforeRender) {
        this._restoreWizardScrollState(scrollState);
      }
      this._skipNextWizardScrollRestore = false;
    }.bind(this), 0);
  };
})();
