"""Standalone bridge server entrypoint."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiohttp import web

from .config import build_parser, config_from_args
from .models import BridgeError
from .router import BridgeRouter

logger = logging.getLogger("xhs-bridge")


def create_app(router: BridgeRouter) -> web.Application:
    """Create the combined HTTP + WebSocket bridge app."""
    app = web.Application(client_max_size=50 * 1024 * 1024)

    async def health(_request: web.Request) -> web.Response:
        return web.json_response({
            "ok": True,
            "server_running": True,
            "active_sessions": router.active_sessions_count(),
        })

    async def rpc(request: web.Request) -> web.Response:
        try:
            msg = await request.json()
        except Exception:
            bridge_error = BridgeError("INVALID_JSON", "请求体不是合法 JSON")
            return web.json_response(
                router.error_payload(bridge_error),
                status=router.error_status_code(bridge_error),
            )
        if not isinstance(msg, dict):
            bridge_error = BridgeError("INVALID_JSON", "请求体必须是 JSON 对象")
            return web.json_response(
                router.error_payload(bridge_error),
                status=router.error_status_code(bridge_error),
            )
        msg.setdefault("role", "cli")
        if not router._is_authorized(msg):
            bridge_error = BridgeError("AUTH_FAILED", "Bridge 鉴权失败")
            return web.json_response(
                router.error_payload(bridge_error),
                status=router.error_status_code(bridge_error),
            )
        try:
            result = await router.execute_cli_rpc(msg)
            return web.json_response(result)
        except BridgeError as exc:
            return web.json_response(
                router.error_payload(exc),
                status=router.error_status_code(exc),
            )

    async def session_state(request: web.Request) -> web.Response:
        session_id = request.match_info["session_id"]
        token = request.query.get("token", "")
        if not router._is_authorized({"token": token}):
            error = BridgeError("AUTH_FAILED", "Bridge 鉴权失败")
            return web.json_response(router.error_payload(error), status=router.error_status_code(error))
        return web.json_response({"result": router.get_session_snapshot(session_id)})

    app.router.add_get("/", router.handle_ws)
    app.router.add_get("/ws", router.handle_ws)
    app.router.add_post("/rpc", rpc)
    app.router.add_get("/health", health)
    app.router.add_get("/sessions/{session_id}", session_state)
    return app


async def serve() -> None:
    """Start the bridge server with CLI configuration."""
    parser = build_parser()
    args = parser.parse_args()
    config = config_from_args(args)

    router = BridgeRouter(token=config.token)
    app = create_app(router)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.host, config.port)
    await site.start()
    logger.info("Bridge server 已启动: ws://%s:%d", config.host, config.port)
    logger.info("HTTP RPC 已启用: http://%s:%d/rpc", config.host, config.port)
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
