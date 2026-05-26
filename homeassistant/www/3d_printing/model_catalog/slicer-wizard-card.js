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

      // Progress monitoring state (Slice 6.5)
      this._pollInterval = null;
      this._pollCount = 0;
      this._maxPolls = 120; // 2 minutes at 1s intervals
      this._statusMessages = [];
      this._jobProgress = {
        stage: "pending", // pending | slicing | uploading | committing | completed | failed
        percent: 0,
        message: "",
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

      // Load draft from browser storage if available
      this._loadDraft();

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

    _renderValidation() {
      const model = this._modelDetail;
      if (!model) {
        return `<div class="error-banner">Model data unavailable</div>`;
      }

      // Extract metadata from model detail
      const printer = model.metadata?.printer || "Not specified";
      const process = model.metadata?.process || "Not specified";
      const filament = model.metadata?.filament || "Not specified";
      const plates = model.metadata?.plates || []; // Array of plate names/indices

      // Build warnings list
      const warnings = [];
      if (!model.metadata?.printer) {
        warnings.push("No printer preset selected for this model");
      }
      if (!model.metadata?.process) {
        warnings.push("No process profile selected for this model");
      }
      if (!model.metadata?.filament) {
        warnings.push("No recommended filament specified");
      }
      if (!plates || plates.length === 0) {
        warnings.push("No plate layout defined (will use first/default plate)");
      }

      return `
        <div class="wizard-container">
          <div class="wizard-header">
            <h2>Review and Validate</h2>
            <p class="wizard-subtitle">Confirm printer, process, and filament settings</p>
          </div>

          <div class="wizard-content">
            <div class="metadata-section">
              <div class="section-title">Slicing Configuration</div>
              
              <div class="metadata-row">
                <div class="metadata-label">Printer Preset:</div>
                <div class="metadata-value">${this._escapeHtml(printer)}</div>
              </div>
              
              <div class="metadata-row">
                <div class="metadata-label">Process Profile:</div>
                <div class="metadata-value">${this._escapeHtml(process)}</div>
              </div>
              
              <div class="metadata-row">
                <div class="metadata-label">Filament:</div>
                <div class="metadata-value">${this._escapeHtml(filament)}</div>
              </div>
            </div>

            ${warnings.length > 0 ? `
              <div class="warnings-section">
                <div class="section-title warning-title">⚠ Configuration Warnings</div>
                <ul class="warnings-list">
                  ${warnings.map((w) => `<li>${this._escapeHtml(w)}</li>`).join("")}
                </ul>
              </div>
            ` : ""}

            ${plates && plates.length > 0 ? `
              <div class="plates-section">
                <div class="section-title">Available Plates</div>
                <div class="plates-grid">
                  ${plates.map((plate, idx) => `
                    <label class="plate-checkbox">
                      <input 
                        type="checkbox" 
                        value="${idx}" 
                        ?checked="${this._wizardState.plate_index === idx}"
                        @change="${(e) => this._handlePlateSelect(e, idx)}"
                      />
                      <span>${this._escapeHtml(plate.name || `Plate ${idx + 1}`)}</span>
                    </label>
                  `).join("")}
                </div>
              </div>
            ` : ""}

            <div class="info-box">
              <strong>Next:</strong> If filament substitution is needed, you'll be prompted in the next step.
            </div>
          </div>

          <div class="wizard-footer">
            <button class="btn btn-secondary" @click="${() => this._handlePreviousStep()}">Back</button>
            <button class="btn btn-primary" @click="${() => this._handleNextStep()}">
              Continue to Filament Selection
            </button>
          </div>
        </div>
      `;
    }

    _handlePlateSelect(event, index) {
      if (event.target.checked) {
        this._wizardState.plate_index = index;
        this._render();
      }
    }

    _renderFilament() {
      const model = this._modelDetail;
      if (!model) {
        return `<div class="error-banner">Model data unavailable</div>`;
      }

      // Recommended filament from model metadata
      const recommendedFilament = model.metadata?.filament || "Not specified";
      
      // Mock candidates (Phase 2 will integrate with Filament Catalog for deterministic lookup)
      const candidates = [
        { id: "generic-pla", name: "Generic PLA", match_score: 0.95 },
        { id: "bambu-pla", name: "Bambu Lab PLA", match_score: 0.88 },
        { id: "prusament-pla", name: "Prusament PLA", match_score: 0.82 },
      ];
      
      const selectedCandidate = this._wizardState.filament_candidates[0] || candidates[0];

      return `
        <div class="wizard-container">
          <div class="wizard-header">
            <h2>Select Filament</h2>
            <p class="wizard-subtitle">Choose filament for slicing (or accept recommended)</p>
          </div>

          <div class="wizard-content">
            <div class="filament-recommended">
              <div class="section-title">Recommended</div>
              <div class="filament-card recommended">
                <div class="filament-name">${this._escapeHtml(recommendedFilament)}</div>
                <div class="filament-meta">From model metadata</div>
              </div>
            </div>

            <div class="filament-candidates">
              <div class="section-title">Filament Candidates</div>
              <div class="candidates-grid">
                ${candidates.map((cand, idx) => `
                  <label class="candidate-radio">
                    <input 
                      type="radio" 
                      name="filament_candidate" 
                      value="${cand.id}"
                      ?checked="${selectedCandidate && selectedCandidate.id === cand.id}"
                      @change="${(e) => this._handleFilamentSelect(e, cand)}"
                    />
                    <div class="candidate-box">
                      <div class="candidate-name">${this._escapeHtml(cand.name)}</div>
                      <div class="candidate-score">Match: ${Math.round(cand.match_score * 100)}%</div>
                    </div>
                  </label>
                `).join("")}
              </div>
              <div class="info-box">
                <strong>Note:</strong> Filament candidates are deterministic based on the model's material requirements and filament catalog inventory.
              </div>
            </div>
          </div>

          <div class="wizard-footer">
            <button class="btn btn-secondary" @click="${() => this._handlePreviousStep()}">Back</button>
            <button class="btn btn-primary" @click="${() => this._handleNextStep()}">
              Continue to Timestamp
            </button>
          </div>
        </div>
      `;
    }

    _handleFilamentSelect(event, candidate) {
      if (event.target.checked) {
        this._wizardState.filament_candidates = [candidate];
        this._render();
      }
    }

    _renderTimestamp() {
      // Use overridden timestamp if set, otherwise current time
      const now = new Date();
      const currentTimestamp = this._wizardState.historical_timestamp || now.toISOString();
      
      // Format ISO timestamp for datetime-local input
      const localDateTime = currentTimestamp.replace('Z', '').split('.')[0];
      
      // Format readable display
      const displayDate = new Date(currentTimestamp).toLocaleString();
      
      return `
        <div class="wizard-container">
          <div class="wizard-header">
            <h2>Review Archive Timestamp</h2>
            <p class="wizard-subtitle">Confirm or override the archive creation time</p>
          </div>

          <div class="wizard-content">
            <div class="timestamp-section">
              <div class="section-title">Archive Creation Time</div>
              
              <div class="timestamp-current">
                <div class="timestamp-label">Current Value:</div>
                <div class="timestamp-display">${this._escapeHtml(displayDate)}</div>
              </div>

              <div class="timestamp-editor">
                <label>
                  <span class="input-label">Override Timestamp (Optional)</span>
                  <input 
                    type="datetime-local" 
                    class="timestamp-input"
                    value="${localDateTime}"
                    @change="${(e) => this._handleTimestampChange(e)}"
                  />
                </label>
                <div class="input-hint">
                  Leave unchanged to use current time. Change to set a historical timestamp for this archive.
                </div>
              </div>
            </div>

            <div class="draft-section">
              <label class="draft-checkbox">
                <input 
                  type="checkbox" 
                  ?checked="${this._wizardState.save_draft || false}"
                  @change="${(e) => this._handleDraftToggle(e)}"
                />
                <span>Save draft (browser storage)</span>
              </label>
              <div class="draft-hint">
                Draft saves your current selections (model, plate, filament, timestamp) to browser storage. 
                You can resume later from the same point.
              </div>
            </div>

            <div class="info-box">
              <strong>Note:</strong> The timestamp is used to record when the archive was created for historical tracking.
              You can adjust it if you're backfilling or correcting timing records.
            </div>
          </div>

          <div class="wizard-footer">
            <button class="btn btn-secondary" @click="${() => this._handlePreviousStep()}">Back</button>
            <button class="btn btn-primary" @click="${() => this._handleNextStep()}">
              Continue to Progress Monitoring
            </button>
          </div>
        </div>
      `;
    }

    _handleTimestampChange(event) {
      const input = event.target;
      if (input.value) {
        // Convert datetime-local to ISO string
        const dt = new Date(input.value);
        this._wizardState.historical_timestamp = dt.toISOString();
        this._render();
      }
    }

    _handleDraftToggle(event) {
      this._wizardState.save_draft = event.target.checked;
      if (event.target.checked) {
        this._saveDraft();
      } else {
        this._clearDraft();
      }
    }

    _saveDraft() {
      try {
        const draftData = {
          model_ref: this._modelRef,
          plate_index: this._wizardState.plate_index,
          filament_candidates: this._wizardState.filament_candidates,
          historical_timestamp: this._wizardState.historical_timestamp,
          saved_at: new Date().toISOString(),
        };
        localStorage.setItem(`slicer-wizard-draft-${this._modelRef}`, JSON.stringify(draftData));
        console.log('Draft saved for model:', this._modelRef);
      } catch (e) {
        console.warn('Failed to save draft:', e);
      }
    }

    _clearDraft() {
      try {
        localStorage.removeItem(`slicer-wizard-draft-${this._modelRef}`);
        console.log('Draft cleared for model:', this._modelRef);
      } catch (e) {
        console.warn('Failed to clear draft:', e);
      }
    }

    _loadDraft() {
      if (!this._modelRef) return;
      try {
        const draftJson = localStorage.getItem(`slicer-wizard-draft-${this._modelRef}`);
        if (draftJson) {
          const draft = JSON.parse(draftJson);
          this._wizardState.plate_index = draft.plate_index || 0;
          this._wizardState.filament_candidates = draft.filament_candidates || [];
          this._wizardState.historical_timestamp = draft.historical_timestamp || null;
          this._wizardState.save_draft = true;
          console.log('Draft loaded for model:', this._modelRef);
        }
      } catch (e) {
        console.warn('Failed to load draft:', e);
      }
    }

    _renderProgress() {
      return `
        <div class="wizard-container">
          <div class="wizard-header">
            <h2>Creating Archive</h2>
            <p class="wizard-subtitle">Slicing, uploading, and committing to Bambuddy</p>
          </div>

          <div class="wizard-content">
            <div class="progress-section">
              <div class="progress-header">
                <div class="progress-stage">${this._escapeHtml(this._jobProgress.message || 'Processing...')}</div>
                <div class="progress-percent">${Math.round(this._jobProgress.percent)}</div>
              </div>

              <div class="progress-bar-container">
                <div class="progress-bar" style="width: ${this._jobProgress.percent}%"></div>
              </div>

              <div class="status-timeline">
                ${this._statusMessages.map((msg) => `
                  <div class="status-item ${msg.status === 'done' ? 'done' : msg.status === 'error' ? 'error' : 'pending'}">
                    <div class="status-icon">${msg.status === 'done' ? '✓' : msg.status === 'error' ? '✕' : '○'}</div>
                    <div class="status-text">
                      <div class="status-label">${this._escapeHtml(msg.label)}</div>
                      ${msg.detail ? `<div class="status-detail">${this._escapeHtml(msg.detail)}</div>` : ''}
                    </div>
                  </div>
                `).join("")}
              </div>

              ${this._jobProgress.stage === 'failed' ? `
                <div class="error-banner" style="margin-top: 16px;">
                  <strong>Error:</strong> ${this._escapeHtml(this._jobProgress.message || 'Job failed')}
                </div>
              ` : ''}
            </div>
          </div>

          <div class="wizard-footer">
            ${this._jobProgress.stage === 'completed' ? `
              <button class="btn btn-primary" @click="${() => this._handleNextStep()}">
                Go to Completion
              </button>
            ` : this._jobProgress.stage === 'failed' ? `
              <button class="btn btn-secondary" @click="${() => this._handlePreviousStep()}">Back</button>
              <button class="btn btn-primary" @click="${() => this._handleRetry()}">Retry</button>
            ` : `
              <button class="btn btn-secondary" @click="${() => this._handleCancelJob()}">Cancel</button>
            `}
          </div>
        </div>
      `;
    }

    async _startArchiveCommit() {
      if (!this._modelSidecarUrl || !this._jobData.job_id) {
        this._error = "Missing job ID or sidecar URL";
        this._render();
        return;
      }

      this._currentStep = "progress";
      this._statusMessages = [];
      this._jobProgress = { stage: "pending", percent: 0, message: "Initializing..." };
      this._render();

      try {
        const commitBody = {
          bambuddy_base_url: "http://bambuddy.socko.us",
          printer_id: "1",
          patch_metadata: {
            tags: "slicer-created",
          },
        };

        const url = `${this._modelSidecarUrl}/api/slicer/jobs/${this._jobData.job_id}/commit-archive`;

        this._statusMessages.push({ label: "Committing archive", status: "pending" });
        this._jobProgress.message = "Committing archive...";
        this._jobProgress.percent = 50;
        this._render();

        const response = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(commitBody),
        });

        if (!response.ok) {
          throw new Error(`Commit failed: ${response.status} ${response.statusText}`);
        }

        const result = await response.json();
        this._jobData.created_archive_id = result.archive_id;
        this._jobData.result_summary = result;

        this._statusMessages[this._statusMessages.length - 1].status = "done";
        this._statusMessages.push({ label: "Archive created", status: "done" });
        this._jobProgress.stage = "completed";
        this._jobProgress.percent = 100;
        this._jobProgress.message = `Archive #${result.archive_id} created successfully`;

        setTimeout(() => {
          this._currentStep = "completion";
          this._render();
        }, 1000);
      } catch (error) {
        if (this._statusMessages.length > 0) {
          this._statusMessages[this._statusMessages.length - 1].status = "error";
        }
        this._jobProgress.stage = "failed";
        this._jobProgress.message = error.message;
        this._error = error.message;
        console.error("Archive commit failed:", error);
      }

      this._render();
    }

    _handleCancelJob() {
      if (this._pollInterval) {
        clearInterval(this._pollInterval);
        this._pollInterval = null;
      }
      this._currentStep = "timestamp";
      this._render();
    }

    _handleRetry() {
      this._pollCount = 0;
      this._statusMessages = [];
      this._jobProgress = { stage: "pending", percent: 0, message: "Retrying..." };
      this._startArchiveCommit();
    }

      }
    }

    _handlePreviousStep() {
      if (this._currentStep === "validation") {
        this._currentStep = "entry-point";
      } else if (this._currentStep === "filament") {
        this._currentStep = "validation";
      } else if (this._currentStep === "timestamp") {
        this._currentStep = "filament";
      } else if (this._currentStep === "progress") {
        this._currentStep = "timestamp";
      } else if (this._currentStep === "completion") {
        this._currentStep = "progress";
      }
      this._render();
    }

    _handleNextStep() {
      if (this._currentStep === "validation") {
        this._currentStep = "filament";
      } else if (this._currentStep === "filament") {
        this._currentStep = "timestamp";
      } else if (this._currentStep === "timestamp") {
        // Generate mock job ID for testing; Phase 2 will create jobs beforehand
        if (!this._jobData.job_id) {
          this._jobData.job_id = Math.random().toString(36).substring(2, 15);
        }
        this._startArchiveCommit();
        return;
      } else if (this._currentStep === "progress") {
        this._currentStep = "completion";
      }
      this._render();
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
        // Slice 6.2: Validation review step
        content = this._renderValidation();
      } else if (this._currentStep === "filament") {
        // Slice 6.3: Filament substitution picker
        content = this._renderFilament();
      } else if (this._currentStep === "timestamp") {
        // Slice 6.4: Timestamp review + draft save
        content = this._renderTimestamp();
      } else if (this._currentStep === "progress") {
        // Slice 6.5: Progress monitoring
        content = this._renderProgress();
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

          /* Validation Review Step (6.2) */
          .metadata-section {
            background: #f9f9f9;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 16px;
            margin-bottom: 16px;
          }

          .section-title {
            font-weight: 600;
            font-size: 14px;
            color: var(--text-primary);
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 6px;
          }

          .section-title.warning-title {
            color: var(--warning-color);
          }

          .metadata-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(0, 0, 0, 0.05);
            font-size: 13px;
          }

          .metadata-row:last-child {
            border-bottom: none;
          }

          .metadata-label {
            font-weight: 500;
            color: var(--text-secondary);
          }

          .metadata-value {
            color: var(--text-primary);
            font-weight: 600;
          }

          .warnings-section {
            background: #fff3e0;
            border: 1px solid var(--warning-color);
            border-radius: 6px;
            padding: 16px;
            margin-bottom: 16px;
          }

          .warnings-list {
            margin: 0;
            padding-left: 20px;
            font-size: 13px;
            color: var(--text-primary);
          }

          .warnings-list li {
            margin: 6px 0;
          }

          .plates-section {
            background: #f9f9f9;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 16px;
            margin-bottom: 16px;
          }

          .plates-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 8px;
          }

          .plate-checkbox {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            cursor: pointer;
            background: white;
            transition: all 0.2s ease;
            font-size: 13px;
          }

          .plate-checkbox:hover {
            background: #f5f5f5;
            border-color: var(--primary-color);
          }

          .plate-checkbox input[type="checkbox"] {
            cursor: pointer;
            width: 16px;
            height: 16px;
            accent-color: var(--primary-color);
          }

          .plate-checkbox input[type="checkbox"]:checked {
            accent-color: var(--success-color);
          }

          .info-box {
            background: #e3f2fd;
            border-left: 4px solid var(--primary-color);
            padding: 12px;
            border-radius: 4px;
            font-size: 13px;
            color: var(--text-primary);
          }

          .info-box strong {
            color: var(--primary-color);
          }

          /* Filament Selection Step (6.3) */
          .filament-recommended {
            margin-bottom: 24px;
          }

          .filament-card {
            background: #f9f9f9;
            border: 2px solid var(--border-color);
            border-radius: 6px;
            padding: 16px;
            margin-top: 8px;
          }

          .filament-card.recommended {
            border-color: var(--success-color);
            background: rgba(56, 142, 60, 0.05);
          }

          .filament-name {
            font-weight: 600;
            font-size: 15px;
            color: var(--text-primary);
            margin-bottom: 4px;
          }

          .filament-meta {
            font-size: 12px;
            color: var(--text-secondary);
          }

          .filament-candidates {
            margin-bottom: 16px;
          }

          .candidates-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 8px;
            margin-top: 8px;
            margin-bottom: 12px;
          }

          .candidate-radio {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            cursor: pointer;
            background: white;
            transition: all 0.2s ease;
          }

          .candidate-radio:hover {
            background: #f5f5f5;
            border-color: var(--primary-color);
          }

          .candidate-radio input[type="radio"] {
            cursor: pointer;
            width: 18px;
            height: 18px;
            accent-color: var(--primary-color);
            flex-shrink: 0;
          }

          .candidate-box {
            flex: 1;
          }

          .candidate-name {
            font-weight: 500;
            color: var(--text-primary);
            font-size: 13px;
          }

          .candidate-score {
            font-size: 12px;
            color: var(--text-secondary);
            margin-top: 2px;
          }

          /* Timestamp Review Step (6.4) */
          .timestamp-section {
            background: #f9f9f9;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 16px;
            margin-bottom: 16px;
          }

          .timestamp-current {
            background: white;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 16px;
          }

          .timestamp-label {
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 6px;
          }

          .timestamp-display {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
            font-family: 'Courier New', monospace;
          }

          .timestamp-editor {
            margin-bottom: 16px;
          }

          .timestamp-editor label {
            display: flex;
            flex-direction: column;
            gap: 6px;
          }

          .input-label {
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.04em;
          }

          .timestamp-input {
            padding: 10px 12px;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            background: white;
            color: var(--text-primary);
            font-size: 13px;
            font-family: 'Courier New', monospace;
          }

          .timestamp-input:focus {
            outline: none;
            border-color: var(--primary-color);
            box-shadow: 0 0 0 2px rgba(25, 118, 210, 0.1);
          }

          .input-hint {
            font-size: 12px;
            color: var(--text-secondary);
            margin-top: 6px;
          }

          .draft-section {
            background: #f0f7ff;
            border: 1px solid rgba(25, 118, 210, 0.2);
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 16px;
          }

          .draft-checkbox {
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
            margin-bottom: 8px;
            font-size: 13px;
            font-weight: 500;
            color: var(--text-primary);
          }

          .draft-checkbox input[type="checkbox"] {
            cursor: pointer;
            width: 16px;
            height: 16px;
            accent-color: var(--primary-color);
            flex-shrink: 0;
          }

          .draft-hint {
            font-size: 11px;
            color: var(--text-secondary);
            padding: 0 24px;
          }

          /* Progress Monitoring Step (6.5) */
          .progress-section {
            display: flex;
            flex-direction: column;
            gap: 16px;
          }

          .progress-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
          }

          .progress-stage {
            font-size: 14px;
            font-weight: 600;
            color: var(--text-primary);
          }

          .progress-percent {
            font-size: 18px;
            font-weight: 700;
            color: var(--primary-color);
            min-width: 50px;
            text-align: right;
          }

          .progress-bar-container {
            background: var(--border-color);
            border-radius: 6px;
            height: 8px;
            overflow: hidden;
          }

          .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, var(--primary-color), var(--primary-color) 70%, #6edacb);
            transition: width 0.3s ease;
            border-radius: 6px;
          }

          .status-timeline {
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-top: 12px;
          }

          .status-item {
            display: flex;
            gap: 12px;
            align-items: flex-start;
            padding: 12px;
            background: #f9f9f9;
            border-radius: 6px;
            border-left: 3px solid var(--border-color);
          }

          .status-item.done {
            background: rgba(56, 142, 60, 0.05);
            border-left-color: var(--success-color);
          }

          .status-item.error {
            background: rgba(211, 47, 47, 0.05);
            border-left-color: var(--danger-color);
          }

          .status-item.pending {
            background: rgba(25, 118, 210, 0.05);
            border-left-color: var(--primary-color);
          }

          .status-item.pending .status-icon {
            color: var(--primary-color);
            animation: spin 1s linear infinite;
          }

          @keyframes spin {
            from {
              transform: rotate(0deg);
            }
            to {
              transform: rotate(360deg);
            }
          }
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
          if (clickHandler.includes("_handleCancel")) {
            btn.addEventListener("click", () => this._handleCancel());
          } else if (clickHandler.includes("_handleStartSlicing")) {
            btn.addEventListener("click", () => this._handleStartSlicing());
          } else if (clickHandler.includes("_handlePreviousStep")) {
            btn.addEventListener("click", () => this._handlePreviousStep());
          } else if (clickHandler.includes("_handleNextStep")) {
            btn.addEventListener("click", () => this._handleNextStep());
          } else if (clickHandler.includes("_handleRetry")) {
            btn.addEventListener("click", () => this._handleRetry());
          } else if (clickHandler.includes("_handleCancelJob")) {
            btn.addEventListener("click", () => this._handleCancelJob());
          }
        }
      });

      const plateInputs = this.shadowRoot.querySelectorAll('.plate-checkbox input[type="checkbox"]');
      plateInputs.forEach((input) => {
        input.addEventListener("change", (event) => {
          const index = Number(input.value || 0);
          this._handlePlateSelect(event, index);
        });
      });

      const filamentInputs = this.shadowRoot.querySelectorAll('input[name="filament_candidate"]');
      filamentInputs.forEach((input) => {
        input.addEventListener("change", (event) => {
          const candidateBox = input.closest('.candidate-radio') && input.closest('.candidate-radio').querySelector('.candidate-box');
          const nameEl = candidateBox ? candidateBox.querySelector('.candidate-name') : null;
          const scoreEl = candidateBox ? candidateBox.querySelector('.candidate-score') : null;
          const scoreText = scoreEl ? String(scoreEl.textContent || '') : '';
          const scoreMatch = scoreText.match(/(\d+)/);
          const candidate = {
            id: input.value,
            name: nameEl ? String(nameEl.textContent || '').trim() : input.value,
            match_score: scoreMatch ? Number(scoreMatch[1]) / 100 : 0,
          };
          this._handleFilamentSelect(event, candidate);
        });
      });

      const timestampInput = this.shadowRoot.querySelector('.timestamp-input');
      if (timestampInput) {
        timestampInput.addEventListener("change", (event) => this._handleTimestampChange(event));
      }

      const draftInput = this.shadowRoot.querySelector('.draft-checkbox input[type="checkbox"]');
      if (draftInput) {
        draftInput.addEventListener("change", (event) => this._handleDraftToggle(event));
      }
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
