/**
 * Browser Source Summary Component (Right Pane) for Intake Wizard Source Step
 * 
 * Displays a synchronized, pre-filtered view of uploaded files/folders:
 * - Same tree structure as left pane (synchronized navigation)
 * - Does NOT show excluded items (pre-filtered)
 * - Shows partial indicators (⚠️) with exclusion counts
 * - Shows batch summary: "X items selected, Y excluded"
 * 
 * Part of Issue #1335: Phase D — Frontend Source Step Browser Mode
 */

class SourceBrowserSummary extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._items = [];
    this._excludedItems = new Set();
    this._currentPath = '';
    this._expandedFolders = new Set();
  }

  connectedCallback() {
    this._render();
  }

  /**
   * Set the file/folder tree data
   * @param {Array} items - Tree structure: [{ type: 'file'|'folder', name, path, children? }]
   */
  set items(items) {
    this._items = items || [];
    this._render();
  }

  /**
   * Set the list of excluded item paths
   * @param {Array<string>} excludedPaths - Paths that are excluded from import
   */
  set excludedItems(excludedPaths) {
    this._excludedItems = new Set(excludedPaths || []);
    this._render();
  }

  /**
   * Set the current navigation path (synchronized from left pane)
   * @param {string} path - Current path being viewed
   */
  set currentPath(path) {
    this._currentPath = path || '';
    this._render();
  }

  /**
   * Set which folders are expanded (synchronized from left pane)
   * @param {Set<string>} expandedPaths - Paths of expanded folders
   */
  set expandedFolders(expandedPaths) {
    this._expandedFolders = new Set(expandedPaths || []);
    this._render();
  }

  /**
   * Get total count of non-excluded items
   * @returns {number}
   */
  getIncludedCount() {
    return this._countIncludedItems(this._items);
  }

  /**
   * Get total count of excluded items
   * @returns {number}
   */
  getExcludedCount() {
    return this._excludedItems.size;
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
   * Check if a folder is marked as partial (has excluded descendants)
   * @private
   */
  _isPartialFolder(folderPath) {
    // A folder is partial if any of its descendants are excluded
    const folderPrefix = folderPath.endsWith('/') ? folderPath : folderPath + '/';
    
    for (const excludedPath of this._excludedItems) {
      if (excludedPath.startsWith(folderPrefix)) {
        return true;
      }
    }
    return false;
  }

  /**
   * Count excluded items directly in a folder
   * @private
   */
  _countExcludedInFolder(folderPath) {
    let count = 0;
    const folderPrefix = folderPath.endsWith('/') ? folderPath : folderPath + '/';
    
    for (const excludedPath of this._excludedItems) {
      if (excludedPath.startsWith(folderPrefix)) {
        // Count each excluded item in this folder
        count++;
      }
    }
    
    return count;
  }

  /**
   * Render tree node for a single item (pre-filtered - excluded items hidden)
   * @private
   */
  _renderTreeNode(item, depth = 0) {
    // Skip excluded items entirely (pre-filtered display)
    if (this._excludedItems.has(item.path)) {
      return '';
    }
    
    const isPartial = this._isPartialFolder(item.path);
    const isExpanded = this._expandedFolders.has(item.path);
    const excludedInFolder = this._countExcludedInFolder(item.path);
    
    const indent = depth * 20;
    const nodeClass = `tree-node ${isPartial ? 'partial' : ''}`;
    
    let html = `
      <div class="${nodeClass}" style="margin-left: ${indent}px;">
        <div class="tree-node-content">
    `;
    
    // Folder expand/collapse indicator (visual only - synchronized with left pane)
    if (item.type === 'folder' && item.children && item.children.length > 0) {
      const hasIncludedChildren = this._hasIncludedChildren(item.children);
      if (hasIncludedChildren) {
        html += `<span class="expand-indicator ${isExpanded ? 'expanded' : ''}">▶</span>`;
      } else {
        html += `<span class="expand-indicator-placeholder"></span>`;
      }
    } else if (item.type === 'folder') {
      html += `<span class="expand-indicator-placeholder"></span>`;
    }
    
    // File type icon
    const icon = item.type === 'folder' ? '📁' : this._getFileIcon(item.name);
    html += `<span class="icon">${icon}</span>`;
    
    // Item name
    html += `<span class="name">${this._escapeHtml(item.name)}</span>`;
    
    // Partial indicator badge (if this folder has excluded descendants)
    if (isPartial && excludedInFolder > 0) {
      html += `<span class="partial-badge" title="${excludedInFolder} items excluded">⚠️ ${excludedInFolder}</span>`;
    }
    
    // Size indicator (for files)
    if (item.type === 'file' && item.size) {
      const sizeStr = this._formatFileSize(item.size);
      html += `<span class="file-size">${sizeStr}</span>`;
    }
    
    html += `
        </div>
    `;
    
    // Render children (only if expanded and they're not excluded)
    if (item.type === 'folder' && item.children && item.children.length > 0 && isExpanded) {
      html += `<div class="children">`;
      for (const child of item.children) {
        html += this._renderTreeNode(child, depth + 1);
      }
      html += `</div>`;
    }
    
    html += `</div>`;
    
    return html;
  }

  /**
   * Check if an item has any non-excluded children
   * @private
   */
  _hasIncludedChildren(children) {
    for (const child of children) {
      if (!this._excludedItems.has(child.path)) {
        return true;
      }
      if (child.type === 'folder' && child.children && this._hasIncludedChildren(child.children)) {
        return true;
      }
    }
    return false;
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
    const totalItems = this.getIncludedCount();
    const excludedCount = this.getExcludedCount();
    
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
        
        .summary-container {
          display: flex;
          flex-direction: column;
          height: 100%;
          background: var(--background-color, #fff);
        }
        
        .batch-summary {
          padding: 12px;
          background-color: var(--info-background, #e3f2fd);
          border-bottom: 1px solid var(--divider-color, #ccc);
          font-size: 13px;
          color: var(--info-color, #1976d2);
          border-radius: 4px 4px 0 0;
        }
        
        .batch-summary strong {
          font-weight: 600;
        }
        
        .tree-container {
          flex: 1;
          overflow-y: auto;
          border: 1px solid var(--divider-color, #ccc);
          border-top: none;
          padding: 8px;
        }
        
        .tree-node {
          margin: 2px 0;
          transition: background-color 0.2s;
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
        
        .expand-indicator {
          width: 24px;
          height: 24px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          color: var(--primary-text-color, #000);
          font-size: 12px;
          transition: transform 0.2s;
        }
        
        .expand-indicator.expanded {
          transform: rotate(90deg);
        }
        
        .expand-indicator-placeholder {
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
        
        .children {
          display: block;
        }
        
        .empty-state {
          padding: 32px 16px;
          text-align: center;
          color: var(--secondary-text-color, #999);
        }
      </style>
      
      <div class="summary-container">
        <div class="batch-summary">
          <strong>${totalItems}</strong> items selected${excludedCount > 0 ? `, <strong>${excludedCount}</strong> excluded` : ''}
        </div>
        
        <div class="tree-container">
          ${treeHtml ? `<div class="tree-nodes">${treeHtml}</div>` : '<div class="empty-state">No files selected</div>'}
        </div>
      </div>
    `;
    
    this.shadowRoot.innerHTML = html;
  }
}

// Register the custom element
customElements.define('source-browser-summary', SourceBrowserSummary);
