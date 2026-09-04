from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

from frontend.client import ApiClient
from oj.ai_authoring import AIAuthoringManager
from oj.ai_sections import merge_section
from oj.config import Settings
from oj.schemas import GeneratedProblem, Problem
from tests.test_ai_http import configure, finish, provider


@pytest.mark.parametrize("target", ["samples", "statement"])
async def test_scoped_http_edit_preserves_unrelated_fields(
    app: FastAPI,
    problem_payload: dict[str, Any],
    target: str,
) -> None:
    manager = app.state.ai_authoring
    base = Problem.model_validate(problem_payload)
    await manager.problems.create(base)
    patch = (
        {"samples": [{"input": "3 4\n", "output": "7\n"}], "review": "验证样例输出为两数之和"}
        if target == "samples"
        else {
            "title": "更明确的标题",
            "description": base.description,
            "input_description": base.input_description,
            "output_description": base.output_description,
            "review": "仅修改标题措辞",
        }
    )
    async with provider(patch) as (url, calls, _):
        await configure(manager, url)
        row = await finish(
            manager,
            await manager.create(
                1, "补充小规模展示样例让题意更清晰", base.id, action="revise", target_section=target
            ),
        )
    assert row["status"] == "completed", row["error"]
    assert len(calls) == 2
    assert all(call["max_tokens"] == 8192 for call in calls)
    assert "testcases" not in calls[0]["messages"][1]["content"]
    assert "Return the COMPLETE" not in calls[1]["messages"][1]["content"]
    result = json.loads(row["result"])
    assert result["kind"] == "section_patch" and result["reviewed"]
    assert not result["verification"]["quality_gate_passed"]
    assert result["problem"]["testcases"] == base.model_dump()["testcases"]
    assert result["problem"]["constraints"] == base.constraints
    assert (await manager.problems.get(base.id)) == base  # Suggestions are not auto-published.


def test_scoped_patch_rejects_overwrite_and_huge_samples(problem_payload: dict[str, Any]) -> None:
    base = Problem.model_validate(problem_payload)
    patch = {"samples": [{"input": "1 2\n", "output": "3\n"}], "review": "explanation"}
    with pytest.raises(ValidationError):
        merge_section(base, "samples", {**patch, "testcases": []})
    with pytest.raises(ValidationError):
        merge_section(
            base, "samples", {**patch, "samples": [{"input": "(" * 100000, "output": "NO"}]}
        )
    with pytest.raises(ValidationError):
        merge_section(base, "samples", {**patch, "samples": patch["samples"] * 2})


async def test_scoped_review_failure_keeps_first_draft(
    app: FastAPI,
    problem_payload: dict[str, Any],
    monkeypatch: Any,
) -> None:
    manager = app.state.ai_authoring
    await configure(manager, "http://127.0.0.1:9999/v1")
    base = Problem.model_validate(problem_payload)
    await manager.problems.create(base)
    calls = []

    async def stream(config: Any, prompt: str, callback: Any) -> Any:
        calls.append(config)
        await callback(10, 20, "provider")
        if len(calls) == 2:
            raise TimeoutError
        return (
            json.dumps({"samples": [{"input": "2 3\n", "output": "5\n"}], "review": "新增样例"}),
            10,
            20,
            "provider",
        )

    monkeypatch.setattr(manager, "_stream_completion", stream)
    row = await finish(
        manager,
        await manager.create(
            1, "增加一些清晰的输入输出示例", base.id, action="revise", target_section="samples"
        ),
    )
    assert row["status"] == "failed" and len(calls) == 2
    result = json.loads(row["result"])
    assert result["kind"] == "section_patch" and not result["reviewed"]
    assert row["input_tokens"] == 20 and row["output_tokens"] == 40


async def test_missing_base_never_calls_paid_model(app: FastAPI, monkeypatch: Any) -> None:
    manager = app.state.ai_authoring
    await configure(manager, "http://127.0.0.1:9999/v1")
    monkeypatch.setattr(manager, "_stream_completion", lambda *_: pytest.fail("paid call"))
    row = await finish(
        manager,
        await manager.create(
            1, "增加一些清晰的输入输出示例", None, action="revise", target_section="samples"
        ),
    )
    assert row["status"] == "failed" and row["cost"] == 0


async def test_truncated_output_can_be_recovered(app: FastAPI) -> None:
    manager = app.state.ai_authoring
    async with provider({"partial": "useful fragment"}, mode="truncated") as (url, calls, _):
        await configure(manager, url)
        row = await finish(manager, await manager.create(1, "创建题目并模拟输出截断问题", None))
    assert row["status"] == "failed" and len(calls) == 1
    result = json.loads(row["result"])
    assert result["kind"] == "incomplete_output"
    assert "useful fragment" in result["text"]


@pytest.mark.parametrize("kind", ["section_patch", "incomplete_output"])
def test_frontend_retained_outputs_and_explicit_retry(
    monkeypatch: Any,
    problem_payload: dict[str, Any],
    kind: str,
) -> None:
    result = {"kind": "incomplete_output", "text": "incomplete JSON"}
    if kind == "section_patch":
        result = merge_section(
            Problem.model_validate(problem_payload),
            "samples",
            {
                "samples": [{"input": "2 3\n", "output": "5\n"}],
                "review": "补充样例",
            },
        )
    data = {
        "task_id": "test",
        "status": "failed",
        "progress": "复审失败",
        "requirement": "补充一些清晰的输入输出样例",
        "action": "revise",
        "target_section": "samples",
        "result": result,
        "error": "test",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 20,
            "cost": 0.01,
            "currency": "CNY",
            "source": "provider",
        },
    }
    calls = []

    def request(_self: Any, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        calls.append((method, path))
        return {"code": 200, "data": data}

    monkeypatch.setattr(ApiClient, "request", request)
    page = AppTest.from_string("""
import streamlit as st
from frontend.ai import task_panel
from frontend.client import ApiClient
st.session_state['ai-terminal-test'] = True
task_panel(ApiClient(), 'test')
""").run()
    assert not page.exception
    assert all(method == "GET" for method, _ in calls)
    assert next(b for b in page.button if b.label == "创建新的修改任务").disabled
    if kind == "section_patch":
        assert next(b for b in page.button if b.label == "载入局部修改到编辑器").disabled
        assert any("复审尚未通过" in message.value for message in page.warning)


@pytest.mark.parametrize("malformed", ["bad_key", "bad_json", "bad_final"])
async def test_existing_critique_repairs_invalid_first_draft(
    app: FastAPI,
    problem_payload: dict[str, Any],
    monkeypatch: Any,
    malformed: str,
) -> None:
    manager = app.state.ai_authoring
    await configure(manager, "http://127.0.0.1:9999/v1")
    base = Problem.model_validate(problem_payload)
    await manager.problems.create(base)
    calls = []
    bad = json.dumps({"samples": [{"input(": "1 2\n", "output": "3\n"}], "review": "typo"})
    if malformed == "bad_json":
        bad = '{"samples":['

    async def stream(config: Any, prompt: str, callback: Any) -> Any:
        calls.append(prompt)
        await callback(10, 20, "provider")
        if len(calls) == 1 or malformed == "bad_final":
            return bad, 10, 20, "provider"
        return (
            json.dumps(
                {
                    "samples": [{"input": "1 2\n", "output": "3\n"}],
                    "review": "字段已修正且样例满足输入约束",
                }
            ),
            10,
            20,
            "provider",
        )

    monkeypatch.setattr(manager, "_stream_completion", stream)
    row = await finish(
        manager,
        await manager.create(
            1, "请补充一些易于理解的样例", base.id, action="revise", target_section="samples"
        ),
    )
    assert len(calls) == 2  # Repair replaces planned review, not an unbounded paid retry loop.
    assert "Local schema feedback" in calls[1]
    assert "input(" in calls[1] or "Malformed JSON" in calls[1]
    assert row["status"] == ("failed" if malformed == "bad_final" else "completed")
    assert row["output_tokens"] == 40


def test_expanded_but_finite_budgets() -> None:
    settings = Settings(
        _env_file=None,
        ai_max_output_tokens=65536,
        ai_section_max_output_tokens=16384,
        ai_stage_timeout_seconds=900,
        ai_task_timeout_seconds=2400,
        ai_stream_read_timeout_seconds=180,
    )
    assert settings.ai_stage_timeout_seconds == 900
    for overrides in [
        {"ai_stage_timeout_seconds": 1801},
        {"ai_task_timeout_seconds": 7201},
        {"ai_stream_read_timeout_seconds": 601},
    ]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **overrides)


def test_syntax_feedback_does_not_execute_model_code(problem_payload: dict[str, Any]) -> None:
    payload = dict(problem_payload)
    payload["testcases"] = [{"input": f"{i} 0\n", "output": f"{i}\n"} for i in range(5)]
    draft = GeneratedProblem.model_validate(
        {
            "problem": payload,
            "reference_solution": "raise RuntimeError('must never execute')",
            "brute_solution": "print(0)",
            "generator_code": "import \nprint(.dumps([]))",
            "review": "syntax check",
            "coverage": {"basic": "basic cases", "boundary": "edge cases", "scale": "scale cases"},
            "wrong_solutions": [
                {"code": "print(0)", "reason": "always prints zero"},
                {"code": "print(1)", "reason": "always prints one"},
            ],
        }
    )
    issues = AIAuthoringManager._syntax_issues(draft)
    assert "generator_code: SyntaxError" in issues
    assert "reference_solution" not in issues
