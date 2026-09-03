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
    assert (await db.fetchone("PRAGMA user_version"))[0] == 2
    backups = await asyncio.to_thread(lambda: list(tmp_path.glob("oj.pre-v0-*.db")))
    assert len(backups) == 1
    backup = Database(backups[0])
    assert (await backup.fetchone("PRAGMA user_version"))[0] == 0
    assert (await backup.fetchone("SELECT username FROM users WHERE id=1"))[0] == "preserved"
