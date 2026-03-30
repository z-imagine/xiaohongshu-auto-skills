"""State storage for active bridge sessions and pending requests."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from websockets.server import ServerConnection

from .types import SessionState


class SessionStore:
    """Keeps track of extension sessions and in-flight CLI requests."""

    def __init__(self) -> None:
        self._extensions: dict[str, ServerConnection] = {}
        self._pending: dict[str, tuple[str, asyncio.Future[Any]]] = {}
        self._session_meta: dict[str, SessionState] = {}

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
        self._session_meta[session_id] = state

    def unregister_extension(self, session_id: str, ws: ServerConnection) -> None:
        current = self._extensions.get(session_id)
        if current is ws:
            self._extensions.pop(session_id, None)

        state = self._session_meta.get(session_id) or SessionState(session_id=session_id)
        state.connected = False
        state.last_seen = datetime.utcnow()
        self._session_meta[session_id] = state

    def has_extension(self, session_id: str) -> bool:
        return session_id in self._extensions

    def has_any_extension(self) -> bool:
        return bool(self._extensions)

    def get_extension(self, session_id: str) -> ServerConnection | None:
        return self._extensions.get(session_id)

    def touch_session(self, session_id: str) -> None:
        state = self._session_meta.get(session_id) or SessionState(session_id=session_id)
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

