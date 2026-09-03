from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(message)


class ApiClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("OJ_API_URL", "http://127.0.0.1:8000").rstrip("/")
        if "http_session" not in st.session_state:
            st.session_state.http_session = requests.Session()
        self.session: requests.Session = st.session_state.http_session

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            result = self.session.request(method, f"{self.base_url}{path}", timeout=15, **kwargs)
            payload = result.json()
            if result.status_code >= 400:
                messages = {403: "没有执行此操作的权限。", 429: "一分钟最多提交 3 次，请稍后重试。"}
                raise ApiError(
                    result.status_code,
                    messages.get(
                        result.status_code, payload.get("msg", f"HTTP {result.status_code}")
                    ),
                )
            return payload
        except requests.RequestException as exc:
            raise RuntimeError("后端服务暂时不可用，请确认 FastAPI 已启动。") from exc

    def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self.request("DELETE", path, **kwargs)
