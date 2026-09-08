"""Authenticate protected routes before FastAPI decodes request bodies."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute


class AuthorizedRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        checks: list[Any] = []
        pending = list(self.dependant.dependencies)
        while pending:
            dependency = pending.pop()
            pending.extend(dependency.dependencies)
            check = dependency.call
            if check and check.__name__ in {
                "get_current_user", "require_admin", "submission_reader"
            } and check not in checks:
                checks.append(check)

        async def authorized(request: Request) -> Response:
            for check in checks:
                await check(request)
            return await handler(request)

        return authorized
