from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from oj.judge import JUDGE_ENV, judge_code
from oj.schemas import Language, Problem
from scripts.build_exam_seed_bank import materialize, specs

SEEDS = Path(__file__).parents[1] / "data" / "problem_seeds"
LEVELS = ("入门", "简单", "中等", "困难", "挑战")


def test_exam_seed_bank_has_expected_ids_levels_and_oracle_outputs() -> None:
    expected = specs()
    assert len(expected) == len({item.id for item in expected}) == 33
    loaded = {
        item.id: item
        for item in (
            Problem.model_validate_json(path.read_text(encoding="utf-8"))
            for path in SEEDS.glob("*.json")
        )
    }
    for spec in expected:
        assert spec.id in loaded
        serialized = json.loads((SEEDS / f"{spec.id}.json").read_text(encoding="utf-8"))
        assert serialized == materialize(spec)
    counts = Counter(loaded[item.id].difficulty for item in expected)
    assert {level: counts[level] for level in LEVELS} == {level: 5 for level in LEVELS}


def test_mock_sets_have_four_questions_and_ten_cases_each() -> None:
    mock = [item for item in specs() if item.source.startswith("程序设计训练期末模拟卷")]
    assert Counter(item.source for item in mock) == {
        "程序设计训练期末模拟卷 A": 4,
        "程序设计训练期末模拟卷 B": 4,
    }
    assert all(len(item.inputs) == 10 for item in mock)


def test_scientific_runtime_supports_numpy_and_pandas_reference_operations() -> None:
    points = np.asarray([[0, 0], [2, 0], [0, 2]])
    target = np.asarray([1, 0])
    assert np.argsort(((points - target) ** 2).sum(axis=1), kind="stable").tolist() == [0, 1, 2]
    frame = pd.DataFrame({"user_id": ["b", "a"], "score": [10, 10]})
    ordered = frame.sort_values(["score", "user_id"], ascending=[False, True])
    assert ordered["user_id"].tolist() == ["a", "b"]


async def test_scientific_solutions_run_through_judge() -> None:
    language = Language(
        name="python",
        file_ext=".py",
        run_cmd="python {src}",
        time_limit=5,
        memory_limit=512,
    )
    knn = Problem.model_validate_json(
        (SEEDS / "mock_a_batch_knn.json").read_text(encoding="utf-8")
    )
    knn = knn.model_copy(update={"testcases": knn.testcases[:1]})
    knn_code = """\
import sys
from collections import Counter
import numpy as np
raw = sys.stdin.read().splitlines()
n, d, q, k = map(int, raw[0].split())
train = np.asarray([list(map(int, row.split())) for row in raw[1:n+1]])
for row in raw[n+1:n+1+q]:
    target = np.asarray(list(map(int, row.split())))
    order = np.argsort(((train[:, :d] - target) ** 2).sum(axis=1), kind="stable")[:k]
    votes = Counter(map(int, train[order, d]))
    print(min(votes, key=lambda label: (-votes[label], label)))
"""
    risk = Problem.model_validate_json(
        (SEEDS / "mock_b_risk_report.json").read_text(encoding="utf-8")
    )
    risk = risk.model_copy(update={"testcases": risk.testcases[:1]})
    risk_code = """\
import sys
import pandas as pd
raw = sys.stdin.read().splitlines()
frame = pd.DataFrame(
    [row.split() for row in raw[1:]],
    columns=["user_id", "age", "income", "overdue"],
)
for column in ["age", "income", "overdue"]:
    frame[column] = frame[column].astype(int)
frame["score"] = frame["overdue"] * 35 + (frame["income"] < 5000) * 20 + (frame["age"] < 25) * 10
frame = frame.sort_values(["score", "user_id"], ascending=[False, True])
for row in frame.itertuples():
    print(row.user_id, row.score)
"""
    assert (await judge_code(knn, language, knn_code)).score == 10
    assert (await judge_code(risk, language, risk_code)).score == 10
    thread_keys = (
        "OPENBLAS_NUM_THREADS",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    )
    assert all(JUDGE_ENV[key] == "1" for key in thread_keys)
