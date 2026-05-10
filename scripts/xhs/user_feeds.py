"""用户主页 Feed 加载更多。"""

from __future__ import annotations

import json
import logging
import time

from .cdp import Page
from .types import Feed
from .urls import make_user_profile_url

logger = logging.getLogger(__name__)

_USER_FEEDS_STATE_JS = """
(() => {
    const state = window.__INITIAL_STATE__;
    const unwrap = (v) => {
        if (v && typeof v === "object" && "value" in v) return v.value;
        if (v && typeof v === "object" && "_value" in v) return v._value;
        return v;
    };
    const user = state && state.user;
    const notes = unwrap(user && user.notes);
    const queries = unwrap(user && user.noteQueries) || [];
    const fetching = unwrap(user && user.isFetchingNotes) || [];
    return JSON.stringify({
        notes: Array.isArray(notes) ? notes : [],
        query: queries[0] || {},
        isFetching: Boolean(fetching[0])
    });
})()
"""


def get_user_feeds(
    page: Page,
    user_id: str,
    xsec_token: str,
    load_more: bool = False,
) -> dict:
    """获取当前用户主页已加载 Feed，可选择触发一次加载更多。"""
    _ensure_user_profile_page(page, user_id, xsec_token)
    before_feeds, _before_query, _before_fetching = _read_user_feeds_state(page)
    before_keys = {_feed_key(feed) for feed in before_feeds}

    if load_more:
        _trigger_load_more_scroll(page)
        _wait_for_load_more(page, before_count=len(before_feeds))

    after_feeds, after_query, _after_fetching = _read_user_feeds_state(page)
    new_feeds = [feed for feed in after_feeds if _feed_key(feed) not in before_keys]

    result_feeds = new_feeds if load_more else after_feeds
    return {
        "feeds": [feed.to_dict() for feed in result_feeds],
        "count": len(result_feeds),
        "totalLoaded": len(after_feeds),
        "hasMore": bool(after_query.get("hasMore", False)),
    }


def _ensure_user_profile_page(page: Page, user_id: str, xsec_token: str) -> None:
    current_url = str(page.evaluate("location.href") or "")
    if f"/user/profile/{user_id}" not in current_url:
        page.navigate(make_user_profile_url(user_id, xsec_token))
        page.wait_for_load()
    page.wait_dom_stable()
    _wait_for_initial_state(page)


def _read_user_feeds_state(page: Page) -> tuple[list[Feed], dict, bool]:
    result = page.evaluate(_USER_FEEDS_STATE_JS)
    if not result:
        return [], {}, False

    state = json.loads(result)
    feeds: list[Feed] = []
    for group in state.get("notes", []):
        if isinstance(group, list):
            feeds.extend(Feed.from_dict(item) for item in group if isinstance(item, dict))
        elif isinstance(group, dict):
            feeds.append(Feed.from_dict(group))
    return feeds, state.get("query", {}) or {}, bool(state.get("isFetching", False))


def _wait_for_load_more(page: Page, before_count: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    saw_fetching = False
    while time.monotonic() < deadline:
        feeds, _query, is_fetching = _read_user_feeds_state(page)
        if is_fetching:
            saw_fetching = True
        if len(feeds) > before_count:
            return
        if saw_fetching and not is_fetching:
            return
        time.sleep(0.5)
    logger.warning("等待用户主页加载更多超时")


def _trigger_load_more_scroll(page: Page) -> None:
    """触发用户主页瀑布流加载更多。

    用户主页的笔记加载由 window 滚动到底部触发。每次加载完成后页面高度会
    增加，下一次再滚到新的底部即可触发下一批，不需要额外模拟 wheel 事件。
    """
    page.scroll_to_bottom()
    time.sleep(0.3)


def _wait_for_initial_state(page: Page, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready = page.evaluate(
            "Boolean(window.__INITIAL_STATE__ && window.__INITIAL_STATE__.user)"
        )
        if ready:
            return
        time.sleep(0.5)
    logger.warning("等待 user __INITIAL_STATE__ 超时")


def _feed_key(feed: Feed) -> str:
    if feed.id:
        return f"id:{feed.id}"
    if feed.note_card.note_id:
        return f"note:{feed.note_card.note_id}"
    if feed.xsec_token:
        return f"xsec:{feed.xsec_token}"
    return f"title:{feed.note_card.display_title}:{feed.index}"
