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
        result = cli_ws.sent_messages[0]["result"]
        assert result["server_running"] is True
        assert result["session_id"] == "session-a"
        assert result["extension_connected"] is True
        assert result["session"]["connected"] is True
        assert result["active_sessions"] == 1

    asyncio.run(scenario())


def test_session_id_is_allocated_for_extension_when_missing() -> None:
    router = BridgeRouter(token="")
    session_id, assigned = router._sessions.allocate_session_id("")
    assert assigned is True
    assert session_id == "default"

    router._sessions.register_extension(session_id, FakeSocket(), "1.0.0")
    next_session_id, next_assigned = router._sessions.allocate_session_id("")
    assert next_assigned is True
    assert next_session_id != session_id
    assert next_session_id.startswith("session-")


def test_cli_request_requires_session_id() -> None:
    async def scenario() -> None:
        router = BridgeRouter(token="")
        cli_ws = FakeSocket()
        await router._handle_cli(cli_ws, {"method": "navigate"})
        assert cli_ws.sent_messages == [{"error": "CLI 请求缺少 session_id", "error_code": "MISSING_SESSION_ID"}]

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


def test_heartbeat_updates_session_state() -> None:
    router = BridgeRouter(token="")
    router._sessions.register_extension("session-a", FakeSocket(), "1.0.0")
    router._sessions.touch_session("session-a", heartbeat=True)

    snapshot = router.get_session_snapshot("session-a")
    assert snapshot["last_heartbeat_at"] is not None


def test_get_session_state_returns_structured_snapshot() -> None:
    async def scenario() -> None:
        router = BridgeRouter(token="")
        cli_ws = FakeSocket()
        router._sessions.register_extension("session-a", FakeSocket(), "1.0.0")
        router._sessions.mark_command("session-a", "navigate")
        await router._handle_cli(cli_ws, {"method": "get_session_state", "session_id": "session-a"})

        result = cli_ws.sent_messages[0]["result"]
        assert result["session_id"] == "session-a"
        assert result["connected"] is True
        assert result["last_method"] == "navigate"
        assert result["connect_count"] == 1

    asyncio.run(scenario())


def test_router_rejects_invalid_token() -> None:
    async def scenario() -> None:
        router = BridgeRouter(token="secret")
        cli_ws = FakeSocket()
        await router._send_error(cli_ws, router_error("AUTH_FAILED", "Bridge 鉴权失败"))
        assert cli_ws.sent_messages == [{"error": "Bridge 鉴权失败", "error_code": "AUTH_FAILED"}]

    def router_error(code: str, message: str):
        from bridge.types import BridgeError

        return BridgeError(code, message)

    asyncio.run(scenario())
