"""Same-origin browser integration; API errors must never fall through to the SPA."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.base import RequestResponseEndpoint


def install_web(app: FastAPI, directory: Path | None = None) -> None:
    root = (directory or Path(__file__).resolve().parents[2] / "web" / "dist").resolve()

    @app.middleware("http")
    async def browser_boundary(request: Request, call_next: RequestResponseEndpoint) -> Response:
        origin = request.headers.get("origin")
        bridge_paths = {
            "/api/auth/login": "POST",
            "/api/users/": "POST",
            "/api/auth/logout": "POST",
            "/api/auth/me": "GET",
        }
        bridge = bool(
            origin
            and request.url.path in bridge_paths
            and origin in getattr(getattr(app.state, "settings", None), "streamlit_origins", ())
            and request.method in {"OPTIONS", bridge_paths[request.url.path]}
        )
        if bridge and request.method == "OPTIONS":
            requested = request.headers.get("access-control-request-method", "")
            headers = request.headers.get("access-control-request-headers", "").lower()
            if requested != bridge_paths[request.url.path] or any(
                header.strip() not in {"", "content-type"} for header in headers.split(",")
            ):
                return Response(status_code=403)
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": str(origin),
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Allow-Methods": requested,
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Vary": "Origin",
                },
            )
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            # Native/API clients do not send Origin. Reject opaque and cross-origin browsers.
            if origin:
                try:
                    supplied = urlsplit(origin)
                except ValueError:
                    supplied = urlsplit("invalid:")
                allowed = {f"{request.url.scheme}://{request.url.netloc}"}
                if request.url.hostname in {"127.0.0.1", "localhost"}:
                    allowed.add(f"http://{request.url.hostname}:5173")
                if supplied.path or supplied.query or (origin not in allowed and not bridge):
                    return JSONResponse(
                        {"code": 403, "msg": "cross-origin write rejected", "data": None},
                        status_code=403,
                    )
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse(
                    {"code": 403, "msg": "cross-site write rejected", "data": None},
                    status_code=403,
                )
        response = await call_next(request)
        if bridge:
            response.headers["Access-Control-Allow-Origin"] = str(origin)
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Expose-Headers"] = "Retry-After"
            response.headers["Vary"] = "Origin"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.api_route(
        "/{path:path}",
        methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    async def frontend(path: str, request: Request) -> Response:
        if request.method not in {"GET", "HEAD"}:
            return JSONResponse({"code": 404, "msg": "not found", "data": None}, status_code=404)
        if path == "api" or path.startswith("api/"):
            return JSONResponse({"code": 404, "msg": "not found", "data": None}, status_code=404)
        asset = (root / path).resolve()
        if not asset.is_relative_to(root):
            return Response(status_code=404)
        if asset.is_file():
            return FileResponse(asset)
        if path.startswith("assets/") or Path(path).suffix:
            return Response(status_code=404)
        index = root / "index.html"
        if not index.is_file():
            return JSONResponse(
                {"code": 503, "msg": "Web UI 未构建：请在 web 目录运行 npm ci 和 npm run build"},
                status_code=503,
            )
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
