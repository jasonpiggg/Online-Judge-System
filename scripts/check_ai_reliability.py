"""Three isolated paid AI checks with a conservative cumulative CNY ceiling."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from oj.ai_authoring import AuthoringError
from oj.ai_prompts import DISPLAY_RULES
from oj.config import Settings
from oj.difficulty import DIFFICULTY_RULES
from oj.main import create_app


async def check(report_path: Path) -> None:
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
    reserved = 0.0
    if await asyncio.to_thread(report_path.exists):
        previous = json.loads(await asyncio.to_thread(report_path.read_text, encoding="utf-8"))
        reserved = float(previous["reserved_cny"])
        reports.extend(previous["tasks"])
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
                await asyncio.to_thread(
                    report_path.write_text,
                    json.dumps(
                        {"reserved_cny": round(reserved, 6), "tasks": reports},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
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
                            "generation_mode": "basic_draft",
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

            first = await run(
                "generate",
                {
                    "requirement": (
                        "生成简单括号匹配题，仅包含小括号，判断是否合法，长度1到100。"
                        "提供简洁题面、参考解、8个针对性小测试。"
                    ),
                    "action": "generate",
                    "target_section": "all",
                    "workflow_version": 2,
                    "generation_mode": "basic_draft",
                },
            )
            if first["row"]["status"] != "completed":
                raise RuntimeError("Generation failed; dependent checks were not charged")
            draft_id = first["row"]["draft_id"]
            await run(
                "review",
                {
                    "requirement": "全面审查当前草稿，只修正已有内容，不补写缺失资产。",
                    "draft_id": draft_id,
                    "action": "review",
                    "target_section": "all",
                    "workflow_version": 2,
                    "generation_mode": "full",
                },
            )
            await run(
                "complete-assets",
                {
                    "requirement": (
                        "保持题面和参考解，补全独立解法、20个小随机输入的生成器、"
                        "8到12个测试点、两个可运行且会被卡错的错误解，并验证。"
                    ),
                    "draft_id": draft_id,
                    "action": "generate",
                    "target_section": "all",
                    "workflow_version": 2,
                    "generation_mode": "full",
                },
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paid", action="store_true", required=True)
    parser.add_argument("--report", type=Path, default=Path("tmp/ai-reliability-report.json"))
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(check(args.report))
    except Exception as exc:
        print(f"Benchmark stopped ({type(exc).__name__}); no credentials printed.")
        raise SystemExit(1) from None
