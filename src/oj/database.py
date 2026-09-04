from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash BLOB NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin','banned')),
    join_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS languages (
    name TEXT PRIMARY KEY,
    file_ext TEXT NOT NULL,
    compile_cmd TEXT,
    run_cmd TEXT NOT NULL,
    time_limit REAL NOT NULL DEFAULT 3,
    memory_limit INTEGER NOT NULL DEFAULT 128
);
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    problem_id TEXT NOT NULL,
    language TEXT NOT NULL,
    code TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending','success','error')),
    score INTEGER,
    counts INTEGER,
    compile_info TEXT,
    run_info TEXT,
    error_info TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS submission_cases (
    submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    case_id INTEGER NOT NULL,
    result TEXT NOT NULL,
    time REAL NOT NULL,
    memory REAL NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(submission_id, case_id)
);
CREATE TABLE IF NOT EXISTS access_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    problem_id TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT 'view_logs',
    time TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_configs (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    provider_url TEXT NOT NULL,
    model TEXT NOT NULL,
    encrypted_api_key BLOB NOT NULL,
    input_price REAL NOT NULL DEFAULT 0,
    output_price REAL NOT NULL DEFAULT 0,
    price_unit INTEGER NOT NULL DEFAULT 1000000
);
CREATE TABLE IF NOT EXISTS ai_system_config (
    id INTEGER PRIMARY KEY CHECK(id=1),
    provider_url TEXT NOT NULL,
    model TEXT NOT NULL,
    encrypted_api_key BLOB NOT NULL,
    input_price REAL NOT NULL DEFAULT 0,
    output_price REAL NOT NULL DEFAULT 0,
    price_unit INTEGER NOT NULL DEFAULT 1000000
);
CREATE TABLE IF NOT EXISTS ai_tasks (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    requirement TEXT NOT NULL,
    problem_id TEXT,
    status TEXT NOT NULL,
    progress TEXT NOT NULL,
    result TEXT,
    error TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    usage_source TEXT NOT NULL DEFAULT 'estimated',
    cost REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workspace_drafts (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    problem_id TEXT NOT NULL,
    language TEXT NOT NULL,
    code TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(user_id, problem_id, language)
);
CREATE TABLE IF NOT EXISTS problem_drafts (
    id TEXT PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    base_problem_id TEXT,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft','verifying','ready','published','archived')),
    requirement TEXT NOT NULL DEFAULT '',
    problem_json TEXT NOT NULL DEFAULT '{}',
    reference_solution TEXT NOT NULL DEFAULT '',
    brute_solution TEXT NOT NULL DEFAULT '',
    generator_code TEXT NOT NULL DEFAULT '',
    review_json TEXT NOT NULL DEFAULT '{}',
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS problem_draft_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id TEXT NOT NULL REFERENCES problem_drafts(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    source TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    change_summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(draft_id, revision)
);
CREATE TABLE IF NOT EXISTS verification_runs (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL REFERENCES problem_drafts(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK(status IN ('pending','running','passed','failed','cancelled')),
    report_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_submissions_user_created ON submissions(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_submissions_problem_created ON submissions(problem_id, created_at);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
CREATE INDEX IF NOT EXISTS idx_access_logs_user_problem ON access_logs(user_id, problem_id);
CREATE INDEX IF NOT EXISTS idx_workspace_drafts_user_updated
    ON workspace_drafts(user_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_problem_drafts_owner_updated
    ON problem_drafts(owner_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_verification_runs_draft
    ON verification_runs(draft_id, created_at);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def initialize(self) -> None:
        await asyncio.to_thread(self.path.parent.mkdir, parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("PRAGMA user_version")
            version = (await cursor.fetchone())[0]  # type: ignore[index]
            await cursor.close()
            if version > 6:
                raise RuntimeError("Database schema is newer than this application")
            existing = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            has_tables = bool(await existing.fetchone())
            await existing.close()
            if version < 6 and has_tables:
                stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
                backup_path = self.path.with_name(f"{self.path.stem}.pre-v{version}-{stamp}.db")
                async with aiosqlite.connect(backup_path) as backup:
                    await db.backup(backup)
            await db.executescript(SCHEMA)
            if version < 1:
                # DDL + version commit together; reruns do not reset any business data.
                await db.execute("BEGIN IMMEDIATE")
                await db.execute(
                    "ALTER TABLE ai_tasks ADD COLUMN stage TEXT NOT NULL DEFAULT 'queued'"
                )
                await db.execute("ALTER TABLE ai_tasks ADD COLUMN usage_details TEXT")
                await db.execute("PRAGMA user_version = 1")
                await db.commit()
            if version < 2:
                await db.execute("BEGIN IMMEDIATE")
                await db.execute("""CREATE TABLE role_change_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_id INTEGER NOT NULL, target_id INTEGER NOT NULL,
                    old_role TEXT NOT NULL, new_role TEXT NOT NULL, time TEXT NOT NULL
                )""")
                await db.execute("PRAGMA user_version = 2")
                await db.commit()
            if version < 3:
                await db.execute("BEGIN IMMEDIATE")
                columns_cursor = await db.execute("PRAGMA table_info(ai_tasks)")
                columns = {row[1] for row in await columns_cursor.fetchall()}
                await columns_cursor.close()
                additions = {
                    "draft_id": "TEXT",
                    "parent_task_id": "TEXT",
                    "action": "TEXT NOT NULL DEFAULT 'generate'",
                    "target_section": "TEXT",
                }
                for name, declaration in additions.items():
                    if name not in columns:
                        await db.execute(
                            f"ALTER TABLE ai_tasks ADD COLUMN {name} {declaration}"  # noqa: S608
                        )
                await db.execute("PRAGMA user_version = 3")
                await db.commit()
            if version < 4:
                # The singleton table is independent of user records and survives reset.
                await db.execute("PRAGMA user_version = 4")
                await db.commit()
            if version < 5:
                await db.execute("BEGIN IMMEDIATE")
                for table in ("ai_configs", "ai_system_config", "ai_tasks"):
                    await db.execute(
                        f"ALTER TABLE {table} ADD COLUMN currency TEXT NOT NULL "  # noqa: S608
                        "DEFAULT 'USD' CHECK(currency IN ('USD','CNY'))"
                    )
                for table in ("ai_configs", "ai_system_config"):
                    await db.execute(
                        f"ALTER TABLE {table} ADD COLUMN cached_input_price REAL"  # noqa: S608
                    )
                await db.execute(
                    "ALTER TABLE ai_system_config ADD COLUMN routing_config TEXT "
                    "NOT NULL DEFAULT '{}'"
                )
                await db.execute("PRAGMA user_version = 5")
                await db.commit()
            if version < 6:
                await db.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS ai_conversations (
                        id TEXT PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        problem_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(user_id, problem_id)
                    );
                    CREATE TABLE IF NOT EXISTS ai_task_context (
                        task_id TEXT PRIMARY KEY REFERENCES ai_tasks(id) ON DELETE CASCADE,
                        kind TEXT NOT NULL DEFAULT 'authoring',
                        conversation_id TEXT REFERENCES ai_conversations(id) ON DELETE CASCADE,
                        payload TEXT NOT NULL,
                        config_snapshot BLOB NOT NULL,
                        fingerprint TEXT NOT NULL,
                        preview TEXT NOT NULL DEFAULT '{}',
                        version INTEGER NOT NULL DEFAULT 0,
                        stage_started_at TEXT,
                        repair_used INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE TABLE IF NOT EXISTS ai_request_keys (
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        request_key TEXT NOT NULL,
                        fingerprint TEXT NOT NULL,
                        task_id TEXT NOT NULL REFERENCES ai_tasks(id) ON DELETE CASCADE,
                        PRIMARY KEY(user_id,request_key)
                    );
                    CREATE INDEX IF NOT EXISTS idx_ai_conversation_tasks
                        ON ai_task_context(conversation_id);
                    PRAGMA user_version = 6;
                    COMMIT;
                """)
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA optimize")
            await db.commit()

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
        finally:
            await db.close()

    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> aiosqlite.Row | None:
        async with self.connect() as db:
            cursor = await db.execute(sql, tuple(params))
            return await cursor.fetchone()

    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        async with self.connect() as db:
            cursor = await db.execute(sql, tuple(params))
            return list(await cursor.fetchall())

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        async with self.connect() as db:
            cursor = await db.execute(sql, tuple(params))
            await db.commit()
            return int(cursor.lastrowid or 0)
