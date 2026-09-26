from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.security import TokenError, decode_access_token
from app.auth.users import User
from app.services.container import Container

_bearer = HTTPBearer(auto_error=False)


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    container: Container = Depends(get_container),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None or creds.scheme.lower() != "bearer":
        raise unauthorized
    try:
        claims = decode_access_token(creds.credentials)
    except TokenError:
        raise unauthorized from None
    user = container.users.get(claims["sub"])
    if user is None or not user.is_active:
        raise unauthorized
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user


def rate_limit(
    response: Response, user: User = Depends(get_current_user), container: Container = Depends(get_container)
) -> User:
    allowed, remaining, reset = container.rate_limiter.check(user.username)
    headers = {
        "X-RateLimit-Limit": str(container.rate_limiter.limit),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(reset),
    }
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={**headers, "Retry-After": str(reset)},
        )
    response.headers.update(headers)
    return user
