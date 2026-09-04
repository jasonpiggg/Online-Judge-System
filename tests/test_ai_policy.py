from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import SecretStr, ValidationError
from streamlit.testing.v1 import AppTest

from frontend.ai import money
from frontend.client import ApiClient
from oj.ai_authoring import calculate_cost
from oj.ai_policy import environment_policy, select_phase_config
from oj.config import Settings
from oj.database import Database
from oj.judge import CaseResult, JudgeOutcome
from oj.schemas import AIModelConfig, GeneratedProblem
from tests.conftest import login_admin
from tests.test_ai_http import finish, generated, provider  # noqa: F401 - shared fixture


def policy_settings() -> Settings:
    return Settings(
        _env_file=None,
        ai_routing_enabled=True,
        ai_quality_model="glm-5.3",
        ai_default_currency="CNY",
        ai_default_model="glm-5.3-flash",
        ai_default_input_price=0.4,
        ai_default_output_price=1.4,
        ai_default_cached_input_price=0.115,
        ai_quality_input_price=8,
        ai_quality_output_price=28,
        ai_quality_cached_input_price=2,
        ai_default_reasoning_effort="high",
        ai_quality_reasoning_effort="high",
        ai_default_json_mode=False,
        ai_quality_json_mode=False,
    )


@pytest.mark.parametrize(
    "phase,action,target,requirement,context,tier",
    [
        ("generation", "generate", "all", "设计一道入门整数求和题", "", "flash"),
        ("generation", "revise", "statement", "修复措辞和排版", "easy", "flash"),
        ("critique", "generate", "all", "设计一道入门整数求和题", "", "quality"),
        ("generation", "generate", "all", "简单讲解动态规划的高难度题", "", "quality"),
        ("generation", "generate", "all", "题目要求未明确难度", "", "quality"),
        ("generation", "review", "all", "审查一道入门题", "", "quality"),
        ("generation", "tests", "testcases", "补充简单边界用例", "", "quality"),
        ("generation", "revise", "statement", "简单修改题面", "hard", "quality"),
        ("generation", "revise", "samples", "调整样例", "easy", "flash"),
    ],
)
def test_routing(
    phase: str,
    action: str,
    target: str,
    requirement: str,
    context: str,
    tier: str,
) -> None:
    base = {
        "config_source": "system",
        "model": "glm-5.3-flash",
        "currency": "CNY",
        "price_unit": 1_000_000,
        "routing_config": environment_policy(policy_settings()),
    }
    selected = select_phase_config(base, phase, action, target, requirement, context)
    assert selected["tier"] == tier
    assert selected["model"] == ("glm-5.3" if tier == "quality" else "glm-5.3-flash")
    assert base["model"] == "glm-5.3-flash"  # Do not mutate the snapshot between phases.
    base.update(config_source="personal", model="my-model")
    assert select_phase_config(base, phase, action, target, requirement)["model"] == "my-model"


def test_cost_cache_and_currency_validation() -> None:
    assert calculate_cost(1_000_000, 1_000_000, 0.4, 1.4, 1_000_000, 500_000, 0.115) == 1.6575
    assert calculate_cost(100, 20, 1, 2, 100, 1000, 0) == 0.4
    assert calculate_cost(100, 20, 1, 2, 100, 50) == 1.4
    assert money(0.1, "CNY") == "¥0.100000 CNY"
    assert money(0.1, "USD") == "$0.100000 USD"
    for values in [
        {"currency": "EUR"},
        {"cached_input_price": -1},
        {"cached_input_price": float("inf")},
    ]:
        with pytest.raises(ValidationError):
            AIModelConfig(provider_url="https://example.com/v1", model="x", **values)
    with pytest.raises(RuntimeError, match="QUALITY_MODEL"):
        environment_policy(Settings(_env_file=None, ai_routing_enabled=True))


async def setup_policy(manager: Any, url: str) -> None:
    for key, value in policy_settings().model_dump().items():
        if (
            key.startswith("ai_default_")
            or key.startswith("ai_quality_")
            or key == "ai_routing_enabled"
        ):
            setattr(manager.settings, key, value)
    manager.settings.ai_default_provider_url = url
    manager.settings.ai_default_api_key = SecretStr("test-key")
    await manager.initialize_system_config()


async def test_two_model_cached_sse_and_currency_api(
    app: FastAPI,
    client: AsyncClient,
    generated: dict[str, Any],  # noqa: F811
) -> None:
    manager = app.state.ai_authoring
    generated.update(
        brute_solution="print(sum(map(int,input().split())))",
        generator_code="import json\nprint(json.dumps([f'{i} {-i}\\n' for i in range(20)]))",
    )
    async with provider(generated, mode="cached") as (url, calls, _):
        await setup_policy(manager, url)
        task_id = await manager.create(1, "设计一道入门整数求和题", None)
        row = await finish(manager, task_id)
    assert row["status"] == "completed", row["error"]
    assert [c["model"] for c in calls] == ["glm-5.3-flash", "glm-5.3"]
    assert all(c["max_tokens"] == 16384 for c in calls)
    assert all(c["reasoning_effort"] == "high" for c in calls)
    assert all("response_format" not in c for c in calls)
    result = json.loads(row["result"])
    assert result["generator_code"] == generated["generator_code"]
    assert result["verification"]["quality_gate_passed"]
    expected = (4 * 0.4 + 6 * 0.115 + 20 * 1.4 + 4 * 8 + 6 * 2 + 20 * 28) / 1_000_000
    assert row["cost"] == pytest.approx(expected)
    assert row["currency"] == "CNY"
    phases = json.loads(row["usage_details"])["phases"]
    assert phases["generation"]["cached_input_tokens"] == 6
    assert phases["generation"]["reasoning_tokens"] == 12
    assert phases["critique"]["pricing"]["input_price"] == 8
    await login_admin(client)
    detail = await client.get(f"/api/ai/problem-tasks/{task_id}")
    assert detail.json()["data"]["usage"]["currency"] == "CNY"
    history = (await client.get("/api/ai/problem-tasks/")).json()["data"]
    assert history[0]["currency"] == "CNY"
    for secret in ["test-key", url, "encrypted_api_key"]:
        assert secret not in detail.text


async def test_truncated_stream_keeps_usage_without_retry(
    app: FastAPI,
    generated: dict[str, Any],  # noqa: F811
) -> None:
    manager = app.state.ai_authoring
    async with provider(generated, mode="truncated") as (url, calls, _):
        await setup_policy(manager, url)
        row = await finish(manager, await manager.create(1, "设计一道入门整数求和题", None))
    assert row["status"] == "failed"
    assert "Token 上限" in row["error"]
    assert len(calls) == 1
    assert row["output_tokens"] == 20
    assert row["cost"] == pytest.approx((10 * 0.4 + 20 * 1.4) / 1_000_000)


async def test_explicit_policy_sync_preserves_keys_and_historical_tasks(app: FastAPI) -> None:
    manager = app.state.ai_authoring
    await setup_policy(manager, "http://127.0.0.1:1234/v1")
    before = await manager.db.fetchone("SELECT * FROM ai_system_config")
    manager.settings.ai_default_input_price = 0.8
    await manager.initialize_system_config()
    assert (await manager.resolve_config(1))["input_price"] == 0.4
    await manager.sync_system_policy()
    after = await manager.resolve_config(1)
    assert after["input_price"] == 0.8
    assert after["encrypted_api_key"] == before["encrypted_api_key"]
    manager.settings.ai_default_api_key = SecretStr("different-key")
    with pytest.raises(RuntimeError, match="differ"):
        await manager.sync_system_policy()
    assert (await manager.resolve_config(1))["encrypted_api_key"] == before["encrypted_api_key"]


async def test_personal_cny_and_usd_configs(client: AsyncClient, app: FastAPI) -> None:
    await login_admin(client)
    for currency in ["CNY", "USD"]:
        result = await client.put(
            "/api/ai/model-config",
            json={
                "provider_url": "http://127.0.0.1:9999/v1",
                "model": "personal",
                "api_key": "personal-key",
                "currency": currency,
                "cached_input_price": 0.2,
            },
        )
        assert result.status_code == 200
        assert result.json()["data"]["currency"] == currency
        assert result.json()["data"]["cached_input_price"] == 0.2
        assert (await app.state.ai_authoring.resolve_config(1))["currency"] == currency


async def test_v4_migration_keeps_historical_dollar_costs(tmp_path: Path) -> None:
    db = Database(tmp_path / "migration.db")
    await db.initialize()
    for table in ("ai_configs", "ai_system_config", "ai_tasks"):
        await db.execute(f"ALTER TABLE {table} DROP COLUMN currency")
    for table in ("ai_configs", "ai_system_config"):
        await db.execute(f"ALTER TABLE {table} DROP COLUMN cached_input_price")
    await db.execute("ALTER TABLE ai_system_config DROP COLUMN routing_config")
    await db.execute("INSERT INTO users VALUES(1,'old',X'00','user','old')")
    await db.execute(
        """INSERT INTO ai_tasks(id,user_id,requirement,status,progress,cost,created_at,updated_at)
           VALUES('old',1,'old','completed','old',1.25,'old','old')"""
    )
    await db.execute("PRAGMA user_version=4")
    await db.initialize()
    await db.initialize()
    row = await db.fetchone("SELECT currency,cost FROM ai_tasks WHERE id='old'")
    assert tuple(row) == ("USD", 1.25)
    backups = await asyncio.to_thread(lambda: list(tmp_path.glob("migration.pre-v4-*.db")))
    assert len(backups) == 1


def test_frontend_personal_currency_and_cache_form(monkeypatch: Any) -> None:
    saved = []

    def request(_self: Any, method: str, _path: str, **kwargs: Any) -> dict[str, Any]:
        if method == "PUT":
            saved.append(kwargs["json"])
        return {"code": 200, "data": {"source": "personal"}}

    monkeypatch.setattr(ApiClient, "request", request)
    page = AppTest.from_string("""
from frontend.ai import model_settings
from frontend.client import ApiClient
model_settings(ApiClient(), {"personal_configured": True, "currency": "CNY",
    "provider_url": "https://example.com/v1", "model": "personal",
    "cached_input_price": 0.115})
""").run()
    assert not page.exception
    assert page.selectbox[0].value == "CNY"
    next(button for button in page.button if button.label == "保存模型配置").click().run()
    assert saved[-1]["currency"] == "CNY"
    assert saved[-1]["cached_input_price"] == 0.115
    page.selectbox[0].set_value("USD")
    page.checkbox[0].uncheck()
    next(button for button in page.button if button.label == "保存模型配置").click().run()
    assert saved[-1]["currency"] == "USD"
    assert saved[-1]["cached_input_price"] is None


@pytest.mark.parametrize("currency,symbol", [("CNY", "¥"), ("USD", "$")])
def test_frontend_task_currency_and_stage_pricing(
    monkeypatch: Any,
    currency: str,
    symbol: str,
) -> None:
    pricing = {
        "input_price": 8,
        "output_price": 28,
        "cached_input_price": 2,
        "price_unit": 1_000_000,
        "currency": currency,
    }
    data = {
        "status": "failed",
        "progress": "test",
        "error": "validation failed",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "cost": 0.25,
            "currency": currency,
            "source": "provider",
        },
        "usage_details": {
            "phases": {
                "critique": {
                    "tier": "quality",
                    "pricing": pricing,
                    "routing_reason": "最终复审",
                    "cached_input_tokens": None,
                }
            }
        },
    }
    monkeypatch.setattr(ApiClient, "request", lambda *_a, **_k: {"code": 200, "data": data})
    page = AppTest.from_string("""
import streamlit as st
from frontend.ai import task_panel
from frontend.client import ApiClient
st.session_state["ai-terminal-test"] = True
task_panel(ApiClient(), "test")
""").run()
    assert not page.exception
    assert page.metric[2].value == f"{symbol}0.250000 {currency}"
    assert any("最终复审" in caption.value for caption in page.caption)
    assert any("未提供" in caption.value for caption in page.caption)


async def test_generator_has_separate_bounded_budget(
    app: FastAPI,
    generated: dict[str, Any],  # noqa: F811
    monkeypatch: Any,
) -> None:
    generated["problem"].update(time_limit=0.01, memory_limit=16)
    generated.update(brute_solution="print(0)", generator_code="import json; print('[]')")
    problem = GeneratedProblem.model_validate(generated)
    calls = []

    async def judge(harness: Any, _language: Any, code: str) -> JudgeOutcome:
        calls.append(code)
        if code == problem.generator_code:
            assert (harness.time_limit, harness.memory_limit) == (3.0, 128)
            cases = [CaseResult(1, "WA", 0, 0, output=json.dumps([f"{i} 0\n" for i in range(20)]))]
        else:
            # Only generator budget changes; submitted solutions retain problem limits.
            assert (harness.time_limit, harness.memory_limit) == (0.01, 16)
            cases = [CaseResult(i, "AC", 0, 0, output="0") for i in range(20)]
        return JudgeOutcome(cases, len(cases), len(cases), None, {}, "")

    monkeypatch.setattr("oj.ai_authoring.judge_code", judge)
    result = await app.state.ai_authoring._verify_differential(problem, None, "test")
    assert result["status"] == "passed"
    assert len(calls) == 3
