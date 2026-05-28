from __future__ import annotations

import asyncio
import zipfile
from io import BytesIO
from pathlib import Path

import httpx

from app.providers.makerworld import AuthenticationError, MakerWorldAdapter, ProviderUnavailableError


def _minimal_3mf_payload() -> bytes:
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr(
                        "_rels/.rels",
                        """<?xml version='1.0' encoding='UTF-8'?>
<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>
    <Relationship Id='rel0' Type='http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel' Target='/3D/3dmodel.model'/>
</Relationships>""",
                )
                archive.writestr(
                        "3D/3dmodel.model",
                        """<?xml version='1.0' encoding='UTF-8'?>
<model unit='millimeter' xmlns='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'>
    <resources />
    <build />
</model>""",
                )
        return buffer.getvalue()


def test_parse_design_id_from_url_supports_documented_variants() -> None:
    adapter = MakerWorldAdapter("token")

    assert adapter.parse_design_id_from_url("https://makerworld.com/en/models/1295917") == 1295917
    assert adapter.parse_design_id_from_url("https://makerworld.com/en/models/1295917-big-brick-man") == 1295917
    assert adapter.parse_design_id_from_url("https://makerworld.com/models/1295917") == 1295917
    assert adapter.parse_design_id_from_url("https://makerworld.com/en/models/1295917#profileId=abc123") == 1295917
    assert adapter.parse_design_id_from_url("https://www.makerworld.com/en/models/1295917-big-brick-man") == 1295917
    assert adapter.parse_design_id_from_url("https://makerworld.com/en/designs/1295917") is None
    assert adapter.parse_design_id_from_url("https://example.com/en/models/1295917") is None


def test_parse_instance_id_from_url_supports_profile_fragment_variants() -> None:
    adapter = MakerWorldAdapter("token")

    assert adapter.parse_instance_id_from_url("https://makerworld.com/en/models/2843338-deadpool#profileId-3170083") == 3170083
    assert adapter.parse_instance_id_from_url("https://makerworld.com/en/models/1295917#profileId=1309483") == 1309483
    assert adapter.parse_instance_id_from_url("https://makerworld.com/en/models/1295917?profileId=1309483") == 1309483
    assert adapter.parse_instance_id_from_url("https://makerworld.com/en/models/1295917") is None
    assert adapter.parse_instance_id_from_url("https://example.com/en/models/1295917#profileId-1309483") is None


def test_resolve_design_id_preserves_profile_ids_in_file_manifest() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer token"
        return httpx.Response(
            200,
            json={
                "id": 2843338,
                "title": "Deadpool Sitting Shelf Figure",
                "designCreator": {"uid": 123, "name": "creator", "avatar": "https://example.com/avatar.png"},
                "profiles": [
                    {
                        "instanceId": 3171088,
                        "profileId": 3170083,
                        "isDefault": False,
                        "title": "Single Color",
                        "plates": [{"index": 1}],
                    },
                    {
                        "instanceId": 3171089,
                        "profileId": 3170084,
                        "isDefault": True,
                        "title": "AMS",
                        "plates": [{"index": 1}, {"index": 2}],
                    },
                ],
            },
        )

    adapter = MakerWorldAdapter(
        "token",
        api_base="https://api.example.invalid/v1",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(adapter.resolve_design_id(2843338))

    assert result is not None
    assert result.design.default_instance_id == 3171089
    assert result.file_manifest == [
        {
            "instance_id": 3171088,
            "profile_id": 3170083,
            "title": "Single Color",
            "is_default": False,
            "plate_count": 1,
        },
        {
            "instance_id": 3171089,
            "profile_id": 3170084,
            "title": "AMS",
            "is_default": True,
            "plate_count": 2,
        },
    ]


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


def test_resolve_design_id_falls_back_to_cover_and_design_pictures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": 1295917,
                "title": "Big Brick Man",
                "designCreator": {"uid": 1234567890, "name": "pippo the printer"},
                "summary": "Large display figurine.",
                "instances": [
                    {
                        "id": 1309482,
                        "isDefault": False,
                        "title": "Default",
                        "plates": [],
                    }
                ],
                "tags": ["brick", "figure"],
                "coverUrl": "https://makerworld.bblmw.com/cover.jpg",
                "designExtension": {
                    "design_pictures": [
                        {"url": "https://makerworld.bblmw.com/cover.jpg", "isRealLifePhoto": 0},
                        {"url": "https://makerworld.bblmw.com/detail-1.jpg", "isRealLifePhoto": 0},
                    ]
                },
            },
        )

    adapter = MakerWorldAdapter(
        "token",
        api_base="https://api.example.invalid/v1",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(adapter.resolve_design_id(1295917))

    assert result is not None
    assert result.design.tags == ["brick", "figure"]
    assert result.design.images == [
        {"url": "https://makerworld.bblmw.com/cover.jpg", "role": "cover"},
        {"url": "https://makerworld.bblmw.com/detail-1.jpg", "isRealLifePhoto": 0},
    ]


def test_resolve_design_id_unwraps_nested_data_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "success",
                "data": {
                    "id": 87439,
                    "title": "Espresso Cup Tree",
                    "designCreator": {"uid": 42, "name": "coffee_fan"},
                    "instances": [{"id": 93597, "isDefault": True, "title": "Default", "plates": []}],
                },
            },
        )

    adapter = MakerWorldAdapter(
        "token",
        api_base="https://api.example.invalid/v1",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(adapter.resolve_design_id(87439))

    assert result is not None
    assert result.design.design_id == 87439
    assert result.design.title == "Espresso Cup Tree"
    assert result.file_manifest[0]["instance_id"] == 93597


def test_resolve_design_id_preserves_metadata_when_instances_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": 1937453,
                "title": "Mug Tree",
                "designCreator": {"uid": 77, "name": "kitchenprints"},
                "summary": "Countertop mug organizer.",
                "coverUrl": "https://makerworld.bblmw.com/mug-tree.jpg",
            },
        )

    adapter = MakerWorldAdapter(
        "token",
        api_base="https://api.example.invalid/v1",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(adapter.resolve_design_id(1937453))

    assert result is not None
    assert result.design.design_id == 1937453
    assert result.design.title == "Mug Tree"
    assert result.design.creator_name == "kitchenprints"
    assert result.design.default_instance_id == 0
    assert result.file_manifest == []
    assert "makerworld_no_instances" in result.warnings


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
    payload = _minimal_3mf_payload()
    captured_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update({key: value for key, value in request.headers.items()})
        assert str(request.url) == "https://api.example.invalid/v1/design-service/instance/1309482/f3mf?type=download"
        return httpx.Response(200, content=payload)

    adapter = MakerWorldAdapter(
        "token",
        api_base="https://api.example.invalid/v1",
        transport=httpx.MockTransport(handler),
    )

    destination = tmp_path / "downloaded.3mf"
    result = asyncio.run(adapter.download_3mf(1309482, destination))

    assert result == destination
    assert destination.read_bytes() == payload
    assert captured_headers["authorization"] == "Bearer token"
    assert captured_headers["accept"] == "application/octet-stream, */*;q=0.9"
    assert captured_headers["origin"] == "https://makerworld.com"
    assert captured_headers["referer"] == "https://makerworld.com/"
    assert "mozilla/5.0" in captured_headers["user-agent"].lower()


def test_download_3mf_classifies_418_as_access_blocked(tmp_path: Path) -> None:
    adapter = MakerWorldAdapter(
        "token",
        api_base="https://api.example.invalid/v1",
        transport=httpx.MockTransport(lambda request: httpx.Response(418, text="blocked")),
    )

    destination = tmp_path / "downloaded.3mf"

    try:
        asyncio.run(adapter.download_3mf(1309482, destination))
    except ProviderUnavailableError as exc:
        assert "status 418" in str(exc)
        assert "blocked" in str(exc)
    else:
        raise AssertionError("Expected ProviderUnavailableError")


def test_download_3mf_rejects_invalid_payload(tmp_path: Path) -> None:
    adapter = MakerWorldAdapter(
        "token",
        api_base="https://api.example.invalid/v1",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'{"error":"bad download"}')),
    )

    destination = tmp_path / "downloaded.3mf"

    try:
        asyncio.run(adapter.download_3mf(1309482, destination))
    except ProviderUnavailableError as exc:
        assert "valid 3MF package" in str(exc)
    else:
        raise AssertionError("Expected ProviderUnavailableError")

    assert not destination.exists()


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