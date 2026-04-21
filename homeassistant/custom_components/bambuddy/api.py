from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientResponseError, ClientSession, ClientTimeout, FormData


_LOGGER = logging.getLogger(__name__)


class BambuddyApiClient:
    def __init__(self, session: ClientSession, base_url: str, api_key: str, timeout_seconds: int) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key.strip()
        self._timeout = ClientTimeout(total=max(1, timeout_seconds))

    async def _raise_for_status_with_detail(self, response) -> None:
        try:
            response.raise_for_status()
        except ClientResponseError as error:
            detail = ""
            try:
                payload = await response.json()
            except Exception:  # noqa: BLE001
                payload = None
            if isinstance(payload, dict):
                detail = str(payload.get("detail") or payload.get("message") or payload.get("error") or "").strip()
            if detail:
                raise RuntimeError(f"Bambuddy returned HTTP {error.status}: {detail}") from error
            raise RuntimeError(f"Bambuddy returned HTTP {error.status}") from error

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

    async def async_fetch_archive_similar(self, archive_id: int, *, limit: int = 6) -> list[dict[str, Any]]:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        normalized_archive_id = int(archive_id)
        normalized_limit = max(1, min(25, int(limit)))

        async with self._session.get(
            f"{self._base_url}/api/v1/archives/{normalized_archive_id}/similar?{urlencode({'limit': normalized_limit})}",
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            await self._raise_for_status_with_detail(response)

            payload = await response.json()
            if not isinstance(payload, list):
                raise RuntimeError("Bambuddy similar archives response was not a JSON array")
            return [item for item in payload if isinstance(item, dict)]

    async def async_compare_archives(self, archive_ids: list[int]) -> dict[str, Any]:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        normalized_ids: list[int] = []
        seen_ids: set[int] = set()
        for value in archive_ids:
            normalized_value = int(value)
            if normalized_value <= 0 or normalized_value in seen_ids:
                continue
            seen_ids.add(normalized_value)
            normalized_ids.append(normalized_value)

        if len(normalized_ids) < 2:
            raise RuntimeError("At least 2 archive IDs are required for comparison")
        if len(normalized_ids) > 5:
            raise RuntimeError("Maximum 5 archive IDs can be compared at once")

        params = urlencode({"archive_ids": ",".join(str(value) for value in normalized_ids)})
        async with self._session.get(
            f"{self._base_url}/api/v1/archives/compare?{params}",
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            await self._raise_for_status_with_detail(response)

            payload = await response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("Bambuddy archive compare response was not a JSON object")
            return payload

    async def async_update_archive(self, archive_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        normalized_archive_id = int(archive_id)
        if normalized_archive_id <= 0:
            raise RuntimeError("archive_id must be a positive integer")
        if not isinstance(payload, dict) or not payload:
            raise RuntimeError("payload must include at least one field")

        async with self._session.patch(
            f"{self._base_url}/api/v1/archives/{normalized_archive_id}",
            headers={"X-API-Key": self._api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=self._timeout,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as error:
                raise RuntimeError(f"Bambuddy returned HTTP {error.status}") from error

            try:
                response_payload = await response.json()
            except Exception:  # noqa: BLE001
                return None

            return response_payload if isinstance(response_payload, dict) else None

    async def async_toggle_archive_favorite(self, archive_id: int) -> dict[str, Any] | None:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        normalized_archive_id = int(archive_id)
        if normalized_archive_id <= 0:
            raise RuntimeError("archive_id must be a positive integer")

        async with self._session.post(
            f"{self._base_url}/api/v1/archives/{normalized_archive_id}/favorite",
            headers={"X-API-Key": self._api_key, "Content-Type": "application/json"},
            timeout=self._timeout,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as error:
                raise RuntimeError(f"Bambuddy returned HTTP {error.status}") from error

            try:
                response_payload = await response.json()
            except Exception:  # noqa: BLE001
                return None

            return response_payload if isinstance(response_payload, dict) else None

    async def async_fetch_archive_capabilities(self, archive_id: int) -> dict[str, Any]:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        async with self._session.get(
            f"{self._base_url}/api/v1/archives/{int(archive_id)}/capabilities",
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as error:
                raise RuntimeError(f"Bambuddy returned HTTP {error.status}") from error

            payload = await response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("Bambuddy archive capabilities response was not a JSON object")
            return payload

    async def async_fetch_archive_gcode(self, archive_id: int) -> str:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        async with self._session.get(
            f"{self._base_url}/api/v1/archives/{int(archive_id)}/gcode",
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as error:
                raise RuntimeError(f"Bambuddy returned HTTP {error.status}") from error

            return await response.text()

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

    async def async_fetch_failure_analysis(
        self,
        *,
        days: int | None = None,
        date_from: str = "",
        date_to: str = "",
        printer_id: int | None = None,
        project_id: int | None = None,
    ) -> dict[str, Any]:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        params: dict[str, str | int] = {}
        if days is not None:
            params["days"] = max(1, int(days))
        if date_from:
            params["date_from"] = str(date_from).strip()
        if date_to:
            params["date_to"] = str(date_to).strip()
        if printer_id is not None:
            params["printer_id"] = int(printer_id)
        if project_id is not None:
            params["project_id"] = int(project_id)

        query_string = urlencode(params)
        url = f"{self._base_url}/api/v1/archives/analysis/failures"
        if query_string:
            url = f"{url}?{query_string}"

        async with self._session.get(
            url,
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            await self._raise_for_status_with_detail(response)
            payload = await response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("Bambuddy failure analysis response was not a JSON object")
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

    async def async_delete_archive_photo(self, archive_id: int, *, photo_path: str) -> None:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        normalized_archive_id = int(archive_id)
        normalized_photo_path = str(photo_path or "").strip().replace("\\", "/").split("/")[-1]
        if not normalized_photo_path:
            raise RuntimeError("Delete photo_path is empty")

        async with self._session.delete(
            f"{self._base_url}/api/v1/archives/{normalized_archive_id}/photos/{normalized_photo_path}",
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as error:
                raise RuntimeError(f"Bambuddy returned HTTP {error.status}") from error

    async def async_delete_archive(self, archive_id: int) -> None:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        normalized_archive_id = int(archive_id)
        if normalized_archive_id <= 0:
            raise RuntimeError("archive_id must be a positive integer")

        async with self._session.delete(
            f"{self._base_url}/api/v1/archives/{normalized_archive_id}",
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as error:
                raise RuntimeError(f"Bambuddy returned HTTP {error.status}") from error

    async def async_delete_archive_timelapse(self, archive_id: int) -> None:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        normalized_archive_id = int(archive_id)
        if normalized_archive_id <= 0:
            raise RuntimeError("archive_id must be a positive integer")

        async with self._session.delete(
            f"{self._base_url}/api/v1/archives/{normalized_archive_id}/timelapse",
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as error:
                raise RuntimeError(f"Bambuddy returned HTTP {error.status}") from error

    async def async_create_archive_slicer_token(self, archive_id: int) -> str:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        normalized_archive_id = int(archive_id)
        if normalized_archive_id <= 0:
            raise RuntimeError("archive_id must be a positive integer")

        async with self._session.post(
            f"{self._base_url}/api/v1/archives/{normalized_archive_id}/slicer-token",
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as error:
                raise RuntimeError(f"Bambuddy returned HTTP {error.status}") from error

            payload = await response.json()
            token = str(payload.get("token") if isinstance(payload, dict) else "").strip()
            if not token:
                raise RuntimeError("Bambuddy slicer token response did not include a token")
            return token

    async def async_create_source_slicer_token(self, archive_id: int) -> str:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        normalized_archive_id = int(archive_id)
        if normalized_archive_id <= 0:
            raise RuntimeError("archive_id must be a positive integer")

        async with self._session.post(
            f"{self._base_url}/api/v1/archives/{normalized_archive_id}/source-slicer-token",
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            try:
                response.raise_for_status()
            except ClientResponseError as error:
                raise RuntimeError(f"Bambuddy returned HTTP {error.status}") from error

            payload = await response.json()
            token = str(payload.get("token") if isinstance(payload, dict) else "").strip()
            if not token:
                raise RuntimeError("Bambuddy source slicer token response did not include a token")
            return token

    async def async_scan_archive_timelapse(self, archive_id: int) -> dict[str, Any] | None:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        normalized_archive_id = int(archive_id)
        if normalized_archive_id <= 0:
            raise RuntimeError("archive_id must be a positive integer")

        async with self._session.post(
            f"{self._base_url}/api/v1/archives/{normalized_archive_id}/timelapse/scan",
            headers={"X-API-Key": self._api_key, "Content-Type": "application/json"},
            timeout=self._timeout,
        ) as response:
            await self._raise_for_status_with_detail(response)

            try:
                payload = await response.json()
            except Exception:  # noqa: BLE001
                return None

            return payload if isinstance(payload, dict) else None

    async def async_upload_archive_timelapse(
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
        normalized_mime_type = str(mime_type or "application/octet-stream").strip().replace("\r", "").replace("\n", "")
        if normalized_archive_id <= 0:
            raise RuntimeError("archive_id must be a positive integer")
        if not normalized_file_name:
            raise RuntimeError("Upload file_name is empty")
        if not content:
            raise RuntimeError("Upload content is empty")

        form = FormData()
        form.add_field(
            "file",
            content,
            filename=normalized_file_name,
            content_type=normalized_mime_type or "application/octet-stream",
        )

        async with self._session.post(
            f"{self._base_url}/api/v1/archives/{normalized_archive_id}/timelapse/upload",
            headers={"X-API-Key": self._api_key},
            data=form,
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

    async def async_fetch_archive_timelapse_info(self, archive_id: int) -> dict[str, Any] | None:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        normalized_archive_id = int(archive_id)
        if normalized_archive_id <= 0:
            raise RuntimeError("archive_id must be a positive integer")

        async with self._session.get(
            f"{self._base_url}/api/v1/archives/{normalized_archive_id}/timelapse/info",
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            await self._raise_for_status_with_detail(response)

            try:
                payload = await response.json()
            except Exception:  # noqa: BLE001
                return None

            return payload if isinstance(payload, dict) else None

    async def async_fetch_archive_timelapse_thumbnails(
        self,
        archive_id: int,
        *,
        count: int = 10,
        width: int = 160,
    ) -> dict[str, Any] | None:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        normalized_archive_id = int(archive_id)
        if normalized_archive_id <= 0:
            raise RuntimeError("archive_id must be a positive integer")

        params = urlencode({"count": max(1, int(count)), "width": max(1, int(width))})
        async with self._session.get(
            f"{self._base_url}/api/v1/archives/{normalized_archive_id}/timelapse/thumbnails?{params}",
            headers={"X-API-Key": self._api_key},
            timeout=self._timeout,
        ) as response:
            await self._raise_for_status_with_detail(response)

            try:
                payload = await response.json()
            except Exception:  # noqa: BLE001
                return None

            return payload if isinstance(payload, dict) else None

    async def async_process_archive_timelapse(
        self,
        archive_id: int,
        *,
        trim_start: float = 0,
        trim_end: float | None = None,
        speed: float = 1.0,
        save_mode: str = "replace",
        output_filename: str | None = None,
        audio_file_name: str | None = None,
        audio_mime_type: str | None = None,
        audio_content: bytes | None = None,
    ) -> dict[str, Any] | None:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        normalized_archive_id = int(archive_id)
        if normalized_archive_id <= 0:
            raise RuntimeError("archive_id must be a positive integer")

        form = FormData()
        form.add_field("trim_start", str(float(trim_start)))
        if trim_end is not None:
            form.add_field("trim_end", str(float(trim_end)))
        form.add_field("speed", str(float(speed)))
        form.add_field("save_mode", str(save_mode or "replace"))
        if output_filename:
            form.add_field("output_filename", str(output_filename))
        if audio_content is not None:
            normalized_audio_name = str(audio_file_name or "audio.mp3").strip().replace("\r", "_").replace("\n", "_")
            normalized_audio_name = normalized_audio_name.replace("\\", "/").split("/")[-1].replace('"', "")
            normalized_audio_mime_type = str(audio_mime_type or "application/octet-stream").strip().replace("\r", "").replace("\n", "")
            form.add_field(
                "audio",
                audio_content,
                filename=normalized_audio_name or "audio.mp3",
                content_type=normalized_audio_mime_type or "application/octet-stream",
            )

        async with self._session.post(
            f"{self._base_url}/api/v1/archives/{normalized_archive_id}/timelapse/process",
            headers={"X-API-Key": self._api_key},
            data=form,
            timeout=self._timeout,
        ) as response:
            await self._raise_for_status_with_detail(response)

            try:
                payload = await response.json()
            except Exception:  # noqa: BLE001
                return None

            return payload if isinstance(payload, dict) else None

    async def async_upload_archive_source_3mf(
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
        normalized_mime_type = str(mime_type or "application/octet-stream").strip().replace("\r", "").replace("\n", "")
        if normalized_archive_id <= 0:
            raise RuntimeError("archive_id must be a positive integer")
        if not normalized_file_name:
            raise RuntimeError("Upload file_name is empty")
        if not content:
            raise RuntimeError("Upload content is empty")

        form = FormData()
        form.add_field(
            "file",
            content,
            filename=normalized_file_name,
            content_type=normalized_mime_type or "application/octet-stream",
        )

        async with self._session.post(
            f"{self._base_url}/api/v1/archives/{normalized_archive_id}/source",
            headers={"X-API-Key": self._api_key},
            data=form,
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

    async def async_upload_archive_replacement(
        self,
        *,
        printer_id: int,
        file_path: Path,
        file_name: str,
        mime_type: str,
    ) -> dict[str, Any] | None:
        if not self._base_url:
            raise RuntimeError("Bambuddy base URL is empty")
        if not self._api_key:
            raise RuntimeError("Bambuddy API key is empty")

        normalized_printer_id = int(printer_id)
        normalized_file_name = str(file_name or "").strip().replace("\r", "_").replace("\n", "_")
        normalized_file_name = normalized_file_name.replace("\\", "/").split("/")[-1].replace('"', "")
        normalized_mime_type = str(mime_type or "application/octet-stream").strip().replace("\r", "").replace("\n", "")
        if normalized_printer_id <= 0:
            raise RuntimeError("printer_id must be a positive integer")
        if not normalized_file_name:
            raise RuntimeError("Upload file_name is empty")
        if not file_path.exists() or not file_path.is_file():
            raise RuntimeError("Replacement upload file is missing")

        form = FormData()
        with file_path.open("rb") as handle:
            form.add_field(
                "file",
                handle,
                filename=normalized_file_name,
                content_type=normalized_mime_type or "application/octet-stream",
            )
            async with self._session.post(
                f"{self._base_url}/api/v1/archives/upload?{urlencode({'printer_id': normalized_printer_id})}",
                headers={"X-API-Key": self._api_key},
                data=form,
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

    async def _async_post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._base_url:
            raise RuntimeError("Bambuddy runtime repair base URL is empty")
        if not self._token:
            raise RuntimeError("Bambuddy runtime repair token is empty")

        async with self._session.post(
            f"{self._base_url}{path}",
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
        return await self._async_post_json("/admin/archive-partial-usage/estimate", payload)

    async def async_runtime_repair(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._async_post_json("/admin/archive-runtime-repair", payload)

    async def async_restore_from(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._async_post_json("/admin/archive-restore-from", payload)

    async def async_restore_verify(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._async_post_json("/admin/archive-restore-verify", payload)

    async def async_scan_archive_storage(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._async_post_json("/admin/archive-storage/scan", payload)

    async def async_scan_archive_storage_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._async_post_json("/admin/archive-storage/scan-batch", payload)