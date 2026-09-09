from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from oj.schemas import AIProblemTaskCreate, BasicGeneratedDraft
from tests.test_ai_http import finish
from tests.test_ai_http import generated as generated  # noqa: F401
from tests.test_web_experience import configured, fake_phases


@pytest.mark.parametrize("repair", [False, True])
async def test_basic_draft_runs_reference_and_saves_verified_revision(
    client: AsyncClient,
    app: FastAPI,
    problem_payload: dict[str, Any],
    generated: dict[str, Any],
    repair: bool,
) -> None:
    manager = await configured(client, app, problem_payload)
    candidate = {k: copy.deepcopy(generated[k]) for k in ("problem", "reference_solution")}
    calls = []

    async def stream(config: Any, prompt: str, usage: Any = None) -> Any:
        calls.append(config)
        value = copy.deepcopy(candidate)
        if repair and len(calls) == 1:
            value["reference_solution"] = "print(-999999)"
        await usage(10, 20, "provider", 0)
        return json.dumps(value), 10, 20, "provider"

    manager._stream_completion = stream
    result = await client.post(
        "/api/ai/problem-tasks/",
        json={
            "requirement": "Generate a basic addition problem with tests",
            "workflow_version": 2,
            "generation_mode": "basic_draft",
        },
        headers={"Idempotency-Key": "basic"},
    )
    assert result.status_code == 200
    tid = result.json()["data"]["task_id"]
    await finish(manager, tid)
    task = (await client.get(f"/api/ai/problem-tasks/{tid}")).json()["data"]
    assert task["status"] == "completed", task["error"]
    assert len(calls) == (2 if repair else 1)
    assert calls[0]["max_output_tokens"] == 8192
    if repair:
        assert calls[1]["max_output_tokens"] == 4096
    report = task["result"]["verification"]
    assert report["level"] == "basic"
    assert report["reference_passed"] is True
    assert report["quality_gate_passed"] is False
    draft = (await client.get(f"/api/problem-drafts/{task['draft_id']}")).json()["data"]
    assert draft["status"] == "ready"
    assert draft["reference_solution"] == candidate["reference_solution"]
    assert not draft["brute_solution"]
    assert report["draft_revision"] == draft["revision"]
    assert len(task["usage_details"]["phases"]) == len(calls)
    # Completing assets is a separate task and reuses the saved statement/reference.
    if not repair:
        full_calls = fake_phases(manager, generated)
        followup = await client.post(
            "/api/ai/problem-tasks/",
            json={
                "requirement": "Complete validation assets for this saved draft",
                "draft_id": draft["id"],
                "workflow_version": 2,
            },
        )
        await finish(manager, followup.json()["data"]["task_id"])
        assert "Stage 2:" in full_calls[0][0]["system_prompt"]
        assert (
            full_calls[0][1]["candidate"]["reference_solution"] == candidate["reference_solution"]
        )


@pytest.mark.parametrize("failure", ["missing_reference", "wrong_answer", "truncated", "network"])
async def test_basic_failures_do_not_claim_success(
    client: AsyncClient,
    app: FastAPI,
    problem_payload: dict[str, Any],
    generated: dict[str, Any],
    failure: str,
) -> None:
    import httpx

    manager = await configured(client, app, problem_payload)
    calls = 0

    async def stream(config: Any, prompt: str, usage: Any = None) -> Any:
        nonlocal calls
        calls += 1
        value = {k: copy.deepcopy(generated[k]) for k in ("problem", "reference_solution")}
        if failure == "network":
            raise httpx.ReadError("test transport failure")
        if failure == "truncated":
            return '{"problem":', 10, 2, "provider"
        value["reference_solution"] = "" if failure == "missing_reference" else "print(-999999)"
        return json.dumps(value), 10, 20, "provider"

    manager._stream_completion = stream
    response = await client.post(
        "/api/ai/problem-tasks/",
        json={
            "requirement": "Generate a basic addition draft",
            "generation_mode": "basic_draft",
        },
    )
    tid = response.json()["data"]["task_id"]
    await finish(manager, tid)
    task = (await client.get(f"/api/ai/problem-tasks/{tid}")).json()["data"]
    assert task["status"] == "failed"
    assert calls == (1 if failure in {"truncated", "network"} else 2)
    assert not task["draft_id"]
    if failure in {"missing_reference", "wrong_answer"}:
        recovery = await client.post(f"/api/ai/problem-tasks/{tid}/save-draft")
        assert recovery.status_code == 200


def test_basic_schema_and_mode_constraints(generated: dict[str, Any]) -> None:
    assert (
        AIProblemTaskCreate(requirement="a sufficiently long requirement").generation_mode == "full"
    )
    with pytest.raises(ValueError):
        AIProblemTaskCreate(
            requirement="a sufficiently long requirement",
            generation_mode="basic_draft",
            action="review",
        )
    value = {k: copy.deepcopy(generated[k]) for k in ("problem", "reference_solution")}
    value["problem"]["testcases"] = value["problem"]["testcases"][:1]
    with pytest.raises(ValueError, match="5"):
        BasicGeneratedDraft.model_validate(value)


async def test_basic_stage_cancellation(app: FastAPI, monkeypatch: Any) -> None:
    from datetime import UTC, datetime, timedelta

    manager = app.state.ai_authoring

    async def invoke(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("expired queue must not call the provider")

    row = {"id": "expired", "created_at": (datetime.now(UTC) - timedelta(seconds=151)).isoformat()}
    with pytest.raises(TimeoutError):
        await manager._generate_basic(row, {"requirement": "basic test"}, invoke)


async def test_balanced_generation_retains_full_validation_with_bounded_outputs(
    client: AsyncClient,
    app: FastAPI,
    problem_payload: dict[str, Any],
    generated: dict[str, Any],
    monkeypatch: Any,
) -> None:
    import asyncio

    original_wait = asyncio.wait_for
    phase_limits = []

    async def observed_wait(future: Any, timeout: Any) -> Any:  # noqa: ASYNC109
        if getattr(future, "__name__", "") == "complete":
            phase_limits.append(timeout)
        return await original_wait(future, timeout)

    monkeypatch.setattr(asyncio, "wait_for", observed_wait)
    manager = await configured(client, app, problem_payload)
    calls = fake_phases(manager, generated)
    response = await client.post(
        "/api/ai/problem-tasks/",
        json={
            "requirement": "Generate a substantive addition problem with independent tests",
            "generation_mode": "balanced",
        },
    )
    tid = response.json()["data"]["task_id"]
    await finish(manager, tid)
    task = (await client.get(f"/api/ai/problem-tasks/{tid}")).json()["data"]
    assert task["status"] == "completed", task["error"]
    assert task["result"]["verification"]["quality_gate_passed"] is True
    assert task["result"]["verification"]["independent_oracle"]["status"] == "passed"
    assert [c[0]["max_output_tokens"] for c in calls] == [8192, 8192, 8192]
    assert len(phase_limits) == 3
    assert all(100 < value <= 235 for value in phase_limits)


def test_balanced_routing_preserves_personal_config_and_matching_quality_prices() -> None:
    from oj.ai_policy import balanced_phase_config, select_phase_config

    base = {
        "config_source": "system",
        "model": "glm-5.3-flash",
        "input_price": 0.4,
        "output_price": 1.4,
        "routing_config": json.dumps(
            {
                "enabled": False,
                "default_reasoning_effort": "low",
                "default_json_mode": False,
                "quality": {
                    "model": "glm-5.3",
                    "input_price": 8,
                    "output_price": 28,
                    "json_mode": False,
                },
            }
        ),
    }
    assert balanced_phase_config(base, "statement")["reasoning_effort"] == "high"
    assert balanced_phase_config(base, "assets")["reasoning_effort"] == "low"
    assert balanced_phase_config(base, "repair")["reasoning_effort"] == "low"
    review = balanced_phase_config(base, "critique")
    assert (review["model"], review["input_price"], review["reasoning_effort"]) == (
        "glm-5.3",
        8,
        "low",
    )
    assert review["json_mode"] is False
    assert select_phase_config(base, "critique", "review", "all", "")["model"] == "glm-5.3-flash"
    personal = {**base, "config_source": "personal", "model": "own-model"}
    assert balanced_phase_config(personal, "critique")["model"] == "own-model"
    assert "reasoning_effort" not in balanced_phase_config(personal, "statement")


@pytest.mark.parametrize("bad_stage", [1, 2, 3])
async def test_balanced_truncation_stops_without_paid_repair(
    client: AsyncClient,
    app: FastAPI,
    problem_payload: dict[str, Any],
    generated: dict[str, Any],
    bad_stage: int,
) -> None:
    manager = await configured(client, app, problem_payload)
    fake_phases(manager, generated)
    original = manager._stream_completion
    count = 0

    async def truncated(config: Any, prompt: str, usage: Any = None) -> Any:
        nonlocal count
        count += 1
        if count == bad_stage:
            return '{"unfinished":', 10, 2, "provider"
        return await original(config, prompt, usage)

    manager._stream_completion = truncated
    response = await client.post(
        "/api/ai/problem-tasks/",
        json={
            "requirement": "Generate a meaningful problem for truncation testing",
            "generation_mode": "balanced",
        },
    )
    tid = response.json()["data"]["task_id"]
    await finish(manager, tid)
    task = (await client.get(f"/api/ai/problem-tasks/{tid}")).json()["data"]
    assert task["status"] == "failed"
    assert count == bad_stage
    assert not task["draft_id"]


def test_complete_json_survives_explanatory_wrapper_without_inventing_missing_content() -> None:
    from oj.ai_authoring import _extract_json

    assert _extract_json('说明：\n```json\n{"patch":{},"review":"ok"}\n```\n以上为成果。') == {
        "patch": {},
        "review": "ok",
    }
    with pytest.raises(ValueError):
        _extract_json('说明：{"problem":{"title":"partial"}')
    with pytest.raises(ValueError):
        _extract_json('{"a":1} {"b":2}')


def test_flat_review_patch_preserves_fields_for_scope_validation() -> None:
    from oj.ai_experience import review_patch

    assert review_patch({"reference_solution": "print(1)", "review": "fix"}) == {
        "patch": {"reference_solution": "print(1)"},
        "review": "fix",
    }
    from oj.ai_authoring import AuthoringError

    with pytest.raises(AuthoringError):
        review_patch({"patch": None, "review": "fix"})


async def test_balanced_review_receives_all_local_execution_failures(
    client: AsyncClient,
    app: FastAPI,
    problem_payload: dict[str, Any],
    generated: dict[str, Any],
) -> None:
    manager = await configured(client, app, problem_payload)
    broken = copy.deepcopy(generated)
    broken["reference_solution"] = "raise RuntimeError()"
    broken["wrong_solutions"][0]["code"] = "raise RuntimeError()"
    calls = fake_phases(manager, broken)
    response = await client.post(
        "/api/ai/problem-tasks/",
        json={
            "requirement": "Generate a problem and detect multiple executable asset issues",
            "generation_mode": "balanced",
        },
    )
    await finish(manager, response.json()["data"]["task_id"])
    feedback = calls[2][1]["local_feedback"]
    assert "reference_solution" in feedback and "wrong_solutions[0]" in feedback
    assert "RE" in feedback
