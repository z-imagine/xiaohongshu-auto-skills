"""将已启用的 NetLogger 风险摘要接入自动化操作。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .errors import CDPError, RiskSignalDetectedError
from .risk_analyzer import analyze

logger = logging.getLogger(__name__)
_BLOCKING_LEVELS = {"medium", "high"}


@dataclass
class NetlogRiskGate:
    """记录操作开始位置，只对本次操作新产生的风险事件做后置判定。"""

    page: Any
    baseline_count: int
    enabled: bool

    @classmethod
    def start(cls, page: Any) -> NetlogRiskGate:
        if not hasattr(page, "get_netlog_state") or not hasattr(page, "get_netlog"):
            return cls(page=page, baseline_count=0, enabled=False)
        try:
            state = page.get_netlog_state()
            if not state.get("enabled"):
                return cls(page=page, baseline_count=0, enabled=False)
            entries = page.get_netlog()
        except CDPError:
            logger.warning("NetLogger 不可用，跳过风险门禁")
            return cls(page=page, baseline_count=0, enabled=False)

        report = analyze(entries)
        if report["risk_level"] in _BLOCKING_LEVELS:
            raise RiskSignalDetectedError(report)
        return cls(page=page, baseline_count=len(entries), enabled=True)

    def check_after(self) -> None:
        """检查操作期间新增的记录；低风险仅保留给报告，不阻断。"""
        if not self.enabled:
            return
        entries = self.page.get_netlog()
        if len(entries) >= self.baseline_count:
            new_entries = entries[self.baseline_count :]
        else:
            new_entries = entries
        report = analyze(new_entries)
        if report["risk_level"] in _BLOCKING_LEVELS:
            raise RiskSignalDetectedError(report)
