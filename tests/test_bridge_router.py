from __future__ import annotations

import asyncio
import json

from bridge.auth import is_token_allowed
from bridge.router import BridgeRouter


class FakeSocket:
    def __init__(self) -> None:
        self.sent_messages: list[dict] = []

    async def send(self, raw: str) -> None:
        self.sent_messages.append(json.loads(raw))


class EchoExtensionSocket:
    def __init__(self, router: BridgeRouter) -> None:
        self._router = router

    async def send(self, raw: str) -> None:
        payload = json.loads(raw)
        self._router._sessions.resolve_pending(
            payload["id"],
            {
                "id": payload["id"],
                "result": {
                    "ok": True,
                    "method": payload["method"],
                    "session_id": payload["session_id"],
                },
            },
        )


def test_is_token_allowed() -> None:
    assert is_token_allowed("", None) is True
    assert is_token_allowed("secret", "secret") is True
    assert is_token_allowed("secret", "") is False


def test_ping_server_uses_session_scope() -> None:
    async def scenario() -> None:
        router = BridgeRouter(token="")
        cli_ws = FakeSocket()
        router._sessions.register_extension("session-a", FakeSocket(), "1.0.0")
        await router._handle_cli(cli_ws, {"method": "ping_server", "session_id": "session-a"})
        assert cli_ws.sent_messages == [
            {
                "result": {
                    "server_running": True,
                    "session_id": "session-a",
                    "extension_connected": True,
                }
            }
        ]

    asyncio.run(scenario())


def test_cli_request_requires_session_id() -> None:
    async def scenario() -> None:
        router = BridgeRouter(token="")
        cli_ws = FakeSocket()
        await router._handle_cli(cli_ws, {"method": "navigate"})
        assert cli_ws.sent_messages == [{"error": "CLI 请求缺少 session_id"}]

    asyncio.run(scenario())


def test_cli_request_routes_to_matching_extension() -> None:
    async def scenario() -> None:
        router = BridgeRouter(token="")
        cli_ws = FakeSocket()
        extension_ws = EchoExtensionSocket(router)
        router._sessions.register_extension("session-a", extension_ws, "1.0.0")

        await router._handle_cli(
            cli_ws,
            {
                "role": "cli",
                "method": "navigate",
                "session_id": "session-a",
                "params": {"url": "https://www.xiaohongshu.com/"},
            },
        )

        assert cli_ws.sent_messages[0]["result"]["ok"] is True
        assert cli_ws.sent_messages[0]["result"]["method"] == "navigate"
        assert cli_ws.sent_messages[0]["result"]["session_id"] == "session-a"

    asyncio.run(scenario())
