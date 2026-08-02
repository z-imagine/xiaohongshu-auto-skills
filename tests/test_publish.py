from __future__ import annotations

import pytest
from xhs import publish
from xhs.errors import AccountRiskControlError, PublishError


class FakePublishPage:
    def __init__(self, *, fire_result: str = "fired", publish_result: dict | None = None) -> None:
        self.fire_result = fire_result
        self.publish_result = publish_result or {"code": 0, "msg": "ok"}
        self.calls: list[str] = []

    def evaluate(self, expression: str):
        self.calls.append(expression)
        if "MutationObserver" in expression:
            return None
        if "xhs-publish-btn" in expression:
            return self.fire_result
        if expression == "window.__xhsPublishResult":
            return self.publish_result
        if expression == "window.__xhsClearPublishCapture?.()":
            return None
        raise AssertionError(f"unexpected expression: {expression[:80]}")


def test_click_publish_button_confirms_success_and_cleans_capture() -> None:
    page = FakePublishPage(publish_result={"source": "xhr", "code": 0, "msg": "ok"})

    publish.click_publish_button(page)

    assert page.calls[-1] == "window.__xhsClearPublishCapture?.()"


def test_click_publish_button_cleans_capture_after_business_failure() -> None:
    page = FakePublishPage(publish_result={"source": "xhr", "code": 123, "msg": "invalid"})

    with pytest.raises(PublishError, match="code=123"):
        publish.click_publish_button(page)

    assert page.calls[-1] == "window.__xhsClearPublishCapture?.()"


def test_click_publish_button_rejects_disabled_component() -> None:
    page = FakePublishPage(fire_result="disabled")

    with pytest.raises(PublishError, match="不可用"):
        publish.click_publish_button(page)

    assert page.calls[-1] == "window.__xhsClearPublishCapture?.()"


@pytest.mark.parametrize(
    ("result", "expected_code"),
    [
        ({"code": -9136, "msg": "因违反社区规范禁止发笔记"}, -9136),
        ({"code": 999, "msg": "账号违规，请稍后再试"}, 999),
    ],
)
def test_publish_result_identifies_risk_control(result: dict, expected_code: int) -> None:
    with pytest.raises(AccountRiskControlError) as exc_info:
        publish._raise_for_publish_result(result)

    assert exc_info.value.code == expected_code


def test_wait_for_active_publish_tab_matches_target_immediately() -> None:
    class ActiveTabPage:
        def evaluate(self, _expression: str) -> str:
            return "上传图文"

    assert publish._wait_for_active_publish_tab(ActiveTabPage(), "上传图文") is True
