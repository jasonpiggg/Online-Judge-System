"""Deterministic local HTTP/SSE provider for manual UI acceptance, never a real model."""

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI(title="Atelier OJ acceptance mock (NOT a model)")
ROOT = Path(__file__).resolve().parents[1]


@app.post("/v1/chat/completions")
async def complete(request: Request) -> StreamingResponse:
    await request.json()
    problem = json.loads(
        await asyncio.to_thread(
            (ROOT / "data/problem_seeds/sum_2.json").read_text, encoding="utf-8"
        )
    )
    problem.update(
        id="ai_verified_sum",
        title="整数求和 · AI 验证样题",
        testcases=[
            {"input": f"{a} {b}\n", "output": f"{a + b}\n"}
            for a, b in [(1, 2), (-5, 8), (0, 0), (-7, -9), (10**9, -(10**9))]
        ],
    )
    result = {
        "problem": problem,
        "reference_solution": "a,b=map(int,input().split());print(a+b)",
        "review": "本地 HTTP mock 验收样题，不是供应商模型结果。"
        "O(1) 时间和空间；有限测试不构成复杂度证明。",
        "coverage": {
            "basic": "第 1 个测试点覆盖正数相加",
            "boundary": "第 2-4 个测试点覆盖负数和零",
            "scale": "第 5 个测试点覆盖最大整数范围，输入规模固定为 2",
        },
        "wrong_solutions": [
            {"code": "a,b=map(int,input().split());print(a-b)", "reason": "把求和错误实现成求差"},
            {
                "code": "a,b=map(int,input().split());print(abs(a)+abs(b))",
                "reason": "忽略整数符号造成错误",
            },
        ],
    }

    async def stream():
        text = json.dumps(result, ensure_ascii=False)
        for offset in range(0, len(text), 80):
            yield (
                "data: "
                + json.dumps({"choices": [{"delta": {"content": text[offset : offset + 80]}}]})
                + "\n\n"
            )
            await asyncio.sleep(0.1)
        yield 'data: {"usage":{"prompt_tokens":120,"completion_tokens":360}}\n\n'
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
