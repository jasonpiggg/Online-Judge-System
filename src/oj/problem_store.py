from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path

from oj.schemas import Problem


class ProblemStore:
    def __init__(self, directory: Path, seed_directory: Path) -> None:
        self.directory = directory
        self.seed_directory = seed_directory
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _initialize_sync(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.seed_directory.exists():
            for source in self.seed_directory.glob("*.json"):
                target = self.directory / source.name
                if not target.exists():
                    shutil.copy2(source, target)
        for path in self.directory.glob("*.json"):
            Problem.model_validate_json(path.read_text(encoding="utf-8"))

    def _path(self, problem_id: str) -> Path:
        return self.directory / f"{problem_id}.json"

    async def list(self) -> list[dict[str, str]]:
        def read_all() -> list[dict[str, str]]:
            result = []
            for path in sorted(self.directory.glob("*.json")):
                problem = Problem.model_validate_json(path.read_text(encoding="utf-8"))
                result.append({"id": problem.id, "title": problem.title})
            return result

        return await asyncio.to_thread(read_all)

    async def get(self, problem_id: str) -> Problem | None:
        path = self._path(problem_id)
        if not path.is_file():
            return None
        return await asyncio.to_thread(self._read_problem, path)

    @staticmethod
    def _read_problem(path: Path) -> Problem:
        return Problem.model_validate_json(path.read_text(encoding="utf-8"))

    async def create(self, problem: Problem) -> bool:
        async with self._lock:
            if self._path(problem.id).exists():
                return False
            await asyncio.to_thread(self._atomic_write, problem)
            return True

    async def update(self, problem: Problem) -> bool:
        async with self._lock:
            if not self._path(problem.id).exists():
                return False
            await asyncio.to_thread(self._atomic_write, problem)
            return True

    async def delete(self, problem_id: str) -> bool:
        async with self._lock:
            path = self._path(problem_id)
            if not path.exists():
                return False
            await asyncio.to_thread(path.unlink)
            return True

    async def reset(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._reset_sync)

    def _reset_sync(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        for path in self.directory.glob("*.json"):
            path.unlink()
        self._initialize_sync()

    def _atomic_write(self, problem: Problem) -> None:
        data = json.dumps(problem.model_dump(), ensure_ascii=False, indent=2)
        fd, temporary = tempfile.mkstemp(prefix=".problem-", dir=self.directory, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path(problem.id))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
