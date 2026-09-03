from __future__ import annotations

import asyncio

import bcrypt


async def hash_password(password: str) -> bytes:
    return await asyncio.to_thread(bcrypt.hashpw, password.encode(), bcrypt.gensalt())


async def verify_password(password: str, password_hash: bytes) -> bool:
    return await asyncio.to_thread(bcrypt.checkpw, password.encode(), password_hash)

