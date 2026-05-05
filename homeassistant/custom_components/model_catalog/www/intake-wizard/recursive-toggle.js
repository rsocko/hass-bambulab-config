/**
 * Recursive Toggle Component
 * 
 * G2: Toggle component for enabling/disabling recursive selection
 * 
 * When user toggles from recursive=true to recursive=false:
 * 1. Detect subfolders under this path
 * 2. Show warning modal
 * 3. Await confirmation
 * 4. Add subfolders to excluded_items if confirmed
 */

class RecursiveToggle extends HTMLElement {
  connectedCallback() {
    this.render();
    this.addEventListener('click', (e) => this._onClick(e));
  }

  disconnectedCallback() {
    this.removeEventListener('click', this._onClick);
  }

  _onClick(e) {
    const target = e.target;
    
    if (target.classList.contains('toggle-button')) {
      this._toggleRecursive();
    }
  }

  _toggleRecursive() {
    const currentValue = this.getAttribute('recursive') === 'true';
    const newValue = !currentValue;
    const path = this.getAttribute('path');
    
    this.setAttribute('recursive', newValue ? 'true' : 'false');
    
    // Dispatch event to parent (organize-step)
    this.dispatchEvent(new CustomEvent('recursive-toggle-changed', {
      detail: {
        selection_path: path,
        new_recursive_value: newValue
      },
      bubbles: true
    }));
    
    this.render();
  }

  render() {
    const path = this.getAttribute('path');
    const isRecursive = this.getAttribute('recursive') === 'true';
    
    this.innerHTML = `
      <style>
        :host {
          --toggle-color: #1976d2;
          --toggle-bg: #e8f4fd;
        }

        .toggle-row {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 8px 0;
          font-size: 13px;
        }

        .toggle-label {
          flex: 1;
          color: #666;
          font-family: monospace;
          font-size: 12px;
          word-break: break-all;
        }

        .toggle-button {
          padding: 6px 12px;
          border: 1px solid var(--toggle-color);
          background-color: ${isRecursive ? 'var(--toggle-color)' : 'white'};
          color: ${isRecursive ? 'white' : 'var(--toggle-color)'};
          border-radius: 3px;
          cursor: pointer;
          font-size: 12px;
          font-weight: 500;
          transition: all 0.2s ease;
          min-width: 60px;
          text-align: center;
        }

        .toggle-button:hover {
          opacity: 0.8;
        }

        .toggle-button:active {
          transform: scale(0.98);
        }
      </style>

      <div class="toggle-row">
        <div class="toggle-label">${path}</div>
        <button class="toggle-button">
          ${isRecursive ? '✓ On' : 'Off'}
        </button>
      </div>
    `;
  }
}

customElements.define('recursive-toggle', RecursiveToggle);
export { RecursiveToggle };
