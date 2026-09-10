"""CPU-bound password primitives exposed as non-blocking async helpers."""

from __future__ import annotations

import asyncio

import bcrypt


def validate_password_bytes(password: str) -> str:
    if len(password.encode("utf-8")) > 72:
        raise ValueError("密码最多 72 个 UTF-8 字节；旧超长密码请联系管理员人工重设")
    return password


async def hash_password(password: str) -> bytes:
    validate_password_bytes(password)
    return await asyncio.to_thread(bcrypt.hashpw, password.encode(), bcrypt.gensalt())


async def verify_password(password: str, password_hash: bytes) -> bool:
    validate_password_bytes(password)
    return await asyncio.to_thread(bcrypt.checkpw, password.encode(), password_hash)

