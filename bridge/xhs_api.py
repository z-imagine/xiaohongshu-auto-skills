"""HTTP business API for Xiaohongshu workflows."""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import json
import sys
from pathlib import Path
from typing import Any, Callable

from aiohttp import web

from .models import BridgeError
from .router import BridgeRouter

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from media_assets import prepare_image_assets, prepare_video_asset  # noqa: E402
from xhs.bridge import BridgePage  # noqa: E402
from xhs.comment import post_comment, reply_comment  # noqa: E402
from xhs.feed_detail import get_feed_detail  # noqa: E402
from xhs.feeds import list_feeds  # noqa: E402
from xhs.like_favorite import favorite_feed, like_feed, unfavorite_feed, unlike_feed  # noqa: E402
from xhs.login import (  # noqa: E402
    fetch_qrcode,
    logout,
    make_qrcode_url,
    send_phone_code,
    submit_phone_code,
    wait_for_login,
)
from xhs.publish import (  # noqa: E402
    click_publish_button,
    fill_publish_form,
    publish_image_content,
    save_as_draft,
)
from xhs.publish_long_article import (  # noqa: E402
    click_next_and_fill_description,
    publish_long_article,
    select_template,
)
from xhs.publish_video import fill_publish_video_form, publish_video_content  # noqa: E402
from xhs.search import search_feeds  # noqa: E402
from xhs.types import CommentLoadConfig, FilterOption, PublishImageContent, PublishVideoContent  # noqa: E402
from xhs.user_feeds import get_user_feeds  # noqa: E402
from xhs.user_search import search_users  # noqa: E402
from xhs.user_profile import get_user_profile  # noqa: E402


def _json_response(data: dict[str, Any], *, status: int = 200) -> web.Response:
    return web.json_response(data, status=status, dumps=lambda obj: json.dumps(obj, ensure_ascii=False))


class InProcessBridgePage(BridgePage):
    """BridgePage-compatible adapter that reuses the in-process router."""

    def __init__(self, router: BridgeRouter, session_id: str, token: str, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__(bridge_url="inproc://bridge", session_id=session_id, token=token)
        self._router = router
        self._loop = loop

    def _call(self, method: str, params: dict | None = None) -> Any:
        message: dict[str, Any] = {
            "role": "cli",
            "method": method,
            "session_id": self._session_id,
            "token": self._token,
        }
        if params:
            message["params"] = params
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._router.execute_cli_rpc(message),
                self._loop,
            )
            response = future.result(timeout=92)
        except BridgeError as exc:
            raise RuntimeError(f"Bridge 错误[{exc.code}]: {exc.message}") from exc
        except concurrent.futures.TimeoutError as exc:
            raise RuntimeError("Bridge 错误[COMMAND_TIMEOUT]: 命令执行超时（92s）") from exc
        except OSError as exc:
            raise RuntimeError(f"无法连接到 bridge server: {exc}") from exc
        return response.get("result")


def register_xhs_routes(app: web.Application, router: BridgeRouter) -> None:
    """Register Xiaohongshu business HTTP routes."""

    async def _read_body(request: web.Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception as exc:
            raise BridgeError("INVALID_JSON", "请求体不是合法 JSON") from exc
        if not isinstance(body, dict):
            raise BridgeError("INVALID_JSON", "请求体必须是 JSON 对象")
        return body

    def _require_str(body: dict[str, Any], field: str) -> str:
        value = str(body.get(field) or "").strip()
        if not value:
            raise BridgeError("INVALID_ARGUMENT", f"缺少必填字段: {field}")
        return value

    def _optional_list(body: dict[str, Any], field: str) -> list[str]:
        value = body.get(field) or []
        if not isinstance(value, list):
            raise BridgeError("INVALID_ARGUMENT", f"字段 {field} 必须是数组")
        return [str(item) for item in value if str(item).strip()]

    def _classify_business_error(exc: Exception, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        """将业务异常分类为结构化响应和 HTTP 状态码。"""
        from xhs.errors import NoFeedDetailError, NotLoggedInError, PageNotAccessibleError

        if isinstance(exc, PageNotAccessibleError):
            payload: dict[str, Any] = {
                "error": str(exc),
                "error_code": "PAGE_NOT_ACCESSIBLE",
                "xhs_error_code": exc.error_code,
                "xhs_url": exc.url,
            }
            # 把请求上下文也带回去，方便调用方排查
            for key in ("feed_id", "xsec_token", "user_id", "keyword"):
                if key in body:
                    payload[key] = body[key]
            return payload, 404

        if isinstance(exc, NoFeedDetailError):
            payload = {
                "error": "笔记不存在或已被删除",
                "error_code": "FEED_NOT_FOUND",
            }
            for key in ("feed_id", "xsec_token"):
                if key in body:
                    payload[key] = body[key]
            return payload, 404

        if isinstance(exc, NotLoggedInError):
            return {"error": str(exc), "error_code": "NOT_LOGGED_IN"}, 401

        # 兜底：未知业务异常
        return {"error": str(exc), "error_code": "BUSINESS_ERROR"}, 500

    async def _run_business(
        request: web.Request,
        handler: Callable[[InProcessBridgePage, dict[str, Any]], dict[str, Any]],
    ) -> web.Response:
        body: dict[str, Any] = {}
        try:
            body = await _read_body(request)
            if not router._is_authorized(body):
                error = BridgeError("AUTH_FAILED", "Bridge 鉴权失败")
                return _json_response(router.error_payload(error), status=router.error_status_code(error))

            session_id = _require_str(body, "session_id")
            token = str(body.get("token") or "")
            loop = asyncio.get_running_loop()
            page = InProcessBridgePage(router, session_id, token, loop)
            result = await asyncio.to_thread(handler, page, body)
            return _json_response(result)
        except BridgeError as exc:
            return _json_response(router.error_payload(exc), status=router.error_status_code(exc))
        except Exception as exc:
            # 记录包含请求上下文的详细错误日志
            logger.error(
                "业务处理失败: exc=%s, session_id=%s, method=%s, body=%s",
                exc,
                body.get("session_id", "-"),
                body.get("method", "-"),
                {k: v for k, v in body.items() if k not in ("token",)},
                exc_info=True,
            )
            payload, status = _classify_business_error(exc, body)
            return _json_response(payload, status=status)

    def handle_check_login(page: InProcessBridgePage, _body: dict[str, Any]) -> dict[str, Any]:
        png_bytes, _b64_orig, already = fetch_qrcode(page)
        if already:
            return {"logged_in": True}
        image_url, login_url = make_qrcode_url(png_bytes)
        result: dict[str, Any] = {
            "logged_in": False,
            "login_method": "qrcode",
            "qrcode_image_url": image_url,
            "qrcode_base64": base64.b64encode(png_bytes).decode(),
            "hint": "未登录，请扫码后调用 /xhs/wait-login",
        }
        if login_url:
            result["qr_login_url"] = login_url
        return result

    def handle_login(page: InProcessBridgePage, _body: dict[str, Any]) -> dict[str, Any]:
        png_bytes, _b64_orig, already = fetch_qrcode(page)
        if already:
            return {"logged_in": True, "message": "已登录"}
        image_url, login_url = make_qrcode_url(png_bytes)
        success = wait_for_login(page, timeout=120)
        result: dict[str, Any] = {
            "logged_in": success,
            "qrcode_image_url": image_url,
            "qrcode_base64": base64.b64encode(png_bytes).decode(),
            "message": "登录成功" if success else "等待超时",
        }
        if login_url:
            result["qr_login_url"] = login_url
        return result

    def handle_get_qrcode(page: InProcessBridgePage, _body: dict[str, Any]) -> dict[str, Any]:
        png_bytes, _b64_orig, already = fetch_qrcode(page)
        if already:
            return {"logged_in": True, "message": "已登录"}
        image_url, login_url = make_qrcode_url(png_bytes)
        result: dict[str, Any] = {
            "logged_in": False,
            "qrcode_image_url": image_url,
            "qrcode_base64": base64.b64encode(png_bytes).decode(),
            "message": "二维码已生成，请扫码后调用 /xhs/wait-login",
        }
        if login_url:
            result["qr_login_url"] = login_url
        return result

    def handle_wait_login(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        timeout = float(body.get("timeout") or 120)
        success = wait_for_login(page, timeout=timeout)
        return {
            "logged_in": success,
            "message": "登录成功" if success else "等待超时，请重新获取二维码",
        }

    def handle_send_code(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        phone = _require_str(body, "phone")
        sent = send_phone_code(page, phone)
        if not sent:
            return {"logged_in": True, "message": "已登录，无需重新登录"}
        return {
            "status": "code_sent",
            "message": f"验证码已发送至 {phone[:3]}****{phone[-4:]}",
        }

    def handle_verify_code(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        code = _require_str(body, "code")
        success = submit_phone_code(page, code)
        return {
            "logged_in": success,
            "message": "登录成功" if success else "验证码错误或超时",
        }

    def handle_delete_cookies(page: InProcessBridgePage, _body: dict[str, Any]) -> dict[str, Any]:
        logged_out = logout(page)
        return {"success": True, "message": "已退出登录" if logged_out else "未登录"}

    def handle_list_feeds(page: InProcessBridgePage, _body: dict[str, Any]) -> dict[str, Any]:
        feeds = list_feeds(page)
        return {"feeds": [f.to_dict() for f in feeds], "count": len(feeds)}

    def handle_search_feeds(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        keyword = _require_str(body, "keyword")
        filter_opt = FilterOption(
            sort_by=str(body.get("sort_by") or ""),
            note_type=str(body.get("note_type") or ""),
            publish_time=str(body.get("publish_time") or ""),
            search_scope=str(body.get("search_scope") or ""),
            location=str(body.get("location") or ""),
        )
        feeds = search_feeds(page, keyword, filter_opt)
        return {"feeds": [f.to_dict() for f in feeds], "count": len(feeds)}

    def handle_search_users(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        users = search_users(page, _require_str(body, "keyword"))
        return {"users": [u.to_dict() for u in users], "count": len(users)}

    def handle_get_feed_detail(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        detail = get_feed_detail(
            page,
            _require_str(body, "feed_id"),
            _require_str(body, "xsec_token"),
            load_all_comments=bool(body.get("load_all_comments", False)),
            config=CommentLoadConfig(
                click_more_replies=bool(body.get("click_more_replies", True)),
                max_replies_threshold=int(body.get("max_replies_threshold") or 20),
                max_comment_items=int(body.get("max_comment_items") or 0),
                scroll_speed=str(body.get("scroll_speed") or "normal"),
            ),
        )
        return detail.to_dict()

    def handle_user_profile(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        profile = get_user_profile(
            page,
            _require_str(body, "user_id"),
            _require_str(body, "xsec_token"),
        )
        return profile.to_dict()

    def handle_user_feeds(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        return get_user_feeds(
            page,
            _require_str(body, "user_id"),
            _require_str(body, "xsec_token"),
            load_more=bool(body.get("load_more", False)),
        )

    def handle_post_comment(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        post_comment(
            page,
            _require_str(body, "feed_id"),
            _require_str(body, "xsec_token"),
            _require_str(body, "content"),
        )
        return {"success": True, "message": "评论发送成功"}

    def handle_reply_comment(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        reply_comment(
            page,
            _require_str(body, "feed_id"),
            _require_str(body, "xsec_token"),
            _require_str(body, "content"),
            comment_id=str(body.get("comment_id") or ""),
            user_id=str(body.get("user_id") or ""),
        )
        return {"success": True, "message": "回复成功"}

    def handle_like_feed(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        action = unlike_feed if bool(body.get("unlike", False)) else like_feed
        result = action(page, _require_str(body, "feed_id"), _require_str(body, "xsec_token"))
        return result.to_dict()

    def handle_favorite_feed(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        action = unfavorite_feed if bool(body.get("unfavorite", False)) else favorite_feed
        result = action(page, _require_str(body, "feed_id"), _require_str(body, "xsec_token"))
        return result.to_dict()

    def _image_content_from_body(body: dict[str, Any]) -> PublishImageContent:
        image_assets = prepare_image_assets(_optional_list(body, "images"), require_remote=True)
        if not image_assets:
            raise BridgeError("INVALID_ARGUMENT", "没有有效的图片资源")
        return PublishImageContent(
            title=_require_str(body, "title"),
            content=_require_str(body, "content"),
            tags=_optional_list(body, "tags"),
            image_assets=image_assets,
            schedule_time=str(body.get("schedule_at") or ""),
            is_original=bool(body.get("original", False)),
            visibility=str(body.get("visibility") or ""),
        )

    def _video_content_from_body(body: dict[str, Any]) -> PublishVideoContent:
        video = _require_str(body, "video")
        return PublishVideoContent(
            title=_require_str(body, "title"),
            content=_require_str(body, "content"),
            tags=_optional_list(body, "tags"),
            video_path=video,
            video_asset=prepare_video_asset(video, require_remote=True),
            schedule_time=str(body.get("schedule_at") or ""),
            visibility=str(body.get("visibility") or ""),
        )

    def handle_publish(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        content = _image_content_from_body(body)
        publish_image_content(page, content)
        return {"success": True, "title": content.title, "images": len(content.image_assets), "status": "发布完成"}

    def handle_fill_publish(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        content = _image_content_from_body(body)
        fill_publish_form(page, content)
        return {"success": True, "title": content.title, "images": len(content.image_assets), "status": "表单已填写，等待确认发布"}

    def handle_fill_publish_video(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        content = _video_content_from_body(body)
        fill_publish_video_form(page, content)
        return {"success": True, "title": content.title, "video": content.video_path, "status": "视频表单已填写，等待确认发布"}

    def handle_click_publish(page: InProcessBridgePage, _body: dict[str, Any]) -> dict[str, Any]:
        click_publish_button(page)
        return {"success": True, "status": "发布完成"}

    def handle_save_draft(page: InProcessBridgePage, _body: dict[str, Any]) -> dict[str, Any]:
        save_as_draft(page)
        return {"success": True, "status": "内容已保存到草稿箱"}

    def handle_long_article(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        images = _optional_list(body, "images")
        templates = publish_long_article(
            page,
            title=_require_str(body, "title"),
            content=_require_str(body, "content"),
            image_paths=images,
            image_assets=prepare_image_assets(images, require_remote=True),
        )
        return {"success": True, "templates": templates, "status": "长文已填写，请选择模板"}

    def handle_select_template(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        name = _require_str(body, "name")
        selected = select_template(page, name)
        if not selected:
            raise BridgeError("INVALID_ARGUMENT", f"未找到模板: {name}")
        return {"success": True, "template": name, "status": "模板已选择"}

    def handle_next_step(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        click_next_and_fill_description(page, _require_str(body, "content"))
        return {"success": True, "status": "已进入发布页，等待确认发布"}

    def handle_publish_video(page: InProcessBridgePage, body: dict[str, Any]) -> dict[str, Any]:
        content = _video_content_from_body(body)
        publish_video_content(page, content)
        return {"success": True, "title": content.title, "video": content.video_path, "status": "发布完成"}

    routes: list[tuple[str, Callable[[InProcessBridgePage, dict[str, Any]], dict[str, Any]]]] = [
        ("check-login", handle_check_login),
        ("login", handle_login),
        ("get-qrcode", handle_get_qrcode),
        ("wait-login", handle_wait_login),
        ("send-code", handle_send_code),
        ("verify-code", handle_verify_code),
        ("delete-cookies", handle_delete_cookies),
        ("list-feeds", handle_list_feeds),
        ("search-feeds", handle_search_feeds),
        ("search-users", handle_search_users),
        ("get-feed-detail", handle_get_feed_detail),
        ("user-profile", handle_user_profile),
        ("user-feeds", handle_user_feeds),
        ("post-comment", handle_post_comment),
        ("reply-comment", handle_reply_comment),
        ("like-feed", handle_like_feed),
        ("favorite-feed", handle_favorite_feed),
        ("publish", handle_publish),
        ("fill-publish", handle_fill_publish),
        ("fill-publish-video", handle_fill_publish_video),
        ("click-publish", handle_click_publish),
        ("save-draft", handle_save_draft),
        ("long-article", handle_long_article),
        ("select-template", handle_select_template),
        ("next-step", handle_next_step),
        ("publish-video", handle_publish_video),
    ]

    def _make_route(handler: Callable[[InProcessBridgePage, dict[str, Any]], dict[str, Any]]):
        async def _route(request: web.Request) -> web.Response:
            return await _run_business(request, handler)

        return _route

    for path, handler in routes:
        app.router.add_post(f"/xhs/{path}", _make_route(handler))
