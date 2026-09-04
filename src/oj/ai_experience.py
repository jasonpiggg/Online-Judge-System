"""Durable browser AI workflows layered over the existing provider and quality gates."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import secrets
from typing import Any

from pydantic import ValidationError

from oj.ai_authoring import (
    AIAuthoringManager,
    AuthoringError,
    UsageCallback,
    _extract_json,
    calculate_cost,
    utcnow,
)
from oj.ai_policy import select_phase_config
from oj.ai_prompts import (
    ASSETS_PROMPT,
    ASSISTANT_PROMPT,
    PROMPT_VERSION,
    REVIEW_PROMPT,
    STATEMENT_PROMPT,
)
from oj.ai_sections import SECTION_FIELDS, merge_section, section_prompt
from oj.errors import APIError
from oj.schemas import GeneratedProblem, Problem


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(compact(value).encode()).hexdigest()


def complete_fields(text: str) -> dict[str, Any]:
    """Only expose complete JSON values, never speculative parsing of incomplete strings."""
    fields: dict[str, Any] = {}
    for name in (
        "title",
        "description",
        "input_description",
        "output_description",
        "constraints",
        "samples",
        "reference_solution",
        "review",
    ):
        match = re.search(r'"' + name + r'"\s*:\s*', text)
        if match:
            try:
                value, _ = json.JSONDecoder().raw_decode(text[match.end() :])
            except ValueError:
                continue
            if (name == "samples" and isinstance(value, list) and all(
                isinstance(item, dict) and isinstance(item.get("input"), str)
                and isinstance(item.get("output"), str) for item in value
            )) or (name != "samples" and isinstance(value, str)):
                fields[name] = value
    return fields


def merge_patch(
    base: dict[str, Any],
    patch: dict[str, Any],
    path: str = "",
) -> dict[str, Any]:
    if not isinstance(patch, dict):
        raise ValueError("Review patch must be an object")
    result = dict(base)
    allowed = (
        set(GeneratedProblem.model_fields)
        if not path
        else set(Problem.model_fields)
        if path == "problem"
        else set(base)
    )
    for key, value in patch.items():
        if key not in allowed:
            raise ValueError(f"Unknown patch field: {key}")
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            result[key] = merge_patch(base[key], value, f"{path}.{key}".lstrip("."))
        else:
            result[key] = value
    return result


class AIExperience(AIAuthoringManager):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.intake_lock = asyncio.Lock()
        self.provider_slots = asyncio.Semaphore(self.settings.ai_model_concurrency)

    async def create_request(
        self,
        user_id: int,
        request: dict[str, Any],
        key: str | None = None,
        *,
        kind: str = "authoring",
        conversation_id: str | None = None,
    ) -> str:
        if key is not None and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", key):
            raise APIError(400, "invalid Idempotency-Key")
        request_hash = digest({"kind": kind, "conversation_id": conversation_id, **request})
        async with self.intake_lock:
            if key:
                prior = await self.db.fetchone(
                    "SELECT * FROM ai_request_keys WHERE user_id=? AND request_key=?",
                    (user_id, key),
                )
                if prior:
                    if prior["fingerprint"] != request_hash:
                        raise APIError(409, "同一请求标识不能用于不同内容")
                    return str(prior["task_id"])
            config = await self.resolve_config(user_id)
            if config is None and request.get("action") == "verify":
                config = {"encrypted_api_key": self.cipher.encrypt(b"")}
            if config is None:
                raise APIError(400, "请先配置可用的 AI 模型")
            payload = dict(request)
            if payload.get("resume_task_id"):
                prior_task = await self.db.fetchone(
                    "SELECT t.result,c.payload FROM ai_tasks t JOIN ai_task_context c "
                    "ON c.task_id=t.id WHERE t.id=? AND t.user_id=? "
                    "AND t.status IN ('failed','cancelled') AND c.kind='authoring'",
                    (payload["resume_task_id"], user_id),
                )
                if not prior_task:
                    raise APIError(404, "可恢复任务不存在")
                previous = json.loads(prior_task["payload"])
                for field in ("requirement", "problem_id", "draft_id", "action", "target_section"):
                    if payload.get(field) != previous.get(field):
                        raise APIError(409, "需求或目标已变更，不能复用旧阶段")
                payload["resume_candidate"] = json.loads(prior_task["result"] or "{}")
            problem_id = payload.get("problem_id")
            if problem_id:
                problem = await self.problems.get(problem_id)
                if not problem:
                    raise APIError(404, "problem not found")
                payload["base_problem"] = problem.model_dump()
            if payload.get("draft_id"):
                draft = await self.db.fetchone(
                    "SELECT * FROM problem_drafts WHERE id=? AND owner_id=?",
                    (payload["draft_id"], user_id),
                )
                if not draft:
                    raise APIError(404, "problem draft not found")
                if draft["status"] in {"archived", "published"}:
                    raise APIError(409, "此草稿已归档或发布，请从题目创建新的编辑草稿")
                payload["base_problem"] = json.loads(draft["problem_json"])
                payload["source_revision"] = draft["revision"]
                payload["assets"] = {
                    k: draft[k] for k in ("reference_solution", "brute_solution", "generator_code")
                }
                payload["assets"].update(json.loads(draft["review_json"]))
            if payload.get("resume_task_id") and (
                previous.get("base_problem") != payload.get("base_problem")
                or previous.get("source_revision") != payload.get("source_revision")
            ):
                raise APIError(409, "原题或草稿版本已变化，请合并后创建新任务")
            if kind == "assistant":
                # Explicit whitelist: never serialize the Problem model to a tutoring request.
                base = payload.pop("base_problem")
                payload["problem"] = {
                    k: base[k]
                    for k in (
                        "id",
                        "title",
                        "description",
                        "input_description",
                        "output_description",
                        "constraints",
                        "samples",
                        "difficulty",
                        "tags",
                    )
                }
                if payload.get("submission_id"):
                    submission = await self.db.fetchone(
                        "SELECT user_id,problem_id,status,score,counts,compile_info,"
                        "run_info,error_info "
                        "FROM submissions WHERE id=?",
                        (payload["submission_id"],),
                    )
                    if not submission or submission["user_id"] != user_id:
                        raise APIError(404, "submission not found")
                    if submission["problem_id"] != problem_id:
                        raise APIError(400, "提交与当前题目不匹配")
                    payload["submission"] = {
                        k: submission[k]
                        for k in (
                            "status",
                            "score",
                            "counts",
                            "compile_info",
                            "run_info",
                            "error_info",
                        )
                    }
                if len(compact(payload).encode()) > 100000:
                    raise APIError(400, "当前题目与代码超过上下文容量，请选择较小的代码片段")
            fingerprint = digest({"kind": kind, "conversation": conversation_id, **payload})
            running = await self.db.fetchone(
                "SELECT t.id FROM ai_tasks t JOIN ai_task_context c ON c.task_id=t.id "
                "WHERE t.user_id=? AND c.fingerprint=? AND t.status IN ('pending','running')",
                (user_id, fingerprint),
            )
            if running:
                if key:
                    await self.db.execute(
                        "INSERT INTO ai_request_keys VALUES(?,?,?,?)",
                        (user_id, key, request_hash, running["id"]),
                    )
                return str(running["id"])
            count = await self.db.fetchone(
                "SELECT COUNT(*) n FROM ai_tasks WHERE user_id=? "
                "AND status IN ('pending','running')",
                (user_id,),
            )
            if count and count["n"] >= self.settings.ai_user_active_tasks:
                raise APIError(429, "已有两个 AI 任务进行中，请等待完成或停止其中一个")
            if kind == "assistant":
                history = await self.db.fetchall(
                    "SELECT c.payload,t.result FROM ai_task_context c "
                    "JOIN ai_tasks t ON t.id=c.task_id "
                    "WHERE c.conversation_id=? AND t.status='completed' ORDER BY t.created_at DESC "
                    "LIMIT 8",
                    (conversation_id,),
                )
                turns = []
                budget = 40000
                for row in history:
                    previous = json.loads(row["payload"])
                    answer = json.loads(row["result"] or "{}")
                    turn = {"user": previous.get("message"), "assistant": answer.get("text", "")}
                    budget -= len(compact(turn).encode())
                    if budget < 0:
                        break
                    turns.append(turn)
                payload["history"] = list(reversed(turns))
            config = dict(config)
            config["_output_limits"] = dict(self.settings.ai_model_output_limits)
            config["encrypted_api_key"] = config["encrypted_api_key"].decode()
            config_blob = self.cipher.encrypt(compact(config).encode())
            task_id, now = "ai-" + secrets.token_urlsafe(12), utcnow()
            async with self.db.connect() as db:
                await db.execute("BEGIN IMMEDIATE")
                await db.execute(
                    "INSERT INTO ai_tasks(id,user_id,requirement,problem_id,draft_id,action,"
                    "target_section,status,progress,stage,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,'pending','等待模型连接','queued',?,?)",
                    (
                        task_id,
                        user_id,
                        payload.get("requirement", payload.get("message", "")),
                        problem_id,
                        payload.get("draft_id"),
                        payload.get("action", "assist"),
                        payload.get("target_section", "all"),
                        now,
                        now,
                    ),
                )
                await db.execute(
                    "INSERT INTO ai_task_context(task_id,kind,conversation_id,payload,"
                    "config_snapshot,"
                    "fingerprint,stage_started_at) VALUES(?,?,?,?,?,?,?)",
                    (
                        task_id,
                        kind,
                        conversation_id,
                        compact(payload),
                        config_blob,
                        fingerprint,
                        now,
                    ),
                )
                if key:
                    await db.execute(
                        "INSERT INTO ai_request_keys VALUES(?,?,?,?)",
                        (user_id, key, request_hash, task_id),
                    )
                await db.commit()
            task = asyncio.create_task(self._run(task_id))
            self.tasks[task_id] = task
            task.add_done_callback(lambda _: self.tasks.pop(task_id, None))
            return task_id

    async def _update(self, task_id: str, status: str, progress: str, stage: str) -> None:
        old = await self.db.fetchone("SELECT stage FROM ai_tasks WHERE id=?", (task_id,))
        await super()._update(task_id, status, progress, stage)
        await self.db.execute(
            "UPDATE ai_task_context SET version=version+1,stage_started_at="
            "CASE WHEN ? THEN ? ELSE stage_started_at END WHERE task_id=?",
            (old is None or old["stage"] != stage, utcnow(), task_id),
        )

    async def _run(self, task_id: str) -> None:
        try:
            await super()._run(task_id)
        finally:
            await self.db.execute(
                "UPDATE ai_task_context SET version=version+1 WHERE task_id=?", (task_id,)
            )

    async def _stream_completion(
        self,
        config: Any,
        prompt: str,
        on_usage: UsageCallback | None = None,
    ) -> tuple[str, int, int, str]:
        task_id = config.get("_task_id")
        waiting = None
        if self.provider_slots.locked() and task_id:
            waiting = await self.db.fetchone(
                "SELECT stage,progress FROM ai_tasks WHERE id=?", (task_id,)
            )
            await self._update(task_id, "running", "正在排队等待模型调用", "waiting_model")
        async with self.provider_slots:
            if waiting:
                await self._update(task_id, "running", waiting["progress"], waiting["stage"])
            return await super()._stream_completion(config, prompt, on_usage)

    async def _preview(self, task_id: str, data: dict[str, Any]) -> None:
        await self.db.execute(
            "UPDATE ai_task_context SET preview=?,version=version+1 WHERE task_id=?",
            (compact(data), task_id),
        )

    async def _author(self, task_id: str) -> None:
        context = await self.db.fetchone(
            "SELECT * FROM ai_task_context WHERE task_id=?", (task_id,)
        )
        if context is None:
            await super()._author(task_id)
            return
        payload = json.loads(context["payload"])
        if context["kind"] != "assistant" and payload.get("workflow_version", 1) == 1:
            await super()._author(task_id)
            return
        config = json.loads(self.cipher.decrypt(context["config_snapshot"]))
        config["encrypted_api_key"] = config["encrypted_api_key"].encode()
        task_row = await self.db.fetchone("SELECT * FROM ai_tasks WHERE id=?", (task_id,))
        phases: dict[str, Any] = {}
        preview: dict[str, Any] = {}

        async def invoke(phase: str, system: str, data: Any, *, assistant: bool = False) -> str:
            selected = select_phase_config(
                config,
                "generation" if phase in {"statement", "assistant"} else "critique",
                payload.get("action", "generate"),
                payload.get("target_section", "all"),
                payload.get("requirement", payload.get("message", "")),
                compact(payload.get("base_problem", {}))[:2000],
            )
            selected.update(
                {
                    "system_prompt": system + "\nProtocol: " + PROMPT_VERSION,
                    "json_mode": False if assistant else selected.get("json_mode", True),
                    "_task_id": task_id,
                }
            )
            if assistant:
                selected["max_output_tokens"] = self.settings.ai_assistant_max_output_tokens
            elif phase.startswith("section") or phase == "review_only":
                selected["max_output_tokens"] = self.settings.ai_section_max_output_tokens
            else:
                selected["max_output_tokens"] = self.settings.ai_max_output_tokens
            model_limit = config.get("_output_limits", {}).get(selected["model"])
            if model_limit:
                selected["max_output_tokens"] = min(selected["max_output_tokens"], model_limit)
            labels = {
                "statement": "正在生成题面与参考解",
                "assets": "正在设计测试与独立解法",
                "critique": "正在复审与修正",
                "repair": "正在定向修复（最多一次）",
                "assistant": "正在生成回答",
                "section": "正在生成局部建议",
                "section_review": "正在复审局部建议",
                "review_only": "正在审查草稿",
            }
            await self._update(task_id, "running", labels[phase], phase)

            async def content(text: str) -> None:
                if assistant:
                    preview["text"] = text
                else:
                    preview.update(complete_fields(text))
                await self._preview(task_id, preview)

            async def usage(i: int, o: int, source: str, cached: int | None = None) -> None:
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
                    "output_token_limit": selected.get(
                        "max_output_tokens", self.settings.ai_max_output_tokens
                    ),
                }
                await self.db.execute(
                    "UPDATE ai_tasks SET input_tokens=?,output_tokens=?,cost=?,currency=?,"
                    "usage_source=?,usage_details=?,updated_at=? WHERE id=?",
                    (
                        sum(v["input_tokens"] for v in phases.values()),
                        sum(v["output_tokens"] for v in phases.values()),
                        sum(v["cost"] for v in phases.values()),
                        config["currency"],
                        "provider"
                        if all(v["source"] == "provider" for v in phases.values())
                        else "estimated",
                        compact({"phases": phases, "prompt_version": PROMPT_VERSION}),
                        utcnow(),
                        task_id,
                    ),
                )
                await self.db.execute(
                    "UPDATE ai_task_context SET version=version+1 WHERE task_id=?", (task_id,)
                )

            selected["_on_content"] = content
            text, i, o, source = await asyncio.wait_for(
                self._stream_completion(selected, compact(data), usage),
                self.settings.ai_stage_timeout_seconds,
            )
            await usage(i, o, source)
            await content(text)
            return text

        if context["kind"] == "assistant":
            text = await invoke("assistant", ASSISTANT_PROMPT, payload, assistant=True)
            if not text.strip():
                raise AuthoringError("模型未返回可见回答，请检查输出预算或模型配置")
            result: dict[str, Any] = {
                "kind": "assistant",
                "text": text,
                "code_hash": digest(payload["code"]),
            }
            await self.db.execute(
                "UPDATE ai_tasks SET result=? WHERE id=?", (compact(result), task_id)
            )
            await self._update(task_id, "completed", "回答已完成", "completed")
            return

        base = payload.get("base_problem")
        target = payload.get("target_section", "all")
        action = payload.get("action", "generate")
        requirement = payload["requirement"]
        if action == "verify":
            assets = payload.get("assets", {})
            generated = GeneratedProblem.model_validate(
                {
                    "problem": base,
                    **{
                        k: assets.get(
                            k, "" if k.endswith("solution") or k == "generator_code" else None
                        )
                        for k in (
                            "reference_solution",
                            "brute_solution",
                            "generator_code",
                            "review",
                            "coverage",
                            "wrong_solutions",
                        )
                    },
                }
            )
            await self._validate_generated(
                task_id, generated, task_row, payload.get("source_revision")
            )
            return
        if action == "review":
            text = await invoke(
                "review_only",
                REVIEW_PROMPT + "\nReturn {review:string} only. No patch.",
                {"requirement": requirement, "problem": base, "assets": payload.get("assets", {})},
            )
            review = _extract_json(text).get("review")
            if not isinstance(review, str) or not review.strip():
                raise AuthoringError("审查意见为空")
            await self.db.execute(
                "UPDATE ai_tasks SET result=? WHERE id=?",
                (compact({"kind": "review", "review": review}), task_id),
            )
            await self._update(task_id, "completed", "审查完成，建议待采纳", "completed")
            return
        if action in {"revise", "tests"} and target != "all":
            if not base:
                raise AuthoringError("局部修改需要完整草稿")
            model = Problem.model_validate(base)
            fields = SECTION_FIELDS.get(target, (target,))
            system = (
                section_prompt(target)
                if target in SECTION_FIELDS
                else (
                    f"Edit only {target}. Return JSON {{{target}: value, review: string}}. "
                    "Preserve all other fields. IO is literal and every test must be valid."
                )
            )
            small_context = {
                k: v for k, v in base.items() if k != "testcases" or target == "testcases"
            }
            first = await invoke(
                "section", system, {"requirement": requirement, "problem": small_context}
            )
            text = await invoke(
                "section_review",
                system + "\nReview and correct the proposed edit.",
                {"requirement": requirement, "problem": small_context, "proposal": first},
            )
            parsed = _extract_json(text)
            if target in SECTION_FIELDS:
                result = merge_section(model, target, parsed)
            else:
                if set(parsed) != {target, "review"} or not isinstance(parsed["review"], str):
                    raise AuthoringError("局部修改结构不正确")
                updated = model.model_dump()
                updated.update({k: parsed[k] for k in fields})
                result = {
                    "kind": "section_patch",
                    "target_section": target,
                    "problem": Problem.model_validate(updated).model_dump(),
                    "baseline": model.model_dump(),
                    "review": parsed["review"],
                    "verification": {"quality_gate_passed": False, "scope": "section_only"},
                }
            result.update(
                {"reviewed": True, "source_draft_revision": payload.get("source_revision")}
            )
            await self.db.execute(
                "UPDATE ai_tasks SET result=? WHERE id=?", (compact(result), task_id)
            )
            await self._update(
                task_id, "completed", "局部建议已复审，待采纳后重新验证", "completed"
            )
            return

        candidate: dict[str, Any] = {
            k: v
            for k, v in payload.get("resume_candidate", {}).items()
            if k in GeneratedProblem.model_fields
        }
        feedback = ""
        try:
            if not candidate.get("problem") or not candidate.get("reference_solution"):
                first = await invoke(
                    "statement",
                    STATEMENT_PROMPT,
                    {
                        "requirement": requirement,
                        "existing_problem": {
                            k: v for k, v in (base or {}).items() if k != "testcases"
                        },
                    },
                )
                candidate = _extract_json(first)
                candidate = {
                    k: v for k, v in candidate.items() if k in {"problem", "reference_solution"}
                }
            if not {"problem", "reference_solution"} <= set(candidate):
                raise ValueError("Stage 1 must contain problem and reference_solution")
            if not isinstance(candidate["problem"], dict):
                raise ValueError("Stage 1 problem must be an object")
            candidate["problem"]["testcases"] = candidate["problem"].get("testcases") or [
                {"input": "", "output": ""}
            ]
            Problem.model_validate(candidate["problem"])
            await self.db.execute(
                "UPDATE ai_tasks SET result=? WHERE id=?",
                (compact({"kind": "candidate", **candidate}), task_id),
            )
        except (ValueError, ValidationError) as exc:
            feedback = str(exc)[:1500]
            if not isinstance(candidate.get("problem"), dict):
                candidate["problem"] = {}
        assets = ""
        if not all(
            candidate.get(k)
            for k in ("coverage", "brute_solution", "generator_code", "wrong_solutions")
        ):
            assets = await invoke(
                "assets",
                ASSETS_PROMPT,
                {
                    "requirement": requirement,
                    "candidate": candidate,
                    "previous_stage_issues": feedback,
                },
            )
        try:
            if assets:
                values = _extract_json(assets)
                if set(values) - {
                    "testcases", "brute_solution", "generator_code", "wrong_solutions",
                    "coverage", "review",
                }:
                    raise ValueError("Stage 2 may not rewrite problem or reference_solution")
                tests = values.pop("testcases")
                candidate.setdefault("problem", {})["testcases"] = tests
                candidate.update(values)
        except (ValueError, KeyError) as exc:
            feedback += "\n" + str(exc)[:1000]
        await self.db.execute(
            "UPDATE ai_tasks SET result=? WHERE id=?",
            (compact({"kind": "candidate", **candidate}), task_id),
        )
        review_text = await invoke(
            "critique",
            REVIEW_PROMPT,
            {"requirement": requirement, "candidate": candidate, "local_feedback": feedback},
        )
        initial_problem = json.loads(compact(candidate.get("problem", {})))
        try:
            review = _extract_json(review_text)
            candidate = merge_patch(candidate, review["patch"])
            candidate["review"] = review["review"]
            generated = GeneratedProblem.model_validate(candidate)
            await self._validate_generated(
                task_id, generated, task_row, payload.get("source_revision"), initial_problem
            )
        except (ValueError, KeyError, AuthoringError) as exc:
            # Only deterministic structure/validation failures reach the single repair call.
            if isinstance(exc, AuthoringError) and "草稿已修改" in str(exc):
                raise
            await self.db.execute(
                "UPDATE ai_task_context SET repair_used=1 WHERE task_id=?", (task_id,)
            )
            preview["repair_reason"] = str(exc)[:3000]
            await self._preview(task_id, preview)
            fixed = await invoke(
                "repair",
                REVIEW_PROMPT,
                {
                    "requirement": requirement,
                    "candidate": candidate,
                    "local_feedback": str(exc)[:3000],
                },
            )
            repair = _extract_json(fixed)
            candidate = merge_patch(candidate, repair["patch"])
            candidate["review"] = repair["review"]
            generated = GeneratedProblem.model_validate(candidate)
            await self._validate_generated(
                task_id, generated, task_row, payload.get("source_revision"), initial_problem
            )
