from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str, server_message: str = "") -> None:
        self.status = status
        self.server_message = server_message
        super().__init__(message)


class ApiClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("OJ_API_URL", "http://127.0.0.1:8000").rstrip("/")
        if "http_session" not in st.session_state:
            session = requests.Session()
            retry = Retry(
                total=2,
                connect=2,
                read=1,
                status=2,
                status_forcelist=(502, 503, 504),
                allowed_methods=frozenset({"GET"}),
                backoff_factor=0.15,
                raise_on_status=False,
            )
            session.mount("http://", HTTPAdapter(max_retries=retry))
            session.mount("https://", HTTPAdapter(max_retries=retry))
            st.session_state.http_session = session
        self.session: requests.Session = st.session_state.http_session

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            result = self.session.request(method, f"{self.base_url}{path}", timeout=15, **kwargs)
            try:
                payload = result.json()
            except requests.exceptions.JSONDecodeError as exc:
                if result.status_code >= 400:
                    raise ApiError(
                        result.status_code,
                        f"服务返回 HTTP {result.status_code}，但错误内容无法解析。",
                    ) from exc
                raise RuntimeError("后端返回了无法解析的响应，请检查 API 或代理配置。") from exc
            if not isinstance(payload, dict) or not {"code", "msg", "data"} <= payload.keys():
                raise RuntimeError("后端响应不符合 {code, msg, data} 协议。")
            if payload["code"] != result.status_code:
                raise RuntimeError("后端 HTTP 状态与响应 code 不一致。")
            if result.status_code >= 400:
                server_message = str(payload.get("msg", ""))
                if result.status_code == 403 and "banned" in server_message.casefold():
                    message = "账户已被禁用，请联系管理员。"
                else:
                    messages = {
                        403: "没有执行此操作的权限。",
                        429: "一分钟最多提交 3 次，请稍后重试。",
                    }
                    message = messages.get(
                        result.status_code, server_message or f"HTTP {result.status_code}"
                    )
                raise ApiError(
                    result.status_code,
                    message,
                    server_message,
                )
            return payload
        except ApiError:
            raise
        except requests.Timeout as exc:
            raise RuntimeError("请求超时，请稍后重试。") from exc
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
