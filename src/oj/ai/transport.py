"""Pin validated DNS answers while retaining the original TLS SNI and HTTP Host."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import AsyncIterator

import httpx


def public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


class PinnedTransport(httpx.AsyncHTTPTransport):
    def __init__(self, *, allow_private: bool = False) -> None:
        super().__init__(
            trust_env=False, retries=0, limits=httpx.Limits(max_keepalive_connections=0)
        )
        self.allow_private = allow_private

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.scheme != "https" and not self.allow_private:
            raise ValueError("AI provider requires HTTPS")
        answers = await asyncio.to_thread(
            socket.getaddrinfo,
            request.url.host,
            request.url.port or 443,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
        )
        addresses = list(dict.fromkeys(str(answer[4][0]) for answer in answers))
        if not addresses or (not self.allow_private and not all(map(public_address, addresses))):
            raise ValueError("AI provider has a non-public connection target")
        # The underlying connector receives a numeric IP, never the untrusted hostname.
        # TLS still verifies the original provider certificate, not the selected IP.
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=addresses[0]),
            headers=request.headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": request.url.host},
        )
        return await super().handle_async_request(pinned)


async def bounded_sse_lines(
    response: httpx.Response, *, max_wire_bytes: int = 8_000_000
) -> AsyncIterator[str]:
    pending = bytearray()
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_wire_bytes:
            raise ValueError("AI stream exceeds wire limit")
        pending.extend(chunk)
        while (newline := pending.find(b"\n")) >= 0:
            if newline > 2_500_000:
                raise ValueError("AI stream event exceeds limit")
            line = bytes(pending[:newline]).decode("utf-8").rstrip("\r")
            del pending[: newline + 1]
            yield line
        if len(pending) > 2_500_000:
            raise ValueError("AI stream event exceeds limit")
    if pending:
        yield pending.decode("utf-8").rstrip("\r")
