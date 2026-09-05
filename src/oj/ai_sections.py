"""Small, schema-checked edits; never ask a sample edit to regenerate a whole problem."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from oj.schemas import DraftProblem, Problem, StrictModel, TestCase


class SampleEdit(StrictModel):
    samples: list[TestCase] = Field(min_length=1, max_length=20)
    review: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def small_unique_examples(self) -> SampleEdit:
        if len({item.input for item in self.samples}) != len(self.samples):
            raise ValueError("样例输入不能重复")
        if any(len(item.input) > 2000 or len(item.output) > 2000 for item in self.samples):
            raise ValueError("展示样例必须简短；大规模数据属于测试点，不应塞入样例")
        return self


class StatementEdit(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=12000)
    input_description: str = Field(min_length=1, max_length=4000)
    output_description: str = Field(min_length=1, max_length=4000)
    review: str = Field(min_length=1, max_length=4000)


class DraftReviewCoverage(StrictModel):
    basic: str = Field(default="", max_length=5000)
    boundary: str = Field(default="", max_length=5000)
    scale: str = Field(default="", max_length=5000)


class DraftReviewWrongSolution(StrictModel):
    code: str = Field(default="", max_length=200_000)
    reason: str = Field(default="", max_length=5000)


class DraftReviewCandidate(StrictModel):
    problem: DraftProblem
    reference_solution: str = Field(default="", max_length=200_000)
    brute_solution: str = Field(default="", max_length=200_000)
    generator_code: str = Field(default="", max_length=200_000)
    coverage: DraftReviewCoverage = Field(default_factory=DraftReviewCoverage)
    wrong_solutions: list[DraftReviewWrongSolution] = Field(default_factory=list, max_length=4)


_REVIEW_PROTECTED_PROBLEM_FIELDS = {"id", "author", "source", "public_cases"}
_REVIEW_ASSET_FIELDS = {
    "reference_solution",
    "brute_solution",
    "generator_code",
    "coverage",
    "wrong_solutions",
}


def _present(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_present(item) for item in value)
    if isinstance(value, dict):
        return any(_present(item) for item in value.values())
    return value is not None


def merge_draft_review(
    baseline: DraftReviewCandidate, patch: dict[str, Any]
) -> DraftReviewCandidate:
    """Merge a model patch without allowing identity/policy changes or new asset modules."""
    if not isinstance(patch, dict):
        raise ValueError("审查修改必须是对象")
    allowed_top = set(DraftReviewCandidate.model_fields)
    extra = set(patch) - allowed_top
    if extra:
        raise ValueError("审查修改包含未知字段：" + "、".join(sorted(extra)))
    baseline_data = baseline.model_dump()
    for field in _REVIEW_ASSET_FIELDS & set(patch):
        if not _present(baseline_data[field]) and _present(patch[field]):
            raise ValueError(f"全面审查不能补写缺失资产：{field}")
    problem_patch = patch.get("problem", {})
    if not isinstance(problem_patch, dict):
        raise ValueError("problem 修改必须是对象")
    protected = set(problem_patch) & _REVIEW_PROTECTED_PROBLEM_FIELDS
    if protected:
        raise ValueError("审查不能修改受保护字段：" + "、".join(sorted(protected)))
    unknown_problem = set(problem_patch) - set(DraftProblem.model_fields)
    if unknown_problem:
        raise ValueError("审查修改包含未知题目字段：" + "、".join(sorted(unknown_problem)))
    merged = dict(baseline_data)
    for field, value in patch.items():
        if field == "problem":
            merged["problem"] = {**baseline_data["problem"], **problem_patch}
        elif field == "coverage" and isinstance(value, dict):
            merged["coverage"] = {**baseline_data["coverage"], **value}
        else:
            merged[field] = value
    candidate = DraftReviewCandidate.model_validate(merged)
    for field in _REVIEW_PROTECTED_PROBLEM_FIELDS:
        if getattr(candidate.problem, field) != getattr(baseline.problem, field):
            raise ValueError(f"审查不能修改受保护字段：{field}")
    return candidate


SECTION_FIELDS = {
    "samples": ("samples",),
    "statement": ("title", "description", "input_description", "output_description"),
}


def section_prompt(target: str) -> str:
    shape = (
        '{"samples":[{"input":"literal input","output":"literal output"}],"review":"explanation"}'
        if target == "samples"
        else '{"title":"...","description":"...","input_description":"...",'
        '"output_description":"...","review":"explanation"}'
    )
    return (
        "You are editing ONLY one section of an existing programming problem. "
        "Return ONLY a JSON object of this exact shape: " + shape + ". "
        "Do not return a complete problem, reference solution, generator, wrong algorithms, "
        "coverage analysis or testcases. Preserve the original semantics and constraints. "
        "For samples, return the complete revised list (normally 5-8, at most 20), preserving "
        "existing samples unless incorrect. Use tiny, distinct, manually checkable examples; "
        "each input/output must be below 2000 characters. Never expand maximum-size strings. "
        "Every sample must satisfy the stated input alphabet, format and value bounds. "
        "Do not create out-of-domain samples just to show validation failures: if input only "
        "permits ()[], braces {} are NOT a valid negative example. "
        "Check exact outputs and whitespace including empty input. Explain each added example "
        "briefly in review. Write in the same language as the problem. No markdown fences."
    )


def merge_section(base: Problem, target: str, data: dict[str, Any]) -> dict[str, Any]:
    parsed = (SampleEdit if target == "samples" else StatementEdit).model_validate(data)
    values = parsed.model_dump()
    # Whitelist assignment ensures the model cannot change limits/tests/identity/other sections.
    updated = base.model_dump()
    updated.update({field: values[field] for field in SECTION_FIELDS[target]})
    problem = Problem.model_validate(updated)
    return {
        "kind": "section_patch",
        "target_section": target,
        "problem": problem.model_dump(),
        "baseline": base.model_dump(),
        "review": values["review"],
        "reviewed": False,
        "verification": {"quality_gate_passed": False, "scope": "section_only"},
    }
