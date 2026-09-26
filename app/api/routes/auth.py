from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import get_container, get_current_user
from app.api.schemas import LoginRequest, TokenResponse, UserOut
from app.auth.security import create_access_token
from app.auth.users import User, authenticate
from app.services.container import Container

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue(container: Container, username: str, password: str) -> TokenResponse:
    user = authenticate(container.users, username, password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    minutes = container.settings.jwt_expire_minutes
    return TokenResponse(access_token=create_access_token(user.username, user.role, minutes), expires_in=minutes * 60)


@router.post("/login", response_model=TokenResponse, summary="Exchange credentials for a JWT")
def login(body: LoginRequest, container: Container = Depends(get_container)) -> TokenResponse:
    return _issue(container, body.username, body.password)


@router.post("/token", response_model=TokenResponse, include_in_schema=False)
def token(form: OAuth2PasswordRequestForm = Depends(), container: Container = Depends(get_container)):
    """OAuth2 form variant, used by the Swagger UI 'Authorize' button."""
    return _issue(container, form.username, form.password)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(username=user.username, role=user.role)
