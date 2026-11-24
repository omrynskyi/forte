"""One error shape for the whole API:  {"detail": {"code": "...", "message": "...", ...}}

Raise AppError (or a subclass) from services and routers. The frontend switches on `code`, and
shows `message` to the user, so write messages in plain language.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, **extra: object) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.extra = extra


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


class Conflict(AppError):
    """Illegal state transition, duplicate, or a rule like "the last Admin can't be removed"."""

    status_code = 409
    code = "conflict"


class NotImplementedYet(AppError):
    """Skeleton stub. The task ID points at the GitHub issue that implements it."""

    status_code = 501
    code = "not_implemented"

    def __init__(self, task: str) -> None:
        super().__init__(f"Not implemented yet. See task {task}.", task=task)


def todo(task: str):  # noqa: ANN201
    raise NotImplementedYet(task)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": {"code": exc.code, "message": exc.message, **exc.extra}},
        )
