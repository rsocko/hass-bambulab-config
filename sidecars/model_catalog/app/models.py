from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ManyfoldModelSummary:
    model_url: str
    public_id: str | None
    model_id: str | None
    name: str
    preview_url: str | None
    creator_name: str | None
    collection_names: tuple[str, ...]
    keyword_names: tuple[str, ...]
