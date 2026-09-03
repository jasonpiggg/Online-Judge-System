from __future__ import annotations

from datetime import datetime

from oj.database import Database
from oj.languages import seed_languages
from oj.security import hash_password


async def bootstrap_database(db: Database) -> None:
    admin = await db.fetchone("SELECT id FROM users WHERE username='admin'")
    if admin is None:
        await db.execute(
            "INSERT INTO users(username,password_hash,role,join_time) VALUES(?,?,?,?)",
            (
                "admin",
                await hash_password("admintestpassword"),
                "admin",
                datetime.now().strftime("%Y-%m-%d"),
            ),
        )
    await seed_languages(db)

