from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="OJ_", extra="ignore")

    database_path: Path = Path("var/oj.db")
    problem_dir: Path = Path("var/problems")
    seed_problem_dir: Path = Path("data/problem_seeds")
    session_cookie: str = "oj_session"
    session_ttl_seconds: int = Field(default=28_800, ge=300, le=2_592_000)
    cookie_secure: bool = False
    ai_encryption_key: str = ""
    allow_private_ai_endpoints: bool = False
    ai_task_timeout_seconds: float = Field(default=300, gt=0, le=900)
    ai_stage_timeout_seconds: float = Field(default=120, gt=0, le=300)
