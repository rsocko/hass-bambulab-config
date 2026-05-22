"""Unit tests for 3MF source metadata URL extraction/cleanup."""

import io
import sys
import zipfile
from pathlib import Path as PathlibPath


SIDECAR_APP_PATH = PathlibPath(__file__).parent.parent.parent.parent / "sidecars" / "model_catalog"
sys.path.insert(0, str(SIDECAR_APP_PATH))

from app.geometry_3mf import extract_3mf_source_metadata


def _create_3mf_with_metadata(metadata_entries: dict[str, str]) -> bytes:
    metadata_xml = "".join(
        f'<metadata name="{name}">{value}</metadata>' for name, value in metadata_entries.items()
    )
    model_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<model unit=\"millimeter\" xmlns=\"http://schemas.microsoft.com/3dmanufacturing/core/2015/02\">"
        f"{metadata_xml}"
        "</model>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("3D/3dmodel.model", model_xml.encode("utf-8"))
    buffer.seek(0)
    return buffer.getvalue()


def test_extract_source_urls_trims_trailing_html_entity_quote_fragment() -> None:
    package = _create_3mf_with_metadata(
        {
            "Application": "PrusaSlicer 2.7",
            "Description": "Download: https://example.com/model&amp;#34;",
        }
    )

    metadata = extract_3mf_source_metadata(package)

    assert metadata is not None
    assert metadata["source_urls"] == ["https://example.com/model"]
    assert metadata["source_url"] == "https://example.com/model"


def test_extract_source_urls_trims_trailing_html_quot_entity() -> None:
    package = _create_3mf_with_metadata(
        {
            "Application": "PrusaSlicer 2.7",
            "Description": "Source https://example.com/item&amp;quot;",
        }
    )

    metadata = extract_3mf_source_metadata(package)

    assert metadata is not None
    assert metadata["source_urls"] == ["https://example.com/item"]
    assert metadata["source_url"] == "https://example.com/item"


def test_extract_source_urls_keeps_valid_query_and_hash_content() -> None:
    package = _create_3mf_with_metadata(
        {
            "Application": "PrusaSlicer 2.7",
            "Description": "Ref https://example.com/model?id=34#section-34",
        }
    )

    metadata = extract_3mf_source_metadata(package)

    assert metadata is not None
    assert metadata["source_urls"] == ["https://example.com/model?id=34#section-34"]
