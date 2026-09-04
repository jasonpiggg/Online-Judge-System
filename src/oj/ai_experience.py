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
from oj.ai_presentation import check_presentation, presentation_issues
from oj.ai_prompts import (
    ASSETS_PROMPT,
    ASSISTANT_PROMPT,
    DISPLAY_RULES,
    PROMPT_VERSION,
    REVIEW_PROMPT,
    STATEMENT_PROMPT,
    TARGETED_REPAIR_PROMPT,
)
from oj.ai_sections import SECTION_FIELDS, merge_section, section_prompt
from oj.difficulty import normalize_difficulty
from oj.errors import APIError
from oj.evaluation import evaluation_summary
from oj.judge import judge_code
from oj.languages import get_language
from oj.schemas import GeneratedProblem, Problem

ASSISTANT_HISTORY_TURNS = 4
ASSISTANT_HISTORY_BYTES = 20_000


def repair_scope(message: str) -> dict[str, str]:
    if "错误解法" in message:
        return {
            "wrong_solutions": "2-4 个可运行但会被测试点卡错的错误解",
            "problem.testcases": "仅在卡错所必需时补充测试点",
            "review": "修复说明",
        }
    if "随机数据生成器" in message:
        return {
            "generator_code": "输出 20-100 个唯一输入字符串 JSON 数组的 Python 程序",
            "review": "修复说明",
        }
    if "oracle" in message.lower() or "对拍" in message:
        return {
            "brute_solution": "独立算法实现",
            "generator_code": "必要时同步修正输入生成器",
            "review": "修复说明",
        }
    if "参考解" in message:
        return {
            "reference_solution": "正确的标准输入输出程序",
            "problem.samples": "仅在期望输出错误时修正",
            "problem.testcases": "仅在期望输出错误时修正",
            "review": "修复说明",
        }
    return {
        "problem": "只修复反馈指出的题目字段",
        "reference_solution": "仅在反馈相关时修正",
        "brute_solution": "仅在反馈相关时修正",
        "generator_code": "仅在反馈相关时修正",
        "wrong_solutions": "仅在反馈相关时修正",
        "coverage": "仅在反馈相关时修正",
        "review": "修复说明",
    }


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
            if (
                name == "samples"
                and isinstance(value, list)
                and all(
                    isinstance(item, dict)
                    and isinstance(item.get("input"), str)
                    and isinstance(item.get("output"), str)
                    for item in value
                )
            ) or (name != "samples" and isinstance(value, str)):
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

    async def start_new_topic(self, user_id: int, conversation_id: str) -> int:
        """Advance the context boundary without deleting earlier usage history."""
        async with self.intake_lock, self.db.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "SELECT context_generation FROM ai_conversations WHERE id=? AND user_id=?",
                (conversation_id, user_id),
            )
            conversation = await cursor.fetchone()
            if conversation is None:
                raise APIError(404, "conversation not found")
            cursor = await db.execute(
                "SELECT COUNT(*) AS n FROM ai_tasks t JOIN ai_task_context c "
                "ON c.task_id=t.id WHERE c.conversation_id=? "
                "AND t.status IN ('pending','running')",
                (conversation_id,),
            )
            active = await cursor.fetchone()
            if active is not None and active["n"]:
                raise APIError(409, "当前回答仍在生成，请先等待完成或停止任务")
            generation = int(conversation["context_generation"]) + 1
            await db.execute(
                "UPDATE ai_conversations SET context_generation=? WHERE id=?",
                (generation, conversation_id),
            )
            await db.commit()
            return generation

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
        async with self.intake_lock:
            context_generation = 0
            if kind == "assistant":
                conversation = await self.db.fetchone(
                    "SELECT context_generation FROM ai_conversations WHERE id=? AND user_id=?",
                    (conversation_id, user_id),
                )
                if conversation is None:
                    raise APIError(404, "conversation not found")
                context_generation = int(conversation["context_generation"])
            # A retried Idempotency-Key keeps identifying the same paid request,
            # even if the user has since started a new topic.
            request_hash = digest({"kind": kind, "conversation_id": conversation_id, **request})
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
                draft_problem = json.loads(draft["problem_json"])
                if "difficulty" in draft_problem:
                    draft_problem["difficulty"] = normalize_difficulty(draft_problem["difficulty"])
                payload["base_problem"] = draft_problem
                payload["source_revision"] = draft["revision"]
                payload["assets"] = {
                    k: draft[k] for k in ("reference_solution", "brute_solution", "generator_code")
                }
                payload["assets"].update(json.loads(draft["review_json"]))
            # Alias normalization must not make an unchanged pre-upgrade task unresumable.
            if payload.get("resume_task_id"):
                previous_base = previous.get("base_problem")
                if isinstance(previous_base, dict) and "difficulty" in previous_base:
                    previous_base["difficulty"] = normalize_difficulty(previous_base["difficulty"])
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
                        "time_limit",
                        "memory_limit",
                    )
                }
                if payload.get("submission_id"):
                    submission = await self.db.fetchone(
                        "SELECT user_id,problem_id,language,code,status,score,counts,compile_info,"
                        "run_info,error_info "
                        "FROM submissions WHERE id=?",
                        (payload["submission_id"],),
                    )
                    if not submission or submission["user_id"] != user_id:
                        raise APIError(404, "submission not found")
                    if submission["problem_id"] != problem_id:
                        raise APIError(400, "提交与当前题目不匹配")
                    cases = await self.db.fetchall(
                        "SELECT case_id AS id,result,time,memory FROM submission_cases "
                        "WHERE submission_id=? ORDER BY case_id",
                        (payload["submission_id"],),
                    )
                    payload["submission"] = {
                        "id": payload["submission_id"],
                        "language": submission["language"],
                        "code": submission["code"],
                        "code_matches_current": submission["code"] == payload.get("code")
                        and submission["language"] == payload.get("language"),
                        "evaluation": evaluation_summary(
                            dict(submission), [dict(c) for c in cases]
                        ),
                        "cases": [dict(c) for c in cases],
                        "compile_info": submission["compile_info"],
                        "run_info": submission["run_info"],
                        "error_info": submission["error_info"],
                    }
                if len(compact(payload).encode()) > 100000:
                    raise APIError(400, "当前题目与代码超过上下文容量，请选择较小的代码片段")
            fingerprint_input = {
                "kind": kind,
                "conversation": conversation_id,
                **payload,
            }
            if kind == "assistant":
                fingerprint_input["context_generation"] = context_generation
            fingerprint = digest(fingerprint_input)
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
                    "WHERE c.conversation_id=? AND c.context_generation=? "
                    "AND t.status='completed' ORDER BY t.created_at DESC "
                    "LIMIT ?",
                    (conversation_id, context_generation, ASSISTANT_HISTORY_TURNS + 1),
                )
                turns = []
                budget = ASSISTANT_HISTORY_BYTES
                history_limited = len(history) > ASSISTANT_HISTORY_TURNS
                for row in history[:ASSISTANT_HISTORY_TURNS]:
                    previous = json.loads(row["payload"])
                    answer = json.loads(row["result"] or "{}")
                    turn = {
                        "user": previous.get("message"),
                        "assistant": answer.get("text", ""),
                        "code_version": digest(previous.get("code", "")),
                        "submission_id": previous.get("submission_id"),
                        "evaluation": previous.get("submission", {}).get("evaluation"),
                        "submission_code_matches_current": (
                            previous.get("submission", {}).get("code") == payload.get("code")
                            and previous.get("submission", {}).get("language")
                            == payload.get("language")
                        ),
                        "same_as_current_code": previous.get("code") == payload.get("code")
                        and previous.get("language") == payload.get("language"),
                    }
                    budget -= len(compact(turn).encode())
                    if budget < 0:
                        history_limited = True
                        break
                    turns.append(turn)
                payload["history"] = list(reversed(turns))
                payload["history_policy"] = {
                    "maximum_turns": ASSISTANT_HISTORY_TURNS,
                    "maximum_bytes": ASSISTANT_HISTORY_BYTES,
                    "older_context_omitted": history_limited,
                }
            config = dict(config)
            config["_output_limits"] = dict(self.settings.ai_model_output_limits)
            config["encrypted_api_key"] = config["encrypted_api_key"].decode()
            config_blob = self.cipher.encrypt(compact(config).encode())
            task_id, now = "ai-" + secrets.token_urlsafe(12), utcnow()
            async with self.db.connect() as db:
                await db.execute("BEGIN IMMEDIATE")
                initial_progress = (
                    "等待本地验证" if payload.get("action") == "verify" else "等待模型连接"
                )
                await db.execute(
                    "INSERT INTO ai_tasks(id,user_id,requirement,problem_id,draft_id,action,"
                    "target_section,status,progress,stage,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,'pending',?,'queued',?,?)",
                    (
                        task_id,
                        user_id,
                        payload.get("requirement", payload.get("message", "")),
                        problem_id,
                        payload.get("draft_id"),
                        payload.get("action", "assist"),
                        payload.get("target_section", "all"),
                        initial_progress,
                        now,
                        now,
                    ),
                )
                await db.execute(
                    "INSERT INTO ai_task_context(task_id,kind,conversation_id,payload,"
                    "config_snapshot,fingerprint,stage_started_at,context_generation) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (
                        task_id,
                        kind,
                        conversation_id,
                        compact(payload),
                        config_blob,
                        fingerprint,
                        now,
                        context_generation,
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

    async def _validate_basic(
        self,
        task_id: str,
        problem: Problem,
        reference_solution: str,
        task_row: Any,
        source_revision: int | None,
    ) -> None:
        """Validate a publishable manual draft without requiring AI quality assets."""
        await self._update(task_id, "running", "正在检查题目结构与排版", "basic_structure")
        prose_issues = presentation_issues(problem.model_dump())
        # A literal dollar in legacy prose is readable, but corrupted commands are not.
        blocking_issues = [
            issue for issue in prose_issues if "unclosed math delimiter" not in issue
        ]
        if blocking_issues:
            raise AuthoringError(
                "题面公式或文本转义有错误。请在“题面与样例”检查公式括号与分隔符，"
                "重新输入损坏的数学符号后再检查。"
            )
        checks: list[dict[str, Any]] = [
            {"id": "schema", "label": "题目字段与限制", "status": "passed"},
            {
                "id": "presentation",
                "label": "Markdown 与数学公式",
                "status": "passed" if not prose_issues else "skipped",
                "detail": (
                    "排版语法正常"
                    if not prose_issues
                    else "发现旧格式排版问题，内容仍可阅读；建议编辑时修正"
                ),
            },
            {
                "id": "cases",
                "label": "样例与测试点格式",
                "status": "passed",
                "detail": f"{len(problem.samples)} 个样例，{len(problem.testcases)} 个测试点",
            },
        ]
        field_names = {
            "description": "题目描述",
            "input_description": "输入格式",
            "output_description": "输出格式",
            "constraints": "数据范围",
            "hint": "提示",
        }
        warnings: list[str] = [
            "旧题排版提示："
            + field_names.get(issue.split(":")[0], "题面")
            + "含未闭合的美元符号。公式请补全 $...$；普通美元符号请写成 \\$。"
            for issue in prose_issues
        ]
        reference_passed: bool | None = None
        if reference_solution.strip():
            await self._update(
                task_id, "running", "正在运行参考解的全部样例与测试点", "basic_reference"
            )
            python = await get_language(self.db, "python")
            if python is None:
                raise AuthoringError("Python 评测语言未注册，无法运行参考解")
            validation_problem = problem.model_copy(
                update={"testcases": [*problem.samples, *problem.testcases]}
            )
            outcome = await asyncio.wait_for(
                judge_code(validation_problem, python, reference_solution),
                self.settings.ai_stage_timeout_seconds,
            )
            if outcome.score != outcome.counts:
                failures = ", ".join(
                    f"#{case.id} {case.result}" for case in outcome.cases if case.result != "AC"
                )
                raise AuthoringError(
                    "参考解没有通过全部样例和测试点："
                    f"{failures}。请检查参考解、输入格式和预期输出。"
                )
            reference_passed = True
            checks.append(
                {
                    "id": "reference",
                    "label": "参考解试跑",
                    "status": "passed",
                    "detail": f"全部 {len(outcome.cases)} 组通过",
                }
            )
        else:
            warnings.append("未提供参考解，因此没有自动核对样例和测试点输出。")
            checks.append(
                {
                    "id": "reference",
                    "label": "参考解试跑",
                    "status": "skipped",
                    "detail": warnings[-1],
                }
            )
        report = {
            "level": "basic",
            "draft_revision": source_revision,
            "quality_gate_passed": False,
            "publishable": True,
            "reference_passed": reference_passed,
            "checks": checks,
            "warnings": warnings,
            "note": "基础检查证明字段可用；未执行的完整质量门禁不影响手工题发布。",
        }
        now = utcnow()
        result = {"kind": "verification", "problem": problem.model_dump(), "verification": report}
        verification_id = "verify-" + secrets.token_urlsafe(12)
        async with self.db.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "SELECT review_json,status FROM problem_drafts "
                "WHERE id=? AND owner_id=? AND revision=?",
                (task_row["draft_id"], task_row["user_id"], source_revision),
            )
            current = await cursor.fetchone()
            if current is None or current["status"] in {"archived", "published"}:
                raise AuthoringError(
                    "草稿已修改、归档或发布；本次检查结果已保留，请对最新版本重新检查。"
                )
            review = json.loads(current["review_json"] or "{}")
            review["verification"] = report
            await db.execute(
                "UPDATE problem_drafts SET status='ready',review_json=?,updated_at=? "
                "WHERE id=? AND owner_id=? AND revision=?",
                (compact(review), now, task_row["draft_id"], task_row["user_id"], source_revision),
            )
            await db.execute(
                "INSERT INTO verification_runs "
                "(id,draft_id,status,report_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (verification_id, task_row["draft_id"], "passed", compact(report), now, now),
            )
            await db.execute(
                "UPDATE ai_tasks SET result=?,draft_id=?,status='completed',"
                "progress='基础检查通过，可以发布',stage='completed',updated_at=? WHERE id=?",
                (compact(result), task_row["draft_id"], now, task_id),
            )
            await db.commit()

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
                    "system_prompt": system + DISPLAY_RULES + "\nProtocol: " + PROMPT_VERSION,
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
                "section_repair": "正在定向修复局部建议（最多一次）",
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
            if payload.get("verification_mode", "full") == "basic":
                await self._validate_basic(
                    task_id,
                    Problem.model_validate(base),
                    payload.get("assets", {}).get("reference_solution", ""),
                    task_row,
                    payload.get("source_revision"),
                )
                return
            assets = payload.get("assets", {})
            try:
                generated = GeneratedProblem.model_validate(
                    {
                        "problem": base,
                        **{
                            k: assets.get(
                                k,
                                "" if k.endswith("solution") or k == "generator_code" else None,
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
            except ValidationError as exc:
                missing = sorted(
                    {str(issue["loc"][0]) for issue in exc.errors() if issue.get("loc")}
                )
                raise AuthoringError(
                    "完整验证资料不完整："
                    + "、".join(missing)
                    + "。请返回草稿的“测试与解法”步骤，补充参考解、错误解、独立 "
                    "oracle 和随机生成器；手工旧题可以先运行基础检查。"
                ) from exc
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
                {
                    "requirement": requirement,
                    "problem": small_context,
                    "proposal": first,
                    "format_check": (
                        "Check math delimiters, LaTeX syntax and JSON escapes; preserve literal IO."
                    ),
                },
            )

            def parse_section(text: str) -> dict[str, Any]:
                parsed = _extract_json(text)
                check_presentation(parsed)
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
                return result

            try:
                result = parse_section(text)
            except (ValueError, AuthoringError) as exc:
                preview["repair_reason"] = str(exc)[:3000]
                await self._preview(task_id, preview)
                await self.db.execute(
                    "UPDATE ai_task_context SET repair_used=1 WHERE task_id=?", (task_id,)
                )
                fixed = await invoke(
                    "section_repair",
                    system,
                    {
                        "requirement": requirement,
                        "problem": small_context,
                        "proposal": text,
                        "local_feedback": str(exc)[:3000],
                    },
                )
                result = parse_section(fixed)
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
            # Recover a misplaced reference without letting model-only keys poison all
            # subsequent patches (Problem's strict schema cannot accept or remove them).
            if isinstance(candidate.get("problem"), dict):
                misplaced = candidate["problem"].get("reference_solution")
                if not candidate.get("reference_solution") and isinstance(misplaced, str):
                    candidate["reference_solution"] = misplaced
                extra = set(candidate["problem"]) - set(Problem.model_fields)
                if extra:
                    feedback += "Removed misplaced problem fields: " + ", ".join(sorted(extra))
                    candidate["problem"] = {
                        k: v for k, v in candidate["problem"].items() if k in Problem.model_fields
                    }
            if not {"problem", "reference_solution"} <= set(candidate):
                raise ValueError("Stage 1 must contain problem and reference_solution")
            if not isinstance(candidate["problem"], dict):
                raise ValueError("Stage 1 problem must be an object")
            candidate["problem"]["testcases"] = candidate["problem"].get("testcases") or [
                {"input": "", "output": ""}
            ]
            candidate["problem"] = Problem.model_validate(candidate["problem"]).model_dump()
            check_presentation(candidate)
            await self.db.execute(
                "UPDATE ai_tasks SET result=? WHERE id=?",
                (compact({"kind": "candidate", "result_version": 2, **candidate}), task_id),
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
                    "testcases",
                    "brute_solution",
                    "generator_code",
                    "wrong_solutions",
                    "coverage",
                    "review",
                }:
                    raise ValueError("Stage 2 may not rewrite problem or reference_solution")
                tests = values.pop("testcases")
                candidate.setdefault("problem", {})["testcases"] = tests
                candidate.update(values)
        except (ValueError, KeyError) as exc:
            feedback += "\n" + str(exc)[:1000]
        await self.db.execute(
            "UPDATE ai_tasks SET result=? WHERE id=?",
            (compact({"kind": "candidate", "result_version": 2, **candidate}), task_id),
        )
        try:
            GeneratedProblem.model_validate(candidate)
        except ValueError as exc:
            feedback += "\nCandidate schema errors: " + self._schema_issues(exc)
        review_text = await invoke(
            "critique",
            REVIEW_PROMPT,
            {
                "requirement": requirement,
                "candidate": candidate,
                "candidate_schema": GeneratedProblem.model_json_schema(),
                "local_feedback": feedback
                + "; ".join(presentation_issues(candidate.get("problem", {}))),
            },
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
            allowed = repair_scope(str(exc))
            fixed = await invoke(
                "repair",
                TARGETED_REPAIR_PROMPT,
                {
                    "requirement": requirement,
                    "candidate": candidate,
                    "allowed_patch": allowed,
                    "local_feedback": str(exc)[:3000],
                },
            )
            repair = _extract_json(fixed)
            patch = repair["patch"]
            if not isinstance(patch, dict):
                raise AuthoringError("定向修复没有返回可用的修改对象") from exc
            allowed_top = {name.split(".", 1)[0] for name in allowed}
            extra_top = set(patch) - allowed_top
            if extra_top:
                raise AuthoringError(
                    "定向修复试图修改无关字段：" + "、".join(sorted(extra_top))
                ) from exc
            nested_allowed = {
                name.split(".", 1)[1]
                for name in allowed
                if name.startswith("problem.")
            }
            if "problem" in patch and nested_allowed:
                if not isinstance(patch["problem"], dict):
                    raise AuthoringError("定向修复中的 problem 必须是对象") from exc
                extra_problem = set(patch["problem"]) - nested_allowed
                if extra_problem:
                    raise AuthoringError(
                        "定向修复试图修改无关题目字段："
                        + "、".join(sorted(extra_problem))
                    ) from exc
            candidate = merge_patch(candidate, patch)
            candidate["review"] = repair["review"]
            generated = GeneratedProblem.model_validate(candidate)
            await self._validate_generated(
                task_id, generated, task_row, payload.get("source_revision"), initial_problem
            )
