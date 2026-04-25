/**
 * STL File Loader for Three.js
 * 
 * Parses binary and ASCII STL files and creates Three.js BufferGeometry
 * Part of Phase 3.2 implementation (3D Viewer)
 * 
 * Usage:
 *   const geometry = await STLLoader.parse(arrayBuffer);
 */

class STLLoader {
  /**
   * Parse STL file (binary or ASCII)
   * @param {ArrayBuffer} arrayBuffer - Binary or ASCII STL data
   * @returns {THREE.BufferGeometry} Three.js geometry object
   */
  static parse(arrayBuffer) {
    const view = new Uint8Array(arrayBuffer);
    
    // Check if ASCII (starts with "solid")
    const isASCII = this._isASCIISTL(view);
    
    if (isASCII) {
      return this._parseASCII(arrayBuffer);
    } else {
      return this._parseBinary(view);
    }
  }

  /**
   * Check if STL file is ASCII format
   * @private
   */
  static _isASCIISTL(view) {
    // First 5 bytes should be "solid"
    const header = String.fromCharCode(view[0], view[1], view[2], view[3], view[4]);
    return header === 'solid';
  }

  /**
   * Parse ASCII STL format
   * @private
   */
  static _parseASCII(arrayBuffer) {
    const text = new TextDecoder().decode(arrayBuffer);
    const geometry = new THREE.BufferGeometry();
    const vertices = [];
    const normals = [];

    // Parse vertices and normals from ASCII format
    const vertexPattern = /vertex\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)/g;
    const normalPattern = /facet\s+normal\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)/g;

    let vertexMatch;
    let normalMatch;
    
    while ((vertexMatch = vertexPattern.exec(text))) {
      vertices.push(
        parseFloat(vertexMatch[1]),
        parseFloat(vertexMatch[3]),
        parseFloat(vertexMatch[5])
      );
    }

    // Generate normals for each triangle (3 vertices per face)
    for (let i = 0; i < vertices.length; i += 9) {
      const v1 = new THREE.Vector3(vertices[i], vertices[i + 1], vertices[i + 2]);
      const v2 = new THREE.Vector3(vertices[i + 3], vertices[i + 4], vertices[i + 5]);
      const v3 = new THREE.Vector3(vertices[i + 6], vertices[i + 7], vertices[i + 8]);

      const edge1 = v2.clone().sub(v1);
      const edge2 = v3.clone().sub(v1);
      const normal = edge1.cross(edge2).normalize();

      // Add normal for each vertex of the triangle
      normals.push(normal.x, normal.y, normal.z);
      normals.push(normal.x, normal.y, normal.z);
      normals.push(normal.x, normal.y, normal.z);
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(vertices), 3));
    geometry.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(normals), 3));
    geometry.computeBoundingBox();

    return geometry;
  }

  /**
   * Parse binary STL format
   * @private
   */
  static _parseBinary(view) {
    const geometry = new THREE.BufferGeometry();
    const vertices = [];
    const normals = [];

    // Binary STL format:
    // 80 byte header + 4 byte triangle count + triangles
    // Each triangle: 12 bytes normal + 36 bytes vertices (9 floats)

    const triangles = new Uint32Array(view.buffer, 80, 1)[0];
    let offset = 84; // After header and triangle count

    for (let i = 0; i < triangles; i++) {
      const dataView = new DataView(view.buffer);

      // Read normal (3 floats)
      const nx = dataView.getFloat32(offset, true);
      const ny = dataView.getFloat32(offset + 4, true);
      const nz = dataView.getFloat32(offset + 8, true);
      offset += 12;

      // Read vertices (3 vertices × 3 coordinates)
      for (let j = 0; j < 3; j++) {
        vertices.push(
          dataView.getFloat32(offset, true),
          dataView.getFloat32(offset + 4, true),
          dataView.getFloat32(offset + 8, true)
        );
        normals.push(nx, ny, nz);
        offset += 12;
      }

      // Skip attribute byte count
      offset += 2;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(vertices), 3));
    geometry.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(normals), 3));
    geometry.computeBoundingBox();

    return geometry;
  }

  /**
   * Get geometry bounding box info
   * @static
   */
  static getGeometryInfo(geometry) {
    geometry.computeBoundingBox();
    const bbox = geometry.boundingBox;
    const size = bbox.getSize(new THREE.Vector3());
    const center = bbox.getCenter(new THREE.Vector3());

    return {
      dimensions: {
        x: size.x.toFixed(2),
        y: size.y.toFixed(2),
        z: size.z.toFixed(2),
      },
      center: {
        x: center.x.toFixed(2),
        y: center.y.toFixed(2),
        z: center.z.toFixed(2),
      },
      volume: ((size.x * size.y * size.z) / 1000).toFixed(2), // in cm³
    };
  }
}
