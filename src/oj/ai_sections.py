"""Small, schema-checked edits; never ask a sample edit to regenerate a whole problem."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from oj.schemas import Problem, StrictModel, TestCase


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
