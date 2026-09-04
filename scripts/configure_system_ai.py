"""Explicitly sync .env nonsecret model/pricing policy, preserving encrypted credentials."""

from __future__ import annotations

import argparse
import asyncio

from oj.ai_authoring import AIAuthoringManager
from oj.config import Settings
from oj.database import Database
from oj.problem_store import ProblemStore


async def apply() -> None:
    settings = Settings()
    db = Database(settings.database_path)
    await db.initialize()
    manager = AIAuthoringManager(
        db, ProblemStore(settings.problem_dir, settings.seed_problem_dir), settings
    )
    await manager.sync_system_policy()
    print("System model policy and pricing synced; credentials preserved; no paid API call.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", required=True)
    parser.parse_args()
    try:
        asyncio.run(apply())
    except Exception as exc:
        # Avoid Pydantic/HTTP exceptions exposing server configuration.
        print(f"Sync failed ({type(exc).__name__}); check server configuration and master key.")
        raise SystemExit(1) from None
