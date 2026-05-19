import { setupThumbnailLazyObserver, addShimmerAnimation, getCachedThumbnailObjectUrl } from './thumbnail-lazy-loader.js?v=2';
import { addUnifiedQueueEntry } from '../common/unified-queue-api-client.js?v=1';
import { UnifiedQueueDialogController, normalizeQueueDialogTargetState, queueDialogTargetStateLabel } from '../common/unified-queue-dialog.js?v=1';

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
    this._refreshSpin = false;
    this._activeActionMenu = "";
    this._mediaGalleryIndices = {};
    this._modelDetailCache = {};
    this._loadingModelMedia = {};
    this._pendingLoad = null;
    this._debounceHandle = null;
    this._deferredRenderHandle = null;
    this._modelSidecarUrl = "";
    this._unifiedQueueByModelRef = {};
    this._frequentsTuning = {
      window_days: 90,
      min_prints: 3,
      backfill_weight: 0.5,
      initialized: false,
    };
    this._visibilityCounts = { active: 0, archived: 0 };
    this._entityTypeFilters = {
      showIdeas: false,
      showWorkingGroups: false,
    };
    this._frequentsRailItems = [];
    this._frequentsRailVisible = this._readFrequentsRailVisibility();
    this._queueDialogController = new UnifiedQueueDialogController(this, {
      loadSourceDetail: this._loadQueueDialogSourceDetail.bind(this),
      addEntry: async ({ queueApiBase, printerId, payload }) => {
        await addUnifiedQueueEntry({ queueApiBase, printerId, payload });
      },
      afterSubmit: async () => {
        await this._refreshData();
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
    this._didInitialRender = false;
    this._hasAttemptedLoad = false;
    this._lastAppliedScopeStamp = 0;
    this._catalogScope = "curated";
    this._thumbnailObserver = null;
    this._renderRAFId = null;
    this._persistentStyle = null;
    this._contentRoot = null;

    // Multi-select primitive (#1401 Phase 0 Foundations)
    this._selectedModelRefs = new Set();
    this._selectionChangeCallbacks = [];
    this._multiSelectMode = false;
  }

  _defaultFilters() {
    return {
      q: "",
      collection: "",
      creator: "",
      tag: "",
      sort: "recent",
      favorites_only: false,
      frequents_only: false,
      has_other_files: false,
      show_archived: false,
    };
  }

  _normalizedEntityType(value) {
    var normalized = String(value || "").trim().toLowerCase();
    if (normalized === "idea" || normalized === "working_group" || normalized === "model") {
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
    if (normalized === "idea") {
      return !!this._entityTypeFilters.showIdeas;
    }
    if (normalized === "working_group") {
      return !!this._entityTypeFilters.showWorkingGroups;
    }
    return true;
  }

  _entityTypeCounts() {
    var counts = { model: 0, idea: 0, working_group: 0 };
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
    var filtered = [];
    for (var i = 0; i < this._results.length; i++) {
      var candidate = this._results[i];
      if (this._isEntityTypeVisible(this._entityTypeForModel(candidate))) {
        filtered.push(candidate);
      }
    }
    return filtered;
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
      return ["model", "working_group"];
    }
    if (normalized === "working_group") {
      return ["model"];
    }
    return [];
  }

  _entityTypeBadgeLabel(entityType) {
    var normalized = this._normalizedEntityType(entityType);
    if (normalized === "idea") {
      return "Idea";
    }
    if (normalized === "working_group") {
      return "Working Group";
    }
    return "";
  }

  _workingGroupIdForModel(model) {
    var fields = model && model.custom_fields && typeof model.custom_fields === "object" ? model.custom_fields : {};
    var candidates = [
      fields.working_group_id,
      fields.published_from_group_id,
      model && model.working_group_id,
    ];
    for (var i = 0; i < candidates.length; i++) {
      var candidate = Number(candidates[i] || 0);
      if (Number.isFinite(candidate) && candidate > 0) {
        return Math.round(candidate);
      }
    }

    var sourceOriginUrl = String(fields.source_origin_url || model && model.source_origin_url || "").trim();
    var match = sourceOriginUrl.match(/working-group:\/\/(\d+)/i);
    if (match) {
      var parsed = Number(match[1] || 0);
      if (Number.isFinite(parsed) && parsed > 0) {
        return Math.round(parsed);
      }
    }
    return 0;
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

  _readFrequentsRailVisibility() {
    try {
      if (window && window.localStorage) {
        var stored = window.localStorage.getItem("model-catalog-frequents-rail-visible");
        if (stored === "false") {
          return false;
        }
      }
    } catch (_error) {
    }
    return true;
  }

  _persistFrequentsRailVisibility() {
    try {
      if (window && window.localStorage) {
        window.localStorage.setItem("model-catalog-frequents-rail-visible", this._frequentsRailVisible ? "true" : "false");
      }
    } catch (_error) {
    }
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

  disconnectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.removeEventListener("click", this._boundClick);
      this.shadowRoot.removeEventListener("input", this._boundInput);
      this.shadowRoot.removeEventListener("change", this._boundChange);
      this.shadowRoot.removeEventListener("keydown", this._boundKeyDown);
      this.shadowRoot.removeEventListener("wheel", this._boundWheel);
    }
    window.removeEventListener("model-catalog-data-changed", this._boundCatalogDataChanged);
    this._cancelScheduledApply();
    if (this._renderRAFId) {
      cancelAnimationFrame(this._renderRAFId);
      this._renderRAFId = null;
    }
    if (this._deferredRenderHandle) {
      window.clearTimeout(this._deferredRenderHandle);
      this._deferredRenderHandle = null;
    }
    if (this._thumbnailObserver && typeof this._thumbnailObserver.disconnect === "function") {
      try { this._thumbnailObserver.disconnect(); } catch (_e) { /* ignore */ }
      this._thumbnailObserver = null;
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
    this._filters.collection = read("#mc-collection");
    this._filters.creator = read("#mc-creator");
    this._filters.tag = read("#mc-tag");
    this._filters.sort = read("#mc-sort") || "recent";
    var perPageTop = Number(read("#mc-per-page") || 0);
    var perPageBottom = Number(read("#mc-per-page-bottom") || 0);
    var perPage = Number.isFinite(perPageTop) && perPageTop > 0 ? perPageTop : perPageBottom;
    if (Number.isFinite(perPage) && perPage > 0) {
      this._pagination.per_page = Math.max(1, Math.min(96, perPage));
    }
    this._filters.favorites_only = !!(root.querySelector("#mc-favorites-only") && root.querySelector("#mc-favorites-only").checked);
    this._filters.frequents_only = !!(root.querySelector("#mc-frequents-only") && root.querySelector("#mc-frequents-only").checked);
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

  _requestLoad(page, refresh) {
    var targetPage = Math.max(1, Number(page || 1));
    if (!this._hass) {
      return;
    }
    if (this._loading) {
      this._pendingLoad = { page: targetPage, refresh: !!refresh };
      return;
    }
    this._loadPage(targetPage, refresh);
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

    this._loading = true;
    this._error = "";
    this._doRender();

    var shared = window.ModelCatalogIntakeShared;
    var stampSnapshot = shared && typeof shared.getModelCatalogScopeStamp === "function"
      ? shared.getModelCatalogScopeStamp(this._catalogScope || "curated")
      : 0;

    try {
      var requestPayload = {
        q: this._filters.q,
        collection: this._filters.collection,
        creator: this._filters.creator,
        tag: this._filters.tag,
        sort: this._filters.sort,
        favorites_only: !!this._filters.favorites_only,
        frequents_only: !!this._filters.frequents_only,
        frequent_window_days: this._clampInteger(this._frequentsTuning.window_days, 90, 7, 3650),
        frequent_min_prints: this._clampInteger(this._frequentsTuning.min_prints, 3, 1, 9999),
        frequent_backfill_weight: 0.5,
        has_other_files: !!this._filters.has_other_files,
        show_archived: !!this._filters.show_archived,
        refresh: !!refresh,
        include_supplements: true,
        page: Math.max(1, Number(page || 1)),
        per_page: this._pagination.per_page,
      };

      var data = await this._callServiceWithResponse("rest_command", "model_catalog_search_models", requestPayload);
      var supplements = data && data.supplements && typeof data.supplements === "object" ? data.supplements : {};
      var supplementFrequentCandidates = Array.isArray(supplements.frequent_candidates) ? supplements.frequent_candidates : null;
      var supplementFavoriteCandidates = Array.isArray(supplements.favorite_candidates) ? supplements.favorite_candidates : null;
      this._results = Array.isArray(data && data.results) ? data.results : [];
      this._frequentsRailItems = this._buildFrequentsRailItems(
        supplementFrequentCandidates || this._results,
        supplementFavoriteCandidates || this._results
      );
      var responseFilters = data && data.filters && typeof data.filters === "object" ? data.filters : {};
      var responseVisibility = data && data.visibility && typeof data.visibility === "object" ? data.visibility : {};
      var responseVisibilityCounts = responseVisibility && responseVisibility.counts && typeof responseVisibility.counts === "object"
        ? responseVisibility.counts
        : {};
      this._visibilityCounts = {
        active: Math.max(0, Number(responseVisibilityCounts.active || 0) || 0),
        archived: Math.max(0, Number(responseVisibilityCounts.archived || 0) || 0),
      };
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
      if (Object.prototype.hasOwnProperty.call(responseFilters, "frequents_only")) {
        this._filters.frequents_only = !!responseFilters.frequents_only;
      }
      if (Object.prototype.hasOwnProperty.call(responseFilters, "show_archived")) {
        this._filters.show_archived = !!responseFilters.show_archived;
      }

      var pagination = data && data.pagination ? data.pagination : {};
      this._pagination.page = Number(pagination.page || requestPayload.page) || 1;
      this._pagination.per_page = Number(pagination.per_page || this._pagination.per_page) || this._pagination.per_page;
      this._pagination.total = Number(pagination.total || 0) || 0;
      this._pagination.total_pages = Number(pagination.total_pages || 0) || 0;
      if (stampSnapshot > (Number(this._lastAppliedScopeStamp) || 0)) {
        this._lastAppliedScopeStamp = stampSnapshot;
      }
      this._refreshUnifiedQueueIndex().then(function () {
        if (this._loading) {
          return;
        }
        if (this._viewMode === "media") {
          this._scheduleDeferredRender(70);
          return;
        }
        this._render();
      }.bind(this));
    } catch (error) {
      this._results = [];
      this._frequentsRailItems = [];
      this._pagination.page = 1;
      this._pagination.total = 0;
      this._pagination.total_pages = 0;
      this._unifiedQueueByModelRef = {};
      this._visibilityCounts = { active: 0, archived: 0 };
      this._error = error && error.message ? String(error.message) : "Could not load model catalog.";
    } finally {
      this._loading = false;
      this._refreshSpin = false;
      this._render();
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

  async _refreshUnifiedQueueIndex() {
    try {
      var queuePayload = await this._callServiceWithResponse("rest_command", "model_catalog_list_unified_queue_entries", {
        printer_id: this._config && this._config.queue_printer_id ? this._config.queue_printer_id : "p1",
        source_kind: "catalog_model",
        sort: "rank:asc",
        limit: 200,
        offset: 0,
      });
      var entries = Array.isArray(queuePayload && queuePayload.entries) ? queuePayload.entries : [];
      var byModelRef = {};
      for (var i = 0; i < entries.length; i++) {
        var entry = entries[i] || {};
        if (String(entry.source_kind || "").toLowerCase() !== "catalog_model") {
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
      this._unifiedQueueByModelRef = byModelRef;
    } catch (_error) {
      this._unifiedQueueByModelRef = {};
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
    if (event.key !== "Enter") {
      return;
    }
    var target = event.target;
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
      this._syncFrequentsTuningFromHelpers(true);
      this._error = "";
      this._activeActionMenu = "";
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
      var nextScope = scope === "collections" ? "collections" : "models";
      if (this._browserScope !== nextScope) {
        this._browserScope = nextScope;
        this._render();
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
      this._cancelScheduledApply();
      this._requestLoad(1, false);
      this._render();
      return;
    }

    if (action === "toggle-frequents-filter") {
      this._filters.frequents_only = !this._filters.frequents_only;
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

    if (action === "toggle-show-ideas-filter") {
      this._entityTypeFilters.showIdeas = !this._entityTypeFilters.showIdeas;
      this._render();
      return;
    }

    if (action === "toggle-show-working-groups-filter") {
      this._entityTypeFilters.showWorkingGroups = !this._entityTypeFilters.showWorkingGroups;
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
      this._filters.collection = collectionName;
      this._cancelScheduledApply();
      this._requestLoad(1, false);
      this._render();
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
      var actionMenuRef = String(target.getAttribute("data-model-ref") || "").trim();
      this._activeActionMenu = this._activeActionMenu === actionMenuRef ? "" : actionMenuRef;
      this._updateActionMenus();
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

    if (action === "toggle-frequents-rail") {
      event.preventDefault();
      event.stopPropagation();
      this._frequentsRailVisible = !this._frequentsRailVisible;
      this._persistFrequentsRailVisibility();
      this._render();
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
      this._requestLoad(1, false);
      return;
    }

    if (action === "prev-page" && this._currentPage() > 1) {
      this._syncFormIntoFilters();
      this._requestLoad(this._currentPage() - 1, false);
      return;
    }

    if (action === "next-page" && this._currentPage() < this._pageCount()) {
      this._syncFormIntoFilters();
      this._requestLoad(this._currentPage() + 1, false);
      return;
    }

    if (action === "last-page") {
      this._syncFormIntoFilters();
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
      var ideaName = window.prompt("Idea title:", "");
      var normalizedIdeaName = String(ideaName || "").trim();
      if (!normalizedIdeaName) {
        return;
      }
      var ideaNotes = window.prompt("Idea notes (optional):", "") || "";
      var ideaLinksRaw = window.prompt("Idea external links (optional, comma/newline-separated, use url|label):", "") || "";
      var ideaSketchUrl = window.prompt("Idea sketch image URL (optional):", "") || "";
      try {
        await this._createIdeaEntity({
          name: normalizedIdeaName,
          notes: String(ideaNotes || "").trim(),
          external_links: this._parseIdeaExternalLinks(ideaLinksRaw),
          sketch_image: String(ideaSketchUrl || "").trim(),
        });
        this._entityTypeFilters.showIdeas = true;
        this._activeActionMenu = "";
        this._error = "";
        this._requestLoad(1, true);
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not create idea.";
        this._render();
      }
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

    if (action === "open-working-files") {
      event.preventDefault();
      event.stopPropagation();
      var groupId = Number(target.getAttribute("data-working-group-id") || 0);
      var groupTitle = String(target.getAttribute("data-model-name") || "Working Files").trim();
      this._activeActionMenu = "";
      this._openWorkingFilesExplorer(groupId, groupTitle);
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

    if (action.indexOf("queue-") === 0) {
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
    if (normalized === "in_progress") {
      return "printing";
    }
    if (normalized === "done") {
      return "done";
    }
    if (this._isUnifiedQueueActiveState(normalized)) {
      return "queued";
    }
    return "none";
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
    var files = Array.isArray(model.files) ? model.files : [];
    if (!files.length) {
      throw new Error("Selected model has no queueable files.");
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

  _queueDialogPrimarySummary() {
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
    if (!Array.isArray(this._queueDialogFiles) || this._queueDialogFiles.length === 0) {
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

    var targetState = this._queueDialogMode === "quick"
      ? "up_next"
      : this._normalizeQueueDialogTargetState(this._queueDialogTargetState);

    var payload = {
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
      await this._loadPage(this._currentPage(), false);
    } catch (error) {
      this._queueDialogSubmitting = false;
      this._queueDialogError = error && error.message ? String(error.message) : "Could not add to queue.";
      this._render();
    }
  }

  async _listUnifiedQueueEntriesForModel(modelRef) {
    var payload = await this._callServiceWithResponse("rest_command", "model_catalog_list_unified_queue_entries", {
      printer_id: this._config && this._config.queue_printer_id ? this._config.queue_printer_id : "p1",
      source_kind: "catalog_model",
      sort: "rank:asc",
      limit: 200,
      offset: 0,
    });
    var entries = Array.isArray(payload && payload.entries) ? payload.entries : [];
    return entries.filter(function (entry) {
      var sourceRef = String((entry && (entry.source_id || entry.source_ref)) || "").trim();
      return sourceRef === modelRef;
    });
  }

  _preferredUnifiedQueueEntry(entries) {
    if (!Array.isArray(entries) || !entries.length) {
      return null;
    }
    var preferred = null;
    for (var i = 0; i < entries.length; i++) {
      var candidate = entries[i] || {};
      if (!preferred) {
        preferred = candidate;
        continue;
      }
      var preferredActive = this._isUnifiedQueueActiveState(preferred.state);
      var candidateActive = this._isUnifiedQueueActiveState(candidate.state);
      if (candidateActive && !preferredActive) {
        preferred = candidate;
        continue;
      }
      if (candidateActive === preferredActive && Number(candidate.rank || 0) < Number(preferred.rank || 0)) {
        preferred = candidate;
      }
    }
    return preferred;
  }

  async _addUnifiedQueueEntryForModel(modelRef, options) {
    var body = options && typeof options === "object" ? options : {};
    return addUnifiedQueueEntry({
      queueApiBase: this._resolveModelSidecarUrl() + '/api/v1',
      printerId: this._config && this._config.queue_printer_id ? this._config.queue_printer_id : "p1",
      payload: {
        source_kind: "catalog_model",
        source_id: modelRef,
        copies: body.copies != null ? body.copies : 1,
        state: body.state || "preparing",
        rank: body.rank != null ? body.rank : 0,
        queue_notes: body.queue_notes || "",
        // Default to quick_add so the entry is populated with the model's
        // file_units and plate_units (otherwise the Details popup shows no
        // files or plates because the v1 add endpoint only seeds units when
        // quick_add or selected_files are provided).
        quick_add: body.quick_add != null ? !!body.quick_add : true,
      },
    });
  }

  async _patchUnifiedQueueEntry(queueEntryId, patchBody) {
    return this._callServiceWithResponse("rest_command", "model_catalog_update_unified_queue_entry", Object.assign({
      queue_entry_id: queueEntryId,
    }, patchBody || {}));
  }

  async _deleteUnifiedQueueEntry(queueEntryId) {
    return this._callServiceWithResponse("rest_command", "model_catalog_delete_unified_queue_entry", {
      queue_entry_id: queueEntryId,
    });
  }

  async _transitionQueueEntryToDone(entry) {
    var entryId = String(entry && entry.queue_entry_id || "").trim();
    var state = String(entry && entry.state || "").trim().toLowerCase();
    if (!entryId || !state) {
      return;
    }
    var paths = {
        backlog: ["up_next", "preparing", "ready", "in_progress", "done"],
        up_next: ["preparing", "ready", "in_progress", "done"],
      preparing: ["ready", "in_progress", "done"],
      ready: ["in_progress", "done"],
      in_progress: ["done"],
      blocked: ["done"],
      done: [],
    };
    var steps = paths[state] || [];
    for (var i = 0; i < steps.length; i++) {
      await this._patchUnifiedQueueEntry(entryId, { state: steps[i] });
    }
  }

  async _applyUnifiedQueueAction(action, modelRef, options) {
    var entries = await this._listUnifiedQueueEntriesForModel(modelRef);
    var preferred = this._preferredUnifiedQueueEntry(entries);
    var actionOptions = options && typeof options === "object" ? options : {};
    var modelName = String(actionOptions.modelName || "Model").trim() || "Model";

    if (action === "queue-clear") {
      for (var i = 0; i < entries.length; i++) {
        var entryId = String(entries[i] && entries[i].queue_entry_id || "").trim();
        if (entryId) {
          var entryState = String(entries[i].state || "").toLowerCase();
          // Require confirmation if entry is not in backlog or up_next
          if (["preparing", "ready", "in_progress", "blocked", "done"].indexOf(entryState) >= 0) {
            var shouldContinue = confirm(
              "This queue entry is in " + entryState + " state. Are you sure you want to dequeue it?"
            );
            if (!shouldContinue) {
              return;
            }
          }
          await this._deleteUnifiedQueueEntry(entryId);
        }
      }
      return true;
    }

    if (action === "queue-add") {
      await this._openQueueDialog(modelRef, modelName, entries, { intent: "add", defaultState: "up_next" });
      return false;
    }

    if (action === "queue-re-add") {
        await this._openQueueDialog(modelRef, modelName, entries, { intent: "re-add", defaultState: "backlog" });
      return false;
    }

    if (action === "queue-mark-queued") {
      if (!preferred || String(preferred.state || "").toLowerCase() === "done") {
          await this._addUnifiedQueueEntryForModel(modelRef, { state: "up_next" });
        return true;
      }
      var preferredState = String(preferred.state || "").toLowerCase();
      if (preferredState === "backlog") {
          await this._patchUnifiedQueueEntry(preferred.queue_entry_id, { state: "up_next" });
      }
      return true;
    }

    if (action === "queue-mark-done") {
      if (!preferred) {
        await this._addUnifiedQueueEntryForModel(modelRef, { state: "done" });
        return true;
      }
      await this._transitionQueueEntryToDone(preferred);
      return true;
    }

    if (action === "queue-priority-up" || action === "queue-priority-down") {
      if (!preferred || String(preferred.state || "").toLowerCase() === "done") {
        await this._addUnifiedQueueEntryForModel(modelRef, { state: "up_next", rank: 0 });
        return true;
      }
      var delta = action === "queue-priority-up" ? -1 : 1;
      var nextRank = Math.max(0, Number(preferred.rank || 0) + delta);
      await this._patchUnifiedQueueEntry(preferred.queue_entry_id, { rank: nextRank });
      return true;
    }

    return true;
  }

  _renderQueueDialog() {
    if (!this._queueDialogOpen) {
      return "";
    }

    var metrics = this._getQueueDialogMetrics();
    var canSubmit = this._canSubmitQueueDialog();
    var existingNote = this._queueDialogExistingCount > 0
      ? '<div class="queue-dialog-existing-note">This model already has ' + this._escapeHtml(String(this._queueDialogExistingCount)) + ' queue entr' + (this._queueDialogExistingCount === 1 ? 'y' : 'ies') + '. Re-add is allowed.</div>'
      : "";
    var planBody = this._queueDialogLoading
      ? '<div class="queue-dialog-note">Loading model files and plates...</div>'
      : this._queueDialogFiles.length === 0
      ? '<div class="queue-dialog-note">No queueable files available for this model.</div>'
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
      + '      <button class="queue-dialog-tab' + (this._queueDialogMode === 'quick' ? ' active' : '') + '" type="button" data-action="queue-dialog-mode" data-mode="quick">Quick</button>'
      + '      <button class="queue-dialog-tab' + (this._queueDialogMode === 'plan' ? ' active' : '') + '" type="button" data-action="queue-dialog-mode" data-mode="plan">Plan</button>'
      + '    </div>'
      + '    <div class="queue-dialog-body">'
      + existingNote
      + (this._queueDialogMode === 'quick'
          ? '<div class="queue-dialog-summary">' + this._escapeHtml(this._queueDialogPrimarySummary()) + '</div>'
          : '<div class="queue-dialog-summary">Choose plates, target state, and notes before creating the queue entry.</div>'
            + '<label class="queue-dialog-field"><span>Target state</span><select class="queue-dialog-target-state"><option value="backlog"' + (this._queueDialogTargetState === 'backlog' ? ' selected' : '') + '>Backlog</option><option value="up_next"' + (this._queueDialogTargetState === 'up_next' ? ' selected' : '') + '>Up Next</option><option value="preparing"' + (this._queueDialogTargetState === 'preparing' ? ' selected' : '') + '>Preparing</option><option value="ready"' + (this._queueDialogTargetState === 'ready' ? ' selected' : '') + '>Ready</option></select></label>'
            + '<label class="queue-dialog-field"><span>Notes</span><textarea class="queue-dialog-notes" data-queue-dialog-notes="true" rows="3" placeholder="Optional operator notes...">' + this._escapeHtml(this._queueDialogNotes) + '</textarea></label>'
            + '<div class="queue-dialog-metrics">Selected ' + this._escapeHtml(String(metrics.selectedPlates)) + ' plates across ' + this._escapeHtml(String(metrics.selectedFiles)) + ' files.</div>'
            + planBody)
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
      var modelRef = String(button.getAttribute("data-model-ref") || "").trim();
      var open = !!this._activeActionMenu && this._activeActionMenu === modelRef;
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

    for (var j = 0; j < this._frequentsRailItems.length; j++) {
      var railModel = this._frequentsRailItems[j];
      if (this._modelRef(railModel) !== targetRef) {
        continue;
      }
      railModel.model_favorite = !!isFavorite;
      if (!railModel.custom_fields || typeof railModel.custom_fields !== "object") {
        railModel.custom_fields = {};
      }
      railModel.custom_fields.model_favorite = !!isFavorite;
      if (!railModel.structured_metadata || typeof railModel.structured_metadata !== "object") {
        railModel.structured_metadata = {};
      }
      if (!railModel.structured_metadata.catalog_signals || typeof railModel.structured_metadata.catalog_signals !== "object") {
        railModel.structured_metadata.catalog_signals = {};
      }
      railModel.structured_metadata.catalog_signals.model_favorite = !!isFavorite;
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

  _isModelFrequent(model) {
    var frequents = model && model.frequents && typeof model.frequents === "object" ? model.frequents : {};
    var ranking = model && model.ranking && typeof model.ranking === "object" ? model.ranking : {};
    if (this._coerceBoolish(model && model.model_frequent) === true) {
      return true;
    }
    if (this._coerceBoolish(frequents.is_frequent) === true) {
      return true;
    }
    return Number(ranking.frequent_score || 0) > 0;
  }

  _modelCatalogVisibility(model) {
    var normalized = String(model && model.catalog_visibility || "").trim().toLowerCase();
    if (normalized === "active" || normalized === "archived") {
      return normalized;
    }
    var fields = model && model.custom_fields && typeof model.custom_fields === "object" ? model.custom_fields : {};
    normalized = String(fields.catalog_visibility || "").trim().toLowerCase();
    if (normalized === "active" || normalized === "archived") {
      return normalized;
    }
    var structured = model && model.structured_metadata && typeof model.structured_metadata === "object" ? model.structured_metadata : {};
    var catalogSignals = structured && structured.catalog_signals && typeof structured.catalog_signals === "object" ? structured.catalog_signals : {};
    normalized = String(catalogSignals.catalog_visibility || "").trim().toLowerCase();
    if (normalized === "active" || normalized === "archived") {
      return normalized;
    }
    return "active";
  }

  _frequentWindowPrintLabel(model) {
    var frequents = model && model.frequents && typeof model.frequents === "object" ? model.frequents : {};
    var windowDays = this._clampInteger(frequents.window_days, this._clampInteger(this._frequentsTuning.window_days, 90, 7, 3650), 7, 3650);
    var count = Number(frequents.print_count_window);
    if (!Number.isFinite(count)) {
      count = Number(frequents.weighted_print_count);
    }
    if (!Number.isFinite(count)) {
      count = Number(model && model.linked_archive_count || 0);
    }
    count = Math.max(0, Math.round(count));
    return "Printed " + String(count) + " time" + (count === 1 ? "" : "s") + " in last " + String(windowDays) + "d";
  }

  _frequentScore(model) {
    var ranking = model && model.ranking && typeof model.ranking === "object" ? model.ranking : {};
    var frequents = model && model.frequents && typeof model.frequents === "object" ? model.frequents : {};
    var score = Number(ranking.frequent_score || 0);
    if (!Number.isFinite(score)) {
      score = Number(frequents.weighted_print_count || 0);
    }
    if (!Number.isFinite(score)) {
      score = Number(model && model.linked_archive_count || 0);
    }
    return Number.isFinite(score) ? score : 0;
  }

  _buildFrequentsRailItems(frequentCandidates, favoriteCandidates) {
    var merged = [];
    var seen = {};

    var favorites = Array.isArray(favoriteCandidates) ? favoriteCandidates : [];
    for (var i = 0; i < favorites.length; i++) {
      var favoriteModel = favorites[i];
      var favoriteRef = this._modelRef(favoriteModel);
      if (!favoriteRef || seen[favoriteRef] || !this._isModelFavorite(favoriteModel) || this._modelCatalogVisibility(favoriteModel) !== "active") {
        continue;
      }
      seen[favoriteRef] = true;
      merged.push(favoriteModel);
      if (merged.length >= 8) {
        return merged;
      }
    }

    var frequents = Array.isArray(frequentCandidates) ? frequentCandidates.slice() : [];
    frequents.sort(function (a, b) {
      return this._frequentScore(b) - this._frequentScore(a);
    }.bind(this));
    for (var j = 0; j < frequents.length; j++) {
      var frequentModel = frequents[j];
      var frequentRef = this._modelRef(frequentModel);
      if (!frequentRef || seen[frequentRef] || !this._isModelFrequent(frequentModel) || this._modelCatalogVisibility(frequentModel) !== "active") {
        continue;
      }
      seen[frequentRef] = true;
      merged.push(frequentModel);
      if (merged.length >= 8) {
        break;
      }
    }

    return merged;
  }

  _renderFrequentsRail() {
    if (this._browserScope === "collections" || !this._frequentsRailItems.length) {
      return "";
    }
    var visibleRailItems = this._frequentsRailItems.filter(function (model) {
      return this._isEntityTypeVisible(this._entityTypeForModel(model));
    }.bind(this));
    if (!visibleRailItems.length) {
      return "";
    }
    var cards = visibleRailItems.map(function (model) {
      var modelRef = this._modelRef(model);
      if (!modelRef) {
        return "";
      }
      var modelName = String(model.name || "Unnamed Model");
      var mediaUrls = this._modelMediaUrls(model);
      var previewUrl = mediaUrls.length ? mediaUrls[0] : "";
      var sourceDownloadUrl = String(model.source_download_url || "").trim();
      var favorite = this._isModelFavorite(model);
      var favoriteButton = ''
        + '<button class="icon-action favorite-action' + (favorite ? ' is-active' : '') + '" type="button" data-action="toggle-favorite" data-model-ref="' + this._escapeHtml(modelRef) + '" data-next-favorite="' + this._escapeHtml(favorite ? 'false' : 'true') + '" aria-label="' + this._escapeHtml(favorite ? 'Remove favorite' : 'Add favorite') + '">'
        + '  <ha-icon icon="' + this._escapeHtml(favorite ? 'mdi:star' : 'mdi:star-outline') + '"></ha-icon>'
        + '</button>';
      var previewHtml = previewUrl
        ? (this._isThumbnailLazyEndpoint(previewUrl)
          ? (function () {
              var cachedObjectUrl = getCachedThumbnailObjectUrl(String(previewUrl));
              if (cachedObjectUrl) {
                return '<img src="' + this._escapeHtml(String(cachedObjectUrl)) + '" alt="' + this._escapeHtml(modelName) + ' preview" loading="lazy">';
              }
              return '<img data-thumbnail-lazy-url="' + this._escapeHtml(String(previewUrl)) + '" alt="' + this._escapeHtml(modelName) + ' preview" loading="lazy">';
            }).call(this)
          : '<img src="' + this._escapeHtml(String(previewUrl)) + '" alt="' + this._escapeHtml(modelName) + ' preview" loading="lazy">')
        : '<div class="thumb-empty"><ha-icon icon="mdi:cube-outline"></ha-icon></div>';

      return ''
        + '<article class="frequent-card" role="group">'
        + '  <button class="frequent-preview" type="button" data-action="view-model-detail" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(modelName) + '">' + previewHtml + '</button>'
        + '  <div class="frequent-content">'
        + '    <button class="frequent-title" type="button" data-action="view-model-detail" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(modelName) + '">' + this._escapeHtml(modelName) + '</button>'
        + '    <div class="frequent-subtitle">' + this._escapeHtml(this._frequentWindowPrintLabel(model)) + '</div>'
        + '    <div class="frequent-actions">'
        + (sourceDownloadUrl ? '<button class="toolbar-btn" type="button" data-action="open-model" data-url="' + this._escapeHtml(sourceDownloadUrl) + '">Download</button>' : '<button class="toolbar-btn" type="button" data-action="view-model-detail" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(modelName) + '">Open</button>')
        + '      <button class="icon-action" type="button" data-action="open-model-history" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(modelName) + '" aria-label="Open print history tab"><ha-icon icon="mdi:history"></ha-icon></button>'
        + favoriteButton
        + '    </div>'
        + '  </div>'
        + '</article>';
    }.bind(this)).join("");

    return ''
      + '<section class="frequents-rail" aria-label="Frequents rail">'
      + '  <div class="frequents-rail-header">'
      + '    <div class="frequents-rail-title-wrap">'
      + '      <div class="frequents-rail-title">Frequents</div>'
      + '      <div class="frequents-rail-subtitle">Favorites are pinned first.</div>'
      + '    </div>'
      + '    <button class="toolbar-btn ghost" type="button" data-action="toggle-frequents-rail">' + (this._frequentsRailVisible ? 'Hide rail' : 'Show rail') + '</button>'
      + '  </div>'
      + (this._frequentsRailVisible ? '<div class="frequents-rail-scroll">' + cards + '</div>' : '')
      + '</section>';
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
    var noun = total === 1 ? "model" : "models";
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

    if (detailModel.preview_url) {
      addUrl(detailModel.preview_url);
    }
    var files = Array.isArray(detailModel.files) ? detailModel.files : (Array.isArray(detail && detail.files) ? detail.files : []);
    if (files.length) {
      files.forEach(function (file) {
        if (file && typeof file === "object") {
          addUrl(file.thumbnail_lazy_url || file.thumbnail_url || file.preview_url);
        }
      });
    }
    if (detail && Array.isArray(detail.photos)) {
      detail.photos.forEach(function (photo) {
        if (photo && typeof photo === "object") {
          addUrl(photo.image_url || photo.thumbnail_url || photo.preview_url || photo.url);
        }
      });
    }
    addUrl(model && model.preview_url);
    return urls;
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
        if (!this._updateModelCardThumb(modelRef)) {
          window.setTimeout(function () {
            this._updateModelCardThumb(modelRef);
          }.bind(this), 120);
        }
      }.bind(this));
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
      if (this._isThumbnailLazyEndpoint(mediaUrl)) {
        var cachedObjectUrl = getCachedThumbnailObjectUrl(mediaUrl);
        if (cachedObjectUrl) {
          img.removeAttribute('data-thumbnail-lazy-url');
          img.src = String(cachedObjectUrl);
        } else {
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
      this._setupThumbnailLazyLoading();
    }
    return updated;
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
      manyfold: "Manyfold",
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
      + '  <button class="toolbar-icon-btn" type="button" data-action="first-page" aria-label="First page" title="First page" ' + (this._loading || page <= 1 ? 'disabled' : '') + '><ha-icon icon="mdi:page-first"></ha-icon></button>'
      + '  <button class="toolbar-icon-btn" type="button" data-action="prev-page" aria-label="Previous page" title="Previous page" ' + (this._loading || page <= 1 ? 'disabled' : '') + '><ha-icon icon="mdi:chevron-left"></ha-icon></button>'
      + '  <div class="page-status">' + this._renderPageStatusWithCount() + '</div>'
      + '  <button class="toolbar-icon-btn" type="button" data-action="next-page" aria-label="Next page" title="Next page" ' + (this._loading || page >= pages ? 'disabled' : '') + '><ha-icon icon="mdi:chevron-right"></ha-icon></button>'
      + '  <button class="toolbar-icon-btn" type="button" data-action="last-page" aria-label="Last page" title="Last page" ' + (this._loading || page >= pages ? 'disabled' : '') + '><ha-icon icon="mdi:page-last"></ha-icon></button>'
      + '</div>';
  }

  _renderOptionToggle(option) {
    var active = this._browserScope === option;
    var label = option === "collections" ? "Collections" : "All models";
    return ''
      + '<button class="segmented-btn' + (active ? ' active' : '') + '" type="button" data-action="set-browser-scope" data-scope="' + this._escapeHtml(option) + '" ' + (this._loading ? 'disabled' : '') + '>'
      + this._escapeHtml(label)
      + '</button>';
  }

  _renderHeaderTitleRow() {
    return ''
      + '<div class="title-row">'
      + '  <div class="title-left">'
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
      + '        <option value="best"' + (this._filters.sort === 'best' ? ' selected' : '') + '>Best match</option>'
      + '        <option value="recent"' + (this._filters.sort === 'recent' ? ' selected' : '') + '>Recent</option>'
      + '        <option value="frequent"' + (this._filters.sort === 'frequent' ? ' selected' : '') + '>Frequent</option>'
      + '        <option value="common"' + (this._filters.sort === 'common' ? ' selected' : '') + '>Common</option>'
      + '        <option value="name"' + (this._filters.sort === 'name' ? ' selected' : '') + '>Name</option>'
      + '      </select>'
      + '    </div>'
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
    var windowDays = this._clampInteger(this._frequentsTuning.window_days, 90, 7, 3650);
    var minPrints = this._clampInteger(this._frequentsTuning.min_prints, 3, 1, 9999);
    var archivedCount = Math.max(0, Number(this._visibilityCounts && this._visibilityCounts.archived || 0) || 0);
    var showArchivedLabel = 'Show archived' + (archivedCount > 0 ? (' \u00b7 ' + String(archivedCount)) : '');
    var typeCounts = this._entityTypeCounts();
    return ''
      + '<div class="filter-row">'
      + '  <input id="mc-q" class="control-input filter-search" type="text" placeholder="Search models" value="' + this._escapeHtml(this._filters.q) + '">'
      + '  <input id="mc-collection" class="control-input" type="text" placeholder="Collection" value="' + this._escapeHtml(this._filters.collection) + '">'
      + '  <input id="mc-creator" class="control-input" type="text" placeholder="Creator" value="' + this._escapeHtml(this._filters.creator) + '">'
      + '  <input id="mc-tag" class="control-input" type="text" placeholder="Tag" value="' + this._escapeHtml(this._filters.tag) + '">'
      + '  <button class="filter-chip toggle-chip' + (this._filters.favorites_only ? ' active favorite' : '') + '" type="button" data-action="toggle-favorites-filter" aria-pressed="' + (this._filters.favorites_only ? 'true' : 'false') + '">Favorites only</button>'
      + '  <button class="filter-chip toggle-chip' + (this._filters.frequents_only ? ' active frequent' : '') + '" type="button" data-action="toggle-frequents-filter" aria-pressed="' + (this._filters.frequents_only ? 'true' : 'false') + '">Frequents only</button>'
      + '  <button class="filter-chip toggle-chip' + (this._filters.has_other_files ? ' active docs' : '') + '" type="button" data-action="toggle-other-files-filter" aria-pressed="' + (this._filters.has_other_files ? 'true' : 'false') + '">Has other files</button>'
      + '  <button class="filter-chip toggle-chip' + (this._entityTypeFilters.showIdeas ? ' active idea' : '') + '" type="button" data-action="toggle-show-ideas-filter" aria-pressed="' + (this._entityTypeFilters.showIdeas ? 'true' : 'false') + '">&#128161; Show ideas (' + this._escapeHtml(String(typeCounts.idea || 0)) + ')</button>'
      + '  <button class="filter-chip toggle-chip' + (this._entityTypeFilters.showWorkingGroups ? ' active working-group' : '') + '" type="button" data-action="toggle-show-working-groups-filter" aria-pressed="' + (this._entityTypeFilters.showWorkingGroups ? 'true' : 'false') + '">&#129529; Show working groups (' + this._escapeHtml(String(typeCounts.working_group || 0)) + ')</button>'
      + '  <button class="filter-chip toggle-chip' + (this._filters.show_archived ? ' active warn' : '') + '" type="button" data-action="toggle-show-archived-filter" aria-pressed="' + (this._filters.show_archived ? 'true' : 'false') + '">' + this._escapeHtml(showArchivedLabel) + '</button>'
      + '  <label class="inline-select" for="mc-frequent-window">Freq window'
      + '    <select id="mc-frequent-window" class="control-input compact-select tuning-select">'
      + '      <option value="30"' + (windowDays === 30 ? ' selected' : '') + '>30d</option>'
      + '      <option value="90"' + (windowDays === 90 ? ' selected' : '') + '>90d</option>'
      + '      <option value="365"' + (windowDays === 365 ? ' selected' : '') + '>1y</option>'
      + '      <option value="3650"' + (windowDays === 3650 ? ' selected' : '') + '>All</option>'
      + '    </select>'
      + '  </label>'
      + '  <label class="inline-select" for="mc-frequent-min-prints">Min prints'
      + '    <select id="mc-frequent-min-prints" class="control-input compact-select tuning-select">'
      + '      <option value="1"' + (minPrints === 1 ? ' selected' : '') + '>1</option>'
      + '      <option value="2"' + (minPrints === 2 ? ' selected' : '') + '>2</option>'
      + '      <option value="3"' + (minPrints === 3 ? ' selected' : '') + '>3</option>'
      + '      <option value="4"' + (minPrints === 4 ? ' selected' : '') + '>4</option>'
      + '      <option value="5"' + (minPrints === 5 ? ' selected' : '') + '>5</option>'
      + '      <option value="6"' + (minPrints === 6 ? ' selected' : '') + '>6</option>'
      + '    </select>'
      + '  </label>'
      + '  <input id="mc-favorites-only" type="checkbox" hidden ' + (this._filters.favorites_only ? 'checked' : '') + '>'
      + '  <input id="mc-frequents-only" type="checkbox" hidden ' + (this._filters.frequents_only ? 'checked' : '') + '>'
      + '  <input id="mc-has-other-files" type="checkbox" hidden ' + (this._filters.has_other_files ? 'checked' : '') + '>'
        + '  <input id="mc-show-archived" type="checkbox" hidden ' + (this._filters.show_archived ? 'checked' : '') + '>'
      + '  <button class="toolbar-btn ghost" type="button" data-action="clear-filters" ' + (this._loading ? 'disabled' : '') + '>Clear</button>'
      + '</div>';
  }

  _renderPageControlStrip() {
    if (this._multiSelectMode) {
      return this._renderMultiSelectStrip('');
    }
    return ''
      + '<div class="page-control-strip">'
      + this._renderNavigationControls()
      + '<div class="toolbar-group density-group">'
      + '  <label for="mc-per-page">Models / Page</label>'
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
    return ''
      + '<div class="page-control-strip bottom-mirror">'
      + this._renderNavigationControls()
      + '<div class="toolbar-group density-group">'
      + '  <label for="mc-per-page-bottom">Models / Page</label>'
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
    return ''
      + '<div class="page-control-strip multi-select-active' + extraClass + '">'
      + '  <span class="ms-count">' + this._escapeHtml(String(count) + ' of ' + String(visible) + ' selected') + '</span>'
      + '  <button class="bulk-btn" type="button" data-action="toggle-select-all-models">' + this._escapeHtml(selectAllLabel) + '</button>'
      + '  <button class="bulk-btn" type="button" data-action="bulk-pin-favorites">Pin Favorites</button>'
      + '  <button class="bulk-btn" type="button" data-action="bulk-unpin-favorites">Unpin Favorites</button>'
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

  _renderModelCard(model) {
    var modelUrl = String(model.model_url || "");
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
      ? '<span class="entity-type-pill ' + this._escapeHtml(entityType === "working_group" ? "working-group" : entityType) + '">' + this._escapeHtml(entityTypeBadgeText) + '</span>'
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
    // avoid whole-grid repaint churn.
    if (this._showMedia && ((this._viewMode === "compact" && mediaCount === 0) || this._viewMode === "media")) {
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
                return '<img src="' + this._escapeHtml(String(cachedObjectUrl)) + '" alt="' + this._escapeHtml(name) + ' preview" loading="lazy">';
              }
              return '<img data-thumbnail-lazy-url="' + this._escapeHtml(String(mediaUrl)) + '" alt="' + this._escapeHtml(name) + ' preview" loading="lazy">';
            }).call(this)
          : '<img src="' + this._escapeHtml(String(mediaUrl)) + '" alt="' + this._escapeHtml(name) + ' preview">'
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
        var promoteLabel = promoteTarget === "working_group" ? "Promote to Working Group" : "Promote to Model";
        promotionActions += '  <button class="advanced-action" type="button" data-action="promote-entity" data-local-model-id="' + this._escapeHtml(localModelId) + '" data-from-entity-type="' + this._escapeHtml(entityType) + '" data-to-entity-type="' + this._escapeHtml(promoteTarget) + '" data-model-name="' + this._escapeHtml(name) + '"><ha-icon icon="mdi:arrow-up-bold-circle-outline"></ha-icon><span>' + this._escapeHtml(promoteLabel) + '</span></button>';
      }
    }
    var workingGroupId = this._workingGroupIdForModel(model);
    var workingGroupActions = '';
    if (entityType === "working_group") {
      workingGroupActions = '  <button class="advanced-action" type="button" data-action="open-working-files" data-model-name="' + this._escapeHtml(name) + '" data-working-group-id="' + this._escapeHtml(String(workingGroupId || 0)) + '"><ha-icon icon="mdi:folder-open-outline"></ha-icon><span>Open in Working Files</span></button>';
    }
    var advancedActions = ''
      + '<div class="advanced-menu-shell">'
      + '  <button class="icon-action advanced" type="button" data-action="toggle-actions" data-model-ref="' + this._escapeHtml(modelRef) + '" aria-label="Open advanced actions" aria-expanded="' + (actionMenuOpen ? 'true' : 'false') + '"><ha-icon icon="mdi:dots-horizontal"></ha-icon></button>'
      + '<div class="advanced-menu' + (actionMenuOpen ? ' is-open' : '') + '" aria-hidden="' + (actionMenuOpen ? 'false' : 'true') + '">'
          + '  <button class="advanced-action primary" type="button" data-action="view-model-detail" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '"><ha-icon icon="mdi:text-box-search-outline"></ha-icon><span>View details</span></button>'
          + '  <button class="advanced-action primary" type="button" data-action="open-model-viewer" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '"><ha-icon icon="mdi:cube-scan"></ha-icon><span>Open 3D viewer</span></button>'
          + (modelUrl ? '  <button class="advanced-action" type="button" data-action="open-model" data-url="' + this._escapeHtml(modelUrl) + '"><ha-icon icon="mdi:open-in-new"></ha-icon><span>Open source page</span></button>' : '')
          + workingGroupActions
          + promotionActions
          + '  <div class="advanced-group-label">Queue actions</div>'
          + '  <div class="advanced-inline-grid">'
          + '    <button class="mini-btn" type="button" data-action="queue-priority-down" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '">-P</button>'
          + '    <button class="mini-btn" type="button" data-action="queue-priority-up" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '">+P</button>'
          + '    <button class="mini-btn" type="button" data-action="queue-mark-queued" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '">Queued</button>'
          + '    <button class="mini-btn" type="button" data-action="queue-mark-done" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '">Done</button>'
          + '    <button class="mini-btn" type="button" data-action="queue-clear" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '">Clear</button>'
          + '    <button class="mini-btn" type="button" data-action="queue-re-add" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '">Re-add</button>'
          + '  </div>'
          + deleteButton
          + '</div>'
      + '</div>';

    var queueRibbonClass = "";
    if (queueStatus === "queued") {
      queueRibbonClass = " is-queued";
    } else if (queueStatus === "printing") {
      queueRibbonClass = " is-printing";
    } else if (queueStatus === "done") {
      queueRibbonClass = " is-done";
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

    var compactMainHtml = ''
      + '<div class="body compact-main">'
      + '  <div class="compact-top-actions">'
      + '    <button class="icon-action viewer" type="button" data-action="open-model-viewer" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="Open 3D viewer"><ha-icon icon="mdi:cube-scan"></ha-icon></button>'
      + favoriteButton
      + queueButton
      + advancedActions
      + '  </div>'
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
      + '    <h3 class="title">' + this._escapeHtml(name) + '</h3>'
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
      + '    <h3 class="title">' + this._escapeHtml(name) + '</h3>'
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
      + '      <h3 class="title">' + this._escapeHtml(name) + '</h3>'
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
        + '<article class="model-card view-media' + queueRibbonClass + (this._isModelSelected(modelRef) ? ' is-selected' : '') + '" tabindex="0" role="button" data-action="' + cardAction + '" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="' + (cardAction === 'toggle-model-select' ? 'Select ' : 'Open details for ') + this._escapeHtml(name) + '">'
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
        + '<article class="model-card view-list' + queueRibbonClass + (this._isModelSelected(modelRef) ? ' is-selected' : '') + '" tabindex="0" role="button" data-action="' + cardAction + '" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="' + (cardAction === 'toggle-model-select' ? 'Select ' : 'Open details for ') + this._escapeHtml(name) + '">'
        + '  <div class="thumb-wrap list-wrap">'
        + '    <div class="thumb list-thumb">' + previewHtml + '</div>'
        + '  </div>'
        + listBodyHtml
        + '</article>';
    }

    var cardAction = this._multiSelectMode ? "toggle-model-select" : "view-model-detail";
    return ''
      + '<article class="model-card view-compact' + queueRibbonClass + (this._isModelSelected(modelRef) ? ' is-selected' : '') + '" tabindex="0" role="button" data-action="' + cardAction + '" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="' + (cardAction === 'toggle-model-select' ? 'Select ' : 'Open details for ') + this._escapeHtml(name) + '">'
      + '  <div class="thumb-wrap compact-wrap"><div class="thumb">' + previewHtml + '</div></div>'
      + compactMainHtml
      + compactFullHtml
      + '</article>';
  }

  _renderCollectionCards() {
    var grouped = {};
    for (var i = 0; i < this._results.length; i++) {
      var model = this._results[i] || {};
      var collections = Array.isArray(model.collection_names) ? model.collection_names : [];
      var targetCollections = collections.length ? collections : ["Unassigned"];
      for (var c = 0; c < targetCollections.length; c++) {
        var name = String(targetCollections[c] || "").trim() || "Unassigned";
        if (!grouped[name]) {
          grouped[name] = {
            name: name,
            total: 0,
            creators: {},
            modelNames: [],
          };
        }
        grouped[name].total += 1;
        var creator = String(model.creator_name || "Unknown creator").trim();
        grouped[name].creators[creator] = (grouped[name].creators[creator] || 0) + 1;
        if (grouped[name].modelNames.length < 3) {
          grouped[name].modelNames.push(String(model.name || "Unnamed model").trim());
        }
      }
    }

    var cards = Object.keys(grouped).sort(function (a, b) {
      return a.localeCompare(b);
    }).map(function (key) {
      var entry = grouped[key];
      var topCreators = Object.keys(entry.creators).sort(function (a, b) {
        return Number(entry.creators[b] || 0) - Number(entry.creators[a] || 0);
      }).slice(0, 2);
      var creatorSummary = topCreators.map(function (name) {
        return name + " (" + String(entry.creators[name]) + ")";
      }).join(" · ");
      return ''
        + '<article class="collection-card">'
        + '  <div class="collection-name">' + this._escapeHtml(entry.name) + '</div>'
        + '  <div class="collection-meta">' + this._escapeHtml(String(entry.total) + (entry.total === 1 ? " model" : " models")) + '</div>'
        + '  <div class="collection-meta">Top creators: ' + this._escapeHtml(creatorSummary || "Unknown") + '</div>'
        + '  <div class="collection-models">' + this._escapeHtml(entry.modelNames.join(" · ")) + '</div>'
        + '  <button class="toolbar-btn" type="button" data-action="set-collection-filter" data-collection="' + this._escapeHtml(entry.name) + '">Open collection</button>'
        + '</article>';
    }.bind(this)).join("");

    if (!cards) {
      return '<div class="state-row">No collections found for current filters.</div>';
    }
    return cards;
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
        if (inferredImages === 0 && detailPhotos.length) {
          inferredImages = detailPhotos.length;
        }
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

  _openWorkingFilesExplorer(groupId, groupTitle) {
    this._fireBrowserModEvent("browser_mod.popup", {
      title: groupTitle ? (groupTitle + " - Working Files") : "Working Files",
      size: "wide",
      content: {
        type: "custom:model-catalog-working-files-explorer-card",
        initial_group_id: Number.isFinite(Number(groupId)) && Number(groupId) > 0 ? Math.round(Number(groupId)) : 0,
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
    var visibleResults = this._filteredResultsForScope();
    return visibleResults.map(function (model) {
      return this._modelRef(model);
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

  _doRender() {
    if (!this.shadowRoot || !this._config) {
      return;
    }

    var visibleResults = this._filteredResultsForScope();

    var resultsHtml = "";
    if (this._loading) {
      resultsHtml = this._renderLoadingPlaceholders();
    } else if (this._error) {
      resultsHtml = '<div class="state-row error">' + this._escapeHtml(this._error) + '</div>';
    } else if (!visibleResults.length) {
      resultsHtml = '<div class="state-row">No models match the current filters.</div>';
    } else if (this._browserScope === "collections") {
      resultsHtml = this._renderCollectionCards();
    } else {
      resultsHtml = visibleResults.map(this._renderModelCard.bind(this)).join("");
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
      + '.shell{display:grid;gap:14px;padding:6px 10px 10px;}'
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
      + '.filter-row{display:grid;grid-template-columns:minmax(180px,1.4fr) repeat(3,minmax(130px,1fr)) auto auto auto auto auto auto;gap:8px;padding:12px;border-radius:16px;border:1px solid var(--line);background:rgba(148,163,184,0.08);align-items:center;}'
      + '.filter-search{grid-column:auto;}'
      + '.inline-select{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:800;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.03em;white-space:nowrap;}'
      + '.inline-select .tuning-select{min-width:84px;min-height:34px;}'
      + '.filter-chip{min-height:36px;padding:0 12px;border-radius:999px;border:1px solid var(--chip-line);background:rgba(15,23,42,0.08);color:var(--secondary-text-color);font-size:12px;font-weight:800;cursor:pointer;appearance:none;pointer-events:auto;position:relative;z-index:1;}'
      + '.filter-chip:hover,.filter-chip:focus-visible{background:rgba(148,163,184,0.18);outline:none;border-color:rgba(148,163,184,0.42);}'
      + '.filter-chip.active{color:var(--primary-text-color);}'
      + '.filter-chip.favorite.active{background:rgba(245,194,66,0.20);border-color:rgba(245,194,66,0.48);color:#f5c242;}'
      + '.filter-chip.frequent.active{background:rgba(16,185,129,0.20);border-color:rgba(16,185,129,0.44);color:#6ee7b7;}'
      + '.filter-chip.docs.active{background:rgba(56,189,248,0.18);border-color:rgba(56,189,248,0.34);color:#93c5fd;}'
      + '.filter-chip.idea.active{background:rgba(250,204,21,0.20);border-color:rgba(250,204,21,0.44);color:#fde68a;}'
      + '.filter-chip.working-group.active{background:rgba(96,165,250,0.20);border-color:rgba(96,165,250,0.44);color:#dbeafe;}'
      + '.frequents-rail{display:grid;gap:10px;padding:12px;border-radius:16px;border:1px solid var(--line);background:rgba(16,185,129,0.08);}'
      + '.frequents-rail-header{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;}'
      + '.frequents-rail-title-wrap{display:grid;gap:2px;}'
      + '.frequents-rail-title{font-size:14px;font-weight:800;letter-spacing:.02em;}'
      + '.frequents-rail-subtitle{font-size:11px;color:var(--secondary-text-color);}'
      + '.frequents-rail-scroll{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(240px,1fr);gap:10px;overflow-x:auto;padding-bottom:2px;}'
      + '.frequent-card{display:grid;grid-template-columns:72px minmax(0,1fr);gap:10px;padding:10px;border-radius:12px;border:1px solid var(--line);background:rgba(15,23,42,0.14);min-height:88px;}'
      + '.frequent-preview{display:flex;align-items:center;justify-content:center;padding:0;border:1px solid var(--line);background:rgba(15,23,42,0.20);border-radius:10px;overflow:hidden;cursor:pointer;}'
      + '.frequent-preview img{width:100%;height:100%;object-fit:cover;display:block;}'
      + '.frequent-content{display:grid;align-content:start;gap:6px;min-width:0;}'
      + '.frequent-title{padding:0;border:0;background:transparent;color:var(--primary-text-color);font-size:13px;font-weight:800;text-align:left;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
      + '.frequent-subtitle{font-size:11px;color:var(--secondary-text-color);}'
      + '.frequent-actions{display:flex;align-items:center;gap:6px;flex-wrap:wrap;}'
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
      + '.results.is-loading{pointer-events:none;}'
      + '.results.view-compact{grid-template-columns:repeat(auto-fill,minmax(360px,1fr));}'
      + '.results.view-media{grid-template-columns:repeat(auto-fill,minmax(320px,1fr));}'
      + '.results.view-list{grid-template-columns:1fr;}'
      + '.results.view-collections{grid-template-columns:repeat(auto-fill,minmax(280px,1fr));}'
      + '.results.media-hidden .thumb-wrap,.results.media-hidden .media-wrap,.results.media-hidden .list-wrap{display:none !important;}'
      + '.results.media-hidden .model-card.view-compact,.results.media-hidden .model-card.view-list{grid-template-columns:1fr;}'
      + '.collection-card{display:grid;gap:8px;padding:14px;border-radius:16px;border:1px solid var(--line);background:linear-gradient(180deg,rgba(15,23,42,0.20),rgba(15,23,42,0.10));}'
      + '.collection-name{font-size:15px;font-weight:800;}'
      + '.collection-meta{font-size:12px;color:var(--secondary-text-color);}'
      + '.collection-models{font-size:12px;line-height:1.4;opacity:.9;}'
      + '.model-card{position:relative;min-width:0;border-radius:20px;border:1px solid var(--line);background:linear-gradient(180deg,rgba(15,23,42,0.22),rgba(15,23,42,0.14));overflow:visible;display:grid;cursor:pointer;transition:border-color .18s ease;contain:layout paint style;}'
      + '.model-card::after{content:"";position:absolute;inset:0;border-radius:inherit;background:transparent;box-shadow:inset 5px 0 0 transparent;opacity:0;transition:opacity .16s ease,box-shadow .16s ease;pointer-events:none;}'
      + '.model-card:hover{border-color:var(--accent-strong);box-shadow:0 6px 16px rgba(15,23,42,0.18);}'
      + '.model-card:focus-visible{outline:none;box-shadow:0 0 0 2px rgba(96,165,250,0.34);border-color:var(--accent-strong);}'
      + '.model-card.view-compact{grid-template-columns:minmax(148px,188px) minmax(0,1fr);grid-template-areas:"thumb main" "full full";column-gap:18px;row-gap:10px;padding:14px;align-items:start;}'
      + '.model-card.view-media{grid-template-rows:auto 1fr;}'
      + '.model-card.view-list{grid-template-columns:88px minmax(0,1fr);column-gap:10px;padding:10px 12px;align-items:start;}'
      + '.model-card.is-queued::after{opacity:1;box-shadow:inset 5px 0 0 #3b82f6;}'
      + '.model-card.is-printing::after{opacity:1;box-shadow:inset 5px 0 0 #1e88e5;}'
      + '.model-card.is-done::after{opacity:1;box-shadow:inset 5px 0 0 #2e7d32;}'
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
      + '.compact-top-actions{display:flex;justify-content:flex-end;align-items:center;gap:8px;}'
      + '.compact-top-actions .advanced-menu-shell{margin-left:0;}'
      + '.compact-title-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:10px;min-width:0;}'
      + '.compact-last-printed{font-size:11px;font-weight:700;color:var(--secondary-text-color);padding-top:2px;}'
      + '.favorite-action{border-color:rgba(245,194,66,0.34);}'
      + '.favorite-action.is-active{background:rgba(245,194,66,0.20);color:#f5c242;border-color:rgba(245,194,66,0.52);}'
      + '.favorite-action.is-active:hover,.favorite-action.is-active:focus-visible{background:rgba(245,194,66,0.26);color:#f5c242;border-color:rgba(245,194,66,0.62);box-shadow:0 0 0 1px rgba(245,194,66,0.28);transform:translateY(-1px);outline:none;}'
      + '.queue-action{border-color:rgba(96,165,250,0.30);background:rgba(30,64,175,0.14);color:#93c5fd;position:relative;}'
      + '.queue-action:hover,.queue-action:focus-visible{background:rgba(59,130,246,0.20);color:#dbeafe;border-color:rgba(96,165,250,0.52);box-shadow:0 0 0 1px rgba(96,165,250,0.20),0 8px 18px rgba(15,23,42,0.20);transform:translateY(-1px);outline:none;}'
      + '.queue-action.has-queue-entries{background:rgba(59,130,246,0.24);color:#bfdbfe;border-color:rgba(96,165,250,0.50);}'
      + '.queue-action.has-queue-entries:hover,.queue-action.has-queue-entries:focus-visible{background:rgba(59,130,246,0.30);color:#eff6ff;border-color:rgba(147,197,253,0.66);box-shadow:0 0 0 1px rgba(96,165,250,0.28),0 10px 22px rgba(15,23,42,0.22);transform:translateY(-1px);outline:none;}'
      + '.queue-count-badge{position:absolute;top:-8px;right:-8px;width:18px;height:18px;min-width:18px;padding:0;border-radius:50%;background:#3b82f6;color:#fff;font-size:10px;font-weight:800;display:flex;align-items:center;justify-content:center;line-height:1;box-sizing:border-box;pointer-events:none;border:1px solid rgba(15,23,42,0.6);}'
      + '.header-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;column-gap:12px;row-gap:8px;}'
      + '.media-body{gap:8px;padding:12px 14px 14px;}'
      + '.media-title-row{display:grid;grid-template-columns:minmax(0,1fr);gap:10px;align-items:start;}'
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
      + '.entity-type-pill.working-group{background:rgba(96,165,250,0.18);border-color:rgba(96,165,250,0.34);color:#dbeafe;}'
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
      + '.icon-action,.mini-btn,.advanced-action{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:34px;padding:0 10px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(15,23,42,0.14);color:var(--primary-text-color);font-size:11px;font-weight:700;cursor:pointer;transition:background .16s ease,color .16s ease,box-shadow .16s ease,transform .16s ease,border-color .16s ease;}'
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
      + '.advanced-action.primary{background:rgba(96,165,250,0.14);border-color:rgba(96,165,250,0.26);}'
      + '.advanced-action.danger{background:rgba(185,28,28,0.14);border-color:rgba(185,28,28,0.26);color:#f87171;}'
      + '.advanced-action.danger:hover,.advanced-action.danger:focus-visible{background:rgba(185,28,28,0.24);border-color:rgba(185,28,28,0.44);color:#fca5a5;}'
      + '.advanced-action ha-icon{--mdc-icon-size:16px;}'
      + '.advanced-group-label{font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--secondary-text-color);padding:2px 2px 0;}'
      + '.advanced-inline-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;}'
      + '.state-row{padding:20px;border-radius:16px;border:1px dashed rgba(148,163,184,0.24);background:rgba(148,163,184,0.10);font-size:13px;color:var(--secondary-text-color);}'
      + '.state-row.error{background:rgba(185,28,28,0.16);color:var(--primary-text-color);}'
      + '.queue-dialog-backdrop{position:fixed;inset:0;z-index:30;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(2,6,23,0.72);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);}'
      + '.queue-dialog{width:min(680px,calc(100vw - 32px));max-height:calc(100vh - 40px);display:grid;grid-template-rows:auto auto minmax(0,1fr) auto;overflow:hidden;border-radius:20px;border:1px solid var(--line-strong);background:rgba(15,23,42,0.97);box-shadow:0 24px 48px rgba(2,6,23,0.42);}'
      + '.queue-dialog-header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:18px 20px 14px;border-bottom:1px solid rgba(148,163,184,0.18);}'
      + '.queue-dialog-header h3{margin:0;font-size:18px;font-weight:800;}'
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
      + '@keyframes shimmer{0%{background-position:200% 0;}100%{background-position:-200% 0;}}'
      + '@keyframes compact-enter{0%{opacity:0;transform:translateY(4px);}100%{opacity:1;transform:translateY(0);}}'
      + '@keyframes spin-refresh{from{transform:rotate(0deg);}to{transform:rotate(360deg);}}'
      + '@media (max-width: 1200px){.filter-row{grid-template-columns:minmax(180px,1fr) repeat(2,minmax(140px,1fr)) auto auto auto auto auto auto;}}'
      + '@media (max-width: 820px){.model-card.view-compact,.model-card.view-list{grid-template-columns:1fr;}.compact-wrap,.list-wrap{min-height:180px;}.thumb,.list-thumb{height:180px;}.tag-project-row,.header-row,.compact-title-row,.compact-tags-row,.media-title-row,.media-footer-row,.list-top-row,.list-bottom-row{grid-template-columns:minmax(0,1fr);}.media-status-chip,.header-actions,.media-actions{justify-content:flex-start;}.compact-top-actions{justify-content:flex-end;}.compact-file-kinds,.list-file-kinds,.list-top-actions{justify-content:flex-start;}.list-action-stack{justify-items:start;}.title-row{align-items:flex-start;}.title-right{width:100%;justify-content:space-between;}.filter-row{grid-template-columns:1fr 1fr;}.inline-select{justify-content:space-between;}.inline-select .tuning-select{min-width:72px;}.page-control-strip{justify-content:flex-start;}.media-overlay-actions{left:10px;right:auto;}}'
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
      + '@media (max-width: 560px){.shell{padding:6px 10px 10px;}.filter-row{grid-template-columns:1fr;}.title-left,.title-right{width:100%;}.sort-group{width:100%;justify-content:space-between;}.import-menu-items{right:auto;left:0;}.toolbar-group{width:100%;justify-content:flex-start;}.page-status{padding-left:0;}.media-preview{min-height:180px;}.metrics{grid-template-columns:1fr;}.advanced-menu{left:0;right:auto;min-width:min(260px,calc(100vw - 56px));}}';
      this._contentRoot = document.createElement('ha-card');
      this.shadowRoot.textContent = '';
      this.shadowRoot.appendChild(this._persistentStyle);
      this.shadowRoot.appendChild(this._contentRoot);
    }

    this._contentRoot.innerHTML = ''
      + '  <div class="shell">'
      + '    <div class="shell-header">'
      + this._renderHeaderTitleRow()
      + this._renderFilterBar()
      + this._renderFrequentsRail()
      + this._renderPageControlStrip()
      + '    </div>'
      + '    <div class="results' + (this._loading ? ' is-loading' : '') + ' view-' + this._escapeHtml(this._browserScope === "collections" ? "collections" : this._viewMode) + (this._showMedia ? '' : ' media-hidden') + '">' + resultsHtml + '</div>'
      + this._renderBottomMirrorStrip()
      + this._renderQueueDialog()
      + '  </div>';

    setTimeout(function () {
      this._setupThumbnailLazyLoading();
    }.bind(this), 0);
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

