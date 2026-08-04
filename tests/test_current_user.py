from __future__ import annotations

import cli
from bridge.router import BridgeRouter
from bridge.server import create_app
from xhs.types import UserBasicInfo, UserInteraction, UserProfileResponse
from xhs.user_feeds import get_user_feeds
from xhs.user_profile import _parse_current_profile_href, get_current_user_profile


def test_parse_current_profile_href_extracts_account_identity() -> None:
    profile_url, user_id, xsec_token = _parse_current_profile_href(
        "/user/profile/abc-123?xsec_token=token-value&xsec_source=pc_note"
    )

    assert profile_url == (
        "https://www.xiaohongshu.com/user/profile/abc-123?"
        "xsec_token=token-value&xsec_source=pc_note"
    )
    assert user_id == "abc-123"
    assert xsec_token == "token-value"


def test_parse_current_profile_href_rejects_non_profile_url() -> None:
    assert _parse_current_profile_href("https://example.com/user/profile/abc") == ("", "", "")


def test_current_user_returns_basic_info_and_restores_page(monkeypatch) -> None:
    class FakePage:
        current_url = "https://www.xiaohongshu.com/explore/original-note"

        def evaluate(self, script: str):
            if script == "location.href":
                return self.current_url
            return "/user/profile/account-1?xsec_token=secret-token"

        def navigate(self, url: str) -> None:
            self.current_url = url

        def wait_for_load(self) -> None:
            pass

        def wait_dom_stable(self) -> None:
            pass

    profile = UserProfileResponse(
        user_basic_info=UserBasicInfo(
            nickname="测试账号",
            red_id="red-1",
            images="https://image.example/avatar.png",
            desc="简介",
            gender=1,
            ip_location="上海",
        ),
        interactions=[UserInteraction(type="fans", name="粉丝", count="9")],
    )
    monkeypatch.setattr("xhs.user_profile.check_login_status", lambda _page: True)
    monkeypatch.setattr("xhs.user_profile._extract_user_profile_data", lambda _page: profile)
    page = FakePage()

    result = get_current_user_profile(page)

    assert result == {
        "userId": "account-1",
        "nickname": "测试账号",
        "redId": "red-1",
        "avatar": "https://image.example/avatar.png",
        "description": "简介",
        "gender": 1,
        "ipLocation": "上海",
        "profileUrl": "https://www.xiaohongshu.com/user/profile/account-1",
        "interactions": [{"type": "fans", "name": "粉丝", "count": "9"}],
    }
    assert page.current_url == "https://www.xiaohongshu.com/explore/original-note"


def test_user_feeds_default_is_first_page(monkeypatch) -> None:
    class FakeFeed:
        id = "note-1"

        def to_dict(self) -> dict:
            return {"id": "note-1"}

    monkeypatch.setattr("xhs.user_feeds._ensure_user_profile_page", lambda *_args: None)
    monkeypatch.setattr(
        "xhs.user_feeds._read_user_feeds_state",
        lambda _page: ([FakeFeed()], {"hasMore": True}, False),
    )

    result = get_user_feeds(object(), "user-1", "xsec-token")

    assert result == {
        "userId": "user-1",
        "page": 1,
        "notes": [{"id": "note-1"}],
        "count": 1,
        "hasMore": True,
    }


def test_current_user_command_is_registered() -> None:
    assert cli.build_parser().parse_args(["current-user"]).func is cli.cmd_current_user


def test_current_user_http_route_is_registered() -> None:
    app = create_app(BridgeRouter(token=""))
    paths = {resource.canonical for resource in app.router.resources()}

    assert "/xhs/current-user" in paths
