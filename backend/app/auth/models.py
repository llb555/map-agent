"""Authenticated principal models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None
    role: str
    claims: dict[str, Any]

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
