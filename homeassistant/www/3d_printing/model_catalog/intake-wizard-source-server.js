/**
 * Server Browser Navigation Component for Intake Wizard Source Step
 * 
 * Displays server folder hierarchy with:
 * - Folder navigation and drill-down
 * - Selection consolidation (parent absorbs children)
 * - Visual indicators for absorbed children: "(included in parent)"
 * - Removal buttons with exclusion tracking
 * - Partial indicators for folders with excluded items
 * - Large folder safeguard (>500 items)
 * 
 * Part of Issue #1336: Phase E — Frontend Source Step Server Mode
 */

class SourceServerBrowser extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._items = [];
    this._currentPath = '';
    this._selectedItems = new Set();      // Topmost selections only
    this._excludedItems = new Set();      // Items excluded from selected parents
    this._onItemSelect = null;
    this._onItemDeselect = null;
    this._onNavigate = null;
    this._onRemoveItem = null;
  }

  connectedCallback() {
    this._render();
  }

  /**
   * Set current folder contents
   * @param {Array} items - [{ type: 'file'|'folder', name, path, children?, size?, itemCount? }]
   */
  set items(items) {
    this._items = items || [];
    this._render();
  }

  /**
   * Set current navigation path
   * @param {string} path - Full path being viewed
   */
  set currentPath(path) {
    this._currentPath = path || '';
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
   * Register callback when user selects an item
   * @param {Function} callback - Called with ({ path, type })
   */
  set onItemSelect(callback) {
    this._onItemSelect = callback;
  }

  /**
   * Register callback when user deselects an item
   * @param {Function} callback - Called with (path)
   */
  set onItemDeselect(callback) {
    this._onItemDeselect = callback;
  }

  /**
   * Register callback when user navigates to folder
   * @param {Function} callback - Called with (path)
   */
  set onNavigate(callback) {
    this._onNavigate = callback;
  }

  /**
   * Register callback when user removes item (adds to exclusions)
   * @param {Function} callback - Called with (path)
   */
  set onRemoveItem(callback) {
    this._onRemoveItem = callback;
  }

  /**
   * Get current selections
   * @returns {Array<string>}
   */
  getSelectedItems() {
    return Array.from(this._selectedItems);
  }

  /**
   * Get current exclusions
   * @returns {Array<string>}
   */
  getExcludedItems() {
    return Array.from(this._excludedItems);
  }

  /**
   * Check if an item is a child of a selected parent
   * @private
   */
  _isChildOfSelection(itemPath) {
    for (const selected of this._selectedItems) {
      // Check if item is descendant of selected
      if (selected !== itemPath && itemPath.startsWith(selected.endsWith('/') ? selected : selected + '/')) {
        return true;
      }
    }
    return false;
  }

  /**
   * Get parent selection if item is absorbed
   * @private
   */
  _getParentSelection(itemPath) {
    for (const selected of this._selectedItems) {
      if (selected !== itemPath && itemPath.startsWith(selected.endsWith('/') ? selected : selected + '/')) {
        return selected;
      }
    }
    return null;
  }

  /**
   * Check if folder can be auto-expanded (< 500 items)
   * @private
   */
  _canAutoExpandFolder(itemCount) {
    return itemCount < 500;
  }

  /**
   * Get file icon based on extension
   * @private
   */
  _getFileIcon(filename) {
    const ext = filename.split('.').pop()?.toLowerCase() || '';
    const iconMap = {
      '3mf': '🔧',
      'stl': '🔧',
      'obj': '🔧',
      'gcode': '📄',
      'pdf': '📖',
      'jpg': '🖼️',
      'jpeg': '🖼️',
      'png': '🖼️',
      'txt': '📝',
    };
    return iconMap[ext] || '📄';
  }

  /**
   * Format file size for display
   * @private
   */
  _formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const index = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, index)).toFixed(1) + ' ' + units[index];
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
   * Handle checkbox change for selection
   * @private
   */
  _onSelectionChange(itemPath, itemType, isChecked, event) {
    event.stopPropagation();

    if (isChecked) {
      // Adding to selection
      this._selectedItems.add(itemPath);
      if (this._onItemSelect) {
        this._onItemSelect({ path: itemPath, type: itemType });
      }
    } else {
      // Removing from selection
      this._selectedItems.delete(itemPath);
      if (this._onItemDeselect) {
        this._onItemDeselect(itemPath);
      }
    }

    this._render();
  }

  /**
   * Handle folder drill-down
   * @private
   */
  _onFolderClick(itemPath, event) {
    event.stopPropagation();

    if (this._onNavigate) {
      this._onNavigate(itemPath);
    }
  }

  /**
   * Handle removal (add to exclusions)
   * @private
   */
  _onRemoveClick(itemPath, event) {
    event.stopPropagation();

    this._excludedItems.add(itemPath);

    if (this._onRemoveItem) {
      this._onRemoveItem(itemPath);
    }

    this._render();
  }

  /**
   * Render a single item
   * @private
   */
  _renderItem(item) {
    const isChildOfSelection = this._isChildOfSelection(item.path);
    const isSelected = this._selectedItems.has(item.path);
    const isExcluded = this._excludedItems.has(item.path);
    const parentSelection = this._getParentSelection(item.path);

    let itemHtml = `
      <div class="item ${item.type} ${isSelected ? 'selected' : ''} ${isChildOfSelection ? 'child-of-selection' : ''} ${isExcluded ? 'excluded' : ''}">
        <div class="item-content">
    `;

    if (isExcluded) {
      itemHtml += `<div class="excluded-overlay"></div>`;
    }

    // Checkbox for selection
    if (item.type === 'file') {
      itemHtml += `
        <input type="checkbox" class="item-checkbox" 
               data-path="${item.path}" 
               ${isSelected ? 'checked' : ''}
               ${isChildOfSelection ? 'disabled' : ''}
               aria-label="Select ${item.name}">
      `;
    } else {
      itemHtml += `
        <input type="checkbox" class="item-checkbox" 
               data-path="${item.path}"
               ${isSelected ? 'checked' : ''}
               ${isChildOfSelection ? 'disabled' : ''}
               aria-label="Select folder ${item.name}">
      `;
    }

    // Item icon
    const icon = item.type === 'folder' ? '📁' : this._getFileIcon(item.name);
    itemHtml += `<span class="icon">${icon}</span>`;

    // Item name
    itemHtml += `<span class="name">${this._escapeHtml(item.name)}</span>`;

    // Folder item count (if applicable)
    if (item.type === 'folder' && item.itemCount !== undefined) {
      const canExpand = this._canAutoExpandFolder(item.itemCount);
      if (!canExpand) {
        itemHtml += `<span class="item-count warning" title="Large folder (${item.itemCount} items) - use search to narrow">🚫 ${item.itemCount}+ items</span>`;
      } else {
        itemHtml += `<span class="item-count">${item.itemCount} items</span>`;
      }
    }

    // File size
    if (item.type === 'file' && item.size) {
      itemHtml += `<span class="file-size">${this._formatFileSize(item.size)}</span>`;
    }

    // Selected indicator for child items (when parent is selected)
    if (isChildOfSelection && parentSelection) {
      itemHtml += `
        <span class="child-indicator" title="Included when parent is selected. Click to exclude it from the import.">
          ✓ included in parent
        </span>
      `;
    }

    // Remove button (only if not already excluded and not child of selection)
    if (!isExcluded && !isChildOfSelection) {
      itemHtml += `
        <button class="remove-btn" 
                data-path="${item.path}"
                title="Remove from import"
                aria-label="Remove ${item.name}">
          ✕
        </button>
      `;
    }

    // Drill-down button for folders
    if (item.type === 'folder') {
      const canExpand = this._canAutoExpandFolder(item.itemCount || 0);
      itemHtml += `
        <button class="drill-down-btn"
                data-path="${item.path}"
                ${!canExpand ? 'disabled' : ''}
                title="${!canExpand ? 'Folder too large to navigate' : 'Navigate into folder'}"
                aria-label="Navigate into ${item.name}">
          ➤
        </button>
      `;
    }

    itemHtml += `
        </div>
      </div>
    `;

    return itemHtml;
  }

  /**
   * Render breadcrumb navigation
   * @private
   */
  _renderBreadcrumb() {
    if (!this._currentPath || this._currentPath === '/') {
      return '<div class="breadcrumb"><span class="path">📁 Root</span></div>';
    }

    const parts = this._currentPath.split('/').filter(p => p);
    let breadcrumb = '<div class="breadcrumb">';
    breadcrumb += '<span class="path" data-path="/">📁 Root</span>';

    let currentPath = '';
    for (const part of parts) {
      currentPath += '/' + part;
      breadcrumb += ` <span class="separator">/</span>`;
      breadcrumb += `<span class="path">${this._escapeHtml(part)}</span>`;
    }

    breadcrumb += '</div>';
    return breadcrumb;
  }

  /**
   * Render selection summary
   * @private
   */
  _renderSelectionSummary() {
    const selectedCount = this._selectedItems.size;
    const excludedCount = this._excludedItems.size;

    let summary = `<div class="selection-summary">`;
    if (selectedCount === 0) {
      summary += `<span>No items selected</span>`;
    } else {
      summary += `<strong>${selectedCount}</strong> folder${selectedCount !== 1 ? 's' : ''} selected`;
      if (excludedCount > 0) {
        summary += `, <strong>${excludedCount}</strong> item${excludedCount !== 1 ? 's' : ''} excluded`;
      }
    }
    summary += `</div>`;

    return summary;
  }

  /**
   * Main render function
   * @private
   */
  _render() {
    let itemsHtml = '';
    for (const item of this._items) {
      itemsHtml += this._renderItem(item);
    }

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

        .breadcrumb .path {
          cursor: pointer;
          color: var(--link-color, #1976d2);
          padding: 2px 4px;
          border-radius: 2px;
          transition: background-color 0.2s;
        }

        .breadcrumb .path:hover {
          background-color: rgba(25, 118, 210, 0.1);
        }

        .breadcrumb .separator {
          margin: 0 4px;
          color: var(--secondary-text-color, #999);
        }

        .selection-summary {
          padding: 8px 12px;
          background-color: var(--info-background, #e3f2fd);
          border-bottom: 1px solid var(--divider-color, #ccc);
          font-size: 13px;
          color: var(--info-color, #1976d2);
        }

        .selection-summary strong {
          font-weight: 600;
        }

        .items-container {
          flex: 1;
          overflow-y: auto;
          padding: 8px;
        }

        .item {
          display: flex;
          align-items: center;
          margin: 2px 0;
          position: relative;
        }

        .item.excluded {
          opacity: 0.5;
          pointer-events: none;
        }

        .item-content {
          display: flex;
          align-items: center;
          gap: 8px;
          width: 100%;
          padding: 6px 8px;
          border-radius: 3px;
          background-color: transparent;
          transition: background-color 0.2s;
          position: relative;
        }

        .item:hover > .item-content {
          background-color: var(--hover-background, #f5f5f5);
        }

        .item.selected > .item-content {
          background-color: var(--selection-background, #e3f2fd);
          border-left: 3px solid var(--primary-color, #1976d2);
        }

        .item.child-of-selection > .item-content {
          background-color: var(--child-selection-background, #f3f3f3);
        }

        .excluded-overlay {
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background-color: rgba(244, 67, 54, 0.1);
          border-radius: 3px;
          pointer-events: none;
        }

        .item-checkbox {
          flex-shrink: 0;
          width: 18px;
          height: 18px;
          cursor: pointer;
          accent-color: var(--primary-color, #1976d2);
        }

        .item-checkbox:disabled {
          cursor: not-allowed;
          opacity: 0.5;
        }

        .icon {
          flex-shrink: 0;
          font-size: 16px;
          min-width: 20px;
        }

        .name {
          flex: 1;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          color: var(--primary-text-color, #000);
          font-weight: 500;
        }

        .item-count {
          flex-shrink: 0;
          font-size: 12px;
          color: var(--secondary-text-color, #999);
          background-color: var(--secondary-background, #f0f0f0);
          padding: 2px 6px;
          border-radius: 2px;
        }

        .item-count.warning {
          background-color: var(--warning-background, #fff3e0);
          color: var(--warning-color, #ff9800);
        }

        .file-size {
          flex-shrink: 0;
          font-size: 12px;
          color: var(--secondary-text-color, #999);
          min-width: 60px;
          text-align: right;
        }

        .child-indicator {
          flex-shrink: 0;
          font-size: 11px;
          color: var(--secondary-text-color, #999);
          background-color: var(--secondary-background, #f0f0f0);
          padding: 2px 6px;
          border-radius: 2px;
          cursor: help;
          white-space: nowrap;
        }

        .remove-btn, .drill-down-btn {
          flex-shrink: 0;
          width: 24px;
          height: 24px;
          padding: 0;
          border: none;
          background: none;
          cursor: pointer;
          opacity: 0;
          transition: opacity 0.2s;
          font-size: 14px;
        }

        .item:hover .remove-btn {
          opacity: 1;
          color: var(--error-color, #f44336);
        }

        .item:hover .drill-down-btn {
          opacity: 1;
          color: var(--primary-color, #1976d2);
        }

        .remove-btn:hover {
          font-weight: bold;
          opacity: 1;
        }

        .drill-down-btn:hover:not(:disabled) {
          font-weight: bold;
          opacity: 1;
        }

        .drill-down-btn:disabled {
          opacity: 0.3;
          cursor: not-allowed;
        }

        .empty-state {
          padding: 32px 16px;
          text-align: center;
          color: var(--secondary-text-color, #999);
        }
      </style>

      <div class="container">
        ${this._renderBreadcrumb()}
        ${this._renderSelectionSummary()}
        
        <div class="items-container">
          ${itemsHtml || '<div class="empty-state">No items in this folder</div>'}
        </div>
      </div>
    `;

    this.shadowRoot.innerHTML = html;

    // Attach event listeners
    this._attachEventListeners();
  }

  /**
   * Attach event listeners to rendered elements
   * @private
   */
  _attachEventListeners() {
    // Selection checkboxes
    const checkboxes = this.shadowRoot.querySelectorAll('.item-checkbox');
    for (const checkbox of checkboxes) {
      const itemPath = checkbox.dataset.path;
      const itemElement = checkbox.closest('.item');
      const itemType = itemElement.classList.contains('folder') ? 'folder' : 'file';

      checkbox.addEventListener('change', (e) => {
        this._onSelectionChange(itemPath, itemType, checkbox.checked, e);
      });
    }

    // Remove buttons
    const removeButtons = this.shadowRoot.querySelectorAll('.remove-btn');
    for (const btn of removeButtons) {
      btn.addEventListener('click', (e) => this._onRemoveClick(btn.dataset.path, e));
    }

    // Drill-down buttons
    const drillDownButtons = this.shadowRoot.querySelectorAll('.drill-down-btn');
    for (const btn of drillDownButtons) {
      if (!btn.disabled) {
        btn.addEventListener('click', (e) => this._onFolderClick(btn.dataset.path, e));
      }
    }

    // Breadcrumb navigation
    const breadcrumbPaths = this.shadowRoot.querySelectorAll('.breadcrumb .path');
    for (const path of breadcrumbPaths) {
      path.addEventListener('click', (e) => {
        const navPath = path.dataset.path || '/';
        if (this._onNavigate) {
          this._onNavigate(navPath);
        }
      });
    }
  }
}

// Register the custom element
customElements.define('source-server', SourceServerBrowser);
