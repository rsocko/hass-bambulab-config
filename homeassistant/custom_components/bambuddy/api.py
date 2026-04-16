from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from aiohttp import ClientResponseError, ClientSession, ClientTimeout


_LOGGER = logging.getLogger(__name__)


class BambuddyApiClient:
    def __init__(self, session: ClientSession, base_url: str, api_key: str, timeout_seconds: int) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key.strip()
        self._timeout = ClientTimeout(total=max(1, timeout_seconds))

    async def async_fetch_printers(self) -> list[dict[str, Any]]:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        async with self._session.get(
            f"{self._base_url}/api/v1/printers/",
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as error:
                raise RuntimeError(f"Bambuddy returned HTTP {error.status}") from error

            payload = await response.json()
            if not isinstance(payload, list):
                raise RuntimeError("Bambuddy printer response was not a JSON array")
            _LOGGER.debug("Fetched %s printers from Bambuddy", len(payload))
            return [item for item in payload if isinstance(item, dict)]

    async def async_fetch_archives(
        self,
        *,
        limit: int,
        date_from: str = "",
        date_to: str = "",
    ) -> list[dict[str, Any]]:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        params: dict[str, str | int] = {"limit": max(1, limit)}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to

        async with self._session.get(
            f"{self._base_url}/api/v1/archives/?{urlencode(params)}",
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as error:
                raise RuntimeError(f"Bambuddy returned HTTP {error.status}") from error

            payload = await response.json()
            if not isinstance(payload, list):
                raise RuntimeError("Bambuddy archive response was not a JSON array")
            _LOGGER.debug("Fetched %s archives from Bambuddy", len(payload))
            return [item for item in payload if isinstance(item, dict)]

    async def async_fetch_archive_detail(self, archive_id: int) -> dict[str, Any]:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        async with self._session.get(
            f"{self._base_url}/api/v1/archives/{int(archive_id)}",
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as error:
                raise RuntimeError(f"Bambuddy returned HTTP {error.status}") from error

            payload = await response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("Bambuddy archive detail response was not a JSON object")
            return payload

    async def async_fetch_archive_stats(self) -> dict[str, Any]:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        async with self._session.get(
            f"{self._base_url}/api/v1/archives/stats",
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as error:
                raise RuntimeError(f"Bambuddy returned HTTP {error.status}") from error

            payload = await response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("Bambuddy archive stats response was not a JSON object")
            return payload

    async def async_upload_archive_photo(
        self,
        archive_id: int,
        *,
        file_name: str,
        mime_type: str,
        content: bytes,
    ) -> dict[str, Any] | None:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        normalized_archive_id = int(archive_id)
        normalized_file_name = str(file_name or "").strip().replace("\r", "_").replace("\n", "_")
        normalized_file_name = normalized_file_name.replace("\\", "/").split("/")[-1].replace('"', "")
        if not normalized_file_name:
            raise RuntimeError("Upload file_name is empty")

        normalized_mime_type = str(mime_type or "application/octet-stream").strip().replace("\r", "").replace("\n", "")
        if not content:
            raise RuntimeError("Upload content is empty")

        boundary = f"----ha-bambuddy-{uuid4().hex}"
        body = (
            f"--{boundary}\r\n".encode("utf-8")
            + f'Content-Disposition: form-data; name="file"; filename="{normalized_file_name}"\r\n'.encode("utf-8")
            + f"Content-Type: {normalized_mime_type}\r\n\r\n".encode("utf-8")
            + content
            + f"\r\n--{boundary}--\r\n".encode("utf-8")
        )

        async with self._session.post(
            f"{self._base_url}/api/v1/archives/{normalized_archive_id}/photos",
            headers={
                "X-API-Key": self._api_key,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
            data=body,
            timeout=self._timeout,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as error:
                raise RuntimeError(f"Bambuddy returned HTTP {error.status}") from error

            try:
                payload = await response.json()
            except Exception:  # noqa: BLE001
                return None

            return payload if isinstance(payload, dict) else None

    async def async_fetch_projects(self) -> list[dict[str, Any]]:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        async with self._session.get(
            f"{self._base_url}/api/v1/projects/",
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as error:
                raise RuntimeError(f"Bambuddy returned HTTP {error.status}") from error

            payload = await response.json()
            if not isinstance(payload, list):
                raise RuntimeError("Bambuddy project response was not a JSON array")
            _LOGGER.debug("Fetched %s projects from Bambuddy", len(payload))
            return [item for item in payload if isinstance(item, dict)]


class BambuddyRuntimeRepairClient:
    def __init__(self, session: ClientSession, base_url: str, token: str, timeout_seconds: int) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._token = token.strip()
        self._timeout = ClientTimeout(total=max(1, timeout_seconds))

    async def async_estimate_partial_usage(
        self,
        *,
        archive_id: int,
        print_status: str,
        printer_id: int | None = None,
        last_layer_num: int | None = None,
        last_progress: float | None = None,
        resolve_spoolman_matches: bool = True,
        keep_tracking_row: bool = True,
    ) -> dict[str, Any]:
        if not self._base_url:
            raise RuntimeError("Bambuddy runtime repair base URL is empty")
        if not self._token:
            raise RuntimeError("Bambuddy runtime repair token is empty")

        payload: dict[str, Any] = {
            "archive_id": archive_id,
            "print_status": print_status,
            "resolve_spoolman_matches": resolve_spoolman_matches,
            "keep_tracking_row": keep_tracking_row,
        }
        if printer_id is not None:
            payload["printer_id"] = printer_id
        if last_layer_num is not None:
            payload["last_layer_num"] = last_layer_num
        if last_progress is not None:
            payload["last_progress"] = last_progress

        async with self._session.post(
            f"{self._base_url}/admin/archive-partial-usage/estimate",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "accept": "application/json",
            },
            json=payload,
            timeout=self._timeout,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as error:
                raise RuntimeError(f"Bambuddy runtime repair returned HTTP {error.status}") from error

            response_payload = await response.json()
            if not isinstance(response_payload, dict):
                raise RuntimeError("Bambuddy runtime repair response was not a JSON object")
            return response_payload