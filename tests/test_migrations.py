import asyncio
from pathlib import Path

import aiosqlite

from oj.database import SCHEMA, Database


async def test_legacy_database_backup_and_idempotent_migration(tmp_path: Path) -> None:
    path = tmp_path / "oj.db"
    async with aiosqlite.connect(path) as old:
        await old.executescript(SCHEMA)
        await old.execute("INSERT INTO users VALUES(1,'preserved',X'00','user','old')")
        await old.commit()
    db = Database(path)
    await db.initialize()
    await db.initialize()
    row = await db.fetchone("SELECT username FROM users WHERE id=1")
    assert row["username"] == "preserved"
    assert (await db.fetchone("PRAGMA user_version"))[0] == 5
    columns = await db.fetchall("PRAGMA table_info(ai_tasks)")
    assert {"draft_id", "parent_task_id", "action", "target_section"} <= {
        row["name"] for row in columns
    }
    assert await db.fetchone(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='workspace_drafts'"
    )
    backups = await asyncio.to_thread(lambda: list(tmp_path.glob("oj.pre-v0-*.db")))
    assert len(backups) == 1
    backup = Database(backups[0])
    assert (await backup.fetchone("PRAGMA user_version"))[0] == 0
    assert (await backup.fetchone("SELECT username FROM users WHERE id=1"))[0] == "preserved"


async def test_v3_upgrade_preserves_personal_config_and_backs_up(tmp_path: Path) -> None:
    db = Database(tmp_path / "oj.db")
    await db.initialize()
    await db.execute("DROP TABLE ai_system_config")
    for table in ("ai_configs", "ai_tasks"):
        await db.execute(f"ALTER TABLE {table} DROP COLUMN currency")
    await db.execute("ALTER TABLE ai_configs DROP COLUMN cached_input_price")
    await db.execute("PRAGMA user_version=3")
    await db.execute("INSERT INTO users VALUES(1,'old',X'00','user','old')")
    await db.execute(
        "INSERT INTO ai_configs VALUES(1,'https://example.com/v1','model',X'0102',0,0,1000000)"
    )
    await db.initialize()
    await db.initialize()
    assert (await db.fetchone("PRAGMA user_version"))[0] == 5
    assert (await db.fetchone("SELECT encrypted_api_key FROM ai_configs"))[0] == b"\x01\x02"
    assert await db.fetchone("SELECT * FROM ai_system_config") is None
    backups = await asyncio.to_thread(lambda: list(tmp_path.glob("oj.pre-v3-*.db")))
    assert len(backups) == 1
