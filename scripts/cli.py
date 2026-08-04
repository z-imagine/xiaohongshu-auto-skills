"""统一 CLI 入口（Extension Bridge 版本）.

通过浏览器扩展 Bridge 连接用户已打开的浏览器，无需 Chrome 调试端口。
bridge server 与浏览器扩展必须由用户预先启动并连接；CLI 不自动启动本地 bridge 或 Chrome。

输出: JSON（ensure_ascii=False）
退出码: 0=成功, 1=未登录, 2=错误
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

# Windows 控制台默认编码（如 cp1252）不支持中文，强制 UTF-8
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("xhs-cli")


# ─── 输出工具 ────────────────────────────────────────────────────────────────


def _output(data: dict, exit_code: int = 0) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))
    sys.exit(exit_code)


def _open_file_if_display(path: str) -> None:
    """有桌面时用系统默认程序打开文件。"""
    import platform
    import subprocess

    try:
        system = platform.system()
        if system == "Windows":
            os.startfile(path)
        elif system == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        logger.debug("无法自动打开文件: %s", path)


# ─── Bridge 连接 ──────────────────────────────────────────────────────────────


class _DummyBrowser:
    """空 browser 对象，保持与旧代码的兼容性。"""

    def close(self) -> None:
        pass

    def close_page(self, page) -> None:
        pass


def _is_local_bridge(bridge_url: str) -> bool:
    """Return True when the bridge points to the local machine."""
    host = (urlparse(bridge_url).hostname or "").lower()
    return host in {"", "localhost", "127.0.0.1", "::1"}


def _ensure_bridge_ready(bridge_url: str, session_id: str, token: str) -> bool:
    """Return whether the configured bridge server and extension are ready."""
    from xhs.bridge import BridgePage

    page = BridgePage(bridge_url=bridge_url, session_id=session_id, token=token)
    if not page.is_server_running():
        logger.warning("Bridge server 未运行，请确认 bridge 已由用户启动: %s", bridge_url)
        return False
    if not page.is_extension_connected():
        logger.warning(
            "目标 session 尚未连接浏览器扩展，请在目标浏览器中配置并连接 extension: session=%s",
            session_id,
        )
        return False
    return True


def _connect(args: argparse.Namespace):
    """返回 (browser, page)，browser 为空对象，page 通过 Extension Bridge 操作浏览器。"""
    from xhs.bridge import BridgePage

    bridge_url, session_id, token = _resolve_bridge_settings(args)
    if not _ensure_bridge_ready(bridge_url, session_id, token):
        raise RuntimeError("bridge 或浏览器扩展未就绪，已停止执行")
    if getattr(args, "_bridge_settings_from_explicit_args", False):
        from xhs.config import BridgeConfig, save_bridge_config

        save_bridge_config(
            BridgeConfig(
                bridge_url=bridge_url,
                bridge_token=token,
                bridge_session_id=session_id,
            ),
        )
    return _DummyBrowser(), BridgePage(bridge_url=bridge_url, session_id=session_id, token=token)


def _resolve_bridge_settings(args: argparse.Namespace) -> tuple[str, str, str]:
    """Resolve bridge settings from complete CLI arguments or user config."""
    from xhs.config import load_bridge_config

    direct_values = {
        "bridge_url": getattr(args, "bridge_url", None),
        "bridge_token": getattr(args, "bridge_token", None),
        "bridge_session_id": getattr(args, "bridge_session_id", None),
    }
    specified = [value is not None for value in direct_values.values()]
    if any(specified):
        if not all(isinstance(value, str) and value.strip() for value in direct_values.values()):
            raise SystemExit(
                "显式 bridge 配置必须同时提供 --bridge-url、--bridge-token 和 --bridge-session-id",
            )
        args._bridge_settings_from_explicit_args = True
        return (
            direct_values["bridge_url"],
            direct_values["bridge_session_id"],
            direct_values["bridge_token"],
        )

    config = load_bridge_config()
    if config is None:
        raise SystemExit(
            "缺少 bridge 配置，请使用 config set 保存配置，或同时提供 "
            "--bridge-url、--bridge-token 和 --bridge-session-id",
        )
    args._bridge_settings_from_explicit_args = False
    return config.bridge_url, config.bridge_session_id, config.bridge_token


def cmd_config_set(args: argparse.Namespace) -> None:
    """Validate and persist a bridge connection configuration."""
    from xhs.bridge import BridgePage
    from xhs.config import BridgeConfig, save_bridge_config

    config = BridgeConfig(
        bridge_url=args.bridge_url,
        bridge_token=args.bridge_token,
        bridge_session_id=args.bridge_session_id,
    )
    page = BridgePage(
        bridge_url=config.bridge_url,
        session_id=config.bridge_session_id,
        token=config.bridge_token,
    )
    if not page.is_server_running():
        raise RuntimeError("无法连接 bridge server，配置未保存")
    if not page.is_extension_connected():
        raise RuntimeError("目标浏览器扩展未连接，配置未保存")

    path = save_bridge_config(config)
    _output({"success": True, "config_path": str(path)})


def cmd_config_status(args: argparse.Namespace) -> None:
    """Report whether a complete user configuration exists without secrets."""
    from xhs.config import config_path, load_bridge_config

    path = config_path()
    config = load_bridge_config(path)
    _output({"configured": config is not None, "config_path": str(path)})


# _connect_saved_tab / _connect_existing 在 bridge 模式下与 _connect 等价
_connect_saved_tab = _connect
_connect_existing = _connect


# ─── 子命令实现 ───────────────────────────────────────────────────────────────


def _qrcode_fallback(browser, page, args: argparse.Namespace) -> None:
    """频率限制时刷新页面返回二维码。"""
    from xhs.login import fetch_qrcode, make_qrcode_url, save_qrcode_to_file
    from xhs.urls import EXPLORE_URL

    page.navigate(EXPLORE_URL)
    page.wait_for_load()

    png_bytes, _b64_orig, already = fetch_qrcode(page)
    if already:
        _output({"logged_in": True, "message": "已登录"})
        return

    qrcode_path = save_qrcode_to_file(png_bytes)
    image_url, login_url = make_qrcode_url(png_bytes)
    _open_file_if_display(qrcode_path)

    result: dict = {
        "logged_in": False,
        "login_method": "qrcode",
        "qrcode_path": qrcode_path,
        "qrcode_image_url": image_url,
        "message": "验证码发送受限，已切换为二维码登录，请扫码。扫码后运行 wait-login 等待登录结果。",
    }
    if login_url:
        result["qr_login_url"] = login_url
    _output(result, exit_code=1)


def cmd_check_login(args: argparse.Namespace) -> None:
    """检查登录状态，未登录时自动获取二维码。"""
    from xhs.login import fetch_qrcode, make_qrcode_url, save_qrcode_to_file

    browser, page = _connect(args)
    try:
        png_bytes, _b64_orig, already = fetch_qrcode(page)
        if already:
            _output({"logged_in": True}, exit_code=0)
            return

        qrcode_path = save_qrcode_to_file(png_bytes)
        image_url, login_url = make_qrcode_url(png_bytes)
        _open_file_if_display(qrcode_path)

        result: dict = {
            "logged_in": False,
            "login_method": "qrcode",
            "qrcode_path": qrcode_path,
            "qrcode_image_url": image_url,
            "hint": "未登录，二维码已自动生成。扫码后运行 wait-login 等待登录结果",
        }
        if login_url:
            result["qr_login_url"] = login_url
        _output(result, exit_code=1)
    finally:
        browser.close()


def cmd_login(args: argparse.Namespace) -> None:
    """登录（扫码，阻塞等待完成）。"""
    from xhs.login import fetch_qrcode, make_qrcode_url, save_qrcode_to_file, wait_for_login

    browser, page = _connect(args)
    try:
        png_bytes, _b64_orig, already = fetch_qrcode(page)
        if already:
            _output({"logged_in": True, "message": "已登录"})
            return

        qrcode_path = save_qrcode_to_file(png_bytes)
        image_url, login_url = make_qrcode_url(png_bytes)
        _open_file_if_display(qrcode_path)

        result: dict = {"qrcode_path": qrcode_path, "qrcode_image_url": image_url}
        if login_url:
            result["qr_login_url"] = login_url
        logger.info("二维码已生成，等待扫码...")

        success = wait_for_login(page, timeout=120)
        _output(
            {"logged_in": success, "message": "登录成功" if success else "等待超时"},
            exit_code=0 if success else 2,
        )
    finally:
        browser.close()


def cmd_get_qrcode(args: argparse.Namespace) -> None:
    """获取登录二维码截图并立即返回（非阻塞）。"""
    from xhs.login import fetch_qrcode, make_qrcode_url, save_qrcode_to_file

    browser, page = _connect(args)
    try:
        png_bytes, _b64_orig, already = fetch_qrcode(page)
        if already:
            browser.close_page(page)
            browser.close()
            _output({"logged_in": True, "message": "已登录"})
            return

        qrcode_path = save_qrcode_to_file(png_bytes)
        image_url, login_url = make_qrcode_url(png_bytes)
        _open_file_if_display(qrcode_path)
        browser.close()

        result: dict = {
            "qrcode_path": qrcode_path,
            "qrcode_image_url": image_url,
            "message": "二维码已生成，请扫码登录。扫码后运行 wait-login 等待登录结果。",
        }
        if login_url:
            result["qr_login_url"] = login_url
        _output(result)
    finally:
        pass


def cmd_wait_login(args: argparse.Namespace) -> None:
    """等待扫码登录完成（配合 get-qrcode 使用）。"""
    from xhs.login import wait_for_login

    browser, page = _connect_saved_tab(args)
    try:
        success = wait_for_login(page, timeout=args.timeout)
        _output(
            {
                "logged_in": success,
                "message": "登录成功" if success else "等待超时，请重新运行 get-qrcode 获取新二维码",
            },
            exit_code=0 if success else 2,
        )
    finally:
        browser.close()


def cmd_phone_login(args: argparse.Namespace) -> None:
    """手机号+验证码登录（交互式）。"""
    from xhs.errors import RateLimitError
    from xhs.login import send_phone_code, submit_phone_code

    browser, page = _connect(args)
    try:
        sent = send_phone_code(page, args.phone)
        if not sent:
            _output({"logged_in": True, "message": "已登录，无需重新登录"})
            return

        code = args.code
        if not code:
            code = input("请输入收到的短信验证码: ").strip()

        success = submit_phone_code(page, code)
        _output(
            {"logged_in": success, "message": "登录成功" if success else "验证码错误或超时"},
            exit_code=0 if success else 2,
        )
    except RateLimitError:
        _qrcode_fallback(browser, page, args)
    finally:
        browser.close()


def cmd_send_code(args: argparse.Namespace) -> None:
    """分步登录第一步：发送手机验证码。"""
    from xhs.errors import RateLimitError
    from xhs.login import send_phone_code

    browser, page = _connect(args)
    try:
        sent = send_phone_code(page, args.phone)
        if not sent:
            _output({"logged_in": True, "message": "已登录，无需重新登录"})
            return
        _output({
            "status": "code_sent",
            "message": (
                f"验证码已发送至 {args.phone[:3]}****{args.phone[-4:]}，"
                "请运行 verify-code --code <验证码>"
            ),
        })
    except RateLimitError:
        _qrcode_fallback(browser, page, args)
    finally:
        browser.close()


def cmd_verify_code(args: argparse.Namespace) -> None:
    """分步登录第二步：填写验证码并提交。"""
    from xhs.login import submit_phone_code

    browser, page = _connect_saved_tab(args)
    try:
        success = submit_phone_code(page, args.code)
        _output(
            {"logged_in": success, "message": "登录成功" if success else "验证码错误或超时"},
            exit_code=0 if success else 2,
        )
    finally:
        browser.close()


def cmd_delete_cookies(args: argparse.Namespace) -> None:
    """退出登录（页面 UI 点击退出）。"""
    from xhs.login import logout

    browser, page = _connect(args)
    try:
        logged_out = logout(page)
        msg = "已退出登录" if logged_out else "未登录"
        _output({"success": True, "message": msg})
    finally:
        browser.close()


def cmd_list_feeds(args: argparse.Namespace) -> None:
    """获取首页 Feed 列表。"""
    from xhs.feeds import list_feeds

    browser, page = _connect(args)
    try:
        feeds = list_feeds(page)
        _output({"feeds": [f.to_dict() for f in feeds], "count": len(feeds)})
    finally:
        browser.close()


def cmd_search_feeds(args: argparse.Namespace) -> None:
    """搜索 Feeds。"""
    from xhs.search import search_feeds
    from xhs.types import FilterOption

    filter_opt = FilterOption(
        sort_by=args.sort_by or "",
        note_type=args.note_type or "",
        publish_time=args.publish_time or "",
        search_scope=args.search_scope or "",
        location=args.location or "",
    )

    browser, page = _connect(args)
    try:
        feeds = search_feeds(page, args.keyword, filter_opt)
        _output({"feeds": [f.to_dict() for f in feeds], "count": len(feeds)})
    finally:
        browser.close()


def cmd_search_users(args: argparse.Namespace) -> None:
    """搜索用户/账号。"""
    from xhs.user_search import search_users

    browser, page = _connect(args)
    try:
        users = search_users(page, args.keyword)
        _output({"users": [u.to_dict() for u in users], "count": len(users)})
    finally:
        browser.close()


def cmd_user_feeds(args: argparse.Namespace) -> None:
    """查询用户笔记第一页，可选择加载下一批。"""
    from xhs.user_feeds import get_user_feeds

    browser, page = _connect(args)
    try:
        result = get_user_feeds(
            page,
            args.user_id,
            args.xsec_token,
            load_more=args.load_more,
        )
        _output(result)
    finally:
        browser.close()


def cmd_current_user(args: argparse.Namespace) -> None:
    """查询当前登录账号的基本信息。"""
    from xhs.user_profile import get_current_user_profile

    browser, page = _connect(args)
    try:
        _output(get_current_user_profile(page))
    finally:
        browser.close()


def cmd_get_feed_detail(args: argparse.Namespace) -> None:
    """获取 Feed 详情。"""
    from xhs.feed_detail import get_feed_detail
    from xhs.types import CommentLoadConfig

    config = CommentLoadConfig(
        click_more_replies=args.click_more_replies,
        max_replies_threshold=args.max_replies_threshold,
        max_comment_items=args.max_comment_items,
        scroll_speed=args.scroll_speed,
    )

    browser, page = _connect(args)
    try:
        detail = get_feed_detail(
            page,
            args.feed_id,
            args.xsec_token,
            load_all_comments=args.load_all_comments,
            config=config,
        )
        _output(detail.to_dict())
    finally:
        browser.close()


def cmd_user_profile(args: argparse.Namespace) -> None:
    """获取用户主页。"""
    from xhs.user_profile import get_user_profile

    browser, page = _connect(args)
    try:
        profile = get_user_profile(page, args.user_id, args.xsec_token)
        _output(profile.to_dict())
    finally:
        browser.close()


def cmd_post_comment(args: argparse.Namespace) -> None:
    """发表评论。"""
    from xhs.comment import post_comment

    browser, page = _connect(args)
    try:
        from xhs.risk_gate import NetlogRiskGate

        gate = NetlogRiskGate.start(page)
        post_comment(page, args.feed_id, args.xsec_token, args.content)
        gate.check_after()
        _output({"success": True, "message": "评论发送成功"})
    finally:
        browser.close()


def cmd_reply_comment(args: argparse.Namespace) -> None:
    """回复评论。"""
    from xhs.comment import reply_comment

    browser, page = _connect(args)
    try:
        from xhs.risk_gate import NetlogRiskGate

        gate = NetlogRiskGate.start(page)
        reply_comment(
            page,
            args.feed_id,
            args.xsec_token,
            args.content,
            comment_id=args.comment_id or "",
            user_id=args.user_id or "",
        )
        gate.check_after()
        _output({"success": True, "message": "回复成功"})
    finally:
        browser.close()


def cmd_like_feed(args: argparse.Namespace) -> None:
    """点赞/取消点赞。"""
    from xhs.like_favorite import like_feed, unlike_feed

    browser, page = _connect(args)
    try:
        from xhs.risk_gate import NetlogRiskGate

        gate = NetlogRiskGate.start(page)
        if args.unlike:
            result = unlike_feed(page, args.feed_id, args.xsec_token)
        else:
            result = like_feed(page, args.feed_id, args.xsec_token)
        gate.check_after()
        _output(result.to_dict())
    finally:
        browser.close()


def cmd_favorite_feed(args: argparse.Namespace) -> None:
    """收藏/取消收藏。"""
    from xhs.like_favorite import favorite_feed, unfavorite_feed

    browser, page = _connect(args)
    try:
        from xhs.risk_gate import NetlogRiskGate

        gate = NetlogRiskGate.start(page)
        if args.unfavorite:
            result = unfavorite_feed(page, args.feed_id, args.xsec_token)
        else:
            result = favorite_feed(page, args.feed_id, args.xsec_token)
        gate.check_after()
        _output(result.to_dict())
    finally:
        browser.close()


def cmd_publish(args: argparse.Namespace) -> None:
    """发布图文内容。"""
    from media_assets import prepare_image_assets
    from xhs.publish import publish_image_content
    from xhs.types import PublishImageContent

    with open(args.title_file, encoding="utf-8") as f:
        title = f.read().strip()
    with open(args.content_file, encoding="utf-8") as f:
        content = f.read().strip()

    bridge_url, _session_id, _token = _resolve_bridge_settings(args)
    image_assets = prepare_image_assets(
        args.images or [],
        require_remote=not _is_local_bridge(bridge_url),
    )
    if not image_assets:
        _output({"success": False, "error": "没有有效的图片资源"}, exit_code=2)

    browser, page = _connect(args)
    try:
        from xhs.risk_gate import NetlogRiskGate

        gate = NetlogRiskGate.start(page)
        publish_image_content(
            page,
            PublishImageContent(
                title=title,
                content=content,
                tags=args.tags or [],
                image_assets=image_assets,
                schedule_time=args.schedule_at,
                is_original=args.original,
                visibility=args.visibility or "",
            ),
        )
        gate.check_after()
        _output({"success": True, "title": title, "images": len(image_assets), "status": "发布完成"})
    finally:
        browser.close()


def cmd_fill_publish(args: argparse.Namespace) -> None:
    """只填写图文表单，不发布。"""
    from media_assets import prepare_image_assets
    from xhs.publish import fill_publish_form
    from xhs.types import PublishImageContent

    with open(args.title_file, encoding="utf-8") as f:
        title = f.read().strip()
    with open(args.content_file, encoding="utf-8") as f:
        content = f.read().strip()

    bridge_url, _session_id, _token = _resolve_bridge_settings(args)
    image_assets = prepare_image_assets(
        args.images or [],
        require_remote=not _is_local_bridge(bridge_url),
    )
    if not image_assets:
        _output({"success": False, "error": "没有有效的图片资源"}, exit_code=2)

    browser, page = _connect(args)
    try:
        fill_publish_form(
            page,
            PublishImageContent(
                title=title,
                content=content,
                tags=args.tags or [],
                image_assets=image_assets,
                schedule_time=args.schedule_at,
                is_original=args.original,
                visibility=args.visibility or "",
            ),
        )
        _output({"success": True, "title": title, "images": len(image_assets), "status": "表单已填写，等待确认发布"})
    finally:
        browser.close()


def cmd_fill_publish_video(args: argparse.Namespace) -> None:
    """只填写视频表单，不发布。"""
    from media_assets import prepare_video_asset
    from xhs.publish_video import fill_publish_video_form
    from xhs.types import PublishVideoContent

    with open(args.title_file, encoding="utf-8") as f:
        title = f.read().strip()
    with open(args.content_file, encoding="utf-8") as f:
        content = f.read().strip()

    bridge_url, _session_id, _token = _resolve_bridge_settings(args)
    video_asset = prepare_video_asset(
        args.video,
        require_remote=not _is_local_bridge(bridge_url),
    )

    browser, page = _connect(args)
    try:
        fill_publish_video_form(
            page,
            PublishVideoContent(
                title=title,
                content=content,
                tags=args.tags or [],
                video_path=args.video,
                video_asset=video_asset,
                schedule_time=args.schedule_at,
                visibility=args.visibility or "",
            ),
        )
        _output({"success": True, "title": title, "video": args.video, "status": "视频表单已填写，等待确认发布"})
    finally:
        browser.close()


def cmd_click_publish(args: argparse.Namespace) -> None:
    """点击发布按钮（在用户确认后调用）。"""
    from xhs.publish import click_publish_button

    browser, page = _connect_existing(args)
    try:
        from xhs.risk_gate import NetlogRiskGate

        gate = NetlogRiskGate.start(page)
        click_publish_button(page)
        gate.check_after()
        _output({"success": True, "status": "发布完成"})
    finally:
        browser.close()


def cmd_save_draft(args: argparse.Namespace) -> None:
    """保存为草稿。"""
    from xhs.publish import save_as_draft

    browser, page = _connect_existing(args)
    try:
        save_as_draft(page)
        _output({"success": True, "status": "内容已保存到草稿箱"})
    finally:
        browser.close()


def cmd_long_article(args: argparse.Namespace) -> None:
    """长文模式：填写内容 + 一键排版，返回模板列表。"""
    from media_assets import prepare_image_assets
    from xhs.publish_long_article import publish_long_article

    with open(args.title_file, encoding="utf-8") as f:
        title = f.read().strip()
    with open(args.content_file, encoding="utf-8") as f:
        content = f.read().strip()

    bridge_url, _session_id, _token = _resolve_bridge_settings(args)
    image_assets = prepare_image_assets(
        args.images or [],
        require_remote=not _is_local_bridge(bridge_url),
    )

    browser, page = _connect(args)
    try:
        template_names = publish_long_article(
            page,
            title=title,
            content=content,
            image_paths=args.images,
            image_assets=image_assets,
        )
        _output({"success": True, "templates": template_names, "status": "长文已填写，请选择模板"})
    finally:
        browser.close()


def cmd_select_template(args: argparse.Namespace) -> None:
    """选择排版模板。"""
    from xhs.publish_long_article import select_template

    browser, page = _connect_existing(args)
    try:
        selected = select_template(page, args.name)
        if selected:
            _output({"success": True, "template": args.name, "status": "模板已选择"})
        else:
            _output({"success": False, "error": f"未找到模板: {args.name}"}, exit_code=2)
    finally:
        browser.close()


def cmd_next_step(args: argparse.Namespace) -> None:
    """点击下一步 + 填写发布页描述。"""
    from xhs.publish_long_article import click_next_and_fill_description

    with open(args.content_file, encoding="utf-8") as f:
        description = f.read().strip()

    browser, page = _connect_existing(args)
    try:
        click_next_and_fill_description(page, description)
        _output({"success": True, "status": "已进入发布页，等待确认发布"})
    finally:
        browser.close()


def cmd_publish_video(args: argparse.Namespace) -> None:
    """发布视频内容。"""
    from media_assets import prepare_video_asset
    from xhs.publish_video import publish_video_content
    from xhs.types import PublishVideoContent

    with open(args.title_file, encoding="utf-8") as f:
        title = f.read().strip()
    with open(args.content_file, encoding="utf-8") as f:
        content = f.read().strip()

    bridge_url, _session_id, _token = _resolve_bridge_settings(args)
    video_asset = prepare_video_asset(
        args.video,
        require_remote=not _is_local_bridge(bridge_url),
    )

    browser, page = _connect(args)
    try:
        from xhs.risk_gate import NetlogRiskGate

        gate = NetlogRiskGate.start(page)
        publish_video_content(
            page,
            PublishVideoContent(
                title=title,
                content=content,
                tags=args.tags or [],
                video_path=args.video,
                video_asset=video_asset,
                schedule_time=args.schedule_at,
                visibility=args.visibility or "",
            ),
        )
        gate.check_after()
        _output({"success": True, "title": title, "video": args.video, "status": "发布完成"})
    finally:
        browser.close()


def cmd_set_netlog_enabled(args: argparse.Namespace) -> None:
    """显式启用或关闭脱敏网络日志。"""
    browser, page = _connect_existing(args)
    try:
        state = page.set_netlog_enabled(args.enabled)
        _output({"success": True, "netlog": state})
    finally:
        browser.close()


def cmd_get_netlog(args: argparse.Namespace) -> None:
    """读取最近的脱敏网络日志。"""
    browser, page = _connect_existing(args)
    try:
        state = page.get_netlog_state()
        if not state.get("enabled"):
            _output({"success": False, "error": "NetLogger 未启用"}, exit_code=2)
        entries = page.get_netlog()
        if args.limit is not None:
            entries = entries[-args.limit :]
        _output({"success": True, "total": len(entries), "entries": entries})
    finally:
        browser.close()


def cmd_risk_report(args: argparse.Namespace) -> None:
    """对当前会话的 NetLog 生成离线风险报告。"""
    from xhs.risk_analyzer import analyze

    browser, page = _connect_existing(args)
    try:
        state = page.get_netlog_state()
        if not state.get("enabled"):
            _output({"success": False, "error": "NetLogger 未启用"}, exit_code=2)
        _output({"success": True, "report": analyze(page.get_netlog())})
    finally:
        browser.close()


def cmd_clear_netlog(args: argparse.Namespace) -> None:
    """清空当前会话的脱敏网络日志。"""
    browser, page = _connect_existing(args)
    try:
        _output({"success": True, "netlog": page.clear_netlog()})
    finally:
        browser.close()


# ─── 只读诊断 ────────────────────────────────────────────────────────────────


def _diagnostic_page(args: argparse.Namespace):
    """Create a bridge page without requiring a connected extension first."""
    from xhs.bridge import BridgePage

    bridge_url, session_id, token = _resolve_bridge_settings(args)
    return BridgePage(bridge_url=bridge_url, session_id=session_id, token=token)


def _png_dimensions(payload: bytes) -> tuple[int, int]:
    """Return PNG pixel dimensions without an image library dependency."""
    if len(payload) < 24 or payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        return 0, 0
    return int.from_bytes(payload[16:20], "big"), int.from_bytes(payload[20:24], "big")


def _save_screenshot(result: dict, output: str | None) -> dict:
    encoded = result.get("data")
    if not isinstance(encoded, str) or not encoded:
        raise RuntimeError("截图结果缺少 PNG 数据")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise RuntimeError("截图 PNG 数据无效") from exc

    if output:
        path = Path(output).expanduser()
        if not path.is_absolute():
            raise ValueError("--output 必须是绝对路径")
        if path.exists():
            raise FileExistsError(f"截图输出文件已存在: {path}")
    else:
        directory = Path(tempfile.mkdtemp(prefix="xhs-diagnostic-"))
        path = directory / "screenshot.png"

    path.write_bytes(payload)
    width, height = _png_dimensions(payload)
    return {
        "path": str(path),
        "mime_type": result.get("mime_type") or "image/png",
        "width": width,
        "height": height,
        "captured_at": result.get("captured_at"),
        "url": result.get("url"),
    }


def cmd_screenshot(args: argparse.Namespace) -> None:
    """Capture the current target XHS tab to a local PNG file."""
    browser = None
    try:
        browser, page = _connect_existing(args)
        _output({"success": True, "screenshot": _save_screenshot(page.screenshot(), args.output)})
    except Exception as exc:
        _output(
            {"success": False, "error_code": "SCREENSHOT_FAILED", "error": str(exc)},
            exit_code=2,
        )
    finally:
        if browser is not None:
            browser.close()


def cmd_inspect_page(args: argparse.Namespace) -> None:
    """Return a bounded, read-only snapshot of the current target page."""
    browser, page = _connect_existing(args)
    try:
        _output({"success": True, "page": page.get_page_state()})
    finally:
        browser.close()


def cmd_bridge_status(args: argparse.Namespace) -> None:
    """Read server-side session state, including an offline extension session."""
    page = _diagnostic_page(args)
    _output({"success": True, "session": page.get_session_state()})


def cmd_diagnose(args: argparse.Namespace) -> None:
    """Collect independent, read-only diagnostic checks with partial results."""
    page = _diagnostic_page(args)
    bridge: dict[str, object]
    try:
        bridge = {"ok": True, "state": page.get_session_state()}
    except Exception as exc:
        bridge = {"ok": False, "error": str(exc)}

    page_state: dict[str, object]
    try:
        page_state = {"ok": True, "state": page.get_page_state()}
    except Exception as exc:
        page_state = {"ok": False, "error": str(exc)}

    result: dict[str, object] = {
        "success": bool(bridge["ok"]),
        "bridge": bridge,
        "page": page_state,
    }
    if args.screenshot:
        try:
            result["screenshot"] = {"ok": True, **_save_screenshot(page.screenshot(), args.output)}
        except Exception as exc:
            result["screenshot"] = {"ok": False, "error": str(exc)}
    _output(result, exit_code=0 if bridge["ok"] else 2)


# ─── 参数解析 ──────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xhs-cli",
        description="小红书自动化 CLI（Extension Bridge 版）",
    )
    parser.add_argument(
        "--bridge-url",
        default=None,
        help="Bridge server WebSocket 地址（需与另外两项 bridge 参数同时提供）",
    )
    parser.add_argument(
        "--bridge-session-id",
        default=None,
        help="目标浏览器的 Session ID（需与另外两项 bridge 参数同时提供）",
    )
    parser.add_argument(
        "--bridge-token",
        default=None,
        help="Bridge 鉴权 token（需与另外两项 bridge 参数同时提供）",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # config
    sub = subparsers.add_parser("config", help="管理用户级 bridge 配置")
    config_subparsers = sub.add_subparsers(dest="config_command", required=True)
    config_set = config_subparsers.add_parser("set", help="验证并保存 bridge 配置")
    config_set.add_argument("--bridge-url", required=True, help="Bridge server WebSocket 地址")
    config_set.add_argument("--bridge-session-id", required=True, help="目标浏览器的 Session ID")
    config_set.add_argument("--bridge-token", required=True, help="Bridge 鉴权 token")
    config_set.set_defaults(func=cmd_config_set)
    config_status = config_subparsers.add_parser(
        "status",
        help="查看 bridge 配置状态（不显示秘密）",
    )
    config_status.set_defaults(func=cmd_config_status)

    # check-login
    sub = subparsers.add_parser("check-login", help="检查登录状态")
    sub.set_defaults(func=cmd_check_login)

    # login
    sub = subparsers.add_parser("login", help="登录（扫码，阻塞等待）")
    sub.set_defaults(func=cmd_login)

    # get-qrcode
    sub = subparsers.add_parser("get-qrcode", help="获取登录二维码截图（非阻塞）")
    sub.set_defaults(func=cmd_get_qrcode)

    # wait-login
    sub = subparsers.add_parser("wait-login", help="等待扫码登录完成（配合 get-qrcode）")
    sub.add_argument("--timeout", type=float, default=120.0, help="等待超时秒数 (default: 120)")
    sub.set_defaults(func=cmd_wait_login)

    # phone-login
    sub = subparsers.add_parser("phone-login", help="手机号+验证码登录（交互式）")
    sub.add_argument("--phone", required=True, help="手机号")
    sub.add_argument("--code", default="", help="短信验证码（省略则交互式输入）")
    sub.set_defaults(func=cmd_phone_login)

    # send-code
    sub = subparsers.add_parser("send-code", help="分步登录第一步：发送手机验证码")
    sub.add_argument("--phone", required=True, help="手机号")
    sub.set_defaults(func=cmd_send_code)

    # verify-code
    sub = subparsers.add_parser("verify-code", help="分步登录第二步：填写验证码")
    sub.add_argument("--code", required=True, help="短信验证码")
    sub.set_defaults(func=cmd_verify_code)

    # delete-cookies
    sub = subparsers.add_parser("delete-cookies", help="退出登录")
    sub.set_defaults(func=cmd_delete_cookies)

    # list-feeds
    sub = subparsers.add_parser("list-feeds", help="获取首页 Feed 列表")
    sub.set_defaults(func=cmd_list_feeds)

    # search-feeds
    sub = subparsers.add_parser("search-feeds", help="搜索 Feeds")
    sub.add_argument("--keyword", required=True, help="搜索关键词")
    sub.add_argument("--sort-by", help="排序: 综合|最新|最多点赞|最多评论|最多收藏")
    sub.add_argument("--note-type", help="类型: 不限|视频|图文")
    sub.add_argument("--publish-time", help="时间: 不限|一天内|一周内|半年内")
    sub.add_argument("--search-scope", help="范围: 不限|已看过|未看过|已关注")
    sub.add_argument("--location", help="位置: 不限|同城|附近")
    sub.set_defaults(func=cmd_search_feeds)

    # search-users
    sub = subparsers.add_parser("search-users", help="搜索用户/账号")
    sub.add_argument("--keyword", required=True, help="搜索关键词")
    sub.set_defaults(func=cmd_search_users)

    # get-feed-detail
    sub = subparsers.add_parser("get-feed-detail", help="获取 Feed 详情")
    sub.add_argument("--feed-id", required=True, help="Feed ID")
    sub.add_argument("--xsec-token", required=True, help="xsec_token")
    sub.add_argument("--load-all-comments", action="store_true", help="加载全部评论")
    sub.add_argument("--click-more-replies", action="store_true", help="展开更多回复")
    sub.add_argument("--max-replies-threshold", type=int, default=10)
    sub.add_argument("--max-comment-items", type=int, default=0)
    sub.add_argument("--scroll-speed", default="normal", help="slow|normal|fast")
    sub.set_defaults(func=cmd_get_feed_detail)

    # user-profile
    sub = subparsers.add_parser("current-user", help="查询当前登录账号的基本信息")
    sub.set_defaults(func=cmd_current_user)

    sub = subparsers.add_parser("user-profile", help="获取用户主页")
    sub.add_argument("--user-id", required=True)
    sub.add_argument("--xsec-token", required=True)
    sub.set_defaults(func=cmd_user_profile)

    # user-feeds
    sub = subparsers.add_parser("user-feeds", help="查询用户笔记第一页，可加载下一批")
    sub.add_argument("--user-id", required=True)
    sub.add_argument("--xsec-token", required=True)
    sub.add_argument("--load-more", action="store_true", help="触发一次加载更多")
    sub.set_defaults(func=cmd_user_feeds)

    # post-comment
    sub = subparsers.add_parser("post-comment", help="发表评论")
    sub.add_argument("--feed-id", required=True)
    sub.add_argument("--xsec-token", required=True)
    sub.add_argument("--content", required=True)
    sub.set_defaults(func=cmd_post_comment)

    # reply-comment
    sub = subparsers.add_parser("reply-comment", help="回复评论")
    sub.add_argument("--feed-id", required=True)
    sub.add_argument("--xsec-token", required=True)
    sub.add_argument("--content", required=True)
    sub.add_argument("--comment-id")
    sub.add_argument("--user-id")
    sub.set_defaults(func=cmd_reply_comment)

    # like-feed
    sub = subparsers.add_parser("like-feed", help="点赞")
    sub.add_argument("--feed-id", required=True)
    sub.add_argument("--xsec-token", required=True)
    sub.add_argument("--unlike", action="store_true")
    sub.set_defaults(func=cmd_like_feed)

    # favorite-feed
    sub = subparsers.add_parser("favorite-feed", help="收藏")
    sub.add_argument("--feed-id", required=True)
    sub.add_argument("--xsec-token", required=True)
    sub.add_argument("--unfavorite", action="store_true")
    sub.set_defaults(func=cmd_favorite_feed)

    # publish
    sub = subparsers.add_parser("publish", help="发布图文")
    sub.add_argument("--title-file", required=True)
    sub.add_argument("--content-file", required=True)
    sub.add_argument("--images", nargs="+", required=True)
    sub.add_argument("--tags", nargs="*")
    sub.add_argument("--schedule-at")
    sub.add_argument("--original", action="store_true")
    sub.add_argument("--visibility")
    sub.set_defaults(func=cmd_publish)

    # publish-video
    sub = subparsers.add_parser("publish-video", help="发布视频")
    sub.add_argument("--title-file", required=True)
    sub.add_argument("--content-file", required=True)
    sub.add_argument("--video", required=True)
    sub.add_argument("--tags", nargs="*")
    sub.add_argument("--schedule-at")
    sub.add_argument("--visibility")
    sub.set_defaults(func=cmd_publish_video)

    # fill-publish
    sub = subparsers.add_parser("fill-publish", help="填写图文表单（不发布）")
    sub.add_argument("--title-file", required=True)
    sub.add_argument("--content-file", required=True)
    sub.add_argument("--images", nargs="+", required=True)
    sub.add_argument("--tags", nargs="*")
    sub.add_argument("--schedule-at")
    sub.add_argument("--original", action="store_true")
    sub.add_argument("--visibility")
    sub.set_defaults(func=cmd_fill_publish)

    # fill-publish-video
    sub = subparsers.add_parser("fill-publish-video", help="填写视频表单（不发布）")
    sub.add_argument("--title-file", required=True)
    sub.add_argument("--content-file", required=True)
    sub.add_argument("--video", required=True)
    sub.add_argument("--tags", nargs="*")
    sub.add_argument("--schedule-at")
    sub.add_argument("--visibility")
    sub.set_defaults(func=cmd_fill_publish_video)

    # click-publish
    sub = subparsers.add_parser("click-publish", help="点击发布按钮")
    sub.set_defaults(func=cmd_click_publish)

    # save-draft
    sub = subparsers.add_parser("save-draft", help="保存为草稿")
    sub.set_defaults(func=cmd_save_draft)

    # long-article
    sub = subparsers.add_parser("long-article", help="长文模式：填写 + 一键排版")
    sub.add_argument("--title-file", required=True)
    sub.add_argument("--content-file", required=True)
    sub.add_argument("--images", nargs="*")
    sub.set_defaults(func=cmd_long_article)

    # select-template
    sub = subparsers.add_parser("select-template", help="选择排版模板")
    sub.add_argument("--name", required=True)
    sub.set_defaults(func=cmd_select_template)

    # next-step
    sub = subparsers.add_parser("next-step", help="点击下一步 + 填写描述")
    sub.add_argument("--content-file", required=True)
    sub.set_defaults(func=cmd_next_step)

    sub = subparsers.add_parser("enable-netlog", help="启用脱敏网络日志（默认关闭）")
    sub.set_defaults(func=cmd_set_netlog_enabled, enabled=True)

    sub = subparsers.add_parser("disable-netlog", help="关闭脱敏网络日志")
    sub.set_defaults(func=cmd_set_netlog_enabled, enabled=False)

    sub = subparsers.add_parser("get-netlog", help="读取脱敏网络日志")
    sub.add_argument("--limit", type=int, default=None, help="只读取最近 N 条")
    sub.set_defaults(func=cmd_get_netlog)

    sub = subparsers.add_parser("risk-report", help="根据 NetLog 生成风险摘要")
    sub.set_defaults(func=cmd_risk_report)

    sub = subparsers.add_parser("clear-netlog", help="清空 NetLog 缓存")
    sub.set_defaults(func=cmd_clear_netlog)

    # Read-only diagnostics. These remain separate from business commands.
    sub = subparsers.add_parser("screenshot", help="截取目标 XHS tab 到本地 PNG")
    sub.add_argument("--output", help="本地 PNG 绝对输出路径（默认临时目录）")
    sub.set_defaults(func=cmd_screenshot)

    sub = subparsers.add_parser("inspect-page", help="读取目标页面的只读状态快照")
    sub.set_defaults(func=cmd_inspect_page)

    sub = subparsers.add_parser("bridge-status", help="读取 bridge 与目标 session 状态")
    sub.set_defaults(func=cmd_bridge_status)

    sub = subparsers.add_parser("diagnose", help="汇总 bridge、页面和可选截图诊断")
    sub.add_argument("--screenshot", action="store_true", help="同时截取目标 tab")
    sub.add_argument("--output", help="截图本地 PNG 绝对输出路径")
    sub.set_defaults(func=cmd_diagnose)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        args.func(args)
    except Exception as e:
        logger.error("执行失败: %s", e, exc_info=True)
        _output({"success": False, "error": str(e)}, exit_code=2)


if __name__ == "__main__":
    main()
