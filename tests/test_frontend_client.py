from __future__ import annotations

from typing import Any

import pytest
import requests

from frontend.client import ApiClient, ApiError


class FakeResponse:
    def __init__(self, status: int, payload: Any = None, *, broken_json: bool = False) -> None:
        self.status_code = status
        self.payload = payload
        self.broken_json = broken_json

    def json(self) -> Any:
        if self.broken_json:
            raise requests.exceptions.JSONDecodeError("bad", "<html>", 0)
        return self.payload


class FakeSession:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response

    def request(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def api_with(response: FakeResponse | Exception) -> ApiClient:
    api = object.__new__(ApiClient)
    api.base_url = "http://test"
    api.session = FakeSession(response)  # type: ignore[assignment]
    return api


def test_client_validates_response_protocol() -> None:
    assert api_with(FakeResponse(200, {"code": 200, "msg": "ok", "data": 1})).get("/")[
        "data"
    ] == 1
    with pytest.raises(RuntimeError, match="code"):
        api_with(FakeResponse(200, {"code": 201, "msg": "ok", "data": None})).get("/")
    with pytest.raises(RuntimeError, match="协议"):
        api_with(FakeResponse(200, {"value": 1})).get("/")


def test_client_handles_non_json_and_banned() -> None:
    with pytest.raises(ApiError, match="无法解析"):
        api_with(FakeResponse(502, broken_json=True)).get("/")
    with pytest.raises(RuntimeError, match="无法解析"):
        api_with(FakeResponse(200, broken_json=True)).get("/")
    with pytest.raises(ApiError, match="账户已被禁用") as banned:
        api_with(
            FakeResponse(403, {"code": 403, "msg": "user is banned", "data": None})
        ).get("/")
    assert banned.value.server_message == "user is banned"


def test_client_separates_timeout_from_connection_failure() -> None:
    with pytest.raises(RuntimeError, match="请求超时"):
        api_with(requests.Timeout()).get("/")
    with pytest.raises(RuntimeError, match="后端服务"):
        api_with(requests.ConnectionError()).get("/")
