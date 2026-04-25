/**
 * Model Detail 3D Viewer Tab Component
 * 
 * Displays 3D model geometry (STL/3MF) using Three.js
 * Part of Phase 3.2 implementation.
 * 
 * Features:
 *   - STL/3MF rendering
 *   - Build volume visualization
 *   - Rotation, zoom, pan controls
 *   - File selector for multi-file models
 *   - Layer coloring (optional)
 */

class ModelDetail3DViewerTab extends HTMLElement {
  constructor() {
    super();
    this._scene = null;
    this._camera = null;
    this._renderer = null;
    this._model = null;
    this._geometry = null;
    this._files = [];
    this._selectedFileIndex = 0;
    this._threejsLoaded = false;
  }

  async connectedCallback() {
    await this._loadThreeJs();
    this._render();
  }

  async _loadThreeJs() {
    if (window.THREE) {
      this._threejsLoaded = true;
      return;
    }

    return new Promise((resolve) => {
      const script = document.createElement('script');
      script.src = 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js';
      script.onload = () => {
        this._threejsLoaded = true;
        resolve();
      };
      document.head.appendChild(script);
    });
  }

  _render() {
    this.innerHTML = `
      <style>
        .viewer-container {
          display: flex;
          flex-direction: column;
          gap: 12px;
          padding: 16px;
          background: var(--card-background-color);
        }

        .viewer-toolbar {
          display: flex;
          gap: 8px;
          align-items: center;
          flex-wrap: wrap;
        }

        .file-selector {
          display: flex;
          gap: 8px;
          align-items: center;
        }

        .file-selector select {
          padding: 6px 12px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
        }

        .viewer-controls {
          display: flex;
          gap: 6px;
        }

        .viewer-controls button {
          padding: 6px 12px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          cursor: pointer;
          font-size: 12px;
        }

        .viewer-controls button:hover {
          background: var(--divider-color);
        }

        #canvas-container {
          width: 100%;
          height: 500px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          background: #1a1a1a;
          position: relative;
        }

        .viewer-info {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 12px;
          padding: 12px;
          background: rgba(0, 0, 0, 0.1);
          border-radius: 4px;
          font-size: 12px;
        }

        .info-item {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .info-label {
          font-weight: 500;
          color: var(--secondary-text-color);
        }

        .info-value {
          color: var(--primary-text-color);
        }

        .loading {
          text-align: center;
          padding: 40px;
          color: var(--secondary-text-color);
        }

        .error {
          padding: 12px;
          background: rgba(239, 83, 80, 0.1);
          border-left: 3px solid #ef5350;
          color: #ef5350;
          border-radius: 2px;
        }
      </style>

      <div class="viewer-container">
        <div class="viewer-toolbar">
          ${this._files.length > 1 ? `
            <div class="file-selector">
              <label>File:</label>
              <select id="file-selector">
                ${this._files.map((f, i) => `<option value="${i}">${f.filename}</option>`).join('')}
              </select>
            </div>
          ` : ''}

          <div class="viewer-controls">
            <button id="btn-reset-view" title="Reset View">↻ Reset</button>
            <button id="btn-show-grid" title="Toggle Grid">⊞ Grid</button>
            <button id="btn-layer-colors" title="Layer Colors">🌈 Layers</button>
            <button id="btn-download" title="Download STL">⬇ Download</button>
          </div>
        </div>

        <div id="canvas-container"></div>

        <div class="viewer-info">
          <div class="info-item">
            <span class="info-label">Dimensions</span>
            <span class="info-value" id="info-dimensions">—</span>
          </div>
          <div class="info-item">
            <span class="info-label">Build Volume Fit</span>
            <span class="info-value" id="info-fit">—</span>
          </div>
          <div class="info-item">
            <span class="info-label">Triangles</span>
            <span class="info-value" id="info-triangles">—</span>
          </div>
          <div class="info-item">
            <span class="info-label">Rendering</span>
            <span class="info-value" id="info-rendering">Waiting for Three.js...</span>
          </div>
        </div>
      </div>
    `;

    if (this._threejsLoaded) {
      this._initializeViewer();
    }
  }

  _initializeViewer() {
    const container = this.querySelector('#canvas-container');
    if (!container) return;

    // TODO: Initialize Three.js scene, camera, renderer
    // TODO: Load STL/3MF geometry
    // TODO: Add controls
    // TODO: Add build volume visualization
    // TODO: Implement event handlers

    console.log('3D Viewer initialized (Phase 3.2 implementation)');
  }
}

customElements.define('model-detail-3d-viewer-tab', ModelDetail3DViewerTab);
