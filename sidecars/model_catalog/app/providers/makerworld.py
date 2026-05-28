"""MakerWorld provider adapter for external source intake."""

from __future__ import annotations

import asyncio
import hashlib
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from ..geometry_3mf import _resolve_model_part_path


@dataclass(frozen=True)
class MakerWorldDesign:
    """Normalized design metadata from the MakerWorld API."""

    design_id: int
    title: str
    creator_name: str
    creator_uid: int
    creator_avatar_url: str | None
    summary: str | None
    license: str | None
    tags: list[str]
    images: list[dict[str, Any]]
    default_instance_id: int
    instances: list[dict[str, Any]]
    like_count: int
    download_count: int
    collect_count: int
    create_time: str | None
    update_time: str | None
    canonical_url: str
    raw_response: dict[str, Any]


@dataclass(frozen=True)
class MakerWorldResolveResult:
    """Result of resolving a MakerWorld URL or design ID."""

    design: MakerWorldDesign
    confidence: str
    warnings: list[str]
    file_manifest: list[dict[str, Any]]


class MakerWorldError(Exception):
    """Base error for MakerWorld adapter operations."""


class AuthenticationError(MakerWorldError):
    """MakerWorld rejected the configured auth token."""


class ProviderUnavailableError(MakerWorldError):
    """MakerWorld is unavailable or returned an unexpected response."""


class MakerWorldAdapter:
    """Provider adapter for MakerWorld source intake."""

    PROVIDER_ID = "makerworld"
    API_BASE = "https://api.bambulab.com/v1"
    DESIGN_URL_RE = httpx.URL("https://makerworld.com")

    def __init__(
        self,
        auth_token: str,
        *,
        api_base: str = API_BASE,
        metadata_timeout: float = 10.0,
        download_timeout: float = 60.0,
        image_timeout: float = 15.0,
        rate_limit_qps: float = 2.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        token = str(auth_token or "").strip()
        if not token:
            raise ValueError("auth_token is required")
        self._auth_token = token
        self._api_base = str(api_base or self.API_BASE).strip().rstrip("/")
        self._metadata_timeout = float(metadata_timeout)
        self._download_timeout = float(download_timeout)
        self._image_timeout = float(image_timeout)
        self._rate_limit_qps = max(float(rate_limit_qps), 0.0)
        self._transport = transport
        self._min_request_interval = (1.0 / self._rate_limit_qps) if self._rate_limit_qps > 0 else 0.0
        self._last_request_started_at = 0.0
        self._rate_lock = asyncio.Lock()

    async def resolve_url(self, url: str) -> MakerWorldResolveResult | None:
        design_id = self.parse_design_id_from_url(url)
        if design_id is None:
            return None
        return await self.resolve_design_id(design_id, source_url=url)

    async def resolve_design_id(
        self,
        design_id: int,
        *,
        source_url: str | None = None,
    ) -> MakerWorldResolveResult | None:
        response = await self._request_json(
            "GET",
            f"/design-service/design/{int(design_id)}",
            timeout=self._metadata_timeout,
            max_429_retries=3,
            max_5xx_retries=1,
        )
        if response is None:
            return None
        normalized_payload = self._unwrap_design_payload(response)
        design = self._normalize_design(normalized_payload, source_url=source_url)
        warnings: list[str] = []
        file_manifest = [
            {
                "instance_id": int(instance.get("id") or 0),
                "title": str(instance.get("title") or "").strip(),
                "is_default": bool(instance.get("isDefault")),
                "plate_count": len(instance.get("plates") or []),
            }
            for instance in design.instances
            if int(instance.get("id") or 0) > 0
        ]
        if not file_manifest:
            warnings.append("makerworld_no_instances")
        return MakerWorldResolveResult(
            design=design,
            confidence="high",
            warnings=warnings,
            file_manifest=file_manifest,
        )

    async def download_3mf(self, instance_id: int, dest_path: Path) -> Path:
        destination = Path(dest_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        url_path = f"/design-service/instance/{int(instance_id)}/f3mf"
        params = {"type": "download"}
        await self._download_to_path(
            url_path,
            destination,
            timeout=self._download_timeout,
            params=params,
            max_429_retries=3,
            max_5xx_retries=1,
        )
        if not _is_valid_3mf_package(destination.read_bytes()):
            try:
                destination.unlink()
            except OSError:
                pass
            raise ProviderUnavailableError("MakerWorld download did not return a valid 3MF package")
        return destination

    async def download_preview_images(
        self,
        design: MakerWorldDesign,
        dest_dir: Path,
    ) -> list[Path]:
        output_dir = Path(dest_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        downloaded: list[Path] = []
        for index, image in enumerate(design.images, start=1):
            image_url = str(image.get("url") or "").strip()
            if not image_url:
                continue
            suffix = Path(urlparse(image_url).path).suffix or ".jpg"
            destination = output_dir / f"makerworld-{design.design_id:07d}-{index:02d}{suffix}"
            await self._download_to_path(
                image_url,
                destination,
                timeout=self._image_timeout,
                max_429_retries=3,
                max_5xx_retries=1,
                absolute_url=True,
            )
            downloaded.append(destination)
        return downloaded

    async def list_user_collections(self, user_id: int) -> list[dict[str, Any]]:
        response = await self._request_json(
            "GET",
            f"/design-user-service/user/{int(user_id)}/collections",
            timeout=self._metadata_timeout,
            max_429_retries=3,
            max_5xx_retries=1,
        )
        if response is None:
            return []
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]
        if isinstance(response, dict):
            items = response.get("items") or response.get("collections") or response.get("data") or []
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return []

    def parse_design_id_from_url(self, url: str) -> int | None:
        candidate = str(url or "").strip()
        if not candidate:
            return None
        try:
            parsed = urlparse(candidate)
        except ValueError:
            return None
        host = (parsed.netloc or "").lower()
        if host not in {"makerworld.com", "www.makerworld.com"}:
            return None
        parts = [part for part in (parsed.path or "").split("/") if part]
        if len(parts) < 2:
            return None
        if len(parts) >= 3 and len(parts[0]) == 2 and parts[1] == "models":
            id_part = parts[2]
        elif parts[0] == "models":
            id_part = parts[1]
        else:
            return None
        id_text = id_part.split("-", 1)[0].strip()
        if not id_text.isdigit():
            return None
        return int(id_text)

    def parse_instance_id_from_url(self, url: str) -> int | None:
        candidate = str(url or "").strip()
        if not candidate:
            return None
        try:
            parsed = urlparse(candidate)
        except ValueError:
            return None
        host = (parsed.netloc or "").lower()
        if host not in {"makerworld.com", "www.makerworld.com"}:
            return None
        for candidate_text in (str(parsed.fragment or "").strip(), str(parsed.query or "").strip()):
            if not candidate_text:
                continue
            match = re.search(r"(?:^|[&#?])profileId(?:=|-)(\d+)(?:$|[&#?])", candidate_text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    def _normalize_design(
        self,
        payload: dict[str, Any],
        *,
        source_url: str | None = None,
    ) -> MakerWorldDesign:
        instances = self._extract_instances(payload)
        default_instance = next((item for item in instances if item.get("isDefault")), instances[0] if instances else {})
        creator = self._extract_creator(payload)
        tags: list[str] = []
        for tag in (payload.get("tags") or []):
            if isinstance(tag, dict):
                tag_name = str(tag.get("name") or "").strip()
            else:
                tag_name = str(tag or "").strip()
            if tag_name:
                tags.append(tag_name)

        images = self._normalize_images(payload)
        design_id = int(payload.get("id") or 0)
        if design_id <= 0:
            raise ProviderUnavailableError("MakerWorld design response did not include a valid design id")
        canonical_url = self._canonical_design_url(design_id, source_url=source_url)
        return MakerWorldDesign(
            design_id=design_id,
            title=str(payload.get("title") or "").strip(),
            creator_name=str(creator.get("name") or "").strip(),
            creator_uid=int(creator.get("uid") or 0),
            creator_avatar_url=str(creator.get("avatar") or "").strip() or None,
            summary=str(payload.get("summary") or "").strip() or None,
            license=str(payload.get("license") or "").strip() or None,
            tags=tags,
            images=images,
            default_instance_id=int(default_instance.get("id") or 0),
            instances=instances,
            like_count=int(payload.get("likeCount") or 0),
            download_count=int(payload.get("downloadCount") or 0),
            collect_count=int(payload.get("collectCount") or 0),
            create_time=str(payload.get("createTime") or "").strip() or None,
            update_time=str(payload.get("updateTime") or "").strip() or None,
            canonical_url=canonical_url,
            raw_response=payload,
        )

    def _unwrap_design_payload(self, payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ProviderUnavailableError("MakerWorld returned invalid design payload")
        data_payload = payload.get("data")
        if isinstance(data_payload, dict):
            has_direct_design_fields = any(key in payload for key in ("id", "title", "instances", "designCreator"))
            has_nested_design_fields = any(key in data_payload for key in ("id", "title", "instances", "designCreator"))
            if has_nested_design_fields and not has_direct_design_fields:
                return data_payload
        return payload

    def _extract_instances(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = (
            payload.get("instances"),
            payload.get("instanceList"),
            payload.get("profiles"),
            payload.get("profileList"),
            payload.get("printProfiles"),
        )
        for candidate in candidates:
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
        return []

    def _extract_creator(self, payload: dict[str, Any]) -> dict[str, Any]:
        for candidate in (
            payload.get("designCreator"),
            payload.get("creator"),
            payload.get("user"),
            payload.get("author"),
        ):
            if isinstance(candidate, dict):
                return candidate
        return {}

    def _normalize_images(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        def add_image(image: Any) -> None:
            if not isinstance(image, dict):
                return
            image_url = str(image.get("url") or "").strip()
            if not image_url or image_url in seen_urls:
                return
            normalized.append(image)
            seen_urls.add(image_url)

        for image in (payload.get("images") or []):
            add_image(image)

        cover_url = str(payload.get("coverUrl") or "").strip()
        if cover_url and cover_url not in seen_urls:
            normalized.append({"url": cover_url, "role": "cover"})
            seen_urls.add(cover_url)

        design_extension = payload.get("designExtension") or {}
        for image in (design_extension.get("design_pictures") or []):
            add_image(image)

        return normalized

    def _canonical_design_url(self, design_id: int, *, source_url: str | None = None) -> str:
        region = "en"
        if source_url:
            parsed = urlparse(str(source_url))
            parts = [part for part in (parsed.path or "").split("/") if part]
            if len(parts) >= 3 and len(parts[0]) == 2 and parts[1] == "models":
                region = parts[0]
        return f"https://makerworld.com/{region}/models/{int(design_id)}"

    async def _request_json(
        self,
        method: str,
        url_path: str,
        *,
        timeout: float,
        params: dict[str, Any] | None = None,
        max_429_retries: int,
        max_5xx_retries: int,
    ) -> dict[str, Any] | list[Any] | None:
        retries_429 = 0
        retries_5xx = 0
        while True:
            response = await self._send_request(
                method,
                url_path,
                timeout=timeout,
                params=params,
            )
            if response.status_code == 404:
                return None
            if response.status_code in {401, 403}:
                raise AuthenticationError("MakerWorld authentication failed")
            if response.status_code == 429:
                if retries_429 >= max_429_retries:
                    raise ProviderUnavailableError("MakerWorld rate limit retries exhausted")
                await asyncio.sleep(0.5 * (2 ** retries_429))
                retries_429 += 1
                continue
            if 500 <= response.status_code <= 599:
                if retries_5xx >= max_5xx_retries:
                    raise ProviderUnavailableError(
                        f"MakerWorld upstream error {response.status_code}"
                    )
                await asyncio.sleep(0.5 * (2 ** retries_5xx))
                retries_5xx += 1
                continue
            if response.status_code != 200:
                raise ProviderUnavailableError(
                    f"MakerWorld request failed with status {response.status_code}"
                )
            try:
                return response.json()
            except ValueError as exc:
                raise ProviderUnavailableError("MakerWorld returned invalid JSON") from exc

    async def _download_to_path(
        self,
        url_path: str,
        destination: Path,
        *,
        timeout: float,
        params: dict[str, Any] | None = None,
        max_429_retries: int,
        max_5xx_retries: int,
        absolute_url: bool = False,
    ) -> None:
        retries_429 = 0
        retries_5xx = 0
        while True:
            response = await self._send_request(
                "GET",
                url_path,
                timeout=timeout,
                params=params,
                absolute_url=absolute_url,
            )
            if response.status_code in {401, 403}:
                raise AuthenticationError("MakerWorld authentication failed")
            if response.status_code == 404:
                raise ProviderUnavailableError("MakerWorld resource was not found")
            if response.status_code == 429:
                if retries_429 >= max_429_retries:
                    raise ProviderUnavailableError("MakerWorld rate limit retries exhausted")
                await asyncio.sleep(0.5 * (2 ** retries_429))
                retries_429 += 1
                continue
            if 500 <= response.status_code <= 599:
                if retries_5xx >= max_5xx_retries:
                    raise ProviderUnavailableError(
                        f"MakerWorld upstream error {response.status_code}"
                    )
                await asyncio.sleep(0.5 * (2 ** retries_5xx))
                retries_5xx += 1
                continue
            if response.status_code != 200:
                raise ProviderUnavailableError(
                    f"MakerWorld download failed with status {response.status_code}"
                )
            destination.write_bytes(response.content)
            return

    async def _send_request(
        self,
        method: str,
        url_path: str,
        *,
        timeout: float,
        params: dict[str, Any] | None = None,
        absolute_url: bool = False,
    ) -> httpx.Response:
        await self._throttle()
        request_url = url_path if absolute_url else f"{self._api_base}{url_path}"
        headers = {
            "Authorization": f"Bearer {self._auth_token}",
            "Accept": "application/json" if not absolute_url else "*/*",
        }
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self._transport,
                follow_redirects=True,
            ) as client:
                return await client.request(method, request_url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("MakerWorld request failed") from exc

    async def _throttle(self) -> None:
        if self._min_request_interval <= 0:
            return
        async with self._rate_lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            delay = self._min_request_interval - (now - self._last_request_started_at)
            if delay > 0:
                await asyncio.sleep(delay)
                now = loop.time()
            self._last_request_started_at = now


def sha256_file(path: Path) -> str:
    """Return SHA-256 digest of a file written by the provider."""

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_valid_3mf_package(payload: bytes) -> bool:
    if not payload:
        return False
    try:
        with zipfile.ZipFile(BytesIO(payload)) as package:
            _resolve_model_part_path(package)
    except (zipfile.BadZipFile, OSError, RuntimeError, ValueError):
        return False
    return True
