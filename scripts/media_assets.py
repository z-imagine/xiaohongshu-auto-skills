"""Temporary publish asset preparation for bridge-based uploads."""

from __future__ import annotations

import hashlib
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

import requests

from xhs.types import UploadAsset

_DEFAULT_UPLOAD_TIMEOUT = 120


def is_remote_url(path: str) -> bool:
    """Return True when the input references a remote HTTP(S) resource."""
    return path.lower().startswith(("http://", "https://"))


class TempAssetUploader:
    """Uploads local files to a temporary asset service before publish."""

    def __init__(self) -> None:
        self._endpoint = os.getenv("XHS_ASSET_UPLOAD_ENDPOINT", "").strip()
        self._token = os.getenv("XHS_ASSET_UPLOAD_TOKEN", "").strip()
        self._timeout = int(os.getenv("XHS_ASSET_UPLOAD_TIMEOUT", str(_DEFAULT_UPLOAD_TIMEOUT)))
        self._session = requests.Session()

    @property
    def is_configured(self) -> bool:
        """Whether a remote asset upload endpoint is available."""
        return bool(self._endpoint)

    def upload_file(self, path: str, purpose: str = "xhs-publish-asset") -> UploadAsset:
        """Upload a local file and return the resulting temporary asset."""
        if not self.is_configured:
            raise RuntimeError("未配置 XHS_ASSET_UPLOAD_ENDPOINT，无法上传本地文件到临时存储")

        resolved = Path(path).resolve()
        content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        with resolved.open("rb") as fh:
            response = self._session.post(
                self._endpoint,
                headers=headers,
                files={"file": (resolved.name, fh, content_type)},
                data={"purpose": purpose},
                timeout=self._timeout,
            )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("asset", payload)
        asset_url = str(
            data.get("url")
            or data.get("download_url")
            or data.get("signed_url")
            or ""
        ).strip()
        if not asset_url:
            raise RuntimeError("临时资源上传成功，但响应中缺少可下载 url")

        return UploadAsset(
            name=str(data.get("name") or resolved.name),
            source_url=asset_url,
            content_type=str(data.get("type") or data.get("content_type") or content_type),
            size=int(data.get("size") or resolved.stat().st_size),
            sha256=str(data.get("sha256") or _sha256_of_file(str(resolved))),
            source=str(resolved),
        )


def prepare_upload_assets(
    files: list[str],
    require_remote: bool = False,
    purpose: str = "xhs-publish-asset",
) -> list[UploadAsset]:
    """Prepare file inputs for publish flows.

    Rules:
    - Existing remote URLs are passed through as temporary assets.
    - Local files are uploaded to the configured temp asset service when needed.
    - Local bridge mode may still fall back to direct local paths for compatibility.
    """
    uploader = TempAssetUploader()
    assets: list[UploadAsset] = []

    for file_path in files:
        if is_remote_url(file_path):
            assets.append(_build_remote_asset(file_path))
            continue

        if not os.path.exists(file_path):
            continue

        if require_remote:
            if not uploader.is_configured:
                raise RuntimeError(
                    "当前 bridge 为远端模式，本地文件必须先上传到临时存储。"
                    "请配置 XHS_ASSET_UPLOAD_ENDPOINT，或直接传入可访问文件 URL。"
                )
            assets.append(uploader.upload_file(file_path, purpose=purpose))
            continue

        if uploader.is_configured:
            assets.append(uploader.upload_file(file_path, purpose=purpose))
            continue

        resolved = str(Path(file_path).resolve())
        assets.append(_build_local_asset(resolved))

    return assets


def prepare_image_assets(images: list[str], require_remote: bool = False) -> list[UploadAsset]:
    """Prepare image assets for image publish flows."""
    return prepare_upload_assets(
        images,
        require_remote=require_remote,
        purpose="xhs-publish-image",
    )


def prepare_video_asset(video: str, require_remote: bool = False) -> UploadAsset:
    """Prepare a single video asset for publish flows."""
    assets = prepare_upload_assets(
        [video],
        require_remote=require_remote,
        purpose="xhs-publish-video",
    )
    if not assets:
        raise RuntimeError("没有有效的视频资源")
    return assets[0]


def _build_remote_asset(url: str) -> UploadAsset:
    parsed = urlparse(url)
    filename = Path(parsed.path).name or "image"
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return UploadAsset(
        name=filename,
        source_url=url,
        content_type=content_type,
        source=url,
    )


def _build_local_asset(path: str) -> UploadAsset:
    resolved = Path(path).resolve()
    content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    return UploadAsset(
        name=resolved.name,
        source_path=str(resolved),
        content_type=content_type,
        size=resolved.stat().st_size,
        sha256=_sha256_of_file(str(resolved)),
        source=str(resolved),
    )


def _sha256_of_file(path: str) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()
