"""One interpretation of persisted judge results for the UI and the tutor."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from oj.database import Database

POINTS_PER_CASE = 10


def evaluation_summary(
    row: Mapping[str, Any], cases: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    status, score, maximum = row["status"], row["score"], row["counts"]
    total = (
        maximum // POINTS_PER_CASE
        if isinstance(maximum, int) and maximum >= 0 and maximum % POINTS_PER_CASE == 0
        else None
    )
    compile_info = row.get("compile_info")
    if isinstance(compile_info, str):
        try:
            compile_info = json.loads(compile_info)
        except ValueError:
            compile_info = None
    compile_failed = isinstance(compile_info, dict) and compile_info.get("result") == "error"
    compile_failed = compile_failed or any(c["result"] == "CE" for c in cases)
    executed = [c for c in cases if c["result"] != "CE"]
    counts = dict(Counter(str(c["result"]) for c in executed))
    passed = counts.get("AC", 0)
    complete = total is not None and len(executed) == total and not compile_failed
    consistent = complete and score == passed * POINTS_PER_CASE
    all_passed = bool(status == "success" and total and consistent and passed == total)
    if status == "pending":
        verdict = "pending"
    elif status == "error":
        verdict = "error"
    elif compile_failed:
        verdict = "CE"
    elif all_passed:
        verdict = "AC"
    elif total == 0 and not executed and score == 0:
        verdict = "empty"
    elif not consistent:
        verdict = "unknown"
    elif passed:
        verdict = "partial"
    else:
        verdict = next(iter(counts)) if len(counts) == 1 else "failed"
    known = bool(executed) or compile_failed or total == 0
    return {
        "status": status,
        "verdict": verdict,
        "score": score,
        "max_score": maximum,
        "executed_cases": len(executed) if known and status == "success" else None,
        "passed_cases": passed if known and status == "success" else None,
        "total_cases": total if status == "success" else None,
        "all_passed": all_passed,
        "result_counts": counts if status == "success" else {},
    }


async def evaluation_batch(db: Database, rows: Sequence[Any]) -> dict[int, dict[str, Any]]:
    """Read case aggregates once, regardless of how many submissions are listed."""
    if not rows:
        return {}
    ids = [row["id"] for row in rows]
    grouped: dict[int, list[dict[str, Any]]] = {key: [] for key in ids}
    # Chunk for SQLite parameter limits; metadata pagination remains O(1) queries per page.
    for offset in range(0, len(ids), 500):
        chunk = ids[offset : offset + 500]
        placeholders = ",".join("?" for _ in chunk)
        cases = await db.fetchall(
            "SELECT submission_id,result FROM submission_cases "  # noqa: S608
            f"WHERE submission_id IN ({placeholders})",  # noqa: S608
            chunk,
        )
        for case in cases:
            grouped[case["submission_id"]].append(dict(case))
    return {row["id"]: evaluation_summary(dict(row), grouped[row["id"]]) for row in rows}
