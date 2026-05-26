"""HTTP bridge to the Bambuddy archive API.

Provides thin wrappers around the Bambuddy ``/api/v1/archives`` endpoints
used by the slicer commit-archive workflow:

  POST   /api/v1/archives/upload?printer_id={id}  → multipart .gcode.3mf upload
  PATCH  /api/v1/archives/{id}                     → metadata update
  POST   /api/v1/archives/{id}/source              → multipart source .3mf upload
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_SOURCE_3MF_MIME = "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArchiveUploadResult:
    """Response from ``POST /api/v1/archives/upload``."""

    archive_id: int
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArchivePatchResult:
    """Response from ``PATCH /api/v1/archives/{id}``."""

    archive_id: int
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceAttachResult:
    """Response from ``POST /api/v1/archives/{id}/source``."""

    archive_id: int
    filename: str
    raw_response: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BambuddyBridgeError(Exception):
    """Base error for Bambuddy bridge operations."""


class BambuddyUpstreamError(BambuddyBridgeError):
    """Bambuddy API returned an error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_headers(api_key: str | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _raise_upstream_error(operation: str, resp: httpx.Response) -> None:
    try:
        detail = resp.json()
    except Exception:
        detail = resp.text
    msg = f"{operation} failed (HTTP {resp.status_code}): {detail}"
    raise BambuddyUpstreamError(msg, status_code=resp.status_code)


# ---------------------------------------------------------------------------
# Bridge functions
# ---------------------------------------------------------------------------


def upload_archive(
    *,
    base_url: str,
    api_key: str | None,
    gcode_3mf_path: Path,
    printer_id: int | str,
    timeout: float = 120.0,
) -> ArchiveUploadResult:
    """Upload a ``.gcode.3mf`` to create a new Bambuddy archive.

    Calls ``POST /api/v1/archives/upload?printer_id={printer_id}`` with
    multipart file upload.
    """
    url = f"{base_url.rstrip('/')}/api/v1/archives/upload"
    headers = _build_headers(api_key)

    with httpx.Client(timeout=timeout) as client:
        with open(gcode_3mf_path, "rb") as f:
            resp = client.post(
                url,
                params={"printer_id": str(printer_id)},
                headers=headers,
                files={"file": (gcode_3mf_path.name, f, "application/octet-stream")},
            )

    if resp.status_code in (200, 201):
        body = resp.json()
        archive_id = body.get("id") or body.get("archive_id")
        if archive_id is None:
            raise BambuddyBridgeError(
                f"Archive upload succeeded but response missing id: {body}"
            )
        return ArchiveUploadResult(
            archive_id=int(archive_id),
            raw_response=body,
        )

    _raise_upstream_error("Archive upload", resp)
    raise AssertionError("unreachable")  # _raise_upstream_error always raises


def patch_archive(
    *,
    base_url: str,
    api_key: str | None,
    archive_id: int,
    patch_body: dict[str, Any],
    timeout: float = 30.0,
) -> ArchivePatchResult:
    """Update metadata on an existing archive.

    Calls ``PATCH /api/v1/archives/{archive_id}`` with a JSON body.
    """
    url = f"{base_url.rstrip('/')}/api/v1/archives/{archive_id}"
    headers = _build_headers(api_key)
    headers["Content-Type"] = "application/json"

    with httpx.Client(timeout=timeout) as client:
        resp = client.patch(url, headers=headers, json=patch_body)

    if resp.status_code == 200:
        return ArchivePatchResult(
            archive_id=archive_id,
            raw_response=resp.json(),
        )

    _raise_upstream_error("Archive patch", resp)
    raise AssertionError("unreachable")


def attach_source(
    *,
    base_url: str,
    api_key: str | None,
    archive_id: int,
    source_3mf_path: Path,
    timeout: float = 120.0,
) -> SourceAttachResult:
    """Attach a source ``.3mf`` to an existing archive.

    Calls ``POST /api/v1/archives/{archive_id}/source`` with multipart
    file upload.
    """
    url = f"{base_url.rstrip('/')}/api/v1/archives/{archive_id}/source"
    headers = _build_headers(api_key)

    with httpx.Client(timeout=timeout) as client:
        with open(source_3mf_path, "rb") as f:
            resp = client.post(
                url,
                headers=headers,
                files={"file": (source_3mf_path.name, f, _SOURCE_3MF_MIME)},
            )

    if resp.status_code in (200, 201):
        body = resp.json()
        return SourceAttachResult(
            archive_id=archive_id,
            filename=body.get("filename") or source_3mf_path.name,
            raw_response=body,
        )

    _raise_upstream_error("Source attachment", resp)
    raise AssertionError("unreachable")
