"""User-level configuration for the XHS CLI."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

CONFIG_DIR_NAME: Final = ".xiaohongshu-auto-skills"
CONFIG_FILE_NAME: Final = "config.json"
CONFIG_KEYS: Final = ("bridge_url", "bridge_token", "bridge_session_id")


@dataclass(frozen=True)
class BridgeConfig:
    bridge_url: str
    bridge_token: str
    bridge_session_id: str


def config_path() -> Path:
    """Return the per-user CLI configuration path."""
    return Path.home() / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def load_bridge_config(path: Path | None = None) -> BridgeConfig | None:
    """Load a complete bridge configuration, if one has been saved."""
    path = path or config_path()
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取 bridge 配置文件: {path}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"bridge 配置文件格式错误: {path}")

    values = {key: payload.get(key) for key in CONFIG_KEYS}
    if not all(isinstance(value, str) and value.strip() for value in values.values()):
        raise RuntimeError(f"bridge 配置不完整: {path}")

    return BridgeConfig(**values)


def save_bridge_config(config: BridgeConfig, path: Path | None = None) -> Path:
    """Atomically save bridge configuration with owner-only permissions."""
    path = path or config_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)

    payload = json.dumps(
        {
            "bridge_url": config.bridge_url,
            "bridge_token": config.bridge_token,
            "bridge_session_id": config.bridge_session_id,
        },
        ensure_ascii=False,
        indent=2,
    )

    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"{payload}\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return path
