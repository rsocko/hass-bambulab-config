from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from .db import connect
from .models import ManyfoldModelSummary


MANYFOLD_API_ACCEPT = "application/vnd.manyfold.v0+json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        self._client = http_client or httpx.Client(base_url=self.base_url, timeout=15.0, trust_env=False)
        self._owns_client = http_client is None
        self._access_token: str | None = None

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
        response = self._client.get(self.models_path, headers=self._request_headers())
        response.raise_for_status()
        payload = response.json()
        rows = self._extract_rows(payload)
        return [normalize_model_summary(self.base_url, row) for row in rows]

    def get_model_detail(self, model_ref: str) -> dict[str, Any]:
        path = self._resolve_ref_path(model_ref, default_prefix=self.models_path)
        response = self._client.get(path, headers=self._request_headers())
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Manyfold model detail response was not a JSON object.")
        return payload

    def get_model_file_detail(self, file_ref: str, *, model_ref: str | None = None) -> dict[str, Any]:
        normalized_file_ref = str(file_ref or "").strip()
        if not normalized_file_ref:
            raise ValueError("Manyfold file reference cannot be empty.")
        if normalized_file_ref.startswith("http://") or normalized_file_ref.startswith("https://") or normalized_file_ref.startswith("/"):
            path = self._resolve_ref_path(normalized_file_ref, default_prefix="/model_files")
        elif model_ref:
            model_path = self._resolve_ref_path(model_ref, default_prefix=self.models_path)
            path = f"{model_path.rstrip('/')}/files/{quote(normalized_file_ref, safe='')}"
        else:
            path = f"/model_files/{quote(normalized_file_ref, safe='')}"
        response = self._client.get(path, headers=self._request_headers())
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Manyfold model file detail response was not a JSON object.")
        return payload

    def list_collections(self) -> list[dict[str, Any]]:
        response = self._client.get(self.collections_path, headers=self._request_headers())
        response.raise_for_status()
        return self._extract_rows(response.json())

    def list_creators(self) -> list[dict[str, Any]]:
        response = self._client.get(self.creators_path, headers=self._request_headers())
        response.raise_for_status()
        return self._extract_rows(response.json())


def normalize_model_summary(base_url: str, payload: dict[str, Any]) -> ManyfoldModelSummary:
    preview = payload.get("preview") or payload.get("preview_file") or {}
    creator = payload.get("creator") or {}
    collections = payload.get("collections") or []
    keywords = payload.get("keywords") or payload.get("tags") or []
    model_url = str(payload.get("url") or payload.get("@id") or "").strip()
    if not model_url and payload.get("id") is not None:
        model_url = f"{base_url.rstrip('/')}/models/{payload['id']}"
    elif model_url.startswith("/"):
        model_url = f"{base_url.rstrip('/')}{model_url}"
    elif model_url.startswith("http://") or model_url.startswith("https://"):
        parsed_model_url = urlsplit(model_url)
        if parsed_model_url.path.startswith("/models/"):
            model_url = f"{base_url.rstrip('/')}{parsed_model_url.path}"
            if parsed_model_url.query:
                model_url += f"?{parsed_model_url.query}"

    def _extract_name(value: Any) -> str | None:
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, dict):
            nested = value.get("name") or value.get("title") or value.get("label")
            return _extract_name(nested)
        return None

    return ManyfoldModelSummary(
        model_url=model_url,
        public_id=str(payload.get("public_id") or "").strip() or None,
        model_id=str(payload.get("id") or "").strip() or None,
        name=str(payload.get("name") or payload.get("title") or "Unnamed Model").strip(),
        preview_url=str(preview.get("url") or preview.get("thumbnail_url") or "").strip() or None,
        creator_name=_extract_name(creator),
        collection_names=tuple(filter(None, (_extract_name(item) for item in collections))),
        keyword_names=tuple(filter(None, (_extract_name(item) for item in keywords))),
    )


def refresh_manyfold_cache(*, db_path, client: ManyfoldClient) -> list[ManyfoldModelSummary]:
    summaries = client.list_models()
    connection = connect(db_path)
    try:
        refreshed_at = utc_now_iso()
        for summary in summaries:
            connection.execute(
                """
                INSERT INTO manyfold_model_summary_cache (
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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(manyfold_model_url) DO UPDATE SET
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
                    summary.model_url,
                    summary.public_id,
                    summary.name,
                    summary.model_id,
                    summary.preview_url,
                    summary.creator_name,
                    json.dumps(summary.collection_names),
                    json.dumps(summary.keyword_names),
                    json.dumps(asdict(summary), sort_keys=True),
                    refreshed_at,
                ),
            )
        connection.commit()
    finally:
        connection.close()
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
