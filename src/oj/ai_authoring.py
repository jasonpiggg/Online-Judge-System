from __future__ import annotations

import ast
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
from cryptography.fernet import Fernet, InvalidToken
from pydantic import ValidationError

from oj.ai_policy import environment_policy, public_pricing, select_phase_config
from oj.ai_presentation import check_presentation
from oj.ai_prompts import DISPLAY_RULES
from oj.ai_sections import SECTION_FIELDS, merge_section, section_prompt
from oj.ai_transport import PinnedTransport, bounded_sse_lines
from oj.config import Settings
from oj.database import Database
from oj.difficulty import DIFFICULTY_RULES
from oj.judge import judge_code, normalize_output
from oj.languages import get_language
from oj.problem_store import ProblemStore
from oj.schemas import AIModelConfig, GeneratedProblem, Problem, TestCase

SYSTEM_PROMPT = """You are an expert programming contest problem setter. Return only a JSON object:
problem: {id,title,description,input_description,output_description,samples:[{input,output}],
constraints,testcases:[{input,output}],difficulty,tags,time_limit,memory_limit},
reference_solution: executable Python 3 code reading stdin and writing stdout,
brute_solution: an independently structured Python 3 oracle suitable for small random cases,
generator_code: deterministic Python 3 code printing a JSON array of 20-100
valid small input strings,
review: knowledge points, difficulty, exact complexity and test limitations,
coverage: {basic: description of case numbers, boundary: description of case numbers,
scale: description of scale cases and why sizes exercise the relevant complexity},
wrong_solutions: [{code: executable Python 3, reason: typical algorithmic mistake}, ...].
At least 5 UNIQUE test inputs and at least 2 DISTINCT typical wrong algorithms are required.
Each wrong algorithm must run successfully but fail at least one expected output or resource limit.
Cover basic, boundary/adversarial and large-scale inputs; provide full literal inputs, not ellipses.
Both samples and tests MUST pass the reference algorithm. Tests are evidence, not complexity proofs.
Use a safe alphanumeric/underscore/hyphen id. String IO preserves whitespace. No markdown fences.
time_limit is seconds and memory_limit is MB; omit them to inherit language defaults.
All executed programs have a 1 MB stdout/stderr limit. Design declared limits accordingly.
When the user leaves design choices open, prefer compact outputs (counts, a selected term,
or a selected move) over exponentially long enumerations such as full large Hanoi traces.
Do not silently weaken explicit user requirements. State honest bounds and limitations.
Every test/sample must satisfy the input domain; malformed input is not a boundary case.
Keep repeated text and examples concise; reserve enough output budget for all code and review."""

UsageCallback = Callable[[int, int, str, int | None], Awaitable[None]]


class AuthoringError(Exception):
    """Only explicitly safe diagnostics may cross the API boundary."""


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    input_price: float,
    output_price: float,
    unit: int,
    cached_tokens: int = 0,
    cached_input_price: float | None = None,
) -> float:
    cached = min(input_tokens, max(0, cached_tokens))
    cache_price = input_price if cached_input_price is None else cached_input_price
    return round(
        (
            (input_tokens - cached) * input_price
            + cached * cache_price
            + output_tokens * output_price
        )
        / unit,
        10,
    )


def _key(settings: Settings) -> bytes:
    if (
        settings.ai_default_provider_url
        or settings.ai_default_model
        or settings.ai_default_api_key.get_secret_value()
    ) and not settings.ai_encryption_key:
        raise RuntimeError("System model requires a stable OJ_AI_ENCRYPTION_KEY")
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
    if parsed.scheme not in {"https", "http"} or parsed.query or parsed.fragment:
        raise ValueError("provider URL must be HTTP(S), without query or fragment")
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

    async def initialize_system_config(self) -> None:
        """Import server-only defaults once; a restart must never overwrite saved credentials."""
        stored = await self.db.fetchone("SELECT * FROM ai_system_config WHERE id=1")
        if stored is not None:
            if not self.settings.ai_encryption_key:
                raise RuntimeError("Stored system model requires OJ_AI_ENCRYPTION_KEY")
            try:
                self.cipher.decrypt(stored["encrypted_api_key"])
            except InvalidToken:
                raise RuntimeError(
                    "System model cannot be decrypted; restore its encryption key"
                ) from None
            return
        settings = self.settings
        values = (
            settings.ai_default_provider_url,
            settings.ai_default_model,
            settings.ai_default_api_key.get_secret_value(),
        )
        if not any(values):
            return
        if not all(values):
            raise RuntimeError("System model requires URL, model and API key together")
        try:
            config = AIModelConfig(
                provider_url=values[0],  # type: ignore[arg-type]
                model=values[1],
                api_key=values[2],
                input_price=settings.ai_default_input_price,
                output_price=settings.ai_default_output_price,
                price_unit=settings.ai_default_price_unit,
                currency=settings.ai_default_currency,
                cached_input_price=settings.ai_default_cached_input_price,
            )
            provider = await validate_provider_url(
                str(config.provider_url), settings.allow_private_ai_endpoints
            )
        except ValueError:
            # Validation diagnostics may contain the supplied credentials/URL.
            raise RuntimeError(
                "Invalid system model configuration; check server environment"
            ) from None
        await self._adopt_legacy_personal_keys()
        await self.db.execute(
            """INSERT INTO ai_system_config
               (id,provider_url,model,encrypted_api_key,input_price,output_price,price_unit,
                currency,cached_input_price,routing_config)
               VALUES(1,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING""",
            (
                provider,
                config.model,
                self.cipher.encrypt(values[2].encode()),
                config.input_price,
                config.output_price,
                config.price_unit,
                config.currency,
                config.cached_input_price,
                environment_policy(settings),
            ),
        )

    async def sync_system_policy(self) -> None:
        """Explicit operator action: update nonsecret policy, never silently rotate keys."""
        await self.initialize_system_config()
        stored = await self.db.fetchone("SELECT * FROM ai_system_config WHERE id=1")
        if stored is None:
            raise RuntimeError("Configure the system model environment first")
        settings = self.settings
        if not settings.ai_default_model.strip():
            raise RuntimeError("System policy requires a nonempty default model")
        provider = await validate_provider_url(
            settings.ai_default_provider_url, settings.allow_private_ai_endpoints
        )
        if (
            provider != stored["provider_url"]
            or self.cipher.decrypt(stored["encrypted_api_key"]).decode()
            != settings.ai_default_api_key.get_secret_value()
        ):
            raise RuntimeError("Stored credentials differ from environment; policy sync refused")
        await self.db.execute(
            """UPDATE ai_system_config SET model=?,input_price=?,output_price=?,price_unit=?,
               currency=?,cached_input_price=?,routing_config=? WHERE id=1""",
            (
                settings.ai_default_model,
                settings.ai_default_input_price,
                settings.ai_default_output_price,
                settings.ai_default_price_unit,
                settings.ai_default_currency,
                settings.ai_default_cached_input_price,
                environment_policy(settings),
            ),
        )

    async def _adopt_legacy_personal_keys(self) -> None:
        """Preserve old local .ai-key credentials when first enabling the stable system key."""
        rows = await self.db.fetchall("SELECT user_id,encrypted_api_key FROM ai_configs")
        replacements = []
        legacy: Fernet | None = None
        for row in rows:
            encrypted = row["encrypted_api_key"]
            try:
                self.cipher.decrypt(encrypted)
                continue
            except InvalidToken:
                pass
            try:
                if legacy is None:
                    path = self.settings.database_path.parent / ".ai-key"
                    legacy = Fernet(await asyncio.to_thread(path.read_bytes))
                plaintext = legacy.decrypt(encrypted)
            except (OSError, ValueError, InvalidToken):
                raise RuntimeError(
                    "Cannot migrate personal model keys; restore the previous encryption key"
                ) from None
            replacements.append((self.cipher.encrypt(plaintext), row["user_id"], encrypted))
        if replacements:
            async with self.db.connect() as db:
                await db.executemany(
                    """UPDATE ai_configs SET encrypted_api_key=?
                       WHERE user_id=? AND encrypted_api_key=?""",
                    replacements,
                )
                await db.commit()

    async def resolve_config(self, user_id: int) -> dict[str, Any] | None:
        """Backend-only effective configuration. Never serialize this result to clients."""
        personal = await self.db.fetchone("SELECT * FROM ai_configs WHERE user_id=?", (user_id,))
        if personal is not None:
            return {**dict(personal), "config_source": "personal"}
        system = await self.db.fetchone("SELECT * FROM ai_system_config WHERE id=1")
        if system is not None:
            return {**dict(system), "config_source": "system"}
        return None

    async def delete_personal_config(self, user_id: int) -> dict[str, object]:
        await self.db.execute("DELETE FROM ai_configs WHERE user_id=?", (user_id,))
        return await self.get_config(user_id)

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
               (user_id,provider_url,model,encrypted_api_key,input_price,output_price,price_unit,
                currency,cached_input_price)
               VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
               provider_url=excluded.provider_url,model=excluded.model,
               encrypted_api_key=excluded.encrypted_api_key,input_price=excluded.input_price,
               output_price=excluded.output_price,price_unit=excluded.price_unit,
               currency=excluded.currency,cached_input_price=excluded.cached_input_price""",
            (
                user_id,
                provider,
                config.model,
                encrypted,
                config.input_price,
                config.output_price,
                config.price_unit,
                config.currency,
                config.cached_input_price,
            ),
        )
        return await self.get_config(user_id)

    async def get_config(self, user_id: int) -> dict[str, object]:
        row = await self.db.fetchone("SELECT * FROM ai_configs WHERE user_id=?", (user_id,))
        system = await self.db.fetchone("SELECT id FROM ai_system_config WHERE id=1")
        flags: dict[str, object] = {
            "source": "personal" if row is not None else "system" if system else "none",
            "system_configured": system is not None,
            "personal_configured": row is not None,
            "api_key_configured": row is not None or system is not None,
        }
        if row is None:
            return flags
        return {
            **{
                key: row[key]
                for key in (
                    "provider_url",
                    "model",
                    "input_price",
                    "output_price",
                    "price_unit",
                    "currency",
                    "cached_input_price",
                )
            },
            **flags,
        }

    async def recover(self) -> None:
        # Never replay paid requests after a server restart.
        await self.db.execute(
            """UPDATE ai_tasks SET status='failed',progress='服务中断',
               error='服务重启中断了任务；已保留观测到的用量，请人工决定是否重新生成。',
               updated_at=? WHERE status IN ('pending','running')""",
            (utcnow(),),
        )

    async def create(
        self,
        user_id: int,
        requirement: str,
        problem_id: str | None,
        draft_id: str | None = None,
        action: str = "generate",
        target_section: str = "all",
    ) -> str:
        task_id = "ai-" + secrets.token_urlsafe(12)
        now = utcnow()
        await self.db.execute(
            """INSERT INTO ai_tasks
               (id,user_id,requirement,problem_id,draft_id,action,target_section,
                status,progress,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                task_id,
                user_id,
                requirement,
                problem_id,
                draft_id,
                action,
                target_section,
                "pending",
                "任务已进入队列",
                now,
                now,
            ),
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
            "UPDATE ai_tasks SET status='cancelled',progress='任务已中断',updated_at=? "
            "WHERE id=? AND status IN ('pending','running')",
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
            elif isinstance(exc, httpx.TransportError):
                message = "模型连接或流式传输中断；已保留已观测用量和可用初稿，不会自动重试收费。"
            elif isinstance(exc, json.JSONDecodeError):
                message = "模型返回的 JSON 不完整或格式错误；已保留可用输出，不会自动重试收费。"
            else:
                message = "AI 生成或验证失败。请检查服务连接、JSON 格式和模型配置后手动重试。"
            await self.db.execute(
                "UPDATE ai_tasks SET status='failed',progress='命题失败',error=?,updated_at=? "
                "WHERE id=?",
                (message, utcnow(), task_id),
            )

    @staticmethod
    def _schema_issues(exc: ValueError) -> str:
        if isinstance(exc, ValidationError):
            return json.dumps(
                [
                    {"field": ".".join(map(str, issue["loc"])), "error": issue["type"]}
                    for issue in exc.errors()[:20]
                ]
            )
        return "Malformed JSON. Return one complete JSON object using the exact required keys."

    @staticmethod
    def _syntax_issues(generated: GeneratedProblem) -> str:
        programs = {
            "reference_solution": generated.reference_solution,
            "brute_solution": generated.brute_solution,
            "generator_code": generated.generator_code,
            **{
                f"wrong_solutions[{i}]": item.code
                for i, item in enumerate(generated.wrong_solutions)
            },
        }
        issues = []
        for field, code in programs.items():
            if not code:
                continue
            try:
                ast.parse(code)
            except (SyntaxError, RecursionError, MemoryError) as exc:
                issues.append(f"{field}: {type(exc).__name__}, line {getattr(exc, 'lineno', '?')}")
        return "\n".join(issues)

    async def _author(self, task_id: str) -> None:
        await self._update(task_id, "running", "正在分析命题需求", "analysis")
        task_row = await self.db.fetchone("SELECT * FROM ai_tasks WHERE id=?", (task_id,))
        if task_row is None:
            return
        config = await self.resolve_config(task_row["user_id"])
        if config is None:
            raise AuthoringError("请先配置模型提供商、模型名称和密钥")
        reference = ""
        routing_context = ""
        base_problem: Problem | None = None
        draft_revision: int | None = None
        if task_row["problem_id"]:
            existing = await self.problems.get(task_row["problem_id"])
            if existing:
                base_problem = existing
                reference = "\nExisting problem to adapt:\n" + existing.model_dump_json()
                routing_context = existing.difficulty + " " + " ".join(existing.tags)
        if task_row["draft_id"]:
            draft = await self.db.fetchone(
                "SELECT * FROM problem_drafts WHERE id=?", (task_row["draft_id"],)
            )
            if draft:
                draft_revision = draft["revision"]
                reference += "\nCurrent authoring draft:\n" + draft["problem_json"]
                draft_problem = json.loads(draft["problem_json"])
                routing_context += " " + str(draft_problem.get("difficulty", ""))
                routing_context += " " + " ".join(draft_problem.get("tags", []))
                if draft_problem:
                    base_problem = Problem.model_validate(draft_problem, context={"legacy": True})
        target = task_row["target_section"] or "all"
        scoped = task_row["action"] == "revise" and target in SECTION_FIELDS
        if scoped and base_problem is None:
            raise AuthoringError("局部修改需要已有题目或完整草稿，请先选择修改对象。")
        prompt = (
            f"Authoring action: {task_row['action']}\n"
            f"Target section: {task_row['target_section']}\n"
            "When the target is not 'all', keep unrelated fields semantically unchanged.\n"
            f"Authoring requirement:\n{task_row['requirement']}{reference}"
        )
        if scoped and base_problem is not None:
            # Do not send hidden testcases or duplicate the same problem/draft context.
            context = base_problem.model_dump(exclude={"testcases"})
            prompt = (
                f"Target section: {target}\nRequirement: {task_row['requirement']}\n"
                "Existing problem:\n" + json.dumps(context, ensure_ascii=False)
            )
        phases: dict[str, dict[str, Any]] = {}
        first_draft_issues = ""
        await self.db.execute(
            "UPDATE ai_tasks SET currency=? WHERE id=?", (config["currency"], task_id)
        )
        for phase, progress in [
            ("generation", "正在流式生成题目"),
            ("critique", "正在第二次调用模型，批判并改进完整结果"),
        ]:
            phase_config = select_phase_config(
                config,
                phase,
                task_row["action"],
                task_row["target_section"] or "all",
                task_row["requirement"],
                routing_context,
            )
            phase_config["_task_id"] = task_id
            if scoped:
                phase_config["system_prompt"] = section_prompt(target)
                phase_config["max_output_tokens"] = self.settings.ai_section_max_output_tokens
            tier_labels = {
                "flash": "Flash",
                "quality": "高质量",
                "personal": "个人",
                "default": "系统默认",
            }
            await self._update(
                task_id, "running", progress + " · " + tier_labels[phase_config["tier"]], phase
            )

            async def usage_update(
                i: int,
                o: int,
                source: str,
                cached: int | None = None,
                phase: str = phase,
                selected: dict[str, Any] = phase_config,
            ) -> None:
                if cached is None:
                    cached = phases.get(phase, {}).get("cached_input_tokens")
                cost = calculate_cost(
                    i,
                    o,
                    selected["input_price"],
                    selected["output_price"],
                    selected["price_unit"],
                    cached or 0,
                    selected.get("cached_input_price"),
                )
                phases[phase] = {
                    "input_tokens": i,
                    "output_tokens": o,
                    "source": source,
                    "cached_input_tokens": cached,
                    "cost": cost,
                    "tier": selected["tier"],
                    "reasoning_effort": selected.get("reasoning_effort"),
                    "json_mode": selected.get("json_mode", True),
                    "reasoning_tokens": selected.get("_reasoning_tokens"),
                    "output_token_limit": selected.get(
                        "max_output_tokens", self.settings.ai_max_output_tokens
                    ),
                    "routing_reason": selected["routing_reason"],
                    "pricing": public_pricing(selected),
                }
                total_in = sum(p["input_tokens"] for p in phases.values())
                total_out = sum(p["output_tokens"] for p in phases.values())
                total_source = (
                    "provider"
                    if all(p["source"] == "provider" for p in phases.values())
                    else "estimated"
                )
                details = {
                    "phases": phases,
                    "config_source": config["config_source"],
                    "pricing": public_pricing(config),
                }
                await self.db.execute(
                    """UPDATE ai_tasks SET input_tokens=?,output_tokens=?,usage_source=?,
                           cost=?,usage_details=?,updated_at=? WHERE id=?""",
                    (
                        total_in,
                        total_out,
                        total_source,
                        round(sum(p["cost"] for p in phases.values()), 10),
                        json.dumps(details),
                        utcnow(),
                        task_id,
                    ),
                )

            text, i, o, source = await asyncio.wait_for(
                self._stream_completion(phase_config, prompt, usage_update),
                self.settings.ai_stage_timeout_seconds,
            )
            await usage_update(i, o, source)
            if scoped:
                assert base_problem is not None
                try:
                    proposal = merge_section(base_problem, target, _extract_json(text))
                except ValueError as exc:
                    if phase != "generation":
                        raise
                    # Use the already-planned critique to repair structure; no extra paid call.
                    first_draft_issues = self._schema_issues(exc)
                    await self._update(
                        task_id, "running", "首稿结构有误，将交给原定复审阶段修正", "critique"
                    )
                else:
                    proposal["reviewed"] = phase == "critique"
                    proposal["source_draft_revision"] = draft_revision
                    await self.db.execute(
                        "UPDATE ai_tasks SET result=? WHERE id=?",
                        (json.dumps(proposal, ensure_ascii=False), task_id),
                    )
            elif phase == "generation":
                # Retain a valid first draft if the paid critique later times out/fails.
                try:
                    first = GeneratedProblem.model_validate(_extract_json(text))
                except ValueError as exc:
                    first_draft_issues = self._schema_issues(exc)
                else:
                    first_draft_issues = self._syntax_issues(first)
                    await self.db.execute(
                        "UPDATE ai_tasks SET result=? WHERE id=?",
                        (first.model_dump_json(), task_id),
                    )
            if phase == "generation":
                prompt = (
                    (
                        "Review ONLY this section edit for correctness and clarity. Fix incorrect "
                        "sample outputs, preserve other sections, "
                        "return the same compact edit JSON.\n"
                        if scoped
                        else "Critically inspect this draft against the original requirement. "
                        "Fix knowledge/difficulty, boundary and scale coverage, outputs and "
                        "two typical wrong algorithms. Return the COMPLETE improved JSON.\n"
                    )
                    + prompt
                    + "\nLocal schema feedback (must fix):\n"
                    + (
                        first_draft_issues
                        or "Schema accepted; still check semantics and input validity."
                    )
                    + "\nDRAFT:\n"
                    + text
                )
        if scoped:
            await self._update(
                task_id, "completed", "局部修改建议已生成并复审，待人工采纳", "completed"
            )
            return
        generated = GeneratedProblem.model_validate(_extract_json(text))
        await self._validate_generated(task_id, generated, task_row, draft_revision)

    async def _validate_generated(
        self,
        task_id: str,
        generated: GeneratedProblem,
        task_row: Any,
        draft_revision: int | None,
        initial_problem: dict[str, Any] | None = None,
    ) -> None:
        await self.db.execute(
            "UPDATE ai_tasks SET result=? WHERE id=?", (generated.model_dump_json(), task_id)
        )
        await self._update(task_id, "running", "正在验证参考解的全部样例与测试点", "validation")
        try:
            check_presentation(generated.model_dump())
        except ValueError as exc:
            raise AuthoringError(str(exc)) from exc
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
        differential = await self._verify_differential(generated, python, task_id)
        mutation_score = round(
            sum(bool(item["rejected_by"]) for item in wrong_results) / len(wrong_results) * 100,
            2,
        )
        result = {
            **generated.model_dump(),
            "verification": {
                "reference_passed": True,
                "samples": len(generated.problem.samples),
                "testcases": len(generated.problem.testcases),
                "wrong_solutions": wrong_results,
                "independent_oracle": differential,
                "mutation_score": mutation_score,
                "quality_gate_passed": differential["status"] == "passed" and mutation_score == 100,
                "note": "有限测试是质量证据，不是复杂度正确性的数学证明。",
            },
        }
        if initial_problem is not None:
            result["initial_problem"] = initial_problem
        await self.db.execute(
            "UPDATE ai_tasks SET result=?,updated_at=? WHERE id=?",
            (json.dumps(result, ensure_ascii=False), utcnow(), task_id),
        )
        await self._save_ready_draft(task_row, task_id, result, draft_revision)

    async def _verify_differential(
        self, generated: GeneratedProblem, python: Any, task_id: str
    ) -> dict[str, Any]:
        if not generated.brute_solution or not generated.generator_code:
            return {
                "status": "not_provided",
                "generated_cases": 0,
                "message": "缺少独立暴力解或随机数据生成器，草稿不会进入可发布状态。",
            }
        await self._update(task_id, "running", "正在运行独立 oracle 随机对拍", "differential")
        harness = generated.problem.model_copy(
            update={
                # Data generation is not the submitted solver: use its own bounded budget.
                # Tiny solver limits must not kill Python's JSON/random module startup.
                "time_limit": 3.0,
                "memory_limit": 128,
                "testcases": [TestCase(input="", output="")],
            }
        )
        generated_output = await asyncio.wait_for(
            judge_code(harness, python, generated.generator_code),
            self.settings.ai_stage_timeout_seconds,
        )
        generator_case = generated_output.cases[0]
        if generator_case.result not in {"AC", "WA"}:
            raise AuthoringError(f"随机数据生成器未能安全执行（{generator_case.result}）")
        try:
            random_inputs = json.loads(generator_case.output)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AuthoringError("随机数据生成器必须输出 JSON 字符串数组") from exc
        if (
            not isinstance(random_inputs, list)
            or not 20 <= len(random_inputs) <= 100
            or any(
                not isinstance(value, str) or len(value.encode()) > 1_000_000
                for value in random_inputs
            )
        ):
            raise AuthoringError("随机数据生成器必须输出 20–100 个大小受限的输入字符串")
        if len(set(random_inputs)) != len(random_inputs):
            raise AuthoringError("随机数据生成器输出了重复输入")
        comparison = generated.problem.model_copy(
            update={"testcases": [TestCase(input=value, output="") for value in random_inputs]}
        )
        reference, oracle = await asyncio.gather(
            judge_code(comparison, python, generated.reference_solution),
            judge_code(comparison, python, generated.brute_solution),
        )
        pairs = zip(reference.cases, oracle.cases, strict=True)
        for index, (actual, expected) in enumerate(pairs, 1):
            if actual.result not in {"AC", "WA"} or expected.result not in {"AC", "WA"}:
                raise AuthoringError(f"随机对拍第 {index} 组发生运行错误或超时")
            if normalize_output(actual.output) != normalize_output(expected.output):
                raise AuthoringError(f"参考解与独立 oracle 在随机对拍第 {index} 组结果不一致")
        return {
            "status": "passed",
            "generated_cases": len(random_inputs),
            "message": "参考解与独立暴力解在受限随机输入上输出一致。",
        }

    async def _save_ready_draft(
        self, task_row: Any, task_id: str, result: dict[str, Any], source_revision: int | None
    ) -> None:
        now = utcnow()
        draft_id = task_row["draft_id"] or "draft-" + secrets.token_urlsafe(12)
        current = await self.db.fetchone("SELECT * FROM problem_drafts WHERE id=?", (draft_id,))
        conflict_message = "草稿已修改、归档或发布；AI 结果和用量已保留，请人工检查后另存。"
        if task_row["draft_id"] and (
            current is None
            or current["owner_id"] != task_row["user_id"]
            or current["revision"] != source_revision
            or current["status"] in {"archived", "published"}
        ):
            raise AuthoringError(conflict_message)
        revision = int(current["revision"]) + 1 if current else 1
        created_at = current["created_at"] if current else now
        reference_solution = result["reference_solution"]
        # Persist exactly the assets that were verified, never reuse an older oracle.
        brute_solution = result.get("brute_solution", "")
        generator_code = result.get("generator_code", "")
        review = {
            "review": result["review"],
            "coverage": result["coverage"],
            "wrong_solutions": result["wrong_solutions"],
            "verification": result["verification"],
        }
        ready = bool(result["verification"].get("quality_gate_passed"))
        draft_status = "ready" if ready else "draft"
        snapshot = {
            "id": draft_id,
            "base_problem_id": task_row["problem_id"],
            "status": draft_status,
            "requirement": task_row["requirement"],
            "problem": result["problem"],
            "reference_solution": reference_solution,
            "brute_solution": brute_solution,
            "generator_code": generator_code,
            "review": review,
            "revision": revision,
            "created_at": created_at,
            "updated_at": now,
        }
        verification_id = "verify-" + secrets.token_urlsafe(12)
        async with self.db.connect() as db:
            if current:
                cursor = await db.execute(
                    """UPDATE problem_drafts SET base_problem_id=?,status=?,
                       requirement=?,problem_json=?,reference_solution=?,brute_solution=?,
                       generator_code=?,review_json=?,revision=?,updated_at=?
                       WHERE id=? AND owner_id=? AND revision=?
                       AND status NOT IN ('archived','published')""",
                    (
                        task_row["problem_id"],
                        draft_status,
                        task_row["requirement"],
                        json.dumps(result["problem"], ensure_ascii=False),
                        reference_solution,
                        brute_solution,
                        generator_code,
                        json.dumps(review, ensure_ascii=False),
                        revision,
                        now,
                        draft_id,
                        task_row["user_id"],
                        source_revision,
                    ),
                )
                # Compare-and-swap also protects changes between the read and this write.
                if cursor.rowcount != 1:
                    raise AuthoringError(conflict_message)
            else:
                await db.execute(
                    """INSERT INTO problem_drafts
                       (id,owner_id,base_problem_id,status,requirement,problem_json,
                        reference_solution,brute_solution,generator_code,review_json,
                        revision,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        draft_id,
                        task_row["user_id"],
                        task_row["problem_id"],
                        draft_status,
                        task_row["requirement"],
                        json.dumps(result["problem"], ensure_ascii=False),
                        reference_solution,
                        brute_solution,
                        generator_code,
                        json.dumps(review, ensure_ascii=False),
                        revision,
                        now,
                        now,
                    ),
                )
            await db.execute(
                """INSERT INTO problem_draft_revisions
                   (draft_id,revision,source,snapshot_json,change_summary,created_at)
                   VALUES(?,?,?,?,?,?)""",
                (
                    draft_id,
                    revision,
                    "ai",
                    json.dumps(snapshot, ensure_ascii=False),
                    f"AI {task_row['action']} · {task_row['target_section']}",
                    now,
                ),
            )
            await db.execute(
                """INSERT INTO verification_runs
                   (id,draft_id,status,report_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?)""",
                (
                    verification_id,
                    draft_id,
                    "passed" if ready else "failed",
                    json.dumps(result["verification"], ensure_ascii=False),
                    now,
                    now,
                ),
            )
            # Expose completion only once the matching draft and verification are committed.
            await db.execute(
                """UPDATE ai_tasks SET draft_id=?,status='completed',
                   progress='命题完成并通过参考解法验证',stage='completed',
                   updated_at=? WHERE id=?""",
                (draft_id, now, task_id),
            )
            await db.commit()

    async def _stream_completion(
        self, config: Any, prompt: str, on_usage: UsageCallback | None = None
    ) -> tuple[str, int, int, str]:
        api_key = self.cipher.decrypt(config["encrypted_api_key"]).decode()
        url = str(config["provider_url"]).rstrip("/") + "/chat/completions"
        system_prompt = config.get("system_prompt", SYSTEM_PROMPT)
        if DIFFICULTY_RULES not in system_prompt:
            system_prompt += DIFFICULTY_RULES
        if DISPLAY_RULES not in system_prompt:
            system_prompt += DISPLAY_RULES
        body = {
            "model": config["model"],
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": config.get("max_output_tokens", self.settings.ai_max_output_tokens),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        }
        chunks: list[str] = []
        if config.get("json_mode", True):
            body["response_format"] = {"type": "json_object"}
        if config.get("reasoning_effort"):
            body["reasoning_effort"] = config["reasoning_effort"]
        usage: dict[str, Any] = {}
        length = 0
        reasoning_length = 0
        observed = False
        last_update = 0.0
        finish_reason = None

        def tokens() -> tuple[int, int, str]:
            if "prompt_tokens" in usage and "completion_tokens" in usage:
                return (
                    max(0, int(usage["prompt_tokens"])),
                    max(0, int(usage["completion_tokens"])),
                    "provider",
                )
            return (
                max(1, len((system_prompt + prompt).encode()) // 4),
                max(1, (length + reasoning_length) // 4),
                "estimated",
            )

        def cached_tokens() -> int | None:
            details = usage.get("prompt_tokens_details") or {}
            value = details.get("cached_tokens")
            if not isinstance(value, int) or isinstance(value, bool):
                return None
            return min(tokens()[0], max(0, value))

        timeout = httpx.Timeout(self.settings.ai_stream_read_timeout_seconds, connect=10)
        try:
            transport = await asyncio.to_thread(
                PinnedTransport, allow_private=self.settings.allow_private_ai_endpoints
            )
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=False, trust_env=False, transport=transport
            ) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=body,
                ) as response:
                    response.raise_for_status()
                    # SSE metadata/heartbeats can dwarf actual text with a large Token budget.
                    # Scale the cumulative wire cap, retaining per-event and 2 MB text limits.
                    async for line in bounded_sse_lines(
                        response, max_wire_bytes=max(8_000_000, int(body["max_tokens"]) * 1024)
                    ):
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
                            reasoning = (usage.get("completion_tokens_details") or {}).get(
                                "reasoning_tokens"
                            )
                            if isinstance(reasoning, int) and not isinstance(reasoning, bool):
                                config["_reasoning_tokens"] = min(tokens()[1], max(0, reasoning))
                        choices = event.get("choices") or []
                        if choices:
                            finish_reason = choices[0].get("finish_reason") or finish_reason
                            delta = choices[0].get("delta", {})
                            # Count reasoning bytes for partial-use estimates, never expose them.
                            reasoning_length += len((delta.get("reasoning_content") or "").encode())
                            content = delta.get("content")
                            if content:
                                chunks.append(content)
                                length += len(content.encode())
                                if length > 2_000_000:
                                    raise AuthoringError("模型输出超过 2 MB，请缩小命题规模。")
                        if on_usage and time.monotonic() - last_update >= 0.5:
                            await on_usage(*tokens(), cached_tokens())
                            if config.get("_on_content"):
                                await config["_on_content"]("".join(chunks))
                            last_update = time.monotonic()
        finally:
            # Cancellation closes the HTTP context first, then persists observed usage.
            if observed and on_usage:
                await on_usage(*tokens(), cached_tokens())
            if config.get("_on_content") and chunks:
                await config["_on_content"]("".join(chunks))
            if chunks and config.get("_task_id"):
                # Preserve incomplete output for download, never treat it as a validated problem.
                await self.db.execute(
                    "UPDATE ai_tasks SET result=? WHERE id=? AND "
                    "(result IS NULL OR json_extract(result,'$.kind')='incomplete_output')",
                    (
                        json.dumps({"kind": "incomplete_output", "text": "".join(chunks)}),
                        config["_task_id"],
                    ),
                )
        text = "".join(chunks)
        if finish_reason == "length":
            raise AuthoringError(
                f"模型输出达到 {body['max_tokens']} Token 上限（含推理），结果可能不完整。"
                "请缩小任务或由管理员调整输出上限；不会自动重试。"
            )
        return text, *tokens()
