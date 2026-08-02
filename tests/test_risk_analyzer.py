from __future__ import annotations

from xhs.risk_analyzer import analyze


def test_risk_analyzer_reports_safe_for_normal_entries() -> None:
    report = analyze([{"status": 200, "category": "business_api", "path": "/api/test"}])

    assert report["risk_level"] == "safe"
    assert report["total_requests"] == 1


def test_risk_analyzer_reports_medium_for_risk_redirect() -> None:
    report = analyze([{"status": 302, "category": "risk_redirect", "path": "/security/check"}])

    assert report["risk_level"] == "medium"
    assert report["high_risk_signals"] == ["风险跳转：/security/check"]


def test_risk_analyzer_ignores_root_redirect() -> None:
    report = analyze([{"status": 302, "category": "ignored_redirect", "path": "/"}])

    assert report["risk_level"] == "safe"
    assert report["high_risk_signals"] == []


def test_risk_analyzer_reports_high_for_http_999() -> None:
    report = analyze([{"status": 999, "category": "business_api", "path": "/api/note/create"}])

    assert report["risk_level"] == "high"


def test_risk_analyzer_reports_low_for_network_error() -> None:
    report = analyze([{"status": 0, "category": "other", "path": "/api/feed"}])

    assert report["risk_level"] == "low"
