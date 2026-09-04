from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from oj.database import Database
from oj.judge import JudgeOutcome, judge_code
from oj.languages import get_language
from oj.problem_store import ProblemStore


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SubmissionManager:
    def __init__(self, db: Database, problems: ProblemStore) -> None:
        self.db = db
        self.problems = problems
        self.tasks: dict[int, asyncio.Task[None]] = {}
        self.intake_lock = asyncio.Lock()

    async def create(self, user_id: int, problem_id: str, language: str, code: str) -> int:
        now = now_iso()
        submission_id = await self.db.execute(
            """INSERT INTO submissions
               (user_id,problem_id,language,code,status,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?)""",
            (user_id, problem_id, language, code, "pending", now, now),
        )
        self.schedule(submission_id)
        return submission_id

    def schedule(self, submission_id: int) -> None:
        previous = self.tasks.get(submission_id)
        if previous and not previous.done():
            previous.cancel()
        task = asyncio.create_task(self._evaluate(submission_id))
        self.tasks[submission_id] = task
        task.add_done_callback(
            lambda finished: (
                self.tasks.pop(submission_id, None)
                if self.tasks.get(submission_id) is finished
                else None
            )
        )

    async def recover(self) -> None:
        rows = await self.db.fetchall("SELECT id FROM submissions WHERE status='pending'")
        for row in rows:
            self.schedule(row["id"])

    async def close(self) -> None:
        running = list(self.tasks.values())
        if not running:
            return
        _done, pending = await asyncio.wait(running, timeout=5)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def cancel_all(self) -> None:
        running = list(self.tasks.values())
        for task in running:
            task.cancel()
        if running:
            await asyncio.gather(*running, return_exceptions=True)

    async def cancel_one(self, submission_id: int) -> None:
        task = self.tasks.get(submission_id)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _evaluate(self, submission_id: int) -> None:
        try:
            row = await self.db.fetchone("SELECT * FROM submissions WHERE id=?", (submission_id,))
            if row is None:
                return
            problem = await self.problems.get(row["problem_id"])
            language = await get_language(self.db, row["language"])
            if problem is None or language is None:
                raise RuntimeError("submission dependency no longer exists")
            outcome = await judge_code(problem, language, row["code"])
            await self._save_outcome(submission_id, outcome)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.db.execute(
                """UPDATE submissions SET status='error', error_info=?, updated_at=?
                   WHERE id=?""",
                ("judge infrastructure error", now_iso(), submission_id),
            )

    async def _save_outcome(self, submission_id: int, outcome: JudgeOutcome) -> None:
        async with self.db.connect() as db:
            await db.execute("DELETE FROM submission_cases WHERE submission_id=?", (submission_id,))
            await db.executemany(
                """INSERT INTO submission_cases
                   (submission_id,case_id,result,time,memory,message) VALUES(?,?,?,?,?,?)""",
                [
                    (
                        submission_id,
                        case.id,
                        case.result,
                        case.time,
                        case.memory,
                        case.message,
                    )
                    for case in outcome.cases
                ],
            )
            await db.execute(
                """UPDATE submissions SET status='success',score=?,counts=?,compile_info=?,
                   run_info=?,error_info=?,updated_at=? WHERE id=?""",
                (
                    outcome.score,
                    outcome.counts,
                    json.dumps(outcome.compile_info, ensure_ascii=False),
                    json.dumps(outcome.run_info, ensure_ascii=False),
                    outcome.error_info,
                    now_iso(),
                    submission_id,
                ),
            )
            await db.commit()


def detail_from_row(row: object, include_metadata: bool = False) -> dict[str, object]:
    status = row["status"]  # type: ignore[index]
    data: dict[str, object] = {
        "submission_id": str(row["id"]),  # type: ignore[index]
        "status": status,
    }
    if include_metadata:
        for name in (
            "user_id", "problem_id", "language", "created_at", "code", "problem_deleted"
        ):
            data[name] = (
                bool(row[name]) if name == "problem_deleted" else row[name]  # type: ignore[index]
            )
    if status == "success":
        data.update(
            score=row["score"],  # type: ignore[index]
            counts=row["counts"],  # type: ignore[index]
            compile_info=json.loads(row["compile_info"]) if row["compile_info"] else None,  # type: ignore[index]
            run_info=json.loads(row["run_info"]) if row["run_info"] else None,  # type: ignore[index]
            error_info=row["error_info"] or "",  # type: ignore[index]
        )
    elif status == "error":
        data["error_info"] = row["error_info"] or "judge infrastructure error"  # type: ignore[index]
    return data


def summary_from_row(row: object, include_metadata: bool = False) -> dict[str, object]:
    detail = detail_from_row(row, include_metadata)
    keys = {"submission_id", "status", "score", "counts"}
    if include_metadata:
        keys.update({"user_id", "problem_id", "language", "created_at", "problem_deleted"})
    return {key: value for key, value in detail.items() if key in keys}
