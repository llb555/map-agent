"""Authentication endpoints for the current JWT principal."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.auth.models import CurrentUser

router = APIRouter(prefix="/api/auth", tags=["auth"])


class CurrentUserDto(BaseModel):
    id: str
    email: str | None
    role: str


@router.get("/me", response_model=CurrentUserDto)
def current_user(user: CurrentUser | None = Depends(get_current_user)) -> CurrentUserDto:
    if user is None:
        return CurrentUserDto(id="anonymous", email=None, role="anonymous")
    return CurrentUserDto(id=user.id, email=user.email, role=user.role)
