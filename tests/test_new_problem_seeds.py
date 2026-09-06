from __future__ import annotations

from pathlib import Path

from oj.judge import judge_code
from oj.schemas import Language, Problem

SEEDS = Path(__file__).parents[1] / "data" / "problem_seeds"

HOT_SEARCH_SOLUTION = r'''import sys
lines = sys.stdin.read().splitlines()
heat, banned, output = {}, set(), []
for line in lines[1:]:
    action, value = line.split()
    if action == "post" and value not in banned:
        heat[value] = heat.get(value, 0) + 1
    elif action == "delete":
        banned.add(value)
        heat.pop(value, None)
    elif action == "query":
        ranked = sorted(heat, key=lambda word: (-heat[word], word))[:int(value)]
        if ranked:
            output.extend([" ".join(ranked), str(sum(heat[word] for word in ranked))])
        else:
            output.extend(["EMPTY", "0"])
print("\n".join(output))
'''

STUDY_REPORT_SOLUTION = r'''import json
from datetime import datetime

filename = input()
start_date = datetime.strptime(input(), "%Y-%m-%d").date()
end_date = datetime.strptime(input(), "%Y-%m-%d").date()
stats = {}
with open(filename, encoding="utf-8") as source:
    for line in source:
        item = json.loads(line)
        start = datetime.strptime(item["start"], "%Y-%m-%d %H:%M")
        end = datetime.strptime(item["end"], "%Y-%m-%d %H:%M")
        if item["status"] != "done" or not start_date <= start.date() <= end_date:
            continue
        if end < start:
            continue
        minutes = int((end - start).total_seconds() / 60)
        row = stats.setdefault(item["student"], [0, 0, 0, set()])
        row[0] += 1
        row[1] += minutes
        row[2] = max(row[2], minutes)
        row[3].add(item["subject"])

rows = [f"Report: {start_date.strftime('%Y/%m/%d')} - {end_date.strftime('%Y/%m/%d')}"]
for name, row in sorted(
    stats.items(), key=lambda pair: (-pair[1][1], -pair[1][0], pair[0])
):
    rows.append(
        f"{name} | sessions={row[0]} | total={row[1]}min | "
        f"longest={row[2]}min | subjects={len(row[3])}"
    )
rows.append(f"TOTAL HOURS: {sum(row[1] for row in stats.values()) / 60:.2f}")
report = "\n".join(rows) + "\n"
with open("report.txt", "w", encoding="utf-8") as target:
    target.write(report)
with open("report.txt", encoding="utf-8") as target:
    print(target.read(), end="")
'''


async def test_new_problem_reference_solutions_pass_every_case() -> None:
    language = Language(
        name="python",
        file_ext=".py",
        run_cmd="python {src}",
        time_limit=5,
        memory_limit=128,
    )
    for problem_id, solution in (
        ("hot_search_ranking", HOT_SEARCH_SOLUTION),
        ("study_record_report", STUDY_REPORT_SOLUTION),
    ):
        problem = Problem.model_validate_json(
            (SEEDS / f"{problem_id}.json").read_text(encoding="utf-8")
        )
        result = await judge_code(problem, language, solution)
        assert result.score == result.counts
