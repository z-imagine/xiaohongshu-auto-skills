"""Standalone bridge server entrypoint."""

from __future__ import annotations

import asyncio
import logging
import sys

import websockets

from .config import build_parser, config_from_args
from .router import BridgeRouter

logger = logging.getLogger("xhs-bridge")


async def serve() -> None:
    """Start the bridge server with CLI configuration."""
    parser = build_parser()
    args = parser.parse_args()
    config = config_from_args(args)

    router = BridgeRouter(token=config.token)
    async with websockets.serve(router.handle, config.host, config.port):
        logger.info("Bridge server 已启动: ws://%s:%d", config.host, config.port)
        logger.info("等待浏览器扩展连接...")
        await asyncio.Future()


def main() -> None:
    """CLI entrypoint."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(serve())


if __name__ == "__main__":
    main()

