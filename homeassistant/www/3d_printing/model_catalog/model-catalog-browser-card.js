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

    this._filters = {
      q: "",
      collection: "",
      creator: "",
      tag: "",
      to_print_status: "",
      to_print_priority_min: "",
      to_print_priority_max: "",
      sort: "recent",
    };

    this._boundClick = this._handleClick.bind(this);
    this._boundKeyDown = this._handleKeyDown.bind(this);
    this._didInitialRender = false;
    this._hasAttemptedLoad = false;
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

    // Perform an initial load only once when hass first connects.
    // This prevents infinite loops when search returns empty results (which
    // would otherwise trigger another load on the next hass state update).
    if (!hadHass && !this._hasAttemptedLoad && !this._loading && !this._error) {
      this._hasAttemptedLoad = true;
      this._loadPage(1, false);
    }

    // Avoid rerendering on every HA state update so text inputs keep focus/value
    // while the operator is typing filter criteria.
    if (!hadHass || !this._didInitialRender) {
      this._didInitialRender = true;
      this._render();
    }
  }

  connectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.addEventListener("click", this._boundClick);
      this.shadowRoot.addEventListener("keydown", this._boundKeyDown);
    }
  }

  disconnectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.removeEventListener("click", this._boundClick);
      this.shadowRoot.removeEventListener("keydown", this._boundKeyDown);
    }
  }

  getCardSize() {
    return 8;
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
        // Keep using the latest known token.
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
  }

  async _loadPage(page, refresh) {
    if (!this._hass || this._loading) {
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
      this._pagination.total = 0;
      this._pagination.total_pages = 0;
      this._error = error && error.message ? String(error.message) : "Could not load model catalog.";
    } finally {
      this._loading = false;
      this._render();
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
    this._syncFormIntoFilters();
    this._loadPage(1, false);
  }

  async _handleClick(event) {
    var target = event && event.target && event.target.closest ? event.target.closest("[data-action]") : null;
    if (!target) {
      return;
    }
    var action = String(target.getAttribute("data-action") || "");

    if (action === "search") {
      this._syncFormIntoFilters();
      this._loadPage(1, false);
      return;
    }

    if (action === "refresh") {
      this._syncFormIntoFilters();
      this._loadPage(1, true);
      return;
    }

    if (action === "prev-page" && this._pagination.page > 1) {
      this._syncFormIntoFilters();
      this._loadPage(this._pagination.page - 1, false);
      return;
    }

    if (action === "next-page" && this._pagination.page < this._pagination.total_pages) {
      this._syncFormIntoFilters();
      this._loadPage(this._pagination.page + 1, false);
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
      var modelRef = String(target.getAttribute("data-model-ref") || "").trim();
      var queueStatus = String(target.getAttribute("data-queue-status") || "").trim().toLowerCase();
      if (!modelRef || this._loading) {
        return;
      }

      try {
        this._error = "";

        if (action === "queue-priority-up") {
          var priorityUpPayload = {
            model_ref: modelRef,
            action: "priority_up",
          };
          if (!queueStatus || queueStatus === "none") {
            priorityUpPayload.to_print_status = "queued";
          }
          await this._callServiceWithResponse("rest_command", "model_catalog_update_model_queue", {
            model_ref: priorityUpPayload.model_ref,
            action: priorityUpPayload.action,
            to_print_status: priorityUpPayload.to_print_status,
          });
        } else if (action === "queue-priority-down") {
          var priorityDownPayload = {
            model_ref: modelRef,
            action: "priority_down",
          };
          if (!queueStatus || queueStatus === "none") {
            priorityDownPayload.to_print_status = "queued";
          }
          await this._callServiceWithResponse("rest_command", "model_catalog_update_model_queue", {
            model_ref: priorityDownPayload.model_ref,
            action: priorityDownPayload.action,
            to_print_status: priorityDownPayload.to_print_status,
          });
        } else if (action === "queue-mark-queued") {
          await this._callServiceWithResponse("rest_command", "model_catalog_update_model_queue", {
            model_ref: modelRef,
            action: "mark_queued",
          });
        } else if (action === "queue-mark-done") {
          await this._callServiceWithResponse("rest_command", "model_catalog_update_model_queue", {
            model_ref: modelRef,
            action: "mark_done",
          });
        } else if (action === "queue-clear") {
          await this._callServiceWithResponse("rest_command", "model_catalog_update_model_queue", {
            model_ref: modelRef,
            action: "clear",
          });
        }

        await this._loadPage(this._pagination.page || 1, false);
      } catch (error) {
        this._error = error && error.message ? String(error.message) : "Could not update queue state.";
        this._render();
      }
    }
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

    var queueChip = queueStatus
      ? '<span class="chip queue">Queue: ' + this._escapeHtml(queueStatus + (queuePriority ? " (P" + queuePriority + ")" : "")) + '</span>'
      : '<span class="chip neutral">Queue: none</span>';

    var modelRef = String(model.public_id || model.model_id || model.model_url || "");

    var queueActions = ''
      + '<div class="queue-actions">'
      + '  <button class="mini-btn" type="button" data-action="queue-priority-down" data-model-ref="' + this._escapeHtml(modelRef) + '" data-queue-status="' + this._escapeHtml(queueStatus) + '">-P</button>'
      + '  <button class="mini-btn" type="button" data-action="queue-priority-up" data-model-ref="' + this._escapeHtml(modelRef) + '" data-queue-status="' + this._escapeHtml(queueStatus) + '">+P</button>'
      + '  <button class="mini-btn" type="button" data-action="queue-mark-queued" data-model-ref="' + this._escapeHtml(modelRef) + '">Queued</button>'
      + '  <button class="mini-btn" type="button" data-action="queue-mark-done" data-model-ref="' + this._escapeHtml(modelRef) + '">Done</button>'
      + '  <button class="mini-btn" type="button" data-action="queue-clear" data-model-ref="' + this._escapeHtml(modelRef) + '">Clear</button>'
      + '</div>';

    var rankingChips = [
      '<span class="chip">Recent ' + this._escapeHtml(recent.toFixed(2)) + '</span>',
      '<span class="chip">Frequent ' + this._escapeHtml(frequent.toFixed(2)) + '</span>',
      '<span class="chip">Common ' + this._escapeHtml(common.toFixed(2)) + '</span>',
    ].join("");

    var previewHtml = model.preview_url
      ? '<img src="' + this._escapeHtml(String(model.preview_url)) + '" alt="' + this._escapeHtml(name) + ' preview">'
      : '<div class="thumb-empty"><ha-icon icon="mdi:cube-outline"></ha-icon><div style="font-size:10px;margin-top:4px;">No preview</div></div>';

    return ''
      + '<article class="model-card">'
      + '  <div class="thumb">' + previewHtml + '</div>'
      + '  <div class="body">'
      + '    <div class="title-row">'
      + '      <h3 class="title">' + this._escapeHtml(name) + '</h3>'
      + '      <div class="title-actions">'
      + '        <button class="open-btn" type="button" data-action="view-model-detail" data-model-ref="' + this._escapeHtml(modelRef) + '" data-model-name="' + this._escapeHtml(name) + '">Details</button>'
      + '        <button class="open-btn" type="button" data-action="open-model" data-url="' + this._escapeHtml(modelUrl) + '">Open</button>'
      + '      </div>'
      + '    </div>'
      + '    <div class="meta">' + this._escapeHtml(creator) + ' / ' + this._escapeHtml(collections.join(", ") || "No collection") + '</div>'
      + '    <div class="meta">Tags: ' + this._escapeHtml(this._formatTagList(tags)) + '</div>'
      + '    <div class="meta">Linked archives: ' + String(linkedCount) + '</div>'
      + '    <div class="chips">' + queueChip + rankingChips + '</div>'
      + queueActions
      + '  </div>'
      + '</article>';
  }

  _openModelDetailPopup(modelRef, modelName) {
    if (!this._hass || !modelRef) {
      return;
    }
    try {
      this._hass.callService('browser_mod', 'popup', {
        title: modelName,
        size: 'wide',
        content: {
          type: 'custom:model-detail-popup-card',
          model_ref: modelRef,
          model_sidecar_url: 'http://localhost:8314',
        },
      });
    } catch (error) {
      console.error('Failed to open model detail popup:', error);
    }
  }

  _render() {
    if (!this.shadowRoot || !this._config) {
      return;
    }

    var cardsHtml = "";
    if (this._loading) {
      cardsHtml = '<div class="state-row">Loading catalog...</div>';
    } else if (this._error) {
      cardsHtml = '<div class="state-row error">' + this._escapeHtml(this._error) + '</div>';
    } else if (!this._results.length) {
      cardsHtml = '<div class="state-row">No models match the current filters.</div>';
    } else {
      cardsHtml = this._results.map(this._renderModelCard.bind(this)).join("");
    }

    this.shadowRoot.innerHTML = ''
      + '<style>'
      + 'ha-card{border-radius:18px;}'
      + '.wrap{display:grid;gap:14px;padding:14px;}'
      + '.header{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;}'
      + '.title{font-size:18px;font-weight:700;}'
      + '.controls{display:grid;gap:10px;grid-template-columns:repeat(8,minmax(0,1fr));}'
      + '.control{display:grid;gap:4px;min-width:0;}'
      + '.control label{font-size:11px;color:var(--secondary-text-color);font-weight:700;letter-spacing:.02em;}'
      + '.control-input{width:100%;box-sizing:border-box;padding:8px 10px;border-radius:10px;border:1px solid var(--divider-color,rgba(148,163,184,0.3));background:var(--card-background-color);color:var(--primary-text-color);}'
      + '.actions{display:flex;gap:8px;align-items:center;}'
      + '.btn{border:1px solid rgba(96,165,250,0.4);background:rgba(30,64,175,0.18);color:var(--primary-text-color);padding:8px 12px;border-radius:999px;cursor:pointer;font-weight:700;}'
      + '.btn.secondary{background:rgba(148,163,184,0.12);border-color:rgba(148,163,184,0.28);}'
      + '.btn:disabled{opacity:.6;cursor:not-allowed;}'
      + '.results{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));}'
      + '.model-card{display:grid;grid-template-columns:108px minmax(0,1fr);gap:10px;padding:10px;border-radius:14px;border:1px solid var(--divider-color,rgba(148,163,184,0.24));background:rgba(148,163,184,0.08);min-width:0;}'
      + '.thumb{width:108px;height:72px;border-radius:10px;overflow:hidden;background:rgba(15,23,42,0.24);display:flex;align-items:center;justify-content:center;}'
      + '.thumb img{width:100%;height:100%;object-fit:cover;display:block;}'
      + '.thumb-empty{opacity:.7;}'
      + '.thumb-empty ha-icon{--mdc-icon-size:24px;}'
      + '.body{display:grid;gap:6px;min-width:0;}'
      + '.title-row{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;}'
      + '.title-row .title{font-size:14px;font-weight:800;line-height:1.3;margin:0;overflow-wrap:anywhere;}'
      + '.title-actions{display:flex;gap:6px;flex-wrap:wrap;}'
      + '.open-btn{border:1px solid rgba(96,165,250,0.42);background:rgba(30,64,175,0.18);color:var(--primary-text-color);padding:4px 8px;border-radius:999px;cursor:pointer;font-size:11px;font-weight:700;}'
      + '.meta{font-size:12px;line-height:1.4;color:var(--secondary-text-color);overflow-wrap:anywhere;}'
      + '.queue-actions{display:flex;flex-wrap:wrap;gap:6px;}'
      + '.mini-btn{border:1px solid rgba(148,163,184,0.30);background:rgba(148,163,184,0.14);color:var(--primary-text-color);padding:3px 8px;border-radius:999px;cursor:pointer;font-size:11px;font-weight:700;}'
      + '.chips{display:flex;flex-wrap:wrap;gap:6px;}'
      + '.chip{font-size:10px;font-weight:700;padding:3px 8px;border-radius:999px;background:rgba(96,165,250,0.14);border:1px solid rgba(96,165,250,0.24);}'
      + '.chip.neutral{background:rgba(148,163,184,0.14);border-color:rgba(148,163,184,0.26);}'
      + '.chip.queue{background:rgba(16,185,129,0.16);border-color:rgba(16,185,129,0.28);}'
      + '.footer{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;}'
      + '.state-row{padding:16px;border-radius:12px;background:rgba(148,163,184,0.10);font-size:13px;}'
      + '.state-row.error{background:rgba(185,28,28,0.16);}'
      + '@media (max-width: 1100px){.controls{grid-template-columns:repeat(4,minmax(0,1fr));}}'
      + '@media (max-width: 980px){.controls{grid-template-columns:repeat(3,minmax(0,1fr));}}'
      + '@media (max-width: 640px){.controls{grid-template-columns:repeat(2,minmax(0,1fr));}.model-card{grid-template-columns:1fr;}.thumb{width:100%;height:140px;}}'
      + '</style>'
      + '<ha-card>'
      + '  <div class="wrap">'
      + '    <div class="header">'
      + '      <div class="title">' + this._escapeHtml(this._config.title) + '</div>'
      + '      <div class="actions">'
      + '        <button class="btn" type="button" data-action="search" ' + (this._loading ? 'disabled' : '') + '>Search</button>'
      + '        <button class="btn secondary" type="button" data-action="refresh" ' + (this._loading ? 'disabled' : '') + '>Refresh Cache</button>'
      + '      </div>'
      + '    </div>'
      + '    <div class="controls">'
      + '      <div class="control"><label for="mc-q">Query</label><input id="mc-q" class="control-input" type="text" value="' + this._escapeHtml(this._filters.q) + '"></div>'
      + '      <div class="control"><label for="mc-collection">Collection</label><input id="mc-collection" class="control-input" type="text" value="' + this._escapeHtml(this._filters.collection) + '"></div>'
      + '      <div class="control"><label for="mc-creator">Creator</label><input id="mc-creator" class="control-input" type="text" value="' + this._escapeHtml(this._filters.creator) + '"></div>'
      + '      <div class="control"><label for="mc-tag">Tag</label><input id="mc-tag" class="control-input" type="text" value="' + this._escapeHtml(this._filters.tag) + '"></div>'
      + '      <div class="control"><label for="mc-queue">Queue</label><select id="mc-queue" class="control-input">'
      + '        <option value=""' + (this._filters.to_print_status === '' ? ' selected' : '') + '>All</option>'
      + '        <option value="queued"' + (this._filters.to_print_status === 'queued' ? ' selected' : '') + '>Queued</option>'
      + '        <option value="done"' + (this._filters.to_print_status === 'done' ? ' selected' : '') + '>Done</option>'
      + '        <option value="none"' + (this._filters.to_print_status === 'none' ? ' selected' : '') + '>None</option>'
      + '      </select></div>'
      + '      <div class="control"><label for="mc-priority-min">Min Priority</label><input id="mc-priority-min" class="control-input" type="number" value="' + this._escapeHtml(this._filters.to_print_priority_min) + '"></div>'
      + '      <div class="control"><label for="mc-priority-max">Max Priority</label><input id="mc-priority-max" class="control-input" type="number" value="' + this._escapeHtml(this._filters.to_print_priority_max) + '"></div>'
      + '      <div class="control"><label for="mc-sort">Sort</label><select id="mc-sort" class="control-input">'
      + '        <option value="best"' + (this._filters.sort === 'best' ? ' selected' : '') + '>Best Match</option>'
      + '        <option value="recent"' + (this._filters.sort === 'recent' ? ' selected' : '') + '>Recent</option>'
      + '        <option value="frequent"' + (this._filters.sort === 'frequent' ? ' selected' : '') + '>Frequent</option>'
      + '        <option value="common"' + (this._filters.sort === 'common' ? ' selected' : '') + '>Common</option>'
      + '        <option value="priority"' + (this._filters.sort === 'priority' ? ' selected' : '') + '>Queue Priority</option>'
      + '        <option value="name"' + (this._filters.sort === 'name' ? ' selected' : '') + '>Name</option>'
      + '      </select></div>'
      + '    </div>'
      + '    <div class="results">' + cardsHtml + '</div>'
      + '    <div class="footer">'
      + '      <div>Total models: ' + String(this._pagination.total || 0) + '</div>'
      + '      <div class="actions">'
      + '        <button class="btn secondary" type="button" data-action="prev-page" ' + (this._loading || this._pagination.page <= 1 ? 'disabled' : '') + '>Prev</button>'
      + '        <div>Page ' + String(this._pagination.page || 1) + ' of ' + String(this._pagination.total_pages || 1) + '</div>'
      + '        <button class="btn secondary" type="button" data-action="next-page" ' + (this._loading || this._pagination.page >= this._pagination.total_pages ? 'disabled' : '') + '>Next</button>'
      + '      </div>'
      + '    </div>'
      + '  </div>'
      + '</ha-card>';
  }
}

customElements.define("model-catalog-browser-card", ModelCatalogBrowserCard);
