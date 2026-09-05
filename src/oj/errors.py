from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def payload(
    code: int, msg: str, data: Any = None, error: dict[str, Any] | None = None
) -> dict[str, Any]:
    value = {"code": code, "msg": msg, "data": data}
    if error is not None:
        value["error"] = error
    return value


def response(code: int = 200, msg: str = "success", data: Any = None) -> JSONResponse:
    return JSONResponse(status_code=code, content=payload(code, msg, data))


class APIError(Exception):
    def __init__(
        self,
        code: int,
        msg: str,
        *,
        error_id: str | None = None,
        title: str | None = None,
        suggestion: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.msg = msg
        self.error_id = error_id
        self.title = title
        self.suggestion = suggestion
        self.headers = headers or {}
        super().__init__(msg)


def _error_details(code: int, msg: str) -> dict[str, Any]:
    lowered = msg.lower()
    if code == 401:
        key, title, suggestion = (
            "auth_required", "需要重新登录", "重新登录后再试，浏览器中的草稿会继续保留。"
        )
    elif code == 403:
        key, title, suggestion = (
            "permission_denied",
            "当前账号没有权限",
            "返回上一页，或联系管理员确认账号角色与资源权限。",
        )
    elif code == 404:
        key, title, suggestion = (
            "not_found", "没有找到请求的内容", "检查链接或编号是否正确，内容也可能已被归档或删除。"
        )
    elif code == 409:
        key, title, suggestion = (
            "conflict", "当前内容已发生变化", "刷新并比较最新版本后再保存，避免覆盖其他页面的修改。"
        )
    elif code == 429:
        key, title, suggestion = (
            "rate_limited", "操作过于频繁", "稍等片刻后重试，不要连续提交相同请求。"
        )
    elif code >= 500:
        key, title, suggestion = (
            "service_error",
            "服务暂时无法完成操作",
            "保留当前内容并稍后重试；问题持续存在时查看服务日志。",
        )
    else:
        key, title, suggestion = (
            "invalid_request", "提交的内容需要调整", "检查标红字段和填写格式后再次提交。"
        )
    if "model" in lowered or "ai" in lowered:
        suggestion = "检查个人模型地址、模型名称、API Key 与账户额度后重试。"
    return {
        "id": key,
        "title": title,
        "message": msg,
        "suggestion": suggestion,
        "retryable": code in {409, 429} or code >= 500,
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def api_error_handler(_request: Request, exc: APIError) -> JSONResponse:
        details = _error_details(exc.code, exc.msg)
        if exc.error_id:
            details["id"] = exc.error_id
        if exc.title:
            details["title"] = exc.title
        if exc.suggestion:
            details["suggestion"] = exc.suggestion
        return JSONResponse(
            status_code=exc.code,
            content=payload(exc.code, exc.msg, error=details),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = [
            {"field": ".".join(str(part) for part in item["loc"][1:]), "message": item["msg"]}
            for item in exc.errors()
        ]
        details = _error_details(400, "invalid request parameters")
        details["id"] = "validation_error"
        details["fields"] = fields
        return JSONResponse(
            status_code=400,
            content=payload(400, "invalid request parameters", error=details),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
        message = "internal server error"
        return JSONResponse(
            status_code=500,
            content=payload(500, message, error=_error_details(500, message)),
        )

