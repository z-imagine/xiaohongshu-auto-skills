from __future__ import annotations

import json

import pytest
from xhs import like_favorite
from xhs.selectors import COLLECT_BUTTON


def _detail(*, liked: bool = False, collected: bool = False) -> dict:
    return {"note": {"interactInfo": {"liked": liked, "collected": collected}}}


class FakePage:
    def __init__(self, states: list[dict], *, has_collect_button: bool = True) -> None:
        self._states = iter(states)
        self.has_collect_button = has_collect_button
        self.clicks: list[str] = []

    def evaluate(self, _script: str) -> str:
        return json.dumps(next(self._states))

    def has_element(self, selector: str) -> bool:
        assert selector == COLLECT_BUTTON
        return self.has_collect_button

    def click_element(self, selector: str) -> None:
        assert selector == COLLECT_BUTTON
        self.clicks.append(selector)


def test_get_interact_state_uses_single_detail_when_feed_key_changes() -> None:
    page = FakePage([{"redirected-feed": _detail(liked=True, collected=True)}])

    assert like_favorite._get_interact_state(page, "requested-feed") == (True, True)


def test_favorite_skips_click_when_state_already_matches() -> None:
    page = FakePage([{"feed-1": _detail(collected=True)}])

    result = like_favorite._toggle_favorite(page, "feed-1", target_collected=True)

    assert result.success is True
    assert result.message == "已收藏"
    assert page.clicks == []


def test_favorite_fails_when_collect_button_is_missing() -> None:
    page = FakePage([{"feed-1": _detail(collected=False)}], has_collect_button=False)

    result = like_favorite._toggle_favorite(page, "feed-1", target_collected=True)

    assert result.success is False
    assert result.message == "收藏失败：未找到收藏按钮"
    assert page.clicks == []


def test_favorite_retries_only_when_first_click_is_not_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = FakePage([{"feed-1": _detail(collected=False)}])
    confirmations = iter([False, True])
    monkeypatch.setattr(like_favorite, "_wait_collected_state", lambda *_args: next(confirmations))

    result = like_favorite._toggle_favorite(page, "feed-1", target_collected=True)

    assert result.success is True
    assert result.message == "收藏成功"
    assert page.clicks == [COLLECT_BUTTON, COLLECT_BUTTON]


def test_favorite_reports_failure_when_state_never_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    page = FakePage([{"feed-1": _detail(collected=False)}])
    monkeypatch.setattr(like_favorite, "_wait_collected_state", lambda *_args: False)

    result = like_favorite._toggle_favorite(page, "feed-1", target_collected=True)

    assert result.success is False
    assert result.message == "收藏失败：状态未变化"
    assert page.clicks == [COLLECT_BUTTON, COLLECT_BUTTON]
