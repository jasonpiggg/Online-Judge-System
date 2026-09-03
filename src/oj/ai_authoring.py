from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet

from oj.config import Settings
from oj.database import Database
from oj.judge import judge_code
from oj.languages import get_language
from oj.problem_store import ProblemStore
from oj.schemas import AIModelConfig, GeneratedProblem

SYSTEM_PROMPT = """You are an expert programming contest problem setter. Return only JSON with:
{"problem": {all Atelier OJ problem fields}, "reference_solution": "Python 3 code", "review":
"a concise boundary and complexity review"}. Include at least five testcases spanning trivial,
boundary, negative/adversarial, and performance-relevant cases. Expected outputs must be exact.
Use a safe problem id containing only letters, numbers, underscores, or hyphens. Do not include
markdown fences."""


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def calculate_cost(
    input_tokens: int, output_tokens: int, input_price: float, output_price: float, unit: int
) -> float:
    return round(input_tokens / unit * input_price + output_tokens / unit * output_price, 10)


def _key(settings: Settings) -> bytes:
    if settings.ai_encryption_key:
        digest = hashlib.sha256(settings.ai_encryption_key.encode()).digest()
        return base64.urlsafe_b64encode(digest)
    key_path = settings.database_path.parent / ".ai-key"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        return key_path.read_bytes()
    value = Fernet.generate_key()
    key_path.write_bytes(value)
    with contextlib.suppress(OSError):
        os.chmod(key_path, 0o600)
    return value


def _is_private_host(hostname: str) -> bool:
    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    return False


async def validate_provider_url(url: str, allow_private: bool) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" and not allow_private:
        raise ValueError("provider URL must use HTTPS")
    if parsed.username or parsed.password or not parsed.hostname:
        raise ValueError("provider URL may not contain credentials")
    if not allow_private and await asyncio.to_thread(_is_private_host, parsed.hostname):
        raise ValueError("private or reserved provider address is not allowed")
    return url.rstrip("/")


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cast(dict[str, Any], json.loads(cleaned))


class AIAuthoringManager:
    def __init__(self, db: Database, problems: ProblemStore, settings: Settings) -> None:
        self.db = db
        self.problems = problems
        self.settings = settings
        self.cipher = Fernet(_key(settings))
        self.tasks: dict[str, asyncio.Task[None]] = {}

    async def save_config(self, user_id: int, config: AIModelConfig) -> dict[str, object]:
        provider = await validate_provider_url(
            str(config.provider_url), self.settings.allow_private_ai_endpoints
        )
        encrypted = self.cipher.encrypt(config.api_key.encode())
        await self.db.execute(
            """INSERT INTO ai_configs
               (user_id,provider_url,model,encrypted_api_key,input_price,output_price,price_unit)
               VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
               provider_url=excluded.provider_url,model=excluded.model,
               encrypted_api_key=excluded.encrypted_api_key,input_price=excluded.input_price,
               output_price=excluded.output_price,price_unit=excluded.price_unit""",
            (
                user_id,
                provider,
                config.model,
                encrypted,
                config.input_price,
                config.output_price,
                config.price_unit,
            ),
        )
        return {
            "provider_url": provider,
            "model": config.model,
            "api_key_configured": True,
            "input_price": config.input_price,
            "output_price": config.output_price,
            "price_unit": config.price_unit,
        }

    async def create(self, user_id: int, requirement: str, problem_id: str | None) -> str:
        task_id = "ai-" + secrets.token_urlsafe(12)
        now = utcnow()
        await self.db.execute(
            """INSERT INTO ai_tasks
               (id,user_id,requirement,problem_id,status,progress,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (task_id, user_id, requirement, problem_id, "pending", "任务已进入队列", now, now),
        )
        task = asyncio.create_task(self._run(task_id))
        self.tasks[task_id] = task
        task.add_done_callback(
            lambda done: self.tasks.pop(task_id, None)
            if self.tasks.get(task_id) is done
            else None
        )
        return task_id

    async def cancel(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self.db.execute(
            "UPDATE ai_tasks SET status='cancelled',progress='任务已中断',updated_at=? WHERE id=?",
            (utcnow(), task_id),
        )

    async def close(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _update(self, task_id: str, status: str, progress: str) -> None:
        await self.db.execute(
            "UPDATE ai_tasks SET status=?,progress=?,updated_at=? WHERE id=?",
            (status, progress, utcnow(), task_id),
        )

    async def _run(self, task_id: str) -> None:
        try:
            await self._update(task_id, "running", "正在分析命题需求")
            task_row = await self.db.fetchone("SELECT * FROM ai_tasks WHERE id=?", (task_id,))
            if task_row is None:
                return
            config = await self.db.fetchone(
                "SELECT * FROM ai_configs WHERE user_id=?", (task_row["user_id"],)
            )
            if config is None:
                raise RuntimeError("请先配置模型提供商、模型名称和密钥")
            reference = ""
            if task_row["problem_id"]:
                existing = await self.problems.get(task_row["problem_id"])
                if existing:
                    reference = "\nExisting problem to adapt:\n" + existing.model_dump_json()
            prompt = f"Authoring requirement:\n{task_row['requirement']}{reference}"
            await self._update(task_id, "running", "正在流式生成题面与测试点")
            text, input_tokens, output_tokens, usage_source = await self._stream_completion(
                config, prompt
            )
            await self._update(task_id, "running", "正在审查结构、边界与复杂度")
            generated = GeneratedProblem.model_validate(_extract_json(text))
            await self._update(task_id, "running", "正在运行参考解法验证所有测试点")
            python = await get_language(self.db, "python")
            if python is None:
                raise RuntimeError("Python 评测语言未注册")
            outcome = await judge_code(generated.problem, python, generated.reference_solution)
            if outcome.score != outcome.counts:
                failures = ", ".join(
                    f"#{case.id}:{case.result}" for case in outcome.cases if case.result != "AC"
                )
                raise RuntimeError(f"参考解法未通过生成测试点：{failures}")
            cost = calculate_cost(
                input_tokens,
                output_tokens,
                config["input_price"],
                config["output_price"],
                config["price_unit"],
            )
            await self.db.execute(
                """UPDATE ai_tasks SET status='completed',progress='命题完成并通过参考解法验证',
                   result=?,input_tokens=?,output_tokens=?,usage_source=?,cost=?,updated_at=?
                   WHERE id=?""",
                (
                    generated.model_dump_json(),
                    input_tokens,
                    output_tokens,
                    usage_source,
                    cost,
                    utcnow(),
                    task_id,
                ),
            )
        except asyncio.CancelledError:
            await self.db.execute(
                """UPDATE ai_tasks SET status='cancelled',progress='任务已中断',updated_at=?
                   WHERE id=?""",
                (utcnow(), task_id),
            )
            raise
        except Exception as exc:
            message = str(exc)[:1000] or "AI 命题失败"
            await self.db.execute(
                """UPDATE ai_tasks SET status='failed',progress='命题失败',error=?,updated_at=?
                   WHERE id=?""",
                (message, utcnow(), task_id),
            )

    async def _stream_completion(
        self, config: object, prompt: str
    ) -> tuple[str, int, int, str]:
        api_key = self.cipher.decrypt(config["encrypted_api_key"]).decode()  # type: ignore[index]
        url = str(config["provider_url"]).rstrip("/") + "/chat/completions"  # type: ignore[index]
        body = {
            "model": config["model"],  # type: ignore[index]
            "stream": True,
            "stream_options": {"include_usage": True},
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
        chunks: list[str] = []
        usage: dict[str, int] = {}
        timeout = httpx.Timeout(90, connect=10)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            async with client.stream(
                "POST",
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    if event.get("usage"):
                        usage = event["usage"]
                    choices = event.get("choices") or []
                    if choices:
                        content = choices[0].get("delta", {}).get("content")
                        if content:
                            chunks.append(content)
        text = "".join(chunks)
        if usage:
            return (
                text,
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)),
                "provider",
            )
        return text, max(1, len(prompt) // 4), max(1, len(text) // 4), "estimated"
