from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from oj.auth import CurrentUser, require_admin
from oj.errors import response
from oj.main_support import bootstrap_database

router = APIRouter(prefix="/api")


@router.post("/reset/")
async def reset_system(
    request: Request, _admin: CurrentUser = Depends(require_admin)
) -> JSONResponse:
    # Finish cancelling workers before IDs/data are reset; no stale worker can overwrite a new row.
    await request.app.state.ai_authoring.close()
    await request.app.state.submissions.cancel_all()
    async with request.app.state.db.connect() as db:
        for table in (
            "sessions",
            "submission_cases",
            "access_logs",
            "role_change_logs",
            "ai_tasks",
            "ai_configs",
            "submissions",
            "languages",
            "users",
        ):
            await db.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed internal table list
        await db.execute("DELETE FROM sqlite_sequence")
        await db.commit()
    await request.app.state.problems.reset()
    await bootstrap_database(request.app.state.db)
    result = response(200, "system reset successfully")
    result.delete_cookie(request.app.state.settings.session_cookie)
    return result

