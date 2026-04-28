from __future__ import annotations

import base64
import html
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from .db import connect, derive_manyfold_model_key
from .models import ManyfoldModelSummary

logger = logging.getLogger(__name__)


MANYFOLD_API_ACCEPT = "application/vnd.manyfold.v0+json"
JSON_CONTENT_TYPE = "application/json"
TUS_VERSION = "1.0.0"
SIGN_IN_PATH = "/users/sign_in"


@dataclass(frozen=True)
class CachedManyfoldModel:
    summary: ManyfoldModelSummary
    raw_payload: dict[str, Any]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonicalize_model_url(base_url: str, model_url: str, *, fallback_model_id: Any | None = None) -> str:
    normalized = str(model_url or "").strip()
    if not normalized and fallback_model_id is not None:
        return f"{base_url.rstrip('/')}/models/{fallback_model_id}"
    if normalized.startswith("/"):
        return f"{base_url.rstrip('/')}{normalized}"
    if normalized.startswith("http://") or normalized.startswith("https://"):
        parsed = urlsplit(normalized)
        if parsed.path.startswith("/models/"):
            canonical = f"{base_url.rstrip('/')}{parsed.path}"
            if parsed.query:
                canonical += f"?{parsed.query}"
            return canonical
    return normalized


def _append_query_param(url: str, key: str, value: str) -> str:
    normalized = str(url or "").strip()
    if not normalized:
        return normalized
    if f"{key}=" in normalized:
        return normalized
    separator = "&" if "?" in normalized else "?"
    return f"{normalized}{separator}{key}={quote(value, safe='')}"


def _json_route(path: str) -> str:
    normalized = str(path or "").strip()
    if not normalized:
        return normalized
    parsed = urlsplit(normalized)
    route_path = parsed.path or normalized
    if route_path.endswith(".json"):
        return normalized
    return urlunsplit((parsed.scheme, parsed.netloc, f"{route_path}.json", parsed.query, parsed.fragment))


def _json_route_candidates(path: str) -> list[str]:
    normalized = str(path or "").strip()
    if not normalized:
        return []

    candidates = [normalized]
    json_route = _json_route(normalized)
    if json_route and json_route not in candidates:
        candidates.append(json_route)
    return candidates


def _absolute_resource_url(base_url: str, ref: str) -> str:
    normalized = str(ref or "").strip()
    if not normalized:
        return normalized
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized
    if normalized.startswith("/"):
        return f"{base_url.rstrip('/')}{normalized}"
    return f"{base_url.rstrip('/')}/{normalized.lstrip('/')}"


def _encode_tus_metadata(metadata: dict[str, str]) -> str:
    parts: list[str] = []
    for key, value in metadata.items():
        normalized_value = str(value or "")
        if not normalized_value:
            continue
        encoded = base64.b64encode(normalized_value.encode("utf-8")).decode("ascii")
        parts.append(f"{key} {encoded}")
    return ",".join(parts)


def _extract_model_id(payload: dict[str, Any]) -> str | None:
    explicit_id = str(payload.get("id") or "").strip()
    if explicit_id:
        return explicit_id

    ref = str(payload.get("@id") or payload.get("url") or "").strip()
    if not ref:
        return None

    path = urlsplit(ref).path or ref
    parts = [segment for segment in path.split("/") if segment]
    if len(parts) >= 2 and parts[-2] == "models":
        return parts[-1]
    return None


def _guess_manyfold_file_type(filename: str) -> str | None:
    suffix = str(filename or "").strip().lower().rsplit(".", 1)
    if len(suffix) != 2:
        return None
    extension = suffix[1]
    return {
        "3mf": "model/3mf",
        "stl": "model/stl",
        "obj": "model/obj",
        "step": "model/step",
        "stp": "model/step",
        "gcode": "text/x.gcode",
        "jpeg": "image/jpeg",
        "jpg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }.get(extension)


class _ManyfoldModelPageParser(HTMLParser):
    def __init__(self, *, model_path: str, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self._model_path = model_path.rstrip("/")
        self._base_url = base_url.rstrip("/")
        self._captured_title: list[str] = []
        self._captured_code: list[str] = []
        self._in_title = False
        self._in_code = False
        self.files_by_id: dict[str, dict[str, Any]] = {}
        self.photos_by_id: dict[str, dict[str, Any]] = {}
        self._pending_photo: dict[str, Any] | None = None
        self._carousel_depth = 0

    @property
    def title(self) -> str:
        return " ".join(part.strip() for part in self._captured_title if part.strip()).strip()

    @property
    def current_filename(self) -> str | None:
        text = " ".join(part.strip() for part in self._captured_code if part.strip()).strip()
        return text or None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "title":
            self._in_title = True
            self._captured_title = []
            return
        if tag == "code":
            self._in_code = True
            self._captured_code = []
            return
        if tag == "div":
            class_name = str(attr_map.get("class") or "")
            classes = {part.strip() for part in class_name.split() if part.strip()}
            if "carousel-item" in classes:
                self._carousel_depth += 1
                self._pending_photo = None
            return
        if tag == "img":
            alt = str(attr_map.get("alt") or "").strip()
            src = str(attr_map.get("src") or "").strip()
            if self._carousel_depth > 0 and src:
                self._pending_photo = {
                    "filename": alt or src.rsplit("/", 1)[-1],
                    "thumbnail_url": src,
                    "image_url": src,
                }
            return
        if tag != "a":
            return

        href = str(attr_map.get("href") or "").strip()
        if not href.startswith(f"{self._model_path}/model_files/"):
            return
        if href.endswith("/edit") or href.endswith("/bulk_edit"):
            return

        download_match = re.match(
            rf"^{re.escape(self._model_path)}/model_files/(?P<file_id>[^./?]+)\.(?P<extension>[^/?]+)\?download=true$",
            href,
        )
        if download_match:
            file_id = download_match.group("file_id")
            extension = download_match.group("extension")
            filename = self.current_filename or f"{file_id}.{extension}"
            row = self.files_by_id.setdefault(
                file_id,
                {
                    "id": file_id,
                    "@id": f"{self._model_path}/model_files/{file_id}",
                    "filename": filename,
                    "name": filename,
                    "contentUrl": f"{self._model_path}/model_files/{file_id}.{extension}?download=true",
                },
            )
            row.setdefault("filename", filename)
            row.setdefault("name", filename)
            row.setdefault("@id", f"{self._model_path}/model_files/{file_id}")
            row["contentUrl"] = f"{self._model_path}/model_files/{file_id}.{extension}?download=true"
            guessed_type = _guess_manyfold_file_type(filename)
            if guessed_type and not row.get("encodingFormat"):
                row["encodingFormat"] = guessed_type
            return

        open_match = re.match(rf"^{re.escape(self._model_path)}/model_files/(?P<file_id>[^/?]+)$", href)
        if open_match:
            file_id = open_match.group("file_id")
            filename = self.current_filename
            pending_photo = self._pending_photo
            if pending_photo and self._carousel_depth > 0:
                photo_row = self.photos_by_id.setdefault(
                    file_id,
                    {
                        "id": file_id,
                        "@id": href,
                        "filename": pending_photo.get("filename") or file_id,
                    },
                )
                photo_row.setdefault("@id", href)
                photo_row.setdefault("filename", pending_photo.get("filename") or file_id)
                thumbnail_url = str(pending_photo.get("thumbnail_url") or "").strip()
                image_url = str(pending_photo.get("image_url") or "").strip()
                if thumbnail_url:
                    photo_row["thumbnail_url"] = thumbnail_url
                if image_url:
                    photo_row["image_url"] = image_url
                self._pending_photo = None
                return
            if not filename:
                return
            row = self.files_by_id.setdefault(
                file_id,
                {
                    "id": file_id,
                    "@id": href,
                    "filename": filename,
                    "name": filename,
                },
            )
            row.setdefault("@id", href)
            row.setdefault("filename", filename)
            row.setdefault("name", filename)
            guessed_type = _guess_manyfold_file_type(filename)
            if guessed_type and not row.get("encodingFormat"):
                row["encodingFormat"] = guessed_type

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
            return
        if tag == "code":
            self._in_code = False
            return
        if tag == "div" and self._carousel_depth > 0:
            self._carousel_depth -= 1
            if self._carousel_depth == 0:
                self._pending_photo = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._captured_title.append(data)
        if self._in_code:
            self._captured_code.append(data)


def _parse_manyfold_model_page_html(base_url: str, model_path: str, html_text: str) -> dict[str, Any]:
    parser = _ManyfoldModelPageParser(model_path=model_path, base_url=base_url)
    parser.feed(html_text)
    files = list(parser.files_by_id.values())
    photos = list(parser.photos_by_id.values())
    payload: dict[str, Any] = {}
    if parser.title:
        payload["name"] = parser.title.split(" Search the Internet for models with this name", 1)[0].strip()
    if files:
        payload["hasPart"] = files
    if photos:
        payload["photos"] = photos
    return payload


class _ManyfoldSignInFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._forms: list[dict[str, str]] = []
        self._current_form: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "form":
            self._current_form = {
                "action": str(attr_map.get("action") or SIGN_IN_PATH).strip() or SIGN_IN_PATH,
            }
            return
        if tag != "input" or self._current_form is None:
            return

        input_name = str(attr_map.get("name") or "").strip()
        if input_name == "user[email]":
            self._current_form["has_email"] = "true"
        elif input_name == "user[password]":
            self._current_form["has_password"] = "true"
        elif input_name == "authenticity_token":
            self._current_form["authenticity_token"] = str(attr_map.get("value") or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._current_form is not None:
            self._forms.append(self._current_form)
            self._current_form = None

    def extract(self) -> tuple[str, str | None] | None:
        for form in self._forms:
            if form.get("has_email") == "true" and form.get("has_password") == "true":
                return form.get("action") or SIGN_IN_PATH, form.get("authenticity_token") or None
        return None


def _parse_manyfold_sign_in_form(html_text: str) -> tuple[str, str | None] | None:
    parser = _ManyfoldSignInFormParser()
    parser.feed(html_text)
    return parser.extract()


class _ManyfoldModelListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._current_href: str | None = None
        self._current_text: list[str] = []
        self.rows: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = {key: value or "" for key, value in attrs}
        href = str(attr_map.get("href") or "").strip()
        if not re.match(r"^/models/[^/?#.]+$", href):
            return
        self._current_href = href
        self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._current_href is None:
            return
        text = " ".join(part.strip() for part in self._current_text if part.strip()).strip()
        href = self._current_href
        self._current_href = None
        self._current_text = []
        if not text:
            return
        if text.lower() in {"open", "edit", "delete", "models", "upload models", "homepage", "sign in"}:
            return
        self.rows.append({"url": href, "name": text})


def _parse_manyfold_model_list_html(base_url: str, html_text: str) -> list[dict[str, Any]]:
    parser = _ManyfoldModelListParser()
    parser.feed(html_text)
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for row in parser.rows:
        canonical_url = canonicalize_model_url(base_url, str(row.get("url") or ""))
        if not canonical_url or canonical_url in seen:
            continue
        seen.add(canonical_url)
        rows.append(
            {
                "url": canonical_url,
                "@id": str(row.get("url") or ""),
                "name": str(row.get("name") or "").strip(),
            }
        )
    return rows


def _redirects_to_sign_in(response: httpx.Response) -> bool:
    location = str(response.headers.get("location") or "").strip()
    if response.status_code not in {301, 302, 303, 307, 308} or not location:
        return False
    parsed = urlsplit(location)
    redirect_path = parsed.path or location
    return redirect_path.startswith(SIGN_IN_PATH)


def _lookup_keys(value: Any) -> tuple[str, ...]:
    keys: list[str] = []

    def _add(raw: Any) -> None:
        text = str(raw or "").strip()
        if not text:
            return
        lowered = text.lower()
        keys.append(lowered)
        parsed = urlsplit(text)
        path = parsed.path.strip().lower()
        if path:
            keys.append(path)
            parts = [segment for segment in path.split("/") if segment]
            if parts:
                keys.append(parts[-1])
    if isinstance(value, dict):
        _add(value.get("id"))
        _add(value.get("@id"))
        _add(value.get("url"))
        _add(value.get("slug"))
        _add(value.get("name"))
        _add(value.get("title"))
        _add(value.get("label"))
    elif isinstance(value, (str, int, float)):
        _add(value)

    unique: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key not in seen:
            seen.add(key)
            unique.append(key)
    return tuple(unique)


def _build_name_lookup(rows: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("title") or row.get("label") or "").strip()
        if not name:
            continue
        for key in _lookup_keys(row):
            lookup[key] = name
    return lookup


def _resolve_lookup_name(value: Any, lookup: dict[str, str] | None) -> str | None:
    if not lookup:
        return None
    for key in _lookup_keys(value):
        if key in lookup:
            return lookup[key]
    return None


def _model_ref_from_payload(payload: dict[str, Any]) -> str | None:
    public_id = str(payload.get("public_id") or "").strip()
    if public_id:
        return public_id

    model_id = _extract_model_id(payload)
    if model_id:
        return model_id

    ref = str(payload.get("@id") or payload.get("url") or "").strip()
    return ref or None


def _collection_ref_from_payload(payload: dict[str, Any]) -> str | None:
    ref = str(payload.get("@id") or payload.get("url") or "").strip()
    if ref:
        return ref

    explicit_id = str(payload.get("id") or "").strip()
    if explicit_id:
        return explicit_id

    slug = str(payload.get("slug") or "").strip()
    if slug:
        return slug

    return None


class ManyfoldClient:
    def __init__(
        self,
        base_url: str,
        *,
        models_path: str = "/models",
        collections_path: str = "/collections",
        creators_path: str = "/creators",
        oauth_token_path: str = "/oauth/token",
        client_id: str | None = None,
        client_secret: str | None = None,
        oauth_scopes: str | None = None,
        session_email: str | None = None,
        session_password: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.models_path = models_path
        self.collections_path = collections_path
        self.creators_path = creators_path
        self.oauth_token_path = oauth_token_path
        self.client_id = client_id
        self.client_secret = client_secret
        self.oauth_scopes = oauth_scopes
        self.session_email = str(session_email or "").strip() or None
        self.session_password = str(session_password or "").strip() or None
        self._client = http_client or httpx.Client(base_url=self.base_url, timeout=15.0, trust_env=False)
        self._owns_client = http_client is None
        self._access_token: str | None = None
        self._site_session_ready = False

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _token_form_data(self, *, include_client_credentials: bool) -> dict[str, str]:
        form_data: dict[str, str] = {
            "grant_type": "client_credentials",
        }
        if include_client_credentials:
            form_data["client_id"] = str(self.client_id)
            form_data["client_secret"] = str(self.client_secret)
        if self.oauth_scopes:
            form_data["scope"] = self.oauth_scopes
        return form_data

    def _auth_headers(self) -> dict[str, str]:
        if not self.client_id or not self.client_secret:
            return {}
        if not self._access_token:
            response = self._client.post(
                self.oauth_token_path,
                data=self._token_form_data(include_client_credentials=True),
            )
            if response.status_code == 401:
                response = self._client.post(
                    self.oauth_token_path,
                    auth=(self.client_id, self.client_secret),
                    data=self._token_form_data(include_client_credentials=False),
                )
            response.raise_for_status()
            payload = response.json()
            self._access_token = str(payload.get("access_token") or "").strip() or None
            if not self._access_token:
                raise RuntimeError("Manyfold OAuth token response did not include access_token.")
        return {"Authorization": f"Bearer {self._access_token}"}

    def _request_headers(self) -> dict[str, str]:
        return {
            "Accept": MANYFOLD_API_ACCEPT,
            **self._auth_headers(),
        }

    def _get_json_with_accept_fallback(self, path: str) -> Any:
        attempts = [
            ("vendor", self._request_headers()),
            ("application_json", {"Accept": "application/json", **self._auth_headers()}),
            ("no_accept", self._auth_headers()),
        ]
        last_error: Exception | None = None
        last_response: httpx.Response | None = None

        for candidate_path in _json_route_candidates(path):
            for index, (label, headers) in enumerate(attempts):
                response = self._client.get(candidate_path, headers=headers)
                last_response = response
                if response.status_code == 406:
                    if index < len(attempts) - 1:
                        logger.warning(
                            "Manyfold endpoint %s rejected %s Accept headers with 406; retrying with %s.",
                            candidate_path,
                            label,
                            attempts[index + 1][0],
                        )
                    continue

                try:
                    response.raise_for_status()
                    return response.json()
                except json.JSONDecodeError as exc:
                    last_error = RuntimeError(
                        f"Manyfold endpoint {candidate_path} returned non-JSON content."
                    )
                    logger.warning(
                        "Manyfold endpoint %s returned non-JSON content for %s Accept headers.",
                        candidate_path,
                        label,
                    )
                    if index < len(attempts) - 1:
                        continue
                    break
                except Exception as exc:
                    last_error = exc
                    break

        if last_error is not None:
            raise last_error
        assert last_response is not None
        last_response.raise_for_status()
        return last_response.json()

    def _ensure_site_session(self) -> bool:
        if self._site_session_ready:
            return True

        if self.session_email and self.session_password:
            login_page = self._client.get(SIGN_IN_PATH, follow_redirects=True)
            login_page.raise_for_status()
            sign_in_form = _parse_manyfold_sign_in_form(login_page.text)
            if not sign_in_form:
                raise RuntimeError("Manyfold sign-in form could not be parsed for session bootstrap.")
            action, authenticity_token = sign_in_form
            form_payload: dict[str, str] = {
                "user[email]": self.session_email,
                "user[password]": self.session_password,
                "user[remember_me]": "1",
            }
            if authenticity_token:
                form_payload["authenticity_token"] = authenticity_token
            sign_in_response = self._client.post(
                action,
                data=form_payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": f"{self.base_url}{SIGN_IN_PATH}",
                },
                follow_redirects=True,
            )
            sign_in_response.raise_for_status()
            if sign_in_response.url.path.startswith(SIGN_IN_PATH) and not self._client.cookies:
                raise RuntimeError(
                    "Manyfold session login failed; verify MANYFOLD_SESSION_EMAIL and MANYFOLD_SESSION_PASSWORD."
                )
            self._site_session_ready = bool(self._client.cookies)
            return self._site_session_ready

        response = self._client.get(self.models_path, follow_redirects=True)
        response.raise_for_status()
        self._site_session_ready = bool(self._client.cookies) or response.is_success
        return self._site_session_ready

    def _post_with_session_retry(
        self,
        path: str,
        *,
        headers: dict[str, str],
        data: Any | None = None,
        json_body: Any | None = None,
    ) -> httpx.Response:
        request_headers = dict(headers)
        if self._site_session_ready and path.startswith("/upload"):
            request_headers = {key: value for key, value in request_headers.items() if key.lower() != "authorization"}
        response = self._client.post(path, headers=request_headers, data=data, json=json_body)
        if response.is_success:
            return response
        if _redirects_to_sign_in(response) or response.status_code in {401, 403}:
            if not (self.session_email and self.session_password):
                raise RuntimeError(
                    "Manyfold upload requires a web session. Configure MANYFOLD_SESSION_EMAIL and MANYFOLD_SESSION_PASSWORD."
                )
            self._ensure_site_session()
            session_headers = {key: value for key, value in headers.items() if key.lower() != "authorization"}
            return self._client.post(path, headers=session_headers, data=data, json=json_body)
        return response

    def _patch_with_session_retry(self, path: str, *, headers: dict[str, str], content: bytes) -> httpx.Response:
        request_headers = dict(headers)
        if self._site_session_ready and path.startswith("/upload"):
            request_headers = {key: value for key, value in request_headers.items() if key.lower() != "authorization"}
        response = self._client.patch(path, headers=request_headers, content=content)
        if response.is_success:
            return response
        if _redirects_to_sign_in(response) or response.status_code in {401, 403}:
            if not (self.session_email and self.session_password):
                raise RuntimeError(
                    "Manyfold upload requires a web session. Configure MANYFOLD_SESSION_EMAIL and MANYFOLD_SESSION_PASSWORD."
                )
            self._ensure_site_session()
            session_headers = {key: value for key, value in headers.items() if key.lower() != "authorization"}
            return self._client.patch(path, headers=session_headers, content=content)
        return response

    def _fallback_model_detail_from_html(self, model_ref: str) -> dict[str, Any]:
        model_path = self._resolve_ref_path(model_ref, default_prefix=self.models_path)
        if self._ensure_site_session():
            response = self._client.get(model_path, follow_redirects=True)
            response.raise_for_status()
            content_type = str(response.headers.get("content-type") or "").lower()
            if "html" not in content_type:
                raise RuntimeError("Manyfold HTML detail fallback did not return HTML.")
            return _parse_manyfold_model_page_html(self.base_url, model_path, response.text)
        raise RuntimeError("Manyfold HTML detail fallback could not establish a site session.")

    def fetch_binary(self, url: str) -> httpx.Response:
        response = self._client.get(url, headers=self._auth_headers(), follow_redirects=True)
        content_type = str(response.headers.get("content-type") or "").lower()
        if response.is_success and content_type.startswith("image/"):
            return response

        if self._ensure_site_session():
            response = self._client.get(url, follow_redirects=True)
            content_type = str(response.headers.get("content-type") or "").lower()
            if response.is_success and content_type.startswith("image/"):
                return response

        return response

    def _resolve_ref_path(self, ref: str, *, default_prefix: str) -> str:
        normalized = str(ref or "").strip()
        if not normalized:
            raise ValueError("Manyfold reference cannot be empty.")
        if normalized.startswith("http://") or normalized.startswith("https://"):
            parsed = urlsplit(normalized)
            return parsed.path or "/"
        if normalized.startswith("/"):
            return normalized
        encoded = quote(normalized, safe="")
        return f"{default_prefix.rstrip('/')}/{encoded}"

    @staticmethod
    def _extract_rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            rows = payload.get("member") or payload.get("models") or payload.get("data") or payload.get("items") or []
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return []

    def list_models(self) -> list[ManyfoldModelSummary]:
        rows = self.list_model_payloads()
        return [normalize_model_summary(self.base_url, row) for row in rows]

    def list_model_payloads(self) -> list[dict[str, Any]]:
        payload = self._get_json_with_accept_fallback(self.models_path)
        return self._extract_rows(payload)

    def list_model_payloads_from_html(self, *, order: str = "recent") -> list[dict[str, Any]]:
        if not self._ensure_site_session():
            return []
        separator = "&" if "?" in self.models_path else "?"
        response = self._client.get(f"{self.models_path}{separator}order={quote(order, safe='')}", follow_redirects=True)
        response.raise_for_status()
        content_type = str(response.headers.get("content-type") or "").lower()
        if "html" not in content_type:
            return []
        return _parse_manyfold_model_list_html(self.base_url, response.text)

    def get_model_detail(self, model_ref: str) -> dict[str, Any]:
        path = self._resolve_ref_path(model_ref, default_prefix=self.models_path)
        try:
            payload = self._get_json_with_accept_fallback(path)
            if not isinstance(payload, dict):
                raise RuntimeError("Manyfold model detail response was not a JSON object.")
            return payload
        except Exception:
            payload = self._fallback_model_detail_from_html(model_ref)
            if payload:
                return payload
            raise

    def list_model_files(self, model_ref: str) -> list[dict[str, Any]]:
        model_path = self._resolve_ref_path(model_ref, default_prefix=self.models_path)
        path = f"{model_path.rstrip('/')}/model_files"
        try:
            response = self._client.get(path, headers=self._request_headers())
            response.raise_for_status()
            payload = response.json()
            return self._extract_rows(payload)
        except Exception:
            detail_payload = self._fallback_model_detail_from_html(model_ref)
            has_part = detail_payload.get("hasPart")
            if isinstance(has_part, list):
                return [row for row in has_part if isinstance(row, dict)]
            raise

    def list_model_photos(self, model_ref: str) -> list[dict[str, Any]]:
        """Fetch photos for a model from Manyfold API."""
        model_path = self._resolve_ref_path(model_ref, default_prefix=self.models_path)
        path = f"{model_path.rstrip('/')}/photos"
        try:
            payload = self._get_json_with_accept_fallback(path)
            rows = self._extract_rows(payload)
            if not rows and isinstance(payload, dict):
                photos_data = payload.get("photos")
                if isinstance(photos_data, list):
                    rows = [row for row in photos_data if isinstance(row, dict)]
            return rows
        except Exception:
            detail_payload = self._fallback_model_detail_from_html(model_ref)
            photos = detail_payload.get("photos")
            if isinstance(photos, list):
                return [row for row in photos if isinstance(row, dict)]
            return []

    def get_model_file_detail(self, file_ref: str, *, model_ref: str | None = None) -> dict[str, Any]:
        normalized_file_ref = str(file_ref or "").strip()
        if not normalized_file_ref:
            raise ValueError("Manyfold file reference cannot be empty.")
        if normalized_file_ref.startswith("http://") or normalized_file_ref.startswith("https://") or normalized_file_ref.startswith("/"):
            path = self._resolve_ref_path(normalized_file_ref, default_prefix="/model_files")
        elif model_ref:
            model_path = self._resolve_ref_path(model_ref, default_prefix=self.models_path)
            path = f"{model_path.rstrip('/')}/model_files/{quote(normalized_file_ref, safe='')}"
        else:
            path = f"/model_files/{quote(normalized_file_ref, safe='')}"
        response = self._client.get(path, headers=self._request_headers())
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Manyfold model file detail response was not a JSON object.")
        return payload

    def list_collections(self) -> list[dict[str, Any]]:
        payload = self._get_json_with_accept_fallback(self.collections_path)
        return self._extract_rows(payload)

    def list_creators(self) -> list[dict[str, Any]]:
        payload = self._get_json_with_accept_fallback(self.creators_path)
        return self._extract_rows(payload)

    def resolve_collection_ref(self, *, collection_id: int | None = None, collection_name: str | None = None) -> str | None:
        normalized_name = str(collection_name or "").strip().lower()
        if normalized_name:
            for collection in self.list_collections():
                name = str(collection.get("name") or collection.get("title") or "").strip().lower()
                if name != normalized_name:
                    continue
                return _collection_ref_from_payload(collection)
            raise ValueError(f"Manyfold collection not found: {collection_name}")

        if collection_id is not None:
            normalized_id = str(collection_id).strip()
            for collection in self.list_collections():
                if str(collection.get("id") or "").strip() == normalized_id:
                    return _collection_ref_from_payload(collection)
            return normalized_id

        return None

    def create_model(self, *, name: str, collection_ref: str | None = None) -> dict[str, Any]:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise ValueError("Manyfold model name is required.")

        payload: dict[str, Any] = {"name": normalized_name}
        if collection_ref:
            payload["collection"] = collection_ref

        headers = {
            **self._request_headers(),
            "Content-Type": JSON_CONTENT_TYPE,
        }
        response = self._client.post(self.models_path, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("Manyfold model create response was not a JSON object.")
        return body

    def upload_file(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        normalized_filename = str(filename or "").strip()
        if not normalized_filename:
            raise ValueError("Manyfold filename is required.")

        file_content_type = str(content_type or _guess_manyfold_file_type(normalized_filename) or "application/octet-stream").strip()
        create_headers = {
            **self._auth_headers(),
            "Tus-Resumable": TUS_VERSION,
            "Upload-Length": str(len(content)),
        }
        metadata_header = _encode_tus_metadata({
            "filename": normalized_filename,
            "content_type": file_content_type,
        })
        if metadata_header:
            create_headers["Upload-Metadata"] = metadata_header

        create_response = self._post_with_session_retry("/upload", headers=create_headers)
        create_response.raise_for_status()
        upload_location = str(create_response.headers.get("Location") or "").strip()
        if not upload_location:
            raise RuntimeError("Manyfold upload create response did not include a Location header.")

        upload_path = self._resolve_ref_path(upload_location, default_prefix="/upload")
        patch_response = self._patch_with_session_retry(
            upload_path,
            headers={
                **self._auth_headers(),
                "Tus-Resumable": TUS_VERSION,
                "Upload-Offset": "0",
                "Content-Length": str(len(content)),
                "Content-Type": "application/offset+octet-stream",
            },
            content=content,
        )
        patch_response.raise_for_status()
        final_offset = str(patch_response.headers.get("Upload-Offset") or "").strip()
        if final_offset and final_offset != str(len(content)):
            raise RuntimeError(
                f"Manyfold upload finished at offset {final_offset}, expected {len(content)}."
            )

        return {
            "id": _absolute_resource_url(self.base_url, upload_location),
            "name": normalized_filename,
            "type": file_content_type,
            "size": len(content),
        }

    def create_model_from_uploads(
        self,
        *,
        uploaded_files: list[dict[str, Any]],
        name: str | None = None,
        collection_ref: str | None = None,
    ) -> dict[str, Any]:
        if not uploaded_files:
            raise ValueError("Manyfold uploaded_files is required.")

        payload: dict[str, Any] = {"files": uploaded_files}
        normalized_name = str(name or "").strip()
        if normalized_name:
            payload["name"] = normalized_name
        if collection_ref:
            payload["isPartOf"] = {
                "@id": _absolute_resource_url(self.base_url, collection_ref),
                "@type": "Collection",
            }

        response = self._post_with_session_retry(
            self.models_path,
            headers={
                **self._request_headers(),
                "Content-Type": MANYFOLD_API_ACCEPT,
            },
            json_body=payload,
        )
        response.raise_for_status()
        if not response.content:
            return {}
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("Manyfold uploaded model create response was not a JSON object.")
        return body

    def add_uploaded_files_to_model(
        self,
        model_ref: str,
        *,
        uploaded_files: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not uploaded_files:
            raise ValueError("Manyfold uploaded_files is required.")

        model_path = self._resolve_ref_path(model_ref, default_prefix=self.models_path)
        response = self._post_with_session_retry(
            f"{model_path.rstrip('/')}/model_files",
            headers={
                **self._request_headers(),
                "Content-Type": MANYFOLD_API_ACCEPT,
            },
            json_body={"files": uploaded_files},
        )
        response.raise_for_status()
        if not response.content:
            return {}
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("Manyfold uploaded file add response was not a JSON object.")
        return body

    def attach_file_to_model(
        self,
        model_ref: str,
        *,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        normalized_filename = str(filename or "").strip()
        if not normalized_filename:
            raise ValueError("Manyfold filename is required.")

        model_path = self._resolve_ref_path(model_ref, default_prefix=self.models_path)
        path = f"{model_path.rstrip('/')}/files"
        file_content_type = str(content_type or "application/octet-stream").strip() or "application/octet-stream"
        response = self._client.post(
            path,
            headers=self._request_headers(),
            files={
                "file": (normalized_filename, content, file_content_type),
                "filename": (None, normalized_filename),
            },
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("Manyfold file attach response was not a JSON object.")
        return body

    def update_model(self, model_ref: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Update model metadata in Manyfold (Phase 3.1).
        
        Args:
            model_ref: Model URL, public_id, or model_id
            updates: Dict with fields to update (e.g., name, description, tags, collection)
        
        Returns:
            Updated model detail from Manyfold
        """
        path = self._resolve_ref_path(model_ref, default_prefix=self.models_path)
        
        # Ensure site session is established before attempting PATCH
        self._ensure_site_session()

        headers = {
            **self._request_headers(),
            "Content-Type": JSON_CONTENT_TYPE,
        }
        response = self._client.patch(path, headers=headers, json=updates)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Manyfold model update response was not a JSON object.")
        return payload


def normalize_model_summary(
    base_url: str,
    payload: dict[str, Any],
    *,
    creator_lookup: dict[str, str] | None = None,
    collection_lookup: dict[str, str] | None = None,
    model_to_collections: dict[str, list[str]] | None = None,
) -> ManyfoldModelSummary:
    # Prefer fully hydrated preview_file_detail first because it includes contentUrl.
    preview = payload.get("preview_file_detail") or payload.get("preview") or payload.get("preview_file") or {}
    creator = payload.get("creator") or payload.get("creator_id") or {}
    collections = payload.get("collections") or payload.get("collection_ids") or []
    keywords = payload.get("keywords") or payload.get("tags") or payload.get("tag_list") or []
    if isinstance(keywords, str):
        keywords = [token.strip() for token in keywords.split(",") if token.strip()]
    model_id = _extract_model_id(payload)
    model_url = canonicalize_model_url(
        base_url,
        str(payload.get("url") or payload.get("@id") or "").strip(),
        fallback_model_id=model_id,
    )

    def _extract_name(value: Any) -> str | None:
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, dict):
            nested = value.get("name") or value.get("title") or value.get("label")
            return _extract_name(nested)
        return None

    creator_name = _extract_name(creator) or _resolve_lookup_name(creator, creator_lookup)

    resolved_collection_names: list[str] = []
    
    # Try model_to_collections mapping first (built from isPartOf field)
    if model_to_collections:
        model_ref = _model_ref_from_payload(payload)
        if model_ref and model_ref in model_to_collections:
            resolved_collection_names = model_to_collections[model_ref]
    
    # Fallback: parse collections field if present
    if not resolved_collection_names:
        for item in collections if isinstance(collections, list) else [collections]:
            name = _extract_name(item) or _resolve_lookup_name(item, collection_lookup)
            if name:
                resolved_collection_names.append(name)

    # Priority: contentUrl (resolved preview file) > fallback URL fields
    # contentUrl is a relative path like /models/{id}/model_files/{fid}.{ext}
    # which Manyfold serves with proper image headers and content negotiation.
    raw_content_url = str(preview.get("contentUrl") or "").strip()
    preview_mime = str(preview.get("encodingFormat") or "").strip().lower()

    preview_url = str(
        raw_content_url
        or preview.get("url")
        or preview.get("thumbnail_url")
        or preview.get("preview_url")
        or preview.get("download_url")
        or ""
    ).strip() or None

    if preview_url:
        preview_url = canonicalize_model_url(base_url, preview_url)
        if raw_content_url:
            if preview_mime.startswith("image/"):
                preview_url = _append_query_param(preview_url, "derivative", "preview")
            else:
                preview_url = None

    # Last-resort fallback: if Manyfold gives only an image @id reference, map it
    # to a canonical URL so the frontend can attempt rendering it.
    if not preview_url and isinstance(preview, dict):
        preview_ref = str(preview.get("@id") or "").strip()
        preview_mime = str(preview.get("encodingFormat") or "").strip().lower()
        if preview_ref and preview_mime.startswith("image/"):
            preview_url = canonicalize_model_url(base_url, preview_ref)

    return ManyfoldModelSummary(
        model_url=model_url,
        public_id=str(payload.get("public_id") or "").strip() or None,
        model_id=model_id,
        name=str(payload.get("name") or payload.get("title") or "Unnamed Model").strip(),
        preview_url=preview_url,
        creator_name=creator_name,
        collection_names=tuple(resolved_collection_names),
        keyword_names=tuple(filter(None, (_extract_name(item) for item in keywords))),
    )


def _refresh_manyfold_cache_internal(*, db_path, client: ManyfoldClient) -> tuple[list[ManyfoldModelSummary], dict[str, Any]]:
    model_rows: list[dict[str, Any]] | None = None
    creator_lookup: dict[str, str] = {}
    collection_lookup: dict[str, str] = {}
    model_to_collections: dict[str, list[str]] = {}
    if hasattr(client, "list_model_payloads"):
        model_rows = client.list_model_payloads()
        try:
            creator_lookup = _build_name_lookup(client.list_creators())
        except Exception as e:
            logger.warning(f"Failed to build creator_lookup: {e}")
            creator_lookup = {}
        try:
            all_collections = client.list_collections()
            collection_lookup = _build_name_lookup(all_collections)
            logger.info(f"Built collection_lookup with {len(collection_lookup)} entries")
            
            # Build collection ID → name mapping for isPartOf resolution.
            # Manyfold may return absolute URLs (http://localhost:3214/collections/...)
            # or relative paths (/collections/...) depending on context.  Normalise
            # every @id to its path component so that both forms match at lookup time.
            collection_id_to_names: dict[str, str] = {}
            for collection in all_collections:
                coll_id = collection.get("@id")
                coll_name = collection.get("name")
                if coll_id and coll_name:
                    # Store under the raw value AND its path-normalised form
                    coll_id_path = urlsplit(str(coll_id)).path or str(coll_id)
                    collection_id_to_names[str(coll_id)] = coll_name
                    if coll_id_path != str(coll_id):
                        collection_id_to_names[coll_id_path] = coll_name
            
            # Manyfold's list endpoint only returns @id+name per model — isPartOf is only
            # exposed in the detail endpoint (ModelSerializer). Fetch details to get collection.
            if collection_id_to_names:
                logger.info(
                    f"Fetching model details to resolve isPartOf for {len(model_rows)} models "
                    f"({len(collection_id_to_names)} collections available)"
                )
                for index, row in enumerate(model_rows):
                    ref = _model_ref_from_payload(row)
                    if not ref:
                        continue
                    try:
                        detail = client.get_model_detail(ref)
                        merged = {**row, **detail}

                        # Resolve preview_file @id to model file details, which include contentUrl.
                        preview_file_ref = detail.get("preview_file")
                        if isinstance(preview_file_ref, dict):
                            preview_file_id = str(preview_file_ref.get("@id") or "").strip()
                            if preview_file_id:
                                try:
                                    merged["preview_file_detail"] = client.get_model_file_detail(
                                        preview_file_id,
                                        model_ref=ref,
                                    )
                                except Exception as preview_error:
                                    logger.debug(
                                        f"Failed to fetch preview details for model {ref}: {preview_error}"
                                    )

                        # Merge detail fields into the list row so normalize_model_summary
                        # sees the full payload (name, isPartOf, creator, keywords, etc.)
                        model_rows[index] = merged
                    except Exception as e:
                        logger.warning(f"Failed to fetch detail for model {ref}: {e}")
                
                # Build model → collections mapping from isPartOf in merged payloads
                for row in model_rows:
                    model_ref = _model_ref_from_payload(row)
                    is_part_of = row.get("isPartOf")
                    
                    if model_ref and is_part_of:
                        if isinstance(is_part_of, dict):
                            collection_id_raw = is_part_of.get("@id")
                        else:
                            collection_id_raw = is_part_of
                        
                        if collection_id_raw:
                            # Try the raw value first, then path-normalised form
                            collection_id_path = urlsplit(str(collection_id_raw)).path or str(collection_id_raw)
                            collection_name = (
                                collection_id_to_names.get(str(collection_id_raw))
                                or collection_id_to_names.get(collection_id_path)
                            )
                            if collection_name:
                                model_to_collections[model_ref] = [collection_name]
                                logger.debug(
                                    f"Model {model_ref} → Collection '{collection_name}' "
                                    f"(isPartOf={collection_id_raw!r})"
                                )
                            else:
                                logger.debug(
                                    f"Model {model_ref}: isPartOf={collection_id_raw!r} "
                                    f"not found in collection_id_to_names keys: "
                                    f"{list(collection_id_to_names.keys())[:5]}"
                                )
                
                logger.info(
                    f"Resolved collections: {len(model_to_collections)}/{len(model_rows)} models have a collection"
                )
        except Exception as e:
            logger.error(f"CRITICAL: Failed to build collection_lookup: {e}", exc_info=True)
            collection_lookup = {}
        
        summaries = [
            normalize_model_summary(
                client.base_url,
                row,
                creator_lookup=creator_lookup,
                collection_lookup=collection_lookup,
                model_to_collections=model_to_collections,
            )
            for row in model_rows
        ]

        # Log collection population status
        models_with_collections = sum(1 for s in summaries if s.collection_names)
        logger.info(f"After normalization: {models_with_collections}/{len(summaries)} models have collection_names")
        if models_with_collections > 0:
            sample_names = [s.collection_names for s in summaries if s.collection_names][:3]
            logger.info(f"Sample collection names: {sample_names}")
    else:
        summaries = client.list_models()
    connection = connect(db_path)
    try:
        existing_count_row = connection.execute("SELECT COUNT(*) AS count FROM manyfold_model_summary_cache").fetchone()
        existing_count = int(existing_count_row["count"]) if existing_count_row else 0

        # Guardrail: if a refresh returns zero models while cache already has data,
        # keep the existing cache instead of wiping it due to a transient upstream issue.
        if not summaries and existing_count > 0:
            logger.warning(
                "Manyfold refresh returned 0 models while cache has %s rows; preserving existing cache.",
                existing_count,
            )
            preserved = read_cached_manyfold_summaries(db_path=db_path)
            return (
                preserved,
                {
                    "outcome": "preserved_cache_after_empty_live_result",
                    "live_model_count": 0,
                    "cache_count_before": existing_count,
                    "cache_count_after": len(preserved),
                    "preserved_cache": True,
                },
            )

        refreshed_at = utc_now_iso()
        active_model_keys: list[str] = []
        for index, summary in enumerate(summaries):
            raw_payload = model_rows[index] if model_rows is not None else asdict(summary)
            model_key = derive_manyfold_model_key(
                manyfold_model_url=summary.model_url,
                manyfold_model_public_id=summary.public_id,
                manyfold_model_id=summary.model_id,
            )
            active_model_keys.append(model_key)
            connection.execute(
                """
                INSERT INTO manyfold_model_summary_cache (
                    manyfold_model_key,
                    manyfold_model_url,
                    manyfold_model_public_id,
                    manyfold_model_name,
                    manyfold_model_id,
                    preview_url,
                    creator_name,
                    collection_names_json,
                    keyword_names_json,
                    raw_json,
                    refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(manyfold_model_key) DO UPDATE SET
                    manyfold_model_url = excluded.manyfold_model_url,
                    manyfold_model_public_id = excluded.manyfold_model_public_id,
                    manyfold_model_name = excluded.manyfold_model_name,
                    manyfold_model_id = excluded.manyfold_model_id,
                    preview_url = excluded.preview_url,
                    creator_name = excluded.creator_name,
                    collection_names_json = excluded.collection_names_json,
                    keyword_names_json = excluded.keyword_names_json,
                    raw_json = excluded.raw_json,
                    refreshed_at = excluded.refreshed_at
                """,
                (
                    model_key,
                    summary.model_url,
                    summary.public_id,
                    summary.name,
                    summary.model_id,
                    summary.preview_url,
                    summary.creator_name,
                    json.dumps(summary.collection_names),
                    json.dumps(summary.keyword_names),
                    json.dumps(raw_payload, sort_keys=True),
                    refreshed_at,
                ),
            )

        if active_model_keys:
            placeholders = ",".join("?" for _ in active_model_keys)
            connection.execute(
                f"DELETE FROM manyfold_model_summary_cache WHERE COALESCE(manyfold_model_key, '') NOT IN ({placeholders})",
                tuple(active_model_keys),
            )
        else:
            connection.execute("DELETE FROM manyfold_model_summary_cache")
        connection.commit()
    finally:
        connection.close()
    return (
        summaries,
        {
            "outcome": "live_refresh_applied_empty" if not summaries else "live_refresh_applied",
            "live_model_count": len(summaries),
            "cache_count_before": existing_count,
            "cache_count_after": len(summaries),
            "preserved_cache": False,
        },
    )


def refresh_manyfold_cache_with_status(*, db_path, client: ManyfoldClient) -> tuple[list[ManyfoldModelSummary], dict[str, Any]]:
    return _refresh_manyfold_cache_internal(db_path=db_path, client=client)


def refresh_manyfold_cache(*, db_path, client: ManyfoldClient) -> list[ManyfoldModelSummary]:
    summaries, _status = _refresh_manyfold_cache_internal(db_path=db_path, client=client)
    return summaries


def read_cached_manyfold_summaries(*, db_path) -> list[ManyfoldModelSummary]:
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT manyfold_model_url, manyfold_model_public_id, manyfold_model_id,
                   manyfold_model_name, preview_url, creator_name,
                   collection_names_json, keyword_names_json
            FROM manyfold_model_summary_cache
            ORDER BY manyfold_model_name COLLATE NOCASE
            """
        ).fetchall()
    finally:
        connection.close()
    summaries: list[ManyfoldModelSummary] = []
    for row in rows:
        summaries.append(
            ManyfoldModelSummary(
                model_url=str(row["manyfold_model_url"]),
                public_id=str(row["manyfold_model_public_id"] or "").strip() or None,
                model_id=str(row["manyfold_model_id"] or "").strip() or None,
                name=str(row["manyfold_model_name"]),
                preview_url=str(row["preview_url"] or "").strip() or None,
                creator_name=str(row["creator_name"] or "").strip() or None,
                collection_names=tuple(json.loads(str(row["collection_names_json"] or "[]"))),
                keyword_names=tuple(json.loads(str(row["keyword_names_json"] or "[]"))),
            )
        )
    return summaries


def read_cached_manyfold_models(*, db_path) -> list[CachedManyfoldModel]:
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT manyfold_model_url, manyfold_model_public_id, manyfold_model_id,
                   manyfold_model_name, preview_url, creator_name,
                   collection_names_json, keyword_names_json, raw_json
            FROM manyfold_model_summary_cache
            ORDER BY manyfold_model_name COLLATE NOCASE
            """
        ).fetchall()
    finally:
        connection.close()

    cached_models: list[CachedManyfoldModel] = []
    for row in rows:
        raw_json = str(row["raw_json"] or "{}").strip() or "{}"
        try:
            raw_payload = json.loads(raw_json)
        except json.JSONDecodeError:
            raw_payload = {}
        if not isinstance(raw_payload, dict):
            raw_payload = {}
        cached_models.append(
            CachedManyfoldModel(
                summary=ManyfoldModelSummary(
                    model_url=str(row["manyfold_model_url"]),
                    public_id=str(row["manyfold_model_public_id"] or "").strip() or None,
                    model_id=str(row["manyfold_model_id"] or "").strip() or None,
                    name=str(row["manyfold_model_name"]),
                    preview_url=str(row["preview_url"] or "").strip() or None,
                    creator_name=str(row["creator_name"] or "").strip() or None,
                    collection_names=tuple(json.loads(str(row["collection_names_json"] or "[]"))),
                    keyword_names=tuple(json.loads(str(row["keyword_names_json"] or "[]"))),
                ),
                raw_payload=raw_payload,
            )
        )
    return cached_models
