from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

from oj.difficulty import DIFFICULTIES
from oj.security import validate_password_bytes


class StrictModel(BaseModel):
    # Code, passwords and test data are opaque: whitespace can be meaningful.
    model_config = ConfigDict(extra="forbid")


class Credentials(StrictModel):
    username: str = Field(
        min_length=3,
        max_length=40,
        pattern=r"^[^\s\x00-\x1f\x7f]+$",
    )
    password: str = Field(min_length=6, max_length=200)

    _password_bytes = field_validator("password")(validate_password_bytes)


class PasswordChange(StrictModel):
    current_password: str = Field(min_length=6, max_length=200)
    new_password: str = Field(min_length=6, max_length=200)

    _password_bytes = field_validator("current_password", "new_password")(validate_password_bytes)


class RoleUpdate(StrictModel):
    role: Literal["user", "admin", "banned"]


class TestCase(StrictModel):
    input: str = Field(max_length=1_000_000)
    output: str = Field(max_length=1_000_000)
    files: dict[
        Annotated[
            str,
            Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"),
        ],
        Annotated[str, Field(max_length=1_000_000)],
    ] = Field(default_factory=dict, max_length=10, exclude_if=lambda value: not value)


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


class DraftProblem(StrictModel):
    """A bounded, partially completed problem that is not publishable yet."""

    id: str = Field(default="", pattern=r"^(?:|[A-Za-z0-9_-]{1,64})$")
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=100_000)
    input_description: str = Field(default="", max_length=20_000)
    output_description: str = Field(default="", max_length=20_000)
    samples: list[TestCase] = Field(default_factory=list, max_length=20)
    constraints: str = Field(default="", max_length=20_000)
    testcases: list[TestCase] = Field(default_factory=list, max_length=100)
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


class WorkspaceDraftUpdate(StrictModel):
    code: str = Field(max_length=200_000)
    expected_revision: int | None = Field(default=None, ge=0)


class LogVisibility(StrictModel):
    public_cases: bool = False


class AIModelConfig(StrictModel):
    currency: Literal["USD", "CNY"] = "USD"
    cached_input_price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    provider_url: HttpUrl
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, min_length=1, max_length=1000)
    input_price: float = Field(default=0, ge=0, allow_inf_nan=False)
    output_price: float = Field(default=0, ge=0, allow_inf_nan=False)
    price_unit: int = Field(default=1_000_000, gt=0)


class AIProblemTaskCreate(StrictModel):
    workflow_version: Literal[1, 2] = 1
    generation_mode: Literal["basic_draft", "balanced", "full"] = "full"
    resume_task_id: str | None = Field(default=None, pattern=r"^ai-[A-Za-z0-9_-]{8,64}$")
    requirement: str = Field(default="", max_length=20_000)
    problem_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    draft_id: str | None = Field(default=None, pattern=r"^draft-[A-Za-z0-9_-]{8,64}$")
    action: Literal["generate", "revise", "review", "tests"] = "generate"
    target_section: Literal["all", "statement", "constraints", "samples", "testcases", "review"] = (
        "all"
    )

    @model_validator(mode="after")
    def basic_mode_scope(self) -> AIProblemTaskCreate:
        if not self.requirement.strip():
            if self.draft_id or self.problem_id:
                self.requirement = "检查并改进所选范围，保留原题意"
            else:
                raise ValueError("请输入命题需求")
        if self.generation_mode in {"basic_draft", "balanced"} and (
            self.action != "generate" or self.target_section != "all"
        ):
            raise ValueError("草稿生成模式仅适用于整题生成")
        return self


class AssistantConversationCreate(StrictModel):
    problem_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


class AssistantMessageCreate(StrictModel):
    message: str = Field(min_length=1, max_length=20000)
    code: str = Field(default="", max_length=200000)
    language: str = Field(default="python", pattern=r"^[a-z][a-z0-9_+-]{0,31}$")
    submission_id: int | None = Field(default=None, ge=1)
    full_solution: bool = False


class ProblemDraftCreate(StrictModel):
    base_problem_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    requirement: str = Field(default="", max_length=20_000)
    # Drafts deliberately accept incomplete fields. Publish and verification still
    # validate the stricter Problem schema.
    problem: DraftProblem | None = None
    reference_solution: str = Field(default="", max_length=200_000)
    brute_solution: str = Field(default="", max_length=200_000)
    generator_code: str = Field(default="", max_length=200_000)
    review: dict[str, Any] = Field(default_factory=dict)


class ProblemDraftUpdate(ProblemDraftCreate):
    revision: int = Field(ge=1)
    change_summary: str = Field(default="人工保存", max_length=500)


class ProblemDraftVerify(StrictModel):
    mode: Literal["basic", "full"] = "full"


class Coverage(StrictModel):
    basic: str = Field(min_length=5, max_length=5000)
    boundary: str = Field(min_length=5, max_length=5000)
    scale: str = Field(min_length=5, max_length=5000)


class WrongSolution(StrictModel):
    code: str = Field(min_length=1, max_length=200_000)
    reason: str = Field(min_length=5, max_length=5000)


class BasicGeneratedDraft(StrictModel):
    problem: Problem
    reference_solution: str = Field(min_length=1, max_length=200_000)

    @model_validator(mode="after")
    def check_basic_assets(self) -> BasicGeneratedDraft:
        inputs = [case.input for case in self.problem.testcases]
        if len(inputs) < 5 or len(set(inputs)) != len(inputs):
            raise ValueError("基础草稿至少需要 5 个互不重复的测试输入")
        if not self.reference_solution.strip():
            raise ValueError("基础草稿必须包含可运行的 Python 参考解")
        if self.problem.difficulty not in {level["value"] for level in DIFFICULTIES}:
            raise ValueError("AI 生成须采用标准难度等级")
        return self


class BasicDraftReview(StrictModel):
    candidate: BasicGeneratedDraft
    blocking_issues: list[str] = Field(max_length=20)
    suggestions: list[str] = Field(max_length=30)


class GeneratedProblem(StrictModel):
    problem: Problem
    reference_solution: str = Field(min_length=1, max_length=200_000)
    brute_solution: str = Field(default="", max_length=200_000)
    generator_code: str = Field(default="", max_length=200_000)
    review: str = Field(min_length=1, max_length=20_000)
    coverage: Coverage
    wrong_solutions: list[WrongSolution] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def check_test_quality(self) -> GeneratedProblem:
        if self.problem.difficulty not in {level["value"] for level in DIFFICULTIES}:
            raise ValueError("AI 生成须采用标准难度等级")
        inputs = [case.input for case in self.problem.testcases]
        if len(inputs) < 5 or len(set(inputs)) != len(inputs):
            raise ValueError("至少需要 5 个互不重复的测试输入")
        if len({item.code for item in self.wrong_solutions}) != len(self.wrong_solutions):
            raise ValueError("错误解法必须互不重复")
        return self
