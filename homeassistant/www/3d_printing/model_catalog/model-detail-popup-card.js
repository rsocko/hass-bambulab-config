/**
 * Model Detail Popup Card
 * 
 * Provides a comprehensive detail view and inline editing interface for models
 * from the Manyfold catalog directly in Home Assistant UI.
 * 
 * Phase 3.0 MVP - Detail View (Read-Only)
 * - Details tab with model metadata and enrichment
 * - Media Gallery tab for photos
 * - 3D Viewer tab for source model inspection
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
    this._error = "";
    this._activeTab = "details";
    this._isEditMode = false;
    this._lastModifiedTimestamp = null;
    this._conflictDialog = null;
    this._showConflictDialog = false;
    this._photoGallery = [];
    
    // Bound handlers
    this._boundClickHandler = this._handleClick.bind(this);
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
    
    this._render();
  }

  connectedCallback() {
    this.shadowRoot.addEventListener("click", this._boundClickHandler);
  }

  disconnectedCallback() {
    this.shadowRoot.removeEventListener("click", this._boundClickHandler);
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

      const legacyUrlEntity = this._hass.states["input_text.model_catalog_sidecar_url"];
      if (legacyUrlEntity && legacyUrlEntity.state) {
        return String(legacyUrlEntity.state).trim();
      }
    }

    return String(this._config && this._config.model_sidecar_url || "").trim();
  }

  _handleClick(event) {
    const target = event.target;
    
    // Tab navigation
    if (target.classList.contains("tab-button")) {
      event.preventDefault();
      this._activeTab = target.dataset.tab;
      this._isEditMode = false;
      this._render();
      return;
    }

    // Edit button (Phase 3.1)
    if (target.id === "btn-edit" || target.closest("#btn-edit")) {
      event.preventDefault();
      if (this._activeTab === "details") {
        this._toggleEditMode();
      }
      return;
    }

    // Save button (Phase 3.1)
    if (target.id === "btn-save" || target.closest("#btn-save")) {
      event.preventDefault();
      this._handleSaveEdits();
      return;
    }

    // Cancel button (Phase 3.1)
    if (target.id === "btn-cancel" || target.closest("#btn-cancel")) {
      event.preventDefault();
      this._isEditMode = false;
      this._render();
      return;
    }
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
    this.shadowRoot.addEventListener("click", this._boundClickHandler);
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
    
    return `
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
      </style>
      
      <div class="popup-container">
        ${this._renderHeader(model)}
        ${this._renderTabNavigation()}
        ${this._renderTabContent(model)}
      </div>
    `;
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
            <button class="action-button">Edit</button>
            <button class="action-button">Download</button>
            <button class="action-button">Print</button>
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
        <button class="tab-button ${this._activeTab === 'viewer' ? 'active' : ''}" data-tab="viewer">
          3D Viewer
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
      case "viewer":
        return this._renderViewerTab();
      case "prints":
        return this._renderPrintsTab();
      default:
        return this._renderDetailsTab(model);
    }
  }

  _renderDetailsTab(model) {
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
        </div>
      </div>
    `;
  }

  _renderGalleryTab() {
    return `
      <div class="tab-content">
        <div class="empty-state">
          <p>📸 Photo Gallery</p>
          <p>Media gallery features coming in Phase 3.1</p>
        </div>
      </div>
    `;
  }

  _renderViewerTab() {
    const files = (this._modelDetail.model && this._modelDetail.model.files) || [];
    
    return `
      <div class="tab-content">
        ${files.length > 0 ? `
          <p>File selector would go here (${files.length} files available)</p>
        ` : `
          <div class="empty-state">
            <p>📁 No Files</p>
            <p>This model has no files available for viewing.</p>
          </div>
        `}
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
    
    return `
      <div class="tab-content">
        <div class="archive-list">
          ${links.map(link => `
            <div class="archive-item">
              <div class="archive-name">Archive #${link.archive_id}</div>
              <div class="archive-detail">
                Match: ${link.match_method} (${link.match_confidence})
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
    }
    this._render();
  }

  async _handleSaveEdits() {
    // Check for conflicts
    try {
      const currentModel = await this._fetchCurrentModel();
      if (currentModel.last_modified && currentModel.last_modified > this._lastModifiedTimestamp) {
        this._showConflictDialog = true;
        this._conflictDialog = {
          currentModel,
          action: 'save',
        };
        this._render();
        return;
      }
    } catch (error) {
      console.warn('Could not check for conflicts:', error);
      // Continue with save anyway
    }

    // Get form data from edit form
    const editForm = this.shadowRoot.querySelector('model-detail-edit-form');
    if (!editForm) {
      console.error('Edit form not found');
      return;
    }

    // Call save service
    if (this._hass) {
      try {
        this._hass.callService('model_catalog', 'update_model', {
          model_ref: this._modelRef,
          model_name: editForm._formData.model_name,
          description: editForm._formData.description,
          tags: editForm._formData.tags,
          collection: editForm._formData.collection,
          enrichment: editForm._formData.enrichment,
        });
        this._isEditMode = false;
        this._render();
      } catch (error) {
        console.error('Error saving model:', error);
        this._error = `Failed to save: ${error}`;
        this._render();
      }
    }
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

  getCardSize() {
    return 10;
  }
}

customElements.define("model-detail-popup-card", ModelDetailPopupCard);
