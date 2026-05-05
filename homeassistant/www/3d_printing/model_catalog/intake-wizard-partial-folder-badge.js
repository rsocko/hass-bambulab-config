/**
 * Partial Folder Badge Component
 * 
 * Displays a badge showing folder has excluded items:
 * - Renders as: 📁 folder/ ⚠️ N items excluded
 * - Includes tooltip explaining the exclusion count
 * - Used in both Browser and Server source step modes
 * 
 * Part of Issue #1336: Phase E — Frontend Source Step Server Mode
 */

class PartialFolderBadge extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._folderPath = '';
    this._excludedCount = 0;
    this._format = 'badge'; // 'badge' or 'section'
  }

  connectedCallback() {
    this._render();
  }

  /**
   * Set the folder path being described
   * @param {string} folderPath - Full path to folder
   */
  set folderPath(folderPath) {
    this._folderPath = folderPath || '';
    this._render();
  }

  /**
   * Set the count of excluded items in this folder
   * @param {number} count - Number of excluded items
   */
  set excludedCount(count) {
    this._excludedCount = count || 0;
    this._render();
  }

  /**
   * Set the display format
   * @param {string} format - 'badge' (inline) or 'section' (block display)
   */
  set format(format) {
    this._format = format || 'badge';
    this._render();
  }

  /**
   * Get the folder name from path
   * @private
   */
  _getFolderName() {
    const parts = this._folderPath.split('/').filter(p => p);
    return parts.length > 0 ? parts[parts.length - 1] : 'Root';
  }

  /**
   * Get tooltip text explaining the exclusion count
   * @private
   */
  _getTooltipText() {
    if (this._excludedCount === 0) {
      return 'No items excluded';
    }
    if (this._excludedCount === 1) {
      return '1 item excluded from this folder';
    }
    return `${this._excludedCount} items excluded from this folder. Subfolders may also have exclusions.`;
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
   * Render badge format (inline)
   * @private
   */
  _renderBadge() {
    const folderName = this._escapeHtml(this._getFolderName());
    const tooltip = this._escapeHtml(this._getTooltipText());

    if (this._excludedCount === 0) {
      return `
        <span class="badge empty" title="${tooltip}">
          📁 ${folderName} <span class="indicator">✓ clean</span>
        </span>
      `;
    }

    return `
      <span class="badge partial" title="${tooltip}">
        📁 ${folderName} <span class="warning-badge">⚠️ ${this._excludedCount}</span>
      </span>
    `;
  }

  /**
   * Render section format (block display)
   * @private
   */
  _renderSection() {
    const folderName = this._escapeHtml(this._getFolderName());
    const tooltip = this._escapeHtml(this._getTooltipText());

    if (this._excludedCount === 0) {
      return `
        <div class="section empty">
          <div class="section-header">
            📁 <strong>${folderName}</strong>
          </div>
          <div class="section-content">
            <span class="indicator">No items excluded</span>
          </div>
        </div>
      `;
    }

    return `
      <div class="section partial">
        <div class="section-header">
          📁 <strong>${folderName}</strong>
          <span class="warning-badge" title="${tooltip}">⚠️ ${this._excludedCount} excluded</span>
        </div>
        <div class="section-content">
          <p class="explanation">This folder has ${this._excludedCount} item${this._excludedCount !== 1 ? 's' : ''} excluded. 
          ${this._excludedCount > 1 ? 'Subfolders may also have exclusions.' : ''}</p>
        </div>
      </div>
    `;
  }

  /**
   * Main render function
   * @private
   */
  _render() {
    const html = `
      <style>
        :host {
          display: inline-block;
          font-family: var(--mdc-typography-font-family, Roboto, sans-serif);
          font-size: 14px;
        }

        .badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 4px 8px;
          border-radius: 4px;
          white-space: nowrap;
          background-color: var(--badge-background, #f5f5f5);
          color: var(--primary-text-color, #000);
          border: 1px solid var(--divider-color, #ddd);
          transition: background-color 0.2s;
        }

        .badge.partial {
          background-color: var(--warning-background, #fff3e0);
          border-color: var(--warning-color, #ff9800);
          color: var(--primary-text-color, #000);
        }

        .badge.empty {
          background-color: var(--success-background, #e8f5e9);
          border-color: var(--success-color, #4caf50);
        }

        .indicator {
          font-size: 12px;
          color: var(--secondary-text-color, #999);
          font-style: italic;
        }

        .badge.empty .indicator {
          color: var(--success-color, #4caf50);
          font-weight: 500;
        }

        .warning-badge {
          display: inline-flex;
          align-items: center;
          gap: 2px;
          padding: 2px 6px;
          background-color: rgba(255, 152, 0, 0.15);
          color: var(--warning-color, #ff9800);
          border-radius: 10px;
          font-size: 12px;
          font-weight: 600;
          white-space: nowrap;
        }

        .section {
          padding: 8px 12px;
          border-radius: 4px;
          background-color: var(--section-background, #fafafa);
          border: 1px solid var(--divider-color, #eee);
          margin: 4px 0;
        }

        .section.partial {
          background-color: var(--warning-background, #fff3e0);
          border-color: var(--warning-color, #ff9800);
        }

        .section.empty {
          background-color: var(--success-background, #e8f5e9);
          border-color: var(--success-color, #4caf50);
        }

        .section-header {
          display: flex;
          align-items: center;
          gap: 8px;
          font-weight: 500;
          color: var(--primary-text-color, #000);
          margin-bottom: 6px;
        }

        .section-header strong {
          font-weight: 600;
        }

        .section-content {
          font-size: 13px;
          color: var(--secondary-text-color, #666);
          line-height: 1.4;
        }

        .explanation {
          margin: 0;
          padding: 0;
        }
      </style>

      ${this._format === 'section' ? this._renderSection() : this._renderBadge()}
    `;

    this.shadowRoot.innerHTML = html;
  }
}

// Register the custom element
customElements.define('partial-folder-badge', PartialFolderBadge);
