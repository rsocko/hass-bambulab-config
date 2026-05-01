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
    this._pendingLoad = null;
    this._debounceHandle = null;

    this._boundClick = this._handleClick.bind(this);
    this._boundInput = this._handleInput.bind(this);
    this._boundChange = this._handleChange.bind(this);
    this._boundKeyDown = this._handleKeyDown.bind(this);
    this._didInitialRender = false;
    this._hasAttemptedLoad = false;
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
      title: config && config.title ? String(config.title) : "Curated Catalog Browser",
      per_page: config && Number.isFinite(Number(config.per_page))
        ? Math.max(1, Math.min(50, Number(config.per_page)))
        : 12,
    };
    this._pagination.per_page = this._config.per_page;
    this._render();
  }

  set hass(hass) {
    var hadHass = !!this._hass;
    this._hass = hass;

    if (!hadHass && !this._hasAttemptedLoad && !this._loading && !this._error) {
      this._hasAttemptedLoad = true;
      this._requestLoad(1, false);
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
    }
  }

  disconnectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.removeEventListener("click", this._boundClick);
      this.shadowRoot.removeEventListener("input", this._boundInput);
      this.shadowRoot.removeEventListener("change", this._boundChange);
      this.shadowRoot.removeEventListener("keydown", this._boundKeyDown);
    }
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

  async _loadPage(page, refresh) {
    if (!this._hass) {
      return;
    }

    this._loading = true;
    this._error = "";
    this._render();

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
    if (!event || event.key !== "Enter") {
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
    var target = event && event.target && event.target.closest ? event.target.closest("[data-action]") : null;
    if (!target) {
      return;
    }
    var action = String(target.getAttribute("data-action") || "");

    if (action === "clear-filters") {
      this._cancelScheduledApply();
      this._filters = this._defaultFilters();
      this._error = "";
      this._requestLoad(1, false);
      this._render();
      return;
    }

    if (action === "set-view") {
      var nextViewMode = this._normalizedViewMode(target.getAttribute("data-view-mode"));
      if (nextViewMode !== this._viewMode) {
        this._viewMode = nextViewMode;
        this._render();
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
      var url = String(target.getAttribute("data-url") || "").trim();
      if (url) {
        window.open(url, "_blank", "noopener,noreferrer");
      }
      return;
    }

    if (action === "view-model-detail") {
      var modelRef = String(target.getAttribute("data-model-ref") || "").trim();
      var modelName = String(target.getAttribute("data-model-name") || "Model").trim();
      if (!modelRef || !this._hass) {
        return;
      }
      this._openModelDetailPopup(modelRef, modelName);
      return;
    }

    if (action.indexOf("queue-") === 0) {
      var queueModelRef = String(target.getAttribute("data-model-ref") || "").trim();
      var queueStatus = String(target.getAttribute("data-queue-status") || "").trim().toLowerCase();
      if (!queueModelRef || this._loading) {
        return;
      }

      try {
        this._error = "";

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

    var ranking = model && model.ranking && typeof model.ranking === "object" ? model.ranking : {};
    var recent = Number(ranking.recent_score || 0);
    var frequent = Number(ranking.frequent_score || 0);
    var common = Number(ranking.common_score || 0);

    var fields = model && model.custom_fields && typeof model.custom_fields === "object" ? model.custom_fields : {};
    var queueStatus = String(fields.to_print_status || "").trim();
    var queuePriority = String(fields.to_print_priority || "").trim();
    var modelRef = String(model.public_id || model.model_id || model.model_url || "");
    var queueLabel = queueStatus ? queueStatus + (queuePriority ? " (P" + queuePriority + ")" : "") : "none";

    var queueChip = queueStatus
      ? '<span class="chip queue">Queue: ' + this._escapeHtml(queueLabel) + '</span>'
      : '<span class="chip neutral">Queue: none</span>';

    var rankingChips = [
      '<span class="chip">Recent ' + this._escapeHtml(recent.toFixed(2)) + '</span>',
      '<span class="chip">Frequent ' + this._escapeHtml(frequent.toFixed(2)) + '</span>',
      '<span class="chip">Common ' + this._escapeHtml(common.toFixed(2)) + '</span>',
    ].join("");

    var previewHtml = model.preview_url
      ? '<img src="' + this._escapeHtml(String(model.preview_url)) + '" alt="' + this._escapeHtml(name) + ' preview">'
      : '<div class="thumb-empty"><ha-icon icon="mdi:cube-outline"></ha-icon><div class="thumb-empty-text">No preview</div></div>';

    var titleActions = ''
      + '<div class="title-actions">'
      + '  <button class="open-btn" type="button" data-action="view-model-detail" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '">Details</button>'
      + '  <button class="open-btn" type="button" data-action="open-model" data-url="' + this._escapeHtml(modelUrl) + '">Open</button>'
      + '</div>';

    var metaHtml = ''
      + '<div class="meta">' + this._escapeHtml(creator) + ' / ' + this._escapeHtml(collections.join(", ") || "No collection") + '</div>'
      + '<div class="meta">Tags: ' + this._escapeHtml(this._formatTagList(tags)) + '</div>'
      + '<div class="meta">Linked archives: ' + String(linkedCount) + '</div>';

    var queueActions = ''
      + '<div class="queue-actions">'
      + '  <button class="mini-btn" type="button" data-action="queue-priority-down" data-model-ref="' + this._escapeHtml(modelRef) + '" data-queue-status="' + this._escapeHtml(queueStatus) + '">-P</button>'
      + '  <button class="mini-btn" type="button" data-action="queue-priority-up" data-model-ref="' + this._escapeHtml(modelRef) + '" data-queue-status="' + this._escapeHtml(queueStatus) + '">+P</button>'
      + '  <button class="mini-btn" type="button" data-action="queue-mark-queued" data-model-ref="' + this._escapeHtml(modelRef) + '">Queued</button>'
      + '  <button class="mini-btn" type="button" data-action="queue-mark-done" data-model-ref="' + this._escapeHtml(modelRef) + '">Done</button>'
      + '  <button class="mini-btn" type="button" data-action="queue-clear" data-model-ref="' + this._escapeHtml(modelRef) + '">Clear</button>'
      + '</div>';

    var bodyHtml = ''
      + '<div class="body">'
      + '  <div class="title-row">'
      + '    <h3 class="title">' + this._escapeHtml(name) + '</h3>'
      + titleActions
      + '  </div>'
      + metaHtml
      + '  <div class="chips">' + queueChip + rankingChips + '</div>'
      + queueActions
      + '</div>';

    if (this._viewMode === "media") {
      return ''
        + '<article class="model-card view-media">'
        + '  <div class="media-preview">' + previewHtml + '</div>'
        + bodyHtml
        + '</article>';
    }

    if (this._viewMode === "list") {
      return ''
        + '<article class="model-card view-list">'
        + '  <div class="thumb list-thumb">' + previewHtml + '</div>'
        + bodyHtml
        + '</article>';
    }

    return ''
      + '<article class="model-card view-compact">'
      + '  <div class="thumb">' + previewHtml + '</div>'
      + bodyHtml
      + '</article>';
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
      + 'ha-card{border-radius:20px;border:1px solid rgba(148,163,184,0.18);background:linear-gradient(180deg,rgba(15,23,42,0.08),rgba(15,23,42,0.02));}'
      + '.shell{display:grid;gap:14px;padding:16px;}'
      + '.shell-header{display:grid;gap:10px;}'
      + '.title-row-main{display:flex;justify-content:space-between;align-items:flex-end;gap:10px;flex-wrap:wrap;}'
      + '.card-title{font-size:18px;font-weight:800;line-height:1.2;}'
      + '.card-subtitle{font-size:12px;color:var(--secondary-text-color);}'
      + '.browser-toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;padding:10px 12px;border-radius:16px;border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.12);}'
      + '.toolbar-cluster{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0;}'
      + '.pager-cluster{flex:1 1 320px;}'
      + '.view-cluster{justify-content:flex-end;}'
      + '.toolbar-btn{min-height:36px;padding:0 12px;border-radius:999px;border:1px solid rgba(148,163,184,0.24);background:rgba(148,163,184,0.12);color:var(--primary-text-color);font-size:12px;font-weight:700;cursor:pointer;}'
      + '.toolbar-btn.toggle.active{background:rgba(30,64,175,0.24);border-color:rgba(96,165,250,0.42);}'
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
      + '.results.view-compact{grid-template-columns:repeat(auto-fill,minmax(320px,1fr));}'
      + '.results.view-media{grid-template-columns:repeat(auto-fill,minmax(360px,1fr));}'
      + '.results.view-list{grid-template-columns:1fr;}'
      + '.model-card{min-width:0;border-radius:18px;border:1px solid rgba(148,163,184,0.22);background:rgba(15,23,42,0.14);overflow:hidden;}'
      + '.model-card.view-compact{display:grid;grid-template-columns:112px minmax(0,1fr);gap:0;}'
      + '.model-card.view-media{display:grid;grid-template-rows:auto 1fr;}'
      + '.model-card.view-list{display:grid;grid-template-columns:96px minmax(0,1fr);}'
      + '.thumb,.media-preview{display:flex;align-items:center;justify-content:center;background:rgba(15,23,42,0.24);overflow:hidden;}'
      + '.thumb{width:112px;height:100%;min-height:120px;}'
      + '.list-thumb{width:96px;min-height:96px;}'
      + '.media-preview{width:100%;aspect-ratio:16/9;min-height:220px;}'
      + '.thumb img,.media-preview img{width:100%;height:100%;object-fit:cover;display:block;}'
      + '.thumb-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;opacity:.72;}'
      + '.thumb-empty ha-icon{--mdc-icon-size:28px;}'
      + '.thumb-empty-text{font-size:10px;margin-top:4px;}'
      + '.body{display:grid;gap:8px;padding:12px 14px;min-width:0;}'
      + '.title-row{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;flex-wrap:wrap;}'
      + '.title{margin:0;font-size:14px;font-weight:800;line-height:1.35;overflow-wrap:anywhere;}'
      + '.title-actions{display:flex;gap:6px;flex-wrap:wrap;}'
      + '.open-btn,.mini-btn{min-height:30px;padding:0 10px;border-radius:999px;border:1px solid rgba(96,165,250,0.30);background:rgba(30,64,175,0.16);color:var(--primary-text-color);font-size:11px;font-weight:700;cursor:pointer;}'
      + '.mini-btn{border-color:rgba(148,163,184,0.28);background:rgba(148,163,184,0.12);}'
      + '.meta{font-size:12px;line-height:1.45;color:var(--secondary-text-color);overflow-wrap:anywhere;}'
      + '.chips{display:flex;flex-wrap:wrap;gap:6px;}'
      + '.chip{font-size:10px;font-weight:700;padding:4px 8px;border-radius:999px;background:rgba(96,165,250,0.14);border:1px solid rgba(96,165,250,0.24);}'
      + '.chip.neutral{background:rgba(148,163,184,0.14);border-color:rgba(148,163,184,0.26);}'
      + '.chip.queue{background:rgba(16,185,129,0.16);border-color:rgba(16,185,129,0.28);}'
      + '.queue-actions{display:flex;flex-wrap:wrap;gap:6px;}'
      + '.state-row{padding:20px;border-radius:16px;border:1px dashed rgba(148,163,184,0.24);background:rgba(148,163,184,0.10);font-size:13px;color:var(--secondary-text-color);}'
      + '.state-row.error{background:rgba(185,28,28,0.16);color:var(--primary-text-color);}'
      + '@media (max-width: 1100px){.controls{grid-template-columns:repeat(3,minmax(0,1fr));}}'
      + '@media (max-width: 820px){.controls{grid-template-columns:repeat(2,minmax(0,1fr));}.model-card.view-compact,.model-card.view-list{grid-template-columns:1fr;}.thumb,.list-thumb{width:100%;height:180px;}}'
      + '@media (max-width: 560px){.shell{padding:14px;}.controls{grid-template-columns:1fr;}.browser-toolbar{align-items:stretch;}.toolbar-cluster{width:100%;}.pager-cluster,.view-cluster{justify-content:flex-start;}.toolbar-btn{flex:1 1 auto;}.page-status{width:100%;padding-left:0;}.media-preview{min-height:180px;}}'
      + '</style>'
      + '<ha-card>'
      + '  <div class="shell">'
      + '    <div class="shell-header">'
      + '      <div class="title-row-main">'
      + '        <div>'
      + '          <div class="card-title">' + this._escapeHtml(this._config.title) + '</div>'
      + '          <div class="card-subtitle">Shared browser shell for curated catalog browsing.</div>'
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
  }
}

customElements.define("model-catalog-browser-card", ModelCatalogBrowserCard);
