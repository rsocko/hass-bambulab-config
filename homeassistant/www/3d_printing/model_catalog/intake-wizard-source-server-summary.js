/**
 * Server Source Summary Component (Right Pane) for Intake Wizard Source Step
 * 
 * Displays server-mode source step summary:
 * - Shows only topmost selected entries (consolidated)
 * - Breadcrumb navigation synchronized with left pane
 * - "Part of: /" indicator when viewing subfolder
 * - Batch summary: "X folders selected, Y excluded"
 * - Pre-filtered view (no excluded items shown)
 * 
 * Part of Issue #1336: Phase E — Frontend Source Step Server Mode
 */

class SourceServerSummary extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._selectedItems = new Set();
    this._excludedItems = new Set();
    this._currentPath = '';
  }

  connectedCallback() {
    this._render();
  }

  /**
   * Set topmost selected items (consolidated - no children)
   * @param {Array<string>} selectedPaths - Paths of selected items
   */
  set selectedItems(selectedPaths) {
    this._selectedItems = new Set(selectedPaths || []);
    this._render();
  }

  /**
   * Set excluded items (items removed from selected parents)
   * @param {Array<string>} excludedPaths - Paths of excluded items
   */
  set excludedItems(excludedPaths) {
    this._excludedItems = new Set(excludedPaths || []);
    this._render();
  }

  /**
   * Set current navigation path (synchronized from left pane)
   * @param {string} path - Current path being viewed
   */
  set currentPath(path) {
    this._currentPath = path || '/';
    this._render();
  }

  /**
   * Get total count of selected items
   * @returns {number}
   */
  getSelectedCount() {
    return this._selectedItems.size;
  }

  /**
   * Get total count of excluded items
   * @returns {number}
   */
  getExcludedCount() {
    return this._excludedItems.size;
  }

  /**
   * Check if current path is a child of any selected item
   * @private
   */
  _getCurrentPathParent() {
    for (const selected of this._selectedItems) {
      const selectedPath = selected.endsWith('/') ? selected : selected + '/';
      const currentPath = this._currentPath.endsWith('/') ? this._currentPath : this._currentPath + '/';
      
      if (currentPath.startsWith(selectedPath) && selected !== this._currentPath) {
        return selected;
      }
    }
    return null;
  }

  /**
   * Get folder name from path
   * @private
   */
  _getFolderName(path) {
    const parts = path.split('/').filter(p => p);
    return parts.length > 0 ? parts[parts.length - 1] : 'Root';
  }

  /**
   * Count excluded items in a selected entry
   * @private
   */
  _countExcludedInSelection(selectedPath) {
    const selectedPrefix = selectedPath.endsWith('/') ? selectedPath : selectedPath + '/';
    let count = 0;
    
    for (const excluded of this._excludedItems) {
      if (excluded.startsWith(selectedPrefix)) {
        count++;
      }
    }
    
    return count;
  }

  /**
   * Escape HTML to prevent XSS
   * @private
   */
  _escapeHtml(text) {
    const map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;',
    };
    return text.replace(/[&<>"']/g, c => map[c]);
  }

  /**
   * Render breadcrumb navigation
   * @private
   */
  _renderBreadcrumb() {
    if (!this._currentPath || this._currentPath === '/') {
      return '<div class="breadcrumb"><span class="path-item">📁 Root</span></div>';
    }

    const parts = this._currentPath.split('/').filter(p => p);
    let breadcrumb = '<div class="breadcrumb">';
    breadcrumb += '<span class="path-item">📁 Root</span>';

    for (const part of parts) {
      breadcrumb += ` <span class="separator">/</span>`;
      breadcrumb += `<span class="path-item">${this._escapeHtml(part)}</span>`;
    }

    breadcrumb += '</div>';
    return breadcrumb;
  }

  /**
   * Render location indicator if viewing subfolder of selection
   * @private
   */
  _renderLocationIndicator() {
    const parent = this._getCurrentPathParent();
    if (!parent) {
      return '';
    }

    const parentName = this._escapeHtml(this._getFolderName(parent));
    return `
      <div class="location-indicator">
        📍 Part of: <strong>${parentName}</strong>
      </div>
    `;
  }

  /**
   * Render selected entries list
   * @private
   */
  _renderSelectedEntries() {
    if (this._selectedItems.size === 0) {
      return '<div class="no-selections">No folders selected</div>';
    }

    let html = '<div class="selected-list">';

    for (const selectedPath of this._selectedItems) {
      const folderName = this._escapeHtml(this._getFolderName(selectedPath));
      const excludedCount = this._countExcludedInSelection(selectedPath);

      html += `
        <div class="selected-entry">
          <div class="entry-header">
            <span class="folder-icon">📁</span>
            <span class="folder-name">${folderName}</span>
          </div>
          ${excludedCount > 0 ? `
            <div class="exclusion-info">
              <span class="badge">⚠️ ${excludedCount} item${excludedCount !== 1 ? 's' : ''} excluded</span>
            </div>
          ` : ''}
        </div>
      `;
    }

    html += '</div>';
    return html;
  }

  /**
   * Render batch summary
   * @private
   */
  _renderBatchSummary() {
    const selectedCount = this._selectedItems.size;
    const excludedCount = this._excludedItems.size;

    let summary = '<div class="batch-summary">';
    
    if (selectedCount === 0) {
      summary += '<span>No folders selected</span>';
    } else {
      summary += `<strong>${selectedCount}</strong> folder${selectedCount !== 1 ? 's' : ''} selected`;
      if (excludedCount > 0) {
        summary += `, <strong>${excludedCount}</strong> item${excludedCount !== 1 ? 's' : ''} excluded`;
      }
    }

    summary += '</div>';
    return summary;
  }

  /**
   * Main render function
   * @private
   */
  _render() {
    const html = `
      <style>
        :host {
          display: block;
          font-family: var(--mdc-typography-font-family, Roboto, sans-serif);
          font-size: 14px;
        }

        .container {
          display: flex;
          flex-direction: column;
          height: 100%;
          background: var(--background-color, #fff);
        }

        .breadcrumb {
          padding: 8px 12px;
          background-color: var(--breadcrumb-background, #f5f5f5);
          border-bottom: 1px solid var(--divider-color, #eee);
          font-size: 13px;
          overflow-x: auto;
          white-space: nowrap;
        }

        .breadcrumb .path-item {
          color: var(--primary-text-color, #000);
          padding: 2px 4px;
        }

        .breadcrumb .separator {
          margin: 0 4px;
          color: var(--secondary-text-color, #999);
        }

        .location-indicator {
          padding: 8px 12px;
          background-color: var(--info-background, #e3f2fd);
          border-bottom: 1px solid var(--divider-color, #ccc);
          font-size: 13px;
          color: var(--info-color, #1976d2);
        }

        .location-indicator strong {
          font-weight: 600;
        }

        .batch-summary {
          padding: 8px 12px;
          background-color: var(--info-background, #e3f2fd);
          border-bottom: 1px solid var(--divider-color, #ccc);
          font-size: 13px;
          color: var(--info-color, #1976d2);
        }

        .batch-summary strong {
          font-weight: 600;
        }

        .content {
          flex: 1;
          overflow-y: auto;
          padding: 12px;
        }

        .selected-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .selected-entry {
          padding: 8px 12px;
          border: 1px solid var(--divider-color, #ddd);
          border-radius: 4px;
          background-color: var(--card-background, #fafafa);
          transition: background-color 0.2s;
        }

        .selected-entry:hover {
          background-color: var(--hover-background, #f5f5f5);
        }

        .entry-header {
          display: flex;
          align-items: center;
          gap: 8px;
          font-weight: 500;
          color: var(--primary-text-color, #000);
          margin-bottom: 6px;
        }

        .folder-icon {
          font-size: 16px;
        }

        .folder-name {
          flex: 1;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .exclusion-info {
          display: flex;
          gap: 4px;
          font-size: 12px;
          color: var(--secondary-text-color, #666);
          margin-top: 6px;
          padding-top: 6px;
          border-top: 1px solid var(--divider-color, #eee);
        }

        .badge {
          display: inline-flex;
          align-items: center;
          gap: 2px;
          padding: 2px 6px;
          background-color: var(--warning-background, #fff3e0);
          color: var(--warning-color, #ff9800);
          border-radius: 10px;
          font-weight: 500;
        }

        .no-selections {
          padding: 32px 16px;
          text-align: center;
          color: var(--secondary-text-color, #999);
        }
      </style>

      <div class="container">
        ${this._renderBreadcrumb()}
        ${this._renderLocationIndicator()}
        ${this._renderBatchSummary()}
        
        <div class="content">
          ${this._renderSelectedEntries()}
        </div>
      </div>
    `;

    this.shadowRoot.innerHTML = html;
  }
}

// Register the custom element
customElements.define('source-server-summary', SourceServerSummary);
