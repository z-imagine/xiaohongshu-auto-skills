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

