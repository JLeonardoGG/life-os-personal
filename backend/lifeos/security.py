from __future__ import annotations

import hmac

from fastapi import Cookie, Depends, Header, HTTPException, Request, Response, status

from lifeos.config import Settings, get_settings

SESSION_COOKIE = "lifeos_session"
LOCAL_CLIENTS = {"127.0.0.1", "::1", "testclient"}


def _matches(candidate: str | None, expected: str) -> bool:
    return bool(candidate) and hmac.compare_digest(candidate, expected)


def require_local_request(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host not in LOCAL_CLIENTS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local access only")


def require_api_key(
    x_lifeos_api_key: str | None = Header(default=None, alias="X-LifeOS-API-Key"),
    settings: Settings = Depends(get_settings),
) -> None:
    if not _matches(x_lifeos_api_key, settings.api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def require_session_or_api_key(
    request: Request,
    lifeos_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_lifeos_api_key: str | None = Header(default=None, alias="X-LifeOS-API-Key"),
    settings: Settings = Depends(get_settings),
) -> None:
    require_local_request(request)
    if _matches(lifeos_session, settings.session_secret) or _matches(x_lifeos_api_key, settings.api_key):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Local session required")


def create_local_session(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    require_local_request(request)
    response.set_cookie(
        SESSION_COOKIE,
        settings.session_secret,
        httponly=True,
        secure=False,
        samesite="strict",
        max_age=60 * 60 * 24 * 30,
        path="/",
    )
    return {"status": "ok"}
