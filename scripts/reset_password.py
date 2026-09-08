"""Explicit local operator recovery; never print or accept a password in argv."""

from __future__ import annotations

import argparse
import asyncio
import getpass

from oj.config import Settings
from oj.database import Database
from oj.schemas import Credentials
from oj.security import hash_password


async def reset_password(db: Database, username: str, password: str) -> None:
    credentials = Credentials(username=username, password=password)
    encoded = await hash_password(credentials.password)
    async with db.connect() as connection:
        await connection.execute("BEGIN IMMEDIATE")
        cursor = await connection.execute("SELECT id FROM users WHERE username=?", (username,))
        row = await cursor.fetchone()
        if row is None:
            raise ValueError("User does not exist")
        await connection.execute(
            "UPDATE users SET password_hash=? WHERE id=?", (encoded, row["id"])
        )
        await connection.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
        await connection.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    args = parser.parse_args()
    password = getpass.getpass("New password (6+ characters, <=72 UTF-8 bytes): ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match; nothing changed")
    if input(f"Reset {args.username} and revoke their sessions? Type RESET: ") != "RESET":
        raise SystemExit("Cancelled; nothing changed")
    try:
        asyncio.run(reset_password(Database(Settings().database_path), args.username, password))
    except ValueError:
        # Pydantic exception text includes input values: do not print it.
        raise SystemExit("Invalid username/password or missing user; nothing changed") from None
    print("Password reset; previous sessions revoked")


if __name__ == "__main__":
    main()
