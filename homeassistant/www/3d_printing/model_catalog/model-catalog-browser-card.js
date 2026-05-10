import { setupThumbnailLazyObserver, addShimmerAnimation, getCachedThumbnailObjectUrl } from './thumbnail-lazy-loader.js?v=2';

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
    this._modelSidecarUrl = "";

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
  }

  _defaultFilters() {
    return {
      q: "",
      collection: "",
      creator: "",
      tag: "",
      to_print_status: "",
      to_print_priority_min: "",
      to_print_priority_max: "",
      sort: "recent",
      favorites_only: false,
      has_other_files: false,
    };
  }

  setConfig(config) {
    this._config = {
      title: config && config.title ? String(config.title) : "Catalog Browser",
      per_page: config && Number.isFinite(Number(config.per_page))
        ? Math.max(1, Math.min(50, Number(config.per_page)))
        : 12,
      model_entity: config && config.model_entity ? String(config.model_entity) : "",
      model_sidecar_url: config && config.model_sidecar_url ? String(config.model_sidecar_url) : "",
    };
    this._pagination.per_page = this._config.per_page;
    this._render();
  }

  set hass(hass) {
    var hadHass = !!this._hass;
    this._hass = hass;
    this._modelSidecarUrl = this._resolveModelSidecarUrl();

    if (!hadHass && !this._hasAttemptedLoad && !this._loading && !this._error) {
      this._hasAttemptedLoad = true;
      this._requestLoad(1, this._isScopeStale());
    }

    if (!hadHass || !this._didInitialRender) {
      this._didInitialRender = true;
      this._render();
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
    setupThumbnailLazyObserver({
      rootElement: this.shadowRoot,
      root: null,
      timeout: 5000,
      retries: 2,
      useIntersectionObserver: true,
      rootMargin: "50px",
      threshold: 0.1,
    });
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
    this._filters.to_print_status = read("#mc-queue");
    this._filters.to_print_priority_min = read("#mc-priority-min");
    this._filters.to_print_priority_max = read("#mc-priority-max");
    this._filters.sort = read("#mc-sort") || "recent";
    var perPageTop = Number(read("#mc-per-page") || 0);
    var perPageBottom = Number(read("#mc-per-page-bottom") || 0);
    var perPage = Number.isFinite(perPageTop) && perPageTop > 0 ? perPageTop : perPageBottom;
    if (Number.isFinite(perPage) && perPage > 0) {
      this._pagination.per_page = Math.max(1, Math.min(96, perPage));
    }
    this._filters.favorites_only = !!(root.querySelector("#mc-favorites-only") && root.querySelector("#mc-favorites-only").checked);
    this._filters.has_other_files = !!(root.querySelector("#mc-has-other-files") && root.querySelector("#mc-has-other-files").checked);
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
    this._render();

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
        to_print_status: this._filters.to_print_status,
        to_print_priority_min: this._filters.to_print_priority_min,
        to_print_priority_max: this._filters.to_print_priority_max,
        sort: this._filters.sort,
        favorites_only: !!this._filters.favorites_only,
        has_other_files: !!this._filters.has_other_files,
        refresh: !!refresh,
        page: Math.max(1, Number(page || 1)),
        per_page: this._pagination.per_page,
      };

      var data = await this._callServiceWithResponse("rest_command", "model_catalog_search_models", requestPayload);
      this._results = Array.isArray(data && data.results) ? data.results : [];

      var pagination = data && data.pagination ? data.pagination : {};
      this._pagination.page = Number(pagination.page || requestPayload.page) || 1;
      this._pagination.per_page = Number(pagination.per_page || this._pagination.per_page) || this._pagination.per_page;
      this._pagination.total = Number(pagination.total || 0) || 0;
      this._pagination.total_pages = Number(pagination.total_pages || 0) || 0;
      if (stampSnapshot > (Number(this._lastAppliedScopeStamp) || 0)) {
        this._lastAppliedScopeStamp = stampSnapshot;
      }
    } catch (error) {
      this._results = [];
      this._pagination.page = 1;
      this._pagination.total = 0;
      this._pagination.total_pages = 0;
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

  _normalizedViewMode(mode) {
    var normalized = String(mode || "compact").trim().toLowerCase();
    if (normalized === "media" || normalized === "list") {
      return normalized;
    }
    return "compact";
  }

  _handleInput(event) {
    var target = event && event.target;
    if (!target || !target.classList || !target.classList.contains("control-input")) {
      return;
    }
    var tagName = String(target.tagName || "").toUpperCase();
    if (tagName === "SELECT") {
      return;
    }
    this._scheduleDebouncedApply();
  }

  _handleChange(event) {
    var target = event && event.target;
    if (!target) {
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
      this._error = "";
      this._activeActionMenu = "";
      this._requestLoad(1, false);
      this._render();
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

    if (action === "toggle-other-files-filter") {
      this._filters.has_other_files = !this._filters.has_other_files;
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
      var queueStatus = String(target.getAttribute("data-queue-status") || "").trim().toLowerCase();
      if (!queueModelRef || this._loading) {
        return;
      }

      try {
        this._error = "";
        this._activeActionMenu = "";

        if (action === "queue-priority-up") {
          var priorityUpPayload = {
            model_ref: queueModelRef,
            action: "priority_up",
          };
          if (!queueStatus || queueStatus === "none") {
            priorityUpPayload.to_print_status = "queued";
          }
          await this._callServiceWithResponse("rest_command", "model_catalog_update_model_queue", priorityUpPayload);
        } else if (action === "queue-priority-down") {
          var priorityDownPayload = {
            model_ref: queueModelRef,
            action: "priority_down",
          };
          if (!queueStatus || queueStatus === "none") {
            priorityDownPayload.to_print_status = "queued";
          }
          await this._callServiceWithResponse("rest_command", "model_catalog_update_model_queue", priorityDownPayload);
        } else if (action === "queue-mark-queued") {
          await this._callServiceWithResponse("rest_command", "model_catalog_update_model_queue", {
            model_ref: queueModelRef,
            action: "mark_queued",
          });
        } else if (action === "queue-mark-done") {
          await this._callServiceWithResponse("rest_command", "model_catalog_update_model_queue", {
            model_ref: queueModelRef,
            action: "mark_done",
          });
        } else if (action === "queue-clear") {
          await this._callServiceWithResponse("rest_command", "model_catalog_update_model_queue", {
            model_ref: queueModelRef,
            action: "clear",
          });
        }

        await this._loadPage(this._currentPage(), false);
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not update queue state.";
        this._render();
      }
    }
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
  }

  _handleWheel(event) {
    var target = event && event.target;
    var surface = target && target.closest ? target.closest(".media-surface[data-model-ref]") : null;
    if (!surface) {
      return;
    }
    var galleryCount = Math.max(0, Number(surface.getAttribute("data-gallery-count") || 0));
    if (galleryCount <= 1) {
      return;
    }
    var delta = Number(event.deltaY || 0);
    if (!delta) {
      return;
    }
    event.preventDefault();
    var modelRef = String(surface.getAttribute("data-model-ref") || "").trim();
    if (!modelRef) {
      return;
    }
    this._setModelMediaIndex(modelRef, this._currentModelMediaIndex(modelRef, galleryCount) + (delta > 0 ? 1 : -1), galleryCount);
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
          this._render();
          return;
        }
        if (!this._updateModelCardThumb(modelRef)) {
          this._render();
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
      + '        <option value="priority"' + (this._filters.sort === 'priority' ? ' selected' : '') + '>Queue priority</option>'
      + '        <option value="name"' + (this._filters.sort === 'name' ? ' selected' : '') + '>Name</option>'
      + '      </select>'
      + '    </div>'
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
    return ''
      + '<div class="filter-row">'
      + '  <input id="mc-q" class="control-input filter-search" type="text" placeholder="Search models" value="' + this._escapeHtml(this._filters.q) + '">'
      + '  <input id="mc-collection" class="control-input" type="text" placeholder="Collection" value="' + this._escapeHtml(this._filters.collection) + '">'
      + '  <input id="mc-creator" class="control-input" type="text" placeholder="Creator" value="' + this._escapeHtml(this._filters.creator) + '">'
      + '  <input id="mc-tag" class="control-input" type="text" placeholder="Tag" value="' + this._escapeHtml(this._filters.tag) + '">'
      + '  <select id="mc-queue" class="control-input">'
      + '    <option value=""' + (this._filters.to_print_status === '' ? ' selected' : '') + '>Queue: all</option>'
      + '    <option value="queued"' + (this._filters.to_print_status === 'queued' ? ' selected' : '') + '>Queue: queued</option>'
      + '    <option value="done"' + (this._filters.to_print_status === 'done' ? ' selected' : '') + '>Queue: done</option>'
      + '    <option value="none"' + (this._filters.to_print_status === 'none' ? ' selected' : '') + '>Queue: none</option>'
      + '  </select>'
      + '  <button class="filter-chip toggle-chip' + (this._filters.favorites_only ? ' active favorite' : '') + '" type="button" data-action="toggle-favorites-filter" aria-pressed="' + (this._filters.favorites_only ? 'true' : 'false') + '">Favorites only</button>'
      + '  <button class="filter-chip toggle-chip' + (this._filters.has_other_files ? ' active docs' : '') + '" type="button" data-action="toggle-other-files-filter" aria-pressed="' + (this._filters.has_other_files ? 'true' : 'false') + '">Has other files</button>'
      + '  <input id="mc-favorites-only" type="checkbox" hidden ' + (this._filters.favorites_only ? 'checked' : '') + '>'
      + '  <input id="mc-has-other-files" type="checkbox" hidden ' + (this._filters.has_other_files ? 'checked' : '') + '>'
      + '  <button class="toolbar-btn ghost" type="button" data-action="clear-filters" ' + (this._loading ? 'disabled' : '') + '>Clear</button>'
      + '</div>';
  }

  _renderPageControlStrip() {
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
      + '  <select id="mc-view-mode" class="control-input compact-select">'
      + '    <option value="compact"' + (this._viewMode === 'compact' ? ' selected' : '') + '>Compact</option>'
      + '    <option value="media"' + (this._viewMode === 'media' ? ' selected' : '') + '>Media</option>'
      + '    <option value="list"' + (this._viewMode === 'list' ? ' selected' : '') + '>List</option>'
      + '  </select>'
      + '  <button class="toolbar-icon-btn media-toggle' + (this._showMedia ? ' active' : '') + '" type="button" data-action="toggle-show-media" aria-pressed="' + (this._showMedia ? 'true' : 'false') + '" title="' + (this._showMedia ? 'Hide media' : 'Show media') + '"><ha-icon icon="mdi:eye' + (this._showMedia ? '' : '-off') + '"></ha-icon></button>'
      + '  <button class="toolbar-icon-btn refresh-btn' + (this._refreshSpin ? ' spinning' : '') + '" type="button" data-action="refresh-page" aria-label="Refresh results" title="Refresh" ' + (this._loading ? 'disabled' : '') + '><ha-icon icon="mdi:refresh"></ha-icon></button>'
      + '</div>'
      + '</div>';
  }

  _renderBottomMirrorStrip() {
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
      title: nextMode === "server" ? "Import From Server Inbox" : "Upload Files or Folders",
      size: "fullscreen",
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
    var queueStatus = String(fields.to_print_status || "").trim().toLowerCase();
    var queuePriority = String(fields.to_print_priority || "").trim();
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
    // Some summaries omit preview URLs until detail is loaded; hydrate in compact
    // so images appear on first load without requiring a view-mode toggle.
    if (this._showMedia && this._viewMode === "compact" && mediaCount === 0) {
      this._loadModelMedia(model);
    }
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

    // Avoid prefetch/re-render churn in compact/list; only hydrate media galleries in media mode.
    if (this._showMedia && this._viewMode === "media") {
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

    var advancedActions = ''
      + '<div class="advanced-menu-shell">'
      + '  <button class="icon-action advanced" type="button" data-action="toggle-actions" data-model-ref="' + this._escapeHtml(modelRef) + '" aria-label="Open advanced actions" aria-expanded="' + (actionMenuOpen ? 'true' : 'false') + '"><ha-icon icon="mdi:dots-horizontal"></ha-icon></button>'
      + '<div class="advanced-menu' + (actionMenuOpen ? ' is-open' : '') + '" aria-hidden="' + (actionMenuOpen ? 'false' : 'true') + '">'
          + '  <button class="advanced-action primary" type="button" data-action="view-model-detail" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '"><ha-icon icon="mdi:text-box-search-outline"></ha-icon><span>View details</span></button>'
          + '  <button class="advanced-action primary" type="button" data-action="open-model-viewer" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '"><ha-icon icon="mdi:cube-scan"></ha-icon><span>Open 3D viewer</span></button>'
          + (modelUrl ? '  <button class="advanced-action" type="button" data-action="open-model" data-url="' + this._escapeHtml(modelUrl) + '"><ha-icon icon="mdi:open-in-new"></ha-icon><span>Open source page</span></button>' : '')
          + '  <div class="advanced-group-label">Queue actions</div>'
          + '  <div class="advanced-inline-grid">'
          + '    <button class="mini-btn" type="button" data-action="queue-priority-down" data-model-ref="' + this._escapeHtml(modelRef) + '" data-queue-status="' + this._escapeHtml(queueStatus) + '">-P</button>'
          + '    <button class="mini-btn" type="button" data-action="queue-priority-up" data-model-ref="' + this._escapeHtml(modelRef) + '" data-queue-status="' + this._escapeHtml(queueStatus) + '">+P</button>'
          + '    <button class="mini-btn" type="button" data-action="queue-mark-queued" data-model-ref="' + this._escapeHtml(modelRef) + '">Queued</button>'
          + '    <button class="mini-btn" type="button" data-action="queue-mark-done" data-model-ref="' + this._escapeHtml(modelRef) + '">Done</button>'
          + '    <button class="mini-btn" type="button" data-action="queue-clear" data-model-ref="' + this._escapeHtml(modelRef) + '">Clear</button>'
          + '  </div>'
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

    var signalChips = "";
    if (recent > 0) {
      signalChips += this._renderModelTagChip("Recent", "signal-chip");
    }
    if (frequent > 0) {
      signalChips += this._renderModelTagChip("Frequent", "signal-chip");
    }
    if (common > 0) {
      signalChips += this._renderModelTagChip("Common", "signal-chip");
    }
    if (!signalChips) {
      signalChips = this._renderModelTagChip("No ranking signal", "subtle-chip");
    }

    var favoriteButton = ''
      + '<button class="icon-action favorite-action' + (modelFavorite ? ' is-active' : '') + '" type="button" data-action="toggle-favorite" data-model-ref="' + this._escapeHtml(modelRef) + '" data-next-favorite="' + this._escapeHtml(modelFavorite ? 'false' : 'true') + '" aria-label="' + this._escapeHtml(modelFavorite ? 'Remove favorite' : 'Add favorite') + '">'
      + '  <ha-icon icon="' + this._escapeHtml(modelFavorite ? 'mdi:star' : 'mdi:star-outline') + '"></ha-icon>'
      + '</button>';
    var queueQuickAction = (queueStatus === "queued")
      ? '<button class="toolbar-btn queue-quick-btn" type="button" data-action="queue-clear" data-model-ref="' + this._escapeHtml(modelRef) + '">Dequeue</button>'
      : '<button class="toolbar-btn queue-quick-btn" type="button" data-action="queue-mark-queued" data-model-ref="' + this._escapeHtml(modelRef) + '">Queue</button>';
    var openQuickAction = ''
      + '<button class="toolbar-btn open-quick-btn" type="button" data-action="view-model-detail" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '">Open</button>';

    var compactMainHtml = ''
      + '<div class="body compact-main">'
      + '  <div class="compact-top-actions">'
      + '    <button class="icon-action viewer" type="button" data-action="open-model-viewer" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="Open 3D viewer"><ha-icon icon="mdi:cube-scan"></ha-icon></button>'
      + favoriteButton
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
      + '    <h3 class="title">' + this._escapeHtml(name) + '</h3>'
      + '    <span class="compact-last-printed">' + this._escapeHtml(this._relativeTimeLabel(lastPrintedAt)) + '</span>'
      + '  </div>'
      + '  <div class="metrics compact-metrics">'
      + this._renderModelMetric('Archives', linkedCount)
      + this._renderModelMetric('Last printed', this._relativeTimeLabel(lastPrintedAt))
      + this._renderModelMetric('Success', successLabel)
      + '  </div>'
      + '  <div class="chip-row signal-row">' + signalChips + '</div>'
      + '  <div class="compact-tags-row">'
      + '    <div class="tags">' + tagMarkup + '</div>'
      + '    <div class="compact-file-kinds">' + fileKindChipMarkup + '</div>'
      + '  </div>'
      + '  <div class="compact-action-row">'
      + openQuickAction
      + queueQuickAction
      + (sourceDownloadUrl ? '<button class="toolbar-btn" type="button" data-action="open-model" data-url="' + this._escapeHtml(sourceDownloadUrl) + '">Source</button>' : '')
      + '  </div>'
      + '</div>';

    var mediaBodyHtml = ''
      + '<div class="body media-body">'
      + '  <div class="media-title-row">'
      + '    <h3 class="title">' + this._escapeHtml(name) + '</h3>'
      + '    <span class="compact-last-printed">' + this._escapeHtml(this._relativeTimeLabel(lastPrintedAt)) + '</span>'
      + '  </div>'
      + '  <div class="subtle-line">' + creatorChip + collectionChips + (hiddenCollectionCount ? this._renderModelTagChip('+' + String(hiddenCollectionCount) + ' more', 'subtle-chip') : '') + '</div>'
      + '  <div class="chip-row provenance-row">'
      + this._renderModelTagChip(this._originTypeLabel(originType), 'origin-chip')
      + sourceChipHtml
      + publishedDestinationChips
      + (hiddenDestinationCount ? this._renderModelTagChip('+' + String(hiddenDestinationCount), 'publish-chip') : '')
      + '  </div>'
      + '  <div class="metrics media-metrics">'
      + this._renderModelMetric('Archives', linkedCount)
      + this._renderModelMetric('Success', successLabel)
      + this._renderModelMetric('Previews', mediaCount || 0)
      + '  </div>'
      + '  <div class="media-footer-row">'
      + '    <div class="tags">' + tagMarkup + '</div>'
      + '    <div class="media-actions">'
      + openQuickAction
      + queueQuickAction
      + favoriteButton
      + advancedActions
      + '    </div>'
      + '  </div>'
      + '</div>';

    var listBodyHtml = ''
      + '<div class="body list-body">'
      + '  <div class="list-grid">'
      + '    <div class="list-cell list-name">'
      + '      <div class="title">' + this._escapeHtml(name) + '</div>'
      + '      <div class="subtle-line">' + creatorChip + '</div>'
      + '    </div>'
      + '    <div class="list-cell">' + this._renderModelTagChip(this._originTypeLabel(originType), 'origin-chip') + '</div>'
      + '    <div class="list-cell">' + this._renderModelTagChip(sourcePlatform ? this._platformDisplayLabel(sourcePlatform) : 'Not set', 'subtle-chip') + '</div>'
      + '    <div class="list-cell list-num">' + this._escapeHtml(String(linkedCount)) + '</div>'
      + '    <div class="list-cell list-num">' + this._escapeHtml(this._relativeTimeLabel(lastPrintedAt)) + '</div>'
      + '    <div class="list-cell list-num">' + this._escapeHtml(successLabel) + '</div>'
      + '    <div class="list-cell">' + (publishedDestinationChips || this._renderModelTagChip('Not published', 'subtle-chip')) + '</div>'
      + '    <div class="list-cell">' + tagMarkup + '</div>'
      + '    <div class="list-cell list-actions">'
      + openQuickAction
      + queueQuickAction
      + favoriteButton
      + advancedActions
      + '    </div>'
      + '  </div>'
      + '</div>';

    if (this._viewMode === "media") {
      return ''
        + '<article class="model-card view-media' + queueRibbonClass + '" tabindex="0" role="button" data-action="view-model-detail" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="Open details for ' + this._escapeHtml(name) + '">'
        + '  <div class="thumb-wrap media-wrap">'
        + '    <div class="media-preview media-surface" data-model-ref="' + this._escapeHtml(modelRef) + '" data-gallery-count="' + this._escapeHtml(String(mediaCount)) + '">' + previewHtml + '</div>'
        + '    <div class="media-overlay"><span class="card-mode-pill">Media</span>' + (mediaCount > 1 ? '<span class="media-counter" data-model-ref="' + this._escapeHtml(modelRef) + '">' + this._escapeHtml(String(mediaIndex + 1) + ' / ' + String(mediaCount)) + '</span>' : '') + '</div>'
        + (mediaCount > 1 ? '<div class="media-gallery-nav"><button class="icon-action" type="button" data-action="media-prev" data-model-ref="' + this._escapeHtml(modelRef) + '" data-gallery-count="' + this._escapeHtml(String(mediaCount)) + '" aria-label="Previous model image"><ha-icon icon="mdi:chevron-left"></ha-icon></button><button class="icon-action" type="button" data-action="media-next" data-model-ref="' + this._escapeHtml(modelRef) + '" data-gallery-count="' + this._escapeHtml(String(mediaCount)) + '" aria-label="Next model image"><ha-icon icon="mdi:chevron-right"></ha-icon></button></div>' : '')
        + '  </div>'
        + mediaBodyHtml
        + '</article>';
    }

    if (this._viewMode === "list") {
      return ''
        + '<article class="model-card view-list' + queueRibbonClass + '" tabindex="0" role="button" data-action="view-model-detail" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="Open details for ' + this._escapeHtml(name) + '">'
        + '  <div class="thumb-wrap list-wrap"><div class="thumb list-thumb">' + previewHtml + '</div><span class="card-mode-pill list-mode">List</span></div>'
        + listBodyHtml
        + '</article>';
    }

    return ''
      + '<article class="model-card view-compact' + queueRibbonClass + '" tabindex="0" role="button" data-action="view-model-detail" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="Open details for ' + this._escapeHtml(name) + '">'
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

  _renderFileKindChipRow(counts) {
    var modelFiles = this._coerceNonNegativeInt(counts && counts.model_files);
    var images = this._coerceNonNegativeInt(counts && counts.images);
    var other = this._coerceNonNegativeInt(counts && counts.other);
    var chips = "";
    if (modelFiles && modelFiles > 0) {
      chips += this._renderModelTagChip("Files " + String(modelFiles), "file-kind-chip file-kind-model");
    }
    if (images && images > 0) {
      chips += this._renderModelTagChip("Images " + String(images), "file-kind-chip file-kind-image");
    }
    if (other && other > 0) {
      chips += this._renderModelTagChip("Other " + String(other), "file-kind-chip file-kind-other");
    }
    return chips;
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

  _openModelDetailPopup(modelRef, modelName) {
    if (!modelRef) {
      return;
    }

    this._fireBrowserModEvent("browser_mod.popup", {
      title: modelName || "Model Details",
      size: "wide",
      content: {
        type: "custom:model-detail-popup-card",
        model_ref: modelRef,
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

  _render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }

    var resultsHtml = "";
    if (this._loading) {
      resultsHtml = '<div class="state-row">Loading catalog...</div>';
    } else if (this._error) {
      resultsHtml = '<div class="state-row error">' + this._escapeHtml(this._error) + '</div>';
    } else if (!this._results.length) {
      resultsHtml = '<div class="state-row">No models match the current filters.</div>';
    } else if (this._browserScope === "collections") {
      resultsHtml = this._renderCollectionCards();
    } else {
      resultsHtml = this._results.map(this._renderModelCard.bind(this)).join("");
    }

    this.shadowRoot.innerHTML = ''
      + '<style>'
      + ':host{--surface-1:rgba(15,23,42,0.12);--surface-2:rgba(15,23,42,0.22);--line:rgba(148,163,184,0.18);--line-strong:rgba(148,163,184,0.28);--accent:rgba(96,165,250,0.22);--accent-strong:rgba(96,165,250,0.38);--chip-bg:rgba(148,163,184,0.12);--chip-line:rgba(148,163,184,0.24);}'
      + 'ha-card{border-radius:20px;border:1px solid var(--line);background:linear-gradient(180deg,rgba(15,23,42,0.08),rgba(15,23,42,0.02));}'
      + '.shell{display:grid;gap:14px;padding:16px;}'
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
      + '.filter-row{display:grid;grid-template-columns:minmax(180px,1.4fr) repeat(4,minmax(130px,1fr)) auto auto auto;gap:8px;padding:12px;border-radius:16px;border:1px solid var(--line);background:rgba(148,163,184,0.08);align-items:center;}'
      + '.filter-search{grid-column:auto;}'
      + '.filter-chip{min-height:36px;padding:0 12px;border-radius:999px;border:1px solid var(--chip-line);background:rgba(15,23,42,0.08);color:var(--secondary-text-color);font-size:12px;font-weight:800;cursor:pointer;appearance:none;pointer-events:auto;position:relative;z-index:1;}'
      + '.filter-chip:hover,.filter-chip:focus-visible{background:rgba(148,163,184,0.18);outline:none;border-color:rgba(148,163,184,0.42);}'
      + '.filter-chip.active{color:var(--primary-text-color);}'
      + '.filter-chip.favorite.active{background:rgba(245,194,66,0.20);border-color:rgba(245,194,66,0.48);color:#f5c242;}'
      + '.filter-chip.docs.active{background:rgba(56,189,248,0.18);border-color:rgba(56,189,248,0.34);color:#93c5fd;}'
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
      + '.model-card{position:relative;min-width:0;border-radius:20px;border:1px solid var(--line);background:linear-gradient(180deg,rgba(15,23,42,0.22),rgba(15,23,42,0.14));overflow:visible;display:grid;cursor:pointer;transition:border-color .18s ease,box-shadow .18s ease;}'
      + '.model-card::after{content:"";position:absolute;inset:0;border-radius:inherit;background:transparent;box-shadow:inset 5px 0 0 transparent;opacity:0;transition:opacity .16s ease,box-shadow .16s ease;pointer-events:none;}'
      + '.model-card:hover{border-color:var(--accent-strong);box-shadow:0 14px 32px rgba(15,23,42,0.18);}'
      + '.model-card:focus-visible{outline:none;box-shadow:0 0 0 2px rgba(96,165,250,0.34);border-color:var(--accent-strong);}'
      + '.model-card.view-compact{grid-template-columns:minmax(148px,188px) minmax(0,1fr);grid-template-areas:"thumb main" "full full";column-gap:18px;row-gap:10px;padding:14px;align-items:start;}'
      + '.model-card.view-media{grid-template-rows:auto 1fr;}'
      + '.model-card.view-list{grid-template-columns:96px minmax(0,1fr);column-gap:12px;padding:14px;align-items:start;}'
      + '.model-card.is-queued::after{opacity:1;box-shadow:inset 5px 0 0 #f59e0b;}'
      + '.model-card.is-printing::after{opacity:1;box-shadow:inset 5px 0 0 #1e88e5;}'
      + '.model-card.is-done::after{opacity:1;box-shadow:inset 5px 0 0 #2e7d32;}'
      + '.thumb-wrap{position:relative;overflow:hidden;border-radius:16px;background:var(--surface-2);}'
      + '.view-compact .compact-wrap{grid-area:thumb;}'
      + '.view-compact .compact-main{grid-area:main;}'
      + '.view-compact .compact-full{grid-area:full;padding:2px 0 0;}'
      + '.compact-wrap{min-height:156px;}'
      + '.list-wrap{min-height:96px;}'
      + '.media-wrap{border-radius:18px 18px 0 0;}'
      + '.thumb,.media-preview{display:flex;align-items:center;justify-content:center;background:rgba(15,23,42,0.24);overflow:hidden;}'
      + '.thumb{width:100%;height:156px;}'
      + '.list-thumb{min-height:96px;height:96px;}'
      + '.media-preview{width:100%;aspect-ratio:16/9;min-height:220px;}'
      + '.thumb img,.media-preview img{width:100%;height:100%;object-fit:cover;display:block;}'
      // Suppress alt-text "flash" on lazy-loaded thumbnails: hide alt text and show a subtle placeholder gradient until src is set (issue #1383)
      + '.thumb img[data-thumbnail-lazy-url]:not([src]),.media-preview img[data-thumbnail-lazy-url]:not([src]){font-size:0;color:transparent;background:linear-gradient(120deg,rgba(148,163,184,0.18),rgba(148,163,184,0.06));}'
      + '.thumb img[data-thumbnail-lazy-url]:not([src])::before,.media-preview img[data-thumbnail-lazy-url]:not([src])::before{content:"";display:block;width:100%;height:100%;}'
      + '.thumb-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;opacity:.72;}'
      + '.thumb-empty ha-icon{--mdc-icon-size:28px;}'
      + '.thumb-empty-text{font-size:10px;margin-top:4px;}'
      + '.body{display:grid;gap:10px;min-width:0;padding:14px 16px 16px;}'
      + '.compact-main,.compact-full{gap:8px;animation:compact-enter .24s ease-out;}'
      + '.view-compact .body,.view-list .body{padding:0;}'
      + '.compact-top-actions{display:flex;justify-content:flex-end;align-items:center;gap:8px;}'
      + '.compact-top-actions .advanced-menu-shell{margin-left:0;}'
      + '.compact-title-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:10px;min-width:0;}'
      + '.compact-last-printed{font-size:11px;font-weight:700;color:var(--secondary-text-color);padding-top:2px;}'
      + '.favorite-action{border-color:rgba(245,194,66,0.34);}'
      + '.favorite-action.is-active{background:rgba(245,194,66,0.20);color:#f5c242;border-color:rgba(245,194,66,0.52);}'
      + '.favorite-action.is-active:hover,.favorite-action.is-active:focus-visible{background:rgba(245,194,66,0.26);color:#f5c242;border-color:rgba(245,194,66,0.62);box-shadow:0 0 0 1px rgba(245,194,66,0.28);transform:translateY(-1px);outline:none;}'
      + '.queue-quick-btn{min-height:30px;padding:0 10px;font-size:11px;border-radius:999px;}'
      + '.open-quick-btn{min-height:30px;padding:0 10px;font-size:11px;border-radius:999px;}'
      + '.header-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;column-gap:12px;row-gap:8px;}'
      + '.media-body{gap:8px;padding:12px 14px 14px;}'
      + '.media-title-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:start;}'
      + '.media-footer-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:start;}'
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
      + '.chip.file-kind-chip{font-size:10px;min-height:24px;padding:3px 8px;}'
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
      + '.list-body{padding:0;overflow-x:auto;}'
      + '.list-grid{display:grid;grid-template-columns:minmax(170px,2fr) minmax(120px,1fr) minmax(120px,1fr) minmax(80px,.7fr) minmax(100px,.8fr) minmax(80px,.7fr) minmax(180px,1.2fr) minmax(180px,1.2fr) auto;gap:8px;align-items:center;min-width:930px;padding:6px 0;}'
      + '.list-cell{min-width:0;display:flex;align-items:center;gap:6px;flex-wrap:wrap;}'
      + '.list-cell.list-num{font-size:12px;font-weight:700;justify-content:flex-end;}'
      + '.list-cell.list-actions{justify-content:flex-end;}'
      + '.list-cell.list-name{display:grid;gap:4px;}'
      + '.tag-project-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:10px;}'
      + '.media-status-chip{display:flex;justify-content:flex-end;}'
      + '.card-mode-pill,.media-counter{position:absolute;top:10px;z-index:1;display:inline-flex;align-items:center;min-height:24px;padding:0 8px;border-radius:999px;border:1px solid rgba(255,255,255,0.24);background:rgba(15,23,42,0.82);font-size:10px;font-weight:800;color:#fff;}'
      + '.card-mode-pill{left:10px;}'
      + '.card-mode-pill.list-mode{top:8px;left:8px;}'
      + '.media-counter{right:10px;}'
      + '.media-overlay{position:absolute;inset:0;pointer-events:none;}'
      + '.media-gallery-nav{position:absolute;left:10px;right:10px;bottom:10px;display:flex;justify-content:space-between;align-items:center;pointer-events:none;}'
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
      + '.advanced-action ha-icon{--mdc-icon-size:16px;}'
      + '.advanced-group-label{font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--secondary-text-color);padding:2px 2px 0;}'
      + '.advanced-inline-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;}'
      + '.state-row{padding:20px;border-radius:16px;border:1px dashed rgba(148,163,184,0.24);background:rgba(148,163,184,0.10);font-size:13px;color:var(--secondary-text-color);}'
      + '.state-row.error{background:rgba(185,28,28,0.16);color:var(--primary-text-color);}'
      + '@keyframes compact-enter{0%{opacity:0;transform:translateY(4px);}100%{opacity:1;transform:translateY(0);}}'
      + '@keyframes spin-refresh{from{transform:rotate(0deg);}to{transform:rotate(360deg);}}'
      + '@media (max-width: 1200px){.filter-row{grid-template-columns:minmax(180px,1fr) repeat(2,minmax(140px,1fr)) auto auto auto;}}'
      + '@media (max-width: 820px){.model-card.view-compact,.model-card.view-list{grid-template-columns:1fr;}.compact-wrap,.list-wrap{min-height:180px;}.thumb,.list-thumb{height:180px;}.tag-project-row,.header-row,.compact-title-row,.compact-tags-row,.media-title-row,.media-footer-row{grid-template-columns:minmax(0,1fr);}.media-status-chip,.header-actions,.media-actions{justify-content:flex-start;}.compact-top-actions{justify-content:flex-end;}.compact-file-kinds{justify-content:flex-start;}.list-grid{min-width:760px;}.title-row{align-items:flex-start;}.title-right{width:100%;justify-content:space-between;}.filter-row{grid-template-columns:1fr 1fr;}.page-control-strip{justify-content:flex-start;}}'
      + '@media (max-width: 560px){.shell{padding:14px;}.filter-row{grid-template-columns:1fr;}.title-left,.title-right{width:100%;}.sort-group{width:100%;justify-content:space-between;}.import-menu-items{right:auto;left:0;}.toolbar-group{width:100%;justify-content:flex-start;}.page-status{padding-left:0;}.media-preview{min-height:180px;}.metrics{grid-template-columns:1fr;}.advanced-menu{left:0;right:auto;min-width:min(260px,calc(100vw - 56px));}}'
      + '</style>'
      + '<ha-card>'
      + '  <div class="shell">'
      + '    <div class="shell-header">'
      + this._renderHeaderTitleRow()
      + this._renderFilterBar()
      + this._renderPageControlStrip()
      + '    </div>'
      + '    <div class="results view-' + this._escapeHtml(this._browserScope === "collections" ? "collections" : this._viewMode) + (this._showMedia ? '' : ' media-hidden') + '">' + resultsHtml + '</div>'
      + this._renderBottomMirrorStrip()
      + '  </div>'
      + '</ha-card>';

    setTimeout(function () {
      this._setupThumbnailLazyLoading();
    }.bind(this), 0);
  }
}

customElements.define("model-catalog-browser-card", ModelCatalogBrowserCard);

