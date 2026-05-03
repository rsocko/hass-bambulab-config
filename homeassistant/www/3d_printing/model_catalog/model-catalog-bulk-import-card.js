class ModelCatalogBulkImportCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._loadingDiscover = false;
    this._loadingImport = false;
    this._error = "";
    this._result = null;
    this._discoverSummary = null;
    this._discoverMeta = {
      folder_path: "",
      grouping_strategy: "by-folder",
      discovered_at: "",
    };
    this._proposals = [];

    this._boundClick = this._handleClick.bind(this);
    this._boundInput = this._handleInput.bind(this);
  }

  setConfig(config) {
    this._config = {
      title: config && config.title ? String(config.title) : "Bulk Working-Group Import",
      default_folder_path: config && config.default_folder_path ? String(config.default_folder_path) : "",
      default_grouping_strategy:
        config && config.default_grouping_strategy ? String(config.default_grouping_strategy) : "by-folder",
    };
    if (!this._discoverMeta.folder_path) {
      this._discoverMeta.folder_path = this._config.default_folder_path;
    }
    this._discoverMeta.grouping_strategy = this._config.default_grouping_strategy || "by-folder";
    this._render();
  }

  set hass(hass) {
    // Only store hass, don't re-render on every update
    // This prevents losing focus when hass updates frequently
    this._hass = hass;
  }

  connectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.addEventListener("click", this._boundClick);
      this.shadowRoot.addEventListener("input", this._boundInput);
      this.shadowRoot.addEventListener("change", this._boundInput);
    }
  }

  disconnectedCallback() {
    if (this.shadowRoot) {
      this.shadowRoot.removeEventListener("click", this._boundClick);
      this.shadowRoot.removeEventListener("input", this._boundInput);
      this.shadowRoot.removeEventListener("change", this._boundInput);
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
        // Keep latest known token.
      }
    }

    var token = auth.accessToken || (auth.data ? auth.data.accessToken : "");
    return token ? { Authorization: "Bearer " + token } : {};
  }

  _normalizeServiceResponse(payload) {
    if (Array.isArray(payload) && payload.length) {
      return this._normalizeServiceResponse(payload[0]);
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
      var message = payload && payload.message ? String(payload.message) : "Service call failed (HTTP " + String(response.status) + ")";
      throw new Error(message);
    }

    return this._normalizeServiceResponse(payload);
  }

  _readDiscoverForm() {
    var root = this.shadowRoot;
    if (!root) {
      return;
    }
    var folderNode = root.querySelector("#bulk-folder-path");
    var strategyNode = root.querySelector("#bulk-grouping-strategy");

    this._discoverMeta.folder_path = folderNode ? String(folderNode.value || "").trim() : "";
    this._discoverMeta.grouping_strategy = strategyNode ? String(strategyNode.value || "by-folder").trim() : "by-folder";
  }

  _proposalPayloadForImport() {
    return this._proposals.map(function (proposal) {
      return {
        proposal_id: proposal.proposal_id,
        title: proposal.title,
        action: proposal.action,
        merge_target: proposal.merge_target,
        files: Array.isArray(proposal.files) ? proposal.files : [],
      };
    });
  }

  async _discover() {
    if (!this._hass || this._loadingDiscover || this._loadingImport) {
      return;
    }

    this._readDiscoverForm();
    if (!this._discoverMeta.folder_path) {
      this._error = "Folder path is required.";
      this._render();
      return;
    }

    this._loadingDiscover = true;
    this._error = "";
    this._result = null;
    this._render();

    try {
      var request = {
        folder_path: this._discoverMeta.folder_path,
        grouping_strategy: this._discoverMeta.grouping_strategy || "by-folder",
      };

      var response = await this._callServiceWithResponse(
        "rest_command",
        "model_catalog_bulk_discover_working_groups",
        request,
      );

      if (response && response.success === false) {
        var discoverError = response.message || "Bulk discover failed.";
        if (response.error) {
          discoverError = discoverError + " (" + String(response.error) + ")";
        }
        throw new Error(discoverError);
      }
      if (response && typeof response.status === "number" && response.status >= 400) {
        throw new Error(response.message || ("Bulk discover failed (HTTP " + String(response.status) + ")."));
      }

      this._discoverSummary = response && response.summary ? response.summary : null;
      this._discoverMeta.discovered_at = response && response.discovered_at ? String(response.discovered_at) : "";
      this._proposals = Array.isArray(response && response.proposals)
        ? response.proposals.map(function (proposal) {
            return {
              proposal_id: String(proposal.proposal_id || ""),
              title: String(proposal.title || "Untitled Group"),
              action: "import",
              merge_target: "",
              files: Array.isArray(proposal.files) ? proposal.files : [],
              warnings: Array.isArray(proposal.warnings) ? proposal.warnings : [],
            };
          })
        : [];
    } catch (error) {
      this._proposals = [];
      this._discoverSummary = null;
      this._error = error && error.message ? String(error.message) : "Bulk discover failed.";
    } finally {
      this._loadingDiscover = false;
      this._render();
    }
  }

  async _importReviewed() {
    if (!this._hass || this._loadingImport || this._loadingDiscover) {
      return;
    }
    if (!this._proposals.length) {
      this._error = "Run discover first so there are proposals to import.";
      this._render();
      return;
    }

    this._loadingImport = true;
    this._error = "";
    this._result = null;
    this._render();

    try {
      var response = await this._callServiceWithResponse(
        "rest_command",
        "model_catalog_bulk_import_working_groups",
        {
          source_folder: this._discoverMeta.folder_path,
          grouping_strategy: this._discoverMeta.grouping_strategy || "by-folder",
          discovery_timestamp: this._discoverMeta.discovered_at,
          proposals: this._proposalPayloadForImport(),
        },
      );
      this._result = response;
    } catch (error) {
      this._error = error && error.message ? String(error.message) : "Bulk import failed.";
    } finally {
      this._loadingImport = false;
      this._render();
    }
  }

  _handleClick(event) {
    var target = event && event.target && event.target.closest ? event.target.closest("[data-action]") : null;
    if (!target) {
      return;
    }
    var action = String(target.getAttribute("data-action") || "");
    if (action === "discover") {
      this._discover();
      return;
    }
    if (action === "import") {
      this._importReviewed();
    }
  }

  _handleInput(event) {
    var target = event && event.target;
    if (!target || !target.dataset) {
      return;
    }

    var proposalId = String(target.dataset.proposalId || "");
    if (!proposalId) {
      return;
    }

    var proposal = this._proposals.find(function (item) {
      return item.proposal_id === proposalId;
    });
    if (!proposal) {
      return;
    }

    if (target.dataset.field === "title") {
      proposal.title = String(target.value || "").trim() || proposal.title;
      return;
    }
    if (target.dataset.field === "action") {
      proposal.action = String(target.value || "import").trim();
      return;
    }
    if (target.dataset.field === "merge_target") {
      proposal.merge_target = String(target.value || "").trim();
      return;
    }
  }

  _renderProposal(proposal) {
    var warnings = Array.isArray(proposal.warnings) ? proposal.warnings : [];
    var warningText = warnings.length ? "<div class=\"proposal-warnings\">Warnings: " + String(warnings.length) + "</div>" : "";
    return ""
      + "<div class=\"proposal\">"
      + "<div class=\"proposal-row\">"
      + "<input class=\"field\" data-proposal-id=\"" + String(proposal.proposal_id) + "\" data-field=\"title\" value=\"" + String(proposal.title).replace(/\"/g, "&quot;") + "\" />"
      + "<select class=\"field\" data-proposal-id=\"" + String(proposal.proposal_id) + "\" data-field=\"action\">"
      + "<option value=\"import\"" + (proposal.action === "import" ? " selected" : "") + ">Import</option>"
      + "<option value=\"merge\"" + (proposal.action === "merge" ? " selected" : "") + ">Merge</option>"
      + "<option value=\"skip\"" + (proposal.action === "skip" ? " selected" : "") + ">Skip</option>"
      + "</select>"
      + "<input class=\"field\" data-proposal-id=\"" + String(proposal.proposal_id) + "\" data-field=\"merge_target\" placeholder=\"merge target (for merge)\" value=\"" + String(proposal.merge_target || "").replace(/\"/g, "&quot;") + "\" />"
      + "</div>"
      + "<div class=\"proposal-meta\">"
      + "<span>Files: " + String((proposal.files || []).length) + "</span>"
      + "<span>Proposal: " + String(proposal.proposal_id) + "</span>"
      + "</div>"
      + warningText
      + "</div>";
  }

  _render() {
    if (!this.shadowRoot) {
      return;
    }
    var canImport = this._proposals.length > 0 && !this._loadingDiscover && !this._loadingImport;
    var discoverSummaryHtml = this._discoverSummary
      ? "<div class=\"summary\">"
        + "<span>Scanned: " + String(this._discoverSummary.scanned_file_count || 0) + "</span>"
        + "<span>Supported: " + String(this._discoverSummary.supported_file_count || 0) + "</span>"
        + "<span>Proposals: " + String(this._discoverSummary.proposal_count || 0) + "</span>"
        + "<span>Duplicate Warnings: " + String(this._discoverSummary.duplicate_warning_count || 0) + "</span>"
        + "</div>"
      : "";

    var resultHtml = "";
    if (this._result && this._result.success) {
      resultHtml = "<div class=\"result ok\">"
        + "Created groups: " + String(this._result.created_group_count || 0)
        + " | Created items: " + String(this._result.created_item_count || 0)
        + " | Duplicates skipped: " + String(this._result.duplicate_skipped_count || 0)
        + "</div>";
    }

    var proposalsHtml = this._proposals.length
      ? this._proposals.map(this._renderProposal.bind(this)).join("")
      : "<div class=\"empty\">Run discover to generate reviewable proposals.</div>";

    this.shadowRoot.innerHTML = ""
      + "<style>"
      + ":host{display:block;font-family:var(--primary-font-family,Segoe UI,sans-serif);}"
      + ".card{background:var(--card-background-color,#fff);border:1px solid rgba(120,120,120,.22);border-radius:14px;padding:14px;}"
      + ".title{font-size:1.1rem;font-weight:650;margin-bottom:10px;}"
      + ".controls{display:grid;grid-template-columns:2fr 1fr 1fr auto auto;gap:8px;align-items:center;margin-bottom:10px;}"
      + ".field,.btn{padding:8px 10px;border-radius:10px;border:1px solid rgba(120,120,120,.35);font:inherit;}"
      + ".field{background:var(--card-background-color,#fff);color:var(--primary-text-color);}"
      + "select.field{color-scheme:light dark;}"
      + ".field option,.field optgroup{background:var(--card-background-color,#fff);color:var(--primary-text-color);}"
      + ".btn{cursor:pointer;background:var(--secondary-background-color,#f7fafb);color:var(--primary-text-color);}"
      + ".btn.primary{background:var(--primary-color,#0d7a68);color:#fff;border-color:var(--primary-color,#0d7a68);}"
      + ".btn:disabled{opacity:.5;cursor:not-allowed;}"
      + ".summary{display:flex;gap:14px;flex-wrap:wrap;font-size:.9rem;color:var(--secondary-text-color,#555);margin:8px 0 10px;}"
      + ".proposal-list{display:grid;gap:10px;}"
      + ".proposal{border:1px solid rgba(120,120,120,.25);border-radius:12px;padding:10px;background:var(--secondary-background-color,#fbfcfd);color:var(--primary-text-color);}"
      + ".proposal-row{display:grid;grid-template-columns:2fr 1fr 2fr;gap:8px;}"
      + ".proposal-meta{display:flex;gap:14px;flex-wrap:wrap;font-size:.85rem;color:var(--secondary-text-color,#555);margin-top:6px;}"
      + ".proposal-warnings{margin-top:6px;font-size:.85rem;color:#93510f;}"
      + ".error{margin-top:10px;color:#b42318;font-size:.9rem;}"
      + ".result{margin-top:10px;padding:8px 10px;border-radius:10px;font-size:.9rem;}"
      + ".result.ok{background:rgba(22,163,74,0.16);color:var(--primary-text-color);border:1px solid rgba(34,197,94,0.45);}"
      + ".empty{font-size:.9rem;color:var(--secondary-text-color,#666);padding:8px 0;}"
      + "@media (max-width:900px){.controls{grid-template-columns:1fr;}.proposal-row{grid-template-columns:1fr;}}"
      + "</style>"
      + "<ha-card class=\"card\">"
      + "<div class=\"title\">" + String((this._config && this._config.title) || "Bulk Working-Group Import") + "</div>"
      + "<div class=\"controls\">"
      + "<input id=\"bulk-folder-path\" class=\"field\" placeholder=\"Folder path (example: D:/3D Printing)\" value=\"" + String(this._discoverMeta.folder_path || "").replace(/\"/g, "&quot;") + "\" />"
      + "<select id=\"bulk-grouping-strategy\" class=\"field\">"
      + "<option value=\"by-folder\"" + (this._discoverMeta.grouping_strategy === "by-folder" ? " selected" : "") + ">by-folder</option>"
      + "<option value=\"by-root\"" + (this._discoverMeta.grouping_strategy === "by-root" ? " selected" : "") + ">by-root</option>"
      + "<option value=\"flat\"" + (this._discoverMeta.grouping_strategy === "flat" ? " selected" : "") + ">flat</option>"
      + "</select>"
      + "<button class=\"btn\" data-action=\"discover\"" + (this._loadingDiscover || this._loadingImport ? " disabled" : "") + ">"
      + (this._loadingDiscover ? "Discovering..." : "Discover")
      + "</button>"
      + "<button class=\"btn primary\" data-action=\"import\"" + (canImport ? "" : " disabled") + ">"
      + (this._loadingImport ? "Importing..." : "Import Reviewed")
      + "</button>"
      + "</div>"
      + discoverSummaryHtml
      + "<div class=\"proposal-list\">" + proposalsHtml + "</div>"
      + (this._error ? "<div class=\"error\">" + String(this._error) + "</div>" : "")
      + resultHtml
      + "</ha-card>";
  }
}

if (!customElements.get("model-catalog-bulk-import-card")) {
  customElements.define("model-catalog-bulk-import-card", ModelCatalogBulkImportCard);
}
