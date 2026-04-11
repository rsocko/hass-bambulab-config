from __future__ import annotations

import logging
from typing import Any

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

    async def async_fetch_archives(self, *, limit: int) -> list[dict[str, Any]]:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        async with self._session.get(
            f"{self._base_url}/api/v1/archives/?limit={max(1, limit)}",
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