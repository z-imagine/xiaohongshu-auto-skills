from __future__ import annotations

import cli


def test_netlog_commands_are_registered() -> None:
    parser = cli.build_parser()

    assert parser.parse_args(["enable-netlog"]).enabled is True
    assert parser.parse_args(["disable-netlog"]).enabled is False
    assert parser.parse_args(["get-netlog", "--limit", "3"]).limit == 3
    assert parser.parse_args(["risk-report"]).command == "risk-report"
    assert parser.parse_args(["clear-netlog"]).command == "clear-netlog"
