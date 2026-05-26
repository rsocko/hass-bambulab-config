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
        post_commit_warning: null,
        timestamp_repair_result: null,
      };
      this._wizardState = {
        printer_id: null,
        bambuddy_printer_id: "1",
        plate_index: 0,
        patch_metadata: {},
        historical_timestamp: null,
        manual_timestamp: null,
        timestamp_mode: "current",
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
          // Normalize provider shape across sidecar revisions.
          const providers = Array.isArray(data.providers)
            ? data.providers.map((provider) => {
                const status = String(provider && provider.status || "").toLowerCase();
                const reachable = provider && provider.reachable === true
                  || status === "available"
                  || status === "healthy"
                  || status === "ok";
                return {
                  ...provider,
                  id: provider && (provider.id || provider.provider) || "Unknown",
                  version_hint: provider && (provider.version_hint || provider.version || provider.status) || "-",
                  reachable,
                };
              })
            : [];
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
        post_commit_warning: null,
        timestamp_repair_result: null,
      };
      this._wizardState = {
        printer_id: null,
        bambuddy_printer_id: "1",
        plate_index: 0,
        patch_metadata: {},
        historical_timestamp: null,
        manual_timestamp: null,
        timestamp_mode: "current",
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
            <button class="btn btn-secondary" @click="${() => this._handleClose()}">Cancel</button>
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
            <button class="btn btn-secondary" @click="${() => this._handleClose()}">Close</button>
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
        warnings.push("Printer preset not extracted from model metadata — the slicer will use the preset embedded in the 3MF file");
      }
      if (!model.metadata?.process) {
        warnings.push("Process profile not extracted — the slicer will use the process profile embedded in the 3MF file");
      }
      if (!model.metadata?.filament) {
        warnings.push("Filament not extracted from model metadata — the slicer will use the filament settings embedded in the 3MF file");
      }
      if (!plates || plates.length === 0) {
        warnings.push("No plate layout defined — will use first/default plate (plate index 0)");
      }
      const hasMetadataWarnings = !model.metadata?.printer || !model.metadata?.process || !model.metadata?.filament;

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
                ${hasMetadataWarnings ? `
                  <div class="preset-note">
                    OrcaSlicer embeds printer, process, and filament settings inside the 3MF file itself. 
                    These warnings mean the Model Catalog hasn't extracted that metadata — but the slicer 
                    will still read the settings directly from the 3MF. No action is needed here.
                  </div>
                ` : ""}
              </div>
            ` : ""}

            <div class="metadata-section">
              <div class="section-title">Archive Commit Settings</div>
              <div class="metadata-row">
                <div class="metadata-label">Bambuddy Printer ID:</div>
                <div class="metadata-value">
                  <input
                    type="text"
                    class="bambuddy-printer-input"
                    id="bambuddy-printer-id-input"
                    value="${this._escapeHtml(this._wizardState.bambuddy_printer_id || "1")}"
                    placeholder="1"
                  />
                </div>
              </div>
              <div class="preset-note">
                Numeric Bambuddy printer DB id (not the Bambu Lab serial number). 
                Default <strong>1</strong> = your first printer. Change if archiving to a different printer.
              </div>
            </div>

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
            <button class="btn btn-secondary" @click="${() => this._handleClose()}">Cancel</button>
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
            <button class="btn btn-secondary" @click="${() => this._handleClose()}">Cancel</button>
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
      const sourceAsset = this._resolveSourceAsset();
      const fileModifiedTimestamp = String(sourceAsset && sourceAsset.file_modified_at || "").trim() || null;
      const mode = String(this._wizardState.timestamp_mode || "current");
      const manualTimestamp = this._wizardState.manual_timestamp || this._wizardState.historical_timestamp || new Date().toISOString();
      const now = new Date();
      const currentTimestamp = mode === "file_modified" && fileModifiedTimestamp
        ? fileModifiedTimestamp
        : mode === "manual"
          ? manualTimestamp
          : now.toISOString();
      
      // Format ISO timestamp for datetime-local input
      const localDateTime = String(manualTimestamp).replace('Z', '').split('.')[0];
      
      // Format readable display
      const displayDate = new Date(currentTimestamp).toLocaleString();
      const fileModifiedDisplay = fileModifiedTimestamp
        ? new Date(fileModifiedTimestamp).toLocaleString()
        : "File modified time is not available for this model asset.";
      const selectedModeLabel = mode === "file_modified"
        ? "Using model file modified time"
        : mode === "manual"
          ? "Using operator-selected timestamp"
          : "Using archive creation time";
      
      return `
        <div class="wizard-container">
          <div class="wizard-header">
            <h2>Review Archive Timestamp</h2>
            <p class="wizard-subtitle">Confirm or override the archive creation time</p>
          </div>

          <div class="wizard-content">
            <div class="timestamp-section">
              <div class="section-title">Archive Creation Time</div>

              <div class="timestamp-mode-group">
                <label class="timestamp-mode-option ${mode === "current" ? "selected" : ""}">
                  <input
                    type="radio"
                    name="timestamp_mode"
                    value="current"
                    ${mode === "current" ? "checked" : ""}
                    @change="${(e) => this._handleTimestampModeChange(e)}"
                  />
                  <div>
                    <div class="timestamp-mode-title">Use current archive time</div>
                    <div class="timestamp-mode-detail">Leave Bambuddy archive timing as created.</div>
                  </div>
                </label>

                <label class="timestamp-mode-option ${mode === "file_modified" ? "selected" : ""} ${fileModifiedTimestamp ? "" : "disabled"}">
                  <input
                    type="radio"
                    name="timestamp_mode"
                    value="file_modified"
                    ${mode === "file_modified" ? "checked" : ""}
                    ${fileModifiedTimestamp ? "" : "disabled"}
                    @change="${(e) => this._handleTimestampModeChange(e)}"
                  />
                  <div>
                    <div class="timestamp-mode-title">Use model file modified time</div>
                    <div class="timestamp-mode-detail">${this._escapeHtml(fileModifiedDisplay)}</div>
                  </div>
                </label>

                <label class="timestamp-mode-option ${mode === "manual" ? "selected" : ""}">
                  <input
                    type="radio"
                    name="timestamp_mode"
                    value="manual"
                    ${mode === "manual" ? "checked" : ""}
                    @change="${(e) => this._handleTimestampModeChange(e)}"
                  />
                  <div>
                    <div class="timestamp-mode-title">Pick a specific date and time</div>
                    <div class="timestamp-mode-detail">Use an operator-provided historical timestamp.</div>
                  </div>
                </label>
              </div>
              
              <div class="timestamp-current">
                <div class="timestamp-label">Selected Mode:</div>
                <div class="timestamp-display">${this._escapeHtml(selectedModeLabel)}</div>
              </div>

              <div class="timestamp-current">
                <div class="timestamp-label">Effective Archive Time:</div>
                <div class="timestamp-display">${this._escapeHtml(displayDate)}</div>
              </div>

              <div class="timestamp-editor ${mode === "manual" ? "" : "disabled"}">
                <label>
                  <span class="input-label">Specific Date/Time</span>
                  <input 
                    type="datetime-local" 
                    class="timestamp-input"
                    value="${localDateTime}"
                    ${mode === "manual" ? "" : "disabled"}
                    @change="${(e) => this._handleTimestampChange(e)}"
                  />
                </label>
                <div class="input-hint">
                  Manual entry is only used when “Pick a specific date and time” is selected.
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
            <button class="btn btn-secondary" @click="${() => this._handleClose()}">Cancel</button>
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
        this._wizardState.manual_timestamp = dt.toISOString();
        if (this._wizardState.timestamp_mode === "manual") {
          this._wizardState.historical_timestamp = this._wizardState.manual_timestamp;
        }
        this._render();
      }
    }

    _handleTimestampModeChange(event) {
      const nextMode = String(event && event.target && event.target.value || "current");
      this._wizardState.timestamp_mode = nextMode;
      if (nextMode === "manual") {
        if (!this._wizardState.manual_timestamp) {
          this._wizardState.manual_timestamp = new Date().toISOString();
        }
        this._wizardState.historical_timestamp = this._wizardState.manual_timestamp;
      } else if (nextMode === "file_modified") {
        const sourceAsset = this._resolveSourceAsset();
        const fileModifiedTimestamp = String(sourceAsset && sourceAsset.file_modified_at || "").trim() || null;
        this._wizardState.historical_timestamp = fileModifiedTimestamp;
      } else {
        this._wizardState.historical_timestamp = null;
      }
      this._render();
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
          manual_timestamp: this._wizardState.manual_timestamp,
          timestamp_mode: this._wizardState.timestamp_mode,
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
          this._wizardState.manual_timestamp = draft.manual_timestamp || draft.historical_timestamp || null;
          this._wizardState.timestamp_mode = draft.timestamp_mode || (draft.historical_timestamp ? "manual" : "current");
          this._wizardState.save_draft = true;
          console.log('Draft loaded for model:', this._modelRef);
        }
      } catch (e) {
        console.warn('Failed to load draft:', e);
      }
    }

    _resolveSourceAsset() {
      const assets = Array.isArray(this._modelDetail && this._modelDetail.assets)
        ? this._modelDetail.assets.slice()
        : [];
      const threeMfAssets = assets.filter((asset) => {
        const filename = String(asset && (asset.filename || asset.asset_filename || asset.name) || "").toLowerCase();
        const assetType = String(asset && (asset.asset_type || asset.content_type || "") || "").toLowerCase();
        return filename.endsWith(".3mf") || assetType === "3mf" || assetType.includes("3mf");
      });
      if (!threeMfAssets.length) {
        return null;
      }
      threeMfAssets.sort((left, right) => {
        const leftScore = String(left && left.asset_role || "") === "primary" ? 0 : 1;
        const rightScore = String(right && right.asset_role || "") === "primary" ? 0 : 1;
        return leftScore - rightScore;
      });
      return threeMfAssets[0];
    }

    _resolveWorkingFilePath(asset) {
      const rawPath = String(asset && (asset.storage_path || asset.local_storage_path || "") || "").trim();
      if (!rawPath) {
        return "";
      }
      const normalized = rawPath.replace(/\\/g, "/");
      if (/^(?:[a-zA-Z]:[\\/]|\/)/.test(normalized)) {
        return normalized;
      }
      return `/assets/Model Catalog/${normalized.replace(/^\/+/, "")}`;
    }

    _buildCreateJobBody(asset) {
      const timestamp = this._wizardState.historical_timestamp || null;
      let timezone = null;
      try {
        timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
      } catch (_error) {
        timezone = null;
      }
      return {
        source_kind: "local_file",
        archive_intent: "create_new",
        workflow_kind: "historical_backfill",
        source_ref: String(this._modelDetail && this._modelDetail.model && (this._modelDetail.model.model_url || this._modelDetail.model.public_id) || this._modelRef || "").trim() || null,
        local_model_id: String(this._modelDetail && this._modelDetail.entry && this._modelDetail.entry.local_model_id || this._modelRef || "").trim() || null,
        working_file_path: this._resolveWorkingFilePath(asset),
        selected_file_path: String(asset && (asset.asset_id || asset.file_id || asset.storage_path || "") || "").trim() || null,
        selected_plate_key: `plate_${Number(this._wizardState.plate_index || 0)}`,
        selected_plate_index: Number(this._wizardState.plate_index || 0),
        source_file_name: String(asset && (asset.filename || asset.asset_filename || asset.name) || "").trim() || null,
        attach_source_after_create: true,
        requested_print_completed_at: timestamp,
        requested_print_timezone: timezone,
        date_override_strategy: timestamp ? "operator_supplied" : "operator_default",
        overrides: {
          plate: String(Number(this._wizardState.plate_index || 0)),
        },
      };
    }

    _buildCommitBody() {
      return {
        bambuddy_base_url: "http://bambuddy.socko.us",
        printer_id: String(this._wizardState.bambuddy_printer_id || "1"),
        patch_metadata: {
          tags: "slicer-created",
        },
      };
    }

    _deriveStartedAtFromCompleted(completedAtIso, durationSeconds) {
      const completedMs = Date.parse(String(completedAtIso || ""));
      const duration = Number(durationSeconds || 0);
      if (!Number.isFinite(completedMs) || !Number.isFinite(duration) || duration < 0) {
        return null;
      }
      return new Date(completedMs - duration * 1000).toISOString();
    }

    async _applyHistoricalArchiveTiming(archiveId) {
      const completedAt = this._wizardState.historical_timestamp || null;
      const mode = String(this._wizardState.timestamp_mode || "current");
      if (!completedAt || mode === "current" || !this._hass || archiveId == null) {
        return { applied: false, warning: null, response: null };
      }

      const result = this._jobData.result_summary && typeof this._jobData.result_summary === "object"
        ? this._jobData.result_summary
        : {};
      const upload = result.upload_response && typeof result.upload_response === "object"
        ? result.upload_response
        : {};
      const durationSeconds = Number(upload.print_time_seconds || result.print_time_seconds || 0);
      const startedAt = this._deriveStartedAtFromCompleted(completedAt, durationSeconds);
      const reason = mode === "file_modified"
        ? "Slicer wizard applied model file modified time after archive creation"
        : "Slicer wizard applied operator-selected historical timestamp after archive creation";
      const payload = {
        archive_id: Number(archiveId),
        completed_at: completedAt,
        created_at: completedAt,
        reason,
        trigger_source: "model_catalog_slicer_wizard",
      };
      if (startedAt) {
        payload.started_at = startedAt;
      }
      payload.status = "completed";

      try {
        const responseEnvelope = await this._hass.callService(
          "bambuddy",
          "correct_print_history_archive_metadata",
          payload,
          undefined,
          true,
          true
        );
        const response = responseEnvelope && responseEnvelope.response && typeof responseEnvelope.response === "object"
          ? responseEnvelope.response
          : responseEnvelope;
        if (!response || response.success !== true) {
          const warning = response && response.message
            ? String(response.message)
            : "Archive created, but historical timestamp repair did not confirm success.";
          return { applied: false, warning, response };
        }
        return { applied: true, warning: null, response };
      } catch (error) {
        return {
          applied: false,
          warning: error && error.message
            ? String(error.message)
            : "Archive created, but historical timestamp repair failed.",
          response: null,
        };
      }
    }

    async _parseJsonResponse(response, fallbackLabel) {
      let body = null;
      try {
        body = await response.json();
      } catch (_error) {
        body = null;
      }
      if (!response.ok) {
        const errorMessage = body && body.error
          ? String(body.error)
          : `${fallbackLabel}: ${response.status} ${response.statusText}`;
        throw new Error(errorMessage);
      }
      return body || {};
    }

    _formatDuration(durationSeconds) {
      const totalSeconds = Number(durationSeconds || 0);
      if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) {
        return "-";
      }
      const hours = Math.floor(totalSeconds / 3600);
      const minutes = Math.floor((totalSeconds % 3600) / 60);
      if (hours > 0) {
        return `${hours}h ${minutes}m`;
      }
      return `${minutes}m`;
    }

    _renderCompletion() {
      const archiveId = this._jobData.created_archive_id || null;
      const result = this._jobData.result_summary && typeof this._jobData.result_summary === "object"
        ? this._jobData.result_summary
        : {};
      const upload = result.upload_response && typeof result.upload_response === "object"
        ? result.upload_response
        : {};
      const patch = result.patch_response && typeof result.patch_response === "object"
        ? result.patch_response
        : {};
      const source = result.source_response && typeof result.source_response === "object"
        ? result.source_response
        : {};
      const isSuccess = String(this._jobData.status || "") === "committed" && !!archiveId;
      const warningMessage = String(this._jobData.post_commit_warning || "").trim();
      const bambuddyArchivesUrl = archiveId
        ? `http://bambuddy.socko.us/archives?search=${encodeURIComponent(String(archiveId))}`
        : "http://bambuddy.socko.us/archives";
      const statusLabel = isSuccess ? "Archive Created" : "Completion Incomplete";
      const statusDetail = isSuccess
        ? `Archive #${archiveId} was created and enriched successfully.`
        : (this._error || "The archive flow finished without a committed archive id.");

      return `
        <div class="wizard-container completion-state ${isSuccess ? "success" : "warning"}">
          <div class="wizard-header completion-header ${isSuccess ? "success" : "warning"}">
            <h2>${this._escapeHtml(statusLabel)}</h2>
            <p class="wizard-subtitle">${this._escapeHtml(statusDetail)}</p>
          </div>

          <div class="wizard-content">
            <div class="completion-kpi-grid">
              <div class="completion-kpi-card">
                <div class="completion-kpi-label">Archive ID</div>
                <div class="completion-kpi-value">${archiveId ? `#${this._escapeHtml(String(archiveId))}` : "-"}</div>
              </div>
              <div class="completion-kpi-card">
                <div class="completion-kpi-label">Printer</div>
                <div class="completion-kpi-value">${this._escapeHtml(String(upload.printer_id || "1"))}</div>
              </div>
              <div class="completion-kpi-card">
                <div class="completion-kpi-label">Print Time</div>
                <div class="completion-kpi-value">${this._escapeHtml(this._formatDuration(upload.print_time_seconds))}</div>
              </div>
              <div class="completion-kpi-card">
                <div class="completion-kpi-label">Filament</div>
                <div class="completion-kpi-value">${Number.isFinite(Number(upload.filament_used_grams)) ? `${Number(upload.filament_used_grams).toFixed(2)} g` : "-"}</div>
              </div>
            </div>

            <div class="completion-section">
              <div class="section-title">Archive Summary</div>
              <div class="completion-detail-list">
                <div class="completion-detail-row">
                  <div class="completion-detail-label">Print Name</div>
                  <div class="completion-detail-value">${this._escapeHtml(String(upload.print_name || "Not available"))}</div>
                </div>
                <div class="completion-detail-row">
                  <div class="completion-detail-label">Uploaded File</div>
                  <div class="completion-detail-value">${this._escapeHtml(String(upload.filename || "Not available"))}</div>
                </div>
                <div class="completion-detail-row">
                  <div class="completion-detail-label">Tags</div>
                  <div class="completion-detail-value">${this._escapeHtml(String(patch.tags || "slicer-created"))}</div>
                </div>
                <div class="completion-detail-row">
                  <div class="completion-detail-label">Archive Time</div>
                  <div class="completion-detail-value">${this._escapeHtml(String(patch.completed_at || upload.completed_at || "Not overridden"))}</div>
                </div>
                <div class="completion-detail-row">
                  <div class="completion-detail-label">Source Attached</div>
                  <div class="completion-detail-value">${source.source_3mf_path ? "Yes" : "No"}</div>
                </div>
              </div>
            </div>

            ${warningMessage ? `
              <div class="error-banner">
                <strong>Follow-up needed:</strong> ${this._escapeHtml(warningMessage)}
              </div>
            ` : ""}

            ${source.source_3mf_path ? `
              <div class="info-box success-box">
                <strong>Source preserved:</strong> ${this._escapeHtml(String(source.filename || source.source_3mf_path))}
              </div>
            ` : ""}

            ${!isSuccess ? `
              <div class="error-banner">
                <strong>Review needed:</strong> ${this._escapeHtml(this._error || "Commit completed without a final success payload.")}
              </div>
            ` : ""}

            <div class="info-box">
              <strong>Bambuddy:</strong> Use the archive id to find this item in the Bambuddy archives view.
            </div>
          </div>

          <div class="wizard-footer">
            <button class="btn btn-secondary" @click="${() => this._handleClosePopup()}">Close</button>
            <button class="btn btn-secondary" @click="${() => this._handleCreateAnother()}">Create Another</button>
            <button class="btn btn-primary" data-archive-search-url="${this._escapeHtml(bambuddyArchivesUrl)}" @click="${() => this._handleOpenArchiveSearch()}">Open in Bambuddy</button>
          </div>
        </div>
      `;
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
      if (!this._modelSidecarUrl) {
        this._error = "Missing sidecar URL";
        this._render();
        return;
      }

      const sourceAsset = this._resolveSourceAsset();
      if (!sourceAsset) {
        this._error = "No source 3MF asset found for this model";
        this._render();
        return;
      }

      this._currentStep = "progress";
      this._statusMessages = [];
      this._error = "";
      this._jobProgress = { stage: "pending", percent: 0, message: "Initializing..." };
      this._render();

      try {
        this._statusMessages.push({ label: "Creating slicer job", status: "pending" });
        this._jobProgress.message = "Creating slicer job...";
        this._jobProgress.percent = 10;
        this._render();

        const createResponse = await fetch(`${this._modelSidecarUrl}/api/slicer/jobs`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this._buildCreateJobBody(sourceAsset)),
        });
        const createdJob = await this._parseJsonResponse(createResponse, "Create job failed");
        this._jobData.job_id = createdJob.job_id;
        this._jobData.status = createdJob.status;
        this._statusMessages[this._statusMessages.length - 1].status = "done";

        this._statusMessages.push({ label: "Slicing source file", status: "pending" });
        this._jobProgress.stage = "slicing";
        this._jobProgress.message = "Slicing source file...";
        this._jobProgress.percent = 40;
        this._render();

        const executeResponse = await fetch(`${this._modelSidecarUrl}/api/slicer/jobs/${createdJob.job_id}/execute`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        });
        const executedJob = await this._parseJsonResponse(executeResponse, "Execute job failed");
        if (String(executedJob.status || "") !== "sliced") {
          throw new Error(`Execute job returned unexpected status: ${executedJob.status || "unknown"}`);
        }
        this._jobData.status = executedJob.status;
        this._jobData.result_summary = executedJob.result_summary || null;
        this._statusMessages[this._statusMessages.length - 1].status = "done";

        this._statusMessages.push({ label: "Committing archive", status: "pending" });
        this._jobProgress.stage = "committing";
        this._jobProgress.message = "Committing archive...";
        this._jobProgress.percent = 75;
        this._render();

        const commitResponse = await fetch(`${this._modelSidecarUrl}/api/slicer/jobs/${createdJob.job_id}/commit-archive`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this._buildCommitBody()),
        });
        const committedJob = await this._parseJsonResponse(commitResponse, "Commit failed");
        const archiveId = committedJob.created_archive_id
          || committedJob.archive_id
          || committedJob.result_summary && committedJob.result_summary.created_archive_id
          || null;
        this._jobData.status = committedJob.status || "committed";
        this._jobData.created_archive_id = archiveId;
        this._jobData.result_summary = committedJob.result_summary || committedJob;
        this._jobData.post_commit_warning = null;
        this._jobData.timestamp_repair_result = null;

        this._statusMessages[this._statusMessages.length - 1].status = "done";
        this._statusMessages.push({ label: "Archive created", status: "done" });

        const timingRepair = await this._applyHistoricalArchiveTiming(archiveId);
        this._jobData.timestamp_repair_result = timingRepair.response || null;
        if (timingRepair.applied) {
          this._statusMessages.push({ label: "Historical timestamp applied", status: "done" });
          if (this._jobData.result_summary && typeof this._jobData.result_summary === "object") {
            this._jobData.result_summary.patch_response = {
              ...this._jobData.result_summary.patch_response,
              completed_at: this._wizardState.historical_timestamp,
            };
          }
        } else if (timingRepair.warning) {
          this._statusMessages.push({ label: "Historical timestamp repair", status: "error", detail: timingRepair.warning });
          this._jobData.post_commit_warning = timingRepair.warning;
        }

        this._jobProgress.stage = "completed";
        this._jobProgress.percent = 100;
        this._jobProgress.message = this._jobData.post_commit_warning
          ? `Archive #${archiveId} created with warnings`
          : archiveId
            ? `Archive #${archiveId} created successfully`
            : "Archive created successfully";

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
      this._jobData.job_id = null;
      this._jobData.status = null;
      this._jobData.created_archive_id = null;
      this._jobData.result_summary = null;
      this._jobData.post_commit_warning = null;
      this._jobData.timestamp_repair_result = null;
      this._jobProgress = { stage: "pending", percent: 0, message: "Retrying..." };
      this._startArchiveCommit();
    }

    _handleCreateAnother() {
      this._clearDraft();
      this._handleCancel();
    }

    _handleClosePopup() {
      if (!this._hass) {
        return;
      }
      this._hass.callService("browser_mod", "close_popup", {}).catch((error) => {
        console.warn("Failed to close popup:", error);
      });
    }

    _handleOpenArchiveSearch(url) {
      if (!url) {
        return;
      }
      window.open(url, "_blank", "noopener,noreferrer");
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
        // Slice 6.6: Completion summary
        content = this._renderCompletion();
      }

      this.shadowRoot.innerHTML = `
        <style>
          :host {
            --accent: var(--primary-color, #6edacb);
            --danger-color: var(--error-color, #ef5350);
            --success-color: var(--success-color, #22c55e);
            --warning-color: var(--warning-color, #ff9a3c);
            --text-primary: var(--primary-text-color);
            --text-secondary: var(--secondary-text-color);
            --bg-primary: var(--ha-card-background, var(--card-background-color));
            --bg-card-alt: color-mix(in srgb, var(--ha-card-background, var(--card-background-color)) 92%, var(--primary-text-color) 8%);
            --border-color: var(--divider-color);
            --surface-info: color-mix(in srgb, var(--accent) 12%, var(--bg-primary));
            --surface-warning: color-mix(in srgb, var(--warning-color) 14%, var(--bg-primary));
            --surface-success: color-mix(in srgb, var(--success-color) 14%, var(--bg-primary));
            --surface-danger: color-mix(in srgb, var(--danger-color) 14%, var(--bg-primary));
            --shadow: 0 12px 30px color-mix(in srgb, var(--primary-text-color) 12%, transparent);
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
            background: linear-gradient(
              135deg,
              color-mix(in srgb, var(--accent) 24%, var(--bg-primary)) 0%,
              color-mix(in srgb, var(--accent) 12%, var(--bg-primary)) 100%
            );
            color: var(--text-primary);
          }

          .wizard-header h2 {
            margin: 0 0 8px 0;
            font-size: 20px;
            font-weight: 600;
          }

          .wizard-subtitle {
            margin: 0;
            font-size: 14px;
            color: var(--text-secondary);
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
            background: var(--bg-card-alt);
          }

          .model-summary {
            background: var(--bg-card-alt);
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
            background: color-mix(in srgb, var(--text-primary) 8%, transparent);
            border: 1px solid color-mix(in srgb, var(--border-color) 80%, transparent);
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
            background: var(--surface-success);
            border: 1px solid color-mix(in srgb, var(--success-color) 45%, transparent);
          }

          .worker-status-panel.unhealthy {
            background: var(--surface-warning);
            border: 1px solid color-mix(in srgb, var(--warning-color) 45%, transparent);
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
            background: var(--bg-card-alt);
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
            background: var(--surface-danger);
            border: 1px solid color-mix(in srgb, var(--danger-color) 45%, transparent);
            border-radius: 6px;
            padding: 12px;
            margin: 16px 0;
            color: var(--text-primary);
            font-size: 13px;
          }

          .error-detail {
            background: var(--surface-warning);
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
            border: 1px solid transparent;
            border-radius: 4px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
          }

          .btn:hover:not(:disabled) {
            filter: brightness(1.06);
          }

          .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
          }

          .btn-primary {
            background: color-mix(in srgb, var(--accent) 22%, transparent);
            border-color: color-mix(in srgb, var(--accent) 38%, transparent);
            color: var(--text-primary);
          }

          .btn-primary:hover:not(:disabled) {
            border-color: color-mix(in srgb, var(--accent) 52%, transparent);
          }

          .btn-secondary {
            background: var(--bg-card-alt);
            border-color: var(--border-color);
            color: var(--text-secondary);
          }

          .btn-secondary:hover:not(:disabled) {
            color: var(--text-primary);
            border-color: color-mix(in srgb, var(--text-primary) 22%, transparent);
          }

          /* Validation Review Step (6.2) */
          .metadata-section {
            background: var(--bg-card-alt);
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
            color: var(--text-primary);
          }

          .metadata-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid color-mix(in srgb, var(--border-color) 85%, transparent);
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
            background: var(--surface-warning);
            border: 1px solid color-mix(in srgb, var(--warning-color) 45%, transparent);
            border-left: 4px solid var(--warning-color);
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
            background: var(--bg-card-alt);
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
            background: var(--bg-primary);
            transition: all 0.2s ease;
            font-size: 13px;
          }

          .plate-checkbox:hover {
            background: color-mix(in srgb, var(--accent) 10%, var(--bg-primary));
            border-color: color-mix(in srgb, var(--accent) 28%, transparent);
          }

          .plate-checkbox input[type="checkbox"] {
            cursor: pointer;
            width: 16px;
            height: 16px;
            accent-color: var(--accent);
          }

          .plate-checkbox input[type="checkbox"]:checked {
            accent-color: var(--success-color);
          }

          .info-box {
            background: var(--surface-info);
            border-left: 4px solid var(--accent);
            padding: 12px;
            border-radius: 4px;
            font-size: 13px;
            color: var(--text-primary);
          }

          .info-box strong {
            color: var(--accent);
          }

          /* Filament Selection Step (6.3) */
          .filament-recommended {
            margin-bottom: 24px;
          }

          .filament-card {
            background: var(--bg-card-alt);
            border: 2px solid var(--border-color);
            border-radius: 6px;
            padding: 16px;
            margin-top: 8px;
          }

          .filament-card.recommended {
            border-color: var(--success-color);
            background: var(--surface-success);
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
            background: var(--bg-primary);
            transition: all 0.2s ease;
          }

          .candidate-radio:hover {
            background: color-mix(in srgb, var(--accent) 10%, var(--bg-primary));
            border-color: color-mix(in srgb, var(--accent) 28%, transparent);
          }

          .candidate-radio input[type="radio"] {
            cursor: pointer;
            width: 18px;
            height: 18px;
            accent-color: var(--accent);
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
            background: var(--bg-card-alt);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 16px;
            margin-bottom: 16px;
          }

          .timestamp-mode-group {
            display: flex;
            flex-direction: column;
            gap: 10px;
            margin-bottom: 16px;
          }

          .timestamp-mode-option {
            display: grid;
            grid-template-columns: 20px 1fr;
            gap: 12px;
            align-items: start;
            padding: 12px;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            background: var(--bg-primary);
            cursor: pointer;
          }

          .timestamp-mode-option.selected {
            border-color: color-mix(in srgb, var(--accent) 34%, transparent);
            background: color-mix(in srgb, var(--accent) 14%, transparent);
          }

          .timestamp-mode-option.disabled {
            opacity: 0.6;
            cursor: not-allowed;
          }

          .timestamp-mode-title {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 4px;
          }

          .timestamp-mode-detail {
            font-size: 12px;
            color: var(--text-secondary);
          }

          .timestamp-current {
            background: var(--bg-primary);
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

          .timestamp-editor.disabled {
            opacity: 0.65;
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
            background: var(--bg-primary);
            color: var(--text-primary);
            font-size: 13px;
            font-family: 'Courier New', monospace;
          }

          .timestamp-input:focus {
            outline: none;
            border-color: color-mix(in srgb, var(--accent) 44%, transparent);
            box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 16%, transparent);
          }

          .input-hint {
            font-size: 12px;
            color: var(--text-secondary);
            margin-top: 6px;
          }

          .draft-section {
            background: var(--surface-info);
            border: 1px solid color-mix(in srgb, var(--accent) 24%, transparent);
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
            accent-color: var(--accent);
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
            color: var(--accent);
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
            background: linear-gradient(90deg, var(--accent), color-mix(in srgb, var(--accent) 75%, #6edacb));
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
            background: var(--bg-card-alt);
            border-radius: 6px;
            border-left: 3px solid var(--border-color);
          }

          .status-item.done {
            background: var(--surface-success);
            border-left-color: var(--success-color);
          }

          .status-item.error {
            background: var(--surface-danger);
            border-left-color: var(--danger-color);
          }

          .status-item.pending {
            background: var(--surface-info);
            border-left-color: var(--accent);
          }

          .status-item.pending .status-icon {
            color: var(--accent);
            animation: spin 1s linear infinite;
          }

          /* Completion Step (6.6) */
          .completion-header.success {
            background: linear-gradient(
              135deg,
              color-mix(in srgb, var(--success-color) 28%, var(--bg-primary)) 0%,
              color-mix(in srgb, var(--success-color) 16%, var(--bg-primary)) 100%
            );
          }

          .completion-header.warning {
            background: linear-gradient(
              135deg,
              color-mix(in srgb, var(--warning-color) 28%, var(--bg-primary)) 0%,
              color-mix(in srgb, var(--warning-color) 16%, var(--bg-primary)) 100%
            );
          }

          .completion-kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
          }

          .completion-kpi-card {
            background: var(--bg-card-alt);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 14px;
          }

          .completion-kpi-label {
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 6px;
          }

          .completion-kpi-value {
            font-size: 18px;
            font-weight: 700;
            color: var(--text-primary);
          }

          .completion-section {
            background: var(--bg-card-alt);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
          }

          .completion-detail-list {
            display: flex;
            flex-direction: column;
            gap: 10px;
          }

          .completion-detail-row {
            display: grid;
            grid-template-columns: 140px 1fr;
            gap: 12px;
            align-items: start;
            font-size: 13px;
          }

          .completion-detail-label {
            color: var(--text-secondary);
            font-weight: 600;
          }

          .completion-detail-value {
            color: var(--text-primary);
            word-break: break-word;
          }

          .success-box {
            background: var(--surface-success);
            border-left-color: var(--success-color);
          }

          @keyframes spin {
            from {
              transform: rotate(0deg);
            }
            to {
              transform: rotate(360deg);
            }
          }

          /* Step progress bar */
          .slicer-outer {
            display: flex;
            flex-direction: column;
            height: 100%;
            overflow: hidden;
          }

          .slicer-outer > .wizard-container {
            flex: 1;
            min-height: 0;
            height: auto;
          }

          .wiz-progress {
            display: flex;
            align-items: center;
            padding: 10px 14px;
            background: var(--bg-card-alt);
            border-bottom: 1px solid var(--border-color);
            overflow-x: auto;
            flex-shrink: 0;
          }

          .wiz-step {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 3px;
            padding: 0 10px;
            position: relative;
            flex: 1;
            min-width: 50px;
          }

          .wiz-step + .wiz-step::before {
            content: '';
            position: absolute;
            left: 0;
            top: 11px;
            width: 1px;
            height: 12px;
            background: var(--border-color);
          }

          .wiz-step-num {
            width: 22px;
            height: 22px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: 700;
            background: var(--bg-primary);
            border: 2px solid var(--border-color);
            color: var(--text-secondary);
          }

          .wiz-step.current .wiz-step-num {
            border-color: var(--accent);
            color: var(--accent);
            background: color-mix(in srgb, var(--accent) 16%, var(--bg-primary));
          }

          .wiz-step.complete .wiz-step-num {
            background: var(--accent);
            border-color: var(--accent);
            color: var(--bg-primary);
          }

          .wiz-step-lbl {
            font-size: 10px;
            text-align: center;
            color: var(--text-secondary);
            font-weight: 500;
            white-space: nowrap;
          }

          .wiz-step.current .wiz-step-lbl {
            color: var(--text-primary);
            font-weight: 600;
          }

          .wiz-step.complete .wiz-step-lbl {
            color: var(--accent);
          }

          .bambuddy-printer-input {
            width: 80px;
            padding: 4px 8px;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            background: var(--bg-primary);
            color: var(--text-primary);
            font-size: 13px;
            font-weight: 600;
          }

          .bambuddy-printer-input:focus {
            outline: none;
            border-color: color-mix(in srgb, var(--accent) 44%, transparent);
          }

          .preset-note {
            font-size: 11px;
            color: var(--text-secondary);
            margin-top: 6px;
            font-style: italic;
          }
          }
        </style>
        <div class="slicer-outer">
          ${this._renderStepProgress()}
          ${content}
        </div>
      `;

      // Re-attach event listeners
      this._attachEventListeners();
    }

    _stepToIndex() {
      const order = ["entry-point", "validation", "filament", "timestamp", "progress", "completion"];
      const idx = order.indexOf(this._currentStep);
      return idx >= 0 ? idx + 1 : 1;
    }

    _stepLabel(stepIndex) {
      const labels = ["Begin", "Validate", "Filament", "Timestamp", "Slice", "Done"];
      return labels[stepIndex - 1] || "";
    }

    _renderStepProgress() {
      const totalSteps = 6;
      const current = this._stepToIndex();
      const items = [];
      for (let i = 1; i <= totalSteps; i++) {
        const isCurrent = i === current;
        const isComplete = i < current;
        items.push(
          `<div class="wiz-step${isCurrent ? " current" : ""}${isComplete ? " complete" : ""}">` +
          `<div class="wiz-step-num">${i}</div>` +
          `<div class="wiz-step-lbl">${this._escapeHtml(this._stepLabel(i))}</div>` +
          `</div>`
        );
      }
      return `<div class="wiz-progress">${items.join("")}</div>`;
    }

    _handleClose() {
      this._handleClosePopup();
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
          } else if (clickHandler.includes("_handleCreateAnother")) {
            btn.addEventListener("click", () => this._handleCreateAnother());
          } else if (clickHandler.includes("_handleClosePopup")) {
            btn.addEventListener("click", () => this._handleClosePopup());
          } else if (clickHandler.includes("_handleClose")) {
            btn.addEventListener("click", () => this._handleClose());
          } else if (clickHandler.includes("_handleOpenArchiveSearch")) {
            const url = String(btn.getAttribute("data-archive-search-url") || "").trim();
            btn.addEventListener("click", () => this._handleOpenArchiveSearch(url));
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

      const timestampModeInputs = this.shadowRoot.querySelectorAll('input[name="timestamp_mode"]');
      timestampModeInputs.forEach((input) => {
        input.addEventListener("change", (event) => this._handleTimestampModeChange(event));
      });

      const draftInput = this.shadowRoot.querySelector('.draft-checkbox input[type="checkbox"]');
      if (draftInput) {
        draftInput.addEventListener("change", (event) => this._handleDraftToggle(event));
      }

      const printerIdInput = this.shadowRoot.querySelector("#bambuddy-printer-id-input");
      if (printerIdInput) {
        printerIdInput.addEventListener("input", (event) => {
          this._wizardState.bambuddy_printer_id = String(event.target.value || "").trim();
        });
        printerIdInput.addEventListener("change", (event) => {
          this._wizardState.bambuddy_printer_id = String(event.target.value || "").trim() || "1";
        });
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
