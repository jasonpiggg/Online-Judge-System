from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class StrictModel(BaseModel):
    # Code, passwords and test data are opaque: whitespace can be meaningful.
    model_config = ConfigDict(extra="forbid")


class Credentials(StrictModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=6, max_length=200)


class RoleUpdate(StrictModel):
    role: Literal["user", "admin", "banned"]


class TestCase(StrictModel):
    input: str = Field(max_length=1_000_000)
    output: str = Field(max_length=1_000_000)


class Problem(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=100_000)
    input_description: str = Field(min_length=1, max_length=20_000)
    output_description: str = Field(min_length=1, max_length=20_000)
    samples: list[TestCase] = Field(min_length=1, max_length=20)
    constraints: str = Field(min_length=1, max_length=20_000)
    testcases: list[TestCase] = Field(min_length=1, max_length=100)
    hint: str = Field(default="", max_length=20_000)
    source: str = Field(default="", max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=30)
    time_limit: float | None = Field(default=None, gt=0, le=30)
    memory_limit: int | None = Field(default=None, ge=16, le=2048)
    author: str = Field(default="", max_length=100)
    difficulty: str = Field(default="", max_length=40)
    public_cases: bool = False


class Language(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_+-]{0,31}$")
    file_ext: str = Field(pattern=r"^\.[A-Za-z0-9]{1,10}$")
    compile_cmd: str | None = Field(default=None, max_length=500)
    run_cmd: str = Field(min_length=1, max_length=500)
    time_limit: float = Field(default=3.0, gt=0, le=30)
    memory_limit: int = Field(default=128, ge=16, le=2048)


class SubmissionCreate(StrictModel):
    problem_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    language: str = Field(pattern=r"^[a-z][a-z0-9_+-]{0,31}$")
    code: str = Field(min_length=1, max_length=200_000)


class LogVisibility(StrictModel):
    public_cases: bool = False


class AIModelConfig(StrictModel):
    provider_url: HttpUrl
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, min_length=1, max_length=1000)
    input_price: float = Field(default=0, ge=0, allow_inf_nan=False)
    output_price: float = Field(default=0, ge=0, allow_inf_nan=False)
    price_unit: int = Field(default=1_000_000, gt=0)


class AIProblemTaskCreate(StrictModel):
    requirement: str = Field(min_length=10, max_length=20_000)
    problem_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")


class Coverage(StrictModel):
    basic: str = Field(min_length=5, max_length=5000)
    boundary: str = Field(min_length=5, max_length=5000)
    scale: str = Field(min_length=5, max_length=5000)


class WrongSolution(StrictModel):
    code: str = Field(min_length=1, max_length=200_000)
    reason: str = Field(min_length=5, max_length=5000)


class GeneratedProblem(StrictModel):
    problem: Problem
    reference_solution: str = Field(min_length=1, max_length=200_000)
    review: str = Field(min_length=1, max_length=20_000)
    coverage: Coverage
    wrong_solutions: list[WrongSolution] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def check_test_quality(self) -> GeneratedProblem:
        inputs = [case.input for case in self.problem.testcases]
        if len(inputs) < 5 or len(set(inputs)) != len(inputs):
            raise ValueError("至少需要 5 个互不重复的测试输入")
        if len({item.code for item in self.wrong_solutions}) != len(self.wrong_solutions):
            raise ValueError("错误解法必须互不重复")
        return self
