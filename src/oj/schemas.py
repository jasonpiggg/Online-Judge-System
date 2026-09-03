from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


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
    time_limit: float = Field(default=3.0, gt=0, le=30)
    memory_limit: int = Field(default=128, ge=16, le=2048)
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




