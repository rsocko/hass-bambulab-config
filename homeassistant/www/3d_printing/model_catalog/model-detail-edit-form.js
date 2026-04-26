/**
 * Model Detail Edit Form Component
 * 
 * Handles inline editing of model metadata and enrichment fields.
 * Part of Phase 3.1 implementation.
 * 
 * Usage:
 *   type: custom:model-detail-edit-form
 *   model_data: <model_object>
 *   on_save: <callback>
 *   on_cancel: <callback>
 */

class ModelDetailEditForm extends HTMLElement {
  constructor() {
    super();
    this._model = null;
    this._formData = {};
    this._validationErrors = {};
  }

  setConfig(config) {
    this._config = config;
    this._model = config.model_data || {};
    this._onSave = config.on_save || (() => {});
    this._onCancel = config.on_cancel || (() => {});
  }

  set hass(hass) {
    this._hass = hass;
  }

  connectedCallback() {
    this._render();
  }

  _render() {
    this.innerHTML = `
      <style>
        .form-container {
          display: grid;
          gap: 16px;
          max-width: 800px;
          padding: 16px;
        }
        .form-group {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .form-group label {
          font-weight: 500;
          color: var(--primary-text-color);
          font-size: 14px;
        }
        .form-group input,
        .form-group textarea,
        .form-group select {
          padding: 8px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          font-family: inherit;
          background: var(--card-background-color);
          color: var(--primary-text-color);
        }
        .form-group textarea {
          resize: vertical;
          min-height: 120px;
        }
        .error-message {
          color: #ef5350;
          font-size: 12px;
          margin-top: 4px;
        }
        .actions {
          display: flex;
          gap: 8px;
          margin-top: 16px;
        }
        button {
          padding: 8px 16px;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-weight: 500;
        }
        .btn-save {
          background: var(--primary-color);
          color: white;
        }
        .btn-cancel {
          background: var(--divider-color);
          color: var(--primary-text-color);
        }
        .advanced-section {
          border-top: 1px solid var(--divider-color);
          margin-top: 16px;
          padding-top: 16px;
        }
        .advanced-header {
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 8px;
          font-weight: 500;
          margin-bottom: 12px;
        }
        .advanced-content {
          display: none;
        }
        .advanced-content.open {
          display: grid;
          gap: 16px;
        }
      </style>

      <div class="form-container">
        <!-- Basic Fields -->
        <div class="form-group">
          <label>Model Name</label>
          <input type="text" id="model-name" placeholder="Enter model name" maxlength="255">
          <div class="error-message" id="error-model-name"></div>
        </div>

        <div class="form-group">
          <label>Description</label>
          <textarea id="model-description" placeholder="Enter model description"></textarea>
          <div class="error-message" id="error-model-description"></div>
        </div>

        <div class="form-group">
          <label>Tags (comma-separated)</label>
          <input type="text" id="model-tags" placeholder="tag1, tag2, tag3">
          <div class="error-message" id="error-model-tags"></div>
        </div>

        <div class="form-group">
          <label>Collection</label>
          <input type="text" id="model-collection" placeholder="Collection name">
          <div class="error-message" id="error-model-collection"></div>
        </div>

        <!-- Advanced Fields -->
        <div class="advanced-section">
          <div class="advanced-header" id="advanced-toggle">
            <span>⚙️ Advanced Enrichment Fields</span>
            <span id="advanced-arrow">▼</span>
          </div>
          <div class="advanced-content" id="advanced-content">
            <div class="form-group">
              <label>Print Time Estimate (seconds)</label>
              <input type="number" id="enrichment-print-time" placeholder="3600" min="0">
              <div class="error-message" id="error-enrichment-print-time"></div>
            </div>

            <div class="form-group">
              <label>Support Type</label>
              <select id="enrichment-support-type">
                <option value="">None</option>
                <option value="tree">Tree Supports</option>
                <option value="linear">Linear Supports</option>
                <option value="grid">Grid Supports</option>
              </select>
            </div>

            <div class="form-group">
              <label>Difficulty Level</label>
              <select id="enrichment-difficulty">
                <option value="">Unknown</option>
                <option value="beginner">Beginner</option>
                <option value="intermediate">Intermediate</option>
                <option value="advanced">Advanced</option>
                <option value="expert">Expert</option>
              </select>
            </div>

            <div class="form-group">
              <label>Print Notes</label>
              <textarea id="enrichment-print-notes" placeholder="Additional notes about printing this model"></textarea>
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="actions">
          <button class="btn-save" id="btn-save">Save Changes</button>
          <button class="btn-cancel" id="btn-cancel">Cancel</button>
        </div>
      </div>
    `;

    this._attachEventListeners();
    this._populateForm();
  }

  _attachEventListeners() {
    document.getElementById('advanced-toggle').addEventListener('click', () => {
      const content = document.getElementById('advanced-content');
      content.classList.toggle('open');
    });

    document.getElementById('btn-save').addEventListener('click', () => this._handleSave());
    document.getElementById('btn-cancel').addEventListener('click', () => this._onCancel());
  }

  _populateForm() {
    if (this._model.name) {
      document.getElementById('model-name').value = this._model.name;
    }
    if (this._model.description) {
      document.getElementById('model-description').value = this._model.description;
    }
    if (this._model.keywords) {
      document.getElementById('model-tags').value = this._model.keywords.join(', ');
    }
    if (this._model.enrichment) {
      const enrichment = this._model.enrichment;
      if (enrichment.print_time_estimate) {
        document.getElementById('enrichment-print-time').value = enrichment.print_time_estimate;
      }
      if (enrichment.support_type_hint) {
        document.getElementById('enrichment-support-type').value = enrichment.support_type_hint;
      }
      if (enrichment.difficulty_level) {
        document.getElementById('enrichment-difficulty').value = enrichment.difficulty_level;
      }
      if (enrichment.print_notes) {
        document.getElementById('enrichment-print-notes').value = enrichment.print_notes;
      }
    }
  }

  _handleSave() {
    this._clearValidationErrors();
    this._validationErrors = {};

    // Validate
    const name = document.getElementById('model-name').value.trim();
    const description = document.getElementById('model-description').value.trim();
    const printTime = document.getElementById('enrichment-print-time').value;
    
    // Required field validation
    if (!name) {
      this._validationErrors['model-name'] = 'Model name is required';
    }
    
    // Length validation
    if (name.length > 255) {
      this._validationErrors['model-name'] = 'Model name must be 255 characters or less';
    }
    
    if (description.length > 5000) {
      this._validationErrors['model-description'] = 'Description must be 5000 characters or less';
    }
    
    // Print time validation
    if (printTime && (isNaN(parseInt(printTime)) || parseInt(printTime) < 0)) {
      this._validationErrors['enrichment-print-time'] = 'Print time must be a positive number (in seconds)';
    }

    if (Object.keys(this._validationErrors).length > 0) {
      this._displayValidationErrors();
      return;
    }

    // Build form data
    const formData = {
      model_ref: this._model.public_id || this._model.model_id,
      model_name: name,
      description: description,
      tags: document.getElementById('model-tags').value.split(',').map(t => t.trim()).filter(t => t),
      collection: document.getElementById('model-collection').value.trim() || null,
      enrichment: {
        print_time_estimate: printTime ? parseInt(printTime) : null,
        support_type_hint: document.getElementById('enrichment-support-type').value || null,
        difficulty_level: document.getElementById('enrichment-difficulty').value || null,
        print_notes: document.getElementById('enrichment-print-notes').value.trim() || null,
      },
    };

    this._onSave(formData);
  }

  _displayValidationErrors() {
    Object.entries(this._validationErrors).forEach(([field, error]) => {
      const errorEl = document.getElementById(`error-${field}`);
      if (errorEl) {
        errorEl.textContent = error;
      }
    });
  }

  _clearValidationErrors() {
    document.querySelectorAll('.error-message').forEach(el => {
      el.textContent = '';
    });
  }
}

customElements.define('model-detail-edit-form', ModelDetailEditForm);
