"""Explicit paid reproduction in a temporary DB; never replay or overwrite the original task."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from pathlib import Path

from oj.config import Settings
from oj.database import Database
from oj.main import create_app
from oj.problem_store import ProblemStore
from oj.schemas import Problem


async def check(task_id: str) -> bool:
    settings = Settings()
    db = Database(settings.database_path)
    original = await db.fetchone("SELECT * FROM ai_tasks WHERE id=?", (task_id,))
    if original is None or original["target_section"] not in {"samples", "statement"}:
        raise RuntimeError("Select an existing section-edit task")
    draft = await db.fetchone("SELECT * FROM problem_drafts WHERE id=?", (original["draft_id"],))
    if draft:
        problem = Problem.model_validate_json(draft["problem_json"])
    else:
        problem = await ProblemStore(settings.problem_dir, settings.seed_problem_dir).get(
            original["problem_id"]
        )
    if problem is None:
        raise RuntimeError("Missing original problem")
    with tempfile.TemporaryDirectory(prefix="oj-section-check-") as directory:
        root = Path(directory)
        app = create_app(
            settings.model_copy(
                update={
                    "database_path": root / "test.db",
                    "problem_dir": root / "problems",
                    "seed_problem_dir": root / "seeds",
                }
            )
        )
        async with app.router.lifespan_context(app):
            manager = app.state.ai_authoring
            await manager.problems.create(problem)
            new_id = await manager.create(
                1,
                original["requirement"],
                problem.id,
                action="revise",
                target_section=original["target_section"],
            )
            task = manager.tasks.get(new_id)
            while task and not task.done():
                await asyncio.wait({task}, timeout=15)
                row = await manager.db.fetchone(
                    "SELECT stage,status FROM ai_tasks WHERE id=?", (new_id,)
                )
                print(json.dumps(dict(row)), flush=True)
            row = await manager.db.fetchone("SELECT * FROM ai_tasks WHERE id=?", (new_id,))
            result = json.loads(row["result"] or "{}")
            correct = None
            if problem.id == "brackets" and result.get("kind") == "section_patch":

                def expected(value: str) -> str:
                    stack: list[str] = []
                    for char in value.rstrip("\r\n"):
                        if char in "([":
                            stack.append(char)
                        elif not stack or stack.pop() != {")": "(", "]": "["}.get(char):
                            return "NO"
                    return "NO" if stack else "YES"

                correct = all(
                    expected(s["input"]) == s["output"].strip()
                    for s in result["problem"]["samples"]
                )
            print(
                json.dumps(
                    {
                        "status": row["status"],
                        "error": row["error"],
                        "cost": row["cost"],
                        "currency": row["currency"],
                        "usage": json.loads(row["usage_details"] or "{}"),
                        "sample_count": len(result.get("problem", {}).get("samples", [])),
                        "brackets_oracle_passed": correct,
                        "kind": result.get("kind"),
                        "reviewed": result.get("reviewed"),
                    }
                ),
                flush=True,
            )
            return (
                row["status"] == "completed"
                and bool(result.get("reviewed"))
                and correct is not False
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--paid", action="store_true", required=True)
    args = parser.parse_args()
    try:
        passed = asyncio.run(check(args.task_id))
    except Exception as exc:
        print(f"Check failed ({type(exc).__name__}); no original task was modified.")
        raise SystemExit(1) from None
    raise SystemExit(0 if passed else 1)
