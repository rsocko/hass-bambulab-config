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
        assert fits is False
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


# Helper functions (would be implemented)

def parse_stl_binary(data):
    """Parse binary STL"""
    pass

def parse_stl_ascii(data):
    """Parse ASCII STL"""
    pass

def detect_stl_format(data):
    """Detect STL format"""
    pass

def compute_normals(vertices):
    """Compute vertex normals"""
    pass

def calculate_bounding_box(vertices):
    """Calculate bounding box"""
    pass

def center_geometry(vertices):
    """Center geometry at origin"""
    pass

def calculate_center(vertices):
    """Calculate center point"""
    pass

def calculate_camera_fit(bbox, fov):
    """Calculate camera position"""
    pass

def get_geometry_info(geometry):
    """Get geometry info"""
    pass

def create_build_volume():
    """Create build volume"""
    pass

def check_model_fits(bbox, build_volume_size):
    """Check if model fits"""
    pass

def generate_fit_message(bbox):
    """Generate fit message"""
    pass

def rotate_camera(pos, dx, dy):
    """Rotate camera"""
    pass

def zoom_camera(z, delta):
    """Zoom camera"""
    pass

def pan_camera(target, dx, dy):
    """Pan camera"""
    pass

def reset_camera_view(bbox):
    """Reset camera view"""
    pass

def call_geometry_endpoint(model_ref, file_id):
    """Call geometry endpoint"""
    pass
