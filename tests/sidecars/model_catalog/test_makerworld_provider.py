from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from app.providers.makerworld import AuthenticationError, MakerWorldAdapter, ProviderUnavailableError


def test_parse_design_id_from_url_supports_documented_variants() -> None:
    adapter = MakerWorldAdapter("token")

    assert adapter.parse_design_id_from_url("https://makerworld.com/en/models/1295917") == 1295917
    assert adapter.parse_design_id_from_url("https://makerworld.com/en/models/1295917-big-brick-man") == 1295917
    assert adapter.parse_design_id_from_url("https://makerworld.com/models/1295917") == 1295917
    assert adapter.parse_design_id_from_url("https://makerworld.com/en/models/1295917#profileId=abc123") == 1295917
    assert adapter.parse_design_id_from_url("https://www.makerworld.com/en/models/1295917-big-brick-man") == 1295917
    assert adapter.parse_design_id_from_url("https://makerworld.com/en/designs/1295917") is None
    assert adapter.parse_design_id_from_url("https://example.com/en/models/1295917") is None


def test_resolve_design_id_normalizes_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer token"
        assert str(request.url) == "https://api.example.invalid/v1/design-service/design/1295917"
        return httpx.Response(
            200,
            json={
                "id": 1295917,
                "title": "Big Brick Man",
                "designCreator": {
                    "uid": 1234567890,
                    "name": "pippo_the_printer",
                    "avatar": "https://public-cdn.bambulab.com/avatar/example.png",
                },
                "summary": "Large display figurine.",
                "instances": [
                    {
                        "id": 1309482,
                        "isDefault": True,
                        "title": "Default",
                        "plates": [{"index": 1}, {"index": 2}],
                    },
                    {
                        "id": 1309483,
                        "isDefault": False,
                        "title": "Single Color",
                        "plates": [{"index": 1}],
                    },
                ],
                "tags": [{"id": 42, "name": "figurine"}, {"id": 99, "name": "toy"}],
                "images": [{"url": "https://makerworld.bblmw.com/example.jpg", "width": 1920, "height": 1080}],
                "likeCount": 342,
                "downloadCount": 1205,
                "collectCount": 89,
                "license": "CC BY-NC 4.0",
                "createTime": "2025-11-15T08:30:00Z",
                "updateTime": "2026-01-20T14:15:00Z",
            },
        )

    adapter = MakerWorldAdapter(
        "token",
        api_base="https://api.example.invalid/v1",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(
        adapter.resolve_design_id(
            1295917,
            source_url="https://makerworld.com/en/models/1295917-big-brick-man",
        )
    )

    assert result is not None
    assert result.confidence == "high"
    assert result.design.design_id == 1295917
    assert result.design.creator_name == "pippo_the_printer"
    assert result.design.default_instance_id == 1309482
    assert result.design.canonical_url == "https://makerworld.com/en/models/1295917"
    assert result.file_manifest == [
        {
            "instance_id": 1309482,
            "title": "Default",
            "is_default": True,
            "plate_count": 2,
        },
        {
            "instance_id": 1309483,
            "title": "Single Color",
            "is_default": False,
            "plate_count": 1,
        },
    ]


def test_resolve_design_id_returns_none_for_404() -> None:
    adapter = MakerWorldAdapter(
        "token",
        api_base="https://api.example.invalid/v1",
        transport=httpx.MockTransport(lambda request: httpx.Response(404, json={"error": "not_found"})),
    )

    result = asyncio.run(adapter.resolve_design_id(1295917))

    assert result is None


def test_resolve_design_id_raises_authentication_error_for_401() -> None:
    adapter = MakerWorldAdapter(
        "token",
        api_base="https://api.example.invalid/v1",
        transport=httpx.MockTransport(lambda request: httpx.Response(401, json={"error": "unauthorized"})),
    )

    try:
        asyncio.run(adapter.resolve_design_id(1295917))
    except AuthenticationError:
        pass
    else:
        raise AssertionError("Expected AuthenticationError")


def test_download_3mf_writes_binary_file(tmp_path: Path) -> None:
    payload = b"makerworld-3mf-binary"
    adapter = MakerWorldAdapter(
        "token",
        api_base="https://api.example.invalid/v1",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=payload)),
    )

    destination = tmp_path / "downloaded.3mf"
    result = asyncio.run(adapter.download_3mf(1309482, destination))

    assert result == destination
    assert destination.read_bytes() == payload


def test_resolve_design_id_raises_provider_unavailable_for_invalid_json() -> None:
    adapter = MakerWorldAdapter(
        "token",
        api_base="https://api.example.invalid/v1",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not-json")),
    )

    try:
        asyncio.run(adapter.resolve_design_id(1295917))
    except ProviderUnavailableError:
        pass
    else:
        raise AssertionError("Expected ProviderUnavailableError")