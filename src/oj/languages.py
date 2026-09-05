from __future__ import annotations

import shlex
import sys

import aiosqlite

from oj.database import Database
from oj.errors import APIError
from oj.schemas import Language

SAFE_EXECUTABLES = {
    "python",
    "python3",
    "g++",
    "gcc",
    "java",
    "javac",
    "node",
    "go",
    "rustc",
}
FORBIDDEN_SHELL_CHARS = frozenset(";&|><`\n\r")


def command_argv(template: str, *, src: str, exe: str) -> list[str]:
    if any(char in template for char in FORBIDDEN_SHELL_CHARS):
        raise ValueError("shell operators are not allowed")
    if "{" in template.replace("{src}", "").replace("{exe}", ""):
        raise ValueError("only {src} and {exe} placeholders are allowed")
    argv = shlex.split(template)
    if not argv:
        raise ValueError("command may not be empty")
    executable = argv[0]
    if executable not in SAFE_EXECUTABLES and executable != "{exe}":
        raise ValueError("executable is not in the safe allowlist")
    expanded = [part.replace("{src}", src).replace("{exe}", exe) for part in argv]
    if executable in {"python", "python3"}:
        # Python submissions run in the server's managed environment. This keeps
        # declared course packages consistent and avoids PATH alias differences.
        expanded[0] = sys.executable
    return expanded


def validate_language(language: Language) -> None:
    source = "/workspace/main" + language.file_ext
    executable = "/workspace/program"
    try:
        run = command_argv(language.run_cmd, src=source, exe=executable)
        if source not in run and executable not in run:
            raise ValueError("run command must reference {src} or {exe}")
        if language.compile_cmd:
            compile_argv = command_argv(language.compile_cmd, src=source, exe=executable)
            if source not in compile_argv or executable not in compile_argv:
                raise ValueError("compile command must reference {src} and {exe}")
    except ValueError as exc:
        raise APIError(400, f"unsafe language configuration: {exc}") from exc


async def seed_languages(db: Database) -> None:
    defaults = (
        ("python", ".py", None, "python3 {src}", 3.0, 128),
        ("cpp", ".cpp", "g++ {src} -O2 -std=c++14 -o {exe}", "{exe}", 3.0, 128),
    )
    async with db.connect() as connection:
        await connection.executemany(
            """INSERT OR IGNORE INTO languages
               (name,file_ext,compile_cmd,run_cmd,time_limit,memory_limit)
               VALUES(?,?,?,?,?,?)""",
            defaults,
        )
        await connection.commit()


async def add_language(db: Database, language: Language) -> None:
    validate_language(language)
    try:
        await db.execute(
            """INSERT INTO languages(name,file_ext,compile_cmd,run_cmd,time_limit,memory_limit)
               VALUES(?,?,?,?,?,?)""",
            (
                language.name,
                language.file_ext,
                language.compile_cmd,
                language.run_cmd,
                language.time_limit,
                language.memory_limit,
            ),
        )
    except aiosqlite.IntegrityError as exc:
        raise APIError(409, "language already exists") from exc


async def get_language(db: Database, name: str) -> Language | None:
    row = await db.fetchone("SELECT * FROM languages WHERE name=?", (name,))
    return Language.model_validate(dict(row)) if row else None

