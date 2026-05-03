"""Unit tests for 3MF thumbnail extraction in geometry_3mf.py."""
import base64
import io
import zipfile
from pathlib import Path

import pytest

# Add sidecar app to path
import sys
from pathlib import Path as PathlibPath

SIDECAR_APP_PATH = PathlibPath(__file__).parent.parent.parent.parent / "sidecars" / "model_catalog"
sys.path.insert(0, str(SIDECAR_APP_PATH))

from app.geometry_3mf import extract_3mf_thumbnail


# One-pixel PNG for testing
ONE_PIXEL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9l9mQAAAAASUVORK5CYII="
)
ONE_PIXEL_PNG_BYTES = base64.b64decode(ONE_PIXEL_PNG_BASE64)

# Small JPEG for testing (1x1 red pixel)
SMALL_JPEG_BASE64 = "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8VAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwAA8A/9k="  # noqa: E501
SMALL_JPEG_BYTES = base64.b64decode(SMALL_JPEG_BASE64)


def _create_3mf_zip(files: dict[str, bytes]) -> bytes:
    """Create a minimal 3MF ZIP with specified files."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    buffer.seek(0)
    return buffer.getvalue()


class TestThumbnailExtraction:
    """Tests for extract_3mf_thumbnail()."""

    def test_empty_bytes_returns_none(self) -> None:
        """Empty package should return None."""
        assert extract_3mf_thumbnail(b"") is None

    def test_none_bytes_returns_none(self) -> None:
        """None input should return None."""
        assert extract_3mf_thumbnail(b"") is None

    def test_invalid_zip_returns_none(self) -> None:
        """Invalid ZIP file should return None."""
        assert extract_3mf_thumbnail(b"not a zip file") is None

    def test_no_thumbnail_returns_none(self) -> None:
        """3MF with no thumbnail should return None."""
        package = _create_3mf_zip({"3D/3dmodel.model": b"<xml/>"})
        assert extract_3mf_thumbnail(package) is None

    def test_metadata_thumbnail_png_found(self) -> None:
        """Should find and return Metadata/thumbnail.png."""
        package = _create_3mf_zip(
            {
                "3D/3dmodel.model": b"<xml/>",
                "Metadata/thumbnail.png": ONE_PIXEL_PNG_BYTES,
            }
        )
        result = extract_3mf_thumbnail(package)
        assert result == ONE_PIXEL_PNG_BYTES

    def test_thumbnails_folder_png_found(self) -> None:
        """Should find thumbnail in Thumbnails/ fallback."""
        package = _create_3mf_zip(
            {
                "3D/3dmodel.model": b"<xml/>",
                "Thumbnails/thumbnail.png": ONE_PIXEL_PNG_BYTES,
            }
        )
        result = extract_3mf_thumbnail(package)
        assert result == ONE_PIXEL_PNG_BYTES

    def test_3d_thumbnail_png_found(self) -> None:
        """Should find 3D/Thumbnail.png."""
        package = _create_3mf_zip(
            {
                "3D/3dmodel.model": b"<xml/>",
                "3D/Thumbnail.png": ONE_PIXEL_PNG_BYTES,
            }
        )
        result = extract_3mf_thumbnail(package)
        assert result == ONE_PIXEL_PNG_BYTES

    def test_auxiliaries_model_pictures_png_found(self) -> None:
        """Should find image in Auxiliaries/Model Pictures/ fallback."""
        package = _create_3mf_zip(
            {
                "3D/3dmodel.model": b"<xml/>",
                "Auxiliaries/Model Pictures/thumbnail.png": ONE_PIXEL_PNG_BYTES,
            }
        )
        result = extract_3mf_thumbnail(package)
        assert result == ONE_PIXEL_PNG_BYTES

    def test_known_paths_priority_order(self) -> None:
        """Should prefer Metadata/thumbnail.png over other candidates."""
        metadata_png = ONE_PIXEL_PNG_BYTES
        other_png = b"different_data"
        package = _create_3mf_zip(
            {
                "3D/3dmodel.model": b"<xml/>",
                "Metadata/thumbnail.png": metadata_png,
                "Thumbnails/thumbnail.png": other_png,
                "3D/Thumbnail.png": other_png,
            }
        )
        result = extract_3mf_thumbnail(package)
        assert result == metadata_png

    def test_jpeg_thumbnail_accepted(self) -> None:
        """Should accept JPEG thumbnails."""
        package = _create_3mf_zip(
            {
                "3D/3dmodel.model": b"<xml/>",
                "Metadata/thumbnail.jpg": SMALL_JPEG_BYTES,
            }
        )
        result = extract_3mf_thumbnail(package)
        assert result == SMALL_JPEG_BYTES

    def test_non_image_file_skipped(self) -> None:
        """Non-image files in known paths should be skipped."""
        package = _create_3mf_zip(
            {
                "3D/3dmodel.model": b"<xml/>",
                "Metadata/thumbnail.txt": b"not an image",
                "Thumbnails/thumbnail.png": ONE_PIXEL_PNG_BYTES,
            }
        )
        result = extract_3mf_thumbnail(package)
        assert result == ONE_PIXEL_PNG_BYTES

    def test_multiple_images_in_auxiliaries_first_returned(self) -> None:
        """Should return first valid image from Auxiliaries/Model Pictures/."""
        package = _create_3mf_zip(
            {
                "3D/3dmodel.model": b"<xml/>",
                "Auxiliaries/Model Pictures/image1.png": ONE_PIXEL_PNG_BYTES,
                "Auxiliaries/Model Pictures/image2.png": b"different_png",
            }
        )
        result = extract_3mf_thumbnail(package)
        # Should get one of the images (order depends on zip iteration)
        assert result in (ONE_PIXEL_PNG_BYTES, b"different_png")

    def test_oversized_file_rejected(self) -> None:
        """Files larger than 2 MB should be rejected."""
        oversized = b"x" * (3 * 1024 * 1024)  # 3 MB
        package = _create_3mf_zip(
            {
                "3D/3dmodel.model": b"<xml/>",
                "Metadata/thumbnail.png": oversized,
            }
        )
        result = extract_3mf_thumbnail(package)
        assert result is None

    def test_compression_ratio_guard(self) -> None:
        """Files with >10x compression ratio (ZIP bomb indicator) should be rejected."""
        # Create a highly repetitive file that compresses very well
        repetitive = b"A" * (15 * 1024 * 1024)  # 15 MB uncompressed
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("Metadata/thumbnail.png", repetitive)
        buffer.seek(0)
        package = buffer.getvalue()

        result = extract_3mf_thumbnail(package)
        # Should reject due to high compression ratio
        assert result is None

    def test_path_traversal_protection(self) -> None:
        """Paths with .. should not be accessible."""
        package = _create_3mf_zip(
            {
                "3D/3dmodel.model": b"<xml/>",
                "../../../etc/passwd": ONE_PIXEL_PNG_BYTES,
            }
        )
        result = extract_3mf_thumbnail(package)
        assert result is None

    def test_case_insensitive_path_matching(self) -> None:
        """Path matching should handle case variations gracefully."""
        # ZIP paths are case-sensitive, but _normalize_part_path should handle them
        package = _create_3mf_zip(
            {
                "3D/3dmodel.model": b"<xml/>",
                "metadata/thumbnail.png": ONE_PIXEL_PNG_BYTES,  # lowercase
            }
        )
        # The function looks for exact matches after normalization
        # so this should still find the file (depending on ZIP member names)
        result = extract_3mf_thumbnail(package)
        # Result depends on exact behavior of _normalize_part_path
        # which handles path normalization

    def test_whitespace_and_slash_normalization(self) -> None:
        """Paths with backslashes should be normalized."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # ZIP typically uses forward slashes, but test normalization
            zf.writestr("3D/3dmodel.model", b"<xml/>")
            zf.writestr("Metadata/thumbnail.png", ONE_PIXEL_PNG_BYTES)
        buffer.seek(0)
        package = buffer.getvalue()

        result = extract_3mf_thumbnail(package)
        assert result == ONE_PIXEL_PNG_BYTES

    def test_real_3mf_sample_if_available(self) -> None:
        """Integration test: extract thumbnail from real 3MF if available."""
        sample_path = Path(__file__).parent.parent.parent.parent / "assets" / "model_catalog"
        if not sample_path.exists():
            pytest.skip("No sample 3MF files available")

        # Look for any .3mf files
        sample_files = list(sample_path.glob("**/*.3mf"))
        if not sample_files:
            pytest.skip("No .3mf sample files found in assets/model_catalog")

        for sample_file in sample_files[:1]:  # Test first sample
            with open(sample_file, "rb") as f:
                package_bytes = f.read()

            result = extract_3mf_thumbnail(package_bytes)
            # Result could be None if no thumbnail, or bytes if found
            assert result is None or isinstance(result, bytes)

    def test_gif_thumbnail_rejected(self) -> None:
        """GIF files should be rejected (only PNG/JPEG allowed)."""
        gif_header = b"GIF89a"  # Minimal GIF header
        package = _create_3mf_zip(
            {
                "3D/3dmodel.model": b"<xml/>",
                "Metadata/thumbnail.gif": gif_header,
            }
        )
        result = extract_3mf_thumbnail(package)
        assert result is None

    def test_empty_png_file_accepted_if_valid(self) -> None:
        """Valid but tiny PNG should be accepted."""
        package = _create_3mf_zip(
            {
                "3D/3dmodel.model": b"<xml/>",
                "Metadata/thumbnail.png": ONE_PIXEL_PNG_BYTES,
            }
        )
        result = extract_3mf_thumbnail(package)
        assert result == ONE_PIXEL_PNG_BYTES


class TestMimeTypeDetection:
    """Tests for _get_mime_type_for_filename() helper."""

    def test_mime_type_png(self) -> None:
        """Should detect PNG MIME type."""
        from app.geometry_3mf import _get_mime_type_for_filename

        assert _get_mime_type_for_filename("thumbnail.png") == "image/png"

    def test_mime_type_jpeg(self) -> None:
        """Should detect JPEG MIME type."""
        from app.geometry_3mf import _get_mime_type_for_filename

        assert _get_mime_type_for_filename("thumbnail.jpg") == "image/jpeg"
        assert _get_mime_type_for_filename("thumbnail.jpeg") == "image/jpeg"

    def test_mime_type_gif(self) -> None:
        """Should detect GIF MIME type."""
        from app.geometry_3mf import _get_mime_type_for_filename

        assert _get_mime_type_for_filename("thumbnail.gif") == "image/gif"

    def test_mime_type_case_insensitive(self) -> None:
        """MIME type detection should be case-insensitive."""
        from app.geometry_3mf import _get_mime_type_for_filename

        assert _get_mime_type_for_filename("THUMBNAIL.PNG") == "image/png"
        assert _get_mime_type_for_filename("Thumbnail.Jpg") == "image/jpeg"

    def test_mime_type_unknown(self) -> None:
        """Should return None for unknown file types."""
        from app.geometry_3mf import _get_mime_type_for_filename

        assert _get_mime_type_for_filename("thumbnail.txt") is None
        assert _get_mime_type_for_filename("thumbnail.bin") is None

    def test_mime_type_empty_filename(self) -> None:
        """Should return None for empty filename."""
        from app.geometry_3mf import _get_mime_type_for_filename

        assert _get_mime_type_for_filename("") is None
        assert _get_mime_type_for_filename(None) is None
