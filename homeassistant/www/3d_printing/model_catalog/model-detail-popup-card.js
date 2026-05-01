/**
 * Model Detail Popup Card
 * 
 * Provides a comprehensive detail view and inline editing interface for models
 * from the Manyfold catalog directly in Home Assistant UI.
 * 
 * Phase 3.0 MVP - Detail View (Read-Only)
 * - Details tab with model metadata and enrichment
 * - Media Gallery tab for photos
 * - 3D Viewer action button that opens dedicated popup
 * - Linked Prints tab showing archives linked to this model
 * 
 * Usage in browser_mod popup:
 * ```
 * service: browser_mod.popup
 * data:
 *   title: Model Name
 *   size: wide
 *   content:
 *     type: custom:model-detail-popup-card
 *     model_ref: "gridfinity-bin"
 *     model_entity: "input_text.model_catalog_sidecar_base_url"
 * ```
 */

class ModelDetailPopupCard extends HTMLElement {
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
    this._isSaving = false;
    this._error = "";
    this._activeTab = "details";
    this._isEditMode = false;
    this._editAdvancedSectionOpen = false;
    this._lastModifiedTimestamp = null;
    this._conflictDialog = null;
    this._showConflictDialog = false;
    this._photoGallery = [];
    this._activePhotoIndex = null;
    
    // Render stability: prevent re-rendering during interactions
    this._isInteracting = false;
    this._renderScheduled = false;
    this._lastRenderedModelUrl = null;
    
    // Bound handlers
    this._boundClickHandler = this._handleClick.bind(this);
    this._boundChangeHandler = this._handleChange.bind(this);
    this._boundDragOverHandler = this._handleDragOver.bind(this);
    this._boundDragLeaveHandler = this._handleDragLeave.bind(this);
    this._boundDropHandler = this._handleDrop.bind(this);
  }

  setConfig(config) {
    this._config = config || {};
    this._modelRef = String(this._config.model_ref || "").trim();
    this._modelSidecarUrl = String(this._config.model_sidecar_url || "").trim();
    this._activeTab = "details";
    this._render();
  }

  set hass(hass) {
    this._hass = hass;

    this._modelSidecarUrl = this._resolveModelSidecarUrl();

    // Perform initial load if we haven't yet
    if (!this._modelDetail && !this._loading && !this._error && this._modelRef && this._modelSidecarUrl) {
      this._loadModelDetail();
    }

    // During edit mode, avoid re-rendering the popup on every HA state tick,
    // which can recreate the form and steal input focus.
    if (this._isEditMode) {
      const editForm = this.shadowRoot.querySelector('model-detail-edit-form');
      if (editForm) {
        editForm.hass = hass;
      }
      return;
    }

    // If we're currently interacting (clicking buttons, etc), defer render
    if (this._isInteracting) {
      this._renderScheduled = true;
      return;
    }

    // Only re-render if model data has changed
    const currentModelUrl = this._modelDetail?.manyfold_model_url || '';
    if (this._lastRenderedModelUrl === currentModelUrl) {
      // Model data hasn't changed, skip re-render
      return;
    }

    this._lastRenderedModelUrl = currentModelUrl;
    this._render();
  }

  connectedCallback() {
    this.shadowRoot.addEventListener("click", this._boundClickHandler);
    this.shadowRoot.addEventListener("change", this._boundChangeHandler);
    this.shadowRoot.addEventListener("dragover", this._boundDragOverHandler);
    this.shadowRoot.addEventListener("dragleave", this._boundDragLeaveHandler);
    this.shadowRoot.addEventListener("drop", this._boundDropHandler);
  }

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("click", this._boundClickHandler);
    this.shadowRoot.removeEventListener("change", this._boundChangeHandler);
    this.shadowRoot.removeEventListener("dragover", this._boundDragOverHandler);
    this.shadowRoot.removeEventListener("dragleave", this._boundDragLeaveHandler);
    this.shadowRoot.removeEventListener("drop", this._boundDropHandler);
  }

  _resolveModelSidecarUrl() {
    if (this._config && this._config.model_entity && this._hass && this._hass.states) {
      const configuredEntity = this._hass.states[this._config.model_entity];
      if (configuredEntity && configuredEntity.state) {
        return String(configuredEntity.state).trim();
      }
    }

    if (this._hass && this._hass.states) {
      const baseUrlEntity = this._hass.states["input_text.model_catalog_sidecar_base_url"];
      if (baseUrlEntity && baseUrlEntity.state) {
        return String(baseUrlEntity.state).trim();
      }
    }

    return String(this._config && this._config.model_sidecar_url || "").trim();
  }

  _handleClick(event) {
    // Mark as interacting to prevent DOM re-renders during click handling
    this._isInteracting = true;
    
    // Use requestAnimationFrame to safely exit interaction mode after click completes
    requestAnimationFrame(() => {
      this._isInteracting = false;
      
      // If a render was scheduled during interaction, do it now
      if (this._renderScheduled) {
        this._renderScheduled = false;
        this._render();
      }
    });

    let target = null;
    if (event.target instanceof Element) {
      target = event.target;
    } else if (event.composedPath) {
      target = event.composedPath().find(node => node instanceof Element) || null;
    }

    if (!target) {
      return;
    }
    
    // Tab navigation
    const tabButton = target.closest('.tab-button');
    if (tabButton) {
      event.preventDefault();
      this._activeTab = tabButton.dataset.tab;
      this._isEditMode = false;
      this._render();
      return;
    }

    // Edit button (Phase 3.1)
    if (target.closest("#btn-edit") || target.closest("#btn-manage-photos")) {
      event.preventDefault();
      if (this._activeTab === "details" || this._activeTab === "gallery") {
        this._toggleEditMode();
      }
      return;
    }

    // Save button (Phase 3.1)
    if (target.closest("#btn-save")) {
      event.preventDefault();
      this._handleSaveEdits();
      return;
    }

    // Cancel button (Phase 3.1)
    if (target.closest("#btn-cancel")) {
      event.preventDefault();
      this._isEditMode = false;
      this._render();
      return;
    }

    if (target.closest("#btn-done")) {
      event.preventDefault();
      this._isEditMode = false;
      this._render();
      return;
    }

    // Download button
    if (target.closest("#btn-download")) {
      event.preventDefault();
      this._handleDownload();
      return;
    }

    // Print button
    if (target.closest("#btn-print")) {
      event.preventDefault();
      this._handlePrint();
      return;
    }

    // 3D viewer button
    if (target.closest("#btn-viewer")) {
      event.preventDefault();
      this._openViewerPopup();
      return;
    }

    // Conflict dialog buttons
    if (target.closest("#btn-conflict-cancel")) {
      event.preventDefault();
      this._handleConflictResolution('cancel');
      return;
    }

    if (target.closest("#btn-conflict-reload")) {
      event.preventDefault();
      this._handleConflictResolution('reload');
      return;
    }

    if (target.closest("#btn-conflict-overwrite")) {
      event.preventDefault();
      this._handleConflictResolution('overwrite');
      return;
    }

    if (target.closest('#btn-photo-lightbox-close')) {
      event.preventDefault();
      this._closePhotoPreview();
      return;
    }

    if (target.closest('#btn-photo-lightbox-prev')) {
      event.preventDefault();
      this._stepPhotoPreview(-1);
      return;
    }

    if (target.closest('#btn-photo-lightbox-next')) {
      event.preventDefault();
      this._stepPhotoPreview(1);
      return;
    }

    if (target.classList && target.classList.contains('photo-lightbox')) {
      event.preventDefault();
      this._closePhotoPreview();
      return;
    }

    // Gallery photo actions
    const photoBtn = target.closest('.gallery-thumbnail [data-action]');
    if (photoBtn && this._activeTab === 'gallery') {
      event.preventDefault();
      const action = photoBtn.dataset.action;
      const photoTile = photoBtn.closest('.gallery-thumbnail');
      if (!photoTile) {
        return;
      }
      const photoId = photoTile.dataset.photoId;
      const photoIdx = parseInt(photoTile.dataset.photoIndex, 10);
      
      if (action === 'preview') {
        this._handlePhotoPreview(photoIdx);
      } else if (action === 'set-preview') {
        this._handleSetPhotoPreview(photoId);
      } else if (action === 'delete') {
        this._handleDeletePhoto(photoId);
      }
      return;
    }

    // Photo upload area
    if (target.closest('#photo-upload-area')) {
      event.preventDefault();
      const fileInput = this.shadowRoot.getElementById('photo-file-input');
      if (fileInput) {
        fileInput.click();
      }
      return;
    }

  }

  _handleChange(event) {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) {
      return;
    }
    if (target.id !== 'photo-file-input') {
      return;
    }

    const selectedFiles = Array.from(target.files || []);
    target.value = '';
    this._handlePhotoFileSelect(selectedFiles);
  }

  _getPhotoUploadArea(target) {
    if (!(target instanceof Element)) {
      return null;
    }
    return target.closest('#photo-upload-area');
  }

  _setPhotoUploadDragState(isActive) {
    const uploadArea = this.shadowRoot.getElementById('photo-upload-area');
    if (!uploadArea) {
      return;
    }
    uploadArea.style.background = isActive ? 'rgba(33, 150, 243, 0.12)' : 'transparent';
    uploadArea.style.borderColor = isActive ? 'var(--primary-color)' : 'var(--divider-color)';
  }

  _handleDragOver(event) {
    const uploadArea = this._getPhotoUploadArea(event.target);
    if (!uploadArea || !this._isEditMode || this._activeTab !== 'gallery') {
      return;
    }

    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
    this._setPhotoUploadDragState(true);
  }

  _handleDragLeave(event) {
    const uploadArea = this._getPhotoUploadArea(event.target);
    if (!uploadArea) {
      return;
    }

    const relatedTarget = event.relatedTarget;
    if (relatedTarget instanceof Node && uploadArea.contains(relatedTarget)) {
      return;
    }
    this._setPhotoUploadDragState(false);
  }

  _handleDrop(event) {
    const uploadArea = this._getPhotoUploadArea(event.target);
    if (!uploadArea || !this._isEditMode || this._activeTab !== 'gallery') {
      return;
    }

    event.preventDefault();
    this._setPhotoUploadDragState(false);

    const files = event.dataTransfer?.files;
    if (!files || files.length === 0) {
      return;
    }

    this._handlePhotoFileSelect(Array.from(files));
  }

  async _loadModelDetail() {
    if (this._loading) return;
    
    this._loading = true;
    this._error = "";
    this._render();
    
    try {
      const url = `${this._modelSidecarUrl}/api/models/${encodeURIComponent(this._modelRef)}/detail`;
      const response = await fetch(url);
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      this._modelDetail = await response.json();
      
      if (!this._modelDetail.success) {
        throw new Error(this._modelDetail.error || "Failed to fetch model detail");
      }
    } catch (error) {
      this._error = String(error || "Unknown error");
      this._modelDetail = null;
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _render() {
    const html = this._loading
      ? this._renderLoading()
      : this._error
      ? this._renderError()
      : this._modelDetail
      ? this._renderPopup()
      : this._renderEmpty();
    
    this.shadowRoot.innerHTML = html;

    // Initialize in-tab edit form after rendering.
    if (this._isEditMode && this._modelDetail && this._modelDetail.model) {
      this._initializeEditForm();
    }
  }

  _renderLoading() {
    return `
      <style>
        .popup { padding: 24px; text-align: center; }
        .spinner { 
          display: inline-block; 
          width: 32px; 
          height: 32px; 
          border: 3px solid #e0e0e0; 
          border-top-color: #2196F3; 
          border-radius: 50%; 
          animation: spin 0.8s linear infinite; 
        }
        @keyframes spin { to { transform: rotate(360deg); } }
      </style>
      <div class="popup">
        <div class="spinner"></div>
        <p>Loading model detail...</p>
      </div>
    `;
  }

  _renderError() {
    return `
      <style>
        .popup { padding: 24px; }
        .error-message { 
          background: #ffebee; 
          border: 1px solid #ef5350; 
          border-radius: 4px; 
          padding: 16px; 
          color: #c62828; 
        }
      </style>
      <div class="popup">
        <div class="error-message">
          <strong>Error loading model detail:</strong><br>
          ${this._error}
        </div>
      </div>
    `;
  }

  _renderEmpty() {
    return `
      <style>
        .popup { padding: 24px; text-align: center; color: #999; }
      </style>
      <div class="popup">
        <p>No model detail available</p>
      </div>
    `;
  }

  _renderPopup() {
    const model = this._modelDetail.model || {};
    
    const popupHtml = `
      <style>
        * { box-sizing: border-box; }
        
        .popup-container {
          max-width: 900px;
          font-family: var(--mdc-typography-font-family, 'Roboto', sans-serif);
          color: var(--primary-text-color);
          background: var(--card-background-color);
        }
        
        .popup-header {
          padding: 20px;
          border-bottom: 1px solid var(--divider-color);
          display: flex;
          gap: 16px;
          align-items: flex-start;
        }
        
        .header-thumbnail {
          width: 120px;
          height: 120px;
          background: var(--secondary-background-color);
          border-radius: 8px;
          flex-shrink: 0;
          overflow: hidden;
          ${model.preview_url ? `background-image: url("${model.preview_url}"); background-size: cover; background-position: center;` : ''}
        }
        
        .header-content {
          flex: 1;
          min-width: 0;
        }
        
        .header-title {
          font-size: 24px;
          font-weight: 500;
          margin: 0 0 8px 0;
          word-break: break-word;
        }
        
        .header-subtitle {
          font-size: 14px;
          color: var(--secondary-text-color);
          margin: 4px 0;
        }
        
        .header-tags {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-top: 8px;
        }
        
        .tag-chip {
          background: var(--secondary-background-color);
          border-radius: 16px;
          padding: 4px 12px;
          font-size: 12px;
          color: var(--primary-text-color);
        }
        
        .header-actions {
          display: flex;
          gap: 8px;
          margin-top: 12px;
          flex-wrap: wrap;
        }
        
        .action-button {
          background: var(--primary-color);
          color: var(--text-primary-color);
          border: none;
          border-radius: 4px;
          padding: 8px 16px;
          font-size: 14px;
          cursor: pointer;
          transition: background 0.2s;
        }
        
        .action-button:hover {
          background: var(--dark-primary-color);
        }
        
        .action-button:disabled {
          opacity: 0.6;
          cursor: not-allowed;
          background: var(--disabled-text-color);
        }
        
        .tab-navigation {
          display: flex;
          border-bottom: 2px solid var(--divider-color);
          padding: 0 20px;
          gap: 4px;
        }
        
        .tab-button {
          background: none;
          border: none;
          padding: 16px 12px;
          cursor: pointer;
          font-size: 14px;
          color: var(--secondary-text-color);
          border-bottom: 2px solid transparent;
          margin-bottom: -2px;
          transition: all 0.2s;
        }
        
        .tab-button:hover {
          color: var(--primary-text-color);
        }
        
        .tab-button.active {
          color: var(--primary-color);
          border-bottom-color: var(--primary-color);
        }
        
        .tab-content {
          padding: 20px;
          min-height: 300px;
        }
        
        .details-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
          gap: 24px;
        }
        
        .detail-section {
          break-inside: avoid;
        }
        
        .detail-section-title {
          font-size: 14px;
          font-weight: 600;
          color: var(--secondary-text-color);
          margin-bottom: 12px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        
        .detail-item {
          display: flex;
          gap: 12px;
          margin-bottom: 8px;
          font-size: 14px;
        }
        
        .detail-label {
          color: var(--secondary-text-color);
          min-width: 100px;
          flex-shrink: 0;
        }
        
        .detail-value {
          color: var(--primary-text-color);
          word-break: break-word;
          flex: 1;
        }
        
        .description-text {
          line-height: 1.6;
          color: var(--primary-text-color);
          margin-bottom: 16px;
          white-space: pre-wrap;
          word-break: break-word;
        }
        
        .stat-list {
          list-style: none;
          padding: 0;
          margin: 0;
        }
        
        .stat-list li {
          padding: 8px 0;
          border-bottom: 1px solid var(--divider-color);
          font-size: 14px;
        }
        
        .stat-list li:last-child {
          border-bottom: none;
        }
        
        .archive-list {
          display: grid;
          gap: 12px;
        }
        
        .archive-item {
          background: var(--secondary-background-color);
          border-radius: 4px;
          padding: 12px;
          font-size: 14px;
        }
        
        .archive-name {
          font-weight: 500;
          color: var(--primary-text-color);
          margin-bottom: 6px;
        }
        
        .archive-detail {
          color: var(--secondary-text-color);
          font-size: 12px;
        }
        
        .empty-state {
          text-align: center;
          padding: 40px 20px;
          color: var(--secondary-text-color);
        }

        .conflict-dialog {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0,0,0,0.5);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
        }

        .conflict-dialog-content {
          background: var(--card-background-color);
          border-radius: 8px;
          padding: 24px;
          max-width: 500px;
          box-shadow: 0 5px 33px rgba(0,0,0,0.12);
        }

        .conflict-dialog-title {
          font-size: 20px;
          font-weight: 600;
          margin-bottom: 12px;
          color: var(--primary-text-color);
        }

        .conflict-dialog-message {
          font-size: 14px;
          color: var(--secondary-text-color);
          margin-bottom: 20px;
          line-height: 1.5;
        }

        .conflict-dialog-actions {
          display: flex;
          gap: 8px;
          justify-content: flex-end;
        }

        .conflict-dialog-actions button {
          padding: 8px 16px;
          border: none;
          border-radius: 4px;
          font-size: 14px;
          cursor: pointer;
          font-weight: 500;
        }

        .btn-cancel-dialog {
          background: var(--divider-color);
          color: var(--primary-text-color);
        }

        .btn-reload {
          background: #ff9800;
          color: white;
        }

        .btn-overwrite {
          background: #f44336;
          color: white;
        }

        .photo-lightbox {
          position: fixed;
          inset: 0;
          background: rgba(0,0,0,0.82);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1100;
          padding: 24px;
          box-sizing: border-box;
        }

        .photo-lightbox-content {
          position: relative;
          display: flex;
          flex-direction: column;
          gap: 12px;
          max-width: min(96vw, 1200px);
          max-height: min(92vh, 900px);
          width: 100%;
        }

        .photo-lightbox-stage {
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 320px;
          border-radius: 12px;
          overflow: hidden;
          background: rgba(9, 14, 23, 0.92);
          box-shadow: 0 20px 60px rgba(0,0,0,0.35);
        }

        .photo-lightbox-image {
          display: block;
          max-width: 100%;
          max-height: calc(92vh - 120px);
          object-fit: contain;
          background: transparent;
        }

        .photo-lightbox-close,
        .photo-lightbox-nav {
          position: absolute;
          border: none;
          border-radius: 999px;
          width: 44px;
          height: 44px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          color: #fff;
          background: rgba(15,23,42,0.72);
          backdrop-filter: blur(10px);
        }

        .photo-lightbox-close {
          top: 16px;
          right: 16px;
          font-size: 22px;
          z-index: 1;
        }

        .photo-lightbox-nav {
          top: 50%;
          transform: translateY(-50%);
          font-size: 26px;
        }

        .photo-lightbox-nav.prev {
          left: 16px;
        }

        .photo-lightbox-nav.next {
          right: 16px;
        }

        .photo-lightbox-meta {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          color: #fff;
        }

        .photo-lightbox-title {
          font-size: 14px;
          font-weight: 600;
          color: #fff;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .photo-lightbox-counter {
          flex: 0 0 auto;
          font-size: 12px;
          font-weight: 600;
          padding: 6px 10px;
          border-radius: 999px;
          background: rgba(15,23,42,0.72);
        }

        @media (max-width: 640px) {
          .photo-lightbox {
            padding: 12px;
          }

          .photo-lightbox-close,
          .photo-lightbox-nav {
            width: 38px;
            height: 38px;
          }

          .photo-lightbox-nav.prev {
            left: 8px;
          }

          .photo-lightbox-nav.next {
            right: 8px;
          }

          .photo-lightbox-meta {
            flex-direction: column;
            align-items: flex-start;
          }
        }
      </style>
      
      <div class="popup-container">
        ${this._renderHeader(model)}
        ${this._renderTabNavigation()}
        ${this._renderTabContent(model)}
      </div>

      ${this._showConflictDialog ? `
        <div class="conflict-dialog">
          <div class="conflict-dialog-content">
            <div class="conflict-dialog-title">⚠️ Conflict Detected</div>
            <div class="conflict-dialog-message">
              This model was modified by another user or session. 
              Choose how you'd like to proceed:
            </div>
            <div class="conflict-dialog-actions">
              <button class="btn-cancel-dialog" id="btn-conflict-cancel">Cancel</button>
              <button class="btn-reload" id="btn-conflict-reload">Reload</button>
              <button class="btn-overwrite" id="btn-conflict-overwrite">Overwrite</button>
            </div>
          </div>
        </div>
      ` : ''}

      ${this._renderPhotoLightbox()}
    `;

    return popupHtml;
  }

  _renderHeader(model) {
    const creator = model.creator_name || "Unknown";
    const collection = model.collection_names && model.collection_names.length 
      ? model.collection_names.join(" / ") 
      : "Uncategorized";
    const keywords = model.keywords || [];
    
    return `
      <div class="popup-header">
        <div class="header-thumbnail"></div>
        <div class="header-content">
          <div class="header-title">${this._escapeHtml(model.name || "Untitled Model")}</div>
          <div class="header-subtitle">by ${this._escapeHtml(creator)}</div>
          <div class="header-subtitle">📁 ${this._escapeHtml(collection)}</div>
          
          ${keywords.length > 0 ? `
            <div class="header-tags">
              ${keywords.slice(0, 5).map(tag => 
                `<span class="tag-chip">${this._escapeHtml(tag)}</span>`
              ).join('')}
            </div>
          ` : ''}
          
          <div class="header-actions">
            ${this._activeTab === 'details' && !this._isEditMode ? `
              <button class="action-button" id="btn-edit">✏️ Edit</button>
            ` : ''}
            ${this._activeTab === 'gallery' && !this._isEditMode ? `
              <button class="action-button" id="btn-manage-photos">📸 Manage Photos</button>
            ` : ''}
            ${this._activeTab === 'details' && this._isEditMode ? `
              <button class="action-button" id="btn-save" style="background: #4CAF50;" ${this._isSaving ? 'disabled' : ''}>
                ${this._isSaving ? '⏳ Saving...' : '💾 Save'}
              </button>
              <button class="action-button" id="btn-cancel" style="background: #f44336;" ${this._isSaving ? 'disabled' : ''}>✕ Cancel</button>
            ` : this._activeTab === 'gallery' && this._isEditMode ? `
              <button class="action-button" id="btn-done" style="background: #607D8B;">✓ Done</button>
            ` : `
              <button class="action-button" id="btn-viewer">🧊 3D View</button>
              <button class="action-button" id="btn-download">📥 Download</button>
              <button class="action-button" id="btn-print">🖨️ Print</button>
            `}
          </div>
        </div>
      </div>
    `;
  }

  _renderTabNavigation() {
    return `
      <div class="tab-navigation">
        <button class="tab-button ${this._activeTab === 'details' ? 'active' : ''}" data-tab="details">
          Details
        </button>
        <button class="tab-button ${this._activeTab === 'gallery' ? 'active' : ''}" data-tab="gallery">
          Gallery
        </button>
        <button class="tab-button ${this._activeTab === 'prints' ? 'active' : ''}" data-tab="prints">
          Linked Prints
        </button>
      </div>
    `;
  }

  _renderTabContent(model) {
    switch (this._activeTab) {
      case "gallery":
        return this._renderGalleryTab();
      case "prints":
        return this._renderPrintsTab();
      default:
        return this._renderDetailsTab(model);
    }
  }

  _renderDetailsTab(model) {
    // In edit mode, show the edit form
    if (this._isEditMode) {
      return `
        <div class="tab-content" id="edit-form-container">
          <!-- Edit form will be inserted here by JavaScript -->
        </div>
      `;
    }

    const enrichment = this._modelDetail.enrichment || {};
    const files = model.files || [];
    const linkedCount = this._modelDetail.link_count || 0;
    
    return `
      <div class="tab-content">
        <div class="details-grid">
          ${model.description ? `
            <div class="detail-section" style="grid-column: 1/-1;">
              <div class="detail-section-title">Description</div>
              <div class="description-text">${this._escapeHtml(model.description)}</div>
            </div>
          ` : ''}
          
          <div class="detail-section">
            <div class="detail-section-title">Quick Stats</div>
            <ul class="stat-list">
              <li>📦 Files: ${files.length}</li>
              <li>⚙️ File types: ${files.map(f => f.file_type || 'unknown').join(', ') || 'N/A'}</li>
              <li>🖨️ Linked archives: ${linkedCount}</li>
              ${model.created_at ? `<li>📅 Created: ${new Date(model.created_at).toLocaleDateString()}</li>` : ''}
              ${model.updated_at ? `<li>🔄 Updated: ${new Date(model.updated_at).toLocaleDateString()}</li>` : ''}
            </ul>
          </div>
          
          ${enrichment.print_notes ? `
            <div class="detail-section">
              <div class="detail-section-title">Print Notes</div>
              <div class="description-text">${this._escapeHtml(enrichment.print_notes)}</div>
            </div>
          ` : ''}
          
          ${enrichment.difficulty_level ? `
            <div class="detail-section">
              <div class="detail-section-title">Difficulty</div>
              <div class="detail-value">${this._escapeHtml(enrichment.difficulty_level)}</div>
            </div>
          ` : ''}

          ${enrichment.print_time_estimate !== null && enrichment.print_time_estimate !== undefined && enrichment.print_time_estimate !== '' ? `
            <div class="detail-section">
              <div class="detail-section-title">Print Time Estimate</div>
              <div class="detail-value">${this._escapeHtml(String(enrichment.print_time_estimate))}s</div>
            </div>
          ` : ''}

          ${enrichment.support_type_hint ? `
            <div class="detail-section">
              <div class="detail-section-title">Support Type</div>
              <div class="detail-value">${this._escapeHtml(enrichment.support_type_hint)}</div>
            </div>
          ` : ''}
        </div>
      </div>
    `;
  }

  _renderGalleryTab() {
    const photos = this._modelDetail.photos || [];
    const previewPhotoId = this._modelDetail.preview_photo_id;
    const galleryModeHint = !this._isEditMode ? `
      <div style="
        margin: 0 0 16px;
        padding: 12px 14px;
        border-radius: 10px;
        background: var(--secondary-background-color);
        color: var(--secondary-text-color);
        font-size: 13px;
      ">
        Use <strong>Manage Photos</strong> in the header to upload or delete photos.
      </div>
    ` : '';
    
    if (!photos || photos.length === 0) {
      return `
        <div class="tab-content">
          ${galleryModeHint}
          <div class="empty-state">
            <p>📸 No Photos</p>
            <p>No photos uploaded yet.</p>
            ${this._isEditMode ? `<p><strong>Use the upload section below to add photos.</strong></p>` : ''}
          </div>
          ${this._isEditMode ? `
            <div style="padding: 20px; text-align: center;">
              <div id="photo-upload-area" style="
                border: 2px dashed var(--divider-color);
                border-radius: 8px;
                padding: 40px 20px;
                cursor: pointer;
                transition: background 0.2s;
              ">
                <p style="margin: 0; font-size: 24px;">📤</p>
                <p style="margin: 8px 0; color: var(--primary-text-color); font-weight: 500;">Click to upload photos</p>
                <p style="margin: 0; color: var(--secondary-text-color); font-size: 12px;">or drag and drop (JPG, PNG, WebP)</p>
              </div>
              <input type="file" id="photo-file-input" multiple accept=".jpg,.jpeg,.png,.webp" style="display: none;">
            </div>
          ` : ''}
        </div>
      `;
    }
    
    return `
      <div class="tab-content">
        ${galleryModeHint}
        <style>
          .gallery-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
          }
          
          .gallery-thumbnail {
            position: relative;
            aspect-ratio: 1;
            background: var(--secondary-background-color);
            border-radius: 8px;
            overflow: hidden;
            cursor: pointer;
          }
          
          .gallery-thumbnail img {
            width: 100%;
            height: 100%;
            object-fit: cover;
          }
          
          .thumbnail-overlay {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            opacity: 0;
            transition: all 0.2s;
          }
          
          .gallery-thumbnail:hover .thumbnail-overlay {
            background: rgba(0,0,0,0.5);
            opacity: 1;
          }
          
          .thumbnail-btn {
            width: 36px;
            height: 36px;
            border: none;
            border-radius: 50%;
            background: rgba(255,255,255,0.9);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            transition: transform 0.2s;
          }
          
          .thumbnail-btn:hover {
            transform: scale(1.1);
          }
          
          .preview-badge {
            position: absolute;
            top: 6px;
            right: 6px;
            background: #4CAF50;
            color: white;
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 11px;
            font-weight: 600;
          }
        </style>
        
        <div class="gallery-grid">
          ${photos.map((photo, idx) => `
            <div class="gallery-thumbnail" data-photo-id="${photo.id}" data-photo-index="${idx}">
              ${photo.thumbnail_url ? `
                <img src="${photo.thumbnail_url}" alt="Photo ${idx + 1}">
              ` : `
                <div style="width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: var(--secondary-text-color);">
                  📷
                </div>
              `}
              ${previewPhotoId === photo.id ? `
                <div class="preview-badge">PREVIEW</div>
              ` : ''}
              <div class="thumbnail-overlay">
                <button class="thumbnail-btn" title="View" data-action="preview">👁</button>
                ${this._isEditMode ? `
                  <button class="thumbnail-btn" title="Set as preview" data-action="set-preview" style="background: #FF9800;">⭐</button>
                  <button class="thumbnail-btn" title="Delete" data-action="delete" style="background: #f44336;">🗑</button>
                ` : ''}
              </div>
            </div>
          `).join('')}
        </div>
        
        ${this._isEditMode ? `
          <div style="padding: 20px; border-top: 1px solid var(--divider-color); text-align: center;">
            <div id="photo-upload-area" style="
              border: 2px dashed var(--divider-color);
              border-radius: 8px;
              padding: 40px 20px;
              cursor: pointer;
              transition: background 0.2s;
            ">
              <p style="margin: 0; font-size: 24px;">📤</p>
              <p style="margin: 8px 0; color: var(--primary-text-color); font-weight: 500;">Click to upload more photos</p>
              <p style="margin: 0; color: var(--secondary-text-color); font-size: 12px;">or drag and drop (JPG, PNG, WebP)</p>
            </div>
            <input type="file" id="photo-file-input" multiple accept=".jpg,.jpeg,.png,.webp" style="display: none;">
          </div>
        ` : ''}
      </div>
    `;
  }

  _renderPrintsTab() {
    const links = this._modelDetail.linked_archives || [];
    
    if (links.length === 0) {
      return `
        <div class="tab-content">
          <div class="empty-state">
            <p>🖨️ No Linked Prints</p>
            <p>This model hasn't been printed yet.</p>
          </div>
        </div>
      `;
    }
    
    // Archive grid view with filters and sorting
    return `
      <div class="tab-content">
        <style>
          .archive-controls {
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
            flex-wrap: wrap;
            align-items: center;
          }
          
          .archive-filter-group {
            display: flex;
            gap: 8px;
            align-items: center;
          }
          
          .filter-label {
            font-size: 12px;
            font-weight: 500;
            color: var(--secondary-text-color);
          }
          
          .filter-btn {
            padding: 4px 12px;
            border: 1px solid var(--divider-color);
            background: var(--card-background-color);
            color: var(--primary-text-color);
            border-radius: 16px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.2s;
          }
          
          .filter-btn:hover {
            border-color: var(--primary-color);
          }
          
          .filter-btn.active {
            background: var(--primary-color);
            color: white;
            border-color: var(--primary-color);
          }
          
          .sort-select {
            padding: 4px 8px;
            border: 1px solid var(--divider-color);
            background: var(--card-background-color);
            color: var(--primary-text-color);
            border-radius: 4px;
            font-size: 12px;
            cursor: pointer;
            color-scheme: light dark;
          }

          .sort-select option,
          .sort-select optgroup {
            background: var(--card-background-color);
            color: var(--primary-text-color);
          }
          
          .archive-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
            gap: 12px;
          }
          
          .archive-card {
            border: 1px solid var(--divider-color);
            border-radius: 8px;
            overflow: hidden;
            background: var(--card-background-color);
            cursor: pointer;
            transition: all 0.2s;
          }
          
          .archive-card:hover {
            border-color: var(--primary-color);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            transform: translateY(-2px);
          }
          
          .archive-thumbnail {
            width: 100%;
            aspect-ratio: 1;
            object-fit: cover;
            background: var(--secondary-background-color);
            border-bottom: 1px solid var(--divider-color);
          }
          
          .archive-card-content {
            padding: 10px;
            display: flex;
            flex-direction: column;
            gap: 6px;
          }
          
          .archive-title {
            font-weight: 500;
            font-size: 13px;
            line-height: 1.3;
            color: var(--primary-text-color);
            overflow: hidden;
            text-overflow: ellipsis;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
          }
          
          .archive-meta {
            font-size: 11px;
            color: var(--secondary-text-color);
            display: flex;
            flex-direction: column;
            gap: 2px;
          }
          
          .archive-status {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: 500;
            width: fit-content;
          }
          
          .status-success {
            background: rgba(76, 175, 80, 0.2);
            color: #2e7d32;
          }
          
          .status-failed {
            background: rgba(244, 67, 54, 0.2);
            color: #c62828;
          }
          
          .status-stopped {
            background: rgba(255, 152, 0, 0.2);
            color: #e65100;
          }
          
          .archive-actions {
            display: flex;
            gap: 4px;
            border-top: 1px solid var(--divider-color);
            padding-top: 6px;
          }
          
          .action-btn {
            flex: 1;
            padding: 4px 6px;
            border: none;
            background: var(--secondary-background-color);
            color: var(--primary-text-color);
            border-radius: 3px;
            cursor: pointer;
            font-size: 11px;
            font-weight: 500;
            transition: all 0.2s;
          }
          
          .action-btn:hover {
            background: var(--primary-color);
            color: white;
          }
        </style>
        
        <div class="archive-controls">
          <div class="archive-filter-group">
            <span class="filter-label">Filter:</span>
            <button class="filter-btn active" data-filter="all">All (${links.length})</button>
            <button class="filter-btn" data-filter="success">Success (${links.filter(l => l.status === 'success').length})</button>
            <button class="filter-btn" data-filter="failed">Failed (${links.filter(l => l.status === 'failed').length})</button>
          </div>
          
          <div class="archive-filter-group">
            <span class="filter-label">Sort:</span>
            <select class="sort-select" data-sort-by="date_newest">
              <option value="date_newest">Date (Newest)</option>
              <option value="date_oldest">Date (Oldest)</option>
              <option value="filament">Filament</option>
              <option value="name">Name</option>
            </select>
          </div>
        </div>
        
        <div class="archive-grid">
          ${links.map(link => `
            <div class="archive-card" data-archive-id="${link.archive_id}">
              ${link.thumbnail_url ? `
                <img class="archive-thumbnail" src="${link.thumbnail_url}" alt="Archive #${link.archive_id}" loading="lazy">
              ` : `
                <div class="archive-thumbnail" style="display: flex; align-items: center; justify-content: center;">
                  <span style="font-size: 32px;">🖨️</span>
                </div>
              `}
              <div class="archive-card-content">
                <div class="archive-title">${this._escapeHtml(link.name || ('Archive #' + link.archive_id))}</div>
                <div class="archive-meta">
                  ${link.completed_at ? `<div>📅 ${new Date(link.completed_at).toLocaleDateString()}</div>` : ''}
                  ${link.filament_name ? `<div>🎨 ${this._escapeHtml(link.filament_name)}</div>` : ''}
                  ${link.status ? `<div class="archive-status status-${link.status}">${link.status.toUpperCase()}</div>` : ''}
                </div>
                <div class="archive-actions">
                  <button class="action-btn" data-action="view-archive">View</button>
                  <button class="action-btn" data-action="print-again">Print Again</button>
                </div>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Phase 3.1 Methods: Edit Mode & Conflict Detection
  
  _toggleEditMode() {
    this._isEditMode = !this._isEditMode;
    if (this._isEditMode) {
      this._lastModifiedTimestamp = this._modelDetail.model.last_modified || Date.now();
      this._editAdvancedSectionOpen = false;
    }
    this._render();
  }

  async _handleSaveEdits() {
    const editForm = this.shadowRoot.querySelector('model-detail-edit-form');
    if (editForm && typeof editForm.submitEdits === 'function') {
      editForm.submitEdits();
      return;
    }

    console.warn('Edit form is not ready; cannot save yet.');
  }

  async _fetchCurrentModel() {
    const url = `${this._modelSidecarUrl}/api/models/${encodeURIComponent(this._modelRef)}/detail`;
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    return data.model || {};
  }

  _handleConflictResolution(action) {
    this._showConflictDialog = false;
    
    if (action === 'reload') {
      // Reload model and discard changes
      this._loadModelDetail();
      this._isEditMode = false;
    } else if (action === 'overwrite') {
      // Force save (overwrite upstream)
      this._handleSaveEdits();
    }
    // 'cancel' just closes the dialog
    
    this._render();
  }

  _initializeEditForm() {
    const container = this.shadowRoot.getElementById('edit-form-container');
    if (!container) return;

    // Reuse existing form instance to preserve focus and in-progress edits.
    const existingForm = container.querySelector('model-detail-edit-form');
    if (existingForm) {
      existingForm.hass = this._hass;
      return;
    }

    const editForm = document.createElement('model-detail-edit-form');
    const modelDataForEdit = {
      ...(this._modelDetail.model || {}),
      enrichment: this._modelDetail.enrichment || {},
    };
    editForm.setConfig({
      model_data: modelDataForEdit,
      advanced_section_open: this._editAdvancedSectionOpen,
      on_advanced_toggle: (isOpen) => {
        this._editAdvancedSectionOpen = Boolean(isOpen);
      },
      on_save: (formData) => this._handleFormSave(formData),
      on_cancel: () => {
        this._isEditMode = false;
        this._editAdvancedSectionOpen = false;
        this._render();
      }
    });
    editForm.hass = this._hass;
    container.appendChild(editForm);
  }

  async _handleFormSave(formData) {
    // Show immediate feedback before network checks so save click feels responsive.
    this._isSaving = true;
    this._error = null;
    this._render();

    // Check for conflicts first
    try {
      const currentModel = await this._fetchCurrentModel();
      if (currentModel.last_modified && currentModel.last_modified > this._lastModifiedTimestamp) {
        this._isSaving = false;
        this._showConflictDialog = true;
        this._conflictDialog = {
          currentModel,
          formData,
          action: 'save',
        };
        this._render();
        return;
      }
    } catch (error) {
      console.warn('Could not check for conflicts:', error);
      // Continue with save anyway
    }

    // Save to sidecar via HA service
    if (this._hass) {
      try {
        console.log('Calling REST command with formData:', formData);
        
        const serviceResponse = await this._hass.callService('rest_command', 'model_catalog_update_model', {
          model_ref: formData.model_ref,
          model_name: formData.model_name,
          description: formData.description,
          tags: formData.tags,
          collection: formData.collection,
          enrichment: formData.enrichment,
        });
        
        console.log('REST command response:', serviceResponse);
        
        // Reload model detail
        console.log('Reloading model detail after save...');
        await this._loadModelDetail();
        
        // Exit edit mode and close popup
        this._isEditMode = false;
        this._editAdvancedSectionOpen = false;
        this._isSaving = false;
        this._error = null;
        console.log('Model saved successfully');
        this._render();
      } catch (error) {
        console.error('Error saving model:', error);
        const errorMsg = error?.message || String(error) || 'Unknown error';
        this._isSaving = false;
        this._error = `Failed to save: ${errorMsg}`;
        this._render();
      }
    } else {
      this._isSaving = false;
      this._error = 'Home Assistant service context unavailable.';
      this._render();
    }
  }

  _handlePhotoPreview(photoIdx) {
    const photos = this._modelDetail.photos || [];
    if (photoIdx < 0 || photoIdx >= photos.length) return;

    this._activePhotoIndex = photoIdx;
    this._render();
  }

  _closePhotoPreview() {
    if (this._activePhotoIndex == null) {
      return;
    }
    this._activePhotoIndex = null;
    this._render();
  }

  _stepPhotoPreview(direction) {
    const photos = this._modelDetail && Array.isArray(this._modelDetail.photos) ? this._modelDetail.photos : [];
    if (!photos.length || this._activePhotoIndex == null) {
      return;
    }

    const nextIndex = (this._activePhotoIndex + direction + photos.length) % photos.length;
    this._activePhotoIndex = nextIndex;
    this._render();
  }

  _renderPhotoLightbox() {
    const photos = this._modelDetail && Array.isArray(this._modelDetail.photos) ? this._modelDetail.photos : [];
    if (!photos.length || this._activePhotoIndex == null) {
      return '';
    }

    const index = Math.max(0, Math.min(this._activePhotoIndex, photos.length - 1));
    const photo = photos[index] || {};
    const imageUrl = String(photo.image_url || photo.thumbnail_url || '').trim();
    if (!imageUrl) {
      return '';
    }

    const photoName = String(photo.filename || `Photo ${index + 1}`).trim() || `Photo ${index + 1}`;
    const escapedName = this._escapeHtml(photoName);
    const escapedImageUrl = this._escapeHtml(imageUrl);

    return `
      <div class="photo-lightbox" role="dialog" aria-modal="true" aria-label="Photo preview">
        <div class="photo-lightbox-content">
          <div class="photo-lightbox-stage">
            <button class="photo-lightbox-close" id="btn-photo-lightbox-close" type="button" aria-label="Close photo preview">✕</button>
            ${photos.length > 1 ? `
              <button class="photo-lightbox-nav prev" id="btn-photo-lightbox-prev" type="button" aria-label="Previous photo">‹</button>
              <button class="photo-lightbox-nav next" id="btn-photo-lightbox-next" type="button" aria-label="Next photo">›</button>
            ` : ''}
            <img class="photo-lightbox-image" src="${escapedImageUrl}" alt="${escapedName}">
          </div>
          <div class="photo-lightbox-meta">
            <div class="photo-lightbox-title">${escapedName}</div>
            <div class="photo-lightbox-counter">${index + 1} / ${photos.length}</div>
          </div>
        </div>
      </div>
    `;
  }

  async _handleSetPhotoPreview(photoId) {
    if (!this._modelSidecarUrl || !this._modelRef) return;
    
    try {
      const response = await fetch(
        `${this._modelSidecarUrl.replace(/\/$/, '')}/api/models/${encodeURIComponent(this._modelRef)}/photos/${encodeURIComponent(photoId)}/preview`,
        {
          method: 'POST',
        }
      );

      let payload = null;
      try {
        payload = await response.json();
      } catch (parseError) {
        payload = null;
      }

      if (!response.ok) {
        const errorMessage = payload && payload.error
          ? String(payload.error)
          : `HTTP ${response.status}`;
        throw new Error(errorMessage);
      }
      
      // Reload model detail
      this._error = '';
      await this._loadModelDetail();
      this._render();
    } catch (error) {
      console.error('Error setting preview photo:', error);
      this._error = `Failed to set preview: ${error}`;
      this._render();
    }
  }

  _handleDeletePhoto(photoId) {
    if (confirm('Are you sure you want to delete this photo?')) {
      this._performDeletePhoto(photoId);
    }
  }

  async _performDeletePhoto(photoId) {
    if (!this._modelSidecarUrl || !this._modelRef) return;
    
    try {
      const response = await fetch(
        `${this._modelSidecarUrl.replace(/\/$/, '')}/api/models/${encodeURIComponent(this._modelRef)}/photos/${encodeURIComponent(photoId)}`,
        {
          method: 'DELETE',
        }
      );

      let payload = null;
      try {
        payload = await response.json();
      } catch (parseError) {
        payload = null;
      }

      if (!response.ok) {
        const errorMessage = payload && payload.error
          ? String(payload.error)
          : `HTTP ${response.status}`;
        throw new Error(errorMessage);
      }
      
      // Reload model detail
      this._error = '';
      await this._loadModelDetail();
      this._render();
    } catch (error) {
      console.error('Error deleting photo:', error);
      this._error = `Failed to delete photo: ${error}`;
      this._render();
    }
  }

  async _handlePhotoFileSelect(files) {
    if (!files || files.length === 0) return;
    
    // Process each file
    for (const file of files) {
      await this._uploadPhoto(file);
    }
  }

  async _uploadPhoto(file) {
    if (!this._modelSidecarUrl || !this._modelRef) return;
    
    // Validate file type and size
    const maxSize = 10 * 1024 * 1024; // 10MB
    if (file.size > maxSize) {
      this._error = `File too large: ${file.name} (max 10MB)`;
      this._render();
      return;
    }
    
    const validTypes = ['image/jpeg', 'image/png', 'image/webp'];
    if (!validTypes.includes(file.type)) {
      this._error = `Invalid file type: ${file.name} (must be JPG, PNG, or WebP)`;
      this._render();
      return;
    }

    try {
      const base64Data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (event) => resolve(event.target?.result);
        reader.onerror = () => reject(reader.error || new Error('Failed to read file'));
        reader.readAsDataURL(file);
      });

      const response = await fetch(
        `${this._modelSidecarUrl.replace(/\/$/, '')}/api/models/${encodeURIComponent(this._modelRef)}/photos`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            photo_file: base64Data,
            set_as_preview: !this._modelDetail.photos || this._modelDetail.photos.length === 0,
          }),
        }
      );

      let payload = null;
      try {
        payload = await response.json();
      } catch (parseError) {
        payload = null;
      }

      if (!response.ok) {
        const errorMessage = payload && payload.error
          ? String(payload.error)
          : `HTTP ${response.status}`;
        throw new Error(errorMessage);
      }

      this._error = '';
      await this._loadModelDetail();
      this._render();
    } catch (error) {
      console.error('Error reading file:', error);
      this._error = `Failed to upload ${file.name}: ${error}`;
      this._render();
    }
  }

  _handleDownload() {
    if (!this._modelDetail || !this._modelDetail.model) {
      console.warn('No model detail available for download');
      return;
    }

    const model = this._modelDetail.model;
    const files = model.files || [];
    
    if (files.length === 0) {
      this._error = 'No files available for download';
      this._render();
      return;
    }

    // For now, log available files
    console.log('Download triggered. Available files:', files);
    
    // In future: could open a modal to select which file to download
    // For now, just show a notification
    if (this._hass) {
      this._hass.callService('persistent_notification', 'create', {
        title: 'Model Download',
        message: `${files.length} file(s) available. Download feature coming soon.`,
      }).catch(err => console.error('Notification failed:', err));
    }
  }

  _handlePrint() {
    if (!this._modelDetail || !this._modelDetail.model) {
      console.warn('No model detail available for print');
      return;
    }

    const model = this._modelDetail.model;
    const files = model.files || [];
    
    if (files.length === 0) {
      this._error = 'No files available to print';
      this._render();
      return;
    }

    // For now, log and show notification
    console.log('Print triggered. Available files:', files);
    
    // In future: could trigger print workflow via HA service
    if (this._hass) {
      this._hass.callService('persistent_notification', 'create', {
        title: 'Model Print',
        message: `${files.length} file(s) ready. Print workflow coming soon.`,
      }).catch(err => console.error('Notification failed:', err));
    }
  }

  _buildModelViewerCardConfig() {
    const model = this._modelDetail && this._modelDetail.model ? this._modelDetail.model : {};
    return {
      type: 'custom:model-detail-3d-viewer-tab',
      model_ref: this._modelRef,
      model_name: String(model.name || '').trim(),
      model_sidecar_url: this._modelSidecarUrl,
      model_json: JSON.stringify(model),
    };
  }

  _buildModelViewerPopupContent() {
    return {
      type: 'vertical-stack',
      cards: [this._buildModelViewerCardConfig()],
    };
  }

  _fireBrowserModEvent(service, data) {
    const event = new CustomEvent('ll-custom', {
      bubbles: true,
      composed: true,
      detail: {
        browser_mod: {
          service,
          data,
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

  _replaceCurrentPopup(popupConfig) {
    if (!popupConfig || typeof popupConfig !== 'object') {
      return;
    }

    this._fireBrowserModEvent('browser_mod.sequence', {
      sequence: [
        { service: 'browser_mod.close_popup' },
        { service: 'browser_mod.popup', data: popupConfig },
      ],
    });
  }

  _openViewerPopup() {
    const model = this._modelDetail && this._modelDetail.model ? this._modelDetail.model : null;

    if (!model) {
      if (this._hass) {
        this._hass.callService('persistent_notification', 'create', {
          title: '3D Viewer',
          message: 'Model details are not loaded yet. Try again in a moment.',
        }).catch(err => console.error('Notification failed:', err));
      }
      return;
    }

    this._replaceCurrentPopup({
      title: `${String(model.name || 'Model')} - 3D Viewer`,
      size: 'wide',
      content: this._buildModelViewerPopupContent(),
    });
  }

  getCardSize() {
    return 10;
  }
}

customElements.define("model-detail-popup-card", ModelDetailPopupCard);
