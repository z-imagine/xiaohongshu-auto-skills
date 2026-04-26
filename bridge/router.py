"""Bridge router shared by WebSocket and HTTP transports."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import UTC
from typing import Any

from aiohttp import WSMsgType, web

from .auth import is_token_allowed
from .session_store import SessionStore
from .models import BridgeError

logger = logging.getLogger("xhs-bridge")


class ExtensionSocketAdapter:
    """Expose a minimal send(raw) interface on top of aiohttp WebSocket."""

    def __init__(self, ws: web.WebSocketResponse) -> None:
        self._ws = ws

    async def send(self, raw: str) -> None:
        await self._ws.send_str(raw)


class BridgeRouter:
    """Routes CLI commands to the correct extension session."""

    def __init__(self, token: str = "") -> None:
        self._expected_token = token
        self._sessions = SessionStore()

    async def handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(max_msg_size=50 * 1024 * 1024)
        await ws.prepare(request)

        try:
            first = await asyncio.wait_for(ws.receive(), timeout=10)
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("握手超时或失败: %s", exc)
            await ws.close()
            return ws

        if first.type != WSMsgType.TEXT:
            await self._send_error_ws(ws, BridgeError("INVALID_JSON", "握手消息不是合法 JSON"))
            await ws.close()
            return ws

        try:
            msg = json.loads(first.data)
        except json.JSONDecodeError:
            await self._send_error_ws(ws, BridgeError("INVALID_JSON", "握手消息不是合法 JSON"))
            await ws.close()
            return ws

        if not self._is_authorized(msg):
            await self._send_error_ws(ws, BridgeError("AUTH_FAILED", "Bridge 鉴权失败"))
            await ws.close()
            return ws

        role = msg.get("role")
        if role == "extension":
            await self._handle_extension(ws, msg)
            return ws
        if role == "cli":
            await self._handle_cli_ws(ws, msg)
            await ws.close()
            return ws

        await self._send_error_ws(ws, BridgeError("UNKNOWN_ROLE", f"未知 role: {role}"))
        await ws.close()
        return ws

    def _is_authorized(self, msg: dict[str, Any]) -> bool:
        return is_token_allowed(self._expected_token, msg.get("token"))

    async def _handle_extension(self, ws: web.WebSocketResponse, msg: dict[str, Any]) -> None:
        session_id, assigned = self._sessions.allocate_session_id(str(msg.get("session_id") or ""))
        extension_version = str(msg.get("extension_version") or "")
        adapter = ExtensionSocketAdapter(ws)
        self._sessions.register_extension(session_id, adapter, extension_version)
        await ws.send_str(json.dumps({
            "kind": "hello",
            "session_id": session_id,
            "assigned": assigned,
        }, ensure_ascii=False))
        logger.info("Extension 已连接: session=%s version=%s", session_id, extension_version or "-")

        try:
            async for message in ws:
                if message.type != WSMsgType.TEXT:
                    if message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
                        break
                    continue
                try:
                    payload = json.loads(message.data)
                except json.JSONDecodeError:
                    continue

                if payload.get("kind") == "heartbeat":
                    self._sessions.touch_session(session_id, heartbeat=True)
                    continue

                self._sessions.touch_session(session_id)
                message_id = payload.get("id")
                if message_id:
                    self._sessions.resolve_pending(message_id, payload)
        finally:
            self._sessions.unregister_extension(session_id, adapter)
            self._sessions.fail_session_requests(session_id, ConnectionError("Extension 断开连接"))
            logger.info("Extension 已断开: session=%s", session_id)

    async def _handle_cli_ws(self, ws: web.WebSocketResponse, msg: dict[str, Any]) -> None:
        try:
            result = await self.execute_cli_rpc(msg)
            await ws.send_str(json.dumps(result, ensure_ascii=False))
        except BridgeError as error:
            await self._send_error_ws(ws, error)

    async def _handle_cli(self, ws: Any, msg: dict[str, Any]) -> None:
        """Backward-compatible helper retained for tests and internal reuse."""
        try:
            result = await self.execute_cli_rpc(msg)
            await ws.send(json.dumps(result, ensure_ascii=False))
        except BridgeError as error:
            await self._send_error(ws, error)

    async def execute_cli_rpc(self, msg: dict[str, Any]) -> dict[str, Any]:
        method = msg.get("method")
        session_id = str(msg.get("session_id") or "").strip()

        if method == "ping_server":
            return {
                "result": {
                    "server_running": True,
                    "session_id": session_id or None,
                    "extension_connected": (
                        self._sessions.has_extension(session_id)
                        if session_id
                        else self._sessions.has_any_extension()
                    ),
                    "session": self.get_session_snapshot(session_id) if session_id else None,
                    "active_sessions": len(
                        [state for state in self._sessions.list_states() if state.connected]
                    ),
                }
            }

        if method == "get_session_state":
            if not session_id:
                raise BridgeError("MISSING_SESSION_ID", "CLI 请求缺少 session_id")
            return {"result": self.get_session_snapshot(session_id)}

        if not session_id:
            raise BridgeError("MISSING_SESSION_ID", "CLI 请求缺少 session_id")

        extension_ws = self._sessions.get_extension(session_id)
        if not extension_ws:
            error = BridgeError("EXTENSION_NOT_CONNECTED", f"Extension 未连接: session={session_id}")
            self._sessions.set_last_error(session_id, error.message)
            raise error

        self._sessions.mark_command(session_id, str(method or ""))
        message_id = str(uuid.uuid4())
        outbound = dict(msg)
        outbound["id"] = message_id
        loop = asyncio.get_running_loop()
        future = self._sessions.create_pending(message_id, session_id, loop)
        started = time.perf_counter()

        await extension_ws.send(json.dumps(outbound, ensure_ascii=False))

        try:
            result = await asyncio.wait_for(future, timeout=90.0)
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.info(
                "Bridge command completed: session=%s method=%s duration_ms=%s",
                session_id,
                method,
                duration_ms,
            )
            return result
        except asyncio.TimeoutError:
            self._sessions.drop_pending(message_id)
            error = BridgeError("COMMAND_TIMEOUT", "命令执行超时（90s）")
            self._sessions.set_last_error(session_id, error.message)
            logger.warning("Bridge command timed out: session=%s method=%s", session_id, method)
            raise error
        except ConnectionError as exc:
            error = BridgeError("EXTENSION_DISCONNECTED", str(exc))
            self._sessions.set_last_error(session_id, error.message)
            logger.warning("Bridge command failed: session=%s method=%s error=%s", session_id, method, exc)
            raise error

    async def _send_error_ws(self, ws: web.WebSocketResponse, error: BridgeError) -> None:
        await ws.send_str(json.dumps(self.error_payload(error), ensure_ascii=False))

    async def _send_error(self, ws: Any, error: BridgeError) -> None:
        await ws.send(json.dumps(self.error_payload(error), ensure_ascii=False))

    def error_payload(self, error: BridgeError) -> dict[str, str]:
        return {
            "error": error.message,
            "error_code": error.code,
        }

    def error_status_code(self, error: BridgeError) -> int:
        mapping = {
            "INVALID_JSON": 400,
            "UNKNOWN_ROLE": 400,
            "MISSING_SESSION_ID": 400,
            "AUTH_FAILED": 401,
            "EXTENSION_NOT_CONNECTED": 409,
            "EXTENSION_DISCONNECTED": 409,
            "COMMAND_TIMEOUT": 504,
        }
        return mapping.get(error.code, 500)

    def active_sessions_count(self) -> int:
        return len([state for state in self._sessions.list_states() if state.connected])

    def get_session_snapshot(self, session_id: str) -> dict[str, Any]:
        state = self._sessions.get_state(session_id)
        return {
            "session_id": state.session_id,
            "connected": state.connected,
            "extension_version": state.extension_version,
            "last_seen": state.last_seen.replace(tzinfo=UTC).isoformat(),
            "last_heartbeat_at": (
                state.last_heartbeat_at.replace(tzinfo=UTC).isoformat()
                if state.last_heartbeat_at
                else None
            ),
            "connected_at": (
                state.connected_at.replace(tzinfo=UTC).isoformat()
                if state.connected_at
                else None
            ),
            "disconnected_at": (
                state.disconnected_at.replace(tzinfo=UTC).isoformat()
                if state.disconnected_at
                else None
            ),
            "connect_count": state.connect_count,
            "disconnect_count": state.disconnect_count,
            "last_command_at": (
                state.last_command_at.replace(tzinfo=UTC).isoformat()
                if state.last_command_at
                else None
            ),
            "last_method": state.last_method,
            "last_error": state.last_error,
        }
