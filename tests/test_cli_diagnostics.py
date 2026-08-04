from __future__ import annotations

import argparse
import base64
import json

import cli
import pytest

PNG_HEADER = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    + (2).to_bytes(4, "big")
    + (3).to_bytes(4, "big")
)


def test_save_screenshot_writes_png_and_metadata(tmp_path) -> None:
    output = tmp_path / "screen.png"
    result = cli._save_screenshot(
        {
            "data": base64.b64encode(PNG_HEADER).decode(),
            "mime_type": "image/png",
            "captured_at": "2026-08-04T12:00:00Z",
            "url": "https://www.xiaohongshu.com/explore",
        },
        str(output),
    )

    assert output.read_bytes() == PNG_HEADER
    assert result == {
        "path": str(output),
        "mime_type": "image/png",
        "width": 2,
        "height": 3,
        "captured_at": "2026-08-04T12:00:00Z",
        "url": "https://www.xiaohongshu.com/explore",
    }


def test_save_screenshot_requires_absolute_output(tmp_path) -> None:
    with pytest.raises(ValueError, match="绝对路径"):
        cli._save_screenshot({"data": base64.b64encode(PNG_HEADER).decode()}, "screen.png")


def test_diagnose_returns_partial_results_when_page_checks_fail(
    monkeypatch, tmp_path, capsys
) -> None:
    class FakePage:
        def get_session_state(self):
            return {"connected": False, "last_error": "extension disconnected"}

        def get_page_state(self):
            raise RuntimeError("Bridge 错误[EXTENSION_NOT_CONNECTED]: extension offline")

        def screenshot(self):
            raise RuntimeError("Bridge 错误[EXTENSION_NOT_CONNECTED]: extension offline")

    monkeypatch.setattr(cli, "_diagnostic_page", lambda _args: FakePage())
    args = argparse.Namespace(screenshot=True, output=str(tmp_path / "screen.png"))

    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_diagnose(args)

    assert exc_info.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["bridge"] == {
        "ok": True,
        "state": {"connected": False, "last_error": "extension disconnected"},
    }
    assert payload["page"]["ok"] is False
    assert payload["screenshot"]["ok"] is False


def test_screenshot_returns_structured_failure(monkeypatch, capsys) -> None:
    class FakeBrowser:
        def close(self) -> None:
            pass

    class FakePage:
        def screenshot(self):
            raise RuntimeError("CDP attach failed")

    monkeypatch.setattr(cli, "_connect_existing", lambda _args: (FakeBrowser(), FakePage()))

    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_screenshot(argparse.Namespace(output=None))

    assert exc_info.value.code == 2
    assert json.loads(capsys.readouterr().out) == {
        "success": False,
        "error_code": "SCREENSHOT_FAILED",
        "error": "CDP attach failed",
    }


def test_diagnostic_commands_are_registered() -> None:
    parser = cli.build_parser()

    assert parser.parse_args(["screenshot"]).func is cli.cmd_screenshot
    assert parser.parse_args(["inspect-page"]).func is cli.cmd_inspect_page
    assert parser.parse_args(["bridge-status"]).func is cli.cmd_bridge_status
    diagnose = parser.parse_args(["diagnose", "--screenshot", "--output", "/tmp/screen.png"])
    assert diagnose.func is cli.cmd_diagnose
    assert diagnose.screenshot is True
    assert diagnose.output == "/tmp/screen.png"
