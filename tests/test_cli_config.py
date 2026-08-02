from __future__ import annotations

import argparse
import stat

import cli
import pytest
import xhs.bridge
import xhs.config
from xhs.config import BridgeConfig, load_bridge_config, save_bridge_config


def test_config_round_trip_uses_owner_only_permissions(tmp_path) -> None:
    path = tmp_path / "config" / "config.json"
    expected = BridgeConfig(
        bridge_url="wss://bridge.example/ws",
        bridge_token="secret-token",
        bridge_session_id="session-1",
    )

    saved_path = save_bridge_config(expected, path)

    assert saved_path == path
    assert load_bridge_config(path) == expected
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_resolve_bridge_settings_uses_complete_direct_values(monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_bridge_config", lambda: None, raising=False)
    args = argparse.Namespace(
        bridge_url="wss://direct.example/ws",
        bridge_token="direct-token",
        bridge_session_id="direct-session",
    )

    assert cli._resolve_bridge_settings(args) == (
        "wss://direct.example/ws",
        "direct-session",
        "direct-token",
    )
    assert args._bridge_settings_from_explicit_args is True


def test_resolve_bridge_settings_rejects_partial_direct_values() -> None:
    args = argparse.Namespace(
        bridge_url="wss://direct.example/ws",
        bridge_token=None,
        bridge_session_id=None,
    )

    with pytest.raises(SystemExit, match="必须同时提供"):
        cli._resolve_bridge_settings(args)


def test_config_commands_are_registered() -> None:
    parser = cli.build_parser()

    status = parser.parse_args(["config", "status"])
    assert status.func is cli.cmd_config_status

    saved = parser.parse_args(
        [
            "config",
            "set",
            "--bridge-url",
            "wss://bridge.example/ws",
            "--bridge-token",
            "secret-token",
            "--bridge-session-id",
            "session-1",
        ],
    )
    assert saved.func is cli.cmd_config_set


def test_bridge_readiness_does_not_start_local_services(monkeypatch: pytest.MonkeyPatch) -> None:
    class UnavailableBridgePage:
        def __init__(self, **_kwargs) -> None:
            pass

        def is_server_running(self) -> bool:
            return False

    monkeypatch.setattr(xhs.bridge, "BridgePage", UnavailableBridgePage)

    assert cli._ensure_bridge_ready("ws://localhost:9333/ws", "session-1", "token") is False


def test_explicit_bridge_settings_are_saved_after_readiness_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeBridgePage:
        def __init__(self, **_kwargs) -> None:
            pass

    saved: list[BridgeConfig] = []
    monkeypatch.setattr(cli, "_ensure_bridge_ready", lambda *_args: True)
    monkeypatch.setattr(xhs.bridge, "BridgePage", FakeBridgePage)
    monkeypatch.setattr(xhs.config, "save_bridge_config", saved.append)
    args = argparse.Namespace(
        bridge_url="wss://direct.example/ws",
        bridge_token="direct-token",
        bridge_session_id="direct-session",
    )

    cli._connect(args)

    assert saved == [
        BridgeConfig(
            bridge_url="wss://direct.example/ws",
            bridge_token="direct-token",
            bridge_session_id="direct-session",
        ),
    ]
