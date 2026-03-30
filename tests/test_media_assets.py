from __future__ import annotations

from pathlib import Path

import pytest

from media_assets import prepare_image_assets, prepare_video_asset


def test_prepare_image_assets_keeps_remote_url() -> None:
    assets = prepare_image_assets(["https://example.com/assets/demo.png"], require_remote=True)
    assert len(assets) == 1
    assert assets[0].source_url == "https://example.com/assets/demo.png"
    assert assets[0].name == "demo.png"


def test_prepare_image_assets_uses_local_path_when_remote_not_required(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    image_path.write_bytes(b"fake-image")

    assets = prepare_image_assets([str(image_path)], require_remote=False)
    assert len(assets) == 1
    assert assets[0].source_path == str(image_path.resolve())
    assert assets[0].size == len(b"fake-image")


def test_prepare_image_assets_requires_upload_service_for_remote_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_path = tmp_path / "sample.jpg"
    image_path.write_bytes(b"fake-image")
    monkeypatch.delenv("XHS_ASSET_UPLOAD_ENDPOINT", raising=False)

    with pytest.raises(RuntimeError, match="XHS_ASSET_UPLOAD_ENDPOINT"):
        prepare_image_assets([str(image_path)], require_remote=True)


def test_prepare_video_asset_uses_remote_url_directly() -> None:
    asset = prepare_video_asset("https://example.com/assets/demo.mp4", require_remote=True)
    assert asset.source_url == "https://example.com/assets/demo.mp4"
    assert asset.name == "demo.mp4"
