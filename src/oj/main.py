from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from oj.ai_experience import AIExperience
from oj.config import Settings
from oj.database import Database
from oj.errors import install_error_handlers
from oj.main_support import bootstrap_database
from oj.problem_store import ProblemStore
from oj.routers.ai import router as ai_router
from oj.routers.auth_users import router as auth_users_router
from oj.routers.authoring import router as authoring_router
from oj.routers.languages import router as languages_router
from oj.routers.logs import router as logs_router
from oj.routers.problems import router as problems_router
from oj.routers.submissions import router as submissions_router
from oj.routers.system import router as system_router
from oj.routers.workspace import router as workspace_router
from oj.submissions import SubmissionManager
from oj.web import install_web


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()
    db = Database(app_settings.database_path)
    problems = ProblemStore(app_settings.problem_dir, app_settings.seed_problem_dir)
    submissions = SubmissionManager(db, problems)
    ai_authoring = AIExperience(db, problems, app_settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await db.initialize()
        await ai_authoring.initialize_system_config()
        await bootstrap_database(db)
        await problems.initialize()
        await ai_authoring.recover()
        await submissions.recover()
        yield
        await ai_authoring.close()
        await submissions.close()

    app = FastAPI(title="Atelier OJ API", version="1.2.0", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.db = db
    app.state.problems = problems
    app.state.submissions = submissions
    app.state.ai_authoring = ai_authoring
    install_error_handlers(app)
    app.include_router(auth_users_router)
    app.include_router(languages_router)
    app.include_router(problems_router)
    app.include_router(submissions_router)
    app.include_router(logs_router)
    app.include_router(system_router)
    app.include_router(ai_router)
    app.include_router(authoring_router)
    app.include_router(workspace_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    install_web(app)
    return app


app = create_app()
