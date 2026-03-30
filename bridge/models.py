"""Shared bridge server types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class SessionState:
    """Tracks a bridge session and its active extension connection."""

    session_id: str
    connected: bool = False
    extension_version: str = ""
    last_seen: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat_at: datetime | None = None
    connected_at: datetime | None = None
    disconnected_at: datetime | None = None
    connect_count: int = 0
    disconnect_count: int = 0
    last_command_at: datetime | None = None
    last_method: str = ""
    last_error: str = ""


@dataclass(slots=True)
class BridgeError:
    """Structured bridge error used across router responses."""

    code: str
    message: str
