"""Verify Supabase access tokens using JWKS or a legacy shared secret."""

from __future__ import annotations

from typing import Any

import jwt

from app.auth.models import CurrentUser
from app.core.config import Settings


class JwtVerifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._algorithms = [item.strip() for item in settings.jwt_algorithms.split(",") if item.strip()]
        self._jwks_client = jwt.PyJWKClient(settings.jwt_jwks_url) if settings.jwt_jwks_url else None
        if settings.auth_enabled and not settings.jwt_secret and self._jwks_client is None:
            raise ValueError("auth_enabled_but_jwt_verification_key_missing")

    def verify(self, token: str) -> CurrentUser:
        if not self._algorithms:
            raise ValueError("jwt_algorithms_required")
        key: Any
        if self._settings.jwt_secret:
            key = self._settings.jwt_secret
        elif self._jwks_client is not None:
            key = self._jwks_client.get_signing_key_from_jwt(token).key
        else:
            raise ValueError("jwt_verification_key_required")

        options = {"require": ["exp", "iat", "sub"]}
        claims = jwt.decode(
            token,
            key=key,
            algorithms=self._algorithms,
            audience=self._settings.jwt_audience or None,
            issuer=self._settings.jwt_issuer or None,
            options=options,
        )
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise jwt.InvalidTokenError("jwt_subject_required")
        app_metadata = claims.get("app_metadata")
        metadata_role = app_metadata.get("role") if isinstance(app_metadata, dict) else None
        role = metadata_role if isinstance(metadata_role, str) and metadata_role else "user"
        email = claims.get("email")
        return CurrentUser(
            id=subject,
            email=email if isinstance(email, str) else None,
            role=role,
            claims=dict(claims),
        )
