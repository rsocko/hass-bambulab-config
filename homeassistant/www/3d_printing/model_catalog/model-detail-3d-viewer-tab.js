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
    this._config = {};
    this._model = null;
    this._scene = null;
    this._camera = null;
    this._renderer = null;
    this._geometry = null;
    this._mesh = null;
    this._gridHelper = null;
    this._files = [];
    this._selectedFileIndex = 0;
    this._threejsLoaded = false;
    this._threejsLoadError = '';
    this._renderLoopId = null;
    this._isGridVisible = true;
  }

  setConfig(config) {
    this._config = config || {};
    this._model = this._parseModelConfig(this._config.model_json || null);

    const modelFiles = this._model && Array.isArray(this._model.files) ? this._model.files : [];
    this._files = modelFiles.filter((file) => {
      const filename = String(file && file.filename || '').toLowerCase();
      const fileType = String(file && file.file_type || '').toLowerCase();
      return (
        filename.endsWith('.stl')
        || filename.endsWith('.3mf')
        || filename.endsWith('.obj')
        || fileType.includes('stl')
        || fileType.includes('3mf')
        || fileType.includes('obj')
      );
    });

    if (this.isConnected) {
      this._render();
    }
  }

  async connectedCallback() {
    try {
      await this._loadThreeJs();
    } catch (error) {
      this._threejsLoadError = String(error && error.message ? error.message : error || 'Failed to load Three.js');
    }
    this._render();
  }

  disconnectedCallback() {
    if (this._renderLoopId) {
      cancelAnimationFrame(this._renderLoopId);
      this._renderLoopId = null;
    }
    if (this._renderer) {
      this._renderer.dispose();
      this._renderer = null;
    }
  }

  async _loadThreeJs() {
    if (window.THREE) {
      this._threejsLoaded = true;
      return;
    }

    const sources = [
      'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js',
      'https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js',
      'https://unpkg.com/three@0.128.0/build/three.min.js',
    ];

    let lastError = null;
    for (const src of sources) {
      try {
        await this._loadScript(src);
        if (window.THREE) {
          this._threejsLoaded = true;
          return;
        }
      } catch (error) {
        lastError = error;
      }
    }

    throw lastError || new Error('Three.js failed to load from configured sources');
  }

  _loadScript(src) {
    return new Promise((resolve, reject) => {
      const existing = Array.from(document.querySelectorAll('script')).find((node) => node && node.src === src);
      if (existing) {
        if (window.THREE) {
          resolve();
          return;
        }
      }

      const script = document.createElement('script');
      script.src = src;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error(`Script failed to load: ${src}`));
      document.head.appendChild(script);

      setTimeout(() => {
        if (!window.THREE) {
          reject(new Error(`Script load timed out: ${src}`));
        }
      }, 12000);
    });
  }

  _render() {
    if (this._files.length === 0) {
      this.innerHTML = `
        <style>
          .viewer-empty {
            padding: 24px;
            border: 1px solid var(--divider-color);
            border-radius: 8px;
            background: var(--card-background-color);
          }

          .viewer-empty h3 {
            margin: 0 0 8px 0;
            font-size: 18px;
            color: var(--primary-text-color);
          }

          .viewer-empty p {
            margin: 0;
            color: var(--secondary-text-color);
            line-height: 1.45;
          }
        </style>
        <div class="viewer-empty">
          <h3>No 3D Files Available</h3>
          <p>This model does not currently include STL, 3MF, or OBJ files that can be rendered in the viewer.</p>
        </div>
      `;
      return;
    }

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

        #canvas-container canvas {
          width: 100%;
          height: 100%;
          display: block;
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

    const selector = this.querySelector('#file-selector');
    if (selector) {
      selector.value = String(this._selectedFileIndex);
      selector.addEventListener('change', (event) => {
        const index = Number(event.target && event.target.value || 0);
        this._selectedFileIndex = Number.isFinite(index) ? Math.max(0, index) : 0;
        this._loadSelectedGeometry().catch((error) => {
          this._setError(`Failed to load model geometry: ${String(error && error.message ? error.message : error)}`);
        });
      });
    }

    const resetButton = this.querySelector('#btn-reset-view');
    if (resetButton) {
      resetButton.addEventListener('click', () => this._resetView());
    }

    const gridButton = this.querySelector('#btn-show-grid');
    if (gridButton) {
      gridButton.addEventListener('click', () => this._toggleGrid());
    }

    const layerButton = this.querySelector('#btn-layer-colors');
    if (layerButton) {
      layerButton.addEventListener('click', () => {
        this._setRenderingStatus('Layer coloring is not implemented for STL/OBJ in this viewer yet.');
      });
    }

    const downloadButton = this.querySelector('#btn-download');
    if (downloadButton) {
      downloadButton.addEventListener('click', () => this._downloadCurrentFile());
    }

    if (this._threejsLoadError) {
      this._setError(`Three.js load failed. ${this._threejsLoadError}`);
      return;
    }

    if (this._threejsLoaded) {
      this._initializeViewer();
    }
  }

  _initializeViewer() {
    const container = this.querySelector('#canvas-container');
    if (!container || !window.THREE) return;

    if (this._renderLoopId) {
      cancelAnimationFrame(this._renderLoopId);
      this._renderLoopId = null;
    }

    container.innerHTML = '';

    const width = Math.max(1, container.clientWidth || 1);
    const height = Math.max(1, container.clientHeight || 1);

    this._scene = new window.THREE.Scene();
    this._scene.background = new window.THREE.Color(0x1a1a1a);

    this._camera = new window.THREE.PerspectiveCamera(55, width / height, 0.1, 100000);
    this._camera.position.set(140, 120, 180);

    this._renderer = new window.THREE.WebGLRenderer({ antialias: true });
    this._renderer.setPixelRatio(window.devicePixelRatio || 1);
    this._renderer.setSize(width, height);
    container.appendChild(this._renderer.domElement);

    const ambientLight = new window.THREE.AmbientLight(0xffffff, 0.55);
    this._scene.add(ambientLight);

    const keyLight = new window.THREE.DirectionalLight(0xffffff, 0.85);
    keyLight.position.set(1, 1, 1);
    this._scene.add(keyLight);

    const fillLight = new window.THREE.DirectionalLight(0xffffff, 0.3);
    fillLight.position.set(-1, 0.5, -1);
    this._scene.add(fillLight);

    this._gridHelper = new window.THREE.GridHelper(256, 16, 0x444444, 0x333333);
    this._gridHelper.position.y = -0.01;
    this._gridHelper.visible = this._isGridVisible;
    this._scene.add(this._gridHelper);

    const axis = new window.THREE.AxesHelper(60);
    this._scene.add(axis);

    const animate = () => {
      this._renderLoopId = requestAnimationFrame(animate);
      if (this._renderer && this._scene && this._camera) {
        this._renderer.render(this._scene, this._camera);
      }
    };
    animate();

    this._setRenderingStatus('Three.js loaded. Fetching model geometry...');
    this._loadSelectedGeometry().catch((error) => {
      this._setError(`Failed to load model geometry: ${String(error && error.message ? error.message : error)}`);
    });
  }

  async _loadSelectedGeometry() {
    const file = this._files[this._selectedFileIndex];
    if (!file) {
      this._setError('No geometry file selected.');
      return;
    }

    const fileType = String(file.file_type || '').toLowerCase();
    const filename = String(file.filename || '').toLowerCase();
    const isStl = filename.endsWith('.stl') || fileType.includes('stl');
    if (!isStl) {
      this._setError(`Unsupported file type for renderer: ${file.file_type || file.filename || 'unknown'}. STL is currently supported.`);
      return;
    }

    const sourceUrl = this._buildFileDownloadUrl(file);
    this._setRenderingStatus(`Downloading ${file.filename || 'geometry file'}...`);
    const response = await fetch(sourceUrl, { credentials: 'include' });
    if (!response.ok) {
      throw new Error(`Download failed (${response.status})`);
    }

    const arrayBuffer = await response.arrayBuffer();
    const parsed = this._parseStl(arrayBuffer);
    this._loadGeometry(parsed);
    this._setRenderingStatus(`Rendering ${file.filename || 'model'} (${parsed.triangleCount} triangles)`);
  }

  _buildFileDownloadUrl(file) {
    const base = String(this._config.model_sidecar_url || '').trim().replace(/\/+$/, '');
    const modelRef = encodeURIComponent(String(this._config.model_ref || '').trim());
    const fileId = encodeURIComponent(String(file && file.id || '').trim());
    return `${base}/api/models/${modelRef}/files/${fileId}/download`;
  }

  _setRenderingStatus(message) {
    const node = this.querySelector('#info-rendering');
    if (node) {
      node.textContent = String(message || '');
    }
  }

  _setError(message) {
    this._setRenderingStatus(`Error: ${message}`);
  }

  _loadGeometry(parsed) {
    if (!window.THREE || !this._scene) {
      return;
    }

    if (this._mesh) {
      this._scene.remove(this._mesh);
      this._mesh.geometry.dispose();
      this._mesh.material.dispose();
      this._mesh = null;
    }

    if (this._geometry) {
      this._geometry.dispose();
      this._geometry = null;
    }

    const geometry = new window.THREE.BufferGeometry();
    geometry.setAttribute('position', new window.THREE.BufferAttribute(parsed.vertices, 3));
    if (parsed.normals && parsed.normals.length > 0) {
      geometry.setAttribute('normal', new window.THREE.BufferAttribute(parsed.normals, 3));
    } else {
      geometry.computeVertexNormals();
    }
    geometry.computeBoundingBox();
    this._geometry = geometry;

    const material = new window.THREE.MeshStandardMaterial({
      color: 0x5fa8d3,
      metalness: 0.1,
      roughness: 0.65,
      side: window.THREE.DoubleSide,
    });

    this._mesh = new window.THREE.Mesh(geometry, material);
    this._scene.add(this._mesh);

    this._updateModelInfo(parsed.triangleCount, geometry.boundingBox);
    this._fitCameraToGeometry(geometry.boundingBox);
  }

  _fitCameraToGeometry(boundingBox) {
    if (!boundingBox || !this._camera) {
      return;
    }

    const center = new window.THREE.Vector3();
    boundingBox.getCenter(center);

    const size = new window.THREE.Vector3();
    boundingBox.getSize(size);

    const maxDim = Math.max(size.x, size.y, size.z, 1);
    const fov = this._camera.fov * (Math.PI / 180);
    const distance = (maxDim / 2) / Math.tan(fov / 2);

    this._camera.position.set(center.x + distance * 0.9, center.y + distance * 0.7, center.z + distance * 1.1);
    this._camera.lookAt(center);
  }

  _updateModelInfo(triangleCount, boundingBox) {
    if (!boundingBox) {
      return;
    }

    const size = new window.THREE.Vector3();
    boundingBox.getSize(size);

    const dimensionsNode = this.querySelector('#info-dimensions');
    if (dimensionsNode) {
      dimensionsNode.textContent = `${size.x.toFixed(1)} x ${size.y.toFixed(1)} x ${size.z.toFixed(1)} mm`;
    }

    const trianglesNode = this.querySelector('#info-triangles');
    if (trianglesNode) {
      trianglesNode.textContent = String(triangleCount || 0);
    }

    const fitNode = this.querySelector('#info-fit');
    if (fitNode) {
      const fits = size.x <= 256 && size.y <= 256 && size.z <= 256;
      fitNode.textContent = fits ? 'Fits (<= 256mm)' : 'Exceeds 256mm volume';
    }
  }

  _resetView() {
    if (!this._geometry || !this._camera) {
      return;
    }
    this._fitCameraToGeometry(this._geometry.boundingBox || null);
  }

  _toggleGrid() {
    if (!this._gridHelper) {
      return;
    }
    this._isGridVisible = !this._isGridVisible;
    this._gridHelper.visible = this._isGridVisible;
  }

  _downloadCurrentFile() {
    const file = this._files[this._selectedFileIndex];
    if (!file) {
      return;
    }
    const url = this._buildFileDownloadUrl(file);
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  _parseStl(arrayBuffer) {
    const bytes = new Uint8Array(arrayBuffer);
    const asciiHeader = String.fromCharCode(...bytes.slice(0, 5)).toLowerCase();
    const isLikelyAscii = asciiHeader === 'solid';

    if (isLikelyAscii) {
      const asciiResult = this._parseAsciiStl(arrayBuffer);
      if (asciiResult.vertices.length > 0) {
        return asciiResult;
      }
    }

    return this._parseBinaryStl(arrayBuffer);
  }

  _parseBinaryStl(arrayBuffer) {
    const view = new DataView(arrayBuffer);
    if (view.byteLength < 84) {
      throw new Error('STL file is too small to parse.');
    }

    const faceCount = view.getUint32(80, true);
    const expectedByteLength = 84 + (faceCount * 50);
    if (expectedByteLength > view.byteLength) {
      throw new Error('STL binary face count does not match file length.');
    }

    const vertices = new Float32Array(faceCount * 9);
    const normals = new Float32Array(faceCount * 9);
    let vertexOffset = 0;

    for (let face = 0; face < faceCount; face += 1) {
      const base = 84 + (face * 50);
      const nx = view.getFloat32(base, true);
      const ny = view.getFloat32(base + 4, true);
      const nz = view.getFloat32(base + 8, true);

      for (let vertex = 0; vertex < 3; vertex += 1) {
        const pointBase = base + 12 + (vertex * 12);
        vertices[vertexOffset] = view.getFloat32(pointBase, true);
        vertices[vertexOffset + 1] = view.getFloat32(pointBase + 4, true);
        vertices[vertexOffset + 2] = view.getFloat32(pointBase + 8, true);

        normals[vertexOffset] = nx;
        normals[vertexOffset + 1] = ny;
        normals[vertexOffset + 2] = nz;
        vertexOffset += 3;
      }
    }

    return {
      vertices,
      normals,
      triangleCount: faceCount,
    };
  }

  _parseAsciiStl(arrayBuffer) {
    const text = new TextDecoder('utf-8').decode(arrayBuffer);
    const vertexPattern = /vertex\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)/g;
    const normalPattern = /facet\s+normal\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)/g;

    const verticesRaw = [];
    let match = null;
    while ((match = vertexPattern.exec(text)) !== null) {
      verticesRaw.push(Number(match[1]), Number(match[2]), Number(match[3]));
    }

    const normalsRaw = [];
    while ((match = normalPattern.exec(text)) !== null) {
      normalsRaw.push(Number(match[1]), Number(match[2]), Number(match[3]));
    }

    if (verticesRaw.length === 0) {
      return {
        vertices: new Float32Array(0),
        normals: new Float32Array(0),
        triangleCount: 0,
      };
    }

    const vertices = new Float32Array(verticesRaw);
    const normals = new Float32Array(vertices.length);
    if (normalsRaw.length > 0) {
      for (let i = 0; i < vertices.length / 9; i += 1) {
        const nx = normalsRaw[i * 3] || 0;
        const ny = normalsRaw[i * 3 + 1] || 0;
        const nz = normalsRaw[i * 3 + 2] || 1;
        const base = i * 9;
        for (let v = 0; v < 3; v += 1) {
          const normalBase = base + (v * 3);
          normals[normalBase] = nx;
          normals[normalBase + 1] = ny;
          normals[normalBase + 2] = nz;
        }
      }
    }

    return {
      vertices,
      normals,
      triangleCount: Math.floor(vertices.length / 9),
    };
  }

  _parseModelConfig(modelValue) {
    if (!modelValue) {
      return null;
    }

    if (typeof modelValue === 'object') {
      return modelValue;
    }

    if (typeof modelValue !== 'string') {
      return null;
    }

    try {
      const parsed = JSON.parse(modelValue);
      return parsed && typeof parsed === 'object' ? parsed : null;
    } catch (_error) {
      return null;
    }
  }
}

customElements.define('model-detail-3d-viewer-tab', ModelDetail3DViewerTab);
