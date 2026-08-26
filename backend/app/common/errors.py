from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class APIError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


async def api_error_handler(_request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, APIError):
        raise exception
    return JSONResponse(
        status_code=exception.status_code,
        content={
            "error": {
                "code": exception.code,
                "message": exception.message,
                "details": exception.details,
            }
        },
    )
