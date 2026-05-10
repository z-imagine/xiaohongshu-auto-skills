#!/usr/bin/env python3
"""用 Kimi WebBridge 测试小红书用户主页笔记加载更多。

示例:
    uv run python scripts/kimi_user_feeds_scroll_test.py \
      --user-id USER_ID \
      --xsec-token 'YOUR_XSEC_TOKEN'
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote


DEFAULT_KIMI_URL = "http://127.0.0.1:10086/command"
DEFAULT_SESSION = "xhs-user-feeds-scroll-test"


def main() -> int:
    args = parse_args()
    client = KimiWebBridge(args.kimi_url, args.session)

    profile_url = make_user_profile_url(args.user_id, args.xsec_token)
    print_json(
        {
            "event": "navigate",
            "url": profile_url,
        }
    )
    client.command("navigate", {"url": profile_url, "newTab": args.new_tab})
    time.sleep(args.initial_wait)

    before = read_state(client)
    before_keys = feed_keys(before["feeds"])
    print_round("initial", before, [])

    round_no = 0
    empty_rounds = 0
    while round_no < args.max_rounds:
        round_no += 1
        after = scroll_and_wait(client, before_count=before["count"], timeout=args.timeout)
        after_keys = feed_keys(after["feeds"])
        new_feeds = [
            simplify_feed(feed)
            for feed in after["feeds"]
            if feed_key(feed) not in before_keys
        ]

        print_round(round_no, after, new_feeds)

        if after["count"] <= before["count"]:
            empty_rounds += 1
            if empty_rounds < args.stop_after_empty:
                print_json(
                    {
                        "event": "retry",
                        "reason": "no new feeds after scroll",
                        "emptyRounds": empty_rounds,
                        "stopAfterEmpty": args.stop_after_empty,
                        "hasMore": after.get("hasMore", False),
                        "totalLoaded": after["count"],
                    }
                )
                before = after
                before_keys = after_keys
                time.sleep(args.round_delay)
                continue

            print_json(
                {
                    "event": "stop",
                    "reason": "no new feeds after consecutive scrolls",
                    "beforeCount": before["count"],
                    "afterCount": after["count"],
                    "emptyRounds": empty_rounds,
                    "hasMore": after.get("hasMore", False),
                }
            )
            return 0

        empty_rounds = 0
        before = after
        before_keys = after_keys
        time.sleep(args.round_delay)

    print_json(
        {
            "event": "stop",
            "reason": "max rounds reached",
            "maxRounds": args.max_rounds,
            "totalLoaded": before["count"],
            "hasMore": before.get("hasMore", False),
        }
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="通过 Kimi WebBridge 在真实浏览器中测试小红书用户主页加载更多。"
    )
    parser.add_argument("--user-id", required=True, help="小红书用户 ID")
    parser.add_argument("--xsec-token", required=True, help="用户主页 URL 中的 xsec_token")
    parser.add_argument("--kimi-url", default=DEFAULT_KIMI_URL, help="Kimi WebBridge command URL")
    parser.add_argument("--session", default=DEFAULT_SESSION, help="Kimi WebBridge session 名称")
    parser.add_argument("--max-rounds", type=int, default=30, help="最多下拉次数")
    parser.add_argument("--timeout", type=float, default=12.0, help="每轮等待加载超时时间")
    parser.add_argument("--initial-wait", type=float, default=3.0, help="打开主页后的初始等待秒数")
    parser.add_argument("--round-delay", type=float, default=0.6, help="每轮之间的等待秒数")
    parser.add_argument("--stop-after-empty", type=int, default=3, help="连续多少轮无新增后停止")
    parser.add_argument("--new-tab", action="store_true", help="使用新标签页打开用户主页")
    return parser.parse_args()


class KimiWebBridge:
    def __init__(self, command_url: str, session: str) -> None:
        self.command_url = command_url
        self.session = session

    def command(self, action: str, args: dict[str, Any]) -> Any:
        payload = json.dumps(
            {"action": action, "args": args, "session": self.session},
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            self.command_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Kimi WebBridge 请求失败: {exc}") from exc

        result = json.loads(body)
        if not result.get("ok", False):
            raise RuntimeError(f"Kimi WebBridge 返回错误: {body}")
        return result.get("data")

    def evaluate(self, code: str) -> Any:
        data = self.command("evaluate", {"code": code})
        if isinstance(data, dict) and "value" in data:
            return data["value"]
        return data


def make_user_profile_url(user_id: str, xsec_token: str) -> str:
    return (
        f"https://www.xiaohongshu.com/user/profile/{quote(user_id)}"
        f"?xsec_token={quote(xsec_token, safe='')}&xsec_source=pc_search"
    )


def read_state(client: KimiWebBridge) -> dict[str, Any]:
    return client.evaluate(
        """
(() => {
  const unwrap = (v) => {
    if (v && typeof v === "object" && "value" in v) return v.value;
    if (v && typeof v === "object" && "_value" in v) return v._value;
    return v;
  };
  const user = window.__INITIAL_STATE__?.user || {};
  const notes = unwrap(user.notes);
  const queries = unwrap(user.noteQueries) || [];
  const fetching = unwrap(user.isFetchingNotes) || [];
  const feeds = Array.isArray(notes) ? notes.flat().filter(Boolean) : [];
  const query = queries[0] || {};
  return {
    href: location.href,
    count: feeds.length,
    feeds,
    hasMore: Boolean(query.hasMore),
    cursor: query.cursor || "",
    isFetching: Boolean(fetching[0]),
    scrollY,
    innerHeight,
    scrollHeight: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)
  };
})()
"""
    )


def scroll_and_wait(client: KimiWebBridge, before_count: int, timeout: float) -> dict[str, Any]:
    return client.evaluate(
        f"""
(async () => {{
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const unwrap = (v) => {{
    if (v && typeof v === "object" && "value" in v) return v.value;
    if (v && typeof v === "object" && "_value" in v) return v._value;
    return v;
  }};
  const state = () => {{
    const user = window.__INITIAL_STATE__?.user || {{}};
    const notes = unwrap(user.notes);
    const queries = unwrap(user.noteQueries) || [];
    const fetching = unwrap(user.isFetchingNotes) || [];
    const feeds = Array.isArray(notes) ? notes.flat().filter(Boolean) : [];
    const query = queries[0] || {{}};
    return {{
      href: location.href,
      count: feeds.length,
      feeds,
      hasMore: Boolean(query.hasMore),
      cursor: query.cursor || "",
      isFetching: Boolean(fetching[0]),
      scrollY,
      innerHeight,
      scrollHeight: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)
    }};
  }};

  window.scrollTo(0, Math.max(document.documentElement.scrollHeight, document.body.scrollHeight));
  let sawFetching = false;
  const startedAt = Date.now();
  while (Date.now() - startedAt < {int(timeout * 1000)}) {{
    await sleep(300);
    const current = state();
    if (current.isFetching) sawFetching = true;
    if (current.count > {before_count}) return current;
    if (sawFetching && !current.isFetching) return current;
  }}
  const current = state();
  current.timeout = true;
  return current;
}})()
"""
    )


def print_round(round_no: int | str, state: dict[str, Any], new_feeds: list[dict[str, Any]]) -> None:
    print_json(
        {
            "round": round_no,
            "newCount": len(new_feeds),
            "totalLoaded": state["count"],
            "hasMore": state.get("hasMore", False),
            "cursor": state.get("cursor", ""),
            "isFetching": state.get("isFetching", False),
            "scrollY": state.get("scrollY"),
            "scrollHeight": state.get("scrollHeight"),
            "newFeeds": new_feeds,
        }
    )


def simplify_feed(feed: dict[str, Any]) -> dict[str, Any]:
    note_card = feed.get("noteCard") or feed.get("note_card") or {}
    user = note_card.get("user") or {}
    interact = note_card.get("interactInfo") or note_card.get("interact_info") or {}
    return {
        "id": feed.get("id") or feed.get("noteId") or note_card.get("noteId"),
        "xsecToken": feed.get("xsecToken") or feed.get("xsec_token"),
        "title": note_card.get("displayTitle") or note_card.get("title") or "",
        "type": note_card.get("type") or feed.get("modelType") or "",
        "author": user.get("nickname") or "",
        "likedCount": interact.get("likedCount") or interact.get("liked_count") or "",
    }


def feed_keys(feeds: list[dict[str, Any]]) -> set[str]:
    return {feed_key(feed) for feed in feeds}


def feed_key(feed: dict[str, Any]) -> str:
    note_card = feed.get("noteCard") or feed.get("note_card") or {}
    return str(
        feed.get("id")
        or feed.get("noteId")
        or note_card.get("noteId")
        or feed.get("xsecToken")
        or feed.get("xsec_token")
        or note_card.get("displayTitle")
        or id(feed)
    )


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print_json({"event": "interrupted"})
        raise SystemExit(130)
    except Exception as exc:
        print_json({"event": "error", "error": str(exc)})
        raise SystemExit(1)
