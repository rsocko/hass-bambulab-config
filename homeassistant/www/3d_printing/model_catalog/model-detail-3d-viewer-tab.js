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
    this._defaultModelColor = '#5fa8d3';
    this._buildPlateSizeMm = 256;
    this._config = {};
    this._model = null;
    this._scene = null;
    this._camera = null;
    this._renderer = null;
    this._controls = null;
    this._geometry = null;
    this._mesh = null;
    this._activeObject3D = null;
    this._gridHelper = null;
    this._buildVolumeHelper = null;
    this._files = [];
    this._selectedFileIndex = 0;
    this._threejsLoaded = false;
    this._orbitControlsLoaded = false;
    this._threejsLoadError = '';
    this._renderLoopId = null;
    this._isGridVisible = true;
    this._isBuildVolumeVisible = false;
    this._initialCameraPos = null;
    this._availablePlates = [];
    this._selectedPlateId = '';
    this._currentDimensionsMm = null;
    this._currentColorInfo = null;
    this._currentGeometryGroups = [];
    this._usePackageColors = true;
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
    this._restoreViewerState();
    this._render();
  }

  disconnectedCallback() {
    this._saveViewerState();
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
    } else {
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
            break;
          }
        } catch (error) {
          lastError = error;
        }
      }

      if (!this._threejsLoaded) {
        throw lastError || new Error('Three.js failed to load from configured sources');
      }
    }

    if (!this._hasOrbitControls()) {
      const orbitSources = [
        'https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js',
        'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/examples/js/controls/OrbitControls.min.js',
        'https://unpkg.com/three@0.128.0/examples/js/controls/OrbitControls.js',
      ];

      let lastError = null;
      for (const src of orbitSources) {
        try {
          await this._loadScript(src);
          if (this._hasOrbitControls()) {
            this._orbitControlsLoaded = true;
            break;
          }
        } catch (error) {
          lastError = error;
        }
      }

      if (!this._hasOrbitControls()) {
        console.warn('OrbitControls failed to load, camera rotation disabled');
      }
    } else {
      this._orbitControlsLoaded = true;
    }

    if (!this._has3mfLoader()) {
      const loaderSources = [
        'https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/3MFLoader.js',
        'https://unpkg.com/three@0.128.0/examples/js/loaders/3MFLoader.js',
      ];

      let loaderError = null;
      for (const src of loaderSources) {
        try {
          await this._loadScript(src);
          if (this._has3mfLoader()) {
            break;
          }
        } catch (error) {
          loaderError = error;
        }
      }

      if (!this._has3mfLoader()) {
        console.warn('3MF loader not available, 3MF support disabled');
      }
    }
  }

  _hasOrbitControls() {
    return !!(window.THREE && typeof window.THREE.OrbitControls === 'function');
  }

  _has3mfLoader() {
    return !!(window.THREE && typeof window.THREE.ThreeMFLoader === 'function');
  }

  _loadScript(src) {
    return new Promise((resolve, reject) => {
      let settled = false;
      const existing = Array.from(document.querySelectorAll('script')).find((node) => node && node.src === src);
      if (existing) {
        if (existing.dataset.loaded === 'true') {
          resolve();
          return;
        }
        existing.addEventListener('load', () => resolve(), { once: true });
        existing.addEventListener('error', () => reject(new Error(`Script failed to load: ${src}`)), { once: true });
        return;
      }

      const script = document.createElement('script');
      script.src = src;
      script.async = true;
      script.onload = () => {
        settled = true;
        script.dataset.loaded = 'true';
        resolve();
      };
      script.onerror = () => {
        settled = true;
        reject(new Error(`Script failed to load: ${src}`));
      };
      document.head.appendChild(script);

      setTimeout(() => {
        if (!settled) {
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
          <div id="plate-selector-host"></div>

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
            <button id="btn-build-volume" title="Show Build Volume">📦 Volume</button>
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

    this._syncPlateSelector();

    const resetButton = this.querySelector('#btn-reset-view');
    if (resetButton) {
      resetButton.addEventListener('click', () => this._resetView());
    }

    const gridButton = this.querySelector('#btn-show-grid');
    if (gridButton) {
      gridButton.addEventListener('click', () => this._toggleGrid());
    }

    const volumeButton = this.querySelector('#btn-build-volume');
    if (volumeButton) {
      volumeButton.addEventListener('click', () => this._toggleBuildVolume());
    }

    const layerButton = this.querySelector('#btn-layer-colors');
    if (layerButton) {
      layerButton.addEventListener('click', () => {
        if (!this._currentColorInfo || !this._currentColorInfo.available) {
          this._setRenderingStatus('This 3MF did not expose usable color metadata.');
          return;
        }
        if (this._currentColorInfo.mode === 'multi' && (!Array.isArray(this._currentGeometryGroups) || this._currentGeometryGroups.length === 0)) {
          this._setRenderingStatus('Multi-color metadata is available, but grouped geometry was not returned.');
          return;
        }
        this._usePackageColors = !this._usePackageColors;
        this._applyCurrentMaterialColor();
        this._setRenderingStatus(this._usePackageColors ? 'Using package color metadata.' : 'Using default viewer color.');
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
    this._gridHelper.position.set(this._buildPlateSizeMm / 2, -0.01, this._buildPlateSizeMm / 2);
    this._gridHelper.visible = this._isGridVisible;
    this._scene.add(this._gridHelper);

    const buildVolumeGeom = new window.THREE.BoxGeometry(256, 256, 256);
    const buildVolumeMat = new window.THREE.LineBasicMaterial({
      color: 0xffa500,
      linewidth: 2,
    });
    const buildVolumeEdges = new window.THREE.EdgesGeometry(buildVolumeGeom);
    this._buildVolumeHelper = new window.THREE.LineSegments(buildVolumeEdges, buildVolumeMat);
    this._buildVolumeHelper.position.set(this._buildPlateSizeMm / 2, this._buildPlateSizeMm / 2, this._buildPlateSizeMm / 2);
    this._buildVolumeHelper.visible = this._isBuildVolumeVisible;
    this._scene.add(this._buildVolumeHelper);

    const axis = new window.THREE.AxesHelper(60);
    this._scene.add(axis);

    if (this._hasOrbitControls() && this._orbitControlsLoaded) {
      this._controls = new window.THREE.OrbitControls(this._camera, this._renderer.domElement);
      this._controls.enableDamping = true;
      this._controls.dampingFactor = 0.05;
      this._controls.autoRotate = false;
      this._controls.enableZoom = true;
      this._controls.enablePan = true;
      this._controls.zoomSpeed = 1.0;
      this._controls.rotateSpeed = 0.5;
      this._controls.panSpeed = 0.5;
      this._controls.minDistance = 10;
      this._controls.maxDistance = 10000;
    }

    this._initialCameraPos = { x: this._camera.position.x, y: this._camera.position.y, z: this._camera.position.z };

    const animate = () => {
      this._renderLoopId = requestAnimationFrame(animate);
      if (this._renderer && this._scene && this._camera) {
        if (this._controls) {
          this._controls.update();
        }
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
    const is3mf = filename.endsWith('.3mf') || fileType.includes('3mf');
    
    if (!isStl && !is3mf) {
      this._setError(`Unsupported file type: ${file.file_type || file.filename || 'unknown'}. Supported: STL, 3MF.`);
      return;
    }
    
    if (isStl) {
      const sourceUrl = this._buildFileDownloadUrl(file);
      this._setRenderingStatus(`Downloading ${file.filename || 'geometry file'}...`);
      const response = await fetch(sourceUrl, this._buildFetchOptions(sourceUrl));
      if (!response.ok) {
        throw new Error(`Download failed (${response.status})`);
      }

      const arrayBuffer = await response.arrayBuffer();
      const parsed = this._parseStl(arrayBuffer);
      this._loadGeometry(parsed);
      this._setRenderingStatus(`Rendering ${file.filename || 'model'} (${parsed.triangleCount} triangles)`);
    } else if (is3mf) {
      await this._load3mf(file);
    }
  }

  async _load3mf(file) {
    const filename = String(file && file.filename || 'model');
    const geometryUrl = this._buildGeometryUrl(file);
    let geometryError = null;

    try {
      this._setRenderingStatus(`Fetching ${filename} geometry...`);
      const response = await fetch(geometryUrl, this._buildFetchOptions(geometryUrl));
      if (!response.ok) {
        throw new Error(`Geometry request failed (${response.status})`);
      }

      const payload = await response.json();
      const parsed = this._normalizeParsedGeometryPayload(payload);
      if (parsed) {
        this._loadGeometry(parsed);
        const plateLabel = this._selectedPlateLabel();
        this._setRenderingStatus(`Rendering ${filename}${plateLabel ? ` (${plateLabel})` : ''} (${parsed.triangleCount} triangles)`);
        return;
      }

      geometryError = new Error(String(payload && payload.error ? payload.error : '3MF geometry payload did not include mesh data.'));
    } catch (error) {
      geometryError = error;
    }

    if (!this._has3mfLoader()) {
      throw geometryError || new Error('3MF geometry unavailable.');
    }

    const sourceUrl = this._buildFileDownloadUrl(file);

    try {
      this._setRenderingStatus(`Downloading ${filename}...`);
      const response = await fetch(sourceUrl, this._buildFetchOptions(sourceUrl));
      if (!response.ok) {
        throw new Error(`Download failed (${response.status})`);
      }

      const arrayBuffer = await response.arrayBuffer();
      this._setRenderingStatus(`Parsing 3MF file...`);
      const loader = new window.THREE.ThreeMFLoader();

      if (typeof loader.parse === 'function') {
        const object = loader.parse(arrayBuffer);
        this._load3mfObject(object, filename);
        return;
      }

      const url = URL.createObjectURL(new Blob([arrayBuffer], { type: 'model/3mf' }));
      loader.load(
        url,
        (object) => {
          URL.revokeObjectURL(url);
          this._load3mfObject(object, filename);
        },
        (progress) => {
          const total = progress && progress.total ? progress.total : 0;
          const loaded = progress && progress.loaded ? progress.loaded : 0;
          const pct = total > 0 ? Math.round((loaded / total) * 100) : 0;
          this._setRenderingStatus(`Loading 3MF ${pct}%...`);
        },
        (error) => {
          URL.revokeObjectURL(url);
          this._setError(`3MF parsing failed: ${error.message}`);
        },
      );
    } catch (error) {
      const detail = geometryError && geometryError.message ? ` Parsed geometry failed: ${geometryError.message}.` : '';
      this._setError(`3MF loading failed:${detail} ${error.message}`.trim());
    }
  }

  _normalizeParsedGeometryPayload(payload) {
    const geometry = payload && payload.geometry;
    const vertices = geometry && Array.isArray(geometry.vertices) ? geometry.vertices : null;
    const rawGroups = geometry && Array.isArray(geometry.groups) ? geometry.groups : [];
    if (!geometry || geometry.format !== 'triangles' || ((!vertices || vertices.length < 9) && rawGroups.length === 0)) {
      return null;
    }

    this._availablePlates = Array.isArray(geometry.plates) ? geometry.plates : [];
    if (typeof geometry.selected_plate_id === 'string' && geometry.selected_plate_id) {
      this._selectedPlateId = geometry.selected_plate_id;
    } else if (this._availablePlates.length > 0 && !this._selectedPlateId) {
      this._selectedPlateId = String(this._availablePlates[0].id || '');
    }
    this._currentDimensionsMm = geometry.dimensions_mm && typeof geometry.dimensions_mm === 'object'
      ? geometry.dimensions_mm
      : null;
    this._currentColorInfo = geometry.color_info && typeof geometry.color_info === 'object'
      ? geometry.color_info
      : null;
    this._syncPlateSelector();

    const triangleCount = Number(geometry.triangle_count);
    const coordinateSystem = String(geometry.coordinate_system || '').trim().toLowerCase();
    const mappedGroups = rawGroups
      .map((group) => {
        const groupVertices = Array.isArray(group && group.vertices) ? group.vertices : null;
        if (!groupVertices || groupVertices.length < 9) {
          return null;
        }
        return {
          key: String(group && group.key || ''),
          color: typeof group?.color === 'string' ? group.color : null,
          extruder: Number.isFinite(Number(group?.extruder)) ? Number(group.extruder) : null,
          triangleCount: Number.isFinite(Number(group?.triangle_count)) && Number(group.triangle_count) > 0
            ? Number(group.triangle_count)
            : Math.floor(groupVertices.length / 9),
          vertices: this._mapVerticesForCoordinateSystem(groupVertices, coordinateSystem),
        };
      })
      .filter(Boolean);

    let normalizedVertices = vertices && vertices.length >= 9
      ? this._mapVerticesForCoordinateSystem(vertices, coordinateSystem)
      : this._flattenGroupVertices(mappedGroups);

    const centeredVertexSets = mappedGroups.length > 0
      ? this._centerVertexSetsOnBuildSurface(mappedGroups.map((group) => group.vertices))
      : this._centerVertexSetsOnBuildSurface([normalizedVertices]);

    if (mappedGroups.length > 0) {
      normalizedVertices = this._flattenGroupVertices(centeredVertexSets.map((groupVertices) => ({ vertices: groupVertices })));
      mappedGroups.forEach((group, index) => {
        group.vertices = centeredVertexSets[index];
      });
    } else {
      normalizedVertices = centeredVertexSets[0] || normalizedVertices;
    }

    this._currentGeometryGroups = mappedGroups;

    return {
      vertices: normalizedVertices,
      groups: mappedGroups,
      normals: null,
      triangleCount: Number.isFinite(triangleCount) && triangleCount > 0 ? triangleCount : Math.floor(vertices.length / 9),
      dimensionsMm: this._currentDimensionsMm,
      color: this._resolvePackageColor(),
    };
  }

  _mapVerticesForCoordinateSystem(vertices, coordinateSystem) {
    return coordinateSystem === 'printer_xyz'
      ? this._mapPrinterVerticesToViewer(vertices)
      : Float32Array.from(vertices);
  }

  _flattenGroupVertices(groups) {
    const flattened = [];
    for (const group of groups) {
      const groupVertices = group && group.vertices;
      if (!groupVertices) {
        continue;
      }
      for (let index = 0; index < groupVertices.length; index += 1) {
        flattened.push(groupVertices[index]);
      }
    }
    return Float32Array.from(flattened);
  }

  _mapPrinterVerticesToViewer(vertices) {
    const mapped = new Float32Array(vertices.length);
    for (let index = 0; index < vertices.length; index += 3) {
      mapped[index] = Number(vertices[index]) || 0;
      mapped[index + 1] = Number(vertices[index + 2]) || 0;
      mapped[index + 2] = -(Number(vertices[index + 1]) || 0);
    }
    return mapped;
  }

  _centerVertexSetsOnBuildSurface(vertexSets) {
    if (!Array.isArray(vertexSets) || vertexSets.length === 0) {
      return vertexSets;
    }

    let minX = Number.POSITIVE_INFINITY;
    let maxX = Number.NEGATIVE_INFINITY;
    let minZ = Number.POSITIVE_INFINITY;
    let maxZ = Number.NEGATIVE_INFINITY;

    for (const vertices of vertexSets) {
      if (!(vertices instanceof Float32Array) || vertices.length < 3) {
        continue;
      }
      for (let index = 0; index < vertices.length; index += 3) {
        const x = Number(vertices[index]);
        const z = Number(vertices[index + 2]);
        if (Number.isFinite(x)) {
          minX = Math.min(minX, x);
          maxX = Math.max(maxX, x);
        }
        if (Number.isFinite(z)) {
          minZ = Math.min(minZ, z);
          maxZ = Math.max(maxZ, z);
        }
      }
    }

    if (![minX, maxX, minZ, maxZ].every(Number.isFinite)) {
      return vertexSets;
    }

    const sourceCenterX = (minX + maxX) / 2;
    const sourceCenterZ = (minZ + maxZ) / 2;
    const targetCenter = this._buildPlateSizeMm / 2;
    const shiftX = targetCenter - sourceCenterX;
    const shiftZ = targetCenter - sourceCenterZ;

    return vertexSets.map((vertices) => {
      if (!(vertices instanceof Float32Array) || vertices.length < 3) {
        return vertices;
      }
      const centered = new Float32Array(vertices);
      for (let index = 0; index < centered.length; index += 3) {
        centered[index] += shiftX;
        centered[index + 2] += shiftZ;
      }
      return centered;
    });
  }

  _load3mfObject(object, filename) {
    if (!object || !this._scene || !window.THREE) {
      this._setError('3MF loader returned empty geometry.');
      return;
    }

    if (object.scene && object.scene.isObject3D) {
      this._load3mfObject(object.scene, filename);
      return;
    }

    if (object.geometry && object.geometry.isBufferGeometry) {
      this._loadGeometry({
        vertices: object.geometry.attributes.position.array,
        normals: object.geometry.attributes.normal ? object.geometry.attributes.normal.array : null,
        triangleCount: Math.floor(object.geometry.attributes.position.count / 3),
      });
      this._setRenderingStatus(`Rendering 3MF ${filename || 'model'}`);
      return;
    }

    if (!object.isObject3D) {
      this._setError('Unsupported 3MF object structure.');
      return;
    }

    if (this._mesh) {
      this._scene.remove(this._mesh);
      if (this._mesh.geometry) {
        this._mesh.geometry.dispose();
      }
      if (this._mesh.material) {
        this._mesh.material.dispose();
      }
      this._mesh = null;
    }

    if (this._activeObject3D) {
      this._disposeObject3D(this._activeObject3D);
      this._scene.remove(this._activeObject3D);
      this._activeObject3D = null;
    }

    let vertexCount = 0;
    object.traverse((child) => {
      if (child.isMesh) {
        if (child.geometry && child.geometry.attributes && child.geometry.attributes.position) {
          vertexCount += child.geometry.attributes.position.count;
        }
        if (!child.material) {
          child.material = new window.THREE.MeshStandardMaterial({
            color: 0x5fa8d3,
            metalness: 0.1,
            roughness: 0.65,
            side: window.THREE.DoubleSide,
          });
        }
      }
    });

    this._activeObject3D = object;
    this._scene.add(object);

    const triangleCount = Math.floor(vertexCount / 3);

    const bbox = new window.THREE.Box3().setFromObject(object);
    this._updateModelInfo(triangleCount, bbox);
    this._fitCameraToGeometry(bbox);
    
    if (this._controls) {
      const center = new window.THREE.Vector3();
      bbox.getCenter(center);
      this._controls.target.copy(center);
      this._controls.update();
    }
    
    this._setRenderingStatus(`Rendering 3MF (${triangleCount} triangles)`);
  }

  _buildFetchOptions(url) {
    try {
      const target = new URL(String(url || ''), window.location.href);
      const sameOrigin = target.origin === window.location.origin;
      return { credentials: sameOrigin ? 'include' : 'omit' };
    } catch (_error) {
      return { credentials: 'omit' };
    }
  }

  _normalizeFileId(fileId) {
    const raw = String(fileId || '').trim();
    if (!raw) {
      return '';
    }

    if (!/^https?:\/\//i.test(raw)) {
      return raw;
    }

    try {
      const parsed = new URL(raw);
      const segments = parsed.pathname.split('/').filter(Boolean);
      return segments.length > 0 ? segments[segments.length - 1] : raw;
    } catch (_error) {
      const parts = raw.split('/').filter(Boolean);
      return parts.length > 0 ? parts[parts.length - 1] : raw;
    }
  }

  _buildFileDownloadUrl(file) {
    const base = String(this._config.model_sidecar_url || '').trim().replace(/\/+$/, '');
    const modelRef = encodeURIComponent(String(this._config.model_ref || '').trim());
    const normalizedFileId = this._normalizeFileId(file && file.id || '');
    const fileId = encodeURIComponent(normalizedFileId);
    return `${base}/api/models/${modelRef}/files/${fileId}/download`;
  }

  _buildGeometryUrl(file) {
    const base = String(this._config.model_sidecar_url || '').trim().replace(/\/+$/, '');
    const modelRef = encodeURIComponent(String(this._config.model_ref || '').trim());
    const normalizedFileId = this._normalizeFileId(file && file.id || '');
    const fileId = encodeURIComponent(normalizedFileId);
    const plateQuery = this._selectedPlateId ? `?plate_id=${encodeURIComponent(this._selectedPlateId)}` : '';
    return `${base}/api/models/${modelRef}/geometry/${fileId}${plateQuery}`;
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

    if (this._activeObject3D) {
      this._disposeObject3D(this._activeObject3D);
      this._scene.remove(this._activeObject3D);
      this._activeObject3D = null;
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

    this._currentGeometryGroups = Array.isArray(parsed.groups) ? parsed.groups : [];

    if (this._currentGeometryGroups.length > 0) {
      const meshGroup = new window.THREE.Group();
      for (const group of this._currentGeometryGroups) {
        const groupGeometry = new window.THREE.BufferGeometry();
        groupGeometry.setAttribute('position', new window.THREE.BufferAttribute(group.vertices, 3));
        groupGeometry.computeVertexNormals();
        const material = new window.THREE.MeshStandardMaterial({
          color: this._resolveRenderedGroupColor(group),
          metalness: 0.1,
          roughness: 0.65,
          side: window.THREE.DoubleSide,
        });
        const mesh = new window.THREE.Mesh(groupGeometry, material);
        mesh.userData.packageColor = group.color || null;
        meshGroup.add(mesh);
      }

      this._activeObject3D = meshGroup;
      this._scene.add(meshGroup);

      const bbox = new window.THREE.Box3().setFromObject(meshGroup);
      this._updateModelInfo(parsed.triangleCount, bbox, parsed.dimensionsMm || null);
      this._fitCameraToGeometry(bbox);
      return;
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
      color: parsed.color || this._defaultModelColor,
      metalness: 0.1,
      roughness: 0.65,
      side: window.THREE.DoubleSide,
    });

    this._mesh = new window.THREE.Mesh(geometry, material);
    this._scene.add(this._mesh);

    this._updateModelInfo(parsed.triangleCount, geometry.boundingBox, parsed.dimensionsMm || null);
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

  _updateModelInfo(triangleCount, boundingBox, dimensionsMm = null) {
    if (!boundingBox && !dimensionsMm) {
      return;
    }

    let size = null;
    if (boundingBox) {
      size = new window.THREE.Vector3();
      boundingBox.getSize(size);
    }

    const dims = dimensionsMm && typeof dimensionsMm === 'object'
      ? {
          x: Number(dimensionsMm.x) || 0,
          y: Number(dimensionsMm.y) || 0,
          z: Number(dimensionsMm.z) || 0,
        }
      : {
          x: size ? size.x : 0,
          y: size ? size.y : 0,
          z: size ? size.z : 0,
        };

    const dimensionsNode = this.querySelector('#info-dimensions');
    if (dimensionsNode) {
      dimensionsNode.textContent = `${dims.x.toFixed(1)} x ${dims.y.toFixed(1)} x ${dims.z.toFixed(1)} mm`;
    }

    const trianglesNode = this.querySelector('#info-triangles');
    if (trianglesNode) {
      trianglesNode.textContent = String(triangleCount || 0);
    }

    const fitNode = this.querySelector('#info-fit');
    if (fitNode) {
      const fits = dims.x <= 256 && dims.y <= 256 && dims.z <= 256;
      fitNode.textContent = fits ? 'Fits (<= 256mm)' : 'Exceeds 256mm volume';
    }
  }

  _syncPlateSelector() {
    const host = this.querySelector('#plate-selector-host');
    if (!host) {
      return;
    }

    if (!Array.isArray(this._availablePlates) || this._availablePlates.length <= 1) {
      host.innerHTML = '';
      return;
    }

    const options = this._availablePlates.map((plate) => {
      const plateId = String(plate && plate.id || '');
      const plateName = String(plate && plate.name || `Plate ${plateId || '?'}`);
      return `<option value="${this._escapeHtml(plateId)}">${this._escapeHtml(plateName)}</option>`;
    }).join('');

    host.innerHTML = `
      <div class="file-selector">
        <label>Plate:</label>
        <select id="plate-selector">${options}</select>
      </div>
    `;

    const selector = this.querySelector('#plate-selector');
    if (!selector) {
      return;
    }
    selector.value = this._selectedPlateId || String(this._availablePlates[0] && this._availablePlates[0].id || '');
    selector.onchange = (event) => {
      const nextPlateId = String(event.target && event.target.value || '').trim();
      this._selectedPlateId = nextPlateId;
      this._loadSelectedGeometry().catch((error) => {
        this._setError(`Failed to load model geometry: ${String(error && error.message ? error.message : error)}`);
      });
    };
  }

  _selectedPlateLabel() {
    if (!Array.isArray(this._availablePlates) || !this._selectedPlateId) {
      return '';
    }
    const match = this._availablePlates.find((plate) => String(plate && plate.id || '') === this._selectedPlateId);
    return match ? String(match.name || '') : '';
  }

  _resolvePackageColor() {
    if (!this._usePackageColors || !this._currentColorInfo || !this._currentColorInfo.available) {
      return null;
    }
    if (this._currentColorInfo.mode !== 'single') {
      return null;
    }
    const primaryColor = String(this._currentColorInfo.primary_color || '').trim();
    return primaryColor || null;
  }

  _resolveRenderedGroupColor(group) {
    if (!this._usePackageColors) {
      return this._defaultModelColor;
    }
    const packageColor = String(group && group.color || '').trim();
    return packageColor || this._defaultModelColor;
  }

  _applyCurrentMaterialColor() {
    if (this._activeObject3D) {
      this._activeObject3D.traverse((child) => {
        if (!child || !child.isMesh || !child.material || !child.material.color) {
          return;
        }
        const packageColor = String(child.userData && child.userData.packageColor || '').trim();
        child.material.color.set(this._usePackageColors && packageColor ? packageColor : this._defaultModelColor);
        child.material.needsUpdate = true;
      });
    }
    const colorValue = this._resolvePackageColor() || this._defaultModelColor;
    if (this._mesh && this._mesh.material && this._mesh.material.color) {
      this._mesh.material.color.set(colorValue);
      this._mesh.material.needsUpdate = true;
    }
  }

  _resetView() {
    if (!this._camera) {
      return;
    }

    let targetBox = null;
    if (this._geometry && this._geometry.boundingBox) {
      targetBox = this._geometry.boundingBox;
    } else if (this._activeObject3D) {
      targetBox = new window.THREE.Box3().setFromObject(this._activeObject3D);
    }

    if (!targetBox) {
      return;
    }

    this._fitCameraToGeometry(targetBox);
    
    if (this._controls) {
      const center = new window.THREE.Vector3();
      targetBox.getCenter(center);
      this._controls.target.copy(center);
      this._controls.update();
    }
  }

  _toggleGrid() {
    if (!this._gridHelper) {
      return;
    }
    this._isGridVisible = !this._isGridVisible;
    this._gridHelper.visible = this._isGridVisible;
  }

  _toggleBuildVolume() {
    if (!this._buildVolumeHelper) {
      return;
    }
    this._isBuildVolumeVisible = !this._isBuildVolumeVisible;
    this._buildVolumeHelper.visible = this._isBuildVolumeVisible;
  }

  _downloadCurrentFile() {
    const file = this._files[this._selectedFileIndex];
    if (!file) {
      return;
    }
    const url = this._buildFileDownloadUrl(file);
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  _disposeObject3D(object) {
    if (!object || typeof object.traverse !== 'function') {
      return;
    }
    object.traverse((child) => {
      if (child && child.geometry && typeof child.geometry.dispose === 'function') {
        child.geometry.dispose();
      }
      if (child && child.material) {
        if (Array.isArray(child.material)) {
          child.material.forEach((material) => {
            if (material && typeof material.dispose === 'function') {
              material.dispose();
            }
          });
        } else if (typeof child.material.dispose === 'function') {
          child.material.dispose();
        }
      }
    });
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

  _escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  _saveViewerState() {
    try {
      const stateKey = `model_viewer_state_${String(this._config.model_ref || 'default')}`;
      const state = {
        selectedFileIndex: this._selectedFileIndex,
        selectedPlateId: this._selectedPlateId,
        gridVisible: this._isGridVisible,
        buildVolumeVisible: this._isBuildVolumeVisible,
        timestamp: Date.now(),
      };
      sessionStorage.setItem(stateKey, JSON.stringify(state));
    } catch (_error) {
      // Silently fail if sessionStorage is unavailable
    }
  }

  _restoreViewerState() {
    try {
      const stateKey = `model_viewer_state_${String(this._config.model_ref || 'default')}`;
      const saved = sessionStorage.getItem(stateKey);
      if (saved) {
        const state = JSON.parse(saved);
        if (typeof state === 'object' && state !== null) {
          if (typeof state.selectedFileIndex === 'number' && state.selectedFileIndex < this._files.length) {
            this._selectedFileIndex = state.selectedFileIndex;
          }
          if (typeof state.selectedPlateId === 'string') {
            this._selectedPlateId = state.selectedPlateId;
          }
          if (typeof state.gridVisible === 'boolean') {
            this._isGridVisible = state.gridVisible;
          }
          if (typeof state.buildVolumeVisible === 'boolean') {
            this._isBuildVolumeVisible = state.buildVolumeVisible;
          }
        }
      }
    } catch (_error) {
      // Silently fail if sessionStorage is unavailable or corrupted
    }
  }
}

customElements.define('model-detail-3d-viewer-tab', ModelDetail3DViewerTab);
