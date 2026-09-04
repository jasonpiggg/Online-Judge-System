"""Deterministic routing: no extra paid classifier, no automatic paid retries."""

from __future__ import annotations

import json
import re
from typing import Any

from oj.config import Settings


def environment_policy(settings: Settings) -> str:
    if settings.ai_routing_enabled and not settings.ai_quality_model.strip():
        raise RuntimeError("AI routing requires OJ_AI_QUALITY_MODEL")
    return json.dumps(
        {
            "enabled": settings.ai_routing_enabled,
            "default_reasoning_effort": settings.ai_default_reasoning_effort,
            "default_json_mode": settings.ai_default_json_mode,
            "quality": {
                "model": settings.ai_quality_model,
                "input_price": settings.ai_quality_input_price,
                "output_price": settings.ai_quality_output_price,
                "cached_input_price": settings.ai_quality_cached_input_price,
                "reasoning_effort": settings.ai_quality_reasoning_effort,
                "json_mode": settings.ai_quality_json_mode,
            },
        }
    )


def select_phase_config(
    base: dict[str, Any],
    phase: str,
    action: str,
    target: str,
    requirement: str,
    context: str = "",
) -> dict[str, Any]:
    config = dict(base)
    config.update(tier="personal", routing_reason="个人配置覆盖系统策略")
    if base["config_source"] == "personal":
        return config
    policy = json.loads(base.get("routing_config") or "{}")
    config["json_mode"] = policy.get("default_json_mode", True)
    if policy.get("default_reasoning_effort"):
        config["reasoning_effort"] = policy["default_reasoning_effort"]
    config.update(tier="default", routing_reason="系统未启用分流")
    if not policy.get("enabled"):
        return config
    content = (requirement + " " + context).lower()
    hard = re.search(
        r"困难|挑战|难题|复杂|高质量|竞赛|提高|动态规划|图论|最短路|网络流|线段树|证明|"
        r"hard|expert|advanced|complex|dynamic.programming|graph|segment.tree|proof|"
        r"数论|莫比乌斯|持久化|树形|树链|博弈|计算几何|number.theory|\bdp\b",
        content,
    )
    easy = re.search(r"入门|简单|基础|新手|easy|beginner|basic|a\s*\+\s*b", content)
    if phase == "critique":
        reason = "最终完整复审使用高质量模型"
    elif action in {"review", "tests"} or target in {"review", "testcases", "constraints"}:
        reason = "审核、测试覆盖或约束修改需要算法推理"
    elif hard:
        reason = "命题需求或原题含复杂算法/高难度信号"
    elif (action == "revise" and target in {"statement", "samples"}) or (
        action == "generate" and easy
    ):
        config.update(tier="flash", routing_reason="入门题初稿或局部题面/样例修改")
        return config
    else:
        reason = "难度不明确或涉及算法修改，保守选择高质量模型"
    # Currency and unit are shared; credentials remain the encrypted system credential.
    config.update(policy["quality"])
    config.update(tier="quality", routing_reason=reason)
    return config


def public_pricing(config: dict[str, Any]) -> dict[str, Any]:
    return {
        key: config.get(key)
        for key in (
            "input_price",
            "output_price",
            "cached_input_price",
            "price_unit",
            "currency",
        )
    }
