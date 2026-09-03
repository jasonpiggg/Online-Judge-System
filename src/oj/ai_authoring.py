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
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet
from pydantic import ValidationError

from oj.config import Settings
from oj.database import Database
from oj.judge import judge_code
from oj.languages import get_language
from oj.problem_store import ProblemStore
from oj.schemas import AIModelConfig, GeneratedProblem

SYSTEM_PROMPT = """You are an expert programming contest problem setter. Return only a JSON object:
problem: {id,title,description,input_description,output_description,samples:[{input,output}],
constraints,testcases:[{input,output}],difficulty,tags,time_limit,memory_limit},
reference_solution: executable Python 3 code reading stdin and writing stdout,
review: knowledge points, difficulty, exact complexity and test limitations,
coverage: {basic: description of case numbers, boundary: description of case numbers,
scale: description of scale cases and why sizes exercise the relevant complexity},
wrong_solutions: [{code: executable Python 3, reason: typical algorithmic mistake}, ...].
At least 5 UNIQUE test inputs and at least 2 DISTINCT typical wrong algorithms are required.
Each wrong algorithm must run successfully but fail at least one expected output or resource limit.
Cover basic, boundary/adversarial and large-scale inputs; provide full literal inputs, not ellipses.
Both samples and tests MUST pass the reference algorithm. Tests are evidence, not complexity proofs.
Use a safe alphanumeric/underscore/hyphen id. String IO preserves whitespace. No markdown fences.
time_limit is seconds and memory_limit is MB; omit them to inherit language defaults."""

UsageCallback = Callable[[int, int, str], Awaitable[None]]


class AuthoringError(Exception):
    """Only explicitly safe diagnostics may cross the API boundary."""


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
        old = await self.db.fetchone("SELECT * FROM ai_configs WHERE user_id=?", (user_id,))
        if config.api_key is None and old is None:
            raise ValueError("首次配置必须提供 API key")
        encrypted = (
            self.cipher.encrypt(config.api_key.encode())
            if config.api_key
            else old["encrypted_api_key"]  # type: ignore[index]
        )
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
        return await self.get_config(user_id)

    async def get_config(self, user_id: int) -> dict[str, object]:
        row = await self.db.fetchone("SELECT * FROM ai_configs WHERE user_id=?", (user_id,))
        if row is None:
            return {"api_key_configured": False}
        return {
            **{
                key: row[key]
                for key in ("provider_url", "model", "input_price", "output_price", "price_unit")
            },
            "api_key_configured": True,
        }

    async def recover(self) -> None:
        # Never replay paid requests after a server restart.
        await self.db.execute(
            """UPDATE ai_tasks SET status='failed',progress='服务中断',
               error='服务重启中断了任务；已保留观测到的用量，请人工决定是否重新生成。',
               updated_at=? WHERE status IN ('pending','running')""",
            (utcnow(),),
        )

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
            lambda done: self.tasks.pop(task_id, None) if self.tasks.get(task_id) is done else None
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

    async def _update(self, task_id: str, status: str, progress: str, stage: str) -> None:
        await self.db.execute(
            "UPDATE ai_tasks SET status=?,progress=?,stage=?,updated_at=? WHERE id=?",
            (status, progress, stage, utcnow(), task_id),
        )

    async def _run(self, task_id: str) -> None:
        try:
            await asyncio.wait_for(self._author(task_id), self.settings.ai_task_timeout_seconds)
        except asyncio.CancelledError:
            await self._update(task_id, "cancelled", "任务已中断，保留已观测用量", "cancelled")
            raise
        except Exception as exc:
            if isinstance(exc, AuthoringError):
                message = str(exc)
            elif isinstance(exc, ValidationError):
                locations = [".".join(map(str, e["loc"])) or "result" for e in exc.errors()]
                message = "生成结果不符合质量结构，请调整需求：" + ", ".join(locations)[:500]
            elif isinstance(exc, (TimeoutError, httpx.TimeoutException)):
                message = "AI 阶段或任务超时。已保留用量；请检查服务商或缩小命题范围。"
            elif isinstance(exc, httpx.HTTPStatusError):
                message = f"模型服务返回 HTTP {exc.response.status_code}，请检查配置和服务额度。"
            else:
                message = "AI 生成或验证失败。请检查服务连接、JSON 格式和模型配置后手动重试。"
            await self.db.execute(
                "UPDATE ai_tasks SET status='failed',progress='命题失败',error=?,updated_at=? "
                "WHERE id=?",
                (message, utcnow(), task_id),
            )

    async def _author(self, task_id: str) -> None:
        await self._update(task_id, "running", "正在分析命题需求", "analysis")
        task_row = await self.db.fetchone("SELECT * FROM ai_tasks WHERE id=?", (task_id,))
        if task_row is None:
            return
        config = await self.db.fetchone(
            "SELECT * FROM ai_configs WHERE user_id=?", (task_row["user_id"],)
        )
        if config is None:
            raise AuthoringError("请先配置模型提供商、模型名称和密钥")
        reference = ""
        if task_row["problem_id"]:
            existing = await self.problems.get(task_row["problem_id"])
            if existing:
                reference = "\nExisting problem to adapt:\n" + existing.model_dump_json()
        prompt = f"Authoring requirement:\n{task_row['requirement']}{reference}"
        phases: dict[str, dict[str, Any]] = {}
        for phase, progress in [
            ("generation", "正在流式生成题目"),
            ("critique", "正在第二次调用模型，批判并改进完整结果"),
        ]:
            await self._update(task_id, "running", progress, phase)

            async def usage_update(i: int, o: int, source: str, phase: str = phase) -> None:
                phases[phase] = {"input_tokens": i, "output_tokens": o, "source": source}
                total_in = sum(p["input_tokens"] for p in phases.values())
                total_out = sum(p["output_tokens"] for p in phases.values())
                total_source = (
                    "provider"
                    if all(p["source"] == "provider" for p in phases.values())
                    else "estimated"
                )
                details = {
                    "phases": phases,
                    "pricing": {
                        key: config[key]
                        for key in (
                            "model",
                            "provider_url",
                            "input_price",
                            "output_price",
                            "price_unit",
                        )
                    },
                }
                await self.db.execute(
                    """UPDATE ai_tasks SET input_tokens=?,output_tokens=?,usage_source=?,
                           cost=?,usage_details=?,updated_at=? WHERE id=?""",
                    (
                        total_in,
                        total_out,
                        total_source,
                        calculate_cost(
                            total_in,
                            total_out,
                            config["input_price"],
                            config["output_price"],
                            config["price_unit"],
                        ),
                        json.dumps(details),
                        utcnow(),
                        task_id,
                    ),
                )

            text, i, o, source = await asyncio.wait_for(
                self._stream_completion(config, prompt, usage_update),
                self.settings.ai_stage_timeout_seconds,
            )
            await usage_update(i, o, source)
            if phase == "generation":
                prompt = (
                    "Critically inspect this draft against the original requirement. "
                    "Fix knowledge/difficulty, boundary and scale coverage, outputs and "
                    "two typical wrong algorithms. Return the COMPLETE improved JSON.\n"
                    + prompt
                    + "\nDRAFT:\n"
                    + text
                )
        generated = GeneratedProblem.model_validate(_extract_json(text))
        await self.db.execute(
            "UPDATE ai_tasks SET result=? WHERE id=?", (generated.model_dump_json(), task_id)
        )
        await self._update(task_id, "running", "正在验证参考解的全部样例与测试点", "validation")
        python = await get_language(self.db, "python")
        if python is None:
            raise AuthoringError("Python 评测语言未注册")
        validation_problem = generated.problem.model_copy(
            update={"testcases": [*generated.problem.samples, *generated.problem.testcases]}
        )
        outcome = await asyncio.wait_for(
            judge_code(validation_problem, python, generated.reference_solution),
            self.settings.ai_stage_timeout_seconds,
        )
        if outcome.score != outcome.counts:
            failures = ", ".join(
                f"#{case.id}:{case.result}" for case in outcome.cases if case.result != "AC"
            )
            raise AuthoringError(f"参考解未通过（先样例后测试点）：{failures}")
        wrong_results = []
        for index, wrong in enumerate(generated.wrong_solutions, 1):
            await self._update(
                task_id, "running", f"正在验证典型错误解法 {index}", "wrong_solutions"
            )
            rejected = await asyncio.wait_for(
                judge_code(generated.problem, python, wrong.code),
                self.settings.ai_stage_timeout_seconds,
            )
            kills = [case.id for case in rejected.cases if case.result in {"WA", "TLE", "MLE"}]
            if not kills or any(case.result in {"CE", "RE", "UNK"} for case in rejected.cases):
                raise AuthoringError(
                    f"错误解法 {index} 未被有效卡错，或无法正常执行；请改进测试点/解法。"
                )
            wrong_results.append(
                {
                    "index": index,
                    "rejected_by": kills,
                    "results": [c.result for c in rejected.cases],
                }
            )
        result = {
            **generated.model_dump(),
            "verification": {
                "reference_passed": True,
                "samples": len(generated.problem.samples),
                "testcases": len(generated.problem.testcases),
                "wrong_solutions": wrong_results,
                "note": "有限测试是质量证据，不是复杂度正确性的数学证明。",
            },
        }
        await self.db.execute(
            """UPDATE ai_tasks SET status='completed',progress='命题完成并通过参考解法验证',
                   stage='completed',result=?,updated_at=? WHERE id=?""",
            (json.dumps(result, ensure_ascii=False), utcnow(), task_id),
        )

    async def _stream_completion(
        self, config: Any, prompt: str, on_usage: UsageCallback | None = None
    ) -> tuple[str, int, int, str]:
        api_key = self.cipher.decrypt(config["encrypted_api_key"]).decode()
        url = str(config["provider_url"]).rstrip("/") + "/chat/completions"
        body = {
            "model": config["model"],
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
        length = 0
        observed = False
        last_update = 0.0

        def tokens() -> tuple[int, int, str]:
            if "prompt_tokens" in usage and "completion_tokens" in usage:
                return (
                    max(0, int(usage["prompt_tokens"])),
                    max(0, int(usage["completion_tokens"])),
                    "provider",
                )
            return (
                max(1, len((SYSTEM_PROMPT + prompt).encode()) // 4),
                max(1, length // 4),
                "estimated",
            )

        timeout = httpx.Timeout(90, connect=10)
        try:
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=False, trust_env=False
            ) as client:
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
                        if event.get("error"):
                            raise AuthoringError("模型流返回错误；请检查服务商配置和额度。")
                        observed = True
                        if event.get("usage"):
                            usage = event["usage"]
                        choices = event.get("choices") or []
                        if choices:
                            content = choices[0].get("delta", {}).get("content")
                            if content:
                                chunks.append(content)
                                length += len(content.encode())
                                if length > 2_000_000:
                                    raise AuthoringError("模型输出超过 2 MB，请缩小命题规模。")
                        if on_usage and time.monotonic() - last_update >= 0.5:
                            await on_usage(*tokens())
                            last_update = time.monotonic()
        finally:
            # Cancellation closes the HTTP context first, then persists observed usage.
            if observed and on_usage:
                await on_usage(*tokens())
        text = "".join(chunks)
        return text, *tokens()
