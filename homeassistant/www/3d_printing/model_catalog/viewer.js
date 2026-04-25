/**
 * ModelViewer - Three.js-based 3D model viewer for Model Catalog
 * 
 * Features:
 * - Automatic scene setup with lighting
 * - STL/OBJ geometry loading
 * - Auto-fit camera to model bounds
 * - OrbitControls for mouse/touch interaction
 * - Build volume visualization (Bambu P1S: 256×256×256mm)
 * - Real-time rendering with responsive sizing
 * 
 * @module viewer
 */

// Bambu P1S build volume dimensions (mm)
const BAMBU_P1S_DIMENSIONS = {
  width: 256,
  height: 256,
  depth: 256,
};

// Conversion factor from model units (mm) to Three.js units
const SCALE_FACTOR = 0.001; // 1mm = 0.001 units in scene

class ModelViewer {
  /**
   * Initialize a 3D model viewer with Three.js
   * 
   * @param {HTMLCanvasElement} canvas - Canvas element for rendering
   * @param {Object} options - Configuration options
   * @param {boolean} options.showBuildVolume - Show build volume helper (default: true)
   * @param {boolean} options.enableControls - Enable orbit controls (default: true)
   * @param {string} options.modelColor - Model mesh color hex (default: 0x0077be)
   */
  constructor(canvas, options = {}) {
    this.canvas = canvas;
    this.options = {
      showBuildVolume: true,
      enableControls: true,
      modelColor: 0x0077be,
      ...options,
    };

    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.controls = null;
    this.mesh = null;
    this.buildVolume = null;
    this.animationFrameId = null;

    this._initScene();
    this._initCamera();
    this._initRenderer();
    this._initLighting();
    this._initControls();
    
    if (this.options.showBuildVolume) {
      this._createBuildVolume();
    }

    this._setupResizeListener();
    this._animate();
  }

  /**
   * Initialize the Three.js scene
   * @private
   */
  _initScene() {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0xf5f5f5);
  }

  /**
   * Initialize the perspective camera
   * @private
   */
  _initCamera() {
    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    
    this.camera = new THREE.PerspectiveCamera(
      75,                          // FOV
      width / height,              // Aspect ratio
      0.1,                         // Near plane
      10000                        // Far plane
    );
    
    // Position camera to view from a comfortable angle
    this.camera.position.set(150, 150, 200);
    this.camera.lookAt(0, 0, 0);
  }

  /**
   * Initialize the WebGL renderer
   * @private
   */
  _initRenderer() {
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: true,
      alpha: false,
    });

    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;

    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowShadowMap;
  }

  /**
   * Initialize lighting
   * @private
   */
  _initLighting() {
    // Ambient light for overall illumination
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    this.scene.add(ambientLight);

    // Directional light for shadows and depth
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(100, 100, 100);
    directionalLight.castShadow = true;
    directionalLight.shadow.mapSize.width = 2048;
    directionalLight.shadow.mapSize.height = 2048;
    directionalLight.shadow.camera.left = -300;
    directionalLight.shadow.camera.right = 300;
    directionalLight.shadow.camera.top = 300;
    directionalLight.shadow.camera.bottom = -300;
    this.scene.add(directionalLight);

    // Secondary light for fill (reduces harsh shadows)
    const fillLight = new THREE.DirectionalLight(0xffffff, 0.3);
    fillLight.position.set(-100, 50, -100);
    this.scene.add(fillLight);
  }

  /**
   * Initialize orbit controls for mouse/touch interaction
   * @private
   */
  _initControls() {
    if (!this.options.enableControls || typeof OrbitControls === 'undefined') {
      console.warn('OrbitControls not available; manual controls disabled');
      return;
    }

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.05;
    this.controls.autoRotate = false;
    this.controls.enableZoom = true;
    this.controls.enablePan = true;
    this.controls.minDistance = 50;
    this.controls.maxDistance = 1000;
  }

  /**
   * Create build volume visualization (Bambu P1S)
   * @private
   */
  _createBuildVolume() {
    const { width, height, depth } = BAMBU_P1S_DIMENSIONS;
    const scaledWidth = width * SCALE_FACTOR;
    const scaledHeight = height * SCALE_FACTOR;
    const scaledDepth = depth * SCALE_FACTOR;

    // Create bounding box helper
    const geometry = new THREE.BoxGeometry(scaledWidth, scaledHeight, scaledDepth);
    const material = new THREE.MeshBasicMaterial({
      color: 0xcccccc,
      transparent: true,
      opacity: 0.1,
      wireframe: false,
    });
    const buildVolume = new THREE.Mesh(geometry, material);
    
    // Add wireframe edges for clarity
    const edges = new THREE.EdgesGeometry(geometry);
    const line = new THREE.LineSegments(
      edges,
      new THREE.LineBasicMaterial({
        color: 0x666666,
        linewidth: 1,
      })
    );
    
    buildVolume.add(line);
    this.scene.add(buildVolume);
    this.buildVolume = buildVolume;
  }

  /**
   * Load geometry from STL/OBJ parser output
   * 
   * @param {Object} geometryData - Parsed geometry from STLParser
   * @param {Float32Array} geometryData.vertices - Flat vertex array [x1,y1,z1,x2,y2,z2,...]
   * @param {Float32Array} geometryData.normals - Flat normal array (optional)
   * @param {number} geometryData.triangleCount - Number of triangles
   */
  loadGeometry(geometryData) {
    // Remove existing mesh
    if (this.mesh) {
      this.scene.remove(this.mesh);
    }

    // Create Three.js BufferGeometry
    const geometry = new THREE.BufferGeometry();

    // Add position attribute (vertices)
    geometry.setAttribute(
      'position',
      new THREE.BufferAttribute(geometryData.vertices, 3)
    );

    // Add normal attribute or compute if not provided
    if (geometryData.normals && geometryData.normals.length > 0) {
      geometry.setAttribute(
        'normal',
        new THREE.BufferAttribute(geometryData.normals, 3)
      );
    } else {
      geometry.computeVertexNormals();
    }

    // Create material and mesh
    const material = new THREE.MeshPhongMaterial({
      color: this.options.modelColor,
      shininess: 100,
      flatShading: false,
      side: THREE.DoubleSide,
    });

    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.castShadow = true;
    this.mesh.receiveShadow = true;
    this.scene.add(this.mesh);

    // Auto-fit camera to model
    this._fitCameraToGeometry(geometry);
  }

  /**
   * Auto-fit camera to view all geometry
   * 
   * @private
   * @param {THREE.BufferGeometry} geometry - Geometry to fit
   */
  _fitCameraToGeometry(geometry) {
    // Compute bounding box
    geometry.computeBoundingBox();
    const boundingBox = geometry.boundingBox;

    if (!boundingBox) return;

    // Calculate center and size
    const center = new THREE.Vector3();
    boundingBox.getCenter(center);
    const size = new THREE.Vector3();
    boundingBox.getSize(size);

    // Calculate camera distance needed to view the model
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = this.camera.fov * (Math.PI / 180); // convert to radians
    let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));

    // Add some padding
    cameraZ *= 1.3;

    // Position camera
    this.camera.position.z = center.z + cameraZ;
    this.camera.position.x = center.x;
    this.camera.position.y = center.y + size.y * 0.5;
    this.camera.lookAt(center);

    // Update controls if available
    if (this.controls) {
      this.controls.target.copy(center);
      this.controls.minDistance = cameraZ * 0.3;
      this.controls.maxDistance = cameraZ * 5;
      this.controls.update();
    }
  }

  /**
   * Get model bounding box dimensions in mm
   * 
   * @returns {Object|null} Dimensions object or null if no geometry loaded
   * @property {number} width - Width in mm
   * @property {number} height - Height in mm
   * @property {number} depth - Depth in mm
   * @property {boolean} fits - Whether model fits in build volume
   */
  getModelDimensions() {
    if (!this.mesh) return null;

    const geometry = this.mesh.geometry;
    geometry.computeBoundingBox();
    const box = geometry.boundingBox;

    if (!box) return null;

    const size = new THREE.Vector3();
    box.getSize(size);

    // Convert from scene units back to mm
    const width = size.x / SCALE_FACTOR;
    const height = size.y / SCALE_FACTOR;
    const depth = size.z / SCALE_FACTOR;

    const { width: bvWidth, height: bvHeight, depth: bvDepth } = BAMBU_P1S_DIMENSIONS;

    return {
      width: Math.round(width * 100) / 100,
      height: Math.round(height * 100) / 100,
      depth: Math.round(depth * 100) / 100,
      fits:
        width <= bvWidth &&
        height <= bvHeight &&
        depth <= bvDepth,
    };
  }

  /**
   * Set model color
   * 
   * @param {number} hexColor - Color as hex number (e.g., 0xFF0000 for red)
   */
  setModelColor(hexColor) {
    if (this.mesh && this.mesh.material) {
      this.mesh.material.color.setHex(hexColor);
    }
    this.options.modelColor = hexColor;
  }

  /**
   * Enable/disable auto-rotation
   * 
   * @param {boolean} enabled - Whether to auto-rotate
   */
  setAutoRotate(enabled) {
    if (this.controls) {
      this.controls.autoRotate = enabled;
    }
  }

  /**
   * Reset camera to initial view
   */
  resetCamera() {
    if (this.mesh) {
      const geometry = this.mesh.geometry;
      this._fitCameraToGeometry(geometry);
    } else {
      this.camera.position.set(150, 150, 200);
      this.camera.lookAt(0, 0, 0);
    }

    if (this.controls) {
      this.controls.reset();
    }
  }

  /**
   * Setup window resize listener for responsive canvas
   * @private
   */
  _setupResizeListener() {
    const resizeObserver = new ResizeObserver(() => {
      const width = this.canvas.clientWidth;
      const height = this.canvas.clientHeight;

      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(width, height);
    });

    resizeObserver.observe(this.canvas);
  }

  /**
   * Animation loop - called every frame
   * @private
   */
  _animate() {
    this.animationFrameId = requestAnimationFrame(() => this._animate());

    // Update controls
    if (this.controls) {
      this.controls.update();
    }

    // Render scene
    this.renderer.render(this.scene, this.camera);
  }

  /**
   * Dispose of resources and stop animation
   */
  dispose() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }

    if (this.controls) {
      this.controls.dispose();
    }

    if (this.mesh && this.mesh.geometry) {
      this.mesh.geometry.dispose();
      this.mesh.material.dispose();
    }

    if (this.renderer) {
      this.renderer.dispose();
    }
  }
}

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ModelViewer, BAMBU_P1S_DIMENSIONS, SCALE_FACTOR };
}
