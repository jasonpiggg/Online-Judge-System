"""One paid end-to-end authoring check in an isolated temporary database; no retries."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from oj.config import Settings
from oj.database import Database
from oj.judge import judge_code
from oj.languages import get_language
from oj.main import create_app
from oj.schemas import GeneratedProblem, TestCase


async def check(source_task_id: str | None = None) -> bool:
    requirement = (
        "Create an easy beginner A+B integer addition problem, two signed integers "
        "on one line, each within [-1000000000, 1000000000]. Keep all descriptions "
        "concise and all literal test inputs short. Use Python built-in sum as the "
        "independent oracle. Supply a deterministic generator of 20 unique inputs, "
        "and two executable wrong algorithms: subtraction and sum of absolute values. "
        "This is an O(1) task; do not invent larger-scale array inputs or extra features."
    )
    if source_task_id:
        db = Database(Settings().database_path)
        original = await db.fetchone("SELECT * FROM ai_tasks WHERE id=?", (source_task_id,))
        if original is None or original["action"] != "generate" or original["problem_id"]:
            raise RuntimeError("Select a standalone full generation task")
        requirement = original["requirement"]
    with tempfile.TemporaryDirectory(prefix="oj-authoring-check-") as directory:
        root = Path(directory)
        settings = Settings().model_copy(
            update={
                "database_path": root / "probe.db",
                "problem_dir": root / "problems",
                "seed_problem_dir": root / "seeds",
            }
        )
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            manager = app.state.ai_authoring
            task_id = await manager.create(
                1,
                requirement,
                None,
            )
            task = manager.tasks.get(task_id)
            while task and not task.done():
                await asyncio.wait({task}, timeout=15)
                row = await manager.db.fetchone(
                    "SELECT stage,status,input_tokens,output_tokens FROM ai_tasks WHERE id=?",
                    (task_id,),
                )
                print(json.dumps(dict(row)), flush=True)
            row = await manager.db.fetchone("SELECT * FROM ai_tasks WHERE id=?", (task_id,))
            result = json.loads(row["result"] or "{}")
            verification = result.get("verification", {})
            if row["status"] == "failed" and result.get("generator_code"):
                generated = GeneratedProblem.model_validate(result)
                language = await get_language(manager.db, "python")
                harness = generated.problem.model_copy(
                    update={
                        "time_limit": 3.0,
                        "memory_limit": 128,
                        "testcases": [TestCase(input="", output="")],
                    }
                )
                outcome = await judge_code(harness, language, generated.generator_code)
                print(
                    json.dumps(
                        {
                            "generator_diagnostic": {
                                "time_limit": harness.time_limit,
                                "memory_limit": harness.memory_limit,
                                "code": generated.generator_code,
                                "cases": [asdict(case) for case in outcome.cases],
                            }
                        }
                    ),
                    flush=True,
                )
            print(
                json.dumps(
                    {
                        "status": row["status"],
                        "error": row["error"],
                        "cost": row["cost"],
                        "currency": row["currency"],
                        "usage_details": json.loads(row["usage_details"] or "{}"),
                        "verification": verification,
                    }
                ),
                flush=True,
            )
            return row["status"] == "completed" and bool(verification.get("quality_gate_passed"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", help="Copy a full task's requirement into the temporary check")
    parser.add_argument(
        "--paid",
        action="store_true",
        required=True,
        help="Authorize two real provider calls using the server configuration",
    )
    args = parser.parse_args()
    try:
        passed = asyncio.run(check(args.task_id))
    except Exception as exc:
        print(f"Check failed ({type(exc).__name__}); server credentials are not printed.")
        raise SystemExit(1) from None
    raise SystemExit(0 if passed else 1)
