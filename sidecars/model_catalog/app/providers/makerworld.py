"""MakerWorld provider adapter for external source intake."""

from __future__ import annotations

import asyncio
import hashlib
import re
import zipfile
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

import httpx

from ..geometry_3mf import _resolve_model_part_path


_RECENT_MAKERWORLD_REQUESTS: deque[dict[str, Any]] = deque(maxlen=25)
_RECENT_MAKERWORLD_REQUESTS_LOCK = Lock()


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _record_recent_makerworld_request(
    *,
    method: str,
    request_url: str,
    request_label: str | None,
    response: httpx.Response | None = None,
    status_code: int | None = None,
    content_type: str | None = None,
    content_length: str | None = None,
    server: str | None = None,
    cf_ray: str | None = None,
    response_body_excerpt: str | None = None,
    error: Exception | None = None,
) -> None:
    parsed = urlparse(str(request_url or "").strip())
    response_json_message: str | None = None
    response_json_error: str | None = None
    response_json_code: Any = None
    if response is not None:
        content_type = str(response.headers.get("content-type") or "").lower()
        if "json" in content_type or "text/" in content_type:
            try:
                excerpt_bytes = response.content[:512]
                response_body_excerpt = excerpt_bytes.decode("utf-8", errors="replace").strip() or None
            except Exception:
                response_body_excerpt = None
        if "json" in content_type:
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                response_json_message = str(payload.get("message") or "").strip() or None
                response_json_error = str(payload.get("error") or "").strip() or None
                response_json_code = payload.get("code")
    entry = {
        "timestamp": _utc_now_iso(),
        "method": str(method or "").upper(),
        "request_label": str(request_label or "").strip() or None,
        "host": str(parsed.netloc or "").strip() or None,
        "path": str(parsed.path or "").strip() or None,
        "query": str(parsed.query or "").strip() or None,
        "status_code": int(response.status_code) if response is not None else (int(status_code) if status_code is not None else None),
        "content_type": str(response.headers.get("content-type") or "").strip() or None if response is not None else (str(content_type or "").strip() or None),
        "content_length": str(response.headers.get("content-length") or "").strip() or None if response is not None else (str(content_length or "").strip() or None),
        "server": str(response.headers.get("server") or "").strip() or None if response is not None else (str(server or "").strip() or None),
        "cf_ray": str(response.headers.get("cf-ray") or "").strip() or None if response is not None else (str(cf_ray or "").strip() or None),
        "response_json_message": response_json_message,
        "response_json_error": response_json_error,
        "response_json_code": response_json_code,
        "response_body_excerpt": response_body_excerpt,
        "error_type": type(error).__name__ if error is not None else None,
        "error": str(error) if error is not None else None,
    }
    with _RECENT_MAKERWORLD_REQUESTS_LOCK:
        _RECENT_MAKERWORLD_REQUESTS.append(entry)


def get_recent_makerworld_request_diagnostics(*, limit: int = 10) -> list[dict[str, Any]]:
    bounded_limit = max(int(limit), 0)
    with _RECENT_MAKERWORLD_REQUESTS_LOCK:
        if bounded_limit == 0:
            return []
        return list(_RECENT_MAKERWORLD_REQUESTS)[-bounded_limit:]


def reset_recent_makerworld_request_diagnostics() -> None:
    with _RECENT_MAKERWORLD_REQUESTS_LOCK:
        _RECENT_MAKERWORLD_REQUESTS.clear()


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
    WEB_API_BASE = "https://makerworld.com/api/v1"
    DESIGN_URL_RE = httpx.URL("https://makerworld.com")
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    )
    MAKERWORLD_CDN_HOSTS = {"makerworld.bblmw.com", "public-cdn.bblmw.com"}

    def __init__(
        self,
        auth_token: str,
        *,
        api_base: str = API_BASE,
        cookie_header: str | None = None,
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
        self._cookie_header = str(cookie_header or "").strip() or None
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
        creator_identity = self._extract_identity(
            design.raw_response,
            self._extract_creator(design.raw_response),
            {"creator_name": design.creator_name, "creator_uid": design.creator_uid},
        )
        warnings: list[str] = []
        file_manifest = []
        for instance in design.instances:
            instance_id = self._extract_instance_id(instance)
            if instance_id <= 0:
                continue
            image_urls = self._extract_instance_image_urls(instance)
            cover_url = str(instance.get("cover") or (image_urls[0] if image_urls else "")).strip() or None
            profile_owner_identity = self._extract_identity(instance)
            explicit_designer_profile = self._extract_designer_profile_flag(instance)
            is_designer_profile = explicit_designer_profile or bool(
                (creator_identity.get("key") and profile_owner_identity.get("key") and creator_identity.get("key") == profile_owner_identity.get("key"))
                or (
                    int(creator_identity.get("id") or 0) > 0
                    and int(profile_owner_identity.get("id") or 0) > 0
                    and int(creator_identity.get("id") or 0) == int(profile_owner_identity.get("id") or 0)
                )
            )
            manifest_entry = {
                "instance_id": instance_id,
                "title": str(instance.get("title") or "").strip(),
                "is_default": bool(instance.get("isDefault")),
                "plate_count": len(instance.get("plates") or []),
            }
            if str(profile_owner_identity.get("name") or "").strip():
                manifest_entry["profile_owner_name"] = str(profile_owner_identity.get("name") or "").strip()
            if int(profile_owner_identity.get("id") or 0) > 0:
                manifest_entry["profile_owner_id"] = int(profile_owner_identity.get("id") or 0)
            if is_designer_profile:
                manifest_entry["is_designer_profile"] = True
            if cover_url:
                manifest_entry["cover_url"] = cover_url
            if image_urls:
                manifest_entry["image_urls"] = image_urls
            profile_id = self._extract_profile_id(instance)
            if profile_id is not None:
                manifest_entry["profile_id"] = profile_id
            file_manifest.append(manifest_entry)
        if not file_manifest:
            warnings.append("makerworld_no_instances")
        return MakerWorldResolveResult(
            design=design,
            confidence="high",
            warnings=warnings,
            file_manifest=file_manifest,
        )

    async def download_3mf(
        self,
        instance_id: int,
        dest_path: Path,
        *,
        design_id: int | None = None,
        profile_id: int | None = None,
    ) -> Path:
        destination = Path(dest_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if design_id is not None and profile_id is not None:
            try:
                signed_url = await self._get_signed_download_url(
                    design_id=int(design_id),
                    profile_id=int(profile_id),
                )
                await self._download_signed_url_to_path(signed_url, destination)
            except ProviderUnavailableError:
                await self._download_legacy_3mf(instance_id, destination)
        else:
            await self._download_legacy_3mf(instance_id, destination)
        if not _is_valid_3mf_package(destination.read_bytes()):
            try:
                destination.unlink()
            except OSError:
                pass
            raise ProviderUnavailableError("MakerWorld download did not return a valid 3MF package")
        return destination

    async def _download_legacy_3mf(self, instance_id: int, destination: Path) -> None:
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
            default_instance_id=self._extract_instance_id(default_instance),
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

    def _extract_instance_id(self, instance: dict[str, Any]) -> int:
        for key in ("instanceId", "instance_id", "id"):
            value = int(instance.get(key) or 0)
            if value > 0:
                return value
        return 0

    def _extract_profile_id(self, instance: dict[str, Any]) -> int | None:
        nested_profile = instance.get("profile")
        candidates: list[Any] = [
            instance.get("profileId"),
            instance.get("profile_id"),
            instance.get("designProfileId"),
        ]
        if isinstance(nested_profile, dict):
            candidates.extend((nested_profile.get("id"), nested_profile.get("profileId")))
        for candidate in candidates:
            value = int(candidate or 0)
            if value > 0:
                return value
        return None

    def _extract_instance_image_urls(self, instance: dict[str, Any]) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()

        def add_url(value: Any) -> None:
            url = str(value or "").strip()
            if not url or url in seen:
                return
            seen.add(url)
            urls.append(url)

        add_url(instance.get("cover"))
        for picture in instance.get("pictures") or []:
            if isinstance(picture, dict):
                add_url(picture.get("url"))
                add_url(picture.get("image_url"))
            else:
                add_url(picture)

        nested_profile = instance.get("profile") if isinstance(instance.get("profile"), dict) else {}
        add_url(nested_profile.get("cover"))
        for picture in nested_profile.get("pictures") or []:
            if isinstance(picture, dict):
                add_url(picture.get("url"))
                add_url(picture.get("image_url"))
            else:
                add_url(picture)

        return urls

    def _extract_identity(self, *sources: Any) -> dict[str, Any]:
        nested_keys = ("profile", "user", "userInfo", "user_info", "creator", "author", "owner", "account", "designCreator")
        name_keys = (
            "profile_owner_name",
            "profileUserName",
            "profile_user_name",
            "displayName",
            "display_name",
            "userName",
            "username",
            "name",
            "nickName",
            "nickname",
            "creator_name",
            "creatorName",
            "authorName",
            "ownerName",
            "owner_name",
            "designer_name",
            "designer",
            "handle",
            "fullName",
            "full_name",
        )
        id_keys = (
            "profile_owner_id",
            "profileUserId",
            "profile_user_id",
            "profileUid",
            "profile_uid",
            "userId",
            "user_id",
            "uid",
            "creatorUid",
            "creator_uid",
            "creator_id",
            "authorId",
            "author_id",
            "ownerId",
            "owner_id",
            "accountId",
            "account_id",
        )
        queue = list(sources)
        seen: set[int] = set()
        resolved_name = ""
        resolved_id = 0
        while queue:
            source = queue.pop(0)
            if not isinstance(source, dict):
                continue
            source_id = id(source)
            if source_id in seen:
                continue
            seen.add(source_id)
            if not resolved_name:
                for key in name_keys:
                    candidate_name = str(source.get(key) or "").strip()
                    if candidate_name:
                        resolved_name = candidate_name
                        break
            if not resolved_id:
                for key in id_keys:
                    candidate_id = int(source.get(key) or 0)
                    if candidate_id > 0:
                        resolved_id = candidate_id
                        break
            for key in nested_keys:
                nested_source = source.get(key)
                if isinstance(nested_source, dict):
                    queue.append(nested_source)
        return {
            "name": resolved_name,
            "id": resolved_id,
            "key": "".join(ch for ch in resolved_name.strip().lower() if ch.isalnum()),
        }

    def _extract_designer_profile_flag(self, *sources: Any) -> bool:
        nested_keys = ("profile", "user", "userInfo", "user_info", "creator", "author", "owner", "account", "designCreator", "extention", "modelInfo")
        explicit_keys = (
            "isDesignerProfile",
            "is_designer_profile",
            "designerProfile",
            "isCreatorProfile",
            "is_creator_profile",
            "creatorProfile",
            "isModelCreator",
            "is_model_creator",
            "isDesignCreator",
            "is_design_creator",
            "fromDesigner",
            "from_designer",
        )
        badge_keys = ("badges", "labels", "tags", "tagList", "markers")
        queue = list(sources)
        seen: set[int] = set()

        def _normalize_text(value: Any) -> str:
            return str(value or "").strip().lower()

        def _is_designer_label(value: Any) -> bool:
            normalized = _normalize_text(value)
            return normalized in {"designer", "design creator", "creator"}

        while queue:
            source = queue.pop(0)
            if not isinstance(source, dict):
                continue
            source_id = id(source)
            if source_id in seen:
                continue
            seen.add(source_id)
            for key in explicit_keys:
                explicit_value = source.get(key)
                if explicit_value in (True, 1, "1"):
                    return True
            for key in badge_keys:
                badge_list = source.get(key)
                if not isinstance(badge_list, list):
                    continue
                for badge in badge_list:
                    if _is_designer_label(badge):
                        return True
                    if isinstance(badge, dict) and (
                        _is_designer_label(badge.get("label"))
                        or _is_designer_label(badge.get("name"))
                        or _is_designer_label(badge.get("text"))
                        or _is_designer_label(badge.get("type"))
                    ):
                        return True
            for key in nested_keys:
                nested_source = source.get(key)
                if isinstance(nested_source, dict):
                    queue.append(nested_source)
        return False

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

    async def _get_signed_download_url(self, *, design_id: int, profile_id: int) -> str:
        design_response = await self._request_json(
            "GET",
            f"/design-service/design/{int(design_id)}",
            timeout=self._metadata_timeout,
            max_429_retries=3,
            max_5xx_retries=1,
        )
        if design_response is None:
            raise ProviderUnavailableError("MakerWorld design was not found")
        design_payload = self._unwrap_design_payload(design_response)
        model_id = str(design_payload.get("modelId") or "").strip()
        if not model_id:
            raise ProviderUnavailableError("MakerWorld design metadata did not include modelId")

        response = await self._send_request(
            "GET",
            f"/iot-service/api/user/profile/{int(profile_id)}",
            timeout=self._metadata_timeout,
            params={"model_id": model_id},
            request_label="signed_download_manifest",
        )
        if response.status_code in {401, 403}:
            raise AuthenticationError("MakerWorld authentication failed")
        if response.status_code == 404:
            raise ProviderUnavailableError("MakerWorld profile download manifest was not found")
        if response.status_code == 429:
            raise ProviderUnavailableError("MakerWorld profile download manifest was rate limited")
        if 500 <= response.status_code <= 599:
            raise ProviderUnavailableError(
                f"MakerWorld profile download manifest failed with status {response.status_code}"
            )
        if response.status_code != 200:
            raise ProviderUnavailableError(
                f"MakerWorld profile download manifest failed with status {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderUnavailableError("MakerWorld profile download manifest returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderUnavailableError("MakerWorld profile download manifest returned invalid payload")
        signed_url = str(payload.get("url") or "").strip()
        if not signed_url:
            raise ProviderUnavailableError("MakerWorld profile download manifest did not include a URL")
        return signed_url

    async def _download_signed_url_to_path(self, signed_url: str, destination: Path) -> None:
        parsed = urlparse(str(signed_url or "").strip())
        host = str(parsed.hostname or "").strip().lower()
        if not host:
            raise ProviderUnavailableError("MakerWorld signed download URL was invalid")
        is_known_cdn = host in self.MAKERWORLD_CDN_HOSTS
        is_s3 = host.endswith(".amazonaws.com")
        if not is_known_cdn and not is_s3:
            raise ProviderUnavailableError(f"MakerWorld signed download host was not allowed: {host}")
        if is_s3:
            payload = await self._download_signed_url_via_urllib(signed_url)
            destination.write_bytes(payload)
            return

        await self._throttle()
        headers = {
            "Accept": "application/octet-stream, */*;q=0.9",
            "User-Agent": self.DEFAULT_USER_AGENT,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._download_timeout,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await client.get(signed_url, headers=headers)
                _record_recent_makerworld_request(
                    method="GET",
                    request_url=str(response.request.url),
                    request_label="signed_binary_download",
                    response=response,
                )
        except httpx.HTTPError as exc:
            _record_recent_makerworld_request(
                method="GET",
                request_url=signed_url,
                request_label="signed_binary_download",
                error=exc,
            )
            raise ProviderUnavailableError("MakerWorld signed download request failed") from exc

        if response.status_code != 200:
            raise ProviderUnavailableError(
                f"MakerWorld signed download failed with status {response.status_code}"
            )
        destination.write_bytes(response.content)

    async def _download_signed_url_via_urllib(self, signed_url: str) -> bytes:
        class _NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
                return None

        def _blocking_fetch() -> tuple[bytes, dict[str, Any]]:
            opener = build_opener(_NoRedirect)
            request = Request(
                signed_url,
                headers={
                    "Accept": "application/octet-stream, */*;q=0.9",
                    "User-Agent": self.DEFAULT_USER_AGENT,
                },
            )
            try:
                with opener.open(request, timeout=self._download_timeout) as response:
                    status_code = int(getattr(response, "status", 200) or 200)
                    payload = response.read()
                    headers = response.headers
                    metadata = {
                        "status_code": status_code,
                        "content_type": str(headers.get("Content-Type") or "").strip() or None,
                        "content_length": str(headers.get("Content-Length") or "").strip() or str(len(payload)),
                        "server": str(headers.get("Server") or "").strip() or None,
                        "cf_ray": str(headers.get("CF-Ray") or "").strip() or None,
                    }
                    if status_code != 200:
                        raise ProviderUnavailableError(
                            f"MakerWorld signed download failed with status {status_code}"
                        )
                    return payload, metadata
            except HTTPError as exc:
                error_body = b""
                try:
                    error_body = exc.read() or b""
                except Exception:
                    error_body = b""
                metadata = {
                    "status_code": int(getattr(exc, "code", 0) or 0) or None,
                    "content_type": str(exc.headers.get("Content-Type") or "").strip() or None if exc.headers is not None else None,
                    "content_length": str(exc.headers.get("Content-Length") or "").strip() or None if exc.headers is not None else None,
                    "server": str(exc.headers.get("Server") or "").strip() or None if exc.headers is not None else None,
                    "cf_ray": str(exc.headers.get("CF-Ray") or "").strip() or None if exc.headers is not None else None,
                    "response_body_excerpt": error_body[:512].decode("utf-8", errors="replace").strip() or None,
                }
                raise ProviderUnavailableError(
                    f"MakerWorld signed download failed with status {metadata['status_code']}"
                ) from exc

        try:
            payload, metadata = await asyncio.to_thread(_blocking_fetch)
        except ProviderUnavailableError as exc:
            http_error = exc.__cause__ if isinstance(exc.__cause__, HTTPError) else None
            if http_error is not None:
                _record_recent_makerworld_request(
                    method="GET",
                    request_url=signed_url,
                    request_label="signed_binary_download_s3",
                    status_code=int(getattr(http_error, "code", 0) or 0) or None,
                    content_type=str(http_error.headers.get("Content-Type") or "").strip() or None if http_error.headers is not None else None,
                    content_length=str(http_error.headers.get("Content-Length") or "").strip() or None if http_error.headers is not None else None,
                    server=str(http_error.headers.get("Server") or "").strip() or None if http_error.headers is not None else None,
                    cf_ray=str(http_error.headers.get("CF-Ray") or "").strip() or None if http_error.headers is not None else None,
                    response_body_excerpt=(
                        (lambda body: body[:512].decode("utf-8", errors="replace").strip() or None)(getattr(http_error, "fp", None).read() if False else b"")
                    ),
                    error=exc,
                )
            else:
                _record_recent_makerworld_request(
                    method="GET",
                    request_url=signed_url,
                    request_label="signed_binary_download_s3",
                    error=exc,
                )
            raise
        except Exception as exc:
            _record_recent_makerworld_request(
                method="GET",
                request_url=signed_url,
                request_label="signed_binary_download_s3",
                error=exc,
            )
            raise ProviderUnavailableError("MakerWorld signed download request failed") from exc

        _record_recent_makerworld_request(
            method="GET",
            request_url=signed_url,
            request_label="signed_binary_download_s3",
            status_code=metadata.get("status_code"),
            content_type=metadata.get("content_type"),
            content_length=metadata.get("content_length"),
            server=metadata.get("server"),
            cf_ray=metadata.get("cf_ray"),
        )
        return payload

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
                request_label="json",
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
        attempted_web_fallback = False
        while True:
            response = await self._send_request(
                "GET",
                url_path,
                timeout=timeout,
                params=params,
                absolute_url=absolute_url,
                accept_header="application/octet-stream, */*;q=0.9" if not absolute_url else "*/*",
                request_label="binary_download" if not absolute_url else "absolute_binary_download",
            )
            if response.status_code in {401, 403}:
                raise AuthenticationError("MakerWorld authentication failed")
            if response.status_code == 404:
                raise ProviderUnavailableError("MakerWorld resource was not found")
            if response.status_code == 418:
                if not absolute_url and not attempted_web_fallback:
                    attempted_web_fallback = True
                    response = await self._send_request(
                        "GET",
                        url_path,
                        timeout=timeout,
                        params=params,
                        accept_header="application/octet-stream, */*;q=0.9",
                        base_url_override=self.WEB_API_BASE,
                        request_label="binary_download_web_fallback",
                    )
                    if response.status_code == 200:
                        destination.write_bytes(response.content)
                        return
                    if response.status_code in {401, 403}:
                        raise AuthenticationError("MakerWorld authentication failed")
                    if response.status_code == 404:
                        raise ProviderUnavailableError("MakerWorld resource was not found")
                    if response.status_code != 418:
                        raise ProviderUnavailableError(
                            f"MakerWorld download failed with status {response.status_code} after 418 fallback"
                        )
                raise ProviderUnavailableError(
                    "MakerWorld download was rejected with status 418 on both api.bambulab.com and makerworld.com/api/v1; upstream likely blocked the request shape or token"
                )
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
        accept_header: str | None = None,
        base_url_override: str | None = None,
        request_label: str | None = None,
    ) -> httpx.Response:
        await self._throttle()
        resolved_base = str(base_url_override or self._api_base).strip().rstrip("/")
        request_url = url_path if absolute_url else f"{resolved_base}{url_path}"
        headers = {
            "Authorization": f"Bearer {self._auth_token}",
            "Accept": accept_header or ("application/json" if not absolute_url else "*/*"),
        }
        if not absolute_url:
            headers.update(
                {
                    "Accept-Language": "en-US,en;q=0.9",
                    "Origin": str(self.DESIGN_URL_RE),
                    "Referer": f"{self.DESIGN_URL_RE}/",
                    "User-Agent": self.DEFAULT_USER_AGENT,
                }
            )
            if self._cookie_header:
                headers["Cookie"] = self._cookie_header
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self._transport,
                follow_redirects=True,
            ) as client:
                response = await client.request(method, request_url, params=params, headers=headers)
                _record_recent_makerworld_request(
                    method=method,
                    request_url=str(response.request.url),
                    request_label=request_label,
                    response=response,
                )
                return response
        except httpx.HTTPError as exc:
            _record_recent_makerworld_request(
                method=method,
                request_url=request_url,
                request_label=request_label,
                error=exc,
            )
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
