/**
 * Model Detail Related Models Component
 * 
 * Displays similar models based on similarity scoring (collection, creator, keywords).
 * Part of Phase 3.3 Cross-System Integration.
 * 
 * Usage in model-detail-popup-card.js:
 *   type: custom:model-detail-related-models
 *   model_ref: "gridfinity-bin"
 *   model_sidecar_url: "http://localhost:8000"
 *   limit: 5
 */

class ModelDetailRelatedModels extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    
    // State
    this._modelRef = "";
    this._modelSidecarUrl = "";
    this._relatedModels = [];
    this._loading = false;
    this._error = "";
    this._limit = 5;
    
    // Bound handlers
    this._boundClickHandler = this._handleClick.bind(this);
  }

  setConfig(config) {
    this._config = config || {};
    this._modelRef = String(this._config.model_ref || "").trim();
    this._modelSidecarUrl = String(this._config.model_sidecar_url || "").trim();
    this._limit = parseInt(this._config.limit || 5);
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    
    // Resolve sidecar URL from entities if needed
    this._modelSidecarUrl = this._resolveModelSidecarUrl();
    
    // Load related models if we haven't yet
    if (!this._relatedModels.length && !this._loading && !this._error && this._modelRef && this._modelSidecarUrl) {
      this._loadRelatedModels();
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
    if (this._modelSidecarUrl) {
      return this._modelSidecarUrl;
    }

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

    return "";
  }

  async _loadRelatedModels() {
    if (!this._modelRef || !this._modelSidecarUrl) {
      this._error = "Missing model reference or sidecar URL";
      this._render();
      return;
    }

    this._loading = true;
    this._error = "";
    this._render();

    try {
      const url = `${this._modelSidecarUrl}/api/models/${encodeURIComponent(this._modelRef)}/related?limit=${this._limit}`;
      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      
      if (data.success && data.related_models) {
        this._relatedModels = data.related_models;
        this._error = "";
      } else {
        this._error = data.error || "Failed to load related models";
        this._relatedModels = [];
      }
    } catch (err) {
      this._error = String(err.message || err);
      this._relatedModels = [];
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _handleClick(event) {
    const target = event.target;

    // Model card click - navigate to related model
    if (target.closest(".related-model-card")) {
      const modelCard = target.closest(".related-model-card");
      const modelRef = modelCard.dataset.modelRef;
      if (modelRef) {
        this._navigateToModel(modelRef);
      }
      return;
    }

    // Retry button click
    if (target.id === "retry-related-models") {
      this._loadRelatedModels();
      return;
    }
  }

  _navigateToModel(modelRef) {
    // Dispatch custom event for parent component to handle navigation
    this.dispatchEvent(new CustomEvent("navigate-to-model", {
      detail: { model_ref: modelRef },
      bubbles: true,
      composed: true
    }));
  }

  _render() {
    const styles = `
      <style>
        :host {
          display: block;
          font-family: var(--paper-font-body1_-_font-family);
          color: var(--primary-text-color);
        }

        .container {
          padding: 16px 0;
        }

        .title {
          font-size: 18px;
          font-weight: 500;
          margin-bottom: 16px;
          color: var(--primary-text-color);
        }

        .grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
          gap: 12px;
        }

        .related-model-card {
          position: relative;
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          overflow: hidden;
          cursor: pointer;
          transition: all 0.2s ease;
          background: var(--card-background-color);
        }

        .related-model-card:hover {
          border-color: var(--primary-color);
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
          transform: translateY(-2px);
        }

        .card-image {
          width: 100%;
          aspect-ratio: 1;
          object-fit: cover;
          background: var(--ha-card-background);
          border-bottom: 1px solid var(--divider-color);
        }

        .card-content {
          padding: 12px;
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .card-title {
          font-weight: 500;
          font-size: 14px;
          line-height: 1.3;
          overflow: hidden;
          text-overflow: ellipsis;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          color: var(--primary-text-color);
        }

        .card-creator {
          font-size: 12px;
          color: var(--secondary-text-color);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .similarity-score {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          font-size: 12px;
          background: var(--primary-color);
          color: white;
          padding: 2px 8px;
          border-radius: 12px;
          width: fit-content;
        }

        .score-value {
          font-weight: 600;
        }

        .card-reasons {
          font-size: 11px;
          color: var(--secondary-text-color);
          line-height: 1.3;
          max-height: 40px;
          overflow: hidden;
        }

        .reason-tag {
          display: inline-block;
          background: var(--secondary-background-color);
          padding: 2px 6px;
          border-radius: 4px;
          margin-right: 4px;
          margin-bottom: 2px;
        }

        .loading {
          text-align: center;
          padding: 32px 16px;
          color: var(--secondary-text-color);
        }

        .spinner {
          display: inline-block;
          width: 40px;
          height: 40px;
          border: 4px solid var(--divider-color);
          border-top-color: var(--primary-color);
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        .error {
          padding: 16px;
          background: rgba(239, 83, 80, 0.1);
          border: 1px solid rgba(239, 83, 80, 0.3);
          border-radius: 8px;
          color: #ef5350;
          font-size: 14px;
        }

        .empty {
          text-align: center;
          padding: 32px 16px;
          color: var(--secondary-text-color);
          font-size: 14px;
        }

        .retry-button {
          display: inline-block;
          margin-top: 12px;
          padding: 8px 16px;
          background: var(--primary-color);
          color: white;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-size: 14px;
          font-weight: 500;
        }

        .retry-button:hover {
          background: var(--primary-color);
          opacity: 0.9;
        }
      </style>
    `;

    let content = "";

    if (this._loading) {
      content = `
        <div class="loading">
          <div class="spinner"></div>
          <p>Loading related models...</p>
        </div>
      `;
    } else if (this._error) {
      content = `
        <div class="error">
          <p>Error loading related models: ${this._error}</p>
          <button class="retry-button" id="retry-related-models">Retry</button>
        </div>
      `;
    } else if (!this._relatedModels.length) {
      content = `
        <div class="empty">
          <p>No related models found</p>
        </div>
      `;
    } else {
      content = `
        <div class="grid">
          ${this._relatedModels.map(model => this._renderModelCard(model)).join("")}
        </div>
      `;
    }

    this.shadowRoot.innerHTML = `
      ${styles}
      <div class="container">
        <div class="title">Related Models</div>
        ${content}
      </div>
    `;
  }

  _renderModelCard(model) {
    const modelRef = model.public_id || model.model_id || "";
    const previewUrl = model.preview_url || "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 256 256'%3E%3Crect fill='%23f0f0f0' width='256' height='256'/%3E%3C/svg%3E";
    
    const reasonsHtml = (model.reasons || [])
      .map(reason => `<span class="reason-tag">${this._escapeHtml(reason)}</span>`)
      .join("");

    return `
      <div class="related-model-card" data-model-ref="${this._escapeHtml(modelRef)}">
        <img class="card-image" src="${previewUrl}" alt="${this._escapeHtml(model.name)}" loading="lazy">
        <div class="card-content">
          <div class="card-title">${this._escapeHtml(model.name)}</div>
          ${model.creator_name ? `<div class="card-creator">by ${this._escapeHtml(model.creator_name)}</div>` : ""}
          <div class="similarity-score">
            <span class="score-value">${model.similarity_score}%</span> match
          </div>
          ${reasonsHtml ? `<div class="card-reasons">${reasonsHtml}</div>` : ""}
        </div>
      </div>
    `;
  }

  _escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }
}

customElements.define("model-detail-related-models", ModelDetailRelatedModels);
