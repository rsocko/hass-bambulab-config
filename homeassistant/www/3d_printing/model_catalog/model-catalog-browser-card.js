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
      var msg = payload && payload.message ? String(payload.message) : "Service call failed (HTTP " + String(response.status) + ")";
      throw new Error(msg);
    }

    var normalized = this._normalizeServiceResponse(payload);
    var wrappedStatus = Number(normalized && normalized.status);
    if (Number.isFinite(wrappedStatus) && wrappedStatus >= 400) {
      var wrappedMessage = "";
      if (normalized && typeof normalized.content === "string") {
        wrappedMessage = normalized.content;
      } else if (normalized && normalized.content && typeof normalized.content.message === "string") {
        wrappedMessage = normalized.content.message;
      } else if (normalized && typeof normalized.message === "string") {
        wrappedMessage = normalized.message;
      }
      throw new Error((wrappedMessage || "Service call failed") + " (HTTP " + String(wrappedStatus) + ")");
    }

    return normalized;
  }

  _cancelScheduledApply() {
    if (this._debounceHandle) {
      clearTimeout(this._debounceHandle);
      this._debounceHandle = null;
    }
  }

  _scheduleDebouncedApply() {
    this._cancelScheduledApply();
    this._debounceHandle = setTimeout(function () {
      this._debounceHandle = null;
      this._applyFilters();
    }.bind(this), 280);
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
  }

  _applyFilters() {
    this._syncFormIntoFilters();
    this._requestLoad(1, false);
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
    if (!target || !target.classList || !target.classList.contains("control-input")) {
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
    var cardTarget = rawTarget && rawTarget.closest ? rawTarget.closest(".model-card[data-action='open-model-viewer']") : null;
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

    if (action === "set-view") {
      var nextViewMode = this._normalizedViewMode(target.getAttribute("data-view-mode"));
      if (nextViewMode !== this._viewMode) {
        this._viewMode = nextViewMode;
        this._activeActionMenu = "";
        this._render();
      }
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

    if (action === "open-model-viewer") {
      var viewerModelRef = String(target.getAttribute("data-model-ref") || "").trim();
      var viewerModelName = String(target.getAttribute("data-model-name") || "Model").trim();
      if (viewerModelRef) {
        this._openModelViewerPopup(viewerModelRef, viewerModelName);
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
    return "Page " + String(this._currentPage()) + " of " + String(this._pageCount());
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

    var mediaUrls = this._modelMediaUrls(model);
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
        this._render();
      }.bind(this));
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

  _escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _renderViewToggle(mode, label) {
    var active = this._viewMode === mode;
    return ''
      + '<button class="toolbar-btn toggle' + (active ? ' active' : '') + '" type="button" data-action="set-view" data-view-mode="' + this._escapeHtml(mode) + '" ' + (this._loading ? 'disabled' : '') + '>'
      + this._escapeHtml(label)
      + '</button>';
  }

  _renderPagingControls() {
    var page = this._currentPage();
    var pages = this._pageCount();
    return ''
      + '<div class="toolbar-cluster pager-cluster">'
      + '  <button class="toolbar-btn" type="button" data-action="first-page" ' + (this._loading || page <= 1 ? 'disabled' : '') + '>First</button>'
      + '  <button class="toolbar-btn" type="button" data-action="prev-page" ' + (this._loading || page <= 1 ? 'disabled' : '') + '>Prev</button>'
      + '  <div class="page-status">' + this._escapeHtml(this._pageStatusText()) + '</div>'
      + '  <button class="toolbar-btn" type="button" data-action="next-page" ' + (this._loading || page >= pages ? 'disabled' : '') + '>Next</button>'
      + '  <button class="toolbar-btn" type="button" data-action="last-page" ' + (this._loading || page >= pages ? 'disabled' : '') + '>Last</button>'
      + '</div>';
  }

  _renderTopToolbar() {
    return ''
      + '<div class="browser-toolbar top-toolbar">'
      + this._renderPagingControls()
      + '<div class="toolbar-cluster view-cluster">'
      + this._renderViewToggle("compact", "Compact")
      + this._renderViewToggle("media", "Media")
      + this._renderViewToggle("list", "List")
      + '</div>'
      + '</div>';
  }

  _renderBottomToolbar() {
    return ''
      + '<div class="browser-toolbar bottom-toolbar">'
      + '<div class="results-summary">Total models: ' + String(this._pagination.total || 0) + '</div>'
      + this._renderPagingControls()
      + '</div>';
  }

  _renderModelCard(model) {
    var modelUrl = String(model.model_url || "");
    var name = String(model.name || "Unnamed Model");
    var creator = String(model.creator_name || "Unknown Creator");
    var collections = Array.isArray(model.collection_names) ? model.collection_names : [];
    var tags = Array.isArray(model.keyword_names) ? model.keyword_names : [];
    var linkedCount = Number(model.linked_archive_count || 0) || 0;
    var modelRef = this._modelRef(model);
    var actionMenuOpen = this._activeActionMenu === modelRef;

    var ranking = model && model.ranking && typeof model.ranking === "object" ? model.ranking : {};
    var recent = Number(ranking.recent_score || 0);
    var frequent = Number(ranking.frequent_score || 0);
    var common = Number(ranking.common_score || 0);

    var fields = model && model.custom_fields && typeof model.custom_fields === "object" ? model.custom_fields : {};
    var queueStatus = String(fields.to_print_status || "").trim();
    var queuePriority = String(fields.to_print_priority || "").trim();
    var queueLabel = queueStatus ? queueStatus + (queuePriority ? " (P" + queuePriority + ")" : "") : "none";
    var queueChipClass = queueStatus === "queued" ? "queue" : (queueStatus === "done" ? "complete" : "neutral");
    var queueChip = this._renderModelTagChip("Queue: " + queueLabel, queueChipClass);
    var creatorChip = this._renderModelTagChip("By " + creator, "subtle-chip");
    var collectionLimit = this._viewMode === "compact" ? 2 : 3;
    var collectionChips = collections.slice(0, collectionLimit).map(function (collection) {
      return this._renderModelTagChip(collection, "subtle-chip");
    }.bind(this)).join("");
    var hiddenCollectionCount = Math.max(0, collections.length - collectionLimit);
    var tagLimit = this._viewMode === "compact" ? 5 : 4;
    var visibleTags = tags.slice(0, tagLimit);
    var hiddenTagCount = Math.max(0, tags.length - visibleTags.length);
    var tagMarkup = visibleTags.map(function (tag) {
      return this._renderModelTagChip(tag, "tag-chip");
    }.bind(this)).join("") + (hiddenTagCount ? this._renderModelTagChip("… +" + String(hiddenTagCount), "tag-chip") : "");
    var mediaUrls = this._modelMediaUrls(model);
    var mediaCount = mediaUrls.length;
    var mediaIndex = this._currentModelMediaIndex(modelRef, mediaCount || 1);
    var mediaUrl = mediaCount > 0 ? mediaUrls[mediaIndex] : "";
    var queuePriorityLabel = queuePriority ? ("P" + queuePriority) : "-";
    var previewLabel = mediaCount > 1 ? (String(mediaIndex + 1) + " / " + String(mediaCount)) : (this._loadingModelMedia[modelRef] ? "Loading media" : "Preview");

    // Load model detail in all view modes to fetch preview/media URLs
    this._loadModelMedia(model);

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
      + '  <button class="icon-action" type="button" data-action="toggle-actions" data-model-ref="' + this._escapeHtml(modelRef) + '" aria-label="Open advanced actions" aria-expanded="' + (actionMenuOpen ? 'true' : 'false') + '"><ha-icon icon="mdi:dots-horizontal"></ha-icon></button>'
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

    var titleCluster = ''
      + '<div class="title-cluster">'
      + '  <h3 class="title">' + this._escapeHtml(name) + '</h3>'
      + '  <div class="subtle-line">' + creatorChip + collectionChips + (hiddenCollectionCount ? this._renderModelTagChip("+" + String(hiddenCollectionCount) + " more", "subtle-chip") : "") + '</div>'
      + '</div>';

    var metaLine = ''
      + '<div class="chip-row status-line">'
      + queueChip
      + this._renderModelTagChip("Priority: " + queuePriorityLabel, "subtle-chip")
      + this._renderModelTagChip("Linked prints: " + String(linkedCount), "subtle-chip")
      + '</div>';

    var metrics = ''
      + '<div class="metrics">'
      + this._renderModelMetric("Recent", recent.toFixed(2))
      + this._renderModelMetric("Frequent", frequent.toFixed(2))
      + this._renderModelMetric("Common", common.toFixed(2))
      + '</div>';

    var detailFooter = ''
      + '<div class="tag-project-row">'
      + '  <div class="tags">' + tagMarkup + '</div>'
      + '  <div class="media-status-chip" data-model-ref="' + this._escapeHtml(modelRef) + '">' + this._renderModelTagChip(previewLabel, mediaCount > 1 ? "queue" : "neutral") + '</div>'
      + '</div>';

    var bodyHtml = ''
      + '<div class="body">'
      + '  <div class="header-row">'
      + titleCluster
      + '    <div class="header-actions">' + advancedActions + '</div>'
      + '  </div>'
      + metaLine
      + metrics
      + detailFooter
      + '</div>';

    if (this._viewMode === "media") {
      return ''
        + '<article class="model-card view-media" tabindex="0" role="button" data-action="open-model-viewer" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="Open 3D viewer for ' + this._escapeHtml(name) + '">'
        + '  <div class="thumb-wrap media-wrap">'
        + '    <div class="media-preview media-surface" data-model-ref="' + this._escapeHtml(modelRef) + '" data-gallery-count="' + this._escapeHtml(String(mediaCount)) + '">' + previewHtml + '</div>'
        + '    <div class="media-overlay"><span class="card-mode-pill">Media</span>' + (mediaCount > 1 ? '<span class="media-counter" data-model-ref="' + this._escapeHtml(modelRef) + '">' + this._escapeHtml(String(mediaIndex + 1) + ' / ' + String(mediaCount)) + '</span>' : '') + '</div>'
        + (mediaCount > 1 ? '<div class="media-gallery-nav"><button class="icon-action" type="button" data-action="media-prev" data-model-ref="' + this._escapeHtml(modelRef) + '" data-gallery-count="' + this._escapeHtml(String(mediaCount)) + '" aria-label="Previous model image"><ha-icon icon="mdi:chevron-left"></ha-icon></button><button class="icon-action" type="button" data-action="media-next" data-model-ref="' + this._escapeHtml(modelRef) + '" data-gallery-count="' + this._escapeHtml(String(mediaCount)) + '" aria-label="Next model image"><ha-icon icon="mdi:chevron-right"></ha-icon></button></div>' : '')
        + '  </div>'
        + bodyHtml
        + '</article>';
    }

    if (this._viewMode === "list") {
      return ''
        + '<article class="model-card view-list" tabindex="0" role="button" data-action="open-model-viewer" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="Open 3D viewer for ' + this._escapeHtml(name) + '">'
        + '  <div class="thumb-wrap list-wrap"><div class="thumb list-thumb">' + previewHtml + '</div><span class="card-mode-pill list-mode">List</span></div>'
        + bodyHtml
        + '</article>';
    }

    return ''
      + '<article class="model-card view-compact" tabindex="0" role="button" data-action="open-model-viewer" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '" aria-label="Open 3D viewer for ' + this._escapeHtml(name) + '">'
      + '  <div class="thumb-wrap compact-wrap"><div class="thumb">' + previewHtml + '</div><span class="card-mode-pill">Compact</span></div>'
      + bodyHtml
      + '</article>';
  }

  _openModelViewerPopup(modelRef, modelName) {
    if (!modelRef) {
      return;
    }
    this._fireBrowserModEvent("browser_mod.popup", {
      title: (modelName || "Model") + " - 3D Viewer",
      size: "wide",
      content: {
        type: "custom:model-detail-3d-viewer-tab",
        model_ref: modelRef,
        model_name: modelName || "Model",
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
    } else {
      resultsHtml = this._results.map(this._renderModelCard.bind(this)).join("");
    }

    this.shadowRoot.innerHTML = ''
      + '<style>'
      + ':host{--surface-1:rgba(15,23,42,0.12);--surface-2:rgba(15,23,42,0.22);--line:rgba(148,163,184,0.18);--line-strong:rgba(148,163,184,0.28);--accent:rgba(96,165,250,0.22);--accent-strong:rgba(96,165,250,0.38);--chip-bg:rgba(148,163,184,0.12);--chip-line:rgba(148,163,184,0.24);}'
      + 'ha-card{border-radius:20px;border:1px solid var(--line);background:linear-gradient(180deg,rgba(15,23,42,0.08),rgba(15,23,42,0.02));}'
      + '.shell{display:grid;gap:14px;padding:16px;}'
      + '.shell-header{display:grid;gap:10px;}'
      + '.title-row-main{display:flex;justify-content:space-between;align-items:flex-end;gap:10px;flex-wrap:wrap;}'
      + '.card-title{font-size:18px;font-weight:800;line-height:1.2;}'
      + '.card-subtitle{font-size:12px;color:var(--secondary-text-color);}'
      + '.browser-toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;padding:10px 12px;border-radius:16px;border:1px solid var(--line);background:var(--surface-1);}'
      + '.toolbar-cluster{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0;}'
      + '.pager-cluster{flex:1 1 320px;}'
      + '.view-cluster{justify-content:flex-end;}'
      + '.toolbar-btn{min-height:36px;padding:0 12px;border-radius:999px;border:1px solid var(--chip-line);background:var(--chip-bg);color:var(--primary-text-color);font-size:12px;font-weight:700;cursor:pointer;}'
      + '.toolbar-btn.toggle.active{background:var(--accent);border-color:var(--accent-strong);}'
      + '.toolbar-btn:disabled{opacity:.55;cursor:not-allowed;}'
      + '.page-status{font-size:12px;font-weight:700;color:var(--secondary-text-color);padding:0 4px;}'
      + '.results-summary{font-size:12px;font-weight:700;color:var(--secondary-text-color);}'
      + '.filter-panel{display:grid;gap:12px;padding:14px;border-radius:18px;border:1px solid rgba(148,163,184,0.16);background:rgba(148,163,184,0.08);}'
      + '.controls{display:grid;gap:10px;grid-template-columns:repeat(4,minmax(0,1fr));}'
      + '.control{display:grid;gap:5px;min-width:0;}'
      + '.control label{font-size:11px;color:var(--secondary-text-color);font-weight:800;letter-spacing:.03em;text-transform:uppercase;}'
      + '.control-input{width:100%;box-sizing:border-box;min-height:40px;padding:9px 12px;border-radius:12px;border:1px solid rgba(148,163,184,0.26);background:rgba(15,23,42,0.18);color:var(--primary-text-color);}'
      + 'select.control-input{color-scheme:light dark;}'
      + '.control-input option,.control-input optgroup{background:var(--card-background-color);color:var(--primary-text-color);}'
      + '.filter-actions{display:flex;justify-content:flex-start;}'
      + '.results{display:grid;gap:12px;}'
      + '.results.view-compact{grid-template-columns:repeat(auto-fill,minmax(360px,1fr));}'
      + '.results.view-media{grid-template-columns:repeat(auto-fill,minmax(360px,1fr));}'
      + '.results.view-list{grid-template-columns:1fr;}'
      + '.model-card{position:relative;min-width:0;border-radius:20px;border:1px solid var(--line);background:linear-gradient(180deg,rgba(15,23,42,0.22),rgba(15,23,42,0.14));overflow:visible;display:grid;cursor:pointer;transition:border-color .18s ease,box-shadow .18s ease;}'
      + '.model-card:hover{border-color:var(--accent-strong);box-shadow:0 14px 32px rgba(15,23,42,0.18);}'
      + '.model-card:focus-visible{outline:none;box-shadow:0 0 0 2px rgba(96,165,250,0.34);border-color:var(--accent-strong);}'
      + '.model-card.view-compact{grid-template-columns:minmax(148px,188px) minmax(0,1fr);column-gap:18px;padding:14px;align-items:start;}'
      + '.model-card.view-media{grid-template-rows:auto 1fr;}'
      + '.model-card.view-list{grid-template-columns:96px minmax(0,1fr);column-gap:12px;padding:14px;align-items:start;}'
      + '.thumb-wrap{position:relative;overflow:hidden;border-radius:16px;background:var(--surface-2);}'
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
      + '.view-compact .body,.view-list .body{padding:0;}'
      + '.header-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;column-gap:12px;row-gap:8px;}'
      + '.title-cluster{display:grid;gap:6px;min-width:0;}'
      + '.title{margin:0;font-size:15px;font-weight:800;line-height:1.35;overflow-wrap:anywhere;}'
      + '.subtle-line,.status-line,.tags{display:flex;flex-wrap:wrap;align-items:center;gap:6px;min-width:0;}'
      + '.header-actions{display:flex;align-items:flex-start;justify-content:flex-end;gap:8px;}'
      + '.chip{display:inline-flex;align-items:center;gap:6px;min-height:26px;font-size:11px;font-weight:700;padding:4px 9px;border-radius:999px;background:var(--chip-bg);border:1px solid var(--chip-line);color:var(--primary-text-color);}'
      + '.chip.neutral{background:rgba(148,163,184,0.14);border-color:rgba(148,163,184,0.26);}'
      + '.chip.queue{background:rgba(16,185,129,0.16);border-color:rgba(16,185,129,0.32);}'
      + '.chip.complete{background:rgba(96,165,250,0.14);border-color:rgba(96,165,250,0.30);}'
      + '.chip.subtle-chip{background:rgba(15,23,42,0.08);border-color:rgba(148,163,184,0.16);color:var(--secondary-text-color);}'
      + '.chip.tag-chip{background:rgba(96,165,250,0.10);border-color:rgba(96,165,250,0.20);}'
      + '.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;}'
      + '.metric{display:grid;gap:3px;padding:10px 12px;border-radius:14px;border:1px solid rgba(148,163,184,0.16);background:rgba(15,23,42,0.08);}'
      + '.metric-label{font-size:10px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;color:var(--secondary-text-color);}'
      + '.metric-value{font-size:14px;font-weight:800;line-height:1.2;}'
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
      + '.icon-action,.mini-btn,.advanced-action{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:34px;padding:0 10px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(15,23,42,0.14);color:var(--primary-text-color);font-size:11px;font-weight:700;cursor:pointer;}'
      + '.icon-action{width:34px;padding:0;}'
      + '.icon-action ha-icon{--mdc-icon-size:18px;}'
      + '.advanced-menu{position:absolute;top:40px;right:0;z-index:4;display:none;gap:8px;min-width:220px;padding:10px;border-radius:16px;border:1px solid var(--line-strong);background:rgba(15,23,42,0.96);box-shadow:0 18px 34px rgba(15,23,42,0.28);}'
      + '.advanced-menu.is-open{display:grid;}'
      + '.advanced-action{justify-content:flex-start;width:100%;padding:0 12px;border-radius:12px;background:rgba(148,163,184,0.10);}'
      + '.advanced-action.primary{background:rgba(96,165,250,0.14);border-color:rgba(96,165,250,0.26);}'
      + '.advanced-action ha-icon{--mdc-icon-size:16px;}'
      + '.advanced-group-label{font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--secondary-text-color);padding:2px 2px 0;}'
      + '.advanced-inline-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;}'
      + '.state-row{padding:20px;border-radius:16px;border:1px dashed rgba(148,163,184,0.24);background:rgba(148,163,184,0.10);font-size:13px;color:var(--secondary-text-color);}'
      + '.state-row.error{background:rgba(185,28,28,0.16);color:var(--primary-text-color);}'
      + '@media (max-width: 1100px){.controls{grid-template-columns:repeat(3,minmax(0,1fr));}}'
      + '@media (max-width: 820px){.controls{grid-template-columns:repeat(2,minmax(0,1fr));}.model-card.view-compact,.model-card.view-list{grid-template-columns:1fr;}.compact-wrap,.list-wrap{min-height:180px;}.thumb,.list-thumb{height:180px;}.tag-project-row,.header-row{grid-template-columns:minmax(0,1fr);}.media-status-chip,.header-actions{justify-content:flex-start;}}'
      + '@media (max-width: 560px){.shell{padding:14px;}.controls{grid-template-columns:1fr;}.browser-toolbar{align-items:stretch;}.toolbar-cluster{width:100%;}.pager-cluster,.view-cluster{justify-content:flex-start;}.toolbar-btn{flex:1 1 auto;}.page-status{width:100%;padding-left:0;}.media-preview{min-height:180px;}.metrics{grid-template-columns:1fr;}.advanced-menu{left:0;right:auto;min-width:min(260px,calc(100vw - 56px));}}'
      + '</style>'
      + '<ha-card>'
      + '  <div class="shell">'
      + '    <div class="shell-header">'
      + '      <div class="title-row-main">'
      + '        <div>'
      + '          <div class="card-title">' + this._escapeHtml(this._config.title) + '</div>'
      + '          <div class="card-subtitle">Shared browser shell for catalog browsing.</div>'
      + '        </div>'
      + '      </div>'
      + this._renderTopToolbar()
      + '    </div>'
      + '    <div class="filter-panel">'
      + '      <div class="controls">'
      + '        <div class="control"><label for="mc-q">Query</label><input id="mc-q" class="control-input" type="text" value="' + this._escapeHtml(this._filters.q) + '"></div>'
      + '        <div class="control"><label for="mc-collection">Collection</label><input id="mc-collection" class="control-input" type="text" value="' + this._escapeHtml(this._filters.collection) + '"></div>'
      + '        <div class="control"><label for="mc-creator">Creator</label><input id="mc-creator" class="control-input" type="text" value="' + this._escapeHtml(this._filters.creator) + '"></div>'
      + '        <div class="control"><label for="mc-tag">Tag</label><input id="mc-tag" class="control-input" type="text" value="' + this._escapeHtml(this._filters.tag) + '"></div>'
      + '        <div class="control"><label for="mc-queue">Queue</label><select id="mc-queue" class="control-input">'
      + '          <option value=""' + (this._filters.to_print_status === '' ? ' selected' : '') + '>All</option>'
      + '          <option value="queued"' + (this._filters.to_print_status === 'queued' ? ' selected' : '') + '>Queued</option>'
      + '          <option value="done"' + (this._filters.to_print_status === 'done' ? ' selected' : '') + '>Done</option>'
      + '          <option value="none"' + (this._filters.to_print_status === 'none' ? ' selected' : '') + '>None</option>'
      + '        </select></div>'
      + '        <div class="control"><label for="mc-priority-min">Min Priority</label><input id="mc-priority-min" class="control-input" type="number" value="' + this._escapeHtml(this._filters.to_print_priority_min) + '"></div>'
      + '        <div class="control"><label for="mc-priority-max">Max Priority</label><input id="mc-priority-max" class="control-input" type="number" value="' + this._escapeHtml(this._filters.to_print_priority_max) + '"></div>'
      + '        <div class="control"><label for="mc-sort">Sort</label><select id="mc-sort" class="control-input">'
      + '          <option value="best"' + (this._filters.sort === 'best' ? ' selected' : '') + '>Best Match</option>'
      + '          <option value="recent"' + (this._filters.sort === 'recent' ? ' selected' : '') + '>Recent</option>'
      + '          <option value="frequent"' + (this._filters.sort === 'frequent' ? ' selected' : '') + '>Frequent</option>'
      + '          <option value="common"' + (this._filters.sort === 'common' ? ' selected' : '') + '>Common</option>'
      + '          <option value="priority"' + (this._filters.sort === 'priority' ? ' selected' : '') + '>Queue Priority</option>'
      + '          <option value="name"' + (this._filters.sort === 'name' ? ' selected' : '') + '>Name</option>'
      + '        </select></div>'
      + '      </div>'
      + '      <div class="filter-actions">'
      + '        <button class="toolbar-btn" type="button" data-action="clear-filters" ' + (this._loading ? 'disabled' : '') + '>Clear Filters</button>'
      + '      </div>'
      + '    </div>'
      + '    <div class="results view-' + this._escapeHtml(this._viewMode) + '">' + resultsHtml + '</div>'
      + this._renderBottomToolbar()
      + '  </div>'
      + '</ha-card>';

    setTimeout(function () {
      this._setupThumbnailLazyLoading();
    }.bind(this), 0);
  }
}

customElements.define("model-catalog-browser-card", ModelCatalogBrowserCard);

