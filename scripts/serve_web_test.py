"""Isolated local browser test server. Never loads .env or the user's runtime database."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

import uvicorn

from oj.config import Settings
from oj.main import create_app

runtime = tempfile.TemporaryDirectory(prefix="oj-web-test-")
root = Path(runtime.name)
app = create_app(
    Settings(
        _env_file=None,
        database_path=root / "oj.db",
        problem_dir=root / "problems",
        seed_problem_dir=Path(__file__).resolve().parents[1] / "data" / "problem_seeds",
        ai_encryption_key="browser-test-only",
        ai_default_provider_url="https://example.com/v1",
        ai_default_model="browser-fixture",
        ai_default_api_key="fixture-not-a-real-key",
    )
)


async def completion(config: Any, prompt: str, usage: Any = None) -> tuple[str, int, int, str]:
    data = json.loads(prompt)
    if "programming tutor" in config["system_prompt"]:
        text = (
            "### 输入提示\n\n先检查输入：两个整数需要相加。\n\n```python\n"
            "a, b = map(int, input().split())\nprint(a + b)\n```"
        )
    elif "Stage 1:" in config["system_prompt"]:
        text = json.dumps(
            {
                "problem": {
                    "id": "browser_sum",
                    "title": "浏览器验收求和题",
                    "description": "输入两个整数，输出和。",
                    "input_description": "一行两个整数。",
                    "output_description": "输出一个整数。",
                    "constraints": "绝对值不超过 10^9。",
                    "samples": [{"input": "1 2", "output": "3"}],
                    "testcases": [],
                    "difficulty": "入门",
                    "tags": ["基础"],
                },
                "reference_solution": "a,b=map(int,input().split());print(a+b)",
            },
            ensure_ascii=False,
        )
    elif "Stage 2:" in config["system_prompt"]:
        text = json.dumps(
            {
                "testcases": [
                    {"input": f"{a} {b}", "output": str(a + b)}
                    for a, b in [(1, 2), (0, 0), (-2, 3), (-1, -2), (10**9, -(10**9))]
                ],
                "brute_solution": "print(sum(map(int,input().split())))",
                "generator_code": (
                    "import json\nprint(json.dumps([f'{i} {-i}' for i in range(20)]))"
                ),
                "wrong_solutions": [
                    {
                        "code": "a,b=map(int,input().split());print(a-b)",
                        "reason": "将加法误写为减法",
                    },
                    {
                        "code": "a,b=map(int,input().split());print(abs(a)+abs(b))",
                        "reason": "忽略了整数的负号",
                    },
                ],
                "coverage": {
                    "basic": "普通正数求和输入",
                    "boundary": "零与负数边界输入",
                    "scale": "最大整数规模输入",
                },
                "review": "所有输入符合范围，复杂度为 O(1)。",
            },
            ensure_ascii=False,
        )
    elif "editing ONLY" in config["system_prompt"]:
        text = json.dumps(
            {"samples": [{"input": "3 4", "output": "7"}], "review": "小规模样例清晰，输出正确。"}
        )
    else:
        text = json.dumps({"patch": {}, "review": "已经检查题目、独立 oracle 和边界输入。"})
    if data.get("message") == "模拟慢速回答":
        await config["_on_content"]("已收到，正在生成…")
        await asyncio.sleep(30)
    for end in range(25, len(text) + 25, 25):
        if config.get("_on_content"):
            await config["_on_content"](text[:end])
        await asyncio.sleep(0.025)
    if usage:
        await usage(20, 40, "provider", 0)
    return text, 20, 40, "provider"


app.state.ai_authoring._stream_completion = completion

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
