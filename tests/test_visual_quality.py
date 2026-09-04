from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from oj.ai_presentation import check_presentation, presentation_issues
from oj.evaluation import evaluation_batch, evaluation_summary
from tests.test_ai_http import finish
from tests.test_ai_http import generated as generated  # noqa: F401
from tests.test_web_experience import configured, fake_phases


@pytest.mark.parametrize(
    ("status", "score", "maximum", "results", "verdict", "passed"),
    [
        ("success", 30, 30, ["AC"] * 3, "AC", 3),
        ("success", 20, 30, ["AC", "WA", "AC"], "partial", 2),
        ("success", 0, 30, ["WA"] * 3, "WA", 0),
        ("success", 0, 30, ["CE"], "CE", 0),
        ("success", 0, 0, [], "empty", 0),
        ("success", 30, 30, [], "unknown", None),
        ("success", 30, 30, ["AC", "WA", "AC"], "unknown", 2),
        ("success", 0, 5, [], "unknown", None),
        ("pending", None, None, [], "pending", None),
        ("error", None, None, [], "error", None),
        *[("success", 0, 10, [v], v, 0) for v in ("RE", "TLE", "MLE", "UNK")],
    ],
)
def test_evaluation_semantics(
    status: str,
    score: int | None,
    maximum: int | None,
    results: list[str],
    verdict: str,
    passed: int | None,
) -> None:
    result = evaluation_summary(
        {"status": status, "score": score, "counts": maximum, "compile_info": "malformed"},
        [{"result": r} for r in results],
    )
    assert result["verdict"] == verdict
    assert result["passed_cases"] == passed
    assert result["all_passed"] == (verdict == "AC")
    if verdict == "CE":
        assert result["executed_cases"] == 0
        assert result["total_cases"] == 3


def test_prose_checks_preserve_literal_assets() -> None:
    prose = r"$a_i^2$, $\frac{a}{b}$, $\sum_{i=1}^n i$ and $O(n \log n)$"
    check_presentation({"problem": {"description": prose, "samples": [{"input": "$"}]}})
    check_presentation({"description": "```python\nprint('$')\n```\n`$` and \\$5"})
    for bad in ["$x", "$x_{i$", "$x} {$", "\f rac", "$\times n$", "$$ x $"]:
        assert presentation_issues({"description": bad})
        with pytest.raises(ValueError):
            check_presentation({"problem": {"description": bad}})


async def test_summary_and_assistant_share_exact_evidence(
    client: AsyncClient,
    app: FastAPI,
    problem_payload: dict[str, Any],
) -> None:
    manager = await configured(client, app, problem_payload)
    db = app.state.db
    code = "print(sum(map(int,input().split())))"
    sid = await db.execute(
        "INSERT INTO submissions(user_id,problem_id,language,code,status,score,counts,"
        "compile_info,created_at,updated_at) VALUES(1,'sum_2','python',?,'success',30,30,"
        "NULL,'2026-09-04','2026-09-04')",
        (code,),
    )
    for i in range(1, 4):
        await db.execute(
            "INSERT INTO submission_cases VALUES(?,?, 'AC',0.01,1,'hidden sentinel')", (sid, i)
        )
    detail = (await client.get(f"/api/submissions/{sid}?include_metadata=true")).json()["data"]
    assert detail["evaluation"]["all_passed"]
    assert detail["evaluation"]["total_cases"] == 3
    listing = (await client.get("/api/submissions/?user_id=1&include_metadata=true")).json()["data"]
    assert listing["submissions"][0]["evaluation"] == detail["evaluation"]
    assert "evaluation" not in (await client.get(f"/api/submissions/{sid}")).json()["data"]
    assert await evaluation_batch(db, []) == {}
    seen = []

    async def complete(config: Any, prompt: str, usage: Any = None) -> Any:
        data = json.loads(prompt)
        seen.append(data)
        assert "hidden sentinel" not in prompt
        assert "testcases" not in data["problem"]
        assert "score/max_score are POINTS" in config["system_prompt"]
        assert "Markdown INSIDE JSON" in config["system_prompt"]
        assert data["submission"]["evaluation"] == detail["evaluation"]
        return "全部通过：$3/3$ 个测试点。", 10, 20, "provider"

    manager._stream_completion = complete
    chat = (await client.post("/api/ai/conversations/", json={"problem_id": "sum_2"})).json()[
        "data"
    ]["id"]
    path = f"/api/ai/conversations/{chat}/messages"
    for text in (code, "print(0)"):
        reply = await client.post(
            path,
            json={
                "message": "分析本次评测",
                "code": text,
                "language": "python",
                "submission_id": sid,
            },
        )
        await finish(manager, reply.json()["data"]["task_id"])
    assert seen[0]["submission"]["code_matches_current"] is True
    assert seen[1]["submission"]["code_matches_current"] is False
    assert seen[1]["submission"]["code"] == code
    assert seen[1]["history"][0]["same_as_current_code"] is False


@pytest.mark.parametrize("repair_succeeds", [True, False])
async def test_section_math_repair_is_bounded(
    client: AsyncClient,
    app: FastAPI,
    problem_payload: dict[str, Any],
    repair_succeeds: bool,
) -> None:
    manager = await configured(client, app, problem_payload)
    manager.settings.ai_section_max_output_tokens = 16384
    calls = []

    async def complete(config: Any, prompt: str, usage: Any = None) -> Any:
        calls.append(config)
        assert config["max_output_tokens"] == 16384
        text = r"$1 \le n \le 10^5$" if len(calls) == 3 and repair_succeeds else "$n_{"
        return json.dumps({"constraints": text, "review": "检查范围。"}), 5, 10, "provider"

    manager._stream_completion = complete
    reply = await client.post(
        "/api/ai/problem-tasks/",
        json={
            "problem_id": "sum_2",
            "action": "revise",
            "target_section": "constraints",
            "requirement": "保持约束语义并规范数学公式排版",
            "workflow_version": 2,
        },
    )
    tid = reply.json()["data"]["task_id"]
    await finish(manager, tid)
    task = (await client.get(f"/api/ai/problem-tasks/{tid}")).json()["data"]
    assert len(calls) == 3
    assert task["repair_used"]
    assert task["status"] == ("completed" if repair_succeeds else "failed")


async def test_misnested_reference_is_recovered_before_review(
    client: AsyncClient,
    app: FastAPI,
    problem_payload: dict[str, Any],
    generated: dict[str, Any],
) -> None:
    manager = await configured(client, app, problem_payload)
    calls = fake_phases(manager, generated)
    original = manager._stream_completion

    async def misplaced(config: Any, prompt: str, usage: Any = None) -> Any:
        text, *tokens = await original(config, prompt, usage)
        if "Stage 1:" in config["system_prompt"]:
            value = json.loads(text)
            value["problem"]["reference_solution"] = value.pop("reference_solution")
            value["problem"]["unwanted"] = "model-only key"
            text = json.dumps(value)
        return text, *tokens

    manager._stream_completion = misplaced
    reply = await client.post(
        "/api/ai/problem-tasks/",
        json={
            "requirement": "生成一道简单的整数求和题，验证阶段结构恢复。",
            "workflow_version": 2,
        },
    )
    tid = reply.json()["data"]["task_id"]
    await finish(manager, tid)
    task = (await client.get(f"/api/ai/problem-tasks/{tid}")).json()["data"]
    assert task["status"] == "completed", task.get("error")
    assert len(calls) == 3
    assert "reference_solution" not in task["result"]["problem"]
