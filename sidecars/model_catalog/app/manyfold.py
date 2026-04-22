from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import httpx

from .db import connect
from .models import ManyfoldModelSummary


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ManyfoldClient:
    def __init__(
        self,
        base_url: str,
        *,
        models_path: str = "/models.json",
        oauth_token_path: str = "/oauth/token",
        client_id: str | None = None,
        client_secret: str | None = None,
        oauth_scopes: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.models_path = models_path
        self.oauth_token_path = oauth_token_path
        self.client_id = client_id
        self.client_secret = client_secret
        self.oauth_scopes = oauth_scopes
        self._client = http_client or httpx.Client(base_url=self.base_url, timeout=15.0)
        self._owns_client = http_client is None
        self._access_token: str | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _auth_headers(self) -> dict[str, str]:
        if not self.client_id or not self.client_secret:
            return {}
        if not self._access_token:
            form_data: dict[str, str] = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
            if self.oauth_scopes:
                form_data["scope"] = self.oauth_scopes
            response = self._client.post(self.oauth_token_path, data=form_data)
            response.raise_for_status()
            payload = response.json()
            self._access_token = str(payload.get("access_token") or "").strip() or None
            if not self._access_token:
                raise RuntimeError("Manyfold OAuth token response did not include access_token.")
        return {"Authorization": f"Bearer {self._access_token}"}

    def list_models(self) -> list[ManyfoldModelSummary]:
        response = self._client.get(self.models_path, headers=self._auth_headers())
        response.raise_for_status()
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("models") or payload.get("data") or []
        return [normalize_model_summary(self.base_url, row) for row in rows]


def normalize_model_summary(base_url: str, payload: dict[str, Any]) -> ManyfoldModelSummary:
    preview = payload.get("preview") or payload.get("preview_file") or {}
    creator = payload.get("creator") or {}
    collections = payload.get("collections") or []
    keywords = payload.get("keywords") or payload.get("tags") or []
    model_url = str(payload.get("url") or "").strip()
    if not model_url and payload.get("id") is not None:
        model_url = f"{base_url.rstrip('/')}/models/{payload['id']}"

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
