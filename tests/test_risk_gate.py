from __future__ import annotations

import pytest
from xhs.errors import RiskSignalDetectedError
from xhs.risk_gate import NetlogRiskGate


class FakePage:
    def __init__(self, enabled: bool, entries: list[dict]) -> None:
        self.enabled = enabled
        self.entries = entries

    def get_netlog_state(self) -> dict:
        return {"enabled": self.enabled}

    def get_netlog(self) -> list[dict]:
        return list(self.entries)


def test_gate_is_inactive_when_netlogger_is_disabled() -> None:
    gate = NetlogRiskGate.start(FakePage(False, []))

    assert gate.enabled is False
    gate.check_after()


def test_gate_blocks_before_operation_for_existing_high_risk_signal() -> None:
    page = FakePage(True, [{"status": 999, "category": "business_api", "path": "/api/note"}])

    with pytest.raises(RiskSignalDetectedError, match="已停止自动化"):
        NetlogRiskGate.start(page)


def test_gate_blocks_only_on_new_high_risk_signal_after_operation() -> None:
    page = FakePage(True, [{"status": 200, "category": "business_api", "path": "/api/feed"}])
    gate = NetlogRiskGate.start(page)
    page.entries.append({"status": 403, "category": "business_api", "path": "/api/note/create"})

    with pytest.raises(RiskSignalDetectedError, match="HTTP 403"):
        gate.check_after()


def test_gate_allows_low_risk_network_failure() -> None:
    page = FakePage(True, [])
    gate = NetlogRiskGate.start(page)
    page.entries.append({"status": 0, "category": "other", "path": "/api/feed"})

    gate.check_after()
