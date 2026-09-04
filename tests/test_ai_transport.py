from typing import Any

import httpx
import pytest

from oj.ai_transport import PinnedTransport, bounded_sse_lines, public_address


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "::1", "169.254.169.254", "10.0.0.1", "::ffff:127.0.0.1", "224.0.0.1", "0.0.0.0"],  # noqa: S104 - validation input, not a bind
    ids=[
        "loopback-v4",
        "loopback-v6",
        "link-local",
        "private",
        "mapped",
        "multicast",
        "unspecified",
    ],
)
def test_non_public_addresses(ip: str) -> None:
    assert not public_address(ip)


async def test_transport_pins_address_and_tls_identity(monkeypatch: Any) -> None:
    def dns(*_args: Any) -> list[Any]:
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    async def send(_self: Any, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "provider.example"
        assert request.extensions["sni_hostname"] == "provider.example"
        return httpx.Response(200)

    monkeypatch.setattr("oj.ai_transport.socket.getaddrinfo", dns)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", send)
    async with PinnedTransport() as transport:
        await transport.handle_async_request(httpx.Request("GET", "https://provider.example/v1"))


async def test_transport_blocks_rebinding_and_http(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "oj.ai_transport.socket.getaddrinfo", lambda *_: [(2, 1, 6, "", ("127.0.0.1", 443))]
    )
    async with PinnedTransport() as transport:
        with pytest.raises(ValueError, match="non-public"):
            await transport.handle_async_request(httpx.Request("GET", "https://provider.example"))
        with pytest.raises(ValueError, match="HTTPS"):
            await transport.handle_async_request(httpx.Request("GET", "http://provider.example"))


@pytest.mark.parametrize(
    "payload",
    [b"a" * 2_500_001, b"a" * 2_500_001 + b"\n", b"a\n" * 4_000_001],
    ids=["long-partial-event", "long-complete-event", "wire-limit"],
)
async def test_sse_memory_bounds(payload: bytes) -> None:
    response = httpx.Response(200, content=payload)
    with pytest.raises(ValueError, match="limit"):
        _ = [line async for line in bounded_sse_lines(response)]


async def test_sse_final_line() -> None:
    response = httpx.Response(200, content=b"data: {}")
    assert [line async for line in bounded_sse_lines(response)] == ["data: {}"]


async def test_sse_wire_budget_is_configurable_but_bounded() -> None:
    response = httpx.Response(200, content=b"data: a\ndata: b\n")
    with pytest.raises(ValueError, match="wire limit"):
        _ = [line async for line in bounded_sse_lines(response, max_wire_bytes=10)]
    assert [line async for line in bounded_sse_lines(response, max_wire_bytes=16)] == [
        "data: a",
        "data: b",
    ]
