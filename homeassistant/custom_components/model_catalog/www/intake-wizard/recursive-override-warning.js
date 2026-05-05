/**
 * Recursive Override Warning Modal
 * 
 * G2: Warning shown when user changes from recursive=true to recursive=false
 * 
 * Shows:
 * - Count of subfolders that would be excluded
 * - List of affected subfolders
 * - Confirm/Cancel buttons
 */

class RecursiveOverrideWarning extends HTMLElement {
  connectedCallback() {
    this.addEventListener('click', (e) => this._onClick(e));
    this.addEventListener('keydown', (e) => this._onKeydown(e));
  }

  disconnectedCallback() {
    this.removeEventListener('click', this._onClick);
    this.removeEventListener('keydown', this._onKeydown);
  }

  _onClick(e) {
    const target = e.target;
    
    if (target.classList.contains('warning-confirm')) {
      this._confirm();
    } else if (target.classList.contains('warning-cancel')) {
      this._cancel();
    } else if (target.classList.contains('warning-overlay')) {
      this._cancel();
    }
  }

  _onKeydown(e) {
    if (e.key === 'Escape') {
      this._cancel();
    }
  }

  _confirm() {
    const path = this.getAttribute('selection-path');
    
    this.dispatchEvent(new CustomEvent('override-confirmed', {
      detail: { selection_path: path },
      bubbles: true
    }));
    
    this.hide();
  }

  _cancel() {
    const path = this.getAttribute('selection-path');
    
    this.dispatchEvent(new CustomEvent('override-cancelled', {
      detail: { selection_path: path },
      bubbles: true
    }));
    
    this.hide();
  }

  hide() {
    this.style.display = 'none';
  }

  show() {
    this.style.display = 'flex';
  }

  /**
   * Set warning data and show
   */
  setWarning(selectionPath, subfoldersToExclude) {
    this.setAttribute('selection-path', selectionPath);
    this.setAttribute('subfolders-count', subfoldersToExclude.length);
    
    // Store subfolders in data attribute (JSON)
    this.setAttribute('subfolders', JSON.stringify(subfoldersToExclude));
    
    this.render();
    this.show();
  }

  render() {
    const path = this.getAttribute('selection-path');
    const count = parseInt(this.getAttribute('subfolders-count') || '0', 10);
    const subfoldersJson = this.getAttribute('subfolders');
    const subfolders = subfoldersJson ? JSON.parse(subfoldersJson) : [];

    this.innerHTML = `
      <style>
        :host {
          display: none;
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          z-index: 1000;
          align-items: center;
          justify-content: center;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }

        .warning-overlay {
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background-color: rgba(0, 0, 0, 0.5);
          cursor: pointer;
        }

        .warning-modal {
          position: relative;
          z-index: 1001;
          background-color: white;
          border-radius: 6px;
          box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
          padding: 24px;
          max-width: 500px;
          max-height: 80vh;
          overflow-y: auto;
          animation: slideUp 0.3s ease;
        }

        @keyframes slideUp {
          from {
            transform: translateY(20px);
            opacity: 0;
          }
          to {
            transform: translateY(0);
            opacity: 1;
          }
        }

        .warning-icon {
          font-size: 32px;
          margin-bottom: 12px;
        }

        .warning-title {
          font-size: 16px;
          font-weight: 600;
          margin-bottom: 8px;
          color: #333;
        }

        .warning-description {
          font-size: 13px;
          color: #666;
          margin-bottom: 16px;
          line-height: 1.5;
        }

        .warning-content {
          background-color: #f5f5f5;
          border-radius: 4px;
          padding: 12px;
          margin-bottom: 16px;
        }

        .subfolders-list {
          list-style: none;
          padding: 0;
          margin: 0;
          font-size: 12px;
        }

        .subfolder-item {
          padding: 6px 0;
          color: #666;
          word-break: break-all;
          font-family: monospace;
        }

        .subfolder-item:before {
          content: '📁 ';
          margin-right: 4px;
        }

        .more-items {
          padding: 6px 0;
          color: #999;
          font-size: 11px;
          font-style: italic;
        }

        .warning-actions {
          display: flex;
          gap: 12px;
          justify-content: flex-end;
        }

        .warning-button {
          padding: 10px 16px;
          border: none;
          border-radius: 4px;
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .warning-cancel {
          background-color: #e0e0e0;
          color: #333;
        }

        .warning-cancel:hover {
          background-color: #d0d0d0;
        }

        .warning-confirm {
          background-color: #d32f2f;
          color: white;
        }

        .warning-confirm:hover {
          background-color: #c62828;
        }

        .warning-confirm:active {
          transform: scale(0.98);
        }
      </style>

      <div class="warning-overlay"></div>

      <div class="warning-modal">
        <div class="warning-icon">⚠️</div>
        <div class="warning-title">Non-Recursive Selection Impact</div>
        
        <div class="warning-description">
          Changing <strong>${path}</strong> to non-recursive mode will exclude 
          <strong>${count}</strong> subfolder${count !== 1 ? 's' : ''}:
        </div>

        <div class="warning-content">
          <ul class="subfolders-list">
            ${subfolders.slice(0, 10).map(folder => `
              <li class="subfolder-item">${folder}</li>
            `).join('')}
            ${subfolders.length > 10 ? `
              <li class="more-items">... and ${subfolders.length - 10} more</li>
            ` : ''}
          </ul>
        </div>

        <div class="warning-description">
          These items will be added to the exclusion list and won't be imported.
        </div>

        <div class="warning-actions">
          <button class="warning-button warning-cancel">Cancel</button>
          <button class="warning-button warning-confirm">Apply Non-Recursive</button>
        </div>
      </div>
    `;
  }
}

customElements.define('recursive-override-warning', RecursiveOverrideWarning);
export { RecursiveOverrideWarning };
