"""搜索小红书用户，复用网页搜索页自动化链路。"""

from __future__ import annotations

import json
import logging
import random
import time

from .cdp import Page
from .errors import NoUsersError
from .types import UserSearchResult
from .urls import make_search_url

logger = logging.getLogger(__name__)

USER_TAB_SELECTOR = "div#user.channel"

_EXTRACT_USERS_JS = """
(() => {
    const state = window.__INITIAL_STATE__;
    const unwrap = (v) => {
        if (v && typeof v === "object" && "value" in v) return v.value;
        if (v && typeof v === "object" && "_value" in v) return v._value;
        return v;
    };
    const users = unwrap(state && state.search && state.search.userLists);
    return users ? JSON.stringify(users) : "";
})()
"""

_USER_SEARCH_STATE_JS = """
(() => {
    const state = window.__INITIAL_STATE__;
    const unwrap = (v) => {
        if (v && typeof v === "object" && "value" in v) return v.value;
        if (v && typeof v === "object" && "_value" in v) return v._value;
        return v;
    };
    const search = state && state.search;
    const type = unwrap(search && search.currentSearchType);
    const users = unwrap(search && search.userLists);
    const context = unwrap(search && search.searchUserContext) || {};
    return {
        type,
        userCount: Array.isArray(users) ? users.length : -1,
        isFetching: Boolean(unwrap(search && search.isFetchingUserLists)),
        fetchStatus: String(unwrap(search && search.fetchUserListsStatus) || ""),
        contextKeyword: String(context.keyword || "")
    };
})()
"""


def search_users(page: Page, keyword: str) -> list[UserSearchResult]:
    """搜索用户/账号。

    该能力保持和 search_feeds 一致：打开小红书搜索页，通过浏览器切换到用户
    tab，再从页面 __INITIAL_STATE__ 读取前端已经拿到的结果。
    """
    page.navigate(make_search_url(keyword))
    page.wait_for_load()
    page.wait_dom_stable()
    _wait_for_initial_state(page)

    _click_element_center(page, USER_TAB_SELECTOR)
    _wait_for_user_search_ready(page, keyword)

    result = page.evaluate(_EXTRACT_USERS_JS)
    if not result:
        raise NoUsersError()

    users_data = json.loads(result)
    return [UserSearchResult.from_dict(u) for u in users_data]


def _wait_for_initial_state(page: Page, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready = page.evaluate("window.__INITIAL_STATE__ !== undefined")
        if ready:
            return
        time.sleep(0.5)
    logger.warning("等待 __INITIAL_STATE__ 超时")


def _wait_for_user_search_ready(page: Page, keyword: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    switched_at: float | None = None
    while time.monotonic() < deadline:
        state = page.evaluate(_USER_SEARCH_STATE_JS) or {}
        if state.get("type") != "user":
            time.sleep(0.5)
            continue

        if switched_at is None:
            switched_at = time.monotonic()

        user_count = int(state.get("userCount", -1))
        if user_count > 0:
            return

        fetch_status = str(state.get("fetchStatus") or "").lower()
        context_keyword = str(state.get("contextKeyword") or "")
        is_fetching = bool(state.get("isFetching", False))
        if (
            context_keyword == keyword
            and not is_fetching
            and fetch_status
            and fetch_status not in {"loading", "pending", "fetching"}
        ):
            return

        # 小红书 state 有时不更新 fetchStatus；切到用户 tab 后给网络请求留出时间。
        if switched_at and time.monotonic() - switched_at >= 3.0 and user_count == 0 and not is_fetching:
            return
        time.sleep(0.5)
    raise NoUsersError()


def _click_element_center(page: Page, selector: str) -> None:
    """按已有 CDP 点击思路，点击元素中心点，不改全局 click_element 行为。"""
    box = page.evaluate(
        f"""
        (() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return null;
            el.scrollIntoView({{block: "center"}});
            const rect = el.getBoundingClientRect();
            return {{x: rect.left + rect.width / 2, y: rect.top + rect.height / 2}};
        }})()
        """
    )
    if not box:
        raise NoUsersError()
    x = float(box["x"]) + random.uniform(-2, 2)
    y = float(box["y"]) + random.uniform(-2, 2)
    page.mouse_move(x, y)
    time.sleep(random.uniform(0.03, 0.08))
    page.mouse_click(x, y)
