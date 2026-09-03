from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI

from oj.config import Settings
from oj.database import Database
from oj.errors import install_error_handlers
from oj.routers.auth_users import router as auth_users_router
from oj.security import hash_password


async def bootstrap(db: Database) -> None:
    admin = await db.fetchone("SELECT id FROM users WHERE username='admin'")
    if admin is None:
        await db.execute(
            "INSERT INTO users(username,password_hash,role,join_time) VALUES(?,?,?,?)",
            (
                "admin",
                await hash_password("admintestpassword"),
                "admin",
                datetime.now().strftime("%Y-%m-%d"),
            ),
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()
    db = Database(app_settings.database_path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await db.initialize()
        await bootstrap(db)
        yield

    app = FastAPI(title="Atelier OJ API", version="0.1.0", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.db = db
    install_error_handlers(app)
    app.include_router(auth_users_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

