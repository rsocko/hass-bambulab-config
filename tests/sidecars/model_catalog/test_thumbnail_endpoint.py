"""Tests for thumbnail endpoint in model_media.py."""
import base64
import io
import json
import zipfile
from unittest.mock import MagicMock, patch

import pytest

# One-pixel PNG for testing
ONE_PIXEL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9l9mQAAAAASUVORK5CYII="
)
ONE_PIXEL_PNG_BYTES = base64.b64decode(ONE_PIXEL_PNG_BASE64)


def _create_3mf_with_thumbnail(thumbnail_bytes: bytes | None = None) -> bytes:
    """Create a minimal 3MF file with optional embedded thumbnail."""
    if thumbnail_bytes is None:
        thumbnail_bytes = ONE_PIXEL_PNG_BYTES
    
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("3D/3dmodel.model", b"<xml/>")
        zf.writestr("Metadata/thumbnail.png", thumbnail_bytes)
    buffer.seek(0)
    return buffer.getvalue()


class TestThumbnailEndpoint:
    """Tests for GET /api/models/{model_ref}/files/{file_id}/thumbnail endpoint."""

    def test_thumbnail_endpoint_import(self):
        """Should be able to import thumbnail endpoint."""
        from app.routers.models_media import get_model_file_thumbnail_endpoint
        
        assert get_model_file_thumbnail_endpoint is not None
        assert callable(get_model_file_thumbnail_endpoint)

    def test_thumbnail_service_import(self):
        """Verify thumbnail service can be imported."""
        from app.services.model_media_service import get_model_file_thumbnail_service
        
        assert get_model_file_thumbnail_service is not None
        assert callable(get_model_file_thumbnail_service)

    def test_thumbnail_endpoint_signature(self):
        """Verify endpoint has correct signature."""
        from app.routers.models_media import get_model_file_thumbnail_endpoint
        import inspect
        
        sig = inspect.signature(get_model_file_thumbnail_endpoint)
        params = list(sig.parameters.keys())
        
        assert "request" in params
        assert "model_ref" in params
        assert "file_id" in params


class TestThumbnailExtraction:
    """Tests for 3MF thumbnail extraction integration."""

    def test_extract_thumbnail_from_3mf(self):
        """Verify thumbnail can be extracted from a 3MF package."""
        from app.geometry_3mf import extract_3mf_thumbnail
        
        package_bytes = _create_3mf_with_thumbnail()
        thumbnail = extract_3mf_thumbnail(package_bytes)
        
        assert thumbnail is not None
        assert thumbnail == ONE_PIXEL_PNG_BYTES

    def test_extract_thumbnail_not_found(self):
        """Verify extraction returns None when no thumbnail."""
        from app.geometry_3mf import extract_3mf_thumbnail
        
        # Create 3MF without thumbnail
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("3D/3dmodel.model", b"<xml/>")
        buffer.seek(0)
        package_bytes = buffer.getvalue()
        
        thumbnail = extract_3mf_thumbnail(package_bytes)
        assert thumbnail is None

    def test_mime_type_detection_png(self):
        """Verify PNG MIME type detection."""
        from app.geometry_3mf import _get_mime_type_for_filename
        
        assert _get_mime_type_for_filename("thumbnail.png") == "image/png"

    def test_mime_type_detection_jpeg(self):
        """Verify JPEG MIME type detection."""
        from app.geometry_3mf import _get_mime_type_for_filename
        
        assert _get_mime_type_for_filename("thumbnail.jpg") == "image/jpeg"

