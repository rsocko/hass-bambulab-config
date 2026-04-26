/**
 * Intake Browser Card — File/folder browser for intake queue
 * 
 * Displays hierarchical file browser with allowlist path navigation.
 * Supports single file/folder selection and batch selection.
 * 
 * Usage:
 * - type: custom:intake-browser-card
 *   entity: input_text.intake_browse_path  # optional, for state binding
 *   sidecar_base_url: "http://localhost:8314"  # optional, defaults to env
 *   allow_batch_select: true  # optional, enable multi-select
 *   on_select: null  # optional, callback when item selected
 */

(async () => {
  // Lightweight browser card for intake queue file/folder selection
  const CARD_NAME = 'intake-browser-card';
  
  if (customElements.get(CARD_NAME)) return;
  
  const LitElement = customElements.get('lit-element') || customElements.get('ha-card');
  const html = LitElement.prototype.html || (() => null);
  const css = LitElement.prototype.css || (() => null);
  
  class IntakeBrowserCard extends LitElement {
    static get properties() {
      return {
        hass: { type: Object },
        config: { type: Object },
        _browsePath: { type: String, state: true },
        _entries: { type: Array, state: true },
        _selected: { type: Set, state: true },
        _loading: { type: Boolean, state: true },
        _error: { type: String, state: true },
      };
    }
    
    constructor() {
      super();
      this._browsePath = '/';
      this._entries = [];
      this._selected = new Set();
      this._loading = false;
      this._error = null;
    }
    
    setConfig(config) {
      this.config = config;
    }
    
    async updated(changedProps) {
      if (changedProps.has('hass') && this.config?.entity) {
        const path = this.hass.states[this.config.entity]?.state;
        if (path && path !== this._browsePath) {
          this._browsePath = path;
          await this._loadBrowse();
        }
      }
    }
    
    async _loadBrowse() {
      this._loading = true;
      this._error = null;
      try {
        const baseUrl = this.config?.sidecar_base_url || 'http://localhost:8314';
        const response = await fetch(
          `${baseUrl}/api/intake/browse?path=${encodeURIComponent(this._browsePath)}`
        );
        
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.error || `HTTP ${response.status}`);
        }
        
        const data = await response.json();
        if (data.success) {
          this._entries = data.entries || [];
          this._updatePathState();
        } else {
          this._error = data.error || 'Browse failed';
        }
      } catch (err) {
        this._error = `Failed to load: ${err.message}`;
      } finally {
        this._loading = false;
      }
    }
    
    async _navigateTo(path) {
      this._browsePath = path;
      await this._loadBrowse();
    }
    
    async _handleEntryClick(entry) {
      if (entry.type === 'folder') {
        await this._navigateTo(entry.path);
      } else {
        this._selected.has(entry.path)
          ? this._selected.delete(entry.path)
          : this._selected.add(entry.path);
        this.requestUpdate();
      }
    }
    
    _updatePathState() {
      if (this.hass && this.config?.entity) {
        this.hass.callService('input_text', 'set_value', {
          entity_id: this.config.entity,
          value: this._browsePath,
        });
      }
    }
    
    render() {
      return html`
        <ha-card>
          <div class="card-content">
            <div class="breadcrumb">
              ${this._renderBreadcrumb()}
            </div>
            
            ${this._loading
              ? html`<p class="loading">Loading...</p>`
              : this._error
              ? html`<p class="error">⚠️ ${this._error}</p>`
              : html`
                  <div class="entries">
                    ${this._entries.map(
                      (entry) => html`
                        <div
                          class="entry ${entry.type} ${this._selected.has(entry.path) ? 'selected' : ''}"
                          @click=${() => this._handleEntryClick(entry)}
                        >
                          <span class="icon">
                            ${entry.type === 'folder' ? '📁' : this._getFileIcon(entry.extension)}
                          </span>
                          <span class="name">${entry.name}</span>
                          ${entry.type === 'file'
                            ? html`<span class="size">${this._formatSize(entry.size_bytes)}</span>`
                            : html`<span class="count">${entry.entry_count || 0} items</span>`}
                        </div>
                      `
                    )}
                  </div>
                `}
          </div>
        </ha-card>
      `;
    }
    
    _renderBreadcrumb() {
      const parts = this._browsePath.split('/').filter(p => p);
      return html`
        <span class="breadcrumb-item" @click=${() => this._navigateTo('/')}>🏠 Root</span>
        ${parts.map(
          (part, idx) => html`
            <span class="separator">/</span>
            <span
              class="breadcrumb-item"
              @click=${() => this._navigateTo('/' + parts.slice(0, idx + 1).join('/'))}
            >
              ${part}
            </span>
          `
        )}
      `;
    }
    
    _getFileIcon(ext) {
      const icons = {
        '.3mf': '🔷',
        '.stl': '⬜',
        '.gcode': '📄',
        '.pdf': '📕',
      };
      return icons[ext?.toLowerCase()] || '📄';
    }
    
    _formatSize(bytes) {
      if (!bytes) return '';
      const units = ['B', 'KB', 'MB', 'GB'];
      let size = bytes;
      let unit = 0;
      while (size >= 1024 && unit < units.length - 1) {
        size /= 1024;
        unit++;
      }
      return `${size.toFixed(1)} ${units[unit]}`;
    }
    
    static get styles() {
      return css`
        .card-content {
          padding: 16px;
        }
        
        .breadcrumb {
          margin-bottom: 16px;
          padding: 8px 12px;
          background: rgba(0, 0, 0, 0.05);
          border-radius: 4px;
          font-size: 0.875rem;
        }
        
        .breadcrumb-item {
          cursor: pointer;
          padding: 0 4px;
        }
        
        .breadcrumb-item:hover {
          text-decoration: underline;
        }
        
        .separator {
          margin: 0 4px;
          opacity: 0.5;
        }
        
        .entries {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        
        .entry {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px;
          border: 1px solid rgba(0, 0, 0, 0.12);
          border-radius: 4px;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .entry:hover {
          background: rgba(0, 0, 0, 0.04);
          border-color: rgba(0, 0, 0, 0.2);
        }
        
        .entry.selected {
          background: rgba(25, 118, 210, 0.1);
          border-color: #1976D2;
        }
        
        .icon {
          font-size: 1.5rem;
          width: 24px;
          text-align: center;
        }
        
        .name {
          flex: 1;
          font-weight: 500;
        }
        
        .size,
        .count {
          font-size: 0.75rem;
          opacity: 0.7;
        }
        
        .loading,
        .error {
          padding: 16px;
          text-align: center;
        }
        
        .error {
          color: #D32F2F;
          font-weight: 500;
        }
      `;
    }
  }
  
  customElements.define(CARD_NAME, IntakeBrowserCard);
})();
