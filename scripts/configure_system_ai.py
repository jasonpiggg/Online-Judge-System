"""Explicitly sync .env nonsecret model/pricing policy, preserving encrypted credentials."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from oj.ai_authoring import AIAuthoringManager
from oj.config import Settings
from oj.database import Database
from oj.problem_store import ProblemStore


async def apply(fast_basic: bool = False) -> None:
    settings = Settings()
    updates = {
        "OJ_AI_ROUTING_ENABLED": "false",
        "OJ_AI_DEFAULT_REASONING_EFFORT": "low",
        "OJ_AI_QUALITY_REASONING_EFFORT": "low",
        "OJ_AI_TASK_TIMEOUT_SECONDS": "240",
    }
    if fast_basic:
        if settings.ai_default_model != "glm-5.3-flash":
            raise RuntimeError(
                "Configure Flash model and its matching prices before enabling fast mode"
            )
        settings = settings.model_copy(
            update={
                "ai_routing_enabled": False,
                "ai_default_reasoning_effort": "low",
                "ai_quality_reasoning_effort": "low",
                "ai_task_timeout_seconds": 240,
            }
        )
    db = Database(settings.database_path)
    await db.initialize()
    manager = AIAuthoringManager(
        db, ProblemStore(settings.problem_dir, settings.seed_problem_dir), settings
    )
    await manager.sync_system_policy()
    if fast_basic:
        # Only these nonsecret policy lines change; credentials and pricing stay byte-for-byte.
        path = Path(".env")
        lines = (await asyncio.to_thread(path.read_text, encoding="utf-8")).splitlines()
        seen = set()
        for index, line in enumerate(lines):
            name = line.partition("=")[0].strip()
            if name in updates:
                lines[index] = f"{name}={updates[name]}"
                seen.add(name)
        lines.extend(f"{name}={value}" for name, value in updates.items() if name not in seen)
        await asyncio.to_thread(path.write_text, "\n".join(lines) + "\n", encoding="utf-8")
    print("System model policy and pricing synced; credentials preserved; no paid API call.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", required=True)
    parser.add_argument("--fast-basic", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(apply(args.fast_basic))
    except Exception as exc:
        # Avoid Pydantic/HTTP exceptions exposing server configuration.
        print(f"Sync failed ({type(exc).__name__}); check server configuration and master key.")
        raise SystemExit(1) from None
