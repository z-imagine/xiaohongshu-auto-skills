"""WebSocket router for CLI requests and extension sessions."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import UTC
from typing import Any

from websockets.server import ServerConnection

from .auth import is_token_allowed
from .session_store import SessionStore
from .models import BridgeError

logger = logging.getLogger("xhs-bridge")


class BridgeRouter:
    """Routes CLI commands to the correct extension session."""

    def __init__(self, token: str = "") -> None:
        self._expected_token = token
        self._sessions = SessionStore()

    async def handle(self, ws: ServerConnection) -> None:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("握手超时或失败: %s", exc)
            return

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await self._send_error(ws, BridgeError("INVALID_JSON", "握手消息不是合法 JSON"))
            return

        if not self._is_authorized(msg):
            await self._send_error(ws, BridgeError("AUTH_FAILED", "Bridge 鉴权失败"))
            return

        role = msg.get("role")
        if role == "extension":
            await self._handle_extension(ws, msg)
            return
        if role == "cli":
            await self._handle_cli(ws, msg)
            return

        await self._send_error(ws, BridgeError("UNKNOWN_ROLE", f"未知 role: {role}"))

    def _is_authorized(self, msg: dict[str, Any]) -> bool:
        return is_token_allowed(self._expected_token, msg.get("token"))

    async def _handle_extension(self, ws: ServerConnection, msg: dict[str, Any]) -> None:
        session_id, assigned = self._sessions.allocate_session_id(str(msg.get("session_id") or ""))
        extension_version = str(msg.get("extension_version") or "")
        self._sessions.register_extension(session_id, ws, extension_version)
        await ws.send(json.dumps({
            "kind": "hello",
            "session_id": session_id,
            "assigned": assigned,
        }, ensure_ascii=False))
        logger.info("Extension 已连接: session=%s version=%s", session_id, extension_version or "-")

        try:
            async for raw in ws:
                try:
                    payload = json.loads(raw)
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
            self._sessions.unregister_extension(session_id, ws)
            self._sessions.fail_session_requests(session_id, ConnectionError("Extension 断开连接"))
            logger.info("Extension 已断开: session=%s", session_id)

    async def _handle_cli(self, ws: ServerConnection, msg: dict[str, Any]) -> None:
        method = msg.get("method")
        session_id = str(msg.get("session_id") or "").strip()

        if method == "ping_server":
            await ws.send(json.dumps({
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
            }))
            return

        if method == "get_session_state":
            if not session_id:
                await self._send_error(
                    ws,
                    BridgeError("MISSING_SESSION_ID", "CLI 请求缺少 session_id"),
                )
                return
            await ws.send(json.dumps({"result": self.get_session_snapshot(session_id)}, ensure_ascii=False))
            return

        if not session_id:
            await self._send_error(ws, BridgeError("MISSING_SESSION_ID", "CLI 请求缺少 session_id"))
            return

        extension_ws = self._sessions.get_extension(session_id)
        if not extension_ws:
            error = BridgeError("EXTENSION_NOT_CONNECTED", f"Extension 未连接: session={session_id}")
            self._sessions.set_last_error(session_id, error.message)
            await self._send_error(ws, error)
            return

        self._sessions.mark_command(session_id, str(method or ""))
        message_id = str(uuid.uuid4())
        msg["id"] = message_id
        loop = asyncio.get_running_loop()
        future = self._sessions.create_pending(message_id, session_id, loop)
        started = time.perf_counter()

        await extension_ws.send(json.dumps(msg, ensure_ascii=False))

        try:
            result = await asyncio.wait_for(future, timeout=90.0)
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.info(
                "Bridge command completed: session=%s method=%s duration_ms=%s",
                session_id,
                method,
                duration_ms,
            )
            await ws.send(json.dumps(result, ensure_ascii=False))
        except asyncio.TimeoutError:
            self._sessions.drop_pending(message_id)
            error = BridgeError("COMMAND_TIMEOUT", "命令执行超时（90s）")
            self._sessions.set_last_error(session_id, error.message)
            logger.warning("Bridge command timed out: session=%s method=%s", session_id, method)
            await self._send_error(ws, error)
        except ConnectionError as exc:
            error = BridgeError("EXTENSION_DISCONNECTED", str(exc))
            self._sessions.set_last_error(session_id, error.message)
            logger.warning("Bridge command failed: session=%s method=%s error=%s", session_id, method, exc)
            await self._send_error(ws, error)

    async def _send_error(self, ws: ServerConnection, error: BridgeError) -> None:
        await ws.send(json.dumps({
            "error": error.message,
            "error_code": error.code,
        }, ensure_ascii=False))

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
