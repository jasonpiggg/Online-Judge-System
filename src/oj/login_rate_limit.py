from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from oj.errors import APIError


@dataclass(frozen=True)
class LoginAttempt:
    client: str
    account: tuple[str, str]


class LoginRateLimiter:
    """Bound failed logins without trusting proxy-controlled address headers."""

    def __init__(
        self,
        *,
        account_limit: int,
        account_window: float,
        client_limit: int,
        client_window: float,
        lockout: float,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.account_limit = account_limit
        self.account_window = account_window
        self.client_limit = client_limit
        self.client_window = client_window
        self.lockout = lockout
        self.max_keys = max_keys
        self.clock = clock
        self._lock = asyncio.Lock()
        self._accounts: dict[tuple[str, str], deque[float]] = {}
        self._clients: dict[str, deque[float]] = {}
        self._account_blocks: dict[tuple[str, str], float] = {}
        self._client_blocks: dict[str, float] = {}
        self._account_inflight: dict[tuple[str, str], int] = {}
        self._client_inflight: dict[str, int] = {}
        self._next_cleanup = 0.0
        self._cleanup_interval = max(1.0, min(account_window, client_window, lockout) / 2)

    @staticmethod
    def _trim(values: deque[float], cutoff: float) -> None:
        while values and values[0] <= cutoff:
            values.popleft()

    def _purge(self, now: float) -> None:
        for account_key, values in list(self._accounts.items()):
            self._trim(values, now - self.account_window)
            if not values:
                self._accounts.pop(account_key, None)
        for client_key, values in list(self._clients.items()):
            self._trim(values, now - self.client_window)
            if not values:
                self._clients.pop(client_key, None)
        self._account_blocks = {
            key: expiry for key, expiry in self._account_blocks.items() if expiry > now
        }
        self._client_blocks = {
            key: expiry for key, expiry in self._client_blocks.items() if expiry > now
        }
        while len(self._accounts) > self.max_keys:
            oldest_account = min(self._accounts, key=lambda item: self._accounts[item][-1])
            self._accounts.pop(oldest_account, None)
            self._account_blocks.pop(oldest_account, None)
        while len(self._clients) > self.max_keys:
            oldest_client = min(self._clients, key=lambda item: self._clients[item][-1])
            self._clients.pop(oldest_client, None)
            self._client_blocks.pop(oldest_client, None)
        while len(self._account_blocks) > self.max_keys:
            earliest_account = min(self._account_blocks, key=self._account_blocks.__getitem__)
            self._account_blocks.pop(earliest_account, None)
        while len(self._client_blocks) > self.max_keys:
            earliest_client = min(self._client_blocks, key=self._client_blocks.__getitem__)
            self._client_blocks.pop(earliest_client, None)

    def _maybe_purge(self, now: float) -> None:
        if now < self._next_cleanup:
            return
        self._purge(now)
        self._next_cleanup = now + self._cleanup_interval

    @staticmethod
    def _bounded_history[K](
        histories: dict[K, deque[float]],
        blocks: dict[K, float],
        key: K,
        max_keys: int,
    ) -> deque[float]:
        values = histories.get(key)
        if values is not None:
            return values
        if len(histories) >= max_keys:
            oldest = next(iter(histories))
            histories.pop(oldest, None)
            blocks.pop(oldest, None)
        values = deque()
        histories[key] = values
        return values

    @staticmethod
    def _set_bounded_block[K](blocks: dict[K, float], key: K, expiry: float, max_keys: int) -> None:
        if key not in blocks and len(blocks) >= max_keys:
            earliest = min(blocks, key=blocks.__getitem__)
            blocks.pop(earliest, None)
        blocks[key] = expiry

    @staticmethod
    def _blocked(retry_after: float) -> APIError:
        seconds = max(1, math.ceil(retry_after))
        return APIError(
            429,
            "too many failed login attempts",
            error_id="login_rate_limited",
            title="登录尝试过于频繁",
            suggestion=f"请等待 {seconds} 秒后再试。",
            headers={"Retry-After": str(seconds)},
        )

    async def begin(self, client: str, username: str) -> LoginAttempt:
        """Atomically reserve an attempt so concurrent failures cannot exceed limits."""
        key = (client, username.casefold())
        async with self._lock:
            now = self.clock()
            self._maybe_purge(now)
            expiry = max(
                self._account_blocks.get(key, 0),
                self._client_blocks.get(client, 0),
            )
            if expiry > now:
                raise self._blocked(expiry - now)
            account = self._accounts.get(key, deque())
            client_attempts = self._clients.get(client, deque())
            if len(account) + self._account_inflight.get(key, 0) >= self.account_limit:
                raise self._blocked(1)
            if (
                len(client_attempts) + self._client_inflight.get(client, 0)
                >= self.client_limit
            ):
                raise self._blocked(1)
            self._account_inflight[key] = self._account_inflight.get(key, 0) + 1
            self._client_inflight[client] = self._client_inflight.get(client, 0) + 1
            return LoginAttempt(client=client, account=key)

    def _release(self, attempt: LoginAttempt) -> None:
        account_count = self._account_inflight.get(attempt.account, 0) - 1
        client_count = self._client_inflight.get(attempt.client, 0) - 1
        if account_count > 0:
            self._account_inflight[attempt.account] = account_count
        else:
            self._account_inflight.pop(attempt.account, None)
        if client_count > 0:
            self._client_inflight[attempt.client] = client_count
        else:
            self._client_inflight.pop(attempt.client, None)

    async def record_failure(self, attempt: LoginAttempt) -> None:
        async with self._lock:
            now = self.clock()
            self._maybe_purge(now)
            self._release(attempt)
            account = self._bounded_history(
                self._accounts,
                self._account_blocks,
                attempt.account,
                self.max_keys,
            )
            client_attempts = self._bounded_history(
                self._clients,
                self._client_blocks,
                attempt.client,
                self.max_keys,
            )
            account.append(now)
            client_attempts.append(now)
            if len(account) >= self.account_limit:
                self._set_bounded_block(
                    self._account_blocks,
                    attempt.account,
                    now + self.lockout,
                    self.max_keys,
                )
                account.clear()
            if len(client_attempts) >= self.client_limit:
                self._set_bounded_block(
                    self._client_blocks,
                    attempt.client,
                    now + self.lockout,
                    self.max_keys,
                )
                client_attempts.clear()

    async def record_success(self, attempt: LoginAttempt) -> None:
        async with self._lock:
            self._release(attempt)
            self._accounts.pop(attempt.account, None)
            self._account_blocks.pop(attempt.account, None)

    async def cancel(self, attempt: LoginAttempt) -> None:
        async with self._lock:
            self._release(attempt)
