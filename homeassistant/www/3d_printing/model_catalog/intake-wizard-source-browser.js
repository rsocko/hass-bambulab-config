/**
 * Browser File Tree Helper for Intake Wizard Source Step
 * 
 * Pure functions for rendering and managing:
 * - Uploaded files/folders in tree structure
 * - Remove buttons [X] for each item
 * - Partial indicators (⚠️) showing exclusion counts
 * 
 * Part of Issue #1335: Phase D — Frontend Source Step Browser Mode
 */

/**
 * Compute partial indicators: folders that contain excluded items
 * @param {Array<string>} excludedPaths - Full paths of excluded items
 * @returns {Map} path => true for partial folders
 */
function computePartialIndicators(excludedPaths) {
  const partialIndicators = new Map();
  
  if (!excludedPaths || excludedPaths.length === 0) {
    return partialIndicators;
  }

  // For each excluded item, mark its parent and ancestors as partial
  for (const excludedPath of excludedPaths) {
    // Extract parent path from excluded item
    const pathParts = excludedPath.split('/').filter(p => p);
    
    // Mark each ancestor as partial (cascade upward)
    for (let i = 1; i < pathParts.length; i++) {
      const ancestorPath = '/' + pathParts.slice(0, i).join('/');
      partialIndicators.set(ancestorPath, true);
    }
  }
  
  return partialIndicators;
}

  /**
   * Set the file/folder tree data
   * @param {Array} items - Tree structure: [{ type: 'file'|'folder', name, path, children?, size?, modifiedAt? }]
   */
  set items(items) {
    this._items = items || [];
    this._computePartialIndicators();
    this._render();
  }

  /**
   * Set the list of excluded item paths
   * @param {Array<string>} excludedPaths - Full paths of excluded items
   */
  set excludedItems(excludedPaths) {
    this._excludedItems = new Set(excludedPaths || []);
    this._computePartialIndicators();
    this._render();
  }

  /**
   * Register callback when user removes an item
   * @param {Function} callback - Called with (path: string) when item is removed
   */
  set onRemoveItem(callback) {
    this._onRemoveItem = callback;
  }

  /**
   * Register callback for state changes (tree expansion, selection changes)
   * @param {Function} callback - Called with { type: 'remove'|'expand', path, state }
   */
  set onStateChange(callback) {
    this._onStateChange = callback;
  }

  /**
   * Get current count of excluded items
   * @returns {number}
   */
  getExcludedCount() {
    return this._excludedItems.size;
  }

  /**
   * Get current count of non-excluded items
   * @returns {number}
   */
  getIncludedCount() {
    return this._countIncludedItems(this._items);
  }

  /**
   * Compute partial indicators: folders that contain excluded items
   * A folder is "partial" if any of its descendants are excluded
   * Marks the folder and all ancestors as partial
   * @private
   */
  _computePartialIndicators() {
    this._partialIndicators.clear();
    
    if (this._excludedItems.size === 0) {
      return;
    }

    // For each excluded item, mark its parent and ancestors as partial
    for (const excludedPath of this._excludedItems) {
      // Extract parent path from excluded item
      const pathParts = excludedPath.split('/').filter(p => p);
      
      // Mark each ancestor as partial (cascade upward)
      for (let i = 1; i < pathParts.length; i++) {
        const ancestorPath = '/' + pathParts.slice(0, i).join('/');
        this._partialIndicators.set(ancestorPath, true);
      }
    }
  }

  /**
   * Count non-excluded items recursively
   * @private
   */
  _countIncludedItems(items) {
    let count = 0;
    for (const item of items) {
      if (!this._excludedItems.has(item.path)) {
        count++;
        if (item.children) {
          count += this._countIncludedItems(item.children);
        }
      }
    }
    return count;
  }

  /**
   * Handle remove button click
   * @private
   */
  _onRemoveClick(path, event) {
    event.stopPropagation();
    
    if (this._onRemoveItem) {
      this._onRemoveItem(path);
    }
    
    if (this._onStateChange) {
      this._onStateChange({ type: 'remove', path });
    }
  }

  /**
   * Handle folder expand/collapse toggle
   * @private
   */
  _onToggleExpand(path, event) {
    event.stopPropagation();
    
    const element = event.currentTarget;
    element.classList.toggle('expanded');
    
    if (this._onStateChange) {
      const isExpanded = element.classList.contains('expanded');
      this._onStateChange({ type: 'expand', path, isExpanded });
    }
  }

  /**
   * Render tree node for a single item
   * @private
   */
  _renderTreeNode(item, depth = 0) {
    const isExcluded = this._excludedItems.has(item.path);
    const isPartial = this._partialIndicators.has(item.path);
    const excludedInFolder = this._countExcludedInFolder(item.path);
    
    const indent = depth * 20;
    const nodeClass = `tree-node ${isExcluded ? 'excluded' : ''} ${isPartial ? 'partial' : ''}`;
    const itemType = item.type === 'folder' ? 'folder' : 'file';
    
    let html = `
      <div class="${nodeClass}" style="margin-left: ${indent}px;">
        <div class="tree-node-content">
    `;
    
    // Folder expand/collapse toggle
    if (item.type === 'folder' && item.children && item.children.length > 0) {
      html += `
        <button class="expand-toggle" aria-label="Toggle folder" data-path="${item.path}">
          <span class="arrow">▶</span>
        </button>
      `;
    } else if (item.type === 'folder') {
      html += `<span class="expand-toggle-placeholder"></span>`;
    }
    
    // File type icon
    const icon = item.type === 'folder' ? '📁' : this._getFileIcon(item.name);
    html += `<span class="icon">${icon}</span>`;
    
    // Item name
    html += `<span class="name">${this._escapeHtml(item.name)}</span>`;
    
    // Partial indicator badge
    if (isPartial && excludedInFolder > 0) {
      html += `<span class="partial-badge" title="${excludedInFolder} items excluded">⚠️ ${excludedInFolder}</span>`;
    }
    
    // Size indicator (for files)
    if (item.type === 'file' && item.size) {
      const sizeStr = this._formatFileSize(item.size);
      html += `<span class="file-size">${sizeStr}</span>`;
    }
    
    // Remove button
    if (!isExcluded) {
      html += `
        <button class="remove-btn" title="Remove from import" aria-label="Remove ${item.name}" data-path="${item.path}">
          ✕
        </button>
      `;
    }
    
    html += `
        </div>
    `;
    
    // Render children (hidden by default, shown when expanded)
    if (item.type === 'folder' && item.children && item.children.length > 0) {
      html += `<div class="children">`;
      for (const child of item.children) {
        // Skip excluded items in tree display (pre-filtered)
        if (!this._excludedItems.has(child.path)) {
          html += this._renderTreeNode(child, depth + 1);
        }
      }
      html += `</div>`;
    }
    
    html += `</div>`;
    
    return html;
  }

  /**
   * Count excluded items directly in a folder (not descendants)
   * @private
   */
  _countExcludedInFolder(folderPath) {
    let count = 0;
    const folderPrefix = folderPath.endsWith('/') ? folderPath : folderPath + '/';
    
    for (const excludedPath of this._excludedItems) {
      if (excludedPath.startsWith(folderPrefix)) {
        // Only count direct children, not nested descendants
        const relative = excludedPath.substring(folderPrefix.length);
        if (!relative.includes('/')) {
          count++;
        }
      }
    }
    
    return count;
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
   * Main render function
   * @private
   */
  _render() {
    const totalItems = this._items.length;
    const includedItems = this.getIncludedCount();
    const excludedItems = this.getExcludedCount();
    
    let treeHtml = '';
    for (const item of this._items) {
      treeHtml += this._renderTreeNode(item);
    }
    
    const html = `
      <style>
        :host {
          display: block;
          font-family: var(--mdc-typography-font-family, Roboto, sans-serif);
          font-size: 14px;
        }
        
        .tree-container {
          max-height: 500px;
          overflow-y: auto;
          border: 1px solid var(--divider-color, #ccc);
          border-radius: 4px;
          padding: 8px;
          background: var(--background-color, #fff);
        }
        
        .summary {
          padding: 8px 0;
          font-size: 13px;
          color: var(--secondary-text-color, #666);
          border-bottom: 1px solid var(--divider-color, #eee);
          margin-bottom: 8px;
        }
        
        .tree-node {
          margin: 2px 0;
          transition: background-color 0.2s;
        }
        
        .tree-node.excluded {
          display: none;
        }
        
        .tree-node-content {
          display: flex;
          align-items: center;
          gap: 4px;
          padding: 4px;
          border-radius: 2px;
          cursor: default;
        }
        
        .tree-node:hover > .tree-node-content {
          background-color: var(--hover-background, #f5f5f5);
        }
        
        .expand-toggle {
          width: 24px;
          height: 24px;
          padding: 0;
          border: none;
          background: none;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--primary-text-color, #000);
          transition: transform 0.2s;
        }
        
        .expand-toggle.expanded .arrow {
          transform: rotate(90deg);
        }
        
        .expand-toggle-placeholder {
          width: 24px;
          height: 24px;
          display: inline-block;
        }
        
        .icon {
          font-size: 16px;
          min-width: 20px;
        }
        
        .name {
          flex: 1;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          color: var(--primary-text-color, #000);
        }
        
        .tree-node.partial > .tree-node-content .name {
          font-weight: 500;
          color: var(--warning-color, #ff9800);
        }
        
        .partial-badge {
          display: inline-flex;
          align-items: center;
          gap: 2px;
          padding: 2px 6px;
          background-color: var(--warning-background, #fff3e0);
          color: var(--warning-color, #ff9800);
          border-radius: 12px;
          font-size: 11px;
          font-weight: 500;
          white-space: nowrap;
        }
        
        .file-size {
          font-size: 12px;
          color: var(--secondary-text-color, #999);
          min-width: 50px;
          text-align: right;
        }
        
        .remove-btn {
          width: 24px;
          height: 24px;
          padding: 0;
          border: none;
          background: none;
          color: var(--error-color, #f44336);
          cursor: pointer;
          opacity: 0.5;
          transition: opacity 0.2s;
          display: none;
        }
        
        .tree-node-content:hover .remove-btn {
          display: block;
          opacity: 1;
        }
        
        .remove-btn:hover {
          opacity: 1;
          font-weight: bold;
        }
        
        .children {
          display: none;
        }
        
        .expand-toggle.expanded ~ .children {
          display: block;
        }
        
        .empty-state {
          padding: 16px;
          text-align: center;
          color: var(--secondary-text-color, #999);
        }
      </style>
      
      <div class="tree-container">
        <div class="summary">
          ${totalItems} items selected
          ${excludedItems > 0 ? `, <strong>${excludedItems}</strong> excluded` : ''}
        </div>
        
        ${treeHtml ? `<div class="tree-nodes">${treeHtml}</div>` : '<div class="empty-state">No files uploaded yet</div>'}
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
    // Expand/collapse toggle
    const expandToggles = this.shadowRoot.querySelectorAll('.expand-toggle');
    for (const toggle of expandToggles) {
      toggle.addEventListener('click', (e) => this._onToggleExpand(toggle.dataset.path, e));
    }
    
    // Remove button
    const removeButtons = this.shadowRoot.querySelectorAll('.remove-btn');
    for (const btn of removeButtons) {
      btn.addEventListener('click', (e) => this._onRemoveClick(btn.dataset.path, e));
    }
  }
}

// Register the custom element
customElements.define('source-browser', SourceBrowserFileTree);
