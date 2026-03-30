"""Bridge server configuration."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass


@dataclass(slots=True)
class BridgeConfig:
    """Runtime configuration for the bridge service."""

    host: str = "127.0.0.1"
    port: int = 9333
    token: str = ""


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser used by the bridge server."""
    parser = argparse.ArgumentParser(description="XHS Extension Bridge Server")
    parser.add_argument(
        "--host",
        default=os.getenv("XHS_BRIDGE_HOST", "127.0.0.1"),
        help="监听地址（默认 127.0.0.1）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("XHS_BRIDGE_PORT", "9333")),
        help="监听端口（默认 9333）",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("XHS_BRIDGE_TOKEN", ""),
        help="bridge 鉴权 token（必填，可用 XHS_BRIDGE_TOKEN）",
    )
    return parser


def config_from_args(args: argparse.Namespace) -> BridgeConfig:
    """Convert parsed CLI args into a config object."""
    if not args.token:
        raise SystemExit("bridge 启动失败：必须通过 --token 或 XHS_BRIDGE_TOKEN 配置鉴权 token")
    return BridgeConfig(
        host=args.host,
        port=args.port,
        token=args.token,
    )
