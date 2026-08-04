"""用户主页，对应 Go xiaohongshu/user_profile.go。"""

from __future__ import annotations

import json
import logging
import time
from urllib.parse import parse_qs, urljoin, urlparse

from .cdp import Page
from .errors import NotLoggedInError
from .login import check_login_status
from .types import Feed, UserBasicInfo, UserInteraction, UserProfileResponse
from .urls import EXPLORE_URL, make_user_profile_url
from .selectors import USER_PROFILE_NAV_LINK

logger = logging.getLogger(__name__)

# 提取用户数据的 JS
_EXTRACT_USER_DATA_JS = """
(() => {
    if (window.__INITIAL_STATE__ &&
        window.__INITIAL_STATE__.user &&
        window.__INITIAL_STATE__.user.userPageData) {
        const userPageData = window.__INITIAL_STATE__.user.userPageData;
        const data = userPageData.value !== undefined ? userPageData.value : userPageData._value;
        if (data) {
            return JSON.stringify(data);
        }
    }
    return "";
})()
"""

_EXTRACT_USER_NOTES_JS = """
(() => {
    if (window.__INITIAL_STATE__ &&
        window.__INITIAL_STATE__.user &&
        window.__INITIAL_STATE__.user.notes) {
        const notes = window.__INITIAL_STATE__.user.notes;
        const data = notes.value !== undefined ? notes.value : notes._value;
        if (data) {
            return JSON.stringify(data);
        }
    }
    return "";
})()
"""


def get_user_profile(page: Page, user_id: str, xsec_token: str) -> UserProfileResponse:
    """获取用户主页信息及帖子。

    Args:
        page: CDP 页面对象。
        user_id: 用户 ID。
        xsec_token: xsec_token。

    Raises:
        RuntimeError: 数据提取失败。
    """
    url = make_user_profile_url(user_id, xsec_token)
    page.navigate(url)
    page.wait_for_load()
    page.wait_dom_stable()

    return _extract_user_profile_data(page)


def get_current_user_profile(page: Page) -> dict:
    """Return basic information for the account currently logged into XHS.

    The profile link in the signed-in navigation is the canonical source for the
    account id.  We deliberately do not expose the link's xsec token.
    """
    original_url = str(page.evaluate("location.href") or "")
    try:
        page.navigate(EXPLORE_URL)
        page.wait_for_load()
        if not check_login_status(page):
            raise NotLoggedInError()

        href = str(page.evaluate(
            f"document.querySelector({json.dumps(USER_PROFILE_NAV_LINK)})?.getAttribute('href') || ''"
        ) or "")
        profile_url, user_id, xsec_token = _parse_current_profile_href(href)
        if not user_id:
            raise RuntimeError("当前账号个人主页链接不可用")

        page.navigate(profile_url or make_user_profile_url(user_id, xsec_token))
        page.wait_for_load()
        page.wait_dom_stable()
        profile = _extract_user_profile_data(page)
        basic_info = profile.user_basic_info
        return {
            "userId": user_id,
            "nickname": basic_info.nickname,
            "redId": basic_info.red_id,
            "avatar": basic_info.images or basic_info.imageb,
            "description": basic_info.desc,
            "gender": basic_info.gender,
            "ipLocation": basic_info.ip_location,
            "profileUrl": f"https://www.xiaohongshu.com/user/profile/{user_id}",
            "interactions": [
                {"type": item.type, "name": item.name, "count": item.count}
                for item in profile.interactions
            ],
        }
    finally:
        try:
            current_url = str(page.evaluate("location.href") or "")
        except Exception:
            current_url = ""
        if original_url and original_url != current_url:
            try:
                page.navigate(original_url)
                page.wait_for_load()
            except Exception:
                logger.warning("恢复原页面失败", exc_info=True)


def _parse_current_profile_href(href: str) -> tuple[str, str, str]:
    """Parse the signed-in navigation profile URL without accepting other paths."""
    profile_url = urljoin("https://www.xiaohongshu.com", href)
    parsed = urlparse(profile_url)
    prefix = "/user/profile/"
    if parsed.netloc != "www.xiaohongshu.com" or not parsed.path.startswith(prefix):
        return "", "", ""
    user_id = parsed.path.removeprefix(prefix).split("/", 1)[0]
    xsec_token = parse_qs(parsed.query).get("xsec_token", [""])[0]
    return profile_url, user_id, xsec_token


def _extract_user_profile_data(page: Page) -> UserProfileResponse:
    """从页面提取用户资料数据。"""
    # 等待 __INITIAL_STATE__
    _wait_for_initial_state(page)

    # 提取用户信息
    user_data_result = page.evaluate(_EXTRACT_USER_DATA_JS)
    if not user_data_result:
        raise RuntimeError("user.userPageData.value not found in __INITIAL_STATE__")

    # 提取用户帖子
    notes_result = page.evaluate(_EXTRACT_USER_NOTES_JS)
    if not notes_result:
        raise RuntimeError("user.notes.value not found in __INITIAL_STATE__")

    # 解析用户信息
    user_page_data = json.loads(user_data_result)
    basic_info = UserBasicInfo.from_dict(user_page_data.get("basicInfo", {}))
    interactions = [UserInteraction.from_dict(i) for i in user_page_data.get("interactions", [])]

    # 解析帖子（双重数组，展平）
    notes_feeds_raw = json.loads(notes_result)
    feeds: list[Feed] = []
    for feed_group in notes_feeds_raw:
        if isinstance(feed_group, list):
            for f in feed_group:
                feeds.append(Feed.from_dict(f))
        elif isinstance(feed_group, dict):
            feeds.append(Feed.from_dict(feed_group))

    return UserProfileResponse(
        user_basic_info=basic_info,
        interactions=interactions,
        feeds=feeds,
    )


def _wait_for_initial_state(page: Page, timeout: float = 10.0) -> None:
    """等待 __INITIAL_STATE__ 就绪。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready = page.evaluate("window.__INITIAL_STATE__ !== undefined")
        if ready:
            return
        time.sleep(0.5)
    logger.warning("等待 __INITIAL_STATE__ 超时")
