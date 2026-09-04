from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, PositiveInt, SecretStr
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
    ai_default_provider_url: str = ""
    ai_default_model: str = ""
    ai_default_api_key: SecretStr = SecretStr("")
    ai_default_input_price: float = Field(default=0, ge=0, allow_inf_nan=False)
    ai_default_output_price: float = Field(default=0, ge=0, allow_inf_nan=False)
    ai_default_price_unit: int = Field(default=1_000_000, gt=0)
    ai_default_currency: Literal["USD", "CNY"] = "USD"
    ai_default_cached_input_price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    ai_routing_enabled: bool = False
    ai_default_reasoning_effort: Literal["high", "max"] | None = None
    ai_quality_reasoning_effort: Literal["high", "max"] | None = None
    ai_default_json_mode: bool = True
    ai_quality_json_mode: bool = True
    ai_quality_model: str = Field(default="", max_length=200)
    ai_quality_input_price: float = Field(default=0, ge=0, allow_inf_nan=False)
    ai_quality_output_price: float = Field(default=0, ge=0, allow_inf_nan=False)
    ai_quality_cached_input_price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    ai_max_output_tokens: int = Field(default=16384, ge=512, le=65536)
    ai_section_max_output_tokens: int = Field(default=8192, ge=512, le=32768)
    ai_assistant_max_output_tokens: int = Field(default=16384, ge=512, le=65536)
    ai_user_active_tasks: int = Field(default=2, ge=1, le=20)
    ai_model_concurrency: int = Field(default=4, ge=1, le=32)
    ai_model_output_limits: dict[str, PositiveInt] = Field(
        default_factory=lambda: {"gpt-4o": 16384}
    )
    ai_stream_read_timeout_seconds: float = Field(default=90, gt=0, le=600)
    allow_private_ai_endpoints: bool = False
    ai_task_timeout_seconds: float = Field(default=300, gt=0, le=7200)
    ai_stage_timeout_seconds: float = Field(default=120, gt=0, le=1800)
