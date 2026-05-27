"""HTTP bridge to the upstream Bambu Studio / OrcaSlicer API sidecar.

Provides thin wrappers around the upstream ``/slice-async`` endpoints.
Each function is stateless; slicer-job lifecycle is managed by the
caller (router + db_slicer_jobs).

Upstream API contract (from swagger.json):
  POST   /slice-async                  → 202 {requestId, status, statusUrl}
  GET    /slice-async/{requestId}      → 200 {requestId, status, metadata?, downloadUrl?, message?}
  GET    /slice-async/{requestId}/result → 200 binary (gcode / 3mf / zip)

MIME types: The upstream validates file type via the multipart Content-Type
header, so we map known 3D-file extensions to their proper MIME types.
  DELETE /slice-async/{requestId}      → 204
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn

import httpx

logger = logging.getLogger(__name__)

_MIME_TYPES: dict[str, str] = {
    ".3mf": "model/3mf",
    ".stl": "model/stl",
    ".step": "model/step",
    ".stp": "model/step",
}


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SliceEnqueueResult:
    """Response from ``POST /slice-async``."""

    request_id: str
    status: str
    status_url: str


@dataclass(frozen=True)
class SlicePollResult:
    """Response from ``GET /slice-async/{requestId}``."""

    request_id: str
    status: str  # pending | processing | completed | failed
    metadata: dict[str, Any] | None = None
    download_url: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class SliceOutputResult:
    """Result of downloading sliced output."""

    output_path: Path
    sha256: str
    content_length: int
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SlicerBridgeError(Exception):
    """Base error for slicer bridge operations."""


class SlicerUpstreamError(SlicerBridgeError):
    """Upstream slicer API returned an error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class SlicerTimeoutError(SlicerBridgeError):
    """Polling exceeded the configured deadline."""


# ---------------------------------------------------------------------------
# Bridge functions
# ---------------------------------------------------------------------------


def enqueue_slice(
    *,
    base_url: str,
    file_path: Path,
    timeout: float = 300.0,
    export_type: str = "3mf",
    overrides: dict[str, Any] | None = None,
) -> SliceEnqueueResult:
    """POST a file to ``/slice-async`` and return the upstream job reference."""
    data: dict[str, str] = {}
    if overrides:
        for key in (
            "printer", "preset", "filament", "filaments", "bedType",
            "plate", "arrange", "orient", "exportType",
            "multicolorOnePlate",
        ):
            if key in overrides:
                data[key] = str(overrides[key])
    if "exportType" not in data:
        data["exportType"] = export_type

    with httpx.Client(timeout=timeout) as client:
        with open(file_path, "rb") as f:
            mime = _MIME_TYPES.get(
                file_path.suffix.lower(), "application/octet-stream"
            )
            resp = client.post(
                f"{base_url}/slice-async",
                files={"file": (file_path.name, f, mime)},
                data=data,
            )

    if resp.status_code == 202:
        body = resp.json()
        return SliceEnqueueResult(
            request_id=body["requestId"],
            status=body["status"],
            status_url=body.get("statusUrl", ""),
        )

    _raise_upstream_error("Slice enqueue", resp)


def poll_slice(
    *,
    base_url: str,
    request_id: str,
    timeout: float = 10.0,
) -> SlicePollResult:
    """GET ``/slice-async/{requestId}`` and return current status."""
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(f"{base_url}/slice-async/{request_id}")

    if resp.status_code == 200:
        body = resp.json()
        return SlicePollResult(
            request_id=body["requestId"],
            status=body["status"],
            metadata=body.get("metadata"),
            download_url=body.get("downloadUrl"),
            error_message=body.get("message"),
        )

    _raise_upstream_error("Slice poll", resp)


def retrieve_output(
    *,
    base_url: str,
    request_id: str,
    dest_path: Path,
    timeout: float = 300.0,
) -> SliceOutputResult:
    """Download sliced output from ``/slice-async/{requestId}/result``.

    Streams to *dest_path* and computes a SHA-256 digest on the fly.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    sha = hashlib.sha256()
    content_length = 0

    with httpx.Client(timeout=timeout) as client:
        with client.stream(
            "GET", f"{base_url}/slice-async/{request_id}/result"
        ) as resp:
            if resp.status_code != 200:
                resp.read()
                _raise_upstream_error("Slice result download", resp)

            metadata = _parse_slice_metadata(resp.headers)

            with open(dest_path, "wb") as out:
                for chunk in resp.iter_bytes(chunk_size=65_536):
                    sha.update(chunk)
                    out.write(chunk)
                    content_length += len(chunk)

    return SliceOutputResult(
        output_path=dest_path,
        sha256=sha.hexdigest(),
        content_length=content_length,
        metadata=metadata,
    )


def cleanup_slice(
    *,
    base_url: str,
    request_id: str,
    timeout: float = 10.0,
) -> bool:
    """DELETE ``/slice-async/{requestId}`` to free upstream resources.

    Returns ``True`` on success, ``False`` if already cleaned up.
    Never raises — errors are logged so they don't mask the primary result.
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.delete(f"{base_url}/slice-async/{request_id}")
        if resp.status_code == 204:
            return True
        if resp.status_code == 404:
            logger.debug("Slice job %s already cleaned up", request_id)
            return False
        logger.warning(
            "Cleanup of slice job %s returned HTTP %d",
            request_id, resp.status_code,
        )
        return False
    except Exception:
        logger.warning(
            "Failed to cleanup slice job %s", request_id, exc_info=True,
        )
        return False


def poll_until_terminal(
    *,
    base_url: str,
    request_id: str,
    poll_interval: float = 2.0,
    max_wait: float = 1800.0,
    poll_timeout: float = 10.0,
) -> SlicePollResult:
    """Block until the upstream job reaches ``completed`` or ``failed``.

    Raises ``SlicerTimeoutError`` when *max_wait* seconds elapse.
    """
    deadline = time.monotonic() + max_wait

    while True:
        result = poll_slice(
            base_url=base_url,
            request_id=request_id,
            timeout=poll_timeout,
        )

        if result.status in ("completed", "failed"):
            return result

        if time.monotonic() + poll_interval > deadline:
            raise SlicerTimeoutError(
                f"Slice job {request_id} did not complete within {max_wait}s "
                f"(last status: {result.status})"
            )

        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_slice_metadata(headers: httpx.Headers) -> dict[str, Any]:
    """Extract slice metadata from upstream response headers."""
    meta: dict[str, Any] = {}
    for header, key in (
        ("X-Print-Time-Seconds", "print_time_seconds"),
        ("X-Filament-Used-g", "filament_used_g"),
        ("X-Filament-Used-mm", "filament_used_mm"),
    ):
        val = headers.get(header)
        if val is not None:
            try:
                meta[key] = float(val)
            except ValueError:
                meta[key] = val
    return meta


def _raise_upstream_error(context: str, resp: httpx.Response) -> NoReturn:
    """Raise ``SlicerUpstreamError`` from an unsuccessful response."""
    try:
        msg = resp.json().get("message", resp.text)
    except Exception:
        msg = resp.text
    raise SlicerUpstreamError(
        f"{context} failed (HTTP {resp.status_code}): {msg}",
        status_code=resp.status_code,
    )
