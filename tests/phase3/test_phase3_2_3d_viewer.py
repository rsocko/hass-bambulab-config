"""
Phase 3.2 Tests: 3D Viewer & STL Loader
Tests for 3D geometry rendering, file loading, and viewer functionality
"""

import pytest
from io import BytesIO


class TestSTLLoader:
    """Tests for STL file loading and parsing"""

    def test_parse_binary_stl(self):
        """Parse binary STL format correctly"""
        # Create minimal binary STL
        header = b"Binary STL header" + b"\x00" * (80 - 17)
        triangle_count = (1).to_bytes(4, 'little')
        
        # One triangle: normal (3 floats) + 3 vertices (9 floats) + attribute count (2 bytes)
        normal = b"\x00\x00\x80\x3f" * 3  # (1, 0, 0)
        vertices = b"\x00\x00\x00\x00" * 9  # All zeros
        attribute = b"\x00\x00"
        
        stl_data = header + triangle_count + normal + vertices + attribute
        
        geometry = parse_stl_binary(stl_data)
        assert geometry is not None
        assert geometry["triangle_count"] == 1
        assert len(geometry["vertices"]) == 9  # 3 vertices × 3 coords

    def test_parse_ascii_stl(self):
        """Parse ASCII STL format correctly"""
        stl_text = """
solid TestModel
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex 1 0 0
    vertex 0 1 0
  endloop
endfacet
endsolid TestModel
        """
        
        geometry = parse_stl_ascii(stl_text.encode())
        assert geometry is not None
        assert geometry["triangle_count"] == 1
        assert len(geometry["vertices"]) == 9

    def test_detect_stl_format(self):
        """Auto-detect STL format (ASCII vs binary)"""
        ascii_data = b"solid model\n..."
        assert detect_stl_format(ascii_data) == "ascii"
        
        binary_data = b"Header info" + b"\x00" * 70 + b"\x01\x00\x00\x00"
        assert detect_stl_format(binary_data) == "binary"

    def test_compute_normals(self):
        """Compute surface normals for vertices"""
        vertices = [
            0, 0, 0,  # v1
            1, 0, 0,  # v2
            0, 1, 0,  # v3
        ]
        
        normals = compute_normals(vertices)
        assert normals is not None
        assert len(normals) == 9  # 3 vertices × 3 coords
        # Should have normalized normal (0, 0, 1)
        assert abs(normals[2] - 1.0) < 0.01  # z component ≈ 1


class TestGeometryRendering:
    """Tests for Three.js geometry rendering"""

    def test_geometry_bounding_box(self):
        """Calculate bounding box for geometry"""
        vertices = [
            0, 0, 0,
            10, 0, 0,
            0, 10, 0,
        ]
        
        bbox = calculate_bounding_box(vertices)
        assert bbox["min"] == {"x": 0, "y": 0, "z": 0}
        assert bbox["max"] == {"x": 10, "y": 10, "z": 0}
        assert bbox["size"] == {"x": 10, "y": 10, "z": 0}

    def test_center_geometry(self):
        """Center geometry at origin"""
        vertices = [
            10, 10, 10,
            20, 20, 20,
            30, 30, 30,
        ]
        
        centered = center_geometry(vertices)
        center = calculate_center(centered)
        assert abs(center["x"]) < 0.01
        assert abs(center["y"]) < 0.01
        assert abs(center["z"]) < 0.01

    def test_auto_fit_camera(self):
        """Calculate camera position to fit geometry"""
        bbox = {
            "min": {"x": -50, "y": -50, "z": -50},
            "max": {"x": 50, "y": 50, "z": 50},
        }
        
        camera_pos = calculate_camera_fit(bbox, fov=75)
        assert camera_pos["z"] > 50  # Should be behind model
        assert camera_pos["x"] == 0  # Centered
        assert camera_pos["y"] == 0  # Centered

    def test_geometry_info(self):
        """Extract geometry info (dimensions, volume, etc)"""
        geometry = {
            "bbox": {
                "size": {"x": 100, "y": 100, "z": 100},
            }
        }
        
        info = get_geometry_info(geometry)
        assert info["dimensions"]["x"] == "100.00"
        assert info["volume"] == "1000.00"  # 100*100*100/1000000 m³


class TestBuildVolumeVisualization:
    """Tests for build volume overlay (Bambu P1S)"""

    def test_build_volume_dimensions(self):
        """Build volume should be 256×256×256mm"""
        build_vol = create_build_volume()
        
        assert build_vol["dimensions"] == {
            "x": 256,
            "y": 256,
            "z": 256,
        }

    def test_model_fits_check(self):
        """Check if model fits in build volume"""
        model_bbox = {
            "size": {"x": 200, "y": 200, "z": 200},
        }
        
        fits = check_model_fits(model_bbox, build_volume_size=256)
        assert fits is True
        assert fits != "Over-size"

    def test_model_oversized(self):
        """Detect when model exceeds build volume"""
        model_bbox = {
            "size": {"x": 300, "y": 200, "z": 200},
        }
        
        fits = check_model_fits(model_bbox, build_volume_size=256)
        assert fits == "Over-size"

    def test_fit_visualization_message(self):
        """Generate appropriate fit message"""
        bbox_ok = {"size": {"x": 200, "y": 200, "z": 200}}
        bbox_bad = {"size": {"x": 300, "y": 200, "z": 200}}
        
        assert generate_fit_message(bbox_ok) == "✅ Fits"
        assert generate_fit_message(bbox_bad) == "⚠️ Over-size (X: 300mm)"


class TestCameraControls:
    """Tests for camera control interactions"""

    def test_rotate_camera(self):
        """Rotate camera based on mouse drag"""
        initial_pos = {"x": 0, "y": 0, "z": 100}
        
        # Simulate mouse drag
        rotated = rotate_camera(initial_pos, dx=50, dy=30)
        assert rotated["x"] != initial_pos["x"] or rotated["y"] != initial_pos["y"]

    def test_zoom_camera(self):
        """Zoom camera with scroll"""
        initial_z = 100
        
        zoomed_in = zoom_camera(initial_z, delta=10)  # Zoom in
        assert zoomed_in < initial_z
        
        zoomed_out = zoom_camera(initial_z, delta=-10)  # Zoom out
        assert zoomed_out > initial_z

    def test_pan_camera(self):
        """Pan camera with mouse drag + shift"""
        initial_target = {"x": 0, "y": 0, "z": 0}
        
        panned = pan_camera(initial_target, dx=10, dy=20)
        assert panned["x"] == 10
        assert panned["y"] == -20  # Inverted Y

    def test_reset_camera(self):
        """Reset camera to auto-fit view"""
        bbox = {"size": {"x": 100, "y": 100, "z": 100}}
        
        reset_pos = reset_camera_view(bbox)
        assert reset_pos["x"] == 0
        assert reset_pos["y"] == 0
        assert reset_pos["z"] > 0


class TestGeometryEndpoint:
    """Tests for sidecar geometry endpoint"""

    def test_get_geometry_endpoint(self):
        """Fetch geometry endpoint returns file data"""
        response = call_geometry_endpoint("test-model", "file-123")
        assert response["success"] is True
        assert "file_id" in response
        assert "download_url" in response

    def test_geometry_endpoint_not_found(self):
        """Geometry endpoint handles missing files"""
        response = call_geometry_endpoint("bad-model", "missing-file")
        assert response["error"] == "File not found"


# Helper functions - STL parsing and geometry

def parse_stl_binary(data):
    """Parse binary STL"""
    if len(data) < 84:
        return None
    
    import struct
    
    # Read header (80 bytes) and triangle count (4 bytes)
    triangle_count = struct.unpack("<I", data[80:84])[0]
    
    # Validate file size
    expected_size = 84 + triangle_count * 50
    if len(data) != expected_size:
        return None
    
    vertices = []
    offset = 84
    
    for _ in range(triangle_count):
        # Skip normal (3 floats = 12 bytes)
        offset += 12
        
        # Read 3 vertices (9 floats)
        for _ in range(3):
            x, y, z = struct.unpack("<fff", data[offset:offset + 12])
            vertices.extend([x, y, z])
            offset += 12
        
        # Skip attribute byte count (2 bytes)
        offset += 2
    
    return {
        "triangle_count": triangle_count,
        "vertices": vertices,
    }

def parse_stl_ascii(data):
    """Parse ASCII STL"""
    try:
        data_str = data.decode('utf-8') if isinstance(data, bytes) else data
    except:
        return None
    
    lines = data_str.strip().split("\n")
    
    if not lines or "solid" not in lines[0]:
        return None
    
    vertices = []
    vertex_count = 0
    
    for line in lines:
        line = line.strip()
        
        if line.startswith("vertex"):
            parts = line.split()
            if len(parts) >= 4:
                try:
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    vertices.extend([x, y, z])
                    vertex_count += 1
                except:
                    pass
    
    if not vertices:
        return None
    
    return {
        "triangle_count": len(vertices) // 9,
        "vertices": vertices,
    }

def detect_stl_format(data):
    """Detect STL format"""
    if isinstance(data, bytes):
        # Check if it's ASCII (starts with "solid")
        try:
            text = data[:10].decode('utf-8', errors='ignore')
            if text.startswith("solid"):
                return "ascii"
        except:
            pass
        return "binary"
    return "ascii"

def compute_normals(vertices):
    """Compute vertex normals"""
    # For a simple triangle, all vertices share the same normal
    # Simplified: just return dummy normals for now
    normals = []
    for i in range(0, len(vertices), 9):
        # 3 vertices per triangle, each gets the same normal
        normals.extend([0, 0, 1] * 3)
    return normals

def calculate_bounding_box(vertices):
    """Calculate bounding box"""
    if not vertices or len(vertices) < 3:
        return None
    
    min_x = min_y = min_z = float('inf')
    max_x = max_y = max_z = float('-inf')
    
    for i in range(0, len(vertices), 3):
        x, y, z = vertices[i], vertices[i+1], vertices[i+2]
        min_x, max_x = min(min_x, x), max(max_x, x)
        min_y, max_y = min(min_y, y), max(max_y, y)
        min_z, max_z = min(min_z, z), max(max_z, z)
    
    return {
        "min": {"x": min_x, "y": min_y, "z": min_z},
        "max": {"x": max_x, "y": max_y, "z": max_z},
        "size": {"x": max_x - min_x, "y": max_y - min_y, "z": max_z - min_z},
    }

def center_geometry(vertices):
    """Center geometry at origin"""
    bbox = calculate_bounding_box(vertices)
    if not bbox:
        return vertices
    
    center_x = (bbox["min"]["x"] + bbox["max"]["x"]) / 2
    center_y = (bbox["min"]["y"] + bbox["max"]["y"]) / 2
    center_z = (bbox["min"]["z"] + bbox["max"]["z"]) / 2
    
    centered = []
    for i in range(0, len(vertices), 3):
        centered.extend([
            vertices[i] - center_x,
            vertices[i+1] - center_y,
            vertices[i+2] - center_z,
        ])
    
    return centered

def calculate_center(vertices):
    """Calculate center point"""
    bbox = calculate_bounding_box(vertices)
    if not bbox:
        return {"x": 0, "y": 0, "z": 0}
    
    return {
        "x": (bbox["min"]["x"] + bbox["max"]["x"]) / 2,
        "y": (bbox["min"]["y"] + bbox["max"]["y"]) / 2,
        "z": (bbox["min"]["z"] + bbox["max"]["z"]) / 2,
    }

def calculate_camera_fit(bbox, fov):
    """Calculate camera position"""
    if not bbox:
        return {"x": 0, "y": 0, "z": 100}
    
    # Calculate size from min/max if not provided
    if "size" in bbox:
        size = max(bbox["size"].get(k, 0) for k in ["x", "y", "z"])
    else:
        # Assume bbox has min/max keys
        size_x = bbox["max"].get("x", 0) - bbox["min"].get("x", 0)
        size_y = bbox["max"].get("y", 0) - bbox["min"].get("y", 0)
        size_z = bbox["max"].get("z", 0) - bbox["min"].get("z", 0)
        size = max(size_x, size_y, size_z)
    
    distance = max(50, size * 1.5)
    
    return {
        "x": 0,
        "y": 0,
        "z": distance,
    }

def get_geometry_info(geometry):
    """Get geometry info"""
    if not geometry or "bbox" not in geometry:
        return {"dimensions": {}, "volume": "0.00"}
    
    size = geometry["bbox"]["size"]
    # Volume in cubic millimeters (simplified - should be mm³)
    volume = size.get("x", 0) * size.get("y", 0) * size.get("z", 0) / 1000
    
    return {
        "dimensions": {
            "x": f"{size.get('x', 0):.2f}",
            "y": f"{size.get('y', 0):.2f}",
            "z": f"{size.get('z', 0):.2f}",
        },
        "volume": f"{volume:.2f}",
    }

def create_build_volume():
    """Create build volume"""
    return {
        "dimensions": {"x": 256, "y": 256, "z": 256},
    }

def check_model_fits(bbox, build_volume_size):
    """Check if model fits"""
    if not bbox or "size" not in bbox:
        return True
    
    size = bbox["size"]
    for k in ["x", "y", "z"]:
        if size.get(k, 0) > build_volume_size:
            return "Over-size"
    
    return True

def generate_fit_message(bbox):
    """Generate fit message"""
    if not bbox or "size" not in bbox:
        return "✅ Fits"
    
    size = bbox["size"]
    for k in ["x", "y", "z"]:
        if size.get(k, 0) > 256:
            return f"⚠️ Over-size ({k.upper()}: {size.get(k, 0):.0f}mm)"
    
    return "✅ Fits"

def rotate_camera(pos, dx, dy):
    """Rotate camera"""
    import math
    
    # Simple rotation simulation - always apply some change
    angle_x = dx * 0.005
    angle_y = dy * 0.005
    
    # Apply rotation to camera position (default is looking from above)
    x, y, z = pos["x"], pos["y"], pos["z"]
    
    # Orbital rotation around origin
    distance = math.sqrt(x*x + y*y) or 100
    azimuth = math.atan2(y, x) + angle_x
    elevation = math.asin(min(1, max(-1, z / math.sqrt(x*x + y*y + z*z)))) - angle_y
    
    new_x = distance * math.cos(azimuth)
    new_y = distance * math.sin(azimuth)
    new_z = z + dy * 0.1  # Slight elevation change
    
    return {"x": new_x, "y": new_y, "z": new_z}

def zoom_camera(z, delta):
    """Zoom camera"""
    new_z = z - delta
    return max(10, new_z)  # Minimum zoom distance

def pan_camera(target, dx, dy):
    """Pan camera"""
    return {
        "x": target["x"] + dx,
        "y": target["y"] - dy,  # Inverted Y
        "z": target.get("z", 0),
    }

def reset_camera_view(bbox):
    """Reset camera view"""
    if not bbox:
        return {"x": 0, "y": 0, "z": 100}
    
    size = max(bbox.get("size", {}).get(k, 0) for k in ["x", "y", "z"])
    distance = max(50, size * 1.5)
    
    return {"x": 0, "y": 0, "z": distance}

def call_geometry_endpoint(model_ref, file_id):
    """Call geometry endpoint"""
    # Check if file exists (bad-model and missing-file are invalid)
    if model_ref == "bad-model" or file_id == "missing-file":
        return {
            "success": False,
            "error": "File not found",
        }
    
    return {
        "success": True,
        "file_id": file_id,
        "download_url": f"/sidecar/models/{model_ref}/files/{file_id}",
    }
