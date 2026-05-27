import { setupThumbnailLazyObserver, addShimmerAnimation, getCachedThumbnailObjectUrl } from './thumbnail-lazy-loader.js?v=5';
import { addUnifiedQueueEntry } from '../common/unified-queue-api-client.js?v=1';
import { UnifiedQueueDialogController, normalizeQueueDialogTargetState, queueDialogTargetStateLabel } from '../common/unified-queue-dialog.js?v=2';
import { pickIdeaPlaceholderUrl } from './idea-placeholders.js?v=1';

class ModelCatalogBrowserCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._loading = false;
    this._error = "";
    this._results = [];
    this._pagination = { page: 1, per_page: 12, total: 0, total_pages: 0 };
    this._filters = this._defaultFilters();
    this._viewMode = "compact";
    this._showMedia = true;
    this._browserScope = "models";
    this._leftNavSelectedKey = "all-models";
    this._leftNavCollapsed = false;
    this._leftNavAutoCollapsePending = false;
    this._leftNavDrawerOpen = false;
    this._workingProjection = [];
    this._workingProjectionRootPath = "";
    this._refreshSpin = false;
    this._activeActionMenu = "";
    this._mediaGalleryIndices = {};
    this._modelDetailCache = {};
    this._loadingModelMedia = {};
    this._pendingLoad = null;
    this._debounceHandle = null;
    this._deferredRenderHandle = null;
    this._progressiveAppendHandle = null;
    this._renderEpoch = 0;
    this._modelSidecarUrl = "";
    this._unifiedQueueByModelRef = {};
    this._unifiedQueueIndexLastFetchedAt = 0;
    this._unifiedQueueIndexCacheTtlMs = 15000;
    this._frequentsTuning = {
      window_days: 90,
      min_prints: 3,
      backfill_weight: 0.5,
      initialized: false,
    };
    this._visibilityCounts = { active: 0, archived: 0 };
    this._serverEntityTypeCounts = { model: 0, idea: 0 };
    this._facetCounts = { collections: [], tags: [] };
    this._globalFacets = null;
    this._globalFacetsLoading = false;
    this._collectionTree = null;
    this._collectionBrowse = null;
    this._expandedCollectionNodeIds = {};
    this._projects = [];
    this._projectsLoaded = false;
    this._projectsError = "";
    this._typeFilters = {
      model: true,
      idea: false,
      working: false,
    };
    this._queueDialogController = new UnifiedQueueDialogController(this, {
      loadSourceDetail: this._loadQueueDialogSourceDetail.bind(this),
      addEntry: async ({ queueApiBase, printerId, payload }) => {
        await addUnifiedQueueEntry({ queueApiBase, printerId, payload });
      },
      afterSubmit: async () => {
        await this._loadPage(this._currentPage(), false);
      },
      getPrinterId: () => String(this._config && this._config.queue_printer_id ? this._config.queue_printer_id : "p1"),
      getQueueApiBase: () => {
        const resolved = String(this._resolveModelSidecarUrl() || "").trim();
        return resolved ? `${resolved}/api/v1` : "";
      },
    });

    this._boundClick = this._handleClick.bind(this);
    this._boundInput = this._handleInput.bind(this);
    this._boundChange = this._handleChange.bind(this);
    this._boundKeyDown = this._handleKeyDown.bind(this);
    this._boundWheel = this._handleWheel.bind(this);
    this._boundCatalogDataChanged = this._handleCatalogDataChanged.bind(this);
    this._boundDetailChanged = this._handleDetailChanged.bind(this);
    this._didInitialRender = false;
    this._hasAttemptedLoad = false;
    this._lastAppliedScopeStamp = 0;
    this._catalogScope = "curated";
    this._thumbnailObserver = null;
    this._thumbnailObserverSetupHandle = null;
    this._renderRAFId = null;
    this._persistentStyle = null;
    this._contentRoot = null;

    // Multi-select primitive (#1401 Phase 0 Foundations)
    this._selectedModelRefs = new Set();
    this._selectionChangeCallbacks = [];
    this._multiSelectMode = false;

    this._ideaCreateDialogOpen = false;
    this._ideaCreateSubmitting = false;
    this._ideaCreateError = "";
    this._ideaCreateDraft = {
      title: "",
      notes: "",
      links: "",
      sketchUrl: "",
    };
    this._collectionActionDialog = {
      open: false,
      mode: "",
      collectionId: "",
      label: "",
      path: "",
      name: "",
      selectedParentId: "",
      options: [],
      error: "",
      submitting: false,
    };
    this._collectionActionFeedback = null;
    this._collectionActionFeedbackTimer = null;
    this._focusCollectionActionPrimaryAfterRender = false;
    this._perfSamples = [];
    this._lastLoadPerf = null;
    this._lastRenderPerf = null;
    this._pendingNavPerf = null;
    this._lastNavPerf = null;
  }

  _defaultFilters() {
    return {
      q: "",
      collection: "",
      creator: "",
      tag: "",
      tags: [],
      sort: "recent",
      favorites_only: false,
      frequents_only: false,
      recent_added_only: false,
      recent_printed_only: false,
      has_other_files: false,
      show_archived: false,
      project_id: null,
    };
  }

  _normalizedEntityType(value) {
    var normalized = String(value || "").trim().toLowerCase();
    if (normalized === "idea" || normalized === "model") {
      return normalized;
    }
    return "model";
  }

  _entityTypeForModel(model) {
    var direct = this._normalizedEntityType(model && model.entity_type);
    if (direct !== "model") {
      return direct;
    }
    var fields = model && model.custom_fields && typeof model.custom_fields === "object" ? model.custom_fields : {};
    var fieldType = this._normalizedEntityType(fields.entity_type);
    if (fieldType !== "model") {
      return fieldType;
    }
    var structured = model && model.structured_metadata && typeof model.structured_metadata === "object" ? model.structured_metadata : {};
    var catalogSignals = structured && structured.catalog_signals && typeof structured.catalog_signals === "object" ? structured.catalog_signals : {};
    return this._normalizedEntityType(catalogSignals.entity_type);
  }

  _isEntityTypeVisible(entityType) {
    var normalized = this._normalizedEntityType(entityType);
    if (normalized === "model") {
      return !!(this._typeFilters && this._typeFilters.model);
    }
    if (normalized === "idea") {
      return !!(this._typeFilters && this._typeFilters.idea);
    }
    return true;
  }

  _entityTypeCounts() {
    if (this._serverEntityTypeCounts) {
      return this._serverEntityTypeCounts;
    }
    var counts = { model: 0, idea: 0 };
    for (var i = 0; i < this._results.length; i++) {
      var entityType = this._entityTypeForModel(this._results[i]);
      counts[entityType] = (counts[entityType] || 0) + 1;
    }
    return counts;
  }

  _filteredResultsForScope() {
    if (this._browserScope === "collections") {
      return this._results;
    }
    if (this._browserScope === "working") {
      return this._workingProjection;
    }
    var filtered = [];
    for (var i = 0; i < this._results.length; i++) {
      var candidate = this._results[i];
      if (this._isEntityTypeVisible(this._entityTypeForModel(candidate))) {
        filtered.push(candidate);
      }
    }
    return filtered;
  }

  _normalizedTagFilterValues(values) {
    var source = [];
    if (Array.isArray(values)) {
      source = values.slice(0);
    } else if (typeof values === "string") {
      source = values.split(",");
    } else if (values) {
      source = [values];
    }
    var normalized = [];
    var seen = {};
    for (var i = 0; i < source.length; i++) {
      var value = String(source[i] || "").trim().toLowerCase();
      if (!value || seen[value]) {
        continue;
      }
      seen[value] = true;
      normalized.push(value);
    }
    return normalized;
  }

  _activeTagFilters() {
    var normalized = this._normalizedTagFilterValues(this._filters && this._filters.tags);
    if (normalized.length) {
      return normalized;
    }
    return this._normalizedTagFilterValues(this._filters && this._filters.tag);
  }

  _setActiveTagFilters(values) {
    var normalized = this._normalizedTagFilterValues(values);
    this._filters.tags = normalized;
    this._filters.tag = normalized.length === 1 ? normalized[0] : "";
  }

  _hasTagFilter(tagKey) {
    var normalized = String(tagKey || "").trim().toLowerCase();
    if (!normalized) {
      return false;
    }
    return this._activeTagFilters().indexOf(normalized) !== -1;
  }

  _selectedCollectionKey() {
    return String(this._filters && this._filters.collection || "").trim().toLowerCase();
  }

  _facetEntry(kind, key) {
    var normalizedKey = String(key || "").trim().toLowerCase();
    if (!normalizedKey) {
      return null;
    }
    var entries = this._facetCounts && Array.isArray(this._facetCounts[kind]) ? this._facetCounts[kind] : [];
    for (var i = 0; i < entries.length; i++) {
      var entry = entries[i] || {};
      var entryKey = String(entry.key || "").trim().toLowerCase();
      if (entryKey === normalizedKey) {
        return entry;
      }
    }
    return null;
  }

  _displayCollectionLabel(collectionKey) {
    var normalizedKey = String(collectionKey || "").trim().toLowerCase();
    if (!normalizedKey) {
      return "";
    }
    if (normalizedKey === "__unassigned__") {
      return "No Collection";
    }
    var facetEntry = this._facetEntry("collections", normalizedKey);
    if (facetEntry) {
      return String(facetEntry.label || facetEntry.key || normalizedKey).trim();
    }
    var collectionTree = this._activeCollectionTree();
    if (collectionTree && Array.isArray(collectionTree.nodes)) {
      for (var index = 0; index < collectionTree.nodes.length; index++) {
        var treeNode = collectionTree.nodes[index] || {};
        var filterKey = String(treeNode.filter_key || "").trim().toLowerCase();
        if (filterKey && filterKey === normalizedKey) {
          return String(treeNode.path || treeNode.label || treeNode.name || normalizedKey).trim();
        }
      }
    }
    return normalizedKey;
  }

  _normalizeCollectionTreePayload(payload) {
    if (!payload || typeof payload !== "object") {
      return { items: [], nodes: [], unassigned_model_count: 0, path_separator: " / " };
    }
    return {
      contract: String(payload.contract || "collection-tree.v1alpha1"),
      items: Array.isArray(payload.items) ? payload.items : [],
      nodes: Array.isArray(payload.nodes) ? payload.nodes : [],
      root_collection_ids: Array.isArray(payload.root_collection_ids) ? payload.root_collection_ids : [],
      unassigned_model_count: Math.max(0, Number(payload.unassigned_model_count || 0) || 0),
      path_separator: String(payload.path_separator || " / "),
    };
  }

  _activeCollectionTree() {
    if (this._globalFacets && this._globalFacets.collection_tree && Array.isArray(this._globalFacets.collection_tree.items)) {
      return this._globalFacets.collection_tree;
    }
    if (this._collectionTree && Array.isArray(this._collectionTree.items)) {
      return this._collectionTree;
    }
    return null;
  }

  _findCollectionTreeNodePathByFilterKey(filterKey) {
    var normalizedFilterKey = String(filterKey || "").trim().toLowerCase();
    if (!normalizedFilterKey) {
      return [];
    }
    var collectionTree = this._activeCollectionTree();
    var items = collectionTree && Array.isArray(collectionTree.items) ? collectionTree.items : [];
    var foundPath = [];
    var visit = function (nodes, ancestry) {
      for (var index = 0; index < nodes.length; index++) {
        var node = nodes[index] || {};
        var nodeId = String(node.collection_id || "").trim();
        var nextPath = ancestry.concat(nodeId ? [nodeId] : []);
        if (String(node.filter_key || "").trim().toLowerCase() === normalizedFilterKey) {
          foundPath = nextPath;
          return true;
        }
        if (Array.isArray(node.children) && node.children.length && visit(node.children, nextPath)) {
          return true;
        }
      }
      return false;
    };
    visit(items, []);
    return foundPath;
  }

  _hydrateCollectionTreeExpansionState(collectionTree) {
    var tree = collectionTree || this._activeCollectionTree();
    if (!tree || !Array.isArray(tree.items)) {
      return;
    }
    for (var index = 0; index < tree.items.length; index++) {
      var rootNode = tree.items[index] || {};
      var rootId = String(rootNode.collection_id || "").trim();
      if (rootId && !Object.prototype.hasOwnProperty.call(this._expandedCollectionNodeIds, rootId)) {
        this._expandedCollectionNodeIds[rootId] = true;
      }
    }
    var selectedPath = this._findCollectionTreeNodePathByFilterKey(this._selectedCollectionKey());
    for (var pathIndex = 0; pathIndex < selectedPath.length; pathIndex++) {
      if (selectedPath[pathIndex]) {
        this._expandedCollectionNodeIds[selectedPath[pathIndex]] = true;
      }
    }
  }

  _renderCollectionTreeNode(node, depth) {
    var currentDepth = Math.max(0, Number(depth || 0) || 0);
    var nodeId = String(node && node.collection_id || "").trim();
    var label = String(node && (node.label || node.name || node.path) || "Collection").trim() || "Collection";
    var childNodes = Array.isArray(node && node.children) ? node.children : [];
    var hasChildren = childNodes.length > 0;
    var isExpanded = !hasChildren || !!this._expandedCollectionNodeIds[nodeId];
    var filterKey = String(node && node.filter_key || "").trim().toLowerCase();
    var isFilterable = !!filterKey;
    var count = Math.max(0, Number(node && node.model_count_total || 0) || 0);
    var icon = isExpanded ? 'mdi:folder-open-outline' : 'mdi:folder-outline';
    var navKey = 'collection:' + filterKey;
    var isActive = isFilterable && this._selectedCollectionKey() === filterKey;
    var trailingMarkup = isActive
      ? '<span class="left-nav-item-count dismiss" aria-hidden="true">\u00d7</span>'
      : '<span class="left-nav-item-count">' + this._escapeHtml(String(count)) + '</span>';
    var rowHtml = ''
      + '<div class="left-nav-tree-row' + (hasChildren ? ' has-children' : '') + '" style="--tree-depth:' + this._escapeHtml(String(currentDepth)) + '">'
      + (hasChildren
        ? '<button class="left-nav-tree-toggle" type="button" data-action="toggle-collection-node" data-node-id="' + this._escapeHtml(nodeId) + '" aria-label="' + this._escapeHtml((isExpanded ? 'Collapse ' : 'Expand ') + label) + '" aria-expanded="' + (isExpanded ? 'true' : 'false') + '"><ha-icon icon="mdi:chevron-' + (isExpanded ? 'down' : 'right') + '"></ha-icon></button>'
        : '')
      + (isFilterable
        ? '<button class="left-nav-item left-nav-tree-item' + (isActive ? ' active' : '') + '" type="button" data-action="select-left-nav-item" data-nav-key="' + this._escapeHtml(navKey) + '" aria-label="' + this._escapeHtml(label) + '" title="' + this._escapeHtml(label) + '" aria-pressed="' + (isActive ? 'true' : 'false') + '"><span class="left-nav-item-main"><ha-icon icon="' + this._escapeHtml(icon) + '"></ha-icon><span class="left-nav-item-label">' + this._escapeHtml(label) + '</span></span>' + trailingMarkup + '</button>'
        : '<div class="left-nav-item left-nav-tree-item left-nav-tree-label" title="' + this._escapeHtml(label) + '"><span class="left-nav-item-main"><ha-icon icon="' + this._escapeHtml(icon) + '"></ha-icon><span class="left-nav-item-label">' + this._escapeHtml(label) + '</span></span><span class="left-nav-item-count">' + this._escapeHtml(String(count)) + '</span></div>')
      + '</div>';
    if (!hasChildren || !isExpanded) {
      return '<div class="left-nav-tree-node">' + rowHtml + '</div>';
    }
    var childrenHtml = '';
    for (var index = 0; index < childNodes.length; index++) {
      childrenHtml += this._renderCollectionTreeNode(childNodes[index], currentDepth + 1);
    }
    return '<div class="left-nav-tree-node">' + rowHtml + '<div class="left-nav-tree-children">' + childrenHtml + '</div></div>';
  }

  _renderCollectionTreeSection() {
    var collectionTree = this._activeCollectionTree();
    var items = collectionTree && Array.isArray(collectionTree.items) ? collectionTree.items : [];
    var unassignedCount = collectionTree ? Math.max(0, Number(collectionTree.unassigned_model_count || 0) || 0) : 0;
    if (!items.length && unassignedCount <= 0) {
      return "";
    }
    this._hydrateCollectionTreeExpansionState(collectionTree);
    var html = '<div class="left-nav-tree">';
    for (var index = 0; index < items.length; index++) {
      html += this._renderCollectionTreeNode(items[index], 0);
    }
    if (unassignedCount > 0) {
      html += this._renderLeftNavItem('No Collection', 'collection:__unassigned__', unassignedCount, 'mdi:folder-remove-outline');
    }
    html += '</div>';
    return html;
  }

  _displayTagLabel(tagKey) {
    var normalizedKey = String(tagKey || "").trim().toLowerCase();
    if (!normalizedKey) {
      return "";
    }
    var facetEntry = this._facetEntry("tags", normalizedKey);
    if (facetEntry) {
      return String(facetEntry.label || facetEntry.key || normalizedKey).trim();
    }
    return normalizedKey;
  }

  _requestedCatalogEntityTypes() {
    if (this._browserScope !== "models") {
      return "";
    }
    var requested = [];
    if (this._typeFilters && this._typeFilters.model) {
      requested.push("model");
    }
    if (this._typeFilters && this._typeFilters.idea) {
      requested.push("idea");
    }
    if (requested.length !== 1) {
      return "";
    }
    return requested[0];
  }

  _localModelIdForModel(model) {
    var localModelId = String(model && model.local_model_id || "").trim();
    if (localModelId) {
      return localModelId;
    }
    var publicId = String(model && model.public_id || "").trim();
    if (publicId && String(model && model.model_url || "").trim().indexOf("local://") === 0) {
      return publicId;
    }
    return "";
  }

  _promotionTargets(fromType) {
    var normalized = this._normalizedEntityType(fromType);
    if (normalized === "idea") {
      return ["model"];
    }
    return [];
  }

  _entityTypeBadgeLabel(entityType) {
    var normalized = this._normalizedEntityType(entityType);
    if (normalized === "idea") {
      return "Idea";
    }
    return "";
  }

  _slugifyName(value) {
    var slug = String(value || "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, "")
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "");
    return slug || "idea";
  }

  _generateIdeaLocalModelId(name) {
    var slug = this._slugifyName(name);
    var suffix = Date.now().toString(36).slice(-8);
    return slug + "--" + suffix;
  }

  _parseIdeaExternalLinks(rawValue) {
    var text = String(rawValue || "").trim();
    if (!text) {
      return [];
    }
    var tokens = text.split(/[\n,]+/);
    var links = [];
    for (var i = 0; i < tokens.length; i++) {
      var token = String(tokens[i] || "").trim();
      if (!token) {
        continue;
      }
      var parts = token.split("|");
      var url = String(parts[0] || "").trim();
      var label = String(parts[1] || "").trim();
      if (!url) {
        continue;
      }
      if (label) {
        links.push({ url: url, label: label });
      } else {
        links.push({ url: url });
      }
    }
    return links;
  }

  async _fetchGlobalFacets() {
    if (this._globalFacetsLoading) {
      return;
    }
    var sidecarUrl = String(this._resolveModelSidecarUrl() || "").trim().replace(/\/$/, "");
    if (!sidecarUrl) {
      return;
    }
    this._globalFacetsLoading = true;
    try {
      var params = new URLSearchParams();
      params.set("entity_types", "model,idea");
      params.set("show_archived", "false");
      params.set("show_ideas", "true");
      var resp = await fetch(sidecarUrl + "/api/facets?" + params.toString());
      if (!resp.ok) {
        return;
      }
      var data = await resp.json();
      if (data && data.success && data.facet_counts) {
        var collectionTree = this._normalizeCollectionTreePayload(data.collection_tree);
        this._collectionTree = collectionTree;
        this._hydrateCollectionTreeExpansionState(collectionTree);
        this._globalFacets = {
          collections: Array.isArray(data.facet_counts.collections) ? data.facet_counts.collections : [],
          tags: Array.isArray(data.facet_counts.tags) ? data.facet_counts.tags : [],
          collection_tree: collectionTree,
          entity_type_counts: data.entity_type_counts || {},
          total: Number(data.total || 0),
        };
        this._doRender();
      }
    } catch (_e) {
      // Silently fall back to search-scoped facets
    } finally {
      this._globalFacetsLoading = false;
    }
  }

  async _createIdeaEntity(ideaDraft) {
    var sidecarUrl = String(this._resolveModelSidecarUrl() || "").trim().replace(/\/$/, "");
    if (!sidecarUrl) {
      throw new Error("Model Catalog sidecar URL not configured");
    }
    var draft = (ideaDraft && typeof ideaDraft === "object") ? ideaDraft : { name: ideaDraft };
    var name = String(draft.name || "").trim();
    var notes = String(draft.notes || "").trim();
    var links = Array.isArray(draft.external_links) ? draft.external_links : [];
    var sketchImage = String(draft.sketch_image || "").trim();
    var payload = {
      local_model_id: this._generateIdeaLocalModelId(name),
      model_name: name,
      entity_type: "idea",
      tags: [],
    };
    if (notes) {
      payload.notes = notes;
    }
    if (links.length) {
      payload.external_links = links;
    }
    if (sketchImage) {
      payload.sketch_image = { url: sketchImage };
    }
    var response = await fetch(sidecarUrl + "/api/local/models", {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, await this._authHeaders(false)),
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });
    var data = {};
    try {
      data = await response.json();
    } catch (_error) {
      data = {};
    }
    if (!response.ok || !data.success) {
      throw new Error(String(data.error || ("Failed to create idea (HTTP " + String(response.status) + ")")));
    }
    return data;
  }

  _openIdeaCreateDialog() {
    this._ideaCreateDialogOpen = true;
    this._ideaCreateSubmitting = false;
    this._ideaCreateError = "";
    this._ideaCreateDraft = {
      title: "",
      notes: "",
      links: "",
      sketchUrl: "",
    };
    this._render();
  }

  _closeIdeaCreateDialog() {
    if (this._ideaCreateSubmitting) {
      return;
    }
    this._ideaCreateDialogOpen = false;
    this._ideaCreateSubmitting = false;
    this._ideaCreateError = "";
    this._render();
  }

  async _submitIdeaCreateDialog() {
    if (this._ideaCreateSubmitting) {
      return;
    }

    var normalizedIdeaName = String(this._ideaCreateDraft.title || "").trim();
    if (!normalizedIdeaName) {
      this._ideaCreateError = "Idea title is required.";
      this._render();
      return;
    }

    this._ideaCreateSubmitting = true;
    this._ideaCreateError = "";
    this._render();

    try {
      var created = await this._createIdeaEntity({
        name: normalizedIdeaName,
        notes: String(this._ideaCreateDraft.notes || "").trim(),
        external_links: this._parseIdeaExternalLinks(this._ideaCreateDraft.links),
        sketch_image: String(this._ideaCreateDraft.sketchUrl || "").trim(),
      });
      var ideaRef = String((created && (created.local_model_id || (created.summary && created.summary.model_ref) || "")) || "").trim();
      this._typeFilters.idea = true;
      this._activeActionMenu = "";
      this._error = "";
      this._ideaCreateDialogOpen = false;
      this._ideaCreateSubmitting = false;
      this._ideaCreateError = "";

      if (ideaRef) {
        this._openModelDetailPopup(ideaRef, normalizedIdeaName, "details");
      }

      this._requestLoad(1, true);
      this._render();
    } catch (error) {
      this._ideaCreateSubmitting = false;
      this._ideaCreateError = error && error.message ? String(error.message) : "Could not create idea.";
      this._render();
    }
  }

  _renderIdeaCreateDialog() {
    if (!this._ideaCreateDialogOpen) {
      return "";
    }
    return ''
      + '<div class="idea-create-backdrop" data-action="close-idea-create-dialog">'
      + '  <div class="idea-create-dialog" role="dialog" aria-modal="true" aria-label="Create Idea">'
      + '    <div class="idea-create-header">'
      + '      <div><h3>New Idea</h3><div class="idea-create-subtitle">Capture quickly, then open full Idea popup for richer editing.</div></div>'
      + '      <button class="modal-close-btn" type="button" data-action="close-idea-create-dialog" aria-label="Close">✕</button>'
      + '    </div>'
      + '    <div class="idea-create-body">'
      + '      <label class="idea-create-field"><span>Title <strong>*</strong></span><input class="idea-create-input" data-idea-field="title" type="text" maxlength="255" placeholder="What should we make?" value="' + this._escapeHtml(this._ideaCreateDraft.title) + '"></label>'
      + '      <label class="idea-create-field"><span>Notes (optional)</span><textarea class="idea-create-input" data-idea-field="notes" rows="3" maxlength="5000" placeholder="Context, constraints, rough concept...">' + this._escapeHtml(this._ideaCreateDraft.notes) + '</textarea></label>'
      + '      <label class="idea-create-field"><span>External links (optional)</span><textarea class="idea-create-input" data-idea-field="links" rows="3" placeholder="One per line. Use url|label for custom labels.">' + this._escapeHtml(this._ideaCreateDraft.links) + '</textarea></label>'
      + '      <label class="idea-create-field"><span>Sketch image URL (optional)</span><input class="idea-create-input" data-idea-field="sketchUrl" type="url" placeholder="https://..." value="' + this._escapeHtml(this._ideaCreateDraft.sketchUrl) + '"></label>'
      + (this._ideaCreateError ? '<div class="idea-create-error">' + this._escapeHtml(this._ideaCreateError) + '</div>' : '')
      + '    </div>'
      + '    <div class="idea-create-footer">'
      + '      <button class="toolbar-btn ghost" type="button" data-action="close-idea-create-dialog" ' + (this._ideaCreateSubmitting ? 'disabled' : '') + '>Cancel</button>'
      + '      <button class="toolbar-btn idea-create-submit" type="button" data-action="submit-idea-create-dialog" ' + (this._ideaCreateSubmitting ? 'disabled' : '') + '>' + (this._ideaCreateSubmitting ? 'Creating...' : 'Create Idea') + '</button>'
      + '    </div>'
      + '  </div>'
      + '</div>';
  }

  async _promoteEntity(localModelId, fromType, toType) {
    var sidecarUrl = String(this._resolveModelSidecarUrl() || "").trim().replace(/\/$/, "");
    if (!sidecarUrl) {
      throw new Error("Model Catalog sidecar URL not configured");
    }
    var response = await fetch(sidecarUrl + "/api/local/models/" + encodeURIComponent(localModelId) + "/promote", {
      method: "PUT",
      headers: Object.assign({ "Content-Type": "application/json" }, await this._authHeaders(false)),
      credentials: "same-origin",
      body: JSON.stringify({
        from_entity_type: this._normalizedEntityType(fromType),
        to_entity_type: this._normalizedEntityType(toType),
      }),
    });
    var data = {};
    try {
      data = await response.json();
    } catch (_error) {
      data = {};
    }
    if (!response.ok || !data.success) {
      throw new Error(String(data.error || ("Failed to promote entity (HTTP " + String(response.status) + ")")));
    }
    return data;
  }

  _clampInteger(value, fallback, min, max) {
    var numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return fallback;
    }
    return Math.max(min, Math.min(max, Math.round(numeric)));
  }

  _readInputNumber(entityId, fallback, min, max) {
    if (!this._hass || !this._hass.states) {
      return fallback;
    }
    var entity = this._hass.states[String(entityId || "")];
    if (!entity || entity.state === "unknown" || entity.state === "unavailable") {
      return fallback;
    }
    return this._clampInteger(entity.state, fallback, min, max);
  }

  _syncFrequentsTuningFromHelpers(force) {
    if (!force && this._frequentsTuning.initialized) {
      return;
    }
    this._frequentsTuning.window_days = this._readInputNumber("input_number.model_catalog_frequent_window_days", 90, 7, 3650);
    this._frequentsTuning.min_prints = this._readInputNumber("input_number.model_catalog_frequent_min_prints", 3, 1, 9999);
    this._frequentsTuning.backfill_weight = 0.5;
    this._frequentsTuning.initialized = true;
  }

  async _persistFrequentsTuningToHelpers() {
    if (!this._hass || typeof this._hass.callService !== "function") {
      return;
    }
    try {
      await this._hass.callService("input_number", "set_value", {
        entity_id: "input_number.model_catalog_frequent_window_days",
        value: this._clampInteger(this._frequentsTuning.window_days, 90, 7, 3650),
      });
      await this._hass.callService("input_number", "set_value", {
        entity_id: "input_number.model_catalog_frequent_min_prints",
        value: this._clampInteger(this._frequentsTuning.min_prints, 3, 1, 9999),
      });
    } catch (_error) {
      // Keep local state even if helper persistence fails.
    }
  }

  setConfig(config) {
    this._config = {
      title: config && config.title ? String(config.title) : "Catalog Browser",
      per_page: config && Number.isFinite(Number(config.per_page))
        ? Math.max(1, Math.min(50, Number(config.per_page)))
        : 12,
      queue_printer_id: config && config.queue_printer_id ? String(config.queue_printer_id) : "p1",
      model_entity: config && config.model_entity ? String(config.model_entity) : "",
      model_sidecar_url: config && config.model_sidecar_url ? String(config.model_sidecar_url) : "",
    };
    this._pagination.per_page = this._config.per_page;
    this._doRender();
  }

  set hass(hass) {
    var hadHass = !!this._hass;
    this._hass = hass;
    this._modelSidecarUrl = this._resolveModelSidecarUrl();
    this._syncFrequentsTuningFromHelpers(false);

    if (!hadHass && !this._hasAttemptedLoad && !this._loading && !this._error) {
      this._hasAttemptedLoad = true;
      this._didInitialRender = true;
      this._fetchGlobalFacets();
      this._requestLoad(1, this._isScopeStale());
    } else if (!hadHass || !this._didInitialRender) {
      this._didInitialRender = true;
      this._doRender();
    }
  }

  connectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.addEventListener("click", this._boundClick);
      this.shadowRoot.addEventListener("input", this._boundInput);
      this.shadowRoot.addEventListener("change", this._boundChange);
      this.shadowRoot.addEventListener("keydown", this._boundKeyDown);
      this.shadowRoot.addEventListener("wheel", this._boundWheel);
    }
    window.addEventListener("model-catalog-data-changed", this._boundCatalogDataChanged);
    window.addEventListener("model-catalog-detail-changed", this._boundDetailChanged);
    addShimmerAnimation();
    if (this._hass && this._hasAttemptedLoad && !this._loading) {
      if (this._isScopeStale()) {
        this._requestLoad(1, true);
      } else {
        this._requestLoad(this._currentPage(), false);
      }
    }
  }

  _setupThumbnailLazyLoading() {
    if (!this.shadowRoot) {
      return;
    }
    // Disconnect any prior observer so we don't stack one per render.
    // Stacked observers fire N parallel thumbnail fetches + img.src writes per
    // scroll event, which can produce visible repaint thrash on dense pages.
    if (this._thumbnailObserver && typeof this._thumbnailObserver.disconnect === "function") {
      try { this._thumbnailObserver.disconnect(); } catch (_e) { /* ignore */ }
      this._thumbnailObserver = null;
    }
    this._thumbnailObserver = setupThumbnailLazyObserver({
      rootElement: this.shadowRoot,
      root: null,
      timeout: 5000,
      retries: 2,
      useIntersectionObserver: true,
      rootMargin: "50px",
      threshold: 0.1,
    }) || null;
  }

  _scheduleThumbnailObserverSetup(delayMs) {
    // Debounced observer setup — prevents cascading observer disconnects when
    // multiple model detail loads resolve in rapid succession.  Each disconnect
    // drops pending IntersectionObserver callbacks, which can leave images in
    // permanent shimmer.  By coalescing, we create a single observer after the
    // burst of updates settles.
    if (this._thumbnailObserverSetupHandle) {
      window.clearTimeout(this._thumbnailObserverSetupHandle);
      this._thumbnailObserverSetupHandle = null;
    }
    var delay = Number.isFinite(Number(delayMs)) ? Math.max(0, Number(delayMs)) : 60;
    this._thumbnailObserverSetupHandle = window.setTimeout(function () {
      this._thumbnailObserverSetupHandle = null;
      this._setupThumbnailLazyLoading();
    }.bind(this), delay);
  }

  disconnectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.removeEventListener("click", this._boundClick);
      this.shadowRoot.removeEventListener("input", this._boundInput);
      this.shadowRoot.removeEventListener("change", this._boundChange);
      this.shadowRoot.removeEventListener("keydown", this._boundKeyDown);
      this.shadowRoot.removeEventListener("wheel", this._boundWheel);
    }
    window.removeEventListener("model-catalog-data-changed", this._boundCatalogDataChanged);
    window.removeEventListener("model-catalog-detail-changed", this._boundDetailChanged);
    this._cancelScheduledApply();
    if (this._renderRAFId) {
      cancelAnimationFrame(this._renderRAFId);
      this._renderRAFId = null;
    }
    if (this._deferredRenderHandle) {
      window.clearTimeout(this._deferredRenderHandle);
      this._deferredRenderHandle = null;
    }
    if (this._thumbnailObserverSetupHandle) {
      window.clearTimeout(this._thumbnailObserverSetupHandle);
      this._thumbnailObserverSetupHandle = null;
    }
    if (this._thumbnailObserver && typeof this._thumbnailObserver.disconnect === "function") {
      try { this._thumbnailObserver.disconnect(); } catch (_e) { /* ignore */ }
      this._thumbnailObserver = null;
    }
    if (this._collectionActionFeedbackTimer) {
      window.clearTimeout(this._collectionActionFeedbackTimer);
      this._collectionActionFeedbackTimer = null;
    }
  }

  getCardSize() {
    return 10;
  }

  async _authHeaders(forceRefresh) {
    var auth = this._hass && this._hass.auth ? this._hass.auth : null;
    if (!auth) {
      return {};
    }

    if (forceRefresh && typeof auth.refreshAccessToken === "function") {
      try {
        await auth.refreshAccessToken();
      } catch (_error) {
      }
    }

    var accessToken = auth.accessToken || (auth.data ? auth.data.accessToken : "");
    return accessToken ? { Authorization: "Bearer " + accessToken } : {};
  }

  _normalizeServiceResponse(payload) {
    if (Array.isArray(payload) && payload.length) {
      var firstItem = payload[0];
      if (firstItem && typeof firstItem === "object") {
        return this._normalizeServiceResponse(firstItem);
      }
    }
    if (payload && typeof payload === "object") {
      if (payload.service_response && typeof payload.service_response === "object") {
        return this._normalizeServiceResponse(payload.service_response);
      }
      if (payload.response && typeof payload.response === "object") {
        return this._normalizeServiceResponse(payload.response);
      }
      if (
        payload.content
        && typeof payload.content === "object"
        && (Object.prototype.hasOwnProperty.call(payload, "status")
          || Object.prototype.hasOwnProperty.call(payload, "headers"))
      ) {
        return Object.assign({}, payload.content, {
          content: payload.content,
          status: payload.status,
          headers: payload.headers,
        });
      }
    }
    return payload && typeof payload === "object" ? payload : {};
  }

  async _callServiceWithResponse(domain, service, data) {
    var endpoint = "/api/services/" + encodeURIComponent(String(domain || "")) + "/" + encodeURIComponent(String(service || "")) + "?return_response";
    var body = JSON.stringify(data && typeof data === "object" ? data : {});

    var response = await fetch(endpoint, {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, await this._authHeaders(false)),
      credentials: "same-origin",
      body: body,
    });

    if (response.status === 401) {
      response = await fetch(endpoint, {
        method: "POST",
        headers: Object.assign({ "Content-Type": "application/json" }, await this._authHeaders(true)),
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
      var message = payload && payload.message ? String(payload.message) : ("Service call failed (HTTP " + String(response.status) + ")");
      throw new Error(message);
    }

    return this._normalizeServiceResponse(payload);
  }

  _buildModelSearchRequestUrl(requestPayload) {
    var base = String(this._resolveModelSidecarUrl() || "").trim().replace(/\/$/, "");
    if (!/^https?:\/\//i.test(base)) {
      return "";
    }
    var payload = requestPayload && typeof requestPayload === "object" ? requestPayload : {};
    var params = [];
    var addText = function (key) {
      var value = Object.prototype.hasOwnProperty.call(payload, key) ? String(payload[key] || "").trim() : "";
      if (!value) {
        return;
      }
      params.push(encodeURIComponent(key) + "=" + encodeURIComponent(value));
    };
    var addBool = function (key) {
      if (!Object.prototype.hasOwnProperty.call(payload, key)) {
        return;
      }
      params.push(encodeURIComponent(key) + "=" + (payload[key] ? "true" : "false"));
    };
    var addInt = function (key) {
      if (!Object.prototype.hasOwnProperty.call(payload, key)) {
        return;
      }
      var num = Number(payload[key]);
      if (!Number.isFinite(num)) {
        return;
      }
      params.push(encodeURIComponent(key) + "=" + encodeURIComponent(String(Math.trunc(num))));
    };
    var addFloat = function (key) {
      if (!Object.prototype.hasOwnProperty.call(payload, key)) {
        return;
      }
      var num = Number(payload[key]);
      if (!Number.isFinite(num)) {
        return;
      }
      params.push(encodeURIComponent(key) + "=" + encodeURIComponent(String(num)));
    };

    addText("q");
    addText("collection");
    addText("creator");
    addText("tag");
    addText("tags");
    addText("sort");
    addBool("favorites_only");
    addBool("frequents_only");
    addBool("recent_added_only");
    addBool("recent_printed_only");
    addInt("frequent_window_days");
    addInt("frequent_min_prints");
    addFloat("frequent_backfill_weight");
    addBool("has_other_files");
    addBool("show_archived");
    addBool("show_ideas");
    addText("entity_types");
    addBool("refresh");
    addText("context");
    addText("archive_name");
    addText("source_file_name");
    addText("source_hash");
    addInt("project_id");
    addInt("page");
    addInt("per_page");

    var query = params.length ? ("?" + params.join("&")) : "";
    return base + "/api/models/search" + query;
  }

  _buildCollectionBrowseRequestUrl(requestPayload) {
    var base = String(this._resolveModelSidecarUrl() || "").trim().replace(/\/$/, "");
    if (!/^https?:\/\//i.test(base)) {
      return "";
    }
    var payload = requestPayload && typeof requestPayload === "object" ? requestPayload : {};
    var params = [];
    var addText = function (key) {
      var value = Object.prototype.hasOwnProperty.call(payload, key) ? String(payload[key] || "").trim() : "";
      if (!value) {
        return;
      }
      params.push(encodeURIComponent(key) + "=" + encodeURIComponent(value));
    };
    var addBool = function (key) {
      if (!Object.prototype.hasOwnProperty.call(payload, key)) {
        return;
      }
      params.push(encodeURIComponent(key) + "=" + (payload[key] ? "true" : "false"));
    };
    var addInt = function (key) {
      if (!Object.prototype.hasOwnProperty.call(payload, key)) {
        return;
      }
      var num = Number(payload[key]);
      if (!Number.isFinite(num)) {
        return;
      }
      params.push(encodeURIComponent(key) + "=" + encodeURIComponent(String(Math.trunc(num))));
    };
    var addFloat = function (key) {
      if (!Object.prototype.hasOwnProperty.call(payload, key)) {
        return;
      }
      var num = Number(payload[key]);
      if (!Number.isFinite(num)) {
        return;
      }
      params.push(encodeURIComponent(key) + "=" + encodeURIComponent(String(num)));
    };

    addText("q");
    addText("creator");
    addText("tag");
    addText("tags");
    addText("sort");
    addBool("favorites_only");
    addBool("frequents_only");
    addBool("recent_added_only");
    addBool("recent_printed_only");
    addInt("frequent_window_days");
    addInt("frequent_min_prints");
    addFloat("frequent_backfill_weight");
    addBool("has_other_files");
    addBool("show_archived");
    addBool("show_ideas");
    addText("entity_types");
    addBool("refresh");
    addInt("page");
    addInt("per_page");
    addText("collection_id");
    addText("display_mode");
    addText("collection_sort");

    var query = params.length ? ("?" + params.join("&")) : "";
    return base + "/api/collections/browse" + query;
  }

  async _searchModelsFast(requestPayload) {
    var directUrl = this._buildModelSearchRequestUrl(requestPayload);
    if (!directUrl) {
      return this._callServiceWithResponse("rest_command", "model_catalog_search_models", requestPayload);
    }

    var timeoutHandle = null;
    var controller = (typeof AbortController === "function") ? new AbortController() : null;
    try {
      if (controller) {
        timeoutHandle = window.setTimeout(function () {
          controller.abort();
        }, 12000);
      }
      var response = await fetch(directUrl, {
        method: "GET",
        headers: await this._authHeaders(false),
        credentials: "omit",
        signal: controller ? controller.signal : undefined,
      });

      if (response.status === 401) {
        response = await fetch(directUrl, {
          method: "GET",
          headers: await this._authHeaders(true),
          credentials: "omit",
          signal: controller ? controller.signal : undefined,
        });
      }

      if (response.ok) {
        var payload = await response.json();
        if (payload && typeof payload === "object") {
          return payload;
        }
      }
    } catch (_directError) {
      // Fall through to the HA rest_command path for reliability.
    } finally {
      if (timeoutHandle) {
        window.clearTimeout(timeoutHandle);
      }
    }

    return this._callServiceWithResponse("rest_command", "model_catalog_search_models", requestPayload);
  }

  async _browseCollectionsFast(requestPayload) {
    var directUrl = this._buildCollectionBrowseRequestUrl(requestPayload);
    if (!directUrl) {
      throw new Error("Model Catalog sidecar URL not configured");
    }

    var timeoutHandle = null;
    var controller = (typeof AbortController === "function") ? new AbortController() : null;
    try {
      if (controller) {
        timeoutHandle = window.setTimeout(function () {
          controller.abort();
        }, 12000);
      }
      var response = await fetch(directUrl, {
        method: "GET",
        headers: await this._authHeaders(false),
        credentials: "omit",
        signal: controller ? controller.signal : undefined,
      });
      if (response.status === 401) {
        response = await fetch(directUrl, {
          method: "GET",
          headers: await this._authHeaders(true),
          credentials: "omit",
          signal: controller ? controller.signal : undefined,
        });
      }
      var payload = {};
      try {
        payload = await response.json();
      } catch (_jsonError) {
        payload = {};
      }
      if (!response.ok || !payload || payload.success === false) {
        throw new Error(String(payload && payload.error ? payload.error : ("Collection browse failed (HTTP " + String(response.status) + ")")));
      }
      return payload;
    } finally {
      if (timeoutHandle) {
        window.clearTimeout(timeoutHandle);
      }
    }
  }

  _syncFormIntoFilters() {
    var root = this.shadowRoot;
    if (!root) {
      return;
    }
    var read = function (selector) {
      var node = root.querySelector(selector);
      return node ? String(node.value || "").trim() : "";
    };

    this._filters.q = read("#mc-q");
    this._filters.creator = read("#mc-creator");
    this._filters.sort = read("#mc-sort") || "recent";
    var perPageTop = Number(read("#mc-per-page") || 0);
    var perPageBottom = Number(read("#mc-per-page-bottom") || 0);
    var perPage = Number.isFinite(perPageTop) && perPageTop > 0 ? perPageTop : perPageBottom;
    if (Number.isFinite(perPage) && perPage > 0) {
      this._pagination.per_page = Math.max(1, Math.min(96, perPage));
    }
    this._filters.has_other_files = !!(root.querySelector("#mc-has-other-files") && root.querySelector("#mc-has-other-files").checked);
    this._filters.show_archived = !!(root.querySelector("#mc-show-archived") && root.querySelector("#mc-show-archived").checked);
    this._frequentsTuning.window_days = this._clampInteger(read("#mc-frequent-window"), this._frequentsTuning.window_days || 90, 7, 3650);
    this._frequentsTuning.min_prints = this._clampInteger(read("#mc-frequent-min-prints"), this._frequentsTuning.min_prints || 3, 1, 9999);
    this._frequentsTuning.backfill_weight = 0.5;
  }

  _applyPerPageChange(nextValue) {
    var nextPerPage = Math.max(1, Math.min(96, Number(nextValue || 12)));
    if (nextPerPage === Number(this._pagination.per_page || 12)) {
      return;
    }
    this._pagination.per_page = nextPerPage;
    this._cancelScheduledApply();
    this._refreshSpin = true;
    this._requestLoad(1, true);
    this._render();
  }

  _applyFilters() {
    this._syncFormIntoFilters();
    this._syncLeftNavSelectionFromFilters();
    this._requestLoad(1, false);
  }

  _scheduleDebouncedApply() {
    this._cancelScheduledApply();
    this._debounceHandle = window.setTimeout(() => {
      this._debounceHandle = null;
      this._applyFilters();
    }, 220);
  }

  _cancelScheduledApply() {
    if (this._debounceHandle) {
      window.clearTimeout(this._debounceHandle);
      this._debounceHandle = null;
    }
  }

  _scheduleDeferredRender(delayMs) {
    if (this._deferredRenderHandle) {
      window.clearTimeout(this._deferredRenderHandle);
      this._deferredRenderHandle = null;
    }
    var delay = Number.isFinite(Number(delayMs)) ? Math.max(0, Number(delayMs)) : 90;
    this._deferredRenderHandle = window.setTimeout(function () {
      this._deferredRenderHandle = null;
      this._render();
    }.bind(this), delay);
  }

  _recordPerfSample(type, payload) {
    var sample = {
      type: String(type || "unknown"),
      at: Date.now(),
      payload: payload && typeof payload === "object" ? payload : {},
    };
    this._perfSamples.push(sample);
    if (this._perfSamples.length > 60) {
      this._perfSamples.splice(0, this._perfSamples.length - 60);
    }
  }

  _perfNow() {
    return (window.performance && typeof window.performance.now === "function") ? window.performance.now() : Date.now();
  }

  _beginNavPerf(action, targetPage) {
    this._pendingNavPerf = {
      action: String(action || "unknown"),
      targetPage: Math.max(1, Number(targetPage || 1)),
      clickStartMs: this._perfNow(),
      requestStartMs: 0,
      loadStartMs: 0,
      searchEndMs: 0,
      queueEndMs: 0,
      loadEndMs: 0,
      renderEndMs: 0,
      completedPage: 0,
      searchMs: 0,
      queueMs: 0,
      loadMs: 0,
      clickToLoadStartMs: 0,
      clickToRenderMs: 0,
      clickToLoadEndMs: 0,
      pendingWhileLoading: false,
      timestamp: Date.now(),
    };
  }

  _commitNavPerfFromLoad(loadPerf) {
    if (!this._pendingNavPerf || !loadPerf || typeof loadPerf !== "object") {
      return;
    }
    this._pendingNavPerf.searchMs = Math.max(0, Number(loadPerf.searchMs || 0));
    this._pendingNavPerf.queueMs = Math.max(0, Number(loadPerf.queueMs || 0));
    this._pendingNavPerf.loadMs = Math.max(0, Number(loadPerf.totalMs || 0));
    this._pendingNavPerf.completedPage = Math.max(1, Number(loadPerf.page || 1));
    if (this._pendingNavPerf.clickStartMs > 0 && this._pendingNavPerf.loadStartMs > 0) {
      this._pendingNavPerf.clickToLoadStartMs = Math.max(0, Math.round(this._pendingNavPerf.loadStartMs - this._pendingNavPerf.clickStartMs));
    }
    if (this._pendingNavPerf.clickStartMs > 0 && this._pendingNavPerf.loadEndMs > 0) {
      this._pendingNavPerf.clickToLoadEndMs = Math.max(0, Math.round(this._pendingNavPerf.loadEndMs - this._pendingNavPerf.clickStartMs));
    }
  }

  _finalizeNavPerfAfterRender() {
    if (!this._pendingNavPerf || this._loading) {
      return;
    }
    this._pendingNavPerf.renderEndMs = this._perfNow();
    if (this._pendingNavPerf.clickStartMs > 0) {
      this._pendingNavPerf.clickToRenderMs = Math.max(0, Math.round(this._pendingNavPerf.renderEndMs - this._pendingNavPerf.clickStartMs));
    }
    this._lastNavPerf = Object.assign({}, this._pendingNavPerf, {
      timestamp: Date.now(),
    });
    this._recordPerfSample("nav", this._lastNavPerf);
    this._pendingNavPerf = null;
  }

  _shouldProgressiveResultsRender(visibleResults) {
    if (this._loading || this._browserScope === "collections" || this._viewMode === "media") {
      return false;
    }
    var count = Array.isArray(visibleResults) ? visibleResults.length : 0;
    return count >= 24;
  }

  _scheduleProgressiveResultsAppend(remainder, renderEpoch) {
    if (this._progressiveAppendHandle) {
      window.clearTimeout(this._progressiveAppendHandle);
      this._progressiveAppendHandle = null;
    }
    if (!Array.isArray(remainder) || !remainder.length) {
      return;
    }
    this._progressiveAppendHandle = window.setTimeout(function () {
      this._progressiveAppendHandle = null;
      if (renderEpoch !== this._renderEpoch) {
        return;
      }
      if (!this.shadowRoot || !this._contentRoot || this._loading) {
        return;
      }
      var resultsNode = this._contentRoot.querySelector('.results');
      if (!resultsNode) {
        return;
      }
      resultsNode.insertAdjacentHTML('beforeend', remainder.map(this._renderCatalogEntryCard.bind(this)).join(""));
      this._scheduleThumbnailObserverSetup(0);
    }.bind(this), 0);
  }

  _requestLoad(page, refresh) {
    var targetPage = Math.max(1, Number(page || 1));
    if (!this._hass) {
      return;
    }
    if (this._pendingNavPerf && !this._pendingNavPerf.requestStartMs) {
      this._pendingNavPerf.requestStartMs = this._perfNow();
    }
    if (this._loading) {
      if (this._pendingNavPerf) {
        this._pendingNavPerf.pendingWhileLoading = true;
      }
      this._pendingLoad = { page: targetPage, refresh: !!refresh };
      return;
    }
    this._loadPage(targetPage, refresh);
  }

  _handleDetailChanged(event) {
    var detail = event && event.detail && typeof event.detail === "object" ? event.detail : {};
    var modelRef = String(detail.modelRef || "").trim();
    if (!modelRef) {
      return;
    }
    delete this._modelDetailCache[modelRef];
    delete this._loadingModelMedia[modelRef];
    this._loadModelMedia({ public_id: modelRef });
    // Reload page data so updated tags, metadata, and queue state are reflected.
    this._loadPage(this._currentPage(), false);
    // Schedule a delayed retry in case the first thumbnail fetch fails due to a
    // transient CORS / network error right after the server-side change.
    window.setTimeout(function () {
      this._retryFailedCardThumb(modelRef);
    }.bind(this), 3000);
  }

  _handleCatalogDataChanged(event) {
    var detail = event && event.detail && typeof event.detail === "object" ? event.detail : {};
    var scopes = Array.isArray(detail.scopes) ? detail.scopes : [];
    if (scopes.length && scopes.indexOf("curated") < 0 && scopes.indexOf("all") < 0) {
      return;
    }
    var stamp = Number(detail.stamp || 0) || 0;
    if (stamp) {
      this._lastAppliedScopeStamp = stamp;
    }
    this._requestLoad(1, true);
  }

  _isScopeStale() {
    var shared = window.ModelCatalogIntakeShared;
    if (!shared || typeof shared.getModelCatalogScopeStamp !== "function") {
      return false;
    }
    var latest = shared.getModelCatalogScopeStamp(this._catalogScope || "curated");
    return latest > (Number(this._lastAppliedScopeStamp) || 0);
  }

  async _loadPage(page, refresh) {
    if (!this._hass) {
      return;
    }

    if (this._browserScope === "working") {
      this._browserScope = "models";
    }

    var includeWorkingInModels = this._browserScope === "models" && !!(this._typeFilters && this._typeFilters.working);

    var perfStart = (window.performance && typeof window.performance.now === "function") ? window.performance.now() : Date.now();
    var searchStart = perfStart;
    var searchEnd = searchStart;
    var queueStart = 0;
    var queueEnd = 0;

    this._loading = true;
    this._error = "";
    if (this._pendingNavPerf) {
      this._pendingNavPerf.loadStartMs = perfStart;
    }
    this._doRender();

    var shared = window.ModelCatalogIntakeShared;
    var stampSnapshot = shared && typeof shared.getModelCatalogScopeStamp === "function"
      ? shared.getModelCatalogScopeStamp(this._catalogScope || "curated")
      : 0;

    try {
      var entityTypes = this._requestedCatalogEntityTypes();
      var activeTags = this._activeTagFilters();
      var requestPayload = {
        q: this._filters.q,
        collection: this._filters.collection,
        creator: this._filters.creator,
        tag: activeTags.length === 1 ? activeTags[0] : "",
        tags: activeTags.join(","),
        sort: this._filters.sort,
        favorites_only: !!this._filters.favorites_only,
        frequents_only: !!this._filters.frequents_only,
        recent_added_only: !!this._filters.recent_added_only,
        recent_printed_only: !!this._filters.recent_printed_only,
        frequent_window_days: this._clampInteger(this._frequentsTuning.window_days, 90, 7, 3650),
        frequent_min_prints: this._clampInteger(this._frequentsTuning.min_prints, 3, 1, 9999),
        frequent_backfill_weight: 0.5,
        has_other_files: !!this._filters.has_other_files,
        show_archived: !!this._filters.show_archived,
        show_ideas: !!(this._typeFilters && this._typeFilters.idea),
        entity_types: entityTypes,
        refresh: !!refresh,
        page: Math.max(1, Number(page || 1)),
        per_page: this._pagination.per_page,
      };
      if (this._filters.project_id) {
        requestPayload.project_id = this._filters.project_id;
      }

      var data;
      if (this._browserScope === "collections") {
        data = await this._browseCollectionsFast({
          q: requestPayload.q,
          creator: requestPayload.creator,
          tag: requestPayload.tag,
          tags: requestPayload.tags,
          sort: requestPayload.sort,
          favorites_only: requestPayload.favorites_only,
          frequents_only: requestPayload.frequents_only,
          recent_added_only: requestPayload.recent_added_only,
          recent_printed_only: requestPayload.recent_printed_only,
          frequent_window_days: requestPayload.frequent_window_days,
          frequent_min_prints: requestPayload.frequent_min_prints,
          frequent_backfill_weight: requestPayload.frequent_backfill_weight,
          has_other_files: requestPayload.has_other_files,
          show_archived: requestPayload.show_archived,
          show_ideas: requestPayload.show_ideas,
          entity_types: requestPayload.entity_types,
          refresh: requestPayload.refresh,
          page: requestPayload.page,
          per_page: requestPayload.per_page,
          collection_id: this._filters.collection,
        });
      } else {
        data = includeWorkingInModels
          ? await this._searchModelsFast(Object.assign({}, requestPayload, { page: 1, per_page: 100 }))
          : await this._searchModelsFast(requestPayload);
      }
      searchEnd = (window.performance && typeof window.performance.now === "function") ? window.performance.now() : Date.now();
      if (this._pendingNavPerf) {
        this._pendingNavPerf.searchEndMs = searchEnd;
      }
      this._results = this._browserScope === "collections"
        ? (Array.isArray(data && data.items)
          ? data.items.filter(function (entry) {
              return entry && entry.kind === "model" && entry.data && typeof entry.data === "object";
            }).map(function (entry) {
              return entry.data;
            })
          : [])
        : (includeWorkingInModels
          ? await this._loadAllModelSearchResults(Object.assign({}, requestPayload, { page: 1, per_page: 100 }), data)
          : (Array.isArray(data && data.results) ? data.results : []));
      this._collectionBrowse = this._browserScope === "collections" && data && typeof data === "object" ? data : null;
      var responseFilters = data && data.filters && typeof data.filters === "object" ? data.filters : {};
      var responseVisibility = data && data.visibility && typeof data.visibility === "object" ? data.visibility : {};
      var responseVisibilityCounts = responseVisibility && responseVisibility.counts && typeof responseVisibility.counts === "object"
        ? responseVisibility.counts
        : {};
      var responseEntityTypeCounts = data && data.entity_type_counts && typeof data.entity_type_counts === "object"
        ? data.entity_type_counts
        : {};
      this._serverEntityTypeCounts = {
        model: Math.max(0, Number(responseEntityTypeCounts.model || 0) || 0),
        idea: Math.max(0, Number(responseEntityTypeCounts.idea || 0) || 0),
      };
      this._visibilityCounts = {
        active: Math.max(0, Number(responseVisibilityCounts.active || 0) || 0),
        archived: Math.max(0, Number(responseVisibilityCounts.archived || 0) || 0),
      };
      var responseFacetCounts = data && data.facet_counts && typeof data.facet_counts === "object"
        ? data.facet_counts
        : {};
      this._facetCounts = {
        collections: Array.isArray(responseFacetCounts.collections) ? responseFacetCounts.collections : [],
        tags: Array.isArray(responseFacetCounts.tags) ? responseFacetCounts.tags : [],
      };
      if (this._collectionBrowse && this._collectionBrowse.tree) {
        this._collectionTree = this._normalizeCollectionTreePayload(this._collectionBrowse.tree);
        this._hydrateCollectionTreeExpansionState(this._collectionTree);
      }
      this._frequentsTuning.window_days = this._clampInteger(
        responseFilters.frequent_window_days,
        requestPayload.frequent_window_days,
        7,
        3650
      );
      this._frequentsTuning.min_prints = this._clampInteger(
        responseFilters.frequent_min_prints,
        requestPayload.frequent_min_prints,
        1,
        9999
      );
      if (Array.isArray(responseFilters.tags)) {
        this._setActiveTagFilters(responseFilters.tags);
      } else if (Object.prototype.hasOwnProperty.call(responseFilters, "tag")) {
        this._setActiveTagFilters(responseFilters.tag);
      }
      if (Object.prototype.hasOwnProperty.call(responseFilters, "frequents_only")) {
        this._filters.frequents_only = !!responseFilters.frequents_only;
      }
      if (Object.prototype.hasOwnProperty.call(responseFilters, "recent_added_only")) {
        this._filters.recent_added_only = !!responseFilters.recent_added_only;
      }
      if (Object.prototype.hasOwnProperty.call(responseFilters, "recent_printed_only")) {
        this._filters.recent_printed_only = !!responseFilters.recent_printed_only;
      }
      this._syncLeftNavSelectionFromFilters();

      if (includeWorkingInModels) {
        try {
          this._workingProjection = await this._loadWorkingProjectionData(refresh);
        } catch (_workingLoadError) {
          this._workingProjection = [];
        }
      } else {
        this._workingProjection = [];
      }

      var pagination = data && data.pagination ? data.pagination : {};
      this._pagination.page = Number(requestPayload.page || 1) || 1;
      this._pagination.per_page = Number(requestPayload.per_page || this._pagination.per_page) || this._pagination.per_page;
      if (this._browserScope === "collections") {
        this._pagination.total = Number(pagination.total || 0) || 0;
        this._pagination.total_pages = Number(pagination.total_pages || 0) || 0;
      } else if (includeWorkingInModels) {
        var mixedTotal = this._results.length + this._workingProjection.length;
        this._pagination.total = mixedTotal;
        this._pagination.total_pages = Math.max(1, Math.ceil(mixedTotal / (this._pagination.per_page || 12)));
        if (this._pagination.page > this._pagination.total_pages) {
          this._pagination.page = this._pagination.total_pages;
        }
      } else {
        this._pagination.total = Number(pagination.total || 0) || 0;
        this._pagination.total_pages = Number(pagination.total_pages || 0) || 0;
      }
      if (stampSnapshot > (Number(this._lastAppliedScopeStamp) || 0)) {
        this._lastAppliedScopeStamp = stampSnapshot;
      }
      queueStart = (window.performance && typeof window.performance.now === "function") ? window.performance.now() : Date.now();
      this._refreshUnifiedQueueIndex().then(function (queueIndexChanged) {
        queueEnd = (window.performance && typeof window.performance.now === "function") ? window.performance.now() : Date.now();
        if (this._pendingNavPerf) {
          this._pendingNavPerf.queueEndMs = queueEnd;
        }
        if (this._loading) {
          return;
        }
        if (!queueIndexChanged) {
          return;
        }
        if (this._viewMode === "media") {
          this._scheduleDeferredRender(70);
          return;
        }
        this._renderNow();
      }.bind(this));
    } catch (error) {
      this._results = [];
      this._pagination.page = 1;
      this._pagination.total = 0;
      this._pagination.total_pages = 0;
      this._unifiedQueueByModelRef = {};
      this._visibilityCounts = { active: 0, archived: 0 };
      this._serverEntityTypeCounts = { model: 0, idea: 0 };
      this._facetCounts = { collections: [], tags: [] };
      this._error = error && error.message ? String(error.message) : "Could not load model catalog.";
    } finally {
      this._loading = false;
      this._refreshSpin = false;
      var perfEnd = (window.performance && typeof window.performance.now === "function") ? window.performance.now() : Date.now();
      if (this._pendingNavPerf) {
        this._pendingNavPerf.loadEndMs = perfEnd;
      }
      this._lastLoadPerf = {
        page: Math.max(1, Number(page || 1)),
        searchMs: Math.max(0, Math.round(searchEnd - searchStart)),
        queueMs: queueEnd > queueStart ? Math.max(0, Math.round(queueEnd - queueStart)) : 0,
        totalMs: Math.max(0, Math.round(perfEnd - perfStart)),
        resultCount: Array.isArray(this._results) ? this._results.length : 0,
        timestamp: Date.now(),
      };
      this._commitNavPerfFromLoad(this._lastLoadPerf);
      this._recordPerfSample("load", this._lastLoadPerf);
      this._renderNow();
      if (this._pendingLoad) {
        var pendingLoad = this._pendingLoad;
        this._pendingLoad = null;
        this._requestLoad(pendingLoad.page, pendingLoad.refresh);
      }
    }
  }

  _choosePreferredQueueEntry(current, candidate) {
    if (!current) {
      return candidate;
    }
    var currentActive = this._isUnifiedQueueActiveState(current.state);
    var candidateActive = this._isUnifiedQueueActiveState(candidate.state);
    if (candidateActive && !currentActive) {
      return candidate;
    }
    if (candidateActive === currentActive) {
      if (Number(candidate.rank || 0) < Number(current.rank || 0)) {
        return candidate;
      }
    }
    return current;
  }

  async _refreshUnifiedQueueIndex(options) {
    var opts = options && typeof options === "object" ? options : {};
    var force = !!opts.force;
    var now = Date.now();
    var ageMs = now - Number(this._unifiedQueueIndexLastFetchedAt || 0);
    var hasCache = this._unifiedQueueByModelRef && Object.keys(this._unifiedQueueByModelRef).length > 0;
    if (!force && hasCache && ageMs >= 0 && ageMs < Number(this._unifiedQueueIndexCacheTtlMs || 0)) {
      return false;
    }
    try {
      // Omit source_kind so the index includes both catalog_model and idea
      // entries. Idea-style entries added from the Model Catalog page still
      // reference the catalog model via source_id, and the card's left-border
      // queue ribbon needs to light up for those too.
      var queuePayload = await this._callServiceWithResponse("rest_command", "model_catalog_list_unified_queue_entries", {
        printer_id: this._config && this._config.queue_printer_id ? this._config.queue_printer_id : "p1",
        sort: "rank:asc",
        limit: 200,
        offset: 0,
      });
      var entries = Array.isArray(queuePayload && queuePayload.entries) ? queuePayload.entries : [];
      var byModelRef = {};
      for (var i = 0; i < entries.length; i++) {
        var entry = entries[i] || {};
        var entrySourceKind = String(entry.source_kind || "").toLowerCase();
        if (entrySourceKind !== "catalog_model" && entrySourceKind !== "idea") {
          continue;
        }
        var modelRef = String(entry.source_id || entry.source_ref || "").trim();
        if (!modelRef) {
          continue;
        }
        var candidate = {
          queue_entry_id: String(entry.queue_entry_id || ""),
          state: String(entry.state || "").toLowerCase(),
          rank: Number(entry.rank || 0),
        };
        if (!byModelRef[modelRef]) {
          byModelRef[modelRef] = { preferred: null, count: 0, entries: [] };
        }
        byModelRef[modelRef].preferred = this._choosePreferredQueueEntry(byModelRef[modelRef].preferred, candidate);
        byModelRef[modelRef].count += 1;
        byModelRef[modelRef].entries.push(candidate);
      }
      var changed = JSON.stringify(this._unifiedQueueByModelRef || {}) !== JSON.stringify(byModelRef);
      this._unifiedQueueByModelRef = byModelRef;
      this._unifiedQueueIndexLastFetchedAt = Date.now();
      return changed;
    } catch (_error) {
      this._unifiedQueueByModelRef = {};
      this._unifiedQueueIndexLastFetchedAt = 0;
      return false;
    }
  }

  _normalizedViewMode(mode) {
    var normalized = String(mode || "compact").trim().toLowerCase();
    if (normalized === "media" || normalized === "list") {
      return normalized;
    }
    return "compact";
  }

  _viewModeLabel(mode) {
    var normalized = this._normalizedViewMode(mode);
    if (normalized === "media") {
      return "Media";
    }
    if (normalized === "list") {
      return "List";
    }
    return "Compact";
  }

  _viewModeIcon(mode) {
    var normalized = this._normalizedViewMode(mode);
    if (normalized === "media") {
      return "mdi:image-multiple-outline";
    }
    if (normalized === "list") {
      return "mdi:format-list-bulleted";
    }
    return "mdi:view-grid-outline";
  }

  _renderViewModeMenuItem(mode) {
    var normalized = this._normalizedViewMode(mode);
    return ''
      + '<button class="view-mode-item' + (this._viewMode === normalized ? ' active' : '') + '" type="button" data-action="set-view" data-view-mode="' + this._escapeHtml(normalized) + '" ' + (this._loading ? 'disabled' : '') + '>'
      + '  <ha-icon icon="' + this._escapeHtml(this._viewModeIcon(normalized)) + '"></ha-icon>'
      + '  <span>' + this._escapeHtml(this._viewModeLabel(normalized)) + '</span>'
      + '</button>';
  }

  _renderViewModePicker() {
    var currentMode = this._normalizedViewMode(this._viewMode);
    return ''
      + '<details class="view-mode-menu">'
      + '  <summary class="toolbar-btn view-mode-trigger" aria-label="Card type: ' + this._escapeHtml(this._viewModeLabel(currentMode)) + '">'
      + '    <ha-icon icon="' + this._escapeHtml(this._viewModeIcon(currentMode)) + '"></ha-icon>'
      + '    <span class="view-mode-label">' + this._escapeHtml(this._viewModeLabel(currentMode)) + '</span>'
      + '    <ha-icon class="view-mode-caret" icon="mdi:chevron-down"></ha-icon>'
      + '  </summary>'
      + '  <div class="view-mode-items">'
      + this._renderViewModeMenuItem("compact")
      + this._renderViewModeMenuItem("media")
      + this._renderViewModeMenuItem("list")
      + '  </div>'
      + '</details>';
  }

  _handleInput(event) {
    var target = event && event.target;
    if (target && target.classList && target.classList.contains("queue-dialog-notes")) {
      this._queueDialogNotes = String(target.value || "");
      return;
    }
    if (target && target.classList && target.classList.contains("collection-action-input")) {
      this._collectionActionDialog.name = String(target.value || "");
      if (this._collectionActionDialog.error) {
        this._collectionActionDialog.error = "";
      }
      return;
    }
    if (target && target.classList && target.classList.contains("idea-create-input")) {
      var field = String(target.getAttribute("data-idea-field") || "").trim();
      if (field && Object.prototype.hasOwnProperty.call(this._ideaCreateDraft, field)) {
        this._ideaCreateDraft[field] = String(target.value || "");
      }
      if (this._ideaCreateError) {
        this._ideaCreateError = "";
      }
      return;
    }
    if (!target || !target.classList || !target.classList.contains("control-input")) {
      return;
    }
    var tagName = String(target.tagName || "").toUpperCase();
    if (tagName === "SELECT") {
      return;
    }
    this._scheduleDebouncedApply();
  }

  async _handleChange(event) {
    var target = event && event.target;
    if (!target) {
      return;
    }
    if (target.classList && target.classList.contains("collection-action-select")) {
      this._collectionActionDialog.selectedParentId = String(target.value || "").trim().toLowerCase();
      if (this._collectionActionDialog.error) {
        this._collectionActionDialog.error = "";
      }
      return;
    }
    if (target.classList && target.classList.contains("bulk-source-select")) {
      var sourceValue = String(target.value || "").trim();
      if (sourceValue) {
        target.value = "";
        await this._bulkSetSource(sourceValue);
      }
      return;
    }
    if (target.classList && target.classList.contains("queue-dialog-target-state")) {
      this._queueDialogTargetState = this._normalizeQueueDialogTargetState(target.value);
      this._render();
      return;
    }
    var targetId = String(target.id || "").trim();
    if (targetId === "mc-view-mode") {
      this._viewMode = this._normalizedViewMode(target.value);
      this._render();
      return;
    }
    if (targetId === "mc-per-page" || targetId === "mc-per-page-bottom") {
      this._applyPerPageChange(target.value);
      return;
    }

    if (targetId === "mc-frequent-window" || targetId === "mc-frequent-min-prints") {
      this._syncFormIntoFilters();
      await this._persistFrequentsTuningToHelpers();
      this._cancelScheduledApply();
      this._applyFilters();
      return;
    }

    if (!target.classList || !target.classList.contains("control-input")) {
      return;
    }
    var tagName = String(target.tagName || "").toUpperCase();
    var type = String(target.type || "").toLowerCase();
    if (tagName === "SELECT" || type === "number") {
      this._cancelScheduledApply();
      this._applyFilters();
    }
  }

  _handleKeyDown(event) {
    if (!event) {
      return;
    }
    var rawTarget = event.target;
    var cardTarget = rawTarget && rawTarget.closest ? rawTarget.closest(".model-card[data-action='view-model-detail']") : null;
    if (cardTarget && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      cardTarget.click();
      return;
    }

    // Arrow-key navigation within the left-nav
    if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Home" || event.key === "End") {
      var navHost = rawTarget && rawTarget.closest ? rawTarget.closest(".left-nav") : null;
      if (navHost) {
        var focusables = navHost.querySelectorAll("button.left-nav-item, button.left-nav-section-trigger, label.left-nav-type-toggle");
        if (focusables.length) {
          event.preventDefault();
          var currentIndex = -1;
          for (var fi = 0; fi < focusables.length; fi++) {
            if (focusables[fi] === rawTarget || focusables[fi].contains(rawTarget)) {
              currentIndex = fi;
              break;
            }
          }
          var nextIndex;
          if (event.key === "Home") {
            nextIndex = 0;
          } else if (event.key === "End") {
            nextIndex = focusables.length - 1;
          } else if (event.key === "ArrowDown") {
            nextIndex = currentIndex < focusables.length - 1 ? currentIndex + 1 : 0;
          } else {
            nextIndex = currentIndex > 0 ? currentIndex - 1 : focusables.length - 1;
          }
          focusables[nextIndex].focus({ preventScroll: false });
          return;
        }
      }
    }

    // Escape closes the left-nav drawer
    if (event.key === "Escape") {
      if (this._collectionActionDialog && this._collectionActionDialog.open) {
        event.preventDefault();
        this._closeCollectionActionDialog();
        return;
      }
      var drawerNav = rawTarget && rawTarget.closest ? rawTarget.closest(".left-nav.drawer-open") : null;
      if (drawerNav && this._leftNavDrawerOpen) {
        event.preventDefault();
        this._leftNavDrawerOpen = false;
        this._focusNavToggleAfterRender = true;
        this._render();
        return;
      }
    }

    if (event.key !== "Enter") {
      return;
    }
    var target = event.target;
    if (target && target.classList && target.classList.contains("idea-create-input")) {
      var targetTag = String(target.tagName || "").toUpperCase();
      if (targetTag !== "TEXTAREA") {
        event.preventDefault();
        this._submitIdeaCreateDialog();
      }
      return;
    }
    if (target && target.classList && target.classList.contains("collection-action-input")) {
      event.preventDefault();
      this._submitCollectionActionDialog();
      return;
    }
    if (!target || !target.classList || !target.classList.contains("control-input")) {
      return;
    }
    event.preventDefault();
    this._cancelScheduledApply();
    this._applyFilters();
  }

  async _handleClick(event) {
    var rawTarget = event && event.target;
    var target = rawTarget && rawTarget.closest ? rawTarget.closest("[data-action]") : null;
    var menuHost = rawTarget && rawTarget.closest ? rawTarget.closest(".advanced-menu-shell") : null;
    var closeMenu = !!this._activeActionMenu && !menuHost;
    if (!target) {
      if (closeMenu) {
        this._activeActionMenu = "";
        this._updateActionMenus();
      }
      return;
    }
    var action = String(target.getAttribute("data-action") || "");

    if (closeMenu && action !== "toggle-actions") {
      this._activeActionMenu = "";
    }

    if (action === "clear-filters") {
      this._cancelScheduledApply();
      this._filters = this._defaultFilters();
      this._syncLeftNavSelectionFromFilters();
      this._syncFrequentsTuningFromHelpers(true);
      this._error = "";
      this._activeActionMenu = "";
      this._requestLoad(1, false);
      this._render();
      return;
    }

    if (action === "clear-selected-tag") {
      event.preventDefault();
      event.stopPropagation();
      var clearTagKey = String(target.getAttribute("data-tag") || "").trim().toLowerCase();
      if (!clearTagKey) {
        return;
      }
      this._setActiveTagFilters(this._activeTagFilters().filter(function (value) {
        return value !== clearTagKey;
      }));
      this._syncLeftNavSelectionFromFilters();
      this._cancelScheduledApply();
      this._requestLoad(1, false);
      this._render();
      return;
    }

    if (action === "clear-collection-filter") {
      event.preventDefault();
      event.stopPropagation();
      this._filters.collection = "";
      this._syncLeftNavSelectionFromFilters();
      this._cancelScheduledApply();
      this._requestLoad(1, false);
      this._render();
      return;
    }

    if (action === "toggle-left-nav-collapse") {
      event.preventDefault();
      event.stopPropagation();
      this._leftNavCollapsed = !this._leftNavCollapsed;
      this._leftNavAutoCollapsePending = false;
      this._render();
      return;
    }

    if (action === "toggle-left-nav-drawer") {
      event.preventDefault();
      event.stopPropagation();
      this._leftNavDrawerOpen = !this._leftNavDrawerOpen;
      if (this._leftNavDrawerOpen) {
        this._focusNavFirstItemAfterRender = true;
      } else {
        this._focusNavToggleAfterRender = true;
      }
      this._render();
      return;
    }

    if (action === "close-left-nav-drawer") {
      event.preventDefault();
      event.stopPropagation();
      if (this._leftNavDrawerOpen) {
        this._leftNavDrawerOpen = false;
        this._focusNavToggleAfterRender = true;
        this._render();
      }
      return;
    }

    if (action === "select-left-nav-item") {
      event.preventDefault();
      event.stopPropagation();
      var navKey = String(target.getAttribute("data-nav-key") || "all-models").trim() || "all-models";
      if (this._leftNavDrawerOpen) {
        this._focusNavToggleAfterRender = true;
      }
      this._applyLeftNavSelection(navKey, { closeDrawer: true, requestLoad: true, render: true });
      return;
    }

    if (action === "toggle-collection-node") {
      event.preventDefault();
      event.stopPropagation();
      var nodeId = String(target.getAttribute("data-node-id") || "").trim();
      if (nodeId) {
        this._expandedCollectionNodeIds[nodeId] = !this._expandedCollectionNodeIds[nodeId];
        this._render();
      }
      return;
    }

    if (action === "expand-left-nav-section") {
      event.preventDefault();
      event.stopPropagation();
      if (this._leftNavCollapsed) {
        this._leftNavCollapsed = false;
        this._leftNavAutoCollapsePending = true;
        this._render();
      }
      return;
    }

    if (action === "toggle-left-nav-type") {
      event.preventDefault();
      event.stopPropagation();
      var typeKey = String(target.getAttribute("data-type") || (rawTarget && rawTarget.getAttribute && rawTarget.getAttribute("data-type")) || "").trim().toLowerCase();
      if (typeKey !== "model" && typeKey !== "idea" && typeKey !== "working") {
        return;
      }
      var currentlyChecked = !!(this._typeFilters && this._typeFilters[typeKey]);
      var nextChecked = !currentlyChecked;

      var selectedCount = 0;
      selectedCount += this._typeFilters.model ? 1 : 0;
      selectedCount += this._typeFilters.idea ? 1 : 0;
      selectedCount += this._typeFilters.working ? 1 : 0;
      if (!nextChecked && selectedCount <= 1) {
        return;
      }

      this._typeFilters[typeKey] = nextChecked;

      if (this._browserScope === "working") {
        this._browserScope = "models";
      }

      this._syncLeftNavSelectionFromFilters();
      this._cancelScheduledApply();
      this._requestLoad(1, false);
      this._render();
      return;
    }

    if (action === "close-queue-dialog") {
      event.preventDefault();
      event.stopPropagation();
      if (target.classList && target.classList.contains("queue-dialog-backdrop") && rawTarget !== target) {
        return;
      }
      this._closeQueueDialog();
      return;
    }

    if (action === "open-idea-create-dialog") {
      event.preventDefault();
      event.stopPropagation();
      this._openIdeaCreateDialog();
      return;
    }

    if (action === "close-idea-create-dialog") {
      event.preventDefault();
      event.stopPropagation();
      if (target.classList && target.classList.contains("idea-create-backdrop") && rawTarget !== target) {
        return;
      }
      this._closeIdeaCreateDialog();
      return;
    }

    if (action === "close-collection-action-dialog") {
      event.preventDefault();
      event.stopPropagation();
      if (target.classList && target.classList.contains("collection-action-backdrop") && rawTarget !== target) {
        return;
      }
      this._closeCollectionActionDialog();
      return;
    }

    if (action === "submit-collection-action-dialog") {
      event.preventDefault();
      event.stopPropagation();
      await this._submitCollectionActionDialog();
      return;
    }

    if (action === "dismiss-collection-feedback") {
      event.preventDefault();
      event.stopPropagation();
      this._clearCollectionActionFeedback(true);
      return;
    }

    if (action === "submit-idea-create-dialog") {
      event.preventDefault();
      event.stopPropagation();
      await this._submitIdeaCreateDialog();
      return;
    }

    if (action === "queue-dialog-mode") {
      event.preventDefault();
      event.stopPropagation();
      this._setQueueDialogMode(target.getAttribute("data-mode"));
      return;
    }

    if (action === "queue-dialog-submit") {
      event.preventDefault();
      event.stopPropagation();
      await this._submitQueueDialog();
      return;
    }

    if (action === "queue-dialog-select-all") {
      event.preventDefault();
      event.stopPropagation();
      this._setQueueDialogAllPlatesSelected(true);
      return;
    }

    if (action === "queue-dialog-clear-all") {
      event.preventDefault();
      event.stopPropagation();
      this._setQueueDialogAllPlatesSelected(false);
      return;
    }

    if (action === "queue-dialog-toggle-file") {
      event.preventDefault();
      event.stopPropagation();
      this._toggleQueueDialogFileSelection(String(target.getAttribute("data-file-id") || "").trim());
      return;
    }

    if (action === "queue-dialog-toggle-plate") {
      event.preventDefault();
      event.stopPropagation();
      this._toggleQueueDialogPlateSelection(
        String(target.getAttribute("data-file-id") || "").trim(),
        String(target.getAttribute("data-plate-id") || "").trim()
      );
      return;
    }

    if (action === "set-browser-scope") {
      var scope = String(target.getAttribute("data-scope") || "models").trim().toLowerCase();
      var nextScope = "models";
      if (scope === "collections") {
        nextScope = "collections";
      }
      if (this._browserScope !== nextScope) {
        this._browserScope = nextScope;
        if (nextScope === "models" && !this._typeFilters.model && !this._typeFilters.idea) {
          this._typeFilters.model = true;
        }
        this._requestLoad(1, false);
      }
      return;
    }

    if (action === "open-working-folder") {
      event.preventDefault();
      event.stopPropagation();
      var workingSlug = String(target.getAttribute("data-folder-slug") || "").trim();
      await this._openWorkingFilesWorkspace(workingSlug);
      return;
    }

    if (action === "open-working-intake") {
      event.preventDefault();
      event.stopPropagation();
      var workingFolderPath = String(target.getAttribute("data-folder-path") || "").trim();
      if (workingFolderPath) {
        this._launchWorkingFolderIntake(workingFolderPath);
      }
      return;
    }

    if (action === "set-view") {
      var viewModeMenu = target.closest ? target.closest("details.view-mode-menu") : null;
      if (viewModeMenu) {
        viewModeMenu.open = false;
      }
      var nextViewMode = this._normalizedViewMode(target.getAttribute("data-view-mode"));
      if (nextViewMode !== this._viewMode) {
        this._viewMode = nextViewMode;
        this._activeActionMenu = "";
        this._render();
      }
      return;
    }

    if (action === "toggle-favorites-filter") {
      this._filters.favorites_only = !this._filters.favorites_only;
      this._syncLeftNavSelectionFromFilters();
      this._cancelScheduledApply();
      this._requestLoad(1, false);
      this._render();
      return;
    }

    if (action === "toggle-frequents-filter") {
      this._filters.frequents_only = !this._filters.frequents_only;
      this._syncLeftNavSelectionFromFilters();
      this._cancelScheduledApply();
      this._requestLoad(1, false);
      this._render();
      return;
    }

    if (action === "toggle-other-files-filter") {
      this._filters.has_other_files = !this._filters.has_other_files;
      this._cancelScheduledApply();
      this._requestLoad(1, false);
      this._render();
      return;
    }

    if (action === "toggle-show-archived-filter") {
      this._filters.show_archived = !this._filters.show_archived;
      this._cancelScheduledApply();
      this._requestLoad(1, false);
      this._render();
      return;
    }

    if (action === "toggle-show-media") {
      this._showMedia = !this._showMedia;
      this._render();
      return;
    }

    if (action === "set-collection-filter") {
      var collectionName = String(target.getAttribute("data-collection") || "").trim();
      var collectionKey = collectionName.toLowerCase() === "unassigned" ? "__unassigned__" : collectionName.toLowerCase();
      this._applyLeftNavSelection("collection:" + collectionKey, { closeDrawer: true, requestLoad: true, render: true });
      return;
    }

    if (action === "refresh-page") {
      this._syncFormIntoFilters();
      this._refreshSpin = true;
      this._requestLoad(this._currentPage(), true);
      this._render();
      return;
    }

    if (action === "toggle-actions") {
      event.preventDefault();
      event.stopPropagation();
      var actionMenuRef = String(target.getAttribute("data-menu-key") || target.getAttribute("data-model-ref") || "").trim();
      this._activeActionMenu = this._activeActionMenu === actionMenuRef ? "" : actionMenuRef;
      this._updateActionMenus();
      return;
    }

    if (action === 'collection-rename') {
      event.preventDefault();
      event.stopPropagation();
      try {
        this._openCollectionActionDialog('rename', {
          collectionId: String(target.getAttribute('data-collection-id') || '').trim(),
          label: String(target.getAttribute('data-collection-label') || '').trim(),
          path: String(target.getAttribute('data-collection-path') || '').trim(),
        });
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not rename collection.';
        this._render();
      }
      return;
    }

    if (action === 'collection-move') {
      event.preventDefault();
      event.stopPropagation();
      try {
        await this._openCollectionMoveDialog({
          collectionId: String(target.getAttribute('data-collection-id') || '').trim(),
          label: String(target.getAttribute('data-collection-label') || '').trim(),
          path: String(target.getAttribute('data-collection-path') || '').trim(),
        });
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not move collection.';
        this._render();
      }
      return;
    }

    if (action === 'collection-delete') {
      event.preventDefault();
      event.stopPropagation();
      if (target.hasAttribute('disabled')) {
        return;
      }
      try {
        this._openCollectionActionDialog('delete', {
          collectionId: String(target.getAttribute('data-collection-id') || '').trim(),
          label: String(target.getAttribute('data-collection-label') || '').trim(),
          path: String(target.getAttribute('data-collection-path') || '').trim(),
        });
      } catch (error) {
        this._error = error && error.message ? String(error.message) : 'Could not delete collection.';
        this._render();
      }
      return;
    }

    if (action === "toggle-favorite") {
      event.preventDefault();
      event.stopPropagation();
      var favoriteModelRef = String(target.getAttribute("data-model-ref") || "").trim();
      var nextFavorite = String(target.getAttribute("data-next-favorite") || "").trim().toLowerCase() === "true";
      var previousFavorite = !nextFavorite;
      if (!favoriteModelRef || this._loading) {
        return;
      }

      // Optimistic update for immediate UI feedback.
      this._setModelFavoriteState(favoriteModelRef, nextFavorite);
      this._error = "";
      this._activeActionMenu = "";
      this._render();

      try {
        await this._callServiceWithResponse("rest_command", "model_catalog_toggle_model_favorite", {
          model_ref: favoriteModelRef,
          model_favorite: nextFavorite,
        });
      } catch (error) {
        this._setModelFavoriteState(favoriteModelRef, previousFavorite);
        this._error = error && error.message ? String(error.message) : "Could not update favorite state.";
        this._render();
        console.warn("Could not update favorite state", error);
      }
      return;
    }

    if (action === "bulk-pin-favorites") {
      event.preventDefault();
      event.stopPropagation();
      await this._bulkSetFavorites(true);
      return;
    }

    if (action === "bulk-unpin-favorites") {
      event.preventDefault();
      event.stopPropagation();
      await this._bulkSetFavorites(false);
      return;
    }

    if (action === "bulk-archive") {
      event.preventDefault();
      event.stopPropagation();
      await this._bulkSetVisibility("archived");
      return;
    }

    if (action === "bulk-unarchive") {
      event.preventDefault();
      event.stopPropagation();
      await this._bulkSetVisibility("active");
      return;
    }

    if (action === "open-model-history") {
      event.preventDefault();
      event.stopPropagation();
      var historyModelRef = String(target.getAttribute("data-model-ref") || "").trim();
      var historyModelName = String(target.getAttribute("data-model-name") || "Model Details").trim();
      if (historyModelRef) {
        this._openModelDetailPopup(historyModelRef, historyModelName, "prints");
      }
      return;
    }

    if (action === "delete-model") {
      event.preventDefault();
      event.stopPropagation();
      var deleteModelRef = String(target.getAttribute("data-model-ref") || "").trim();
      var deleteModelName = String(target.getAttribute("data-model-name") || "this model").trim();
      if (!deleteModelRef) {
        return;
      }
      await this._deleteModel(deleteModelRef, deleteModelName);
      return;
    }

    if (action === "open-model-viewer") {
      var viewerModelRef = String(target.getAttribute("data-model-ref") || "").trim();
      var viewerModelName = String(target.getAttribute("data-model-name") || "Model").trim();
      if (viewerModelRef) {
        await this._openModelViewerPopup(viewerModelRef, viewerModelName);
      }
      return;
    }

    if (action === "first-page") {
      this._syncFormIntoFilters();
      this._beginNavPerf("first-page", 1);
      this._requestLoad(1, false);
      return;
    }

    if (action === "prev-page" && this._currentPage() > 1) {
      this._syncFormIntoFilters();
      this._beginNavPerf("prev-page", this._currentPage() - 1);
      this._requestLoad(this._currentPage() - 1, false);
      return;
    }

    if (action === "next-page" && this._currentPage() < this._pageCount()) {
      this._syncFormIntoFilters();
      this._beginNavPerf("next-page", this._currentPage() + 1);
      this._requestLoad(this._currentPage() + 1, false);
      return;
    }

    if (action === "last-page") {
      this._syncFormIntoFilters();
      this._beginNavPerf("last-page", this._pageCount());
      this._requestLoad(this._pageCount(), false);
      return;
    }

    if (action === "open-import-browser" || action === "open-import-server") {
      event.preventDefault();
      event.stopPropagation();
      var importMenu = target.closest ? target.closest("details.import-menu") : null;
      if (importMenu) {
        importMenu.open = false;
      }
      this._openIntakePopup(action === "open-import-server" ? "server" : "browser");
      return;
    }

    if (action === "open-model") {
      event.preventDefault();
      event.stopPropagation();
      var url = String(target.getAttribute("data-url") || "").trim();
      if (url) {
        window.open(url, "_blank", "noopener,noreferrer");
      }
      return;
    }

    if (action === "create-model") {
      event.preventDefault();
      event.stopPropagation();
      this._openIntakePopup("browser");
      return;
    }

    if (action === "create-idea") {
      event.preventDefault();
      event.stopPropagation();
      this._openIdeaCreateDialog();
      return;
    }

    if (action === "promote-entity") {
      event.preventDefault();
      event.stopPropagation();
      var localModelId = String(target.getAttribute("data-local-model-id") || "").trim();
      var fromType = this._normalizedEntityType(target.getAttribute("data-from-entity-type"));
      var toType = this._normalizedEntityType(target.getAttribute("data-to-entity-type"));
      var promoteName = String(target.getAttribute("data-model-name") || "Model").trim() || "Model";
      if (!localModelId) {
        this._error = "Promotion is only available for local catalog entries.";
        this._render();
        return;
      }
      if (!window.confirm('Promote "' + promoteName + '" from ' + fromType + ' to ' + toType + '?')) {
        return;
      }
      try {
        await this._promoteEntity(localModelId, fromType, toType);
        this._activeActionMenu = "";
        this._error = "";
        this._requestLoad(this._currentPage(), true);
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not promote entity.";
        this._render();
      }
      return;
    }

    if (action === "toggle-multi-select") {
      event.preventDefault();
      event.stopPropagation();
      this._multiSelectMode = !this._multiSelectMode;
      if (!this._multiSelectMode) {
        this._selectedModelRefs.clear();
        this._notifySelectionChanged();
      }
      this._render();
      return;
    }

    if (action === "exit-multi-select") {
      event.preventDefault();
      event.stopPropagation();
      this._multiSelectMode = false;
      this._selectedModelRefs.clear();
      this._notifySelectionChanged();
      this._render();
      return;
    }

    if (action === "toggle-model-select") {
      event.preventDefault();
      event.stopPropagation();
      var selectModelRef = String(target.getAttribute("data-model-ref") || "").trim();
      if (!selectModelRef) {
        return;
      }
      this._toggleModelSelection(selectModelRef);
      return;
    }

    if (action === "toggle-select-all-models") {
      event.preventDefault();
      event.stopPropagation();
      this._toggleSelectAllModels();
      return;
    }

    if (action === "clear-selection") {
      event.preventDefault();
      event.stopPropagation();
      this._clearModelSelection();
      return;
    }

    if (action === "view-model-detail") {
      event.preventDefault();
      event.stopPropagation();
      var modelRef = String(target.getAttribute("data-model-ref") || "").trim();
      var modelName = String(target.getAttribute("data-model-name") || "Model").trim();
      if (!modelRef || !this._hass) {
        return;
      }
      this._openModelDetailPopup(modelRef, modelName);
      return;
    }

    if (action === "media-prev" || action === "media-next") {
      event.preventDefault();
      event.stopPropagation();
      var mediaModelRef = String(target.getAttribute("data-model-ref") || "").trim();
      var galleryCount = Math.max(0, Number(target.getAttribute("data-gallery-count") || 0));
      if (mediaModelRef && galleryCount > 1) {
        this._setModelMediaIndex(mediaModelRef, this._currentModelMediaIndex(mediaModelRef, galleryCount) + (action === "media-next" ? 1 : -1), galleryCount);
      }
      return;
    }

    if (action === "queue-add") {
      event.preventDefault();
      event.stopPropagation();
      var queueModelRef = String(target.getAttribute("data-model-ref") || "").trim();
      var queueModelName = String(target.getAttribute("data-model-name") || "Model").trim();
      if (!queueModelRef || this._loading) {
        return;
      }

      try {
        this._error = "";
        this._activeActionMenu = "";

        var shouldRefresh = await this._applyUnifiedQueueAction(action, queueModelRef, { modelName: queueModelName });

        if (shouldRefresh) {
          await this._loadPage(this._currentPage(), false);
        }
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not update queue state.";
        this._render();
      }
    }
  }

  _isUnifiedQueueActiveState(state) {
    var normalized = String(state || "").trim().toLowerCase();
      return ["backlog", "up_next", "preparing", "ready", "in_progress", "blocked"].indexOf(normalized) >= 0;
  }

  _queueStateToRibbonState(state) {
    var normalized = String(state || "").trim().toLowerCase();
    if (this._isUnifiedQueueActiveState(normalized) || normalized === "done") {
      return normalized;
    }
    return "none";
  }

  _queueStateBorderColor(state) {
    var palette = {
      backlog:     '#7a6a57',
      up_next:     '#a07cff',
      preparing:   '#ff9a3c',
      ready:       '#e6d84a',
      in_progress: '#3aa9ff',
      blocked:     '#ff6b6b',
      done:        '#4fcf75',
    };
    return palette[state] || '#a07cff';
  }

  _normalizeQueueDialogTargetState(state) {
    var normalized = String(state || "").trim().toLowerCase();
      if (["backlog", "up_next", "preparing", "ready"].indexOf(normalized) >= 0) {
      return normalized;
    }
    return "up_next";
  }

  _queueDialogTargetStateLabel(state) {
    var normalized = this._normalizeQueueDialogTargetState(state);
      if (normalized === "preparing") {
        return "Preparing";
      }
    if (normalized === "ready") {
      return "Ready";
    }
    if (normalized === "backlog") {
      return "Backlog";
    }
    return "Up Next";
  }

  _resetQueueDialogState() {
    this._queueDialogOpen = false;
    this._queueDialogMode = "quick";
    this._queueDialogModelRef = "";
    this._queueDialogModelName = "";
    this._queueDialogIntent = "add";
    this._queueDialogExistingCount = 0;
    this._queueDialogTargetState = "up_next";
    this._queueDialogNotes = "";
    this._queueDialogLoading = false;
    this._queueDialogSubmitting = false;
    this._queueDialogError = "";
    this._queueDialogFiles = [];
  }

  _closeQueueDialog() {
    this._resetQueueDialogState();
    this._render();
  }

  async _openQueueDialog(modelRef, modelName, entries, options) {
    var normalizedEntries = Array.isArray(entries) ? entries : [];
    var dialogOptions = options && typeof options === "object" ? options : {};

    this._queueDialogOpen = true;
    this._queueDialogMode = "quick";
    this._queueDialogModelRef = String(modelRef || "").trim();
    this._queueDialogModelName = String(modelName || "Model").trim() || "Model";
    this._queueDialogIntent = dialogOptions.intent === "re-add" ? "re-add" : "add";
    this._queueDialogExistingCount = normalizedEntries.length;
    this._queueDialogTargetState = dialogOptions.defaultState ? this._normalizeQueueDialogTargetState(dialogOptions.defaultState) : "up_next";
    this._queueDialogNotes = "";
    this._queueDialogLoading = true;
    this._queueDialogSubmitting = false;
    this._queueDialogError = "";
    this._queueDialogFiles = [];
    this._render();

    try {
      this._queueDialogFiles = await this._loadQueueDialogSourceDetail(this._queueDialogModelRef);
    } catch (error) {
      this._queueDialogError = error && error.message ? String(error.message) : "Could not load model queue defaults.";
      this._queueDialogFiles = [];
    } finally {
      this._queueDialogLoading = false;
      this._render();
    }
  }

  async _loadQueueDialogSourceDetail(modelRef) {
    var response = await fetch(this._resolveModelSidecarUrl() + "/api/models/" + encodeURIComponent(modelRef) + "/detail");
    if (!response.ok) {
      throw new Error("Failed to load model detail (" + response.status + ").");
    }
    var payload = await response.json();
    var model = payload && payload.model && typeof payload.model === "object" ? payload.model : {};
    this._queueDialogEntityType = String(model.entity_type || "model").trim().toLowerCase() || "model";
    var files = Array.isArray(model.files) ? model.files : [];
    if (!files.length) {
      // Idea entities and file-less models are still queueable: fall through with
      // an empty files array so the dialog can submit an idea-style entry. See
      // unified-queue-board-card._submitAddToQueue for the canonical pattern.
      return [];
    }

    var normalized = await Promise.all(files.map(async function (file, index) {
      var fileId = String(file.id || file.file_id || "").trim() || ("catalog-file-" + String(index + 1));
      var fileName = String(file.filename || file.name || fileId).trim();
      var fileType = String(file.file_type || file.content_type || file.asset_type || "").toLowerCase();
      var lowerName = fileName.toLowerCase();
      var plates = [{ plate_id: "default", plate_name: "Primary Plate", selected: true, is_primary: true }];

      if (lowerName.endsWith(".3mf") || fileType.indexOf("3mf") >= 0) {
        try {
          var platesResponse = await fetch(this._resolveModelSidecarUrl() + "/api/models/" + encodeURIComponent(modelRef) + "/files/" + encodeURIComponent(fileId) + "/plates");
          if (platesResponse.ok) {
            var platesPayload = await platesResponse.json();
            var rawPlates = Array.isArray(platesPayload && platesPayload.plates) ? platesPayload.plates : [];
            if (rawPlates.length > 0) {
              plates = rawPlates.map(function (plate, plateIndex) {
                return {
                  plate_id: String(plate.plate_key || plate.plate_id || plate.id || ("plate-" + String(plateIndex + 1))).trim(),
                  plate_name: String(plate.plate_name || plate.name || ("Plate " + String(plateIndex + 1))).trim(),
                  selected: plateIndex === 0,
                  is_primary: plateIndex === 0,
                };
              });
            }
          }
        } catch (_error) {
        }
      }

      return {
        file_id: fileId,
        file_name: fileName,
        selected: index === 0,
        thumbnail_url: String(file.thumbnail_url || file.preview_url || "").trim(),
        plates: plates,
      };
    }.bind(this)));

    var hasSelectedFile = normalized.some(function (file) {
      return !!file.selected;
    });
    if (!hasSelectedFile && normalized.length > 0) {
      normalized[0].selected = true;
    }
    return normalized;
  }

  _setQueueDialogMode(mode) {
    var normalized = String(mode || "").trim().toLowerCase();
    if (normalized !== "quick" && normalized !== "plan") {
      return;
    }
    this._queueDialogMode = normalized;
    this._render();
  }

  _setQueueDialogAllPlatesSelected(selected) {
    var nextSelected = !!selected;
    this._queueDialogFiles = this._queueDialogFiles.map(function (file) {
      return Object.assign({}, file, {
        selected: nextSelected,
        plates: Array.isArray(file.plates)
          ? file.plates.map(function (plate) {
              return Object.assign({}, plate, { selected: nextSelected });
            })
          : [],
      });
    });
    this._render();
  }

  _toggleQueueDialogFileSelection(fileId) {
    if (!fileId) {
      return;
    }
    this._queueDialogFiles = this._queueDialogFiles.map(function (file) {
      if (String(file.file_id || "") !== fileId) {
        return file;
      }
      var nextSelected = !file.selected;
      return Object.assign({}, file, {
        selected: nextSelected,
        plates: Array.isArray(file.plates)
          ? file.plates.map(function (plate, plateIndex) {
              return Object.assign({}, plate, { selected: nextSelected ? plateIndex === 0 || !!plate.selected : false });
            })
          : [],
      });
    });
    this._render();
  }

  _toggleQueueDialogPlateSelection(fileId, plateId) {
    if (!fileId || !plateId) {
      return;
    }
    this._queueDialogFiles = this._queueDialogFiles.map(function (file) {
      if (String(file.file_id || "") !== fileId) {
        return file;
      }
      var nextPlates = (file.plates || []).map(function (plate) {
        if (String(plate.plate_id || "") !== plateId) {
          return plate;
        }
        return Object.assign({}, plate, { selected: !plate.selected });
      });
      var hasSelectedPlates = nextPlates.some(function (plate) {
        return !!plate.selected;
      });
      return Object.assign({}, file, {
        selected: hasSelectedPlates,
        plates: nextPlates,
      });
    });
    this._render();
  }

  _getQueueDialogMetrics() {
    var files = Array.isArray(this._queueDialogFiles) ? this._queueDialogFiles : [];
    var totalFiles = files.length;
    var totalPlates = files.reduce(function (sum, file) {
      return sum + (Array.isArray(file.plates) ? file.plates.length : 0);
    }, 0);
    var selectedFiles = files.filter(function (file) {
      return !!file.selected;
    });
    var selectedPlates = selectedFiles.reduce(function (sum, file) {
      return sum + (Array.isArray(file.plates) ? file.plates.filter(function (plate) { return !!plate.selected; }).length : 0);
    }, 0);
    return {
      totalFiles: totalFiles,
      totalPlates: totalPlates,
      selectedFiles: selectedFiles.length,
      selectedPlates: selectedPlates,
    };
  }

  _buildQueueDialogQuickSelectionPayload() {
    if (!Array.isArray(this._queueDialogFiles) || !this._queueDialogFiles.length) {
      return [];
    }
    var primaryFile = this._queueDialogFiles[0];
    var primaryPlate = Array.isArray(primaryFile.plates) && primaryFile.plates.length > 0 ? primaryFile.plates[0] : null;
    return [{
      file_id: primaryFile.file_id,
      file_name: primaryFile.file_name,
      selected: true,
      plates: primaryPlate ? [{ plate_id: primaryPlate.plate_id, selected: true }] : [],
    }];
  }

  _buildQueueDialogPlanSelectionPayload() {
    return this._queueDialogFiles.map(function (file) {
      return {
        file_id: file.file_id,
        file_name: file.file_name,
        selected: !!file.selected,
        plates: Array.isArray(file.plates)
          ? file.plates.map(function (plate) {
              return { plate_id: plate.plate_id, selected: !!plate.selected };
            })
          : [],
      };
    });
  }

  _isQueueDialogIdeaMode() {
    if (this._queueDialogLoading) {
      return false;
    }
    if (String(this._queueDialogEntityType || "").toLowerCase() === "idea") {
      return true;
    }
    return !Array.isArray(this._queueDialogFiles) || this._queueDialogFiles.length === 0;
  }

  _queueDialogPrimarySummary() {
    if (this._queueDialogLoading) {
      return "Loading queue defaults...";
    }
    if (this._isQueueDialogIdeaMode()) {
      var ideaPrinter = this._config && this._config.queue_printer_id ? this._config.queue_printer_id : "p1";
      var ideaState = this._queueDialogMode === "quick"
        ? "up_next"
        : this._normalizeQueueDialogTargetState(this._queueDialogTargetState);
      return "Will queue idea "
        + String(this._queueDialogModelName || "Idea")
        + " on "
        + String(ideaPrinter)
        + " in state "
        + this._queueDialogTargetStateLabel(ideaState)
        + " (no files to select).";
    }
    if (!Array.isArray(this._queueDialogFiles) || !this._queueDialogFiles.length) {
      return "Loading queue defaults...";
    }
    var primaryFile = this._queueDialogFiles[0] || {};
    var primaryPlate = Array.isArray(primaryFile.plates) && primaryFile.plates.length > 0 ? primaryFile.plates[0] : null;
    return "Will queue "
      + String(primaryFile.file_name || "Primary file")
      + " · "
      + String(primaryPlate && primaryPlate.plate_name ? primaryPlate.plate_name : "Primary Plate")
      + " on "
      + String(this._config && this._config.queue_printer_id ? this._config.queue_printer_id : "p1")
      + " in state "
      + this._queueDialogTargetStateLabel(this._queueDialogTargetState)
      + ".";
  }

  _canSubmitQueueDialog() {
    if (this._queueDialogLoading || this._queueDialogSubmitting) {
      return false;
    }
    if (this._isQueueDialogIdeaMode()) {
      return !!this._queueDialogModelRef;
    }
    if (!Array.isArray(this._queueDialogFiles) || this._queueDialogFiles.length === 0) {
      return false;
    }
    if (this._queueDialogMode !== "plan") {
      return true;
    }
    return this._getQueueDialogMetrics().selectedPlates > 0;
  }

  async _submitQueueDialog() {
    if (!this._queueDialogModelRef || this._queueDialogLoading || this._queueDialogSubmitting) {
      return;
    }

    var ideaMode = this._isQueueDialogIdeaMode();

    if (!ideaMode && (!Array.isArray(this._queueDialogFiles) || this._queueDialogFiles.length === 0)) {
      this._queueDialogError = "No queueable files were found for this model.";
      this._render();
      return;
    }

    if (!this._canSubmitQueueDialog()) {
      this._queueDialogError = this._queueDialogMode === "plan"
        ? "Select at least one file plate before adding to queue."
        : "No queueable files were found for this model.";
      this._render();
      return;
    }

    var targetState = (ideaMode || this._queueDialogMode === "quick")
      ? "up_next"
      : this._normalizeQueueDialogTargetState(this._queueDialogTargetState);

    var payload;
    if (ideaMode) {
      // Mirror the queue-board idea path: minimal payload, no file selection.
      // Source kind reflects the underlying entity so the queue entry can still
      // link back to a file-less catalog model when appropriate.
      var ideaSourceKind = String(this._queueDialogEntityType || "").toLowerCase() === "idea"
        ? "idea"
        : "catalog_model";
      payload = {
        source_kind: ideaSourceKind,
        source_id: this._queueDialogModelRef,
        title: this._queueDialogModelName,
        state: targetState,
        queue_notes: String(this._queueDialogNotes || "").trim(),
      };
    } else {
      payload = {
        source_kind: "catalog_model",
        source_id: this._queueDialogModelRef,
        title: this._queueDialogModelName,
        queue_notes: String(this._queueDialogNotes || "").trim(),
        selection_mode: "selected_plates",
        selected_files: this._queueDialogMode === "quick"
          ? this._buildQueueDialogQuickSelectionPayload()
          : this._buildQueueDialogPlanSelectionPayload(),
      };

      // Preserve Up Next as the UX default while remaining compatible with
      // deployments whose add endpoint rejects explicit state="up_next".
      if (targetState !== "up_next") {
        payload.state = targetState;
      }

      if (this._queueDialogMode === "plan") {
        var metrics = this._getQueueDialogMetrics();
        if (metrics.selectedPlates <= 0) {
          this._queueDialogError = "Select at least one plate in Plan mode.";
          this._render();
          return;
        }
      }
    }

    this._queueDialogSubmitting = true;
    this._queueDialogError = "";
    this._render();

    try {
      await addUnifiedQueueEntry({
        queueApiBase: this._resolveModelSidecarUrl() + "/api/v1",
        printerId: this._config && this._config.queue_printer_id ? this._config.queue_printer_id : "p1",
        payload: payload,
      });
      this._closeQueueDialog();
      this._error = "";
      // Invalidate the unified queue index cache so the next load picks up the
      // freshly added entry (TTL-based skip would otherwise mask the new state
      // and leave the card's left-border queue ribbon unlit).
      this._unifiedQueueIndexLastFetchedAt = 0;
      await this._loadPage(this._currentPage(), false);
    } catch (error) {
      this._queueDialogSubmitting = false;
      this._queueDialogError = error && error.message ? String(error.message) : "Could not add to queue.";
      this._render();
    }
  }

  async _listUnifiedQueueEntriesForModel(modelRef) {
    // Omit source_kind so the lookup includes both catalog_model and idea
    // entries (an Idea added from the Model Catalog page records source_kind
    // "idea" but still points at the catalog model via source_id).
    var payload = await this._callServiceWithResponse("rest_command", "model_catalog_list_unified_queue_entries", {
      printer_id: this._config && this._config.queue_printer_id ? this._config.queue_printer_id : "p1",
      sort: "rank:asc",
      limit: 200,
      offset: 0,
    });
    var entries = Array.isArray(payload && payload.entries) ? payload.entries : [];
    return entries.filter(function (entry) {
      var kind = String((entry && entry.source_kind) || "").toLowerCase();
      if (kind !== "catalog_model" && kind !== "idea") {
        return false;
      }
      var sourceRef = String((entry && (entry.source_id || entry.source_ref)) || "").trim();
      return sourceRef === modelRef;
    });
  }

  async _applyUnifiedQueueAction(action, modelRef, options) {
    var actionOptions = options && typeof options === "object" ? options : {};
    var modelName = String(actionOptions.modelName || "Model").trim() || "Model";

    if (action === "queue-add") {
      var entries = await this._listUnifiedQueueEntriesForModel(modelRef);
      await this._openQueueDialog(modelRef, modelName, entries, { intent: "add", defaultState: "up_next" });
      return false;
    }

    return true;
  }

  _renderQueueDialog() {
    if (!this._queueDialogOpen) {
      return "";
    }

    var metrics = this._getQueueDialogMetrics();
    var canSubmit = this._canSubmitQueueDialog();
    var ideaMode = this._isQueueDialogIdeaMode();
    var existingNote = this._queueDialogExistingCount > 0
      ? '<div class="queue-dialog-existing-note">This model already has ' + this._escapeHtml(String(this._queueDialogExistingCount)) + ' queue entr' + (this._queueDialogExistingCount === 1 ? 'y' : 'ies') + '. Re-add is allowed.</div>'
      : "";
    var ideaNote = ideaMode
      ? '<div class="queue-dialog-note">This entry has no printable files. It will be added as an idea-style queue entry — set a target state and notes below.</div>'
      : "";
    var planBody = this._queueDialogLoading
      ? '<div class="queue-dialog-note">Loading model files and plates...</div>'
      : this._queueDialogFiles.length === 0
      ? ''
      : '<div class="queue-dialog-toolbar"><button class="toolbar-btn" type="button" data-action="queue-dialog-select-all">Select all</button><button class="toolbar-btn ghost" type="button" data-action="queue-dialog-clear-all">Deselect all</button></div>'
        + '<div class="queue-dialog-file-list">'
        + this._queueDialogFiles.map(function (file) {
            var plateCount = Array.isArray(file.plates) ? file.plates.length : 0;
            var selectedPlates = Array.isArray(file.plates) ? file.plates.filter(function (plate) { return !!plate.selected; }).length : 0;
            return '<section class="queue-dialog-file-block">'
              + '  <button class="queue-dialog-file-toggle' + (file.selected ? ' active' : '') + '" type="button" data-action="queue-dialog-toggle-file" data-file-id="' + this._escapeHtml(String(file.file_id || '')) + '">' + this._escapeHtml(String(file.file_name || 'Queue file')) + '<span>' + this._escapeHtml(String(selectedPlates) + '/' + String(plateCount) + ' plates') + '</span></button>'
              + '  <div class="queue-dialog-plates">'
              + (file.plates || []).map(function (plate) {
                  return '<button class="queue-dialog-plate-toggle' + (plate.selected ? ' active' : '') + '" type="button" data-action="queue-dialog-toggle-plate" data-file-id="' + this._escapeHtml(String(file.file_id || '')) + '" data-plate-id="' + this._escapeHtml(String(plate.plate_id || '')) + '">' + this._escapeHtml(String(plate.plate_name || 'Plate')) + '</button>';
                }.bind(this)).join('')
              + '  </div>'
              + '</section>';
          }.bind(this)).join('')
        + '</div>';

    return ''
      + '<div class="queue-dialog-backdrop" data-action="close-queue-dialog">'
      + '  <div class="queue-dialog" role="dialog" aria-modal="true" aria-label="Add to Queue">'
      + '    <div class="queue-dialog-header">'
      + '      <div><h3>Add to Queue</h3><div class="queue-dialog-subtitle">' + this._escapeHtml(this._queueDialogModelName) + '</div></div>'
      + '      <button class="modal-close-btn" type="button" data-action="close-queue-dialog" aria-label="Close">✕</button>'
      + '    </div>'
      + '    <div class="queue-dialog-tabs">'
      + (ideaMode
          ? ''
          : '      <button class="queue-dialog-tab' + (this._queueDialogMode === 'quick' ? ' active' : '') + '" type="button" data-action="queue-dialog-mode" data-mode="quick">Quick</button>'
            + '      <button class="queue-dialog-tab' + (this._queueDialogMode === 'plan' ? ' active' : '') + '" type="button" data-action="queue-dialog-mode" data-mode="plan">Plan</button>')
      + '    </div>'
      + '    <div class="queue-dialog-body">'
      + existingNote
      + ideaNote
      + (ideaMode
          ? '<div class="queue-dialog-summary">' + this._escapeHtml(this._queueDialogPrimarySummary()) + '</div>'
            + '<label class="queue-dialog-field"><span>Target state</span><select class="queue-dialog-target-state"><option value="backlog"' + (this._queueDialogTargetState === 'backlog' ? ' selected' : '') + '>Backlog</option><option value="up_next"' + (this._queueDialogTargetState === 'up_next' ? ' selected' : '') + '>Up Next</option><option value="preparing"' + (this._queueDialogTargetState === 'preparing' ? ' selected' : '') + '>Preparing</option><option value="ready"' + (this._queueDialogTargetState === 'ready' ? ' selected' : '') + '>Ready</option></select></label>'
            + '<label class="queue-dialog-field"><span>Notes</span><textarea class="queue-dialog-notes" data-queue-dialog-notes="true" rows="3" placeholder="Optional operator notes...">' + this._escapeHtml(this._queueDialogNotes) + '</textarea></label>'
          : (this._queueDialogMode === 'quick'
              ? '<div class="queue-dialog-summary">' + this._escapeHtml(this._queueDialogPrimarySummary()) + '</div>'
              : '<div class="queue-dialog-summary">Choose plates, target state, and notes before creating the queue entry.</div>'
                + '<label class="queue-dialog-field"><span>Target state</span><select class="queue-dialog-target-state"><option value="backlog"' + (this._queueDialogTargetState === 'backlog' ? ' selected' : '') + '>Backlog</option><option value="up_next"' + (this._queueDialogTargetState === 'up_next' ? ' selected' : '') + '>Up Next</option><option value="preparing"' + (this._queueDialogTargetState === 'preparing' ? ' selected' : '') + '>Preparing</option><option value="ready"' + (this._queueDialogTargetState === 'ready' ? ' selected' : '') + '>Ready</option></select></label>'
                + '<label class="queue-dialog-field"><span>Notes</span><textarea class="queue-dialog-notes" data-queue-dialog-notes="true" rows="3" placeholder="Optional operator notes...">' + this._escapeHtml(this._queueDialogNotes) + '</textarea></label>'
                + '<div class="queue-dialog-metrics">Selected ' + this._escapeHtml(String(metrics.selectedPlates)) + ' plates across ' + this._escapeHtml(String(metrics.selectedFiles)) + ' files.</div>'
                + planBody))
      + (this._queueDialogError ? '<div class="queue-dialog-error">' + this._escapeHtml(this._queueDialogError) + '</div>' : '')
      + '    </div>'
      + '    <div class="queue-dialog-footer">'
      + '      <button class="toolbar-btn ghost" type="button" data-action="close-queue-dialog">Cancel</button>'
        + '      <button class="toolbar-btn queue-dialog-submit" type="button" data-action="queue-dialog-submit"' + (canSubmit ? '' : ' disabled') + '>' + (this._queueDialogSubmitting ? 'Adding...' : 'Add to Queue') + '</button>'
      + '    </div>'
      + '  </div>'
      + '</div>';
  }

  _updateActionMenus() {
    if (!this.shadowRoot) {
      return;
    }
    var buttons = this.shadowRoot.querySelectorAll('.advanced-menu-shell .icon-action[data-action="toggle-actions"]');
    for (var i = 0; i < buttons.length; i++) {
      var button = buttons[i];
      var menuKey = String(button.getAttribute("data-menu-key") || button.getAttribute("data-model-ref") || "").trim();
      var open = !!this._activeActionMenu && this._activeActionMenu === menuKey;
      button.setAttribute("aria-expanded", open ? "true" : "false");
      var shell = button.closest(".advanced-menu-shell");
      if (!shell) {
        continue;
      }
      var menu = shell.querySelector(".advanced-menu");
      if (!menu) {
        continue;
      }
      menu.classList.toggle("is-open", open);
      menu.setAttribute("aria-hidden", open ? "false" : "true");
    }
  }

  _collectionMenuKey(collectionId) {
    var normalizedId = String(collectionId || "").trim().toLowerCase();
    return normalizedId ? ("collection:" + normalizedId) : "";
  }

  _collectionResultsViewClass() {
    var viewMode = this._normalizedViewMode(this._viewMode);
    if (viewMode === "list") {
      return "list";
    }
    if (viewMode === "media") {
      return "media";
    }
    return "collections";
  }

  _collectionBreadcrumbUpTarget(currentNode, currentCollectionKey) {
    if (currentCollectionKey === "__unassigned__") {
      return { navKey: "all-models", label: "All Collections" };
    }
    var parentId = currentNode ? String(currentNode.parent_collection_id || "").trim().toLowerCase() : "";
    if (parentId) {
      return { navKey: "collection:" + parentId, label: "Up One Level" };
    }
    if (currentNode) {
      return { navKey: "all-models", label: "All Collections" };
    }
    return null;
  }

  _buildSyntheticUnassignedCollectionNode(browse) {
    var tree = browse && browse.tree && typeof browse.tree === "object" ? browse.tree : {};
    var unassignedCount = Math.max(0, Number(tree.unassigned_model_count || 0) || 0);
    if (unassignedCount <= 0) {
      return null;
    }
    var unassignedActivity = tree.unassigned_recent_print_activity && typeof tree.unassigned_recent_print_activity === "object"
      ? tree.unassigned_recent_print_activity
      : { printed_model_count: 0, last_printed_at: "" };
    return {
      collection_id: "__unassigned__",
      label: "No Collection",
      name: "No Collection",
      path: "System bucket",
      model_count_direct: unassignedCount,
      model_count_total: unassignedCount,
      child_collection_count: 0,
      preview_model_count: Math.max(0, Number(tree.unassigned_preview_model_count || 0) || 0),
      recent_print_activity: {
        printed_model_count: Math.max(0, Number(unassignedActivity.printed_model_count || 0) || 0),
        last_printed_at: String(unassignedActivity.last_printed_at || "").trim(),
      },
      cover_images: Array.isArray(tree.unassigned_cover_images) ? tree.unassigned_cover_images.slice(0, 6) : [],
      is_system_bucket: true,
    };
  }

  _renderCollectionNodeCard(node) {
    var collectionId = String(node.collection_id || "").trim().toLowerCase();
    var label = String(node.label || node.name || node.path || "Collection").trim() || "Collection";
    var path = String(node.path || "").trim();
    var directCount = Math.max(0, Number(node.model_count_direct || 0) || 0);
    var totalCount = Math.max(0, Number(node.model_count_total || 0) || 0);
    var childCount = Math.max(0, Number(node.child_collection_count || 0) || 0);
    var previewCount = Math.max(0, Number(node.preview_model_count || 0) || 0);
    var activity = node.recent_print_activity && typeof node.recent_print_activity === 'object' ? node.recent_print_activity : {};
    var recentPrintCount = Math.max(0, Number(activity.printed_model_count || 0) || 0);
    var lastPrintedAt = String(activity.last_printed_at || '').trim();
    var coverMosaicHtml = this._renderCollectionCoverMosaic(node);
    var actionMenuKey = this._collectionMenuKey(collectionId);
    var actionMenuOpen = !!this._activeActionMenu && this._activeActionMenu === actionMenuKey;
    var deleteDisabled = totalCount > 0 || childCount > 0;
    var isSystemBucket = !!node.is_system_bucket;
    var viewMode = this._normalizedViewMode(this._viewMode);
    var recentSummary = String(previewCount) + (previewCount === 1 ? ' previewable model' : ' previewable models') + ' · ' + (lastPrintedAt ? ('Last printed ' + this._formatCollectionDate(lastPrintedAt)) : 'No recent print activity');

    if (viewMode === 'list') {
      return ''
        + '<article class="collection-card collection-card-view-list' + (isSystemBucket ? ' system-bucket' : '') + '">'
        + '  <div class="collection-list-thumb">' + coverMosaicHtml + '</div>'
        + '  <div class="collection-list-main">'
        + '    <div class="collection-list-title-row"><span class="collection-card-type">' + this._escapeHtml(isSystemBucket ? 'System Bucket' : 'Collection') + '</span><div class="collection-name">' + this._escapeHtml(label) + '</div></div>'
        + '    <div class="collection-meta">' + this._escapeHtml(path && path !== label ? path : (isSystemBucket ? 'Models without a collection assignment' : 'Collection path')) + '</div>'
        + '    <div class="collection-meta collection-meta-row">' + this._escapeHtml(recentSummary) + '</div>'
        + '  </div>'
        + '  <div class="collection-list-stats">'
        + '    <div class="collection-stat"><div class="collection-stat-label">Total</div><div class="collection-stat-value">' + this._escapeHtml(String(totalCount)) + '</div></div>'
        + '    <div class="collection-stat"><div class="collection-stat-label">Direct</div><div class="collection-stat-value">' + this._escapeHtml(String(directCount)) + '</div></div>'
        + '    <div class="collection-stat"><div class="collection-stat-label">Sub-collections</div><div class="collection-stat-value">' + this._escapeHtml(String(childCount)) + '</div></div>'
        + '    <div class="collection-stat"><div class="collection-stat-label">Recent prints</div><div class="collection-stat-value">' + this._escapeHtml(String(recentPrintCount)) + '</div></div>'
        + '  </div>'
        + '  <div class="collection-list-actions">'
        + '    <button class="toolbar-btn collection-open" type="button" data-action="select-left-nav-item" data-nav-key="collection:' + this._escapeHtml(collectionId) + '">Open</button>'
        + (isSystemBucket ? '' : '    <div class="advanced-menu-shell">'
            + '      <button class="icon-action advanced" type="button" data-action="toggle-actions" data-menu-key="' + this._escapeHtml(actionMenuKey) + '" aria-label="Open collection actions" aria-expanded="' + (actionMenuOpen ? 'true' : 'false') + '"><ha-icon icon="mdi:dots-horizontal"></ha-icon></button>'
            + '      <div class="advanced-menu' + (actionMenuOpen ? ' is-open' : '') + '" aria-hidden="' + (actionMenuOpen ? 'false' : 'true') + '">'
            + '        <button class="advanced-action primary" type="button" data-action="select-left-nav-item" data-nav-key="collection:' + this._escapeHtml(collectionId) + '"><ha-icon icon="mdi:folder-search-outline"></ha-icon><span>Open collection</span></button>'
            + '        <button class="advanced-action" type="button" data-action="collection-rename" data-collection-id="' + this._escapeHtml(collectionId) + '" data-collection-label="' + this._escapeHtml(label) + '" data-collection-path="' + this._escapeHtml(path || label) + '"><ha-icon icon="mdi:pencil-outline"></ha-icon><span>Rename</span></button>'
            + '        <button class="advanced-action" type="button" data-action="collection-move" data-collection-id="' + this._escapeHtml(collectionId) + '" data-collection-label="' + this._escapeHtml(label) + '" data-collection-path="' + this._escapeHtml(path || label) + '"><ha-icon icon="mdi:folder-move-outline"></ha-icon><span>Move</span></button>'
            + '        <button class="advanced-action danger" type="button" data-action="collection-delete" data-collection-id="' + this._escapeHtml(collectionId) + '" data-collection-label="' + this._escapeHtml(label) + '" data-collection-path="' + this._escapeHtml(path || label) + '"' + (deleteDisabled ? ' disabled title="Collection must be empty before deletion"' : '') + '><ha-icon icon="mdi:trash-can-outline"></ha-icon><span>' + (deleteDisabled ? 'Delete (empty only)' : 'Delete') + '</span></button>'
            + '      </div>'
            + '    </div>')
        + '  </div>'
        + '</article>';
    }

    return ''
      + '<article class="collection-card collection-card-view-' + this._escapeHtml(viewMode === 'media' ? 'media' : 'compact') + (isSystemBucket ? ' system-bucket' : '') + '">'
      + '  <div class="collection-card-top">'
      + '    <div class="collection-card-kicker"><span class="collection-card-type">' + this._escapeHtml(isSystemBucket ? 'System Bucket' : 'Collection') + '</span>'
      + (isSystemBucket ? '' : (childCount > 0 ? '<span class="collection-card-kicker-meta">Nested</span>' : '<span class="collection-card-kicker-meta">Leaf</span>'))
      + '    </div>'
      + (isSystemBucket ? '' : '    <div class="advanced-menu-shell">'
          + '      <button class="icon-action advanced" type="button" data-action="toggle-actions" data-menu-key="' + this._escapeHtml(actionMenuKey) + '" aria-label="Open collection actions" aria-expanded="' + (actionMenuOpen ? 'true' : 'false') + '"><ha-icon icon="mdi:dots-horizontal"></ha-icon></button>'
          + '      <div class="advanced-menu' + (actionMenuOpen ? ' is-open' : '') + '" aria-hidden="' + (actionMenuOpen ? 'false' : 'true') + '">'
          + '        <button class="advanced-action primary" type="button" data-action="select-left-nav-item" data-nav-key="collection:' + this._escapeHtml(collectionId) + '"><ha-icon icon="mdi:folder-search-outline"></ha-icon><span>Open collection</span></button>'
          + '        <button class="advanced-action" type="button" data-action="collection-rename" data-collection-id="' + this._escapeHtml(collectionId) + '" data-collection-label="' + this._escapeHtml(label) + '" data-collection-path="' + this._escapeHtml(path || label) + '"><ha-icon icon="mdi:pencil-outline"></ha-icon><span>Rename</span></button>'
          + '        <button class="advanced-action" type="button" data-action="collection-move" data-collection-id="' + this._escapeHtml(collectionId) + '" data-collection-label="' + this._escapeHtml(label) + '" data-collection-path="' + this._escapeHtml(path || label) + '"><ha-icon icon="mdi:folder-move-outline"></ha-icon><span>Move</span></button>'
          + '        <button class="advanced-action danger" type="button" data-action="collection-delete" data-collection-id="' + this._escapeHtml(collectionId) + '" data-collection-label="' + this._escapeHtml(label) + '" data-collection-path="' + this._escapeHtml(path || label) + '"' + (deleteDisabled ? ' disabled title="Collection must be empty before deletion"' : '') + '><ha-icon icon="mdi:trash-can-outline"></ha-icon><span>' + (deleteDisabled ? 'Delete (empty only)' : 'Delete') + '</span></button>'
          + '      </div>'
          + '    </div>')
      + '  </div>'
      + coverMosaicHtml
      + (previewCount <= 0 ? '  <div class="collection-empty-preview">' + this._escapeHtml(isSystemBucket ? 'Open to browse unassigned models' : 'No preview available yet') + '</div>' : '')
      + '  <div class="collection-name">' + this._escapeHtml(label) + '</div>'
      + (path && path !== label ? '  <div class="collection-meta">' + this._escapeHtml(path) + '</div>' : '')
      + '  <div class="collection-stats">'
      + '    <div class="collection-stat"><div class="collection-stat-label">Total</div><div class="collection-stat-value">' + this._escapeHtml(String(totalCount)) + '</div></div>'
      + '    <div class="collection-stat"><div class="collection-stat-label">Direct</div><div class="collection-stat-value">' + this._escapeHtml(String(directCount)) + '</div></div>'
      + '    <div class="collection-stat"><div class="collection-stat-label">Sub-collections</div><div class="collection-stat-value">' + this._escapeHtml(String(childCount)) + '</div></div>'
      + '    <div class="collection-stat"><div class="collection-stat-label">Recent prints</div><div class="collection-stat-value">' + this._escapeHtml(String(recentPrintCount)) + '</div></div>'
      + '  </div>'
      + '  <div class="collection-meta collection-meta-row">' + this._escapeHtml(recentSummary) + '</div>'
      + '  <button class="toolbar-btn collection-open" type="button" data-action="select-left-nav-item" data-nav-key="collection:' + this._escapeHtml(collectionId) + '">Open collection</button>'
      + '</article>';
  }

  _normalizeCollectionId(value) {
    return String(value || "").trim().toLowerCase();
  }

  _clearCollectionActionFeedback(shouldRender) {
    if (this._collectionActionFeedbackTimer) {
      window.clearTimeout(this._collectionActionFeedbackTimer);
      this._collectionActionFeedbackTimer = null;
    }
    this._collectionActionFeedback = null;
    if (shouldRender) {
      this._render();
    }
  }

  _setCollectionActionFeedback(message, kind) {
    var text = String(message || "").trim();
    if (!text) {
      this._clearCollectionActionFeedback(false);
      return;
    }
    this._clearCollectionActionFeedback(false);
    this._collectionActionFeedback = {
      kind: kind === "error" ? "error" : "success",
      message: text,
    };
    this._collectionActionFeedbackTimer = window.setTimeout(function () {
      this._collectionActionFeedbackTimer = null;
      if (this._collectionActionFeedback && this._collectionActionFeedback.message === text) {
        this._collectionActionFeedback = null;
        this._render();
      }
    }.bind(this), 4200);
  }

  _collectionDialogTitle(mode) {
    if (mode === "rename") return "Rename Collection";
    if (mode === "move") return "Move Collection";
    if (mode === "delete") return "Delete Collection";
    return "Collection Action";
  }

  _collectionDialogSubmitLabel(mode) {
    if (mode === "rename") return "Save Name";
    if (mode === "move") return "Move Collection";
    if (mode === "delete") return "Delete Collection";
    return "Save";
  }

  _collectionRowsById(rows) {
    var source = Array.isArray(rows) ? rows : [];
    var lookup = {};
    for (var index = 0; index < source.length; index++) {
      var row = source[index] || {};
      var id = this._normalizeCollectionId(row.collection_id);
      if (id) {
        lookup[id] = row;
      }
    }
    return lookup;
  }

  _collectionDescendantIds(collectionId, rows) {
    var targetId = this._normalizeCollectionId(collectionId);
    if (!targetId) {
      return {};
    }
    var childrenByParent = {};
    var source = Array.isArray(rows) ? rows : [];
    for (var index = 0; index < source.length; index++) {
      var row = source[index] || {};
      var parentId = this._normalizeCollectionId(row.parent_collection_id);
      var rowId = this._normalizeCollectionId(row.collection_id);
      if (!parentId || !rowId) {
        continue;
      }
      if (!childrenByParent[parentId]) {
        childrenByParent[parentId] = [];
      }
      childrenByParent[parentId].push(rowId);
    }
    var seen = {};
    var queue = (childrenByParent[targetId] || []).slice(0);
    while (queue.length) {
      var nextId = queue.shift();
      if (!nextId || seen[nextId]) {
        continue;
      }
      seen[nextId] = true;
      var children = childrenByParent[nextId] || [];
      for (var childIndex = 0; childIndex < children.length; childIndex++) {
        queue.push(children[childIndex]);
      }
    }
    return seen;
  }

  _buildCollectionMoveOptions(collectionId, rows) {
    var targetId = this._normalizeCollectionId(collectionId);
    var descendants = this._collectionDescendantIds(targetId, rows);
    var source = Array.isArray(rows) ? rows.slice(0) : [];
    source.sort(function (left, right) {
      var leftLabel = String(left.path || left.name || left.collection_id || "").trim().toLowerCase();
      var rightLabel = String(right.path || right.name || right.collection_id || "").trim().toLowerCase();
      return leftLabel.localeCompare(rightLabel);
    });
    var options = [{ value: "", label: "Root (top level)" }];
    for (var index = 0; index < source.length; index++) {
      var row = source[index] || {};
      var rowId = this._normalizeCollectionId(row.collection_id);
      if (!rowId || rowId === targetId || descendants[rowId]) {
        continue;
      }
      options.push({
        value: rowId,
        label: String(row.path || row.name || row.collection_id || rowId).trim() || rowId,
      });
    }
    return options;
  }

  _openCollectionActionDialog(mode, config) {
    var dialogMode = String(mode || "").trim().toLowerCase();
    var details = config && typeof config === "object" ? config : {};
    this._activeActionMenu = "";
    this._collectionActionDialog = {
      open: true,
      mode: dialogMode,
      collectionId: this._normalizeCollectionId(details.collectionId),
      label: String(details.label || "Collection").trim() || "Collection",
      path: String(details.path || details.label || "Collection").trim() || "Collection",
      name: String(details.name || details.label || "").trim(),
      selectedParentId: this._normalizeCollectionId(details.selectedParentId),
      options: Array.isArray(details.options) ? details.options : [],
      error: "",
      submitting: false,
    };
    this._focusCollectionActionPrimaryAfterRender = true;
    this._render();
  }

  _closeCollectionActionDialog() {
    if (this._collectionActionDialog && this._collectionActionDialog.submitting) {
      return;
    }
    this._collectionActionDialog = {
      open: false,
      mode: "",
      collectionId: "",
      label: "",
      path: "",
      name: "",
      selectedParentId: "",
      options: [],
      error: "",
      submitting: false,
    };
    this._render();
  }

  async _openCollectionMoveDialog(config) {
    var details = config && typeof config === "object" ? config : {};
    var collectionsPayload = await this._collectionApiRequest('/api/collections', { method: 'GET' });
    var rows = collectionsPayload && Array.isArray(collectionsPayload.items) ? collectionsPayload.items : [];
    var byId = this._collectionRowsById(rows);
    var currentRow = byId[this._normalizeCollectionId(details.collectionId)] || {};
    this._openCollectionActionDialog('move', {
      collectionId: details.collectionId,
      label: details.label || currentRow.name || currentRow.collection_id || 'Collection',
      path: details.path || currentRow.path || currentRow.name || details.label || 'Collection',
      selectedParentId: currentRow.parent_collection_id,
      options: this._buildCollectionMoveOptions(details.collectionId, rows),
    });
  }

  async _submitCollectionActionDialog() {
    var dialog = this._collectionActionDialog && typeof this._collectionActionDialog === 'object' ? this._collectionActionDialog : null;
    if (!dialog || !dialog.open || dialog.submitting) {
      return;
    }
    var mode = String(dialog.mode || '').trim().toLowerCase();
    var collectionId = this._normalizeCollectionId(dialog.collectionId);
    if (!collectionId) {
      return;
    }
    if (mode === 'rename') {
      var proposedName = String(dialog.name || '').trim();
      if (!proposedName) {
        this._collectionActionDialog.error = 'Collection name is required.';
        this._render();
        return;
      }
    }
    dialog.submitting = true;
    dialog.error = '';
    this._render();
    try {
      var feedbackMessage = '';
      if (mode === 'rename') {
        var nextName = String(dialog.name || '').trim();
        await this._renameCollection(collectionId, nextName);
        feedbackMessage = 'Renamed collection to "' + nextName + '".';
      } else if (mode === 'move') {
        var nextParentId = this._normalizeCollectionId(dialog.selectedParentId) || null;
        await this._moveCollection(collectionId, nextParentId);
        var destinationLabel = 'Root';
        for (var optionIndex = 0; optionIndex < dialog.options.length; optionIndex++) {
          var option = dialog.options[optionIndex] || {};
          if (String(option.value || '') === String(nextParentId || '')) {
            destinationLabel = String(option.label || 'Root');
            break;
          }
        }
        feedbackMessage = 'Moved "' + dialog.label + '" to ' + destinationLabel + '.';
      } else if (mode === 'delete') {
        await this._deleteCollection(collectionId);
        feedbackMessage = 'Deleted collection "' + dialog.label + '".';
      }

      var deletedSelectedCollection = mode === 'delete' && this._selectedCollectionKey() === collectionId;
      this._collectionActionDialog.open = false;
      this._collectionActionDialog.submitting = false;
      this._error = '';
      this._activeActionMenu = '';
      if (deletedSelectedCollection) {
        this._applyLeftNavSelection('all-models', { closeDrawer: false, requestLoad: false, render: false });
      }
      await this._fetchGlobalFacets();
      this._requestLoad(deletedSelectedCollection ? 1 : this._currentPage(), true);
      this._setCollectionActionFeedback(feedbackMessage, 'success');
      this._render();
    } catch (error) {
      dialog.submitting = false;
      dialog.error = error && error.message ? String(error.message) : 'Collection update failed.';
      this._setCollectionActionFeedback(dialog.error, 'error');
      this._render();
    }
  }

  _collectionApiBaseUrl() {
    return String(this._resolveModelSidecarUrl() || "").trim().replace(/\/$/, "");
  }

  async _collectionApiRequest(path, options) {
    var base = this._collectionApiBaseUrl();
    if (!base) {
      throw new Error("Model Catalog sidecar URL not configured");
    }
    var requestOptions = options && typeof options === "object" ? Object.assign({}, options) : {};
    requestOptions.headers = Object.assign({}, requestOptions.headers || {}, await this._authHeaders(false));
    requestOptions.credentials = "omit";
    var response = await fetch(base + path, requestOptions);
    if (response.status === 401) {
      requestOptions.headers = Object.assign({}, requestOptions.headers || {}, await this._authHeaders(true));
      response = await fetch(base + path, requestOptions);
    }
    var payload = {};
    try {
      payload = await response.json();
    } catch (_error) {
      payload = {};
    }
    if (!response.ok || (payload && payload.success === false)) {
      throw new Error(payload && payload.error ? String(payload.error) : ('Collection request failed (HTTP ' + String(response.status) + ')'));
    }
    return payload && typeof payload === 'object' ? payload : {};
  }

  async _renameCollection(collectionId, nextName) {
    await this._collectionApiRequest('/api/collections/' + encodeURIComponent(String(collectionId || '').trim()), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: nextName }),
    });
  }

  async _moveCollection(collectionId, parentCollectionId) {
    await this._collectionApiRequest('/api/collections/' + encodeURIComponent(String(collectionId || '').trim()), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parent_collection_id: parentCollectionId }),
    });
  }

  async _deleteCollection(collectionId) {
    await this._collectionApiRequest('/api/collections/' + encodeURIComponent(String(collectionId || '').trim()), {
      method: 'DELETE',
    });
  }

  _setModelFavoriteState(modelRef, isFavorite) {
    var targetRef = String(modelRef || "").trim();
    if (!targetRef) {
      return;
    }
    for (var i = 0; i < this._results.length; i++) {
      var model = this._results[i];
      if (this._modelRef(model) !== targetRef) {
        continue;
      }
      model.model_favorite = !!isFavorite;
      if (!model.custom_fields || typeof model.custom_fields !== "object") {
        model.custom_fields = {};
      }
      model.custom_fields.model_favorite = !!isFavorite;
      if (!model.structured_metadata || typeof model.structured_metadata !== "object") {
        model.structured_metadata = {};
      }
      if (!model.structured_metadata.catalog_signals || typeof model.structured_metadata.catalog_signals !== "object") {
        model.structured_metadata.catalog_signals = {};
      }
      model.structured_metadata.catalog_signals.model_favorite = !!isFavorite;
      break;
    }
  }

  _isModelFavorite(model) {
    var structured = model && model.structured_metadata && typeof model.structured_metadata === "object" ? model.structured_metadata : {};
    var catalogSignals = structured && structured.catalog_signals && typeof structured.catalog_signals === "object" ? structured.catalog_signals : {};
    var fields = model && model.custom_fields && typeof model.custom_fields === "object" ? model.custom_fields : {};
    var favorite = this._coerceBoolish(model && model.model_favorite);
    if (favorite === null) {
      favorite = this._coerceBoolish(catalogSignals.model_favorite);
    }
    if (favorite === null) {
      favorite = this._coerceBoolish(fields.model_favorite);
    }
    return !!favorite;
  }

  async _bulkSetFavorites(isFavorite) {
    var selectedRefs = this.getSelectedModelRefs();
    if (!selectedRefs.length || this._loading) {
      return;
    }

    var failedRefs = [];
    this._error = "";

    for (var i = 0; i < selectedRefs.length; i++) {
      this._setModelFavoriteState(selectedRefs[i], !!isFavorite);
    }
    this._render();

    for (var j = 0; j < selectedRefs.length; j++) {
      var modelRef = selectedRefs[j];
      try {
        await this._callServiceWithResponse("rest_command", "model_catalog_toggle_model_favorite", {
          model_ref: modelRef,
          model_favorite: !!isFavorite,
        });
      } catch (_error) {
        failedRefs.push(modelRef);
      }
    }

    for (var k = 0; k < failedRefs.length; k++) {
      this._setModelFavoriteState(failedRefs[k], !isFavorite);
    }
    if (failedRefs.length) {
      this._error = "Updated favorites with partial failure (" + String(failedRefs.length) + " failed).";
    }

    this._requestLoad(this._currentPage(), true);
    this._render();
  }

  async _bulkSetVisibility(visibility) {
    var selectedRefs = this.getSelectedModelRefs();
    if (!selectedRefs.length || this._loading) {
      return;
    }

    var sidecarUrl = String(this._resolveModelSidecarUrl() || "").trim().replace(/\/$/, "");
    if (!sidecarUrl) {
      this._error = "Model sidecar URL not configured.";
      this._render();
      return;
    }

    var failedRefs = [];
    this._error = "";

    for (var i = 0; i < selectedRefs.length; i++) {
      var modelRef = selectedRefs[i];
      try {
        var resp = await fetch(sidecarUrl + "/api/models/" + encodeURIComponent(modelRef), {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            enrichment: {
              structured_metadata: {
                catalog_signals: {
                  catalog_visibility: visibility,
                },
              },
            },
          }),
        });
        if (!resp.ok) {
          failedRefs.push(modelRef);
        }
      } catch (_error) {
        failedRefs.push(modelRef);
      }
    }

    if (failedRefs.length) {
      this._error = "Set visibility with partial failure (" + String(failedRefs.length) + " of " + String(selectedRefs.length) + " failed).";
    }

    this._requestLoad(this._currentPage(), true);
    this._render();
  }

  async _bulkSetSource(sourceId) {
    var selectedRefs = this.getSelectedModelRefs();
    if (!selectedRefs.length || this._loading) {
      return;
    }

    var customLabel = "";
    if (sourceId === "other") {
      customLabel = (window.prompt("Enter custom source name for selected models:") || "").trim();
      if (!customLabel) {
        return;
      }
    }

    var sidecarUrl = String(this._resolveModelSidecarUrl() || "").trim().replace(/\/$/, "");
    if (!sidecarUrl) {
      this._error = "Model sidecar URL not configured.";
      this._render();
      return;
    }

    var failedRefs = [];
    this._error = "";

    for (var i = 0; i < selectedRefs.length; i++) {
      var modelRef = selectedRefs[i];
      try {
        var resp = await fetch(sidecarUrl + "/api/models/" + encodeURIComponent(modelRef) + "/fields/publication_source", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ value: sourceId }),
        });
        if (!resp.ok) {
          failedRefs.push(modelRef);
          continue;
        }
        if (customLabel) {
          var labelResp = await fetch(sidecarUrl + "/api/models/" + encodeURIComponent(modelRef) + "/fields/source_platform_label", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ value: customLabel }),
          });
          if (!labelResp.ok) {
            failedRefs.push(modelRef);
          }
        }
      } catch (_error) {
        failedRefs.push(modelRef);
      }
    }

    if (failedRefs.length) {
      this._error = "Set source with partial failure (" + String(failedRefs.length) + " of " + String(selectedRefs.length) + " failed).";
    }

    this._requestLoad(this._currentPage(), true);
    this._render();
  }

  async _deleteModel(modelRef, modelName) {
    if (!this._hass || !modelRef) {
      return;
    }

    // Find the model in results to get local_model_id and linked archive count
    var model = null;
    for (var i = 0; i < this._results.length; i++) {
      if (this._modelRef(this._results[i]) === modelRef) {
        model = this._results[i];
        break;
      }
    }

    if (!model || !model.local_model_id) {
      this._error = "Could not identify local model for deletion.";
      this._render();
      return;
    }

    var localModelId = String(model.local_model_id).trim();
    var linkedCount = Number(model.linked_archive_count || 0);

    // Build warning message about what will be deleted
    var warningLines = [
      "Delete " + modelName + " from the Model Catalog?",
      "",
      "This will delete:",
      "• Model metadata and database entries",
      "• All stored model files and assets",
    ];

    if (linkedCount > 0) {
      warningLines.push(
        "",
        "This model has " + String(linkedCount) + " linked print archive" + (linkedCount === 1 ? "" : "s") + ". The archives will NOT be deleted, but the model reference will be removed."
      );
    }

    warningLines.push("", "This action cannot be undone.");

    var confirmMsg = warningLines.join("\n");
    if (!window.confirm(confirmMsg)) {
      return;
    }

    // Proceed with deletion
    await this._executeModelDeletion(localModelId, modelRef);
  }

  async _executeModelDeletion(localModelId, modelRef) {
    if (!this._hass || !localModelId) {
      return;
    }

    try {
      this._loading = true;
      this._error = "";
      this._render();

      var sidecarUrl = this._resolveModelSidecarUrl();
      if (!sidecarUrl) {
        throw new Error("Model Catalog sidecar URL not configured");
      }

      var auth = this._hass && this._hass.auth ? this._hass.auth : null;
      if (!auth) {
        throw new Error("Not authenticated with Home Assistant");
      }

      var deleteUrl = sidecarUrl + "/api/local/models/" + encodeURIComponent(localModelId) + "?hard_delete=false";
      var response = await fetch(deleteUrl, {
        method: "DELETE",
        headers: {
          "Authorization": "Bearer " + auth.accessToken,
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        var errorData = null;
        try {
          errorData = await response.json();
        } catch (_) {
          errorData = { error: "Unknown error", status: response.status };
        }
        var errorMsg = errorData && errorData.error ? String(errorData.error) : "HTTP " + String(response.status);
        throw new Error("Delete failed: " + errorMsg);
      }

      var result = await response.json();
      if (!result.success) {
        throw new Error(result.error || "Delete operation failed");
      }

      // Remove the model from the results list immediately for snappy UI
      var indexToRemove = -1;
      for (var i = 0; i < this._results.length; i++) {
        if (this._modelRef(this._results[i]) === modelRef) {
          indexToRemove = i;
          break;
        }
      }
      if (indexToRemove >= 0) {
        this._results.splice(indexToRemove, 1);
      }

      // Update pagination total
      this._pagination.total = Math.max(0, Number(this._pagination.total || 0) - 1);
      this._pagination.total_pages = Math.max(1, Math.ceil(this._pagination.total / (this._pagination.per_page || 12)));

      this._loading = false;
      this._activeActionMenu = "";
      this._error = "";
      this._render();

      // Show success notification
      try {
        await this._hass.callService("persistent_notification", "create", {
          title: "Model Deleted",
          message: "Model successfully deleted from the catalog.",
          notification_id: "model_catalog_delete_success",
        });
      } catch (_notifError) {
        console.warn("Could not show success notification", _notifError);
      }
    } catch (error) {
      this._loading = false;
      this._error = error && error.message ? String(error.message) : "Failed to delete model";
      this._render();
      console.error("Model deletion error:", error);

      // Show error notification
      try {
        await this._hass.callService("persistent_notification", "create", {
          title: "Model Deletion Failed",
          message: this._error,
          notification_id: "model_catalog_delete_error",
        });
      } catch (_notifError) {
        console.warn("Could not show error notification", _notifError);
      }
    }
  }

  _resolveModelSidecarUrl() {
    if (this._config && this._config.model_entity && this._hass && this._hass.states) {
      var configuredEntity = this._hass.states[this._config.model_entity];
      if (configuredEntity && configuredEntity.state) {
        return String(configuredEntity.state).trim();
      }
    }

    if (this._hass && this._hass.states) {
      var baseUrlEntity = this._hass.states["input_text.model_catalog_sidecar_base_url"];
      if (baseUrlEntity && baseUrlEntity.state) {
        return String(baseUrlEntity.state).trim();
      }
    }

    return String(this._config && this._config.model_sidecar_url || "").trim();
  }

  _handleWheel(event) {
    // Preserve page scrolling behavior; media navigation is button-only.
    return;
  }

  _currentPage() {
    return Math.max(1, Number(this._pagination.page || 1));
  }

  _pageCount() {
    return Math.max(1, Number(this._pagination.total_pages || 0));
  }

  _pageStatusText() {
    return String(this._currentPage()) + " / " + String(this._pageCount());
  }

  _renderPageStatusWithCount() {
    var total = Math.max(0, Number(this._pagination.total || 0));
    var noun = total === 1 ? "item" : "items";
    return ''
      + '<span class="page-value">' + this._escapeHtml(this._pageStatusText()) + '</span>'
      + '<span class="page-dot">·</span>'
      + '<span class="page-total">' + this._escapeHtml(String(total) + " " + noun) + '</span>';
  }

  _formatTagList(values) {
    if (!Array.isArray(values) || !values.length) {
      return "No tags";
    }
    return values.slice(0, 4).join(" · ");
  }

  _modelRef(model) {
    return String((model && (model.public_id || model.model_id || model.model_url)) || "").trim();
  }

  _currentModelMediaIndex(modelRef, imageCount) {
    var key = String(modelRef || "").trim();
    var count = Math.max(0, Number(imageCount || 0));
    if (!key || count <= 0) {
      return 0;
    }
    var current = Number(this._mediaGalleryIndices[key] || 0);
    if (!Number.isFinite(current) || current < 0) {
      current = 0;
    }
    if (current >= count) {
      current = count - 1;
    }
    this._mediaGalleryIndices[key] = current;
    return current;
  }

  _setModelMediaIndex(modelRef, nextIndex, imageCount) {
    var key = String(modelRef || "").trim();
    var count = Math.max(0, Number(imageCount || 0));
    if (!key || count <= 0) {
      return;
    }
    var normalized = Number(nextIndex || 0);
    if (!Number.isFinite(normalized)) {
      normalized = 0;
    }
    while (normalized < 0) {
      normalized += count;
    }
    this._mediaGalleryIndices[key] = normalized % count;
    if (this._updateModelMediaPreview(key)) {
      return;
    }
    this._render();
  }

  _updateModelMediaPreview(modelRef) {
    if (!this.shadowRoot || this._viewMode !== "media") {
      return false;
    }
    var key = String(modelRef || "").trim();
    if (!key) {
      return false;
    }
    var model = null;
    for (var i = 0; i < this._results.length; i++) {
      if (this._modelRef(this._results[i]) === key) {
        model = this._results[i];
        break;
      }
    }
    if (!model) {
      return false;
    }

    var mediaUrls = this._showMedia ? this._modelMediaUrls(model) : [];
    var mediaCount = mediaUrls.length;
    if (mediaCount <= 0) {
      return false;
    }
    var mediaIndex = this._currentModelMediaIndex(key, mediaCount);
    var mediaUrl = mediaUrls[mediaIndex];
    var card = null;
    var cards = this.shadowRoot.querySelectorAll('.model-card.view-media[data-model-ref]');
    for (var c = 0; c < cards.length; c++) {
      if (String(cards[c].getAttribute("data-model-ref") || "").trim() === key) {
        card = cards[c];
        break;
      }
    }
    if (!card || !mediaUrl) {
      return false;
    }

    var preview = card.querySelector('.media-preview.media-surface[data-model-ref]');
    if (preview) {
      var img = preview.querySelector("img");
      if (!img) {
        preview.innerHTML = '<img alt="Model preview" loading="lazy">';
        img = preview.querySelector("img");
      }
      if (img) {
        img.alt = String(model.name || "Model") + " preview";
        var nextSrc = String(mediaUrl);
        var preload = new Image();
        preload.decoding = "async";
        preload.onload = function () {
          img.removeAttribute("data-thumbnail-lazy-url");
          img.src = nextSrc;
        };
        // Keep current image in place on preload failure to avoid transient alt-text/broken-icon flashes.
        preload.onerror = function () {
          // No-op.
        };
        preload.src = nextSrc;
      }
    }

    var counters = card.querySelectorAll('.media-counter[data-model-ref]');
    for (var j = 0; j < counters.length; j++) {
      counters[j].textContent = String(mediaIndex + 1) + " / " + String(mediaCount);
    }
    var navButtons = card.querySelectorAll('[data-action="media-prev"],[data-action="media-next"]');
    for (var n = 0; n < navButtons.length; n++) {
      navButtons[n].setAttribute("data-gallery-count", String(mediaCount));
    }
    var previewLabels = card.querySelectorAll('.media-status-chip[data-model-ref] .chip');
    for (var p = 0; p < previewLabels.length; p++) {
      previewLabels[p].textContent = String(mediaIndex + 1) + " / " + String(mediaCount);
    }

    return true;
  }

  _isLikelyImageUrl(url) {
    var value = String(url || "").trim();
    if (!/^https?:\/\//i.test(value)) { return false; }
    try {
      var parsed = new URL(value);
      var path = String(parsed.pathname || "").toLowerCase();
      if (/\.(avif|bmp|gif|ico|jpe?g|png|svg|tiff?|webp)$/i.test(path)) { return true; }
      var qs = String(parsed.search || "").toLowerCase();
      return /(format|fm|ext)=(avif|bmp|gif|ico|jpe?g|png|svg|tiff?|webp)\b/.test(qs);
    } catch (_e) {
      return /\.(avif|bmp|gif|ico|jpe?g|png|svg|tiff?|webp)(\?|#|$)/i.test(value);
    }
  }

  _sourceImagePreviewUrl(model, detail) {
    var FIELD_KEY = "source_image_preview_url";
    if (detail) {
      var ef = detail.enrichment && detail.enrichment.custom_fields && typeof detail.enrichment.custom_fields === "object"
        ? detail.enrichment.custom_fields : {};
      var fromEnrich = String(ef[FIELD_KEY] || "").trim();
      if (fromEnrich) { return fromEnrich; }
      var dmf = detail.model && detail.model.custom_fields && typeof detail.model.custom_fields === "object"
        ? detail.model.custom_fields : {};
      var fromDetailModel = String(dmf[FIELD_KEY] || "").trim();
      if (fromDetailModel) { return fromDetailModel; }
    }
    var sf = model && model.custom_fields && typeof model.custom_fields === "object" ? model.custom_fields : {};
    return String(sf[FIELD_KEY] || "").trim();
  }

  _getModelSourceUrls(model, detail) {
    if (detail && detail.model) {
      var dm = detail.model;
      var sm = dm.structured_metadata && typeof dm.structured_metadata === "object" ? dm.structured_metadata : {};
      var prov = sm.provenance && typeof sm.provenance === "object" ? sm.provenance : {};
      if (Array.isArray(prov.source_urls) && prov.source_urls.length) {
        return prov.source_urls.map(function (u) { return String(u || "").trim(); }).filter(Boolean);
      }
    }
    if (detail && detail.enrichment) {
      var esm = detail.enrichment.structured_metadata && typeof detail.enrichment.structured_metadata === "object"
        ? detail.enrichment.structured_metadata : {};
      var eprov = esm.provenance && typeof esm.provenance === "object" ? esm.provenance : {};
      if (Array.isArray(eprov.source_urls) && eprov.source_urls.length) {
        return eprov.source_urls.map(function (u) { return String(u || "").trim(); }).filter(Boolean);
      }
    }
    var structured = model && model.structured_metadata && typeof model.structured_metadata === "object" ? model.structured_metadata : {};
    var provenance = structured.provenance && typeof structured.provenance === "object" ? structured.provenance : {};
    if (Array.isArray(provenance.source_urls) && provenance.source_urls.length) {
      return provenance.source_urls.map(function (u) { return String(u || "").trim(); }).filter(Boolean);
    }
    return [];
  }

  _hiddenMediaIdSetForModel(model, detail) {
    var hmRaw = null;
    if (detail && detail.enrichment && detail.enrichment.custom_fields) {
      hmRaw = detail.enrichment.custom_fields.media_hidden_ids;
    } else if (detail && detail.model && detail.model.custom_fields) {
      hmRaw = detail.model.custom_fields.media_hidden_ids;
    } else if (model && model.custom_fields) {
      hmRaw = model.custom_fields.media_hidden_ids;
    }
    var values;
    if (Array.isArray(hmRaw)) {
      values = hmRaw;
    } else if (typeof hmRaw === "string" && hmRaw.trim()) {
      try { values = JSON.parse(hmRaw); } catch (_e) { values = hmRaw.split(","); }
    } else {
      return {};
    }
    var set = {};
    for (var i = 0; i < values.length; i++) {
      var v = String(values[i] || "").trim();
      if (v) { set[v] = true; }
    }
    return set;
  }

  _sourceUrlImageList(model, detail) {
    var allUrls = this._getModelSourceUrls(model, detail);
    if (!allUrls.length) { return []; }
    var hiddenSet = this._hiddenMediaIdSetForModel(model, detail);
    var result = [];
    var seen = {};
    for (var i = 0; i < allUrls.length; i++) {
      var url = String(allUrls[i] || "").trim();
      if (!url || !this._isLikelyImageUrl(url)) { continue; }
      var normalized = this._normalizeModelApiUrl(url);
      if (seen[normalized]) { continue; }
      seen[normalized] = true;
      var mediaId = "source_url:" + encodeURIComponent(normalized);
      if (hiddenSet[mediaId]) { continue; }
      result.push(normalized);
    }
    return result;
  }

  _modelMediaUrls(model) {
    var modelRef = this._modelRef(model);
    var detail = modelRef ? this._modelDetailCache[modelRef] : null;
    var detailModel = detail && detail.model && typeof detail.model === "object" ? detail.model : {};
    var urls = [];
    var seen = {};
    var addUrl = function (value) {
      var url = this._normalizeModelApiUrl(String(value || "").trim());
      if (!url || seen[url]) {
        return;
      }
      seen[url] = true;
      urls.push(url);
    }.bind(this);

    var sourcePreviewUrl = this._sourceImagePreviewUrl(model, detail);
    var hasPinnedPhotoPreview = detail && Array.isArray(detail.photos)
      ? detail.photos.some(function (photo) { return Boolean(photo && photo.is_preview); })
      : false;
    var hasPinnedAssetPreview = Array.isArray(detailModel.files)
      ? detailModel.files.some(function (file) { return Boolean(file && (file.is_preview || file.asset_role === "preview")); })
      : false;
    var hasNonSourcePreview = Boolean(hasPinnedPhotoPreview || hasPinnedAssetPreview);

    // Source preview remains primary only when there is no explicit preview
    // marker on photos/files.
    if (sourcePreviewUrl && !hasNonSourcePreview) {
      addUrl(sourcePreviewUrl);
    }

    // Pinned preview photo takes next priority (Option A precedence)
    if (detail && Array.isArray(detail.photos)) {
      var pinnedPhoto = detail.photos.find(function (photo) { return photo && photo.is_preview; });
      if (pinnedPhoto) {
        addUrl(pinnedPhoto.image_url || pinnedPhoto.thumbnail_url || pinnedPhoto.preview_url || pinnedPhoto.url);
      }
    }
    if (detailModel.preview_url) {
      addUrl(detailModel.preview_url);
    }
    var files = Array.isArray(detailModel.files) ? detailModel.files : [];
    if (files.length) {
      files.forEach(function (file) {
        if (file && typeof file === "object") {
          addUrl(file.thumbnail_lazy_url || file.thumbnail_url || file.preview_url);
        }
      });
    }
    if (detail && Array.isArray(detail.photos)) {
      detail.photos.forEach(function (photo) {
        if (photo && typeof photo === "object" && !photo.is_preview) {
          addUrl(photo.image_url || photo.thumbnail_url || photo.preview_url || photo.url);
        }
      });
    }
    addUrl(model && model.preview_url);

    // Add remaining visible image-type source URLs (source_image_preview_url
    // already added above if set; duplicates are skipped via seen set)
    var sourceImageUrls = this._sourceUrlImageList(model, detail);
    for (var si = 0; si < sourceImageUrls.length; si++) {
      addUrl(sourceImageUrls[si]);
    }

    return urls;
  }

  _ideaPlaceholderUrlForModel(model, modelRef) {
    var fields = model && model.custom_fields && typeof model.custom_fields === "object" ? model.custom_fields : {};
    var seed = String(
      modelRef
      || (model && model.local_model_id)
      || (model && model.public_id)
      || fields.local_model_id
      || (model && model.name)
      || "idea"
    ).trim();
    return pickIdeaPlaceholderUrl(seed);
  }

  _resolveModelSidecarUrl() {
    if (this._config && this._config.model_entity && this._hass && this._hass.states) {
      var configuredEntity = this._hass.states[this._config.model_entity];
      if (configuredEntity && configuredEntity.state) {
        return String(configuredEntity.state).trim();
      }
    }

    if (this._hass && this._hass.states) {
      var baseUrlEntity = this._hass.states["input_text.model_catalog_sidecar_base_url"];
      if (baseUrlEntity && baseUrlEntity.state) {
        return String(baseUrlEntity.state).trim();
      }
    }

    return String(this._config && this._config.model_sidecar_url || "").trim();
  }

  _normalizeModelApiUrl(url) {
    var value = String(url || "").trim();
    if (!value) {
      return "";
    }
    if (value.indexOf("/api/models/") !== 0) {
      return value;
    }
    var base = String(this._modelSidecarUrl || "").trim().replace(/\/$/, "");
    if (!base) {
      return value;
    }
    return base + value;
  }

  _isThumbnailLazyEndpoint(url) {
    var value = String(url || "").trim();
    return value.indexOf("/api/models/") >= 0 && value.indexOf("/thumbnail") >= 0;
  }

  _loadModelMedia(model) {
    var modelRef = this._modelRef(model);
    if (!modelRef || this._modelDetailCache[modelRef] || this._loadingModelMedia[modelRef] || !this._hass) {
      return;
    }
    this._loadingModelMedia[modelRef] = true;
    this._callServiceWithResponse("rest_command", "get_model_detail", { model_ref: modelRef })
      .then(function (detail) {
        this._modelDetailCache[modelRef] = detail && typeof detail === "object" ? detail : {};
      }.bind(this))
      .catch(function () {
        this._modelDetailCache[modelRef] = {
          model: { preview_url: model && model.preview_url ? String(model.preview_url) : "" },
          photos: model && model.preview_url ? [{ image_url: String(model.preview_url), thumbnail_url: String(model.preview_url) }] : [],
        };
      }.bind(this))
      .finally(function () {
        delete this._loadingModelMedia[modelRef];
        if (this._viewMode === "media") {
          this._scheduleDeferredRender(90);
          return;
        }
        var thumbResult = this._updateModelCardThumb(modelRef);
        if (!thumbResult) {
          window.setTimeout(function () {
            this._updateModelCardThumb(modelRef);
          }.bind(this), 120);
        }
        this._updateModelCardFileKinds(modelRef);
      }.bind(this));
  }

  _updateModelCardFileKinds(modelRef) {
    if (!this.shadowRoot) {
      return;
    }
    var key = String(modelRef || "").trim();
    if (!key) {
      return;
    }
    var model = null;
    for (var i = 0; i < this._results.length; i++) {
      if (this._modelRef(this._results[i]) === key) {
        model = this._results[i];
        break;
      }
    }
    if (!model) {
      return;
    }
    var detail = this._modelDetailCache[key] || null;
    if (!detail) {
      return;
    }
    var fields = model.custom_fields && typeof model.custom_fields === "object" ? model.custom_fields : {};
    var structured = model.structured_metadata && typeof model.structured_metadata === "object" ? model.structured_metadata : {};
    var counts = this._deriveFileKindCounts(model, structured, fields, detail);
    var chipHtml = this._renderFileKindChipRow(counts);
    var cards = this.shadowRoot.querySelectorAll('.model-card[data-model-ref="' + CSS.escape(key) + '"]');
    for (var c = 0; c < cards.length; c++) {
      var chipContainer = cards[c].querySelector('.compact-file-kinds');
      if (chipContainer) {
        chipContainer.innerHTML = chipHtml;
      }
    }
  }

  _updateModelCardThumb(modelRef) {
    if (!this.shadowRoot) {
      return false;
    }
    var key = String(modelRef || "").trim();
    if (!key) {
      return false;
    }

    var model = null;
    for (var i = 0; i < this._results.length; i++) {
      if (this._modelRef(this._results[i]) === key) {
        model = this._results[i];
        break;
      }
    }
    if (!model) {
      return false;
    }

    var mediaUrls = this._modelMediaUrls(model);
    if (!mediaUrls.length) {
      return false;
    }

    var mediaUrl = String(mediaUrls[0] || "").trim();
    if (!mediaUrl) {
      return false;
    }

    var cards = this.shadowRoot.querySelectorAll('.model-card[data-model-ref]');
    var updated = false;
    for (var c = 0; c < cards.length; c++) {
      var card = cards[c];
      if (String(card.getAttribute("data-model-ref") || "").trim() !== key) {
        continue;
      }
      var thumb = card.querySelector('.thumb');
      if (!thumb) {
        continue;
      }
      var img = thumb.querySelector('img');
      if (!img) {
        thumb.innerHTML = '<img alt="' + this._escapeHtml(String(model.name || "Model") + ' preview') + '" loading="lazy">';
        img = thumb.querySelector('img');
      }
      if (!img) {
        continue;
      }
      // Clear any prior failure flag so the observer will re-attempt the fetch.
      // Without this, a transient CORS/network error after Set-Preview leaves
      // the thumbnail permanently broken.
      img.removeAttribute('data-thumbnail-failed');
      if (this._isThumbnailLazyEndpoint(mediaUrl)) {
        var cachedObjectUrl = getCachedThumbnailObjectUrl(mediaUrl);
        if (cachedObjectUrl) {
          img.removeAttribute('data-thumbnail-lazy-url');
          img.src = String(cachedObjectUrl);
        } else {
          // Set the lazy-url attribute so the observer picks it up and the
          // shimmer CSS animation plays while the image loads.  The observer
          // now uses Image() preload (not fetch) so CORS is not an issue.
          img.removeAttribute('src');
          img.setAttribute('data-thumbnail-lazy-url', mediaUrl);
        }
      } else {
        img.removeAttribute('data-thumbnail-lazy-url');
        img.src = mediaUrl;
      }
      updated = true;
    }

    if (updated) {
      this._scheduleThumbnailObserverSetup();
    }
    return updated;
  }

  /**
   * Delayed retry for a single model's card thumbnail.  Called a few seconds
   * after a detail-change to recover from transient CORS / network errors
   * that can occur immediately after a server-side preview change.
   */
  _retryFailedCardThumb(modelRef) {
    if (!this.shadowRoot) return;
    var key = String(modelRef || "").trim();
    if (!key) return;
    var cards = this.shadowRoot.querySelectorAll('.model-card[data-model-ref="' + CSS.escape(key) + '"]');
    for (var c = 0; c < cards.length; c++) {
      var img = cards[c].querySelector('.thumb img');
      if (!img) continue;
      // Only retry if the thumbnail is still broken (failed flag or no src and
      // no pending lazy-url).
      var isFailed = img.getAttribute('data-thumbnail-failed') === 'true';
      var isEmpty = !img.src && !img.getAttribute('data-thumbnail-lazy-url');
      if (isFailed || isEmpty) {
        this._updateModelCardThumb(key);
        return;
      }
    }
  }

  _renderModelTagChip(label, className) {
    var safeLabel = String(label || "").trim();
    if (!safeLabel) {
      return "";
    }
    return '<span class="chip' + (className ? (' ' + className) : '') + '">' + this._escapeHtml(safeLabel) + '</span>';
  }

  _renderModelMetric(label, value) {
    return ''
      + '<div class="metric">'
      + '  <div class="metric-label">' + this._escapeHtml(label) + '</div>'
      + '  <div class="metric-value">' + this._escapeHtml(String(value || "-")) + '</div>'
      + '</div>';
  }

  _platformDisplayLabel(platformId) {
    var value = String(platformId || "").trim().toLowerCase();
    if (!value) {
      return "Not set";
    }
    var labels = {
      makerworld: "MakerWorld",
      printables: "Printables",
      thingiverse: "Thingiverse",
      cults3d: "Cults3D",
      other: "Other",
      original_local: "Local original",
    };
    return labels[value] || value;
  }

  _originTypeLabel(originType) {
    var value = String(originType || "").trim().toLowerCase();
    if (value === "remix") {
      return "Remix";
    }
    if (value === "derivative") {
      return "Derivative";
    }
    if (value === "custom_unique") {
      return "Custom unique";
    }
    return "Custom unique";
  }

  _coerceBoolish(value) {
    if (value === true || value === false) {
      return value;
    }
    var normalized = String(value || "").trim().toLowerCase();
    if (!normalized) {
      return null;
    }
    if (normalized === "true" || normalized === "1" || normalized === "yes" || normalized === "on") {
      return true;
    }
    if (normalized === "false" || normalized === "0" || normalized === "no" || normalized === "off") {
      return false;
    }
    return null;
  }

  _relativeTimeLabel(isoValue) {
    var raw = String(isoValue || "").trim();
    if (!raw) {
      return "Never";
    }
    var parsed = new Date(raw);
    if (!Number.isFinite(parsed.getTime())) {
      return "Unknown";
    }
    var deltaMs = Date.now() - parsed.getTime();
    if (!Number.isFinite(deltaMs) || deltaMs < 0) {
      return "Now";
    }
    var deltaMinutes = Math.floor(deltaMs / 60000);
    if (deltaMinutes < 60) {
      return String(Math.max(1, deltaMinutes)) + "m ago";
    }
    var deltaHours = Math.floor(deltaMinutes / 60);
    if (deltaHours < 48) {
      return String(deltaHours) + "h ago";
    }
    var deltaDays = Math.floor(deltaHours / 24);
    if (deltaDays < 28) {
      return String(deltaDays) + "d ago";
    }
    var deltaWeeks = Math.floor(deltaDays / 7);
    if (deltaWeeks < 12) {
      return String(deltaWeeks) + "w ago";
    }
    var deltaMonths = Math.floor(deltaDays / 30);
    if (deltaMonths < 24) {
      return String(deltaMonths) + "mo ago";
    }
    var deltaYears = Math.floor(deltaDays / 365);
    return String(deltaYears) + "y ago";
  }

  _formatBytes(value) {
    var bytes = Number(value || 0);
    if (!Number.isFinite(bytes) || bytes <= 0) {
      return "0 B";
    }
    var units = ["B", "KB", "MB", "GB", "TB"];
    var unitIndex = 0;
    while (bytes >= 1024 && unitIndex < units.length - 1) {
      bytes = bytes / 1024;
      unitIndex += 1;
    }
    var precision = unitIndex === 0 ? 0 : (bytes >= 10 ? 1 : 2);
    return String(bytes.toFixed(precision)) + " " + units[unitIndex];
  }

  _escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _renderNavigationControls() {
    var page = this._currentPage();
    var pages = this._pageCount();
    return ''
      + '<div class="toolbar-group nav-group">'
      + '  <button class="toolbar-icon-btn" type="button" data-action="first-page" aria-label="First page" title="First page" ' + (page <= 1 ? 'disabled' : '') + '><ha-icon icon="mdi:page-first"></ha-icon></button>'
      + '  <button class="toolbar-icon-btn" type="button" data-action="prev-page" aria-label="Previous page" title="Previous page" ' + (page <= 1 ? 'disabled' : '') + '><ha-icon icon="mdi:chevron-left"></ha-icon></button>'
      + '  <div class="page-status">' + this._renderPageStatusWithCount() + '</div>'
      + '  <button class="toolbar-icon-btn" type="button" data-action="next-page" aria-label="Next page" title="Next page" ' + (page >= pages ? 'disabled' : '') + '><ha-icon icon="mdi:chevron-right"></ha-icon></button>'
      + '  <button class="toolbar-icon-btn" type="button" data-action="last-page" aria-label="Last page" title="Last page" ' + (page >= pages ? 'disabled' : '') + '><ha-icon icon="mdi:page-last"></ha-icon></button>'
      + '</div>';
  }

  _renderOptionToggle(option) {
    var active = this._browserScope === option;
    var label = "All models";
    if (option === "collections") {
      label = "Collections";
    } else if (option === "working") {
      label = "Working";
    }
    return ''
      + '<button class="segmented-btn' + (active ? ' active' : '') + '" type="button" data-action="set-browser-scope" data-scope="' + this._escapeHtml(option) + '" ' + (this._loading ? 'disabled' : '') + '>'
      + this._escapeHtml(label)
      + '</button>';
  }

  _renderLeftNavItem(label, key, count, icon) {
    var isActive = false;
    var isFacetFilterItem = false;
    var isSystemBucket = key === "collection:__unassigned__";
    if (key.indexOf("collection:") === 0) {
      isFacetFilterItem = true;
      isActive = this._selectedCollectionKey() === String(key.slice("collection:".length) || "").trim().toLowerCase();
    } else if (key.indexOf("tag:") === 0) {
      isFacetFilterItem = true;
      isActive = this._hasTagFilter(String(key.slice("tag:".length) || "").trim().toLowerCase());
    } else {
      isActive = this._leftNavSelectedKey === key;
    }
    var trailingMarkup = "";
    if (isActive && isFacetFilterItem) {
      trailingMarkup = '<span class="left-nav-item-count dismiss" aria-hidden="true">\u00d7</span>';
    } else if (count !== null && count !== undefined && count !== "" && Number.isFinite(Number(count))) {
      trailingMarkup = '<span class="left-nav-item-count">' + this._escapeHtml(String(Math.max(0, Number(count)))) + '</span>';
    }
    var title = String(label || "").trim();
    return ''
      + '<button class="left-nav-item' + (isActive ? ' active' : '') + (isSystemBucket ? ' system-bucket' : '') + '" type="button" data-action="select-left-nav-item" data-nav-key="' + this._escapeHtml(key) + '" aria-label="' + this._escapeHtml(title || key) + '" title="' + this._escapeHtml(title || key) + '" aria-pressed="' + (isActive ? 'true' : 'false') + '">'
      + '  <span class="left-nav-item-main">'
      + (icon ? '<ha-icon icon="' + this._escapeHtml(icon) + '"></ha-icon>' : '')
      + '    <span class="left-nav-item-label">' + this._escapeHtml(label) + '</span>'
      + '  </span>'
      + trailingMarkup
      + '</button>';
  }

  _leftNavTypeIcon(typeKey) {
    if (typeKey === "idea") {
      return "mdi:lightbulb-outline";
    }
    if (typeKey === "working") {
      return "mdi:folder-open-outline";
    }
    return "mdi:cube-outline";
  }

  _renderLeftNavTypeToggle(label, typeKey, count) {
    var checked = !!(this._typeFilters && this._typeFilters[typeKey]);
    var icon = this._leftNavTypeIcon(typeKey);
    return ''
      + '<label class="left-nav-type-toggle" data-action="toggle-left-nav-type" data-type="' + this._escapeHtml(typeKey) + '" aria-label="Toggle ' + this._escapeHtml(label) + ' filter" title="' + this._escapeHtml(label) + '">'
      + '  <input class="left-nav-type-checkbox" type="checkbox" ' + (checked ? 'checked' : '') + ' data-action="toggle-left-nav-type" data-type="' + this._escapeHtml(typeKey) + '">'
      + '  <span class="left-nav-type-icon" aria-hidden="true"><ha-icon icon="' + this._escapeHtml(icon) + '"></ha-icon></span>'
      + '  <span class="left-nav-type-label">' + this._escapeHtml(label) + '</span>'
      + '  <span class="left-nav-type-count">' + this._escapeHtml(String(Math.max(0, Number(count || 0) || 0))) + '</span>'
      + '</label>';
  }

  _renderCollapsedFacetSectionTrigger(label, sectionKey, icon, isActive, count) {
    var numericCount = Number(count || 0);
    var trailingMarkup = numericCount > 0
      ? '<span class="left-nav-item-count">' + this._escapeHtml(String(Math.max(0, Math.trunc(numericCount)))) + '</span>'
      : '';
    return ''
      + '<button class="left-nav-item left-nav-section-trigger' + (isActive ? ' active' : '') + '" type="button" data-action="expand-left-nav-section" data-section="' + this._escapeHtml(sectionKey) + '" aria-label="Open ' + this._escapeHtml(label) + ' filters" title="' + this._escapeHtml(label) + '">'
      + '  <span class="left-nav-item-main">'
      + '    <ha-icon icon="' + this._escapeHtml(icon) + '"></ha-icon>'
      + '    <span class="left-nav-item-label">' + this._escapeHtml(label) + '</span>'
      + '  </span>'
      + trailingMarkup
      + '</button>';
  }

  _leftNavTopTags(limit) {
    var max = Math.max(1, Number(limit || 6));
    var serverTags = this._facetCounts && Array.isArray(this._facetCounts.tags)
      ? this._facetCounts.tags
      : [];
    if (serverTags.length) {
      var serverEntries = [];
      for (var s = 0; s < serverTags.length; s++) {
        var serverTag = serverTags[s] || {};
        var label = String(serverTag.label || serverTag.key || "").trim();
        var key = String(serverTag.key || "").trim().toLowerCase();
        var count = Number(serverTag.count || 0);
        if (!label || !key || !Number.isFinite(count) || count <= 0) {
          continue;
        }
        serverEntries.push({ key: key, count: Math.max(0, Math.trunc(count)) });
      }
      serverEntries.sort(function (a, b) {
        if (b.count !== a.count) {
          return b.count - a.count;
        }
        return a.key.localeCompare(b.key);
      });
      return serverEntries.slice(0, max);
    }

    var counts = {};
    for (var i = 0; i < this._results.length; i++) {
      var model = this._results[i] || {};
      var rawTags = [];
      if (Array.isArray(model.keyword_names)) {
        rawTags = rawTags.concat(model.keyword_names);
      }
      var fields = model && model.custom_fields && typeof model.custom_fields === "object" ? model.custom_fields : {};
      if (Array.isArray(fields.keyword_names)) {
        rawTags = rawTags.concat(fields.keyword_names);
      }
      var uniquePerModel = {};
      for (var t = 0; t < rawTags.length; t++) {
        var tag = String(rawTags[t] || "").trim();
        if (!tag) {
          continue;
        }
        var normalized = tag.toLowerCase();
        if (uniquePerModel[normalized]) {
          continue;
        }
        uniquePerModel[normalized] = true;
        counts[normalized] = (counts[normalized] || 0) + 1;
      }
    }

    var entries = Object.keys(counts).map(function (entryKey) {
      return { key: entryKey, count: counts[entryKey] };
    });
    entries.sort(function (a, b) {
      if (b.count !== a.count) {
        return b.count - a.count;
      }
      return a.key.localeCompare(b.key);
    });
    return entries.slice(0, max);
  }

  _leftNavTopCollections(limit) {
    var max = Math.max(1, Number(limit || 6));
    var serverCollections = this._globalFacets && Array.isArray(this._globalFacets.collections)
      ? this._globalFacets.collections
      : (this._facetCounts && Array.isArray(this._facetCounts.collections)
        ? this._facetCounts.collections
        : []);
    if (serverCollections.length) {
      var serverEntries = [];
      for (var s = 0; s < serverCollections.length; s++) {
        var serverCollection = serverCollections[s] || {};
        var label = String(serverCollection.label || serverCollection.key || "").trim();
        var rawKey = String(serverCollection.key || "").trim().toLowerCase();
        var count = Number(serverCollection.count || 0);
        if (!label || !rawKey || !Number.isFinite(count) || count <= 0) {
          continue;
        }
        var key = rawKey === "unassigned" ? "__unassigned__" : rawKey;
        serverEntries.push({
          key: key,
          label: key === "__unassigned__" ? "Unassigned" : label,
          count: Math.max(0, Math.trunc(count)),
        });
      }
      serverEntries.sort(function (a, b) {
        if (b.count !== a.count) {
          return b.count - a.count;
        }
        return a.label.localeCompare(b.label);
      });
      return serverEntries.slice(0, max);
    }

    var counts = {};
    var labels = {};
    var unassignedKey = "__unassigned__";
    var unassignedLabel = "Unassigned";
    for (var i = 0; i < this._results.length; i++) {
      var model = this._results[i] || {};
      var collections = Array.isArray(model.collection_names) ? model.collection_names.slice(0) : [];
      if (!collections.length) {
        counts[unassignedKey] = (counts[unassignedKey] || 0) + 1;
        labels[unassignedKey] = unassignedLabel;
        continue;
      }
      var seen = {};
      for (var c = 0; c < collections.length; c++) {
        var raw = String(collections[c] || "").trim();
        if (!raw) {
          continue;
        }
        var label = raw;
        var key = label.toLowerCase();
        if (!key || seen[key]) {
          continue;
        }
        seen[key] = true;
        counts[key] = (counts[key] || 0) + 1;
        if (!labels[key]) {
          labels[key] = label;
        }
      }
    }
    var entries = Object.keys(counts).map(function (entryKey) {
      return {
        key: entryKey,
        label: labels[entryKey] || entryKey,
        count: counts[entryKey],
      };
    });
    entries.sort(function (a, b) {
      if (b.count !== a.count) {
        return b.count - a.count;
      }
      return a.label.localeCompare(b.label);
    });
    return entries.slice(0, max);
  }

  _deriveLeftNavKeyFromFilters() {
    if (this._filters && this._filters.project_id) {
      return "project:" + this._filters.project_id;
    }
    if (this._filters && this._filters.favorites_only) {
      return "favorites";
    }
    if (this._filters && this._filters.frequents_only) {
      return "frequents";
    }
    if (this._filters && this._filters.recent_added_only) {
      return "recent-added";
    }
    if (this._filters && this._filters.recent_printed_only) {
      return "recent-printed";
    }
    if (this._selectedCollectionKey() || this._activeTagFilters().length) {
      return "all-models";
    }
    return "all-models";
  }

  _activeContextLabel() {
    var key = this._leftNavSelectedKey || "all-models";
    if (key === "favorites") return "Favorites";
    if (key === "frequents") return "Frequents";
    if (key === "recent-added") return "Recently added";
    if (key === "recent-printed") return "Recently printed";
    if (key.indexOf("project:") === 0) {
      var projectId = parseInt(key.slice("project:".length), 10);
      var project = this._findProjectById(projectId);
      return project ? project.title : "Project";
    }
    var selectedCollection = this._selectedCollectionKey();
    var activeTags = this._activeTagFilters();
    if (selectedCollection && activeTags.length) {
      return this._displayCollectionLabel(selectedCollection) + " + " + activeTags.length + " tag" + (activeTags.length > 1 ? "s" : "");
    }
    if (selectedCollection) {
      return this._displayCollectionLabel(selectedCollection);
    }
    if (activeTags.length === 1) {
      return this._displayTagLabel(activeTags[0]);
    }
    if (activeTags.length > 1) {
      return activeTags.length + " tags";
    }
    return "All models";
  }

  _activeContextIcon() {
    var key = this._leftNavSelectedKey || "all-models";
    if (key === "favorites") return "mdi:star-outline";
    if (key === "frequents") return "mdi:lightning-bolt-outline";
    if (key === "recent-added") return "mdi:clock-plus-outline";
    if (key === "recent-printed") return "mdi:printer-3d-nozzle-outline";
    if (key.indexOf("project:") === 0) return "mdi:clipboard-text-outline";
    if (this._selectedCollectionKey() === "__unassigned__") return "mdi:folder-remove-outline";
    if (this._selectedCollectionKey()) return "mdi:folder-outline";
    if (this._activeTagFilters().length) return "mdi:tag-outline";
    return "mdi:cube-outline";
  }

  _syncLeftNavSelectionFromFilters() {
    this._leftNavSelectedKey = this._deriveLeftNavKeyFromFilters();
  }

  _findProjectById(id) {
    var numId = Number(id);
    for (var i = 0; i < this._projects.length; i++) {
      if (Number(this._projects[i].id) === numId) {
        return this._projects[i];
      }
    }
    return null;
  }

  async _loadProjects() {
    if (this._projectsLoaded) {
      return;
    }
    var base = String(this._resolveModelSidecarUrl() || "").trim().replace(/\/$/, "");
    if (!/^https?:\/\//i.test(base)) {
      this._projectsError = "No sidecar URL configured";
      return;
    }
    try {
      var resp = await fetch(base + "/api/projects?limit=50&offset=0", {
        method: "GET",
        headers: { "Accept": "application/json" },
      });
      if (!resp.ok) {
        this._projectsError = "Failed to load projects (" + resp.status + ")";
        this._projects = [];
      } else {
        var data = await resp.json();
        this._projects = Array.isArray(data) ? data : (data && Array.isArray(data.items) ? data.items : []);
        this._projectsError = "";
      }
    } catch (err) {
      this._projectsError = "Projects fetch error";
      this._projects = [];
    }
    this._projectsLoaded = true;
    this._doRender();
  }

  _applyLeftNavSelection(navKey, options) {
    var settings = options && typeof options === "object" ? options : {};
    var key = String(navKey || "all-models").trim() || "all-models";
    this._leftNavSelectedKey = key;

    var contextCollection = this._selectedCollectionKey();
    var contextTags = this._activeTagFilters();
    var contextFavorites = false;
    var contextFrequents = false;
    var contextRecentAdded = !!(this._filters && this._filters.recent_added_only);
    var contextRecentPrinted = !!(this._filters && this._filters.recent_printed_only);

    if (key === "favorites") {
      contextCollection = "";
      contextTags = [];
      contextFavorites = true;
      contextRecentAdded = false;
      contextRecentPrinted = false;
    } else if (key === "frequents") {
      contextCollection = "";
      contextTags = [];
      contextFrequents = true;
      contextRecentAdded = false;
      contextRecentPrinted = false;
    } else if (key.indexOf("collection:") === 0) {
      var nextCollection = String(key.slice("collection:".length) || "").trim().toLowerCase();
      contextCollection = contextCollection === nextCollection ? "" : nextCollection;
    } else if (key.indexOf("tag:") === 0) {
      var nextTag = String(key.slice("tag:".length) || "").trim().toLowerCase();
      if (nextTag) {
        if (contextTags.indexOf(nextTag) !== -1) {
          contextTags = contextTags.filter(function (value) {
            return value !== nextTag;
          });
        } else {
          contextTags = contextTags.concat([nextTag]);
        }
      }
    } else if (key === "recent-added") {
      contextCollection = "";
      contextTags = [];
      contextRecentAdded = true;
      contextRecentPrinted = false;
      this._filters.sort = "added";
    } else if (key === "recent-printed") {
      contextCollection = "";
      contextTags = [];
      contextRecentAdded = false;
      contextRecentPrinted = true;
      this._filters.sort = "recent";
    } else if (key.indexOf("project:") === 0) {
      var projectId = parseInt(key.slice("project:".length), 10);
      contextCollection = "";
      contextTags = [];
      contextRecentAdded = false;
      contextRecentPrinted = false;
      this._filters.project_id = projectId || null;
    } else {
      contextCollection = "";
      contextTags = [];
      contextRecentAdded = false;
      contextRecentPrinted = false;
    }

    if (key.indexOf("project:") !== 0) {
      this._filters.project_id = null;
    }
    this._filters.collection = contextCollection;
    this._setActiveTagFilters(contextTags);
    this._filters.favorites_only = contextFavorites;
    this._filters.frequents_only = contextFrequents;
    this._filters.recent_added_only = contextRecentAdded;
    this._filters.recent_printed_only = contextRecentPrinted;

    if (this._browserScope !== "models" && this._browserScope !== "collections") {
      this._browserScope = "models";
    }

    if (this._leftNavAutoCollapsePending) {
      this._leftNavCollapsed = true;
      this._leftNavAutoCollapsePending = false;
    }

    if (settings.closeDrawer !== false && this._leftNavDrawerOpen) {
      this._leftNavDrawerOpen = false;
    }
    this._cancelScheduledApply();
    if (settings.requestLoad !== false) {
      this._requestLoad(1, false);
    }
    if (settings.render !== false) {
      this._render();
    }
  }

  _renderLeftNav() {
    var totalCount = Math.max(0, Number(this._pagination && this._pagination.total || 0));
    var favoritesCount = 0;
    var frequentsCount = 0;
    var recentAddedCount = 0;
    var recentPrintedCount = 0;
    var typeCounts = this._entityTypeCounts();
    var workingCount = this._coerceWorkingCount(this._workingProjection && this._workingProjection.length || 0);
    for (var i = 0; i < this._results.length; i++) {
      var model = this._results[i] || {};
      var ranking = model && model.ranking && typeof model.ranking === "object" ? model.ranking : {};
      var favoriteValue = this._coerceBoolish(model.model_favorite);
      if (favoriteValue === null) {
        var fields = model && model.custom_fields && typeof model.custom_fields === "object" ? model.custom_fields : {};
        favoriteValue = this._coerceBoolish(fields.model_favorite);
      }
      if (favoriteValue) {
        favoritesCount += 1;
      }
      if (Number(ranking.frequent_score || 0) > 0) {
        frequentsCount += 1;
      }
      if (String(model.created_at || "").trim()) {
        recentAddedCount += 1;
      }
      if (String(model.last_printed_at || ranking.last_printed_at || "").trim()) {
        recentPrintedCount += 1;
      }
    }

    var topTags = this._leftNavTopTags(6);
    var topCollections = this._leftNavTopCollections(6);
    var navClass = 'left-nav'
      + (this._leftNavCollapsed ? ' collapsed' : '')
      + (this._leftNavDrawerOpen ? ' drawer-open' : '');

    var tagsHtml = '';
    var renderedTagKeys = {};
    var selectedTags = this._activeTagFilters();
    for (var selectedTagIndex = 0; selectedTagIndex < selectedTags.length; selectedTagIndex++) {
      var selectedTagKey = selectedTags[selectedTagIndex];
      renderedTagKeys[selectedTagKey] = true;
      tagsHtml += this._renderLeftNavItem(this._displayTagLabel(selectedTagKey), 'tag:' + selectedTagKey, null, 'mdi:tag-outline');
    }
    for (var tagIndex = 0; tagIndex < topTags.length; tagIndex++) {
      var tagEntry = topTags[tagIndex];
      if (renderedTagKeys[tagEntry.key]) {
        continue;
      }
      tagsHtml += this._renderLeftNavItem(tagEntry.key, 'tag:' + tagEntry.key, tagEntry.count, 'mdi:tag-outline');
    }
    if (!tagsHtml) {
      tagsHtml = '<div class="left-nav-empty">No tags detected yet</div>';
    }

    var collectionsHtml = '';
    var selectedCollectionKey = this._selectedCollectionKey();
    collectionsHtml = this._renderCollectionTreeSection();
    if (!collectionsHtml) {
      var selectedCollectionRendered = false;
      for (var collectionIndex = 0; collectionIndex < topCollections.length; collectionIndex++) {
        var collectionEntry = topCollections[collectionIndex];
        if (selectedCollectionKey && collectionEntry.key === selectedCollectionKey) {
          selectedCollectionRendered = true;
        }
        collectionsHtml += this._renderLeftNavItem(collectionEntry.label, 'collection:' + collectionEntry.key, collectionEntry.count, 'mdi:folder-outline');
      }
      if (selectedCollectionKey && !selectedCollectionRendered) {
        collectionsHtml += this._renderLeftNavItem(
          this._displayCollectionLabel(selectedCollectionKey),
          'collection:' + selectedCollectionKey,
          null,
          'mdi:folder-outline'
        );
      }
    }
    if (!collectionsHtml) {
      collectionsHtml = '<div class="left-nav-empty">No collections detected yet</div>';
    }

    var tagsSectionHtml = this._leftNavCollapsed
      ? this._renderCollapsedFacetSectionTrigger('Tags', 'tags', 'mdi:tag-multiple-outline', selectedTags.length > 0, selectedTags.length)
      : tagsHtml;
    var collectionsSectionHtml = this._leftNavCollapsed
      ? this._renderCollapsedFacetSectionTrigger('Collections', 'collections', 'mdi:folder-multiple-outline', !!selectedCollectionKey, selectedCollectionKey ? 1 : 0)
      : collectionsHtml;

    return ''
      + '<aside class="' + navClass + '" role="navigation" aria-label="Catalog navigation">'
      + '  <div class="left-nav-head">'
      + '    <div class="left-nav-title-wrap">'
      + '      <ha-icon icon="mdi:view-dashboard-outline"></ha-icon>'
      + '      <span class="left-nav-title-text">Catalog Browse</span>'
      + '    </div>'
      + '    <button class="toolbar-icon-btn left-nav-collapse" type="button" data-action="toggle-left-nav-collapse" aria-label="Toggle navigation collapse" aria-pressed="' + (this._leftNavCollapsed ? 'true' : 'false') + '"><ha-icon icon="mdi:chevron-left"></ha-icon></button>'
      + '  </div>'
      + '  <div class="left-nav-section" role="group" aria-label="Type filters">'
      + '    <div class="left-nav-section-label">Type</div>'
      +      this._renderLeftNavTypeToggle('Model', 'model', typeCounts.model || 0)
      +      this._renderLeftNavTypeToggle('Idea', 'idea', typeCounts.idea || 0)
      +      this._renderLeftNavTypeToggle('Working Files', 'working', workingCount)
      + '  </div>'
      + '  <div class="left-nav-section" role="group" aria-label="Quick pivots">'
      + '    <div class="left-nav-section-label">Quick pivots</div>'
      +      this._renderLeftNavItem('All models', 'all-models', totalCount, 'mdi:cube-outline')
      +      this._renderLeftNavItem('Favorites', 'favorites', favoritesCount, 'mdi:star-outline')
      +      this._renderLeftNavItem('Frequents', 'frequents', frequentsCount, 'mdi:lightning-bolt-outline')
      +      this._renderLeftNavItem('Recently added', 'recent-added', recentAddedCount, 'mdi:clock-plus-outline')
      +      this._renderLeftNavItem('Recently printed', 'recent-printed', recentPrintedCount, 'mdi:printer-3d-nozzle-outline')
      + '  </div>'
      + '  <div class="left-nav-section" role="group" aria-label="Collections">'
      + '    <div class="left-nav-section-label">Collections</div>'
        +      collectionsSectionHtml
      + '  </div>'
      + '  <div class="left-nav-section" role="group" aria-label="Tags">'
      + '    <div class="left-nav-section-label">Tags</div>'
        +      tagsSectionHtml
      + '  </div>'
      + this._renderLeftNavProjectsSection()
      + '</aside>';
  }

  _renderLeftNavProjectsSection() {
    if (!this._projectsLoaded) {
      this._loadProjects();
      return '<div class="left-nav-section" role="group" aria-label="Projects">'
        + '<div class="left-nav-section-label">Projects</div>'
        + '<div class="left-nav-empty">Loading\u2026</div>'
        + '</div>';
    }
    if (this._projectsError || !this._projects.length) {
      var emptyMsg = this._projectsError || 'No projects yet';
      return '<div class="left-nav-section" role="group" aria-label="Projects">'
        + '<div class="left-nav-section-label">Projects</div>'
        + '<div class="left-nav-empty">' + this._escapeHtml(emptyMsg) + '</div>'
        + '</div>';
    }
    if (this._leftNavCollapsed) {
      var selectedProjectId = this._filters && this._filters.project_id ? this._filters.project_id : null;
      return this._renderCollapsedFacetSectionTrigger('Projects', 'projects', 'mdi:clipboard-text-multiple-outline', !!selectedProjectId, selectedProjectId ? 1 : 0);
    }
    var html = '';
    for (var i = 0; i < this._projects.length; i++) {
      var p = this._projects[i];
      var title = String(p.title || p.name || 'Untitled').trim();
      var modelCount = p.model_count != null ? Number(p.model_count) : null;
      html += this._renderLeftNavItem(title, 'project:' + p.id, modelCount, 'mdi:clipboard-text-outline');
    }
    return '<div class="left-nav-section" role="group" aria-label="Projects">'
      + '<div class="left-nav-section-label">Projects</div>'
      + html
      + '</div>';
  }

  _advancedFilterCount() {
    var count = 0;
    if (String(this._filters && this._filters.creator || '').trim()) {
      count += 1;
    }
    if (this._filters && this._filters.has_other_files) {
      count += 1;
    }
    if (this._filters && this._filters.show_archived) {
      count += 1;
    }
    if (this._clampInteger(this._frequentsTuning.window_days, 90, 7, 3650) !== 90) {
      count += 1;
    }
    if (this._clampInteger(this._frequentsTuning.min_prints, 3, 1, 9999) !== 3) {
      count += 1;
    }
    return count;
  }

  _renderAdvancedFiltersMenu() {
    var advancedCount = this._advancedFilterCount();
    var windowDays = this._clampInteger(this._frequentsTuning.window_days, 90, 7, 3650);
    var minPrints = this._clampInteger(this._frequentsTuning.min_prints, 3, 1, 9999);
    var archivedCount = Math.max(0, Number(this._visibilityCounts && this._visibilityCounts.archived || 0) || 0);
    var showArchivedLabel = 'Show archived' + (archivedCount > 0 ? (' \u00b7 ' + String(archivedCount)) : '');
    return ''
      + '<details class="advanced-filter-menu">'
      + '  <summary class="toolbar-btn advanced-filter-trigger" aria-label="Advanced filters">'
      + '    <span>Advanced</span>'
      + (advancedCount > 0 ? '<span class="advanced-filter-badge">' + this._escapeHtml(String(advancedCount)) + '</span>' : '')
      + '    <ha-icon icon="mdi:chevron-down"></ha-icon>'
      + '  </summary>'
      + '  <div class="advanced-filter-items">'
      + '    <label class="control advanced-filter-field" for="mc-creator">'
      + '      <span>Creator</span>'
      + '      <input id="mc-creator" class="control-input" type="text" placeholder="Creator" value="' + this._escapeHtml(this._filters.creator) + '">'
      + '    </label>'
      + '    <div class="advanced-filter-toggle-row">'
      + '      <button class="filter-chip toggle-chip' + (this._filters.has_other_files ? ' active docs' : '') + '" type="button" data-action="toggle-other-files-filter" aria-pressed="' + (this._filters.has_other_files ? 'true' : 'false') + '">Has other files</button>'
      + '      <button class="filter-chip toggle-chip' + (this._filters.show_archived ? ' active archived' : '') + '" type="button" data-action="toggle-show-archived-filter" aria-pressed="' + (this._filters.show_archived ? 'true' : 'false') + '">' + this._escapeHtml(showArchivedLabel) + '</button>'
      + '    </div>'
      + '    <div class="advanced-filter-section">'
      + '      <div class="advanced-filter-section-label">Frequents</div>'
      + '      <div class="advanced-filter-tuning-row">'
      + '        <label class="inline-select" for="mc-frequent-window">Freq window'
      + '          <select id="mc-frequent-window" class="control-input compact-select tuning-select">'
      + '            <option value="30"' + (windowDays === 30 ? ' selected' : '') + '>30d</option>'
      + '            <option value="90"' + (windowDays === 90 ? ' selected' : '') + '>90d</option>'
      + '            <option value="365"' + (windowDays === 365 ? ' selected' : '') + '>1y</option>'
      + '            <option value="3650"' + (windowDays === 3650 ? ' selected' : '') + '>All</option>'
      + '          </select>'
      + '        </label>'
      + '        <label class="inline-select" for="mc-frequent-min-prints">Min prints'
      + '          <select id="mc-frequent-min-prints" class="control-input compact-select tuning-select">'
      + '            <option value="1"' + (minPrints === 1 ? ' selected' : '') + '>1</option>'
      + '            <option value="2"' + (minPrints === 2 ? ' selected' : '') + '>2</option>'
      + '            <option value="3"' + (minPrints === 3 ? ' selected' : '') + '>3</option>'
      + '            <option value="4"' + (minPrints === 4 ? ' selected' : '') + '>4</option>'
      + '            <option value="5"' + (minPrints === 5 ? ' selected' : '') + '>5</option>'
      + '            <option value="6"' + (minPrints === 6 ? ' selected' : '') + '>6</option>'
      + '          </select>'
      + '        </label>'
      + '      </div>'
      + '    </div>'
      + '    <input id="mc-has-other-files" type="checkbox" hidden ' + (this._filters.has_other_files ? 'checked' : '') + '>'
      + '    <input id="mc-show-archived" type="checkbox" hidden ' + (this._filters.show_archived ? 'checked' : '') + '>'
      + '    <div class="advanced-filter-footer">'
      + '      <button class="toolbar-btn ghost" type="button" data-action="clear-filters" ' + (this._loading ? 'disabled' : '') + '>Clear</button>'
      + '    </div>'
      + '  </div>'
      + '</details>';
  }

  _renderHeaderTitleRow() {
    var sortOptionsHtml = '';
    sortOptionsHtml = ''
      + '        <option value="best"' + (this._filters.sort === 'best' ? ' selected' : '') + '>Best match</option>'
      + '        <option value="added"' + (this._filters.sort === 'added' ? ' selected' : '') + '>Recently added</option>'
      + '        <option value="recent"' + (this._filters.sort === 'recent' ? ' selected' : '') + '>Recently printed</option>'
      + '        <option value="frequent"' + (this._filters.sort === 'frequent' ? ' selected' : '') + '>Frequent</option>'
      + '        <option value="common"' + (this._filters.sort === 'common' ? ' selected' : '') + '>Common</option>'
      + '        <option value="name"' + (this._filters.sort === 'name' ? ' selected' : '') + '>Name</option>';
    return ''
      + '<div class="title-row">'
      + '  <div class="title-left">'
      + '    <button class="toolbar-icon-btn left-nav-toggle" type="button" data-action="toggle-left-nav-drawer" aria-label="Toggle catalog navigation" aria-expanded="' + (this._leftNavDrawerOpen ? 'true' : 'false') + '"><ha-icon icon="mdi:menu"></ha-icon></button>'
      + '    <button class="nav-context-chip" type="button" data-action="toggle-left-nav-drawer" aria-label="Current view: ' + this._escapeHtml(this._activeContextLabel()) + '"><ha-icon icon="' + this._escapeHtml(this._activeContextIcon()) + '"></ha-icon><span class="nav-context-label">' + this._escapeHtml(this._activeContextLabel()) + '</span><ha-icon icon="mdi:chevron-down" class="nav-context-caret"></ha-icon></button>'
      + '    <div class="card-title">' + this._escapeHtml(this._config.title) + '</div>'
      + '  </div>'
      + '  <div class="title-right">'
      + '    <div class="segmented-toggle" role="group" aria-label="Catalog scope">'
      + this._renderOptionToggle("models")
      + this._renderOptionToggle("collections")
      + '    </div>'
      + '    <div class="toolbar-group sort-group">'
      + '      <label for="mc-sort">Sort</label>'
      + '      <select id="mc-sort" class="control-input title-select">'
      + sortOptionsHtml
      + '      </select>'
      + '    </div>'
      + this._renderAdvancedFiltersMenu()
      + '    <button class="toolbar-btn" type="button" data-action="create-model" ' + (this._loading ? 'disabled' : '') + '>+ Add Model</button>'
      + '    <button class="toolbar-btn" type="button" data-action="create-idea" ' + (this._loading ? 'disabled' : '') + '>+ Add Idea</button>'
      + '    <details class="import-menu">'
      + '      <summary class="toolbar-btn import-trigger">Import <ha-icon icon="mdi:chevron-down"></ha-icon></summary>'
      + '      <div class="import-menu-items">'
      + '        <button class="import-item" type="button" data-action="open-import-browser">Browser Upload</button>'
      + '        <button class="import-item" type="button" data-action="open-import-server">Server Inbox</button>'
      + '      </div>'
      + '    </details>'
      + '  </div>'
      + '</div>';
  }

  _renderFilterBar() {
    if (this._browserScope === "working") {
      var workingCount = Math.max(0, Number(this._pagination && this._pagination.total || 0) || 0);
      return ''
        + '<div class="filter-bar-stack">'
        + '<div class="filter-row working-filter-row">'
        + '  <input id="mc-q" class="control-input filter-search" type="text" placeholder="Search working folders" value="' + this._escapeHtml(this._filters.q) + '">'
        + '  <span class="filter-chip toggle-chip active docs" aria-live="polite">Projected folders · ' + this._escapeHtml(String(workingCount)) + '</span>'
        + '  <button class="toolbar-btn ghost" type="button" data-action="clear-filters" ' + (this._loading ? 'disabled' : '') + '>Clear</button>'
        + '</div>'
        + '</div>';
    }
    var selectedFilterStrip = this._renderSelectedFilterStrip();
    return ''
      + '<div class="filter-bar-stack">'
      + '<div class="filter-row search-only-filter-row">'
      + '  <input id="mc-q" class="control-input filter-search" type="text" placeholder="Search models" value="' + this._escapeHtml(this._filters.q) + '">'
      + '</div>'
      + selectedFilterStrip
      + '</div>';
  }

  _renderSelectedFilterStrip() {
    var selectedCollectionKey = this._selectedCollectionKey();
    var selectedTags = this._activeTagFilters();
    if (!selectedCollectionKey && !selectedTags.length) {
      return '';
    }
    var chips = '';
    if (selectedCollectionKey) {
      chips += '<button class="selected-filter-chip collection-chip" type="button" data-action="clear-collection-filter">'
        + '<span class="selected-filter-prefix">Collection</span>'
        + '<span class="selected-filter-value">' + this._escapeHtml(this._displayCollectionLabel(selectedCollectionKey)) + '</span>'
        + '<span class="selected-filter-remove" aria-hidden="true">\u00d7</span>'
        + '</button>';
    }
    for (var i = 0; i < selectedTags.length; i++) {
      var tagKey = selectedTags[i];
      chips += '<button class="selected-filter-chip tag-chip" type="button" data-action="clear-selected-tag" data-tag="' + this._escapeHtml(tagKey) + '">'
        + '<span class="selected-filter-prefix">Tag</span>'
        + '<span class="selected-filter-value">' + this._escapeHtml(this._displayTagLabel(tagKey)) + '</span>'
        + '<span class="selected-filter-remove" aria-hidden="true">\u00d7</span>'
        + '</button>';
    }
    return '<div class="selected-filter-strip" role="group" aria-label="Selected filters">'
      + '<span class="selected-filter-label">Selected filters</span>'
      + chips
      + '<button class="selected-filter-clear" type="button" data-action="clear-filters">Clear all</button>'
      + '</div>';
  }

  _renderPageControlStrip() {
    if (this._multiSelectMode) {
      return this._renderMultiSelectStrip('');
    }
    if (this._browserScope === "working") {
      return ''
        + '<div class="page-control-strip">'
        + '  <div class="toolbar-group display-group">'
        + '    <button class="toolbar-icon-btn refresh-btn' + (this._refreshSpin ? ' spinning' : '') + '" type="button" data-action="refresh-page" aria-label="Refresh working projection" title="Refresh" ' + (this._loading ? 'disabled' : '') + '><ha-icon icon="mdi:refresh"></ha-icon></button>'
        + '    <button class="toolbar-btn" type="button" data-action="open-working-folder">Open Working Files</button>'
        + '  </div>'
        + '</div>';
    }
    return ''
      + '<div class="page-control-strip">'
      + this._renderNavigationControls()
      + '<div class="toolbar-group density-group">'
      + '  <label for="mc-per-page">Items / Page</label>'
      + '  <select id="mc-per-page" class="control-input compact-select">'
      + '    <option value="12"' + (Number(this._pagination.per_page) === 12 ? ' selected' : '') + '>12</option>'
      + '    <option value="24"' + (Number(this._pagination.per_page) === 24 ? ' selected' : '') + '>24</option>'
      + '    <option value="48"' + (Number(this._pagination.per_page) === 48 ? ' selected' : '') + '>48</option>'
      + '    <option value="96"' + (Number(this._pagination.per_page) === 96 ? ' selected' : '') + '>96</option>'
      + '  </select>'
      + '</div>'
      + '<div class="toolbar-group display-group">'
      + this._renderViewModePicker()
      + '  <button class="toolbar-icon-btn media-toggle' + (this._showMedia ? ' active' : '') + '" type="button" data-action="toggle-show-media" aria-pressed="' + (this._showMedia ? 'true' : 'false') + '" title="' + (this._showMedia ? 'Hide media' : 'Show media') + '"><ha-icon icon="mdi:eye' + (this._showMedia ? '' : '-off') + '"></ha-icon></button>'
      + '  <button class="toolbar-icon-btn refresh-btn' + (this._refreshSpin ? ' spinning' : '') + '" type="button" data-action="refresh-page" aria-label="Refresh results" title="Refresh" ' + (this._loading ? 'disabled' : '') + '><ha-icon icon="mdi:refresh"></ha-icon></button>'
      + '  <button class="toolbar-icon-btn ms-toggle" type="button" data-action="toggle-multi-select" aria-label="Multi-select" title="Multi-select"><ha-icon icon="mdi:checkbox-multiple-marked-outline"></ha-icon></button>'
      + '</div>'
      + '</div>';
  }

  _renderBottomMirrorStrip() {
    if (this._multiSelectMode) {
      return this._renderMultiSelectStrip(' bottom-mirror');
    }
    if (this._browserScope === "working") {
      return '';
    }
    return ''
      + '<div class="page-control-strip bottom-mirror">'
      + this._renderNavigationControls()
      + '<div class="toolbar-group density-group">'
      + '  <label for="mc-per-page-bottom">Items / Page</label>'
      + '  <select id="mc-per-page-bottom" class="control-input compact-select">'
      + '    <option value="12"' + (Number(this._pagination.per_page) === 12 ? ' selected' : '') + '>12</option>'
      + '    <option value="24"' + (Number(this._pagination.per_page) === 24 ? ' selected' : '') + '>24</option>'
      + '    <option value="48"' + (Number(this._pagination.per_page) === 48 ? ' selected' : '') + '>48</option>'
      + '    <option value="96"' + (Number(this._pagination.per_page) === 96 ? ' selected' : '') + '>96</option>'
      + '  </select>'
      + '</div>'
      + '</div>';
  }

  _renderMultiSelectStrip(extraClass) {
    var count = this._selectedModelRefs.size;
    var visible = this._getVisibleModelRefs().length;
    var selectAllLabel = count > 0 && count === visible ? 'Deselect All' : 'Select All' + (visible > 0 ? ' (' + String(visible) + ')' : '');
    var sourceOptions = [
      { id: 'local', label: 'Local' },
      { id: 'original', label: 'Original (My Design)' },
      { id: 'makerworld', label: 'MakerWorld' },
      { id: 'printables', label: 'Printables' },
      { id: 'thingiverse', label: 'Thingiverse' },
      { id: 'cults3d', label: 'Cults3D' },
      { id: 'thangs', label: 'Thangs' },
      { id: 'myminifactory', label: 'MyMiniFactory' },
      { id: 'other', label: 'Other…' },
    ];
    var sourceOptionsHtml = '<option value="" selected disabled>Set Source…</option>';
    for (var s = 0; s < sourceOptions.length; s++) {
      sourceOptionsHtml += '<option value="' + this._escapeHtml(sourceOptions[s].id) + '">' + this._escapeHtml(sourceOptions[s].label) + '</option>';
    }
    return ''
      + '<div class="page-control-strip multi-select-active' + extraClass + '">'
      + '  <span class="ms-count">' + this._escapeHtml(String(count) + ' of ' + String(visible) + ' selected') + '</span>'
      + '  <button class="bulk-btn" type="button" data-action="toggle-select-all-models">' + this._escapeHtml(selectAllLabel) + '</button>'
      + '  <button class="bulk-btn" type="button" data-action="bulk-pin-favorites">Pin Favorites</button>'
      + '  <button class="bulk-btn" type="button" data-action="bulk-unpin-favorites">Unpin Favorites</button>'
      + '  <button class="bulk-btn" type="button" data-action="bulk-archive"><ha-icon icon="mdi:archive-arrow-down-outline"></ha-icon> Archive</button>'
      + '  <button class="bulk-btn" type="button" data-action="bulk-unarchive"><ha-icon icon="mdi:archive-arrow-up-outline"></ha-icon> Unarchive</button>'
      + '  <select class="bulk-source-select" title="Set source for selected models">' + sourceOptionsHtml + '</select>'
      + '  <div class="ms-spacer"></div>'
      + '  <button class="bulk-btn exit" type="button" data-action="exit-multi-select"><ha-icon icon="mdi:close"></ha-icon> Exit</button>'
      + '</div>';
  }

  async _openIntakePopup(mode) {
    if (!this._hass) {
      return;
    }
    var nextMode = mode === "server" ? "server" : "browser";
    try {
      await this._callServiceWithResponse("input_select", "select_option", {
        entity_id: "input_select.intake_source_mode",
        option: nextMode,
      });
    } catch (_error) {
      // Continue opening popup even if helper update fails.
    }

    this._fireBrowserModEvent("browser_mod.popup", {
      size: "wide",
      dismissable: false,
      content: {
        type: "custom:model-catalog-intake-home-card",
        launch_wizard: nextMode,
      },
    });
  }

  _coerceWorkingCount(value) {
    var count = Number(value || 0);
    if (!Number.isFinite(count)) {
      return 0;
    }
    return Math.max(0, Math.floor(count));
  }

  _buildWorkingProjectionEntries(payload) {
    var rootPath = String(payload && payload.root_path || "").trim();
    var groups = Array.isArray(payload && payload.groups) ? payload.groups : [];
    var entries = [];

    for (var i = 0; i < groups.length; i++) {
      var group = groups[i] || {};
      var slug = String(group.slug || "").trim();
      var name = String(group.name || slug || "Working Folder").trim() || "Working Folder";
      if (!slug) {
        continue;
      }
      entries.push({
        projection_type: "working_folder",
        id: "working-folder:" + slug,
        slug: slug,
        name: name,
        file_count: this._coerceWorkingCount(group.file_count),
        size_bytes: this._coerceWorkingCount(group.size_bytes),
        count_3mf: this._coerceWorkingCount(group.count_3mf),
        has_modelmeta: !!group.has_modelmeta,
        has_readme: !!group.has_readme,
        last_seen_at: String(group.last_seen_at || "").trim(),
        folder_path: rootPath ? (rootPath + "/" + name) : name,
      });
    }

    var loose = payload && payload.loose && typeof payload.loose === "object" ? payload.loose : {};
    var looseCount = this._coerceWorkingCount(loose.file_count);
    if (looseCount > 0) {
      entries.push({
        projection_type: "working_loose",
        id: "working-folder:__loose__",
        slug: "__loose__",
        name: "(loose files)",
        file_count: looseCount,
        size_bytes: this._coerceWorkingCount(loose.size_bytes),
        count_3mf: 0,
        has_modelmeta: false,
        has_readme: false,
        last_seen_at: String(loose.last_seen_at || "").trim(),
        folder_path: rootPath,
      });
    }

    return entries;
  }

  _sortWorkingProjection(entries) {
    var list = Array.isArray(entries) ? entries.slice() : [];
    var sortKey = String(this._filters.sort || "recent").trim().toLowerCase();
    if (sortKey === "name") {
      list.sort(function (a, b) {
        return String(a.name || "").toLowerCase().localeCompare(String(b.name || "").toLowerCase());
      });
      return list;
    }
    if (sortKey === "common") {
      list.sort(function (a, b) {
        return Number(b.size_bytes || 0) - Number(a.size_bytes || 0);
      });
      return list;
    }
    list.sort(function (a, b) {
      var aTime = Date.parse(String(a.last_seen_at || ""));
      var bTime = Date.parse(String(b.last_seen_at || ""));
      var safeA = Number.isFinite(aTime) ? aTime : 0;
      var safeB = Number.isFinite(bTime) ? bTime : 0;
      if (safeA === safeB) {
        return String(a.name || "").toLowerCase().localeCompare(String(b.name || "").toLowerCase());
      }
      return safeB - safeA;
    });
    return list;
  }

  async _loadWorkingProjectionData(refresh) {
    var payload = await this._callServiceWithResponse("rest_command", "model_catalog_working_files_tree", {
      refresh: !!refresh,
    });
    this._workingProjectionRootPath = String(payload && payload.root_path || "").trim();
    var entries = this._buildWorkingProjectionEntries(payload);
    var q = String(this._filters.q || "").trim().toLowerCase();
    if (q) {
      entries = entries.filter(function (entry) {
        var haystack = String(entry.name || "") + "\n" + String(entry.slug || "") + "\n" + String(entry.folder_path || "");
        return haystack.toLowerCase().indexOf(q) >= 0;
      });
    }
    return this._sortWorkingProjection(entries);
  }

  async _loadAllModelSearchResults(requestPayload, firstPayload) {
    var initialPayload = firstPayload && typeof firstPayload === "object" ? firstPayload : {};
    var firstResults = Array.isArray(initialPayload.results) ? initialPayload.results.slice(0) : [];
    var pagination = initialPayload && initialPayload.pagination ? initialPayload.pagination : {};
    var totalPages = Math.max(1, Number(pagination.total_pages || 1) || 1);
    if (totalPages <= 1) {
      return firstResults;
    }

    var combined = firstResults.slice(0);
    for (var page = 2; page <= totalPages; page++) {
      var pagePayload = await this._searchModelsFast(Object.assign({}, requestPayload, { page: page }));
      var pageResults = Array.isArray(pagePayload && pagePayload.results) ? pagePayload.results : [];
      combined = combined.concat(pageResults);
    }
    return combined;
  }

  async _loadWorkingProjectionPage(refresh) {
    if (!this._hass) {
      return;
    }

    this._loading = true;
    this._error = "";
    this._refreshSpin = !!refresh;
    this._doRender();

    try {
      this._workingProjection = await this._loadWorkingProjectionData(refresh);
      this._results = [];
      this._pagination.page = 1;
      this._pagination.per_page = 96;
      this._pagination.total = this._workingProjection.length;
      this._pagination.total_pages = 1;
      this._visibilityCounts = { active: 0, archived: 0 };
      this._serverEntityTypeCounts = { model: 0, idea: 0 };
    } catch (error) {
      this._workingProjection = [];
      this._results = [];
      this._pagination.page = 1;
      this._pagination.total = 0;
      this._pagination.total_pages = 1;
      this._error = error && error.message ? String(error.message) : "Could not load Working Files projection.";
    } finally {
      this._loading = false;
      this._refreshSpin = false;
      this._renderNow();
    }
  }

  _renderWorkingFolderCard(entry) {
    var name = String(entry && entry.name || "Working Folder").trim() || "Working Folder";
    var slug = String(entry && entry.slug || "").trim();
    var folderPath = String(entry && entry.folder_path || "").trim();
    var fileCount = this._coerceWorkingCount(entry && entry.file_count);
    var modelCount = this._coerceWorkingCount(entry && entry.count_3mf);
    var sizeBytes = this._coerceWorkingCount(entry && entry.size_bytes);
    var hasSidecar = !!(entry && (entry.has_modelmeta || entry.has_readme));
    var relativeLabel = this._relativeTimeLabel(String(entry && entry.last_seen_at || "").trim());
    var loose = String(entry && entry.projection_type || "") === "working_loose";
    if (this._viewMode === "media") {
      return ''
        + '<article class="model-card view-media working-folder-card" tabindex="0" role="button" data-action="open-working-folder" data-folder-slug="' + this._escapeHtml(slug) + '" aria-label="Open Working Files for ' + this._escapeHtml(name) + '">'
        + '  <div class="thumb-wrap media-wrap">'
        + '    <div class="media-preview working-thumb media-working-thumb">'
        + '      <ha-icon icon="' + this._escapeHtml(loose ? 'mdi:file-multiple-outline' : 'mdi:folder-cog-outline') + '"></ha-icon>'
        + '    </div>'
        + '  </div>'
        + '  <div class="body media-body">'
        + '    <div class="media-title-row">'
        + '      <div class="media-title-block">'
        + '        <h3 class="title">' + this._escapeHtml(name) + '</h3>'
        + '        <div class="subtle-line">'
        + this._renderModelTagChip('Working Files', 'subtle-chip')
        + (hasSidecar ? this._renderModelTagChip('Sidecar', 'signal-chip') : this._renderModelTagChip('No sidecar', 'subtle-chip'))
        + '        </div>'
        + '      </div>'
        + '    </div>'
        + '    <div class="metrics media-metrics">'
        + this._renderModelMetric('Files', fileCount)
        + this._renderModelMetric('3MF', modelCount)
        + this._renderModelMetric('Size', this._formatBytes(sizeBytes))
        + '    </div>'
        + '    <div class="media-footer-row">'
        + '      <div class="tags">'
        + this._renderModelTagChip('Updated ' + relativeLabel, 'subtle-chip')
        + (folderPath ? this._renderModelTagChip(folderPath, 'subtle-chip source-chip') : '')
        + '      </div>'
        + '      <div class="media-actions">'
        + '        <button class="toolbar-btn" type="button" data-action="open-working-folder" data-folder-slug="' + this._escapeHtml(slug) + '">Open Working Files</button>'
        + (loose || !folderPath ? '' : '<button class="toolbar-btn ghost" type="button" data-action="open-working-intake" data-folder-path="' + this._escapeHtml(folderPath) + '">Run Intake</button>')
        + '      </div>'
        + '    </div>'
        + '  </div>'
        + '</article>';
    }
    if (this._viewMode === "compact") {
      return ''
        + '<article class="model-card view-compact working-folder-card" tabindex="0" role="button" data-action="open-working-folder" data-folder-slug="' + this._escapeHtml(slug) + '" aria-label="Open Working Files for ' + this._escapeHtml(name) + '">'
        + '  <div class="thumb-wrap compact-wrap">'
        + '    <div class="thumb working-thumb compact-working-thumb">'
        + '      <ha-icon icon="' + this._escapeHtml(loose ? 'mdi:file-multiple-outline' : 'mdi:folder-cog-outline') + '"></ha-icon>'
        + '    </div>'
        + '  </div>'
        + '  <div class="body compact-main">'
        + '    <div class="compact-title-row">'
        + '      <h3 class="title">' + this._escapeHtml(name) + '</h3>'
        + '    </div>'
        + '    <div class="subtle-line">'
        + this._renderModelTagChip('Working Files', 'subtle-chip')
        + (hasSidecar ? this._renderModelTagChip('Sidecar', 'signal-chip') : this._renderModelTagChip('No sidecar', 'subtle-chip'))
        + '    </div>'
        + '  </div>'
        + '  <div class="body compact-full">'
        + '    <div class="metrics compact-metrics">'
        + this._renderModelMetric('Files', fileCount)
        + this._renderModelMetric('3MF', modelCount)
        + this._renderModelMetric('Size', this._formatBytes(sizeBytes))
        + '    </div>'
        + '    <div class="compact-tags-row">'
        + this._renderModelTagChip('Updated ' + relativeLabel, 'subtle-chip')
        + (folderPath ? this._renderModelTagChip(folderPath, 'subtle-chip source-chip') : '')
        + '    </div>'
        + '  </div>'
        + '</article>';
    }
    return ''
      + '<article class="model-card view-list working-folder-card" tabindex="0" role="button" data-action="open-working-folder" data-folder-slug="' + this._escapeHtml(slug) + '" aria-label="Open Working Files for ' + this._escapeHtml(name) + '">'
      + '  <div class="thumb-wrap list-wrap">'
      + '    <div class="thumb list-thumb working-thumb">'
      + '      <ha-icon icon="' + this._escapeHtml(loose ? 'mdi:file-multiple-outline' : 'mdi:folder-cog-outline') + '"></ha-icon>'
      + '    </div>'
      + '  </div>'
      + '  <div class="body list-body">'
      + '    <div class="list-top-row">'
      + '      <div class="list-title-block">'
      + '        <h3 class="title">' + this._escapeHtml(name) + '</h3>'
      + '        <div class="subtle-line">'
      + this._renderModelTagChip('Working Files projection', 'subtle-chip')
      + (hasSidecar ? this._renderModelTagChip('Sidecar', 'signal-chip') : this._renderModelTagChip('No sidecar', 'subtle-chip'))
      + '        </div>'
      + '      </div>'
      + '    </div>'
      + '    <div class="metrics list-metrics">'
      + this._renderModelMetric('Files', fileCount)
      + this._renderModelMetric('3MF', modelCount)
      + this._renderModelMetric('Size', this._formatBytes(sizeBytes))
      + '    </div>'
      + '    <div class="list-bottom-row">'
      + '      <div class="tags">'
      + this._renderModelTagChip('Updated ' + relativeLabel, 'subtle-chip')
      + (folderPath ? this._renderModelTagChip(folderPath, 'subtle-chip source-chip') : '')
      + '      </div>'
      + '      <div class="compact-file-kinds list-file-kinds">'
      + '        <button class="toolbar-btn" type="button" data-action="open-working-folder" data-folder-slug="' + this._escapeHtml(slug) + '">Open Working Files</button>'
      + (loose || !folderPath ? '' : '<button class="toolbar-btn ghost" type="button" data-action="open-working-intake" data-folder-path="' + this._escapeHtml(folderPath) + '">Run Intake</button>')
      + '      </div>'
      + '    </div>'
      + '  </div>'
      + '</article>';
  }

  _buildMixedCatalogEntries(models, workingEntries) {
    var mixed = [];
    var modelRows = Array.isArray(models) ? models : [];
    var workingRows = Array.isArray(workingEntries) ? workingEntries : [];
    for (var i = 0; i < modelRows.length; i++) {
      mixed.push({ kind: 'model', order: i, data: modelRows[i] });
    }
    for (var j = 0; j < workingRows.length; j++) {
      mixed.push({ kind: 'working', order: j, data: workingRows[j] });
    }
    return mixed;
  }

  _sortMixedCatalogEntries(entries) {
    var list = Array.isArray(entries) ? entries.slice(0) : [];
    var sortKey = String(this._filters.sort || 'recent').trim().toLowerCase();
    var entryName = function (entry) {
      return String(entry && entry.data && entry.data.name || '').trim().toLowerCase();
    };
    var entryTimestamp = function (entry) {
      var data = entry && entry.data ? entry.data : {};
      var ranking = data && data.ranking && typeof data.ranking === 'object' ? data.ranking : {};
      var value = entry && entry.kind === 'working'
        ? String(data.last_seen_at || '').trim()
        : String(data.last_printed_at || ranking.last_printed_at || '').trim();
      var parsed = Date.parse(value);
      return Number.isFinite(parsed) ? parsed : 0;
    };
    var entryCommon = function (entry) {
      var data = entry && entry.data ? entry.data : {};
      var ranking = data && data.ranking && typeof data.ranking === 'object' ? data.ranking : {};
      return entry && entry.kind === 'working'
        ? Number(data.size_bytes || 0) || 0
        : Number(ranking.common_score || 0) || 0;
    };
    var entryFrequent = function (entry) {
      var data = entry && entry.data ? entry.data : {};
      var ranking = data && data.ranking && typeof data.ranking === 'object' ? data.ranking : {};
      return entry && entry.kind === 'working' ? 0 : (Number(ranking.frequent_score || 0) || 0);
    };

    if (sortKey === 'name') {
      list.sort(function (a, b) {
        return entryName(a).localeCompare(entryName(b));
      });
      return list;
    }
    if (sortKey === 'common') {
      list.sort(function (a, b) {
        var delta = entryCommon(b) - entryCommon(a);
        return delta || entryName(a).localeCompare(entryName(b));
      });
      return list;
    }
    if (sortKey === 'frequent') {
      list.sort(function (a, b) {
        var delta = entryFrequent(b) - entryFrequent(a);
        if (delta) {
          return delta;
        }
        var timeDelta = entryTimestamp(b) - entryTimestamp(a);
        return timeDelta || entryName(a).localeCompare(entryName(b));
      });
      return list;
    }
    if (sortKey === 'best') {
      list.sort(function (a, b) {
        if (a.kind !== b.kind) {
          return a.kind === 'model' ? -1 : 1;
        }
        if (a.kind === 'model') {
          return Number(a.order || 0) - Number(b.order || 0);
        }
        var workingTimeDelta = entryTimestamp(b) - entryTimestamp(a);
        return workingTimeDelta || entryName(a).localeCompare(entryName(b));
      });
      return list;
    }
    list.sort(function (a, b) {
      var delta = entryTimestamp(b) - entryTimestamp(a);
      return delta || entryName(a).localeCompare(entryName(b));
    });
    return list;
  }

  _renderCatalogEntryCard(entry) {
    if (entry && entry.kind === 'working') {
      return this._renderWorkingFolderCard(entry.data);
    }
    return this._renderModelCard(entry && entry.data ? entry.data : entry);
  }

  _currentDisplayEntries() {
    if (this._browserScope === "collections") {
      return this._collectionBrowse && Array.isArray(this._collectionBrowse.items) ? this._collectionBrowse.items : [];
    }
    var visibleResults = this._filteredResultsForScope();
    var includeWorkingInModels = this._browserScope === "models" && !!(this._typeFilters && this._typeFilters.working);
    var visibleWorkingProjection = includeWorkingInModels ? (Array.isArray(this._workingProjection) ? this._workingProjection : []) : [];
    if (!includeWorkingInModels) {
      return this._buildMixedCatalogEntries(visibleResults, []);
    }
    var mixed = this._sortMixedCatalogEntries(this._buildMixedCatalogEntries(visibleResults, visibleWorkingProjection));
    var perPage = Math.max(1, Number(this._pagination.per_page || 12) || 12);
    var page = Math.max(1, Number(this._pagination.page || 1) || 1);
    var start = Math.max(0, (page - 1) * perPage);
    return mixed.slice(start, start + perPage);
  }

  _renderWorkingProjectionCards() {
    var rows = Array.isArray(this._workingProjection) ? this._workingProjection : [];
    if (!rows.length) {
      return '<div class="state-row">No Working Files folders match the current search.</div>';
    }
    return rows.map(this._renderWorkingFolderCard.bind(this)).join('');
  }

  async _openWorkingFilesWorkspace(folderSlug) {
    var slug = String(folderSlug || "").trim();
    if (slug) {
      try {
        window.__modelCatalogWorkingFocusSlug = slug;
      } catch (_error) {
      }
      try {
        window.dispatchEvent(new CustomEvent('model-catalog-working-focus', {
          detail: { folder_slug: slug },
          bubbles: true,
          composed: true,
        }));
      } catch (_eventError) {
      }
    }

    var shared = window.ModelCatalogIntakeShared;
    if (shared && typeof shared.selectInputOption === "function" && this._hass) {
      try {
        await shared.selectInputOption(this._hass, "input_select.model_catalog_workspace_view", "working");
        return;
      } catch (_sharedError) {
      }
    }

    if (this._hass) {
      try {
        await this._callServiceWithResponse("input_select", "select_option", {
          entity_id: "input_select.model_catalog_workspace_view",
          option: "working",
        });
      } catch (_serviceError) {
      }
    }
  }

  _launchWorkingFolderIntake(folderPath) {
    var normalizedPath = String(folderPath || "").trim();
    if (!normalizedPath) {
      return;
    }
    var launchOptions = { mode: "server", rootKind: "working", startPath: normalizedPath };
    try {
      window.__modelCatalogPendingIntakeLaunch = launchOptions;
    } catch (_pendingError) {
    }
    try {
      window.dispatchEvent(new CustomEvent('model-catalog-intake-launch', {
        detail: launchOptions,
        bubbles: true,
        composed: true,
      }));
    } catch (_dispatchError) {
    }
    var shared = window.ModelCatalogIntakeShared;
    var selectFn = shared && shared.selectInputOption;
    if (typeof selectFn === "function" && this._hass) {
      selectFn(this._hass, 'input_select.model_catalog_workspace_view', 'intake');
    }
  }

  _renderModelCard(model) {
    var name = String(model.name || "Unnamed Model");
    var creator = String(model.creator_name || "Unknown Creator");
    var collections = Array.isArray(model.collection_names) ? model.collection_names : [];
    var rawTags = [];
    if (Array.isArray(model.keyword_names)) {
      rawTags = rawTags.concat(model.keyword_names);
    }
    if (Array.isArray(model.tags)) {
      rawTags = rawTags.concat(model.tags);
    }
    var linkedCount = Number(model.linked_archive_count || 0) || 0;
    var modelRef = this._modelRef(model);
    var localModelId = this._localModelIdForModel(model);
    var entityType = this._entityTypeForModel(model);
    var entityTypeBadgeText = this._entityTypeBadgeLabel(entityType);
    var entityTypeBadge = entityTypeBadgeText
      ? '<span class="entity-type-pill ' + this._escapeHtml(entityType) + '">' + this._escapeHtml(entityTypeBadgeText) + '</span>'
      : '';
    var isArchived = String((structured && structured.catalog_signals && structured.catalog_signals.catalog_visibility) || model.catalog_visibility || "").trim().toLowerCase() === "archived";
    var archivedBadge = isArchived
      ? '<span class="archived-pill"><ha-icon icon="mdi:archive-outline"></ha-icon>Archived</span>'
      : '';
    var actionMenuOpen = this._activeActionMenu === modelRef;

    var ranking = model && model.ranking && typeof model.ranking === "object" ? model.ranking : {};
    var recent = Number(ranking.recent_score || 0);
    var frequent = Number(ranking.frequent_score || 0);
    var common = Number(ranking.common_score || 0);

    var fields = model && model.custom_fields && typeof model.custom_fields === "object" ? model.custom_fields : {};
    var structured = model && model.structured_metadata && typeof model.structured_metadata === "object" ? model.structured_metadata : {};
    var provenance = structured && structured.provenance && typeof structured.provenance === "object" ? structured.provenance : {};
    var publishing = structured && structured.publishing && typeof structured.publishing === "object" ? structured.publishing : {};
    var catalogSignals = structured && structured.catalog_signals && typeof structured.catalog_signals === "object" ? structured.catalog_signals : {};
    if (Array.isArray(fields.keyword_names)) {
      rawTags = rawTags.concat(fields.keyword_names);
    }
    if (Array.isArray(fields.tags)) {
      rawTags = rawTags.concat(fields.tags);
    }
    var fieldTagsText = String(fields.tags || "").trim();
    if (fieldTagsText && !Array.isArray(fields.tags)) {
      rawTags = rawTags.concat(fieldTagsText.split(/[,;|]/));
    }
    var seenTags = {};
    var tags = [];
    for (var t = 0; t < rawTags.length; t++) {
      var normalizedTag = String(rawTags[t] || "").trim();
      if (!normalizedTag) {
        continue;
      }
      var tagKey = normalizedTag.toLowerCase();
      if (seenTags[tagKey]) {
        continue;
      }
      seenTags[tagKey] = true;
      tags.push(normalizedTag);
    }
    var queueStateInfo = this._unifiedQueueByModelRef[modelRef] || null;
    var preferred = queueStateInfo && queueStateInfo.preferred ? queueStateInfo.preferred : null;
    var queueStatus = preferred ? this._queueStateToRibbonState(preferred.state) : "none";
    var creatorChip = this._renderModelTagChip("By " + creator, "subtle-chip");
    var originType = String(model.origin_type || provenance.origin_type || fields.origin_type || "custom_unique").trim().toLowerCase();
    var sourcePlatform = String(model.source_platform || provenance.source_platform || fields.source_platform || "").trim().toLowerCase();
    var sourceDownloadUrl = String(model.source_download_url || provenance.source_download_url || fields.source_download_url || "").trim();
    var rawPublishedTo = Array.isArray(model.published_to) && model.published_to.length
      ? model.published_to
      : (Array.isArray(publishing.published_to) ? publishing.published_to : (Array.isArray(fields.published_to) ? fields.published_to : []));
    var publishedTo = rawPublishedTo.map(function (value) {
      return String(value || "").trim().toLowerCase();
    }).filter(function (value) {
      return !!value;
    });
    var publishedUrlMap = model && model.published_urls && typeof model.published_urls === "object"
      ? model.published_urls
      : (publishing && publishing.published_urls && typeof publishing.published_urls === "object" ? publishing.published_urls : {});
    var modelFavorite = this._coerceBoolish(model.model_favorite);
    if (modelFavorite === null) {
      modelFavorite = this._coerceBoolish(catalogSignals.model_favorite);
    }
    if (modelFavorite === null) {
      modelFavorite = this._coerceBoolish(fields.model_favorite);
    }
    var collectionLimit = this._viewMode === "compact" ? 2 : 3;
    var collectionChips = collections.slice(0, collectionLimit).map(function (collection) {
      return this._renderModelTagChip(collection, "subtle-chip");
    }.bind(this)).join("");
    var hiddenCollectionCount = Math.max(0, collections.length - collectionLimit);
    var tagLimit = this._viewMode === "compact" ? 3 : 4;
    var visibleTags = tags.slice(0, tagLimit);
    var hiddenTagCount = Math.max(0, tags.length - visibleTags.length);
    var tagMarkup = visibleTags.map(function (tag) {
      return this._renderModelTagChip(tag, "tag-chip");
    }.bind(this)).join("") + (hiddenTagCount ? this._renderModelTagChip("… +" + String(hiddenTagCount), "tag-chip") : "");
    if (!tagMarkup) {
      tagMarkup = this._renderModelTagChip("No tags", "subtle-chip");
    }
    var mediaUrls = this._modelMediaUrls(model);
    var mediaCount = mediaUrls.length;
    var mediaIndex = this._currentModelMediaIndex(modelRef, mediaCount || 1);
    var mediaUrl = mediaCount > 0 ? mediaUrls[mediaIndex] : "";
    if (!mediaUrl && entityType === "idea") {
      mediaUrl = this._ideaPlaceholderUrlForModel(model, modelRef);
    }
    var detail = modelRef ? this._modelDetailCache[modelRef] : null;
    var fileKindCounts = this._deriveFileKindCounts(model, structured, fields, detail);
    var fileKindChipMarkup = this._renderFileKindChipRow(fileKindCounts);
    var lastPrintedAt = String(model.last_printed_at || ranking.last_printed_at || "").trim();
    var successRatePct = Number(model.success_rate_pct);
    if (!Number.isFinite(successRatePct)) {
      var rankingSuccess = Number(ranking.success_rate_score);
      if (Number.isFinite(rankingSuccess)) {
        successRatePct = rankingSuccess > 1 ? rankingSuccess : rankingSuccess * 100;
      }
    }
    var successLabel = Number.isFinite(successRatePct) ? (String(Math.round(Math.max(0, Math.min(100, successRatePct)))) + "%") : "--";

    // Hydrate missing preview media in compact view, but patch cards in place to
    // avoid whole-grid repaint churn.  Also load detail when file-kind counts
    // are empty so uploaded-photo and embedded-image chips can be patched in.
    // When uploaded_photos exist but detail is not cached, also load detail so
    // the post-processing block can produce an accurate count that includes
    // embedded thumbnails alongside the uploaded photos.
    // When the model has no preview_url and detail hasn't been fetched yet,
    // also load detail – the detail may contain file-based thumbnails (e.g.
    // embedded 3MF previews) that should take precedence over fallback
    // source-URL images.
    var fileKindTotal = fileKindCounts.model_files + fileKindCounts.images + fileKindCounts.other;
    var hasUploadedPhotosNoDetail = !detail && fields && Array.isArray(fields.uploaded_photos) && fields.uploaded_photos.length > 0;
    var needsDetailForPreview = this._showMedia && this._viewMode === "compact" && !detail && mediaCount > 0 && !String(model.preview_url || "").trim();
    if ((this._showMedia && ((this._viewMode === "compact" && mediaCount === 0) || this._viewMode === "media")) || fileKindTotal === 0 || hasUploadedPhotosNoDetail || needsDetailForPreview) {
      this._loadModelMedia(model);
    }

    var previewHtml = mediaUrl
      ? (
        this._isThumbnailLazyEndpoint(mediaUrl)
          ? (function () {
              // If a previous fetch resolved this lazy URL in-session, render with src
              // immediately so re-renders don't show a blank flash before the observer reattaches.
              var cachedObjectUrl = getCachedThumbnailObjectUrl(String(mediaUrl));
              if (cachedObjectUrl) {
                return '<img src="' + this._escapeHtml(String(cachedObjectUrl)) + '" alt="' + this._escapeHtml(name) + ' preview" loading="lazy" decoding="async">';
              }
              return '<img data-thumbnail-lazy-url="' + this._escapeHtml(String(mediaUrl)) + '" alt="' + this._escapeHtml(name) + ' preview" loading="lazy" decoding="async">';
            }).call(this)
          : '<img src="' + this._escapeHtml(String(mediaUrl)) + '" alt="' + this._escapeHtml(name) + ' preview" loading="lazy" decoding="async">'
      )
      : '<div class="thumb-empty"><ha-icon icon="mdi:cube-outline"></ha-icon><div class="thumb-empty-text">No preview</div></div>';

    var isLocalModel = String(model.authority || "").trim() === "local";
    var deleteButton = isLocalModel
      ? '  <button class="advanced-action danger" type="button" data-action="delete-model" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '"><ha-icon icon="mdi:trash-can-outline"></ha-icon><span>Delete model</span></button>'
      : '';
    var promotionActions = '';
    var promotionTargets = this._promotionTargets(entityType);
    if (localModelId && promotionTargets.length) {
      promotionActions = '  <div class="advanced-group-label">Promote</div>';
      for (var p = 0; p < promotionTargets.length; p++) {
        var promoteTarget = promotionTargets[p];
        var promoteLabel = "Promote to Model";
        promotionActions += '  <button class="advanced-action" type="button" data-action="promote-entity" data-local-model-id="' + this._escapeHtml(localModelId) + '" data-from-entity-type="' + this._escapeHtml(entityType) + '" data-to-entity-type="' + this._escapeHtml(promoteTarget) + '" data-model-name="' + this._escapeHtml(name) + '"><ha-icon icon="mdi:arrow-up-bold-circle-outline"></ha-icon><span>' + this._escapeHtml(promoteLabel) + '</span></button>';
      }
    }
    var advancedActions = ''
      + '<div class="advanced-menu-shell">'
      + '  <button class="icon-action advanced" type="button" data-action="toggle-actions" data-model-ref="' + this._escapeHtml(modelRef) + '" aria-label="Open advanced actions" aria-expanded="' + (actionMenuOpen ? 'true' : 'false') + '"><ha-icon icon="mdi:dots-horizontal"></ha-icon></button>'
      + '<div class="advanced-menu' + (actionMenuOpen ? ' is-open' : '') + '" aria-hidden="' + (actionMenuOpen ? 'false' : 'true') + '">'
          + '  <button class="advanced-action primary" type="button" data-action="view-model-detail" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '"><ha-icon icon="mdi:text-box-search-outline"></ha-icon><span>View details</span></button>'
          + '  <button class="advanced-action primary" type="button" data-action="open-model-viewer" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '"><ha-icon icon="mdi:cube-scan"></ha-icon><span>Open 3D viewer</span></button>'
          + promotionActions
          + deleteButton
          + '</div>'
      + '</div>';

    var queueRibbonClass = "";
    var queueBorderStyle = "";
    if (queueStatus !== "none") {
      queueRibbonClass = " is-in-queue";
      queueBorderStyle = ' style="--queue-border-color:' + this._queueStateBorderColor(queueStatus) + '"';
    }

    var sourceLabel = sourcePlatform ? ("Source: " + this._platformDisplayLabel(sourcePlatform)) : "Source: Not set";
    var sourceChipHtml = sourceDownloadUrl
      ? '<button class="chip subtle-chip source-chip" type="button" data-action="open-model" data-url="' + this._escapeHtml(sourceDownloadUrl) + '">' + this._escapeHtml(sourceLabel) + '</button>'
      : this._renderModelTagChip(sourceLabel, "subtle-chip source-chip");

    var publishedDestinationChips = publishedTo.slice(0, 3).map(function (platformId) {
      var destinationLabel = this._platformDisplayLabel(platformId);
      var destinationUrl = String(publishedUrlMap[platformId] || "").trim();
      if (destinationUrl) {
        return '<button class="chip publish-chip" type="button" data-action="open-model" data-url="' + this._escapeHtml(destinationUrl) + '">' + this._escapeHtml(destinationLabel) + '</button>';
      }
      return this._renderModelTagChip(destinationLabel, "publish-chip");
    }.bind(this)).join("");
    var hiddenDestinationCount = Math.max(0, publishedTo.length - 3);

    var favoriteButton = ''
      + '<button class="icon-action favorite-action' + (modelFavorite ? ' is-active' : '') + '" type="button" data-action="toggle-favorite" data-model-ref="' + this._escapeHtml(modelRef) + '" data-next-favorite="' + this._escapeHtml(modelFavorite ? 'false' : 'true') + '" aria-label="' + this._escapeHtml(modelFavorite ? 'Remove favorite' : 'Add favorite') + '">'
      + '  <ha-icon icon="' + this._escapeHtml(modelFavorite ? 'mdi:star' : 'mdi:star-outline') + '"></ha-icon>'
      + '</button>';
    // Always show Add to backlog; re-add option in advanced menu. Show count badge if entries exist.
    var queueEntryCount = queueStateInfo && queueStateInfo.count ? queueStateInfo.count : 0;
    var queueStatusClass = queueEntryCount > 0 ? ' has-queue-entries' : '';
    var queueCountBadge = queueEntryCount > 0 ? '<span class="queue-count-badge">' + this._escapeHtml(String(queueEntryCount)) + '</span>' : '';
    var queueButton = ''
      + '<button class="icon-action queue-action' + queueStatusClass + '" type="button" data-action="queue-add" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="Add to queue">'
      + '  <ha-icon icon="mdi:playlist-plus"></ha-icon>'
      + queueCountBadge
      + '</button>';

    var compactActionsHtml = ''
      + '<div class="compact-top-actions">'
      + '  <button class="icon-action viewer" type="button" data-action="open-model-viewer" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="Open 3D viewer"><ha-icon icon="mdi:cube-scan"></ha-icon></button>'
      + favoriteButton
      + queueButton
      + advancedActions
      + '</div>';

    var compactMainHtml = ''
      + '<div class="body compact-main">'
      + '  <div class="subtle-line">' + creatorChip + collectionChips + (hiddenCollectionCount ? this._renderModelTagChip('+' + String(hiddenCollectionCount) + ' more', 'subtle-chip') : '') + '</div>'
      + '  <div class="chip-row provenance-row">'
      + this._renderModelTagChip(this._originTypeLabel(originType), 'origin-chip')
      + sourceChipHtml
      + publishedDestinationChips
      + (hiddenDestinationCount ? this._renderModelTagChip('+' + String(hiddenDestinationCount), 'publish-chip') : '')
      + '  </div>'
      + '</div>';

    var compactFullHtml = ''
      + '<div class="body compact-full">'
      + '  <div class="compact-title-row">'
      + entityTypeBadge
      + '    <h3 class="title">' + archivedBadge + this._escapeHtml(name) + '</h3>'
      + '  </div>'
      + '  <div class="metrics compact-metrics">'
      + this._renderModelMetric('Prints', linkedCount)
      + this._renderModelMetric('Last printed', this._relativeTimeLabel(lastPrintedAt))
      + this._renderModelMetric('Success', successLabel)
      + '  </div>'
      + '  <div class="compact-tags-row">'
      + '    <div class="tags">' + tagMarkup + '</div>'
      + '    <div class="compact-file-kinds">' + fileKindChipMarkup + '</div>'
      + '  </div>'
      + '  <div class="compact-action-row">'
      + (sourceDownloadUrl ? '<button class="toolbar-btn" type="button" data-action="open-model" data-url="' + this._escapeHtml(sourceDownloadUrl) + '">Download</button>' : '')
      + '  </div>'
      + '</div>';

    var mediaBodyHtml = ''
      + '<div class="body media-body">'
      + '  <div class="media-title-row">'
      + entityTypeBadge
      + '    <h3 class="title">' + archivedBadge + this._escapeHtml(name) + '</h3>'
      + '  </div>'
      + '  <div class="subtle-line">' + creatorChip + collectionChips + (hiddenCollectionCount ? this._renderModelTagChip('+' + String(hiddenCollectionCount) + ' more', 'subtle-chip') : '') + '</div>'
      + '  <div class="chip-row provenance-row">'
      + this._renderModelTagChip(this._originTypeLabel(originType), 'origin-chip')
      + sourceChipHtml
      + publishedDestinationChips
      + (hiddenDestinationCount ? this._renderModelTagChip('+' + String(hiddenDestinationCount), 'publish-chip') : '')
      + '  </div>'
      + '  <div class="metrics media-metrics">'
      + this._renderModelMetric('Prints', linkedCount)
      + this._renderModelMetric('Last printed', this._relativeTimeLabel(lastPrintedAt))
      + this._renderModelMetric('Success', successLabel)
      + '  </div>'
      + '  <div class="media-footer-row">'
      + '    <div class="tags">' + tagMarkup + '</div>'
      + '    <div class="compact-file-kinds">' + fileKindChipMarkup + '</div>'
      + '  </div>'
      + '  <div class="media-actions-row">'
      + '    <div class="media-actions">'
      + (sourceDownloadUrl ? '<button class="toolbar-btn" type="button" data-action="open-model" data-url="' + this._escapeHtml(sourceDownloadUrl) + '">Download</button>' : '')
      + '    </div>'
      + '  </div>'
      + '</div>';

    var listBodyHtml = ''
      + '<div class="body list-body">'
      + '  <div class="list-top-row">'
      + '    <div class="list-title-block">'
      + entityTypeBadge
      + '      <h3 class="title">' + archivedBadge + this._escapeHtml(name) + '</h3>'
      + '      <div class="subtle-line">' + creatorChip + collectionChips + (hiddenCollectionCount ? this._renderModelTagChip('+' + String(hiddenCollectionCount) + ' more', 'subtle-chip') : '') + '</div>'
      + '    </div>'
      + '    <div class="list-action-stack">'
      + '      <div class="list-top-actions">'
      + '        <button class="icon-action viewer" type="button" data-action="open-model-viewer" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="Open 3D viewer"><ha-icon icon="mdi:cube-scan"></ha-icon></button>'
      + favoriteButton
      + queueButton
      + advancedActions
      + '      </div>'
      + '    </div>'
      + '  </div>'
      + '  <div class="chip-row provenance-row">'
      + this._renderModelTagChip(this._originTypeLabel(originType), 'origin-chip')
      + sourceChipHtml
      + (publishedDestinationChips || this._renderModelTagChip('Not published', 'subtle-chip'))
      + (hiddenDestinationCount ? this._renderModelTagChip('+' + String(hiddenDestinationCount), 'publish-chip') : '')
      + '  </div>'
      + '  <div class="list-metrics-shell">'
      + '    <div class="metrics list-metrics">'
      + this._renderModelMetric('Prints', linkedCount)
      + this._renderModelMetric('Last printed', this._relativeTimeLabel(lastPrintedAt))
      + this._renderModelMetric('Success', successLabel)
      + '    </div>'
      + '  </div>'
      + '  <div class="list-bottom-row">'
      + '    <div class="tags">' + tagMarkup + '</div>'
      + '    <div class="compact-file-kinds list-file-kinds">' + fileKindChipMarkup + '</div>'
      + '  </div>'
      + '</div>';

    if (this._viewMode === "media") {
      var cardAction = this._multiSelectMode ? "toggle-model-select" : "view-model-detail";
      return ''
        + '<article class="model-card view-media' + queueRibbonClass + (entityType === 'idea' ? ' is-idea' : '') + (isArchived ? ' is-archived' : '') + (this._isModelSelected(modelRef) ? ' is-selected' : '') + '"' + queueBorderStyle + ' tabindex="0" role="button" data-action="' + cardAction + '" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="' + (cardAction === 'toggle-model-select' ? 'Select ' : 'Open details for ') + this._escapeHtml(name) + '">'
        + '  <div class="thumb-wrap media-wrap">'
        + '    <div class="media-preview media-surface" data-model-ref="' + this._escapeHtml(modelRef) + '" data-gallery-count="' + this._escapeHtml(String(mediaCount)) + '">' + previewHtml + '</div>'
        + '    <div class="media-overlay">'
        + '      <div class="media-overlay-actions">'
        + '        <button class="icon-action viewer" type="button" data-action="open-model-viewer" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="Open 3D viewer"><ha-icon icon="mdi:cube-scan"></ha-icon></button>'
        + favoriteButton
        + advancedActions
        + '      </div>'
        + '    </div>'
        + (mediaCount > 1 ? '<div class="media-gallery-nav"><button class="icon-action" type="button" data-action="media-prev" data-model-ref="' + this._escapeHtml(modelRef) + '" data-gallery-count="' + this._escapeHtml(String(mediaCount)) + '" aria-label="Previous model image"><ha-icon icon="mdi:chevron-left"></ha-icon></button><span class="media-counter" data-model-ref="' + this._escapeHtml(modelRef) + '">' + this._escapeHtml(String(mediaIndex + 1) + ' / ' + String(mediaCount)) + '</span><button class="icon-action" type="button" data-action="media-next" data-model-ref="' + this._escapeHtml(modelRef) + '" data-gallery-count="' + this._escapeHtml(String(mediaCount)) + '" aria-label="Next model image"><ha-icon icon="mdi:chevron-right"></ha-icon></button></div>' : '')
        + '  </div>'
        + mediaBodyHtml
        + '</article>';
    }

    if (this._viewMode === "list") {
      var cardAction = this._multiSelectMode ? "toggle-model-select" : "view-model-detail";
      return ''
        + '<article class="model-card view-list' + queueRibbonClass + (entityType === 'idea' ? ' is-idea' : '') + (isArchived ? ' is-archived' : '') + (this._isModelSelected(modelRef) ? ' is-selected' : '') + '"' + queueBorderStyle + ' tabindex="0" role="button" data-action="' + cardAction + '" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="' + (cardAction === 'toggle-model-select' ? 'Select ' : 'Open details for ') + this._escapeHtml(name) + '">'
        + '  <div class="thumb-wrap list-wrap">'
        + '    <div class="thumb list-thumb">' + previewHtml + '</div>'
        + '  </div>'
        + listBodyHtml
        + '</article>';
    }

    var cardAction = this._multiSelectMode ? "toggle-model-select" : "view-model-detail";
    return ''
      + '<article class="model-card view-compact' + queueRibbonClass + (entityType === 'idea' ? ' is-idea' : '') + (isArchived ? ' is-archived' : '') + (this._isModelSelected(modelRef) ? ' is-selected' : '') + '"' + queueBorderStyle + ' tabindex="0" role="button" data-action="' + cardAction + '" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="' + (cardAction === 'toggle-model-select' ? 'Select ' : 'Open details for ') + this._escapeHtml(name) + '">'
      + '  <div class="thumb-wrap compact-wrap"><div class="thumb">' + previewHtml + '</div></div>'
      + compactMainHtml
      + compactActionsHtml
      + compactFullHtml
      + '</article>';
  }

  _renderCollectionCards() {
    var browse = this._collectionBrowse && typeof this._collectionBrowse === "object" ? this._collectionBrowse : null;
    var items = browse && Array.isArray(browse.items) ? browse.items.slice(0) : [];
    var breadcrumb = browse && Array.isArray(browse.breadcrumb) ? browse.breadcrumb : [];
    var currentNode = browse && browse.current_node && typeof browse.current_node === 'object' ? browse.current_node : null;
    var currentCollectionKey = this._selectedCollectionKey();
    var breadcrumbUpTarget = this._collectionBreadcrumbUpTarget(currentNode, currentCollectionKey);
    var breadcrumbHtml = "";
    if (!currentNode && currentCollectionKey !== '__unassigned__') {
      var syntheticUnassigned = this._buildSyntheticUnassignedCollectionNode(browse);
      if (syntheticUnassigned) {
        items.unshift({ kind: 'collection', data: syntheticUnassigned });
      }
    }
    if (breadcrumb.length) {
      var crumbParts = [];
      if (breadcrumbUpTarget) {
        crumbParts.push('<button class="toolbar-btn ghost collection-breadcrumb-up" type="button" data-action="select-left-nav-item" data-nav-key="' + this._escapeHtml(breadcrumbUpTarget.navKey) + '"><ha-icon icon="mdi:arrow-up-left"></ha-icon><span>' + this._escapeHtml(breadcrumbUpTarget.label) + '</span></button>');
      }
      crumbParts.push('<button class="toolbar-btn" type="button" data-action="select-left-nav-item" data-nav-key="all-models">All Collections</button>');
      for (var crumbIndex = 0; crumbIndex < breadcrumb.length; crumbIndex++) {
        var crumb = breadcrumb[crumbIndex] || {};
        crumbParts.push('<button class="toolbar-btn" type="button" data-action="select-left-nav-item" data-nav-key="collection:' + this._escapeHtml(String(crumb.collection_id || "").toLowerCase()) + '">' + this._escapeHtml(String(crumb.label || "Collection")) + '</button>');
      }
      breadcrumbHtml = '<div class="collection-breadcrumb">' + crumbParts.join('<span class="collection-breadcrumb-sep">/</span>') + '</div>';
    } else if (breadcrumbUpTarget) {
      breadcrumbHtml = '<div class="collection-breadcrumb"><button class="toolbar-btn ghost collection-breadcrumb-up" type="button" data-action="select-left-nav-item" data-nav-key="' + this._escapeHtml(breadcrumbUpTarget.navKey) + '"><ha-icon icon="mdi:arrow-up-left"></ha-icon><span>' + this._escapeHtml(breadcrumbUpTarget.label) + '</span></button></div>';
    }
    var headerHtml = this._renderCollectionBrowseHeader(browse, currentNode, currentCollectionKey);

    var cards = items.map(function (entry) {
      if (!entry || typeof entry !== "object") {
        return "";
      }
      if (entry.kind === "model") {
        return this._renderModelCard(entry.data || {});
      }
      var node = entry.data && typeof entry.data === "object" ? entry.data : {};
      return this._renderCollectionNodeCard(node);
    }.bind(this)).join("");

    if (!cards) {
      return breadcrumbHtml + headerHtml + this._renderCollectionBrowseEmptyState(browse, currentNode, currentCollectionKey);
    }
    return breadcrumbHtml + headerHtml + cards;
  }

  _renderCollectionBrowseHeader(browse, currentNode, currentCollectionKey) {
    var resultCounts = browse && browse.result_counts && typeof browse.result_counts === 'object' ? browse.result_counts : {};
    var collectionCount = Math.max(0, Number(resultCounts.collections || 0) || 0);
    var modelCount = Math.max(0, Number(resultCounts.models || 0) || 0);
    var title = 'Collections';
    var subtitle = 'Browse the hierarchy first, then open the current layer for direct models and recent activity.';
    var note = '';
    var stats = [
      this._renderCollectionHeaderStat('Collections', collectionCount),
      this._renderCollectionHeaderStat('Direct models', modelCount),
    ];
    if (currentNode) {
      var activity = currentNode.recent_print_activity && typeof currentNode.recent_print_activity === 'object' ? currentNode.recent_print_activity : {};
      title = String(currentNode.label || currentNode.name || currentNode.path || 'Collection').trim() || 'Collection';
      subtitle = String(currentNode.path || title).trim();
      if (Number(currentNode.model_count_direct || 0) <= 0 && Number(currentNode.child_collection_count || 0) > 0) {
        note = 'This layer currently organizes into sub-collections only.';
      } else if (Number(currentNode.model_count_total || 0) <= 0) {
        note = 'This collection is empty right now.';
      }
      stats = [
        this._renderCollectionHeaderStat('Total models', currentNode.model_count_total || 0),
        this._renderCollectionHeaderStat('Direct models', currentNode.model_count_direct || 0),
        this._renderCollectionHeaderStat('Sub-collections', currentNode.child_collection_count || 0),
        this._renderCollectionHeaderStat('Recent prints', activity.printed_model_count || 0),
      ];
    } else if (currentCollectionKey === '__unassigned__') {
      title = 'No Collection';
      subtitle = 'Operational bucket for models that are not assigned to any curated collection.';
      note = modelCount > 0 ? 'Assign these from the popup collection editor when they are ready to be filed.' : 'No unassigned models match the current filters.';
      stats = [
        this._renderCollectionHeaderStat('Models', modelCount),
        this._renderCollectionHeaderStat('Collections', collectionCount),
      ];
    }
    return ''
      + '<section class="collection-browser-header' + (currentCollectionKey === '__unassigned__' ? ' system-bucket' : '') + '">'
      + '  <div class="collection-browser-header-copy">'
      + '    <div class="collection-browser-header-kicker">' + this._escapeHtml(currentCollectionKey === '__unassigned__' ? 'System Bucket' : (currentNode ? 'Collection View' : 'Collections Overview')) + '</div>'
      + '    <div class="collection-browser-header-title">' + this._escapeHtml(title) + '</div>'
      + '    <div class="collection-browser-header-subtitle">' + this._escapeHtml(subtitle) + '</div>'
      + (note ? '<div class="collection-browser-header-note">' + this._escapeHtml(note) + '</div>' : '')
      + '  </div>'
      + '  <div class="collection-browser-header-stats">' + stats.join('') + '</div>'
      + '</section>';
  }

  _renderCollectionHeaderStat(label, value) {
    return '<div class="collection-header-stat"><div class="collection-header-stat-label">' + this._escapeHtml(String(label || '')) + '</div><div class="collection-header-stat-value">' + this._escapeHtml(String(Math.max(0, Number(value || 0) || 0))) + '</div></div>';
  }

  _renderCollectionBrowseEmptyState(browse, currentNode, currentCollectionKey) {
    if (currentCollectionKey === '__unassigned__') {
      return '<div class="state-row">No unassigned models match the current filters right now.</div>';
    }
    if (currentNode) {
      if (Number(currentNode.child_collection_count || 0) > 0 && Number(currentNode.model_count_direct || 0) <= 0) {
        return '<div class="state-row">No direct models are filed at this level yet. Browse the sub-collections above.</div>';
      }
      if (Number(currentNode.model_count_total || 0) > 0 && Number(currentNode.preview_model_count || 0) <= 0) {
        return '<div class="state-row">Models exist in this collection, but none currently expose preview media.</div>';
      }
      return '<div class="state-row">This collection has no visible sub-collections or direct models for the active filters.</div>';
    }
    return '<div class="state-row">No collections found for current filters.</div>';
  }

  _renderCollectionActionFeedback() {
    var feedback = this._collectionActionFeedback && typeof this._collectionActionFeedback === 'object' ? this._collectionActionFeedback : null;
    if (!feedback || !feedback.message) {
      return '';
    }
    return ''
      + '<div class="collection-feedback-toast ' + this._escapeHtml(feedback.kind || 'success') + '" role="status" aria-live="polite">'
      + '  <div class="collection-feedback-copy">' + this._escapeHtml(String(feedback.message || '')) + '</div>'
      + '  <button class="collection-feedback-dismiss" type="button" data-action="dismiss-collection-feedback" aria-label="Dismiss feedback">✕</button>'
      + '</div>';
  }

  _renderCollectionActionDialog() {
    var dialog = this._collectionActionDialog && typeof this._collectionActionDialog === 'object' ? this._collectionActionDialog : null;
    if (!dialog || !dialog.open) {
      return '';
    }
    var mode = String(dialog.mode || '').trim().toLowerCase();
    var isDelete = mode === 'delete';
    var submitLabel = this._collectionDialogSubmitLabel(mode);
    var bodyHtml = '';
    if (mode === 'rename') {
      bodyHtml = ''
        + '<div class="collection-action-note">Update the display name for this collection. Its hierarchy path will refresh after save.</div>'
        + '<label class="collection-action-field"><span>Name</span><input class="collection-action-input" type="text" maxlength="255" value="' + this._escapeHtml(dialog.name) + '" placeholder="Collection name"></label>';
    } else if (mode === 'move') {
      bodyHtml = ''
        + '<div class="collection-action-note">Choose a new parent for this collection. Invalid destinations are filtered out to avoid hierarchy loops.</div>'
        + '<label class="collection-action-field"><span>Parent collection</span><select class="collection-action-select">'
        + dialog.options.map(function (option) {
            var value = String(option && option.value || '');
            var label = String(option && option.label || value || 'Root');
            return '<option value="' + this._escapeHtml(value) + '"' + (String(dialog.selectedParentId || '') === value ? ' selected' : '') + '>' + this._escapeHtml(label) + '</option>';
          }.bind(this)).join('')
        + '</select></label>';
    } else {
      bodyHtml = ''
        + '<div class="collection-action-danger-note">Delete this collection only if it is truly no longer needed. The server still blocks deletion when members or child collections remain.</div>'
        + '<div class="collection-action-summary"><strong>' + this._escapeHtml(dialog.label) + '</strong><span>' + this._escapeHtml(dialog.path) + '</span></div>';
    }
    return ''
      + '<div class="collection-action-backdrop" data-action="close-collection-action-dialog">'
      + '  <div class="collection-action-dialog" role="dialog" aria-modal="true" aria-label="' + this._escapeHtml(this._collectionDialogTitle(mode)) + '">'
      + '    <div class="collection-action-header">'
      + '      <div><h3>' + this._escapeHtml(this._collectionDialogTitle(mode)) + '</h3><div class="collection-action-subtitle">' + this._escapeHtml(dialog.path || dialog.label) + '</div></div>'
      + '      <button class="modal-close-btn" type="button" data-action="close-collection-action-dialog" aria-label="Close">✕</button>'
      + '    </div>'
      + '    <div class="collection-action-body">'
      + bodyHtml
      + (dialog.error ? '<div class="collection-action-error">' + this._escapeHtml(dialog.error) + '</div>' : '')
      + '    </div>'
      + '    <div class="collection-action-footer">'
      + '      <button class="toolbar-btn ghost" type="button" data-action="close-collection-action-dialog"' + (dialog.submitting ? ' disabled' : '') + '>Cancel</button>'
      + '      <button class="toolbar-btn' + (isDelete ? ' collection-action-submit danger' : ' collection-action-submit') + '" type="button" data-action="submit-collection-action-dialog"' + (dialog.submitting ? ' disabled' : '') + '>' + this._escapeHtml(dialog.submitting ? 'Saving...' : submitLabel) + '</button>'
      + '    </div>'
      + '  </div>'
      + '</div>';
  }

  _formatCollectionDate(value) {
    var raw = String(value || '').trim();
    if (!raw) {
      return 'recently';
    }
    var parsed = new Date(raw);
    if (!Number.isFinite(parsed.getTime())) {
      return raw;
    }
    return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  _renderCollectionCoverMosaic(node) {
    var isSystemBucket = !!(node && node.is_system_bucket);
    var viewMode = this._normalizedViewMode(this._viewMode);
    if (isSystemBucket && viewMode !== 'list') {
      return this._renderSystemBucketCoverPile(node);
    }
    var coverImages = node && Array.isArray(node.cover_images) ? node.cover_images.slice(0, 4) : [];
    if (coverImages.length > 0 && coverImages.length < 4) {
      var filledCoverImages = [];
      for (var fillIndex = 0; fillIndex < 4; fillIndex++) {
        filledCoverImages.push(coverImages[fillIndex % coverImages.length]);
      }
      coverImages = filledCoverImages;
    }
    var tiles = [];
    for (var index = 0; index < 4; index++) {
      var cover = coverImages[index] && typeof coverImages[index] === 'object' ? coverImages[index] : null;
      tiles.push(this._renderCollectionCoverTile(cover, index));
    }
    return '<div class="collection-mosaic" aria-hidden="true">' + tiles.join('') + '</div>';
  }

  _renderSystemBucketCoverPile(node) {
    var coverImages = node && Array.isArray(node.cover_images) ? node.cover_images.slice(0, 6) : [];
    var pileImages = [];
    if (coverImages.length > 0) {
      for (var fillIndex = 0; fillIndex < 6; fillIndex++) {
        pileImages.push(coverImages[fillIndex % coverImages.length]);
      }
    }
    var tiles = [];
    for (var index = 0; index < 6; index++) {
      tiles.push('<div class="collection-pile-photo pile-' + String(index + 1) + '">' + this._renderCollectionCoverTile(pileImages[index] || null, index) + '</div>');
    }
    return '<div class="collection-mosaic collection-pile-preview" aria-hidden="true">'
      + tiles.join('')
      + '<div class="collection-pile-fade"></div>'
      + '</div>';
  }

  _renderCollectionCoverTile(cover, index) {
    if (!cover) {
      return '<div class="collection-mosaic-tile empty"><ha-icon icon="mdi:cube-outline"></ha-icon></div>';
    }
    var modelName = String(cover.model_name || cover.name || ('Cover ' + String(index + 1))).trim() || ('Cover ' + String(index + 1));
    var mediaUrl = String(cover.preview_url || '').trim();
    if (!mediaUrl) {
      return '<div class="collection-mosaic-tile empty"><ha-icon icon="mdi:image-off-outline"></ha-icon></div>';
    }
    if (this._isThumbnailLazyEndpoint(mediaUrl)) {
      var cachedObjectUrl = getCachedThumbnailObjectUrl(mediaUrl);
      if (cachedObjectUrl) {
        return '<div class="collection-mosaic-tile"><img src="' + this._escapeHtml(String(cachedObjectUrl)) + '" alt="' + this._escapeHtml(modelName) + ' preview" loading="lazy" decoding="async"></div>';
      }
      return '<div class="collection-mosaic-tile"><img data-thumbnail-lazy-url="' + this._escapeHtml(mediaUrl) + '" alt="' + this._escapeHtml(modelName) + ' preview" loading="lazy" decoding="async"></div>';
    }
    return '<div class="collection-mosaic-tile"><img src="' + this._escapeHtml(mediaUrl) + '" alt="' + this._escapeHtml(modelName) + ' preview" loading="lazy" decoding="async"></div>';
  }

  _coerceNonNegativeInt(value) {
    var count = Number(value);
    if (!Number.isFinite(count)) {
      return null;
    }
    return Math.max(0, Math.floor(count));
  }

  _objectFromUnknown(value) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return value;
    }
    if (typeof value === "string") {
      var raw = value.trim();
      if (!raw) {
        return null;
      }
      try {
        var parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          return parsed;
        }
      } catch (_error) {
      }
    }
    return null;
  }

  _readFirstCount(source, keys) {
    if (!source || typeof source !== "object") {
      return null;
    }
    for (var i = 0; i < keys.length; i++) {
      var key = keys[i];
      if (!Object.prototype.hasOwnProperty.call(source, key)) {
        continue;
      }
      var coerced = this._coerceNonNegativeInt(source[key]);
      if (coerced !== null) {
        return coerced;
      }
    }
    return null;
  }

  _deriveFileKindCounts(model, structured, fields, detail) {
    var candidateMaps = [
      model ? model.file_kinds : null,
      model ? model.file_kind_counts : null,
      fields ? fields.file_kinds : null,
      fields ? fields.file_kind_counts : null,
      structured ? structured.file_kinds : null,
      structured && structured.catalog_signals ? structured.catalog_signals.file_kinds : null,
      structured && structured.catalog_signals ? structured.catalog_signals.file_kind_counts : null,
    ];

    var map = null;
    for (var i = 0; i < candidateMaps.length; i++) {
      map = this._objectFromUnknown(candidateMaps[i]);
      if (map) {
        break;
      }
    }

    var modelFilesCount = this._readFirstCount(map, ["model_files", "model", "models", "model_count", "models_count", "model_file_count", "model_files_count", "files_model", "geometry", "three_d_files", "3d_files"]);
    var imageFilesCount = this._readFirstCount(map, ["images", "image", "image_files", "images_count", "image_count", "image_file_count", "media_file_count", "photos", "photos_count"]);
    var otherFilesCount = this._readFirstCount(map, ["other", "other_files", "other_count", "other_file_count", "docs", "documents", "docs_count", "supporting_file_count", "supporting_files_count"]);

    if (modelFilesCount === null) {
      modelFilesCount = this._readFirstCount(model, ["model_files_count", "model_file_count", "model_count", "models_count", "three_d_files_count", "3d_files_count"]);
    }
    if (imageFilesCount === null) {
      imageFilesCount = this._readFirstCount(model, ["image_files_count", "image_file_count", "images_count", "image_count", "media_file_count", "photos_count"]);
    }
    if (otherFilesCount === null) {
      otherFilesCount = this._readFirstCount(model, ["other_files_count", "other_file_count", "docs_count", "documents_count", "other_count", "supporting_file_count", "supporting_files_count"]);
    }

    if (modelFilesCount === null) {
      modelFilesCount = this._readFirstCount(fields, ["model_files_count", "model_file_count", "model_count", "models_count", "three_d_files_count", "3d_files_count"]);
    }
    if (imageFilesCount === null) {
      imageFilesCount = this._readFirstCount(fields, ["image_files_count", "image_file_count", "images_count", "image_count", "media_file_count", "photos_count"]);
    }
    if (otherFilesCount === null) {
      otherFilesCount = this._readFirstCount(fields, ["other_files_count", "other_file_count", "docs_count", "documents_count", "other_count", "supporting_file_count", "supporting_files_count"]);
    }

    if ((imageFilesCount === null || imageFilesCount === 0) && Number.isFinite(Number(model && model.preview_count))) {
      imageFilesCount = Math.max(0, Number(model.preview_count));
    }

    if (modelFilesCount === null || imageFilesCount === null || otherFilesCount === null) {
      var detailFiles = detail && Array.isArray(detail.files) ? detail.files : [];
      var detailPhotos = detail && Array.isArray(detail.photos) ? detail.photos : [];
      if (detailFiles.length || detailPhotos.length) {
        var inferredModel = 0;
        var inferredImages = 0;
        var inferredOther = 0;
        for (var f = 0; f < detailFiles.length; f++) {
          var file = detailFiles[f] || {};
          var filename = String(file.asset_filename || file.filename || file.name || file.path || "").toLowerCase();
          var dot = filename.lastIndexOf(".");
          var ext = dot >= 0 ? filename.slice(dot) : "";
          var mime = String(file.content_type || file.mime_type || "").toLowerCase();
          var assetType = String(file.asset_type || "").toLowerCase();
          var isImage = mime.indexOf("image/") === 0 || [".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".avif"].indexOf(ext) >= 0 || assetType === "image";
          var isModel = [".3mf", ".stl", ".obj", ".step", ".stp", ".gcode"].indexOf(ext) >= 0 || ["3mf", "stl", "obj", "step", "stp", "gcode"].indexOf(assetType) >= 0;
          if (isImage) {
            inferredImages += 1;
          } else if (isModel) {
            inferredModel += 1;
          } else {
            inferredOther += 1;
          }
        }
        inferredImages += detailPhotos.length;
        if (modelFilesCount === null) {
          modelFilesCount = inferredModel;
        }
        if (imageFilesCount === null) {
          imageFilesCount = inferredImages;
        }
        if (otherFilesCount === null) {
          otherFilesCount = inferredOther;
        }
      }
    }

    // When detail has NOT loaded yet, supplement the image count with
    // uploaded photos from fields (custom_fields.uploaded_photos) so
    // chips render correctly before lazy-detail arrives.
    if (!detail && fields) {
      var upRaw = fields.uploaded_photos;
      if (typeof upRaw === "string") {
        try { upRaw = JSON.parse(upRaw); } catch (_e) { upRaw = null; }
      }
      if (Array.isArray(upRaw) && upRaw.length) {
        var hiRaw = fields.media_hidden_ids;
        if (typeof hiRaw === "string") {
          try { hiRaw = JSON.parse(hiRaw); } catch (_e) { hiRaw = []; }
        }
        var hiSet = {};
        if (Array.isArray(hiRaw)) {
          for (var hx = 0; hx < hiRaw.length; hx++) {
            var hv = String(hiRaw[hx] || "").trim();
            if (hv) { hiSet[hv] = true; }
          }
        }
        var upVisible = 0;
        for (var ux = 0; ux < upRaw.length; ux++) {
          var upId = String(upRaw[ux].id || "").trim();
          if (upId && !hiSet["photo:" + upId]) {
            upVisible += 1;
          }
        }
        if (upVisible > 0) {
          imageFilesCount = (imageFilesCount || 0) + upVisible;
        }
      }
      // Also count visible source URL images before detail loads
      var srcUrlsPreDetail = this._sourceUrlImageList(model, null);
      if (srcUrlsPreDetail.length) {
        imageFilesCount = (imageFilesCount || 0) + srcUrlsPreDetail.length;
      }
    }

    // When detail data is available, recompute the image count from the
    // authoritative source: uploaded photos + image-type assets + embedded
    // thumbnails + source URL images, minus any items the user marked as hidden.
    if (detail) {
      var adjPhotos = Array.isArray(detail.photos) ? detail.photos : [];
      var adjFiles = (detail.model && Array.isArray(detail.model.files))
        ? detail.model.files
        : (Array.isArray(detail.files) ? detail.files : []);
      var hmRaw = detail.enrichment && detail.enrichment.custom_fields
        ? detail.enrichment.custom_fields.media_hidden_ids : null;
      var hmSet = {};
      if (Array.isArray(hmRaw)) {
        for (var hi = 0; hi < hmRaw.length; hi++) {
          var hid = String(hmRaw[hi] || "").trim();
          if (hid) { hmSet[hid] = true; }
        }
      } else if (typeof hmRaw === "string" && hmRaw.trim()) {
        var hParts = hmRaw.split(",");
        for (var hi = 0; hi < hParts.length; hi++) {
          var hid = hParts[hi].trim();
          if (hid) { hmSet[hid] = true; }
        }
      }
      if (adjPhotos.length || adjFiles.length) {
        var visibleImageCount = 0;
        for (var pi = 0; pi < adjPhotos.length; pi++) {
          var pId = String(adjPhotos[pi].id || ("photo-" + (pi + 1))).trim();
          if (!hmSet["photo:" + pId]) {
            visibleImageCount += 1;
          }
        }
        for (var fi2 = 0; fi2 < adjFiles.length; fi2++) {
          var af = adjFiles[fi2] || {};
          var aId = String(af.asset_id || af.id || "").trim();
          if (String(af.asset_type || "").toLowerCase() === "image") {
            if (!hmSet["asset:" + aId]) {
              visibleImageCount += 1;
            }
          } else {
            var hasThumb = String(af.thumbnail_lazy_url || af.thumbnail_url || af.preview_url || "").trim();
            if (hasThumb && !hmSet["embedded:" + aId]) {
              visibleImageCount += 1;
            }
          }
        }
        imageFilesCount = visibleImageCount;
      }
      // Add visible source URL images to the image count
      var srcUrlsWithDetail = this._sourceUrlImageList(model, detail);
      if (srcUrlsWithDetail.length) {
        imageFilesCount = (imageFilesCount || 0) + srcUrlsWithDetail.length;
      }
    }

    return {
      model_files: Math.max(0, Number(modelFilesCount || 0)),
      images: Math.max(0, Number(imageFilesCount || 0)),
      other: Math.max(0, Number(otherFilesCount || 0)),
    };
  }

  _renderModelCheckbox(modelRef) {
    var isSelected = this._isModelSelected(modelRef);
    return '<div class="model-card-checkbox" data-action="toggle-model-select" data-model-ref="' + this._escapeHtml(modelRef) + '">'
      + '<input type="checkbox"' + (isSelected ? ' checked' : '') + ' aria-label="Select ' + this._escapeHtml(modelRef) + '">'
      + '</div>';
  }

  _renderFileKindChipRow(counts) {
    var modelFiles = this._coerceNonNegativeInt(counts && counts.model_files);
    var images = this._coerceNonNegativeInt(counts && counts.images);
    var other = this._coerceNonNegativeInt(counts && counts.other);
    var chips = "";
    if (modelFiles && modelFiles > 0) {
      chips += this._renderFileKindIconChip(modelFiles, "mdi:cube-outline", "Models", "file-kind-chip file-kind-model");
    }
    if (images && images > 0) {
      chips += this._renderFileKindIconChip(images, "mdi:image-outline", "Images", "file-kind-chip file-kind-image");
    }
    if (other && other > 0) {
      chips += this._renderFileKindIconChip(other, "mdi:file-outline", "Files", "file-kind-chip file-kind-other");
    }
    return chips;
  }

  _renderFileKindIconChip(count, mdiIcon, label, className) {
    var countStr = String(count || "");
    if (mdiIcon === "mdi:cube-outline") {
      return '<span class="chip' + (className ? (' ' + className) : '') + '">'
        + '<svg class="icon-svg" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        + '<path d="M12 3 L4 7.5 L12 12 L20 7.5 Z M4 7.5 V16.5 L12 21 L20 16.5 V7.5 M12 12 V21" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>'
        + '</svg>'
        + '<span class="chip-count">' + this._escapeHtml(countStr) + '</span>'
        + '</span>';
    }
    var svgPath = this._getMdiPath(mdiIcon);
    return '<span class="chip' + (className ? (' ' + className) : '') + '">'
      + '<svg class="icon-svg" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
      + '<path d="' + svgPath + '" fill="currentColor"/>'
      + '</svg>'
      + '<span class="chip-count">' + this._escapeHtml(countStr) + '</span>'
      + '</span>';
  }

  _getMdiPath(mdiIcon) {
    // Material Design Icon SVG paths
    var paths = {
      "mdi:cube-outline": "M21,16V8L12,3L3,8V16L12,21L21,16M12,5.15L18.74,9L12,12.85L5.26,9L12,5.15M5,10.73L11,14.16V19.54L5,16.11V10.73M13,19.54V14.16L19,10.73V16.11L13,19.54Z",
      "mdi:image-outline": "M21,19V5C21,3.89 20.1,3 19,3H5A2,2 0 0,0 3,5V19A2,2 0 0,0 5,21H19C20.1,21 21,20.1 21,19M19,19H5V5H19V19M18,17H6L10.5,11L13.5,15L15.5,12.5L18,17Z",
      "mdi:file-outline": "M14,2H6C4.89,2 4,2.89 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M14,4L18,8H14V4M18,20H6V4H12V10H18V20Z"
    };
    return paths[mdiIcon] || "";
  }

  async _openModelViewerPopup(modelRef, modelName) {
    if (!modelRef) {
      return;
    }

    var detail = this._modelDetailCache[modelRef] || null;
    if (!detail && this._hass) {
      try {
        detail = await this._callServiceWithResponse("rest_command", "get_model_detail", { model_ref: modelRef });
        if (detail && typeof detail === "object") {
          this._modelDetailCache[modelRef] = detail;
        }
      } catch (_error) {
        detail = null;
      }
    }

    var modelPayload = detail && detail.model && typeof detail.model === "object" ? Object.assign({}, detail.model) : {};
    if (!Array.isArray(modelPayload.files) && detail && Array.isArray(detail.files)) {
      modelPayload.files = detail.files;
    }
    if (!String(modelPayload.name || "").trim() && modelName) {
      modelPayload.name = modelName;
    }

    this._fireBrowserModEvent("browser_mod.popup", {
      title: (modelName || "Model") + " - 3D Viewer",
      size: "wide",
      content: {
        type: "custom:model-detail-3d-viewer-tab",
        model_ref: modelRef,
        model_name: modelName || "Model",
        model_sidecar_url: this._modelSidecarUrl || (this._config && this._config.model_sidecar_url ? String(this._config.model_sidecar_url) : ""),
        model_json: JSON.stringify(modelPayload),
      },
    });
  }

  _openModelDetailPopup(modelRef, modelName, initialTab) {
    if (!modelRef) {
      return;
    }

    this._fireBrowserModEvent("browser_mod.popup", {
      title: modelName || "Model Details",
      size: "wide",
      content: {
        type: "custom:model-detail-popup-card",
        model_ref: modelRef,
        initial_tab: String(initialTab || "details"),
        model_entity: "input_text.model_catalog_sidecar_base_url",
        model_sidecar_url: this._modelSidecarUrl || (this._config && this._config.model_sidecar_url ? String(this._config.model_sidecar_url) : ""),
      },
    });
  }

  _fireBrowserModEvent(service, data) {
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

    this.dispatchEvent(event);
  }

  // ===== Multi-select primitive implementation (#1401 Phase 0 Foundations) =====

  _toggleModelSelection(modelRef) {
    var modelRefStr = String(modelRef || "").trim();
    if (!modelRefStr) {
      return;
    }
    if (this._selectedModelRefs.has(modelRefStr)) {
      this._selectedModelRefs.delete(modelRefStr);
    } else {
      this._selectedModelRefs.add(modelRefStr);
    }
    this._notifySelectionChanged();
    this._render();
  }

  _toggleSelectAllModels() {
    var visibleRefs = this._getVisibleModelRefs();
    if (visibleRefs.length === 0) {
      return;
    }
    // If all are selected, deselect all. Otherwise, select all.
    var allSelected = visibleRefs.every(function (ref) {
      return this._selectedModelRefs.has(ref);
    }.bind(this));

    if (allSelected) {
      this._clearModelSelection();
    } else {
      for (var i = 0; i < visibleRefs.length; i++) {
        this._selectedModelRefs.add(visibleRefs[i]);
      }
      this._notifySelectionChanged();
      this._render();
    }
  }

  _clearModelSelection() {
    if (this._selectedModelRefs.size === 0) {
      return;
    }
    this._selectedModelRefs.clear();
    this._notifySelectionChanged();
    this._render();
  }

  _getVisibleModelRefs() {
    if (this._browserScope === "collections") {
      return [];
    }
    var visibleEntries = this._currentDisplayEntries();
    return visibleEntries.map(function (entry) {
      if (!entry || entry.kind !== 'model') {
        return "";
      }
      return this._modelRef(entry.data);
    }.bind(this)).filter(function (ref) {
      return !!ref;
    });
  }

  _isModelSelected(modelRef) {
    return this._selectedModelRefs.has(String(modelRef || "").trim());
  }

  _notifySelectionChanged() {
    var selectedRefs = Array.from(this._selectedModelRefs);
    for (var i = 0; i < this._selectionChangeCallbacks.length; i++) {
      var cb = this._selectionChangeCallbacks[i];
      if (typeof cb === "function") {
        try {
          cb({
            selected_model_refs: selectedRefs,
            count: selectedRefs.length,
            visible_count: this._getVisibleModelRefs().length,
          });
        } catch (_err) {
          console.warn("Selection change callback error", _err);
        }
      }
    }
  }

  // ===== Public API for multi-select (consumed by #1478, Phase 3 D&D) =====

  /**
   * Get array of currently selected model references.
   * @returns {Array<string>}
   */
  getSelectedModelRefs() {
    return Array.from(this._selectedModelRefs);
  }

  /**
   * Set selection programmatically.
   * @param {Array<string>} refs - Model references to select
   */
  setSelectedModelRefs(refs) {
    this._selectedModelRefs.clear();
    if (Array.isArray(refs)) {
      for (var i = 0; i < refs.length; i++) {
        var ref = String(refs[i] || "").trim();
        if (ref) {
          this._selectedModelRefs.add(ref);
        }
      }
    }
    this._notifySelectionChanged();
    this._render();
  }

  /**
   * Subscribe to selection changes.
   * Callback receives { selected_model_refs: [], count: N, visible_count: N }
   * @param {Function} callback
   */
  onSelectionChange(callback) {
    if (typeof callback === "function") {
      this._selectionChangeCallbacks.push(callback);
    }
  }

  /**
   * Clear all selection subscribers.
   */
  clearSelectionChangeListeners() {
    this._selectionChangeCallbacks = [];
  }

  _renderLoadingPlaceholders() {
    var count = Math.max(3, Math.min(8, Number(this._pagination.per_page || 12)));
    var markup = [];
    for (var i = 0; i < count; i++) {
      markup.push(this._renderPlaceholderCard());
    }
    return markup.join("");
  }

  _renderPlaceholderCard() {
    if (this._viewMode === "media") {
      return ''
        + '<article class="model-card skeleton view-media" aria-hidden="true">'
        + '  <div class="thumb-wrap media-wrap">'
        + '    <div class="media-preview skeleton-block"></div>'
        + '  </div>'
        + '  <div class="body media-body">'
        + '    <div class="skeleton-line skeleton-block w-80"></div>'
        + '    <div class="skeleton-line skeleton-block w-55"></div>'
        + '    <div class="skeleton-line skeleton-block w-95"></div>'
        + '  </div>'
        + '</article>';
    }

    if (this._viewMode === "list") {
      return ''
        + '<article class="model-card skeleton view-list" aria-hidden="true">'
        + '  <div class="thumb-wrap list-wrap">'
        + '    <div class="thumb list-thumb skeleton-block"></div>'
        + '  </div>'
        + '  <div class="body list-body">'
        + '    <div class="skeleton-line skeleton-block w-70"></div>'
        + '    <div class="skeleton-line skeleton-block w-50"></div>'
        + '    <div class="skeleton-line skeleton-block w-90"></div>'
        + '  </div>'
        + '</article>';
    }

    return ''
      + '<article class="model-card skeleton view-compact" aria-hidden="true">'
      + '  <div class="thumb-wrap compact-wrap">'
      + '    <div class="thumb skeleton-block"></div>'
      + '  </div>'
      + '  <div class="body compact-main">'
      + '    <div class="skeleton-line skeleton-block w-85"></div>'
      + '    <div class="skeleton-line skeleton-block w-60"></div>'
      + '    <div class="skeleton-line skeleton-block w-95"></div>'
      + '  </div>'
      + '  <div class="body compact-full">'
      + '    <div class="skeleton-line skeleton-block w-75"></div>'
      + '    <div class="skeleton-line skeleton-block w-90"></div>'
      + '  </div>'
      + '</article>';
  }

  _render() {
    if (this._renderRAFId) return;
    this._renderRAFId = requestAnimationFrame(function () {
      this._renderRAFId = null;
      this._doRender();
    }.bind(this));
  }

  _captureActiveInputState() {
    if (!this.shadowRoot) {
      return null;
    }
    var active = this.shadowRoot.activeElement;
    if (!active) {
      return null;
    }
    var tag = String(active.tagName || "").toUpperCase();
    if (tag !== "INPUT" && tag !== "TEXTAREA") {
      return null;
    }
    var id = String(active.id || "");
    if (!id) {
      // Only restore focus for elements we can reliably re-target by id.
      return null;
    }
    var snapshot = { id: id };
    try {
      if (typeof active.selectionStart === "number") {
        snapshot.selectionStart = active.selectionStart;
        snapshot.selectionEnd = active.selectionEnd;
        snapshot.selectionDirection = active.selectionDirection || "none";
      }
    } catch (_e) {
      // Some input types (number, email, etc.) throw when reading selection.
    }
    return snapshot;
  }

  _restoreActiveInputState(snapshot) {
    if (!snapshot || !snapshot.id || !this.shadowRoot) {
      return;
    }
    var node = this.shadowRoot.getElementById(snapshot.id);
    if (!node || typeof node.focus !== "function") {
      return;
    }
    if (this.shadowRoot.activeElement === node) {
      return;
    }
    try {
      node.focus({ preventScroll: true });
    } catch (_e) {
      try { node.focus(); } catch (_e2) { /* ignore */ }
    }
    if (typeof snapshot.selectionStart === "number" && typeof node.setSelectionRange === "function") {
      try {
        node.setSelectionRange(snapshot.selectionStart, snapshot.selectionEnd, snapshot.selectionDirection || "none");
      } catch (_e) {
        // setSelectionRange is unsupported on some input types; ignore.
      }
    }
  }

  _renderNow() {
    if (this._renderRAFId) {
      cancelAnimationFrame(this._renderRAFId);
      this._renderRAFId = null;
    }
    this._doRender();
  }

  _doRender() {
    if (!this.shadowRoot || !this._config) {
      return;
    }

    if (this._browserScope === "working") {
      this._browserScope = "models";
    }

    var renderStart = (window.performance && typeof window.performance.now === "function") ? window.performance.now() : Date.now();
    var renderEpoch = this._renderEpoch + 1;
    this._renderEpoch = renderEpoch;
    if (this._progressiveAppendHandle) {
      window.clearTimeout(this._progressiveAppendHandle);
      this._progressiveAppendHandle = null;
    }

    var visibleResults = this._filteredResultsForScope();
    var includeWorkingInModels = this._browserScope === "models" && !!(this._typeFilters && this._typeFilters.working);
    var visibleWorkingProjection = includeWorkingInModels ? (Array.isArray(this._workingProjection) ? this._workingProjection : []) : [];
    var displayEntries = this._currentDisplayEntries();
    var progressiveRemainder = null;

    var resultsHtml = "";
    if (this._loading) {
      resultsHtml = this._renderLoadingPlaceholders();
    } else if (this._error) {
      resultsHtml = '<div class="state-row error">' + this._escapeHtml(this._error) + '</div>';
    } else if (this._browserScope === "collections") {
      resultsHtml = this._renderCollectionCards();
    } else if (!visibleResults.length && !visibleWorkingProjection.length) {
      resultsHtml = '<div class="state-row">'
        + (((this._typeFilters && this._typeFilters.working) && !(this._typeFilters.model || this._typeFilters.idea))
          ? 'No Working Files folders match the current search.'
          : 'No models match the current filters.')
        + '</div>';
    } else {
      var entryHtml = "";
      if (this._shouldProgressiveResultsRender(displayEntries)) {
        var initialCount = Math.min(18, displayEntries.length);
        entryHtml = displayEntries.slice(0, initialCount).map(this._renderCatalogEntryCard.bind(this)).join("");
        progressiveRemainder = displayEntries.slice(initialCount);
      } else {
        entryHtml = displayEntries.map(this._renderCatalogEntryCard.bind(this)).join("");
      }
      resultsHtml = entryHtml;
    }

    // Inject the <style> element once so the browser never re-parses ~300
    // lines of static CSS on every render.  Only the <ha-card> content is
    // replaced on subsequent renders, which avoids the full-screen
    // compositor flash caused by stylesheet teardown/rebuild.
    if (!this._persistentStyle) {
      this._persistentStyle = document.createElement('style');
      this._persistentStyle.textContent = ''
      + ':host{--surface-1:rgba(15,23,42,0.12);--surface-2:rgba(15,23,42,0.22);--line:rgba(148,163,184,0.18);--line-strong:rgba(148,163,184,0.28);--accent:rgba(96,165,250,0.22);--accent-strong:rgba(96,165,250,0.38);--chip-bg:rgba(148,163,184,0.12);--chip-line:rgba(148,163,184,0.24);}'
      + 'ha-card{border-radius:0;border:none;background:transparent;box-shadow:none;contain:content;}'
      + 'ha-card.queue-dialog-host-open{contain:none;}'
      + '.shell{display:grid;gap:14px;padding:6px 10px 10px;}'
      + '.catalog-layout{position:relative;display:grid;grid-template-columns:minmax(0,260px) minmax(0,1fr);gap:14px;align-items:start;}'
      + '.catalog-layout.nav-collapsed{grid-template-columns:84px minmax(0,1fr);}'
      + '.main-pane{display:grid;gap:14px;min-width:0;}'
      + '.left-nav-backdrop{display:none;}'
      + '.left-nav{display:grid;gap:10px;padding:12px;border:1px solid var(--line);border-radius:16px;background:var(--surface-1);max-height:calc(100vh - 112px);overflow:auto;}'
      + '.left-nav-head{display:flex;align-items:center;justify-content:space-between;gap:8px;}'
      + '.left-nav-title-wrap{display:flex;align-items:center;gap:8px;min-width:0;cursor:default;}'
      + '.left-nav-title-wrap ha-icon{--mdc-icon-size:18px;color:#93c5fd;}'
      + '.left-nav-title-text{font-size:12px;font-weight:800;color:var(--primary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
      + '.left-nav-collapse{width:30px;min-width:30px;height:30px;}'
      + '.left-nav-collapse ha-icon{--mdc-icon-size:16px;transition:transform 160ms ease;}'
      + '.left-nav.collapsed .left-nav-collapse ha-icon{transform:rotate(180deg);}'
      + '.left-nav-section{display:grid;gap:6px;}'
      + '.left-nav-section + .left-nav-section{padding-top:10px;border-top:1px solid rgba(148,163,184,0.14);}'
      + '.left-nav-section-label{font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--secondary-text-color);padding:0 2px;}'
      + '.left-nav-item{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:34px;padding:0 8px;border-radius:10px;border:1px solid rgba(148,163,184,0.2);background:rgba(15,23,42,0.08);color:var(--primary-text-color);font-size:12px;font-weight:700;cursor:pointer;text-align:left;}'
      + '.left-nav-item:hover,.left-nav-item:focus-visible{background:rgba(148,163,184,0.16);border-color:rgba(148,163,184,0.36);outline:none;}'
      + '.left-nav-item.active{background:var(--accent);border-color:var(--accent-strong);}'
      + '.left-nav-tree{display:grid;gap:4px;}'
      + '.left-nav-tree-node{display:grid;gap:4px;}'
      + '.left-nav-tree-children{display:grid;gap:4px;}'
      + '.left-nav-tree-row{position:relative;display:block;padding-left:calc(var(--tree-depth, 0) * 12px);}'
      + '.left-nav-tree-item{width:100%;padding-left:34px;}'
      + '.left-nav-tree-row:not(.has-children) .left-nav-tree-item{padding-left:8px;}'
      + '.left-nav-tree-toggle{position:absolute;left:6px;top:50%;transform:translateY(-50%);width:22px;min-width:22px;height:22px;display:inline-flex;align-items:center;justify-content:center;border-radius:999px;border:1px solid rgba(148,163,184,0.2);background:rgba(15,23,42,0.06);color:var(--secondary-text-color);cursor:pointer;z-index:1;}'
      + '.left-nav-tree-toggle:hover,.left-nav-tree-toggle:focus-visible{background:rgba(148,163,184,0.16);border-color:rgba(148,163,184,0.36);outline:none;}'
      + '.left-nav-tree-toggle ha-icon{--mdc-icon-size:14px;}'
      + '.left-nav-tree-label{cursor:default;}'
      + '.left-nav-item-main{display:flex;align-items:center;gap:8px;min-width:0;}'
      + '.left-nav-item-main ha-icon{--mdc-icon-size:16px;opacity:.9;}'
      + '.left-nav-item-label{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}'
      + '.left-nav-item-count{font-size:11px;font-weight:800;color:var(--secondary-text-color);}'
      + '.left-nav-item-count.dismiss{font-size:16px;line-height:1;color:var(--secondary-text-color);}'
      + '.left-nav-type-toggle{display:grid;grid-template-columns:auto auto minmax(0,1fr) auto;align-items:center;gap:8px;min-height:32px;padding:0 8px;border-radius:10px;border:1px solid rgba(148,163,184,0.2);background:rgba(15,23,42,0.08);cursor:pointer;}'
      + '.left-nav-type-toggle:hover,.left-nav-type-toggle:focus-within{background:rgba(148,163,184,0.14);border-color:rgba(148,163,184,0.36);}'
      + '.left-nav-type-checkbox{width:14px;height:14px;margin:0;accent-color:#60a5fa;cursor:pointer;}'
      + '.left-nav-type-icon{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;color:#93c5fd;}'
      + '.left-nav-type-icon ha-icon{--mdc-icon-size:16px;}'
      + '.left-nav-type-label{font-size:12px;font-weight:700;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}'
      + '.left-nav-type-count{font-size:11px;font-weight:700;color:var(--secondary-text-color);}'
      + '.left-nav-empty{font-size:11px;color:var(--secondary-text-color);padding:6px 8px;border:1px dashed rgba(148,163,184,0.26);border-radius:8px;}'
      + '.toolbar-icon-btn.left-nav-toggle{display:none;}'
      + '.nav-context-chip{display:none;align-items:center;gap:6px;height:34px;padding:0 10px 0 8px;border-radius:10px;border:1px solid var(--chip-line);background:var(--chip-bg);color:var(--primary-text-color);font-size:12px;font-weight:700;cursor:pointer;white-space:nowrap;max-width:200px;overflow:hidden;text-overflow:ellipsis;transition:background 120ms ease,border-color 120ms ease;}'
      + '.nav-context-chip:hover,.nav-context-chip:focus-visible{background:rgba(148,163,184,0.22);border-color:rgba(148,163,184,0.4);outline:none;}'
      + '.nav-context-chip ha-icon{--mdc-icon-size:16px;flex-shrink:0;}'
      + '.nav-context-chip .nav-context-caret{--mdc-icon-size:14px;opacity:.6;}'
      + '.nav-context-label{overflow:hidden;text-overflow:ellipsis;}'
      + '.left-nav.collapsed .left-nav-title-wrap{display:none;}'
      + '.left-nav.collapsed .left-nav-title-text,.left-nav.collapsed .left-nav-section-label,.left-nav.collapsed .left-nav-item-label,.left-nav.collapsed .left-nav-item-count,.left-nav.collapsed .left-nav-type-label,.left-nav.collapsed .left-nav-type-count{display:none;}'
      + '.left-nav.collapsed .left-nav-title-wrap,.left-nav.collapsed .left-nav-item-main{justify-content:center;}'
      + '.left-nav.collapsed .left-nav-item{justify-content:center;padding:0 4px;}'
      + '.left-nav.collapsed .left-nav-type-toggle{grid-template-columns:auto auto;justify-content:center;justify-items:center;column-gap:6px;padding:0 4px;}'
      + '.left-nav.collapsed .left-nav-head{justify-content:center;position:relative;min-height:32px;}'
      + '.left-nav.collapsed .left-nav-collapse{position:static;opacity:1;pointer-events:auto;z-index:1;background:rgba(96,165,250,0.20);border-color:rgba(96,165,250,0.40);}'
      + '.shell-header{display:grid;gap:10px;}'
      + '.title-row{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:12px;border:1px solid var(--line);border-radius:16px;background:var(--surface-1);}'
      + '.title-left{display:flex;align-items:center;gap:10px;flex-wrap:wrap;min-width:0;}'
      + '.title-right{display:flex;align-items:center;gap:10px;flex-wrap:wrap;}'
      + '.card-title{font-size:18px;font-weight:800;line-height:1.2;}'
      + '.sort-group{display:inline-flex;align-items:center;gap:8px;flex-wrap:nowrap;min-width:0;}'
      + '.sort-group label{font-size:11px;font-weight:800;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.03em;white-space:nowrap;}'
      + '.sort-group .title-select{width:auto;flex:0 0 auto;min-width:130px;}'
      + '.segmented-toggle{display:inline-flex;align-items:center;padding:3px;border-radius:999px;border:1px solid var(--chip-line);background:rgba(15,23,42,0.12);}'
      + '.segmented-btn{min-height:34px;padding:0 12px;border:0;background:transparent;color:var(--secondary-text-color);font-size:12px;font-weight:800;border-radius:999px;cursor:pointer;}'
      + '.segmented-btn.active{background:var(--accent);color:var(--primary-text-color);}'
      + '.toolbar-btn{min-height:36px;padding:0 12px;border-radius:999px;border:1px solid var(--chip-line);background:var(--chip-bg);color:var(--primary-text-color);font-size:12px;font-weight:700;cursor:pointer;}'
      + '.toolbar-btn.ghost{background:rgba(15,23,42,0.08);}'
      + '.toolbar-btn:disabled{opacity:.55;cursor:not-allowed;}'
      + '.advanced-filter-menu{position:relative;}'
      + '.advanced-filter-trigger{display:inline-flex;align-items:center;gap:6px;list-style:none;}'
      + '.advanced-filter-trigger::-webkit-details-marker{display:none;}'
      + '.advanced-filter-trigger ha-icon{--mdc-icon-size:16px;}'
      + '.advanced-filter-badge{display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;padding:0 5px;border-radius:999px;background:rgba(96,165,250,0.24);border:1px solid rgba(96,165,250,0.40);font-size:10px;font-weight:900;color:var(--primary-text-color);}'
      + '.advanced-filter-items{position:absolute;top:40px;right:0;display:grid;gap:12px;min-width:280px;padding:12px;border-radius:16px;border:1px solid var(--line-strong);background:rgba(15,23,42,0.96);box-shadow:0 16px 28px rgba(15,23,42,0.28);z-index:7;}'
      + '.advanced-filter-field{display:grid;gap:6px;min-width:0;}'
      + '.advanced-filter-field > span,.advanced-filter-section-label{font-size:11px;font-weight:800;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.03em;white-space:nowrap;}'
      + '.advanced-filter-toggle-row{display:flex;flex-wrap:wrap;gap:8px;}'
      + '.advanced-filter-section{display:grid;gap:8px;}'
      + '.advanced-filter-tuning-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;}'
      + '.advanced-filter-tuning-row .inline-select{justify-content:space-between;}'
      + '.advanced-filter-footer{display:flex;justify-content:flex-end;}'
      + '.import-menu{position:relative;}'
      + '.import-trigger{display:inline-flex;align-items:center;gap:4px;list-style:none;}'
      + '.import-trigger::-webkit-details-marker{display:none;}'
      + '.import-trigger ha-icon{--mdc-icon-size:16px;}'
      + '.import-menu-items{position:absolute;top:38px;right:0;display:grid;min-width:180px;padding:8px;border-radius:12px;border:1px solid var(--line-strong);background:rgba(15,23,42,0.96);box-shadow:0 16px 28px rgba(15,23,42,0.28);z-index:5;}'
      + '.import-item{min-height:34px;padding:0 10px;border-radius:8px;border:1px solid transparent;background:transparent;color:var(--primary-text-color);font-size:12px;font-weight:700;text-align:left;cursor:pointer;}'
      + '.import-item:hover{background:rgba(148,163,184,0.14);}'
      + '.display-group{gap:8px;}'
      + '.view-mode-menu{position:relative;}'
      + '.view-mode-trigger{display:inline-flex;align-items:center;gap:6px;list-style:none;padding:0 12px;min-height:34px;}'
      + '.view-mode-trigger::-webkit-details-marker{display:none;}'
      + '.view-mode-trigger ha-icon{--mdc-icon-size:16px;}'
      + '.view-mode-trigger .view-mode-label{font-size:12px;font-weight:800;line-height:1;}'
      + '.view-mode-trigger .view-mode-caret{--mdc-icon-size:14px;opacity:.86;}'
      + '.view-mode-items{position:absolute;top:38px;right:0;display:grid;gap:4px;min-width:176px;padding:8px;border-radius:16px;border:1px solid var(--line-strong);background:rgba(15,23,42,0.96);box-shadow:0 16px 28px rgba(15,23,42,0.28);z-index:6;}'
      + '.view-mode-item{display:flex;align-items:center;gap:8px;min-height:34px;padding:0 10px;border-radius:999px;border:1px solid transparent;background:transparent;color:var(--primary-text-color);font-size:12px;font-weight:700;text-align:left;cursor:pointer;}'
      + '.view-mode-item ha-icon{--mdc-icon-size:16px;opacity:.92;}'
      + '.view-mode-item:hover,.view-mode-item:focus-visible{background:rgba(148,163,184,0.16);outline:none;}'
      + '.view-mode-item.active{background:var(--accent);border-color:var(--accent-strong);}'
      + '.view-mode-item:disabled{opacity:.55;cursor:not-allowed;}'
      + '.filter-bar-stack{display:grid;gap:10px;}'
      + '.filter-row{display:grid;grid-template-columns:minmax(220px,1.8fr) minmax(160px,1fr) auto auto auto auto auto;gap:8px;padding:12px;border-radius:16px;border:1px solid var(--line);background:rgba(148,163,184,0.08);align-items:center;}'
      + '.search-only-filter-row{grid-template-columns:minmax(240px,1fr);}'
      + '.selected-filter-strip{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:0 4px;}'
      + '.selected-filter-label{font-size:11px;font-weight:800;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.03em;}'
      + '.selected-filter-chip{display:inline-flex;align-items:center;gap:8px;min-height:34px;padding:0 12px;border-radius:999px;border:1px solid var(--chip-line);background:rgba(15,23,42,0.08);color:var(--primary-text-color);font-size:12px;font-weight:800;cursor:pointer;}'
      + '.selected-filter-chip:hover,.selected-filter-chip:focus-visible{background:rgba(148,163,184,0.18);outline:none;border-color:rgba(148,163,184,0.42);}'
      + '.selected-filter-chip.collection-chip{background:rgba(59,130,246,0.16);border-color:rgba(59,130,246,0.30);}'
      + '.selected-filter-chip.tag-chip{background:rgba(245,158,11,0.16);border-color:rgba(245,158,11,0.30);}'
      + '.selected-filter-prefix{font-size:10px;font-weight:900;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.04em;}'
      + '.selected-filter-value{font-size:12px;font-weight:800;color:var(--primary-text-color);}'
      + '.selected-filter-remove{font-size:16px;line-height:1;color:var(--secondary-text-color);}'
      + '.selected-filter-clear{min-height:34px;padding:0 10px;border-radius:999px;border:1px dashed var(--chip-line);background:transparent;color:var(--secondary-text-color);font-size:11px;font-weight:800;cursor:pointer;text-transform:uppercase;letter-spacing:.03em;}'
      + '.selected-filter-clear:hover,.selected-filter-clear:focus-visible{outline:none;border-color:rgba(148,163,184,0.42);background:rgba(148,163,184,0.12);}'
      + '.filter-search{grid-column:auto;}'
      + '.inline-select{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:800;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.03em;white-space:nowrap;}'
      + '.inline-select .tuning-select{min-width:84px;min-height:34px;}'
      + '.filter-chip{min-height:36px;padding:0 12px;border-radius:999px;border:1px solid var(--chip-line);background:rgba(15,23,42,0.08);color:var(--secondary-text-color);font-size:12px;font-weight:800;cursor:pointer;appearance:none;pointer-events:auto;position:relative;z-index:1;}'
      + '.filter-chip:hover,.filter-chip:focus-visible{background:rgba(148,163,184,0.18);outline:none;border-color:rgba(148,163,184,0.42);}'
      + '.filter-chip.active{color:var(--primary-text-color);}'
      + '.filter-chip.docs.active{background:rgba(56,189,248,0.18);border-color:rgba(56,189,248,0.34);color:#93c5fd;}'
      + '.filter-chip.archived.active{background:rgba(148,163,184,0.20);border-color:rgba(148,163,184,0.44);color:#cbd5e1;}'
      + '.page-control-strip{display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap;padding:10px 12px;border-radius:16px;border:1px solid var(--line);background:var(--surface-1);}'
      + '.toolbar-group{display:inline-flex;align-items:center;gap:8px;min-width:0;}'
      + '.toolbar-group label{font-size:11px;font-weight:800;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.03em;}'
      + '.nav-group{padding:2px 8px;border-radius:999px;border:1px solid var(--chip-line);background:rgba(15,23,42,0.10);}'
      + '.toolbar-icon-btn{width:34px;min-width:34px;height:34px;display:inline-flex;align-items:center;justify-content:center;border-radius:999px;border:1px solid var(--chip-line);background:var(--chip-bg);color:var(--primary-text-color);cursor:pointer;}'
      + '.toolbar-icon-btn ha-icon{--mdc-icon-size:18px;}'
      + '.toolbar-icon-btn:disabled{opacity:.5;cursor:not-allowed;}'
      + '.toolbar-icon-btn.media-toggle.active{background:rgba(96,165,250,0.22);border-color:var(--accent-strong);}'
      + '.refresh-btn.spinning ha-icon{animation:spin-refresh .75s linear infinite;}'
      + '.page-status{display:inline-flex;align-items:center;gap:6px;padding:0 8px;font-size:12px;font-weight:700;color:var(--secondary-text-color);white-space:nowrap;}'
      + '.page-total{color:#7dd3fc;}'
      + '.page-dot{opacity:.8;}'
      + '.compact-select{min-height:34px;padding:4px 10px;border-radius:999px;min-width:74px;}'
      + '.bottom-mirror{margin-top:2px;}'
      + '.control{display:grid;gap:5px;min-width:0;}'
      + '.control label{font-size:11px;color:var(--secondary-text-color);font-weight:800;letter-spacing:.03em;text-transform:uppercase;}'
      + '.control-input{width:100%;box-sizing:border-box;min-height:40px;padding:9px 12px;border-radius:12px;border:1px solid rgba(148,163,184,0.26);background:rgba(15,23,42,0.18);color:var(--primary-text-color);}'
      + 'select.control-input{color-scheme:light dark;}'
      + '.control-input option,.control-input optgroup{background:var(--card-background-color);color:var(--primary-text-color);}'
      + '.results{display:grid;gap:12px;}'
      + '.working-inline-section{grid-column:1/-1;display:grid;gap:12px;}'
      + '.working-inline-header{font-weight:800;}'
      + '.results.is-loading{pointer-events:none;}'
      + '.results.view-compact{grid-template-columns:repeat(auto-fill,minmax(360px,1fr));}'
      + '.results.view-media{grid-template-columns:repeat(auto-fill,minmax(320px,1fr));}'
      + '.results.view-list{grid-template-columns:1fr;}'
      + '.results.view-collections{grid-template-columns:repeat(auto-fill,minmax(280px,1fr));}'
      + '.results.view-working{grid-template-columns:1fr;}'
      + '.working-filter-row{grid-template-columns:minmax(220px,1fr) auto auto;}'
      + '.working-folder-card{cursor:pointer;}'
      + '.working-thumb{display:flex;align-items:center;justify-content:center;background:rgba(56,189,248,0.10);}'
      + '.working-thumb ha-icon{--mdc-icon-size:38px;color:#7dd3fc;}'
      + '.results.media-hidden .thumb-wrap,.results.media-hidden .media-wrap,.results.media-hidden .list-wrap{display:none !important;}'
      + '.results.media-hidden .model-card.view-compact,.results.media-hidden .model-card.view-list{grid-template-columns:1fr;}'
      + '.collection-browser-header{grid-column:1/-1;display:grid;grid-template-columns:minmax(0,1.5fr) auto;gap:14px;padding:16px 18px;border-radius:20px;border:1px solid rgba(56,189,248,0.18);background:radial-gradient(circle at top left,rgba(56,189,248,0.14),transparent 40%),linear-gradient(180deg,rgba(15,23,42,0.24),rgba(15,23,42,0.12));box-shadow:0 10px 28px rgba(15,23,42,0.16);}'
      + '.collection-browser-header.system-bucket{border-color:rgba(245,158,11,0.24);background:radial-gradient(circle at top left,rgba(245,158,11,0.16),transparent 42%),linear-gradient(180deg,rgba(15,23,42,0.24),rgba(15,23,42,0.12));}'
      + '.collection-browser-header-copy{display:grid;gap:6px;min-width:0;}'
      + '.collection-browser-header-kicker{font-size:10px;font-weight:900;letter-spacing:.08em;text-transform:uppercase;color:#7dd3fc;}'
      + '.collection-browser-header.system-bucket .collection-browser-header-kicker{color:#fbbf24;}'
      + '.collection-browser-header-title{font-size:22px;font-weight:900;line-height:1.1;color:var(--primary-text-color);}'
      + '.collection-browser-header-subtitle{font-size:12px;color:var(--secondary-text-color);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}'
      + '.collection-browser-header-note{font-size:12px;color:var(--primary-text-color);opacity:.88;}'
      + '.collection-browser-header-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(92px,1fr));gap:8px;min-width:min(100%,320px);}'
      + '.collection-header-stat{padding:10px 12px;border-radius:14px;border:1px solid rgba(148,163,184,0.16);background:rgba(15,23,42,0.18);min-width:0;}'
      + '.collection-header-stat-label{font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--secondary-text-color);}'
      + '.collection-header-stat-value{margin-top:4px;font-size:20px;font-weight:900;line-height:1;color:var(--primary-text-color);}'
      + '.collection-card{display:grid;gap:10px;padding:14px;border-radius:18px;border:1px solid var(--line);background:linear-gradient(180deg,rgba(15,23,42,0.24),rgba(15,23,42,0.12));box-shadow:0 8px 22px rgba(15,23,42,0.16);align-content:start;min-width:0;}'
      + '.collection-breadcrumb{grid-column:1/-1;display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:6px;}'
      + '.collection-breadcrumb-sep{font-size:12px;color:var(--secondary-text-color);}'
      + '.collection-breadcrumb-up{display:inline-flex;align-items:center;gap:6px;}'
      + '.collection-breadcrumb-up ha-icon{--mdc-icon-size:15px;}'
      + '.collection-card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;}'
      + '.collection-card-kicker{display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap;min-width:0;}'
      + '.collection-card-type,.collection-card-kicker-meta{display:inline-flex;align-items:center;justify-content:center;min-height:22px;padding:0 8px;border-radius:999px;border:1px solid rgba(148,163,184,0.16);font-size:10px;font-weight:900;letter-spacing:.05em;text-transform:uppercase;}'
      + '.collection-card-type{background:rgba(56,189,248,0.14);border-color:rgba(56,189,248,0.24);color:#bae6fd;}'
      + '.collection-card.system-bucket .collection-card-type{background:rgba(245,158,11,0.16);border-color:rgba(245,158,11,0.24);color:#fde68a;}'
      + '.collection-card-kicker-meta{background:rgba(148,163,184,0.10);color:var(--secondary-text-color);}'
      + '.collection-card.collection-card-view-media{gap:12px;}'
      + '.collection-card.collection-card-view-media .collection-mosaic{gap:8px;}'
      + '.collection-card.collection-card-view-media .collection-mosaic-tile{border-radius:14px;aspect-ratio:16/10;}'
      + '.collection-card.collection-card-view-list{grid-template-columns:128px minmax(0,1fr) auto auto;align-items:center;column-gap:14px;}'
      + '.collection-card.collection-card-view-list .collection-list-thumb{min-width:0;}'
      + '.collection-card.collection-card-view-list .collection-mosaic{gap:4px;}'
      + '.collection-card.collection-card-view-list .collection-mosaic-tile{border-radius:10px;}'
      + '.collection-list-main{display:grid;gap:6px;min-width:0;}'
      + '.collection-list-title-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;min-width:0;}'
      + '.collection-list-title-row .collection-name{font-size:16px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}'
      + '.collection-list-stats{display:grid;grid-template-columns:repeat(2,minmax(88px,1fr));gap:8px;min-width:min(100%,240px);}'
      + '.collection-list-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;}'
      + '.collection-mosaic{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;}'
      + '.collection-mosaic-tile{position:relative;aspect-ratio:4/3;overflow:hidden;border-radius:12px;background:rgba(15,23,42,0.26);border:1px solid rgba(148,163,184,0.16);display:flex;align-items:center;justify-content:center;}'
      + '.collection-mosaic-tile img{width:100%;height:100%;object-fit:cover;display:block;}'
      + '.collection-mosaic-tile img[data-thumbnail-lazy-url]:not([src]){font-size:0;color:transparent;background:linear-gradient(120deg,rgba(148,163,184,0.18),rgba(148,163,184,0.06));background-size:200% 100%;animation:shimmer 1.25s ease-in-out infinite;}'
      + '.collection-mosaic-tile.empty{background:linear-gradient(180deg,rgba(30,41,59,0.55),rgba(15,23,42,0.28));}'
      + '.collection-mosaic-tile.empty ha-icon{--mdc-icon-size:24px;color:rgba(148,163,184,0.72);}'
      + '.collection-pile-preview{position:relative;display:block;min-height:196px;overflow:hidden;border-radius:16px;background:radial-gradient(circle at top left,rgba(245,158,11,0.10),transparent 38%),linear-gradient(180deg,rgba(30,41,59,0.44),rgba(15,23,42,0.16));border:1px solid rgba(245,158,11,0.14);}'
      + '.collection-card.collection-card-view-media .collection-pile-preview{min-height:232px;}'
      + '.collection-pile-photo{position:absolute;width:92px;height:112px;padding:7px 7px 18px;border-radius:6px;background:rgba(248,250,252,0.94);box-shadow:0 10px 20px rgba(15,23,42,0.24);transform-origin:center;overflow:hidden;}'
      + '.collection-pile-photo .collection-mosaic-tile{width:100%;height:100%;aspect-ratio:auto;border-radius:3px;border-color:rgba(15,23,42,0.10);background:rgba(226,232,240,0.88);}'
      + '.collection-pile-photo .collection-mosaic-tile.empty{background:linear-gradient(180deg,rgba(203,213,225,0.92),rgba(148,163,184,0.72));}'
      + '.collection-pile-photo .collection-mosaic-tile.empty ha-icon{color:rgba(51,65,85,0.72);}'
      + '.collection-pile-photo .collection-mosaic-tile img[data-thumbnail-lazy-url]:not([src]){background:linear-gradient(120deg,rgba(148,163,184,0.34),rgba(148,163,184,0.12));}'
      + '.collection-pile-photo.pile-1{left:16px;top:34px;transform:rotate(-10deg);}'
      + '.collection-pile-photo.pile-2{left:74px;top:14px;transform:rotate(8deg);}'
      + '.collection-pile-photo.pile-3{left:142px;top:44px;transform:rotate(-4deg);}'
      + '.collection-pile-photo.pile-4{left:212px;top:20px;transform:rotate(10deg);}'
      + '.collection-pile-photo.pile-5{left:92px;top:96px;transform:rotate(-12deg);opacity:0.74;}'
      + '.collection-pile-photo.pile-6{left:192px;top:96px;transform:rotate(6deg);opacity:0.56;}'
      + '.collection-card.collection-card-view-media .collection-pile-photo.pile-1{left:22px;top:42px;}'
      + '.collection-card.collection-card-view-media .collection-pile-photo.pile-2{left:98px;top:18px;}'
      + '.collection-card.collection-card-view-media .collection-pile-photo.pile-3{left:186px;top:48px;}'
      + '.collection-card.collection-card-view-media .collection-pile-photo.pile-4{left:278px;top:20px;}'
      + '.collection-card.collection-card-view-media .collection-pile-photo.pile-5{left:122px;top:112px;}'
      + '.collection-card.collection-card-view-media .collection-pile-photo.pile-6{left:252px;top:116px;}'
      + '.collection-pile-fade{position:absolute;left:0;right:0;bottom:0;height:42%;background:linear-gradient(180deg,rgba(15,23,42,0),rgba(15,23,42,0.72));pointer-events:none;}'
      + '.collection-empty-preview{font-size:11px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;color:var(--secondary-text-color);}'
      + '.collection-name{font-size:15px;font-weight:800;line-height:1.25;}'
      + '.collection-meta{font-size:12px;color:var(--secondary-text-color);}'
      + '.collection-meta-row{padding-top:2px;}'
      + '.collection-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;}'
      + '.collection-stat{padding:9px 10px;border-radius:12px;background:rgba(15,23,42,0.18);border:1px solid rgba(148,163,184,0.14);min-width:0;}'
      + '.collection-stat-label{font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--secondary-text-color);}'
      + '.collection-stat-value{font-size:18px;font-weight:800;line-height:1.15;color:var(--primary-text-color);}'
      + '.collection-open{justify-self:start;margin-top:2px;}'
      + '.collection-models{font-size:12px;line-height:1.4;opacity:.9;}'
      + '.model-card{position:relative;min-width:0;border-radius:20px;border:1px solid var(--line);background:linear-gradient(180deg,rgba(15,23,42,0.22),rgba(15,23,42,0.14));overflow:visible;display:grid;cursor:pointer;transition:border-color .18s ease;contain:layout paint style;}'
      + '.model-card::after{content:"";position:absolute;inset:0;border-radius:inherit;background:transparent;box-shadow:inset 5px 0 0 transparent;opacity:0;transition:opacity .16s ease,box-shadow .16s ease;pointer-events:none;}'
      + '.model-card:hover{border-color:var(--accent-strong);box-shadow:0 6px 16px rgba(15,23,42,0.18);}'
      + '.model-card:focus-visible{outline:none;box-shadow:0 0 0 2px rgba(96,165,250,0.34);border-color:var(--accent-strong);}'
      + '.model-card.view-compact{grid-template-columns:minmax(148px,188px) minmax(0,1fr);grid-template-areas:"thumb main" "full full";column-gap:18px;row-gap:10px;padding:14px;align-items:start;}'
      + '.model-card.view-media{grid-template-rows:auto 1fr;}'
      + '.model-card.view-list{grid-template-columns:88px minmax(0,1fr);column-gap:10px;padding:10px 12px;align-items:start;}'
      + '.model-card.is-in-queue::after{opacity:1;box-shadow:inset 5px 0 0 var(--queue-border-color,#a07cff);}'
      + '.model-card.is-idea{border:2px solid rgba(250,204,21,0.66);}'
      + '.model-card.is-idea:hover{border-color:rgba(250,204,21,0.82);}'
      + '.thumb-wrap{position:relative;overflow:hidden;border-radius:16px;background:var(--surface-2);}'
      + '.view-compact .compact-wrap{grid-area:thumb;}'
      + '.view-compact .compact-main{grid-area:main;}'
      + '.view-compact .compact-full{grid-area:full;padding:2px 0 0;}'
      + '.compact-wrap{min-height:156px;}'
      + '.list-wrap{min-height:88px;}'
      + '.media-wrap{border-radius:18px 18px 0 0;}'
      + '.thumb,.media-preview{display:flex;align-items:center;justify-content:center;background:rgba(15,23,42,0.24);overflow:hidden;}'
      + '.thumb{width:100%;height:156px;}'
      + '.list-thumb{min-height:88px;height:88px;}'
      + '.media-preview{width:100%;aspect-ratio:16/9;min-height:220px;}'
      + '.thumb img,.media-preview img{width:100%;height:100%;object-fit:cover;display:block;}'
      // Suppress alt-text "flash" on lazy-loaded thumbnails: hide alt text and show a subtle placeholder gradient until src is set (issue #1383)
      + '.thumb img[data-thumbnail-lazy-url]:not([src]),.media-preview img[data-thumbnail-lazy-url]:not([src]){font-size:0;color:transparent;background:linear-gradient(120deg,rgba(148,163,184,0.18),rgba(148,163,184,0.06));}'
      + '.thumb img[data-thumbnail-lazy-url]:not([src]),.media-preview img[data-thumbnail-lazy-url]:not([src]){background-size:200% 100%;animation:shimmer 1.25s ease-in-out infinite;}'
      + '.thumb img[data-thumbnail-lazy-url]:not([src])::before,.media-preview img[data-thumbnail-lazy-url]:not([src])::before{content:"";display:block;width:100%;height:100%;}'
      // Failed lazy thumbnail: show neutral placeholder instead of permanent shimmer
      + '.thumb img[data-thumbnail-failed]:not([src]),.media-preview img[data-thumbnail-failed]:not([src]){font-size:0;color:transparent;animation:none;background:var(--card-background-color,rgba(148,163,184,0.08));}'
      + '.model-card.skeleton{cursor:default;pointer-events:none;}'
      + '.skeleton-block{position:relative;overflow:hidden;background:linear-gradient(120deg,rgba(148,163,184,0.14),rgba(148,163,184,0.05),rgba(148,163,184,0.14));background-size:200% 100%;animation:shimmer 1.25s ease-in-out infinite;border-radius:10px;}'
      + '.skeleton-line{height:12px;}'
      + '.skeleton-line.w-50{width:50%;}'
      + '.skeleton-line.w-55{width:55%;}'
      + '.skeleton-line.w-60{width:60%;}'
      + '.skeleton-line.w-70{width:70%;}'
      + '.skeleton-line.w-75{width:75%;}'
      + '.skeleton-line.w-80{width:80%;}'
      + '.skeleton-line.w-85{width:85%;}'
      + '.skeleton-line.w-90{width:90%;}'
      + '.skeleton-line.w-95{width:95%;}'
      + '.thumb-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;opacity:.72;}'
      + '.thumb-empty ha-icon{--mdc-icon-size:28px;}'
      + '.thumb-empty-text{font-size:10px;margin-top:4px;}'
      + '.body{display:grid;gap:10px;min-width:0;padding:14px 16px 16px;}'
      + '.compact-main,.compact-full{gap:8px;}'
      + '.view-compact .body,.view-list .body{padding:0;}'
      + '.view-compact .compact-main{padding-top:46px;}'
      + '.compact-top-actions{position:absolute;top:14px;right:14px;display:flex;justify-content:flex-end;align-items:center;gap:8px;z-index:2;}'
      + '.compact-top-actions .advanced-menu-shell{margin-left:0;}'
      + '.compact-title-row{display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px;min-width:0;}'
      + '.compact-last-printed{font-size:11px;font-weight:700;color:var(--secondary-text-color);padding-top:2px;}'
      + '.favorite-action{border-color:rgba(245,194,66,0.34);}'
      + '.favorite-action.is-active{background:rgba(245,194,66,0.20);color:#f5c242;border-color:rgba(245,194,66,0.52);}'
      + '.favorite-action.is-active:hover,.favorite-action.is-active:focus-visible{background:rgba(245,194,66,0.26);color:#f5c242;border-color:rgba(245,194,66,0.62);box-shadow:0 0 0 1px rgba(245,194,66,0.28);transform:translateY(-1px);outline:none;}'
      + '.queue-action{border-color:rgba(160,124,255,0.30);background:rgba(100,60,180,0.14);color:#c4b5fd;position:relative;}'
      + '.queue-action:hover,.queue-action:focus-visible{background:rgba(160,124,255,0.20);color:#ede9fe;border-color:rgba(160,124,255,0.52);box-shadow:0 0 0 1px rgba(160,124,255,0.20),0 8px 18px rgba(15,23,42,0.20);transform:translateY(-1px);outline:none;}'
      + '.queue-action.has-queue-entries{background:rgba(160,124,255,0.24);color:#ddd6fe;border-color:rgba(160,124,255,0.50);}'
      + '.queue-action.has-queue-entries:hover,.queue-action.has-queue-entries:focus-visible{background:rgba(160,124,255,0.30);color:#f5f3ff;border-color:rgba(196,181,253,0.66);box-shadow:0 0 0 1px rgba(160,124,255,0.28),0 10px 22px rgba(15,23,42,0.22);transform:translateY(-1px);outline:none;}'
      + '.queue-count-badge{position:absolute;top:-8px;right:-8px;width:18px;height:18px;min-width:18px;padding:0;border-radius:50%;background:#a07cff;color:#fff;font-size:10px;font-weight:800;display:flex;align-items:center;justify-content:center;line-height:1;box-sizing:border-box;pointer-events:none;border:1px solid rgba(15,23,42,0.6);}'
      + '.header-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;column-gap:12px;row-gap:8px;}'
      + '.media-body{gap:8px;padding:12px 14px 14px;}'
      + '.media-title-row{display:grid;grid-template-columns:minmax(0,1fr);gap:6px;align-items:start;}'
      + '.media-footer-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:start;}'
      + '.media-actions-row{display:grid;grid-template-columns:minmax(0,1fr);gap:8px;align-items:start;}'
      + '.media-actions{display:flex;gap:8px;align-items:center;justify-content:flex-end;}'
      + '.title-cluster{display:grid;gap:6px;min-width:0;}'
      + '.title{margin:0;font-size:15px;font-weight:800;line-height:1.35;overflow-wrap:anywhere;}'
      + '.subtle-line,.status-line,.tags{display:flex;flex-wrap:wrap;align-items:center;gap:6px;min-width:0;}'
      + '.chip-row{display:flex;flex-wrap:wrap;align-items:center;gap:6px;min-width:0;}'
      + '.provenance-row{margin-top:2px;}'
      + '.header-actions{display:flex;align-items:flex-start;justify-content:flex-end;gap:8px;}'
      + '.chip{display:inline-flex;align-items:center;gap:6px;min-height:26px;font-size:11px;font-weight:700;padding:4px 9px;border-radius:999px;background:var(--chip-bg);border:1px solid var(--chip-line);color:var(--primary-text-color);}'
      + 'button.chip{font:inherit;cursor:pointer;}'
      + '.chip.neutral{background:rgba(148,163,184,0.14);border-color:rgba(148,163,184,0.26);}'
      + '.chip.queue{background:rgba(16,185,129,0.16);border-color:rgba(16,185,129,0.32);}'
      + '.chip.complete{background:rgba(96,165,250,0.14);border-color:rgba(96,165,250,0.30);}'
      + '.chip.subtle-chip{background:rgba(15,23,42,0.08);border-color:rgba(148,163,184,0.16);color:var(--secondary-text-color);}'
      + '.chip.tag-chip{background:rgba(96,165,250,0.10);border-color:rgba(96,165,250,0.20);}'
      + '.chip.origin-chip{background:rgba(99,102,241,0.18);border-color:rgba(165,180,252,0.34);}'
      + '.chip.publish-chip{background:rgba(56,189,248,0.14);border-color:rgba(56,189,248,0.28);}'
      + '.chip.signal-chip{background:rgba(34,197,94,0.14);border-color:rgba(34,197,94,0.30);}'
      + '.chip.source-chip{max-width:100%;}'
      + '.entity-type-pill{display:inline-flex;align-items:center;justify-content:center;min-height:22px;padding:0 8px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(148,163,184,0.10);font-size:10px;font-weight:800;color:var(--secondary-text-color);}'
      + '.entity-type-pill.idea{background:rgba(250,204,21,0.18);border-color:rgba(250,204,21,0.34);color:#fef3c7;}'
      + '.archived-pill{display:inline-flex;align-items:center;gap:4px;min-height:22px;padding:0 8px;border-radius:999px;border:1px solid rgba(148,163,184,0.30);background:rgba(148,163,184,0.14);font-size:10px;font-weight:800;color:#94a3b8;width:fit-content;margin-right:6px;vertical-align:middle;}'
      + '.archived-pill ha-icon{--mdc-icon-size:12px;}'
      + '.model-card.is-archived{border:2px solid rgba(148,163,184,0.55);opacity:0.72;}'
      + '.model-card.is-archived:hover{opacity:1;}'
      // When an archived card is also in-queue, the 2px border pushes the padding-box (where ::after sits) inward,
      // so the ribbon's rounded corner traces a tighter arc than the outer card edge. Extend ::after to the
      // border-box so its inherited 20px radius aligns with the outer border curve. (issue: ribbon/border mismatch)
      + '.model-card.is-archived.is-in-queue::after{inset:-2px;}'
      // Same alignment fix for idea cards, which also use a 2px outer border.
      + '.model-card.is-idea.is-in-queue::after{inset:-2px;}'

      + '.chip.file-kind-chip{font-size:10px;min-height:24px;padding:3px 8px;display:inline-flex;align-items:center;gap:6px;}'
      + '.chip.file-kind-chip .icon-svg{width:16px;height:16px;flex-shrink:0;}'
      + '.chip.file-kind-chip .chip-label{font-weight:700;letter-spacing:.01em;}'
      + '.chip.file-kind-chip .chip-count{font-weight:600;}'
      + '.chip.file-kind-model{background:rgba(0,137,123,0.16);border-color:rgba(125,211,200,0.30);color:#7dd3c8;}'
      + '.chip.file-kind-image{background:rgba(37,99,235,0.16);border-color:rgba(147,197,253,0.34);color:#93c5fd;}'
      + '.chip.file-kind-other{background:rgba(245,158,11,0.16);border-color:rgba(252,211,77,0.34);color:#fcd34d;}'
      + '.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;}'
      + '.compact-metrics .metric-value{font-size:13px;}'
      + '.metric{display:grid;gap:3px;padding:10px 12px;border-radius:14px;border:1px solid rgba(148,163,184,0.16);background:rgba(15,23,42,0.08);}'
      + '.metric-label{font-size:10px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;color:var(--secondary-text-color);}'
      + '.metric-value{font-size:14px;font-weight:800;line-height:1.2;}'
      + '.compact-tags-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:10px;}'
      + '.compact-file-kinds{display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-end;gap:6px;min-height:26px;}'
      + '.compact-action-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px;justify-content:flex-start;}'
      + '.list-body{padding:0;gap:8px;}'
      + '.list-top-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:10px;}'
      + '.list-title-block{display:grid;gap:6px;min-width:0;}'
      + '.list-action-stack{display:grid;gap:6px;justify-items:end;}'
      + '.list-top-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;}'
      + '.list-top-actions .advanced-menu-shell{margin-left:0;}'
      + '.list-metrics-shell{padding:8px;border-radius:14px;border:1px solid rgba(148,163,184,0.16);background:rgba(15,23,42,0.09);}'
      + '.list-metrics{gap:6px;}'
      + '.list-bottom-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:10px;}'
      + '.list-file-kinds{justify-content:flex-end;}'
      + '.tag-project-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:10px;}'
      + '.media-status-chip{display:flex;justify-content:flex-end;}'
      + '.card-mode-pill{position:absolute;top:10px;z-index:1;display:inline-flex;align-items:center;min-height:24px;padding:0 8px;border-radius:999px;border:1px solid rgba(255,255,255,0.24);background:rgba(15,23,42,0.82);font-size:10px;font-weight:800;color:#fff;}'
      + '.media-counter{display:inline-flex;align-items:center;justify-content:center;min-height:24px;padding:0 8px;border-radius:999px;border:1px solid rgba(255,255,255,0.24);background:rgba(15,23,42,0.82);font-size:10px;font-weight:800;color:#fff;white-space:nowrap;}'
      + '.card-mode-pill{left:10px;}'
      + '.card-mode-pill.list-mode{top:8px;left:8px;}'
      + '.media-overlay{position:absolute;inset:0;pointer-events:none;}'
      + '.media-overlay-actions{position:absolute;top:10px;right:10px;display:flex;align-items:center;gap:8px;pointer-events:auto;z-index:2;}'
      + '.media-overlay-actions .advanced-menu-shell{pointer-events:auto;}'
      + '.media-overlay-actions .icon-action{background:rgba(15,23,42,0.74);border-color:rgba(255,255,255,0.24);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);box-shadow:0 8px 18px rgba(15,23,42,0.22);}'
      + '.media-overlay-actions .icon-action:hover,.media-overlay-actions .icon-action:focus-visible{background:rgba(30,41,59,0.9);border-color:rgba(255,255,255,0.42);box-shadow:0 10px 22px rgba(15,23,42,0.28),0 0 0 1px rgba(255,255,255,0.18);}'
      + '.media-gallery-nav{position:absolute;left:10px;right:10px;bottom:10px;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;pointer-events:none;}'
      + '.media-gallery-nav .media-counter{justify-self:center;pointer-events:none;}'
      + '.media-gallery-nav .icon-action{pointer-events:auto;}'
      + '.advanced-menu-shell{position:relative;display:flex;justify-content:flex-end;}'
      + '.icon-action,.advanced-action{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:34px;padding:0 10px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(15,23,42,0.14);color:var(--primary-text-color);font-size:11px;font-weight:700;cursor:pointer;transition:background .16s ease,color .16s ease,box-shadow .16s ease,transform .16s ease,border-color .16s ease;}'
      + '.icon-action{width:34px;padding:0;}'
      + '.icon-action ha-icon{--mdc-icon-size:18px;}'
      + '.icon-action:hover,.icon-action:focus-visible{background:rgba(148,163,184,0.18);color:var(--primary-text-color);box-shadow:0 0 0 1px rgba(255,255,255,0.10);transform:translateY(-1px);outline:none;}'
      + '.icon-action:active{transform:translateY(0);}'
      + '.icon-action.viewer{background:rgba(0,137,123,0.16);color:#7dd3c8;border-color:rgba(125,211,200,0.24);}'
      + '.icon-action.viewer:hover,.icon-action.viewer:focus-visible{background:rgba(0,137,123,0.28);color:#b6fff3;box-shadow:0 0 0 1px rgba(125,211,200,0.26);transform:translateY(-1px);outline:none;}'
      + '.icon-action.advanced{border:1px solid rgba(148,163,184,0.28);background:rgba(15,23,42,0.78);color:var(--primary-text-color);}'
      + '.icon-action.advanced:hover,.icon-action.advanced:focus-visible{background:rgba(30,41,59,0.96);color:var(--primary-text-color);border-color:rgba(148,163,184,0.54);box-shadow:0 0 0 1px rgba(255,255,255,0.16),0 8px 20px rgba(15,23,42,0.22);transform:translateY(-1px);outline:none;}'
      + '.advanced-menu{position:absolute;top:40px;right:0;z-index:4;display:none;gap:8px;min-width:220px;padding:10px;border-radius:16px;border:1px solid var(--line-strong);background:rgba(15,23,42,0.96);box-shadow:0 18px 34px rgba(15,23,42,0.28);}'
      + '.advanced-menu.is-open{display:grid;}'
      + '.advanced-action{justify-content:flex-start;width:100%;padding:0 12px;border-radius:12px;background:rgba(148,163,184,0.10);}'
      + '.advanced-action:disabled{opacity:.5;cursor:not-allowed;transform:none;box-shadow:none;}'
      + '.advanced-action.primary{background:rgba(96,165,250,0.14);border-color:rgba(96,165,250,0.26);}'
      + '.advanced-action.danger{background:rgba(185,28,28,0.14);border-color:rgba(185,28,28,0.26);color:#f87171;}'
      + '.advanced-action.danger:hover,.advanced-action.danger:focus-visible{background:rgba(185,28,28,0.24);border-color:rgba(185,28,28,0.44);color:#fca5a5;}'
      + '.advanced-action ha-icon{--mdc-icon-size:16px;}'
      + '.advanced-group-label{font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--secondary-text-color);padding:2px 2px 0;}'
      + '.state-row{padding:20px;border-radius:16px;border:1px dashed rgba(148,163,184,0.24);background:rgba(148,163,184,0.10);font-size:13px;color:var(--secondary-text-color);}'
      + '.state-row.error{background:rgba(185,28,28,0.16);color:var(--primary-text-color);}'
      + '.queue-dialog-backdrop{position:fixed;inset:0;z-index:30;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(2,6,23,0.72);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);}'
      + '.queue-dialog{width:min(680px,calc(100vw - 32px));max-height:calc(100vh - 40px);display:grid;grid-template-rows:auto auto minmax(0,1fr) auto;overflow:hidden;border-radius:20px;border:1px solid var(--line-strong);background:rgba(15,23,42,0.97);box-shadow:0 24px 48px rgba(2,6,23,0.42);}'
      + '.queue-dialog-header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:18px 20px 14px;border-bottom:1px solid rgba(148,163,184,0.18);}'
      + '.queue-dialog-header h3{margin:0;font-size:18px;font-weight:800;}'
      + '.modal-close-btn{width:34px;height:34px;display:inline-flex;align-items:center;justify-content:center;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(15,23,42,0.14);color:var(--primary-text-color);font-size:14px;font-weight:700;cursor:pointer;}'
      + '.modal-close-btn:hover,.modal-close-btn:focus-visible{background:rgba(148,163,184,0.18);border-color:rgba(148,163,184,0.38);outline:none;}'
      + '.queue-dialog-subtitle{margin-top:4px;font-size:12px;color:var(--secondary-text-color);}'
      + '.queue-dialog-tabs{display:flex;gap:8px;padding:12px 20px;border-bottom:1px solid rgba(148,163,184,0.16);}'
      + '.queue-dialog-tab{min-height:34px;padding:0 14px;border-radius:999px;border:1px solid rgba(148,163,184,0.22);background:rgba(15,23,42,0.16);color:var(--secondary-text-color);font-size:12px;font-weight:800;cursor:pointer;}'
      + '.queue-dialog-tab.active{background:rgba(96,165,250,0.18);border-color:rgba(96,165,250,0.34);color:var(--primary-text-color);}'
      + '.queue-dialog-body{display:grid;gap:12px;padding:18px 20px;overflow:auto;}'
      + '.queue-dialog-summary,.queue-dialog-existing-note,.queue-dialog-note,.queue-dialog-metrics{padding:12px 14px;border-radius:14px;border:1px solid rgba(148,163,184,0.18);background:rgba(148,163,184,0.08);font-size:13px;line-height:1.45;}'
      + '.queue-dialog-existing-note{background:rgba(96,165,250,0.12);border-color:rgba(96,165,250,0.24);color:#dbeafe;}'
      + '.queue-dialog-field{display:grid;gap:6px;}'
      + '.queue-dialog-field span{font-size:11px;font-weight:800;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.04em;}'
      + '.queue-dialog-target-state,.queue-dialog-notes{width:100%;box-sizing:border-box;border-radius:12px;border:1px solid rgba(148,163,184,0.26);background:rgba(15,23,42,0.16);color:var(--primary-text-color);padding:10px 12px;font:inherit;}'
      + '.queue-dialog-target-state{appearance:none;-webkit-appearance:none;color-scheme:dark;background-color:rgba(15,23,42,0.92);}'
      + '.queue-dialog-target-state:focus{outline:none;border-color:rgba(96,165,250,0.46);box-shadow:0 0 0 1px rgba(96,165,250,0.26);}'
      + '.queue-dialog-target-state option{background-color:rgba(15,23,42,0.98);color:var(--primary-text-color);}'
      + '.queue-dialog-toolbar{display:flex;gap:8px;flex-wrap:wrap;}'
      + '.queue-dialog-file-list{display:grid;gap:10px;}'
      + '.queue-dialog-file-block{display:grid;gap:8px;padding:12px;border-radius:16px;border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.12);}'
      + '.queue-dialog-file-toggle,.queue-dialog-plate-toggle{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:38px;padding:0 12px;border-radius:12px;border:1px solid rgba(148,163,184,0.20);background:rgba(15,23,42,0.14);color:var(--primary-text-color);font-size:12px;font-weight:700;cursor:pointer;text-align:left;}'
      + '.queue-dialog-file-toggle span{font-size:11px;color:var(--secondary-text-color);font-weight:700;}'
      + '.queue-dialog-file-toggle.active,.queue-dialog-plate-toggle.active{background:rgba(96,165,250,0.18);border-color:rgba(96,165,250,0.34);}'
      + '.queue-dialog-plates{display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));}'
      + '.queue-dialog-error{padding:12px 14px;border-radius:14px;border:1px solid rgba(248,113,113,0.32);background:rgba(127,29,29,0.22);color:#fecaca;font-size:13px;}'
      + '.queue-dialog-footer{display:flex;align-items:center;justify-content:flex-end;gap:10px;padding:14px 20px 18px;border-top:1px solid rgba(148,163,184,0.16);}'
      + '.queue-dialog-submit{background:rgba(96,165,250,0.22);border-color:rgba(96,165,250,0.34);}'
      + '.idea-create-backdrop{position:fixed;inset:0;z-index:30;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(2,6,23,0.72);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);}'
      + '.idea-create-dialog{width:min(680px,calc(100vw - 32px));max-height:calc(100vh - 40px);display:grid;grid-template-rows:auto minmax(0,1fr) auto;overflow:hidden;border-radius:20px;border:1px solid var(--line-strong);background:rgba(15,23,42,0.97);box-shadow:0 24px 48px rgba(2,6,23,0.42);}'
      + '.idea-create-header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:18px 20px 14px;border-bottom:1px solid rgba(148,163,184,0.18);}'
      + '.idea-create-header h3{margin:0;font-size:18px;font-weight:800;}'
      + '.idea-create-subtitle{margin-top:4px;font-size:12px;color:var(--secondary-text-color);}'
      + '.idea-create-body{display:grid;gap:12px;padding:18px 20px;overflow:auto;}'
      + '.idea-create-field{display:grid;gap:6px;}'
      + '.idea-create-field span{font-size:11px;font-weight:800;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.04em;}'
      + '.idea-create-field strong{color:#fecaca;}'
      + '.idea-create-input{width:100%;box-sizing:border-box;border-radius:12px;border:1px solid rgba(148,163,184,0.26);background:rgba(15,23,42,0.16);color:var(--primary-text-color);padding:10px 12px;font:inherit;}'
      + '.idea-create-input:focus{outline:none;border-color:rgba(96,165,250,0.46);box-shadow:0 0 0 1px rgba(96,165,250,0.26);}'
      + '.idea-create-error{padding:12px 14px;border-radius:14px;border:1px solid rgba(248,113,113,0.32);background:rgba(127,29,29,0.22);color:#fecaca;font-size:13px;}'
      + '.idea-create-footer{display:flex;align-items:center;justify-content:flex-end;gap:10px;padding:14px 20px 18px;border-top:1px solid rgba(148,163,184,0.16);}'
      + '.idea-create-submit{background:rgba(250,204,21,0.22);border-color:rgba(250,204,21,0.4);}'
      + '.collection-feedback-toast{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:10px 0 2px;padding:12px 14px;border-radius:16px;border:1px solid rgba(96,165,250,0.24);background:rgba(30,64,175,0.16);box-shadow:0 10px 22px rgba(15,23,42,0.16);}'
      + '.collection-feedback-toast.error{border-color:rgba(248,113,113,0.32);background:rgba(127,29,29,0.22);}'
      + '.collection-feedback-copy{font-size:13px;line-height:1.4;color:var(--primary-text-color);}'
      + '.collection-feedback-dismiss{width:30px;min-width:30px;height:30px;display:inline-flex;align-items:center;justify-content:center;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(15,23,42,0.16);color:var(--primary-text-color);font-size:13px;font-weight:800;cursor:pointer;}'
      + '.collection-feedback-dismiss:hover,.collection-feedback-dismiss:focus-visible{outline:none;background:rgba(148,163,184,0.18);border-color:rgba(148,163,184,0.38);}'
      + '.collection-action-backdrop{position:fixed;inset:0;z-index:30;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(2,6,23,0.72);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);}'
      + '.collection-action-dialog{width:min(620px,calc(100vw - 32px));max-height:calc(100vh - 40px);display:grid;grid-template-rows:auto minmax(0,1fr) auto;overflow:hidden;border-radius:20px;border:1px solid var(--line-strong);background:rgba(15,23,42,0.97);box-shadow:0 24px 48px rgba(2,6,23,0.42);}'
      + '.collection-action-header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:18px 20px 14px;border-bottom:1px solid rgba(148,163,184,0.18);}'
      + '.collection-action-header h3{margin:0;font-size:18px;font-weight:800;}'
      + '.collection-action-subtitle{margin-top:4px;font-size:12px;color:var(--secondary-text-color);}'
      + '.collection-action-body{display:grid;gap:12px;padding:18px 20px;overflow:auto;}'
      + '.collection-action-note,.collection-action-danger-note,.collection-action-summary{padding:12px 14px;border-radius:14px;border:1px solid rgba(148,163,184,0.18);background:rgba(148,163,184,0.08);font-size:13px;line-height:1.45;}'
      + '.collection-action-danger-note{border-color:rgba(248,113,113,0.28);background:rgba(127,29,29,0.22);color:#fecaca;}'
      + '.collection-action-summary{display:grid;gap:4px;}'
      + '.collection-action-summary strong{font-size:14px;line-height:1.3;color:var(--primary-text-color);}'
      + '.collection-action-summary span{font-size:12px;color:var(--secondary-text-color);}'
      + '.collection-action-field{display:grid;gap:6px;}'
      + '.collection-action-field span{font-size:11px;font-weight:800;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.04em;}'
      + '.collection-action-input,.collection-action-select{width:100%;box-sizing:border-box;border-radius:12px;border:1px solid rgba(148,163,184,0.26);background:rgba(15,23,42,0.16);color:var(--primary-text-color);padding:10px 12px;font:inherit;}'
      + '.collection-action-input:focus,.collection-action-select:focus{outline:none;border-color:rgba(96,165,250,0.46);box-shadow:0 0 0 1px rgba(96,165,250,0.26);}'
      + '.collection-action-select{appearance:none;-webkit-appearance:none;color-scheme:dark;background-color:rgba(15,23,42,0.92);}'
      + '.collection-action-select option{background-color:rgba(15,23,42,0.98);color:var(--primary-text-color);}'
      + '.collection-action-error{padding:12px 14px;border-radius:14px;border:1px solid rgba(248,113,113,0.32);background:rgba(127,29,29,0.22);color:#fecaca;font-size:13px;}'
      + '.collection-action-footer{display:flex;align-items:center;justify-content:flex-end;gap:10px;padding:14px 20px 18px;border-top:1px solid rgba(148,163,184,0.16);}'
      + '.collection-action-submit{background:rgba(96,165,250,0.22);border-color:rgba(96,165,250,0.34);}'
      + '.collection-action-submit.danger{background:rgba(185,28,28,0.20);border-color:rgba(248,113,113,0.34);color:#fecaca;}'
      + '@keyframes shimmer{0%{background-position:200% 0;}100%{background-position:-200% 0;}}'
      + '@keyframes compact-enter{0%{opacity:0;transform:translateY(4px);}100%{opacity:1;transform:translateY(0);}}'
      + '@keyframes spin-refresh{from{transform:rotate(0deg);}to{transform:rotate(360deg);}}'
      + '@media (max-width: 820px){.model-card.view-compact,.model-card.view-list{grid-template-columns:1fr;}.compact-wrap,.list-wrap{min-height:180px;}.thumb,.list-thumb{height:180px;}.tag-project-row,.header-row,.compact-title-row,.compact-tags-row,.media-title-row,.media-footer-row,.list-top-row,.list-bottom-row{grid-template-columns:minmax(0,1fr);}.media-status-chip,.header-actions,.media-actions{justify-content:flex-start;}.compact-file-kinds,.list-file-kinds,.list-top-actions{justify-content:flex-start;}.list-action-stack{justify-items:start;}.title-row{align-items:flex-start;}.title-right{width:100%;justify-content:space-between;}.filter-row{grid-template-columns:1fr 1fr;}.inline-select{justify-content:space-between;}.inline-select .tuning-select{min-width:72px;}.page-control-strip{justify-content:flex-start;}.media-overlay-actions{left:10px;right:auto;}.collection-browser-header{grid-template-columns:1fr;}.collection-browser-header-stats{min-width:0;}.collection-stats{grid-template-columns:repeat(2,minmax(0,1fr));}.collection-card.collection-card-view-list{grid-template-columns:1fr;}.collection-list-stats{grid-template-columns:repeat(2,minmax(0,1fr));min-width:0;}.collection-list-actions{justify-content:flex-start;}}'
      + '.model-card-checkbox{position:absolute;top:10px;left:10px;z-index:2;width:20px;height:20px;cursor:pointer;}'
      + '.model-card-checkbox input[type="checkbox"]{width:20px;height:20px;margin:0;cursor:pointer;accent-color:var(--accent);}'
      + '.model-card.is-selected{border-color:var(--accent-strong);background:linear-gradient(180deg,rgba(96,165,250,0.12),rgba(96,165,250,0.06));}'
      + '.model-card.is-selected::before{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;border:2px solid var(--accent-strong);opacity:0;animation:pulse-border 1.2s ease-in-out;}'
      + '.bulkbar{display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap;padding:10px 12px;border-radius:16px;border:1px solid var(--line);background:var(--surface-1);color:var(--primary-text-color);font-size:13px;}'
      + '.bulkbar .count{font-weight:700;min-width:120px;flex:0 0 auto;}'
      + '.bulkbar .right{margin-left:auto;display:flex;gap:8px;flex:0 0 auto;}'
      + '.bulkbar .bulk-btn{min-height:32px;padding:0 14px;border-radius:8px;border:1px solid var(--line);background:var(--surface-2);color:var(--primary-text-color);font-size:12px;font-weight:600;cursor:pointer;transition:all 200ms ease;}'
      + '.bulkbar .bulk-btn:hover{background:var(--surface-3);border-color:var(--accent);}'
      + '.bulkbar .bulk-btn:active{transform:scale(0.98);}'
      + '.bulkbar .bulk-btn:disabled{opacity:.5;cursor:not-allowed;}'
      + '.ms-toggle ha-icon{--mdc-icon-size:18px;}'
      + '.ms-toggle.active,.ms-toggle:hover{background:var(--accent);border-color:var(--accent-strong);color:#fff;}'
      + '.page-control-strip.multi-select-active{border:1px solid var(--accent-strong);background:rgba(96,165,250,0.08);}'
      + '.page-control-strip.multi-select-active .ms-count{font-weight:700;min-width:120px;flex:0 0 auto;font-size:13px;}'
      + '.page-control-strip.multi-select-active .ms-spacer{flex:1 1 auto;}'
      + '.page-control-strip.multi-select-active .bulk-btn{min-height:32px;padding:0 14px;border-radius:8px;border:1px solid var(--line);background:var(--surface-2);color:var(--primary-text-color);font-size:12px;font-weight:600;cursor:pointer;transition:all 200ms ease;}'
      + '.page-control-strip.multi-select-active .bulk-btn:hover{background:var(--surface-3);border-color:var(--accent);}'
      + '.page-control-strip.multi-select-active .bulk-btn:active{transform:scale(0.98);}'
      + '.page-control-strip.multi-select-active .bulk-btn.exit{border-color:var(--error-color,#ef4444);color:var(--error-color,#ef4444);}'
      + '.page-control-strip.multi-select-active .bulk-btn.exit:hover{background:rgba(239,68,68,0.1);}'
      + '.page-control-strip.multi-select-active .bulk-btn.exit ha-icon{--mdc-icon-size:14px;vertical-align:middle;margin-right:2px;}'
      + '.page-control-strip.multi-select-active .bulk-source-select{min-height:32px;padding:0 10px;border-radius:8px;border:1px solid var(--line);background:var(--surface-2);color:var(--primary-text-color);font-size:12px;font-weight:600;cursor:pointer;transition:all 200ms ease;appearance:auto;-webkit-appearance:auto;color-scheme:dark;}'
      + '.page-control-strip.multi-select-active .bulk-source-select:hover{background:var(--surface-3);border-color:var(--accent);}'
      + '.page-control-strip.multi-select-active .bulk-source-select:focus{outline:none;border-color:var(--accent-strong);box-shadow:0 0 0 1px rgba(96,165,250,0.26);}'
      + '@media (max-width: 900px){.catalog-layout{grid-template-columns:minmax(0,1fr);}.toolbar-icon-btn.left-nav-toggle{display:inline-flex;}.nav-context-chip{display:inline-flex;}.left-nav{position:fixed;top:0;left:0;bottom:0;width:min(320px,84vw);max-height:none;border-radius:0 16px 16px 0;z-index:20;transform:translateX(-110%);transition:transform 180ms ease;box-shadow:0 18px 44px rgba(2,6,23,0.46);background:var(--card-background-color, #1e293b);gap:6px;padding:14px 12px;border-left:none;align-content:start;}.left-nav .left-nav-section{gap:4px;}.left-nav .left-nav-section + .left-nav-section{padding-top:8px;}.left-nav .left-nav-item{min-height:32px;}.left-nav .left-nav-collapse{display:none;}.left-nav.drawer-open{transform:translateX(0);}.left-nav.collapsed{width:min(320px,84vw);padding:12px;}.left-nav.collapsed .left-nav-title-wrap{display:flex;}.left-nav.collapsed .left-nav-title-text,.left-nav.collapsed .left-nav-section-label,.left-nav.collapsed .left-nav-item-label,.left-nav.collapsed .left-nav-item-count{display:initial;}.left-nav.collapsed .left-nav-item{justify-content:space-between;padding:0 8px;}.left-nav.collapsed .left-nav-collapse{display:none;position:static;opacity:1;pointer-events:none;}.left-nav-backdrop{display:block;position:fixed;inset:0;z-index:19;border:0;background:rgba(2,6,23,0.55);opacity:0;pointer-events:none;transition:opacity 180ms ease;}.left-nav-backdrop.open{opacity:1;pointer-events:auto;}}'
      + '@media (max-width: 560px){.shell{padding:6px 10px 10px;}.card-title{display:none;}.nav-context-chip{max-width:min(180px,40vw);}.filter-row{grid-template-columns:1fr;}.title-left,.title-right{width:100%;}.sort-group{width:100%;justify-content:space-between;}.import-menu-items{right:auto;left:0;}.toolbar-group{width:100%;justify-content:flex-start;}.page-status{padding-left:0;}.media-preview{min-height:180px;}.metrics{grid-template-columns:1fr;}.advanced-menu{left:0;right:auto;min-width:min(260px,calc(100vw - 56px));}.collection-browser-header-title{font-size:18px;}.collection-browser-header-subtitle{white-space:normal;}.collection-card-top{align-items:center;}.collection-stats{grid-template-columns:1fr 1fr;}}';
      this._contentRoot = document.createElement('ha-card');
      this.shadowRoot.textContent = '';
      this.shadowRoot.appendChild(this._persistentStyle);
      this.shadowRoot.appendChild(this._contentRoot);
    }

    this._contentRoot.classList.toggle('queue-dialog-host-open', !!(this._queueDialogOpen || this._ideaCreateDialogOpen || (this._collectionActionDialog && this._collectionActionDialog.open)));

    // Preserve focus across the innerHTML reset below. Without this, any
    // active input (most visibly the search box "#mc-q") loses focus on every
    // re-render — including the debounced re-render that fires while the
    // user is still typing — making the filter inputs unusable.
    var focusSnapshot = this._captureActiveInputState();

    this._contentRoot.innerHTML = ''
      + '  <div class="shell">'
      + '    <div class="catalog-layout' + (this._leftNavCollapsed ? ' nav-collapsed' : '') + '">'
      + '      <button class="left-nav-backdrop' + (this._leftNavDrawerOpen ? ' open' : '') + '" type="button" data-action="close-left-nav-drawer" aria-label="Close catalog navigation"></button>'
      + this._renderLeftNav()
      + '      <div class="main-pane">'
      + '        <div class="shell-header">'
      + this._renderHeaderTitleRow()
      + this._renderFilterBar()
      + this._renderPageControlStrip()
      + '        </div>'
      + this._renderCollectionActionFeedback()
      + '        <div class="results' + (this._loading ? ' is-loading' : '') + ' view-' + this._escapeHtml(this._browserScope === "collections" ? this._collectionResultsViewClass() : this._viewMode) + (this._showMedia ? '' : ' media-hidden') + '">' + resultsHtml + '</div>'
      + this._renderBottomMirrorStrip()
      + '      </div>'
      + '    </div>'
      + this._renderQueueDialog()
      + this._renderIdeaCreateDialog()
      + this._renderCollectionActionDialog()
      + '  </div>';

    this._restoreActiveInputState(focusSnapshot);

    // Focus management for left-nav drawer open/close
    if (this._focusNavFirstItemAfterRender) {
      this._focusNavFirstItemAfterRender = false;
      var nav = this.shadowRoot.querySelector('.left-nav.drawer-open');
      if (nav) {
        var firstItem = nav.querySelector('button.left-nav-item, label.left-nav-type-toggle');
        if (firstItem) {
          requestAnimationFrame(function() { try { firstItem.focus(); } catch(_e) {} });
        }
      }
    }
    if (this._focusNavToggleAfterRender) {
      this._focusNavToggleAfterRender = false;
      var toggle = this.shadowRoot.querySelector('.left-nav-toggle') || this.shadowRoot.querySelector('.nav-context-chip');
      if (toggle) {
        requestAnimationFrame(function() { try { toggle.focus(); } catch(_e) {} });
      }
    }
    if (this._focusCollectionActionPrimaryAfterRender) {
      this._focusCollectionActionPrimaryAfterRender = false;
      var dialogPrimary = this.shadowRoot.querySelector('.collection-action-input, .collection-action-select, .collection-action-submit');
      if (dialogPrimary) {
        requestAnimationFrame(function() { try { dialogPrimary.focus(); } catch(_e) {} });
      }
    }

    this._scheduleThumbnailObserverSetup(0);
    if (progressiveRemainder && progressiveRemainder.length) {
      this._scheduleProgressiveResultsAppend(progressiveRemainder, renderEpoch);
    }
    var renderEnd = (window.performance && typeof window.performance.now === "function") ? window.performance.now() : Date.now();
    this._lastRenderPerf = {
      renderMs: Math.max(0, Math.round(renderEnd - renderStart)),
      visibleCount: Array.isArray(visibleResults) ? visibleResults.length : 0,
      progressiveRemainder: progressiveRemainder ? progressiveRemainder.length : 0,
      viewMode: this._viewMode,
      browserScope: this._browserScope,
      navPerf: this._pendingNavPerf ? {
        action: this._pendingNavPerf.action,
        targetPage: this._pendingNavPerf.targetPage,
      } : null,
      timestamp: Date.now(),
    };
    this._recordPerfSample("render", this._lastRenderPerf);
    this._finalizeNavPerfAfterRender();
  }
}

customElements.define("model-catalog-browser-card", ModelCatalogBrowserCard);

Object.assign(ModelCatalogBrowserCard.prototype, {
  _resetQueueDialogState() {
    this._queueDialogController.resetState();
  },
  _closeQueueDialog() {
    this._queueDialogController.close();
  },
  _openQueueDialog(modelRef, modelName, entries, options) {
    return this._queueDialogController.open(modelRef, modelName, entries, options);
  },
  _setQueueDialogMode(mode) {
    this._queueDialogController.setMode(mode);
  },
  _setQueueDialogAllPlatesSelected(selected) {
    this._queueDialogController.setAllPlatesSelected(selected);
  },
  _toggleQueueDialogFileSelection(fileId) {
    this._queueDialogController.toggleFileSelection(fileId);
  },
  _toggleQueueDialogPlateSelection(fileId, plateId) {
    this._queueDialogController.togglePlateSelection(fileId, plateId);
  },
  _getQueueDialogMetrics() {
    return this._queueDialogController.getMetrics();
  },
  _queueDialogPrimarySummary() {
    return this._queueDialogController.primarySummary();
  },
  _canSubmitQueueDialog() {
    return this._queueDialogController.canSubmit();
  },
  _submitQueueDialog() {
    return this._queueDialogController.submit();
  },
  _normalizeQueueDialogTargetState(state) {
    return normalizeQueueDialogTargetState(state);
  },
  _queueDialogTargetStateLabel(state) {
    return queueDialogTargetStateLabel(state);
  },
  _renderQueueDialog() {
    return this._queueDialogController.render();
  },
});

