from collections.abc import AsyncIterator
from typing import Annotated, Any

import httpx
from fastapi import Depends

from backend.app.auth.service import get_app_settings
from backend.app.common.errors import APIError
from backend.app.config import Settings


async def get_simulator_client(
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        base_url=settings.simulator_internal_url,
        timeout=httpx.Timeout(10.0),
    ) as client:
        yield client


async def proxy_simulator_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        response = await client.request(method, path, json=payload)
    except httpx.RequestError as error:
        raise APIError(
            502,
            "SIMULATOR_UNAVAILABLE",
            "Simulator control service is unavailable",
        ) from error
    if response.status_code == 404:
        raise APIError(
            404,
            "SIMULATOR_TARGET_NOT_FOUND",
            "Simulator target was not found",
        )
    if response.status_code >= 400:
        raise APIError(
            502,
            "SIMULATOR_CONTROL_FAILED",
            "Simulator control service rejected the operation",
            {"upstream_status": response.status_code},
        )
    try:
        result = response.json()
    except ValueError as error:
        raise APIError(
            502,
            "SIMULATOR_INVALID_RESPONSE",
            "Simulator control service returned an invalid response",
        ) from error
    if not isinstance(result, dict):
        raise APIError(
            502,
            "SIMULATOR_INVALID_RESPONSE",
            "Simulator control service returned an invalid response",
        )
    return result
