"""Explicit paid acceptance against isolated data; no automatic replay of failed tasks."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

import httpx

from oj.config import Settings
from oj.main import create_app
from oj.schemas import Problem


async def check(
    output: Path,
    only: list[str] | None = None,
    revise_fixture: Path | None = None,
) -> None:
    settings = Settings()
    source = create_app(settings).state.ai_authoring
    config = await source.resolve_config(1)
    if not config:
        raise RuntimeError("No configured model")
    reports: list[dict[str, Any]] = []
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="oj-quality-acceptance-") as directory:
        root = Path(directory)
        app = create_app(
            settings.model_copy(
                update={
                    "database_path": root / "oj.db",
                    "problem_dir": root / "problems",
                    "seed_problem_dir": Path(__file__).parent.parent / "data" / "problem_seeds",
                }
            )
        )
        manager = app.state.ai_authoring
        config["encrypted_api_key"] = manager.cipher.encrypt(
            source.cipher.decrypt(config["encrypted_api_key"])
        )

        async def fixed_config(_: int) -> Any:
            return dict(config)

        manager.resolve_config = fixed_config
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client,
        ):
            login = await client.post(
                "/api/auth/login",
                json={
                    "username": "admin",
                    "password": "admintestpassword",
                },
            )
            login.raise_for_status()
            problem = Problem.model_validate(
                {
                    "id": "quality_sum",
                    "title": "整数求和验收",
                    "description": "计算 $a+b$。",
                    "input_description": "一行两个整数 $a,b$。",
                    "output_description": "输出和。",
                    "constraints": r"$-10^9 \le a,b \le 10^9$。",
                    "difficulty": "入门",
                    "tags": ["基础"],
                    "samples": [{"input": "1 2", "output": "3"}],
                    "testcases": [
                        {"input": "1 2", "output": "3"},
                        {"input": "0 0", "output": "0"},
                        {"input": "-2 3", "output": "1"},
                    ],
                }
            )
            await manager.problems.create(problem)
            code = "a,b=map(int,input().split());print(a+b)"
            wrong = "a,b=map(int,input().split());print(a-b)"
            sids = []
            for lang, value in [
                ("python", code),
                ("python", wrong),
                ("cpp", "int main( { return 0; }"),
            ]:
                sid = await app.state.submissions.create(1, problem.id, lang, value)
                await app.state.submissions.tasks[sid]
                sids.append(sid)
            chat = (
                await client.post("/api/ai/conversations/", json={"problem_id": problem.id})
            ).json()["data"]["id"]

            async def run(label: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
                reply = await client.post(
                    path, json=payload, headers={"Idempotency-Key": "quality-" + label}
                )
                reply.raise_for_status()
                task_id = reply.json()["data"]["task_id"]
                last = None
                while True:
                    task = (await client.get("/api/ai/problem-tasks/" + task_id)).json()["data"]
                    if task["stage"] != last:
                        print(label, task["stage"], flush=True)
                        last = task["stage"]
                    if task["status"] in ("completed", "failed", "cancelled"):
                        break
                    await asyncio.sleep(2)
                report = {
                    "name": label,
                    "status": task["status"],
                    "usage": task["usage"],
                    "error": task.get("error"),
                    "repair_used": task.get("repair_used"),
                    "result": task.get("result"),
                    "draft_id": task.get("draft_id"),
                }
                reports.append(report)
                await asyncio.to_thread(
                    output.write_text,
                    json.dumps(reports, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(
                    json.dumps({k: report[k] for k in ("name", "status", "usage", "repair_used")}),
                    flush=True,
                )
                return task

            if revise_fixture:
                saved = json.loads(
                    await asyncio.to_thread(revise_fixture.read_text, encoding="utf-8")
                )
                baseline = next(item["result"] for item in saved if item["name"] == "full")
                draft = await client.post(
                    "/api/problem-drafts/",
                    json={
                        "problem": baseline["problem"],
                        "reference_solution": baseline["reference_solution"],
                        "brute_solution": baseline["brute_solution"],
                        "generator_code": baseline["generator_code"],
                        "review": {
                            k: baseline[k] for k in ("review", "coverage", "wrong_solutions")
                        },
                    },
                )
                draft.raise_for_status()
                await run(
                    "revise_all",
                    "/api/ai/problem-tasks/",
                    {
                        "draft_id": draft.json()["data"]["id"],
                        "action": "revise",
                        "target_section": "all",
                        "requirement": (
                            "保留这道求和题语义，完善数学排版和测试覆盖并重新验证。保持简洁。"
                        ),
                        "workflow_version": 2,
                    },
                )
                return
            path = f"/api/ai/conversations/{chat}/messages"
            scenarios = [
                ("hint", "给一个简短提示，不要完整代码。", wrong, "python", None),
                (
                    "all_passed",
                    "解释当前代码和本次评测是否通过，说明复杂度。",
                    code,
                    "python",
                    sids[0],
                ),
                ("partial", "分析本次评测，指出代码中的问题。", wrong, "python", sids[1]),
                ("compile", "分析编译失败，如何修复？", "int main( { return 0; }", "cpp", sids[2]),
                (
                    "changed",
                    "我改了代码，现在还有问题吗？区分当前代码与原提交。",
                    wrong,
                    "python",
                    sids[0],
                ),
                (
                    "solution",
                    "继续前面的讨论，请给出完整 Python 题解和代码，使用数学公式解释。",
                    wrong,
                    "python",
                    sids[1],
                ),
            ]
            for label, message, value, lang, sid in scenarios:
                if only and label not in only:
                    continue
                await run(
                    label,
                    path,
                    {"message": message, "code": value, "language": lang, "submission_id": sid},
                )
            if only:
                return
            tasks_path = "/api/ai/problem-tasks/"
            for target, request in [
                ("statement", "润色题面，变量和复杂度用数学公式，保持原语义。"),
                ("samples", "完善三个简短样例，覆盖正数、零和负数。"),
                ("constraints", "保持约束范围不变，用规范 LaTeX 表达。"),
                ("testcases", "设计至少五个独特测试，覆盖正负数、零和边界，保持原语义。"),
                ("review", "仅审查语义、样例与数学排版，指出实际问题，不重写题目。"),
            ]:
                await run(
                    target,
                    tasks_path,
                    {
                        "problem_id": problem.id,
                        "action": "review" if target == "review" else "revise",
                        "target_section": target,
                        "requirement": request,
                        "workflow_version": 2,
                    },
                )
            full = await run(
                "full",
                tasks_path,
                {
                    "requirement": "生成简洁入门整数求和题，题号 quality_generated，"
                    "两个绝对值不超过10^9的整数，输出和。"
                    "题面和约束使用 Markdown 与 LaTeX。参考解直接相加；独立 oracle 使用内置 sum；"
                    "生成器输出20个独特小输入的JSON列表；错误解使用减法与绝对值和。边界测试含负数与零。",
                    "workflow_version": 2,
                },
            )
            if full["status"] == "completed":
                await run(
                    "revise_all",
                    tasks_path,
                    {
                        "draft_id": full["draft_id"],
                        "action": "revise",
                        "target_section": "all",
                        "requirement": (
                            "保留这道求和题语义，完善数学排版和测试覆盖并重新验证。保持简洁。"
                        ),
                        "workflow_version": 2,
                    },
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-paid", action="store_true", required=True)
    parser.add_argument("--output", type=Path, default=Path("var/quality-real-acceptance.json"))
    parser.add_argument("--revise-fixture", type=Path)
    parser.add_argument(
        "--only",
        nargs="+",
        choices=["hint", "all_passed", "partial", "compile", "changed", "solution"],
    )
    args = parser.parse_args()
    asyncio.run(check(args.output, args.only, args.revise_fixture))
