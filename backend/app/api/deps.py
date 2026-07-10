"""API layer: dependency helpers to access shared container from request state."""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.models import CurrentUser
from app.core.container import AppContainer

bearer_scheme = HTTPBearer(auto_error=False)


def get_container(request: Request) -> AppContainer:
    return request.app.state.container  # type: ignore[return-value]


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    container: AppContainer = Depends(get_container),
) -> CurrentUser | None:
    if not container.settings.auth_enabled:
        return None
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication_required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return container.jwt_verifier.verify(credentials.credentials)
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_or_expired_token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_admin(user: CurrentUser | None = Depends(get_current_user)) -> CurrentUser | None:
    if user is not None and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_required")
    return user


def require_authenticated_user(user: CurrentUser | None = Depends(get_current_user)) -> CurrentUser:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication_required")
    return user
