"""State storage for active bridge sessions and pending requests."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from websockets.server import ServerConnection

from .models import SessionState


class SessionStore:
    """Keeps track of extension sessions and in-flight CLI requests."""

    def __init__(self) -> None:
        self._extensions: dict[str, ServerConnection] = {}
        self._pending: dict[str, tuple[str, asyncio.Future[Any]]] = {}
        self._session_meta: dict[str, SessionState] = {}

    def allocate_session_id(self, preferred: str = "") -> tuple[str, bool]:
        """Return an existing preferred session_id or allocate a new unique one."""
        candidate = preferred.strip()
        if candidate:
            return candidate, False

        if "default" not in self._extensions and "default" not in self._session_meta:
            return "default", True

        while True:
            candidate = f"session-{uuid.uuid4().hex[:12]}"
            if candidate not in self._extensions and candidate not in self._session_meta:
                return candidate, True

    def register_extension(
        self,
        session_id: str,
        ws: ServerConnection,
        extension_version: str = "",
    ) -> None:
        self._extensions[session_id] = ws
        state = self._session_meta.get(session_id) or SessionState(session_id=session_id)
        state.connected = True
        state.extension_version = extension_version
        state.last_seen = datetime.utcnow()
        state.connected_at = state.last_seen
        state.connect_count += 1
        state.last_error = ""
        self._session_meta[session_id] = state

    def unregister_extension(self, session_id: str, ws: ServerConnection) -> None:
        current = self._extensions.get(session_id)
        if current is ws:
            self._extensions.pop(session_id, None)

        state = self._session_meta.get(session_id) or SessionState(session_id=session_id)
        state.connected = False
        state.last_seen = datetime.utcnow()
        state.disconnected_at = state.last_seen
        state.disconnect_count += 1
        self._session_meta[session_id] = state

    def has_extension(self, session_id: str) -> bool:
        return session_id in self._extensions

    def has_any_extension(self) -> bool:
        return bool(self._extensions)

    def get_extension(self, session_id: str) -> ServerConnection | None:
        return self._extensions.get(session_id)

    def touch_session(self, session_id: str, heartbeat: bool = False) -> None:
        state = self._session_meta.get(session_id) or SessionState(session_id=session_id)
        state.last_seen = datetime.utcnow()
        if heartbeat:
            state.last_heartbeat_at = state.last_seen
        self._session_meta[session_id] = state

    def mark_command(self, session_id: str, method: str) -> None:
        state = self._session_meta.get(session_id) or SessionState(session_id=session_id)
        state.last_method = method
        state.last_command_at = datetime.utcnow()
        self._session_meta[session_id] = state

    def set_last_error(self, session_id: str, error: str) -> None:
        state = self._session_meta.get(session_id) or SessionState(session_id=session_id)
        state.last_error = error
        state.last_seen = datetime.utcnow()
        self._session_meta[session_id] = state

    def create_pending(
        self,
        request_id: str,
        session_id: str,
        loop: asyncio.AbstractEventLoop,
    ) -> asyncio.Future[Any]:
        future: asyncio.Future[Any] = loop.create_future()
        self._pending[request_id] = (session_id, future)
        return future

    def resolve_pending(self, request_id: str, payload: Any) -> None:
        pending = self._pending.pop(request_id, None)
        if not pending:
            return
        _session_id, future = pending
        if not future.done():
            future.set_result(payload)

    def drop_pending(self, request_id: str) -> None:
        self._pending.pop(request_id, None)

    def fail_session_requests(self, session_id: str, error: Exception) -> None:
        stale_ids = [
            request_id
            for request_id, (pending_session_id, _future) in self._pending.items()
            if pending_session_id == session_id
        ]
        for request_id in stale_ids:
            _pending_session_id, future = self._pending.pop(request_id)
            if not future.done():
                future.set_exception(error)

    def get_state(self, session_id: str) -> SessionState:
        return self._session_meta.get(session_id) or SessionState(session_id=session_id)

    def list_states(self) -> list[SessionState]:
        return list(self._session_meta.values())
