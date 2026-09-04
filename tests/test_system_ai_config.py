from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from streamlit.testing.v1 import AppTest

from frontend.client import ApiClient
from oj.ai_authoring import AIAuthoringManager
from oj.config import Settings
from oj.main import create_app
from oj.schemas import AIModelConfig
from tests.conftest import login_admin


async def seed(app: FastAPI) -> None:
    manager = app.state.ai_authoring
    manager.settings.ai_default_provider_url = "http://127.0.0.1:9999/v1"
    manager.settings.ai_default_model = "server-only-model"
    manager.settings.ai_default_api_key = SecretStr("test-system-secret")
    await manager.initialize_system_config()


async def test_default_encrypted_idempotent_and_new_user_fallback(
    client: AsyncClient, app: FastAPI
) -> None:
    await seed(app)
    manager = app.state.ai_authoring
    row = await manager.db.fetchone("SELECT * FROM ai_system_config")
    assert row["encrypted_api_key"] != b"test-system-secret"
    assert manager.cipher.decrypt(row["encrypted_api_key"]) == b"test-system-secret"
    manager.settings.ai_default_api_key = SecretStr("do-not-overwrite")
    await manager.initialize_system_config()
    row2 = await manager.db.fetchone("SELECT * FROM ai_system_config")
    assert row2["encrypted_api_key"] == row["encrypted_api_key"]
    await client.post("/api/users/", json={"username": "new-user", "password": "test-pass"})
    await client.post("/api/auth/login", json={"username": "new-user", "password": "test-pass"})
    result = await client.get("/api/ai/model-config")
    assert result.json()["data"] == {
        "source": "system",
        "system_configured": True,
        "personal_configured": False,
        "api_key_configured": True,
    }
    assert "test-system-secret" not in result.text
    assert "server-only-model" not in result.text
    assert "127.0.0.1" not in result.text


async def test_personal_override_and_delete_restore_default(
    client: AsyncClient, app: FastAPI
) -> None:
    await seed(app)
    await login_admin(client)
    payload = {"provider_url": "http://127.0.0.1:9998/v1", "model": "personal-model"}
    # A user must never reuse the server key with their own endpoint.
    assert (await client.put("/api/ai/model-config", json=payload)).status_code == 400
    saved = await client.put(
        "/api/ai/model-config", json={**payload, "api_key": "personal-test-secret"}
    )
    assert saved.json()["data"]["source"] == "personal"
    assert "personal-test-secret" not in saved.text
    effective = await app.state.ai_authoring.resolve_config(1)
    assert effective["model"] == "personal-model"
    updated = await client.put("/api/ai/model-config", json={**payload, "model": "changed"})
    assert updated.status_code == 200
    effective = await app.state.ai_authoring.resolve_config(1)
    assert (
        app.state.ai_authoring.cipher.decrypt(effective["encrypted_api_key"])
        == b"personal-test-secret"
    )
    # Another user's lookup cannot see the override.
    assert (await app.state.ai_authoring.resolve_config(999))["config_source"] == "system"
    removed = await client.delete("/api/ai/model-config")
    assert removed.json()["data"]["source"] == "system"
    assert (await client.delete("/api/ai/model-config")).status_code == 200
    client.cookies.clear()
    assert (await client.delete("/api/ai/model-config")).status_code == 401


async def test_startup_import_and_reset_preserve_default(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "test.db",
        problem_dir=tmp_path / "problems",
        seed_problem_dir=tmp_path / "seeds",
        ai_encryption_key="stable-test-master",
        ai_default_provider_url="http://127.0.0.1:9999/v1",
        ai_default_model="mock",
        ai_default_api_key="startup-test-secret",
        allow_private_ai_endpoints=True,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            await login_admin(client)
            assert (await client.get("/api/ai/model-config")).json()["data"]["source"] == "system"
            assert (await client.post("/api/reset/")).status_code == 200
            await login_admin(client)
            assert (await client.get("/api/ai/model-config")).json()["data"]["source"] == "system"


async def test_missing_or_wrong_master_fails_closed(app: FastAPI) -> None:
    await seed(app)
    original = app.state.ai_authoring
    for master in ["", "wrong-master"]:
        settings = original.settings.model_copy(
            update={
                "ai_encryption_key": master,
                "ai_default_provider_url": "",
                "ai_default_model": "",
                "ai_default_api_key": SecretStr(""),
            }
        )
        manager = AIAuthoringManager(original.db, original.problems, settings)
        with pytest.raises(RuntimeError) as exc:
            await manager.initialize_system_config()
        assert "test-system-secret" not in str(exc.value)


async def test_partial_environment_is_rejected(app: FastAPI) -> None:
    app.state.ai_authoring.settings.ai_default_model = "partial"
    with pytest.raises(RuntimeError, match="together"):
        await app.state.ai_authoring.initialize_system_config()
    assert await app.state.db.fetchone("SELECT * FROM ai_system_config") is None


async def test_system_task_uses_default_without_exposing_server_config(
    client: AsyncClient, app: FastAPI, monkeypatch: Any
) -> None:
    await seed(app)
    await client.post("/api/users/", json={"username": "new-user", "password": "test-pass"})
    await client.post("/api/auth/login", json={"username": "new-user", "password": "test-pass"})
    seen = []

    async def mock_stream(config: Any, _prompt: str, callback: Any) -> tuple[str, int, int, str]:
        seen.append(config["model"])
        assert (
            app.state.ai_authoring.cipher.decrypt(config["encrypted_api_key"])
            == b"test-system-secret"
        )
        await callback(10, 20, "provider")
        return "{}", 10, 20, "provider"  # Deliberately invalid result, no paid HTTP request.

    monkeypatch.setattr(app.state.ai_authoring, "_stream_completion", mock_stream)
    created = await client.post(
        "/api/ai/problem-tasks/", json={"requirement": "创建一道用于验证系统默认配置的练习题"}
    )
    assert created.status_code == 200
    task_id = created.json()["data"]["task_id"]
    task = app.state.ai_authoring.tasks.get(task_id)
    if task:
        await task
    detail = await client.get(f"/api/ai/problem-tasks/{task_id}")
    assert seen == ["server-only-model", "server-only-model"]
    assert detail.json()["data"]["usage_details"]["config_source"] == "system"
    for private in ["test-system-secret", "server-only-model", "127.0.0.1"]:
        assert private not in detail.text


def test_frontend_system_default_enables_generation(monkeypatch: Any) -> None:
    def request(_self: Any, _method: str, path: str, **_kwargs: Any) -> dict[str, Any]:
        data: Any = []
        if path == "/api/ai/model-config":
            data = {
                "source": "system",
                "system_configured": True,
                "personal_configured": False,
                "api_key_configured": True,
            }
        return {"code": 200, "msg": "success", "data": data}

    monkeypatch.setattr(ApiClient, "request", request)
    app = AppTest.from_string("""
from frontend.ai import ai_page
from frontend.client import ApiClient
ai_page(ApiClient())
""").run()
    assert not app.exception
    assert not next(button for button in app.button if button.label == "生成并验证").disabled
    assert any("系统模型已配置" in item.value for item in app.success)
    assert "test-system-secret" not in json.dumps(app.session_state.filtered_state, default=str)


async def test_legacy_local_key_migrates_personal_override(app: FastAPI) -> None:
    original = app.state.ai_authoring
    old_settings = original.settings.model_copy(update={"ai_encryption_key": ""})
    old = AIAuthoringManager(original.db, original.problems, old_settings)
    await old.save_config(
        1,
        AIModelConfig(
            provider_url="http://127.0.0.1:9998/v1",
            model="old-personal",
            api_key="old-personal-key",
        ),
    )
    before = await original.db.fetchone("SELECT encrypted_api_key FROM ai_configs WHERE user_id=1")
    await seed(app)
    after = await original.db.fetchone("SELECT encrypted_api_key FROM ai_configs WHERE user_id=1")
    assert before["encrypted_api_key"] != after["encrypted_api_key"]
    assert original.cipher.decrypt(after["encrypted_api_key"]) == b"old-personal-key"
    assert (await original.resolve_config(1))["model"] == "old-personal"
    assert (old_settings.database_path.parent / ".ai-key").exists()


async def test_invalid_system_url_fails_without_echoing_secret(app: FastAPI) -> None:
    manager = app.state.ai_authoring
    manager.settings.ai_default_provider_url = "https://user:secret-in-url@example.com/v1"
    manager.settings.ai_default_model = "mock"
    manager.settings.ai_default_api_key = SecretStr("private-api-key")
    with pytest.raises(RuntimeError) as exc:
        await manager.initialize_system_config()
    assert "secret-in-url" not in str(exc.value)
    assert "private-api-key" not in str(exc.value)
    assert await manager.db.fetchone("SELECT * FROM ai_system_config") is None


def test_env_default_requires_stable_master(app: FastAPI) -> None:
    settings = app.state.settings.model_copy(
        update={
            "ai_encryption_key": "",
            "ai_default_model": "mock",
        }
    )
    with pytest.raises(RuntimeError, match="OJ_AI_ENCRYPTION_KEY"):
        AIAuthoringManager(app.state.db, app.state.problems, settings)
