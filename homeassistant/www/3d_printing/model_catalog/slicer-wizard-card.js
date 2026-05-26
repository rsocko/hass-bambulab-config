/**
 * Slicer Wizard Card
 * 
 * Multi-step wizard for creating archives from source 3MF files.
 * 
 * Slice 6.0 MVP - Entry point, worker availability, and step scaffolding
 * - Worker health display (reachable / unavailable)
 * - Entry point confirmation dialog
 * - Graceful unavailable state
 * 
 * Slice 6.1+ will add:
 * - Validation review step
 * - Filament substitution picker
 * - Slice job progress monitoring
 * - Completion summary
 * 
 * Usage in browser_mod popup:
 * ```
 * service: browser_mod.popup
 * data:
 *   title: Create Archive From Source
 *   size: wide
 *   content:
 *     type: custom:slicer-wizard-card
 *     model_ref: "gridfinity-bin"
 *     model_entity: "input_text.model_catalog_sidecar_base_url"
 * ```
 * 
 * Or directly from model detail:
 * ```
 * await hass.callService('browser_mod', 'popup', {
 *   title: `Slice ${modelName}`,
 *   size: 'wide',
 *   content: {
 *     type: 'custom:slicer-wizard-card',
 *     model_ref: modelRef,
 *     model_entity: modelEntity
 *   }
 * });
 * ```
 */

(function () {
  class SlicerWizardCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._hass = null;
      this._config = null;

      // State
      this._modelRef = "";
      this._modelSidecarUrl = "";
      this._modelDetail = null;
      this._loading = false;
      this._error = "";
      this._workerStatus = null; // { reachable, providers: [...] }
      this._currentStep = "entry-point"; // "entry-point" | "validation" | "filament" | "timestamp" | "progress" | "completion"
      this._jobData = {
        model_ref: "",
        job_id: null,
        status: null,
        archive_id: null,
        created_archive_id: null,
        result_summary: null,
      };
      this._wizardState = {
        printer_id: null,
        plate_index: 0,
        patch_metadata: {},
        historical_timestamp: null,
        review_warnings: [],
        filament_candidates: [],
      };
    }

    setConfig(config) {
      this._config = config;
      this._modelRef = config.model_ref || "";
      // model_entity points to input_text.model_catalog_sidecar_base_url or similar
      this._modelEntity = config.model_entity || "input_text.model_catalog_sidecar_base_url";
    }

    set hass(hass) {
      this._hass = hass;
      this._update();
    }

    async _update() {
      if (!this._hass || !this._modelRef) {
        return;
      }

      // Get sidecar URL from entity
      if (this._modelEntity) {
        const entity = this._hass.states[this._modelEntity];
        if (entity) {
          this._modelSidecarUrl = entity.state;
        }
      }

      // Fetch model detail if not already loaded
      if (!this._modelDetail && this._modelSidecarUrl) {
        await this._loadModelDetail();
      }

      // Probe worker status
      if (this._modelSidecarUrl) {
        await this._probeWorkerStatus();
      }

      this._render();
    }

    async _loadModelDetail() {
      try {
        this._loading = true;
        const url = `${this._modelSidecarUrl}/api/local/models/${this._modelRef}`;
        const response = await fetch(url);
        if (response.ok) {
          this._modelDetail = await response.json();
        } else {
          this._error = `Failed to load model: ${response.status} ${response.statusText}`;
        }
      } catch (error) {
        this._error = `Error loading model: ${error.message}`;
      } finally {
        this._loading = false;
      }
    }

    async _probeWorkerStatus() {
      try {
        const url = `${this._modelSidecarUrl}/api/slicer/providers`;
        const response = await fetch(url);
        if (response.ok) {
          const data = await response.json();
          // Aggregate reachability across providers
          const providers = data.providers || [];
          const reachable = providers.length > 0 && providers.some((p) => p.reachable === true);
          this._workerStatus = {
            reachable,
            providers,
            error: null,
          };
        } else {
          this._workerStatus = {
            reachable: false,
            providers: [],
            error: `Probe failed: ${response.status}`,
          };
        }
      } catch (error) {
        this._workerStatus = {
          reachable: false,
          providers: [],
          error: `Network error: ${error.message}`,
        };
      }
    }

    async _handleStartSlicing() {
      if (!this._workerStatus || !this._workerStatus.reachable) {
        this._error = "Slicer worker is not available. Please check configuration and try again.";
        this._render();
        return;
      }

      // Transition to next step (validation review)
      this._currentStep = "validation";
      this._render();
    }

    _handleCancel() {
      this._currentStep = "entry-point";
      this._jobData = {
        model_ref: "",
        job_id: null,
        status: null,
        archive_id: null,
        created_archive_id: null,
        result_summary: null,
      };
      this._wizardState = {
        printer_id: null,
        plate_index: 0,
        patch_metadata: {},
        historical_timestamp: null,
        review_warnings: [],
        filament_candidates: [],
      };
      this._error = "";
      this._render();
    }

    _renderEntryPoint() {
      const workerHealthy = this._workerStatus && this._workerStatus.reachable;
      const model = this._modelDetail;

      return `
        <div class="wizard-container">
          <div class="wizard-header">
            <h2>Create Archive From Source</h2>
            <p class="wizard-subtitle">Slice and commit a 3MF source file to Bambuddy</p>
          </div>

          <div class="wizard-content">
            ${model ? `
              <div class="model-summary">
                <div class="model-name">${this._escapeHtml(model.display_name || model.model_id)}</div>
                <div class="model-meta">
                  <span>${model.category || "Uncategorized"}</span>
                  ${model.primary_file ? `<span>${this._basename(model.primary_file)}</span>` : ""}
                </div>
              </div>
            ` : ""}

            <div class="worker-status-panel ${workerHealthy ? "healthy" : "unhealthy"}">
              <div class="status-icon">${workerHealthy ? "✓" : "⚠"}</div>
              <div class="status-text">
                <div class="status-title">
                  ${workerHealthy ? "Slicer Worker Ready" : "Slicer Worker Unavailable"}
                </div>
                <div class="status-detail">
                  ${workerHealthy
                    ? "The local slicer is ready to process your 3MF file."
                    : "The slicer worker is not reachable. Check configuration and network connectivity."}
                </div>
              </div>
            </div>

            ${!workerHealthy && this._workerStatus.error ? `
              <div class="error-detail">
                <strong>Error:</strong> ${this._escapeHtml(this._workerStatus.error)}
              </div>
            ` : ""}

            ${workerHealthy && this._workerStatus.providers ? `
              <div class="provider-details">
                <div class="provider-title">Provider Capabilities:</div>
                ${this._workerStatus.providers.map((p) => `
                  <div class="provider-item">
                    <div class="provider-name">${this._escapeHtml(p.id || "Unknown")}</div>
                    <div class="provider-version">${this._escapeHtml(p.version_hint || "—")}</div>
                  </div>
                `).join("")}
              </div>
            ` : ""}

            ${this._error ? `
              <div class="error-banner">
                <strong>Error:</strong> ${this._escapeHtml(this._error)}
              </div>
            ` : ""}
          </div>

          <div class="wizard-footer">
            <button class="btn btn-secondary" @click="${() => this._handleCancel()}">Cancel</button>
            <button 
              class="btn btn-primary" 
              ?disabled="${!workerHealthy || this._loading}"
              @click="${() => this._handleStartSlicing()}"
            >
              ${this._loading ? "Loading..." : "Begin Slicing"}
            </button>
          </div>
        </div>
      `;
    }

    _renderUnavailable() {
      return `
        <div class="wizard-container unavailable-state">
          <div class="unavailable-icon">⚠</div>
          <h2>Slicer Worker Unavailable</h2>
          <p>
            The local slicer worker is not reachable. Please verify:
          </p>
          <ul>
            <li>The slicer worker container is running</li>
            <li>Network connectivity from Home Assistant to the worker</li>
            <li>Sidecar configuration is correct</li>
          </ul>
          ${this._workerStatus && this._workerStatus.error ? `
            <div class="error-detail">
              <strong>Details:</strong> ${this._escapeHtml(this._workerStatus.error)}
            </div>
          ` : ""}
          <div class="wizard-footer">
            <button class="btn btn-secondary" @click="${() => this._handleCancel()}">Close</button>
          </div>
        </div>
      `;
    }

    _render() {
      const workerHealthy = this._workerStatus && this._workerStatus.reachable;

      let content = "";
      if (this._currentStep === "entry-point") {
        if (!workerHealthy) {
          content = this._renderUnavailable();
        } else {
          content = this._renderEntryPoint();
        }
      } else if (this._currentStep === "validation") {
        // Slice 6.2+
        content = `<div class="placeholder">Validation review step (6.2+)</div>`;
      } else if (this._currentStep === "filament") {
        // Slice 6.3+
        content = `<div class="placeholder">Filament substitution step (6.3+)</div>`;
      } else if (this._currentStep === "timestamp") {
        // Slice 6.4+
        content = `<div class="placeholder">Timestamp review step (6.4+)</div>`;
      } else if (this._currentStep === "progress") {
        // Slice 6.5+
        content = `<div class="placeholder">Progress monitoring step (6.5+)</div>`;
      } else if (this._currentStep === "completion") {
        // Slice 6.6+
        content = `<div class="placeholder">Completion summary step (6.6+)</div>`;
      }

      this.shadowRoot.innerHTML = `
        <style>
          :host {
            --primary-color: #1976d2;
            --danger-color: #d32f2f;
            --success-color: #388e3c;
            --warning-color: #f57c00;
            --text-primary: #212121;
            --text-secondary: #757575;
            --bg-primary: #ffffff;
            --border-color: #e0e0e0;
            --shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
          }

          * {
            box-sizing: border-box;
          }

          .wizard-container {
            display: flex;
            flex-direction: column;
            height: 100%;
            min-height: 400px;
            background: var(--bg-primary);
            border-radius: 8px;
            overflow: auto;
          }

          .wizard-header {
            padding: 24px;
            border-bottom: 1px solid var(--border-color);
            background: linear-gradient(135deg, var(--primary-color), var(--primary-color) 80%);
            color: white;
          }

          .wizard-header h2 {
            margin: 0 0 8px 0;
            font-size: 20px;
            font-weight: 600;
          }

          .wizard-subtitle {
            margin: 0;
            font-size: 14px;
            opacity: 0.9;
          }

          .wizard-content {
            flex: 1;
            padding: 24px;
            overflow-y: auto;
          }

          .wizard-footer {
            display: flex;
            gap: 12px;
            justify-content: flex-end;
            padding: 16px 24px;
            border-top: 1px solid var(--border-color);
            background: #f5f5f5;
          }

          .model-summary {
            background: #f9f9f9;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 16px;
          }

          .model-name {
            font-weight: 600;
            font-size: 16px;
            color: var(--text-primary);
            margin-bottom: 4px;
          }

          .model-meta {
            display: flex;
            gap: 8px;
            font-size: 12px;
            color: var(--text-secondary);
          }

          .model-meta span {
            padding: 2px 6px;
            background: rgba(0, 0, 0, 0.05);
            border-radius: 3px;
          }

          .worker-status-panel {
            display: flex;
            gap: 12px;
            padding: 16px;
            border-radius: 6px;
            margin-bottom: 16px;
            align-items: flex-start;
          }

          .worker-status-panel.healthy {
            background: #e8f5e9;
            border: 1px solid #4caf50;
          }

          .worker-status-panel.unhealthy {
            background: #fff3e0;
            border: 1px solid #ff9800;
          }

          .status-icon {
            font-size: 24px;
            flex-shrink: 0;
          }

          .worker-status-panel.healthy .status-icon {
            color: var(--success-color);
          }

          .worker-status-panel.unhealthy .status-icon {
            color: var(--warning-color);
          }

          .status-text {
            flex: 1;
          }

          .status-title {
            font-weight: 600;
            font-size: 14px;
            margin-bottom: 4px;
          }

          .status-detail {
            font-size: 13px;
            color: var(--text-secondary);
          }

          .provider-details {
            background: #f9f9f9;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 12px;
            margin-top: 12px;
          }

          .provider-title {
            font-weight: 600;
            font-size: 13px;
            margin-bottom: 8px;
          }

          .provider-item {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            padding: 4px 0;
          }

          .provider-name {
            color: var(--text-primary);
          }

          .provider-version {
            color: var(--text-secondary);
          }

          .error-banner {
            background: #ffebee;
            border: 1px solid #ef5350;
            border-radius: 6px;
            padding: 12px;
            margin: 16px 0;
            color: #c62828;
            font-size: 13px;
          }

          .error-detail {
            background: #fff3e0;
            border-left: 4px solid var(--warning-color);
            padding: 12px;
            margin: 12px 0;
            font-size: 12px;
            color: var(--text-primary);
          }

          .unavailable-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
          }

          .unavailable-icon {
            font-size: 64px;
            margin-bottom: 16px;
            opacity: 0.5;
          }

          .unavailable-state h2 {
            color: var(--text-primary);
            margin: 0 0 12px 0;
          }

          .unavailable-state p {
            color: var(--text-secondary);
            margin: 0 0 16px 0;
            max-width: 400px;
          }

          .unavailable-state ul {
            text-align: left;
            display: inline-block;
            color: var(--text-secondary);
            font-size: 13px;
            margin: 0 0 16px 0;
            padding-left: 20px;
          }

          .unavailable-state li {
            margin: 4px 0;
          }

          .placeholder {
            padding: 40px;
            text-align: center;
            color: var(--text-secondary);
            font-style: italic;
          }

          .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
          }

          .btn:hover:not(:disabled) {
            opacity: 0.9;
          }

          .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
          }

          .btn-primary {
            background: var(--primary-color);
            color: white;
          }

          .btn-secondary {
            background: var(--text-secondary);
            color: white;
          }
        </style>
        ${content}
      `;

      // Re-attach event listeners
      this._attachEventListeners();
    }

    _attachEventListeners() {
      const buttons = this.shadowRoot.querySelectorAll("button");
      buttons.forEach((btn) => {
        const clickHandler = btn.getAttribute("@click");
        if (clickHandler) {
          // Parse and execute the click handler
          // This is a simplified approach; a real implementation might use a templating library
          if (clickHandler.includes("_handleCancel")) {
            btn.addEventListener("click", () => this._handleCancel());
          } else if (clickHandler.includes("_handleStartSlicing")) {
            btn.addEventListener("click", () => this._handleStartSlicing());
          }
        }
      });
    }

    _basename(path) {
      if (!path) return "";
      const normalized = String(path).replace(/\\/g, "/");
      const parts = normalized.split("/");
      return parts[parts.length - 1] || normalized;
    }

    _escapeHtml(value) {
      return String(value == null ? "" : value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }
  }

  // Register the custom element
  customElements.define("slicer-wizard-card", SlicerWizardCard);

  // Also make it available as a window property for debugging
  window.SlicerWizardCard = SlicerWizardCard;
})();
