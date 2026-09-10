"""Six explicitly paid, isolated AI checks with a conservative CNY reservation ceiling."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from oj.ai.authoring import AuthoringError, utcnow
from oj.ai.prompts import DISPLAY_RULES
from oj.config import Settings
from oj.difficulty import DIFFICULTY_RULES
from oj.main import create_app
from oj.schemas import Problem


async def check(report_path: Path, balanced: bool = False) -> None:
    original = Settings()
    if (
        original.ai_default_model != "glm-5.3-flash"
        or original.ai_default_currency != "CNY"
        or original.ai_default_input_price <= 0
        or original.ai_default_output_price <= 0
        or original.ai_routing_enabled
        or original.ai_default_reasoning_effort != "low"
    ):
        raise RuntimeError("Known Flash CNY pricing and low/no-routing configuration required")
    reports: list[dict[str, Any]] = []
    reserved = 0.316822 if balanced else 0.0  # Include the entire first run reservation.
    with tempfile.TemporaryDirectory(prefix="oj-basic-benchmark-") as folder:
        root = Path(folder)
        settings = original.model_copy(
            update={
                "database_path": root / "probe.db",
                "problem_dir": root / "problems",
                "seed_problem_dir": root / "seeds",
            }
        )
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            manager = app.state.ai_authoring
            transport = manager._stream_completion

            async def limited(config: Any, prompt: str, on_usage: Any = None) -> Any:
                nonlocal reserved
                if (
                    config["model"] not in {"glm-5.3-flash", "glm-5.3"}
                    or config["currency"] != "CNY"
                ):
                    raise AuthoringError("Benchmark rejected an unbudgeted model")
                if config["input_price"] <= 0 or config["output_price"] <= 0:
                    raise AuthoringError("Benchmark requires known positive prices")
                # UTF-8 bytes bound input tokens conservatively; include injected rules and framing.
                input_bound = (
                    len(
                        (
                            prompt + config["system_prompt"] + DISPLAY_RULES + DIFFICULTY_RULES
                        ).encode()
                    )
                    + 4096
                )
                output_bound = config["max_output_tokens"]
                estimate = (
                    input_bound * config["input_price"] + output_bound * config["output_price"]
                ) / config["price_unit"]
                if reserved + estimate > 5:
                    raise AuthoringError("Benchmark's 5 CNY reservation ceiling reached")
                reserved += estimate  # Never refund reservations, including failed calls.
                return await transport(config, prompt, on_usage)

            manager._stream_completion = limited

            async def run(label: str, body: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
                start = time.monotonic()
                tid = await manager.create_request(1, body, **kwargs)
                task = manager.tasks.get(tid)
                if task:
                    await task
                row = await manager.db.fetchone("SELECT * FROM ai_tasks WHERE id=?", (tid,))
                result = json.loads(row["result"] or "{}")
                report = {
                    "case": label,
                    "status": row["status"],
                    "elapsed_seconds": round(time.monotonic() - start, 3),
                    "input_tokens": row["input_tokens"],
                    "output_tokens": row["output_tokens"],
                    "cost_cny": row["cost"],
                    "usage_source": row["usage_source"],
                    "verification": result.get("verification"),
                    "phases": json.loads(row["usage_details"] or "{}").get("phases", {}),
                    "error": row["error"],
                }
                reports.append(report)
                await asyncio.to_thread(
                    report_path.write_text,
                    json.dumps(
                        {
                            "model": original.ai_default_model,
                            "generation_mode": "balanced" if balanced else "basic_draft",
                            "reserved_cny": round(reserved, 6),
                            "tasks": reports,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                print(
                    json.dumps(
                        {
                            k: report[k]
                            for k in ("case", "status", "elapsed_seconds", "cost_cny", "error")
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                return {"row": row, "result": result}

            cases = [
                (
                    "beginner-addition",
                    "生成入门整数加法题：输入两个绝对值不超过一百万的整数，输出和。",
                ),
                (
                    "easy-brackets",
                    "生成简单括号匹配题，仅包含小括号，判断是否合法，字符串长度不超过100。",
                ),
                (
                    "medium-shortest-path",
                    "生成中等无权无向图最短路题，最多30个点60条边，输出从1到n的距离，不可达输出-1。",
                ),
                (
                    "hard-knapsack",
                    "生成困难分组背包题，每组最多选一个物品，容量最多100，组数最多8，每组最多5个物品。",
                ),
            ]
            basic = []
            for label, requirement in cases:
                basic.append(
                    await run(
                        label,
                        {
                            "requirement": requirement
                            + " 提供简洁中文题面、Python参考解及5到8个小规模测试点。",
                            "action": "generate",
                            "target_section": "all",
                            "workflow_version": 2,
                            "generation_mode": "balanced" if balanced else "basic_draft",
                        },
                    )
                )
            if balanced:
                return  # Exactly four additional tasks; no dependent paid calls.
            first = next((b for b in basic if b["row"]["status"] == "completed"), None)
            if first:
                problem = Problem.model_validate(first["result"]["problem"])
                await manager.problems.create(problem)  # Isolated store only, never production.
                await manager.db.execute(
                    "INSERT INTO ai_conversations(id,user_id,problem_id,created_at) "
                    "VALUES(?,1,?,?)",
                    ("benchmark-chat", problem.id, utcnow()),
                )
                await run(
                    "assistant",
                    {
                        "problem_id": problem.id,
                        "message": "请给一个简洁的渐进提示，不要直接给完整代码。",
                        "code": "",
                        "language": "python",
                        "full_solution": False,
                    },
                    kind="assistant",
                    conversation_id="benchmark-chat",
                )
                await run(
                    "complete-assets",
                    {
                        "requirement": (
                            "保留题面和参考解，补充独立解、20组小规模随机输入的生成器"
                            "及两个可执行错误解，完成验证。"
                        ),
                        "draft_id": first["row"]["draft_id"],
                        "action": "generate",
                        "target_section": "all",
                        "workflow_version": 2,
                        "generation_mode": "full",
                    },
                )
            else:
                print("No successful basic draft; dependent assistant/completion checks skipped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paid", action="store_true", required=True)
    parser.add_argument("--balanced", action="store_true")
    parser.add_argument("--report", type=Path, default=Path("tmp/basic-ai-report.json"))
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(check(args.report, args.balanced))
    except Exception as exc:
        print(f"Benchmark stopped ({type(exc).__name__}); no credentials printed.")
        raise SystemExit(1) from None
