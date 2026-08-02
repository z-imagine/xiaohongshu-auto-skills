"""对脱敏 NetLog 进行离线风险归纳。"""

from __future__ import annotations

from collections import Counter
from typing import Any

RISK_CODES = {401, 403, 429, 461, 999}


def analyze(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """根据网络元数据生成稳定、无副作用的风险摘要。"""
    category_distribution = Counter(str(entry.get("category", "other")) for entry in entries)
    high_signals: list[str] = []
    warnings: list[str] = []

    for entry in entries:
        status = entry.get("status")
        path = str(entry.get("path", ""))[:120]
        category = entry.get("category")
        if category == "risk_redirect":
            high_signals.append(f"风险跳转：{path}")
        elif status in RISK_CODES:
            high_signals.append(f"HTTP {status}：{path}")
        elif status == 0:
            warnings.append(f"网络请求失败：{path}")

    if any("HTTP 999" in signal for signal in high_signals):
        risk_level = "high"
    elif high_signals:
        risk_level = "medium"
    elif warnings:
        risk_level = "low"
    else:
        risk_level = "safe"

    return {
        "risk_level": risk_level,
        "total_requests": len(entries),
        "category_distribution": dict(category_distribution),
        "high_risk_signals": high_signals,
        "warnings": warnings,
        "summary": f"本会话采集 {len(entries)} 条脱敏网络记录。",
    }
