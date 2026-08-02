from __future__ import annotations

import argparse
import json
from pathlib import Path

import cli

ROOT_DIR = Path(__file__).resolve().parent.parent
MATRIX_PATH = ROOT_DIR / "tests" / "fixtures" / "skill-regression-cases.json"


def test_skill_regression_matrix_has_complete_cases() -> None:
    cases = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    parser = cli.build_parser()
    commands = next(
        action.choices
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )

    expected_prompts = {
        "搜索笔记并总结",
        "直接发布这组图片",
        "取消发布",
        "批量点赞 30 条",
        "检查登录并扫码",
        "分析竞品",
        "研究某话题后发布",
    }
    assert {case["prompt"] for case in cases} == expected_prompts

    for case in cases:
        assert case["skill"].startswith("xhs-")
        assert case["requires_bridge"] is True
        assert case["stop_condition"]
        assert set(case["allowed_commands"]) <= set(commands)
